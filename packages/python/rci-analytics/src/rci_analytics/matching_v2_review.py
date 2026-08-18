"""Deterministic review-queue construction for Matching Architecture v2.

Review queues are not gold labels. They preserve the engine proposal and its
immutable evidence reference so independent reviewers can create a gold set
without treating model output as ground truth.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from rci_analytics.matching_v2 import ListingEvidence, TieredMatchDecisionV2
from rci_analytics.matching_v2_shadow import MatchingShadowResultV2
from rci_analytics.models import JsonObject


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)


def _stable_rank(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class MatchingV2ReviewSampling:
    per_stratum_limit: int = 40
    include_all_automatic_approvals: bool = True

    def __post_init__(self) -> None:
        if self.per_stratum_limit < 1:
            raise ValueError("per-stratum review limit must be positive")


def _stratum(
    decision: TieredMatchDecisionV2,
    competitor_frequency: Mapping[str, int],
) -> str:
    if competitor_frequency.get(decision.competitor.listing_id, 0) > 1 and decision.tier:
        return f"overlapping_many_to_one_{decision.tier}_{decision.status}"
    if decision.status == "auto_approved":
        return f"automatic_{decision.tier or 'unresolved'}"
    if decision.tier:
        return f"review_{decision.tier}"
    if decision.status == "not_comparable":
        return "known_hard_conflict"
    return "incomplete_or_unknown_evidence"


def _case(
    decision: TieredMatchDecisionV2,
    *,
    benchmark_source_reference: str,
    competitor_source_reference: str,
    stratum: str,
) -> JsonObject:
    contract = decision.to_contract()
    evidence_references = sorted(
        {
            benchmark_source_reference,
            competitor_source_reference,
        }
    )
    return {
        "case_id": f"case-{_stable_rank([evidence_references, decision.edge_id])[:24]}",
        "benchmark_listing_id": decision.benchmark.listing_id,
        "competitor_listing_id": decision.competitor.listing_id,
        "competitor_retailer_id": decision.competitor.retailer_id,
        "benchmark_listing": _listing_summary(decision.benchmark),
        "competitor_listing": _listing_summary(decision.competitor),
        "stratum": stratum,
        "critical": decision.status == "auto_approved" or "overlapping_many_to_one" in stratum,
        "engine_proposal": {
            "edge_id": decision.edge_id,
            "tier": decision.tier,
            "status": decision.status,
            "decision_reason": decision.decision_reason,
            "evidence_coverage": contract["evidence_coverage"],
        },
        "evidence_refs": [
            f"{reference}|edge_id={decision.edge_id}" for reference in evidence_references
        ],
        "edge": contract,
        "review_state": "pending",
    }


def _listing_summary(listing: ListingEvidence) -> JsonObject:
    return {
        "listing_id": listing.listing_id,
        "retailer_id": listing.retailer_id,
        "retailer_product_id": listing.retailer_product_id,
        "title": listing.title,
        "brand": listing.brand,
        "brand_type": listing.brand_type,
        "brand_verified": listing.brand_verified,
        "brand_governance": dict(listing.brand_governance),
        "seller_governance": dict(listing.seller_governance),
        "pdp_evidence": dict(listing.pdp_evidence),
        "observed_location_count": listing.observed_location_count,
        "image_url": listing.image_url,
        "image_urls": list(listing.image_urls),
        "product_url": listing.product_url,
        "identifiers": [
            {
                "scheme": identifier.scheme,
                "value": identifier.value,
                "verification_status": identifier.verification_status,
                "source": identifier.source,
            }
            for identifier in listing.identifiers
        ],
        "attributes": {
            name: {
                "value": value.value,
                "source": value.source,
                "reliability": value.reliability,
                "review_status": value.review_status,
            }
            for name, value in sorted(listing.attributes.items())
        },
    }


def build_matching_v2_review_queue(
    results: Sequence[MatchingShadowResultV2],
    *,
    queue_id: str,
    queue_version: str,
    benchmark_source_reference: str,
    source_references: Mapping[str, str],
    sampling: MatchingV2ReviewSampling | None = None,
    selection_mode: Literal["validation_sample", "operational_exhaustive"] = "validation_sample",
) -> JsonObject:
    """Build a deterministic review queue without creating gold labels.

    Validation queues retain every automatic approval and a bounded sample of
    the remaining strata. Operational queues retain every governed candidate;
    only those exhaustive queues are eligible to drive a report release.
    """

    if not results:
        raise ValueError("review queue requires at least one shadow result")
    if not benchmark_source_reference:
        raise ValueError("review queue requires an immutable benchmark source reference")
    policy_checksums = {result.policy_checksum for result in results}
    pack_versions = {(result.product_pack_id, result.product_pack_version) for result in results}
    if len(policy_checksums) != 1 or len(pack_versions) != 1:
        raise ValueError("review queue cannot mix Product Pack versions or policy checksums")
    config = sampling or MatchingV2ReviewSampling()
    if selection_mode not in {"validation_sample", "operational_exhaustive"}:
        raise ValueError(f"unsupported review queue selection mode {selection_mode!r}")
    all_decisions = tuple(
        decision
        for result in results
        for decision in (
            tuple(edge for edge in result.edges if edge.tier is not None)
            if selection_mode == "operational_exhaustive"
            else (*result.edges, *result.blocked_review_edges)
        )
    )
    competitor_frequency = Counter(
        decision.competitor.listing_id
        for decision in all_decisions
        if decision.tier is not None and decision.status != "not_comparable"
    )
    by_stratum: dict[str, list[tuple[TieredMatchDecisionV2, str]]] = {}
    for result in results:
        source_reference = source_references.get(result.competitor_retailer_id)
        if not source_reference:
            raise ValueError(
                f"missing immutable source reference for {result.competitor_retailer_id!r}"
            )
        decisions = (
            tuple(edge for edge in result.edges if edge.tier is not None)
            if selection_mode == "operational_exhaustive"
            else (*result.edges, *result.blocked_review_edges)
        )
        for decision in decisions:
            stratum = (
                f"{decision.competitor.retailer_id}:{_stratum(decision, competitor_frequency)}"
            )
            by_stratum.setdefault(stratum, []).append((decision, source_reference))

    selected: list[JsonObject] = []
    available_counts: dict[str, int] = {}
    selected_counts: dict[str, int] = {}
    excluded_counts: dict[str, int] = {}
    if selection_mode == "operational_exhaustive":
        for result in results:
            retailer_id = result.competitor_retailer_id
            excluded_counts[f"{retailer_id}:unresolved_without_governed_tier"] = sum(
                edge.tier is None for edge in result.edges
            )
            excluded_counts[f"{retailer_id}:hard_blocked_pairs"] = result.blocked_pairs
            excluded_counts[f"{retailer_id}:hard_blocked_audit_sample"] = len(
                result.blocked_review_edges
            )
    for stratum in sorted(by_stratum):
        rows = sorted(
            by_stratum[stratum],
            key=lambda row: _stable_rank(
                [row[0].benchmark.listing_id, row[0].competitor.listing_id, row[0].edge_id]
            ),
        )
        available_counts[stratum] = len(rows)
        if selection_mode == "operational_exhaustive":
            chosen = rows
        elif config.include_all_automatic_approvals:
            automatic = [row for row in rows if row[0].status == "auto_approved"]
            automatic_ids = {row[0].edge_id for row in automatic}
            sampled = [row for row in rows if row[0].edge_id not in automatic_ids][
                : config.per_stratum_limit
            ]
            chosen = [*automatic, *sampled]
        else:
            chosen = rows[: config.per_stratum_limit]
        selected_counts[stratum] = len(chosen)
        selected.extend(
            _case(
                decision,
                benchmark_source_reference=benchmark_source_reference,
                competitor_source_reference=source_reference,
                stratum=stratum,
            )
            for decision, source_reference in chosen
        )

    selected.sort(key=lambda row: (str(row["stratum"]), str(row["case_id"])))
    pack_id, pack_version = next(iter(pack_versions))
    document: JsonObject = {
        "schema_version": "2.0.0",
        "queue_id": queue_id,
        "version": queue_version,
        "purpose": (
            "operational_match_certification"
            if selection_mode == "operational_exhaustive"
            else "human_gold_set_adjudication"
        ),
        "authoritative": False,
        "product_pack": {"id": pack_id, "version": pack_version},
        "policy_checksum": next(iter(policy_checksums)),
        "source_evidence": sorted({benchmark_source_reference, *source_references.values()}),
        "sampling": {
            "method": (
                "exhaustive_governed_candidates"
                if selection_mode == "operational_exhaustive"
                else "deterministic_stratified_sha256"
            ),
            "per_stratum_limit": config.per_stratum_limit,
            "include_all_automatic_approvals": config.include_all_automatic_approvals,
            "available_counts": available_counts,
            "selected_counts": selected_counts,
            "excluded_counts": excluded_counts,
        },
        "cases": selected,
    }
    document["checksum"] = _stable_rank(document)
    return document


def queue_cases(document: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    cases = document.get("cases", [])
    if not isinstance(cases, list):
        raise ValueError("review queue cases must be an array")
    return (case for case in cases if isinstance(case, dict))
