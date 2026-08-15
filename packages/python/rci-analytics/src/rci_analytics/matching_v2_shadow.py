"""Shadow-mode adapters from current classified Search evidence to Matching v2."""

from __future__ import annotations

import hashlib
import heapq
import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from rci_analytics.matching_v2 import (
    AttributeValue,
    DeterministicMatchEngineV2,
    IdentifierEvidence,
    ListingEvidence,
    MatchingPolicyV2,
    TieredMatchDecisionV2,
    compile_matching_policy_v2,
)
from rci_analytics.models import ClassifiedOffer, JsonObject
from rci_analytics.product_pack import ProductPack


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)


def _source_reliability(source: str) -> float:
    return {
        "human": 1.0,
        "manufacturer": 1.0,
        "pdp": 0.95,
        "search": 0.8,
        "retailer_pack": 0.9,
        "product_pack_constant": 0.9,
        "product_pack_default": 0.4,
        "unresolved": 0.0,
    }.get(source, 0.7)


def _brand_type(attributes: Mapping[str, Any]) -> str:
    governance = attributes.get("_brand_governance")
    if isinstance(governance, dict):
        value = str(governance.get("role") or governance.get("brand_type") or "unclassified")
        if value in {"private_label", "regional", "national"}:
            return value
    return "unclassified"


def _brand_is_verified(attributes: Mapping[str, Any]) -> bool:
    governance = attributes.get("_brand_governance")
    return isinstance(governance, dict) and governance.get("status") == "resolved"


def _identifier_rows(rows: Sequence[ClassifiedOffer]) -> tuple[IdentifierEvidence, ...]:
    found: dict[tuple[str, str], IdentifierEvidence] = {}
    for item in rows:
        offer = item.offer
        found[("retailer_product_id", offer.retailer_product_id)] = IdentifierEvidence(
            scheme="retailer_product_id",
            value=offer.retailer_product_id,
            verification_status="observed",
            source="search",
        )
        raw = offer.raw
        for scheme in ("gtin", "upc", "asin", "manufacturer_item_id", "sku"):
            value = raw.get(scheme)
            if value not in (None, ""):
                found[(scheme, str(value))] = IdentifierEvidence(
                    scheme=scheme,
                    value=str(value),
                    verification_status="observed",
                    source="search",
                )
    return tuple(sorted(found.values(), key=lambda row: (row.scheme, row.value)))


@dataclass(slots=True)
class _ListingAccumulatorState:
    retailer_id: str
    retailer_product_id: str
    attribute_values: dict[str, dict[str, Any]] = field(default_factory=lambda: defaultdict(dict))
    attribute_sources: dict[str, Counter[str]] = field(default_factory=lambda: defaultdict(Counter))
    identifiers: dict[tuple[str, str], IdentifierEvidence] = field(default_factory=dict)
    titles: Counter[str] = field(default_factory=Counter)
    image_urls: Counter[str] = field(default_factory=Counter)
    product_urls: Counter[str] = field(default_factory=Counter)
    brands: set[str] = field(default_factory=set)
    brand_types: Counter[str] = field(default_factory=Counter)
    branded_rows: int = 0
    verified_brand_rows: int = 0


class ListingEvidenceAccumulatorV2:
    """Collapse placement evidence incrementally without retaining every store row."""

    def __init__(self, pack: ProductPack) -> None:
        self._pack = pack
        self._states: dict[tuple[str, str], _ListingAccumulatorState] = {}

    def add(self, item: ClassifiedOffer) -> None:
        offer = item.offer
        if not item.in_scope or offer.price is None or offer.price <= 0:
            return
        key = (offer.retailer_id, offer.retailer_product_id)
        state = self._states.setdefault(
            key,
            _ListingAccumulatorState(
                retailer_id=offer.retailer_id,
                retailer_product_id=offer.retailer_product_id,
            ),
        )
        for definition in self._pack.attributes:
            name = str(definition["name"])
            value = item.attributes.get(name)
            if value is None or value in definition.get("unknown_values", []):
                continue
            state.attribute_values[name][_canonical(value)] = value
            provenance = item.attributes.get("_attribute_provenance")
            source = (
                str(provenance.get(name) or "search") if isinstance(provenance, dict) else "search"
            )
            state.attribute_sources[name][source] += 1

        for identifier in _identifier_rows((item,)):
            state.identifiers[(identifier.scheme, identifier.value)] = identifier
        state.titles[offer.title] += 1
        if offer.image_url:
            state.image_urls[offer.image_url] += 1
        if offer.product_url:
            state.product_urls[offer.product_url] += 1
        brand = item.attributes.get("brand") or offer.brand
        if brand:
            state.brands.add(str(brand).strip())
            state.branded_rows += 1
            if _brand_is_verified(item.attributes):
                state.verified_brand_rows += 1
        state.brand_types[_brand_type(item.attributes)] += 1

    def extend(self, offers: Iterable[ClassifiedOffer]) -> None:
        for item in offers:
            self.add(item)

    def listings(self, retailer_id: str) -> tuple[ListingEvidence, ...]:
        results: list[ListingEvidence] = []
        for (state_retailer, product_id), state in sorted(self._states.items()):
            if state_retailer != retailer_id:
                continue
            attributes: dict[str, AttributeValue] = {}
            for definition in self._pack.attributes:
                name = str(definition["name"])
                values = state.attribute_values.get(name, {})
                sources = state.attribute_sources.get(name, Counter())
                if len(values) == 1:
                    source = sources.most_common(1)[0][0] if sources else "search"
                    attributes[name] = AttributeValue(
                        next(iter(values.values())),
                        source,
                        _source_reliability(source),
                        "verified",
                    )
                elif len(values) > 1:
                    attributes[name] = AttributeValue(
                        None,
                        "search_attribute_conflict",
                        0,
                        "conflicted",
                    )
            brand = next(iter(state.brands)) if len(state.brands) == 1 else None
            brand_type = (
                sorted(state.brand_types.items(), key=lambda row: (-row[1], row[0]))[0][0]
                if state.brand_types
                else "unclassified"
            )
            results.append(
                ListingEvidence(
                    listing_id=f"{retailer_id}:{product_id}",
                    retailer_id=retailer_id,
                    retailer_product_id=product_id,
                    attributes=attributes,
                    identifiers=tuple(
                        sorted(state.identifiers.values(), key=lambda row: (row.scheme, row.value))
                    ),
                    title=_representative_text(state.titles),
                    image_url=_representative_text(state.image_urls),
                    product_url=_representative_text(state.product_urls),
                    brand=brand,
                    brand_type=brand_type,  # type: ignore[arg-type]
                    brand_verified=bool(brand) and state.branded_rows == state.verified_brand_rows,
                )
            )
        return tuple(results)


def _representative_text(values: Counter[str]) -> str | None:
    if not values:
        return None
    return sorted(values.items(), key=lambda row: (-row[1], row[0]))[0][0]


def build_listing_evidence_v2(
    offers: Iterable[ClassifiedOffer],
    *,
    pack: ProductPack,
    retailer_id: str,
) -> tuple[ListingEvidence, ...]:
    """Collapse positive Search placements into conservative listing evidence.

    Conflicting product-level attributes are retained as conflicted unknowns so
    they cannot create automatic exact matches. Search placements remain
    separate from the listing identity in the underlying source artifacts.
    """

    accumulator = ListingEvidenceAccumulatorV2(pack)
    accumulator.extend(offers)
    return accumulator.listings(retailer_id)


@dataclass(frozen=True, slots=True)
class MatchingShadowResultV2:
    schema_version: str
    product_pack_id: str
    product_pack_version: str
    profile_id: str
    policy_checksum: str
    benchmark_retailer_id: str
    competitor_retailer_id: str
    benchmark_listings: int
    competitor_listings: int
    possible_pairs: int
    evaluated_pairs: int
    blocked_pairs: int
    edges: tuple[TieredMatchDecisionV2, ...]
    blocked_review_edges: tuple[TieredMatchDecisionV2, ...] = ()

    def summary(self) -> JsonObject:
        tiers = Counter(edge.tier or "none" for edge in self.edges)
        statuses = Counter(edge.status for edge in self.edges)
        return {
            "schema_version": self.schema_version,
            "product_pack_id": self.product_pack_id,
            "product_pack_version": self.product_pack_version,
            "profile_id": self.profile_id,
            "policy_checksum": self.policy_checksum,
            "benchmark_retailer_id": self.benchmark_retailer_id,
            "competitor_retailer_id": self.competitor_retailer_id,
            "benchmark_listings": self.benchmark_listings,
            "competitor_listings": self.competitor_listings,
            "possible_pairs": self.possible_pairs,
            "evaluated_pairs": self.evaluated_pairs,
            "blocked_pairs": self.blocked_pairs,
            "blocked_review_sample": len(self.blocked_review_edges),
            "tier_counts": dict(sorted(tiers.items())),
            "status_counts": dict(sorted(statuses.items())),
            "auto_approved_edges": statuses.get("auto_approved", 0),
            "review_edges": sum(
                statuses.get(status, 0)
                for status in ("candidate", "unresolved", "needs_revalidation")
            ),
            "not_comparable_edges": statuses.get("not_comparable", 0),
        }


class MatchingShadowEvaluatorV2:
    """Run deterministic v2 evaluation without mutating authoritative results."""

    def __init__(
        self,
        pack: ProductPack,
        profile_id: str,
        *,
        policy: MatchingPolicyV2 | None = None,
    ) -> None:
        self._pack = pack
        self._profile_id = profile_id
        self._policy = policy or compile_matching_policy_v2(pack, profile_id)
        self._engine = DeterministicMatchEngineV2()

    @property
    def policy(self) -> MatchingPolicyV2:
        return self._policy

    def evaluate(
        self,
        offers: Iterable[ClassifiedOffer],
        *,
        benchmark_retailer_id: str,
        competitor_retailer_id: str,
        decided_at: str,
    ) -> MatchingShadowResultV2:
        offer_rows = tuple(offers)
        benchmark = build_listing_evidence_v2(
            offer_rows,
            pack=self._pack,
            retailer_id=benchmark_retailer_id,
        )
        competitor = build_listing_evidence_v2(
            offer_rows,
            pack=self._pack,
            retailer_id=competitor_retailer_id,
        )
        return self.evaluate_listings(
            benchmark,
            competitor,
            benchmark_retailer_id=benchmark_retailer_id,
            competitor_retailer_id=competitor_retailer_id,
            decided_at=decided_at,
        )

    def evaluate_listings(
        self,
        benchmark: Sequence[ListingEvidence],
        competitor: Sequence[ListingEvidence],
        *,
        benchmark_retailer_id: str,
        competitor_retailer_id: str,
        decided_at: str,
        maximum_candidate_pairs: int | None = None,
        blocked_review_limit: int = 40,
    ) -> MatchingShadowResultV2:
        """Generate candidates and retain a deterministic hard-negative review sample."""

        if blocked_review_limit < 0:
            raise ValueError("blocked review limit cannot be negative")

        edges: list[TieredMatchDecisionV2] = []
        blocked_sample: list[tuple[int, str, int, int]] = []
        possible_pairs = len(benchmark) * len(competitor)
        candidate_indexes = self._candidate_indexes(competitor)
        all_competitor_indexes = set(range(len(competitor)))
        for benchmark_index, benchmark_listing in enumerate(benchmark):
            eligible_indexes = set(all_competitor_indexes)
            for rule in self._policy.attributes:
                if rule.role != "hard_blocker":
                    continue
                value = benchmark_listing.attributes.get(rule.name)
                if value is None or value.value is None or value.review_status == "conflicted":
                    continue
                values, unknown = candidate_indexes[rule.name]
                eligible_indexes &= values.get(_canonical(value.value), set()) | unknown
            if blocked_review_limit:
                for competitor_index in all_competitor_indexes - eligible_indexes:
                    competitor_listing = competitor[competitor_index]
                    pair_key = f"{benchmark_listing.listing_id}|{competitor_listing.listing_id}"
                    rank = int(hashlib.sha256(pair_key.encode()).hexdigest(), 16)
                    candidate = (-rank, pair_key, benchmark_index, competitor_index)
                    if len(blocked_sample) < blocked_review_limit:
                        heapq.heappush(blocked_sample, candidate)
                    elif rank < -blocked_sample[0][0]:
                        heapq.heapreplace(blocked_sample, candidate)
            for index in sorted(eligible_indexes):
                if maximum_candidate_pairs is not None and len(edges) >= maximum_candidate_pairs:
                    raise ValueError(
                        "matching v2 shadow candidate limit exceeded: "
                        f"{maximum_candidate_pairs} retained pairs"
                    )
                edges.append(
                    self._engine.evaluate(
                        benchmark_listing,
                        competitor[index],
                        self._policy,
                        decided_at=decided_at,
                    )
                )
        blocked_review_edges = tuple(
            self._engine.evaluate(
                benchmark[benchmark_index],
                competitor[competitor_index],
                self._policy,
                decided_at=decided_at,
            )
            for _, _, benchmark_index, competitor_index in sorted(
                blocked_sample, key=lambda row: (-row[0], row[1])
            )
        )
        return MatchingShadowResultV2(
            schema_version="2.0.0-shadow",
            product_pack_id=self._pack.id,
            product_pack_version=self._pack.version,
            profile_id=self._profile_id,
            policy_checksum=self._policy.checksum,
            benchmark_retailer_id=benchmark_retailer_id,
            competitor_retailer_id=competitor_retailer_id,
            benchmark_listings=len(benchmark),
            competitor_listings=len(competitor),
            possible_pairs=possible_pairs,
            evaluated_pairs=len(edges),
            blocked_pairs=possible_pairs - len(edges),
            edges=tuple(edges),
            blocked_review_edges=blocked_review_edges,
        )

    def _candidate_indexes(
        self, competitor: Sequence[ListingEvidence]
    ) -> dict[str, tuple[dict[str, set[int]], set[int]]]:
        indexes: dict[str, tuple[dict[str, set[int]], set[int]]] = {}
        for rule in self._policy.attributes:
            if rule.role != "hard_blocker":
                continue
            values: dict[str, set[int]] = defaultdict(set)
            unknown: set[int] = set()
            for index, listing in enumerate(competitor):
                value = listing.attributes.get(rule.name)
                if value is None or value.value is None or value.review_status == "conflicted":
                    unknown.add(index)
                else:
                    values[_canonical(value.value)].add(index)
            indexes[rule.name] = (values, unknown)
        return indexes


def shadow_result_checksum(result: MatchingShadowResultV2) -> str:
    document = {
        **result.summary(),
        "edges": [edge.to_contract() for edge in result.edges],
        "blocked_review_edges": [edge.to_contract() for edge in result.blocked_review_edges],
    }
    return hashlib.sha256(_canonical(document).encode()).hexdigest()
