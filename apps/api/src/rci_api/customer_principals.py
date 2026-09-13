"""CPGHero customer principal resolution from external identity subjects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, cast

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from rci_api.workos_auth import WorkOSSessionIdentity
from rci_core import ENTITLEMENT_KEYS, ROLE_KEYS, AccessPrincipal
from rci_core.access_control import EntitlementKey, RoleKey


@dataclass(frozen=True, slots=True)
class CustomerPrincipalResolution:
    principal: AccessPrincipal
    source: str
    workos_session_id: str | None = None
    workos_organization_id: str | None = None


class CustomerPrincipalRepository(Protocol):
    async def resolve_workos_identity(
        self,
        identity: WorkOSSessionIdentity,
    ) -> CustomerPrincipalResolution: ...


class PostgresCustomerPrincipalRepository:
    """Resolve authenticated WorkOS identities through CPGHero-owned access rows."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def resolve_workos_identity(
        self,
        identity: WorkOSSessionIdentity,
    ) -> CustomerPrincipalResolution:
        async with self._engine.begin() as connection:
            user_row = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT
                          u.id::text AS user_id,
                          u.email AS email
                        FROM external_identity external
                        JOIN app_user u ON u.id = external.user_id
                        WHERE external.provider = 'workos'
                          AND external.subject_type = 'user'
                          AND external.subject_id = :workos_user_id
                        """
                        ),
                        {"workos_user_id": identity.workos_user_id},
                    )
                )
                .mappings()
                .first()
            )
            if not user_row:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        "Customer user is authenticated but has not been provisioned in CPGHero."
                    ),
                )

            account_id = await self._resolve_account_id(
                connection,
                app_user_id=str(user_row["user_id"]),
                workos_organization_id=identity.workos_organization_id,
            )
            membership_row = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT id::text AS membership_id
                        FROM account_membership
                        WHERE user_id = CAST(:user_id AS uuid)
                          AND account_id = CAST(:account_id AS uuid)
                          AND status = 'active'
                        """
                        ),
                        {"user_id": str(user_row["user_id"]), "account_id": account_id},
                    )
                )
                .mappings()
                .first()
            )
            if not membership_row:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Customer user is not an active member of the selected CPGHero account.",
                )

            workspace_id = await self._resolve_workspace_id(
                connection,
                membership_id=str(membership_row["membership_id"]),
            )
            roles = await self._resolve_roles(
                connection,
                membership_id=str(membership_row["membership_id"]),
                workspace_id=workspace_id,
            )
            entitlements = await self._resolve_entitlements(connection, account_id=account_id)

            await connection.execute(
                text(
                    """
                    UPDATE external_identity
                    SET email_snapshot = :email,
                        last_seen_at = now(),
                        updated_at = now()
                    WHERE provider = 'workos'
                      AND subject_type = 'user'
                      AND subject_id = :workos_user_id
                    """
                ),
                {"email": identity.email, "workos_user_id": identity.workos_user_id},
            )

        return CustomerPrincipalResolution(
            principal=AccessPrincipal(
                user_id=str(user_row["user_id"]),
                email=str(user_row["email"] or identity.email),
                account_id=account_id,
                workspace_id=workspace_id,
                role_keys=roles,
                entitlements=entitlements,
            ),
            source="workos_session",
            workos_session_id=identity.session_id,
            workos_organization_id=identity.workos_organization_id,
        )

    async def _resolve_account_id(
        self,
        connection: AsyncConnection,
        *,
        app_user_id: str,
        workos_organization_id: str | None,
    ) -> str:
        if workos_organization_id:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT account.id::text AS account_id
                        FROM external_identity external
                        JOIN account ON account.id = external.account_id
                        WHERE external.provider = 'workos'
                          AND external.subject_type = 'organization'
                          AND external.subject_id = :workos_organization_id
                          AND account.status = 'active'
                        """
                        ),
                        {"workos_organization_id": workos_organization_id},
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        "Customer organization is authenticated but has not been provisioned "
                        "in CPGHero."
                    ),
                )
            return str(row["account_id"])

        rows = (
            (
                await connection.execute(
                    text(
                        """
                    SELECT account.id::text AS account_id
                    FROM account_membership membership
                    JOIN account ON account.id = membership.account_id
                    WHERE membership.user_id = CAST(:user_id AS uuid)
                      AND membership.status = 'active'
                      AND account.status = 'active'
                    ORDER BY membership.created_at ASC, membership.id ASC
                    LIMIT 2
                    """
                    ),
                    {"user_id": app_user_id},
                )
            )
            .mappings()
            .all()
        )
        if len(rows) == 1:
            return str(rows[0]["account_id"])
        if not rows:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Customer user has no active CPGHero account membership.",
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Customer user belongs to multiple accounts; "
                "WorkOS organization selection is required."
            ),
        )

    async def _resolve_workspace_id(
        self,
        connection: AsyncConnection,
        *,
        membership_id: str,
    ) -> str | None:
        row = (
            (
                await connection.execute(
                    text(
                        """
                    SELECT workspace_id::text AS workspace_id
                    FROM workspace_membership
                    WHERE account_membership_id = CAST(:membership_id AS uuid)
                      AND status = 'active'
                    ORDER BY created_at ASC, id ASC
                    LIMIT 1
                    """
                    ),
                    {"membership_id": membership_id},
                )
            )
            .mappings()
            .first()
        )
        return str(row["workspace_id"]) if row else None

    async def _resolve_roles(
        self,
        connection: AsyncConnection,
        *,
        membership_id: str,
        workspace_id: str | None,
    ) -> frozenset[RoleKey]:
        account_roles = (
            (
                await connection.execute(
                    text(
                        """
                    SELECT role.role_key
                    FROM account_membership_role membership_role
                    JOIN platform_role role ON role.id = membership_role.role_id
                    WHERE membership_role.account_membership_id = CAST(:membership_id AS uuid)
                    """
                    ),
                    {"membership_id": membership_id},
                )
            )
            .mappings()
            .all()
        )
        role_values = {str(row["role_key"]) for row in account_roles}
        if workspace_id:
            workspace_roles = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT role.role_key
                        FROM workspace_membership membership
                        JOIN workspace_membership_role membership_role
                          ON membership_role.workspace_membership_id = membership.id
                        JOIN platform_role role ON role.id = membership_role.role_id
                        WHERE membership.account_membership_id = CAST(:membership_id AS uuid)
                          AND membership.workspace_id = CAST(:workspace_id AS uuid)
                          AND membership.status = 'active'
                        """
                        ),
                        {"membership_id": membership_id, "workspace_id": workspace_id},
                    )
                )
                .mappings()
                .all()
            )
            role_values.update(str(row["role_key"]) for row in workspace_roles)

        unknown_roles = sorted(role_values.difference(cast("frozenset[str]", ROLE_KEYS)))
        if unknown_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Customer role mapping contains unknown role keys: {', '.join(unknown_roles)}"
                ),
            )
        if not role_values:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Customer user has no active CPGHero role assignment.",
            )
        return frozenset(cast("RoleKey", role) for role in role_values)

    async def _resolve_entitlements(
        self,
        connection: AsyncConnection,
        *,
        account_id: str,
    ) -> frozenset[EntitlementKey]:
        rows = (
            (
                await connection.execute(
                    text(
                        """
                    SELECT entitlement_key
                    FROM account_entitlement
                    WHERE account_id = CAST(:account_id AS uuid)
                      AND status = 'active'
                      AND (starts_at IS NULL OR starts_at <= now())
                      AND (expires_at IS NULL OR expires_at > now())
                    """
                    ),
                    {"account_id": account_id},
                )
            )
            .mappings()
            .all()
        )
        values = {str(row["entitlement_key"]) for row in rows}
        unknown = sorted(values.difference(cast("frozenset[str]", ENTITLEMENT_KEYS)))
        if unknown:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Customer entitlement mapping contains unknown entitlement keys: "
                    f"{', '.join(unknown)}"
                ),
            )
        return frozenset(cast("EntitlementKey", entitlement) for entitlement in values)
