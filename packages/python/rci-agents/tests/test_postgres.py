from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from rci_agents import AgentTaskSpec, PostgresAgentTaskRepository, PromptTemplateLoader
from rci_agents.governance import checksum
from sqlalchemy import text

from rci_collections.models import CollectionPlan, CostEstimate
from rci_collections.planner import canonical_checksum
from rci_collections.repository import PostgresCollectionRepository
from rci_db import DatabaseProbe

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


@pytest.mark.skipif(
    not os.getenv("RCI_TEST_DATABASE_URL"),
    reason="set RCI_TEST_DATABASE_URL to run governed AI Postgres integration",
)
async def test_agent_task_reservation_is_replica_safe_and_idempotent() -> None:
    database = DatabaseProbe(os.environ["RCI_TEST_DATABASE_URL"])
    collections = PostgresCollectionRepository(database.engine)
    repository = PostgresAgentTaskRepository(database.engine)
    definition_key = f"agent-test-{uuid4()}"
    config: dict[str, object] = {"id": definition_key, "name": "Agent audit", "enabled": True}
    definition = await collections.publish_definition(config, canonical_checksum(config))
    run = await collections.create_run(
        definition,
        CollectionPlan(
            estimate=CostEstimate(
                definition_id=definition_key,
                retailers=(),
                estimated_total_pages=0,
                estimated_total_credits=0,
            ),
            initial_tasks=(),
        ),
    )
    async with database.engine.begin() as connection:
        analysis_run_id = str(
            (
                await connection.execute(
                    text(
                        """
                        INSERT INTO analysis_run (
                          collection_run_id, product_pack_id, product_pack_version,
                          status, code_version
                        ) VALUES (
                          CAST(:run_id AS uuid), 'fresh_ground_beef', '1.0.0',
                          'running', 'test'
                        ) RETURNING id::text
                        """
                    ),
                    {"run_id": run.id},
                )
            ).scalar_one()
        )
    prompt = PromptTemplateLoader(REPOSITORY_ROOT).load("governed_insight")
    payload = {"analysis_id": definition_key, "metrics": []}
    spec = AgentTaskSpec(
        analysis_run_id=analysis_run_id,
        analysis_id=definition_key,
        role="insight",
        prompt=prompt,
        provider="fake",
        model_id="fake-model",
        input_checksum=checksum(payload),
        input_document=payload,
        max_attempts=2,
    )
    try:
        claims = await asyncio.gather(
            repository.reserve(spec, worker_id="replica-a", lease_seconds=30),
            repository.reserve(spec, worker_id="replica-b", lease_seconds=30),
        )
        assert sum(claim.acquired for claim in claims) == 1
        assert len({claim.task_id for claim in claims}) == 1
        task_id = claims[0].task_id
        output = json.loads(
            (REPOSITORY_ROOT / "examples/agent-output.ground-beef-insight.json").read_text()
        )
        output["task_id"] = task_id
        owner_index = 0 if claims[0].acquired else 1
        owner_worker = ("replica-a", "replica-b")[owner_index]
        stale_worker = ("replica-b", "replica-a")[owner_index]
        with pytest.raises(RuntimeError, match="lease expired"):
            await repository.succeed(task_id, stale_worker, output)
        await repository.succeed(task_id, owner_worker, output)

        cached = await repository.reserve(spec, worker_id="replica-c", lease_seconds=30)
        assert cached.acquired is False
        assert cached.cached_output is not None
        assert cached.cached_output["task_id"] == task_id
    finally:
        async with database.engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM analysis_run WHERE id::text = :analysis_run_id"),
                {"analysis_run_id": analysis_run_id},
            )
            await connection.execute(
                text("DELETE FROM collection_run WHERE id::text = :run_id"),
                {"run_id": run.id},
            )
            await connection.execute(
                text(
                    "DELETE FROM collection_definition_version "
                    "WHERE definition_id::text = :definition_id"
                ),
                {"definition_id": definition.id},
            )
            await connection.execute(
                text("DELETE FROM collection_definition WHERE id::text = :definition_id"),
                {"definition_id": definition.id},
            )
        await database.dispose()
