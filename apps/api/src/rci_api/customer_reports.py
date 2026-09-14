"""Customer-owned report listing APIs.

These routes expose only reports explicitly granted to the resolved CPGHero
customer account/workspace. They do not infer customer access from legacy
organization-wide report rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Protocol

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.types import Integer, String

from rci_api.customer_access import (
    current_customer_access_principal,
    enforce_customer_access,
)
from rci_core import AccessPrincipal

router = APIRouter(prefix="/api/v1/customer", tags=["customer-reports"])


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


class CustomerReportRepository(Protocol):
    async def list_reports(
        self,
        *,
        account_id: str,
        workspace_id: str | None,
        limit: int,
    ) -> list[CustomerReportSummary]: ...


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
