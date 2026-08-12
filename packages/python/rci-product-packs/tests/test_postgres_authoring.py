from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest

from rci_db import DatabaseProbe
from rci_product_packs import (
    PostgresProductPackAuthoringRepository,
    PostgresProductPackCatalog,
    ProductPackDraftConflictError,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def _bundle(pack_id: str) -> tuple[dict[str, object], dict[str, object]]:
    config = json.loads((REPOSITORY_ROOT / "product-packs/fresh_ground_beef.json").read_text())
    blueprint = json.loads(
        (REPOSITORY_ROOT / "report-blueprints/fresh_ground_beef_leadership.json").read_text()
    )
    blueprint_id = f"{pack_id}_leadership"
    config.update({"id": pack_id, "name": "Test Product Pack", "version": "1.0.0"})
    config["reporting"]["report_blueprint"] = {
        "id": blueprint_id,
        "version": "1.0.0",
    }
    blueprint.update(
        {
            "id": blueprint_id,
            "version": "1.0.0",
            "product_pack": {"id": pack_id, "version": "1.0.0"},
        }
    )
    return deepcopy(config), deepcopy(blueprint)


@pytest.mark.skipif(
    not os.getenv("RCI_TEST_DATABASE_URL"),
    reason="set RCI_TEST_DATABASE_URL to run Product Pack authoring integration",
)
async def test_postgres_authoring_queue_cancellation_and_immutable_publication() -> None:
    database = DatabaseProbe(os.environ["RCI_TEST_DATABASE_URL"])
    repository = PostgresProductPackAuthoringRepository(database.engine)
    catalog = PostgresProductPackCatalog(database.engine)
    pack_id = f"test_product_pack_{uuid4().hex}"
    config, blueprint = _bundle(pack_id)
    try:
        draft = await repository.create_draft(
            product_pack_id=pack_id,
            proposed_version="1.0.0",
            config=config,
            report_blueprint=blueprint,
            actor="integration-test",
        )
        superseded_config, superseded_blueprint = _bundle(f"{pack_id}_superseded")
        superseded = await repository.create_draft(
            product_pack_id=f"{pack_id}_superseded",
            proposed_version="1.0.0",
            config=superseded_config,
            report_blueprint=superseded_blueprint,
            actor="integration-test",
        )
        abandoned = await repository.abandon_draft(
            superseded.id,
            actor="integration-test",
            reason="regenerated from corrected evidence",
        )
        assert abandoned.status == "abandoned"
        first = await repository.request_validation(
            draft.id,
            suite="quick",
            engine_version="integration-test",
        )
        duplicate = await repository.request_validation(
            draft.id,
            suite="quick",
            engine_version="integration-test",
        )
        assert duplicate.id == first.id

        claimed = await repository.claim_validations(
            worker_id="product-pack-worker-a",
            limit=1,
            lease_seconds=60,
        )
        assert [run.id for run in claimed] == [first.id]
        assert (
            await repository.claim_validations(
                worker_id="product-pack-worker-b",
                limit=1,
                lease_seconds=60,
            )
            == []
        )

        cancelled = await repository.cancel_validation(
            draft.id,
            first.id,
            actor="integration-test",
        )
        assert cancelled.cancel_requested_at is not None
        completed = await repository.complete_validation(
            first.id,
            worker_id="product-pack-worker-a",
            passed=True,
            gates=[{"id": "quick", "status": "passed"}],
        )
        assert completed.status == "cancelled"

        retried = await repository.request_validation(
            draft.id,
            suite="quick",
            engine_version="integration-test",
        )
        assert retried.id == first.id
        assert retried.status == "queued"
        assert retried.attempt_count == 0

        for index, kind in enumerate(("compact_golden", "full_golden"), start=1):
            await repository.add_evidence(
                draft.id,
                kind=kind,
                label=kind,
                storage_uri=f"s3://private/{pack_id}/{kind}.parquet",
                content_type="application/vnd.apache.parquet",
                checksum=f"{index}" * 64,
                byte_size=100,
                row_count=10,
                metadata={"authority": "integration-test"},
                actor="integration-test",
            )
        publication_validation = await repository.request_validation(
            draft.id,
            suite="publication",
            engine_version="integration-test",
        )
        publication_claim = await repository.claim_validations(
            worker_id="product-pack-worker-a",
            limit=2,
            lease_seconds=60,
        )
        publication_job = next(
            run for run in publication_claim if run.id == publication_validation.id
        )
        passed = await repository.complete_validation(
            publication_job.id,
            worker_id="product-pack-worker-a",
            passed=True,
            gates=[{"id": "publication", "status": "passed"}],
        )
        assert passed.status == "passed"

        publication = await repository.publish(
            draft.id,
            validation_run_id=passed.id,
            actor="integration-test",
            activate=True,
            default_keyword="test product",
            release_notes="Integration certification",
        )
        record = await catalog.get(pack_id, "1.0.0")
        published = await catalog.list_published()
        assert publication.active is True
        assert record.active is True
        assert any(
            item.id == pack_id and item.version == "1.0.0" and item.active for item in published
        )
        assert record.document == config
        assert record.report_blueprint == blueprint

        with pytest.raises(ProductPackDraftConflictError, match="immutable"):
            await repository.update_draft(
                draft.id,
                expected_revision=1,
                config={**config, "description": "changed after publication"},
                report_blueprint=blueprint,
                actor="integration-test",
            )
    finally:
        await database.dispose()
