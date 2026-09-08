from __future__ import annotations

import csv
import json
import os
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path

import pytest

from rci_analytics.classification import OfferClassifier
from rci_analytics.matching import ComparisonInputReducer, product_footprint
from rci_analytics.normalization import CanonicalOfferNormalizer, RetailerIdentityMap
from rci_analytics.price_monitoring import PriceMonitoringFilters, PriceMonitoringProjector
from rci_analytics.product_pack import ProductPackLoader
from rci_retailer_packs import GovernedBrandResolver, GovernedSellerResolver

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
INPUT_ENV = {
    "walmart_us": "RCI_GOLDEN_MILK_WALMART_CSV",
    "aldi_us": "RCI_GOLDEN_MILK_ALDI_CSV",
    "amazon_us_same_day": "RCI_GOLDEN_MILK_AMAZON_CSV",
}
INPUTS = {retailer: os.getenv(name) for retailer, name in INPUT_ENV.items()}
DISPLAY_NAMES = {
    "walmart_us": "Walmart",
    "aldi_us": "ALDI",
    "amazon_us_same_day": "Amazon",
}

pytestmark = pytest.mark.skipif(
    not all(INPUTS.values()),
    reason="set all three RCI_GOLDEN_MILK_*_CSV paths for the full regression",
)


def test_full_milk_reported_store_distribution_equals_retained_positive_search_source() -> None:
    expected = json.loads(
        (REPOSITORY_ROOT / "fixtures/golden/milk/validated_summary.json").read_text()
    )
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_fluid_milk")
    assert pack.version == "1.6.0"
    normalizer = CanonicalOfferNormalizer(
        RetailerIdentityMap.from_catalog(REPOSITORY_ROOT / "config/retailer-catalog.json")
    )
    classifier = OfferClassifier(pack)
    reducer = ComparisonInputReducer(pack)
    raw_rows: Counter[str] = Counter()
    qualifying_rows: Counter[str] = Counter()
    qualifying_zips: dict[str, set[str]] = defaultdict(set)
    qualifying_stores: dict[str, set[str]] = defaultdict(set)
    qualifying_products: dict[str, set[str]] = defaultdict(set)
    product_distribution_stores: dict[tuple[str, str], set[str]] = defaultdict(set)
    walmart_locations: dict[str, tuple[str, str]] = {}
    with (REPOSITORY_ROOT / "fixtures/location_master/locations.csv").open(
        newline="", encoding="utf-8-sig"
    ) as handle:
        for row in csv.DictReader(handle):
            if row["Provider"] == "Walmart":
                walmart_locations[row["Store_No"]] = (row["State"], row["City"])
    audited_product_rows = 0
    audited_product_stores: set[str] = set()
    audited_product_zips: set[str] = set()
    audited_product_states: set[str] = set()
    audited_product_cities: set[str] = set()
    audited_product_offers = []

    for expected_retailer, input_path in INPUTS.items():
        assert input_path is not None
        with Path(input_path).open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                normalized = replace(normalizer.normalize(dict(row)), raw={})
                assert normalized.retailer_id == expected_retailer
                raw_rows[expected_retailer] += 1
                if (
                    expected_retailer == "walmart_us"
                    and normalized.retailer_product_id == "46942839"
                ):
                    audited_product_rows += 1
                    assert normalized.store_number is not None
                    assert normalized.zipcode is not None
                    audited_product_stores.add(normalized.store_number)
                    audited_product_zips.add(normalized.zipcode)
                    state, city = walmart_locations[normalized.store_number]
                    audited_product_states.add(state)
                    audited_product_cities.add(city)
                classified = classifier.classify(normalized)
                if (
                    expected_retailer == "walmart_us"
                    and normalized.retailer_product_id == "46942839"
                ):
                    audited_product_offers.append(classified)
                if classified.in_scope:
                    qualifying_rows[expected_retailer] += 1
                    if normalized.zipcode is not None:
                        qualifying_zips[expected_retailer].add(normalized.zipcode)
                    if normalized.store_number is not None:
                        qualifying_stores[expected_retailer].add(normalized.store_number)
                    qualifying_products[expected_retailer].add(normalized.retailer_product_id)
                if (
                    (classified.in_scope or classified.scope_reason == "explicitly out of stock")
                    and normalized.price is not None
                    and normalized.price > 0
                    and normalized.store_number is not None
                ):
                    product_distribution_stores[
                        (expected_retailer, normalized.retailer_product_id)
                    ].add(normalized.store_number)
                reducer.add(classified)

    assert sum(raw_rows.values()) == expected["source_rows_total"] == 348_980
    for retailer_id, display_name in DISPLAY_NAMES.items():
        scorecard = expected["retailer_stats"][display_name]
        assert raw_rows[retailer_id] == scorecard["raw_rows"]
        assert qualifying_rows[retailer_id] == scorecard["qual_rows"]
        assert len(qualifying_zips[retailer_id]) == scorecard["fresh_zips"]
        assert len(qualifying_stores[retailer_id]) == scorecard["fresh_stores"]
        assert len(qualifying_products[retailer_id]) == scorecard["fresh_products"]

    assert audited_product_rows == 83
    assert len(audited_product_stores) == 83
    assert len(audited_product_zips) == 78
    assert audited_product_states == {"CA"}
    assert len(audited_product_cities) == 59
    assert len(product_distribution_stores[("walmart_us", "46942839")]) == 83

    footprint = product_footprint(
        audited_product_offers,
        analysis_id="milk-46942839-source-audit",
        retailer_id="walmart_us",
        product_id="46942839",
    )
    assert footprint["store_count"] == 83
    assert len(footprint["locations"]) == 83
    assert {row["store_number"] for row in footprint["locations"]} == (audited_product_stores)
    assert footprint["distribution_contract"]["inventory_claim"] is False
    assert footprint["distribution_contract"]["stock_status_used"] is False

    monitoring = PriceMonitoringProjector(
        pack,
        GovernedBrandResolver.from_repository(REPOSITORY_ROOT),
        seller_resolver=GovernedSellerResolver.from_repository(REPOSITORY_ROOT),
    ).build(
        audited_product_offers,
        analysis_id="milk-46942839-source-audit",
        generated_at="2026-08-07T12:00:00Z",
        filters=PriceMonitoringFilters(
            retailer_id="walmart_us",
            product_id="46942839",
        ),
        source_rows=len(audited_product_offers),
        product_location_limit=None,
    )
    assert monitoring["summary"]["distribution_store_count"] == 83
    assert monitoring["summary"]["service_area_presence_count"] == 0
    assert monitoring["presence"]["distribution_store_count"] == 83
    assert monitoring["presence"]["service_area_presence_count"] == 0
    product = monitoring["products"][0]
    assert product["product_id"] == "46942839"
    assert product["distribution_store_count"] == 83
    assert product["service_area_presence_count"] == 0
    assert len(product["sample_locations"]) == 83

    def keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value) | {key for child in value.values() for key in keys(child)}
        if isinstance(value, list):
            return {key for child in value for key in keys(child)}
        return set()

    assert {
        "in_stock",
        "availability_status",
        "verified_local_availability",
        "verified_available_locations",
    }.isdisjoint(keys(monitoring))

    with (REPOSITORY_ROOT / "fixtures/golden/milk/product_catalog.csv").open(
        newline="", encoding="utf-8-sig"
    ) as handle:
        walmart_catalog = {
            str(row["Product ID"]): int(row["Covered Stores"])
            for row in csv.DictReader(handle)
            if row["Retailer"] == "Walmart" and row["Qualifying Fresh"] == "True"
        }
    assert walmart_catalog
    assert set(walmart_catalog) == {
        product_id
        for retailer_id, product_id in product_distribution_stores
        if retailer_id == "walmart_us"
    }
    for product_id, reported_store_count in walmart_catalog.items():
        assert reported_store_count == len(
            product_distribution_stores[("walmart_us", product_id)]
        ), product_id
    assert walmart_catalog["46942839"] == 83
