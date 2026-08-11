"""Product Pack authoring records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

JsonObject = dict[str, Any]
DraftStatus = Literal[
    "draft",
    "validating",
    "candidate",
    "certified",
    "published",
    "abandoned",
]
ValidationSuite = Literal["quick", "compact", "full", "publication"]
ValidationStatus = Literal["queued", "running", "passed", "failed", "cancelled"]


@dataclass(frozen=True, slots=True)
class ProductPackDraft:
    id: str
    product_pack_id: str
    base_version: str | None
    proposed_version: str
    status: DraftStatus
    revision: int
    config: JsonObject
    report_blueprint: JsonObject
    checksum: str
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ProductPackValidationRun:
    id: str
    draft_id: str
    draft_revision: int
    draft_checksum: str
    suite: ValidationSuite
    status: ValidationStatus
    gates: tuple[JsonObject, ...]
    engine_version: str | None
    attempt_count: int
    max_attempts: int
    locked_by: str | None
    lease_expires_at: datetime | None
    last_error: str | None
    cancel_requested_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ProductPackEvidence:
    id: str
    draft_id: str
    kind: str
    label: str
    storage_uri: str
    content_type: str
    checksum: str
    byte_size: int
    row_count: int | None
    metadata: JsonObject
    created_by: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ProductPackPublication:
    product_pack_id: str
    version: str
    checksum: str
    report_blueprint_id: str
    report_blueprint_version: str
    report_blueprint_checksum: str
    validation_run_id: str
    active: bool
    published_by: str
    published_at: datetime
