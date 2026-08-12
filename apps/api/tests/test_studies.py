from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from rci_api.studies import (
    _category_identity,
    _next_patch_version,
    _pdp_plan,
    _study_collection_config,
)
from rci_studies import StudyRecord, canonical_checksum, initial_approval_state

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _study() -> StudyRecord:
    query = {
        "keyword": "fresh category",
        "target_terms": ["category"],
        "exclusion_terms": ["accessory"],
        "alternate_queries": [],
        "source": "deterministic",
        "rationale": "fixture",
        "revision": 1,
    }
    now = datetime.now(UTC)
    return StudyRecord(
        id="4bd66ded-3471-48f9-8b4e-821302a8dfc8",
        name="Fresh category discovery",
        status="query_review",
        intake={
            "benchmark_retailer_id": "walmart_us",
            "competitor_retailer_ids": ["aldi_us"],
            "category_context": "Fresh category",
            "known_inclusions": ["category"],
            "known_exclusions": ["accessory"],
            "geography_request": {},
            "max_search_pages": 1,
            "amazon_same_day_url_template": None,
        },
        query_plan=query,
        query_plan_checksum=canonical_checksum(query),
        approval_state=initial_approval_state(),
        geography_resolution_id=None,
        search_scope_estimate_id=None,
        collection_run_id=None,
        pdp_estimate=None,
        pdp_plan_checksum=None,
        pdp_run_id=None,
        product_pack_draft_id=None,
        profile_summary={},
        last_error=None,
        created_at=now,
        updated_at=now,
    )


def _product(
    retailer_id: str,
    product_id: str,
    contexts: list[dict[str, object]],
    *,
    admission_status: str = "provisionally_admitted",
) -> dict[str, object]:
    return {
        "retailer_id": retailer_id,
        "retailer_product_id": product_id,
        "title": "Fresh category product",
        "brand": "Example",
        "url": f"https://example.test/{product_id}",
        "image_url": None,
        "admission_status": admission_status,
        "price_contexts": contexts,
        "identifiers": {"product_id": product_id},
        "source_artifact_ids": ["artifact-1"],
    }


def test_discovery_collection_has_no_pack_or_analysis_side_effect() -> None:
    config = _study_collection_config(
        _study(),
        resolution_id="ecb98cba-5a58-44c2-a757-af9ad418c447",
        resolution_checksum="a" * 64,
    )

    assert config["purpose"] == "study_discovery"
    assert config["product_pack"] is None
    assert config["analysis"] is None
    assert config["product_detail_enrichment"]["policy"] == "disabled"
    assert [row["retailer_id"] for row in config["retailers"]] == [
        "walmart_us",
        "aldi_us",
    ]


def test_pdp_plan_uses_only_admitted_products_and_distinct_price_contexts() -> None:
    products = [
        _product(
            "walmart_us",
            "100",
            [
                {
                    "zipcode": "72712",
                    "store_number": "1",
                    "fulfillment_type": "pickup",
                    "observed_price": 3.25,
                },
                {
                    "zipcode": "72713",
                    "store_number": "2",
                    "fulfillment_type": "pickup",
                    "observed_price": 3.45,
                },
            ],
        ),
        _product(
            "aldi_us",
            "200",
            [
                {
                    "zipcode": "72712",
                    "store_number": "475-101",
                    "observed_price": 2.99,
                }
            ],
        ),
        _product(
            "walmart_us",
            "noise",
            [
                {
                    "zipcode": "72712",
                    "store_number": "1",
                    "observed_price": 1.00,
                }
            ],
            admission_status="excluded",
        ),
    ]

    estimate, calls = _pdp_plan(products, REPOSITORY_ROOT)

    assert estimate["eligible_products"] == 2
    assert estimate["planned_calls"] == 3
    assert estimate["estimated_credits"] == 5
    assert estimate["invalid_candidates"] == []
    assert {call["retailer_product_id"] for call in calls} == {"100", "200"}
    assert [
        call["request_context"]["fulfillment_type"]
        for call in calls
        if call["retailer_id"] == "aldi_us"
    ] == ["pickup"]


def test_pdp_plan_fails_closed_for_missing_retailer_context() -> None:
    estimate, calls = _pdp_plan(
        [_product("walmart_us", "100", [{"observed_price": 3.25}])],
        REPOSITORY_ROOT,
    )

    assert calls == []
    assert estimate["eligible_products"] == 0
    assert estimate["invalid_candidates"][0]["product_id"] == "100"


def test_study_draft_identity_comes_from_category_not_study_name() -> None:
    study = replace(
        _study(),
        name="Fresh category — Walmart vs ALDI — AR/TX pilot",
    )

    assert _category_identity(study) == ("fresh_category", "Fresh category")


def test_next_patch_version_preserves_existing_release_line() -> None:
    assert _next_patch_version("1.0.0") == "1.0.1"
    assert _next_patch_version("1.2.7") == "1.2.8"
