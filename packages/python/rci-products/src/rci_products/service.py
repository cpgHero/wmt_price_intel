"""Durable Product Details enrichment orchestration."""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from rci_products.client import ProductDetailTransportFailure
from rci_products.models import ProductDetailFetchResult, ProductDetailJob
from rci_products.repository import ProductDetailRepository

logger = logging.getLogger(__name__)

DEFAULT_PRODUCT_DETAIL_CACHE_TTL_SECONDS = 2_592_000


class ProductDetailFetcher(Protocol):
    async def fetch(self, job: ProductDetailJob) -> ProductDetailFetchResult: ...


class ProductDetailWorker:
    def __init__(
        self,
        repository: ProductDetailRepository,
        fetcher: ProductDetailFetcher,
        *,
        worker_id: str,
        claim_limit: int = 1,
        lease_seconds: int = 300,
        cache_ttl_seconds: int = DEFAULT_PRODUCT_DETAIL_CACHE_TTL_SECONDS,
    ) -> None:
        self._repository = repository
        self._fetcher = fetcher
        self._worker_id = worker_id
        self._claim_limit = claim_limit
        self._lease_seconds = lease_seconds
        self._cache_ttl_seconds = cache_ttl_seconds
        self._inflight: set[asyncio.Task[None]] = set()

    async def run_once(self) -> int:
        await self._reap_completed()
        capacity = max(self._claim_limit - len(self._inflight), 0)
        jobs = (
            await self._repository.claim(
                self._worker_id,
                limit=capacity,
                lease_seconds=self._lease_seconds,
            )
            if capacity
            else []
        )
        self._inflight.update(asyncio.create_task(self._execute(job)) for job in jobs)
        if self._inflight:
            done, _ = await asyncio.wait(
                self._inflight,
                return_when=asyncio.FIRST_COMPLETED,
            )
            await self._reap(done)
        return len(jobs)

    async def close(self) -> None:
        """Finish already-leased calls before the transport is closed."""

        if not self._inflight:
            return
        tasks = tuple(self._inflight)
        self._inflight.clear()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                logger.error(
                    "Product Details in-flight task failed during shutdown",
                    exc_info=(type(result), result, result.__traceback__),
                    extra={"event": "product_detail_shutdown_task_failed"},
                )

    async def _reap_completed(self) -> None:
        await self._reap({task for task in self._inflight if task.done()})

    async def _reap(self, tasks: set[asyncio.Task[None]]) -> None:
        if not tasks:
            return
        self._inflight.difference_update(tasks)
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                logger.error(
                    "Product Details task failed; the durable lease will recover it",
                    exc_info=(type(result), result, result.__traceback__),
                    extra={"event": "product_detail_task_failed"},
                )

    async def _execute(self, job: ProductDetailJob) -> None:
        finished = asyncio.Event()
        heartbeat = asyncio.create_task(self._heartbeat(job.id, finished))
        try:
            try:
                result = await self._fetcher.fetch(job)
            except ProductDetailTransportFailure as exc:
                await self._repository.fail_transport(
                    job,
                    self._worker_id,
                    str(exc),
                    retry_delay_seconds=exc.retry_delay_seconds,
                )
                logger.warning(
                    "Product Details transport failed",
                    extra={
                        "event": "product_detail_transport_failed",
                        "job_id": job.id,
                        "retailer_id": job.retailer_id,
                    },
                )
                return
            snapshot = await self._repository.record_fetch(
                job,
                self._worker_id,
                result,
                cache_ttl_seconds=self._cache_ttl_seconds,
            )
            logger.info(
                "Product Details attempt recorded",
                extra={
                    "event": "product_detail_attempt_recorded",
                    "job_id": job.id,
                    "snapshot_id": snapshot.id,
                    "retailer_id": job.retailer_id,
                    "http_status": result.http_status,
                    "billable_credits": result.credits,
                    "succeeded": result.normalized is not None,
                },
            )
        finally:
            finished.set()
            await heartbeat

    async def _heartbeat(self, job_id: str, finished: asyncio.Event) -> None:
        interval = max(self._lease_seconds / 3, 1)
        while not finished.is_set():
            try:
                await asyncio.wait_for(finished.wait(), timeout=interval)
            except TimeoutError:
                if not await self._repository.extend_lease(
                    job_id,
                    self._worker_id,
                    self._lease_seconds,
                ):
                    return
