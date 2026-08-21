from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from rci_api.competitive_release_audit import (
    audit_competitive_portfolio_set,
    require_competitive_portfolio_set,
)


def _summary(*, benchmark: int, scored: int) -> dict[str, Any]:
    leader = scored
    unscored = benchmark - scored
    return {
        "benchmark_product_locations": benchmark,
        "scored_product_locations": scored,
        "coverage_rate": round(scored / benchmark, 4) if benchmark else None,
        "leader_product_locations": leader,
        "tied_product_locations": 0,
        "at_risk_product_locations": 0,
        "losing_product_locations": 0,
        "unscored_product_locations": unscored,
        "leader_rate": 1.0 if scored else None,
        "benchmark_lower_rate": 1.0 if scored else None,
        "competitor_lower_rate": 0.0 if scored else None,
        "parity_rate": 0.0 if scored else None,
        "average_gap": 0.25 if scored else None,
    }


def _document(profile: str, radius: int, scored: int) -> dict[str, Any]:
    scorecard_summary = _summary(benchmark=2, scored=scored)
    relationship_summary = _summary(benchmark=scored, scored=scored)
    product = {
        "product_id": "w1",
        "product_name": "Walmart eggs",
        "image_url": None,
        "relationships": 1,
        **scorecard_summary,
    }
    relationship = {
        "relationship_id": "relationship-1",
        "competitor_id": "aldi_us",
        "competitor_name": "ALDI",
        "benchmark_product_id": "w1",
        "benchmark_product_name": "Walmart eggs",
        "benchmark_image_url": None,
        "competitor_product_id": "a1",
        "competitor_product_name": "ALDI eggs",
        "competitor_brand": "Goldhen",
        "competitor_brand_type": "private_label",
        "competitor_image_url": None,
        "profile_id": profile,
        "profile_label": profile,
        "comparison_metric": "package_price",
        "comparison_unit": "USD/package",
        "scope_mode": "global",
        "scoped_benchmark_locations": 2,
        **relationship_summary,
    }
    scorecard = {
        "competitor_id": "aldi_us",
        "competitor": "ALDI",
        "benchmark_products": 1,
        "competitor_products": 1,
        "relationships": 1,
        **scorecard_summary,
        "products": [product],
        "product_relationships": [relationship],
    }
    assortment = {
        "competitor_id": "aldi_us",
        "competitor": "ALDI",
        "profile_id": profile,
        "relationships": 1,
        "matched_benchmark_products": 1,
        "matched_competitor_products": 1,
        "benchmark_only_products": 0,
        "competitor_whitespace_products": 0,
        "benchmark_match_coverage": 1.0,
        "competitor_match_coverage": 1.0,
        "profiles": [],
        "top_benchmark_only": [],
        "top_competitor_whitespace": [],
        "products": [product],
        **scorecard_summary,
    }
    return {
        "schema_version": "1.2.0",
        "analysis_id": "egg-release",
        "generated_at": "2026-08-20T12:00:00+00:00",
        "benchmark_retailer": {"id": "walmart_us", "name": "Walmart (US)"},
        "filters": {
            "competitor_id": "all",
            "profile_id": profile,
            "radius_miles": radius,
            "state": None,
            "city": None,
        },
        "policy": {
            "physical_store_rule": "within selected radius",
            "service_area_rule": "same delivery ZIP",
            "grain": "certified product relationship x observed Walmart product-store",
        },
        "scorecards": [scorecard],
        "cohorts": [],
        "assortment_scorecards": [assortment],
    }


def _complete_set() -> list[dict[str, Any]]:
    return [
        _document(profile, radius, {1: 1, 3: 2, 5: 2}[radius])
        for profile in ("compatible", "strict")
        for radius in (1, 3, 5)
    ]


def test_competitive_release_audit_reconciles_complete_radius_matrix() -> None:
    audit = audit_competitive_portfolio_set(
        _complete_set(),
        expected_profiles=("compatible", "strict"),
    )

    assert audit["status"] == "passed"
    assert audit["document_count"] == 6
    assert audit["error_count"] == 0
    assert audit["warning_count"] == 0


def test_competitive_release_audit_fails_rates_rollups_and_radius_regression() -> None:
    documents = deepcopy(_complete_set())
    documents[1]["scorecards"][0]["coverage_rate"] = 0.25
    documents[1]["scorecards"][0]["average_gap"] = 99.0
    documents[1]["scorecards"][0]["products"][0]["scored_product_locations"] = 1
    documents[2]["scorecards"][0]["scored_product_locations"] = 0
    documents[2]["scorecards"][0]["unscored_product_locations"] = 2
    documents[2]["scorecards"][0]["coverage_rate"] = 0.0
    documents[2]["scorecards"][0]["leader_product_locations"] = 0
    documents[2]["scorecards"][0]["leader_rate"] = None
    documents[2]["scorecards"][0]["benchmark_lower_rate"] = None
    documents[2]["scorecards"][0]["competitor_lower_rate"] = None
    documents[2]["scorecards"][0]["parity_rate"] = None

    audit = audit_competitive_portfolio_set(
        documents,
        expected_profiles=("compatible", "strict"),
    )

    assert audit["status"] == "failed"
    codes = {row["code"] for row in audit["findings"] if row["severity"] == "error"}
    assert "rate_mismatch" in codes
    assert "product_rollup_mismatch" in codes
    assert "average_gap_rollup_mismatch" in codes
    assert "radius_scored_evidence_regression" in codes
    with pytest.raises(ValueError, match="competitive portfolio release audit failed"):
        require_competitive_portfolio_set(
            documents,
            expected_profiles=("compatible", "strict"),
        )


def test_competitive_release_audit_rejects_incomplete_materialization_matrix() -> None:
    audit = audit_competitive_portfolio_set(
        _complete_set()[:-1],
        expected_profiles=("compatible", "strict"),
    )

    assert audit["status"] == "failed"
    assert any(row["code"] == "materialization_matrix_incomplete" for row in audit["findings"])
