"""Product Pack catalog and immutable database publication."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from rci_contracts import validate_instance

router = APIRouter(prefix="/api/v1")


class ProductPackSummary(BaseModel):
    id: str
    name: str
    version: str
    default_keyword: str


class ProductPackCatalogResponse(BaseModel):
    schema_version: str
    default_pack_id: str
    packs: tuple[ProductPackSummary, ...]


@dataclass(frozen=True, slots=True)
class ProductPackCatalogVersion:
    id: str
    name: str
    version: str
    checksum: str
    document: dict[str, Any]


def _canonical_checksum(document: dict[str, Any]) -> str:
    body = json.dumps(
        document,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(body).hexdigest()


def load_product_pack_catalog_versions(root: Path) -> tuple[ProductPackCatalogVersion, ...]:
    """Load the deployable catalog and verify every indexed immutable version."""

    index = json.loads((root / "product-packs" / "index.json").read_text(encoding="utf-8"))
    versions: list[ProductPackCatalogVersion] = []
    for summary in index["packs"]:
        path = root / "product-packs" / str(summary["file"])
        document = json.loads(path.read_text(encoding="utf-8"))
        validate_instance(root, "product-pack.schema.json", document, label=str(path))
        for field in ("id", "name", "version"):
            if str(document[field]) != str(summary[field]):
                raise ValueError(
                    f"Product Pack catalog {field} for {path.name!r} does not match its document"
                )
        versions.append(
            ProductPackCatalogVersion(
                id=str(document["id"]),
                name=str(document["name"]),
                version=str(document["version"]),
                checksum=_canonical_checksum(document),
                document=document,
            )
        )
    return tuple(versions)


async def synchronize_product_pack_catalog(engine: AsyncEngine, root: Path) -> int:
    """Publish missing file-backed Product Pack versions without mutating existing ones."""

    versions = load_product_pack_catalog_versions(root)
    async with engine.begin() as connection:
        for pack in versions:
            await connection.execute(
                text(
                    """
                    INSERT INTO product_pack (id, name)
                    VALUES (:id, :name)
                    ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name
                    """
                ),
                {"id": pack.id, "name": pack.name},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO product_pack_version (
                      product_pack_id, version, schema_version, config, checksum
                    ) VALUES (
                      :id, :version, :schema_version, CAST(:config AS jsonb), :checksum
                    )
                    ON CONFLICT (product_pack_id, version) DO NOTHING
                    """
                ),
                {
                    "id": pack.id,
                    "version": pack.version,
                    "schema_version": str(pack.document["schema_version"]),
                    "config": json.dumps(pack.document, sort_keys=True),
                    "checksum": pack.checksum,
                },
            )
            existing_checksum = (
                await connection.execute(
                    text(
                        """
                        SELECT checksum FROM product_pack_version
                        WHERE product_pack_id = :id AND version = :version
                        """
                    ),
                    {"id": pack.id, "version": pack.version},
                )
            ).scalar_one()
            if str(existing_checksum) != pack.checksum:
                raise ValueError(
                    f"Product Pack {pack.id}@{pack.version} differs from its immutable "
                    "published version; increment the version before deployment"
                )
    return len(versions)


@lru_cache(maxsize=1)
def _catalog() -> ProductPackCatalogResponse:
    root = Path(os.getenv("RCI_REPOSITORY_ROOT", Path.cwd())).resolve()
    document = json.loads((root / "product-packs" / "index.json").read_text(encoding="utf-8"))
    packs = tuple(ProductPackSummary.model_validate(value) for value in document["packs"])
    pack_ids = {pack.id for pack in packs}
    default_pack_id = str(document["default_pack_id"])
    if default_pack_id not in pack_ids:
        raise ValueError("default Product Pack is not present in the catalog")
    for value in document["packs"]:
        path = root / "product-packs" / str(value["file"])
        if not path.is_file():
            raise ValueError(f"Product Pack catalog file {path.name!r} does not exist")
    return ProductPackCatalogResponse(
        schema_version=str(document["schema_version"]),
        default_pack_id=default_pack_id,
        packs=packs,
    )


@router.get("/product-packs", response_model=ProductPackCatalogResponse, tags=["product-packs"])
async def list_product_packs() -> ProductPackCatalogResponse:
    return _catalog()
