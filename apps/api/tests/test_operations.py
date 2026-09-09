from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from httpx import ASGITransport, AsyncClient

from rci_api.main import create_app
from rci_api.operations import _evidence_status, _migration_heads, _safe_error
from rci_core import AppSettings

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class FakeOperationsRepository:
    async def snapshot(self) -> dict[str, Any]:
        return {
            "migration_version": "0053_scope_projections",
            "collection_queued": 2,
            "collection_running": 1,
            "collection_expired": 0,
            "collection_failed_24h": 0,
            "analysis_queued": 0,
            "analysis_running": 0,
            "analysis_expired": 0,
            "analysis_failed_24h": 0,
            "recent_analysis_failures": [
                {
                    "run_id": f"failure-run-{index}",
                    "product_pack_id": "fresh_shell_eggs",
                    "product_pack_version": "1.3.1",
                    "attempt_count": 3,
                    "max_attempts": 3,
                    "last_error": (
                        "materialization failed api_key=must-not-leak"
                        if index == 0
                        else f"failure {index}"
                    ),
                    "created_at": datetime(2026, 8, 29, 10, tzinfo=UTC),
                    "started_at": datetime(2026, 8, 29, 11, tzinfo=UTC),
                    "completed_at": datetime(2026, 8, 29, 12, tzinfo=UTC),
                }
                for index in range(11)
            ],
            "pdp_queued": 0,
            "pdp_running": 0,
            "pdp_expired": 0,
            "pdp_failed_24h": 0,
            "ai_queued": 0,
            "ai_running": 0,
            "ai_expired": 0,
            "ai_needs_review_24h": 0,
            "report_queued": 0,
            "report_running": 0,
            "report_expired": 0,
            "report_blocked_24h": 0,
            "report_blocked_active": 2,
            "recent_report_materialization_failures": [
                {
                    "job_id": f"report-job-{index}",
                    "analysis_id": f"fresh_shell_eggs-analysis-{index}",
                    "product_pack_id": "fresh_shell_eggs",
                    "product_pack_version": "1.3.1",
                    "status": "blocked",
                    "stage": "blocked",
                    "progress_current": 6,
                    "progress_total": None,
                    "attempt_count": 3,
                    "max_attempts": 3,
                    "last_error": (
                        "materialization API 500 password=must-not-leak-either"
                        if index == 0
                        else f"report failure {index}"
                    ),
                    "created_at": datetime(2026, 8, 29, 9, tzinfo=UTC),
                    "started_at": datetime(2026, 8, 29, 10, tzinfo=UTC),
                    "completed_at": None,
                    "updated_at": datetime(2026, 8, 29, 12, tzinfo=UTC),
                }
                for index in range(11)
            ],
            "open_blockers": 0,
            "active_ready_reports": 6,
            "active_pending_reports": 0,
            "active_blocked_reports": 0,
            "provider_cooldowns": 0,
            "last_provider_429_at": None,
            "latest_collection_at": datetime(2026, 8, 28, tzinfo=UTC),
            "latest_ready_report_at": datetime(2026, 8, 29, tzinfo=UTC),
            "search_credits_30d": 120,
            "pdp_credits_30d": 30,
            "ai_estimated_cost_30d": 1.25,
            "ai_usage_unknown_30d": 1,
        }


def test_repository_migration_graph_has_one_expected_head() -> None:
    assert _migration_heads(REPOSITORY_ROOT) == ("0053_scope_projections",)


def test_recovery_evidence_fails_openly_when_not_recorded() -> None:
    assert _evidence_status(None, datetime.now(UTC) - datetime.now(UTC)) == "not_recorded"


def test_safe_error_redacts_credentials_and_bounds_operator_detail() -> None:
    safe = _safe_error(
        "Authorization: Bearer bearer-secret "
        "postgresql://operator:database-secret@db.internal/app "
        "token=session-secret " + ("diagnostic " * 200)
    )

    assert safe is not None
    assert "bearer-secret" not in safe
    assert "database-secret" not in safe
    assert "session-secret" not in safe
    assert safe.count("[REDACTED]") == 3
    assert len(safe) == 800
    assert safe.endswith("…")


async def test_operations_snapshot_exposes_live_controls_without_secrets(monkeypatch: Any) -> None:
    monkeypatch.setenv("RCI_REPOSITORY_ROOT", str(REPOSITORY_ROOT))
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "a" * 40)
    monkeypatch.setenv("METRICSCART_API_KEY", "must-not-leak")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-leak-either")
    monkeypatch.setenv("RCI_LAST_DATABASE_BACKUP_VERIFIED_AT", "2026-08-29T12:00:00Z")
    monkeypatch.setenv("RCI_LAST_RESTORE_DRILL_AT", "2026-08-01T12:00:00Z")
    app = create_app(AppSettings(app_env="development", app_version="1.2.3"))

    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        app.state.operations_repository = FakeOperationsRepository()
        response = await client.get("/api/v1/admin/operations")

    assert response.status_code == 200
    document = response.json()
    assert document["release"]["commit_sha"] == "a" * 40
    assert document["release"]["migration_matches"] is True
    assert document["release"]["product_packs"]
    assert document["release"]["retailer_packs"]
    assert document["queues"][0] == {
        "label": "Search collection",
        "state": "healthy",
        "queued": 2,
        "running": 1,
        "expired_leases": 0,
        "failures_24h": 0,
        "active_blocked": 0,
    }
    assert document["spend_30d"]["metricscart_estimated_usd"] == 0.3
    assert document["spend_30d"]["ai_estimated_usd"] == 1.25
    assert document["controls"]["collection_provider"] is None
    assert document["overall_state"] in {"healthy", "attention"}
    report_queue = next(
        queue for queue in document["queues"] if queue["label"] == "Report materialization"
    )
    assert report_queue["failures_24h"] == 0
    assert report_queue["active_blocked"] == 2
    assert report_queue["state"] == "attention"
    assert len(document["recent_analysis_failures"]) == 10
    analysis_failure = document["recent_analysis_failures"][0]
    assert {key: analysis_failure[key] for key in analysis_failure if not key.endswith("_at")} == {
        "run_id": "failure-run-0",
        "product_pack_id": "fresh_shell_eggs",
        "product_pack_version": "1.3.1",
        "attempt_count": 3,
        "max_attempts": 3,
        "last_error": "materialization failed api_key=[REDACTED]",
    }
    assert datetime.fromisoformat(analysis_failure["created_at"]) == datetime(
        2026, 8, 29, 10, tzinfo=UTC
    )
    assert len(document["recent_report_materialization_failures"]) == 10
    report_failure = document["recent_report_materialization_failures"][0]
    assert {key: report_failure[key] for key in report_failure if not key.endswith("_at")} == {
        "job_id": "report-job-0",
        "analysis_id": "fresh_shell_eggs-analysis-0",
        "product_pack_id": "fresh_shell_eggs",
        "product_pack_version": "1.3.1",
        "status": "blocked",
        "stage": "blocked",
        "progress_current": 6,
        "progress_total": None,
        "attempt_count": 3,
        "max_attempts": 3,
        "last_error": "materialization API 500 password=[REDACTED]",
    }
    assert datetime.fromisoformat(report_failure["updated_at"]) == datetime(
        2026, 8, 29, 12, tzinfo=UTC
    )
    assert report_failure["completed_at"] is None
    serialized = response.text
    assert "must-not-leak" not in serialized
    assert "METRICSCART_API_KEY" not in serialized


async def test_production_operations_requires_admin_token(monkeypatch: Any) -> None:
    monkeypatch.setenv("PRODUCT_PACK_ADMIN_TOKEN", "private-admin-token")
    app = create_app(AppSettings(app_env="production"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/admin/operations")

    assert response.status_code == 401
    assert "administrator" in response.json()["detail"].lower()
