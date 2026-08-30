from __future__ import annotations

import asyncio
import csv
import json
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import pytest

from rci_locations import (
    EligibilityReconciler,
    InMemoryLocationRepository,
    LocationImporter,
    RetailerCatalog,
)
from rci_locations.eligibility import plan_as_json, plan_from_json
from rci_locations.eligibility_cli import run_reconciliation
from rci_locations.importer import EXPECTED_COLUMNS, transform_row
from rci_locations.models import EligibilityReconciliationPlan, LocationRecord

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
CATALOG_PATH = REPOSITORY_ROOT / "config" / "retailer-catalog.json"


def _row(*, store_number: str, status: str = "active") -> dict[str, str]:
    row = {column: "" for column in EXPECTED_COLUMNS}
    row.update(
        {
            "Store_No": store_number,
            "Name": "Kroger test store",
            "Zip_Code": "48160",
            "Provider": "kroger",
            "Status": status,
            "Country": "USA",
            "mc_location_id": f"mc-{store_number}",
        }
    )
    return row


async def _repository_with_stale_kroger_rows() -> InMemoryLocationRepository:
    catalog = RetailerCatalog.from_path(CATALOG_PATH)
    padded, _ = transform_row(_row(store_number="01800576"), catalog)
    unpadded, _ = transform_row(_row(store_number="1800576"), catalog)
    superseded, _ = transform_row(
        _row(store_number="03500995", status="superseded"),
        catalog,
    )
    repository = InMemoryLocationRepository()
    await repository.upsert_locations(
        "seed-import",
        [
            padded,
            replace(
                unpadded,
                collection_eligible=True,
                collection_eligibility_reason=None,
            ),
            replace(
                superseded,
                collection_eligibility_reason="superseded_by_authoritative_import",
            ),
        ],
    )
    return repository


async def test_reconciliation_dry_run_is_catalog_driven_and_read_only() -> None:
    repository = await _repository_with_stale_kroger_rows()
    reconciler = EligibilityReconciler(
        repository,
        RetailerCatalog.from_path(CATALOG_PATH),
        catalog_path=CATALOG_PATH,
    )

    plan = await reconciler.plan(retailer_ids={"kroger_us"})

    assert plan.scanned_rows == 3
    assert plan.changed_rows == 1
    assert plan.eligible_before == 2
    assert plan.eligible_after == 1
    assert plan.enabled_rows == 0
    assert plan.disabled_rows == 1
    assert plan.changes[0].store_number == "1800576"
    assert plan.changes[0].after_reason == "store_number_not_provider_safe"
    assert plan.audit_run_id is None
    assert plan_as_json(plan)["mode"] == "dry_run"
    assert repository.eligibility_reconciliations == {}
    assert await repository.count_locations("kroger_us") == 2


async def test_reviewed_plan_round_trips_and_rejects_tampering() -> None:
    repository = await _repository_with_stale_kroger_rows()
    reconciler = EligibilityReconciler(
        repository,
        RetailerCatalog.from_path(CATALOG_PATH),
        catalog_path=CATALOG_PATH,
    )
    plan = await reconciler.plan(retailer_ids={"kroger_us"})
    document = plan_as_json(plan)

    assert plan_from_json(document) == plan
    assert plan_from_json(json.loads(json.dumps(document))) == plan

    tampered = json.loads(json.dumps(document))
    tampered["changed_rows"] += 1
    with pytest.raises(ValueError, match="checksum does not match"):
        plan_from_json(tampered)

    already_applied = plan_as_json(replace(plan, audit_run_id="audit-run"))
    with pytest.raises(ValueError, match="unapplied dry-run"):
        plan_from_json(already_applied)


async def test_apply_cli_requires_reviewed_artifact_and_cannot_override_scope(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="--reviewed-plan is required"):
        await run_reconciliation(
            catalog_path=CATALOG_PATH,
            retailer_ids=set(),
            apply=True,
            requested_by="owner",
            change_reason="test",
            reviewed_plan_path=None,
            output=None,
        )

    with pytest.raises(ValueError, match="--retailer cannot override"):
        await run_reconciliation(
            catalog_path=CATALOG_PATH,
            retailer_ids={"kroger_us"},
            apply=True,
            requested_by="owner",
            change_reason="test",
            reviewed_plan_path=tmp_path / "reviewed.json",
            output=None,
        )


async def test_reconciliation_apply_is_audited_idempotent_and_preserves_lifecycle_reason() -> None:
    repository = await _repository_with_stale_kroger_rows()
    reconciler = EligibilityReconciler(
        repository,
        RetailerCatalog.from_path(CATALOG_PATH),
        catalog_path=CATALOG_PATH,
    )
    plan = plan_from_json(plan_as_json(await reconciler.plan(retailer_ids={"kroger_us"})))

    applied = await reconciler.apply(
        plan,
        requested_by="platform-owner",
        change_reason="Require canonical provider eight-digit Kroger store IDs",
    )

    assert applied.audit_run_id is not None
    assert plan_as_json(applied)["mode"] == "apply"
    audit = repository.eligibility_reconciliations[applied.audit_run_id]
    assert audit["status"] == "completed"
    assert audit["requested_by"] == "platform-owner"
    assert audit["reviewed_plan_sha256"] == plan_as_json(plan)["plan_sha256"]
    assert await repository.count_locations("kroger_us") == 1
    superseded = next(
        location
        for location in repository.locations.values()
        if location.store_number == "03500995"
    )
    assert superseded.collection_eligibility_reason == "superseded_by_authoritative_import"

    second_plan = await reconciler.plan(retailer_ids={"kroger_us"})
    assert second_plan.changed_rows == 0
    assert second_plan.eligible_before == second_plan.eligible_after == 1


async def test_reconciliation_apply_rejects_stale_snapshot_and_records_failure() -> None:
    class ConcurrentChangeRepository(InMemoryLocationRepository):
        async def apply_eligibility_reconciliation(
            self,
            audit_run_id: str,
            plan: EligibilityReconciliationPlan,
        ) -> None:
            identity = next(iter(self.locations))
            self.locations[identity] = replace(
                self.locations[identity],
                status="temporarily_closed",
            )
            await super().apply_eligibility_reconciliation(audit_run_id, plan)

    seeded = await _repository_with_stale_kroger_rows()
    repository = ConcurrentChangeRepository()
    repository.locations.update(seeded.locations)
    repository.location_import_ids.update(seeded.location_import_ids)
    reconciler = EligibilityReconciler(
        repository,
        RetailerCatalog.from_path(CATALOG_PATH),
        catalog_path=CATALOG_PATH,
    )
    plan = await reconciler.plan(retailer_ids={"kroger_us"})

    with pytest.raises(RuntimeError, match="snapshot changed after dry run"):
        await reconciler.apply(
            plan,
            requested_by="platform-owner",
            change_reason="test optimistic reconciliation guard",
        )

    audit = next(iter(repository.eligibility_reconciliations.values()))
    assert audit["status"] == "failed"
    assert "snapshot changed" in str(audit["error_message"])


async def test_reconciliation_rejects_unknown_retailer_and_anonymous_apply() -> None:
    repository = await _repository_with_stale_kroger_rows()
    reconciler = EligibilityReconciler(
        repository,
        RetailerCatalog.from_path(CATALOG_PATH),
        catalog_path=CATALOG_PATH,
    )

    with pytest.raises(ValueError, match="not catalogued"):
        await reconciler.plan(retailer_ids={"not-a-retailer"})

    plan = await reconciler.plan(retailer_ids={"kroger_us"})
    with pytest.raises(ValueError, match="requested_by is required"):
        await reconciler.apply(plan, requested_by=" ", change_reason="reason")
    with pytest.raises(ValueError, match="change_reason is required"):
        await reconciler.apply(plan, requested_by="owner", change_reason=" ")

    tampered = replace(plan, eligible_after=plan.eligible_after + 1)
    with pytest.raises(ValueError, match="current catalog-derived dry run"):
        await reconciler.apply(
            tampered,
            requested_by="owner",
            change_reason="must reject a modified plan",
        )


async def test_import_and_reconciliation_share_one_whole_operation_lock(
    tmp_path: Path,
) -> None:
    class PausedImportRepository(InMemoryLocationRepository):
        def __init__(self) -> None:
            super().__init__()
            self.import_write_reached = asyncio.Event()
            self.allow_import_write = asyncio.Event()

        async def upsert_locations(
            self,
            import_id: str,
            locations: Sequence[LocationRecord],
        ) -> None:
            if import_id != "seed-import":
                self.import_write_reached.set()
                await self.allow_import_write.wait()
            await super().upsert_locations(import_id, locations)

    seeded = await _repository_with_stale_kroger_rows()
    repository = PausedImportRepository()
    repository.locations.update(seeded.locations)
    repository.location_import_ids.update(seeded.location_import_ids)
    catalog = RetailerCatalog.from_path(CATALOG_PATH)
    reconciler = EligibilityReconciler(repository, catalog, catalog_path=CATALOG_PATH)
    reviewed_plan = await reconciler.plan(retailer_ids={"kroger_us"})

    source = tmp_path / "kroger.csv"
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=sorted(EXPECTED_COLUMNS))
        writer.writeheader()
        writer.writerow(_row(store_number="1800576"))

    import_task = asyncio.create_task(LocationImporter(repository, catalog).import_file(source))
    await asyncio.wait_for(repository.import_write_reached.wait(), timeout=1)
    apply_task = asyncio.create_task(
        reconciler.apply(
            reviewed_plan,
            requested_by="platform-owner",
            change_reason="prove import/apply mutual exclusion",
        )
    )
    await asyncio.sleep(0)
    assert not apply_task.done()
    assert repository.eligibility_reconciliations == {}

    repository.allow_import_write.set()
    await asyncio.wait_for(import_task, timeout=1)
    with pytest.raises(ValueError, match="reviewed plan no longer matches"):
        await asyncio.wait_for(apply_task, timeout=1)
    assert repository.eligibility_reconciliations == {}
