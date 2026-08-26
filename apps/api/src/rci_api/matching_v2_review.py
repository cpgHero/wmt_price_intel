"""Authenticated human certification API for Matching v2."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
from collections import defaultdict
from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal, Protocol, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from rci_analytics.matching_v2 import (
    AttributeValue,
    DeterministicMatchEngineV2,
    IdentifierEvidence,
    ListingEvidence,
    compile_matching_policy_v2,
)
from rci_analytics.product_pack import ProductPackLoader
from rci_contracts import ContractError, validate_instance

router = APIRouter(prefix="/api/v1/matching-v2", tags=["matching-v2-review"])

MatchTier = Literal[
    "exact_item",
    "exact_specification",
    "equivalent_product",
    "comparable_substitute",
    "custom_approved",
]
_ALL_MATCH_TIERS = (
    "exact_item",
    "exact_specification",
    "equivalent_product",
    "comparable_substitute",
    "custom_approved",
)
ReviewVerdict = Literal["comparable", "not_comparable", "insufficient_evidence"]
AIReviewSelectionMode = Literal["all_cases", "product_evidence_coverage"]
AttributeEvidenceBatchScope = Literal["latest_lineage", "all_lineages"]
AttributeEvidenceEligibility = Literal["all", "eligible", "ineligible"]
AttributeEvidenceDecisionStatus = Literal["all", "undecided", "verified", "rejected"]
AttributeEvidenceClaimStatus = Literal["all", "awaiting_review", "conflict", "verified", "rejected"]
AttributeEvidenceRelationship = Literal[
    "fills_unknown",
    "corroborates_existing",
    "refines_existing",
    "conflicts_with_existing",
    "invalid",
]
_MAX_AI_RETRY_ROUNDS = 4
_MAX_AI_REVIEW_BATCH_CASES = 1_500
_AI_RETRY_BLOCKED_MESSAGE = "does not match governed input or prompt"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)


def _checksum(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _matching_v2_certification_coverage(
    labels: Sequence[Mapping[str, Any]],
    cases: Sequence[Mapping[str, Any]],
    *,
    sampling: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Reconcile the certified gold set against every retailer's review queue.

    A zero in reporting is not interpretable without this funnel. It can mean no candidate was
    certified, every candidate was rejected, or certified relationships produced no admissible
    store-level observations. The release persists the first two distinctions; the report
    projection adds the observation outcome later.
    """

    retailer_by_case: dict[str, str] = {}
    retailer_counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "candidate_count": 0,
            "certified_count": 0,
            "certified_comparable_count": 0,
            "certified_not_comparable_count": 0,
            "reviewed_insufficient_evidence_count": 0,
            "pending_unreviewed_count": 0,
            "unresolved_count": 0,
        }
    )
    for case in cases:
        case_id = str(case.get("case_id") or case.get("external_case_id") or "").strip()
        retailer_id = str(case.get("competitor_retailer_id") or "").strip()
        if not case_id or not retailer_id:
            raise ValueError("matching v2 coverage requires a case id and competitor retailer")
        if case_id in retailer_by_case:
            raise ValueError(f"matching v2 coverage contains duplicate case {case_id!r}")
        retailer_by_case[case_id] = retailer_id
        retailer_counts[retailer_id]["candidate_count"] += 1

    certified_case_ids: set[str] = set()
    comparable_count = 0
    for label in labels:
        case_id = str(label.get("case_id") or "").strip()
        if case_id in certified_case_ids:
            raise ValueError(f"matching v2 gold set contains duplicate case {case_id!r}")
        certified_retailer_id = retailer_by_case.get(case_id)
        if certified_retailer_id is None:
            raise ValueError(f"matching v2 gold-set case {case_id!r} is absent from its queue")
        certified_case_ids.add(case_id)
        counts = retailer_counts[certified_retailer_id]
        counts["certified_count"] += 1
        if bool(label.get("expected_comparable")):
            comparable_count += 1
            counts["certified_comparable_count"] += 1
        else:
            counts["certified_not_comparable_count"] += 1

    reviewed_insufficient_evidence_count = 0
    pending_unreviewed_count = 0
    for case in cases:
        case_id = str(case.get("case_id") or case.get("external_case_id") or "").strip()
        if case_id in certified_case_ids:
            continue
        retailer_id = retailer_by_case[case_id]
        final_decision = case.get("final_decision")
        final_verdict = str(
            case.get("final_verdict")
            or (final_decision.get("verdict") if isinstance(final_decision, Mapping) else "")
            or ""
        )
        if final_verdict == "insufficient_evidence":
            reviewed_insufficient_evidence_count += 1
            retailer_counts[retailer_id]["reviewed_insufficient_evidence_count"] += 1
        else:
            pending_unreviewed_count += 1
            retailer_counts[retailer_id]["pending_unreviewed_count"] += 1

    retailers: list[dict[str, Any]] = []
    for retailer_id in sorted(retailer_counts):
        counts = retailer_counts[retailer_id]
        counts["unresolved_count"] = counts["candidate_count"] - counts["certified_count"]
        retailers.append({"competitor_retailer_id": retailer_id, **counts})

    available_counts = sampling.get("available_counts") if isinstance(sampling, Mapping) else None
    selected_counts = sampling.get("selected_counts") if isinstance(sampling, Mapping) else None
    source_candidate_count = (
        sum(
            max(0, int(value))
            for value in available_counts.values()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        )
        if isinstance(available_counts, Mapping)
        else len(retailer_by_case)
    )
    selected_candidate_count = (
        sum(
            max(0, int(value))
            for value in selected_counts.values()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        )
        if isinstance(selected_counts, Mapping)
        else len(retailer_by_case)
    )
    if selected_candidate_count != len(retailer_by_case):
        raise ValueError(
            "matching v2 queue sampling counts do not reconcile to its persisted cases"
        )
    selection_complete = source_candidate_count == selected_candidate_count
    selection_coverage_rate = (
        round(selected_candidate_count / source_candidate_count, 6)
        if source_candidate_count
        else 1.0
    )

    return {
        "authority": "matching_v2_certified_gold_set",
        "source_candidate_count": source_candidate_count,
        "selected_candidate_count": selected_candidate_count,
        "selection_complete": selection_complete,
        "selection_coverage_rate": selection_coverage_rate,
        "queue_case_count": len(retailer_by_case),
        "certified_label_count": len(certified_case_ids),
        "certified_comparable_count": comparable_count,
        "certified_not_comparable_count": len(certified_case_ids) - comparable_count,
        "unresolved_excluded_count": len(retailer_by_case) - len(certified_case_ids),
        "reviewed_insufficient_evidence_count": reviewed_insufficient_evidence_count,
        "pending_unreviewed_count": pending_unreviewed_count,
        "automatic_fallback_enabled": False,
        "retailers": retailers,
    }


def _is_ai_retry_integrity_failure(message: object) -> bool:
    """Keep governed input/prompt mismatches out of the paid retry boundary."""

    return _AI_RETRY_BLOCKED_MESSAGE in str(message or "").strip().lower()


def _observed_location_count(case: Mapping[str, Any], side: str) -> int:
    listing = case.get(f"{side}_listing")
    if not isinstance(listing, Mapping):
        return 0
    value = listing.get("observed_location_count", 0)
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _has_complete_observed_location_evidence(case: Mapping[str, Any]) -> bool:
    """Every review candidate must represent products actually seen in Search."""

    return all(_observed_location_count(case, side) > 0 for side in ("benchmark", "competitor"))


def _case_order_key(case: Mapping[str, Any]) -> tuple[int, int, int, str, str]:
    """Rank the benchmark footprint first, then competitor reach and review risk."""

    return (
        -_observed_location_count(case, "benchmark"),
        -_observed_location_count(case, "competitor"),
        -int(bool(case.get("critical"))),
        str(case.get("stratum") or ""),
        str(case.get("case_id") or ""),
    )


def _missing_evidence_listing_ids(case: Mapping[str, Any]) -> set[str]:
    """Return products whose hard-blocker evidence is unknown in this pair."""

    edge = case.get("edge")
    rows = edge.get("attribute_evidence") if isinstance(edge, Mapping) else None
    if not isinstance(rows, list):
        return set()
    missing: set[str] = set()
    for side in ("benchmark", "competitor"):
        listing = case.get(f"{side}_listing")
        listing = listing if isinstance(listing, Mapping) else {}
        listing_id = str(listing.get("listing_id") or case.get(f"{side}_listing_id") or "")
        if not listing_id:
            continue
        if any(
            isinstance(row, Mapping)
            and row.get("role") == "hard_blocker"
            and (
                row.get("outcome") == "unknown"
                or (
                    row.get("outcome") == "ignored"
                    and row.get("conditional_not_applicable") is not True
                )
            )
            and (
                row.get(f"{side}_value") in (None, "", "Unknown", "unknown")
                or row.get(f"{side}_source") in (None, "unresolved")
            )
            for row in rows
        ):
            missing.add(listing_id)
    return missing


def _product_evidence_coverage_selection(
    cases: Sequence[Mapping[str, Any]], *, limit: int
) -> tuple[list[Mapping[str, Any]], int]:
    """Greedily cover distinct unresolved products with the fewest pair-level AI calls."""

    uncovered = set().union(*(_missing_evidence_listing_ids(case) for case in cases))
    total_product_count = len(uncovered)
    remaining = list(cases)
    selected: list[Mapping[str, Any]] = []
    while uncovered and remaining and len(selected) < limit:
        candidate = min(
            remaining,
            key=lambda case: (
                -len(_missing_evidence_listing_ids(case) & uncovered),
                *_case_order_key(case),
            ),
        )
        covered = _missing_evidence_listing_ids(candidate) & uncovered
        if not covered:
            break
        selected.append(candidate)
        uncovered -= covered
        remaining.remove(candidate)
    return selected, total_product_count


def _apply_observed_location_sidecar(
    documents: Sequence[dict[str, Any]],
    *,
    queue_id: str,
    queue_version: str,
    root: Path,
) -> None:
    """Complete legacy read views without mutating immutable review evidence."""

    catalog_path = root / "config" / "matching-v2-review-footprints.json"
    if not catalog_path.is_file():
        return
    try:
        catalog = json.loads(catalog_path.read_text())
    except (OSError, json.JSONDecodeError):
        return
    queues = catalog.get("queues") if isinstance(catalog, Mapping) else None
    if not isinstance(queues, list):
        return
    matching_queue = next(
        (
            item
            for item in queues
            if isinstance(item, Mapping)
            and item.get("queue_id") == queue_id
            and item.get("queue_version") == queue_version
        ),
        None,
    )
    counts_by_case = matching_queue.get("cases") if isinstance(matching_queue, Mapping) else None
    listings_by_id = matching_queue.get("listings") if isinstance(matching_queue, Mapping) else None
    if not isinstance(counts_by_case, Mapping):
        counts_by_case = {}
    if not isinstance(listings_by_id, Mapping):
        listings_by_id = {}
    for document in documents:
        counts = counts_by_case.get(document.get("case_id"))
        if not isinstance(counts, Mapping):
            counts = {}
        for side in ("benchmark", "competitor"):
            listing = document.get(f"{side}_listing")
            if not isinstance(listing, dict):
                continue
            listing_id = str(
                listing.get("listing_id")
                or document.get(f"{side}_listing_id")
                or (
                    f"{listing.get('retailer_id')}:{listing.get('retailer_product_id')}"
                    if listing.get("retailer_id") and listing.get("retailer_product_id")
                    else ""
                )
                or ""
            )
            listing_evidence = listings_by_id.get(listing_id)
            if not isinstance(listing_evidence, Mapping):
                listing_evidence = {}
            count = counts.get(
                f"{side}_observed_location_count",
                listing_evidence.get("observed_location_count"),
            )
            if (
                "observed_location_count" not in listing
                and isinstance(count, int)
                and not isinstance(count, bool)
                and count >= 0
            ):
                listing["observed_location_count"] = count
            governance = listing.get("seller_governance")
            sidecar_governance = listing_evidence.get("seller_governance")
            if not isinstance(governance, Mapping) and isinstance(sidecar_governance, Mapping):
                listing["seller_governance"] = {
                    **dict(sidecar_governance),
                    "source": "reconciled_release_evidence",
                    "resolution_method": "legacy_queue_sidecar",
                }


def _enabled(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _repository_root() -> Path:
    return Path(os.getenv("RCI_REPOSITORY_ROOT", Path.cwd())).resolve()


def _review_queue_quarantines(root: Path) -> list[dict[str, Any]]:
    path = root / "config" / "matching-v2-quarantined-queues.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not load Matching v2 queue quarantine catalog: {exc}") from exc
    entries = document.get("queues") if isinstance(document, Mapping) else None
    if not isinstance(entries, list):
        raise ValueError("Matching v2 queue quarantine catalog must contain a queues array")
    return [dict(entry) for entry in entries if isinstance(entry, Mapping)]


def _review_queue_quarantine(
    root: Path, queue_id: str, queue_version: str
) -> dict[str, Any] | None:
    """Return an explicit operational quarantine without mutating queue history."""

    for entry in _review_queue_quarantines(root):
        if (
            str(entry.get("queue_id") or "") == queue_id
            and str(entry.get("queue_version") or "") == queue_version
        ):
            return entry
    return None


def _active_certification_policy(product_pack_id: str) -> dict[str, Any]:
    """Load the current Product Pack roles used at the certification boundary.

    Review queues remain immutable historical evidence. Certification applies the stricter of
    the queue snapshot and the currently active Product Pack so an unsafe legacy role cannot be
    approved after the category policy is corrected.
    """

    pack = ProductPackLoader(_repository_root()).load(product_pack_id)
    matching_v2 = pack.document.get("matching_v2")
    matching_v2 = matching_v2 if isinstance(matching_v2, Mapping) else {}
    configured_roles = matching_v2.get("attribute_roles")
    configured_roles = configured_roles if isinstance(configured_roles, Mapping) else {}
    attribute_roles = {
        str(attribute): str(rule.get("role") or "")
        for attribute, rule in configured_roles.items()
        if isinstance(rule, Mapping) and str(rule.get("role") or "")
    }
    hard_blockers = sorted(
        attribute for attribute, role in attribute_roles.items() if role == "hard_blocker"
    )
    unknown_is_blocking = {
        str(attribute): bool(rule.get("unknown_is_blocking", True))
        for attribute, rule in configured_roles.items()
        if isinstance(rule, Mapping) and str(rule.get("role") or "") == "hard_blocker"
    }
    attribute_definitions = {
        str(attribute.get("name") or ""): {
            "data_type": str(attribute.get("data_type") or "string"),
            "allowed_values": list(attribute.get("allowed_values") or []),
            "unknown_values": list(attribute.get("unknown_values") or []),
        }
        for attribute in pack.document.get("attributes", [])
        if isinstance(attribute, Mapping) and attribute.get("name")
    }
    comparison_rules = {
        str(attribute): dict(rule)
        for attribute, rule in configured_roles.items()
        if isinstance(rule, Mapping)
    }
    if not hard_blockers:
        raise ValueError(
            f"active Product Pack {product_pack_id!r} defines no certification hard blockers"
        )
    allowed_tiers = [
        tier
        for tier in _ALL_MATCH_TIERS
        if tier != "comparable_substitute"
        or bool(matching_v2.get("allow_comparable_substitute", True))
    ]
    return {
        "product_pack_id": pack.id,
        "product_pack_version": pack.version,
        "attribute_roles": attribute_roles,
        "hard_blocker_attributes": hard_blockers,
        "hard_blocker_unknown_is_blocking": unknown_is_blocking,
        "attribute_definitions": attribute_definitions,
        "comparison_rules": comparison_rules,
        "allowed_tiers": allowed_tiers,
        "allow_comparable_substitute": bool(matching_v2.get("allow_comparable_substitute", True)),
        "policy_checksum": pack.checksum,
        "queue_evidence_is_immutable": True,
        "stricter_active_policy_wins": True,
    }


def _hard_blocker_issues(
    case: Mapping[str, Any],
    hard_blocker_attributes: Sequence[str],
    unknown_nonblocking_attributes: Sequence[str] = (),
) -> list[dict[str, Any]]:
    edge = case.get("edge")
    edge = edge if isinstance(edge, Mapping) else {}
    evidence_rows = edge.get("attribute_evidence")
    evidence_rows = evidence_rows if isinstance(evidence_rows, list) else []
    evidence_by_attribute = {
        str(row.get("attribute") or ""): row
        for row in evidence_rows
        if isinstance(row, Mapping) and row.get("attribute")
    }
    issues: list[dict[str, Any]] = []
    unknown_nonblocking = set(unknown_nonblocking_attributes)
    for attribute in hard_blocker_attributes:
        evidence = evidence_by_attribute.get(attribute)
        outcome = str(evidence.get("outcome") or "missing") if evidence else "missing"
        if outcome in {"match", "within_tolerance"}:
            continue
        if (
            outcome == "ignored"
            and evidence is not None
            and evidence.get("conditional_not_applicable") is True
        ):
            continue
        if outcome in {"missing", "unknown"} and attribute in unknown_nonblocking:
            continue
        issues.append(
            {
                "attribute": attribute,
                "outcome": outcome,
                "benchmark_value": evidence.get("benchmark_value") if evidence else None,
                "competitor_value": evidence.get("competitor_value") if evidence else None,
                "reason": (
                    "The active Product Pack prohibits a known conflict on this attribute"
                    + (
                        "."
                        if attribute in unknown_nonblocking
                        else " and requires it to be known before certification."
                    )
                ),
            }
        )
    return issues


def _apply_active_certification_policy(
    case: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a derived review view/input without mutating immutable queue evidence."""

    document = dict(case)
    edge = document.get("edge")
    edge = dict(edge) if isinstance(edge, Mapping) else {}
    rows = edge.get("attribute_evidence")
    rows = rows if isinstance(rows, list) else []
    active_roles = policy.get("attribute_roles")
    active_roles = active_roles if isinstance(active_roles, Mapping) else {}
    role_strength = {
        "ignored": 0,
        "descriptive": 0,
        "identity": 1,
        "soft_comparator": 2,
        "required_exact": 3,
        "hard_blocker": 4,
    }
    updated_rows: list[Any] = []
    for value in rows:
        if not isinstance(value, Mapping):
            updated_rows.append(value)
            continue
        row = dict(value)
        attribute = str(row.get("attribute") or "")
        active_role = str(active_roles.get(attribute) or "")
        queue_role = str(row.get("role") or "")
        if active_role and role_strength.get(active_role, 0) > role_strength.get(queue_role, 0):
            row["queue_role"] = queue_role or None
            row["role"] = active_role
            row["role_source"] = "active_product_pack_certification_policy"
        rule = policy.get("comparison_rules", {}).get(attribute)
        applicability = rule.get("not_applicable_when") if isinstance(rule, Mapping) else None
        row.pop("conditional_not_applicable", None)
        if isinstance(applicability, Mapping):
            context_attribute = str(applicability.get("attribute") or "")
            allowed_values = {_canonical(value) for value in applicability.get("values") or []}
            context_row = next(
                (
                    candidate
                    for candidate in rows
                    if isinstance(candidate, Mapping)
                    and str(candidate.get("attribute") or "") == context_attribute
                ),
                None,
            )
            if (
                isinstance(context_row, Mapping)
                and _canonical(context_row.get("benchmark_value")) in allowed_values
                and _canonical(context_row.get("competitor_value")) in allowed_values
            ):
                row["outcome"] = "ignored"
                row["conditional_not_applicable"] = True
                row["rationale"] = (
                    f"Not applicable when both {context_attribute} values are governed "
                    "multi-ingredient formulations."
                )
        updated_rows.append(row)
    edge["attribute_evidence"] = updated_rows
    document["edge"] = edge
    document["certification_policy"] = dict(policy)
    document["certification_hard_blocker_attributes"] = sorted(
        {
            *(str(value) for value in policy.get("hard_blocker_attributes") or []),
            *(
                str(row.get("attribute"))
                for row in updated_rows
                if isinstance(row, Mapping)
                and row.get("attribute")
                and str(row.get("role") or "") == "hard_blocker"
            ),
        }
    )
    unknown_is_blocking = policy.get("hard_blocker_unknown_is_blocking")
    unknown_is_blocking = unknown_is_blocking if isinstance(unknown_is_blocking, Mapping) else {}
    document["certification_unknown_nonblocking_attributes"] = sorted(
        attribute
        for attribute in document["certification_hard_blocker_attributes"]
        if unknown_is_blocking.get(attribute) is False
    )
    document["certification_blockers"] = _hard_blocker_issues(
        document,
        document["certification_hard_blocker_attributes"],
        document["certification_unknown_nonblocking_attributes"],
    )
    allowed_tiers = [
        str(value)
        for value in policy.get("allowed_tiers", _ALL_MATCH_TIERS)
        if str(value) in _ALL_MATCH_TIERS
    ]
    document["certification_allowed_tiers"] = allowed_tiers
    final_decision = document.get("final_decision")
    final_decision = final_decision if isinstance(final_decision, Mapping) else {}
    final_tiers = (
        [str(value) for value in final_decision.get("allowed_tiers") or []]
        if final_decision.get("verdict") == "comparable"
        else []
    )
    document["certification_tier_blockers"] = sorted(
        tier for tier in final_tiers if tier not in allowed_tiers
    )
    reconciliation = document.get("attribute_evidence_reconciliation")
    reconciliation = reconciliation if isinstance(reconciliation, Mapping) else {}
    reconciliation_conflicts = reconciliation.get("conflicts")
    reconciliation_conflicts = (
        reconciliation_conflicts if isinstance(reconciliation_conflicts, list) else []
    )
    recomputation = document.get("certification_engine_recomputation")
    recomputation = recomputation if isinstance(recomputation, Mapping) else {}
    document["certification_release_blocked"] = bool(
        document["certification_blockers"]
        or document["certification_tier_blockers"]
        or reconciliation_conflicts
        or recomputation.get("status") == "blocked"
    )
    return document


def _listing_image_urls(listing: Any) -> set[str]:
    """Return exact PDP/image references attached to one immutable listing."""

    if not isinstance(listing, Mapping):
        return set()
    images: set[str] = set()
    for key in ("image_url", "image_primary"):
        if listing.get(key):
            images.add(str(listing[key]))
    for key in ("image_urls", "images"):
        values = listing.get(key)
        if isinstance(values, list):
            images.update(str(value) for value in values if value)
    pdp = listing.get("pdp_evidence")
    if isinstance(pdp, Mapping):
        images.update(_listing_image_urls(pdp))
    return images


def _attribute_value_is_unresolved(
    value: Any,
    definition: Mapping[str, Any],
    *,
    source: str | None = None,
) -> bool:
    """Treat an absent, declared-unknown, or default-only value as unresolved."""

    if value is None or value == "" or value == []:
        return True
    if str(source or "").strip().casefold() in {"unresolved", "product_pack_default"}:
        return True
    unknown_values = list(definition.get("unknown_values") or [])
    if isinstance(value, str):
        rendered = value.strip().casefold()
        if rendered in {"", "unknown"}:
            return True
        return any(
            isinstance(unknown, str) and rendered == unknown.strip().casefold()
            for unknown in unknown_values
        )
    return _canonical(value) in {_canonical(unknown) for unknown in unknown_values}


_LOCKED_ATTRIBUTE_SOURCE_MARKERS = (
    "configured_constant",
    "exact_alias",
    "exact_canonical",
    "governed_override",
    "human_verified",
    "manual_override",
    "product_pack_override",
    "retailer_pack",
)
_ATTRIBUTE_COMPARISON_STOP_WORDS = {"and", "plus", "with"}


def _attribute_source_is_locked(source: Any) -> bool:
    rendered = str(source or "").strip().casefold()
    return any(marker in rendered for marker in _LOCKED_ATTRIBUTE_SOURCE_MARKERS)


def _attribute_comparison_tokens(value: Any) -> set[str]:
    values = value if isinstance(value, list) else [value]
    tokens: set[str] = set()
    for item in values:
        tokens.update(
            token
            for token in re.findall(r"[a-z0-9]+", str(item).casefold())
            if token not in _ATTRIBUTE_COMPARISON_STOP_WORDS
        )
    return tokens


def _attribute_evidence_relationship(
    *,
    attribute: str,
    current_value: Any,
    current_source: Any,
    proposed_value: Any,
    definition: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> AttributeEvidenceRelationship:
    """Classify source-bound label evidence without equating non-null with correct."""

    if _attribute_value_is_unresolved(
        current_value,
        definition,
        source=str(current_source or ""),
    ):
        return "fills_unknown"
    try:
        normalized_current = _normalize_reconciled_attribute(attribute, current_value, policy)
    except ValueError:
        return "conflicts_with_existing"
    data_type = str(definition.get("data_type") or "string")
    if data_type == "number":
        return (
            "corroborates_existing"
            if float(normalized_current) == float(proposed_value)
            else "conflicts_with_existing"
        )
    if data_type in {"string", "enum", "array"}:
        current_tokens = _attribute_comparison_tokens(normalized_current)
        proposed_tokens = _attribute_comparison_tokens(proposed_value)
        if current_tokens == proposed_tokens:
            return "corroborates_existing"
        if current_tokens and current_tokens < proposed_tokens:
            return "refines_existing"
    return "conflicts_with_existing"


def _normalize_reconciled_attribute(attribute: str, value: Any, policy: Mapping[str, Any]) -> Any:
    definitions = policy.get("attribute_definitions")
    definitions = definitions if isinstance(definitions, Mapping) else {}
    definition = definitions.get(attribute)
    if not isinstance(definition, Mapping):
        raise ValueError(f"attribute {attribute!r} is not declared by the active Product Pack")
    data_type = str(definition.get("data_type") or "string")
    if data_type == "number":
        match = re.search(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)", str(value))
        if match is None:
            raise ValueError("the proposed numeric value contains no number")
        number = float(match.group(0))
        return int(number) if number.is_integer() else number
    if data_type == "enum":
        rendered = " ".join(str(value).split())
        allowed = [str(item) for item in definition.get("allowed_values") or []]
        canonical = {item.casefold(): item for item in allowed}.get(rendered.casefold())
        if canonical is None:
            raise ValueError("the proposed value is outside the Product Pack enum")
        return canonical
    if data_type == "array":
        if not isinstance(value, list):
            raise ValueError("the proposed array value is not an array")
        return [" ".join(str(item).split()) for item in value if str(item).strip()]
    rendered = " ".join(str(value).split())
    if not rendered:
        raise ValueError("the proposed value is empty")
    return rendered


def _reconciliation_proposals(
    case: Mapping[str, Any], policy: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Build server-owned, checksum-bound proposals from the latest advisory AI output."""

    ai_draft = case.get("ai_draft")
    if not isinstance(ai_draft, Mapping) or ai_draft.get("status") != "succeeded":
        return []
    output = ai_draft.get("output_document")
    result = output.get("result") if isinstance(output, Mapping) else None
    proposals = result.get("attribute_proposals") if isinstance(result, Mapping) else None
    if not isinstance(proposals, list):
        return []
    benchmark_images = _listing_image_urls(case.get("benchmark_listing"))
    competitor_images = _listing_image_urls(case.get("competitor_listing"))
    case_checksum = str(case.get("case_checksum") or _checksum(case.get("case_id")))
    output_checksum = str(ai_draft.get("output_checksum") or "")
    policy_checksum = str(policy.get("policy_checksum") or "")
    attributes = policy.get("attribute_definitions")
    attributes = attributes if isinstance(attributes, Mapping) else {}
    edge = case.get("edge")
    evidence_rows = edge.get("attribute_evidence") if isinstance(edge, Mapping) else None
    evidence_by_attribute = {
        str(row.get("attribute") or ""): row
        for row in evidence_rows or []
        if isinstance(row, Mapping)
    }
    output_rows: list[dict[str, Any]] = []
    for index, raw in enumerate(proposals):
        if not isinstance(raw, Mapping):
            continue
        attribute = str(raw.get("attribute") or "").strip()
        source_url = str(raw.get("source_image_url") or "").strip()
        visible_text = str(raw.get("visible_text") or "").strip()
        source = str(raw.get("evidence_source") or "").strip()
        try:
            confidence = float(raw.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0.0
        sides = []
        if source_url and source_url in benchmark_images:
            sides.append("benchmark")
        if source_url and source_url in competitor_images:
            sides.append("competitor")
        reasons: list[str] = []
        if attribute not in attributes:
            reasons.append("attribute_not_in_active_product_pack")
        if source != "image":
            reasons.append("structured_ai_proposal_is_not_source_attributable")
        if len(sides) != 1:
            reasons.append("image_must_resolve_to_exactly_one_listing")
        side = sides[0] if len(sides) == 1 else None
        definition = attributes.get(attribute)
        definition = definition if isinstance(definition, Mapping) else {}
        evidence_row = evidence_by_attribute.get(attribute)
        current_value = (
            evidence_row.get(f"{side}_value")
            if side and isinstance(evidence_row, Mapping)
            else None
        )
        current_source = (
            evidence_row.get(f"{side}_source")
            if side and isinstance(evidence_row, Mapping)
            else None
        )
        if side and not isinstance(evidence_row, Mapping):
            reasons.append("attribute_not_present_in_governed_edge")
        if not visible_text:
            reasons.append("visible_label_text_required")
        if confidence < 0.85:
            reasons.append("confidence_below_85_percent")
        normalized_value: Any = None
        relationship: AttributeEvidenceRelationship = "invalid"
        if not reasons:
            try:
                normalized_value = _normalize_reconciled_attribute(
                    attribute, raw.get("value"), policy
                )
                definition = attributes.get(attribute)
                definition = definition if isinstance(definition, Mapping) else {}
                unknown_values = {
                    _canonical(value) for value in definition.get("unknown_values") or []
                }
                if _canonical(normalized_value) in unknown_values:
                    reasons.append("declared_unknown_value_cannot_resolve_evidence")
                else:
                    relationship = _attribute_evidence_relationship(
                        attribute=attribute,
                        current_value=current_value,
                        current_source=current_source,
                        proposed_value=normalized_value,
                        definition=definition,
                        policy=policy,
                    )
                    if relationship == "corroborates_existing":
                        reasons.append("proposal_corroborates_current_value")
                    elif relationship in {
                        "refines_existing",
                        "conflicts_with_existing",
                    } and _attribute_source_is_locked(current_source):
                        reasons.append("current_value_has_locked_governed_authority")
            except ValueError as exc:
                reasons.append(f"normalization_failed:{exc}")
        listing = case.get(f"{side}_listing") if side else None
        listing = listing if isinstance(listing, Mapping) else {}
        descriptor = {
            "proposal_index": index,
            "ai_task_id": str(ai_draft.get("id") or ""),
            "ai_output_checksum": output_checksum,
            "case_checksum": case_checksum,
            "policy_checksum": policy_checksum,
            "listing_role": side,
            "listing_id": str(listing.get("listing_id") or case.get(f"{side}_listing_id") or ""),
            "attribute": attribute,
            "raw_value": raw.get("value"),
            "normalized_value": normalized_value,
            "evidence_source": source,
            "confidence": confidence,
            "visible_text": visible_text or None,
            "source_image_url": source_url or None,
            "eligible": not reasons,
            "ineligibility_reasons": reasons,
        }
        descriptor["proposal_checksum"] = _checksum(descriptor)
        descriptor.update(
            {
                "current_value": current_value,
                "current_source": current_source,
                "evidence_relationship": relationship,
                "decision_effect": {
                    "fills_unknown": "fill_missing_value",
                    "corroborates_existing": "no_change",
                    "refines_existing": "replace_with_verified_refinement",
                    "conflicts_with_existing": "replace_with_verified_correction",
                    "invalid": "no_change",
                }[relationship],
            }
        )
        output_rows.append(descriptor)
    return output_rows


def _reconciled_outcome(
    benchmark: Any, competitor: Any, attribute: str, policy: Mapping[str, Any]
) -> str:
    if benchmark is None or competitor is None:
        return "unknown"
    if isinstance(benchmark, str) and benchmark.casefold() == "unknown":
        return "unknown"
    if isinstance(competitor, str) and competitor.casefold() == "unknown":
        return "unknown"
    if isinstance(benchmark, (int, float)) and isinstance(competitor, (int, float)):
        rules = policy.get("comparison_rules")
        rule = rules.get(attribute) if isinstance(rules, Mapping) else None
        try:
            tolerance = float(rule.get("numeric_tolerance", 0)) if isinstance(rule, Mapping) else 0
        except (TypeError, ValueError):
            tolerance = 0
        difference = abs(float(benchmark) - float(competitor))
        if difference == 0:
            return "match"
        return "within_tolerance" if difference <= tolerance else "conflict"
    if isinstance(benchmark, list) and isinstance(competitor, list):
        benchmark_values = {str(value).casefold() for value in benchmark}
        competitor_values = {str(value).casefold() for value in competitor}
        return "match" if benchmark_values == competitor_values else "conflict"
    return "match" if str(benchmark).casefold() == str(competitor).casefold() else "conflict"


def _apply_attribute_reconciliation(
    case: Mapping[str, Any],
    policy: Mapping[str, Any],
    decisions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Overlay only currently verified evidence into a derived certification view."""

    document = dict(case)
    proposals = _reconciliation_proposals(document, policy)
    attribute_definitions = policy.get("attribute_definitions")
    attribute_definitions = (
        attribute_definitions if isinstance(attribute_definitions, Mapping) else {}
    )
    latest_by_proposal: dict[str, Mapping[str, Any]] = {}
    for decision_row in decisions:
        checksum = str(decision_row.get("proposal_checksum") or "")
        if checksum and checksum not in latest_by_proposal:
            latest_by_proposal[checksum] = decision_row
    for proposal in proposals:
        current_decision = latest_by_proposal.get(str(proposal["proposal_checksum"]))
        proposal["decision"] = dict(current_decision) if current_decision is not None else None
    verified: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for proposal in proposals:
        current_decision = proposal.get("decision")
        if (
            proposal.get("eligible")
            and isinstance(current_decision, Mapping)
            and current_decision.get("decision") == "verified"
        ):
            verified[(str(proposal["listing_role"]), str(proposal["attribute"]))].append(proposal)
    # A label attribute belongs to the distinct retailer product, not to only the
    # pair in which it was first reviewed. Reuse a human-verified image proposal
    # across cases in the same immutable queue when its Product Pack policy,
    # listing identity, normalized value, and source attribution remain bound in
    # the persisted proposal document. This removes repeated review without
    # weakening the evidence gate or mutating raw Search/PDP evidence.
    listing_sides = {
        str(document.get(f"{side}_listing_id") or ""): side for side in ("benchmark", "competitor")
    }
    for side in ("benchmark", "competitor"):
        listing = document.get(f"{side}_listing")
        if isinstance(listing, Mapping) and listing.get("listing_id"):
            listing_sides[str(listing["listing_id"])] = side
    local_proposal_checksums = {
        str(proposal.get("proposal_checksum") or "") for proposal in proposals
    }
    reused_decision_ids: set[str] = set()
    for decision_row in latest_by_proposal.values():
        if decision_row.get("decision") != "verified":
            continue
        proposal_checksum = str(decision_row.get("proposal_checksum") or "")
        decision_id = str(decision_row.get("id") or "")
        if proposal_checksum in local_proposal_checksums or (
            decision_id and decision_id in reused_decision_ids
        ):
            continue
        source_proposal = decision_row.get("proposal_document")
        if not isinstance(source_proposal, Mapping):
            continue
        listing_id = str(source_proposal.get("listing_id") or "")
        reuse_side = listing_sides.get(listing_id)
        attribute = str(source_proposal.get("attribute") or "")
        if (
            reuse_side is None
            or not source_proposal.get("eligible")
            or str(source_proposal.get("policy_checksum") or "")
            != str(policy.get("policy_checksum") or "")
            or attribute not in attribute_definitions
        ):
            continue
        try:
            normalized_value = _normalize_reconciled_attribute(
                attribute, source_proposal.get("normalized_value"), policy
            )
        except ValueError:
            continue
        verified[(reuse_side, attribute)].append(
            {
                **dict(source_proposal),
                "proposal_checksum": proposal_checksum,
                "listing_role": reuse_side,
                "normalized_value": normalized_value,
                "decision": dict(decision_row),
                "reused_product_evidence": True,
            }
        )
        if decision_id:
            reused_decision_ids.add(decision_id)
    resolved: dict[tuple[str, str], dict[str, Any]] = {}
    conflicts: list[dict[str, Any]] = []
    for key, values in verified.items():
        distinct = {_canonical(value.get("normalized_value")) for value in values}
        if len(distinct) != 1:
            conflicts.append(
                {
                    "listing_role": key[0],
                    "attribute": key[1],
                    "reason": "multiple_verified_values_conflict",
                    "proposal_checksums": [value["proposal_checksum"] for value in values],
                }
            )
        else:
            resolved[key] = values[0]
    edge = document.get("edge")
    edge = dict(edge) if isinstance(edge, Mapping) else {}
    rows = [dict(row) for row in edge.get("attribute_evidence", []) if isinstance(row, Mapping)]
    by_attribute = {str(row.get("attribute") or ""): row for row in rows}
    for (_, attribute), proposal in resolved.items():
        row = by_attribute.setdefault(attribute, {"attribute": attribute})
        side = str(proposal["listing_role"])
        current_value = row.get(f"{side}_value")
        current_source = row.get(f"{side}_source")
        definition = attribute_definitions.get(attribute)
        definition = definition if isinstance(definition, Mapping) else {}
        target_relationship = _attribute_evidence_relationship(
            attribute=attribute,
            current_value=current_value,
            current_source=current_source,
            proposed_value=proposal["normalized_value"],
            definition=definition,
            policy=policy,
        )
        if target_relationship in {
            "refines_existing",
            "conflicts_with_existing",
        } and _attribute_source_is_locked(current_source):
            conflicts.append(
                {
                    "listing_role": side,
                    "attribute": attribute,
                    "reason": "verified_evidence_conflicts_with_locked_current_value",
                    "proposal_checksums": [proposal["proposal_checksum"]],
                }
            )
            continue
        if target_relationship == "corroborates_existing":
            continue
        row[f"{side}_superseded_value"] = current_value
        row[f"{side}_superseded_source"] = current_source
        row[f"{side}_reconciliation_relationship"] = target_relationship
        row[f"{side}_value"] = proposal["normalized_value"]
        row[f"{side}_source"] = "human_verified_ai_vision"
        row[f"{side}_reconciliation_decision_id"] = proposal["decision"].get("id")
        row["outcome"] = _reconciled_outcome(
            row.get("benchmark_value"), row.get("competitor_value"), attribute, policy
        )
    edge["attribute_evidence"] = list(by_attribute.values())
    document["edge"] = edge
    evidence_refs = [str(value) for value in document.get("evidence_refs") or []]
    for proposal in resolved.values():
        decision_id = str(proposal["decision"].get("id") or "")
        reference = f"matching-v2-attribute-evidence-decision:{decision_id}"
        if decision_id and reference not in evidence_refs:
            evidence_refs.append(reference)
    document["evidence_refs"] = evidence_refs
    document["attribute_evidence_reconciliation"] = {
        "schema_version": "1.0.0",
        "advisory_proposal_count": len(proposals),
        "eligible_proposal_count": sum(1 for row in proposals if row["eligible"]),
        "verified_proposal_count": sum(
            1
            for row in proposals
            if isinstance(row.get("decision"), Mapping)
            and row["decision"].get("decision") == "verified"
        ),
        "reused_product_evidence_count": sum(
            1
            for values in verified.values()
            for value in values
            if value.get("reused_product_evidence")
        ),
        "conflicts": conflicts,
        "proposals": proposals,
        "raw_evidence_mutated": False,
        "human_verification_required": True,
    }
    return document


def _listing_evidence_from_certification_view(
    document: Mapping[str, Any], side: Literal["benchmark", "competitor"]
) -> ListingEvidence:
    """Rebuild engine input from the derived edge without changing queue evidence."""

    listing = document.get(f"{side}_listing")
    listing = listing if isinstance(listing, Mapping) else {}
    listed_attributes = listing.get("attributes")
    listed_attributes = listed_attributes if isinstance(listed_attributes, Mapping) else {}
    edge = document.get("edge")
    edge = edge if isinstance(edge, Mapping) else {}
    rows = edge.get("attribute_evidence")
    rows = rows if isinstance(rows, list) else []
    attributes: dict[str, AttributeValue] = {}
    for row in rows:
        if not isinstance(row, Mapping) or not row.get("attribute"):
            continue
        attribute = str(row["attribute"])
        value = row.get(f"{side}_value")
        listed = listed_attributes.get(attribute)
        listed = listed if isinstance(listed, Mapping) else {}
        source = str(row.get(f"{side}_source") or listed.get("source") or "unresolved")
        if source == "human_verified_ai_vision":
            reliability = 1.0
            review_status = "verified"
        else:
            try:
                reliability = float(listed.get("reliability", row.get("reliability", 0)))
            except (TypeError, ValueError):
                reliability = 0.0
            review_status = str(listed.get("review_status") or "unreviewed")
            if review_status not in {"unreviewed", "verified", "conflicted"}:
                review_status = "unreviewed"
        attributes[attribute] = AttributeValue(
            value=value,
            source=source,
            reliability=max(0.0, min(1.0, reliability)),
            review_status=cast(Any, review_status),
        )
    identifiers: list[IdentifierEvidence] = []
    for row in listing.get("identifiers") or []:
        if not isinstance(row, Mapping) or not row.get("scheme") or not row.get("value"):
            continue
        status_value = str(row.get("verification_status") or "observed")
        if status_value not in {"observed", "verified", "disputed"}:
            status_value = "observed"
        identifiers.append(
            IdentifierEvidence(
                scheme=str(row["scheme"]),
                value=str(row["value"]),
                verification_status=cast(Any, status_value),
                source=str(row.get("source") or "unknown"),
            )
        )
    brand_type = str(listing.get("brand_type") or "unclassified")
    if brand_type not in {"private_label", "regional", "national", "unclassified"}:
        brand_type = "unclassified"
    image_urls = tuple(
        dict.fromkeys(str(value) for value in listing.get("image_urls") or [] if value)
    )
    retrieval_contexts = tuple(
        dict.fromkeys(str(value) for value in listing.get("retrieval_contexts") or [] if value)
    )
    return ListingEvidence(
        listing_id=str(
            listing.get("listing_id") or document.get(f"{side}_listing_id") or f"{side}:unknown"
        ),
        retailer_id=str(listing.get("retailer_id") or "unknown"),
        retailer_product_id=str(listing.get("retailer_product_id") or "unknown"),
        attributes=attributes,
        identifiers=tuple(identifiers),
        title=str(listing.get("title")) if listing.get("title") is not None else None,
        image_url=(str(listing.get("image_url")) if listing.get("image_url") else None),
        image_urls=image_urls,
        product_url=(str(listing.get("product_url")) if listing.get("product_url") else None),
        brand=str(listing.get("brand")) if listing.get("brand") is not None else None,
        brand_type=cast(Any, brand_type),
        brand_verified=bool(listing.get("brand_verified", False)),
        brand_governance=(
            dict(listing.get("brand_governance") or {})
            if isinstance(listing.get("brand_governance"), Mapping)
            else {}
        ),
        seller_governance=(
            dict(listing.get("seller_governance") or {})
            if isinstance(listing.get("seller_governance"), Mapping)
            else {}
        ),
        pdp_evidence=(
            dict(listing.get("pdp_evidence") or {})
            if isinstance(listing.get("pdp_evidence"), Mapping)
            else {}
        ),
        retrieval_contexts=retrieval_contexts,
        observed_location_count=int(listing.get("observed_location_count") or 0),
    )


@lru_cache(maxsize=64)
def _compiled_certification_matching_policy(
    product_pack_id: str, profile_id: str, policy_checksum: str
) -> Any:
    pack = ProductPackLoader(_repository_root()).load(product_pack_id)
    if str(pack.checksum) != policy_checksum:
        raise ValueError("the active Product Pack checksum changed during recomputation")
    return compile_matching_policy_v2(pack, profile_id)


def _recompute_certification_engine(
    case: Mapping[str, Any], policy: Mapping[str, Any]
) -> dict[str, Any]:
    """Re-run the deterministic engine against the governed derived evidence view."""

    document = dict(case)
    edge = document.get("edge")
    edge = dict(edge) if isinstance(edge, Mapping) else {}
    edge_policy = edge.get("policy")
    edge_policy = edge_policy if isinstance(edge_policy, Mapping) else {}
    policy_id = str(edge_policy.get("policy_id") or "")
    product_pack_id = str(policy.get("product_pack_id") or "")
    expected_prefix = f"{product_pack_id}:"
    profile_id = (
        policy_id.removeprefix(expected_prefix) if policy_id.startswith(expected_prefix) else ""
    )
    reconciliation = document.get("attribute_evidence_reconciliation")
    reconciliation = reconciliation if isinstance(reconciliation, Mapping) else {}
    conflicts = reconciliation.get("conflicts")
    conflicts = conflicts if isinstance(conflicts, list) else []
    failure: str | None = None
    decision_contract: dict[str, Any] | None = None
    try:
        if not product_pack_id or not profile_id:
            raise ValueError("the queue edge does not identify an active Product Pack profile")
        if conflicts:
            raise ValueError("verified attribute evidence conflicts for this product pair")
        matching_policy = _compiled_certification_matching_policy(
            product_pack_id,
            profile_id,
            str(policy.get("policy_checksum") or ""),
        )
        decided_at = (
            str(
                (edge.get("decision") or {}).get("decided_at")
                if isinstance(edge.get("decision"), Mapping)
                else ""
            )
            or "1970-01-01T00:00:00Z"
        )
        decision = DeterministicMatchEngineV2().evaluate(
            _listing_evidence_from_certification_view(document, "benchmark"),
            _listing_evidence_from_certification_view(document, "competitor"),
            matching_policy,
            decided_at=decided_at,
        )
        decision_contract = decision.to_contract()
    except (KeyError, TypeError, ValueError) as exc:
        failure = str(exc)

    queue_engine = document.get("queue_engine_proposal")
    if not isinstance(queue_engine, Mapping):
        queue_engine = document.get("engine_proposal")
    document["queue_engine_proposal"] = (
        dict(queue_engine) if isinstance(queue_engine, Mapping) else {}
    )
    if decision_contract is None:
        edge["tier"] = None
        edge["status"] = "unresolved"
        edge["eligible_price_bases"] = []
        document["engine_proposal"] = {
            "edge_id": None,
            "tier": None,
            "status": "unresolved",
            "decision_reason": failure,
            "evidence_coverage": {},
            "origin": "derived_certification_recomputation",
        }
        recomputation = {
            "status": "blocked",
            "error": failure,
            "active_policy_checksum": policy.get("policy_checksum"),
            "profile_id": profile_id or None,
        }
    else:
        for key in (
            "tier",
            "status",
            "eligible_price_bases",
            "evidence_coverage",
            "attribute_evidence",
        ):
            edge[key] = decision_contract[key]
        edge["policy"] = decision_contract["policy"]
        edge["decision"] = decision_contract["decision"]
        document["engine_proposal"] = {
            "edge_id": decision_contract["edge_id"],
            "tier": decision_contract["tier"],
            "status": decision_contract["status"],
            "decision_reason": decision_contract["decision"]["reason"],
            "evidence_coverage": decision_contract["evidence_coverage"],
            "origin": "derived_certification_recomputation",
        }
        recomputation = {
            "status": "succeeded",
            "error": None,
            "active_policy_checksum": policy.get("policy_checksum"),
            "profile_id": profile_id,
            "queue_engine_proposal": document["queue_engine_proposal"],
            "derived_engine_proposal": document["engine_proposal"],
        }
    document["edge"] = edge
    recomputation["checksum"] = _checksum(recomputation)
    document["certification_engine_recomputation"] = recomputation
    document["certification_view_checksum"] = _checksum(
        {
            "case_checksum": document.get("case_checksum"),
            "active_policy_checksum": policy.get("policy_checksum"),
            "engine_proposal": document.get("engine_proposal"),
            "eligible_price_bases": edge.get("eligible_price_bases"),
            "attribute_evidence": edge.get("attribute_evidence"),
            "evidence_refs": sorted(str(value) for value in document.get("evidence_refs") or []),
            "recomputation_checksum": recomputation["checksum"],
        }
    )
    return document


def _derived_certification_view(
    case: Mapping[str, Any],
    policy: Mapping[str, Any],
    decisions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build the one certification view shared by AI, UI, bulk, and release paths."""

    reconciled = _apply_attribute_reconciliation(case, policy, decisions)
    governed = _apply_active_certification_policy(reconciled, policy)
    recomputed = _recompute_certification_engine(governed, policy)
    return _apply_active_certification_policy(recomputed, policy)


def _attribute_evidence_proposal_index(
    queue_view: Mapping[str, Any],
    *,
    batch_scope: AttributeEvidenceBatchScope,
    root_batch_id: str | None,
    eligibility: AttributeEvidenceEligibility,
    decision_status: AttributeEvidenceDecisionStatus,
    offset: int,
    limit: int,
) -> dict[str, Any]:
    """Project latest advisory image proposals into an administrator review index.

    The review queue remains immutable. This projection only groups the latest task for each
    case by its retry-lineage root and exposes the existing checksum-bound decision lane.
    """

    queue = queue_view.get("queue")
    queue = queue if isinstance(queue, Mapping) else {}
    cases = queue_view.get("cases")
    cases = cases if isinstance(cases, list) else []
    rows: list[dict[str, Any]] = []
    lineages: dict[str, dict[str, Any]] = {}
    for raw_case in cases:
        if not isinstance(raw_case, Mapping):
            continue
        ai_draft = raw_case.get("ai_draft")
        if not isinstance(ai_draft, Mapping) or ai_draft.get("status") != "succeeded":
            continue
        batch_id = str(ai_draft.get("batch_id") or "")
        lineage_id = str(ai_draft.get("root_batch_id") or batch_id)
        if not lineage_id:
            continue
        reconciliation = raw_case.get("attribute_evidence_reconciliation")
        reconciliation = reconciliation if isinstance(reconciliation, Mapping) else {}
        proposals = reconciliation.get("proposals")
        proposals = proposals if isinstance(proposals, list) else []
        lineage = lineages.setdefault(
            lineage_id,
            {
                "root_batch_id": lineage_id,
                "batch_ids": set(),
                "model_ids": set(),
                "case_ids": set(),
                "proposal_count": 0,
                "eligible_proposal_count": 0,
                "ineligible_proposal_count": 0,
                "undecided_proposal_count": 0,
                "verified_proposal_count": 0,
                "rejected_proposal_count": 0,
                "latest_activity_at": "",
            },
        )
        if batch_id:
            lineage["batch_ids"].add(batch_id)
        if ai_draft.get("model_id"):
            lineage["model_ids"].add(str(ai_draft["model_id"]))
        lineage["case_ids"].add(str(raw_case.get("case_id") or ""))
        activity_at = str(
            ai_draft.get("completed_at")
            or ai_draft.get("updated_at")
            or ai_draft.get("created_at")
            or ""
        )
        lineage["latest_activity_at"] = max(lineage["latest_activity_at"], activity_at)
        for raw_proposal in proposals:
            if not isinstance(raw_proposal, Mapping):
                continue
            proposal = dict(raw_proposal)
            proposal_decision = proposal.get("decision")
            proposal_decision = (
                proposal_decision if isinstance(proposal_decision, Mapping) else None
            )
            current_decision = (
                str(proposal_decision.get("decision") or "undecided")
                if proposal_decision
                else "undecided"
            )
            is_eligible = bool(proposal.get("eligible"))
            listing_role = str(proposal.get("listing_role") or "")
            listing = raw_case.get(f"{listing_role}_listing")
            listing = listing if isinstance(listing, Mapping) else {}
            counterpart_role = "competitor" if listing_role == "benchmark" else "benchmark"
            counterpart = raw_case.get(f"{counterpart_role}_listing")
            counterpart = counterpart if isinstance(counterpart, Mapping) else {}
            lineage["proposal_count"] += 1
            lineage["eligible_proposal_count" if is_eligible else "ineligible_proposal_count"] += 1
            lineage[f"{current_decision}_proposal_count"] += 1
            rows.append(
                {
                    **proposal,
                    "case_id": str(raw_case.get("case_id") or ""),
                    "case_review_status": str(raw_case.get("review_status") or "pending"),
                    "competitor_retailer_id": str(
                        raw_case.get("competitor_retailer_id")
                        or (raw_case.get("competitor_listing") or {}).get("retailer_id")
                        or ""
                    ),
                    "listing": {
                        "listing_id": str(listing.get("listing_id") or ""),
                        "retailer_id": str(listing.get("retailer_id") or ""),
                        "retailer_product_id": str(listing.get("retailer_product_id") or ""),
                        "title": listing.get("title"),
                        "brand": listing.get("brand"),
                        "image_url": listing.get("image_url"),
                        "product_url": listing.get("product_url"),
                        "observed_location_count": int(listing.get("observed_location_count") or 0),
                    },
                    "counterpart": {
                        "listing_id": str(counterpart.get("listing_id") or ""),
                        "retailer_id": str(counterpart.get("retailer_id") or ""),
                        "retailer_product_id": str(counterpart.get("retailer_product_id") or ""),
                        "title": counterpart.get("title"),
                        "brand": counterpart.get("brand"),
                        "image_url": counterpart.get("image_url"),
                    },
                    "decision_status": current_decision,
                    "ai_draft": {
                        "id": str(ai_draft.get("id") or ""),
                        "batch_id": batch_id,
                        "root_batch_id": lineage_id,
                        "model_id": str(ai_draft.get("model_id") or ""),
                        "completed_at": ai_draft.get("completed_at"),
                    },
                }
            )

    rendered_lineages = []
    for lineage in lineages.values():
        case_ids = lineage["case_ids"]
        rendered_lineages.append(
            {
                **{key: value for key, value in lineage.items() if key != "case_ids"},
                "batch_ids": sorted(lineage["batch_ids"]),
                "model_ids": sorted(lineage["model_ids"]),
                "case_count": len(case_ids),
            }
        )
    rendered_lineages.sort(
        key=lambda row: (str(row["latest_activity_at"]), str(row["root_batch_id"])),
        reverse=True,
    )
    selected_root_batch_id = root_batch_id
    if selected_root_batch_id is None and batch_scope == "latest_lineage":
        selected_root_batch_id = (
            str(rendered_lineages[0]["root_batch_id"]) if rendered_lineages else None
        )
    if selected_root_batch_id is not None and selected_root_batch_id not in lineages:
        raise KeyError(f"attribute-evidence batch lineage {selected_root_batch_id!r} was not found")
    if selected_root_batch_id is not None:
        rows = [row for row in rows if row["ai_draft"]["root_batch_id"] == selected_root_batch_id]

    summary_rows = list(rows)
    relationship_counts = {
        relationship: sum(
            str(row.get("evidence_relationship") or "invalid") == relationship
            for row in summary_rows
        )
        for relationship in (
            "fills_unknown",
            "corroborates_existing",
            "refines_existing",
            "conflicts_with_existing",
            "invalid",
        )
    }
    summary = {
        "proposal_count": len(summary_rows),
        "distinct_claim_count": len(
            {
                (str(row.get("listing_id") or ""), str(row.get("attribute") or ""))
                for row in summary_rows
            }
        ),
        "eligible_proposal_count": sum(bool(row.get("eligible")) for row in summary_rows),
        "ineligible_proposal_count": sum(not bool(row.get("eligible")) for row in summary_rows),
        "undecided_proposal_count": sum(
            row["decision_status"] == "undecided" for row in summary_rows
        ),
        "verified_proposal_count": sum(
            row["decision_status"] == "verified" for row in summary_rows
        ),
        "rejected_proposal_count": sum(
            row["decision_status"] == "rejected" for row in summary_rows
        ),
        "relationship_counts": relationship_counts,
    }
    if eligibility == "eligible":
        rows = [row for row in rows if row.get("eligible")]
    elif eligibility == "ineligible":
        rows = [row for row in rows if not row.get("eligible")]
    if decision_status != "all":
        rows = [row for row in rows if row["decision_status"] == decision_status]
    rows.sort(
        key=lambda row: (
            row["decision_status"] != "undecided",
            -float(row.get("confidence") or 0),
            str(row["listing"].get("retailer_id") or ""),
            str(row.get("attribute") or ""),
            str(row.get("proposal_checksum") or ""),
        )
    )
    return {
        "schema_version": "1.0.0-attribute-evidence-index",
        "authoritative": False,
        "human_verification_required": True,
        "queue": dict(queue),
        "batch_scope": batch_scope,
        "selected_root_batch_id": selected_root_batch_id,
        "batch_lineages": rendered_lineages,
        "filters": {
            "eligibility": eligibility,
            "decision_status": decision_status,
        },
        "summary": summary,
        "selected_proposal_count": len(rows),
        "offset": offset,
        "limit": limit,
        "proposals": rows[offset : offset + limit],
    }


def _attribute_evidence_claim_index(
    queue_view: Mapping[str, Any],
    *,
    batch_scope: AttributeEvidenceBatchScope,
    root_batch_id: str | None,
    status_filter: AttributeEvidenceClaimStatus,
    attribute_filter: str | None,
    offset: int,
    limit: int,
) -> dict[str, Any]:
    """Collapse pair-level AI proposals into one governed product-attribute claim.

    Repeated proposals from different comparison pairs are context, not independent proof. The
    claim checksum binds the complete current proposal population so an administrator cannot act
    on a stale or partially loaded claim. Existing source-bound decisions remain immutable.
    """

    proposal_view = _attribute_evidence_proposal_index(
        queue_view,
        batch_scope=batch_scope,
        root_batch_id=root_batch_id,
        eligibility="all",
        decision_status="all",
        offset=0,
        limit=100_000,
    )
    queue = proposal_view.get("queue")
    queue = queue if isinstance(queue, Mapping) else {}
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for raw in proposal_view.get("proposals") or []:
        if not isinstance(raw, Mapping) or not raw.get("eligible"):
            continue
        listing_id = str(raw.get("listing_id") or "")
        attribute = str(raw.get("attribute") or "")
        if listing_id and attribute:
            grouped[(listing_id, attribute)].append(dict(raw))

    claims: list[dict[str, Any]] = []
    attribute_counts: dict[str, int] = defaultdict(int)
    for (listing_id, attribute), proposal_rows in grouped.items():
        proposal_checksums = sorted(
            {str(row.get("proposal_checksum") or "") for row in proposal_rows}
        )
        claim_descriptor = {
            "schema_version": "1.0.0-product-attribute-claim",
            "queue_id": str(queue.get("queue_id") or ""),
            "queue_version": str(queue.get("version") or ""),
            "batch_scope": batch_scope,
            "selected_root_batch_id": proposal_view.get("selected_root_batch_id"),
            "listing_id": listing_id,
            "attribute": attribute,
            "proposal_checksums": proposal_checksums,
        }
        claim_checksum = _checksum(claim_descriptor)
        variants_by_value: dict[str, list[dict[str, Any]]] = defaultdict(list)
        current_evidence: dict[str, dict[str, Any]] = {}
        counterpart_products: dict[str, dict[str, Any]] = {}
        for row in proposal_rows:
            variants_by_value[_canonical(row.get("normalized_value"))].append(row)
            current_key = _canonical(
                {"value": row.get("current_value"), "source": row.get("current_source")}
            )
            current_evidence[current_key] = {
                "value": row.get("current_value"),
                "source": row.get("current_source"),
            }
            counterpart = row.get("counterpart")
            if isinstance(counterpart, Mapping):
                counterpart_id = str(counterpart.get("listing_id") or "")
                if counterpart_id:
                    counterpart_products[counterpart_id] = dict(counterpart)

        variants: list[dict[str, Any]] = []
        verified_values: set[str] = set()
        claim_rejected = False
        claim_decision: Mapping[str, Any] | None = None
        for value_key, variant_rows in variants_by_value.items():
            ordered = sorted(
                variant_rows,
                key=lambda row: (
                    -float(row.get("confidence") or 0),
                    str(row.get("proposal_checksum") or ""),
                ),
            )
            citations: dict[tuple[str, str], dict[str, Any]] = {}
            for row in ordered:
                citation_key = (
                    str(row.get("source_image_url") or ""),
                    str(row.get("visible_text") or ""),
                )
                citations[citation_key] = {
                    "source_image_url": row.get("source_image_url"),
                    "visible_text": row.get("visible_text"),
                    "confidence": float(row.get("confidence") or 0),
                    "case_id": str(row.get("case_id") or ""),
                    "proposal_checksum": str(row.get("proposal_checksum") or ""),
                    "counterpart_retailer_id": str(row.get("competitor_retailer_id") or ""),
                }
                decision = row.get("decision")
                if not isinstance(decision, Mapping):
                    continue
                if decision.get("decision") == "verified":
                    verified_values.add(value_key)
                    claim_decision = decision
                proposal_document = decision.get("proposal_document")
                stored_claim = (
                    proposal_document.get("claim_decision")
                    if isinstance(proposal_document, Mapping)
                    else None
                )
                if (
                    decision.get("decision") == "rejected"
                    and isinstance(stored_claim, Mapping)
                    and stored_claim.get("claim_checksum") == claim_checksum
                ):
                    claim_rejected = True
                    claim_decision = decision
            variants.append(
                {
                    "value": ordered[0].get("normalized_value"),
                    "value_checksum": _checksum(
                        {
                            "claim_checksum": claim_checksum,
                            "normalized_value": ordered[0].get("normalized_value"),
                        }
                    ),
                    "proposal_count": len(ordered),
                    "case_count": len({str(row.get("case_id") or "") for row in ordered}),
                    "minimum_confidence": min(float(row.get("confidence") or 0) for row in ordered),
                    "maximum_confidence": max(float(row.get("confidence") or 0) for row in ordered),
                    "evidence_relationships": sorted(
                        {str(row.get("evidence_relationship") or "invalid") for row in ordered}
                    ),
                    "representative_case_id": str(ordered[0].get("case_id") or ""),
                    "representative_proposal_checksum": str(
                        ordered[0].get("proposal_checksum") or ""
                    ),
                    "citations": sorted(
                        citations.values(),
                        key=lambda citation: (
                            -float(citation["confidence"]),
                            str(citation["source_image_url"] or ""),
                        ),
                    ),
                }
            )

        if len(verified_values) > 1:
            claim_status: AttributeEvidenceClaimStatus = "conflict"
            status_reason = (
                "Multiple human-verified values conflict; certification remains blocked."
            )
        elif len(verified_values) == 1:
            claim_status = "verified"
            status_reason = "One human-verified value governs this product attribute."
        elif claim_rejected:
            claim_status = "rejected"
            status_reason = "The complete current product-attribute claim was rejected."
        elif len(variants) > 1:
            claim_status = "conflict"
            status_reason = (
                "AI evidence proposes multiple values; an administrator must select one."
            )
        else:
            claim_status = "awaiting_review"
            status_reason = "A source-attributable product claim awaits administrator review."

        variants.sort(
            key=lambda variant: (
                -int(variant["case_count"]),
                -float(variant["maximum_confidence"]),
                str(variant["value_checksum"]),
            )
        )
        listing = proposal_rows[0].get("listing")
        listing = dict(listing) if isinstance(listing, Mapping) else {}
        attribute_counts[attribute] += 1
        claims.append(
            {
                **claim_descriptor,
                "claim_checksum": claim_checksum,
                "status": claim_status,
                "status_reason": status_reason,
                "listing": listing,
                "current_evidence": sorted(
                    current_evidence.values(),
                    key=lambda evidence: _canonical(evidence),
                ),
                "proposal_count": len(proposal_rows),
                "affected_case_count": len(
                    {str(row.get("case_id") or "") for row in proposal_rows}
                ),
                "counterpart_product_count": len(counterpart_products),
                "counterpart_retailers": sorted(
                    {
                        str(product.get("retailer_id") or "")
                        for product in counterpart_products.values()
                        if product.get("retailer_id")
                    }
                ),
                "variants": variants,
                "decision": dict(claim_decision) if claim_decision else None,
                "raw_evidence_mutated": False,
            }
        )

    summary_claims = list(claims)
    summary = {
        "claim_count": len(summary_claims),
        "proposal_count": sum(int(claim["proposal_count"]) for claim in summary_claims),
        "awaiting_review_count": sum(
            claim["status"] == "awaiting_review" for claim in summary_claims
        ),
        "conflict_count": sum(claim["status"] == "conflict" for claim in summary_claims),
        "verified_count": sum(claim["status"] == "verified" for claim in summary_claims),
        "rejected_count": sum(claim["status"] == "rejected" for claim in summary_claims),
        "affected_product_count": len({str(claim["listing_id"]) for claim in summary_claims}),
    }
    if attribute_filter:
        claims = [claim for claim in claims if claim["attribute"] == attribute_filter]
    if status_filter != "all":
        claims = [claim for claim in claims if claim["status"] == status_filter]
    status_order = {"conflict": 0, "awaiting_review": 1, "verified": 2, "rejected": 3}
    claims.sort(
        key=lambda claim: (
            status_order[str(claim["status"])],
            -int(claim["listing"].get("observed_location_count") or 0),
            str(claim["listing"].get("retailer_id") or ""),
            str(claim["attribute"]),
            str(claim["listing_id"]),
        )
    )
    return {
        "schema_version": "1.0.0-product-attribute-claim-index",
        "authoritative": False,
        "human_verification_required": True,
        "raw_evidence_mutated": False,
        "queue": dict(queue),
        "batch_scope": batch_scope,
        "selected_root_batch_id": proposal_view.get("selected_root_batch_id"),
        "batch_lineages": proposal_view.get("batch_lineages") or [],
        "filters": {"status": status_filter, "attribute": attribute_filter},
        "summary": summary,
        "attributes": [
            {"attribute": name, "claim_count": count}
            for name, count in sorted(attribute_counts.items())
        ],
        "selected_claim_count": len(claims),
        "offset": offset,
        "limit": limit,
        "claims": claims[offset : offset + limit],
    }


def _certification_evidence_refs(
    document: Mapping[str, Any], submitted_refs: Sequence[str]
) -> list[str]:
    checksum = str(document.get("certification_view_checksum") or "")
    case_id = str(document.get("case_id") or "unknown")
    view_reference = (
        f"matching-v2-certification-view://{case_id}#sha256={checksum}"
        if len(checksum) == 64
        else None
    )
    return list(
        dict.fromkeys(
            [
                *(str(value) for value in document.get("evidence_refs") or []),
                *(str(value) for value in submitted_refs),
                *([view_reference] if view_reference else []),
            ]
        )
    )


def _disallowed_certification_tiers(tiers: Sequence[str], case: Mapping[str, Any]) -> list[str]:
    allowed = case.get("certification_allowed_tiers")
    allowed = allowed if isinstance(allowed, list) else list(_ALL_MATCH_TIERS)
    return sorted({str(tier) for tier in tiers if str(tier) not in allowed})


class ImportReviewQueueRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    organization_id: str = Field(min_length=1)
    imported_by: str = Field(min_length=1, max_length=200)
    queue: dict[str, Any] | None = None
    queue_json: str | None = Field(default=None, min_length=2)
    successor_of_version: str | None = Field(default=None, min_length=1, max_length=50)
    carry_forward_certified: bool = False
    carry_forward_attribute_evidence: bool = False
    scope_only_pack_revision: bool = False

    @model_validator(mode="after")
    def validate_successor_options(self) -> ImportReviewQueueRequest:
        if self.carry_forward_certified and self.successor_of_version is None:
            raise ValueError("carry_forward_certified requires an explicit successor_of_version")
        if self.carry_forward_attribute_evidence and self.successor_of_version is None:
            raise ValueError(
                "carry_forward_attribute_evidence requires an explicit successor_of_version"
            )
        if self.scope_only_pack_revision and not self.carry_forward_certified:
            raise ValueError("scope_only_pack_revision requires carry_forward_certified")
        return self


class ReviewSubmissionRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    reviewer_id: str = Field(min_length=1, max_length=200)
    verdict: ReviewVerdict
    allowed_tiers: list[MatchTier] = Field(default_factory=list)
    rationale: str = Field(min_length=1, max_length=10_000)
    evidence_refs: list[str] = Field(min_length=1)
    supersedes_submission_id: str | None = None


class AttributeEvidenceDecisionRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    reviewer_id: str = Field(min_length=1, max_length=200)
    proposal_checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    decision: Literal["verified", "rejected"]
    rationale: str = Field(min_length=1, max_length=2_000)
    supersedes_decision_id: str | None = None


class AttributeEvidenceClaimDecisionRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    reviewer_id: str = Field(min_length=1, max_length=200)
    claim_checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    decision: Literal["verified", "rejected"]
    rationale: str = Field(min_length=1, max_length=2_000)
    selected_proposal_checksum: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    batch_scope: AttributeEvidenceBatchScope = "all_lineages"
    root_batch_id: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_claim_scope(self) -> AttributeEvidenceClaimDecisionRequest:
        if self.batch_scope == "latest_lineage" and self.root_batch_id is None:
            return self
        if self.batch_scope == "all_lineages" and self.root_batch_id is not None:
            raise ValueError("root_batch_id requires latest_lineage scope")
        return self


class AdjudicationRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    adjudicator_id: str = Field(min_length=1, max_length=200)
    verdict: ReviewVerdict
    allowed_tiers: list[MatchTier] = Field(default_factory=list)
    rationale: str = Field(min_length=1, max_length=10_000)
    evidence_refs: list[str] = Field(min_length=1)
    submission_ids: list[str] = Field(min_length=2)
    supersedes_adjudication_id: str | None = None


class AIReviewDraftRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    requested_by: str = Field(min_length=1, max_length=200)


class AIReviewBatchRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    requested_by: str = Field(min_length=1, max_length=200)
    case_ids: list[str] = Field(
        min_length=1,
        max_length=_MAX_AI_REVIEW_BATCH_CASES,
    )


class AIReviewRetryRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    requested_by: str = Field(min_length=1, max_length=200)
    case_ids: list[str] = Field(min_length=1, max_length=25)
    retry_reason: str = Field(min_length=1, max_length=1_000)


class AIBulkCertificationPreviewRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    case_ids: list[str] = Field(min_length=1, max_length=500)


class AIBulkCertificationCommitRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    reviewer_id: str = Field(min_length=1, max_length=200)
    case_ids: list[str] = Field(min_length=1, max_length=50)
    confirmation_checksum: str = Field(pattern=r"^[a-f0-9]{64}$")


class GoldSetReplayRequest(BaseModel):
    """Explicitly bind a certified snapshot to a governed analysis replay."""

    model_config = ConfigDict(str_strip_whitespace=True)

    source_analysis_id: str = Field(min_length=1, max_length=300)
    released_by: str = Field(min_length=1, max_length=200)
    force_rebuild: bool = False
    rebuild_reason: str | None = Field(default=None, min_length=1, max_length=1_000)

    @model_validator(mode="after")
    def require_rebuild_reason(self) -> GoldSetReplayRequest:
        if self.force_rebuild and not self.rebuild_reason:
            raise ValueError("a forced governed rebuild requires a rebuild reason")
        if not self.force_rebuild and self.rebuild_reason:
            raise ValueError("a rebuild reason is valid only for a forced governed rebuild")
        return self


_AI_BULK_CERTIFICATION_POLICY: dict[str, Any] = {
    "id": "guarded_ai_recommendation_bulk_certification",
    "version": "1.7.0",
    "max_cases": 50,
    "max_candidates_assessed": 500,
    "action": "certify_ai_recommendations",
    "allowed_verdicts": ["comparable", "not_comparable"],
    "allowed_tiers": [
        "exact_item",
        "exact_specification",
        "equivalent_product",
        "comparable_substitute",
        "custom_approved",
    ],
    "minimum_critical_coverage": 1.0,
    "minimum_ai_attribute_confidence": 0.85,
    "require_ai_engine_tier_agreement": True,
    "require_zero_ai_conflicts": False,
    "require_no_hard_blocker_conflicts": True,
    "require_known_hard_blocker_conflict_for_not_comparable": True,
    "warn_on_ai_engine_tier_disagreement": False,
    "warn_on_ai_conflicts": True,
    "warn_on_hard_blocker_conflicts": True,
    "require_no_known_third_party_seller": True,
    "advisory_warnings_do_not_block_human_confirmation": True,
    "final_decision": "final_until_flagged",
}


_AI_BULK_WARNING_CODES = {
    "ai_engine_verdict_disagreement",
    "critical_evidence_incomplete",
    "ai_conflict_present",
    "low_confidence_ai_attribute",
}


_AI_BULK_REASON_LABELS = {
    "final_decision_exists": "A final human decision already exists.",
    "ai_draft_not_ready": "The latest AI draft is not successfully completed.",
    "ai_draft_invalid": "The completed AI draft does not contain valid governed output.",
    "ai_verdict_not_certifiable": (
        "The AI recommendation is insufficient evidence and cannot become a final bulk decision."
    ),
    "tier_not_bulk_eligible": "The comparable recommendation has no supported match tier.",
    "tier_disallowed_by_product_pack": (
        "The active Product Pack does not permit this relationship tier."
    ),
    "not_comparable_tier_present": (
        "A not-comparable recommendation cannot also carry a match tier."
    ),
    "comparison_basis_missing": (
        "A comparable recommendation must name package price, normalized unit price, or both."
    ),
    "comparison_basis_not_eligible": (
        "The proposed price basis is not supported by the deterministic package evidence."
    ),
    "non_comparable_basis_present": (
        "A non-comparable recommendation cannot carry a price-comparison basis."
    ),
    "engine_tier_missing": "The deterministic engine did not propose a match tier.",
    "ai_engine_tier_disagreement": "The AI and deterministic engine propose different tiers.",
    "ai_engine_verdict_disagreement": (
        "The AI recommends not comparable while the deterministic engine proposes a match."
    ),
    "engine_proposal_blocked": "The deterministic engine marked the pair ineligible or rejected.",
    "critical_evidence_incomplete": "Critical deterministic evidence is incomplete.",
    "ai_conflict_present": "The AI draft identifies one or more unresolved conflicts.",
    "hard_blocker_conflict": (
        "A current Product Pack hard-blocker attribute conflicts or has blocking unknown evidence."
    ),
    "not_comparable_conflict_unverified": (
        "A bulk not-comparable decision requires a known deterministic Product Pack "
        "hard-blocker conflict; AI-only or internally contradictory evidence requires "
        "individual review."
    ),
    "low_confidence_ai_attribute": "An AI-proposed attribute is below the bulk confidence floor.",
    "known_third_party_seller": (
        "A known third-party marketplace seller makes the listing ineligible."
    ),
    "certification_view_invalid": (
        "The checksum-bound deterministic certification view is missing or invalid."
    ),
    "certification_recomputation_blocked": (
        "The deterministic certification view could not be recomputed from governed evidence."
    ),
    "attribute_reconciliation_conflict": (
        "Verified attribute evidence conflicts and requires individual resolution."
    ),
    "evidence_refs_missing": "The case has no immutable source-evidence references.",
    "bulk_batch_limit": (
        "The relationship passed the required gates but is deferred to the next 50-case "
        "confirmation batch."
    ),
}


def _known_third_party_seller(listing: Mapping[str, Any]) -> bool:
    governance = listing.get("seller_governance")
    if not isinstance(governance, Mapping):
        return False
    if governance.get("eligible") is False:
        return True
    status_value = (
        str(governance.get("status") or governance.get("eligibility") or "").strip().lower()
    )
    if not status_value:
        return False
    if "first_party" in status_value or "first-party" in status_value:
        return False
    return any(token in status_value for token in ("third_party", "third-party", "excluded"))


def _case_has_known_third_party_seller(case: Mapping[str, Any]) -> bool:
    return any(
        _known_third_party_seller(listing)
        for listing in (
            case.get("benchmark_listing"),
            case.get("competitor_listing"),
        )
        if isinstance(listing, Mapping)
    )


def _deterministic_comparison_bases(case: Mapping[str, Any]) -> list[str]:
    """Translate engine-owned price bases; product compatibility is decided elsewhere."""

    edge = case.get("edge")
    edge = edge if isinstance(edge, Mapping) else {}
    eligible = edge.get("eligible_price_bases")
    eligible = set(str(value) for value in eligible) if isinstance(eligible, list) else set()
    result: list[str] = []
    if "exact_package" in eligible:
        result.append("package_price")
    if "normalized_unit" in eligible:
        result.append("normalized_unit_price")
    return result


def _bulk_ai_certification_eligibility(case: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate a case under deterministic, server-owned bulk-certification guardrails."""

    reason_codes: list[str] = []
    if case.get("review_status") != "pending":
        reason_codes.append("final_decision_exists")
    certification_view_checksum = str(case.get("certification_view_checksum") or "")
    if len(certification_view_checksum) != 64:
        reason_codes.append("certification_view_invalid")
    recomputation = case.get("certification_engine_recomputation")
    recomputation = recomputation if isinstance(recomputation, Mapping) else {}
    if recomputation.get("status") != "succeeded":
        reason_codes.append("certification_recomputation_blocked")
    reconciliation = case.get("attribute_evidence_reconciliation")
    reconciliation = reconciliation if isinstance(reconciliation, Mapping) else {}
    reconciliation_conflicts = reconciliation.get("conflicts")
    if isinstance(reconciliation_conflicts, list) and reconciliation_conflicts:
        reason_codes.append("attribute_reconciliation_conflict")

    ai_draft = case.get("ai_draft")
    if not isinstance(ai_draft, Mapping) or ai_draft.get("status") != "succeeded":
        reason_codes.append("ai_draft_not_ready")
        result: Mapping[str, Any] = {}
    else:
        output = ai_draft.get("output_document")
        candidate_result = output.get("result") if isinstance(output, Mapping) else None
        output_checksum = str(case.get("ai_output_checksum") or "")
        if (
            not isinstance(output, Mapping)
            or output.get("authoritative") is not False
            or output.get("human_review_required") is not True
            or not isinstance(candidate_result, Mapping)
            or candidate_result.get("requires_human_review") is not True
            or len(output_checksum) != 64
        ):
            reason_codes.append("ai_draft_invalid")
            result = {}
        else:
            result = candidate_result

    verdict = str(result.get("verdict_proposal") or "")
    ai_tier = str(result.get("tier_proposal") or "")
    proposed_comparison_bases = result.get("comparison_basis_proposal", [])
    proposed_comparison_bases = (
        [str(value) for value in proposed_comparison_bases]
        if isinstance(proposed_comparison_bases, list)
        else []
    )
    eligible_comparison_bases = _deterministic_comparison_bases(case)
    if result and verdict not in _AI_BULK_CERTIFICATION_POLICY["allowed_verdicts"]:
        reason_codes.append("ai_verdict_not_certifiable")
    if result and verdict == "comparable":
        if ai_tier not in _AI_BULK_CERTIFICATION_POLICY["allowed_tiers"]:
            reason_codes.append("tier_not_bulk_eligible")
        active_allowed_tiers = case.get("certification_allowed_tiers")
        if (
            isinstance(active_allowed_tiers, list)
            and ai_tier
            and ai_tier not in active_allowed_tiers
        ):
            reason_codes.append("tier_disallowed_by_product_pack")
        if not proposed_comparison_bases:
            reason_codes.append("comparison_basis_missing")
        elif any(basis not in eligible_comparison_bases for basis in proposed_comparison_bases):
            reason_codes.append("comparison_basis_not_eligible")
    elif result and verdict == "not_comparable" and ai_tier:
        reason_codes.append("not_comparable_tier_present")
    if result and verdict != "comparable" and proposed_comparison_bases:
        reason_codes.append("non_comparable_basis_present")

    engine = case.get("engine_proposal")
    engine = engine if isinstance(engine, Mapping) else {}
    engine_tier = str(engine.get("tier") or "")
    engine_status = str(engine.get("status") or "").lower()
    engine_rejects = any(token in engine_status for token in ("reject", "block", "ineligible"))
    if verdict == "comparable":
        if not engine_tier:
            reason_codes.append("engine_tier_missing")
        elif ai_tier and ai_tier != engine_tier:
            reason_codes.append("ai_engine_tier_disagreement")
        if engine_rejects:
            reason_codes.append("engine_proposal_blocked")
    elif verdict == "not_comparable" and engine_tier and not engine_rejects:
        reason_codes.append("ai_engine_verdict_disagreement")

    coverage = engine.get("evidence_coverage")
    coverage = coverage if isinstance(coverage, Mapping) else {}
    try:
        critical_coverage = float(coverage.get("critical_coverage", 0))
    except (TypeError, ValueError):
        critical_coverage = 0.0
    if critical_coverage < _AI_BULK_CERTIFICATION_POLICY["minimum_critical_coverage"]:
        reason_codes.append("critical_evidence_incomplete")

    conflicts = result.get("conflicts", []) if result else []
    if isinstance(conflicts, list) and conflicts:
        reason_codes.append("ai_conflict_present")

    hard_blocker_attributes = case.get("certification_hard_blocker_attributes")
    if not isinstance(hard_blocker_attributes, list):
        edge = case.get("edge")
        edge = edge if isinstance(edge, Mapping) else {}
        attribute_evidence = edge.get("attribute_evidence", [])
        hard_blocker_attributes = [
            str(evidence.get("attribute"))
            for evidence in attribute_evidence
            if isinstance(evidence, Mapping)
            and str(evidence.get("role") or "") == "hard_blocker"
            and evidence.get("attribute")
        ]
    unknown_nonblocking_attributes = case.get("certification_unknown_nonblocking_attributes")
    unknown_nonblocking_attributes = (
        unknown_nonblocking_attributes if isinstance(unknown_nonblocking_attributes, list) else []
    )
    hard_blocker_issues = _hard_blocker_issues(
        case, hard_blocker_attributes, unknown_nonblocking_attributes
    )
    if verdict == "comparable" and hard_blocker_issues:
        reason_codes.append("hard_blocker_conflict")
    if verdict == "not_comparable" and not any(
        str(issue.get("outcome") or "").lower() == "conflict"
        for issue in hard_blocker_issues
        if isinstance(issue, Mapping)
    ):
        reason_codes.append("not_comparable_conflict_unverified")

    attribute_proposals = result.get("attribute_proposals", []) if result else []
    if isinstance(attribute_proposals, list):
        for proposal in attribute_proposals:
            if not isinstance(proposal, Mapping):
                reason_codes.append("low_confidence_ai_attribute")
                break
            try:
                confidence = float(proposal.get("confidence", 0))
            except (TypeError, ValueError):
                confidence = 0.0
            if confidence < _AI_BULK_CERTIFICATION_POLICY["minimum_ai_attribute_confidence"]:
                reason_codes.append("low_confidence_ai_attribute")
                break

    if any(
        _known_third_party_seller(listing)
        for listing in (
            case.get("benchmark_listing"),
            case.get("competitor_listing"),
        )
        if isinstance(listing, Mapping)
    ):
        reason_codes.append("known_third_party_seller")
    if not case.get("evidence_refs"):
        reason_codes.append("evidence_refs_missing")

    reason_codes = list(dict.fromkeys(reason_codes))
    warning_codes = [code for code in reason_codes if code in _AI_BULK_WARNING_CODES]
    blocking_reason_codes = [code for code in reason_codes if code not in _AI_BULK_WARNING_CODES]
    return {
        "case_id": str(case.get("case_id") or ""),
        "eligible": not blocking_reason_codes,
        "reason_codes": blocking_reason_codes,
        "reasons": [_AI_BULK_REASON_LABELS[code] for code in blocking_reason_codes],
        "warning_codes": warning_codes,
        "warnings": [_AI_BULK_REASON_LABELS[code] for code in warning_codes],
        "recommended_verdict": verdict or None,
        "recommended_tier": ai_tier or None,
        "recommended_comparison_bases": proposed_comparison_bases,
        "eligible_comparison_bases": eligible_comparison_bases,
        "critical_coverage": critical_coverage,
        "engine_status": engine_status or None,
        "ai_task_id": (str(ai_draft.get("id")) if isinstance(ai_draft, Mapping) else None),
        "ai_rationale": str(result.get("rationale") or "") or None,
        "hard_blocker_issues": hard_blocker_issues,
        "certification_view_checksum": certification_view_checksum,
        "benchmark_product": _bulk_product_summary(case.get("benchmark_listing")),
        "competitor_product": _bulk_product_summary(case.get("competitor_listing")),
    }


def _bulk_product_summary(value: Any) -> dict[str, Any]:
    listing = value if isinstance(value, Mapping) else {}
    return {
        "retailer_id": listing.get("retailer_id"),
        "retailer_product_id": listing.get("retailer_product_id"),
        "title": listing.get("title"),
        "brand": listing.get("brand"),
        "image_url": listing.get("image_url"),
        "observed_location_count": _observed_location_count({"listing": listing}, "listing"),
    }


def _ai_bulk_certification_policy() -> dict[str, Any]:
    return {
        **_AI_BULK_CERTIFICATION_POLICY,
        "checksum": _checksum(_AI_BULK_CERTIFICATION_POLICY),
        "human_confirmation_required": True,
        "automatically_changes_reporting": False,
    }


def _bulk_confirmation_checksum(
    *,
    queue_id: str,
    queue_version: str,
    candidates: Sequence[Mapping[str, Any]],
) -> str:
    policy = _ai_bulk_certification_policy()
    return _checksum(
        {
            "queue_id": queue_id,
            "queue_version": queue_version,
            "policy_checksum": policy["checksum"],
            "cases": [
                {
                    "case_id": candidate["case_id"],
                    "case_checksum": candidate["case_checksum"],
                    "certification_view_checksum": candidate["certification_view_checksum"],
                    "ai_task_id": candidate["ai_task_id"],
                    "ai_output_checksum": candidate["ai_output_checksum"],
                    "recommended_verdict": candidate["recommended_verdict"],
                    "recommended_tier": candidate["recommended_tier"],
                    "recommended_comparison_bases": candidate["recommended_comparison_bases"],
                }
                for candidate in sorted(candidates, key=lambda row: str(row["case_id"]))
            ],
        }
    )


def _bulk_preview_document(
    *,
    queue_id: str,
    queue_version: str,
    snapshots: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    evaluated: list[dict[str, Any]] = []
    for snapshot in snapshots:
        candidate = _bulk_ai_certification_eligibility(snapshot)
        candidate["case_checksum"] = str(snapshot.get("case_checksum") or "")
        candidate["ai_output_checksum"] = str(snapshot.get("ai_output_checksum") or "")
        evaluated.append(candidate)
    eligible_candidates = [candidate for candidate in evaluated if candidate["eligible"]]
    maximum_cases = int(_AI_BULK_CERTIFICATION_POLICY["max_cases"])
    eligible = eligible_candidates[:maximum_cases]
    for candidate in eligible_candidates[maximum_cases:]:
        candidate["eligible"] = False
        candidate["reason_codes"].append("bulk_batch_limit")
        candidate["reasons"].append(_AI_BULK_REASON_LABELS["bulk_batch_limit"])
    excluded = [candidate for candidate in evaluated if not candidate["eligible"]]
    reason_counts: dict[str, int] = defaultdict(int)
    for candidate in excluded:
        for reason_code in candidate["reason_codes"]:
            reason_counts[reason_code] += 1
    warning_counts: dict[str, int] = defaultdict(int)
    for candidate in eligible:
        for warning_code in candidate["warning_codes"]:
            warning_counts[warning_code] += 1
    return {
        "schema_version": "1.0.0-ai-bulk-certification-preview",
        "queue_id": queue_id,
        "queue_version": queue_version,
        "policy": _ai_bulk_certification_policy(),
        "requested_case_count": len(evaluated),
        "eligible_case_count": len(eligible),
        "excluded_case_count": len(excluded),
        "eligible_cases": eligible,
        "excluded_cases": excluded,
        "exclusion_summary": [
            {
                "reason_code": reason_code,
                "reason": _AI_BULK_REASON_LABELS[reason_code],
                "case_count": count,
            }
            for reason_code, count in sorted(reason_counts.items())
        ],
        "warning_summary": [
            {
                "warning_code": warning_code,
                "warning": _AI_BULK_REASON_LABELS[warning_code],
                "case_count": count,
            }
            for warning_code, count in sorted(warning_counts.items())
        ],
        "confirmation_checksum": (
            _bulk_confirmation_checksum(
                queue_id=queue_id,
                queue_version=queue_version,
                candidates=eligible,
            )
            if eligible
            else None
        ),
        "human_confirmation_required": True,
        "final_until_flagged": True,
        "automatically_changes_reporting": False,
    }


class MatchingV2ReviewRepository(Protocol):
    async def list_queues(self, *, limit: int) -> list[dict[str, Any]]: ...

    async def import_queue(
        self,
        organization_id: str,
        queue: Mapping[str, Any],
        *,
        imported_by: str,
        successor_of_version: str | None = None,
        carry_forward_certified: bool = False,
        carry_forward_attribute_evidence: bool = False,
        scope_only_pack_revision: bool = False,
    ) -> dict[str, Any]: ...

    async def queue_view(
        self,
        external_queue_id: str,
        *,
        competitor_retailer_id: str | None,
        benchmark_product_id: str | None,
        competitor_product_id: str | None,
        stratum: str | None,
        review_status: str | None,
        offset: int,
        limit: int,
    ) -> dict[str, Any]: ...

    async def submit_review(
        self,
        external_queue_id: str,
        external_case_id: str,
        submission: Mapping[str, Any],
        *,
        submission_checksum: str,
    ) -> dict[str, Any]: ...

    async def decide_attribute_evidence(
        self,
        external_queue_id: str,
        external_case_id: str,
        decision: Mapping[str, Any],
        *,
        decision_checksum: str,
    ) -> dict[str, Any]: ...

    async def adjudicate(
        self,
        external_queue_id: str,
        external_case_id: str,
        adjudication: Mapping[str, Any],
        *,
        adjudication_checksum: str,
    ) -> dict[str, Any]: ...

    async def request_ai_draft(
        self,
        external_queue_id: str,
        external_case_id: str,
        *,
        requested_by: str,
        model_id: str,
        prompt: Mapping[str, str],
    ) -> dict[str, Any]: ...

    async def request_ai_drafts(
        self,
        external_queue_id: str,
        external_case_ids: Sequence[str],
        *,
        requested_by: str,
        model_id: str,
        prompt: Mapping[str, str],
    ) -> list[dict[str, Any]]: ...

    async def eligible_ai_review_cases(
        self,
        external_queue_id: str,
        *,
        competitor_retailer_id: str | None,
        selection_mode: AIReviewSelectionMode,
        limit: int,
    ) -> dict[str, Any]: ...

    async def retry_ai_drafts(
        self,
        external_queue_id: str,
        external_case_ids: Sequence[str],
        *,
        requested_by: str,
        model_id: str,
        prompt: Mapping[str, str],
        retry_reason: str,
    ) -> list[dict[str, Any]]: ...

    async def preview_ai_bulk_certification(
        self,
        external_queue_id: str,
        external_case_ids: Sequence[str],
    ) -> dict[str, Any]: ...

    async def commit_ai_bulk_certification(
        self,
        external_queue_id: str,
        external_case_ids: Sequence[str],
        *,
        reviewer_id: str,
        confirmation_checksum: str,
    ) -> dict[str, Any]: ...

    async def create_gold_set_replay(
        self,
        external_queue_id: str,
        gold_set: Mapping[str, Any],
        *,
        document_checksum: str,
        released_by: str,
        source_analysis_id: str,
        force_rebuild: bool,
        rebuild_reason: str | None,
    ) -> dict[str, Any]: ...


class PostgresMatchingV2ReviewRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def list_queues(self, *, limit: int) -> list[dict[str, Any]]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        SELECT q.external_queue_id, q.version, q.product_pack_id,
                               q.product_pack_version, q.policy_checksum,
                               q.document_checksum, q.imported_by, q.created_at,
                               count(DISTINCT c.id) AS case_count,
                               count(DISTINCT s.review_case_id)
                                 FILTER (WHERE s.review_case_id IS NOT NULL) AS reviewed_case_count,
                               count(DISTINCT a.review_case_id)
                                 FILTER (WHERE a.review_case_id IS NOT NULL)
                                 AS adjudicated_case_count
                        FROM matching_v2_review_queue q
                        LEFT JOIN matching_v2_review_case c ON c.review_queue_id = q.id
                        LEFT JOIN matching_v2_review_submission s ON s.review_case_id = c.id
                        LEFT JOIN matching_v2_adjudication a ON a.review_case_id = c.id
                        GROUP BY q.id
                        ORDER BY q.created_at DESC
                        LIMIT :limit
                        """
                    ),
                    {"limit": limit},
                )
            ).mappings()
            return [
                {
                    "queue_id": row["external_queue_id"],
                    "version": row["version"],
                    "product_pack": {
                        "id": row["product_pack_id"],
                        "version": row["product_pack_version"],
                    },
                    "policy_checksum": row["policy_checksum"],
                    "checksum": row["document_checksum"],
                    "imported_by": row["imported_by"],
                    "created_at": row["created_at"].isoformat(),
                    "case_count": int(row["case_count"]),
                    "reviewed_case_count": int(row["reviewed_case_count"]),
                    "adjudicated_case_count": int(row["adjudicated_case_count"]),
                }
                for row in rows
            ]

    async def import_queue(
        self,
        organization_id: str,
        queue: Mapping[str, Any],
        *,
        imported_by: str,
        successor_of_version: str | None = None,
        carry_forward_certified: bool = False,
        carry_forward_attribute_evidence: bool = False,
        scope_only_pack_revision: bool = False,
    ) -> dict[str, Any]:
        async with self._engine.begin() as connection:
            existing = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT id::text, document_checksum
                        FROM matching_v2_review_queue
                        WHERE organization_id = CAST(:organization_id AS uuid)
                          AND external_queue_id = :queue_id
                          AND version = :version
                        """
                        ),
                        {
                            "organization_id": organization_id,
                            "queue_id": queue["queue_id"],
                            "version": queue["version"],
                        },
                    )
                )
                .mappings()
                .first()
            )
            if existing is not None:
                if str(existing["document_checksum"]) != str(queue["checksum"]):
                    raise ValueError("queue ID/version already exists with a different checksum")
                return {
                    "id": str(existing["id"]),
                    "queue_id": queue["queue_id"],
                    "version": queue["version"],
                    "checksum": queue["checksum"],
                    "imported": False,
                    "case_count": len(queue["cases"]),
                }
            row = (
                (
                    await connection.execute(
                        text(
                            """
                        INSERT INTO matching_v2_review_queue (
                          organization_id, external_queue_id, version,
                          product_pack_id, product_pack_version, policy_checksum,
                          source_evidence, sampling, document, document_checksum, imported_by
                        ) VALUES (
                          CAST(:organization_id AS uuid), :queue_id, :version,
                          :product_pack_id, :product_pack_version, :policy_checksum,
                          CAST(:source_evidence AS jsonb), CAST(:sampling AS jsonb),
                          CAST(:document AS jsonb), :document_checksum, :imported_by
                        )
                        RETURNING id::text
                        """
                        ),
                        {
                            "organization_id": organization_id,
                            "queue_id": queue["queue_id"],
                            "version": queue["version"],
                            "product_pack_id": queue["product_pack"]["id"],
                            "product_pack_version": queue["product_pack"]["version"],
                            "policy_checksum": queue["policy_checksum"],
                            "source_evidence": _canonical(queue["source_evidence"]),
                            "sampling": _canonical(queue["sampling"]),
                            "document": _canonical(queue),
                            "document_checksum": queue["checksum"],
                            "imported_by": imported_by,
                        },
                    )
                )
                .mappings()
                .one()
            )
            review_queue_id = str(row["id"])
            successor_cases: dict[str, tuple[str, Mapping[str, Any]]] = {}
            successor_pairs: dict[tuple[str, str], tuple[str, Mapping[str, Any]]] = {}
            for case in queue["cases"]:
                case_id = await self._insert_case(connection, review_queue_id, case)
                successor_cases[str(case["case_id"])] = (case_id, case)
                pair = (
                    str(case["benchmark_listing_id"]),
                    str(case["competitor_listing_id"]),
                )
                if pair in successor_pairs:
                    raise ValueError(f"successor queue contains duplicate listing pair {pair!r}")
                successor_pairs[pair] = (case_id, case)
            carried_forward_count = 0
            carried_forward_attribute_decision_count = 0
            skipped_attribute_decision_checksums: list[str] = []
            if carry_forward_certified:
                if successor_of_version is None:
                    raise ValueError(
                        "carry_forward_certified requires an explicit predecessor version"
                    )
                carried_forward_count = await self._carry_forward_certified_submissions(
                    connection,
                    organization_id=organization_id,
                    queue=queue,
                    predecessor_version=successor_of_version,
                    successor_cases=successor_cases,
                    successor_pairs=successor_pairs,
                    scope_only_pack_revision=scope_only_pack_revision,
                )
            if carry_forward_attribute_evidence:
                if successor_of_version is None:
                    raise ValueError(
                        "carry_forward_attribute_evidence requires an explicit predecessor version"
                    )
                (
                    carried_forward_attribute_decision_count,
                    skipped_attribute_decision_checksums,
                ) = await self._carry_forward_attribute_evidence_decisions(
                    connection,
                    organization_id=organization_id,
                    queue=queue,
                    predecessor_version=successor_of_version,
                    successor_pairs=successor_pairs,
                )
        return {
            "id": review_queue_id,
            "queue_id": queue["queue_id"],
            "version": queue["version"],
            "checksum": queue["checksum"],
            "imported": True,
            "case_count": len(queue["cases"]),
            "carried_forward_count": carried_forward_count,
            "carried_forward_attribute_decision_count": (carried_forward_attribute_decision_count),
            "skipped_attribute_decision_count": len(skipped_attribute_decision_checksums),
            "skipped_attribute_decision_checksums": skipped_attribute_decision_checksums,
            "pending_case_count": len(queue["cases"]) - carried_forward_count,
            "successor_of_version": successor_of_version,
            "scope_only_pack_revision": scope_only_pack_revision,
        }

    @staticmethod
    async def _insert_case(
        connection: AsyncConnection,
        review_queue_id: str,
        case: Mapping[str, Any],
    ) -> str:
        row = (
            (
                await connection.execute(
                    text(
                        """
                INSERT INTO matching_v2_review_case (
                  review_queue_id, external_case_id, benchmark_listing_id,
                  competitor_listing_id, competitor_retailer_id, stratum,
                  critical, case_document, case_checksum
                ) VALUES (
                  CAST(:review_queue_id AS uuid), :external_case_id, :benchmark_listing_id,
                  :competitor_listing_id, :competitor_retailer_id, :stratum,
                  :critical, CAST(:case_document AS jsonb), :case_checksum
                )
                RETURNING id::text
                """
                    ),
                    {
                        "review_queue_id": review_queue_id,
                        "external_case_id": case["case_id"],
                        "benchmark_listing_id": case["benchmark_listing_id"],
                        "competitor_listing_id": case["competitor_listing_id"],
                        "competitor_retailer_id": case["competitor_retailer_id"],
                        "stratum": case["stratum"],
                        "critical": case["critical"],
                        "case_document": _canonical(case),
                        "case_checksum": _checksum(case),
                    },
                )
            )
            .mappings()
            .one()
        )
        return str(row["id"])

    @staticmethod
    def _without_additive_image_evidence(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {
                str(key): PostgresMatchingV2ReviewRepository._without_additive_image_evidence(child)
                for key, child in value.items()
                if str(key) not in {"image_url", "image_urls"}
            }
        if isinstance(value, list):
            return [
                PostgresMatchingV2ReviewRepository._without_additive_image_evidence(child)
                for child in value
            ]
        return value

    @staticmethod
    def _collect_image_evidence(value: Any) -> set[str]:
        images: set[str] = set()
        if isinstance(value, Mapping):
            for key, child in value.items():
                if str(key) == "image_url" and child:
                    images.add(str(child))
                elif str(key) == "image_urls" and isinstance(child, list):
                    images.update(str(item) for item in child if item)
                else:
                    images.update(PostgresMatchingV2ReviewRepository._collect_image_evidence(child))
        elif isinstance(value, list):
            for child in value:
                images.update(PostgresMatchingV2ReviewRepository._collect_image_evidence(child))
        return images

    @staticmethod
    def _image_evidence_is_additive(
        predecessor: Mapping[str, Any], successor: Mapping[str, Any]
    ) -> bool:
        for side in ("benchmark_listing", "competitor_listing"):
            old_listing = predecessor.get(side)
            new_listing = successor.get(side)
            if not isinstance(old_listing, Mapping) or not isinstance(new_listing, Mapping):
                return False
            old_images = PostgresMatchingV2ReviewRepository._collect_image_evidence(old_listing)
            new_images = PostgresMatchingV2ReviewRepository._collect_image_evidence(new_listing)
            if not old_images.issubset(new_images):
                return False
        return True

    _ATTRIBUTE_PROPOSAL_CHECKSUM_FIELDS = (
        "proposal_index",
        "ai_task_id",
        "ai_output_checksum",
        "case_checksum",
        "policy_checksum",
        "listing_role",
        "listing_id",
        "attribute",
        "raw_value",
        "normalized_value",
        "evidence_source",
        "confidence",
        "visible_text",
        "source_image_url",
        "eligible",
        "ineligibility_reasons",
    )

    @classmethod
    def _attribute_proposal_checksum_is_valid(cls, proposal: Mapping[str, Any]) -> bool:
        expected = str(proposal.get("proposal_checksum") or "")
        payload = {field: proposal.get(field) for field in cls._ATTRIBUTE_PROPOSAL_CHECKSUM_FIELDS}
        return len(expected) == 64 and _checksum(payload) == expected

    @staticmethod
    def _attribute_row(case: Mapping[str, Any], attribute: str) -> Mapping[str, Any] | None:
        edge = case.get("edge")
        rows = edge.get("attribute_evidence") if isinstance(edge, Mapping) else None
        return next(
            (
                row
                for row in rows or []
                if isinstance(row, Mapping) and str(row.get("attribute") or "") == attribute
            ),
            None,
        )

    @classmethod
    def _attribute_evidence_successor_is_compatible(
        cls,
        *,
        proposal: Mapping[str, Any],
        predecessor_case: Mapping[str, Any],
        successor_case: Mapping[str, Any],
        policy_checksum: str,
        ai_output_checksum: str,
    ) -> bool:
        """Allow brand-only queue enrichment without weakening image-evidence lineage."""

        if (
            proposal.get("eligible") is not True
            or proposal.get("evidence_source") != "image"
            or str(proposal.get("policy_checksum") or "") != policy_checksum
            or str(proposal.get("ai_output_checksum") or "") != ai_output_checksum
            or not cls._attribute_proposal_checksum_is_valid(proposal)
        ):
            return False
        role = str(proposal.get("listing_role") or "")
        attribute = str(proposal.get("attribute") or "")
        if role not in {"benchmark", "competitor"} or not attribute:
            return False
        predecessor_listing = predecessor_case.get(f"{role}_listing")
        successor_listing = successor_case.get(f"{role}_listing")
        if not isinstance(predecessor_listing, Mapping) or not isinstance(
            successor_listing, Mapping
        ):
            return False
        listing_id = str(proposal.get("listing_id") or "")
        predecessor_listing_id = str(
            predecessor_listing.get("listing_id")
            or predecessor_case.get(f"{role}_listing_id")
            or ""
        )
        successor_listing_id = str(
            successor_listing.get("listing_id") or successor_case.get(f"{role}_listing_id") or ""
        )
        if (
            not listing_id
            or listing_id != predecessor_listing_id
            or listing_id != successor_listing_id
        ):
            return False
        source_image = str(proposal.get("source_image_url") or "")
        if (
            not source_image
            or source_image not in cls._collect_image_evidence(predecessor_listing)
            or source_image not in cls._collect_image_evidence(successor_listing)
        ):
            return False
        predecessor_row = cls._attribute_row(predecessor_case, attribute)
        successor_row = cls._attribute_row(successor_case, attribute)
        if predecessor_row is None or successor_row is None:
            return False
        value_key = f"{role}_value"
        source_key = f"{role}_source"
        return _canonical(predecessor_row.get(value_key)) == _canonical(
            proposal.get("current_value")
        ) == _canonical(successor_row.get(value_key)) and str(
            predecessor_row.get(source_key) or ""
        ) == str(proposal.get("current_source") or "") == str(successor_row.get(source_key) or "")

    @staticmethod
    def _scope_only_pack_revision_is_compatible(
        predecessor: Mapping[str, Any], successor: Mapping[str, Any]
    ) -> bool:
        """Permit only additive scope exclusions and version-reference changes."""

        predecessor_document = json.loads(_canonical(predecessor))
        successor_document = json.loads(_canonical(successor))
        if str(predecessor_document.get("id") or "") != str(successor_document.get("id") or ""):
            return False
        if str(predecessor_document.get("version") or "") == str(
            successor_document.get("version") or ""
        ):
            return False
        predecessor_scope = predecessor_document.get("scope")
        successor_scope = successor_document.get("scope")
        if not isinstance(predecessor_scope, dict) or not isinstance(successor_scope, dict):
            return False
        predecessor_exclusions = {
            str(value) for value in predecessor_scope.get("hard_exclusion_patterns", [])
        }
        successor_exclusions = {
            str(value) for value in successor_scope.get("hard_exclusion_patterns", [])
        }
        if not predecessor_exclusions < successor_exclusions:
            return False
        predecessor_document.pop("version", None)
        successor_document.pop("version", None)
        predecessor_scope.pop("hard_exclusion_patterns", None)
        successor_scope.pop("hard_exclusion_patterns", None)
        for document in (predecessor_document, successor_document):
            reporting = document.get("reporting")
            if not isinstance(reporting, dict):
                return False
            blueprint = reporting.get("report_blueprint")
            if not isinstance(blueprint, dict):
                return False
            blueprint.pop("version", None)
        return predecessor_document == successor_document

    @classmethod
    def _without_scope_revision_metadata(cls, value: Mapping[str, Any]) -> Any:
        """Remove identifiers derived solely from a compatible Product Pack revision."""

        document = json.loads(_canonical(value))
        document.pop("case_id", None)
        edge = document.get("edge")
        if isinstance(edge, dict):
            edge.pop("edge_id", None)
            policy = edge.get("policy")
            if isinstance(policy, dict):
                policy.pop("checksum", None)
                policy.pop("product_pack_version", None)
        proposal = document.get("engine_proposal")
        if isinstance(proposal, dict):
            proposal.pop("edge_id", None)
        evidence_refs = document.get("evidence_refs")
        if isinstance(evidence_refs, list):
            document["evidence_refs"] = [
                str(reference).partition("|edge_id=")[0] for reference in evidence_refs
            ]
        return cls._without_additive_image_evidence(document)

    @classmethod
    async def _carry_forward_certified_submissions(
        cls,
        connection: AsyncConnection,
        *,
        organization_id: str,
        queue: Mapping[str, Any],
        predecessor_version: str,
        successor_cases: Mapping[str, tuple[str, Mapping[str, Any]]],
        successor_pairs: Mapping[tuple[str, str], tuple[str, Mapping[str, Any]]],
        scope_only_pack_revision: bool,
    ) -> int:
        predecessor = (
            (
                await connection.execute(
                    text(
                        """
                        SELECT id::text, product_pack_id, product_pack_version,
                               policy_checksum
                        FROM matching_v2_review_queue
                        WHERE organization_id = CAST(:organization_id AS uuid)
                          AND external_queue_id = :queue_id
                          AND version = :version
                        """
                    ),
                    {
                        "organization_id": organization_id,
                        "queue_id": queue["queue_id"],
                        "version": predecessor_version,
                    },
                )
            )
            .mappings()
            .first()
        )
        if predecessor is None:
            raise ValueError("the declared predecessor review queue was not found")
        if str(predecessor["product_pack_id"]) != str(queue["product_pack"]["id"]):
            raise ValueError("certified decisions cannot cross Product Pack identities")
        if scope_only_pack_revision:
            versions = (
                await connection.execute(
                    text(
                        """
                        SELECT version, config
                        FROM product_pack_version
                        WHERE product_pack_id = :product_pack_id
                          AND version IN (:predecessor_version, :successor_version)
                        """
                    ),
                    {
                        "product_pack_id": queue["product_pack"]["id"],
                        "predecessor_version": predecessor["product_pack_version"],
                        "successor_version": queue["product_pack"]["version"],
                    },
                )
            ).mappings()
            pack_documents = {str(row["version"]): dict(row["config"]) for row in versions}
            predecessor_pack = pack_documents.get(str(predecessor["product_pack_version"]))
            successor_pack = pack_documents.get(str(queue["product_pack"]["version"]))
            if (
                predecessor_pack is None
                or successor_pack is None
                or not cls._scope_only_pack_revision_is_compatible(predecessor_pack, successor_pack)
            ):
                raise ValueError(
                    "scope-only carry-forward requires an additive exclusion-only "
                    "Product Pack revision"
                )
        elif str(predecessor["product_pack_version"]) != str(
            queue["product_pack"]["version"]
        ) or str(predecessor["policy_checksum"]) != str(queue["policy_checksum"]):
            raise ValueError("certified decisions cannot cross Product Pack or policy revisions")
        adjudication_count = (
            await connection.execute(
                text(
                    """
                    SELECT count(*)
                    FROM matching_v2_adjudication a
                    JOIN matching_v2_review_case c ON c.id = a.review_case_id
                    WHERE c.review_queue_id = CAST(:queue_id AS uuid)
                    """
                ),
                {"queue_id": predecessor["id"]},
            )
        ).scalar_one()
        if int(adjudication_count) > 0:
            raise ValueError(
                "evidence-only succession requires explicit handling for adjudicated decisions"
            )
        rows = (
            await connection.execute(
                text(
                    """
                    SELECT DISTINCT ON (c.id)
                           c.external_case_id, c.case_document,
                           s.id::text AS submission_id, s.reviewer_id, s.verdict,
                           s.allowed_tiers, s.rationale, s.evidence_refs
                    FROM matching_v2_review_case c
                    JOIN matching_v2_review_submission s ON s.review_case_id = c.id
                    WHERE c.review_queue_id = CAST(:queue_id AS uuid)
                    ORDER BY c.id, s.created_at DESC, s.id DESC
                    """
                ),
                {"queue_id": predecessor["id"]},
            )
        ).mappings()
        carried = 0
        for row in rows:
            if str(row["verdict"]) not in {"comparable", "not_comparable"}:
                continue
            external_case_id = str(row["external_case_id"])
            predecessor_document = dict(row["case_document"])
            if scope_only_pack_revision:
                pair = (
                    str(predecessor_document.get("benchmark_listing_id") or ""),
                    str(predecessor_document.get("competitor_listing_id") or ""),
                )
                successor = successor_pairs.get(pair)
            else:
                successor = successor_cases.get(external_case_id)
            if successor is None:
                raise ValueError(
                    "a certified predecessor case is absent from the successor queue: "
                    f"{external_case_id}"
                )
            successor_case_id, successor_document = successor
            documents_match = (
                cls._without_scope_revision_metadata(predecessor_document)
                == cls._without_scope_revision_metadata(successor_document)
                if scope_only_pack_revision
                else cls._without_additive_image_evidence(predecessor_document)
                == cls._without_additive_image_evidence(successor_document)
            )
            if (
                not cls._image_evidence_is_additive(predecessor_document, successor_document)
                or not documents_match
            ):
                raise ValueError(
                    "a certified decision can only carry across compatible immutable evidence: "
                    f"{external_case_id}"
                )
            predecessor_submission_id = str(row["submission_id"])
            provenance_ref = f"matching-v2-review-submission:{predecessor_submission_id}"
            evidence_refs = [str(value) for value in (row["evidence_refs"] or [])]
            for reference in successor_document.get("evidence_refs", []):
                rendered = str(reference)
                if rendered not in evidence_refs:
                    evidence_refs.append(rendered)
            if provenance_ref not in evidence_refs:
                evidence_refs.append(provenance_ref)
            carry_note = (
                f"\n\nCarried forward from immutable queue version {predecessor_version}; "
                + (
                    "the pair, governed attributes, matching policy, proposal, and source "
                    "evidence are unchanged under an audited additive scope-exclusion revision."
                    if scope_only_pack_revision
                    else "the pair, governed attributes, policy, proposal, and source evidence "
                    "are unchanged, with only additive PDP image references in this successor."
                )
            )
            rationale = str(row["rationale"])
            rationale = f"{rationale[: max(0, 10_000 - len(carry_note))]}{carry_note}"
            submission_document = {
                "review_case_id": successor_case_id,
                "reviewer_id": str(row["reviewer_id"]),
                "verdict": str(row["verdict"]),
                "allowed_tiers": list(row["allowed_tiers"] or []),
                "rationale": rationale,
                "evidence_refs": evidence_refs,
                "supersedes_submission_id": predecessor_submission_id,
            }
            await connection.execute(
                text(
                    """
                    INSERT INTO matching_v2_review_submission (
                      review_case_id, reviewer_id, verdict, allowed_tiers,
                      rationale, evidence_refs, submission_checksum,
                      supersedes_submission_id
                    ) VALUES (
                      CAST(:case_id AS uuid), :reviewer_id, :verdict, :allowed_tiers,
                      :rationale, CAST(:evidence_refs AS jsonb), :submission_checksum,
                      CAST(:supersedes_submission_id AS uuid)
                    )
                    """
                ),
                {
                    "case_id": successor_case_id,
                    "reviewer_id": submission_document["reviewer_id"],
                    "verdict": submission_document["verdict"],
                    "allowed_tiers": submission_document["allowed_tiers"],
                    "rationale": rationale,
                    "evidence_refs": _canonical(evidence_refs),
                    "submission_checksum": _checksum(submission_document),
                    "supersedes_submission_id": predecessor_submission_id,
                },
            )
            carried += 1
        return carried

    @classmethod
    async def _carry_forward_attribute_evidence_decisions(
        cls,
        connection: AsyncConnection,
        *,
        organization_id: str,
        queue: Mapping[str, Any],
        predecessor_version: str,
        successor_pairs: Mapping[tuple[str, str], tuple[str, Mapping[str, Any]]],
    ) -> tuple[int, list[str]]:
        """Carry only source-identical human evidence decisions into a successor queue."""

        predecessor = (
            (
                await connection.execute(
                    text(
                        """
                        SELECT id::text, product_pack_id, product_pack_version,
                               policy_checksum
                        FROM matching_v2_review_queue
                        WHERE organization_id = CAST(:organization_id AS uuid)
                          AND external_queue_id = :queue_id
                          AND version = :version
                        """
                    ),
                    {
                        "organization_id": organization_id,
                        "queue_id": queue["queue_id"],
                        "version": predecessor_version,
                    },
                )
            )
            .mappings()
            .first()
        )
        if predecessor is None:
            raise ValueError("the declared predecessor review queue was not found")
        if (
            str(predecessor["product_pack_id"]) != str(queue["product_pack"]["id"])
            or str(predecessor["product_pack_version"]) != str(queue["product_pack"]["version"])
            or str(predecessor["policy_checksum"]) != str(queue["policy_checksum"])
        ):
            raise ValueError(
                "attribute evidence decisions cannot cross Product Pack or policy revisions"
            )
        active_policy = _active_certification_policy(str(queue["product_pack"]["id"]))
        if str(active_policy.get("product_pack_version") or "") != str(
            queue["product_pack"]["version"]
        ):
            raise ValueError(
                "attribute evidence succession requires the active Product Pack version"
            )
        attribute_policy_checksum = str(active_policy.get("policy_checksum") or "")
        rows = (
            await connection.execute(
                text(
                    """
                    SELECT DISTINCT ON (decision.proposal_checksum)
                           review_case.external_case_id,
                           review_case.case_document,
                           decision.id::text AS decision_id,
                           decision.ai_review_task_id::text AS ai_review_task_id,
                           decision.proposal_checksum,
                           decision.proposal_document,
                           decision.decision,
                           decision.reviewer_id,
                           decision.rationale,
                           task.output_checksum
                    FROM matching_v2_attribute_evidence_decision decision
                    JOIN matching_v2_review_case review_case
                      ON review_case.id = decision.review_case_id
                    JOIN matching_v2_ai_review_task task
                      ON task.id = decision.ai_review_task_id
                    WHERE review_case.review_queue_id = CAST(:queue_id AS uuid)
                    ORDER BY decision.proposal_checksum,
                             decision.created_at DESC,
                             decision.id DESC
                    """
                ),
                {"queue_id": predecessor["id"]},
            )
        ).mappings()
        carried = 0
        skipped: list[str] = []
        for row in rows:
            predecessor_case = dict(row["case_document"])
            pair = (
                str(predecessor_case.get("benchmark_listing_id") or ""),
                str(predecessor_case.get("competitor_listing_id") or ""),
            )
            successor = successor_pairs.get(pair)
            if successor is None:
                skipped.append(str(row["proposal_checksum"]))
                continue
            successor_case_id, successor_case = successor
            proposal = row["proposal_document"]
            if not isinstance(
                proposal, Mapping
            ) or not cls._attribute_evidence_successor_is_compatible(
                proposal=proposal,
                predecessor_case=predecessor_case,
                successor_case=successor_case,
                policy_checksum=attribute_policy_checksum,
                ai_output_checksum=str(row["output_checksum"] or ""),
            ):
                skipped.append(str(row["proposal_checksum"]))
                continue
            predecessor_decision_id = str(row["decision_id"])
            carry_note = (
                f"\n\nCarried forward from immutable queue version {predecessor_version}; "
                "the listing, attribute value, Product Pack policy, AI output, cited image, "
                "visible evidence, and proposal checksum are unchanged."
            )
            rationale = str(row["rationale"])
            rationale = f"{rationale[: max(0, 2_000 - len(carry_note))]}{carry_note}"
            external_case_id = str(successor_case.get("case_id") or "")
            decision_document = {
                "reviewer_id": str(row["reviewer_id"]),
                "proposal_checksum": str(row["proposal_checksum"]),
                "decision": str(row["decision"]),
                "rationale": rationale,
                "supersedes_decision_id": predecessor_decision_id,
            }
            decision_checksum = _checksum(
                {
                    "schema_version": "1.0.0-attribute-evidence-decision",
                    "queue_id": queue["queue_id"],
                    "case_id": external_case_id,
                    **decision_document,
                }
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO matching_v2_attribute_evidence_decision (
                      review_case_id, ai_review_task_id, proposal_checksum,
                      proposal_document, decision, reviewer_id, rationale,
                      decision_checksum, supersedes_decision_id
                    ) VALUES (
                      CAST(:case_id AS uuid), CAST(:ai_task_id AS uuid),
                      :proposal_checksum, CAST(:proposal_document AS jsonb),
                      :decision, :reviewer_id, :rationale, :decision_checksum,
                      CAST(:supersedes_decision_id AS uuid)
                    )
                    """
                ),
                {
                    "case_id": successor_case_id,
                    "ai_task_id": row["ai_review_task_id"],
                    "proposal_checksum": row["proposal_checksum"],
                    "proposal_document": _canonical(proposal),
                    "decision": row["decision"],
                    "reviewer_id": row["reviewer_id"],
                    "rationale": rationale,
                    "decision_checksum": decision_checksum,
                    "supersedes_decision_id": predecessor_decision_id,
                },
            )
            carried += 1
        return carried, skipped

    async def queue_view(
        self,
        external_queue_id: str,
        *,
        competitor_retailer_id: str | None,
        benchmark_product_id: str | None,
        competitor_product_id: str | None,
        stratum: str | None,
        review_status: str | None,
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        async with self._engine.connect() as connection:
            queue = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT id::text, external_queue_id, version, product_pack_id,
                               product_pack_version, policy_checksum, document_checksum,
                               imported_by, created_at
                        FROM matching_v2_review_queue
                        WHERE external_queue_id = :queue_id
                        ORDER BY created_at DESC
                        LIMIT 1
                        """
                        ),
                        {"queue_id": external_queue_id},
                    )
                )
                .mappings()
                .first()
            )
            if queue is None:
                raise KeyError(f"matching v2 review queue {external_queue_id!r} was not found")
            cases = await self._case_rows(
                connection,
                str(queue["id"]),
                competitor_retailer_id=competitor_retailer_id,
                benchmark_product_id=benchmark_product_id,
                competitor_product_id=competitor_product_id,
                stratum=stratum,
            )
            case_ids = [str(case["id"]) for case in cases]
            submissions = await self._submission_rows(connection, case_ids)
            adjudications = await self._adjudication_rows(connection, case_ids)
            ai_drafts = await self._ai_draft_rows(connection, case_ids)
            attribute_decisions = await self._queue_attribute_decision_rows(
                connection, str(queue["id"])
            )
            ai_review_summary = await self._ai_review_summary(connection, str(queue["id"]))
        documents = self._case_documents(
            cases, submissions, adjudications, ai_drafts, attribute_decisions
        )
        _apply_observed_location_sidecar(
            documents,
            queue_id=external_queue_id,
            queue_version=str(queue["version"]),
            root=_repository_root(),
        )
        documents = [
            document for document in documents if not _case_has_known_third_party_seller(document)
        ]
        documents.sort(key=_case_order_key)
        competitor_counts: dict[str, int] = defaultdict(int)
        for document in documents:
            retailer_id = str(document.get("competitor_retailer_id") or "")
            if retailer_id:
                competitor_counts[retailer_id] += 1
        competitor_retailers = [
            {"retailer_id": retailer_id, "case_count": case_count}
            for retailer_id, case_count in sorted(competitor_counts.items())
        ]
        summary_counts: dict[str, int] = defaultdict(int)
        for row in documents:
            summary_counts[str(row["review_status"])] += 1
        total_cases = len(documents)
        if review_status is not None:
            documents = [row for row in documents if row["review_status"] == review_status]
        return {
            "schema_version": "2.0.0-review-view",
            "authoritative": False,
            "queue": {
                "id": str(queue["id"]),
                "queue_id": queue["external_queue_id"],
                "version": queue["version"],
                "product_pack": {
                    "id": queue["product_pack_id"],
                    "version": queue["product_pack_version"],
                },
                "policy_checksum": queue["policy_checksum"],
                "checksum": queue["document_checksum"],
                "imported_by": queue["imported_by"],
                "created_at": queue["created_at"].isoformat(),
            },
            "filters": {
                "competitor_retailer_id": competitor_retailer_id,
                "benchmark_product_id": benchmark_product_id,
                "competitor_product_id": competitor_product_id,
                "stratum": stratum,
                "review_status": review_status,
            },
            "competitor_retailers": competitor_retailers,
            "ai_review_summary": ai_review_summary,
            "status_counts": dict(sorted(summary_counts.items())),
            "total_cases": total_cases,
            "selected_case_count": len(documents),
            "offset": offset,
            "limit": limit,
            "cases": documents[offset : offset + limit],
        }

    @staticmethod
    async def _competitor_retailers(
        connection: AsyncConnection,
        review_queue_id: str,
        *,
        stratum: str | None,
    ) -> list[dict[str, Any]]:
        rows = (
            await connection.execute(
                text(
                    """
                    SELECT competitor_retailer_id, count(*) AS case_count
                    FROM matching_v2_review_case
                    WHERE review_queue_id = CAST(:review_queue_id AS uuid)
                      AND (CAST(:stratum AS text) IS NULL
                           OR stratum = CAST(:stratum AS text))
                    GROUP BY competitor_retailer_id
                    ORDER BY competitor_retailer_id
                    """
                ),
                {
                    "review_queue_id": review_queue_id,
                    "stratum": stratum,
                },
            )
        ).mappings()
        return [
            {
                "retailer_id": str(row["competitor_retailer_id"]),
                "case_count": int(row["case_count"]),
            }
            for row in rows
        ]

    @staticmethod
    async def _case_rows(
        connection: AsyncConnection,
        review_queue_id: str,
        *,
        competitor_retailer_id: str | None,
        benchmark_product_id: str | None,
        competitor_product_id: str | None,
        stratum: str | None,
    ) -> list[Mapping[str, Any]]:
        rows = (
            await connection.execute(
                text(
                    """
                    SELECT id::text, external_case_id, competitor_retailer_id,
                           stratum, critical, case_document, case_checksum, created_at
                    FROM matching_v2_review_case
                    WHERE review_queue_id = CAST(:review_queue_id AS uuid)
                      AND (CAST(:competitor_retailer_id AS text) IS NULL
                           OR competitor_retailer_id = CAST(:competitor_retailer_id AS text))
                      AND (CAST(:benchmark_product_id AS text) IS NULL
                           OR case_document #>> '{benchmark_listing,retailer_product_id}' =
                              CAST(:benchmark_product_id AS text))
                      AND (CAST(:competitor_product_id AS text) IS NULL
                           OR case_document #>> '{competitor_listing,retailer_product_id}' =
                              CAST(:competitor_product_id AS text))
                      AND (CAST(:stratum AS text) IS NULL
                           OR stratum = CAST(:stratum AS text))
                    ORDER BY critical DESC, stratum, external_case_id
                    """
                ),
                {
                    "review_queue_id": review_queue_id,
                    "competitor_retailer_id": competitor_retailer_id,
                    "benchmark_product_id": benchmark_product_id,
                    "competitor_product_id": competitor_product_id,
                    "stratum": stratum,
                },
            )
        ).mappings()
        return [dict(row) for row in rows]

    @staticmethod
    async def _submission_rows(
        connection: AsyncConnection, case_ids: Sequence[str]
    ) -> list[Mapping[str, Any]]:
        if not case_ids:
            return []
        rows = (
            await connection.execute(
                text(
                    """
                    SELECT id::text, review_case_id::text, reviewer_id, verdict,
                           allowed_tiers, rationale, evidence_refs,
                           submission_checksum, supersedes_submission_id::text,
                           bulk_action_id::text, created_at
                    FROM matching_v2_review_submission
                    WHERE review_case_id = ANY(CAST(:case_ids AS uuid[]))
                    ORDER BY review_case_id, created_at DESC, id DESC
                    """
                ),
                {"case_ids": list(case_ids)},
            )
        ).mappings()
        return [dict(row) for row in rows]

    @staticmethod
    async def _adjudication_rows(
        connection: AsyncConnection, case_ids: Sequence[str]
    ) -> list[Mapping[str, Any]]:
        if not case_ids:
            return []
        rows = (
            await connection.execute(
                text(
                    """
                    SELECT DISTINCT ON (a.review_case_id)
                           a.id::text, a.review_case_id::text, a.adjudicator_id,
                           a.verdict, a.allowed_tiers, a.rationale, a.evidence_refs,
                           a.adjudication_checksum, a.created_at,
                           coalesce(array_agg(link.submission_id::text)
                             FILTER (WHERE link.submission_id IS NOT NULL), ARRAY[]::text[])
                             AS submission_ids
                    FROM matching_v2_adjudication a
                    LEFT JOIN matching_v2_adjudication_submission link
                      ON link.adjudication_id = a.id
                    WHERE a.review_case_id = ANY(CAST(:case_ids AS uuid[]))
                    GROUP BY a.id
                    ORDER BY a.review_case_id, a.created_at DESC, a.id DESC
                    """
                ),
                {"case_ids": list(case_ids)},
            )
        ).mappings()
        return [dict(row) for row in rows]

    @staticmethod
    async def _ai_draft_rows(
        connection: AsyncConnection, case_ids: Sequence[str]
    ) -> list[Mapping[str, Any]]:
        if not case_ids:
            return []
        rows = (
            await connection.execute(
                text(
                    """
                    WITH RECURSIVE task_lineage AS (
                      SELECT task.id, task.batch_id AS root_batch_id
                      FROM matching_v2_ai_review_task task
                      WHERE task.retry_of_task_id IS NULL
                      UNION ALL
                      SELECT child.id, parent.root_batch_id
                      FROM matching_v2_ai_review_task child
                      JOIN task_lineage parent ON parent.id = child.retry_of_task_id
                    )
                    SELECT DISTINCT ON (task.review_case_id)
                           task.id::text, task.batch_id::text,
                           lineage.root_batch_id::text,
                           task.review_case_id::text,
                           task.status, task.requested_by,
                           task.model_provider, task.model_id, task.prompt_id,
                           task.prompt_version, task.prompt_checksum,
                           task.input_checksum, task.output_checksum,
                           task.output_document, task.usage, task.attempt_count,
                           task.max_attempts, task.retry_of_task_id::text,
                           task.retry_sequence, task.retry_reason,
                           task.last_error_type, task.last_error_message,
                           task.created_at, task.updated_at, task.locked_at,
                           task.lease_expires_at, task.completed_at
                    FROM matching_v2_ai_review_task task
                    JOIN task_lineage lineage ON lineage.id = task.id
                    WHERE task.review_case_id = ANY(CAST(:case_ids AS uuid[]))
                    ORDER BY task.review_case_id, task.created_at DESC, task.id DESC
                    """
                ),
                {"case_ids": list(case_ids)},
            )
        ).mappings()
        return [dict(row) for row in rows]

    @staticmethod
    async def _attribute_decision_rows(
        connection: AsyncConnection, case_ids: Sequence[str]
    ) -> list[Mapping[str, Any]]:
        if not case_ids:
            return []
        rows = (
            await connection.execute(
                text(
                    """
                    SELECT id::text, review_case_id::text, ai_review_task_id::text,
                           proposal_checksum, proposal_document, decision, reviewer_id,
                           rationale, decision_checksum, supersedes_decision_id::text,
                           created_at
                    FROM matching_v2_attribute_evidence_decision
                    WHERE review_case_id = ANY(CAST(:case_ids AS uuid[]))
                    ORDER BY review_case_id, proposal_checksum, created_at DESC, id DESC
                    """
                ),
                {"case_ids": list(case_ids)},
            )
        ).mappings()
        return [dict(row) for row in rows]

    @staticmethod
    async def _queue_attribute_decision_rows(
        connection: AsyncConnection, review_queue_id: str
    ) -> list[Mapping[str, Any]]:
        """Return immutable evidence decisions available to any case for that product."""

        rows = (
            await connection.execute(
                text(
                    """
                    SELECT decision.id::text,
                           decision.review_case_id::text,
                           decision.ai_review_task_id::text,
                           decision.proposal_checksum,
                           decision.proposal_document,
                           decision.decision,
                           decision.reviewer_id,
                           decision.rationale,
                           decision.decision_checksum,
                           decision.supersedes_decision_id::text,
                           decision.created_at
                    FROM matching_v2_attribute_evidence_decision decision
                    JOIN matching_v2_review_case review_case
                      ON review_case.id = decision.review_case_id
                    WHERE review_case.review_queue_id = CAST(:review_queue_id AS uuid)
                    ORDER BY decision.proposal_checksum,
                             decision.created_at DESC,
                             decision.id DESC
                    """
                ),
                {"review_queue_id": review_queue_id},
            )
        ).mappings()
        return [dict(row) for row in rows]

    @staticmethod
    async def _ai_review_summary(
        connection: AsyncConnection, review_queue_id: str
    ) -> dict[str, Any]:
        status_row = (
            (
                await connection.execute(
                    text(
                        """
                        WITH latest AS (
                          SELECT DISTINCT ON (task.review_case_id)
                                 task.status
                          FROM matching_v2_ai_review_task task
                          JOIN matching_v2_review_case review_case
                            ON review_case.id = task.review_case_id
                          WHERE review_case.review_queue_id = CAST(:review_queue_id AS uuid)
                          ORDER BY task.review_case_id, task.created_at DESC, task.id DESC
                        )
                        SELECT count(*) FILTER (WHERE status = 'queued') AS queued,
                               count(*) FILTER (WHERE status = 'running') AS running,
                               count(*) FILTER (WHERE status = 'succeeded') AS succeeded,
                               count(*) FILTER (WHERE status = 'needs_review') AS needs_review
                        FROM latest
                        """
                    ),
                    {"review_queue_id": review_queue_id},
                )
            )
            .mappings()
            .one()
        )
        batch = (
            (
                await connection.execute(
                    text(
                        """
                        SELECT batch.id::text, batch.requested_by, batch.model_provider,
                               batch.model_id, batch.requested_case_count,
                               batch.created_at AS submitted_at,
                               min(task.locked_at) AS started_at,
                               max(task.updated_at) AS last_activity_at,
                               CASE
                                 WHEN count(task.id) > 0
                                  AND count(task.id) FILTER (
                                    WHERE task.status IN ('queued', 'running')
                                  ) = 0
                                 THEN max(coalesce(task.completed_at, task.updated_at))
                                 ELSE NULL
                               END AS completed_at,
                               count(task.id) AS task_count,
                               count(task.id) FILTER (WHERE task.status = 'queued') AS queued,
                               count(task.id) FILTER (WHERE task.status = 'running') AS running,
                               count(task.id) FILTER (WHERE task.status = 'succeeded') AS succeeded,
                               count(task.id) FILTER (
                                 WHERE task.status = 'needs_review'
                               ) AS needs_review,
                               coalesce(sum(
                                 CASE
                                   WHEN task.usage ? 'estimated_cost_usd'
                                   THEN (task.usage->>'estimated_cost_usd')::numeric
                                   ELSE 0
                                 END
                               ), 0) AS estimated_cost_usd
                        FROM matching_v2_ai_review_batch batch
                        LEFT JOIN matching_v2_ai_review_task task
                          ON task.batch_id = batch.id
                        WHERE batch.review_queue_id = CAST(:review_queue_id AS uuid)
                        GROUP BY batch.id
                        ORDER BY batch.created_at DESC, batch.id DESC
                        LIMIT 1
                        """
                    ),
                    {"review_queue_id": review_queue_id},
                )
            )
            .mappings()
            .first()
        )
        counts = {
            key: int(status_row[key] or 0)
            for key in ("queued", "running", "succeeded", "needs_review")
        }
        if batch is None:
            return {
                "active_task_count": counts["queued"] + counts["running"],
                "status_counts": counts,
                "latest_batch": None,
            }
        batch_counts = {
            key: int(batch[key] or 0) for key in ("queued", "running", "succeeded", "needs_review")
        }
        completed_count = batch_counts["succeeded"] + batch_counts["needs_review"]
        task_count = int(batch["task_count"] or 0)
        estimated_seconds_remaining: int | None = None
        if completed_count and batch_counts["queued"] + batch_counts["running"]:
            elapsed = max(
                0.0,
                (batch["last_activity_at"] - batch["submitted_at"]).total_seconds(),
            )
            estimated_seconds_remaining = math.ceil(
                (elapsed / completed_count) * (task_count - completed_count)
            )
        iso_fields = {
            key: (batch[key].isoformat() if batch[key] is not None else None)
            for key in ("submitted_at", "started_at", "last_activity_at", "completed_at")
        }
        return {
            "active_task_count": counts["queued"] + counts["running"],
            "status_counts": counts,
            "latest_batch": {
                "id": str(batch["id"]),
                "requested_by": str(batch["requested_by"]),
                "model_provider": str(batch["model_provider"]),
                "model_id": str(batch["model_id"]),
                "requested_case_count": int(batch["requested_case_count"]),
                "task_count": task_count,
                **batch_counts,
                "completed_count": completed_count,
                "progress_percent": (
                    round((completed_count / task_count) * 100, 1) if task_count else 0.0
                ),
                "estimated_seconds_remaining": estimated_seconds_remaining,
                "estimated_cost_usd": float(batch["estimated_cost_usd"] or 0),
                **iso_fields,
            },
        }

    @staticmethod
    def _case_documents(
        cases: Sequence[Mapping[str, Any]],
        submissions: Sequence[Mapping[str, Any]],
        adjudications: Sequence[Mapping[str, Any]],
        ai_drafts: Sequence[Mapping[str, Any]],
        attribute_decisions: Sequence[Mapping[str, Any]] = (),
    ) -> list[dict[str, Any]]:
        submissions_by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in submissions:
            submissions_by_case[str(row["review_case_id"])].append(
                {key: value for key, value in row.items() if key != "review_case_id"}
            )
        adjudication_by_case = {
            str(row["review_case_id"]): {
                key: value for key, value in row.items() if key != "review_case_id"
            }
            for row in adjudications
        }
        ai_draft_by_case = {
            str(row["review_case_id"]): {
                key: (value.isoformat() if hasattr(value, "isoformat") else value)
                for key, value in row.items()
                if key != "review_case_id"
            }
            for row in ai_drafts
        }
        attribute_decisions_by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
        attribute_decisions_by_listing: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in attribute_decisions:
            rendered = {
                key: (value.isoformat() if hasattr(value, "isoformat") else value)
                for key, value in row.items()
                if key != "review_case_id"
            }
            attribute_decisions_by_case[str(row["review_case_id"])].append(rendered)
            proposal_document = row.get("proposal_document")
            if isinstance(proposal_document, Mapping) and proposal_document.get("listing_id"):
                attribute_decisions_by_listing[str(proposal_document["listing_id"])].append(
                    rendered
                )
        output: list[dict[str, Any]] = []
        for row in cases:
            case_id = str(row["id"])
            reviews = submissions_by_case.get(case_id, [])
            adjudication = adjudication_by_case.get(case_id)
            decision_candidates: list[dict[str, Any]] = []
            if reviews:
                decision_candidates.append(
                    {
                        **reviews[0],
                        "source": "review_submission",
                        "reviewer_id": reviews[0]["reviewer_id"],
                    }
                )
            if adjudication is not None:
                decision_candidates.append(
                    {
                        **adjudication,
                        "source": "legacy_adjudication",
                        "reviewer_id": adjudication["adjudicator_id"],
                    }
                )
            final_decision = max(
                decision_candidates,
                key=lambda decision: decision["created_at"],
                default=None,
            )
            if final_decision is None:
                review_status = "pending"
            elif final_decision["verdict"] == "comparable":
                review_status = "approved"
            elif final_decision["verdict"] == "not_comparable":
                review_status = "rejected"
            else:
                review_status = "flagged"
            case_document = dict(row["case_document"])
            product_decisions: list[dict[str, Any]] = []
            for side in ("benchmark", "competitor"):
                listing = case_document.get(f"{side}_listing")
                listing_id = (
                    str(listing.get("listing_id") or "")
                    if isinstance(listing, Mapping)
                    else str(case_document.get(f"{side}_listing_id") or "")
                )
                product_decisions.extend(attribute_decisions_by_listing.get(listing_id, []))
            decisions = list(attribute_decisions_by_case.get(case_id, []))
            known_decision_ids = {str(decision.get("id") or "") for decision in decisions}
            decisions.extend(
                decision
                for decision in product_decisions
                if str(decision.get("id") or "") not in known_decision_ids
            )
            output.append(
                {
                    **case_document,
                    "database_id": case_id,
                    "case_checksum": str(
                        row.get("case_checksum") or _checksum(row["case_document"])
                    ),
                    "review_status": review_status,
                    "review_submissions": reviews,
                    "adjudication": adjudication,
                    "final_decision": final_decision,
                    "ai_draft": ai_draft_by_case.get(case_id),
                    "attribute_evidence_decisions": decisions,
                }
            )
        return output

    @staticmethod
    async def _bulk_ai_snapshot(
        connection: AsyncConnection,
        external_queue_id: str,
        external_case_ids: Sequence[str],
        *,
        lock_cases: bool,
    ) -> tuple[str, str, list[dict[str, Any]]]:
        lock_clause = "FOR UPDATE OF review_case" if lock_cases else ""
        rows = list(
            (
                await connection.execute(
                    text(
                        f"""
                        WITH selected_queue AS (
                          SELECT id, version, product_pack_id, product_pack_version
                          FROM matching_v2_review_queue
                          WHERE external_queue_id = :queue_id
                          ORDER BY created_at DESC
                          LIMIT 1
                        )
                        SELECT selected_queue.id::text AS review_queue_id,
                               selected_queue.version AS queue_version,
                               selected_queue.product_pack_id,
                               selected_queue.product_pack_version,
                               review_case.id::text AS review_case_id,
                               review_case.external_case_id,
                               review_case.case_document,
                               review_case.case_checksum,
                               current_decision.verdict AS current_verdict,
                               ai_task.id::text AS ai_task_id,
                               ai_task.status AS ai_status,
                               ai_task.output_document AS ai_output_document,
                               ai_task.output_checksum AS ai_output_checksum,
                               ai_task.model_id AS ai_model_id,
                               ai_task.requested_by AS ai_requested_by,
                               ai_task.created_at AS ai_created_at,
                               ai_task.updated_at AS ai_updated_at
                        FROM selected_queue
                        JOIN matching_v2_review_case review_case
                          ON review_case.review_queue_id = selected_queue.id
                        LEFT JOIN LATERAL (
                          SELECT decision.verdict
                          FROM (
                            SELECT submission.verdict, submission.created_at, submission.id
                            FROM matching_v2_review_submission submission
                            WHERE submission.review_case_id = review_case.id
                            UNION ALL
                            SELECT adjudication.verdict, adjudication.created_at, adjudication.id
                            FROM matching_v2_adjudication adjudication
                            WHERE adjudication.review_case_id = review_case.id
                          ) decision
                          ORDER BY decision.created_at DESC, decision.id DESC
                          LIMIT 1
                        ) current_decision ON true
                        LEFT JOIN LATERAL (
                          SELECT task.id, task.status, task.output_document,
                                 task.output_checksum, task.model_id, task.requested_by,
                                 task.created_at, task.updated_at
                          FROM matching_v2_ai_review_task task
                          WHERE task.review_case_id = review_case.id
                          ORDER BY task.created_at DESC, task.id DESC
                          LIMIT 1
                        ) ai_task ON true
                        WHERE review_case.external_case_id = ANY(CAST(:case_ids AS text[]))
                        ORDER BY review_case.external_case_id
                        {lock_clause}
                        """
                    ),
                    {"queue_id": external_queue_id, "case_ids": list(external_case_ids)},
                )
            )
            .mappings()
            .all()
        )
        if not rows:
            raise KeyError(f"matching v2 review queue {external_queue_id!r} was not found")
        rows_by_case = {str(row["external_case_id"]): row for row in rows}
        missing = [case_id for case_id in external_case_ids if case_id not in rows_by_case]
        if missing:
            raise KeyError(
                f"matching v2 review cases {missing!r} were not found in queue "
                f"{external_queue_id!r}"
            )
        certification_policy = _active_certification_policy(str(rows[0]["product_pack_id"]))
        decision_rows = await PostgresMatchingV2ReviewRepository._queue_attribute_decision_rows(
            connection, str(rows[0]["review_queue_id"])
        )
        snapshots: list[dict[str, Any]] = []
        for external_case_id in external_case_ids:
            row = rows_by_case[external_case_id]
            document = dict(row["case_document"])
            ai_draft = None
            if row["ai_task_id"] is not None:
                ai_draft = {
                    "id": str(row["ai_task_id"]),
                    "status": str(row["ai_status"]),
                    "output_document": row["ai_output_document"],
                    "output_checksum": row["ai_output_checksum"],
                    "model_id": row["ai_model_id"],
                    "requested_by": row["ai_requested_by"],
                    "created_at": row["ai_created_at"].isoformat(),
                    "updated_at": row["ai_updated_at"].isoformat(),
                }
            document["case_checksum"] = str(row["case_checksum"])
            document["ai_draft"] = ai_draft
            document = _derived_certification_view(
                document,
                certification_policy,
                decision_rows,
            )
            current_verdict = row["current_verdict"]
            if current_verdict is None:
                review_status = "pending"
            elif current_verdict == "comparable":
                review_status = "approved"
            elif current_verdict == "not_comparable":
                review_status = "rejected"
            else:
                review_status = "flagged"
            snapshots.append(
                {
                    **document,
                    "review_case_id": str(row["review_case_id"]),
                    "case_checksum": str(row["case_checksum"]),
                    "review_status": review_status,
                    "ai_draft": ai_draft,
                    "ai_output_checksum": str(row["ai_output_checksum"] or ""),
                }
            )
        queue_version = str(rows[0]["queue_version"])
        _apply_observed_location_sidecar(
            snapshots,
            queue_id=external_queue_id,
            queue_version=queue_version,
            root=_repository_root(),
        )
        return str(rows[0]["review_queue_id"]), queue_version, snapshots

    async def preview_ai_bulk_certification(
        self,
        external_queue_id: str,
        external_case_ids: Sequence[str],
    ) -> dict[str, Any]:
        async with self._engine.connect() as connection:
            _, queue_version, snapshots = await self._bulk_ai_snapshot(
                connection,
                external_queue_id,
                external_case_ids,
                lock_cases=False,
            )
        return _bulk_preview_document(
            queue_id=external_queue_id,
            queue_version=queue_version,
            snapshots=snapshots,
        )

    async def commit_ai_bulk_certification(
        self,
        external_queue_id: str,
        external_case_ids: Sequence[str],
        *,
        reviewer_id: str,
        confirmation_checksum: str,
    ) -> dict[str, Any]:
        idempotency_key = _checksum(
            {
                "queue_id": external_queue_id,
                "reviewer_id": reviewer_id,
                "confirmation_checksum": confirmation_checksum,
            }
        )
        async with self._engine.begin() as connection:
            existing = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT id::text, case_ids, case_count, audit_document, created_at
                            FROM matching_v2_bulk_certification_action
                            WHERE idempotency_key = :idempotency_key
                            """
                        ),
                        {"idempotency_key": idempotency_key},
                    )
                )
                .mappings()
                .first()
            )
            if existing is not None:
                existing_audit = existing["audit_document"]
                existing_audit = existing_audit if isinstance(existing_audit, Mapping) else {}
                existing_cases = existing_audit.get("cases", [])
                existing_cases = existing_cases if isinstance(existing_cases, list) else []
                not_comparable_count = sum(
                    1
                    for candidate in existing_cases
                    if isinstance(candidate, Mapping)
                    and candidate.get("recommended_verdict") == "not_comparable"
                )
                comparable_count = int(existing["case_count"]) - not_comparable_count
                return {
                    "action_id": str(existing["id"]),
                    "queue_id": external_queue_id,
                    "certified_case_ids": list(existing["case_ids"]),
                    "certified_case_count": int(existing["case_count"]),
                    "comparable_case_count": comparable_count,
                    "not_comparable_case_count": not_comparable_count,
                    # Compatibility aliases for a web/API rolling deployment.
                    "approved_case_ids": list(existing["case_ids"]),
                    "approved_case_count": int(existing["case_count"]),
                    "confirmation_checksum": confirmation_checksum,
                    "created_at": existing["created_at"].isoformat(),
                    "idempotent_replay": True,
                    "final_until_flagged": True,
                    "automatically_changes_reporting": False,
                }

            case_id_rows = list(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT review_case.id::text
                            FROM matching_v2_review_case review_case
                            JOIN matching_v2_review_queue review_queue
                              ON review_queue.id = review_case.review_queue_id
                            WHERE review_queue.external_queue_id = :queue_id
                              AND review_case.external_case_id = ANY(CAST(:case_ids AS text[]))
                            ORDER BY review_case.id
                            """
                        ),
                        {
                            "queue_id": external_queue_id,
                            "case_ids": list(external_case_ids),
                        },
                    )
                )
                .scalars()
                .all()
            )
            for review_case_id in case_id_rows:
                await connection.execute(
                    text("SELECT pg_advisory_xact_lock(hashtextextended(:case_id, 0))"),
                    {"case_id": str(review_case_id)},
                )

            review_queue_id, queue_version, snapshots = await self._bulk_ai_snapshot(
                connection,
                external_queue_id,
                external_case_ids,
                lock_cases=True,
            )
            preview = _bulk_preview_document(
                queue_id=external_queue_id,
                queue_version=queue_version,
                snapshots=snapshots,
            )
            if preview["excluded_case_count"]:
                excluded = ", ".join(
                    f"{candidate['case_id']} ({', '.join(candidate['reason_codes'])})"
                    for candidate in preview["excluded_cases"]
                )
                raise ValueError(
                    "bulk certification stopped because one or more cases changed or no "
                    f"longer pass policy: {excluded}"
                )
            current_checksum = str(preview["confirmation_checksum"] or "")
            if not secrets.compare_digest(current_checksum, confirmation_checksum):
                raise ValueError(
                    "bulk certification preview is stale; assess the recommendations again"
                )

            policy = _ai_bulk_certification_policy()
            audit_document = {
                "schema_version": "1.1.0-ai-bulk-certification-action",
                "queue_id": external_queue_id,
                "queue_version": queue_version,
                "reviewer_id": reviewer_id,
                "policy": policy,
                "confirmation_checksum": confirmation_checksum,
                "cases": [
                    {
                        "case_id": candidate["case_id"],
                        "case_checksum": candidate["case_checksum"],
                        "certification_view_checksum": candidate["certification_view_checksum"],
                        "ai_task_id": candidate["ai_task_id"],
                        "ai_output_checksum": candidate["ai_output_checksum"],
                        "recommended_verdict": candidate["recommended_verdict"],
                        "recommended_tier": candidate["recommended_tier"],
                        "recommended_comparison_bases": candidate["recommended_comparison_bases"],
                    }
                    for candidate in preview["eligible_cases"]
                ],
                "human_confirmation_required": True,
                "final_until_flagged": True,
                "automatically_changes_reporting": False,
            }
            action = (
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO matching_v2_bulk_certification_action (
                              review_queue_id, reviewer_id, action_type, policy_id,
                              policy_version, policy_checksum, confirmation_checksum,
                              idempotency_key, case_ids, case_count, audit_document
                            ) VALUES (
                              CAST(:review_queue_id AS uuid), :reviewer_id,
                              'certify_ai_recommendations', :policy_id, :policy_version,
                              :policy_checksum, :confirmation_checksum, :idempotency_key,
                              :case_ids, :case_count, CAST(:audit_document AS jsonb)
                            )
                            RETURNING id::text, created_at
                            """
                        ),
                        {
                            "review_queue_id": review_queue_id,
                            "reviewer_id": reviewer_id,
                            "policy_id": policy["id"],
                            "policy_version": policy["version"],
                            "policy_checksum": policy["checksum"],
                            "confirmation_checksum": confirmation_checksum,
                            "idempotency_key": idempotency_key,
                            "case_ids": list(external_case_ids),
                            "case_count": len(external_case_ids),
                            "audit_document": _canonical(audit_document),
                        },
                    )
                )
                .mappings()
                .one()
            )
            action_id = str(action["id"])
            snapshots_by_case = {str(row["case_id"]): row for row in snapshots}
            preview_by_case = {str(row["case_id"]): row for row in preview["eligible_cases"]}
            decisions: list[dict[str, Any]] = []
            for external_case_id in external_case_ids:
                snapshot = snapshots_by_case[external_case_id]
                candidate = preview_by_case[external_case_id]
                ai_reference = (
                    f"matching-v2-ai-review://{candidate['ai_task_id']}"
                    f"#sha256={candidate['ai_output_checksum']}"
                )
                evidence_refs = _certification_evidence_refs(
                    snapshot,
                    [*snapshot.get("evidence_refs", []), ai_reference],
                )
                recommended_verdict = str(candidate["recommended_verdict"])
                allowed_tiers = (
                    [candidate["recommended_tier"]] if recommended_verdict == "comparable" else []
                )
                certified_outcome = (
                    f"comparable at {candidate['recommended_tier']} using "
                    f"{', '.join(candidate['recommended_comparison_bases'])}"
                    if recommended_verdict == "comparable"
                    else "not comparable"
                )
                rationale = (
                    f"Administrator bulk-certified this AI recommendation as {certified_outcome} "
                    "after the "
                    f"{policy['id']} v{policy['version']} preview passed every required gate. "
                    + (
                        "Advisory warnings acknowledged: " + "; ".join(candidate["warnings"]) + ". "
                        if candidate["warnings"]
                        else ""
                    )
                    + f"AI evidence rationale: {candidate['ai_rationale']}"
                )
                submission_checksum = _checksum(
                    {
                        "queue_id": external_queue_id,
                        "case_id": external_case_id,
                        "reviewer_id": reviewer_id,
                        "verdict": recommended_verdict,
                        "allowed_tiers": allowed_tiers,
                        "rationale": rationale,
                        "evidence_refs": evidence_refs,
                        "bulk_action_id": action_id,
                    }
                )
                submission = (
                    (
                        await connection.execute(
                            text(
                                """
                                INSERT INTO matching_v2_review_submission (
                                  review_case_id, reviewer_id, verdict, allowed_tiers,
                                  rationale, evidence_refs, submission_checksum,
                                  supersedes_submission_id, bulk_action_id
                                ) VALUES (
                                  CAST(:review_case_id AS uuid), :reviewer_id,
                                  :verdict, :allowed_tiers, :rationale,
                                  CAST(:evidence_refs AS jsonb), :submission_checksum,
                                  NULL, CAST(:bulk_action_id AS uuid)
                                )
                                RETURNING id::text, created_at
                                """
                            ),
                            {
                                "review_case_id": snapshot["review_case_id"],
                                "reviewer_id": reviewer_id,
                                "verdict": recommended_verdict,
                                "allowed_tiers": allowed_tiers,
                                "rationale": rationale,
                                "evidence_refs": _canonical(evidence_refs),
                                "submission_checksum": submission_checksum,
                                "bulk_action_id": action_id,
                            },
                        )
                    )
                    .mappings()
                    .one()
                )
                decisions.append(
                    {
                        "case_id": external_case_id,
                        "submission_id": str(submission["id"]),
                        "verdict": recommended_verdict,
                        "tier": candidate["recommended_tier"],
                        "created_at": submission["created_at"].isoformat(),
                    }
                )
        comparable_case_count = sum(
            1 for decision in decisions if decision["verdict"] == "comparable"
        )
        not_comparable_case_count = len(decisions) - comparable_case_count
        return {
            "action_id": action_id,
            "queue_id": external_queue_id,
            "certified_case_ids": list(external_case_ids),
            "certified_case_count": len(external_case_ids),
            "comparable_case_count": comparable_case_count,
            "not_comparable_case_count": not_comparable_case_count,
            # Compatibility aliases for a web/API rolling deployment.
            "approved_case_ids": list(external_case_ids),
            "approved_case_count": len(external_case_ids),
            "confirmation_checksum": confirmation_checksum,
            "decisions": decisions,
            "created_at": action["created_at"].isoformat(),
            "idempotent_replay": False,
            "final_until_flagged": True,
            "automatically_changes_reporting": False,
        }

    async def request_ai_draft(
        self,
        external_queue_id: str,
        external_case_id: str,
        *,
        requested_by: str,
        model_id: str,
        prompt: Mapping[str, str],
    ) -> dict[str, Any]:
        tasks = await self.request_ai_drafts(
            external_queue_id,
            [external_case_id],
            requested_by=requested_by,
            model_id=model_id,
            prompt=prompt,
        )
        return tasks[0]

    async def eligible_ai_review_cases(
        self,
        external_queue_id: str,
        *,
        competitor_retailer_id: str | None,
        selection_mode: AIReviewSelectionMode,
        limit: int,
    ) -> dict[str, Any]:
        """Return a lightweight, exposure-ranked scope for a paid AI review run."""

        async with self._engine.connect() as connection:
            rows = list(
                (
                    await connection.execute(
                        text(
                            """
                            WITH selected_queue AS (
                              SELECT id, version, product_pack_id
                              FROM matching_v2_review_queue
                              WHERE external_queue_id = :queue_id
                              ORDER BY created_at DESC
                              LIMIT 1
                            )
                            SELECT c.external_case_id, c.case_document, c.case_checksum,
                                   q.id::text AS review_queue_id,
                                   q.version AS queue_version,
                                   q.product_pack_id,
                                   latest_task.input_checksum AS latest_ai_input_checksum,
                                   latest_task.status AS latest_ai_status,
                                   (
                                     SELECT count(*)
                                     FROM matching_v2_ai_review_task active_task
                                     WHERE active_task.review_case_id = c.id
                                       AND active_task.status IN ('queued', 'running')
                                   ) AS active_ai_task_count
                            FROM matching_v2_review_case c
                            JOIN selected_queue q ON q.id = c.review_queue_id
                            LEFT JOIN LATERAL (
                              SELECT task.input_checksum, task.status
                              FROM matching_v2_ai_review_task task
                              WHERE task.review_case_id = c.id
                              ORDER BY task.created_at DESC, task.id DESC
                              LIMIT 1
                            ) latest_task ON true
                            LEFT JOIN LATERAL (
                              SELECT decision.verdict
                              FROM (
                                SELECT s.verdict, s.created_at, s.id
                                FROM matching_v2_review_submission s
                                WHERE s.review_case_id = c.id
                                UNION ALL
                                SELECT a.verdict, a.created_at, a.id
                                FROM matching_v2_adjudication a
                                WHERE a.review_case_id = c.id
                              ) decision
                              ORDER BY decision.created_at DESC, decision.id DESC
                              LIMIT 1
                            ) current_decision ON true
                            WHERE (CAST(:competitor_retailer_id AS text) IS NULL
                                   OR c.competitor_retailer_id =
                                      CAST(:competitor_retailer_id AS text))
                              AND coalesce(current_decision.verdict, 'pending')
                                  NOT IN ('comparable', 'not_comparable')
                            """
                        ),
                        {
                            "queue_id": external_queue_id,
                            "competitor_retailer_id": competitor_retailer_id,
                        },
                    )
                )
                .mappings()
                .all()
            )
        if not rows:
            # Distinguish an empty eligible scope from an unknown queue.
            async with self._engine.connect() as connection:
                queue_exists = (
                    await connection.execute(
                        text(
                            """
                            SELECT 1
                            FROM matching_v2_review_queue
                            WHERE external_queue_id = :queue_id
                            LIMIT 1
                            """
                        ),
                        {"queue_id": external_queue_id},
                    )
                ).scalar_one_or_none()
            if queue_exists is None:
                raise KeyError(f"matching v2 review queue {external_queue_id!r} was not found")
            return {
                "queue_id": external_queue_id,
                "competitor_retailer_id": competitor_retailer_id,
                "selection_mode": selection_mode,
                "eligible_case_count": 0,
                "selected_case_count": 0,
                "deferred_case_count": 0,
                "unresolved_product_evidence_count": 0,
                "selected_product_evidence_count": 0,
                "case_ids": [],
            }
        documents = []
        for row in rows:
            document = dict(row["case_document"])
            document["case_checksum"] = str(row["case_checksum"])
            documents.append(document)
        _apply_observed_location_sidecar(
            documents,
            queue_id=external_queue_id,
            queue_version=str(rows[0]["queue_version"]),
            root=_repository_root(),
        )
        async with self._engine.connect() as connection:
            evidence_decisions = await self._queue_attribute_decision_rows(
                connection, str(rows[0]["review_queue_id"])
            )
        certification_policy = _active_certification_policy(str(rows[0]["product_pack_id"]))
        documents = [
            _derived_certification_view(document, certification_policy, evidence_decisions)
            for document in documents
        ]
        row_by_case = {str(row["external_case_id"]): row for row in rows}
        documents = [
            document
            for document in documents
            if int(row_by_case[str(document["case_id"])]["active_ai_task_count"] or 0) == 0
            and str(row_by_case[str(document["case_id"])]["latest_ai_input_checksum"] or "")
            != _checksum(document)
        ]
        documents = [
            document for document in documents if not _case_has_known_third_party_seller(document)
        ]
        incomplete_footprints = [
            str(document.get("case_id") or "")
            for document in documents
            if not _has_complete_observed_location_evidence(document)
        ]
        if incomplete_footprints:
            raise ValueError(
                "AI review scope has incomplete Search-derived observed-location evidence: "
                f"{incomplete_footprints[:10]!r}"
            )
        documents.sort(key=_case_order_key)
        evidence_product_count = len(
            set().union(*(_missing_evidence_listing_ids(document) for document in documents))
        )
        selected: Sequence[Mapping[str, Any]]
        if selection_mode == "product_evidence_coverage":
            selected, evidence_product_count = _product_evidence_coverage_selection(
                documents, limit=limit
            )
        else:
            selected = documents[:limit]
        return {
            "queue_id": external_queue_id,
            "competitor_retailer_id": competitor_retailer_id,
            "selection_mode": selection_mode,
            "eligible_case_count": len(documents),
            "selected_case_count": len(selected),
            "deferred_case_count": max(0, len(documents) - len(selected)),
            "unresolved_product_evidence_count": evidence_product_count,
            "selected_product_evidence_count": len(
                set().union(*(_missing_evidence_listing_ids(document) for document in selected))
            ),
            "case_ids": [str(document["case_id"]) for document in selected],
        }

    async def request_ai_drafts(
        self,
        external_queue_id: str,
        external_case_ids: Sequence[str],
        *,
        requested_by: str,
        model_id: str,
        prompt: Mapping[str, str],
    ) -> list[dict[str, Any]]:
        async with self._engine.begin() as connection:
            rows = list(
                (
                    await connection.execute(
                        text(
                            """
                            WITH selected_queue AS (
                              SELECT id, version, product_pack_id
                              FROM matching_v2_review_queue
                              WHERE external_queue_id = :queue_id
                              ORDER BY created_at DESC
                              LIMIT 1
                            )
                            SELECT c.id::text, c.external_case_id, c.case_document,
                                   c.case_checksum, c.review_queue_id::text,
                                   q.version AS queue_version,
                                   q.product_pack_id,
                                   (
                                     SELECT count(*)
                                     FROM matching_v2_ai_review_task active_task
                                     WHERE active_task.review_case_id = c.id
                                       AND active_task.status IN ('queued', 'running')
                                   ) AS active_ai_task_count,
                                   (
                                     SELECT decision.verdict
                                     FROM (
                                       SELECT s.verdict, s.created_at, s.id
                                       FROM matching_v2_review_submission s
                                       WHERE s.review_case_id = c.id
                                       UNION ALL
                                       SELECT a.verdict, a.created_at, a.id
                                       FROM matching_v2_adjudication a
                                       WHERE a.review_case_id = c.id
                                     ) decision
                                     ORDER BY decision.created_at DESC, decision.id DESC
                                     LIMIT 1
                                   ) AS current_verdict
                            FROM matching_v2_review_case c
                            JOIN selected_queue q ON q.id = c.review_queue_id
                            WHERE c.external_case_id = ANY(CAST(:case_ids AS text[]))
                            """
                        ),
                        {"queue_id": external_queue_id, "case_ids": list(external_case_ids)},
                    )
                )
                .mappings()
                .all()
            )
            rows_by_case = {str(row["external_case_id"]): row for row in rows}
            missing = [case_id for case_id in external_case_ids if case_id not in rows_by_case]
            if missing:
                raise KeyError(
                    f"matching v2 review cases {missing!r} were not found in queue "
                    f"{external_queue_id!r}"
                )
            sidecar_documents = {
                case_id: {
                    **dict(rows_by_case[case_id]["case_document"]),
                    "case_checksum": str(rows_by_case[case_id]["case_checksum"]),
                }
                for case_id in external_case_ids
            }
            _apply_observed_location_sidecar(
                list(sidecar_documents.values()),
                queue_id=external_queue_id,
                queue_version=str(rows[0]["queue_version"]),
                root=_repository_root(),
            )
            certification_policy = _active_certification_policy(str(rows[0]["product_pack_id"]))
            evidence_decisions = await self._queue_attribute_decision_rows(
                connection, str(rows[0]["review_queue_id"])
            )
            sidecar_documents = {
                case_id: _derived_certification_view(
                    document, certification_policy, evidence_decisions
                )
                for case_id, document in sidecar_documents.items()
            }
            excluded_seller_cases = [
                case_id
                for case_id in external_case_ids
                if _case_has_known_third_party_seller(sidecar_documents[case_id])
            ]
            if excluded_seller_cases:
                raise ValueError(
                    "known third-party marketplace seller cases cannot request AI drafts: "
                    f"{excluded_seller_cases!r}"
                )
            incomplete_footprints = [
                case_id
                for case_id in external_case_ids
                if not _has_complete_observed_location_evidence(sidecar_documents[case_id])
            ]
            if incomplete_footprints:
                raise ValueError(
                    "AI review requires nonzero Search-derived observed-location evidence: "
                    f"{incomplete_footprints!r}"
                )
            finalized = [
                case_id
                for case_id in external_case_ids
                if rows_by_case[case_id]["current_verdict"] in {"comparable", "not_comparable"}
            ]
            if finalized:
                raise ValueError(f"finalized review cases cannot request AI drafts: {finalized!r}")
            active = [
                case_id
                for case_id in external_case_ids
                if int(rows_by_case[case_id]["active_ai_task_count"] or 0) > 0
            ]
            if active:
                raise ValueError(f"review cases already have active AI tasks: {active!r}")
            batch = await self._insert_ai_review_batch(
                connection,
                review_queue_id=str(rows[0]["review_queue_id"]),
                external_case_ids=external_case_ids,
                requested_by=requested_by,
                model_id=model_id,
                prompt=prompt,
                idempotency_context=_checksum(
                    {
                        case_id: sidecar_documents[case_id]["certification_view_checksum"]
                        for case_id in sorted(external_case_ids)
                    }
                ),
            )
            tasks = [
                await self._insert_ai_draft_task(
                    connection,
                    {
                        **dict(rows_by_case[case_id]),
                        "case_document": sidecar_documents[case_id],
                    },
                    batch_id=str(batch["id"]),
                    requested_by=requested_by,
                    model_id=model_id,
                    prompt=prompt,
                )
                for case_id in external_case_ids
            ]
            if any(str(task["batch_id"]) != str(batch["id"]) for task in tasks):
                raise ValueError(
                    "one or more selected cases already belong to a different AI review batch"
                )
        return tasks

    async def retry_ai_drafts(
        self,
        external_queue_id: str,
        external_case_ids: Sequence[str],
        *,
        requested_by: str,
        model_id: str,
        prompt: Mapping[str, str],
        retry_reason: str,
    ) -> list[dict[str, Any]]:
        """Create new linked tasks for terminal failures without rewriting history."""

        async with self._engine.begin() as connection:
            for external_case_id in sorted(external_case_ids):
                await connection.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                    {"lock_key": f"matching-v2-ai-retry:{external_queue_id}:{external_case_id}"},
                )
            rows = list(
                (
                    await connection.execute(
                        text(
                            """
                            WITH selected_queue AS (
                              SELECT id, version, product_pack_id
                              FROM matching_v2_review_queue
                              WHERE external_queue_id = :queue_id
                              ORDER BY created_at DESC
                              LIMIT 1
                            )
                            SELECT c.id::text, c.external_case_id, c.case_document,
                                   c.case_checksum, c.review_queue_id::text,
                                   q.version AS queue_version,
                                   q.product_pack_id,
                                   (
                                     SELECT decision.verdict
                                     FROM (
                                       SELECT s.verdict, s.created_at, s.id
                                       FROM matching_v2_review_submission s
                                       WHERE s.review_case_id = c.id
                                       UNION ALL
                                       SELECT a.verdict, a.created_at, a.id
                                       FROM matching_v2_adjudication a
                                       WHERE a.review_case_id = c.id
                                     ) decision
                                     ORDER BY decision.created_at DESC, decision.id DESC
                                     LIMIT 1
                                   ) AS current_verdict,
                                   latest_task.id::text AS ai_task_id,
                                   latest_task.status AS ai_status,
                                   latest_task.input_document AS ai_input_document,
                                   latest_task.input_checksum AS ai_input_checksum,
                                   latest_task.retry_sequence AS ai_retry_sequence,
                                   latest_task.attempt_count AS ai_attempt_count,
                                   latest_task.max_attempts AS ai_max_attempts,
                                   latest_task.usage AS ai_usage,
                                   latest_task.last_error_type AS ai_last_error_type,
                                   latest_task.last_error_message AS ai_last_error_message,
                                   (
                                     SELECT count(*)
                                     FROM matching_v2_ai_review_task active_task
                                     WHERE active_task.review_case_id = c.id
                                       AND active_task.status IN ('queued', 'running')
                                   ) AS active_ai_task_count
                            FROM matching_v2_review_case c
                            JOIN selected_queue q ON q.id = c.review_queue_id
                            LEFT JOIN LATERAL (
                              SELECT task.*
                              FROM matching_v2_ai_review_task task
                              WHERE task.review_case_id = c.id
                              ORDER BY task.created_at DESC, task.id DESC
                              LIMIT 1
                            ) latest_task ON true
                            WHERE c.external_case_id = ANY(CAST(:case_ids AS text[]))
                            FOR UPDATE OF c
                            """
                        ),
                        {"queue_id": external_queue_id, "case_ids": list(external_case_ids)},
                    )
                )
                .mappings()
                .all()
            )
            if not rows:
                raise KeyError(f"matching v2 review queue {external_queue_id!r} was not found")
            rows_by_case = {str(row["external_case_id"]): row for row in rows}
            missing = [case_id for case_id in external_case_ids if case_id not in rows_by_case]
            if missing:
                raise KeyError(
                    f"matching v2 review cases {missing!r} were not found in queue "
                    f"{external_queue_id!r}"
                )
            sidecar_documents = {
                case_id: {
                    **dict(rows_by_case[case_id]["case_document"]),
                    "case_checksum": str(rows_by_case[case_id]["case_checksum"]),
                }
                for case_id in external_case_ids
            }
            _apply_observed_location_sidecar(
                list(sidecar_documents.values()),
                queue_id=external_queue_id,
                queue_version=str(rows[0]["queue_version"]),
                root=_repository_root(),
            )
            certification_policy = _active_certification_policy(str(rows[0]["product_pack_id"]))
            evidence_decisions = await self._queue_attribute_decision_rows(
                connection, str(rows[0]["review_queue_id"])
            )
            sidecar_documents = {
                case_id: _derived_certification_view(
                    document, certification_policy, evidence_decisions
                )
                for case_id, document in sidecar_documents.items()
            }
            excluded_seller_cases = [
                case_id
                for case_id in external_case_ids
                if _case_has_known_third_party_seller(sidecar_documents[case_id])
            ]
            if excluded_seller_cases:
                raise ValueError(
                    "known third-party marketplace seller cases cannot retry AI drafts: "
                    f"{excluded_seller_cases!r}"
                )
            incomplete_footprints = [
                case_id
                for case_id in external_case_ids
                if not _has_complete_observed_location_evidence(sidecar_documents[case_id])
            ]
            if incomplete_footprints:
                raise ValueError(
                    "AI review retry requires nonzero Search-derived observed-location evidence: "
                    f"{incomplete_footprints!r}"
                )
            finalized = [
                case_id
                for case_id in external_case_ids
                if rows_by_case[case_id]["current_verdict"] in {"comparable", "not_comparable"}
            ]
            if finalized:
                raise ValueError(f"finalized review cases cannot retry AI drafts: {finalized!r}")
            without_terminal_failure = [
                case_id
                for case_id in external_case_ids
                if rows_by_case[case_id]["ai_task_id"] is None
                or rows_by_case[case_id]["ai_status"] != "needs_review"
                or int(rows_by_case[case_id]["active_ai_task_count"] or 0) > 0
            ]
            if without_terminal_failure:
                raise ValueError(
                    "AI retries require the latest task to be a terminal needs-review failure "
                    f"with no active task: {without_terminal_failure!r}"
                )
            exhausted = [
                case_id
                for case_id in external_case_ids
                if int(rows_by_case[case_id]["ai_retry_sequence"] or 0) >= _MAX_AI_RETRY_ROUNDS
            ]
            if exhausted:
                raise ValueError(
                    f"AI retry limit of {_MAX_AI_RETRY_ROUNDS} rounds reached: {exhausted!r}"
                )
            integrity_failures = [
                case_id
                for case_id in external_case_ids
                if _is_ai_retry_integrity_failure(rows_by_case[case_id]["ai_last_error_message"])
            ]
            if integrity_failures:
                raise ValueError(
                    "governed input or prompt integrity failures require engineering review, "
                    f"not another paid AI call: {integrity_failures!r}"
                )
            retry_context = _checksum(
                {
                    "operation": "retry",
                    "prior_task_ids": sorted(
                        str(rows_by_case[case_id]["ai_task_id"]) for case_id in external_case_ids
                    ),
                }
            )
            batch = await self._insert_ai_review_batch(
                connection,
                review_queue_id=str(rows[0]["review_queue_id"]),
                external_case_ids=external_case_ids,
                requested_by=requested_by,
                model_id=model_id,
                prompt=prompt,
                idempotency_context=retry_context,
            )
            tasks = [
                await self._insert_ai_retry_task(
                    connection,
                    dict(rows_by_case[case_id]),
                    batch_id=str(batch["id"]),
                    requested_by=requested_by,
                    model_id=model_id,
                    prompt=prompt,
                    retry_reason=retry_reason,
                    certification_policy=certification_policy,
                    certification_input_document=sidecar_documents[case_id],
                )
                for case_id in external_case_ids
            ]
        return tasks

    @staticmethod
    async def _insert_ai_review_batch(
        connection: AsyncConnection,
        *,
        review_queue_id: str,
        external_case_ids: Sequence[str],
        requested_by: str,
        model_id: str,
        prompt: Mapping[str, str],
        idempotency_context: str | None = None,
    ) -> dict[str, Any]:
        idempotency_document = {
            "review_queue_id": review_queue_id,
            "case_ids": sorted(external_case_ids),
            "model_id": model_id,
            "prompt_checksum": prompt["checksum"],
        }
        if idempotency_context is not None:
            idempotency_document["context"] = idempotency_context
        idempotency_key = _checksum(idempotency_document)
        row = (
            (
                await connection.execute(
                    text(
                        """
                        INSERT INTO matching_v2_ai_review_batch (
                          review_queue_id, idempotency_key, requested_by,
                          model_provider, model_id, prompt_id, prompt_version,
                          prompt_checksum, requested_case_count
                        ) VALUES (
                          CAST(:review_queue_id AS uuid), :idempotency_key,
                          :requested_by, 'openai', :model_id, :prompt_id,
                          :prompt_version, :prompt_checksum, :requested_case_count
                        )
                        ON CONFLICT (idempotency_key) DO UPDATE SET
                          updated_at = matching_v2_ai_review_batch.updated_at
                        RETURNING id::text, created_at, requested_case_count
                        """
                    ),
                    {
                        "review_queue_id": review_queue_id,
                        "idempotency_key": idempotency_key,
                        "requested_by": requested_by,
                        "model_id": model_id,
                        "prompt_id": prompt["id"],
                        "prompt_version": prompt["version"],
                        "prompt_checksum": prompt["checksum"],
                        "requested_case_count": len(external_case_ids),
                    },
                )
            )
            .mappings()
            .one()
        )
        return dict(row)

    @staticmethod
    async def _insert_ai_retry_task(
        connection: AsyncConnection,
        row: Mapping[str, Any],
        *,
        batch_id: str,
        requested_by: str,
        model_id: str,
        prompt: Mapping[str, str],
        retry_reason: str,
        certification_policy: Mapping[str, Any],
        certification_input_document: Mapping[str, Any],
    ) -> dict[str, Any]:
        stored_input_document = dict(row["ai_input_document"])
        stored_input_checksum = _checksum(stored_input_document)
        if stored_input_checksum != str(row["ai_input_checksum"]):
            raise ValueError(
                f"stored AI input checksum is invalid for case {row['external_case_id']!r}"
            )
        input_document = dict(certification_input_document)
        if str(input_document.get("certification_policy", {}).get("policy_checksum") or "") != str(
            certification_policy.get("policy_checksum") or ""
        ):
            raise ValueError("AI retry certification input does not use the active Product Pack")
        input_checksum = _checksum(input_document)
        retry_sequence = int(row["ai_retry_sequence"] or 0) + 1
        idempotency_key = _checksum(
            {
                "operation": "retry",
                "retry_of_task_id": str(row["ai_task_id"]),
                "retry_sequence": retry_sequence,
                "model_id": model_id,
                "prompt_checksum": prompt["checksum"],
                "input_checksum": input_checksum,
            }
        )
        task = (
            (
                await connection.execute(
                    text(
                        """
                        INSERT INTO matching_v2_ai_review_task (
                          review_case_id, batch_id, idempotency_key, requested_by, status,
                          prompt_id, prompt_version, prompt_checksum,
                          model_provider, model_id, input_checksum, input_document,
                          retry_of_task_id, retry_sequence, retry_reason
                        ) VALUES (
                          CAST(:review_case_id AS uuid), CAST(:batch_id AS uuid),
                          :idempotency_key, :requested_by, 'queued',
                          :prompt_id, :prompt_version, :prompt_checksum,
                          'openai', :model_id, :input_checksum, CAST(:input_document AS jsonb),
                          CAST(:retry_of_task_id AS uuid), :retry_sequence, :retry_reason
                        )
                        RETURNING id::text, batch_id::text, status, model_provider, model_id,
                                  prompt_id, prompt_version, input_checksum,
                                  attempt_count, max_attempts, retry_of_task_id::text,
                                  retry_sequence, retry_reason, created_at
                        """
                    ),
                    {
                        "review_case_id": str(row["id"]),
                        "batch_id": batch_id,
                        "idempotency_key": idempotency_key,
                        "requested_by": requested_by,
                        "prompt_id": prompt["id"],
                        "prompt_version": prompt["version"],
                        "prompt_checksum": prompt["checksum"],
                        "model_id": model_id,
                        "input_checksum": input_checksum,
                        "input_document": _canonical(input_document),
                        "retry_of_task_id": str(row["ai_task_id"]),
                        "retry_sequence": retry_sequence,
                        "retry_reason": retry_reason,
                    },
                )
            )
            .mappings()
            .one()
        )
        return {
            **{
                key: (value.isoformat() if hasattr(value, "isoformat") else value)
                for key, value in task.items()
            },
            "case_id": str(row["external_case_id"]),
            "previous_attempt_count": int(row["ai_attempt_count"] or 0),
            "previous_max_attempts": int(row["ai_max_attempts"] or 0),
            "previous_usage": dict(row["ai_usage"] or {}),
            "previous_error_type": row["ai_last_error_type"],
            "previous_error_message": row["ai_last_error_message"],
            "authoritative": False,
            "human_review_required": True,
        }

    @staticmethod
    async def _insert_ai_draft_task(
        connection: AsyncConnection,
        row: Mapping[str, Any],
        *,
        batch_id: str,
        requested_by: str,
        model_id: str,
        prompt: Mapping[str, str],
    ) -> dict[str, Any]:
        input_document = dict(row["case_document"])
        input_checksum = _checksum(input_document)
        idempotency_key = _checksum(
            {
                "review_case_id": str(row["id"]),
                "case_checksum": str(row["case_checksum"]),
                "model_id": model_id,
                "prompt_checksum": prompt["checksum"],
                "input_checksum": input_checksum,
            }
        )
        task = (
            (
                await connection.execute(
                    text(
                        """
                        INSERT INTO matching_v2_ai_review_task (
                          review_case_id, batch_id, idempotency_key, requested_by, status,
                          prompt_id, prompt_version, prompt_checksum,
                          model_provider, model_id, input_checksum, input_document
                        ) VALUES (
                          CAST(:review_case_id AS uuid), CAST(:batch_id AS uuid),
                          :idempotency_key, :requested_by,
                          'queued', :prompt_id, :prompt_version, :prompt_checksum,
                          'openai', :model_id, :input_checksum,
                          CAST(:input_document AS jsonb)
                        )
                        ON CONFLICT (idempotency_key) DO UPDATE SET
                          requested_by = matching_v2_ai_review_task.requested_by
                        RETURNING id::text, batch_id::text, status, model_provider, model_id,
                                  prompt_id, prompt_version, input_checksum,
                                  attempt_count, max_attempts, created_at
                        """
                    ),
                    {
                        "review_case_id": str(row["id"]),
                        "batch_id": batch_id,
                        "idempotency_key": idempotency_key,
                        "requested_by": requested_by,
                        "prompt_id": prompt["id"],
                        "prompt_version": prompt["version"],
                        "prompt_checksum": prompt["checksum"],
                        "model_id": model_id,
                        "input_checksum": input_checksum,
                        "input_document": _canonical(input_document),
                    },
                )
            )
            .mappings()
            .one()
        )
        return {
            **{
                key: (value.isoformat() if hasattr(value, "isoformat") else value)
                for key, value in task.items()
            },
            "authoritative": False,
            "human_review_required": True,
        }

    async def decide_attribute_evidence(
        self,
        external_queue_id: str,
        external_case_id: str,
        decision: Mapping[str, Any],
        *,
        decision_checksum: str,
    ) -> dict[str, Any]:
        async with self._engine.begin() as connection:
            case_id = await self._case_id(connection, external_queue_id, external_case_id)
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:case_id, 0))"),
                {"case_id": case_id},
            )
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT review_case.case_document, review_case.case_checksum,
                                   review_queue.product_pack_id,
                                   (
                                     SELECT current_decision.verdict
                                     FROM (
                                       SELECT submission.verdict, submission.created_at,
                                              submission.id
                                       FROM matching_v2_review_submission submission
                                       WHERE submission.review_case_id = review_case.id
                                       UNION ALL
                                       SELECT adjudication.verdict, adjudication.created_at,
                                              adjudication.id
                                       FROM matching_v2_adjudication adjudication
                                       WHERE adjudication.review_case_id = review_case.id
                                     ) current_decision
                                     ORDER BY current_decision.created_at DESC,
                                              current_decision.id DESC
                                     LIMIT 1
                                   ) AS current_verdict
                            FROM matching_v2_review_case review_case
                            JOIN matching_v2_review_queue review_queue
                              ON review_queue.id = review_case.review_queue_id
                            WHERE review_case.id = CAST(:case_id AS uuid)
                            """
                        ),
                        {"case_id": case_id},
                    )
                )
                .mappings()
                .one()
            )
            if row["current_verdict"] in {"comparable", "not_comparable"}:
                raise ValueError(
                    "attribute evidence must be reconciled before final match certification"
                )
            ai_rows = await self._ai_draft_rows(connection, [case_id])
            if not ai_rows:
                raise ValueError("the case has no AI evidence proposal to reconcile")
            ai = dict(ai_rows[0])
            ai_draft = {
                key: (value.isoformat() if hasattr(value, "isoformat") else value)
                for key, value in ai.items()
                if key != "review_case_id"
            }
            document = {
                **dict(row["case_document"]),
                "case_checksum": str(row["case_checksum"]),
                "ai_draft": ai_draft,
            }
            policy = _active_certification_policy(str(row["product_pack_id"]))
            proposal = next(
                (
                    value
                    for value in _reconciliation_proposals(document, policy)
                    if value["proposal_checksum"] == decision["proposal_checksum"]
                ),
                None,
            )
            if proposal is None:
                raise ValueError(
                    "the proposal is not part of the latest checksum-bound AI evidence output"
                )
            if not proposal["eligible"]:
                raise ValueError(
                    "the proposal is not eligible for governed reconciliation: "
                    + ", ".join(proposal["ineligibility_reasons"])
                )
            supersedes = decision.get("supersedes_decision_id")
            if supersedes:
                prior = (
                    (
                        await connection.execute(
                            text(
                                """
                                SELECT id::text
                                FROM matching_v2_attribute_evidence_decision
                                WHERE id = CAST(:decision_id AS uuid)
                                  AND review_case_id = CAST(:case_id AS uuid)
                                  AND proposal_checksum = :proposal_checksum
                                """
                            ),
                            {
                                "decision_id": supersedes,
                                "case_id": case_id,
                                "proposal_checksum": decision["proposal_checksum"],
                            },
                        )
                    )
                    .mappings()
                    .first()
                )
                if prior is None:
                    raise ValueError("the superseded evidence decision was not found")
            existing = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT id::text, created_at
                            FROM matching_v2_attribute_evidence_decision
                            WHERE decision_checksum = :checksum
                            """
                        ),
                        {"checksum": decision_checksum},
                    )
                )
                .mappings()
                .first()
            )
            if existing is not None:
                return {
                    "id": str(existing["id"]),
                    "queue_id": external_queue_id,
                    "case_id": external_case_id,
                    "checksum": decision_checksum,
                    "created_at": existing["created_at"].isoformat(),
                }
            inserted = (
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO matching_v2_attribute_evidence_decision (
                              review_case_id, ai_review_task_id, proposal_checksum,
                              proposal_document, decision, reviewer_id, rationale,
                              decision_checksum, supersedes_decision_id
                            ) VALUES (
                              CAST(:case_id AS uuid), CAST(:ai_task_id AS uuid),
                              :proposal_checksum, CAST(:proposal_document AS jsonb),
                              :decision, :reviewer_id, :rationale, :decision_checksum,
                              CAST(:supersedes_decision_id AS uuid)
                            )
                            RETURNING id::text, created_at
                            """
                        ),
                        {
                            "case_id": case_id,
                            "ai_task_id": proposal["ai_task_id"],
                            "proposal_checksum": proposal["proposal_checksum"],
                            "proposal_document": _canonical(
                                {
                                    **proposal,
                                    **(
                                        {"claim_decision": decision["claim_decision"]}
                                        if isinstance(decision.get("claim_decision"), Mapping)
                                        else {}
                                    ),
                                }
                            ),
                            "decision": decision["decision"],
                            "reviewer_id": decision["reviewer_id"],
                            "rationale": decision["rationale"],
                            "decision_checksum": decision_checksum,
                            "supersedes_decision_id": supersedes,
                        },
                    )
                )
                .mappings()
                .one()
            )
        return {
            "id": str(inserted["id"]),
            "queue_id": external_queue_id,
            "case_id": external_case_id,
            "proposal_checksum": proposal["proposal_checksum"],
            "decision": decision["decision"],
            "checksum": decision_checksum,
            "created_at": inserted["created_at"].isoformat(),
            "raw_evidence_mutated": False,
        }

    async def submit_review(
        self,
        external_queue_id: str,
        external_case_id: str,
        submission: Mapping[str, Any],
        *,
        submission_checksum: str,
    ) -> dict[str, Any]:
        async with self._engine.begin() as connection:
            case_id = await self._case_id(connection, external_queue_id, external_case_id)
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:case_id, 0))"),
                {"case_id": case_id},
            )
            case_row = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT review_case.case_document, review_case.case_checksum,
                               review_queue.id::text AS review_queue_id,
                               review_queue.version,
                               review_queue.product_pack_id
                        FROM matching_v2_review_case review_case
                        JOIN matching_v2_review_queue review_queue
                          ON review_queue.id = review_case.review_queue_id
                        WHERE review_case.id = CAST(:case_id AS uuid)
                        """
                        ),
                        {"case_id": case_id},
                    )
                )
                .mappings()
                .one()
            )
            case_document = dict(case_row["case_document"])
            case_document["case_checksum"] = str(case_row["case_checksum"])
            _apply_observed_location_sidecar(
                [case_document],
                queue_id=external_queue_id,
                queue_version=str(case_row["version"]),
                root=_repository_root(),
            )
            if _case_has_known_third_party_seller(case_document):
                raise ValueError("a known third-party marketplace seller case cannot be certified")
            ai_rows = await self._ai_draft_rows(connection, [case_id])
            if ai_rows:
                case_document["ai_draft"] = {
                    key: (value.isoformat() if hasattr(value, "isoformat") else value)
                    for key, value in ai_rows[0].items()
                    if key != "review_case_id"
                }
            decisions = await self._queue_attribute_decision_rows(
                connection, str(case_row["review_queue_id"])
            )
            policy = _active_certification_policy(str(case_row["product_pack_id"]))
            case_document = _derived_certification_view(case_document, policy, decisions)
            submission = dict(submission)
            submission["evidence_refs"] = _certification_evidence_refs(
                case_document, submission.get("evidence_refs") or []
            )
            submission_checksum = _checksum(
                {
                    "queue_id": external_queue_id,
                    "case_id": external_case_id,
                    **submission,
                }
            )
            certification_blockers = case_document.get("certification_blockers")
            if submission["verdict"] == "comparable" and certification_blockers:
                blocked_attributes = ", ".join(
                    str(issue.get("attribute") or "unknown")
                    for issue in certification_blockers
                    if isinstance(issue, Mapping)
                )
                raise ValueError(
                    "a comparable decision cannot be certified while current Product Pack "
                    f"hard blockers conflict or are unresolved: {blocked_attributes}"
                )
            disallowed_tiers = _disallowed_certification_tiers(
                submission["allowed_tiers"], case_document
            )
            if submission["verdict"] == "comparable" and disallowed_tiers:
                raise ValueError(
                    "a comparable decision cannot use relationship tiers prohibited by the "
                    f"current Product Pack: {', '.join(disallowed_tiers)}"
                )
            existing = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT id::text, created_at
                            FROM matching_v2_review_submission
                            WHERE submission_checksum = :checksum
                            """
                        ),
                        {"checksum": submission_checksum},
                    )
                )
                .mappings()
                .first()
            )
            if existing is not None:
                return {
                    "id": str(existing["id"]),
                    "queue_id": external_queue_id,
                    "case_id": external_case_id,
                    "checksum": submission_checksum,
                    "created_at": existing["created_at"].isoformat(),
                }
            current_decision = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT decision.verdict
                            FROM (
                              SELECT verdict, created_at, id
                              FROM matching_v2_review_submission
                              WHERE review_case_id = CAST(:case_id AS uuid)
                              UNION ALL
                              SELECT verdict, created_at, id
                              FROM matching_v2_adjudication
                              WHERE review_case_id = CAST(:case_id AS uuid)
                            ) decision
                            ORDER BY decision.created_at DESC, decision.id DESC
                            LIMIT 1
                            """
                        ),
                        {"case_id": case_id},
                    )
                )
                .mappings()
                .first()
            )
            if (
                current_decision is not None
                and current_decision["verdict"] in {"comparable", "not_comparable"}
                and submission["verdict"] != "insufficient_evidence"
            ):
                raise ValueError(
                    "a finalized review case must be flagged before its decision can change"
                )
            supersedes_submission_id = submission.get("supersedes_submission_id")
            if supersedes_submission_id is not None:
                superseded = (
                    (
                        await connection.execute(
                            text(
                                """
                                SELECT id::text
                                FROM matching_v2_review_submission
                                WHERE id = CAST(:submission_id AS uuid)
                                  AND review_case_id = CAST(:case_id AS uuid)
                                """
                            ),
                            {
                                "submission_id": supersedes_submission_id,
                                "case_id": case_id,
                            },
                        )
                    )
                    .mappings()
                    .first()
                )
                if superseded is None:
                    raise ValueError("a superseded review must belong to the same case")
            row = (
                (
                    await connection.execute(
                        text(
                            """
                        INSERT INTO matching_v2_review_submission (
                          review_case_id, reviewer_id, verdict, allowed_tiers,
                          rationale, evidence_refs, submission_checksum,
                          supersedes_submission_id
                        ) VALUES (
                          CAST(:case_id AS uuid), :reviewer_id, :verdict, :allowed_tiers,
                          :rationale, CAST(:evidence_refs AS jsonb), :submission_checksum,
                          CAST(:supersedes_submission_id AS uuid)
                        )
                        ON CONFLICT (submission_checksum) DO NOTHING
                        RETURNING id::text, created_at
                        """
                        ),
                        {
                            "case_id": case_id,
                            "reviewer_id": submission["reviewer_id"],
                            "verdict": submission["verdict"],
                            "allowed_tiers": list(submission["allowed_tiers"]),
                            "rationale": submission["rationale"],
                            "evidence_refs": _canonical(submission["evidence_refs"]),
                            "submission_checksum": submission_checksum,
                            "supersedes_submission_id": supersedes_submission_id,
                        },
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                row = (
                    (
                        await connection.execute(
                            text(
                                """
                            SELECT id::text, created_at
                            FROM matching_v2_review_submission
                            WHERE submission_checksum = :checksum
                            """
                            ),
                            {"checksum": submission_checksum},
                        )
                    )
                    .mappings()
                    .one()
                )
        return {
            "id": str(row["id"]),
            "queue_id": external_queue_id,
            "case_id": external_case_id,
            "checksum": submission_checksum,
            "created_at": row["created_at"].isoformat(),
        }

    async def adjudicate(
        self,
        external_queue_id: str,
        external_case_id: str,
        adjudication: Mapping[str, Any],
        *,
        adjudication_checksum: str,
    ) -> dict[str, Any]:
        submission_ids = list(adjudication["submission_ids"])
        async with self._engine.begin() as connection:
            case_id = await self._case_id(connection, external_queue_id, external_case_id)
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:case_id, 0))"),
                {"case_id": case_id},
            )
            case_row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT review_case.case_document, review_case.case_checksum,
                                   review_queue.id::text AS review_queue_id,
                                   review_queue.version,
                                   review_queue.product_pack_id
                            FROM matching_v2_review_case review_case
                            JOIN matching_v2_review_queue review_queue
                              ON review_queue.id = review_case.review_queue_id
                            WHERE review_case.id = CAST(:case_id AS uuid)
                            """
                        ),
                        {"case_id": case_id},
                    )
                )
                .mappings()
                .one()
            )
            case_document = dict(case_row["case_document"])
            case_document["case_checksum"] = str(case_row["case_checksum"])
            _apply_observed_location_sidecar(
                [case_document],
                queue_id=external_queue_id,
                queue_version=str(case_row["version"]),
                root=_repository_root(),
            )
            ai_rows = await self._ai_draft_rows(connection, [case_id])
            if ai_rows:
                case_document["ai_draft"] = {
                    key: (value.isoformat() if hasattr(value, "isoformat") else value)
                    for key, value in ai_rows[0].items()
                    if key != "review_case_id"
                }
            decisions = await self._queue_attribute_decision_rows(
                connection, str(case_row["review_queue_id"])
            )
            policy = _active_certification_policy(str(case_row["product_pack_id"]))
            case_document = _derived_certification_view(case_document, policy, decisions)
            adjudication = dict(adjudication)
            adjudication["evidence_refs"] = _certification_evidence_refs(
                case_document, adjudication.get("evidence_refs") or []
            )
            adjudication_checksum = _checksum(
                {
                    "queue_id": external_queue_id,
                    "case_id": external_case_id,
                    **adjudication,
                }
            )
            certification_blockers = case_document.get("certification_blockers")
            if adjudication["verdict"] == "comparable" and certification_blockers:
                blocked_attributes = ", ".join(
                    str(issue.get("attribute") or "unknown")
                    for issue in certification_blockers
                    if isinstance(issue, Mapping)
                )
                raise ValueError(
                    "a comparable adjudication cannot be certified while current Product Pack "
                    f"hard blockers conflict or are unresolved: {blocked_attributes}"
                )
            disallowed_tiers = _disallowed_certification_tiers(
                adjudication["allowed_tiers"], case_document
            )
            if adjudication["verdict"] == "comparable" and disallowed_tiers:
                raise ValueError(
                    "a comparable adjudication cannot use relationship tiers prohibited by the "
                    f"current Product Pack: {', '.join(disallowed_tiers)}"
                )
            submissions = list(
                (
                    await connection.execute(
                        text(
                            """
                            WITH latest AS (
                              SELECT DISTINCT ON (reviewer_id) id, reviewer_id
                              FROM matching_v2_review_submission
                              WHERE review_case_id = CAST(:case_id AS uuid)
                              ORDER BY reviewer_id, created_at DESC, id DESC
                            )
                            SELECT id::text, reviewer_id
                            FROM latest
                            WHERE id = ANY(CAST(:submission_ids AS uuid[]))
                            """
                        ),
                        {"case_id": case_id, "submission_ids": submission_ids},
                    )
                ).mappings()
            )
            if len(submissions) != len(set(submission_ids)):
                raise ValueError(
                    "every adjudication submission must be the current review for its "
                    "reviewer and belong to the case"
                )
            if len({str(row["reviewer_id"]) for row in submissions}) < 2:
                raise ValueError("adjudication requires two independent reviewers")
            existing_adjudication_id = await connection.scalar(
                text(
                    """
                    SELECT id::text
                    FROM matching_v2_adjudication
                    WHERE review_case_id = CAST(:case_id AS uuid)
                    ORDER BY created_at DESC, id DESC
                    LIMIT 1
                    """
                ),
                {"case_id": case_id},
            )
            supersedes_adjudication_id = adjudication.get("supersedes_adjudication_id")
            if existing_adjudication_id is None and supersedes_adjudication_id is not None:
                raise ValueError("there is no prior adjudication to supersede")
            if existing_adjudication_id is not None and str(existing_adjudication_id) != str(
                supersedes_adjudication_id
            ):
                raise ValueError(
                    "a replacement adjudication must supersede the latest case adjudication"
                )
            row = (
                (
                    await connection.execute(
                        text(
                            """
                        INSERT INTO matching_v2_adjudication (
                          review_case_id, adjudicator_id, verdict, allowed_tiers,
                          rationale, evidence_refs, adjudication_checksum,
                          supersedes_adjudication_id
                        ) VALUES (
                          CAST(:case_id AS uuid), :adjudicator_id, :verdict, :allowed_tiers,
                          :rationale, CAST(:evidence_refs AS jsonb), :adjudication_checksum,
                          CAST(:supersedes_adjudication_id AS uuid)
                        )
                        ON CONFLICT (adjudication_checksum) DO NOTHING
                        RETURNING id::text, created_at
                        """
                        ),
                        {
                            "case_id": case_id,
                            "adjudicator_id": adjudication["adjudicator_id"],
                            "verdict": adjudication["verdict"],
                            "allowed_tiers": list(adjudication["allowed_tiers"]),
                            "rationale": adjudication["rationale"],
                            "evidence_refs": _canonical(adjudication["evidence_refs"]),
                            "adjudication_checksum": adjudication_checksum,
                            "supersedes_adjudication_id": supersedes_adjudication_id,
                        },
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                row = (
                    (
                        await connection.execute(
                            text(
                                """
                            SELECT id::text, created_at
                            FROM matching_v2_adjudication
                            WHERE adjudication_checksum = :checksum
                            """
                            ),
                            {"checksum": adjudication_checksum},
                        )
                    )
                    .mappings()
                    .one()
                )
            for submission_id in sorted(set(submission_ids)):
                await connection.execute(
                    text(
                        """
                        INSERT INTO matching_v2_adjudication_submission (
                          adjudication_id, submission_id
                        ) VALUES (CAST(:adjudication_id AS uuid), CAST(:submission_id AS uuid))
                        ON CONFLICT DO NOTHING
                        """
                    ),
                    {"adjudication_id": row["id"], "submission_id": submission_id},
                )
        return {
            "id": str(row["id"]),
            "queue_id": external_queue_id,
            "case_id": external_case_id,
            "checksum": adjudication_checksum,
            "created_at": row["created_at"].isoformat(),
        }

    async def create_gold_set_replay(
        self,
        external_queue_id: str,
        gold_set: Mapping[str, Any],
        *,
        document_checksum: str,
        released_by: str,
        source_analysis_id: str,
        force_rebuild: bool,
        rebuild_reason: str | None,
    ) -> dict[str, Any]:
        labels = list(gold_set.get("labels", []))
        exclusions = list(gold_set.get("exclusions", []))
        label_case_ids = {str(label.get("case_id") or "") for label in labels}
        exclusion_case_ids = {str(exclusion.get("case_id") or "") for exclusion in exclusions}
        if "" in label_case_ids or "" in exclusion_case_ids:
            raise ValueError("matching v2 release entries require a case id")
        if len(label_case_ids) != len(labels) or len(exclusion_case_ids) != len(exclusions):
            raise ValueError("matching v2 release contains duplicate case entries")
        if label_case_ids & exclusion_case_ids:
            raise ValueError("a matching v2 case cannot be both certified and excluded")
        async with self._engine.begin() as connection:
            queue = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT q.id::text, q.organization_id::text, q.version,
                               q.product_pack_id, q.product_pack_version,
                               q.sampling, q.document->>'purpose' AS queue_purpose,
                               count(c.id)::integer AS queue_case_count
                        FROM matching_v2_review_queue q
                        JOIN matching_v2_review_case c ON c.review_queue_id = q.id
                        WHERE q.external_queue_id = :queue_id
                        GROUP BY q.id
                        ORDER BY q.created_at DESC
                        LIMIT 1
                        """
                        ),
                        {"queue_id": external_queue_id},
                    )
                )
                .mappings()
                .first()
            )
            if queue is None:
                raise KeyError(f"matching v2 review queue {external_queue_id!r} was not found")
            queue_cases = [
                dict(row)
                for row in (
                    await connection.execute(
                        text(
                            """
                            SELECT review_case.external_case_id AS case_id,
                                   review_case.competitor_retailer_id,
                                   current_decision.verdict AS final_verdict
                            FROM matching_v2_review_case review_case
                            LEFT JOIN LATERAL (
                              SELECT decision.verdict
                              FROM (
                                SELECT submission.verdict, submission.created_at,
                                       submission.id
                                FROM matching_v2_review_submission submission
                                WHERE submission.review_case_id = review_case.id
                                UNION ALL
                                SELECT adjudication.verdict, adjudication.created_at,
                                       adjudication.id
                                FROM matching_v2_adjudication adjudication
                                WHERE adjudication.review_case_id = review_case.id
                              ) decision
                              ORDER BY decision.created_at DESC, decision.id DESC
                              LIMIT 1
                            ) current_decision ON true
                            WHERE review_case.review_queue_id = CAST(:review_queue_id AS uuid)
                            ORDER BY review_case.competitor_retailer_id,
                                     review_case.external_case_id
                            """
                        ),
                        {"review_queue_id": queue["id"]},
                    )
                )
                .mappings()
                .all()
            ]
            if len(queue_cases) != int(queue["queue_case_count"]):
                raise ValueError("matching v2 queue counts changed while creating its release")
            current_insufficient_case_ids = {
                str(case["case_id"])
                for case in queue_cases
                if str(case.get("final_verdict") or "") == "insufficient_evidence"
            }
            if exclusion_case_ids != current_insufficient_case_ids:
                raise ValueError(
                    "matching v2 insufficient-evidence decisions changed while creating its release"
                )
            source = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT result.id::text AS result_id, run.collection_run_id::text,
                               run.input_set_id::text, run.product_pack_id,
                               run.product_pack_version, run.code_version, run.max_attempts
                        FROM analysis_result result
                        JOIN analysis_run run ON run.id = result.analysis_run_id
                        WHERE result.result->>'analysis_id' = :analysis_id
                          AND (result.archived_at IS NULL OR :include_archived_source)
                        ORDER BY result.created_at DESC
                        LIMIT 1
                        """
                        ),
                        {
                            "analysis_id": source_analysis_id,
                            "include_archived_source": force_rebuild,
                        },
                    )
                )
                .mappings()
                .first()
            )
            if source is None:
                raise KeyError(f"source analysis {source_analysis_id!r} was not found")
            if str(source["product_pack_id"]) != str(queue["product_pack_id"]):
                raise ValueError(
                    "source analysis category does not match the certified review queue: "
                    f"{source['product_pack_id']!r} != {queue['product_pack_id']!r}"
                )
            sampling = queue.get("sampling")
            coverage = _matching_v2_certification_coverage(
                labels,
                queue_cases,
                sampling=sampling if isinstance(sampling, Mapping) else None,
            )
            if not coverage["selection_complete"]:
                raise ValueError(
                    "a sampled Matching v2 validation queue cannot drive an operational "
                    "report release; regenerate an exhaustive operational certification queue"
                )
            if str(queue["queue_purpose"] or "") != "operational_match_certification":
                raise ValueError(
                    "only an operational Matching v2 certification queue can drive a report "
                    "release; validation gold sets remain model-quality evidence"
                )
            if not isinstance(sampling, Mapping) or str(sampling.get("method") or "") != (
                "exhaustive_governed_candidates"
            ):
                raise ValueError(
                    "operational Matching v2 reporting requires an exhaustive governed-candidate "
                    "queue"
                )
            release = (
                (
                    await connection.execute(
                        text(
                            """
                        INSERT INTO matching_v2_gold_set_release (
                          organization_id, review_queue_id, external_gold_set_id, version,
                          product_pack_id, product_pack_version, document, coverage,
                          document_checksum, released_by
                        ) VALUES (
                          CAST(:organization_id AS uuid), CAST(:review_queue_id AS uuid),
                          :gold_set_id, :version, :product_pack_id, :product_pack_version,
                          CAST(:document AS jsonb), CAST(:coverage AS jsonb), :checksum,
                          :released_by
                        )
                        ON CONFLICT (review_queue_id, document_checksum)
                        DO UPDATE SET released_by = matching_v2_gold_set_release.released_by
                        RETURNING id::text, created_at
                        """
                        ),
                        {
                            "organization_id": queue["organization_id"],
                            "review_queue_id": queue["id"],
                            "gold_set_id": gold_set["gold_set_id"],
                            "version": gold_set["version"],
                            "product_pack_id": queue["product_pack_id"],
                            "product_pack_version": queue["product_pack_version"],
                            "document": _canonical(gold_set),
                            "coverage": _canonical(coverage),
                            "checksum": document_checksum,
                            "released_by": released_by,
                        },
                    )
                )
                .mappings()
                .one()
            )
            replay_identity = (
                f"{source['collection_run_id']}:{queue['product_pack_id']}:"
                f"{queue['product_pack_version']}:{release['id']}"
            )
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:identity, 0))"),
                {"identity": replay_identity},
            )
            replay_generation = 1
            if force_rebuild:
                replay_generation = int(
                    (
                        await connection.scalar(
                            text(
                                """
                                SELECT coalesce(max(replay_generation), 0) + 1
                                FROM analysis_run
                                WHERE collection_run_id = CAST(:collection_run_id AS uuid)
                                  AND product_pack_id = :product_pack_id
                                  AND product_pack_version = :product_pack_version
                                  AND match_revision_id IS NULL
                                  AND brand_revision_id IS NULL
                                  AND matching_v2_gold_set_release_id = CAST(:release_id AS uuid)
                                """
                            ),
                            {
                                "collection_run_id": source["collection_run_id"],
                                "product_pack_id": queue["product_pack_id"],
                                "product_pack_version": queue["product_pack_version"],
                                "release_id": release["id"],
                            },
                        )
                    )
                    or 1
                )
            run = (
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO analysis_run (
                              collection_run_id, input_set_id, product_pack_id,
                              product_pack_version, status, code_version, max_attempts,
                              source_analysis_result_id, matching_v2_gold_set_release_id,
                              replay_generation, replay_reason
                            ) VALUES (
                              CAST(:collection_run_id AS uuid), CAST(:input_set_id AS uuid),
                              :product_pack_id, :product_pack_version, 'queued', :code_version,
                              :max_attempts, CAST(:source_result_id AS uuid),
                              CAST(:release_id AS uuid), :replay_generation, :replay_reason
                            )
                            ON CONFLICT DO NOTHING
                            RETURNING id::text, status
                            """
                        ),
                        {
                            **dict(source),
                            "product_pack_id": queue["product_pack_id"],
                            "product_pack_version": queue["product_pack_version"],
                            "source_result_id": source["result_id"],
                            "release_id": release["id"],
                            "replay_generation": replay_generation,
                            "replay_reason": rebuild_reason,
                        },
                    )
                )
                .mappings()
                .first()
            )
            if run is None:
                run = (
                    (
                        await connection.execute(
                            text(
                                """
                            SELECT id::text, status FROM analysis_run
                            WHERE collection_run_id = CAST(:collection_run_id AS uuid)
                              AND product_pack_id = :product_pack_id
                              AND product_pack_version = :product_pack_version
                              AND match_revision_id IS NULL
                              AND brand_revision_id IS NULL
                              AND matching_v2_gold_set_release_id = CAST(:release_id AS uuid)
                              AND replay_generation = :replay_generation
                            """
                            ),
                            {
                                "collection_run_id": source["collection_run_id"],
                                "product_pack_id": queue["product_pack_id"],
                                "product_pack_version": queue["product_pack_version"],
                                "release_id": release["id"],
                                "replay_generation": replay_generation,
                            },
                        )
                    )
                    .mappings()
                    .one()
                )
        return {
            "gold_set_release_id": str(release["id"]),
            "gold_set_checksum": document_checksum,
            "analysis_run_id": str(run["id"]),
            "analysis_status": str(run["status"]),
            "replay_generation": replay_generation,
            "rebuild_reason": rebuild_reason,
            "coverage": coverage,
        }

    @staticmethod
    async def _case_id(
        connection: AsyncConnection,
        external_queue_id: str,
        external_case_id: str,
    ) -> str:
        row = (
            (
                await connection.execute(
                    text(
                        """
                    SELECT c.id::text
                    FROM matching_v2_review_case c
                    JOIN matching_v2_review_queue q ON q.id = c.review_queue_id
                    WHERE q.external_queue_id = :queue_id
                      AND c.external_case_id = :case_id
                    ORDER BY q.created_at DESC
                    LIMIT 1
                    """
                    ),
                    {"queue_id": external_queue_id, "case_id": external_case_id},
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise KeyError(
                f"matching v2 review case {external_case_id!r} was not found "
                f"in queue {external_queue_id!r}"
            )
        return str(row["id"])


class MatchingV2ReviewService:
    def __init__(self, repository: MatchingV2ReviewRepository, repository_root: Path) -> None:
        self._repository = repository
        self._root = repository_root

    async def list_queues(self, *, limit: int) -> dict[str, Any]:
        queues = await self._repository.list_queues(limit=limit)
        for queue in queues:
            if not isinstance(queue, dict):
                continue
            queue["quarantine"] = _review_queue_quarantine(
                self._root,
                str(queue.get("queue_id") or queue.get("external_queue_id") or ""),
                str(queue.get("version") or ""),
            )
        return {
            "schema_version": "2.0.0-review-queue-index",
            "authoritative": False,
            "queues": queues,
        }

    async def import_queue(self, request: ImportReviewQueueRequest) -> dict[str, Any]:
        if request.queue_json is not None:
            try:
                queue = json.loads(request.queue_json)
            except json.JSONDecodeError as exc:
                raise ValueError("review queue JSON is invalid") from exc
            if not isinstance(queue, dict):
                raise ValueError("review queue JSON must contain an object")
        elif request.queue is not None:
            queue = request.queue
        else:
            raise ValueError("review queue import requires queue_json or queue")
        try:
            validate_instance(
                self._root,
                "matching-v2-review-queue.schema.json",
                queue,
                label="matching v2 review queue import",
            )
        except ContractError as exc:
            raise ValueError(str(exc)) from exc
        expected_checksum = str(queue["checksum"])
        unsigned = dict(queue)
        unsigned.pop("checksum", None)
        if _checksum(unsigned) != expected_checksum:
            raise ValueError("review queue checksum does not match its canonical document")
        excluded_seller_cases = [
            str(case.get("case_id") or "")
            for case in queue["cases"]
            if _case_has_known_third_party_seller(case)
        ]
        if excluded_seller_cases:
            raise ValueError(
                "review queue contains known third-party marketplace seller cases: "
                f"{excluded_seller_cases!r}"
            )
        if (
            request.carry_forward_certified
            and request.successor_of_version
            and _review_queue_quarantine(
                self._root,
                str(queue.get("queue_id") or ""),
                request.successor_of_version,
            )
        ):
            raise ValueError(
                "certified decisions cannot be carried forward from a quarantined Matching v2 queue"
            )
        return await self._repository.import_queue(
            request.organization_id,
            queue,
            imported_by=request.imported_by,
            successor_of_version=request.successor_of_version,
            carry_forward_certified=request.carry_forward_certified,
            carry_forward_attribute_evidence=request.carry_forward_attribute_evidence,
            scope_only_pack_revision=request.scope_only_pack_revision,
        )

    async def queue_view(self, external_queue_id: str, **filters: Any) -> dict[str, Any]:
        document = await self._repository.queue_view(external_queue_id, **filters)
        queue = document.get("queue")
        queue = queue if isinstance(queue, Mapping) else {}
        product_pack = queue.get("product_pack")
        product_pack = product_pack if isinstance(product_pack, Mapping) else {}
        product_pack_id = str(product_pack.get("id") or "")
        if not product_pack_id:
            raise ValueError("matching v2 review queue does not identify its Product Pack")
        certification_policy = _active_certification_policy(product_pack_id)
        cases = document.get("cases")
        cases = cases if isinstance(cases, list) else []
        reconciled_cases: list[Any] = []
        for case in cases:
            if not isinstance(case, Mapping):
                reconciled_cases.append(case)
                continue
            decisions = case.get("attribute_evidence_decisions")
            decisions = decisions if isinstance(decisions, list) else []
            reconciled_cases.append(
                _derived_certification_view(case, certification_policy, decisions)
            )
        document["cases"] = reconciled_cases
        document["certification_policy"] = certification_policy
        document["quarantine"] = _review_queue_quarantine(
            self._root,
            external_queue_id,
            str(queue.get("version") or ""),
        )
        document["certification_blocker_summary"] = {
            "visible_case_count": len(document["cases"]),
            "blocked_case_count": sum(
                1 for case in document["cases"] if case.get("certification_release_blocked")
            ),
            "finalized_comparable_case_count": sum(
                1
                for case in document["cases"]
                if case.get("review_status") == "approved"
                and case.get("certification_release_blocked")
            ),
        }
        return document

    async def attribute_evidence_proposals(
        self,
        external_queue_id: str,
        *,
        competitor_retailer_id: str | None,
        batch_scope: AttributeEvidenceBatchScope,
        root_batch_id: str | None,
        eligibility: AttributeEvidenceEligibility,
        decision_status: AttributeEvidenceDecisionStatus,
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        queue_view = await self.queue_view(
            external_queue_id,
            competitor_retailer_id=competitor_retailer_id,
            benchmark_product_id=None,
            competitor_product_id=None,
            stratum=None,
            review_status=None,
            offset=0,
            limit=100_000,
        )
        return _attribute_evidence_proposal_index(
            queue_view,
            batch_scope=batch_scope,
            root_batch_id=root_batch_id,
            eligibility=eligibility,
            decision_status=decision_status,
            offset=offset,
            limit=limit,
        )

    async def attribute_evidence_claims(
        self,
        external_queue_id: str,
        *,
        competitor_retailer_id: str | None,
        batch_scope: AttributeEvidenceBatchScope,
        root_batch_id: str | None,
        status_filter: AttributeEvidenceClaimStatus,
        attribute_filter: str | None,
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        queue_view = await self.queue_view(
            external_queue_id,
            competitor_retailer_id=competitor_retailer_id,
            benchmark_product_id=None,
            competitor_product_id=None,
            stratum=None,
            review_status=None,
            offset=0,
            limit=100_000,
        )
        return _attribute_evidence_claim_index(
            queue_view,
            batch_scope=batch_scope,
            root_batch_id=root_batch_id,
            status_filter=status_filter,
            attribute_filter=attribute_filter,
            offset=offset,
            limit=limit,
        )

    async def decide_attribute_evidence_claim(
        self,
        external_queue_id: str,
        request: AttributeEvidenceClaimDecisionRequest,
    ) -> dict[str, Any]:
        """Persist one checksum-bound decision for a complete product-attribute claim."""

        await self._assert_queue_not_quarantined(external_queue_id)
        view = await self.attribute_evidence_claims(
            external_queue_id,
            competitor_retailer_id=None,
            batch_scope=request.batch_scope,
            root_batch_id=request.root_batch_id,
            status_filter="all",
            attribute_filter=None,
            offset=0,
            limit=100_000,
        )
        claim = next(
            (
                row
                for row in view.get("claims") or []
                if isinstance(row, Mapping) and row.get("claim_checksum") == request.claim_checksum
            ),
            None,
        )
        if claim is None:
            raise ValueError(
                "the product-attribute claim is stale or outside the current AI evidence scope"
            )
        variants = claim.get("variants")
        variants = variants if isinstance(variants, list) else []
        selected_variant: Mapping[str, Any] | None = None
        if request.selected_proposal_checksum:
            selected_variant = next(
                (
                    variant
                    for variant in variants
                    if isinstance(variant, Mapping)
                    and variant.get("representative_proposal_checksum")
                    == request.selected_proposal_checksum
                ),
                None,
            )
            if selected_variant is None:
                raise ValueError("the selected value is not part of this checksum-bound claim")
        elif len(variants) == 1:
            selected_variant = variants[0] if isinstance(variants[0], Mapping) else None
        elif request.decision == "verified":
            raise ValueError("select one evidence value before verifying a conflicting claim")
        elif variants:
            selected_variant = variants[0] if isinstance(variants[0], Mapping) else None
        if selected_variant is None:
            raise ValueError("the claim has no eligible source-bound evidence variant")

        representative_case_id = str(selected_variant.get("representative_case_id") or "")
        representative_checksum = str(
            selected_variant.get("representative_proposal_checksum") or ""
        )
        if not representative_case_id or len(representative_checksum) != 64:
            raise ValueError("the claim lacks a valid representative proposal")
        claim_context = {
            "schema_version": "1.0.0-product-attribute-claim-decision",
            "claim_checksum": request.claim_checksum,
            "listing_id": str(claim.get("listing_id") or ""),
            "attribute": str(claim.get("attribute") or ""),
            "decision_scope": "complete_product_attribute_claim",
            "selected_value": selected_variant.get("value"),
            "selected_value_checksum": selected_variant.get("value_checksum"),
            "proposal_checksums": list(claim.get("proposal_checksums") or []),
            "variant_count": len(variants),
            "affected_case_count": int(claim.get("affected_case_count") or 0),
        }
        payload = {
            "reviewer_id": request.reviewer_id,
            "proposal_checksum": representative_checksum,
            "decision": request.decision,
            "rationale": request.rationale,
            "supersedes_decision_id": None,
            "claim_decision": claim_context,
        }
        decision_checksum = _checksum(
            {
                "schema_version": "1.0.0-product-attribute-claim-decision",
                "queue_id": external_queue_id,
                "case_id": representative_case_id,
                **payload,
            }
        )
        result = await self._repository.decide_attribute_evidence(
            external_queue_id,
            representative_case_id,
            payload,
            decision_checksum=decision_checksum,
        )
        return {
            **result,
            "claim_checksum": request.claim_checksum,
            "claim_status": request.decision,
            "listing_id": claim_context["listing_id"],
            "attribute": claim_context["attribute"],
            "selected_value": claim_context["selected_value"],
            "affected_case_count": claim_context["affected_case_count"],
            "raw_evidence_mutated": False,
            "automatically_certified_matches": 0,
        }

    async def _assert_queue_not_quarantined(self, external_queue_id: str) -> None:
        if not any(
            str(entry.get("queue_id") or "") == external_queue_id
            for entry in _review_queue_quarantines(self._root)
        ):
            return
        document = await self._repository.queue_view(
            external_queue_id,
            competitor_retailer_id=None,
            benchmark_product_id=None,
            competitor_product_id=None,
            stratum=None,
            review_status=None,
            offset=0,
            limit=0,
        )
        queue = document.get("queue")
        queue = queue if isinstance(queue, Mapping) else {}
        quarantine = _review_queue_quarantine(
            self._root,
            external_queue_id,
            str(queue.get("version") or ""),
        )
        if quarantine:
            raise ValueError(
                "this Matching v2 queue is quarantined and cannot accept AI work, "
                "certification, export, or replay: "
                f"{quarantine.get('reason') or 'trust reset required'!s}"
            )

    async def submit_review(
        self,
        external_queue_id: str,
        external_case_id: str,
        request: ReviewSubmissionRequest,
    ) -> dict[str, Any]:
        await self._assert_queue_not_quarantined(external_queue_id)
        self._validate_tiers(request.verdict, request.allowed_tiers)
        payload = request.model_dump(mode="json")
        checksum = _checksum(
            {"queue_id": external_queue_id, "case_id": external_case_id, **payload}
        )
        return await self._repository.submit_review(
            external_queue_id,
            external_case_id,
            payload,
            submission_checksum=checksum,
        )

    async def decide_attribute_evidence(
        self,
        external_queue_id: str,
        external_case_id: str,
        request: AttributeEvidenceDecisionRequest,
    ) -> dict[str, Any]:
        await self._assert_queue_not_quarantined(external_queue_id)
        payload = request.model_dump(mode="json")
        checksum = _checksum(
            {
                "schema_version": "1.0.0-attribute-evidence-decision",
                "queue_id": external_queue_id,
                "case_id": external_case_id,
                **payload,
            }
        )
        return await self._repository.decide_attribute_evidence(
            external_queue_id,
            external_case_id,
            payload,
            decision_checksum=checksum,
        )

    async def request_ai_draft(
        self,
        external_queue_id: str,
        external_case_id: str,
        request: AIReviewDraftRequest,
        *,
        model_id: str,
    ) -> dict[str, Any]:
        await self._assert_queue_not_quarantined(external_queue_id)
        prompt = self._matching_review_prompt()
        return await self._repository.request_ai_draft(
            external_queue_id,
            external_case_id,
            requested_by=request.requested_by,
            model_id=model_id,
            prompt=prompt,
        )

    async def request_ai_drafts(
        self,
        external_queue_id: str,
        request: AIReviewBatchRequest,
        *,
        model_id: str,
    ) -> dict[str, Any]:
        await self._assert_queue_not_quarantined(external_queue_id)
        case_ids = list(dict.fromkeys(request.case_ids))
        if len(case_ids) != len(request.case_ids):
            raise ValueError("AI draft batch case IDs must be unique")
        prompt = self._matching_review_prompt()
        tasks = await self._repository.request_ai_drafts(
            external_queue_id,
            case_ids,
            requested_by=request.requested_by,
            model_id=model_id,
            prompt=prompt,
        )
        return {
            "authoritative": False,
            "human_review_required": True,
            "queue_id": external_queue_id,
            "requested_case_count": len(case_ids),
            "batch": (
                {
                    "id": tasks[0]["batch_id"],
                    "created_at": tasks[0]["created_at"],
                    "requested_case_count": len(case_ids),
                }
                if tasks
                else None
            ),
            "tasks": tasks,
        }

    async def eligible_ai_review_cases(
        self,
        external_queue_id: str,
        *,
        competitor_retailer_id: str | None,
        selection_mode: AIReviewSelectionMode,
    ) -> dict[str, Any]:
        return await self._repository.eligible_ai_review_cases(
            external_queue_id,
            competitor_retailer_id=competitor_retailer_id,
            selection_mode=selection_mode,
            limit=_MAX_AI_REVIEW_BATCH_CASES,
        )

    async def retry_ai_drafts(
        self,
        external_queue_id: str,
        request: AIReviewRetryRequest,
        *,
        model_id: str,
    ) -> dict[str, Any]:
        await self._assert_queue_not_quarantined(external_queue_id)
        case_ids = list(dict.fromkeys(request.case_ids))
        if len(case_ids) != len(request.case_ids):
            raise ValueError("AI retry case IDs must be unique")
        prompt = self._matching_review_prompt()
        tasks = await self._repository.retry_ai_drafts(
            external_queue_id,
            case_ids,
            requested_by=request.requested_by,
            model_id=model_id,
            prompt=prompt,
            retry_reason=request.retry_reason,
        )
        return {
            "authoritative": False,
            "human_review_required": True,
            "history_preserved": True,
            "queue_id": external_queue_id,
            "requested_case_count": len(case_ids),
            "batch": (
                {
                    "id": tasks[0]["batch_id"],
                    "created_at": tasks[0]["created_at"],
                    "requested_case_count": len(case_ids),
                }
                if tasks
                else None
            ),
            "tasks": tasks,
        }

    async def preview_ai_bulk_certification(
        self,
        external_queue_id: str,
        request: AIBulkCertificationPreviewRequest,
    ) -> dict[str, Any]:
        await self._assert_queue_not_quarantined(external_queue_id)
        case_ids = list(dict.fromkeys(request.case_ids))
        if len(case_ids) != len(request.case_ids):
            raise ValueError("bulk certification case IDs must be unique")
        return await self._repository.preview_ai_bulk_certification(
            external_queue_id,
            case_ids,
        )

    async def commit_ai_bulk_certification(
        self,
        external_queue_id: str,
        request: AIBulkCertificationCommitRequest,
    ) -> dict[str, Any]:
        await self._assert_queue_not_quarantined(external_queue_id)
        case_ids = list(dict.fromkeys(request.case_ids))
        if len(case_ids) != len(request.case_ids):
            raise ValueError("bulk certification case IDs must be unique")
        return await self._repository.commit_ai_bulk_certification(
            external_queue_id,
            case_ids,
            reviewer_id=request.reviewer_id,
            confirmation_checksum=request.confirmation_checksum,
        )

    def _matching_review_prompt(self) -> dict[str, str]:
        path = self._root / "agent-prompts" / "matching_v2_evidence_review.json"
        body = path.read_bytes()
        document = json.loads(body)
        validate_instance(self._root, "agent-prompt.schema.json", document, label=str(path))
        if document["role"] != "matching_review":
            raise ValueError("matching review prompt has the wrong role")
        return {
            "id": str(document["id"]),
            "version": str(document["version"]),
            "checksum": hashlib.sha256(body).hexdigest(),
        }

    async def adjudicate(
        self,
        external_queue_id: str,
        external_case_id: str,
        request: AdjudicationRequest,
    ) -> dict[str, Any]:
        await self._assert_queue_not_quarantined(external_queue_id)
        self._validate_tiers(request.verdict, request.allowed_tiers)
        if len(set(request.submission_ids)) < 2:
            raise ValueError("adjudication requires two distinct submission IDs")
        payload = request.model_dump(mode="json")
        checksum = _checksum(
            {"queue_id": external_queue_id, "case_id": external_case_id, **payload}
        )
        return await self._repository.adjudicate(
            external_queue_id,
            external_case_id,
            payload,
            adjudication_checksum=checksum,
        )

    async def gold_set(self, external_queue_id: str) -> dict[str, Any]:
        await self._assert_queue_not_quarantined(external_queue_id)
        view = await self.queue_view(
            external_queue_id,
            competitor_retailer_id=None,
            benchmark_product_id=None,
            competitor_product_id=None,
            stratum=None,
            review_status=None,
            offset=0,
            limit=1_000_000,
        )
        labels: list[dict[str, Any]] = []
        exclusions: list[dict[str, Any]] = []
        for case in view["cases"]:
            decision = case.get("final_decision")
            if (
                case["review_status"] == "flagged"
                and decision is not None
                and decision.get("verdict") == "insufficient_evidence"
            ):
                linked = set(decision.get("submission_ids", []))
                reviews = (
                    [review for review in case["review_submissions"] if review["id"] in linked]
                    if linked
                    else [decision]
                )
                evidence_refs = sorted(
                    {
                        *case["evidence_refs"],
                        *decision["evidence_refs"],
                        *(reference for review in reviews for reference in review["evidence_refs"]),
                    }
                )
                legacy_adjudication = decision["source"] == "legacy_adjudication"
                exclusions.append(
                    {
                        "case_id": case["case_id"],
                        "benchmark_listing_id": case["benchmark_listing_id"],
                        "competitor_listing_id": case["competitor_listing_id"],
                        "reason": "insufficient_evidence",
                        "critical": case["critical"],
                        "stratum": case["stratum"],
                        "review_status": (
                            "adjudicated" if legacy_adjudication else "single_reviewed"
                        ),
                        "reviewers": sorted(
                            {
                                str(review.get("reviewer_id") or review.get("adjudicator_id"))
                                for review in reviews
                                if review.get("reviewer_id") or review.get("adjudicator_id")
                            }
                        ),
                        "evidence_refs": evidence_refs,
                        "rationale": decision["rationale"],
                    }
                )
                continue
            if case["review_status"] not in {"approved", "rejected"}:
                continue
            if case["review_status"] == "approved" and case.get("certification_release_blocked"):
                # A formerly approved comparable relationship is not exportable after a
                # stricter current Product Pack exposes a hard conflict or prohibited tier.
                continue
            decision = case["final_decision"]
            if decision is None:
                continue
            linked = set(decision.get("submission_ids", []))
            reviews = (
                [review for review in case["review_submissions"] if review["id"] in linked]
                if linked
                else [decision]
            )
            evidence_refs = sorted(
                {
                    *case["evidence_refs"],
                    *decision["evidence_refs"],
                    *(reference for review in reviews for reference in review["evidence_refs"]),
                }
            )
            legacy_adjudication = decision["source"] == "legacy_adjudication"
            labels.append(
                {
                    "case_id": case["case_id"],
                    "benchmark_listing_id": case["benchmark_listing_id"],
                    "competitor_listing_id": case["competitor_listing_id"],
                    "expected_comparable": decision["verdict"] == "comparable",
                    "allowed_tiers": list(decision["allowed_tiers"]),
                    "critical": case["critical"],
                    "stratum": case["stratum"],
                    "review_status": ("adjudicated" if legacy_adjudication else "single_reviewed"),
                    "reviewers": sorted(
                        {
                            str(review.get("reviewer_id") or review.get("adjudicator_id"))
                            for review in reviews
                            if review.get("reviewer_id") or review.get("adjudicator_id")
                        }
                    ),
                    "evidence_refs": evidence_refs,
                    "rationale": decision["rationale"],
                }
            )
        document = {
            "schema_version": "2.0.0",
            "coverage_contract_version": "1.0.0",
            "gold_set_id": f"{external_queue_id}-gold-set",
            "version": view["queue"]["version"],
            "purpose": "release_certification",
            "product_pack": view["queue"]["product_pack"],
            "source_evidence": sorted(
                {
                    reference
                    for item in [*labels, *exclusions]
                    for reference in item["evidence_refs"]
                }
            ),
            "labels": labels,
            "exclusions": exclusions,
        }
        if labels:
            validate_instance(
                self._root,
                "matching-v2-gold-set.schema.json",
                document,
                label="matching v2 certified gold set",
            )
        return document

    async def create_gold_set_replay(
        self,
        external_queue_id: str,
        request: GoldSetReplayRequest,
    ) -> dict[str, Any]:
        gold_set = await self.gold_set(external_queue_id)
        if not gold_set["labels"]:
            raise ValueError("a governed replay requires at least one certified label")
        return await self._repository.create_gold_set_replay(
            external_queue_id,
            gold_set,
            document_checksum=_checksum(gold_set),
            released_by=request.released_by,
            source_analysis_id=request.source_analysis_id,
            force_rebuild=request.force_rebuild,
            rebuild_reason=request.rebuild_reason,
        )

    @staticmethod
    def _validate_tiers(verdict: ReviewVerdict, tiers: Sequence[MatchTier]) -> None:
        if verdict == "comparable" and not tiers:
            raise ValueError("a comparable verdict requires at least one allowed tier")
        if verdict != "comparable" and tiers:
            raise ValueError("a non-comparable or insufficient verdict cannot allow tiers")


def _require_review_access(request: Request, provided_token: str | None) -> None:
    enabled = _enabled(
        os.getenv("MATCHING_V2_REVIEW_API_ENABLED"),
        default=not request.app.state.settings.is_production,
    )
    if not enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Matching v2 human review is not enabled.",
        )
    expected = os.getenv("PRODUCT_PACK_ADMIN_TOKEN")
    if request.app.state.settings.is_production and (
        not expected or not provided_token or not secrets.compare_digest(expected, provided_token)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated administrator access is required.",
        )


def get_matching_v2_review_service(request: Request) -> MatchingV2ReviewService:
    return MatchingV2ReviewService(
        PostgresMatchingV2ReviewRepository(request.app.state.database_probe.engine),
        _repository_root(),
    )


MatchingV2ReviewServiceDependency = Annotated[
    MatchingV2ReviewService,
    Depends(get_matching_v2_review_service),
]
AdminToken = Annotated[str | None, Header(alias="X-RCI-Admin-Token")]


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, KeyError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


def _matching_ai_review_policy() -> dict[str, Any]:
    enabled = _enabled(os.getenv("MATCHING_V2_AI_REVIEW_ENABLED"))
    model_id = (
        os.getenv("OPENAI_MODEL_MATCHING_REVIEW") or os.getenv("OPENAI_MODEL_NARRATIVE") or ""
    ).strip()
    try:
        max_request_cost_usd = float(os.getenv("OPENAI_MATCHING_MAX_REQUEST_COST_USD", "0.35"))
    except ValueError:
        max_request_cost_usd = 0.35
    return {
        "enabled": enabled and bool(model_id),
        "model_id": model_id or None,
        "max_batch_cases": _MAX_AI_REVIEW_BATCH_CASES,
        "queue_wide_selection": True,
        "queue_wide_scope": "current_queue_and_competitor_filter",
        "max_request_cost_usd": max_request_cost_usd,
        "max_retry_rounds": _MAX_AI_RETRY_ROUNDS,
        "retryable_statuses": ["needs_review"],
        "retry_preserves_history": True,
        "retry_blocks_integrity_failures": True,
        "vision_policy": "missing_or_conflicting_critical_evidence_only",
        "authoritative": False,
        "human_review_required": True,
    }


def _require_matching_ai_review() -> str:
    policy = _matching_ai_review_policy()
    if not _enabled(os.getenv("MATCHING_V2_AI_REVIEW_ENABLED")):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Matching v2 AI draft review is not enabled.",
        )
    model_id = str(policy["model_id"] or "")
    if not model_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No Matching v2 AI review model is configured.",
        )
    return model_id


@router.post("/review-queues/import", status_code=status.HTTP_201_CREATED)
async def import_matching_v2_review_queue(
    request: Request,
    body: ImportReviewQueueRequest,
    service: MatchingV2ReviewServiceDependency,
    x_rci_admin_token: AdminToken = None,
) -> dict[str, Any]:
    _require_review_access(request, x_rci_admin_token)
    try:
        return await service.import_queue(body)
    except (ContractError, KeyError, ValueError) as exc:
        raise _http_error(exc) from exc


@router.get("/review-queues")
async def list_matching_v2_review_queues(
    request: Request,
    service: MatchingV2ReviewServiceDependency,
    x_rci_admin_token: AdminToken = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    _require_review_access(request, x_rci_admin_token)
    return await service.list_queues(limit=limit)


@router.get("/review-queues/{queue_id}")
async def get_matching_v2_review_queue(
    queue_id: str,
    request: Request,
    service: MatchingV2ReviewServiceDependency,
    x_rci_admin_token: AdminToken = None,
    competitor_retailer_id: str | None = Query(default=None),
    benchmark_product_id: str | None = Query(default=None),
    competitor_product_id: str | None = Query(default=None),
    stratum: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    _require_review_access(request, x_rci_admin_token)
    try:
        document = await service.queue_view(
            queue_id,
            competitor_retailer_id=competitor_retailer_id,
            benchmark_product_id=benchmark_product_id,
            competitor_product_id=competitor_product_id,
            stratum=stratum,
            review_status=review_status,
            offset=offset,
            limit=limit,
        )
        document["ai_review_policy"] = _matching_ai_review_policy()
        document["ai_bulk_certification_policy"] = _ai_bulk_certification_policy()
        return document
    except KeyError as exc:
        raise _http_error(exc) from exc


@router.get("/review-queues/{queue_id}/attribute-evidence-proposals")
async def list_matching_v2_attribute_evidence_proposals(
    queue_id: str,
    request: Request,
    service: MatchingV2ReviewServiceDependency,
    x_rci_admin_token: AdminToken = None,
    competitor_retailer_id: str | None = Query(default=None),
    batch_scope: Annotated[AttributeEvidenceBatchScope, Query()] = "latest_lineage",
    root_batch_id: str | None = Query(default=None),
    eligibility: Annotated[AttributeEvidenceEligibility, Query()] = "eligible",
    decision_status: Annotated[AttributeEvidenceDecisionStatus, Query()] = "undecided",
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    _require_review_access(request, x_rci_admin_token)
    try:
        return await service.attribute_evidence_proposals(
            queue_id,
            competitor_retailer_id=competitor_retailer_id,
            batch_scope=batch_scope,
            root_batch_id=root_batch_id,
            eligibility=eligibility,
            decision_status=decision_status,
            offset=offset,
            limit=limit,
        )
    except KeyError as exc:
        raise _http_error(exc) from exc


@router.get("/review-queues/{queue_id}/attribute-evidence-claims")
async def list_matching_v2_attribute_evidence_claims(
    queue_id: str,
    request: Request,
    service: MatchingV2ReviewServiceDependency,
    x_rci_admin_token: AdminToken = None,
    competitor_retailer_id: str | None = Query(default=None),
    batch_scope: Annotated[AttributeEvidenceBatchScope, Query()] = "all_lineages",
    root_batch_id: str | None = Query(default=None),
    claim_status: Annotated[AttributeEvidenceClaimStatus, Query()] = "awaiting_review",
    attribute: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    _require_review_access(request, x_rci_admin_token)
    try:
        return await service.attribute_evidence_claims(
            queue_id,
            competitor_retailer_id=competitor_retailer_id,
            batch_scope=batch_scope,
            root_batch_id=root_batch_id,
            status_filter=claim_status,
            attribute_filter=attribute,
            offset=offset,
            limit=limit,
        )
    except (KeyError, ValueError) as exc:
        raise _http_error(exc) from exc


@router.post(
    "/review-queues/{queue_id}/attribute-evidence-claims/{claim_checksum}/decisions",
    status_code=status.HTTP_201_CREATED,
)
async def decide_matching_v2_attribute_evidence_claim(
    queue_id: str,
    claim_checksum: str,
    request: Request,
    body: AttributeEvidenceClaimDecisionRequest,
    service: MatchingV2ReviewServiceDependency,
    x_rci_admin_token: AdminToken = None,
) -> dict[str, Any]:
    _require_review_access(request, x_rci_admin_token)
    if body.claim_checksum != claim_checksum:
        raise HTTPException(status_code=422, detail="claim checksum path and body differ")
    try:
        return await service.decide_attribute_evidence_claim(queue_id, body)
    except (KeyError, ValueError) as exc:
        raise _http_error(exc) from exc


@router.post(
    "/review-queues/{queue_id}/cases/{case_id}/submissions",
    status_code=status.HTTP_201_CREATED,
)
async def submit_matching_v2_review(
    queue_id: str,
    case_id: str,
    request: Request,
    body: ReviewSubmissionRequest,
    service: MatchingV2ReviewServiceDependency,
    x_rci_admin_token: AdminToken = None,
) -> dict[str, Any]:
    _require_review_access(request, x_rci_admin_token)
    try:
        return await service.submit_review(queue_id, case_id, body)
    except (KeyError, ValueError) as exc:
        raise _http_error(exc) from exc


@router.post(
    "/review-queues/{queue_id}/cases/{case_id}/attribute-evidence-decisions",
    status_code=status.HTTP_201_CREATED,
)
async def decide_matching_v2_attribute_evidence(
    queue_id: str,
    case_id: str,
    request: Request,
    body: AttributeEvidenceDecisionRequest,
    service: MatchingV2ReviewServiceDependency,
    x_rci_admin_token: AdminToken = None,
) -> dict[str, Any]:
    _require_review_access(request, x_rci_admin_token)
    try:
        return await service.decide_attribute_evidence(queue_id, case_id, body)
    except (KeyError, ValueError) as exc:
        raise _http_error(exc) from exc


@router.post(
    "/review-queues/{queue_id}/cases/{case_id}/ai-drafts",
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_matching_v2_ai_draft(
    queue_id: str,
    case_id: str,
    request: Request,
    body: AIReviewDraftRequest,
    service: MatchingV2ReviewServiceDependency,
    x_rci_admin_token: AdminToken = None,
) -> dict[str, Any]:
    _require_review_access(request, x_rci_admin_token)
    model_id = _require_matching_ai_review()
    try:
        return await service.request_ai_draft(
            queue_id,
            case_id,
            body,
            model_id=model_id,
        )
    except (ContractError, KeyError, OSError, ValueError) as exc:
        raise _http_error(exc) from exc


@router.post(
    "/review-queues/{queue_id}/ai-drafts",
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_matching_v2_ai_draft_batch(
    queue_id: str,
    request: Request,
    body: AIReviewBatchRequest,
    service: MatchingV2ReviewServiceDependency,
    x_rci_admin_token: AdminToken = None,
) -> dict[str, Any]:
    _require_review_access(request, x_rci_admin_token)
    model_id = _require_matching_ai_review()
    try:
        return await service.request_ai_drafts(queue_id, body, model_id=model_id)
    except (ContractError, KeyError, OSError, ValueError) as exc:
        raise _http_error(exc) from exc


@router.get("/review-queues/{queue_id}/ai-drafts/eligible-cases")
async def list_matching_v2_ai_draft_eligible_cases(
    queue_id: str,
    request: Request,
    service: MatchingV2ReviewServiceDependency,
    x_rci_admin_token: AdminToken = None,
    competitor_retailer_id: str | None = Query(default=None),
    selection_mode: AIReviewSelectionMode = "all_cases",
) -> dict[str, Any]:
    _require_review_access(request, x_rci_admin_token)
    _require_matching_ai_review()
    try:
        document = await service.eligible_ai_review_cases(
            queue_id,
            competitor_retailer_id=competitor_retailer_id,
            selection_mode=selection_mode,
        )
        document["policy"] = _matching_ai_review_policy()
        document["authoritative"] = False
        document["human_review_required"] = True
        return document
    except (KeyError, ValueError) as exc:
        raise _http_error(exc) from exc


@router.post(
    "/review-queues/{queue_id}/ai-drafts/retry",
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_matching_v2_ai_draft_batch(
    queue_id: str,
    request: Request,
    body: AIReviewRetryRequest,
    service: MatchingV2ReviewServiceDependency,
    x_rci_admin_token: AdminToken = None,
) -> dict[str, Any]:
    _require_review_access(request, x_rci_admin_token)
    model_id = _require_matching_ai_review()
    try:
        return await service.retry_ai_drafts(queue_id, body, model_id=model_id)
    except (ContractError, KeyError, OSError, ValueError) as exc:
        raise _http_error(exc) from exc


@router.post("/review-queues/{queue_id}/ai-bulk-certification/preview")
async def preview_matching_v2_ai_bulk_certification(
    queue_id: str,
    request: Request,
    body: AIBulkCertificationPreviewRequest,
    service: MatchingV2ReviewServiceDependency,
    x_rci_admin_token: AdminToken = None,
) -> dict[str, Any]:
    _require_review_access(request, x_rci_admin_token)
    try:
        return await service.preview_ai_bulk_certification(queue_id, body)
    except (KeyError, ValueError) as exc:
        raise _http_error(exc) from exc


@router.post(
    "/review-queues/{queue_id}/ai-bulk-certification/commit",
    status_code=status.HTTP_201_CREATED,
)
async def commit_matching_v2_ai_bulk_certification(
    queue_id: str,
    request: Request,
    body: AIBulkCertificationCommitRequest,
    service: MatchingV2ReviewServiceDependency,
    x_rci_admin_token: AdminToken = None,
) -> dict[str, Any]:
    _require_review_access(request, x_rci_admin_token)
    try:
        return await service.commit_ai_bulk_certification(queue_id, body)
    except (KeyError, ValueError) as exc:
        raise _http_error(exc) from exc


@router.post(
    "/review-queues/{queue_id}/cases/{case_id}/adjudications",
    status_code=status.HTTP_201_CREATED,
)
async def adjudicate_matching_v2_review(
    queue_id: str,
    case_id: str,
    request: Request,
    body: AdjudicationRequest,
    service: MatchingV2ReviewServiceDependency,
    x_rci_admin_token: AdminToken = None,
) -> dict[str, Any]:
    _require_review_access(request, x_rci_admin_token)
    try:
        return await service.adjudicate(queue_id, case_id, body)
    except (KeyError, ValueError) as exc:
        raise _http_error(exc) from exc


@router.get("/review-queues/{queue_id}/gold-set")
async def export_matching_v2_gold_set(
    queue_id: str,
    request: Request,
    service: MatchingV2ReviewServiceDependency,
    x_rci_admin_token: AdminToken = None,
) -> dict[str, Any]:
    _require_review_access(request, x_rci_admin_token)
    try:
        return await service.gold_set(queue_id)
    except (ContractError, KeyError, ValueError) as exc:
        raise _http_error(exc) from exc


@router.post(
    "/review-queues/{queue_id}/gold-set/replays",
    status_code=status.HTTP_201_CREATED,
)
async def create_matching_v2_gold_set_replay(
    queue_id: str,
    request: Request,
    body: GoldSetReplayRequest,
    service: MatchingV2ReviewServiceDependency,
    x_rci_admin_token: AdminToken = None,
) -> dict[str, Any]:
    _require_review_access(request, x_rci_admin_token)
    try:
        return await service.create_gold_set_replay(queue_id, body)
    except (ContractError, KeyError, ValueError) as exc:
        raise _http_error(exc) from exc
