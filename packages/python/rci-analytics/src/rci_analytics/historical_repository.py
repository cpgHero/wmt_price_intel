"""Postgres persistence for live and historical analysis input sets."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from rci_analytics.historical import (
    HistoricalImportRecord,
    PreparedHistoricalImport,
    StoredHistoricalArtifact,
    canonical_json,
)

DEFAULT_ORGANIZATION_ID = "00000000-0000-0000-0000-000000000001"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


class PostgresAnalysisInputRepository:
    def __init__(
        self,
        engine: AsyncEngine,
        *,
        organization_id: str = DEFAULT_ORGANIZATION_ID,
    ) -> None:
        self._engine = engine
        self._organization_id = organization_id

    async def register(
        self,
        prepared: PreparedHistoricalImport,
        stored_artifacts: tuple[StoredHistoricalArtifact, ...],
        *,
        code_version: str,
        max_attempts: int,
    ) -> HistoricalImportRecord:
        if len(stored_artifacts) != len(prepared.artifacts):
            raise ValueError("stored artifact count does not match historical manifest")
        if sum(value.row_count for value in stored_artifacts) != prepared.total_rows:
            raise ValueError("stored artifact rows do not match historical manifest")
        async with self._engine.begin() as connection:
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"historical-input:{prepared.manifest.stable_key}"},
            )
            existing = await self._existing_historical(connection, prepared)
            if existing is not None:
                return existing
            definition_version_id = await self._definition_version(connection, prepared)
            run_id = str(
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO collection_run (
                              organization_id, definition_version_id, status,
                              estimated_pages, estimated_credits,
                              actual_success_pages, actual_credits,
                              trigger_type, completed_at,
                              availability_gate_status, availability_gate_config
                            ) VALUES (
                              CAST(:organization_id AS uuid), CAST(:definition_version_id AS uuid),
                              'succeeded', 0, 0, 0, 0, 'historical_import', now(),
                              'skipped', '{}'::jsonb
                            )
                            RETURNING id::text
                            """
                        ),
                        {
                            "organization_id": self._organization_id,
                            "definition_version_id": definition_version_id,
                        },
                    )
                ).scalar_one()
            )
            input_set_id = str(
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO analysis_input_set (
                              organization_id, source_kind, stable_key, collection_run_id,
                              product_pack_id, product_pack_version, analysis_config,
                              manifest, manifest_checksum, total_rows, status, completed_at
                            ) VALUES (
                              CAST(:organization_id AS uuid), 'historical_import', :stable_key,
                              CAST(:collection_run_id AS uuid), :product_pack_id,
                              :product_pack_version, CAST(:analysis_config AS jsonb),
                              CAST(:manifest AS jsonb), :manifest_checksum, :total_rows,
                              'ready', now()
                            )
                            RETURNING id::text
                            """
                        ),
                        {
                            "organization_id": self._organization_id,
                            "stable_key": prepared.manifest.stable_key,
                            "collection_run_id": run_id,
                            "product_pack_id": prepared.manifest.product_pack_id,
                            "product_pack_version": prepared.manifest.product_pack_version,
                            "analysis_config": _json(prepared.manifest.analysis_config),
                            "manifest": _json(prepared.durable_manifest),
                            "manifest_checksum": prepared.manifest_checksum,
                            "total_rows": prepared.total_rows,
                        },
                    )
                ).scalar_one()
            )
            for artifact in sorted(stored_artifacts, key=lambda value: value.ordinal):
                await self._attach_historical_artifact(
                    connection,
                    input_set_id=input_set_id,
                    collection_run_id=run_id,
                    artifact=artifact,
                    manifest_checksum=prepared.manifest_checksum,
                )
            analysis_run_id = str(
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO analysis_run (
                              collection_run_id, input_set_id, product_pack_id,
                              product_pack_version, status, code_version, max_attempts
                            ) VALUES (
                              CAST(:collection_run_id AS uuid), CAST(:input_set_id AS uuid),
                              :product_pack_id, :product_pack_version, 'queued',
                              :code_version, :max_attempts
                            )
                            RETURNING id::text
                            """
                        ),
                        {
                            "collection_run_id": run_id,
                            "input_set_id": input_set_id,
                            "product_pack_id": prepared.manifest.product_pack_id,
                            "product_pack_version": prepared.manifest.product_pack_version,
                            "code_version": code_version,
                            "max_attempts": max_attempts,
                        },
                    )
                ).scalar_one()
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO audit_event (
                      organization_id, event_type, entity_type, entity_id, details
                    ) VALUES (
                      CAST(:organization_id AS uuid), 'historical_input_imported',
                      'analysis_input_set', :input_set_id, CAST(:details AS jsonb)
                    )
                    """
                ),
                {
                    "organization_id": self._organization_id,
                    "input_set_id": input_set_id,
                    "details": _json(
                        {
                            "manifest_checksum": prepared.manifest_checksum,
                            "collection_run_id": run_id,
                            "analysis_run_id": analysis_run_id,
                            "total_rows": prepared.total_rows,
                        }
                    ),
                },
            )
            return HistoricalImportRecord(
                input_set_id=input_set_id,
                collection_run_id=run_id,
                analysis_run_id=analysis_run_id,
                manifest_checksum=prepared.manifest_checksum,
                total_rows=prepared.total_rows,
                created=True,
            )

    async def _existing_historical(
        self,
        connection: AsyncConnection,
        prepared: PreparedHistoricalImport,
    ) -> HistoricalImportRecord | None:
        row = (
            (
                await connection.execute(
                    text(
                        """
                        SELECT i.id::text AS input_set_id,
                               i.collection_run_id::text AS collection_run_id,
                               ar.id::text AS analysis_run_id,
                               i.manifest_checksum, i.total_rows
                        FROM analysis_input_set i
                        JOIN analysis_run ar
                          ON ar.input_set_id = i.id
                         AND ar.product_pack_id = i.product_pack_id
                         AND ar.product_pack_version = i.product_pack_version
                        WHERE i.organization_id::text = :organization_id
                          AND i.source_kind = 'historical_import'
                          AND i.manifest_checksum = :manifest_checksum
                        """
                    ),
                    {
                        "organization_id": self._organization_id,
                        "manifest_checksum": prepared.manifest_checksum,
                    },
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        return HistoricalImportRecord(
            input_set_id=str(row["input_set_id"]),
            collection_run_id=str(row["collection_run_id"]),
            analysis_run_id=str(row["analysis_run_id"]),
            manifest_checksum=str(row["manifest_checksum"]),
            total_rows=int(row["total_rows"]),
            created=False,
        )

    async def _definition_version(
        self,
        connection: AsyncConnection,
        prepared: PreparedHistoricalImport,
    ) -> str:
        definition_id = str(
            (
                await connection.execute(
                    text(
                        """
                        INSERT INTO collection_definition (
                          organization_id, stable_key, name, active
                        ) VALUES (
                          CAST(:organization_id AS uuid), :stable_key, :name, false
                        )
                        ON CONFLICT (organization_id, stable_key) DO UPDATE
                        SET name = EXCLUDED.name
                        RETURNING id::text
                        """
                    ),
                    {
                        "organization_id": self._organization_id,
                        "stable_key": f"historical:{prepared.manifest.stable_key}",
                        "name": prepared.manifest.name,
                    },
                )
            ).scalar_one()
        )
        definition_checksum = hashlib.sha256(
            canonical_json(prepared.manifest.analysis_config).encode()
        ).hexdigest()
        existing = (
            await connection.execute(
                text(
                    """
                    SELECT id::text
                    FROM collection_definition_version
                    WHERE definition_id::text = :definition_id AND checksum = :checksum
                    """
                ),
                {"definition_id": definition_id, "checksum": definition_checksum},
            )
        ).scalar_one_or_none()
        if existing is not None:
            return str(existing)
        return str(
            (
                await connection.execute(
                    text(
                        """
                        INSERT INTO collection_definition_version (
                          definition_id, version, config, checksum
                        )
                        SELECT CAST(:definition_id AS uuid),
                               COALESCE(max(version), 0) + 1,
                               CAST(:config AS jsonb), :checksum
                        FROM collection_definition_version
                        WHERE definition_id = CAST(:definition_id AS uuid)
                        RETURNING id::text
                        """
                    ),
                    {
                        "definition_id": definition_id,
                        "config": _json(prepared.manifest.analysis_config),
                        "checksum": definition_checksum,
                    },
                )
            ).scalar_one()
        )

    @staticmethod
    async def _attach_historical_artifact(
        connection: AsyncConnection,
        *,
        input_set_id: str,
        collection_run_id: str,
        artifact: StoredHistoricalArtifact,
        manifest_checksum: str,
    ) -> None:
        artifact_id = (
            await connection.execute(
                text(
                    """
                    INSERT INTO dataset_artifact (
                      collection_run_id, artifact_type, storage_uri, content_type,
                      row_count, byte_size, checksum, schema_version, metadata
                    ) VALUES (
                      CAST(:collection_run_id AS uuid), 'raw_historical_csv', :storage_uri,
                      :content_type, :row_count, :byte_size, :checksum, '1.0.0',
                      CAST(:metadata AS jsonb)
                    )
                    ON CONFLICT (storage_uri) DO UPDATE
                    SET storage_uri = EXCLUDED.storage_uri
                    WHERE dataset_artifact.checksum = EXCLUDED.checksum
                    RETURNING id::text
                    """
                ),
                {
                    "collection_run_id": collection_run_id,
                    "storage_uri": artifact.storage_uri,
                    "content_type": artifact.content_type,
                    "row_count": artifact.row_count,
                    "byte_size": artifact.byte_size,
                    "checksum": artifact.checksum,
                    "metadata": _json(
                        {
                            "source_kind": "historical_import",
                            "source_name": artifact.source_name,
                            "source_format": artifact.source_format,
                            "retailer_id": artifact.retailer_id,
                            "adapter_id": artifact.adapter_id,
                            "manifest_checksum": manifest_checksum,
                            "columns": list(artifact.columns),
                            "immutable": True,
                        }
                    ),
                },
            )
        ).scalar_one_or_none()
        if artifact_id is None:
            raise ValueError(f"dataset artifact {artifact.storage_uri!r} is immutable")
        await connection.execute(
            text(
                """
                INSERT INTO analysis_input_artifact (
                  input_set_id, dataset_artifact_id, ordinal, retailer_id,
                  adapter_id, source_name, source_format, row_count, checksum, metadata
                ) VALUES (
                  CAST(:input_set_id AS uuid), CAST(:dataset_artifact_id AS uuid), :ordinal,
                  :retailer_id, :adapter_id, :source_name, :source_format,
                  :row_count, :checksum, CAST(:metadata AS jsonb)
                )
                """
            ),
            {
                "input_set_id": input_set_id,
                "dataset_artifact_id": artifact_id,
                "ordinal": artifact.ordinal,
                "retailer_id": artifact.retailer_id,
                "adapter_id": artifact.adapter_id,
                "source_name": artifact.source_name,
                "source_format": artifact.source_format,
                "row_count": artifact.row_count,
                "checksum": artifact.checksum,
                "metadata": _json({"columns": list(artifact.columns)}),
            },
        )

    async def materialize_live(
        self,
        *,
        code_version: str,
        max_attempts: int,
    ) -> int:
        """Wrap completed provider collections in immutable input sets and queue analysis."""

        async with self._engine.begin() as connection:
            candidates = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT r.id::text AS collection_run_id, r.organization_id::text,
                                   v.id::text AS definition_version_id,
                                   v.checksum AS definition_checksum, v.config,
                                   v.config->'product_pack'->>'id' AS product_pack_id,
                                   v.config->'product_pack'->>'version' AS product_pack_version,
                                   count(*) AS artifact_count,
                                   COALESCE(sum(t.result_count), 0) AS total_rows,
                                   encode(digest(string_agg(
                                     da.checksum, '|' ORDER BY
                                     t.retailer_id, t.location_scope_key, t.page_number, t.id
                                   ), 'sha256'), 'hex') AS artifact_chain_checksum
                            FROM collection_run r
                            JOIN collection_definition_version v ON v.id = r.definition_version_id
                            JOIN collection_task t ON t.collection_run_id = r.id
                            JOIN dataset_artifact da ON da.id = t.raw_artifact_id
                            LEFT JOIN analysis_input_set existing
                              ON existing.collection_run_id = r.id
                            WHERE r.status IN ('succeeded', 'completed_with_warnings')
                              AND t.status = 'succeeded'
                              AND t.http_status BETWEEN 200 AND 299
                              AND v.config->'product_pack'->>'id' IS NOT NULL
                              AND v.config->'product_pack'->>'version' IS NOT NULL
                              AND existing.id IS NULL
                            GROUP BY r.id, r.organization_id, v.id, v.checksum, v.config
                            ORDER BY r.created_at, r.id
                            """
                        )
                    )
                )
                .mappings()
                .all()
            )
            for candidate in candidates:
                manifest = {
                    "schema_version": "1.0.0",
                    "kind": "live_collection",
                    "collection_run_id": str(candidate["collection_run_id"]),
                    "collection_definition_version_id": str(candidate["definition_version_id"]),
                    "collection_definition_checksum": str(candidate["definition_checksum"]),
                    "artifact_count": int(candidate["artifact_count"]),
                    "artifact_chain_checksum": str(candidate["artifact_chain_checksum"]),
                    "total_rows": int(candidate["total_rows"]),
                }
                manifest_checksum = hashlib.sha256(canonical_json(manifest).encode()).hexdigest()
                input_set_id = str(
                    (
                        await connection.execute(
                            text(
                                """
                                INSERT INTO analysis_input_set (
                                  organization_id, source_kind, stable_key, collection_run_id,
                                  product_pack_id, product_pack_version, analysis_config,
                                  manifest, manifest_checksum, total_rows, status, completed_at
                                ) VALUES (
                                  CAST(:organization_id AS uuid), 'live_collection', :stable_key,
                                  CAST(:collection_run_id AS uuid), :product_pack_id,
                                  :product_pack_version, CAST(:analysis_config AS jsonb),
                                  CAST(:manifest AS jsonb), :manifest_checksum, :total_rows,
                                  'ready', now()
                                )
                                RETURNING id::text
                                """
                            ),
                            {
                                "organization_id": str(candidate["organization_id"]),
                                "stable_key": f"collection-{candidate['collection_run_id']}",
                                "collection_run_id": str(candidate["collection_run_id"]),
                                "product_pack_id": str(candidate["product_pack_id"]),
                                "product_pack_version": str(candidate["product_pack_version"]),
                                "analysis_config": _json(dict(candidate["config"])),
                                "manifest": _json(manifest),
                                "manifest_checksum": manifest_checksum,
                                "total_rows": int(candidate["total_rows"]),
                            },
                        )
                    ).scalar_one()
                )
                await connection.execute(
                    text(
                        """
                        INSERT INTO analysis_input_artifact (
                          input_set_id, dataset_artifact_id, ordinal, retailer_id,
                          adapter_id, source_name, source_format, row_count, checksum, metadata
                        )
                        SELECT CAST(:input_set_id AS uuid), source.dataset_artifact_id,
                               source.ordinal, source.retailer_id, source.adapter_id,
                               source.source_name, 'metricscart_provider_json',
                               source.result_count, source.checksum,
                               jsonb_build_object(
                                 'task_id', source.task_id,
                                 'page_number', source.page_number,
                                 'location_scope_key', source.location_scope_key
                               )
                        FROM (
                          SELECT da.id AS dataset_artifact_id,
                                 row_number() OVER (
                                   ORDER BY t.retailer_id, t.location_scope_key,
                                            t.page_number, t.id
                                 ) - 1 AS ordinal,
                                 t.retailer_id, t.adapter_id,
                                 'task-' || t.id::text || '.json.gz' AS source_name,
                                 t.result_count, da.checksum, t.id::text AS task_id,
                                 t.page_number, t.location_scope_key
                          FROM collection_task t
                          JOIN dataset_artifact da ON da.id = t.raw_artifact_id
                          WHERE t.collection_run_id::text = :collection_run_id
                            AND t.status = 'succeeded'
                            AND t.http_status BETWEEN 200 AND 299
                        ) source
                        ORDER BY source.ordinal
                        """
                    ),
                    {
                        "input_set_id": input_set_id,
                        "collection_run_id": str(candidate["collection_run_id"]),
                    },
                )
                await connection.execute(
                    text(
                        """
                        UPDATE analysis_run
                        SET input_set_id = CAST(:input_set_id AS uuid)
                        WHERE collection_run_id::text = :collection_run_id
                          AND product_pack_id = :product_pack_id
                          AND product_pack_version = :product_pack_version
                          AND input_set_id IS NULL
                        """
                    ),
                    {
                        "input_set_id": input_set_id,
                        "collection_run_id": str(candidate["collection_run_id"]),
                        "product_pack_id": str(candidate["product_pack_id"]),
                        "product_pack_version": str(candidate["product_pack_version"]),
                    },
                )
            inserted = await connection.execute(
                text(
                    """
                    INSERT INTO analysis_run (
                      collection_run_id, input_set_id, product_pack_id, product_pack_version,
                      status, code_version, max_attempts
                    )
                    SELECT i.collection_run_id, i.id, i.product_pack_id,
                           i.product_pack_version, 'queued', :code_version, :max_attempts
                    FROM analysis_input_set i
                    WHERE i.source_kind = 'live_collection' AND i.status = 'ready'
                      AND NOT EXISTS (
                        SELECT 1 FROM analysis_run ar
                        WHERE ar.collection_run_id = i.collection_run_id
                          AND ar.product_pack_id = i.product_pack_id
                          AND ar.product_pack_version = i.product_pack_version
                      )
                    ON CONFLICT ON CONSTRAINT analysis_run_collection_pack_uq DO NOTHING
                    RETURNING id
                    """
                ),
                {"code_version": code_version, "max_attempts": max_attempts},
            )
            return len(inserted.all())
