from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from rci_analytics.historical import (
    HistoricalImportService,
    HistoricalInputManifestLoader,
    InMemoryHistoricalInputRepository,
    InMemoryHistoricalObjectStore,
    prepare_historical_import,
)
from rci_contracts import ContractError

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def _manifest(source_name: str, checksum: str, rows: int) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "stable_key": "leading-zero-identifiers",
        "name": "Leading-zero identifier replay",
        "captured_at": "2026-08-07T05:00:00Z",
        "product_pack": {"id": "fresh_strawberries", "version": "1.0.0"},
        "analysis_config": {
            "id": "historical-leading-zero-identifiers",
            "name": "Historical leading-zero identifiers",
            "version": "1.0.0",
            "benchmark_retailer": "walmart_us",
            "product_pack": {"id": "fresh_strawberries", "version": "1.0.0"},
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
                "expected_sha256": checksum,
                "expected_rows": rows,
            }
        ],
        "metadata": {"source_rows_total": rows},
    }


def _source(tmp_path: Path) -> tuple[Path, bytes]:
    body = (
        b"Retailer,Retailer Store Id,Zipcode,Retailer Product Id,Product Name,Price\n"
        b'walmart.com,0007,00617,0000000000123,"Fresh Strawberries, 1 lb",2.98\n'
    )
    path = tmp_path / "leading-zero.csv"
    path.write_bytes(body)
    return path, body


async def test_historical_import_is_checksummed_immutable_and_idempotent(
    tmp_path: Path,
) -> None:
    source_path, body = _source(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(_manifest(source_path.name, hashlib.sha256(body).hexdigest(), 1)),
        encoding="utf-8",
    )
    manifest = HistoricalInputManifestLoader(REPOSITORY_ROOT).load(manifest_path)
    prepared = prepare_historical_import(manifest, tmp_path)
    store = InMemoryHistoricalObjectStore()
    repository = InMemoryHistoricalInputRepository()
    service = HistoricalImportService(store, repository, code_version="test")

    first = await service.import_prepared(prepared)
    second = await service.import_prepared(prepared)

    assert first.created is True
    assert second.created is False
    assert second.input_set_id == first.input_set_id
    assert second.collection_run_id == first.collection_run_id
    assert second.analysis_run_id == first.analysis_run_id
    assert first.total_rows == 1
    assert len(store.objects) == 1
    assert next(iter(store.objects.values())) == body
    assert b"0007,00617,0000000000123" in next(iter(store.objects.values()))
    assert str(tmp_path) not in json.dumps(prepared.durable_manifest)


def test_historical_import_rejects_checksum_or_row_drift(tmp_path: Path) -> None:
    source_path, body = _source(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    document = _manifest(source_path.name, "0" * 64, 2)
    manifest_path.write_text(json.dumps(document), encoding="utf-8")
    manifest = HistoricalInputManifestLoader(REPOSITORY_ROOT).load(manifest_path)

    with pytest.raises(ContractError, match="SHA-256"):
        prepare_historical_import(manifest, tmp_path)

    corrected = deepcopy(document)
    corrected["artifacts"][0]["expected_sha256"] = hashlib.sha256(body).hexdigest()  # type: ignore[index]
    manifest_path.write_text(json.dumps(corrected), encoding="utf-8")
    manifest = HistoricalInputManifestLoader(REPOSITORY_ROOT).load(manifest_path)
    with pytest.raises(ContractError, match="row count"):
        prepare_historical_import(manifest, tmp_path)


def test_manifest_requires_matching_product_pack_and_enabled_retailers(
    tmp_path: Path,
) -> None:
    source_path, body = _source(tmp_path)
    document = _manifest(source_path.name, hashlib.sha256(body).hexdigest(), 1)
    document["analysis_config"]["product_pack"]["id"] = "fresh_shell_eggs"  # type: ignore[index]
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ContractError, match="Product Pack"):
        HistoricalInputManifestLoader(REPOSITORY_ROOT).load(manifest_path)


def test_historical_import_rejects_source_root_escape(tmp_path: Path) -> None:
    source_root = tmp_path / "sources"
    source_root.mkdir()
    outside = tmp_path / "outside.csv"
    outside.write_text("id\n00123\n", encoding="utf-8")
    escaped = source_root / "escaped.csv"
    escaped.symlink_to(outside)
    body = outside.read_bytes()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(_manifest(escaped.name, hashlib.sha256(body).hexdigest(), 1)),
        encoding="utf-8",
    )
    manifest = HistoricalInputManifestLoader(REPOSITORY_ROOT).load(manifest_path)

    with pytest.raises(ContractError, match="outside source root"):
        prepare_historical_import(manifest, source_root)


def test_full_historical_manifests_pin_all_supplied_rows() -> None:
    loader = HistoricalInputManifestLoader(REPOSITORY_ROOT)
    strawberries = loader.load(
        REPOSITORY_ROOT / "examples/historical-input-manifest.strawberries.json"
    )
    ground_beef = loader.load(
        REPOSITORY_ROOT / "examples/historical-input-manifest.ground-beef.json"
    )

    assert sum(value.expected_rows for value in strawberries.artifacts) == 297443
    assert sum(value.expected_rows for value in ground_beef.artifacts) == 225791
    assert all(
        len(value.expected_sha256) == 64
        for value in (*strawberries.artifacts, *ground_beef.artifacts)
    )
