from __future__ import annotations

from pathlib import Path

from httpx import ASGITransport, AsyncClient

from rci_api.collections import get_collection_service
from rci_api.main import create_app
from rci_collections import (
    CollectionPlanner,
    CollectionRetailerCatalog,
    InMemoryCollectionRepository,
)
from rci_collections.models import LocationUnit
from rci_collections.service import CollectionService

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
                "adapter_id": "fake_walmart",
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
    repository = InMemoryCollectionRepository(units)
    catalog = CollectionRetailerCatalog.from_path(
        REPOSITORY_ROOT / "config" / "retailer-catalog.json"
    )
    return CollectionService(
        repository,
        CollectionPlanner(repository, catalog),
        REPOSITORY_ROOT,
    )


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

        created = await client.post("/api/v1/collection-definitions/api-collection/runs")
        assert created.status_code == 201
        run_id = created.json()["id"]

        tasks = await client.get(f"/api/v1/collection-runs/{run_id}/tasks")
        assert len(tasks.json()) == 2
        assert all(item["status"] == "pending" for item in tasks.json())

        usage = await client.get(f"/api/v1/collection-runs/{run_id}/usage")
        assert usage.json()["estimated_pages"] == 2
        assert usage.json()["actual_credits"] == 0

        monitor = await client.get(f"/api/v1/collection-runs/{run_id}/monitor")
        assert monitor.status_code == 200
        assert monitor.json()["configured_global_rps"] == 2
        assert monitor.json()["retry_attempts"] == 0
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

        cancelled = await client.post(f"/api/v1/collection-runs/{run_id}/cancel")
        assert cancelled.json()["status"] == "cancelled"


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
