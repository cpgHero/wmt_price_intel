from __future__ import annotations

import inspect
from typing import Any

from httpx import ASGITransport, AsyncClient

from rci_api.customer_provisioning import (
    CustomerAccountFoundationAccount,
    CustomerAccountFoundationEntitlement,
    CustomerAccountFoundationMember,
    CustomerAccountFoundationResponse,
    CustomerAccountFoundationSummary,
    CustomerAccountFoundationWorkspace,
    CustomerAuthCanaryStatus,
    CustomerAuthInvitationStatus,
    CustomerAuthReadinessResponse,
    CustomerAuthWebhookEventStatus,
    PostgresCustomerProvisioningRepository,
    PrepareCustomerAccountRequest,
    PrepareCustomerAccountResponse,
    WebhookProcessingResult,
    _workos_invitation_id_for_event,
    _workos_user_id_for_event,
)
from rci_api.main import create_app
from rci_core import AccessPrincipal, AppSettings


class FakeCustomerProvisioningRepository:
    def __init__(self) -> None:
        self.prepared: tuple[PrepareCustomerAccountRequest, AccessPrincipal] | None = None
        self.webhook_payloads: list[tuple[dict[str, Any], str]] = []

    async def prepare_customer_account(
        self,
        request: PrepareCustomerAccountRequest,
        *,
        prepared_by: AccessPrincipal,
    ) -> PrepareCustomerAccountResponse:
        self.prepared = (request, prepared_by)
        return PrepareCustomerAccountResponse(
            account_id="00000000-0000-0000-0000-000000000101",
            account_slug=request.account_slug or "acme-foods",
            workspace_id="00000000-0000-0000-0000-000000000201",
            workspace_slug=request.workspace_slug,
            user_id="00000000-0000-0000-0000-000000000301",
            invitation_id="00000000-0000-0000-0000-000000000401",
            invitation_status="prepared",
            membership_status="invited",
            role_keys=tuple(request.role_keys),
            entitlement_keys=tuple(request.entitlement_keys),
            external_organization_mapped=bool(request.workos_organization_id),
            external_user_mapped=bool(request.workos_user_id),
            customer_auth_provider="cpghero",
        )

    async def record_identity_webhook(
        self,
        *,
        payload: dict[str, Any],
        payload_sha256: str,
    ) -> WebhookProcessingResult:
        self.webhook_payloads.append((payload, payload_sha256))
        return WebhookProcessingResult(
            event_id=str(payload["id"]),
            event_type=str(payload["event"]),
            processing_status="processed",
        )

    async def customer_auth_readiness(
        self,
        *,
        email: str | None = None,
        limit: int = 25,
    ) -> CustomerAuthReadinessResponse:
        assert limit == 25
        return CustomerAuthReadinessResponse(
            customer_auth_provider="disabled",
            customer_login_enabled=False,
            canary=CustomerAuthCanaryStatus(
                enabled=True,
                configured=False,
                allowed_email_count=0,
                allowed_domain_count=0,
            ),
            cutover_ready=False,
            blockers=("Production customer login is still disabled.",),
            invitations=(
                CustomerAuthInvitationStatus(
                    email=email or "admin@acme.example",
                    account_slug="acme-foods",
                    account_display_name="Acme Foods",
                    workspace_slug="default",
                    workspace_display_name="Default workspace",
                    invitation_status="sent",
                    account_membership_status="invited",
                    workspace_membership_status="invited",
                    role_keys=("account_owner",),
                    entitlement_keys=("analytics.price_intelligence",),
                    has_external_user_mapping=True,
                    has_external_organization_mapping=True,
                    has_workos_invitation=True,
                    accepted=False,
                    prepared_at="2026-09-14 01:00:00+00",
                    updated_at="2026-09-14 01:30:00+00",
                ),
            ),
            recent_webhook_events=(
                CustomerAuthWebhookEventStatus(
                    event_type="user.created",
                    processing_status="processed",
                    email_snapshot=email or "admin@acme.example",
                    has_workos_user=True,
                    has_workos_organization=False,
                    has_workos_invitation=False,
                    processed=True,
                    received_at="2026-09-14 01:29:56+00",
                    processed_at="2026-09-14 01:29:56+00",
                ),
            ),
        )

    async def customer_account_foundation(
        self,
        *,
        account_slug: str | None = None,
        limit: int = 50,
    ) -> CustomerAccountFoundationResponse:
        assert limit == 50
        return CustomerAccountFoundationResponse(
            summary=CustomerAccountFoundationSummary(
                accounts=1,
                customer_accounts=1,
                active_accounts=1,
                workspaces=1,
                active_workspaces=1,
                members=1,
                active_members=1,
                entitlements=1,
                active_entitlements=1,
                active_report_grants=2,
            ),
            accounts=(
                CustomerAccountFoundationAccount(
                    account_id="00000000-0000-0000-0000-000000000101",
                    account_slug=account_slug or "acme-foods",
                    account_display_name="Acme Foods",
                    account_type="customer",
                    account_status="active",
                    workspace_count=1,
                    member_count=1,
                    active_member_count=1,
                    entitlement_count=1,
                    active_entitlement_count=1,
                    active_report_grant_count=2,
                    revoked_report_grant_count=1,
                    has_identity_provider_organization_binding=True,
                    created_at="2026-09-14 01:00:00+00",
                ),
            ),
            workspaces=(
                CustomerAccountFoundationWorkspace(
                    workspace_id="00000000-0000-0000-0000-000000000201",
                    account_id="00000000-0000-0000-0000-000000000101",
                    account_slug=account_slug or "acme-foods",
                    account_display_name="Acme Foods",
                    workspace_slug="default",
                    workspace_display_name="Default workspace",
                    workspace_status="active",
                    active_member_count=1,
                    active_report_grant_count=2,
                    revoked_report_grant_count=1,
                    created_at="2026-09-14 01:01:00+00",
                ),
            ),
            members=(
                CustomerAccountFoundationMember(
                    user_id="00000000-0000-0000-0000-000000000301",
                    email="admin@acme.example",
                    display_name="Acme Admin",
                    account_id="00000000-0000-0000-0000-000000000101",
                    account_slug=account_slug or "acme-foods",
                    account_display_name="Acme Foods",
                    account_membership_status="active",
                    workspace_slug="default",
                    workspace_display_name="Default workspace",
                    workspace_membership_status="active",
                    account_role_keys=("account_owner",),
                    workspace_role_keys=(),
                    has_identity_provider_user_binding=True,
                    created_at="2026-09-14 01:02:00+00",
                ),
            ),
            entitlements=(
                CustomerAccountFoundationEntitlement(
                    account_id="00000000-0000-0000-0000-000000000101",
                    account_slug=account_slug or "acme-foods",
                    account_display_name="Acme Foods",
                    entitlement_key="analytics.price_intelligence",
                    entitlement_status="active",
                    starts_at=None,
                    expires_at=None,
                    created_at="2026-09-14 01:03:00+00",
                ),
            ),
        )


def _app(app_env: str = "development") -> tuple[Any, FakeCustomerProvisioningRepository]:
    repository = FakeCustomerProvisioningRepository()
    app = create_app(AppSettings(app_env=app_env))
    app.state.customer_provisioning_repository = repository
    return app, repository


async def test_prepare_customer_account_is_admin_guarded_and_cpghero_facing(
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("PRODUCT_PACK_ADMIN_TOKEN", "private-admin-token")
    app, repository = _app(app_env="production")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        missing = await client.post(
            "/api/v1/admin/customer-provisioning/accounts/prepare",
            json={
                "account_display_name": "Acme Foods",
                "admin_email": "Admin@Acme.example",
                "role_keys": ["account_owner"],
                "entitlement_keys": ["analytics.price_intelligence"],
            },
        )
        prepared = await client.post(
            "/api/v1/admin/customer-provisioning/accounts/prepare",
            headers={"X-RCI-Admin-Token": "private-admin-token"},
            json={
                "account_display_name": "Acme Foods",
                "admin_email": "Admin@Acme.example",
                "role_keys": ["account_owner"],
                "entitlement_keys": ["analytics.price_intelligence"],
                "workos_organization_id": "org_123",
            },
        )

    assert missing.status_code == 401
    assert prepared.status_code == 200
    body = prepared.json()
    assert body["schema_version"] == "1.0.0-customer-provisioning"
    assert body["customer_auth_provider"] == "cpghero"
    assert "workos_organization_id" not in body
    assert body["external_organization_mapped"] is True
    assert repository.prepared is not None
    request, principal = repository.prepared
    assert request.admin_email == "admin@acme.example"
    assert principal.user_id == "authenticated-platform-admin"


async def test_prepare_customer_account_rejects_unknown_roles_and_entitlements() -> None:
    app, repository = _app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        role_response = await client.post(
            "/api/v1/admin/customer-provisioning/accounts/prepare",
            json={
                "account_display_name": "Acme Foods",
                "admin_email": "admin@acme.example",
                "role_keys": ["super_admin"],
            },
        )
        entitlement_response = await client.post(
            "/api/v1/admin/customer-provisioning/accounts/prepare",
            json={
                "account_display_name": "Acme Foods",
                "admin_email": "admin@acme.example",
                "role_keys": ["viewer"],
                "entitlement_keys": ["private.provider_console"],
            },
        )

    assert role_response.status_code == 422
    assert "super_admin" in role_response.text
    assert entitlement_response.status_code == 422
    assert "private.provider_console" in entitlement_response.text
    assert repository.prepared is None


async def test_prepare_customer_account_rejects_system_roles() -> None:
    app, repository = _app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/admin/customer-provisioning/accounts/prepare",
            json={
                "account_display_name": "Acme Foods",
                "admin_email": "admin@acme.example",
                "role_keys": ["system_admin"],
            },
        )

    assert response.status_code == 422
    assert "system roles cannot be assigned to customer accounts" in response.text
    assert repository.prepared is None


async def test_customer_auth_readiness_is_admin_guarded(monkeypatch: Any) -> None:
    monkeypatch.setenv("PRODUCT_PACK_ADMIN_TOKEN", "private-admin-token")
    app, _repository = _app(app_env="production")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        missing = await client.get("/api/v1/admin/customer-provisioning/readiness")
        ready = await client.get(
            "/api/v1/admin/customer-provisioning/readiness?email=Admin@Acme.example",
            headers={"X-RCI-Admin-Token": "private-admin-token"},
        )

    assert missing.status_code == 401
    assert ready.status_code == 200
    body = ready.json()
    assert body["schema_version"] == "1.0.0-customer-auth-readiness"
    assert body["customer_auth_provider"] == "disabled"
    assert body["customer_login_enabled"] is False
    assert body["cutover_ready"] is False
    assert body["canary"] == {
        "enabled": True,
        "configured": False,
        "allowed_email_count": 0,
        "allowed_domain_count": 0,
    }
    assert body["invitations"][0]["email"] == "Admin@Acme.example"
    assert "workos_user_id" not in body["invitations"][0]
    assert body["recent_webhook_events"][0]["processing_status"] == "processed"


async def test_customer_account_foundation_is_admin_guarded_and_source_backed(
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("PRODUCT_PACK_ADMIN_TOKEN", "private-admin-token")
    app, _repository = _app(app_env="production")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        missing = await client.get("/api/v1/admin/customer-provisioning/account-foundation")
        snapshot = await client.get(
            "/api/v1/admin/customer-provisioning/account-foundation?account_slug=acme-foods",
            headers={"X-RCI-Admin-Token": "private-admin-token"},
        )

    assert missing.status_code == 401
    assert snapshot.status_code == 200
    body = snapshot.json()
    assert body["schema_version"] == "1.0.0-customer-account-foundation"
    assert body["summary"]["customer_accounts"] == 1
    assert body["summary"]["active_report_grants"] == 2
    assert body["accounts"][0]["account_slug"] == "acme-foods"
    assert body["workspaces"][0]["workspace_slug"] == "default"
    assert body["members"][0]["account_role_keys"] == ["account_owner"]
    assert body["members"][0]["has_identity_provider_user_binding"] is True
    assert body["entitlements"][0]["entitlement_key"] == "analytics.price_intelligence"
    assert "workos_user_id" not in body["members"][0]
    assert "workos_organization_id" not in body["accounts"][0]


def test_workos_webhook_extracts_event_type_specific_ids() -> None:
    user_created = {
        "id": "user_01M2EPG44YNPCPXBCJE28NR019",
        "email": "admin@acme.example",
    }
    invitation_accepted = {
        "id": "invitation_01M2EPG46YZ3XA1VD342MAFDG6",
        "email": "admin@acme.example",
        "user_id": "user_01M2EPG44YNPCPXBCJE28NR019",
    }

    assert _workos_user_id_for_event("user.created", user_created) == (
        "user_01M2EPG44YNPCPXBCJE28NR019"
    )
    assert _workos_invitation_id_for_event("user.created", user_created) is None
    assert _workos_user_id_for_event("invitation.accepted", invitation_accepted) == (
        "user_01M2EPG44YNPCPXBCJE28NR019"
    )
    assert _workos_invitation_id_for_event("invitation.accepted", invitation_accepted) == (
        "invitation_01M2EPG46YZ3XA1VD342MAFDG6"
    )


def test_postgres_invitation_lookup_casts_nullable_text_parameters() -> None:
    source = inspect.getsource(PostgresCustomerProvisioningRepository._find_invitation)

    assert "CAST(:workos_invitation_id AS text) IS NOT NULL" in source
    assert "invitation.workos_invitation_id =" in source
    assert "CAST(:workos_invitation_id AS text)" in source
    assert "CAST(:email AS text) IS NOT NULL" in source
    assert "invitation.email = CAST(:email AS text)" in source


async def test_workos_webhook_requires_configured_secret(monkeypatch: Any) -> None:
    monkeypatch.delenv("WORKOS_WEBHOOK_SECRET", raising=False)
    app, _repository = _app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/webhooks/workos",
            headers={"WorkOS-Signature": "sig"},
            json={"id": "event_123", "event": "invitation.accepted", "data": {}},
        )

    assert response.status_code == 503
    assert "signing secret is not configured" in response.json()["detail"]


async def test_workos_webhook_verifies_signature_and_records_event(monkeypatch: Any) -> None:
    monkeypatch.setenv("WORKOS_WEBHOOK_SECRET", "whsec_test")
    app, repository = _app()
    seen: dict[str, str] = {}

    def verifier(event_body: bytes, signature: str, secret: str) -> None:
        seen["body"] = event_body.decode("utf-8")
        seen["signature"] = signature
        seen["secret"] = secret

    app.state.workos_webhook_verifier = verifier

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/webhooks/workos",
            headers={"WorkOS-Signature": "sig-valid"},
            json={
                "id": "event_123",
                "event": "invitation.accepted",
                "data": {"email": "admin@acme.example", "user_id": "user_123"},
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "schema_version": "1.0.0-customer-identity-webhook",
        "event_id": "event_123",
        "event_type": "invitation.accepted",
        "processing_status": "processed",
    }
    assert seen["signature"] == "sig-valid"
    assert seen["secret"] == "whsec_test"
    assert repository.webhook_payloads
    payload, payload_sha256 = repository.webhook_payloads[0]
    assert payload["data"]["email"] == "admin@acme.example"
    assert len(payload_sha256) == 64
