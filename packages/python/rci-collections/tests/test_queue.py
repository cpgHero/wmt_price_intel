from __future__ import annotations

import asyncio
import inspect
from pathlib import Path

import pytest

from rci_collections import (
    CollectionPlanner,
    CollectionRetailerCatalog,
    FakeProvider,
    InMemoryCollectionRepository,
    QueueWorker,
)
from rci_collections.models import LocationUnit, ProviderPage, QueueTask
from rci_collections.planner import canonical_checksum
from rci_collections.repository import PostgresCollectionRepository
from rci_collections.service import CollectionBudgetError, CollectionService

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def _config(*, max_pages: int = 1, budget: int | None = None) -> dict[str, object]:
    return {
        "id": "queue-test",
        "name": "Queue Test Collection",
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
        "budget": {
            "max_credits_per_run": budget,
            "block_if_estimate_exceeds_budget": True,
        },
    }


def _repository(size: int) -> InMemoryCollectionRepository:
    return InMemoryCollectionRepository(
        [
            LocationUnit(
                id=f"location-{index}",
                retailer_id="walmart_us",
                zipcode=f"{index:05d}",
                store_number=f"{index:04d}",
                state="IL",
                country="USA",
            )
            for index in range(size)
        ]
    )


def _gated_repository(size: int = 5) -> InMemoryCollectionRepository:
    return InMemoryCollectionRepository(
        [
            LocationUnit(
                id=f"aldi-location-{index}",
                retailer_id="aldi_us",
                zipcode=f"45{index:03d}",
                store_number=f"046-{index:03d}",
                state="OH",
                country="USA",
            )
            for index in range(size)
        ]
    )


async def _gated_run(
    repository: InMemoryCollectionRepository,
    *,
    gate_overrides: dict[str, object] | None = None,
):
    config = _config()
    config["benchmark_retailer"] = "aldi_us"
    config["retailers"] = [
        {
            "retailer_id": "aldi_us",
            "adapter_id": "metricscart_new_aldi_serp_zipcode",
            "enabled": True,
            "request_overrides": {},
        }
    ]
    config["availability_gate"] = {
        "enabled": True,
        "retailer_ids": ["aldi_us"],
        "sample_size_per_retailer": 2,
        "max_billable_404_rate": 0.5,
    }
    config["availability_gate"].update(gate_overrides or {})
    definition = await repository.publish_definition(config, canonical_checksum(config))
    planner = CollectionPlanner(
        repository,
        CollectionRetailerCatalog.from_path(REPOSITORY_ROOT / "config" / "retailer-catalog.json"),
    )
    return await repository.create_run(definition, await planner.plan(config))


async def _run(repository: InMemoryCollectionRepository, *, max_pages: int = 1):
    config = _config(max_pages=max_pages)
    definition = await repository.publish_definition(config, canonical_checksum(config))
    planner = CollectionPlanner(
        repository,
        CollectionRetailerCatalog.from_path(REPOSITORY_ROOT / "config" / "retailer-catalog.json"),
    )
    return await repository.create_run(definition, await planner.plan(config))


async def test_multiple_workers_never_claim_or_execute_a_task_twice() -> None:
    repository = _repository(50)
    run = await _run(repository)
    provider = FakeProvider(latency_seconds=0.001)
    workers = [
        QueueWorker(
            repository,
            provider,
            worker_id=f"worker-{index}",
            claim_limit=3,
            lease_seconds=30,
        )
        for index in range(8)
    ]

    await asyncio.gather(*(worker.drain() for worker in workers))

    assert len(provider.calls) == 50
    assert len(set(provider.calls)) == 50
    usage = await repository.usage(run.id)
    assert usage is not None
    assert usage.succeeded_tasks == 50
    assert usage.actual_success_pages == 50
    assert usage.actual_credits == 50
    completed = await repository.get_run(run.id)
    assert completed is not None
    assert completed.status == "succeeded"


async def test_worker_refills_a_free_slot_without_waiting_for_slowest_request() -> None:
    repository = _repository(3)
    run = await _run(repository)
    release_slow = asyncio.Event()
    third_started = asyncio.Event()

    class VariableLatencyProvider:
        def __init__(self) -> None:
            self.calls: list[str] = []
            self.slow_task_id: str | None = None

        async def fetch(self, task: QueueTask) -> ProviderPage:
            self.calls.append(task.id)
            if self.slow_task_id is None:
                self.slow_task_id = task.id
                await release_slow.wait()
            elif len(self.calls) >= 3:
                third_started.set()
            await asyncio.sleep(0)
            return ProviderPage(http_status=200, result_count=1)

    provider = VariableLatencyProvider()
    worker = QueueWorker(
        repository,
        provider,
        worker_id="rolling-worker",
        claim_limit=2,
        lease_seconds=30,
    )

    assert await asyncio.wait_for(worker.run_once(), timeout=1) == 1
    await asyncio.wait_for(third_started.wait(), timeout=1)
    assert len(provider.calls) == 3
    assert provider.slow_task_id in provider.calls

    release_slow.set()
    assert await worker.drain() == 2
    usage = await repository.usage(run.id)
    assert usage is not None
    assert usage.succeeded_tasks == 3


async def test_worker_retailer_concurrency_capacity_prevents_slow_lane_monopoly() -> None:
    repository = _repository(3)
    await _run(repository)

    claimed = await repository.claim_tasks(
        "capacity-worker",
        claim_limit=3,
        lease_seconds=30,
        active_retailer_counts={"walmart_us": 2},
        retailer_concurrency_limit=2,
    )

    assert claimed == []


async def test_expired_lease_is_reclaimed_and_stale_owner_cannot_complete() -> None:
    repository = _repository(1)
    run = await _run(repository)
    original = (await repository.claim_tasks("worker-a", claim_limit=1, lease_seconds=30))[0]
    await repository.expire_lease_for_test(original.id)
    assert not await repository.complete_success(
        original.id,
        "worker-a",
        http_status=200,
        result_count=1,
        next_task=None,
    )

    reclaimed = (await repository.claim_tasks("worker-b", claim_limit=1, lease_seconds=30))[0]

    assert reclaimed.id == original.id
    assert reclaimed.attempt_count == 2
    assert (
        await repository.complete_success(
            original.id,
            "worker-a",
            http_status=200,
            result_count=1,
            next_task=None,
        )
        is False
    )
    assert (
        await repository.complete_success(
            reclaimed.id,
            "worker-b",
            http_status=200,
            result_count=1,
            next_task=None,
        )
        is True
    )
    usage = await repository.usage(run.id)
    assert usage is not None
    assert usage.actual_credits == 1


async def test_retry_and_credit_accounting_are_idempotent() -> None:
    repository = _repository(1)
    run = await _run(repository)
    first = (await repository.claim_tasks("worker", claim_limit=1, lease_seconds=30))[0]
    assert await repository.complete_failure(
        first.id,
        "worker",
        failure_class="network",
        error_message="temporary",
        retryable=True,
        retry_delay_seconds=0,
    )
    second = (await repository.claim_tasks("worker", claim_limit=1, lease_seconds=30))[0]
    assert second.attempt_count == 2
    assert await repository.complete_success(
        second.id,
        "worker",
        http_status=200,
        result_count=1,
        next_task=None,
    )
    assert not await repository.complete_success(
        second.id,
        "worker",
        http_status=200,
        result_count=1,
        next_task=None,
    )
    usage = await repository.usage(run.id)
    assert usage is not None
    assert usage.actual_success_pages == 1
    assert usage.actual_credits == 1


async def test_failed_task_can_be_manually_requeued_with_attempt_budget_remaining() -> None:
    repository = _repository(1)
    run = await _run(repository)
    task = (await repository.claim_tasks("worker", claim_limit=1, lease_seconds=30))[0]
    assert await repository.complete_failure(
        task.id,
        "worker",
        failure_class="provider_5xx",
        error_message="upstream failed",
        retryable=False,
        retry_delay_seconds=0,
    )
    failed = await repository.get_run(run.id)
    assert failed is not None
    assert failed.status == "failed"

    assert await repository.retry_failed(run.id) == 1
    retried = (await repository.claim_tasks("worker", claim_limit=1, lease_seconds=30))[0]
    assert retried.attempt_count == 2


@pytest.mark.parametrize(
    "failure_class",
    ["provider_5xx", "timeout", "network", "rate_limit"],
)
async def test_nonpreflight_transient_nonbillable_failure_completes_with_warnings(
    failure_class: str,
) -> None:
    repository = _repository(2)
    run = await _run(repository)
    successful = (await repository.claim_tasks("worker", claim_limit=1, lease_seconds=30))[0]
    assert await repository.complete_success(
        successful.id,
        "worker",
        http_status=200,
        result_count=1,
        next_task=None,
    )
    failed = (await repository.claim_tasks("worker", claim_limit=1, lease_seconds=30))[0]
    assert await repository.complete_failure(
        failed.id,
        "worker",
        failure_class=failure_class,
        error_message="transient provider failure exhausted retries",
        retryable=False,
        retry_delay_seconds=0,
        http_status=503 if failure_class == "provider_5xx" else None,
        billable=False,
    )

    final = await repository.get_run(run.id)
    assert final is not None
    assert final.status == "completed_with_warnings"


@pytest.mark.parametrize(
    ("failure_class", "billable"),
    [("parse_error", False), ("provider_5xx", True)],
)
async def test_nonpreflight_hard_or_billable_failure_still_fails_run(
    failure_class: str,
    billable: bool,
) -> None:
    repository = _repository(2)
    run = await _run(repository)
    successful = (await repository.claim_tasks("worker", claim_limit=1, lease_seconds=30))[0]
    assert await repository.complete_success(
        successful.id,
        "worker",
        http_status=200,
        result_count=1,
        next_task=None,
    )
    failed = (await repository.claim_tasks("worker", claim_limit=1, lease_seconds=30))[0]
    assert await repository.complete_failure(
        failed.id,
        "worker",
        failure_class=failure_class,
        error_message="hard or billable failure",
        retryable=False,
        retry_delay_seconds=0,
        http_status=200 if billable else None,
        billable=billable,
    )

    final = await repository.get_run(run.id)
    assert final is not None
    assert final.status == "failed"


async def test_cancellation_stops_new_claims_but_finishes_claimed_task() -> None:
    repository = _repository(2)
    run = await _run(repository)
    claimed = (await repository.claim_tasks("worker", claim_limit=1, lease_seconds=30))[0]

    cancelled = await repository.cancel_run(run.id)
    assert cancelled is not None
    assert cancelled.status == "cancel_requested"
    assert not await repository.claim_tasks("other", claim_limit=10, lease_seconds=30)
    assert await repository.complete_success(
        claimed.id,
        "worker",
        http_status=200,
        result_count=1,
        next_task=None,
    )
    final = await repository.get_run(run.id)
    assert final is not None
    assert final.status == "cancelled"
    usage = await repository.usage(run.id)
    assert usage is not None
    assert usage.succeeded_tasks == 1
    assert usage.cancelled_tasks == 1
    assert usage.actual_credits == 1


async def test_pagination_stops_on_empty_and_actual_is_below_maximum() -> None:
    repository = _repository(1)
    run = await _run(repository, max_pages=3)
    worker = QueueWorker(
        repository,
        FakeProvider(),
        worker_id="worker",
        claim_limit=1,
        lease_seconds=30,
    )

    assert await worker.drain() == 2

    usage = await repository.usage(run.id)
    assert usage is not None
    assert usage.estimated_pages == 3
    assert usage.estimated_credits == 3
    assert usage.actual_success_pages == 2
    assert usage.actual_credits == 2
    assert usage.succeeded_tasks == 2


async def test_budget_blocks_run_before_tasks_are_created() -> None:
    repository = _repository(2)
    config = _config(budget=1)
    planner = CollectionPlanner(
        repository,
        CollectionRetailerCatalog.from_path(REPOSITORY_ROOT / "config" / "retailer-catalog.json"),
    )
    service = CollectionService(repository, planner, REPOSITORY_ROOT)
    await service.publish_definition(config)

    with pytest.raises(CollectionBudgetError, match="exceed run budget"):
        await service.create_run("queue-test")


def test_postgres_claim_query_uses_skip_locked() -> None:
    source = inspect.getsource(PostgresCollectionRepository.claim_tasks)
    assert "FOR UPDATE OF t SKIP LOCKED" in source
    assert "PARTITION BY e.collection_run_id, e.retailer_id" in source
    assert "q.lane_position" in source
    assert "q.retailer_position" in source
    assert "active_retailer_counts" in source


async def test_availability_gate_claims_sample_first_and_stops_on_excess_404s() -> None:
    repository = _gated_repository()
    run = await _gated_run(repository)

    preflight = []
    for _ in range(2):
        claimed = await repository.claim_tasks("gate-worker", claim_limit=10, lease_seconds=30)
        assert len(claimed) == 1 and claimed[0].is_preflight
        task = claimed[0]
        preflight.append(task)
        assert await repository.complete_failure(
            task.id,
            "gate-worker",
            failure_class="invalid_request",
            error_message="provider returned 404",
            retryable=False,
            retry_delay_seconds=0,
            http_status=404,
            billable=True,
        )

    assert not await repository.claim_tasks("other-worker", claim_limit=10, lease_seconds=30)
    final = await repository.get_run(run.id)
    usage = await repository.usage(run.id)
    assert final is not None and usage is not None
    assert final.availability_gate_status == "failed"
    assert final.status == "failed"
    assert usage.failed_tasks == 2
    assert usage.cancelled_tasks == 3
    assert usage.actual_credits == 4

    assert await repository.retry_failed(run.id) == 2
    retried_preflight = []
    for _ in range(2):
        claimed = await repository.claim_tasks("retry-worker", claim_limit=10, lease_seconds=30)
        assert len(claimed) == 1 and claimed[0].is_preflight
        task = claimed[0]
        retried_preflight.append(task)
        assert await repository.complete_success(
            task.id,
            "retry-worker",
            http_status=200,
            result_count=1,
            next_task=None,
        )
    released = await repository.claim_tasks("released-worker", claim_limit=10, lease_seconds=30)
    assert len(released) == 3


async def test_expired_preflight_lease_is_reclaimable_without_parallel_sample() -> None:
    repository = _gated_repository()
    await _gated_run(repository)
    original = (await repository.claim_tasks("gate-worker-a", claim_limit=10, lease_seconds=30))[0]
    await repository.expire_lease_for_test(original.id)

    reclaimed = await repository.claim_tasks("gate-worker-b", claim_limit=10, lease_seconds=30)

    assert len(reclaimed) == 1
    assert reclaimed[0].id == original.id
    assert reclaimed[0].attempt_count == 2


async def test_availability_gate_releases_remaining_tasks_at_threshold() -> None:
    repository = _gated_repository()
    run = await _gated_run(repository)
    preflight = await repository.claim_tasks("gate-worker", claim_limit=10, lease_seconds=30)
    assert len(preflight) == 1
    assert await repository.complete_success(
        preflight[0].id,
        "gate-worker",
        http_status=200,
        result_count=1,
        next_task=None,
    )
    assert await repository.complete_failure(
        (await repository.claim_tasks("gate-worker", claim_limit=10, lease_seconds=30))[0].id,
        "gate-worker",
        failure_class="invalid_request",
        error_message="provider returned 404",
        retryable=False,
        retry_delay_seconds=0,
        http_status=404,
        billable=True,
    )

    remaining = await repository.claim_tasks("collection-worker", claim_limit=10, lease_seconds=30)
    assert len(remaining) == 3
    assert all(not task.is_preflight for task in remaining)
    for task in remaining:
        assert await repository.complete_success(
            task.id,
            "collection-worker",
            http_status=200,
            result_count=1,
            next_task=None,
        )
    final = await repository.get_run(run.id)
    assert final is not None
    assert final.availability_gate_status == "passed"
    assert final.status == "completed_with_warnings"
    assert final.actual_credits == 10


@pytest.mark.parametrize(
    "failure_class",
    ["provider_5xx", "timeout", "network", "rate_limit"],
)
async def test_resilient_gate_tolerates_only_configured_transient_nonbillable_failure(
    failure_class: str,
) -> None:
    repository = _gated_repository(size=6)
    run = await _gated_run(
        repository,
        gate_overrides={
            "sample_size_per_retailer": 5,
            "minimum_successful_samples": 4,
            "max_transient_nonbillable_failures": 1,
        },
    )

    for _ in range(4):
        task = (await repository.claim_tasks("gate-worker", claim_limit=10, lease_seconds=30))[0]
        assert task.is_preflight
        assert await repository.complete_success(
            task.id,
            "gate-worker",
            http_status=200,
            result_count=1,
            next_task=None,
        )
    failed_sample = (await repository.claim_tasks("gate-worker", claim_limit=10, lease_seconds=30))[
        0
    ]
    assert failed_sample.is_preflight
    assert await repository.complete_failure(
        failed_sample.id,
        "gate-worker",
        failure_class=failure_class,
        error_message="transient provider failure exhausted retries",
        retryable=False,
        retry_delay_seconds=0,
        http_status=503 if failure_class == "provider_5xx" else None,
        billable=False,
    )

    released = await repository.claim_tasks("collection-worker", claim_limit=10, lease_seconds=30)
    assert len(released) == 1
    assert released[0].is_preflight is False
    monitor = await repository.monitor(run.id)
    assert monitor is not None
    gate = monitor.retailer_gates[0]
    assert gate.status == "passed"
    assert gate.successful_samples == 4
    assert gate.transient_nonbillable_failure_samples == 1
    assert gate.hard_failure_samples == 0
    assert gate.minimum_successful_samples == 4
    assert gate.max_transient_nonbillable_failures == 1


@pytest.mark.parametrize(
    ("failure_class", "http_status", "billable"),
    [
        ("invalid_request", 400, False),
        ("authentication", 401, False),
        ("schema_drift", 200, True),
        ("parse_error", 200, True),
        ("object_storage", None, False),
    ],
)
async def test_resilient_gate_never_tolerates_hard_failure_classes(
    failure_class: str,
    http_status: int | None,
    billable: bool,
) -> None:
    repository = _gated_repository(size=6)
    run = await _gated_run(
        repository,
        gate_overrides={
            "sample_size_per_retailer": 5,
            "minimum_successful_samples": 4,
            "max_transient_nonbillable_failures": 1,
        },
    )

    failed_sample = (await repository.claim_tasks("gate-worker", claim_limit=10, lease_seconds=30))[
        0
    ]
    assert await repository.complete_failure(
        failed_sample.id,
        "gate-worker",
        failure_class=failure_class,
        error_message="hard preflight failure",
        retryable=False,
        retry_delay_seconds=0,
        http_status=http_status,
        billable=billable,
    )

    assert not await repository.claim_tasks("collection-worker", claim_limit=10, lease_seconds=30)
    final = await repository.get_run(run.id)
    monitor = await repository.monitor(run.id)
    assert final is not None and monitor is not None
    assert final.availability_gate_status == "failed"
    assert monitor.retailer_gates[0].hard_failure_samples == 1
    assert monitor.retailer_gates[0].reason == "1 hard non-404 failure(s)"


async def test_legacy_gate_still_blocks_transient_failure_without_explicit_quorum() -> None:
    repository = _gated_repository(size=3)
    run = await _gated_run(repository)
    failed_sample = (await repository.claim_tasks("gate-worker", claim_limit=10, lease_seconds=30))[
        0
    ]
    assert await repository.complete_failure(
        failed_sample.id,
        "gate-worker",
        failure_class="provider_5xx",
        error_message="transient provider failure exhausted retries",
        retryable=False,
        retry_delay_seconds=0,
        http_status=503,
        billable=False,
    )

    final = await repository.get_run(run.id)
    monitor = await repository.monitor(run.id)
    assert final is not None and monitor is not None
    assert final.availability_gate_status == "failed"
    gate = monitor.retailer_gates[0]
    assert gate.minimum_successful_samples is None
    assert gate.reason == "1 terminal non-404 failure(s)"


async def test_resilient_gate_keeps_billable_404_threshold_independent() -> None:
    repository = _gated_repository(size=6)
    run = await _gated_run(
        repository,
        gate_overrides={
            "sample_size_per_retailer": 5,
            "minimum_successful_samples": 3,
            "max_transient_nonbillable_failures": 2,
            "max_billable_404_rate": 0.2,
        },
    )

    for _ in range(2):
        task = (await repository.claim_tasks("gate-worker", claim_limit=10, lease_seconds=30))[0]
        assert await repository.complete_failure(
            task.id,
            "gate-worker",
            failure_class="invalid_request",
            error_message="provider returned 404",
            retryable=False,
            retry_delay_seconds=0,
            http_status=404,
            billable=True,
        )

    final = await repository.get_run(run.id)
    monitor = await repository.monitor(run.id)
    assert final is not None and monitor is not None
    assert final.availability_gate_status == "failed"
    assert monitor.retailer_gates[0].reason == "404 rate 0.400 exceeded 0.200"


async def test_availability_gate_stops_as_soon_as_passing_is_impossible() -> None:
    repository = _gated_repository(size=7)
    config = _config()
    config["benchmark_retailer"] = "aldi_us"
    config["retailers"] = [
        {
            "retailer_id": "aldi_us",
            "adapter_id": "metricscart_new_aldi_serp_zipcode",
            "enabled": True,
            "request_overrides": {},
        }
    ]
    config["availability_gate"] = {
        "enabled": True,
        "retailer_ids": ["aldi_us"],
        "sample_size_per_retailer": 5,
        "max_billable_404_rate": 0.5,
    }
    definition = await repository.publish_definition(config, canonical_checksum(config))
    planner = CollectionPlanner(
        repository,
        CollectionRetailerCatalog.from_path(REPOSITORY_ROOT / "config/retailer-catalog.json"),
    )
    run = await repository.create_run(definition, await planner.plan(config))

    for _ in range(3):
        task = (await repository.claim_tasks("gate-worker", claim_limit=10, lease_seconds=30))[0]
        assert task.is_preflight
        assert await repository.complete_failure(
            task.id,
            "gate-worker",
            failure_class="invalid_request",
            error_message="provider returned 404",
            retryable=False,
            retry_delay_seconds=0,
            http_status=404,
            billable=True,
        )

    assert not await repository.claim_tasks("gate-worker", claim_limit=10, lease_seconds=30)
    usage = await repository.usage(run.id)
    monitor = await repository.monitor(run.id)
    assert usage is not None and monitor is not None
    assert usage.failed_tasks == 3
    assert usage.cancelled_tasks == 4
    assert monitor.retailer_gates[0].reason == "404 rate 0.600 exceeded 0.500"


async def test_availability_gate_evaluates_each_retailer_without_cross_masking() -> None:
    repository = InMemoryCollectionRepository(
        [
            LocationUnit(
                id=f"aldi-{index}",
                retailer_id="aldi_us",
                zipcode=f"45{index:03d}",
                store_number=f"046-{index:03d}",
                state="OH",
                country="USA",
            )
            for index in range(3)
        ]
        + [
            LocationUnit(
                id=f"walmart-{index}",
                retailer_id="walmart_us",
                zipcode=f"46{index:03d}",
                store_number=str(index),
                state="OH",
                country="USA",
            )
            for index in range(3)
        ]
    )
    config = _config()
    config["retailers"] = [
        {
            "retailer_id": "aldi_us",
            "adapter_id": "metricscart_new_aldi_serp_zipcode",
            "enabled": True,
            "request_overrides": {},
        },
        {
            "retailer_id": "walmart_us",
            "adapter_id": "metricscart_walmart_search_zipcode_v2",
            "enabled": True,
            "request_overrides": {},
        },
    ]
    config["availability_gate"] = {
        "enabled": True,
        "retailer_ids": ["aldi_us", "walmart_us"],
        "sample_size_per_retailer": 2,
        "max_billable_404_rate": 0.5,
    }
    definition = await repository.publish_definition(config, canonical_checksum(config))
    planner = CollectionPlanner(
        repository,
        CollectionRetailerCatalog.from_path(REPOSITORY_ROOT / "config/retailer-catalog.json"),
    )
    run = await repository.create_run(definition, await planner.plan(config))
    processed = 0
    while processed < 4:
        preflight = await repository.claim_tasks("gate-worker", claim_limit=10, lease_seconds=30)
        assert 1 <= len(preflight) <= 2
        for task in preflight:
            processed += 1
            if task.retailer_id == "aldi_us":
                assert await repository.complete_success(
                    task.id,
                    "gate-worker",
                    http_status=200,
                    result_count=1,
                    next_task=None,
                )
            else:
                assert await repository.complete_failure(
                    task.id,
                    "gate-worker",
                    failure_class="invalid_request",
                    error_message="provider returned 404",
                    retryable=False,
                    retry_delay_seconds=0,
                    http_status=404,
                    billable=True,
                )

    # Walmart fails independently while ALDI passes and releases its remaining
    # task; one unhealthy retailer must not strand healthy paid work.
    released = await repository.claim_tasks("collection-worker", claim_limit=10, lease_seconds=30)
    assert len(released) == 1
    assert released[0].retailer_id == "aldi_us"
    assert await repository.complete_success(
        released[0].id,
        "collection-worker",
        http_status=200,
        result_count=1,
        next_task=None,
    )
    final = await repository.get_run(run.id)
    usage = await repository.usage(run.id)
    assert final is not None and usage is not None
    assert final.availability_gate_status == "partial"
    assert final.status == "completed_with_warnings"
    assert usage.cancelled_tasks == 1
    monitor = await repository.monitor(run.id)
    assert monitor is not None
    assert {gate.retailer_id: gate.status for gate in monitor.retailer_gates} == {
        "aldi_us": "passed",
        "walmart_us": "failed",
    }


def test_postgres_availability_gate_groups_preflight_by_retailer() -> None:
    source = inspect.getsource(PostgresCollectionRepository._reconcile_run)
    assert "GROUP BY g.collection_run_id, g.retailer_id" in source
    assert "transient_failure_classes" in source
    assert "minimum_successful_samples" in source
    assert "max_transient_nonbillable_failures" in source
    assert "availability preflight failed by retailer" in source
    assert "retailer_id = :retailer_id AND status = 'pending'" in source
