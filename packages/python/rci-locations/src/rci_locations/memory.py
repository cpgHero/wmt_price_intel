"""Deterministic in-memory repository used for unit tests and dry validation."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from rci_locations.eligibility import eligibility_plan_sha256, eligibility_snapshot_sha256
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


class InMemoryLocationRepository:
    def __init__(self) -> None:
        self.retailers: dict[str, RetailerDefinition] = {}
        self.aliases: dict[tuple[str, str], str] = {}
        self.locations: dict[tuple[str, str, str, str], LocationRecord] = {}
        self.location_import_ids: dict[tuple[str, str, str, str], str] = {}
        self.imports: dict[str, ImportState] = {}
        self.eligibility_reconciliations: dict[str, dict[str, object]] = {}
        self._location_policy_lock = asyncio.Lock()

    @asynccontextmanager
    async def location_policy_operation_lock(self) -> AsyncIterator[None]:
        async with self._location_policy_lock:
            yield

    async def begin_import(self, source_path: str, source_sha256: str) -> str:
        import_id = str(uuid4())
        self.imports[import_id] = ImportState(
            id=import_id,
            source_path=source_path,
            source_sha256=source_sha256,
            status="running",
            total_rows=0,
            imported_rows=0,
            skipped_rows=0,
            retailer_count=0,
            error_message=None,
            started_at=datetime.now(UTC),
            completed_at=None,
        )
        return import_id

    async def upsert_retailers(
        self,
        retailers: Sequence[RetailerDefinition],
        aliases: Sequence[RetailerAlias],
    ) -> None:
        for retailer in retailers:
            self.retailers[retailer.id] = retailer
        for alias in aliases:
            self.aliases[(alias.alias, alias.country)] = alias.retailer_id

    async def upsert_locations(
        self,
        import_id: str,
        locations: Sequence[LocationRecord],
    ) -> None:
        for location in locations:
            self.locations[location.identity] = location
            self.location_import_ids[location.identity] = import_id

    async def retire_missing_locations(self, import_id: str, retailer_ids: Sequence[str]) -> None:
        authoritative = set(retailer_ids)
        for identity, location in list(self.locations.items()):
            if (
                location.retailer_id in authoritative
                and self.location_import_ids.get(identity) != import_id
            ):
                self.locations[identity] = replace(
                    location,
                    status="superseded",
                    collection_eligible=False,
                    collection_eligibility_reason="superseded_by_authoritative_import",
                )

    async def complete_import(self, summary: ImportSummary) -> None:
        state = self.imports[summary.import_id]
        self.imports[summary.import_id] = replace(
            state,
            status="completed",
            total_rows=summary.total_rows,
            imported_rows=summary.imported_rows,
            skipped_rows=summary.skipped_rows,
            retailer_count=summary.retailer_count,
            completed_at=datetime.now(UTC),
        )

    async def update_import_progress(
        self,
        import_id: str,
        *,
        total_rows: int,
        imported_rows: int,
        skipped_rows: int,
        retailer_count: int,
    ) -> None:
        state = self.imports[import_id]
        self.imports[import_id] = replace(
            state,
            total_rows=total_rows,
            imported_rows=imported_rows,
            skipped_rows=skipped_rows,
            retailer_count=retailer_count,
        )

    async def fail_import(self, import_id: str, error_message: str) -> None:
        state = self.imports[import_id]
        self.imports[import_id] = replace(
            state,
            status="failed",
            error_message=error_message,
            completed_at=datetime.now(UTC),
        )

    async def list_retailers(self, country: str | None = None) -> list[RetailerCount]:
        counts: dict[str, int] = {}
        for location in self.locations.values():
            if not location.collection_eligible:
                continue
            counts[location.retailer_id] = counts.get(location.retailer_id, 0) + 1
        return [
            RetailerCount(
                id=retailer.id,
                display_name=retailer.display_name,
                country=retailer.country,
                active=retailer.active,
                catalogued=retailer.catalogued,
                location_count=counts.get(retailer.id, 0),
            )
            for retailer in sorted(self.retailers.values(), key=lambda item: item.id)
            if country is None or retailer.country == country
        ]

    async def count_locations(self, retailer_id: str) -> int:
        return sum(
            location.retailer_id == retailer_id and location.collection_eligible
            for location in self.locations.values()
        )

    async def search_locations(
        self,
        *,
        retailer_id: str | None,
        country: str | None,
        query: str | None,
        zipcode: str | None,
        limit: int,
        offset: int,
    ) -> list[LocationSearchResult]:
        normalized_query = query.casefold() if query else None
        matches = []
        for index, location in enumerate(self.locations.values()):
            if not location.collection_eligible:
                continue
            if retailer_id is not None and location.retailer_id != retailer_id:
                continue
            if country is not None and location.country != country:
                continue
            if zipcode is not None and location.zipcode != zipcode:
                continue
            haystack = " ".join(
                value or ""
                for value in (
                    location.store_number,
                    location.store_name,
                    location.city,
                    location.state,
                    location.address,
                )
            ).casefold()
            if normalized_query is not None and normalized_query not in haystack:
                continue
            matches.append(
                LocationSearchResult(
                    id=f"memory-{index}",
                    retailer_id=location.retailer_id,
                    provider=location.provider,
                    provider_location_id=location.provider_location_id,
                    store_number=location.store_number,
                    store_name=location.store_name,
                    raw_zipcode=location.raw_zipcode,
                    zipcode=location.zipcode,
                    city=location.city,
                    state=location.state,
                    country=location.country,
                    latitude=location.latitude,
                    longitude=location.longitude,
                )
            )
        return matches[offset : offset + limit]

    async def list_imports(self, limit: int = 20) -> list[ImportState]:
        return sorted(self.imports.values(), key=lambda item: item.started_at, reverse=True)[:limit]

    async def list_location_eligibility_states(
        self,
        retailer_ids: Sequence[str],
    ) -> list[LocationEligibilityState]:
        selected = set(retailer_ids)
        states = [
            LocationEligibilityState(
                id="|".join(identity),
                retailer_id=location.retailer_id,
                store_number=location.store_number,
                status=location.status,
                collection_eligible=location.collection_eligible,
                collection_eligibility_reason=location.collection_eligibility_reason,
            )
            for identity, location in self.locations.items()
            if not selected or location.retailer_id in selected
        ]
        return sorted(states, key=lambda item: item.id)

    async def begin_eligibility_reconciliation(
        self,
        plan: EligibilityReconciliationPlan,
        *,
        requested_by: str,
        change_reason: str,
    ) -> str:
        audit_run_id = str(uuid4())
        self.eligibility_reconciliations[audit_run_id] = {
            "status": "running",
            "plan": plan,
            "requested_by": requested_by,
            "change_reason": change_reason,
            "reviewed_plan_sha256": eligibility_plan_sha256(plan),
            "error_message": None,
        }
        return audit_run_id

    async def apply_eligibility_reconciliation(
        self,
        audit_run_id: str,
        plan: EligibilityReconciliationPlan,
    ) -> None:
        current = await self.list_location_eligibility_states(plan.retailer_ids)
        if eligibility_snapshot_sha256(current) != plan.snapshot_sha256:
            raise RuntimeError(
                "location eligibility snapshot changed after dry run; rerun reconciliation"
            )

        by_id = {"|".join(identity): identity for identity in self.locations}
        for change in plan.changes:
            identity = by_id[change.id]
            location = self.locations[identity]
            if (
                location.status != change.status
                or location.collection_eligible != change.before_eligible
                or location.collection_eligibility_reason != change.before_reason
            ):
                raise RuntimeError("location eligibility update no longer matches audited plan")
            self.locations[identity] = replace(
                location,
                collection_eligible=change.after_eligible,
                collection_eligibility_reason=change.after_reason,
            )
        self.eligibility_reconciliations[audit_run_id]["status"] = "completed"

    async def fail_eligibility_reconciliation(
        self,
        audit_run_id: str,
        error_message: str,
    ) -> None:
        self.eligibility_reconciliations[audit_run_id]["status"] = "failed"
        self.eligibility_reconciliations[audit_run_id]["error_message"] = error_message[:4_000]
