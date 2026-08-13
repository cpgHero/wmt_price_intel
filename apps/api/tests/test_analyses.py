from __future__ import annotations

import json
from pathlib import Path

from httpx import ASGITransport, AsyncClient

from rci_api.analyses import (
    get_analysis_service,
    get_brand_review_service,
    get_match_review_service,
)
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
        assert generated.json()["renderer_version"] == "2.15.0"
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


async def test_match_review_api_exposes_decisions_and_zero_provider_reanalysis() -> None:
    class MatchService:
        async def view(self, analysis_id: str) -> dict[str, object]:
            return {
                "analysis_id": analysis_id,
                "product_pack_id": "fresh_ground_beef",
                "product_pack_version": "1.0.0",
                "revision_id": None,
                "revision": 0,
                "future_application": None,
                "benchmark_retailer": {"id": "walmart_us", "name": "Walmart"},
                "competitors": [{"id": "aldi_us", "name": "ALDI"}],
                "profiles": [],
                "products": [],
                "connections": [],
                "summary": {"suggested": 0, "confirmed": 0, "rejected": 0, "unmatched": 0},
            }

        async def decide(
            self, _analysis_id: str, command: object, *, actor: str
        ) -> dict[str, object]:
            assert actor == "reviewer@example.test"
            assert command.decision == "confirmed"
            assert command.scope["mode"] == "observed_benchmark_product_footprint"
            return {"revision_id": "revision-id", "revision": 1, "status": "saved"}

        async def recompute(
            self,
            _analysis_id: str,
            *,
            expected_revision: int,
            apply_to_future_runs: bool,
            actor: str,
        ) -> object:
            assert expected_revision == 1
            assert apply_to_future_runs is True
            assert actor == "reviewer@example.test"
            return type(
                "Queued",
                (),
                {
                    "analysis_run_id": "run-id",
                    "source_analysis_id": "analysis-id",
                    "match_revision_id": "revision-id",
                    "status": "queued",
                    "applied_to_future_runs": True,
                },
            )()

    app = create_app()
    app.dependency_overrides[get_match_review_service] = lambda: MatchService()
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        review = await client.get("/api/v1/analyses/analysis-id/match-review")
        decision = await client.post(
            "/api/v1/analyses/analysis-id/match-review/decisions",
            headers={"X-RCI-Actor": "reviewer@example.test"},
            json={
                "expected_revision": 0,
                "competitor_retailer_id": "aldi_us",
                "profile_id": "strict",
                "benchmark_product_id": "w1",
                "competitor_product_id": "a1",
                "decision": "confirmed",
                "scope": {
                    "mode": "observed_benchmark_product_footprint",
                    "relationship_role": "primary",
                    "comparison_family_key": "milk:whole:gallon",
                    "definition": {
                        "benchmark_location_scope_keys": [],
                        "future_location_policy": "follow_unique_product_footprint",
                    },
                    "checksum": "a" * 64,
                },
            },
        )
        recompute = await client.post(
            "/api/v1/analyses/analysis-id/match-review/recompute",
            json={"expected_revision": 1, "apply_to_future_runs": True},
            headers={"X-RCI-Actor": "reviewer@example.test"},
        )

    assert review.status_code == 200
    assert decision.json()["revision"] == 1
    assert recompute.json()["provider_calls_queued"] == 0
    assert recompute.json()["applied_to_future_runs"] is True


async def test_brand_workbench_api_stages_decisions_and_zero_provider_reanalysis() -> None:
    class BrandService:
        async def view(self, analysis_id: str) -> dict[str, object]:
            return {
                "schema_version": "1.0.0",
                "analysis_id": analysis_id,
                "product_pack_id": "fresh_fluid_milk",
                "product_pack_version": "1.2.0",
                "revision": 0,
                "future_application": None,
                "retailers": [{"id": "walmart_us", "name": "Walmart"}],
                "brands": [],
                "summary": {
                    "suggested": 0,
                    "confirmed": 0,
                    "rejected": 0,
                    "unclassified": 0,
                    "candidate_matches": 0,
                    "ambiguous_matches": 0,
                },
            }

        async def decide(
            self, _analysis_id: str, command: object, *, actor: str
        ) -> dict[str, object]:
            assert actor == "reviewer@example.test"
            assert command.normalized_brand == "hiland dairy"
            assert command.role == "regional"
            return {"revision_id": "brand-revision-id", "revision": 1, "status": "saved"}

        async def recompute(
            self,
            _analysis_id: str,
            *,
            expected_revision: int,
            apply_to_future_runs: bool,
            actor: str,
        ) -> object:
            assert expected_revision == 1
            assert apply_to_future_runs is False
            assert actor == "reviewer@example.test"
            return type(
                "Queued",
                (),
                {
                    "analysis_run_id": "brand-run-id",
                    "source_analysis_id": "analysis-id",
                    "brand_revision_id": "brand-revision-id",
                    "status": "queued",
                    "applied_to_future_runs": False,
                },
            )()

    app = create_app()
    app.dependency_overrides[get_brand_review_service] = lambda: BrandService()
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        view = await client.get("/api/v1/analyses/analysis-id/brand-workbench")
        decision = await client.post(
            "/api/v1/analyses/analysis-id/brand-workbench/decisions",
            headers={"X-RCI-Actor": "reviewer@example.test"},
            json={
                "expected_revision": 0,
                "retailer_id": "walmart_us",
                "normalized_brand": "hiland dairy",
                "role": "regional",
                "decision": "confirmed",
            },
        )
        recompute = await client.post(
            "/api/v1/analyses/analysis-id/brand-workbench/recompute",
            headers={"X-RCI-Actor": "reviewer@example.test"},
            json={"expected_revision": 1, "apply_to_future_runs": False},
        )

    assert view.status_code == 200
    assert decision.json()["revision"] == 1
    assert recompute.json()["provider_calls_queued"] == 0
    assert recompute.json()["applied_to_future_runs"] is False


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


async def test_product_decision_evidence_is_read_separately_from_report_view() -> None:
    service = _service()
    app = create_app()
    app.dependency_overrides[get_analysis_service] = lambda: service
    document = json.loads(
        (REPOSITORY_ROOT / "examples/analysis-result-v2.ground-beef.json").read_text()
    )
    document["source"]["collection_run_id"] = "run-product-evidence"
    decision = {
        "id": "product-decision-1",
        "benchmark_product_id": "100",
        "competitor": "aldi_us",
        "competitor_product_id": "200",
    }
    evidence = {
        "decision_id": "product-decision-1",
        "summary": {"benchmark_stores_undercut": 1},
        "rows": [
            {
                "zipcode": "72712",
                "benchmark_store": "100",
                "competitor_store": "200",
                "benchmark_price": 4.0,
                "competitor_price": 3.5,
                "competitor_minus_benchmark": -0.5,
                "outcome": "competitor_lower",
            }
        ],
    }
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        published = await service.publish(
            document,
            collection_run_id="run-product-evidence",
        )
        await service.publish_publication(
            published.analysis_id,
            document,
            presentation_context={
                "product_decisions": [decision],
                "product_evidence": {"product-decision-1": evidence},
            },
        )

        report = await client.get(f"/api/v1/analyses/{published.analysis_id}/report")
        detail = await client.get(
            f"/api/v1/analyses/{published.analysis_id}/product-decisions/"
            "product-decision-1/evidence"
        )

    assert report.status_code == 200
    assert "product_evidence" not in report.json()
    assert detail.status_code == 200
    assert detail.json()["summary"]["benchmark_stores_undercut"] == 1
    assert detail.json()["rows"][0]["benchmark_store"] == "100"
