"""Customer-owned report listing APIs.

These routes expose only reports explicitly granted to the resolved CPGHero
customer account/workspace. They do not infer customer access from legacy
organization-wide report rows.
"""

from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any, Literal, Protocol

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.types import Integer, String

from rci_analytics import PriceMonitoringFilters
from rci_api.analyses import AnalysisServiceDependency
from rci_api.customer_access import (
    current_customer_access_principal,
    enforce_customer_access,
)
from rci_api.price_monitoring import (
    BrandFilter,
)
from rci_api.price_monitoring import (
    ServiceDependency as PriceMonitoringServiceDependency,
)
from rci_core import AccessPrincipal
from rci_results.service import AnalysisNotFoundError, ProductEvidenceNotFoundError

router = APIRouter(prefix="/api/v1/customer", tags=["customer-reports"])
admin_router = APIRouter(prefix="/api/v1/admin/customer-report-access", tags=["admin"])


@dataclass(frozen=True, slots=True)
class CustomerReportSummary:
    access_id: str
    analysis_id: str
    analysis_result_id: str
    collection_run_id: str | None
    product_pack_id: str | None
    product_pack_version: str | None
    reporting_status: str
    schema_version: str
    checksum: str
    title: str
    category: str | None
    retailer_count: int | None
    created_at: datetime
    granted_at: datetime


@dataclass(frozen=True, slots=True)
class CustomerReportDetail:
    summary: CustomerReportSummary
    analysis: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AdminCustomerReportGrant:
    access_id: str
    account_id: str
    account_slug: str
    account_display_name: str
    workspace_id: str | None
    workspace_slug: str | None
    workspace_display_name: str | None
    analysis_id: str
    analysis_result_id: str
    title: str
    category: str | None
    status: str
    granted_at: datetime


@dataclass(frozen=True, slots=True)
class AdminGrantableReport:
    analysis_id: str
    analysis_result_id: str
    title: str
    category: str | None
    product_pack_id: str | None
    product_pack_version: str | None
    created_at: datetime


class CustomerReportRepository(Protocol):
    async def list_reports(
        self,
        *,
        account_id: str,
        workspace_id: str | None,
        limit: int,
    ) -> list[CustomerReportSummary]: ...

    async def get_report(
        self,
        *,
        access_id: str,
        account_id: str,
        workspace_id: str | None,
    ) -> CustomerReportDetail | None: ...

    async def admin_snapshot(self, *, limit: int) -> dict[str, list[Any]]: ...

    async def admin_grant_report(
        self,
        *,
        account_key: str,
        workspace_key: str | None,
        analysis_result_id: str,
        granted_by: str | None,
    ) -> AdminCustomerReportGrant: ...

    async def admin_revoke_report(self, *, access_id: str) -> AdminCustomerReportGrant | None: ...


class PostgresCustomerReportRepository:
    """Read customer report grants from Postgres."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def list_reports(
        self,
        *,
        account_id: str,
        workspace_id: str | None,
        limit: int,
    ) -> list[CustomerReportSummary]:
        statement = text(
            """
            SELECT
              access.id::text AS access_id,
              result.id::text AS analysis_result_id,
              result.analysis_id,
              result.schema_version,
              result.checksum,
              result.reporting_status,
              result.created_at,
              access.created_at AS granted_at,
              run.collection_run_id::text AS collection_run_id,
              run.product_pack_id,
              run.product_pack_version,
              COALESCE(
                result.result #>> '{metadata,title}',
                result.result #>> '{report,title}',
                result.result #>> '{summary,title}',
                result.analysis_id
              ) AS title,
              COALESCE(
                result.result #>> '{metadata,category}',
                result.result #>> '{product_pack,category}',
                result.result #>> '{category}'
              ) AS category,
              CASE
                WHEN jsonb_typeof(result.result #> '{retailers}') = 'array'
                THEN jsonb_array_length(result.result #> '{retailers}')
                ELSE NULL
              END AS retailer_count
            FROM customer_report_access access
            JOIN analysis_result result
              ON result.id = access.analysis_result_id
            LEFT JOIN analysis_run run
              ON run.id = result.analysis_run_id
            WHERE access.account_id = CAST(:account_id AS uuid)
              AND access.status = 'active'
              AND result.archived_at IS NULL
              AND (
                access.workspace_id IS NULL
                OR access.workspace_id = CAST(:workspace_id AS uuid)
              )
            ORDER BY result.created_at DESC, access.created_at DESC, result.id DESC
            LIMIT :limit
            """
        ).bindparams(
            bindparam("account_id", type_=String()),
            bindparam("workspace_id", type_=String()),
            bindparam("limit", type_=Integer()),
        )
        async with self._engine.begin() as connection:
            rows = (
                await connection.execute(
                    statement,
                    {
                        "account_id": account_id,
                        "workspace_id": workspace_id,
                        "limit": limit,
                    },
                )
            ).mappings()
        return [
            CustomerReportSummary(
                access_id=str(row["access_id"]),
                analysis_id=str(row["analysis_id"]),
                analysis_result_id=str(row["analysis_result_id"]),
                collection_run_id=(
                    str(row["collection_run_id"]) if row["collection_run_id"] else None
                ),
                product_pack_id=(str(row["product_pack_id"]) if row["product_pack_id"] else None),
                product_pack_version=(
                    str(row["product_pack_version"]) if row["product_pack_version"] else None
                ),
                reporting_status=str(row["reporting_status"]),
                schema_version=str(row["schema_version"]),
                checksum=str(row["checksum"]),
                title=str(row["title"]),
                category=str(row["category"]) if row["category"] else None,
                retailer_count=(
                    int(row["retailer_count"]) if row["retailer_count"] is not None else None
                ),
                created_at=row["created_at"],
                granted_at=row["granted_at"],
            )
            for row in rows
        ]

    async def get_report(
        self,
        *,
        access_id: str,
        account_id: str,
        workspace_id: str | None,
    ) -> CustomerReportDetail | None:
        statement = text(
            """
            SELECT
              access.id::text AS access_id,
              result.id::text AS analysis_result_id,
              result.analysis_run_id::text AS analysis_run_id,
              result.analysis_id,
              result.schema_version,
              result.checksum,
              result.reporting_status,
              result.result,
              result.created_at,
              access.created_at AS granted_at,
              run.collection_run_id::text AS collection_run_id,
              run.status AS analysis_run_status,
              run.product_pack_id,
              run.product_pack_version,
              COALESCE(
                result.result #>> '{metadata,title}',
                result.result #>> '{report,title}',
                result.result #>> '{summary,title}',
                result.analysis_id
              ) AS title,
              COALESCE(
                result.result #>> '{metadata,category}',
                result.result #>> '{product_pack,category}',
                result.result #>> '{category}'
              ) AS category,
              CASE
                WHEN jsonb_typeof(result.result #> '{retailers}') = 'array'
                THEN jsonb_array_length(result.result #> '{retailers}')
                ELSE NULL
              END AS retailer_count
            FROM customer_report_access access
            JOIN analysis_result result
              ON result.id = access.analysis_result_id
            JOIN analysis_run run
              ON run.id = result.analysis_run_id
            WHERE access.id = CAST(:access_id AS uuid)
              AND access.account_id = CAST(:account_id AS uuid)
              AND access.status = 'active'
              AND result.archived_at IS NULL
              AND result.reporting_status = 'ready'
              AND (
                access.workspace_id IS NULL
                OR access.workspace_id = CAST(:workspace_id AS uuid)
              )
            """
        ).bindparams(
            bindparam("access_id", type_=String()),
            bindparam("account_id", type_=String()),
            bindparam("workspace_id", type_=String()),
        )
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        statement,
                        {
                            "access_id": access_id,
                            "account_id": account_id,
                            "workspace_id": workspace_id,
                        },
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            return None
        summary = CustomerReportSummary(
            access_id=str(row["access_id"]),
            analysis_id=str(row["analysis_id"]),
            analysis_result_id=str(row["analysis_result_id"]),
            collection_run_id=(str(row["collection_run_id"]) if row["collection_run_id"] else None),
            product_pack_id=(str(row["product_pack_id"]) if row["product_pack_id"] else None),
            product_pack_version=(
                str(row["product_pack_version"]) if row["product_pack_version"] else None
            ),
            reporting_status=str(row["reporting_status"]),
            schema_version=str(row["schema_version"]),
            checksum=str(row["checksum"]),
            title=str(row["title"]),
            category=str(row["category"]) if row["category"] else None,
            retailer_count=int(row["retailer_count"])
            if row["retailer_count"] is not None
            else None,
            created_at=row["created_at"],
            granted_at=row["granted_at"],
        )
        return CustomerReportDetail(
            summary=summary,
            analysis={
                "id": str(row["analysis_result_id"]),
                "analysis_run_id": str(row["analysis_run_id"]),
                "analysis_id": str(row["analysis_id"]),
                "collection_run_id": (
                    str(row["collection_run_id"]) if row["collection_run_id"] else None
                ),
                "status": str(row["analysis_run_status"]),
                "reporting_status": str(row["reporting_status"]),
                "product_pack_id": (
                    str(row["product_pack_id"]) if row["product_pack_id"] else None
                ),
                "product_pack_version": (
                    str(row["product_pack_version"]) if row["product_pack_version"] else None
                ),
                "schema_version": str(row["schema_version"]),
                "checksum": str(row["checksum"]),
                "result": dict(row["result"]),
                "created_at": row["created_at"],
            },
        )

    async def admin_snapshot(self, *, limit: int) -> dict[str, list[Any]]:
        async with self._engine.connect() as connection:
            grants = (
                await connection.execute(
                    text(
                        """
                        SELECT
                          access.id::text AS access_id,
                          account.id::text AS account_id,
                          account.slug AS account_slug,
                          account.display_name AS account_display_name,
                          workspace.id::text AS workspace_id,
                          workspace.slug AS workspace_slug,
                          workspace.display_name AS workspace_display_name,
                          result.analysis_id,
                          result.id::text AS analysis_result_id,
                          COALESCE(
                            result.result #>> '{metadata,title}',
                            result.result #>> '{report,title}',
                            result.result #>> '{summary,title}',
                            result.analysis_id
                          ) AS title,
                          COALESCE(
                            result.result #>> '{metadata,category}',
                            result.result #>> '{product_pack,category}',
                            result.result #>> '{category}'
                          ) AS category,
                          access.status,
                          access.created_at AS granted_at
                        FROM customer_report_access access
                        JOIN account ON account.id = access.account_id
                        LEFT JOIN workspace ON workspace.id = access.workspace_id
                        JOIN analysis_result result ON result.id = access.analysis_result_id
                        ORDER BY access.created_at DESC, access.id DESC
                        LIMIT :limit
                        """
                    ),
                    {"limit": limit},
                )
            ).mappings()
            reports = (
                await connection.execute(
                    text(
                        """
                        SELECT
                          result.analysis_id,
                          result.id::text AS analysis_result_id,
                          COALESCE(
                            result.result #>> '{metadata,title}',
                            result.result #>> '{report,title}',
                            result.result #>> '{summary,title}',
                            result.analysis_id
                          ) AS title,
                          COALESCE(
                            result.result #>> '{metadata,category}',
                            result.result #>> '{product_pack,category}',
                            result.result #>> '{category}'
                          ) AS category,
                          run.product_pack_id,
                          run.product_pack_version,
                          result.created_at
                        FROM analysis_result result
                        LEFT JOIN analysis_run run ON run.id = result.analysis_run_id
                        WHERE result.archived_at IS NULL
                          AND result.reporting_status = 'ready'
                        ORDER BY result.created_at DESC, result.id DESC
                        LIMIT :limit
                        """
                    ),
                    {"limit": limit},
                )
            ).mappings()
        return {
            "grants": [
                AdminCustomerReportGrant(
                    access_id=str(row["access_id"]),
                    account_id=str(row["account_id"]),
                    account_slug=str(row["account_slug"]),
                    account_display_name=str(row["account_display_name"]),
                    workspace_id=str(row["workspace_id"]) if row["workspace_id"] else None,
                    workspace_slug=str(row["workspace_slug"]) if row["workspace_slug"] else None,
                    workspace_display_name=(
                        str(row["workspace_display_name"])
                        if row["workspace_display_name"]
                        else None
                    ),
                    analysis_id=str(row["analysis_id"]),
                    analysis_result_id=str(row["analysis_result_id"]),
                    title=str(row["title"]),
                    category=str(row["category"]) if row["category"] else None,
                    status=str(row["status"]),
                    granted_at=row["granted_at"],
                )
                for row in grants
            ],
            "grantable_reports": [
                AdminGrantableReport(
                    analysis_id=str(row["analysis_id"]),
                    analysis_result_id=str(row["analysis_result_id"]),
                    title=str(row["title"]),
                    category=str(row["category"]) if row["category"] else None,
                    product_pack_id=str(row["product_pack_id"]) if row["product_pack_id"] else None,
                    product_pack_version=(
                        str(row["product_pack_version"]) if row["product_pack_version"] else None
                    ),
                    created_at=row["created_at"],
                )
                for row in reports
            ],
        }

    async def admin_grant_report(
        self,
        *,
        account_key: str,
        workspace_key: str | None,
        analysis_result_id: str,
        granted_by: str | None,
    ) -> AdminCustomerReportGrant:
        async with self._engine.begin() as connection:
            account = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT id::text, slug, display_name
                        FROM account
                        WHERE (id::text = :account_key OR slug = lower(:account_key))
                          AND status = 'active'
                        """
                        ),
                        {"account_key": account_key.strip()},
                    )
                )
                .mappings()
                .first()
            )
            if account is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Active customer account was not found.",
                )
            workspace_id: str | None = None
            if workspace_key:
                workspace = (
                    (
                        await connection.execute(
                            text(
                                """
                            SELECT id::text
                            FROM workspace
                            WHERE account_id = CAST(:account_id AS uuid)
                              AND (id::text = :workspace_key OR slug = lower(:workspace_key))
                              AND status = 'active'
                            """
                            ),
                            {
                                "account_id": str(account["id"]),
                                "workspace_key": workspace_key.strip(),
                            },
                        )
                    )
                    .mappings()
                    .first()
                )
                if workspace is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Active workspace was not found for this account.",
                    )
                workspace_id = str(workspace["id"])
            report_exists = await connection.scalar(
                text(
                    """
                    SELECT 1
                    FROM analysis_result
                    WHERE id = CAST(:analysis_result_id AS uuid)
                      AND archived_at IS NULL
                      AND reporting_status = 'ready'
                    """
                ),
                {"analysis_result_id": analysis_result_id},
            )
            if report_exists is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="A ready, active report was not found for this analysis result.",
                )
            if workspace_id is None:
                row = (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO customer_report_access (
                              account_id, workspace_id, analysis_result_id, status,
                              granted_by, metadata, updated_at
                            )
                            VALUES (
                              CAST(:account_id AS uuid), NULL,
                              CAST(:analysis_result_id AS uuid), 'active',
                              CAST(:granted_by AS uuid), CAST(:metadata AS jsonb), now()
                            )
                            ON CONFLICT (account_id, analysis_result_id)
                            WHERE workspace_id IS NULL
                            DO UPDATE SET status = 'active',
                                          granted_by = EXCLUDED.granted_by,
                                          metadata = customer_report_access.metadata
                                                     || EXCLUDED.metadata,
                                          updated_at = now()
                            RETURNING id::text
                            """
                        ),
                        {
                            "account_id": str(account["id"]),
                            "analysis_result_id": analysis_result_id,
                            "granted_by": granted_by,
                            "metadata": json.dumps({"source": "admin_customer_report_access"}),
                        },
                    )
                ).scalar_one()
            else:
                row = (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO customer_report_access (
                              account_id, workspace_id, analysis_result_id, status,
                              granted_by, metadata, updated_at
                            )
                            VALUES (
                              CAST(:account_id AS uuid), CAST(:workspace_id AS uuid),
                              CAST(:analysis_result_id AS uuid), 'active',
                              CAST(:granted_by AS uuid), CAST(:metadata AS jsonb), now()
                            )
                            ON CONFLICT (account_id, workspace_id, analysis_result_id)
                            WHERE workspace_id IS NOT NULL
                            DO UPDATE SET status = 'active',
                                          granted_by = EXCLUDED.granted_by,
                                          metadata = customer_report_access.metadata
                                                     || EXCLUDED.metadata,
                                          updated_at = now()
                            RETURNING id::text
                            """
                        ),
                        {
                            "account_id": str(account["id"]),
                            "workspace_id": workspace_id,
                            "analysis_result_id": analysis_result_id,
                            "granted_by": granted_by,
                            "metadata": json.dumps({"source": "admin_customer_report_access"}),
                        },
                    )
                ).scalar_one()
        grant = await self._admin_grant_by_id(str(row))
        if grant is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Report grant was written but could not be reloaded.",
            )
        return grant

    async def admin_revoke_report(self, *, access_id: str) -> AdminCustomerReportGrant | None:
        async with self._engine.begin() as connection:
            row = (
                await connection.execute(
                    text(
                        """
                        UPDATE customer_report_access
                        SET status = 'revoked', updated_at = now()
                        WHERE id = CAST(:access_id AS uuid)
                        RETURNING id::text
                        """
                    ),
                    {"access_id": access_id},
                )
            ).scalar_one_or_none()
        return await self._admin_grant_by_id(str(row)) if row is not None else None

    async def _admin_grant_by_id(self, access_id: str) -> AdminCustomerReportGrant | None:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT
                          access.id::text AS access_id,
                          account.id::text AS account_id,
                          account.slug AS account_slug,
                          account.display_name AS account_display_name,
                          workspace.id::text AS workspace_id,
                          workspace.slug AS workspace_slug,
                          workspace.display_name AS workspace_display_name,
                          result.analysis_id,
                          result.id::text AS analysis_result_id,
                          COALESCE(
                            result.result #>> '{metadata,title}',
                            result.result #>> '{report,title}',
                            result.result #>> '{summary,title}',
                            result.analysis_id
                          ) AS title,
                          COALESCE(
                            result.result #>> '{metadata,category}',
                            result.result #>> '{product_pack,category}',
                            result.result #>> '{category}'
                          ) AS category,
                          access.status,
                          access.created_at AS granted_at
                        FROM customer_report_access access
                        JOIN account ON account.id = access.account_id
                        LEFT JOIN workspace ON workspace.id = access.workspace_id
                        JOIN analysis_result result ON result.id = access.analysis_result_id
                        WHERE access.id = CAST(:access_id AS uuid)
                        """
                        ),
                        {"access_id": access_id},
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            return None
        return AdminCustomerReportGrant(
            access_id=str(row["access_id"]),
            account_id=str(row["account_id"]),
            account_slug=str(row["account_slug"]),
            account_display_name=str(row["account_display_name"]),
            workspace_id=str(row["workspace_id"]) if row["workspace_id"] else None,
            workspace_slug=str(row["workspace_slug"]) if row["workspace_slug"] else None,
            workspace_display_name=(
                str(row["workspace_display_name"]) if row["workspace_display_name"] else None
            ),
            analysis_id=str(row["analysis_id"]),
            analysis_result_id=str(row["analysis_result_id"]),
            title=str(row["title"]),
            category=str(row["category"]) if row["category"] else None,
            status=str(row["status"]),
            granted_at=row["granted_at"],
        )


def get_customer_report_repository(request: Request) -> CustomerReportRepository:
    configured = getattr(request.app.state, "customer_report_repository", None)
    if configured is not None:
        return configured
    return PostgresCustomerReportRepository(request.app.state.database_probe.engine)


CustomerReportRepositoryDependency = Annotated[
    CustomerReportRepository,
    Depends(get_customer_report_repository),
]
CustomerPrincipalDependency = Annotated[
    AccessPrincipal,
    Depends(current_customer_access_principal),
]


class CustomerReportSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    access_id: str
    analysis_id: str
    analysis_result_id: str
    collection_run_id: str | None
    product_pack_id: str | None
    product_pack_version: str | None
    reporting_status: str
    schema_version: str
    checksum: str
    title: str
    category: str | None
    retailer_count: int | None
    created_at: datetime
    granted_at: datetime


class CustomerReportListResponse(BaseModel):
    schema_version: str = "1.0.0-customer-report-list"
    scope: dict[str, str | None]
    reports: list[CustomerReportSummaryResponse]


class CustomerReportDetailResponse(BaseModel):
    schema_version: str = "1.0.0-customer-report-detail"
    scope: dict[str, str | None]
    report: CustomerReportSummaryResponse
    analysis: dict[str, Any]


class CustomerReportViewResponse(BaseModel):
    schema_version: str = "1.0.0-customer-report-view"
    scope: dict[str, str | None]
    report: CustomerReportSummaryResponse
    analysis: dict[str, Any]
    view: dict[str, Any]


class CustomerReportQualityResponse(BaseModel):
    schema_version: str = "1.0.0-customer-report-quality"
    scope: dict[str, str | None]
    report: CustomerReportSummaryResponse
    quality: dict[str, Any]


class AdminCustomerReportGrantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    access_id: str
    account_id: str
    account_slug: str
    account_display_name: str
    workspace_id: str | None
    workspace_slug: str | None
    workspace_display_name: str | None
    analysis_id: str
    analysis_result_id: str
    title: str
    category: str | None
    status: str
    granted_at: datetime


class AdminGrantableReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    analysis_id: str
    analysis_result_id: str
    title: str
    category: str | None
    product_pack_id: str | None
    product_pack_version: str | None
    created_at: datetime


class AdminCustomerReportAccessSnapshotResponse(BaseModel):
    schema_version: str = "1.0.0-admin-customer-report-access"
    grants: list[AdminCustomerReportGrantResponse]
    grantable_reports: list[AdminGrantableReportResponse]


class AdminCustomerReportGrantRequest(BaseModel):
    account: str = Field(min_length=1)
    workspace: str | None = Field(default=None)
    analysis_result_id: str = Field(min_length=1)


def _require_customer_report_admin(
    request: Request,
    provided: str | None,
) -> None:
    expected = os.getenv("PRODUCT_PACK_ADMIN_TOKEN", "").strip()
    if request.app.state.settings.is_production and (
        not expected or not provided or not secrets.compare_digest(expected, provided)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated administrator access is required.",
        )


async def _authorized_customer_report_detail(
    *,
    access_id: str,
    principal: AccessPrincipal,
    repository: CustomerReportRepository,
) -> CustomerReportDetail:
    enforce_customer_access(
        principal,
        permission="analytics.view",
        entitlement="app_analytics",
    )
    if principal.account_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Customer account access is required for this resource.",
        )
    detail = await repository.get_report(
        access_id=access_id,
        account_id=principal.account_id,
        workspace_id=principal.workspace_id,
    )
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="A granted, ready customer report was not found.",
        )
    return detail


@router.get("/reports", response_model=CustomerReportListResponse)
async def list_customer_reports(
    principal: CustomerPrincipalDependency,
    repository: CustomerReportRepositoryDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> CustomerReportListResponse:
    enforce_customer_access(
        principal,
        permission="analytics.view",
        entitlement="app_analytics",
    )
    if principal.account_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Customer account access is required for this resource.",
        )
    account_id = principal.account_id

    reports = await repository.list_reports(
        account_id=account_id,
        workspace_id=principal.workspace_id,
        limit=limit,
    )
    return CustomerReportListResponse(
        scope={
            "account_id": account_id,
            "workspace_id": principal.workspace_id,
        },
        reports=[CustomerReportSummaryResponse.model_validate(report) for report in reports],
    )


@router.get("/reports/{access_id}", response_model=CustomerReportDetailResponse)
async def get_customer_report(
    access_id: str,
    principal: CustomerPrincipalDependency,
    repository: CustomerReportRepositoryDependency,
) -> CustomerReportDetailResponse:
    detail = await _authorized_customer_report_detail(
        access_id=access_id,
        principal=principal,
        repository=repository,
    )
    return CustomerReportDetailResponse(
        scope={
            "account_id": principal.account_id,
            "workspace_id": principal.workspace_id,
        },
        report=CustomerReportSummaryResponse.model_validate(detail.summary),
        analysis=detail.analysis,
    )


@router.get("/reports/{access_id}/report", response_model=CustomerReportViewResponse)
async def get_customer_report_view(
    access_id: str,
    principal: CustomerPrincipalDependency,
    repository: CustomerReportRepositoryDependency,
    service: AnalysisServiceDependency,
) -> CustomerReportViewResponse:
    detail = await _authorized_customer_report_detail(
        access_id=access_id,
        principal=principal,
        repository=repository,
    )
    try:
        view = await service.report_view(detail.summary.analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return CustomerReportViewResponse(
        scope={
            "account_id": principal.account_id,
            "workspace_id": principal.workspace_id,
        },
        report=CustomerReportSummaryResponse.model_validate(detail.summary),
        analysis=detail.analysis,
        view=view,
    )


@router.get("/reports/{access_id}/quality", response_model=CustomerReportQualityResponse)
async def get_customer_report_quality(
    access_id: str,
    principal: CustomerPrincipalDependency,
    repository: CustomerReportRepositoryDependency,
    service: AnalysisServiceDependency,
) -> CustomerReportQualityResponse:
    detail = await _authorized_customer_report_detail(
        access_id=access_id,
        principal=principal,
        repository=repository,
    )
    try:
        quality = await service.quality(detail.summary.analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return CustomerReportQualityResponse(
        scope={
            "account_id": principal.account_id,
            "workspace_id": principal.workspace_id,
        },
        report=CustomerReportSummaryResponse.model_validate(detail.summary),
        quality=quality,
    )


@router.get("/reports/{access_id}/product-decisions/{decision_id}/evidence")
async def get_customer_product_decision_evidence(
    access_id: str,
    decision_id: str,
    principal: CustomerPrincipalDependency,
    repository: CustomerReportRepositoryDependency,
    service: AnalysisServiceDependency,
) -> dict[str, Any]:
    detail = await _authorized_customer_report_detail(
        access_id=access_id,
        principal=principal,
        repository=repository,
    )
    try:
        return await service.product_evidence(detail.summary.analysis_id, decision_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ProductEvidenceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/reports/{access_id}/price-monitoring/map")
async def get_customer_price_monitoring_map(
    access_id: str,
    principal: CustomerPrincipalDependency,
    repository: CustomerReportRepositoryDependency,
    service: PriceMonitoringServiceDependency,
    retailer: str = Query(min_length=1),
    brand_type: BrandFilter = "all",
    state_filter: str | None = Query(default=None, alias="state"),
    city: str | None = None,
    zipcode: str | None = None,
    product_id: str = Query(min_length=1),
    detail: Literal["summary", "full"] = "full",
) -> dict[str, Any]:
    report = await _authorized_customer_report_detail(
        access_id=access_id,
        principal=principal,
        repository=repository,
    )
    try:
        return await service.map_view(
            report.summary.analysis_id,
            PriceMonitoringFilters(
                retailer_id=retailer,
                brand_type=brand_type,
                state=state_filter,
                city=city,
                zipcode=zipcode,
                product_id=product_id,
            ),
            detail=detail,
        )
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.post("/reports/{access_id}/price-monitoring/state-coverage")
async def get_customer_price_monitoring_state_coverage(
    request: Request,
    access_id: str,
    principal: CustomerPrincipalDependency,
    repository: CustomerReportRepositoryDependency,
    service: PriceMonitoringServiceDependency,
) -> dict[str, Any]:
    report = await _authorized_customer_report_detail(
        access_id=access_id,
        principal=principal,
        repository=repository,
    )
    body = await request.json()
    raw_products = body.get("products") if isinstance(body, dict) else None
    if not isinstance(raw_products, list):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="products must be a list",
        )
    if len(raw_products) > 1_000:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="state coverage is limited to 1,000 products per request",
        )
    products = [
        {
            "retailer_id": str(row.get("retailer_id") or ""),
            "product_id": str(row.get("product_id") or ""),
        }
        for row in raw_products
        if isinstance(row, dict)
    ]
    try:
        return await service.state_coverage(report.summary.analysis_id, products)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.get("/reports/{access_id}/price-monitoring/evidence.csv")
async def get_customer_price_monitoring_evidence_csv(
    access_id: str,
    principal: CustomerPrincipalDependency,
    repository: CustomerReportRepositoryDependency,
    service: PriceMonitoringServiceDependency,
    retailer: str = Query(min_length=1),
    product_id: str = Query(min_length=1),
    brand_type: BrandFilter = "all",
    state_filter: str | None = Query(default=None, alias="state"),
    city: str | None = None,
    zipcode: str | None = None,
) -> Response:
    report = await _authorized_customer_report_detail(
        access_id=access_id,
        principal=principal,
        repository=repository,
    )
    try:
        body = await service.evidence_csv(
            report.summary.analysis_id,
            PriceMonitoringFilters(
                retailer_id=retailer,
                brand_type=brand_type,
                state=state_filter,
                city=city,
                zipcode=zipcode,
                product_id=product_id,
            ),
        )
        safe_retailer = "".join(
            character for character in retailer if character.isalnum() or character in "_-"
        )
        safe_product_id = "".join(
            character for character in product_id if character.isalnum() or character in "_-"
        )
        filename = (
            f"{safe_retailer or 'retailer'}-{safe_product_id or 'product'}-price-evidence.csv"
        )
        return Response(
            content=body,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@admin_router.get("", response_model=AdminCustomerReportAccessSnapshotResponse)
async def admin_customer_report_access_snapshot(
    request: Request,
    repository: CustomerReportRepositoryDependency,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> AdminCustomerReportAccessSnapshotResponse:
    _require_customer_report_admin(request, x_rci_admin_token)
    snapshot = await repository.admin_snapshot(limit=limit)
    return AdminCustomerReportAccessSnapshotResponse(
        grants=[
            AdminCustomerReportGrantResponse.model_validate(grant) for grant in snapshot["grants"]
        ],
        grantable_reports=[
            AdminGrantableReportResponse.model_validate(report)
            for report in snapshot["grantable_reports"]
        ],
    )


@admin_router.post("", response_model=AdminCustomerReportGrantResponse)
async def admin_grant_customer_report_access(
    request: Request,
    repository: CustomerReportRepositoryDependency,
    command: AdminCustomerReportGrantRequest,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> AdminCustomerReportGrantResponse:
    _require_customer_report_admin(request, x_rci_admin_token)
    grant = await repository.admin_grant_report(
        account_key=command.account,
        workspace_key=command.workspace,
        analysis_result_id=command.analysis_result_id,
        granted_by=None,
    )
    return AdminCustomerReportGrantResponse.model_validate(grant)


@admin_router.delete("/{access_id}", response_model=AdminCustomerReportGrantResponse)
async def admin_revoke_customer_report_access(
    access_id: str,
    request: Request,
    repository: CustomerReportRepositoryDependency,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> AdminCustomerReportGrantResponse:
    _require_customer_report_admin(request, x_rci_admin_token)
    grant = await repository.admin_revoke_report(access_id=access_id)
    if grant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report grant not found.")
    return AdminCustomerReportGrantResponse.model_validate(grant)
