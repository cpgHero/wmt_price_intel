"""Canonical analysis readers and immutable delivery-artifact APIs."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict

from rci_contracts import ContractError
from rci_results import (
    AnalysisResultService,
    AnalysisResultValidator,
    PostgresResultsRepository,
    S3ReportObjectStore,
)
from rci_results.models import AnalysisRecord, DownloadLink, ReportArtifactRecord
from rci_results.service import AnalysisNotFoundError, ArtifactNotFoundError
from rci_results.storage import ReportObjectStore, UnavailableReportObjectStore

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
    artifact_type: str
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
    )


AnalysisServiceDependency = Annotated[AnalysisResultService, Depends(get_analysis_service)]
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


@router.get("/analyses/{analysis_id}/quality", tags=["analyses"])
async def get_quality(
    analysis_id: str,
    service: AnalysisServiceDependency,
) -> dict[str, Any]:
    try:
        return await service.quality(analysis_id)
    except AnalysisNotFoundError as exc:
        raise _analysis_not_found(exc) from exc


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
