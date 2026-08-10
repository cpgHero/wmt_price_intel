from __future__ import annotations

import json
from email import policy
from email.parser import BytesParser
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest

from rci_results import AnalysisResultValidator, ArtifactRenderer, ReportBlueprintLoader

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
        "Recommended Actions",
        "Data Quality",
        "Methodology & Caveats",
    ]

    html = renderer.render(result, "html")
    assert html.body.startswith(b"<!doctype html>")
    assert b"Normalized Price-per-Pound View" in html.body
    assert b"ALDI pressure is concentrated" in html.body
    assert b"Competitive Scorecard" in html.body

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
            b"Artifact Manifest",
        ):
            assert name in workbook_xml

    email = BytesParser(policy=policy.default).parsebytes(
        renderer.render(result, "leadership_email").body
    )
    assert "Fresh Ground Beef" in str(email["Subject"])
    assert "Prioritize" in email.get_body(preferencelist=("plain",)).get_content()
    attachments = list(email.iter_attachments())
    assert [attachment.get_filename() for attachment in attachments] == [
        "ground-beef-2026-08-07-example-report.html"
    ]
    assert attachments[0].get_payload(decode=True) == html.body

    audit = renderer.render(result, "audit_zip")
    with ZipFile(BytesIO(audit.body)) as archive:
        assert "analysis-result.json" in archive.namelist()
        assert json.loads(archive.read("analysis-result.json")) == result


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
            "evidence_ref": "evidence.matches.aldi",
        }
    )
    result["comparisons"][0]["metric_refs"].append(metric_id)

    view = ArtifactRenderer(REPOSITORY_ROOT).report_view(result)
    price_section = next(
        section for section in view["sections"] if section["kind"] == "price_position"
    )

    assert price_section["records"][0]["matched geographies"] == "41"


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

    assert "Benchmark product price map" in html
    assert "All mapped benchmark products" in html
    assert "data-product='100'" in html
    assert "PDP enrichment supplies product reference detail" in html


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

    assert "View source search observations" in html
    assert "Fresh Ground Beef" in html
    assert "Missing or zero search price" in html


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
        "recommendations",
        "quality",
        "methodology",
    ]
