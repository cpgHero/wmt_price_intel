from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from rci_analytics import (
    CompetitiveProductLeadershipProjector,
    ProductLeadershipRelationship,
    ProductPriceObservation,
    certify_competitive_product_leadership,
)
from rci_contracts import validate_instance

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def test_competitive_product_leadership_example_matches_contract() -> None:
    example = json.loads(
        (REPOSITORY_ROOT / "examples/competitive-product-leadership.example.json").read_text()
    )

    validate_instance(
        REPOSITORY_ROOT,
        "competitive-product-leadership.schema.json",
        example,
        label="competitive product leadership example",
    )


def _observation(
    retailer: str,
    product: str,
    store: str,
    longitude: float,
    price: float,
) -> ProductPriceObservation:
    return ProductPriceObservation(
        retailer_id=retailer,
        retailer_name="Walmart (US)" if retailer == "walmart_us" else "ALDI",
        product_id=product,
        product_name=f"Product {product}",
        image_url=None,
        scope_key=f"{retailer}|72712|{store}",
        location_kind="store",
        store_number=store,
        store_name=f"Store {store}",
        zipcode="72712",
        city="Bentonville",
        state="AR",
        country="USA",
        latitude=36.37,
        longitude=longitude,
        package_price=price,
        comparison_value=price,
        observed_at="2026-08-07T06:00:00Z",
        is_sponsored=False,
        in_stock=True,
        availability_status="verified_in_stock",
        verified_local_availability=True,
    )


def _unverified(
    observation: ProductPriceObservation,
    *,
    reason: str,
) -> ProductPriceObservation:
    if reason == "sponsored":
        return replace(
            observation,
            is_sponsored=True,
            availability_status="unverified_sponsored",
            verified_local_availability=False,
        )
    if reason == "out_of_stock":
        return replace(
            observation,
            in_stock=False,
            availability_status="explicitly_out_of_stock",
            verified_local_availability=False,
        )
    if reason == "unknown_sponsorship":
        return replace(
            observation,
            is_sponsored=None,
            availability_status="unverified",
            verified_local_availability=False,
        )
    if reason == "unknown_stock":
        return replace(
            observation,
            in_stock=None,
            availability_status="unverified",
            verified_local_availability=False,
        )
    if reason == "contradictory":
        return replace(
            observation,
            in_stock=False,
            availability_status="verified_in_stock",
            verified_local_availability=True,
        )
    if reason == "not_search_observed":
        return replace(observation, search_observed=False)
    raise ValueError(f"unsupported unverified reason: {reason}")


def _single_store_result(
    *,
    benchmark: list[ProductPriceObservation],
    competitors: list[ProductPriceObservation],
) -> dict[str, Any]:
    relationship = ProductLeadershipRelationship(
        relationship_id="verified-local-relationship",
        competitor_id="aldi_us",
        competitor_name="ALDI",
        benchmark_product_id="w1",
        competitor_product_id="a1",
        profile_id="strict",
        profile_label="Strict",
        comparison_metric="package_price",
        comparison_unit="USD/package",
    )
    return CompetitiveProductLeadershipProjector().build(
        analysis_id="verified-local-analysis",
        generated_at="2026-08-07T06:00:00Z",
        benchmark_retailer={"id": "walmart_us", "name": "Walmart (US)"},
        benchmark_product={"id": "w1", "name": "Product w1", "image_url": None},
        benchmark_observations=benchmark,
        competitor_observations=competitors,
        relationships=[relationship],
        competitor_options=[{"id": "aldi_us", "name": "ALDI"}],
        product_options=[{"id": "w1", "name": "Product w1", "image_url": None}],
        profile_options=[{"id": "strict", "name": "Strict"}],
        selected_competitor="all",
        selected_profile="strict",
        radius_miles=1,
    )


def test_leadership_excludes_search_presence_without_verified_local_availability() -> None:
    reasons = (
        "sponsored",
        "out_of_stock",
        "unknown_sponsorship",
        "unknown_stock",
        "contradictory",
        "not_search_observed",
    )
    benchmark = [
        _unverified(
            _observation("walmart_us", "w1", f"w-{index}", -94.21, 3.00),
            reason=reason,
        )
        for index, reason in enumerate(reasons)
    ]
    benchmark.append(_observation("walmart_us", "w1", "w-verified", -94.21, 4.00))
    competitors = [
        _unverified(
            _observation("aldi_us", "a1", f"a-{index}", -94.205, 1.00),
            reason=reason,
        )
        for index, reason in enumerate(reasons)
    ]
    competitors.append(_observation("aldi_us", "a1", "a-verified", -94.205, 4.50))

    result = _single_store_result(benchmark=benchmark, competitors=competitors)

    summary = result["summary"]
    assert isinstance(summary, dict)
    assert summary["benchmark_observed_stores"] == 1
    assert summary["scored_stores"] == 1
    outcomes = result["outcomes"]
    assert isinstance(outcomes, list)
    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert isinstance(outcome, dict)
    assert outcome["status"] == "leader"
    assert outcome["benchmark"]["store_number"] == "w-verified"
    assert outcome["competitor"]["store_number"] == "a-verified"
    assert "verified local Search-listed" in result["policy"]["comparison_definition"]
    assert certify_competitive_product_leadership(result).ready


@pytest.mark.parametrize(
    ("side", "field", "value"),
    [
        ("benchmark", "is_sponsored", True),
        ("benchmark", "is_sponsored", None),
        ("benchmark", "in_stock", False),
        ("benchmark", "in_stock", None),
        ("benchmark", "availability_status", "unverified"),
        ("benchmark", "verified_local_availability", False),
        ("competitor", "is_sponsored", True),
        ("competitor", "is_sponsored", None),
        ("competitor", "in_stock", False),
        ("competitor", "in_stock", None),
        ("competitor", "availability_status", "unverified"),
        ("competitor", "verified_local_availability", False),
    ],
)
def test_certifier_independently_rejects_unverified_local_outcome_evidence(
    side: str,
    field: str,
    value: object,
) -> None:
    result = _single_store_result(
        benchmark=[_observation("walmart_us", "w1", "w-1", -94.21, 4.00)],
        competitors=[_observation("aldi_us", "a1", "a-1", -94.205, 3.50)],
    )
    corrupted = copy.deepcopy(result)
    corrupted["outcomes"][0][side][field] = value

    certification = certify_competitive_product_leadership(corrupted)

    assert not certification.ready
    assert f"outcomes[0]: {side} lacks verified local availability evidence" in certification.errors


@pytest.mark.parametrize("side", ["benchmark", "competitor"])
def test_certifier_requires_a_positive_search_listed_price(side: str) -> None:
    result = _single_store_result(
        benchmark=[_observation("walmart_us", "w1", "w-1", -94.21, 4.00)],
        competitors=[_observation("aldi_us", "a1", "a-1", -94.205, 3.50)],
    )
    corrupted = copy.deepcopy(result)
    corrupted["outcomes"][0][side]["search_observed"] = False

    certification = certify_competitive_product_leadership(corrupted)

    assert not certification.ready
    assert f"outcomes[0]: {side} lacks a positive Search-listed price" in certification.errors


def test_store_leadership_uses_radius_scope_and_mutually_exclusive_statuses() -> None:
    benchmark = [
        _observation("walmart_us", "w1", "w-1", -94.21, 4.00),
        _observation("walmart_us", "w1", "w-2", -94.17, 4.00),
        _observation("walmart_us", "w1", "w-3", -93.90, 4.00),
    ]
    competitors = [
        _observation("aldi_us", "a1", "a-1", -94.205, 3.75),
        _observation("aldi_us", "a1", "a-2", -94.165, 4.06),
    ]
    relationship = ProductLeadershipRelationship(
        relationship_id="relationship-1",
        competitor_id="aldi_us",
        competitor_name="ALDI",
        benchmark_product_id="w1",
        competitor_product_id="a1",
        profile_id="strict",
        profile_label="Strict each-to-each",
        comparison_metric="package_price",
        comparison_unit="USD/package",
    )

    result = CompetitiveProductLeadershipProjector().build(
        analysis_id="analysis-1",
        generated_at="2026-08-07T06:00:00Z",
        benchmark_retailer={"id": "walmart_us", "name": "Walmart (US)"},
        benchmark_product={"id": "w1", "name": "Product w1", "image_url": None},
        benchmark_observations=benchmark,
        competitor_observations=competitors,
        relationships=[relationship],
        competitor_options=[{"id": "aldi_us", "name": "ALDI"}],
        product_options=[{"id": "w1", "name": "Product w1", "image_url": None}],
        profile_options=[{"id": "strict", "name": "Strict each-to-each"}],
        selected_competitor="all",
        selected_profile="strict",
        radius_miles=1,
    )

    validate_instance(
        REPOSITORY_ROOT,
        "competitive-product-leadership.schema.json",
        result,
        label="competitive product leadership test view",
    )

    assert result["summary"] == {
        "benchmark_observed_stores": 3,
        "scored_stores": 2,
        "coverage_rate": 0.6667,
        "leader_stores": 0,
        "tied_stores": 0,
        "at_risk_stores": 1,
        "losing_stores": 1,
        "unscored_stores": 1,
        "leader_rate": 0.0,
        "average_gap": -0.095,
        "average_losing_gap": 0.25,
        "maximum_losing_gap": 0.25,
    }
    assert {row["status"] for row in result["outcomes"]} == {
        "losing",
        "at_risk",
        "unscored",
    }
    assert all("price_ladder" not in row for row in result["outcomes"])
    losing = next(row for row in result["outcomes"] if row["status"] == "losing")
    assert losing["comparison_value_reduction_to_lead"] == 0.26
    ladder = result["price_ladder_summary"]
    assert ladder["comparable_benchmark_locations"] == 2
    assert ladder["benchmark_rank_one_locations"] == 1
    assert ladder["benchmark_rank_one_rate"] == 0.5
    assert [row["product_id"] for row in ladder["rows"]] == ["a1", "w1"]


def test_unmatched_governed_product_remains_visible_and_every_store_is_unscored() -> None:
    benchmark = [
        _observation("walmart_us", "w-unmatched", "w-1", -94.21, 4.00),
        _observation("walmart_us", "w-unmatched", "w-2", -94.17, 4.10),
    ]
    result = CompetitiveProductLeadershipProjector().build(
        analysis_id="analysis-unmatched",
        generated_at="2026-08-07T06:00:00Z",
        benchmark_retailer={"id": "walmart_us", "name": "Walmart (US)"},
        benchmark_product={"id": "w-unmatched", "name": "Unmatched", "image_url": None},
        benchmark_observations=benchmark,
        competitor_observations=[],
        relationships=[],
        competitor_options=[{"id": "aldi_us", "name": "ALDI"}],
        product_options=[{"id": "w-unmatched", "name": "Unmatched", "image_url": None}],
        profile_options=[{"id": "strict", "name": "Strict each-to-each"}],
        selected_competitor="all",
        selected_profile="strict",
        radius_miles=1,
        comparison_metric="package_price",
        comparison_unit="USD/package",
    )

    validate_instance(
        REPOSITORY_ROOT,
        "competitive-product-leadership.schema.json",
        result,
        label="unmatched competitive product leadership view",
    )
    assert result["summary"]["benchmark_observed_stores"] == 2
    assert result["summary"]["scored_stores"] == 0
    assert result["summary"]["unscored_stores"] == 2
    assert not result["relationships"]
    assert certify_competitive_product_leadership(result).ready


def test_footprint_price_ladder_keeps_one_product_position_per_benchmark_store() -> None:
    benchmark = [_observation("walmart_us", "w1", "w-1", -94.21, 4.00)]
    competitors = [
        _observation("aldi_us", "a1", "a-1", -94.205, 3.75),
        _observation("aldi_us", "a1", "a-2", -94.204, 3.95),
        _observation("aldi_us", "a2", "a-3", -94.203, 4.50),
    ]
    relationships = [
        ProductLeadershipRelationship(
            relationship_id=f"relationship-{product}",
            competitor_id="aldi_us",
            competitor_name="ALDI",
            benchmark_product_id="w1",
            competitor_product_id=product,
            profile_id="strict",
            profile_label="Strict each-to-each",
            comparison_metric="package_price",
            comparison_unit="USD/package",
        )
        for product in ("a1", "a2")
    ]

    result = CompetitiveProductLeadershipProjector().build(
        analysis_id="analysis-ladder",
        generated_at="2026-08-07T06:00:00Z",
        benchmark_retailer={"id": "walmart_us", "name": "Walmart (US)"},
        benchmark_product={"id": "w1", "name": "Product w1", "image_url": None},
        benchmark_observations=benchmark,
        competitor_observations=competitors,
        relationships=relationships,
        competitor_options=[{"id": "aldi_us", "name": "ALDI"}],
        product_options=[{"id": "w1", "name": "Product w1", "image_url": None}],
        profile_options=[{"id": "strict", "name": "Strict each-to-each"}],
        selected_competitor="all",
        selected_profile="strict",
        radius_miles=1,
    )

    ladder = result["price_ladder_summary"]
    assert ladder["comparable_benchmark_locations"] == 1
    assert ladder["median_benchmark_rank"] == 2.0
    assert ladder["benchmark_rank_one_locations"] == 0
    assert [row["product_id"] for row in ladder["rows"]] == [
        "a1",
        "w1",
        "a2",
    ]
    a1 = next(row for row in ladder["rows"] if row["product_id"] == "a1")
    assert a1["comparison_locations"] == 1
    assert a1["price_median"] == 3.75
    assert a1["below_benchmark_locations"] == 1
    assert certify_competitive_product_leadership(result).ready


def test_distribution_scoped_relationship_only_scores_admitted_benchmark_store() -> None:
    benchmark = [
        _observation("walmart_us", "w1", "w-1", -94.21, 4.00),
        _observation("walmart_us", "w1", "w-2", -94.20, 4.00),
    ]
    competitor = [_observation("aldi_us", "a1", "a-1", -94.205, 3.50)]
    relationship = ProductLeadershipRelationship(
        relationship_id="regional-relationship",
        competitor_id="aldi_us",
        competitor_name="ALDI",
        benchmark_product_id="w1",
        competitor_product_id="a1",
        profile_id="strict",
        profile_label="Strict",
        comparison_metric="package_price",
        comparison_unit="USD/package",
        scope_mode="observed_benchmark_product_footprint",
        benchmark_location_scope_keys=(benchmark[0].scope_key,),
    )

    result = CompetitiveProductLeadershipProjector().build(
        analysis_id="analysis-1",
        generated_at="2026-08-07T06:00:00Z",
        benchmark_retailer={"id": "walmart_us", "name": "Walmart (US)"},
        benchmark_product={"id": "w1", "name": "Product w1", "image_url": None},
        benchmark_observations=benchmark,
        competitor_observations=competitor,
        relationships=[relationship],
        competitor_options=[{"id": "aldi_us", "name": "ALDI"}],
        product_options=[{"id": "w1", "name": "Product w1", "image_url": None}],
        profile_options=[{"id": "strict", "name": "Strict"}],
        selected_competitor="aldi_us",
        selected_profile="strict",
        radius_miles=1,
    )

    assert result["summary"]["scored_stores"] == 1
    assert result["summary"]["unscored_stores"] == 1


def test_compacted_observed_footprint_scope_admits_all_observed_benchmark_stores() -> None:
    benchmark = [
        _observation("walmart_us", "w1", "w-1", -94.21, 4.00),
        _observation("walmart_us", "w1", "w-2", -94.20, 4.00),
    ]
    competitor = [_observation("aldi_us", "a1", "a-1", -94.205, 3.50)]
    relationship = ProductLeadershipRelationship(
        relationship_id="footprint-relationship",
        competitor_id="aldi_us",
        competitor_name="ALDI",
        benchmark_product_id="w1",
        competitor_product_id="a1",
        profile_id="strict",
        profile_label="Strict",
        comparison_metric="package_price",
        comparison_unit="USD/package",
        scope_mode="observed_benchmark_product_footprint",
    )

    result = CompetitiveProductLeadershipProjector().build(
        analysis_id="analysis-1",
        generated_at="2026-08-07T06:00:00Z",
        benchmark_retailer={"id": "walmart_us", "name": "Walmart (US)"},
        benchmark_product={"id": "w1", "name": "Product w1", "image_url": None},
        benchmark_observations=benchmark,
        competitor_observations=competitor,
        relationships=[relationship],
        competitor_options=[{"id": "aldi_us", "name": "ALDI"}],
        product_options=[{"id": "w1", "name": "Product w1", "image_url": None}],
        profile_options=[{"id": "strict", "name": "Strict"}],
        selected_competitor="aldi_us",
        selected_profile="strict",
        radius_miles=1,
    )

    assert result["summary"]["scored_stores"] == 2
    assert result["summary"]["unscored_stores"] == 0
    assert result["relationships"][0]["scoped_benchmark_locations"] == 2


def test_distribution_scope_translates_canonical_product_location_key() -> None:
    benchmark = [
        replace(
            _observation("walmart_us", "w1", "w-1", -94.21, 4.00),
            scope_key="walmart_us|store|w-1",
        )
    ]
    competitor = [
        replace(
            _observation("amazon_us_same_day", "a1", "", -94.21, 3.50),
            scope_key="amazon_us_same_day|service_area|72712",
            location_kind="service_area",
            store_number=None,
        )
    ]
    relationship = ProductLeadershipRelationship(
        relationship_id="regional-relationship",
        competitor_id="amazon_us_same_day",
        competitor_name="Amazon Same Day",
        benchmark_product_id="w1",
        competitor_product_id="a1",
        profile_id="strict",
        profile_label="Strict",
        comparison_metric="package_price",
        comparison_unit="USD/package",
        scope_mode="observed_benchmark_product_footprint",
        benchmark_location_scope_keys=("walmart_us|72712|w-1",),
    )

    result = CompetitiveProductLeadershipProjector().build(
        analysis_id="analysis-1",
        generated_at="2026-08-07T06:00:00Z",
        benchmark_retailer={"id": "walmart_us", "name": "Walmart (US)"},
        benchmark_product={"id": "w1", "name": "Product w1", "image_url": None},
        benchmark_observations=benchmark,
        competitor_observations=competitor,
        relationships=[relationship],
        competitor_options=[{"id": "amazon_us_same_day", "name": "Amazon Same Day"}],
        product_options=[{"id": "w1", "name": "Product w1", "image_url": None}],
        profile_options=[{"id": "strict", "name": "Strict"}],
        selected_competitor="all",
        selected_profile="strict",
        radius_miles=3,
    )

    assert result["summary"]["scored_stores"] == 1
    assert result["outcomes"][0]["distance_miles"] is None
    assert certify_competitive_product_leadership(result).ready

    wrong_zip = copy.deepcopy(result)
    wrong_zip["outcomes"][0]["competitor"]["zipcode"] = "99999"
    certification = certify_competitive_product_leadership(wrong_zip)
    assert not certification.ready
    assert any(
        "service-area comparison is not exact ZIP" in error for error in certification.errors
    )


def test_product_leadership_certification_recomputes_math_and_geography() -> None:
    benchmark = [_observation("walmart_us", "w1", "w-1", -94.21, 4.00)]
    competitor = [_observation("aldi_us", "a1", "a-1", -94.205, 3.50)]
    relationship = ProductLeadershipRelationship(
        relationship_id="relationship-1",
        competitor_id="aldi_us",
        competitor_name="ALDI",
        benchmark_product_id="w1",
        competitor_product_id="a1",
        profile_id="strict",
        profile_label="Strict",
        comparison_metric="package_price",
        comparison_unit="USD/package",
    )
    result = CompetitiveProductLeadershipProjector().build(
        analysis_id="analysis-1",
        generated_at="2026-08-07T06:00:00Z",
        benchmark_retailer={"id": "walmart_us", "name": "Walmart (US)"},
        benchmark_product={"id": "w1", "name": "Product w1", "image_url": None},
        benchmark_observations=benchmark,
        competitor_observations=competitor,
        relationships=[relationship],
        competitor_options=[{"id": "aldi_us", "name": "ALDI"}],
        product_options=[{"id": "w1", "name": "Product w1", "image_url": None}],
        profile_options=[{"id": "strict", "name": "Strict"}],
        selected_competitor="all",
        selected_profile="strict",
        radius_miles=1,
    )

    certification = certify_competitive_product_leadership(result)
    assert certification.ready
    assert certification.checks > 40

    corrupted = copy.deepcopy(result)
    corrupted["summary"]["losing_stores"] = 0
    broken = certify_competitive_product_leadership(corrupted)
    assert not broken.ready
    assert "summary.losing_stores does not reconcile to outcomes" in broken.errors


def test_spatial_index_keeps_nearby_stores_across_bucket_boundary() -> None:
    benchmark = [_observation("walmart_us", "w1", "w-1", -94.199, 4.00)]
    competitor = [_observation("aldi_us", "a1", "a-1", -94.201, 3.90)]
    relationship = ProductLeadershipRelationship(
        relationship_id="boundary-relationship",
        competitor_id="aldi_us",
        competitor_name="ALDI",
        benchmark_product_id="w1",
        competitor_product_id="a1",
        profile_id="strict",
        profile_label="Strict",
        comparison_metric="package_price",
        comparison_unit="USD/package",
    )

    result = CompetitiveProductLeadershipProjector().build(
        analysis_id="analysis-1",
        generated_at="2026-08-07T06:00:00Z",
        benchmark_retailer={"id": "walmart_us", "name": "Walmart (US)"},
        benchmark_product={"id": "w1", "name": "Product w1", "image_url": None},
        benchmark_observations=benchmark,
        competitor_observations=competitor,
        relationships=[relationship],
        competitor_options=[{"id": "aldi_us", "name": "ALDI"}],
        product_options=[{"id": "w1", "name": "Product w1", "image_url": None}],
        profile_options=[{"id": "strict", "name": "Strict"}],
        selected_competitor="aldi_us",
        selected_profile="strict",
        radius_miles=1,
    )

    assert result["summary"]["scored_stores"] == 1
    assert result["outcomes"][0]["status"] == "losing"
    assert result["city_summaries"] == []
