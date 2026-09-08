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
    "walmart_us": "RCI_GOLDEN_BANANAS_WALMART_CSV",
    "aldi_us": "RCI_GOLDEN_BANANAS_ALDI_CSV",
    "amazon_us_same_day": "RCI_GOLDEN_BANANAS_AMAZON_CSV",
}
INPUTS = {retailer: os.getenv(name) for retailer, name in INPUT_ENV.items()}
DISPLAY_NAMES = {
    "walmart_us": "Walmart",
    "aldi_us": "ALDI",
    "amazon_us_same_day": "Amazon",
}

pytestmark = pytest.mark.skipif(
    not all(INPUTS.values()),
    reason="set all three RCI_GOLDEN_BANANAS_*_CSV paths for the full regression",
)


def test_full_banana_search_golden_is_quarantined_from_local_comparisons() -> None:
    expected = json.loads(
        (REPOSITORY_ROOT / "fixtures/golden/bananas/validated_summary.json").read_text()
    )
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_bananas")
    assert pack.version == "1.2.0"
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

    for expected_retailer, input_path in INPUTS.items():
        assert input_path is not None
        with Path(input_path).open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                normalized = replace(normalizer.normalize(dict(row)), raw={})
                assert normalized.retailer_id == expected_retailer
                raw_rows[expected_retailer] += 1
                availability_statuses[expected_retailer][
                    classify_local_availability(
                        in_stock=normalized.in_stock,
                        is_sponsored=normalized.is_sponsored,
                    )
                ] += 1
                classified = classifier.classify(normalized)
                if classified.in_scope:
                    qualifying_rows[expected_retailer] += 1
                    if normalized.zipcode is not None:
                        qualifying_zips[expected_retailer].add(normalized.zipcode)
                    if normalized.store_number is not None:
                        qualifying_stores[expected_retailer].add(normalized.store_number)
                    qualifying_products[expected_retailer].add(normalized.retailer_product_id)
                reducer.add(classified)

    assert sum(raw_rows.values()) == expected["raw_rows"]["total"] == 168_440
    scorecards = {row["retailer"]: row for row in expected["scorecard"]}
    for retailer_id, display_name in DISPLAY_NAMES.items():
        scorecard = scorecards[display_name]
        assert raw_rows[retailer_id] == scorecard["raw_rows"]
        assert qualifying_rows[retailer_id] == scorecard["fresh_rows"]
        assert len(qualifying_zips[retailer_id]) == scorecard["fresh_zips"]
        assert len(qualifying_stores[retailer_id]) == scorecard["fresh_stores"]
        assert len(qualifying_products[retailer_id]) == scorecard["fresh_products"]

    offers = reducer.offers()
    engine = ComparisonEngine(pack)
    assert availability_statuses == {
        "walmart_us": Counter({"unverified": 96_994}),
        "aldi_us": Counter({"unverified": 4_429}),
        "amazon_us_same_day": Counter(
            {"verified_in_stock": 66_823, "explicitly_out_of_stock": 194}
        ),
    }
    # Walmart and ALDI have Search-listed prices but no explicit stock signal
    # in these historical files. Every local profile must fail closed.
    for competitor_id in ("aldi_us", "amazon_us_same_day"):
        for profile_id in (
            "strict_each",
            "weight_normalized",
            "conventional_bunch_range",
            "organic_bunch_package",
            "organic_bunch_midpoint",
        ):
            assert (
                engine.compare(
                    offers,
                    benchmark_id="walmart_us",
                    competitor_id=competitor_id,
                    profile_id=profile_id,
                )
                == []
            )
