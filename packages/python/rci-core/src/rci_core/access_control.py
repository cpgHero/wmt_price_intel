"""Shared CPGHero account, role, permission, and entitlement primitives."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

PermissionKey = Literal[
    "users.manage",
    "roles.manage",
    "api_keys.manage",
    "projects.create",
    "projects.manage",
    "projects.approve_paid_run",
    "exports.download",
    "analytics.view",
    "analytics.share",
    "billing.view",
    "system.admin",
    "system.provider_admin",
    "system.governance",
]

EntitlementKey = Literal[
    "live_api",
    "bulk_projects",
    "app_analytics",
    "endpoint.search",
    "endpoint.product_detail",
    "endpoint.reviews",
    "analytics.price_intelligence",
    "analytics.competitive_intelligence",
    "analytics.share_of_search",
    "analytics.review_radar",
    "analytics.proximity",
    "delivery.app_download",
    "delivery.email",
    "delivery.sftp",
    "delivery.s3",
    "delivery.azure_blob",
]

ENTITLEMENT_KEYS: frozenset[EntitlementKey] = frozenset(
    {
        "live_api",
        "bulk_projects",
        "app_analytics",
        "endpoint.search",
        "endpoint.product_detail",
        "endpoint.reviews",
        "analytics.price_intelligence",
        "analytics.competitive_intelligence",
        "analytics.share_of_search",
        "analytics.review_radar",
        "analytics.proximity",
        "delivery.app_download",
        "delivery.email",
        "delivery.sftp",
        "delivery.s3",
        "delivery.azure_blob",
    }
)

RoleKey = Literal[
    "system_owner",
    "system_admin",
    "system_analyst",
    "account_owner",
    "account_admin",
    "project_owner",
    "analyst",
    "viewer",
    "developer",
    "billing_user",
]

RoleScope = Literal["system", "account", "workspace", "project"]

ROLE_PERMISSIONS: dict[RoleKey, frozenset[PermissionKey]] = {
    "system_owner": frozenset(
        {
            "system.admin",
            "system.provider_admin",
            "system.governance",
        }
    ),
    "system_admin": frozenset({"system.admin", "system.governance"}),
    "system_analyst": frozenset({"system.governance"}),
    "account_owner": frozenset(
        {
            "users.manage",
            "roles.manage",
            "api_keys.manage",
            "projects.create",
            "projects.manage",
            "projects.approve_paid_run",
            "exports.download",
            "analytics.view",
            "analytics.share",
            "billing.view",
        }
    ),
    "account_admin": frozenset(
        {
            "users.manage",
            "api_keys.manage",
            "projects.create",
            "projects.manage",
            "projects.approve_paid_run",
            "exports.download",
            "analytics.view",
            "analytics.share",
        }
    ),
    "project_owner": frozenset(
        {
            "projects.create",
            "projects.manage",
            "projects.approve_paid_run",
            "exports.download",
            "analytics.view",
            "analytics.share",
        }
    ),
    "analyst": frozenset({"exports.download", "analytics.view", "analytics.share"}),
    "viewer": frozenset({"analytics.view"}),
    "developer": frozenset({"api_keys.manage", "billing.view"}),
    "billing_user": frozenset({"billing.view"}),
}

ROLE_SCOPES: dict[RoleKey, RoleScope] = {
    "system_owner": "system",
    "system_admin": "system",
    "system_analyst": "system",
    "account_owner": "account",
    "account_admin": "account",
    "project_owner": "project",
    "analyst": "workspace",
    "viewer": "workspace",
    "developer": "account",
    "billing_user": "account",
}

ROLE_KEYS: frozenset[RoleKey] = frozenset(ROLE_PERMISSIONS.keys())


@dataclass(frozen=True, slots=True)
class AccessPrincipal:
    """Authenticated actor after identity-provider-specific login is resolved."""

    user_id: str
    email: str
    account_id: str | None = None
    workspace_id: str | None = None
    role_keys: frozenset[RoleKey] = field(default_factory=frozenset)
    entitlements: frozenset[EntitlementKey] = field(default_factory=frozenset)

    @property
    def permissions(self) -> frozenset[PermissionKey]:
        merged: set[PermissionKey] = set()
        for role_key in self.role_keys:
            merged.update(ROLE_PERMISSIONS[role_key])
        return frozenset(merged)

    @property
    def is_system_actor(self) -> bool:
        return any(ROLE_SCOPES[role_key] == "system" for role_key in self.role_keys)

    def has_permission(self, permission: PermissionKey) -> bool:
        return permission in self.permissions

    def require_permission(self, permission: PermissionKey) -> None:
        if not self.has_permission(permission):
            raise PermissionError(f"principal lacks required permission: {permission}")

    def has_entitlement(self, entitlement: EntitlementKey) -> bool:
        return entitlement in self.entitlements

    def require_entitlement(self, entitlement: EntitlementKey) -> None:
        if not self.has_entitlement(entitlement):
            raise PermissionError(f"principal lacks required entitlement: {entitlement}")
