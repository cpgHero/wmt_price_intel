"""Application service for immutable result publication, reading, and delivery."""

from __future__ import annotations

from typing import Any

from rci_results.contracts import AnalysisResultValidator, result_checksum
from rci_results.models import (
    AnalysisRecord,
    ArtifactType,
    DownloadLink,
    JsonObject,
    ReportArtifactRecord,
)
from rci_results.ports import ResultsRepository
from rci_results.renderers import ArtifactRenderer
from rci_results.storage import ReportObjectStore


class AnalysisNotFoundError(LookupError):
    pass


class ArtifactNotFoundError(LookupError):
    pass


class AnalysisResultService:
    def __init__(
        self,
        repository: ResultsRepository,
        validator: AnalysisResultValidator,
        object_store: ReportObjectStore,
        renderer: ArtifactRenderer | None = None,
    ) -> None:
        self._repository = repository
        self._validator = validator
        self._object_store = object_store
        self._renderer = renderer or ArtifactRenderer()

    async def publish(
        self, document: dict[str, Any], *, collection_run_id: str | None = None
    ) -> AnalysisRecord:
        result = self._validator.validate(document)
        embedded_run_id: str | None
        if result["schema_version"] == "2.0.0":
            source = result["source"]
            assert isinstance(source, dict)
            embedded = source.get("collection_run_id")
            embedded_run_id = str(embedded) if embedded is not None else None
        else:
            embedded_run_id = str(result["collection_run_id"])
        if (
            collection_run_id is not None
            and embedded_run_id is not None
            and embedded_run_id != collection_run_id
        ):
            raise ValueError("AnalysisResult collection_run_id does not match the request path")
        resolved_run_id = collection_run_id or embedded_run_id
        if resolved_run_id is None:
            raise ValueError("historical AnalysisResult publication requires a collection run")
        return await self._repository.publish(
            result,
            result_checksum(result),
            collection_run_id=resolved_run_id,
        )

    async def list_analyses(self, limit: int = 50) -> list[AnalysisRecord]:
        return await self._repository.list_analyses(limit)

    async def get(self, identifier: str) -> AnalysisRecord:
        record = await self._repository.get(identifier)
        if record is None:
            raise AnalysisNotFoundError(f"analysis {identifier!r} was not found")
        return record

    async def get_by_collection_run(self, run_id: str) -> AnalysisRecord:
        record = await self._repository.get_by_collection_run(run_id)
        if record is None:
            raise AnalysisNotFoundError(f"analysis for collection run {run_id!r} was not found")
        return record

    async def matches(self, identifier: str) -> JsonObject:
        record = await self.get(identifier)
        return {
            "analysis_id": record.analysis_id,
            "segments": record.result.get("segments", []),
            "comparisons": record.result.get("comparisons", []),
            "evidence": record.result.get("provenance", {}).get("match_evidence", []),
        }

    async def quality(self, identifier: str) -> JsonObject:
        record = await self.get(identifier)
        return {
            "analysis_id": record.analysis_id,
            "data_quality": record.result["data_quality"],
            "validation": record.result["validation"],
        }

    async def report_view(self, identifier: str) -> JsonObject:
        record = await self.get(identifier)
        return self._renderer.report_view(record.result)

    async def generate_artifact(
        self, identifier: str, artifact_type: ArtifactType
    ) -> ReportArtifactRecord:
        analysis = await self.get(identifier)
        existing = next(
            (
                artifact
                for artifact in await self._repository.list_artifacts(analysis.analysis_id)
                if artifact.artifact_type == artifact_type
            ),
            None,
        )
        if existing is not None:
            return existing
        payload = self._renderer.render(analysis.result, artifact_type)
        storage_uri = await self._object_store.put(analysis.analysis_id, payload)
        return await self._repository.record_artifact(analysis, payload, storage_uri)

    async def list_artifacts(self, identifier: str) -> list[ReportArtifactRecord]:
        analysis = await self.get(identifier)
        return await self._repository.list_artifacts(analysis.analysis_id)

    async def download_link(
        self, artifact_id: str, *, expires_in_seconds: int = 300
    ) -> DownloadLink:
        artifact = await self._repository.get_artifact(artifact_id)
        if artifact is None:
            raise ArtifactNotFoundError(f"artifact {artifact_id!r} was not found")
        url = await self._object_store.presign(
            artifact.storage_uri,
            expires_in_seconds=expires_in_seconds,
        )
        return DownloadLink(
            artifact_id=artifact.id,
            url=url,
            expires_in_seconds=expires_in_seconds,
        )
