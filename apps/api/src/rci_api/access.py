"""Shared CPGHero API access guards.

This module intentionally preserves the current admin-token behavior while
returning a stable access principal that future account-scoped routes can
enforce against.
"""

from __future__ import annotations

import os
import secrets
from typing import cast

from fastapi import HTTPException, Request, status

from rci_core import ENTITLEMENT_KEYS, ROLE_KEYS, AccessPrincipal
from rci_core.access_control import EntitlementKey, RoleKey

SYSTEM_ADMIN_USER_ID = "authenticated-platform-admin"
SYSTEM_ADMIN_EMAIL = "platform-admin@cpghero.internal"
CUSTOMER_AUTH_TEST_HARNESS_ENABLED = "CPGHERO_CUSTOMER_AUTH_TEST_HARNESS_ENABLED"


def enabled_from_env(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def require_platform_admin(
    request: Request,
    provided_token: str | None,
    *,
    detail: str = "Authenticated administrator access is required.",
) -> AccessPrincipal:
    """Require the existing platform-admin token in production.

    Development and test retain the existing permissive behavior so local tools,
    tests, and internal admin work do not accidentally become blocked before the
    final customer identity provider is selected.
    """

    expected = os.getenv("PRODUCT_PACK_ADMIN_TOKEN", "").strip()
    if request.app.state.settings.is_production and (
        not expected or not provided_token or not secrets.compare_digest(expected, provided_token)
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)
    return AccessPrincipal(
        user_id=SYSTEM_ADMIN_USER_ID,
        email=SYSTEM_ADMIN_EMAIL,
        role_keys=frozenset({"system_admin"}),
    )


def require_enabled_platform_admin(
    request: Request,
    provided_token: str | None,
    *,
    enabled_flag_name: str,
    default_enabled: bool,
    disabled_detail: str,
    unauthorized_detail: str = "Authenticated administrator access is required.",
) -> AccessPrincipal:
    if not enabled_from_env(os.getenv(enabled_flag_name), default=default_enabled):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=disabled_detail)
    return require_platform_admin(request, provided_token, detail=unauthorized_detail)


def _split_csv(value: str | None) -> list[str]:
    if value is None:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _invalid_values(values: list[str], allowed: frozenset[str]) -> list[str]:
    return sorted(set(values).difference(allowed))


def require_customer_principal(
    request: Request,
    *,
    test_user_id: str | None,
    test_email: str | None,
    test_account_id: str | None,
    test_workspace_id: str | None,
    test_roles: str | None,
    test_entitlements: str | None,
) -> AccessPrincipal:
    """Resolve the current customer principal.

    Production WorkOS session verification is intentionally not implemented in
    this development seam. Until the live callback/session exchange is shipped,
    production fails closed. Non-production tests and local demos can opt into a
    header-backed harness with explicit, validated role and entitlement keys.
    """

    if request.app.state.settings.is_production:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Customer authentication is not enabled in production yet.",
        )

    if not enabled_from_env(os.getenv(CUSTOMER_AUTH_TEST_HARNESS_ENABLED)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Customer authentication test harness is disabled.",
        )

    if not test_user_id or not test_email or not test_account_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Customer test principal requires user, email, and account headers.",
        )

    role_values = _split_csv(test_roles)
    if not role_values:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Customer test principal requires at least one role.",
        )

    invalid_roles = _invalid_values(role_values, cast("frozenset[str]", ROLE_KEYS))
    if invalid_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown customer role keys: {', '.join(invalid_roles)}",
        )

    entitlement_values = _split_csv(test_entitlements)
    invalid_entitlements = _invalid_values(
        entitlement_values,
        cast("frozenset[str]", ENTITLEMENT_KEYS),
    )
    if invalid_entitlements:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown customer entitlement keys: {', '.join(invalid_entitlements)}",
        )

    return AccessPrincipal(
        user_id=test_user_id.strip(),
        email=test_email.strip(),
        account_id=test_account_id.strip(),
        workspace_id=test_workspace_id.strip() if test_workspace_id else None,
        role_keys=frozenset(cast("RoleKey", role) for role in role_values),
        entitlements=frozenset(
            cast("EntitlementKey", entitlement) for entitlement in entitlement_values
        ),
    )


def platform_admin_actor(principal: AccessPrincipal) -> str:
    """Return a server-controlled audit actor for token-authenticated admins."""

    if principal.is_system_actor:
        return principal.user_id
    return "authenticated-platform-actor"
