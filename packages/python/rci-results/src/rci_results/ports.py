"""Persistence ports for canonical results and delivery artifacts."""

from __future__ import annotations

from typing import Protocol

from rci_results.models import (
    AnalysisPublicationRecord,
    AnalysisRecord,
    ArtifactPayload,
    JsonObject,
    ReportArtifactRecord,
)


class ResultsRepository(Protocol):
    async def publish(
        self,
        result: JsonObject,
        checksum: str,
        *,
        collection_run_id: str,
    ) -> AnalysisRecord: ...

    async def list_analyses(self, limit: int = 50) -> list[AnalysisRecord]: ...

    async def get(self, identifier: str) -> AnalysisRecord | None: ...

    async def get_by_collection_run(self, run_id: str) -> AnalysisRecord | None: ...

    async def publish_publication(
        self,
        analysis: AnalysisRecord,
        result: JsonObject,
        publication_checksum: str,
        *,
        presentation_context: JsonObject,
    ) -> AnalysisPublicationRecord: ...

    async def latest_publication(self, analysis_id: str) -> AnalysisPublicationRecord | None: ...

    async def record_artifact(
        self,
        analysis: AnalysisRecord,
        payload: ArtifactPayload,
        storage_uri: str,
        *,
        publication: AnalysisPublicationRecord | None = None,
    ) -> ReportArtifactRecord: ...

    async def list_artifacts(self, analysis_id: str) -> list[ReportArtifactRecord]: ...

    async def get_artifact(self, artifact_id: str) -> ReportArtifactRecord | None: ...
