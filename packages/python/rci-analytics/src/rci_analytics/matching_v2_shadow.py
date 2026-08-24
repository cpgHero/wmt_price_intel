"""Shadow-mode adapters from current classified Search evidence to Matching v2."""

from __future__ import annotations

import hashlib
import heapq
import json
import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from rci_analytics.classification import OfferClassifier
from rci_analytics.matching_v2 import (
    AttributeValue,
    DeterministicMatchEngineV2,
    IdentifierEvidence,
    ListingEvidence,
    ListingLocationEvidence,
    MatchingPolicyV2,
    TieredMatchDecisionV2,
    compile_matching_policy_v2,
)
from rci_analytics.models import ClassifiedOffer, JsonObject
from rci_analytics.product_pack import ProductPack


def _canonical(value: Any) -> str:
    if not isinstance(value, bool) and isinstance(value, int | float | Decimal):
        try:
            return f"number:{Decimal(str(value)).normalize()}"
        except InvalidOperation:
            pass
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
        "search_override_correction": 0.8,
        "unresolved": 0.0,
    }.get(source, 0.7)


def _retrieval_context(value: Any) -> str | None:
    normalized = " ".join(str(value or "").casefold().split())
    return normalized or None


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
    pdp_titles: Counter[str] = field(default_factory=Counter)
    image_urls: Counter[str] = field(default_factory=Counter)
    product_urls: Counter[str] = field(default_factory=Counter)
    brands: set[str] = field(default_factory=set)
    brand_types: Counter[str] = field(default_factory=Counter)
    branded_rows: int = 0
    verified_brand_rows: int = 0
    brand_governance: Counter[str] = field(default_factory=Counter)
    seller_governance: Counter[str] = field(default_factory=Counter)
    pdp_evidence: Counter[str] = field(default_factory=Counter)
    retrieval_contexts: set[str] = field(default_factory=set)
    locations: dict[str, ListingLocationEvidence] = field(default_factory=dict)


class ListingEvidenceAccumulatorV2:
    """Collapse placement evidence incrementally without retaining every store row."""

    def __init__(self, pack: ProductPack) -> None:
        self._pack = pack
        self._observed_classifier = OfferClassifier(pack)
        self._observed_attribute_cache: dict[tuple[str, str, str, str, str], Any] = {}
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
        location_key = "|".join(
            (
                str(offer.retailer_id),
                str(offer.zipcode or "unknown"),
                str(offer.store_number or f"zip:{offer.zipcode or 'unknown'}"),
            )
        )
        if location_key:
            state.locations[location_key] = ListingLocationEvidence(
                scope_key=location_key,
                zipcode=offer.zipcode,
                latitude=offer.latitude,
                longitude=offer.longitude,
            )
        context = _retrieval_context(offer.raw.get("collection_keyword"))
        if context:
            state.retrieval_contexts.add(context)
        for definition in self._pack.attributes:
            name = str(definition["name"])
            value = item.attributes.get(name)
            provenance = item.attributes.get("_attribute_provenance")
            source = (
                str(provenance.get(name) or "search") if isinstance(provenance, dict) else "search"
            )
            observed_brand = str(item.attributes.get("brand") or offer.brand or "")
            observed_key = (
                offer.retailer_id,
                offer.retailer_product_id,
                name,
                offer.title,
                observed_brand,
            )
            if observed_key not in self._observed_attribute_cache:
                self._observed_attribute_cache[observed_key] = (
                    self._observed_classifier.observed_attribute(
                        name,
                        offer,
                        brand=observed_brand or None,
                    )
                )
            observed_value = self._observed_attribute_cache[observed_key]
            if (
                source == "product_pack_override"
                and observed_value is not None
                and _canonical(observed_value) != _canonical(value)
            ):
                value = observed_value
                source = "search_override_correction"
            allowed_values = definition.get("allowed_values")
            if (
                value is None
                or value in definition.get("unknown_values", [])
                or (
                    isinstance(allowed_values, list)
                    and allowed_values
                    and value not in allowed_values
                )
            ):
                continue
            state.attribute_values[name][_canonical(value)] = value
            state.attribute_sources[name][source] += 1

        for identifier in _identifier_rows((item,)):
            state.identifiers[(identifier.scheme, identifier.value)] = identifier
        state.titles[offer.title] += 1
        if offer.image_url:
            state.image_urls[offer.image_url] += 1
        if offer.product_url:
            state.product_urls[offer.product_url] += 1
        pdp_evidence = item.attributes.get("_pdp_evidence")
        if isinstance(pdp_evidence, dict):
            state.pdp_evidence[_canonical(pdp_evidence)] += 1
            if pdp_evidence.get("name"):
                state.pdp_titles[str(pdp_evidence["name"])] += 1
            if pdp_evidence.get("image_url"):
                state.image_urls[str(pdp_evidence["image_url"])] += 1
            pdp_image_urls = pdp_evidence.get("image_urls")
            if isinstance(pdp_image_urls, list):
                for image_url in pdp_image_urls:
                    value = str(image_url or "").strip()
                    if value:
                        state.image_urls[value] += 1
            if pdp_evidence.get("url"):
                state.product_urls[str(pdp_evidence["url"])] += 1
        brand_governance = item.attributes.get("_brand_governance")
        if isinstance(brand_governance, dict):
            state.brand_governance[_canonical(brand_governance)] += 1
        seller_governance = item.attributes.get("_seller_governance")
        if isinstance(seller_governance, dict):
            state.seller_governance[_canonical(seller_governance)] += 1
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
                    title=_representative_text(state.pdp_titles)
                    or _representative_text(state.titles),
                    image_url=_representative_text(state.image_urls),
                    image_urls=tuple(
                        value
                        for value, _count in sorted(
                            state.image_urls.items(), key=lambda row: (-row[1], row[0])
                        )
                    ),
                    product_url=_representative_text(state.product_urls),
                    brand=brand,
                    brand_type=brand_type,  # type: ignore[arg-type]
                    brand_verified=bool(brand) and state.branded_rows == state.verified_brand_rows,
                    brand_governance=_representative_document(state.brand_governance),
                    seller_governance=_representative_document(state.seller_governance),
                    pdp_evidence=_representative_document(state.pdp_evidence),
                    retrieval_contexts=tuple(sorted(state.retrieval_contexts)),
                    observed_location_count=len(state.locations),
                    observed_locations=tuple(
                        state.locations[key] for key in sorted(state.locations)
                    ),
                )
            )
        return tuple(results)


def _representative_text(values: Counter[str]) -> str | None:
    if not values:
        return None
    return sorted(values.items(), key=lambda row: (-row[1], row[0]))[0][0]


def _representative_document(values: Counter[str]) -> dict[str, Any]:
    selected = _representative_text(values)
    if selected is None:
        return {}
    value = json.loads(selected)
    return dict(value) if isinstance(value, dict) else {}


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
    attribute_blocked_pairs: int = 0
    geography_blocked_pairs: int = 0
    retrieval_blocked_pairs: int = 0

    def summary(self) -> JsonObject:
        tiers = Counter(edge.tier or "none" for edge in self.edges)
        statuses = Counter(edge.status for edge in self.edges)
        benchmark_with_candidates = {edge.benchmark.retailer_product_id for edge in self.edges}
        competitor_with_candidates = {edge.competitor.retailer_product_id for edge in self.edges}
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
            "benchmark_listings_with_candidates": len(benchmark_with_candidates),
            "benchmark_listings_without_candidates": (
                self.benchmark_listings - len(benchmark_with_candidates)
            ),
            "competitor_listings_with_candidates": len(competitor_with_candidates),
            "possible_pairs": self.possible_pairs,
            "evaluated_pairs": self.evaluated_pairs,
            "blocked_pairs": self.blocked_pairs,
            "attribute_blocked_pairs": self.attribute_blocked_pairs,
            "geography_blocked_pairs": self.geography_blocked_pairs,
            "retrieval_blocked_pairs": self.retrieval_blocked_pairs,
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
        geography_indexes = self._geographic_candidate_indexes(benchmark, competitor)
        attribute_blocked_pairs = 0
        geography_blocked_pairs = 0
        retrieval_blocked_pairs = 0
        for benchmark_index, benchmark_listing in enumerate(benchmark):
            eligible_indexes = set(all_competitor_indexes)
            for rule in self._policy.attributes:
                if rule.role != "hard_blocker":
                    continue
                value = benchmark_listing.attributes.get(rule.name)
                if value is None or value.value is None or value.review_status == "conflicted":
                    if (
                        rule.unknown_is_blocking
                        and not self._policy.candidate_include_unknown_hard_blockers
                    ):
                        eligible_indexes.clear()
                    continue
                if rule.numeric_tolerance is not None and not isinstance(value.value, bool):
                    within_tolerance: set[int] = set()
                    for index, competitor_listing in enumerate(competitor):
                        candidate_value = competitor_listing.attributes.get(rule.name)
                        if (
                            candidate_value is None
                            or candidate_value.value is None
                            or candidate_value.review_status == "conflicted"
                        ):
                            if (
                                not rule.unknown_is_blocking
                                or self._policy.candidate_include_unknown_hard_blockers
                            ):
                                within_tolerance.add(index)
                            continue
                        try:
                            gap = abs(
                                Decimal(str(value.value)) - Decimal(str(candidate_value.value))
                            )
                        except InvalidOperation:
                            continue
                        if gap <= Decimal(str(rule.numeric_tolerance)):
                            within_tolerance.add(index)
                    eligible_indexes &= within_tolerance
                    continue
                values, unknown = candidate_indexes[rule.name]
                eligible_indexes &= values.get(_canonical(value.value), set()) | unknown
            attribute_eligible_indexes = set(eligible_indexes)
            attribute_blocked_pairs += len(all_competitor_indexes - attribute_eligible_indexes)
            if geography_indexes is not None:
                geographically_eligible = geography_indexes[benchmark_index]
                geography_blocked_pairs += len(eligible_indexes - geographically_eligible)
                eligible_indexes &= geographically_eligible
            if self._policy.candidate_retrieval_mode == "lexical_top_k":
                retrieved = self._lexical_candidates(
                    benchmark_listing,
                    competitor,
                    eligible_indexes,
                )
                retrieval_blocked_pairs += len(eligible_indexes - retrieved)
                eligible_indexes = retrieved
            elif self._policy.candidate_retrieval_mode == "structured_high_recall":
                retrieved = self._structured_high_recall_candidates(
                    benchmark_listing,
                    competitor,
                    eligible_indexes,
                )
                retrieval_blocked_pairs += len(eligible_indexes - retrieved)
                eligible_indexes = retrieved
            if blocked_review_limit:
                for competitor_index in all_competitor_indexes - attribute_eligible_indexes:
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
            attribute_blocked_pairs=attribute_blocked_pairs,
            geography_blocked_pairs=geography_blocked_pairs,
            retrieval_blocked_pairs=retrieval_blocked_pairs,
        )

    def _lexical_candidates(
        self,
        benchmark: ListingEvidence,
        competitor: Sequence[ListingEvidence],
        eligible_indexes: set[int],
    ) -> set[int]:
        """Retrieve a bounded, deterministic proposal set without deciding comparability."""

        benchmark_tokens = _candidate_tokens(benchmark, self._policy.candidate_retrieval_stop_words)
        ranked: list[tuple[float, str, int]] = []
        for index in eligible_indexes:
            candidate = competitor[index]
            if _shares_allowed_identifier(benchmark, candidate, self._policy):
                similarity = 1.0
            else:
                candidate_tokens = _candidate_tokens(
                    candidate, self._policy.candidate_retrieval_stop_words
                )
                union = benchmark_tokens | candidate_tokens
                similarity = len(benchmark_tokens & candidate_tokens) / len(union) if union else 0.0
            if similarity >= self._policy.candidate_retrieval_minimum_similarity:
                ranked.append((-similarity, candidate.listing_id, index))
        ranked.sort()
        return {
            index
            for _score, _listing_id, index in ranked[
                : self._policy.candidate_retrieval_maximum_per_benchmark
            ]
        }

    def _structured_high_recall_candidates(
        self,
        benchmark: ListingEvidence,
        competitor: Sequence[ListingEvidence],
        eligible_indexes: set[int],
    ) -> set[int]:
        """Retrieve evidence-bearing candidates without letting title rank erase brand lanes.

        Known hard conflicts have already been removed before this method runs. This
        stage therefore ranks only potentially compatible products. Structured
        attribute agreement and shared collection-query context are retrieval
        evidence; title similarity and brand type affect ordering. None of these
        signals can certify a relationship or override a known hard conflict.
        """

        attribute_names = self._policy.candidate_retrieval_structured_attributes
        benchmark_tokens = _candidate_tokens(
            benchmark,
            self._policy.candidate_retrieval_stop_words,
            attribute_names=attribute_names,
            preserve_numeric=self._policy.candidate_retrieval_preserve_numeric_tokens,
        )
        ranked: list[tuple[int, int, int, int, float, str, int]] = []
        benchmark_contexts = set(benchmark.retrieval_contexts)
        for index in eligible_indexes:
            candidate = competitor[index]
            candidate_contexts = set(candidate.retrieval_contexts)
            shared_contexts = benchmark_contexts & candidate_contexts
            if (
                self._policy.candidate_retrieval_context_mode == "require_when_available"
                and benchmark_contexts
                and candidate_contexts
                and not shared_contexts
            ):
                continue
            shares_identifier = _shares_allowed_identifier(benchmark, candidate, self._policy)
            structured_matches = _structured_attribute_match_count(
                benchmark,
                candidate,
                attribute_names,
            )
            candidate_tokens = _candidate_tokens(
                candidate,
                self._policy.candidate_retrieval_stop_words,
                attribute_names=attribute_names,
                preserve_numeric=self._policy.candidate_retrieval_preserve_numeric_tokens,
            )
            union = benchmark_tokens | candidate_tokens
            similarity = len(benchmark_tokens & candidate_tokens) / len(union) if union else 0.0
            if not (
                shares_identifier
                or (
                    self._policy.candidate_retrieval_context_mode != "disabled"
                    and bool(shared_contexts)
                )
                or structured_matches >= self._policy.candidate_retrieval_minimum_structured_matches
                or similarity >= self._policy.candidate_retrieval_minimum_similarity
            ):
                continue
            same_brand_lane = int(benchmark.brand_type == candidate.brand_type)
            ranked.append(
                (
                    -int(shares_identifier),
                    -(
                        len(shared_contexts)
                        if self._policy.candidate_retrieval_context_mode != "disabled"
                        else 0
                    ),
                    -structured_matches,
                    -same_brand_lane,
                    -similarity,
                    candidate.listing_id,
                    index,
                )
            )

        ranked.sort()
        maximum = self._policy.candidate_retrieval_maximum_per_benchmark
        lane_minimum = self._policy.candidate_retrieval_minimum_per_brand_lane
        selected: set[int] = set()
        if lane_minimum:
            lanes: dict[str, list[tuple[int, int, int, int, float, str, int]]] = defaultdict(list)
            for row in ranked:
                lanes[competitor[row[-1]].brand_type].append(row)
            lane_order = ("private_label", "national", "regional", "unclassified")
            for position in range(lane_minimum):
                for lane in lane_order:
                    rows = lanes.get(lane, ())
                    if position < len(rows) and len(selected) < maximum:
                        selected.add(rows[position][-1])
        for row in ranked:
            if len(selected) >= maximum:
                break
            selected.add(row[-1])
        return selected

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
                    if (
                        not rule.unknown_is_blocking
                        or self._policy.candidate_include_unknown_hard_blockers
                    ):
                        unknown.add(index)
                else:
                    values[_canonical(value.value)].add(index)
            indexes[rule.name] = (values, unknown)
        return indexes

    def _geographic_candidate_indexes(
        self,
        benchmark: Sequence[ListingEvidence],
        competitor: Sequence[ListingEvidence],
    ) -> tuple[set[int], ...] | None:
        if self._policy.candidate_geography_mode == "disabled":
            return None

        if competitor and competitor[0].retailer_id in set(
            self._policy.candidate_service_area_retailer_ids
        ):
            by_zip: dict[str, set[int]] = defaultdict(set)
            for index, listing in enumerate(competitor):
                for location in listing.observed_locations:
                    if location.zipcode:
                        by_zip[location.zipcode].add(index)
            return tuple(
                set().union(
                    *(
                        by_zip.get(location.zipcode, set())
                        for location in listing.observed_locations
                        if location.zipcode is not None
                    )
                )
                if listing.observed_locations
                else set()
                for listing in benchmark
            )

        radius = self._policy.candidate_physical_radius_miles
        cell_size = radius / 69.0
        spatial: dict[tuple[int, int], list[tuple[int, float, float]]] = defaultdict(list)
        for index, listing in enumerate(competitor):
            for location in listing.observed_locations:
                if location.latitude is None or location.longitude is None:
                    continue
                cell = (
                    math.floor(location.latitude / cell_size),
                    math.floor(location.longitude / cell_size),
                )
                spatial[cell].append((index, location.latitude, location.longitude))

        results: list[set[int]] = []
        for listing in benchmark:
            matched: set[int] = set()
            for location in listing.observed_locations:
                if location.latitude is None or location.longitude is None:
                    continue
                center = (
                    math.floor(location.latitude / cell_size),
                    math.floor(location.longitude / cell_size),
                )
                longitude_reach = max(
                    1,
                    math.ceil(
                        1
                        / max(
                            math.cos(math.radians(location.latitude)),
                            0.2,
                        )
                    ),
                )
                for latitude_cell in range(center[0] - 1, center[0] + 2):
                    for longitude_cell in range(
                        center[1] - longitude_reach,
                        center[1] + longitude_reach + 1,
                    ):
                        for index, latitude, longitude in spatial.get(
                            (latitude_cell, longitude_cell), ()
                        ):
                            if (
                                _distance_miles(
                                    location.latitude,
                                    location.longitude,
                                    latitude,
                                    longitude,
                                )
                                <= radius
                            ):
                                matched.add(index)
            if (
                not matched
                and self._policy.candidate_missing_location_policy == "allow"
                and not listing.observed_locations
            ):
                matched.update(range(len(competitor)))
            results.append(matched)
        return tuple(results)


def _structured_attribute_match_count(
    benchmark: ListingEvidence,
    competitor: ListingEvidence,
    attribute_names: tuple[str, ...],
) -> int:
    matches = 0
    for name in attribute_names:
        benchmark_value = benchmark.attributes.get(name)
        competitor_value = competitor.attributes.get(name)
        if (
            benchmark_value is None
            or benchmark_value.value is None
            or benchmark_value.review_status == "conflicted"
            or competitor_value is None
            or competitor_value.value is None
            or competitor_value.review_status == "conflicted"
        ):
            continue
        if _canonical(benchmark_value.value) == _canonical(competitor_value.value):
            matches += 1
    return matches


def _candidate_tokens(
    listing: ListingEvidence,
    stop_words: tuple[str, ...],
    *,
    attribute_names: tuple[str, ...] = ("active_ingredient",),
    preserve_numeric: bool = False,
) -> set[str]:
    text_values = [listing.title or ""]
    attribute_tokens: set[str] = set()
    for name in attribute_names:
        value = listing.attributes.get(name)
        if value is not None and value.value is not None and value.review_status != "conflicted":
            text_values.append(str(value.value))
            normalized = re.sub(r"[^a-z0-9]+", "_", str(value.value).casefold()).strip("_")
            if normalized:
                attribute_tokens.add(f"attribute_{name}_{normalized}")
    tokens = re.findall(r"[a-z0-9]+", " ".join(text_values).casefold())
    ignored = set(stop_words)

    def usable(token: str) -> bool:
        return preserve_numeric or not token.isdigit()

    unigrams = [
        token for token in tokens if token not in ignored and usable(token) and len(token) >= 2
    ]
    bigrams = [
        f"{tokens[index]}_{tokens[index + 1]}"
        for index in range(len(tokens) - 1)
        if usable(tokens[index])
        and usable(tokens[index + 1])
        and (tokens[index] not in ignored or tokens[index + 1] not in ignored)
    ]
    return {*unigrams, *bigrams, *attribute_tokens}


def _shares_allowed_identifier(
    benchmark: ListingEvidence,
    competitor: ListingEvidence,
    policy: MatchingPolicyV2,
) -> bool:
    allowed = set(policy.exact_item_identifier_schemes)
    benchmark_values = {
        (row.scheme, row.value)
        for row in benchmark.identifiers
        if row.scheme in allowed and row.verification_status != "disputed"
    }
    return any(
        (row.scheme, row.value) in benchmark_values
        for row in competitor.identifiers
        if row.scheme in allowed and row.verification_status != "disputed"
    )


def _distance_miles(
    latitude_1: float,
    longitude_1: float,
    latitude_2: float,
    longitude_2: float,
) -> float:
    first_latitude = math.radians(latitude_1)
    second_latitude = math.radians(latitude_2)
    latitude_delta = second_latitude - first_latitude
    longitude_delta = math.radians(longitude_2 - longitude_1)
    haversine = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(first_latitude) * math.cos(second_latitude) * math.sin(longitude_delta / 2) ** 2
    )
    return 3958.7613 * 2 * math.asin(math.sqrt(haversine))


def shadow_result_checksum(result: MatchingShadowResultV2) -> str:
    document = {
        **result.summary(),
        "edges": [edge.to_contract() for edge in result.edges],
        "blocked_review_edges": [edge.to_contract() for edge in result.blocked_review_edges],
    }
    return hashlib.sha256(_canonical(document).encode()).hexdigest()
