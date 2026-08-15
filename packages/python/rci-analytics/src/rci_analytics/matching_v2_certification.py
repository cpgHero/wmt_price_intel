"""Stage-specific certification gates for Matching Architecture v2."""

from __future__ import annotations

from dataclasses import dataclass

from rci_analytics.matching_v2 import MatchTier, TieredMatchDecisionV2
from rci_analytics.models import JsonObject


@dataclass(frozen=True, slots=True)
class GoldMatchLabelV2:
    case_id: str
    benchmark_listing_id: str
    competitor_listing_id: str
    expected_comparable: bool
    allowed_tiers: tuple[MatchTier, ...]
    critical: bool = False
    stratum: str = "unspecified"
    review_status: str = "synthetic_fixture"
    reviewers: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    rationale: str | None = None

    @property
    def pair(self) -> tuple[str, str]:
        return self.benchmark_listing_id, self.competitor_listing_id


@dataclass(frozen=True, slots=True)
class MatchingCertificationThresholdsV2:
    candidate_recall: float = 0.995
    auto_approval_precision: float = 0.999

    def __post_init__(self) -> None:
        if not 0 <= self.candidate_recall <= 1:
            raise ValueError("candidate recall threshold must be between zero and one")
        if not 0 <= self.auto_approval_precision <= 1:
            raise ValueError("auto-approval precision threshold must be between zero and one")


@dataclass(frozen=True, slots=True)
class MatchingV2Certification:
    product_pack_id: str
    product_pack_version: str
    policy_checksum: str
    gold_set_version: str
    gold_positive_pairs: int
    recalled_positive_pairs: int
    candidate_recall: float
    labeled_auto_approvals: int
    correct_auto_approvals: int
    auto_approval_precision: float
    unlabeled_auto_approvals: int
    hard_conflict_auto_approvals: int
    thresholds: MatchingCertificationThresholdsV2
    release_gate: bool
    strata: JsonObject
    failures: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.failures

    def to_contract(self) -> JsonObject:
        return {
            "schema_version": "2.0.0",
            "product_pack_id": self.product_pack_id,
            "product_pack_version": self.product_pack_version,
            "policy_checksum": self.policy_checksum,
            "gold_set_version": self.gold_set_version,
            "metrics": {
                "gold_positive_pairs": self.gold_positive_pairs,
                "recalled_positive_pairs": self.recalled_positive_pairs,
                "candidate_recall": self.candidate_recall,
                "labeled_auto_approvals": self.labeled_auto_approvals,
                "correct_auto_approvals": self.correct_auto_approvals,
                "auto_approval_precision": self.auto_approval_precision,
                "unlabeled_auto_approvals": self.unlabeled_auto_approvals,
                "hard_conflict_auto_approvals": self.hard_conflict_auto_approvals,
            },
            "thresholds": {
                "candidate_recall": self.thresholds.candidate_recall,
                "auto_approval_precision": self.thresholds.auto_approval_precision,
            },
            "release_gate": self.release_gate,
            "strata": self.strata,
            "failures": list(self.failures),
            "ready": self.ready,
        }


def certify_matching_v2(
    decisions: tuple[TieredMatchDecisionV2, ...],
    labels: tuple[GoldMatchLabelV2, ...],
    *,
    gold_set_version: str,
    thresholds: MatchingCertificationThresholdsV2 | None = None,
    release_gate: bool = False,
) -> MatchingV2Certification:
    """Measure recall and precision at their correct, separate stages."""

    if not decisions:
        raise ValueError("certification requires at least one evaluated decision")
    if not labels:
        raise ValueError("certification requires at least one gold label")
    threshold = thresholds or MatchingCertificationThresholdsV2()
    pair_labels: dict[tuple[str, str], GoldMatchLabelV2] = {}
    for label in labels:
        if label.pair in pair_labels:
            raise ValueError(f"duplicate gold pair {label.pair!r}")
        pair_labels[label.pair] = label

    decision_pairs = {
        (decision.benchmark.listing_id, decision.competitor.listing_id) for decision in decisions
    }
    positives = [label for label in labels if label.expected_comparable]
    recalled = [label for label in positives if label.pair in decision_pairs]
    candidate_recall = round(len(recalled) / len(positives), 6) if positives else 1.0

    auto = [decision for decision in decisions if decision.status == "auto_approved"]
    labeled_auto = [
        decision
        for decision in auto
        if (decision.benchmark.listing_id, decision.competitor.listing_id) in pair_labels
    ]
    correct_auto = []
    for decision in labeled_auto:
        label = pair_labels[(decision.benchmark.listing_id, decision.competitor.listing_id)]
        if label.expected_comparable and decision.tier in label.allowed_tiers:
            correct_auto.append(decision)
    auto_precision = round(len(correct_auto) / len(labeled_auto), 6) if labeled_auto else 1.0
    unlabeled_auto = len(auto) - len(labeled_auto)
    hard_conflict_auto = sum(
        any(row.role == "hard_blocker" and row.outcome == "conflict" for row in decision.evidence)
        for decision in auto
    )

    failures: list[str] = []
    if candidate_recall < threshold.candidate_recall:
        failures.append(
            f"candidate recall {candidate_recall:.4%} is below {threshold.candidate_recall:.4%}"
        )
    if auto_precision < threshold.auto_approval_precision:
        failures.append(
            "auto-approval precision "
            f"{auto_precision:.4%} is below {threshold.auto_approval_precision:.4%}"
        )
    if unlabeled_auto:
        failures.append(f"{unlabeled_auto} automatic approvals lack a gold label")
    if hard_conflict_auto:
        failures.append(f"{hard_conflict_auto} automatic approvals contain a hard conflict")
    if release_gate:
        non_adjudicated = [label for label in labels if label.review_status != "adjudicated"]
        under_reviewed = [label for label in labels if len(set(label.reviewers)) < 2]
        unsupported = [label for label in labels if not label.evidence_refs]
        if non_adjudicated:
            failures.append(f"{len(non_adjudicated)} gold labels are not adjudicated")
        if under_reviewed:
            failures.append(f"{len(under_reviewed)} gold labels have fewer than two reviewers")
        if unsupported:
            failures.append(f"{len(unsupported)} gold labels have no immutable evidence reference")

    policy = decisions[0].policy
    if any(decision.policy.checksum != policy.checksum for decision in decisions):
        failures.append("certification input mixes policy checksums")
    strata: JsonObject = {}
    for stratum in sorted({label.stratum for label in labels}):
        stratum_labels = [label for label in labels if label.stratum == stratum]
        stratum_positives = [label for label in stratum_labels if label.expected_comparable]
        stratum_recalled = [label for label in stratum_positives if label.pair in decision_pairs]
        stratum_auto = [
            decision
            for decision in auto
            if (decision.benchmark.listing_id, decision.competitor.listing_id)
            in {label.pair for label in stratum_labels}
        ]
        stratum_correct_auto = [
            decision
            for decision in stratum_auto
            if pair_labels[
                (decision.benchmark.listing_id, decision.competitor.listing_id)
            ].expected_comparable
            and decision.tier
            in pair_labels[
                (decision.benchmark.listing_id, decision.competitor.listing_id)
            ].allowed_tiers
        ]
        strata[stratum] = {
            "labels": len(stratum_labels),
            "positive_pairs": len(stratum_positives),
            "candidate_recall": (
                round(len(stratum_recalled) / len(stratum_positives), 6)
                if stratum_positives
                else 1.0
            ),
            "automatic_approvals": len(stratum_auto),
            "auto_approval_precision": (
                round(len(stratum_correct_auto) / len(stratum_auto), 6) if stratum_auto else 1.0
            ),
        }
    return MatchingV2Certification(
        product_pack_id=policy.product_pack_id,
        product_pack_version=policy.product_pack_version,
        policy_checksum=policy.checksum,
        gold_set_version=gold_set_version,
        gold_positive_pairs=len(positives),
        recalled_positive_pairs=len(recalled),
        candidate_recall=candidate_recall,
        labeled_auto_approvals=len(labeled_auto),
        correct_auto_approvals=len(correct_auto),
        auto_approval_precision=auto_precision,
        unlabeled_auto_approvals=unlabeled_auto,
        hard_conflict_auto_approvals=hard_conflict_auto,
        thresholds=threshold,
        release_gate=release_gate,
        strata=strata,
        failures=tuple(failures),
    )
