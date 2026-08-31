from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection

from rci_collections.composite import (
    MATERIALIZATION_WRITE_BATCH_SIZE,
    PostgresCompositeEvidenceRepository,
    RecoveryLaunchRecord,
    RecoveryPlanRecord,
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
async def test_postgres_scope_projection_history_refuses_migration_downgrade() -> None:
    database_url = os.environ["RCI_TEST_DATABASE_URL"]
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
    await composite_repository.approve_scope_projection(
        fixture.base_run.id,
        retailer_id="kroger_us",
        projection_kind="canonical_alias_collapse",
        projection_checksum=preview.projection_checksum,
        base_snapshot_checksum=preview.base_snapshot_checksum,
        review_reason="prove immutable history blocks downgrade",
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
            "0052_recovery_continuations",
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode != 0
    assert "cannot downgrade 0053 while immutable collection scope projections exist" in (
        completed.stdout + completed.stderr
    )
    verification = DatabaseProbe(database_url)
    try:
        async with verification.engine.connect() as connection:
            assert (
                await connection.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar_one() == "0053_scope_projections"
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
) -> TaskSeed:
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
        request_payload={
            "keyword": "milk",
            "zipcode": zipcode,
            "store_number": store_number,
            "page": 1,
            "request_overrides": {},
            "_provider_request_contract": request_contract,
        },
        request_fingerprint=canonical_checksum(
            {
                "retailer_id": retailer_id,
                "location_scope_key": location_scope_key,
                "store_number": store_number,
            }
        ),
        is_preflight=False,
        max_attempts=1,
    )


async def _create_scope_projection_fixture(
    database: DatabaseProbe,
    repository: PostgresCollectionRepository,
    *,
    pair_count: int,
    include_benchmark_failure: bool,
) -> _ScopeProjectionFixture:
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
            "max_credits_per_run": pair_count * 2 + 20,
            "max_credits_per_day": pair_count * 4 + 100,
            "max_credits_per_month": pair_count * 4 + 100,
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
    for index in range(pair_count):
        canonical_store = f"{1_000_000 + index:08d}"
        alias_store = canonical_store[1:]
        zipcode = f"{index % 100_000:05d}"
        canonical_location_id = str(uuid4())
        alias_location_id = str(uuid4())
        for kind, store_number, location_id, eligible in (
            ("canonical", canonical_store, canonical_location_id, True),
            ("alias", alias_store, alias_location_id, False),
        ):
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
                )
            )
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
                        "competitor": pair_count * 2,
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
                        "scanned": pair_count * 2,
                        "changed": pair_count,
                        "eligible_before": pair_count * 2,
                        "eligible_after": pair_count,
                        "reason_counts_after": json.dumps(
                            {"store_number_not_provider_safe": pair_count},
                            sort_keys=True,
                        ),
                        "changes": json.dumps(audit_changes, sort_keys=True),
                    },
                )
            ).scalar_one()
        )

    estimates = [
        RetailerEstimate("kroger_us", pair_count * 2, 1, 1, pair_count * 2, pair_count * 2)
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
                {"run_id": base_run.id, "successes": pair_count * 2},
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
    return _ScopeProjectionFixture(
        definition=definition,
        base_run=base_run,
        source_audit_id=source_audit_id,
        benchmark_task_id=benchmark_task_id,
        canonical_task_ids=canonical_task_ids,
        alias_task_ids=alias_task_ids,
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
