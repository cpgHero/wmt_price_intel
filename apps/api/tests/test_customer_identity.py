from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch

from rci_api.customer_auth import router as customer_auth_router
from rci_api.customer_identity import router as customer_identity_router
from rci_api.customer_principals import CustomerPrincipalResolution
from rci_api.workos_auth import (
    FLOW_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    WorkOSCustomerSessionAuthenticator,
    WorkOSLoginComplete,
    WorkOSLoginStart,
    WorkOSSessionIdentity,
)
from rci_core import AccessPrincipal, AppSettings


def _test_app(
    *,
    app_env: str = "development",
    provider: str = "disabled",
) -> FastAPI:
    app = FastAPI()
    app.state.settings = AppSettings(
        app_env=app_env,
        customer_identity_provider=provider,  # type: ignore[arg-type]
        workos_client_id="client_123",
        workos_redirect_uri="https://web-production-ee2a4.up.railway.app/api/auth/callback",
    )
    app.include_router(customer_auth_router)
    app.include_router(customer_identity_router)
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
        "provider": "cpghero",
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


class FakeCustomerSessionAuthenticator:
    def start_login(self, *, return_to: str) -> WorkOSLoginStart:
        return WorkOSLoginStart(
            authorization_url=f"https://auth.workos.test/authorize?return_to={return_to}",
            flow_cookie="sealed-flow",
        )

    def complete_login(
        self,
        *,
        code: str,
        state: str,
        flow_cookie: str,
        request: object,
    ) -> WorkOSLoginComplete:
        assert code == "code_123"
        assert state == "state_123"
        assert flow_cookie == "sealed-flow"
        return WorkOSLoginComplete(sealed_session="sealed-session", return_to="/reports")

    def authenticate_session_cookie(
        self,
        *,
        session_cookie: str | None,
        request: object,
    ) -> WorkOSSessionIdentity:
        if session_cookie != "sealed-session":
            raise AssertionError("expected sealed session cookie")
        return WorkOSSessionIdentity(
            workos_user_id="user_workos_123",
            email="buyer@example.com",
            workos_organization_id="org_workos_456",
            session_id="sess_789",
        )

    def get_logout_url(self, *, session_cookie: str | None, return_to: str | None) -> str | None:
        assert session_cookie == "sealed-session"
        return f"https://auth.workos.test/logout?return_to={return_to}"


class FakeCustomerPrincipalRepository:
    async def resolve_workos_identity(
        self,
        identity: WorkOSSessionIdentity,
    ) -> CustomerPrincipalResolution:
        assert identity.workos_user_id == "user_workos_123"
        return CustomerPrincipalResolution(
            principal=AccessPrincipal(
                user_id="00000000-0000-0000-0000-000000000301",
                email=identity.email,
                account_id="00000000-0000-0000-0000-000000000101",
                workspace_id="00000000-0000-0000-0000-000000000201",
                role_keys=frozenset({"account_admin", "analyst"}),
                entitlements=frozenset({"app_analytics", "analytics.proximity"}),
            ),
            source="workos_session",
            workos_session_id=identity.session_id,
            workos_organization_id=identity.workos_organization_id,
        )


class DummyWorkOSClient:
    pass


def _canary_authenticator(
    *,
    enabled: bool = True,
    allowed_emails: tuple[str, ...] = (),
    allowed_domains: tuple[str, ...] = (),
) -> WorkOSCustomerSessionAuthenticator:
    return WorkOSCustomerSessionAuthenticator(
        client=DummyWorkOSClient(),  # type: ignore[arg-type]
        redirect_uri="https://web-production-ee2a4.up.railway.app/api/auth/callback",
        cookie_password="unused-by-canary-unit-test",
        canary_enabled=enabled,
        allowed_emails=allowed_emails,
        allowed_domains=allowed_domains,
    )


def test_workos_canary_allows_approved_email_or_domain() -> None:
    by_email = _canary_authenticator(allowed_emails=("buyer@example.com",))
    by_domain = _canary_authenticator(allowed_domains=("cpghero.com",))

    by_email._assert_canary_user_allowed({"email": "Buyer@Example.com"})
    by_domain._assert_canary_user_allowed({"email": "owner@cpghero.com"})


def test_workos_canary_rejects_unapproved_or_unconfigured_users() -> None:
    with pytest.raises(HTTPException) as unconfigured:
        _canary_authenticator()._assert_canary_user_allowed({"email": "buyer@example.com"})
    with pytest.raises(HTTPException) as rejected:
        _canary_authenticator(
            allowed_emails=("owner@example.com",),
        )._assert_canary_user_allowed({"email": "buyer@example.com"})

    assert unconfigured.value.status_code == 503
    assert "no allowed users or domains" in unconfigured.value.detail
    assert rejected.value.status_code == 403
    assert "limited to approved users" in rejected.value.detail


async def test_customer_auth_login_sets_flow_cookie_and_redirects_to_workos() -> None:
    app = _test_app(provider="workos")
    app.state.customer_session_authenticator = FakeCustomerSessionAuthenticator()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/auth/login?return_to=/reports", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "https://auth.workos.test/authorize?return_to=/reports"
    assert FLOW_COOKIE_NAME in response.cookies


async def test_customer_auth_callback_sets_session_cookie_and_clears_flow_cookie() -> None:
    app = _test_app(provider="workos")
    app.state.customer_session_authenticator = FakeCustomerSessionAuthenticator()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set(FLOW_COOKIE_NAME, "sealed-flow")
        response = await client.get(
            "/api/auth/callback?code=code_123&state=state_123",
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == "/reports"
    assert response.cookies[SESSION_COOKIE_NAME] == "sealed-session"
    assert f"{FLOW_COOKIE_NAME}=" in response.headers["set-cookie"]


async def test_customer_me_resolves_workos_session_through_cpg_principal_repository() -> None:
    app = _test_app(provider="workos", app_env="production")
    app.state.customer_session_authenticator = FakeCustomerSessionAuthenticator()
    app.state.customer_principal_repository = FakeCustomerPrincipalRepository()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set(SESSION_COOKIE_NAME, "sealed-session")
        response = await client.get("/api/v1/me")

    assert response.status_code == 200
    assert response.json() == {
        "schema_version": "1.0.0-customer-principal",
        "auth": {
            "provider": "cpghero",
            "source": "customer_session",
        },
        "principal": {
            "user_id": "00000000-0000-0000-0000-000000000301",
            "email": "buyer@example.com",
            "account_id": "00000000-0000-0000-0000-000000000101",
            "workspace_id": "00000000-0000-0000-0000-000000000201",
            "roles": ["account_admin", "analyst"],
            "permissions": [
                "analytics.share",
                "analytics.view",
                "api_keys.manage",
                "exports.download",
                "projects.approve_paid_run",
                "projects.create",
                "projects.manage",
                "users.manage",
            ],
            "entitlements": ["analytics.proximity", "app_analytics"],
            "is_system_actor": False,
        },
    }


async def test_customer_auth_logout_clears_customer_session_cookie() -> None:
    app = _test_app(provider="workos")
    app.state.customer_session_authenticator = FakeCustomerSessionAuthenticator()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set(SESSION_COOKIE_NAME, "sealed-session")
        response = await client.get("/api/auth/logout?return_to=/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "https://auth.workos.test/logout?return_to=/"
    assert f"{SESSION_COOKIE_NAME}=" in response.headers["set-cookie"]
