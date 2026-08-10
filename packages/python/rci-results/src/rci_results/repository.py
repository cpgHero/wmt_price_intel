"""PostgreSQL persistence for immutable AnalysisResult and report metadata."""

from __future__ import annotations

import hashlib
import json
from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncEngine

from rci_results.models import (
    AnalysisPublicationRecord,
    AnalysisRecord,
    ArtifactPayload,
    ArtifactType,
    JsonObject,
    ReportArtifactRecord,
)

DEFAULT_ORGANIZATION_ID = "00000000-0000-0000-0000-000000000001"


def _json(value: JsonObject) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _analysis(row: RowMapping | dict[str, Any]) -> AnalysisRecord:
    return AnalysisRecord(
        id=str(row["id"]),
        analysis_run_id=str(row["analysis_run_id"]),
        analysis_id=str(row["analysis_id"]),
        collection_run_id=str(row["collection_run_id"]),
        status=str(row["status"]),
        product_pack_id=str(row["product_pack_id"]),
        product_pack_version=str(row["product_pack_version"]),
        schema_version=str(row["schema_version"]),
        checksum=str(row["checksum"]),
        result=dict(row["result"]),
        created_at=row["created_at"],
    )


def _artifact(row: RowMapping) -> ReportArtifactRecord:
    return ReportArtifactRecord(
        id=str(row["id"]),
        analysis_run_id=str(row["analysis_run_id"]),
        publication_id=(str(row["publication_id"]) if row["publication_id"] is not None else None),
        artifact_type=cast(ArtifactType, str(row["artifact_type"])),
        renderer_version=str(row["renderer_version"]),
        dataset_artifact_id=str(row["dataset_artifact_id"]),
        storage_uri=str(row["storage_uri"]),
        content_type=str(row["content_type"]),
        byte_size=int(row["byte_size"]),
        checksum=str(row["checksum"]),
        status=str(row["status"]),
        created_at=row["created_at"],
    )


def _publication(row: RowMapping) -> AnalysisPublicationRecord:
    return AnalysisPublicationRecord(
        id=str(row["id"]),
        analysis_result_id=str(row["analysis_result_id"]),
        analysis_id=str(row["analysis_id"]),
        version=int(row["version"]),
        status=str(row["status"]),
        source_result_checksum=str(row["source_result_checksum"]),
        publication_checksum=str(row["publication_checksum"]),
        result=dict(row["result"]),
        presentation_context=dict(row["presentation_context"]),
        created_at=row["created_at"],
    )


_ANALYSIS_SELECT = """
SELECT r.id::text AS id, r.analysis_run_id::text AS analysis_run_id,
       r.analysis_id, ar.collection_run_id::text AS collection_run_id,
       ar.status, ar.product_pack_id, ar.product_pack_version,
       r.schema_version, r.checksum, r.result, r.created_at
FROM analysis_result r
JOIN analysis_run ar ON ar.id = r.analysis_run_id
"""

_ARTIFACT_SELECT = """
SELECT ra.id::text AS id, ra.analysis_run_id::text AS analysis_run_id,
       ra.publication_id::text AS publication_id,
       ra.artifact_type, ra.renderer_version,
       ra.dataset_artifact_id::text AS dataset_artifact_id,
       da.storage_uri, da.content_type, da.byte_size, da.checksum,
       ra.status, ra.created_at
FROM report_artifact ra
JOIN dataset_artifact da ON da.id = ra.dataset_artifact_id
"""

_PUBLICATION_SELECT = """
SELECT p.id::text AS id, p.analysis_result_id::text AS analysis_result_id,
       r.analysis_id, p.version, p.status, p.source_result_checksum,
       p.publication_checksum, p.result, p.presentation_context, p.created_at
FROM analysis_publication p
JOIN analysis_result r ON r.id = p.analysis_result_id
"""


class PostgresResultsRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def publish(
        self,
        result: JsonObject,
        checksum: str,
        *,
        collection_run_id: str,
    ) -> AnalysisRecord:
        analysis_id = str(result["analysis_id"])
        embedded_analysis_run_id = result.get("analysis_run_id")
        product_pack = result["product_pack"]
        assert isinstance(product_pack, dict)
        async with self._engine.begin() as connection:
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:analysis_id, 0))"),
                {"analysis_id": analysis_id},
            )
            existing = (
                (
                    await connection.execute(
                        text(f"{_ANALYSIS_SELECT} WHERE r.analysis_id = :analysis_id"),
                        {"analysis_id": analysis_id},
                    )
                )
                .mappings()
                .first()
            )
            if existing is not None:
                record = _analysis(existing)
                if record.checksum != checksum:
                    raise ValueError(f"AnalysisResult {analysis_id!r} is immutable")
                return record
            source_where = (
                "WHERE ar.id::text = :analysis_run_id"
                if embedded_analysis_run_id is not None
                else (
                    "WHERE ar.collection_run_id::text = :collection_run_id "
                    "AND ar.product_pack_id = :product_pack_id "
                    "AND ar.product_pack_version = :product_pack_version"
                )
            )
            source_parameters = (
                {"analysis_run_id": str(embedded_analysis_run_id)}
                if embedded_analysis_run_id is not None
                else {
                    "collection_run_id": collection_run_id,
                    "product_pack_id": str(product_pack["id"]),
                    "product_pack_version": str(product_pack["version"]),
                }
            )
            source_existing = (
                (
                    await connection.execute(
                        text(f"{_ANALYSIS_SELECT} {source_where}"),
                        source_parameters,
                    )
                )
                .mappings()
                .first()
            )
            if source_existing is not None:
                record = _analysis(source_existing)
                if record.checksum != checksum:
                    raise ValueError("AnalysisResult collection run and Product Pack are immutable")
                return record
            pending_run = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT id::text, collection_run_id::text AS collection_run_id,
                              product_pack_id, product_pack_version
                            FROM analysis_run WHERE id::text = :analysis_run_id
                            FOR UPDATE
                            """
                        ),
                        {"analysis_run_id": str(embedded_analysis_run_id)},
                    )
                )
                .mappings()
                .first()
                if embedded_analysis_run_id is not None
                else None
            )
            collection_exists = bool(
                (
                    await connection.execute(
                        text("SELECT 1 FROM collection_run WHERE id::text = :run_id"),
                        {"run_id": collection_run_id},
                    )
                ).scalar_one_or_none()
            )
            if not collection_exists:
                raise LookupError(f"collection run {collection_run_id!r} does not exist")
            if pending_run is not None:
                if (
                    str(pending_run["collection_run_id"]) != collection_run_id
                    or str(pending_run["product_pack_id"]) != str(product_pack["id"])
                    or str(pending_run["product_pack_version"]) != str(product_pack["version"])
                ):
                    raise ValueError("embedded analysis run does not match the result source")
                analysis_run_id = str(pending_run["id"])
                await connection.execute(
                    text(
                        """
                        UPDATE analysis_run SET status = 'succeeded',
                          code_version = :code_version,
                          started_at = COALESCE(started_at, CAST(:generated_at AS timestamptz)),
                          completed_at = CAST(:generated_at AS timestamptz),
                          locked_by = NULL, locked_at = NULL, lease_expires_at = NULL,
                          last_error = NULL
                        WHERE id::text = :analysis_run_id
                        """
                    ),
                    {
                        "analysis_run_id": analysis_run_id,
                        "code_version": str(
                            result.get("provenance", {}).get("analytics_code_version", "")
                        ),
                        "generated_at": str(result["generated_at"]),
                    },
                )
            else:
                analysis_run_id = str(
                    (
                        await connection.execute(
                            text(
                                """
                            INSERT INTO analysis_run (
                              collection_run_id, product_pack_id, product_pack_version,
                              status, code_version, started_at, completed_at
                            ) VALUES (
                              CAST(:collection_run_id AS uuid), :product_pack_id,
                              :product_pack_version, 'succeeded', :code_version,
                              CAST(:generated_at AS timestamptz), CAST(:generated_at AS timestamptz)
                            )
                            ON CONFLICT ON CONSTRAINT
                              analysis_run_collection_pack_match_revision_uq
                            DO UPDATE SET status = 'succeeded',
                              code_version = EXCLUDED.code_version,
                              started_at = COALESCE(analysis_run.started_at, EXCLUDED.started_at),
                              completed_at = EXCLUDED.completed_at,
                              locked_by = NULL, locked_at = NULL, lease_expires_at = NULL,
                              last_error = NULL
                            RETURNING id::text
                            """
                            ),
                            {
                                "collection_run_id": collection_run_id,
                                "product_pack_id": str(product_pack["id"]),
                                "product_pack_version": str(product_pack["version"]),
                                "code_version": str(
                                    result.get("provenance", {}).get("analytics_code_version", "")
                                ),
                                "generated_at": str(result["generated_at"]),
                            },
                        )
                    ).scalar_one()
                )
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO analysis_result (
                              analysis_run_id, analysis_id, schema_version, result, checksum
                            ) VALUES (
                              CAST(:analysis_run_id AS uuid), :analysis_id, :schema_version,
                              CAST(:result AS jsonb), :checksum
                            )
                            RETURNING id::text AS id, analysis_run_id::text AS analysis_run_id,
                              analysis_id, schema_version, checksum, result, created_at
                            """
                        ),
                        {
                            "analysis_run_id": analysis_run_id,
                            "analysis_id": analysis_id,
                            "schema_version": str(result["schema_version"]),
                            "result": _json(result),
                            "checksum": checksum,
                        },
                    )
                )
                .mappings()
                .one()
            )
            combined = dict(row)
            combined.update(
                {
                    "collection_run_id": collection_run_id,
                    "status": "succeeded",
                    "product_pack_id": str(product_pack["id"]),
                    "product_pack_version": str(product_pack["version"]),
                }
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO audit_event (
                      organization_id, event_type, entity_type, entity_id, details
                    ) VALUES (
                      CAST(:organization_id AS uuid), 'analysis_result_published',
                      'analysis_result', :entity_id, CAST(:details AS jsonb)
                    )
                    """
                ),
                {
                    "organization_id": DEFAULT_ORGANIZATION_ID,
                    "entity_id": analysis_id,
                    "details": _json({"checksum": checksum}),
                },
            )
            return _analysis(combined)

    async def list_analyses(self, limit: int = 50) -> list[AnalysisRecord]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        f"{_ANALYSIS_SELECT} WHERE r.archived_at IS NULL "
                        "ORDER BY r.created_at DESC LIMIT :limit"
                    ),
                    {"limit": limit},
                )
            ).mappings()
            return [_analysis(row) for row in rows]

    async def get(self, identifier: str) -> AnalysisRecord | None:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            f"{_ANALYSIS_SELECT} "
                            "WHERE r.analysis_id = :identifier OR r.id::text = :identifier"
                        ),
                        {"identifier": identifier},
                    )
                )
                .mappings()
                .first()
            )
            return _analysis(row) if row is not None else None

    async def get_by_collection_run(self, run_id: str) -> AnalysisRecord | None:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            f"{_ANALYSIS_SELECT} "
                            "WHERE ar.collection_run_id::text = :run_id "
                            "ORDER BY r.created_at DESC LIMIT 1"
                        ),
                        {"run_id": run_id},
                    )
                )
                .mappings()
                .first()
            )
            return _analysis(row) if row is not None else None

    async def publish_publication(
        self,
        analysis: AnalysisRecord,
        result: JsonObject,
        publication_checksum: str,
        *,
        presentation_context: JsonObject,
    ) -> AnalysisPublicationRecord:
        async with self._engine.begin() as connection:
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:record_id, 0))"),
                {"record_id": analysis.id},
            )
            source_checksum = (
                await connection.execute(
                    text("SELECT checksum FROM analysis_result WHERE id::text = :record_id"),
                    {"record_id": analysis.id},
                )
            ).scalar_one_or_none()
            if source_checksum is None:
                raise LookupError(f"analysis {analysis.analysis_id!r} was not found")
            if str(source_checksum) != analysis.checksum:
                raise ValueError("AnalysisResult changed while publishing")
            existing = (
                (
                    await connection.execute(
                        text(
                            f"{_PUBLICATION_SELECT} "
                            "WHERE p.analysis_result_id::text = :record_id "
                            "AND p.publication_checksum = :checksum"
                        ),
                        {"record_id": analysis.id, "checksum": publication_checksum},
                    )
                )
                .mappings()
                .first()
            )
            if existing is not None:
                return _publication(existing)
            version = int(
                (
                    await connection.execute(
                        text(
                            "SELECT COALESCE(MAX(version), 0) + 1 "
                            "FROM analysis_publication "
                            "WHERE analysis_result_id::text = :record_id"
                        ),
                        {"record_id": analysis.id},
                    )
                ).scalar_one()
            )
            await connection.execute(
                text(
                    "UPDATE analysis_publication SET status = 'superseded' "
                    "WHERE analysis_result_id::text = :record_id "
                    "AND status = 'ready_to_share'"
                ),
                {"record_id": analysis.id},
            )
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            WITH inserted AS (
                              INSERT INTO analysis_publication (
                                analysis_result_id, version, status,
                                source_result_checksum, publication_checksum,
                                result, presentation_context
                              ) VALUES (
                                CAST(:record_id AS uuid), :version, 'ready_to_share',
                                :source_checksum, :publication_checksum,
                                CAST(:result AS jsonb), CAST(:presentation_context AS jsonb)
                              ) RETURNING *
                            )
                            SELECT p.id::text AS id,
                              p.analysis_result_id::text AS analysis_result_id,
                              :analysis_id AS analysis_id, p.version, p.status,
                              p.source_result_checksum, p.publication_checksum,
                              p.result, p.presentation_context, p.created_at
                            FROM inserted p
                            """
                        ),
                        {
                            "record_id": analysis.id,
                            "analysis_id": analysis.analysis_id,
                            "version": version,
                            "source_checksum": analysis.checksum,
                            "publication_checksum": publication_checksum,
                            "result": _json(result),
                            "presentation_context": _json(presentation_context),
                        },
                    )
                )
                .mappings()
                .one()
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO audit_event (
                      organization_id, event_type, entity_type, entity_id, details
                    ) VALUES (
                      CAST(:organization_id AS uuid), 'analysis_publication_created',
                      'analysis_publication', :entity_id, CAST(:details AS jsonb)
                    )
                    """
                ),
                {
                    "organization_id": DEFAULT_ORGANIZATION_ID,
                    "entity_id": str(row["id"]),
                    "details": _json(
                        {
                            "analysis_id": analysis.analysis_id,
                            "version": version,
                            "source_result_checksum": analysis.checksum,
                            "publication_checksum": publication_checksum,
                        }
                    ),
                },
            )
            return _publication(row)

    async def latest_publication(self, analysis_id: str) -> AnalysisPublicationRecord | None:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            f"{_PUBLICATION_SELECT} WHERE r.analysis_id = :analysis_id "
                            "ORDER BY p.version DESC LIMIT 1"
                        ),
                        {"analysis_id": analysis_id},
                    )
                )
                .mappings()
                .first()
            )
            return _publication(row) if row is not None else None

    async def record_artifact(
        self,
        analysis: AnalysisRecord,
        payload: ArtifactPayload,
        storage_uri: str,
        *,
        publication: AnalysisPublicationRecord | None = None,
    ) -> ReportArtifactRecord:
        checksum = hashlib.sha256(payload.body).hexdigest()
        async with self._engine.begin() as connection:
            dataset_id = (
                await connection.execute(
                    text(
                        """
                        INSERT INTO dataset_artifact (
                          collection_run_id, artifact_type, storage_uri, content_type,
                          row_count, byte_size, checksum, schema_version, metadata
                        ) VALUES (
                          CAST(:collection_run_id AS uuid), :artifact_type, :storage_uri,
                          :content_type, NULL, :byte_size, :checksum, :schema_version,
                          CAST(:metadata AS jsonb)
                        )
                        ON CONFLICT (storage_uri) DO UPDATE
                        SET storage_uri = EXCLUDED.storage_uri
                        WHERE dataset_artifact.checksum = EXCLUDED.checksum
                        RETURNING id::text
                        """
                    ),
                    {
                        "collection_run_id": analysis.collection_run_id,
                        "artifact_type": f"report_{payload.artifact_type}",
                        "storage_uri": storage_uri,
                        "content_type": payload.content_type,
                        "byte_size": len(payload.body),
                        "checksum": checksum,
                        "schema_version": analysis.schema_version,
                        "metadata": _json(
                            {
                                "analysis_id": analysis.analysis_id,
                                "filename": payload.filename,
                                "renderer_version": payload.renderer_version,
                                "publication_id": (
                                    publication.id if publication is not None else None
                                ),
                                "publication_version": (
                                    publication.version if publication is not None else None
                                ),
                            }
                        ),
                    },
                )
            ).scalar_one_or_none()
            if dataset_id is None:
                raise ValueError(f"report artifact {storage_uri!r} is immutable")
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            WITH inserted AS (
                              INSERT INTO report_artifact (
                                analysis_run_id, artifact_type, renderer_version,
                                dataset_artifact_id, publication_id, status
                              ) VALUES (
                                CAST(:analysis_run_id AS uuid), :artifact_type, :renderer_version,
                                CAST(:dataset_id AS uuid), CAST(:publication_id AS uuid), 'ready'
                              )
                              ON CONFLICT DO NOTHING
                              RETURNING *
                            ), selected AS (
                              SELECT * FROM inserted
                              UNION ALL
                              SELECT * FROM report_artifact
                              WHERE analysis_run_id = CAST(:analysis_run_id AS uuid)
                                AND artifact_type = :artifact_type
                                AND renderer_version = :renderer_version
                                AND publication_id IS NOT DISTINCT FROM
                                  CAST(:publication_id AS uuid)
                              LIMIT 1
                            )
                            SELECT i.id::text AS id, i.analysis_run_id::text AS analysis_run_id,
                              i.publication_id::text AS publication_id,
                              i.artifact_type, i.renderer_version,
                              i.dataset_artifact_id::text AS dataset_artifact_id,
                              da.storage_uri, da.content_type, da.byte_size, da.checksum,
                              i.status, i.created_at
                            FROM selected i
                            JOIN dataset_artifact da ON da.id = i.dataset_artifact_id
                            """
                        ),
                        {
                            "analysis_run_id": analysis.analysis_run_id,
                            "artifact_type": payload.artifact_type,
                            "renderer_version": payload.renderer_version,
                            "dataset_id": dataset_id,
                            "publication_id": (publication.id if publication is not None else None),
                        },
                    )
                )
                .mappings()
                .one()
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO audit_event (
                      organization_id, event_type, entity_type, entity_id, details
                    ) VALUES (
                      CAST(:organization_id AS uuid), 'report_artifact_generated',
                      'analysis_result', :entity_id, CAST(:details AS jsonb)
                    )
                    """
                ),
                {
                    "organization_id": DEFAULT_ORGANIZATION_ID,
                    "entity_id": analysis.analysis_id,
                    "details": _json(
                        {
                            "artifact_type": payload.artifact_type,
                            "renderer_version": payload.renderer_version,
                            "checksum": checksum,
                            "publication_id": (publication.id if publication is not None else None),
                        }
                    ),
                },
            )
            return _artifact(row)

    async def list_artifacts(self, analysis_id: str) -> list[ReportArtifactRecord]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        f"{_ARTIFACT_SELECT} "
                        "JOIN analysis_run ar ON ar.id = ra.analysis_run_id "
                        "JOIN analysis_result r ON r.analysis_run_id = ar.id "
                        "WHERE r.analysis_id = :analysis_id ORDER BY ra.created_at DESC"
                    ),
                    {"analysis_id": analysis_id},
                )
            ).mappings()
            return [_artifact(row) for row in rows]

    async def get_artifact(self, artifact_id: str) -> ReportArtifactRecord | None:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(f"{_ARTIFACT_SELECT} WHERE ra.id::text = :artifact_id"),
                        {"artifact_id": artifact_id},
                    )
                )
                .mappings()
                .first()
            )
            return _artifact(row) if row is not None else None
