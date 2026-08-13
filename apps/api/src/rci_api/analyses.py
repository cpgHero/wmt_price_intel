"""Canonical analysis readers and immutable delivery-artifact APIs."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from rci_analytics import CatalogProductPackLoader
from rci_contracts import ContractError
from rci_product_packs import PostgresProductPackCatalog
from rci_results import (
    AnalysisResultService,
    AnalysisResultValidator,
    ArtifactRenderer,
    BrandDecisionCommand,
    BrandReviewService,
    BrandRevisionConflictError,
    MatchDecisionCommand,
    MatchOneToOneConflictError,
    MatchReviewService,
    MatchRevisionConflictError,
    PostgresBrandReviewRepository,
    PostgresMatchReviewRepository,
    PostgresResultsRepository,
    S3ReportObjectStore,
)
from rci_results.models import AnalysisRecord, DownloadLink, ReportArtifactRecord
from rci_results.service import (
    AnalysisNotFoundError,
    ArtifactNotFoundError,
    ProductEvidenceNotFoundError,
)
from rci_results.storage import ReportObjectStore, UnavailableReportObjectStore
from rci_retailer_packs import GovernedBrandResolver

router = APIRouter(prefix="/api/v1")


class AnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    analysis_run_id: str
    analysis_id: str
    collection_run_id: str
    status: str
    product_pack_id: str
    product_pack_version: str
    schema_version: str
    checksum: str
    result: dict[str, Any]
    created_at: datetime


class ArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    analysis_run_id: str
    publication_id: str | None
    artifact_type: str
    renderer_version: str
    content_type: str
    byte_size: int
    checksum: str
    status: str
    created_at: datetime


class DownloadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    artifact_id: str
    url: str
    expires_in_seconds: int


class MatchScopeRequest(BaseModel):
    mode: Literal["global", "observed_benchmark_product_footprint", "explicit_benchmark_locations"]
    relationship_role: Literal["primary", "alternative"]
    comparison_family_key: str = Field(min_length=1)
    definition: dict[str, Any]
    checksum: str = Field(pattern="^[a-f0-9]{64}$")
    artifact_id: str | None = None


class MatchDecisionRequest(BaseModel):
    expected_revision: int = Field(ge=0)
    competitor_retailer_id: str = Field(min_length=1)
    profile_id: str = Field(min_length=1)
    benchmark_product_id: str = Field(min_length=1)
    competitor_product_id: str = Field(min_length=1)
    decision: Literal["confirmed", "rejected", "reset"]
    replace_conflicts: bool = False
    reason: str | None = Field(default=None, max_length=1000)
    scope: MatchScopeRequest | None = None


class MatchRecomputeRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    apply_to_future_runs: bool


class BrandDecisionRequest(BaseModel):
    expected_revision: int = Field(ge=0)
    retailer_id: str = Field(min_length=1)
    normalized_brand: str = Field(min_length=1)
    role: Literal["private_label", "regional", "national", "unclassified"]
    decision: Literal["confirmed", "rejected", "reset"]
    canonical_brand_id: str | None = Field(default=None, min_length=1)
    reason: str | None = Field(default=None, max_length=1000)


class BrandRecomputeRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    apply_to_future_runs: bool


def _enabled(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_analysis_service(request: Request) -> AnalysisResultService:
    repository_root = Path(os.getenv("RCI_REPOSITORY_ROOT", Path.cwd())).resolve()
    bucket = os.getenv("OBJECT_STORAGE_BUCKET")
    object_store: ReportObjectStore
    if bucket:
        object_store = S3ReportObjectStore.create(
            bucket=bucket,
            endpoint_url=os.getenv("OBJECT_STORAGE_ENDPOINT"),
            region_name=os.getenv("OBJECT_STORAGE_REGION"),
            access_key_id=os.getenv("OBJECT_STORAGE_ACCESS_KEY_ID"),
            secret_access_key=os.getenv("OBJECT_STORAGE_SECRET_ACCESS_KEY"),
            force_path_style=_enabled(os.getenv("OBJECT_STORAGE_FORCE_PATH_STYLE"), default=True),
        )
    else:
        object_store = UnavailableReportObjectStore()
    return AnalysisResultService(
        PostgresResultsRepository(request.app.state.database_probe.engine),
        AnalysisResultValidator(repository_root),
        object_store,
        ArtifactRenderer(repository_root),
        PostgresProductPackCatalog(request.app.state.database_probe.engine),
    )


def get_match_review_service(request: Request) -> MatchReviewService:
    repository_root = Path(os.getenv("RCI_REPOSITORY_ROOT", Path.cwd())).resolve()
    catalog = json.loads((repository_root / "config" / "retailer-catalog.json").read_text())
    names = {
        str(row["id"]): str(row["display_name"])
        for row in catalog.get("retailers", [])
        if isinstance(row, dict) and row.get("id") and row.get("display_name")
    }
    return MatchReviewService(
        get_analysis_service(request),
        PostgresMatchReviewRepository(request.app.state.database_probe.engine),
        retailer_names=names,
    )


def get_brand_review_service(request: Request) -> BrandReviewService:
    repository_root = Path(os.getenv("RCI_REPOSITORY_ROOT", Path.cwd())).resolve()
    retailer_catalog = json.loads(
        (repository_root / "config" / "retailer-catalog.json").read_text()
    )
    names = {
        str(row["id"]): str(row["display_name"])
        for row in retailer_catalog.get("retailers", [])
        if isinstance(row, dict) and row.get("id") and row.get("display_name")
    }
    product_pack_catalog = PostgresProductPackCatalog(request.app.state.database_probe.engine)
    return BrandReviewService(
        get_analysis_service(request),
        PostgresBrandReviewRepository(request.app.state.database_probe.engine),
        CatalogProductPackLoader(repository_root, product_pack_catalog),
        retailer_names=names,
        brand_resolver=GovernedBrandResolver.from_repository(repository_root),
    )


AnalysisServiceDependency = Annotated[AnalysisResultService, Depends(get_analysis_service)]
MatchReviewServiceDependency = Annotated[MatchReviewService, Depends(get_match_review_service)]
BrandReviewServiceDependency = Annotated[BrandReviewService, Depends(get_brand_review_service)]
AnalysisBody = Annotated[dict[str, Any], Body()]


def _analysis_not_found(exc: AnalysisNotFoundError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post(
    "/collection-runs/{run_id}/analysis",
    response_model=AnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["analyses"],
)
async def publish_analysis(
    run_id: str,
    service: AnalysisServiceDependency,
    document: AnalysisBody,
) -> AnalysisRecord:
    try:
        return await service.publish(document, collection_run_id=run_id)
    except ContractError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get(
    "/collection-runs/{run_id}/analysis",
    response_model=AnalysisResponse,
    tags=["analyses"],
)
async def get_collection_run_analysis(
    run_id: str,
    service: AnalysisServiceDependency,
) -> AnalysisRecord:
    try:
        return await service.get_by_collection_run(run_id)
    except AnalysisNotFoundError as exc:
        raise _analysis_not_found(exc) from exc


@router.get("/analyses", response_model=list[AnalysisResponse], tags=["analyses"])
async def list_analyses(
    service: AnalysisServiceDependency,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[AnalysisRecord]:
    return await service.list_analyses(limit)


@router.get("/analyses/{analysis_id}", response_model=AnalysisResponse, tags=["analyses"])
async def get_analysis(
    analysis_id: str,
    service: AnalysisServiceDependency,
) -> AnalysisRecord:
    try:
        return await service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise _analysis_not_found(exc) from exc


@router.get("/analyses/{analysis_id}/matches", tags=["analyses"])
async def get_matches(
    analysis_id: str,
    service: AnalysisServiceDependency,
) -> dict[str, Any]:
    try:
        return await service.matches(analysis_id)
    except AnalysisNotFoundError as exc:
        raise _analysis_not_found(exc) from exc


@router.get("/analyses/{analysis_id}/match-review", tags=["analyses"])
async def get_match_review(
    analysis_id: str,
    service: MatchReviewServiceDependency,
) -> dict[str, Any]:
    try:
        return await service.view(analysis_id)
    except AnalysisNotFoundError as exc:
        raise _analysis_not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/analyses/{analysis_id}/match-review/decisions", tags=["analyses"])
async def save_match_decision(
    analysis_id: str,
    service: MatchReviewServiceDependency,
    command: MatchDecisionRequest,
    actor: Annotated[str | None, Header(alias="X-RCI-Actor")] = None,
) -> dict[str, Any]:
    try:
        return await service.decide(
            analysis_id,
            MatchDecisionCommand(**command.model_dump()),
            actor=actor or "interactive-user",
        )
    except AnalysisNotFoundError as exc:
        raise _analysis_not_found(exc) from exc
    except MatchOneToOneConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(exc), "conflicts": exc.conflicts},
        ) from exc
    except MatchRevisionConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.post("/analyses/{analysis_id}/match-review/recompute", tags=["analyses"])
async def recompute_match_review(
    analysis_id: str,
    service: MatchReviewServiceDependency,
    command: MatchRecomputeRequest,
    actor: Annotated[str | None, Header(alias="X-RCI-Actor")] = None,
) -> dict[str, Any]:
    try:
        result = await service.recompute(
            analysis_id,
            expected_revision=command.expected_revision,
            apply_to_future_runs=command.apply_to_future_runs,
            actor=actor or "interactive-user",
        )
        return {
            "analysis_run_id": result.analysis_run_id,
            "source_analysis_id": result.source_analysis_id,
            "match_revision_id": result.match_revision_id,
            "status": result.status,
            "applied_to_future_runs": result.applied_to_future_runs,
            "provider_calls_queued": 0,
        }
    except AnalysisNotFoundError as exc:
        raise _analysis_not_found(exc) from exc
    except (MatchRevisionConflictError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/analyses/{analysis_id}/brand-workbench", tags=["analyses"])
async def get_brand_workbench(
    analysis_id: str,
    service: BrandReviewServiceDependency,
) -> dict[str, Any]:
    try:
        return await service.view(analysis_id)
    except AnalysisNotFoundError as exc:
        raise _analysis_not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/analyses/{analysis_id}/brand-workbench/decisions", tags=["analyses"])
async def save_brand_decision(
    analysis_id: str,
    service: BrandReviewServiceDependency,
    command: BrandDecisionRequest,
    actor: Annotated[str | None, Header(alias="X-RCI-Actor")] = None,
) -> dict[str, Any]:
    try:
        return await service.decide(
            analysis_id,
            BrandDecisionCommand(**command.model_dump()),
            actor=actor or "interactive-user",
        )
    except AnalysisNotFoundError as exc:
        raise _analysis_not_found(exc) from exc
    except BrandRevisionConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.post("/analyses/{analysis_id}/brand-workbench/recompute", tags=["analyses"])
async def recompute_brand_workbench(
    analysis_id: str,
    service: BrandReviewServiceDependency,
    command: BrandRecomputeRequest,
    actor: Annotated[str | None, Header(alias="X-RCI-Actor")] = None,
) -> dict[str, Any]:
    try:
        result = await service.recompute(
            analysis_id,
            expected_revision=command.expected_revision,
            apply_to_future_runs=command.apply_to_future_runs,
            actor=actor or "interactive-user",
        )
        return {
            "analysis_run_id": result.analysis_run_id,
            "source_analysis_id": result.source_analysis_id,
            "brand_revision_id": result.brand_revision_id,
            "status": result.status,
            "applied_to_future_runs": result.applied_to_future_runs,
            "provider_calls_queued": 0,
        }
    except AnalysisNotFoundError as exc:
        raise _analysis_not_found(exc) from exc
    except (BrandRevisionConflictError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/analyses/{analysis_id}/quality", tags=["analyses"])
async def get_quality(
    analysis_id: str,
    service: AnalysisServiceDependency,
) -> dict[str, Any]:
    try:
        return await service.quality(analysis_id)
    except AnalysisNotFoundError as exc:
        raise _analysis_not_found(exc) from exc


@router.get("/analyses/{analysis_id}/report", tags=["analyses"])
async def get_report_view(
    analysis_id: str,
    service: AnalysisServiceDependency,
) -> dict[str, Any]:
    try:
        return await service.report_view(analysis_id)
    except AnalysisNotFoundError as exc:
        raise _analysis_not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get(
    "/analyses/{analysis_id}/product-decisions/{decision_id}/evidence",
    tags=["analyses"],
)
async def get_product_decision_evidence(
    analysis_id: str,
    decision_id: str,
    service: AnalysisServiceDependency,
) -> dict[str, Any]:
    try:
        return await service.product_evidence(analysis_id, decision_id)
    except AnalysisNotFoundError as exc:
        raise _analysis_not_found(exc) from exc
    except ProductEvidenceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/analyses/{analysis_id}/artifacts",
    response_model=list[ArtifactResponse],
    tags=["artifacts"],
)
async def list_artifacts(
    analysis_id: str,
    service: AnalysisServiceDependency,
) -> list[ReportArtifactRecord]:
    try:
        return await service.list_artifacts(analysis_id)
    except AnalysisNotFoundError as exc:
        raise _analysis_not_found(exc) from exc


@router.post(
    "/analyses/{analysis_id}/artifacts/{artifact_type}",
    response_model=ArtifactResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["artifacts"],
)
async def generate_artifact(
    analysis_id: str,
    artifact_type: Literal["html", "xlsx", "leadership_email", "audit_zip"],
    service: AnalysisServiceDependency,
) -> ReportArtifactRecord:
    try:
        return await service.generate_artifact(analysis_id, artifact_type)
    except AnalysisNotFoundError as exc:
        raise _analysis_not_found(exc) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc


@router.get(
    "/artifacts/{artifact_id}/download",
    response_model=DownloadResponse,
    tags=["artifacts"],
)
async def download_artifact(
    artifact_id: str,
    service: AnalysisServiceDependency,
) -> DownloadLink:
    try:
        return await service.download_link(artifact_id)
    except ArtifactNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
