"""Immutable failure-only recovery selection and composite evidence assembly."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from rci_collections.models import TRANSIENT_NONBILLABLE_FAILURE_CLASSES
from rci_collections.planner import canonical_checksum
from rci_collections.request_contract import build_effective_provider_request

SELECTION_POLICY_VERSION = "failure-only-v1"
CONTINUATION_SELECTION_POLICY_VERSION = "unresolved-continuation-v1"
ASSEMBLY_POLICY_VERSION = "composite-evidence-v1"
SCOPE_PROJECTION_POLICY_VERSION = "collection-scope-projection-v1"
MINIMUM_CONCLUSIVE_COVERAGE = 0.95
MAXIMUM_CONTINUATION_TASKS = 50_000
SEARCH_CREDIT_UNIT_COST_USD = Decimal("0.002000")
MATERIALIZATION_WRITE_BATCH_SIZE = 1_000

SelectionReason = Literal[
    "failed_gate_scope",
    "cancelled_gate_scope",
    "blocking_failure",
    "transient_gap",
]
BindingMode = Literal["exact", "legacy_operational_adoption"]
RecoveryPlanMode = Literal["exact_launch", "legacy_adoption"]
ScopeProjectionKind = Literal["canonical_alias_collapse", "limited_provider_footprint"]
ScopeProjectionDisposition = Literal["scoreable", "unavailable"]
EvidenceOutcome = Literal[
    "usable_success",
    "retained_billable_404",
    "zero_credit_missing",
    "contract_missing",
    "quarantined",
]
type TaskMapping = Mapping[Any, Any] | RowMapping


@dataclass(frozen=True, slots=True)
class RecoverySelectionItem:
    source_task_id: str
    retailer_id: str
    canonical_request_key: str
    selection_reason: SelectionReason
    required_for_assembly: bool
    credits_per_success: int
    maximum_credits: int
    source_snapshot: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RetailerRecoverySummary:
    retailer_id: str
    selected_tasks: int
    required_tasks: int
    optional_transient_tasks: int
    maximum_provider_attempts: int
    maximum_credits: int
    reused_successes: int
    retained_billable_404s: int
    retained_billable_404_credits: int


@dataclass(frozen=True, slots=True)
class RecoverySelectionPreview:
    base_collection_run_id: str
    selection_policy_version: str
    selection_checksum: str
    base_snapshot_checksum: str
    selected_task_count: int
    maximum_provider_attempts: int
    maximum_credits: int
    retailers: tuple[RetailerRecoverySummary, ...]
    items: tuple[RecoverySelectionItem, ...]


@dataclass(frozen=True, slots=True)
class ScopeProjectionItem:
    source_task_id: str
    retailer_id: str
    canonical_request_key: str
    disposition: Literal["retained", "excluded"]
    reason: str
    mapped_retained_task_id: str | None
    source_snapshot: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ScopeProjectionPreview:
    base_collection_run_id: str
    retailer_id: str
    projection_kind: ScopeProjectionKind
    policy_version: str
    base_snapshot_checksum: str
    source_audit_id: str | None
    source_evidence_checksum: str
    raw_task_count: int
    retained_task_count: int
    excluded_task_count: int
    raw_location_count: int
    retained_location_count: int
    excluded_location_count: int
    raw_task_retention_ratio: str
    governed_coverage_ratio: str
    minimum_scoreable_coverage: str
    scorecard_disposition: ScopeProjectionDisposition
    projection_checksum: str
    manifest: dict[str, Any]
    items: tuple[ScopeProjectionItem, ...]


@dataclass(frozen=True, slots=True)
class ScopeProjectionRecord:
    id: str
    base_collection_run_id: str
    retailer_id: str
    projection_kind: str
    policy_version: str
    base_snapshot_checksum: str
    source_audit_id: str | None
    source_evidence_checksum: str
    raw_task_count: int
    retained_task_count: int
    excluded_task_count: int
    raw_location_count: int
    retained_location_count: int
    excluded_location_count: int
    raw_task_retention_ratio: str
    governed_coverage_ratio: str
    minimum_scoreable_coverage: str
    scorecard_disposition: str
    projection_checksum: str
    review_reason: str
    reviewed_by: str
    manifest: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ContinuationLineageComponent:
    recovery_plan_id: str
    recovery_collection_run_id: str
    continuation_of_recovery_plan_id: str | None
    continuation_depth: int
    selection_checksum: str
    selection_keys: tuple[str, ...]
    adopted_keys: tuple[str, ...]
    recovery_rows: tuple[TaskMapping, ...]


@dataclass(frozen=True, slots=True)
class ContinuationSelectionPreview:
    base_collection_run_id: str
    continuation_of_recovery_plan_id: str
    lineage_plan_ids: tuple[str, ...]
    lineage_checksum: str
    selection_policy_version: str
    selection_checksum: str
    base_snapshot_checksum: str
    selected_task_count: int
    maximum_provider_attempts: int
    maximum_credits: int
    resolved_before_count: int
    conclusive_before_count: int
    retained_success_count: int
    retained_billable_404_count: int
    retailers: tuple[RetailerRecoverySummary, ...]
    items: tuple[RecoverySelectionItem, ...]


@dataclass(frozen=True, slots=True)
class RecoveryPlanRecord:
    id: str
    base_collection_run_id: str
    recovery_collection_run_id: str | None
    recovery_batch_id: str | None
    plan_mode: str
    reservation_active: bool
    selection_policy_version: str
    selection_checksum: str
    base_snapshot_checksum: str
    scope_projection_id: str | None
    scope_projection_checksum: str | None
    selection_scope: dict[str, Any]
    plan_generation: int
    supersedes_recovery_plan_id: str | None
    continuation_of_recovery_plan_id: str | None
    continuation_depth: int
    selected_task_count: int
    maximum_credits: int
    approved_credit_ceiling: int
    reason: str
    approved_by: str
    status: str
    binding_manifest: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class CompositeInputSetRecord:
    id: str
    base_collection_run_id: str
    recovery_collection_run_ids: tuple[str, ...]
    assembly_generation: int
    manifest_checksum: str
    total_rows: int
    trust_state: str
    status: str
    analysis_run_id: str | None = None


@dataclass(frozen=True, slots=True)
class RecoveryBatchRecord:
    id: str
    organization_id: str
    spend_authorization_id: str
    phase_key: str
    inventory_checksum: str
    authorized_run_ids: tuple[str, ...]
    approved_credit_ceiling: int
    reserved_credits: int
    unit_cost_usd: str
    currency: str
    reason: str
    approved_by: str
    status: str
    created_at: datetime
    closed_at: datetime | None


@dataclass(frozen=True, slots=True)
class SpendAuthorizationRecord:
    id: str
    organization_id: str
    phase_key: str
    inventory_checksum: str
    authorized_run_ids: tuple[str, ...]
    approved_credit_ceiling: int
    unit_cost_usd: str
    currency: str
    reason: str
    authorized_by: str
    status: str
    created_at: datetime
    consumed_at: datetime | None


@dataclass(frozen=True, slots=True)
class RecoveryBatchInventoryRun:
    collection_run_id: str
    status: str
    actual_credits: int
    estimated_credits: int
    accounted_credits: int


@dataclass(frozen=True, slots=True)
class RecoveryBatchStatusRecord:
    batch: RecoveryBatchRecord
    accounted_credits: int
    remaining_credits: int
    approved_amount_usd: str
    accounted_amount_usd: str
    recovery_plan_count: int
    runs: tuple[RecoveryBatchInventoryRun, ...]


@dataclass(frozen=True, slots=True)
class RetailerUnavailabilityApprovalRecord:
    id: str
    base_collection_run_id: str
    retailer_id: str
    base_snapshot_checksum: str
    reason: str
    approved_by: str
    status: str
    created_at: datetime
    revoked_at: datetime | None
    revoked_by: str | None


@dataclass(frozen=True, slots=True)
class RecoveryBatchRunRecord:
    recovery_batch_id: str
    collection_run_id: str
    accounted_credits: int
    batch_accounted_credits: int


@dataclass(frozen=True, slots=True)
class RecoveryLaunchRecord:
    recovery_plan_id: str
    collection_run_id: str
    definition_version_id: str
    status: str
    task_count: int
    maximum_credits: int
    availability_gate_status: str
    reused_existing_run: bool


@dataclass(frozen=True, slots=True)
class ResolvedTaskEvidence:
    canonical_request_key: str
    selected_task_id: str
    selected_raw_artifact_id: str | None
    superseded_task_id: str | None
    evidence_outcome: EvidenceOutcome
    redundant_task_ids: tuple[str, ...]


def _approval_contract(
    row: TaskMapping,
    *,
    approved_credit_ceiling: int,
    reason: str,
    approved_by: str,
    recovery_batch_id: str | None,
    plan_mode: RecoveryPlanMode,
    supersedes_recovery_plan_id: str | None,
) -> bool:
    expected = {
        "approved_credit_ceiling": approved_credit_ceiling,
        "reason": reason.strip(),
        "approved_by": approved_by.strip(),
        "recovery_batch_id": recovery_batch_id,
        "plan_mode": plan_mode,
        "supersedes_recovery_plan_id": supersedes_recovery_plan_id,
    }
    actual = {
        "approved_credit_ceiling": int(row["approved_credit_ceiling"]),
        "reason": str(row["reason"]),
        "approved_by": str(row["approved_by"]),
        "recovery_batch_id": (
            str(row["recovery_batch_id"]) if row.get("recovery_batch_id") is not None else None
        ),
        "plan_mode": str(row["plan_mode"]),
        "supersedes_recovery_plan_id": (
            str(row["supersedes_recovery_plan_id"])
            if row.get("supersedes_recovery_plan_id") is not None
            else None
        ),
    }
    return actual == expected


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def effective_request_identity(row: TaskMapping) -> dict[str, Any]:
    """Normalize only fields that can change the outbound provider request.

    Run IDs, geography-row IDs, planning flags, and unrelated query metadata
    are excluded. ``adapter_id`` pins the endpoint and catalog defaults.
    Amazon's keyword/template pair is represented by the resolved URL because
    that is what the provider receives.
    """

    return build_effective_provider_request(row)


def outbound_query_contract(config: Mapping[str, Any]) -> dict[str, Any]:
    """Return query fields capable of changing any provider request.

    Administrative notes and labels intentionally do not affect legacy
    recovery compatibility.
    """

    query = config.get("query")
    if not isinstance(query, Mapping):
        return {}
    return {
        key: query[key]
        for key in ("keyword", "keywords", "amazon_same_day_url_template")
        if key in query
    }


def canonical_request_key(row: TaskMapping) -> str:
    """Return a run-independent identity for one exact provider request."""

    return canonical_checksum(effective_request_identity(row))


def request_identity_provenance(row: TaskMapping) -> dict[str, Any]:
    """Validate and disclose how a task's outbound identity was established.

    New tasks carry their immutable provider contract. Older tasks can only be
    reconstructed from the current catalog. For a successful legacy page, the
    provider artifact must corroborate the request method, path, and parameter
    names. Historical parameter/default values remain explicitly unproven.
    """

    provenance = str(row.get("_request_contract_provenance") or "frozen_task_contract")
    identity = effective_request_identity(row)
    if provenance == "frozen_task_contract":
        return {
            "mode": provenance,
            "verified_fields": ["frozen_provider_request_contract"],
            "unverified_fields": [],
        }
    if provenance != "reconstructed_current_catalog":
        raise ValueError(f"unsupported request identity provenance {provenance!r}")
    metadata = row.get("raw_artifact_metadata")
    if not isinstance(metadata, Mapping):
        raise ValueError("successful legacy evidence lacks provider artifact request metadata")
    actual_method = str(metadata.get("request_method") or "").upper()
    actual_path = str(metadata.get("request_path") or "")
    actual_parameter_names = sorted(
        str(value) for value in (metadata.get("request_parameter_names") or [])
    )
    expected_method = str(identity["method"]).upper()
    expected_path = str(identity["path"])
    expected_parameter_names = sorted(str(value) for value in dict(identity["params"]))
    if (
        actual_method != expected_method
        or actual_path != expected_path
        or actual_parameter_names != expected_parameter_names
    ):
        raise ValueError(
            "legacy provider artifact request metadata does not match the "
            "reconstructed current-catalog request identity"
        )
    return {
        "mode": provenance,
        "verified_fields": [
            "request_method",
            "request_path",
            "request_parameter_names",
        ],
        "unverified_fields": ["parameter_values", "historical_catalog_defaults"],
        "request_method": expected_method,
        "request_path": expected_path,
        "request_parameter_names": expected_parameter_names,
    }


def request_identity_provenance_manifest(
    components: Mapping[str, Sequence[TaskMapping]],
) -> dict[str, Any]:
    """Validate usable task identities and return a bounded audit summary."""

    records: list[dict[str, Any]] = []
    mode_counts: dict[str, int] = {}
    outcome_counts: dict[str, int] = {}
    for component, rows in sorted(components.items()):
        for row in rows:
            outcome = evidence_outcome(row)
            if outcome not in {"usable_success", "retained_billable_404"}:
                continue
            provenance = request_identity_provenance(row)
            mode = str(provenance["mode"])
            mode_counts[mode] = mode_counts.get(mode, 0) + 1
            outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1
            records.append(
                {
                    "component": component,
                    "task_id": str(row["id"]),
                    "canonical_request_key": canonical_request_key(row),
                    "evidence_outcome": outcome,
                    "provenance": provenance,
                }
            )
    return {
        "mode_counts": mode_counts,
        "outcome_counts": outcome_counts,
        "validated_conclusive_task_count": len(records),
        "validation_checksum": canonical_checksum({"records": records}),
        "reconstructed_current_catalog_checks": [
            "request_method",
            "request_path",
            "request_parameter_names",
        ],
        "reconstructed_current_catalog_unverified": [
            "parameter_values",
            "historical_catalog_defaults",
        ],
    }


def _is_retained_404(row: TaskMapping) -> bool:
    return (
        str(row["status"]) == "failed"
        and row.get("http_status") == 404
        and str(row.get("failure_class") or "") == "invalid_request"
        and int(row.get("billable_credits") or 0) > 0
    )


def _is_blocking_failure(row: TaskMapping) -> bool:
    if str(row["status"]) != "failed" or bool(row.get("is_preflight")):
        return False
    if _is_retained_404(row):
        return False
    return not (
        int(row.get("billable_credits") or 0) == 0
        and str(row.get("failure_class") or "") in TRANSIENT_NONBILLABLE_FAILURE_CLASSES
    )


def select_recovery_reason(row: TaskMapping) -> SelectionReason | None:
    """Select only evidence gaps that block a complete immutable assembly.

    A failed retailer gate selects its uncalled/cancelled population and its
    non-404 failed samples. A passed retailer selects only hard failures. A
    successful response and a billable 404 are immutable evidence and are
    never selected for another paid call.
    """

    status = str(row["status"])
    gate_status = str(row.get("retailer_gate_status") or "skipped")
    if status == "succeeded" or _is_retained_404(row):
        return None
    if gate_status == "failed":
        if status == "cancelled":
            return "cancelled_gate_scope"
        if status == "failed":
            return "failed_gate_scope"
        return None
    if _is_blocking_failure(row):
        return "blocking_failure"
    if evidence_outcome(row) == "zero_credit_missing":
        return "transient_gap"
    return None


def evidence_outcome(row: TaskMapping) -> EvidenceOutcome:
    status = str(row["status"])
    http_status = row.get("http_status")
    failure_class = str(row.get("failure_class") or "")
    if (
        status == "succeeded"
        and isinstance(http_status, int)
        and 200 <= http_status <= 299
        and row.get("raw_artifact_id") is not None
    ):
        return "usable_success"
    if _is_retained_404(row):
        return "retained_billable_404"
    if http_status == 200 and failure_class in {"schema_drift", "parse_error"}:
        return "contract_missing"
    if int(row.get("billable_credits") or 0) == 0 and (
        failure_class in TRANSIENT_NONBILLABLE_FAILURE_CLASSES
        or failure_class == "lease_exhausted"
        or status == "cancelled"
    ):
        return "zero_credit_missing"
    return "quarantined"


def _evidence_strength(outcome: EvidenceOutcome) -> int:
    return {
        "zero_credit_missing": 0,
        "quarantined": 1,
        "contract_missing": 2,
        "retained_billable_404": 3,
        "usable_success": 4,
    }[outcome]


def composite_trust_state(
    outcomes: Sequence[EvidenceOutcome],
    *,
    has_uncovered_recovery: bool = False,
    has_inadequate_recovery: bool = False,
) -> str:
    """Classify whether de-duplicated evidence may enter downstream analysis."""

    if (
        has_uncovered_recovery
        or has_inadequate_recovery
        or any(outcome in {"contract_missing", "quarantined"} for outcome in outcomes)
    ):
        return "blocked"
    if any(outcome == "zero_credit_missing" for outcome in outcomes):
        return "ready_with_warnings"
    return "ready"


def recovery_adequacy(
    outcomes_by_retailer: Mapping[str, Sequence[EvidenceOutcome]],
    *,
    maximum_warning_count: int = 2,
    maximum_warning_rate: float = 0.05,
) -> tuple[bool, dict[str, dict[str, Any]]]:
    """Fail closed on retailer recoveries that do not materially repair evidence.

    A small number of isolated, nonbillable gaps may remain a warning only when
    the same retailer lineage contains definitive usable/unavailable evidence.
    Callers must pass the complete cumulative lineage population so a failed
    optional retry cannot turn otherwise-ready 95%+ evidence into a blocker.
    """

    blocked = False
    manifest: dict[str, dict[str, Any]] = {}
    for retailer_id, outcomes in sorted(outcomes_by_retailer.items()):
        counts = {outcome: outcomes.count(outcome) for outcome in set(outcomes)}
        selected = len(outcomes)
        usable = counts.get("usable_success", 0)
        definitive = usable + counts.get("retained_billable_404", 0)
        zero_credit = counts.get("zero_credit_missing", 0)
        hard = counts.get("contract_missing", 0) + counts.get("quarantined", 0)
        warning_rate = zero_credit / selected if selected else 1.0
        allowed_warning_count = max(maximum_warning_count, int(selected * maximum_warning_rate))
        retailer_blocked = bool(
            selected == 0
            or hard
            or definitive == 0
            or zero_credit > allowed_warning_count
            or warning_rate > maximum_warning_rate
        )
        blocked = blocked or retailer_blocked
        manifest[retailer_id] = {
            "selected_requests": selected,
            "definitive_requests": definitive,
            "usable_successes": usable,
            "zero_credit_missing": zero_credit,
            "contract_or_quarantined": hard,
            "zero_credit_missing_rate": warning_rate,
            "maximum_warning_count": allowed_warning_count,
            "maximum_warning_rate": maximum_warning_rate,
            "status": "blocked" if retailer_blocked else ("warning" if zero_credit else "ready"),
        }
    return blocked, manifest


def retailer_collection_readiness(
    outcomes_by_retailer: Mapping[str, Sequence[EvidenceOutcome]],
    *,
    minimum_successes: int,
    maximum_404_rate: float,
    nonempty_successes_by_retailer: Mapping[str, int] | None = None,
    unavailability_approvals: Mapping[str, Mapping[str, Any]] | None = None,
    scope_projection_dispositions: Mapping[str, Mapping[str, Any]] | None = None,
    minimum_conclusive_coverage: float = MINIMUM_CONCLUSIVE_COVERAGE,
) -> tuple[bool, dict[str, dict[str, Any]]]:
    """Validate raw Search coverage, not product relevance or scorecard readiness.

    This gate only proves that each configured retailer contributed a bounded,
    contract-valid, non-empty Search evidence population. Admission, matching,
    and the publication semantic gate must still establish reportable governed
    comparisons; zero reported evidence is never inferred to be a valid score.
    """

    blocked = False
    manifest: dict[str, dict[str, Any]] = {}
    for retailer_id, outcomes in sorted(outcomes_by_retailer.items()):
        planned = len(outcomes)
        successes = outcomes.count("usable_success")
        not_found = outcomes.count("retained_billable_404")
        conclusive = successes + not_found
        conclusive_coverage = conclusive / planned if planned else 0.0
        not_found_rate = not_found / conclusive if conclusive else 1.0
        hard = outcomes.count("contract_missing") + outcomes.count("quarantined")
        nonempty_successes = int((nonempty_successes_by_retailer or {}).get(retailer_id, 0))
        approval = (unavailability_approvals or {}).get(retailer_id)
        scope_projection = (scope_projection_dispositions or {}).get(retailer_id)
        projection_unavailable = bool(
            scope_projection is not None
            and str(scope_projection.get("scorecard_disposition") or "") == "unavailable"
        )
        sufficient = bool(
            not hard
            and successes >= minimum_successes
            and nonempty_successes >= 1
            and conclusive_coverage >= minimum_conclusive_coverage
            and not_found_rate <= maximum_404_rate
        )
        explicitly_unavailable = bool(not hard and (approval is not None or projection_unavailable))
        retailer_blocked = bool(hard or (not sufficient and not explicitly_unavailable))
        blocked = blocked or retailer_blocked
        if retailer_blocked:
            readiness_status = "blocking_integrity"
        elif explicitly_unavailable:
            readiness_status = "unavailable"
        elif conclusive_coverage < 1.0 or not_found:
            readiness_status = "warning"
        else:
            readiness_status = "scoreable"
        manifest[retailer_id] = {
            "planned_requests": planned,
            "usable_successes": successes,
            "retained_billable_404s": not_found,
            "conclusive_coverage": conclusive_coverage,
            "minimum_conclusive_coverage": minimum_conclusive_coverage,
            "retained_404_rate": not_found_rate,
            "maximum_404_rate": maximum_404_rate,
            "minimum_successes": minimum_successes,
            "nonempty_usable_successes": nonempty_successes,
            "contract_or_quarantined": hard,
            "status": readiness_status,
            "unavailability_approval": (
                {
                    "id": str(approval["id"]),
                    "reason": str(approval["reason"]),
                    "approved_by": str(approval["approved_by"]),
                    "base_snapshot_checksum": str(approval["base_snapshot_checksum"]),
                }
                if explicitly_unavailable and approval is not None
                else None
            ),
            "scope_projection": (
                {
                    "id": str(scope_projection["id"]),
                    "projection_kind": str(scope_projection["projection_kind"]),
                    "projection_checksum": str(scope_projection["projection_checksum"]),
                    "raw_task_count": int(scope_projection["raw_task_count"]),
                    "retained_task_count": int(scope_projection["retained_task_count"]),
                    "excluded_task_count": int(scope_projection["excluded_task_count"]),
                    "raw_location_count": int(scope_projection["raw_location_count"]),
                    "retained_location_count": int(scope_projection["retained_location_count"]),
                    "excluded_location_count": int(scope_projection["excluded_location_count"]),
                    "raw_task_retention_ratio": str(scope_projection["raw_task_retention_ratio"]),
                    "governed_coverage_ratio": str(scope_projection["governed_coverage_ratio"]),
                    "minimum_scoreable_coverage": str(
                        scope_projection["minimum_scoreable_coverage"]
                    ),
                    "scorecard_disposition": str(scope_projection["scorecard_disposition"]),
                }
                if scope_projection is not None
                else None
            ),
        }
    return blocked, manifest


def resolve_task_precedence(
    base_rows: Sequence[TaskMapping],
    recovery_rows: Sequence[TaskMapping],
    *,
    approved_recovery_keys: Sequence[str],
) -> tuple[ResolvedTaskEvidence, ...]:
    """Resolve one lineage row per provider request without double counting."""

    def unique(rows: Sequence[TaskMapping], label: str) -> dict[str, TaskMapping]:
        result: dict[str, TaskMapping] = {}
        for row in rows:
            key = canonical_request_key(row)
            if key in result:
                raise ValueError(f"{label} contains duplicate canonical request evidence")
            result[key] = row
        return result

    base_by_key = unique(base_rows, "base")
    recovery_by_key = unique(recovery_rows, "recovery")
    approved = set(approved_recovery_keys)
    if approved - set(recovery_by_key):
        raise ValueError("recovery is missing approved canonical requests")
    if set(recovery_by_key) - set(base_by_key):
        raise ValueError("recovery contains canonical requests outside the base run")
    resolved: list[ResolvedTaskEvidence] = []
    for key, base_task in sorted(base_by_key.items()):
        recovery_task = recovery_by_key.get(key)
        selected = base_task
        superseded_task_id: str | None = None
        redundant_task_ids: tuple[str, ...] = ()
        if recovery_task is not None:
            base_outcome = evidence_outcome(base_task)
            recovery_outcome = evidence_outcome(recovery_task)
            if base_outcome != "usable_success" and _evidence_strength(
                recovery_outcome
            ) > _evidence_strength(base_outcome):
                selected = recovery_task
                superseded_task_id = str(base_task["id"])
            else:
                redundant_task_ids = (str(recovery_task["id"]),)
        resolved.append(
            ResolvedTaskEvidence(
                canonical_request_key=key,
                selected_task_id=str(selected["id"]),
                selected_raw_artifact_id=(
                    str(selected["raw_artifact_id"])
                    if selected.get("raw_artifact_id") is not None
                    else None
                ),
                superseded_task_id=superseded_task_id,
                evidence_outcome=evidence_outcome(selected),
                redundant_task_ids=redundant_task_ids,
            )
        )
    return tuple(resolved)


def _task_snapshot(row: TaskMapping) -> dict[str, Any]:
    return {
        **_task_contract_snapshot(row),
        "collection_run_id": str(row["collection_run_id"]),
        "attempt_count": int(row.get("attempt_count") or 0),
        "status": str(row["status"]),
        "http_status": row.get("http_status"),
        "failure_class": row.get("failure_class"),
        "billable_credits": int(row.get("billable_credits") or 0),
        "raw_artifact_id": (
            str(row["raw_artifact_id"]) if row.get("raw_artifact_id") is not None else None
        ),
        "result_count": row.get("result_count"),
        "location_snapshot": {
            "latitude": row.get("frozen_latitude"),
            "longitude": row.get("frozen_longitude"),
            "city": row.get("frozen_city"),
            "state": row.get("frozen_state"),
        },
    }


def _task_contract_snapshot(row: TaskMapping) -> dict[str, Any]:
    return {
        "task_id": str(row["id"]),
        "retailer_id": str(row["retailer_id"]),
        "adapter_id": str(row["adapter_id"]),
        "location_scope_key": str(row["location_scope_key"]),
        "zipcode": str(row["zipcode"]),
        "store_number": (str(row["store_number"]) if row.get("store_number") is not None else None),
        "retailer_location_id": (
            str(row["retailer_location_id"])
            if row.get("retailer_location_id") is not None
            else None
        ),
        "page_number": int(row["page_number"]),
        "max_pages": int(row["max_pages"]),
        "stop_on_empty": bool(row["stop_on_empty"]),
        "stop_on_short_page": bool(row["stop_on_short_page"]),
        "request_payload": dict(row["request_payload"]),
        "request_fingerprint": str(row["request_fingerprint"]),
        "is_preflight": bool(row.get("is_preflight")),
        "credits_per_success": int(row["credits_per_success"]),
        "priority": int(row["priority"]),
        "max_attempts": int(row["max_attempts"]),
        "effective_request_identity": effective_request_identity(row),
    }


def _scope_task_snapshot(
    row: TaskMapping,
    *,
    verified_provider_error_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the complete immutable inputs used by one scope decision."""

    last_error = str(row.get("last_error") or "")
    raw_metadata = row.get("raw_artifact_metadata")
    metadata = dict(raw_metadata) if isinstance(raw_metadata, Mapping) else {}
    return {
        "task": _task_snapshot(row),
        "canonical_request_key": canonical_request_key(row),
        "current_location_eligible": row.get("current_location_eligible"),
        "raw_artifact": {
            "id": (str(row["raw_artifact_id"]) if row.get("raw_artifact_id") is not None else None),
            "checksum": row.get("raw_artifact_checksum"),
            "provider": metadata.get("provider"),
            "retailer_id": metadata.get("retailer_id"),
            "adapter_id": metadata.get("adapter_id"),
            "http_status": metadata.get("http_status"),
            "body_checksum": metadata.get("body_checksum"),
        },
        "provider_error_evidence": {
            "verified": (
                dict(verified_provider_error_evidence)
                if verified_provider_error_evidence is not None
                else None
            ),
            "mutable_diagnostic": {
                "task_http_status": row.get("http_status"),
                "failure_class": row.get("failure_class"),
                "last_error_sha256": hashlib.sha256(last_error.encode()).hexdigest(),
            },
        },
    }


def _alias_family_key(row: TaskMapping, canonical_store_number: str) -> str:
    """Bind an alias to the otherwise-identical canonical provider request."""

    identity = effective_request_identity(row)
    params = dict(identity.get("params") or {})
    params["store"] = canonical_store_number
    return canonical_checksum(
        {
            "method": identity.get("method"),
            "path": identity.get("path"),
            "params": params,
        }
    )


def _physical_location_identity(row: TaskMapping) -> str:
    location_id = str(row.get("retailer_location_id") or "")
    if not location_id:
        raise ValueError("store scope projection requires an immutable retailer location identity")
    return location_id


def _is_sha256(value: object) -> bool:
    text_value = str(value or "")
    return len(text_value) == 64 and all(
        character in "0123456789abcdef" for character in text_value
    )


def _provider_invalid_store_rejection_evidence(
    row: TaskMapping,
    provider_error_evidence_contracts: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any] | None:
    """Verify an invalid-store rejection from immutable raw response evidence.

    ``last_error`` is intentionally excluded from authority: it is mutable task
    diagnostic text. The projection instead requires the immutable dataset
    artifact, its compressed-object checksum, HTTP metadata, and an exact raw
    response-body checksum from the reviewed adapter contract.
    """

    if str(row.get("status") or "") != "failed" or row.get("http_status") != 400:
        return None
    adapter_id = str(row.get("adapter_id") or "")
    contract_container = provider_error_evidence_contracts.get(adapter_id)
    contract = (
        contract_container.get("invalid_store_scope")
        if isinstance(contract_container, Mapping)
        else None
    )
    if not isinstance(contract, Mapping):
        raise ValueError(
            "provider invalid-store rejection has no reviewed response evidence contract"
        )
    expected_status = int(contract.get("http_status") or 0)
    body_checksum_allowlist = {
        str(value) for value in contract.get("body_checksum_allowlist") or []
    }
    if (
        expected_status != 400
        or not body_checksum_allowlist
        or not all(_is_sha256(value) for value in body_checksum_allowlist)
    ):
        raise ValueError("provider invalid-store response evidence contract is invalid")

    artifact_id = str(row.get("raw_artifact_id") or "")
    artifact_checksum = str(row.get("raw_artifact_checksum") or "")
    metadata_value = row.get("raw_artifact_metadata")
    if not artifact_id or not _is_sha256(artifact_checksum):
        raise ValueError(
            "provider invalid-store rejection lacks an immutable raw artifact and checksum"
        )
    if not isinstance(metadata_value, Mapping):
        raise ValueError("provider invalid-store rejection lacks raw artifact metadata")
    metadata = dict(metadata_value)
    if (
        metadata.get("provider") != "metricscart"
        or str(metadata.get("retailer_id") or "") != str(row.get("retailer_id") or "")
        or str(metadata.get("adapter_id") or "") != adapter_id
        or metadata.get("http_status") != expected_status
    ):
        raise ValueError(
            "provider invalid-store raw artifact metadata differs from its frozen task"
        )
    body_checksum = str(metadata.get("body_checksum") or "")
    if not _is_sha256(body_checksum) or body_checksum not in body_checksum_allowlist:
        raise ValueError(
            "provider invalid-store raw response body is not in the reviewed checksum allowlist"
        )
    return {
        "classification": "invalid_store_scope",
        "provider": "metricscart",
        "retailer_id": str(row["retailer_id"]),
        "adapter_id": adapter_id,
        "http_status": expected_status,
        "raw_artifact_id": artifact_id,
        "raw_artifact_checksum": artifact_checksum,
        "body_checksum": body_checksum,
        "evidence_contract_checksum": canonical_checksum(dict(contract)),
    }


def _location_audit_evidence(source_audit: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "kind": "location_eligibility_reconciliation",
        "audit_id": str(source_audit.get("id") or ""),
        "catalog_sha256": str(source_audit.get("catalog_sha256") or ""),
        "snapshot_sha256": str(source_audit.get("snapshot_sha256") or ""),
        "reviewed_plan_sha256": str(source_audit.get("reviewed_plan_sha256") or ""),
        "retailer_ids": sorted(str(value) for value in source_audit.get("retailer_ids") or []),
        "status": str(source_audit.get("status") or ""),
        "scanned_rows": int(source_audit.get("scanned_rows") or 0),
        "changed_rows": int(source_audit.get("changed_rows") or 0),
        "eligible_before": int(source_audit.get("eligible_before") or 0),
        "eligible_after": int(source_audit.get("eligible_after") or 0),
        "changes": list(source_audit.get("changes") or []),
    }


def validate_scope_projection_header_manifest(row: Mapping[str, Any]) -> dict[str, Any]:
    """Fail closed when a persisted projection header drifts from its review manifest."""

    manifest = dict(row.get("manifest") or {})
    if canonical_checksum(manifest) != str(row["projection_checksum"]):
        raise ValueError("stored scope projection manifest checksum is invalid")

    def fixed_ratio(name: str) -> str:
        return format(Decimal(str(row[name])), ".6f")

    source_audit_value = row.get("source_audit_text")
    if source_audit_value is None:
        source_audit_value = row.get("source_audit_id")
    header_contract = {
        "policy_version": str(row["policy_version"]),
        "base_collection_run_id": str(row.get("base_run_id") or row["base_collection_run_id"]),
        "retailer_id": str(row["retailer_id"]),
        "projection_kind": str(row["projection_kind"]),
        "base_snapshot_checksum": str(row["base_snapshot_checksum"]),
        "source_audit_id": (str(source_audit_value) if source_audit_value is not None else None),
        "source_evidence_checksum": str(row["source_evidence_checksum"]),
        "raw_task_count": int(row["raw_task_count"]),
        "retained_task_count": int(row["retained_task_count"]),
        "excluded_task_count": int(row["excluded_task_count"]),
        "raw_location_count": int(row["raw_location_count"]),
        "retained_location_count": int(row["retained_location_count"]),
        "excluded_location_count": int(row["excluded_location_count"]),
        "raw_task_retention_ratio": fixed_ratio("raw_task_retention_ratio"),
        "governed_coverage_ratio": fixed_ratio("governed_coverage_ratio"),
        "minimum_scoreable_coverage": fixed_ratio("minimum_scoreable_coverage"),
        "scorecard_disposition": str(row["scorecard_disposition"]),
    }
    if {key: manifest.get(key) for key in header_contract} != header_contract:
        raise ValueError("stored scope projection header differs from its reviewed manifest")
    source_evidence = manifest.get("source_evidence")
    if not isinstance(source_evidence, Mapping) or canonical_checksum(dict(source_evidence)) != str(
        row["source_evidence_checksum"]
    ):
        raise ValueError("stored scope projection source evidence checksum is invalid")
    inventory_checksum = manifest.get("inventory_checksum")
    if not isinstance(inventory_checksum, str) or len(inventory_checksum) != 64:
        raise ValueError("stored scope projection manifest has no inventory checksum")
    return manifest


def build_scope_projection_preview(
    base_collection_run_id: str,
    rows: Sequence[TaskMapping],
    *,
    retailer_id: str,
    projection_kind: ScopeProjectionKind,
    base_snapshot_checksum: str,
    source_audit: Mapping[str, Any] | None = None,
    provider_error_evidence_contracts: Mapping[str, Mapping[str, Any]] | None = None,
    minimum_scoreable_coverage: float = MINIMUM_CONCLUSIVE_COVERAGE,
) -> ScopeProjectionPreview:
    """Build a complete, checksum-bound retailer task projection.

    Alias collapse proves a one-for-one canonical physical-scope denominator;
    raw-row retention is disclosed separately and never drives scoreability.
    Limited provider footprint uses retained/raw network coverage and therefore
    becomes unavailable when it is below the governed minimum.
    """

    selected = sorted(
        (row for row in rows if str(row["retailer_id"]) == retailer_id),
        key=lambda row: (canonical_request_key(row), str(row["id"])),
    )
    if not selected:
        raise ValueError("scope projection retailer has no tasks in the immutable base run")
    if not (0 < minimum_scoreable_coverage <= 1):
        raise ValueError("minimum scoreable coverage must be greater than zero and at most one")

    items: list[ScopeProjectionItem] = []
    source_evidence: dict[str, Any]
    if projection_kind == "canonical_alias_collapse":
        if source_audit is None:
            raise ValueError("canonical alias collapse requires a completed location audit")
        if str(source_audit.get("status") or "") != "completed":
            raise ValueError("canonical alias collapse requires a completed location audit")
        if retailer_id not in {str(value) for value in source_audit.get("retailer_ids") or []}:
            raise ValueError("location audit does not cover the projected retailer")
        audit_changes = list(source_audit.get("changes") or [])
        if int(source_audit.get("changed_rows") or 0) != len(audit_changes):
            raise ValueError("location audit change inventory is incomplete")
        audit_by_location: dict[str, Mapping[str, Any]] = {}
        for change in audit_changes:
            if not isinstance(change, Mapping):
                raise ValueError("location audit contains an invalid change record")
            location_id = str(change.get("id") or "")
            if not location_id or location_id in audit_by_location:
                raise ValueError("location audit contains an ambiguous location identity")
            audit_by_location[location_id] = change

        retained_rows: dict[str, TaskMapping] = {}
        excluded_rows: list[TaskMapping] = []
        for row in selected:
            store_number = str(row.get("store_number") or "")
            if bool(row.get("current_location_eligible")):
                if len(store_number) != 8 or not store_number.isdigit():
                    raise ValueError(
                        "canonical alias collapse retained a non-eight-digit provider scope"
                    )
                family_key = _alias_family_key(row, store_number)
                if family_key in retained_rows:
                    raise ValueError("canonical alias collapse has duplicate retained scopes")
                retained_rows[family_key] = row
            else:
                if len(store_number) != 7 or not store_number.isdigit():
                    raise ValueError(
                        "canonical alias collapse may exclude only audited seven-digit aliases"
                    )
                excluded_rows.append(row)
        if not retained_rows or not excluded_rows:
            raise ValueError("canonical alias collapse requires retained and excluded scopes")

        alias_location_mapping: dict[str, str] = {}
        mapped_physical_targets: set[str] = set()
        for row in selected:
            store_number = str(row.get("store_number") or "")
            snapshot = _scope_task_snapshot(row)
            if bool(row.get("current_location_eligible")):
                items.append(
                    ScopeProjectionItem(
                        source_task_id=str(row["id"]),
                        retailer_id=retailer_id,
                        canonical_request_key=canonical_request_key(row),
                        disposition="retained",
                        reason="provider_safe_canonical_scope",
                        mapped_retained_task_id=None,
                        source_snapshot=snapshot,
                    )
                )
                continue
            location_id = str(row.get("retailer_location_id") or "")
            audit_change = audit_by_location.get(location_id)
            if audit_change is None:
                raise ValueError("excluded alias is not backed by the reviewed location audit")
            if not (
                bool(audit_change.get("before_eligible"))
                and not bool(audit_change.get("after_eligible"))
                and str(audit_change.get("store_number") or "") == store_number
            ):
                raise ValueError("excluded alias conflicts with its location-audit decision")
            canonical_store = store_number.zfill(8)
            retained = retained_rows.get(_alias_family_key(row, canonical_store))
            if retained is None:
                raise ValueError(
                    "excluded alias has no otherwise-identical retained canonical task"
                )
            retained_task_id = str(retained["id"])
            alias_location_id = _physical_location_identity(row)
            retained_location_id = _physical_location_identity(retained)
            prior_target = alias_location_mapping.setdefault(
                alias_location_id, retained_location_id
            )
            if prior_target != retained_location_id:
                raise ValueError("one alias location maps to multiple canonical physical scopes")
            items.append(
                ScopeProjectionItem(
                    source_task_id=str(row["id"]),
                    retailer_id=retailer_id,
                    canonical_request_key=canonical_request_key(row),
                    disposition="excluded",
                    reason="audited_alias_of_provider_safe_canonical_scope",
                    mapped_retained_task_id=retained_task_id,
                    source_snapshot=snapshot,
                )
            )
        for target in alias_location_mapping.values():
            if target in mapped_physical_targets:
                raise ValueError("more than one alias maps to the same canonical physical scope")
            mapped_physical_targets.add(target)
        excluded_location_ids = {_physical_location_identity(row) for row in excluded_rows}
        if set(alias_location_mapping) != excluded_location_ids:
            raise ValueError("canonical alias location inventory is not completely mapped")
        governed_coverage = Decimal("1")
        disposition: ScopeProjectionDisposition = "scoreable"
        source_evidence = _location_audit_evidence(source_audit)
        source_audit_id = str(source_audit.get("id") or "")
        if not source_audit_id:
            raise ValueError("completed location audit has no durable audit identity")
    elif projection_kind == "limited_provider_footprint":
        if source_audit is not None:
            raise ValueError("limited provider footprint is bound to task evidence, not an audit")
        disposition_by_location: dict[str, Literal["retained", "excluded"]] = {}
        invalid_store_artifact_evidence: list[dict[str, Any]] = []
        response_contracts = provider_error_evidence_contracts or {}
        for row in selected:
            rejection_evidence = _provider_invalid_store_rejection_evidence(row, response_contracts)
            if rejection_evidence is not None:
                disposition_value: Literal["retained", "excluded"] = "excluded"
                reason = "provider_rejected_store_scope_http_400"
                invalid_store_artifact_evidence.append(
                    {"source_task_id": str(row["id"]), **rejection_evidence}
                )
            elif evidence_outcome(row) == "usable_success":
                disposition_value = "retained"
                reason = "provider_valid_successful_scope"
            else:
                raise ValueError(
                    "limited provider footprint contains evidence other than a usable success "
                    "or an exact provider invalid-store rejection"
                )
            location_id = _physical_location_identity(row)
            prior_disposition = disposition_by_location.setdefault(location_id, disposition_value)
            if prior_disposition != disposition_value:
                raise ValueError(
                    "provider footprint contains conflicting evidence for one physical location"
                )
            items.append(
                ScopeProjectionItem(
                    source_task_id=str(row["id"]),
                    retailer_id=retailer_id,
                    canonical_request_key=canonical_request_key(row),
                    disposition=disposition_value,
                    reason=reason,
                    mapped_retained_task_id=None,
                    source_snapshot=_scope_task_snapshot(
                        row,
                        verified_provider_error_evidence=rejection_evidence,
                    ),
                )
            )
        retained_location_count = sum(
            value == "retained" for value in disposition_by_location.values()
        )
        governed_coverage = Decimal(retained_location_count) / Decimal(len(disposition_by_location))
        disposition = (
            "scoreable"
            if governed_coverage >= Decimal(str(minimum_scoreable_coverage))
            else "unavailable"
        )
        source_audit_id = None
        source_evidence = {
            "kind": "immutable_provider_task_evidence",
            "valid_location_ids": sorted(
                location_id
                for location_id, value in disposition_by_location.items()
                if value == "retained"
            ),
            "invalid_store_location_ids": sorted(
                location_id
                for location_id, value in disposition_by_location.items()
                if value == "excluded"
            ),
            "valid_success_task_ids": sorted(
                item.source_task_id for item in items if item.disposition == "retained"
            ),
            "invalid_store_task_ids": sorted(
                item.source_task_id for item in items if item.disposition == "excluded"
            ),
            "invalid_store_artifact_evidence": sorted(
                invalid_store_artifact_evidence,
                key=lambda value: str(value["source_task_id"]),
            ),
        }
    else:
        raise ValueError(f"unsupported scope projection kind {projection_kind!r}")

    items.sort(key=lambda item: (item.canonical_request_key, item.source_task_id))
    if len({item.canonical_request_key for item in items}) != len(items):
        raise ValueError("scope projection contains duplicate canonical provider requests")
    retained_count = sum(item.disposition == "retained" for item in items)
    excluded_count = len(items) - retained_count
    if retained_count == 0:
        raise ValueError("scope projection cannot remove the complete retailer population")
    raw_retention = Decimal(retained_count) / Decimal(len(items))
    locations_by_disposition: dict[str, set[str]] = {"retained": set(), "excluded": set()}
    row_by_task_id = {str(row["id"]): row for row in selected}
    for item in items:
        locations_by_disposition[item.disposition].add(
            _physical_location_identity(row_by_task_id[item.source_task_id])
        )
    overlap_locations = locations_by_disposition["retained"] & locations_by_disposition["excluded"]
    if overlap_locations:
        raise ValueError("one physical location has both retained and excluded task decisions")
    retained_location_count = len(locations_by_disposition["retained"])
    excluded_location_count = len(locations_by_disposition["excluded"])
    raw_location_count = retained_location_count + excluded_location_count

    def ratio(value: Decimal) -> str:
        return str(value.quantize(Decimal("0.000001")))

    source_evidence_checksum = canonical_checksum(source_evidence)
    manifest = {
        "schema_version": "1.0.0",
        "policy_version": SCOPE_PROJECTION_POLICY_VERSION,
        "base_collection_run_id": base_collection_run_id,
        "retailer_id": retailer_id,
        "projection_kind": projection_kind,
        "base_snapshot_checksum": base_snapshot_checksum,
        "source_audit_id": source_audit_id,
        "source_evidence_checksum": source_evidence_checksum,
        "source_evidence": source_evidence,
        "raw_task_count": len(items),
        "retained_task_count": retained_count,
        "excluded_task_count": excluded_count,
        "raw_location_count": raw_location_count,
        "retained_location_count": retained_location_count,
        "excluded_location_count": excluded_location_count,
        "raw_task_retention_ratio": ratio(raw_retention),
        "governed_coverage_ratio": ratio(governed_coverage),
        "minimum_scoreable_coverage": ratio(Decimal(str(minimum_scoreable_coverage))),
        "scorecard_disposition": disposition,
        "coverage_numerator_location_count": retained_location_count,
        "coverage_denominator_location_count": (
            retained_location_count
            if projection_kind == "canonical_alias_collapse"
            else raw_location_count
        ),
        "coverage_semantics": (
            "canonical_physical_scopes_retained_over_canonical_physical_scopes"
            if projection_kind == "canonical_alias_collapse"
            else "provider_valid_scopes_over_frozen_network_scopes"
        ),
        "inventory_checksum": canonical_checksum(
            {
                "items": [
                    {
                        "source_task_id": item.source_task_id,
                        "canonical_request_key": item.canonical_request_key,
                        "disposition": item.disposition,
                        "reason": item.reason,
                        "mapped_retained_task_id": item.mapped_retained_task_id,
                        "source_snapshot": item.source_snapshot,
                    }
                    for item in items
                ]
            }
        ),
    }
    return ScopeProjectionPreview(
        base_collection_run_id=base_collection_run_id,
        retailer_id=retailer_id,
        projection_kind=projection_kind,
        policy_version=SCOPE_PROJECTION_POLICY_VERSION,
        base_snapshot_checksum=base_snapshot_checksum,
        source_audit_id=source_audit_id,
        source_evidence_checksum=source_evidence_checksum,
        raw_task_count=len(items),
        retained_task_count=retained_count,
        excluded_task_count=excluded_count,
        raw_location_count=raw_location_count,
        retained_location_count=retained_location_count,
        excluded_location_count=excluded_location_count,
        raw_task_retention_ratio=ratio(raw_retention),
        governed_coverage_ratio=ratio(governed_coverage),
        minimum_scoreable_coverage=ratio(Decimal(str(minimum_scoreable_coverage))),
        scorecard_disposition=disposition,
        projection_checksum=canonical_checksum(manifest),
        manifest=manifest,
        items=tuple(items),
    )


def build_exact_recovery_task_contracts(
    preview: RecoverySelectionPreview | ContinuationSelectionPreview,
    *,
    selection_checksum: str,
    base_snapshot_checksum: str,
    approved_credit_ceiling: int,
) -> tuple[dict[str, Any], ...]:
    """Validate an approved preview and return exact, gate-free clone contracts."""

    if preview.selection_checksum != selection_checksum:
        raise ValueError("the approved recovery selection no longer matches the base run")
    if preview.base_snapshot_checksum != base_snapshot_checksum:
        raise ValueError("the approved recovery base snapshot no longer matches the base run")
    if preview.maximum_credits != approved_credit_ceiling:
        raise ValueError(
            "the exact recovery credit ceiling must equal the immutable selection maximum"
        )
    contracts: list[dict[str, Any]] = []
    fields = (
        "retailer_id",
        "retailer_location_id",
        "adapter_id",
        "location_scope_key",
        "zipcode",
        "store_number",
        "page_number",
        "max_pages",
        "stop_on_empty",
        "stop_on_short_page",
        "credits_per_success",
        "request_payload",
        "request_fingerprint",
        "priority",
        "max_attempts",
    )
    for item in preview.items:
        snapshot = dict(item.source_snapshot)
        if int(snapshot["page_number"]) < int(snapshot["max_pages"]):
            raise ValueError(
                "exact recovery cannot launch a task that may create unapproved paid pages; "
                "multi-page continuation recovery is not supported and must remain blocked "
                "until deterministic descendants are implemented"
            )
        contract = {name: snapshot[name] for name in fields}
        contract["is_preflight"] = False
        contracts.append(contract)
    return tuple(contracts)


def build_recovery_preview(
    base_collection_run_id: str,
    rows: Sequence[TaskMapping],
    *,
    definition_checksum: str,
    retailer_ids: Sequence[str] = (),
    allow_ineligible_locations: bool = False,
    base_snapshot_checksum_override: str | None = None,
    scope_projection_binding: Mapping[str, Any] | None = None,
) -> RecoverySelectionPreview:
    retailer_filter = frozenset(str(value) for value in retailer_ids)
    ordered = sorted(rows, key=lambda row: (str(row["retailer_id"]), canonical_request_key(row)))
    snapshots = [_task_snapshot(row) for row in ordered]
    calculated_base_snapshot_checksum = canonical_checksum(
        {
            "base_collection_run_id": base_collection_run_id,
            "definition_checksum": definition_checksum,
            "tasks": snapshots,
        }
    )
    base_snapshot_checksum = base_snapshot_checksum_override or calculated_base_snapshot_checksum
    items: list[RecoverySelectionItem] = []
    retailer_values: dict[str, dict[str, int]] = {}
    for row in ordered:
        retailer_id = str(row["retailer_id"])
        if retailer_filter and retailer_id not in retailer_filter:
            continue
        values = retailer_values.setdefault(
            retailer_id,
            {
                "selected_tasks": 0,
                "required_tasks": 0,
                "optional_transient_tasks": 0,
                "maximum_provider_attempts": 0,
                "maximum_credits": 0,
                "reused_successes": 0,
                "retained_billable_404s": 0,
                "retained_billable_404_credits": 0,
            },
        )
        if str(row["status"]) == "succeeded":
            values["reused_successes"] += 1
        if _is_retained_404(row):
            values["retained_billable_404s"] += 1
            values["retained_billable_404_credits"] += int(row["billable_credits"])
        reason = select_recovery_reason(row)
        if reason is None:
            continue
        if row.get("current_location_eligible") is False and not allow_ineligible_locations:
            raise ValueError(
                "failure-only recovery is blocked because the frozen run contains a "
                f"currently ineligible {retailer_id} location scope; approve the retailer "
                "as unavailable or wait for a checksum-bound scope-projection release"
            )
        item = RecoverySelectionItem(
            source_task_id=str(row["id"]),
            retailer_id=retailer_id,
            canonical_request_key=canonical_request_key(row),
            selection_reason=reason,
            required_for_assembly=reason != "transient_gap",
            credits_per_success=int(row["credits_per_success"]),
            maximum_credits=int(row["credits_per_success"]) * int(row["max_attempts"]),
            source_snapshot=_task_snapshot(row),
        )
        items.append(item)
        values["selected_tasks"] += 1
        if item.required_for_assembly:
            values["required_tasks"] += 1
        else:
            values["optional_transient_tasks"] += 1
        values["maximum_provider_attempts"] += int(row["max_attempts"])
        values["maximum_credits"] += item.maximum_credits
    selection_manifest = {
        "schema_version": "1.0.0",
        "selection_policy_version": SELECTION_POLICY_VERSION,
        "base_collection_run_id": base_collection_run_id,
        "base_snapshot_checksum": base_snapshot_checksum,
        "selection_scope": {"retailer_ids": sorted(retailer_filter)},
        "items": [
            {
                "source_task_id": item.source_task_id,
                "canonical_request_key": item.canonical_request_key,
                "selection_reason": item.selection_reason,
                "required_for_assembly": item.required_for_assembly,
                "source_snapshot": item.source_snapshot,
            }
            for item in items
        ],
    }
    if scope_projection_binding is not None:
        selection_manifest["scope_projection"] = dict(scope_projection_binding)
    retailers = tuple(
        RetailerRecoverySummary(retailer_id=retailer_id, **values)
        for retailer_id, values in sorted(retailer_values.items())
    )
    return RecoverySelectionPreview(
        base_collection_run_id=base_collection_run_id,
        selection_policy_version=SELECTION_POLICY_VERSION,
        selection_checksum=canonical_checksum(selection_manifest),
        base_snapshot_checksum=base_snapshot_checksum,
        selected_task_count=len(items),
        maximum_provider_attempts=sum(int(item.source_snapshot["max_attempts"]) for item in items),
        maximum_credits=sum(item.maximum_credits for item in items),
        retailers=retailers,
        items=tuple(items),
    )


def build_continuation_preview(
    base_collection_run_id: str,
    base_rows: Sequence[TaskMapping],
    lineage_components: Sequence[ContinuationLineageComponent],
    *,
    definition_checksum: str,
    continuation_of_recovery_plan_id: str,
    retailer_ids: Sequence[str] = (),
    minimum_successes: int = 1,
    maximum_404_rate: float = 0.5,
    minimum_conclusive_coverage: float = MINIMUM_CONCLUSIVE_COVERAGE,
    base_snapshot_checksum_override: str | None = None,
    scope_projection_binding: Mapping[str, Any] | None = None,
) -> ContinuationSelectionPreview:
    """Select only evidence still needed after an immutable terminal lineage.

    Successful responses and retained billable 404s are conclusive and can never
    be selected. Integrity failures are always selected. Nonbillable gaps are
    selected only to the deterministic number needed to satisfy the collection
    readiness contract, leaving already-safe bounded gaps as disclosed warnings.
    """

    if not lineage_components:
        raise ValueError("continuation requires at least one bound recovery component")
    if not 0 < minimum_conclusive_coverage <= 1:
        raise ValueError("minimum_conclusive_coverage must be in (0, 1]")
    if not 0 <= maximum_404_rate <= 1:
        raise ValueError("maximum_404_rate must be in [0, 1]")
    if minimum_successes < 1:
        raise ValueError("minimum_successes must be positive")

    retailer_filter = frozenset(str(value) for value in retailer_ids)
    base_preview = build_recovery_preview(
        base_collection_run_id,
        base_rows,
        definition_checksum=definition_checksum,
        allow_ineligible_locations=True,
        base_snapshot_checksum_override=base_snapshot_checksum_override,
        scope_projection_binding=scope_projection_binding,
    )
    base_by_key: dict[str, TaskMapping] = {}
    for row in base_rows:
        key = canonical_request_key(row)
        if key in base_by_key:
            raise ValueError("base run contains duplicate canonical request evidence")
        base_by_key[key] = row
    current_by_key = dict(base_by_key)
    selected_task_ids: dict[str, str] = {}
    expected_parent: str | None = None
    seen_plan_ids: set[str] = set()
    seen_run_ids: set[str] = set()
    lineage_manifest: list[dict[str, Any]] = []
    for expected_depth, component in enumerate(lineage_components):
        if component.recovery_plan_id in seen_plan_ids:
            raise ValueError("continuation lineage repeats a recovery plan")
        if component.recovery_collection_run_id in seen_run_ids:
            raise ValueError("continuation lineage repeats a recovery run")
        if component.continuation_of_recovery_plan_id != expected_parent:
            raise ValueError("continuation lineage is not a single ordered chain")
        if component.continuation_depth != expected_depth:
            raise ValueError("continuation lineage depth is not contiguous")
        selection_keys = set(component.selection_keys)
        adopted_keys = set(component.adopted_keys)
        if len(selection_keys) != len(component.selection_keys):
            raise ValueError("continuation ancestor has duplicate selected requests")
        if selection_keys & adopted_keys:
            raise ValueError("continuation ancestor selects and adopts the same request")
        recovery_by_key: dict[str, TaskMapping] = {}
        for row in component.recovery_rows:
            key = canonical_request_key(row)
            if key in recovery_by_key:
                raise ValueError("continuation ancestor run has duplicate request evidence")
            recovery_by_key[key] = row
        governed_keys = selection_keys | adopted_keys
        if not governed_keys.issubset(base_by_key):
            raise ValueError("continuation ancestor contains a request outside the base run")
        if not governed_keys.issubset(recovery_by_key):
            raise ValueError("continuation ancestor is missing governed request evidence")
        for key in sorted(governed_keys):
            current = current_by_key[key]
            recovery = recovery_by_key[key]
            if evidence_outcome(current) != "usable_success" and _evidence_strength(
                evidence_outcome(recovery)
            ) > _evidence_strength(evidence_outcome(current)):
                current_by_key[key] = recovery
                selected_task_ids[key] = str(recovery["id"])
        lineage_manifest.append(
            {
                "recovery_plan_id": component.recovery_plan_id,
                "recovery_collection_run_id": component.recovery_collection_run_id,
                "continuation_of_recovery_plan_id": component.continuation_of_recovery_plan_id,
                "continuation_depth": component.continuation_depth,
                "selection_checksum": component.selection_checksum,
                "selected_keys": sorted(selection_keys),
                "adopted_keys": sorted(adopted_keys),
                "recovery_evidence_checksum": canonical_checksum(
                    {
                        "tasks": [
                            _task_snapshot(recovery_by_key[key]) for key in sorted(recovery_by_key)
                        ]
                    }
                ),
            }
        )
        seen_plan_ids.add(component.recovery_plan_id)
        seen_run_ids.add(component.recovery_collection_run_id)
        expected_parent = component.recovery_plan_id
    if expected_parent != continuation_of_recovery_plan_id:
        raise ValueError("continuation parent is not the terminal lineage component")

    lineage_checksum = canonical_checksum(
        {
            "base_collection_run_id": base_collection_run_id,
            "base_snapshot_checksum": base_preview.base_snapshot_checksum,
            "components": lineage_manifest,
        }
    )
    rows_by_retailer: dict[str, list[tuple[str, TaskMapping]]] = {}
    for key, row in sorted(current_by_key.items()):
        retailer_id = str(row["retailer_id"])
        if retailer_filter and retailer_id not in retailer_filter:
            continue
        rows_by_retailer.setdefault(retailer_id, []).append((key, row))

    selected: list[RecoverySelectionItem] = []
    retailer_values: dict[str, dict[str, int]] = {}
    for retailer_id, keyed_rows in sorted(rows_by_retailer.items()):
        conclusive = [
            (key, row)
            for key, row in keyed_rows
            if evidence_outcome(row) in {"usable_success", "retained_billable_404"}
        ]
        usable_count = sum(evidence_outcome(row) == "usable_success" for _, row in keyed_rows)
        nonempty_usable_count = sum(
            evidence_outcome(row) == "usable_success" and int(row.get("result_count") or 0) > 0
            for _, row in keyed_rows
        )
        retained_404_count = sum(
            evidence_outcome(row) == "retained_billable_404" for _, row in keyed_rows
        )
        hard = [
            (key, row)
            for key, row in keyed_rows
            if evidence_outcome(row) in {"contract_missing", "quarantined"}
            and row.get("current_location_eligible") is not False
        ]
        gaps = [
            (key, row)
            for key, row in keyed_rows
            if evidence_outcome(row) == "zero_credit_missing"
            and row.get("current_location_eligible") is not False
        ]
        planned_count = len(keyed_rows)
        conclusive_count = len(conclusive)
        needed_for_coverage = max(
            0,
            math.ceil(planned_count * minimum_conclusive_coverage) - conclusive_count,
        )
        needed_for_success = max(
            0,
            minimum_successes - usable_count,
            1 - nonempty_usable_count,
        )
        if maximum_404_rate == 0:
            needed_for_404 = len(gaps) + len(hard) if retained_404_count else 0
        else:
            needed_for_404 = max(
                0,
                math.ceil(retained_404_count / maximum_404_rate) - conclusive_count,
            )
        needed_total = max(needed_for_coverage, needed_for_success, needed_for_404)
        available_unresolved = len(hard) + len(gaps)
        projected_conclusive = conclusive_count + available_unresolved
        projected_404_rate = (
            retained_404_count / projected_conclusive if projected_conclusive else 1.0
        )
        if needed_total > available_unresolved or projected_404_rate > maximum_404_rate:
            raise ValueError(
                f"{retailer_id} cannot satisfy collection readiness from its unresolved "
                "canonical requests; use an explicit governed unavailability decision "
                "instead of spending on an inadequate continuation"
            )
        gap_count = max(0, needed_total - len(hard))
        selected_rows = [*hard, *gaps[:gap_count]]
        values = {
            "selected_tasks": 0,
            "required_tasks": 0,
            "optional_transient_tasks": 0,
            "maximum_provider_attempts": 0,
            "maximum_credits": 0,
            "reused_successes": usable_count,
            "retained_billable_404s": retained_404_count,
            "retained_billable_404_credits": sum(
                int(row.get("billable_credits") or 0)
                for _, row in keyed_rows
                if evidence_outcome(row) == "retained_billable_404"
            ),
        }
        for key, row in selected_rows:
            outcome = evidence_outcome(row)
            required = outcome in {"contract_missing", "quarantined"}
            item = RecoverySelectionItem(
                source_task_id=str(row["id"]),
                retailer_id=retailer_id,
                canonical_request_key=key,
                selection_reason="blocking_failure" if required else "transient_gap",
                required_for_assembly=required,
                credits_per_success=int(row["credits_per_success"]),
                maximum_credits=int(row["credits_per_success"]) * int(row["max_attempts"]),
                source_snapshot=_task_snapshot(row),
            )
            selected.append(item)
            values["selected_tasks"] += 1
            values["required_tasks" if required else "optional_transient_tasks"] += 1
            values["maximum_provider_attempts"] += int(row["max_attempts"])
            values["maximum_credits"] += item.maximum_credits
        retailer_values[retailer_id] = values

    selected.sort(key=lambda item: (item.retailer_id, item.canonical_request_key))
    if len(selected) > MAXIMUM_CONTINUATION_TASKS:
        raise ValueError(
            f"continuation selects {len(selected)} tasks, above the governed "
            f"{MAXIMUM_CONTINUATION_TASKS}-task cap"
        )
    selection_manifest = {
        "schema_version": "1.0.0",
        "selection_policy_version": CONTINUATION_SELECTION_POLICY_VERSION,
        "base_collection_run_id": base_collection_run_id,
        "base_snapshot_checksum": base_preview.base_snapshot_checksum,
        "continuation_of_recovery_plan_id": continuation_of_recovery_plan_id,
        "lineage_checksum": lineage_checksum,
        "selection_scope": {"retailer_ids": sorted(retailer_filter)},
        "items": [
            {
                "source_task_id": item.source_task_id,
                "canonical_request_key": item.canonical_request_key,
                "selection_reason": item.selection_reason,
                "required_for_assembly": item.required_for_assembly,
                "source_snapshot": item.source_snapshot,
            }
            for item in selected
        ],
    }
    if scope_projection_binding is not None:
        selection_manifest["scope_projection"] = dict(scope_projection_binding)
    return ContinuationSelectionPreview(
        base_collection_run_id=base_collection_run_id,
        continuation_of_recovery_plan_id=continuation_of_recovery_plan_id,
        lineage_plan_ids=tuple(component.recovery_plan_id for component in lineage_components),
        lineage_checksum=lineage_checksum,
        selection_policy_version=CONTINUATION_SELECTION_POLICY_VERSION,
        selection_checksum=canonical_checksum(selection_manifest),
        base_snapshot_checksum=base_preview.base_snapshot_checksum,
        selected_task_count=len(selected),
        maximum_provider_attempts=sum(
            int(item.source_snapshot["max_attempts"]) for item in selected
        ),
        maximum_credits=sum(item.maximum_credits for item in selected),
        resolved_before_count=len(selected_task_ids),
        conclusive_before_count=sum(
            evidence_outcome(row) in {"usable_success", "retained_billable_404"}
            for row in current_by_key.values()
        ),
        retained_success_count=sum(
            evidence_outcome(row) == "usable_success" for row in current_by_key.values()
        ),
        retained_billable_404_count=sum(
            evidence_outcome(row) == "retained_billable_404" for row in current_by_key.values()
        ),
        retailers=tuple(
            RetailerRecoverySummary(retailer_id=retailer_id, **values)
            for retailer_id, values in sorted(retailer_values.items())
        ),
        items=tuple(selected),
    )


def partition_uncovered_recovery_keys(
    uncovered_required_keys: set[str],
    *,
    base_by_key: Mapping[str, TaskMapping],
    chosen_by_key: Mapping[str, tuple[TaskMapping, EvidenceOutcome]],
    collection_readiness_manifest: Mapping[str, Mapping[str, Any]],
    unavailable_retailer_ids: set[str],
) -> tuple[set[str], set[str], set[str]]:
    """Separate blockers from governed warnings and explicitly unavailable scope."""

    unavailable = {
        key
        for key in uncovered_required_keys
        if str(base_by_key[key]["retailer_id"]) in unavailable_retailer_ids
    }
    blocking = {
        key
        for key in uncovered_required_keys
        if str(base_by_key[key]["retailer_id"]) not in unavailable_retailer_ids
        and (
            chosen_by_key[key][1] in {"contract_missing", "quarantined"}
            or collection_readiness_manifest[str(base_by_key[key]["retailer_id"])]["status"]
            == "blocking_integrity"
        )
    }
    tolerated = uncovered_required_keys - unavailable - blocking
    return blocking, unavailable, tolerated


class PostgresCompositeEvidenceRepository:
    """Persist checksum-bound recovery intent and assemble immutable evidence."""

    def __init__(
        self,
        engine: AsyncEngine,
        *,
        analysis_code_version: str = ASSEMBLY_POLICY_VERSION,
        analysis_max_attempts: int = 3,
        provider_request_contracts: Mapping[str, Mapping[str, Any]],
        provider_error_evidence_contracts: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> None:
        self._engine = engine
        self._analysis_code_version = analysis_code_version
        self._analysis_max_attempts = analysis_max_attempts
        self._provider_request_contracts = {
            str(key): dict(value) for key, value in provider_request_contracts.items()
        }
        self._provider_error_evidence_contracts = {
            str(key): dict(value)
            for key, value in (provider_error_evidence_contracts or {}).items()
        }

    async def preview(
        self,
        base_collection_run_id: str,
        *,
        retailer_ids: Sequence[str] = (),
        scope_projection_id: str | None = None,
    ) -> RecoverySelectionPreview:
        async with self._engine.connect() as connection:
            definition_checksum, rows = await self._base_rows(connection, base_collection_run_id)
            raw_preview = build_recovery_preview(
                base_collection_run_id,
                rows,
                definition_checksum=definition_checksum,
                allow_ineligible_locations=True,
            )
            binding = None
            if scope_projection_id is not None:
                projection = await self._scope_projection_row(
                    connection, scope_projection_id, include_inventory=True
                )
                rows = self._apply_scope_projection_rows(
                    rows,
                    [projection],
                    base_collection_run_id=base_collection_run_id,
                    base_snapshot_checksum=raw_preview.base_snapshot_checksum,
                )
                binding = self._scope_projection_binding(projection)
        return build_recovery_preview(
            base_collection_run_id,
            rows,
            definition_checksum=definition_checksum,
            retailer_ids=retailer_ids,
            base_snapshot_checksum_override=raw_preview.base_snapshot_checksum,
            scope_projection_binding=binding,
        )

    async def preview_scope_projection(
        self,
        base_collection_run_id: str,
        *,
        retailer_id: str,
        projection_kind: ScopeProjectionKind,
        source_audit_id: str | None = None,
    ) -> ScopeProjectionPreview:
        async with self._engine.connect() as connection:
            return await self._build_scope_projection_preview(
                connection,
                base_collection_run_id,
                retailer_id=retailer_id,
                projection_kind=projection_kind,
                source_audit_id=source_audit_id,
            )

    async def approve_scope_projection(
        self,
        base_collection_run_id: str,
        *,
        retailer_id: str,
        projection_kind: ScopeProjectionKind,
        projection_checksum: str,
        base_snapshot_checksum: str,
        review_reason: str,
        reviewed_by: str,
        source_audit_id: str | None = None,
    ) -> ScopeProjectionRecord:
        """Persist exactly the complete projection an administrator reviewed."""

        if not review_reason.strip() or not reviewed_by.strip():
            raise ValueError("review_reason and reviewed_by are required")
        async with self._engine.begin() as connection:
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"collection-scope-projection:{base_collection_run_id}:{retailer_id}"},
            )
            preview = await self._build_scope_projection_preview(
                connection,
                base_collection_run_id,
                retailer_id=retailer_id,
                projection_kind=projection_kind,
                source_audit_id=source_audit_id,
                for_update=True,
            )
            if preview.base_snapshot_checksum != base_snapshot_checksum:
                raise ValueError("scope projection no longer matches the immutable base snapshot")
            if preview.projection_checksum != projection_checksum:
                raise ValueError("scope projection changed; review a new complete preview")
            existing = (
                (
                    await connection.execute(
                        text(
                            "SELECT * FROM collection_scope_projection "
                            "WHERE base_collection_run_id::text = :run_id "
                            "AND retailer_id = :retailer_id "
                            "AND projection_checksum = :checksum"
                        ),
                        {
                            "run_id": base_collection_run_id,
                            "retailer_id": retailer_id,
                            "checksum": projection_checksum,
                        },
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                if (
                    str(existing["review_reason"]) != review_reason.strip()
                    or str(existing["reviewed_by"]) != reviewed_by.strip()
                ):
                    raise ValueError("the reviewed projection already has another approval record")
                verified = await self._scope_projection_row(
                    connection, str(existing["id"]), include_inventory=True
                )
                return self._scope_projection_record(verified)
            run = (
                (
                    await connection.execute(
                        text(
                            "SELECT organization_id::text FROM collection_run "
                            "WHERE id::text = :run_id"
                        ),
                        {"run_id": base_collection_run_id},
                    )
                )
                .mappings()
                .one()
            )
            inserted = (
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO collection_scope_projection (
                              organization_id, base_collection_run_id, retailer_id,
                              projection_kind, policy_version, base_snapshot_checksum,
                              source_audit_id, source_evidence_checksum,
                              raw_task_count, retained_task_count, excluded_task_count,
                              raw_location_count, retained_location_count,
                              excluded_location_count, raw_task_retention_ratio,
                              governed_coverage_ratio,
                              minimum_scoreable_coverage, scorecard_disposition,
                              projection_checksum, review_reason, reviewed_by, manifest
                            ) VALUES (
                              CAST(:organization_id AS uuid), CAST(:run_id AS uuid),
                              :retailer_id, :projection_kind, :policy_version,
                              :base_snapshot_checksum, CAST(:source_audit_id AS uuid),
                              :source_evidence_checksum, :raw_task_count,
                              :retained_task_count, :excluded_task_count,
                              :raw_location_count, :retained_location_count,
                              :excluded_location_count, :raw_task_retention_ratio,
                              :governed_coverage_ratio,
                              :minimum_scoreable_coverage, :scorecard_disposition,
                              :projection_checksum, :review_reason, :reviewed_by,
                              CAST(:manifest AS jsonb)
                            ) RETURNING *
                            """
                        ),
                        {
                            "organization_id": str(run["organization_id"]),
                            "run_id": base_collection_run_id,
                            "retailer_id": retailer_id,
                            "projection_kind": projection_kind,
                            "policy_version": preview.policy_version,
                            "base_snapshot_checksum": preview.base_snapshot_checksum,
                            "source_audit_id": preview.source_audit_id,
                            "source_evidence_checksum": preview.source_evidence_checksum,
                            "raw_task_count": preview.raw_task_count,
                            "retained_task_count": preview.retained_task_count,
                            "excluded_task_count": preview.excluded_task_count,
                            "raw_location_count": preview.raw_location_count,
                            "retained_location_count": preview.retained_location_count,
                            "excluded_location_count": preview.excluded_location_count,
                            "raw_task_retention_ratio": preview.raw_task_retention_ratio,
                            "governed_coverage_ratio": preview.governed_coverage_ratio,
                            "minimum_scoreable_coverage": preview.minimum_scoreable_coverage,
                            "scorecard_disposition": preview.scorecard_disposition,
                            "projection_checksum": preview.projection_checksum,
                            "review_reason": review_reason.strip(),
                            "reviewed_by": reviewed_by.strip(),
                            "manifest": _json(preview.manifest),
                        },
                    )
                )
                .mappings()
                .one()
            )
            projection_id = str(inserted["id"])
            inventory = [
                {
                    "scope_projection_id": projection_id,
                    "source_task_id": item.source_task_id,
                    "ordinal": ordinal,
                    "canonical_request_key": item.canonical_request_key,
                    "disposition": item.disposition,
                    "reason": item.reason,
                    "mapped_retained_task_id": item.mapped_retained_task_id,
                    "source_snapshot": item.source_snapshot,
                }
                for ordinal, item in enumerate(preview.items)
            ]
            inserted_count = 0
            for offset in range(0, len(inventory), MATERIALIZATION_WRITE_BATCH_SIZE):
                batch = inventory[offset : offset + MATERIALIZATION_WRITE_BATCH_SIZE]
                inserted_count += int(
                    (
                        await connection.execute(
                            text(
                                """
                                WITH payload AS (
                                  SELECT * FROM jsonb_to_recordset(CAST(:rows AS jsonb)) AS x(
                                    scope_projection_id text, source_task_id text,
                                    ordinal integer, canonical_request_key text,
                                    disposition text, reason text,
                                    mapped_retained_task_id text, source_snapshot jsonb
                                  )
                                ), inserted AS (
                                  INSERT INTO collection_scope_projection_task (
                                    scope_projection_id, source_task_id, ordinal,
                                    canonical_request_key, disposition, reason,
                                    mapped_retained_task_id, source_snapshot
                                  )
                                  SELECT CAST(scope_projection_id AS uuid),
                                         CAST(source_task_id AS uuid), ordinal,
                                         canonical_request_key, disposition, reason,
                                         CAST(mapped_retained_task_id AS uuid), source_snapshot
                                  FROM payload RETURNING 1
                                ) SELECT count(*)::integer FROM inserted
                                """
                            ),
                            {"rows": _json(batch)},
                        )
                    ).scalar_one()
                )
            if inserted_count != preview.raw_task_count:
                raise RuntimeError("scope projection inventory insertion was incomplete")
            verified = await self._scope_projection_row(
                connection, projection_id, include_inventory=True
            )
            return self._scope_projection_record(verified)

    async def preview_continuation(
        self,
        continuation_of_recovery_plan_id: str,
        *,
        retailer_ids: Sequence[str] = (),
    ) -> ContinuationSelectionPreview:
        """Preview incremental work against a terminal immutable plan lineage."""

        async with self._engine.connect() as connection:
            return await self._build_continuation_preview(
                connection,
                continuation_of_recovery_plan_id,
                retailer_ids=retailer_ids,
            )

    async def _build_continuation_preview(
        self,
        connection: AsyncConnection,
        continuation_of_recovery_plan_id: str,
        *,
        retailer_ids: Sequence[str] = (),
    ) -> ContinuationSelectionPreview:
        parent = await self._plan_row(connection, continuation_of_recovery_plan_id)
        base_run_id = str(parent["base_collection_run_id"])
        definition_checksum, base_rows = await self._base_rows(connection, base_run_id)
        raw_preview = build_recovery_preview(
            base_run_id,
            base_rows,
            definition_checksum=definition_checksum,
            allow_ineligible_locations=True,
        )
        scope_projection_binding = None
        if parent.get("scope_projection_id") is not None:
            projection = await self._scope_projection_row(
                connection, str(parent["scope_projection_id"]), include_inventory=True
            )
            if str(projection["projection_checksum"]) != str(
                parent.get("scope_projection_checksum") or ""
            ):
                raise ValueError("continuation parent scope projection checksum changed")
            base_rows = self._apply_scope_projection_rows(
                base_rows,
                [projection],
                base_collection_run_id=base_run_id,
                base_snapshot_checksum=raw_preview.base_snapshot_checksum,
            )
            scope_projection_binding = self._scope_projection_binding(projection)
        run = (
            (
                await connection.execute(
                    text(
                        "SELECT availability_gate_config FROM collection_run "
                        "WHERE id::text = :run_id"
                    ),
                    {"run_id": base_run_id},
                )
            )
            .mappings()
            .one()
        )
        gate_config = dict(run.get("availability_gate_config") or {})
        plan_rows = list(
            (
                await connection.execute(
                    text(
                        """
                        WITH RECURSIVE lineage AS (
                          SELECT p.*, ARRAY[p.id] AS lineage_path
                          FROM collection_recovery_plan p
                          WHERE p.id::text = :parent_plan_id
                          UNION ALL
                          SELECT ancestor.*, child.lineage_path || ancestor.id
                          FROM collection_recovery_plan ancestor
                          JOIN lineage child
                            ON child.continuation_of_recovery_plan_id = ancestor.id
                          WHERE NOT ancestor.id = ANY(child.lineage_path)
                        )
                        SELECT * FROM lineage
                        ORDER BY continuation_depth, created_at, id
                        """
                    ),
                    {"parent_plan_id": continuation_of_recovery_plan_id},
                )
            )
            .mappings()
            .all()
        )
        if not plan_rows or str(plan_rows[-1]["id"]) != continuation_of_recovery_plan_id:
            raise ValueError("continuation parent does not resolve to a complete lineage")
        if any(str(row["base_collection_run_id"]) != base_run_id for row in plan_rows):
            raise ValueError("continuation lineage spans more than one base run")
        if any(
            str(row.get("scope_projection_id") or "")
            != str(parent.get("scope_projection_id") or "")
            or str(row.get("scope_projection_checksum") or "")
            != str(parent.get("scope_projection_checksum") or "")
            for row in plan_rows
        ):
            raise ValueError("continuation lineage changes its scope projection")
        if len({str(row["organization_id"]) for row in plan_rows}) != 1:
            raise ValueError("continuation lineage spans more than one organization")
        if len(plan_rows) > 33:
            raise ValueError("continuation lineage exceeds the governed depth limit")
        batch_ids = {str(row.get("recovery_batch_id") or "") for row in plan_rows}
        if len(batch_ids) != 1 or "" in batch_ids:
            raise ValueError("continuation lineage must share one immutable recovery batch")
        if any(str(row["status"]) not in {"bound", "ready"} for row in plan_rows):
            raise ValueError("continuation requires every ancestor plan to be bound or ready")
        recovery_run_ids = [
            str(row["recovery_collection_run_id"])
            for row in plan_rows
            if row.get("recovery_collection_run_id") is not None
        ]
        if len(recovery_run_ids) != len(plan_rows):
            raise ValueError("continuation ancestor is not bound to a recovery run")
        terminal_rows = (
            (
                await connection.execute(
                    text(
                        "SELECT id::text, status FROM collection_run "
                        "WHERE id::text = ANY(CAST(:run_ids AS text[]))"
                    ),
                    {"run_ids": recovery_run_ids},
                )
            )
            .mappings()
            .all()
        )
        terminal_statuses: dict[str, str] = {
            str(row["id"]): str(row["status"]) for row in terminal_rows
        }
        if set(terminal_statuses) != set(recovery_run_ids) or any(
            str(status) not in {"succeeded", "completed_with_warnings", "failed", "cancelled"}
            for status in terminal_statuses.values()
        ):
            raise ValueError("continuation requires every ancestor recovery run to be terminal")
        components: list[ContinuationLineageComponent] = []
        for plan, recovery_run_id in zip(plan_rows, recovery_run_ids, strict=True):
            plan_id = str(plan["id"])
            selection_keys = tuple(
                str(value)
                for value in (
                    await connection.execute(
                        text(
                            "SELECT canonical_request_key "
                            "FROM collection_recovery_selection "
                            "WHERE recovery_plan_id::text = :plan_id ORDER BY ordinal"
                        ),
                        {"plan_id": plan_id},
                    )
                ).scalars()
            )
            binding_manifest = dict(plan.get("binding_manifest") or {})
            adopted_keys = tuple(
                sorted(
                    str(row["canonical_request_key"])
                    for row in binding_manifest.get("adopted_gap_replacements", [])
                )
            )
            components.append(
                ContinuationLineageComponent(
                    recovery_plan_id=plan_id,
                    recovery_collection_run_id=recovery_run_id,
                    continuation_of_recovery_plan_id=(
                        str(plan["continuation_of_recovery_plan_id"])
                        if plan.get("continuation_of_recovery_plan_id") is not None
                        else None
                    ),
                    continuation_depth=int(plan.get("continuation_depth") or 0),
                    selection_checksum=str(plan["selection_checksum"]),
                    selection_keys=selection_keys,
                    adopted_keys=adopted_keys,
                    recovery_rows=tuple(await self._task_rows(connection, recovery_run_id)),
                )
            )
        return build_continuation_preview(
            base_run_id,
            base_rows,
            components,
            definition_checksum=definition_checksum,
            continuation_of_recovery_plan_id=continuation_of_recovery_plan_id,
            retailer_ids=retailer_ids,
            minimum_successes=max(int(gate_config.get("minimum_successful_samples") or 1), 1),
            maximum_404_rate=float(gate_config.get("max_billable_404_rate", 0.5)),
            base_snapshot_checksum_override=raw_preview.base_snapshot_checksum,
            scope_projection_binding=scope_projection_binding,
        )

    async def approve_retailer_unavailability(
        self,
        base_collection_run_id: str,
        *,
        retailer_id: str,
        base_snapshot_checksum: str,
        reason: str,
        approved_by: str,
    ) -> RetailerUnavailabilityApprovalRecord:
        """Explicitly classify an evidence-deficient competitor as unavailable."""

        if not retailer_id.strip() or not reason.strip() or not approved_by.strip():
            raise ValueError("retailer_id, reason, and approved_by are required")
        async with self._engine.begin() as connection:
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"collection-recovery:{base_collection_run_id}"},
            )
            definition_checksum, rows = await self._base_rows(
                connection, base_collection_run_id, for_update=True
            )
            preview = build_recovery_preview(
                base_collection_run_id,
                rows,
                definition_checksum=definition_checksum,
                allow_ineligible_locations=True,
            )
            if preview.base_snapshot_checksum != base_snapshot_checksum:
                raise ValueError(
                    "the retailer-unavailability approval does not match the base snapshot"
                )
            run = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT r.organization_id::text, r.availability_gate_config,
                                   v.config
                            FROM collection_run r
                            JOIN collection_definition_version v
                              ON v.id = r.definition_version_id
                            WHERE r.id::text = :run_id
                            """
                        ),
                        {"run_id": base_collection_run_id},
                    )
                )
                .mappings()
                .one()
            )
            config = dict(run["config"] or {})
            enabled_retailers = {
                str(item["retailer_id"])
                for item in config.get("retailers", [])
                if isinstance(item, Mapping) and bool(item.get("enabled"))
            }
            if retailer_id not in enabled_retailers:
                raise ValueError("retailer is not enabled in the immutable collection definition")
            if retailer_id == str(config.get("benchmark_retailer") or ""):
                raise ValueError("the benchmark retailer cannot be classified as unavailable")
            retailer_rows = [row for row in rows if str(row["retailer_id"]) == retailer_id]
            outcomes = [evidence_outcome(row) for row in retailer_rows]
            if any(outcome in {"contract_missing", "quarantined"} for outcome in outcomes):
                raise ValueError(
                    "contract or quarantined evidence is an integrity blocker and cannot be waived"
                )
            nonempty = sum(
                evidence_outcome(row) == "usable_success" and int(row.get("result_count") or 0) > 0
                for row in retailer_rows
            )
            gate_config = dict(run.get("availability_gate_config") or {})
            already_safe, _ = retailer_collection_readiness(
                {retailer_id: outcomes},
                minimum_successes=max(int(gate_config.get("minimum_successful_samples") or 1), 1),
                maximum_404_rate=float(gate_config.get("max_billable_404_rate", 0.5)),
                nonempty_successes_by_retailer={retailer_id: nonempty},
            )
            has_ineligible_scope = any(
                row.get("current_location_eligible") is False for row in retailer_rows
            )
            if not already_safe and not has_ineligible_scope:
                raise ValueError(
                    "retailer Search evidence is already sufficient; unavailable is not valid"
                )
            existing = (
                (
                    await connection.execute(
                        text(
                            "SELECT * FROM collection_retailer_unavailability_approval "
                            "WHERE base_collection_run_id::text = :run_id "
                            "AND retailer_id = :retailer_id AND status = 'active' FOR UPDATE"
                        ),
                        {"run_id": base_collection_run_id, "retailer_id": retailer_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                if (
                    str(existing["base_snapshot_checksum"]) == base_snapshot_checksum
                    and str(existing["reason"]) == reason.strip()
                    and str(existing["approved_by"]) == approved_by.strip()
                ):
                    return self._unavailability_record(existing)
                raise ValueError("retailer already has a different active unavailability approval")
            inserted = (
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO collection_retailer_unavailability_approval (
                              organization_id, base_collection_run_id, retailer_id,
                              base_snapshot_checksum, reason, approved_by
                            ) VALUES (
                              CAST(:organization_id AS uuid), CAST(:run_id AS uuid),
                              :retailer_id, :base_snapshot_checksum, :reason, :approved_by
                            ) RETURNING *
                            """
                        ),
                        {
                            "organization_id": str(run["organization_id"]),
                            "run_id": base_collection_run_id,
                            "retailer_id": retailer_id,
                            "base_snapshot_checksum": base_snapshot_checksum,
                            "reason": reason.strip(),
                            "approved_by": approved_by.strip(),
                        },
                    )
                )
                .mappings()
                .one()
            )
            return self._unavailability_record(inserted)

    async def revoke_retailer_unavailability(
        self, approval_id: str, *, revoked_by: str
    ) -> RetailerUnavailabilityApprovalRecord:
        """Revoke one active approval while preserving every prior generation."""

        if not revoked_by.strip():
            raise ValueError("revoked_by is required")
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "SELECT * FROM collection_retailer_unavailability_approval "
                            "WHERE id::text = :approval_id FOR UPDATE"
                        ),
                        {"approval_id": approval_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise LookupError(f"retailer unavailability approval {approval_id!r} was not found")
            if str(row["status"]) == "revoked":
                if str(row.get("revoked_by") or "") != revoked_by.strip():
                    raise ValueError("approval was revoked by a different authenticated actor")
                return self._unavailability_record(row)
            updated = (
                (
                    await connection.execute(
                        text(
                            "UPDATE collection_retailer_unavailability_approval "
                            "SET status = 'revoked', revoked_at = now(), revoked_by = :revoked_by "
                            "WHERE id::text = :approval_id AND status = 'active' RETURNING *"
                        ),
                        {"approval_id": approval_id, "revoked_by": revoked_by.strip()},
                    )
                )
                .mappings()
                .one()
            )
            return self._unavailability_record(updated)

    async def authorize_recovery_spend(
        self,
        *,
        organization_id: str,
        phase_key: str,
        approved_credit_ceiling: int,
        unit_cost_usd: str,
        currency: str,
        reason: str,
        authorized_by: str,
        collection_run_ids: Sequence[str],
    ) -> SpendAuthorizationRecord:
        """Create the immutable owner authorization used by the offline admin workflow.

        This method is intentionally not exposed by the web API. A batch can only
        consume one of these pre-existing records, preventing an authenticated API
        caller from inventing a new phase, price, inventory, or ceiling.
        """

        normalized_phase_key = phase_key.strip()
        if not normalized_phase_key or not reason.strip() or not authorized_by.strip():
            raise ValueError("phase_key, reason, and authorized_by are required")
        if approved_credit_ceiling <= 0:
            raise ValueError("approved_credit_ceiling must be positive")
        try:
            normalized_unit_cost = Decimal(str(unit_cost_usd)).quantize(Decimal("0.000001"))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("unit_cost_usd must be a decimal") from exc
        if normalized_unit_cost != SEARCH_CREDIT_UNIT_COST_USD:
            raise ValueError("Search recovery credit cost is fixed at $0.002000 per credit")
        if currency.strip().upper() != "USD":
            raise ValueError("only USD recovery authorizations are supported")
        run_ids = tuple(sorted(set(str(value) for value in collection_run_ids)))
        if not run_ids:
            raise ValueError("spend authorization requires the exact existing phase inventory")
        inventory_checksum = canonical_checksum(
            {"phase_key": normalized_phase_key, "collection_run_ids": list(run_ids)}
        )
        async with self._engine.begin() as connection:
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"collection-spend-authorization:{organization_id}:{normalized_phase_key}"},
            )
            runs = list(
                (
                    await connection.execute(
                        text(
                            "SELECT id::text, organization_id::text FROM collection_run "
                            "WHERE id::text = ANY(CAST(:run_ids AS text[])) FOR UPDATE"
                        ),
                        {"run_ids": list(run_ids)},
                    )
                )
                .mappings()
                .all()
            )
            if len(runs) != len(run_ids):
                raise LookupError("one or more authorized phase runs were not found")
            if any(str(run["organization_id"]) != organization_id for run in runs):
                raise ValueError("all authorized phase runs must share the organization")
            existing = (
                (
                    await connection.execute(
                        text(
                            "SELECT * FROM collection_spend_authorization "
                            "WHERE organization_id = CAST(:organization_id AS uuid) "
                            "AND phase_key = :phase_key FOR UPDATE"
                        ),
                        {"organization_id": organization_id, "phase_key": normalized_phase_key},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                expected = (
                    str(existing["inventory_checksum"]) == inventory_checksum
                    and tuple(sorted(str(value) for value in existing["authorized_run_ids"]))
                    == run_ids
                    and int(existing["approved_credit_ceiling"]) == approved_credit_ceiling
                    and Decimal(str(existing["unit_cost_usd"])) == normalized_unit_cost
                    and str(existing["currency"]) == "USD"
                    and str(existing["reason"]) == reason.strip()
                    and str(existing["authorized_by"]) == authorized_by.strip()
                )
                if not expected:
                    raise ValueError("phase key already has a different immutable authorization")
                return self._spend_authorization_record(existing)
            inserted = (
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO collection_spend_authorization (
                              organization_id, phase_key, inventory_checksum,
                              authorized_run_ids, approved_credit_ceiling, unit_cost_usd,
                              currency, reason, authorized_by
                            ) VALUES (
                              CAST(:organization_id AS uuid), :phase_key, :inventory_checksum,
                              CAST(:authorized_run_ids AS jsonb), :ceiling, :unit_cost,
                              'USD', :reason, :authorized_by
                            ) RETURNING *
                            """
                        ),
                        {
                            "organization_id": organization_id,
                            "phase_key": normalized_phase_key,
                            "inventory_checksum": inventory_checksum,
                            "authorized_run_ids": _json(list(run_ids)),
                            "ceiling": approved_credit_ceiling,
                            "unit_cost": str(normalized_unit_cost),
                            "reason": reason.strip(),
                            "authorized_by": authorized_by.strip(),
                        },
                    )
                )
                .mappings()
                .one()
            )
            return self._spend_authorization_record(inserted)

    async def create_recovery_batch(self, *, authorization_id: str) -> RecoveryBatchRecord:
        """Consume one immutable offline authorization into exactly one batch."""

        async with self._engine.begin() as connection:
            authorization = (
                (
                    await connection.execute(
                        text(
                            "SELECT * FROM collection_spend_authorization "
                            "WHERE id::text = :authorization_id FOR UPDATE"
                        ),
                        {"authorization_id": authorization_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if authorization is None:
                raise LookupError(f"spend authorization {authorization_id!r} was not found")
            existing = (
                (
                    await connection.execute(
                        text(
                            "SELECT * FROM collection_recovery_batch "
                            "WHERE spend_authorization_id = CAST(:authorization_id AS uuid) "
                            "FOR UPDATE"
                        ),
                        {"authorization_id": authorization_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                return self._batch_record(existing)
            if str(authorization["status"]) != "active":
                raise ValueError("spend authorization is not active")
            organization_id = str(authorization["organization_id"])
            normalized_phase_key = str(authorization["phase_key"])
            run_ids = tuple(sorted(str(value) for value in authorization["authorized_run_ids"]))
            inventory_checksum = str(authorization["inventory_checksum"])
            approved_credit_ceiling = int(authorization["approved_credit_ceiling"])
            normalized_unit_cost = Decimal(str(authorization["unit_cost_usd"]))
            if normalized_unit_cost != SEARCH_CREDIT_UNIT_COST_USD:
                raise ValueError("spend authorization uses an unsupported Search credit rate")
            runs = list(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT id::text, organization_id::text, status,
                                   actual_credits, estimated_credits
                            FROM collection_run
                            WHERE id::text = ANY(CAST(:run_ids AS text[]))
                            FOR UPDATE
                            """
                        ),
                        {"run_ids": list(run_ids)},
                    )
                )
                .mappings()
                .all()
            )
            if len(runs) != len(run_ids):
                raise LookupError("one or more aggregate recovery batch runs were not found")
            if any(str(run["organization_id"]) != organization_id for run in runs):
                raise ValueError("all aggregate recovery batch runs must share the organization")
            already_assigned = list(
                (
                    await connection.execute(
                        text(
                            "SELECT collection_run_id::text, recovery_batch_id::text "
                            "FROM collection_recovery_batch_run "
                            "WHERE collection_run_id::text = ANY(CAST(:run_ids AS text[]))"
                        ),
                        {"run_ids": list(run_ids)},
                    )
                )
                .mappings()
                .all()
            )
            if already_assigned:
                raise ValueError("one or more phase runs are already assigned to another batch")
            accounted = sum(
                int(run["actual_credits"])
                if str(run["status"])
                in {"succeeded", "completed_with_warnings", "failed", "cancelled"}
                else int(run["estimated_credits"])
                for run in runs
            )
            if accounted > approved_credit_ceiling:
                raise ValueError(
                    f"existing phase runs account for {accounted} credits, above the "
                    f"approved ceiling {approved_credit_ceiling}"
                )
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO collection_recovery_batch (
                              organization_id, spend_authorization_id,
                              phase_key, inventory_checksum,
                              authorized_run_ids, approved_credit_ceiling, unit_cost_usd,
                              currency, reason, approved_by
                            ) VALUES (
                              CAST(:organization_id AS uuid), CAST(:authorization_id AS uuid),
                              :phase_key,
                              :inventory_checksum, CAST(:authorized_run_ids AS jsonb),
                              :ceiling, :unit_cost_usd, 'USD', :reason, :approved_by
                            ) RETURNING *
                            """
                        ),
                        {
                            "organization_id": organization_id,
                            "authorization_id": authorization_id,
                            "phase_key": normalized_phase_key,
                            "inventory_checksum": inventory_checksum,
                            "authorized_run_ids": _json(list(run_ids)),
                            "ceiling": approved_credit_ceiling,
                            "unit_cost_usd": str(normalized_unit_cost),
                            "reason": str(authorization["reason"]),
                            "approved_by": str(authorization["authorized_by"]),
                        },
                    )
                )
                .mappings()
                .one()
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO collection_recovery_batch_run (
                      recovery_batch_id, collection_run_id
                    ) SELECT CAST(:batch_id AS uuid), CAST(value AS uuid)
                      FROM unnest(CAST(:run_ids AS text[])) value
                    """
                ),
                {"batch_id": str(row["id"]), "run_ids": list(run_ids)},
            )
            updated = (
                (
                    await connection.execute(
                        text(
                            "UPDATE collection_recovery_batch SET reserved_credits = :accounted "
                            "WHERE id = CAST(:batch_id AS uuid) RETURNING *"
                        ),
                        {"batch_id": str(row["id"]), "accounted": accounted},
                    )
                )
                .mappings()
                .one()
            )
            await connection.execute(
                text(
                    "UPDATE collection_spend_authorization SET status = 'consumed', "
                    "consumed_at = now() WHERE id = CAST(:authorization_id AS uuid)"
                ),
                {"authorization_id": authorization_id},
            )
            return self._batch_record(updated)

    async def get_recovery_batch_status(self, batch_id: str) -> RecoveryBatchStatusRecord:
        """Return recomputed spend and immutable run inventory for one phase."""

        async with self._engine.connect() as connection:
            batch = await self._batch_row(connection, batch_id)
            return await self._batch_status_record(connection, batch)

    async def close_recovery_batch(self, batch_id: str) -> RecoveryBatchStatusRecord:
        """Atomically close a completed phase authorization against actual usage."""

        async with self._engine.begin() as connection:
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"collection-recovery-batch:{batch_id}"},
            )
            batch = await self._batch_row(connection, batch_id, for_update=True)
            if str(batch["status"]) == "cancelled":
                raise ValueError("a cancelled aggregate recovery batch cannot be closed")
            if str(batch["status"]) == "closed":
                return await self._batch_status_record(connection, batch)
            authorized_run_ids = {str(value) for value in (batch.get("authorized_run_ids") or [])}
            inventory_rows = await self._batch_inventory_rows(connection, batch_id)
            if {row.collection_run_id for row in inventory_rows} != authorized_run_ids:
                raise ValueError(
                    "the aggregate recovery batch run inventory is incomplete or changed"
                )
            terminal = {"succeeded", "completed_with_warnings", "failed", "cancelled"}
            if any(row.status not in terminal for row in inventory_rows):
                raise ValueError("every authorized phase run must be terminal before close")
            plan_rows = list(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT p.id::text, p.maximum_credits,
                                   p.recovery_collection_run_id::text AS recovery_run_id,
                                   r.status AS recovery_status,
                                   r.actual_credits AS recovery_actual_credits
                            FROM collection_recovery_plan p
                            LEFT JOIN collection_run r
                              ON r.id = p.recovery_collection_run_id
                            WHERE p.recovery_batch_id::text = :batch_id
                              AND p.reservation_active
                            """
                        ),
                        {"batch_id": batch_id},
                    )
                )
                .mappings()
                .all()
            )
            for plan in plan_rows:
                if plan.get("recovery_run_id") is None:
                    raise ValueError("every reserved recovery plan must be launched before close")
                if str(plan.get("recovery_status") or "") not in terminal:
                    raise ValueError("every exact recovery run must be terminal before close")
                if int(plan.get("recovery_actual_credits") or 0) > int(plan["maximum_credits"]):
                    raise ValueError(
                        "a recovery run exceeded its immutable maximum-credit reservation"
                    )
            accounted = await self._batch_accounted_credits(connection, batch_id)
            if accounted > int(batch["approved_credit_ceiling"]):
                raise ValueError("aggregate recovery usage exceeds its approved ceiling")
            closed = (
                (
                    await connection.execute(
                        text(
                            "UPDATE collection_recovery_batch "
                            "SET status = 'closed', closed_at = now(), "
                            "reserved_credits = :accounted "
                            "WHERE id::text = :batch_id RETURNING *"
                        ),
                        {"batch_id": batch_id, "accounted": accounted},
                    )
                )
                .mappings()
                .one()
            )
            return await self._batch_status_record(connection, closed)

    async def attach_run_to_recovery_batch(
        self, batch_id: str, collection_run_id: str
    ) -> RecoveryBatchRunRecord:
        """Attach a phase run to the aggregate authorization exactly once."""

        async with self._engine.begin() as connection:
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"collection-recovery-batch:{batch_id}"},
            )
            batch = await self._batch_row(connection, batch_id, for_update=True)
            if str(batch["status"]) != "open":
                raise ValueError("the aggregate recovery batch is not open")
            if collection_run_id not in {
                str(value) for value in (batch.get("authorized_run_ids") or [])
            }:
                raise ValueError(
                    "collection run is not part of the immutable authorized phase inventory"
                )
            run = (
                (
                    await connection.execute(
                        text(
                            "SELECT organization_id::text, status, actual_credits, "
                            "estimated_credits FROM collection_run WHERE id::text = :run_id"
                        ),
                        {"run_id": collection_run_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if run is None:
                raise LookupError(f"collection run {collection_run_id!r} was not found")
            if str(run["organization_id"]) != str(batch["organization_id"]):
                raise ValueError("collection run belongs to another organization")
            bound_plan_id = (
                await connection.execute(
                    text(
                        "SELECT id::text FROM collection_recovery_plan "
                        "WHERE recovery_collection_run_id::text = :run_id "
                        "AND recovery_batch_id IS NOT NULL"
                    ),
                    {"run_id": collection_run_id},
                )
            ).scalar_one_or_none()
            if bound_plan_id is not None:
                raise ValueError(
                    "an exact plan recovery run is already accounted through its plan reservation"
                )
            existing_batch_id = (
                await connection.execute(
                    text(
                        "SELECT recovery_batch_id::text FROM collection_recovery_batch_run "
                        "WHERE collection_run_id::text = :run_id"
                    ),
                    {"run_id": collection_run_id},
                )
            ).scalar_one_or_none()
            if existing_batch_id is not None and str(existing_batch_id) != batch_id:
                raise ValueError("collection run is already accounted under another batch")
            if existing_batch_id is None:
                raise ValueError(
                    "immutable batch inventory is incomplete; create a new phase key rather "
                    "than attaching a run after authorization"
                )
            accounted = await self._batch_accounted_credits(connection, batch_id)
            if accounted > int(batch["approved_credit_ceiling"]):
                raise ValueError(
                    f"aggregate recovery batch ceiling {batch['approved_credit_ceiling']} "
                    f"would be exceeded by {accounted} accounted credits"
                )
            await connection.execute(
                text(
                    "UPDATE collection_recovery_batch SET reserved_credits = :accounted "
                    "WHERE id::text = :batch_id"
                ),
                {"batch_id": batch_id, "accounted": accounted},
            )
            run_credits = (
                int(run["actual_credits"])
                if str(run["status"])
                in {"succeeded", "completed_with_warnings", "failed", "cancelled"}
                else int(run["estimated_credits"])
            )
            return RecoveryBatchRunRecord(
                recovery_batch_id=batch_id,
                collection_run_id=collection_run_id,
                accounted_credits=run_credits,
                batch_accounted_credits=accounted,
            )

    async def approve(
        self,
        base_collection_run_id: str,
        *,
        selection_checksum: str,
        approved_credit_ceiling: int,
        reason: str,
        approved_by: str,
        retailer_ids: Sequence[str] = (),
        supersedes_recovery_plan_id: str | None = None,
        recovery_batch_id: str | None = None,
        plan_mode: RecoveryPlanMode = "exact_launch",
        scope_projection_id: str | None = None,
        scope_projection_checksum: str | None = None,
    ) -> RecoveryPlanRecord:
        if not reason.strip() or not approved_by.strip():
            raise ValueError("reason and approved_by are required")
        if recovery_batch_id is None:
            raise ValueError("every recovery approval requires the authorized phase batch")
        async with self._engine.begin() as connection:
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"collection-recovery:{base_collection_run_id}"},
            )
            definition_checksum, rows = await self._base_rows(
                connection, base_collection_run_id, for_update=True
            )
            raw_preview = build_recovery_preview(
                base_collection_run_id,
                rows,
                definition_checksum=definition_checksum,
                allow_ineligible_locations=True,
            )
            scope_projection = None
            scope_projection_binding = None
            if (scope_projection_id is None) != (scope_projection_checksum is None):
                raise ValueError("scope projection id and checksum must be supplied together")
            if scope_projection_id is not None:
                scope_projection = await self._scope_projection_row(
                    connection, scope_projection_id, include_inventory=True
                )
                if str(scope_projection["projection_checksum"]) != scope_projection_checksum:
                    raise ValueError("scope projection checksum differs from the reviewed record")
                rows = self._apply_scope_projection_rows(
                    rows,
                    [scope_projection],
                    base_collection_run_id=base_collection_run_id,
                    base_snapshot_checksum=raw_preview.base_snapshot_checksum,
                )
                scope_projection_binding = self._scope_projection_binding(scope_projection)
            preview = build_recovery_preview(
                base_collection_run_id,
                rows,
                definition_checksum=definition_checksum,
                retailer_ids=retailer_ids,
                base_snapshot_checksum_override=raw_preview.base_snapshot_checksum,
                scope_projection_binding=scope_projection_binding,
            )
            if not preview.items:
                raise ValueError("the base run has no eligible failure-only recovery tasks")
            if preview.selection_checksum != selection_checksum:
                raise ValueError("the recovery selection changed; review a new preview")
            if approved_credit_ceiling != preview.maximum_credits:
                raise ValueError(
                    "the approved credit ceiling must equal the immutable recovery selection"
                )
            if plan_mode == "exact_launch":
                build_exact_recovery_task_contracts(
                    preview,
                    selection_checksum=selection_checksum,
                    base_snapshot_checksum=preview.base_snapshot_checksum,
                    approved_credit_ceiling=approved_credit_ceiling,
                )
            plan_generation = 1
            transferred_reservation = False
            if supersedes_recovery_plan_id is not None:
                superseded = await self._plan_row(
                    connection, supersedes_recovery_plan_id, for_update=True
                )
                if str(superseded["base_collection_run_id"]) != base_collection_run_id:
                    raise ValueError("the superseded plan belongs to another base run")
                if str(superseded["selection_checksum"]) != preview.selection_checksum:
                    raise ValueError("a replacement plan must preserve the exact selection")
                if str(superseded["base_snapshot_checksum"]) != preview.base_snapshot_checksum:
                    raise ValueError("a replacement plan must preserve the exact base snapshot")
                if str(superseded.get("scope_projection_id") or "") != str(
                    scope_projection_id or ""
                ) or str(superseded.get("scope_projection_checksum") or "") != str(
                    scope_projection_checksum or ""
                ):
                    raise ValueError("a replacement plan must preserve its scope projection")
                plan_generation = int(superseded["plan_generation"]) + 1
                if (
                    str(superseded["status"]) != "approved"
                    or superseded.get("recovery_collection_run_id") is not None
                ):
                    existing_replacement = (
                        (
                            await connection.execute(
                                text(
                                    """
                                    SELECT * FROM collection_recovery_plan
                                    WHERE base_collection_run_id::text = :base_run_id
                                      AND selection_checksum = :selection_checksum
                                      AND plan_generation = :plan_generation
                                    FOR UPDATE
                                    """
                                ),
                                {
                                    "base_run_id": base_collection_run_id,
                                    "selection_checksum": preview.selection_checksum,
                                    "plan_generation": plan_generation,
                                },
                            )
                        )
                        .mappings()
                        .one_or_none()
                    )
                    if existing_replacement is not None and _approval_contract(
                        existing_replacement,
                        approved_credit_ceiling=approved_credit_ceiling,
                        reason=reason,
                        approved_by=approved_by,
                        recovery_batch_id=recovery_batch_id,
                        plan_mode=plan_mode,
                        supersedes_recovery_plan_id=supersedes_recovery_plan_id,
                    ):
                        return self._plan_record(existing_replacement)
                    raise ValueError(
                        "only an approved, never-launched recovery plan can be superseded"
                    )
                if str(superseded.get("plan_mode") or "") != plan_mode:
                    raise ValueError("a replacement plan must preserve the plan mode")
                prior_batch_id = (
                    str(superseded["recovery_batch_id"])
                    if superseded.get("recovery_batch_id") is not None
                    else None
                )
                if prior_batch_id != recovery_batch_id:
                    raise ValueError("a replacement plan must preserve its recovery batch")
                if plan_mode == "exact_launch" and not bool(superseded["reservation_active"]):
                    raise ValueError("the prior plan no longer owns an active batch reservation")
                transferred_reservation = plan_mode == "exact_launch"
            base_row = (
                (
                    await connection.execute(
                        text(
                            "SELECT organization_id::text FROM collection_run "
                            "WHERE id::text = :run_id"
                        ),
                        {"run_id": base_collection_run_id},
                    )
                )
                .mappings()
                .one()
            )
            existing = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT * FROM collection_recovery_plan
                            WHERE base_collection_run_id::text = :base_run_id
                              AND selection_checksum = :selection_checksum
                              AND plan_generation = :plan_generation
                            FOR UPDATE
                            """
                        ),
                        {
                            "base_run_id": base_collection_run_id,
                            "selection_checksum": preview.selection_checksum,
                            "plan_generation": plan_generation,
                        },
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                if str(existing["status"]) in {"superseded", "cancelled"}:
                    raise ValueError("the existing recovery plan generation is no longer active")
                if not _approval_contract(
                    existing,
                    approved_credit_ceiling=approved_credit_ceiling,
                    reason=reason,
                    approved_by=approved_by,
                    recovery_batch_id=recovery_batch_id,
                    plan_mode=plan_mode,
                    supersedes_recovery_plan_id=supersedes_recovery_plan_id,
                ):
                    raise ValueError("an existing recovery plan has different immutable approval")
                return self._plan_record(existing)

            overlapping_plan = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT p.id::text, count(*) AS overlap_count
                            FROM collection_recovery_plan p
                            JOIN collection_recovery_selection s
                              ON s.recovery_plan_id = p.id
                            WHERE p.base_collection_run_id::text = :base_run_id
                              AND p.status IN ('approved','bound','ready','blocked')
                              AND (
                                CAST(:supersedes_plan_id AS text) IS NULL
                                OR p.id::text <> :supersedes_plan_id
                              )
                              AND s.canonical_request_key = ANY(CAST(:selection_keys AS text[]))
                            GROUP BY p.id
                            ORDER BY p.id
                            LIMIT 1
                            """
                        ),
                        {
                            "base_run_id": base_collection_run_id,
                            "supersedes_plan_id": supersedes_recovery_plan_id,
                            "selection_keys": [
                                item.canonical_request_key for item in preview.items
                            ],
                        },
                    )
                )
                .mappings()
                .one_or_none()
            )
            if overlapping_plan is not None:
                raise ValueError(
                    "the recovery selection overlaps active plan "
                    f"{overlapping_plan['id']} "
                    f"({overlapping_plan['overlap_count']} canonical requests)"
                )

            reservation_active = plan_mode == "exact_launch"
            assert recovery_batch_id is not None
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"collection-recovery-batch:{recovery_batch_id}"},
            )
            batch = await self._batch_row(connection, recovery_batch_id, for_update=True)
            if str(batch["organization_id"]) != str(base_row["organization_id"]):
                raise ValueError("aggregate recovery batch belongs to another organization")
            base_is_accounted = (
                await connection.execute(
                    text(
                        "SELECT 1 FROM collection_recovery_batch_run "
                        "WHERE recovery_batch_id::text = :batch_id "
                        "AND collection_run_id::text = :run_id"
                    ),
                    {"batch_id": recovery_batch_id, "run_id": base_collection_run_id},
                )
            ).scalar_one_or_none()
            if base_is_accounted is None:
                raise ValueError(
                    "base collection run must be in the immutable authorized phase inventory"
                )
            if str(batch["status"]) != "open":
                raise ValueError("the authorized phase batch is not open")
            if approved_credit_ceiling > int(batch["approved_credit_ceiling"]):
                raise ValueError(
                    "the recovery plan credit ceiling exceeds the owner-authorized phase ceiling"
                )
            if reservation_active:
                nonterminal_phase_runs = int(
                    (
                        await connection.execute(
                            text(
                                """
                                SELECT count(*)
                                FROM collection_recovery_batch_run link
                                JOIN collection_run run ON run.id = link.collection_run_id
                                WHERE link.recovery_batch_id::text = :batch_id
                                  AND run.status NOT IN (
                                    'succeeded','completed_with_warnings','failed','cancelled'
                                  )
                                """
                            ),
                            {"batch_id": recovery_batch_id},
                        )
                    ).scalar_one()
                )
                if nonterminal_phase_runs:
                    raise ValueError(
                        "all pre-existing phase runs must be terminal before reserving "
                        "new recovery credits"
                    )
                accounted = await self._batch_accounted_credits(connection, recovery_batch_id)
                requested_total = accounted + (
                    0 if transferred_reservation else preview.maximum_credits
                )
                if requested_total > int(batch["approved_credit_ceiling"]):
                    raise ValueError(
                        "aggregate recovery batch is missing, closed, or lacks credit capacity"
                    )
                await connection.execute(
                    text(
                        "UPDATE collection_recovery_batch SET reserved_credits = :reserved "
                        "WHERE id::text = :batch_id"
                    ),
                    {"batch_id": recovery_batch_id, "reserved": requested_total},
                )
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO collection_recovery_plan (
                              organization_id, base_collection_run_id,
                              selection_policy_version, selection_checksum,
                              base_snapshot_checksum, selection_scope, plan_generation,
                              supersedes_recovery_plan_id, recovery_batch_id, plan_mode,
                              reservation_active, selected_task_count,
                              maximum_credits, approved_credit_ceiling, reason, approved_by,
                              scope_projection_id, scope_projection_checksum
                            ) VALUES (
                              CAST(:organization_id AS uuid), CAST(:base_run_id AS uuid),
                              :policy, :selection_checksum, :base_snapshot_checksum,
                              CAST(:selection_scope AS jsonb), :plan_generation,
                              CAST(:supersedes_plan_id AS uuid), CAST(:recovery_batch_id AS uuid),
                              :plan_mode, :reservation_active, :selected_task_count,
                              :maximum_credits, :approved_credit_ceiling, :reason, :approved_by,
                              CAST(:scope_projection_id AS uuid), :scope_projection_checksum
                            )
                            RETURNING *
                            """
                        ),
                        {
                            "organization_id": str(base_row["organization_id"]),
                            "base_run_id": base_collection_run_id,
                            "policy": preview.selection_policy_version,
                            "selection_checksum": preview.selection_checksum,
                            "base_snapshot_checksum": preview.base_snapshot_checksum,
                            "selection_scope": _json(
                                {
                                    "retailer_ids": sorted(set(retailer_ids)),
                                    **(
                                        {"scope_projection": scope_projection_binding}
                                        if scope_projection_binding is not None
                                        else {}
                                    ),
                                }
                            ),
                            "plan_generation": plan_generation,
                            "supersedes_plan_id": supersedes_recovery_plan_id,
                            "recovery_batch_id": recovery_batch_id,
                            "plan_mode": plan_mode,
                            "reservation_active": reservation_active,
                            "selected_task_count": preview.selected_task_count,
                            "maximum_credits": preview.maximum_credits,
                            "approved_credit_ceiling": approved_credit_ceiling,
                            "reason": reason.strip(),
                            "approved_by": approved_by.strip(),
                            "scope_projection_id": scope_projection_id,
                            "scope_projection_checksum": scope_projection_checksum,
                        },
                    )
                )
                .mappings()
                .one()
            )
            plan_id = str(row["id"])
            for ordinal, item in enumerate(preview.items):
                await connection.execute(
                    text(
                        """
                        INSERT INTO collection_recovery_selection (
                          recovery_plan_id, source_task_id, ordinal,
                          canonical_request_key, selection_reason, source_snapshot
                        ) VALUES (
                          CAST(:plan_id AS uuid), CAST(:source_task_id AS uuid), :ordinal,
                          :canonical_request_key, :selection_reason,
                          CAST(:source_snapshot AS jsonb)
                        ) ON CONFLICT DO NOTHING
                        """
                    ),
                    {
                        "plan_id": plan_id,
                        "source_task_id": item.source_task_id,
                        "ordinal": ordinal,
                        "canonical_request_key": item.canonical_request_key,
                        "selection_reason": item.selection_reason,
                        "source_snapshot": _json(item.source_snapshot),
                    },
                )
            if supersedes_recovery_plan_id is not None:
                updated = await connection.execute(
                    text(
                        "UPDATE collection_recovery_plan SET status = 'superseded', "
                        "reservation_active = false "
                        "WHERE id::text = :plan_id "
                        "AND status = 'approved' AND recovery_collection_run_id IS NULL"
                    ),
                    {"plan_id": supersedes_recovery_plan_id},
                )
                if updated.rowcount != 1:
                    raise ValueError("the prior recovery plan could not be superseded atomically")
            return self._plan_record(row)

    async def approve_continuation(
        self,
        continuation_of_recovery_plan_id: str,
        *,
        selection_checksum: str,
        lineage_checksum: str,
        base_snapshot_checksum: str,
        approved_credit_ceiling: int,
        reason: str,
        approved_by: str,
        retailer_ids: Sequence[str] = (),
        recovery_batch_id: str,
    ) -> RecoveryPlanRecord:
        """Reserve and persist one unresolved-only continuation generation."""

        if not reason.strip() or not approved_by.strip():
            raise ValueError("reason and approved_by are required")
        async with self._engine.begin() as connection:
            parent_unlocked = await self._plan_row(connection, continuation_of_recovery_plan_id)
            base_run_id = str(parent_unlocked["base_collection_run_id"])
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"collection-recovery:{base_run_id}"},
            )
            parent = await self._plan_row(
                connection, continuation_of_recovery_plan_id, for_update=True
            )
            preview = await self._build_continuation_preview(
                connection,
                continuation_of_recovery_plan_id,
                retailer_ids=retailer_ids,
            )
            if not preview.items:
                raise ValueError(
                    "the terminal lineage has no unresolved evidence required for readiness"
                )
            if preview.selection_checksum != selection_checksum:
                raise ValueError("the continuation selection changed; review a new preview")
            if preview.lineage_checksum != lineage_checksum:
                raise ValueError("the continuation lineage changed; review a new preview")
            if preview.base_snapshot_checksum != base_snapshot_checksum:
                raise ValueError("the continuation no longer matches the immutable base snapshot")
            if approved_credit_ceiling != preview.maximum_credits:
                raise ValueError(
                    "the approved credit ceiling must equal the immutable continuation selection"
                )
            build_exact_recovery_task_contracts(
                preview,
                selection_checksum=selection_checksum,
                base_snapshot_checksum=base_snapshot_checksum,
                approved_credit_ceiling=approved_credit_ceiling,
            )
            parent_batch_id = str(parent.get("recovery_batch_id") or "")
            if not parent_batch_id or parent_batch_id != recovery_batch_id:
                raise ValueError("continuation must preserve its parent's immutable recovery batch")
            continuation_depth = int(parent.get("continuation_depth") or 0) + 1
            if continuation_depth > 32:
                raise ValueError("continuation lineage exceeds the governed depth limit")

            existing = (
                (
                    await connection.execute(
                        text(
                            "SELECT * FROM collection_recovery_plan "
                            "WHERE continuation_of_recovery_plan_id::text = :parent_plan_id "
                            "AND status NOT IN ('cancelled','superseded') FOR UPDATE"
                        ),
                        {"parent_plan_id": continuation_of_recovery_plan_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            expected_scope: dict[str, Any] = {
                "retailer_ids": sorted(set(str(value) for value in retailer_ids)),
                "lineage_plan_ids": list(preview.lineage_plan_ids),
                "lineage_checksum": preview.lineage_checksum,
            }
            if parent.get("scope_projection_id") is not None:
                expected_scope["scope_projection"] = {
                    "id": str(parent["scope_projection_id"]),
                    "retailer_id": str(
                        dict(parent.get("selection_scope") or {})["scope_projection"]["retailer_id"]
                    ),
                    "projection_checksum": str(parent["scope_projection_checksum"]),
                }
            if existing is not None:
                same = bool(
                    str(existing["selection_checksum"]) == preview.selection_checksum
                    and str(existing["base_snapshot_checksum"]) == preview.base_snapshot_checksum
                    and int(existing["approved_credit_ceiling"]) == approved_credit_ceiling
                    and str(existing["recovery_batch_id"]) == recovery_batch_id
                    and str(existing["reason"]) == reason.strip()
                    and str(existing["approved_by"]) == approved_by.strip()
                    and dict(existing.get("selection_scope") or {}) == expected_scope
                )
                if same:
                    return self._plan_record(existing)
                raise ValueError("continuation parent already has a different active child")

            lineage_ids = list(preview.lineage_plan_ids)
            overlapping_plan = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT p.id::text, count(*) AS overlap_count
                            FROM collection_recovery_plan p
                            JOIN collection_recovery_selection s
                              ON s.recovery_plan_id = p.id
                            WHERE p.base_collection_run_id::text = :base_run_id
                              AND p.status IN ('approved','bound','ready','blocked')
                              AND NOT (p.id::text = ANY(CAST(:lineage_ids AS text[])))
                              AND s.canonical_request_key = ANY(CAST(:selection_keys AS text[]))
                            GROUP BY p.id ORDER BY p.id LIMIT 1
                            """
                        ),
                        {
                            "base_run_id": base_run_id,
                            "lineage_ids": lineage_ids,
                            "selection_keys": [
                                item.canonical_request_key for item in preview.items
                            ],
                        },
                    )
                )
                .mappings()
                .one_or_none()
            )
            if overlapping_plan is not None:
                raise ValueError(
                    "continuation selection overlaps non-lineage plan "
                    f"{overlapping_plan['id']} ({overlapping_plan['overlap_count']} requests)"
                )

            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"collection-recovery-batch:{recovery_batch_id}"},
            )
            batch = await self._batch_row(connection, recovery_batch_id, for_update=True)
            if str(batch["organization_id"]) != str(parent["organization_id"]):
                raise ValueError("continuation batch belongs to another organization")
            if str(batch["status"]) != "open":
                raise ValueError("the authorized phase batch is not open")
            base_is_accounted = (
                await connection.execute(
                    text(
                        "SELECT 1 FROM collection_recovery_batch_run "
                        "WHERE recovery_batch_id::text = :batch_id "
                        "AND collection_run_id::text = :run_id"
                    ),
                    {"batch_id": recovery_batch_id, "run_id": base_run_id},
                )
            ).scalar_one_or_none()
            if base_is_accounted is None:
                raise ValueError(
                    "base collection run is outside the immutable authorized inventory"
                )
            accounted = await self._batch_accounted_credits(connection, recovery_batch_id)
            requested_total = accounted + preview.maximum_credits
            if requested_total > int(batch["approved_credit_ceiling"]):
                raise ValueError(
                    "aggregate recovery batch lacks remaining credits for this continuation"
                )
            await connection.execute(
                text(
                    "UPDATE collection_recovery_batch SET reserved_credits = :reserved "
                    "WHERE id::text = :batch_id"
                ),
                {"batch_id": recovery_batch_id, "reserved": requested_total},
            )
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO collection_recovery_plan (
                              organization_id, base_collection_run_id,
                              selection_policy_version, selection_checksum,
                              base_snapshot_checksum, selection_scope, plan_generation,
                              recovery_batch_id, plan_mode, reservation_active,
                              selected_task_count, maximum_credits,
                              approved_credit_ceiling, reason, approved_by,
                              continuation_of_recovery_plan_id, continuation_depth,
                              scope_projection_id, scope_projection_checksum
                            ) VALUES (
                              CAST(:organization_id AS uuid), CAST(:base_run_id AS uuid),
                              :policy, :selection_checksum, :base_snapshot_checksum,
                              CAST(:selection_scope AS jsonb), :plan_generation,
                              CAST(:recovery_batch_id AS uuid), 'exact_launch', true,
                              :selected_task_count, :maximum_credits,
                              :approved_credit_ceiling, :reason, :approved_by,
                              CAST(:parent_plan_id AS uuid), :continuation_depth,
                              CAST(:scope_projection_id AS uuid), :scope_projection_checksum
                            ) RETURNING *
                            """
                        ),
                        {
                            "organization_id": str(parent["organization_id"]),
                            "base_run_id": base_run_id,
                            "policy": CONTINUATION_SELECTION_POLICY_VERSION,
                            "selection_checksum": preview.selection_checksum,
                            "base_snapshot_checksum": preview.base_snapshot_checksum,
                            "selection_scope": _json(expected_scope),
                            "plan_generation": int(parent["plan_generation"]) + 1,
                            "recovery_batch_id": recovery_batch_id,
                            "selected_task_count": preview.selected_task_count,
                            "maximum_credits": preview.maximum_credits,
                            "approved_credit_ceiling": approved_credit_ceiling,
                            "reason": reason.strip(),
                            "approved_by": approved_by.strip(),
                            "parent_plan_id": continuation_of_recovery_plan_id,
                            "continuation_depth": continuation_depth,
                            "scope_projection_id": (
                                str(parent["scope_projection_id"])
                                if parent.get("scope_projection_id") is not None
                                else None
                            ),
                            "scope_projection_checksum": (
                                str(parent["scope_projection_checksum"])
                                if parent.get("scope_projection_checksum") is not None
                                else None
                            ),
                        },
                    )
                )
                .mappings()
                .one()
            )
            plan_id = str(row["id"])
            await connection.execute(
                text(
                    """
                    INSERT INTO collection_recovery_selection (
                      recovery_plan_id, source_task_id, ordinal,
                      canonical_request_key, selection_reason, source_snapshot
                    ) VALUES (
                      CAST(:plan_id AS uuid), CAST(:source_task_id AS uuid), :ordinal,
                      :canonical_request_key, :selection_reason,
                      CAST(:source_snapshot AS jsonb)
                    )
                    """
                ),
                [
                    {
                        "plan_id": plan_id,
                        "source_task_id": item.source_task_id,
                        "ordinal": ordinal,
                        "canonical_request_key": item.canonical_request_key,
                        "selection_reason": item.selection_reason,
                        "source_snapshot": _json(item.source_snapshot),
                    }
                    for ordinal, item in enumerate(preview.items)
                ],
            )
            return self._plan_record(row)

    async def launch_exact_recovery(self, plan_id: str) -> RecoveryLaunchRecord:
        """Create one idempotent, gate-free run containing only approved failures."""

        async with self._engine.begin() as connection:
            base_run_id = (
                await connection.execute(
                    text(
                        "SELECT base_collection_run_id::text "
                        "FROM collection_recovery_plan WHERE id::text = :plan_id"
                    ),
                    {"plan_id": plan_id},
                )
            ).scalar_one_or_none()
            if base_run_id is None:
                raise LookupError(f"collection recovery plan {plan_id!r} was not found")
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"collection-recovery:{base_run_id}"},
            )
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"collection-recovery-plan:{plan_id}"},
            )
            plan = await self._plan_row(connection, plan_id, for_update=True)
            existing_run_id = plan.get("recovery_collection_run_id")
            if existing_run_id is not None:
                manifest = dict(plan.get("binding_manifest") or {})
                if manifest.get("launch_mode") not in {
                    "exact_failure_only",
                    "exact_unresolved_continuation",
                }:
                    raise ValueError("recovery plan is already bound to an externally created run")
                return await self._launch_record(
                    connection,
                    plan_id,
                    str(existing_run_id),
                    reused_existing_run=True,
                )
            if str(plan["status"]) != "approved":
                raise ValueError(f"a {plan['status']} recovery plan cannot be launched")
            if str(plan.get("plan_mode") or "") != "exact_launch":
                raise ValueError("legacy-adoption plans cannot launch provider work")
            if plan.get("recovery_batch_id") is None or not bool(plan["reservation_active"]):
                raise ValueError("exact recovery plan has no active aggregate batch reservation")
            batch = await self._batch_row(
                connection, str(plan["recovery_batch_id"]), for_update=True
            )
            if str(batch["status"]) != "open":
                raise ValueError("the aggregate recovery batch is not open")
            accounted = await self._batch_accounted_credits(
                connection, str(plan["recovery_batch_id"])
            )
            if accounted > int(batch["approved_credit_ceiling"]):
                raise ValueError("the aggregate recovery batch credit ceiling is exceeded")

            base_run_id = str(plan["base_collection_run_id"])
            definition_checksum, base_rows = await self._base_rows(
                connection, base_run_id, for_update=True
            )
            raw_preview = build_recovery_preview(
                base_run_id,
                base_rows,
                definition_checksum=definition_checksum,
                allow_ineligible_locations=True,
            )
            scope = dict(plan.get("selection_scope") or {})
            retailer_ids = tuple(str(value) for value in scope.get("retailer_ids", []))
            continuation_parent = plan.get("continuation_of_recovery_plan_id")
            if continuation_parent is None:
                scope_projection_binding = None
                if plan.get("scope_projection_id") is not None:
                    projection = await self._scope_projection_row(
                        connection, str(plan["scope_projection_id"]), include_inventory=True
                    )
                    if str(projection["projection_checksum"]) != str(
                        plan.get("scope_projection_checksum") or ""
                    ):
                        raise ValueError("recovery plan scope projection checksum changed")
                    base_rows = self._apply_scope_projection_rows(
                        base_rows,
                        [projection],
                        base_collection_run_id=base_run_id,
                        base_snapshot_checksum=raw_preview.base_snapshot_checksum,
                    )
                    scope_projection_binding = self._scope_projection_binding(projection)
                    if scope.get("scope_projection") != scope_projection_binding:
                        raise ValueError("recovery plan scope-projection selection binding changed")
                preview: RecoverySelectionPreview | ContinuationSelectionPreview = (
                    build_recovery_preview(
                        base_run_id,
                        base_rows,
                        definition_checksum=definition_checksum,
                        retailer_ids=retailer_ids,
                        base_snapshot_checksum_override=raw_preview.base_snapshot_checksum,
                        scope_projection_binding=scope_projection_binding,
                    )
                )
                launch_mode = "exact_failure_only"
            else:
                preview = await self._build_continuation_preview(
                    connection,
                    str(continuation_parent),
                    retailer_ids=retailer_ids,
                )
                if scope.get("lineage_checksum") != preview.lineage_checksum:
                    raise ValueError("approved continuation lineage checksum changed")
                if tuple(scope.get("lineage_plan_ids") or ()) != preview.lineage_plan_ids:
                    raise ValueError("approved continuation lineage plan order changed")
                launch_mode = "exact_unresolved_continuation"
            contracts = build_exact_recovery_task_contracts(
                preview,
                selection_checksum=str(plan["selection_checksum"]),
                base_snapshot_checksum=str(plan["base_snapshot_checksum"]),
                approved_credit_ceiling=int(plan["approved_credit_ceiling"]),
            )
            if len(contracts) != int(plan["selected_task_count"]):
                raise ValueError("the approved recovery task count no longer matches its plan")
            stored_selections = list(
                (
                    await connection.execute(
                        text(
                            "SELECT source_task_id::text, ordinal, canonical_request_key, "
                            "selection_reason, source_snapshot "
                            "FROM collection_recovery_selection "
                            "WHERE recovery_plan_id::text = :plan_id ORDER BY ordinal"
                        ),
                        {"plan_id": plan_id},
                    )
                )
                .mappings()
                .all()
            )
            expected_selections = [
                {
                    "source_task_id": item.source_task_id,
                    "ordinal": ordinal,
                    "canonical_request_key": item.canonical_request_key,
                    "selection_reason": item.selection_reason,
                    "source_snapshot": item.source_snapshot,
                }
                for ordinal, item in enumerate(preview.items)
            ]
            actual_selections = [
                {
                    "source_task_id": str(row["source_task_id"]),
                    "ordinal": int(row["ordinal"]),
                    "canonical_request_key": str(row["canonical_request_key"]),
                    "selection_reason": str(row["selection_reason"]),
                    "source_snapshot": dict(row["source_snapshot"]),
                }
                for row in stored_selections
            ]
            if actual_selections != expected_selections:
                raise ValueError("stored recovery selections differ from the approved checksum")

            base_contract = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT r.organization_id::text, r.definition_version_id::text,
                                   v.definition_id::text, v.config
                            FROM collection_run r
                            JOIN collection_definition_version v
                              ON v.id = r.definition_version_id
                            WHERE r.id::text = :run_id
                            """
                        ),
                        {"run_id": base_run_id},
                    )
                )
                .mappings()
                .one()
            )
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"collection-budget:{base_contract['definition_id']}"},
            )
            await self._check_recovery_budgets(
                connection,
                definition_id=str(base_contract["definition_id"]),
                definition_config=dict(base_contract["config"]),
                requested_credits=preview.maximum_credits,
                approved_credit_ceiling=int(plan["approved_credit_ceiling"]),
            )
            recovery_run_id = str(
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO collection_run (
                              organization_id, definition_version_id, status,
                              estimated_pages, estimated_credits, trigger_type,
                              availability_gate_status, availability_gate_config
                            ) VALUES (
                              CAST(:organization_id AS uuid),
                              CAST(:definition_version_id AS uuid), 'queued',
                              :estimated_pages, :estimated_credits, 'manual',
                              'skipped', '{}'::jsonb
                            ) RETURNING id::text
                            """
                        ),
                        {
                            "organization_id": str(base_contract["organization_id"]),
                            "definition_version_id": str(base_contract["definition_version_id"]),
                            "estimated_pages": len(contracts),
                            "estimated_credits": preview.maximum_credits,
                        },
                    )
                ).scalar_one()
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO collection_task (
                      collection_run_id, retailer_id, retailer_location_id, adapter_id,
                      location_scope_key, zipcode, store_number, page_number, max_pages,
                      stop_on_empty, stop_on_short_page, credits_per_success,
                      request_payload, request_fingerprint, priority, max_attempts, is_preflight
                    ) VALUES (
                      CAST(:collection_run_id AS uuid), :retailer_id,
                      CAST(:retailer_location_id AS uuid), :adapter_id,
                      :location_scope_key, :zipcode, :store_number, :page_number, :max_pages,
                      :stop_on_empty, :stop_on_short_page, :credits_per_success,
                      CAST(:request_payload AS jsonb), :request_fingerprint,
                      :priority, :max_attempts, false
                    )
                    """
                ),
                [
                    {
                        **contract,
                        "collection_run_id": recovery_run_id,
                        "request_payload": _json(contract["request_payload"]),
                    }
                    for contract in contracts
                ],
            )
            recovery_rows = await self._task_rows(connection, recovery_run_id)
            if len(recovery_rows) != len(contracts):
                raise RuntimeError("exact recovery task insertion was incomplete")
            binding_manifest = {
                "schema_version": "1.0.0",
                "binding_mode": "exact",
                "launch_mode": launch_mode,
                "recovery_task_count": len(recovery_rows),
                "approved_selection_count": len(recovery_rows),
                "bound_maximum_provider_attempts": preview.maximum_provider_attempts,
                "bound_maximum_credits": preview.maximum_credits,
                "approved_selection_maximum_credits": preview.maximum_credits,
                "credit_ceiling_applies_to": "complete_recovery_run",
                "recovery_task_contract_checksum": canonical_checksum(
                    {
                        "tasks": [
                            {
                                "canonical_request_key": key,
                                "task_id": str(row["id"]),
                                "snapshot": _task_contract_snapshot(row),
                            }
                            for key, row in sorted(
                                self._unique_tasks(recovery_rows, "launched recovery").items()
                            )
                        ]
                    }
                ),
                "redundant_evidence": [],
                "adopted_gap_replacements": [],
                "continuation_lineage": (
                    {
                        "continuation_of_recovery_plan_id": str(continuation_parent),
                        "lineage_plan_ids": list(preview.lineage_plan_ids),
                        "lineage_checksum": preview.lineage_checksum,
                    }
                    if isinstance(preview, ContinuationSelectionPreview)
                    else None
                ),
            }
            updated = await connection.execute(
                text(
                    """
                    UPDATE collection_recovery_plan
                    SET recovery_collection_run_id = CAST(:recovery_run_id AS uuid),
                        status = 'bound', bound_at = now(),
                        binding_manifest = CAST(:binding_manifest AS jsonb)
                    WHERE id::text = :plan_id AND status = 'approved'
                      AND recovery_collection_run_id IS NULL
                    """
                ),
                {
                    "plan_id": plan_id,
                    "recovery_run_id": recovery_run_id,
                    "binding_manifest": _json(binding_manifest),
                },
            )
            if updated.rowcount != 1:
                raise RuntimeError("recovery plan binding was not committed with its run")
            return await self._launch_record(
                connection,
                plan_id,
                recovery_run_id,
                reused_existing_run=False,
            )

    async def bind_recovery_run(
        self,
        plan_id: str,
        recovery_run_id: str,
        *,
        binding_mode: BindingMode = "exact",
    ) -> RecoveryPlanRecord:
        """Bind a recovery run after exact or audited legacy validation."""

        if binding_mode != "legacy_operational_adoption":
            raise ValueError(
                "exact recovery plans may be bound only by the checksum-bound launch path"
            )

        async with self._engine.begin() as connection:
            base_run_id = (
                await connection.execute(
                    text(
                        "SELECT base_collection_run_id::text "
                        "FROM collection_recovery_plan WHERE id::text = :plan_id"
                    ),
                    {"plan_id": plan_id},
                )
            ).scalar_one_or_none()
            if base_run_id is None:
                raise LookupError(f"collection recovery plan {plan_id!r} was not found")
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"collection-recovery:{base_run_id}"},
            )
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"collection-recovery-plan:{plan_id}"},
            )
            plan = await self._plan_row(connection, plan_id, for_update=True)
            if str(plan["status"]) in {"superseded", "cancelled", "blocked"}:
                raise ValueError(f"a {plan['status']} recovery plan cannot be bound")
            if (
                binding_mode == "legacy_operational_adoption"
                and str(plan.get("plan_mode") or "") != "legacy_adoption"
            ):
                raise ValueError("legacy operational adoption requires a legacy-adoption plan")
            if plan.get("recovery_batch_id") is None:
                raise ValueError("legacy adoption has no immutable phase-spend lineage")
            recovery_status = (
                await connection.execute(
                    text(
                        "SELECT status FROM collection_run "
                        "WHERE id::text = :recovery_run_id FOR UPDATE"
                    ),
                    {"recovery_run_id": recovery_run_id},
                )
            ).scalar_one_or_none()
            if recovery_status is None:
                raise LookupError(f"collection run {recovery_run_id!r} was not found")
            if str(recovery_status) not in {
                "succeeded",
                "completed_with_warnings",
                "failed",
                "cancelled",
            }:
                raise ValueError("legacy operational adoption requires a terminal recovery run")
            batch_id = str(plan["recovery_batch_id"])
            batch = await self._batch_row(connection, batch_id, for_update=True)
            if str(batch["organization_id"]) != str(plan["organization_id"]):
                raise ValueError("legacy recovery batch belongs to another organization")
            accounted_ids = set(
                (
                    await connection.execute(
                        text(
                            "SELECT collection_run_id::text "
                            "FROM collection_recovery_batch_run "
                            "WHERE recovery_batch_id::text = :batch_id "
                            "AND collection_run_id::text = ANY(CAST(:run_ids AS text[]))"
                        ),
                        {
                            "batch_id": batch_id,
                            "run_ids": [str(plan["base_collection_run_id"]), recovery_run_id],
                        },
                    )
                ).scalars()
            )
            if accounted_ids != {str(plan["base_collection_run_id"]), recovery_run_id}:
                raise ValueError(
                    "base and adopted recovery runs must both be in the immutable "
                    "authorized phase inventory"
                )
            base_rows = await self._task_rows(connection, str(plan["base_collection_run_id"]))
            recovery_rows = await self._task_rows(connection, recovery_run_id)
            identity_provenance = request_identity_provenance_manifest(
                {"base": base_rows, "recovery": recovery_rows}
            )
            selected_keys = set(
                (
                    await connection.execute(
                        text(
                            "SELECT canonical_request_key FROM collection_recovery_selection "
                            "WHERE recovery_plan_id::text = :plan_id"
                        ),
                        {"plan_id": plan_id},
                    )
                ).scalars()
            )
            base_by_key = self._unique_tasks(base_rows, "base")
            recovery_by_key = self._unique_tasks(recovery_rows, "recovery")
            recovery_keys = set(recovery_by_key)
            missing_keys = selected_keys - recovery_keys
            extra_keys = recovery_keys - selected_keys
            if missing_keys:
                raise ValueError(
                    f"recovery task set is missing approved requests (missing={len(missing_keys)})"
                )
            redundant: list[dict[str, Any]] = []
            adopted_replacements: list[dict[str, Any]] = []
            if extra_keys and binding_mode != "legacy_operational_adoption":
                raise ValueError(
                    "recovery contains requests outside the approved selection; "
                    "legacy operational evidence requires explicit adoption"
                )
            for key in sorted(extra_keys):
                base_task = base_by_key.get(key)
                if base_task is None:
                    raise ValueError("legacy recovery contains a request outside the base run")
                recovery_task = recovery_by_key[key]
                base_outcome = evidence_outcome(base_task)
                recovery_outcome = evidence_outcome(recovery_task)
                entry = {
                    "canonical_request_key": key,
                    "base_task_id": str(base_task["id"]),
                    "base_outcome": base_outcome,
                    "recovery_task_id": str(recovery_task["id"]),
                    "recovery_outcome": recovery_outcome,
                }
                if base_outcome == "usable_success":
                    entry["resolution"] = "base_success_retained"
                    redundant.append(entry)
                elif _evidence_strength(recovery_outcome) > _evidence_strength(base_outcome):
                    entry["resolution"] = (
                        "recovery_fills_base_gap"
                        if recovery_outcome == "usable_success"
                        else "stronger_recovery_evidence_selected"
                    )
                    adopted_replacements.append(entry)
                else:
                    entry["resolution"] = "base_evidence_retained"
                    redundant.append(entry)
            bound_maximum_provider_attempts = sum(int(row["max_attempts"]) for row in recovery_rows)
            bound_maximum_credits = sum(
                int(row["credits_per_success"]) * int(row["max_attempts"]) for row in recovery_rows
            )
            binding_manifest = {
                "schema_version": "1.0.0",
                "binding_mode": binding_mode,
                "recovery_task_count": len(recovery_rows),
                "recovery_task_contract_checksum": canonical_checksum(
                    {
                        "tasks": [
                            {
                                "canonical_request_key": key,
                                "task_id": str(recovery_by_key[key]["id"]),
                                "snapshot": _task_contract_snapshot(recovery_by_key[key]),
                            }
                            for key in sorted(recovery_by_key)
                        ]
                    }
                ),
                "approved_selection_count": len(selected_keys),
                "bound_maximum_provider_attempts": bound_maximum_provider_attempts,
                "bound_maximum_credits": bound_maximum_credits,
                "approved_selection_maximum_credits": int(plan["maximum_credits"]),
                "credit_ceiling_applies_to": (
                    "approved_selection_only_preexisting_operational_run"
                ),
                "identity_provenance": identity_provenance,
                "redundant_evidence": redundant,
                "adopted_gap_replacements": adopted_replacements,
            }
            run_contracts = list(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT r.id::text, r.organization_id::text, r.status,
                                   v.config, v.geography_resolution_id::text
                            FROM collection_run r
                            JOIN collection_definition_version v
                              ON v.id = r.definition_version_id
                            WHERE r.id::text IN (:base_run_id, :recovery_run_id)
                            """
                        ),
                        {
                            "base_run_id": str(plan["base_collection_run_id"]),
                            "recovery_run_id": recovery_run_id,
                        },
                    )
                )
                .mappings()
                .all()
            )
            contract_by_run = {str(row["id"]): row for row in run_contracts}
            if recovery_run_id not in contract_by_run:
                raise LookupError(f"collection run {recovery_run_id!r} was not found")
            base_run_id = str(plan["base_collection_run_id"])
            base_contract = contract_by_run.get(base_run_id)
            recovery_contract = contract_by_run[recovery_run_id]
            if base_contract is None:
                raise LookupError(f"collection run {base_run_id!r} was not found")
            if str(recovery_contract["organization_id"]) != str(plan["organization_id"]):
                raise ValueError("recovery run belongs to a different organization")
            if binding_mode == "legacy_operational_adoption" and str(
                recovery_contract["status"]
            ) not in {"succeeded", "completed_with_warnings", "failed", "cancelled"}:
                raise ValueError("legacy operational adoption requires a terminal recovery run")
            base_config = dict(base_contract["config"])
            recovery_config = dict(recovery_contract["config"])
            if base_config.get("product_pack") != recovery_config.get("product_pack"):
                raise ValueError("recovery run uses a different Product Pack contract")
            if base_config.get("benchmark_retailer") != recovery_config.get("benchmark_retailer"):
                raise ValueError("recovery run uses a different benchmark retailer")
            if outbound_query_contract(base_config) != outbound_query_contract(recovery_config):
                raise ValueError("recovery run uses a different Search query contract")
            base_geography = base_contract.get("geography_resolution_id")
            recovery_geography = recovery_contract.get("geography_resolution_id")
            if (str(base_geography) if base_geography is not None else None) != (
                str(recovery_geography) if recovery_geography is not None else None
            ):
                raise ValueError("recovery run uses a different frozen geography")
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            UPDATE collection_recovery_plan
                            SET recovery_collection_run_id = CAST(:recovery_run_id AS uuid),
                                status = 'bound', bound_at = now(),
                                binding_manifest = CAST(:binding_manifest AS jsonb)
                            WHERE id::text = :plan_id
                              AND recovery_collection_run_id IS NULL
                            RETURNING *
                            """
                        ),
                        {
                            "plan_id": plan_id,
                            "recovery_run_id": recovery_run_id,
                            "binding_manifest": _json(binding_manifest),
                        },
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                if str(plan.get("recovery_collection_run_id") or "") != recovery_run_id:
                    raise ValueError("recovery plan is already bound to another run")
                if dict(plan.get("binding_manifest") or {}) != binding_manifest:
                    raise ValueError("recovery plan is already bound under another contract")
                row = plan
            return self._plan_record(row)

    async def materialize(
        self,
        base_collection_run_id: str,
        recovery_plan_ids: Sequence[str],
        scope_projection_ids: Sequence[str] = (),
    ) -> CompositeInputSetRecord:
        """Assemble a base run and one or more immutable recovery components."""

        plan_ids = tuple(sorted(set(recovery_plan_ids)))
        projection_ids = tuple(sorted(set(scope_projection_ids)))
        if not plan_ids:
            raise ValueError("at least one recovery plan is required")
        async with self._engine.begin() as connection:
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"collection-recovery:{base_collection_run_id}"},
            )
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"composite-evidence:{base_collection_run_id}"},
            )
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": "analysis-input-materialization"},
            )
            plans = list(
                (
                    await connection.execute(
                        text(
                            "SELECT * FROM collection_recovery_plan "
                            "WHERE id::text = ANY(CAST(:plan_ids AS text[])) "
                            "ORDER BY continuation_depth, plan_generation, "
                            "selection_checksum, id FOR UPDATE"
                        ),
                        {"plan_ids": list(plan_ids)},
                    )
                )
                .mappings()
                .all()
            )
            if len(plans) != len(plan_ids):
                raise LookupError("one or more collection recovery plans were not found")
            for plan in plans:
                if str(plan["base_collection_run_id"]) != base_collection_run_id:
                    raise ValueError("all recovery plans must belong to the same base run")
                if str(plan["status"]) not in {"bound", "ready"}:
                    raise ValueError(
                        f"recovery plan {plan['id']} is not an active bound/ready generation"
                    )
                if plan.get("recovery_collection_run_id") is None:
                    raise ValueError(f"recovery plan {plan['id']} has not been bound")

            plans_by_id = {str(plan["id"]): plan for plan in plans}
            ancestor_ids_by_plan: dict[str, set[str]] = {}
            for plan in plans:
                plan_id = str(plan["id"])
                ancestors: set[str] = set()
                parent_id = (
                    str(plan["continuation_of_recovery_plan_id"])
                    if plan.get("continuation_of_recovery_plan_id") is not None
                    else None
                )
                while parent_id is not None:
                    if parent_id in ancestors:
                        raise ValueError("recovery continuation lineage contains a cycle")
                    parent = plans_by_id.get(parent_id)
                    if parent is None:
                        raise ValueError(
                            "materialization requires every continuation ancestor plan"
                        )
                    ancestors.add(parent_id)
                    parent_id = (
                        str(parent["continuation_of_recovery_plan_id"])
                        if parent.get("continuation_of_recovery_plan_id") is not None
                        else None
                    )
                ancestor_ids_by_plan[plan_id] = ancestors

            recovery_run_ids = tuple(str(plan["recovery_collection_run_id"]) for plan in plans)
            if len(set(recovery_run_ids)) != len(recovery_run_ids):
                raise ValueError("a recovery run cannot satisfy more than one component plan")
            run_ids = [base_collection_run_id, *recovery_run_ids]
            run_rows = list(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT r.id::text, r.status, r.actual_credits,
                                   r.estimated_credits,
                                   r.organization_id::text,
                                   r.availability_gate_config,
                                   v.checksum AS definition_checksum, v.config
                            FROM collection_run r
                            JOIN collection_definition_version v
                              ON v.id = r.definition_version_id
                            WHERE r.id::text = ANY(CAST(:run_ids AS text[]))
                            """
                        ),
                        {"run_ids": run_ids},
                    )
                )
                .mappings()
                .all()
            )
            by_run = {str(row["id"]): row for row in run_rows}
            if set(by_run) != set(run_ids):
                raise LookupError("base or recovery collection run was not found")
            if any(
                str(by_run[run_id]["status"])
                not in {"succeeded", "completed_with_warnings", "failed", "cancelled"}
                for run_id in recovery_run_ids
            ):
                raise ValueError("every recovery run must be terminal")
            over_budget_recovery_runs = [
                run_id
                for run_id in recovery_run_ids
                if int(by_run[run_id]["actual_credits"]) > int(by_run[run_id]["estimated_credits"])
            ]
            if over_budget_recovery_runs:
                raise ValueError(
                    "terminal recovery actual credits exceeded the reserved hard upper bound"
                )

            raw_base_rows = await self._task_rows(connection, base_collection_run_id)
            raw_preview = build_recovery_preview(
                base_collection_run_id,
                raw_base_rows,
                definition_checksum=str(by_run[base_collection_run_id]["definition_checksum"]),
                allow_ineligible_locations=True,
            )
            projections = [
                await self._scope_projection_row(connection, projection_id, include_inventory=True)
                for projection_id in projection_ids
            ]
            immutable_config = dict(by_run[base_collection_run_id]["config"] or {})
            enabled_retailers = {
                str(item["retailer_id"])
                for item in immutable_config.get("retailers", [])
                if isinstance(item, Mapping) and bool(item.get("enabled"))
            }
            benchmark_retailer = str(immutable_config.get("benchmark_retailer") or "")
            invalid_projection_retailers = sorted(
                str(projection["retailer_id"])
                for projection in projections
                if str(projection["retailer_id"]) not in enabled_retailers
                or str(projection["retailer_id"]) == benchmark_retailer
            )
            if invalid_projection_retailers:
                raise ValueError(
                    "scope projections must target enabled non-benchmark retailers "
                    f"({', '.join(invalid_projection_retailers)})"
                )
            plan_projection_ids = {
                str(plan["scope_projection_id"])
                for plan in plans
                if plan.get("scope_projection_id") is not None
            }
            if not plan_projection_ids.issubset(set(projection_ids)):
                raise ValueError("materialization requires every recovery-plan scope projection")
            projection_by_id = {
                str(projection.get("projection_id") or projection["id"]): projection
                for projection in projections
            }
            for plan in plans:
                if plan.get("scope_projection_id") is None:
                    continue
                projection = projection_by_id[str(plan["scope_projection_id"])]
                if str(plan.get("scope_projection_checksum") or "") != str(
                    projection["projection_checksum"]
                ):
                    raise ValueError("recovery plan differs from its reviewed scope projection")
            base_rows = self._apply_scope_projection_rows(
                raw_base_rows,
                projections,
                base_collection_run_id=base_collection_run_id,
                base_snapshot_checksum=raw_preview.base_snapshot_checksum,
            )
            scope_projection_bindings = [
                self._scope_projection_binding(projection) for projection in projections
            ]
            scope_projection_bindings.sort(key=lambda row: (row["retailer_id"], row["id"]))
            scope_projection_context = (
                {"projections": scope_projection_bindings} if scope_projection_bindings else None
            )
            identity_rows_by_component: dict[str, Sequence[TaskMapping]] = {"base": base_rows}
            base_by_key = self._unique_tasks(base_rows, "base")
            full_preview = build_recovery_preview(
                base_collection_run_id,
                base_rows,
                definition_checksum=str(by_run[base_collection_run_id]["definition_checksum"]),
                allow_ineligible_locations=True,
                base_snapshot_checksum_override=raw_preview.base_snapshot_checksum,
                scope_projection_binding=scope_projection_context,
            )
            unavailability_rows = list(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT id::text, retailer_id, base_snapshot_checksum,
                                   reason, approved_by
                            FROM collection_retailer_unavailability_approval
                            WHERE base_collection_run_id::text = :run_id
                              AND status = 'active'
                            """
                        ),
                        {"run_id": base_collection_run_id},
                    )
                )
                .mappings()
                .all()
            )
            stale_unavailability = [
                str(row["retailer_id"])
                for row in unavailability_rows
                if str(row["base_snapshot_checksum"]) != raw_preview.base_snapshot_checksum
            ]
            if stale_unavailability:
                raise ValueError(
                    "retailer-unavailability approval does not match the immutable base "
                    f"snapshot ({', '.join(sorted(stale_unavailability))})"
                )
            unavailability_approvals = {
                str(row["retailer_id"]): dict(row) for row in unavailability_rows
            }
            scope_projection_dispositions = {
                str(projection["retailer_id"]): {
                    **self._scope_projection_binding(projection),
                    "projection_kind": str(projection["projection_kind"]),
                    "raw_task_count": int(projection["raw_task_count"]),
                    "retained_task_count": int(projection["retained_task_count"]),
                    "excluded_task_count": int(projection["excluded_task_count"]),
                    "raw_location_count": int(projection["raw_location_count"]),
                    "retained_location_count": int(projection["retained_location_count"]),
                    "excluded_location_count": int(projection["excluded_location_count"]),
                    "raw_task_retention_ratio": str(projection["raw_task_retention_ratio"]),
                    "governed_coverage_ratio": str(projection["governed_coverage_ratio"]),
                    "minimum_scoreable_coverage": str(projection["minimum_scoreable_coverage"]),
                    "scorecard_disposition": str(projection["scorecard_disposition"]),
                }
                for projection in projections
            }
            conflicting_approvals = sorted(
                retailer_id
                for retailer_id, projection in scope_projection_dispositions.items()
                if projection["scorecard_disposition"] == "scoreable"
                and retailer_id in unavailability_approvals
            )
            if conflicting_approvals:
                raise ValueError(
                    "scoreable scope projections conflict with active retailer-unavailability "
                    f"approvals ({', '.join(conflicting_approvals)}); revoke those approvals "
                    "through the governed API before materialization"
                )
            full_selection_keys = {item.canonical_request_key for item in full_preview.items}
            required_selection_keys = {
                item.canonical_request_key
                for item in full_preview.items
                if item.required_for_assembly
            }
            optional_transient_keys = full_selection_keys - required_selection_keys
            selected_recovery: dict[str, TaskMapping] = {}
            selected_by_plan: dict[str, str] = {}
            redundant_evidence: list[dict[str, Any]] = []
            component_manifest: list[dict[str, Any]] = []
            for plan, recovery_run_id in zip(plans, recovery_run_ids, strict=True):
                if str(plan["selection_policy_version"]) not in {
                    SELECTION_POLICY_VERSION,
                    CONTINUATION_SELECTION_POLICY_VERSION,
                }:
                    raise ValueError("unsupported recovery selection policy version")
                if str(plan["base_snapshot_checksum"]) != raw_preview.base_snapshot_checksum:
                    raise ValueError("a recovery plan no longer matches the base snapshot")
                plan_id = str(plan["id"])
                selection_rows = list(
                    (
                        await connection.execute(
                            text(
                                "SELECT source_task_id::text, canonical_request_key "
                                "FROM collection_recovery_selection "
                                "WHERE recovery_plan_id::text = :plan_id"
                            ),
                            {"plan_id": plan_id},
                        )
                    )
                    .mappings()
                    .all()
                )
                selection_keys = {str(row["canonical_request_key"]) for row in selection_rows}
                if not selection_keys.issubset(full_selection_keys):
                    raise ValueError("recovery plan contains a non-eligible base request")
                overlap = set(selected_by_plan) & selection_keys
                invalid_overlap = {
                    key
                    for key in overlap
                    if selected_by_plan[key] not in ancestor_ids_by_plan[plan_id]
                }
                if invalid_overlap:
                    raise ValueError(
                        "recovery plans contain overlapping approved requests "
                        f"outside a continuation lineage (overlap={len(invalid_overlap)})"
                    )
                recovery_rows = await self._task_rows(connection, recovery_run_id)
                identity_rows_by_component[recovery_run_id] = recovery_rows
                recovery_by_key = self._unique_tasks(recovery_rows, f"recovery {recovery_run_id}")
                binding_manifest = dict(plan.get("binding_manifest") or {})
                if plan.get("continuation_of_recovery_plan_id") is not None:
                    continuation_manifest = dict(binding_manifest.get("continuation_lineage") or {})
                    scope = dict(plan.get("selection_scope") or {})
                    if (
                        str(continuation_manifest.get("continuation_of_recovery_plan_id") or "")
                        != str(plan["continuation_of_recovery_plan_id"])
                        or continuation_manifest.get("lineage_checksum")
                        != scope.get("lineage_checksum")
                        or tuple(continuation_manifest.get("lineage_plan_ids") or ())
                        != tuple(scope.get("lineage_plan_ids") or ())
                    ):
                        raise ValueError("bound continuation lineage manifest is inconsistent")
                bound_contract_checksum = canonical_checksum(
                    {
                        "tasks": [
                            {
                                "canonical_request_key": key,
                                "task_id": str(recovery_by_key[key]["id"]),
                                "snapshot": _task_contract_snapshot(recovery_by_key[key]),
                            }
                            for key in sorted(recovery_by_key)
                        ]
                    }
                )
                if bound_contract_checksum != str(
                    binding_manifest.get("recovery_task_contract_checksum") or ""
                ):
                    raise ValueError("bound recovery task evidence changed after approval")
                if not selection_keys.issubset(recovery_by_key):
                    raise ValueError("bound recovery is missing an approved request")
                adopted_rows = list(binding_manifest.get("adopted_gap_replacements") or [])
                redundant_rows = list(binding_manifest.get("redundant_evidence") or [])
                adopted_keys = {str(row["canonical_request_key"]) for row in adopted_rows}
                redundant_keys = {str(row["canonical_request_key"]) for row in redundant_rows}
                extra_keys = set(recovery_by_key) - selection_keys
                if extra_keys != adopted_keys | redundant_keys:
                    raise ValueError("legacy recovery extras do not match the binding manifest")
                overlap = set(selected_recovery) & (selection_keys | adopted_keys)
                invalid_overlap = {
                    key
                    for key in overlap
                    if selected_by_plan[key] not in ancestor_ids_by_plan[plan_id]
                }
                if invalid_overlap:
                    raise ValueError(
                        "recovery components compete for the same canonical request "
                        f"outside a continuation lineage (overlap={len(invalid_overlap)})"
                    )
                for key in sorted(selection_keys | adopted_keys):
                    candidate = recovery_by_key[key]
                    prior = selected_recovery.get(key, base_by_key[key])
                    if evidence_outcome(prior) != "usable_success" and _evidence_strength(
                        evidence_outcome(candidate)
                    ) > _evidence_strength(evidence_outcome(prior)):
                        selected_recovery[key] = candidate
                        selected_by_plan[key] = plan_id
                    elif key not in selected_by_plan:
                        selected_by_plan[key] = plan_id
                    else:
                        redundant_evidence.append(
                            {
                                "canonical_request_key": key,
                                "recovery_plan_id": plan_id,
                                "prior_recovery_plan_id": selected_by_plan[key],
                                "prior_task_id": str(prior["id"]),
                                "prior_outcome": evidence_outcome(prior),
                                "recovery_task_id": str(candidate["id"]),
                                "recovery_outcome": evidence_outcome(candidate),
                                "resolution": "continuation_did_not_improve_lineage_evidence",
                            }
                        )
                redundant_evidence.extend(
                    [{**row, "recovery_plan_id": plan_id} for row in redundant_rows]
                )
                component_manifest.append(
                    {
                        "recovery_plan_id": plan_id,
                        "recovery_run_id": recovery_run_id,
                        "selection_checksum": str(plan["selection_checksum"]),
                        "selected_task_count": len(selection_keys),
                        "binding_mode": binding_manifest.get("binding_mode"),
                        "identity_provenance": binding_manifest.get("identity_provenance"),
                        "recovery_task_contract_checksum": bound_contract_checksum,
                        "redundant_evidence_count": len(redundant_rows),
                        "adopted_gap_replacement_count": len(adopted_rows),
                        "continuation_of_recovery_plan_id": (
                            str(plan["continuation_of_recovery_plan_id"])
                            if plan.get("continuation_of_recovery_plan_id") is not None
                            else None
                        ),
                        "continuation_depth": int(plan.get("continuation_depth") or 0),
                    }
                )

            identity_provenance = request_identity_provenance_manifest(identity_rows_by_component)

            all_uncovered_required_keys = required_selection_keys - set(selected_by_plan)
            chosen: list[tuple[str, TaskMapping, str | None, EvidenceOutcome]] = []
            for key, base_task in sorted(base_by_key.items()):
                recovery_task = selected_recovery.get(key)
                selected = base_task
                superseded_task_id: str | None = None
                if recovery_task is not None:
                    base_outcome = evidence_outcome(base_task)
                    recovery_outcome = evidence_outcome(recovery_task)
                    if base_outcome != "usable_success" and _evidence_strength(
                        recovery_outcome
                    ) > _evidence_strength(base_outcome):
                        selected = recovery_task
                        superseded_task_id = str(base_task["id"])
                    else:
                        redundant_evidence.append(
                            {
                                "canonical_request_key": key,
                                "recovery_plan_id": selected_by_plan[key],
                                "base_task_id": str(base_task["id"]),
                                "base_outcome": base_outcome,
                                "recovery_task_id": str(recovery_task["id"]),
                                "recovery_outcome": recovery_outcome,
                                "resolution": "recovery_did_not_improve_base_evidence",
                            }
                        )
                outcome = evidence_outcome(selected)
                chosen.append(
                    (
                        key,
                        selected,
                        superseded_task_id,
                        outcome,
                    )
                )
            chosen_by_key = {key: (row, outcome) for key, row, _, outcome in chosen}
            unresolved_optional_transient_keys = {
                key
                for key in optional_transient_keys
                if chosen_by_key[key][1] not in {"usable_success", "retained_billable_404"}
            }
            base_config_for_scope = dict(by_run[base_collection_run_id]["config"])
            configured_retailers = {
                str(item["retailer_id"])
                for item in base_config_for_scope.get("retailers", [])
                if isinstance(item, Mapping) and bool(item.get("enabled"))
            }
            all_outcomes_by_retailer: dict[str, list[EvidenceOutcome]] = {
                retailer_id: [] for retailer_id in configured_retailers
            }
            nonempty_successes_by_retailer: dict[str, int] = {
                retailer_id: 0 for retailer_id in configured_retailers
            }
            for _, row, _, outcome in chosen:
                retailer_id = str(row["retailer_id"])
                all_outcomes_by_retailer.setdefault(retailer_id, []).append(outcome)
                if outcome == "usable_success" and int(row.get("result_count") or 0) > 0:
                    nonempty_successes_by_retailer[retailer_id] = (
                        nonempty_successes_by_retailer.get(retailer_id, 0) + 1
                    )
            _, adequacy_manifest = recovery_adequacy(all_outcomes_by_retailer)
            gate_config = dict(by_run[base_collection_run_id].get("availability_gate_config") or {})
            minimum_successes = max(int(gate_config.get("minimum_successful_samples") or 1), 1)
            maximum_404_rate = float(gate_config.get("max_billable_404_rate", 0.5))
            collection_readiness_blocked, collection_readiness_manifest = (
                retailer_collection_readiness(
                    all_outcomes_by_retailer,
                    minimum_successes=minimum_successes,
                    maximum_404_rate=maximum_404_rate,
                    nonempty_successes_by_retailer=nonempty_successes_by_retailer,
                    unavailability_approvals=unavailability_approvals,
                    scope_projection_dispositions=scope_projection_dispositions,
                )
            )
            unavailable_retailer_ids = {
                retailer_id
                for retailer_id, row in collection_readiness_manifest.items()
                if row["status"] == "unavailable"
            }
            (
                uncovered_keys,
                unavailable_uncovered_keys,
                tolerated_uncovered_required_keys,
            ) = partition_uncovered_recovery_keys(
                all_uncovered_required_keys,
                base_by_key=base_by_key,
                chosen_by_key=chosen_by_key,
                collection_readiness_manifest=collection_readiness_manifest,
                unavailable_retailer_ids=unavailable_retailer_ids,
            )
            inadequacy_blocked = any(
                row["status"] == "blocked"
                and (
                    retailer_id not in unavailable_retailer_ids
                    or int(row["contract_or_quarantined"]) > 0
                )
                for retailer_id, row in adequacy_manifest.items()
            )
            trust_state = composite_trust_state(
                [outcome for _, _, _, outcome in chosen],
                has_uncovered_recovery=bool(uncovered_keys),
                has_inadequate_recovery=(inadequacy_blocked or collection_readiness_blocked),
            )
            blocking = trust_state == "blocked"

            base_config = dict(by_run[base_collection_run_id]["config"])
            product_pack = dict(base_config.get("product_pack") or {})
            if not product_pack.get("id") or not product_pack.get("version"):
                raise ValueError("base collection does not identify a Product Pack")
            generation = int(
                (
                    await connection.execute(
                        text(
                            "SELECT COALESCE(max(assembly_generation), 0) + 1 "
                            "FROM analysis_input_set WHERE collection_run_id::text = :run_id"
                        ),
                        {"run_id": base_collection_run_id},
                    )
                ).scalar_one()
            )
            retailer_summary: dict[str, dict[str, int]] = {}
            for _, row, _, outcome in chosen:
                summary = retailer_summary.setdefault(
                    str(row["retailer_id"]),
                    {
                        name: 0
                        for name in (
                            "usable_success",
                            "retained_billable_404",
                            "zero_credit_missing",
                            "contract_missing",
                            "quarantined",
                        )
                    },
                )
                summary[outcome] += 1
            task_chain_checksum = hashlib.sha256(
                "|".join(f"{key}:{row['id']}:{outcome}" for key, row, _, outcome in chosen).encode()
            ).hexdigest()
            total_rows = sum(
                int(row.get("result_count") or 0)
                for _, row, _, outcome in chosen
                if outcome == "usable_success"
            )
            usable_artifacts = [
                {
                    "ordinal": ordinal,
                    "canonical_request_key": key,
                    "dataset_artifact_id": str(row["raw_artifact_id"]),
                    "checksum": str(row["raw_artifact_checksum"]),
                }
                for ordinal, (key, row, _, outcome) in enumerate(chosen)
                if outcome == "usable_success"
            ]
            manifest = {
                "schema_version": "2.0.0",
                "kind": "live_collection_composite",
                "assembly_policy_version": ASSEMBLY_POLICY_VERSION,
                "base_collection_run_id": base_collection_run_id,
                "base_snapshot_checksum": full_preview.base_snapshot_checksum,
                "definition_checksum": str(by_run[base_collection_run_id]["definition_checksum"]),
                "components": component_manifest,
                "scope_projections": [
                    {
                        "id": str(projection.get("projection_id") or projection["id"]),
                        "retailer_id": str(projection["retailer_id"]),
                        "projection_kind": str(projection["projection_kind"]),
                        "policy_version": str(projection["policy_version"]),
                        "projection_checksum": str(projection["projection_checksum"]),
                        "source_audit_id": (
                            str(projection["source_audit_id"])
                            if projection.get("source_audit_id") is not None
                            else None
                        ),
                        "source_evidence_checksum": str(projection["source_evidence_checksum"]),
                        "raw_task_count": int(projection["raw_task_count"]),
                        "retained_task_count": int(projection["retained_task_count"]),
                        "excluded_task_count": int(projection["excluded_task_count"]),
                        "raw_location_count": int(projection["raw_location_count"]),
                        "retained_location_count": int(projection["retained_location_count"]),
                        "excluded_location_count": int(projection["excluded_location_count"]),
                        "raw_task_retention_ratio": str(projection["raw_task_retention_ratio"]),
                        "governed_coverage_ratio": str(projection["governed_coverage_ratio"]),
                        "minimum_scoreable_coverage": str(projection["minimum_scoreable_coverage"]),
                        "scorecard_disposition": str(projection["scorecard_disposition"]),
                        "inventory_checksum": str(
                            dict(projection["manifest"])["inventory_checksum"]
                        ),
                    }
                    for projection in projections
                ],
                "raw_base_task_count": len(raw_base_rows),
                "projected_base_task_count": len(base_rows),
                "projected_excluded_task_count": len(raw_base_rows) - len(base_rows),
                "task_chain_checksum": task_chain_checksum,
                "task_count": len(chosen),
                "total_rows": total_rows,
                "usable_artifact_count": len(usable_artifacts),
                "usable_artifact_manifest_checksum": canonical_checksum(
                    {"artifacts": usable_artifacts}
                ),
                "trust_state": trust_state,
                "unrecovered_selected_count": len(uncovered_keys),
                "unrecovered_selection_checksum": canonical_checksum(
                    {"canonical_request_keys": sorted(uncovered_keys)}
                ),
                "unrecovered_optional_transient_count": len(unresolved_optional_transient_keys),
                "unrecovered_optional_transient_checksum": canonical_checksum(
                    {"canonical_request_keys": sorted(unresolved_optional_transient_keys)}
                ),
                "unavailable_unrecovered_required_count": len(unavailable_uncovered_keys),
                "unavailable_unrecovered_required_checksum": canonical_checksum(
                    {"canonical_request_keys": sorted(unavailable_uncovered_keys)}
                ),
                "tolerated_unrecovered_required_count": len(tolerated_uncovered_required_keys),
                "tolerated_unrecovered_required_checksum": canonical_checksum(
                    {"canonical_request_keys": sorted(tolerated_uncovered_required_keys)}
                ),
                "unavailable_retailers": sorted(
                    retailer_id
                    for retailer_id, row in collection_readiness_manifest.items()
                    if row["status"] == "unavailable"
                ),
                "retailers": retailer_summary,
                "recovery_adequacy": adequacy_manifest,
                "retailer_collection_readiness": collection_readiness_manifest,
                "identity_provenance": identity_provenance,
                "redundant_evidence": redundant_evidence,
                "component_actual_credits": {
                    run_id: int(by_run[run_id]["actual_credits"]) for run_id in run_ids
                },
            }
            manifest_checksum = canonical_checksum(manifest)
            existing = (
                (
                    await connection.execute(
                        text(
                            "SELECT id::text, collection_run_id::text, assembly_generation, "
                            "manifest_checksum, total_rows, trust_state, status "
                            "FROM analysis_input_set WHERE organization_id = CAST(:org AS uuid) "
                            "AND source_kind = 'live_collection_composite' "
                            "AND manifest_checksum = :checksum"
                        ),
                        {
                            "org": str(by_run[base_collection_run_id]["organization_id"]),
                            "checksum": manifest_checksum,
                        },
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                stored_projection_links = list(
                    (
                        await connection.execute(
                            text(
                                "SELECT scope_projection_id::text, ordinal, "
                                "projection_checksum FROM analysis_input_scope_projection "
                                "WHERE input_set_id::text = :input_set_id ORDER BY ordinal"
                            ),
                            {"input_set_id": str(existing["id"])},
                        )
                    )
                    .mappings()
                    .all()
                )
                expected_projection_links = [
                    {
                        "scope_projection_id": str(
                            projection.get("projection_id") or projection["id"]
                        ),
                        "ordinal": ordinal,
                        "projection_checksum": str(projection["projection_checksum"]),
                    }
                    for ordinal, projection in enumerate(projections)
                ]
                actual_projection_links = [
                    {
                        "scope_projection_id": str(row["scope_projection_id"]),
                        "ordinal": int(row["ordinal"]),
                        "projection_checksum": str(row["projection_checksum"]),
                    }
                    for row in stored_projection_links
                ]
                if actual_projection_links != expected_projection_links:
                    raise ValueError(
                        "existing analysis input scope-projection lineage is incomplete or changed"
                    )
                analysis_run_id = await self._queue_composite_analysis(
                    connection,
                    str(existing["id"]),
                    queue_allowed=str(existing["status"]) == "ready",
                )
                return CompositeInputSetRecord(
                    id=str(existing["id"]),
                    base_collection_run_id=str(existing["collection_run_id"]),
                    recovery_collection_run_ids=recovery_run_ids,
                    assembly_generation=int(existing["assembly_generation"]),
                    manifest_checksum=str(existing["manifest_checksum"]),
                    total_rows=int(existing["total_rows"]),
                    trust_state=str(existing["trust_state"]),
                    status=str(existing["status"]),
                    analysis_run_id=analysis_run_id,
                )
            input_set_id = str(
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO analysis_input_set (
                              organization_id, source_kind, stable_key, collection_run_id,
                              product_pack_id, product_pack_version, analysis_config,
                              manifest, manifest_checksum, total_rows, status, completed_at,
                              assembly_generation, assembly_policy_version, trust_state
                            ) VALUES (
                              CAST(:organization_id AS uuid), 'live_collection_composite',
                              :stable_key, CAST(:base_run_id AS uuid), :product_pack_id,
                              :product_pack_version, CAST(:analysis_config AS jsonb),
                              CAST(:manifest AS jsonb), :manifest_checksum, :total_rows,
                              :status, now(), :generation, :assembly_policy_version, :trust_state
                            ) RETURNING id::text
                            """
                        ),
                        {
                            "organization_id": str(
                                by_run[base_collection_run_id]["organization_id"]
                            ),
                            "stable_key": (f"composite-{base_collection_run_id}-g{generation}"),
                            "base_run_id": base_collection_run_id,
                            "product_pack_id": str(product_pack["id"]),
                            "product_pack_version": str(product_pack["version"]),
                            "analysis_config": _json(base_config),
                            "manifest": _json(manifest),
                            "manifest_checksum": manifest_checksum,
                            "total_rows": total_rows,
                            "status": "failed" if blocking else "ready",
                            "generation": generation,
                            "assembly_policy_version": ASSEMBLY_POLICY_VERSION,
                            "trust_state": trust_state,
                        },
                    )
                ).scalar_one()
            )
            await self._insert_component(
                connection,
                input_set_id,
                base_collection_run_id,
                ordinal=0,
                role="base",
                recovery_plan_id=None,
                row=by_run[base_collection_run_id],
            )
            for ordinal, (plan, recovery_run_id) in enumerate(
                zip(plans, recovery_run_ids, strict=True), start=1
            ):
                await self._insert_component(
                    connection,
                    input_set_id,
                    recovery_run_id,
                    ordinal=ordinal,
                    role="recovery",
                    recovery_plan_id=str(plan["id"]),
                    row=by_run[recovery_run_id],
                )
            await self._insert_selected_evidence(
                connection,
                input_set_id,
                chosen,
                expected_usable_artifacts=usable_artifacts,
            )
            if projections:
                await connection.execute(
                    text(
                        """
                        INSERT INTO analysis_input_scope_projection (
                          input_set_id, scope_projection_id, ordinal, projection_checksum
                        ) VALUES (
                          CAST(:input_set_id AS uuid), CAST(:projection_id AS uuid),
                          :ordinal, :projection_checksum
                        )
                        """
                    ),
                    [
                        {
                            "input_set_id": input_set_id,
                            "projection_id": str(
                                projection.get("projection_id") or projection["id"]
                            ),
                            "ordinal": ordinal,
                            "projection_checksum": str(projection["projection_checksum"]),
                        }
                        for ordinal, projection in enumerate(projections)
                    ],
                )
            if not blocking:
                await connection.execute(
                    text(
                        "UPDATE collection_recovery_plan SET status = 'ready' "
                        "WHERE id::text = ANY(CAST(:plan_ids AS text[])) "
                        "AND status IN ('bound','ready')"
                    ),
                    {"plan_ids": list(plan_ids)},
                )
            analysis_run_id = await self._queue_composite_analysis(
                connection,
                input_set_id,
                queue_allowed=not blocking,
            )
            return CompositeInputSetRecord(
                id=input_set_id,
                base_collection_run_id=base_collection_run_id,
                recovery_collection_run_ids=recovery_run_ids,
                assembly_generation=generation,
                manifest_checksum=manifest_checksum,
                total_rows=total_rows,
                trust_state=trust_state,
                status="failed" if blocking else "ready",
                analysis_run_id=analysis_run_id,
            )

    @staticmethod
    async def _insert_selected_evidence(
        connection: AsyncConnection,
        input_set_id: str,
        chosen: Sequence[tuple[str, TaskMapping, str | None, EvidenceOutcome]],
        *,
        expected_usable_artifacts: Sequence[Mapping[str, Any]],
    ) -> None:
        """Persist immutable task/artifact lineage with bounded set-based writes."""

        lineage_rows: list[dict[str, Any]] = []
        artifact_rows: list[dict[str, Any]] = []
        for ordinal, (key, row, superseded_task_id, outcome) in enumerate(chosen):
            snapshot = _task_snapshot(row)
            lineage_rows.append(
                {
                    "canonical_request_key": key,
                    "selected_task_id": str(row["id"]),
                    "retailer_id": str(row["retailer_id"]),
                    "location_scope_key": str(row["location_scope_key"]),
                    "page_number": int(row["page_number"]),
                    "evidence_outcome": outcome,
                    "superseded_task_id": superseded_task_id,
                    "snapshot": snapshot,
                }
            )
            if outcome == "usable_success":
                artifact_rows.append(
                    {
                        "ordinal": ordinal,
                        "canonical_request_key": key,
                        "task_id": str(row["id"]),
                        "location_snapshot": snapshot["location_snapshot"],
                    }
                )

        inserted_lineage_keys: list[str] = []
        for offset in range(0, len(lineage_rows), MATERIALIZATION_WRITE_BATCH_SIZE):
            batch = lineage_rows[offset : offset + MATERIALIZATION_WRITE_BATCH_SIZE]
            inserted_lineage_keys.extend(
                str(value)
                for value in (
                    await connection.execute(
                        text(
                            """
                            WITH payload AS (
                              SELECT *
                              FROM jsonb_to_recordset(CAST(:rows AS jsonb)) AS x(
                                canonical_request_key text,
                                selected_task_id text,
                                retailer_id text,
                                location_scope_key text,
                                page_number integer,
                                evidence_outcome text,
                                superseded_task_id text,
                                snapshot jsonb
                              )
                            )
                            INSERT INTO analysis_input_task_lineage (
                              input_set_id, canonical_request_key, selected_task_id,
                              retailer_id, location_scope_key, page_number, evidence_outcome,
                              superseded_task_id, snapshot
                            )
                            SELECT CAST(:input_set_id AS uuid), canonical_request_key,
                                   CAST(selected_task_id AS uuid), retailer_id,
                                   location_scope_key, page_number, evidence_outcome,
                                   CAST(superseded_task_id AS uuid), snapshot
                            FROM payload
                            RETURNING canonical_request_key
                            """
                        ),
                        {"input_set_id": input_set_id, "rows": _json(batch)},
                    )
                ).scalars()
            )
        expected_lineage_keys = sorted(row["canonical_request_key"] for row in lineage_rows)
        if sorted(inserted_lineage_keys) != expected_lineage_keys:
            raise RuntimeError("composite task-lineage bulk insertion was incomplete")

        inserted_artifacts: list[dict[str, Any]] = []
        for offset in range(0, len(artifact_rows), MATERIALIZATION_WRITE_BATCH_SIZE):
            batch = artifact_rows[offset : offset + MATERIALIZATION_WRITE_BATCH_SIZE]
            returned = (
                (
                    await connection.execute(
                        text(
                            """
                            WITH payload AS (
                              SELECT *
                              FROM jsonb_to_recordset(CAST(:rows AS jsonb)) AS x(
                                ordinal integer,
                                canonical_request_key text,
                                task_id text,
                                location_snapshot jsonb
                              )
                            )
                            INSERT INTO analysis_input_artifact (
                              input_set_id, dataset_artifact_id, ordinal, retailer_id,
                              adapter_id, source_name, source_format, row_count, checksum, metadata
                            )
                            SELECT CAST(:input_set_id AS uuid), da.id, payload.ordinal,
                                   t.retailer_id, t.adapter_id,
                                   'task-' || t.id::text || '.json.gz',
                                   'metricscart_provider_json', COALESCE(t.result_count, 0),
                                   da.checksum, jsonb_build_object(
                                     'task_id', t.id::text,
                                     'collection_run_id', t.collection_run_id::text,
                                     'page_number', t.page_number,
                                     'location_scope_key', t.location_scope_key,
                                     'canonical_request_key', payload.canonical_request_key,
                                     'location_snapshot', payload.location_snapshot
                                   )
                            FROM payload
                            JOIN collection_task t ON t.id = CAST(payload.task_id AS uuid)
                            JOIN dataset_artifact da ON da.id = t.raw_artifact_id
                            RETURNING ordinal, metadata->>'canonical_request_key'
                                      AS canonical_request_key,
                                      dataset_artifact_id::text AS dataset_artifact_id,
                                      checksum
                            """
                        ),
                        {"input_set_id": input_set_id, "rows": _json(batch)},
                    )
                )
                .mappings()
                .all()
            )
            inserted_artifacts.extend(
                {
                    "ordinal": int(row["ordinal"]),
                    "canonical_request_key": str(row["canonical_request_key"]),
                    "dataset_artifact_id": str(row["dataset_artifact_id"]),
                    "checksum": str(row["checksum"]),
                }
                for row in returned
            )
        expected_artifacts: list[dict[str, Any]] = [
            {
                "ordinal": int(row["ordinal"]),
                "canonical_request_key": str(row["canonical_request_key"]),
                "dataset_artifact_id": str(row["dataset_artifact_id"]),
                "checksum": str(row["checksum"]),
            }
            for row in expected_usable_artifacts
        ]
        expected_artifacts.sort(key=lambda row: int(row["ordinal"]))
        if sorted(inserted_artifacts, key=lambda row: row["ordinal"]) != expected_artifacts:
            raise RuntimeError(
                "composite usable-artifact bulk insertion differs from its immutable manifest"
            )

    async def _queue_composite_analysis(
        self,
        connection: AsyncConnection,
        input_set_id: str,
        *,
        queue_allowed: bool,
    ) -> str | None:
        if not queue_allowed:
            return None
        existing = (
            await connection.execute(
                text(
                    "SELECT id::text FROM analysis_run "
                    "WHERE input_set_id::text = :input_set_id "
                    "ORDER BY created_at, id LIMIT 1"
                ),
                {"input_set_id": input_set_id},
            )
        ).scalar_one_or_none()
        if existing is not None:
            return str(existing)
        inserted = (
            await connection.execute(
                text(
                    """
                    INSERT INTO analysis_run (
                      collection_run_id, input_set_id, product_pack_id,
                      product_pack_version, status, code_version, max_attempts,
                      match_revision_id, brand_revision_id, source_analysis_result_id,
                      replay_generation, replay_reason
                    )
                    SELECT i.collection_run_id, i.id, i.product_pack_id,
                           i.product_pack_version, 'queued', :code_version, :max_attempts,
                           governed_match.id, governed_brand.id,
                           COALESCE(
                             governed_match.source_analysis_result_id,
                             governed_brand.source_analysis_result_id
                           ), replay.next_generation, 'composite collection evidence'
                    FROM analysis_input_set i
                    LEFT JOIN LATERAL (
                      SELECT revision.id, revision.source_analysis_result_id
                      FROM product_match_application_policy policy
                      JOIN product_match_revision revision ON revision.id = policy.revision_id
                      WHERE policy.organization_id = i.organization_id
                        AND policy.product_pack_id = i.product_pack_id
                        AND policy.product_pack_version = i.product_pack_version
                        AND policy.benchmark_retailer_id =
                          i.analysis_config->>'benchmark_retailer'
                      LIMIT 1
                    ) governed_match ON true
                    LEFT JOIN LATERAL (
                      SELECT revision.id, revision.source_analysis_result_id
                      FROM brand_classification_application_policy policy
                      JOIN brand_classification_revision revision
                        ON revision.id = policy.revision_id
                      WHERE policy.organization_id = i.organization_id
                        AND policy.product_pack_id = i.product_pack_id
                        AND policy.product_pack_version = i.product_pack_version
                        AND policy.benchmark_retailer_id =
                          i.analysis_config->>'benchmark_retailer'
                      LIMIT 1
                    ) governed_brand ON true
                    LEFT JOIN LATERAL (
                      SELECT COALESCE(max(existing.replay_generation), 0) + 1
                        AS next_generation
                      FROM analysis_run existing
                      WHERE existing.collection_run_id = i.collection_run_id
                        AND existing.product_pack_id = i.product_pack_id
                        AND existing.product_pack_version = i.product_pack_version
                        AND existing.match_revision_id IS NOT DISTINCT FROM governed_match.id
                        AND existing.brand_revision_id IS NOT DISTINCT FROM governed_brand.id
                        AND existing.matching_v2_gold_set_release_id IS NULL
                    ) replay ON true
                    WHERE i.id::text = :input_set_id
                      AND i.source_kind = 'live_collection_composite'
                      AND i.status = 'ready' AND i.trust_state <> 'blocked'
                    ON CONFLICT ON CONSTRAINT
                      analysis_run_collection_pack_match_revision_uq DO NOTHING
                    RETURNING id::text
                    """
                ),
                {
                    "input_set_id": input_set_id,
                    "code_version": self._analysis_code_version,
                    "max_attempts": self._analysis_max_attempts,
                },
            )
        ).scalar_one_or_none()
        if inserted is not None:
            return str(inserted)
        return (
            await connection.execute(
                text(
                    "SELECT id::text FROM analysis_run "
                    "WHERE input_set_id::text = :input_set_id "
                    "ORDER BY created_at, id LIMIT 1"
                ),
                {"input_set_id": input_set_id},
            )
        ).scalar_one_or_none()

    @staticmethod
    async def _check_recovery_budgets(
        connection: AsyncConnection,
        *,
        definition_id: str,
        definition_config: Mapping[str, Any],
        requested_credits: int,
        approved_credit_ceiling: int,
    ) -> None:
        if requested_credits > approved_credit_ceiling:
            raise ValueError("exact recovery exceeds the approved batch credit ceiling")
        budget = definition_config.get("budget")
        if not isinstance(budget, Mapping):
            return
        run_limit = budget.get("max_credits_per_run")
        if (
            bool(budget.get("block_if_estimate_exceeds_budget", True))
            and run_limit is not None
            and requested_credits > int(run_limit)
        ):
            raise ValueError(
                f"exact recovery credits {requested_credits} exceed run budget {run_limit}"
            )
        for period, limit in (
            ("day", budget.get("max_credits_per_day")),
            ("month", budget.get("max_credits_per_month")),
        ):
            if limit is None:
                continue
            used = int(
                (
                    await connection.execute(
                        text(
                            f"""
                            SELECT COALESCE(sum(
                              CASE WHEN r.status IN (
                                'succeeded', 'completed_with_warnings', 'failed', 'cancelled'
                              ) THEN r.actual_credits ELSE r.estimated_credits END
                            ), 0)
                            FROM collection_run r
                            JOIN collection_definition_version v
                              ON v.id = r.definition_version_id
                            WHERE v.definition_id = CAST(:definition_id AS uuid)
                              AND r.created_at >= (
                                date_trunc('{period}', now() AT TIME ZONE 'UTC')
                                AT TIME ZONE 'UTC'
                              )
                            """
                        ),
                        {"definition_id": definition_id},
                    )
                ).scalar_one()
            )
            if used + requested_credits > int(limit):
                raise ValueError(
                    f"{period} credit budget {limit} would be exceeded: "
                    f"used/reserved {used}, requested {requested_credits}"
                )

    @staticmethod
    async def _launch_record(
        connection: AsyncConnection,
        plan_id: str,
        recovery_run_id: str,
        *,
        reused_existing_run: bool,
    ) -> RecoveryLaunchRecord:
        row = (
            (
                await connection.execute(
                    text(
                        """
                        SELECT r.id::text, r.definition_version_id::text, r.status,
                               r.estimated_credits, r.availability_gate_status,
                               count(t.id)::integer AS task_count
                        FROM collection_run r
                        LEFT JOIN collection_task t ON t.collection_run_id = r.id
                        WHERE r.id::text = :run_id
                        GROUP BY r.id, r.definition_version_id, r.status,
                                 r.estimated_credits, r.availability_gate_status
                        """
                    ),
                    {"run_id": recovery_run_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise LookupError(f"recovery collection run {recovery_run_id!r} was not found")
        return RecoveryLaunchRecord(
            recovery_plan_id=plan_id,
            collection_run_id=str(row["id"]),
            definition_version_id=str(row["definition_version_id"]),
            status=str(row["status"]),
            task_count=int(row["task_count"]),
            maximum_credits=int(row["estimated_credits"]),
            availability_gate_status=str(row["availability_gate_status"]),
            reused_existing_run=reused_existing_run,
        )

    async def _build_scope_projection_preview(
        self,
        connection: AsyncConnection,
        base_collection_run_id: str,
        *,
        retailer_id: str,
        projection_kind: ScopeProjectionKind,
        source_audit_id: str | None,
        for_update: bool = False,
    ) -> ScopeProjectionPreview:
        definition_checksum, rows = await self._base_rows(
            connection, base_collection_run_id, for_update=for_update
        )
        base_config = dict(
            (
                await connection.execute(
                    text(
                        "SELECT v.config FROM collection_run r "
                        "JOIN collection_definition_version v ON v.id = r.definition_version_id "
                        "WHERE r.id::text = :run_id"
                    ),
                    {"run_id": base_collection_run_id},
                )
            ).scalar_one()
        )
        enabled_retailers = {
            str(item["retailer_id"])
            for item in base_config.get("retailers", [])
            if isinstance(item, Mapping) and bool(item.get("enabled"))
        }
        if retailer_id not in enabled_retailers:
            raise ValueError("scope projection retailer is not enabled in the base definition")
        if retailer_id == str(base_config.get("benchmark_retailer") or ""):
            raise ValueError("the benchmark retailer cannot receive a scope projection")
        raw_preview = build_recovery_preview(
            base_collection_run_id,
            rows,
            definition_checksum=definition_checksum,
            allow_ineligible_locations=True,
        )
        source_audit: TaskMapping | None = None
        if projection_kind == "canonical_alias_collapse":
            if source_audit_id is None:
                raise ValueError("canonical alias collapse requires source_audit_id")
            source_audit = (
                (
                    await connection.execute(
                        text(
                            "SELECT id::text, catalog_sha256, snapshot_sha256, "
                            "reviewed_plan_sha256, retailer_ids, status, scanned_rows, "
                            "changed_rows, eligible_before, eligible_after, changes "
                            "FROM location_eligibility_reconciliation_run "
                            "WHERE id::text = :audit_id"
                        ),
                        {"audit_id": source_audit_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if source_audit is None:
                raise LookupError(f"location eligibility audit {source_audit_id!r} was not found")
        elif source_audit_id is not None:
            raise ValueError("limited provider footprint cannot bind a location audit")
        return build_scope_projection_preview(
            base_collection_run_id,
            rows,
            retailer_id=retailer_id,
            projection_kind=projection_kind,
            base_snapshot_checksum=raw_preview.base_snapshot_checksum,
            source_audit=(dict(source_audit) if source_audit is not None else None),
            provider_error_evidence_contracts=self._provider_error_evidence_contracts,
        )

    async def _scope_projection_row(
        self,
        connection: AsyncConnection,
        scope_projection_id: str,
        *,
        include_inventory: bool,
    ) -> dict[str, Any]:
        row = (
            (
                await connection.execute(
                    text(
                        "SELECT *, id::text AS projection_id, "
                        "base_collection_run_id::text AS base_run_id, "
                        "source_audit_id::text AS source_audit_text "
                        "FROM collection_scope_projection WHERE id::text = :projection_id"
                    ),
                    {"projection_id": scope_projection_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise LookupError(f"collection scope projection {scope_projection_id!r} was not found")
        result = dict(row)
        manifest = validate_scope_projection_header_manifest(result)
        source_evidence = dict(manifest["source_evidence"])
        if result.get("source_audit_text") is not None:
            source_audit = (
                (
                    await connection.execute(
                        text(
                            "SELECT id::text, catalog_sha256, snapshot_sha256, "
                            "reviewed_plan_sha256, retailer_ids, status, scanned_rows, "
                            "changed_rows, eligible_before, eligible_after, changes "
                            "FROM location_eligibility_reconciliation_run "
                            "WHERE id = CAST(:audit_id AS uuid)"
                        ),
                        {"audit_id": str(result["source_audit_text"])},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if (
                source_audit is None
                or _location_audit_evidence(dict(source_audit)) != source_evidence
            ):
                raise ValueError(
                    "scope projection location-audit evidence differs from its immutable snapshot"
                )
        if include_inventory:
            inventory = list(
                (
                    await connection.execute(
                        text(
                            "SELECT source_task_id::text, ordinal, canonical_request_key, "
                            "disposition, reason, mapped_retained_task_id::text, source_snapshot "
                            "FROM collection_scope_projection_task "
                            "WHERE scope_projection_id::text = :projection_id ORDER BY ordinal"
                        ),
                        {"projection_id": scope_projection_id},
                    )
                )
                .mappings()
                .all()
            )
            if len(inventory) != int(result["raw_task_count"]):
                raise ValueError("stored scope projection task inventory is incomplete")
            inventory_document = {
                "items": [
                    {
                        "source_task_id": str(item["source_task_id"]),
                        "canonical_request_key": str(item["canonical_request_key"]),
                        "disposition": str(item["disposition"]),
                        "reason": str(item["reason"]),
                        "mapped_retained_task_id": (
                            str(item["mapped_retained_task_id"])
                            if item.get("mapped_retained_task_id") is not None
                            else None
                        ),
                        "source_snapshot": dict(item["source_snapshot"]),
                    }
                    for item in inventory
                ]
            }
            if canonical_checksum(inventory_document) != str(manifest["inventory_checksum"]):
                raise ValueError("stored scope projection inventory checksum is invalid")
            result["inventory"] = inventory
        return result

    @staticmethod
    def _scope_projection_binding(projection: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "id": str(projection.get("projection_id") or projection["id"]),
            "retailer_id": str(projection["retailer_id"]),
            "projection_checksum": str(projection["projection_checksum"]),
        }

    @staticmethod
    def _apply_scope_projection_rows(
        rows: Sequence[TaskMapping],
        projections: Sequence[Mapping[str, Any]],
        *,
        base_collection_run_id: str,
        base_snapshot_checksum: str,
    ) -> list[TaskMapping]:
        by_task_id = {str(row["id"]): row for row in rows}
        projection_by_retailer: dict[str, Mapping[str, Any]] = {}
        retained_by_retailer: dict[str, set[str]] = {}
        for projection in projections:
            if str(projection.get("base_run_id") or projection["base_collection_run_id"]) != (
                base_collection_run_id
            ):
                raise ValueError("scope projection belongs to another base collection run")
            if str(projection["base_snapshot_checksum"]) != base_snapshot_checksum:
                raise ValueError("scope projection no longer matches the immutable base snapshot")
            retailer_id = str(projection["retailer_id"])
            if retailer_id in projection_by_retailer:
                raise ValueError("more than one scope projection targets the same retailer")
            inventory = list(projection.get("inventory") or [])
            retailer_task_ids = {
                task_id
                for task_id, row in by_task_id.items()
                if str(row["retailer_id"]) == retailer_id
            }
            inventory_task_ids = {str(item["source_task_id"]) for item in inventory}
            if inventory_task_ids != retailer_task_ids:
                raise ValueError("scope projection does not inventory every frozen retailer task")
            retained = {
                str(item["source_task_id"])
                for item in inventory
                if str(item["disposition"]) == "retained"
            }
            if len(retained) != int(projection["retained_task_count"]):
                raise ValueError("scope projection retained count differs from its inventory")
            projection_by_retailer[retailer_id] = projection
            retained_by_retailer[retailer_id] = retained
        return [
            row
            for row in rows
            if str(row["retailer_id"]) not in retained_by_retailer
            or str(row["id"]) in retained_by_retailer[str(row["retailer_id"])]
        ]

    async def _base_rows(
        self,
        connection: AsyncConnection,
        run_id: str,
        *,
        for_update: bool = False,
    ) -> tuple[str, list[TaskMapping]]:
        lock = " FOR UPDATE" if for_update else ""
        run = (
            (
                await connection.execute(
                    text(
                        "SELECT v.checksum, r.status FROM collection_run r "
                        "JOIN collection_definition_version v "
                        "ON v.id = r.definition_version_id "
                        "WHERE r.id::text = :run_id" + lock
                    ),
                    {"run_id": run_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if run is None:
            raise LookupError(f"collection run {run_id!r} was not found")
        if str(run["status"]) not in {
            "succeeded",
            "completed_with_warnings",
            "failed",
            "cancelled",
        }:
            raise ValueError("a recovery selection requires a terminal base run")
        rows = await self._task_rows(connection, run_id)
        if not rows:
            raise ValueError("base collection run has no tasks")
        return str(run["checksum"]), rows

    async def _task_rows(self, connection: AsyncConnection, run_id: str) -> list[TaskMapping]:
        rows = list(
            (
                await connection.execute(
                    text(
                        """
                        SELECT t.*, g.status AS retailer_gate_status,
                               da.metadata AS raw_artifact_metadata,
                               da.checksum AS raw_artifact_checksum,
                               v.geography_resolution_id::text AS geography_resolution_id,
                               gl.id::text AS frozen_geography_location_id,
                               gl.retailer_location_id::text AS frozen_retailer_location_id,
                               gl.zipcode AS frozen_zipcode,
                               gl.store_number AS frozen_store_number,
                               gl.latitude AS frozen_latitude,
                               gl.longitude AS frozen_longitude,
                               gl.city AS frozen_city,
                               gl.state AS frozen_state,
                               gl.country AS frozen_country,
                               CASE
                                 WHEN t.retailer_location_id IS NULL THEN NULL
                                 ELSE COALESCE(l.collection_eligible, false)
                               END AS current_location_eligible
                        FROM collection_task t
                        JOIN collection_run r ON r.id = t.collection_run_id
                        JOIN collection_definition_version v ON v.id = r.definition_version_id
                        LEFT JOIN collection_retailer_gate g
                          ON g.collection_run_id = t.collection_run_id
                         AND g.retailer_id = t.retailer_id
                        LEFT JOIN dataset_artifact da ON da.id = t.raw_artifact_id
                        LEFT JOIN collection_geography_location gl
                          ON gl.resolution_id = v.geography_resolution_id
                         AND gl.retailer_id = t.retailer_id
                         AND gl.scope_key = t.location_scope_key
                        LEFT JOIN retailer_location l ON l.id = t.retailer_location_id
                        WHERE t.collection_run_id::text = :run_id
                        ORDER BY t.retailer_id, t.location_scope_key,
                                 t.page_number, t.id
                        """
                    ),
                    {"run_id": run_id},
                )
            )
            .mappings()
            .all()
        )
        normalized: list[TaskMapping] = []
        for row in rows:
            if row.get("geography_resolution_id") is None:
                raise ValueError(
                    "collection task has no immutable geography resolution for composite evidence"
                )
            if row.get("frozen_geography_location_id") is None:
                raise ValueError(
                    "collection task does not match a location in its immutable "
                    "geography resolution"
                )
            if str(row.get("frozen_zipcode") or "") != str(row["zipcode"]):
                raise ValueError(
                    "collection task ZIP differs from its immutable geography location"
                )
            task_store_number = (
                str(row["store_number"]) if row.get("store_number") is not None else None
            )
            frozen_store_number = (
                str(row["frozen_store_number"])
                if row.get("frozen_store_number") is not None
                else None
            )
            if task_store_number != frozen_store_number:
                raise ValueError(
                    "collection task store differs from its immutable geography location"
                )
            task_location_id = (
                str(row["retailer_location_id"])
                if row.get("retailer_location_id") is not None
                else None
            )
            frozen_location_id = (
                str(row["frozen_retailer_location_id"])
                if row.get("frozen_retailer_location_id") is not None
                else None
            )
            if task_location_id != frozen_location_id:
                raise ValueError(
                    "collection task location identity differs from its immutable "
                    "geography location"
                )
            payload = dict(row["request_payload"])
            provenance = "frozen_task_contract"
            if "_provider_request_contract" not in payload:
                contract = self._provider_request_contracts.get(str(row["adapter_id"]))
                if contract is None:
                    raise ValueError(
                        "legacy collection task has no frozen provider request contract and "
                        f"adapter {row['adapter_id']!r} is absent from the supplied catalog"
                    )
                payload["_provider_request_contract"] = contract
                provenance = "reconstructed_current_catalog"
            normalized.append(
                {
                    **dict(row),
                    "request_payload": payload,
                    "_request_contract_provenance": provenance,
                }
            )
        return normalized

    @staticmethod
    def _unique_tasks(rows: Sequence[TaskMapping], label: str) -> dict[str, TaskMapping]:
        result: dict[str, TaskMapping] = {}
        for row in rows:
            key = canonical_request_key(row)
            if key in result:
                raise ValueError(f"{label} run contains duplicate canonical request evidence")
            result[key] = row
        return result

    @staticmethod
    async def _plan_row(
        connection: AsyncConnection, plan_id: str, *, for_update: bool = False
    ) -> RowMapping:
        row = (
            (
                await connection.execute(
                    text(
                        "SELECT * FROM collection_recovery_plan WHERE id::text = :plan_id"
                        + (" FOR UPDATE" if for_update else "")
                    ),
                    {"plan_id": plan_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise LookupError(f"collection recovery plan {plan_id!r} was not found")
        return row

    @staticmethod
    async def _batch_row(
        connection: AsyncConnection, batch_id: str, *, for_update: bool = False
    ) -> RowMapping:
        row = (
            (
                await connection.execute(
                    text(
                        "SELECT * FROM collection_recovery_batch WHERE id::text = :batch_id"
                        + (" FOR UPDATE" if for_update else "")
                    ),
                    {"batch_id": batch_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise LookupError(f"collection recovery batch {batch_id!r} was not found")
        return row

    @staticmethod
    async def _batch_accounted_credits(connection: AsyncConnection, batch_id: str) -> int:
        """Return terminal actuals plus active estimates/reservations without double count."""

        return int(
            (
                await connection.execute(
                    text(
                        """
                        WITH attached AS (
                          SELECT r.id,
                                 CASE WHEN r.status IN (
                                   'succeeded','completed_with_warnings','failed','cancelled'
                                 ) THEN r.actual_credits ELSE r.estimated_credits END AS credits
                          FROM collection_recovery_batch_run link
                          JOIN collection_run r ON r.id = link.collection_run_id
                          WHERE link.recovery_batch_id::text = :batch_id
                        ), plan_usage AS (
                          SELECT p.id,
                                 CASE
                                   WHEN p.recovery_collection_run_id IS NULL
                                     THEN p.maximum_credits
                                   WHEN r.status IN (
                                     'succeeded','completed_with_warnings','failed','cancelled'
                                   ) THEN r.actual_credits
                                   ELSE r.estimated_credits
                                 END AS credits
                          FROM collection_recovery_plan p
                          LEFT JOIN collection_run r ON r.id = p.recovery_collection_run_id
                          WHERE p.recovery_batch_id::text = :batch_id
                            AND p.reservation_active
                        )
                        SELECT COALESCE((SELECT sum(credits) FROM attached), 0)
                             + COALESCE((SELECT sum(credits) FROM plan_usage), 0)
                        """
                    ),
                    {"batch_id": batch_id},
                )
            ).scalar_one()
        )

    @staticmethod
    async def _batch_inventory_rows(
        connection: AsyncConnection, batch_id: str
    ) -> tuple[RecoveryBatchInventoryRun, ...]:
        rows = list(
            (
                await connection.execute(
                    text(
                        """
                        SELECT r.id::text, r.status, r.actual_credits, r.estimated_credits
                        FROM collection_recovery_batch_run link
                        JOIN collection_run r ON r.id = link.collection_run_id
                        WHERE link.recovery_batch_id::text = :batch_id
                        ORDER BY r.id
                        """
                    ),
                    {"batch_id": batch_id},
                )
            )
            .mappings()
            .all()
        )
        terminal = {"succeeded", "completed_with_warnings", "failed", "cancelled"}
        return tuple(
            RecoveryBatchInventoryRun(
                collection_run_id=str(row["id"]),
                status=str(row["status"]),
                actual_credits=int(row["actual_credits"]),
                estimated_credits=int(row["estimated_credits"]),
                accounted_credits=(
                    int(row["actual_credits"])
                    if str(row["status"]) in terminal
                    else int(row["estimated_credits"])
                ),
            )
            for row in rows
        )

    async def _batch_status_record(
        self, connection: AsyncConnection, batch: TaskMapping
    ) -> RecoveryBatchStatusRecord:
        batch_id = str(batch["id"])
        accounted = await self._batch_accounted_credits(connection, batch_id)
        plan_count = int(
            (
                await connection.execute(
                    text(
                        "SELECT count(*) FROM collection_recovery_plan "
                        "WHERE recovery_batch_id::text = :batch_id"
                    ),
                    {"batch_id": batch_id},
                )
            ).scalar_one()
        )
        unit_cost = Decimal(str(batch["unit_cost_usd"]))
        ceiling = int(batch["approved_credit_ceiling"])
        return RecoveryBatchStatusRecord(
            batch=self._batch_record(batch),
            accounted_credits=accounted,
            remaining_credits=max(ceiling - accounted, 0),
            approved_amount_usd=format(unit_cost * ceiling, "f"),
            accounted_amount_usd=format(unit_cost * accounted, "f"),
            recovery_plan_count=plan_count,
            runs=await self._batch_inventory_rows(connection, batch_id),
        )

    @staticmethod
    async def _insert_component(
        connection: AsyncConnection,
        input_set_id: str,
        run_id: str,
        *,
        ordinal: int,
        role: str,
        recovery_plan_id: str | None,
        row: TaskMapping,
    ) -> None:
        summary = {
            "status": str(row["status"]),
            "actual_credits": int(row["actual_credits"]),
            "definition_checksum": str(row["definition_checksum"]),
        }
        await connection.execute(
            text(
                """
                INSERT INTO analysis_input_component (
                  input_set_id, collection_run_id, ordinal, component_role,
                  recovery_plan_id, component_checksum, summary
                ) VALUES (
                  CAST(:input_set_id AS uuid), CAST(:run_id AS uuid), :ordinal,
                  :role, CAST(:recovery_plan_id AS uuid), :checksum,
                  CAST(:summary AS jsonb)
                )
                """
            ),
            {
                "input_set_id": input_set_id,
                "run_id": run_id,
                "ordinal": ordinal,
                "role": role,
                "recovery_plan_id": recovery_plan_id,
                "checksum": canonical_checksum(summary),
                "summary": _json(summary),
            },
        )

    @staticmethod
    def _plan_record(row: TaskMapping) -> RecoveryPlanRecord:
        return RecoveryPlanRecord(
            id=str(row["id"]),
            base_collection_run_id=str(row["base_collection_run_id"]),
            recovery_collection_run_id=(
                str(row["recovery_collection_run_id"])
                if row.get("recovery_collection_run_id") is not None
                else None
            ),
            recovery_batch_id=(
                str(row["recovery_batch_id"]) if row.get("recovery_batch_id") is not None else None
            ),
            plan_mode=str(row["plan_mode"]),
            reservation_active=bool(row["reservation_active"]),
            selection_policy_version=str(row["selection_policy_version"]),
            selection_checksum=str(row["selection_checksum"]),
            base_snapshot_checksum=str(row["base_snapshot_checksum"]),
            scope_projection_id=(
                str(row["scope_projection_id"])
                if row.get("scope_projection_id") is not None
                else None
            ),
            scope_projection_checksum=(
                str(row["scope_projection_checksum"])
                if row.get("scope_projection_checksum") is not None
                else None
            ),
            selection_scope=dict(row.get("selection_scope") or {}),
            plan_generation=int(row["plan_generation"]),
            supersedes_recovery_plan_id=(
                str(row["supersedes_recovery_plan_id"])
                if row.get("supersedes_recovery_plan_id") is not None
                else None
            ),
            continuation_of_recovery_plan_id=(
                str(row["continuation_of_recovery_plan_id"])
                if row.get("continuation_of_recovery_plan_id") is not None
                else None
            ),
            continuation_depth=int(row.get("continuation_depth") or 0),
            selected_task_count=int(row["selected_task_count"]),
            maximum_credits=int(row["maximum_credits"]),
            approved_credit_ceiling=int(row["approved_credit_ceiling"]),
            reason=str(row["reason"]),
            approved_by=str(row["approved_by"]),
            status=str(row["status"]),
            binding_manifest=dict(row.get("binding_manifest") or {}),
            created_at=row["created_at"],
        )

    @staticmethod
    def _scope_projection_record(row: TaskMapping) -> ScopeProjectionRecord:
        return ScopeProjectionRecord(
            id=str(row["id"]),
            base_collection_run_id=str(row["base_collection_run_id"]),
            retailer_id=str(row["retailer_id"]),
            projection_kind=str(row["projection_kind"]),
            policy_version=str(row["policy_version"]),
            base_snapshot_checksum=str(row["base_snapshot_checksum"]),
            source_audit_id=(
                str(row["source_audit_id"]) if row.get("source_audit_id") is not None else None
            ),
            source_evidence_checksum=str(row["source_evidence_checksum"]),
            raw_task_count=int(row["raw_task_count"]),
            retained_task_count=int(row["retained_task_count"]),
            excluded_task_count=int(row["excluded_task_count"]),
            raw_location_count=int(row["raw_location_count"]),
            retained_location_count=int(row["retained_location_count"]),
            excluded_location_count=int(row["excluded_location_count"]),
            raw_task_retention_ratio=str(row["raw_task_retention_ratio"]),
            governed_coverage_ratio=str(row["governed_coverage_ratio"]),
            minimum_scoreable_coverage=str(row["minimum_scoreable_coverage"]),
            scorecard_disposition=str(row["scorecard_disposition"]),
            projection_checksum=str(row["projection_checksum"]),
            review_reason=str(row["review_reason"]),
            reviewed_by=str(row["reviewed_by"]),
            manifest=dict(row["manifest"]),
            created_at=row["created_at"],
        )

    @staticmethod
    def _batch_record(row: TaskMapping) -> RecoveryBatchRecord:
        return RecoveryBatchRecord(
            id=str(row["id"]),
            organization_id=str(row["organization_id"]),
            spend_authorization_id=str(row["spend_authorization_id"]),
            phase_key=str(row["phase_key"]),
            inventory_checksum=str(row["inventory_checksum"]),
            authorized_run_ids=tuple(
                sorted(str(value) for value in (row.get("authorized_run_ids") or []))
            ),
            approved_credit_ceiling=int(row["approved_credit_ceiling"]),
            reserved_credits=int(row["reserved_credits"]),
            unit_cost_usd=format(Decimal(str(row["unit_cost_usd"])), "f"),
            currency=str(row["currency"]),
            reason=str(row["reason"]),
            approved_by=str(row["approved_by"]),
            status=str(row["status"]),
            created_at=row["created_at"],
            closed_at=row.get("closed_at"),
        )

    @staticmethod
    def _spend_authorization_record(row: TaskMapping) -> SpendAuthorizationRecord:
        return SpendAuthorizationRecord(
            id=str(row["id"]),
            organization_id=str(row["organization_id"]),
            phase_key=str(row["phase_key"]),
            inventory_checksum=str(row["inventory_checksum"]),
            authorized_run_ids=tuple(
                sorted(str(value) for value in (row.get("authorized_run_ids") or []))
            ),
            approved_credit_ceiling=int(row["approved_credit_ceiling"]),
            unit_cost_usd=format(Decimal(str(row["unit_cost_usd"])), "f"),
            currency=str(row["currency"]),
            reason=str(row["reason"]),
            authorized_by=str(row["authorized_by"]),
            status=str(row["status"]),
            created_at=row["created_at"],
            consumed_at=row.get("consumed_at"),
        )

    @staticmethod
    def _unavailability_record(row: TaskMapping) -> RetailerUnavailabilityApprovalRecord:
        return RetailerUnavailabilityApprovalRecord(
            id=str(row["id"]),
            base_collection_run_id=str(row["base_collection_run_id"]),
            retailer_id=str(row["retailer_id"]),
            base_snapshot_checksum=str(row["base_snapshot_checksum"]),
            reason=str(row["reason"]),
            approved_by=str(row["approved_by"]),
            status=str(row["status"]),
            created_at=row["created_at"],
            revoked_at=row.get("revoked_at"),
            revoked_by=(str(row["revoked_by"]) if row.get("revoked_by") is not None else None),
        )
