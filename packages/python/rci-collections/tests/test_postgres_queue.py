from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import text

from rci_collections.models import (
    CollectionPlan,
    CostEstimate,
    RawArtifact,
    RetailerEstimate,
    TaskSeed,
)
from rci_collections.planner import canonical_checksum
from rci_collections.repository import PostgresCollectionRepository
from rci_db import DatabaseProbe


async def _isolate_claimable_runs(database: DatabaseProbe) -> None:
    """Keep global queue-claim integration tests independent of prior test fixtures."""
    async with database.engine.begin() as connection:
        await connection.execute(
            text(
                """
                UPDATE collection_run
                SET status = 'cancelled',
                    cancel_requested_at = COALESCE(cancel_requested_at, now()),
                    completed_at = COALESCE(completed_at, now())
                WHERE status IN ('queued', 'running')
                """
            )
        )


@pytest.mark.skipif(
    not os.getenv("RCI_TEST_DATABASE_URL"),
    reason="set RCI_TEST_DATABASE_URL to run Postgres SKIP LOCKED integration",
)
async def test_postgres_workers_claim_without_duplicates() -> None:
    database = DatabaseProbe(os.environ["RCI_TEST_DATABASE_URL"])
    await _isolate_claimable_runs(database)
    repository = PostgresCollectionRepository(database.engine)
    stable_key = f"postgres-concurrency-{uuid4()}"
    config: dict[str, object] = {
        "id": stable_key,
        "name": "Postgres Concurrency Test",
        "enabled": True,
    }
    definition = await repository.publish_definition(config, canonical_checksum(config))
    seeds = tuple(
        TaskSeed(
            retailer_id="walmart_us",
            retailer_location_id=None,
            adapter_id="fake",
            location_scope_key=f"zip:{index:05d}",
            zipcode=f"{index:05d}",
            store_number=None,
            page_number=1,
            max_pages=1,
            stop_on_empty=True,
            stop_on_short_page=False,
            credits_per_success=1,
            request_payload={"page": 1, "zipcode": f"{index:05d}"},
            request_fingerprint=f"fingerprint-{index}",
        )
        for index in range(40)
    )
    plan = CollectionPlan(
        estimate=CostEstimate(
            definition_id=stable_key,
            retailers=(
                RetailerEstimate(
                    retailer_id="walmart_us",
                    location_units=40,
                    credits_per_page=1,
                    max_pages=1,
                    estimated_pages=40,
                    estimated_credits=40,
                ),
            ),
            estimated_total_pages=40,
            estimated_total_credits=40,
        ),
        initial_tasks=seeds,
    )
    try:
        run = await repository.create_run(definition, plan)
        claim_sets = await asyncio.gather(
            *(
                repository.claim_tasks(f"postgres-worker-{index}", claim_limit=8, lease_seconds=30)
                for index in range(5)
            )
        )
        claimed = [task for claim_set in claim_sets for task in claim_set]
        assert len({task.id for task in claimed}) == len(claimed)
        while len(claimed) < 40:
            refill = await repository.claim_tasks(
                "postgres-refill-worker",
                claim_limit=40 - len(claimed),
                lease_seconds=30,
            )
            assert refill
            claimed.extend(refill)
            assert len({task.id for task in claimed}) == len(claimed)
        assert len(claimed) == 40

        first = claimed[0]
        assert await repository.complete_failure(
            first.id,
            str(first.locked_by),
            failure_class="parse_error",
            error_message="billable 2xx parse failure",
            retryable=True,
            retry_delay_seconds=0,
            http_status=200,
            billable=True,
        )
        retried = (
            await repository.claim_tasks("postgres-retry-worker", claim_limit=1, lease_seconds=30)
        )[0]
        assert retried.id == first.id

        artifact = RawArtifact(
            storage_uri=f"s3://test/raw/{run.id}/{retried.id}.json.gz",
            content_type="application/json",
            byte_size=20,
            checksum="a" * 64,
            metadata={"provider": "metricscart", "attempt": 1},
        )
        completions = await asyncio.gather(
            *(
                repository.complete_success(
                    task.id,
                    str(task.locked_by),
                    http_status=200,
                    result_count=1,
                    next_task=None,
                    raw_artifact=artifact if task.id == retried.id else None,
                )
                for task in [*claimed[1:], retried]
            )
        )
        assert all(completions)
        usage = await repository.usage(run.id)
        assert usage is not None
        assert usage.succeeded_tasks == 40
        assert usage.actual_success_pages == 41
        assert usage.actual_credits == 41
        tasks = await repository.list_tasks(run.id)
        assert sum(task.raw_artifact_id is not None for task in tasks) == 1
        assert sum(task.billable_credits for task in tasks) == 41
    finally:
        await database.dispose()


@pytest.mark.skipif(
    not os.getenv("RCI_TEST_DATABASE_URL"),
    reason="set RCI_TEST_DATABASE_URL to run Postgres retailer-fairness integration",
)
async def test_postgres_claims_round_robin_across_retailer_lanes() -> None:
    database = DatabaseProbe(os.environ["RCI_TEST_DATABASE_URL"])
    await _isolate_claimable_runs(database)
    repository = PostgresCollectionRepository(database.engine)
    stable_key = f"postgres-retailer-fairness-{uuid4()}"
    config: dict[str, object] = {
        "id": stable_key,
        "name": "Postgres Retailer Fairness Test",
        "enabled": True,
    }
    definition = await repository.publish_definition(config, canonical_checksum(config))
    retailer_ids = ("aldi_us", "walmart_us")
    seeds = tuple(
        TaskSeed(
            retailer_id=retailer_id,
            retailer_location_id=None,
            adapter_id="fake",
            location_scope_key=f"{retailer_id}:{index}",
            zipcode=f"{index:05d}",
            store_number=str(index),
            page_number=1,
            max_pages=1,
            stop_on_empty=True,
            stop_on_short_page=False,
            credits_per_success=1,
            request_payload={"page": 1, "zipcode": f"{index:05d}"},
            request_fingerprint=f"{retailer_id}-fairness-{index}",
        )
        for retailer_id in retailer_ids
        for index in range(6)
    )
    plan = CollectionPlan(
        estimate=CostEstimate(
            definition_id=stable_key,
            retailers=tuple(
                RetailerEstimate(
                    retailer_id=retailer_id,
                    location_units=6,
                    credits_per_page=1,
                    max_pages=1,
                    estimated_pages=6,
                    estimated_credits=6,
                )
                for retailer_id in retailer_ids
            ),
            estimated_total_pages=12,
            estimated_total_credits=12,
        ),
        initial_tasks=seeds,
    )
    try:
        await repository.create_run(definition, plan)
        claimed = await repository.claim_tasks(
            "retailer-fairness-worker", claim_limit=2, lease_seconds=30
        )
        assert {task.retailer_id for task in claimed} == set(retailer_ids)
    finally:
        await database.dispose()


@pytest.mark.skipif(
    not os.getenv("RCI_TEST_DATABASE_URL"),
    reason="set RCI_TEST_DATABASE_URL to run Postgres retailer-gate integration",
)
async def test_postgres_retailer_gates_release_healthy_retailer_independently() -> None:
    database = DatabaseProbe(os.environ["RCI_TEST_DATABASE_URL"])
    await _isolate_claimable_runs(database)
    repository = PostgresCollectionRepository(database.engine)
    stable_key = f"postgres-retailer-gates-{uuid4()}"
    config: dict[str, object] = {
        "id": stable_key,
        "name": "Postgres Retailer Gate Test",
        "enabled": True,
    }
    definition = await repository.publish_definition(config, canonical_checksum(config))
    seeds = tuple(
        TaskSeed(
            retailer_id=retailer_id,
            retailer_location_id=None,
            adapter_id="fake",
            location_scope_key=f"{retailer_id}:{index}",
            zipcode=f"{index:05d}",
            store_number=str(index),
            page_number=1,
            max_pages=1,
            stop_on_empty=True,
            stop_on_short_page=False,
            credits_per_success=1,
            request_payload={"page": 1, "zipcode": f"{index:05d}"},
            request_fingerprint=f"{retailer_id}-fingerprint-{index}",
            is_preflight=index < 2,
        )
        for retailer_id in ("aldi_us", "walmart_us")
        for index in range(3)
    )
    plan = CollectionPlan(
        estimate=CostEstimate(
            definition_id=stable_key,
            retailers=tuple(
                RetailerEstimate(
                    retailer_id=retailer_id,
                    location_units=3,
                    credits_per_page=1,
                    max_pages=1,
                    estimated_pages=3,
                    estimated_credits=3,
                )
                for retailer_id in ("aldi_us", "walmart_us")
            ),
            estimated_total_pages=6,
            estimated_total_credits=6,
        ),
        initial_tasks=seeds,
        availability_gate={
            "enabled": True,
            "retailer_ids": ["aldi_us", "walmart_us"],
            "sample_size_per_retailer": 2,
            "max_billable_404_rate": 0.5,
        },
    )
    try:
        run = await repository.create_run(definition, plan)
        for _ in range(2):
            claimed = await repository.claim_tasks("gate-worker", claim_limit=10, lease_seconds=30)
            assert {task.retailer_id for task in claimed} == {"aldi_us", "walmart_us"}
            for task in claimed:
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

        released = await repository.claim_tasks(
            "collection-worker", claim_limit=10, lease_seconds=30
        )
        assert len(released) == 1
        assert released[0].retailer_id == "aldi_us"
        assert await repository.complete_success(
            released[0].id,
            "collection-worker",
            http_status=200,
            result_count=1,
            next_task=None,
        )
        monitor = await repository.monitor(run.id)
        assert monitor is not None
        assert {gate.retailer_id: gate.status for gate in monitor.retailer_gates} == {
            "aldi_us": "passed",
            "walmart_us": "failed",
        }
    finally:
        await database.dispose()


@pytest.mark.skipif(
    not os.getenv("RCI_TEST_DATABASE_URL"),
    reason="set RCI_TEST_DATABASE_URL to run Postgres resilient-gate integration",
)
async def test_postgres_resilient_gate_and_terminal_transient_warning_match_memory() -> None:
    database = DatabaseProbe(os.environ["RCI_TEST_DATABASE_URL"])
    await _isolate_claimable_runs(database)
    repository = PostgresCollectionRepository(database.engine)
    stable_key = f"postgres-resilient-gate-{uuid4()}"
    config: dict[str, object] = {
        "id": stable_key,
        "name": "Postgres Resilient Gate Test",
        "enabled": True,
    }
    definition = await repository.publish_definition(config, canonical_checksum(config))
    seeds = tuple(
        TaskSeed(
            retailer_id="walmart_us",
            retailer_location_id=None,
            adapter_id="fake",
            location_scope_key=f"location:walmart-{index}",
            zipcode=f"90{index:03d}",
            store_number=str(2400 + index),
            page_number=1,
            max_pages=1,
            stop_on_empty=True,
            stop_on_short_page=False,
            credits_per_success=1,
            request_payload={"page": 1, "zipcode": f"90{index:03d}"},
            request_fingerprint=f"walmart-resilient-{index}",
            is_preflight=index < 5,
        )
        for index in range(6)
    )
    plan = CollectionPlan(
        estimate=CostEstimate(
            definition_id=stable_key,
            retailers=(RetailerEstimate("walmart_us", 6, 1, 1, 6, 6),),
            estimated_total_pages=6,
            estimated_total_credits=6,
        ),
        initial_tasks=seeds,
        availability_gate={
            "enabled": True,
            "retailer_ids": ["walmart_us"],
            "sample_size_per_retailer": 5,
            "max_billable_404_rate": 0.5,
            "minimum_successful_samples": 4,
            "max_transient_nonbillable_failures": 1,
        },
    )
    try:
        run = await repository.create_run(definition, plan)
        for _ in range(4):
            task = (await repository.claim_tasks("gate-worker", claim_limit=1, lease_seconds=30))[0]
            assert task.is_preflight
            assert await repository.complete_success(
                task.id,
                "gate-worker",
                http_status=200,
                result_count=1,
                next_task=None,
            )
        failed_sample = (
            await repository.claim_tasks("gate-worker", claim_limit=1, lease_seconds=30)
        )[0]
        assert failed_sample.is_preflight
        assert await repository.complete_failure(
            failed_sample.id,
            "gate-worker",
            failure_class="provider_5xx",
            error_message="provider 500 exhausted retries",
            retryable=False,
            retry_delay_seconds=0,
            http_status=500,
            billable=False,
        )
        bulk = (await repository.claim_tasks("collection-worker", claim_limit=1, lease_seconds=30))[
            0
        ]
        assert bulk.is_preflight is False
        assert await repository.complete_failure(
            bulk.id,
            "collection-worker",
            failure_class="provider_5xx",
            error_message="provider 500 exhausted retries",
            retryable=False,
            retry_delay_seconds=0,
            http_status=500,
            billable=False,
        )

        final = await repository.get_run(run.id)
        monitor = await repository.monitor(run.id)
        assert final is not None and monitor is not None
        assert final.availability_gate_status == "passed"
        assert final.status == "completed_with_warnings"
        gate = monitor.retailer_gates[0]
        assert gate.successful_samples == 4
        assert gate.transient_nonbillable_failure_samples == 1
        assert gate.hard_failure_samples == 0
    finally:
        await database.dispose()


@pytest.mark.skipif(
    not os.getenv("RCI_TEST_DATABASE_URL"),
    reason="set RCI_TEST_DATABASE_URL to run Postgres preflight-priority integration",
)
async def test_postgres_claims_eligible_preflight_before_released_bulk_work() -> None:
    database = DatabaseProbe(os.environ["RCI_TEST_DATABASE_URL"])
    await _isolate_claimable_runs(database)
    repository = PostgresCollectionRepository(database.engine)
    stable_key = f"postgres-preflight-priority-{uuid4()}"
    config: dict[str, object] = {
        "id": stable_key,
        "name": "Postgres Preflight Priority Test",
        "enabled": True,
    }
    definition = await repository.publish_definition(config, canonical_checksum(config))
    seeds = (
        TaskSeed(
            retailer_id="walmart_us",
            retailer_location_id=None,
            adapter_id="fake",
            location_scope_key="walmart-bulk",
            zipcode="46038",
            store_number="5767",
            page_number=1,
            max_pages=1,
            stop_on_empty=True,
            stop_on_short_page=False,
            credits_per_success=1,
            request_payload={"page": 1, "zipcode": "46038"},
            request_fingerprint="walmart-bulk-fingerprint",
            priority=1,
            is_preflight=False,
        ),
        TaskSeed(
            retailer_id="aldi_us",
            retailer_location_id=None,
            adapter_id="fake",
            location_scope_key="aldi-preflight",
            zipcode="46060",
            store_number="13",
            page_number=1,
            max_pages=1,
            stop_on_empty=True,
            stop_on_short_page=False,
            credits_per_success=1,
            request_payload={"page": 1, "zipcode": "46060"},
            request_fingerprint="aldi-preflight-fingerprint",
            priority=100,
            is_preflight=True,
        ),
    )
    plan = CollectionPlan(
        estimate=CostEstimate(
            definition_id=stable_key,
            retailers=(
                RetailerEstimate("walmart_us", 1, 1, 1, 1, 1),
                RetailerEstimate("aldi_us", 1, 1, 1, 1, 1),
            ),
            estimated_total_pages=2,
            estimated_total_credits=2,
        ),
        initial_tasks=seeds,
        availability_gate={
            "enabled": True,
            "retailer_ids": ["aldi_us"],
            "sample_size_per_retailer": 1,
            "max_billable_404_rate": 0,
        },
    )
    try:
        await repository.create_run(definition, plan)
        claimed = await repository.claim_tasks(
            "preflight-priority-worker", claim_limit=1, lease_seconds=30
        )
        assert len(claimed) == 1
        assert claimed[0].retailer_id == "aldi_us"
        assert claimed[0].is_preflight is True
    finally:
        await database.dispose()
