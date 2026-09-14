"""Owner-only customer account provisioning and identity webhook endpoints."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from typing import Annotated, Any, Protocol, cast

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from workos import WorkOSClient

from rci_api.access import platform_admin_actor, require_platform_admin
from rci_core import ENTITLEMENT_KEYS, ROLE_KEYS, AccessPrincipal
from rci_core.access_control import ROLE_SCOPES, EntitlementKey, RoleKey

router = APIRouter(prefix="/api/v1")
webhook_router = APIRouter(prefix="/api/webhooks", tags=["customer-auth"])

DEFAULT_WORKSPACE_SLUG = "default"
DEFAULT_WORKSPACE_NAME = "Default workspace"
LEGACY_USER_ROLE = "viewer"
DEFAULT_ACCOUNT_ADMIN_ROLES: tuple[RoleKey, ...] = ("account_owner",)
CUSTOMER_ASSIGNABLE_ROLE_KEYS: frozenset[RoleKey] = frozenset(
    role_key for role_key, scope in ROLE_SCOPES.items() if scope != "system"
)


def _normalize_email(value: str) -> str:
    normalized = value.strip().lower()
    if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
        raise ValueError("email must be a valid email-like address")
    return normalized


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    slug = re.sub(r"-+", "-", slug)
    if len(slug) < 3:
        slug = f"{slug}-account".strip("-")
    return slug[:63].strip("-")


def _validate_role_keys(values: tuple[str, ...]) -> tuple[RoleKey, ...]:
    role_values = tuple(dict.fromkeys(value.strip() for value in values if value.strip()))
    invalid = sorted(set(role_values).difference(cast("frozenset[str]", ROLE_KEYS)))
    if invalid:
        raise ValueError(f"unknown role keys: {', '.join(invalid)}")
    system_roles = sorted(
        set(role_values).difference(cast("frozenset[str]", CUSTOMER_ASSIGNABLE_ROLE_KEYS))
    )
    if system_roles:
        raise ValueError(
            f"system roles cannot be assigned to customer accounts: {', '.join(system_roles)}"
        )
    if not role_values:
        raise ValueError("at least one role key is required")
    return tuple(cast("RoleKey", role) for role in role_values)


def _validate_entitlement_keys(values: tuple[str, ...]) -> tuple[EntitlementKey, ...]:
    entitlement_values = tuple(dict.fromkeys(value.strip() for value in values if value.strip()))
    invalid = sorted(set(entitlement_values).difference(cast("frozenset[str]", ENTITLEMENT_KEYS)))
    if invalid:
        raise ValueError(f"unknown entitlement keys: {', '.join(invalid)}")
    return tuple(cast("EntitlementKey", entitlement) for entitlement in entitlement_values)


def _event_data(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def _string_field(container: dict[str, Any], *names: str) -> str | None:
    for name in names:
        value = container.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _nested_string_field(container: dict[str, Any], *paths: tuple[str, ...]) -> str | None:
    for path in paths:
        value: Any = container
        for part in path:
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(part)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _workos_user_id_for_event(event_type: str, data: dict[str, Any]) -> str | None:
    explicit_user_id = _string_field(data, "user_id") or _nested_string_field(data, ("user", "id"))
    if explicit_user_id:
        return explicit_user_id
    data_id = _string_field(data, "id")
    if event_type in {"user.created", "user.updated"} and data_id and data_id.startswith("user_"):
        return data_id
    return None


def _workos_invitation_id_for_event(event_type: str, data: dict[str, Any]) -> str | None:
    explicit_invitation_id = _string_field(data, "invitation_id") or _nested_string_field(
        data,
        ("invitation", "id"),
    )
    if explicit_invitation_id:
        return explicit_invitation_id
    data_id = _string_field(data, "id")
    if event_type.startswith("invitation.") and data_id:
        return data_id
    if data_id and data_id.startswith("invitation_"):
        return data_id
    return None


class PrepareCustomerAccountRequest(BaseModel):
    account_display_name: str = Field(min_length=2, max_length=160)
    admin_email: str = Field(min_length=3, max_length=320)
    account_slug: str | None = Field(default=None, min_length=3, max_length=64)
    workspace_slug: str = Field(default=DEFAULT_WORKSPACE_SLUG, min_length=3, max_length=64)
    workspace_display_name: str = Field(
        default=DEFAULT_WORKSPACE_NAME, min_length=2, max_length=160
    )
    admin_display_name: str | None = Field(default=None, max_length=160)
    role_keys: tuple[RoleKey, ...] = DEFAULT_ACCOUNT_ADMIN_ROLES
    entitlement_keys: tuple[EntitlementKey, ...] = ()
    workos_organization_id: str | None = Field(default=None, max_length=200)
    workos_user_id: str | None = Field(default=None, max_length=200)
    activate_now: bool = False

    @field_validator("admin_email")
    @classmethod
    def normalize_admin_email(cls, value: str) -> str:
        return _normalize_email(value)

    @field_validator("account_slug", "workspace_slug")
    @classmethod
    def validate_slug(cls, value: str | None) -> str | None:
        if value is None:
            return value
        slug = _slugify(value)
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}[a-z0-9]", slug):
            raise ValueError("slug must contain lowercase letters, numbers, and hyphens")
        return slug

    @field_validator("role_keys")
    @classmethod
    def normalize_role_keys(cls, value: tuple[str, ...]) -> tuple[RoleKey, ...]:
        return _validate_role_keys(value)

    @field_validator("entitlement_keys")
    @classmethod
    def normalize_entitlement_keys(cls, value: tuple[str, ...]) -> tuple[EntitlementKey, ...]:
        return _validate_entitlement_keys(value)


class PrepareCustomerAccountResponse(BaseModel):
    schema_version: str = "1.0.0-customer-provisioning"
    account_id: str
    account_slug: str
    workspace_id: str
    workspace_slug: str
    user_id: str
    invitation_id: str
    invitation_status: str
    membership_status: str
    role_keys: tuple[str, ...]
    entitlement_keys: tuple[str, ...]
    external_organization_mapped: bool
    external_user_mapped: bool
    customer_auth_provider: str


class CustomerAuthCanaryStatus(BaseModel):
    enabled: bool
    configured: bool
    allowed_email_count: int
    allowed_domain_count: int


class CustomerAuthInvitationStatus(BaseModel):
    email: str
    account_slug: str
    account_display_name: str
    workspace_slug: str | None = None
    workspace_display_name: str | None = None
    invitation_status: str
    account_membership_status: str | None = None
    workspace_membership_status: str | None = None
    role_keys: tuple[str, ...] = ()
    entitlement_keys: tuple[str, ...] = ()
    has_external_user_mapping: bool
    has_external_organization_mapping: bool
    has_workos_invitation: bool
    accepted: bool
    prepared_at: str
    updated_at: str


class CustomerAuthWebhookEventStatus(BaseModel):
    event_type: str
    processing_status: str
    email_snapshot: str | None = None
    has_workos_user: bool
    has_workos_organization: bool
    has_workos_invitation: bool
    processed: bool
    received_at: str
    processed_at: str | None = None


class CustomerAuthReadinessResponse(BaseModel):
    schema_version: str = "1.0.0-customer-auth-readiness"
    customer_auth_provider: str
    customer_login_enabled: bool
    canary: CustomerAuthCanaryStatus
    cutover_ready: bool
    blockers: tuple[str, ...]
    invitations: tuple[CustomerAuthInvitationStatus, ...]
    recent_webhook_events: tuple[CustomerAuthWebhookEventStatus, ...]


class CustomerAccountFoundationSummary(BaseModel):
    accounts: int
    customer_accounts: int
    active_accounts: int
    workspaces: int
    active_workspaces: int
    members: int
    active_members: int
    entitlements: int
    active_entitlements: int
    active_report_grants: int


class CustomerAccountFoundationAccount(BaseModel):
    account_id: str
    account_slug: str
    account_display_name: str
    account_type: str
    account_status: str
    workspace_count: int
    member_count: int
    active_member_count: int
    entitlement_count: int
    active_entitlement_count: int
    active_report_grant_count: int
    revoked_report_grant_count: int
    has_identity_provider_organization_binding: bool
    created_at: str


class CustomerAccountFoundationWorkspace(BaseModel):
    workspace_id: str
    account_id: str
    account_slug: str
    account_display_name: str
    workspace_slug: str
    workspace_display_name: str
    workspace_status: str
    active_member_count: int
    active_report_grant_count: int
    revoked_report_grant_count: int
    created_at: str


class CustomerAccountFoundationMember(BaseModel):
    user_id: str
    email: str
    display_name: str | None = None
    account_id: str
    account_slug: str
    account_display_name: str
    account_membership_status: str
    workspace_slug: str | None = None
    workspace_display_name: str | None = None
    workspace_membership_status: str | None = None
    account_role_keys: tuple[str, ...] = ()
    workspace_role_keys: tuple[str, ...] = ()
    has_identity_provider_user_binding: bool
    created_at: str


class CustomerAccountFoundationEntitlement(BaseModel):
    account_id: str
    account_slug: str
    account_display_name: str
    entitlement_key: str
    entitlement_status: str
    starts_at: str | None = None
    expires_at: str | None = None
    created_at: str


class CustomerAccountFoundationResponse(BaseModel):
    schema_version: str = "1.0.0-customer-account-foundation"
    summary: CustomerAccountFoundationSummary
    accounts: tuple[CustomerAccountFoundationAccount, ...]
    workspaces: tuple[CustomerAccountFoundationWorkspace, ...]
    members: tuple[CustomerAccountFoundationMember, ...]
    entitlements: tuple[CustomerAccountFoundationEntitlement, ...]


@dataclass(frozen=True, slots=True)
class WebhookProcessingResult:
    event_id: str
    event_type: str
    processing_status: str


class CustomerProvisioningRepository(Protocol):
    async def prepare_customer_account(
        self,
        request: PrepareCustomerAccountRequest,
        *,
        prepared_by: AccessPrincipal,
    ) -> PrepareCustomerAccountResponse: ...

    async def record_identity_webhook(
        self,
        *,
        payload: dict[str, Any],
        payload_sha256: str,
    ) -> WebhookProcessingResult: ...

    async def customer_auth_readiness(
        self,
        *,
        email: str | None = None,
        limit: int = 25,
    ) -> CustomerAuthReadinessResponse: ...

    async def customer_account_foundation(
        self,
        *,
        account_slug: str | None = None,
        limit: int = 50,
    ) -> CustomerAccountFoundationResponse: ...


class PostgresCustomerProvisioningRepository:
    """Provision CPGHero-owned access rows before customer login is enabled."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def customer_account_foundation(
        self,
        *,
        account_slug: str | None = None,
        limit: int = 50,
    ) -> CustomerAccountFoundationResponse:
        normalized_slug = _slugify(account_slug) if account_slug else None
        safe_limit = max(1, min(limit, 200))
        async with self._engine.begin() as connection:
            summary = await self._customer_account_foundation_summary(
                connection,
                account_slug=normalized_slug,
            )
            accounts = await self._customer_account_foundation_accounts(
                connection,
                account_slug=normalized_slug,
                limit=safe_limit,
            )
            workspaces = await self._customer_account_foundation_workspaces(
                connection,
                account_slug=normalized_slug,
                limit=safe_limit,
            )
            members = await self._customer_account_foundation_members(
                connection,
                account_slug=normalized_slug,
                limit=safe_limit,
            )
            entitlements = await self._customer_account_foundation_entitlements(
                connection,
                account_slug=normalized_slug,
                limit=safe_limit,
            )
        return CustomerAccountFoundationResponse(
            summary=summary,
            accounts=tuple(accounts),
            workspaces=tuple(workspaces),
            members=tuple(members),
            entitlements=tuple(entitlements),
        )

    async def _customer_account_foundation_summary(
        self,
        connection: AsyncConnection,
        *,
        account_slug: str | None,
    ) -> CustomerAccountFoundationSummary:
        row = (
            (
                await connection.execute(
                    text(
                        """
                        SELECT
                          COUNT(*)::integer AS accounts,
                          COUNT(*) FILTER (WHERE account_type = 'customer')::integer
                            AS customer_accounts,
                          COUNT(*) FILTER (WHERE status = 'active')::integer
                            AS active_accounts,
                          (
                            SELECT COUNT(*)::integer
                            FROM workspace
                            JOIN account ON account.id = workspace.account_id
                            WHERE (
                              CAST(:account_slug AS text) IS NULL
                              OR account.slug = CAST(:account_slug AS text)
                            )
                          ) AS workspaces,
                          (
                            SELECT COUNT(*)::integer
                            FROM workspace
                            JOIN account ON account.id = workspace.account_id
                            WHERE workspace.status = 'active'
                              AND (
                                CAST(:account_slug AS text) IS NULL
                                OR account.slug = CAST(:account_slug AS text)
                              )
                          ) AS active_workspaces,
                          (
                            SELECT COUNT(*)::integer
                            FROM account_membership
                            JOIN account ON account.id = account_membership.account_id
                            WHERE (
                              CAST(:account_slug AS text) IS NULL
                              OR account.slug = CAST(:account_slug AS text)
                            )
                          ) AS members,
                          (
                            SELECT COUNT(*)::integer
                            FROM account_membership
                            JOIN account ON account.id = account_membership.account_id
                            WHERE account_membership.status = 'active'
                              AND (
                                CAST(:account_slug AS text) IS NULL
                                OR account.slug = CAST(:account_slug AS text)
                              )
                          ) AS active_members,
                          (
                            SELECT COUNT(*)::integer
                            FROM account_entitlement
                            JOIN account ON account.id = account_entitlement.account_id
                            WHERE (
                              CAST(:account_slug AS text) IS NULL
                              OR account.slug = CAST(:account_slug AS text)
                            )
                          ) AS entitlements,
                          (
                            SELECT COUNT(*)::integer
                            FROM account_entitlement
                            JOIN account ON account.id = account_entitlement.account_id
                            WHERE account_entitlement.status = 'active'
                              AND (
                                CAST(:account_slug AS text) IS NULL
                                OR account.slug = CAST(:account_slug AS text)
                              )
                          ) AS active_entitlements,
                          (
                            SELECT COUNT(*)::integer
                            FROM customer_report_access
                            JOIN account ON account.id = customer_report_access.account_id
                            WHERE customer_report_access.status = 'active'
                              AND (
                                CAST(:account_slug AS text) IS NULL
                                OR account.slug = CAST(:account_slug AS text)
                              )
                          ) AS active_report_grants
                        FROM account
                        WHERE (
                          CAST(:account_slug AS text) IS NULL
                          OR slug = CAST(:account_slug AS text)
                        )
                        """
                    ),
                    {"account_slug": account_slug},
                )
            )
            .mappings()
            .one()
        )
        return CustomerAccountFoundationSummary(
            accounts=int(row["accounts"] or 0),
            customer_accounts=int(row["customer_accounts"] or 0),
            active_accounts=int(row["active_accounts"] or 0),
            workspaces=int(row["workspaces"] or 0),
            active_workspaces=int(row["active_workspaces"] or 0),
            members=int(row["members"] or 0),
            active_members=int(row["active_members"] or 0),
            entitlements=int(row["entitlements"] or 0),
            active_entitlements=int(row["active_entitlements"] or 0),
            active_report_grants=int(row["active_report_grants"] or 0),
        )

    async def _customer_account_foundation_accounts(
        self,
        connection: AsyncConnection,
        *,
        account_slug: str | None,
        limit: int,
    ) -> list[CustomerAccountFoundationAccount]:
        rows = (
            (
                await connection.execute(
                    text(
                        """
                        SELECT
                          account.id::text AS account_id,
                          account.slug AS account_slug,
                          account.display_name AS account_display_name,
                          account.account_type,
                          account.status AS account_status,
                          COALESCE(workspace_counts.workspace_count, 0)::integer
                            AS workspace_count,
                          COALESCE(member_counts.member_count, 0)::integer AS member_count,
                          COALESCE(member_counts.active_member_count, 0)::integer
                            AS active_member_count,
                          COALESCE(entitlement_counts.entitlement_count, 0)::integer
                            AS entitlement_count,
                          COALESCE(entitlement_counts.active_entitlement_count, 0)::integer
                            AS active_entitlement_count,
                          COALESCE(report_counts.active_report_grant_count, 0)::integer
                            AS active_report_grant_count,
                          COALESCE(report_counts.revoked_report_grant_count, 0)::integer
                            AS revoked_report_grant_count,
                          external_identity.id IS NOT NULL
                            AS has_identity_provider_organization_binding,
                          account.created_at::text AS created_at
                        FROM account
                        LEFT JOIN (
                          SELECT account_id, COUNT(*) AS workspace_count
                          FROM workspace
                          GROUP BY account_id
                        ) workspace_counts ON workspace_counts.account_id = account.id
                        LEFT JOIN (
                          SELECT
                            account_id,
                            COUNT(*) AS member_count,
                            COUNT(*) FILTER (WHERE status = 'active') AS active_member_count
                          FROM account_membership
                          GROUP BY account_id
                        ) member_counts ON member_counts.account_id = account.id
                        LEFT JOIN (
                          SELECT
                            account_id,
                            COUNT(*) AS entitlement_count,
                            COUNT(*) FILTER (WHERE status = 'active')
                              AS active_entitlement_count
                          FROM account_entitlement
                          GROUP BY account_id
                        ) entitlement_counts ON entitlement_counts.account_id = account.id
                        LEFT JOIN (
                          SELECT
                            account_id,
                            COUNT(*) FILTER (WHERE status = 'active')
                              AS active_report_grant_count,
                            COUNT(*) FILTER (WHERE status = 'revoked')
                              AS revoked_report_grant_count
                          FROM customer_report_access
                          GROUP BY account_id
                        ) report_counts ON report_counts.account_id = account.id
                        LEFT JOIN external_identity
                          ON external_identity.provider = 'workos'
                         AND external_identity.subject_type = 'organization'
                         AND external_identity.account_id = account.id
                        WHERE (
                          CAST(:account_slug AS text) IS NULL
                          OR account.slug = CAST(:account_slug AS text)
                        )
                        ORDER BY account.created_at DESC, account.display_name ASC
                        LIMIT :limit
                        """
                    ),
                    {"account_slug": account_slug, "limit": limit},
                )
            )
            .mappings()
            .all()
        )
        return [
            CustomerAccountFoundationAccount(
                account_id=str(row["account_id"]),
                account_slug=str(row["account_slug"]),
                account_display_name=str(row["account_display_name"]),
                account_type=str(row["account_type"]),
                account_status=str(row["account_status"]),
                workspace_count=int(row["workspace_count"] or 0),
                member_count=int(row["member_count"] or 0),
                active_member_count=int(row["active_member_count"] or 0),
                entitlement_count=int(row["entitlement_count"] or 0),
                active_entitlement_count=int(row["active_entitlement_count"] or 0),
                active_report_grant_count=int(row["active_report_grant_count"] or 0),
                revoked_report_grant_count=int(row["revoked_report_grant_count"] or 0),
                has_identity_provider_organization_binding=bool(
                    row["has_identity_provider_organization_binding"]
                ),
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

    async def _customer_account_foundation_workspaces(
        self,
        connection: AsyncConnection,
        *,
        account_slug: str | None,
        limit: int,
    ) -> list[CustomerAccountFoundationWorkspace]:
        rows = (
            (
                await connection.execute(
                    text(
                        """
                        SELECT
                          workspace.id::text AS workspace_id,
                          account.id::text AS account_id,
                          account.slug AS account_slug,
                          account.display_name AS account_display_name,
                          workspace.slug AS workspace_slug,
                          workspace.display_name AS workspace_display_name,
                          workspace.status AS workspace_status,
                          COALESCE(member_counts.active_member_count, 0)::integer
                            AS active_member_count,
                          COALESCE(report_counts.active_report_grant_count, 0)::integer
                            AS active_report_grant_count,
                          COALESCE(report_counts.revoked_report_grant_count, 0)::integer
                            AS revoked_report_grant_count,
                          workspace.created_at::text AS created_at
                        FROM workspace
                        JOIN account ON account.id = workspace.account_id
                        LEFT JOIN (
                          SELECT
                            workspace_id,
                            COUNT(*) FILTER (WHERE status = 'active')
                              AS active_member_count
                          FROM workspace_membership
                          GROUP BY workspace_id
                        ) member_counts ON member_counts.workspace_id = workspace.id
                        LEFT JOIN (
                          SELECT
                            workspace_id,
                            COUNT(*) FILTER (WHERE status = 'active')
                              AS active_report_grant_count,
                            COUNT(*) FILTER (WHERE status = 'revoked')
                              AS revoked_report_grant_count
                          FROM customer_report_access
                          WHERE workspace_id IS NOT NULL
                          GROUP BY workspace_id
                        ) report_counts ON report_counts.workspace_id = workspace.id
                        WHERE (
                          CAST(:account_slug AS text) IS NULL
                          OR account.slug = CAST(:account_slug AS text)
                        )
                        ORDER BY workspace.created_at DESC, account.display_name ASC
                        LIMIT :limit
                        """
                    ),
                    {"account_slug": account_slug, "limit": limit},
                )
            )
            .mappings()
            .all()
        )
        return [
            CustomerAccountFoundationWorkspace(
                workspace_id=str(row["workspace_id"]),
                account_id=str(row["account_id"]),
                account_slug=str(row["account_slug"]),
                account_display_name=str(row["account_display_name"]),
                workspace_slug=str(row["workspace_slug"]),
                workspace_display_name=str(row["workspace_display_name"]),
                workspace_status=str(row["workspace_status"]),
                active_member_count=int(row["active_member_count"] or 0),
                active_report_grant_count=int(row["active_report_grant_count"] or 0),
                revoked_report_grant_count=int(row["revoked_report_grant_count"] or 0),
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

    async def _customer_account_foundation_members(
        self,
        connection: AsyncConnection,
        *,
        account_slug: str | None,
        limit: int,
    ) -> list[CustomerAccountFoundationMember]:
        rows = (
            (
                await connection.execute(
                    text(
                        """
                        SELECT
                          app_user.id::text AS user_id,
                          app_user.email,
                          app_user.display_name,
                          account.id::text AS account_id,
                          account.slug AS account_slug,
                          account.display_name AS account_display_name,
                          account_membership.status AS account_membership_status,
                          workspace.slug AS workspace_slug,
                          workspace.display_name AS workspace_display_name,
                          workspace_membership.status AS workspace_membership_status,
                          COALESCE(account_roles.role_keys, ARRAY[]::text[])
                            AS account_role_keys,
                          COALESCE(workspace_roles.role_keys, ARRAY[]::text[])
                            AS workspace_role_keys,
                          external_identity.id IS NOT NULL
                            AS has_identity_provider_user_binding,
                          account_membership.created_at::text AS created_at
                        FROM account_membership
                        JOIN account ON account.id = account_membership.account_id
                        JOIN app_user ON app_user.id = account_membership.user_id
                        LEFT JOIN workspace_membership
                          ON workspace_membership.account_membership_id = account_membership.id
                        LEFT JOIN workspace ON workspace.id = workspace_membership.workspace_id
                        LEFT JOIN (
                          SELECT
                            account_membership_role.account_membership_id,
                            ARRAY_AGG(platform_role.role_key ORDER BY platform_role.role_key)
                              AS role_keys
                          FROM account_membership_role
                          JOIN platform_role ON platform_role.id = account_membership_role.role_id
                          GROUP BY account_membership_role.account_membership_id
                        ) account_roles
                          ON account_roles.account_membership_id = account_membership.id
                        LEFT JOIN (
                          SELECT
                            workspace_membership_role.workspace_membership_id,
                            ARRAY_AGG(platform_role.role_key ORDER BY platform_role.role_key)
                              AS role_keys
                          FROM workspace_membership_role
                          JOIN platform_role ON platform_role.id = workspace_membership_role.role_id
                          GROUP BY workspace_membership_role.workspace_membership_id
                        ) workspace_roles
                          ON workspace_roles.workspace_membership_id = workspace_membership.id
                        LEFT JOIN external_identity
                          ON external_identity.provider = 'workos'
                         AND external_identity.subject_type = 'user'
                         AND external_identity.user_id = app_user.id
                        WHERE (
                          CAST(:account_slug AS text) IS NULL
                          OR account.slug = CAST(:account_slug AS text)
                        )
                        ORDER BY account_membership.created_at DESC, app_user.email ASC
                        LIMIT :limit
                        """
                    ),
                    {"account_slug": account_slug, "limit": limit},
                )
            )
            .mappings()
            .all()
        )
        return [
            CustomerAccountFoundationMember(
                user_id=str(row["user_id"]),
                email=str(row["email"]),
                display_name=str(row["display_name"]) if row["display_name"] else None,
                account_id=str(row["account_id"]),
                account_slug=str(row["account_slug"]),
                account_display_name=str(row["account_display_name"]),
                account_membership_status=str(row["account_membership_status"]),
                workspace_slug=str(row["workspace_slug"]) if row["workspace_slug"] else None,
                workspace_display_name=(
                    str(row["workspace_display_name"]) if row["workspace_display_name"] else None
                ),
                workspace_membership_status=(
                    str(row["workspace_membership_status"])
                    if row["workspace_membership_status"]
                    else None
                ),
                account_role_keys=tuple(str(value) for value in row["account_role_keys"] or []),
                workspace_role_keys=tuple(str(value) for value in row["workspace_role_keys"] or []),
                has_identity_provider_user_binding=bool(row["has_identity_provider_user_binding"]),
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

    async def _customer_account_foundation_entitlements(
        self,
        connection: AsyncConnection,
        *,
        account_slug: str | None,
        limit: int,
    ) -> list[CustomerAccountFoundationEntitlement]:
        rows = (
            (
                await connection.execute(
                    text(
                        """
                        SELECT
                          account.id::text AS account_id,
                          account.slug AS account_slug,
                          account.display_name AS account_display_name,
                          account_entitlement.entitlement_key,
                          account_entitlement.status AS entitlement_status,
                          account_entitlement.starts_at::text AS starts_at,
                          account_entitlement.expires_at::text AS expires_at,
                          account_entitlement.created_at::text AS created_at
                        FROM account_entitlement
                        JOIN account ON account.id = account_entitlement.account_id
                        WHERE (
                          CAST(:account_slug AS text) IS NULL
                          OR account.slug = CAST(:account_slug AS text)
                        )
                        ORDER BY account_entitlement.created_at DESC,
                                 account_entitlement.entitlement_key ASC
                        LIMIT :limit
                        """
                    ),
                    {"account_slug": account_slug, "limit": limit},
                )
            )
            .mappings()
            .all()
        )
        return [
            CustomerAccountFoundationEntitlement(
                account_id=str(row["account_id"]),
                account_slug=str(row["account_slug"]),
                account_display_name=str(row["account_display_name"]),
                entitlement_key=str(row["entitlement_key"]),
                entitlement_status=str(row["entitlement_status"]),
                starts_at=str(row["starts_at"]) if row["starts_at"] else None,
                expires_at=str(row["expires_at"]) if row["expires_at"] else None,
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

    async def customer_auth_readiness(
        self,
        *,
        email: str | None = None,
        limit: int = 25,
    ) -> CustomerAuthReadinessResponse:
        normalized_email = _normalize_email(email) if email else None
        safe_limit = max(1, min(limit, 100))
        async with self._engine.begin() as connection:
            invitations = await self._customer_auth_invitation_statuses(
                connection,
                email=normalized_email,
                limit=safe_limit,
            )
            events = await self._customer_auth_webhook_event_statuses(
                connection,
                email=normalized_email,
                limit=safe_limit,
            )
        canary = self._canary_status()
        provider = os.getenv("CPGHERO_CUSTOMER_AUTH_PROVIDER", "disabled").strip().lower()
        blockers = self._customer_auth_blockers(
            provider=provider,
            canary=canary,
            invitations=invitations,
        )
        return CustomerAuthReadinessResponse(
            customer_auth_provider=provider,
            customer_login_enabled=provider == "workos",
            canary=canary,
            cutover_ready=not blockers,
            blockers=tuple(blockers),
            invitations=tuple(invitations),
            recent_webhook_events=tuple(events),
        )

    def _canary_status(self) -> CustomerAuthCanaryStatus:
        canary_enabled = os.getenv(
            "CPGHERO_CUSTOMER_AUTH_CANARY_ENABLED", "true"
        ).strip().lower() not in {"0", "false", "disabled", "no", "off"}
        allowed_email_count = len(
            [
                part
                for part in os.getenv("CPGHERO_CUSTOMER_AUTH_ALLOWED_EMAILS", "").split(",")
                if part.strip()
            ]
        )
        allowed_domain_count = len(
            [
                part
                for part in os.getenv("CPGHERO_CUSTOMER_AUTH_ALLOWED_DOMAINS", "").split(",")
                if part.strip()
            ]
        )
        return CustomerAuthCanaryStatus(
            enabled=canary_enabled,
            configured=(not canary_enabled) or bool(allowed_email_count or allowed_domain_count),
            allowed_email_count=allowed_email_count,
            allowed_domain_count=allowed_domain_count,
        )

    def _customer_auth_blockers(
        self,
        *,
        provider: str,
        canary: CustomerAuthCanaryStatus,
        invitations: list[CustomerAuthInvitationStatus],
    ) -> list[str]:
        blockers: list[str] = []
        if provider != "workos":
            blockers.append("Production customer login is still disabled.")
        if canary.enabled and not canary.configured:
            blockers.append("Customer login canary is enabled without an allowlist.")
        if not invitations:
            blockers.append("No prepared customer invitations are visible for this check.")
        if not any(invitation.has_external_user_mapping for invitation in invitations):
            blockers.append("No invited user has a verified identity-provider user binding yet.")
        if not any(
            invitation.accepted or invitation.account_membership_status == "active"
            for invitation in invitations
        ):
            blockers.append(
                "No invited user has accepted access or active CPGHero account membership yet."
            )
        if not any(
            invitation.workspace_membership_status in {None, "active"} for invitation in invitations
        ):
            blockers.append("No invited user has active CPGHero workspace access yet.")
        return blockers

    async def _customer_auth_invitation_statuses(
        self,
        connection: AsyncConnection,
        *,
        email: str | None,
        limit: int,
    ) -> list[CustomerAuthInvitationStatus]:
        rows = (
            (
                await connection.execute(
                    text(
                        """
                        SELECT
                          invitation.email,
                          account.slug AS account_slug,
                          account.display_name AS account_display_name,
                          workspace.slug AS workspace_slug,
                          workspace.display_name AS workspace_display_name,
                          invitation.status AS invitation_status,
                          account_membership.status AS account_membership_status,
                          workspace_membership.status AS workspace_membership_status,
                          invitation.role_keys,
                          invitation.entitlement_keys,
                          invitation.workos_user_id IS NOT NULL AS has_external_user_mapping,
                          invitation.workos_organization_id IS NOT NULL
                            AS has_external_organization_mapping,
                          invitation.workos_invitation_id IS NOT NULL AS has_workos_invitation,
                          invitation.accepted_at IS NOT NULL AS accepted,
                          invitation.created_at::text AS prepared_at,
                          invitation.updated_at::text AS updated_at
                        FROM customer_account_invitation invitation
                        JOIN account ON account.id = invitation.account_id
                        LEFT JOIN workspace ON workspace.id = invitation.workspace_id
                        LEFT JOIN account_membership
                          ON account_membership.account_id = invitation.account_id
                         AND account_membership.user_id = invitation.user_id
                        LEFT JOIN workspace_membership
                          ON workspace_membership.workspace_id = invitation.workspace_id
                         AND workspace_membership.account_membership_id = account_membership.id
                        WHERE (
                          CAST(:email AS text) IS NULL
                          OR invitation.email = CAST(:email AS text)
                        )
                        ORDER BY invitation.updated_at DESC, invitation.created_at DESC
                        LIMIT :limit
                        """
                    ),
                    {"email": email, "limit": limit},
                )
            )
            .mappings()
            .all()
        )
        return [
            CustomerAuthInvitationStatus(
                email=str(row["email"]),
                account_slug=str(row["account_slug"]),
                account_display_name=str(row["account_display_name"]),
                workspace_slug=str(row["workspace_slug"]) if row["workspace_slug"] else None,
                workspace_display_name=(
                    str(row["workspace_display_name"]) if row["workspace_display_name"] else None
                ),
                invitation_status=str(row["invitation_status"]),
                account_membership_status=(
                    str(row["account_membership_status"])
                    if row["account_membership_status"]
                    else None
                ),
                workspace_membership_status=(
                    str(row["workspace_membership_status"])
                    if row["workspace_membership_status"]
                    else None
                ),
                role_keys=tuple(str(value) for value in row["role_keys"] or []),
                entitlement_keys=tuple(str(value) for value in row["entitlement_keys"] or []),
                has_external_user_mapping=bool(row["has_external_user_mapping"]),
                has_external_organization_mapping=bool(row["has_external_organization_mapping"]),
                has_workos_invitation=bool(row["has_workos_invitation"]),
                accepted=bool(row["accepted"]),
                prepared_at=str(row["prepared_at"]),
                updated_at=str(row["updated_at"]),
            )
            for row in rows
        ]

    async def _customer_auth_webhook_event_statuses(
        self,
        connection: AsyncConnection,
        *,
        email: str | None,
        limit: int,
    ) -> list[CustomerAuthWebhookEventStatus]:
        rows = (
            (
                await connection.execute(
                    text(
                        """
                        SELECT
                          event_type,
                          processing_status,
                          email_snapshot,
                          workos_user_id IS NOT NULL AS has_workos_user,
                          workos_organization_id IS NOT NULL AS has_workos_organization,
                          workos_invitation_id IS NOT NULL AS has_workos_invitation,
                          processed_at IS NOT NULL AS processed,
                          received_at::text AS received_at,
                          processed_at::text AS processed_at
                        FROM customer_identity_webhook_event
                        WHERE (
                          CAST(:email AS text) IS NULL
                          OR email_snapshot = CAST(:email AS text)
                        )
                        ORDER BY received_at DESC
                        LIMIT :limit
                        """
                    ),
                    {"email": email, "limit": limit},
                )
            )
            .mappings()
            .all()
        )
        return [
            CustomerAuthWebhookEventStatus(
                event_type=str(row["event_type"]),
                processing_status=str(row["processing_status"]),
                email_snapshot=str(row["email_snapshot"]) if row["email_snapshot"] else None,
                has_workos_user=bool(row["has_workos_user"]),
                has_workos_organization=bool(row["has_workos_organization"]),
                has_workos_invitation=bool(row["has_workos_invitation"]),
                processed=bool(row["processed"]),
                received_at=str(row["received_at"]),
                processed_at=str(row["processed_at"]) if row["processed_at"] else None,
            )
            for row in rows
        ]

    async def prepare_customer_account(
        self,
        request: PrepareCustomerAccountRequest,
        *,
        prepared_by: AccessPrincipal,
    ) -> PrepareCustomerAccountResponse:
        account_slug = request.account_slug or _slugify(request.account_display_name)
        membership_status = (
            "active" if request.activate_now and request.workos_user_id else "invited"
        )
        invitation_status = "accepted" if membership_status == "active" else "prepared"
        async with self._engine.begin() as connection:
            account_row = await self._get_or_create_account(
                connection,
                slug=account_slug,
                display_name=request.account_display_name,
            )
            workspace_row = await self._get_or_create_workspace(
                connection,
                account_id=str(account_row["account_id"]),
                slug=request.workspace_slug,
                display_name=request.workspace_display_name,
            )
            user_row = await self._get_or_create_user(
                connection,
                organization_id=str(account_row["organization_id"]),
                email=request.admin_email,
                display_name=request.admin_display_name,
            )
            membership_id = await self._upsert_account_membership(
                connection,
                account_id=str(account_row["account_id"]),
                user_id=str(user_row["user_id"]),
                status_value=membership_status,
            )
            workspace_membership_id = await self._upsert_workspace_membership(
                connection,
                workspace_id=str(workspace_row["workspace_id"]),
                account_membership_id=membership_id,
                status_value=membership_status,
            )
            await self._assign_roles(
                connection,
                account_id=str(account_row["account_id"]),
                membership_id=membership_id,
                workspace_membership_id=workspace_membership_id,
                role_keys=request.role_keys,
            )
            await self._grant_entitlements(
                connection,
                account_id=str(account_row["account_id"]),
                entitlement_keys=request.entitlement_keys,
                granted_by=None if prepared_by.is_system_actor else prepared_by.user_id,
            )
            if request.workos_organization_id:
                await self._upsert_external_identity(
                    connection,
                    subject_type="organization",
                    subject_id=request.workos_organization_id,
                    account_id=str(account_row["account_id"]),
                    user_id=None,
                    email_snapshot=None,
                )
            if request.workos_user_id:
                await self._upsert_external_identity(
                    connection,
                    subject_type="user",
                    subject_id=request.workos_user_id,
                    account_id=None,
                    user_id=str(user_row["user_id"]),
                    email_snapshot=request.admin_email,
                )
            invitation_row = (
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO customer_account_invitation (
                              account_id,
                              workspace_id,
                              user_id,
                              email,
                              display_name,
                              status,
                              role_keys,
                              entitlement_keys,
                              workos_organization_id,
                              workos_user_id,
                              metadata,
                              accepted_at,
                              updated_at
                            )
                            VALUES (
                              CAST(:account_id AS uuid),
                              CAST(:workspace_id AS uuid),
                              CAST(:user_id AS uuid),
                              :email,
                              :display_name,
                              :status,
                              CAST(:role_keys AS text[]),
                              CAST(:entitlement_keys AS text[]),
                              :workos_organization_id,
                              :workos_user_id,
                              CAST(:metadata AS jsonb),
                              CASE WHEN :status = 'accepted' THEN now() ELSE NULL END,
                              now()
                            )
                            ON CONFLICT (account_id, email) DO UPDATE
                            SET workspace_id = EXCLUDED.workspace_id,
                                user_id = EXCLUDED.user_id,
                                display_name = EXCLUDED.display_name,
                                status = EXCLUDED.status,
                                role_keys = EXCLUDED.role_keys,
                                entitlement_keys = EXCLUDED.entitlement_keys,
                                workos_organization_id = COALESCE(
                                  EXCLUDED.workos_organization_id,
                                  customer_account_invitation.workos_organization_id
                                ),
                                workos_user_id = COALESCE(
                                  EXCLUDED.workos_user_id,
                                  customer_account_invitation.workos_user_id
                                ),
                                metadata = (
                                  customer_account_invitation.metadata || EXCLUDED.metadata
                                ),
                                accepted_at = COALESCE(
                                  customer_account_invitation.accepted_at,
                                  EXCLUDED.accepted_at
                                ),
                                updated_at = now()
                            RETURNING id::text AS invitation_id, status
                            """
                        ),
                        {
                            "account_id": str(account_row["account_id"]),
                            "workspace_id": str(workspace_row["workspace_id"]),
                            "user_id": str(user_row["user_id"]),
                            "email": request.admin_email,
                            "display_name": request.admin_display_name,
                            "status": invitation_status,
                            "role_keys": list(request.role_keys),
                            "entitlement_keys": list(request.entitlement_keys),
                            "workos_organization_id": request.workos_organization_id,
                            "workos_user_id": request.workos_user_id,
                            "metadata": json.dumps(
                                {
                                    "prepared_by": platform_admin_actor(prepared_by),
                                    "source": "admin_customer_provisioning_api",
                                }
                            ),
                        },
                    )
                )
                .mappings()
                .one()
            )

        return PrepareCustomerAccountResponse(
            account_id=str(account_row["account_id"]),
            account_slug=account_slug,
            workspace_id=str(workspace_row["workspace_id"]),
            workspace_slug=request.workspace_slug,
            user_id=str(user_row["user_id"]),
            invitation_id=str(invitation_row["invitation_id"]),
            invitation_status=str(invitation_row["status"]),
            membership_status=membership_status,
            role_keys=tuple(request.role_keys),
            entitlement_keys=tuple(request.entitlement_keys),
            external_organization_mapped=bool(request.workos_organization_id),
            external_user_mapped=bool(request.workos_user_id),
            customer_auth_provider="cpghero",
        )

    async def _get_or_create_account(
        self,
        connection: AsyncConnection,
        *,
        slug: str,
        display_name: str,
    ) -> dict[str, Any]:
        row = (
            (
                await connection.execute(
                    text(
                        """
                        SELECT id::text AS account_id, organization_id::text AS organization_id
                        FROM account
                        WHERE slug = :slug
                        """
                    ),
                    {"slug": slug},
                )
            )
            .mappings()
            .first()
        )
        if row:
            return dict(row)
        organization_id = (
            (
                await connection.execute(
                    text(
                        """
                        INSERT INTO organization (name)
                        VALUES (:name)
                        RETURNING id::text AS organization_id
                        """
                    ),
                    {"name": display_name},
                )
            )
            .mappings()
            .one()
        )["organization_id"]
        account = (
            (
                await connection.execute(
                    text(
                        """
                        INSERT INTO account (
                          organization_id, slug, display_name, account_type, metadata
                        )
                        VALUES (
                          CAST(:organization_id AS uuid),
                          :slug,
                          :display_name,
                          'customer',
                          CAST(:metadata AS jsonb)
                        )
                        RETURNING id::text AS account_id, organization_id::text AS organization_id
                        """
                    ),
                    {
                        "organization_id": str(organization_id),
                        "slug": slug,
                        "display_name": display_name,
                        "metadata": json.dumps({"source": "admin_customer_provisioning_api"}),
                    },
                )
            )
            .mappings()
            .one()
        )
        return dict(account)

    async def _get_or_create_workspace(
        self,
        connection: AsyncConnection,
        *,
        account_id: str,
        slug: str,
        display_name: str,
    ) -> dict[str, Any]:
        return dict(
            (
                await connection.execute(
                    text(
                        """
                            INSERT INTO workspace (account_id, slug, display_name, metadata)
                            VALUES (
                              CAST(:account_id AS uuid),
                              :slug,
                              :display_name,
                              CAST(:metadata AS jsonb)
                            )
                            ON CONFLICT (account_id, slug) DO UPDATE
                            SET display_name = EXCLUDED.display_name,
                                updated_at = now()
                            RETURNING id::text AS workspace_id, slug
                            """
                    ),
                    {
                        "account_id": account_id,
                        "slug": slug,
                        "display_name": display_name,
                        "metadata": json.dumps({"source": "admin_customer_provisioning_api"}),
                    },
                )
            )
            .mappings()
            .one()
        )

    async def _get_or_create_user(
        self,
        connection: AsyncConnection,
        *,
        organization_id: str,
        email: str,
        display_name: str | None,
    ) -> dict[str, Any]:
        return dict(
            (
                await connection.execute(
                    text(
                        """
                            INSERT INTO app_user (organization_id, email, display_name, role)
                            VALUES (
                              CAST(:organization_id AS uuid),
                              :email,
                              :display_name,
                              :role
                            )
                            ON CONFLICT (email) DO UPDATE
                            SET display_name = COALESCE(
                              EXCLUDED.display_name,
                              app_user.display_name
                            )
                            RETURNING id::text AS user_id, email
                            """
                    ),
                    {
                        "organization_id": organization_id,
                        "email": email,
                        "display_name": display_name,
                        "role": LEGACY_USER_ROLE,
                    },
                )
            )
            .mappings()
            .one()
        )

    async def _upsert_account_membership(
        self,
        connection: AsyncConnection,
        *,
        account_id: str,
        user_id: str,
        status_value: str,
    ) -> str:
        row = (
            (
                await connection.execute(
                    text(
                        """
                        INSERT INTO account_membership (account_id, user_id, status, updated_at)
                        VALUES (
                          CAST(:account_id AS uuid),
                          CAST(:user_id AS uuid),
                          :status,
                          now()
                        )
                        ON CONFLICT (account_id, user_id) DO UPDATE
                        SET status = CASE
                              WHEN account_membership.status = 'active' THEN 'active'
                              ELSE EXCLUDED.status
                            END,
                            updated_at = now()
                        RETURNING id::text AS membership_id
                        """
                    ),
                    {"account_id": account_id, "user_id": user_id, "status": status_value},
                )
            )
            .mappings()
            .one()
        )
        return str(row["membership_id"])

    async def _upsert_workspace_membership(
        self,
        connection: AsyncConnection,
        *,
        workspace_id: str,
        account_membership_id: str,
        status_value: str,
    ) -> str:
        row = (
            (
                await connection.execute(
                    text(
                        """
                        INSERT INTO workspace_membership (
                          workspace_id, account_membership_id, status, updated_at
                        )
                        VALUES (
                          CAST(:workspace_id AS uuid),
                          CAST(:account_membership_id AS uuid),
                          :status,
                          now()
                        )
                        ON CONFLICT (workspace_id, account_membership_id) DO UPDATE
                        SET status = CASE
                              WHEN workspace_membership.status = 'active' THEN 'active'
                              ELSE EXCLUDED.status
                            END,
                            updated_at = now()
                        RETURNING id::text AS workspace_membership_id
                        """
                    ),
                    {
                        "workspace_id": workspace_id,
                        "account_membership_id": account_membership_id,
                        "status": status_value,
                    },
                )
            )
            .mappings()
            .one()
        )
        return str(row["workspace_membership_id"])

    async def _assign_roles(
        self,
        connection: AsyncConnection,
        *,
        account_id: str,
        membership_id: str,
        workspace_membership_id: str,
        role_keys: tuple[RoleKey, ...],
    ) -> None:
        for role_key in role_keys:
            role_row = await self._ensure_account_role(connection, account_id, role_key)
            if str(role_row["role_scope"]) == "workspace":
                await connection.execute(
                    text(
                        """
                        INSERT INTO workspace_membership_role (workspace_membership_id, role_id)
                        VALUES (
                          CAST(:workspace_membership_id AS uuid),
                          CAST(:role_id AS uuid)
                        )
                        ON CONFLICT DO NOTHING
                        """
                    ),
                    {
                        "workspace_membership_id": workspace_membership_id,
                        "role_id": str(role_row["role_id"]),
                    },
                )
            else:
                await connection.execute(
                    text(
                        """
                        INSERT INTO account_membership_role (account_membership_id, role_id)
                        VALUES (
                          CAST(:account_membership_id AS uuid),
                          CAST(:role_id AS uuid)
                        )
                        ON CONFLICT DO NOTHING
                        """
                    ),
                    {"account_membership_id": membership_id, "role_id": str(role_row["role_id"])},
                )

    async def _ensure_account_role(
        self,
        connection: AsyncConnection,
        account_id: str,
        role_key: RoleKey,
    ) -> dict[str, Any]:
        existing = (
            (
                await connection.execute(
                    text(
                        """
                        SELECT id::text AS role_id, role_scope
                        FROM platform_role
                        WHERE account_id = CAST(:account_id AS uuid)
                          AND role_key = :role_key
                        """
                    ),
                    {"account_id": account_id, "role_key": role_key},
                )
            )
            .mappings()
            .first()
        )
        if existing:
            return dict(existing)
        template = (
            (
                await connection.execute(
                    text(
                        """
                        SELECT id::text AS template_role_id,
                               display_name,
                               description,
                               role_scope
                        FROM platform_role
                        WHERE role_key = :role_key
                        ORDER BY CASE WHEN account_id IS NULL THEN 0 ELSE 1 END, created_at ASC
                        LIMIT 1
                        """
                    ),
                    {"role_key": role_key},
                )
            )
            .mappings()
            .first()
        )
        if not template:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Role key is known but has no database template: {role_key}",
            )
        created = (
            (
                await connection.execute(
                    text(
                        """
                        INSERT INTO platform_role (
                          account_id,
                          role_key,
                          display_name,
                          description,
                          role_scope,
                          system_managed
                        )
                        VALUES (
                          CAST(:account_id AS uuid),
                          :role_key,
                          :display_name,
                          :description,
                          :role_scope,
                          true
                        )
                        RETURNING id::text AS role_id, role_scope
                        """
                    ),
                    {
                        "account_id": account_id,
                        "role_key": role_key,
                        "display_name": str(template["display_name"]),
                        "description": str(template["description"]),
                        "role_scope": str(template["role_scope"]),
                    },
                )
            )
            .mappings()
            .one()
        )
        await connection.execute(
            text(
                """
                INSERT INTO platform_role_permission (role_id, permission_key)
                SELECT CAST(:role_id AS uuid), permission_key
                FROM platform_role_permission
                WHERE role_id = CAST(:template_role_id AS uuid)
                ON CONFLICT DO NOTHING
                """
            ),
            {
                "role_id": str(created["role_id"]),
                "template_role_id": str(template["template_role_id"]),
            },
        )
        return dict(created)

    async def _grant_entitlements(
        self,
        connection: AsyncConnection,
        *,
        account_id: str,
        entitlement_keys: tuple[EntitlementKey, ...],
        granted_by: str | None,
    ) -> None:
        for entitlement_key in entitlement_keys:
            await connection.execute(
                text(
                    """
                    INSERT INTO account_entitlement (
                      account_id, entitlement_key, status, granted_by, updated_at
                    )
                    VALUES (
                      CAST(:account_id AS uuid),
                      :entitlement_key,
                      'active',
                      CAST(:granted_by AS uuid),
                      now()
                    )
                    ON CONFLICT (account_id, entitlement_key) DO UPDATE
                    SET status = 'active',
                        updated_at = now()
                    """
                ),
                {
                    "account_id": account_id,
                    "entitlement_key": entitlement_key,
                    "granted_by": granted_by,
                },
            )

    async def _upsert_external_identity(
        self,
        connection: AsyncConnection,
        *,
        subject_type: str,
        subject_id: str,
        account_id: str | None,
        user_id: str | None,
        email_snapshot: str | None,
    ) -> None:
        await connection.execute(
            text(
                """
                INSERT INTO external_identity (
                  provider,
                  subject_type,
                  subject_id,
                  account_id,
                  user_id,
                  email_snapshot,
                  metadata,
                  last_seen_at,
                  updated_at
                )
                VALUES (
                  'workos',
                  :subject_type,
                  :subject_id,
                  CAST(:account_id AS uuid),
                  CAST(:user_id AS uuid),
                  :email_snapshot,
                  CAST(:metadata AS jsonb),
                  now(),
                  now()
                )
                ON CONFLICT (provider, subject_type, subject_id) DO UPDATE
                SET account_id = COALESCE(EXCLUDED.account_id, external_identity.account_id),
                    user_id = COALESCE(EXCLUDED.user_id, external_identity.user_id),
                    email_snapshot = COALESCE(
                      EXCLUDED.email_snapshot,
                      external_identity.email_snapshot
                    ),
                    metadata = external_identity.metadata || EXCLUDED.metadata,
                    last_seen_at = now(),
                    updated_at = now()
                """
            ),
            {
                "subject_type": subject_type,
                "subject_id": subject_id,
                "account_id": account_id,
                "user_id": user_id,
                "email_snapshot": email_snapshot,
                "metadata": json.dumps({"source": "customer_provisioning"}),
            },
        )

    async def record_identity_webhook(
        self,
        *,
        payload: dict[str, Any],
        payload_sha256: str,
    ) -> WebhookProcessingResult:
        event_id = _string_field(payload, "id", "event_id")
        event_type = _string_field(payload, "event", "event_type", "type")
        if not event_id or not event_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Identity webhook payload is missing event id or event type.",
            )
        data = _event_data(payload)
        email = _string_field(data, "email") or _nested_string_field(data, ("user", "email"))
        workos_organization_id = _string_field(data, "organization_id") or _nested_string_field(
            data,
            ("organization", "id"),
        )
        workos_user_id = _workos_user_id_for_event(event_type, data)
        workos_invitation_id = _workos_invitation_id_for_event(event_type, data)
        async with self._engine.begin() as connection:
            inserted = (
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO customer_identity_webhook_event (
                              provider,
                              provider_event_id,
                              event_type,
                              payload_sha256,
                              workos_organization_id,
                              workos_user_id,
                              workos_invitation_id,
                              email_snapshot,
                              metadata
                            )
                            VALUES (
                              'workos',
                              :event_id,
                              :event_type,
                              :payload_sha256,
                              :workos_organization_id,
                              :workos_user_id,
                              :workos_invitation_id,
                              :email,
                              CAST(:metadata AS jsonb)
                            )
                            ON CONFLICT (provider, provider_event_id) DO NOTHING
                            RETURNING id::text AS event_row_id
                            """
                        ),
                        {
                            "event_id": event_id,
                            "event_type": event_type,
                            "payload_sha256": payload_sha256,
                            "workos_organization_id": workos_organization_id,
                            "workos_user_id": workos_user_id,
                            "workos_invitation_id": workos_invitation_id,
                            "email": _normalize_email(email) if email else None,
                            "metadata": json.dumps({"source": "workos_webhook"}),
                        },
                    )
                )
                .mappings()
                .first()
            )
            if not inserted:
                return WebhookProcessingResult(
                    event_id=event_id,
                    event_type=event_type,
                    processing_status="duplicate",
                )
            processing_status = await self._apply_identity_event(
                connection,
                event_type=event_type,
                email=email,
                workos_user_id=workos_user_id,
                workos_organization_id=workos_organization_id,
                workos_invitation_id=workos_invitation_id,
            )
            await connection.execute(
                text(
                    """
                    UPDATE customer_identity_webhook_event
                    SET processing_status = :processing_status,
                        processed_at = now()
                    WHERE provider = 'workos'
                      AND provider_event_id = :event_id
                    """
                ),
                {"processing_status": processing_status, "event_id": event_id},
            )
        return WebhookProcessingResult(
            event_id=event_id,
            event_type=event_type,
            processing_status=processing_status,
        )

    async def _apply_identity_event(
        self,
        connection: AsyncConnection,
        *,
        event_type: str,
        email: str | None,
        workos_user_id: str | None,
        workos_organization_id: str | None,
        workos_invitation_id: str | None,
    ) -> str:
        if event_type not in {"invitation.accepted", "user.created", "user.updated"}:
            return "ignored"
        invitation = await self._find_invitation(
            connection,
            email=email,
            workos_invitation_id=workos_invitation_id,
        )
        if not invitation:
            return "ignored"
        if workos_user_id:
            await self._upsert_external_identity(
                connection,
                subject_type="user",
                subject_id=workos_user_id,
                account_id=None,
                user_id=str(invitation["user_id"]),
                email_snapshot=_normalize_email(email) if email else str(invitation["email"]),
            )
        if workos_organization_id:
            await self._upsert_external_identity(
                connection,
                subject_type="organization",
                subject_id=workos_organization_id,
                account_id=str(invitation["account_id"]),
                user_id=None,
                email_snapshot=None,
            )
        if event_type != "invitation.accepted":
            await connection.execute(
                text(
                    """
                    UPDATE customer_account_invitation
                    SET workos_user_id = COALESCE(:workos_user_id, workos_user_id),
                        workos_organization_id = COALESCE(
                          :workos_organization_id,
                          workos_organization_id
                        ),
                        updated_at = now()
                    WHERE id = CAST(:invitation_id AS uuid)
                    """
                ),
                {
                    "workos_user_id": workos_user_id,
                    "workos_organization_id": workos_organization_id,
                    "invitation_id": str(invitation["invitation_id"]),
                },
            )
            return "processed"
        await connection.execute(
            text(
                """
                UPDATE customer_account_invitation
                SET status = 'accepted',
                    workos_user_id = COALESCE(:workos_user_id, workos_user_id),
                    workos_organization_id = COALESCE(
                      :workos_organization_id,
                      workos_organization_id
                    ),
                    accepted_at = COALESCE(accepted_at, now()),
                    updated_at = now()
                WHERE id = CAST(:invitation_id AS uuid)
                """
            ),
            {
                "workos_user_id": workos_user_id,
                "workos_organization_id": workos_organization_id,
                "invitation_id": str(invitation["invitation_id"]),
            },
        )
        await connection.execute(
            text(
                """
                UPDATE account_membership
                SET status = 'active', updated_at = now()
                WHERE id = CAST(:membership_id AS uuid)
                """
            ),
            {"membership_id": str(invitation["membership_id"])},
        )
        await connection.execute(
            text(
                """
                UPDATE workspace_membership
                SET status = 'active', updated_at = now()
                WHERE account_membership_id = CAST(:membership_id AS uuid)
                """
            ),
            {"membership_id": str(invitation["membership_id"])},
        )
        return "processed"

    async def _find_invitation(
        self,
        connection: AsyncConnection,
        *,
        email: str | None,
        workos_invitation_id: str | None,
    ) -> dict[str, Any] | None:
        normalized_email = _normalize_email(email) if email else None
        row = (
            (
                await connection.execute(
                    text(
                        """
                        SELECT
                          invitation.id::text AS invitation_id,
                          invitation.account_id::text AS account_id,
                          invitation.user_id::text AS user_id,
                          invitation.email AS email,
                          membership.id::text AS membership_id
                        FROM customer_account_invitation invitation
                        JOIN account_membership membership
                          ON membership.account_id = invitation.account_id
                         AND membership.user_id = invitation.user_id
                        WHERE (
                            CAST(:workos_invitation_id AS text) IS NOT NULL
                            AND invitation.workos_invitation_id =
                              CAST(:workos_invitation_id AS text)
                          )
                          OR (
                            CAST(:email AS text) IS NOT NULL
                            AND invitation.email = CAST(:email AS text)
                            AND invitation.status IN ('prepared','sent')
                          )
                        ORDER BY invitation.created_at ASC, invitation.id ASC
                        LIMIT 1
                        """
                    ),
                    {"workos_invitation_id": workos_invitation_id, "email": normalized_email},
                )
            )
            .mappings()
            .first()
        )
        return dict(row) if row else None


def _customer_provisioning_repository(request: Request) -> CustomerProvisioningRepository:
    configured = getattr(request.app.state, "customer_provisioning_repository", None)
    if configured is not None:
        return configured
    return PostgresCustomerProvisioningRepository(request.app.state.database_probe.engine)


@router.post(
    "/admin/customer-provisioning/accounts/prepare",
    tags=["admin", "customer-auth"],
)
async def prepare_customer_account(
    body: PrepareCustomerAccountRequest,
    request: Request,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> PrepareCustomerAccountResponse:
    principal = require_platform_admin(request, x_rci_admin_token)
    repository = _customer_provisioning_repository(request)
    return await repository.prepare_customer_account(body, prepared_by=principal)


@router.get(
    "/admin/customer-provisioning/readiness",
    tags=["admin", "customer-auth"],
)
async def customer_auth_readiness(
    request: Request,
    email: Annotated[str | None, Query(min_length=3, max_length=320)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> CustomerAuthReadinessResponse:
    require_platform_admin(request, x_rci_admin_token)
    repository = _customer_provisioning_repository(request)
    return await repository.customer_auth_readiness(email=email, limit=limit)


@router.get(
    "/admin/customer-provisioning/account-foundation",
    tags=["admin", "customer-auth"],
)
async def customer_account_foundation(
    request: Request,
    account_slug: Annotated[str | None, Query(min_length=3, max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> CustomerAccountFoundationResponse:
    require_platform_admin(request, x_rci_admin_token)
    repository = _customer_provisioning_repository(request)
    return await repository.customer_account_foundation(account_slug=account_slug, limit=limit)


def _verify_workos_webhook(request: Request, event_body: bytes, signature: str | None) -> None:
    secret = os.getenv("WORKOS_WEBHOOK_SECRET", "").strip()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Customer identity webhook signing secret is not configured.",
        )
    if not signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Customer identity webhook signature is required.",
        )
    verifier = getattr(request.app.state, "workos_webhook_verifier", None)
    if verifier is not None:
        verifier(event_body, signature, secret)
        return
    client = WorkOSClient(
        api_key=os.getenv("WORKOS_API_KEY", "sk_missing"),
        client_id=os.getenv("WORKOS_CLIENT_ID", "client_missing"),
    )
    try:
        client.webhooks.verify_event(
            event_body=event_body,
            event_signature=signature,
            secret=secret,
        )
    except Exception as exc:  # pragma: no cover - exact SDK exception types are not stable.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Customer identity webhook signature is invalid.",
        ) from exc


@webhook_router.post("/workos")
async def workos_identity_webhook(
    request: Request,
    workos_signature: Annotated[str | None, Header(alias="WorkOS-Signature")] = None,
) -> dict[str, str]:
    event_body = await request.body()
    _verify_workos_webhook(request, event_body, workos_signature)
    try:
        payload = json.loads(event_body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Customer identity webhook payload must be JSON.",
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Customer identity webhook payload must be an object.",
        )
    result = await _customer_provisioning_repository(request).record_identity_webhook(
        payload=payload,
        payload_sha256=hashlib.sha256(event_body).hexdigest(),
    )
    return {
        "schema_version": "1.0.0-customer-identity-webhook",
        "event_id": result.event_id,
        "event_type": result.event_type,
        "processing_status": result.processing_status,
    }
