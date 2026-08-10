from __future__ import annotations

from pathlib import Path
from typing import Any

from httpx import ASGITransport, AsyncClient

import rci_api.main as api_main
from rci_api.main import create_app
from rci_api.product_packs import load_product_pack_catalog_versions
from rci_core import AppSettings

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


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


def test_deployable_product_pack_catalog_contains_valid_immutable_versions() -> None:
    versions = load_product_pack_catalog_versions(REPOSITORY_ROOT)

    assert {pack.id for pack in versions} == {
        "fresh_bananas",
        "fresh_fluid_milk",
        "fresh_ground_beef",
        "fresh_shell_eggs",
        "fresh_strawberries",
    }
    assert {pack.version for pack in versions} == {"1.0.0", "1.1.0"}
    assert next(pack for pack in versions if pack.id == "fresh_ground_beef").version == "1.0.0"
    assert all(pack.schema_version == "1.0.0" for pack in versions)
    assert all(len(pack.checksum) == 64 for pack in versions)


async def test_production_startup_publishes_product_pack_catalog(monkeypatch: Any) -> None:
    events: list[tuple[str, object]] = []

    class Probe:
        engine = object()

        async def dispose(self) -> None:
            events.append(("disposed", self.engine))

    probe = Probe()

    async def synchronize(engine: object, root: Path) -> int:
        events.append(("synchronized", engine))
        assert root == REPOSITORY_ROOT
        return 5

    monkeypatch.chdir(REPOSITORY_ROOT)
    monkeypatch.setattr(api_main, "DatabaseProbe", lambda _url: probe)
    monkeypatch.setattr(api_main, "synchronize_product_pack_catalog", synchronize)
    app = create_app(AppSettings(app_env="production"))

    async with app.router.lifespan_context(app):
        assert events == [("synchronized", probe.engine)]

    assert events == [
        ("synchronized", probe.engine),
        ("disposed", probe.engine),
    ]
