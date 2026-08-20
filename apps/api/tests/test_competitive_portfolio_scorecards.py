from __future__ import annotations

from pathlib import Path
from types import MethodType

import pytest
from fastapi import HTTPException

from rci_api.competitive_leadership import (
    CompetitiveProductLeadershipService,
    _candidate_segment_rows,
    _portfolio_summary,
    _require_internal_materialization_token,
)
from rci_contracts import validate_instance

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_certified_candidate_creates_cohort_without_legacy_price_segment() -> None:
    rows = _candidate_segment_rows(
        {"product_pack": {"cohort_dimensions": ["count", "size"]}},
        [
            {
                "competitor": "sams_club_us",
                "profile_id": "compatible",
                "match_attributes": {
                    "count": 24.0,
                    "size": "Large",
                    "brand": "Member's Mark",
                },
            }
        ],
        [],
    )

    assert len(rows) == 1
    assert rows[0]["_competitor_id"] == "sams_club_us"
    assert rows[0]["_segment_attributes"] == {"count": 24.0, "size": "Large"}
    assert "Brand" not in rows[0]["segment"]


def test_competitive_materialization_requires_internal_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RCI_INTERNAL_SERVICE_TOKEN", "expected")

    with pytest.raises(HTTPException) as missing:
        _require_internal_materialization_token(None)
    assert getattr(missing.value, "status_code", None) == 401

    with pytest.raises(HTTPException) as wrong:
        _require_internal_materialization_token("wrong")
    assert getattr(wrong.value, "status_code", None) == 401

    _require_internal_materialization_token("expected")


@pytest.mark.asyncio
async def test_portfolio_materialization_rejects_non_ready_report() -> None:
    class Analyses:
        async def report_view(self, _analysis_id: str) -> dict:
            return {
                "report_readiness": {
                    "blocking_reasons": [{"code": "certified_relationship_count_mismatch"}]
                }
            }

    service = CompetitiveProductLeadershipService(
        repository_root=REPOSITORY_ROOT,
        analyses=Analyses(),  # type: ignore[arg-type]
        price_monitoring=None,  # type: ignore[arg-type]
        product_packs=None,  # type: ignore[arg-type]
    )

    with pytest.raises(ValueError, match="certified_relationship_count_mismatch"):
        await service.pre_materialize_portfolios("analysis-1")


def test_portfolio_summary_uses_product_location_grain() -> None:
    summary = _portfolio_summary(
        [
            {"status": "leader", "competitor_minus_benchmark": 0.2},
            {"status": "losing", "competitor_minus_benchmark": -0.1},
            {"status": "unscored", "competitor_minus_benchmark": None},
        ]
    )

    assert summary == {
        "benchmark_product_locations": 3,
        "scored_product_locations": 2,
        "coverage_rate": 0.6667,
        "leader_product_locations": 1,
        "tied_product_locations": 0,
        "at_risk_product_locations": 0,
        "losing_product_locations": 1,
        "unscored_product_locations": 1,
        "leader_rate": 0.5,
        "benchmark_lower_rate": 0.5,
        "competitor_lower_rate": 0.5,
        "parity_rate": 0.0,
        "average_gap": 0.05,
    }


def test_portfolio_scorecard_contract_accepts_radius_native_projection() -> None:
    summary = _portfolio_summary([{"status": "leader", "competitor_minus_benchmark": 0.2}])
    document = {
        "schema_version": "1.1.0",
        "analysis_id": "analysis-1",
        "generated_at": "2026-08-20T12:00:00+00:00",
        "benchmark_retailer": {"id": "walmart_us", "name": "Walmart (US)"},
        "filters": {
            "competitor_id": "aldi_us",
            "profile_id": "compatible",
            "radius_miles": 3,
            "state": None,
            "city": None,
        },
        "policy": {
            "physical_store_rule": "within selected radius",
            "service_area_rule": "same delivery ZIP",
            "grain": "certified product relationship x observed Walmart product-store",
        },
        "scorecards": [
            {
                "competitor_id": "aldi_us",
                "competitor": "ALDI",
                "benchmark_products": 1,
                "competitor_products": 1,
                "relationships": 1,
                **summary,
                "products": [
                    {
                        "product_id": "w1",
                        "product_name": "Walmart product",
                        "image_url": None,
                        "relationships": 1,
                        **summary,
                    }
                ],
            }
        ],
        "cohorts": [],
        "assortment_scorecards": [],
    }

    validate_instance(
        REPOSITORY_ROOT,
        "competitive-portfolio-scorecards.schema.json",
        document,
        label="competitive portfolio scorecards",
    )


@pytest.mark.asyncio
async def test_portfolio_view_aggregates_each_certified_product_location_once() -> None:
    class Analyses:
        async def report_view(self, _analysis_id: str) -> dict:
            return {
                "generated_at": "2026-08-20T12:00:00+00:00",
                "retailer_scope": {
                    "benchmark": {"id": "walmart_us", "name": "Walmart (US)"},
                    "competitors": [{"id": "aldi_us", "name": "ALDI"}],
                },
                "comparison_bases": [
                    {
                        "profile_id": "compatible",
                        "scorecard_role": "preferred",
                    }
                ],
                "match_candidates": [
                    {
                        "id": "pair-1",
                        "relationship_id": "relationship-1",
                        "relationship_status": "confirmed",
                        "qa_status": "ready",
                        "profile_id": "compatible",
                        "competitor": "aldi_us",
                        "benchmark_product_id": "w1",
                        "competitor_product_id": "a1",
                        "match_attributes": {"size": "large", "count": 12},
                    },
                    {
                        "id": "pair-2",
                        "relationship_id": "relationship-2",
                        "relationship_status": "confirmed",
                        "qa_status": "ready",
                        "profile_id": "compatible",
                        "competitor": "aldi_us",
                        "benchmark_product_id": "w1",
                        "competitor_product_id": "a2",
                        "match_attributes": {"size": "large", "count": 12},
                    },
                ],
                "sections": [
                    {
                        "kind": "segment_analysis",
                        "records": [
                            {
                                "_competitor_id": "aldi_us",
                                "_profile_id": "compatible",
                                "_segment_id": "large-12",
                                "_segment_attributes": {"size": "Large", "count": 12.0},
                                "competitor": "ALDI",
                                "segment": "12 each · large",
                            }
                        ],
                    }
                ],
                "assortment_analysis": {
                    "comparisons": [
                        {
                            "competitor": "aldi_us",
                            "benchmark_only_products": 2,
                            "competitor_whitespace_products": 3,
                            "benchmark_match_coverage": 0.25,
                            "competitor_match_coverage": 0.5,
                        }
                    ]
                },
            }

    service = CompetitiveProductLeadershipService(
        repository_root=REPOSITORY_ROOT,
        analyses=Analyses(),  # type: ignore[arg-type]
        price_monitoring=None,  # type: ignore[arg-type]
        product_packs=None,  # type: ignore[arg-type]
    )

    async def view(self: CompetitiveProductLeadershipService, *_args: object, **_kwargs: object):
        return {
            "benchmark_product": {
                "id": "w1",
                "name": "Walmart product",
                "image_url": None,
            },
            "relationships": [
                {
                    "relationship_id": "relationship-1",
                    "competitor_id": "aldi_us",
                    "competitor_name": "ALDI",
                    "benchmark_product_id": "w1",
                    "benchmark_product_name": "Walmart product",
                    "benchmark_image_url": "https://example.com/w1.png",
                    "competitor_product_id": "a1",
                    "competitor_product_name": "ALDI product one",
                    "competitor_brand": "Friendly Farms",
                    "competitor_brand_type": "private_label",
                    "competitor_image_url": "https://example.com/a1.png",
                    "profile_id": "compatible",
                    "profile_label": "Compatible package",
                    "comparison_metric": "package_price",
                    "comparison_unit": "USD/package",
                    "scope_mode": "global",
                    "scoped_benchmark_locations": 2,
                },
                {
                    "relationship_id": "relationship-2",
                    "competitor_id": "aldi_us",
                    "competitor_name": "ALDI",
                    "benchmark_product_id": "w1",
                    "benchmark_product_name": "Walmart product",
                    "benchmark_image_url": "https://example.com/w1.png",
                    "competitor_product_id": "a2",
                    "competitor_product_name": "ALDI product two",
                    "competitor_brand": "Friendly Farms",
                    "competitor_brand_type": "private_label",
                    "competitor_image_url": "https://example.com/a2.png",
                    "profile_id": "compatible",
                    "profile_label": "Compatible package",
                    "comparison_metric": "package_price",
                    "comparison_unit": "USD/package",
                    "scope_mode": "global",
                    "scoped_benchmark_locations": 2,
                },
            ],
            "outcomes": [
                {
                    "relationship_id": "relationship-1",
                    "status": "leader",
                    "competitor_minus_benchmark": 0.2,
                    "benchmark": {"comparison_value": 3.0},
                    "competitor": {"comparison_value": 3.2},
                },
                {
                    "relationship_id": "relationship-1",
                    "status": "losing",
                    "competitor_minus_benchmark": -0.1,
                    "benchmark": {"comparison_value": 3.1},
                    "competitor": {"comparison_value": 3.0},
                },
            ],
        }

    service.view = MethodType(view, service)  # type: ignore[method-assign]
    result = await service.portfolio_view(
        "analysis-1",
        competitor_id="aldi_us",
        profile_id="compatible",
        radius_miles=3,
        state=None,
        city=None,
    )

    assert result["filters"]["radius_miles"] == 3
    assert result["scorecards"][0]["scored_product_locations"] == 2
    assert result["schema_version"] == "1.2.0"
    assert result["scorecards"][0]["relationships"] == 2
    assert result["scorecards"][0]["products"][0]["product_id"] == "w1"
    relationships = result["scorecards"][0]["product_relationships"]
    assert [row["competitor_product_id"] for row in relationships] == ["a1", "a2"]
    assert relationships[0]["scored_product_locations"] == 2
    assert relationships[1]["scored_product_locations"] == 0
    assert relationships[0]["benchmark_product_name"] == "Walmart product"
    assert relationships[0]["competitor_product_name"] == "ALDI product one"
    assert result["cohorts"][0]["segment"] == "12 each · large"
    assert result["cohorts"][0]["relationships"] == 2
    assert result["cohorts"][0]["scored_product_locations"] == 2
    assert result["cohorts"][0]["benchmark_median"] == 3.05
    assert result["cohorts"][0]["paired_median_gap"] == 0.05
    assert result["assortment_scorecards"][0]["benchmark_only_products"] == 2
    assert result["assortment_scorecards"][0]["coverage_rate"] == 1.0
