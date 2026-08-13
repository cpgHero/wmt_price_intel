from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from rci_api.main import create_app
from rci_api.price_monitoring import get_price_monitoring_service


async def test_price_monitoring_api_passes_governed_filters() -> None:
    class PriceService:
        async def view(self, analysis_id: str, filters: object) -> dict[str, object]:
            assert analysis_id == "analysis-1"
            assert filters.retailer_id == "walmart_us"
            assert filters.brand_type == "private_label"
            assert filters.state == "AR"
            assert filters.city == "Bentonville"
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
