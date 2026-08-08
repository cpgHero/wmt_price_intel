from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from rci_collections import (
    CollectionPlanner,
    CollectionRetailerCatalog,
    InMemoryCollectionRepository,
    QueueWorker,
)
from rci_collections.models import LocationUnit
from rci_collections.planner import canonical_checksum
from rci_providers.adapters import MetricsCartAdapterRegistry
from rci_providers.client import MetricsCartClient, MetricsCartSettings
from rci_providers.limiter import InMemoryProviderLimiter
from rci_providers.models import RetryPolicy
from rci_providers.storage import InMemoryRawObjectStore

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
CATALOG_PATH = REPOSITORY_ROOT / "config" / "retailer-catalog.json"
BASE_URL = "https://metricscart.test"


async def _run(max_pages: int = 3):
    repository = InMemoryCollectionRepository(
        [
            LocationUnit(
                id="location-1",
                retailer_id="walmart_us",
                zipcode="10001",
                store_number="0007",
                state="NY",
                country="USA",
            )
        ]
    )
    config: dict[str, object] = {
        "id": "metricscart-pagination",
        "name": "MetricsCart Pagination",
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
                "request_overrides": {},
            }
        ],
        "geography": {"strategy": "all_retailer_locations", "country": "USA"},
        "pagination": {"max_pages": max_pages, "stop_on_empty": True},
        "delivery": {"web_report": True, "excel": False, "leadership_email": False},
    }
    definition = await repository.publish_definition(config, canonical_checksum(config))
    planner = CollectionPlanner(repository, CollectionRetailerCatalog.from_path(CATALOG_PATH))
    run = await repository.create_run(definition, await planner.plan(config))
    return repository, run


@pytest.mark.parametrize(("empty_page", "expected_pages"), [(2, 2), (None, 3)])
@respx.mock
async def test_mocked_provider_paginates_until_empty_or_configured_maximum(
    empty_page: int | None, expected_pages: int
) -> None:
    def response(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        results = [] if empty_page is not None and page >= empty_page else [{"id": page}]
        return httpx.Response(200, json={"data": {"items": results}})

    route = respx.get(f"{BASE_URL}/mc/walmart/search/zipcode/v2").mock(side_effect=response)
    repository, run = await _run()
    object_store = InMemoryRawObjectStore()
    provider = MetricsCartClient(
        MetricsCartSettings(
            api_key="test-key",
            base_url=BASE_URL,
            retry_policy=RetryPolicy(jitter=False),
        ),
        MetricsCartAdapterRegistry.from_catalog(CATALOG_PATH),
        InMemoryProviderLimiter(rps=100, rpm=1000),
        object_store,
    )
    worker = QueueWorker(
        repository,
        provider,
        worker_id="metricscart-worker",
        claim_limit=1,
        lease_seconds=30,
    )

    try:
        processed = await worker.drain()
    finally:
        await provider.close()

    usage = await repository.usage(run.id)
    tasks = await repository.list_tasks(run.id)
    assert usage is not None
    assert processed == expected_pages
    assert route.call_count == expected_pages
    assert usage.actual_success_pages == expected_pages
    assert usage.actual_credits == expected_pages
    assert len(object_store.objects) == expected_pages
    assert all(task.raw_artifact_id is not None for task in tasks)
    assert [task.page_number for task in tasks] == list(range(1, expected_pages + 1))


@respx.mock
async def test_each_billable_2xx_attempt_is_accounted_even_when_json_parse_retries() -> None:
    responses = iter(
        [
            httpx.Response(200, content=b"not-json"),
            httpx.Response(200, json={"results": []}),
        ]
    )
    route = respx.get(f"{BASE_URL}/mc/walmart/search/zipcode/v2").mock(
        side_effect=lambda _request: next(responses)
    )
    repository, run = await _run(max_pages=1)
    object_store = InMemoryRawObjectStore()
    provider = MetricsCartClient(
        MetricsCartSettings(
            api_key="test-key",
            base_url=BASE_URL,
            retry_policy=RetryPolicy(
                initial_backoff_seconds=0,
                rate_limit_backoff_seconds=120,
                max_backoff_seconds=120,
                jitter=False,
            ),
        ),
        MetricsCartAdapterRegistry.from_catalog(CATALOG_PATH),
        InMemoryProviderLimiter(rps=100, rpm=1000),
        object_store,
    )
    worker = QueueWorker(
        repository,
        provider,
        worker_id="metricscart-worker",
        claim_limit=1,
        lease_seconds=30,
    )

    try:
        assert await worker.drain() == 2
    finally:
        await provider.close()

    usage = await repository.usage(run.id)
    task = (await repository.list_tasks(run.id))[0]
    assert usage is not None
    assert route.call_count == 2
    assert usage.succeeded_tasks == 1
    assert usage.actual_success_pages == 2
    assert usage.actual_credits == 2
    assert task.billable_credits == 2
    assert len(object_store.objects) == 2
