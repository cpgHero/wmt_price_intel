from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text

from rci_collections.models import CollectionPlan, CostEstimate
from rci_collections.planner import canonical_checksum
from rci_collections.repository import PostgresCollectionRepository
from rci_db import DatabaseProbe
from rci_results import (
    AnalysisResultService,
    AnalysisResultValidator,
    InMemoryReportObjectStore,
    PostgresResultsRepository,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


@pytest.mark.skipif(
    not os.getenv("RCI_TEST_DATABASE_URL"),
    reason="set RCI_TEST_DATABASE_URL to run Postgres result persistence integration",
)
async def test_postgres_result_and_report_persistence_is_idempotent_and_immutable() -> None:
    database = DatabaseProbe(os.environ["RCI_TEST_DATABASE_URL"])
    collection_repository = PostgresCollectionRepository(database.engine)
    definition_id = f"results-test-{uuid4()}"
    config: dict[str, object] = {
        "id": definition_id,
        "name": "Results persistence integration",
        "enabled": True,
    }
    definition = await collection_repository.publish_definition(config, canonical_checksum(config))
    run = await collection_repository.create_run(
        definition,
        CollectionPlan(
            estimate=CostEstimate(
                definition_id=definition_id,
                retailers=(),
                estimated_total_pages=0,
                estimated_total_credits=0,
            ),
            initial_tasks=(),
        ),
    )
    document = json.loads(
        (REPOSITORY_ROOT / "examples/analysis-result.strawberries.json").read_text()
    )
    analysis_id = f"analysis-{uuid4()}"
    document["analysis_id"] = analysis_id
    document["collection_run_id"] = run.id
    service = AnalysisResultService(
        PostgresResultsRepository(database.engine),
        AnalysisResultValidator(REPOSITORY_ROOT),
        InMemoryReportObjectStore(),
    )
    try:
        first = await service.publish(document)
        assert (await service.publish(document)).id == first.id
        changed = copy.deepcopy(document)
        changed["comparisons"][0]["matches"] = 1
        with pytest.raises(ValueError, match="immutable"):
            await service.publish(changed)

        artifact = await service.generate_artifact(analysis_id, "html")
        assert (await service.generate_artifact(analysis_id, "html")).id == artifact.id
        assert artifact.renderer_version == "2.1.0"
        assert (await service.get(analysis_id)).result == document
        assert [row.id for row in await service.list_artifacts(analysis_id)] == [artifact.id]
    finally:
        async with database.engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM audit_event WHERE entity_id = :analysis_id"),
                {"analysis_id": analysis_id},
            )
            await connection.execute(
                text(
                    "DELETE FROM report_artifact WHERE analysis_run_id IN "
                    "(SELECT id FROM analysis_run WHERE collection_run_id::text = :run_id)"
                ),
                {"run_id": run.id},
            )
            await connection.execute(
                text(
                    "DELETE FROM analysis_result WHERE analysis_run_id IN "
                    "(SELECT id FROM analysis_run WHERE collection_run_id::text = :run_id)"
                ),
                {"run_id": run.id},
            )
            await connection.execute(
                text("DELETE FROM analysis_run WHERE collection_run_id::text = :run_id"),
                {"run_id": run.id},
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
