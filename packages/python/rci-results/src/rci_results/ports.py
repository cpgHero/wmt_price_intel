"""Persistence ports for canonical results and delivery artifacts."""

from __future__ import annotations

from typing import Protocol

from rci_results.models import (
    AnalysisRecord,
    ArtifactPayload,
    JsonObject,
    ReportArtifactRecord,
)


class ResultsRepository(Protocol):
    async def publish(self, result: JsonObject, checksum: str) -> AnalysisRecord: ...

    async def list_analyses(self, limit: int = 50) -> list[AnalysisRecord]: ...

    async def get(self, identifier: str) -> AnalysisRecord | None: ...

    async def record_artifact(
        self,
        analysis: AnalysisRecord,
        payload: ArtifactPayload,
        storage_uri: str,
    ) -> ReportArtifactRecord: ...

    async def list_artifacts(self, analysis_id: str) -> list[ReportArtifactRecord]: ...

    async def get_artifact(self, artifact_id: str) -> ReportArtifactRecord | None: ...
