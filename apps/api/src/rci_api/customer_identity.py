"""Customer identity endpoints.

These endpoints expose CPGHero's app-local principal model. They do not expose
identity-provider secrets and do not make upstream provider calls.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, Request, Response

from rci_api.access import require_customer_principal
from rci_api.customer_principals import (
    CustomerPrincipalRepository,
    CustomerPrincipalResolution,
    PostgresCustomerPrincipalRepository,
)
from rci_api.workos_auth import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    CustomerSessionAuthenticator,
    WorkOSCustomerSessionAuthenticator,
    set_customer_cookie,
)
from rci_core import AccessPrincipal

router = APIRouter(prefix="/api/v1", tags=["customer-auth"])


def _serialize_principal(
    principal: AccessPrincipal,
    *,
    source: str,
) -> dict[str, object]:
    auth: dict[str, object] = {
        "provider": "cpghero",
        "source": source,
    }
    return {
        "schema_version": "1.0.0-customer-principal",
        "auth": auth,
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


def _customer_authenticator(request: Request) -> CustomerSessionAuthenticator:
    configured = getattr(request.app.state, "customer_session_authenticator", None)
    if configured is not None:
        return configured
    return WorkOSCustomerSessionAuthenticator.from_env(request.app.state.settings)


def _customer_principal_repository(request: Request) -> CustomerPrincipalRepository:
    configured = getattr(request.app.state, "customer_principal_repository", None)
    if configured is not None:
        return configured
    return PostgresCustomerPrincipalRepository(request.app.state.database_probe.engine)


async def _resolve_workos_customer_principal(
    request: Request,
    response: Response,
) -> CustomerPrincipalResolution:
    authenticator = _customer_authenticator(request)
    identity = authenticator.authenticate_session_cookie(
        session_cookie=request.cookies.get(SESSION_COOKIE_NAME),
        request=request,
    )
    if identity.refreshed and identity.sealed_session:
        set_customer_cookie(
            response,
            settings=request.app.state.settings,
            name=SESSION_COOKIE_NAME,
            value=identity.sealed_session,
            max_age=SESSION_MAX_AGE_SECONDS,
        )
    repository = _customer_principal_repository(request)
    return await repository.resolve_workos_identity(identity)


@router.get("/me")
async def current_customer_principal(
    request: Request,
    response: Response,
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
    settings = request.app.state.settings
    if settings.customer_identity_provider == "workos":
        resolution = await _resolve_workos_customer_principal(request, response)
        return _serialize_principal(
            resolution.principal,
            source="customer_session",
        )

    principal = require_customer_principal(
        request,
        test_user_id=x_cpghero_test_user_id,
        test_email=x_cpghero_test_email,
        test_account_id=x_cpghero_test_account_id,
        test_workspace_id=x_cpghero_test_workspace_id,
        test_roles=x_cpghero_test_roles,
        test_entitlements=x_cpghero_test_entitlements,
    )
    return _serialize_principal(
        principal,
        source="non_production_test_harness",
    )
