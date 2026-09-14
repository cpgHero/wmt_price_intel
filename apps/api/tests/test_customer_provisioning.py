from __future__ import annotations

import inspect
from typing import Any

from httpx import ASGITransport, AsyncClient

from rci_api.customer_provisioning import (
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
