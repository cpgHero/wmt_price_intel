"""Deterministic, evidence-linked presentation context for analysis reports."""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Iterable

from rci_analytics.models import ClassifiedOffer, JsonObject, MatchRecord


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
                "value_label": f"{outcome_label} · signed gap ${gap:+.2f}",
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
