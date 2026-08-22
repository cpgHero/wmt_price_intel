from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx

from rci_collections.models import QueueTask
from rci_collections.worker import ProviderFailure
from rci_providers.adapters import MetricsCartAdapterRegistry
from rci_providers.client import (
    MetricsCartClient,
    MetricsCartSettings,
    credential_budget_key,
)
from rci_providers.limiter import InMemoryProviderLimiter
from rci_providers.models import RetryPolicy
from rci_providers.storage import InMemoryRawObjectStore

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
CATALOG_PATH = REPOSITORY_ROOT / "config" / "retailer-catalog.json"
BASE_URL = "https://metricscart.test"


def test_credential_budget_key_is_stable_and_never_contains_plaintext_secret() -> None:
    budget_key = credential_budget_key("test-secret-key")
    assert budget_key == credential_budget_key("test-secret-key")
    assert "test-secret-key" not in budget_key


def _task(adapter_id: str, retailer_id: str, *, store: str | None) -> QueueTask:
    now = datetime.now(UTC)
    return QueueTask(
        id=f"00000000-0000-0000-0000-{len(adapter_id):012d}",
        collection_run_id="00000000-0000-0000-0000-000000000201",
        retailer_id=retailer_id,
        retailer_location_id=None,
        adapter_id=adapter_id,
        location_scope_key="zip:10001",
        zipcode="10001",
        store_number=store,
        page_number=1,
        max_pages=2,
        stop_on_empty=True,
        stop_on_short_page=False,
        credits_per_success=1 if retailer_id == "walmart_us" else 2,
        request_payload={
            "keyword": "strawberries",
            "amazon_same_day_url_template": (
                "https://www.amazon.com/s?k={{keyword}}&i=samedaystore"
            ),
            "sort": None,
            "request_overrides": {},
        },
        request_fingerprint="fingerprint",
        status="running",
        priority=100,
        attempt_count=1,
        max_attempts=5,
        available_at=now,
        locked_by="worker",
        lease_expires_at=now + timedelta(minutes=5),
        created_at=now,
    )


def _client(store: InMemoryRawObjectStore, limiter=None) -> MetricsCartClient:
    return MetricsCartClient(
        MetricsCartSettings(
            api_key="test-secret-key",
            base_url=BASE_URL,
            retry_policy=RetryPolicy(jitter=False),
        ),
        MetricsCartAdapterRegistry.from_catalog(CATALOG_PATH),
        limiter or InMemoryProviderLimiter(rps=100, rpm=1000),
        store,
    )


@pytest.mark.parametrize(
    ("adapter_id", "retailer_id", "fixture_name", "path", "store"),
    [
        (
            "metricscart_walmart_search_zipcode_v2",
            "walmart_us",
            "walmart_success.json",
            "/mc/walmart/search/zipcode/v2/",
            "2464",
        ),
        (
            "metricscart_new_aldi_serp_zipcode",
            "aldi_us",
            "aldi_success.json",
            "/mc/new_aldi/serp/zipcode",
            "473-103",
        ),
        (
            "metricscart_amazon_same_day_zipcode",
            "amazon_us_same_day",
            "amazon_success.json",
            "/mc/amazon/search/zipcode/",
            None,
        ),
    ],
)
@respx.mock
async def test_mocked_retailer_requests_persist_raw_pages_before_success(
    adapter_id: str,
    retailer_id: str,
    fixture_name: str,
    path: str,
    store: str | None,
) -> None:
    payload = json.loads((REPOSITORY_ROOT / "fixtures" / "api_samples" / fixture_name).read_text())
    route = respx.get(f"{BASE_URL}{path}").mock(return_value=httpx.Response(200, json=payload))
    object_store = InMemoryRawObjectStore()
    client = _client(object_store)

    try:
        page = await client.fetch(_task(adapter_id, retailer_id, store=store))
    finally:
        await client.close()

    assert page.result_count == 1
    assert page.raw_artifact is not None
    assert route.called
    request = route.calls.last.request
    assert request.url.params["x-api-key"] == "test-secret-key"
    assert request.url.params["page"] == "1"
    assert request.headers["accept"] == "application/json"
    assert request.headers["content-type"] == "application/json"
    raw = next(iter(object_store.objects.values()))
    assert json.loads(gzip.decompress(raw)) == payload
    assert "test-secret-key" not in json.dumps(page.raw_artifact.metadata)
    assert page.raw_artifact.storage_uri.startswith(
        "s3://test-raw/raw/provider=metricscart/run_id="
    )
    response_audit = page.raw_artifact.metadata["search_response_audit"]
    assert response_audit["contract_version"] == "1.0.0"
    assert response_audit["result_path"] == "results"
    assert response_audit["result_count"] == 1
    assert response_audit["availability_authority"] == "positive_search_price"


@pytest.mark.parametrize(
    ("status", "failure_class", "retryable", "billable"),
    [
        (400, "invalid_request", False, False),
        (401, "authentication", False, False),
        (404, "invalid_request", False, True),
        (503, "provider_5xx", True, False),
    ],
)
@respx.mock
async def test_http_failures_are_normalized_and_raw_evidence_is_retained(
    status: int, failure_class: str, retryable: bool, billable: bool
) -> None:
    respx.get(f"{BASE_URL}/mc/walmart/search/zipcode/v2/").mock(
        return_value=httpx.Response(status, json={"error": "fixture"})
    )
    object_store = InMemoryRawObjectStore()
    client = _client(object_store)

    with pytest.raises(ProviderFailure) as captured:
        await client.fetch(
            _task("metricscart_walmart_search_zipcode_v2", "walmart_us", store="2464")
        )
    await client.close()

    assert captured.value.failure_class == failure_class
    assert captured.value.retryable is retryable
    assert captured.value.billable is billable
    assert captured.value.http_status == status
    assert captured.value.raw_artifact is not None
    assert len(object_store.objects) == 1


@respx.mock
async def test_429_applies_shared_120_second_cooldown_and_retry_policy() -> None:
    fixture = json.loads(
        (REPOSITORY_ROOT / "fixtures" / "api_samples" / "metricscart_429.json").read_text()
    )
    respx.get(f"{BASE_URL}/mc/walmart/search/zipcode/v2/").mock(
        return_value=httpx.Response(fixture["http_status"], json=fixture["body"])
    )
    now = 0.0
    sleeps: list[float] = []

    def clock() -> float:
        return now

    async def sleep(seconds: float) -> None:
        nonlocal now
        sleeps.append(seconds)
        now += seconds

    limiter = InMemoryProviderLimiter(rps=100, rpm=1000, clock=clock, sleep=sleep)
    client = _client(InMemoryRawObjectStore(), limiter)

    with pytest.raises(ProviderFailure) as captured:
        await client.fetch(
            _task("metricscart_walmart_search_zipcode_v2", "walmart_us", store="2464")
        )
    assert captured.value.failure_class == "rate_limit"
    assert captured.value.retry_delay_seconds == fixture["normalized"]["backoff_seconds"]
    await limiter.acquire()
    await client.close()

    assert sleeps == [120]


@respx.mock
async def test_parse_error_is_retried_once_after_preserving_body() -> None:
    respx.get(f"{BASE_URL}/mc/walmart/search/zipcode/v2/").mock(
        return_value=httpx.Response(200, content=b"not-json")
    )
    object_store = InMemoryRawObjectStore()
    client = _client(object_store)

    with pytest.raises(ProviderFailure) as captured:
        await client.fetch(
            _task("metricscart_walmart_search_zipcode_v2", "walmart_us", store="2464")
        )
    await client.close()

    assert captured.value.failure_class == "parse_error"
    assert captured.value.retryable
    assert captured.value.billable
    assert gzip.decompress(next(iter(object_store.objects.values()))) == b"not-json"


@respx.mock
async def test_unknown_billable_response_shape_fails_closed_as_schema_drift() -> None:
    payload = {"query": {"keyword": "strawberries"}, "unexpected_products": []}
    respx.get(f"{BASE_URL}/mc/walmart/search/zipcode/v2/").mock(
        return_value=httpx.Response(200, json=payload)
    )
    object_store = InMemoryRawObjectStore()
    client = _client(object_store)

    with pytest.raises(ProviderFailure) as captured:
        await client.fetch(
            _task("metricscart_walmart_search_zipcode_v2", "walmart_us", store="2464")
        )
    await client.close()

    assert captured.value.failure_class == "schema_drift"
    assert captured.value.retryable is False
    assert captured.value.billable is True
    assert captured.value.raw_artifact is not None
    assert json.loads(gzip.decompress(next(iter(object_store.objects.values())))) == payload


@respx.mock
async def test_missing_core_field_fails_closed_without_silent_row_loss() -> None:
    payload = {
        "query": {"keyword": "strawberries"},
        "results": [
            {
                "retailer_product_id": "123",
                "price": 3.48,
                "is_sponsored": False,
                "retailer": "walmart.com",
            }
        ],
    }
    respx.get(f"{BASE_URL}/mc/walmart/search/zipcode/v2/").mock(
        return_value=httpx.Response(200, json=payload)
    )
    client = _client(InMemoryRawObjectStore())

    with pytest.raises(ProviderFailure) as captured:
        await client.fetch(
            _task("metricscart_walmart_search_zipcode_v2", "walmart_us", store="2464")
        )
    await client.close()

    assert captured.value.failure_class == "schema_drift"
    assert "name missing in 1" in str(captured.value)
