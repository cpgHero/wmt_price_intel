from __future__ import annotations

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch

from rci_api.customer_identity import router
from rci_core import AppSettings


def _test_app(*, app_env: str = "development") -> FastAPI:
    app = FastAPI()
    app.state.settings = AppSettings(
        app_env=app_env,
        customer_identity_provider="workos",
        workos_client_id="client_123",
        workos_redirect_uri="https://web-production-ee2a4.up.railway.app/api/auth/callback",
    )
    app.include_router(router)
    return app


def _headers(**overrides: str) -> dict[str, str]:
    headers = {
        "X-CPGHero-Test-User-Id": "user_123",
        "X-CPGHero-Test-Email": "analyst@example.com",
        "X-CPGHero-Test-Account-Id": "account_abc",
        "X-CPGHero-Test-Workspace-Id": "workspace_xyz",
        "X-CPGHero-Test-Roles": "analyst, viewer",
        "X-CPGHero-Test-Entitlements": "app_analytics, analytics.price_intelligence",
    }
    headers.update(overrides)
    return headers


async def test_customer_me_requires_explicit_non_production_harness(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.delenv("CPGHERO_CUSTOMER_AUTH_TEST_HARNESS_ENABLED", raising=False)
    app = _test_app(app_env="development")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/me", headers=_headers())

    assert response.status_code == 401
    assert response.json() == {"detail": "Customer authentication test harness is disabled."}


async def test_customer_me_resolves_valid_non_production_principal(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("CPGHERO_CUSTOMER_AUTH_TEST_HARNESS_ENABLED", "true")
    app = _test_app(app_env="development")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/me", headers=_headers())

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "1.0.0-customer-principal"
    assert body["auth"] == {
        "provider": "workos",
        "source": "non_production_test_harness",
    }
    assert body["principal"] == {
        "user_id": "user_123",
        "email": "analyst@example.com",
        "account_id": "account_abc",
        "workspace_id": "workspace_xyz",
        "roles": ["analyst", "viewer"],
        "permissions": ["analytics.share", "analytics.view", "exports.download"],
        "entitlements": ["analytics.price_intelligence", "app_analytics"],
        "is_system_actor": False,
    }


async def test_customer_me_rejects_production_test_headers(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("CPGHERO_CUSTOMER_AUTH_TEST_HARNESS_ENABLED", "true")
    app = _test_app(app_env="production")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/me", headers=_headers())

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Customer authentication is not enabled in production yet."
    }


async def test_customer_me_rejects_unknown_role_and_entitlement_keys(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("CPGHERO_CUSTOMER_AUTH_TEST_HARNESS_ENABLED", "true")
    app = _test_app(app_env="development")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        role_response = await client.get(
            "/api/v1/me",
            headers=_headers(**{"X-CPGHero-Test-Roles": "viewer, super_user"}),
        )
        entitlement_response = await client.get(
            "/api/v1/me",
            headers=_headers(**{"X-CPGHero-Test-Entitlements": "app_analytics, secret_feed"}),
        )

    assert role_response.status_code == 400
    assert role_response.json() == {"detail": "Unknown customer role keys: super_user"}
    assert entitlement_response.status_code == 400
    assert entitlement_response.json() == {
        "detail": "Unknown customer entitlement keys: secret_feed"
    }


async def test_customer_me_does_not_serialize_workos_secrets(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("CPGHERO_CUSTOMER_AUTH_TEST_HARNESS_ENABLED", "true")
    monkeypatch.setenv("WORKOS_API_KEY", "sk_test_must_not_appear")
    monkeypatch.setenv("WORKOS_COOKIE_PASSWORD", "cookie_secret_must_not_appear")
    app = _test_app(app_env="development")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/me", headers=_headers())

    serialized = str(response.json())
    assert "sk_test_must_not_appear" not in serialized
    assert "cookie_secret_must_not_appear" not in serialized
