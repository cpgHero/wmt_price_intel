"""Read-only Product Pack catalog for configuration-driven collection creation."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

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
