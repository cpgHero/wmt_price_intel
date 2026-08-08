from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text

from rci_automation.models import ScheduleSource
from rci_automation.repository import PostgresAutomationRepository
from rci_collections.models import CollectionPlan, CostEstimate
from rci_collections.planner import canonical_checksum
from rci_collections.repository import PostgresCollectionRepository
from rci_db import DatabaseProbe
from rci_results import (
    AnalysisResultService,
    AnalysisResultValidator,
    InMemoryReportObjectStore,
    PostgresResultsRepository,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


@pytest.mark.skipif(
    not os.getenv("RCI_TEST_DATABASE_URL"),
    reason="set RCI_TEST_DATABASE_URL to run Postgres automation integration",
)
async def test_postgres_schedule_and_email_claims_are_exclusive_and_idempotent() -> None:
    database = DatabaseProbe(os.environ["RCI_TEST_DATABASE_URL"])
    collections = PostgresCollectionRepository(database.engine)
    automation = PostgresAutomationRepository(database.engine)
    stable_key = f"automation-test-{uuid4()}"
    config: dict[str, object] = {
        "id": stable_key,
        "name": "Automation persistence test",
        "enabled": True,
        "schedule": {"type": "cron", "cron": "* * * * *", "timezone": "UTC"},
        "delivery": {"leadership_email": False},
    }
    definition = await collections.publish_definition(config, canonical_checksum(config))
    run = await collections.create_run(
        definition,
        CollectionPlan(
            estimate=CostEstimate(
                definition_id=stable_key,
                retailers=(),
                estimated_total_pages=0,
                estimated_total_credits=0,
            ),
            initial_tasks=(),
        ),
    )
    document = json.loads(
        (REPOSITORY_ROOT / "examples" / "analysis-result.strawberries.json").read_text()
    )
    analysis_id = f"analysis-{uuid4()}"
    document["analysis_id"] = analysis_id
    document["collection_run_id"] = run.id
    result_service = AnalysisResultService(
        PostgresResultsRepository(database.engine),
        AnalysisResultValidator(REPOSITORY_ROOT),
        InMemoryReportObjectStore(),
    )
    analysis = await result_service.publish(document)
    try:
        source = ScheduleSource(definition.id, stable_key, True, config)
        await automation.upsert_schedule(
            source,
            cron_expression="* * * * *",
            timezone="UTC",
            enabled=True,
            next_run_at=datetime.now(UTC) - timedelta(minutes=1),
        )
        claims = await asyncio.gather(
            automation.claim_due_schedules("scheduler-a", limit=1, lease_seconds=30),
            automation.claim_due_schedules("scheduler-b", limit=1, lease_seconds=30),
        )
        assert sum(len(rows) for rows in claims) == 1
        claimed = next(rows[0] for rows in claims if rows)
        await automation.complete_schedule(
            claimed,
            next_run_at=datetime.now(UTC) + timedelta(minutes=1),
            collection_run_id=run.id,
            error=None,
        )
        assert (await automation.list_schedules())[0].last_collection_run_id == run.id

        analysis_claims = await asyncio.gather(
            automation.claim_analyses("scheduler-a", limit=10_000, lease_seconds=30),
            automation.claim_analyses("scheduler-b", limit=10_000, lease_seconds=30),
        )
        claimed_analyses = [
            context
            for contexts in analysis_claims
            for context in contexts
            if context.analysis_result_id == analysis.id
        ]
        assert len(claimed_analyses) == 1
        claim_owner = "scheduler-a" if claimed_analyses[0] in analysis_claims[0] else "scheduler-b"
        await automation.complete_analysis(analysis.id, claim_owner, None)

        context = await automation.get_analysis(analysis_id)
        assert context is not None
        first = await automation.enqueue_email(
            context,
            alert_event=None,
            delivery_type="analysis_report",
            recipients=("leadership@example.com",),
            subject="Test",
            text_body="Evidence-backed delivery",
            html_body=None,
            evidence={"analysis_id": analysis_id, "checksum": analysis.checksum},
            idempotency_key=f"test:{analysis_id}",
        )
        repeated = await automation.enqueue_email(
            context,
            alert_event=None,
            delivery_type="analysis_report",
            recipients=("leadership@example.com",),
            subject="Test",
            text_body="Evidence-backed delivery",
            html_body=None,
            evidence={"analysis_id": analysis_id, "checksum": analysis.checksum},
            idempotency_key=f"test:{analysis_id}",
        )
        assert repeated.id == first.id
        email_claims = await asyncio.gather(
            automation.claim_emails("scheduler-a", limit=1, lease_seconds=30),
            automation.claim_emails("scheduler-b", limit=1, lease_seconds=30),
        )
        assert sum(len(rows) for rows in email_claims) == 1
    finally:
        async with database.engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM email_delivery WHERE analysis_result_id::text = :analysis_id"),
                {"analysis_id": analysis.id},
            )
            await connection.execute(
                text(
                    "UPDATE collection_schedule SET last_collection_run_id = NULL "
                    "WHERE definition_id::text = :definition_id"
                ),
                {"definition_id": definition.id},
            )
            await connection.execute(
                text("DELETE FROM collection_schedule WHERE definition_id::text = :definition_id"),
                {"definition_id": definition.id},
            )
            await connection.execute(
                text(
                    "DELETE FROM analysis_automation_state "
                    "WHERE analysis_result_id::text = :analysis_id"
                ),
                {"analysis_id": analysis.id},
            )
            await connection.execute(
                text("DELETE FROM analysis_result WHERE analysis_run_id::text = :analysis_run_id"),
                {"analysis_run_id": analysis.analysis_run_id},
            )
            await connection.execute(
                text("DELETE FROM analysis_run WHERE id::text = :analysis_run_id"),
                {"analysis_run_id": analysis.analysis_run_id},
            )
            await connection.execute(
                text("DELETE FROM collection_run WHERE id::text = :run_id"),
                {"run_id": run.id},
            )
            await connection.execute(
                text(
                    "DELETE FROM collection_definition_version "
                    "WHERE definition_id::text = :definition_id"
                ),
                {"definition_id": definition.id},
            )
            await connection.execute(
                text("DELETE FROM collection_definition WHERE id::text = :definition_id"),
                {"definition_id": definition.id},
            )
        await database.dispose()
