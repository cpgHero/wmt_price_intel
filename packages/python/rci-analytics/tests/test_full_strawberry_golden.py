from __future__ import annotations

import csv
import json
import os
import statistics
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from rci_analytics.classification import OfferClassifier
from rci_analytics.matching import ComparisonEngine
from rci_analytics.models import MatchRecord
from rci_analytics.normalization import CanonicalOfferNormalizer, RetailerIdentityMap
from rci_analytics.product_pack import ProductPackLoader

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
INPUT_ENV = {
    "walmart_us": "RCI_GOLDEN_STRAWBERRIES_WALMART_CSV",
    "aldi_us": "RCI_GOLDEN_STRAWBERRIES_ALDI_CSV",
    "amazon_us_same_day": "RCI_GOLDEN_STRAWBERRIES_AMAZON_CSV",
}
INPUTS = {retailer: os.getenv(name) for retailer, name in INPUT_ENV.items()}

pytestmark = pytest.mark.skipif(
    not all(INPUTS.values()),
    reason="set all three RCI_GOLDEN_STRAWBERRIES_*_CSV paths for the full regression",
)


def _expected_row(
    document: dict[str, Any],
    section: str,
    **where: str,
) -> dict[str, Any]:
    return next(
        row
        for row in document[section]
        if all(row.get(key) == value for key, value in where.items())
    )


def _summary(engine: ComparisonEngine, matches: list[MatchRecord]) -> dict[str, Any]:
    summary = engine.summarize(matches)
    distances = [match.distance_miles for match in matches if match.distance_miles is not None]
    return {
        "matches": summary.matches,
        "unique_geographies": summary.unique_geographies,
        "benchmark_lower": summary.benchmark_lower,
        "competitor_lower": summary.competitor_lower,
        "parity": summary.parity,
        "benchmark_lower_rate": summary.benchmark_lower_rate,
        "competitor_lower_rate": summary.competitor_lower_rate,
        "parity_rate": summary.parity_rate,
        "median_gap": summary.median_gap,
        "median_benchmark": float(statistics.median(match.benchmark_value for match in matches)),
        "median_competitor": float(statistics.median(match.competitor_value for match in matches)),
        "median_distance": statistics.median(distances) if distances else None,
    }


def _segment(
    matches: list[MatchRecord], *, weight_oz: float | None, organic: bool
) -> list[MatchRecord]:
    return [
        match
        for match in matches
        if match.attributes.get("organic") is organic
        and (weight_oz is None or match.attributes.get("weight_oz") == weight_oz)
    ]


def _assert_counts(actual: dict[str, Any], expected: dict[str, Any]) -> None:
    mappings = {
        "matches": "matches",
        "benchmark_lower": "walmart_lower",
        "competitor_lower": ("aldi_lower" if "aldi_lower" in expected else "competitor_lower"),
        "parity": "parity",
    }
    for actual_name, expected_name in mappings.items():
        assert actual[actual_name] == expected[expected_name]
    for actual_name, expected_name in (
        ("benchmark_lower_rate", "walmart_lower_rate"),
        (
            "competitor_lower_rate",
            "aldi_lower_rate" if "aldi_lower_rate" in expected else "competitor_lower_rate",
        ),
        ("parity_rate", "parity_rate"),
    ):
        assert actual[actual_name] == pytest.approx(expected[expected_name], abs=1e-12)


def test_full_strawberry_golden_regression() -> None:
    expected = json.loads(
        (REPOSITORY_ROOT / "fixtures/golden/strawberries/validated_summary.json").read_text()
    )
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_strawberries")
    normalizer = CanonicalOfferNormalizer(
        RetailerIdentityMap.from_catalog(REPOSITORY_ROOT / "config/retailer-catalog.json")
    )
    classifier = OfferClassifier(pack)
    engine = ComparisonEngine(pack)
    source_rows = 0
    seen_offer_ids: set[str] = set()
    in_scope_rows: Counter[str] = Counter()
    offers = []
    for input_path in INPUTS.values():
        assert input_path is not None
        with Path(input_path).open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                source_rows += 1
                offer = replace(normalizer.normalize(dict(row)), raw={})
                if offer.offer_id in seen_offer_ids:
                    continue
                seen_offer_ids.add(offer.offer_id)
                classified = classifier.classify(offer)
                if classified.in_scope:
                    in_scope_rows[offer.retailer_id] += 1
                    offers.append(classified)

    assert source_rows == expected["total_source_rows"] == 297_443
    expected_fresh_rows = {
        "walmart_us": 14_951,
        "aldi_us": 5_767,
        "amazon_us_same_day": 2_527,
    }
    assert in_scope_rows == expected_fresh_rows

    competitor_names = {"aldi_us": "ALDI", "amazon_us_same_day": "Amazon"}
    segment_specs = {
        "Conventional whole strawberries — 1 lb": (16.0, False),
        "Organic whole strawberries — 1 lb": (16.0, True),
        "Conventional whole strawberries — 2 lb": (32.0, False),
    }
    for competitor_id, competitor_name in competitor_names.items():
        strict = engine.compare(
            offers,
            benchmark_id="walmart_us",
            competitor_id=competitor_id,
            profile_id="strict",
        )
        aggregate = _summary(engine, strict)
        _assert_counts(
            aggregate,
            _expected_row(
                expected,
                "strict_summary",
                competitor=competitor_name,
                segment="All strict same-weight segments",
            ),
        )
        for label, (weight, organic) in segment_specs.items():
            _assert_counts(
                _summary(engine, _segment(strict, weight_oz=weight, organic=organic)),
                _expected_row(
                    expected,
                    "strict_summary",
                    competitor=competitor_name,
                    segment=label,
                ),
            )

        unit_price = engine.compare(
            offers,
            benchmark_id="walmart_us",
            competitor_id=competitor_id,
            profile_id="unit_price",
        )
        for organic, label in (
            (False, "Conventional whole strawberries — best available $/lb"),
            (True, "Organic whole strawberries — best available $/lb"),
        ):
            _assert_counts(
                _summary(engine, _segment(unit_price, weight_oz=None, organic=organic)),
                _expected_row(
                    expected,
                    "unit_price_summary",
                    competitor=competitor_name,
                    segment=label,
                ),
            )

    proximity = engine.compare(
        offers,
        benchmark_id="walmart_us",
        competitor_id="aldi_us",
        profile_id="aldi_10mi",
    )
    _assert_counts(
        _summary(engine, proximity),
        _expected_row(
            expected,
            "aldi_proximity_summary",
            segment="All validated ALDI store-segment matches within 10 miles",
        ),
    )
    for label, (weight, organic) in segment_specs.items():
        _assert_counts(
            _summary(engine, _segment(proximity, weight_oz=weight, organic=organic)),
            _expected_row(expected, "aldi_proximity_summary", segment=label),
        )
