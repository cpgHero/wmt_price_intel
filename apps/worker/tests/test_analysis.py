from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from rci_analytics import InMemoryDatasetStore, ParquetDatasetWriter
from rci_collections.models import QueueTask, RawArtifact
from rci_providers import MetricsCartAdapterRegistry
from rci_results import (
    AnalysisResultService,
    AnalysisResultValidator,
    InMemoryReportObjectStore,
    InMemoryResultsRepository,
)
from rci_worker.analysis import AnalysisJob, AnalysisProcessor, CollectedPage

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


class RawReader:
    def __init__(self, payloads: dict[str, object]) -> None:
        self._payloads = payloads

    async def read(self, page: CollectedPage) -> object:
        return self._payloads[page.task.id]


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
                latitude=None,
                longitude=None,
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
        product_pack_id="fresh_strawberries",
        product_pack_version="1.0.0",
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
    assert analysis.result["source_summary"]["normalized_offers"] == 3
    assert {row["retailer_id"] for row in analysis.result["coverage"]} == {
        "walmart_us",
        "aldi_us",
        "amazon_us_same_day",
    }
    assert analysis.result["comparisons"]
    assert len(artifact_recorder.artifacts) >= 7
    assert all(uri.endswith(".parquet") for uri in dataset_store.objects)


def test_analysis_orchestrator_has_no_product_category_branches() -> None:
    source = (REPOSITORY_ROOT / "apps/worker/src/rci_worker/analysis.py").read_text()
    assert "fresh_strawberries" not in source
    assert "fresh_shell_eggs" not in source
