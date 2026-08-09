from __future__ import annotations

from pathlib import Path

from rci_analytics import AnalysisResultV2Builder, ComparisonFact, ProductPackLoader, evidence_set
from rci_contracts import validate_instance

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


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
