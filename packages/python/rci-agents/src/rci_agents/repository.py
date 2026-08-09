"""Idempotent audit persistence for governed AI tasks."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from rci_agents.governance import checksum
from rci_agents.models import AgentTaskReservation, AgentTaskSpec, JsonObject


class AgentTaskRepository(Protocol):
    async def reserve(
        self,
        spec: AgentTaskSpec,
        *,
        worker_id: str,
        lease_seconds: int,
    ) -> AgentTaskReservation: ...

    async def succeed(self, task_id: str, worker_id: str, output: JsonObject) -> None: ...

    async def fail(
        self,
        task_id: str,
        worker_id: str,
        error_type: str,
        issues: list[str],
    ) -> None: ...


def _idempotency_key(spec: AgentTaskSpec) -> str:
    return checksum(
        {
            "analysis_run_id": spec.analysis_run_id,
            "role": spec.role,
            "prompt_checksum": spec.prompt.checksum,
            "model": [spec.provider, spec.model_id],
            "input_checksum": spec.input_checksum,
        }
    )


class InMemoryAgentTaskRepository:
    def __init__(self) -> None:
        self._records: dict[str, JsonObject] = {}

    async def reserve(
        self,
        spec: AgentTaskSpec,
        *,
        worker_id: str,
        lease_seconds: int,
    ) -> AgentTaskReservation:
        key = _idempotency_key(spec)
        record = self._records.get(key)
        if record is not None and record["status"] == "succeeded":
            return AgentTaskReservation(
                task_id=str(record["id"]),
                acquired=False,
                cached_output=dict(record["output"]),
            )
        if (
            record is not None
            and record["status"] == "running"
            and record["lease_expires_at"] > datetime.now(UTC)
        ):
            return AgentTaskReservation(task_id=str(record["id"]), acquired=False)
        if record is not None and int(record["attempt_count"]) >= spec.max_attempts:
            return AgentTaskReservation(task_id=str(record["id"]), acquired=False)
        task_id = str(record["id"]) if record else str(uuid4())
        self._records[key] = {
            "id": task_id,
            "status": "running",
            "worker_id": worker_id,
            "lease_expires_at": datetime.now(UTC) + timedelta(seconds=lease_seconds),
            "attempt_count": int(record["attempt_count"]) + 1 if record else 1,
            "spec": spec,
            "output": None,
        }
        return AgentTaskReservation(task_id=task_id, acquired=True)

    async def succeed(self, task_id: str, worker_id: str, output: JsonObject) -> None:
        record = self._find(task_id)
        self._assert_lease_owner(record, worker_id)
        record.update({"status": "succeeded", "output": dict(output)})

    async def fail(
        self,
        task_id: str,
        worker_id: str,
        error_type: str,
        issues: list[str],
    ) -> None:
        record = self._find(task_id)
        self._assert_lease_owner(record, worker_id)
        record.update(
            {
                "status": "needs_review",
                "error_type": error_type,
                "issues": list(issues),
            }
        )

    def _find(self, task_id: str) -> JsonObject:
        return next(record for record in self._records.values() if record["id"] == task_id)

    @staticmethod
    def _assert_lease_owner(record: JsonObject, worker_id: str) -> None:
        if (
            record["status"] != "running"
            or record["worker_id"] != worker_id
            or record["lease_expires_at"] <= datetime.now(UTC)
        ):
            raise RuntimeError("governed AI task lease is no longer owned by this worker")


class PostgresAgentTaskRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def reserve(
        self,
        spec: AgentTaskSpec,
        *,
        worker_id: str,
        lease_seconds: int,
    ) -> AgentTaskReservation:
        key = _idempotency_key(spec)
        async with self._engine.begin() as connection:
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": key},
            )
            existing = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT id::text AS id, status, output_document,
                                   attempt_count, lease_expires_at > now() AS lease_active
                            FROM agent_task
                            WHERE idempotency_key = :key
                            """
                        ),
                        {"key": key},
                    )
                )
                .mappings()
                .first()
            )
            if existing is not None and existing["status"] == "succeeded":
                return AgentTaskReservation(
                    task_id=str(existing["id"]),
                    acquired=False,
                    cached_output=dict(existing["output_document"]),
                )
            if existing is not None and (
                (existing["status"] == "running" and bool(existing["lease_active"]))
                or int(existing["attempt_count"]) >= spec.max_attempts
            ):
                return AgentTaskReservation(task_id=str(existing["id"]), acquired=False)
            params = {
                "key": key,
                "analysis_run_id": spec.analysis_run_id,
                "analysis_id": spec.analysis_id,
                "role": spec.role,
                "prompt_id": spec.prompt.id,
                "prompt_version": spec.prompt.version,
                "prompt_checksum": spec.prompt.checksum,
                "provider": spec.provider,
                "model_id": spec.model_id,
                "input_checksum": spec.input_checksum,
                "input_document": json.dumps(spec.input_document, sort_keys=True),
                "max_attempts": spec.max_attempts,
                "worker_id": worker_id,
                "lease_seconds": lease_seconds,
            }
            task_id = str(
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO agent_task (
                              idempotency_key, analysis_run_id, analysis_id, role,
                              prompt_template_id, prompt_template_version,
                              prompt_template_checksum, model_provider, model_id,
                              input_checksum, input_document, status, attempt_count,
                              max_attempts, locked_by, locked_at, lease_expires_at
                            ) VALUES (
                              :key, CAST(:analysis_run_id AS uuid), :analysis_id, :role,
                              :prompt_id, :prompt_version, :prompt_checksum, :provider,
                              :model_id, :input_checksum, CAST(:input_document AS jsonb),
                              'running', 1, :max_attempts, :worker_id, now(),
                              now() + make_interval(secs => :lease_seconds)
                            )
                            ON CONFLICT (idempotency_key) DO UPDATE SET
                              status = 'running',
                              attempt_count = agent_task.attempt_count + 1,
                              locked_by = EXCLUDED.locked_by,
                              locked_at = now(),
                              lease_expires_at = EXCLUDED.lease_expires_at,
                              last_error_type = NULL,
                              validation = '{}'::jsonb,
                              updated_at = now()
                            RETURNING id::text
                            """
                        ),
                        params,
                    )
                ).scalar_one()
            )
            return AgentTaskReservation(task_id=task_id, acquired=True)

    async def succeed(self, task_id: str, worker_id: str, output: JsonObject) -> None:
        async with self._engine.begin() as connection:
            result = await connection.execute(
                text(
                    """
                    UPDATE agent_task
                    SET status = 'succeeded', output_checksum = :output_checksum,
                        output_document = CAST(:output AS jsonb),
                        validation = CAST(:validation AS jsonb),
                        usage = CAST(:usage AS jsonb), completed_at = now(),
                        locked_by = NULL, locked_at = NULL, lease_expires_at = NULL,
                        updated_at = now()
                    WHERE id::text = :task_id AND status = 'running'
                      AND locked_by = :worker_id AND lease_expires_at > now()
                    """
                ),
                {
                    "task_id": task_id,
                    "worker_id": worker_id,
                    "output_checksum": str(output["output_checksum_sha256"]),
                    "output": json.dumps(output, sort_keys=True),
                    "validation": json.dumps(output["validation"], sort_keys=True),
                    "usage": json.dumps(output.get("usage", {}), sort_keys=True),
                },
            )
            if result.rowcount != 1:
                raise RuntimeError("governed AI task lease expired before completion")

    async def fail(
        self,
        task_id: str,
        worker_id: str,
        error_type: str,
        issues: list[str],
    ) -> None:
        async with self._engine.begin() as connection:
            result = await connection.execute(
                text(
                    """
                    UPDATE agent_task
                    SET status = 'needs_review', last_error_type = :error_type,
                        validation = CAST(:validation AS jsonb),
                        completed_at = now(), locked_by = NULL, locked_at = NULL,
                        lease_expires_at = NULL, updated_at = now()
                    WHERE id::text = :task_id AND status = 'running'
                      AND locked_by = :worker_id AND lease_expires_at > now()
                    """
                ),
                {
                    "task_id": task_id,
                    "worker_id": worker_id,
                    "error_type": error_type[:200],
                    "validation": json.dumps(
                        {
                            "status": "needs_review",
                            "unsupported_numeric_claims": 0,
                            "metric_reference_coverage": 0,
                            "issues": issues,
                        },
                        sort_keys=True,
                    ),
                },
            )
            if result.rowcount != 1:
                raise RuntimeError("governed AI task lease expired before failure was recorded")
