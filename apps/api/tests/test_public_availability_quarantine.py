from __future__ import annotations

import copy
from datetime import UTC, datetime
from typing import Any

from httpx import ASGITransport, AsyncClient

from rci_api.analyses import get_analysis_service, has_verified_local_availability_contract
from rci_api.automation import get_automation_service
from rci_api.competitive_leadership import (
    PostgresCompetitiveLeadershipRepository,
    get_competitive_product_leadership_service,
)
from rci_api.main import create_app
from rci_api.price_monitoring import PostgresPriceMonitoringRepository, get_price_monitoring_service
from rci_results.models import AnalysisPublicationRecord, AnalysisRecord, DownloadLink
from rci_results.service import AnalysisNotFoundError, ArtifactNotCurrentError


def _result(*, current: bool, unavailable: set[str] | None = None) -> dict[str, Any]:
    unavailable = unavailable or set()
    required = [
        "walmart_us",
        *(retailer for retailer in ["aldi_us"] if retailer not in unavailable),
    ]
    coverage = []
    metrics = []
    for retailer in required:
        metric_ids = [
            f"coverage.{retailer}.verified_available_offers",
            f"coverage.{retailer}.verified_available_zips",
            f"coverage.{retailer}.verified_available_stores",
        ]
        coverage.append(
            {
                "retailer_id": retailer,
                "metric_refs": metric_ids if current else [],
                "evidence_refs": [f"evidence.classified.{retailer}"],
            }
        )
        if current:
            for metric_id in metric_ids:
                unit = (
                    "offers"
                    if metric_id.endswith("offers")
                    else "zipcodes"
                    if metric_id.endswith("zips")
                    else "stores"
                )
                metrics.append(
                    {
                        "metric_id": metric_id,
                        "value": 3,
                        "unit": unit,
                        "evidence_refs": [f"evidence.classified.{retailer}"],
                    }
                )
    return {
        "schema_version": "2.0.0",
        "analysis_id": "current-analysis" if current else "legacy-analysis",
        "source": {"unavailable_retailers": sorted(unavailable)},
        "benchmark_retailer": "walmart_us",
        "competitors": ["aldi_us"],
        "coverage": coverage,
        "metrics": metrics,
        "evidence_sets": [
            {"evidence_set_id": f"evidence.classified.{retailer}"} for retailer in required
        ],
        "validation": {
            "status": "ready_to_share",
            "checks": [
                {
                    "id": "verified-local-availability",
                    # A passing marker without its metrics is an intentionally
                    # adversarial legacy case covered by this fixture.
                    "status": "passed",
                    "evidence_refs": [f"evidence.classified.{retailer}" for retailer in required],
                }
            ],
        },
    }


def _record(result: dict[str, Any]) -> AnalysisRecord:
    return AnalysisRecord(
        id=f"record-{result['analysis_id']}",
        analysis_run_id=f"run-{result['analysis_id']}",
        analysis_id=str(result["analysis_id"]),
        collection_run_id=f"collection-{result['analysis_id']}",
        status="succeeded",
        reporting_status="ready",
        product_pack_id="fresh_fluid_milk",
        product_pack_version="1.3.0",
        schema_version="2.0.0",
        checksum="a" * 64,
        result=result,
        created_at=datetime(2026, 9, 8, tzinfo=UTC),
    )


class AnalysisService:
    def __init__(self, record: AnalysisRecord, *, active: bool = True) -> None:
        self.record = record
        self.active = active
        self.report_calls = 0
        self.download_calls = 0
        self.publication: AnalysisPublicationRecord | None = None
        self.artifact_current = True

    async def get(self, _identifier: str) -> AnalysisRecord:
        return self.record

    async def get_active(self, _identifier: str) -> AnalysisRecord:
        if not self.active:
            raise AnalysisNotFoundError("active analysis was not found")
        return self.record

    async def get_by_artifact(self, _artifact_id: str) -> AnalysisRecord:
        return self.record

    async def get_current_artifact(self, artifact_id: str) -> object:
        if not self.artifact_current:
            raise ArtifactNotCurrentError(f"artifact {artifact_id!r} was superseded")
        return object()

    async def presentation_source(
        self, _identifier: str
    ) -> tuple[AnalysisRecord, AnalysisPublicationRecord | None, dict[str, Any]]:
        document = self.publication.result if self.publication is not None else self.record.result
        return self.record, self.publication, document

    async def get_by_collection_run(self, _run_id: str) -> AnalysisRecord:
        return self.record

    async def list_analyses(self, _limit: int) -> list[AnalysisRecord]:
        return [self.record]

    async def report_view(self, analysis_id: str) -> dict[str, Any]:
        self.report_calls += 1
        return {"analysis_id": analysis_id, "status": "rendered"}

    async def download_link(self, artifact_id: str) -> DownloadLink:
        self.download_calls += 1
        return DownloadLink(
            artifact_id=artifact_id,
            url="https://download.test/report",
            expires_in_seconds=300,
        )


class _ScalarRows:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def scalars(self) -> list[dict[str, Any]]:
        return self._rows


class _CapturingConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []

    async def scalar(self, statement: object, _parameters: dict[str, Any]) -> dict[str, Any]:
        self.statements.append(str(statement))
        return {"schema_version": "current"}

    async def execute(self, statement: object, _parameters: dict[str, Any]) -> _ScalarRows:
        self.statements.append(str(statement))
        return _ScalarRows([{"schema_version": "current"}])


class _ConnectionContext:
    def __init__(self, connection: _CapturingConnection) -> None:
        self._connection = connection

    async def __aenter__(self) -> _CapturingConnection:
        return self._connection

    async def __aexit__(self, *_args: object) -> None:
        return None


class _CapturingEngine:
    def __init__(self) -> None:
        self.connection = _CapturingConnection()

    def connect(self) -> _ConnectionContext:
        return _ConnectionContext(self.connection)


def test_availability_contract_requires_metrics_and_honors_governed_unavailability() -> None:
    assert has_verified_local_availability_contract(_result(current=True)) is True
    assert has_verified_local_availability_contract(_result(current=False)) is False

    result = _result(current=True)
    result["metrics"][0]["value"] = 0
    assert has_verified_local_availability_contract(result) is False

    unavailable = _result(current=True, unavailable={"aldi_us"})
    assert has_verified_local_availability_contract(unavailable) is True

    unavailable_benchmark = copy.deepcopy(unavailable)
    unavailable_benchmark["source"]["unavailable_retailers"] = ["walmart_us", "aldi_us"]
    assert has_verified_local_availability_contract(unavailable_benchmark) is False

    unknown_unavailable = copy.deepcopy(unavailable)
    unknown_unavailable["source"]["unavailable_retailers"] = ["target_us"]
    assert has_verified_local_availability_contract(unknown_unavailable) is False


async def test_exact_latest_publication_document_is_quarantined_when_contract_diverges() -> None:
    service = AnalysisService(_record(_result(current=True)))
    divergent = copy.deepcopy(service.record.result)
    divergent["coverage"][0]["metric_refs"] = []
    service.publication = AnalysisPublicationRecord(
        id="divergent-publication",
        analysis_result_id=service.record.id,
        analysis_id=service.record.analysis_id,
        version=2,
        status="ready_to_share",
        source_result_checksum=service.record.checksum,
        publication_checksum="b" * 64,
        result=divergent,
        presentation_context={},
        created_at=datetime(2026, 9, 8, tzinfo=UTC),
    )
    app = create_app()
    app.dependency_overrides[get_analysis_service] = lambda: service
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        response = await client.get("/api/v1/analyses/current-analysis/report")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "legacy_availability_contract_quarantined"
    assert service.report_calls == 0


async def test_valid_publication_cannot_unquarantine_legacy_base_result_endpoints() -> None:
    legacy = _result(current=False)
    service = AnalysisService(_record(legacy))
    corrected = _result(current=True)
    corrected["analysis_id"] = legacy["analysis_id"]
    service.publication = AnalysisPublicationRecord(
        id="corrected-publication",
        analysis_result_id=service.record.id,
        analysis_id=service.record.analysis_id,
        version=2,
        status="ready_to_share",
        source_result_checksum=service.record.checksum,
        publication_checksum="b" * 64,
        result=corrected,
        presentation_context={},
        created_at=datetime(2026, 9, 8, tzinfo=UTC),
    )
    app = create_app()
    app.dependency_overrides[get_analysis_service] = lambda: service
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        analysis = await client.get("/api/v1/analyses/legacy-analysis")
        report = await client.get("/api/v1/analyses/legacy-analysis/report")
        listing = await client.get("/api/v1/analyses")

    assert analysis.status_code == report.status_code == 409
    assert analysis.json()["detail"]["code"] == "legacy_availability_contract_quarantined"
    assert report.json()["detail"]["code"] == "legacy_availability_contract_quarantined"
    assert listing.json() == []
    assert service.report_calls == 0


async def test_superseded_artifact_is_rejected_before_presigning() -> None:
    service = AnalysisService(_record(_result(current=True)))
    service.artifact_current = False
    app = create_app()
    app.dependency_overrides[get_analysis_service] = lambda: service
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        response = await client.get("/api/v1/artifacts/superseded-artifact/download")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "artifact_not_current"
    assert service.download_calls == 0


async def test_stored_public_materializations_require_active_ready_analysis() -> None:
    engine = _CapturingEngine()
    price_repository = PostgresPriceMonitoringRepository(engine)  # type: ignore[arg-type]
    competitive_repository = PostgresCompetitiveLeadershipRepository(engine)  # type: ignore[arg-type]

    await price_repository.architecture_materialization(
        "analysis-id",
        mode="benchmark_anchored",
        fixed_increment=0.5,
        brand_type="all",
        brand=None,
        state=None,
        city=None,
        zipcode=None,
    )
    await competitive_repository.materialization(
        "analysis-id",
        profile_id="strict",
        radius_miles=3,
    )
    await competitive_repository.materializations("analysis-id")

    assert len(engine.connection.statements) == 3
    for statement in engine.connection.statements:
        assert "result.reporting_status = 'ready'" in statement
        assert "result.archived_at IS NULL" in statement


async def test_direct_analysis_report_and_artifact_reads_quarantine_legacy_results() -> None:
    service = AnalysisService(_record(_result(current=False)))
    app = create_app()
    app.dependency_overrides[get_analysis_service] = lambda: service
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        analysis = await client.get("/api/v1/analyses/legacy-analysis")
        report = await client.get("/api/v1/analyses/legacy-analysis/report")
        artifact = await client.get("/api/v1/artifacts/legacy-artifact/download")
        listing = await client.get("/api/v1/analyses")

    expected = {
        "code": "legacy_availability_contract_quarantined",
        "message": (
            "This report is quarantined because it does not contain validated "
            "local-availability evidence for every scoreable retailer."
        ),
        "analysis_id": "legacy-analysis",
    }
    assert analysis.status_code == report.status_code == artifact.status_code == 409
    assert analysis.json()["detail"] == expected
    assert report.json()["detail"] == expected
    assert artifact.json()["detail"] == expected
    assert listing.json() == []
    assert service.report_calls == 0
    assert service.download_calls == 0


async def test_current_contract_passes_and_inactive_report_is_still_quarantined() -> None:
    service = AnalysisService(_record(_result(current=True)))
    app = create_app()
    app.dependency_overrides[get_analysis_service] = lambda: service
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        report = await client.get("/api/v1/analyses/current-analysis/report")
        artifact = await client.get("/api/v1/artifacts/current-artifact/download")
        listing = await client.get("/api/v1/analyses")
        service.active = False
        inactive = await client.get("/api/v1/analyses/current-analysis/report")

    assert report.status_code == 200
    assert artifact.status_code == 200
    assert [row["analysis_id"] for row in listing.json()] == ["current-analysis"]
    assert inactive.status_code == 409
    assert inactive.json()["detail"]["code"] == "report_not_active"


async def test_price_monitoring_cached_document_cannot_bypass_analysis_quarantine() -> None:
    class PriceService:
        def __init__(self) -> None:
            self.calls = 0

        async def catalog_document(self, analysis_id: str, retailer_id: str) -> dict[str, Any]:
            self.calls += 1
            return {"analysis_id": analysis_id, "retailer_id": retailer_id, "cached": True}

    analysis_service = AnalysisService(_record(_result(current=False)))
    price_service = PriceService()
    app = create_app()
    app.dependency_overrides[get_analysis_service] = lambda: analysis_service
    app.dependency_overrides[get_price_monitoring_service] = lambda: price_service
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        quarantined = await client.get(
            "/api/v1/analyses/legacy-analysis/price-monitoring",
            params={"retailer": "walmart_us"},
        )
        analysis_service.record = _record(_result(current=True))
        current = await client.get(
            "/api/v1/analyses/current-analysis/price-monitoring",
            params={"retailer": "walmart_us"},
        )

    assert quarantined.status_code == 409
    assert quarantined.json()["detail"]["code"] == "legacy_availability_contract_quarantined"
    assert price_service.calls == 1
    assert current.status_code == 200
    assert current.json()["cached"] is True


async def test_competitive_stored_document_cannot_bypass_analysis_quarantine() -> None:
    class LeadershipService:
        def __init__(self) -> None:
            self.calls = 0

        async def view(self, analysis_id: str, **_filters: Any) -> dict[str, Any]:
            self.calls += 1
            return {"analysis_id": analysis_id, "stored": True}

    analysis_service = AnalysisService(_record(_result(current=False)))
    leadership_service = LeadershipService()
    app = create_app()
    app.dependency_overrides[get_analysis_service] = lambda: analysis_service
    app.dependency_overrides[get_competitive_product_leadership_service] = lambda: (
        leadership_service
    )
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        quarantined = await client.get(
            "/api/v1/analyses/legacy-analysis/competitive-product-leadership"
        )
        analysis_service.record = _record(_result(current=True))
        current = await client.get(
            "/api/v1/analyses/current-analysis/competitive-product-leadership"
        )

    assert quarantined.status_code == 409
    assert quarantined.json()["detail"]["code"] == "legacy_availability_contract_quarantined"
    assert leadership_service.calls == 1
    assert current.status_code == 200
    assert current.json()["stored"] is True


async def test_automation_history_and_evaluation_cannot_bypass_analysis_quarantine() -> None:
    class AutomationService:
        def __init__(self) -> None:
            self.history_calls = 0
            self.evaluation_calls = 0

        async def history(self, _analysis_id: str, **_filters: Any) -> object:
            self.history_calls += 1
            return object()

        async def evaluate_analysis(self, _analysis_id: str) -> tuple[int, int]:
            self.evaluation_calls += 1
            return 0, 0

    analysis_service = AnalysisService(_record(_result(current=False)))
    automation_service = AutomationService()
    app = create_app()
    app.dependency_overrides[get_analysis_service] = lambda: analysis_service
    app.dependency_overrides[get_automation_service] = lambda: automation_service
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        history = await client.get("/api/v1/analyses/legacy-analysis/history")
        evaluation = await client.post("/api/v1/analyses/legacy-analysis/evaluate-alerts")

    assert history.status_code == evaluation.status_code == 409
    assert history.json()["detail"]["code"] == "legacy_availability_contract_quarantined"
    assert evaluation.json()["detail"]["code"] == "legacy_availability_contract_quarantined"
    assert automation_service.history_calls == 0
    assert automation_service.evaluation_calls == 0


async def test_collection_run_operator_read_remains_available_for_legacy_result() -> None:
    service = AnalysisService(_record(_result(current=False)))
    app = create_app()
    app.dependency_overrides[get_analysis_service] = lambda: service
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        response = await client.get("/api/v1/collection-runs/source-run/analysis")

    assert response.status_code == 200
    assert response.json()["analysis_id"] == "legacy-analysis"
