from __future__ import annotations

import pytest

from rci_core.access_control import (
    ENTITLEMENT_KEYS,
    ROLE_KEYS,
    ROLE_PERMISSIONS,
    ROLE_SCOPES,
    AccessPrincipal,
)


def test_account_owner_expands_to_management_and_reporting_permissions() -> None:
    principal = AccessPrincipal(
        user_id="user-1",
        email="owner@example.com",
        account_id="account-1",
        role_keys=frozenset({"account_owner"}),
        entitlements=frozenset({"bulk_projects", "app_analytics"}),
    )

    assert principal.has_permission("users.manage")
    assert principal.has_permission("projects.approve_paid_run")
    assert principal.has_permission("analytics.share")
    assert principal.has_permission("billing.view")
    assert principal.has_entitlement("bulk_projects")
    assert principal.has_entitlement("app_analytics")
    assert principal.is_system_actor is False


def test_viewer_cannot_approve_paid_work_or_download_exports() -> None:
    principal = AccessPrincipal(
        user_id="user-2",
        email="viewer@example.com",
        account_id="account-1",
        workspace_id="workspace-1",
        role_keys=frozenset({"viewer"}),
    )

    assert principal.permissions == frozenset({"analytics.view"})

    with pytest.raises(PermissionError, match=r"projects\.approve_paid_run"):
        principal.require_permission("projects.approve_paid_run")

    with pytest.raises(PermissionError, match="bulk_projects"):
        principal.require_entitlement("bulk_projects")


def test_system_roles_are_classified_as_system_actors() -> None:
    principal = AccessPrincipal(
        user_id="user-3",
        email="admin@example.com",
        role_keys=frozenset({"system_admin"}),
    )

    assert principal.is_system_actor
    assert principal.permissions == ROLE_PERMISSIONS["system_admin"]
    assert ROLE_SCOPES["system_admin"] == "system"


def test_runtime_role_and_entitlement_registries_cover_known_keys() -> None:
    assert frozenset(ROLE_PERMISSIONS) == ROLE_KEYS
    assert "viewer" in ROLE_KEYS
    assert "analytics.price_intelligence" in ENTITLEMENT_KEYS
    assert "delivery.sftp" in ENTITLEMENT_KEYS
