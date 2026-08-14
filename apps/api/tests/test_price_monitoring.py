from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path
from types import MethodType, SimpleNamespace

import polars as pl
from httpx import ASGITransport, AsyncClient

from rci_analytics import PriceMonitoringFilters
from rci_api.main import create_app
from rci_api.price_monitoring import (
    ClassifiedArtifact,
    PriceMonitoringService,
    S3ParquetReader,
    get_price_monitoring_service,
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
    class Analyses:
        async def get(self, analysis_id: str) -> object:
            assert analysis_id == "analysis-1"
            return SimpleNamespace(
                collection_run_id="run-1",
                result={
                    "benchmark_retailer": "walmart_us",
                    "competitors": ["aldi_us"],
                },
            )

    class Repository:
        async def artifacts(self, collection_run_id: str, retailer_id: str) -> list[object]:
            assert (collection_run_id, retailer_id) == ("run-1", "aldi_us")
            return [
                ClassifiedArtifact(
                    storage_uri="s3://artifacts/aldi.parquet",
                    checksum="a" * 64,
                    row_count=2,
                )
            ]

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
                "aldi_us:a-1": {"name": "ALDI Product One"},
                "aldi_us:a-2": {"name": "ALDI Product Two"},
            }

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
            assert artifact is not None
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
        product_pack_loader=object(),  # type: ignore[arg-type]
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

    assert {product_id: len(rows) for product_id, rows in first.items()} == {
        "a-1": 1,
        "a-2": 1,
    }
    assert first == second
    assert first["a-1"][0].product_name == "ALDI Product One"
    assert reader.calls == 1


async def test_price_monitoring_api_passes_governed_filters() -> None:
    class PriceService:
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
