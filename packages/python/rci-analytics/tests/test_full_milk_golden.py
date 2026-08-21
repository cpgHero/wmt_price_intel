from __future__ import annotations

import csv
import json
import os
import statistics
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from rci_analytics.classification import OfferClassifier
from rci_analytics.matching import ComparisonEngine, ComparisonInputReducer
from rci_analytics.models import MatchRecord
from rci_analytics.normalization import CanonicalOfferNormalizer, RetailerIdentityMap
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


def _summary(engine: ComparisonEngine, matches: list[MatchRecord]) -> dict[str, Any]:
    if not matches:
        return {
            "matches": 0,
            "unique_zips": 0,
            "walmart_lower": 0,
            "competitor_lower": 0,
            "parity": 0,
            "walmart_lower_rate": None,
            "competitor_lower_rate": None,
            "parity_rate": None,
            "median_gap_per_gallon": None,
            "mean_gap_per_gallon": None,
        }
    summary = engine.summarize(matches)
    return {
        "matches": summary.matches,
        "unique_zips": summary.unique_geographies,
        "walmart_lower": summary.benchmark_lower,
        "competitor_lower": summary.competitor_lower,
        "parity": summary.parity,
        "walmart_lower_rate": summary.benchmark_lower_rate,
        "competitor_lower_rate": summary.competitor_lower_rate,
        "parity_rate": summary.parity_rate,
        "median_gap_per_gallon": summary.median_gap,
        "mean_gap_per_gallon": float(statistics.mean(match.gap for match in matches)),
    }


def test_full_milk_golden_regression() -> None:
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

    for expected_retailer, input_path in INPUTS.items():
        assert input_path is not None
        with Path(input_path).open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                normalized = replace(normalizer.normalize(dict(row)), raw={})
                assert normalized.retailer_id == expected_retailer
                raw_rows[expected_retailer] += 1
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
            actual = _summary(engine, matches)
            comparison = expected["comparisons"][f"{display_name}_{mode}"]
            for field, expected_value in comparison.items():
                if field in {"competitor", "comparison_mode"}:
                    continue
                if expected_value is None:
                    assert actual[field] is None
                elif isinstance(expected_value, float):
                    assert actual[field] == pytest.approx(expected_value, abs=1e-12)
                else:
                    assert actual[field] == expected_value
