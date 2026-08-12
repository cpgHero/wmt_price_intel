"""Versioned collection definition and run APIs."""

from __future__ import annotations

import csv
import io
import json
import os
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

from rci_collections import CollectionPlanner, CollectionRetailerCatalog
from rci_collections.geography import CollectionGeographyResolver
from rci_collections.models import (
    CostEstimate,
    DefinitionRecord,
    GeographyResolution,
    LocationFacet,
    QueueTask,
    RunMonitor,
    RunRecord,
    RunUsage,
    ScopeEstimateRecord,
)
from rci_collections.repository import PostgresCollectionRepository
from rci_collections.service import (
    CollectionApprovalError,
    CollectionBudgetError,
    CollectionNotFoundError,
    CollectionService,
)
from rci_contracts import ContractError
from rci_product_packs import PostgresProductPackCatalog

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


class GeographyLocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: str
    retailer_id: str
    retailer_location_id: str | None
    scope_key: str
    store_number: str | None
    store_name: str | None
    zipcode: str
    city: str | None
    state: str | None
    country: str
    latitude: float | None
    longitude: float | None
    selection_reason: str


class GeographyEdgeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    primary_location_id: str
    competitor_location_id: str
    distance_miles: float


class GeographyResolutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    request: dict[str, Any]
    checksum: str
    status: str
    counts: dict[str, Any]
    locations: tuple[GeographyLocationResponse, ...]
    edges: tuple[GeographyEdgeResponse, ...]
    created_at: datetime


class ScopeEstimateResponse(BaseModel):
    id: str
    definition_id: str
    resolution_id: str
    configuration_checksum: str
    geography_checksum: str
    retailers: tuple[RetailerEstimateResponse, ...]
    estimated_total_pages: int
    estimated_total_credits: int
    expires_at: datetime
    created_at: datetime


class ApprovedLaunchRequest(BaseModel):
    config: dict[str, Any]
    estimate_id: str


class LocationFacetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    state: str
    city: str | None
    location_count: int


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
    scope_estimate_id: str | None


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
        CollectionGeographyResolver(repository, _retailer_catalog()),
    )


CollectionServiceDependency = Annotated[CollectionService, Depends(get_collection_service)]
CollectionConfigBody = Annotated[dict[str, Any], Body()]


def _not_found(exc: CollectionNotFoundError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def _scope_estimate_response(record: ScopeEstimateRecord) -> ScopeEstimateResponse:
    return ScopeEstimateResponse(
        id=record.id,
        definition_id=record.definition_id,
        resolution_id=record.resolution_id,
        configuration_checksum=record.configuration_checksum,
        geography_checksum=record.geography_checksum,
        retailers=tuple(
            RetailerEstimateResponse.model_validate(item) for item in record.estimate.retailers
        ),
        estimated_total_pages=record.estimate.estimated_total_pages,
        estimated_total_credits=record.estimate.estimated_total_credits,
        expires_at=record.expires_at,
        created_at=record.created_at,
    )


@router.get("/collection-builder/options", tags=["collections"])
async def collection_builder_options(request: Request) -> dict[str, Any]:
    root = _repository_root()
    product_packs = json.loads((root / "product-packs" / "index.json").read_text(encoding="utf-8"))
    try:
        published_packs = await PostgresProductPackCatalog(
            request.app.state.database_probe.engine
        ).list_published()
    except Exception:
        published_packs = ()
    pack_options = [
        {
            "id": item.id,
            "name": item.name,
            "version": item.version,
            "default_keyword": item.default_keyword,
            "active": item.active,
        }
        for item in published_packs
    ] or [{**item, "active": True} for item in product_packs["packs"]]
    active_ids = {str(item["id"]) for item in pack_options}
    default_pack_id = str(product_packs["default_pack_id"])
    if default_pack_id not in active_ids:
        default_pack_id = str(pack_options[0]["id"])
    return {
        "retailers": [
            {
                "id": item.retailer_id,
                "display_name": item.display_name,
                "adapter_id": item.adapter_id,
                "location_dimension": item.location_dimension,
                "credits_per_page": item.credits_per_successful_page,
                "status": item.status,
            }
            for item in _retailer_catalog().enabled()
        ],
        "product_packs": pack_options,
        "default_product_pack_id": default_pack_id,
        "geography": {
            "primary_selection_modes": [
                "all_locations",
                "states",
                "per_state",
                "state_cities",
                "custom_zips",
                "custom_locations",
            ],
            "competitor_correspondence_modes": [
                "same_zip",
                "primary_states",
                "radius",
            ],
            "radius_miles": [1, 3, 5],
        },
        "product_detail_policies": [
            "disabled",
            "new_or_changed",
            "refresh_after_7_days",
            "refresh_after_30_days",
            "manual",
        ],
    }


@router.get(
    "/collection-builder/location-facets",
    response_model=list[LocationFacetResponse],
    tags=["collections"],
)
async def collection_builder_location_facets(
    service: CollectionServiceDependency,
    retailer_id: str,
    country: str = "USA",
    states: Annotated[list[str] | None, Query()] = None,
) -> list[LocationFacet]:
    return await service.repository.list_location_facets(retailer_id, country, states or ())


@router.post(
    "/collection-geography-resolutions",
    response_model=GeographyResolutionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["collections"],
)
async def resolve_collection_geography(
    service: CollectionServiceDependency,
    request_body: CollectionConfigBody,
) -> GeographyResolution:
    try:
        return await service.resolve_geography(request_body)
    except ContractError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.get(
    "/collection-geography-resolutions/{resolution_id}",
    response_model=GeographyResolutionResponse,
    tags=["collections"],
)
async def get_collection_geography(
    resolution_id: str,
    service: CollectionServiceDependency,
) -> GeographyResolution:
    try:
        return await service.get_geography_resolution(resolution_id)
    except CollectionNotFoundError as exc:
        raise _not_found(exc) from exc


@router.get(
    "/collection-geography-resolutions/{resolution_id}/locations",
    response_model=list[GeographyLocationResponse],
    tags=["collections"],
)
async def get_collection_geography_locations(
    resolution_id: str,
    service: CollectionServiceDependency,
    retailer_id: str | None = None,
    role: str | None = None,
) -> list[Any]:
    resolution = await get_collection_geography(resolution_id, service)
    return [
        item
        for item in resolution.locations
        if (retailer_id is None or item.retailer_id == retailer_id)
        and (role is None or item.role == role)
    ]


@router.get(
    "/collection-geography-resolutions/{resolution_id}/download",
    tags=["collections"],
)
async def download_collection_geography(
    resolution_id: str,
    service: CollectionServiceDependency,
) -> StreamingResponse:
    resolution = await get_collection_geography(resolution_id, service)
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(
        [
            "role",
            "retailer_id",
            "store_number",
            "store_name",
            "zipcode",
            "city",
            "state",
            "country",
            "latitude",
            "longitude",
            "selection_reason",
        ]
    )
    for item in resolution.locations:
        writer.writerow(
            [
                item.role,
                item.retailer_id,
                item.store_number,
                item.store_name,
                item.zipcode,
                item.city,
                item.state,
                item.country,
                item.latitude,
                item.longitude,
                item.selection_reason,
            ]
        )
    return StreamingResponse(
        iter([stream.getvalue()]),
        media_type="text/csv",
        headers={"content-disposition": f'attachment; filename="geography-{resolution_id}.csv"'},
    )


@router.post(
    "/collection-scope-estimates",
    response_model=ScopeEstimateResponse,
    tags=["collections"],
)
async def create_collection_scope_estimate(
    service: CollectionServiceDependency,
    config: CollectionConfigBody,
) -> ScopeEstimateResponse:
    try:
        return _scope_estimate_response(await service.create_scope_estimate(config))
    except (ContractError, CollectionNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.post(
    "/collection-launches",
    response_model=RunResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["collections"],
)
async def launch_approved_collection(
    service: CollectionServiceDependency,
    request_body: ApprovedLaunchRequest,
) -> RunRecord:
    try:
        return await service.launch_approved(request_body.config, request_body.estimate_id)
    except ContractError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except (CollectionApprovalError, CollectionBudgetError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


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
