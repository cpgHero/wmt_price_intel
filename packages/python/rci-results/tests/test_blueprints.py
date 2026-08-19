from __future__ import annotations

import json
from email import policy
from email.parser import BytesParser
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest

from rci_results import (
    AnalysisResultValidator,
    ArtifactRenderer,
    ReportBlueprintLoader,
    ReportViewValidator,
)
from rci_results.blueprints import ReportProjector, _segment_display_label

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
PACK_IDS = (
    "fresh_strawberries",
    "fresh_shell_eggs",
    "fresh_fluid_milk",
    "fresh_bananas",
    "fresh_ground_beef",
)


def _result() -> dict[str, object]:
    return json.loads(
        (REPOSITORY_ROOT / "examples/analysis-result-v2.ground-beef.json").read_text()
    )


@pytest.mark.parametrize("pack_id", PACK_IDS)
def test_each_product_pack_selects_a_valid_versioned_report_blueprint(pack_id: str) -> None:
    pack = json.loads((REPOSITORY_ROOT / f"product-packs/{pack_id}.json").read_text())
    reference = pack["reporting"]["report_blueprint"]
    blueprint = ReportBlueprintLoader(REPOSITORY_ROOT).load(reference["id"])

    assert blueprint.version == reference["version"]
    assert blueprint.product_pack_id == pack_id
    assert {profile["artifact_type"] for profile in blueprint.document["artifact_profiles"]} == {
        "html",
        "xlsx",
        "leadership_email",
        "audit_zip",
    }


def test_v2_contract_resolves_every_metric_and_evidence_reference() -> None:
    result = _result()

    validated = AnalysisResultValidator(REPOSITORY_ROOT).validate(result)

    assert validated == result


def test_report_view_contract_validates_canonical_delivery_fixture() -> None:
    document = json.loads((REPOSITORY_ROOT / "examples/report-view.ground-beef.json").read_text())

    assert ReportViewValidator(REPOSITORY_ROOT).validate(document) == document


def test_evidence_retailer_annotation_prefers_exact_ids_and_safe_unique_roots() -> None:
    result = {
        "benchmark_retailer": "walmart_us",
        "competitors": ["walmart_mx", "amazon_us_same_day"],
    }

    assert (
        ReportProjector._evidence_retailer_id(
            result, {"evidence_set_id": "evidence-classified-walmart_mx"}
        )
        == "walmart_mx"
    )
    assert (
        ReportProjector._evidence_retailer_id(
            result, {"evidence_set_id": "evidence-classified-amazon"}
        )
        == "amazon_us_same_day"
    )
    assert (
        ReportProjector._evidence_retailer_id(
            result, {"evidence_set_id": "evidence-classified-walmart"}
        )
        is None
    )


def test_blueprint_drives_report_view_and_all_artifact_sections() -> None:
    result = _result()
    renderer = ArtifactRenderer(REPOSITORY_ROOT)

    view = renderer.report_view(result)
    section_titles = [section["title"] for section in view["sections"]]
    assert section_titles == [
        "Executive Summary",
        "Decision KPIs",
        "Geographic Footprint",
        "Exact Package Price Position",
        "Normalized Price-per-Pound View",
        "10-Mile Validation",
        "Products and Assortment",
        "Assortment Intelligence",
        "Recommended Actions",
        "Data Quality",
        "Methodology & Caveats",
    ]
    assert [(group["id"], group["label"]) for group in view["groups"]] == [
        ("overview", "Overview"),
        ("price-segments", "Price & Segments"),
        ("products", "Products"),
        ("geography", "Geography"),
        ("assortment", "Assortment"),
        ("match-review", "Match Review"),
        ("quality-methodology", "Quality & Methodology"),
        ("exports", "Exports"),
    ]
    assert view["retailer_scope"] == {
        "benchmark": {"id": "walmart_us", "name": "Walmart (US)"},
        "competitors": [
            {"id": "aldi_us", "name": "ALDI"},
            {"id": "amazon_us_same_day", "name": "Amazon Same Day (US)"},
        ],
    }
    assert {(row["competitor_id"], row["profile_id"]) for row in view["retailer_scorecards"]} == {
        (competitor, profile)
        for competitor in ("aldi_us", "amazon_us_same_day")
        for profile in (
            "strict_exact_package",
            "normalized_price_per_lb",
            "strict_within_10mi",
        )
    }
    assert view["schema_version"] == "1.1.0"
    assert view["comparison_bases"][0]["profile_id"] == "strict_exact_package"
    assert view["comparison_bases"][0]["population_basis"] == "relationship_resolved_products"
    assert view["retailer_scorecards"][0]["basis_status"] == "preferred"
    assert view["retailer_scorecards"][0]["dominant_outcome"] == "competitor_lower"
    assert view["retailer_scorecards"][0]["comparison_metric"] == "package_price"
    assert view["retailer_scorecards"][0]["price_unit"] == "USD/package"
    assert view["retailer_scorecards"][0]["median_gap_statistic"] == "paired_median_gap"
    assert view["retailer_scorecards"][0]["minimum_observations"] == 25
    assert view["retailer_scorecards"][0]["minimum_geographies"] == 25
    assert view["retailer_scorecards"][0]["status"] == "limited_evidence"
    assert "0 of 25 required geographies" in view["retailer_scorecards"][0]["readiness_reason"]
    assert view["report_readiness"]["status"] == "limited"
    assert view["retailer_scorecards"][0]["matches"] == 9049
    assert view["retailer_scorecards"][0]["competitor_lower_rate"] == pytest.approx(0.8414189413)
    amazon_strict = next(
        row
        for row in view["retailer_scorecards"]
        if row["competitor_id"] == "amazon_us_same_day"
        and row["profile_id"] == "strict_exact_package"
    )
    assert amazon_strict["benchmark_lower_rate"] == pytest.approx(0.9363920751)
    product_section = next(
        section for section in view["sections"] if section["kind"] == "product_table"
    )
    amazon_record = next(
        row
        for row in product_section["records"]
        if row["evidence_set_id"] == "evidence-classified-amazon"
    )
    assert amazon_record["_competitor_id"] == "amazon_us_same_day"
    walmart_evidence = next(
        row
        for row in product_section["evidence_sets"]
        if row["evidence_set_id"] == "evidence-classified-walmart"
    )
    assert walmart_evidence["_retailer_id"] == "walmart_us"

    html = renderer.render(result, "html")
    assert html.body.startswith(b"<!doctype html>")
    assert b"Normalized Price-per-Pound View" in html.body
    assert b"ALDI pressure is concentrated" in html.body
    assert b"Decision KPIs" not in html.body
    assert b">Overview</a>" in html.body
    assert b"Decision readiness" in html.body
    assert b"Product relationship review" in html.body
    assert b"Export manifest" in html.body
    assert b"Retailer scorecard" in html.body
    assert b"id=report-competitor" in html.body
    assert b"data-competitor-id='aldi_us'" in html.body
    assert b"data-retailer-title='Leadership answer'" in html.body
    assert b"node.textContent=`${retailer.name}: ${node.dataset.retailerTitle}`" in html.body
    assert b"Walmart (US)" in html.body

    workbook = renderer.render(result, "xlsx")
    with ZipFile(BytesIO(workbook.body)) as archive:
        workbook_xml = archive.read("xl/workbook.xml")
        for name in (
            b"Executive Summary",
            b"Leadership Narrative",
            b"Metrics",
            b"Retailer Scorecard",
            b"Price Comparisons",
            b"Segment Analysis",
            b"Geography",
            b"Data Quality",
            b"Methodology",
            b"Report Readiness",
            b"Comparison Bases",
            b"Product Decisions",
            b"Suppressed Decisions",
            b"Match Relationships",
            b"Match Governance",
            b"Artifact Manifest",
        ):
            assert name in workbook_xml
        shared_strings = archive.read("xl/sharedStrings.xml")
        assert b"Reference Retailer" in shared_strings
        assert b"Competitor Lower Share" in shared_strings
        assert b"Paired Median Price Position" in shared_strings

    email = BytesParser(policy=policy.default).parsebytes(
        renderer.render(result, "leadership_email").body
    )
    assert "Fresh Ground Beef" in str(email["Subject"])
    assert "Prioritize" in email.get_body(preferencelist=("plain",)).get_content()
    assert "Retailer scorecard" in email.get_body(preferencelist=("plain",)).get_content()
    assert "Report integrity" in email.get_body(preferencelist=("plain",)).get_content()
    attachments = list(email.iter_attachments())
    assert [attachment.get_filename() for attachment in attachments] == [
        "ground-beef-2026-08-07-example-report.html"
    ]
    assert attachments[0].get_payload(decode=True) == html.body

    audit = renderer.render(result, "audit_zip")
    with ZipFile(BytesIO(audit.body)) as archive:
        assert "analysis-result.json" in archive.namelist()
        assert json.loads(archive.read("analysis-result.json")) == result


def test_report_readiness_blocks_ambiguous_relationship_groups() -> None:
    view = ArtifactRenderer(REPOSITORY_ROOT).report_view(
        _result(),
        presentation_context={
            "match_relationships": [],
            "ambiguous_match_groups": [
                {
                    "candidate_group_id": "candidate-1",
                    "competitor_id": "aldi_us",
                    "candidates": [],
                }
            ],
            "suppressed_product_decisions": [],
        },
    )

    assert view["match_governance"]["ambiguous"] == 1
    assert view["report_readiness"]["status"] == "review_required"
    assert view["report_readiness"]["blocking_reasons"][0]["code"] == (
        "ambiguous_product_relationships"
    )


def test_interactive_report_view_compacts_audit_only_location_scopes() -> None:
    view = ArtifactRenderer(REPOSITORY_ROOT).report_view(
        _result(),
        presentation_context={
            "match_candidates": [
                {
                    "id": "candidate-1",
                    "benchmark_location_scope_keys": ["walmart_us|72712|1"],
                    "excluded_benchmark_location_scope_keys": ["walmart_us|72712|2"],
                }
            ],
            "match_relationships": [
                {
                    "relationship_id": "relationship-1",
                    "competitor_id": "aldi_us",
                    "status": "confirmed",
                    "eligible_profile_ids": ["compatible"],
                    "benchmark_location_scope_keys": ["walmart_us|72712|1"],
                    "excluded_benchmark_location_scope_keys": ["walmart_us|72712|2"],
                }
            ],
            "assortment_analysis": {
                "retailers": [
                    {
                        "retailer": "walmart_us",
                        "products": [
                            {
                                "product_id": "100",
                                "canonical_product_id": "walmart_us:100",
                                "name": "Product 100",
                                "brand": "Great Value",
                                "brand_type": "private_label",
                                "brand_origin": "retailer_pack",
                                "brand_status": "approved",
                                "image_url": None,
                                "observed_locations": 2,
                                "observed_zipcodes": 2,
                                "location_scope_keys": [
                                    "walmart_us|72712|1",
                                    "walmart_us|72712|2",
                                ],
                                "pdp_details": {"description_full": "large audit payload"},
                            }
                        ],
                    }
                ]
            },
        },
    )

    assert "benchmark_location_scope_keys" not in view["match_candidates"][0]
    assert view["match_relationships"] == [
        {
            "relationship_id": "relationship-1",
            "competitor_id": "aldi_us",
            "status": "confirmed",
            "eligible_profile_ids": ["compatible"],
        }
    ]
    product = view["assortment_analysis"]["retailers"][0]["products"][0]
    assert product == {
        "product_id": "100",
        "canonical_product_id": "walmart_us:100",
        "name": "Product 100",
        "brand": "Great Value",
        "brand_type": "private_label",
        "brand_origin": "retailer_pack",
        "brand_status": "approved",
        "image_url": None,
        "observed_locations": 2,
        "observed_zipcodes": 2,
    }


def test_sparse_suppressed_product_decisions_warn_without_blocking_report() -> None:
    view = ArtifactRenderer(REPOSITORY_ROOT).report_view(
        _result(),
        presentation_context={
            "match_relationships": [],
            "ambiguous_match_groups": [],
            "suppressed_product_decisions": [
                {
                    "id": "sparse-pair",
                    "benchmark_product_id": "100",
                    "competitor_product_id": "200",
                    "competitor": "aldi_us",
                    "suppression_reasons": ["Only 8 retained observations; 25 are required"],
                }
            ],
        },
    )

    assert view["report_readiness"]["status"] == "limited"
    assert view["report_readiness"]["blocking_reasons"] == []
    assert view["report_readiness"]["warnings"][0]["code"] == (
        "sparse_product_decisions_suppressed"
    )


def test_review_threshold_suppression_warns_without_blocking_report() -> None:
    view = ArtifactRenderer(REPOSITORY_ROOT).report_view(
        _result(),
        presentation_context={
            "match_relationships": [],
            "ambiguous_match_groups": [],
            "suppressed_product_decisions": [
                {
                    "id": "large-gap-pair",
                    "benchmark_product_id": "100",
                    "competitor_product_id": "200",
                    "competitor": "amazon_us_same_day",
                    "suppression_reasons": [
                        "Only 6 retained observations; 25 are required",
                        "Paired median price difference exceeds the Product Pack review threshold",
                    ],
                }
            ],
        },
    )

    assert view["report_readiness"]["status"] == "limited"
    assert view["report_readiness"]["blocking_reasons"] == []
    assert view["report_readiness"]["warnings"][0]["code"] == (
        "sparse_product_decisions_suppressed"
    )


def test_parity_is_a_first_class_dominant_outcome() -> None:
    assert ReportProjector._dominant_outcome(0.0, 0.0, 1.0) == "parity"
    assert ReportProjector._dominant_outcome(0.4, 0.4, 0.2) == "competitor_lower"


def test_leadership_html_prioritizes_governed_narrative_and_visible_comparisons() -> None:
    result = _result()
    result["insights"] = [
        {
            "id": f"insight-{index}",
            "title": f"Decision title {index}",
            "summary": f"Long supporting summary {index}",
            "severity": "medium",
            "business_impact": "Act on the governed signal.",
            "metric_refs": ["aldi-exact-matches"],
            "evidence_refs": ["evidence-exact-aldi"],
            "confidence": "high",
            "generated_by": "deterministic",
        }
        for index in range(7)
    ]

    html = ArtifactRenderer(REPOSITORY_ROOT).render(result, "html").body.decode()

    assert "Decision title 0" not in html
    assert "ALDI pressure is concentrated" in html
    assert "<figure class=comparison-chart>" in html
    assert "View supporting detail" in html
    assert "All comparable items" in html


def test_report_view_humanizes_catalog_and_product_pack_labels() -> None:
    result = _result()
    result["metrics"].append(
        {
            **result["metrics"][0],
            "metric_id": "source.total_rows",
            "name": (
                "aldi_us Lean Pct: 80 / Fat Pct: 20 / Weight Lb: 2.25 / "
                "Organic: False / Grass Fed: False / Premium Tier: standard matches"
            ),
        }
    )

    view = ArtifactRenderer(REPOSITORY_ROOT).report_view(result)
    names = [str(metric["name"]) for section in view["sections"] for metric in section["metrics"]]
    rendered = " ".join(names)

    assert "aldi_us" not in rendered
    assert "Lean Pct:" not in rendered
    assert "ALDI 80% lean / 20% fat / 2.25 lb / non-organic / non-grass-fed" in rendered


def test_segment_display_label_humanizes_units_and_boolean_attributes() -> None:
    pack = json.loads((REPOSITORY_ROOT / "product-packs/fresh_fluid_milk.json").read_text())

    label = _segment_display_label(
        {
            "segment_id": "milk-segment",
            "label": "128 fl_oz / 1% / non-organic / non-lactose_free",
            "attributes": {
                "volume_oz": 128,
                "fat_type": "1%",
                "organic": False,
                "lactose_free": False,
            },
        },
        pack,
    )

    assert label == "128 fl oz · 1% · non-organic · non-lactose-free"


def test_comparison_table_projects_matched_geography_count() -> None:
    result = _result()
    metric_id = "aldi-exact-unique-geographies"
    result["metrics"].append(
        {
            "metric_id": metric_id,
            "name": "ALDI exact matched geographies",
            "value": 41,
            "unit": "locations",
            "method": "distinct exact-match geography keys",
            "evidence_ref": "evidence-exact-aldi",
        }
    )
    result["comparisons"][0]["metric_refs"].append(metric_id)

    view = ArtifactRenderer(REPOSITORY_ROOT).report_view(result)
    price_section = next(
        section for section in view["sections"] if section["kind"] == "price_position"
    )

    assert price_section["records"][0]["matched geographies"] == "41"
    assert price_section["records"][0]["_matched_geographies"] == 41.0
    assert price_section["records"][0]["_dominant_outcome"] == "competitor_lower"


def test_comparison_table_retains_segment_attributes_for_product_drilldown() -> None:
    result = _result()
    result["comparisons"][0]["segment_id"] = "organic_grass_fed_85_15_1lb"

    view = ArtifactRenderer(REPOSITORY_ROOT).report_view(result)
    price_section = next(
        section for section in view["sections"] if section["kind"] == "price_position"
    )

    assert price_section["records"][0]["_segment_attributes"] == {
        "lean_pct": 85,
        "package_weight_lb": 1,
        "organic": True,
        "grass_fed": True,
    }


def test_report_view_exposes_product_pack_cohort_guidance() -> None:
    view = ArtifactRenderer(REPOSITORY_ROOT).report_view(_result())

    assert view["product_pack"]["cohort_dimensions"] == [
        "Lean Pct",
        "Fat Pct",
        "Weight Lb",
        "Organic",
        "Grass Fed",
        "Premium Tier",
    ]
    assert view["product_pack"]["minimum_cohort_geographies"] == 25


def test_retailer_scorecard_contract_scales_to_thirteen_competitors() -> None:
    result = _result()
    competitors = [f"retailer_{index}_us" for index in range(13)]
    result["competitors"] = competitors
    result["coverage"] = []
    result["metrics"] = []
    result["comparisons"] = []
    for index, competitor in enumerate(competitors):
        matches_id = f"retailer-{index}-matches"
        reference_rate_id = f"retailer-{index}-benchmark-lower-rate"
        competitor_rate_id = f"retailer-{index}-competitor-lower-rate"
        result["metrics"].extend(
            [
                {"metric_id": matches_id, "value": 1000 - index, "unit": "matches"},
                {"metric_id": reference_rate_id, "value": 0.6, "unit": "rate"},
                {"metric_id": competitor_rate_id, "value": 0.4, "unit": "rate"},
            ]
        )
        result["comparisons"].append(
            {
                "comparison_id": f"retailer-{index}-strict",
                "competitor_id": competitor,
                "profile_id": "strict_exact_package",
                "segment_id": "all",
                "metric_refs": [matches_id, reference_rate_id, competitor_rate_id],
                "evidence_refs": [],
            }
        )
    product_pack = json.loads(
        (REPOSITORY_ROOT / "product-packs/fresh_ground_beef.json").read_text()
    )

    scorecards = ReportProjector().retailer_scorecards(result, product_pack)

    assert len(scorecards) == 39
    strict_scorecards = [row for row in scorecards if row["profile_id"] == "strict_exact_package"]
    assert [row["competitor_id"] for row in strict_scorecards] == competitors
    assert all(row["benchmark_lower_rate"] == 0.6 for row in strict_scorecards)
    assert all(row["competitor_lower_rate"] == 0.4 for row in strict_scorecards)
    assert all(row["parity_rate"] == pytest.approx(0.0) for row in strict_scorecards)
    assert all(row["status"] == "limited_evidence" for row in scorecards)
    assert all("required geographies" in row["readiness_reason"] for row in strict_scorecards)


def test_retailer_scorecards_project_every_available_comparison_basis() -> None:
    result = _result()
    result["comparison_modes"].append(
        {
            "profile_id": "compatible",
            "label": "Compatible specification",
            "geography": "exact_zip",
            "comparison_metric": "package_price",
            "dimensions": [],
        }
    )
    result["metrics"].extend(
        [
            {"metric_id": "aldi-compatible.matches", "value": 100, "unit": "matches"},
            {
                "metric_id": "aldi-compatible.unique_geographies",
                "value": 80,
                "unit": "locations",
            },
            {
                "metric_id": "aldi-compatible.benchmark_lower_rate",
                "value": 0.4,
                "unit": "rate",
            },
            {
                "metric_id": "aldi-compatible.competitor_lower_rate",
                "value": 0.5,
                "unit": "rate",
            },
            {"metric_id": "aldi-compatible.parity_rate", "value": 0.1, "unit": "rate"},
        ]
    )
    result["comparisons"].append(
        {
            "comparison_id": "aldi-compatible-all",
            "competitor_id": "aldi_us",
            "profile_id": "compatible",
            "segment_id": "all",
            "metric_refs": [
                "aldi-compatible.matches",
                "aldi-compatible.unique_geographies",
                "aldi-compatible.benchmark_lower_rate",
                "aldi-compatible.competitor_lower_rate",
                "aldi-compatible.parity_rate",
            ],
            "evidence_refs": [],
        }
    )
    product_pack = json.loads(
        (REPOSITORY_ROOT / "product-packs/fresh_ground_beef.json").read_text()
    )

    scorecards = ReportProjector().retailer_scorecards(result, product_pack)

    aldi_profiles = {
        row["profile_id"]: row for row in scorecards if row["competitor_id"] == "aldi_us"
    }
    assert set(aldi_profiles) == {
        "strict_exact_package",
        "normalized_price_per_lb",
        "strict_within_10mi",
        "compatible",
    }
    assert aldi_profiles["compatible"]["matches"] == 100
    assert aldi_profiles["compatible"]["evidence_state"] == "reported"


def test_retailer_scorecards_keep_missing_basis_as_an_explicit_zero_state() -> None:
    result = _result()
    result["comparison_modes"].append(
        {
            "profile_id": "compatible",
            "label": "Compatible specification",
            "geography": "exact_zip",
            "comparison_metric": "package_price",
            "dimensions": [],
        }
    )
    product_pack = json.loads(
        (REPOSITORY_ROOT / "product-packs/fresh_ground_beef.json").read_text()
    )

    scorecards = ReportProjector().retailer_scorecards(result, product_pack)
    profiles = {row["profile_id"]: row for row in scorecards if row["competitor_id"] == "aldi_us"}

    assert set(profiles) == {
        "strict_exact_package",
        "normalized_price_per_lb",
        "strict_within_10mi",
        "compatible",
    }
    assert profiles["compatible"]["matches"] is None
    assert profiles["compatible"]["evidence_state"] == "no_governed_relationships"
    assert profiles["compatible"]["status"] == "limited_evidence"


def test_certified_relationship_without_price_evidence_is_not_labeled_unmatched() -> None:
    result = _result()
    result["comparison_modes"].append(
        {
            "profile_id": "compatible",
            "label": "Compatible specification",
            "geography": "exact_zip",
            "comparison_metric": "package_price",
            "dimensions": [],
        }
    )
    result["source"]["matching_v2_certification_coverage"] = {
        "retailers": [
            {
                "competitor_retailer_id": "aldi_us",
                "certified_comparable_count": 2,
            }
        ]
    }
    product_pack = json.loads(
        (REPOSITORY_ROOT / "product-packs/fresh_ground_beef.json").read_text()
    )

    scorecards = ReportProjector().retailer_scorecards(result, product_pack)
    profiles = {row["profile_id"]: row for row in scorecards if row["competitor_id"] == "aldi_us"}

    assert profiles["compatible"]["matches"] is None
    assert profiles["compatible"]["evidence_state"] == "no_admissible_observations"
    assert "Certified comparable products exist" in profiles["compatible"]["readiness_reason"]


def test_matching_v2_incomplete_certification_blocks_report_readiness() -> None:
    result = _result()
    result["source"]["matching_v2_certification_coverage"] = {
        "authority": "matching_v2_certified_gold_set",
        "queue_case_count": 100,
        "certified_label_count": 60,
        "certified_comparable_count": 20,
        "certified_not_comparable_count": 40,
        "unresolved_excluded_count": 40,
        "automatic_fallback_enabled": False,
    }

    view = ArtifactRenderer(REPOSITORY_ROOT).report_view(result)

    assert view["certification_coverage"]["unresolved_excluded_count"] == 40
    assert view["report_readiness"]["status"] == "review_required"
    assert any(
        reason["code"] == "matching_v2_certification_incomplete"
        for reason in view["report_readiness"]["blocking_reasons"]
    )


def test_zero_scorecard_reconciles_to_governed_product_evidence() -> None:
    result = _result()
    result["competitors"] = ["safeway_us"]
    result["comparisons"] = []
    result["comparison_modes"] = [
        {
            "profile_id": "strict",
            "label": "Governed product relationships",
            "geography": "exact_zip",
            "comparison_metric": "price_per_dozen",
            "dimensions": [],
        }
    ]
    view = ArtifactRenderer(REPOSITORY_ROOT).report_view(
        result,
        presentation_context={
            "product_decisions": [
                {
                    "id": "relationship-decision",
                    "competitor": "safeway_us",
                    "benchmark_product_id": "walmart-eggs",
                    "competitor_product_id": "safeway-eggs",
                    "profile_id": "strict",
                    "comparison_metric": "price_per_dozen",
                    "matches": 40,
                    "geographies": 40,
                    "benchmark_lower": 30,
                    "competitor_lower": 5,
                    "parity": 5,
                    "median_gap": 0.5,
                    "qa_status": "ready",
                }
            ]
        },
    )

    scorecard = view["retailer_scorecards"][0]
    assert scorecard["basis_status"] == "fallback"
    assert scorecard["comparison_lens"] == "Governed product relationships"
    assert scorecard["comparison_metric"] == "price_per_dozen"
    assert scorecard["matches"] == 40
    assert scorecard["matched_geographies"] == 40
    assert scorecard["benchmark_lower_rate"] == 0.75
    assert scorecard["competitor_lower_rate"] == 0.125
    assert scorecard["parity_rate"] == 0.125
    assert scorecard["status"] == "ready"


def test_retailer_scorecard_is_limited_when_outcome_shares_do_not_reconcile() -> None:
    result = _result()
    result["metrics"].append(
        {
            "metric_id": "aldi-benchmark-lower-rate",
            "name": "ALDI benchmark lower rate",
            "value": 0.2,
            "unit": "rate",
            "method": "test fixture",
            "evidence_ref": "evidence-exact-aldi",
        }
    )
    result["comparisons"][0]["metric_refs"].append("aldi-benchmark-lower-rate")
    result["metrics"].append(
        {
            "metric_id": "aldi-parity-rate",
            "name": "ALDI parity rate",
            "value": 0.25,
            "unit": "rate",
            "method": "test fixture",
            "evidence_ref": "evidence-exact-aldi",
        }
    )
    result["comparisons"][0]["metric_refs"].append("aldi-parity-rate")
    result["metrics"].append(
        {
            "metric_id": "aldi-unique-geographies",
            "name": "ALDI unique geographies",
            "value": 100,
            "unit": "locations",
            "method": "test fixture",
            "evidence_ref": "evidence-exact-aldi",
        }
    )
    result["comparisons"][0]["metric_refs"].append("aldi-unique-geographies")
    product_pack = json.loads(
        (REPOSITORY_ROOT / "product-packs/fresh_ground_beef.json").read_text()
    )

    scorecard = ReportProjector().retailer_scorecards(result, product_pack)[0]

    assert scorecard["status"] == "limited_evidence"
    assert "outcome shares total" in scorecard["readiness_reason"]
    view = ArtifactRenderer(REPOSITORY_ROOT).report_view(result)
    assert view["report_readiness"]["status"] == "review_required"
    assert view["report_readiness"]["blocking_reasons"][0]["code"] == (
        "price_outcomes_do_not_reconcile"
    )


def test_leadership_html_renders_analysis_linked_product_map() -> None:
    result = _result()
    context = {
        "map_points": [
            {
                "id": "point-1",
                "label": "Benchmark ground beef",
                "latitude": 36.37,
                "longitude": -94.21,
                "benchmark_product_id": "100",
                "benchmark_product_name": "Benchmark ground beef",
                "outcome": "competitor_lower",
                "zipcode": "72712",
                "value_label": "Competitor lower · signed gap $-0.50",
            }
        ]
    }

    html = (
        ArtifactRenderer(REPOSITORY_ROOT)
        .render(
            result,
            "html",
            presentation_context=context,
        )
        .body.decode()
    )

    assert "Analysis-linked geographic price outcomes" in html
    assert "All mapped Walmart (US) products" in html
    assert '"benchmark_product_id":"100"' in html
    assert "class=state-layer" in html
    assert "</rect><g class=state-layer>" in html
    assert html.count("<path d=") > 40


def test_leadership_html_links_quality_counts_to_search_observations() -> None:
    result = _result()
    context = {
        "quality_observations": [
            {
                "issue": "Missing or zero search price",
                "retailer": "walmart_us",
                "product": "Fresh Ground Beef",
                "product_id": "abc-123",
                "price": None,
                "zipcode": "00501",
                "store": "0042",
                "reason": "Search result did not contain a positive USD price",
                "source_url": "https://example.test/product/abc-123",
            }
        ]
    }

    html = (
        ArtifactRenderer(REPOSITORY_ROOT)
        .render(result, "html", presentation_context=context)
        .body.decode()
    )

    assert "Source search records behind the quality counts" in html
    assert "Fresh Ground Beef" in html
    assert "Missing or zero search price" in html
    assert "Open result" in html


def test_shareable_html_matches_app_groups_and_product_evidence_contract() -> None:
    result = _result()
    decision = {
        "id": "pair-1",
        "priority": "attention",
        "benchmark_product_id": "walmart-80-20",
        "benchmark_product_name": "Walmart 80/20 Ground Beef",
        "benchmark_image_url": "https://example.test/walmart.jpg",
        "competitor": "aldi_us",
        "competitor_product_id": "aldi-80-20",
        "competitor_product_name": "ALDI 80/20 Ground Beef",
        "competitor_image_url": "https://example.test/aldi.jpg",
        "median_gap": -1.8,
        "median_benchmark_price": 7.99,
        "median_competitor_price": 6.19,
        "geographies": 42,
        "evidence_summary": {
            "benchmark_store_observations": 51,
            "matched_zip_markets": 42,
        },
    }
    context = {
        "product_decisions": [decision],
        "assortment_analysis": {
            "benchmark_retailer": "walmart_us",
            "retailers": [
                {"retailer": "walmart_us", "distinct_products": 8},
                {"retailer": "aldi_us", "distinct_products": 6},
            ],
            "comparisons": [
                {
                    "competitor": "aldi_us",
                    "product_relationships": 4,
                    "benchmark_only_products": 4,
                    "competitor_whitespace_products": 2,
                    "geography": {
                        "shared_zipcodes": 10,
                        "benchmark_broader_zipcodes": 6,
                        "competitor_broader_zipcodes": 3,
                        "parity_zipcodes": 1,
                    },
                    "key_points": ["Four governed product relationships were observed."],
                    "top_benchmark_only": [],
                    "top_competitor_whitespace": [],
                }
            ],
        },
        "product_evidence": {
            "pair-1": {
                "comparison_grain": "Exact package and ZIP",
                "rows": [
                    {
                        "zipcode": "00501",
                        "benchmark_store": "0042",
                        "benchmark_price": 7.99,
                        "competitor_store": "479-149",
                        "competitor_price": 6.19,
                        "outcome": "competitor_lower",
                    }
                ],
            }
        },
    }

    view = ArtifactRenderer(REPOSITORY_ROOT).report_view(
        result,
        presentation_context=context,
    )

    assert view["product_evidence"] == context["product_evidence"]

    html = (
        ArtifactRenderer(REPOSITORY_ROOT)
        .render(result, "html", presentation_context=context)
        .body.decode()
    )

    expected_groups = [
        "Overview",
        "Price &amp; Segments",
        "Products",
        "Geography",
        "Assortment",
        "Match Review",
        "Quality &amp; Methodology",
        "Exports",
    ]
    assert all(f">{label}</a>" in html for label in expected_groups)
    assert "Product-level price evidence" in html
    assert "Walmart 80/20 Ground Beef" in html
    assert "ALDI 80/20 Ground Beef" in html
    assert "ALDI is $1.80 lower at the median match" in html
    assert "View exact store evidence" in html
    assert "00501" in html
    assert "Product relationship and whitespace scorecard" in html
    assert "Four governed product relationships were observed." in html
    assert "Decision readiness" in html
    assert "Product relationship review" in html
    assert "Export manifest" in html


def test_artifacts_reconcile_to_the_same_immutable_result_checksum() -> None:
    result = _result()
    renderer = ArtifactRenderer(REPOSITORY_ROOT)
    checksum = str(result["provenance"]["final_result_checksum_sha256"])  # type: ignore[index]
    checksum_bytes = checksum.encode()

    html = renderer.render(result, "html")
    assert checksum_bytes in html.body
    assert b"data-result-checksum" in html.body

    workbook = renderer.render(result, "xlsx")
    with ZipFile(BytesIO(workbook.body)) as archive:
        workbook_text = b"".join(
            archive.read(name) for name in archive.namelist() if name.endswith(".xml")
        )
        assert checksum_bytes in workbook_text

    email = BytesParser(policy=policy.default).parsebytes(
        renderer.render(result, "leadership_email").body
    )
    assert str(email["X-RCI-Result-Checksum"]) == checksum
    assert checksum in email.get_body(preferencelist=("plain",)).get_content()

    audit = renderer.render(result, "audit_zip")
    with ZipFile(BytesIO(audit.body)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["result_checksum_sha256"] == checksum


def test_artifact_specific_report_view_uses_blueprint_section_profile() -> None:
    result = _result()
    renderer = ArtifactRenderer(REPOSITORY_ROOT)
    email_view = renderer.report_view(result, artifact_type="leadership_email")

    assert [section["id"] for section in email_view["sections"]] == [
        "executive_summary",
        "coverage",
        "exact_price",
        "normalized_price",
        "proximity",
        "products",
        "assortment_analysis",
        "recommendations",
        "quality",
        "methodology",
    ]
