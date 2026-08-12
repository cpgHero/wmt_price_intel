"""Postgres persistence for governed Product Pack authoring."""

from __future__ import annotations

import hashlib
import json
from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from rci_product_packs.catalog import JsonObject, canonical_checksum
from rci_product_packs.models import (
    DraftStatus,
    ProductPackDraft,
    ProductPackEvidence,
    ProductPackPublication,
    ProductPackValidationRun,
    ValidationStatus,
    ValidationSuite,
)


class ProductPackDraftNotFoundError(LookupError):
    pass


class ProductPackDraftConflictError(RuntimeError):
    pass


class ProductPackPublicationError(RuntimeError):
    pass


def _json(document: object) -> str:
    return json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def draft_checksum(config: JsonObject, report_blueprint: JsonObject) -> str:
    return canonical_checksum({"config": config, "report_blueprint": report_blueprint})


def _draft(row: RowMapping) -> ProductPackDraft:
    return ProductPackDraft(
        id=str(row["id"]),
        product_pack_id=str(row["product_pack_id"]),
        base_version=str(row["base_version"]) if row["base_version"] is not None else None,
        proposed_version=str(row["proposed_version"]),
        status=cast(DraftStatus, str(row["status"])),
        revision=int(row["revision"]),
        config=dict(row["config"]),
        report_blueprint=dict(row["report_blueprint"]),
        checksum=str(row["checksum"]),
        created_by=str(row["created_by"]),
        updated_by=str(row["updated_by"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _validation(row: RowMapping) -> ProductPackValidationRun:
    return ProductPackValidationRun(
        id=str(row["id"]),
        draft_id=str(row["draft_id"]),
        draft_revision=int(row["draft_revision"]),
        draft_checksum=str(row["draft_checksum"]),
        suite=cast(ValidationSuite, str(row["suite"])),
        status=cast(ValidationStatus, str(row["status"])),
        gates=tuple(dict(item) for item in row["gates"]),
        engine_version=str(row["engine_version"]) if row["engine_version"] is not None else None,
        attempt_count=int(row["attempt_count"]),
        max_attempts=int(row["max_attempts"]),
        locked_by=str(row["locked_by"]) if row["locked_by"] is not None else None,
        lease_expires_at=row["lease_expires_at"],
        last_error=str(row["last_error"]) if row["last_error"] is not None else None,
        cancel_requested_at=row["cancel_requested_at"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        created_at=row["created_at"],
    )


def _evidence(row: RowMapping) -> ProductPackEvidence:
    return ProductPackEvidence(
        id=str(row["id"]),
        draft_id=str(row["draft_id"]),
        kind=str(row["kind"]),
        label=str(row["label"]),
        storage_uri=str(row["storage_uri"]),
        content_type=str(row["content_type"]),
        checksum=str(row["checksum"]),
        byte_size=int(row["byte_size"]),
        row_count=int(row["row_count"]) if row["row_count"] is not None else None,
        metadata=dict(row["metadata"]),
        created_by=str(row["created_by"]),
        created_at=row["created_at"],
    )


_DRAFT_SELECT = """
SELECT id::text AS id, product_pack_id, base_version, proposed_version, status,
  revision, config, report_blueprint, checksum, created_by, updated_by,
  created_at, updated_at
FROM product_pack_draft
"""

_DRAFT_COLUMNS = """
id::text AS id, product_pack_id, base_version, proposed_version, status,
revision, config, report_blueprint, checksum, created_by, updated_by,
created_at, updated_at
"""

_VALIDATION_COLUMNS = """
id::text AS id, draft_id::text AS draft_id, draft_revision, draft_checksum,
  suite, status, gates, engine_version, attempt_count, max_attempts, locked_by,
  lease_expires_at, last_error, cancel_requested_at, started_at, completed_at, created_at
"""

_VALIDATION_SELECT = f"""
SELECT {_VALIDATION_COLUMNS}
FROM product_pack_validation_run
"""

_EVIDENCE_SELECT = """
SELECT id::text AS id, draft_id::text AS draft_id, kind, label, storage_uri,
  content_type, checksum, byte_size, row_count, metadata, created_by, created_at
FROM product_pack_evidence_set
"""


class PostgresProductPackAuthoringRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def list_drafts(self) -> list[ProductPackDraft]:
        async with self._engine.connect() as connection:
            rows = (
                (await connection.execute(text(f"{_DRAFT_SELECT} ORDER BY updated_at DESC")))
                .mappings()
                .all()
            )
        return [_draft(row) for row in rows]

    async def get_draft(self, draft_id: str) -> ProductPackDraft:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(f"{_DRAFT_SELECT} WHERE id::text = :draft_id"),
                        {"draft_id": draft_id},
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            raise ProductPackDraftNotFoundError(f"Product Pack draft {draft_id!r} was not found")
        return _draft(row)

    async def find_draft(
        self,
        product_pack_id: str,
        proposed_version: str,
    ) -> ProductPackDraft | None:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            f"{_DRAFT_SELECT} WHERE product_pack_id = :product_pack_id "
                            "AND proposed_version = :proposed_version"
                        ),
                        {
                            "product_pack_id": product_pack_id,
                            "proposed_version": proposed_version,
                        },
                    )
                )
                .mappings()
                .first()
            )
        return _draft(row) if row is not None else None

    async def create_draft(
        self,
        *,
        product_pack_id: str,
        proposed_version: str,
        config: JsonObject,
        report_blueprint: JsonObject,
        actor: str,
        base_version: str | None = None,
    ) -> ProductPackDraft:
        checksum = draft_checksum(config, report_blueprint)
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO product_pack_draft (
                              product_pack_id, base_version, proposed_version, status,
                              revision, config, report_blueprint, checksum, created_by, updated_by
                            ) VALUES (
                              :product_pack_id, :base_version, :proposed_version, 'draft', 1,
                              CAST(:config AS jsonb), CAST(:report_blueprint AS jsonb),
                              :checksum, :actor, :actor
                            )
                            RETURNING id::text AS id, product_pack_id, base_version,
                              proposed_version, status, revision, config, report_blueprint,
                              checksum, created_by, updated_by, created_at, updated_at
                            """
                        ),
                        {
                            "product_pack_id": product_pack_id,
                            "base_version": base_version,
                            "proposed_version": proposed_version,
                            "config": _json(config),
                            "report_blueprint": _json(report_blueprint),
                            "checksum": checksum,
                            "actor": actor,
                        },
                    )
                )
                .mappings()
                .one()
            )
            await self._record_revision(
                connection,
                draft_id=str(row["id"]),
                revision=1,
                config=config,
                report_blueprint=report_blueprint,
                checksum=checksum,
                actor=actor,
                reason="Draft created",
            )
            await self._event(
                connection,
                str(row["id"]),
                "draft_created",
                actor,
                {"base_version": base_version, "proposed_version": proposed_version},
            )
        return _draft(row)

    async def update_draft(
        self,
        draft_id: str,
        *,
        expected_revision: int,
        config: JsonObject,
        report_blueprint: JsonObject,
        actor: str,
        reason: str | None = None,
    ) -> ProductPackDraft:
        checksum = draft_checksum(config, report_blueprint)
        async with self._engine.begin() as connection:
            current = (
                (
                    await connection.execute(
                        text(f"{_DRAFT_SELECT} WHERE id::text = :draft_id FOR UPDATE"),
                        {"draft_id": draft_id},
                    )
                )
                .mappings()
                .first()
            )
            if current is None:
                raise ProductPackDraftNotFoundError(
                    f"Product Pack draft {draft_id!r} was not found"
                )
            if int(current["revision"]) != expected_revision:
                raise ProductPackDraftConflictError(
                    f"Draft revision changed from {expected_revision} to {current['revision']}"
                )
            if str(current["status"]) in {"published", "abandoned"}:
                raise ProductPackDraftConflictError("Published or abandoned drafts are immutable")
            if str(current["checksum"]) == checksum:
                return _draft(current)
            revision = expected_revision + 1
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            UPDATE product_pack_draft SET revision = :revision,
                              status = 'draft', config = CAST(:config AS jsonb),
                              report_blueprint = CAST(:report_blueprint AS jsonb),
                              checksum = :checksum, updated_by = :actor, updated_at = now()
                            WHERE id::text = :draft_id
                            RETURNING id::text AS id, product_pack_id, base_version,
                              proposed_version, status, revision, config, report_blueprint,
                              checksum, created_by, updated_by, created_at, updated_at
                            """
                        ),
                        {
                            "draft_id": draft_id,
                            "revision": revision,
                            "config": _json(config),
                            "report_blueprint": _json(report_blueprint),
                            "checksum": checksum,
                            "actor": actor,
                        },
                    )
                )
                .mappings()
                .one()
            )
            await self._record_revision(
                connection,
                draft_id=draft_id,
                revision=revision,
                config=config,
                report_blueprint=report_blueprint,
                checksum=checksum,
                actor=actor,
                reason=reason,
            )
            await self._event(
                connection,
                draft_id,
                "draft_updated",
                actor,
                {"revision": revision, "reason": reason},
            )
        return _draft(row)

    async def abandon_draft(self, draft_id: str, *, actor: str, reason: str) -> ProductPackDraft:
        """Close a superseded mutable draft while preserving its complete audit history."""

        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            f"""
                            UPDATE product_pack_draft SET status = 'abandoned',
                              updated_by = :actor, updated_at = now()
                            WHERE id::text = :draft_id
                              AND status IN ('draft', 'candidate', 'certified')
                            RETURNING {_DRAFT_COLUMNS}
                            """
                        ),
                        {"draft_id": draft_id, "actor": actor},
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                existing = await connection.execute(
                    text(f"{_DRAFT_SELECT} WHERE id::text = :draft_id"),
                    {"draft_id": draft_id},
                )
                current = existing.mappings().first()
                if current is None:
                    raise ProductPackDraftNotFoundError(
                        f"Product Pack draft {draft_id!r} was not found"
                    )
                if str(current["status"]) == "published":
                    raise ProductPackDraftConflictError("Published drafts cannot be abandoned")
                return _draft(current)
            await self._event(
                connection,
                draft_id,
                "draft_abandoned",
                actor,
                {"reason": reason},
            )
        return _draft(row)

    async def list_evidence(self, draft_id: str) -> list[ProductPackEvidence]:
        await self.get_draft(draft_id)
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            f"{_EVIDENCE_SELECT} WHERE draft_id::text = :draft_id "
                            "ORDER BY created_at"
                        ),
                        {"draft_id": draft_id},
                    )
                )
                .mappings()
                .all()
            )
        return [_evidence(row) for row in rows]

    async def add_evidence(
        self,
        draft_id: str,
        *,
        kind: str,
        label: str,
        storage_uri: str,
        content_type: str,
        checksum: str,
        byte_size: int,
        row_count: int | None,
        metadata: JsonObject,
        actor: str,
    ) -> ProductPackEvidence:
        await self.get_draft(draft_id)
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO product_pack_evidence_set (
                              draft_id, kind, label, storage_uri, content_type, checksum,
                              byte_size, row_count, metadata, created_by
                            ) VALUES (
                              CAST(:draft_id AS uuid), :kind, :label, :storage_uri,
                              :content_type, :checksum, :byte_size, :row_count,
                              CAST(:metadata AS jsonb), :actor
                            )
                            ON CONFLICT (draft_id, kind, checksum) DO UPDATE
                              SET label = EXCLUDED.label
                            RETURNING id::text AS id, draft_id::text AS draft_id, kind, label,
                              storage_uri, content_type, checksum, byte_size, row_count,
                              metadata, created_by, created_at
                            """
                        ),
                        {
                            "draft_id": draft_id,
                            "kind": kind,
                            "label": label,
                            "storage_uri": storage_uri,
                            "content_type": content_type,
                            "checksum": checksum,
                            "byte_size": byte_size,
                            "row_count": row_count,
                            "metadata": _json(metadata),
                            "actor": actor,
                        },
                    )
                )
                .mappings()
                .one()
            )
            await self._event(
                connection,
                draft_id,
                "evidence_attached",
                actor,
                {"kind": kind, "checksum": checksum},
            )
        return _evidence(row)

    async def list_validations(self, draft_id: str) -> list[ProductPackValidationRun]:
        await self.get_draft(draft_id)
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            f"{_VALIDATION_SELECT} WHERE draft_id::text = :draft_id "
                            "ORDER BY created_at DESC"
                        ),
                        {"draft_id": draft_id},
                    )
                )
                .mappings()
                .all()
            )
        return [_validation(row) for row in rows]

    async def request_validation(
        self,
        draft_id: str,
        *,
        suite: ValidationSuite,
        engine_version: str,
        max_attempts: int = 3,
    ) -> ProductPackValidationRun:
        draft = await self.get_draft(draft_id)
        evidence = await self.list_evidence(draft_id)
        evidence_key = ":".join(sorted(item.checksum for item in evidence))
        idempotency_key = hashlib.sha256(
            f"{draft.checksum}:{suite}:{engine_version}:{evidence_key}".encode()
        ).hexdigest()
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO product_pack_validation_run (
                              draft_id, draft_revision, draft_checksum, suite, status,
                              gates, idempotency_key, engine_version, max_attempts
                            ) VALUES (
                              CAST(:draft_id AS uuid), :draft_revision, :draft_checksum,
                              :suite, 'queued', '[]'::jsonb, :idempotency_key,
                              :engine_version, :max_attempts
                            )
                            ON CONFLICT (idempotency_key) DO UPDATE
                              SET status = CASE
                                    WHEN product_pack_validation_run.status
                                      IN ('failed', 'cancelled')
                                      THEN 'queued'
                                    ELSE product_pack_validation_run.status
                                  END,
                                  gates = CASE
                                    WHEN product_pack_validation_run.status
                                      IN ('failed', 'cancelled')
                                      THEN '[]'::jsonb
                                    ELSE product_pack_validation_run.gates
                                  END,
                                  attempt_count = CASE
                                    WHEN product_pack_validation_run.status
                                      IN ('failed', 'cancelled')
                                      THEN 0
                                    ELSE product_pack_validation_run.attempt_count
                                  END,
                                  locked_by = CASE
                                    WHEN product_pack_validation_run.status
                                      IN ('failed', 'cancelled')
                                      THEN NULL
                                    ELSE product_pack_validation_run.locked_by
                                  END,
                                  locked_at = CASE
                                    WHEN product_pack_validation_run.status
                                      IN ('failed', 'cancelled')
                                      THEN NULL
                                    ELSE product_pack_validation_run.locked_at
                                  END,
                                  lease_expires_at = CASE
                                    WHEN product_pack_validation_run.status
                                      IN ('failed', 'cancelled')
                                      THEN NULL
                                    ELSE product_pack_validation_run.lease_expires_at
                                  END,
                                  last_error = CASE
                                    WHEN product_pack_validation_run.status
                                      IN ('failed', 'cancelled')
                                      THEN NULL
                                    ELSE product_pack_validation_run.last_error
                                  END,
                                  cancel_requested_at = CASE
                                    WHEN product_pack_validation_run.status
                                      IN ('failed', 'cancelled')
                                      THEN NULL
                                    ELSE product_pack_validation_run.cancel_requested_at
                                  END,
                                  started_at = CASE
                                    WHEN product_pack_validation_run.status
                                      IN ('failed', 'cancelled')
                                      THEN NULL
                                    ELSE product_pack_validation_run.started_at
                                  END,
                                  completed_at = CASE
                                    WHEN product_pack_validation_run.status
                                      IN ('failed', 'cancelled')
                                      THEN NULL
                                    ELSE product_pack_validation_run.completed_at
                                  END
                            RETURNING id::text AS id, draft_id::text AS draft_id,
                              draft_revision, draft_checksum, suite, status, gates,
                              engine_version, attempt_count, max_attempts, locked_by,
                              lease_expires_at, last_error, cancel_requested_at,
                              started_at, completed_at, created_at
                            """
                        ),
                        {
                            "draft_id": draft_id,
                            "draft_revision": draft.revision,
                            "draft_checksum": draft.checksum,
                            "suite": suite,
                            "idempotency_key": idempotency_key,
                            "engine_version": engine_version,
                            "max_attempts": max_attempts,
                        },
                    )
                )
                .mappings()
                .one()
            )
            if str(row["status"]) == "queued":
                await connection.execute(
                    text(
                        "UPDATE product_pack_draft SET status = 'validating', updated_at = now() "
                        "WHERE id::text = :draft_id AND status NOT IN ('published', 'abandoned')"
                    ),
                    {"draft_id": draft_id},
                )
        return _validation(row)

    async def claim_validations(
        self,
        *,
        worker_id: str,
        limit: int,
        lease_seconds: int,
    ) -> list[ProductPackValidationRun]:
        async with self._engine.begin() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            """
                            WITH candidates AS (
                              SELECT id FROM product_pack_validation_run
                              WHERE cancel_requested_at IS NULL
                                AND attempt_count < max_attempts
                                AND (
                                  status = 'queued'
                                  OR (status = 'running' AND lease_expires_at < now())
                                )
                              ORDER BY created_at
                              FOR UPDATE SKIP LOCKED
                              LIMIT :limit
                            )
                            UPDATE product_pack_validation_run job
                            SET status = 'running', locked_by = :worker_id, locked_at = now(),
                              lease_expires_at = now() + make_interval(secs => :lease_seconds),
                              attempt_count = attempt_count + 1,
                              started_at = COALESCE(started_at, now())
                            FROM candidates WHERE job.id = candidates.id
                            RETURNING job.id::text AS id, job.draft_id::text AS draft_id,
                              job.draft_revision, job.draft_checksum, job.suite, job.status,
                              job.gates, job.engine_version, job.attempt_count,
                              job.max_attempts, job.locked_by, job.lease_expires_at,
                              job.last_error, job.cancel_requested_at, job.started_at,
                              job.completed_at, job.created_at
                            """
                        ),
                        {
                            "worker_id": worker_id,
                            "limit": limit,
                            "lease_seconds": lease_seconds,
                        },
                    )
                )
                .mappings()
                .all()
            )
        return [_validation(row) for row in rows]

    async def complete_validation(
        self,
        run_id: str,
        *,
        worker_id: str,
        passed: bool,
        gates: list[JsonObject],
        error: str | None = None,
    ) -> ProductPackValidationRun:
        status_value = "passed" if passed else "failed"
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            UPDATE product_pack_validation_run SET
                              status = CASE
                                WHEN cancel_requested_at IS NOT NULL THEN 'cancelled'
                                ELSE :status
                              END,
                              gates = CAST(:gates AS jsonb), last_error = :error,
                              completed_at = now(), locked_by = NULL, locked_at = NULL,
                              lease_expires_at = NULL
                            WHERE id::text = :run_id AND status = 'running'
                              AND locked_by = :worker_id
                            RETURNING id::text AS id, draft_id::text AS draft_id,
                              draft_revision, draft_checksum, suite, status, gates,
                              engine_version, attempt_count, max_attempts, locked_by,
                              lease_expires_at, last_error, cancel_requested_at,
                              started_at, completed_at, created_at
                            """
                        ),
                        {
                            "run_id": run_id,
                            "worker_id": worker_id,
                            "status": status_value,
                            "gates": _json(gates),
                            "error": error,
                        },
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise ProductPackDraftConflictError("Validation lease is no longer owned")
            completed_status = str(row["status"])
            next_status = (
                "certified"
                if completed_status == "passed" and str(row["suite"]) == "publication"
                else "candidate"
                if completed_status == "passed"
                else "draft"
            )
            await connection.execute(
                text(
                    """
                    UPDATE product_pack_draft SET status = :status, updated_at = now()
                    WHERE id = CAST(:draft_id AS uuid)
                      AND revision = :revision AND checksum = :checksum
                      AND status NOT IN ('published', 'abandoned')
                    """
                ),
                {
                    "draft_id": str(row["draft_id"]),
                    "revision": int(row["draft_revision"]),
                    "checksum": str(row["draft_checksum"]),
                    "status": next_status,
                },
            )
            await self._event(
                connection,
                str(row["draft_id"]),
                "validation_completed",
                worker_id,
                {"run_id": run_id, "suite": str(row["suite"]), "status": completed_status},
            )
        return _validation(row)

    async def cancel_validation(
        self,
        draft_id: str,
        run_id: str,
        *,
        actor: str,
    ) -> ProductPackValidationRun:
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            f"""
                            UPDATE product_pack_validation_run SET
                              cancel_requested_at = COALESCE(cancel_requested_at, now()),
                              status = CASE WHEN status = 'queued' THEN 'cancelled' ELSE status END,
                              completed_at = CASE
                                WHEN status = 'queued' THEN COALESCE(completed_at, now())
                                ELSE completed_at
                              END
                            WHERE id::text = :run_id AND draft_id::text = :draft_id
                              AND status IN ('queued', 'running')
                            RETURNING {_VALIDATION_COLUMNS}
                            """
                        ),
                        {"run_id": run_id, "draft_id": draft_id},
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                existing = (
                    (
                        await connection.execute(
                            text(
                                f"{_VALIDATION_SELECT} WHERE id::text = :run_id "
                                "AND draft_id::text = :draft_id"
                            ),
                            {"run_id": run_id, "draft_id": draft_id},
                        )
                    )
                    .mappings()
                    .first()
                )
                if existing is None:
                    raise ProductPackDraftNotFoundError(
                        f"Product Pack validation {run_id!r} was not found"
                    )
                return _validation(existing)
            await connection.execute(
                text(
                    "UPDATE product_pack_draft SET status = 'draft', updated_at = now() "
                    "WHERE id::text = :draft_id AND status = 'validating'"
                ),
                {"draft_id": draft_id},
            )
            await self._event(
                connection,
                draft_id,
                "validation_cancel_requested",
                actor,
                {"run_id": run_id, "status": str(row["status"])},
            )
        return _validation(row)

    async def fail_validation_attempt(
        self,
        run_id: str,
        *,
        worker_id: str,
        error: str,
    ) -> None:
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                    UPDATE product_pack_validation_run SET
                      status = CASE
                        WHEN cancel_requested_at IS NOT NULL THEN 'cancelled'
                        WHEN attempt_count >= max_attempts THEN 'failed' ELSE 'queued' END,
                      last_error = :error, locked_by = NULL, locked_at = NULL,
                      lease_expires_at = NULL,
                      completed_at = CASE
                        WHEN cancel_requested_at IS NOT NULL
                          OR attempt_count >= max_attempts THEN now() ELSE NULL END
                    WHERE id::text = :run_id AND locked_by = :worker_id
                    RETURNING draft_id::text AS draft_id, status
                    """
                        ),
                        {"run_id": run_id, "worker_id": worker_id, "error": error[:4000]},
                    )
                )
                .mappings()
                .first()
            )
            if row is not None and str(row["status"]) in {"failed", "cancelled"}:
                await connection.execute(
                    text(
                        "UPDATE product_pack_draft SET status = 'draft', updated_at = now() "
                        "WHERE id::text = :draft_id AND status = 'validating'"
                    ),
                    {"draft_id": str(row["draft_id"])},
                )

    async def publish(
        self,
        draft_id: str,
        *,
        validation_run_id: str,
        actor: str,
        activate: bool,
        default_keyword: str,
        release_notes: str | None,
    ) -> ProductPackPublication:
        async with self._engine.begin() as connection:
            await connection.execute(text("SET CONSTRAINTS ALL DEFERRED"))
            draft_row = (
                (
                    await connection.execute(
                        text(f"{_DRAFT_SELECT} WHERE id::text = :draft_id FOR UPDATE"),
                        {"draft_id": draft_id},
                    )
                )
                .mappings()
                .first()
            )
            if draft_row is None:
                raise ProductPackDraftNotFoundError(
                    f"Product Pack draft {draft_id!r} was not found"
                )
            draft = _draft(draft_row)
            validation = (
                (
                    await connection.execute(
                        text(
                            f"{_VALIDATION_SELECT} WHERE id::text = :validation_run_id FOR UPDATE"
                        ),
                        {"validation_run_id": validation_run_id},
                    )
                )
                .mappings()
                .first()
            )
            if (
                draft.status != "certified"
                or validation is None
                or str(validation["status"]) != "passed"
                or str(validation["suite"]) != "publication"
                or int(validation["draft_revision"]) != draft.revision
                or str(validation["draft_checksum"]) != draft.checksum
            ):
                raise ProductPackPublicationError(
                    "Publication requires a passing publication validation for this exact revision"
                )
            config = draft.config
            blueprint = draft.report_blueprint
            pack_id = str(config["id"])
            version = str(config["version"])
            blueprint_id = str(blueprint["id"])
            blueprint_version = str(blueprint["version"])
            if (pack_id, version) != (draft.product_pack_id, draft.proposed_version):
                raise ProductPackPublicationError("Draft identity does not match its Product Pack")
            pack_checksum = canonical_checksum(config)
            blueprint_checksum = canonical_checksum(blueprint)
            await connection.execute(
                text(
                    """
                    INSERT INTO product_pack (id, name, active)
                    VALUES (:id, :name, true)
                    ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, updated_at = now()
                    """
                ),
                {"id": pack_id, "name": str(config["name"])},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO report_blueprint (id, name, active)
                    VALUES (:id, :name, true)
                    ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name
                    """
                ),
                {"id": blueprint_id, "name": blueprint_id.replace("_", " ").title()},
            )
            try:
                await connection.execute(
                    text(
                        """
                        INSERT INTO product_pack_version (
                          product_pack_id, version, schema_version, config, checksum,
                          default_keyword, report_blueprint_id, report_blueprint_version,
                          report_blueprint_checksum, published_by, release_notes,
                          certification_validation_run_id
                        ) VALUES (
                          :pack_id, :version, :schema_version, CAST(:config AS jsonb),
                          :checksum, :default_keyword, :blueprint_id, :blueprint_version,
                          :blueprint_checksum, :actor, :release_notes,
                          CAST(:validation_run_id AS uuid)
                        )
                        """
                    ),
                    {
                        "pack_id": pack_id,
                        "version": version,
                        "schema_version": str(config.get("schema_version", "1.0.0")),
                        "config": _json(config),
                        "checksum": pack_checksum,
                        "default_keyword": default_keyword,
                        "blueprint_id": blueprint_id,
                        "blueprint_version": blueprint_version,
                        "blueprint_checksum": blueprint_checksum,
                        "actor": actor,
                        "release_notes": release_notes,
                        "validation_run_id": validation_run_id,
                    },
                )
                await connection.execute(
                    text(
                        """
                        INSERT INTO report_blueprint_version (
                          report_blueprint_id, version, schema_version,
                          product_pack_id, product_pack_version, config, checksum, published_by
                        ) VALUES (
                          :blueprint_id, :blueprint_version, :schema_version,
                          :pack_id, :pack_version, CAST(:config AS jsonb), :checksum, :actor
                        )
                        """
                    ),
                    {
                        "blueprint_id": blueprint_id,
                        "blueprint_version": blueprint_version,
                        "schema_version": str(blueprint.get("schema_version", "1.0.0")),
                        "pack_id": pack_id,
                        "pack_version": version,
                        "config": _json(blueprint),
                        "checksum": blueprint_checksum,
                        "actor": actor,
                    },
                )
            except IntegrityError as exc:
                raise ProductPackPublicationError(
                    f"Product Pack {pack_id}@{version} already exists or conflicts"
                ) from exc
            if activate:
                await connection.execute(
                    text(
                        "UPDATE product_pack SET active_version = :version, active = true, "
                        "updated_at = now() WHERE id = :pack_id"
                    ),
                    {"pack_id": pack_id, "version": version},
                )
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            UPDATE product_pack_draft SET status = 'published', updated_by = :actor,
                              updated_at = now() WHERE id::text = :draft_id
                            RETURNING updated_at
                            """
                        ),
                        {"draft_id": draft_id, "actor": actor},
                    )
                )
                .mappings()
                .one()
            )
            await self._event(
                connection,
                draft_id,
                "version_published",
                actor,
                {"version": version, "active": activate},
            )
        return ProductPackPublication(
            product_pack_id=pack_id,
            version=version,
            checksum=pack_checksum,
            report_blueprint_id=blueprint_id,
            report_blueprint_version=blueprint_version,
            report_blueprint_checksum=blueprint_checksum,
            validation_run_id=validation_run_id,
            active=activate,
            published_by=actor,
            published_at=row["updated_at"],
        )

    @staticmethod
    async def _record_revision(
        connection: Any,
        *,
        draft_id: str,
        revision: int,
        config: JsonObject,
        report_blueprint: JsonObject,
        checksum: str,
        actor: str,
        reason: str | None,
    ) -> None:
        await connection.execute(
            text(
                """
                INSERT INTO product_pack_draft_revision (
                  draft_id, revision, config, report_blueprint, checksum,
                  changed_by, change_reason
                ) VALUES (
                  CAST(:draft_id AS uuid), :revision, CAST(:config AS jsonb),
                  CAST(:report_blueprint AS jsonb), :checksum, :actor, :reason
                )
                """
            ),
            {
                "draft_id": draft_id,
                "revision": revision,
                "config": _json(config),
                "report_blueprint": _json(report_blueprint),
                "checksum": checksum,
                "actor": actor,
                "reason": reason,
            },
        )

    @staticmethod
    async def _event(
        connection: Any,
        draft_id: str,
        event_type: str,
        actor: str,
        details: JsonObject,
    ) -> None:
        await connection.execute(
            text(
                """
                INSERT INTO product_pack_review_event (draft_id, event_type, actor, details)
                VALUES (CAST(:draft_id AS uuid), :event_type, :actor, CAST(:details AS jsonb))
                """
            ),
            {
                "draft_id": draft_id,
                "event_type": event_type,
                "actor": actor,
                "details": _json(details),
            },
        )
