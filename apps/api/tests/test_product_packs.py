from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from rci_api.main import create_app


async def test_product_pack_catalog_is_configuration_driven() -> None:
    app = create_app()
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        response = await client.get("/api/v1/product-packs")

    assert response.status_code == 200
    document = response.json()
    assert document["default_pack_id"] == "fresh_strawberries"
    assert {pack["id"] for pack in document["packs"]} >= {
        "fresh_strawberries",
        "fresh_shell_eggs",
    }
