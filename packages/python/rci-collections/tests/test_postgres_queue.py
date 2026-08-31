from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncTransaction

from rci_collections.composite import (
    MATERIALIZATION_WRITE_BATCH_SIZE,
    PostgresCompositeEvidenceRepository,
    RecoveryLaunchRecord,
    RecoveryPlanRecord,
    ScopeProjectionPreview,
    canonical_request_key,
    evidence_outcome,
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

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


_SCOPE_WALMART_REQUEST_CONTRACT: dict[str, object] = {
    "retailer_id": "walmart_us",
    "adapter_id": "fake_walmart",
    "method": "GET",
    "path": "/fake/walmart/search",
    "supported_params": ["keyword", "zipcode", "store", "page"],
    "required_params": ["keyword", "zipcode", "store", "page"],
    "default_sort": None,
    "default_request_params": {},
}


_SCOPE_KROGER_REQUEST_CONTRACT: dict[str, object] = {
    "retailer_id": "kroger_us",
    "adapter_id": "fake_kroger",
    "method": "GET",
    "path": "/fake/kroger/search",
    "supported_params": ["keyword", "zipcode", "store", "page"],
    "required_params": ["keyword", "zipcode", "store", "page"],
    "default_sort": None,
    "default_request_params": {},
}


@dataclass(frozen=True)
class _ScopeProjectionFixture:
    definition: DefinitionRecord
    base_run: RunRecord
    source_audit_id: str
    benchmark_task_id: str | None
    canonical_task_ids: tuple[str, ...]
    alias_task_ids: tuple[str, ...]
    gap_task_ids: tuple[str, ...]


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
    geography_resolution_id = str(uuid4())
    retailer_location_ids = [str(uuid4()) for _ in range(2)]
    async with database.engine.begin() as connection:
        organization_id = str(
            (
                await connection.execute(
                    text(
                        """
                        SELECT d.organization_id::text
                        FROM collection_definition_version v
                        JOIN collection_definition d ON d.id = v.definition_id
                        WHERE v.id::text = :version_id
                        """
                    ),
                    {"version_id": definition.version_id},
                )
            ).scalar_one()
        )
        await connection.execute(
            text(
                """
                INSERT INTO collection_geography_resolution (
                  id, organization_id, primary_retailer_id, country,
                  request, checksum, status, counts
                ) VALUES (
                  CAST(:resolution_id AS uuid), CAST(:organization_id AS uuid),
                  'walmart_us', 'USA', '{}'::jsonb, :checksum, 'ready',
                  CAST(:counts AS jsonb)
                )
                """
            ),
            {
                "resolution_id": geography_resolution_id,
                "organization_id": organization_id,
                "checksum": canonical_checksum(
                    {"test": stable_key, "locations": ["location:0", "location:1"]}
                ),
                "counts": '{"primary":2,"competitor":0}',
            },
        )
        await connection.execute(
            text(
                """
                INSERT INTO retailer_location (
                  id, retailer_id, provider, provider_location_id,
                  store_number, store_name, raw_zipcode, zipcode,
                  city, state, country, latitude, longitude, status,
                  raw_row, collection_eligible
                ) VALUES (
                  CAST(:location_id AS uuid), 'walmart_us', :provider,
                  :store_number, :store_number, :store_name, :zipcode, :zipcode,
                  :city, 'CA', 'USA', :latitude, :longitude, 'active',
                  '{}'::jsonb, true
                )
                """
            ),
            [
                {
                    "location_id": retailer_location_ids[index],
                    "provider": stable_key,
                    "store_number": str(2400 + index),
                    "store_name": f"Mutable Store {index}",
                    "zipcode": f"9000{index}",
                    "city": f"Mutable City {index}",
                    "latitude": 30.0 + index,
                    "longitude": -110.0 - index,
                }
                for index in range(2)
            ],
        )
        await connection.execute(
            text(
                """
                INSERT INTO collection_geography_location (
                  resolution_id, role, retailer_id, retailer_location_id,
                  scope_key, store_number, zipcode, country,
                  latitude, longitude, selection_reason
                ) VALUES (
                  CAST(:resolution_id AS uuid), 'primary', 'walmart_us',
                  CAST(:retailer_location_id AS uuid),
                  :scope_key, :store_number, :zipcode, 'USA',
                  :latitude, :longitude, 'postgres_test_fixture'
                )
                """
            ),
            [
                {
                    "resolution_id": geography_resolution_id,
                    "retailer_location_id": retailer_location_ids[index],
                    "scope_key": f"location:{index}",
                    "store_number": str(2400 + index),
                    "zipcode": f"9000{index}",
                    "latitude": 34.0 + index,
                    "longitude": -118.0 - index,
                }
                for index in range(2)
            ],
        )
        await connection.execute(
            text(
                "UPDATE collection_definition_version "
                "SET geography_resolution_id = CAST(:resolution_id AS uuid) "
                "WHERE id::text = :version_id"
            ),
            {
                "resolution_id": geography_resolution_id,
                "version_id": definition.version_id,
            },
        )
    seeds = tuple(
        TaskSeed(
            retailer_id="walmart_us",
            retailer_location_id=retailer_location_ids[index],
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
            # A later location import may legitimately update the live master. The
            # composite must continue to use the definition-bound geography snapshot.
            await connection.execute(
                text(
                    """
                    UPDATE retailer_location
                    SET latitude = 51.5, longitude = -0.1,
                        city = 'Mutated After Collection'
                    WHERE id = ANY(CAST(:location_ids AS uuid[]))
                    """
                ),
                {"location_ids": retailer_location_ids},
            )
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
        with pytest.raises(ValueError, match="immutable authorized phase inventory"):
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
            materialized_counts = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT
                              (SELECT count(*) FROM analysis_input_task_lineage
                               WHERE input_set_id::text = :input_set_id) AS lineage_count,
                              (SELECT count(*) FROM analysis_input_artifact
                               WHERE input_set_id::text = :input_set_id) AS artifact_count
                            """
                        ),
                        {"input_set_id": ready.id},
                    )
                )
                .mappings()
                .one()
            )
            frozen_location_snapshot = dict(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT snapshot->'location_snapshot'
                            FROM analysis_input_task_lineage
                            WHERE input_set_id::text = :input_set_id
                              AND location_scope_key = 'location:0'
                            """
                        ),
                        {"input_set_id": ready.id},
                    )
                ).scalar_one()
            )
        assert str(queued_input_set) == ready.id
        assert dict(materialized_counts) == {"lineage_count": 2, "artifact_count": 1}
        assert set(frozen_location_snapshot) == {"latitude", "longitude", "city", "state"}
        assert frozen_location_snapshot["latitude"] == 34.0
        assert frozen_location_snapshot["longitude"] == -118.0
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


@pytest.mark.skipif(
    not os.getenv("RCI_TEST_DATABASE_URL"),
    reason="set RCI_TEST_DATABASE_URL to run Postgres bulk-materialization integration",
)
async def test_postgres_composite_materializes_more_than_one_bulk_batch_exactly() -> None:
    database = DatabaseProbe(os.environ["RCI_TEST_DATABASE_URL"])
    await _isolate_claimable_runs(database)
    collection_repository = PostgresCollectionRepository(database.engine)
    composite_repository = _postgres_composite_repository(database)
    task_count = MATERIALIZATION_WRITE_BATCH_SIZE + 2
    stable_key = f"postgres-composite-bulk-{uuid4()}"
    definition: DefinitionRecord | None = None
    try:
        definition = await _publish_bulk_materialization_definition(
            collection_repository,
            stable_key,
            task_count=task_count,
        )
        await _attach_bulk_materialization_geography(
            database,
            definition,
            task_count=task_count,
        )
        seeds = tuple(_bulk_materialization_seed(index) for index in range(task_count))
        plan = CollectionPlan(
            estimate=CostEstimate(
                definition_id=definition.stable_key,
                retailers=(
                    RetailerEstimate(
                        "walmart_us",
                        task_count,
                        1,
                        1,
                        task_count,
                        task_count,
                    ),
                ),
                estimated_total_pages=task_count,
                estimated_total_credits=task_count,
            ),
            initial_tasks=seeds,
        )
        base_run = await collection_repository.create_run(definition, plan)
        await _complete_bulk_base_fixture(database, base_run.id)

        preview = await composite_repository.preview(base_run.id)
        assert preview.selected_task_count == 1
        assert preview.retailers[0].reused_successes == task_count - 2
        assert preview.retailers[0].retained_billable_404s == 1
        organization_id = await _run_organization_id(database, base_run.id)
        authorization = await composite_repository.authorize_recovery_spend(
            organization_id=organization_id,
            phase_key=f"postgres-bulk-materialization-{uuid4()}",
            approved_credit_ceiling=task_count + 10,
            unit_cost_usd="0.002000",
            currency="USD",
            reason="exercise multi-batch immutable materialization",
            authorized_by="postgres-bulk-materialization-test",
            collection_run_ids=(base_run.id,),
        )
        batch = await composite_repository.create_recovery_batch(authorization_id=authorization.id)
        recovery_plan = await composite_repository.approve(
            base_run.id,
            selection_checksum=preview.selection_checksum,
            approved_credit_ceiling=preview.maximum_credits,
            reason="recover the one nonbillable gap before bulk assembly",
            approved_by="postgres-bulk-materialization-test",
            recovery_batch_id=batch.id,
        )
        recovery = await composite_repository.launch_exact_recovery(recovery_plan.id)
        await _complete_bulk_recovery_fixture(database, recovery.collection_run_id)

        materialized = await composite_repository.materialize(base_run.id, (recovery_plan.id,))

        assert materialized.status == "ready"
        assert materialized.total_rows == (task_count - 1) * 2
        async with database.engine.connect() as connection:
            counts = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT
                              (SELECT count(*) FROM analysis_input_task_lineage
                               WHERE input_set_id::text = :input_set_id) AS lineage_count,
                              (SELECT count(*) FROM analysis_input_artifact
                               WHERE input_set_id::text = :input_set_id) AS artifact_count,
                              (SELECT count(DISTINCT canonical_request_key)
                               FROM analysis_input_task_lineage
                               WHERE input_set_id::text = :input_set_id) AS lineage_key_count,
                              (SELECT count(DISTINCT metadata->>'canonical_request_key')
                               FROM analysis_input_artifact
                               WHERE input_set_id::text = :input_set_id) AS artifact_key_count,
                              (SELECT count(*) FROM analysis_run
                               WHERE input_set_id::text = :input_set_id) AS analysis_count
                            """
                        ),
                        {"input_set_id": materialized.id},
                    )
                )
                .mappings()
                .one()
            )
            manifest = dict(
                (
                    await connection.execute(
                        text(
                            "SELECT manifest FROM analysis_input_set WHERE id::text = :input_set_id"
                        ),
                        {"input_set_id": materialized.id},
                    )
                ).scalar_one()
            )
        assert dict(counts) == {
            "lineage_count": task_count,
            "artifact_count": task_count - 1,
            "lineage_key_count": task_count,
            "artifact_key_count": task_count - 1,
            "analysis_count": 1,
        }
        assert manifest["task_count"] == task_count
        assert manifest["usable_artifact_count"] == task_count - 1
    finally:
        if definition is not None:
            await _cancel_concurrency_definition_runs(database, definition.version_id)
        await database.dispose()


@pytest.mark.skipif(
    not os.getenv("RCI_TEST_DATABASE_URL"),
    reason="set RCI_TEST_DATABASE_URL to run Postgres materialization rollback integration",
)
async def test_postgres_bulk_reconciliation_mismatch_rolls_back_input_and_analysis() -> None:
    database = DatabaseProbe(os.environ["RCI_TEST_DATABASE_URL"])
    collection_repository = PostgresCollectionRepository(database.engine)
    composite_repository = _postgres_composite_repository(database)
    definition: DefinitionRecord | None = None
    input_set_id = str(uuid4())
    try:
        definition = await _publish_concurrency_definition(
            collection_repository,
            f"postgres-bulk-rollback-{uuid4()}",
        )
        succeeded_run = await _create_terminal_concurrency_run(
            database,
            collection_repository,
            definition,
            request_index=0,
            outcome="succeeded",
        )
        with pytest.raises(
            RuntimeError,
            match="usable-artifact bulk insertion differs",
        ):
            async with database.engine.begin() as connection:
                run_row = (
                    (
                        await connection.execute(
                            text(
                                """
                                SELECT r.organization_id::text, v.config
                                FROM collection_run r
                                JOIN collection_definition_version v
                                  ON v.id = r.definition_version_id
                                WHERE r.id::text = :run_id
                                """
                            ),
                            {"run_id": succeeded_run.id},
                        )
                    )
                    .mappings()
                    .one()
                )
                rows = await composite_repository._task_rows(connection, succeeded_run.id)
                row = rows[0]
                key = canonical_request_key(row)
                await connection.execute(
                    text(
                        """
                        INSERT INTO analysis_input_set (
                          id, organization_id, source_kind, stable_key, collection_run_id,
                          product_pack_id, product_pack_version, analysis_config,
                          manifest, manifest_checksum, total_rows, status, completed_at,
                          assembly_generation, assembly_policy_version, trust_state
                        ) VALUES (
                          CAST(:input_set_id AS uuid), CAST(:organization_id AS uuid),
                          'live_collection_composite', :stable_key, CAST(:run_id AS uuid),
                          'fresh_fluid_milk', '1.0.0', CAST(:analysis_config AS jsonb),
                          '{}'::jsonb, :manifest_checksum, 1, 'ready', now(),
                          1, 'composite-evidence-v1', 'ready'
                        )
                        """
                    ),
                    {
                        "input_set_id": input_set_id,
                        "organization_id": str(run_row["organization_id"]),
                        "stable_key": f"rollback-{input_set_id}",
                        "run_id": succeeded_run.id,
                        "analysis_config": "{}",
                        "manifest_checksum": canonical_checksum({"rollback": input_set_id}),
                    },
                )
                await composite_repository._insert_selected_evidence(
                    connection,
                    input_set_id,
                    [(key, row, None, evidence_outcome(row))],
                    expected_usable_artifacts=(
                        {
                            "ordinal": 0,
                            "canonical_request_key": key,
                            "dataset_artifact_id": str(row["raw_artifact_id"]),
                            "checksum": "forced-checksum-mismatch",
                        },
                    ),
                )
                await composite_repository._queue_composite_analysis(
                    connection,
                    input_set_id,
                    queue_allowed=True,
                )

        async with database.engine.connect() as connection:
            rolled_back_counts = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT
                              (SELECT count(*) FROM analysis_input_set
                               WHERE id::text = :input_set_id) AS input_count,
                              (SELECT count(*) FROM analysis_input_task_lineage
                               WHERE input_set_id::text = :input_set_id) AS lineage_count,
                              (SELECT count(*) FROM analysis_input_artifact
                               WHERE input_set_id::text = :input_set_id) AS artifact_count,
                              (SELECT count(*) FROM analysis_run
                               WHERE input_set_id::text = :input_set_id) AS analysis_count
                            """
                        ),
                        {"input_set_id": input_set_id},
                    )
                )
                .mappings()
                .one()
            )
        assert dict(rolled_back_counts) == {
            "input_count": 0,
            "lineage_count": 0,
            "artifact_count": 0,
            "analysis_count": 0,
        }
    finally:
        if definition is not None:
            await _cancel_concurrency_definition_runs(database, definition.version_id)
        await database.dispose()


@pytest.mark.skipif(
    not os.getenv("RCI_TEST_DATABASE_URL"),
    reason="set RCI_TEST_DATABASE_URL to run Postgres scope-projection integration",
)
async def test_postgres_scope_projection_approval_inventory_and_triggers_are_immutable() -> None:
    database = DatabaseProbe(os.environ["RCI_TEST_DATABASE_URL"])
    collection_repository = PostgresCollectionRepository(database.engine)
    composite_repository = _scope_projection_repository(database)
    fixture: _ScopeProjectionFixture | None = None
    try:
        # 501 canonical/alias pairs cross the 1,000-row persistence batch boundary.
        # At least one excluded alias is deliberately ordered before the boundary
        # while its retained canonical target is in the following batch, proving
        # the DEFERRABLE mapping trigger observes the complete transaction.
        fixture = await _create_scope_projection_fixture(
            database,
            collection_repository,
            pair_count=501,
            include_benchmark_failure=False,
        )
        preview = await composite_repository.preview_scope_projection(
            fixture.base_run.id,
            retailer_id="kroger_us",
            projection_kind="canonical_alias_collapse",
            source_audit_id=fixture.source_audit_id,
        )
        assert preview.raw_task_count == 1_002
        assert preview.retained_task_count == 501
        assert preview.excluded_task_count == 501
        ordinal_by_task = {
            item.source_task_id: ordinal for ordinal, item in enumerate(preview.items)
        }
        assert any(
            ordinal < MATERIALIZATION_WRITE_BATCH_SIZE
            and item.mapped_retained_task_id is not None
            and ordinal_by_task[item.mapped_retained_task_id] >= MATERIALIZATION_WRITE_BATCH_SIZE
            for ordinal, item in enumerate(preview.items)
            if item.disposition == "excluded"
        )

        approved = await composite_repository.approve_scope_projection(
            fixture.base_run.id,
            retailer_id="kroger_us",
            projection_kind="canonical_alias_collapse",
            projection_checksum=preview.projection_checksum,
            base_snapshot_checksum=preview.base_snapshot_checksum,
            review_reason="approve complete batched canonical inventory",
            reviewed_by="postgres-scope-projection-test",
            source_audit_id=fixture.source_audit_id,
        )
        repeated = await composite_repository.approve_scope_projection(
            fixture.base_run.id,
            retailer_id="kroger_us",
            projection_kind="canonical_alias_collapse",
            projection_checksum=preview.projection_checksum,
            base_snapshot_checksum=preview.base_snapshot_checksum,
            review_reason="approve complete batched canonical inventory",
            reviewed_by="postgres-scope-projection-test",
            source_audit_id=fixture.source_audit_id,
        )
        assert repeated.id == approved.id
        with pytest.raises(ValueError, match="review a new complete preview"):
            await composite_repository.approve_scope_projection(
                fixture.base_run.id,
                retailer_id="kroger_us",
                projection_kind="canonical_alias_collapse",
                projection_checksum="f" * 64,
                base_snapshot_checksum=preview.base_snapshot_checksum,
                review_reason="altered checksum",
                reviewed_by="postgres-scope-projection-test",
                source_audit_id=fixture.source_audit_id,
            )
        with pytest.raises(ValueError, match="another approval record"):
            await composite_repository.approve_scope_projection(
                fixture.base_run.id,
                retailer_id="kroger_us",
                projection_kind="canonical_alias_collapse",
                projection_checksum=preview.projection_checksum,
                base_snapshot_checksum=preview.base_snapshot_checksum,
                review_reason="altered approval reason",
                reviewed_by="postgres-scope-projection-test",
                source_audit_id=fixture.source_audit_id,
            )

        async with database.engine.connect() as connection:
            inventory_rows = list(
                (
                    await connection.execute(
                        text(
                            "SELECT source_task_id::text, ordinal, disposition, "
                            "mapped_retained_task_id::text AS mapped_retained_task_id "
                            "FROM collection_scope_projection_task "
                            "WHERE scope_projection_id::text = :projection_id "
                            "ORDER BY ordinal"
                        ),
                        {"projection_id": approved.id},
                    )
                )
                .mappings()
                .all()
            )
        assert len(inventory_rows) == 1_002
        retained_task_ids = {
            str(row["source_task_id"]) for row in inventory_rows if row["disposition"] == "retained"
        }
        assert all(
            str(row["mapped_retained_task_id"]) in retained_task_ids
            for row in inventory_rows
            if row["disposition"] == "excluded"
        )

        for statement in (
            "UPDATE collection_scope_projection SET review_reason = 'mutated' "
            "WHERE id::text = :projection_id",
            "DELETE FROM collection_scope_projection WHERE id::text = :projection_id",
            "UPDATE collection_scope_projection_task SET reason = 'mutated' "
            "WHERE scope_projection_id::text = :projection_id AND ordinal = 0",
            "DELETE FROM collection_scope_projection_task "
            "WHERE scope_projection_id::text = :projection_id AND ordinal = 0",
        ):
            with pytest.raises(DBAPIError, match="immutable"):
                async with database.engine.begin() as connection:
                    await connection.execute(text(statement), {"projection_id": approved.id})

        for statement in (
            "UPDATE location_eligibility_reconciliation_run "
            "SET change_reason = 'mutated' WHERE id::text = :audit_id",
            "DELETE FROM location_eligibility_reconciliation_run WHERE id::text = :audit_id",
        ):
            with pytest.raises(DBAPIError, match=r"completed.*audits are immutable"):
                async with database.engine.begin() as connection:
                    await connection.execute(text(statement), {"audit_id": fixture.source_audit_id})

        # The header trigger rejects an organization mismatch, the benchmark,
        # and a retailer absent from the immutable enabled-retailer definition.
        for organization_id, retailer_id, message in (
            (str(uuid4()), "kroger_us", "organization differs"),
            (await _run_organization_id(database, fixture.base_run.id), "walmart_us", "enabled"),
            (await _run_organization_id(database, fixture.base_run.id), "aldi_us", "enabled"),
        ):
            with pytest.raises(DBAPIError, match=message):
                async with database.engine.begin() as connection:
                    await _clone_projection_header(
                        connection,
                        approved.id,
                        organization_id=organization_id,
                        retailer_id=retailer_id,
                    )

        other_task_id = await _create_cross_run_scope_task(
            database,
            collection_repository,
            fixture.definition,
        )
        with pytest.raises(DBAPIError, match="source task differs"):
            async with database.engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO collection_scope_projection_task ("
                        "scope_projection_id, source_task_id, ordinal, "
                        "canonical_request_key, disposition, reason, source_snapshot"
                        ") VALUES (CAST(:projection_id AS uuid), CAST(:task_id AS uuid), "
                        "90000, :request_key, 'retained', 'invalid cross-run source', '{}'::jsonb)"
                    ),
                    {
                        "projection_id": approved.id,
                        "task_id": other_task_id,
                        "request_key": canonical_checksum({"cross_run": other_task_id}),
                    },
                )
        with pytest.raises(DBAPIError, match="mapped canonical task differs"):
            async with database.engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO collection_scope_projection_task ("
                        "scope_projection_id, source_task_id, ordinal, "
                        "canonical_request_key, disposition, reason, "
                        "mapped_retained_task_id, source_snapshot"
                        ") VALUES (CAST(:projection_id AS uuid), CAST(:source_task_id AS uuid), "
                        "90001, :request_key, 'excluded', 'invalid cross-run mapping', "
                        "CAST(:mapped_task_id AS uuid), '{}'::jsonb)"
                    ),
                    {
                        "projection_id": approved.id,
                        "source_task_id": fixture.canonical_task_ids[0],
                        "mapped_task_id": other_task_id,
                        "request_key": canonical_checksum({"cross_run_mapping": other_task_id}),
                    },
                )

        # Insert a fresh header and only its excluded alias. The deferred
        # constraint must reject the transaction because its mapped target was
        # never inserted as retained in that same projection.
        with pytest.raises(DBAPIError, match="canonical alias exclusions require"):
            async with database.engine.begin() as connection:
                null_mapping_projection_id = await _clone_projection_header(
                    connection,
                    approved.id,
                    organization_id=await _run_organization_id(database, fixture.base_run.id),
                    retailer_id="kroger_us",
                )
                await connection.execute(
                    text(
                        "INSERT INTO collection_scope_projection_task ("
                        "scope_projection_id, source_task_id, ordinal, canonical_request_key, "
                        "disposition, reason, mapped_retained_task_id, source_snapshot) "
                        "SELECT CAST(:new_projection_id AS uuid), source_task_id, 0, "
                        "canonical_request_key, disposition, reason, NULL, source_snapshot "
                        "FROM collection_scope_projection_task "
                        "WHERE scope_projection_id::text = :projection_id "
                        "AND disposition = 'excluded' ORDER BY ordinal LIMIT 1"
                    ),
                    {
                        "new_projection_id": null_mapping_projection_id,
                        "projection_id": approved.id,
                    },
                )

        with pytest.raises(DBAPIError, match="not retained by the same projection"):
            async with database.engine.begin() as connection:
                incomplete_projection_id = await _clone_projection_header(
                    connection,
                    approved.id,
                    organization_id=await _run_organization_id(database, fixture.base_run.id),
                    retailer_id="kroger_us",
                )
                await connection.execute(
                    text(
                        "INSERT INTO collection_scope_projection_task ("
                        "scope_projection_id, source_task_id, ordinal, canonical_request_key, "
                        "disposition, reason, mapped_retained_task_id, source_snapshot"
                        ") SELECT CAST(:new_projection_id AS uuid), source_task_id, 0, "
                        "canonical_request_key, disposition, reason, mapped_retained_task_id, "
                        "source_snapshot FROM collection_scope_projection_task "
                        "WHERE scope_projection_id::text = :projection_id "
                        "AND disposition = 'excluded' ORDER BY ordinal LIMIT 1"
                    ),
                    {
                        "new_projection_id": incomplete_projection_id,
                        "projection_id": approved.id,
                    },
                )
    finally:
        if fixture is not None:
            await _cancel_concurrency_definition_runs(database, fixture.definition.version_id)
        await database.dispose()


@pytest.mark.skipif(
    not os.getenv("RCI_TEST_DATABASE_URL"),
    reason="set RCI_TEST_DATABASE_URL to run the 0054 migration roundtrip",
)
async def test_postgres_0054_roundtrip_preserves_v1_history_and_restores_head() -> None:
    database_url = os.environ["RCI_TEST_DATABASE_URL"]
    environment = {**os.environ, "DATABASE_URL": database_url}
    database = DatabaseProbe(database_url)
    collection_repository = PostgresCollectionRepository(database.engine)
    composite_repository = _scope_projection_repository(database)
    fixture = await _create_scope_projection_fixture(
        database,
        collection_repository,
        pair_count=1,
        include_benchmark_failure=False,
    )
    preview = await composite_repository.preview_scope_projection(
        fixture.base_run.id,
        retailer_id="kroger_us",
        projection_kind="canonical_alias_collapse",
        source_audit_id=fixture.source_audit_id,
    )
    approved = await composite_repository.approve_scope_projection(
        fixture.base_run.id,
        retailer_id="kroger_us",
        projection_kind="canonical_alias_collapse",
        projection_checksum=preview.projection_checksum,
        base_snapshot_checksum=preview.base_snapshot_checksum,
        review_reason="prove the 0054 roundtrip preserves v1 bytes",
        reviewed_by="postgres-scope-projection-test",
        source_audit_id=fixture.source_audit_id,
    )

    async def projection_snapshot(probe: DatabaseProbe) -> dict[str, object]:
        async with probe.engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "SELECT to_jsonb(projection) AS header, "
                            "COALESCE(jsonb_agg(to_jsonb(item) ORDER BY item.ordinal) "
                            "FILTER (WHERE item.scope_projection_id IS NOT NULL), '[]') "
                            "AS inventory FROM collection_scope_projection projection "
                            "LEFT JOIN collection_scope_projection_task item "
                            "ON item.scope_projection_id = projection.id "
                            "WHERE projection.id = CAST(:projection_id AS uuid) "
                            "GROUP BY projection.id"
                        ),
                        {"projection_id": approved.id},
                    )
                )
                .mappings()
                .one()
            )
        return {"header": dict(row["header"]), "inventory": list(row["inventory"])}

    before = await projection_snapshot(database)
    await database.dispose()
    restoration: subprocess.CompletedProcess[str] | None = None
    try:
        downgraded = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "database/alembic.ini",
                "downgrade",
                "0053_scope_projections",
            ],
            cwd=REPOSITORY_ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert downgraded.returncode == 0, downgraded.stdout + downgraded.stderr
        downgraded_probe = DatabaseProbe(database_url)
        try:
            async with downgraded_probe.engine.connect() as connection:
                assert (
                    int(
                        (
                            await connection.execute(
                                text(
                                    "SELECT count(*) FROM pg_trigger "
                                    "WHERE tgname LIKE '%_audited_projection_source_%_trg'"
                                )
                            )
                        ).scalar_one()
                    )
                    == 0
                )
                assert (
                    int(
                        (
                            await connection.execute(
                                text(
                                    "SELECT count(*) FROM pg_indexes "
                                    "WHERE schemaname = current_schema() "
                                    "AND indexname = "
                                    "'collection_scope_projection_task_source_idx'"
                                )
                            )
                        ).scalar_one()
                    )
                    == 0
                )
        finally:
            await downgraded_probe.dispose()
        upgraded = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "database/alembic.ini",
                "upgrade",
                "head",
            ],
            cwd=REPOSITORY_ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert upgraded.returncode == 0, upgraded.stdout + upgraded.stderr
        verification = DatabaseProbe(database_url)
        try:
            assert await projection_snapshot(verification) == before
            async with verification.engine.connect() as connection:
                assert (
                    await connection.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one() == "0054_audited_alias_reconcile"
        finally:
            await verification.dispose()
    finally:
        restoration = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "database/alembic.ini",
                "upgrade",
                "head",
            ],
            cwd=REPOSITORY_ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert restoration.returncode == 0, restoration.stdout + restoration.stderr
        final_probe = DatabaseProbe(database_url)
        try:
            async with final_probe.engine.connect() as connection:
                assert (
                    await connection.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one() == "0054_audited_alias_reconcile"
        finally:
            await final_probe.dispose()


@pytest.mark.skipif(
    not os.getenv("RCI_TEST_DATABASE_URL"),
    reason="set RCI_TEST_DATABASE_URL to run Postgres audited reconciliation integration",
)
async def test_postgres_audited_alias_reconciliation_commits_full_legacy_egg_shape() -> None:
    database = DatabaseProbe(os.environ["RCI_TEST_DATABASE_URL"])
    collection_repository = PostgresCollectionRepository(database.engine)
    composite_repository = _scope_projection_repository(database)
    fixture: _ScopeProjectionFixture | None = None
    try:
        fixture = await _create_scope_projection_fixture(
            database,
            collection_repository,
            pair_count=1_296,
            canonical_count=1_369,
            unpaired_scopes=(("1400945", "45069"), ("2900768", "25064")),
            include_benchmark_failure=False,
            legacy_contracts=True,
        )
        preview = await composite_repository.preview_scope_projection(
            fixture.base_run.id,
            retailer_id="kroger_us",
            projection_kind="audited_alias_reconciliation",
            source_audit_id=fixture.source_audit_id,
        )
        assert (
            preview.raw_task_count,
            preview.retained_task_count,
            preview.excluded_task_count,
        ) == (2_667, 1_369, 1_298)
        assert preview.raw_task_retention_ratio == "0.513311"
        assert preview.denominator_gap_location_count == 2
        assert preview.coverage_numerator_location_count == 1_369
        assert preview.coverage_denominator_location_count == 1_371
        assert preview.governed_coverage_ratio == "0.998541"
        assert preview.scorecard_disposition == "scoreable"
        identity_evidence = preview.manifest["source_evidence"]["request_identity"]
        adapter_evidence = identity_evidence["contracts"]["fake_kroger"]
        assert adapter_evidence["frozen_task_count"] == 0
        assert adapter_evidence["reconstructed_task_count"] == 2_667
        assert adapter_evidence["called_artifact_count"] == 4
        assert len(adapter_evidence["called_artifacts"]) == 4

        approval_started = perf_counter()
        approved = await composite_repository.approve_scope_projection(
            fixture.base_run.id,
            retailer_id="kroger_us",
            projection_kind="audited_alias_reconciliation",
            projection_checksum=preview.projection_checksum,
            base_snapshot_checksum=preview.base_snapshot_checksum,
            review_reason="approve the production-shaped governed legacy reconciliation",
            reviewed_by="postgres-scope-projection-test",
            source_audit_id=fixture.source_audit_id,
        )
        approval_elapsed_seconds = perf_counter() - approval_started
        assert approval_elapsed_seconds < 30, (
            "the 2,667-row deferred scope validation exceeded its bounded CI budget: "
            f"{approval_elapsed_seconds:.3f}s"
        )
        repeated = await composite_repository.approve_scope_projection(
            fixture.base_run.id,
            retailer_id="kroger_us",
            projection_kind="audited_alias_reconciliation",
            projection_checksum=preview.projection_checksum,
            base_snapshot_checksum=preview.base_snapshot_checksum,
            review_reason="approve the production-shaped governed legacy reconciliation",
            reviewed_by="postgres-scope-projection-test",
            source_audit_id=fixture.source_audit_id,
        )
        assert repeated.id == approved.id

        async with database.engine.connect() as connection:
            inventory = (
                (
                    await connection.execute(
                        text(
                            "SELECT count(*)::integer AS task_count, "
                            "count(*) FILTER (WHERE mapped_retained_task_id IS NOT NULL)::integer "
                            "AS mapped_count, count(*) FILTER (WHERE reason = "
                            "'audited_provider_unsafe_unpaired_scope_gap' "
                            "AND mapped_retained_task_id IS NULL)::integer AS gap_count, "
                            "count(*) FILTER (WHERE "
                            "source_snapshot->'task'->'persisted_request_payload' "
                            "? '_provider_request_contract')::integer AS persisted_contract_count, "
                            "count(*) FILTER (WHERE source_snapshot->'task'->'request_payload' "
                            "? '_provider_request_contract')::integer AS executable_contract_count "
                            "FROM collection_scope_projection_task "
                            "WHERE scope_projection_id = CAST(:projection_id AS uuid)"
                        ),
                        {"projection_id": approved.id},
                    )
                )
                .mappings()
                .one()
            )
        assert dict(inventory) == {
            "task_count": 2_667,
            "mapped_count": 1_296,
            "gap_count": 2,
            "persisted_contract_count": 0,
            "executable_contract_count": 2_667,
        }
    finally:
        if fixture is not None:
            await _cancel_concurrency_definition_runs(database, fixture.definition.version_id)
        await database.dispose()


@pytest.mark.skipif(
    not os.getenv("RCI_TEST_DATABASE_URL"),
    reason="set RCI_TEST_DATABASE_URL to run Postgres audited ratio parity",
)
async def test_postgres_audited_ratio_rounding_and_canonical_hash_match_python() -> None:
    database = DatabaseProbe(os.environ["RCI_TEST_DATABASE_URL"])
    collection_repository = PostgresCollectionRepository(database.engine)
    composite_repository = _scope_projection_repository(database)
    fixture: _ScopeProjectionFixture | None = None
    try:
        checksum_document = {
            "lower": {"z_key": "last", "AKey": "first", "_under": "middle"},
            "MixedCase": ["_under", "AKey", "z_key"],
        }
        async with database.engine.connect() as connection:
            postgres_checksum = str(
                (
                    await connection.execute(
                        text(
                            "SELECT encode(digest(convert_to("
                            "scope_projection_canonical_jsonb(CAST(:document AS jsonb)), "
                            "'UTF8'), 'sha256'), 'hex')"
                        ),
                        {"document": json.dumps(checksum_document, ensure_ascii=False)},
                    )
                ).scalar_one()
            )
        assert postgres_checksum == canonical_checksum(checksum_document)

        unpaired_scopes = tuple(
            (f"{2_000_000 + index:07d}", f"{index + 1:05d}") for index in range(127)
        )
        fixture = await _create_scope_projection_fixture(
            database,
            collection_repository,
            pair_count=0,
            canonical_count=1,
            unpaired_scopes=unpaired_scopes,
            include_benchmark_failure=False,
        )
        preview = await composite_repository.preview_scope_projection(
            fixture.base_run.id,
            retailer_id="kroger_us",
            projection_kind="audited_alias_reconciliation",
            source_audit_id=fixture.source_audit_id,
        )
        assert preview.raw_task_retention_ratio == "0.007813"
        assert preview.governed_coverage_ratio == "0.007813"
        assert preview.scorecard_disposition == "unavailable"
        approved = await composite_repository.approve_scope_projection(
            fixture.base_run.id,
            retailer_id="kroger_us",
            projection_kind="audited_alias_reconciliation",
            projection_checksum=preview.projection_checksum,
            base_snapshot_checksum=preview.base_snapshot_checksum,
            review_reason="prove Python and PostgreSQL audited ratio parity",
            reviewed_by="postgres-scope-projection-test",
            source_audit_id=fixture.source_audit_id,
        )
        assert approved.raw_task_retention_ratio == "0.007813"
        assert approved.governed_coverage_ratio == "0.007813"
    finally:
        if fixture is not None:
            await _cancel_concurrency_definition_runs(database, fixture.definition.version_id)
        await database.dispose()


@pytest.mark.skipif(
    not os.getenv("RCI_TEST_DATABASE_URL"),
    reason="set RCI_TEST_DATABASE_URL to run audited projection trust-boundary negatives",
)
async def test_postgres_audited_projection_direct_writes_fail_closed() -> None:
    database = DatabaseProbe(os.environ["RCI_TEST_DATABASE_URL"])
    collection_repository = PostgresCollectionRepository(database.engine)
    composite_repository = _scope_projection_repository(database)
    fixture: _ScopeProjectionFixture | None = None
    try:
        fixture = await _create_scope_projection_fixture(
            database,
            collection_repository,
            pair_count=1,
            canonical_count=2,
            unpaired_scopes=(("2000000", "45069"),),
            include_benchmark_failure=False,
        )
        preview = await composite_repository.preview_scope_projection(
            fixture.base_run.id,
            retailer_id="kroger_us",
            projection_kind="audited_alias_reconciliation",
            source_audit_id=fixture.source_audit_id,
        )
        organization_id = await _run_organization_id(database, fixture.base_run.id)
        original_items = _scope_projection_item_documents(preview)

        with pytest.raises(DBAPIError, match="terminal immutable base run"):
            async with database.engine.begin() as connection:
                await connection.execute(
                    text(
                        "UPDATE collection_run SET status = 'running', completed_at = NULL "
                        "WHERE id = CAST(:run_id AS uuid)"
                    ),
                    {"run_id": fixture.base_run.id},
                )
                await _insert_audited_projection_preview(
                    connection,
                    preview,
                    organization_id=organization_id,
                )

        with pytest.raises(DBAPIError, match="checksum-bound to its header"):
            async with database.engine.begin() as connection:
                await _insert_audited_projection_preview(
                    connection,
                    preview,
                    organization_id=organization_id,
                    header_overrides={"base_snapshot_checksum": "0" * 64},
                )

        checksum_tampered_manifest = json.loads(json.dumps(preview.manifest))
        checksum_tampered_manifest["base_snapshot_checksum"] = "1" * 64
        with pytest.raises(DBAPIError, match="checksum-bound to its header"):
            async with database.engine.begin() as connection:
                await _insert_audited_projection_preview(
                    connection,
                    preview,
                    organization_id=organization_id,
                    manifest=checksum_tampered_manifest,
                    projection_checksum=preview.projection_checksum,
                )

        threshold_tampered_manifest = json.loads(json.dumps(preview.manifest))
        threshold_tampered_manifest["minimum_scoreable_coverage"] = "0.500000"
        threshold_tampered_manifest["scorecard_disposition"] = "scoreable"
        with pytest.raises(DBAPIError, match="scoreability"):
            async with database.engine.begin() as connection:
                await _insert_audited_projection_preview(
                    connection,
                    preview,
                    organization_id=organization_id,
                    manifest=threshold_tampered_manifest,
                    header_overrides={
                        "minimum_scoreable_coverage": "0.500000",
                        "scorecard_disposition": "scoreable",
                    },
                )

        inventory_tampered_manifest = json.loads(json.dumps(preview.manifest))
        inventory_tampered_manifest["inventory_checksum"] = "2" * 64
        with pytest.raises(DBAPIError, match="denominator or disposition"):
            async with database.engine.begin() as connection:
                await _insert_audited_projection_preview(
                    connection,
                    preview,
                    organization_id=organization_id,
                    manifest=inventory_tampered_manifest,
                )

        ratio_tampered_manifest = json.loads(json.dumps(preview.manifest))
        ratio_tampered_manifest["raw_task_retention_ratio"] = "0.900000"
        with pytest.raises(DBAPIError, match="denominator or disposition"):
            async with database.engine.begin() as connection:
                await _insert_audited_projection_preview(
                    connection,
                    preview,
                    organization_id=organization_id,
                    manifest=ratio_tampered_manifest,
                    header_overrides={"raw_task_retention_ratio": "0.900000"},
                )

        with pytest.raises(DBAPIError, match="sealed inventory counts do not reconcile"):
            async with database.engine.begin() as connection:
                await _insert_audited_projection_preview(
                    connection,
                    preview,
                    organization_id=organization_id,
                    items=json.loads(json.dumps(original_items[:-1])),
                )

        spoofed_snapshot_items = json.loads(json.dumps(original_items))
        spoofed_snapshot_items[0]["source_snapshot"]["task"]["zipcode"] = "99999"
        with pytest.raises(DBAPIError, match="source snapshot differs"):
            async with database.engine.begin() as connection:
                await _insert_audited_projection_preview(
                    connection,
                    preview,
                    organization_id=organization_id,
                    items=spoofed_snapshot_items,
                )

        spoofed_geography_items = json.loads(json.dumps(original_items))
        spoofed_geography_items[0]["source_snapshot"]["task"]["location_snapshot"]["latitude"] = (
            88.0
        )
        with pytest.raises(DBAPIError, match="source snapshot differs"):
            async with database.engine.begin() as connection:
                await _insert_audited_projection_preview(
                    connection,
                    preview,
                    organization_id=organization_id,
                    items=spoofed_geography_items,
                )

        for path, value in (
            (("current_location_eligible",), "spoofed"),
            (("task", "status"), "spoofed"),
            (("raw_artifact", "checksum"), "f" * 64),
            (("provider_error_evidence", "verified"), {"spoofed": True}),
        ):
            spoofed_authority_items = json.loads(json.dumps(original_items))
            target = spoofed_authority_items[0]["source_snapshot"]
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            with pytest.raises(DBAPIError, match="source snapshot differs"):
                async with database.engine.begin() as connection:
                    await _insert_audited_projection_preview(
                        connection,
                        preview,
                        organization_id=organization_id,
                        items=spoofed_authority_items,
                    )

        null_alias_items = json.loads(json.dumps(original_items))
        exact_alias = next(
            item
            for item in null_alias_items
            if item["reason"] == "audited_alias_of_provider_safe_canonical_scope"
        )
        exact_alias["mapped_retained_task_id"] = None
        with pytest.raises(DBAPIError, match="exact alias requires"):
            async with database.engine.begin() as connection:
                await _insert_audited_projection_preview(
                    connection,
                    preview,
                    organization_id=organization_id,
                    items=null_alias_items,
                )

        mapped_gap_items = json.loads(json.dumps(original_items))
        gap = next(
            item
            for item in mapped_gap_items
            if item["reason"] == "audited_provider_unsafe_unpaired_scope_gap"
        )
        gap["mapped_retained_task_id"] = fixture.canonical_task_ids[0]
        with pytest.raises(DBAPIError, match="unpaired scope gap cannot invent"):
            async with database.engine.begin() as connection:
                await _insert_audited_projection_preview(
                    connection,
                    preview,
                    organization_id=organization_id,
                    items=mapped_gap_items,
                )

        false_gap_items = json.loads(json.dumps(original_items))
        false_gap = next(
            item
            for item in false_gap_items
            if item["reason"] == "audited_alias_of_provider_safe_canonical_scope"
        )
        false_gap["reason"] = "audited_provider_unsafe_unpaired_scope_gap"
        false_gap["mapped_retained_task_id"] = None
        false_gap_manifest = json.loads(json.dumps(preview.manifest))
        false_gap_manifest.update(
            {
                "denominator_gap_location_count": 2,
                "governed_coverage_ratio": "0.500000",
                "scorecard_disposition": "unavailable",
                "coverage_denominator_location_count": 4,
                "inventory_checksum": canonical_checksum({"items": false_gap_items}),
            }
        )
        with pytest.raises(DBAPIError, match="denominator or disposition"):
            async with database.engine.begin() as connection:
                await _insert_audited_projection_preview(
                    connection,
                    preview,
                    organization_id=organization_id,
                    manifest=false_gap_manifest,
                    header_overrides={
                        "denominator_gap_location_count": 2,
                        "governed_coverage_ratio": "0.500000",
                        "scorecard_disposition": "unavailable",
                    },
                    items=false_gap_items,
                )

        wrong_audit_change_manifest = json.loads(json.dumps(preview.manifest))
        wrong_change_evidence = wrong_audit_change_manifest["source_evidence"]
        wrong_change_evidence["location_audit"]["changes"][0]["retailer_id"] = "aldi_us"
        wrong_change_checksum = canonical_checksum(wrong_change_evidence)
        wrong_audit_change_manifest["source_evidence_checksum"] = wrong_change_checksum
        with pytest.raises(DBAPIError, match="denominator or disposition"):
            async with database.engine.begin() as connection:
                await _insert_audited_projection_preview(
                    connection,
                    preview,
                    organization_id=organization_id,
                    manifest=wrong_audit_change_manifest,
                    header_overrides={"source_evidence_checksum": wrong_change_checksum},
                )

        with pytest.raises(DBAPIError, match="retailer is absent"):
            async with database.engine.begin() as connection:
                wrong_retailer_audit_id = str(
                    (
                        await connection.execute(
                            text(
                                "INSERT INTO location_eligibility_reconciliation_run ("
                                "catalog_path, catalog_sha256, snapshot_sha256, "
                                "reviewed_plan_sha256, retailer_ids, requested_by, "
                                "change_reason, status, scanned_rows, changed_rows, "
                                "eligible_before, eligible_after, enabled_rows, disabled_rows, "
                                "reason_counts_before, reason_counts_after, changes, completed_at) "
                                "SELECT catalog_path, catalog_sha256, snapshot_sha256, "
                                "reviewed_plan_sha256, ARRAY['aldi_us']::text[], requested_by, "
                                "change_reason, status, scanned_rows, changed_rows, "
                                "eligible_before, eligible_after, enabled_rows, disabled_rows, "
                                "reason_counts_before, reason_counts_after, changes, completed_at "
                                "FROM location_eligibility_reconciliation_run "
                                "WHERE id = CAST(:audit_id AS uuid) RETURNING id::text"
                            ),
                            {"audit_id": fixture.source_audit_id},
                        )
                    ).scalar_one()
                )
                wrong_retailer_manifest = json.loads(json.dumps(preview.manifest))
                wrong_retailer_evidence = wrong_retailer_manifest["source_evidence"]
                wrong_retailer_evidence["location_audit"]["audit_id"] = wrong_retailer_audit_id
                wrong_retailer_evidence["location_audit"]["retailer_ids"] = ["aldi_us"]
                wrong_retailer_checksum = canonical_checksum(wrong_retailer_evidence)
                wrong_retailer_manifest.update(
                    {
                        "source_audit_id": wrong_retailer_audit_id,
                        "source_evidence_checksum": wrong_retailer_checksum,
                    }
                )
                await _insert_audited_projection_preview(
                    connection,
                    preview,
                    organization_id=organization_id,
                    manifest=wrong_retailer_manifest,
                    header_overrides={
                        "source_audit_id": wrong_retailer_audit_id,
                        "source_evidence_checksum": wrong_retailer_checksum,
                    },
                )

        with pytest.raises(DBAPIError, match="differs from frozen geography"):
            async with database.engine.begin() as connection:
                await connection.execute(
                    text(
                        "UPDATE collection_geography_location SET store_number = '99999999' "
                        "WHERE scope_key = 'kroger:canonical:0' AND resolution_id = ("
                        "SELECT version.geography_resolution_id FROM collection_run run "
                        "JOIN collection_definition_version version "
                        "ON version.id = run.definition_version_id "
                        "WHERE run.id = CAST(:run_id AS uuid))"
                    ),
                    {"run_id": fixture.base_run.id},
                )
                await _insert_audited_projection_preview(
                    connection,
                    preview,
                    organization_id=organization_id,
                )

        for drift_statement in (
            "UPDATE collection_task SET zipcode = '99999' WHERE id = CAST(:task_id AS uuid)",
            "UPDATE collection_task SET page_number = page_number + 1 "
            "WHERE id = CAST(:task_id AS uuid)",
            "UPDATE collection_task SET request_payload = "
            "jsonb_set(request_payload, '{keyword}', '\"changed milk\"'::jsonb) "
            "WHERE id = CAST(:task_id AS uuid)",
        ):
            with pytest.raises(DBAPIError, match="source evidence is immutable"):
                async with database.engine.begin() as connection:
                    await _insert_audited_projection_preview(
                        connection,
                        preview,
                        organization_id=organization_id,
                    )
                    await connection.execute(
                        text(drift_statement),
                        {"task_id": fixture.canonical_task_ids[0]},
                    )
    finally:
        if fixture is not None:
            await _cancel_concurrency_definition_runs(database, fixture.definition.version_id)
        await database.dispose()


@pytest.mark.skipif(
    not os.getenv("RCI_TEST_DATABASE_URL"),
    reason="set RCI_TEST_DATABASE_URL to run audited projection lock serialization",
)
async def test_postgres_audited_projection_locks_source_until_guard_is_visible() -> None:
    database = DatabaseProbe(os.environ["RCI_TEST_DATABASE_URL"])
    collection_repository = PostgresCollectionRepository(database.engine)
    composite_repository = _scope_projection_repository(database)
    fixture: _ScopeProjectionFixture | None = None
    projection_connection: AsyncConnection | None = None
    projection_transaction: AsyncTransaction | None = None
    try:
        fixture = await _create_scope_projection_fixture(
            database,
            collection_repository,
            pair_count=1,
            canonical_count=2,
            unpaired_scopes=(("1400945", "45069"),),
            include_benchmark_failure=True,
        )
        preview = await composite_repository.preview_scope_projection(
            fixture.base_run.id,
            retailer_id="kroger_us",
            projection_kind="audited_alias_reconciliation",
            source_audit_id=fixture.source_audit_id,
        )
        organization_id = await _run_organization_id(database, fixture.base_run.id)
        unrelated_task_id = await _create_cross_run_scope_task(
            database, collection_repository, fixture.definition
        )
        async with database.engine.connect() as connection:
            source_rows = list(
                (
                    await connection.execute(
                        text(
                            "SELECT task.id::text AS task_id, "
                            "task.raw_artifact_id::text AS artifact_id, "
                            "geography.id::text AS geography_location_id "
                            "FROM collection_task task "
                            "JOIN collection_run run ON run.id = task.collection_run_id "
                            "JOIN collection_definition_version version "
                            "ON version.id = run.definition_version_id "
                            "JOIN collection_geography_location geography "
                            "ON geography.resolution_id = version.geography_resolution_id "
                            "AND geography.retailer_id = task.retailer_id "
                            "AND geography.scope_key = task.location_scope_key "
                            "WHERE task.id = ANY(CAST(:task_ids AS uuid[])) "
                            "ORDER BY task.id"
                        ),
                        {"task_ids": list(fixture.canonical_task_ids)},
                    )
                )
                .mappings()
                .all()
            )
        sources = {str(row["task_id"]): dict(row) for row in source_rows}
        assert len(sources) == 2
        assert all(row["artifact_id"] is not None for row in sources.values())
        assert fixture.benchmark_task_id is not None
        projection_connection = await database.engine.connect()
        projection_transaction = await projection_connection.begin()
        await _insert_audited_projection_preview(
            projection_connection,
            preview,
            organization_id=organization_id,
        )
        source_task_id, deleted_source_task_id = fixture.canonical_task_ids
        source = sources[source_task_id]
        deleted_source = sources[deleted_source_task_id]

        async def concurrent_write(
            statement: str,
            parameters: dict[str, object],
            started: asyncio.Event,
        ) -> DBAPIError | None:
            try:
                async with database.engine.begin() as connection:
                    started.set()
                    await connection.execute(text(statement), parameters)
            except DBAPIError as exc:
                return exc
            return None

        suffix = str(uuid4())
        writes: tuple[tuple[str, dict[str, object]], ...] = (
            (
                "UPDATE collection_task SET last_error = 'concurrent drift' "
                "WHERE id = CAST(:task_id AS uuid)",
                {"task_id": source_task_id},
            ),
            (
                "DELETE FROM collection_task WHERE id = CAST(:task_id AS uuid)",
                {"task_id": deleted_source_task_id},
            ),
            (
                "INSERT INTO collection_task (collection_run_id, retailer_id, "
                "retailer_location_id, adapter_id, location_scope_key, zipcode, "
                "store_number, page_number, max_pages, stop_on_empty, stop_on_short_page, "
                "credits_per_success, request_payload, request_fingerprint, status, "
                "max_attempts) SELECT CAST(:base_run_id AS uuid), retailer_id, "
                "retailer_location_id, adapter_id, :scope_key, zipcode, store_number, "
                "page_number, max_pages, stop_on_empty, stop_on_short_page, "
                "credits_per_success, request_payload, md5(request_fingerprint || :suffix) "
                "|| md5(:suffix || request_fingerprint), status, max_attempts "
                "FROM collection_task WHERE id = CAST(:task_id AS uuid)",
                {
                    "base_run_id": fixture.base_run.id,
                    "scope_key": f"concurrent:late-task:{suffix}",
                    "suffix": suffix,
                    "task_id": unrelated_task_id,
                },
            ),
            (
                "UPDATE collection_task SET collection_run_id = CAST(:base_run_id AS uuid), "
                "location_scope_key = :scope_key, request_fingerprint = "
                "md5(request_fingerprint || :suffix) || md5(:suffix || request_fingerprint) "
                "WHERE id = CAST(:task_id AS uuid)",
                {
                    "base_run_id": fixture.base_run.id,
                    "scope_key": f"concurrent:moved-task:{suffix}",
                    "suffix": suffix,
                    "task_id": unrelated_task_id,
                },
            ),
            (
                "UPDATE collection_task SET retailer_id = 'kroger_us' "
                "WHERE id = CAST(:task_id AS uuid)",
                {"task_id": fixture.benchmark_task_id},
            ),
            (
                "UPDATE collection_geography_location SET selection_reason = "
                "'concurrent task-linked drift' "
                "WHERE id = CAST(:location_id AS uuid)",
                {"location_id": source["geography_location_id"]},
            ),
            (
                "DELETE FROM collection_geography_location WHERE id = CAST(:location_id AS uuid)",
                {"location_id": deleted_source["geography_location_id"]},
            ),
            (
                "UPDATE dataset_artifact SET metadata = metadata "
                "WHERE id = CAST(:artifact_id AS uuid)",
                {"artifact_id": source["artifact_id"]},
            ),
            (
                "UPDATE collection_run SET status = status WHERE id = CAST(:run_id AS uuid)",
                {"run_id": fixture.base_run.id},
            ),
        )
        started = [asyncio.Event() for _ in writes]
        workers = [
            asyncio.create_task(concurrent_write(statement, parameters, event))
            for (statement, parameters), event in zip(writes, started, strict=True)
        ]
        await asyncio.gather(*(event.wait() for event in started))
        await asyncio.sleep(0.1)
        assert all(not worker.done() for worker in workers), (
            "concurrent source UPDATE/INSERT did not wait for projection source locks"
        )
        await projection_transaction.commit()
        results = await asyncio.wait_for(asyncio.gather(*workers), timeout=10)
        assert all(isinstance(result, DBAPIError) for result in results)
        assert all(
            "source evidence is immutable" in str(result)
            or "collection_scope_projection_task_source_task_id_fkey" in str(result)
            for result in results
        )
    finally:
        if projection_transaction is not None and getattr(
            projection_transaction, "is_active", False
        ):
            await projection_transaction.rollback()
        if projection_connection is not None:
            await projection_connection.close()
        if fixture is not None:
            await _cancel_concurrency_definition_runs(database, fixture.definition.version_id)
        await database.dispose()


@pytest.mark.skipif(
    not os.getenv("RCI_TEST_DATABASE_URL"),
    reason="set RCI_TEST_DATABASE_URL to run legacy request identity negatives",
)
async def test_postgres_legacy_identity_contract_and_artifact_drift_fail_closed() -> None:
    database = DatabaseProbe(os.environ["RCI_TEST_DATABASE_URL"])
    collection_repository = PostgresCollectionRepository(database.engine)
    composite_repository = _scope_projection_repository(database)
    fixture: _ScopeProjectionFixture | None = None
    try:
        fixture = await _create_scope_projection_fixture(
            database,
            collection_repository,
            pair_count=1,
            canonical_count=4,
            unpaired_scopes=(("2000000", "45069"),),
            include_benchmark_failure=False,
            legacy_contracts=True,
        )
        preview = await composite_repository.preview_scope_projection(
            fixture.base_run.id,
            retailer_id="kroger_us",
            projection_kind="audited_alias_reconciliation",
            source_audit_id=fixture.source_audit_id,
        )
        organization_id = await _run_organization_id(database, fixture.base_run.id)
        original_items = _scope_projection_item_documents(preview)

        spoofed_provenance_items = json.loads(json.dumps(original_items))
        spoofed_provenance = spoofed_provenance_items[0]["source_snapshot"]["task"][
            "request_identity_provenance"
        ]
        spoofed_provenance["verified_fields"].append("historical_parameter_values")
        spoofed_provenance["unexpected_claim"] = True
        with pytest.raises(DBAPIError, match="request identity differs"):
            async with database.engine.begin() as connection:
                await _insert_audited_projection_preview(
                    connection,
                    preview,
                    organization_id=organization_id,
                    items=spoofed_provenance_items,
                )

        with pytest.raises(DBAPIError, match="called legacy task conflicts"):
            async with database.engine.begin() as connection:
                await connection.execute(
                    text(
                        "UPDATE dataset_artifact SET metadata = "
                        "jsonb_set(metadata, '{request_path}', '\"/spoofed/path\"'::jsonb) "
                        "WHERE id = (SELECT raw_artifact_id FROM collection_task "
                        "WHERE collection_run_id = CAST(:run_id AS uuid) "
                        "AND raw_artifact_id IS NOT NULL ORDER BY id LIMIT 1)"
                    ),
                    {"run_id": fixture.base_run.id},
                )
                await _insert_audited_projection_preview(
                    connection,
                    preview,
                    organization_id=organization_id,
                )

        with pytest.raises(DBAPIError, match="called legacy task conflicts"):
            async with database.engine.begin() as connection:
                await connection.execute(
                    text(
                        "UPDATE collection_task SET http_status = NULL "
                        "WHERE id = CAST(:task_id AS uuid)"
                    ),
                    {"task_id": fixture.canonical_task_ids[0]},
                )
                await _insert_audited_projection_preview(
                    connection,
                    preview,
                    organization_id=organization_id,
                )

        with pytest.raises(DBAPIError, match="called legacy task conflicts"):
            async with database.engine.begin() as connection:
                await connection.execute(
                    text(
                        "UPDATE dataset_artifact SET artifact_type = 'analysis_input' "
                        "WHERE id = (SELECT raw_artifact_id FROM collection_task "
                        "WHERE id = CAST(:task_id AS uuid))"
                    ),
                    {"task_id": fixture.canonical_task_ids[0]},
                )
                await _insert_audited_projection_preview(
                    connection,
                    preview,
                    organization_id=organization_id,
                )

        spoofed_contract_manifest = json.loads(json.dumps(preview.manifest))
        request_identity = spoofed_contract_manifest["source_evidence"]["request_identity"]
        adapter_evidence = request_identity["contracts"]["fake_kroger"]
        adapter_evidence["contract"]["path"] = "/spoofed/path"
        adapter_evidence["sealed_contract_checksum"] = canonical_checksum(
            adapter_evidence["contract"]
        )
        spoofed_source_evidence_checksum = canonical_checksum(
            spoofed_contract_manifest["source_evidence"]
        )
        spoofed_contract_manifest["source_evidence_checksum"] = spoofed_source_evidence_checksum
        with pytest.raises(DBAPIError, match="request identity differs"):
            async with database.engine.begin() as connection:
                await _insert_audited_projection_preview(
                    connection,
                    preview,
                    organization_id=organization_id,
                    manifest=spoofed_contract_manifest,
                    header_overrides={"source_evidence_checksum": spoofed_source_evidence_checksum},
                )

        noncanonical_contract_manifest = json.loads(json.dumps(preview.manifest))
        noncanonical_identity = noncanonical_contract_manifest["source_evidence"][
            "request_identity"
        ]
        noncanonical_adapter = noncanonical_identity["contracts"]["fake_kroger"]
        noncanonical_adapter["contract"]["unexpected_unsealed_semantic"] = True
        noncanonical_adapter["sealed_contract_checksum"] = canonical_checksum(
            noncanonical_adapter["contract"]
        )
        noncanonical_source_checksum = canonical_checksum(
            noncanonical_contract_manifest["source_evidence"]
        )
        noncanonical_contract_manifest["source_evidence_checksum"] = noncanonical_source_checksum
        with pytest.raises(DBAPIError, match="request identity differs"):
            async with database.engine.begin() as connection:
                await _insert_audited_projection_preview(
                    connection,
                    preview,
                    organization_id=organization_id,
                    manifest=noncanonical_contract_manifest,
                    header_overrides={"source_evidence_checksum": noncanonical_source_checksum},
                )

        with pytest.raises(DBAPIError, match="source snapshot differs"):
            async with database.engine.begin() as connection:
                await connection.execute(
                    text(
                        "UPDATE collection_task SET request_payload = "
                        "jsonb_set(request_payload, '{keyword}', '\"spoofed milk\"'::jsonb) "
                        "WHERE id = CAST(:task_id AS uuid)"
                    ),
                    {"task_id": fixture.canonical_task_ids[0]},
                )
                await _insert_audited_projection_preview(
                    connection,
                    preview,
                    organization_id=organization_id,
                )

        with pytest.raises(DBAPIError, match="zero-use cancellation"):
            async with database.engine.begin() as connection:
                await connection.execute(
                    text(
                        "UPDATE collection_task SET raw_artifact_id = NULL "
                        "WHERE id = CAST(:task_id AS uuid)"
                    ),
                    {"task_id": fixture.canonical_task_ids[0]},
                )
                await _insert_audited_projection_preview(
                    connection,
                    preview,
                    organization_id=organization_id,
                )

        with pytest.raises(DBAPIError, match="zero-use cancellation"):
            async with database.engine.begin() as connection:
                await connection.execute(
                    text(
                        "UPDATE collection_task SET attempt_count = 1 "
                        "WHERE id = CAST(:task_id AS uuid)"
                    ),
                    {"task_id": fixture.gap_task_ids[0]},
                )
                await _insert_audited_projection_preview(
                    connection,
                    preview,
                    organization_id=organization_id,
                )
    finally:
        if fixture is not None:
            await _cancel_concurrency_definition_runs(database, fixture.definition.version_id)
        await database.dispose()


@pytest.mark.skipif(
    not os.getenv("RCI_TEST_DATABASE_URL"),
    reason="set RCI_TEST_DATABASE_URL to run legacy projection recovery integration",
)
async def test_postgres_legacy_projection_recovery_clones_only_retained_sealed_tasks() -> None:
    database = DatabaseProbe(os.environ["RCI_TEST_DATABASE_URL"])
    collection_repository = PostgresCollectionRepository(database.engine)
    composite_repository = _scope_projection_repository(database)
    fixture: _ScopeProjectionFixture | None = None
    try:
        fixture = await _create_scope_projection_fixture(
            database,
            collection_repository,
            pair_count=3,
            canonical_count=6,
            unpaired_scopes=(("1400945", "45069"),),
            include_benchmark_failure=False,
            legacy_contracts=True,
        )
        projection_preview = await composite_repository.preview_scope_projection(
            fixture.base_run.id,
            retailer_id="kroger_us",
            projection_kind="audited_alias_reconciliation",
            source_audit_id=fixture.source_audit_id,
        )
        projection = await composite_repository.approve_scope_projection(
            fixture.base_run.id,
            retailer_id="kroger_us",
            projection_kind="audited_alias_reconciliation",
            projection_checksum=projection_preview.projection_checksum,
            base_snapshot_checksum=projection_preview.base_snapshot_checksum,
            review_reason="bind governed legacy aliases before exact recovery",
            reviewed_by="postgres-scope-projection-test",
            source_audit_id=fixture.source_audit_id,
        )
        recovery_preview = await composite_repository.preview(
            fixture.base_run.id,
            scope_projection_id=projection.id,
        )
        assert recovery_preview.selected_task_count == 2
        assert all(
            str(item.source_snapshot["location_scope_key"]).startswith("kroger:canonical:")
            for item in recovery_preview.items
        )
        changed_kroger_contract = {
            **_SCOPE_KROGER_REQUEST_CONTRACT,
            "path": "/fake/kroger/search/catalog-v2",
            "default_request_params": {"catalog_revision": "v2"},
        }
        changed_catalog_repository = PostgresCompositeEvidenceRepository(
            database.engine,
            provider_request_contracts={
                "fake_walmart": _SCOPE_WALMART_REQUEST_CONTRACT,
                "fake_kroger": changed_kroger_contract,
            },
        )
        changed_catalog_preview = await changed_catalog_repository.preview(
            fixture.base_run.id,
            scope_projection_id=projection.id,
        )
        assert changed_catalog_preview.base_snapshot_checksum == (
            recovery_preview.base_snapshot_checksum
        )
        assert changed_catalog_preview.selection_checksum == recovery_preview.selection_checksum
        assert [item.source_task_id for item in changed_catalog_preview.items] == [
            item.source_task_id for item in recovery_preview.items
        ]
        repeated_projection = await changed_catalog_repository.approve_scope_projection(
            fixture.base_run.id,
            retailer_id="kroger_us",
            projection_kind="audited_alias_reconciliation",
            projection_checksum=projection_preview.projection_checksum,
            base_snapshot_checksum=projection_preview.base_snapshot_checksum,
            review_reason="bind governed legacy aliases before exact recovery",
            reviewed_by="postgres-scope-projection-test",
            source_audit_id=fixture.source_audit_id,
        )
        assert repeated_projection.id == projection.id
        organization_id = await _run_organization_id(database, fixture.base_run.id)
        authorization = await changed_catalog_repository.authorize_recovery_spend(
            organization_id=organization_id,
            phase_key=f"postgres-legacy-projection-recovery-{uuid4()}",
            approved_credit_ceiling=14,
            unit_cost_usd="0.002000",
            currency="USD",
            reason="prove sealed legacy clone execution contract",
            authorized_by="postgres-scope-projection-test",
            collection_run_ids=(fixture.base_run.id,),
        )
        batch = await changed_catalog_repository.create_recovery_batch(
            authorization_id=authorization.id
        )
        plan = await changed_catalog_repository.approve(
            fixture.base_run.id,
            selection_checksum=changed_catalog_preview.selection_checksum,
            approved_credit_ceiling=changed_catalog_preview.maximum_credits,
            reason="recover only unresolved retained provider-safe scopes",
            approved_by="postgres-scope-projection-test",
            recovery_batch_id=batch.id,
            scope_projection_id=projection.id,
            scope_projection_checksum=projection.projection_checksum,
        )
        launch = await changed_catalog_repository.launch_exact_recovery(plan.id)

        async with database.engine.connect() as connection:
            clone_rows = list(
                (
                    await connection.execute(
                        text(
                            "SELECT location_scope_key, request_payload, request_fingerprint "
                            "FROM collection_task WHERE collection_run_id = "
                            "CAST(:run_id AS uuid) ORDER BY location_scope_key"
                        ),
                        {"run_id": launch.collection_run_id},
                    )
                )
                .mappings()
                .all()
            )
            binding = (
                (
                    await connection.execute(
                        text(
                            "SELECT scope_projection_id::text, scope_projection_checksum "
                            "FROM collection_recovery_plan WHERE id = CAST(:plan_id AS uuid)"
                        ),
                        {"plan_id": plan.id},
                    )
                )
                .mappings()
                .one()
            )
        assert len(clone_rows) == 2
        assert all(
            str(row["location_scope_key"]).startswith("kroger:canonical:") for row in clone_rows
        )
        assert all(
            "_provider_request_contract" in dict(row["request_payload"]) for row in clone_rows
        )
        assert all(
            dict(row["request_payload"])["_provider_request_contract"]
            == _SCOPE_KROGER_REQUEST_CONTRACT
            for row in clone_rows
        )
        assert all(
            str(row["request_fingerprint"]) == canonical_checksum(dict(row["request_payload"]))
            for row in clone_rows
        )
        assert dict(binding) == {
            "scope_projection_id": projection.id,
            "scope_projection_checksum": projection.projection_checksum,
        }
    finally:
        if fixture is not None:
            await _cancel_concurrency_definition_runs(database, fixture.definition.version_id)
        await database.dispose()


@pytest.mark.skipif(
    not os.getenv("RCI_TEST_DATABASE_URL"),
    reason="set RCI_TEST_DATABASE_URL to run audited source immutability integration",
)
async def test_postgres_audited_projection_protects_frozen_source_evidence() -> None:
    database = DatabaseProbe(os.environ["RCI_TEST_DATABASE_URL"])
    collection_repository = PostgresCollectionRepository(database.engine)
    composite_repository = _scope_projection_repository(database)
    fixture: _ScopeProjectionFixture | None = None
    try:
        fixture = await _create_scope_projection_fixture(
            database,
            collection_repository,
            pair_count=1,
            canonical_count=4,
            unpaired_scopes=(("1400945", "45069"),),
            include_benchmark_failure=False,
            legacy_contracts=True,
        )
        preview = await composite_repository.preview_scope_projection(
            fixture.base_run.id,
            retailer_id="kroger_us",
            projection_kind="audited_alias_reconciliation",
            source_audit_id=fixture.source_audit_id,
        )
        projection = await composite_repository.approve_scope_projection(
            fixture.base_run.id,
            retailer_id="kroger_us",
            projection_kind="audited_alias_reconciliation",
            projection_checksum=preview.projection_checksum,
            base_snapshot_checksum=preview.base_snapshot_checksum,
            review_reason="prove bounded source immutability after approval",
            reviewed_by="postgres-scope-projection-test",
            source_audit_id=fixture.source_audit_id,
        )
        recovery_before_master_change = await composite_repository.preview(
            fixture.base_run.id,
            scope_projection_id=projection.id,
        )
        async with database.engine.connect() as connection:
            retained_location_id = str(
                (
                    await connection.execute(
                        text(
                            "SELECT retailer_location_id::text FROM collection_task "
                            "WHERE id = CAST(:task_id AS uuid)"
                        ),
                        {"task_id": fixture.canonical_task_ids[0]},
                    )
                ).scalar_one()
            )
            stored_approval_eligibility = (
                await connection.execute(
                    text(
                        "SELECT source_snapshot->'current_location_eligible' "
                        "FROM collection_scope_projection_task "
                        "WHERE scope_projection_id = CAST(:projection_id AS uuid) "
                        "AND source_task_id = CAST(:task_id AS uuid)"
                    ),
                    {
                        "projection_id": projection.id,
                        "task_id": fixture.canonical_task_ids[0],
                    },
                )
            ).scalar_one()
        assert stored_approval_eligibility is True

        # The current location master remains operationally mutable.  Its later
        # eligibility state must not reinterpret the sealed approval-time scope.
        async with database.engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE retailer_location SET collection_eligible = false "
                    "WHERE id = CAST(:location_id AS uuid)"
                ),
                {"location_id": retained_location_id},
            )
        recovery_after_master_change = await composite_repository.preview(
            fixture.base_run.id,
            scope_projection_id=projection.id,
        )
        assert (
            recovery_after_master_change.base_snapshot_checksum
            == recovery_before_master_change.base_snapshot_checksum
        )
        assert (
            recovery_after_master_change.selection_checksum
            == recovery_before_master_change.selection_checksum
        )
        assert [item.source_task_id for item in recovery_after_master_change.items] == [
            item.source_task_id for item in recovery_before_master_change.items
        ]
        repeated_projection = await composite_repository.approve_scope_projection(
            fixture.base_run.id,
            retailer_id="kroger_us",
            projection_kind="audited_alias_reconciliation",
            projection_checksum=preview.projection_checksum,
            base_snapshot_checksum=preview.base_snapshot_checksum,
            review_reason="prove bounded source immutability after approval",
            reviewed_by="postgres-scope-projection-test",
            source_audit_id=fixture.source_audit_id,
        )
        assert repeated_projection.id == projection.id
        async with database.engine.connect() as connection:
            assert (
                await connection.execute(
                    text(
                        "SELECT source_snapshot->'current_location_eligible' "
                        "FROM collection_scope_projection_task "
                        "WHERE scope_projection_id = CAST(:projection_id AS uuid) "
                        "AND source_task_id = CAST(:task_id AS uuid)"
                    ),
                    {
                        "projection_id": projection.id,
                        "task_id": fixture.canonical_task_ids[0],
                    },
                )
            ).scalar_one() is True
        async with database.engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE retailer_location SET collection_eligible = true "
                    "WHERE id = CAST(:location_id AS uuid)"
                ),
                {"location_id": retained_location_id},
            )
        unrelated_task_id = await _create_cross_run_scope_task(
            database, collection_repository, fixture.definition
        )
        async with database.engine.connect() as connection:
            source = dict(
                (
                    await connection.execute(
                        text(
                            "SELECT task.raw_artifact_id::text AS artifact_id, "
                            "geography.id::text AS geography_location_id, "
                            "version.id::text AS definition_version_id, "
                            "version.geography_resolution_id::text AS resolution_id "
                            "FROM collection_task task "
                            "JOIN collection_run run ON run.id = task.collection_run_id "
                            "JOIN collection_definition_version version "
                            "ON version.id = run.definition_version_id "
                            "JOIN collection_geography_location geography "
                            "ON geography.resolution_id = version.geography_resolution_id "
                            "AND geography.retailer_id = task.retailer_id "
                            "AND geography.scope_key = task.location_scope_key "
                            "WHERE task.id = CAST(:task_id AS uuid)"
                        ),
                        {"task_id": fixture.canonical_task_ids[0]},
                    )
                )
                .mappings()
                .one()
            )
            unrelated_run_id = str(
                (
                    await connection.execute(
                        text(
                            "SELECT collection_run_id::text FROM collection_task "
                            "WHERE id = CAST(:task_id AS uuid)"
                        ),
                        {"task_id": unrelated_task_id},
                    )
                ).scalar_one()
            )
            source_index = str(
                (
                    await connection.execute(
                        text(
                            "SELECT indexdef FROM pg_indexes WHERE schemaname = current_schema() "
                            "AND indexname = 'collection_scope_projection_task_source_idx'"
                        )
                    )
                ).scalar_one()
            )
        assert "(source_task_id, scope_projection_id)" in source_index

        protected_statements = (
            (
                "UPDATE collection_task SET last_error = last_error "
                "WHERE id = CAST(:target_id AS uuid)",
                fixture.canonical_task_ids[0],
            ),
            (
                "DELETE FROM collection_task WHERE id = CAST(:target_id AS uuid)",
                fixture.canonical_task_ids[0],
            ),
            (
                "UPDATE dataset_artifact SET metadata = metadata "
                "WHERE id = CAST(:target_id AS uuid)",
                source["artifact_id"],
            ),
            (
                "DELETE FROM dataset_artifact WHERE id = CAST(:target_id AS uuid)",
                source["artifact_id"],
            ),
            (
                "UPDATE collection_geography_location SET selection_reason = selection_reason "
                "WHERE id = CAST(:target_id AS uuid)",
                source["geography_location_id"],
            ),
            (
                "DELETE FROM collection_geography_location WHERE id = CAST(:target_id AS uuid)",
                source["geography_location_id"],
            ),
            (
                "UPDATE collection_definition_version SET config = config "
                "WHERE id = CAST(:target_id AS uuid)",
                source["definition_version_id"],
            ),
            (
                "DELETE FROM collection_definition_version WHERE id = CAST(:target_id AS uuid)",
                source["definition_version_id"],
            ),
            (
                "UPDATE collection_run SET status = status WHERE id = CAST(:target_id AS uuid)",
                fixture.base_run.id,
            ),
            (
                "DELETE FROM collection_run WHERE id = CAST(:target_id AS uuid)",
                fixture.base_run.id,
            ),
        )
        for statement, target_id in protected_statements:
            assert target_id is not None
            with pytest.raises(
                DBAPIError,
                match=r"source evidence is immutable|violates foreign key constraint",
            ):
                async with database.engine.begin() as connection:
                    await connection.execute(text(statement), {"target_id": target_id})

        with pytest.raises(DBAPIError, match="source evidence is immutable"):
            async with database.engine.begin() as connection:
                await connection.execute(
                    text(
                        "UPDATE collection_task SET collection_run_id = "
                        "CAST(:base_run_id AS uuid), "
                        "location_scope_key = location_scope_key || ':moved' "
                        "WHERE id = CAST(:task_id AS uuid)"
                    ),
                    {
                        "base_run_id": fixture.base_run.id,
                        "task_id": unrelated_task_id,
                    },
                )

        with pytest.raises(DBAPIError, match="source evidence is immutable"):
            async with database.engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO collection_task (collection_run_id, retailer_id, "
                        "retailer_location_id, adapter_id, location_scope_key, zipcode, "
                        "store_number, page_number, max_pages, stop_on_empty, "
                        "stop_on_short_page, credits_per_success, request_payload, "
                        "request_fingerprint, status, max_attempts) "
                        "SELECT CAST(:base_run_id AS uuid), retailer_id, retailer_location_id, "
                        "adapter_id, location_scope_key || ':late', zipcode, store_number, "
                        "page_number, max_pages, stop_on_empty, stop_on_short_page, "
                        "credits_per_success, request_payload, request_fingerprint || '-late', "
                        "status, max_attempts FROM collection_task "
                        "WHERE id = CAST(:task_id AS uuid)"
                    ),
                    {
                        "base_run_id": fixture.base_run.id,
                        "task_id": unrelated_task_id,
                    },
                )

        unrelated_resolution_id = str(uuid4())
        organization_id = await _run_organization_id(database, fixture.base_run.id)
        unrelated_geography_id: str
        async with database.engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE collection_task SET last_error = 'unrelated mutation allowed' "
                    "WHERE id = CAST(:task_id AS uuid)"
                ),
                {"task_id": unrelated_task_id},
            )
            await connection.execute(
                text("UPDATE collection_run SET status = status WHERE id = CAST(:run_id AS uuid)"),
                {"run_id": unrelated_run_id},
            )
            await connection.execute(
                text(
                    "UPDATE collection_geography_resolution SET counts = counts "
                    "WHERE id = CAST(:resolution_id AS uuid)"
                ),
                {"resolution_id": source["resolution_id"]},
            )
            await connection.execute(
                text(
                    "INSERT INTO collection_geography_resolution (id, organization_id, "
                    "primary_retailer_id, country, request, checksum, status, counts) "
                    "VALUES (CAST(:resolution_id AS uuid), CAST(:organization_id AS uuid), "
                    "'walmart_us', 'USA', '{\"fixture\":\"unrelated\"}'::jsonb, "
                    ":checksum, 'ready', '{}'::jsonb)"
                ),
                {
                    "resolution_id": unrelated_resolution_id,
                    "organization_id": organization_id,
                    "checksum": canonical_checksum({"fixture": unrelated_resolution_id}),
                },
            )
            unrelated_geography_id = str(
                (
                    await connection.execute(
                        text(
                            "INSERT INTO collection_geography_location (resolution_id, role, "
                            "retailer_id, scope_key, store_number, zipcode, country, "
                            "selection_reason) VALUES (CAST(:resolution_id AS uuid), "
                            "'competitor', 'kroger_us', :scope_key, '09999999', '99999', "
                            "'USA', 'unrelated_fixture') RETURNING id::text"
                        ),
                        {
                            "resolution_id": unrelated_resolution_id,
                            "scope_key": f"unrelated:{uuid4()}",
                        },
                    )
                ).scalar_one()
            )

        # Rows with no inventoried task identity are outside the projection's
        # source authority even when they share the bound resolution.
        async with database.engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO collection_geography_location (resolution_id, role, "
                    "retailer_id, scope_key, store_number, zipcode, country, "
                    "selection_reason) VALUES (CAST(:protected_resolution_id AS uuid), "
                    "'competitor', 'kroger_us', :scope_key, '09999998', '99998', "
                    "'USA', 'late_unlinked_fixture')"
                ),
                {
                    "protected_resolution_id": source["resolution_id"],
                    "scope_key": f"late-unlinked:{uuid4()}",
                },
            )
            await connection.execute(
                text(
                    "UPDATE collection_geography_location SET resolution_id = "
                    "CAST(:protected_resolution_id AS uuid) "
                    "WHERE id = CAST(:unrelated_geography_id AS uuid)"
                ),
                {
                    "protected_resolution_id": source["resolution_id"],
                    "unrelated_geography_id": unrelated_geography_id,
                },
            )
    finally:
        if fixture is not None:
            await _cancel_concurrency_definition_runs(database, fixture.definition.version_id)
        await database.dispose()


@pytest.mark.skipif(
    not os.getenv("RCI_TEST_DATABASE_URL"),
    reason="set RCI_TEST_DATABASE_URL to run projected materialization integration",
)
async def test_postgres_projection_bound_materialization_is_exact_and_atomic() -> None:
    database = DatabaseProbe(os.environ["RCI_TEST_DATABASE_URL"])
    collection_repository = PostgresCollectionRepository(database.engine)
    composite_repository = _scope_projection_repository(database)
    fixture: _ScopeProjectionFixture | None = None
    wrong_fixture: _ScopeProjectionFixture | None = None
    try:
        fixture = await _create_scope_projection_fixture(
            database,
            collection_repository,
            pair_count=1,
            include_benchmark_failure=True,
        )
        preview = await composite_repository.preview_scope_projection(
            fixture.base_run.id,
            retailer_id="kroger_us",
            projection_kind="canonical_alias_collapse",
            source_audit_id=fixture.source_audit_id,
        )
        projection = await composite_repository.approve_scope_projection(
            fixture.base_run.id,
            retailer_id="kroger_us",
            projection_kind="canonical_alias_collapse",
            projection_checksum=preview.projection_checksum,
            base_snapshot_checksum=preview.base_snapshot_checksum,
            review_reason="bind the complete canonical projection to materialization",
            reviewed_by="postgres-scope-projection-test",
            source_audit_id=fixture.source_audit_id,
        )
        recovery_preview = await composite_repository.preview(
            fixture.base_run.id,
            scope_projection_id=projection.id,
        )
        assert recovery_preview.selected_task_count == 1
        organization_id = await _run_organization_id(database, fixture.base_run.id)
        authorization = await composite_repository.authorize_recovery_spend(
            organization_id=organization_id,
            phase_key=f"postgres-projected-materialization-{uuid4()}",
            approved_credit_ceiling=10,
            unit_cost_usd="0.002000",
            currency="USD",
            reason="exercise atomic projection-bound materialization",
            authorized_by="postgres-scope-projection-test",
            collection_run_ids=(fixture.base_run.id,),
        )
        batch = await composite_repository.create_recovery_batch(authorization_id=authorization.id)
        plan = await composite_repository.approve(
            fixture.base_run.id,
            selection_checksum=recovery_preview.selection_checksum,
            approved_credit_ceiling=recovery_preview.maximum_credits,
            reason="recover the benchmark failure under the reviewed scope projection",
            approved_by="postgres-scope-projection-test",
            recovery_batch_id=batch.id,
            scope_projection_id=projection.id,
            scope_projection_checksum=projection.projection_checksum,
        )
        recovery = await composite_repository.launch_exact_recovery(plan.id)
        recovery_task_id = await _complete_scope_recovery_fixture(
            database, recovery.collection_run_id
        )

        class FailingAfterProjectionLinkRepository(PostgresCompositeEvidenceRepository):
            async def _queue_composite_analysis(
                self,
                connection: object,
                input_set_id: str,
                *,
                queue_allowed: bool,
            ) -> str | None:
                await super()._queue_composite_analysis(  # type: ignore[arg-type]
                    connection, input_set_id, queue_allowed=queue_allowed
                )
                raise RuntimeError("forced failure after projection lineage insertion")

        failing_repository = FailingAfterProjectionLinkRepository(
            database.engine,
            provider_request_contracts={
                "fake_walmart": _SCOPE_WALMART_REQUEST_CONTRACT,
                "fake_kroger": _SCOPE_KROGER_REQUEST_CONTRACT,
            },
        )
        with pytest.raises(RuntimeError, match="forced failure"):
            await failing_repository.materialize(
                fixture.base_run.id,
                (plan.id,),
                (projection.id,),
            )
        assert await _projection_materialization_counts(database, fixture.base_run.id) == {
            "input_count": 0,
            "lineage_count": 0,
            "artifact_count": 0,
            "projection_count": 0,
            "analysis_count": 0,
        }

        materialized = await composite_repository.materialize(
            fixture.base_run.id,
            (plan.id,),
            (projection.id,),
        )
        repeated = await composite_repository.materialize(
            fixture.base_run.id,
            (plan.id,),
            (projection.id,),
        )
        assert repeated.id == materialized.id
        async with database.engine.connect() as connection:
            selected_task_ids = set(
                str(value)
                for value in (
                    await connection.execute(
                        text(
                            "SELECT selected_task_id::text "
                            "FROM analysis_input_task_lineage "
                            "WHERE input_set_id::text = :input_set_id"
                        ),
                        {"input_set_id": materialized.id},
                    )
                ).scalars()
            )
            artifact_task_ids = set(
                str(value)
                for value in (
                    await connection.execute(
                        text(
                            "SELECT metadata->>'task_id' FROM analysis_input_artifact "
                            "WHERE input_set_id::text = :input_set_id"
                        ),
                        {"input_set_id": materialized.id},
                    )
                ).scalars()
            )
            projection_links = [
                dict(row)
                for row in (
                    (
                        await connection.execute(
                            text(
                                "SELECT scope_projection_id::text AS scope_projection_id, "
                                "ordinal, projection_checksum "
                                "FROM analysis_input_scope_projection "
                                "WHERE input_set_id::text = :input_set_id"
                            ),
                            {"input_set_id": materialized.id},
                        )
                    )
                    .mappings()
                    .all()
                )
            ]
        assert fixture.alias_task_ids[0] not in selected_task_ids
        assert fixture.alias_task_ids[0] not in artifact_task_ids
        assert fixture.canonical_task_ids[0] in selected_task_ids
        assert fixture.canonical_task_ids[0] in artifact_task_ids
        assert fixture.benchmark_task_id not in selected_task_ids
        assert recovery_task_id in selected_task_ids
        assert projection_links == [
            {
                "scope_projection_id": projection.id,
                "ordinal": 0,
                "projection_checksum": projection.projection_checksum,
            }
        ]
        assert await _projection_materialization_counts(database, fixture.base_run.id) == {
            "input_count": 1,
            "lineage_count": 2,
            "artifact_count": 2,
            "projection_count": 1,
            "analysis_count": 1,
        }

        with pytest.raises(ValueError, match="requires every recovery-plan scope projection"):
            await composite_repository.materialize(fixture.base_run.id, (plan.id,), ())

        wrong_fixture = await _create_scope_projection_fixture(
            database,
            collection_repository,
            pair_count=1,
            include_benchmark_failure=False,
        )
        wrong_preview = await composite_repository.preview_scope_projection(
            wrong_fixture.base_run.id,
            retailer_id="kroger_us",
            projection_kind="canonical_alias_collapse",
            source_audit_id=wrong_fixture.source_audit_id,
        )
        wrong_projection = await composite_repository.approve_scope_projection(
            wrong_fixture.base_run.id,
            retailer_id="kroger_us",
            projection_kind="canonical_alias_collapse",
            projection_checksum=wrong_preview.projection_checksum,
            base_snapshot_checksum=wrong_preview.base_snapshot_checksum,
            review_reason="wrong-base projection trigger fixture",
            reviewed_by="postgres-scope-projection-test",
            source_audit_id=wrong_fixture.source_audit_id,
        )
        with pytest.raises(ValueError, match="requires every recovery-plan scope projection"):
            await composite_repository.materialize(
                fixture.base_run.id,
                (plan.id,),
                (wrong_projection.id,),
            )

        with pytest.raises(DBAPIError, match="analysis input scope-projection binding"):
            async with database.engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO analysis_input_scope_projection ("
                        "input_set_id, scope_projection_id, ordinal, projection_checksum"
                        ") VALUES (CAST(:input_set_id AS uuid), "
                        "CAST(:projection_id AS uuid), 99, :checksum)"
                    ),
                    {
                        "input_set_id": materialized.id,
                        "projection_id": wrong_projection.id,
                        "checksum": wrong_projection.projection_checksum,
                    },
                )
        with pytest.raises(DBAPIError, match="analysis input scope-projection binding"):
            async with database.engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO analysis_input_scope_projection ("
                        "input_set_id, scope_projection_id, ordinal, projection_checksum"
                        ") VALUES (CAST(:input_set_id AS uuid), "
                        "CAST(:projection_id AS uuid), 99, :checksum)"
                    ),
                    {
                        "input_set_id": materialized.id,
                        "projection_id": projection.id,
                        "checksum": "0" * 64,
                    },
                )
        with pytest.raises(DBAPIError, match="immutable"):
            async with database.engine.begin() as connection:
                await connection.execute(
                    text(
                        "DELETE FROM analysis_input_scope_projection "
                        "WHERE input_set_id::text = :input_set_id"
                    ),
                    {"input_set_id": materialized.id},
                )
        with pytest.raises(DBAPIError, match="recovery plan scope projection binding"):
            async with database.engine.begin() as connection:
                await connection.execute(
                    text(
                        "UPDATE collection_recovery_plan SET "
                        "scope_projection_id = CAST(:projection_id AS uuid), "
                        "scope_projection_checksum = :checksum WHERE id::text = :plan_id"
                    ),
                    {
                        "projection_id": wrong_projection.id,
                        "checksum": wrong_projection.projection_checksum,
                        "plan_id": plan.id,
                    },
                )
    finally:
        for candidate in (fixture, wrong_fixture):
            if candidate is not None:
                await _cancel_concurrency_definition_runs(database, candidate.definition.version_id)
        await database.dispose()


@pytest.mark.skipif(
    not os.getenv("RCI_TEST_DATABASE_URL"),
    reason="set RCI_TEST_DATABASE_URL to run Postgres scope-projection downgrade refusal",
)
async def test_postgres_audited_reconciliation_history_refuses_0054_downgrade() -> None:
    database_url = os.environ["RCI_TEST_DATABASE_URL"]
    database = DatabaseProbe(database_url)
    collection_repository = PostgresCollectionRepository(database.engine)
    composite_repository = _scope_projection_repository(database)
    fixture = await _create_scope_projection_fixture(
        database,
        collection_repository,
        pair_count=1,
        canonical_count=2,
        unpaired_scopes=(("1400945", "45069"),),
        include_benchmark_failure=False,
    )
    preview = await composite_repository.preview_scope_projection(
        fixture.base_run.id,
        retailer_id="kroger_us",
        projection_kind="audited_alias_reconciliation",
        source_audit_id=fixture.source_audit_id,
    )
    await composite_repository.approve_scope_projection(
        fixture.base_run.id,
        retailer_id="kroger_us",
        projection_kind="audited_alias_reconciliation",
        projection_checksum=preview.projection_checksum,
        base_snapshot_checksum=preview.base_snapshot_checksum,
        review_reason="prove audited reconciliation history blocks 0054 downgrade",
        reviewed_by="postgres-scope-projection-test",
        source_audit_id=fixture.source_audit_id,
    )
    await database.dispose()

    environment = {**os.environ, "DATABASE_URL": database_url}
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "database/alembic.ini",
            "downgrade",
            "0053_scope_projections",
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode != 0
    assert "cannot downgrade 0054 while audited alias reconciliation history exists" in (
        completed.stdout + completed.stderr
    )
    verification = DatabaseProbe(database_url)
    try:
        async with verification.engine.connect() as connection:
            assert (
                await connection.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar_one() == "0054_audited_alias_reconcile"
    finally:
        await verification.dispose()


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


@pytest.mark.skipif(
    not os.getenv("RCI_TEST_DATABASE_URL"),
    reason="set RCI_TEST_DATABASE_URL to run Postgres continuation concurrency integration",
)
async def test_postgres_concurrent_continuation_approval_is_idempotent_and_reserves_once() -> None:
    database = DatabaseProbe(os.environ["RCI_TEST_DATABASE_URL"])
    collection_repository = PostgresCollectionRepository(database.engine)
    composite_repository = _postgres_composite_repository(database)
    definition: DefinitionRecord | None = None
    try:
        definition = await _publish_concurrency_definition(
            collection_repository, f"postgres-continuation-{uuid4()}"
        )
        base_run = await _create_terminal_concurrency_run(
            database,
            collection_repository,
            definition,
            request_index=0,
            outcome="failed",
        )
        legacy_recovery = await _create_terminal_concurrency_run(
            database,
            collection_repository,
            definition,
            request_index=0,
            outcome="failed",
        )
        initial_preview = await composite_repository.preview(base_run.id)
        batch_id = await _create_concurrency_batch(
            database,
            composite_repository,
            (base_run.id, legacy_recovery.id),
            approved_credit_ceiling=1,
            phase_key=f"postgres-continuation-{uuid4()}",
        )
        root_plan = await composite_repository.approve(
            base_run.id,
            selection_checksum=initial_preview.selection_checksum,
            approved_credit_ceiling=initial_preview.maximum_credits,
            reason="adopt terminal failed recovery before bounded continuation",
            approved_by="postgres-concurrency-test",
            recovery_batch_id=batch_id,
            plan_mode="legacy_adoption",
        )
        root_plan = await composite_repository.bind_recovery_run(
            root_plan.id,
            legacy_recovery.id,
            binding_mode="legacy_operational_adoption",
        )
        continuation = await composite_repository.preview_continuation(root_plan.id)
        assert continuation.selected_task_count == 1
        assert continuation.maximum_credits == 1

        outcomes = await asyncio.wait_for(
            asyncio.gather(
                *(
                    composite_repository.approve_continuation(
                        root_plan.id,
                        selection_checksum=continuation.selection_checksum,
                        lineage_checksum=continuation.lineage_checksum,
                        base_snapshot_checksum=continuation.base_snapshot_checksum,
                        approved_credit_ceiling=continuation.maximum_credits,
                        reason="one immutable unresolved-only continuation",
                        approved_by="postgres-concurrency-test",
                        recovery_batch_id=batch_id,
                    )
                    for _ in range(2)
                ),
            ),
            timeout=10,
        )

        assert len({record.id for record in outcomes}) == 1
        assert {record.continuation_of_recovery_plan_id for record in outcomes} == {root_plan.id}
        async with database.engine.connect() as connection:
            child_count = int(
                (
                    await connection.execute(
                        text(
                            "SELECT count(*) FROM collection_recovery_plan "
                            "WHERE continuation_of_recovery_plan_id::text = :parent_id"
                        ),
                        {"parent_id": root_plan.id},
                    )
                ).scalar_one()
            )
            reserved_credits = int(
                (
                    await connection.execute(
                        text(
                            "SELECT reserved_credits FROM collection_recovery_batch "
                            "WHERE id::text = :batch_id"
                        ),
                        {"batch_id": batch_id},
                    )
                ).scalar_one()
            )
        assert child_count == 1
        assert reserved_credits == 1
    finally:
        if definition is not None:
            await _cancel_concurrency_definition_runs(database, definition.version_id)
        await database.dispose()


async def _publish_bulk_materialization_definition(
    repository: PostgresCollectionRepository,
    stable_key: str,
    *,
    task_count: int,
) -> DefinitionRecord:
    config: dict[str, object] = {
        "id": stable_key,
        "name": "Postgres Composite Bulk Materialization Test",
        "enabled": True,
        "benchmark_retailer": "walmart_us",
        "product_pack": {"id": "fresh_fluid_milk", "version": "1.0.0"},
        "query": {"keyword": "milk"},
        "budget": {
            "max_credits_per_run": task_count + 10,
            "max_credits_per_day": (task_count + 10) * 2,
            "max_credits_per_month": (task_count + 10) * 2,
        },
    }
    return await repository.publish_definition(config, canonical_checksum(config))


async def _attach_bulk_materialization_geography(
    database: DatabaseProbe,
    definition: DefinitionRecord,
    *,
    task_count: int,
) -> None:
    resolution_id = str(uuid4())
    async with database.engine.begin() as connection:
        organization_id = str(
            (
                await connection.execute(
                    text(
                        """
                        SELECT d.organization_id::text
                        FROM collection_definition_version v
                        JOIN collection_definition d ON d.id = v.definition_id
                        WHERE v.id::text = :version_id
                        """
                    ),
                    {"version_id": definition.version_id},
                )
            ).scalar_one()
        )
        await connection.execute(
            text(
                """
                INSERT INTO collection_geography_resolution (
                  id, organization_id, primary_retailer_id, country,
                  request, checksum, status, counts
                ) VALUES (
                  CAST(:resolution_id AS uuid), CAST(:organization_id AS uuid),
                  'walmart_us', 'USA', '{"fixture":"bulk-materialization"}'::jsonb,
                  :checksum, 'ready', CAST(:counts AS jsonb)
                )
                """
            ),
            {
                "resolution_id": resolution_id,
                "organization_id": organization_id,
                "checksum": canonical_checksum(
                    {
                        "definition_version_id": definition.version_id,
                        "task_count": task_count,
                    }
                ),
                "counts": f'{{"primary":{task_count},"competitor":0}}',
            },
        )
        await connection.execute(
            text(
                """
                INSERT INTO collection_geography_location (
                  resolution_id, role, retailer_id, retailer_location_id,
                  scope_key, store_number, zipcode, city, state, country,
                  latitude, longitude, selection_reason
                ) VALUES (
                  CAST(:resolution_id AS uuid), 'primary', 'walmart_us', NULL,
                  :scope_key, :store_number, :zipcode, 'Bulk City', 'CA', 'USA',
                  :latitude, :longitude, 'postgres_test_fixture'
                )
                """
            ),
            [
                {
                    "resolution_id": resolution_id,
                    "scope_key": f"bulk:{index}",
                    "store_number": str(900_000 + index),
                    "zipcode": f"{10_000 + index:05d}",
                    "latitude": 30.0 + index / 100_000,
                    "longitude": -100.0 - index / 100_000,
                }
                for index in range(task_count)
            ],
        )
        await connection.execute(
            text(
                "UPDATE collection_definition_version "
                "SET geography_resolution_id = CAST(:resolution_id AS uuid) "
                "WHERE id::text = :version_id"
            ),
            {"resolution_id": resolution_id, "version_id": definition.version_id},
        )


def _bulk_materialization_seed(index: int) -> TaskSeed:
    zipcode = f"{10_000 + index:05d}"
    store_number = str(900_000 + index)
    return TaskSeed(
        retailer_id="walmart_us",
        retailer_location_id=None,
        adapter_id="fake_walmart",
        location_scope_key=f"bulk:{index}",
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
        request_fingerprint=f"bulk-materialization-{index}",
        is_preflight=False,
        max_attempts=1,
    )


async def _complete_bulk_base_fixture(database: DatabaseProbe, run_id: str) -> None:
    async with database.engine.begin() as connection:
        await connection.execute(
            text(
                """
                WITH artifacts AS (
                  INSERT INTO dataset_artifact (
                    collection_run_id, artifact_type, storage_uri, content_type,
                    row_count, byte_size, checksum, schema_version, metadata
                  )
                  SELECT CAST(:run_id AS uuid), 'raw_provider_response',
                         's3://test/composite-bulk/' || t.id::text || '.json.gz',
                         'application/json', 2, 64,
                         md5(t.id::text) || md5(t.id::text), '1.0.0',
                         jsonb_build_object('task_id', t.id::text)
                  FROM collection_task t
                  WHERE t.collection_run_id = CAST(:run_id AS uuid)
                    AND t.location_scope_key NOT IN ('bulk:0', 'bulk:1')
                  RETURNING id, metadata->>'task_id' AS task_id
                )
                UPDATE collection_task t
                SET status = 'succeeded', completed_at = now(), http_status = 200,
                    result_count = 2, billable_credits = 1, raw_artifact_id = artifacts.id
                FROM artifacts
                WHERE t.id::text = artifacts.task_id
                """
            ),
            {"run_id": run_id},
        )
        await connection.execute(
            text(
                """
                UPDATE collection_task
                SET status = 'failed', completed_at = now(),
                    http_status = CASE location_scope_key
                      WHEN 'bulk:0' THEN 500 ELSE 404 END,
                    failure_class = CASE location_scope_key
                      WHEN 'bulk:0' THEN 'lease_exhausted' ELSE 'invalid_request' END,
                    billable_credits = CASE location_scope_key
                      WHEN 'bulk:0' THEN 0 ELSE 1 END
                WHERE collection_run_id::text = :run_id
                  AND location_scope_key IN ('bulk:0', 'bulk:1')
                """
            ),
            {"run_id": run_id},
        )
        await connection.execute(
            text(
                """
                UPDATE collection_run
                SET status = 'completed_with_warnings',
                    actual_success_pages = :success_count,
                    actual_credits = :actual_credits,
                    completed_at = now()
                WHERE id::text = :run_id
                """
            ),
            {
                "run_id": run_id,
                "success_count": MATERIALIZATION_WRITE_BATCH_SIZE,
                "actual_credits": MATERIALIZATION_WRITE_BATCH_SIZE + 1,
            },
        )


async def _complete_bulk_recovery_fixture(database: DatabaseProbe, run_id: str) -> None:
    async with database.engine.begin() as connection:
        updated = int(
            (
                await connection.execute(
                    text(
                        """
                        WITH artifacts AS (
                          INSERT INTO dataset_artifact (
                            collection_run_id, artifact_type, storage_uri, content_type,
                            row_count, byte_size, checksum, schema_version, metadata
                          )
                          SELECT CAST(:run_id AS uuid), 'raw_provider_response',
                                 's3://test/composite-bulk-recovery/' || t.id::text || '.json.gz',
                                 'application/json', 2, 64,
                                 md5(t.id::text) || md5(t.id::text), '1.0.0',
                                 jsonb_build_object('task_id', t.id::text)
                          FROM collection_task t
                          WHERE t.collection_run_id = CAST(:run_id AS uuid)
                          RETURNING id, metadata->>'task_id' AS task_id
                        )
                        UPDATE collection_task t
                        SET status = 'succeeded', completed_at = now(), http_status = 200,
                            result_count = 2, billable_credits = 1,
                            raw_artifact_id = artifacts.id
                        FROM artifacts
                        WHERE t.id::text = artifacts.task_id
                        RETURNING 1
                        """
                    ),
                    {"run_id": run_id},
                )
            ).scalar_one()
        )
        assert updated == 1
        await connection.execute(
            text(
                "UPDATE collection_run SET status = 'succeeded', actual_success_pages = 1, "
                "actual_credits = 1, completed_at = now() WHERE id::text = :run_id"
            ),
            {"run_id": run_id},
        )


def _scope_projection_repository(
    database: DatabaseProbe,
) -> PostgresCompositeEvidenceRepository:
    return PostgresCompositeEvidenceRepository(
        database.engine,
        provider_request_contracts={
            "fake_walmart": _SCOPE_WALMART_REQUEST_CONTRACT,
            "fake_kroger": _SCOPE_KROGER_REQUEST_CONTRACT,
        },
    )


def _scope_task_seed(
    *,
    retailer_id: str,
    retailer_location_id: str | None,
    adapter_id: str,
    location_scope_key: str,
    zipcode: str,
    store_number: str,
    request_contract: dict[str, object],
    persist_request_contract: bool = True,
) -> TaskSeed:
    request_payload: dict[str, object] = {
        "keyword": "milk",
        "zipcode": zipcode,
        "store_number": store_number,
        "page": 1,
        "request_overrides": {},
    }
    if persist_request_contract:
        request_payload["_provider_request_contract"] = request_contract
    return TaskSeed(
        retailer_id=retailer_id,
        retailer_location_id=retailer_location_id,
        adapter_id=adapter_id,
        location_scope_key=location_scope_key,
        zipcode=zipcode,
        store_number=store_number,
        page_number=1,
        max_pages=1,
        stop_on_empty=True,
        stop_on_short_page=True,
        credits_per_success=1,
        request_payload=request_payload,
        request_fingerprint=canonical_checksum(request_payload),
        is_preflight=False,
        max_attempts=1,
    )


async def _create_scope_projection_fixture(
    database: DatabaseProbe,
    repository: PostgresCollectionRepository,
    *,
    pair_count: int,
    include_benchmark_failure: bool,
    canonical_count: int | None = None,
    unpaired_scopes: tuple[tuple[str, str], ...] = (),
    legacy_contracts: bool = False,
) -> _ScopeProjectionFixture:
    if legacy_contracts and include_benchmark_failure:
        raise ValueError("legacy scope fixture does not support a benchmark failure")
    canonical_count = pair_count if canonical_count is None else canonical_count
    if canonical_count < pair_count:
        raise ValueError("canonical_count cannot be smaller than pair_count")
    competitor_task_count = canonical_count + pair_count + len(unpaired_scopes)
    stable_key = f"postgres-scope-projection-{uuid4()}"
    config: dict[str, object] = {
        "id": stable_key,
        "name": "Postgres Scope Projection Test",
        "enabled": True,
        "benchmark_retailer": "walmart_us",
        "product_pack": {"id": "fresh_fluid_milk", "version": "1.0.0"},
        "query": {"keyword": "milk"},
        "retailers": [
            {
                "retailer_id": "walmart_us",
                "adapter_id": "fake_walmart",
                "enabled": True,
                "request_overrides": {},
            },
            {
                "retailer_id": "kroger_us",
                "adapter_id": "fake_kroger",
                "enabled": True,
                "request_overrides": {},
            },
        ],
        "budget": {
            "max_credits_per_run": competitor_task_count + 20,
            "max_credits_per_day": competitor_task_count * 2 + 100,
            "max_credits_per_month": competitor_task_count * 2 + 100,
        },
    }
    definition = await repository.publish_definition(config, canonical_checksum(config))
    resolution_id = str(uuid4())
    benchmark_location_id = str(uuid4()) if include_benchmark_failure else None
    location_rows: list[dict[str, object]] = []
    geography_rows: list[dict[str, object]] = []
    seeds: list[TaskSeed] = []
    audit_changes: list[dict[str, object]] = []
    if benchmark_location_id is not None:
        location_rows.append(
            {
                "location_id": benchmark_location_id,
                "retailer_id": "walmart_us",
                "provider": stable_key,
                "provider_location_id": "2400",
                "store_number": "2400",
                "store_name": "Benchmark Store",
                "zipcode": "90020",
                "city": "Los Angeles",
                "state": "CA",
                "latitude": 34.05,
                "longitude": -118.25,
                "eligible": True,
            }
        )
        geography_rows.append(
            {
                **location_rows[-1],
                "resolution_id": resolution_id,
                "role": "primary",
                "scope_key": "walmart:benchmark",
            }
        )
        seeds.append(
            _scope_task_seed(
                retailer_id="walmart_us",
                retailer_location_id=benchmark_location_id,
                adapter_id="fake_walmart",
                location_scope_key="walmart:benchmark",
                zipcode="90020",
                store_number="2400",
                request_contract=_SCOPE_WALMART_REQUEST_CONTRACT,
            )
        )
    for index in range(canonical_count):
        canonical_store = f"{1_000_000 + index:08d}"
        alias_store = canonical_store[1:]
        zipcode = f"{index % 100_000:05d}"
        canonical_location_id = str(uuid4())
        alias_location_id = str(uuid4())
        scoped_locations = [("canonical", canonical_store, canonical_location_id, True)]
        if index < pair_count:
            scoped_locations.append(("alias", alias_store, alias_location_id, False))
        for kind, store_number, location_id, eligible in scoped_locations:
            location = {
                "location_id": location_id,
                "retailer_id": "kroger_us",
                "provider": stable_key,
                "provider_location_id": f"{kind}-{store_number}",
                "store_number": store_number,
                "store_name": f"Kroger {kind.title()} {index}",
                "zipcode": zipcode,
                "city": "Projection City",
                "state": "OH",
                "latitude": 39.0 + index / 100_000,
                "longitude": -84.0 - index / 100_000,
                "eligible": eligible,
            }
            location_rows.append(location)
            geography_rows.append(
                {
                    **location,
                    "resolution_id": resolution_id,
                    "role": "competitor",
                    "scope_key": f"kroger:{kind}:{index}",
                }
            )
            seeds.append(
                _scope_task_seed(
                    retailer_id="kroger_us",
                    retailer_location_id=location_id,
                    adapter_id="fake_kroger",
                    location_scope_key=f"kroger:{kind}:{index}",
                    zipcode=zipcode,
                    store_number=store_number,
                    request_contract=_SCOPE_KROGER_REQUEST_CONTRACT,
                    persist_request_contract=not legacy_contracts,
                )
            )
        if index < pair_count:
            audit_changes.append(
                {
                    "id": alias_location_id,
                    "retailer_id": "kroger_us",
                    "store_number": alias_store,
                    "before_eligible": True,
                    "after_eligible": False,
                    "after_reason": "store_number_not_provider_safe",
                }
            )
    for unpaired_index, (store_number, zipcode) in enumerate(unpaired_scopes):
        location_id = str(uuid4())
        location = {
            "location_id": location_id,
            "retailer_id": "kroger_us",
            "provider": stable_key,
            "provider_location_id": f"gap-{store_number}",
            "store_number": store_number,
            "store_name": f"Kroger Audited Gap {unpaired_index}",
            "zipcode": zipcode,
            "city": "Projection City",
            "state": "OH",
            "latitude": 39.0,
            "longitude": -84.0,
            "eligible": False,
        }
        location_rows.append(location)
        geography_rows.append(
            {
                **location,
                "resolution_id": resolution_id,
                "role": "competitor",
                "scope_key": f"kroger:gap:{unpaired_index}",
            }
        )
        seeds.append(
            _scope_task_seed(
                retailer_id="kroger_us",
                retailer_location_id=location_id,
                adapter_id="fake_kroger",
                location_scope_key=f"kroger:gap:{unpaired_index}",
                zipcode=zipcode,
                store_number=store_number,
                request_contract=_SCOPE_KROGER_REQUEST_CONTRACT,
                persist_request_contract=not legacy_contracts,
            )
        )
        audit_changes.append(
            {
                "id": location_id,
                "retailer_id": "kroger_us",
                "store_number": store_number,
                "before_eligible": True,
                "after_eligible": False,
                "after_reason": "store_number_not_provider_safe",
            }
        )

    async with database.engine.begin() as connection:
        organization_id = str(
            (
                await connection.execute(
                    text(
                        "SELECT d.organization_id::text "
                        "FROM collection_definition_version v "
                        "JOIN collection_definition d ON d.id = v.definition_id "
                        "WHERE v.id::text = :version_id"
                    ),
                    {"version_id": definition.version_id},
                )
            ).scalar_one()
        )
        await connection.execute(
            text(
                "INSERT INTO collection_geography_resolution ("
                "id, organization_id, primary_retailer_id, country, request, checksum, "
                "status, counts) VALUES (CAST(:resolution_id AS uuid), "
                "CAST(:organization_id AS uuid), 'walmart_us', 'USA', "
                "'{\"fixture\":\"scope-projection\"}'::jsonb, :checksum, 'ready', "
                "CAST(:counts AS jsonb))"
            ),
            {
                "resolution_id": resolution_id,
                "organization_id": organization_id,
                "checksum": canonical_checksum(
                    {"fixture": stable_key, "location_count": len(location_rows)}
                ),
                "counts": json.dumps(
                    {
                        "primary": int(include_benchmark_failure),
                        "competitor": competitor_task_count,
                    }
                ),
            },
        )
        await connection.execute(
            text(
                "INSERT INTO retailer_location ("
                "id, retailer_id, provider, provider_location_id, store_number, store_name, "
                "raw_zipcode, zipcode, city, state, country, latitude, longitude, status, "
                "raw_row, collection_eligible) VALUES (CAST(:location_id AS uuid), "
                ":retailer_id, :provider, :provider_location_id, :store_number, :store_name, "
                ":zipcode, :zipcode, :city, :state, 'USA', :latitude, :longitude, 'active', "
                "'{}'::jsonb, :eligible)"
            ),
            location_rows,
        )
        await connection.execute(
            text(
                "INSERT INTO collection_geography_location ("
                "resolution_id, role, retailer_id, retailer_location_id, scope_key, "
                "store_number, zipcode, city, state, country, latitude, longitude, "
                "selection_reason) VALUES (CAST(:resolution_id AS uuid), :role, "
                ":retailer_id, CAST(:location_id AS uuid), :scope_key, :store_number, "
                ":zipcode, :city, :state, 'USA', :latitude, :longitude, "
                "'postgres_scope_projection_fixture')"
            ),
            geography_rows,
        )
        await connection.execute(
            text(
                "UPDATE collection_definition_version "
                "SET geography_resolution_id = CAST(:resolution_id AS uuid) "
                "WHERE id::text = :version_id"
            ),
            {"resolution_id": resolution_id, "version_id": definition.version_id},
        )
        source_audit_id = str(
            (
                await connection.execute(
                    text(
                        "INSERT INTO location_eligibility_reconciliation_run ("
                        "catalog_path, catalog_sha256, snapshot_sha256, reviewed_plan_sha256, "
                        "retailer_ids, requested_by, change_reason, status, scanned_rows, "
                        "changed_rows, eligible_before, eligible_after, enabled_rows, "
                        "disabled_rows, reason_counts_before, reason_counts_after, changes, "
                        "completed_at) VALUES ('config/retailer-catalog.json', :catalog, "
                        ":snapshot, :plan, ARRAY['kroger_us']::text[], "
                        "'postgres-scope-projection-test', 'canonical alias fixture', "
                        "'completed', :scanned, :changed, :eligible_before, :eligible_after, "
                        "0, :changed, '{}'::jsonb, "
                        "CAST(:reason_counts_after AS jsonb), "
                        "CAST(:changes AS jsonb), now()) RETURNING id::text"
                    ),
                    {
                        "catalog": canonical_checksum({"catalog": stable_key}),
                        "snapshot": canonical_checksum({"snapshot": stable_key}),
                        "plan": canonical_checksum({"plan": stable_key}),
                        "scanned": competitor_task_count,
                        "changed": pair_count + len(unpaired_scopes),
                        "eligible_before": competitor_task_count,
                        "eligible_after": canonical_count,
                        "reason_counts_after": json.dumps(
                            {"store_number_not_provider_safe": (pair_count + len(unpaired_scopes))},
                            sort_keys=True,
                        ),
                        "changes": json.dumps(audit_changes, sort_keys=True),
                    },
                )
            ).scalar_one()
        )

    estimates = [
        RetailerEstimate(
            "kroger_us", competitor_task_count, 1, 1, competitor_task_count, competitor_task_count
        )
    ]
    if include_benchmark_failure:
        estimates.insert(0, RetailerEstimate("walmart_us", 1, 1, 1, 1, 1))
    plan = CollectionPlan(
        estimate=CostEstimate(
            definition_id=definition.stable_key,
            retailers=tuple(estimates),
            estimated_total_pages=len(seeds),
            estimated_total_credits=len(seeds),
        ),
        initial_tasks=tuple(seeds),
    )
    base_run = await repository.create_run(definition, plan)
    async with database.engine.begin() as connection:
        if include_benchmark_failure:
            await connection.execute(
                text(
                    "WITH artifacts AS ("
                    "INSERT INTO dataset_artifact (collection_run_id, artifact_type, "
                    "storage_uri, content_type, row_count, byte_size, checksum, "
                    "schema_version, metadata) SELECT CAST(:run_id AS uuid), "
                    "'raw_provider_response', 's3://test/scope/' || t.id::text || '.json.gz', "
                    "'application/json', 1, 64, md5(t.id::text) || md5(t.id::text), "
                    "'1.0.0', jsonb_build_object('task_id', t.id::text, 'provider', 'test') "
                    "FROM collection_task t WHERE t.collection_run_id = CAST(:run_id AS uuid) "
                    "AND t.retailer_id = 'kroger_us' RETURNING id, metadata->>'task_id' AS task_id"
                    ") UPDATE collection_task t SET status = 'succeeded', completed_at = now(), "
                    "http_status = 200, result_count = 1, billable_credits = 1, "
                    "raw_artifact_id = artifacts.id FROM artifacts "
                    "WHERE t.id::text = artifacts.task_id"
                ),
                {"run_id": base_run.id},
            )
            await connection.execute(
                text(
                    "UPDATE collection_task SET status = 'failed', completed_at = now(), "
                    "http_status = 500, failure_class = 'lease_exhausted', "
                    "billable_credits = 0 WHERE collection_run_id = CAST(:run_id AS uuid) "
                    "AND retailer_id = 'walmart_us'"
                ),
                {"run_id": base_run.id},
            )
            await connection.execute(
                text(
                    "UPDATE collection_run SET status = 'completed_with_warnings', "
                    "actual_success_pages = :successes, actual_credits = :successes, "
                    "completed_at = now() WHERE id = CAST(:run_id AS uuid)"
                ),
                {"run_id": base_run.id, "successes": competitor_task_count},
            )
        else:
            await connection.execute(
                text(
                    "UPDATE collection_task SET status = 'cancelled', completed_at = now(), "
                    "failure_class = 'cancelled' "
                    "WHERE collection_run_id = CAST(:run_id AS uuid)"
                ),
                {"run_id": base_run.id},
            )
            await connection.execute(
                text(
                    "UPDATE collection_run SET status = 'cancelled', completed_at = now() "
                    "WHERE id = CAST(:run_id AS uuid)"
                ),
                {"run_id": base_run.id},
            )
        if legacy_contracts:
            await connection.execute(
                text(
                    "WITH called AS ("
                    "SELECT id, row_number() OVER (ORDER BY location_scope_key, id) "
                    "AS call_ordinal "
                    "FROM collection_task WHERE collection_run_id = CAST(:run_id AS uuid) "
                    "AND retailer_id = 'kroger_us' "
                    "AND location_scope_key LIKE 'kroger:canonical:%' ORDER BY location_scope_key "
                    "LIMIT 4), artifacts AS ("
                    "INSERT INTO dataset_artifact (collection_run_id, artifact_type, storage_uri, "
                    "content_type, row_count, byte_size, checksum, schema_version, metadata) "
                    "SELECT CAST(:run_id AS uuid), 'raw_provider_response', "
                    "'s3://test/scope-legacy/' || called.id::text || '.json.gz', "
                    "'application/json', 1, 64, md5(called.id::text) || md5(called.id::text), "
                    "'1.0.0', jsonb_build_object("
                    "'provider', 'metricscart', 'retailer_id', 'kroger_us', "
                    "'adapter_id', 'fake_kroger', 'task_id', called.id::text, "
                    "'request_method', 'GET', 'request_path', '/fake/kroger/search', "
                    "'request_parameter_names', jsonb_build_array("
                    "'keyword', 'page', 'store', 'zipcode'), "
                    "'http_status', CASE WHEN called.call_ordinal = 1 THEN 200 ELSE 404 END, "
                    "'body_checksum', md5('body-' || called.id::text) || "
                    "md5('body-' || called.id::text)) "
                    "FROM called RETURNING id, metadata->>'task_id' AS task_id, "
                    "(metadata->>'http_status')::integer AS http_status) "
                    "UPDATE collection_task task SET "
                    "status = CASE WHEN artifacts.http_status = 200 "
                    "THEN 'succeeded' ELSE 'failed' END, "
                    "completed_at = now(), attempt_count = 1, http_status = artifacts.http_status, "
                    "failure_class = CASE WHEN artifacts.http_status = 404 "
                    "THEN 'invalid_request' ELSE NULL END, billable_credits = 3, "
                    "result_count = CASE WHEN artifacts.http_status = 200 THEN 1 ELSE NULL END, "
                    "raw_artifact_id = artifacts.id FROM artifacts "
                    "WHERE task.id::text = artifacts.task_id"
                ),
                {"run_id": base_run.id},
            )
            await connection.execute(
                text(
                    "UPDATE collection_run SET status = 'completed_with_warnings', "
                    "actual_success_pages = 1, actual_credits = 12, completed_at = now() "
                    "WHERE id = CAST(:run_id AS uuid)"
                ),
                {"run_id": base_run.id},
            )
        task_rows = list(
            (
                await connection.execute(
                    text(
                        "SELECT id::text, retailer_id, location_scope_key "
                        "FROM collection_task "
                        "WHERE collection_run_id = CAST(:run_id AS uuid)"
                    ),
                    {"run_id": base_run.id},
                )
            )
            .mappings()
            .all()
        )
    benchmark_task_id = next(
        (str(row["id"]) for row in task_rows if row["retailer_id"] == "walmart_us"),
        None,
    )
    canonical_task_ids = tuple(
        str(row["id"])
        for row in sorted(task_rows, key=lambda row: str(row["location_scope_key"]))
        if str(row["location_scope_key"]).startswith("kroger:canonical:")
    )
    alias_task_ids = tuple(
        str(row["id"])
        for row in sorted(task_rows, key=lambda row: str(row["location_scope_key"]))
        if str(row["location_scope_key"]).startswith("kroger:alias:")
    )
    gap_task_ids = tuple(
        str(row["id"])
        for row in sorted(task_rows, key=lambda row: str(row["location_scope_key"]))
        if str(row["location_scope_key"]).startswith("kroger:gap:")
    )
    return _ScopeProjectionFixture(
        definition=definition,
        base_run=base_run,
        source_audit_id=source_audit_id,
        benchmark_task_id=benchmark_task_id,
        canonical_task_ids=canonical_task_ids,
        alias_task_ids=alias_task_ids,
        gap_task_ids=gap_task_ids,
    )


async def _create_cross_run_scope_task(
    database: DatabaseProbe,
    repository: PostgresCollectionRepository,
    definition: DefinitionRecord,
) -> str:
    seed = _scope_task_seed(
        retailer_id="kroger_us",
        retailer_location_id=None,
        adapter_id="fake_kroger",
        location_scope_key=f"cross-run:{uuid4()}",
        zipcode="43230",
        store_number="09999999",
        request_contract=_SCOPE_KROGER_REQUEST_CONTRACT,
    )
    run = await repository.create_run(
        definition,
        CollectionPlan(
            estimate=CostEstimate(
                definition_id=definition.stable_key,
                retailers=(RetailerEstimate("kroger_us", 1, 1, 1, 1, 1),),
                estimated_total_pages=1,
                estimated_total_credits=1,
            ),
            initial_tasks=(seed,),
        ),
    )
    async with database.engine.begin() as connection:
        task_id = str(
            (
                await connection.execute(
                    text(
                        "UPDATE collection_task SET status = 'cancelled', completed_at = now(), "
                        "failure_class = 'cancelled' "
                        "WHERE collection_run_id = CAST(:run_id AS uuid) "
                        "RETURNING id::text"
                    ),
                    {"run_id": run.id},
                )
            ).scalar_one()
        )
        await connection.execute(
            text(
                "UPDATE collection_run SET status = 'cancelled', completed_at = now() "
                "WHERE id = CAST(:run_id AS uuid)"
            ),
            {"run_id": run.id},
        )
    return task_id


async def _clone_projection_header(
    connection: AsyncConnection,
    source_projection_id: str,
    *,
    organization_id: str,
    retailer_id: str,
) -> str:
    return str(
        (
            await connection.execute(
                text(
                    "INSERT INTO collection_scope_projection ("
                    "organization_id, base_collection_run_id, retailer_id, projection_kind, "
                    "policy_version, base_snapshot_checksum, source_audit_id, "
                    "source_evidence_checksum, raw_task_count, retained_task_count, "
                    "excluded_task_count, raw_location_count, retained_location_count, "
                    "excluded_location_count, raw_task_retention_ratio, "
                    "governed_coverage_ratio, minimum_scoreable_coverage, "
                    "scorecard_disposition, projection_checksum, review_reason, reviewed_by, "
                    "manifest) SELECT CAST(:organization_id AS uuid), "
                    "base_collection_run_id, :retailer_id, projection_kind, policy_version, "
                    "base_snapshot_checksum, source_audit_id, source_evidence_checksum, "
                    "raw_task_count, retained_task_count, excluded_task_count, "
                    "raw_location_count, retained_location_count, excluded_location_count, "
                    "raw_task_retention_ratio, governed_coverage_ratio, "
                    "minimum_scoreable_coverage, scorecard_disposition, :checksum, "
                    "'direct trigger fixture', 'postgres-scope-projection-test', manifest "
                    "FROM collection_scope_projection WHERE id::text = :projection_id "
                    "RETURNING id::text"
                ),
                {
                    "organization_id": organization_id,
                    "retailer_id": retailer_id,
                    "checksum": canonical_checksum({"projection_clone": str(uuid4())}),
                    "projection_id": source_projection_id,
                },
            )
        ).scalar_one()
    )


def _scope_projection_item_documents(
    preview: ScopeProjectionPreview,
) -> list[dict[str, object]]:
    return [
        {
            "source_task_id": item.source_task_id,
            "canonical_request_key": item.canonical_request_key,
            "disposition": item.disposition,
            "reason": item.reason,
            "mapped_retained_task_id": item.mapped_retained_task_id,
            "source_snapshot": item.source_snapshot,
        }
        for item in preview.items
    ]


async def _insert_audited_projection_preview(
    connection: AsyncConnection,
    preview: ScopeProjectionPreview,
    *,
    organization_id: str,
    manifest: dict[str, object] | None = None,
    header_overrides: dict[str, object] | None = None,
    items: list[dict[str, object]] | None = None,
    projection_checksum: str | None = None,
) -> str:
    manifest_document = json.loads(json.dumps(preview.manifest)) if manifest is None else manifest
    header: dict[str, object] = {
        "organization_id": organization_id,
        "base_collection_run_id": preview.base_collection_run_id,
        "retailer_id": preview.retailer_id,
        "projection_kind": preview.projection_kind,
        "policy_version": preview.policy_version,
        "base_snapshot_checksum": preview.base_snapshot_checksum,
        "source_audit_id": preview.source_audit_id,
        "source_evidence_checksum": preview.source_evidence_checksum,
        "raw_task_count": preview.raw_task_count,
        "retained_task_count": preview.retained_task_count,
        "excluded_task_count": preview.excluded_task_count,
        "raw_location_count": preview.raw_location_count,
        "retained_location_count": preview.retained_location_count,
        "excluded_location_count": preview.excluded_location_count,
        "denominator_gap_location_count": preview.denominator_gap_location_count,
        "raw_task_retention_ratio": preview.raw_task_retention_ratio,
        "governed_coverage_ratio": preview.governed_coverage_ratio,
        "minimum_scoreable_coverage": preview.minimum_scoreable_coverage,
        "scorecard_disposition": preview.scorecard_disposition,
        "projection_checksum": (
            projection_checksum
            if projection_checksum is not None
            else canonical_checksum(manifest_document)
        ),
        "manifest": json.dumps(manifest_document, ensure_ascii=False, sort_keys=True),
    }
    header.update(header_overrides or {})
    projection_id = str(
        (
            await connection.execute(
                text(
                    "INSERT INTO collection_scope_projection ("
                    "organization_id, base_collection_run_id, retailer_id, projection_kind, "
                    "policy_version, base_snapshot_checksum, source_audit_id, "
                    "source_evidence_checksum, raw_task_count, retained_task_count, "
                    "excluded_task_count, raw_location_count, retained_location_count, "
                    "excluded_location_count, denominator_gap_location_count, "
                    "raw_task_retention_ratio, governed_coverage_ratio, "
                    "minimum_scoreable_coverage, scorecard_disposition, projection_checksum, "
                    "review_reason, reviewed_by, manifest) VALUES ("
                    "CAST(:organization_id AS uuid), CAST(:base_collection_run_id AS uuid), "
                    ":retailer_id, :projection_kind, :policy_version, :base_snapshot_checksum, "
                    "CAST(:source_audit_id AS uuid), :source_evidence_checksum, "
                    ":raw_task_count, :retained_task_count, :excluded_task_count, "
                    ":raw_location_count, :retained_location_count, :excluded_location_count, "
                    ":denominator_gap_location_count, :raw_task_retention_ratio, "
                    ":governed_coverage_ratio, :minimum_scoreable_coverage, "
                    ":scorecard_disposition, :projection_checksum, "
                    "'direct audited trust-boundary test', "
                    "'postgres-scope-projection-test', CAST(:manifest AS jsonb)) "
                    "RETURNING id::text"
                ),
                header,
            )
        ).scalar_one()
    )
    item_documents = _scope_projection_item_documents(preview) if items is None else items
    await connection.execute(
        text(
            "INSERT INTO collection_scope_projection_task ("
            "scope_projection_id, source_task_id, ordinal, canonical_request_key, "
            "disposition, reason, mapped_retained_task_id, source_snapshot) VALUES ("
            "CAST(:scope_projection_id AS uuid), CAST(:source_task_id AS uuid), :ordinal, "
            ":canonical_request_key, :disposition, :reason, "
            "CAST(:mapped_retained_task_id AS uuid), CAST(:source_snapshot AS jsonb))"
        ),
        [
            {
                **item,
                "scope_projection_id": projection_id,
                "ordinal": ordinal,
                "source_snapshot": json.dumps(
                    item["source_snapshot"], ensure_ascii=False, sort_keys=True
                ),
            }
            for ordinal, item in enumerate(item_documents)
        ],
    )
    return projection_id


async def _complete_scope_recovery_fixture(database: DatabaseProbe, run_id: str) -> str:
    async with database.engine.begin() as connection:
        task_id = str(
            (
                await connection.execute(
                    text(
                        "WITH artifact AS ("
                        "INSERT INTO dataset_artifact (collection_run_id, artifact_type, "
                        "storage_uri, content_type, row_count, byte_size, checksum, "
                        "schema_version, metadata) SELECT CAST(:run_id AS uuid), "
                        "'raw_provider_response', 's3://test/scope-recovery/' || t.id::text || "
                        "'.json.gz', 'application/json', 1, 64, "
                        "md5(t.id::text) || md5(t.id::text), '1.0.0', "
                        "jsonb_build_object('task_id', t.id::text, 'provider', 'test') "
                        "FROM collection_task t "
                        "WHERE t.collection_run_id = CAST(:run_id AS uuid) "
                        "RETURNING id, metadata->>'task_id' AS task_id"
                        ") UPDATE collection_task t SET status = 'succeeded', "
                        "completed_at = now(), http_status = 200, result_count = 1, "
                        "billable_credits = 1, raw_artifact_id = artifact.id FROM artifact "
                        "WHERE t.id::text = artifact.task_id RETURNING t.id::text"
                    ),
                    {"run_id": run_id},
                )
            ).scalar_one()
        )
        await connection.execute(
            text(
                "UPDATE collection_run SET status = 'succeeded', actual_success_pages = 1, "
                "actual_credits = 1, completed_at = now() "
                "WHERE id = CAST(:run_id AS uuid)"
            ),
            {"run_id": run_id},
        )
    return task_id


async def _projection_materialization_counts(
    database: DatabaseProbe, base_run_id: str
) -> dict[str, int]:
    async with database.engine.connect() as connection:
        row = (
            (
                await connection.execute(
                    text(
                        "WITH inputs AS (SELECT id FROM analysis_input_set "
                        "WHERE collection_run_id = CAST(:run_id AS uuid) "
                        "AND source_kind = 'live_collection_composite') SELECT "
                        "(SELECT count(*) FROM inputs) AS input_count, "
                        "(SELECT count(*) FROM analysis_input_task_lineage "
                        "WHERE input_set_id IN (SELECT id FROM inputs)) AS lineage_count, "
                        "(SELECT count(*) FROM analysis_input_artifact "
                        "WHERE input_set_id IN (SELECT id FROM inputs)) AS artifact_count, "
                        "(SELECT count(*) FROM analysis_input_scope_projection "
                        "WHERE input_set_id IN (SELECT id FROM inputs)) AS projection_count, "
                        "(SELECT count(*) FROM analysis_run "
                        "WHERE input_set_id IN (SELECT id FROM inputs)) AS analysis_count"
                    ),
                    {"run_id": base_run_id},
                )
            )
            .mappings()
            .one()
        )
    return {key: int(value) for key, value in row.items()}


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
    await _ensure_concurrency_geography(
        database,
        definition,
        request_index=request_index,
        zipcode=zipcode,
        store_number=store_number,
    )
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


async def _ensure_concurrency_geography(
    database: DatabaseProbe,
    definition: DefinitionRecord,
    *,
    request_index: int,
    zipcode: str,
    store_number: str,
) -> None:
    """Give concurrency fixtures the immutable geography required by composites."""

    async with database.engine.begin() as connection:
        definition_row = (
            (
                await connection.execute(
                    text(
                        """
                        SELECT d.organization_id::text,
                               v.geography_resolution_id::text
                        FROM collection_definition_version v
                        JOIN collection_definition d ON d.id = v.definition_id
                        WHERE v.id::text = :version_id
                        FOR UPDATE OF v
                        """
                    ),
                    {"version_id": definition.version_id},
                )
            )
            .mappings()
            .one()
        )
        resolution_id = definition_row["geography_resolution_id"]
        if resolution_id is None:
            resolution_id = str(uuid4())
            await connection.execute(
                text(
                    """
                    INSERT INTO collection_geography_resolution (
                      id, organization_id, primary_retailer_id, country,
                      request, checksum, status, counts
                    ) VALUES (
                      CAST(:resolution_id AS uuid), CAST(:organization_id AS uuid),
                      'walmart_us', 'USA', CAST(:request AS jsonb), :checksum,
                      'ready', CAST(:counts AS jsonb)
                    )
                    """
                ),
                {
                    "resolution_id": resolution_id,
                    "organization_id": str(definition_row["organization_id"]),
                    "request": '{"fixture":"postgres-composite-concurrency"}',
                    "counts": '{"primary":0,"competitor":0}',
                    "checksum": canonical_checksum(
                        {
                            "fixture": "postgres-composite-concurrency",
                            "definition_version_id": definition.version_id,
                        }
                    ),
                },
            )
            await connection.execute(
                text(
                    "UPDATE collection_definition_version "
                    "SET geography_resolution_id = CAST(:resolution_id AS uuid) "
                    "WHERE id::text = :version_id"
                ),
                {
                    "resolution_id": resolution_id,
                    "version_id": definition.version_id,
                },
            )
        await connection.execute(
            text(
                """
                INSERT INTO collection_geography_location (
                  resolution_id, role, retailer_id, retailer_location_id,
                  scope_key, store_number, zipcode, city, state, country,
                  latitude, longitude, selection_reason
                ) VALUES (
                  CAST(:resolution_id AS uuid), 'primary', 'walmart_us', NULL,
                  :scope_key, :store_number, :zipcode, 'Fixture City', 'CA', 'USA',
                  :latitude, :longitude, 'postgres_test_fixture'
                )
                ON CONFLICT (resolution_id, retailer_id, scope_key) DO NOTHING
                """
            ),
            {
                "resolution_id": str(resolution_id),
                "scope_key": f"location:{request_index}",
                "store_number": store_number,
                "zipcode": zipcode,
                "latitude": 34.0 + request_index / 1000,
                "longitude": -118.0 - request_index / 1000,
            },
        )


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
