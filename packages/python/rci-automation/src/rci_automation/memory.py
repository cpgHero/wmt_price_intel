"""Concurrency-safe in-memory automation repository and email sender."""

from __future__ import annotations

import asyncio
import copy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from rci_automation.models import (
    AlertDefinitionRecord,
    AlertEvaluation,
    AlertEventRecord,
    AnalysisContext,
    EmailDeliveryRecord,
    JsonObject,
    ScheduleRecord,
    ScheduleSource,
)


class InMemoryAutomationRepository:
    def __init__(
        self,
        *,
        schedule_sources: tuple[ScheduleSource, ...] = (),
        analyses: tuple[AnalysisContext, ...] = (),
    ) -> None:
        self._lock = asyncio.Lock()
        self._sources = {source.definition_id: source for source in schedule_sources}
        self._schedules: dict[str, ScheduleRecord] = {}
        self._alerts: dict[str, list[AlertDefinitionRecord]] = {}
        self._analyses = {context.analysis.analysis_id: context for context in analyses}
        self._analysis_by_result = {context.analysis_result_id: context for context in analyses}
        self._analysis_states: dict[str, tuple[str, str | None, datetime | None]] = {}
        self._events: dict[tuple[str, str], AlertEventRecord] = {}
        self._emails: dict[str, EmailDeliveryRecord] = {}

    async def schedule_sources(self) -> list[ScheduleSource]:
        return list(self._sources.values())

    async def upsert_schedule(
        self,
        source: ScheduleSource,
        *,
        cron_expression: str,
        timezone: str,
        enabled: bool,
        next_run_at: datetime,
    ) -> ScheduleRecord:
        async with self._lock:
            existing = next(
                (
                    row
                    for row in self._schedules.values()
                    if row.definition_id == source.definition_id
                ),
                None,
            )
            now = datetime.now(UTC)
            if existing is None:
                record = ScheduleRecord(
                    id=str(uuid4()),
                    definition_id=source.definition_id,
                    definition_key=source.stable_key,
                    cron_expression=cron_expression,
                    timezone=timezone,
                    enabled=enabled,
                    next_run_at=next_run_at,
                    last_scheduled_for=None,
                    last_collection_run_id=None,
                    lease_owner=None,
                    lease_expires_at=None,
                    last_error=None,
                    created_at=now,
                    updated_at=now,
                )
            else:
                changed = (
                    existing.cron_expression != cron_expression or existing.timezone != timezone
                )
                record = replace(
                    existing,
                    cron_expression=cron_expression,
                    timezone=timezone,
                    enabled=enabled,
                    next_run_at=next_run_at if changed else existing.next_run_at,
                    updated_at=now,
                )
            self._schedules[record.id] = record
            return copy.deepcopy(record)

    async def disable_schedule(self, definition_id: str, *, error: str | None = None) -> None:
        async with self._lock:
            for schedule_id, schedule in tuple(self._schedules.items()):
                if schedule.definition_id == definition_id:
                    self._schedules[schedule_id] = replace(
                        schedule,
                        enabled=False,
                        last_error=error,
                        updated_at=datetime.now(UTC),
                    )

    async def list_schedules(self) -> list[ScheduleRecord]:
        return sorted(self._schedules.values(), key=lambda row: row.definition_key)

    async def claim_due_schedules(
        self, worker_id: str, *, limit: int, lease_seconds: int
    ) -> list[ScheduleRecord]:
        now = datetime.now(UTC)
        async with self._lock:
            candidates = [
                row
                for row in self._schedules.values()
                if row.enabled
                and row.next_run_at <= now
                and (row.lease_expires_at is None or row.lease_expires_at <= now)
            ]
            claimed = []
            for row in sorted(candidates, key=lambda item: item.next_run_at)[:limit]:
                updated = replace(
                    row,
                    lease_owner=worker_id,
                    lease_expires_at=now + timedelta(seconds=lease_seconds),
                )
                self._schedules[row.id] = updated
                claimed.append(updated)
            return claimed

    async def complete_schedule(
        self,
        schedule: ScheduleRecord,
        *,
        next_run_at: datetime,
        collection_run_id: str | None,
        error: str | None,
    ) -> None:
        async with self._lock:
            current = self._schedules[schedule.id]
            self._schedules[schedule.id] = replace(
                current,
                next_run_at=next_run_at,
                last_scheduled_for=schedule.next_run_at,
                last_collection_run_id=collection_run_id,
                lease_owner=None,
                lease_expires_at=None,
                last_error=error,
                updated_at=datetime.now(UTC),
            )

    async def publish_alert(self, config: JsonObject, checksum: str) -> AlertDefinitionRecord:
        key = str(config["id"])
        async with self._lock:
            versions = self._alerts.setdefault(key, [])
            for version in versions:
                if version.checksum == checksum:
                    return version
            now = datetime.now(UTC)
            record = AlertDefinitionRecord(
                id=versions[0].id if versions else str(uuid4()),
                stable_key=key,
                name=str(config["name"]),
                active=bool(config["enabled"]),
                version_id=str(uuid4()),
                version=len(versions) + 1,
                checksum=checksum,
                config=copy.deepcopy(config),
                created_at=now,
            )
            versions.append(record)
            return record

    async def list_alerts(self) -> list[AlertDefinitionRecord]:
        return sorted((rows[-1] for rows in self._alerts.values()), key=lambda row: row.stable_key)

    async def list_alert_events(self, limit: int = 100) -> list[AlertEventRecord]:
        return sorted(self._events.values(), key=lambda row: row.created_at, reverse=True)[:limit]

    async def get_analysis(self, identifier: str) -> AnalysisContext | None:
        context = self._analyses.get(identifier) or self._analysis_by_result.get(identifier)
        return copy.deepcopy(context)

    async def previous_analysis(self, current: AnalysisContext) -> AnalysisContext | None:
        candidates = [
            context
            for context in self._analyses.values()
            if context.analysis.created_at < current.analysis.created_at
            and context.analysis.product_pack_id == current.analysis.product_pack_id
            and context.collection_definition_id == current.collection_definition_id
        ]
        return max(candidates, key=lambda row: row.analysis.created_at, default=None)

    async def claim_analyses(
        self, worker_id: str, *, limit: int, lease_seconds: int
    ) -> list[AnalysisContext]:
        now = datetime.now(UTC)
        async with self._lock:
            claimed = []
            for context in sorted(self._analyses.values(), key=lambda row: row.analysis.created_at):
                state = self._analysis_states.get(context.analysis_result_id)
                if state and (state[0] == "processed" or (state[2] and state[2] > now)):
                    continue
                self._analysis_states[context.analysis_result_id] = (
                    "processing",
                    worker_id,
                    now + timedelta(seconds=lease_seconds),
                )
                claimed.append(context)
                if len(claimed) == limit:
                    break
            return copy.deepcopy(claimed)

    async def complete_analysis(
        self, analysis_result_id: str, worker_id: str, error: str | None
    ) -> None:
        async with self._lock:
            state = self._analysis_states.get(analysis_result_id)
            if state is not None and state[1] == worker_id:
                self._analysis_states[analysis_result_id] = (
                    "failed" if error else "processed",
                    None,
                    None,
                )

    async def record_alert_event(
        self,
        definition: AlertDefinitionRecord,
        current: AnalysisContext,
        baseline: AnalysisContext | None,
        evaluation: AlertEvaluation,
        *,
        cooldown_minutes: int,
    ) -> AlertEventRecord:
        key = (definition.version_id, current.analysis_result_id)
        async with self._lock:
            existing = self._events.get(key)
            if existing is not None:
                return existing
            cutoff = datetime.now(UTC) - timedelta(minutes=cooldown_minutes)
            suppressed = (
                evaluation.triggered
                and cooldown_minutes > 0
                and any(
                    event.alert_key == definition.stable_key
                    and event.status == "triggered"
                    and event.created_at >= cutoff
                    for event in self._events.values()
                )
            )
            record = AlertEventRecord(
                id=str(uuid4()),
                alert_definition_version_id=definition.version_id,
                alert_key=definition.stable_key,
                analysis_result_id=current.analysis_result_id,
                analysis_id=current.analysis.analysis_id,
                baseline_analysis_result_id=(
                    baseline.analysis_result_id if baseline is not None else None
                ),
                baseline_analysis_id=(baseline.analysis.analysis_id if baseline else None),
                status=(
                    "suppressed"
                    if suppressed
                    else ("triggered" if evaluation.triggered else "not_triggered")
                ),
                current_value=evaluation.current_value,
                baseline_value=evaluation.baseline_value,
                change_value=evaluation.change_value,
                evidence=copy.deepcopy(evaluation.evidence),
                created_at=datetime.now(UTC),
            )
            self._events[key] = record
            return record

    async def enqueue_email(
        self,
        current: AnalysisContext,
        *,
        alert_event: AlertEventRecord | None,
        delivery_type: str,
        recipients: tuple[str, ...],
        subject: str,
        text_body: str,
        html_body: str | None,
        evidence: JsonObject,
        idempotency_key: str,
    ) -> EmailDeliveryRecord:
        async with self._lock:
            existing = self._emails.get(idempotency_key)
            if existing is not None:
                return existing
            now = datetime.now(UTC)
            record = EmailDeliveryRecord(
                id=str(uuid4()),
                alert_event_id=alert_event.id if alert_event else None,
                analysis_result_id=current.analysis_result_id,
                analysis_id=current.analysis.analysis_id,
                delivery_type=delivery_type,
                recipients=recipients,
                subject=subject,
                text_body=text_body,
                html_body=html_body,
                evidence=copy.deepcopy(evidence),
                idempotency_key=idempotency_key,
                status="pending",
                attempt_count=0,
                max_attempts=5,
                available_at=now,
                locked_by=None,
                lease_expires_at=None,
                provider_message_id=None,
                last_error=None,
                created_at=now,
                sent_at=None,
            )
            self._emails[idempotency_key] = record
            return record

    async def claim_emails(
        self, worker_id: str, *, limit: int, lease_seconds: int
    ) -> list[EmailDeliveryRecord]:
        now = datetime.now(UTC)
        async with self._lock:
            eligible = [
                delivery
                for delivery in self._emails.values()
                if delivery.attempt_count < delivery.max_attempts
                and (
                    (delivery.status == "pending" and delivery.available_at <= now)
                    or (
                        delivery.status == "sending"
                        and delivery.lease_expires_at is not None
                        and delivery.lease_expires_at <= now
                    )
                )
            ]
            claimed = []
            for delivery in sorted(eligible, key=lambda row: row.created_at)[:limit]:
                updated = replace(
                    delivery,
                    status="sending",
                    attempt_count=delivery.attempt_count + 1,
                    locked_by=worker_id,
                    lease_expires_at=now + timedelta(seconds=lease_seconds),
                )
                self._emails[delivery.idempotency_key] = updated
                claimed.append(updated)
            return claimed

    async def complete_email(
        self,
        delivery_id: str,
        worker_id: str,
        *,
        provider_message_id: str | None,
        error: str | None,
        retry_delay_seconds: int,
    ) -> None:
        async with self._lock:
            key, delivery = next(item for item in self._emails.items() if item[1].id == delivery_id)
            if delivery.locked_by != worker_id:
                return
            exhausted = delivery.attempt_count >= delivery.max_attempts
            self._emails[key] = replace(
                delivery,
                status="sent" if error is None else ("failed" if exhausted else "pending"),
                available_at=datetime.now(UTC) + timedelta(seconds=retry_delay_seconds),
                locked_by=None,
                lease_expires_at=None,
                provider_message_id=provider_message_id,
                last_error=error,
                sent_at=datetime.now(UTC) if error is None else None,
            )

    async def list_email_deliveries(self, limit: int = 100) -> list[EmailDeliveryRecord]:
        return sorted(self._emails.values(), key=lambda row: row.created_at, reverse=True)[:limit]


class RecordingEmailSender:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.deliveries: list[EmailDeliveryRecord] = []

    async def send(self, delivery: EmailDeliveryRecord) -> str:
        if self.fail:
            raise RuntimeError("simulated SMTP failure")
        self.deliveries.append(delivery)
        return f"message-{len(self.deliveries)}"
