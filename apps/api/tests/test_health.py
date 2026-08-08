from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from rci_api.main import create_app
from rci_core import AppSettings


class FakeProbe:
    def __init__(self, ready: bool) -> None:
        self.ready = ready

    async def is_ready(self) -> bool:
        return self.ready

    async def dispose(self) -> None:
        return None


async def test_liveness_and_version() -> None:
    app = create_app(AppSettings(app_version="1.2.3"))
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        response = await client.get("/health/live")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "service": "api", "version": "1.2.3"}
        assert (await client.get("/api/v1/version")).json() == {"version": "1.2.3"}


async def test_readiness_reports_postgres_state() -> None:
    app = create_app()
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        app.state.database_probe = FakeProbe(ready=False)
        response = await client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["dependencies"] == {"postgres": "unavailable"}

        app.state.database_probe = FakeProbe(ready=True)
        response = await client.get("/health/ready")
        assert response.status_code == 200
        assert response.json()["status"] == "ready"
