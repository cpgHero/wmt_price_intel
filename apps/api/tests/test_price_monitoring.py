from __future__ import annotations

from pathlib import Path
from types import MethodType

from httpx import ASGITransport, AsyncClient

from rci_analytics import PriceMonitoringFilters
from rci_api.main import create_app
from rci_api.price_monitoring import PriceMonitoringService, get_price_monitoring_service


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
