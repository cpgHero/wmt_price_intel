"""Typed immutable result and delivery records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

JsonObject = dict[str, Any]
ArtifactType = Literal["html", "xlsx", "leadership_email", "audit_zip"]


@dataclass(frozen=True, slots=True)
class AnalysisRecord:
    id: str
    analysis_run_id: str
    analysis_id: str
    collection_run_id: str
    status: str
    product_pack_id: str
    product_pack_version: str
    schema_version: str
    checksum: str
    result: JsonObject
    created_at: datetime
    reporting_status: str = "ready"


@dataclass(frozen=True, slots=True)
class AnalysisPublicationRecord:
    id: str
    analysis_result_id: str
    analysis_id: str
    version: int
    status: str
    source_result_checksum: str
    publication_checksum: str
    result: JsonObject
    presentation_context: JsonObject
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ArtifactPayload:
    artifact_type: ArtifactType
    filename: str
    content_type: str
    body: bytes
    renderer_version: str = "legacy"


@dataclass(frozen=True, slots=True)
class ReportArtifactRecord:
    id: str
    analysis_run_id: str
    publication_id: str | None
    artifact_type: ArtifactType
    renderer_version: str
    dataset_artifact_id: str
    storage_uri: str
    content_type: str
    byte_size: int
    checksum: str
    status: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class DownloadLink:
    artifact_id: str
    url: str
    expires_in_seconds: int
