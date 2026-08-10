"""Generic dimension, unit-price, geography, and proximity comparisons."""

from __future__ import annotations

import hashlib
import math
import statistics
from collections.abc import Iterable
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any

from rci_analytics.models import (
    ClassifiedOffer,
    ComparisonSummary,
    JsonObject,
    MatchRecord,
    ProductMatchRule,
)
from rci_analytics.product_pack import ProductPack


@dataclass(frozen=True, slots=True)
class MatchRelationshipResolution:
    """One-to-one relationship projection over Product Pack-admitted matches."""

    matches: tuple[MatchRecord, ...]
    relationships: tuple[JsonObject, ...]
    ambiguous_groups: tuple[JsonObject, ...]


def _maximum_matching(
    edges: set[tuple[str, str]],
    *,
    omitted: tuple[str, str] | None = None,
) -> dict[str, str]:
    adjacency: dict[str, list[str]] = {}
    for benchmark_product_id, competitor_product_id in sorted(edges):
        if (benchmark_product_id, competitor_product_id) == omitted:
            continue
        adjacency.setdefault(benchmark_product_id, []).append(competitor_product_id)
    competitor_to_benchmark: dict[str, str] = {}

    def admit(benchmark_product_id: str, seen: set[str]) -> bool:
        for competitor_product_id in adjacency.get(benchmark_product_id, []):
            if competitor_product_id in seen:
                continue
            seen.add(competitor_product_id)
            previous = competitor_to_benchmark.get(competitor_product_id)
            if previous is None or admit(previous, seen):
                competitor_to_benchmark[competitor_product_id] = benchmark_product_id
                return True
        return False

    for benchmark_product_id in sorted(adjacency):
        admit(benchmark_product_id, set())
    return {
        benchmark_product_id: competitor_product_id
        for competitor_product_id, benchmark_product_id in competitor_to_benchmark.items()
    }


def _edge_components(edges: set[tuple[str, str]]) -> list[set[tuple[str, str]]]:
    remaining = set(edges)
    components: list[set[tuple[str, str]]] = []
    while remaining:
        seed = min(remaining)
        component: set[tuple[str, str]] = set()
        benchmark_frontier = {seed[0]}
        competitor_frontier = {seed[1]}
        while benchmark_frontier or competitor_frontier:
            related = {
                edge
                for edge in remaining
                if edge[0] in benchmark_frontier or edge[1] in competitor_frontier
            }
            if not related:
                break
            component.update(related)
            remaining.difference_update(related)
            benchmark_frontier = {edge[0] for edge in related}
            competitor_frontier = {edge[1] for edge in related}
        components.append(component)
    return components


def resolve_one_to_one_relationships(
    offers: Iterable[ClassifiedOffer],
    matches: Iterable[MatchRecord],
    *,
    benchmark_retailer: str,
    profile_priority: Iterable[str],
) -> MatchRelationshipResolution:
    """Resolve automatic exact-geography candidates without arbitrary business tie-breaks.

    Confirmed relationship rows always win. Automatic edges must be mutual best on the
    Product Pack profile priority and part of a unique maximum one-to-one assignment.
    Evidence volume and stable IDs never decide product identity.
    """

    match_rows = list(matches)
    priorities = {str(profile_id): index for index, profile_id in enumerate(profile_priority)}
    offer_index = {item.offer.offer_id: item.offer for item in offers}
    pair_rows: dict[tuple[str, str, str], list[MatchRecord]] = {}
    passthrough: list[MatchRecord] = []
    for match in match_rows:
        if match.profile_id not in priorities:
            passthrough.append(match)
            continue
        benchmark = offer_index.get(match.benchmark_offer_id)
        competitor = offer_index.get(match.competitor_offer_id)
        if (
            benchmark is None
            or competitor is None
            or benchmark.retailer_id != benchmark_retailer
            or competitor.retailer_id != match.competitor_id
        ):
            continue
        key = (
            match.competitor_id,
            benchmark.retailer_product_id,
            competitor.retailer_product_id,
        )
        pair_rows.setdefault(key, []).append(match)

    selected: dict[tuple[str, str, str], str] = {}
    ambiguous_groups: list[JsonObject] = []
    for competitor_id in sorted({key[0] for key in pair_rows}):
        competitor_pairs = {key for key in pair_rows if key[0] == competitor_id}
        confirmed = {
            key
            for key in competitor_pairs
            if any(
                str(row.attributes.get("_match_origin")) == "user_confirmed"
                for row in pair_rows[key]
            )
        }
        confirmed_benchmark = [key[1] for key in confirmed]
        confirmed_competitor = [key[2] for key in confirmed]
        if len(confirmed_benchmark) != len(set(confirmed_benchmark)) or len(
            confirmed_competitor
        ) != len(set(confirmed_competitor)):
            raise ValueError("confirmed product relationships must be globally one-to-one")
        selected.update({key: "confirmed" for key in confirmed})
        locked_benchmark = set(confirmed_benchmark)
        locked_competitor = set(confirmed_competitor)
        automatic = {
            key
            for key in competitor_pairs - confirmed
            if key[1] not in locked_benchmark and key[2] not in locked_competitor
        }
        if not automatic:
            continue
        edge_rank = {
            (key[1], key[2]): min(priorities[row.profile_id] for row in pair_rows[key])
            for key in automatic
        }
        best_benchmark = {
            benchmark_product_id: min(
                rank
                for (candidate_benchmark, _candidate_competitor), rank in edge_rank.items()
                if candidate_benchmark == benchmark_product_id
            )
            for benchmark_product_id, _competitor_product_id in edge_rank
        }
        best_competitor = {
            competitor_product_id: min(
                rank
                for (_candidate_benchmark, candidate_competitor), rank in edge_rank.items()
                if candidate_competitor == competitor_product_id
            )
            for _benchmark_product_id, competitor_product_id in edge_rank
        }
        mutual_best = {
            edge
            for edge, rank in edge_rank.items()
            if rank == best_benchmark[edge[0]] and rank == best_competitor[edge[1]]
        }
        for component in _edge_components(mutual_best):
            assignment = _maximum_matching(component)
            unique = all(
                len(_maximum_matching(component, omitted=edge)) < len(assignment)
                for edge in assignment.items()
            )
            if unique:
                for benchmark_product_id, competitor_product_id in assignment.items():
                    selected[(competitor_id, benchmark_product_id, competitor_product_id)] = (
                        "suggested"
                    )
                continue
            candidate_rows = [
                {
                    "benchmark_product_id": benchmark_product_id,
                    "competitor_product_id": competitor_product_id,
                    "eligible_profile_ids": sorted(
                        {
                            row.profile_id
                            for row in pair_rows[
                                (competitor_id, benchmark_product_id, competitor_product_id)
                            ]
                        },
                        key=lambda value: (priorities[value], value),
                    ),
                }
                for benchmark_product_id, competitor_product_id in sorted(component)
            ]
            seed = "|".join(
                (
                    competitor_id,
                    *(
                        f"{row['benchmark_product_id']}:{row['competitor_product_id']}"
                        for row in candidate_rows
                    ),
                )
            )
            ambiguous_groups.append(
                {
                    "candidate_group_id": (
                        f"candidate-{hashlib.sha256(seed.encode()).hexdigest()[:20]}"
                    ),
                    "competitor_id": competitor_id,
                    "candidates": candidate_rows,
                }
            )

    relationships: list[JsonObject] = []
    resolved: list[MatchRecord] = list(passthrough)
    for key, status in sorted(selected.items()):
        competitor_id, benchmark_product_id, competitor_product_id = key
        seed = "|".join(key)
        relationship_id = f"relationship-{hashlib.sha256(seed.encode()).hexdigest()[:20]}"
        rows = pair_rows[key]
        eligible_profiles = sorted(
            {row.profile_id for row in rows},
            key=lambda value: (priorities[value], value),
        )
        relationships.append(
            {
                "relationship_id": relationship_id,
                "competitor_id": competitor_id,
                "benchmark_product_id": benchmark_product_id,
                "competitor_product_id": competitor_product_id,
                "status": status,
                "eligible_profile_ids": eligible_profiles,
                "qa_status": "ready",
                "suppression_reasons": [],
            }
        )
        resolved.extend(
            replace(
                row,
                attributes={
                    **row.attributes,
                    "_relationship_id": relationship_id,
                    "_relationship_status": status,
                },
            )
            for row in rows
        )
    resolved.sort(
        key=lambda row: (
            row.competitor_id,
            priorities.get(row.profile_id, len(priorities)),
            row.geography_key,
            row.benchmark_offer_id,
            row.competitor_offer_id,
        )
    )
    return MatchRelationshipResolution(
        matches=tuple(resolved),
        relationships=tuple(relationships),
        ambiguous_groups=tuple(ambiguous_groups),
    )


def haversine_miles(
    latitude_a: float, longitude_a: float, latitude_b: float, longitude_b: float
) -> float:
    radius_miles = 3958.7613
    lat_a, lon_a, lat_b, lon_b = map(
        math.radians, (latitude_a, longitude_a, latitude_b, longitude_b)
    )
    delta_lat = lat_b - lat_a
    delta_lon = lon_b - lon_a
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * radius_miles * math.asin(math.sqrt(value))


def geographic_overlap(
    offers: Iterable[ClassifiedOffer], benchmark_id: str, competitor_id: str
) -> set[str]:
    benchmark = {
        item.offer.zipcode
        for item in offers
        if item.in_scope
        and item.offer.retailer_id == benchmark_id
        and item.offer.zipcode is not None
    }
    competitor = {
        item.offer.zipcode
        for item in offers
        if item.in_scope
        and item.offer.retailer_id == competitor_id
        and item.offer.zipcode is not None
    }
    return benchmark & competitor


class ComparisonEngine:
    def __init__(self, pack: ProductPack) -> None:
        self.pack = pack
        self._tolerance = Decimal(str(pack.document["qa_rules"].get("parity_tolerance_dollars", 0)))
        self._unknown_values = {
            str(definition["name"]): tuple(definition.get("unknown_values", []))
            for definition in pack.attributes
        }

    def compare(
        self,
        offers: list[ClassifiedOffer],
        *,
        benchmark_id: str,
        competitor_id: str,
        profile_id: str,
    ) -> list[MatchRecord]:
        profile = self.pack.profile(profile_id)
        if profile["geography"] == "radius":
            return self._radius_matches(offers, benchmark_id, competitor_id, profile)
        if profile["geography"] != "exact_zip":
            raise ValueError(
                f"geography {profile['geography']!r} is not implemented for this engine"
            )
        return self._exact_zip_matches(offers, benchmark_id, competitor_id, profile)

    def compare_governed(
        self,
        offers: list[ClassifiedOffer],
        *,
        benchmark_id: str,
        competitor_id: str,
        profile_id: str,
        rules: Iterable[ProductMatchRule] = (),
    ) -> list[MatchRecord]:
        """Apply an immutable one-to-one decision snapshot to generic matches."""

        applicable = [
            rule
            for rule in rules
            if rule.competitor_id == competitor_id
            and profile_id in (rule.eligible_profile_ids or (rule.profile_id,))
        ]
        confirmed = [rule for rule in applicable if rule.decision == "confirmed"]
        rejected = {
            (rule.benchmark_product_id, rule.competitor_product_id)
            for rule in applicable
            if rule.decision == "rejected"
        }
        benchmark_products = [rule.benchmark_product_id for rule in confirmed]
        competitor_products = [rule.competitor_product_id for rule in confirmed]
        if len(benchmark_products) != len(set(benchmark_products)) or len(
            competitor_products
        ) != len(set(competitor_products)):
            raise ValueError("confirmed product-match rules must be one-to-one")

        offer_index = {item.offer.offer_id: item.offer for item in offers}
        locked_benchmark = set(benchmark_products)
        locked_competitor = set(competitor_products)
        automatic = []
        for match in self.compare(
            offers,
            benchmark_id=benchmark_id,
            competitor_id=competitor_id,
            profile_id=profile_id,
        ):
            benchmark = offer_index.get(match.benchmark_offer_id)
            competitor = offer_index.get(match.competitor_offer_id)
            if benchmark is None or competitor is None:
                continue
            pair = (benchmark.retailer_product_id, competitor.retailer_product_id)
            if pair in rejected or pair[0] in locked_benchmark or pair[1] in locked_competitor:
                continue
            automatic.append(match)

        profile = self.pack.profile(profile_id)
        if confirmed and profile["geography"] != "exact_zip":
            raise ValueError("confirmed product matches currently require exact-ZIP geography")
        governed = [
            match
            for rule in confirmed
            for match in self._confirmed_exact_zip_matches(
                offers,
                benchmark_id=benchmark_id,
                competitor_id=competitor_id,
                profile=profile,
                benchmark_product_id=rule.benchmark_product_id,
                competitor_product_id=rule.competitor_product_id,
            )
        ]
        return sorted(
            [*governed, *automatic],
            key=lambda match: (
                match.geography_key,
                match.benchmark_offer_id,
                match.competitor_offer_id,
            ),
        )

    def _confirmed_exact_zip_matches(
        self,
        offers: list[ClassifiedOffer],
        *,
        benchmark_id: str,
        competitor_id: str,
        profile: JsonObject,
        benchmark_product_id: str,
        competitor_product_id: str,
    ) -> list[MatchRecord]:
        metric = self._comparison_metric(profile)
        benchmark = self._selected_product_by_zip(
            offers,
            retailer_id=benchmark_id,
            product_id=benchmark_product_id,
            profile=profile,
            metric=metric,
            role="benchmark",
        )
        competitor = self._selected_product_by_zip(
            offers,
            retailer_id=competitor_id,
            product_id=competitor_product_id,
            profile=profile,
            metric=metric,
            role="competitor",
        )
        dimensions = tuple(str(value) for value in profile["dimensions"])
        return [
            self._match(
                profile=profile,
                competitor_id=competitor_id,
                geography_key=zipcode,
                benchmark=benchmark[zipcode][0],
                competitor=competitor[zipcode][0],
                dimensions=dimensions,
                metric=metric,
                benchmark_value=benchmark[zipcode][1],
                competitor_value=competitor[zipcode][1],
                matched_attributes={
                    **{name: benchmark[zipcode][0].attributes.get(name) for name in dimensions},
                    "_match_origin": "user_confirmed",
                },
            )
            for zipcode in sorted(benchmark.keys() & competitor.keys())
        ]

    def _selected_product_by_zip(
        self,
        offers: list[ClassifiedOffer],
        *,
        retailer_id: str,
        product_id: str,
        profile: JsonObject,
        metric: str,
        role: str,
    ) -> dict[str, tuple[ClassifiedOffer, Decimal]]:
        selected: dict[str, tuple[ClassifiedOffer, Decimal]] = {}
        for item in offers:
            value = self._metric_value(item, metric)
            if (
                not item.in_scope
                or item.offer.retailer_id != retailer_id
                or item.offer.retailer_product_id != product_id
                or item.offer.zipcode is None
                or not self._available_for_matching(item, profile)
                or not self._satisfies_constraints(item, profile, role)
                or value is None
            ):
                continue
            previous = selected.get(item.offer.zipcode)
            if previous is None or (value, item.offer.offer_id) < (
                previous[1],
                previous[0].offer.offer_id,
            ):
                selected[item.offer.zipcode] = (item, value)
        return selected

    def comparison_metric(self, profile_id: str) -> str:
        """Resolve a profile's configured or derived comparison metric."""

        return self._comparison_metric(self.pack.profile(profile_id))

    def _comparison_metric(self, profile: JsonObject) -> str:
        configured = profile.get("comparison_metric")
        if configured:
            return str(configured)
        dimensions = {str(value) for value in profile["dimensions"]}
        secondary = set(self.pack.document["normalization"].get("secondary_metrics", []))
        for rule in self.pack.document["normalization"].get("conversion_rules", []):
            if str(rule["from"]) not in dimensions and str(rule["to"]) in secondary:
                return str(rule["to"])
        return "package_price"

    def _dimension_key(
        self,
        item: ClassifiedOffer,
        dimensions: tuple[str, ...],
        unknown_policy: str,
        brand_policy: str,
    ) -> tuple[Any, ...] | None:
        values = tuple(item.attributes.get(name) for name in dimensions)
        if any(value is None for value in values) and unknown_policy in {"reject", "review"}:
            return None
        brand = self._brand_component(item, brand_policy)
        if brand is None:
            return None
        return (*values, *brand)

    def _brand_component(self, item: ClassifiedOffer, brand_policy: str) -> tuple[str, ...] | None:
        if brand_policy == "ignore_brand":
            return ()
        brand = item.attributes.get("brand") or item.offer.brand
        if not brand:
            return None
        normalized = self._normalized_brand(str(brand))
        if brand_policy == "same_brand":
            return (normalized,)
        if brand_policy == "private_label_equivalent":
            configured = self.pack.document.get("brand_rules", {}).get("private_labels", {})
            private_labels = configured.get(item.offer.retailer_id, [])
            if normalized not in {self._normalized_brand(str(value)) for value in private_labels}:
                return None
            return ("private_label",)
        raise ValueError(f"brand policy {brand_policy!r} is not implemented")

    def _normalized_brand(self, value: str) -> str:
        normalized = " ".join(
            "".join(
                character if character.isalnum() else " " for character in value.casefold()
            ).split()
        )
        aliases = self.pack.document.get("brand_rules", {}).get("aliases", {})
        for canonical, values in aliases.items():
            candidates = [canonical, *values]
            if normalized in {
                " ".join(
                    "".join(
                        character if character.isalnum() else " "
                        for character in str(candidate).casefold()
                    ).split()
                )
                for candidate in candidates
            }:
                return str(canonical).casefold()
        return normalized

    @staticmethod
    def _metric_value(item: ClassifiedOffer, metric: str) -> Decimal | None:
        value = item.offer.price if metric == "package_price" else item.metrics.get(metric)
        return value if value is not None and value > 0 else None

    def _available_for_matching(self, item: ClassifiedOffer, profile: JsonObject) -> bool:
        policy = str(profile.get("availability_policy", "search_presence"))
        if policy == "retailer_specific":
            retailer = self.pack.document.get("retailer_overrides", {}).get(
                item.offer.retailer_id, {}
            )
            policy = str(retailer.get("matching_availability_policy", "search_presence"))
        if policy == "search_presence":
            return True
        if policy == "in_stock_only":
            return item.offer.in_stock is True
        raise ValueError(f"matching availability policy {policy!r} is not implemented")

    def _selected(
        self,
        offers: list[ClassifiedOffer],
        retailer_id: str,
        profile: JsonObject,
        metric: str,
        role: str,
    ) -> dict[tuple[str, tuple[Any, ...]], tuple[ClassifiedOffer, Decimal]]:
        dimensions = tuple(str(value) for value in profile["dimensions"])
        unknown_policy = str(profile.get("unknown_policy", "reject"))
        brand_policy = str(profile.get("brand_policy", "ignore_brand"))
        selected: dict[tuple[str, tuple[Any, ...]], tuple[ClassifiedOffer, Decimal]] = {}
        for item in offers:
            if (
                not item.in_scope
                or item.offer.retailer_id != retailer_id
                or item.offer.zipcode is None
                or not self._available_for_matching(item, profile)
                or not self._satisfies_constraints(item, profile, role)
            ):
                continue
            dimension_key = self._dimension_key(item, dimensions, unknown_policy, brand_policy)
            value = self._metric_value(item, metric)
            if dimension_key is None or value is None:
                continue
            key = (item.offer.zipcode, dimension_key)
            previous = selected.get(key)
            if previous is None or value < previous[1]:
                selected[key] = (item, value)
        return selected

    @staticmethod
    def _satisfies_constraints(
        item: ClassifiedOffer, profile: JsonObject, role: str | None = None
    ) -> bool:
        constraint_groups = [profile.get("attribute_constraints", {})]
        if role is not None:
            constraint_groups.append(profile.get(f"{role}_attribute_constraints", {}))
        return all(
            item.attributes.get(name) in allowed
            for constraints in constraint_groups
            for name, allowed in constraints.items()
        )

    def _exact_zip_matches(
        self,
        offers: list[ClassifiedOffer],
        benchmark_id: str,
        competitor_id: str,
        profile: JsonObject,
    ) -> list[MatchRecord]:
        if profile.get("unknown_policy") == "wildcard_if_one_unknown":
            return self._wildcard_exact_zip_matches(offers, benchmark_id, competitor_id, profile)
        metric = self._comparison_metric(profile)
        benchmark = self._selected(offers, benchmark_id, profile, metric, "benchmark")
        competitor = self._selected(offers, competitor_id, profile, metric, "competitor")
        dimensions = tuple(str(value) for value in profile["dimensions"])
        matches: list[MatchRecord] = []
        for key in sorted(benchmark.keys() & competitor.keys(), key=str):
            benchmark_offer, benchmark_value = benchmark[key]
            competitor_offer, competitor_value = competitor[key]
            matches.append(
                self._match(
                    profile=profile,
                    competitor_id=competitor_id,
                    geography_key=key[0],
                    benchmark=benchmark_offer,
                    competitor=competitor_offer,
                    dimensions=dimensions,
                    metric=metric,
                    benchmark_value=benchmark_value,
                    competitor_value=competitor_value,
                )
            )
        return matches

    def _wildcard_exact_zip_matches(
        self,
        offers: list[ClassifiedOffer],
        benchmark_id: str,
        competitor_id: str,
        profile: JsonObject,
    ) -> list[MatchRecord]:
        metric = self._comparison_metric(profile)
        dimensions = tuple(str(value) for value in profile["dimensions"])
        wildcard_dimensions = frozenset(
            str(value) for value in profile.get("wildcard_dimensions", dimensions)
        )
        brand_policy = str(profile.get("brand_policy", "ignore_brand"))
        benchmark = self._eligible_by_zip(offers, benchmark_id, profile, metric, "benchmark")
        competitor = self._eligible_by_zip(offers, competitor_id, profile, metric, "competitor")
        selected: dict[
            tuple[str, tuple[Any, ...]],
            tuple[ClassifiedOffer, Decimal, ClassifiedOffer, Decimal],
        ] = {}
        for zipcode in benchmark.keys() & competitor.keys():
            for benchmark_offer, benchmark_value in benchmark[zipcode]:
                for competitor_offer, competitor_value in competitor[zipcode]:
                    resolved = self._compatible_dimension_key(
                        benchmark_offer,
                        competitor_offer,
                        dimensions,
                        wildcard_dimensions,
                        brand_policy,
                    )
                    if resolved is None:
                        continue
                    key = (zipcode, resolved)
                    candidate = (
                        benchmark_offer,
                        benchmark_value,
                        competitor_offer,
                        competitor_value,
                    )
                    previous = selected.get(key)
                    if previous is None or (
                        benchmark_value,
                        competitor_value,
                        benchmark_offer.offer.offer_id,
                        competitor_offer.offer.offer_id,
                    ) < (
                        previous[1],
                        previous[3],
                        previous[0].offer.offer_id,
                        previous[2].offer.offer_id,
                    ):
                        selected[key] = candidate
        return [
            self._match(
                profile=profile,
                competitor_id=competitor_id,
                geography_key=zipcode,
                benchmark=benchmark_offer,
                competitor=competitor_offer,
                dimensions=dimensions,
                metric=metric,
                benchmark_value=benchmark_value,
                competitor_value=competitor_value,
                matched_attributes={name: resolved[index] for index, name in enumerate(dimensions)},
            )
            for (zipcode, resolved), (
                benchmark_offer,
                benchmark_value,
                competitor_offer,
                competitor_value,
            ) in sorted(selected.items(), key=lambda item: str(item[0]))
        ]

    def _eligible_by_zip(
        self,
        offers: list[ClassifiedOffer],
        retailer_id: str,
        profile: JsonObject,
        metric: str,
        role: str,
    ) -> dict[str, list[tuple[ClassifiedOffer, Decimal]]]:
        selected: dict[str, list[tuple[ClassifiedOffer, Decimal]]] = {}
        for item in offers:
            value = self._metric_value(item, metric)
            if (
                item.in_scope
                and item.offer.retailer_id == retailer_id
                and item.offer.zipcode is not None
                and self._available_for_matching(item, profile)
                and self._satisfies_constraints(item, profile, role)
                and value is not None
            ):
                selected.setdefault(item.offer.zipcode, []).append((item, value))
        return selected

    def _compatible_dimension_key(
        self,
        benchmark: ClassifiedOffer,
        competitor: ClassifiedOffer,
        dimensions: tuple[str, ...],
        wildcard_dimensions: frozenset[str],
        brand_policy: str,
    ) -> tuple[Any, ...] | None:
        resolved: list[Any] = []
        for name in dimensions:
            benchmark_value = benchmark.attributes.get(name)
            competitor_value = competitor.attributes.get(name)
            benchmark_unknown = self._is_unknown(name, benchmark_value)
            competitor_unknown = self._is_unknown(name, competitor_value)
            if name not in wildcard_dimensions:
                if benchmark_unknown or competitor_unknown or benchmark_value != competitor_value:
                    return None
                resolved.append(benchmark_value)
            elif not benchmark_unknown and not competitor_unknown:
                if benchmark_value != competitor_value:
                    return None
                resolved.append(benchmark_value)
            elif benchmark_unknown and competitor_unknown:
                return None
            else:
                resolved.append(benchmark_value if not benchmark_unknown else competitor_value)
        benchmark_brand = self._brand_component(benchmark, brand_policy)
        competitor_brand = self._brand_component(competitor, brand_policy)
        if benchmark_brand is None or competitor_brand is None:
            return None
        if benchmark_brand != competitor_brand:
            return None
        return (*resolved, *benchmark_brand)

    def _is_unknown(self, dimension: str, value: Any) -> bool:
        return value is None or any(
            value == configured for configured in self._unknown_values.get(dimension, ())
        )

    def _radius_matches(
        self,
        offers: list[ClassifiedOffer],
        benchmark_id: str,
        competitor_id: str,
        profile: JsonObject,
    ) -> list[MatchRecord]:
        radius = float(profile["radius_miles"])
        metric = self._comparison_metric(profile)
        dimensions = tuple(str(value) for value in profile["dimensions"])
        unknown_policy = str(profile.get("unknown_policy", "reject"))
        benchmark = self._selected_stores(
            offers, benchmark_id, dimensions, unknown_policy, metric, profile, "benchmark"
        )
        competitors = self._selected_stores(
            offers, competitor_id, dimensions, unknown_policy, metric, profile, "competitor"
        )
        by_dimensions: dict[tuple[Any, ...], list[tuple[ClassifiedOffer, Decimal]]] = {}
        for (_, dimension_key), value in benchmark.items():
            by_dimensions.setdefault(dimension_key, []).append(value)
        cell_degrees = max(radius / 69.0, 0.01)
        spatial_by_dimensions: dict[
            tuple[Any, ...],
            dict[tuple[int, int], list[tuple[ClassifiedOffer, Decimal]]],
        ] = {}
        for dimension_key, values in by_dimensions.items():
            cells: dict[tuple[int, int], list[tuple[ClassifiedOffer, Decimal]]] = {}
            for benchmark_offer, benchmark_value in values:
                latitude = benchmark_offer.offer.latitude
                longitude = benchmark_offer.offer.longitude
                if latitude is None or longitude is None:
                    continue
                cell = (
                    math.floor(latitude / cell_degrees),
                    math.floor(longitude / cell_degrees),
                )
                cells.setdefault(cell, []).append((benchmark_offer, benchmark_value))
            spatial_by_dimensions[dimension_key] = cells
        matches: list[MatchRecord] = []
        for (store_key, dimension_key), (competitor_offer, competitor_value) in sorted(
            competitors.items(), key=lambda item: str(item[0])
        ):
            latitude = competitor_offer.offer.latitude
            longitude = competitor_offer.offer.longitude
            if latitude is None or longitude is None:
                continue
            latitude_delta = radius / 69.0
            longitude_scale = abs(math.cos(math.radians(latitude)))
            longitude_delta = 180.0 if longitude_scale < 0.05 else radius / (69.0 * longitude_scale)
            latitude_cells = range(
                math.floor((latitude - latitude_delta) / cell_degrees),
                math.floor((latitude + latitude_delta) / cell_degrees) + 1,
            )
            longitude_cells = range(
                math.floor((longitude - longitude_delta) / cell_degrees),
                math.floor((longitude + longitude_delta) / cell_degrees) + 1,
            )
            nearby = spatial_by_dimensions.get(dimension_key, {})
            if (
                longitude_scale < 0.05
                or longitude - longitude_delta < -180
                or longitude + longitude_delta > 180
            ):
                potential_candidates = by_dimensions.get(dimension_key, [])
            else:
                potential_candidates = [
                    candidate
                    for latitude_cell in latitude_cells
                    for longitude_cell in longitude_cells
                    for candidate in nearby.get((latitude_cell, longitude_cell), ())
                ]
            candidates: list[tuple[float, ClassifiedOffer, Decimal]] = []
            for benchmark_offer, benchmark_value in potential_candidates:
                benchmark_lat = benchmark_offer.offer.latitude
                benchmark_lon = benchmark_offer.offer.longitude
                if benchmark_lat is None or benchmark_lon is None:
                    continue
                distance = haversine_miles(latitude, longitude, benchmark_lat, benchmark_lon)
                if distance <= radius:
                    candidates.append((distance, benchmark_offer, benchmark_value))
            if not candidates:
                continue
            distance, benchmark_offer, benchmark_value = min(
                candidates, key=lambda value: (value[0], value[2], value[1].offer.offer_id)
            )
            matches.append(
                self._match(
                    profile=profile,
                    competitor_id=competitor_id,
                    geography_key=self._proximity_key(store_key, benchmark_offer),
                    benchmark=benchmark_offer,
                    competitor=competitor_offer,
                    dimensions=dimensions,
                    metric=metric,
                    benchmark_value=benchmark_value,
                    competitor_value=competitor_value,
                    distance_miles=distance,
                )
            )
        return matches

    @staticmethod
    def _proximity_key(store_key: str, benchmark: ClassifiedOffer) -> str:
        benchmark_key = benchmark.offer.store_number or benchmark.offer.offer_id
        return f"{store_key}->{benchmark_key}"

    def _selected_stores(
        self,
        offers: list[ClassifiedOffer],
        retailer_id: str,
        dimensions: tuple[str, ...],
        unknown_policy: str,
        metric: str,
        profile: JsonObject,
        role: str,
    ) -> dict[tuple[str, tuple[Any, ...]], tuple[ClassifiedOffer, Decimal]]:
        selected: dict[tuple[str, tuple[Any, ...]], tuple[ClassifiedOffer, Decimal]] = {}
        brand_policy = str(profile.get("brand_policy", "ignore_brand"))
        for item in offers:
            if (
                not item.in_scope
                or item.offer.retailer_id != retailer_id
                or not self._available_for_matching(item, profile)
                or not self._satisfies_constraints(item, profile, role)
            ):
                continue
            dimension_key = self._dimension_key(item, dimensions, unknown_policy, brand_policy)
            value = self._metric_value(item, metric)
            if dimension_key is None or value is None:
                continue
            store_key = item.offer.store_number or item.offer.zipcode
            if store_key is None:
                continue
            key = (store_key, dimension_key)
            previous = selected.get(key)
            if previous is None or value < previous[1]:
                selected[key] = (item, value)
        return selected

    def _match(
        self,
        *,
        profile: JsonObject,
        competitor_id: str,
        geography_key: str,
        benchmark: ClassifiedOffer,
        competitor: ClassifiedOffer,
        dimensions: tuple[str, ...],
        metric: str,
        benchmark_value: Decimal,
        competitor_value: Decimal,
        distance_miles: float | None = None,
        matched_attributes: JsonObject | None = None,
    ) -> MatchRecord:
        gap = competitor_value - benchmark_value
        benchmark_interval = self._interval(benchmark, profile)
        competitor_interval = self._interval(competitor, profile)
        intervals_overlap = (
            benchmark_interval is not None
            and competitor_interval is not None
            and max(benchmark_interval[0], competitor_interval[0])
            <= min(benchmark_interval[1], competitor_interval[1])
        )
        if intervals_overlap or abs(gap) <= self._tolerance:
            winner = "parity"
        elif gap > 0:
            winner = "benchmark_lower"
        else:
            winner = "competitor_lower"
        return MatchRecord(
            profile_id=str(profile["id"]),
            competitor_id=competitor_id,
            geography_key=geography_key,
            benchmark_offer_id=benchmark.offer.offer_id,
            competitor_offer_id=competitor.offer.offer_id,
            attributes=matched_attributes
            or {name: benchmark.attributes.get(name) for name in dimensions},
            comparison_metric=metric,
            benchmark_value=benchmark_value,
            competitor_value=competitor_value,
            gap=gap,
            winner=winner,
            distance_miles=distance_miles,
            benchmark_interval_low=(
                benchmark_interval[0] if benchmark_interval is not None else None
            ),
            benchmark_interval_high=(
                benchmark_interval[1] if benchmark_interval is not None else None
            ),
            competitor_interval_low=(
                competitor_interval[0] if competitor_interval is not None else None
            ),
            competitor_interval_high=(
                competitor_interval[1] if competitor_interval is not None else None
            ),
        )

    def _interval(
        self, item: ClassifiedOffer, profile: JsonObject
    ) -> tuple[Decimal, Decimal] | None:
        configured = profile.get("comparison_interval")
        if not isinstance(configured, dict):
            return None
        low = self._metric_value(item, str(configured["low_metric"]))
        high = self._metric_value(item, str(configured["high_metric"]))
        if low is None or high is None:
            return None
        return min(low, high), max(low, high)

    @staticmethod
    def summarize(matches: list[MatchRecord]) -> ComparisonSummary:
        if not matches:
            raise ValueError("cannot summarize an empty match set")
        total = len(matches)
        benchmark_lower = sum(item.winner == "benchmark_lower" for item in matches)
        competitor_lower = sum(item.winner == "competitor_lower" for item in matches)
        parity = sum(item.winner == "parity" for item in matches)
        return ComparisonSummary(
            profile_id=matches[0].profile_id,
            competitor_id=matches[0].competitor_id,
            matches=total,
            unique_geographies=len({item.geography_key for item in matches}),
            benchmark_lower=benchmark_lower,
            competitor_lower=competitor_lower,
            parity=parity,
            benchmark_lower_rate=benchmark_lower / total,
            competitor_lower_rate=competitor_lower / total,
            parity_rate=parity / total,
            benchmark_median=float(statistics.median(item.benchmark_value for item in matches)),
            competitor_median=float(statistics.median(item.competitor_value for item in matches)),
            median_gap=float(statistics.median(item.gap for item in matches)),
            mean_gap=float(statistics.fmean(item.gap for item in matches)),
        )


class ComparisonInputReducer:
    """Retain only offers that can affect configured comparison outcomes.

    The reducer is category-neutral: selection keys, metrics, availability, constraints,
    brand policy, and geography all come from the Product Pack. It lets historical and
    live inputs be classified as a stream while preserving the existing comparison
    engine's lowest-positive selection semantics.
    """

    def __init__(
        self,
        pack: ProductPack,
        *,
        profile_ids: Iterable[str] | None = None,
    ) -> None:
        self._engine = ComparisonEngine(pack)
        requested = set(profile_ids or ())
        available = {str(profile["id"]) for profile in pack.matching_profiles}
        unknown = requested - available
        if unknown:
            raise ValueError(f"Product Pack has no comparison profiles {sorted(unknown)}")
        self._profiles = tuple(
            profile
            for profile in pack.matching_profiles
            if not requested or str(profile["id"]) in requested
        )
        self._selected: dict[
            tuple[str, str, str, tuple[Any, ...]],
            tuple[ClassifiedOffer, Decimal],
        ] = {}
        self.input_offers = 0

    def add(self, item: ClassifiedOffer) -> None:
        self.input_offers += 1
        if not item.in_scope:
            return
        for profile in self._profiles:
            satisfies_either_role = self._engine._satisfies_constraints(
                item, profile, "benchmark"
            ) or self._engine._satisfies_constraints(item, profile, "competitor")
            if not self._engine._available_for_matching(item, profile) or not satisfies_either_role:
                continue
            metric = self._engine._comparison_metric(profile)
            value = self._engine._metric_value(item, metric)
            if value is None:
                continue
            dimensions = tuple(str(name) for name in profile["dimensions"])
            brand_policy = str(profile.get("brand_policy", "ignore_brand"))
            dimension_key: tuple[Any, ...] | None
            if profile.get("unknown_policy") == "wildcard_if_one_unknown":
                brand = self._engine._brand_component(item, brand_policy)
                if brand is None:
                    continue
                dimension_key = (
                    *(item.attributes.get(name) for name in dimensions),
                    *brand,
                )
            else:
                dimension_key = self._engine._dimension_key(
                    item,
                    dimensions,
                    str(profile.get("unknown_policy", "reject")),
                    brand_policy,
                )
                if dimension_key is None:
                    continue
            geography = str(profile["geography"])
            if geography == "exact_zip":
                geography_key = item.offer.zipcode
            elif geography == "radius":
                geography_key = item.offer.store_number or item.offer.zipcode
            else:
                raise ValueError(
                    f"geography {geography!r} is not implemented for the comparison reducer"
                )
            if geography_key is None:
                continue
            key = (
                str(profile["id"]),
                item.offer.retailer_id,
                geography_key,
                dimension_key,
            )
            previous = self._selected.get(key)
            if previous is None or value < previous[1]:
                self._selected[key] = (item, value)

    def extend(self, items: Iterable[ClassifiedOffer]) -> None:
        for item in items:
            self.add(item)

    def offers(self) -> list[ClassifiedOffer]:
        retained: dict[str, ClassifiedOffer] = {}
        for item, _ in self._selected.values():
            retained[item.offer.offer_id] = item
        return list(retained.values())

    @property
    def retained_offers(self) -> int:
        return len({item.offer.offer_id for item, _ in self._selected.values()})
