"""Typed records for schedules, comparisons, alerts, and delivery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from rci_results.models import AnalysisRecord

JsonObject = dict[str, Any]


@dataclass(frozen=True, slots=True)
class ScheduleSource:
    definition_id: str
    stable_key: str
    active: bool
    config: JsonObject


@dataclass(frozen=True, slots=True)
class ScheduleRecord:
    id: str
    definition_id: str
    definition_key: str
    cron_expression: str
    timezone: str
    enabled: bool
    next_run_at: datetime
    last_scheduled_for: datetime | None
    last_collection_run_id: str | None
    lease_owner: str | None
    lease_expires_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AnalysisContext:
    analysis: AnalysisRecord
    analysis_result_id: str
    collection_definition_id: str
    collection_definition_key: str
    collection_config: JsonObject


@dataclass(frozen=True, slots=True)
class MetricValue:
    value: Decimal
    json_pointer: str


@dataclass(frozen=True, slots=True)
class MetricChange:
    metric_key: str
    current_value: Decimal
    baseline_value: Decimal
    change_value: Decimal
    percent_change: Decimal | None
    current_evidence_ref: str
    baseline_evidence_ref: str


@dataclass(frozen=True, slots=True)
class HistoricalComparison:
    current_analysis_id: str
    baseline_analysis_id: str
    product_pack_id: str
    collection_definition_key: str
    changes: tuple[MetricChange, ...]


@dataclass(frozen=True, slots=True)
class AlertDefinitionRecord:
    id: str
    stable_key: str
    name: str
    active: bool
    version_id: str
    version: int
    checksum: str
    config: JsonObject
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AlertEvaluation:
    triggered: bool
    current_value: Decimal
    baseline_value: Decimal | None
    change_value: Decimal | None
    evidence: JsonObject


@dataclass(frozen=True, slots=True)
class AlertEventRecord:
    id: str
    alert_definition_version_id: str
    alert_key: str
    analysis_result_id: str
    analysis_id: str
    baseline_analysis_result_id: str | None
    baseline_analysis_id: str | None
    status: str
    current_value: Decimal | None
    baseline_value: Decimal | None
    change_value: Decimal | None
    evidence: JsonObject
    created_at: datetime


@dataclass(frozen=True, slots=True)
class EmailDeliveryRecord:
    id: str
    alert_event_id: str | None
    analysis_result_id: str
    analysis_id: str
    delivery_type: str
    recipients: tuple[str, ...]
    subject: str
    text_body: str
    html_body: str | None
    evidence: JsonObject
    idempotency_key: str
    status: str
    attempt_count: int
    max_attempts: int
    available_at: datetime
    locked_by: str | None
    lease_expires_at: datetime | None
    provider_message_id: str | None
    last_error: str | None
    created_at: datetime
    sent_at: datetime | None


@dataclass(frozen=True, slots=True)
class AutomationTickResult:
    schedules_synchronized: int
    scheduled_runs_created: int
    analyses_evaluated: int
    alert_events_triggered: int
    emails_sent: int
    failures: int
