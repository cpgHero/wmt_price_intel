"""Governed Search-first study discovery and Product Pack handoff APIs."""

from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError

from rci_api.collections import get_collection_service
from rci_api.product_packs import (
    CreateProductPackDraftRequest,
    _actor,
    _require_authoring_access,
    _starter_documents,
)
from rci_contracts import ContractError, validate_instance
from rci_product_packs import (
    FileProductPackCatalog,
    PostgresProductPackAuthoringRepository,
    PostgresProductPackCatalog,
    draft_checksum,
)
from rci_products import (
    MetricsCartProductDetailAdapter,
    PostgresProductDetailRepository,
    ProductDetailCatalog,
    ProductDetailRequestContext,
)
from rci_studies import (
    PostgresStudyRepository,
    StudyNotFoundError,
    StudyRecord,
    StudyStateError,
    canonical_checksum,
    initial_approval_state,
    initial_query_plan,
    safe_product_pack_id,
)

router = APIRouter(prefix="/api/v1/admin/studies", tags=["admin", "studies"])


class CreateStudyRequest(BaseModel):
    name: str = Field(min_length=3, max_length=160)
    benchmark_retailer_id: str = Field(min_length=1, max_length=100)
    competitor_retailer_ids: list[str] = Field(min_length=1)
    category_context: str = Field(min_length=2, max_length=2000)
    known_inclusions: list[str] = Field(default_factory=list)
    known_exclusions: list[str] = Field(default_factory=list)
    geography_request: dict[str, Any]
    max_search_pages: int = Field(default=1, ge=1, le=3)
    amazon_same_day_url_template: str | None = Field(default=None, max_length=2000)


class UpdateQueryPlanRequest(BaseModel):
    keyword: str = Field(min_length=1, max_length=200)
    target_terms: list[str] = Field(min_length=1)
    exclusion_terms: list[str] = Field(default_factory=list)
    alternate_queries: list[str] = Field(default_factory=list, max_length=8)
    rationale: str | None = Field(default=None, max_length=2000)


class RefineProfileScopeRequest(BaseModel):
    target_terms: list[str] = Field(min_length=1)
    exclusion_terms: list[str] = Field(default_factory=list)
    rationale: str | None = Field(default=None, max_length=2000)


class ApproveSearchRequest(BaseModel):
    estimate_id: str
    query_plan_checksum: str = Field(pattern="^[a-f0-9]{64}$")


class ApprovePdpRequest(BaseModel):
    plan_checksum: str = Field(pattern="^[a-f0-9]{64}$")
    max_credits: int = Field(ge=1, le=10000)


class UpdateProductDispositionRequest(BaseModel):
    retailer_id: str = Field(min_length=1, max_length=100)
    retailer_product_id: str = Field(min_length=1, max_length=500)
    admission_status: str = Field(pattern="^(provisionally_admitted|excluded|review_required)$")
    reason: str = Field(min_length=3, max_length=1000)


class CreateDraftRequest(BaseModel):
    product_pack_id: str | None = Field(default=None, pattern="^[a-z0-9_]+$")
    name: str | None = Field(default=None, min_length=1, max_length=160)
    proposed_version: str = Field(default="1.0.0", pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    category_family: str | None = Field(default=None, min_length=1, max_length=160)


def _category_identity(study: StudyRecord) -> tuple[str, str]:
    """Return a reusable category identity, never a study/geography identity."""

    keyword = str(study.query_plan.get("keyword") or "").strip()
    inclusion = next(
        (
            str(value).strip()
            for value in study.intake.get("known_inclusions", [])
            if str(value).strip()
        ),
        "",
    )
    category_name = keyword or inclusion or study.name
    if not category_name.casefold().startswith("fresh "):
        category_name = f"Fresh {category_name}"
    category_name = category_name.title()[:160]
    return safe_product_pack_id(category_name), category_name


async def _active_category_pack(
    request: Request,
    *,
    pack_id: str,
) -> Any | None:
    """Prefer the database catalog, with the repository catalog as bootstrap fallback."""

    try:
        records = await PostgresProductPackCatalog(
            request.app.state.database_probe.engine
        ).list_active()
    except Exception:
        records = await FileProductPackCatalog(_root()).list_active()
    return next((record for record in records if record.id == pack_id), None)


def _next_patch_version(version: str) -> str:
    major, minor, patch = (int(value) for value in version.split("."))
    return f"{major}.{minor}.{patch + 1}"


class StudyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    status: str
    intake: dict[str, Any]
    query_plan: dict[str, Any]
    query_plan_checksum: str
    approval_state: dict[str, Any]
    geography_resolution_id: str | None
    search_scope_estimate_id: str | None
    collection_run_id: str | None
    pdp_estimate: dict[str, Any] | None
    pdp_plan_checksum: str | None
    pdp_run_id: str | None
    product_pack_draft_id: str | None
    profile_summary: dict[str, Any]
    last_error: str | None
    created_at: Any
    updated_at: Any


def _repository(request: Request) -> PostgresStudyRepository:
    return PostgresStudyRepository(request.app.state.database_probe.engine)


def _root() -> Path:
    return Path(os.getenv("RCI_REPOSITORY_ROOT", Path.cwd())).resolve()


def _authorized(
    request: Request,
    token: str | None,
) -> None:
    _require_authoring_access(request, token)


def _not_found(exc: StudyNotFoundError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def _study_collection_config(
    study: StudyRecord,
    *,
    resolution_id: str,
    resolution_checksum: str,
) -> dict[str, Any]:
    intake = study.intake
    query = study.query_plan
    retailer_catalog = {
        str(row["id"]): row
        for row in json.loads(
            (_root() / "config" / "retailer-catalog.json").read_text(encoding="utf-8")
        )["retailers"]
    }
    retailer_ids = [
        str(intake["benchmark_retailer_id"]),
        *(str(value) for value in intake["competitor_retailer_ids"]),
    ]
    retailers = []
    for retailer_id in retailer_ids:
        catalog_row = retailer_catalog.get(retailer_id)
        if catalog_row is None or catalog_row.get("status") != "enabled":
            raise StudyStateError(f"retailer {retailer_id!r} is not enabled for collection")
        retailers.append(
            {
                "retailer_id": retailer_id,
                "adapter_id": str(catalog_row["adapter_id"]),
                "enabled": True,
                "max_pages_override": int(intake["max_search_pages"]),
            }
        )
    return {
        "id": f"study-{study.id}",
        "name": f"Discovery · {study.name}",
        "version": "1.0.0",
        "enabled": False,
        "purpose": "study_discovery",
        "benchmark_retailer": str(intake["benchmark_retailer_id"]),
        "product_pack": None,
        "study_discovery": {
            "study_id": study.id,
            "query_plan_checksum": study.query_plan_checksum,
        },
        "query": {
            "keyword": str(query["keyword"]),
            "amazon_same_day_url_template": intake.get("amazon_same_day_url_template"),
            "notes": "Governed category-discovery sample; no analysis is generated.",
        },
        "retailers": retailers,
        "geography": {
            "strategy": "approved_resolution",
            "resolution_id": resolution_id,
            "resolution_checksum": resolution_checksum,
            "country": str(intake["geography_request"].get("country", "USA")),
            "benchmark_retailer": str(intake["benchmark_retailer_id"]),
            "refresh_policy": "frozen",
        },
        "pagination": {
            "max_pages": int(intake["max_search_pages"]),
            "stop_on_empty": True,
            "stop_on_short_page": True,
        },
        "availability_gate": None,
        "schedule": {"type": "manual", "timezone": "America/Chicago"},
        "analysis": None,
        "delivery": {
            "web_report": False,
            "excel": False,
            "leadership_email": False,
            "audit_package": False,
        },
        "budget": {
            "max_credits_per_run": None,
            "block_if_estimate_exceeds_budget": True,
            "max_credits_per_day": None,
            "max_credits_per_month": None,
        },
        "product_detail_enrichment": {
            "policy": "disabled",
            "approval": "separate_after_search",
            "analysis_admitted_products_only": True,
            "price_variation_samples": True,
        },
    }


@router.get("", response_model=list[StudyResponse])
async def list_studies(
    request: Request,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> list[StudyRecord]:
    _authorized(request, x_rci_admin_token)
    return await _repository(request).list()


@router.post("", response_model=StudyResponse, status_code=status.HTTP_201_CREATED)
async def create_study(
    request_body: CreateStudyRequest,
    request: Request,
    x_rci_actor: Annotated[str | None, Header(alias="X-RCI-Actor")] = None,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> StudyRecord:
    _authorized(request, x_rci_admin_token)
    if request_body.benchmark_retailer_id in request_body.competitor_retailer_ids:
        raise HTTPException(status_code=422, detail="Primary retailer cannot be a competitor")
    if (
        "amazon_us_same_day" in request_body.competitor_retailer_ids
        and not request_body.amazon_same_day_url_template
    ):
        raise HTTPException(
            status_code=422,
            detail="Amazon Same Day discovery requires a reviewed URL template",
        )
    geography = dict(request_body.geography_request)
    if (
        geography.get("primary_retailer_id") != request_body.benchmark_retailer_id
        or geography.get("competitor_retailer_ids") != request_body.competitor_retailer_ids
    ):
        raise HTTPException(
            status_code=422,
            detail="Study retailers and geography retailers must match exactly",
        )
    try:
        validate_instance(
            _root(),
            "collection-geography-request.schema.json",
            geography,
            label="study geography request",
        )
    except ContractError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    intake = {
        "benchmark_retailer_id": request_body.benchmark_retailer_id,
        "competitor_retailer_ids": request_body.competitor_retailer_ids,
        "category_context": request_body.category_context,
        "known_inclusions": request_body.known_inclusions,
        "known_exclusions": request_body.known_exclusions,
        "geography_request": geography,
        "max_search_pages": request_body.max_search_pages,
        "amazon_same_day_url_template": request_body.amazon_same_day_url_template,
    }
    plan = initial_query_plan(
        request_body.category_context,
        known_inclusions=request_body.known_inclusions,
        known_exclusions=request_body.known_exclusions,
    )
    return await _repository(request).create(
        name=request_body.name,
        intake=intake,
        query_plan=plan,
        query_plan_checksum=canonical_checksum(plan),
        approval_state=initial_approval_state(),
        actor=_actor(x_rci_actor),
    )


@router.get("/{study_id}", response_model=StudyResponse)
async def get_study(
    study_id: str,
    request: Request,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> StudyRecord:
    _authorized(request, x_rci_admin_token)
    try:
        return await _repository(request).get(study_id)
    except StudyNotFoundError as exc:
        raise _not_found(exc) from exc


@router.patch("/{study_id}/query-plan", response_model=StudyResponse)
async def update_query_plan(
    study_id: str,
    request_body: UpdateQueryPlanRequest,
    request: Request,
    x_rci_actor: Annotated[str | None, Header(alias="X-RCI-Actor")] = None,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> StudyRecord:
    _authorized(request, x_rci_admin_token)
    current = await get_study(study_id, request, x_rci_admin_token)
    plan = {
        "keyword": request_body.keyword.strip(),
        "target_terms": sorted({value.strip().casefold() for value in request_body.target_terms}),
        "exclusion_terms": sorted(
            {value.strip().casefold() for value in request_body.exclusion_terms if value.strip()}
        ),
        "alternate_queries": sorted(
            {value.strip() for value in request_body.alternate_queries if value.strip()}
        ),
        "source": "human_edited",
        "rationale": request_body.rationale,
        "revision": int(current.query_plan["revision"]) + 1,
    }
    try:
        return await _repository(request).update_query_plan(
            study_id,
            query_plan=plan,
            checksum=canonical_checksum(plan),
            actor=_actor(x_rci_actor),
        )
    except StudyStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{study_id}/profile-scope", response_model=StudyResponse)
async def refine_profile_scope(
    study_id: str,
    request_body: RefineProfileScopeRequest,
    request: Request,
    x_rci_actor: Annotated[str | None, Header(alias="X-RCI-Actor")] = None,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> StudyRecord:
    """Re-run scope screening against saved Search evidence at zero provider cost."""

    _authorized(request, x_rci_admin_token)
    repository = _repository(request)
    try:
        current = await repository.get(study_id)
        plan = {
            **current.query_plan,
            "target_terms": sorted(
                {value.strip().casefold() for value in request_body.target_terms}
            ),
            "exclusion_terms": sorted(
                {
                    value.strip().casefold()
                    for value in request_body.exclusion_terms
                    if value.strip()
                }
            ),
            "source": "human_refined_post_search",
            "rationale": request_body.rationale,
            "revision": int(current.query_plan["revision"]) + 1,
        }
        checksum = canonical_checksum(plan)
        return await repository.revise_profile_scope(
            study_id,
            query_plan=plan,
            checksum=checksum,
            actor=_actor(x_rci_actor),
        )
    except StudyNotFoundError as exc:
        raise _not_found(exc) from exc
    except (StudyStateError, IntegrityError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{study_id}/search-estimate", response_model=StudyResponse)
async def estimate_search(
    study_id: str,
    request: Request,
    x_rci_actor: Annotated[str | None, Header(alias="X-RCI-Actor")] = None,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> StudyRecord:
    _authorized(request, x_rci_admin_token)
    repository = _repository(request)
    try:
        study = await repository.get(study_id)
        collection_service = get_collection_service(request)
        resolution = await collection_service.resolve_geography(
            dict(study.intake["geography_request"])
        )
        config = _study_collection_config(
            study,
            resolution_id=resolution.id,
            resolution_checksum=resolution.checksum,
        )
        estimate = await collection_service.create_scope_estimate(config)
        return await repository.record_search_estimate(
            study_id,
            geography_resolution_id=resolution.id,
            estimate_id=estimate.id,
            estimated_credits=estimate.estimate.estimated_total_credits,
            actor=_actor(x_rci_actor),
        )
    except StudyNotFoundError as exc:
        raise _not_found(exc) from exc
    except (StudyStateError, ContractError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{study_id}/search-launch", response_model=StudyResponse)
async def launch_search(
    study_id: str,
    request_body: ApproveSearchRequest,
    request: Request,
    x_rci_actor: Annotated[str | None, Header(alias="X-RCI-Actor")] = None,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> StudyRecord:
    _authorized(request, x_rci_admin_token)
    repository = _repository(request)
    study = await repository.get(study_id)
    if request_body.query_plan_checksum != study.query_plan_checksum:
        raise HTTPException(status_code=409, detail="Query plan changed; estimate again")
    if request_body.estimate_id != study.search_scope_estimate_id:
        raise HTTPException(status_code=409, detail="Search estimate is not current")
    resolution = await get_collection_service(request).get_geography_resolution(
        str(study.geography_resolution_id)
    )
    config = _study_collection_config(
        study,
        resolution_id=resolution.id,
        resolution_checksum=resolution.checksum,
    )
    try:
        run = await get_collection_service(request).launch_approved(
            config, request_body.estimate_id
        )
        return await repository.record_search_launch(
            study_id,
            collection_run_id=run.id,
            approved_by=_actor(x_rci_actor),
        )
    except (StudyStateError, ValueError, ContractError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{study_id}/products")
async def list_study_products(
    study_id: str,
    request: Request,
    admission_status: str | None = Query(default=None),
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> list[dict[str, Any]]:
    _authorized(request, x_rci_admin_token)
    try:
        return await _repository(request).list_products(
            study_id,
            admission_status=admission_status,
        )
    except StudyNotFoundError as exc:
        raise _not_found(exc) from exc


@router.get("/{study_id}/pdp-audit")
async def get_pdp_audit(
    study_id: str,
    request: Request,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> dict[str, Any]:
    _authorized(request, x_rci_admin_token)
    try:
        study = await _repository(request).get(study_id)
    except StudyNotFoundError as exc:
        raise _not_found(exc) from exc
    if study.pdp_run_id is None:
        raise HTTPException(status_code=404, detail="Study has no PDP enrichment run")
    product_repository = PostgresProductDetailRepository(
        request.app.state.database_probe.engine,
        _root(),
    )
    audit = await product_repository.run_audit(study.pdp_run_id)
    if audit is None:
        raise HTTPException(status_code=404, detail="PDP enrichment run was not found")
    return audit


@router.patch("/{study_id}/products", response_model=StudyResponse)
async def update_study_product(
    study_id: str,
    request_body: UpdateProductDispositionRequest,
    request: Request,
    x_rci_actor: Annotated[str | None, Header(alias="X-RCI-Actor")] = None,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> StudyRecord:
    _authorized(request, x_rci_admin_token)
    try:
        return await _repository(request).update_product_disposition(
            study_id,
            retailer_id=request_body.retailer_id,
            retailer_product_id=request_body.retailer_product_id,
            admission_status=request_body.admission_status,
            reason=request_body.reason,
            actor=_actor(x_rci_actor),
        )
    except StudyNotFoundError as exc:
        raise _not_found(exc) from exc
    except StudyStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _pdp_plan(products: list[dict[str, Any]], root: Path) -> tuple[dict[str, Any], list[Any]]:
    catalog = ProductDetailCatalog.from_path(root)
    calls: list[dict[str, Any]] = []
    invalid: list[dict[str, str]] = []
    for product in products:
        if product["admission_status"] != "provisionally_admitted":
            continue
        try:
            endpoint = catalog.get(str(product["retailer_id"]))
        except ValueError as exc:
            invalid.append({"product_id": str(product["retailer_product_id"]), "reason": str(exc)})
            continue
        for context in product["price_contexts"]:
            request_context = ProductDetailRequestContext(
                product_id=str(product["retailer_product_id"]),
                zipcode=context.get("zipcode"),
                store=context.get("store_number"),
                fulfillment_type=(
                    context.get("fulfillment_type")
                    or ("pickup" if product["retailer_id"] in {"walmart_us", "aldi_us"} else None)
                ),
                url=product.get("url"),
            )
            try:
                MetricsCartProductDetailAdapter(endpoint).build_request(request_context)
            except ValueError as exc:
                invalid.append(
                    {
                        "product_id": str(product["retailer_product_id"]),
                        "reason": str(exc),
                    }
                )
                continue
            parameters = request_context.parameters()
            calls.append(
                {
                    "retailer_id": product["retailer_id"],
                    "retailer_product_id": product["retailer_product_id"],
                    "title": product["title"],
                    "brand": product.get("brand"),
                    "url": product.get("url"),
                    "image_url": product.get("image_url"),
                    "identifiers": product.get("identifiers", {}),
                    "source_artifact_ids": product.get("source_artifact_ids", []),
                    "request_context": parameters,
                    "endpoint": endpoint,
                }
            )
    estimate = {
        "eligible_products": len(
            {(call["retailer_id"], call["retailer_product_id"]) for call in calls}
        ),
        "planned_calls": len(calls),
        "estimated_credits": sum(call["endpoint"].credits_per_successful_page for call in calls),
        "credits_by_retailer": dict(
            Counter(
                {
                    retailer_id: sum(
                        call["endpoint"].credits_per_successful_page
                        for call in calls
                        if call["retailer_id"] == retailer_id
                    )
                    for retailer_id in {call["retailer_id"] for call in calls}
                }
            )
        ),
        "invalid_candidates": invalid,
        "policy": "one_context_per_product_plus_distinct_search_price_states",
    }
    return estimate, calls


@router.post("/{study_id}/pdp-estimate", response_model=StudyResponse)
async def estimate_pdp(
    study_id: str,
    request: Request,
    x_rci_actor: Annotated[str | None, Header(alias="X-RCI-Actor")] = None,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> StudyRecord:
    _authorized(request, x_rci_admin_token)
    repository = _repository(request)
    products = await repository.list_products(study_id)
    estimate, calls = _pdp_plan(products, _root())
    if estimate["invalid_candidates"]:
        examples = "; ".join(
            f"{item['product_id']}: {item['reason']}" for item in estimate["invalid_candidates"][:5]
        )
        raise HTTPException(
            status_code=422,
            detail=(
                "Every admitted product must have a valid PDP request context. "
                f"Review or exclude the invalid candidates first: {examples}"
            ),
        )
    if not calls:
        raise HTTPException(status_code=422, detail="No PDP-ready admitted products were found")
    checksum = canonical_checksum(
        {
            "study_id": study_id,
            "calls": [
                {
                    **{key: value for key, value in call.items() if key != "endpoint"},
                    "endpoint_id": call["endpoint"].endpoint_id,
                }
                for call in calls
            ],
        }
    )
    estimate["plan_checksum"] = checksum
    try:
        return await repository.record_pdp_estimate(
            study_id,
            estimate=estimate,
            checksum=checksum,
            actor=_actor(x_rci_actor),
        )
    except StudyStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{study_id}/pdp-launch", response_model=StudyResponse)
async def launch_pdp(
    study_id: str,
    request_body: ApprovePdpRequest,
    request: Request,
    x_rci_actor: Annotated[str | None, Header(alias="X-RCI-Actor")] = None,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> StudyRecord:
    _authorized(request, x_rci_admin_token)
    repository = _repository(request)
    study = await repository.get(study_id)
    if request_body.plan_checksum != study.pdp_plan_checksum:
        raise HTTPException(status_code=409, detail="PDP plan changed; estimate again")
    if not study.pdp_estimate or request_body.max_credits < int(
        study.pdp_estimate["estimated_credits"]
    ):
        raise HTTPException(status_code=409, detail="PDP credit ceiling is below the estimate")
    products = await repository.list_products(study_id)
    _estimate, calls = _pdp_plan(products, _root())
    product_repository = PostgresProductDetailRepository(
        request.app.state.database_probe.engine,
        _root(),
    )
    run = await product_repository.create_run(
        max_credits=request_body.max_credits,
        active=False,
    )
    try:
        for call in calls:
            context_document = dict(call["request_context"])
            context = ProductDetailRequestContext(
                product_id=str(context_document["product_id"]),
                zipcode=context_document.get("zipcode"),
                store=context_document.get("store"),
                fulfillment_type=context_document.get("fulfillment_type"),
                url=context_document.get("url"),
            )
            product = await product_repository.upsert_serp_product(
                retailer_id=str(call["retailer_id"]),
                retailer_product_id=str(call["retailer_product_id"]),
                name=str(call["title"]),
                brand=call.get("brand"),
                url=str(call.get("url") or ""),
                image_primary=call.get("image_url"),
                identifiers=dict(call["identifiers"]),
                context={
                    "source": "study_discovery_admitted_product",
                    "study_id": study_id,
                    "source_artifact_id": next(iter(call["source_artifact_ids"]), None),
                    **context_document,
                },
            )
            await product_repository.enqueue(run.id, product, call["endpoint"], context)
        launched = await repository.record_pdp_launch(
            study_id,
            pdp_run_id=run.id,
            approved_by=_actor(x_rci_actor),
        )
    except Exception:
        await product_repository.cancel_run(run.id)
        raise
    # A run whose every request was served from the durable cache has no jobs for a
    # worker to finish. Reconcile it explicitly so discovery can advance immediately.
    await product_repository.reconcile_run(run.id)
    if await repository.reconcile_enrichment():
        return await repository.get(study_id)
    return launched


@router.post("/{study_id}/product-pack-draft", response_model=StudyResponse)
async def create_product_pack_draft(
    study_id: str,
    request_body: CreateDraftRequest,
    request: Request,
    x_rci_actor: Annotated[str | None, Header(alias="X-RCI-Actor")] = None,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> StudyRecord:
    _authorized(request, x_rci_admin_token)
    repository = _repository(request)
    study = await repository.get(study_id)
    if study.product_pack_draft_id:
        return study
    if not study.pdp_run_id:
        raise HTTPException(
            status_code=409,
            detail="Complete approved PDP enrichment before creating a Product Pack draft",
        )
    product_repository = PostgresProductDetailRepository(
        request.app.state.database_probe.engine,
        _root(),
    )
    pdp_run = await product_repository.get_run(study.pdp_run_id)
    if pdp_run is None or pdp_run.status not in {"completed", "completed_with_errors"}:
        raise HTTPException(
            status_code=409,
            detail="PDP enrichment is not complete",
        )
    inferred_pack_id, inferred_name = _category_identity(study)
    pack_id = request_body.product_pack_id or inferred_pack_id
    active_pack = await _active_category_pack(request, pack_id=pack_id)
    name = request_body.name or (active_pack.name if active_pack else inferred_name)
    category_family = request_body.category_family or (
        str(active_pack.document["category_family"]) if active_pack else inferred_name.casefold()
    )
    proposed_version = (
        _next_patch_version(active_pack.version)
        if active_pack and request_body.proposed_version == "1.0.0"
        else request_body.proposed_version
    )
    if active_pack:
        config = json.loads(json.dumps(active_pack.document))
        blueprint = json.loads(json.dumps(active_pack.report_blueprint))
        config.update(
            {
                "id": pack_id,
                "name": name,
                "version": proposed_version,
                "category_family": category_family,
            }
        )
        blueprint["version"] = proposed_version
        blueprint["product_pack"] = {"id": pack_id, "version": proposed_version}
        config["reporting"]["report_blueprint"]["version"] = proposed_version
    else:
        starter_request = CreateProductPackDraftRequest(
            product_pack_id=pack_id,
            name=name,
            proposed_version=proposed_version,
            category_family=category_family,
            default_keyword=str(study.query_plan["keyword"]),
        )
        config, blueprint = _starter_documents(_root(), starter_request)
    config["scope"]["target_terms"] = sorted(
        {
            *(str(value) for value in config["scope"].get("target_terms", [])),
            *(str(value) for value in study.query_plan["target_terms"]),
        }
    )
    config["scope"]["exclude"] = sorted(
        {
            *(str(value) for value in config["scope"].get("exclude", [])),
            *(str(value) for value in study.query_plan["exclusion_terms"]),
        }
    )
    if not active_pack:
        config["scope"]["hard_exclusion_patterns"] = list(study.query_plan["exclusion_terms"])
    config["description"] = (
        "Evidence-informed draft from governed study discovery. Attribute hypotheses and "
        "matching lenses require human review and certification before publication."
    )
    config["regression"]["golden_dataset_ids"] = sorted(
        {
            *(str(value) for value in config["regression"].get("golden_dataset_ids", [])),
            f"study:{study_id}",
        }
    )
    authoring_repository = PostgresProductPackAuthoringRepository(
        request.app.state.database_probe.engine
    )
    try:
        draft = await authoring_repository.create_draft(
            product_pack_id=pack_id,
            proposed_version=proposed_version,
            config=config,
            report_blueprint=blueprint,
            actor=_actor(x_rci_actor),
            base_version=active_pack.version if active_pack else None,
        )
    except IntegrityError as exc:
        existing = await authoring_repository.find_draft(
            pack_id,
            proposed_version,
        )
        if existing is None or existing.checksum != draft_checksum(config, blueprint):
            raise HTTPException(
                status_code=409,
                detail="Product Pack version already exists with different content",
            ) from exc
        draft = existing
    products = await repository.list_products(study_id)
    evidence_document = {
        "study_id": study_id,
        "collection_run_id": study.collection_run_id,
        "pdp_run_id": study.pdp_run_id,
        "query_plan": study.query_plan,
        "query_plan_checksum": study.query_plan_checksum,
        "profile_summary": study.profile_summary,
        "products": products,
    }
    evidence_checksum = canonical_checksum(evidence_document)
    evidence_bytes = json.dumps(
        evidence_document,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    await authoring_repository.add_evidence(
        draft.id,
        kind="classification",
        label=f"Study discovery population · {study.name}",
        storage_uri=f"study://{study_id}/population/{evidence_checksum}",
        content_type="application/json",
        checksum=evidence_checksum,
        byte_size=len(evidence_bytes),
        row_count=len(products),
        metadata={
            "study_id": study_id,
            "collection_run_id": study.collection_run_id,
            "pdp_run_id": study.pdp_run_id,
            "source_authority": {
                "price_and_location": "search",
                "identity_and_attributes": "pdp",
            },
            "pdp_run_status": pdp_run.status,
        },
        actor=_actor(x_rci_actor),
    )
    pdp_audit = await product_repository.run_audit(study.pdp_run_id)
    if pdp_audit is not None:
        pdp_evidence_document = {
            "study_id": study_id,
            "pdp_run_id": study.pdp_run_id,
            "status": pdp_audit["status"],
            "actual_credits": pdp_audit["actual_credits"],
            "calls": [
                {
                    "retailer_id": call["retailer_id"],
                    "retailer_product_id": call["retailer_product_id"],
                    "product_name": call["product_name"],
                    "evidence_status": (
                        "pdp_enriched" if call["status"] == "succeeded" else "pdp_unavailable"
                    ),
                    "http_status": call["http_status"],
                    "request_context": call["request_context"],
                    "snapshot_id": call["snapshot_id"],
                    "identity_evidence": call["identity_evidence"],
                }
                for call in pdp_audit["calls"]
            ],
        }
        pdp_evidence_checksum = canonical_checksum(pdp_evidence_document)
        pdp_evidence_bytes = json.dumps(
            pdp_evidence_document,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        await authoring_repository.add_evidence(
            draft.id,
            kind="pdp",
            label=f"PDP identity outcomes · {study.name}",
            storage_uri=f"study://{study_id}/pdp/{pdp_evidence_checksum}",
            content_type="application/json",
            checksum=pdp_evidence_checksum,
            byte_size=len(pdp_evidence_bytes),
            row_count=len(pdp_audit["calls"]),
            metadata={
                "study_id": study_id,
                "pdp_run_id": study.pdp_run_id,
                "succeeded_calls": pdp_audit["succeeded_calls"],
                "failed_calls": pdp_audit["failed_calls"],
                "actual_credits": pdp_audit["actual_credits"],
                "identity_fallback": "search",
            },
            actor=_actor(x_rci_actor),
        )
    return await repository.link_draft(study_id, draft.id, _actor(x_rci_actor))


@router.post("/{study_id}/product-pack-draft/regenerate", response_model=StudyResponse)
async def regenerate_product_pack_draft(
    study_id: str,
    request_body: CreateDraftRequest,
    request: Request,
    x_rci_actor: Annotated[str | None, Header(alias="X-RCI-Actor")] = None,
    x_rci_admin_token: Annotated[str | None, Header(alias="X-RCI-Admin-Token")] = None,
) -> StudyRecord:
    _authorized(request, x_rci_admin_token)
    repository = _repository(request)
    study = await repository.get(study_id)
    if study.product_pack_draft_id is None:
        return await create_product_pack_draft(
            study_id, request_body, request, x_rci_actor, x_rci_admin_token
        )
    authoring_repository = PostgresProductPackAuthoringRepository(
        request.app.state.database_probe.engine
    )
    await repository.reopen_draft_handoff(study_id, _actor(x_rci_actor))
    try:
        replacement = await create_product_pack_draft(
            study_id, request_body, request, x_rci_actor, x_rci_admin_token
        )
    except Exception as exc:
        await repository.link_draft(study_id, study.product_pack_draft_id, _actor(x_rci_actor))
        raise HTTPException(
            status_code=409,
            detail=f"The replacement Product Pack draft could not be created: {exc}",
        ) from exc
    await authoring_repository.abandon_draft(
        study.product_pack_draft_id,
        actor=_actor(x_rci_actor),
        reason="Superseded by regenerated study evidence handoff",
    )
    return replacement
