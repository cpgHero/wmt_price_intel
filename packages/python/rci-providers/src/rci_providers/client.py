"""Shared MetricsCart HTTP client."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field, replace

import httpx

from rci_collections.models import ProviderPage, QueueTask, RawArtifact
from rci_collections.worker import ProviderFailure
from rci_providers.adapters import MetricsCartAdapterRegistry
from rci_providers.limiter import ProviderLimiter
from rci_providers.models import RetryPolicy
from rci_providers.storage import RawObjectStore


def is_billable_http_status(status: int) -> bool:
    """MetricsCart bills every 2xx and 404 response page."""

    return 200 <= status < 300 or status == 404


def credential_budget_key(api_key: str) -> str:
    return f"credential-{hashlib.sha256(api_key.encode()).hexdigest()[:24]}"


@dataclass(frozen=True, slots=True)
class MetricsCartSettings:
    api_key: str
    base_url: str = "https://api.metricscart.com"
    timeout_seconds: float = 60
    max_connections: int = 256
    max_keepalive_connections: int = 128
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)

    @classmethod
    def from_env(cls) -> MetricsCartSettings:
        api_key = os.getenv("METRICSCART_API_KEY", "").strip()
        if not api_key:
            raise ValueError("METRICSCART_API_KEY is required for the MetricsCart provider")
        return cls(
            api_key=api_key,
            base_url=os.getenv("METRICSCART_API_BASE_URL", "https://api.metricscart.com"),
            timeout_seconds=float(os.getenv("METRICSCART_TIMEOUT_SECONDS", "60")),
            max_connections=int(os.getenv("METRICSCART_MAX_CONNECTIONS", "256")),
            max_keepalive_connections=int(
                os.getenv("METRICSCART_MAX_KEEPALIVE_CONNECTIONS", "128")
            ),
            retry_policy=RetryPolicy(
                initial_backoff_seconds=float(
                    os.getenv("METRICSCART_INITIAL_BACKOFF_SECONDS", "30")
                ),
                rate_limit_backoff_seconds=float(
                    os.getenv("METRICSCART_RATE_LIMIT_BACKOFF_SECONDS", "120")
                ),
                max_backoff_seconds=float(os.getenv("METRICSCART_MAX_BACKOFF_SECONDS", "900")),
                jitter=True,
            ),
        )


class MetricsCartClient:
    def __init__(
        self,
        settings: MetricsCartSettings,
        adapters: MetricsCartAdapterRegistry,
        limiter: ProviderLimiter,
        object_store: RawObjectStore,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._adapters = adapters
        self._limiter = limiter
        self._object_store = object_store
        self._owns_http_client = http_client is None
        self._http = http_client or httpx.AsyncClient(
            base_url=settings.base_url,
            timeout=settings.timeout_seconds,
            limits=httpx.Limits(
                max_connections=settings.max_connections,
                max_keepalive_connections=settings.max_keepalive_connections,
            ),
        )

    async def fetch(self, task: QueueTask) -> ProviderPage:
        try:
            adapter = self._adapters.get(task.adapter_id)
            request = adapter.build_request(task)
        except ValueError as exc:
            raise ProviderFailure(
                "invalid_request", str(exc), retryable=False, retry_delay_seconds=0
            ) from exc

        limiter_scope = f"search:{adapter.retailer_id}"
        await self._limiter.acquire(limiter_scope)
        try:
            response = await self._http.request(
                request.method,
                request.path,
                params={**request.params, "x-api-key": self._settings.api_key},
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
        except httpx.TimeoutException as exc:
            self._raise_transport("timeout", "MetricsCart request timed out", task, exc)
        except httpx.TransportError as exc:
            self._raise_transport("network", "MetricsCart network error", task, exc)

        # Propagate provider backpressure before object I/O so a bucket incident cannot
        # cause other worker replicas to continue sending requests after a known 429.
        if response.status_code == 429:
            await self._limiter.pause(self._rate_limit_delay(response, task), limiter_scope)

        try:
            artifact = await self._object_store.put_response(
                task,
                request,
                http_status=response.status_code,
                body=response.content,
                response_content_type=response.headers.get("content-type"),
            )
        except Exception as exc:
            raise ProviderFailure(
                "object_storage",
                "raw MetricsCart response could not be persisted",
                retryable=True,
                retry_delay_seconds=self._settings.retry_policy.delay(
                    "object_storage", task.attempt_count
                ),
                http_status=response.status_code,
                billable=is_billable_http_status(response.status_code),
            ) from exc

        await self._raise_for_status(response, task, artifact)
        if not response.content:
            payload: object = {}
        else:
            try:
                payload = response.json()
            except (UnicodeDecodeError, ValueError) as exc:
                raise ProviderFailure(
                    "parse_error",
                    "MetricsCart returned an invalid JSON response",
                    retryable=task.attempt_count <= 1,
                    retry_delay_seconds=self._settings.retry_policy.delay(
                        "parse_error", task.attempt_count
                    ),
                    http_status=response.status_code,
                    raw_artifact=artifact,
                    billable=True,
                ) from exc
        try:
            response_audit = adapter.audit_response(payload)
        except ValueError as exc:
            raise ProviderFailure(
                "schema_drift",
                f"MetricsCart Search response contract failed: {exc}",
                retryable=False,
                retry_delay_seconds=0,
                http_status=response.status_code,
                raw_artifact=artifact,
                billable=True,
            ) from exc
        artifact = replace(
            artifact,
            metadata={**artifact.metadata, "search_response_audit": response_audit},
        )
        results = adapter.extract_result_array(payload)
        return ProviderPage(
            http_status=response.status_code,
            result_count=len(results),
            raw_artifact=artifact,
        )

    def _raise_transport(
        self, failure_class: str, message: str, task: QueueTask, cause: Exception
    ) -> None:
        raise ProviderFailure(
            failure_class,
            message,
            retryable=True,
            retry_delay_seconds=self._settings.retry_policy.delay(
                failure_class, task.attempt_count
            ),
        ) from cause

    async def _raise_for_status(
        self, response: httpx.Response, task: QueueTask, artifact: RawArtifact
    ) -> None:
        status = response.status_code
        if 200 <= status < 300:
            return
        if status == 429:
            delay = self._rate_limit_delay(response, task)
            raise _RateLimitFailure(delay, artifact)
        if status in {401, 403}:
            failure_class, retryable = "authentication", False
        elif status in {408, 425}:
            failure_class, retryable = "timeout", True
        elif status >= 500:
            failure_class, retryable = "provider_5xx", True
        else:
            failure_class, retryable = "invalid_request", False
        raise ProviderFailure(
            failure_class,
            f"MetricsCart HTTP {status}",
            retryable=retryable,
            retry_delay_seconds=(
                self._settings.retry_policy.delay(failure_class, task.attempt_count)
                if retryable
                else 0
            ),
            http_status=status,
            raw_artifact=artifact,
            billable=is_billable_http_status(status),
        )

    @staticmethod
    def _retry_after(response: httpx.Response) -> float | None:
        try:
            return max(float(response.headers["retry-after"]), 0)
        except (KeyError, ValueError):
            return None

    def _rate_limit_delay(self, response: httpx.Response, task: QueueTask) -> float:
        return self._settings.retry_policy.delay(
            "rate_limit",
            task.attempt_count,
            retry_after=self._retry_after(response),
        )

    async def close(self) -> None:
        if self._owns_http_client:
            await self._http.aclose()

    async def __aenter__(self) -> MetricsCartClient:
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.close()


class _RateLimitFailure(ProviderFailure):
    def __init__(self, delay: float, artifact: RawArtifact) -> None:
        super().__init__(
            "rate_limit",
            "MetricsCart rate limit (429)",
            retryable=True,
            retry_delay_seconds=delay,
            http_status=429,
            raw_artifact=artifact,
        )
        self.delay = delay
