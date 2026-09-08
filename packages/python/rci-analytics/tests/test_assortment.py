from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from rci_analytics import AssortmentAccumulator, merge_assortment_product_context
from rci_analytics.classification import OfferClassifier
from rci_analytics.models import ClassifiedOffer, MatchRecord, NormalizedOffer
from rci_analytics.product_pack import ProductPackLoader

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def _offer(
    offer_id: str,
    retailer: str,
    product_id: str,
    zipcode: str | None,
    store: str | None,
    *,
    brand: str | None = None,
    brand_type: str | None = None,
    in_stock: bool | None = True,
    is_sponsored: bool | None = False,
    collected_at: str | None = None,
) -> ClassifiedOffer:
    return ClassifiedOffer(
        offer=NormalizedOffer(
            offer_id=offer_id,
            retailer_id=retailer,
            retailer_product_id=product_id,
            title=f"Product {product_id}",
            brand=brand,
            price=Decimal("4.99"),
            currency="USD",
            zipcode=zipcode,
            store_number=store,
            latitude=None,
            longitude=None,
            in_stock=in_stock,
            product_url=None,
            image_url=None,
            collected_at=collected_at,
            raw={},
            is_sponsored=is_sponsored,
        ),
        in_scope=True,
        scope_reason=None,
        attributes=(
            {
                "_brand_governance": {
                    "status": "resolved",
                    "role": brand_type,
                }
            }
            if brand_type
            else {}
        ),
        metrics={"package_price": Decimal("4.99")},
        review_reasons=(),
    )


def test_assortment_metrics_are_distinct_product_and_store_based() -> None:
    accumulator = AssortmentAccumulator()
    for offer in (
        _offer("w1-a", "walmart_us", "w1", "72712", "1"),
        _offer("w1-b", "walmart_us", "w1", "72713", "2"),
        _offer("w2", "walmart_us", "w2", "72712", "1"),
        _offer("a1", "aldi_us", "a1", "72712", "A"),
        _offer("a2", "aldi_us", "a2", "72713", "B"),
    ):
        accumulator.add(offer)
    result = accumulator.finalize(
        benchmark_retailer="walmart_us",
        competitors=["aldi_us"],
        profiles=[
            {
                "id": "strict",
                "label": "Exact package",
                "geography": "exact_zip",
            }
        ],
        matches=[
            MatchRecord(
                profile_id="strict",
                competitor_id="aldi_us",
                geography_key="72712",
                benchmark_offer_id="w1-a",
                competitor_offer_id="a1",
                attributes={},
                comparison_metric="package_price",
                benchmark_value=Decimal("4.99"),
                competitor_value=Decimal("4.79"),
                gap=Decimal("-0.20"),
                winner="competitor",
            )
        ],
    )

    comparison = result["comparisons"][0]
    assert result["retailers"][0]["distinct_products"] == 2
    assert {row["product_id"] for row in result["retailers"][0]["products"]} == {"w1", "w2"}
    assert result["retailers"][0]["products"][0]["location_scope_keys"][0].startswith("walmart_us|")
    assert comparison["product_relationships"] == 1
    assert comparison["benchmark_only_products"] == 1
    assert comparison["competitor_whitespace_products"] == 1
    assert comparison["benchmark_match_coverage"] == 0.5
    assert comparison["top_benchmark_only"][0]["product_id"] == "w2"
    assert comparison["ambiguous_candidate_groups"] == 0
    assert comparison["geography"]["top_benchmark_breadth_gaps"] == [
        {
            "zipcode": "72712",
            "benchmark_products": 2,
            "competitor_products": 1,
            "product_count_gap": 1,
        }
    ]


def test_assortment_reports_brand_breadth_and_geographic_concentration() -> None:
    accumulator = AssortmentAccumulator()
    for offer in (
        _offer("w1", "walmart_us", "w1", "72712", "1", brand="Regional Dairy"),
        _offer("w2", "walmart_us", "w2", "72713", "2", brand="Regional Dairy"),
        _offer("w3", "walmart_us", "w3", "90020", "3", brand="National Dairy"),
        _offer("w3b", "walmart_us", "w3", "98101", "7", brand="National Dairy"),
        _offer("w3c", "walmart_us", "w3", "80202", "8", brand="National Dairy"),
        _offer("w3d", "walmart_us", "w3", "02108", "9", brand="National Dairy"),
        _offer("w4", "walmart_us", "w4", "10001", "4", brand="National Dairy"),
        _offer("w5", "walmart_us", "w5", "60601", "5", brand="National Dairy"),
        _offer("w6", "walmart_us", "w6", "30301", "6"),
        _offer("a1", "aldi_us", "a1", "72712", "A", brand="Friendly Farms"),
    ):
        accumulator.add(offer)

    result = accumulator.finalize(
        benchmark_retailer="walmart_us",
        competitors=["aldi_us"],
        profiles=[{"id": "strict", "label": "Exact package", "geography": "exact_zip"}],
        matches=[],
        ambiguous_groups=[
            {
                "competitor_id": "aldi_us",
                "candidates": [
                    {
                        "benchmark_product_id": "w1",
                        "competitor_product_id": "a1",
                    }
                ],
            }
        ],
    )

    walmart = result["retailers"][0]
    comparison = result["comparisons"][0]
    assert walmart["distinct_brands"] == 2
    assert walmart["unbranded_products"] == 1
    assert walmart["top_brands"][0]["brand"] == "National Dairy"
    assert walmart["top_brands"][0]["distinct_products"] == 3
    assert walmart["top_brands"][0]["distribution_store_count"] == 6
    assert walmart["top_brands"][0]["service_area_presence_count"] == 0
    assert walmart["top_brands"][0]["observed_zipcodes"] == 6
    assert walmart["geographically_concentrated_brands"][0]["brand"] == ("Regional Dairy")
    assert comparison["ambiguous_candidate_groups"] == 1
    assert comparison["ambiguous_benchmark_products"] == 1
    assert comparison["ambiguous_competitor_products"] == 1
    assert comparison["benchmark_only_products"] == 5
    assert comparison["competitor_whitespace_products"] == 0


def test_assortment_products_retain_governed_brand_type() -> None:
    accumulator = AssortmentAccumulator()
    accumulator.add(
        _offer(
            "w1",
            "walmart_us",
            "w1",
            "72712",
            "1",
            brand="Great Value",
            brand_type="private_label",
        )
    )

    result = accumulator.finalize(
        benchmark_retailer="walmart_us",
        competitors=[],
        profiles=[],
        matches=[],
    )

    assert result["retailers"][0]["products"][0]["brand_type"] == "private_label"


def test_assortment_counts_positive_price_store_search_rows_without_stock_gating() -> None:
    accumulator = AssortmentAccumulator()
    for offer in (
        _offer("verified", "walmart_us", "verified", "10001", "1"),
        _offer(
            "out-of-stock",
            "walmart_us",
            "out-of-stock",
            "10002",
            "2",
            in_stock=False,
        ),
        _offer(
            "sponsored",
            "walmart_us",
            "sponsored",
            "10003",
            "3",
            is_sponsored=True,
        ),
        _offer(
            "unknown-stock",
            "walmart_us",
            "unknown-stock",
            "10004",
            "4",
            in_stock=None,
        ),
        _offer(
            "unknown-sponsorship",
            "walmart_us",
            "unknown-sponsorship",
            "10005",
            "5",
            is_sponsored=None,
        ),
    ):
        accumulator.add(offer)

    result = accumulator.finalize(
        benchmark_retailer="walmart_us",
        competitors=[],
        profiles=[],
        matches=[],
    )

    walmart = result["retailers"][0]
    assert walmart["distinct_products"] == 5
    assert walmart["search_distinct_products"] == 5
    assert walmart["observed_locations"] == 5
    assert walmart["distribution_store_count"] == 5
    assert walmart["service_area_presence_count"] == 0
    products = {row["product_id"]: row for row in walmart["products"]}
    assert all(product["distribution_store_count"] == 1 for product in products.values())
    assert all(product["service_area_presence_count"] == 0 for product in products.values())
    assert products["sponsored"]["location_scope_keys"] == ["walmart_us|store|3"]
    assert all("availability_status" not in product for product in products.values())
    assert all("in_stock" not in product for product in products.values())


def test_assortment_uses_latest_positive_price_row_without_stock_tie_gating() -> None:
    accumulator = AssortmentAccumulator()
    for offer in (
        # Intentionally arrive newest first: input order must not resurrect stale stock.
        _offer(
            "newer-oos",
            "walmart_us",
            "chronological",
            "10001",
            "1",
            in_stock=False,
            collected_at="2026-08-07T12:05:00Z",
        ),
        _offer(
            "older-in-stock",
            "walmart_us",
            "chronological",
            "10001",
            "1",
            collected_at="2026-08-07T12:00:00Z",
        ),
        # A verified organic row wins a same-time tie with sponsored evidence.
        _offer(
            "z-sponsored",
            "walmart_us",
            "organic-tie",
            "10002",
            "2",
            is_sponsored=True,
            collected_at="2026-08-07T12:00:00Z",
        ),
        _offer(
            "a-organic",
            "walmart_us",
            "organic-tie",
            "10002",
            "2",
            collected_at="2026-08-07T12:00:00Z",
        ),
        # Contradictory organic evidence at one instant fails closed to out-of-stock.
        _offer(
            "organic-out",
            "walmart_us",
            "stock-conflict",
            "10003",
            "3",
            in_stock=False,
            collected_at="2026-08-07T12:00:00Z",
        ),
        _offer(
            "organic-in",
            "walmart_us",
            "stock-conflict",
            "10003",
            "3",
            collected_at="2026-08-07T12:00:00Z",
        ),
    ):
        accumulator.add(offer)

    result = accumulator.finalize(
        benchmark_retailer="walmart_us",
        competitors=[],
        profiles=[],
        matches=[],
    )
    walmart = result["retailers"][0]
    products = {row["product_id"]: row for row in walmart["products"]}

    assert walmart["distinct_products"] == 3
    assert walmart["distribution_store_count"] == 3
    assert walmart["service_area_presence_count"] == 0
    assert all(product["distribution_store_count"] == 1 for product in products.values())
    assert all("availability_status" not in product for product in products.values())


def test_assortment_does_not_invent_store_or_service_area_without_location_identity() -> None:
    accumulator = AssortmentAccumulator()
    accumulator.add(_offer("unknown", "walmart_us", "unknown", None, None))

    result = accumulator.finalize(
        benchmark_retailer="walmart_us",
        competitors=[],
        profiles=[],
        matches=[],
    )
    walmart = result["retailers"][0]
    assert walmart["distinct_products"] == 0
    assert walmart["distribution_store_count"] == 0
    assert walmart["service_area_presence_count"] == 0
    assert walmart["products"] == []


def test_real_banana_classifier_keeps_positive_price_row_despite_out_of_stock_metadata() -> None:
    classifier = OfferClassifier(ProductPackLoader(REPOSITORY_ROOT).load("fresh_bananas"))
    base = replace(
        _offer(
            "banana-in-stock",
            "walmart_us",
            "banana-1",
            "72712",
            "1",
            collected_at="2026-08-07T12:00:00Z",
        ).offer,
        title="Fresh Banana, Each",
    )
    verified = classifier.classify(base)
    out_of_stock = classifier.classify(
        replace(
            base,
            offer_id="banana-out-of-stock",
            in_stock=False,
            collected_at="2026-08-07T12:05:00Z",
        )
    )
    assert verified.in_scope is True
    assert out_of_stock.in_scope is True
    assert out_of_stock.scope_reason is None

    accumulator = AssortmentAccumulator()
    accumulator.add(verified)
    accumulator.add(out_of_stock)
    result = accumulator.finalize(
        benchmark_retailer="walmart_us",
        competitors=[],
        profiles=[],
        matches=[],
    )
    walmart = result["retailers"][0]
    product = walmart["products"][0]

    assert walmart["distinct_products"] == 1
    assert walmart["distribution_store_count"] == 1
    assert product["distribution_store_count"] == 1
    assert product["service_area_presence_count"] == 0
    assert "availability_status" not in product


def test_newer_seller_policy_exclusion_retracts_assortment_availability() -> None:
    older = _offer(
        "older-first-party",
        "walmart_us",
        "seller-transition",
        "72712",
        "1",
        collected_at="2026-08-07T12:00:00Z",
    )
    later = replace(
        _offer(
            "later-third-party",
            "walmart_us",
            "seller-transition",
            "72712",
            "1",
            collected_at="2026-08-07T12:05:00Z",
        ),
        in_scope=False,
        scope_reason=("known third-party marketplace seller excluded by Retailer Pack policy"),
        attributes={
            "_seller_governance": {
                "status": "excluded_third_party",
                "eligible": False,
            }
        },
        metrics={},
    )
    accumulator = AssortmentAccumulator()
    accumulator.add(older)
    accumulator.add(later)

    result = accumulator.finalize(
        benchmark_retailer="walmart_us",
        competitors=[],
        profiles=[],
        matches=[],
    )
    walmart = result["retailers"][0]
    assert walmart["distinct_products"] == 0
    assert walmart["distribution_store_count"] == 0
    assert walmart["service_area_presence_count"] == 0
    assert walmart["products"] == []


def test_assortment_uses_certified_relationship_without_price_overlap() -> None:
    accumulator = AssortmentAccumulator()
    accumulator.add(_offer("w1", "walmart_us", "w1", "72712", "1"))
    accumulator.add(_offer("s1", "sams_club_us", "s1", "10001", "A"))

    result = accumulator.finalize(
        benchmark_retailer="walmart_us",
        competitors=["sams_club_us"],
        profiles=[
            {
                "id": "compatible",
                "label": "Compatible specification",
                "geography": "exact_zip",
            }
        ],
        matches=[],
        relationships=[
            {
                "competitor_id": "sams_club_us",
                "benchmark_product_id": "w1",
                "competitor_product_id": "s1",
                "status": "confirmed",
                "eligible_profile_ids": ["compatible"],
            }
        ],
    )

    comparison = result["comparisons"][0]
    assert comparison["product_relationships"] == 1
    assert comparison["matched_benchmark_products"] == 1
    assert comparison["matched_competitor_products"] == 1
    assert comparison["benchmark_only_products"] == 0
    assert comparison["competitor_whitespace_products"] == 0
    assert comparison["profiles"][0]["relationships"] == 1


def test_assortment_relationship_absent_from_verified_assortment_cannot_reduce_whitespace() -> None:
    accumulator = AssortmentAccumulator()
    accumulator.add(_offer("w1", "walmart_us", "w1", "72712", "1"))
    accumulator.add(_offer("a1", "aldi_us", "a1", "72712", "A"))

    result = accumulator.finalize(
        benchmark_retailer="walmart_us",
        competitors=["aldi_us"],
        profiles=[{"id": "compatible", "label": "Compatible", "geography": "exact_zip"}],
        matches=[],
        relationships=[
            {
                "competitor_id": "aldi_us",
                "benchmark_product_id": "w-missing",
                "competitor_product_id": "a1",
                "status": "confirmed",
                "eligible_profile_ids": ["compatible"],
            }
        ],
    )

    comparison = result["comparisons"][0]
    assert comparison["product_relationships"] == 0
    assert comparison["matched_benchmark_products"] == 0
    assert comparison["matched_competitor_products"] == 0
    assert comparison["benchmark_only_products"] == 1
    assert comparison["competitor_whitespace_products"] == 1
    assert comparison["benchmark_match_coverage"] == 0.0
    assert comparison["competitor_match_coverage"] == 0.0


def test_legacy_out_of_stock_scope_reason_keeps_positive_price_assortment_relationship() -> None:
    accumulator = AssortmentAccumulator()
    walmart = _offer(
        "w1",
        "walmart_us",
        "w1",
        "72712",
        "1",
        collected_at="2026-08-07T12:00:00Z",
    )
    aldi_in_stock = _offer(
        "a1-in-stock",
        "aldi_us",
        "a1",
        "72712",
        "A",
        collected_at="2026-08-07T12:00:00Z",
    )
    aldi_out_of_stock = replace(
        _offer(
            "a1-out-of-stock",
            "aldi_us",
            "a1",
            "72712",
            "A",
            in_stock=False,
            collected_at="2026-08-07T12:05:00Z",
        ),
        in_scope=False,
        scope_reason="explicitly out of stock",
    )
    accumulator.add(walmart)
    accumulator.add(aldi_in_stock)
    accumulator.add(aldi_out_of_stock)

    result = accumulator.finalize(
        benchmark_retailer="walmart_us",
        competitors=["aldi_us"],
        profiles=[{"id": "strict", "label": "Exact package", "geography": "exact_zip"}],
        matches=[
            MatchRecord(
                profile_id="strict",
                competitor_id="aldi_us",
                geography_key="72712",
                benchmark_offer_id="w1",
                competitor_offer_id="a1-in-stock",
                attributes={},
                comparison_metric="package_price",
                benchmark_value=Decimal("4.99"),
                competitor_value=Decimal("4.99"),
                gap=Decimal("0"),
                winner="tie",
            )
        ],
        ambiguous_groups=[
            {
                "competitor_id": "aldi_us",
                "candidates": [
                    {
                        "benchmark_product_id": "w1",
                        "competitor_product_id": "a1",
                    }
                ],
            }
        ],
        relationships=[
            {
                "competitor_id": "aldi_us",
                "benchmark_product_id": "w1",
                "competitor_product_id": "a1",
                "status": "confirmed",
                "eligible_profile_ids": ["strict"],
            }
        ],
    )

    aldi = result["retailers"][1]
    comparison = result["comparisons"][0]
    assert aldi["search_distinct_products"] == 1
    assert aldi["distinct_products"] == 1
    assert aldi["distribution_store_count"] == 1
    assert aldi["service_area_presence_count"] == 0
    assert comparison["product_relationships"] == 1
    assert comparison["ambiguous_candidate_groups"] == 1
    assert comparison["matched_benchmark_products"] == 1
    assert comparison["matched_competitor_products"] == 1
    assert comparison["benchmark_only_products"] == 0
    assert comparison["competitor_whitespace_products"] == 0
    assert comparison["profiles"][0]["relationships"] == 1
    assert comparison["top_benchmark_only"] == []


def test_pdp_context_enriches_identity_without_changing_metrics() -> None:
    source = {
        "comparisons": [
            {
                "product_relationships": 3,
                "top_benchmark_only": [
                    {
                        "canonical_product_id": "walmart_us:w1",
                        "name": "Search name",
                        "brand": "Search brand",
                    }
                ],
                "top_competitor_whitespace": [],
            }
        ]
    }
    enriched = merge_assortment_product_context(
        source,
        [
            {
                "canonical_product_id": "walmart_us:w1",
                "name": "PDP name",
                "brand": "PDP brand",
                "seller": "Walmart.com",
                "image_url": "https://example.test/product.png",
                "description": "PDP description",
                "category_path": "Dairy > Milk",
                "identifiers": {"upc": "012345678905"},
                "specification": {"size": "1 gal"},
                "fulfillment": {"pickup_available": True},
                "reviews": {"rating": 4.6},
                "pdp_source_field_inventory": ["seller", "rating"],
                "price": 3.94,
                "price_currency": "USD",
            }
        ],
    )

    assert enriched["comparisons"][0]["product_relationships"] == 3
    assert enriched["comparisons"][0]["top_benchmark_only"][0]["name"] == "PDP name"
    product = enriched["comparisons"][0]["top_benchmark_only"][0]
    assert product["seller"] == "Walmart.com"
    assert product["brand"] == "PDP brand"
    assert product["observed_brand"] == "Search brand"
    assert product["description"] == "PDP description"
    assert product["identifiers"] == {"upc": "012345678905"}
    assert product["specification"] == {"size": "1 gal"}
    assert product["fulfillment"] == {"pickup_available": True}
    assert product["reviews"] == {"rating": 4.6}
    assert product["pdp_reference_price"] == 3.94
    assert "price" not in product
    assert source["comparisons"][0]["top_benchmark_only"][0]["name"] == "Search name"
