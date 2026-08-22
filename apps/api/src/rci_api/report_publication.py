"""Durable, trust-gated report materialization and administrator status APIs."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from rci_api.analyses import get_analysis_service
from rci_api.competitive_leadership import (
    get_competitive_product_leadership_service,
)
from rci_api.competitive_release_audit import audit_competitive_portfolio_set
from rci_api.price_monitoring import get_price_monitoring_service

router = APIRouter(prefix="/api/v1")

PRICE_SCOPES = (
    ("benchmark_anchored", 0.5),
    ("fixed_range", 0.5),
    ("fixed_range", 1.0),
)


class PortfolioScopeRequest(BaseModel):
    profile_id: str = Field(min_length=1)
    radius_miles: int = Field(ge=1, le=5)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _checksum(document: dict[str, Any]) -> str:
    return hashlib.sha256(_json(document).encode()).hexdigest()


def _require_internal_token(provided: str | None) -> None:
    expected = os.getenv("RCI_INTERNAL_SERVICE_TOKEN", "").strip()
    if not expected or not provided or not secrets.compare_digest(expected, provided):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated internal service access is required.",
        )


def _require_admin(request: Request, provided: str | None) -> None:
    expected = os.getenv("PRODUCT_PACK_ADMIN_TOKEN", "").strip()
    if request.app.state.settings.is_production and (
        not expected or not provided or not secrets.compare_digest(expected, provided)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated administrator access is required.",
        )


async def _job_row(request: Request, job_id: str) -> dict[str, Any]:
    async with request.app.state.database_probe.engine.connect() as connection:
        row = (
            (
                await connection.execute(
                    text(
                        """
                        SELECT job.id::text, result.analysis_id, result.reporting_status,
                          run.product_pack_id, run.product_pack_version,
                          job.status, job.stage, job.progress_current, job.progress_total,
                          job.work_plan, job.audit_document, job.attempt_count,
                          job.max_attempts, job.available_at, job.locked_by,
                          job.locked_at, job.lease_expires_at, job.last_error,
                          job.started_at, job.completed_at, job.created_at, job.updated_at
                        FROM report_materialization_job job
                        JOIN analysis_result result ON result.id = job.analysis_result_id
                        JOIN analysis_run run ON run.id = result.analysis_run_id
                        WHERE job.id::text = :job_id
                        """
                    ),
                    {"job_id": job_id},
                )
            )
            .mappings()
            .first()
        )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job was not found.")
    return dict(row)


async def _require_lease(request: Request, job_id: str, worker_id: str | None) -> dict[str, Any]:
    row = await _job_row(request, job_id)
    if (
        not worker_id
        or row["status"] != "running"
        or row["locked_by"] != worker_id
        or row["lease_expires_at"] is None
        or row["lease_expires_at"] <= datetime.now(row["lease_expires_at"].tzinfo)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The report-materialization lease is no longer owned by this worker.",
        )
    return row


async def _stage_documents(
    request: Request,
    job_id: str,
    *,
    kind: str,
    documents: list[tuple[str, dict[str, Any]]],
    stage: str,
    worker_id: str,
) -> int:
    engine = request.app.state.database_probe.engine
    async with engine.begin() as connection:
        lease_owned = await connection.scalar(
            text(
                """
                SELECT 1 FROM report_materialization_job
                WHERE id = CAST(:job_id AS uuid) AND status = 'running'
                  AND locked_by = :worker_id AND lease_expires_at > now()
                FOR UPDATE
                """
            ),
            {"job_id": job_id, "worker_id": worker_id},
        )
        if lease_owned is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The report-materialization lease expired before staging.",
            )
        for scope_key, document in documents:
            await connection.execute(
                text(
                    """
                    INSERT INTO report_materialization_stage (
                      job_id, document_kind, scope_key, document, checksum
                    ) VALUES (
                      CAST(:job_id AS uuid), :kind, :scope_key,
                      CAST(:document AS jsonb), :checksum
                    )
                    ON CONFLICT ON CONSTRAINT report_materialization_stage_scope_uq
                    DO UPDATE SET document = EXCLUDED.document,
                                  checksum = EXCLUDED.checksum,
                                  updated_at = now()
                    """
                ),
                {
                    "job_id": job_id,
                    "kind": kind,
                    "scope_key": scope_key,
                    "document": _json(document),
                    "checksum": _checksum(document),
                },
            )
        completed = int(
            (
                await connection.execute(
                    text(
                        "SELECT COUNT(*) FROM report_materialization_stage "
                        "WHERE job_id = CAST(:job_id AS uuid)"
                    ),
                    {"job_id": job_id},
                )
            ).scalar_one()
        )
        await connection.execute(
            text(
                """
                UPDATE report_materialization_job
                SET stage = :stage, progress_current = :completed, updated_at = now()
                WHERE id = CAST(:job_id AS uuid)
                """
            ),
            {"job_id": job_id, "stage": stage, "completed": completed},
        )
    return completed


@router.post("/internal/report-materialization-jobs/{job_id}/prepare")
async def prepare_report_materialization(
    job_id: str,
    request: Request,
    x_rci_internal_token: Annotated[str | None, Header(alias="X-RCI-Internal-Token")] = None,
    x_rci_worker_id: Annotated[str | None, Header(alias="X-RCI-Worker-ID")] = None,
) -> dict[str, Any]:
    _require_internal_token(x_rci_internal_token)
    job = await _require_lease(request, job_id, x_rci_worker_id)
    report = await get_analysis_service(request).report_view(str(job["analysis_id"]))
    readiness = report.get("report_readiness")
    blockers = readiness.get("blocking_reasons", []) if isinstance(readiness, dict) else []
    if blockers:
        codes = sorted(
            {
                str(row.get("code") or "report_not_ready")
                for row in blockers
                if isinstance(row, dict)
            }
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Report is not decision-ready: " + ", ".join(codes),
        )
    profiles = sorted(
        {
            str(row["profile_id"])
            for row in report.get("comparison_bases", [])
            if isinstance(row, dict) and row.get("profile_id")
        }
    )
    if not profiles:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No governed comparison basis is available for publication.",
        )
    plan = {
        "schema_version": "1.0.0-report-materialization-plan",
        "analysis_id": str(job["analysis_id"]),
        "price_scopes": [f"{mode}:{increment:.2f}" for mode, increment in PRICE_SCOPES],
        "portfolio_scopes": [f"{profile}:{radius}" for profile in profiles for radius in (1, 3, 5)],
        "profiles": profiles,
        "radii": [1, 3, 5],
    }
    async with request.app.state.database_probe.engine.begin() as connection:
        completed_scopes = {
            str(row)
            for row in (
                await connection.execute(
                    text(
                        """
                        SELECT document_kind || ':' || scope_key
                        FROM report_materialization_stage
                        WHERE job_id = CAST(:job_id AS uuid)
                        """
                    ),
                    {"job_id": job_id},
                )
            ).scalars()
        }
        total = len(plan["price_scopes"]) + len(plan["portfolio_scopes"]) + 1
        updated = await connection.execute(
            text(
                """
                UPDATE report_materialization_job
                SET work_plan = CAST(:plan AS jsonb), stage = 'preparing',
                    progress_current = :completed, progress_total = :total,
                    updated_at = now()
                WHERE id = CAST(:job_id AS uuid) AND status = 'running'
                  AND locked_by = :worker_id AND lease_expires_at > now()
                """
            ),
            {
                "job_id": job_id,
                "plan": _json(plan),
                "completed": len(completed_scopes),
                "total": total,
                "worker_id": x_rci_worker_id,
            },
        )
        if not updated.rowcount:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The report-materialization lease expired during preparation.",
            )
    return {**plan, "completed_scopes": sorted(completed_scopes), "progress_total": total}


@router.post("/internal/report-materialization-jobs/{job_id}/price-architecture")
async def stage_price_architecture(
    job_id: str,
    request: Request,
    x_rci_internal_token: Annotated[str | None, Header(alias="X-RCI-Internal-Token")] = None,
    x_rci_worker_id: Annotated[str | None, Header(alias="X-RCI-Worker-ID")] = None,
) -> dict[str, Any]:
    _require_internal_token(x_rci_internal_token)
    job = await _require_lease(request, job_id, x_rci_worker_id)
    matrices = await get_price_monitoring_service(request).pre_materialize_architecture_matrices(
        str(job["analysis_id"]), refresh=True, publish=False
    )
    documents = []
    for matrix in matrices:
        filters = dict(matrix.get("filters") or {})
        scope = f"{filters.get('mode')}:{float(filters.get('fixed_increment') or 0):.2f}"
        documents.append((scope, matrix))
    completed = await _stage_documents(
        request,
        job_id,
        kind="price_architecture",
        documents=documents,
        stage="price_architecture",
        worker_id=str(x_rci_worker_id),
    )
    return {"status": "staged", "matrix_count": len(documents), "progress_current": completed}


@router.post("/internal/report-materialization-jobs/{job_id}/competitive-portfolio")
async def stage_competitive_portfolio(
    job_id: str,
    scope: PortfolioScopeRequest,
    request: Request,
    x_rci_internal_token: Annotated[str | None, Header(alias="X-RCI-Internal-Token")] = None,
    x_rci_worker_id: Annotated[str | None, Header(alias="X-RCI-Worker-ID")] = None,
) -> dict[str, Any]:
    _require_internal_token(x_rci_internal_token)
    job = await _require_lease(request, job_id, x_rci_worker_id)
    if scope.radius_miles not in {1, 3, 5}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Competitive radius must be 1, 3, or 5 miles.",
        )
    document = await get_competitive_product_leadership_service(request).portfolio_view(
        str(job["analysis_id"]),
        competitor_id="all",
        profile_id=scope.profile_id,
        radius_miles=scope.radius_miles,  # type: ignore[arg-type]
        state=None,
        city=None,
        refresh=True,
        publish=False,
    )
    completed = await _stage_documents(
        request,
        job_id,
        kind="competitive_portfolio",
        documents=[(f"{scope.profile_id}:{scope.radius_miles}", document)],
        stage=f"competitive_portfolio:{scope.profile_id}:{scope.radius_miles}",
        worker_id=str(x_rci_worker_id),
    )
    return {"status": "staged", "progress_current": completed}


@router.post("/internal/report-materialization-jobs/{job_id}/finalize")
async def finalize_report_materialization(
    job_id: str,
    request: Request,
    x_rci_internal_token: Annotated[str | None, Header(alias="X-RCI-Internal-Token")] = None,
    x_rci_worker_id: Annotated[str | None, Header(alias="X-RCI-Worker-ID")] = None,
) -> dict[str, Any]:
    _require_internal_token(x_rci_internal_token)
    job = await _require_lease(request, job_id, x_rci_worker_id)
    plan = dict(job.get("work_plan") or {})
    profiles = [str(row) for row in plan.get("profiles", [])]
    async with request.app.state.database_probe.engine.connect() as connection:
        staged = [
            dict(row)
            for row in (
                await connection.execute(
                    text(
                        """
                        SELECT document_kind, scope_key, document, checksum
                        FROM report_materialization_stage
                        WHERE job_id = CAST(:job_id AS uuid)
                        ORDER BY document_kind, scope_key
                        """
                    ),
                    {"job_id": job_id},
                )
            ).mappings()
        ]
    price_rows = [row for row in staged if row["document_kind"] == "price_architecture"]
    portfolio_rows = [row for row in staged if row["document_kind"] == "competitive_portfolio"]
    expected_price = set(plan.get("price_scopes", []))
    expected_portfolio = set(plan.get("portfolio_scopes", []))
    actual_price = {str(row["scope_key"]) for row in price_rows}
    actual_portfolio = {str(row["scope_key"]) for row in portfolio_rows}
    portfolio_audit = audit_competitive_portfolio_set(
        [dict(row["document"]) for row in portfolio_rows],
        expected_profiles=profiles,
    )
    gate_findings = list(portfolio_audit["findings"])
    if actual_price != expected_price:
        gate_findings.append(
            {
                "severity": "error",
                "code": "price_architecture_matrix_incomplete",
                "message": "All three default Price Architecture matrices are required.",
                "context": {
                    "expected": sorted(expected_price),
                    "actual": sorted(actual_price),
                },
            }
        )
    if actual_portfolio != expected_portfolio:
        gate_findings.append(
            {
                "severity": "error",
                "code": "competitive_portfolio_matrix_incomplete",
                "message": "Every configured basis-by-radius portfolio is required.",
                "context": {
                    "expected": sorted(expected_portfolio),
                    "actual": sorted(actual_portfolio),
                },
            }
        )
    error_count = sum(row["severity"] == "error" for row in gate_findings)
    warning_count = sum(row["severity"] == "warning" for row in gate_findings)
    audit = {
        **portfolio_audit,
        "schema_version": "1.0.0-report-publication-trust-gate",
        "status": "passed" if error_count == 0 else "failed",
        "price_architecture_document_count": len(price_rows),
        "competitive_portfolio_document_count": len(portfolio_rows),
        "error_count": error_count,
        "warning_count": warning_count,
        "findings": gate_findings,
    }
    if error_count:
        async with request.app.state.database_probe.engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE report_materialization_job SET audit_document = CAST(:audit AS jsonb), "
                    "stage = 'semantic_audit_failed', updated_at = now() "
                    "WHERE id = CAST(:job_id AS uuid) AND status = 'running' "
                    "AND locked_by = :worker_id AND lease_expires_at > now()"
                ),
                {
                    "job_id": job_id,
                    "audit": _json(audit),
                    "worker_id": x_rci_worker_id,
                },
            )
        codes = sorted({row["code"] for row in gate_findings if row["severity"] == "error"})
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Report publication trust gate failed: " + ", ".join(codes),
        )

    engine = request.app.state.database_probe.engine
    async with engine.begin() as connection:
        locked = (
            (
                await connection.execute(
                    text(
                        """
                        SELECT job.analysis_result_id::text, result.analysis_id,
                          run.product_pack_id, job.progress_total
                        FROM report_materialization_job job
                        JOIN analysis_result result ON result.id = job.analysis_result_id
                        JOIN analysis_run run ON run.id = result.analysis_run_id
                        WHERE job.id = CAST(:job_id AS uuid)
                          AND job.status = 'running' AND job.locked_by = :worker_id
                          AND job.lease_expires_at > now()
                        FOR UPDATE OF job, result
                        """
                    ),
                    {"job_id": job_id, "worker_id": x_rci_worker_id},
                )
            )
            .mappings()
            .first()
        )
        if locked is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The report-materialization lease expired before publication.",
            )
        analysis_result_id = str(locked["analysis_result_id"])
        for row in price_rows:
            document = dict(row["document"])
            filters = dict(document.get("filters") or {})
            await connection.execute(
                text(
                    """
                    INSERT INTO price_architecture_materialization (
                      analysis_result_id, mode, fixed_increment, brand_type,
                      brand, state, city, zipcode, source_revision, document
                    )
                    SELECT id, :mode, CAST(:fixed_increment AS numeric), :brand_type,
                      :brand, :state, :city, :zipcode, checksum, CAST(:document AS jsonb)
                    FROM analysis_result WHERE id = CAST(:analysis_result_id AS uuid)
                    ON CONFLICT ON CONSTRAINT price_architecture_materialization_scope_uq
                    DO UPDATE SET source_revision = EXCLUDED.source_revision,
                                  document = EXCLUDED.document,
                                  materialized_at = now()
                    """
                ),
                {
                    "analysis_result_id": analysis_result_id,
                    "mode": str(filters.get("mode") or "benchmark_anchored"),
                    "fixed_increment": float(filters.get("fixed_increment") or 0.5),
                    "brand_type": str(filters.get("brand_type") or "all"),
                    "brand": str(filters.get("brand") or ""),
                    "state": str(filters.get("state") or ""),
                    "city": str(filters.get("city") or ""),
                    "zipcode": str(filters.get("zipcode") or ""),
                    "document": _json(document),
                },
            )
        for row in portfolio_rows:
            document = dict(row["document"])
            filters = dict(document.get("filters") or {})
            await connection.execute(
                text(
                    """
                    INSERT INTO competitive_portfolio_materialization (
                      analysis_result_id, profile_id, radius_miles,
                      source_revision, document
                    )
                    SELECT id, :profile_id, :radius_miles, checksum, CAST(:document AS jsonb)
                    FROM analysis_result WHERE id = CAST(:analysis_result_id AS uuid)
                    ON CONFLICT ON CONSTRAINT competitive_portfolio_materialization_scope_uq
                    DO UPDATE SET source_revision = EXCLUDED.source_revision,
                                  document = EXCLUDED.document,
                                  materialized_at = now()
                    """
                ),
                {
                    "analysis_result_id": analysis_result_id,
                    "profile_id": str(filters.get("profile_id") or ""),
                    "radius_miles": int(filters.get("radius_miles") or 0),
                    "document": _json(document),
                },
            )
        archived_ids = [
            str(row)
            for row in (
                await connection.execute(
                    text(
                        """
                        UPDATE analysis_result predecessor
                        SET archived_at = now()
                        FROM analysis_run predecessor_run
                        WHERE predecessor.analysis_run_id = predecessor_run.id
                          AND predecessor_run.product_pack_id = :product_pack_id
                          AND predecessor.id <> CAST(:analysis_result_id AS uuid)
                          AND predecessor.reporting_status = 'ready'
                          AND predecessor.archived_at IS NULL
                        RETURNING predecessor.id::text
                        """
                    ),
                    {
                        "product_pack_id": str(locked["product_pack_id"]),
                        "analysis_result_id": analysis_result_id,
                    },
                )
            ).scalars()
        ]
        await connection.execute(
            text(
                """
                UPDATE analysis_result
                SET reporting_status = 'ready', archived_at = NULL
                WHERE id = CAST(:analysis_result_id AS uuid)
                """
            ),
            {"analysis_result_id": analysis_result_id},
        )
        await connection.execute(
            text(
                """
                UPDATE report_materialization_job
                SET status = 'succeeded', stage = 'complete',
                    progress_current = progress_total,
                    audit_document = CAST(:audit AS jsonb), completed_at = now(),
                    locked_by = NULL, locked_at = NULL, lease_expires_at = NULL,
                    last_error = NULL, updated_at = now()
                WHERE id = CAST(:job_id AS uuid)
                """
            ),
            {"job_id": job_id, "audit": _json(audit)},
        )
        await connection.execute(
            text(
                """
                INSERT INTO audit_event (
                  organization_id, event_type, entity_type, entity_id, details
                ) VALUES (
                  '00000000-0000-0000-0000-000000000001',
                  'report_publication_gate_passed', 'analysis_result', :entity_id,
                  CAST(:details AS jsonb)
                )
                """
            ),
            {
                "entity_id": str(locked["analysis_id"]),
                "details": _json(
                    {
                        "job_id": job_id,
                        "audit": audit,
                        "recoverably_archived_predecessor_ids": archived_ids,
                    }
                ),
            },
        )
    return {
        "status": "published",
        "analysis_id": str(job["analysis_id"]),
        "audit": audit,
        "archived_predecessor_count": len(archived_ids),
    }


@router.get("/admin/report-materialization-jobs")
async def list_report_materialization_jobs(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> list[dict[str, Any]]:
    _require_admin(request, x_rci_admin_token)
    async with request.app.state.database_probe.engine.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    """
                    SELECT job.id::text, result.analysis_id, result.reporting_status,
                      run.product_pack_id, run.product_pack_version,
                      job.status, job.stage, job.progress_current, job.progress_total,
                      job.audit_document, job.attempt_count, job.max_attempts,
                      job.available_at, job.last_error, job.started_at,
                      job.completed_at, job.created_at, job.updated_at
                    FROM report_materialization_job job
                    JOIN analysis_result result ON result.id = job.analysis_result_id
                    JOIN analysis_run run ON run.id = result.analysis_run_id
                    ORDER BY job.created_at DESC LIMIT :limit
                    """
                ),
                {"limit": limit},
            )
        ).mappings()
        return [dict(row) for row in rows]


@router.post("/admin/report-materialization-jobs/{job_id}/retry")
async def retry_report_materialization_job(
    job_id: str,
    request: Request,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> dict[str, Any]:
    _require_admin(request, x_rci_admin_token)
    async with request.app.state.database_probe.engine.begin() as connection:
        row = (
            await connection.execute(
                text(
                    """
                        UPDATE report_materialization_job job
                        SET status = 'queued', stage = 'queued', available_at = now(),
                            attempt_count = 0, progress_current = 0,
                            locked_by = NULL, locked_at = NULL, lease_expires_at = NULL,
                            last_error = NULL, completed_at = NULL, updated_at = now()
                        WHERE job.id = CAST(:job_id AS uuid)
                          AND job.status IN ('blocked', 'retry_wait')
                        RETURNING job.analysis_result_id::text
                        """
                ),
                {"job_id": job_id},
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only blocked or retry-wait jobs can be manually retried.",
            )
        await connection.execute(
            text("DELETE FROM report_materialization_stage WHERE job_id = CAST(:job_id AS uuid)"),
            {"job_id": job_id},
        )
        await connection.execute(
            text(
                "UPDATE analysis_result SET reporting_status = 'pending' "
                "WHERE id::text = :analysis_result_id"
            ),
            {"analysis_result_id": str(row)},
        )
    return {"status": "queued", "job_id": job_id}
