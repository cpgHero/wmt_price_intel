"""Read-only inspection of Matching Architecture v2 shadow artifacts."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Annotated, Any, Protocol

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

router = APIRouter(prefix="/api/v1", tags=["matching-v2"])


def _enabled(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class MatchingV2ShadowArtifact:
    retailer_id: str
    storage_uri: str
    checksum: str
    created_at: str


class MatchingV2ShadowRepository(Protocol):
    async def artifacts(self, analysis_id: str) -> list[MatchingV2ShadowArtifact]: ...


class MatchingV2ShadowReader(Protocol):
    async def read(self, artifact: MatchingV2ShadowArtifact) -> dict[str, Any]: ...


class PostgresMatchingV2ShadowRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def artifacts(self, analysis_id: str) -> list[MatchingV2ShadowArtifact]:
        statement = text(
            """
            SELECT coalesce(da.metadata->>'retailer_id', '') AS retailer_id,
                   da.storage_uri, da.checksum, da.created_at
            FROM analysis_result result
            JOIN analysis_run run ON run.id = result.analysis_run_id
            JOIN dataset_artifact da ON da.collection_run_id = run.collection_run_id
            WHERE result.analysis_id = :analysis_id
              AND da.artifact_type = 'matching_v2_shadow'
            ORDER BY da.created_at, da.storage_uri
            """
        )
        async with self._engine.connect() as connection:
            rows = (await connection.execute(statement, {"analysis_id": analysis_id})).mappings()
            return [
                MatchingV2ShadowArtifact(
                    retailer_id=str(row["retailer_id"]),
                    storage_uri=str(row["storage_uri"]),
                    checksum=str(row["checksum"]),
                    created_at=row["created_at"].isoformat(),
                )
                for row in rows
            ]


class S3MatchingV2ShadowReader:
    def __init__(self, *, bucket: str, client: Any) -> None:
        self._bucket = bucket
        self._client = client

    @classmethod
    def from_environment(cls) -> S3MatchingV2ShadowReader:
        import boto3  # type: ignore[import-untyped]
        from botocore.config import Config  # type: ignore[import-untyped]

        bucket = os.getenv("OBJECT_STORAGE_BUCKET", "").strip()
        if not bucket:
            raise RuntimeError("object storage is not configured")
        force_path = _enabled(os.getenv("OBJECT_STORAGE_FORCE_PATH_STYLE"), default=True)
        client = boto3.client(
            "s3",
            endpoint_url=os.getenv("OBJECT_STORAGE_ENDPOINT") or None,
            region_name=os.getenv("OBJECT_STORAGE_REGION") or None,
            aws_access_key_id=os.getenv("OBJECT_STORAGE_ACCESS_KEY_ID") or None,
            aws_secret_access_key=os.getenv("OBJECT_STORAGE_SECRET_ACCESS_KEY") or None,
            config=Config(s3={"addressing_style": "path" if force_path else "virtual"}),
        )
        return cls(bucket=bucket, client=client)

    async def read(self, artifact: MatchingV2ShadowArtifact) -> dict[str, Any]:
        prefix = f"s3://{self._bucket}/"
        if not artifact.storage_uri.startswith(prefix):
            raise ValueError("matching v2 artifact belongs to a different bucket")
        key = artifact.storage_uri.removeprefix(prefix)

        def download() -> bytes:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
            return bytes(response["Body"].read())

        body = await asyncio.to_thread(download)
        document = json.loads(body)
        if not isinstance(document, dict):
            raise ValueError("matching v2 artifact is not a JSON object")
        return document


class MatchingV2ShadowService:
    def __init__(
        self,
        repository: MatchingV2ShadowRepository,
        reader: MatchingV2ShadowReader,
    ) -> None:
        self._repository = repository
        self._reader = reader

    async def view(
        self,
        analysis_id: str,
        *,
        competitor_retailer_id: str | None,
        tier: str | None,
        match_status: str | None,
        benchmark_product_id: str | None,
        competitor_product_id: str | None,
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        artifacts = await self._repository.artifacts(analysis_id)
        if competitor_retailer_id is not None:
            artifacts = [
                artifact for artifact in artifacts if artifact.retailer_id == competitor_retailer_id
            ]
        documents = [await self._reader.read(artifact) for artifact in artifacts]
        edges = [
            edge
            for document in documents
            for edge in document.get("edges", [])
            if isinstance(edge, dict)
            and (tier is None or edge.get("tier") == tier)
            and (match_status is None or edge.get("status") == match_status)
            and (
                benchmark_product_id is None
                or str(edge.get("benchmark_listing_id", "")).endswith(f":{benchmark_product_id}")
            )
            and (
                competitor_product_id is None
                or str(edge.get("competitor_listing_id", "")).endswith(f":{competitor_product_id}")
            )
        ]
        edges.sort(
            key=lambda edge: (
                str(edge.get("benchmark_listing_id", "")),
                str(edge.get("competitor_listing_id", "")),
                str(edge.get("edge_id", "")),
            )
        )
        return {
            "schema_version": "2.0.0-shadow-view",
            "analysis_id": analysis_id,
            "authoritative": False,
            "report_metrics_affected": False,
            "artifacts": [
                {
                    "retailer_id": artifact.retailer_id,
                    "checksum": artifact.checksum,
                    "created_at": artifact.created_at,
                    "summary": {key: value for key, value in document.items() if key != "edges"},
                }
                for artifact, document in zip(artifacts, documents, strict=True)
            ],
            "filters": {
                "competitor_retailer_id": competitor_retailer_id,
                "tier": tier,
                "status": match_status,
                "benchmark_product_id": benchmark_product_id,
                "competitor_product_id": competitor_product_id,
            },
            "total_edges": len(edges),
            "offset": offset,
            "limit": limit,
            "edges": edges[offset : offset + limit],
        }


def get_matching_v2_shadow_service(request: Request) -> MatchingV2ShadowService:
    if not _enabled(os.getenv("MATCHING_V2_SHADOW_API_ENABLED"), default=False):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Matching v2 shadow inspection is not enabled.",
        )
    try:
        reader = S3MatchingV2ShadowReader.from_environment()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return MatchingV2ShadowService(
        PostgresMatchingV2ShadowRepository(request.app.state.database_probe.engine),
        reader,
    )


MatchingV2ShadowServiceDependency = Annotated[
    MatchingV2ShadowService,
    Depends(get_matching_v2_shadow_service),
]


@router.get("/analyses/{analysis_id}/matching-v2-shadow")
async def get_matching_v2_shadow(
    analysis_id: str,
    service: MatchingV2ShadowServiceDependency,
    competitor_retailer_id: str | None = Query(default=None),
    tier: str | None = Query(default=None),
    match_status: str | None = Query(default=None, alias="status"),
    benchmark_product_id: str | None = Query(default=None),
    competitor_product_id: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    return await service.view(
        analysis_id,
        competitor_retailer_id=competitor_retailer_id,
        tier=tier,
        match_status=match_status,
        benchmark_product_id=benchmark_product_id,
        competitor_product_id=competitor_product_id,
        offset=offset,
        limit=limit,
    )
