"""Application service for collection definitions and runs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from rci_collections.geography import CollectionGeographyResolver
from rci_collections.models import (
    BudgetExceededError,
    CostEstimate,
    DefinitionRecord,
    GeographyResolution,
    JsonObject,
    QueueTask,
    RunMonitor,
    RunRecord,
    RunUsage,
    ScopeEstimateRecord,
)
from rci_collections.planner import CollectionPlanner, canonical_checksum
from rci_collections.ports import CollectionRepository
from rci_contracts import ContractError, validate_instance
from rci_core import CronExpressionError, CronSchedule


class CollectionNotFoundError(LookupError):
    pass


class CollectionBudgetError(ValueError):
    pass


class CollectionApprovalError(ValueError):
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
        geography_resolver: CollectionGeographyResolver | None = None,
    ) -> None:
        self.repository = repository
        self.planner = planner
        self.schema_root = schema_root
        self.geography_resolver = geography_resolver

    async def resolve_geography(self, request: JsonObject) -> GeographyResolution:
        if self.geography_resolver is None:
            raise RuntimeError("collection geography resolver is not configured")
        validate_instance(
            self.schema_root,
            "collection-geography-request.schema.json",
            request,
            label="collection geography request",
        )
        try:
            resolution = await self.geography_resolver.resolve(request)
        except ValueError as exc:
            raise ContractError(f"collection geography request: {exc}") from exc
        return await self.repository.save_geography_resolution(resolution)

    async def get_geography_resolution(self, resolution_id: str) -> GeographyResolution:
        resolution = await self.repository.get_geography_resolution(resolution_id)
        if resolution is None:
            raise CollectionNotFoundError(
                f"collection geography resolution {resolution_id!r} was not found"
            )
        return resolution

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

    async def create_scope_estimate(
        self,
        config: JsonObject,
        *,
        valid_for_minutes: int = 30,
    ) -> ScopeEstimateRecord:
        validate_instance(
            self.schema_root,
            "collection-definition.schema.json",
            config,
            label="collection definition",
        )
        _validate_schedule(config)
        geography = config.get("geography")
        if not isinstance(geography, dict) or geography.get("strategy") != "approved_resolution":
            raise ContractError(
                "collection definition: geography must reference an approved resolution"
            )
        resolution = await self.get_geography_resolution(str(geography["resolution_id"]))
        if str(geography["resolution_checksum"]) != resolution.checksum:
            raise ContractError("collection definition: geography checksum does not match")
        plan = await self.planner.plan(config)
        now = datetime.now(UTC)
        record = ScopeEstimateRecord(
            id=str(uuid4()),
            definition_id=str(config["id"]),
            resolution_id=resolution.id,
            configuration_checksum=canonical_checksum(config),
            geography_checksum=resolution.checksum,
            estimate=plan.estimate,
            expires_at=now + timedelta(minutes=valid_for_minutes),
            created_at=now,
        )
        return await self.repository.save_scope_estimate(record)

    async def launch_approved(self, config: JsonObject, estimate_id: str) -> RunRecord:
        estimate = await self.repository.get_scope_estimate(estimate_id)
        if estimate is None:
            raise CollectionApprovalError("the approved estimate was not found")
        now = datetime.now(UTC)
        expires_at = estimate.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= now:
            raise CollectionApprovalError("the approved estimate has expired; estimate again")
        configuration_checksum = canonical_checksum(config)
        if configuration_checksum != estimate.configuration_checksum:
            raise CollectionApprovalError(
                "the collection changed after approval; review a new estimate"
            )
        geography = config.get("geography")
        if not isinstance(geography, dict):
            raise CollectionApprovalError("the collection has no approved geography")
        if (
            str(geography.get("resolution_id")) != estimate.resolution_id
            or str(geography.get("resolution_checksum")) != estimate.geography_checksum
        ):
            raise CollectionApprovalError(
                "the geography changed after approval; review a new estimate"
            )
        plan = await self.planner.plan(config)
        if (
            plan.estimate.estimated_total_pages != estimate.estimate.estimated_total_pages
            or plan.estimate.estimated_total_credits != estimate.estimate.estimated_total_credits
        ):
            raise CollectionApprovalError(
                "the current plan no longer matches the approved estimate"
            )
        definition = await self.publish_definition(config)
        try:
            return await self.repository.create_run(definition, plan, scope_estimate_id=estimate.id)
        except BudgetExceededError as exc:
            raise CollectionBudgetError(str(exc)) from exc

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

    async def list_runs(self, limit: int = 50) -> list[RunRecord]:
        return await self.repository.list_runs(limit)

    async def list_tasks(
        self,
        run_id: str,
        limit: int = 200,
        *,
        retailer_id: str | None = None,
        status: str | None = None,
    ) -> list[QueueTask]:
        await self.get_run(run_id)
        return await self.repository.list_tasks(
            run_id,
            limit,
            retailer_id=retailer_id,
            status=status,
        )

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
        try:
            return await self.repository.retry_failed(run_id)
        except ValueError as exc:
            raise CollectionApprovalError(str(exc)) from exc
