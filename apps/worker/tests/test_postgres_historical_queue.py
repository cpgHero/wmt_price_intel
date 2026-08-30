from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text

from rci_analytics import (
    HistoricalImportService,
    HistoricalInputManifestLoader,
    InMemoryHistoricalObjectStore,
    PostgresAnalysisInputRepository,
    prepare_historical_import,
)
from rci_db import DatabaseProbe
from rci_worker.analysis import PostgresAnalysisQueue

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.skipif(
    not os.getenv("RCI_TEST_DATABASE_URL"),
    reason="set RCI_TEST_DATABASE_URL to run Postgres historical-input integration",
)
async def test_historical_import_reaches_generic_analysis_queue_idempotently(
    tmp_path: Path,
) -> None:
    database = DatabaseProbe(os.environ["RCI_TEST_DATABASE_URL"])
    stable_key = f"historical-postgres-{uuid4()}"
    source_name = "historical.csv"
    source = tmp_path / source_name
    body = (
        b"Retailer,Retailer Store Id,Zipcode,Retailer Product Id,Product Name,Price\n"
        b"walmart.com,0007,00617,0000000000123,Fresh Strawberries 1 lb,2.98\n"
    )
    source.write_bytes(body)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "stable_key": stable_key,
                "name": "Postgres historical queue test",
                "captured_at": "2026-08-07T05:00:00Z",
                "product_pack": {"id": "fresh_strawberries", "version": "1.0.0"},
                "analysis_config": {
                    "id": stable_key,
                    "name": "Postgres historical queue test",
                    "version": "1.0.0",
                    "benchmark_retailer": "walmart_us",
                    "product_pack": {
                        "id": "fresh_strawberries",
                        "version": "1.0.0",
                    },
                    "retailers": [{"retailer_id": "walmart_us", "enabled": True}],
                    "analysis": {"comparison_profiles": ["strict"]},
                    "delivery": {},
                },
                "artifacts": [
                    {
                        "ordinal": 0,
                        "retailer_id": "walmart_us",
                        "adapter_id": "historical_metricscart_search_monitor_csv",
                        "source_name": source_name,
                        "source_format": "metricscart_search_monitor_csv",
                        "content_type": "text/csv",
                        "expected_sha256": hashlib.sha256(body).hexdigest(),
                        "expected_rows": 1,
                    }
                ],
                "metadata": {"source_rows_total": 1},
            }
        ),
        encoding="utf-8",
    )
    prepared = prepare_historical_import(
        HistoricalInputManifestLoader(REPOSITORY_ROOT).load(manifest_path), tmp_path
    )
    repository = PostgresAnalysisInputRepository(database.engine)
    service = HistoricalImportService(
        InMemoryHistoricalObjectStore(), repository, code_version="test"
    )
    run_id: str | None = None
    try:
        first = await service.import_prepared(prepared)
        run_id = first.collection_run_id
        second = await service.import_prepared(prepared)
        assert first.created is True
        assert second.created is False
        assert second.input_set_id == first.input_set_id
        assert second.analysis_run_id == first.analysis_run_id

        jobs = await PostgresAnalysisQueue(
            database.engine,
            code_version="test",
            historical_replay_enabled=True,
        ).claim("historical-test-worker", limit=100, lease_seconds=30)
        job = next(value for value in jobs if value.id == first.analysis_run_id)
        assert job.input_set_id == first.input_set_id
        assert job.source_kind == "historical_import"
        assert job.collection_run_id == first.collection_run_id

        async with database.engine.connect() as connection:
            artifact_rows = int(
                (
                    await connection.execute(
                        text(
                            "SELECT count(*) FROM analysis_input_artifact "
                            "WHERE input_set_id::text = :input_set_id"
                        ),
                        {"input_set_id": first.input_set_id},
                    )
                ).scalar_one()
            )
        assert artifact_rows == 1

        ready_manifest = f"ready-{uuid4()}"
        blocked_manifest = f"blocked-{uuid4()}"
        async with database.engine.begin() as connection:
            ready_input_set_id = str(
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO analysis_input_set (
                              organization_id, source_kind, stable_key, collection_run_id,
                              product_pack_id, product_pack_version, analysis_config,
                              manifest, manifest_checksum, total_rows, status, completed_at,
                              assembly_generation, assembly_policy_version, trust_state
                            )
                            SELECT organization_id, 'live_collection_composite',
                                   :stable_key, collection_run_id, product_pack_id,
                                   product_pack_version, analysis_config,
                                   jsonb_build_object(
                                     'test', CAST(:manifest_checksum AS text)
                                   ),
                                   :manifest_checksum, total_rows, 'ready', now(), 2,
                                   'composite-evidence-v1', 'ready'
                            FROM analysis_input_set WHERE id::text = :source_input_set_id
                            RETURNING id::text
                            """
                        ),
                        {
                            "stable_key": ready_manifest,
                            "manifest_checksum": ready_manifest,
                            "source_input_set_id": first.input_set_id,
                        },
                    )
                ).scalar_one()
            )
            blocked_input_set_id = str(
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO analysis_input_set (
                              organization_id, source_kind, stable_key, collection_run_id,
                              product_pack_id, product_pack_version, analysis_config,
                              manifest, manifest_checksum, total_rows, status, completed_at,
                              assembly_generation, assembly_policy_version, trust_state
                            )
                            SELECT organization_id, 'live_collection_composite',
                                   :stable_key, collection_run_id, product_pack_id,
                                   product_pack_version, analysis_config,
                                   jsonb_build_object(
                                     'test', CAST(:manifest_checksum AS text)
                                   ),
                                   :manifest_checksum, 0, 'failed', now(), 3,
                                   'composite-evidence-v1', 'blocked'
                            FROM analysis_input_set WHERE id::text = :source_input_set_id
                            RETURNING id::text
                            """
                        ),
                        {
                            "stable_key": blocked_manifest,
                            "manifest_checksum": blocked_manifest,
                            "source_input_set_id": first.input_set_id,
                        },
                    )
                ).scalar_one()
            )

        await repository.materialize_live(code_version="test", max_attempts=3)
        async with database.engine.connect() as connection:
            composite_runs = list(
                (
                    await connection.execute(
                        text(
                            "SELECT input_set_id::text FROM analysis_run "
                            "WHERE input_set_id::text IN (:ready_id, :blocked_id)"
                        ),
                        {
                            "ready_id": ready_input_set_id,
                            "blocked_id": blocked_input_set_id,
                        },
                    )
                ).scalars()
            )
        assert composite_runs == [ready_input_set_id]

        composite_jobs = await PostgresAnalysisQueue(
            database.engine,
            code_version="test",
            historical_replay_enabled=True,
        ).claim("composite-test-worker", limit=100, lease_seconds=30)
        composite_job = next(
            value for value in composite_jobs if value.input_set_id == ready_input_set_id
        )
        assert composite_job.source_kind == "live_collection_composite"
        assert all(value.input_set_id != blocked_input_set_id for value in composite_jobs)
    finally:
        if run_id is not None:
            async with database.engine.begin() as connection:
                await connection.execute(
                    text("DELETE FROM collection_run WHERE id::text = :run_id"),
                    {"run_id": run_id},
                )
                await connection.execute(
                    text(
                        "DELETE FROM collection_definition "
                        "WHERE organization_id::text = :organization_id "
                        "AND stable_key = :stable_key"
                    ),
                    {
                        "organization_id": "00000000-0000-0000-0000-000000000001",
                        "stable_key": f"historical:{stable_key}",
                    },
                )
        await database.dispose()
