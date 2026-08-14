"""Deterministic benchmark-store competitive price-leadership projection."""

from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from statistics import mean
from typing import Literal

from rci_analytics.models import JsonObject

LeadershipStatus = Literal["leader", "tied", "at_risk", "losing", "unscored"]


@dataclass(frozen=True, slots=True)
class ProductPriceObservation:
    retailer_id: str
    retailer_name: str
    product_id: str
    product_name: str
    image_url: str | None
    scope_key: str
    location_kind: Literal["store", "service_area"]
    store_number: str | None
    store_name: str | None
    zipcode: str | None
    city: str | None
    state: str | None
    country: str
    latitude: float | None
    longitude: float | None
    package_price: float
    comparison_value: float
    observed_at: str | None


@dataclass(frozen=True, slots=True)
class ProductLeadershipRelationship:
    relationship_id: str
    competitor_id: str
    competitor_name: str
    benchmark_product_id: str
    competitor_product_id: str
    profile_id: str
    profile_label: str
    comparison_metric: str
    comparison_unit: str
    scope_mode: str = "global"
    benchmark_location_scope_keys: tuple[str, ...] = ()

    def admits(self, benchmark_scope_key: str) -> bool:
        return self.scope_mode == "global" or (
            benchmark_scope_key in self.benchmark_location_scope_keys
        )


def _round(value: float | int | None, places: int = 4) -> float | None:
    return round(float(value), places) if value is not None else None


def _distance_miles(left: ProductPriceObservation, right: ProductPriceObservation) -> float | None:
    if (
        left.latitude is None
        or left.longitude is None
        or right.latitude is None
        or right.longitude is None
    ):
        return None
    earth_radius_miles = 3958.7613
    left_latitude = math.radians(left.latitude)
    right_latitude = math.radians(right.latitude)
    latitude_delta = math.radians(right.latitude - left.latitude)
    longitude_delta = math.radians(right.longitude - left.longitude)
    value = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(left_latitude) * math.cos(right_latitude) * math.sin(longitude_delta / 2) ** 2
    )
    return earth_radius_miles * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def _location(value: ProductPriceObservation) -> JsonObject:
    return {
        "retailer_id": value.retailer_id,
        "retailer_name": value.retailer_name,
        "product_id": value.product_id,
        "product_name": value.product_name,
        "image_url": value.image_url,
        "scope_key": value.scope_key,
        "location_kind": value.location_kind,
        "store_number": value.store_number,
        "store_name": value.store_name,
        "zipcode": value.zipcode,
        "city": value.city,
        "state": value.state,
        "country": value.country,
        "latitude": value.latitude,
        "longitude": value.longitude,
        "package_price": _round(value.package_price),
        "comparison_value": _round(value.comparison_value),
        "observed_at": value.observed_at,
    }


def _summary(rows: list[JsonObject]) -> JsonObject:
    outcomes = Counter(str(row["status"]) for row in rows)
    scored = [row for row in rows if row["status"] != "unscored"]
    losses = [row for row in rows if row["status"] == "losing"]
    gaps = [float(row["competitor_minus_benchmark"]) for row in scored]
    losing_gaps = [abs(float(row["competitor_minus_benchmark"])) for row in losses]
    return {
        "benchmark_observed_stores": len(rows),
        "scored_stores": len(scored),
        "coverage_rate": _round(len(scored) / len(rows)) if rows else None,
        "leader_stores": outcomes["leader"],
        "tied_stores": outcomes["tied"],
        "at_risk_stores": outcomes["at_risk"],
        "losing_stores": outcomes["losing"],
        "unscored_stores": outcomes["unscored"],
        "leader_rate": _round(outcomes["leader"] / len(scored)) if scored else None,
        "average_gap": _round(mean(gaps)) if gaps else None,
        "average_losing_gap": _round(mean(losing_gaps)) if losing_gaps else None,
        "maximum_losing_gap": _round(max(losing_gaps)) if losing_gaps else None,
    }


def _geography_summary(rows: list[JsonObject], *, level: str, label: str) -> JsonObject:
    summary = _summary(rows)
    return {
        "id": f"{level}:{label}",
        "level": level,
        "label": label,
        **summary,
    }


class CompetitiveProductLeadershipProjector:
    """Score one benchmark product at benchmark-store grain.

    Every benchmark store is assigned exactly one mutually exclusive status. A
    competitor service area (for example Amazon Same Day) is comparable only in
    the same ZIP; physical competitor stores must fall within the selected radius.
    """

    def build(
        self,
        *,
        analysis_id: str,
        generated_at: str,
        benchmark_retailer: JsonObject,
        benchmark_product: JsonObject,
        benchmark_observations: list[ProductPriceObservation],
        competitor_observations: list[ProductPriceObservation],
        relationships: list[ProductLeadershipRelationship],
        competitor_options: list[JsonObject],
        product_options: list[JsonObject],
        profile_options: list[JsonObject],
        selected_competitor: str,
        selected_profile: str,
        radius_miles: Literal[1, 3, 5],
        state: str | None = None,
        city: str | None = None,
        parity_tolerance: float = 0.01,
        at_risk_threshold: float = 0.10,
    ) -> JsonObject:
        if radius_miles not in {1, 3, 5}:
            raise ValueError("competitive radius must be 1, 3, or 5 miles")
        if parity_tolerance < 0 or at_risk_threshold <= parity_tolerance:
            raise ValueError("leadership thresholds are invalid")
        if not relationships:
            raise ValueError("no governed product relationship matches this context")
        metrics = {row.comparison_metric for row in relationships}
        units = {row.comparison_unit for row in relationships}
        if len(metrics) != 1 or len(units) != 1:
            raise ValueError("selected relationships do not share one comparison basis")

        visible_benchmark = [
            row
            for row in benchmark_observations
            if (state is None or row.state == state) and (city is None or row.city == city)
        ]
        candidates_by_product: dict[tuple[str, str], list[ProductPriceObservation]] = defaultdict(
            list
        )
        for observation in competitor_observations:
            candidates_by_product[(observation.retailer_id, observation.product_id)].append(
                observation
            )

        outcomes: list[JsonObject] = []
        for benchmark in visible_benchmark:
            candidates: list[
                tuple[
                    float,
                    float,
                    str,
                    ProductLeadershipRelationship,
                    ProductPriceObservation,
                ]
            ] = []
            for relationship in relationships:
                if not relationship.admits(benchmark.scope_key):
                    continue
                for competitor in candidates_by_product.get(
                    (relationship.competitor_id, relationship.competitor_product_id), []
                ):
                    distance = _distance_miles(benchmark, competitor)
                    if competitor.location_kind == "service_area":
                        if not benchmark.zipcode or competitor.zipcode != benchmark.zipcode:
                            continue
                        comparable_distance = 0.0
                    elif distance is None or distance > radius_miles:
                        continue
                    else:
                        comparable_distance = distance
                    candidates.append(
                        (
                            competitor.comparison_value,
                            comparable_distance,
                            competitor.scope_key,
                            relationship,
                            competitor,
                        )
                    )

            matched_competitor: ProductPriceObservation | None = None
            selected_relationship: ProductLeadershipRelationship | None = None
            distance_miles: float | None = None
            status: LeadershipStatus = "unscored"
            gap: float | None = None
            reduction: float | None = None
            if candidates:
                (
                    _value,
                    comparable_distance,
                    _scope,
                    selected_relationship,
                    matched_competitor,
                ) = min(
                    candidates,
                    key=lambda candidate: (candidate[0], candidate[1], candidate[2]),
                )
                distance_miles = (
                    None
                    if matched_competitor.location_kind == "service_area"
                    else comparable_distance
                )
                gap = matched_competitor.comparison_value - benchmark.comparison_value
                if abs(gap) <= parity_tolerance:
                    status = "tied"
                elif gap < -parity_tolerance:
                    status = "losing"
                    reduction = (
                        benchmark.comparison_value
                        - matched_competitor.comparison_value
                        + (parity_tolerance)
                    )
                elif gap <= at_risk_threshold:
                    status = "at_risk"
                else:
                    status = "leader"

            seed = "|".join(
                (
                    analysis_id,
                    benchmark.scope_key,
                    selected_relationship.relationship_id if selected_relationship else "unscored",
                )
            )
            outcomes.append(
                {
                    "id": f"leadership-{hashlib.sha256(seed.encode()).hexdigest()[:24]}",
                    "status": status,
                    "benchmark": _location(benchmark),
                    "competitor": (_location(matched_competitor) if matched_competitor else None),
                    "relationship_id": (
                        selected_relationship.relationship_id if selected_relationship else None
                    ),
                    "distance_miles": _round(distance_miles, 2),
                    "competitor_minus_benchmark": _round(gap),
                    "comparison_value_reduction_to_lead": _round(reduction),
                }
            )

        status_order = {"losing": 0, "at_risk": 1, "tied": 2, "leader": 3, "unscored": 4}
        outcomes.sort(
            key=lambda row: (
                status_order[str(row["status"])],
                -abs(float(row["competitor_minus_benchmark"] or 0)),
                str(row["benchmark"].get("state") or ""),
                str(row["benchmark"].get("store_number") or ""),
            )
        )
        state_groups: dict[str, list[JsonObject]] = defaultdict(list)
        city_groups: dict[tuple[str, str], list[JsonObject]] = defaultdict(list)
        competitor_groups: dict[str, list[JsonObject]] = defaultdict(list)
        for row in outcomes:
            benchmark_location = row["benchmark"]
            state_label = str(benchmark_location.get("state") or "Unknown state")
            city_label = str(benchmark_location.get("city") or "Unknown city")
            state_groups[state_label].append(row)
            city_groups[(state_label, city_label)].append(row)
            competitor_location = row.get("competitor")
            if isinstance(competitor_location, dict):
                competitor_groups[str(competitor_location["retailer_id"])].append(row)

        competitor_name_index = {str(row["id"]): str(row["name"]) for row in competitor_options}
        comparison_metric = next(iter(metrics))
        comparison_unit = next(iter(units))
        return {
            "schema_version": "1.0.0",
            "analysis_id": analysis_id,
            "generated_at": generated_at,
            "benchmark_retailer": benchmark_retailer,
            "benchmark_product": benchmark_product,
            "competitors": competitor_options,
            "filters": {
                "competitor_id": selected_competitor,
                "profile_id": selected_profile,
                "radius_miles": radius_miles,
                "state": state,
                "city": city,
            },
            "filter_options": {
                "products": product_options,
                "competitors": competitor_options,
                "profiles": profile_options,
                "radii_miles": [1, 3, 5],
                "states": [
                    {"value": label, "label": label, "count": len(rows)}
                    for label, rows in sorted(state_groups.items())
                ],
                "cities": [
                    {
                        "value": label,
                        "label": label,
                        "state": state_label,
                        "count": len(rows),
                    }
                    for (state_label, label), rows in sorted(city_groups.items())
                    if state is not None and state_label == state
                ],
            },
            "policy": {
                "price_authority": "Search",
                "identity_authority": "Product Pack classification with PDP enrichment",
                "location_authority": "Retailer location master",
                "observation_definition": (
                    "A product observed in Search with a price greater than zero is available "
                    "at that retailer location. The latest observation in the collection run "
                    "controls duplicate product-location rows."
                ),
                "comparison_definition": (
                    "Each observed benchmark store is compared with the lowest current value "
                    "among its governed matched competitor products within the selected radius. "
                    "Service-area retailers are compared within the same ZIP."
                ),
                "comparison_metric": comparison_metric,
                "comparison_unit": comparison_unit,
                "parity_tolerance": parity_tolerance,
                "at_risk_threshold": at_risk_threshold,
                "status_definition": {
                    "leader": "Benchmark lead is greater than the at-risk threshold.",
                    "tied": "Absolute price difference is within the parity tolerance.",
                    "at_risk": "Benchmark leads, but by no more than the at-risk threshold.",
                    "losing": "The lowest geographically comparable competitor is lower.",
                    "unscored": "No governed matched competitor observation is comparable.",
                },
            },
            "summary": _summary(outcomes),
            "state_summaries": [
                _geography_summary(rows, level="state", label=label)
                for label, rows in sorted(state_groups.items())
            ],
            "city_summaries": [
                _geography_summary(rows, level="city", label=f"{label}, {state_label}")
                for (state_label, label), rows in sorted(city_groups.items())
            ],
            "competitor_summaries": [
                {
                    "competitor_id": competitor_id,
                    "competitor": competitor_name_index.get(competitor_id, competitor_id),
                    **_summary(rows),
                }
                for competitor_id, rows in sorted(competitor_groups.items())
            ],
            "relationships": [
                {
                    "relationship_id": row.relationship_id,
                    "competitor_id": row.competitor_id,
                    "competitor_name": row.competitor_name,
                    "benchmark_product_id": row.benchmark_product_id,
                    "competitor_product_id": row.competitor_product_id,
                    "profile_id": row.profile_id,
                    "profile_label": row.profile_label,
                    "comparison_metric": row.comparison_metric,
                    "comparison_unit": row.comparison_unit,
                    "scope_mode": row.scope_mode,
                    "scoped_benchmark_locations": len(row.benchmark_location_scope_keys),
                }
                for row in relationships
            ],
            "outcomes": outcomes,
        }
