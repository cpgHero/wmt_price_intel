from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import text

from rci_collections.composite import (
    PostgresCompositeEvidenceRepository,
    RecoveryLaunchRecord,
    RecoveryPlanRecord,
)
from rci_collections.models import (
    CollectionPlan,
    CostEstimate,
    DefinitionRecord,
    RawArtifact,
    RetailerEstimate,
    RunRecord,
    TaskSeed,
)
from rci_collections.planner import canonical_checksum
from rci_collections.repository import PostgresCollectionRepository
from rci_db import DatabaseProbe


@pytest.mark.skipif(
    not os.getenv("RCI_TEST_DATABASE_URL"),
    reason="set RCI_TEST_DATABASE_URL to run Postgres exact-recovery integration",
)
async def test_postgres_exact_recovery_launch_is_failure_only_and_idempotent() -> None:
    database = DatabaseProbe(os.environ["RCI_TEST_DATABASE_URL"])
    await _isolate_claimable_runs(database)
    collection_repository = PostgresCollectionRepository(database.engine)
    fake_request_contract = {
        "retailer_id": "walmart_us",
        "adapter_id": "fake_walmart",
        "method": "GET",
        "path": "/fake/walmart/search",
        "supported_params": ["keyword", "zipcode", "store", "page"],
        "required_params": ["keyword", "zipcode", "store", "page"],
        "default_sort": None,
        "default_request_params": {},
    }
    composite_repository = PostgresCompositeEvidenceRepository(
        database.engine, provider_request_contracts={"fake_walmart": fake_request_contract}
    )
    stable_key = f"postgres-exact-recovery-{uuid4()}"
    config: dict[str, object] = {
        "id": stable_key,
        "name": "Postgres Exact Recovery Test",
        "enabled": True,
        "benchmark_retailer": "walmart_us",
        "product_pack": {"id": "fresh_fluid_milk", "version": "1.0.0"},
        "query": {"keyword": "milk"},
        "budget": {
            "max_credits_per_run": 2,
            "max_credits_per_day": 100,
            "max_credits_per_month": 100,
        },
    }
    definition = await collection_repository.publish_definition(config, canonical_checksum(config))
    seeds = tuple(
        TaskSeed(
            retailer_id="walmart_us",
            retailer_location_id=None,
            adapter_id="fake_walmart",
            location_scope_key=f"location:{index}",
            zipcode=f"9000{index}",
            store_number=str(2400 + index),
            page_number=1,
            max_pages=1,
            stop_on_empty=True,
            stop_on_short_page=True,
            credits_per_success=1,
            request_payload={
                "keyword": "milk",
                "zipcode": f"9000{index}",
                "store_number": str(2400 + index),
                "page": 1,
                "request_overrides": {},
                "_provider_request_contract": fake_request_contract,
            },
            request_fingerprint=f"exact-recovery-{index}",
            is_preflight=True,
            max_attempts=1,
        )
        for index in range(2)
    )
    plan = CollectionPlan(
        estimate=CostEstimate(
            definition_id=stable_key,
            retailers=(RetailerEstimate("walmart_us", 2, 1, 1, 2, 2),),
            estimated_total_pages=2,
            estimated_total_credits=2,
        ),
        initial_tasks=seeds,
    )
    try:
        base_run = await collection_repository.create_run(definition, plan)
        async with database.engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    UPDATE collection_task
                    SET status = 'failed', completed_at = now(),
                        http_status = CASE location_scope_key
                          WHEN 'location:0' THEN 500 ELSE 404 END,
                        failure_class = CASE location_scope_key
                          WHEN 'location:0' THEN 'lease_exhausted' ELSE 'invalid_request' END,
                        billable_credits = CASE location_scope_key
                          WHEN 'location:0' THEN 0 ELSE 1 END
                    WHERE collection_run_id::text = :run_id
                    """
                ),
                {"run_id": base_run.id},
            )
            await connection.execute(
                text(
                    "UPDATE collection_run SET status = 'failed', actual_credits = 1, "
                    "completed_at = now() WHERE id::text = :run_id"
                ),
                {"run_id": base_run.id},
            )

        preview = await composite_repository.preview(base_run.id)
        assert preview.selected_task_count == 1
        assert preview.retailers[0].retained_billable_404s == 1
        async with database.engine.connect() as connection:
            organization_id = str(
                (
                    await connection.execute(
                        text(
                            "SELECT organization_id::text FROM collection_run "
                            "WHERE id::text = :run_id"
                        ),
                        {"run_id": base_run.id},
                    )
                ).scalar_one()
            )
        async with database.engine.begin() as connection:
            for status, reason in (
                ("revoked", "first historical approval"),
                ("revoked", "second historical approval"),
                ("active", "current approval"),
            ):
                await connection.execute(
                    text(
                        """
                        INSERT INTO collection_retailer_unavailability_approval (
                          organization_id, base_collection_run_id, retailer_id,
                          base_snapshot_checksum, reason, approved_by, status,
                          revoked_at, revoked_by
                        ) VALUES (
                          CAST(:organization_id AS uuid), CAST(:run_id AS uuid),
                          'walmart_us', :snapshot, :reason, 'postgres-test', :status,
                          CASE WHEN :status = 'revoked' THEN now() ELSE NULL END,
                          CASE WHEN :status = 'revoked' THEN 'postgres-test' ELSE NULL END
                        )
                        """
                    ),
                    {
                        "organization_id": organization_id,
                        "run_id": base_run.id,
                        "snapshot": f"snapshot-{reason}",
                        "reason": reason,
                        "status": status,
                    },
                )
            states = list(
                (
                    await connection.execute(
                        text(
                            "SELECT status FROM collection_retailer_unavailability_approval "
                            "WHERE base_collection_run_id::text = :run_id ORDER BY created_at, id"
                        ),
                        {"run_id": base_run.id},
                    )
                ).scalars()
            )
            assert states.count("revoked") == 2
            assert states.count("active") == 1
            await connection.execute(
                text(
                    "DELETE FROM collection_retailer_unavailability_approval "
                    "WHERE base_collection_run_id::text = :run_id"
                ),
                {"run_id": base_run.id},
            )
        authorization = await composite_repository.authorize_recovery_spend(
            organization_id=organization_id,
            phase_key=f"phase-13.77-test-{stable_key}",
            approved_credit_ceiling=10,
            unit_cost_usd="0.002",
            currency="USD",
            reason="aggregate exact-recovery integration budget",
            authorized_by="postgres-test",
            collection_run_ids=(base_run.id,),
        )
        repeated_authorization = await composite_repository.authorize_recovery_spend(
            organization_id=organization_id,
            phase_key=f"phase-13.77-test-{stable_key}",
            approved_credit_ceiling=10,
            unit_cost_usd="0.002000",
            currency="USD",
            reason="aggregate exact-recovery integration budget",
            authorized_by="postgres-test",
            collection_run_ids=(base_run.id,),
        )
        assert repeated_authorization.id == authorization.id
        batch = await composite_repository.create_recovery_batch(authorization_id=authorization.id)
        assert batch.reserved_credits == 1
        repeated_batch = await composite_repository.create_recovery_batch(
            authorization_id=authorization.id
        )
        assert repeated_batch.id == batch.id
        recovery_plan = await composite_repository.approve(
            base_run.id,
            selection_checksum=preview.selection_checksum,
            approved_credit_ceiling=1,
            reason="recover only the hard non-billable failure",
            approved_by="postgres-test",
            recovery_batch_id=batch.id,
        )
        replacement_plan = await composite_repository.approve(
            base_run.id,
            selection_checksum=preview.selection_checksum,
            approved_credit_ceiling=1,
            reason="replace approval without changing the immutable selection",
            approved_by="postgres-test",
            supersedes_recovery_plan_id=recovery_plan.id,
            recovery_batch_id=batch.id,
        )
        assert replacement_plan.plan_generation == recovery_plan.plan_generation + 1
        repeated_replacement = await composite_repository.approve(
            base_run.id,
            selection_checksum=preview.selection_checksum,
            approved_credit_ceiling=1,
            reason="replace approval without changing the immutable selection",
            approved_by="postgres-test",
            supersedes_recovery_plan_id=recovery_plan.id,
            recovery_batch_id=batch.id,
        )
        assert repeated_replacement.id == replacement_plan.id
        with pytest.raises(ValueError, match="only an approved"):
            await composite_repository.approve(
                base_run.id,
                selection_checksum=preview.selection_checksum,
                approved_credit_ceiling=1,
                reason="invalid repeated supersession",
                approved_by="postgres-test",
                supersedes_recovery_plan_id=recovery_plan.id,
                recovery_batch_id=batch.id,
            )
        first = await composite_repository.launch_exact_recovery(replacement_plan.id)
        repeated = await composite_repository.launch_exact_recovery(replacement_plan.id)

        assert first.collection_run_id == repeated.collection_run_id
        assert first.reused_existing_run is False
        assert repeated.reused_existing_run is True
        assert first.task_count == 1
        assert first.maximum_credits == 1
        assert first.availability_gate_status == "skipped"
        with pytest.raises(ValueError, match="already accounted through its plan"):
            await composite_repository.attach_run_to_recovery_batch(
                batch.id, first.collection_run_id
            )
        async with database.engine.connect() as connection:
            rows = list(
                (
                    await connection.execute(
                        text(
                            "SELECT location_scope_key, attempt_count, is_preflight, status "
                            "FROM collection_task WHERE collection_run_id::text = :run_id"
                        ),
                        {"run_id": first.collection_run_id},
                    )
                )
                .mappings()
                .all()
            )
            run_count = int(
                (
                    await connection.execute(
                        text(
                            "SELECT count(*) FROM collection_run "
                            "WHERE definition_version_id::text = :version_id "
                            "AND id::text <> :base_run_id"
                        ),
                        {
                            "version_id": definition.version_id,
                            "base_run_id": base_run.id,
                        },
                    )
                ).scalar_one()
            )
        assert [dict(row) for row in rows] == [
            {
                "location_scope_key": "location:0",
                "attempt_count": 0,
                "is_preflight": False,
                "status": "pending",
            }
        ]
        assert run_count == 1

        claimed = await collection_repository.claim_tasks(
            "exact-recovery-worker", claim_limit=1, lease_seconds=30
        )
        assert [task.collection_run_id for task in claimed] == [first.collection_run_id]
        assert await collection_repository.complete_success(
            claimed[0].id,
            "exact-recovery-worker",
            http_status=200,
            result_count=2,
            next_task=None,
            raw_artifact=RawArtifact(
                storage_uri=f"s3://test/recovery/{claimed[0].id}.json.gz",
                content_type="application/json",
                byte_size=100,
                checksum="b" * 64,
                metadata={"provider": "metricscart", "test": True},
            ),
        )
        ready = await composite_repository.materialize(base_run.id, (replacement_plan.id,))
        assert ready.status == "ready"
        assert ready.trust_state == "ready"
        assert ready.analysis_run_id is not None
        async with database.engine.connect() as connection:
            queued_input_set = (
                await connection.execute(
                    text(
                        "SELECT input_set_id::text FROM analysis_run "
                        "WHERE id::text = :analysis_run_id"
                    ),
                    {"analysis_run_id": ready.analysis_run_id},
                )
            ).scalar_one()
        assert str(queued_input_set) == ready.id
        status_record = await composite_repository.get_recovery_batch_status(batch.id)
        assert status_record.accounted_credits == 2
        assert status_record.remaining_credits == 8
        assert status_record.approved_amount_usd == "0.020000"
        closed = await composite_repository.close_recovery_batch(batch.id)
        assert closed.batch.status == "closed"
        assert closed.accounted_credits == 2
        assert (await composite_repository.close_recovery_batch(batch.id)).batch.status == (
            "closed"
        )

        with pytest.raises(ValueError, match="never-launched"):
            await composite_repository.approve(
                base_run.id,
                selection_checksum=preview.selection_checksum,
                approved_credit_ceiling=1,
                reason="bound plans cannot be superseded and repaid",
                approved_by="postgres-test",
                supersedes_recovery_plan_id=replacement_plan.id,
                recovery_batch_id=batch.id,
            )
    finally:
        await database.dispose()


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


@pytest.mark.skipif(
    not os.getenv("RCI_TEST_DATABASE_URL"),
    reason="set RCI_TEST_DATABASE_URL to run Postgres composite concurrency integration",
)
async def test_postgres_concurrent_recovery_batch_creation_is_one_idempotent_batch() -> None:
    database = DatabaseProbe(os.environ["RCI_TEST_DATABASE_URL"])
    collection_repository = PostgresCollectionRepository(database.engine)
    composite_repository = _postgres_composite_repository(database)
    definition: DefinitionRecord | None = None
    try:
        definition = await _publish_concurrency_definition(
            collection_repository, f"postgres-batch-create-{uuid4()}"
        )
        base_run = await _create_terminal_concurrency_run(
            database,
            collection_repository,
            definition,
            request_index=0,
            outcome="failed",
        )
        organization_id = await _run_organization_id(database, base_run.id)
        authorization = await composite_repository.authorize_recovery_spend(
            organization_id=organization_id,
            phase_key=f"postgres-batch-create-{uuid4()}",
            approved_credit_ceiling=1,
            unit_cost_usd="0.002000",
            currency="USD",
            reason="prove authorization consumption is concurrency-safe",
            authorized_by="postgres-concurrency-test",
            collection_run_ids=(base_run.id,),
        )

        batches = await asyncio.wait_for(
            asyncio.gather(
                *(
                    composite_repository.create_recovery_batch(authorization_id=authorization.id)
                    for _ in range(8)
                )
            ),
            timeout=10,
        )

        assert len({batch.id for batch in batches}) == 1
        async with database.engine.connect() as connection:
            batch_count = int(
                (
                    await connection.execute(
                        text(
                            "SELECT count(*) FROM collection_recovery_batch "
                            "WHERE spend_authorization_id::text = :authorization_id"
                        ),
                        {"authorization_id": authorization.id},
                    )
                ).scalar_one()
            )
            authorization_status = str(
                (
                    await connection.execute(
                        text(
                            "SELECT status FROM collection_spend_authorization "
                            "WHERE id::text = :authorization_id"
                        ),
                        {"authorization_id": authorization.id},
                    )
                ).scalar_one()
            )
        assert batch_count == 1
        assert authorization_status == "consumed"
    finally:
        if definition is not None:
            await _cancel_concurrency_definition_runs(database, definition.version_id)
        await database.dispose()


@pytest.mark.skipif(
    not os.getenv("RCI_TEST_DATABASE_URL"),
    reason="set RCI_TEST_DATABASE_URL to run Postgres composite concurrency integration",
)
async def test_postgres_concurrent_approvals_cannot_double_reserve_last_credit() -> None:
    database = DatabaseProbe(os.environ["RCI_TEST_DATABASE_URL"])
    collection_repository = PostgresCollectionRepository(database.engine)
    composite_repository = _postgres_composite_repository(database)
    definition: DefinitionRecord | None = None
    try:
        definition = await _publish_concurrency_definition(
            collection_repository, f"postgres-cap-boundary-{uuid4()}"
        )
        base_runs = tuple(
            [
                await _create_terminal_concurrency_run(
                    database,
                    collection_repository,
                    definition,
                    request_index=index,
                    outcome="failed",
                )
                for index in range(2)
            ]
        )
        previews = tuple([await composite_repository.preview(run.id) for run in base_runs])
        assert [preview.maximum_credits for preview in previews] == [1, 1]
        organization_id = await _run_organization_id(database, base_runs[0].id)
        authorization = await composite_repository.authorize_recovery_spend(
            organization_id=organization_id,
            phase_key=f"postgres-cap-boundary-{uuid4()}",
            approved_credit_ceiling=1,
            unit_cost_usd="0.002000",
            currency="USD",
            reason="one remaining credit may fund only one recovery selection",
            authorized_by="postgres-concurrency-test",
            collection_run_ids=tuple(run.id for run in base_runs),
        )
        batch = await composite_repository.create_recovery_batch(authorization_id=authorization.id)

        outcomes = await asyncio.wait_for(
            asyncio.gather(
                *(
                    composite_repository.approve(
                        run.id,
                        selection_checksum=preview.selection_checksum,
                        approved_credit_ceiling=preview.maximum_credits,
                        reason=f"concurrent capacity claimant {index}",
                        approved_by="postgres-concurrency-test",
                        recovery_batch_id=batch.id,
                    )
                    for index, (run, preview) in enumerate(zip(base_runs, previews, strict=True))
                ),
                return_exceptions=True,
            ),
            timeout=10,
        )

        successes = [outcome for outcome in outcomes if isinstance(outcome, RecoveryPlanRecord)]
        failures = [outcome for outcome in outcomes if isinstance(outcome, BaseException)]
        assert len(successes) == 1
        assert len(failures) == 1
        assert isinstance(failures[0], ValueError)
        assert "lacks credit capacity" in str(failures[0])
        async with database.engine.connect() as connection:
            batch_row = (
                (
                    await connection.execute(
                        text(
                            "SELECT reserved_credits, approved_credit_ceiling "
                            "FROM collection_recovery_batch WHERE id::text = :batch_id"
                        ),
                        {"batch_id": batch.id},
                    )
                )
                .mappings()
                .one()
            )
            plan_count = int(
                (
                    await connection.execute(
                        text(
                            "SELECT count(*) FROM collection_recovery_plan "
                            "WHERE recovery_batch_id::text = :batch_id"
                        ),
                        {"batch_id": batch.id},
                    )
                ).scalar_one()
            )
        assert int(batch_row["reserved_credits"]) == 1
        assert int(batch_row["approved_credit_ceiling"]) == 1
        assert plan_count == 1
    finally:
        if definition is not None:
            await _cancel_concurrency_definition_runs(database, definition.version_id)
        await database.dispose()


@pytest.mark.skipif(
    not os.getenv("RCI_TEST_DATABASE_URL"),
    reason="set RCI_TEST_DATABASE_URL to run Postgres composite concurrency integration",
)
async def test_postgres_supersede_vs_launch_has_one_serialized_winner() -> None:
    database = DatabaseProbe(os.environ["RCI_TEST_DATABASE_URL"])
    collection_repository = PostgresCollectionRepository(database.engine)
    composite_repository = _postgres_composite_repository(database)
    definition: DefinitionRecord | None = None
    try:
        definition = await _publish_concurrency_definition(
            collection_repository, f"postgres-supersede-launch-{uuid4()}"
        )
        base_run = await _create_terminal_concurrency_run(
            database,
            collection_repository,
            definition,
            request_index=0,
            outcome="failed",
        )
        preview = await composite_repository.preview(base_run.id)
        batch_id = await _create_concurrency_batch(
            database,
            composite_repository,
            (base_run.id,),
            approved_credit_ceiling=1,
            phase_key=f"postgres-supersede-launch-{uuid4()}",
        )
        original = await composite_repository.approve(
            base_run.id,
            selection_checksum=preview.selection_checksum,
            approved_credit_ceiling=1,
            reason="original recovery approval",
            approved_by="postgres-concurrency-test",
            recovery_batch_id=batch_id,
        )

        outcomes = await asyncio.wait_for(
            asyncio.gather(
                composite_repository.approve(
                    base_run.id,
                    selection_checksum=preview.selection_checksum,
                    approved_credit_ceiling=1,
                    reason="replacement recovery approval",
                    approved_by="postgres-concurrency-test",
                    supersedes_recovery_plan_id=original.id,
                    recovery_batch_id=batch_id,
                ),
                composite_repository.launch_exact_recovery(original.id),
                return_exceptions=True,
            ),
            timeout=10,
        )

        winners = [
            outcome
            for outcome in outcomes
            if isinstance(outcome, (RecoveryPlanRecord, RecoveryLaunchRecord))
        ]
        failures = [outcome for outcome in outcomes if isinstance(outcome, BaseException)]
        assert len(winners) == 1
        assert len(failures) == 1
        assert isinstance(failures[0], ValueError)
        async with database.engine.connect() as connection:
            plan_rows = list(
                (
                    await connection.execute(
                        text(
                            "SELECT status, recovery_collection_run_id IS NOT NULL AS launched "
                            "FROM collection_recovery_plan "
                            "WHERE base_collection_run_id::text = :base_run_id "
                            "ORDER BY plan_generation"
                        ),
                        {"base_run_id": base_run.id},
                    )
                )
                .mappings()
                .all()
            )
        if isinstance(winners[0], RecoveryLaunchRecord):
            assert [dict(row) for row in plan_rows] == [{"status": "bound", "launched": True}]
        else:
            assert [dict(row) for row in plan_rows] == [
                {"status": "superseded", "launched": False},
                {"status": "approved", "launched": False},
            ]
    finally:
        if definition is not None:
            await _cancel_concurrency_definition_runs(database, definition.version_id)
        await database.dispose()


@pytest.mark.skipif(
    not os.getenv("RCI_TEST_DATABASE_URL"),
    reason="set RCI_TEST_DATABASE_URL to run Postgres composite concurrency integration",
)
async def test_postgres_close_vs_launch_cannot_deadlock_or_close_unfinished_work() -> None:
    database = DatabaseProbe(os.environ["RCI_TEST_DATABASE_URL"])
    collection_repository = PostgresCollectionRepository(database.engine)
    composite_repository = _postgres_composite_repository(database)
    definition: DefinitionRecord | None = None
    try:
        definition = await _publish_concurrency_definition(
            collection_repository, f"postgres-close-launch-{uuid4()}"
        )
        base_run = await _create_terminal_concurrency_run(
            database,
            collection_repository,
            definition,
            request_index=0,
            outcome="failed",
        )
        preview = await composite_repository.preview(base_run.id)
        batch_id = await _create_concurrency_batch(
            database,
            composite_repository,
            (base_run.id,),
            approved_credit_ceiling=1,
            phase_key=f"postgres-close-launch-{uuid4()}",
        )
        plan = await composite_repository.approve(
            base_run.id,
            selection_checksum=preview.selection_checksum,
            approved_credit_ceiling=1,
            reason="recovery must launch before the batch can close",
            approved_by="postgres-concurrency-test",
            recovery_batch_id=batch_id,
        )

        outcomes = await asyncio.wait_for(
            asyncio.gather(
                composite_repository.close_recovery_batch(batch_id),
                composite_repository.launch_exact_recovery(plan.id),
                return_exceptions=True,
            ),
            timeout=10,
        )

        assert isinstance(outcomes[0], ValueError)
        assert "reserved recovery plan must be launched" in str(
            outcomes[0]
        ) or "exact recovery run must be terminal" in str(outcomes[0])
        assert isinstance(outcomes[1], RecoveryLaunchRecord)
        async with database.engine.connect() as connection:
            state = (
                (
                    await connection.execute(
                        text(
                            "SELECT b.status AS batch_status, p.status AS plan_status, "
                            "r.status AS run_status "
                            "FROM collection_recovery_batch b "
                            "JOIN collection_recovery_plan p ON p.recovery_batch_id = b.id "
                            "JOIN collection_run r ON r.id = p.recovery_collection_run_id "
                            "WHERE b.id::text = :batch_id"
                        ),
                        {"batch_id": batch_id},
                    )
                )
                .mappings()
                .one()
            )
        assert dict(state) == {
            "batch_status": "open",
            "plan_status": "bound",
            "run_status": "queued",
        }
    finally:
        if definition is not None:
            await _cancel_concurrency_definition_runs(database, definition.version_id)
        await database.dispose()


@pytest.mark.skipif(
    not os.getenv("RCI_TEST_DATABASE_URL"),
    reason="set RCI_TEST_DATABASE_URL to run Postgres composite concurrency integration",
)
async def test_postgres_legacy_bind_retry_is_idempotent_and_never_reopens_provider_work() -> None:
    database = DatabaseProbe(os.environ["RCI_TEST_DATABASE_URL"])
    collection_repository = PostgresCollectionRepository(database.engine)
    composite_repository = _postgres_composite_repository(database)
    definition: DefinitionRecord | None = None
    try:
        definition = await _publish_concurrency_definition(
            collection_repository, f"postgres-legacy-bind-{uuid4()}"
        )
        base_run = await _create_terminal_concurrency_run(
            database,
            collection_repository,
            definition,
            request_index=0,
            outcome="failed",
        )
        recovery_run = await _create_terminal_concurrency_run(
            database,
            collection_repository,
            definition,
            request_index=0,
            outcome="succeeded",
        )
        preview = await composite_repository.preview(base_run.id)
        batch_id = await _create_concurrency_batch(
            database,
            composite_repository,
            (base_run.id, recovery_run.id),
            approved_credit_ceiling=2,
            phase_key=f"postgres-legacy-bind-{uuid4()}",
        )
        plan = await composite_repository.approve(
            base_run.id,
            selection_checksum=preview.selection_checksum,
            approved_credit_ceiling=1,
            reason="adopt the already-terminal operational recovery",
            approved_by="postgres-concurrency-test",
            recovery_batch_id=batch_id,
            plan_mode="legacy_adoption",
        )

        outcomes = await asyncio.wait_for(
            asyncio.gather(
                composite_repository.bind_recovery_run(
                    plan.id,
                    recovery_run.id,
                    binding_mode="legacy_operational_adoption",
                ),
                composite_repository.bind_recovery_run(
                    plan.id,
                    recovery_run.id,
                    binding_mode="legacy_operational_adoption",
                ),
                composite_repository.launch_exact_recovery(plan.id),
                return_exceptions=True,
            ),
            timeout=10,
        )

        bound = [outcome for outcome in outcomes if isinstance(outcome, RecoveryPlanRecord)]
        failures = [outcome for outcome in outcomes if isinstance(outcome, BaseException)]
        assert len(bound) == 2
        assert {record.recovery_collection_run_id for record in bound} == {recovery_run.id}
        assert {record.status for record in bound} == {"bound"}
        assert len(failures) == 1
        assert isinstance(failures[0], ValueError)
        rebound = await composite_repository.bind_recovery_run(
            plan.id,
            recovery_run.id,
            binding_mode="legacy_operational_adoption",
        )
        assert rebound.status == "bound"
        assert rebound.recovery_collection_run_id == recovery_run.id
        async with database.engine.connect() as connection:
            state = (
                (
                    await connection.execute(
                        text(
                            "SELECT p.status AS plan_status, p.reservation_active, "
                            "count(*) FILTER (WHERE r.status IN ('queued','running')) "
                            "AS open_runs, "
                            "count(*) FILTER (WHERE t.status IN ('pending','running')) "
                            "AS open_tasks "
                            "FROM collection_recovery_plan p "
                            "JOIN collection_run r "
                            "  ON r.definition_version_id = "
                            "     (SELECT definition_version_id FROM collection_run "
                            "      WHERE id = p.base_collection_run_id) "
                            "LEFT JOIN collection_task t ON t.collection_run_id = r.id "
                            "WHERE p.id::text = :plan_id "
                            "GROUP BY p.status, p.reservation_active"
                        ),
                        {"plan_id": plan.id},
                    )
                )
                .mappings()
                .one()
            )
            run_count = int(
                (
                    await connection.execute(
                        text(
                            "SELECT count(*) FROM collection_run "
                            "WHERE definition_version_id::text = :version_id"
                        ),
                        {"version_id": definition.version_id},
                    )
                ).scalar_one()
            )
        assert str(state["plan_status"]) == "bound"
        assert bool(state["reservation_active"]) is False
        assert int(state["open_runs"]) == 0
        assert int(state["open_tasks"]) == 0
        assert run_count == 2
    finally:
        if definition is not None:
            await _cancel_concurrency_definition_runs(database, definition.version_id)
        await database.dispose()


_CONCURRENCY_REQUEST_CONTRACT: dict[str, object] = {
    "retailer_id": "walmart_us",
    "adapter_id": "fake_walmart",
    "method": "GET",
    "path": "/fake/walmart/search",
    "supported_params": ["keyword", "zipcode", "store", "page"],
    "required_params": ["keyword", "zipcode", "store", "page"],
    "default_sort": None,
    "default_request_params": {},
}


def _postgres_composite_repository(
    database: DatabaseProbe,
) -> PostgresCompositeEvidenceRepository:
    return PostgresCompositeEvidenceRepository(
        database.engine,
        provider_request_contracts={"fake_walmart": _CONCURRENCY_REQUEST_CONTRACT},
    )


async def _publish_concurrency_definition(
    repository: PostgresCollectionRepository, stable_key: str
) -> DefinitionRecord:
    config: dict[str, object] = {
        "id": stable_key,
        "name": "Postgres Composite Concurrency Test",
        "enabled": True,
        "benchmark_retailer": "walmart_us",
        "product_pack": {"id": "fresh_fluid_milk", "version": "1.0.0"},
        "query": {"keyword": "milk"},
        "budget": {
            "max_credits_per_run": 100,
            "max_credits_per_day": 1000,
            "max_credits_per_month": 1000,
        },
    }
    return await repository.publish_definition(config, canonical_checksum(config))


async def _create_terminal_concurrency_run(
    database: DatabaseProbe,
    repository: PostgresCollectionRepository,
    definition: DefinitionRecord,
    *,
    request_index: int,
    outcome: str,
) -> RunRecord:
    if outcome not in {"failed", "succeeded"}:
        raise ValueError(f"unsupported concurrency fixture outcome {outcome!r}")
    zipcode = f"90{request_index:03d}"
    store_number = str(2400 + request_index)
    seed = TaskSeed(
        retailer_id="walmart_us",
        retailer_location_id=None,
        adapter_id="fake_walmart",
        location_scope_key=f"location:{request_index}",
        zipcode=zipcode,
        store_number=store_number,
        page_number=1,
        max_pages=1,
        stop_on_empty=True,
        stop_on_short_page=True,
        credits_per_success=1,
        request_payload={
            "keyword": "milk",
            "zipcode": zipcode,
            "store_number": store_number,
            "page": 1,
            "request_overrides": {},
            "_provider_request_contract": _CONCURRENCY_REQUEST_CONTRACT,
        },
        request_fingerprint=f"concurrency-{request_index}-{uuid4()}",
        is_preflight=True,
        max_attempts=1,
    )
    plan = CollectionPlan(
        estimate=CostEstimate(
            definition_id=definition.stable_key,
            retailers=(RetailerEstimate("walmart_us", 1, 1, 1, 1, 1),),
            estimated_total_pages=1,
            estimated_total_credits=1,
        ),
        initial_tasks=(seed,),
    )
    run = await repository.create_run(definition, plan)
    raw_artifact_id: str | None = None
    if outcome == "succeeded":
        raw_artifact_id = await repository.record_artifact(
            run.id,
            RawArtifact(
                storage_uri=f"s3://test/concurrency/{run.id}.json.gz",
                content_type="application/json",
                byte_size=64,
                checksum=canonical_checksum({"run_id": run.id, "request_index": request_index}),
                metadata={"provider": "postgres-concurrency-test"},
            ),
        )
    async with database.engine.begin() as connection:
        if outcome == "succeeded":
            await connection.execute(
                text(
                    "UPDATE collection_task SET status = 'succeeded', completed_at = now(), "
                    "http_status = 200, result_count = 1, billable_credits = 1, "
                    "raw_artifact_id = CAST(:artifact_id AS uuid) "
                    "WHERE collection_run_id::text = :run_id"
                ),
                {"run_id": run.id, "artifact_id": raw_artifact_id},
            )
            await connection.execute(
                text(
                    "UPDATE collection_run SET status = 'succeeded', actual_success_pages = 1, "
                    "actual_credits = 1, completed_at = now() WHERE id::text = :run_id"
                ),
                {"run_id": run.id},
            )
        else:
            await connection.execute(
                text(
                    "UPDATE collection_task SET status = 'failed', completed_at = now(), "
                    "http_status = 500, failure_class = 'lease_exhausted', "
                    "billable_credits = 0 WHERE collection_run_id::text = :run_id"
                ),
                {"run_id": run.id},
            )
            await connection.execute(
                text(
                    "UPDATE collection_run SET status = 'failed', actual_credits = 0, "
                    "completed_at = now() WHERE id::text = :run_id"
                ),
                {"run_id": run.id},
            )
    updated = await repository.get_run(run.id)
    assert updated is not None
    return updated


async def _run_organization_id(database: DatabaseProbe, run_id: str) -> str:
    async with database.engine.connect() as connection:
        return str(
            (
                await connection.execute(
                    text(
                        "SELECT organization_id::text FROM collection_run WHERE id::text = :run_id"
                    ),
                    {"run_id": run_id},
                )
            ).scalar_one()
        )


async def _create_concurrency_batch(
    database: DatabaseProbe,
    repository: PostgresCompositeEvidenceRepository,
    run_ids: tuple[str, ...],
    *,
    approved_credit_ceiling: int,
    phase_key: str,
) -> str:
    organization_id = await _run_organization_id(database, run_ids[0])
    authorization = await repository.authorize_recovery_spend(
        organization_id=organization_id,
        phase_key=phase_key,
        approved_credit_ceiling=approved_credit_ceiling,
        unit_cost_usd="0.002000",
        currency="USD",
        reason="Postgres composite concurrency test authorization",
        authorized_by="postgres-concurrency-test",
        collection_run_ids=run_ids,
    )
    return (await repository.create_recovery_batch(authorization_id=authorization.id)).id


async def _cancel_concurrency_definition_runs(
    database: DatabaseProbe, definition_version_id: str
) -> None:
    """Leave no claimable work behind if a concurrency assertion fails mid-transition."""

    async with database.engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE collection_task SET status = 'cancelled', completed_at = now(), "
                "locked_by = NULL, locked_at = NULL, lease_expires_at = NULL "
                "WHERE collection_run_id IN "
                "(SELECT id FROM collection_run WHERE definition_version_id::text = :version_id) "
                "AND status IN ('pending','running')"
            ),
            {"version_id": definition_version_id},
        )
        await connection.execute(
            text(
                "UPDATE collection_run SET status = 'cancelled', "
                "cancel_requested_at = COALESCE(cancel_requested_at, now()), "
                "completed_at = COALESCE(completed_at, now()) "
                "WHERE definition_version_id::text = :version_id "
                "AND status IN ('queued','running')"
            ),
            {"version_id": definition_version_id},
        )
