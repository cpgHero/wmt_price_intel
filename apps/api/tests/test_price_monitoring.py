from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import time
from contextlib import suppress
from io import BytesIO
from pathlib import Path
from types import MethodType, SimpleNamespace

import polars as pl
import pytest
from httpx import ASGITransport, AsyncClient

from rci_analytics import PriceMonitoringFilters, ProductPackLoader
from rci_api.main import create_app
from rci_api.price_monitoring import (
    ClassifiedArtifact,
    PriceMonitoringService,
    S3ParquetReader,
    get_price_monitoring_service,
    select_evidence_artifacts,
)


async def test_materialized_catalog_is_filtered_sorted_and_paged() -> None:
    class Repository:
        async def catalog_materialization(
            self, analysis_id: str, retailer_id: str
        ) -> dict[str, object]:
            assert (analysis_id, retailer_id) == ("analysis-1", "walmart_us")
            return {
                "analysis_id": analysis_id,
                "products": [
                    {
                        "product_id": "2",
                        "name": "Nature Made Adult Multivitamin",
                        "brand": "Nature Made",
                        "brand_type": "national",
                        "seller": "Walmart.com",
                        "presence": {"observed_locations": 12},
                    },
                    {
                        "product_id": "1",
                        "name": "Spring Valley Adult Multivitamin",
                        "brand": "Spring Valley",
                        "brand_type": "private_label",
                        "seller": "Walmart.com",
                        "presence": {"observed_locations": 41},
                    },
                    {
                        "product_id": "3",
                        "name": "Spring Valley Vitamin C",
                        "brand": "Spring Valley",
                        "brand_type": "private_label",
                        "seller": None,
                        "presence": {"observed_locations": 30},
                    },
                ],
            }

    service = object.__new__(PriceMonitoringService)
    service._repository = Repository()
    page = await service.catalog_page(
        "analysis-1",
        "walmart_us",
        query="spring valley",
        brand_type="private_label",
        seller="Walmart.com",
        offset=0,
        limit=1,
    )

    assert page["pagination"] == {
        "offset": 0,
        "limit": 1,
        "returned": 1,
        "filtered_total": 1,
        "total": 3,
        "has_more": False,
    }
    assert [row["product_id"] for row in page["view"]["products"]] == ["1"]
    assert page["facets"]["brands"] == ["Nature Made", "Spring Valley"]
    assert page["facets"]["sellers"] == ["Walmart.com"]


async def test_large_price_projection_does_not_block_api_event_loop(monkeypatch: object) -> None:
    service = object.__new__(PriceMonitoringService)
    service._view_cache = {}
    service._view_tasks = {}
    service._root = Path(__file__).resolve().parents[3]
    prepared = SimpleNamespace(
        analysis=SimpleNamespace(analysis_id="analysis-1"),
        product_context_revision="revision-1",
    )
    started = threading.Event()
    release = threading.Event()
    project_calls = 0

    async def prepare(
        _service: PriceMonitoringService,
        _analysis_id: str,
        _retailer_id: str,
    ) -> object:
        return prepared

    def project(
        _service: PriceMonitoringService,
        _prepared: object,
        _filters: PriceMonitoringFilters,
        **_limits: object,
    ) -> dict[str, object]:
        nonlocal project_calls
        project_calls += 1
        started.set()
        assert release.wait(timeout=2)
        return {"schema_version": "test"}

    monkeypatch.setattr("rci_api.price_monitoring.validate_instance", lambda *_args, **_kw: None)  # type: ignore[union-attr]
    service._prepare = MethodType(prepare, service)  # type: ignore[method-assign]
    service._project = MethodType(project, service)  # type: ignore[method-assign]

    view_task = asyncio.create_task(
        service.view("analysis-1", PriceMonitoringFilters(retailer_id="walmart_us"))
    )
    deadline = time.monotonic() + 1
    while not started.is_set() and time.monotonic() < deadline:
        await asyncio.sleep(0.005)
    assert started.is_set()

    heartbeat_started = time.monotonic()
    await asyncio.sleep(0.02)
    assert time.monotonic() - heartbeat_started < 0.2

    # A timed-out HTTP request must not abandon the expensive build or cause a
    # later request to start the same projection again.
    view_task.cancel()
    with suppress(asyncio.CancelledError):
        await view_task
    joined_task = asyncio.create_task(
        service.view("analysis-1", PriceMonitoringFilters(retailer_id="walmart_us"))
    )
    await asyncio.sleep(0.02)
    assert project_calls == 1

    release.set()
    assert await joined_task == {"schema_version": "test"}
    assert service._view_cache


def _artifact(artifact_id: str, partition: int, rows: int, created_at: str) -> ClassifiedArtifact:
    return ClassifiedArtifact(
        id=artifact_id,
        storage_uri=f"s3://artifacts/{artifact_id}.parquet",
        checksum=hashlib.sha256(artifact_id.encode()).hexdigest(),
        row_count=rows,
        partition=partition,
        created_at=created_at,
    )


def _evidence(artifacts: list[ClassifiedArtifact]) -> dict[str, object]:
    manifest = sorted((row.id, row.checksum, row.row_count) for row in artifacts)
    checksum = hashlib.sha256(
        json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    return {"checksum_sha256": checksum, "row_count": sum(row.row_count for row in artifacts)}


def test_classified_artifacts_are_bound_to_the_published_evidence_generation() -> None:
    first = [
        _artifact("first-0", 0, 10, "2026-08-17T00:00:00Z"),
        _artifact("first-1", 1, 12, "2026-08-17T00:00:00Z"),
    ]
    governed = [
        _artifact("governed-0", 0, 9, "2026-08-18T00:00:00Z"),
        _artifact("governed-1", 1, 11, "2026-08-18T00:00:00Z"),
    ]

    selected = select_evidence_artifacts([*first, *governed], _evidence(governed))

    assert [row.id for row in selected] == ["governed-0", "governed-1"]


def test_ambiguous_artifact_generations_fail_closed_without_an_evidence_manifest() -> None:
    with pytest.raises(RuntimeError, match="multiple generations"):
        select_evidence_artifacts(
            [
                _artifact("first", 0, 10, "2026-08-17T00:00:00Z"),
                _artifact("second", 0, 10, "2026-08-18T00:00:00Z"),
            ],
            None,
        )


async def test_parquet_reader_projects_governed_columns_and_inserts_optional_columns() -> None:
    buffer = BytesIO()
    pl.DataFrame(
        {
            "offer_id": ["offer-1", "offer-2"],
            "retailer_id": ["walmart_us", "walmart_us"],
            "retailer_product_id": ["000123", "999"],
            "title": ["Product 123", "Product 999"],
            "price": [4.99, 8.99],
            "unused_payload": [
                "must not be decoded into the read model",
                "must not be decoded into the read model",
            ],
        }
    ).write_parquet(buffer)
    payload = buffer.getvalue()

    class Body:
        def read(self) -> bytes:
            return payload

    class Client:
        def __init__(self) -> None:
            self.calls = 0

        def get_object(self, **_kwargs: object) -> dict[str, object]:
            self.calls += 1
            return {"Body": Body()}

    client = Client()
    reader = S3ParquetReader(bucket="artifacts", client=client)
    artifact = ClassifiedArtifact(
        storage_uri="s3://artifacts/classified.parquet",
        checksum=hashlib.sha256(payload).hexdigest(),
        row_count=2,
    )
    rows = await reader.read(artifact)
    selected = await reader.read_products(
        artifact,
        retailer_id="walmart_us",
        product_ids=["000123"],
    )

    assert rows[0]["offer_id"] == "offer-1"
    assert "metrics_json" not in rows[0]
    assert "unused_payload" not in rows[0]
    assert [row["retailer_product_id"] for row in selected] == ["000123"]
    assert client.calls == 1


async def test_product_observation_batch_reads_only_requested_products_once() -> None:
    historical_artifact = _artifact("historical", 0, 2, "2026-08-16T00:00:00Z")
    governed_artifact = _artifact("governed", 0, 2, "2026-08-17T00:00:00Z")

    class Analyses:
        async def get(self, analysis_id: str) -> object:
            assert analysis_id == "analysis-1"
            return SimpleNamespace(
                analysis_id="analysis-1",
                collection_run_id="run-1",
                product_pack_id="fresh_ground_beef",
                product_pack_version="1.0.0",
                result={
                    "benchmark_retailer": "walmart_us",
                    "competitors": ["aldi_us"],
                    "evidence_sets": [
                        {
                            "evidence_set_id": "evidence.classified.aldi_us",
                            **_evidence([governed_artifact]),
                        }
                    ],
                },
            )

    class Repository:
        async def artifacts(self, collection_run_id: str, retailer_id: str) -> list[object]:
            assert (collection_run_id, retailer_id) == ("run-1", "aldi_us")
            return [historical_artifact, governed_artifact]

        async def location_context(
            self, collection_run_id: str, retailer_id: str
        ) -> tuple[dict[tuple[str, str], dict[str, object]], dict[object, object], int]:
            assert (collection_run_id, retailer_id) == ("run-1", "aldi_us")
            return (
                {
                    ("aldi_us", "1"): {
                        "store_name": "ALDI One",
                        "zipcode": "72712",
                        "city": "Bentonville",
                        "state": "AR",
                        "country": "USA",
                        "latitude": 36.37,
                        "longitude": -94.21,
                    },
                    ("aldi_us", "2"): {
                        "store_name": "ALDI Two",
                        "zipcode": "72756",
                        "city": "Rogers",
                        "state": "AR",
                        "country": "USA",
                        "latitude": 36.33,
                        "longitude": -94.12,
                    },
                },
                {},
                2,
            )

        async def product_context(
            self, retailer_id: str, product_ids: list[str]
        ) -> dict[str, dict[str, object]]:
            assert retailer_id == "aldi_us"
            assert product_ids == ["a-1", "a-2"]
            return {
                "aldi_us:a-1": {
                    "name": "ALDI Product One",
                    "brand": "ALDI",
                    "image_url": "https://example.com/aldi-one.jpg",
                },
                "aldi_us:a-2": {"name": "ALDI Product Two"},
            }

        async def brand_overrides(self, **_kwargs: object) -> list[object]:
            return []

    class PackLoader:
        async def load(self, product_pack_id: str, version: str) -> object:
            assert (product_pack_id, version) == ("fresh_ground_beef", "1.0.0")
            return ProductPackLoader(Path(__file__).resolve().parents[3]).load(product_pack_id)

    class Reader:
        def __init__(self) -> None:
            self.calls = 0

        async def read_products(
            self,
            artifact: object,
            *,
            retailer_id: str,
            product_ids: list[str],
        ) -> list[dict[str, object]]:
            assert artifact == governed_artifact
            assert retailer_id == "aldi_us"
            assert product_ids == ["a-1", "a-2"]
            self.calls += 1
            return [
                {
                    "offer_id": f"offer-{index}",
                    "retailer_id": "aldi_us",
                    "retailer_product_id": product_id,
                    "title": f"Search {product_id}",
                    "price": price,
                    "currency": "USD",
                    "zipcode": zipcode,
                    "store_number": str(index),
                    "in_scope": True,
                    "metrics_json": "{}",
                    "collected_at": "2026-08-07T06:00:00Z",
                }
                for index, (product_id, zipcode, price) in enumerate(
                    (("a-1", "72712", 3.99), ("a-2", "72756", 4.99)),
                    start=1,
                )
            ]

    reader = Reader()
    service = PriceMonitoringService(
        repository_root=Path(__file__).resolve().parents[3],
        analysis_service=Analyses(),  # type: ignore[arg-type]
        repository=Repository(),  # type: ignore[arg-type]
        product_pack_loader=PackLoader(),  # type: ignore[arg-type]
        reader=reader,  # type: ignore[arg-type]
    )
    first = await service.product_observations_for_products(
        "analysis-1",
        retailer_id="aldi_us",
        product_ids=["a-2", "a-1"],
        comparison_metric="package_price",
    )
    second = await service.product_observations_for_products(
        "analysis-1",
        retailer_id="aldi_us",
        product_ids=["a-1", "a-2"],
        comparison_metric="package_price",
    )
    subset = await service.product_observations_for_products(
        "analysis-1",
        retailer_id="aldi_us",
        product_ids=["a-1"],
        comparison_metric="package_price",
    )

    assert {product_id: len(rows) for product_id, rows in first.items()} == {
        "a-1": 1,
        "a-2": 1,
    }
    assert first == second
    assert list(subset) == ["a-1"]
    assert subset["a-1"] == first["a-1"]
    assert first["a-1"][0].product_name == "ALDI Product One"
    assert first["a-1"][0].brand == "ALDI"
    assert first["a-1"][0].image_url == "https://example.com/aldi-one.jpg"
    assert reader.calls == 1


async def test_price_monitoring_api_passes_governed_filters() -> None:
    class PriceService:
        async def catalog_document(
            self, analysis_id: str, retailer_id: str
        ) -> dict[str, object] | None:
            raise AssertionError("filtered views must not use the default catalog shortcut")

        async def view(self, analysis_id: str, filters: object) -> dict[str, object]:
            assert analysis_id == "analysis-1"
            assert filters.retailer_id == "walmart_us"
            assert filters.brand_type == "private_label"
            assert filters.state == "AR"
            assert filters.city == "Bentonville"
            assert filters.zipcode == "72712"
            assert filters.product_id == "123"
            return {"analysis_id": analysis_id, "retailer": filters.retailer_id}

    app = create_app()
    app.dependency_overrides[get_price_monitoring_service] = lambda: PriceService()
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        response = await client.get(
            "/api/v1/analyses/analysis-1/price-monitoring",
            params={
                "retailer": "walmart_us",
                "brand_type": "private_label",
                "state": "AR",
                "city": "Bentonville",
                "zipcode": "72712",
                "product_id": "123",
            },
        )

    assert response.status_code == 200
    assert response.json() == {"analysis_id": "analysis-1", "retailer": "walmart_us"}


async def test_default_price_monitoring_api_uses_publication_catalog() -> None:
    class PriceService:
        async def catalog_document(
            self, analysis_id: str, retailer_id: str
        ) -> dict[str, object] | None:
            assert (analysis_id, retailer_id) == ("analysis-1", "walmart_us")
            return {
                "schema_version": "1.0.0",
                "analysis_id": analysis_id,
                "products": [{"product_id": "123"}],
            }

        async def view(self, _analysis_id: str, _filters: object) -> dict[str, object]:
            raise AssertionError("the default view must not rebuild classified Search evidence")

    app = create_app()
    app.dependency_overrides[get_price_monitoring_service] = lambda: PriceService()
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        response = await client.get(
            "/api/v1/analyses/analysis-1/price-monitoring",
            params={"retailer": "walmart_us"},
        )

    assert response.status_code == 200
    assert response.json()["products"] == [{"product_id": "123"}]


async def test_default_price_monitoring_api_falls_back_when_catalog_is_absent() -> None:
    class PriceService:
        async def catalog_document(
            self, analysis_id: str, retailer_id: str
        ) -> dict[str, object] | None:
            assert (analysis_id, retailer_id) == ("analysis-1", "walmart_us")
            return None

        async def view(self, analysis_id: str, filters: object) -> dict[str, object]:
            assert analysis_id == "analysis-1"
            assert filters.retailer_id == "walmart_us"
            return {"analysis_id": analysis_id, "source": "live-fallback"}

    app = create_app()
    app.dependency_overrides[get_price_monitoring_service] = lambda: PriceService()
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        response = await client.get(
            "/api/v1/analyses/analysis-1/price-monitoring",
            params={"retailer": "walmart_us"},
        )

    assert response.status_code == 200
    assert response.json() == {"analysis_id": "analysis-1", "source": "live-fallback"}


async def test_price_monitoring_api_rejects_unknown_brand_filter() -> None:
    app = create_app()
    app.dependency_overrides[get_price_monitoring_service] = lambda: object()
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        response = await client.get(
            "/api/v1/analyses/analysis-1/price-monitoring",
            params={"retailer": "walmart_us", "brand_type": "invented"},
        )

    assert response.status_code == 422


async def test_price_architecture_api_passes_governed_scope_and_rung_method() -> None:
    class PriceService:
        async def architecture_matrix(
            self, analysis_id: str, **filters: object
        ) -> dict[str, object]:
            assert analysis_id == "analysis-1"
            assert filters == {
                "mode": "fixed_range",
                "fixed_increment": 1.0,
                "brand_type": "private_label",
                "brand": "Great Value",
                "state": "AR",
                "city": "Bentonville",
                "zipcode": "72712",
            }
            return {"analysis_id": analysis_id, "mode": filters["mode"]}

    app = create_app()
    app.dependency_overrides[get_price_monitoring_service] = lambda: PriceService()
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        response = await client.get(
            "/api/v1/analyses/analysis-1/price-architecture-matrix",
            params={
                "mode": "fixed_range",
                "fixed_increment": "1",
                "brand_type": "private_label",
                "brand": "Great Value",
                "state": "AR",
                "city": "Bentonville",
                "zipcode": "72712",
            },
        )

    assert response.status_code == 200
    assert response.json() == {"analysis_id": "analysis-1", "mode": "fixed_range"}


async def test_price_architecture_materialization_requires_internal_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class PriceService:
        async def pre_materialize_architecture_matrices(
            self, analysis_id: str, *, refresh: bool
        ) -> list[dict[str, object]]:
            raise AssertionError("unauthenticated requests must not start materialization")

    monkeypatch.setenv("RCI_INTERNAL_SERVICE_TOKEN", "test-internal-token")
    app = create_app()
    app.dependency_overrides[get_price_monitoring_service] = lambda: PriceService()
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        response = await client.post(
            "/api/v1/internal/analyses/analysis-1/price-architecture-matrix/materialize"
        )

    assert response.status_code == 401


async def test_price_architecture_materialization_builds_default_read_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class PriceService:
        async def pre_materialize_architecture_matrices(
            self, analysis_id: str, *, refresh: bool
        ) -> list[dict[str, object]]:
            assert analysis_id == "analysis-1"
            assert refresh is True
            return [{"mode": "benchmark_anchored"}, {"increment": 0.5}, {"increment": 1.0}]

    monkeypatch.setenv("RCI_INTERNAL_SERVICE_TOKEN", "test-internal-token")
    app = create_app()
    app.dependency_overrides[get_price_monitoring_service] = lambda: PriceService()
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        response = await client.post(
            "/api/v1/internal/analyses/analysis-1/price-architecture-matrix/materialize",
            headers={"X-RCI-Internal-Token": "test-internal-token"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "analysis_id": "analysis-1",
        "status": "materialized",
        "matrix_count": 3,
        "provider_calls_queued": 0,
    }


async def test_price_monitoring_map_passes_exact_product_and_detail_scope() -> None:
    class PriceService:
        async def map_view(
            self,
            analysis_id: str,
            filters: object,
            *,
            detail: str,
        ) -> dict[str, object]:
            assert analysis_id == "analysis-1"
            assert filters.retailer_id == "walmart_us"
            assert filters.product_id == "123"
            assert filters.state == "AR"
            assert detail == "summary"
            return {"analysis_id": analysis_id, "detail": detail}

    app = create_app()
    app.dependency_overrides[get_price_monitoring_service] = lambda: PriceService()
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        response = await client.get(
            "/api/v1/analyses/analysis-1/price-monitoring/map",
            params={
                "retailer": "walmart_us",
                "product_id": "123",
                "state": "AR",
                "detail": "summary",
            },
        )

    assert response.status_code == 200
    assert response.json() == {"analysis_id": "analysis-1", "detail": "summary"}


async def test_price_monitoring_map_projects_observed_and_not_observed_store_points() -> None:
    service = object.__new__(PriceMonitoringService)
    service._map_cache = {}
    service._root = Path(__file__).resolve().parents[3]

    async def prepare(
        _service: PriceMonitoringService,
        analysis_id: str,
        retailer_id: str,
    ) -> object:
        assert analysis_id == "analysis-1"
        assert retailer_id == "walmart_us"
        return object()

    def project(
        _service: PriceMonitoringService,
        prepared: object,
        filters: PriceMonitoringFilters,
        **limits: object,
    ) -> dict[str, object]:
        assert prepared is not None
        assert filters.product_id == "123"
        assert limits == {"location_limit": None, "product_location_limit": 0}
        return {
            "retailer": {"id": "walmart_us", "name": "Walmart (US)"},
            "products": [
                {
                    "product_id": "123",
                    "name": "Product 123",
                    "price_stats": {"observation_median": 5.0},
                }
            ],
            "location_display": {"total": 2},
            "locations": [
                {
                    "scope_key": "store:1",
                    "kind": "store",
                    "store_number": "1",
                    "store_name": "Store One",
                    "zipcode": "72712",
                    "city": "Bentonville",
                    "state": "AR",
                    "country": "USA",
                    "latitude": 36.37,
                    "longitude": -94.21,
                    "median_price": 4.5,
                },
                {
                    "scope_key": "store:2",
                    "kind": "store",
                    "store_number": "2",
                    "store_name": "Store Two",
                    "zipcode": "72756",
                    "city": "Rogers",
                    "state": "AR",
                    "country": "USA",
                    "latitude": None,
                    "longitude": None,
                    "median_price": 5.5,
                },
            ],
            "distribution_gaps": {
                "location_display": {"total": 1},
                "locations": [
                    {
                        "scope_key": "store:3",
                        "kind": "store",
                        "store_number": "3",
                        "store_name": "Store Three",
                        "zipcode": "72764",
                        "city": "Springdale",
                        "state": "AR",
                        "country": "USA",
                        "latitude": 36.18,
                        "longitude": -94.13,
                    }
                ],
            },
        }

    service._prepare = MethodType(prepare, service)  # type: ignore[method-assign]
    service._project = MethodType(project, service)  # type: ignore[method-assign]
    result = await service.map_view(
        "analysis-1",
        PriceMonitoringFilters(retailer_id="walmart_us", product_id="123"),
    )

    assert result["reference_price"] == 5.0
    assert result["display"] == {
        "observed_locations": 2,
        "observed_points": 1,
        "observed_missing_coordinates": 1,
        "observed_sampled": False,
        "below_reference_locations": 1,
        "at_reference_locations": 0,
        "above_reference_locations": 1,
        "not_observed_locations": 1,
        "not_observed_points": 1,
        "not_observed_missing_coordinates": 0,
        "not_observed_sampled": False,
    }
    assert result["points"][0]["status"] == "observed"
    assert result["points"][0]["difference_from_reference"] == -0.5
    assert result["points"][1]["status"] == "not_observed"
    assert result["points"][1]["price"] is None


async def test_price_monitoring_evidence_export_passes_exact_product_scope() -> None:
    class PriceService:
        async def evidence_csv(self, analysis_id: str, filters: object) -> str:
            assert analysis_id == "analysis-1"
            assert filters.retailer_id == "walmart_us"
            assert filters.product_id == "123"
            assert filters.state == "AR"
            assert filters.city == "Bentonville"
            assert filters.zipcode == "72712"
            return "retailer,product_id\nWalmart,123\n"

    app = create_app()
    app.dependency_overrides[get_price_monitoring_service] = lambda: PriceService()
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        response = await client.get(
            "/api/v1/analyses/analysis-1/price-monitoring/evidence.csv",
            params={
                "retailer": "walmart_us",
                "product_id": "123",
                "state": "AR",
                "city": "Bentonville",
                "zipcode": "72712",
            },
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.text.endswith("Walmart,123\n")
