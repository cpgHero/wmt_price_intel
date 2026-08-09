from __future__ import annotations

from pathlib import Path

from rci_analytics import (
    ComparisonInsightInput,
    DeterministicInsightEngine,
    ProductPackLoader,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def _input(
    *,
    competitor: str,
    profile: str,
    segment: str,
    matches: float,
    geographies: float,
    benchmark_rate: float,
    competitor_rate: float,
) -> ComparisonInsightInput:
    fields = {
        "matches": matches,
        "unique_geographies": geographies,
        "benchmark_lower_rate": benchmark_rate,
        "competitor_lower_rate": competitor_rate,
    }
    return ComparisonInsightInput(
        benchmark_id="walmart_us",
        competitor_id=competitor,
        profile_id=profile,
        profile_label=profile.replace("_", " "),
        segment_id=segment,
        segment_label="All comparable items" if segment == "all" else segment.replace("_", " "),
        values=fields,
        metric_refs={name: f"metric.{competitor}.{profile}.{segment}.{name}" for name in fields},
        evidence_refs=(f"evidence.{competitor}.{profile}",),
    )


def test_product_pack_rules_rank_breadth_magnitude_confidence_and_actionability() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_strawberries")
    engine = DeterministicInsightEngine(pack)

    ranked = engine.rank(
        [
            _input(
                competitor="amazon_us_same_day",
                profile="strict",
                segment="conventional_1lb",
                matches=630,
                geographies=500,
                benchmark_rate=0.3,
                competitor_rate=0.7,
            ),
            _input(
                competitor="aldi_us",
                profile="strict",
                segment="all",
                matches=200,
                geographies=200,
                benchmark_rate=0.8,
                competitor_rate=0.2,
            ),
        ]
    )

    assert [candidate.insight["severity"] for candidate in ranked] == ["high", "positive"]
    assert ranked[0].score > ranked[1].score
    assert ranked[0].breadth == 1
    assert ranked[0].magnitude == 0.4
    assert ranked[0].confidence == 1
    assert ranked[0].recommendation is not None
    assert ranked[0].recommendation["priority"] == 1
    assert ranked[0].insight["generated_by"] == "deterministic"
    assert ranked[0].insight["metric_refs"]
    assert ranked[0].insight["evidence_refs"]


def test_insight_ranking_is_stable_and_omits_weak_or_unsupported_signals() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_ground_beef")
    engine = DeterministicInsightEngine(pack)
    too_small = _input(
        competitor="aldi_us",
        profile="strict_exact_package",
        segment="organic_85_15",
        matches=10,
        geographies=10,
        benchmark_rate=0.1,
        competitor_rate=0.9,
    )
    no_trigger = _input(
        competitor="amazon_us_same_day",
        profile="strict_exact_package",
        segment="all",
        matches=1000,
        geographies=900,
        benchmark_rate=0.6,
        competitor_rate=0.4,
    )

    assert engine.rank([too_small, no_trigger]) == []
