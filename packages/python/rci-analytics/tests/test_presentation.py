from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from rci_analytics.models import ClassifiedOffer, MatchRecord, NormalizedOffer
from rci_analytics.presentation import (
    benchmark_product_decisions,
    benchmark_product_evidence,
    benchmark_product_map_points,
    benchmark_product_match_candidates,
    merge_product_decision_context,
    merge_product_evidence_summary,
)


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
    assert points[0]["comparison_metric"] == "package_price"
    assert points[0]["value_label"] == "Benchmark lower · paired difference $1.25 /package"


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


def test_product_decisions_prioritize_losses_and_name_locations() -> None:
    benchmark = [_offer("store-a", "100", -94.2), _offer("store-b", "100", -90.1)]
    competitor = [
        ClassifiedOffer(
            offer=NormalizedOffer(
                offer_id=f"competitor-{item.offer.offer_id}",
                retailer_id="aldi_us",
                retailer_product_id="aldi-100",
                title="ALDI comparison product",
                brand=None,
                price=Decimal("3.50"),
                currency="USD",
                zipcode=item.offer.zipcode,
                store_number="aldi-store",
                latitude=item.offer.latitude,
                longitude=item.offer.longitude,
                in_stock=True,
                product_url="https://example.com/aldi-100",
                image_url="https://example.com/aldi-100.jpg",
                collected_at=None,
                raw={},
            ),
            in_scope=True,
            scope_reason=None,
            attributes={"size": "1 lb"},
            metrics={},
            review_reasons=(),
        )
        for item in benchmark
    ]
    decisions = benchmark_product_decisions(
        [*benchmark, *competitor],
        [_match("store-a", "aldi_us", "-0.50"), _match("store-b", "aldi_us", "-0.25")],
        benchmark_retailer="walmart_us",
    )

    assert len(decisions) == 1
    assert decisions[0]["priority"] == "attention"
    assert decisions[0]["competitor_product_name"] == "ALDI comparison product"
    assert decisions[0]["plain_insight"] == ("Competitor is $0.38 lower at the paired median")
    assert decisions[0]["geographies"] == 2
    assert decisions[0]["top_locations"][0]["zipcode"] == "72712"
    assert decisions[0]["match_attributes"] == {"size": "1 lb"}


def test_match_candidates_preserve_profile_eligibility_without_inventing_pairs() -> None:
    benchmark = [_offer("store-a", "100", -94.2)]
    competitor = [
        ClassifiedOffer(
            offer=replace(
                benchmark[0].offer,
                offer_id="competitor-store-a",
                retailer_id="aldi_us",
                retailer_product_id="aldi-100",
                title="ALDI comparison product",
            ),
            in_scope=True,
            scope_reason=None,
            attributes={"size": "1 lb"},
            metrics={},
            review_reasons=(),
        )
    ]
    strict = _match("store-a", "aldi_us", "-0.50")
    unit = replace(
        strict,
        profile_id="unit_price",
        comparison_metric="price_per_lb",
        gap=Decimal("-0.25"),
    )

    candidates = benchmark_product_match_candidates(
        [*benchmark, *competitor],
        [strict, unit],
        benchmark_retailer="walmart_us",
        profiles=[
            {
                "id": "strict",
                "label": "Exact package",
                "geography": "exact_zip",
                "comparison_metric": "package_price",
            },
            {
                "id": "unit_price",
                "label": "Price per pound",
                "geography": "exact_zip",
                "comparison_metric": "price_per_lb",
            },
        ],
    )

    assert [row["profile_id"] for row in candidates] == ["strict", "unit_price"]
    assert [row["match_basis"] for row in candidates] == [
        "exact_package",
        "normalized_unit",
    ]
    assert all("size" in str(row["match_rationale"]) for row in candidates)
    assert all(
        row["benchmark_location_scope_keys"] == ["walmart_us|72712|store-a"] for row in candidates
    )


def test_presentation_excludes_mismatched_weighted_multipacks() -> None:
    benchmark = _offer("store-a", "walmart-three-pack", -94.2)
    benchmark = replace(
        benchmark,
        offer=replace(benchmark.offer, title="Organic Ground Beef, 1 lb, 3 Count"),
    )
    competitor = _offer("competitor-store-a", "aldi-single", -94.2)
    competitor = replace(
        competitor,
        offer=replace(
            competitor.offer,
            retailer_id="aldi_us",
            title="Organic Ground Beef, 1 lb",
        ),
    )
    matches = [_match("store-a", "aldi_us", "-10.00")]

    assert (
        benchmark_product_decisions(
            [benchmark, competitor],
            matches,
            benchmark_retailer="walmart_us",
        )
        == []
    )
    assert (
        benchmark_product_map_points(
            [benchmark, competitor],
            matches,
            benchmark_retailer="walmart_us",
        )
        == []
    )


def test_pdp_context_improves_identity_without_changing_price_evidence() -> None:
    decision = {
        "id": "decision-1",
        "benchmark_product_id": "100",
        "benchmark_product_name": "Search title",
        "competitor": "aldi_us",
        "competitor_product_id": "200",
        "competitor_product_name": "Search competitor title",
        "median_gap": -0.5,
    }
    enriched = merge_product_decision_context(
        [decision],
        [
            {
                "canonical_product_id": "walmart_us:100",
                "name": "PDP product title",
                "image_url": "https://example.com/product.jpg",
                "specification": {"size": "one pound"},
            }
        ],
        benchmark_retailer="walmart_us",
    )

    assert enriched[0]["benchmark_product_name"] == "PDP product title"
    assert enriched[0]["benchmark_image_url"] == "https://example.com/product.jpg"
    assert enriched[0]["benchmark_specification"] == {"size": "one pound"}
    assert enriched[0]["median_gap"] == -0.5


def test_product_evidence_reports_every_benchmark_store_without_changing_match_grain() -> None:
    benchmark = [
        _offer("walmart-1", "100", -94.2),
        _offer("walmart-2", "100", -94.1),
    ]
    competitor = ClassifiedOffer(
        offer=NormalizedOffer(
            offer_id="aldi-1",
            retailer_id="aldi_us",
            retailer_product_id="200",
            title="ALDI comparison product",
            brand=None,
            price=Decimal("3.50"),
            currency="USD",
            zipcode="72712",
            store_number="aldi-store",
            latitude=36.38,
            longitude=-94.15,
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
    decision = {
        "id": "decision-1",
        "benchmark_product_id": "100",
        "competitor": "aldi_us",
        "competitor_product_id": "200",
    }

    evidence = benchmark_product_evidence(
        [*benchmark, competitor],
        [decision],
        benchmark_retailer="walmart_us",
    )
    summary = evidence["decision-1"]["summary"]

    assert summary == {
        "matched_zip_markets": 1,
        "benchmark_store_observations": 2,
        "competitor_store_observations": 1,
        "benchmark_stores_lower": 0,
        "benchmark_stores_undercut": 2,
        "price_parity": 0,
    }
    assert len(evidence["decision-1"]["rows"]) == 2
    assert evidence["decision-1"]["comparison_metric"] == "package_price"
    assert evidence["decision-1"]["comparison_unit"] == "USD/package"
    assert evidence["decision-1"]["raw_price_unit"] == "USD/package"
    assert evidence["decision-1"]["rows"][0]["comparison_gap"] == -0.5
    merged = merge_product_evidence_summary([decision], evidence)
    assert merged[0]["evidence_available"] is True
    assert merged[0]["evidence_summary"] == summary


def test_normalized_product_evidence_uses_governed_unit_values_and_retains_raw_prices() -> None:
    benchmark = replace(
        _offer("walmart-1", "100", -94.2),
        offer=replace(_offer("walmart-1", "100", -94.2).offer, price=Decimal("4.00")),
        metrics={"price_per_lb": Decimal("2.00")},
    )
    competitor = ClassifiedOffer(
        offer=replace(
            benchmark.offer,
            offer_id="aldi-1",
            retailer_id="aldi_us",
            retailer_product_id="200",
            title="ALDI comparison product",
            price=Decimal("3.50"),
            store_number="aldi-store",
        ),
        in_scope=True,
        scope_reason=None,
        attributes={"size": "0.5 lb"},
        metrics={"price_per_lb": Decimal("3.00")},
        review_reasons=(),
    )
    decision = {
        "id": "normalized-decision",
        "benchmark_product_id": "100",
        "competitor": "aldi_us",
        "competitor_product_id": "200",
        "comparison_metric": "price_per_lb",
    }

    row = benchmark_product_evidence(
        [benchmark, competitor],
        [decision],
        benchmark_retailer="walmart_us",
    )["normalized-decision"]["rows"][0]

    assert row["benchmark_price"] == 4.0
    assert row["competitor_price"] == 3.5
    assert row["competitor_minus_benchmark"] == -0.5
    assert row["benchmark_comparison_value"] == 2.0
    assert row["competitor_comparison_value"] == 3.0
    assert row["comparison_gap"] == 1.0
    assert row["outcome"] == "benchmark_lower"
    assert row["comparison_unit"] == "USD/lb"
