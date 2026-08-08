"""Concurrency-safe in-memory control plane used by deterministic tests."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from rci_collections.models import (
    BudgetExceededError,
    CollectionPlan,
    DefinitionRecord,
    LocationUnit,
    QueueTask,
    RawArtifact,
    RetailerRunProgress,
    RunMonitor,
    RunRecord,
    RunUsage,
    TaskSeed,
)

DEFAULT_ORGANIZATION_ID = "00000000-0000-0000-0000-000000000001"


class InMemoryCollectionRepository:
    def __init__(self, location_units: Sequence[LocationUnit] = ()) -> None:
        self._lock = asyncio.Lock()
        self._location_units = list(location_units)
        self._definitions: dict[str, list[DefinitionRecord]] = {}
        self._definition_ids: dict[str, str] = {}
        self._versions: dict[str, DefinitionRecord] = {}
        self._runs: dict[str, RunRecord] = {}
        self._tasks: dict[str, QueueTask] = {}
        self._task_identities: set[tuple[str, str, str, int, str]] = set()
        self._artifacts: dict[str, RawArtifact] = {}
        self._scheduled_runs: dict[tuple[str, datetime], str] = {}

    async def list_location_units(
        self, retailer_ids: Sequence[str], country: str
    ) -> list[LocationUnit]:
        selected = set(retailer_ids)
        return [
            unit
            for unit in self._location_units
            if unit.retailer_id in selected and unit.country == country
        ]

    async def publish_definition(
        self, config: dict[str, object], checksum: str
    ) -> DefinitionRecord:
        stable_key = str(config["id"])
        async with self._lock:
            versions = self._definitions.setdefault(stable_key, [])
            for version in versions:
                if version.checksum == checksum:
                    return version
            definition_id = self._definition_ids.setdefault(stable_key, str(uuid4()))
            record = DefinitionRecord(
                id=definition_id,
                stable_key=stable_key,
                name=str(config["name"]),
                active=bool(config.get("enabled", True)),
                version_id=str(uuid4()),
                version=len(versions) + 1,
                checksum=checksum,
                config=dict(config),
                created_at=datetime.now(UTC),
            )
            versions.append(record)
            self._versions[record.version_id] = record
            return record

    async def list_definitions(self) -> list[DefinitionRecord]:
        async with self._lock:
            return sorted(
                (versions[-1] for versions in self._definitions.values()),
                key=lambda item: item.stable_key,
            )

    async def get_definition(self, identifier: str) -> DefinitionRecord | None:
        async with self._lock:
            versions = self._definitions.get(identifier)
            if versions:
                return versions[-1]
            stable_key = next(
                (key for key, value in self._definition_ids.items() if value == identifier), None
            )
            return self._definitions[stable_key][-1] if stable_key is not None else None

    async def create_run(
        self,
        definition: DefinitionRecord,
        plan: CollectionPlan,
        *,
        trigger_type: str = "manual",
        schedule_id: str | None = None,
        scheduled_for: datetime | None = None,
    ) -> RunRecord:
        async with self._lock:
            now = datetime.now(UTC)
            if schedule_id is not None and scheduled_for is not None:
                existing_id = self._scheduled_runs.get((schedule_id, scheduled_for))
                if existing_id is not None:
                    return self._runs[existing_id]
            self._check_period_budgets(definition, plan, now)
            run = RunRecord(
                id=str(uuid4()),
                definition_version_id=definition.version_id,
                status="queued",
                estimated_pages=plan.estimate.estimated_total_pages,
                estimated_credits=plan.estimate.estimated_total_credits,
                actual_success_pages=0,
                actual_credits=0,
                started_at=None,
                completed_at=None,
                cancel_requested_at=None,
                created_at=now,
                trigger_type=trigger_type,
                schedule_id=schedule_id,
                scheduled_for=scheduled_for,
            )
            self._runs[run.id] = run
            if schedule_id is not None and scheduled_for is not None:
                self._scheduled_runs[(schedule_id, scheduled_for)] = run.id
            for seed in plan.initial_tasks:
                self._insert_task(run.id, seed, now)
            if not plan.initial_tasks:
                run = replace(run, status="succeeded", completed_at=now)
                self._runs[run.id] = run
            return run

    def _check_period_budgets(
        self, definition: DefinitionRecord, plan: CollectionPlan, now: datetime
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
        definition_versions = {
            version.version_id
            for versions in self._definitions.values()
            for version in versions
            if version.id == definition.id
        }
        runs = [
            run for run in self._runs.values() if run.definition_version_id in definition_versions
        ]
        periods = (
            ("day", budget.get("max_credits_per_day")),
            ("month", budget.get("max_credits_per_month")),
        )
        for period, limit in periods:
            if limit is None:
                continue
            selected = [
                run
                for run in runs
                if run.created_at.year == now.year
                and (period != "month" or run.created_at.month == now.month)
                and (period != "day" or run.created_at.date() == now.date())
            ]
            used = sum(
                run.actual_credits
                if run.status in {"succeeded", "failed", "cancelled"}
                else run.estimated_credits
                for run in selected
            )
            if used + estimate > int(limit):
                raise BudgetExceededError(
                    f"{period} credit budget {limit} would be exceeded: "
                    f"used/reserved {used}, requested {estimate}"
                )

    def _insert_task(self, run_id: str, seed: TaskSeed, now: datetime) -> bool:
        identity = (
            run_id,
            seed.retailer_id,
            seed.location_scope_key,
            seed.page_number,
            seed.request_fingerprint,
        )
        if identity in self._task_identities:
            return False
        self._task_identities.add(identity)
        task = QueueTask(
            id=str(uuid4()),
            collection_run_id=run_id,
            retailer_id=seed.retailer_id,
            retailer_location_id=seed.retailer_location_id,
            adapter_id=seed.adapter_id,
            location_scope_key=seed.location_scope_key,
            zipcode=seed.zipcode,
            store_number=seed.store_number,
            page_number=seed.page_number,
            max_pages=seed.max_pages,
            stop_on_empty=seed.stop_on_empty,
            stop_on_short_page=seed.stop_on_short_page,
            credits_per_success=seed.credits_per_success,
            request_payload=dict(seed.request_payload),
            request_fingerprint=seed.request_fingerprint,
            status="pending",
            priority=seed.priority,
            attempt_count=0,
            max_attempts=seed.max_attempts,
            available_at=now,
            locked_by=None,
            lease_expires_at=None,
            created_at=now,
        )
        self._tasks[task.id] = task
        return True

    async def get_run(self, run_id: str) -> RunRecord | None:
        async with self._lock:
            return self._runs.get(run_id)

    async def list_tasks(self, run_id: str, limit: int = 200) -> list[QueueTask]:
        async with self._lock:
            tasks = [task for task in self._tasks.values() if task.collection_run_id == run_id]
            return sorted(tasks, key=lambda item: (item.created_at, item.id))[:limit]

    async def usage(self, run_id: str) -> RunUsage | None:
        async with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return None
            counts = {
                status: 0 for status in ("pending", "running", "succeeded", "failed", "cancelled")
            }
            for task in self._tasks.values():
                if task.collection_run_id == run_id:
                    counts[task.status] += 1
            return RunUsage(
                run_id=run.id,
                estimated_pages=run.estimated_pages,
                estimated_credits=run.estimated_credits,
                actual_success_pages=run.actual_success_pages,
                actual_credits=run.actual_credits,
                pending_tasks=counts["pending"],
                running_tasks=counts["running"],
                succeeded_tasks=counts["succeeded"],
                failed_tasks=counts["failed"],
                cancelled_tasks=counts["cancelled"],
            )

    async def monitor(self, run_id: str) -> RunMonitor | None:
        async with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return None
            tasks = [task for task in self._tasks.values() if task.collection_run_id == run_id]
            totals = {
                status: sum(task.status == status for task in tasks)
                for status in ("pending", "running", "succeeded", "failed", "cancelled")
            }
            usage = RunUsage(
                run_id=run.id,
                estimated_pages=run.estimated_pages,
                estimated_credits=run.estimated_credits,
                actual_success_pages=run.actual_success_pages,
                actual_credits=run.actual_credits,
                pending_tasks=totals["pending"],
                running_tasks=totals["running"],
                succeeded_tasks=totals["succeeded"],
                failed_tasks=totals["failed"],
                cancelled_tasks=totals["cancelled"],
            )
            retailers = []
            for retailer_id in sorted({task.retailer_id for task in tasks}):
                selected = [task for task in tasks if task.retailer_id == retailer_id]
                retailers.append(
                    RetailerRunProgress(
                        retailer_id=retailer_id,
                        pending_tasks=sum(task.status == "pending" for task in selected),
                        running_tasks=sum(task.status == "running" for task in selected),
                        succeeded_tasks=sum(task.status == "succeeded" for task in selected),
                        failed_tasks=sum(task.status == "failed" for task in selected),
                        cancelled_tasks=sum(task.status == "cancelled" for task in selected),
                        billable_credits=sum(task.billable_credits for task in selected),
                        attempts=sum(task.attempt_count for task in selected),
                        retries=sum(max(task.attempt_count - 1, 0) for task in selected),
                    )
                )
            failure_classes: dict[str, int] = {}
            for task in tasks:
                if task.failure_class is not None:
                    failure_classes[task.failure_class] = (
                        failure_classes.get(task.failure_class, 0) + 1
                    )
            now = datetime.now(UTC)
            start = run.started_at or run.created_at
            end = run.completed_at or now
            return RunMonitor(
                run=run,
                usage=usage,
                retailers=tuple(retailers),
                retry_attempts=sum(max(task.attempt_count - 1, 0) for task in tasks),
                failure_classes=failure_classes,
                elapsed_seconds=max((end - start).total_seconds(), 0),
                provider_state=None,
            )

    async def record_artifact(self, run_id: str, artifact: RawArtifact) -> str:
        async with self._lock:
            if run_id not in self._runs:
                raise ValueError(f"collection run {run_id!r} does not exist")
            artifact_id = self._record_artifact(artifact)
            assert artifact_id is not None
            return artifact_id

    async def claim_tasks(
        self, worker_id: str, *, claim_limit: int, lease_seconds: int
    ) -> list[QueueTask]:
        now = datetime.now(UTC)
        async with self._lock:
            exhausted_runs: set[str] = set()
            for task_id, task in tuple(self._tasks.items()):
                run = self._runs[task.collection_run_id]
                if (
                    run.cancel_requested_at is None
                    and task.status == "running"
                    and task.lease_expires_at is not None
                    and task.lease_expires_at <= now
                    and task.attempt_count >= task.max_attempts
                ):
                    self._tasks[task_id] = replace(
                        task,
                        status="failed",
                        locked_by=None,
                        lease_expires_at=None,
                        failure_class="lease_exhausted",
                        last_error="Lease expired after maximum attempts",
                    )
                    exhausted_runs.add(run.id)
            for run_id in exhausted_runs:
                self._reconcile_run(run_id, now)

            cancelled_runs: set[str] = set()
            for task_id, task in tuple(self._tasks.items()):
                run = self._runs[task.collection_run_id]
                if (
                    run.cancel_requested_at is not None
                    and task.status == "running"
                    and task.lease_expires_at is not None
                    and task.lease_expires_at <= now
                ):
                    self._tasks[task_id] = replace(
                        task,
                        status="cancelled",
                        locked_by=None,
                        lease_expires_at=None,
                    )
                    cancelled_runs.add(run.id)
            for run_id in cancelled_runs:
                self._reconcile_run(run_id, now)

            eligible = []
            for task in self._tasks.values():
                run = self._runs[task.collection_run_id]
                pending = task.status == "pending" and task.available_at <= now
                expired = (
                    task.status == "running"
                    and task.lease_expires_at is not None
                    and task.lease_expires_at <= now
                )
                if (
                    (pending or expired)
                    and task.attempt_count < task.max_attempts
                    and run.cancel_requested_at is None
                    and run.status in {"queued", "running"}
                ):
                    eligible.append(task)
            eligible.sort(key=lambda item: (item.priority, item.created_at, item.id))
            claimed = []
            for task in eligible[:claim_limit]:
                updated = replace(
                    task,
                    status="running",
                    attempt_count=task.attempt_count + 1,
                    locked_by=worker_id,
                    lease_expires_at=now + timedelta(seconds=lease_seconds),
                )
                self._tasks[task.id] = updated
                claimed.append(updated)
                run = self._runs[task.collection_run_id]
                if run.status == "queued":
                    self._runs[run.id] = replace(run, status="running", started_at=now)
            return claimed

    async def extend_lease(self, task_id: str, worker_id: str, lease_seconds: int) -> bool:
        now = datetime.now(UTC)
        async with self._lock:
            task = self._tasks.get(task_id)
            if (
                task is None
                or task.status != "running"
                or task.locked_by != worker_id
                or task.lease_expires_at is None
                or task.lease_expires_at <= now
            ):
                return False
            self._tasks[task_id] = replace(
                task, lease_expires_at=now + timedelta(seconds=lease_seconds)
            )
            return True

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
        now = datetime.now(UTC)
        async with self._lock:
            task = self._tasks.get(task_id)
            if task is None or task.status == "succeeded":
                return False
            if (
                task.status != "running"
                or task.locked_by != worker_id
                or task.lease_expires_at is None
                or task.lease_expires_at <= now
            ):
                return False
            updated = replace(
                task,
                status="succeeded",
                locked_by=None,
                lease_expires_at=None,
                http_status=http_status,
                result_count=result_count,
                billable_credits=task.billable_credits + task.credits_per_success,
                raw_artifact_id=self._record_artifact(raw_artifact) or task.raw_artifact_id,
            )
            self._tasks[task_id] = updated
            run = self._runs[task.collection_run_id]
            self._runs[run.id] = replace(
                run,
                actual_success_pages=run.actual_success_pages + 1,
                actual_credits=run.actual_credits + task.credits_per_success,
            )
            if run.cancel_requested_at is None and next_task is not None:
                self._insert_task(run.id, next_task, now)
            self._reconcile_run(run.id, now)
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
        now = datetime.now(UTC)
        async with self._lock:
            task = self._tasks.get(task_id)
            if (
                task is None
                or task.status != "running"
                or task.locked_by != worker_id
                or task.lease_expires_at is None
                or task.lease_expires_at <= now
            ):
                return False
            run = self._runs[task.collection_run_id]
            can_retry = (
                retryable
                and task.attempt_count < task.max_attempts
                and run.cancel_requested_at is None
            )
            billed_credits = task.credits_per_success if billable else 0
            self._tasks[task_id] = replace(
                task,
                status="pending" if can_retry else "failed",
                available_at=now + timedelta(seconds=retry_delay_seconds),
                locked_by=None,
                lease_expires_at=None,
                failure_class=failure_class,
                last_error=error_message,
                http_status=http_status,
                raw_artifact_id=self._record_artifact(raw_artifact) or task.raw_artifact_id,
                billable_credits=task.billable_credits + billed_credits,
            )
            if billed_credits:
                self._runs[run.id] = replace(
                    run,
                    actual_success_pages=(
                        run.actual_success_pages
                        + int(http_status is not None and 200 <= http_status < 300)
                    ),
                    actual_credits=run.actual_credits + billed_credits,
                )
            self._reconcile_run(run.id, now)
            return True

    def _record_artifact(self, artifact: RawArtifact | None) -> str | None:
        if artifact is None:
            return None
        existing = self._artifacts.setdefault(artifact.storage_uri, artifact)
        if existing != artifact:
            raise ValueError(f"artifact URI {artifact.storage_uri!r} is immutable")
        return artifact.storage_uri

    async def cancel_run(self, run_id: str) -> RunRecord | None:
        now = datetime.now(UTC)
        async with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return None
            if run.status in {"cancelled", "succeeded", "failed"}:
                return run
            run = replace(run, status="cancel_requested", cancel_requested_at=now)
            self._runs[run_id] = run
            for task_id, task in tuple(self._tasks.items()):
                if task.collection_run_id == run_id and task.status == "pending":
                    self._tasks[task_id] = replace(task, status="cancelled")
            self._reconcile_run(run_id, now)
            return self._runs[run_id]

    async def retry_failed(self, run_id: str) -> int:
        now = datetime.now(UTC)
        async with self._lock:
            run = self._runs.get(run_id)
            if run is None or run.cancel_requested_at is not None:
                return 0
            retried = 0
            for task_id, task in tuple(self._tasks.items()):
                if (
                    task.collection_run_id == run_id
                    and task.status == "failed"
                    and task.attempt_count < task.max_attempts
                ):
                    self._tasks[task_id] = replace(
                        task,
                        status="pending",
                        available_at=now,
                        failure_class=None,
                        locked_by=None,
                        lease_expires_at=None,
                    )
                    retried += 1
            if retried:
                self._runs[run_id] = replace(
                    run, status="running" if run.started_at else "queued", completed_at=None
                )
            return retried

    def _reconcile_run(self, run_id: str, now: datetime) -> None:
        run = self._runs[run_id]
        tasks = [task for task in self._tasks.values() if task.collection_run_id == run_id]
        if any(task.status in {"pending", "running"} for task in tasks):
            return
        if run.cancel_requested_at is not None:
            status = "cancelled"
        elif any(task.status == "failed" for task in tasks):
            status = "failed"
        else:
            status = "succeeded"
        self._runs[run_id] = replace(run, status=status, completed_at=now)

    async def expire_lease_for_test(self, task_id: str) -> None:
        async with self._lock:
            task = self._tasks[task_id]
            self._tasks[task_id] = replace(
                task, lease_expires_at=datetime.now(UTC) - timedelta(seconds=1)
            )
