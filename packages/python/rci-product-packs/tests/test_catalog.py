from __future__ import annotations

import json
from pathlib import Path

import pytest

from rci_product_packs import FileProductPackCatalog, canonical_checksum

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


async def test_file_catalog_returns_exact_immutable_runtime_bundle() -> None:
    catalog = FileProductPackCatalog(REPOSITORY_ROOT)

    record = await catalog.get("fresh_ground_beef", "1.1.0")

    assert record.id == "fresh_ground_beef"
    assert record.version == "1.1.0"
    assert record.active is True
    assert record.checksum == canonical_checksum(record.document)
    assert record.report_blueprint["product_pack"] == {
        "id": record.id,
        "version": record.version,
    }


async def test_file_catalog_lists_every_active_repository_pack() -> None:
    catalog = FileProductPackCatalog(REPOSITORY_ROOT)

    records = await catalog.list_active()

    index = json.loads((REPOSITORY_ROOT / "product-packs/index.json").read_text())
    assert {(record.id, record.version) for record in records} == {
        (str(item["id"]), str(item["version"])) for item in index["packs"]
    }


async def test_file_catalog_lists_bootstrap_versions_as_published() -> None:
    catalog = FileProductPackCatalog(REPOSITORY_ROOT)

    assert await catalog.list_published() == await catalog.list_active()


async def test_file_catalog_rejects_unknown_version() -> None:
    catalog = FileProductPackCatalog(REPOSITORY_ROOT)

    with pytest.raises(LookupError, match="was not found"):
        await catalog.get("fresh_ground_beef", "99.0.0")


def test_canonical_checksum_ignores_mapping_order() -> None:
    assert canonical_checksum({"a": 1, "b": {"c": 2}}) == canonical_checksum(
        {"b": {"c": 2}, "a": 1}
    )
