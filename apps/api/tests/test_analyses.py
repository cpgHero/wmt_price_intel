from __future__ import annotations

import json
from pathlib import Path

from httpx import ASGITransport, AsyncClient

from rci_api.analyses import get_analysis_service
from rci_api.main import create_app
from rci_results import (
    AnalysisResultService,
    AnalysisResultValidator,
    InMemoryReportObjectStore,
    InMemoryResultsRepository,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _document() -> dict[str, object]:
    return json.loads(
        (REPOSITORY_ROOT / "examples" / "analysis-result.strawberries.json").read_text()
    )


def _service() -> AnalysisResultService:
    return AnalysisResultService(
        InMemoryResultsRepository(),
        AnalysisResultValidator(REPOSITORY_ROOT),
        InMemoryReportObjectStore(),
    )


async def test_analysis_reader_quality_match_and_artifact_apis() -> None:
    service = _service()
    app = create_app()
    app.dependency_overrides[get_analysis_service] = lambda: service
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        document = _document()
        published = await client.post("/api/v1/collection-runs/run-example/analysis", json=document)
        assert published.status_code == 201
        analysis_id = published.json()["analysis_id"]

        listing = await client.get("/api/v1/analyses")
        assert [row["analysis_id"] for row in listing.json()] == [analysis_id]
        fetched = await client.get(f"/api/v1/analyses/{analysis_id}")
        assert fetched.json()["result"] == document
        by_run = await client.get("/api/v1/collection-runs/run-example/analysis")
        assert by_run.json()["analysis_id"] == analysis_id
        matches = await client.get(f"/api/v1/analyses/{analysis_id}/matches")
        assert len(matches.json()["comparisons"]) == 4
        quality = await client.get(f"/api/v1/analyses/{analysis_id}/quality")
        assert quality.json()["validation"]["status"] == "ready_to_share"

        generated = await client.post(f"/api/v1/analyses/{analysis_id}/artifacts/html")
        assert generated.status_code == 201
        assert generated.json()["renderer_version"] == "2.8.1"
        assert generated.json()["publication_id"] is None
        artifact_id = generated.json()["id"]
        artifacts = await client.get(f"/api/v1/analyses/{analysis_id}/artifacts")
        assert [row["id"] for row in artifacts.json()] == [artifact_id]
        download = await client.get(f"/api/v1/artifacts/{artifact_id}/download")
        assert download.status_code == 200
        assert download.json()["expires_in_seconds"] == 300


async def test_analysis_api_rejects_contract_mismatch_and_mutation() -> None:
    service = _service()
    app = create_app()
    app.dependency_overrides[get_analysis_service] = lambda: service
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        document = _document()
        mismatch = await client.post("/api/v1/collection-runs/wrong/analysis", json=document)
        assert mismatch.status_code == 409

        assert (
            await client.post("/api/v1/collection-runs/run-example/analysis", json=document)
        ).status_code == 201
        document["comparisons"][0]["matches"] = 1  # type: ignore[index]
        mutation = await client.post("/api/v1/collection-runs/run-example/analysis", json=document)
        assert mutation.status_code == 409

        invalid = await client.post(
            "/api/v1/collection-runs/run-example/analysis",
            json={"analysis_id": "invalid"},
        )
        assert invalid.status_code == 422


async def test_analysis_v2_report_endpoint_returns_blueprint_projection() -> None:
    service = _service()
    app = create_app()
    app.dependency_overrides[get_analysis_service] = lambda: service
    document = json.loads(
        (REPOSITORY_ROOT / "examples/analysis-result-v2.ground-beef.json").read_text()
    )
    document["source"]["collection_run_id"] = "run-v2-example"
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        published = await client.post(
            "/api/v1/collection-runs/run-v2-example/analysis",
            json=document,
        )
        assert published.status_code == 201

        report = await client.get(f"/api/v1/analyses/{document['analysis_id']}/report")

    assert report.status_code == 200
    assert report.json()["blueprint"] == {
        "id": "fresh_ground_beef_leadership",
        "version": "1.0.0",
    }
    assert report.json()["sections"][0]["id"] == "executive_summary"
