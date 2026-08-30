"""Queue worker lifecycle with a deterministic fake provider."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Protocol

from rci_collections.models import ProviderPage, QueueTask, RawArtifact
from rci_collections.planner import next_page_seed
from rci_collections.ports import CollectionRepository

logger = logging.getLogger(__name__)


class CollectionProvider(Protocol):
    async def fetch(self, task: QueueTask) -> ProviderPage: ...


class ProviderFailure(RuntimeError):
    def __init__(
        self,
        failure_class: str,
        message: str,
        *,
        retryable: bool,
        retry_delay_seconds: float | None = None,
        http_status: int | None = None,
        raw_artifact: RawArtifact | None = None,
        billable: bool = False,
    ) -> None:
        super().__init__(message)
        self.failure_class = failure_class
        self.retryable = retryable
        self.retry_delay_seconds = retry_delay_seconds
        self.http_status = http_status
        self.raw_artifact = raw_artifact
        self.billable = billable


class FakeProvider:
    """Return one non-empty page followed by an empty successful page by default."""

    def __init__(
        self,
        result_count: Callable[[QueueTask], int] | None = None,
        *,
        latency_seconds: float = 0,
    ) -> None:
        self._result_count = result_count or (lambda task: 1 if task.page_number == 1 else 0)
        self._latency_seconds = latency_seconds
        self.calls: list[str] = []

    async def fetch(self, task: QueueTask) -> ProviderPage:
        if self._latency_seconds:
            await asyncio.sleep(self._latency_seconds)
        else:
            await asyncio.sleep(0)
        self.calls.append(task.id)
        return ProviderPage(http_status=200, result_count=self._result_count(task))


class QueueWorker:
    def __init__(
        self,
        repository: CollectionRepository,
        provider: CollectionProvider,
        *,
        worker_id: str,
        claim_limit: int = 10,
        lease_seconds: int = 300,
    ) -> None:
        self._repository = repository
        self._provider = provider
        self.worker_id = worker_id
        self.claim_limit = claim_limit
        self.lease_seconds = lease_seconds
        self._active_tasks: set[asyncio.Task[None]] = set()

    async def run_once(self) -> int:
        """Keep the bounded worker window full and return completed task count.

        Provider latency varies substantially by retailer. Waiting for every task in a
        claimed batch lets one timeout idle all otherwise-free slots. Retaining the
        unfinished tasks and refilling each completed slot preserves the durable lease
        boundary while allowing independent retailer limits to run concurrently.
        """
        await self._fill_available_slots()
        if not self._active_tasks:
            return 0

        completed, _ = await asyncio.wait(
            self._active_tasks,
            return_when=asyncio.FIRST_COMPLETED,
        )
        self._active_tasks.difference_update(completed)
        for task in completed:
            task.result()
        await self._fill_available_slots()
        return len(completed)

    async def _fill_available_slots(self) -> int:
        available_slots = self.claim_limit - len(self._active_tasks)
        if available_slots <= 0:
            return 0
        tasks = await self._repository.claim_tasks(
            self.worker_id,
            claim_limit=available_slots,
            lease_seconds=self.lease_seconds,
        )
        if tasks:
            logger.info(
                "claimed collection tasks",
                extra={
                    "event": "tasks_claimed",
                    "worker_id": self.worker_id,
                    "claimed_tasks": len(tasks),
                },
            )
        self._active_tasks.update(asyncio.create_task(self._execute(task)) for task in tasks)
        return len(tasks)

    async def close(self) -> None:
        """Finish already-leased tasks without claiming new work."""
        if not self._active_tasks:
            return
        active = tuple(self._active_tasks)
        self._active_tasks.clear()
        await asyncio.gather(*active)

    async def _execute(self, task: QueueTask) -> None:
        started = time.monotonic()
        context = {
            "run_id": task.collection_run_id,
            "task_id": task.id,
            "retailer_id": task.retailer_id,
            "location_key": task.location_scope_key,
            "page": task.page_number,
            "worker_id": self.worker_id,
            "attempt": task.attempt_count,
        }
        logger.info(
            "collection task started",
            extra={"event": "task_started", "status": "running", **context},
        )
        finished = asyncio.Event()
        heartbeat = asyncio.create_task(self._heartbeat(task.id, finished))
        try:
            try:
                page = await self._provider.fetch(task)
            finally:
                finished.set()
                await heartbeat
        except ProviderFailure as exc:
            await self._repository.complete_failure(
                task.id,
                self.worker_id,
                failure_class=exc.failure_class,
                error_message=str(exc),
                retryable=exc.retryable,
                retry_delay_seconds=(
                    exc.retry_delay_seconds
                    if exc.retry_delay_seconds is not None
                    else min(2 ** max(task.attempt_count - 1, 0), 300)
                ),
                http_status=exc.http_status,
                raw_artifact=exc.raw_artifact,
                billable=exc.billable,
            )
            logger.warning(
                "collection task failed",
                extra={
                    "event": "task_failed",
                    "status": "retry_pending" if exc.retryable else "failed",
                    "failure_class": exc.failure_class,
                    "http_status": exc.http_status,
                    "latency_ms": round((time.monotonic() - started) * 1_000, 3),
                    **context,
                },
            )
            return

        empty_stop = task.stop_on_empty and page.result_count == 0
        short_stop = (
            task.stop_on_short_page
            and page.page_size is not None
            and page.result_count < page.page_size
        )
        next_task = None if empty_stop or short_stop else next_page_seed(task)
        await self._repository.complete_success(
            task.id,
            self.worker_id,
            http_status=page.http_status,
            result_count=page.result_count,
            next_task=next_task,
            raw_artifact=page.raw_artifact,
        )
        logger.info(
            "collection task succeeded",
            extra={
                "event": "task_succeeded",
                "status": "succeeded",
                "http_status": page.http_status,
                "result_count": page.result_count,
                "latency_ms": round((time.monotonic() - started) * 1_000, 3),
                **context,
            },
        )

    async def _heartbeat(self, task_id: str, finished: asyncio.Event) -> None:
        interval = max(self.lease_seconds / 3, 0.1)
        while not finished.is_set():
            try:
                await asyncio.wait_for(finished.wait(), timeout=interval)
            except TimeoutError:
                if not await self._repository.extend_lease(
                    task_id, self.worker_id, self.lease_seconds
                ):
                    logger.warning(
                        "collection task lease could not be extended",
                        extra={
                            "event": "lease_lost",
                            "task_id": task_id,
                            "worker_id": self.worker_id,
                        },
                    )
                    return

    async def drain(self, *, max_cycles: int = 10_000) -> int:
        processed = 0
        for _ in range(max_cycles):
            claimed = await self.run_once()
            processed += claimed
            if claimed == 0:
                return processed
        raise RuntimeError("worker drain exceeded max_cycles")
