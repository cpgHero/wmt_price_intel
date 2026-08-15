from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from rci_analytics import InMemoryDatasetStore, ParquetDatasetWriter, ProductPackLoader
from rci_collections.models import QueueTask, RawArtifact
from rci_providers import MetricsCartAdapterRegistry
from rci_results import (
    AnalysisResultService,
    AnalysisResultValidator,
    InMemoryReportObjectStore,
    InMemoryResultsRepository,
)
from rci_worker.analysis import (
    AnalysisJob,
    AnalysisProcessor,
    CollectedPage,
    HistoricalSource,
    S3HistoricalCSVReader,
    apply_brand_classification_rules,
    historical_source_row,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
RUN_ID = "00000000-0000-0000-0000-000000000701"


def _task(
    retailer_id: str,
    adapter_id: str,
    product_id: str,
    store_number: str | None,
) -> QueueTask:
    now = datetime.now(UTC)
    return QueueTask(
        id=f"00000000-0000-0000-0000-{product_id[-12:].zfill(12)}",
        collection_run_id=RUN_ID,
        retailer_id=retailer_id,
        retailer_location_id=None,
        adapter_id=adapter_id,
        location_scope_key="zip:44906",
        zipcode="44906",
        store_number=store_number,
        page_number=1,
        max_pages=1,
        stop_on_empty=True,
        stop_on_short_page=False,
        credits_per_success=1 if retailer_id == "walmart_us" else 2,
        request_payload={"keyword": "strawberries"},
        request_fingerprint=f"fingerprint-{retailer_id}",
        status="succeeded",
        priority=100,
        attempt_count=1,
        max_attempts=5,
        available_at=now,
        locked_by=None,
        lease_expires_at=now + timedelta(minutes=5),
        created_at=now,
        http_status=200,
        result_count=1,
        billable_credits=1 if retailer_id == "walmart_us" else 2,
        raw_artifact_id=f"raw-{retailer_id}",
    )


class PageQueue:
    def __init__(self, pages: list[CollectedPage]) -> None:
        self._pages = pages

    async def pages(self, run_id: str) -> list[CollectedPage]:
        assert run_id == RUN_ID
        return self._pages


class HistoricalQueue:
    def __init__(self, sources: list[HistoricalSource]) -> None:
        self._sources = sources

    async def historical_sources(self, input_set_id: str) -> list[HistoricalSource]:
        assert input_set_id == "00000000-0000-0000-0000-000000000704"
        return self._sources


class RawReader:
    def __init__(self, payloads: dict[str, object]) -> None:
        self._payloads = payloads

    async def read(self, page: CollectedPage) -> object:
        return self._payloads[page.task.id]


class HistoricalReader:
    def __init__(self, rows: dict[str, list[dict[str, str]]]) -> None:
        self._rows = rows

    async def read(self, source: HistoricalSource) -> list[dict[str, str]]:
        return self._rows[source.retailer_id]


class ArtifactRecorder:
    def __init__(self) -> None:
        self.artifacts: list[RawArtifact] = []

    async def record_artifact(self, run_id: str, artifact: RawArtifact) -> str:
        assert run_id == RUN_ID
        self.artifacts.append(artifact)
        return artifact.storage_uri


def _payload(product_id: str, price: str) -> dict[str, Any]:
    return {
        "results": [
            {
                "name": "Fresh Strawberries, 1 lb",
                "brand": "Fresh Produce",
                "price": price,
                "retailer_product_id": product_id,
                "url": f"https://retailer.example/items/{product_id}",
                "stock_availability": True,
            }
        ]
    }


def test_consolidated_historical_rows_keep_their_own_retailer_identity() -> None:
    source = HistoricalSource(
        dataset_artifact_id="artifact-eggs",
        input_set_id="input-eggs",
        ordinal=0,
        retailer_id="walmart_us",
        adapter_id="historical_metricscart_consolidated_serp_csv",
        source_name="eggs.csv",
        source_format="metricscart_consolidated_serp_csv",
        storage_uri="s3://raw/eggs.csv",
        checksum="a" * 64,
        row_count=1,
    )

    assert historical_source_row({"Retailer": "aldi.us"}, source) == {"Retailer": "aldi.us"}


def test_single_retailer_historical_rows_use_the_manifest_retailer() -> None:
    source = HistoricalSource(
        dataset_artifact_id="artifact-walmart",
        input_set_id="input-walmart",
        ordinal=0,
        retailer_id="walmart_us",
        adapter_id="historical_metricscart_search_monitor_csv",
        source_name="walmart.csv",
        source_format="metricscart_search_monitor_csv",
        storage_uri="s3://raw/walmart.csv",
        checksum="a" * 64,
        row_count=1,
    )

    assert historical_source_row({"Retailer": "incorrect"}, source)["retailer_id"] == ("walmart_us")


async def test_completed_collection_runs_through_generic_product_pack_pipeline() -> None:
    specifications = [
        (
            "walmart_us",
            "metricscart_walmart_search_zipcode_v2",
            "44391605",
            "2040",
            "$2.98",
        ),
        (
            "aldi_us",
            "metricscart_new_aldi_serp_zipcode",
            "16383764",
            "463-048",
            "$2.49",
        ),
        (
            "amazon_us_same_day",
            "metricscart_amazon_same_day_zipcode",
            "B000P6J0SM",
            None,
            "$3.49",
        ),
    ]
    now = datetime.now(UTC)
    pages: list[CollectedPage] = []
    payloads: dict[str, object] = {}
    for retailer_id, adapter_id, product_id, store_number, price in specifications:
        task = _task(retailer_id, adapter_id, product_id, store_number)
        pages.append(
            CollectedPage(
                task=task,
                storage_uri=f"s3://raw/{task.id}.json.gz",
                checksum="a" * 64,
                collected_at=now,
                latitude=40.7584,
                longitude=-82.5154,
            )
        )
        payloads[task.id] = _payload(product_id, price)

    result_repository = InMemoryResultsRepository()
    result_service = AnalysisResultService(
        result_repository,
        AnalysisResultValidator(REPOSITORY_ROOT),
        InMemoryReportObjectStore(),
    )
    dataset_store = InMemoryDatasetStore()
    artifact_recorder = ArtifactRecorder()
    processor = AnalysisProcessor(
        repository_root=REPOSITORY_ROOT,
        queue=PageQueue(pages),  # type: ignore[arg-type]
        adapters=MetricsCartAdapterRegistry.from_catalog(
            REPOSITORY_ROOT / "config" / "retailer-catalog.json"
        ),
        raw_reader=RawReader(payloads),  # type: ignore[arg-type]
        dataset_writer=ParquetDatasetWriter(dataset_store),
        collections=artifact_recorder,  # type: ignore[arg-type]
        results=result_service,
        code_version="test-version",
    )
    job = AnalysisJob(
        id="00000000-0000-0000-0000-000000000702",
        collection_run_id=RUN_ID,
        input_set_id="00000000-0000-0000-0000-000000000703",
        source_kind="live_collection",
        product_pack_id="fresh_strawberries",
        product_pack_version="1.1.0",
        definition_config={
            "benchmark_retailer": "walmart_us",
            "retailers": [
                {"retailer_id": retailer_id, "enabled": True} for retailer_id, *_ in specifications
            ],
            "delivery": {
                "web_report": False,
                "excel": False,
                "leadership_email": False,
                "audit_package": False,
            },
        },
        attempt_count=1,
        max_attempts=3,
    )

    analysis_id = await processor.process(job)

    analysis = await result_service.get_by_collection_run(RUN_ID)
    assert analysis.analysis_id == analysis_id
    assert analysis.result["schema_version"] == "2.0.0"
    assert analysis.result["source"]["total_rows"] == 3
    assert {row["retailer_id"] for row in analysis.result["coverage"]} == {
        "walmart_us",
        "aldi_us",
        "amazon_us_same_day",
    }
    assert analysis.result["comparisons"]
    assert {mode["comparison_metric"] for mode in analysis.result["comparison_modes"]} == {
        "package_price",
        "price_per_lb",
    }
    assert len(artifact_recorder.artifacts) >= 7
    assert all(uri.endswith(".parquet") for uri in dataset_store.objects)
    publication = await result_service.latest_publication(analysis_id)
    assert publication is not None
    map_points = publication.presentation_context["map_points"]
    assert isinstance(map_points, list)
    assert map_points == []
    suppressed = publication.presentation_context["suppressed_product_decisions"]
    assert suppressed
    assert all(row["qa_status"] == "suppressed" for row in suppressed)
    assert all(
        "Requires at least 25 retained observations" in row["suppression_reasons"]
        for row in suppressed
    )


async def test_historical_input_replays_through_same_generic_pipeline() -> None:
    retailer_ids = ("walmart_us", "aldi_us", "amazon_us_same_day")
    input_set_id = "00000000-0000-0000-0000-000000000704"
    sources = [
        HistoricalSource(
            dataset_artifact_id=f"artifact-{retailer_id}",
            input_set_id=input_set_id,
            ordinal=index,
            retailer_id=retailer_id,
            adapter_id="historical_metricscart_search_monitor_csv",
            source_name=f"{retailer_id}.csv",
            source_format="metricscart_search_monitor_csv",
            storage_uri=f"s3://raw/{retailer_id}.csv",
            checksum=f"{index}" * 64,
            row_count=1,
        )
        for index, retailer_id in enumerate(retailer_ids, start=1)
    ]
    product_ids = {
        "walmart_us": "44391605",
        "aldi_us": "16383764",
        "amazon_us_same_day": "B000P6J0SM",
    }
    timestamps = {
        "walmart_us": "2026-08-07T05:03:04.869637",
        "aldi_us": "2026-08-07T05:04:05Z",
        "amazon_us_same_day": "1.786118963679E+12",
    }
    rows = {
        retailer_id: [
            {
                "Retailer Store Id": "0007" if retailer_id != "amazon_us_same_day" else "",
                "Zipcode": "00617",
                "Retailer Product Id": product_ids[retailer_id],
                "Product Name": "Fresh Strawberries, 1 lb",
                "Price": price,
                "Stock Availability": "true",
                "Date": timestamps[retailer_id],
            }
        ]
        for retailer_id, price in zip(retailer_ids, ("2.98", "2.49", "3.49"), strict=True)
    }
    result_repository = InMemoryResultsRepository()
    result_service = AnalysisResultService(
        result_repository,
        AnalysisResultValidator(REPOSITORY_ROOT),
        InMemoryReportObjectStore(),
    )
    dataset_store = InMemoryDatasetStore()
    artifact_recorder = ArtifactRecorder()
    processor = AnalysisProcessor(
        repository_root=REPOSITORY_ROOT,
        queue=HistoricalQueue(sources),  # type: ignore[arg-type]
        adapters=MetricsCartAdapterRegistry.from_catalog(
            REPOSITORY_ROOT / "config" / "retailer-catalog.json"
        ),
        raw_reader=RawReader({}),  # type: ignore[arg-type]
        historical_reader=HistoricalReader(rows),  # type: ignore[arg-type]
        dataset_writer=ParquetDatasetWriter(dataset_store),
        collections=artifact_recorder,  # type: ignore[arg-type]
        results=result_service,
        code_version="test-version",
    )
    job = AnalysisJob(
        id="00000000-0000-0000-0000-000000000705",
        collection_run_id=RUN_ID,
        input_set_id=input_set_id,
        source_kind="historical_import",
        product_pack_id="fresh_strawberries",
        product_pack_version="1.1.0",
        definition_config={
            "benchmark_retailer": "walmart_us",
            "retailers": [
                {"retailer_id": retailer_id, "enabled": True} for retailer_id in retailer_ids
            ],
            "analysis": {"comparison_profiles": ["strict"]},
            "delivery": {},
        },
        attempt_count=1,
        max_attempts=3,
    )

    analysis_id = await processor.process(job)

    analysis = await result_service.get_by_collection_run(RUN_ID)
    assert analysis.analysis_id == analysis_id
    assert analysis.result["source"]["kind"] == "historical_import"
    assert analysis.result["source"]["total_rows"] == 3
    assert analysis.result["source"]["observed_start"] == "2026-08-07T05:03:04.869637Z"
    assert analysis.result["source"]["observed_end"] == "2026-08-07T16:09:23.679000Z"
    assert analysis.result["source"]["source_artifact_ids"] == sorted(
        source.dataset_artifact_id for source in sources
    )
    assert analysis.result["comparisons"]


def test_analysis_orchestrator_has_no_product_category_branches() -> None:
    source = (REPOSITORY_ROOT / "apps/worker/src/rci_worker/analysis.py").read_text()
    assert "fresh_strawberries" not in source
    assert "fresh_shell_eggs" not in source
    assert "fresh_ground_beef" not in source


def test_brand_revision_adds_and_removes_private_label_without_mutating_pack() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_fluid_milk")
    rules = [
        SimpleNamespace(
            retailer_id="walmart_us",
            normalized_brand="hiland dairy",
            display_brand="Hiland Dairy",
            role="private_label",
            decision="confirmed",
        ),
        SimpleNamespace(
            retailer_id="walmart_us",
            normalized_brand="great value",
            display_brand="Great Value",
            role="private_label",
            decision="rejected",
        ),
    ]

    governed = apply_brand_classification_rules(pack, rules)  # type: ignore[arg-type]

    assert "Hiland Dairy" in governed.document["brand_rules"]["private_labels"]["walmart_us"]
    assert "Great Value" not in governed.document["brand_rules"]["private_labels"]["walmart_us"]
    assert "Hiland Dairy" not in pack.document["brand_rules"]["private_labels"]["walmart_us"]
    assert "Great Value" in pack.document["brand_rules"]["private_labels"]["walmart_us"]


async def test_historical_reader_yields_checksum_verified_bounded_batches() -> None:
    body = b"Retailer Product Id,Product Name,Price\n1,One,1.00\n2,Two,2.00\n3,Three,3.00\n"

    class Client:
        def get_object(self, **kwargs: object) -> dict[str, BytesIO]:
            assert kwargs == {"Bucket": "raw", "Key": "history.csv"}
            return {"Body": BytesIO(body)}

    source = HistoricalSource(
        dataset_artifact_id="artifact-1",
        input_set_id="input-1",
        ordinal=0,
        retailer_id="walmart_us",
        adapter_id="historical_metricscart_search_monitor_csv",
        source_name="history.csv",
        source_format="metricscart_search_monitor_csv",
        storage_uri="s3://raw/history.csv",
        checksum=hashlib.sha256(body).hexdigest(),
        row_count=3,
    )
    reader = S3HistoricalCSVReader(bucket="raw", client=Client())

    batches = [batch async for batch in reader.iter_batches(source, batch_size=2)]

    assert [len(batch) for batch in batches] == [2, 1]
    assert batches[1][0]["Retailer Product Id"] == "3"
