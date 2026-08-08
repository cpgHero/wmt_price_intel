"""Application service for collection definitions and runs."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from rci_collections.models import (
    BudgetExceededError,
    CostEstimate,
    DefinitionRecord,
    JsonObject,
    QueueTask,
    RunMonitor,
    RunRecord,
    RunUsage,
)
from rci_collections.planner import CollectionPlanner, canonical_checksum
from rci_collections.ports import CollectionRepository
from rci_contracts import ContractError, validate_instance
from rci_core import CronExpressionError, CronSchedule


class CollectionNotFoundError(LookupError):
    pass


class CollectionBudgetError(ValueError):
    pass


def _validate_schedule(config: JsonObject) -> None:
    schedule = config.get("schedule")
    if not isinstance(schedule, dict):
        return
    timezone = str(schedule.get("timezone", "UTC"))
    expression = str(schedule.get("cron") or "0 0 * * *")
    try:
        CronSchedule(expression, timezone)
    except CronExpressionError as exc:
        raise ContractError(f"collection definition: schedule: {exc}") from exc


class CollectionService:
    def __init__(
        self,
        repository: CollectionRepository,
        planner: CollectionPlanner,
        schema_root: Path,
    ) -> None:
        self.repository = repository
        self.planner = planner
        self.schema_root = schema_root

    async def publish_definition(self, config: JsonObject) -> DefinitionRecord:
        validate_instance(
            self.schema_root,
            "collection-definition.schema.json",
            config,
            label="collection definition",
        )
        _validate_schedule(config)
        return await self.repository.publish_definition(config, canonical_checksum(config))

    async def list_definitions(self) -> list[DefinitionRecord]:
        return await self.repository.list_definitions()

    async def get_definition(self, identifier: str) -> DefinitionRecord:
        definition = await self.repository.get_definition(identifier)
        if definition is None:
            raise CollectionNotFoundError(f"collection definition {identifier!r} was not found")
        return definition

    async def estimate(self, identifier: str) -> CostEstimate:
        definition = await self.get_definition(identifier)
        return (await self.planner.plan(definition.config)).estimate

    async def estimate_config(self, config: JsonObject) -> CostEstimate:
        validate_instance(
            self.schema_root,
            "collection-definition.schema.json",
            config,
            label="collection definition",
        )
        _validate_schedule(config)
        return (await self.planner.plan(config)).estimate

    async def create_run(
        self,
        identifier: str,
        *,
        trigger_type: str = "manual",
        schedule_id: str | None = None,
        scheduled_for: datetime | None = None,
    ) -> RunRecord:
        definition = await self.get_definition(identifier)
        plan = await self.planner.plan(definition.config)
        try:
            return await self.repository.create_run(
                definition,
                plan,
                trigger_type=trigger_type,
                schedule_id=schedule_id,
                scheduled_for=scheduled_for,
            )
        except BudgetExceededError as exc:
            raise CollectionBudgetError(str(exc)) from exc

    async def get_run(self, run_id: str) -> RunRecord:
        run = await self.repository.get_run(run_id)
        if run is None:
            raise CollectionNotFoundError(f"collection run {run_id!r} was not found")
        return run

    async def list_tasks(self, run_id: str, limit: int = 200) -> list[QueueTask]:
        await self.get_run(run_id)
        return await self.repository.list_tasks(run_id, limit)

    async def usage(self, run_id: str) -> RunUsage:
        usage = await self.repository.usage(run_id)
        if usage is None:
            raise CollectionNotFoundError(f"collection run {run_id!r} was not found")
        return usage

    async def monitor(self, run_id: str) -> RunMonitor:
        monitor = await self.repository.monitor(run_id)
        if monitor is None:
            raise CollectionNotFoundError(f"collection run {run_id!r} was not found")
        return monitor

    async def cancel_run(self, run_id: str) -> RunRecord:
        run = await self.repository.cancel_run(run_id)
        if run is None:
            raise CollectionNotFoundError(f"collection run {run_id!r} was not found")
        return run

    async def retry_failed(self, run_id: str) -> int:
        await self.get_run(run_id)
        return await self.repository.retry_failed(run_id)
