"""Catalog-driven reconciliation of persisted location eligibility."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from rci_locations.catalog import RetailerCatalog
from rci_locations.models import (
    EligibilityReconciliationPlan,
    LocationEligibilityChange,
    LocationEligibilityState,
)
from rci_locations.ports import LocationEligibilityRepository

PRESERVED_LIFECYCLE_REASONS = frozenset({"superseded_by_authoritative_import"})
PLAN_SCHEMA_VERSION = "location-eligibility-plan/v1"


def file_sha256(source: Path) -> str:
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def eligibility_snapshot_sha256(states: list[LocationEligibilityState]) -> str:
    """Fingerprint every persisted decision input so apply cannot use a stale dry run."""

    payload = [
        {
            "collection_eligibility_reason": state.collection_eligibility_reason,
            "collection_eligible": state.collection_eligible,
            "id": state.id,
            "retailer_id": state.retailer_id,
            "status": state.status,
            "store_number": state.store_number,
        }
        for state in sorted(states, key=lambda item: item.id)
    ]
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _plan_payload(plan: EligibilityReconciliationPlan) -> dict[str, Any]:
    payload = asdict(plan)
    # The reviewed plan is the immutable decision proposal. The later audit ID
    # identifies its execution and therefore must not change the proposal hash.
    payload["audit_run_id"] = None
    return payload


def eligibility_plan_sha256(plan: EligibilityReconciliationPlan) -> str:
    """Fingerprint the complete reviewed proposal independently of its execution."""

    encoded = json.dumps(
        _plan_payload(plan),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def plan_as_json(plan: EligibilityReconciliationPlan) -> dict[str, object]:
    """Return the complete machine-auditable dry-run/apply document."""

    document: dict[str, object] = asdict(plan)
    document["retailer_ids"] = list(plan.retailer_ids)
    document["changes"] = [asdict(change) for change in plan.changes]
    document["mode"] = "apply" if plan.audit_run_id else "dry_run"
    document["plan_schema_version"] = PLAN_SCHEMA_VERSION
    document["plan_sha256"] = eligibility_plan_sha256(plan)
    return document


def _require_int(value: object, *, field: str) -> int:
    if type(value) is not int:
        raise ValueError(f"reviewed plan {field} must be an integer")
    return value


def _require_optional_string(value: object, *, field: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise ValueError(f"reviewed plan {field} must be a string or null")
    return value


def _reason_counts_from_json(value: object, *, field: str) -> dict[str, int]:
    if not isinstance(value, dict):
        raise ValueError(f"reviewed plan {field} must be an object")
    counts: dict[str, int] = {}
    for reason, count in value.items():
        if not isinstance(reason, str):
            raise ValueError(f"reviewed plan {field} keys must be strings")
        parsed_count = _require_int(count, field=f"{field}.{reason}")
        if parsed_count < 0:
            raise ValueError(f"reviewed plan {field}.{reason} must be non-negative")
        counts[reason] = parsed_count
    return counts


def plan_from_json(document: object) -> EligibilityReconciliationPlan:
    """Load a reviewed dry-run artifact without coercing identifiers or counts."""

    if not isinstance(document, dict):
        raise ValueError("reviewed plan must be a JSON object")
    expected_keys = {
        "audit_run_id",
        "catalog_path",
        "catalog_sha256",
        "snapshot_sha256",
        "retailer_ids",
        "scanned_rows",
        "changed_rows",
        "eligible_before",
        "eligible_after",
        "enabled_rows",
        "disabled_rows",
        "reason_counts_before",
        "reason_counts_after",
        "changes",
        "mode",
        "plan_schema_version",
        "plan_sha256",
    }
    if set(document) != expected_keys:
        missing = sorted(expected_keys - set(document))
        unexpected = sorted(set(document) - expected_keys)
        raise ValueError(
            "reviewed plan fields do not match the supported contract: "
            f"missing={missing}, unexpected={unexpected}"
        )
    if document["plan_schema_version"] != PLAN_SCHEMA_VERSION:
        raise ValueError("reviewed plan schema version is not supported")
    if document["mode"] != "dry_run" or document["audit_run_id"] is not None:
        raise ValueError("--apply requires an unapplied dry-run plan artifact")

    retailer_ids_value = document["retailer_ids"]
    if not isinstance(retailer_ids_value, list) or not all(
        isinstance(value, str) for value in retailer_ids_value
    ):
        raise ValueError("reviewed plan retailer_ids must be a string array")
    retailer_ids = tuple(retailer_ids_value)
    if retailer_ids != tuple(sorted(set(retailer_ids))):
        raise ValueError("reviewed plan retailer_ids must be unique and sorted")

    changes_value = document["changes"]
    if not isinstance(changes_value, list):
        raise ValueError("reviewed plan changes must be an array")
    change_keys = {
        "id",
        "retailer_id",
        "store_number",
        "status",
        "before_eligible",
        "before_reason",
        "after_eligible",
        "after_reason",
    }
    changes: list[LocationEligibilityChange] = []
    for index, value in enumerate(changes_value):
        if not isinstance(value, dict) or set(value) != change_keys:
            raise ValueError(f"reviewed plan changes[{index}] has invalid fields")
        for field in ("id", "retailer_id", "store_number"):
            if not isinstance(value[field], str) or not value[field]:
                raise ValueError(f"reviewed plan changes[{index}].{field} must be a string")
        for field in ("before_eligible", "after_eligible"):
            if type(value[field]) is not bool:
                raise ValueError(f"reviewed plan changes[{index}].{field} must be a boolean")
        changes.append(
            LocationEligibilityChange(
                id=value["id"],
                retailer_id=value["retailer_id"],
                store_number=value["store_number"],
                status=_require_optional_string(value["status"], field=f"changes[{index}].status"),
                before_eligible=value["before_eligible"],
                before_reason=_require_optional_string(
                    value["before_reason"], field=f"changes[{index}].before_reason"
                ),
                after_eligible=value["after_eligible"],
                after_reason=_require_optional_string(
                    value["after_reason"], field=f"changes[{index}].after_reason"
                ),
            )
        )

    string_fields = ("catalog_path", "catalog_sha256", "snapshot_sha256", "plan_sha256")
    for field in string_fields:
        if not isinstance(document[field], str) or not document[field]:
            raise ValueError(f"reviewed plan {field} must be a string")
    plan = EligibilityReconciliationPlan(
        catalog_path=document["catalog_path"],
        catalog_sha256=document["catalog_sha256"],
        snapshot_sha256=document["snapshot_sha256"],
        retailer_ids=retailer_ids,
        scanned_rows=_require_int(document["scanned_rows"], field="scanned_rows"),
        changed_rows=_require_int(document["changed_rows"], field="changed_rows"),
        eligible_before=_require_int(document["eligible_before"], field="eligible_before"),
        eligible_after=_require_int(document["eligible_after"], field="eligible_after"),
        enabled_rows=_require_int(document["enabled_rows"], field="enabled_rows"),
        disabled_rows=_require_int(document["disabled_rows"], field="disabled_rows"),
        reason_counts_before=_reason_counts_from_json(
            document["reason_counts_before"], field="reason_counts_before"
        ),
        reason_counts_after=_reason_counts_from_json(
            document["reason_counts_after"], field="reason_counts_after"
        ),
        changes=tuple(changes),
    )
    if document["plan_sha256"] != eligibility_plan_sha256(plan):
        raise ValueError("reviewed plan checksum does not match its contents")
    return plan


def _reason_counts(
    decisions: list[tuple[bool, str | None]],
) -> dict[str, int]:
    counts = Counter(
        reason or "missing_ineligibility_reason" for eligible, reason in decisions if not eligible
    )
    return dict(sorted(counts.items()))


class EligibilityReconciler:
    """Dry-run first; apply only an unchanged, catalog-evaluated snapshot."""

    def __init__(
        self,
        repository: LocationEligibilityRepository,
        catalog: RetailerCatalog,
        *,
        catalog_path: Path,
    ) -> None:
        self._repository = repository
        self._catalog = catalog
        self._catalog_path = catalog_path.resolve()
        self._catalog_sha256 = file_sha256(self._catalog_path)

    async def plan(
        self,
        *,
        retailer_ids: set[str] | None = None,
    ) -> EligibilityReconciliationPlan:
        selected = tuple(sorted(retailer_ids or set()))
        unknown = set(selected) - self._catalog.retailer_ids()
        if unknown:
            raise ValueError(f"retailer IDs are not catalogued: {sorted(unknown)}")

        states = await self._repository.list_location_eligibility_states(selected)
        changes: list[LocationEligibilityChange] = []
        after_decisions: list[tuple[bool, str | None]] = []

        for state in states:
            after_eligible, after_reason = self._catalog.collection_eligibility_for_retailer_id(
                state.retailer_id,
                store_number=state.store_number,
                status=state.status,
            )
            if (
                not after_eligible
                and state.collection_eligibility_reason in PRESERVED_LIFECYCLE_REASONS
            ):
                after_reason = state.collection_eligibility_reason
            after_decisions.append((after_eligible, after_reason))
            if (
                after_eligible != state.collection_eligible
                or after_reason != state.collection_eligibility_reason
            ):
                changes.append(
                    LocationEligibilityChange(
                        id=state.id,
                        retailer_id=state.retailer_id,
                        store_number=state.store_number,
                        status=state.status,
                        before_eligible=state.collection_eligible,
                        before_reason=state.collection_eligibility_reason,
                        after_eligible=after_eligible,
                        after_reason=after_reason,
                    )
                )

        before_decisions = [
            (state.collection_eligible, state.collection_eligibility_reason) for state in states
        ]
        eligible_before = sum(eligible for eligible, _ in before_decisions)
        eligible_after = sum(eligible for eligible, _ in after_decisions)
        enabled_rows = sum(
            not change.before_eligible and change.after_eligible for change in changes
        )
        disabled_rows = sum(
            change.before_eligible and not change.after_eligible for change in changes
        )
        return EligibilityReconciliationPlan(
            catalog_path=str(self._catalog_path),
            catalog_sha256=self._catalog_sha256,
            snapshot_sha256=eligibility_snapshot_sha256(states),
            retailer_ids=selected,
            scanned_rows=len(states),
            changed_rows=len(changes),
            eligible_before=eligible_before,
            eligible_after=eligible_after,
            enabled_rows=enabled_rows,
            disabled_rows=disabled_rows,
            reason_counts_before=_reason_counts(before_decisions),
            reason_counts_after=_reason_counts(after_decisions),
            changes=tuple(changes),
        )

    async def apply(
        self,
        plan: EligibilityReconciliationPlan,
        *,
        requested_by: str,
        change_reason: str,
    ) -> EligibilityReconciliationPlan:
        actor = requested_by.strip()
        reason = change_reason.strip()
        if not actor:
            raise ValueError("requested_by is required when applying eligibility changes")
        if not reason:
            raise ValueError("change_reason is required when applying eligibility changes")
        if plan.audit_run_id is not None:
            raise ValueError("an applied reconciliation plan cannot be applied again")
        if plan.catalog_sha256 != self._catalog_sha256:
            raise ValueError("reconciliation plan catalog checksum does not match this catalog")
        async with self._repository.location_policy_operation_lock():
            fresh_plan = await self.plan(retailer_ids=set(plan.retailer_ids) or None)
            if fresh_plan != plan:
                raise ValueError(
                    "reviewed plan no longer matches the current catalog-derived dry run"
                )

            audit_run_id = await self._repository.begin_eligibility_reconciliation(
                plan,
                requested_by=actor,
                change_reason=reason,
            )
            try:
                await self._repository.apply_eligibility_reconciliation(
                    audit_run_id,
                    plan,
                )
            except Exception as exc:
                await self._repository.fail_eligibility_reconciliation(
                    audit_run_id,
                    str(exc),
                )
                raise
        return replace(plan, audit_run_id=audit_run_id)
