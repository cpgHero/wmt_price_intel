"""Application service coordinating scheduling, alerts, history, and email."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from email import policy
from email.parser import BytesParser
from pathlib import Path

from rci_automation.cron import CronExpressionError, CronSchedule
from rci_automation.evaluator import AlertEvaluator, HistoricalComparator, MetricSelectionError
from rci_automation.models import (
    AlertDefinitionRecord,
    AlertEventRecord,
    AnalysisContext,
    AutomationTickResult,
    EmailDeliveryRecord,
    HistoricalComparison,
    JsonObject,
    ScheduleRecord,
)
from rci_automation.ports import AutomationRepository, EmailSender
from rci_collections.service import CollectionService
from rci_contracts import validate_instance
from rci_results import ArtifactRenderer


def _checksum(document: JsonObject) -> str:
    body = json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(body.encode()).hexdigest()


class AutomationNotFoundError(LookupError):
    pass


class AutomationService:
    def __init__(
        self,
        repository: AutomationRepository,
        collection_service: CollectionService,
        email_sender: EmailSender,
        schema_root: Path,
    ) -> None:
        self.repository = repository
        self.collection_service = collection_service
        self.email_sender = email_sender
        self.schema_root = schema_root
        self._alerts = AlertEvaluator()
        self._history = HistoricalComparator()
        self._renderer = ArtifactRenderer()

    async def publish_alert(self, config: JsonObject) -> AlertDefinitionRecord:
        validate_instance(
            self.schema_root,
            "alert-definition.schema.json",
            config,
            label="alert definition",
        )
        return await self.repository.publish_alert(config, _checksum(config))

    async def list_alerts(self) -> list[AlertDefinitionRecord]:
        return await self.repository.list_alerts()

    async def list_alert_events(self, limit: int = 100) -> list[AlertEventRecord]:
        return await self.repository.list_alert_events(limit)

    async def list_schedules(self) -> list[ScheduleRecord]:
        return await self.repository.list_schedules()

    async def list_email_deliveries(self, limit: int = 100) -> list[EmailDeliveryRecord]:
        return await self.repository.list_email_deliveries(limit)

    async def sync_schedules(self, *, now: datetime | None = None) -> int:
        synchronized, _ = await self._synchronize_schedules(now=now)
        return synchronized

    async def _synchronize_schedules(self, *, now: datetime | None = None) -> tuple[int, int]:
        instant = now or datetime.now(UTC)
        synchronized = 0
        failures = 0
        for source in await self.repository.schedule_sources():
            config = source.config.get("schedule")
            if (
                not source.active
                or not isinstance(config, dict)
                or config.get("type") != "cron"
                or not config.get("cron")
            ):
                await self.repository.disable_schedule(source.definition_id)
                continue
            try:
                cron = CronSchedule(str(config["cron"]), str(config.get("timezone", "UTC")))
            except CronExpressionError as exc:
                await self.repository.disable_schedule(
                    source.definition_id,
                    error=f"invalid schedule: {exc}"[:4_000],
                )
                failures += 1
                continue
            await self.repository.upsert_schedule(
                source,
                cron_expression=cron.expression,
                timezone=str(config.get("timezone", "UTC")),
                enabled=True,
                next_run_at=cron.next_after(instant),
            )
            synchronized += 1
        return synchronized, failures

    async def materialize_due_schedules(
        self,
        worker_id: str,
        *,
        limit: int = 10,
        lease_seconds: int = 300,
        now: datetime | None = None,
    ) -> tuple[int, int]:
        instant = now or datetime.now(UTC)
        created = 0
        failures = 0
        schedules = await self.repository.claim_due_schedules(
            worker_id, limit=limit, lease_seconds=lease_seconds
        )
        for schedule in schedules:
            run_id = None
            error = None
            try:
                run = await self.collection_service.create_run(
                    schedule.definition_key,
                    trigger_type="scheduled",
                    schedule_id=schedule.id,
                    scheduled_for=schedule.next_run_at,
                )
                run_id = run.id
                created += 1
            except Exception as exc:  # scheduler must release the lease and continue
                error = str(exc)[:4_000]
                failures += 1
            cron = CronSchedule(schedule.cron_expression, schedule.timezone)
            await self.repository.complete_schedule(
                schedule,
                next_run_at=cron.next_after(instant),
                collection_run_id=run_id,
                error=error,
            )
        return created, failures

    async def history(
        self, analysis_id: str, *, baseline_id: str | None = None
    ) -> HistoricalComparison:
        current = await self._analysis(analysis_id)
        baseline = (
            await self._analysis(baseline_id)
            if baseline_id is not None
            else await self.repository.previous_analysis(current)
        )
        if baseline is None:
            raise AutomationNotFoundError("no comparable baseline analysis was found")
        if (
            current.analysis.product_pack_id != baseline.analysis.product_pack_id
            or current.collection_definition_id != baseline.collection_definition_id
        ):
            raise ValueError(
                "historical analyses must share Product Pack and collection definition"
            )
        return self._history.compare(current, baseline)

    async def evaluate_analysis(self, analysis_id: str) -> tuple[int, int]:
        current = await self._analysis(analysis_id)
        baseline = await self.repository.previous_analysis(current)
        return await self._evaluate(current, baseline)

    async def process_analyses(
        self, worker_id: str, *, limit: int = 10, lease_seconds: int = 300
    ) -> tuple[int, int, int]:
        evaluated = triggered = failures = 0
        for current in await self.repository.claim_analyses(
            worker_id, limit=limit, lease_seconds=lease_seconds
        ):
            error = None
            try:
                baseline = await self.repository.previous_analysis(current)
                event_count, _ = await self._evaluate(current, baseline)
                triggered += event_count
                evaluated += 1
            except Exception as exc:  # release/retry this analysis independently
                error = str(exc)[:4_000]
                failures += 1
            await self.repository.complete_analysis(current.analysis_result_id, worker_id, error)
        return evaluated, triggered, failures

    async def _evaluate(
        self, current: AnalysisContext, baseline: AnalysisContext | None
    ) -> tuple[int, int]:
        triggered = deliveries = 0
        for definition in await self.repository.list_alerts():
            if not definition.active or not self._alerts.applies(definition, current):
                continue
            try:
                evaluation = self._alerts.evaluate(definition, current, baseline)
            except MetricSelectionError:
                continue
            cooldown = int(definition.config.get("cooldown_minutes", 0))
            event = await self.repository.record_alert_event(
                definition,
                current,
                baseline,
                evaluation,
                cooldown_minutes=cooldown,
            )
            if evaluation.triggered and event.status == "triggered":
                triggered += 1
                recipients = tuple(definition.config["delivery"]["email_recipients"])
                await self.repository.enqueue_email(
                    current,
                    alert_event=event,
                    delivery_type="alert",
                    recipients=recipients,
                    subject=f"RCI alert: {definition.name}",
                    text_body=self._alert_body(definition, event),
                    html_body=None,
                    evidence=event.evidence,
                    idempotency_key=f"alert:{event.id}",
                )
                deliveries += 1
        report_delivery = current.collection_config.get("delivery", {})
        recipients = tuple(report_delivery.get("email_recipients", []))
        if report_delivery.get("leadership_email") and recipients:
            subject, body = self._leadership_email(current)
            await self.repository.enqueue_email(
                current,
                alert_event=None,
                delivery_type="analysis_report",
                recipients=recipients,
                subject=subject,
                text_body=body,
                html_body=None,
                evidence={
                    "analysis_id": current.analysis.analysis_id,
                    "analysis_checksum": current.analysis.checksum,
                },
                idempotency_key=f"analysis-report:{current.analysis.analysis_id}",
            )
            deliveries += 1
        return triggered, deliveries

    async def deliver_emails(
        self, worker_id: str, *, limit: int = 20, lease_seconds: int = 120
    ) -> tuple[int, int]:
        sent = failures = 0
        deliveries = await self.repository.claim_emails(
            worker_id, limit=limit, lease_seconds=lease_seconds
        )
        for delivery in deliveries:
            message_id = error = None
            try:
                message_id = await self.email_sender.send(delivery)
                sent += 1
            except Exception as exc:  # each delivery has its own retry budget
                error = str(exc)[:4_000]
                failures += 1
            retry_delay = min(60 * (2 ** max(delivery.attempt_count - 1, 0)), 3_600)
            await self.repository.complete_email(
                delivery.id,
                worker_id,
                provider_message_id=message_id,
                error=error,
                retry_delay_seconds=retry_delay,
            )
        return sent, failures

    async def tick(
        self,
        worker_id: str,
        *,
        claim_limit: int = 10,
        lease_seconds: int = 300,
    ) -> AutomationTickResult:
        synchronized, synchronization_failures = await self._synchronize_schedules()
        runs, schedule_failures = await self.materialize_due_schedules(
            worker_id, limit=claim_limit, lease_seconds=lease_seconds
        )
        analyses, alerts, analysis_failures = await self.process_analyses(
            worker_id, limit=claim_limit, lease_seconds=lease_seconds
        )
        sent, email_failures = await self.deliver_emails(
            worker_id, limit=claim_limit, lease_seconds=min(lease_seconds, 120)
        )
        return AutomationTickResult(
            schedules_synchronized=synchronized,
            scheduled_runs_created=runs,
            analyses_evaluated=analyses,
            alert_events_triggered=alerts,
            emails_sent=sent,
            failures=(
                synchronization_failures + schedule_failures + analysis_failures + email_failures
            ),
        )

    async def _analysis(self, identifier: str | None) -> AnalysisContext:
        if identifier is None:
            raise AutomationNotFoundError("analysis identifier is required")
        context = await self.repository.get_analysis(identifier)
        if context is None:
            raise AutomationNotFoundError(f"analysis {identifier!r} was not found")
        return context

    @staticmethod
    def _alert_body(definition: AlertDefinitionRecord, event: AlertEventRecord) -> str:
        baseline = f"\nBaseline: {event.baseline_value}" if event.baseline_value is not None else ""
        change = f"\nChange: {event.change_value}" if event.change_value is not None else ""
        return (
            f"{definition.name}\n\nAnalysis: {event.analysis_id}\n"
            f"Current value: {event.current_value}{baseline}{change}\n\n"
            "This notification is backed by the stored AnalysisResult evidence references."
        )

    def _leadership_email(self, current: AnalysisContext) -> tuple[str, str]:
        payload = self._renderer.render(current.analysis.result, "leadership_email")
        message = BytesParser(policy=policy.default).parsebytes(payload.body)
        body = message.get_body(preferencelist=("plain",))
        return str(message["Subject"]), body.get_content() if body else ""
