from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, Header, Request
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch

from rci_api.access import require_enabled_platform_admin, require_platform_admin
from rci_core import AppSettings


def _test_app(*, app_env: str = "production") -> FastAPI:
    app = FastAPI()
    app.state.settings = AppSettings(app_env=app_env)

    @app.get("/admin")
    async def admin(
        request: Request,
        x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
    ) -> dict[str, object]:
        principal = require_platform_admin(request, x_rci_admin_token)
        return {
            "user_id": principal.user_id,
            "is_system_actor": principal.is_system_actor,
            "permissions": sorted(principal.permissions),
        }

    @app.get("/feature-admin")
    async def feature_admin(
        request: Request,
        x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
    ) -> dict[str, str]:
        principal = require_enabled_platform_admin(
            request,
            x_rci_admin_token,
            enabled_flag_name="CPGHERO_TEST_FEATURE_ENABLED",
            default_enabled=not request.app.state.settings.is_production,
            disabled_detail="Feature is disabled.",
        )
        return {"user_id": principal.user_id}

    return app


async def test_platform_admin_requires_matching_token_in_production(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRODUCT_PACK_ADMIN_TOKEN", "private-admin-token")
    app = _test_app(app_env="production")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        missing = await client.get("/admin")
        invalid = await client.get("/admin", headers={"X-RCI-Admin-Token": "wrong-token"})
        valid = await client.get("/admin", headers={"X-RCI-Admin-Token": "private-admin-token"})

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert valid.status_code == 200
    assert valid.json() == {
        "user_id": "authenticated-platform-admin",
        "is_system_actor": True,
        "permissions": ["system.admin", "system.governance"],
    }


async def test_platform_admin_rejects_production_when_expected_token_is_unset(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.delenv("PRODUCT_PACK_ADMIN_TOKEN", raising=False)
    app = _test_app(app_env="production")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/admin", headers={"X-RCI-Admin-Token": "anything"})

    assert response.status_code == 401


async def test_platform_admin_allows_non_production_without_token(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.delenv("PRODUCT_PACK_ADMIN_TOKEN", raising=False)
    app = _test_app(app_env="development")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/admin")

    assert response.status_code == 200
    assert response.json()["is_system_actor"] is True


async def test_enabled_platform_admin_respects_feature_flag_before_token(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRODUCT_PACK_ADMIN_TOKEN", "private-admin-token")
    monkeypatch.setenv("CPGHERO_TEST_FEATURE_ENABLED", "false")
    app = _test_app(app_env="production")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/feature-admin",
            headers={"X-RCI-Admin-Token": "private-admin-token"},
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "Feature is disabled."}
