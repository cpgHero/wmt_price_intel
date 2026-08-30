"""Versioned collection definition and run APIs."""

from __future__ import annotations

import csv
import io
import json
import os
import secrets
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from rci_collections import CollectionPlanner, CollectionRetailerCatalog
from rci_collections.composite import (
    CompositeInputSetRecord,
    ContinuationSelectionPreview,
    PostgresCompositeEvidenceRepository,
    RecoveryBatchRecord,
    RecoveryBatchRunRecord,
    RecoveryBatchStatusRecord,
    RecoveryLaunchRecord,
    RecoveryPlanRecord,
    RecoverySelectionPreview,
    RetailerUnavailabilityApprovalRecord,
    ScopeProjectionPreview,
    ScopeProjectionRecord,
)
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
from rci_core import APP_VERSION
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


class RecoveryRetailerSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    retailer_id: str
    selected_tasks: int
    required_tasks: int
    optional_transient_tasks: int
    maximum_provider_attempts: int
    maximum_credits: int
    reused_successes: int
    retained_billable_404s: int
    retained_billable_404_credits: int


class RecoverySelectionItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_task_id: str
    retailer_id: str
    canonical_request_key: str
    selection_reason: str
    required_for_assembly: bool
    credits_per_success: int
    maximum_credits: int
    source_snapshot: dict[str, Any]


class RecoverySelectionPreviewResponse(BaseModel):
    base_collection_run_id: str
    selection_policy_version: str
    selection_checksum: str
    base_snapshot_checksum: str
    selected_task_count: int
    maximum_provider_attempts: int
    maximum_credits: int
    retailers: tuple[RecoveryRetailerSummaryResponse, ...]
    items: tuple[RecoverySelectionItemResponse, ...]


class ScopeProjectionItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_task_id: str
    retailer_id: str
    canonical_request_key: str
    disposition: str
    reason: str
    mapped_retained_task_id: str | None
    source_snapshot: dict[str, Any]


class ScopeProjectionPreviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    base_collection_run_id: str
    retailer_id: str
    projection_kind: str
    policy_version: str
    base_snapshot_checksum: str
    source_audit_id: str | None
    source_evidence_checksum: str
    raw_task_count: int
    retained_task_count: int
    excluded_task_count: int
    raw_location_count: int
    retained_location_count: int
    excluded_location_count: int
    raw_task_retention_ratio: str
    governed_coverage_ratio: str
    minimum_scoreable_coverage: str
    scorecard_disposition: str
    projection_checksum: str
    manifest: dict[str, Any]
    item_offset: int
    item_limit: int
    next_item_offset: int | None
    items: tuple[ScopeProjectionItemResponse, ...]


class ApproveScopeProjectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retailer_id: str = Field(min_length=1, max_length=100)
    projection_kind: Literal["canonical_alias_collapse", "limited_provider_footprint"]
    projection_checksum: str = Field(min_length=64, max_length=64)
    base_snapshot_checksum: str = Field(min_length=64, max_length=64)
    source_audit_id: UUID | None = None
    review_reason: str = Field(min_length=1, max_length=2_000)


class ScopeProjectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    base_collection_run_id: str
    retailer_id: str
    projection_kind: str
    policy_version: str
    base_snapshot_checksum: str
    source_audit_id: str | None
    source_evidence_checksum: str
    raw_task_count: int
    retained_task_count: int
    excluded_task_count: int
    raw_location_count: int
    retained_location_count: int
    excluded_location_count: int
    raw_task_retention_ratio: str
    governed_coverage_ratio: str
    minimum_scoreable_coverage: str
    scorecard_disposition: str
    projection_checksum: str
    review_reason: str
    reviewed_by: str
    manifest: dict[str, Any]
    created_at: datetime


class ContinuationSelectionPreviewResponse(BaseModel):
    base_collection_run_id: str
    continuation_of_recovery_plan_id: str
    lineage_plan_ids: tuple[str, ...]
    lineage_checksum: str
    selection_policy_version: str
    selection_checksum: str
    base_snapshot_checksum: str
    selected_task_count: int
    maximum_provider_attempts: int
    maximum_credits: int
    resolved_before_count: int
    conclusive_before_count: int
    retained_success_count: int
    retained_billable_404_count: int
    retailers: tuple[RecoveryRetailerSummaryResponse, ...]
    item_offset: int
    item_limit: int
    next_item_offset: int | None
    items: tuple[RecoverySelectionItemResponse, ...]


class ApproveRecoveryPlanRequest(BaseModel):
    selection_checksum: str
    approved_credit_ceiling: int
    reason: str
    retailer_ids: tuple[str, ...] = ()
    supersedes_recovery_plan_id: UUID | None = None
    recovery_batch_id: UUID | None = None
    plan_mode: Literal["exact_launch", "legacy_adoption"] = "exact_launch"
    scope_projection_id: UUID | None = None
    scope_projection_checksum: str | None = Field(default=None, min_length=64, max_length=64)


class ApproveRecoveryContinuationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selection_checksum: str = Field(min_length=64, max_length=64)
    lineage_checksum: str = Field(min_length=64, max_length=64)
    base_snapshot_checksum: str = Field(min_length=64, max_length=64)
    approved_credit_ceiling: int = Field(gt=0)
    reason: str = Field(min_length=1, max_length=2_000)
    retailer_ids: tuple[str, ...] = Field(default=(), max_length=100)
    recovery_batch_id: UUID


class ApproveRetailerUnavailabilityRequest(BaseModel):
    retailer_id: str
    base_snapshot_checksum: str
    reason: str


class RetailerUnavailabilityApprovalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    base_collection_run_id: str
    retailer_id: str
    base_snapshot_checksum: str
    reason: str
    approved_by: str
    status: str
    created_at: datetime
    revoked_at: datetime | None
    revoked_by: str | None


class RecoveryPlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    base_collection_run_id: str
    recovery_collection_run_id: str | None
    recovery_batch_id: str | None
    plan_mode: str
    reservation_active: bool
    selection_policy_version: str
    selection_checksum: str
    base_snapshot_checksum: str
    scope_projection_id: str | None
    scope_projection_checksum: str | None
    selection_scope: dict[str, Any]
    plan_generation: int
    supersedes_recovery_plan_id: str | None
    continuation_of_recovery_plan_id: str | None
    continuation_depth: int
    selected_task_count: int
    maximum_credits: int
    approved_credit_ceiling: int
    reason: str
    approved_by: str
    status: str
    binding_manifest: dict[str, Any]
    created_at: datetime


class RecoveryLaunchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    recovery_plan_id: str
    collection_run_id: str
    definition_version_id: str
    status: str
    task_count: int
    maximum_credits: int
    availability_gate_status: str
    reused_existing_run: bool


class CreateRecoveryBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authorization_id: UUID


class RecoveryBatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    spend_authorization_id: str
    phase_key: str
    inventory_checksum: str
    authorized_run_ids: tuple[str, ...]
    approved_credit_ceiling: int
    reserved_credits: int
    unit_cost_usd: str
    currency: str
    reason: str
    approved_by: str
    status: str
    created_at: datetime
    closed_at: datetime | None


class RecoveryBatchInventoryRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    collection_run_id: str
    status: str
    actual_credits: int
    estimated_credits: int
    accounted_credits: int


class RecoveryBatchStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    batch: RecoveryBatchResponse
    accounted_credits: int
    remaining_credits: int
    approved_amount_usd: str
    accounted_amount_usd: str
    recovery_plan_count: int
    runs: tuple[RecoveryBatchInventoryRunResponse, ...]


class RecoveryBatchRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    recovery_batch_id: str
    collection_run_id: str
    accounted_credits: int
    batch_accounted_credits: int


class BindRecoveryRunRequest(BaseModel):
    recovery_run_id: UUID
    binding_mode: Literal["legacy_operational_adoption"] = "legacy_operational_adoption"


class MaterializeCompositeInputRequest(BaseModel):
    recovery_plan_ids: tuple[UUID, ...]
    scope_projection_ids: tuple[UUID, ...] = ()


class CompositeInputSetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    base_collection_run_id: str
    recovery_collection_run_ids: tuple[str, ...]
    assembly_generation: int
    manifest_checksum: str
    total_rows: int
    trust_state: str
    status: str
    analysis_run_id: str | None


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


class RetailerGateProgressResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    retailer_id: str
    status: str
    sample_size: int
    completed_samples: int
    open_samples: int
    successful_samples: int
    not_found_samples: int
    other_failure_samples: int
    transient_nonbillable_failure_samples: int
    hard_failure_samples: int
    maximum_404_rate: float
    minimum_successful_samples: int | None
    max_transient_nonbillable_failures: int | None
    reason: str | None
    resolved_at: datetime | None


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
    retailer_gates: tuple[RetailerGateProgressResponse, ...]
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


def get_composite_evidence_repository(
    request: Request,
) -> PostgresCompositeEvidenceRepository:
    return PostgresCompositeEvidenceRepository(
        request.app.state.database_probe.engine,
        analysis_code_version=request.app.state.settings.app_version or APP_VERSION,
        analysis_max_attempts=int(os.getenv("ANALYSIS_MAX_ATTEMPTS", "3")),
        provider_request_contracts=_retailer_catalog().provider_request_contracts(),
        provider_error_evidence_contracts=(_retailer_catalog().provider_error_evidence_contracts()),
    )


CollectionServiceDependency = Annotated[CollectionService, Depends(get_collection_service)]
CompositeEvidenceDependency = Annotated[
    PostgresCompositeEvidenceRepository,
    Depends(get_composite_evidence_repository),
]
CollectionConfigBody = Annotated[dict[str, Any], Body()]


def _not_found(exc: CollectionNotFoundError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def _require_recovery_admin(request: Request, provided: str | None) -> None:
    expected = os.getenv("PRODUCT_PACK_ADMIN_TOKEN", "").strip()
    if request.app.state.settings.is_production and (
        not expected or not provided or not secrets.compare_digest(expected, provided)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated administrator access is required.",
        )


def _recovery_admin_actor() -> str:
    """Return a server-controlled principal; client headers cannot forge audit identity."""

    return "authenticated-platform-admin"


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


def _recovery_preview_response(
    preview: RecoverySelectionPreview,
    *,
    include_items: bool,
) -> RecoverySelectionPreviewResponse:
    return RecoverySelectionPreviewResponse(
        base_collection_run_id=preview.base_collection_run_id,
        selection_policy_version=preview.selection_policy_version,
        selection_checksum=preview.selection_checksum,
        base_snapshot_checksum=preview.base_snapshot_checksum,
        selected_task_count=preview.selected_task_count,
        maximum_provider_attempts=preview.maximum_provider_attempts,
        maximum_credits=preview.maximum_credits,
        retailers=tuple(
            RecoveryRetailerSummaryResponse.model_validate(item) for item in preview.retailers
        ),
        items=(
            tuple(RecoverySelectionItemResponse.model_validate(item) for item in preview.items)
            if include_items
            else ()
        ),
    )


def _continuation_preview_response(
    preview: ContinuationSelectionPreview,
    *,
    item_offset: int,
    item_limit: int,
) -> ContinuationSelectionPreviewResponse:
    page = preview.items[item_offset : item_offset + item_limit]
    next_offset = item_offset + len(page)
    return ContinuationSelectionPreviewResponse(
        base_collection_run_id=preview.base_collection_run_id,
        continuation_of_recovery_plan_id=preview.continuation_of_recovery_plan_id,
        lineage_plan_ids=preview.lineage_plan_ids,
        lineage_checksum=preview.lineage_checksum,
        selection_policy_version=preview.selection_policy_version,
        selection_checksum=preview.selection_checksum,
        base_snapshot_checksum=preview.base_snapshot_checksum,
        selected_task_count=preview.selected_task_count,
        maximum_provider_attempts=preview.maximum_provider_attempts,
        maximum_credits=preview.maximum_credits,
        resolved_before_count=preview.resolved_before_count,
        conclusive_before_count=preview.conclusive_before_count,
        retained_success_count=preview.retained_success_count,
        retained_billable_404_count=preview.retained_billable_404_count,
        retailers=tuple(
            RecoveryRetailerSummaryResponse.model_validate(item) for item in preview.retailers
        ),
        item_offset=item_offset,
        item_limit=item_limit,
        next_item_offset=(next_offset if next_offset < preview.selected_task_count else None),
        items=tuple(RecoverySelectionItemResponse.model_validate(item) for item in page),
    )


def _scope_projection_preview_response(
    preview: ScopeProjectionPreview,
    *,
    item_offset: int,
    item_limit: int,
) -> ScopeProjectionPreviewResponse:
    page = preview.items[item_offset : item_offset + item_limit]
    next_offset = item_offset + len(page)
    return ScopeProjectionPreviewResponse(
        base_collection_run_id=preview.base_collection_run_id,
        retailer_id=preview.retailer_id,
        projection_kind=preview.projection_kind,
        policy_version=preview.policy_version,
        base_snapshot_checksum=preview.base_snapshot_checksum,
        source_audit_id=preview.source_audit_id,
        source_evidence_checksum=preview.source_evidence_checksum,
        raw_task_count=preview.raw_task_count,
        retained_task_count=preview.retained_task_count,
        excluded_task_count=preview.excluded_task_count,
        raw_location_count=preview.raw_location_count,
        retained_location_count=preview.retained_location_count,
        excluded_location_count=preview.excluded_location_count,
        raw_task_retention_ratio=preview.raw_task_retention_ratio,
        governed_coverage_ratio=preview.governed_coverage_ratio,
        minimum_scoreable_coverage=preview.minimum_scoreable_coverage,
        scorecard_disposition=preview.scorecard_disposition,
        projection_checksum=preview.projection_checksum,
        manifest=preview.manifest,
        item_offset=item_offset,
        item_limit=item_limit,
        next_item_offset=(next_offset if next_offset < preview.raw_task_count else None),
        items=tuple(ScopeProjectionItemResponse.model_validate(item) for item in page),
    )


def _composite_error(exc: LookupError | ValueError) -> HTTPException:
    return HTTPException(
        status_code=(
            status.HTTP_404_NOT_FOUND if isinstance(exc, LookupError) else status.HTTP_409_CONFLICT
        ),
        detail=str(exc),
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
                "supports_pagination": item.supports_pagination,
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
async def retry_failed(
    run_id: str,
    request: Request,
    service: CollectionServiceDependency,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> RetryResponse:
    _require_recovery_admin(request, x_rci_admin_token)
    try:
        count = await service.retry_failed(run_id)
    except CollectionNotFoundError as exc:
        raise _not_found(exc) from exc
    except CollectionApprovalError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return RetryResponse(run_id=run_id, retried_tasks=count)


@router.get(
    "/collection-runs/{run_id}/scope-projection-preview",
    response_model=ScopeProjectionPreviewResponse,
    tags=["collections"],
)
async def preview_collection_scope_projection(
    run_id: UUID,
    request: Request,
    repository: CompositeEvidenceDependency,
    retailer_id: str = Query(min_length=1, max_length=100),
    projection_kind: Literal["canonical_alias_collapse", "limited_provider_footprint"] = Query(),
    source_audit_id: Annotated[UUID | None, Query()] = None,
    item_offset: int = Query(default=0, ge=0, le=100_000),
    item_limit: int = Query(default=100, ge=1, le=500),
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> ScopeProjectionPreviewResponse:
    """Preview every retained/excluded frozen task before approval."""

    _require_recovery_admin(request, x_rci_admin_token)
    try:
        preview = await repository.preview_scope_projection(
            str(run_id),
            retailer_id=retailer_id,
            projection_kind=projection_kind,
            source_audit_id=(str(source_audit_id) if source_audit_id is not None else None),
        )
    except (LookupError, ValueError) as exc:
        raise _composite_error(exc) from exc
    return _scope_projection_preview_response(
        preview, item_offset=item_offset, item_limit=item_limit
    )


@router.post(
    "/collection-runs/{run_id}/scope-projections",
    response_model=ScopeProjectionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["collections"],
)
async def approve_collection_scope_projection(
    run_id: UUID,
    request_body: ApproveScopeProjectionRequest,
    request: Request,
    repository: CompositeEvidenceDependency,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> ScopeProjectionRecord:
    """Persist only the exact complete projection reviewed by an administrator."""

    _require_recovery_admin(request, x_rci_admin_token)
    try:
        return await repository.approve_scope_projection(
            str(run_id),
            retailer_id=request_body.retailer_id,
            projection_kind=request_body.projection_kind,
            projection_checksum=request_body.projection_checksum,
            base_snapshot_checksum=request_body.base_snapshot_checksum,
            source_audit_id=(
                str(request_body.source_audit_id)
                if request_body.source_audit_id is not None
                else None
            ),
            review_reason=request_body.review_reason,
            reviewed_by=_recovery_admin_actor(),
        )
    except (LookupError, ValueError) as exc:
        raise _composite_error(exc) from exc


@router.get(
    "/collection-runs/{run_id}/recovery-preview",
    response_model=RecoverySelectionPreviewResponse,
    tags=["collections"],
)
async def preview_failure_only_recovery(
    run_id: UUID,
    request: Request,
    repository: CompositeEvidenceDependency,
    retailer_ids: Annotated[list[str] | None, Query()] = None,
    include_items: bool = Query(default=False),
    scope_projection_id: Annotated[UUID | None, Query()] = None,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> RecoverySelectionPreviewResponse:
    """Preview a zero-overlap, checksum-bound recovery selection."""

    _require_recovery_admin(request, x_rci_admin_token)
    try:
        preview = await repository.preview(
            str(run_id),
            retailer_ids=retailer_ids or (),
            scope_projection_id=(
                str(scope_projection_id) if scope_projection_id is not None else None
            ),
        )
    except (LookupError, ValueError) as exc:
        raise _composite_error(exc) from exc
    return _recovery_preview_response(preview, include_items=include_items)


@router.post(
    "/collection-runs/{run_id}/retailer-unavailability",
    response_model=RetailerUnavailabilityApprovalResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["collections"],
)
async def approve_retailer_unavailability(
    run_id: UUID,
    request_body: ApproveRetailerUnavailabilityRequest,
    request: Request,
    repository: CompositeEvidenceDependency,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> RetailerUnavailabilityApprovalRecord:
    _require_recovery_admin(request, x_rci_admin_token)
    try:
        return await repository.approve_retailer_unavailability(
            str(run_id),
            retailer_id=request_body.retailer_id,
            base_snapshot_checksum=request_body.base_snapshot_checksum,
            reason=request_body.reason,
            approved_by=_recovery_admin_actor(),
        )
    except (LookupError, ValueError) as exc:
        raise _composite_error(exc) from exc


@router.post(
    "/retailer-unavailability/{approval_id}/revoke",
    response_model=RetailerUnavailabilityApprovalResponse,
    tags=["collections"],
)
async def revoke_retailer_unavailability(
    approval_id: UUID,
    request: Request,
    repository: CompositeEvidenceDependency,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> RetailerUnavailabilityApprovalRecord:
    _require_recovery_admin(request, x_rci_admin_token)
    try:
        return await repository.revoke_retailer_unavailability(
            str(approval_id), revoked_by=_recovery_admin_actor()
        )
    except (LookupError, ValueError) as exc:
        raise _composite_error(exc) from exc


@router.post(
    "/collection-recovery-batches",
    response_model=RecoveryBatchResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["collections"],
)
async def create_recovery_batch(
    request_body: CreateRecoveryBatchRequest,
    request: Request,
    repository: CompositeEvidenceDependency,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> RecoveryBatchRecord:
    _require_recovery_admin(request, x_rci_admin_token)
    try:
        return await repository.create_recovery_batch(
            authorization_id=str(request_body.authorization_id),
        )
    except (LookupError, ValueError) as exc:
        raise _composite_error(exc) from exc


@router.get(
    "/collection-recovery-batches/{batch_id}",
    response_model=RecoveryBatchStatusResponse,
    tags=["collections"],
)
async def get_recovery_batch_status(
    batch_id: UUID,
    request: Request,
    repository: CompositeEvidenceDependency,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> RecoveryBatchStatusRecord:
    _require_recovery_admin(request, x_rci_admin_token)
    try:
        return await repository.get_recovery_batch_status(str(batch_id))
    except (LookupError, ValueError) as exc:
        raise _composite_error(exc) from exc


@router.post(
    "/collection-recovery-batches/{batch_id}/close",
    response_model=RecoveryBatchStatusResponse,
    tags=["collections"],
)
async def close_recovery_batch(
    batch_id: UUID,
    request: Request,
    repository: CompositeEvidenceDependency,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> RecoveryBatchStatusRecord:
    _require_recovery_admin(request, x_rci_admin_token)
    try:
        return await repository.close_recovery_batch(str(batch_id))
    except (LookupError, ValueError) as exc:
        raise _composite_error(exc) from exc


@router.post(
    "/collection-recovery-batches/{batch_id}/runs/{run_id}",
    response_model=RecoveryBatchRunResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["collections"],
)
async def attach_run_to_recovery_batch(
    batch_id: UUID,
    run_id: UUID,
    request: Request,
    repository: CompositeEvidenceDependency,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> RecoveryBatchRunRecord:
    _require_recovery_admin(request, x_rci_admin_token)
    try:
        return await repository.attach_run_to_recovery_batch(str(batch_id), str(run_id))
    except (LookupError, ValueError) as exc:
        raise _composite_error(exc) from exc


@router.post(
    "/collection-runs/{run_id}/recovery-plans",
    response_model=RecoveryPlanResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["collections"],
)
async def approve_failure_only_recovery(
    run_id: UUID,
    request_body: ApproveRecoveryPlanRequest,
    request: Request,
    repository: CompositeEvidenceDependency,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> RecoveryPlanRecord:
    """Persist approval for the exact previewed task set without launching it."""

    _require_recovery_admin(request, x_rci_admin_token)
    try:
        return await repository.approve(
            str(run_id),
            selection_checksum=request_body.selection_checksum,
            approved_credit_ceiling=request_body.approved_credit_ceiling,
            reason=request_body.reason,
            approved_by=_recovery_admin_actor(),
            retailer_ids=request_body.retailer_ids,
            supersedes_recovery_plan_id=(
                str(request_body.supersedes_recovery_plan_id)
                if request_body.supersedes_recovery_plan_id is not None
                else None
            ),
            recovery_batch_id=(
                str(request_body.recovery_batch_id)
                if request_body.recovery_batch_id is not None
                else None
            ),
            plan_mode=request_body.plan_mode,
            scope_projection_id=(
                str(request_body.scope_projection_id)
                if request_body.scope_projection_id is not None
                else None
            ),
            scope_projection_checksum=request_body.scope_projection_checksum,
        )
    except (LookupError, ValueError) as exc:
        raise _composite_error(exc) from exc


@router.get(
    "/collection-recovery-plans/{plan_id}/continuation-preview",
    response_model=ContinuationSelectionPreviewResponse,
    tags=["collections"],
)
async def preview_unresolved_recovery_continuation(
    plan_id: UUID,
    request: Request,
    repository: CompositeEvidenceDependency,
    retailer_ids: Annotated[list[str] | None, Query(max_length=100)] = None,
    item_offset: int = Query(default=0, ge=0, le=50_000),
    item_limit: int = Query(default=100, ge=1, le=500),
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> ContinuationSelectionPreviewResponse:
    """Preview a paginated unresolved-only child of a terminal plan lineage."""

    _require_recovery_admin(request, x_rci_admin_token)
    try:
        preview = await repository.preview_continuation(
            str(plan_id), retailer_ids=retailer_ids or ()
        )
    except (LookupError, ValueError) as exc:
        raise _composite_error(exc) from exc
    return _continuation_preview_response(
        preview,
        item_offset=item_offset,
        item_limit=item_limit,
    )


@router.post(
    "/collection-recovery-plans/{plan_id}/continuations",
    response_model=RecoveryPlanResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["collections"],
)
async def approve_unresolved_recovery_continuation(
    plan_id: UUID,
    request_body: ApproveRecoveryContinuationRequest,
    request: Request,
    repository: CompositeEvidenceDependency,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> RecoveryPlanRecord:
    """Approve exactly the full checksum-bound continuation preview."""

    _require_recovery_admin(request, x_rci_admin_token)
    try:
        return await repository.approve_continuation(
            str(plan_id),
            selection_checksum=request_body.selection_checksum,
            lineage_checksum=request_body.lineage_checksum,
            base_snapshot_checksum=request_body.base_snapshot_checksum,
            approved_credit_ceiling=request_body.approved_credit_ceiling,
            reason=request_body.reason,
            approved_by=_recovery_admin_actor(),
            retailer_ids=request_body.retailer_ids,
            recovery_batch_id=str(request_body.recovery_batch_id),
        )
    except (LookupError, ValueError) as exc:
        raise _composite_error(exc) from exc


@router.post(
    "/collection-recovery-plans/{plan_id}/launch",
    response_model=RecoveryLaunchResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["collections"],
)
async def launch_failure_only_recovery(
    plan_id: UUID,
    request: Request,
    repository: CompositeEvidenceDependency,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> RecoveryLaunchRecord:
    """Idempotently launch only the checksum-bound, approved recovery tasks."""

    _require_recovery_admin(request, x_rci_admin_token)
    try:
        return await repository.launch_exact_recovery(str(plan_id))
    except (LookupError, ValueError) as exc:
        raise _composite_error(exc) from exc


@router.post(
    "/collection-recovery-plans/{plan_id}/bind-run",
    response_model=RecoveryPlanResponse,
    tags=["collections"],
)
async def bind_recovery_run(
    plan_id: UUID,
    request_body: BindRecoveryRunRequest,
    request: Request,
    repository: CompositeEvidenceDependency,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> RecoveryPlanRecord:
    _require_recovery_admin(request, x_rci_admin_token)
    try:
        return await repository.bind_recovery_run(
            str(plan_id),
            str(request_body.recovery_run_id),
            binding_mode=request_body.binding_mode,
        )
    except (LookupError, ValueError) as exc:
        raise _composite_error(exc) from exc


@router.post(
    "/collection-runs/{run_id}/composite-input-sets",
    response_model=CompositeInputSetResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["collections"],
)
async def materialize_composite_input_set(
    run_id: UUID,
    request_body: MaterializeCompositeInputRequest,
    request: Request,
    repository: CompositeEvidenceDependency,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> CompositeInputSetRecord:
    """Assemble de-duplicated evidence; blocked assemblies never queue analysis."""

    _require_recovery_admin(request, x_rci_admin_token)
    try:
        return await repository.materialize(
            str(run_id),
            tuple(str(value) for value in request_body.recovery_plan_ids),
            tuple(str(value) for value in request_body.scope_projection_ids),
        )
    except (LookupError, ValueError) as exc:
        raise _composite_error(exc) from exc


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
    "/collection-runs/{run_id}/failures.csv",
    tags=["collections"],
)
async def download_collection_failures(
    run_id: str, service: CollectionServiceDependency
) -> StreamingResponse:
    try:
        tasks = await service.list_tasks(run_id, 100_000, status="failed")
    except CollectionNotFoundError as exc:
        raise _not_found(exc) from exc
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(
        [
            "retailer_id",
            "adapter_id",
            "zipcode",
            "store_number",
            "location_scope_key",
            "page_number",
            "is_preflight",
            "http_status",
            "failure_class",
            "last_error",
            "attempt_count",
            "max_attempts",
            "billable_credits",
            "request_payload",
        ]
    )
    for task in tasks:
        writer.writerow(
            [
                task.retailer_id,
                task.adapter_id,
                task.zipcode,
                task.store_number,
                task.location_scope_key,
                task.page_number,
                task.is_preflight,
                task.http_status,
                task.failure_class,
                task.last_error,
                task.attempt_count,
                task.max_attempts,
                task.billable_credits,
                json.dumps(task.request_payload, sort_keys=True),
            ]
        )
    return StreamingResponse(
        iter([stream.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"content-disposition": f'attachment; filename="collection-{run_id}-failures.csv"'},
    )


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
        retailer_gates=tuple(
            RetailerGateProgressResponse.model_validate(row) for row in snapshot.retailer_gates
        ),
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
