"""Independent trust checks for Product Leadership response documents."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from statistics import mean
from typing import Any

from rci_analytics.models import JsonObject

_STATUSES = ("leader", "tied", "at_risk", "losing", "unscored")
_ABS_TOLERANCE = 0.0006


def _close(left: Any, right: Any, tolerance: float = _ABS_TOLERANCE) -> bool:
    if left is None or right is None:
        return left is right
    try:
        return abs(float(left) - float(right)) <= tolerance
    except (TypeError, ValueError):
        return False


def _rows(value: Any) -> list[JsonObject]:
    return [dict(row) for row in value] if isinstance(value, list) else []


def _summary(rows: list[JsonObject]) -> JsonObject:
    outcomes = Counter(str(row.get("status")) for row in rows)
    scored = [row for row in rows if row.get("status") != "unscored"]
    losses = [row for row in rows if row.get("status") == "losing"]
    gaps = [float(row["competitor_minus_benchmark"]) for row in scored]
    losing_gaps = [abs(float(row["competitor_minus_benchmark"])) for row in losses]
    return {
        "benchmark_observed_stores": len(rows),
        "scored_stores": len(scored),
        "coverage_rate": round(len(scored) / len(rows), 4) if rows else None,
        "leader_stores": outcomes["leader"],
        "tied_stores": outcomes["tied"],
        "at_risk_stores": outcomes["at_risk"],
        "losing_stores": outcomes["losing"],
        "unscored_stores": outcomes["unscored"],
        "leader_rate": round(outcomes["leader"] / len(scored), 4) if scored else None,
        "average_gap": round(mean(gaps), 4) if gaps else None,
        "average_losing_gap": round(mean(losing_gaps), 4) if losing_gaps else None,
        "maximum_losing_gap": round(max(losing_gaps), 4) if losing_gaps else None,
    }


@dataclass(frozen=True, slots=True)
class ProductLeadershipCertification:
    checks: int
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.errors

    def require_ready(self) -> None:
        if self.errors:
            raise ValueError("; ".join(self.errors))


def certify_competitive_product_leadership(
    document: JsonObject,
) -> ProductLeadershipCertification:
    """Recompute decision-facing metrics and verify evidence invariants.

    The projector and this certifier intentionally do not share summary or
    classification helpers. This makes the check useful as an independent
    guard against a regression in the production calculation path.
    """

    errors: list[str] = []
    warnings: list[str] = []
    checks = 0

    def check(condition: bool, message: str) -> None:
        nonlocal checks
        checks += 1
        if not condition:
            errors.append(message)

    outcomes = _rows(document.get("outcomes"))
    policy = dict(document.get("policy") or {})
    filters = dict(document.get("filters") or {})
    relationships = _rows(document.get("relationships"))
    relationship_index = {
        str(row.get("relationship_id")): row for row in relationships if row.get("relationship_id")
    }
    parity = float(policy.get("parity_tolerance") or 0)
    at_risk = float(policy.get("at_risk_threshold") or 0)
    radius = float(filters.get("radius_miles") or 0)
    selected_product = str(dict(document.get("benchmark_product") or {}).get("id") or "")

    outcome_ids = [str(row.get("id") or "") for row in outcomes]
    scope_keys = [str(dict(row.get("benchmark") or {}).get("scope_key") or "") for row in outcomes]
    check(len(outcome_ids) == len(set(outcome_ids)), "outcome IDs are not unique")
    check(len(scope_keys) == len(set(scope_keys)), "benchmark locations are counted more than once")

    product_identities: dict[tuple[str, str], JsonObject] = {}
    relationship_usage: Counter[str] = Counter()
    for index, row in enumerate(outcomes):
        label = f"outcomes[{index}]"
        status = str(row.get("status") or "")
        benchmark = dict(row.get("benchmark") or {})
        competitor_raw = row.get("competitor")
        competitor = dict(competitor_raw) if isinstance(competitor_raw, dict) else None
        relationship_id = str(row.get("relationship_id") or "")
        gap = row.get("competitor_minus_benchmark")
        reduction = row.get("comparison_value_reduction_to_lead")
        ladder_raw = row.get("price_ladder")
        ladder = dict(ladder_raw) if isinstance(ladder_raw, dict) else None

        check(status in _STATUSES, f"{label}: unsupported status {status!r}")
        check(
            str(benchmark.get("product_id") or "") == selected_product,
            f"{label}: benchmark product differs from the selected product",
        )
        check(
            bool(benchmark.get("in_stock")) and float(benchmark.get("package_price") or 0) > 0,
            f"{label}: benchmark is not a positive-price Search observation",
        )
        check(
            float(benchmark.get("comparison_value") or 0) > 0,
            f"{label}: benchmark comparison value is not positive",
        )
        benchmark_identity = (
            str(benchmark.get("retailer_id")),
            str(benchmark.get("product_id")),
        )
        product_identities[benchmark_identity] = benchmark

        check(ladder is not None, f"{label}: price ladder is unavailable")
        if ladder is not None:
            rungs = _rows(ladder.get("rungs"))
            rung_prices = [
                float(dict(rung.get("location") or {}).get("comparison_value") or 0)
                for rung in rungs
            ]
            benchmark_rungs = [rung for rung in rungs if rung.get("is_benchmark") is True]
            check(bool(rungs), f"{label}: price ladder has no rungs")
            check(
                rung_prices == sorted(rung_prices),
                f"{label}: price ladder is not ordered from lowest to highest",
            )
            check(
                len(benchmark_rungs) == 1,
                f"{label}: price ladder must contain exactly one benchmark rung",
            )
            check(
                int(ladder.get("rung_count") or 0) == len(rungs),
                f"{label}: price ladder rung count does not reconcile",
            )
            if benchmark_rungs:
                benchmark_rung = benchmark_rungs[0]
                check(
                    str(dict(benchmark_rung.get("location") or {}).get("scope_key") or "")
                    == str(benchmark.get("scope_key") or ""),
                    f"{label}: price ladder benchmark location differs from the outcome",
                )
                check(
                    int(ladder.get("benchmark_rank") or 0)
                    == int(benchmark_rung.get("price_rank") or 0),
                    f"{label}: price ladder benchmark rank does not reconcile",
                )
            if rung_prices:
                check(
                    _close(
                        ladder.get("gap_to_leader"),
                        float(benchmark.get("comparison_value") or 0) - rung_prices[0],
                    ),
                    f"{label}: price ladder gap to leader does not reconcile",
                )

        if status == "unscored":
            check(competitor is None, f"{label}: unscored row has competitor evidence")
            check(not relationship_id, f"{label}: unscored row has a relationship")
            check(gap is None, f"{label}: unscored row has a price gap")
            check(reduction is None, f"{label}: unscored row has a reduction value")
            continue

        check(competitor is not None, f"{label}: scored row lacks competitor evidence")
        check(relationship_id in relationship_index, f"{label}: relationship is not declared")
        if competitor is None:
            continue
        relationship_usage[relationship_id] += 1
        competitor_identity = (
            str(competitor.get("retailer_id")),
            str(competitor.get("product_id")),
        )
        product_identities[competitor_identity] = competitor
        relationship = relationship_index.get(relationship_id, {})
        check(
            str(competitor.get("retailer_id")) == str(relationship.get("competitor_id")),
            f"{label}: competitor retailer differs from the relationship",
        )
        check(
            str(competitor.get("product_id")) == str(relationship.get("competitor_product_id")),
            f"{label}: competitor product differs from the relationship",
        )
        check(
            bool(competitor.get("in_stock")) and float(competitor.get("package_price") or 0) > 0,
            f"{label}: competitor is not a positive-price Search observation",
        )
        expected_gap = float(competitor.get("comparison_value") or 0) - float(
            benchmark.get("comparison_value") or 0
        )
        check(_close(gap, expected_gap), f"{label}: price gap does not reconcile")

        if abs(expected_gap) <= parity:
            expected_status = "tied"
        elif expected_gap < -parity:
            expected_status = "losing"
        elif expected_gap <= at_risk:
            expected_status = "at_risk"
        else:
            expected_status = "leader"
        check(status == expected_status, f"{label}: status does not match the governed thresholds")
        expected_reduction = (
            float(benchmark.get("comparison_value") or 0)
            - float(competitor.get("comparison_value") or 0)
            + parity
            if expected_status == "losing"
            else None
        )
        check(
            _close(reduction, expected_reduction),
            f"{label}: reduction-to-lead does not reconcile",
        )

        if competitor.get("location_kind") == "service_area":
            check(row.get("distance_miles") is None, f"{label}: service area exposes a distance")
            check(
                bool(benchmark.get("zipcode"))
                and benchmark.get("zipcode") == competitor.get("zipcode"),
                f"{label}: service-area comparison is not exact ZIP",
            )
        else:
            distance = row.get("distance_miles")
            check(distance is not None, f"{label}: physical-store comparison lacks distance")
            if distance is not None:
                check(float(distance) <= radius + 0.01, f"{label}: competitor is outside radius")

    expected_summary = _summary(outcomes)
    reported_summary = dict(document.get("summary") or {})
    for field, expected in expected_summary.items():
        check(
            _close(reported_summary.get(field), expected),
            f"summary.{field} does not reconcile to outcomes",
        )

    grouped_states: dict[str, list[JsonObject]] = defaultdict(list)
    grouped_cities: dict[str, list[JsonObject]] = defaultdict(list)
    grouped_competitors: dict[str, list[JsonObject]] = defaultdict(list)
    for row in outcomes:
        benchmark = dict(row.get("benchmark") or {})
        state = str(benchmark.get("state") or "Unknown state")
        city = str(benchmark.get("city") or "Unknown city")
        grouped_states[state].append(row)
        grouped_cities[f"{city}, {state}"].append(row)
        competitor = row.get("competitor")
        if isinstance(competitor, dict):
            grouped_competitors[str(competitor.get("retailer_id"))].append(row)

    def certify_groups(
        reported: list[JsonObject],
        grouped: dict[str, list[JsonObject]],
        *,
        label_field: str,
        prefix: str,
    ) -> None:
        index = {str(row.get(label_field)): row for row in reported}
        check(set(index) == set(grouped), f"{prefix} labels do not partition current outcomes")
        for label, rows in grouped.items():
            expected = _summary(rows)
            actual = index.get(label, {})
            for field, value in expected.items():
                check(
                    _close(actual.get(field), value),
                    f"{prefix} {label!r} field {field!r} does not reconcile",
                )

    certify_groups(
        _rows(document.get("state_summaries")),
        grouped_states,
        label_field="label",
        prefix="state summary",
    )
    city_rows = _rows(document.get("city_summaries"))
    if filters.get("state") is None:
        check(not city_rows, "city summaries are populated without a state filter")
    else:
        certify_groups(
            city_rows,
            grouped_cities,
            label_field="label",
            prefix="city summary",
        )

    competitor_rows = _rows(document.get("competitor_summaries"))
    competitor_index = {str(row.get("competitor_id")): row for row in competitor_rows}
    check(
        set(competitor_index) == set(grouped_competitors),
        "competitor summaries do not partition scored outcomes",
    )
    for competitor_id, rows in grouped_competitors.items():
        expected = _summary(rows)
        actual = competitor_index.get(competitor_id, {})
        for field, value in expected.items():
            check(
                _close(actual.get(field), value),
                f"competitor summary {competitor_id!r} field {field!r} does not reconcile",
            )

    filter_options = dict(document.get("filter_options") or {})
    state_options = {
        str(row.get("value")): int(row.get("count") or 0)
        for row in _rows(filter_options.get("states"))
    }
    check(
        state_options == {label: len(rows) for label, rows in grouped_states.items()},
        "state filter counts do not reconcile to outcomes",
    )

    unused_relationships = sorted(set(relationship_index) - set(relationship_usage))
    if unused_relationships:
        warnings.append(
            f"{len(unused_relationships)} governed relationship(s) have no comparable "
            "current observation"
        )
    if outcomes and not expected_summary["scored_stores"]:
        warnings.append("the selected product has no comparable current store evidence")
    unresolved = [
        identity
        for identity in product_identities.values()
        if identity.get("brand_type") == "unclassified"
    ]
    if unresolved:
        warnings.append(
            f"{len(unresolved)} selected retailer product(s) have unclassified brand type"
        )
    missing_images = [
        identity for identity in product_identities.values() if not identity.get("image_url")
    ]
    if missing_images:
        warnings.append(f"{len(missing_images)} selected retailer product(s) lack imagery")

    return ProductLeadershipCertification(
        checks=checks,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )
