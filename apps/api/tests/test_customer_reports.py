from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, HTTPException, status
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch

from rci_api.analyses import get_analysis_service
from rci_api.customer_identity import router as customer_identity_router
from rci_api.customer_principals import CustomerPrincipalResolution
from rci_api.customer_reports import (
    AdminCustomerReportGrant,
    AdminGrantableReport,
    CustomerReportDetail,
    CustomerReportSummary,
)
from rci_api.customer_reports import admin_router as customer_report_admin_router
from rci_api.customer_reports import router as customer_report_router
from rci_api.price_monitoring import get_price_monitoring_service
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
                role_keys=self.role_keys,
                entitlements=self.entitlements,
            ),
            source="workos_session",
        )


class FakeCustomerReportRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.detail: CustomerReportDetail | None = CustomerReportDetail(
            summary=self._summary(),
            analysis={
                "id": "00000000-0000-0000-0000-000000000501",
                "analysis_run_id": "00000000-0000-0000-0000-000000000701",
                "analysis_id": "milk-aug-2026",
                "collection_run_id": "00000000-0000-0000-0000-000000000601",
                "status": "succeeded",
                "reporting_status": "ready",
                "product_pack_id": "fluid_milk",
                "product_pack_version": "1.4.0",
                "schema_version": "2.0.0",
                "checksum": "a" * 64,
                "result": {"schema_version": "2.0.0", "analysis_id": "milk-aug-2026"},
                "created_at": datetime(2026, 8, 20, 12, 0, tzinfo=UTC),
            },
        )

    def _summary(self) -> CustomerReportSummary:
        return CustomerReportSummary(
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

    def _admin_grant(self, *, status: str = "active") -> AdminCustomerReportGrant:
        return AdminCustomerReportGrant(
            access_id="00000000-0000-0000-0000-000000000401",
            account_id="00000000-0000-0000-0000-000000000101",
            account_slug="ghretail",
            account_display_name="GHRetail",
            workspace_id="00000000-0000-0000-0000-000000000201",
            workspace_slug="pricing",
            workspace_display_name="Pricing",
            analysis_id="milk-aug-2026",
            analysis_result_id="00000000-0000-0000-0000-000000000501",
            title="Milk price intelligence",
            category="Milk",
            status=status,
            granted_at=datetime(2026, 9, 14, 9, 0, tzinfo=UTC),
        )

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
        return [self._summary()]

    async def get_report(
        self,
        *,
        access_id: str,
        account_id: str,
        workspace_id: str | None,
    ) -> CustomerReportDetail | None:
        self.calls.append(
            {
                "access_id": access_id,
                "account_id": account_id,
                "workspace_id": workspace_id,
            }
        )
        return self.detail

    async def admin_snapshot(self, *, limit: int) -> dict[str, list[object]]:
        self.calls.append({"admin_snapshot_limit": limit})
        return {
            "grants": [self._admin_grant()],
            "grantable_reports": [
                AdminGrantableReport(
                    analysis_id="milk-aug-2026",
                    analysis_result_id="00000000-0000-0000-0000-000000000501",
                    title="Milk price intelligence",
                    category="Milk",
                    product_pack_id="fluid_milk",
                    product_pack_version="1.4.0",
                    created_at=datetime(2026, 8, 20, 12, 0, tzinfo=UTC),
                )
            ],
        }

    async def admin_grant_report(
        self,
        *,
        account_key: str,
        workspace_key: str | None,
        analysis_result_id: str,
        granted_by: str | None,
    ) -> AdminCustomerReportGrant:
        self.calls.append(
            {
                "account_key": account_key,
                "workspace_key": workspace_key,
                "analysis_result_id": analysis_result_id,
                "granted_by": granted_by,
            }
        )
        return self._admin_grant()

    async def admin_revoke_report(self, *, access_id: str) -> AdminCustomerReportGrant | None:
        self.calls.append({"revoke_access_id": access_id})
        return self._admin_grant(status="revoked")


class FakeAnalysisService:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    async def report_view(self, analysis_id: str) -> dict[str, object]:
        self.calls.append({"report_view": analysis_id})
        return {
            "analysis_id": analysis_id,
            "generated_at": "2026-09-14T00:00:00Z",
            "sections": [],
        }

    async def quality(self, analysis_id: str) -> dict[str, object]:
        self.calls.append({"quality": analysis_id})
        return {"analysis_id": analysis_id, "status": "passed"}

    async def product_evidence(self, analysis_id: str, decision_id: str) -> dict[str, object]:
        self.calls.append({"product_evidence": f"{analysis_id}:{decision_id}"})
        return {
            "analysis_id": analysis_id,
            "decision_id": decision_id,
            "rows": [],
        }


class FakePriceMonitoringService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def map_view(
        self,
        analysis_id: str,
        filters: Any,
        *,
        detail: str,
    ) -> dict[str, object]:
        self.calls.append(
            {
                "map_view": analysis_id,
                "retailer_id": filters.retailer_id,
                "product_id": filters.product_id,
                "detail": detail,
            }
        )
        return {
            "analysis_id": analysis_id,
            "display": {"distribution_store_count": 2, "not_observed_locations": 1},
            "points": [],
        }

    async def state_coverage(
        self,
        analysis_id: str,
        products: list[dict[str, str]],
    ) -> dict[str, object]:
        self.calls.append({"state_coverage": analysis_id, "products": products})
        return {
            "analysis_id": analysis_id,
            "products": products,
            "state_options": [{"state": "CA", "product_count": 1}],
        }

    async def evidence_csv(self, analysis_id: str, filters: Any) -> str:
        self.calls.append(
            {
                "evidence_csv": analysis_id,
                "retailer_id": filters.retailer_id,
                "product_id": filters.product_id,
            }
        )
        return "retailer_id,product_id\nwalmart,123\n"


def _test_app(
    *,
    principal_repository: FakeCustomerPrincipalRepository | None = None,
    report_repository: FakeCustomerReportRepository | None = None,
    analysis_service: FakeAnalysisService | None = None,
    price_monitoring_service: FakePriceMonitoringService | None = None,
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
    app.dependency_overrides[get_analysis_service] = lambda: (
        analysis_service or FakeAnalysisService()
    )
    app.dependency_overrides[get_price_monitoring_service] = lambda: (
        price_monitoring_service or FakePriceMonitoringService()
    )
    app.include_router(customer_identity_router)
    app.include_router(customer_report_admin_router)
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


async def test_customer_report_detail_requires_active_grant() -> None:
    app, reports = _test_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set(SESSION_COOKIE_NAME, "sealed-session")
        response = await client.get("/api/v1/customer/reports/00000000-0000-0000-0000-000000000401")

    assert response.status_code == 200
    assert reports.calls == [
        {
            "access_id": "00000000-0000-0000-0000-000000000401",
            "account_id": "00000000-0000-0000-0000-000000000101",
            "workspace_id": "00000000-0000-0000-0000-000000000201",
        }
    ]
    payload = response.json()
    assert payload["schema_version"] == "1.0.0-customer-report-detail"
    assert payload["report"]["title"] == "Milk price intelligence"
    assert payload["analysis"]["analysis_id"] == "milk-aug-2026"


async def test_customer_report_detail_hides_missing_or_ungranted_report() -> None:
    reports = FakeCustomerReportRepository()
    reports.detail = None
    app, reports = _test_app(report_repository=reports)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set(SESSION_COOKIE_NAME, "sealed-session")
        response = await client.get("/api/v1/customer/reports/00000000-0000-0000-0000-000000000499")

    assert response.status_code == 404
    assert response.json() == {"detail": "A granted, ready customer report was not found."}


async def test_customer_report_view_uses_grant_before_report_service() -> None:
    analysis_service = FakeAnalysisService()
    app, reports = _test_app(analysis_service=analysis_service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set(SESSION_COOKIE_NAME, "sealed-session")
        response = await client.get(
            "/api/v1/customer/reports/00000000-0000-0000-0000-000000000401/report"
        )

    assert response.status_code == 200
    assert reports.calls == [
        {
            "access_id": "00000000-0000-0000-0000-000000000401",
            "account_id": "00000000-0000-0000-0000-000000000101",
            "workspace_id": "00000000-0000-0000-0000-000000000201",
        }
    ]
    assert analysis_service.calls == [{"report_view": "milk-aug-2026"}]
    payload = response.json()
    assert payload["schema_version"] == "1.0.0-customer-report-view"
    assert payload["report"]["title"] == "Milk price intelligence"
    assert payload["view"]["analysis_id"] == "milk-aug-2026"


async def test_customer_report_quality_uses_grant_before_quality_service() -> None:
    analysis_service = FakeAnalysisService()
    app, _reports = _test_app(analysis_service=analysis_service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set(SESSION_COOKIE_NAME, "sealed-session")
        response = await client.get(
            "/api/v1/customer/reports/00000000-0000-0000-0000-000000000401/quality"
        )

    assert response.status_code == 200
    assert analysis_service.calls == [{"quality": "milk-aug-2026"}]
    assert response.json()["quality"] == {
        "analysis_id": "milk-aug-2026",
        "status": "passed",
    }


async def test_customer_report_evidence_uses_grant_before_evidence_service() -> None:
    analysis_service = FakeAnalysisService()
    app, _reports = _test_app(analysis_service=analysis_service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set(SESSION_COOKIE_NAME, "sealed-session")
        response = await client.get(
            "/api/v1/customer/reports/00000000-0000-0000-0000-000000000401"
            "/product-decisions/decision-123/evidence"
        )

    assert response.status_code == 200
    assert analysis_service.calls == [{"product_evidence": "milk-aug-2026:decision-123"}]
    assert response.json() == {
        "analysis_id": "milk-aug-2026",
        "decision_id": "decision-123",
        "rows": [],
    }


async def test_customer_report_view_does_not_call_report_service_without_grant() -> None:
    reports = FakeCustomerReportRepository()
    reports.detail = None
    analysis_service = FakeAnalysisService()
    app, reports = _test_app(report_repository=reports, analysis_service=analysis_service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set(SESSION_COOKIE_NAME, "sealed-session")
        response = await client.get(
            "/api/v1/customer/reports/00000000-0000-0000-0000-000000000499/report"
        )

    assert response.status_code == 404
    assert reports.calls == [
        {
            "access_id": "00000000-0000-0000-0000-000000000499",
            "account_id": "00000000-0000-0000-0000-000000000101",
            "workspace_id": "00000000-0000-0000-0000-000000000201",
        }
    ]
    assert analysis_service.calls == []


async def test_customer_report_map_uses_grant_before_price_service() -> None:
    price_service = FakePriceMonitoringService()
    app, reports = _test_app(price_monitoring_service=price_service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set(SESSION_COOKIE_NAME, "sealed-session")
        response = await client.get(
            "/api/v1/customer/reports/00000000-0000-0000-0000-000000000401"
            "/price-monitoring/map?retailer=walmart&product_id=123&detail=summary"
        )

    assert response.status_code == 200
    assert reports.calls == [
        {
            "access_id": "00000000-0000-0000-0000-000000000401",
            "account_id": "00000000-0000-0000-0000-000000000101",
            "workspace_id": "00000000-0000-0000-0000-000000000201",
        }
    ]
    assert price_service.calls == [
        {
            "map_view": "milk-aug-2026",
            "retailer_id": "walmart",
            "product_id": "123",
            "detail": "summary",
        }
    ]
    assert response.json()["display"]["distribution_store_count"] == 2


async def test_customer_report_state_coverage_uses_grant_before_price_service() -> None:
    price_service = FakePriceMonitoringService()
    app, _reports = _test_app(price_monitoring_service=price_service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set(SESSION_COOKIE_NAME, "sealed-session")
        response = await client.post(
            "/api/v1/customer/reports/00000000-0000-0000-0000-000000000401"
            "/price-monitoring/state-coverage",
            json={"products": [{"retailer_id": "walmart", "product_id": "123"}]},
        )

    assert response.status_code == 200
    assert price_service.calls == [
        {
            "state_coverage": "milk-aug-2026",
            "products": [{"retailer_id": "walmart", "product_id": "123"}],
        }
    ]
    assert response.json()["state_options"] == [{"state": "CA", "product_count": 1}]


async def test_customer_report_evidence_csv_uses_grant_before_price_service() -> None:
    price_service = FakePriceMonitoringService()
    app, _reports = _test_app(price_monitoring_service=price_service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set(SESSION_COOKIE_NAME, "sealed-session")
        response = await client.get(
            "/api/v1/customer/reports/00000000-0000-0000-0000-000000000401"
            "/price-monitoring/evidence.csv?retailer=walmart&product_id=123"
        )

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.text == "retailer_id,product_id\nwalmart,123\n"
    assert price_service.calls == [
        {
            "evidence_csv": "milk-aug-2026",
            "retailer_id": "walmart",
            "product_id": "123",
        }
    ]


async def test_customer_report_map_does_not_call_price_service_without_grant() -> None:
    reports = FakeCustomerReportRepository()
    reports.detail = None
    price_service = FakePriceMonitoringService()
    app, reports = _test_app(report_repository=reports, price_monitoring_service=price_service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set(SESSION_COOKIE_NAME, "sealed-session")
        response = await client.get(
            "/api/v1/customer/reports/00000000-0000-0000-0000-000000000499"
            "/price-monitoring/map?retailer=walmart&product_id=123"
        )

    assert response.status_code == 404
    assert reports.calls == [
        {
            "access_id": "00000000-0000-0000-0000-000000000499",
            "account_id": "00000000-0000-0000-0000-000000000101",
            "workspace_id": "00000000-0000-0000-0000-000000000201",
        }
    ]
    assert price_service.calls == []


async def test_admin_customer_report_access_snapshot_requires_admin_token() -> None:
    app, reports = _test_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/admin/customer-report-access")

    assert response.status_code == 401
    assert reports.calls == []


async def test_admin_customer_report_access_snapshot_lists_grants_and_reports(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRODUCT_PACK_ADMIN_TOKEN", "secret")
    app, reports = _test_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/admin/customer-report-access?limit=20",
            headers={"X-RCI-Admin-Token": "secret"},
        )

    assert response.status_code == 200
    assert reports.calls == [{"admin_snapshot_limit": 20}]
    payload = response.json()
    assert payload["schema_version"] == "1.0.0-admin-customer-report-access"
    assert payload["grants"][0]["account_slug"] == "ghretail"
    assert payload["grantable_reports"][0]["analysis_result_id"] == (
        "00000000-0000-0000-0000-000000000501"
    )


async def test_admin_customer_report_access_grants_ready_report(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRODUCT_PACK_ADMIN_TOKEN", "secret")
    app, reports = _test_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/admin/customer-report-access",
            headers={"X-RCI-Admin-Token": "secret"},
            json={
                "account": "ghretail",
                "workspace": "pricing",
                "analysis_result_id": "00000000-0000-0000-0000-000000000501",
            },
        )

    assert response.status_code == 200
    assert reports.calls == [
        {
            "account_key": "ghretail",
            "workspace_key": "pricing",
            "analysis_result_id": "00000000-0000-0000-0000-000000000501",
            "granted_by": None,
        }
    ]
    assert response.json()["status"] == "active"


async def test_admin_customer_report_access_revokes_without_deleting(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRODUCT_PACK_ADMIN_TOKEN", "secret")
    app, reports = _test_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.delete(
            "/api/v1/admin/customer-report-access/00000000-0000-0000-0000-000000000401",
            headers={"X-RCI-Admin-Token": "secret"},
        )

    assert response.status_code == 200
    assert reports.calls == [{"revoke_access_id": "00000000-0000-0000-0000-000000000401"}]
    assert response.json()["status"] == "revoked"
