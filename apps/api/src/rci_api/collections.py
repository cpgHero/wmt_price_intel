"""Versioned collection definition and run APIs."""

from __future__ import annotations

import os
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict

from rci_collections import CollectionPlanner, CollectionRetailerCatalog
from rci_collections.models import (
    CostEstimate,
    DefinitionRecord,
    QueueTask,
    RunMonitor,
    RunRecord,
    RunUsage,
)
from rci_collections.repository import PostgresCollectionRepository
from rci_collections.service import (
    CollectionBudgetError,
    CollectionNotFoundError,
    CollectionService,
)
from rci_contracts import ContractError

router = APIRouter(prefix="/api/v1")


class DefinitionResponse(BaseModel):
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


class RetailerEstimateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    retailer_id: str
    location_units: int
    credits_per_page: int
    max_pages: int
    estimated_pages: int
    estimated_credits: int


class CostEstimateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    definition_id: str
    retailers: tuple[RetailerEstimateResponse, ...]
    estimated_total_pages: int
    estimated_total_credits: int


class RunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    definition_version_id: str
    status: str
    estimated_pages: int
    estimated_credits: int
    actual_success_pages: int
    actual_credits: int
    started_at: datetime | None
    completed_at: datetime | None
    cancel_requested_at: datetime | None
    created_at: datetime
    trigger_type: str
    schedule_id: str | None
    scheduled_for: datetime | None
    availability_gate_status: str
    availability_gate_config: dict[str, Any]


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    collection_run_id: str
    retailer_id: str
    retailer_location_id: str | None
    adapter_id: str
    location_scope_key: str
    zipcode: str
    store_number: str | None
    page_number: int
    max_pages: int
    status: str
    attempt_count: int
    max_attempts: int
    locked_by: str | None
    lease_expires_at: datetime | None
    http_status: int | None
    result_count: int | None
    failure_class: str | None
    billable_credits: int
    raw_artifact_id: str | None


class UsageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: str
    estimated_pages: int
    estimated_credits: int
    actual_success_pages: int
    actual_credits: int
    pending_tasks: int
    running_tasks: int
    succeeded_tasks: int
    failed_tasks: int
    cancelled_tasks: int


class RetryResponse(BaseModel):
    run_id: str
    retried_tasks: int


class RetailerProgressResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    retailer_id: str
    pending_tasks: int
    running_tasks: int
    succeeded_tasks: int
    failed_tasks: int
    cancelled_tasks: int
    billable_credits: int
    attempts: int
    retries: int


class ProviderRateStateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provider: str
    second_count: int
    minute_count: int
    paused_until: datetime | None
    last_429_at: datetime | None
    updated_at: datetime


class RunMonitorResponse(BaseModel):
    run: RunResponse
    usage: UsageResponse
    retailers: tuple[RetailerProgressResponse, ...]
    retry_attempts: int
    failure_classes: dict[str, int]
    elapsed_seconds: float
    provider_state: ProviderRateStateResponse | None
    configured_global_rps: int
    configured_global_rpm: int


@lru_cache(maxsize=1)
def _repository_root() -> Path:
    return Path(os.getenv("RCI_REPOSITORY_ROOT", Path.cwd())).resolve()


@lru_cache(maxsize=1)
def _retailer_catalog() -> CollectionRetailerCatalog:
    return CollectionRetailerCatalog.from_path(
        _repository_root() / "config" / "retailer-catalog.json"
    )


def get_collection_service(request: Request) -> CollectionService:
    repository = PostgresCollectionRepository(request.app.state.database_probe.engine)
    return CollectionService(
        repository,
        CollectionPlanner(
            repository,
            _retailer_catalog(),
            max_attempts=int(os.getenv("METRICSCART_MAX_ATTEMPTS", "5")),
        ),
        _repository_root(),
    )


CollectionServiceDependency = Annotated[CollectionService, Depends(get_collection_service)]
CollectionConfigBody = Annotated[dict[str, Any], Body()]


def _not_found(exc: CollectionNotFoundError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post(
    "/collection-definitions",
    response_model=DefinitionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["collections"],
)
async def publish_definition(
    service: CollectionServiceDependency,
    config: CollectionConfigBody,
) -> DefinitionRecord:
    try:
        return await service.publish_definition(config)
    except ContractError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.get(
    "/collection-definitions",
    response_model=list[DefinitionResponse],
    tags=["collections"],
)
async def list_definitions(
    service: CollectionServiceDependency,
) -> list[DefinitionRecord]:
    return await service.list_definitions()


@router.get(
    "/collection-definitions/{identifier}",
    response_model=DefinitionResponse,
    tags=["collections"],
)
async def get_definition(
    identifier: str,
    service: CollectionServiceDependency,
) -> DefinitionRecord:
    try:
        return await service.get_definition(identifier)
    except CollectionNotFoundError as exc:
        raise _not_found(exc) from exc


@router.post(
    "/collection-estimates",
    response_model=CostEstimateResponse,
    tags=["collections"],
)
async def estimate_config(
    service: CollectionServiceDependency,
    config: CollectionConfigBody,
) -> CostEstimate:
    try:
        return await service.estimate_config(config)
    except ContractError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.post(
    "/collection-definitions/{identifier}/estimate",
    response_model=CostEstimateResponse,
    tags=["collections"],
)
async def estimate_definition(
    identifier: str,
    service: CollectionServiceDependency,
) -> CostEstimate:
    try:
        return await service.estimate(identifier)
    except CollectionNotFoundError as exc:
        raise _not_found(exc) from exc


@router.post(
    "/collection-definitions/{identifier}/runs",
    response_model=RunResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["collections"],
)
async def create_run(identifier: str, service: CollectionServiceDependency) -> RunRecord:
    try:
        return await service.create_run(identifier)
    except CollectionNotFoundError as exc:
        raise _not_found(exc) from exc
    except CollectionBudgetError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/collection-runs/{run_id}", response_model=RunResponse, tags=["collections"])
async def get_run(run_id: str, service: CollectionServiceDependency) -> RunRecord:
    try:
        return await service.get_run(run_id)
    except CollectionNotFoundError as exc:
        raise _not_found(exc) from exc


@router.get("/collection-runs", response_model=list[RunResponse], tags=["collections"])
async def list_runs(
    service: CollectionServiceDependency,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[RunRecord]:
    return await service.list_runs(limit)


@router.post("/collection-runs/{run_id}/cancel", response_model=RunResponse, tags=["collections"])
async def cancel_run(run_id: str, service: CollectionServiceDependency) -> RunRecord:
    try:
        return await service.cancel_run(run_id)
    except CollectionNotFoundError as exc:
        raise _not_found(exc) from exc


@router.post(
    "/collection-runs/{run_id}/retry-failed",
    response_model=RetryResponse,
    tags=["collections"],
)
async def retry_failed(run_id: str, service: CollectionServiceDependency) -> RetryResponse:
    try:
        count = await service.retry_failed(run_id)
    except CollectionNotFoundError as exc:
        raise _not_found(exc) from exc
    return RetryResponse(run_id=run_id, retried_tasks=count)


@router.get(
    "/collection-runs/{run_id}/tasks",
    response_model=list[TaskResponse],
    tags=["collections"],
)
async def list_tasks(
    run_id: str,
    service: CollectionServiceDependency,
    limit: int = Query(default=200, ge=1, le=2_000),
    retailer_id: str | None = Query(default=None, min_length=1, max_length=100),
    task_status: str | None = Query(default=None, alias="status", min_length=1, max_length=40),
) -> list[QueueTask]:
    try:
        return await service.list_tasks(
            run_id,
            limit,
            retailer_id=retailer_id,
            status=task_status,
        )
    except CollectionNotFoundError as exc:
        raise _not_found(exc) from exc


@router.get(
    "/collection-runs/{run_id}/usage",
    response_model=UsageResponse,
    tags=["collections"],
)
async def usage(run_id: str, service: CollectionServiceDependency) -> RunUsage:
    try:
        return await service.usage(run_id)
    except CollectionNotFoundError as exc:
        raise _not_found(exc) from exc


@router.get(
    "/collection-runs/{run_id}/monitor",
    response_model=RunMonitorResponse,
    tags=["collections"],
)
async def monitor(run_id: str, service: CollectionServiceDependency) -> RunMonitorResponse:
    try:
        snapshot = await service.monitor(run_id)
    except CollectionNotFoundError as exc:
        raise _not_found(exc) from exc
    return _monitor_response(snapshot)


def _monitor_response(snapshot: RunMonitor) -> RunMonitorResponse:
    return RunMonitorResponse(
        run=RunResponse.model_validate(snapshot.run),
        usage=UsageResponse.model_validate(snapshot.usage),
        retailers=tuple(RetailerProgressResponse.model_validate(row) for row in snapshot.retailers),
        retry_attempts=snapshot.retry_attempts,
        failure_classes={key: int(value) for key, value in snapshot.failure_classes.items()},
        elapsed_seconds=snapshot.elapsed_seconds,
        provider_state=(
            ProviderRateStateResponse.model_validate(snapshot.provider_state)
            if snapshot.provider_state is not None
            else None
        ),
        configured_global_rps=int(os.getenv("METRICSCART_GLOBAL_RPS", "2")),
        configured_global_rpm=int(os.getenv("METRICSCART_GLOBAL_RPM", "108")),
    )
