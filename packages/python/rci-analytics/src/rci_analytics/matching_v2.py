"""Evidence-governed pairwise matching and local comparison shadow engine.

The v2 engine is intentionally independent from the authoritative v1 matcher.
It produces deterministic, contract-ready evidence that can be reconciled in
shadow mode before any Product Pack is promoted.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, cast

from rci_analytics.product_pack import ProductPack

JsonObject = dict[str, Any]
AttributeRole = Literal[
    "identity",
    "hard_blocker",
    "required_exact",
    "soft_comparator",
    "descriptive",
    "ignored",
]
EvidenceOutcome = Literal["match", "conflict", "unknown", "ignored", "within_tolerance"]
MatchTier = Literal[
    "exact_item",
    "exact_specification",
    "equivalent_product",
    "comparable_substitute",
    "custom_approved",
]
MatchStatus = Literal[
    "candidate",
    "auto_approved",
    "human_approved",
    "rejected",
    "expired",
    "superseded",
    "needs_revalidation",
    "unresolved",
    "not_comparable",
]
BrandType = Literal["private_label", "regional", "national", "unclassified"]
CoverageReason = Literal[
    "comparable",
    "no_eligible_match",
    "no_geographic_overlap",
    "matched_product_not_observed",
    "price_unavailable_or_stale",
    "collection_failure",
    "attribute_evidence_incomplete",
    "match_review_required",
]
SelectionPolicy = Literal[
    "lowest_eligible_local_offer",
    "nearest_eligible_offer",
    "representative_assortment",
]

_APPROVED_STATUSES = frozenset({"auto_approved", "human_approved"})


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)


def _checksum(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode()).hexdigest()


def _normalized_scalar(value: Any) -> Any:
    if isinstance(value, str):
        return " ".join(value.casefold().split())
    if isinstance(value, list):
        return tuple(_normalized_scalar(item) for item in value)
    if isinstance(value, dict):
        return tuple(
            (str(key), _normalized_scalar(item)) for key, item in sorted(value.items(), key=str)
        )
    return value


@dataclass(frozen=True, slots=True)
class IdentifierEvidence:
    scheme: str
    value: str
    verification_status: Literal["observed", "verified", "disputed"] = "observed"
    source: str = "unknown"


@dataclass(frozen=True, slots=True)
class AttributeValue:
    value: Any
    source: str
    reliability: float = 1.0
    review_status: Literal["unreviewed", "verified", "conflicted"] = "verified"

    def __post_init__(self) -> None:
        if not 0 <= self.reliability <= 1:
            raise ValueError("attribute reliability must be between zero and one")


@dataclass(frozen=True, slots=True)
class ListingEvidence:
    listing_id: str
    retailer_id: str
    retailer_product_id: str
    attributes: Mapping[str, AttributeValue]
    identifiers: tuple[IdentifierEvidence, ...] = ()
    title: str | None = None
    image_url: str | None = None
    product_url: str | None = None
    brand: str | None = None
    brand_type: BrandType = "unclassified"
    brand_verified: bool = False
    brand_governance: Mapping[str, Any] = field(default_factory=dict)
    seller_governance: Mapping[str, Any] = field(default_factory=dict)
    pdp_evidence: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AttributePolicyV2:
    name: str
    role: AttributeRole
    weight: float = 1.0
    numeric_tolerance: float | None = None
    critical: bool = True

    def __post_init__(self) -> None:
        if self.weight < 0:
            raise ValueError("attribute weight cannot be negative")
        if self.numeric_tolerance is not None and self.numeric_tolerance < 0:
            raise ValueError("numeric tolerance cannot be negative")


@dataclass(frozen=True, slots=True)
class MatchingPolicyV2:
    policy_id: str
    version: str
    product_pack_id: str
    product_pack_version: str
    attributes: tuple[AttributePolicyV2, ...]
    eligible_price_bases: tuple[str, ...]
    price_basis_requirements: tuple[tuple[str, tuple[str, ...]], ...] = ()
    exact_item_identifier_schemes: tuple[str, ...] = (
        "gtin",
        "upc",
        "manufacturer_item_id",
    )
    auto_approval_tiers: tuple[Literal["exact_item", "exact_specification"], ...] = ()
    minimum_equivalent_coverage: float = 0.8
    equivalent_score_threshold: float = 0.9
    allow_comparable_substitute: bool = True
    geography_policy: str = "physical_store_radius"
    scope_mode: Literal["global", "observed_distribution", "explicit_locations", "regional"] = (
        "observed_distribution"
    )
    fulfillment_types: tuple[str, ...] = ("pickup",)

    def __post_init__(self) -> None:
        if not self.attributes:
            raise ValueError("matching policy must define attributes")
        names = [rule.name for rule in self.attributes]
        if len(names) != len(set(names)):
            raise ValueError("matching policy attribute names must be unique")
        if not self.eligible_price_bases:
            raise ValueError("matching policy must define an eligible price basis")
        if len(self.eligible_price_bases) != len(set(self.eligible_price_bases)):
            raise ValueError("matching policy price bases must be unique")
        requirement_bases = [basis for basis, _ in self.price_basis_requirements]
        if len(requirement_bases) != len(set(requirement_bases)):
            raise ValueError("matching policy price-basis requirement keys must be unique")
        if any(
            not attributes or len(attributes) != len(set(attributes))
            for _, attributes in self.price_basis_requirements
        ):
            raise ValueError(
                "matching policy price-basis attribute requirements must be non-empty and unique"
            )
        unknown_bases = sorted(
            basis
            for basis, _ in self.price_basis_requirements
            if basis not in self.eligible_price_bases
        )
        if unknown_bases:
            raise ValueError(
                f"price-basis requirements reference ineligible bases: {unknown_bases}"
            )
        unknown_attributes = sorted(
            name
            for _, required_attributes in self.price_basis_requirements
            for name in required_attributes
            if name not in names
        )
        if unknown_attributes:
            raise ValueError(
                f"price-basis requirements reference unknown attributes: {unknown_attributes}"
            )
        if not 0 <= self.minimum_equivalent_coverage <= 1:
            raise ValueError("minimum equivalent coverage must be between zero and one")
        if not 0 <= self.equivalent_score_threshold <= 1:
            raise ValueError("equivalent score threshold must be between zero and one")

    @property
    def checksum(self) -> str:
        return _checksum(
            {
                "policy_id": self.policy_id,
                "version": self.version,
                "product_pack_id": self.product_pack_id,
                "product_pack_version": self.product_pack_version,
                "attributes": [
                    {
                        "name": rule.name,
                        "role": rule.role,
                        "weight": rule.weight,
                        "numeric_tolerance": rule.numeric_tolerance,
                        "critical": rule.critical,
                    }
                    for rule in self.attributes
                ],
                "eligible_price_bases": self.eligible_price_bases,
                "price_basis_requirements": self.price_basis_requirements,
                "exact_item_identifier_schemes": self.exact_item_identifier_schemes,
                "auto_approval_tiers": self.auto_approval_tiers,
                "minimum_equivalent_coverage": self.minimum_equivalent_coverage,
                "equivalent_score_threshold": self.equivalent_score_threshold,
                "allow_comparable_substitute": self.allow_comparable_substitute,
                "geography_policy": self.geography_policy,
                "scope_mode": self.scope_mode,
                "fulfillment_types": self.fulfillment_types,
            }
        )


@dataclass(frozen=True, slots=True)
class AttributeComparisonV2:
    attribute: str
    role: AttributeRole
    benchmark_value: Any
    competitor_value: Any
    outcome: EvidenceOutcome
    benchmark_source: str | None
    competitor_source: str | None
    weight: float
    reliability: float
    rationale: str | None = None

    def to_contract(self) -> JsonObject:
        return {
            "attribute": self.attribute,
            "role": self.role,
            "benchmark_value": self.benchmark_value,
            "competitor_value": self.competitor_value,
            "outcome": self.outcome,
            "benchmark_source": self.benchmark_source,
            "competitor_source": self.competitor_source,
            "weight": self.weight,
            "reliability": self.reliability,
            "rationale": self.rationale,
        }


@dataclass(frozen=True, slots=True)
class TieredMatchDecisionV2:
    edge_id: str
    policy: MatchingPolicyV2
    benchmark: ListingEvidence
    competitor: ListingEvidence
    tier: MatchTier | None
    status: MatchStatus
    brand_relationship: str
    eligible_price_bases: tuple[str, ...]
    known_critical: int
    required_critical: int
    critical_coverage: float
    weighted_evidence_score: float | None
    evidence: tuple[AttributeComparisonV2, ...]
    decision_reason: str
    decided_at: str

    def to_contract(self) -> JsonObject:
        return {
            "schema_version": "2.0.0",
            "edge_id": self.edge_id,
            "policy": {
                "policy_id": self.policy.policy_id,
                "version": self.policy.version,
                "product_pack_id": self.policy.product_pack_id,
                "product_pack_version": self.policy.product_pack_version,
                "checksum": self.policy.checksum,
            },
            "benchmark_listing_id": self.benchmark.listing_id,
            "competitor_listing_id": self.competitor.listing_id,
            "tier": self.tier,
            "status": self.status,
            "brand_relationship": self.brand_relationship,
            "eligible_price_bases": list(self.eligible_price_bases),
            "evidence_coverage": {
                "known_critical": self.known_critical,
                "required_critical": self.required_critical,
                "critical_coverage": self.critical_coverage,
                "weighted_evidence_score": self.weighted_evidence_score,
            },
            "attribute_evidence": [row.to_contract() for row in self.evidence],
            "applicability": {
                "scope_mode": self.policy.scope_mode,
                "geography_policy": self.policy.geography_policy,
                "benchmark_location_scope_keys": [],
                "fulfillment_types": list(self.policy.fulfillment_types),
                "effective_from": self.decided_at,
                "effective_to": None,
            },
            "decision": {
                "origin": "deterministic_rule",
                "decided_at": self.decided_at,
                "actor": None,
                "reason": self.decision_reason,
                "supersedes_edge_id": None,
            },
        }


def compile_matching_policy_v2(pack: ProductPack, profile_id: str) -> MatchingPolicyV2:
    """Compile a conservative v2 policy from an existing Product Pack profile."""

    profile = pack.profile(profile_id)
    dimensions = {str(value) for value in profile["dimensions"]}
    configured = dict(pack.matching_v2 or {})
    configured_roles = dict(configured.get("attribute_roles") or {})
    rules: list[AttributePolicyV2] = []
    for attribute in pack.attributes:
        name = str(attribute["name"])
        configured_rule = configured_roles.get(name)
        if isinstance(configured_rule, dict):
            rules.append(
                AttributePolicyV2(
                    name=name,
                    role=cast(AttributeRole, str(configured_rule["role"])),
                    weight=float(configured_rule["weight"]),
                    numeric_tolerance=(
                        float(configured_rule["numeric_tolerance"])
                        if configured_rule.get("numeric_tolerance") is not None
                        else None
                    ),
                    critical=bool(configured_rule["critical"]),
                )
            )
        elif name in dimensions:
            role: AttributeRole = (
                "required_exact"
                if attribute.get("required_for_strict") is True
                else "soft_comparator"
            )
            rules.append(AttributePolicyV2(name=name, role=role, critical=True))
        elif str(attribute.get("role")) == "identity":
            rules.append(AttributePolicyV2(name=name, role="identity", critical=False))
        else:
            rules.append(AttributePolicyV2(name=name, role="descriptive", critical=False))

    comparison_metric = str(profile.get("comparison_metric") or "package_price")
    if comparison_metric == "package_price":
        basis = "exact_package"
    elif comparison_metric in {"price_per_lb", "price_per_oz"}:
        basis = "random_weight_unit" if "lb" in comparison_metric else "normalized_unit"
    else:
        basis = "normalized_unit"
    scope = dict(profile.get("relationship_scope_policy") or {})
    default_scope = str(scope.get("default_scope_mode") or "observed_benchmark_product_footprint")
    scope_mode: Literal["global", "observed_distribution", "explicit_locations", "regional"]
    scope_mode = {
        "global": "global",
        "observed_benchmark_product_footprint": "observed_distribution",
        "explicit_benchmark_locations": "explicit_locations",
    }.get(default_scope, "observed_distribution")  # type: ignore[assignment]
    geography = str(profile.get("geography") or "exact_zip")
    geography_policy = {
        "exact_zip": "same_zip",
        "radius": "physical_store_radius",
        "same_store_market": "merchant_market",
        "national": "national",
    }.get(geography, geography)
    return MatchingPolicyV2(
        policy_id=f"{pack.id}:{profile_id}",
        version=str(configured.get("policy_version") or "2.0.0-shadow"),
        product_pack_id=pack.id,
        product_pack_version=pack.version,
        attributes=tuple(rules),
        eligible_price_bases=tuple(
            str(value)
            for value in configured.get(
                "eligible_price_bases", (basis, "lowest_eligible_local_offer")
            )
        ),
        price_basis_requirements=tuple(
            (str(basis), tuple(str(name) for name in required_attributes))
            for basis, required_attributes in sorted(
                dict(configured.get("price_basis_requirements") or {}).items()
            )
        ),
        exact_item_identifier_schemes=tuple(
            str(value)
            for value in configured.get(
                "exact_item_identifier_schemes",
                ("gtin", "upc", "manufacturer_item_id"),
            )
        ),
        auto_approval_tiers=tuple(
            cast(
                Literal["exact_item", "exact_specification"],
                value,
            )
            for value in configured.get("auto_approval_tiers", ())
        ),
        minimum_equivalent_coverage=float(configured.get("minimum_equivalent_coverage", 0.8)),
        equivalent_score_threshold=float(configured.get("equivalent_score_threshold", 0.9)),
        allow_comparable_substitute=bool(configured.get("allow_comparable_substitute", True)),
        geography_policy=str(configured.get("geography_policy") or geography_policy),
        scope_mode=cast(
            Literal["global", "observed_distribution", "explicit_locations", "regional"],
            configured.get("scope_mode") or scope_mode,
        ),
        fulfillment_types=tuple(
            str(value) for value in configured.get("fulfillment_types", ("pickup",))
        ),
    )


class DeterministicMatchEngineV2:
    """Evaluate pairwise product evidence without price or geography leakage."""

    def evaluate(
        self,
        benchmark: ListingEvidence,
        competitor: ListingEvidence,
        policy: MatchingPolicyV2,
        *,
        decided_at: str,
    ) -> TieredMatchDecisionV2:
        _validate_datetime(decided_at)
        evidence = tuple(
            self._compare_attribute(
                rule,
                benchmark.attributes.get(rule.name),
                competitor.attributes.get(rule.name),
            )
            for rule in policy.attributes
        )
        critical_rows = [
            row
            for rule, row in zip(policy.attributes, evidence, strict=True)
            if rule.critical and rule.role != "ignored"
        ]
        known_critical = sum(row.outcome != "unknown" for row in critical_rows)
        required_critical = len(critical_rows)
        critical_coverage = (
            round(known_critical / required_critical, 6) if required_critical else 1.0
        )
        score_rows = [
            row
            for row in critical_rows
            if row.outcome not in {"unknown", "ignored"} and row.weight > 0 and row.reliability > 0
        ]
        score_denominator = sum(row.weight * row.reliability for row in score_rows)
        score_numerator = sum(
            row.weight
            * row.reliability
            * (1.0 if row.outcome in {"match", "within_tolerance"} else 0.0)
            for row in score_rows
        )
        weighted_score = (
            round(score_numerator / score_denominator, 6) if score_denominator else None
        )

        hard_conflicts = [
            row for row in evidence if row.role == "hard_blocker" and row.outcome == "conflict"
        ]
        critical_conflicts = [
            row
            for rule, row in zip(policy.attributes, evidence, strict=True)
            if rule.critical and row.outcome == "conflict"
        ]
        required_conflicts = [
            row for row in evidence if row.role == "required_exact" and row.outcome == "conflict"
        ]
        required_unknowns = [
            row for row in evidence if row.role == "required_exact" and row.outcome == "unknown"
        ]
        verified_identifier = self._shared_verified_identifier(benchmark, competitor, policy)

        tier: MatchTier | None
        status: MatchStatus
        reason: str
        if hard_conflicts:
            tier = None
            status = "not_comparable"
            reason = "A Product Pack hard-blocker attribute conflicts."
        elif verified_identifier and not critical_conflicts:
            tier = "exact_item"
            if tier in policy.auto_approval_tiers:
                status = "auto_approved"
                reason = (
                    f"Verified shared {verified_identifier} with no contradictory critical "
                    "evidence; the Product Pack authorizes automatic exact-item approval."
                )
            else:
                status = "candidate"
                reason = (
                    f"Verified shared {verified_identifier} with no contradictory critical "
                    "evidence; Product Pack review is required for this tier."
                )
        elif not critical_conflicts and not required_unknowns and critical_coverage == 1:
            tier = "exact_specification"
            if tier in policy.auto_approval_tiers:
                status = "auto_approved"
                reason = (
                    "All required critical attributes are known and compatible; the Product "
                    "Pack authorizes automatic exact-specification approval."
                )
            else:
                status = "candidate"
                reason = (
                    "All required critical attributes are known and compatible; Product Pack "
                    "review is required for this tier."
                )
        elif (
            not required_conflicts
            and critical_coverage >= policy.minimum_equivalent_coverage
            and weighted_score is not None
            and weighted_score >= policy.equivalent_score_threshold
        ):
            tier = "equivalent_product"
            status = "candidate"
            reason = (
                "Equivalent-product thresholds pass; human approval is required until certified."
            )
        elif required_conflicts and policy.allow_comparable_substitute:
            tier = "comparable_substitute"
            status = "candidate"
            reason = (
                "Material differences prevent equivalence but permit a labeled substitute review."
            )
        else:
            tier = None
            status = "unresolved"
            reason = "Critical evidence is incomplete or insufficient for a governed tier."

        price_bases = self._eligible_price_bases(policy, tier, evidence)
        edge_seed = {
            "policy": policy.checksum,
            "benchmark": benchmark.listing_id,
            "competitor": competitor.listing_id,
            "tier": tier,
            "status": status,
        }
        return TieredMatchDecisionV2(
            edge_id=f"edge-{_checksum(edge_seed)[:24]}",
            policy=policy,
            benchmark=benchmark,
            competitor=competitor,
            tier=tier,
            status=status,
            brand_relationship=_brand_relationship(benchmark, competitor),
            eligible_price_bases=price_bases,
            known_critical=known_critical,
            required_critical=required_critical,
            critical_coverage=critical_coverage,
            weighted_evidence_score=weighted_score,
            evidence=evidence,
            decision_reason=reason,
            decided_at=decided_at,
        )

    @staticmethod
    def _compare_attribute(
        policy: AttributePolicyV2,
        benchmark: AttributeValue | None,
        competitor: AttributeValue | None,
    ) -> AttributeComparisonV2:
        benchmark_value = benchmark.value if benchmark is not None else None
        competitor_value = competitor.value if competitor is not None else None
        rationale: str | None = None
        if policy.role == "ignored":
            outcome: EvidenceOutcome = "ignored"
        elif _is_unknown_or_conflicted(benchmark) or _is_unknown_or_conflicted(competitor):
            outcome = "unknown"
            if benchmark is not None and benchmark.review_status == "conflicted":
                rationale = "Benchmark evidence conflicts across observed sources or placements."
            elif competitor is not None and competitor.review_status == "conflicted":
                rationale = "Competitor evidence conflicts across observed sources or placements."
            else:
                rationale = "At least one side lacks governed evidence for this attribute."
        elif _normalized_scalar(benchmark_value) == _normalized_scalar(competitor_value):
            outcome = "match"
        elif (
            policy.numeric_tolerance is not None
            and isinstance(benchmark_value, (int, float))
            and not isinstance(benchmark_value, bool)
            and isinstance(competitor_value, (int, float))
            and not isinstance(competitor_value, bool)
            and abs(float(benchmark_value) - float(competitor_value)) <= policy.numeric_tolerance
        ):
            outcome = "within_tolerance"
        else:
            outcome = "conflict"
        reliability = min(
            benchmark.reliability if benchmark is not None else 0,
            competitor.reliability if competitor is not None else 0,
        )
        return AttributeComparisonV2(
            attribute=policy.name,
            role=policy.role,
            benchmark_value=benchmark_value,
            competitor_value=competitor_value,
            outcome=outcome,
            benchmark_source=benchmark.source if benchmark is not None else None,
            competitor_source=competitor.source if competitor is not None else None,
            weight=policy.weight,
            reliability=reliability,
            rationale=rationale,
        )

    @staticmethod
    def _shared_verified_identifier(
        benchmark: ListingEvidence,
        competitor: ListingEvidence,
        policy: MatchingPolicyV2,
    ) -> str | None:
        allowed = set(policy.exact_item_identifier_schemes)
        benchmark_values = {
            (row.scheme, row.value.strip())
            for row in benchmark.identifiers
            if row.scheme in allowed and row.verification_status == "verified"
        }
        competitor_values = {
            (row.scheme, row.value.strip())
            for row in competitor.identifiers
            if row.scheme in allowed and row.verification_status == "verified"
        }
        shared = sorted(benchmark_values & competitor_values)
        return shared[0][0] if shared else None

    @staticmethod
    def _eligible_price_bases(
        policy: MatchingPolicyV2,
        tier: MatchTier | None,
        evidence: Sequence[AttributeComparisonV2],
    ) -> tuple[str, ...]:
        if tier is None:
            return ()
        evidence_by_attribute = {row.attribute: row for row in evidence}
        configured_requirements = dict(policy.price_basis_requirements)
        eligible: list[str] = []
        for basis in policy.eligible_price_bases:
            requirements = configured_requirements.get(basis)
            if requirements is None and basis == "exact_package":
                requirements = tuple(
                    row.attribute for row in evidence if row.role == "required_exact"
                )
            if requirements is not None and not all(
                evidence_by_attribute[name].outcome in {"match", "within_tolerance"}
                for name in requirements
            ):
                continue
            eligible.append(basis)
        return tuple(dict.fromkeys(eligible))


@dataclass(frozen=True, slots=True)
class LocalOfferV2:
    retailer_id: str
    listing_id: str
    product_id: str
    location_scope_key: str
    location_kind: Literal["store", "service_area"]
    comparison_value: float | None
    observed_at: str | None
    store_number: str | None = None
    zipcode: str | None = None
    offer_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    distribution_count: int = 1

    def to_contract(self, *, distance_miles: float | None) -> JsonObject:
        return {
            "retailer_id": self.retailer_id,
            "listing_id": self.listing_id,
            "product_id": self.product_id,
            "location_scope_key": self.location_scope_key,
            "store_number": self.store_number,
            "zipcode": self.zipcode,
            "offer_id": self.offer_id,
            "observed_at": self.observed_at,
            "comparison_value": self.comparison_value,
            "distance_miles": round(distance_miles, 4) if distance_miles is not None else None,
        }


class LocalComparisonProjectorV2:
    """Materialize all eligible local offers and the policy-selected result."""

    def project(
        self,
        *,
        analysis_id: str,
        competitor_retailer_id: str,
        policy_revision: str,
        benchmark: LocalOfferV2,
        edges: Sequence[TieredMatchDecisionV2],
        competitor_offers: Sequence[LocalOfferV2],
        price_basis: Literal["exact_package", "normalized_unit", "random_weight_unit"],
        selection_policy: SelectionPolicy,
        radius_miles: float,
        generated_at: str,
    ) -> list[JsonObject]:
        _validate_datetime(generated_at)
        relevant = [edge for edge in edges if edge.benchmark.listing_id == benchmark.listing_id]
        approved = [
            edge
            for edge in relevant
            if edge.status in _APPROVED_STATUSES
            and edge.competitor.retailer_id == competitor_retailer_id
            and price_basis in edge.eligible_price_bases
        ]
        if not approved:
            reason: CoverageReason = (
                "match_review_required"
                if any(
                    edge.status in {"candidate", "unresolved", "needs_revalidation"}
                    for edge in relevant
                )
                else "no_eligible_match"
            )
            return [
                self._unscored_contract(
                    analysis_id=analysis_id,
                    competitor_retailer_id=competitor_retailer_id,
                    policy_revision=policy_revision,
                    benchmark=benchmark,
                    edge_id=None,
                    price_basis=price_basis,
                    reason=reason,
                    selection_policy=selection_policy,
                    generated_at=generated_at,
                )
            ]

        approved_by_competitor = {edge.competitor.listing_id: edge for edge in approved}
        observed_matches = [
            offer
            for offer in competitor_offers
            if offer.retailer_id == competitor_retailer_id
            and offer.listing_id in approved_by_competitor
        ]
        if not observed_matches:
            return [
                self._unscored_contract(
                    analysis_id=analysis_id,
                    competitor_retailer_id=competitor_retailer_id,
                    policy_revision=policy_revision,
                    benchmark=benchmark,
                    edge_id=approved[0].edge_id,
                    price_basis=price_basis,
                    reason="matched_product_not_observed",
                    selection_policy=selection_policy,
                    generated_at=generated_at,
                )
            ]

        geographic: list[tuple[LocalOfferV2, TieredMatchDecisionV2, float | None]] = []
        for offer in observed_matches:
            distance = _local_distance(benchmark, offer)
            if offer.location_kind == "service_area":
                if benchmark.zipcode and offer.zipcode and benchmark.zipcode == offer.zipcode:
                    geographic.append((offer, approved_by_competitor[offer.listing_id], None))
            elif distance is not None and distance <= radius_miles:
                geographic.append((offer, approved_by_competitor[offer.listing_id], distance))
            elif distance is None and benchmark.zipcode and benchmark.zipcode == offer.zipcode:
                geographic.append((offer, approved_by_competitor[offer.listing_id], None))
        if not geographic:
            return [
                self._unscored_contract(
                    analysis_id=analysis_id,
                    competitor_retailer_id=competitor_retailer_id,
                    policy_revision=policy_revision,
                    benchmark=benchmark,
                    edge_id=approved[0].edge_id,
                    price_basis=price_basis,
                    reason="no_geographic_overlap",
                    selection_policy=selection_policy,
                    generated_at=generated_at,
                )
            ]

        priced = [
            row
            for row in geographic
            if row[0].comparison_value is not None and row[0].comparison_value > 0
        ]
        if benchmark.comparison_value is None or benchmark.comparison_value <= 0 or not priced:
            return [
                self._unscored_contract(
                    analysis_id=analysis_id,
                    competitor_retailer_id=competitor_retailer_id,
                    policy_revision=policy_revision,
                    benchmark=benchmark,
                    edge_id=approved[0].edge_id,
                    price_basis=price_basis,
                    reason="price_unavailable_or_stale",
                    selection_policy=selection_policy,
                    generated_at=generated_at,
                )
            ]

        ranked = sorted(priced, key=lambda row: _selection_key(row, selection_policy))
        rows: list[JsonObject] = []
        for rank, (offer, edge, distance) in enumerate(ranked, start=1):
            competitor_value = float(offer.comparison_value or 0)
            benchmark_value = float(benchmark.comparison_value)
            gap = competitor_value - benchmark_value
            winner = (
                "parity"
                if abs(gap) < 0.000001
                else ("competitor_lower" if gap < 0 else "benchmark_lower")
            )
            seed = {
                "analysis": analysis_id,
                "edge": edge.edge_id,
                "basis": price_basis,
                "benchmark": benchmark.location_scope_key,
                "competitor": offer.location_scope_key,
                "offer": offer.offer_id,
            }
            rows.append(
                {
                    "schema_version": "2.0.0",
                    "comparison_id": f"comparison-{_checksum(seed)[:24]}",
                    "analysis_id": analysis_id,
                    "match_edge_id": edge.edge_id,
                    "competitor_retailer_id": competitor_retailer_id,
                    "policy_revision": policy_revision,
                    "benchmark": benchmark.to_contract(distance_miles=None),
                    "competitor": offer.to_contract(distance_miles=distance),
                    "price_basis": price_basis,
                    "coverage": {
                        "semantic": True,
                        "availability": True,
                        "price": True,
                        "reason": "comparable",
                    },
                    "selection": {
                        "status": "selected" if rank == 1 else "eligible_not_selected",
                        "policy": selection_policy,
                        "candidate_count": len(ranked),
                        "selection_rank": rank,
                    },
                    "result": {
                        "benchmark_value": benchmark_value,
                        "competitor_value": competitor_value,
                        "competitor_minus_benchmark": round(gap, 6),
                        "winner": winner,
                    },
                    "source_authority": "search_location_observation",
                    "generated_at": generated_at,
                }
            )
        return rows

    @staticmethod
    def _unscored_contract(
        *,
        analysis_id: str,
        competitor_retailer_id: str,
        policy_revision: str,
        benchmark: LocalOfferV2,
        edge_id: str | None,
        price_basis: str,
        reason: CoverageReason,
        selection_policy: SelectionPolicy,
        generated_at: str,
    ) -> JsonObject:
        seed = {
            "analysis": analysis_id,
            "edge": edge_id,
            "basis": price_basis,
            "benchmark": benchmark.location_scope_key,
            "reason": reason,
        }
        return {
            "schema_version": "2.0.0",
            "comparison_id": f"comparison-{_checksum(seed)[:24]}",
            "analysis_id": analysis_id,
            "match_edge_id": edge_id,
            "competitor_retailer_id": competitor_retailer_id,
            "policy_revision": policy_revision,
            "benchmark": benchmark.to_contract(distance_miles=None),
            "competitor": None,
            "price_basis": price_basis,
            "coverage": {
                "semantic": reason not in {"no_eligible_match", "match_review_required"},
                "availability": False,
                "price": False,
                "reason": reason,
            },
            "selection": {
                "status": "unscored",
                "policy": selection_policy,
                "candidate_count": 0,
                "selection_rank": None,
            },
            "result": None,
            "source_authority": "search_location_observation",
            "generated_at": generated_at,
        }


def reconcile_local_comparisons(rows: Sequence[Mapping[str, Any]]) -> JsonObject:
    """Reconcile atomic rows without double-counting benchmark stores."""

    selected = [row for row in rows if row["selection"]["status"] == "selected"]
    selected_keys: set[tuple[str, str, str]] = set()
    for row in selected:
        key = (
            str(row["benchmark"]["listing_id"]),
            str(row["benchmark"]["location_scope_key"]),
            str(row["price_basis"]),
        )
        if key in selected_keys:
            raise ValueError("more than one controlling comparison exists for a product-location")
        selected_keys.add(key)
    losing_product_locations = [
        row for row in selected if row.get("result", {}).get("winner") == "competitor_lower"
    ]
    losing_store_keys = {
        str(row["benchmark"]["location_scope_key"]) for row in losing_product_locations
    }
    scored_store_keys = {str(row["benchmark"]["location_scope_key"]) for row in selected}
    unscored = [row for row in rows if row["selection"]["status"] == "unscored"]
    reason_counts: dict[str, int] = {}
    for row in unscored:
        reason = str(row["coverage"]["reason"])
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
    return {
        "selected_product_locations": len(selected),
        "unique_scored_stores": len(scored_store_keys),
        "losing_product_locations": len(losing_product_locations),
        "unique_losing_stores": len(losing_store_keys),
        "unscored_product_locations": len(unscored),
        "unscored_reason_counts": dict(sorted(reason_counts.items())),
        "reconciled": True,
    }


def _brand_relationship(benchmark: ListingEvidence, competitor: ListingEvidence) -> str:
    if (
        benchmark.brand
        and competitor.brand
        and benchmark.brand_verified
        and competitor.brand_verified
        and _normalized_scalar(benchmark.brand) == _normalized_scalar(competitor.brand)
    ):
        return "same_verified_brand"
    if benchmark.brand_type == competitor.brand_type == "private_label":
        return "private_label_to_private_label"
    if {benchmark.brand_type, competitor.brand_type} == {"private_label", "national"}:
        return "private_label_to_national_brand"
    if "regional" in {benchmark.brand_type, competitor.brand_type}:
        return "regional_brand_relationship"
    if benchmark.brand_type == competitor.brand_type == "national":
        return "different_national_brands"
    if benchmark.brand is None and competitor.brand is None:
        return "brand_unknown"
    return "unbranded_or_generic"


def _is_unknown_or_conflicted(value: AttributeValue | None) -> bool:
    return value is None or value.value is None or value.review_status == "conflicted"


def _selection_key(
    row: tuple[LocalOfferV2, TieredMatchDecisionV2, float | None],
    policy: SelectionPolicy,
) -> tuple[Any, ...]:
    offer, edge, distance = row
    value = float(offer.comparison_value or math.inf)
    safe_distance = distance if distance is not None else 0.0
    if policy == "nearest_eligible_offer":
        return (safe_distance, value, offer.location_scope_key, edge.edge_id)
    if policy == "representative_assortment":
        return (-offer.distribution_count, value, safe_distance, offer.location_scope_key)
    return (value, safe_distance, offer.location_scope_key, edge.edge_id)


def _local_distance(benchmark: LocalOfferV2, competitor: LocalOfferV2) -> float | None:
    benchmark_latitude = benchmark.latitude
    benchmark_longitude = benchmark.longitude
    competitor_latitude = competitor.latitude
    competitor_longitude = competitor.longitude
    if (
        benchmark_latitude is None
        or benchmark_longitude is None
        or competitor_latitude is None
        or competitor_longitude is None
    ):
        return None
    latitude_1 = math.radians(benchmark_latitude)
    latitude_2 = math.radians(competitor_latitude)
    latitude_delta = latitude_2 - latitude_1
    longitude_delta = math.radians(competitor_longitude - benchmark_longitude)
    haversine = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(latitude_1) * math.cos(latitude_2) * math.sin(longitude_delta / 2) ** 2
    )
    return 3958.7613 * 2 * math.asin(math.sqrt(haversine))


def _validate_datetime(value: str) -> None:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid ISO datetime {value!r}") from exc
