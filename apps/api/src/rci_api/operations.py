"""Protected production operations, release, queue, and spend snapshot."""

from __future__ import annotations

import os
import re
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Protocol

from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from rci_product_packs import FileProductPackCatalog
from rci_retailer_packs import FileRetailerPackCatalog

router = APIRouter(prefix="/api/v1")


class OperationsSnapshotRepository(Protocol):
    async def snapshot(self) -> dict[str, Any]: ...


def _require_admin(request: Request, provided: str | None) -> None:
    expected = os.getenv("PRODUCT_PACK_ADMIN_TOKEN", "").strip()
    if request.app.state.settings.is_production and (
        not expected or not provided or not secrets.compare_digest(expected, provided)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated administrator access is required.",
        )


def _repository_root() -> Path:
    return Path(os.getenv("RCI_REPOSITORY_ROOT", Path.cwd())).resolve()


def _migration_heads(root: Path) -> tuple[str, ...]:
    revisions: set[str] = set()
    parents: set[str] = set()
    for path in sorted((root / "database" / "migrations" / "versions").glob("*.py")):
        body = path.read_text(encoding="utf-8")
        revision = re.search(r'^revision:.*?=\s*["\']([^"\']+)["\']', body, re.MULTILINE)
        parent = re.search(r'^down_revision:.*?=\s*["\']([^"\']+)["\']', body, re.MULTILINE)
        if revision:
            revisions.add(revision.group(1))
        if parent:
            parents.add(parent.group(1))
    return tuple(sorted(revisions - parents))


def _parse_timestamp(name: str) -> datetime | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _evidence_status(observed_at: datetime | None, maximum_age: timedelta) -> str:
    if observed_at is None:
        return "not_recorded"
    return "current" if datetime.now(UTC) - observed_at <= maximum_age else "stale"


def _enabled(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


class PostgresOperationsSnapshotRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def snapshot(self) -> dict[str, Any]:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT
                              (SELECT version_num FROM alembic_version LIMIT 1)
                                AS migration_version,
                              (SELECT COUNT(*) FROM collection_task
                                WHERE status = 'pending') AS collection_queued,
                              (SELECT COUNT(*) FROM collection_task
                                WHERE status = 'running') AS collection_running,
                              (SELECT COUNT(*) FROM collection_task
                                WHERE status = 'running' AND lease_expires_at < now())
                                AS collection_expired,
                              (SELECT COUNT(*) FROM collection_task
                                WHERE status = 'failed'
                                  AND COALESCE(completed_at, created_at)
                                    >= now() - interval '24 hours')
                                AS collection_failed_24h,
                              (SELECT COUNT(*) FROM analysis_run
                                WHERE status = 'queued') AS analysis_queued,
                              (SELECT COUNT(*) FROM analysis_run
                                WHERE status = 'running') AS analysis_running,
                              (SELECT COUNT(*) FROM analysis_run
                                WHERE status = 'running' AND lease_expires_at < now())
                                AS analysis_expired,
                              (SELECT COUNT(*) FROM analysis_run
                                WHERE status = 'failed'
                                  AND COALESCE(completed_at, created_at)
                                    >= now() - interval '24 hours')
                                AS analysis_failed_24h,
                              (SELECT COUNT(*) FROM product_detail_job
                                WHERE status = 'queued') AS pdp_queued,
                              (SELECT COUNT(*) FROM product_detail_job
                                WHERE status = 'running') AS pdp_running,
                              (SELECT COUNT(*) FROM product_detail_job
                                WHERE status = 'running' AND lease_expires_at < now())
                                AS pdp_expired,
                              (SELECT COUNT(*) FROM product_detail_job
                                WHERE status = 'failed'
                                  AND COALESCE(completed_at, created_at)
                                    >= now() - interval '24 hours')
                                AS pdp_failed_24h,
                              (SELECT COUNT(*) FROM matching_v2_ai_review_task
                                WHERE status = 'queued') AS ai_queued,
                              (SELECT COUNT(*) FROM matching_v2_ai_review_task
                                WHERE status = 'running') AS ai_running,
                              (SELECT COUNT(*) FROM matching_v2_ai_review_task
                                WHERE status = 'running' AND lease_expires_at < now())
                                AS ai_expired,
                              (SELECT COUNT(*) FROM matching_v2_ai_review_task
                                WHERE status = 'needs_review'
                                  AND updated_at >= now() - interval '24 hours')
                                AS ai_needs_review_24h,
                              (SELECT COUNT(*) FROM report_materialization_job
                                WHERE status IN ('awaiting_publication','queued','retry_wait'))
                                AS report_queued,
                              (SELECT COUNT(*) FROM report_materialization_job
                                WHERE status = 'running') AS report_running,
                              (SELECT COUNT(*) FROM report_materialization_job
                                WHERE status = 'running' AND lease_expires_at < now())
                                AS report_expired,
                              (SELECT COUNT(*) FROM report_materialization_job job
                                JOIN analysis_result result
                                  ON result.id = job.analysis_result_id
                                WHERE job.status = 'blocked'
                                  AND result.archived_at IS NULL) AS report_blocked,
                              (SELECT COUNT(*) FROM validation_issue issue
                                LEFT JOIN analysis_result result
                                  ON result.analysis_run_id = issue.analysis_run_id
                                WHERE issue.severity = 'blocker'
                                  AND issue.status = 'open'
                                  AND (
                                    (result.id IS NOT NULL AND result.archived_at IS NULL)
                                    OR issue.created_at >= now() - interval '24 hours'
                                  )) AS open_blockers,
                              (SELECT COUNT(*) FROM analysis_result
                                WHERE archived_at IS NULL AND reporting_status = 'ready')
                                AS active_ready_reports,
                              (SELECT COUNT(*) FROM analysis_result
                                WHERE archived_at IS NULL AND reporting_status = 'pending')
                                AS active_pending_reports,
                              (SELECT COUNT(*) FROM analysis_result
                                WHERE archived_at IS NULL AND reporting_status = 'blocked')
                                AS active_blocked_reports,
                              (SELECT COUNT(*) FROM provider_rate_limit_state
                                WHERE paused_until > now()) AS provider_cooldowns,
                              (SELECT MAX(last_429_at) FROM provider_rate_limit_state)
                                AS last_provider_429_at,
                              (SELECT MAX(completed_at) FROM collection_run
                                WHERE status = 'succeeded') AS latest_collection_at,
                              (SELECT MAX(created_at) FROM analysis_result
                                WHERE archived_at IS NULL AND reporting_status = 'ready')
                                AS latest_ready_report_at,
                              (SELECT COALESCE(SUM(billable_credits), 0) FROM collection_task
                                WHERE created_at >= now() - interval '30 days')
                                AS search_credits_30d,
                              (SELECT COALESCE(SUM(billable_credits), 0) FROM product_detail_job
                                WHERE created_at >= now() - interval '30 days')
                                AS pdp_credits_30d,
                              (SELECT COALESCE(SUM(
                                  CASE WHEN usage->>'estimated_cost_usd' ~ '^[0-9]+(\\.[0-9]+)?$'
                                    THEN (usage->>'estimated_cost_usd')::numeric ELSE 0 END
                                ), 0) FROM matching_v2_ai_review_task
                                WHERE created_at >= now() - interval '30 days')
                                +
                              (SELECT COALESCE(SUM(
                                  CASE WHEN usage->>'estimated_cost_usd' ~ '^[0-9]+(\\.[0-9]+)?$'
                                    THEN (usage->>'estimated_cost_usd')::numeric ELSE 0 END
                                ), 0) FROM agent_task
                                WHERE created_at >= now() - interval '30 days')
                                AS ai_estimated_cost_30d,
                              (SELECT COUNT(*) FROM matching_v2_ai_review_task
                                WHERE created_at >= now() - interval '30 days'
                                  AND status IN ('succeeded','needs_review')
                                  AND NOT (usage ? 'estimated_cost_usd'))
                                +
                              (SELECT COUNT(*) FROM agent_task
                                WHERE created_at >= now() - interval '30 days'
                                  AND status IN ('succeeded','needs_review')
                                  AND NOT (usage ? 'estimated_cost_usd'))
                                AS ai_usage_unknown_30d
                            """
                        )
                    )
                )
                .mappings()
                .one()
            )
        return dict(row)


def _queue(
    label: str,
    *,
    queued: int,
    running: int,
    expired: int,
    recent_failures: int,
) -> dict[str, Any]:
    state = "blocked" if expired else "attention" if recent_failures else "healthy"
    return {
        "label": label,
        "state": state,
        "queued": queued,
        "running": running,
        "expired_leases": expired,
        "failures_24h": recent_failures,
    }


async def _build_snapshot(
    request: Request, repository: OperationsSnapshotRepository
) -> dict[str, Any]:
    row = await repository.snapshot()
    root = _repository_root()
    product_packs = await FileProductPackCatalog(root).list_active()
    retailer_packs = FileRetailerPackCatalog(root).active_versions()
    expected_heads = _migration_heads(root)
    current_migration = str(row["migration_version"])
    queues = [
        _queue(
            "Search collection",
            queued=int(row["collection_queued"]),
            running=int(row["collection_running"]),
            expired=int(row["collection_expired"]),
            recent_failures=int(row["collection_failed_24h"]),
        ),
        _queue(
            "Analysis",
            queued=int(row["analysis_queued"]),
            running=int(row["analysis_running"]),
            expired=int(row["analysis_expired"]),
            recent_failures=int(row["analysis_failed_24h"]),
        ),
        _queue(
            "PDP enrichment",
            queued=int(row["pdp_queued"]),
            running=int(row["pdp_running"]),
            expired=int(row["pdp_expired"]),
            recent_failures=int(row["pdp_failed_24h"]),
        ),
        _queue(
            "Matching AI review",
            queued=int(row["ai_queued"]),
            running=int(row["ai_running"]),
            expired=int(row["ai_expired"]),
            recent_failures=int(row["ai_needs_review_24h"]),
        ),
        _queue(
            "Report materialization",
            queued=int(row["report_queued"]),
            running=int(row["report_running"]),
            expired=int(row["report_expired"]),
            recent_failures=int(row["report_blocked"]),
        ),
    ]
    backup_at = _parse_timestamp("RCI_LAST_DATABASE_BACKUP_VERIFIED_AT")
    restore_at = _parse_timestamp("RCI_LAST_RESTORE_DRILL_AT")
    migration_matches = current_migration in expected_heads
    overall_state = (
        "blocked"
        if not migration_matches
        or any(queue["state"] == "blocked" for queue in queues)
        or int(row["open_blockers"])
        else "attention"
        if any(queue["state"] == "attention" for queue in queues)
        or int(row["provider_cooldowns"])
        or _evidence_status(backup_at, timedelta(hours=24)) != "current"
        or _evidence_status(restore_at, timedelta(days=90)) != "current"
        else "healthy"
    )
    credit_usd = float(os.getenv("METRICSCART_CREDIT_USD", "0.002"))
    return {
        "schema_version": "1.0.0-system-operations",
        "generated_at": datetime.now(UTC).isoformat(),
        "overall_state": overall_state,
        "release": {
            "app_version": request.app.state.settings.app_version,
            "commit_sha": os.getenv("RAILWAY_GIT_COMMIT_SHA")
            or os.getenv("GIT_COMMIT_SHA")
            or "unavailable",
            "deployment_id": os.getenv("RAILWAY_DEPLOYMENT_ID") or "unavailable",
            "environment": os.getenv("RAILWAY_ENVIRONMENT_NAME")
            or request.app.state.settings.app_env,
            "service": os.getenv("RAILWAY_SERVICE_NAME") or "api",
            "database_migration": current_migration,
            "expected_migration_heads": list(expected_heads),
            "migration_matches": migration_matches,
            "product_packs": [
                {"id": pack.id, "version": pack.version, "checksum": pack.checksum}
                for pack in product_packs
            ],
            "retailer_packs": [
                {"id": pack.id, "version": pack.version, "checksum": pack.checksum}
                for pack in sorted(retailer_packs.values(), key=lambda item: item.id)
            ],
        },
        "queues": queues,
        "publication": {
            "active_ready_reports": int(row["active_ready_reports"]),
            "active_pending_reports": int(row["active_pending_reports"]),
            "active_blocked_reports": int(row["active_blocked_reports"]),
            "open_validation_blockers": int(row["open_blockers"]),
            "latest_ready_report_at": row["latest_ready_report_at"],
            "latest_successful_collection_at": row["latest_collection_at"],
        },
        "provider": {
            "active_cooldowns": int(row["provider_cooldowns"]),
            "last_429_at": row["last_provider_429_at"],
            "global_rps": int(os.getenv("METRICSCART_GLOBAL_RPS", "2")),
            "global_rpm": int(os.getenv("METRICSCART_GLOBAL_RPM", "108")),
            "maximum_attempts": int(os.getenv("METRICSCART_MAX_ATTEMPTS", "5")),
        },
        "spend_30d": {
            "search_credits": int(row["search_credits_30d"]),
            "pdp_credits": int(row["pdp_credits_30d"]),
            "metricscart_estimated_usd": round(
                (int(row["search_credits_30d"]) + int(row["pdp_credits_30d"])) * credit_usd,
                4,
            ),
            "ai_estimated_usd": round(float(row["ai_estimated_cost_30d"]), 4),
            "ai_completed_tasks_without_cost": int(row["ai_usage_unknown_30d"]),
            "provider_billing_is_authoritative": True,
        },
        "controls": {
            "collection_provider": os.getenv("COLLECTION_PROVIDER") or None,
            "product_detail_enrichment_enabled": _enabled("PRODUCT_DETAIL_ENRICHMENT_ENABLED"),
            "analysis_pipeline_enabled": _enabled("ANALYSIS_PIPELINE_ENABLED", "true"),
            "matching_ai_review_enabled": _enabled("MATCHING_V2_AI_REVIEW_ENABLED"),
            "ai_enabled": _enabled("AI_ENABLED"),
            "openai_matching_max_request_cost_usd": float(
                os.getenv("OPENAI_MATCHING_MAX_REQUEST_COST_USD", "0.35")
            ),
        },
        "recovery": {
            "database_backup": {
                "status": _evidence_status(backup_at, timedelta(hours=24)),
                "verified_at": backup_at,
                "maximum_age_hours": 24,
            },
            "restore_drill": {
                "status": _evidence_status(restore_at, timedelta(days=90)),
                "verified_at": restore_at,
                "maximum_age_days": 90,
            },
            "evidence_source": "operator-attested Railway environment timestamps",
        },
    }


def get_operations_repository(request: Request) -> OperationsSnapshotRepository:
    override = getattr(request.app.state, "operations_repository", None)
    if override is not None:
        return override
    return PostgresOperationsSnapshotRepository(request.app.state.database_probe.engine)


@router.get("/admin/operations")
async def operations_snapshot(
    request: Request,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> dict[str, Any]:
    _require_admin(request, x_rci_admin_token)
    return await _build_snapshot(request, get_operations_repository(request))
