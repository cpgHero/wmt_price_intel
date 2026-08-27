from __future__ import annotations

import asyncio
from pathlib import Path
from types import MethodType, SimpleNamespace

import pytest
from fastapi import HTTPException

from rci_api.competitive_leadership import (
    CompetitiveProductLeadershipService,
    _attributes_match,
    _candidate_segment_rows,
    _cohort_summary,
    _coverage_rows,
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


def test_certified_candidate_matches_display_label_cohort_dimensions() -> None:
    rows = _candidate_segment_rows(
        {
            "product_pack": {
                "cohort_dimensions": [
                    "Lean Pct",
                    "Fat Pct",
                    "Weight Lb",
                    "Organic",
                    "Grass Fed",
                    "Premium Tier",
                ]
            }
        },
        [
            {
                "competitor": "aldi_us",
                "profile_id": "strict",
                "match_attributes": {
                    "lean_pct": 93,
                    "fat_pct": 7,
                    "weight_lb": 1.0,
                    "organic": True,
                    "grass_fed": True,
                    "premium_tier": "standard",
                    "brand": "Never Any!",
                },
            }
        ],
        [],
    )

    assert len(rows) == 1
    assert rows[0]["_segment_attributes"] == {
        "lean_pct": 93,
        "fat_pct": 7,
        "weight_lb": 1.0,
        "organic": True,
        "grass_fed": True,
        "premium_tier": "standard",
    }
    assert "brand" not in rows[0]["_segment_attributes"]


def test_cohort_attributes_form_an_exact_partition_when_evidence_is_missing() -> None:
    rows = _candidate_segment_rows(
        {"product_pack": {"cohort_dimensions": ["size", "count", "housing", "organic"]}},
        [
            {
                "competitor": "amazon_us_same_day",
                "profile_id": "strict",
                "match_attributes": {
                    "size": "Large",
                    "count": 12,
                    "housing": "Cage-Free",
                    "organic": True,
                },
            },
            {
                "competitor": "amazon_us_same_day",
                "profile_id": "strict",
                "match_attributes": {
                    "size": "Large",
                    "count": 12,
                    "housing": "Cage-Free",
                },
            },
        ],
        [],
    )

    assert len(rows) == 2
    candidates = [
        {"size": "Large", "count": 12, "housing": "Cage-Free", "organic": True},
        {"size": "Large", "count": 12, "housing": "Cage-Free"},
    ]
    for candidate in candidates:
        assert (
            sum(
                _attributes_match(
                    candidate,
                    row["_segment_attributes"],
                    set(row["_segment_dimensions"]),
                )
                for row in rows
            )
            == 1
        )


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
        async def get(self, analysis_id: str) -> SimpleNamespace:
            return SimpleNamespace(analysis_id=analysis_id)

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


@pytest.mark.asyncio
async def test_portfolio_materialization_does_not_publish_before_set_audit() -> None:
    class Analyses:
        async def get(self, analysis_id: str) -> SimpleNamespace:
            return SimpleNamespace(analysis_id=analysis_id)

        async def report_view(self, analysis_id: str) -> dict:
            return {
                "analysis_id": analysis_id,
                "report_readiness": {"blocking_reasons": []},
                "comparison_bases": [{"profile_id": "strict"}],
            }

    class Repository:
        def __init__(self) -> None:
            self.store_calls = 0

        async def store_materializations(self, _analysis_id: str, _documents: list[dict]) -> None:
            self.store_calls += 1

    repository = Repository()
    service = CompetitiveProductLeadershipService(
        repository_root=REPOSITORY_ROOT,
        analyses=Analyses(),  # type: ignore[arg-type]
        price_monitoring=None,  # type: ignore[arg-type]
        product_packs=None,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
    )
    publish_values: list[bool] = []

    async def invalid_portfolio(
        self: CompetitiveProductLeadershipService,
        *_args: object,
        **kwargs: object,
    ) -> dict:
        publish_values.append(bool(kwargs.get("publish")))
        return {}

    service.portfolio_view = MethodType(invalid_portfolio, service)  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="competitive portfolio release audit failed"):
        await service.pre_materialize_portfolios("analysis-1", refresh=True)

    assert publish_values == [False, False, False]
    assert repository.store_calls == 0


@pytest.mark.asyncio
async def test_decision_quality_view_audits_complete_stored_publication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Analyses:
        async def get(self, analysis_id: str) -> SimpleNamespace:
            return SimpleNamespace(analysis_id=analysis_id)

        async def report_view(self, analysis_id: str) -> dict:
            return {
                "analysis_id": analysis_id,
                "comparison_bases": [
                    {"profile_id": "compatible_spec"},
                    {"profile_id": "exact_spec"},
                ],
            }

    class Repository:
        async def materializations(self, analysis_id: str) -> list[dict]:
            assert analysis_id == "analysis-1"
            return [{"stored": "document"}]

    captured: dict[str, object] = {}

    def audit(documents: list[dict], *, expected_profiles: list[str]) -> dict:
        captured["documents"] = documents
        captured["profiles"] = expected_profiles
        return {
            "schema_version": "1.1.0-competitive-decision-quality-audit",
            "status": "passed",
            "analysis_id": "analysis-1",
            "document_count": 1,
            "profiles": ["compatible_spec", "exact_spec"],
            "radii": [1, 3, 5],
            "retailer_count": 0,
            "expected_context_count": 0,
            "context_count": 0,
            "context_state_counts": {
                "scored": 0,
                "local_evidence_limited": 0,
                "no_selected_basis_relationship": 0,
            },
            "contexts": [],
            "error_count": 0,
            "warning_count": 0,
            "findings": [],
        }

    monkeypatch.setattr("rci_api.competitive_leadership.audit_competitive_portfolio_set", audit)
    service = CompetitiveProductLeadershipService(
        repository_root=REPOSITORY_ROOT,
        analyses=Analyses(),  # type: ignore[arg-type]
        price_monitoring=None,  # type: ignore[arg-type]
        product_packs=None,  # type: ignore[arg-type]
        repository=Repository(),  # type: ignore[arg-type]
    )

    result = await service.decision_quality_view("analysis-1")

    assert result["status"] == "passed"
    assert captured == {
        "documents": [{"stored": "document"}],
        "profiles": ["compatible_spec", "exact_spec"],
    }


@pytest.mark.asyncio
async def test_analysis_context_is_loaded_once_for_concurrent_product_groups() -> None:
    class Analyses:
        def __init__(self) -> None:
            self.get_calls = 0
            self.report_calls = 0

        async def get(self, analysis_id: str) -> SimpleNamespace:
            self.get_calls += 1
            return SimpleNamespace(analysis_id=analysis_id)

        async def report_view(self, analysis_id: str) -> dict:
            self.report_calls += 1
            return {"analysis_id": analysis_id}

    analyses = Analyses()
    service = CompetitiveProductLeadershipService(
        repository_root=REPOSITORY_ROOT,
        analyses=analyses,  # type: ignore[arg-type]
        price_monitoring=None,  # type: ignore[arg-type]
        product_packs=None,  # type: ignore[arg-type]
    )

    first, second = await asyncio.gather(
        service._analysis_context("analysis-1"),
        service._analysis_context("analysis-1"),
    )

    assert first is second
    assert analyses.get_calls == 1
    assert analyses.report_calls == 1


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


def test_coverage_rows_partition_the_complete_catalog_once() -> None:
    funnel, products = _coverage_rows(
        catalog={
            **{product_id: {} for product_id in ("p1", "p2", "p3", "p4", "p5")},
            "p6": {"scope": "exclude"},
        },
        observed_products={
            product_id: {"product_id": product_id, "observed_locations": 3}
            for product_id in ("p1", "p2", "p3", "p4")
        },
        identity_candidates=[
            {
                "relationship_id": "r1",
                "benchmark_product_id": "p1",
                "competitor_product_id": "c1",
            },
            {
                "relationship_id": "r2",
                "benchmark_product_id": "p2",
                "competitor_product_id": "c2",
            },
            {
                "relationship_id": "r3",
                "benchmark_product_id": "p3",
                "competitor_product_id": "c3",
            },
        ],
        selected_candidates=[
            {
                "relationship_id": "r1",
                "benchmark_product_id": "p1",
                "competitor_product_id": "c1",
            },
            {
                "relationship_id": "r2",
                "benchmark_product_id": "p2",
                "competitor_product_id": "c2",
            },
        ],
        product_summaries=[
            {"product_id": "p1", "scored_product_locations": 2},
            {"product_id": "p2", "scored_product_locations": 0},
        ],
    )

    assert funnel == {
        "catalog_products": 6,
        "in_scope_catalog_products": 5,
        "observed_catalog_products": 4,
        "certified_identity_products": 3,
        "selected_price_basis_products": 2,
        "locally_scored_products": 1,
        "scored_product_locations": 2,
        "status_counts": {
            "benchmark_not_observed": 1,
            "no_certified_relationship": 1,
            "no_selected_price_basis": 1,
            "no_local_competitor_evidence": 1,
            "scored": 1,
            "governed_out_of_scope": 1,
        },
    }
    assert len(products) == 6
    assert {row["product_id"] for row in products} == {
        "p1",
        "p2",
        "p3",
        "p4",
        "p5",
        "p6",
    }


def test_cohort_summary_filters_metrics_and_lineage_to_included_relationships() -> None:
    summary = _portfolio_summary([{"status": "leader", "competitor_minus_benchmark": 0.2}])
    relationship_rows = [
        {"relationship_id": "relationship-1", **summary},
        {
            "relationship_id": "relationship-2",
            **_portfolio_summary([{"status": "losing", "competitor_minus_benchmark": -5.0}]),
        },
    ]
    cohort = _cohort_summary(
        segment_row={
            "_competitor_id": "target_us",
            "_profile_id": "compatible",
            "_segment_id": "vitamin-c",
            "_segment_attributes": {"active_ingredient": "vitamin_c"},
            "_segment_dimensions": ["active_ingredient"],
            "competitor": "Target",
            "segment": "Vitamin C",
        },
        candidates=[
            {
                "relationship_id": "relationship-1",
                "benchmark_product_id": "w1",
                "competitor_product_id": "t1",
                "match_attributes": {"active_ingredient": "vitamin_c"},
            },
            {
                "relationship_id": "relationship-2",
                "benchmark_product_id": "w1",
                "competitor_product_id": "t2",
                "match_attributes": {"active_ingredient": "vitamin_e"},
            },
        ],
        product_views={
            "w1": {
                "benchmark_product": {"name": "Spring Valley Vitamin C"},
                "outcomes": [
                    {
                        "relationship_id": "relationship-1",
                        "status": "leader",
                        "competitor_minus_benchmark": 0.2,
                        "benchmark": {"comparison_value": 3.0},
                        "competitor": {"comparison_value": 3.2},
                    },
                    {
                        "relationship_id": "relationship-2",
                        "status": "losing",
                        "competitor_minus_benchmark": -5.0,
                        "benchmark": {"comparison_value": 8.0},
                        "competitor": {"comparison_value": 3.0},
                    },
                ],
            }
        },
        relationship_rows=relationship_rows,
    )

    assert cohort["relationships"] == 1
    assert cohort["scored_product_locations"] == 1
    assert cohort["average_gap"] == 0.2
    assert cohort["benchmark_median"] == 3.0
    assert [row["relationship_id"] for row in cohort["product_relationships"]] == ["relationship-1"]


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
        async def get(self, analysis_id: str) -> SimpleNamespace:
            return SimpleNamespace(analysis_id=analysis_id)

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
                    {
                        "id": "pair-3",
                        "relationship_id": "relationship-3",
                        "relationship_status": "confirmed",
                        "qa_status": "ready",
                        "profile_id": "compatible",
                        "profile_label": "Compatible package",
                        "competitor": "aldi_us",
                        "benchmark_product_id": "w2",
                        "benchmark_product_name": "Walmart unobserved product",
                        "competitor_product_id": "a3",
                        "competitor_product_name": "ALDI product three",
                        "comparison_metric": "package_price",
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
                    "retailers": [
                        {
                            "retailer": "walmart_us",
                            "products": [
                                {
                                    "canonical_product_id": "walmart_us:w1",
                                    "product_id": "w1",
                                    "name": "Walmart product",
                                    "observed_locations": 2,
                                    "observed_zipcodes": 2,
                                }
                            ],
                        },
                        {
                            "retailer": "aldi_us",
                            "products": [
                                {
                                    "canonical_product_id": f"aldi_us:{product_id}",
                                    "product_id": product_id,
                                    "name": f"ALDI {product_id}",
                                    "observed_locations": 1,
                                    "observed_zipcodes": 1,
                                }
                                for product_id in ("a1", "a2", "a3")
                            ],
                        },
                    ],
                    "comparisons": [
                        {
                            "competitor": "aldi_us",
                            "benchmark_only_products": 2,
                            "competitor_whitespace_products": 3,
                            "benchmark_match_coverage": 0.25,
                            "competitor_match_coverage": 0.5,
                        }
                    ],
                },
            }

    class Prices:
        def __init__(self) -> None:
            self.requests: list[tuple[str, str, tuple[str, ...]]] = []

        async def product_observations_for_products(
            self,
            _analysis_id: str,
            *,
            retailer_id: str,
            product_ids: list[str],
            comparison_metric: str,
        ) -> dict:
            self.requests.append((retailer_id, comparison_metric, tuple(product_ids)))
            return {}

    prices = Prices()
    service = CompetitiveProductLeadershipService(
        repository_root=REPOSITORY_ROOT,
        analyses=Analyses(),  # type: ignore[arg-type]
        price_monitoring=prices,  # type: ignore[arg-type]
        product_packs=None,  # type: ignore[arg-type]
    )

    async def view(self: CompetitiveProductLeadershipService, *_args: object, **_kwargs: object):
        if _kwargs.get("benchmark_product_id") == "w2":
            raise LookupError("positive benchmark Search observations are unavailable")
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
    assert result["schema_version"] == "1.4.0"
    assert result["scorecards"][0]["relationships"] == 3
    assert result["scorecards"][0]["evidence_funnel"] == {
        "catalog_products": 2,
        "in_scope_catalog_products": 2,
        "observed_catalog_products": 1,
        "certified_identity_products": 2,
        "selected_price_basis_products": 2,
        "locally_scored_products": 1,
        "scored_product_locations": 2,
        "status_counts": {
            "benchmark_not_observed": 1,
            "no_certified_relationship": 0,
            "no_selected_price_basis": 0,
            "no_local_competitor_evidence": 0,
            "scored": 1,
            "governed_out_of_scope": 0,
        },
    }
    assert result["scorecards"][0]["products"][0]["product_id"] == "w1"
    assert {row["product_id"] for row in result["scorecards"][0]["products"]} == {
        "w1",
        "w2",
    }
    relationships = result["scorecards"][0]["product_relationships"]
    assert [row["competitor_product_id"] for row in relationships] == ["a1", "a2", "a3"]
    assert relationships[0]["scored_product_locations"] == 2
    assert relationships[1]["scored_product_locations"] == 0
    assert relationships[2]["scored_product_locations"] == 0
    assert relationships[0]["benchmark_product_name"] == "Walmart product"
    assert relationships[0]["competitor_product_name"] == "ALDI product one"
    assert result["cohorts"][0]["segment"] == "12 each · large"
    assert result["cohorts"][0]["relationships"] == 3
    assert [
        row["competitor_product_id"] for row in result["cohorts"][0]["product_relationships"]
    ] == ["a1", "a2", "a3"]
    assert result["cohorts"][0]["scored_product_locations"] == 2
    assert result["cohorts"][0]["benchmark_median"] == 3.05
    assert result["cohorts"][0]["paired_median_gap"] == 0.05
    assortment = result["assortment_scorecards"][0]
    assert assortment["matched_benchmark_products"] == 1
    assert assortment["matched_competitor_products"] == 3
    assert assortment["benchmark_only_products"] == 0
    assert assortment["competitor_whitespace_products"] == 0
    assert assortment["benchmark_match_coverage"] == 1.0
    assert result["assortment_scorecards"][0]["coverage_rate"] == 1.0
    assert prices.requests == [
        ("aldi_us", "package_price", ("a1", "a2", "a3")),
        ("walmart_us", "package_price", ("w1", "w2")),
    ]

    coverage = await service.product_coverage_view(
        "analysis-1",
        competitor_id="aldi_us",
        profile_id="compatible",
        radius_miles=3,
    )
    assert coverage["schema_version"] == "1.0.0"
    assert coverage["evidence_funnel"] == result["scorecards"][0]["evidence_funnel"]
    assert [(row["product_id"], row["status"]) for row in coverage["products"]] == [
        ("w1", "scored"),
        ("w2", "benchmark_not_observed"),
    ]
