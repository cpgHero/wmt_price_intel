from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from rci_analytics.classification import OfferClassifier
from rci_analytics.matching import ComparisonEngine, geographic_overlap
from rci_analytics.normalization import CanonicalOfferNormalizer, RetailerIdentityMap
from rci_analytics.product_pack import ProductPackLoader

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def _pipeline():
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_strawberries")
    document = dict(pack.document)
    document.pop("retailer_overrides")
    pack = replace(pack, document=document)
    normalizer = CanonicalOfferNormalizer(
        RetailerIdentityMap.from_catalog(REPOSITORY_ROOT / "config" / "retailer-catalog.json")
    )
    return normalizer, OfferClassifier(pack), ComparisonEngine(pack)


def _row(
    retailer_id: str,
    product_id: str,
    title: str,
    price: str,
    *,
    zipcode: str = "10001",
    store: str = "store-1",
    latitude: float = 40.7500,
    longitude: float = -73.9900,
) -> dict[str, object]:
    return {
        "retailer_id": retailer_id,
        "retailer_product_id": product_id,
        "title": title,
        "price": price,
        "zipcode": zipcode,
        "store_number": store,
        "stock_availability": True,
        "latitude": latitude,
        "longitude": longitude,
    }


def _classified():
    normalizer, classifier, engine = _pipeline()
    rows = [
        _row("walmart_us", "w-1", "Fresh Strawberries, 1 lb", "2.38"),
        _row("walmart_us", "w-2", "Fresh Strawberries, 2 lb", "4.52"),
        _row("walmart_us", "w-o", "Fresh Organic Strawberries, 1 lb", "3.33"),
        _row("aldi_us", "a-1", "Fresh Strawberries, 1 lb", "2.55"),
        _row("aldi_us", "a-2", "Fresh Strawberries, 2 lb", "5.99"),
        _row("aldi_us", "a-o", "Fresh Organic Strawberries, 1 lb", "3.85"),
        _row("amazon_us_same_day", "m-1", "Strawberries, 1 lb", "1.99"),
        _row("amazon_us_same_day", "m-2", "Strawberries, 2 lb", "5.32"),
        _row("amazon_us_same_day", "m-o", "Organic Strawberries, 1 lb", "3.34"),
    ]
    offers = classifier.classify_many(normalizer.normalize_many(rows))
    return offers, engine


def test_strict_profile_never_crosses_package_weights() -> None:
    offers, engine = _classified()
    matches = engine.compare(
        offers,
        benchmark_id="walmart_us",
        competitor_id="amazon_us_same_day",
        profile_id="strict",
    )

    assert len(matches) == 3
    assert {(match.attributes["weight_oz"], match.winner) for match in matches} == {
        (16.0, "competitor_lower"),
        (16.0, "parity"),
        (32.0, "benchmark_lower"),
    }
    assert all(match.comparison_metric == "package_price" for match in matches)


def test_unit_price_profile_selects_lowest_positive_price_per_lb() -> None:
    offers, engine = _classified()
    aldi = engine.compare(
        offers,
        benchmark_id="walmart_us",
        competitor_id="aldi_us",
        profile_id="unit_price",
    )
    amazon = engine.compare(
        offers,
        benchmark_id="walmart_us",
        competitor_id="amazon_us_same_day",
        profile_id="unit_price",
    )

    aldi_by_organic = {match.attributes["organic"]: match for match in aldi}
    amazon_by_organic = {match.attributes["organic"]: match for match in amazon}
    assert aldi_by_organic[False].benchmark_value == Decimal("2.26")
    assert aldi_by_organic[False].competitor_value == Decimal("2.55")
    assert aldi_by_organic[False].gap == Decimal("0.29")
    assert amazon_by_organic[False].benchmark_value == Decimal("2.26")
    assert amazon_by_organic[False].competitor_value == Decimal("1.99")
    assert amazon_by_organic[False].gap == Decimal("-0.27")
    assert amazon_by_organic[True].winner == "parity"
    assert all(match.comparison_metric == "price_per_lb" for match in [*aldi, *amazon])


def test_geographic_overlap_and_optional_radius_validation() -> None:
    normalizer, classifier, engine = _pipeline()
    rows = [
        _row(
            "walmart_us",
            "w-near",
            "Fresh Strawberries, 1 lb",
            "2.38",
            store="w-near",
            latitude=41.881832,
            longitude=-87.623177,
        ),
        _row(
            "aldi_us",
            "a-near",
            "Fresh Strawberries, 1 lb",
            "2.55",
            store="a-near",
            latitude=41.889,
            longitude=-87.630,
        ),
        _row(
            "aldi_us",
            "a-far",
            "Fresh Strawberries, 1 lb",
            "2.55",
            zipcode="60660",
            store="a-far",
            latitude=42.2,
            longitude=-88.2,
        ),
    ]
    offers = classifier.classify_many(normalizer.normalize_many(rows))

    assert geographic_overlap(offers, "walmart_us", "aldi_us") == {"10001"}
    matches = engine.compare(
        offers,
        benchmark_id="walmart_us",
        competitor_id="aldi_us",
        profile_id="aldi_10mi",
    )
    assert len(matches) == 1
    assert matches[0].winner == "benchmark_lower"
    assert matches[0].distance_miles is not None
    assert matches[0].distance_miles < 10
