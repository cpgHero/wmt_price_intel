"""Reusable CPGHero customer access dependencies and scope guards."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status

from rci_api.customer_identity import resolve_current_customer_principal
from rci_api.customer_principals import CustomerPrincipalResolution
from rci_core import AccessPrincipal
from rci_core.access_control import EntitlementKey, PermissionKey


async def current_customer_access_principal(
    resolution: Annotated[
        CustomerPrincipalResolution,
        Depends(resolve_current_customer_principal),
    ],
) -> AccessPrincipal:
    """Return the current CPGHero customer principal for protected API routes."""

    return resolution.principal


def enforce_customer_access(
    principal: AccessPrincipal,
    *,
    permission: PermissionKey | None = None,
    entitlement: EntitlementKey | None = None,
    account_id: str | None = None,
    workspace_id: str | None = None,
) -> None:
    """Fail closed when a customer principal cannot access a scoped resource.

    This helper intentionally makes authorization checks explicit at route/service
    boundaries. A route can opt into only the dimensions it knows how to enforce,
    and future report/project routes can add account/workspace predicates without
    reimplementing identity-provider-specific session handling.
    """

    if account_id is not None and principal.account_id != account_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Customer account access is required for this resource.",
        )
    if workspace_id is not None and principal.workspace_id != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Customer workspace access is required for this resource.",
        )
    if permission is not None and not principal.has_permission(permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Customer permission is required for this resource.",
        )
    if entitlement is not None and not principal.has_entitlement(entitlement):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Customer entitlement is required for this resource.",
        )
