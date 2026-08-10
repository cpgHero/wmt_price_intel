from __future__ import annotations

from decimal import Decimal

from rci_analytics import AssortmentAccumulator, merge_assortment_product_context
from rci_analytics.models import ClassifiedOffer, MatchRecord, NormalizedOffer


def _offer(
    offer_id: str,
    retailer: str,
    product_id: str,
    zipcode: str,
    store: str,
) -> ClassifiedOffer:
    return ClassifiedOffer(
        offer=NormalizedOffer(
            offer_id=offer_id,
            retailer_id=retailer,
            retailer_product_id=product_id,
            title=f"Product {product_id}",
            brand=None,
            price=Decimal("4.99"),
            currency="USD",
            zipcode=zipcode,
            store_number=store,
            latitude=None,
            longitude=None,
            in_stock=True,
            product_url=None,
            image_url=None,
            collected_at=None,
            raw={},
        ),
        in_scope=True,
        scope_reason=None,
        attributes={},
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
    assert comparison["product_relationships"] == 1
    assert comparison["benchmark_only_products"] == 1
    assert comparison["competitor_whitespace_products"] == 1
    assert comparison["benchmark_match_coverage"] == 0.5
    assert comparison["top_benchmark_only"][0]["product_id"] == "w2"


def test_pdp_context_enriches_identity_without_changing_metrics() -> None:
    source = {
        "comparisons": [
            {
                "product_relationships": 3,
                "top_benchmark_only": [
                    {
                        "canonical_product_id": "walmart_us:w1",
                        "name": "Search name",
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
                "image_url": "https://example.test/product.png",
            }
        ],
    )

    assert enriched["comparisons"][0]["product_relationships"] == 3
    assert enriched["comparisons"][0]["top_benchmark_only"][0]["name"] == "PDP name"
    assert source["comparisons"][0]["top_benchmark_only"][0]["name"] == "Search name"
