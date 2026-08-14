from __future__ import annotations

import json
from pathlib import Path

from rci_analytics import (
    CompetitiveProductLeadershipProjector,
    ProductLeadershipRelationship,
    ProductPriceObservation,
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
    )


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
    losing = next(row for row in result["outcomes"] if row["status"] == "losing")
    assert losing["comparison_value_reduction_to_lead"] == 0.26


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
