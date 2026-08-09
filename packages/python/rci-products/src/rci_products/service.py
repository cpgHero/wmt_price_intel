"""Durable Product Details enrichment orchestration."""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from rci_products.client import ProductDetailTransportFailure
from rci_products.models import ProductDetailFetchResult, ProductDetailJob
from rci_products.repository import ProductDetailRepository

logger = logging.getLogger(__name__)


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
        cache_ttl_seconds: int = 604_800,
    ) -> None:
        self._repository = repository
        self._fetcher = fetcher
        self._worker_id = worker_id
        self._claim_limit = claim_limit
        self._lease_seconds = lease_seconds
        self._cache_ttl_seconds = cache_ttl_seconds

    async def run_once(self) -> int:
        jobs = await self._repository.claim(
            self._worker_id,
            limit=self._claim_limit,
            lease_seconds=self._lease_seconds,
        )
        await asyncio.gather(*(self._execute(job) for job in jobs))
        return len(jobs)

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
