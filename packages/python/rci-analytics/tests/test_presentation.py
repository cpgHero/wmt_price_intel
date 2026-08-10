from __future__ import annotations

from decimal import Decimal

from rci_analytics.models import ClassifiedOffer, MatchRecord, NormalizedOffer
from rci_analytics.presentation import benchmark_product_map_points


def _offer(offer_id: str, product_id: str, longitude: float) -> ClassifiedOffer:
    return ClassifiedOffer(
        offer=NormalizedOffer(
            offer_id=offer_id,
            retailer_id="walmart_us",
            retailer_product_id=product_id,
            title=f"Benchmark product {product_id}",
            brand=None,
            price=Decimal("4.00"),
            currency="USD",
            zipcode="72712",
            store_number=offer_id,
            latitude=36.37,
            longitude=longitude,
            in_stock=True,
            product_url=None,
            image_url=None,
            collected_at=None,
            raw={},
        ),
        in_scope=True,
        scope_reason=None,
        attributes={"size": "1 lb"},
        metrics={},
        review_reasons=(),
    )


def _match(offer_id: str, competitor: str, gap: str) -> MatchRecord:
    value = Decimal(gap)
    return MatchRecord(
        profile_id="strict",
        competitor_id=competitor,
        geography_key="72712",
        benchmark_offer_id=offer_id,
        competitor_offer_id=f"competitor-{offer_id}",
        attributes={"size": "1 lb"},
        comparison_metric="package_price",
        benchmark_value=Decimal("4.00"),
        competitor_value=Decimal("4.00") + value,
        gap=value,
        winner="benchmark_lower" if value > 0 else "competitor_lower",
    )


def test_map_points_are_filterable_by_benchmark_product_and_evidence_linked() -> None:
    offers = [_offer("store-a", "100", -94.2), _offer("store-b", "200", -90.1)]
    points = benchmark_product_map_points(
        offers,
        [_match("store-a", "aldi_us", "1.25"), _match("store-b", "aldi_us", "-0.50")],
        benchmark_retailer="walmart_us",
    )

    assert {point["benchmark_product_id"] for point in points} == {"100", "200"}
    assert {point["outcome"] for point in points} == {
        "benchmark_lower",
        "competitor_lower",
    }
    assert points[0]["benchmark_price"] == 4.0
    assert points[0]["competitor"] == "aldi_us"


def test_map_points_apply_deterministic_product_and_location_caps() -> None:
    offers = [
        _offer(f"store-{product}-{index}", product, -124 + index)
        for product in ("100", "200")
        for index in range(4)
    ]
    matches = [_match(item.offer.offer_id, "aldi_us", "1.00") for item in offers]

    points = benchmark_product_map_points(
        offers,
        matches,
        benchmark_retailer="walmart_us",
        max_products=1,
        max_points_per_product=2,
    )

    assert len(points) == 2
    assert {point["benchmark_product_id"] for point in points} == {"100"}
