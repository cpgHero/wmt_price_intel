"""Shared CPGHero API access guards.

This module intentionally preserves the current admin-token behavior while
returning a stable access principal that future account-scoped routes can
enforce against.
"""

from __future__ import annotations

import os
import secrets

from fastapi import HTTPException, Request, status

from rci_core import AccessPrincipal

SYSTEM_ADMIN_USER_ID = "authenticated-platform-admin"
SYSTEM_ADMIN_EMAIL = "platform-admin@cpghero.internal"


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


def platform_admin_actor(principal: AccessPrincipal) -> str:
    """Return a server-controlled audit actor for token-authenticated admins."""

    if principal.is_system_actor:
        return principal.user_id
    return "authenticated-platform-actor"
