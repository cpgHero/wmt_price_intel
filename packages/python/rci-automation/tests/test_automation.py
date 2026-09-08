from __future__ import annotations

import asyncio
import copy
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from rci_automation.cron import CronExpressionError, CronSchedule
from rci_automation.email import FakeEmailSender, email_sender_from_env
from rci_automation.memory import InMemoryAutomationRepository, RecordingEmailSender
from rci_automation.models import AnalysisContext, ScheduleSource
from rci_automation.repository import PostgresAutomationRepository
from rci_automation.service import AutomationNotFoundError, AutomationService
from rci_collections import (
    CollectionPlanner,
    CollectionRetailerCatalog,
    InMemoryCollectionRepository,
)
from rci_collections.models import LocationUnit
from rci_collections.service import CollectionBudgetError, CollectionService
from rci_results.models import AnalysisRecord

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def _collection_config() -> dict[str, object]:
    return {
        "id": "scheduled-strawberries",
        "name": "Scheduled Strawberries",
        "version": "1.0.0",
        "enabled": True,
        "benchmark_retailer": "walmart_us",
        "product_pack": {"id": "fresh_strawberries", "version": "1.0.0"},
        "query": {"keyword": "strawberries"},
        "retailers": [
            {
                "retailer_id": "walmart_us",
                "adapter_id": "metricscart_walmart_search_zipcode_v2",
                "enabled": True,
            }
        ],
        "geography": {"strategy": "all_retailer_locations", "country": "USA"},
        "pagination": {"max_pages": 1, "stop_on_empty": True},
        "schedule": {
            "type": "cron",
            "cron": "* * * * *",
            "timezone": "America/Chicago",
        },
        "delivery": {
            "web_report": True,
            "excel": True,
            "leadership_email": True,
            "email_recipients": ["leadership@example.com"],
        },
    }


def _collection_service(
    config: dict[str, object] | None = None,
) -> tuple[CollectionService, InMemoryCollectionRepository]:
    units = (
        LocationUnit("location-1", "walmart_us", "01234", "001", "CT", "USA"),
        LocationUnit("location-2", "walmart_us", "01235", "002", "CT", "USA"),
    )
    repository = InMemoryCollectionRepository(units)
    service = CollectionService(
        repository,
        CollectionPlanner(
            repository,
            CollectionRetailerCatalog.from_path(
                REPOSITORY_ROOT / "config" / "retailer-catalog.json"
            ),
        ),
        REPOSITORY_ROOT,
    )
    return service, repository


def _analysis_context(
    analysis_id: str,
    generated_at: datetime,
    *,
    competitor_lower_rate: float,
    walmart_zips: int,
    parity_rate: float,
    quality_score: float,
) -> AnalysisContext:
    document = json.loads(
        (REPOSITORY_ROOT / "examples" / "analysis-result-v2.ground-beef.json").read_text()
    )
    document["analysis_id"] = analysis_id
    document["generated_at"] = generated_at.isoformat()
    automation_metrics = {
        "automation.competitor_lower_rate": competitor_lower_rate,
        "automation.walmart_zips": walmart_zips,
        "automation.parity_rate": parity_rate,
        "automation.quality_score": quality_score,
    }
    for metric_id, value in automation_metrics.items():
        document["metrics"].append(
            {
                "metric_id": metric_id,
                "name": metric_id,
                "value": value,
                "unit": "rate" if isinstance(value, float) else "zipcodes",
                "method": "automation regression fixture",
                "source": "deterministic",
                "evidence_refs": ["evidence-source-manifest"],
            }
        )
    availability_evidence = []
    for coverage in document["coverage"]:
        retailer_id = str(coverage["retailer_id"])
        evidence_ref = str(coverage["evidence_refs"][0])
        availability_evidence.append(evidence_ref)
        for field, unit in (
            ("verified_available_offers", "offers"),
            ("verified_available_zips", "zipcodes"),
            ("verified_available_stores", "stores"),
        ):
            metric_id = f"coverage.{retailer_id}.{field}"
            coverage["metric_refs"].append(metric_id)
            document["metrics"].append(
                {
                    "metric_id": metric_id,
                    "name": metric_id,
                    "value": 1,
                    "unit": unit,
                    "method": "verified automation regression fixture",
                    "source": "deterministic",
                    "evidence_refs": [evidence_ref],
                }
            )
    document["validation"]["checks"].append(
        {
            "id": "verified-local-availability",
            "status": "passed",
            "evidence_refs": availability_evidence,
        }
    )
    result_id = f"result-{analysis_id}"
    record = AnalysisRecord(
        id=result_id,
        analysis_run_id=f"analysis-run-{analysis_id}",
        analysis_id=analysis_id,
        collection_run_id=f"collection-run-{analysis_id}",
        status="succeeded",
        product_pack_id="fresh_strawberries",
        product_pack_version="1.0.0",
        schema_version="2.0.0",
        checksum=f"checksum-{analysis_id}",
        result=document,
        created_at=generated_at,
    )
    config = _collection_config()
    return AnalysisContext(
        analysis=record,
        analysis_result_id=result_id,
        collection_definition_id="definition-1",
        collection_definition_key="scheduled-strawberries",
        collection_config=config,
    )


def _alert(
    alert_id: str,
    *,
    path: list[str],
    where: dict[str, object] | None,
    field: str,
    operator: str,
    threshold: float,
) -> dict[str, object]:
    del path, where
    metric_ids = {
        "competitor_lower_rate": "automation.competitor_lower_rate",
        "fresh_zips": "automation.walmart_zips",
        "parity_rate": "automation.parity_rate",
        "score": "automation.quality_score",
    }
    metric: dict[str, object] = {
        "path": ["metrics"],
        "where": {"metric_id": metric_ids[field]},
        "field": "value",
    }
    return {
        "id": alert_id,
        "name": f"Test {alert_id}",
        "enabled": True,
        "scope": {"product_pack_ids": ["fresh_strawberries"]},
        "metric": metric,
        "condition": {
            "operator": operator,
            "threshold": threshold,
            "change_mode": "absolute",
        },
        "cooldown_minutes": 0,
        "delivery": {"email_recipients": ["alerts@example.com"]},
    }


def _quarantined_context(
    context: AnalysisContext, *, reporting_status: str = "ready"
) -> AnalysisContext:
    document = copy.deepcopy(context.analysis.result)
    availability_check = next(
        row
        for row in document["validation"]["checks"]
        if row.get("id") == "verified-local-availability"
    )
    availability_check["status"] = "failed"
    return replace(
        context,
        analysis=replace(
            context.analysis,
            result=document,
            reporting_status=reporting_status,
        ),
    )


class _MappedRows:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def mappings(self) -> list[dict[str, object]]:
        return self._rows


class _FeedConnection:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.statements: list[str] = []
        self.parameters: list[dict[str, object]] = []

    async def execute(self, statement: object, parameters: dict[str, object]) -> _MappedRows:
        self.statements.append(str(statement))
        self.parameters.append(parameters)
        return _MappedRows(self.rows)


class _FeedConnectionContext:
    def __init__(self, connection: _FeedConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> _FeedConnection:
        return self.connection

    async def __aexit__(self, *_args: object) -> None:
        return None


class _FeedEngine:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.connection = _FeedConnection(rows)

    def connect(self) -> _FeedConnectionContext:
        return _FeedConnectionContext(self.connection)


def _public_feed_fields(
    context: AnalysisContext,
    *,
    organization_id: str,
    reporting_status: str = "ready",
    archived: bool = False,
    result: dict[str, object] | None = None,
    publication_status: str | None = None,
) -> dict[str, object]:
    publication_result = copy.deepcopy(result or context.analysis.result)
    return {
        "public_reporting_status": reporting_status,
        "public_archived_at": datetime.now(UTC) if archived else None,
        "public_result": copy.deepcopy(result or context.analysis.result),
        "public_result_checksum": context.analysis.checksum,
        "public_organization_id": organization_id,
        "public_alert_organization_id": organization_id,
        "public_publication_id": "publication-1" if publication_status is not None else None,
        "public_publication_analysis_result_id": context.analysis_result_id,
        "public_publication_status": publication_status,
        "public_publication_source_result_checksum": context.analysis.checksum,
        "public_publication_result": publication_result,
    }


def _feed_event_row(
    context: AnalysisContext, *, row_id: str, public: dict[str, object]
) -> dict[str, object]:
    row = {
        "id": row_id,
        "alert_definition_version_id": "alert-version-1",
        "alert_key": "price-alert",
        "analysis_result_id": context.analysis_result_id,
        "analysis_id": context.analysis.analysis_id,
        "baseline_analysis_result_id": public.get("public_baseline_analysis_result_id"),
        "baseline_analysis_id": None,
        "status": "triggered",
        "current_value": "1.0",
        "baseline_value": None,
        "change_value": None,
        "evidence": {"source": "test"},
        "created_at": datetime.now(UTC),
        **public,
    }
    row.pop("alert_event_id", None)
    return row


def _feed_email_row(
    context: AnalysisContext, *, row_id: str, public: dict[str, object]
) -> dict[str, object]:
    return {
        "id": row_id,
        "alert_event_id": public.get("alert_event_id"),
        "analysis_result_id": context.analysis_result_id,
        "analysis_id": context.analysis.analysis_id,
        "delivery_type": "analysis_report",
        "recipients": ["leadership@example.com"],
        "subject": "Leadership report",
        "text_body": "Report",
        "html_body": None,
        "evidence": {"source": "test"},
        "idempotency_key": row_id,
        "status": "sent",
        "attempt_count": 1,
        "max_attempts": 3,
        "available_at": datetime.now(UTC),
        "locked_by": None,
        "lease_expires_at": None,
        "provider_message_id": "message-1",
        "last_error": None,
        "created_at": datetime.now(UTC),
        "sent_at": datetime.now(UTC),
        **public,
    }


def _with_feed_baseline(
    public: dict[str, object],
    *,
    organization_id: str,
    result: dict[str, object],
    event_analysis_result_id: str,
    archived: bool = True,
) -> dict[str, object]:
    return {
        **copy.deepcopy(public),
        "alert_event_id": "alert-event-1",
        "public_alert_event_id": "alert-event-1",
        "public_event_analysis_result_id": event_analysis_result_id,
        "public_baseline_analysis_result_id": "baseline-result",
        "public_baseline_reporting_status": "ready",
        "public_baseline_archived_at": datetime.now(UTC) if archived else None,
        "public_baseline_result": copy.deepcopy(result),
        "public_baseline_organization_id": organization_id,
    }


def test_cron_supports_timezone_steps_and_validation() -> None:
    schedule = CronSchedule("*/15 9-10 * * 1-5", "America/Chicago")
    before = datetime(2026, 8, 7, 13, 59, tzinfo=UTC)
    assert schedule.next_after(before) == datetime(2026, 8, 7, 14, 0, tzinfo=UTC)
    sunday_range = CronSchedule("5/20 9 * * 5-7", "UTC")
    assert sunday_range.next_after(datetime(2026, 8, 7, 9, 4, tzinfo=UTC)) == datetime(
        2026, 8, 7, 9, 5, tzinfo=UTC
    )
    assert sunday_range.matches(datetime(2026, 8, 9, 9, 25, tzinfo=UTC))
    with pytest.raises(CronExpressionError, match="five fields"):
        CronSchedule("0 9 * *", "UTC")
    with pytest.raises(CronExpressionError, match="unknown timezone"):
        CronSchedule("0 9 * * *", "Not/AZone")


async def test_public_automation_feeds_fail_closed_on_owner_and_publication_lineage() -> None:
    organization_id = "11111111-1111-1111-1111-111111111111"
    other_organization_id = "22222222-2222-2222-2222-222222222222"
    context = _analysis_context(
        "feed-analysis",
        datetime(2026, 9, 8, tzinfo=UTC),
        competitor_lower_rate=0.6,
        walmart_zips=3_700,
        parity_rate=0.7,
        quality_score=0.8,
    )
    certified = _public_feed_fields(
        context,
        organization_id=organization_id,
        publication_status="ready_to_share",
    )
    legacy_result = copy.deepcopy(context.analysis.result)
    availability_check = next(
        row
        for row in legacy_result["validation"]["checks"]
        if row.get("id") == "verified-local-availability"
    )
    availability_check["status"] = "failed"
    cases = {
        "certified": certified,
        "legacy": _public_feed_fields(
            context,
            organization_id=organization_id,
            result=legacy_result,
            publication_status="ready_to_share",
        ),
        "pending": _public_feed_fields(
            context,
            organization_id=organization_id,
            reporting_status="pending",
            publication_status="ready_to_share",
        ),
        "blocked": _public_feed_fields(
            context,
            organization_id=organization_id,
            reporting_status="blocked",
            publication_status="ready_to_share",
        ),
        "archived": _public_feed_fields(
            context,
            organization_id=organization_id,
            archived=True,
            publication_status="ready_to_share",
        ),
        "cross-tenant": _public_feed_fields(
            context,
            organization_id=other_organization_id,
            publication_status="ready_to_share",
        ),
        "superseded-publication": _public_feed_fields(
            context,
            organization_id=organization_id,
            publication_status="superseded",
        ),
    }
    wrong_checksum = _public_feed_fields(
        context,
        organization_id=organization_id,
        publication_status="ready_to_share",
    )
    wrong_checksum["public_publication_source_result_checksum"] = "wrong-checksum"
    cases["wrong-publication-source"] = wrong_checksum
    wrong_owner = _public_feed_fields(
        context,
        organization_id=organization_id,
        publication_status="ready_to_share",
    )
    wrong_owner["public_publication_analysis_result_id"] = "other-result"
    cases["wrong-publication-owner"] = wrong_owner
    cases["certified-archived-baseline"] = _with_feed_baseline(
        certified,
        organization_id=organization_id,
        result=context.analysis.result,
        event_analysis_result_id=context.analysis_result_id,
    )
    cases["legacy-baseline"] = _with_feed_baseline(
        certified,
        organization_id=organization_id,
        result=legacy_result,
        event_analysis_result_id=context.analysis_result_id,
    )
    cases["cross-tenant-baseline"] = _with_feed_baseline(
        certified,
        organization_id=other_organization_id,
        result=context.analysis.result,
        event_analysis_result_id=context.analysis_result_id,
    )
    cases["wrong-event-owner"] = _with_feed_baseline(
        certified,
        organization_id=organization_id,
        result=context.analysis.result,
        event_analysis_result_id="other-result",
    )

    event_engine = _FeedEngine(
        [
            _feed_event_row(context, row_id=row_id, public=public)
            for row_id, public in cases.items()
            if row_id != "wrong-event-owner"
        ]
    )
    email_engine = _FeedEngine(
        [_feed_email_row(context, row_id=row_id, public=public) for row_id, public in cases.items()]
    )
    event_repository = PostgresAutomationRepository(  # type: ignore[arg-type]
        event_engine, organization_id=organization_id
    )
    email_repository = PostgresAutomationRepository(  # type: ignore[arg-type]
        email_engine, organization_id=organization_id
    )

    events = await event_repository.list_alert_events(limit=100)
    deliveries = await email_repository.list_email_deliveries(limit=100)

    assert [row.id for row in events] == ["certified", "certified-archived-baseline"]
    assert [row.id for row in deliveries] == ["certified", "certified-archived-baseline"]
    event_statement = event_engine.connection.statements[0]
    email_statement = email_engine.connection.statements[0]
    for statement in (event_statement, email_statement):
        assert "reporting_status = 'ready'" in statement
        assert "archived_at IS NULL" in statement
        assert "organization_id = CAST(:organization_id AS uuid)" in statement
        assert "analysis_publication" in statement
        assert "ORDER BY p.version DESC LIMIT 1" in statement
    assert event_engine.connection.parameters[0]["organization_id"] == organization_id
    assert email_engine.connection.parameters[0]["organization_id"] == organization_id


async def test_schedule_materialization_is_leased_and_idempotent() -> None:
    collection_service, collection_repository = _collection_service()
    config = _collection_config()
    config["budget"] = {
        "max_credits_per_run": 2,
        "max_credits_per_day": 2,
        "max_credits_per_month": 2,
        "block_if_estimate_exceeds_budget": True,
    }
    definition = await collection_service.publish_definition(config)
    source = ScheduleSource(
        definition_id=definition.id,
        stable_key=definition.stable_key,
        active=True,
        config=definition.config,
    )
    repository = InMemoryAutomationRepository(schedule_sources=(source,))
    service = AutomationService(
        repository,
        collection_service,
        RecordingEmailSender(),
        REPOSITORY_ROOT,
    )
    past = datetime.now(UTC) - timedelta(minutes=2)
    assert await service.sync_schedules(now=past) == 1

    created, failures = await service.materialize_due_schedules("scheduler-1")
    assert (created, failures) == (1, 0)
    schedule = (await repository.list_schedules())[0]
    assert schedule.last_collection_run_id is not None
    run = await collection_repository.get_run(schedule.last_collection_run_id)
    assert run is not None
    assert run.trigger_type == "scheduled"
    assert run.schedule_id == schedule.id

    repeated = await collection_service.create_run(
        definition.stable_key,
        trigger_type="scheduled",
        schedule_id=schedule.id,
        scheduled_for=schedule.last_scheduled_for,
    )
    assert repeated.id == run.id


async def test_invalid_legacy_schedule_does_not_block_valid_scheduler_work() -> None:
    collection_service, _ = _collection_service()
    valid_config = _collection_config()
    invalid_config = _collection_config()
    invalid_config["id"] = "invalid-schedule"
    invalid_config["schedule"] = {
        "type": "cron",
        "cron": "61 * * * *",
        "timezone": "UTC",
    }
    repository = InMemoryAutomationRepository(
        schedule_sources=(
            ScheduleSource("definition-valid", "valid", True, valid_config),
            ScheduleSource("definition-invalid", "invalid", True, invalid_config),
        )
    )
    service = AutomationService(
        repository,
        collection_service,
        RecordingEmailSender(),
        REPOSITORY_ROOT,
    )

    result = await service.tick("scheduler-1")

    assert result.schedules_synchronized == 1
    assert result.failures == 1
    assert [schedule.definition_key for schedule in await repository.list_schedules()] == ["valid"]


async def test_alert_cooldown_is_atomic_across_concurrent_evaluations() -> None:
    collection_service, _ = _collection_service()
    baseline = _analysis_context(
        "baseline",
        datetime(2026, 8, 1, tzinfo=UTC),
        competitor_lower_rate=0.4,
        walmart_zips=3_500,
        parity_rate=0.5,
        quality_score=0.95,
    )
    current_a = _analysis_context(
        "current-a",
        datetime(2026, 8, 8, 12, 0, tzinfo=UTC),
        competitor_lower_rate=0.7,
        walmart_zips=3_700,
        parity_rate=0.7,
        quality_score=0.8,
    )
    current_b = _analysis_context(
        "current-b",
        datetime(2026, 8, 8, 12, 1, tzinfo=UTC),
        competitor_lower_rate=0.7,
        walmart_zips=3_700,
        parity_rate=0.7,
        quality_score=0.8,
    )
    for context in (current_a, current_b):
        context.collection_config["delivery"] = {"leadership_email": False}
    repository = InMemoryAutomationRepository(analyses=(baseline, current_a, current_b))
    service = AutomationService(
        repository, collection_service, RecordingEmailSender(), REPOSITORY_ROOT
    )
    alert = _alert(
        "replica-cooldown",
        path=["data_quality"],
        where=None,
        field="score",
        operator="lt",
        threshold=0.9,
    )
    alert["cooldown_minutes"] = 60
    await service.publish_alert(alert)

    evaluations = await asyncio.gather(
        service.evaluate_analysis("current-a"),
        service.evaluate_analysis("current-b"),
    )
    assert sum(triggered for triggered, _ in evaluations) == 1
    assert sum(queued for _, queued in evaluations) == 1
    assert sorted(event.status for event in await repository.list_alert_events()) == [
        "suppressed",
        "triggered",
    ]


async def test_alert_records_evidence_when_condition_does_not_trigger() -> None:
    collection_service, _ = _collection_service()
    current = _analysis_context(
        "quality-ok",
        datetime(2026, 8, 8, tzinfo=UTC),
        competitor_lower_rate=0.4,
        walmart_zips=3_500,
        parity_rate=0.5,
        quality_score=0.95,
    )
    current.collection_config["delivery"] = {"leadership_email": False}
    repository = InMemoryAutomationRepository(analyses=(current,))
    service = AutomationService(
        repository, collection_service, RecordingEmailSender(), REPOSITORY_ROOT
    )
    await service.publish_alert(
        _alert(
            "quality-remains-good",
            path=["data_quality"],
            where=None,
            field="score",
            operator="lt",
            threshold=0.9,
        )
    )

    assert await service.evaluate_analysis("quality-ok") == (0, 0)
    event = (await repository.list_alert_events())[0]
    assert event.status == "not_triggered"
    assert event.evidence["current"]["json_pointer"].endswith("/value")


async def test_daily_and_monthly_budgets_reserve_credits_atomically() -> None:
    collection_service, _ = _collection_service()
    config = _collection_config()
    config["budget"] = {
        "max_credits_per_run": 2,
        "max_credits_per_day": 3,
        "max_credits_per_month": 10,
        "block_if_estimate_exceeds_budget": True,
    }
    await collection_service.publish_definition(config)

    assert (await collection_service.create_run("scheduled-strawberries")).estimated_credits == 2
    with pytest.raises(CollectionBudgetError, match="day credit budget"):
        await collection_service.create_run("scheduled-strawberries")


async def test_history_and_four_alert_condition_families_carry_evidence() -> None:
    collection_service, _ = _collection_service()
    baseline = _analysis_context(
        "baseline",
        datetime(2026, 8, 1, tzinfo=UTC),
        competitor_lower_rate=0.4,
        walmart_zips=3_500,
        parity_rate=0.5,
        quality_score=0.95,
    )
    current = _analysis_context(
        "current",
        datetime(2026, 8, 8, tzinfo=UTC),
        competitor_lower_rate=0.6,
        walmart_zips=3_700,
        parity_rate=0.7,
        quality_score=0.8,
    )
    repository = InMemoryAutomationRepository(analyses=(baseline, current))
    sender = RecordingEmailSender()
    service = AutomationService(repository, collection_service, sender, REPOSITORY_ROOT)
    alerts = (
        _alert(
            "competitor-lower",
            path=["comparisons"],
            where={
                "competitor_id": "amazon_us_same_day",
                "segment_id": "conventional_1lb",
            },
            field="competitor_lower_rate",
            operator="gt",
            threshold=0.5,
        ),
        _alert(
            "coverage-expands",
            path=["coverage"],
            where={"retailer_id": "walmart_us"},
            field="fresh_zips",
            operator="change_gte",
            threshold=100,
        ),
        _alert(
            "parity-changes",
            path=["comparisons"],
            where={
                "competitor_id": "amazon_us_same_day",
                "segment_id": "organic_1lb",
            },
            field="parity_rate",
            operator="absolute_change_gte",
            threshold=0.1,
        ),
        _alert(
            "quality-drops",
            path=["data_quality"],
            where=None,
            field="score",
            operator="lt",
            threshold=0.9,
        ),
    )
    for alert in alerts:
        await service.publish_alert(alert)

    history = await service.history("current")
    coverage_change = next(
        change for change in history.changes if change.metric_key == "automation.walmart_zips"
    )
    assert coverage_change.change_value == 200
    assert coverage_change.current_evidence_ref.endswith("/value")

    triggered, queued = await service.evaluate_analysis("current")
    assert (triggered, queued) == (4, 5)  # four alerts plus the configured leadership email
    events = await repository.list_alert_events()
    assert len(events) == 4
    assert all(event.status == "triggered" for event in events)
    assert all(
        event.evidence["current"]["analysis_checksum"] == "checksum-current" for event in events
    )
    assert all("json_pointer" in event.evidence["current"] for event in events)

    sent, failures = await service.deliver_emails("scheduler-1")
    assert (sent, failures) == (5, 0)
    assert len(sender.deliveries) == 5
    assert all(delivery.evidence for delivery in sender.deliveries)


async def test_quarantined_analysis_cannot_enter_history_evaluation_or_rendering() -> None:
    collection_service, _ = _collection_service()
    current = _quarantined_context(
        _analysis_context(
            "quarantined",
            datetime(2026, 8, 8, tzinfo=UTC),
            competitor_lower_rate=0.6,
            walmart_zips=3_700,
            parity_rate=0.7,
            quality_score=0.8,
        )
    )
    repository = InMemoryAutomationRepository(analyses=(current,))
    sender = RecordingEmailSender()
    service = AutomationService(repository, collection_service, sender, REPOSITORY_ROOT)

    with pytest.raises(AutomationNotFoundError, match="quarantined from automation"):
        await service.history("quarantined")
    with pytest.raises(AutomationNotFoundError, match="quarantined from automation"):
        await service.evaluate_analysis("quarantined")
    with pytest.raises(AutomationNotFoundError, match="quarantined from automation"):
        service._leadership_email(current)

    assert await service.process_analyses("scheduler-1") == (0, 0, 1)
    assert await repository.list_email_deliveries() == []
    assert sender.deliveries == []


async def test_nonready_analysis_is_not_claimed_for_evaluation_or_email() -> None:
    collection_service, _ = _collection_service()
    ready = _analysis_context(
        "pending",
        datetime(2026, 8, 8, tzinfo=UTC),
        competitor_lower_rate=0.6,
        walmart_zips=3_700,
        parity_rate=0.7,
        quality_score=0.8,
    )
    pending = replace(
        ready,
        analysis=replace(ready.analysis, reporting_status="pending"),
    )
    repository = InMemoryAutomationRepository(analyses=(pending,))
    service = AutomationService(
        repository, collection_service, RecordingEmailSender(), REPOSITORY_ROOT
    )
    await repository.enqueue_email(
        pending,
        alert_event=None,
        delivery_type="analysis_report",
        recipients=("leadership@example.com",),
        subject="Unsafe",
        text_body="Unsafe",
        html_body=None,
        evidence={},
        idempotency_key="pending-report",
    )

    assert await repository.claim_analyses("scheduler-1", limit=10, lease_seconds=60) == []
    assert await repository.claim_emails("scheduler-1", limit=10, lease_seconds=60) == []
    with pytest.raises(AutomationNotFoundError, match="was not found"):
        await service.evaluate_analysis("pending")


async def test_email_sender_rechecks_certification_after_enqueue() -> None:
    collection_service, _ = _collection_service()
    current = _analysis_context(
        "current",
        datetime(2026, 8, 8, tzinfo=UTC),
        competitor_lower_rate=0.6,
        walmart_zips=3_700,
        parity_rate=0.7,
        quality_score=0.8,
    )
    repository = InMemoryAutomationRepository(analyses=(current,))
    sender = RecordingEmailSender()
    service = AutomationService(repository, collection_service, sender, REPOSITORY_ROOT)
    assert await service.evaluate_analysis("current") == (0, 1)

    availability_check = next(
        row
        for row in current.analysis.result["validation"]["checks"]
        if row.get("id") == "verified-local-availability"
    )
    availability_check["status"] = "failed"

    assert await service.deliver_emails("scheduler-1") == (0, 1)
    assert sender.deliveries == []


async def test_email_failure_retries_without_losing_evidence() -> None:
    collection_service, _ = _collection_service()
    current = _analysis_context(
        "current",
        datetime.now(UTC),
        competitor_lower_rate=0.6,
        walmart_zips=3_700,
        parity_rate=0.7,
        quality_score=0.8,
    )
    repository = InMemoryAutomationRepository(analyses=(current,))
    service = AutomationService(
        repository,
        collection_service,
        RecordingEmailSender(fail=True),
        REPOSITORY_ROOT,
    )
    await service.publish_alert(
        _alert(
            "quality-drops",
            path=["data_quality"],
            where=None,
            field="score",
            operator="lt",
            threshold=0.9,
        )
    )
    assert await service.evaluate_analysis("current") == (1, 2)
    assert await service.deliver_emails("scheduler-1") == (0, 2)
    deliveries = await repository.list_email_deliveries()
    assert all(delivery.status == "pending" for delivery in deliveries)
    assert all(delivery.attempt_count == 1 for delivery in deliveries)
    assert all(delivery.evidence for delivery in deliveries)


async def test_fake_email_provider_is_non_network_and_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EMAIL_PROVIDER", "fake")
    sender = email_sender_from_env()
    assert isinstance(sender, FakeEmailSender)
    collection_service, _ = _collection_service()
    current = _analysis_context(
        "fake-delivery",
        datetime.now(UTC),
        competitor_lower_rate=0.6,
        walmart_zips=3_700,
        parity_rate=0.7,
        quality_score=0.8,
    )
    current.collection_config["delivery"] = {"leadership_email": False}
    repository = InMemoryAutomationRepository(analyses=(current,))
    service = AutomationService(repository, collection_service, sender, REPOSITORY_ROOT)
    await service.publish_alert(
        _alert(
            "fake-delivery",
            path=["data_quality"],
            where=None,
            field="score",
            operator="lt",
            threshold=0.9,
        )
    )

    assert await service.evaluate_analysis("fake-delivery") == (1, 1)
    assert await service.deliver_emails("scheduler-1") == (1, 0)
    delivery = (await repository.list_email_deliveries())[0]
    assert delivery.status == "sent"
    assert delivery.provider_message_id is not None
    assert delivery.provider_message_id.startswith("fake-")
    assert await service.deliver_emails("scheduler-2") == (0, 0)


def test_unknown_email_provider_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMAIL_PROVIDER", "unexpected")
    with pytest.raises(RuntimeError, match="EMAIL_PROVIDER"):
        email_sender_from_env()
