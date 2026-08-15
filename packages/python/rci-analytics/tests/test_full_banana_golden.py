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


def _expected_comparisons() -> dict[tuple[str, str], dict[str, str]]:
    path = REPOSITORY_ROOT / "fixtures/golden/bananas/comparison_summary.csv"
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return {(row["competitor"], row["comparison"]): row for row in csv.DictReader(handle)}


def _summary(engine: ComparisonEngine, matches: list[MatchRecord]) -> dict[str, Any]:
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
        "median_gap": summary.median_gap,
        "mean_gap": float(statistics.mean(match.gap for match in matches)),
    }


def _segment(matches: list[MatchRecord], *, variety: str, organic: bool) -> list[MatchRecord]:
    return [
        match
        for match in matches
        if match.attributes.get("variety") == variety and match.attributes.get("organic") is organic
    ]


def _assert_comparison(
    engine: ComparisonEngine,
    matches: list[MatchRecord],
    expected: dict[str, str],
) -> None:
    actual = _summary(engine, matches)
    integer_fields = {
        "matches": "matches",
        "unique_zips": "unique_zips",
        "walmart_lower": "walmart_lower",
        "competitor_lower": "competitor_lower",
        "parity": "parity",
    }
    for actual_name, expected_name in integer_fields.items():
        assert actual[actual_name] == int(expected[expected_name])
    for field in (
        "walmart_lower_rate",
        "competitor_lower_rate",
        "parity_rate",
        "median_gap",
        "mean_gap",
    ):
        assert actual[field] == pytest.approx(float(expected[field]), abs=1e-12)


def test_full_banana_golden_regression() -> None:
    expected = json.loads(
        (REPOSITORY_ROOT / "fixtures/golden/bananas/validated_summary.json").read_text()
    )
    comparisons = _expected_comparisons()
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
    strict_aldi = engine.compare(
        offers,
        benchmark_id="walmart_us",
        competitor_id="aldi_us",
        profile_id="strict_each",
    )
    _assert_comparison(
        engine,
        _segment(strict_aldi, variety="Standard Yellow", organic=False),
        comparisons[("ALDI", "Standard yellow banana — each price")],
    )
    _assert_comparison(
        engine,
        _segment(strict_aldi, variety="Plantain", organic=False),
        comparisons[("ALDI", "Plantain — each price")],
    )
    strict_amazon = engine.compare(
        offers,
        benchmark_id="walmart_us",
        competitor_id="amazon_us_same_day",
        profile_id="strict_each",
    )
    _assert_comparison(
        engine,
        _segment(strict_amazon, variety="Standard Yellow", organic=False),
        comparisons[("Amazon", "Standard yellow banana — each price")],
    )
    _assert_comparison(
        engine,
        _segment(strict_amazon, variety="Plantain", organic=False),
        comparisons[("Amazon", "Plantain — each price")],
    )

    weight_aldi = engine.compare(
        offers,
        benchmark_id="walmart_us",
        competitor_id="aldi_us",
        profile_id="weight_normalized",
    )
    _assert_comparison(
        engine,
        _segment(weight_aldi, variety="Standard Yellow", organic=False),
        comparisons[("ALDI", "Standard yellow banana — normalized weight price")],
    )
    _assert_comparison(
        engine,
        _segment(weight_aldi, variety="Standard Yellow", organic=True),
        comparisons[("ALDI", "Organic yellow banana — normalized weight price")],
    )
    weight_amazon = engine.compare(
        offers,
        benchmark_id="walmart_us",
        competitor_id="amazon_us_same_day",
        profile_id="weight_normalized",
    )
    _assert_comparison(
        engine,
        _segment(weight_amazon, variety="Standard Yellow", organic=True),
        comparisons[("Amazon", "Organic yellow banana — normalized weight price")],
    )

    range_matches = engine.compare(
        offers,
        benchmark_id="walmart_us",
        competitor_id="amazon_us_same_day",
        profile_id="conventional_bunch_range",
    )
    _assert_comparison(
        engine,
        range_matches,
        comparisons[("Amazon", "Standard yellow banana — Amazon 4-5 count bunch vs Walmart each")],
    )
    for match in range_matches:
        assert match.competitor_interval_low is not None
        assert match.competitor_interval_high is not None
        assert (
            match.competitor_interval_low <= match.benchmark_value <= match.competitor_interval_high
        )

    for profile_id, comparison_name in (
        ("organic_bunch_package", "Organic banana bunch — package price"),
        (
            "organic_bunch_midpoint",
            "Organic banana bunch — estimated midpoint price per banana",
        ),
    ):
        matches = engine.compare(
            offers,
            benchmark_id="walmart_us",
            competitor_id="amazon_us_same_day",
            profile_id=profile_id,
        )
        _assert_comparison(engine, matches, comparisons[("Amazon", comparison_name)])
