from __future__ import annotations

import csv
import json
import os
import statistics
from collections import Counter, defaultdict
from dataclasses import replace
from decimal import Decimal
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
    "walmart_us": "RCI_GOLDEN_GROUND_BEEF_WALMART_CSV",
    "aldi_us": "RCI_GOLDEN_GROUND_BEEF_ALDI_CSV",
    "amazon_us_same_day": "RCI_GOLDEN_GROUND_BEEF_AMAZON_CSV",
}
INPUTS = {retailer: os.getenv(name) for retailer, name in INPUT_ENV.items()}
DISPLAY_NAMES = {
    "walmart_us": "Walmart",
    "aldi_us": "ALDI",
    "amazon_us_same_day": "Amazon",
}

pytestmark = pytest.mark.skipif(
    not all(INPUTS.values()),
    reason="set all three RCI_GOLDEN_GROUND_BEEF_*_CSV paths for the full regression",
)


def _summary(engine: ComparisonEngine, matches: list[MatchRecord]) -> dict[str, Any]:
    summary = engine.summarize(matches)
    return {
        "matches": summary.matches,
        "walmart_lower": summary.benchmark_lower,
        "competitor_lower": summary.competitor_lower,
        "parity": summary.parity,
        "walmart_lower_rate": summary.benchmark_lower_rate,
        "competitor_lower_rate": summary.competitor_lower_rate,
        "parity_rate": summary.parity_rate,
        "median_walmart_price": float(
            statistics.median(match.benchmark_value for match in matches)
        ),
        "median_competitor_price": float(
            statistics.median(match.competitor_value for match in matches)
        ),
    }


def _segment(
    matches: list[MatchRecord],
    *,
    lean_pct: int,
    fat_pct: int,
    weight_lb: float,
    organic: bool,
    grass_fed: bool,
    premium_tier: str = "standard",
) -> list[MatchRecord]:
    expected = {
        "lean_pct": lean_pct,
        "fat_pct": fat_pct,
        "weight_lb": weight_lb,
        "organic": organic,
        "grass_fed": grass_fed,
        "premium_tier": premium_tier,
    }
    return [
        match
        for match in matches
        if all(match.attributes.get(name) == value for name, value in expected.items())
    ]


def test_full_ground_beef_golden_regression() -> None:
    expected = json.loads(
        (REPOSITORY_ROOT / "fixtures/golden/ground_beef/validated_summary.json").read_text()
    )
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_ground_beef")
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
    variable_weight_observations: set[tuple[Decimal, Decimal]] = set()

    for expected_retailer, input_path in INPUTS.items():
        assert input_path is not None
        with Path(input_path).open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                raw_rows[expected_retailer] += 1
                normalized = replace(normalizer.normalize(dict(row)), raw={})
                assert normalized.retailer_id == expected_retailer
                classified = classifier.classify(normalized)
                if classified.in_scope:
                    qualifying_rows[expected_retailer] += 1
                    if normalized.zipcode is not None:
                        qualifying_zips[expected_retailer].add(normalized.zipcode)
                    if normalized.store_number is not None:
                        qualifying_stores[expected_retailer].add(normalized.store_number)
                    qualifying_products[expected_retailer].add(normalized.retailer_product_id)
                    if (
                        expected_retailer == "aldi_us"
                        and normalized.retailer_product_id == "17771077"
                        and normalized.price is not None
                        and classified.metrics["price_per_lb"] is not None
                    ):
                        variable_weight_observations.add(
                            (normalized.price, classified.metrics["price_per_lb"])
                        )
                reducer.add(classified)

    assert sum(raw_rows.values()) == expected["source_rows_total"] == 225_791
    for retailer_id, display_name in DISPLAY_NAMES.items():
        scorecard = expected["retailer_scorecard"][display_name]
        assert raw_rows[retailer_id] == scorecard["raw_rows"]
        assert qualifying_rows[retailer_id] == scorecard["qualifying_rows"]
        assert len(qualifying_zips[retailer_id]) == scorecard["qualifying_zips"]
        assert len(qualifying_stores[retailer_id]) == scorecard["qualifying_stores"]
        assert len(qualifying_products[retailer_id]) == scorecard["qualifying_products"]

    assert (Decimal("13.9300"), Decimal("13.9300") / Decimal("2.25")) in (
        variable_weight_observations
    )

    offers = reducer.offers()
    engine = ComparisonEngine(pack)
    exact_by_competitor: dict[str, list[MatchRecord]] = {}
    for competitor_id, display_name in (
        ("aldi_us", "ALDI"),
        ("amazon_us_same_day", "Amazon"),
    ):
        matches = engine.compare(
            offers,
            benchmark_id="walmart_us",
            competitor_id=competitor_id,
            profile_id="strict",
        )
        exact_by_competitor[display_name] = matches
        actual = _summary(engine, matches)
        for field, expected_value in expected["exact_summary"][display_name].items():
            assert actual[field] == pytest.approx(expected_value, abs=1e-12)

    segment_specs = {
        "ALDI_73_27_5lb": (73, 27, 5.0, False, False),
        "ALDI_80_20_2_25lb": (80, 20, 2.25, False, False),
        "ALDI_organic_85_15_1lb": (85, 15, 1.0, True, True),
    }
    for segment_id, values in segment_specs.items():
        segment = _segment(
            exact_by_competitor["ALDI"],
            lean_pct=values[0],
            fat_pct=values[1],
            weight_lb=values[2],
            organic=values[3],
            grass_fed=values[4],
        )
        actual = _summary(engine, segment)
        segment_expected = expected["selected_segments"][segment_id]
        for field in (
            "matches",
            "walmart_lower_rate",
            "competitor_lower_rate",
            "median_walmart_price",
            "median_competitor_price",
        ):
            if field in segment_expected:
                assert actual[field] == pytest.approx(segment_expected[field], abs=1e-12)
        median_gap_per_lb = float(
            statistics.median(match.gap / Decimal(str(values[2])) for match in segment)
        )
        assert median_gap_per_lb == pytest.approx(segment_expected["median_gap_per_lb"], abs=1e-12)

    proximity = engine.compare(
        offers,
        benchmark_id="walmart_us",
        competitor_id="aldi_us",
        profile_id="aldi_10mi",
    )
    assert len(proximity) == expected["proximity_summary"]["ALDI_10mi_matches"]

    unit_price = engine.compare(
        offers,
        benchmark_id="walmart_us",
        competitor_id="aldi_us",
        profile_id="unit_price",
    )
    variable_segment = [
        match
        for match in unit_price
        if match.attributes.get("lean_pct") == 80
        and match.attributes.get("fat_pct") == 20
        and match.attributes.get("organic") is False
        and match.attributes.get("grass_fed") is False
        and match.attributes.get("premium_tier") == "standard"
    ]
    assert len(variable_segment) == 1_482
    assert float(statistics.median(x.competitor_value for x in variable_segment)) == pytest.approx(
        13.93 / 2.25,
        abs=1e-12,
    )
