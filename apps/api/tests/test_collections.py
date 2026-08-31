from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from httpx import ASGITransport, AsyncClient

from rci_api.collections import get_collection_service, get_composite_evidence_repository
from rci_api.main import create_app
from rci_collections import (
    CollectionPlanner,
    CollectionRetailerCatalog,
    InMemoryCollectionRepository,
)
from rci_collections.composite import (
    ContinuationSelectionPreview,
    RecoveryLaunchRecord,
    RecoverySelectionItem,
    RetailerRecoverySummary,
    ScopeProjectionItem,
    ScopeProjectionPreview,
    ScopeProjectionRecord,
)
from rci_collections.geography import CollectionGeographyResolver
from rci_collections.models import LocationUnit
from rci_collections.service import CollectionService
from rci_core import AppSettings

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _config() -> dict[str, object]:
    return {
        "id": "api-collection",
        "name": "API Collection Test",
        "version": "1.0.0",
        "enabled": True,
        "benchmark_retailer": "walmart_us",
        "product_pack": {"id": "fresh_strawberries", "version": "1.0.0"},
        "query": {"keyword": "strawberries"},
        "retailers": [
            {
                "retailer_id": "walmart_us",
                "adapter_id": "metricscart_walmart_search_zipcode_v2",
                "enabled": True,
            }
        ],
        "geography": {"strategy": "all_retailer_locations", "country": "USA"},
        "pagination": {"max_pages": 1, "stop_on_empty": True},
        "delivery": {"web_report": True, "excel": False, "leadership_email": False},
    }


def _service() -> CollectionService:
    units = [
        LocationUnit(
            id=f"location-{index}",
            retailer_id="walmart_us",
            zipcode=f"0600{index}",
            store_number=f"00{index}",
            state="CT",
            country="USA",
        )
        for index in range(2)
    ]
    units.append(
        LocationUnit(
            id="00000000-0000-0000-0000-000000000101",
            retailer_id="aldi_us",
            zipcode="06000",
            store_number="475-101",
            state="CT",
            country="USA",
            city="Example",
            latitude=41.6,
            longitude=-72.7,
        )
    )
    repository = InMemoryCollectionRepository(units)
    catalog = CollectionRetailerCatalog.from_path(
        REPOSITORY_ROOT / "config" / "retailer-catalog.json"
    )
    return CollectionService(
        repository,
        CollectionPlanner(repository, catalog),
        REPOSITORY_ROOT,
        CollectionGeographyResolver(repository, catalog),
    )


def _approved_config(resolution: dict[str, object]) -> dict[str, object]:
    config = _config()
    config["retailers"] = [
        {
            "retailer_id": "walmart_us",
            "adapter_id": "metricscart_walmart_search_zipcode_v2",
            "enabled": True,
        },
        {
            "retailer_id": "aldi_us",
            "adapter_id": "metricscart_new_aldi_serp_zipcode",
            "enabled": True,
        },
        {
            "retailer_id": "amazon_us_same_day",
            "adapter_id": "metricscart_amazon_same_day_zipcode",
            "enabled": True,
        },
    ]
    config["geography"] = {
        "strategy": "approved_resolution",
        "country": "USA",
        "resolution_id": resolution["id"],
        "resolution_checksum": resolution["checksum"],
        "refresh_policy": "frozen",
    }
    return config


async def test_collection_definition_run_and_usage_apis() -> None:
    service = _service()
    app = create_app()
    app.dependency_overrides[get_collection_service] = lambda: service
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        published = await client.post("/api/v1/collection-definitions", json=_config())
        assert published.status_code == 201
        assert published.json()["version"] == 1

        repeated = await client.post("/api/v1/collection-definitions", json=_config())
        assert repeated.json()["version_id"] == published.json()["version_id"]

        revised = _config()
        revised["name"] = "Revised API Collection"
        revision = await client.post("/api/v1/collection-definitions", json=revised)
        assert revision.json()["version"] == 2

        estimate = await client.post("/api/v1/collection-definitions/api-collection/estimate")
        assert estimate.status_code == 200
        assert estimate.json()["estimated_total_pages"] == 2
        assert estimate.json()["estimated_total_credits"] == 2

        direct_estimate = await client.post("/api/v1/collection-estimates", json=_config())
        assert direct_estimate.status_code == 200
        assert direct_estimate.json() == estimate.json()

        created = await client.post("/api/v1/collection-definitions/api-collection/runs")
        assert created.status_code == 201
        run_id = created.json()["id"]

        runs = await client.get("/api/v1/collection-runs?limit=10")
        assert runs.status_code == 200
        assert [item["id"] for item in runs.json()] == [run_id]

        tasks = await client.get(f"/api/v1/collection-runs/{run_id}/tasks")
        assert len(tasks.json()) == 2
        assert all(item["status"] == "pending" for item in tasks.json())

        filtered_tasks = await client.get(
            f"/api/v1/collection-runs/{run_id}/tasks",
            params={"retailer_id": "walmart_us", "status": "failed"},
        )
        assert filtered_tasks.status_code == 200
        assert filtered_tasks.json() == []

        usage = await client.get(f"/api/v1/collection-runs/{run_id}/usage")
        assert usage.json()["estimated_pages"] == 2
        assert usage.json()["actual_credits"] == 0

        monitor = await client.get(f"/api/v1/collection-runs/{run_id}/monitor")
        assert monitor.status_code == 200
        assert monitor.json()["configured_global_rps"] == 2
        assert monitor.json()["retry_attempts"] == 0
        assert monitor.json()["retailer_gates"] == []
        assert monitor.json()["retailers"] == [
            {
                "retailer_id": "walmart_us",
                "pending_tasks": 2,
                "running_tasks": 0,
                "succeeded_tasks": 0,
                "failed_tasks": 0,
                "cancelled_tasks": 0,
                "billable_credits": 0,
                "attempts": 0,
                "retries": 0,
            }
        ]
        failures = await client.get(f"/api/v1/collection-runs/{run_id}/failures.csv")
        assert failures.status_code == 200
        assert failures.headers["content-type"].startswith("text/csv")
        assert failures.text.startswith("retailer_id,adapter_id,zipcode,store_number")

        cancelled = await client.post(f"/api/v1/collection-runs/{run_id}/cancel")
        assert cancelled.json()["status"] == "cancelled"


async def test_exact_recovery_launch_api_is_idempotency_visible() -> None:
    class CompositeRepository:
        async def launch_exact_recovery(self, plan_id: str) -> RecoveryLaunchRecord:
            return RecoveryLaunchRecord(
                recovery_plan_id=plan_id,
                collection_run_id="00000000-0000-0000-0000-000000000201",
                definition_version_id="00000000-0000-0000-0000-000000000202",
                status="queued",
                task_count=13,
                maximum_credits=23,
                availability_gate_status="skipped",
                reused_existing_run=True,
            )

    app = create_app()
    app.dependency_overrides[get_composite_evidence_repository] = CompositeRepository
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        response = await client.post(
            "/api/v1/collection-recovery-plans/00000000-0000-0000-0000-000000000200/launch"
        )

    assert response.status_code == 201
    assert response.json() == {
        "recovery_plan_id": "00000000-0000-0000-0000-000000000200",
        "collection_run_id": "00000000-0000-0000-0000-000000000201",
        "definition_version_id": "00000000-0000-0000-0000-000000000202",
        "status": "queued",
        "task_count": 13,
        "maximum_credits": 23,
        "availability_gate_status": "skipped",
        "reused_existing_run": True,
    }


async def test_continuation_preview_is_paginated_but_checksum_covers_full_selection() -> None:
    plan_id = "00000000-0000-0000-0000-000000000200"
    items = tuple(
        RecoverySelectionItem(
            source_task_id=f"00000000-0000-0000-0000-{index:012d}",
            retailer_id="aldi_us",
            canonical_request_key=f"key-{index}",
            selection_reason="transient_gap",
            required_for_assembly=False,
            credits_per_success=2,
            maximum_credits=10,
            source_snapshot={"index": index},
        )
        for index in range(3)
    )

    class CompositeRepository:
        async def preview_continuation(
            self, parent_plan_id: str, *, retailer_ids: tuple[str, ...] | list[str]
        ) -> ContinuationSelectionPreview:
            assert parent_plan_id == plan_id
            assert tuple(retailer_ids) == ("aldi_us",)
            return ContinuationSelectionPreview(
                base_collection_run_id="00000000-0000-0000-0000-000000000100",
                continuation_of_recovery_plan_id=plan_id,
                lineage_plan_ids=(plan_id,),
                lineage_checksum="a" * 64,
                selection_policy_version="unresolved-continuation-v1",
                selection_checksum="b" * 64,
                base_snapshot_checksum="c" * 64,
                selected_task_count=3,
                maximum_provider_attempts=15,
                maximum_credits=30,
                resolved_before_count=2,
                conclusive_before_count=97,
                retained_success_count=96,
                retained_billable_404_count=1,
                retailers=(
                    RetailerRecoverySummary(
                        retailer_id="aldi_us",
                        selected_tasks=3,
                        required_tasks=0,
                        optional_transient_tasks=3,
                        maximum_provider_attempts=15,
                        maximum_credits=30,
                        reused_successes=96,
                        retained_billable_404s=1,
                        retained_billable_404_credits=2,
                    ),
                ),
                items=items,
            )

    app = create_app()
    app.dependency_overrides[get_composite_evidence_repository] = CompositeRepository
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        response = await client.get(
            f"/api/v1/collection-recovery-plans/{plan_id}/continuation-preview",
            params={"retailer_ids": "aldi_us", "item_offset": 1, "item_limit": 1},
        )
        over_page_cap = await client.get(
            f"/api/v1/collection-recovery-plans/{plan_id}/continuation-preview",
            params={"item_limit": 501},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["selection_checksum"] == "b" * 64
    assert payload["selected_task_count"] == 3
    assert payload["item_offset"] == 1
    assert payload["next_item_offset"] == 2
    assert [item["canonical_request_key"] for item in payload["items"]] == ["key-1"]
    assert over_page_cap.status_code == 422


async def test_scope_projection_preview_is_admin_only_paginated_and_checksum_complete() -> None:
    run_id = "00000000-0000-0000-0000-000000000100"
    items = tuple(
        ScopeProjectionItem(
            source_task_id=f"00000000-0000-0000-0000-{index:012d}",
            retailer_id="wegmans_us",
            canonical_request_key=f"key-{index}",
            disposition=("retained" if index < 2 else "excluded"),
            reason=(
                "provider_valid_successful_scope"
                if index < 2
                else "provider_rejected_store_scope_http_400"
            ),
            mapped_retained_task_id=None,
            source_snapshot={"index": index},
        )
        for index in range(3)
    )

    class CompositeRepository:
        async def preview_scope_projection(self, base_run_id: str, **values: object) -> Any:
            assert base_run_id == run_id
            assert values == {
                "retailer_id": "wegmans_us",
                "projection_kind": "limited_provider_footprint",
                "source_audit_id": None,
            }
            return ScopeProjectionPreview(
                base_collection_run_id=run_id,
                retailer_id="wegmans_us",
                projection_kind="limited_provider_footprint",
                policy_version="collection-scope-projection-v1",
                base_snapshot_checksum="a" * 64,
                source_audit_id=None,
                source_evidence_checksum="b" * 64,
                raw_task_count=3,
                retained_task_count=2,
                excluded_task_count=1,
                raw_location_count=3,
                retained_location_count=2,
                excluded_location_count=1,
                denominator_gap_location_count=0,
                raw_task_retention_ratio="0.666667",
                governed_coverage_ratio="0.666667",
                minimum_scoreable_coverage="0.950000",
                scorecard_disposition="unavailable",
                coverage_numerator_location_count=2,
                coverage_denominator_location_count=3,
                coverage_semantics="provider_valid_scopes_over_frozen_network_scopes",
                projection_checksum="c" * 64,
                manifest={"inventory_checksum": "d" * 64},
                items=items,
            )

    app = create_app()
    app.dependency_overrides[get_composite_evidence_repository] = CompositeRepository
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        response = await client.get(
            f"/api/v1/collection-runs/{run_id}/scope-projection-preview",
            params={
                "retailer_id": "wegmans_us",
                "projection_kind": "limited_provider_footprint",
                "item_offset": 1,
                "item_limit": 1,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["projection_checksum"] == "c" * 64
    assert payload["raw_task_count"] == 3
    assert payload["next_item_offset"] == 2
    assert payload["items"][0]["source_task_id"].endswith("000000000001")


async def test_audited_projection_preview_explains_zero_gap_policy_mismatch() -> None:
    run_id = "00000000-0000-0000-0000-000000000100"

    class CompositeRepository:
        async def preview_scope_projection(self, base_run_id: str, **values: object) -> None:
            assert base_run_id == run_id
            assert values["projection_kind"] == "audited_alias_reconciliation"
            raise ValueError(
                "audited alias reconciliation requires at least one audited unpaired "
                "denominator gap; use canonical_alias_collapse when every alias is mapped"
            )

    app = create_app()
    app.dependency_overrides[get_composite_evidence_repository] = CompositeRepository
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        response = await client.get(
            f"/api/v1/collection-runs/{run_id}/scope-projection-preview",
            params={
                "retailer_id": "kroger_us",
                "projection_kind": "audited_alias_reconciliation",
                "source_audit_id": "00000000-0000-0000-0000-000000000500",
            },
        )

    assert response.status_code == 409
    assert "use canonical_alias_collapse" in response.json()["detail"]


async def test_scope_projection_approval_uses_server_controlled_actor() -> None:
    captured: dict[str, object] = {}
    run_id = "00000000-0000-0000-0000-000000000100"

    class CompositeRepository:
        async def approve_scope_projection(self, base_run_id: str, **values: object) -> None:
            captured.update({"base_run_id": base_run_id, **values})
            raise ValueError("intentional audit capture")

    app = create_app()
    app.dependency_overrides[get_composite_evidence_repository] = CompositeRepository
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        response = await client.post(
            f"/api/v1/collection-runs/{run_id}/scope-projections",
            headers={"X-RCI-Actor": "forged-client-principal"},
            json={
                "retailer_id": "kroger_us",
                "projection_kind": "canonical_alias_collapse",
                "projection_checksum": "a" * 64,
                "base_snapshot_checksum": "b" * 64,
                "source_audit_id": "00000000-0000-0000-0000-000000000500",
                "review_reason": "collapse audited aliases",
            },
        )

    assert response.status_code == 409
    assert captured["base_run_id"] == run_id
    assert captured["reviewed_by"] == "authenticated-platform-admin"
    assert captured["source_audit_id"] == "00000000-0000-0000-0000-000000000500"


async def test_audited_scope_projection_approval_is_api_idempotent() -> None:
    run_id = "00000000-0000-0000-0000-000000000100"
    projection_id = "00000000-0000-0000-0000-000000000054"
    calls: list[dict[str, object]] = []
    record = ScopeProjectionRecord(
        id=projection_id,
        base_collection_run_id=run_id,
        retailer_id="kroger_us",
        projection_kind="audited_alias_reconciliation",
        policy_version="audited-alias-reconciliation-v1",
        base_snapshot_checksum="b" * 64,
        source_audit_id="00000000-0000-0000-0000-000000000500",
        source_evidence_checksum="c" * 64,
        raw_task_count=2_667,
        retained_task_count=1_369,
        excluded_task_count=1_298,
        raw_location_count=2_667,
        retained_location_count=1_369,
        excluded_location_count=1_298,
        denominator_gap_location_count=2,
        raw_task_retention_ratio="0.513311",
        governed_coverage_ratio="0.998541",
        minimum_scoreable_coverage="0.950000",
        scorecard_disposition="scoreable",
        coverage_numerator_location_count=1_369,
        coverage_denominator_location_count=1_371,
        coverage_semantics=("provider_safe_scopes_over_provider_safe_plus_audited_unpaired_gaps"),
        projection_checksum="a" * 64,
        review_reason="approve governed legacy reconciliation",
        reviewed_by="authenticated-platform-admin",
        manifest={"inventory_checksum": "d" * 64},
        created_at=datetime(2026, 8, 30, tzinfo=UTC),
    )

    class CompositeRepository:
        async def approve_scope_projection(
            self, base_run_id: str, **values: object
        ) -> ScopeProjectionRecord:
            calls.append({"base_run_id": base_run_id, **values})
            return record

    body = {
        "retailer_id": "kroger_us",
        "projection_kind": "audited_alias_reconciliation",
        "projection_checksum": "a" * 64,
        "base_snapshot_checksum": "b" * 64,
        "source_audit_id": "00000000-0000-0000-0000-000000000500",
        "review_reason": "approve governed legacy reconciliation",
    }
    app = create_app()
    app.dependency_overrides[get_composite_evidence_repository] = CompositeRepository
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        first = await client.post(f"/api/v1/collection-runs/{run_id}/scope-projections", json=body)
        second = await client.post(f"/api/v1/collection-runs/{run_id}/scope-projections", json=body)

    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    assert first.json()["id"] == projection_id
    assert len(calls) == 2
    assert all(call["projection_kind"] == "audited_alias_reconciliation" for call in calls)


async def test_continuation_approval_uses_server_actor_and_forbids_extra_fields() -> None:
    captured: dict[str, object] = {}
    plan_id = "00000000-0000-0000-0000-000000000200"
    batch_id = "00000000-0000-0000-0000-000000000300"

    class CompositeRepository:
        async def approve_continuation(self, parent_plan_id: str, **values: object) -> None:
            captured.update({"parent_plan_id": parent_plan_id, **values})
            raise ValueError("intentional audit capture")

    body = {
        "selection_checksum": "a" * 64,
        "lineage_checksum": "b" * 64,
        "base_snapshot_checksum": "c" * 64,
        "approved_credit_ceiling": 10,
        "reason": "repair only unresolved lineage evidence",
        "retailer_ids": ["aldi_us"],
        "recovery_batch_id": batch_id,
    }
    app = create_app()
    app.dependency_overrides[get_composite_evidence_repository] = CompositeRepository
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        response = await client.post(
            f"/api/v1/collection-recovery-plans/{plan_id}/continuations",
            headers={"X-RCI-Actor": "forged-client-principal"},
            json=body,
        )
        invalid = await client.post(
            f"/api/v1/collection-recovery-plans/{plan_id}/continuations",
            json={**body, "maximum_tasks": 999_999},
        )
        over_retailer_cap = await client.post(
            f"/api/v1/collection-recovery-plans/{plan_id}/continuations",
            json={**body, "retailer_ids": [f"retailer-{index}" for index in range(101)]},
        )

    assert response.status_code == 409
    assert captured["parent_plan_id"] == plan_id
    assert captured["approved_by"] == "authenticated-platform-admin"
    assert captured["recovery_batch_id"] == batch_id
    assert invalid.status_code == 422
    assert over_retailer_cap.status_code == 422


async def test_production_recovery_controls_require_admin_token(monkeypatch: Any) -> None:
    class CompositeRepository:
        async def launch_exact_recovery(self, plan_id: str) -> RecoveryLaunchRecord:
            raise AssertionError(f"unauthorized request reached repository for {plan_id}")

        async def create_recovery_batch(self, **values: object) -> None:
            raise AssertionError(f"unauthorized request reached repository: {values}")

        async def preview_continuation(self, plan_id: str, **values: object) -> None:
            raise AssertionError(
                f"unauthorized continuation preview reached repository: {plan_id} {values}"
            )

        async def approve_continuation(self, plan_id: str, **values: object) -> None:
            raise AssertionError(
                f"unauthorized continuation approval reached repository: {plan_id} {values}"
            )

        async def preview_scope_projection(self, run_id: str, **values: object) -> None:
            raise AssertionError(
                f"unauthorized scope projection preview reached repository: {run_id} {values}"
            )

    class CollectionRepository:
        async def retry_failed(self, run_id: str) -> int:
            raise AssertionError(f"unauthorized retry reached repository for {run_id}")

    monkeypatch.setenv("PRODUCT_PACK_ADMIN_TOKEN", "private-recovery-token")
    app = create_app(AppSettings(app_env="production"))
    app.dependency_overrides[get_composite_evidence_repository] = CompositeRepository
    app.dependency_overrides[get_collection_service] = CollectionRepository
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/collection-recovery-plans/00000000-0000-0000-0000-000000000200/launch"
        )
        batch_response = await client.post(
            "/api/v1/collection-recovery-batches",
            json={
                "authorization_id": "00000000-0000-0000-0000-000000000099",
            },
        )
        retry_response = await client.post(
            "/api/v1/collection-runs/00000000-0000-0000-0000-000000000101/retry-failed"
        )
        continuation_preview = await client.get(
            "/api/v1/collection-recovery-plans/"
            "00000000-0000-0000-0000-000000000200/continuation-preview"
        )
        continuation_approval = await client.post(
            "/api/v1/collection-recovery-plans/00000000-0000-0000-0000-000000000200/continuations",
            json={
                "selection_checksum": "a" * 64,
                "lineage_checksum": "b" * 64,
                "base_snapshot_checksum": "c" * 64,
                "approved_credit_ceiling": 1,
                "reason": "must remain admin-only",
                "recovery_batch_id": "00000000-0000-0000-0000-000000000300",
            },
        )
        scope_projection_preview = await client.get(
            "/api/v1/collection-runs/00000000-0000-0000-0000-000000000101/scope-projection-preview",
            params={
                "retailer_id": "wegmans_us",
                "projection_kind": "limited_provider_footprint",
            },
        )

    assert response.status_code == 401
    assert "administrator" in response.json()["detail"].lower()
    assert batch_response.status_code == 401
    assert retry_response.status_code == 401
    assert continuation_preview.status_code == 401
    assert continuation_approval.status_code == 401
    assert scope_projection_preview.status_code == 401


async def test_batch_creation_accepts_only_offline_authorization_id() -> None:
    captured: dict[str, object] = {}

    class CompositeRepository:
        async def create_recovery_batch(self, **values: object) -> None:
            captured.update(values)
            raise ValueError("intentional audit capture")

    app = create_app()
    app.dependency_overrides[get_composite_evidence_repository] = CompositeRepository
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        response = await client.post(
            "/api/v1/collection-recovery-batches",
            headers={"X-RCI-Actor": "forged-client-principal"},
            json={
                "authorization_id": "00000000-0000-0000-0000-000000000099",
            },
        )

    assert response.status_code == 409
    assert captured == {"authorization_id": "00000000-0000-0000-0000-000000000099"}


async def test_recovery_controls_reject_malformed_or_client_defined_authorization() -> None:
    class CompositeRepository:
        async def create_recovery_batch(self, **values: object) -> None:
            raise AssertionError(f"invalid request reached repository: {values}")

    app = create_app()
    app.dependency_overrides[get_composite_evidence_repository] = CompositeRepository
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        malformed = await client.post(
            "/api/v1/collection-recovery-batches",
            json={"authorization_id": "not-a-uuid"},
        )
        client_defined = await client.post(
            "/api/v1/collection-recovery-batches",
            json={
                "authorization_id": "00000000-0000-0000-0000-000000000099",
                "approved_credit_ceiling": 999_999,
                "unit_cost_usd": "0.001",
            },
        )
        malformed_path = await client.post("/api/v1/collection-recovery-plans/not-a-uuid/launch")

    assert malformed.status_code == 422
    assert client_defined.status_code == 422
    assert malformed_path.status_code == 422


async def test_invalid_collection_definition_is_rejected() -> None:
    service = _service()
    app = create_app()
    app.dependency_overrides[get_collection_service] = lambda: service
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        response = await client.post("/api/v1/collection-definitions", json={"id": "invalid"})
        assert response.status_code == 422
        assert "benchmark_retailer" in response.json()["detail"]

        invalid_cron = _config()
        invalid_cron["schedule"] = {
            "type": "cron",
            "cron": "61 * * * *",
            "timezone": "UTC",
        }
        response = await client.post("/api/v1/collection-definitions", json=invalid_cron)
        assert response.status_code == 422
        assert "outside 0..59" in response.json()["detail"]

        invalid_timezone = _config()
        invalid_timezone["schedule"] = {
            "type": "manual",
            "cron": None,
            "timezone": "Not/AZone",
        }
        response = await client.post("/api/v1/collection-definitions", json=invalid_timezone)
        assert response.status_code == 422
        assert "unknown timezone" in response.json()["detail"]


async def test_geography_estimate_and_launch_are_checksum_guarded() -> None:
    service = _service()
    app = create_app()
    app.dependency_overrides[get_collection_service] = lambda: service
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        request = {
            "primary_retailer_id": "walmart_us",
            "competitor_retailer_ids": ["aldi_us", "amazon_us_same_day"],
            "country": "USA",
            "primary_selection": {"mode": "custom_zips", "zipcodes": ["06000"]},
            "competitor_correspondence": {"mode": "same_zip"},
            "exclusions": [],
        }
        geography = await client.post("/api/v1/collection-geography-resolutions", json=request)
        assert geography.status_code == 201
        assert geography.json()["counts"] == {
            "total": 3,
            "primary": 1,
            "competitors": {"aldi_us": 1, "amazon_us_same_day": 1},
        }

        config = _approved_config(geography.json())
        estimate = await client.post("/api/v1/collection-scope-estimates", json=config)
        assert estimate.status_code == 200
        assert estimate.json()["estimated_total_credits"] == 5

        changed = dict(config)
        changed["name"] = "Changed after approval"
        rejected = await client.post(
            "/api/v1/collection-launches",
            json={"config": changed, "estimate_id": estimate.json()["id"]},
        )
        assert rejected.status_code == 409
        assert "changed after approval" in rejected.json()["detail"]
        definitions_after_rejection = await client.get("/api/v1/collection-definitions")
        assert definitions_after_rejection.json() == []

        launched = await client.post(
            "/api/v1/collection-launches",
            json={"config": config, "estimate_id": estimate.json()["id"]},
        )
        assert launched.status_code == 201
        assert launched.json()["estimated_credits"] == 5
        repeated_launch = await client.post(
            "/api/v1/collection-launches",
            json={"config": config, "estimate_id": estimate.json()["id"]},
        )
        assert repeated_launch.status_code == 201
        assert repeated_launch.json()["id"] == launched.json()["id"]
