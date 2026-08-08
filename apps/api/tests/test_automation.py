from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from httpx import ASGITransport, AsyncClient

from rci_api.automation import get_automation_service
from rci_api.main import create_app
from rci_automation.memory import InMemoryAutomationRepository, RecordingEmailSender
from rci_automation.models import AnalysisContext
from rci_automation.service import AutomationService
from rci_collections import (
    CollectionPlanner,
    CollectionRetailerCatalog,
    InMemoryCollectionRepository,
)
from rci_collections.service import CollectionService
from rci_results.models import AnalysisRecord

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _context(analysis_id: str, created_at: datetime, rate: float) -> AnalysisContext:
    document = json.loads(
        (REPOSITORY_ROOT / "examples" / "analysis-result.strawberries.json").read_text()
    )
    document["analysis_id"] = analysis_id
    document["generated_at"] = created_at.isoformat()
    document["comparisons"][1]["competitor_lower_rate"] = rate
    result_id = f"result-{analysis_id}"
    record = AnalysisRecord(
        id=result_id,
        analysis_run_id=f"analysis-run-{analysis_id}",
        analysis_id=analysis_id,
        collection_run_id=f"collection-run-{analysis_id}",
        status="succeeded",
        product_pack_id="fresh_strawberries",
        product_pack_version="1.0.0",
        schema_version="1.0.0",
        checksum=f"checksum-{analysis_id}",
        result=document,
        created_at=created_at,
    )
    return AnalysisContext(
        analysis=record,
        analysis_result_id=result_id,
        collection_definition_id="definition-1",
        collection_definition_key="strawberries_aug2026",
        collection_config={"delivery": {"leadership_email": False}},
    )


def _service() -> AutomationService:
    collection_repository = InMemoryCollectionRepository()
    collection_service = CollectionService(
        collection_repository,
        CollectionPlanner(
            collection_repository,
            CollectionRetailerCatalog.from_path(
                REPOSITORY_ROOT / "config" / "retailer-catalog.json"
            ),
        ),
        REPOSITORY_ROOT,
    )
    contexts = (
        _context("baseline", datetime(2026, 8, 1, tzinfo=UTC), 0.4),
        _context("current", datetime(2026, 8, 8, tzinfo=UTC), 0.6),
    )
    return AutomationService(
        InMemoryAutomationRepository(analyses=contexts),
        collection_service,
        RecordingEmailSender(),
        REPOSITORY_ROOT,
    )


async def test_automation_crud_history_evaluation_and_delivery_apis() -> None:
    service = _service()
    app = create_app()
    app.dependency_overrides[get_automation_service] = lambda: service
    alert = json.loads(
        (REPOSITORY_ROOT / "examples" / "alert-definition.amazon-pressure.json").read_text()
    )
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        published = await client.post("/api/v1/alert-definitions", json=alert)
        assert published.status_code == 201
        assert published.json()["version"] == 1

        listing = await client.get("/api/v1/alert-definitions")
        assert [row["stable_key"] for row in listing.json()] == ["amazon-1lb-pressure"]

        history = await client.get("/api/v1/analyses/current/history")
        assert history.status_code == 200
        assert history.json()["baseline_analysis_id"] == "baseline"
        metric = next(
            row
            for row in history.json()["changes"]
            if row["metric_key"].endswith("competitor_lower_rate")
            and "segment_id=conventional_1lb" in row["metric_key"]
        )
        assert float(metric["change_value"]) == 0.2

        evaluated = await client.post("/api/v1/analyses/current/evaluate-alerts")
        assert evaluated.json() == {"triggered_events": 1, "queued_deliveries": 1}
        events = await client.get("/api/v1/alert-events")
        assert events.json()[0]["evidence"]["current"]["analysis_id"] == "current"
        deliveries = await client.get("/api/v1/email-deliveries")
        assert deliveries.json()[0]["status"] == "pending"
        assert deliveries.json()[0]["evidence"]["current"]["json_pointer"]

        schedules = await client.post("/api/v1/collection-schedules/sync")
        assert schedules.json() == {"count": 0}


async def test_automation_api_rejects_invalid_alert_and_missing_history() -> None:
    service = _service()
    app = create_app()
    app.dependency_overrides[get_automation_service] = lambda: service
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        invalid = await client.post("/api/v1/alert-definitions", json={"id": "bad"})
        assert invalid.status_code == 422
        missing = await client.get("/api/v1/analyses/missing/history")
        assert missing.status_code == 404
