"""Concurrency-safe in-memory result repository for tests and local composition."""

from __future__ import annotations

import asyncio
import copy
import hashlib
from datetime import UTC, datetime
from uuid import uuid4

from rci_results.models import (
    AnalysisRecord,
    ArtifactPayload,
    JsonObject,
    ReportArtifactRecord,
)


class InMemoryResultsRepository:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._analyses: dict[str, AnalysisRecord] = {}
        self._analysis_ids_by_record: dict[str, str] = {}
        self._artifacts: dict[str, ReportArtifactRecord] = {}

    async def publish(
        self,
        result: JsonObject,
        checksum: str,
        *,
        collection_run_id: str,
    ) -> AnalysisRecord:
        analysis_id = str(result["analysis_id"])
        async with self._lock:
            existing = self._analyses.get(analysis_id)
            if existing is not None:
                if existing.checksum != checksum:
                    raise ValueError(f"AnalysisResult {analysis_id!r} is immutable")
                return copy.deepcopy(existing)
            product_pack = result["product_pack"]
            assert isinstance(product_pack, dict)
            source_existing = next(
                (
                    record
                    for record in self._analyses.values()
                    if record.collection_run_id == collection_run_id
                    and record.product_pack_id == str(product_pack["id"])
                    and record.product_pack_version == str(product_pack["version"])
                ),
                None,
            )
            if source_existing is not None:
                if source_existing.checksum != checksum:
                    raise ValueError("AnalysisResult collection run and Product Pack are immutable")
                return copy.deepcopy(source_existing)
            record = AnalysisRecord(
                id=str(uuid4()),
                analysis_run_id=str(uuid4()),
                analysis_id=analysis_id,
                collection_run_id=collection_run_id,
                status="succeeded",
                product_pack_id=str(product_pack["id"]),
                product_pack_version=str(product_pack["version"]),
                schema_version=str(result["schema_version"]),
                checksum=checksum,
                result=result,
                created_at=datetime.now(UTC),
            )
            self._analyses[analysis_id] = record
            self._analysis_ids_by_record[record.id] = analysis_id
            return copy.deepcopy(record)

    async def list_analyses(self, limit: int = 50) -> list[AnalysisRecord]:
        async with self._lock:
            records = sorted(
                self._analyses.values(), key=lambda record: record.created_at, reverse=True
            )[:limit]
            return copy.deepcopy(records)

    async def get(self, identifier: str) -> AnalysisRecord | None:
        async with self._lock:
            analysis_id = self._analysis_ids_by_record.get(identifier, identifier)
            return copy.deepcopy(self._analyses.get(analysis_id))

    async def get_by_collection_run(self, run_id: str) -> AnalysisRecord | None:
        async with self._lock:
            matching = [
                record for record in self._analyses.values() if record.collection_run_id == run_id
            ]
            if not matching:
                return None
            return copy.deepcopy(max(matching, key=lambda record: record.created_at))

    async def record_artifact(
        self,
        analysis: AnalysisRecord,
        payload: ArtifactPayload,
        storage_uri: str,
    ) -> ReportArtifactRecord:
        checksum = hashlib.sha256(payload.body).hexdigest()
        async with self._lock:
            existing = next(
                (
                    artifact
                    for artifact in self._artifacts.values()
                    if artifact.storage_uri == storage_uri
                ),
                None,
            )
            if existing is not None:
                if existing.checksum != checksum:
                    raise ValueError(f"report artifact {storage_uri!r} is immutable")
                return existing
            record = ReportArtifactRecord(
                id=str(uuid4()),
                analysis_run_id=analysis.analysis_run_id,
                artifact_type=payload.artifact_type,
                renderer_version=payload.renderer_version,
                dataset_artifact_id=str(uuid4()),
                storage_uri=storage_uri,
                content_type=payload.content_type,
                byte_size=len(payload.body),
                checksum=checksum,
                status="ready",
                created_at=datetime.now(UTC),
            )
            self._artifacts[record.id] = record
            return record

    async def list_artifacts(self, analysis_id: str) -> list[ReportArtifactRecord]:
        analysis = await self.get(analysis_id)
        if analysis is None:
            return []
        async with self._lock:
            return sorted(
                (
                    artifact
                    for artifact in self._artifacts.values()
                    if artifact.analysis_run_id == analysis.analysis_run_id
                ),
                key=lambda artifact: artifact.created_at,
                reverse=True,
            )

    async def get_artifact(self, artifact_id: str) -> ReportArtifactRecord | None:
        async with self._lock:
            return self._artifacts.get(artifact_id)
