"""Search-authoritative retailer price-monitoring read model and API."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Annotated, Any, Literal

import polars as pl
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from rci_analytics import (
    CatalogProductPackLoader,
    PriceMonitoringFilters,
    PriceMonitoringProjector,
    classified_offer_from_record,
)
from rci_api.analyses import get_analysis_service
from rci_contracts import validate_instance
from rci_product_packs import PostgresProductPackCatalog
from rci_results import AnalysisResultService
from rci_results.service import AnalysisNotFoundError
from rci_retailer_packs import BrandDecisionOverride, GovernedBrandResolver

router = APIRouter(prefix="/api/v1", tags=["price-monitoring"])
BrandFilter = Literal["all", "private_label", "regional", "national", "unclassified"]


@dataclass(frozen=True, slots=True)
class ClassifiedArtifact:
    storage_uri: str
    checksum: str
    row_count: int


class S3ParquetReader:
    def __init__(self, *, bucket: str, client: Any) -> None:
        self._bucket = bucket
        self._client = client
        self._cache: dict[str, list[dict[str, Any]]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    @classmethod
    def from_environment(cls) -> S3ParquetReader:
        import boto3  # type: ignore[import-untyped]
        from botocore.config import Config  # type: ignore[import-untyped]

        bucket = os.getenv("OBJECT_STORAGE_BUCKET", "").strip()
        if not bucket:
            raise RuntimeError("object storage is not configured")
        force_path = os.getenv("OBJECT_STORAGE_FORCE_PATH_STYLE", "true").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        client = boto3.client(
            "s3",
            endpoint_url=os.getenv("OBJECT_STORAGE_ENDPOINT") or None,
            region_name=os.getenv("OBJECT_STORAGE_REGION") or None,
            aws_access_key_id=os.getenv("OBJECT_STORAGE_ACCESS_KEY_ID") or None,
            aws_secret_access_key=os.getenv("OBJECT_STORAGE_SECRET_ACCESS_KEY") or None,
            config=Config(s3={"addressing_style": "path" if force_path else "virtual"}),
        )
        return cls(bucket=bucket, client=client)

    async def read(self, artifact: ClassifiedArtifact) -> list[dict[str, Any]]:
        cached = self._cache.get(artifact.checksum)
        if cached is not None:
            return cached
        lock = self._locks.setdefault(artifact.checksum, asyncio.Lock())
        async with lock:
            cached = self._cache.get(artifact.checksum)
            if cached is not None:
                return cached
            rows = await self._download(artifact)
            if len(self._cache) >= 3:
                self._cache.pop(next(iter(self._cache)))
            self._cache[artifact.checksum] = rows
            return rows

    async def _download(self, artifact: ClassifiedArtifact) -> list[dict[str, Any]]:
        prefix = f"s3://{self._bucket}/"
        if not artifact.storage_uri.startswith(prefix):
            raise ValueError("classified dataset belongs to a different object-storage bucket")
        key = artifact.storage_uri.removeprefix(prefix)

        def download() -> bytes:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
            return bytes(response["Body"].read())

        body = await asyncio.to_thread(download)
        if hashlib.sha256(body).hexdigest() != artifact.checksum:
            raise ValueError(f"classified dataset checksum mismatch for {artifact.storage_uri}")
        columns = [
            "offer_id",
            "retailer_id",
            "retailer_product_id",
            "title",
            "brand",
            "price",
            "currency",
            "zipcode",
            "store_number",
            "latitude",
            "longitude",
            "in_stock",
            "product_url",
            "image_url",
            "collected_at",
            "in_scope",
            "scope_reason",
            "attributes_json",
        ]
        frame = await asyncio.to_thread(
            pl.read_parquet,
            BytesIO(body),
            columns=columns,
        )
        return frame.to_dicts()


class PostgresPriceMonitoringRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def artifacts(self, collection_run_id: str, retailer_id: str) -> list[ClassifiedArtifact]:
        statement = text(
            """
            SELECT storage_uri, checksum, coalesce(row_count, 0)::integer AS row_count
            FROM dataset_artifact
            WHERE collection_run_id::text = :collection_run_id
              AND artifact_type = 'classified_offers'
              AND metadata->>'retailer_id' = :retailer_id
            ORDER BY coalesce((metadata->>'partition')::integer, 0), created_at
            """
        )
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    statement,
                    {"collection_run_id": collection_run_id, "retailer_id": retailer_id},
                )
            ).mappings()
            return [ClassifiedArtifact(**dict(row)) for row in rows]

    async def source_rows(self, collection_run_id: str, retailer_id: str) -> int:
        statement = text(
            """
            SELECT coalesce(sum(aia.row_count), 0)::bigint
            FROM analysis_input_set ais
            JOIN analysis_input_artifact aia ON aia.input_set_id = ais.id
            WHERE ais.collection_run_id::text = :collection_run_id
              AND aia.retailer_id = :retailer_id
            """
        )
        async with self._engine.connect() as connection:
            value = await connection.scalar(
                statement,
                {"collection_run_id": collection_run_id, "retailer_id": retailer_id},
            )
            return int(value or 0)

    async def location_context(
        self,
        collection_run_id: str,
        retailer_id: str,
    ) -> tuple[dict[tuple[str, str], dict[str, Any]], int]:
        locations = text(
            """
            SELECT retailer_id, store_number, store_name, zipcode, city, state, country,
                   latitude, longitude
            FROM retailer_location
            WHERE retailer_id = :retailer_id
            """
        )
        planned = text(
            """
            SELECT count(DISTINCT location_scope_key)::integer
            FROM collection_task
            WHERE collection_run_id::text = :collection_run_id
              AND retailer_id = :retailer_id
            """
        )
        zip_geography = text(
            """
            SELECT zipcode, min(city) AS city, min(state) AS state, min(country) AS country,
                   avg(latitude) AS latitude, avg(longitude) AS longitude
            FROM retailer_location
            WHERE zipcode IS NOT NULL
            GROUP BY zipcode
            """
        )
        async with self._engine.connect() as connection:
            rows = (await connection.execute(locations, {"retailer_id": retailer_id})).mappings()
            index = {(str(row["retailer_id"]), str(row["store_number"])): dict(row) for row in rows}
            if retailer_id == "amazon_us_same_day":
                zip_rows = (await connection.execute(zip_geography)).mappings()
                index.update(
                    {
                        (retailer_id, f"zip:{row['zipcode']}"): {
                            **dict(row),
                            "store_name": None,
                        }
                        for row in zip_rows
                    }
                )
            planned_count = int(
                await connection.scalar(
                    planned,
                    {"collection_run_id": collection_run_id, "retailer_id": retailer_id},
                )
                or 0
            )
        return index, planned_count

    async def product_context(
        self,
        retailer_id: str,
        product_ids: list[str],
    ) -> dict[str, dict[str, Any]]:
        if not product_ids:
            return {}
        statement = text(
            """
            SELECT retailer_id, retailer_product_id, identity
            FROM canonical_product
            WHERE retailer_id = :retailer_id
              AND retailer_product_id = ANY(CAST(:product_ids AS text[]))
            """
        )
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    statement,
                    {"retailer_id": retailer_id, "product_ids": product_ids},
                )
            ).mappings()
            context: dict[str, dict[str, Any]] = {}
            for row in rows:
                identity = dict(row["identity"])
                context[f"{row['retailer_id']}:{row['retailer_product_id']}"] = {
                    "name": identity.get("name"),
                    "brand": identity.get("brand"),
                    "image_url": identity.get("image_primary"),
                    "url": identity.get("url"),
                }
            return context

    async def brand_overrides(
        self,
        *,
        revision_id: str | None,
        product_pack_id: str,
        product_pack_version: str,
        benchmark_retailer_id: str,
    ) -> list[BrandDecisionOverride]:
        statement = text(
            """
            WITH selected AS (
              SELECT id
              FROM brand_classification_revision
              WHERE (
                (:revision_id IS NOT NULL AND id::text = :revision_id)
                OR (
                  :revision_id IS NULL
                  AND product_pack_id = :product_pack_id
                  AND product_pack_version = :product_pack_version
                  AND benchmark_retailer_id = :benchmark_retailer_id
                  AND status = 'current'
                )
              )
              ORDER BY revision DESC
              LIMIT 1
            )
            SELECT retailer_id, normalized_brand, display_brand, role, decision
            FROM brand_classification_rule
            WHERE revision_id = (SELECT id FROM selected)
            """
        )
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    statement,
                    {
                        "revision_id": revision_id,
                        "product_pack_id": product_pack_id,
                        "product_pack_version": product_pack_version,
                        "benchmark_retailer_id": benchmark_retailer_id,
                    },
                )
            ).mappings()
            return [BrandDecisionOverride(**dict(row)) for row in rows]


class PriceMonitoringService:
    def __init__(
        self,
        *,
        repository_root: Path,
        analysis_service: AnalysisResultService,
        repository: PostgresPriceMonitoringRepository,
        product_pack_loader: CatalogProductPackLoader,
        reader: S3ParquetReader,
    ) -> None:
        self._root = repository_root
        self._analyses = analysis_service
        self._repository = repository
        self._packs = product_pack_loader
        self._reader = reader
        catalog = json.loads((repository_root / "config" / "retailer-catalog.json").read_text())
        self._retailer_names = {
            str(row["id"]): str(row["display_name"])
            for row in catalog.get("retailers", [])
            if isinstance(row, dict) and row.get("id") and row.get("display_name")
        }

    async def view(self, analysis_id: str, filters: PriceMonitoringFilters) -> dict[str, Any]:
        if filters.city is not None and filters.state is None:
            raise ValueError("a city filter requires its state")
        analysis = await self._analyses.get(analysis_id)
        result = analysis.result
        benchmark = str(result["benchmark_retailer"])
        retailer_options = [benchmark, *(str(value) for value in result["competitors"])]
        if filters.retailer_id not in retailer_options:
            raise ValueError(f"retailer {filters.retailer_id!r} is not in this analysis")
        artifacts = await self._repository.artifacts(
            analysis.collection_run_id,
            filters.retailer_id,
        )
        if not artifacts:
            raise LookupError(
                f"classified Search evidence for {filters.retailer_id!r} is unavailable"
            )
        records: list[dict[str, Any]] = []
        for artifact in artifacts:
            records.extend(await self._reader.read(artifact))
        offers = [classified_offer_from_record(record) for record in records]
        product_ids = sorted(
            {
                offer.offer.retailer_product_id
                for offer in offers
                if offer.offer.retailer_id == filters.retailer_id and offer.in_scope
            }
        )
        location_index, expected_locations = await self._repository.location_context(
            analysis.collection_run_id,
            filters.retailer_id,
        )
        product_context = await self._repository.product_context(
            filters.retailer_id,
            product_ids,
        )
        source = result.get("source", {})
        revision_id = str(source["brand_revision_id"]) if source.get("brand_revision_id") else None
        overrides = await self._repository.brand_overrides(
            revision_id=revision_id,
            product_pack_id=analysis.product_pack_id,
            product_pack_version=analysis.product_pack_version,
            benchmark_retailer_id=benchmark,
        )
        resolver = GovernedBrandResolver.from_repository(self._root).with_overrides(overrides)
        pack = await self._packs.load(
            analysis.product_pack_id,
            analysis.product_pack_version,
        )
        view = PriceMonitoringProjector(
            pack,
            resolver,
            retailer_names=self._retailer_names,
        ).build(
            offers,
            analysis_id=analysis.analysis_id,
            generated_at=analysis.created_at.isoformat(),
            filters=filters,
            location_index=location_index,
            expected_location_count=expected_locations,
            source_rows=(
                await self._repository.source_rows(
                    analysis.collection_run_id,
                    filters.retailer_id,
                )
            ),
            artifact_checksums=[artifact.checksum for artifact in artifacts],
            product_context=product_context,
            retailer_options=retailer_options,
        )
        validate_instance(
            self._root,
            "price-monitoring-view.schema.json",
            view,
            label=f"price-monitoring:{analysis.analysis_id}:{filters.retailer_id}",
        )
        return view


def get_price_monitoring_service(request: Request) -> PriceMonitoringService:
    existing = getattr(request.app.state, "price_monitoring_service", None)
    if existing is not None:
        return existing
    root = Path(os.getenv("RCI_REPOSITORY_ROOT", Path.cwd())).resolve()
    engine = request.app.state.database_probe.engine
    service = PriceMonitoringService(
        repository_root=root,
        analysis_service=get_analysis_service(request),
        repository=PostgresPriceMonitoringRepository(engine),
        product_pack_loader=CatalogProductPackLoader(
            root,
            PostgresProductPackCatalog(engine),
        ),
        reader=S3ParquetReader.from_environment(),
    )
    request.app.state.price_monitoring_service = service
    return service


ServiceDependency = Annotated[PriceMonitoringService, Depends(get_price_monitoring_service)]


@router.get("/analyses/{analysis_id}/price-monitoring")
async def price_monitoring_view(
    analysis_id: str,
    service: ServiceDependency,
    retailer: str = Query(min_length=1),
    brand_type: BrandFilter = "all",
    state_filter: str | None = Query(default=None, alias="state"),
    city: str | None = None,
    product_id: str | None = None,
) -> dict[str, Any]:
    try:
        return await service.view(
            analysis_id,
            PriceMonitoringFilters(
                retailer_id=retailer,
                brand_type=brand_type,
                state=state_filter,
                city=city,
                product_id=product_id,
            ),
        )
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
