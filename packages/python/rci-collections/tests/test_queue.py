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
from rci_collections.models import LocationUnit
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
                "adapter_id": "fake_walmart",
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


async def _gated_run(repository: InMemoryCollectionRepository):
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


async def test_availability_gate_claims_sample_first_and_stops_on_excess_404s() -> None:
    repository = _gated_repository()
    run = await _gated_run(repository)

    preflight = await repository.claim_tasks("gate-worker", claim_limit=10, lease_seconds=30)
    assert len(preflight) == 2
    assert all(task.is_preflight for task in preflight)
    for task in preflight:
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
    retried_preflight = await repository.claim_tasks(
        "retry-worker", claim_limit=10, lease_seconds=30
    )
    assert len(retried_preflight) == 2
    assert all(task.is_preflight for task in retried_preflight)
    for task in retried_preflight:
        assert await repository.complete_success(
            task.id,
            "retry-worker",
            http_status=200,
            result_count=1,
            next_task=None,
        )
    released = await repository.claim_tasks("released-worker", claim_limit=10, lease_seconds=30)
    assert len(released) == 3


async def test_availability_gate_releases_remaining_tasks_at_threshold() -> None:
    repository = _gated_repository()
    run = await _gated_run(repository)
    preflight = await repository.claim_tasks("gate-worker", claim_limit=10, lease_seconds=30)
    assert await repository.complete_success(
        preflight[0].id,
        "gate-worker",
        http_status=200,
        result_count=1,
        next_task=None,
    )
    assert await repository.complete_failure(
        preflight[1].id,
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
    preflight = await repository.claim_tasks("gate-worker", claim_limit=10, lease_seconds=30)
    assert len(preflight) == 4

    for task in preflight:
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

    # The combined 404 rate is exactly 50%, but Walmart's retailer-specific
    # rate is 100%, so the gate must fail closed and cancel both remaining tasks.
    assert not await repository.claim_tasks("collection-worker", claim_limit=10, lease_seconds=30)
    final = await repository.get_run(run.id)
    usage = await repository.usage(run.id)
    assert final is not None and usage is not None
    assert final.availability_gate_status == "failed"
    assert usage.cancelled_tasks == 2


def test_postgres_availability_gate_groups_preflight_by_retailer() -> None:
    source = inspect.getsource(PostgresCollectionRepository._reconcile_run)
    assert "GROUP BY retailer_id" in source
    assert "availability preflight failed by retailer" in source
