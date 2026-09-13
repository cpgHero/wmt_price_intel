"""Customer identity endpoints.

These endpoints expose CPGHero's app-local principal model. They do not expose
identity-provider secrets and do not make upstream provider calls.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, Request

from rci_api.access import require_customer_principal

router = APIRouter(prefix="/api/v1", tags=["customer-auth"])


@router.get("/me")
async def current_customer_principal(
    request: Request,
    x_cpghero_test_user_id: Annotated[
        str | None,
        Header(alias="X-CPGHero-Test-User-Id"),
    ] = None,
    x_cpghero_test_email: Annotated[
        str | None,
        Header(alias="X-CPGHero-Test-Email"),
    ] = None,
    x_cpghero_test_account_id: Annotated[
        str | None,
        Header(alias="X-CPGHero-Test-Account-Id"),
    ] = None,
    x_cpghero_test_workspace_id: Annotated[
        str | None,
        Header(alias="X-CPGHero-Test-Workspace-Id"),
    ] = None,
    x_cpghero_test_roles: Annotated[
        str | None,
        Header(alias="X-CPGHero-Test-Roles"),
    ] = None,
    x_cpghero_test_entitlements: Annotated[
        str | None,
        Header(alias="X-CPGHero-Test-Entitlements"),
    ] = None,
) -> dict[str, object]:
    principal = require_customer_principal(
        request,
        test_user_id=x_cpghero_test_user_id,
        test_email=x_cpghero_test_email,
        test_account_id=x_cpghero_test_account_id,
        test_workspace_id=x_cpghero_test_workspace_id,
        test_roles=x_cpghero_test_roles,
        test_entitlements=x_cpghero_test_entitlements,
    )
    settings = request.app.state.settings
    return {
        "schema_version": "1.0.0-customer-principal",
        "auth": {
            "provider": settings.customer_identity_provider,
            "source": "non_production_test_harness",
        },
        "principal": {
            "user_id": principal.user_id,
            "email": principal.email,
            "account_id": principal.account_id,
            "workspace_id": principal.workspace_id,
            "roles": sorted(principal.role_keys),
            "permissions": sorted(principal.permissions),
            "entitlements": sorted(principal.entitlements),
            "is_system_actor": principal.is_system_actor,
        },
    }
