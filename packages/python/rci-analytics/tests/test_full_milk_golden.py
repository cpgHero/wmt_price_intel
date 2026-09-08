from __future__ import annotations

import csv
import json
import os
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path

import pytest

from rci_analytics.classification import OfferClassifier
from rci_analytics.matching import ComparisonEngine, ComparisonInputReducer
from rci_analytics.normalization import CanonicalOfferNormalizer, RetailerIdentityMap
from rci_analytics.product_location import classify_local_availability
from rci_analytics.product_pack import ProductPackLoader

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


def test_full_milk_search_golden_is_quarantined_from_local_comparisons() -> None:
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
    availability_statuses: dict[str, Counter[str]] = defaultdict(Counter)
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
    audited_product_statuses: Counter[str] = Counter()

    for expected_retailer, input_path in INPUTS.items():
        assert input_path is not None
        with Path(input_path).open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                normalized = replace(normalizer.normalize(dict(row)), raw={})
                assert normalized.retailer_id == expected_retailer
                raw_rows[expected_retailer] += 1
                availability_status = classify_local_availability(
                    in_stock=normalized.in_stock,
                    is_sponsored=normalized.is_sponsored,
                )
                availability_statuses[expected_retailer][availability_status] += 1
                if (
                    expected_retailer == "walmart_us"
                    and normalized.retailer_product_id == "46942839"
                ):
                    audited_product_rows += 1
                    audited_product_statuses[availability_status] += 1
                    assert normalized.store_number is not None
                    assert normalized.zipcode is not None
                    audited_product_stores.add(normalized.store_number)
                    audited_product_zips.add(normalized.zipcode)
                    state, city = walmart_locations[normalized.store_number]
                    audited_product_states.add(state)
                    audited_product_cities.add(city)
                classified = classifier.classify(normalized)
                if classified.in_scope:
                    qualifying_rows[expected_retailer] += 1
                    if normalized.zipcode is not None:
                        qualifying_zips[expected_retailer].add(normalized.zipcode)
                    if normalized.store_number is not None:
                        qualifying_stores[expected_retailer].add(normalized.store_number)
                    qualifying_products[expected_retailer].add(normalized.retailer_product_id)
                reducer.add(classified)

    assert sum(raw_rows.values()) == expected["source_rows_total"] == 348_980
    for retailer_id, display_name in DISPLAY_NAMES.items():
        scorecard = expected["retailer_stats"][display_name]
        assert raw_rows[retailer_id] == scorecard["raw_rows"]
        assert qualifying_rows[retailer_id] == scorecard["qual_rows"]
        assert len(qualifying_zips[retailer_id]) == scorecard["fresh_zips"]
        assert len(qualifying_stores[retailer_id]) == scorecard["fresh_stores"]
        assert len(qualifying_products[retailer_id]) == scorecard["fresh_products"]

    offers = reducer.offers()
    engine = ComparisonEngine(pack)
    assert availability_statuses == {
        "walmart_us": Counter({"unverified": 184_750, "unverified_sponsored": 56_029}),
        "aldi_us": Counter({"unverified": 41_321}),
        "amazon_us_same_day": Counter(
            {"verified_in_stock": 63_854, "explicitly_out_of_stock": 3_026}
        ),
    }
    assert audited_product_rows == 83
    assert len(audited_product_stores) == 83
    assert len(audited_product_zips) == 78
    assert audited_product_states == {"CA"}
    assert len(audited_product_cities) == 59
    assert audited_product_statuses == Counter({"unverified": 83})
    # These immutable historical Search exports remain valid discovery and
    # price evidence, but Walmart and ALDI contain no explicit stock signal.
    # They must therefore produce no local comparisons instead of recreating
    # the legacy Search-placement footprint as store carriage.
    profile_by_mode = {
        "same_brand": "same_brand_exact",
        "private_label": "private_label",
        "equivalent": "all_brand",
    }
    for competitor_id, display_name in (
        ("aldi_us", "ALDI"),
        ("amazon_us_same_day", "Amazon"),
    ):
        for mode, profile_id in profile_by_mode.items():
            matches = engine.compare(
                offers,
                benchmark_id="walmart_us",
                competitor_id=competitor_id,
                profile_id=profile_id,
            )
            assert matches == [], (
                f"legacy {display_name} {mode} Search rows must remain quarantined "
                "from verified-local comparisons"
            )
