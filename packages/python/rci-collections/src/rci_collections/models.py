"""Typed collection control-plane records."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

JsonObject = dict[str, Any]


@dataclass(frozen=True, slots=True)
class RetailerCapability:
    retailer_id: str
    display_name: str
    adapter_id: str
    status: str
    location_dimension: str
    credits_per_successful_page: int
    endpoint: str
    supports_pagination: bool = True


@dataclass(frozen=True, slots=True)
class LocationUnit:
    id: str
    retailer_id: str
    zipcode: str | None
    store_number: str
    state: str | None
    country: str
    store_name: str | None = None
    city: str | None = None
    latitude: float | None = None
    longitude: float | None = None


@dataclass(frozen=True, slots=True)
class LocationFacet:
    state: str
    city: str | None
    location_count: int


@dataclass(frozen=True, slots=True)
class GeographyLocation:
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


@dataclass(frozen=True, slots=True)
class GeographyEdge:
    primary_location_id: str
    competitor_location_id: str
    distance_miles: float


@dataclass(frozen=True, slots=True)
class GeographyResolution:
    id: str
    request: JsonObject
    checksum: str
    status: str
    counts: JsonObject
    locations: tuple[GeographyLocation, ...]
    edges: tuple[GeographyEdge, ...]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ScopeEstimateRecord:
    id: str
    definition_id: str
    resolution_id: str
    configuration_checksum: str
    geography_checksum: str
    estimate: CostEstimate
    expires_at: datetime
    created_at: datetime


@dataclass(frozen=True, slots=True)
class TaskSeed:
    retailer_id: str
    retailer_location_id: str | None
    adapter_id: str
    location_scope_key: str
    zipcode: str
    store_number: str | None
    page_number: int
    max_pages: int
    stop_on_empty: bool
    stop_on_short_page: bool
    credits_per_success: int
    request_payload: JsonObject
    request_fingerprint: str
    priority: int = 100
    max_attempts: int = 5
    is_preflight: bool = False


@dataclass(frozen=True, slots=True)
class RetailerEstimate:
    retailer_id: str
    location_units: int
    credits_per_page: int
    max_pages: int
    estimated_pages: int
    estimated_credits: int


@dataclass(frozen=True, slots=True)
class CostEstimate:
    definition_id: str
    retailers: tuple[RetailerEstimate, ...]
    estimated_total_pages: int
    estimated_total_credits: int


@dataclass(frozen=True, slots=True)
class CollectionPlan:
    estimate: CostEstimate
    initial_tasks: tuple[TaskSeed, ...]
    availability_gate: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DefinitionRecord:
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
class RunRecord:
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
    trigger_type: str = "manual"
    schedule_id: str | None = None
    scheduled_for: datetime | None = None
    availability_gate_status: str = "skipped"
    availability_gate_config: JsonObject = field(default_factory=dict)
    scope_estimate_id: str | None = None


class BudgetExceededError(ValueError):
    """Raised when an atomic collection-run budget reservation cannot be made."""


@dataclass(frozen=True, slots=True)
class QueueTask:
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
    stop_on_empty: bool
    stop_on_short_page: bool
    credits_per_success: int
    request_payload: JsonObject
    request_fingerprint: str
    status: str
    priority: int
    attempt_count: int
    max_attempts: int
    available_at: datetime
    locked_by: str | None
    lease_expires_at: datetime | None
    created_at: datetime
    http_status: int | None = None
    result_count: int | None = None
    failure_class: str | None = None
    last_error: str | None = None
    billable_credits: int = 0
    raw_artifact_id: str | None = None
    is_preflight: bool = False


@dataclass(frozen=True, slots=True)
class RawArtifact:
    storage_uri: str
    content_type: str
    byte_size: int
    checksum: str
    metadata: JsonObject
    artifact_type: str = "raw_provider_response"
    schema_version: str = "1.0.0"
    row_count: int | None = None


@dataclass(frozen=True, slots=True)
class ProviderPage:
    http_status: int
    result_count: int
    page_size: int | None = None
    raw_artifact: RawArtifact | None = None


@dataclass(frozen=True, slots=True)
class RunUsage:
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


@dataclass(frozen=True, slots=True)
class RetailerRunProgress:
    retailer_id: str
    pending_tasks: int
    running_tasks: int
    succeeded_tasks: int
    failed_tasks: int
    cancelled_tasks: int
    billable_credits: int
    attempts: int
    retries: int


@dataclass(frozen=True, slots=True)
class ProviderRateState:
    provider: str
    second_count: int
    minute_count: int
    paused_until: datetime | None
    last_429_at: datetime | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class RunMonitor:
    run: RunRecord
    usage: RunUsage
    retailers: tuple[RetailerRunProgress, ...]
    retry_attempts: int
    failure_classes: JsonObject
    elapsed_seconds: float
    provider_state: ProviderRateState | None
