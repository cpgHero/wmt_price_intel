from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, status
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch

from rci_api.customer_identity import router as customer_identity_router
from rci_api.customer_principals import CustomerPrincipalResolution
from rci_api.customer_reports import CustomerReportSummary
from rci_api.customer_reports import router as customer_report_router
from rci_api.workos_auth import SESSION_COOKIE_NAME, WorkOSSessionIdentity
from rci_core import AccessPrincipal, AppSettings


class FakeCustomerSessionAuthenticator:
    def authenticate_session_cookie(
        self,
        *,
        session_cookie: str | None,
        request: object,
    ) -> WorkOSSessionIdentity:
        if session_cookie != "sealed-session":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Customer authentication is required.",
            )
        return WorkOSSessionIdentity(
            workos_user_id="user_workos_123",
            email="buyer@example.com",
            workos_organization_id="org_workos_456",
            session_id="sess_789",
        )


class FakeCustomerPrincipalRepository:
    def __init__(
        self,
        *,
        account_id: str | None = "00000000-0000-0000-0000-000000000101",
        workspace_id: str | None = "00000000-0000-0000-0000-000000000201",
        role_keys: frozenset[str] = frozenset({"analyst"}),
        entitlements: frozenset[str] = frozenset({"app_analytics"}),
    ) -> None:
        self.account_id = account_id
        self.workspace_id = workspace_id
        self.role_keys = role_keys
        self.entitlements = entitlements

    async def resolve_workos_identity(
        self,
        identity: WorkOSSessionIdentity,
    ) -> CustomerPrincipalResolution:
        return CustomerPrincipalResolution(
            principal=AccessPrincipal(
                user_id="00000000-0000-0000-0000-000000000301",
                email=identity.email,
                account_id=self.account_id,
                workspace_id=self.workspace_id,
                role_keys=self.role_keys,  # type: ignore[arg-type]
                entitlements=self.entitlements,  # type: ignore[arg-type]
            ),
            source="workos_session",
        )


class FakeCustomerReportRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def list_reports(
        self,
        *,
        account_id: str,
        workspace_id: str | None,
        limit: int,
    ) -> list[CustomerReportSummary]:
        self.calls.append(
            {
                "account_id": account_id,
                "workspace_id": workspace_id,
                "limit": limit,
            }
        )
        return [
            CustomerReportSummary(
                access_id="00000000-0000-0000-0000-000000000401",
                analysis_id="milk-aug-2026",
                analysis_result_id="00000000-0000-0000-0000-000000000501",
                collection_run_id="00000000-0000-0000-0000-000000000601",
                product_pack_id="fluid_milk",
                product_pack_version="1.4.0",
                reporting_status="ready",
                schema_version="2.0.0",
                checksum="a" * 64,
                title="Milk price intelligence",
                category="Milk",
                retailer_count=4,
                created_at=datetime(2026, 8, 20, 12, 0, tzinfo=UTC),
                granted_at=datetime(2026, 9, 14, 9, 0, tzinfo=UTC),
            )
        ]


def _test_app(
    *,
    principal_repository: FakeCustomerPrincipalRepository | None = None,
    report_repository: FakeCustomerReportRepository | None = None,
) -> tuple[FastAPI, FakeCustomerReportRepository]:
    app = FastAPI()
    app.state.settings = AppSettings(
        app_env="production",
        customer_identity_provider="workos",
        workos_client_id="client_123",
        workos_redirect_uri="https://web-production-ee2a4.up.railway.app/api/auth/callback",
    )
    reports = report_repository or FakeCustomerReportRepository()
    app.state.customer_session_authenticator = FakeCustomerSessionAuthenticator()
    app.state.customer_principal_repository = (
        principal_repository or FakeCustomerPrincipalRepository()
    )
    app.state.customer_report_repository = reports
    app.include_router(customer_identity_router)
    app.include_router(customer_report_router)
    return app, reports


async def test_customer_report_list_requires_customer_session() -> None:
    app, _reports = _test_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/customer/reports")

    assert response.status_code == 401
    assert response.json() == {"detail": "Customer authentication is required."}


async def test_customer_report_list_returns_scoped_granted_reports() -> None:
    app, reports = _test_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set(SESSION_COOKIE_NAME, "sealed-session")
        response = await client.get("/api/v1/customer/reports?limit=25")

    assert response.status_code == 200
    assert reports.calls == [
        {
            "account_id": "00000000-0000-0000-0000-000000000101",
            "workspace_id": "00000000-0000-0000-0000-000000000201",
            "limit": 25,
        }
    ]
    assert response.json() == {
        "schema_version": "1.0.0-customer-report-list",
        "scope": {
            "account_id": "00000000-0000-0000-0000-000000000101",
            "workspace_id": "00000000-0000-0000-0000-000000000201",
        },
        "reports": [
            {
                "access_id": "00000000-0000-0000-0000-000000000401",
                "analysis_id": "milk-aug-2026",
                "analysis_result_id": "00000000-0000-0000-0000-000000000501",
                "collection_run_id": "00000000-0000-0000-0000-000000000601",
                "product_pack_id": "fluid_milk",
                "product_pack_version": "1.4.0",
                "reporting_status": "ready",
                "schema_version": "2.0.0",
                "checksum": "a" * 64,
                "title": "Milk price intelligence",
                "category": "Milk",
                "retailer_count": 4,
                "created_at": "2026-08-20T12:00:00Z",
                "granted_at": "2026-09-14T09:00:00Z",
            }
        ],
    }


async def test_customer_report_list_denies_missing_analytics_permission() -> None:
    app, reports = _test_app(
        principal_repository=FakeCustomerPrincipalRepository(
            role_keys=frozenset({"billing_user"}),
        )
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set(SESSION_COOKIE_NAME, "sealed-session")
        response = await client.get("/api/v1/customer/reports")

    assert response.status_code == 403
    assert response.json() == {"detail": "Customer permission is required for this resource."}
    assert reports.calls == []


async def test_customer_report_list_denies_missing_app_analytics_entitlement() -> None:
    app, reports = _test_app(
        principal_repository=FakeCustomerPrincipalRepository(
            entitlements=frozenset(),
        )
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set(SESSION_COOKIE_NAME, "sealed-session")
        response = await client.get("/api/v1/customer/reports")

    assert response.status_code == 403
    assert response.json() == {"detail": "Customer entitlement is required for this resource."}
    assert reports.calls == []


async def test_customer_report_list_denies_principal_without_account() -> None:
    app, reports = _test_app(principal_repository=FakeCustomerPrincipalRepository(account_id=None))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set(SESSION_COOKIE_NAME, "sealed-session")
        response = await client.get("/api/v1/customer/reports")

    assert response.status_code == 403
    assert response.json() == {"detail": "Customer account access is required for this resource."}
    assert reports.calls == []


async def test_customer_report_list_supports_non_production_header_harness(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("CPGHERO_CUSTOMER_AUTH_TEST_HARNESS_ENABLED", "true")
    reports = FakeCustomerReportRepository()
    app = FastAPI()
    app.state.settings = AppSettings(app_env="development")
    app.state.customer_report_repository = reports
    app.include_router(customer_identity_router)
    app.include_router(customer_report_router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/customer/reports",
            headers={
                "X-CPGHero-Test-User-Id": "user_123",
                "X-CPGHero-Test-Email": "analyst@example.com",
                "X-CPGHero-Test-Account-Id": "account_abc",
                "X-CPGHero-Test-Workspace-Id": "workspace_xyz",
                "X-CPGHero-Test-Roles": "analyst",
                "X-CPGHero-Test-Entitlements": "app_analytics",
            },
        )

    assert response.status_code == 200
    assert reports.calls == [
        {
            "account_id": "account_abc",
            "workspace_id": "workspace_xyz",
            "limit": 50,
        }
    ]
