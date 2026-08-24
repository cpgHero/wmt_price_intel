"""Budget-aware MetricsCart Product Details client."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine

from rci_products.adapters import MetricsCartProductDetailAdapter
from rci_products.catalog import ProductDetailCatalog
from rci_products.models import ProductDetailFetchResult, ProductDetailJob
from rci_products.storage import ProductDetailRawObjectStore
from rci_providers.client import (
    MetricsCartSettings,
    credential_budget_key,
    is_billable_http_status,
)
from rci_providers.limiter import PostgresProviderLimiter, ProviderLimiter


class ProductDetailTransportFailure(RuntimeError):
    def __init__(self, message: str, *, retry_delay_seconds: float) -> None:
        super().__init__(message)
        self.retry_delay_seconds = retry_delay_seconds


class ProductDetailLimiterRegistry(Protocol):
    def get(self, retailer_id: str) -> ProviderLimiter: ...


class ProductDetailCompositeLimiter:
    """Apply account-wide and retailer-specific permits to every PDP request."""

    def __init__(
        self,
        global_limiter: ProviderLimiter,
        retailer_limiter: ProviderLimiter,
    ) -> None:
        self._global_limiter = global_limiter
        self._retailer_limiter = retailer_limiter

    async def acquire(self, scope_key: str | None = None) -> None:
        await self._global_limiter.acquire(scope_key)
        await self._retailer_limiter.acquire(scope_key)

    async def pause(self, seconds: float, scope_key: str | None = None) -> None:
        # A provider 429 has been observed across several retailer PDP lanes at
        # the same instant. Pause both scopes so another replica cannot turn a
        # hidden account-wide throttle into repeated zero-evidence attempts.
        await self._global_limiter.pause(seconds, scope_key)
        await self._retailer_limiter.pause(seconds, scope_key)


class StaticProductDetailLimiterRegistry:
    def __init__(self, factory: Callable[[str], ProviderLimiter]) -> None:
        self._factory = factory
        self._limiters: dict[str, ProviderLimiter] = {}

    def get(self, retailer_id: str) -> ProviderLimiter:
        return self._limiters.setdefault(retailer_id, self._factory(retailer_id))


class PostgresProductDetailLimiterRegistry(StaticProductDetailLimiterRegistry):
    def __init__(
        self,
        engine: AsyncEngine,
        *,
        api_key: str,
        rps: int = 3,
        rpm: int = 180,
        global_rps: int = 2,
        global_rpm: int = 120,
    ) -> None:
        budget_key = credential_budget_key(api_key)
        global_limiter = PostgresProviderLimiter(
            engine,
            provider="metricscart:pdp:all_retailers",
            budget_key=budget_key,
            rps=global_rps,
            rpm=global_rpm,
        )
        super().__init__(
            lambda retailer_id: ProductDetailCompositeLimiter(
                global_limiter,
                PostgresProviderLimiter(
                    engine,
                    provider=f"metricscart:pdp:{retailer_id}",
                    budget_key=budget_key,
                    rps=rps,
                    rpm=rpm,
                ),
            )
        )


class MetricsCartProductDetailClient:
    def __init__(
        self,
        settings: MetricsCartSettings,
        catalog: ProductDetailCatalog,
        limiters: ProductDetailLimiterRegistry,
        object_store: ProductDetailRawObjectStore,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._catalog = catalog
        self._limiters = limiters
        self._object_store = object_store
        self._owns_http = http_client is None
        self._http = http_client or httpx.AsyncClient(
            base_url=settings.base_url,
            timeout=settings.timeout_seconds,
        )

    async def fetch(self, job: ProductDetailJob) -> ProductDetailFetchResult:
        endpoint = self._catalog.get(job.retailer_id)
        if endpoint != job.endpoint:
            raise ValueError("queued Product Details endpoint no longer matches the catalog")
        adapter = MetricsCartProductDetailAdapter(endpoint)
        request = adapter.build_request(job.context)
        limiter = self._limiters.get(job.retailer_id)
        await limiter.acquire()
        try:
            response = await self._http.request(
                request.method,
                request.path,
                params={**request.params, "x-api-key": self._settings.api_key},
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
        except httpx.TimeoutException as exc:
            raise ProductDetailTransportFailure(
                "MetricsCart Product Details request timed out",
                retry_delay_seconds=self._settings.retry_policy.delay("timeout", job.attempt_count),
            ) from exc
        except httpx.TransportError as exc:
            raise ProductDetailTransportFailure(
                "MetricsCart Product Details network error",
                retry_delay_seconds=self._settings.retry_policy.delay("network", job.attempt_count),
            ) from exc

        retry_delay = 0.0
        if response.status_code == 429:
            retry_delay = self._rate_limit_delay(response, job)
            await limiter.pause(retry_delay)
        artifact = await self._object_store.put_response(
            job,
            request,
            http_status=response.status_code,
            body=response.content,
            response_content_type=response.headers.get("content-type"),
        )
        billable = is_billable_http_status(response.status_code)
        credits = endpoint.credits_per_successful_page if billable else 0
        observed_at = datetime.now(UTC)
        if 200 <= response.status_code < 300:
            try:
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("Product Details response must be an object")
                normalized = adapter.normalize(payload, job.context)
            except (UnicodeDecodeError, ValueError) as exc:
                return ProductDetailFetchResult(
                    observed_at=observed_at,
                    http_status=response.status_code,
                    billable=billable,
                    credits=credits,
                    raw_artifact=artifact,
                    failure_class="parse_error",
                    failure_message=str(exc),
                    should_retry=False,
                )
            return ProductDetailFetchResult(
                observed_at=observed_at,
                http_status=response.status_code,
                billable=billable,
                credits=credits,
                raw_artifact=artifact,
                normalized=normalized,
            )
        if response.status_code == 429:
            failure_class, should_retry = "rate_limit", True
        elif response.status_code in {408, 425}:
            failure_class, should_retry = "timeout", True
        elif response.status_code >= 500:
            failure_class, should_retry = "provider_5xx", True
        elif response.status_code == 404:
            failure_class, should_retry = "unavailable", False
        elif response.status_code in {401, 403}:
            failure_class, should_retry = "authentication", False
        else:
            failure_class, should_retry = "invalid_request", False
        if should_retry and retry_delay <= 0:
            retry_delay = self._settings.retry_policy.delay(failure_class, job.attempt_count)
        return ProductDetailFetchResult(
            observed_at=observed_at,
            http_status=response.status_code,
            billable=billable,
            credits=credits,
            raw_artifact=artifact,
            failure_class=failure_class,
            failure_message=f"MetricsCart HTTP {response.status_code}",
            should_retry=should_retry,
            retry_delay_seconds=retry_delay,
        )

    def _rate_limit_delay(self, response: httpx.Response, job: ProductDetailJob) -> float:
        try:
            retry_after = max(float(response.headers["retry-after"]), 0)
        except (KeyError, ValueError):
            retry_after = None
        return self._settings.retry_policy.delay(
            "rate_limit", job.attempt_count, retry_after=retry_after
        )

    async def close(self) -> None:
        if self._owns_http:
            await self._http.aclose()
