from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from rci_product_packs.models import ProductPackDraft, ProductPackEvidence
from rci_product_packs.repository import draft_checksum
from rci_worker.product_pack_validation import validate_product_pack_draft

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _draft() -> ProductPackDraft:
    config = json.loads((REPOSITORY_ROOT / "product-packs/fresh_ground_beef.json").read_text())
    blueprint = json.loads(
        (REPOSITORY_ROOT / "report-blueprints/fresh_ground_beef_leadership.json").read_text()
    )
    now = datetime.now(UTC)
    return ProductPackDraft(
        id="00000000-0000-0000-0000-000000000001",
        product_pack_id=str(config["id"]),
        base_version=None,
        proposed_version=str(config["version"]),
        status="draft",
        revision=1,
        config=config,
        report_blueprint=blueprint,
        checksum=draft_checksum(config, blueprint),
        created_by="test",
        updated_by="test",
        created_at=now,
        updated_at=now,
    )


def _evidence(kind: str) -> ProductPackEvidence:
    return ProductPackEvidence(
        id=f"evidence-{kind}",
        draft_id="00000000-0000-0000-0000-000000000001",
        kind=kind,
        label=kind,
        storage_uri=f"s3://private/{kind}.parquet",
        content_type="application/vnd.apache.parquet",
        checksum="a" * 64,
        byte_size=100,
        row_count=10,
        metadata={"authority": "governed_test"},
        created_by="test",
        created_at=datetime.now(UTC),
    )


def test_quick_suite_validates_contract_and_generic_capabilities() -> None:
    gates = validate_product_pack_draft(REPOSITORY_ROOT, _draft(), (), "quick")

    assert gates
    assert {str(gate["status"]) for gate in gates} == {"passed"}


def test_publication_suite_requires_compact_and_full_golden_manifests() -> None:
    gates = validate_product_pack_draft(REPOSITORY_ROOT, _draft(), (), "publication")

    golden_gate = next(gate for gate in gates if gate["id"] == "golden_evidence")
    assert golden_gate["status"] == "failed"
    assert "compact_golden" in str(golden_gate["message"])
    assert "full_golden" in str(golden_gate["message"])


def test_publication_suite_accepts_checksum_bound_golden_manifests() -> None:
    gates = validate_product_pack_draft(
        REPOSITORY_ROOT,
        _draft(),
        (_evidence("compact_golden"), _evidence("full_golden")),
        "publication",
    )

    assert {str(gate["status"]) for gate in gates} == {"passed"}
