from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx

from rci_products.catalog import ProductDetailCatalog
from rci_products.client import MetricsCartProductDetailClient, StaticProductDetailLimiterRegistry
from rci_products.models import ProductDetailJob, ProductDetailRequestContext
from rci_products.storage import InMemoryProductDetailRawObjectStore
from rci_providers.client import MetricsCartSettings
from rci_providers.limiter import InMemoryProviderLimiter
from rci_providers.models import RetryPolicy

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
BASE_URL = "https://metricscart.test"


def _job(retailer_id: str = "walmart_us") -> ProductDetailJob:
    catalog = ProductDetailCatalog.from_path(REPOSITORY_ROOT)
    endpoint = catalog.get(retailer_id)
    context = ProductDetailRequestContext(
        product_id="677669806",
        zipcode="90020",
        store="2464",
        fulfillment_type="pickup",
    )
    return ProductDetailJob(
        id="00000000-0000-0000-0000-000000000101",
        run_id="00000000-0000-0000-0000-000000000102",
        canonical_product_db_id="00000000-0000-0000-0000-000000000103",
        canonical_product_id="walmart_us:677669806",
        retailer_id=retailer_id,
        endpoint=endpoint,
        context=context,
        request_checksum=context.checksum(endpoint),
        credits_per_call=endpoint.credits_per_successful_page,
        status="running",
        attempt_count=1,
        max_attempts=3,
    )


def _client(store: InMemoryProductDetailRawObjectStore, limiter=None):
    catalog = ProductDetailCatalog.from_path(REPOSITORY_ROOT)
    return MetricsCartProductDetailClient(
        MetricsCartSettings(
            api_key="test-secret-key",
            base_url=BASE_URL,
            retry_policy=RetryPolicy(jitter=False),
        ),
        catalog,
        StaticProductDetailLimiterRegistry(
            lambda _retailer: limiter or InMemoryProviderLimiter(rps=100, rpm=1000)
        ),
        store,
    )


@respx.mock
async def test_success_is_billed_once_and_raw_response_is_immutable() -> None:
    payload = json.loads(
        (REPOSITORY_ROOT / "fixtures/api_samples/metricscart_pdp_walmart_200.json").read_text()
    )
    route = respx.get(f"{BASE_URL}/mc/walmart/product/zipcode").mock(
        return_value=httpx.Response(200, json=payload)
    )
    store = InMemoryProductDetailRawObjectStore()
    client = _client(store)

    try:
        result = await client.fetch(_job())
    finally:
        await client.close()

    assert route.call_count == 1
    assert result.billable is True
    assert result.credits == 2
    assert result.normalized is not None
    assert result.normalized.identifiers["upc"] == "028400310413"
    assert json.loads(gzip.decompress(next(iter(store.objects.values())))) == payload
    request = route.calls.last.request
    assert request.url.params["x-api-key"] == "test-secret-key"
    assert "test-secret-key" not in json.dumps(result.raw_artifact.metadata)


@pytest.mark.parametrize(
    ("status", "billable", "credits", "failure_class", "retry"),
    [
        (404, True, 2, "unavailable", False),
        (429, False, 0, "rate_limit", True),
        (503, False, 0, "provider_5xx", True),
    ],
)
@respx.mock
async def test_failure_billing_and_retry_policy(
    status: int,
    billable: bool,
    credits: int,
    failure_class: str,
    retry: bool,
) -> None:
    respx.get(f"{BASE_URL}/mc/walmart/product/zipcode").mock(
        return_value=httpx.Response(status, json={"error": "fixture"})
    )
    store = InMemoryProductDetailRawObjectStore()
    client = _client(store)

    try:
        result = await client.fetch(_job())
    finally:
        await client.close()

    assert result.observed_at <= datetime.now(UTC)
    assert result.billable is billable
    assert result.credits == credits
    assert result.failure_class == failure_class
    assert result.should_retry is retry
    assert len(store.objects) == 1
