"""Application service for immutable result publication, reading, and delivery."""

from __future__ import annotations

from typing import Any

from rci_results.contracts import AnalysisResultValidator, result_checksum
from rci_results.models import (
    AnalysisPublicationRecord,
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


class ProductEvidenceNotFoundError(LookupError):
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

    async def publish_publication(
        self,
        identifier: str,
        document: dict[str, Any],
        *,
        presentation_context: JsonObject | None = None,
    ) -> AnalysisPublicationRecord:
        analysis = await self.get(identifier)
        result = self._validator.validate(document)
        if str(result.get("schema_version")) != "2.0.0":
            raise ValueError("governed publications require AnalysisResult V2")
        if str(result.get("analysis_id")) != analysis.analysis_id:
            raise ValueError("publication analysis_id does not match the immutable result")
        product_pack = result.get("product_pack")
        if not isinstance(product_pack, dict) or (
            str(product_pack.get("id")) != analysis.product_pack_id
            or str(product_pack.get("version")) != analysis.product_pack_version
        ):
            raise ValueError("publication Product Pack does not match the immutable result")
        for field in ("source", "metrics", "evidence_sets"):
            if result_checksum({"value": result.get(field)}) != result_checksum(
                {"value": analysis.result.get(field)}
            ):
                raise ValueError(f"publication changed authoritative {field}")
        context = dict(presentation_context or {})
        unknown_context = set(context) - {
            "product_highlights",
            "product_decisions",
            "product_evidence",
            "map_points",
            "notes",
        }
        if unknown_context:
            raise ValueError(
                f"publication presentation context has unsupported keys {sorted(unknown_context)}"
            )
        publication_checksum = result_checksum(
            {
                "result_checksum": result_checksum(result),
                "presentation_context": context,
            }
        )
        return await self._repository.publish_publication(
            analysis,
            result,
            publication_checksum,
            presentation_context=context,
        )

    async def latest_publication(self, identifier: str) -> AnalysisPublicationRecord | None:
        analysis = await self.get(identifier)
        return await self._repository.latest_publication(analysis.analysis_id)

    async def _presentation_source(
        self, identifier: str
    ) -> tuple[AnalysisRecord, AnalysisPublicationRecord | None, JsonObject]:
        analysis = await self.get(identifier)
        publication = await self._repository.latest_publication(analysis.analysis_id)
        document = publication.result if publication is not None else analysis.result
        return analysis, publication, document

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
        _analysis, publication, document = await self._presentation_source(identifier)
        presentation_context = (
            {
                key: value
                for key, value in publication.presentation_context.items()
                if key != "product_evidence"
            }
            if publication is not None
            else None
        )
        view = self._renderer.report_view(
            document,
            presentation_context=presentation_context,
        )
        provenance = document.get("provenance", {})
        governed_checksum = (
            provenance.get("final_result_checksum_sha256") if isinstance(provenance, dict) else None
        )
        view["result_checksum"] = (
            governed_checksum
            if isinstance(governed_checksum, str) and len(governed_checksum) == 64
            else result_checksum(document)
        )
        view["publication"] = (
            {
                "id": publication.id,
                "version": publication.version,
                "status": publication.status,
                "source_result_checksum": publication.source_result_checksum,
                "publication_checksum": publication.publication_checksum,
                "created_at": publication.created_at.isoformat(),
            }
            if publication is not None
            else None
        )
        return view

    async def product_evidence(self, identifier: str, decision_id: str) -> JsonObject:
        analysis, publication, _document = await self._presentation_source(identifier)
        if publication is None:
            raise ProductEvidenceNotFoundError(
                f"product evidence for analysis {analysis.analysis_id!r} is not available"
            )
        evidence = publication.presentation_context.get("product_evidence", {})
        if not isinstance(evidence, dict) or not isinstance(evidence.get(decision_id), dict):
            raise ProductEvidenceNotFoundError(
                f"product decision evidence {decision_id!r} was not found"
            )
        decisions = publication.presentation_context.get("product_decisions", [])
        decision = next(
            (
                dict(row)
                for row in decisions
                if isinstance(row, dict) and str(row.get("id")) == decision_id
            ),
            None,
        )
        return {
            "analysis_id": analysis.analysis_id,
            "publication_id": publication.id,
            "publication_version": publication.version,
            "decision": decision,
            **dict(evidence[decision_id]),
        }

    async def generate_artifact(
        self, identifier: str, artifact_type: ArtifactType
    ) -> ReportArtifactRecord:
        analysis, publication, document = await self._presentation_source(identifier)
        existing = next(
            (
                artifact
                for artifact in await self._repository.list_artifacts(analysis.analysis_id)
                if artifact.artifact_type == artifact_type
                and artifact.renderer_version == self._renderer.version
                and artifact.publication_id == (publication.id if publication is not None else None)
            ),
            None,
        )
        if existing is not None:
            return existing
        payload = self._renderer.render(
            document,
            artifact_type,
            presentation_context=(
                publication.presentation_context if publication is not None else None
            ),
        )
        storage_uri = await self._object_store.put(analysis.analysis_id, payload)
        return await self._repository.record_artifact(
            analysis,
            payload,
            storage_uri,
            publication=publication,
        )

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
