from __future__ import annotations

from pathlib import Path
from typing import Any

from rci_analytics import AnalysisResultV2Builder, ComparisonFact, ProductPackLoader, evidence_set
from rci_analytics.result_v2 import matching_v2_certification_is_complete
from rci_contracts import validate_instance

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def test_complete_matching_v2_certification_does_not_require_legacy_zip_rows_per_retailer() -> None:
    coverage: dict[str, Any] = {
        "selection_complete": True,
        "queue_case_count": 3,
        "certified_label_count": 2,
        "unresolved_excluded_count": 1,
        "reviewed_insufficient_evidence_count": 1,
        "pending_unreviewed_count": 0,
        "automatic_fallback_enabled": False,
        "retailers": [
            {
                "competitor_retailer_id": "sams_club_us",
                "pending_unreviewed_count": 0,
            },
            {
                "competitor_retailer_id": "target_us",
                "pending_unreviewed_count": 0,
            },
        ],
    }
    source = {
        "matching_v2_gold_set_release_id": "3c967ecc-17fd-4bad-a749-c223519723d0",
        "matching_v2_certification_coverage": coverage,
    }

    assert matching_v2_certification_is_complete(
        source,
        ["sams_club_us", "target_us"],
    )

    coverage.pop("pending_unreviewed_count")
    assert not matching_v2_certification_is_complete(
        source,
        ["sams_club_us", "target_us"],
    )


def test_builder_accepts_complete_matching_v2_identity_without_legacy_row_per_retailer() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_shell_eggs")
    source_evidence = evidence_set(
        "evidence.source",
        "source_manifest",
        [("raw-walmart", "a" * 64, 100), ("raw-target", "b" * 64, 100)],
    )
    comparison_evidence = evidence_set(
        "evidence.matches.target.strict",
        "exact_matches",
        [("target-match", "c" * 64, 10)],
    )
    comparison = ComparisonFact(
        competitor_id="target_us",
        profile_id="strict",
        profile_label="Strict package",
        geography="exact_zip",
        comparison_metric="package_price",
        dimensions=("count", "shell_color"),
        evidence_ref="evidence.matches.target.strict",
        values={
            "matches": 10,
            "unique_geographies": 10,
            "benchmark_lower": 6,
            "competitor_lower": 4,
            "parity": 0,
            "benchmark_lower_rate": 0.6,
            "competitor_lower_rate": 0.4,
            "parity_rate": 0.0,
            "median_gap": 0.12,
        },
    )
    coverage_rows = []
    coverage_evidence = []
    for index, retailer in enumerate(("walmart_us", "target_us", "sams_club_us"), start=1):
        evidence = evidence_set(
            f"evidence.classified.{retailer}",
            "classified_offers",
            [(f"classified-{retailer}", f"{index + 3:x}" * 64, 20)],
        )
        coverage_evidence.append(evidence)
        coverage_rows.append(
            {
                "retailer_id": retailer,
                "offers": 20,
                "in_scope_offers": 20,
                "in_scope_zips": 10,
                "in_scope_stores": 10,
                "evidence_ref": f"evidence.classified.{retailer}",
            }
        )

    result = AnalysisResultV2Builder(pack, code_version="test").build(
        analysis_id="analysis-matching-v2-identity-complete",
        analysis_run_id="run-matching-v2-identity-complete",
        generated_at="2026-08-20T12:00:00Z",
        source={
            "input_set_id": "input-matching-v2-identity-complete",
            "kind": "historical_import",
            "collection_run_id": None,
            "matching_v2_gold_set_release_id": "3c967ecc-17fd-4bad-a749-c223519723d0",
            "matching_v2_gold_set_checksum": "f" * 64,
            "matching_v2_certification_coverage": {
                "selection_complete": True,
                "queue_case_count": 3,
                "certified_label_count": 2,
                "unresolved_excluded_count": 1,
                "reviewed_insufficient_evidence_count": 1,
                "pending_unreviewed_count": 0,
                "automatic_fallback_enabled": False,
                "retailers": [
                    {
                        "competitor_retailer_id": "target_us",
                        "pending_unreviewed_count": 0,
                    },
                    {
                        "competitor_retailer_id": "sams_club_us",
                        "pending_unreviewed_count": 0,
                    },
                ],
            },
            "observed_start": None,
            "observed_end": None,
            "sampling": False,
            "total_rows": 200,
            "source_artifact_ids": ["raw-walmart", "raw-target"],
        },
        benchmark_retailer="walmart_us",
        competitors=["target_us", "sams_club_us"],
        coverage_facts=coverage_rows,
        comparison_facts=[comparison],
        data_quality_facts={
            "normalization_rejections": 0,
            "review_offers": 0,
            "zero_or_missing_price_offers": 0,
        },
        evidence_sets=[source_evidence, comparison_evidence, *coverage_evidence],
        raw_source_artifact_ids=["raw-walmart", "raw-target"],
    )

    assert result["validation"]["status"] == "ready_to_share"
    certification_check = next(
        check
        for check in result["validation"]["checks"]
        if check["id"] == "matching-v2-certification-complete"
    )
    assert certification_check["status"] == "passed"


def test_generic_builder_emits_contract_valid_evidence_linked_result() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_strawberries")
    source_evidence = evidence_set(
        "evidence.source",
        "source_manifest",
        [("raw-walmart", "a" * 64, 100), ("raw-amazon", "b" * 64, 80)],
    )
    classified_walmart = evidence_set(
        "evidence.classified.walmart_us",
        "classified_offers",
        [("classified-walmart", "c" * 64, 20)],
    )
    classified_amazon = evidence_set(
        "evidence.classified.amazon_us_same_day",
        "classified_offers",
        [("classified-amazon", "d" * 64, 20)],
    )
    match_evidence = evidence_set(
        "evidence.matches.amazon.strict",
        "exact_matches",
        [("matches-amazon", "e" * 64, 100)],
    )
    fact = ComparisonFact(
        competitor_id="amazon_us_same_day",
        profile_id="strict",
        profile_label="Strict package",
        geography="exact_zip",
        comparison_metric="package_price",
        dimensions=("weight_oz", "organic"),
        evidence_ref="evidence.matches.amazon.strict",
        values={
            "matches": 100,
            "unique_geographies": 80,
            "benchmark_lower": 20,
            "competitor_lower": 75,
            "parity": 5,
            "benchmark_lower_rate": 0.2,
            "competitor_lower_rate": 0.75,
            "parity_rate": 0.05,
            "median_gap": -0.4,
        },
        segment_id="conventional_1lb",
        segment_label="Conventional / 16 oz",
        attributes={"weight_oz": 16, "organic": False},
    )

    result = AnalysisResultV2Builder(pack, code_version="test").build(
        analysis_id="analysis-v2-test",
        analysis_run_id="run-v2-test",
        generated_at="2026-08-08T12:00:00Z",
        source={
            "input_set_id": "input-v2-test",
            "kind": "historical_import",
            "collection_run_id": None,
            "matching_v2_gold_set_release_id": "8374b3c8-379c-4b19-b400-773f36a9a1e4",
            "matching_v2_gold_set_checksum": "f" * 64,
            "matching_v2_certification_coverage": {
                "authority": "matching_v2_certified_gold_set",
                "source_candidate_count": 10,
                "selected_candidate_count": 10,
                "selection_complete": True,
                "selection_coverage_rate": 1.0,
                "queue_case_count": 10,
                "certified_label_count": 8,
                "certified_comparable_count": 7,
                "certified_not_comparable_count": 1,
                "unresolved_excluded_count": 2,
                "automatic_fallback_enabled": False,
                "retailers": [
                    {
                        "competitor_retailer_id": "amazon_us_same_day",
                        "candidate_count": 10,
                        "certified_count": 8,
                        "certified_comparable_count": 7,
                        "certified_not_comparable_count": 1,
                        "unresolved_count": 2,
                    }
                ],
            },
            "observed_start": None,
            "observed_end": None,
            "sampling": False,
            "total_rows": 180,
            "source_artifact_ids": ["raw-walmart", "raw-amazon"],
        },
        benchmark_retailer="walmart_us",
        competitors=["amazon_us_same_day"],
        coverage_facts=[
            {
                "retailer_id": "walmart_us",
                "offers": 20,
                "in_scope_offers": 20,
                "in_scope_zips": 20,
                "in_scope_stores": 20,
                "evidence_ref": "evidence.classified.walmart_us",
            },
            {
                "retailer_id": "amazon_us_same_day",
                "offers": 20,
                "in_scope_offers": 20,
                "in_scope_zips": 20,
                "in_scope_stores": 0,
                "evidence_ref": "evidence.classified.amazon_us_same_day",
            },
        ],
        comparison_facts=[fact],
        data_quality_facts={
            "normalization_rejections": 0,
            "review_offers": 0,
            "zero_or_missing_price_offers": 0,
        },
        evidence_sets=[
            source_evidence,
            classified_walmart,
            classified_amazon,
            match_evidence,
        ],
        raw_source_artifact_ids=["raw-walmart", "raw-amazon"],
    )

    validate_instance(
        REPOSITORY_ROOT,
        "analysis-result-v2.schema.json",
        result,
        label="generated AnalysisResult V2",
    )
    assert result["insights"][0]["generated_by"] == "deterministic"
    assert result["recommendations"][0]["metric_refs"]
    assert result["validation"]["unsupported_numeric_claims"] == 0
    assert result["validation"]["metric_reference_coverage"] == 1
    narrative_ids = {section["id"] for section in result["narratives"]["sections"]}
    assert {
        "executive_summary",
        "coverage",
        "exact_price",
        "normalized_price",
        "segments",
        "products",
        "recommendations",
        "quality",
        "methodology",
    } <= narrative_ids
    assert all(
        section["metric_refs"] and section["evidence_refs"]
        for section in result["narratives"]["sections"]
    )


def test_executive_summary_prefers_governed_scorecard_profile_over_larger_sensitivity() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_ground_beef")
    source_evidence = evidence_set(
        "evidence.source",
        "source_manifest",
        [("raw-walmart", "a" * 64, 100), ("raw-aldi", "b" * 64, 100)],
    )
    facts = [
        ComparisonFact(
            competitor_id="aldi_us",
            profile_id="strict",
            profile_label="Strict same-ZIP and exact-package comparison",
            geography="exact_zip",
            comparison_metric="package_price",
            dimensions=("weight_lb",),
            evidence_ref="evidence.matches.aldi.strict",
            values={
                "matches": 30,
                "unique_geographies": 30,
                "benchmark_lower": 24,
                "competitor_lower": 6,
                "parity": 0,
                "benchmark_lower_rate": 0.8,
                "competitor_lower_rate": 0.2,
                "parity_rate": 0.0,
                "median_gap": 0.35,
            },
        ),
        ComparisonFact(
            competitor_id="aldi_us",
            profile_id="aldi_10mi",
            profile_label="ALDI-Walmart 10 mile sensitivity",
            geography="radius",
            comparison_metric="package_price",
            dimensions=("weight_lb",),
            evidence_ref="evidence.matches.aldi.radius",
            values={
                "matches": 20_000,
                "unique_geographies": 4_000,
                "benchmark_lower": 2_000,
                "competitor_lower": 18_000,
                "parity": 0,
                "benchmark_lower_rate": 0.1,
                "competitor_lower_rate": 0.9,
                "parity_rate": 0.0,
                "median_gap": -0.25,
            },
        ),
    ]
    result = AnalysisResultV2Builder(pack, code_version="test").build(
        analysis_id="analysis-summary-profile-test",
        analysis_run_id="run-summary-profile-test",
        generated_at="2026-08-11T12:00:00Z",
        source={
            "input_set_id": "input-summary-profile-test",
            "kind": "historical_import",
            "collection_run_id": None,
            "observed_start": None,
            "observed_end": None,
            "sampling": False,
            "total_rows": 200,
            "source_artifact_ids": ["raw-walmart", "raw-aldi"],
        },
        benchmark_retailer="walmart_us",
        competitors=["aldi_us"],
        coverage_facts=[
            {
                "retailer_id": retailer,
                "offers": 100,
                "in_scope_offers": 100,
                "in_scope_zips": 30,
                "in_scope_stores": 30,
                "evidence_ref": "evidence.source",
            }
            for retailer in ("walmart_us", "aldi_us")
        ],
        comparison_facts=facts,
        data_quality_facts={
            "normalization_rejections": 0,
            "review_offers": 0,
            "zero_or_missing_price_offers": 0,
        },
        evidence_sets=[
            source_evidence,
            evidence_set(
                "evidence.matches.aldi.strict",
                "exact_matches",
                [("strict", "c" * 64, 30)],
            ),
            evidence_set(
                "evidence.matches.aldi.radius",
                "proximity_matches",
                [("radius", "d" * 64, 20_000)],
            ),
        ],
        raw_source_artifact_ids=["raw-walmart", "raw-aldi"],
    )

    summary = next(
        section["body"]
        for section in result["narratives"]["sections"]
        if section["id"] == "executive_summary"
    )
    assert "strict same-zip and exact-package comparison" in summary
    assert "10 mile" not in summary
