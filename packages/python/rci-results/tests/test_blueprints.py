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

    workbook = renderer.render(result, "xlsx")
    with ZipFile(BytesIO(workbook.body)) as archive:
        workbook_xml = archive.read("xl/workbook.xml")
        for name in (
            b"Executive Summary",
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
    assert "Prioritize" in email.get_content()

    audit = renderer.render(result, "audit_zip")
    with ZipFile(BytesIO(audit.body)) as archive:
        assert "analysis-result.json" in archive.namelist()
        assert json.loads(archive.read("analysis-result.json")) == result


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
    assert checksum in email.get_content()

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
        "recommendations",
        "methodology",
    ]
