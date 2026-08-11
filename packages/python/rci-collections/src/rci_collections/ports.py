"""Control-plane persistence ports."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from rci_collections.models import (
    CollectionPlan,
    DefinitionRecord,
    GeographyResolution,
    LocationFacet,
    LocationUnit,
    QueueTask,
    RawArtifact,
    RunMonitor,
    RunRecord,
    RunUsage,
    ScopeEstimateRecord,
    TaskSeed,
)


class LocationUniverseRepository(Protocol):
    async def list_location_units(
        self, retailer_ids: Sequence[str], country: str
    ) -> list[LocationUnit]: ...

    async def get_geography_resolution(self, resolution_id: str) -> GeographyResolution | None: ...

    async def list_location_facets(
        self,
        retailer_id: str,
        country: str,
        states: Sequence[str] = (),
    ) -> list[LocationFacet]: ...


class CollectionRepository(LocationUniverseRepository, Protocol):
    async def save_geography_resolution(
        self, resolution: GeographyResolution
    ) -> GeographyResolution: ...

    async def save_scope_estimate(self, estimate: ScopeEstimateRecord) -> ScopeEstimateRecord: ...

    async def get_scope_estimate(self, estimate_id: str) -> ScopeEstimateRecord | None: ...
    async def publish_definition(
        self, config: dict[str, object], checksum: str
    ) -> DefinitionRecord: ...

    async def list_definitions(self) -> list[DefinitionRecord]: ...

    async def get_definition(self, identifier: str) -> DefinitionRecord | None: ...

    async def create_run(
        self,
        definition: DefinitionRecord,
        plan: CollectionPlan,
        *,
        trigger_type: str = "manual",
        schedule_id: str | None = None,
        scheduled_for: datetime | None = None,
        scope_estimate_id: str | None = None,
    ) -> RunRecord: ...

    async def get_run(self, run_id: str) -> RunRecord | None: ...

    async def list_runs(self, limit: int = 50) -> list[RunRecord]: ...

    async def list_tasks(
        self,
        run_id: str,
        limit: int = 200,
        *,
        retailer_id: str | None = None,
        status: str | None = None,
    ) -> list[QueueTask]: ...

    async def usage(self, run_id: str) -> RunUsage | None: ...

    async def monitor(self, run_id: str) -> RunMonitor | None: ...

    async def record_artifact(self, run_id: str, artifact: RawArtifact) -> str: ...

    async def claim_tasks(
        self, worker_id: str, *, claim_limit: int, lease_seconds: int
    ) -> list[QueueTask]: ...

    async def extend_lease(self, task_id: str, worker_id: str, lease_seconds: int) -> bool: ...

    async def complete_success(
        self,
        task_id: str,
        worker_id: str,
        *,
        http_status: int,
        result_count: int,
        next_task: TaskSeed | None,
        raw_artifact: RawArtifact | None = None,
    ) -> bool: ...

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
    ) -> bool: ...

    async def cancel_run(self, run_id: str) -> RunRecord | None: ...

    async def retry_failed(self, run_id: str) -> int: ...
