"""Value objects for governed Search-first category discovery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

JsonObject = dict[str, Any]


@dataclass(frozen=True, slots=True)
class DiscoveryObservation:
    retailer_id: str
    retailer_product_id: str
    title: str
    brand: str | None
    price: Decimal | None
    zipcode: str | None
    store_number: str | None
    url: str | None
    image_url: str | None
    source_artifact_id: str | None
    identifiers: JsonObject
    fulfillment_type: str | None = None


@dataclass(frozen=True, slots=True)
class DiscoveryProduct:
    retailer_id: str
    retailer_product_id: str
    title: str
    brand: str | None
    url: str | None
    image_url: str | None
    admission_status: str
    admission_reason: str
    observation_count: int
    store_count: int
    zipcode_count: int
    price_min: Decimal | None
    price_max: Decimal | None
    price_contexts: tuple[JsonObject, ...]
    representative_context: JsonObject
    brand_resolution: JsonObject
    identifiers: JsonObject
    source_artifact_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DiscoveryProfile:
    products: tuple[DiscoveryProduct, ...]
    summary: JsonObject


@dataclass(frozen=True, slots=True)
class StudyRecord:
    id: str
    name: str
    status: str
    intake: JsonObject
    query_plan: JsonObject
    query_plan_checksum: str
    approval_state: JsonObject
    geography_resolution_id: str | None
    search_scope_estimate_id: str | None
    collection_run_id: str | None
    pdp_estimate: JsonObject | None
    pdp_plan_checksum: str | None
    pdp_run_id: str | None
    product_pack_draft_id: str | None
    profile_summary: JsonObject
    last_error: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class StudyJob:
    id: str
    study_id: str
    kind: str
    payload: JsonObject
    attempt_count: int
    max_attempts: int
