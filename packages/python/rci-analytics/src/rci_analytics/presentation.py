"""Deterministic, evidence-linked presentation context for analysis reports."""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Iterable
from decimal import Decimal
from statistics import median

from rci_analytics.models import ClassifiedOffer, JsonObject, MatchRecord, NormalizedOffer


def _preferred_text(values: Iterable[str | None], fallback: str) -> str:
    counts = Counter(value.strip() for value in values if value and value.strip())
    if not counts:
        return fallback
    return sorted(counts, key=lambda value: (-counts[value], value))[0]


def _money(value: Decimal) -> str:
    return f"${abs(value):,.2f}"


def benchmark_product_decisions(
    offers: Iterable[ClassifiedOffer],
    matches: Iterable[MatchRecord],
    *,
    benchmark_retailer: str,
    max_rows: int = 16,
    max_locations_per_row: int = 3,
) -> list[JsonObject]:
    """Build decision-first product pairs from admitted exact-match evidence.

    This is presentation context rather than a new analytical metric surface. It keeps
    product identity, outcomes, prices, and locations tied to the underlying match rows.
    """

    if max_rows < 1 or max_locations_per_row < 1:
        raise ValueError("product decision row and location limits must be positive")
    offer_index = {item.offer.offer_id: item.offer for item in offers}
    grouped: dict[
        tuple[str, str, str], list[tuple[MatchRecord, NormalizedOffer, NormalizedOffer]]
    ] = {}
    for match in matches:
        benchmark = offer_index.get(match.benchmark_offer_id)
        competitor = offer_index.get(match.competitor_offer_id)
        if benchmark is None or competitor is None or benchmark.retailer_id != benchmark_retailer:
            continue
        key = (
            benchmark.retailer_product_id,
            match.competitor_id,
            competitor.retailer_product_id,
        )
        grouped.setdefault(key, []).append((match, benchmark, competitor))

    rows: list[JsonObject] = []
    for (benchmark_product_id, competitor_id, competitor_product_id), values in grouped.items():
        match_rows = [value[0] for value in values]
        benchmark_offers = [value[1] for value in values]
        competitor_offers = [value[2] for value in values]
        outcomes = Counter(match.winner for match in match_rows)
        match_count = len(match_rows)
        benchmark_lower = outcomes["benchmark_lower"]
        competitor_lower = outcomes["competitor_lower"]
        parity = outcomes["parity"]
        median_gap = median(match.gap for match in match_rows)
        priority = (
            "attention"
            if competitor_lower > benchmark_lower
            else "protect"
            if benchmark_lower > competitor_lower
            else "parity"
        )
        lead = (
            f"Competitor is typically {_money(median_gap)} higher"
            if median_gap > 0
            else f"Competitor is typically {_money(median_gap)} lower"
            if median_gap < 0
            else "Typical prices are tied"
        )
        geography_rows: dict[str, JsonObject] = {}
        for match, benchmark, _competitor in values:
            location_key = f"{benchmark.zipcode}|{benchmark.store_number or ''}"
            candidate: JsonObject = {
                "zipcode": benchmark.zipcode,
                "store": benchmark.store_number,
                "outcome": match.winner,
                "benchmark_price": float(match.benchmark_value),
                "competitor_price": float(match.competitor_value),
                "gap": float(match.gap),
            }
            existing = geography_rows.get(location_key)
            if existing is None or abs(float(candidate["gap"])) > abs(float(existing["gap"])):
                geography_rows[location_key] = candidate
        top_locations = sorted(
            geography_rows.values(),
            key=lambda value: (
                0 if value["outcome"] == "competitor_lower" else 1,
                -abs(float(value["gap"])),
                str(value["zipcode"]),
                str(value.get("store") or ""),
            ),
        )[:max_locations_per_row]
        seed = "|".join((benchmark_product_id, competitor_id, competitor_product_id))
        rows.append(
            {
                "id": f"product-{hashlib.sha256(seed.encode()).hexdigest()[:20]}",
                "priority": priority,
                "benchmark_product_id": benchmark_product_id,
                "benchmark_product_name": _preferred_text(
                    (offer.title for offer in benchmark_offers), benchmark_product_id
                ),
                "benchmark_image_url": _preferred_text(
                    (offer.image_url for offer in benchmark_offers), ""
                )
                or None,
                "benchmark_product_url": _preferred_text(
                    (offer.product_url for offer in benchmark_offers), ""
                )
                or None,
                "competitor": competitor_id,
                "competitor_product_id": competitor_product_id,
                "competitor_product_name": _preferred_text(
                    (offer.title for offer in competitor_offers), competitor_product_id
                ),
                "competitor_image_url": _preferred_text(
                    (offer.image_url for offer in competitor_offers), ""
                )
                or None,
                "competitor_product_url": _preferred_text(
                    (offer.product_url for offer in competitor_offers), ""
                )
                or None,
                "matches": match_count,
                "geographies": len(geography_rows),
                "benchmark_lower": benchmark_lower,
                "competitor_lower": competitor_lower,
                "parity": parity,
                "benchmark_lower_share": benchmark_lower / match_count,
                "competitor_lower_share": competitor_lower / match_count,
                "median_benchmark_price": float(
                    median(match.benchmark_value for match in match_rows)
                ),
                "median_competitor_price": float(
                    median(match.competitor_value for match in match_rows)
                ),
                "median_gap": float(median_gap),
                "plain_insight": lead,
                "top_locations": top_locations,
            }
        )
    ranked = sorted(
        rows,
        key=lambda row: (
            {"attention": 0, "protect": 1, "parity": 2}[str(row["priority"])],
            -float(
                row["competitor_lower_share"]
                if row["priority"] == "attention"
                else row["benchmark_lower_share"]
            ),
            -abs(float(row["median_gap"])),
            -int(row["geographies"]),
            str(row["benchmark_product_id"]),
            str(row["competitor_product_id"]),
        ),
    )
    if len(ranked) <= max_rows:
        return ranked
    attention = [row for row in ranked if row["priority"] == "attention"]
    protect = [row for row in ranked if row["priority"] == "protect"]
    parity_rows = [row for row in ranked if row["priority"] == "parity"]
    attention_limit = min(len(attention), max(1, (max_rows * 5 + 7) // 8))
    protect_limit = min(len(protect), max_rows - attention_limit)
    selected = [*attention[:attention_limit], *protect[:protect_limit]]
    selected_ids = {str(row["id"]) for row in selected}
    selected.extend(
        row
        for row in [*parity_rows, *attention[attention_limit:], *protect[protect_limit:]]
        if str(row["id"]) not in selected_ids
    )
    return selected[:max_rows]


def merge_product_decision_context(
    decisions: Iterable[JsonObject],
    product_context: Iterable[JsonObject],
    *,
    benchmark_retailer: str,
) -> list[JsonObject]:
    """Overlay PDP-backed identity fields without changing price-decision evidence."""

    context_index = {
        str(item.get("canonical_product_id")): item
        for item in product_context
        if item.get("canonical_product_id")
    }
    merged: list[JsonObject] = []
    for source in decisions:
        row = dict(source)
        for prefix, retailer, product_id in (
            (
                "benchmark",
                benchmark_retailer,
                str(row.get("benchmark_product_id", "")),
            ),
            (
                "competitor",
                str(row.get("competitor", "")),
                str(row.get("competitor_product_id", "")),
            ),
        ):
            context = context_index.get(f"{retailer}:{product_id}")
            if context is None:
                continue
            for target, source_name in (
                (f"{prefix}_product_name", "name"),
                (f"{prefix}_image_url", "image_url"),
                (f"{prefix}_product_url", "url"),
                (f"{prefix}_brand", "brand"),
                (f"{prefix}_description", "description"),
                (f"{prefix}_category_path", "category_path"),
                (f"{prefix}_identifiers", "identifiers"),
                (f"{prefix}_specification", "specification"),
                (f"{prefix}_physical_properties", "physical_properties"),
                (f"{prefix}_variant_configuration", "variant_configuration"),
            ):
                value = context.get(source_name)
                if value not in (None, "", {}, []):
                    row[target] = value
        merged.append(row)
    return merged


def _sample_geographies(rows: list[JsonObject], limit: int) -> list[JsonObject]:
    """Select a stable, geographically distributed sample for browser-safe maps."""

    ordered = sorted(
        rows,
        key=lambda row: (
            float(row["longitude"]),
            float(row["latitude"]),
            str(row["id"]),
        ),
    )
    if len(ordered) <= limit:
        return ordered
    return [ordered[(index * len(ordered)) // limit] for index in range(limit)]


def benchmark_product_map_points(
    offers: Iterable[ClassifiedOffer],
    matches: Iterable[MatchRecord],
    *,
    benchmark_retailer: str,
    max_products: int = 20,
    max_points_per_product: int = 150,
) -> list[JsonObject]:
    """Project exact-match evidence into a benchmark-product-filterable map dataset."""

    if max_products < 1 or max_points_per_product < 1:
        raise ValueError("map Product and point limits must be positive")
    offer_index = {item.offer.offer_id: item for item in offers}
    candidate_rows: list[JsonObject] = []
    product_counts: Counter[str] = Counter()
    for match in matches:
        benchmark = offer_index.get(match.benchmark_offer_id)
        if benchmark is None or benchmark.offer.retailer_id != benchmark_retailer:
            continue
        offer = benchmark.offer
        if offer.latitude is None or offer.longitude is None:
            continue
        product_id = offer.retailer_product_id
        point_seed = "|".join(
            (
                match.profile_id,
                match.competitor_id,
                product_id,
                match.geography_key,
                offer.offer_id,
            )
        )
        point_id = hashlib.sha256(point_seed.encode()).hexdigest()[:24]
        gap = float(match.gap)
        outcome_label = {
            "benchmark_lower": "Benchmark lower",
            "competitor_lower": "Competitor lower",
            "parity": "Price parity",
        }.get(match.winner, match.winner.replace("_", " ").title())
        candidate_rows.append(
            {
                "id": point_id,
                "label": offer.title,
                "latitude": offer.latitude,
                "longitude": offer.longitude,
                "value": gap,
                "value_label": f"{outcome_label} · price difference ${abs(gap):.2f}",
                "retailer": benchmark_retailer,
                "benchmark_product_id": product_id,
                "benchmark_product_name": offer.title,
                "competitor": match.competitor_id,
                "outcome": match.winner,
                "zipcode": offer.zipcode,
                "store": offer.store_number,
                "benchmark_price": float(match.benchmark_value),
                "competitor_price": float(match.competitor_value),
                "matches": 1,
            }
        )
        product_counts[product_id] += 1
    selected_products = {
        product_id
        for product_id, _count in sorted(
            product_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )[:max_products]
    }
    by_product: dict[str, list[JsonObject]] = {product_id: [] for product_id in selected_products}
    for row in candidate_rows:
        product_id = str(row["benchmark_product_id"])
        if product_id in by_product:
            by_product[product_id].append(row)
    return [
        row
        for product_id in sorted(
            by_product,
            key=lambda value: (-product_counts[value], value),
        )
        for row in _sample_geographies(by_product[product_id], max_points_per_product)
    ]
