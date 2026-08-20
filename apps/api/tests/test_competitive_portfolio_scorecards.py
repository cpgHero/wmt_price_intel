from __future__ import annotations

from pathlib import Path
from types import MethodType

import pytest

from rci_api.competitive_leadership import (
    CompetitiveProductLeadershipService,
    _portfolio_summary,
)
from rci_contracts import validate_instance

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


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
        "schema_version": "1.0.0",
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
                    }
                ],
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
            "relationships": [{"relationship_id": "relationship-1"}],
            "outcomes": [
                {"status": "leader", "competitor_minus_benchmark": 0.2},
                {"status": "losing", "competitor_minus_benchmark": -0.1},
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
    assert result["scorecards"][0]["relationships"] == 1
    assert result["scorecards"][0]["products"][0]["product_id"] == "w1"
