"""Product Pack catalog and immutable database publication."""

from __future__ import annotations

import json
import os
import secrets
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, cast

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from rci_contracts import validate_instance
from rci_product_packs import (
    FileProductPackCatalog,
    PostgresProductPackAuthoringRepository,
    PostgresProductPackCatalog,
    ProductPackDraftConflictError,
    ProductPackDraftNotFoundError,
    ProductPackPublicationError,
    canonical_checksum,
)
from rci_product_packs.models import ValidationSuite

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


class ProductPackDraftResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    product_pack_id: str
    base_version: str | None
    proposed_version: str
    status: str
    revision: int
    config: dict[str, Any]
    report_blueprint: dict[str, Any]
    checksum: str
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime


class ProductPackValidationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    draft_id: str
    draft_revision: int
    draft_checksum: str
    suite: str
    status: str
    gates: tuple[dict[str, Any], ...]
    engine_version: str | None
    attempt_count: int
    max_attempts: int
    locked_by: str | None
    lease_expires_at: datetime | None
    last_error: str | None
    cancel_requested_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class ProductPackEvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    draft_id: str
    kind: str
    label: str
    storage_uri: str
    content_type: str
    checksum: str
    byte_size: int
    row_count: int | None
    metadata: dict[str, Any]
    created_by: str
    created_at: datetime


class CreateProductPackDraftRequest(BaseModel):
    product_pack_id: str = Field(pattern="^[a-z0-9_]+$")
    name: str = Field(min_length=1, max_length=160)
    proposed_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    category_family: str = Field(min_length=1, max_length=160)
    default_keyword: str = Field(min_length=1, max_length=200)
    source_pack_id: str | None = None
    source_version: str | None = None


class UpdateProductPackDraftRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    config: dict[str, Any]
    report_blueprint: dict[str, Any]
    reason: str | None = Field(default=None, max_length=1000)


class RequestProductPackValidation(BaseModel):
    suite: str = Field(pattern="^(quick|compact|full|publication)$")


class AddProductPackEvidenceRequest(BaseModel):
    kind: str = Field(
        pattern="^(serp|pdp|classification|attribute|comparison|compact_golden|full_golden)$"
    )
    label: str = Field(min_length=1, max_length=200)
    storage_uri: str = Field(min_length=1, max_length=2000)
    content_type: str = Field(min_length=1, max_length=200)
    checksum: str = Field(pattern="^[a-f0-9]{64}$")
    byte_size: int = Field(ge=0)
    row_count: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PublishProductPackRequest(BaseModel):
    validation_run_id: str = Field(min_length=1)
    activate: bool = False
    default_keyword: str = Field(min_length=1, max_length=200)
    release_notes: str | None = Field(default=None, max_length=4000)


@dataclass(frozen=True, slots=True)
class ProductPackCatalogVersion:
    id: str
    name: str
    version: str
    schema_version: str
    checksum: str
    document: dict[str, Any]
    default_keyword: str
    report_blueprint: dict[str, Any]
    report_blueprint_checksum: str


def _canonical_checksum(document: dict[str, Any]) -> str:
    return canonical_checksum(document)


def _enabled(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _actor(value: str | None) -> str:
    rendered = (value or "interactive-admin").strip()
    return rendered[:200] or "interactive-admin"


def _require_authoring_access(request: Request, provided_token: str | None) -> None:
    enabled = _enabled(
        os.getenv("PRODUCT_PACK_BUILDER_ENABLED"),
        default=not request.app.state.settings.is_production,
    )
    if not enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Product Pack authoring is disabled in this environment.",
        )
    expected = os.getenv("PRODUCT_PACK_ADMIN_TOKEN")
    if request.app.state.settings.is_production and (
        not expected or not provided_token or not secrets.compare_digest(expected, provided_token)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated Product Pack administrator access is required.",
        )


def _starter_documents(
    root: Path,
    request_body: CreateProductPackDraftRequest,
) -> tuple[dict[str, Any], dict[str, Any]]:
    index = json.loads((root / "product-packs" / "index.json").read_text(encoding="utf-8"))
    starter_summary = next(
        item for item in index["packs"] if item["id"] == index["default_pack_id"]
    )
    template = json.loads(
        (root / "product-packs" / str(starter_summary["file"])).read_text(encoding="utf-8")
    )
    template_blueprint_ref = template["reporting"]["report_blueprint"]
    blueprint = json.loads(
        (root / "report-blueprints" / f"{template_blueprint_ref['id']}.json").read_text(
            encoding="utf-8"
        )
    )
    pack_id = request_body.product_pack_id
    version = request_body.proposed_version
    blueprint_id = f"{pack_id}_leadership"
    template.update(
        {
            "id": pack_id,
            "name": request_body.name,
            "version": version,
            "category_family": request_body.category_family,
            "description": (
                "Governed Product Pack draft. Replace starter rules with labeled evidence."
            ),
            "scope": {
                "include": [request_body.default_keyword],
                "exclude": [],
                "hard_exclusion_patterns": [],
                "target_terms": [request_body.default_keyword],
                "availability_policy": "search_presence",
                "require_positive_price": True,
            },
            "attributes": [
                {
                    "name": "package_weight_oz",
                    "label": "Package weight",
                    "data_type": "number",
                    "role": "matching",
                    "required_for_strict": True,
                    "unit": "oz",
                    "unknown_policy": "review",
                    "extractors": ["title_rule", "retailer_field", "manual"],
                    "extraction_rules": [
                        {
                            "type": "measurement",
                            "sources": ["title", "raw_text"],
                            "units": {"oz": 1, "ounce": 1, "ounces": 1, "lb": 16, "lbs": 16},
                        }
                    ],
                }
            ],
            "normalization": {
                "primary_display_metric": "package_price",
                "secondary_metrics": [],
                "conversion_rules": [],
                "forbidden_metrics": [],
                "package_equivalence_policy": "exact_package_first",
            },
            "matching_profiles": [
                {
                    "id": "strict_package",
                    "label": "Exact package",
                    "geography": "exact_zip",
                    "dimensions": ["package_weight_oz"],
                    "brand_policy": "ignore_brand",
                    "unknown_policy": "reject",
                    "price_selection": "lowest_positive",
                    "comparison_metric": "package_price",
                    "availability_policy": "search_presence",
                }
            ],
            "brand_rules": {"aliases": {}, "private_labels": {}},
            "retailer_overrides": {},
            "regression": {
                "golden_dataset_ids": [],
                "expected_headlines": [],
                "tolerances": {},
            },
        }
    )
    template["reporting"] = {
        "headline_segments": [],
        "required_caveats": [
            "Search observations are authoritative for store-specific price and availability.",
            "Comparison eligibility follows the configured Product Pack attributes.",
        ],
        "recommended_charts": ["footprint", "segment_win_rate", "price_position"],
        "decision_rules": {
            "preferred_scorecard_profile_id": "strict_package",
            "profile_priority": ["strict_package"],
            "minimum_observations": 25,
            "minimum_geographies": 25,
            "executive_relationship_states": ["suggested", "confirmed"],
            "extreme_gap_behavior": "suppress",
            "parity_display": "include",
        },
        "alertable_metrics": [],
        "report_blueprint": {"id": blueprint_id, "version": version},
        "narrative_playbook": {
            "leadership_objective": (
                "Explain the validated price, assortment, and geographic position for "
                f"{request_body.name}."
            ),
            "required_topics": [
                "data_scope",
                "footprint",
                "exact_price",
                "normalized_price",
                "segment_drivers",
                "geography",
                "fulfillment",
                "brand_assortment",
                "actions",
                "caveats",
            ],
            "decision_lenses": [
                {
                    "id": "package_position",
                    "label": "Package-price position",
                    "question": (
                        "Where is the primary retailer winning or being undercut on "
                        "comparable packages?"
                    ),
                    "metric_selectors": ["comparison.*"],
                }
            ],
            "action_principles": [
                "Use only repeated, evidence-backed price and assortment signals.",
                "Keep decisions specific to the configured comparison lens.",
            ],
            "forbidden_claims": [
                "Do not compare products that fail the configured eligibility rules.",
                "Do not replace observed store price with enriched product-detail price.",
            ],
            "small_sample_threshold": 25,
        },
        "insight_ranking": {
            "weights": {
                "breadth": 0.3,
                "magnitude": 0.3,
                "confidence": 0.2,
                "actionability": 0.2,
            },
            "minimum_score": 0.3,
            "max_candidates": 8,
        },
        "insight_rules": [
            {
                "id": "competitive_pressure",
                "scope": "both",
                "condition": {
                    "field": "competitor_lower_rate",
                    "operator": "gt",
                    "threshold": 0.5,
                },
                "title_template": "{competitor} pressure in {segment}",
                "summary_template": (
                    "{competitor} is lower more often than {benchmark} for the selected "
                    "{profile} comparison."
                ),
                "business_impact": (
                    "Repeated price pressure may warrant a product- and market-level review."
                ),
                "severity": "high",
                "breadth_scale": 500,
                "magnitude_scale": 0.5,
                "confidence_scale": 250,
                "actionability": 0.8,
                "minimum_matches": 25,
                "limitations": [
                    "The signal is limited to validated comparable products and observed markets."
                ],
            }
        ],
    }
    blueprint["id"] = blueprint_id
    blueprint["version"] = version
    blueprint["product_pack"] = {"id": pack_id, "version": version}
    section_titles = {
        "executive_summary": "Executive Summary",
        "kpi_strip": "Decision KPIs",
        "coverage": f"{request_body.name} Geographic Footprint",
        "price_position": "Comparable Price Position",
        "segment_analysis": "Attribute Segments",
        "geographic_sensitivity": "Geographic Sensitivity",
        "product_table": "Products and Assortment",
        "assortment": "Assortment Intelligence",
        "recommendations": "Key Points",
        "data_quality": "Data Quality",
        "methodology": "Caveats and Assumptions",
    }
    for section in blueprint["sections"]:
        section["title"] = section_titles.get(section["kind"], section["title"])
        section["empty_state"] = "No validated evidence was produced for this section."
    return template, blueprint


def load_product_pack_catalog_versions(root: Path) -> tuple[ProductPackCatalogVersion, ...]:
    """Load the deployable catalog and verify every indexed immutable version."""

    index = json.loads((root / "product-packs" / "index.json").read_text(encoding="utf-8"))
    versions: list[ProductPackCatalogVersion] = []
    for summary in index["packs"]:
        path = root / "product-packs" / str(summary["file"])
        document = json.loads(path.read_text(encoding="utf-8"))
        validate_instance(root, "product-pack.schema.json", document, label=str(path))
        blueprint_ref = document["reporting"]["report_blueprint"]
        blueprint_path = root / "report-blueprints" / f"{blueprint_ref['id']}.json"
        blueprint = json.loads(blueprint_path.read_text(encoding="utf-8"))
        validate_instance(
            root,
            "report-blueprint.schema.json",
            blueprint,
            label=str(blueprint_path),
        )
        if str(blueprint["version"]) != str(blueprint_ref["version"]):
            raise ValueError(f"Product Pack {path.name!r} report-blueprint version mismatch")
        if (str(blueprint["product_pack"]["id"]), str(blueprint["product_pack"]["version"])) != (
            str(document["id"]),
            str(document["version"]),
        ):
            raise ValueError(f"Report blueprint {blueprint_path.name!r} belongs to another pack")
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
                schema_version=str(document.get("schema_version", "1.0.0")),
                checksum=_canonical_checksum(document),
                document=document,
                default_keyword=str(summary.get("default_keyword", "")),
                report_blueprint=blueprint,
                report_blueprint_checksum=_canonical_checksum(blueprint),
            )
        )
    return tuple(versions)


async def synchronize_product_pack_catalog(engine: AsyncEngine, root: Path) -> int:
    """Publish missing file-backed Product Pack versions without mutating existing ones."""

    versions = load_product_pack_catalog_versions(root)
    async with engine.begin() as connection:
        await connection.execute(text("SET CONSTRAINTS ALL DEFERRED"))
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
                      product_pack_id, version, schema_version, config, checksum,
                      default_keyword, report_blueprint_id, report_blueprint_version,
                      report_blueprint_checksum, published_by
                    ) VALUES (
                      :id, :version, :schema_version, CAST(:config AS jsonb), :checksum,
                      :default_keyword, :report_blueprint_id, :report_blueprint_version,
                      :report_blueprint_checksum, 'repository-seed'
                    )
                    ON CONFLICT (product_pack_id, version) DO NOTHING
                    """
                ),
                {
                    "id": pack.id,
                    "version": pack.version,
                    "schema_version": pack.schema_version,
                    "config": json.dumps(pack.document, sort_keys=True),
                    "checksum": pack.checksum,
                    "default_keyword": pack.default_keyword,
                    "report_blueprint_id": str(pack.report_blueprint["id"]),
                    "report_blueprint_version": str(pack.report_blueprint["version"]),
                    "report_blueprint_checksum": pack.report_blueprint_checksum,
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
            await connection.execute(
                text(
                    """
                    UPDATE product_pack_version SET
                      default_keyword = CASE
                        WHEN default_keyword = '' THEN :default_keyword ELSE default_keyword END,
                      report_blueprint_id = COALESCE(report_blueprint_id, :report_blueprint_id),
                      report_blueprint_version = COALESCE(
                        report_blueprint_version, :report_blueprint_version
                      ),
                      report_blueprint_checksum = COALESCE(
                        report_blueprint_checksum, :report_blueprint_checksum
                      )
                    WHERE product_pack_id = :id AND version = :version
                    """
                ),
                {
                    "id": pack.id,
                    "version": pack.version,
                    "default_keyword": pack.default_keyword,
                    "report_blueprint_id": str(pack.report_blueprint["id"]),
                    "report_blueprint_version": str(pack.report_blueprint["version"]),
                    "report_blueprint_checksum": pack.report_blueprint_checksum,
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO report_blueprint (id, name)
                    VALUES (:id, :name)
                    ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name
                    """
                ),
                {
                    "id": str(pack.report_blueprint["id"]),
                    "name": str(pack.report_blueprint["id"]).replace("_", " ").title(),
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO report_blueprint_version (
                      report_blueprint_id, version, schema_version,
                      product_pack_id, product_pack_version, config, checksum, published_by
                    ) VALUES (
                      :blueprint_id, :blueprint_version, :schema_version,
                      :pack_id, :pack_version, CAST(:config AS jsonb), :checksum,
                      'repository-seed'
                    )
                    ON CONFLICT (report_blueprint_id, version) DO NOTHING
                    """
                ),
                {
                    "blueprint_id": str(pack.report_blueprint["id"]),
                    "blueprint_version": str(pack.report_blueprint["version"]),
                    "schema_version": str(pack.report_blueprint.get("schema_version", "1.0.0")),
                    "pack_id": pack.id,
                    "pack_version": pack.version,
                    "config": json.dumps(pack.report_blueprint, sort_keys=True),
                    "checksum": pack.report_blueprint_checksum,
                },
            )
            existing_blueprint_checksum = (
                await connection.execute(
                    text(
                        """
                        SELECT checksum FROM report_blueprint_version
                        WHERE report_blueprint_id = :id AND version = :version
                        """
                    ),
                    {
                        "id": str(pack.report_blueprint["id"]),
                        "version": str(pack.report_blueprint["version"]),
                    },
                )
            ).scalar_one()
            if str(existing_blueprint_checksum) != pack.report_blueprint_checksum:
                raise ValueError(
                    f"Report blueprint {pack.report_blueprint['id']}@"
                    f"{pack.report_blueprint['version']} differs from its immutable version"
                )
            await connection.execute(
                text(
                    """
                    UPDATE product_pack SET active_version = COALESCE(active_version, :version),
                      updated_at = now()
                    WHERE id = :id
                    """
                ),
                {"id": pack.id, "version": pack.version},
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
async def list_product_packs(request: Request) -> ProductPackCatalogResponse:
    try:
        records = await PostgresProductPackCatalog(
            request.app.state.database_probe.engine
        ).list_active()
    except Exception:
        return _catalog()
    if not records:
        return _catalog()
    fallback = _catalog()
    return ProductPackCatalogResponse(
        schema_version="1.0",
        default_pack_id=(
            fallback.default_pack_id
            if any(item.id == fallback.default_pack_id for item in records)
            else records[0].id
        ),
        packs=tuple(
            ProductPackSummary(
                id=item.id,
                name=item.name,
                version=item.version,
                default_keyword=item.default_keyword,
            )
            for item in records
        ),
    )


@router.get("/product-packs/{pack_id}/versions/{version}", tags=["product-packs"])
async def get_product_pack_version(
    pack_id: str,
    version: str,
    request: Request,
) -> dict[str, Any]:
    try:
        record = await PostgresProductPackCatalog(request.app.state.database_probe.engine).get(
            pack_id, version
        )
    except Exception as database_error:
        root = Path(os.getenv("RCI_REPOSITORY_ROOT", Path.cwd())).resolve()
        try:
            record = await FileProductPackCatalog(root).get(pack_id, version)
        except LookupError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from (
                database_error
            )
    return {
        "id": record.id,
        "name": record.name,
        "version": record.version,
        "active": record.active,
        "default_keyword": record.default_keyword,
        "checksum": record.checksum,
        "config": record.document,
        "report_blueprint": record.report_blueprint,
    }


@router.get("/admin/product-packs/status", tags=["admin", "product-packs"])
async def product_pack_builder_status(request: Request) -> dict[str, Any]:
    enabled = _enabled(
        os.getenv("PRODUCT_PACK_BUILDER_ENABLED"),
        default=not request.app.state.settings.is_production,
    )
    return {
        "enabled": enabled,
        "writes_require_authentication": request.app.state.settings.is_production,
        "production_safe": bool(os.getenv("PRODUCT_PACK_ADMIN_TOKEN")) if enabled else True,
    }


@router.get("/admin/product-packs/capabilities", tags=["admin", "product-packs"])
async def product_pack_capabilities() -> dict[str, Any]:
    root = Path(os.getenv("RCI_REPOSITORY_ROOT", Path.cwd())).resolve()
    return json.loads(
        (root / "config" / "product-pack-capabilities.json").read_text(encoding="utf-8")
    )


@router.get(
    "/admin/product-packs/drafts",
    response_model=list[ProductPackDraftResponse],
    tags=["admin", "product-packs"],
)
async def list_product_pack_drafts(
    request: Request,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> list[Any]:
    _require_authoring_access(request, x_rci_admin_token)
    return await PostgresProductPackAuthoringRepository(
        request.app.state.database_probe.engine
    ).list_drafts()


@router.post(
    "/admin/product-packs/drafts",
    response_model=ProductPackDraftResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["admin", "product-packs"],
)
async def create_product_pack_draft(
    request_body: CreateProductPackDraftRequest,
    request: Request,
    x_rci_actor: Annotated[str | None, Header(alias="X-RCI-Actor")] = None,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> Any:
    _require_authoring_access(request, x_rci_admin_token)
    root = Path(os.getenv("RCI_REPOSITORY_ROOT", Path.cwd())).resolve()
    base_version: str | None = None
    if request_body.source_pack_id and request_body.source_version:
        try:
            source = await PostgresProductPackCatalog(request.app.state.database_probe.engine).get(
                request_body.source_pack_id, request_body.source_version
            )
        except Exception as database_error:
            try:
                source = await FileProductPackCatalog(root).get(
                    request_body.source_pack_id,
                    request_body.source_version,
                )
            except LookupError as exc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=str(exc),
                ) from database_error
        config = deepcopy(source.document)
        blueprint = deepcopy(source.report_blueprint)
        base_version = source.version
        config.update(
            {
                "id": request_body.product_pack_id,
                "name": request_body.name,
                "version": request_body.proposed_version,
                "category_family": request_body.category_family,
            }
        )
        blueprint_id = (
            str(blueprint["id"])
            if request_body.product_pack_id == source.id
            else f"{request_body.product_pack_id}_leadership"
        )
        blueprint["id"] = blueprint_id
        blueprint["version"] = request_body.proposed_version
        blueprint["product_pack"] = {
            "id": request_body.product_pack_id,
            "version": request_body.proposed_version,
        }
        config["reporting"]["report_blueprint"] = {
            "id": blueprint_id,
            "version": request_body.proposed_version,
        }
    elif request_body.source_pack_id or request_body.source_version:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="source_pack_id and source_version must be supplied together",
        )
    else:
        config, blueprint = _starter_documents(root, request_body)
    try:
        return await PostgresProductPackAuthoringRepository(
            request.app.state.database_probe.engine
        ).create_draft(
            product_pack_id=request_body.product_pack_id,
            proposed_version=request_body.proposed_version,
            config=config,
            report_blueprint=blueprint,
            actor=_actor(x_rci_actor),
            base_version=base_version,
        )
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A draft or published version already uses this Product Pack version.",
        ) from exc


@router.get(
    "/admin/product-packs/drafts/{draft_id}",
    response_model=ProductPackDraftResponse,
    tags=["admin", "product-packs"],
)
async def get_product_pack_draft(
    draft_id: str,
    request: Request,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> Any:
    _require_authoring_access(request, x_rci_admin_token)
    try:
        return await PostgresProductPackAuthoringRepository(
            request.app.state.database_probe.engine
        ).get_draft(draft_id)
    except ProductPackDraftNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch(
    "/admin/product-packs/drafts/{draft_id}",
    response_model=ProductPackDraftResponse,
    tags=["admin", "product-packs"],
)
async def update_product_pack_draft(
    draft_id: str,
    request_body: UpdateProductPackDraftRequest,
    request: Request,
    x_rci_actor: Annotated[str | None, Header(alias="X-RCI-Actor")] = None,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> Any:
    _require_authoring_access(request, x_rci_admin_token)
    try:
        return await PostgresProductPackAuthoringRepository(
            request.app.state.database_probe.engine
        ).update_draft(
            draft_id,
            expected_revision=request_body.expected_revision,
            config=request_body.config,
            report_blueprint=request_body.report_blueprint,
            actor=_actor(x_rci_actor),
            reason=request_body.reason,
        )
    except ProductPackDraftNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ProductPackDraftConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get(
    "/admin/product-packs/drafts/{draft_id}/evidence",
    response_model=list[ProductPackEvidenceResponse],
    tags=["admin", "product-packs"],
)
async def list_product_pack_evidence(
    draft_id: str,
    request: Request,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> list[Any]:
    _require_authoring_access(request, x_rci_admin_token)
    try:
        return await PostgresProductPackAuthoringRepository(
            request.app.state.database_probe.engine
        ).list_evidence(draft_id)
    except ProductPackDraftNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/admin/product-packs/drafts/{draft_id}/evidence",
    response_model=ProductPackEvidenceResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["admin", "product-packs"],
)
async def add_product_pack_evidence(
    draft_id: str,
    request_body: AddProductPackEvidenceRequest,
    request: Request,
    x_rci_actor: Annotated[str | None, Header(alias="X-RCI-Actor")] = None,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> Any:
    _require_authoring_access(request, x_rci_admin_token)
    try:
        return await PostgresProductPackAuthoringRepository(
            request.app.state.database_probe.engine
        ).add_evidence(
            draft_id,
            kind=request_body.kind,
            label=request_body.label,
            storage_uri=request_body.storage_uri,
            content_type=request_body.content_type,
            checksum=request_body.checksum,
            byte_size=request_body.byte_size,
            row_count=request_body.row_count,
            metadata=request_body.metadata,
            actor=_actor(x_rci_actor),
        )
    except ProductPackDraftNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/admin/product-packs/drafts/{draft_id}/validations",
    response_model=list[ProductPackValidationResponse],
    tags=["admin", "product-packs"],
)
async def list_product_pack_validations(
    draft_id: str,
    request: Request,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> list[Any]:
    _require_authoring_access(request, x_rci_admin_token)
    try:
        return await PostgresProductPackAuthoringRepository(
            request.app.state.database_probe.engine
        ).list_validations(draft_id)
    except ProductPackDraftNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/admin/product-packs/drafts/{draft_id}/validations",
    response_model=ProductPackValidationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["admin", "product-packs"],
)
async def request_product_pack_validation(
    draft_id: str,
    request_body: RequestProductPackValidation,
    request: Request,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> Any:
    _require_authoring_access(request, x_rci_admin_token)
    try:
        return await PostgresProductPackAuthoringRepository(
            request.app.state.database_probe.engine
        ).request_validation(
            draft_id,
            suite=cast(ValidationSuite, request_body.suite),
            engine_version=str(request.app.state.settings.app_version),
        )
    except ProductPackDraftNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/admin/product-packs/drafts/{draft_id}/validations/{validation_run_id}/cancel",
    response_model=ProductPackValidationResponse,
    tags=["admin", "product-packs"],
)
async def cancel_product_pack_validation(
    draft_id: str,
    validation_run_id: str,
    request: Request,
    x_rci_actor: Annotated[str | None, Header(alias="X-RCI-Actor")] = None,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> Any:
    _require_authoring_access(request, x_rci_admin_token)
    try:
        return await PostgresProductPackAuthoringRepository(
            request.app.state.database_probe.engine
        ).cancel_validation(
            draft_id,
            validation_run_id,
            actor=_actor(x_rci_actor),
        )
    except ProductPackDraftNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/admin/product-packs/drafts/{draft_id}/publish",
    status_code=status.HTTP_201_CREATED,
    tags=["admin", "product-packs"],
)
async def publish_product_pack_draft(
    draft_id: str,
    request_body: PublishProductPackRequest,
    request: Request,
    x_rci_actor: Annotated[str | None, Header(alias="X-RCI-Actor")] = None,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> dict[str, Any]:
    _require_authoring_access(request, x_rci_admin_token)
    try:
        publication = await PostgresProductPackAuthoringRepository(
            request.app.state.database_probe.engine
        ).publish(
            draft_id,
            validation_run_id=request_body.validation_run_id,
            actor=_actor(x_rci_actor),
            activate=request_body.activate,
            default_keyword=request_body.default_keyword,
            release_notes=request_body.release_notes,
        )
    except ProductPackDraftNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ProductPackPublicationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {
        "schema_version": "1.0.0",
        "product_pack_id": publication.product_pack_id,
        "version": publication.version,
        "checksum": publication.checksum,
        "report_blueprint_id": publication.report_blueprint_id,
        "report_blueprint_version": publication.report_blueprint_version,
        "report_blueprint_checksum": publication.report_blueprint_checksum,
        "validation_run_id": publication.validation_run_id,
        "active": publication.active,
        "published_by": publication.published_by,
        "published_at": publication.published_at.isoformat(),
    }
