"""Postgres collection control plane and SKIP LOCKED durable queue."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from rci_collections.models import (
    BudgetExceededError,
    CollectionPlan,
    DefinitionRecord,
    LocationUnit,
    ProviderRateState,
    QueueTask,
    RawArtifact,
    RetailerRunProgress,
    RunMonitor,
    RunRecord,
    RunUsage,
    TaskSeed,
)

DEFAULT_ORGANIZATION_ID = "00000000-0000-0000-0000-000000000001"


def _json(value: dict[str, object]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _definition(row: RowMapping) -> DefinitionRecord:
    return DefinitionRecord(
        id=str(row["id"]),
        stable_key=str(row["stable_key"]),
        name=str(row["name"]),
        active=bool(row["active"]),
        version_id=str(row["version_id"]),
        version=int(row["version"]),
        checksum=str(row["checksum"]),
        config=dict(row["config"]),
        created_at=row["created_at"],
    )


def _run(row: RowMapping) -> RunRecord:
    return RunRecord(
        id=str(row["id"]),
        definition_version_id=str(row["definition_version_id"]),
        status=str(row["status"]),
        estimated_pages=int(row["estimated_pages"]),
        estimated_credits=int(row["estimated_credits"]),
        actual_success_pages=int(row["actual_success_pages"]),
        actual_credits=int(row["actual_credits"]),
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        cancel_requested_at=row["cancel_requested_at"],
        created_at=row["created_at"],
        trigger_type=str(row.get("trigger_type", "manual")),
        schedule_id=str(row["schedule_id"]) if row.get("schedule_id") is not None else None,
        scheduled_for=row.get("scheduled_for"),
        availability_gate_status=str(row.get("availability_gate_status", "skipped")),
        availability_gate_config=dict(row.get("availability_gate_config") or {}),
    )


def _task(row: RowMapping) -> QueueTask:
    return QueueTask(
        id=str(row["id"]),
        collection_run_id=str(row["collection_run_id"]),
        retailer_id=str(row["retailer_id"]),
        retailer_location_id=(
            str(row["retailer_location_id"]) if row["retailer_location_id"] is not None else None
        ),
        adapter_id=str(row["adapter_id"]),
        location_scope_key=str(row["location_scope_key"]),
        zipcode=str(row["zipcode"]),
        store_number=str(row["store_number"]) if row["store_number"] is not None else None,
        page_number=int(row["page_number"]),
        max_pages=int(row["max_pages"]),
        stop_on_empty=bool(row["stop_on_empty"]),
        stop_on_short_page=bool(row["stop_on_short_page"]),
        credits_per_success=int(row["credits_per_success"]),
        request_payload=dict(row["request_payload"]),
        request_fingerprint=str(row["request_fingerprint"]),
        status=str(row["status"]),
        priority=int(row["priority"]),
        attempt_count=int(row["attempt_count"]),
        max_attempts=int(row["max_attempts"]),
        available_at=row["available_at"],
        locked_by=str(row["locked_by"]) if row["locked_by"] is not None else None,
        lease_expires_at=row["lease_expires_at"],
        created_at=row["created_at"],
        http_status=row["http_status"],
        result_count=row["result_count"],
        failure_class=row["failure_class"],
        last_error=row["last_error"],
        billable_credits=int(row["billable_credits"]),
        raw_artifact_id=(
            str(row["raw_artifact_id"]) if row.get("raw_artifact_id") is not None else None
        ),
        is_preflight=bool(row.get("is_preflight", False)),
    )


class PostgresCollectionRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def list_location_units(
        self, retailer_ids: Sequence[str], country: str
    ) -> list[LocationUnit]:
        if not retailer_ids:
            return []
        statement = text(
            """
            SELECT id::text AS id, retailer_id, zipcode, store_number, state, country
            FROM retailer_location
            WHERE retailer_id = ANY(CAST(:retailer_ids AS text[])) AND country = :country
            ORDER BY retailer_id, store_number, id
            """
        )
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    statement,
                    {"retailer_ids": list(retailer_ids), "country": country},
                )
            ).mappings()
            return [LocationUnit(**dict(row)) for row in rows]

    async def publish_definition(
        self, config: dict[str, object], checksum: str
    ) -> DefinitionRecord:
        stable_key = str(config["id"])
        async with self._engine.begin() as connection:
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:stable_key, 0))"),
                {"stable_key": stable_key},
            )
            definition_row = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT id::text AS id
                        FROM collection_definition
                        WHERE organization_id = CAST(:organization_id AS uuid)
                          AND stable_key = :stable_key
                        FOR UPDATE
                        """
                        ),
                        {
                            "organization_id": DEFAULT_ORGANIZATION_ID,
                            "stable_key": stable_key,
                        },
                    )
                )
                .mappings()
                .first()
            )
            if definition_row is None:
                definition_id = str(
                    (
                        await connection.execute(
                            text(
                                """
                                INSERT INTO collection_definition (
                                  organization_id, stable_key, name, active
                                ) VALUES (
                                  CAST(:organization_id AS uuid), :stable_key, :name, :active
                                )
                                RETURNING id::text
                                """
                            ),
                            {
                                "organization_id": DEFAULT_ORGANIZATION_ID,
                                "stable_key": stable_key,
                                "name": str(config["name"]),
                                "active": bool(config.get("enabled", True)),
                            },
                        )
                    ).scalar_one()
                )
            else:
                definition_id = str(definition_row["id"])
                await connection.execute(
                    text(
                        """
                        UPDATE collection_definition
                        SET name = :name, active = :active
                        WHERE id = CAST(:id AS uuid)
                        """
                    ),
                    {
                        "id": definition_id,
                        "name": str(config["name"]),
                        "active": bool(config.get("enabled", True)),
                    },
                )

            existing = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT v.id::text AS version_id, v.version, v.checksum, v.config,
                               v.created_at, d.id::text AS id, d.stable_key, d.name, d.active
                        FROM collection_definition_version v
                        JOIN collection_definition d ON d.id = v.definition_id
                        WHERE v.definition_id = CAST(:definition_id AS uuid)
                          AND v.checksum = :checksum
                        """
                        ),
                        {"definition_id": definition_id, "checksum": checksum},
                    )
                )
                .mappings()
                .first()
            )
            if existing is not None:
                return _definition(existing)

            next_version = int(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT COALESCE(max(version), 0) + 1
                            FROM collection_definition_version
                            WHERE definition_id = CAST(:definition_id AS uuid)
                            """
                        ),
                        {"definition_id": definition_id},
                    )
                ).scalar_one()
            )
            row = (
                (
                    await connection.execute(
                        text(
                            """
                        WITH inserted AS (
                          INSERT INTO collection_definition_version (
                            definition_id, version, config, checksum
                          ) VALUES (
                            CAST(:definition_id AS uuid), :version,
                            CAST(:config AS jsonb), :checksum
                          )
                          RETURNING id, version, checksum, config, created_at, definition_id
                        )
                        SELECT i.id::text AS version_id, i.version, i.checksum, i.config,
                               i.created_at, d.id::text AS id, d.stable_key, d.name, d.active
                        FROM inserted i
                        JOIN collection_definition d ON d.id = i.definition_id
                        """
                        ),
                        {
                            "definition_id": definition_id,
                            "version": next_version,
                            "config": _json(config),
                            "checksum": checksum,
                        },
                    )
                )
                .mappings()
                .one()
            )
            return _definition(row)

    async def list_definitions(self) -> list[DefinitionRecord]:
        statement = text(
            """
            SELECT d.id::text AS id, d.stable_key, d.name, d.active,
                   v.id::text AS version_id, v.version, v.checksum, v.config, v.created_at
            FROM collection_definition d
            JOIN LATERAL (
              SELECT * FROM collection_definition_version
              WHERE definition_id = d.id ORDER BY version DESC LIMIT 1
            ) v ON true
            WHERE d.organization_id = CAST(:organization_id AS uuid)
            ORDER BY d.stable_key
            """
        )
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(statement, {"organization_id": DEFAULT_ORGANIZATION_ID})
            ).mappings()
            return [_definition(row) for row in rows]

    async def get_definition(self, identifier: str) -> DefinitionRecord | None:
        statement = text(
            """
            SELECT d.id::text AS id, d.stable_key, d.name, d.active,
                   v.id::text AS version_id, v.version, v.checksum, v.config, v.created_at
            FROM collection_definition d
            JOIN LATERAL (
              SELECT * FROM collection_definition_version
              WHERE definition_id = d.id ORDER BY version DESC LIMIT 1
            ) v ON true
            WHERE d.organization_id = CAST(:organization_id AS uuid)
              AND (d.id::text = :identifier OR d.stable_key = :identifier)
            """
        )
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        statement,
                        {
                            "organization_id": DEFAULT_ORGANIZATION_ID,
                            "identifier": identifier,
                        },
                    )
                )
                .mappings()
                .first()
            )
            return _definition(row) if row is not None else None

    async def create_run(
        self,
        definition: DefinitionRecord,
        plan: CollectionPlan,
        *,
        trigger_type: str = "manual",
        schedule_id: str | None = None,
        scheduled_for: datetime | None = None,
    ) -> RunRecord:
        async with self._engine.begin() as connection:
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:budget_key, 0))"),
                {"budget_key": f"collection-budget:{definition.id}"},
            )
            if schedule_id is not None and scheduled_for is not None:
                existing = (
                    (
                        await connection.execute(
                            text(
                                "SELECT * FROM collection_run "
                                "WHERE schedule_id::text = :schedule_id "
                                "AND scheduled_for = :scheduled_for"
                            ),
                            {"schedule_id": schedule_id, "scheduled_for": scheduled_for},
                        )
                    )
                    .mappings()
                    .first()
                )
                if existing is not None:
                    return _run(existing)
            await self._check_period_budgets(connection, definition, plan)
            row = (
                (
                    await connection.execute(
                        text(
                            """
                        INSERT INTO collection_run (
                          organization_id, definition_version_id, status,
                          estimated_pages, estimated_credits, trigger_type,
                          schedule_id, scheduled_for, availability_gate_status,
                          availability_gate_config
                        ) VALUES (
                          CAST(:organization_id AS uuid), CAST(:definition_version_id AS uuid),
                          :status, :estimated_pages, :estimated_credits, :trigger_type,
                          CAST(:schedule_id AS uuid), :scheduled_for,
                          :availability_gate_status, CAST(:availability_gate_config AS jsonb)
                        )
                        ON CONFLICT ON CONSTRAINT collection_run_schedule_slot_uq DO NOTHING
                        RETURNING *
                        """
                        ),
                        {
                            "organization_id": DEFAULT_ORGANIZATION_ID,
                            "definition_version_id": definition.version_id,
                            "status": "queued" if plan.initial_tasks else "succeeded",
                            "estimated_pages": plan.estimate.estimated_total_pages,
                            "estimated_credits": plan.estimate.estimated_total_credits,
                            "trigger_type": trigger_type,
                            "schedule_id": schedule_id,
                            "scheduled_for": scheduled_for,
                            "availability_gate_status": (
                                "pending" if plan.availability_gate else "skipped"
                            ),
                            "availability_gate_config": _json(plan.availability_gate),
                        },
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                if schedule_id is None or scheduled_for is None:
                    raise RuntimeError("collection run insert returned no row")
                existing = (
                    (
                        await connection.execute(
                            text(
                                "SELECT * FROM collection_run "
                                "WHERE schedule_id::text = :schedule_id "
                                "AND scheduled_for = :scheduled_for"
                            ),
                            {"schedule_id": schedule_id, "scheduled_for": scheduled_for},
                        )
                    )
                    .mappings()
                    .one()
                )
                return _run(existing)
            run_id = str(row["id"])
            if plan.initial_tasks:
                await connection.execute(
                    self._insert_task_statement(),
                    [self._task_parameters(run_id, seed) for seed in plan.initial_tasks],
                )
            else:
                row = (
                    (
                        await connection.execute(
                            text(
                                """
                            UPDATE collection_run SET completed_at = now()
                            WHERE id = CAST(:id AS uuid) RETURNING *
                            """
                            ),
                            {"id": run_id},
                        )
                    )
                    .mappings()
                    .one()
                )
            return _run(row)

    @staticmethod
    async def _check_period_budgets(
        connection: AsyncConnection,
        definition: DefinitionRecord,
        plan: CollectionPlan,
    ) -> None:
        budget = definition.config.get("budget")
        if not isinstance(budget, dict):
            return
        estimate = plan.estimate.estimated_total_credits
        run_limit = budget.get("max_credits_per_run")
        if (
            bool(budget.get("block_if_estimate_exceeds_budget", True))
            and run_limit is not None
            and estimate > int(run_limit)
        ):
            raise BudgetExceededError(f"estimated credits {estimate} exceed run budget {run_limit}")
        for period, limit in (
            ("day", budget.get("max_credits_per_day")),
            ("month", budget.get("max_credits_per_month")),
        ):
            if limit is None:
                continue
            interval = "day" if period == "day" else "month"
            used = int(
                (
                    await connection.execute(
                        text(
                            f"""
                            SELECT COALESCE(sum(
                              CASE WHEN r.status IN (
                                'succeeded', 'completed_with_warnings', 'failed', 'cancelled'
                              )
                                THEN r.actual_credits ELSE r.estimated_credits END
                            ), 0)
                            FROM collection_run r
                            JOIN collection_definition_version v ON v.id = r.definition_version_id
                            WHERE v.definition_id = CAST(:definition_id AS uuid)
                              AND r.created_at >= (
                                date_trunc('{interval}', now() AT TIME ZONE 'UTC')
                                AT TIME ZONE 'UTC'
                              )
                            """
                        ),
                        {"definition_id": definition.id},
                    )
                ).scalar_one()
            )
            if used + estimate > int(limit):
                raise BudgetExceededError(
                    f"{period} credit budget {limit} would be exceeded: "
                    f"used/reserved {used}, requested {estimate}"
                )

    @staticmethod
    def _insert_task_statement():
        return text(
            """
            INSERT INTO collection_task (
              collection_run_id, retailer_id, retailer_location_id, adapter_id,
              location_scope_key, zipcode, store_number, page_number, max_pages,
              stop_on_empty, stop_on_short_page, credits_per_success,
              request_payload, request_fingerprint, priority, max_attempts, is_preflight
            ) VALUES (
              CAST(:collection_run_id AS uuid), :retailer_id,
              CAST(:retailer_location_id AS uuid), :adapter_id, :location_scope_key,
              :zipcode, :store_number, :page_number, :max_pages, :stop_on_empty,
              :stop_on_short_page, :credits_per_success, CAST(:request_payload AS jsonb),
              :request_fingerprint, :priority, :max_attempts, :is_preflight
            )
            ON CONFLICT ON CONSTRAINT collection_task_identity_uq DO NOTHING
            """
        )

    @staticmethod
    def _task_parameters(run_id: str, seed: TaskSeed) -> dict[str, object]:
        return {
            "collection_run_id": run_id,
            "retailer_id": seed.retailer_id,
            "retailer_location_id": seed.retailer_location_id,
            "adapter_id": seed.adapter_id,
            "location_scope_key": seed.location_scope_key,
            "zipcode": seed.zipcode,
            "store_number": seed.store_number,
            "page_number": seed.page_number,
            "max_pages": seed.max_pages,
            "stop_on_empty": seed.stop_on_empty,
            "stop_on_short_page": seed.stop_on_short_page,
            "credits_per_success": seed.credits_per_success,
            "request_payload": _json(seed.request_payload),
            "request_fingerprint": seed.request_fingerprint,
            "priority": seed.priority,
            "max_attempts": seed.max_attempts,
            "is_preflight": seed.is_preflight,
        }

    async def get_run(self, run_id: str) -> RunRecord | None:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text("SELECT * FROM collection_run WHERE id::text = :id"), {"id": run_id}
                    )
                )
                .mappings()
                .first()
            )
            return _run(row) if row is not None else None

    async def list_runs(self, limit: int = 50) -> list[RunRecord]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        SELECT * FROM collection_run
                        ORDER BY created_at DESC, id DESC
                        LIMIT :limit
                        """
                    ),
                    {"limit": limit},
                )
            ).mappings()
            return [_run(row) for row in rows]

    async def list_tasks(
        self,
        run_id: str,
        limit: int = 200,
        *,
        retailer_id: str | None = None,
        status: str | None = None,
    ) -> list[QueueTask]:
        filters = ["collection_run_id::text = :run_id"]
        parameters: dict[str, object] = {"run_id": run_id, "limit": limit}
        if retailer_id is not None:
            filters.append("retailer_id = :retailer_id")
            parameters["retailer_id"] = retailer_id
        if status is not None:
            filters.append("status = :status")
            parameters["status"] = status
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        f"""
                        SELECT * FROM collection_task
                        WHERE {" AND ".join(filters)}
                        ORDER BY created_at, id LIMIT :limit
                        """
                    ),
                    parameters,
                )
            ).mappings()
            return [_task(row) for row in rows]

    async def usage(self, run_id: str) -> RunUsage | None:
        statement = text(
            """
            SELECT r.id::text AS run_id, r.estimated_pages, r.estimated_credits,
                   r.actual_success_pages, r.actual_credits,
                   count(*) FILTER (WHERE t.status = 'pending')::integer AS pending_tasks,
                   count(*) FILTER (WHERE t.status = 'running')::integer AS running_tasks,
                   count(*) FILTER (WHERE t.status = 'succeeded')::integer AS succeeded_tasks,
                   count(*) FILTER (WHERE t.status = 'failed')::integer AS failed_tasks,
                   count(*) FILTER (WHERE t.status = 'cancelled')::integer AS cancelled_tasks
            FROM collection_run r
            LEFT JOIN collection_task t ON t.collection_run_id = r.id
            WHERE r.id::text = :run_id
            GROUP BY r.id
            """
        )
        async with self._engine.connect() as connection:
            row = (await connection.execute(statement, {"run_id": run_id})).mappings().first()
            return RunUsage(**dict(row)) if row is not None else None

    async def monitor(self, run_id: str) -> RunMonitor | None:
        run = await self.get_run(run_id)
        usage = await self.usage(run_id)
        if run is None or usage is None:
            return None
        async with self._engine.connect() as connection:
            progress_rows = (
                await connection.execute(
                    text(
                        """
                        SELECT retailer_id,
                          count(*) FILTER (WHERE status = 'pending')::integer AS pending_tasks,
                          count(*) FILTER (WHERE status = 'running')::integer AS running_tasks,
                          count(*) FILTER (WHERE status = 'succeeded')::integer AS succeeded_tasks,
                          count(*) FILTER (WHERE status = 'failed')::integer AS failed_tasks,
                          count(*) FILTER (WHERE status = 'cancelled')::integer AS cancelled_tasks,
                          COALESCE(sum(billable_credits), 0)::integer AS billable_credits,
                          COALESCE(sum(attempt_count), 0)::integer AS attempts,
                          COALESCE(sum(GREATEST(attempt_count - 1, 0)), 0)::integer AS retries
                        FROM collection_task
                        WHERE collection_run_id::text = :run_id
                        GROUP BY retailer_id ORDER BY retailer_id
                        """
                    ),
                    {"run_id": run_id},
                )
            ).mappings()
            retailers = tuple(RetailerRunProgress(**dict(row)) for row in progress_rows)
            failure_rows = (
                await connection.execute(
                    text(
                        """
                        SELECT failure_class, count(*)::integer AS failures
                        FROM collection_task
                        WHERE collection_run_id::text = :run_id
                          AND failure_class IS NOT NULL
                        GROUP BY failure_class ORDER BY failure_class
                        """
                    ),
                    {"run_id": run_id},
                )
            ).mappings()
            failure_classes = {
                str(row["failure_class"]): int(row["failures"]) for row in failure_rows
            }
            provider_row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT provider, second_count, minute_count, paused_until,
                                   last_429_at, updated_at
                            FROM provider_rate_limit_state
                            ORDER BY updated_at DESC LIMIT 1
                            """
                        )
                    )
                )
                .mappings()
                .first()
            )
        provider_state = (
            ProviderRateState(**dict(provider_row)) if provider_row is not None else None
        )
        now = datetime.now(UTC)
        start = run.started_at or run.created_at
        end = run.completed_at or now
        return RunMonitor(
            run=run,
            usage=usage,
            retailers=retailers,
            retry_attempts=sum(row.retries for row in retailers),
            failure_classes=failure_classes,
            elapsed_seconds=max((end - start).total_seconds(), 0),
            provider_state=provider_state,
        )

    async def claim_tasks(
        self, worker_id: str, *, claim_limit: int, lease_seconds: int
    ) -> list[QueueTask]:
        claim_statement = text(
            """
            WITH candidates AS (
              SELECT t.id
              FROM collection_task t
              JOIN collection_run r ON r.id = t.collection_run_id
              WHERE (
                (t.status = 'pending' AND t.available_at <= now()) OR
                (t.status = 'running' AND t.lease_expires_at <= now())
              )
                AND r.status IN ('queued', 'running')
                AND r.cancel_requested_at IS NULL
                AND t.attempt_count < t.max_attempts
                AND (
                  r.availability_gate_status IN ('skipped', 'passed') OR
                  (r.availability_gate_status = 'pending' AND t.is_preflight)
                )
              ORDER BY t.priority, t.created_at, t.id
              FOR UPDATE OF t SKIP LOCKED
              LIMIT :claim_limit
            )
            UPDATE collection_task t
            SET status = 'running', locked_by = :worker_id, locked_at = now(),
                lease_expires_at = now() + make_interval(secs => :lease_seconds),
                attempt_count = t.attempt_count + 1
            FROM candidates c
            WHERE t.id = c.id
            RETURNING t.*
            """
        )
        async with self._engine.begin() as connection:
            exhausted_run_ids = (
                await connection.execute(
                    text(
                        """
                        UPDATE collection_task t
                        SET status = 'failed', failure_class = 'lease_exhausted',
                            last_error = 'Lease expired after maximum attempts',
                            locked_by = NULL, locked_at = NULL, lease_expires_at = NULL,
                            completed_at = now()
                        FROM collection_run r
                        WHERE r.id = t.collection_run_id
                          AND r.cancel_requested_at IS NULL
                          AND t.status = 'running' AND t.lease_expires_at <= now()
                          AND t.attempt_count >= t.max_attempts
                        RETURNING t.collection_run_id::text
                        """
                    )
                )
            ).scalars()
            for run_id in set(exhausted_run_ids):
                await self._reconcile_run(connection, run_id)

            cancelled_run_ids = (
                await connection.execute(
                    text(
                        """
                        UPDATE collection_task t
                        SET status = 'cancelled', locked_by = NULL, locked_at = NULL,
                            lease_expires_at = NULL, completed_at = now()
                        FROM collection_run r
                        WHERE r.id = t.collection_run_id
                          AND r.cancel_requested_at IS NOT NULL
                          AND t.status = 'running' AND t.lease_expires_at <= now()
                        RETURNING t.collection_run_id::text
                        """
                    )
                )
            ).scalars()
            for run_id in set(cancelled_run_ids):
                await self._reconcile_run(connection, run_id)

            rows = (
                (
                    await connection.execute(
                        claim_statement,
                        {
                            "worker_id": worker_id,
                            "claim_limit": claim_limit,
                            "lease_seconds": lease_seconds,
                        },
                    )
                )
                .mappings()
                .all()
            )
            run_ids = {str(row["collection_run_id"]) for row in rows}
            if run_ids:
                await connection.execute(
                    text(
                        """
                        UPDATE collection_run
                        SET status = 'running', started_at = COALESCE(started_at, now())
                        WHERE id = ANY(CAST(:run_ids AS uuid[])) AND status = 'queued'
                        """
                    ),
                    {"run_ids": list(run_ids)},
                )
            return [_task(row) for row in rows]

    async def extend_lease(self, task_id: str, worker_id: str, lease_seconds: int) -> bool:
        statement = text(
            """
            UPDATE collection_task
            SET lease_expires_at = now() + make_interval(secs => :lease_seconds)
            WHERE id::text = :task_id AND status = 'running' AND locked_by = :worker_id
              AND lease_expires_at > now()
            RETURNING id
            """
        )
        async with self._engine.begin() as connection:
            result = await connection.execute(
                statement,
                {
                    "task_id": task_id,
                    "worker_id": worker_id,
                    "lease_seconds": lease_seconds,
                },
            )
            return result.first() is not None

    async def record_artifact(self, run_id: str, artifact: RawArtifact) -> str:
        async with self._engine.begin() as connection:
            artifact_id = await self._record_artifact(connection, run_id, None, artifact)
            assert artifact_id is not None
            return artifact_id

    async def complete_success(
        self,
        task_id: str,
        worker_id: str,
        *,
        http_status: int,
        result_count: int,
        next_task: TaskSeed | None,
        raw_artifact: RawArtifact | None = None,
    ) -> bool:
        async with self._engine.begin() as connection:
            row = await self._locked_task(connection, task_id)
            if row is None or row["status"] == "succeeded":
                return False
            if (
                row["status"] != "running"
                or row["locked_by"] != worker_id
                or not row["lease_valid"]
            ):
                return False
            run_id = str(row["collection_run_id"])
            credits = int(row["credits_per_success"])
            raw_artifact_id = await self._record_artifact(connection, run_id, task_id, raw_artifact)
            await connection.execute(
                text(
                    """
                    UPDATE collection_task
                    SET status = 'succeeded', http_status = :http_status,
                        result_count = :result_count,
                        billable_credits = billable_credits + :credits,
                        raw_artifact_id = CAST(:raw_artifact_id AS uuid),
                        locked_by = NULL, locked_at = NULL, lease_expires_at = NULL,
                        completed_at = now()
                    WHERE id::text = :task_id
                    """
                ),
                {
                    "task_id": task_id,
                    "http_status": http_status,
                    "result_count": result_count,
                    "credits": credits,
                    "raw_artifact_id": raw_artifact_id,
                },
            )
            run_row = (
                (
                    await connection.execute(
                        text(
                            """
                        UPDATE collection_run
                        SET actual_success_pages = actual_success_pages + 1,
                            actual_credits = actual_credits + :credits
                        WHERE id::text = :run_id
                        RETURNING cancel_requested_at
                        """
                        ),
                        {"run_id": run_id, "credits": credits},
                    )
                )
                .mappings()
                .one()
            )
            if next_task is not None and run_row["cancel_requested_at"] is None:
                await connection.execute(
                    self._insert_task_statement(), self._task_parameters(run_id, next_task)
                )
            await self._reconcile_run(connection, run_id)
            return True

    async def complete_failure(
        self,
        task_id: str,
        worker_id: str,
        *,
        failure_class: str,
        error_message: str,
        retryable: bool,
        retry_delay_seconds: float,
        http_status: int | None = None,
        raw_artifact: RawArtifact | None = None,
        billable: bool = False,
    ) -> bool:
        async with self._engine.begin() as connection:
            row = await self._locked_task(connection, task_id)
            if (
                row is None
                or row["status"] != "running"
                or row["locked_by"] != worker_id
                or not row["lease_valid"]
            ):
                return False
            run_id = str(row["collection_run_id"])
            run_cancelled = bool(
                (
                    await connection.execute(
                        text(
                            "SELECT cancel_requested_at IS NOT NULL FROM collection_run "
                            "WHERE id::text = :run_id"
                        ),
                        {"run_id": run_id},
                    )
                ).scalar_one()
            )
            can_retry = (
                retryable
                and int(row["attempt_count"]) < int(row["max_attempts"])
                and not run_cancelled
            )
            raw_artifact_id = await self._record_artifact(connection, run_id, task_id, raw_artifact)
            billed_credits = int(row["credits_per_success"]) if billable else 0
            await connection.execute(
                text(
                    """
                    UPDATE collection_task
                    SET status = :status,
                        available_at = now() + make_interval(secs => :retry_delay_seconds),
                        locked_by = NULL, locked_at = NULL, lease_expires_at = NULL,
                        failure_class = :failure_class, last_error = :last_error,
                        http_status = :http_status,
                        raw_artifact_id = COALESCE(
                          CAST(:raw_artifact_id AS uuid), raw_artifact_id
                        ),
                        billable_credits = billable_credits + :billed_credits,
                        completed_at = CASE WHEN :can_retry THEN NULL ELSE now() END
                    WHERE id::text = :task_id
                    """
                ),
                {
                    "task_id": task_id,
                    "status": "pending" if can_retry else "failed",
                    "retry_delay_seconds": retry_delay_seconds,
                    "failure_class": failure_class,
                    "last_error": error_message[:4_000],
                    "can_retry": can_retry,
                    "http_status": http_status,
                    "raw_artifact_id": raw_artifact_id,
                    "billed_credits": billed_credits,
                },
            )
            if billed_credits:
                await connection.execute(
                    text(
                        """
                        UPDATE collection_run
                        SET actual_success_pages = actual_success_pages + :successful_page,
                            actual_credits = actual_credits + :credits
                        WHERE id::text = :run_id
                        """
                    ),
                    {
                        "run_id": run_id,
                        "credits": billed_credits,
                        "successful_page": int(
                            http_status is not None and 200 <= http_status < 300
                        ),
                    },
                )
            await self._reconcile_run(connection, run_id)
            return True

    @staticmethod
    async def _record_artifact(
        connection: AsyncConnection,
        run_id: str,
        task_id: str | None,
        artifact: RawArtifact | None,
    ) -> str | None:
        if artifact is None:
            return None
        artifact_id = (
            await connection.execute(
                text(
                    """
                        INSERT INTO dataset_artifact (
                          collection_run_id, artifact_type, storage_uri, content_type,
                          row_count, byte_size, checksum, schema_version, metadata
                        ) VALUES (
                          CAST(:run_id AS uuid), :artifact_type, :storage_uri, :content_type,
                          :row_count, :byte_size, :checksum, :schema_version,
                          CAST(:metadata AS jsonb)
                        )
                        ON CONFLICT (storage_uri) DO UPDATE
                        SET storage_uri = EXCLUDED.storage_uri
                        WHERE dataset_artifact.checksum = EXCLUDED.checksum
                        RETURNING id::text
                        """
                ),
                {
                    "run_id": run_id,
                    "artifact_type": artifact.artifact_type,
                    "storage_uri": artifact.storage_uri,
                    "content_type": artifact.content_type,
                    "byte_size": artifact.byte_size,
                    "row_count": artifact.row_count,
                    "checksum": artifact.checksum,
                    "schema_version": artifact.schema_version,
                    "metadata": _json(
                        {
                            **artifact.metadata,
                            **({"task_id": task_id} if task_id is not None else {}),
                        }
                    ),
                },
            )
        ).scalar_one_or_none()
        if artifact_id is None:
            raise ValueError(f"dataset artifact {artifact.storage_uri!r} is immutable")
        return str(artifact_id)

    async def cancel_run(self, run_id: str) -> RunRecord | None:
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                        UPDATE collection_run
                        SET cancel_requested_at = COALESCE(cancel_requested_at, now()),
                            status = CASE
                              WHEN status IN (
                                'succeeded', 'completed_with_warnings', 'failed', 'cancelled'
                              ) THEN status
                              ELSE 'cancel_requested'
                            END
                        WHERE id::text = :run_id
                        RETURNING *
                        """
                        ),
                        {"run_id": run_id},
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            await connection.execute(
                text(
                    """
                    UPDATE collection_task
                    SET status = 'cancelled', completed_at = now()
                    WHERE collection_run_id::text = :run_id AND status = 'pending'
                    """
                ),
                {"run_id": run_id},
            )
            await connection.execute(
                text(
                    """
                    UPDATE collection_task
                    SET status = 'cancelled', locked_by = NULL, locked_at = NULL,
                        lease_expires_at = NULL, completed_at = now()
                    WHERE collection_run_id::text = :run_id AND status = 'running'
                      AND lease_expires_at <= now()
                    """
                ),
                {"run_id": run_id},
            )
            await self._reconcile_run(connection, run_id)
            refreshed = (
                (
                    await connection.execute(
                        text("SELECT * FROM collection_run WHERE id::text = :run_id"),
                        {"run_id": run_id},
                    )
                )
                .mappings()
                .one()
            )
            return _run(refreshed)

    async def retry_failed(self, run_id: str) -> int:
        async with self._engine.begin() as connection:
            result = await connection.execute(
                text(
                    """
                    UPDATE collection_task t
                    SET status = 'pending', available_at = now(), failure_class = NULL,
                        last_error = NULL, completed_at = NULL
                    FROM collection_run r
                    WHERE r.id = t.collection_run_id AND r.id::text = :run_id
                      AND r.cancel_requested_at IS NULL AND t.status = 'failed'
                      AND t.attempt_count < t.max_attempts
                    RETURNING t.id
                    """
                ),
                {"run_id": run_id},
            )
            count = len(result.all())
            if count:
                await connection.execute(
                    text(
                        """
                        UPDATE collection_task t
                        SET status = 'pending', available_at = now(), completed_at = NULL
                        FROM collection_run r
                        WHERE r.id = t.collection_run_id AND r.id::text = :run_id
                          AND r.availability_gate_status = 'failed'
                          AND NOT t.is_preflight AND t.status = 'cancelled'
                        """
                    ),
                    {"run_id": run_id},
                )
                await connection.execute(
                    text(
                        """
                        UPDATE collection_run
                        SET status = CASE WHEN started_at IS NULL THEN 'queued' ELSE 'running' END,
                            completed_at = NULL, error_summary = NULL,
                            availability_gate_status = CASE
                              WHEN availability_gate_status = 'failed' THEN 'pending'
                              ELSE availability_gate_status END
                        WHERE id::text = :run_id
                        """
                    ),
                    {"run_id": run_id},
                )
            return count

    @staticmethod
    async def _locked_task(connection: AsyncConnection, task_id: str) -> RowMapping | None:
        # Lock the parent first so concurrent completions and cancellation use one order.
        run_id = (
            await connection.execute(
                text("SELECT collection_run_id::text FROM collection_task WHERE id::text = :id"),
                {"id": task_id},
            )
        ).scalar_one_or_none()
        if run_id is None:
            return None
        run_exists = (
            await connection.execute(
                text("SELECT id FROM collection_run WHERE id::text = :run_id FOR UPDATE"),
                {"run_id": run_id},
            )
        ).first()
        if run_exists is None:
            return None
        return (
            (
                await connection.execute(
                    text(
                        "SELECT *, lease_expires_at > now() AS lease_valid "
                        "FROM collection_task WHERE id::text = :id FOR UPDATE"
                    ),
                    {"id": task_id},
                )
            )
            .mappings()
            .first()
        )

    @staticmethod
    async def _reconcile_run(connection: AsyncConnection, run_id: str) -> None:
        gate = (
            (
                await connection.execute(
                    text(
                        "SELECT availability_gate_status, availability_gate_config "
                        "FROM collection_run WHERE id::text = :run_id FOR UPDATE"
                    ),
                    {"run_id": run_id},
                )
            )
            .mappings()
            .one()
        )
        if gate["availability_gate_status"] == "pending":
            summary = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT count(*)::integer AS total,
                                   count(*) FILTER (
                                     WHERE status IN ('pending', 'running')
                                   )::integer AS open,
                                   count(*) FILTER (WHERE http_status = 404)::integer AS not_found,
                                   count(*) FILTER (
                                     WHERE status = 'failed' AND http_status IS DISTINCT FROM 404
                                   )::integer AS other_failures
                            FROM collection_task
                            WHERE collection_run_id::text = :run_id AND is_preflight
                            """
                        ),
                        {"run_id": run_id},
                    )
                )
                .mappings()
                .one()
            )
            if int(summary["total"]) and not int(summary["open"]):
                config = dict(gate["availability_gate_config"] or {})
                rate = int(summary["not_found"]) / int(summary["total"])
                maximum = float(config.get("max_billable_404_rate", 0.5))
                gate_status = (
                    "failed" if rate > maximum or int(summary["other_failures"]) else "passed"
                )
                error_summary = (
                    f"availability preflight failed: billable 404 rate {rate:.3f} "
                    f"exceeded {maximum:.3f}"
                    if rate > maximum
                    else "availability preflight failed: provider sample had terminal failures"
                )
                await connection.execute(
                    text(
                        """
                        UPDATE collection_run
                        SET availability_gate_status = :gate_status,
                            error_summary = CASE WHEN :gate_status = 'failed'
                              THEN :error_summary ELSE error_summary END
                        WHERE id::text = :run_id
                        """
                    ),
                    {
                        "run_id": run_id,
                        "gate_status": gate_status,
                        "error_summary": error_summary,
                    },
                )
                if gate_status == "failed":
                    await connection.execute(
                        text(
                            """
                            UPDATE collection_task
                            SET status = 'cancelled', completed_at = now()
                            WHERE collection_run_id::text = :run_id
                              AND NOT is_preflight AND status = 'pending'
                            """
                        ),
                        {"run_id": run_id},
                    )
        await connection.execute(
            text(
                """
                UPDATE collection_run r
                SET status = CASE
                      WHEN r.cancel_requested_at IS NOT NULL THEN 'cancelled'
                      WHEN r.availability_gate_status = 'failed' THEN 'failed'
                      WHEN EXISTS (
                        SELECT 1 FROM collection_task t
                        WHERE t.collection_run_id = r.id AND t.status = 'failed'
                          AND NOT (
                            t.http_status = 404 AND t.failure_class = 'invalid_request'
                          )
                      ) THEN 'failed'
                      WHEN EXISTS (
                        SELECT 1 FROM collection_task t
                        WHERE t.collection_run_id = r.id AND t.status = 'failed'
                      ) AND EXISTS (
                        SELECT 1 FROM collection_task t
                        WHERE t.collection_run_id = r.id AND t.status = 'succeeded'
                      ) THEN 'completed_with_warnings'
                      WHEN EXISTS (
                        SELECT 1 FROM collection_task t
                        WHERE t.collection_run_id = r.id AND t.status = 'failed'
                      ) THEN 'failed'
                      ELSE 'succeeded'
                    END,
                    completed_at = now()
                WHERE r.id::text = :run_id
                  AND NOT EXISTS (
                    SELECT 1 FROM collection_task t
                    WHERE t.collection_run_id = r.id AND t.status IN ('pending', 'running')
                  )
                """
            ),
            {"run_id": run_id},
        )
