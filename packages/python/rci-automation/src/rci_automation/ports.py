"""Automation persistence and delivery ports."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

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


class AutomationRepository(Protocol):
    async def schedule_sources(self) -> list[ScheduleSource]: ...

    async def upsert_schedule(
        self,
        source: ScheduleSource,
        *,
        cron_expression: str,
        timezone: str,
        enabled: bool,
        next_run_at: datetime,
    ) -> ScheduleRecord: ...

    async def disable_schedule(self, definition_id: str) -> None: ...

    async def list_schedules(self) -> list[ScheduleRecord]: ...

    async def claim_due_schedules(
        self, worker_id: str, *, limit: int, lease_seconds: int
    ) -> list[ScheduleRecord]: ...

    async def complete_schedule(
        self,
        schedule: ScheduleRecord,
        *,
        next_run_at: datetime,
        collection_run_id: str | None,
        error: str | None,
    ) -> None: ...

    async def publish_alert(self, config: JsonObject, checksum: str) -> AlertDefinitionRecord: ...

    async def list_alerts(self) -> list[AlertDefinitionRecord]: ...

    async def list_alert_events(self, limit: int = 100) -> list[AlertEventRecord]: ...

    async def get_analysis(self, identifier: str) -> AnalysisContext | None: ...

    async def previous_analysis(self, current: AnalysisContext) -> AnalysisContext | None: ...

    async def claim_analyses(
        self, worker_id: str, *, limit: int, lease_seconds: int
    ) -> list[AnalysisContext]: ...

    async def complete_analysis(
        self, analysis_result_id: str, worker_id: str, error: str | None
    ) -> None: ...

    async def record_alert_event(
        self,
        definition: AlertDefinitionRecord,
        current: AnalysisContext,
        baseline: AnalysisContext | None,
        evaluation: AlertEvaluation,
        *,
        cooldown_minutes: int,
    ) -> AlertEventRecord: ...

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
    ) -> EmailDeliveryRecord: ...

    async def claim_emails(
        self, worker_id: str, *, limit: int, lease_seconds: int
    ) -> list[EmailDeliveryRecord]: ...

    async def complete_email(
        self,
        delivery_id: str,
        worker_id: str,
        *,
        provider_message_id: str | None,
        error: str | None,
        retry_delay_seconds: int,
    ) -> None: ...

    async def list_email_deliveries(self, limit: int = 100) -> list[EmailDeliveryRecord]: ...


class EmailSender(Protocol):
    async def send(self, delivery: EmailDeliveryRecord) -> str: ...
