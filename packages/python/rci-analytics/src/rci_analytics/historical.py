"""Checksummed historical CSV input preparation and idempotent import orchestration."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from rci_contracts import ContractError, validate_instance

JsonObject = dict[str, Any]
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
_ADAPTER_FORMATS = {
    "historical_metricscart_search_monitor_csv": "metricscart_search_monitor_csv",
    "historical_metricscart_consolidated_serp_csv": ("metricscart_consolidated_serp_csv"),
}


def canonical_json(document: Mapping[str, Any]) -> str:
    """Serialize a contract document deterministically for content addressing."""

    return json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


@dataclass(frozen=True, slots=True)
class HistoricalArtifactSpec:
    ordinal: int
    retailer_id: str
    adapter_id: str
    source_name: str
    source_format: str
    content_type: str
    expected_sha256: str
    expected_rows: int


@dataclass(frozen=True, slots=True)
class HistoricalInputManifest:
    stable_key: str
    name: str
    captured_at: str
    product_pack_id: str
    product_pack_version: str
    analysis_config: JsonObject
    artifacts: tuple[HistoricalArtifactSpec, ...]
    document: JsonObject


@dataclass(frozen=True, slots=True)
class PreparedHistoricalArtifact:
    spec: HistoricalArtifactSpec
    path: Path
    checksum: str
    row_count: int
    byte_size: int
    columns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PreparedHistoricalImport:
    manifest: HistoricalInputManifest
    manifest_checksum: str
    durable_manifest: JsonObject
    artifacts: tuple[PreparedHistoricalArtifact, ...]
    total_rows: int


@dataclass(frozen=True, slots=True)
class StoredHistoricalArtifact:
    ordinal: int
    retailer_id: str
    adapter_id: str
    source_name: str
    source_format: str
    storage_uri: str
    content_type: str
    checksum: str
    row_count: int
    byte_size: int
    columns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HistoricalImportRecord:
    input_set_id: str
    collection_run_id: str
    analysis_run_id: str
    manifest_checksum: str
    total_rows: int
    created: bool


class HistoricalObjectStore(Protocol):
    async def put(
        self,
        artifact: PreparedHistoricalArtifact,
        *,
        manifest_checksum: str,
    ) -> StoredHistoricalArtifact: ...


class HistoricalInputRepository(Protocol):
    async def register(
        self,
        prepared: PreparedHistoricalImport,
        stored_artifacts: tuple[StoredHistoricalArtifact, ...],
        *,
        code_version: str,
        max_attempts: int,
    ) -> HistoricalImportRecord: ...


def historical_object_key(artifact: PreparedHistoricalArtifact, *, manifest_checksum: str) -> str:
    safe_name = _SAFE_NAME.sub("-", artifact.spec.source_name).strip("-.") or "source.csv"
    return (
        "raw/source=historical_import/"
        f"input_manifest={manifest_checksum}/retailer_id={artifact.spec.retailer_id}/"
        f"part={artifact.spec.ordinal:04d}/"
        f"{safe_name.removesuffix('.csv')}-{artifact.checksum[:16]}.csv"
    )


class HistoricalInputManifestLoader:
    def __init__(self, repository_root: Path) -> None:
        self._root = repository_root

    def load(self, path: Path) -> HistoricalInputManifest:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ContractError(f"Could not read historical input manifest {path}: {exc}") from exc
        validate_instance(
            self._root,
            "historical-input-manifest.schema.json",
            document,
            label=str(path),
        )
        product_pack = document["product_pack"]
        analysis_config = document["analysis_config"]
        if analysis_config["product_pack"] != product_pack:
            raise ContractError("analysis_config Product Pack must match manifest Product Pack")
        enabled_retailers = {
            str(value["retailer_id"])
            for value in analysis_config["retailers"]
            if bool(value["enabled"])
        }
        artifacts = tuple(
            HistoricalArtifactSpec(
                ordinal=int(value["ordinal"]),
                retailer_id=str(value["retailer_id"]),
                adapter_id=str(value["adapter_id"]),
                source_name=str(value["source_name"]),
                source_format=str(value["source_format"]),
                content_type=str(value["content_type"]),
                expected_sha256=str(value["expected_sha256"]),
                expected_rows=int(value["expected_rows"]),
            )
            for value in document["artifacts"]
        )
        ordinals = [artifact.ordinal for artifact in artifacts]
        if sorted(ordinals) != list(range(len(artifacts))):
            raise ContractError("historical artifact ordinals must be contiguous from zero")
        for artifact in artifacts:
            if artifact.retailer_id not in enabled_retailers:
                raise ContractError(
                    f"historical artifact retailer {artifact.retailer_id!r} is not enabled"
                )
            if _ADAPTER_FORMATS[artifact.adapter_id] != artifact.source_format:
                raise ContractError(
                    f"adapter {artifact.adapter_id!r} does not accept {artifact.source_format!r}"
                )
        expected_total = document.get("metadata", {}).get("source_rows_total")
        if expected_total is not None and int(expected_total) != sum(
            artifact.expected_rows for artifact in artifacts
        ):
            raise ContractError("metadata.source_rows_total does not equal artifact rows")
        return HistoricalInputManifest(
            stable_key=str(document["stable_key"]),
            name=str(document["name"]),
            captured_at=str(document["captured_at"]),
            product_pack_id=str(product_pack["id"]),
            product_pack_version=str(product_pack["version"]),
            analysis_config=dict(analysis_config),
            artifacts=artifacts,
            document=dict(document),
        )


def _profile_csv(path: Path, spec: HistoricalArtifactSpec) -> PreparedHistoricalArtifact:
    checksum = hashlib.sha256()
    byte_size = 0
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            checksum.update(chunk)
            byte_size += len(chunk)
    digest = checksum.hexdigest()
    try:
        with path.open("r", newline="", encoding="utf-8-sig") as source:
            reader = csv.reader(source)
            header = next(reader)
            if not header or any(not value.strip() for value in header):
                raise ValueError("CSV header contains an empty column")
            if len(set(header)) != len(header):
                raise ValueError("CSV header contains duplicate columns")
            row_count = sum(1 for _ in reader)
    except (OSError, StopIteration, UnicodeDecodeError, csv.Error, ValueError) as exc:
        raise ContractError(f"Invalid historical CSV {spec.source_name!r}: {exc}") from exc
    if digest != spec.expected_sha256:
        raise ContractError(
            f"{spec.source_name}: SHA-256 {digest} does not match {spec.expected_sha256}"
        )
    if row_count != spec.expected_rows:
        raise ContractError(
            f"{spec.source_name}: row count {row_count} does not match {spec.expected_rows}"
        )
    return PreparedHistoricalArtifact(
        spec=spec,
        path=path,
        checksum=digest,
        row_count=row_count,
        byte_size=byte_size,
        columns=tuple(header),
    )


def prepare_historical_import(
    manifest: HistoricalInputManifest, source_root: Path
) -> PreparedHistoricalImport:
    root = source_root.resolve(strict=True)
    prepared_artifacts: list[PreparedHistoricalArtifact] = []
    for spec in sorted(manifest.artifacts, key=lambda value: value.ordinal):
        path = (root / spec.source_name).resolve(strict=True)
        if not path.is_relative_to(root) or not path.is_file():
            raise ContractError(f"historical source {spec.source_name!r} is outside source root")
        prepared_artifacts.append(_profile_csv(path, spec))
    artifacts = tuple(prepared_artifacts)
    durable_manifest: JsonObject = {
        "schema_version": "1.0.0",
        "kind": "historical_import",
        "stable_key": manifest.stable_key,
        "name": manifest.name,
        "captured_at": manifest.captured_at,
        "product_pack": {
            "id": manifest.product_pack_id,
            "version": manifest.product_pack_version,
        },
        "analysis_config": manifest.analysis_config,
        "artifacts": [
            {
                "ordinal": artifact.spec.ordinal,
                "retailer_id": artifact.spec.retailer_id,
                "adapter_id": artifact.spec.adapter_id,
                "source_name": artifact.spec.source_name,
                "source_format": artifact.spec.source_format,
                "content_type": artifact.spec.content_type,
                "checksum_sha256": artifact.checksum,
                "row_count": artifact.row_count,
                "byte_size": artifact.byte_size,
                "columns": list(artifact.columns),
            }
            for artifact in artifacts
        ],
        "metadata": dict(manifest.document.get("metadata", {})),
    }
    manifest_checksum = hashlib.sha256(canonical_json(durable_manifest).encode()).hexdigest()
    return PreparedHistoricalImport(
        manifest=manifest,
        manifest_checksum=manifest_checksum,
        durable_manifest=durable_manifest,
        artifacts=artifacts,
        total_rows=sum(artifact.row_count for artifact in artifacts),
    )


class HistoricalImportService:
    def __init__(
        self,
        object_store: HistoricalObjectStore,
        repository: HistoricalInputRepository,
        *,
        code_version: str,
        max_attempts: int = 3,
    ) -> None:
        self._object_store = object_store
        self._repository = repository
        self._code_version = code_version
        self._max_attempts = max_attempts

    async def import_prepared(self, prepared: PreparedHistoricalImport) -> HistoricalImportRecord:
        stored_values: list[StoredHistoricalArtifact] = []
        for artifact in prepared.artifacts:
            stored_values.append(
                await self._object_store.put(
                    artifact,
                    manifest_checksum=prepared.manifest_checksum,
                )
            )
        return await self._repository.register(
            prepared,
            tuple(stored_values),
            code_version=self._code_version,
            max_attempts=self._max_attempts,
        )


@dataclass(slots=True)
class InMemoryHistoricalObjectStore:
    bucket: str = "historical-test"
    objects: dict[str, bytes] = field(default_factory=dict)

    async def put(
        self,
        artifact: PreparedHistoricalArtifact,
        *,
        manifest_checksum: str,
    ) -> StoredHistoricalArtifact:
        key = historical_object_key(artifact, manifest_checksum=manifest_checksum)
        body = artifact.path.read_bytes()
        previous = self.objects.setdefault(key, body)
        if previous != body:
            raise RuntimeError(f"immutable historical object collision at {key}")
        return StoredHistoricalArtifact(
            ordinal=artifact.spec.ordinal,
            retailer_id=artifact.spec.retailer_id,
            adapter_id=artifact.spec.adapter_id,
            source_name=artifact.spec.source_name,
            source_format=artifact.spec.source_format,
            storage_uri=f"s3://{self.bucket}/{key}",
            content_type=artifact.spec.content_type,
            checksum=artifact.checksum,
            row_count=artifact.row_count,
            byte_size=artifact.byte_size,
            columns=artifact.columns,
        )


@dataclass(slots=True)
class InMemoryHistoricalInputRepository:
    imports: dict[str, HistoricalImportRecord] = field(default_factory=dict)
    artifacts: dict[str, tuple[StoredHistoricalArtifact, ...]] = field(default_factory=dict)

    async def register(
        self,
        prepared: PreparedHistoricalImport,
        stored_artifacts: tuple[StoredHistoricalArtifact, ...],
        *,
        code_version: str,
        max_attempts: int,
    ) -> HistoricalImportRecord:
        del code_version, max_attempts
        existing = self.imports.get(prepared.manifest_checksum)
        if existing is not None:
            return HistoricalImportRecord(
                input_set_id=existing.input_set_id,
                collection_run_id=existing.collection_run_id,
                analysis_run_id=existing.analysis_run_id,
                manifest_checksum=existing.manifest_checksum,
                total_rows=existing.total_rows,
                created=False,
            )
        record = HistoricalImportRecord(
            input_set_id=str(uuid4()),
            collection_run_id=str(uuid4()),
            analysis_run_id=str(uuid4()),
            manifest_checksum=prepared.manifest_checksum,
            total_rows=prepared.total_rows,
            created=True,
        )
        self.imports[prepared.manifest_checksum] = record
        self.artifacts[record.input_set_id] = stored_artifacts
        return record
