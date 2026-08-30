"""Persistence ports used by the importer and read APIs."""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from typing import Protocol

from rci_locations.models import (
    EligibilityReconciliationPlan,
    ImportState,
    ImportSummary,
    LocationEligibilityState,
    LocationRecord,
    LocationSearchResult,
    RetailerAlias,
    RetailerCount,
    RetailerDefinition,
)


class LocationPolicyOperationRepository(Protocol):
    def location_policy_operation_lock(self) -> AbstractAsyncContextManager[None]: ...


class LocationRepository(LocationPolicyOperationRepository, Protocol):
    async def begin_import(self, source_path: str, source_sha256: str) -> str: ...

    async def upsert_retailers(
        self,
        retailers: Sequence[RetailerDefinition],
        aliases: Sequence[RetailerAlias],
    ) -> None: ...

    async def upsert_locations(
        self, import_id: str, locations: Sequence[LocationRecord]
    ) -> None: ...

    async def retire_missing_locations(
        self, import_id: str, retailer_ids: Sequence[str]
    ) -> None: ...

    async def update_import_progress(
        self,
        import_id: str,
        *,
        total_rows: int,
        imported_rows: int,
        skipped_rows: int,
        retailer_count: int,
    ) -> None: ...

    async def complete_import(self, summary: ImportSummary) -> None: ...

    async def fail_import(self, import_id: str, error_message: str) -> None: ...


class LocationReadRepository(Protocol):
    async def list_retailers(self, country: str | None = None) -> list[RetailerCount]: ...

    async def count_locations(self, retailer_id: str) -> int: ...

    async def search_locations(
        self,
        *,
        retailer_id: str | None,
        country: str | None,
        query: str | None,
        zipcode: str | None,
        limit: int,
        offset: int,
    ) -> list[LocationSearchResult]: ...

    async def list_imports(self, limit: int = 20) -> list[ImportState]: ...


class LocationEligibilityRepository(LocationPolicyOperationRepository, Protocol):
    async def list_location_eligibility_states(
        self,
        retailer_ids: Sequence[str],
    ) -> list[LocationEligibilityState]: ...

    async def begin_eligibility_reconciliation(
        self,
        plan: EligibilityReconciliationPlan,
        *,
        requested_by: str,
        change_reason: str,
    ) -> str: ...

    async def apply_eligibility_reconciliation(
        self,
        audit_run_id: str,
        plan: EligibilityReconciliationPlan,
    ) -> None: ...

    async def fail_eligibility_reconciliation(
        self,
        audit_run_id: str,
        error_message: str,
    ) -> None: ...
