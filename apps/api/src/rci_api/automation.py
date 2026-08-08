"""Schedule, historical comparison, alert, and delivery APIs."""

from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict

from rci_api.collections import get_collection_service
from rci_automation import (
    AutomationService,
    PostgresAutomationRepository,
    SMTPEmailSender,
    SMTPSettings,
    UnavailableEmailSender,
)
from rci_automation.models import (
    AlertDefinitionRecord,
    AlertEventRecord,
    EmailDeliveryRecord,
    HistoricalComparison,
    ScheduleRecord,
)
from rci_automation.service import AutomationNotFoundError
from rci_contracts import ContractError

router = APIRouter(prefix="/api/v1")


class ScheduleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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


class AlertDefinitionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    stable_key: str
    name: str
    active: bool
    version_id: str
    version: int
    checksum: str
    config: dict[str, Any]
    created_at: datetime


class AlertEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    evidence: dict[str, Any]
    created_at: datetime


class EmailDeliveryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    alert_event_id: str | None
    analysis_result_id: str
    analysis_id: str
    delivery_type: str
    recipients: tuple[str, ...]
    subject: str
    evidence: dict[str, Any]
    idempotency_key: str
    status: str
    attempt_count: int
    max_attempts: int
    available_at: datetime
    provider_message_id: str | None
    last_error: str | None
    created_at: datetime
    sent_at: datetime | None


class MetricChangeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    metric_key: str
    current_value: Decimal
    baseline_value: Decimal
    change_value: Decimal
    percent_change: Decimal | None
    current_evidence_ref: str
    baseline_evidence_ref: str


class HistoricalComparisonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    current_analysis_id: str
    baseline_analysis_id: str
    product_pack_id: str
    collection_definition_key: str
    changes: tuple[MetricChangeResponse, ...]


class CountResponse(BaseModel):
    count: int


class EvaluationResponse(BaseModel):
    triggered_events: int
    queued_deliveries: int


def get_automation_service(request: Request) -> AutomationService:
    repository = PostgresAutomationRepository(request.app.state.database_probe.engine)
    sender = (
        SMTPEmailSender(SMTPSettings.from_env())
        if os.getenv("SMTP_HOST") and os.getenv("SMTP_FROM_EMAIL")
        else UnavailableEmailSender()
    )
    return AutomationService(
        repository,
        get_collection_service(request),
        sender,
        Path(os.getenv("RCI_REPOSITORY_ROOT", Path.cwd())).resolve(),
    )


AutomationServiceDependency = Annotated[AutomationService, Depends(get_automation_service)]
AlertBody = Annotated[dict[str, Any], Body()]


@router.post(
    "/alert-definitions",
    response_model=AlertDefinitionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["automation"],
)
async def publish_alert(
    service: AutomationServiceDependency, config: AlertBody
) -> AlertDefinitionRecord:
    try:
        return await service.publish_alert(config)
    except ContractError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.get(
    "/alert-definitions",
    response_model=list[AlertDefinitionResponse],
    tags=["automation"],
)
async def list_alerts(
    service: AutomationServiceDependency,
) -> list[AlertDefinitionRecord]:
    return await service.list_alerts()


@router.get("/alert-events", response_model=list[AlertEventResponse], tags=["automation"])
async def list_alert_events(
    service: AutomationServiceDependency,
    limit: int = Query(default=100, ge=1, le=1_000),
) -> list[AlertEventRecord]:
    return await service.list_alert_events(limit)


@router.get(
    "/collection-schedules",
    response_model=list[ScheduleResponse],
    tags=["automation"],
)
async def list_schedules(
    service: AutomationServiceDependency,
) -> list[ScheduleRecord]:
    return await service.list_schedules()


@router.post("/collection-schedules/sync", response_model=CountResponse, tags=["automation"])
async def sync_schedules(service: AutomationServiceDependency) -> CountResponse:
    return CountResponse(count=await service.sync_schedules())


@router.get(
    "/analyses/{analysis_id}/history",
    response_model=HistoricalComparisonResponse,
    tags=["automation"],
)
async def analysis_history(
    analysis_id: str,
    service: AutomationServiceDependency,
    baseline_id: str | None = Query(default=None),
) -> HistoricalComparison:
    try:
        return await service.history(analysis_id, baseline_id=baseline_id)
    except AutomationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post(
    "/analyses/{analysis_id}/evaluate-alerts",
    response_model=EvaluationResponse,
    tags=["automation"],
)
async def evaluate_alerts(
    analysis_id: str, service: AutomationServiceDependency
) -> EvaluationResponse:
    try:
        triggered, deliveries = await service.evaluate_analysis(analysis_id)
        return EvaluationResponse(triggered_events=triggered, queued_deliveries=deliveries)
    except AutomationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/email-deliveries",
    response_model=list[EmailDeliveryResponse],
    tags=["automation"],
)
async def list_email_deliveries(
    service: AutomationServiceDependency,
    limit: int = Query(default=100, ge=1, le=1_000),
) -> list[EmailDeliveryRecord]:
    return await service.list_email_deliveries(limit)
