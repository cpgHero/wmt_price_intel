from __future__ import annotations

import copy
import hashlib
import json
from email import policy
from email.parser import BytesParser
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest

from rci_contracts import ContractError
from rci_results import (
    AnalysisResultService,
    AnalysisResultValidator,
    ArtifactRenderer,
    InMemoryReportObjectStore,
    InMemoryResultsRepository,
    S3ReportObjectStore,
)
from rci_results.models import ArtifactPayload

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def _result() -> dict[str, object]:
    return json.loads(
        (REPOSITORY_ROOT / "examples" / "analysis-result.strawberries.json").read_text()
    )


def _service() -> tuple[AnalysisResultService, InMemoryReportObjectStore]:
    store = InMemoryReportObjectStore()
    return (
        AnalysisResultService(
            InMemoryResultsRepository(),
            AnalysisResultValidator(REPOSITORY_ROOT),
            store,
        ),
        store,
    )


def test_analysis_result_contract_rejects_missing_authoritative_sections() -> None:
    invalid = _result()
    invalid.pop("comparisons")

    with pytest.raises(ContractError, match="comparisons"):
        AnalysisResultValidator(REPOSITORY_ROOT).validate(invalid)


async def test_result_publication_is_idempotent_and_immutable() -> None:
    service, _ = _service()
    result = _result()

    first = await service.publish(result)
    result["analysis_id"] = "mutated-after-publish"
    stored = await service.get(first.analysis_id)
    assert stored.result["analysis_id"] == first.analysis_id
    stored.result["analysis_id"] = "mutated-return-value"
    assert (await service.get(first.analysis_id)).result["analysis_id"] == first.analysis_id
    assert (await service.get_by_collection_run(first.collection_run_id)).id == first.id
    result = _result()
    assert await service.publish(result) == first
    changed = copy.deepcopy(result)
    changed["comparisons"][0]["matches"] = 1  # type: ignore[index]
    with pytest.raises(ValueError, match="immutable"):
        await service.publish(changed)
    different_id = copy.deepcopy(result)
    different_id["analysis_id"] = "different-id-for-the-same-source-run"
    with pytest.raises(ValueError, match="collection run and Product Pack"):
        await service.publish(different_id)


def test_renderers_preserve_result_and_create_auditable_formats() -> None:
    result = _result()
    original = copy.deepcopy(result)
    renderer = ArtifactRenderer()

    html = renderer.render(result, "html")
    assert html.renderer_version == renderer.version == "2.6.0"
    assert html.body.startswith(b"<!doctype html>")
    assert b"0.99964" in html.body

    workbook = renderer.render(result, "xlsx")
    assert workbook.body.startswith(b"PK")
    assert renderer.render(result, "xlsx").body == workbook.body
    with ZipFile(BytesIO(workbook.body)) as archive:
        workbook_xml = archive.read("xl/workbook.xml")
        assert b"Executive Summary" in workbook_xml
        assert b"Comparisons" in workbook_xml
        assert b"Data Quality" in workbook_xml

    email = renderer.render(result, "leadership_email")
    parsed = BytesParser(policy=policy.default).parsebytes(email.body)
    assert "Competitive Intelligence" in str(parsed["Subject"])
    assert "Amazon is the main 1 lb" in parsed.get_body(preferencelist=("plain",)).get_content()
    attachments = list(parsed.iter_attachments())
    assert [attachment.get_filename() for attachment in attachments] == [
        "strawberries-2026-08-07-example-report.html"
    ]
    assert attachments[0].get_content().startswith("<!doctype html>")

    audit = renderer.render(result, "audit_zip")
    assert renderer.render(result, "audit_zip").body == audit.body
    with ZipFile(BytesIO(audit.body)) as archive:
        assert set(archive.namelist()) == {
            "analysis-result.json",
            "manifest.json",
            "strawberries-2026-08-07-example.html",
            "strawberries-2026-08-07-example.xlsx",
            "strawberries-2026-08-07-example.eml",
        }
        assert json.loads(archive.read("analysis-result.json")) == result
        manifest = json.loads(archive.read("manifest.json"))
        assert len(manifest["files"]) == 4
        assert manifest["renderer_version"] == renderer.version

    assert result == original


def test_blueprint_html_preserves_narrative_paragraphs() -> None:
    result = json.loads(
        (REPOSITORY_ROOT / "examples" / "analysis-result-v2.ground-beef.json").read_text()
    )
    result["narratives"]["sections"][0]["body"] = "Answer first.\n\nDecision implication."

    html = ArtifactRenderer(REPOSITORY_ROOT).render(result, "html").body

    assert b"<p>Answer first.</p><p>Decision implication.</p>" in html
    assert b"Leadership answer" in html
    assert b">executive_summary<" not in html
    assert b"Generated August 8, 2026 at 12:00 PM UTC" in html


async def test_artifact_generation_is_immutable_and_uses_short_lived_downloads() -> None:
    service, store = _service()
    analysis = await service.publish(_result())

    artifacts = [
        await service.generate_artifact(analysis.analysis_id, artifact_type)
        for artifact_type in ("html", "xlsx", "leadership_email", "audit_zip")
    ]

    assert len(store.objects) == 4
    assert {artifact.artifact_type for artifact in artifacts} == {
        "html",
        "xlsx",
        "leadership_email",
        "audit_zip",
    }
    repeated = [
        await service.generate_artifact(analysis.analysis_id, artifact_type)
        for artifact_type in ("html", "xlsx", "leadership_email", "audit_zip")
    ]
    assert [artifact.id for artifact in repeated] == [artifact.id for artifact in artifacts]
    assert len(store.objects) == 4
    download = await service.download_link(artifacts[0].id)
    assert download.expires_in_seconds == 300
    assert download.url.startswith("https://download.test/")


async def test_governed_publication_drives_report_view_and_versioned_artifacts() -> None:
    repository = InMemoryResultsRepository()
    store = InMemoryReportObjectStore()
    service = AnalysisResultService(
        repository,
        AnalysisResultValidator(REPOSITORY_ROOT),
        store,
        ArtifactRenderer(REPOSITORY_ROOT),
    )
    base = json.loads(
        (REPOSITORY_ROOT / "examples" / "analysis-result-v2.ground-beef.json").read_text()
    )
    analysis = await service.publish(base, collection_run_id="ground-beef-example-run")
    published_result = copy.deepcopy(base)
    published_result["narratives"]["sections"][0]["body"] = "Published leadership answer."

    publication = await service.publish_publication(analysis.analysis_id, published_result)
    repeated = await service.publish_publication(analysis.analysis_id, published_result)
    view = await service.report_view(analysis.analysis_id)
    artifact = await service.generate_artifact(analysis.analysis_id, "html")

    assert repeated.id == publication.id
    assert publication.version == 1
    assert publication.source_result_checksum == analysis.checksum
    assert view["publication"]["id"] == publication.id
    assert view["sections"][0]["narrative"]["body"] == "Published leadership answer."
    assert artifact.publication_id == publication.id

    next_result = copy.deepcopy(published_result)
    next_result["narratives"]["sections"][0]["body"] = "Superseding answer."
    next_publication = await service.publish_publication(analysis.analysis_id, next_result)
    next_artifact = await service.generate_artifact(analysis.analysis_id, "html")

    assert next_publication.version == 2
    assert next_artifact.publication_id == next_publication.id
    assert next_artifact.id != artifact.id


async def test_publication_cannot_change_authoritative_metrics() -> None:
    service, _ = _service()
    base = json.loads(
        (REPOSITORY_ROOT / "examples" / "analysis-result-v2.ground-beef.json").read_text()
    )
    analysis = await service.publish(base, collection_run_id="ground-beef-example-run")
    changed = copy.deepcopy(base)
    changed["metrics"][0]["value"] = 999

    with pytest.raises(ValueError, match="authoritative metrics"):
        await service.publish_publication(analysis.analysis_id, changed)


async def test_new_renderer_version_generates_a_new_immutable_artifact() -> None:
    class NextArtifactRenderer(ArtifactRenderer):
        @property
        def version(self) -> str:
            return "2.7.0"

    repository = InMemoryResultsRepository()
    store = InMemoryReportObjectStore()
    current = AnalysisResultService(
        repository,
        AnalysisResultValidator(REPOSITORY_ROOT),
        store,
        ArtifactRenderer(),
    )
    analysis = await current.publish(_result())
    first = await current.generate_artifact(analysis.analysis_id, "html")
    upgraded = AnalysisResultService(
        repository,
        AnalysisResultValidator(REPOSITORY_ROOT),
        store,
        NextArtifactRenderer(),
    )

    second = await upgraded.generate_artifact(analysis.analysis_id, "html")

    assert first.id != second.id
    assert first.renderer_version == "2.6.0"
    assert second.renderer_version == "2.7.0"
    assert len(store.objects) == 2
    listed = await upgraded.list_artifacts(analysis.analysis_id)
    assert {artifact.renderer_version for artifact in listed} == {
        "2.6.0",
        "2.7.0",
    }


def test_renderer_module_has_no_analytics_engine_dependency() -> None:
    source = (
        REPOSITORY_ROOT / "packages/python/rci-results/src/rci_results/renderers.py"
    ).read_text()
    assert "rci_analytics" not in source
    assert "statistics" not in source
    assert "polars" not in source


class PreconditionFailed(Exception):
    def __init__(self) -> None:
        self.response = {"Error": {"Code": "PreconditionFailed"}}
        super().__init__("object already exists")


class ExistingS3Client:
    def __init__(self, checksum: str) -> None:
        self.checksum = checksum
        self.put_calls = 0

    def put_object(self, **_kwargs: object) -> None:
        self.put_calls += 1
        raise PreconditionFailed

    def head_object(self, **_kwargs: object) -> dict[str, object]:
        return {"Metadata": {"sha256": self.checksum}}


async def test_s3_report_put_is_idempotent_when_immutable_object_exists() -> None:
    payload = ArtifactPayload("html", "analysis.html", "text/html", b"same report")
    client = ExistingS3Client(hashlib.sha256(payload.body).hexdigest())
    store = S3ReportObjectStore(bucket="reports", client=client)

    uri = await store.put("analysis-1", payload)

    assert uri.startswith("s3://reports/reports/analysis_id=analysis-1/")
    assert client.put_calls == 1
