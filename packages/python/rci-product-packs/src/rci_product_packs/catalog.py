"""Exact-version Product Pack and report-blueprint document catalog."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

JsonObject = dict[str, Any]


def canonical_checksum(document: JsonObject) -> str:
    body = json.dumps(
        document,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(body).hexdigest()


@dataclass(frozen=True, slots=True)
class CatalogProductPack:
    id: str
    name: str
    version: str
    active: bool
    default_keyword: str
    checksum: str
    document: JsonObject
    report_blueprint: JsonObject


class ProductPackCatalog(Protocol):
    async def list_active(self) -> tuple[CatalogProductPack, ...]: ...

    async def get(self, pack_id: str, version: str) -> CatalogProductPack: ...


class FileProductPackCatalog:
    """Repository-backed bootstrap catalog used by tests and development."""

    def __init__(self, repository_root: Path) -> None:
        self._root = repository_root

    def _versions(self) -> tuple[CatalogProductPack, ...]:
        index = json.loads(
            (self._root / "product-packs" / "index.json").read_text(encoding="utf-8")
        )
        records: list[CatalogProductPack] = []
        for summary in index["packs"]:
            document = json.loads(
                (self._root / "product-packs" / str(summary["file"])).read_text(encoding="utf-8")
            )
            blueprint_ref = document["reporting"]["report_blueprint"]
            blueprint = json.loads(
                (self._root / "report-blueprints" / f"{blueprint_ref['id']}.json").read_text(
                    encoding="utf-8"
                )
            )
            records.append(
                CatalogProductPack(
                    id=str(document["id"]),
                    name=str(document["name"]),
                    version=str(document["version"]),
                    active=True,
                    default_keyword=str(summary.get("default_keyword", "")),
                    checksum=canonical_checksum(document),
                    document=document,
                    report_blueprint=blueprint,
                )
            )
        return tuple(records)

    async def list_active(self) -> tuple[CatalogProductPack, ...]:
        return self._versions()

    async def get(self, pack_id: str, version: str) -> CatalogProductPack:
        try:
            return next(
                record
                for record in self._versions()
                if (record.id, record.version) == (pack_id, version)
            )
        except StopIteration as exc:
            raise LookupError(f"Product Pack {pack_id}@{version} was not found") from exc


class PostgresProductPackCatalog:
    """Load immutable Product Pack bundles by their requested database version."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def list_active(self) -> tuple[CatalogProductPack, ...]:
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT p.id, p.name, p.active_version AS version,
                              v.checksum, v.config,
                              COALESCE(v.default_keyword, '') AS default_keyword,
                              b.config AS report_blueprint
                            FROM product_pack p
                            JOIN product_pack_version v
                              ON v.product_pack_id = p.id
                             AND v.version = p.active_version
                            JOIN report_blueprint_version b
                              ON b.report_blueprint_id = v.report_blueprint_id
                             AND b.version = v.report_blueprint_version
                            WHERE p.active AND p.active_version IS NOT NULL
                            ORDER BY p.name, p.id
                            """
                        )
                    )
                )
                .mappings()
                .all()
            )
        return tuple(self._record(row, active=True) for row in rows)

    async def get(self, pack_id: str, version: str) -> CatalogProductPack:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT p.id, p.name, v.version, v.checksum, v.config,
                              COALESCE(v.default_keyword, '') AS default_keyword,
                              (p.active AND p.active_version = v.version) AS active,
                              b.config AS report_blueprint
                            FROM product_pack p
                            JOIN product_pack_version v ON v.product_pack_id = p.id
                            JOIN report_blueprint_version b
                              ON b.report_blueprint_id = v.report_blueprint_id
                             AND b.version = v.report_blueprint_version
                            WHERE p.id = :pack_id AND v.version = :version
                            """
                        ),
                        {"pack_id": pack_id, "version": version},
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            raise LookupError(f"Product Pack {pack_id}@{version} was not found")
        return self._record(row, active=bool(row["active"]))

    @staticmethod
    def _record(row: Any, *, active: bool) -> CatalogProductPack:
        return CatalogProductPack(
            id=str(row["id"]),
            name=str(row["name"]),
            version=str(row["version"]),
            active=active,
            default_keyword=str(row["default_keyword"]),
            checksum=str(row["checksum"]),
            document=dict(row["config"]),
            report_blueprint=dict(row["report_blueprint"]),
        )
