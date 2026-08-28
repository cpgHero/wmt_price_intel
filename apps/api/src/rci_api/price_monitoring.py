"""Search-authoritative retailer price-monitoring read model and API."""

from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import os
import secrets
from collections import defaultdict
from dataclasses import dataclass
from io import BytesIO, StringIO
from pathlib import Path
from typing import Annotated, Any, Literal

import polars as pl
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from rci_analytics import (
    CatalogProductPackLoader,
    PriceArchitectureMatrixProjector,
    PriceArchitectureRetailerInput,
    PriceMonitoringFilters,
    PriceMonitoringProjector,
    ProductPriceObservation,
    classified_offer_from_record,
)
from rci_analytics.product_location import ProductLocationPopulation
from rci_api.analyses import get_analysis_service
from rci_contracts import validate_instance
from rci_product_packs import PostgresProductPackCatalog
from rci_products import PRODUCT_DETAIL_NORMALIZER_VERSION
from rci_results import AnalysisResultService
from rci_results.service import AnalysisNotFoundError
from rci_retailer_packs import (
    BrandDecisionOverride,
    GovernedBrandResolver,
    GovernedSellerResolver,
)

router = APIRouter(prefix="/api/v1", tags=["price-monitoring"])
BrandFilter = Literal["all", "private_label", "regional", "national", "unclassified"]
PriceArchitectureMode = Literal["benchmark_anchored", "fixed_range"]


@dataclass(frozen=True, slots=True)
class ClassifiedArtifact:
    storage_uri: str
    checksum: str
    row_count: int
    id: str | None = None
    partition: int = 0
    created_at: str = ""
    generation_id: str | None = None


def _manifest_checksum(artifacts: list[ClassifiedArtifact]) -> str:
    """Return the AnalysisResult evidence-set checksum for an artifact group."""

    if any(not artifact.id for artifact in artifacts):
        raise ValueError("classified artifact IDs are required for evidence reconciliation")
    manifest = sorted(
        (str(artifact.id), artifact.checksum, artifact.row_count) for artifact in artifacts
    )
    body = json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(body.encode()).hexdigest()


def _classified_evidence_set(
    result: dict[str, Any],
    retailer_id: str,
) -> dict[str, Any] | None:
    evidence_set_id = f"evidence.classified.{retailer_id}"
    return next(
        (
            dict(row)
            for row in result.get("evidence_sets", [])
            if isinstance(row, dict) and str(row.get("evidence_set_id")) == evidence_set_id
        ),
        None,
    )


def select_evidence_artifacts(
    artifacts: list[ClassifiedArtifact],
    evidence_set: dict[str, Any] | None,
) -> list[ClassifiedArtifact]:
    """Select exactly the immutable artifact generation cited by AnalysisResult.

    Historical replays may attach more than one derived artifact generation to
    the same collection run. New artifacts carry ``generation_id``. Legacy
    generations are reconstructed by their ordinal occurrence per partition,
    then verified against the AnalysisResult evidence checksum. No ambiguous or
    approximate fallback is permitted.
    """

    if not artifacts:
        return []
    partitions: dict[int, list[ClassifiedArtifact]] = defaultdict(list)
    for artifact in artifacts:
        partitions[artifact.partition].append(artifact)
    for rows in partitions.values():
        rows.sort(key=lambda row: (row.created_at, str(row.id or ""), row.checksum))

    if evidence_set is None:
        if any(len(rows) != 1 for rows in partitions.values()):
            raise RuntimeError(
                "classified evidence has multiple generations but AnalysisResult has no "
                "governing evidence manifest"
            )
        return [rows[0] for _partition, rows in sorted(partitions.items())]

    expected_checksum = str(evidence_set.get("checksum_sha256") or "")
    expected_rows = int(evidence_set.get("row_count") or 0)
    candidates: list[list[ClassifiedArtifact]] = []

    generation_ids = sorted(
        {artifact.generation_id for artifact in artifacts if artifact.generation_id is not None}
    )
    for generation_id in generation_ids:
        candidates.append(
            sorted(
                [row for row in artifacts if row.generation_id == generation_id],
                key=lambda row: row.partition,
            )
        )

    legacy_depth = max(len(rows) for rows in partitions.values())
    for ordinal in range(legacy_depth):
        if all(len(rows) > ordinal for rows in partitions.values()):
            candidates.append([rows[ordinal] for _partition, rows in sorted(partitions.items())])

    matches: dict[tuple[str, ...], list[ClassifiedArtifact]] = {}
    for candidate in candidates:
        identity = tuple(sorted(str(row.id or row.checksum) for row in candidate))
        if identity in matches or sum(row.row_count for row in candidate) != expected_rows:
            continue
        try:
            checksum = _manifest_checksum(candidate)
        except ValueError:
            continue
        if checksum == expected_checksum:
            matches[identity] = candidate

    if len(matches) != 1:
        raise RuntimeError(
            "classified artifact generation does not reconcile to the immutable "
            f"AnalysisResult evidence set (matches={len(matches)}, "
            f"expected_rows={expected_rows})"
        )
    return next(iter(matches.values()))


def compact_price_monitoring_catalog(view: dict[str, Any]) -> dict[str, Any]:
    """Remove product-workspace evidence from a retailer catalog read model."""

    compact = dict(view)
    gaps = dict(compact.get("distribution_gaps") or {})
    gap_display = dict(gaps.get("location_display") or {})
    gap_total = int(gap_display.get("total") or 0)
    gaps.update(
        {
            "geographies": [],
            "locations": [],
            "location_display": {
                **gap_display,
                "returned": 0,
                "sampled": gap_total > 0,
            },
        }
    )
    compact["distribution_gaps"] = gaps
    compact["geographies"] = []
    compact["locations"] = []
    compact["price_histogram"] = []
    compact["exceptions"] = []
    compact["products"] = [
        {
            **dict(product),
            "pdp": {
                "enriched": bool(dict(product.get("pdp") or {}).get("enriched")),
                "authority": dict(dict(product.get("pdp") or {}).get("authority") or {}),
            },
            "price_histogram": [],
            "sample_locations": [],
        }
        for product in compact.get("products", [])
        if isinstance(product, dict)
    ]
    return compact


@dataclass(frozen=True, slots=True)
class PreparedPriceMonitoringData:
    analysis: Any
    projector: PriceMonitoringProjector
    offers: tuple[Any, ...]
    location_index: dict[tuple[str, str], dict[str, Any]]
    eligible_location_index: dict[tuple[str, str], dict[str, Any]]
    expected_locations: int
    source_rows: int
    artifact_checksums: tuple[str, ...]
    product_context: dict[str, dict[str, Any]]
    product_context_revision: str
    retailer_options: tuple[str, ...]
    population: ProductLocationPopulation | None = None


class S3ParquetReader:
    def __init__(self, *, bucket: str, client: Any) -> None:
        self._bucket = bucket
        self._client = client
        self._cache: dict[str, list[dict[str, Any]]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._body_cache: dict[str, bytes] = {}
        self._body_locks: dict[str, asyncio.Lock] = {}

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
            config=Config(
                max_pool_connections=int(os.getenv("OBJECT_STORAGE_MAX_POOL_CONNECTIONS", "64")),
                s3={"addressing_style": "path" if force_path else "virtual"},
            ),
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
        body = await self._body(artifact)
        return await asyncio.to_thread(lambda: self._decode(body).to_dicts())

    async def read_products(
        self,
        artifact: ClassifiedArtifact,
        *,
        retailer_id: str,
        product_ids: list[str],
    ) -> list[dict[str, Any]]:
        """Read only selected products while preserving authoritative Search columns."""

        if not product_ids:
            return []
        body = await self._body(artifact)

        def decode_products() -> pl.DataFrame:
            schema = pl.read_parquet_schema(BytesIO(body))
            available = [column for column in self._columns() if column in schema]
            required = {"retailer_id", "retailer_product_id"}
            if not required.issubset(schema):
                return pl.DataFrame()
            return (
                pl.scan_parquet(BytesIO(body))
                .filter(
                    (pl.col("retailer_id") == retailer_id)
                    & pl.col("retailer_product_id").is_in(product_ids)
                )
                .select(available)
                .collect()
            )

        return await asyncio.to_thread(lambda: decode_products().to_dicts())

    async def _body(self, artifact: ClassifiedArtifact) -> bytes:
        cached = self._body_cache.get(artifact.checksum)
        if cached is not None:
            return cached
        lock = self._body_locks.setdefault(artifact.checksum, asyncio.Lock())
        async with lock:
            cached = self._body_cache.get(artifact.checksum)
            if cached is not None:
                return cached
            body = await self._fetch(artifact)
            if len(self._body_cache) >= 3:
                self._body_cache.pop(next(iter(self._body_cache)))
            self._body_cache[artifact.checksum] = body
            return body

    async def _fetch(self, artifact: ClassifiedArtifact) -> bytes:
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
        return body

    @staticmethod
    def _columns() -> list[str]:
        return [
            "offer_id",
            "retailer_id",
            "retailer_product_id",
            "title",
            "brand",
            "price",
            "regular_price",
            "discounted_price",
            "is_sponsored",
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
            "metrics_json",
            "review_reasons_json",
        ]

    @classmethod
    def _decode(cls, body: bytes) -> pl.DataFrame:
        schema = pl.read_parquet_schema(BytesIO(body))
        available = [column for column in cls._columns() if column in schema]
        return pl.read_parquet(BytesIO(body), columns=available)


class PostgresPriceMonitoringRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def catalog_materialization(
        self, analysis_id: str, retailer_id: str
    ) -> dict[str, Any] | None:
        statement = text(
            """
            SELECT materialization.document
            FROM price_monitoring_catalog_materialization materialization
            JOIN analysis_result result
              ON result.id = materialization.analysis_result_id
            WHERE result.analysis_id = :analysis_id
              AND materialization.retailer_id = :retailer_id
              AND result.reporting_status = 'ready'
              AND result.archived_at IS NULL
            """
        )
        async with self._engine.connect() as connection:
            document = await connection.scalar(
                statement,
                {"analysis_id": analysis_id, "retailer_id": retailer_id},
            )
        return dict(document) if isinstance(document, dict) else None

    async def store_catalog_materialization(
        self,
        analysis_id: str,
        *,
        retailer_id: str,
        source_revision: str,
        document: dict[str, Any],
    ) -> None:
        statement = text(
            """
            INSERT INTO price_monitoring_catalog_materialization (
              analysis_result_id, retailer_id, source_revision, document
            )
            SELECT id, :retailer_id, :source_revision, CAST(:document AS jsonb)
            FROM analysis_result
            WHERE analysis_id = :analysis_id
            ON CONFLICT ON CONSTRAINT price_monitoring_catalog_materialization_scope_uq
            DO UPDATE SET source_revision = EXCLUDED.source_revision,
                          document = EXCLUDED.document,
                          materialized_at = now()
            RETURNING id
            """
        )
        async with self._engine.begin() as connection:
            materialization_id = await connection.scalar(
                statement,
                {
                    "analysis_id": analysis_id,
                    "retailer_id": retailer_id,
                    "source_revision": source_revision,
                    "document": json.dumps(
                        document, ensure_ascii=False, separators=(",", ":")
                    ),
                },
            )
            if materialization_id is None:
                raise LookupError(f"analysis {analysis_id!r} was not found")

    async def architecture_materialization(
        self,
        analysis_id: str,
        *,
        mode: PriceArchitectureMode,
        fixed_increment: float,
        brand_type: BrandFilter,
        brand: str | None,
        state: str | None,
        city: str | None,
        zipcode: str | None,
    ) -> dict[str, Any] | None:
        statement = text(
            """
            SELECT materialization.document
            FROM price_architecture_materialization materialization
            JOIN analysis_result result
              ON result.id = materialization.analysis_result_id
            WHERE result.analysis_id = :analysis_id
              AND materialization.mode = :mode
              AND materialization.fixed_increment = CAST(:fixed_increment AS numeric)
              AND materialization.brand_type = :brand_type
              AND materialization.brand = :brand
              AND materialization.state = :state
              AND materialization.city = :city
              AND materialization.zipcode = :zipcode
            """
        )
        async with self._engine.connect() as connection:
            document = await connection.scalar(
                statement,
                {
                    "analysis_id": analysis_id,
                    "mode": mode,
                    "fixed_increment": fixed_increment,
                    "brand_type": brand_type,
                    "brand": brand or "",
                    "state": state or "",
                    "city": city or "",
                    "zipcode": zipcode or "",
                },
            )
        return dict(document) if isinstance(document, dict) else None

    async def store_architecture_materialization(
        self,
        analysis_id: str,
        *,
        mode: PriceArchitectureMode,
        fixed_increment: float,
        brand_type: BrandFilter,
        brand: str | None,
        state: str | None,
        city: str | None,
        zipcode: str | None,
        source_revision: str,
        document: dict[str, Any],
    ) -> None:
        statement = text(
            """
            INSERT INTO price_architecture_materialization (
              analysis_result_id, mode, fixed_increment, brand_type, brand,
              state, city, zipcode, source_revision, document
            )
            SELECT id, :mode, CAST(:fixed_increment AS numeric), :brand_type, :brand,
              :state, :city, :zipcode, :source_revision, CAST(:document AS jsonb)
            FROM analysis_result
            WHERE analysis_id = :analysis_id
            ON CONFLICT ON CONSTRAINT price_architecture_materialization_scope_uq
            DO UPDATE SET
              source_revision = EXCLUDED.source_revision,
              document = EXCLUDED.document,
              materialized_at = now()
            RETURNING id
            """
        )
        async with self._engine.begin() as connection:
            materialization_id = await connection.scalar(
                statement,
                {
                    "analysis_id": analysis_id,
                    "mode": mode,
                    "fixed_increment": fixed_increment,
                    "brand_type": brand_type,
                    "brand": brand or "",
                    "state": state or "",
                    "city": city or "",
                    "zipcode": zipcode or "",
                    "source_revision": source_revision,
                    "document": json.dumps(document, ensure_ascii=False, separators=(",", ":")),
                },
            )
            if materialization_id is None:
                raise LookupError(f"analysis {analysis_id!r} was not found")

    async def artifacts(self, collection_run_id: str, retailer_id: str) -> list[ClassifiedArtifact]:
        statement = text(
            """
            SELECT id::text, storage_uri, checksum,
                   coalesce(row_count, 0)::integer AS row_count,
                   coalesce((metadata->>'partition')::integer, 0) AS partition,
                   created_at::text,
                   nullif(metadata->>'analysis_run_id', '') AS generation_id
            FROM dataset_artifact
            WHERE collection_run_id::text = :collection_run_id
              AND artifact_type = 'classified_offers'
              AND metadata->>'retailer_id' = :retailer_id
            ORDER BY coalesce((metadata->>'partition')::integer, 0), created_at
            """
        )
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        statement,
                        {"collection_run_id": collection_run_id, "retailer_id": retailer_id},
                    )
                )
                .mappings()
                .all()
            )
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
    ) -> tuple[
        dict[tuple[str, str], dict[str, Any]],
        dict[tuple[str, str], dict[str, Any]],
        int,
    ]:
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
            SELECT DISTINCT location_scope_key, store_number, zipcode
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
            parameters = {
                "collection_run_id": collection_run_id,
                "retailer_id": retailer_id,
            }
            rows = (await connection.execute(locations, parameters)).mappings().all()
            location_index = {
                (str(row["retailer_id"]), str(row["store_number"])): dict(row) for row in rows
            }
            if retailer_id == "amazon_us_same_day":
                zip_rows = (await connection.execute(zip_geography)).mappings()
                location_index.update(
                    {
                        (retailer_id, f"zip:{row['zipcode']}"): {
                            **dict(row),
                            "store_name": None,
                        }
                        for row in zip_rows
                    }
                )
            planned_rows = (await connection.execute(planned, parameters)).mappings().all()
        eligible_index: dict[tuple[str, str], dict[str, Any]] = {}
        for row in planned_rows:
            store_number = str(row["store_number"]) if row["store_number"] is not None else None
            zipcode = str(row["zipcode"]) if row["zipcode"] is not None else None
            location_key = store_number or (f"zip:{zipcode}" if zipcode else None)
            if location_key is None:
                continue
            context = dict(location_index.get((retailer_id, location_key), {}))
            context.setdefault("retailer_id", retailer_id)
            context.setdefault("store_number", store_number)
            context.setdefault("zipcode", zipcode)
            eligible_index[(retailer_id, location_key)] = context
        return location_index, eligible_index, len(planned_rows)

    async def product_context(
        self,
        retailer_id: str,
        product_ids: list[str],
    ) -> dict[str, dict[str, Any]]:
        context, _revision = await self.product_context_bundle(retailer_id, product_ids)
        return context

    async def product_context_bundle(
        self,
        retailer_id: str,
        product_ids: list[str],
    ) -> tuple[dict[str, dict[str, Any]], str]:
        """Return PDP context and its cache revision from one database snapshot."""

        if not product_ids:
            return {}, "0:"
        statement = text(
            """
            SELECT cp.retailer_id, cp.retailer_product_id, cp.identifiers,
              cp.identity, revision.normalized,
              count(*) OVER ()::integer AS context_product_count,
              COALESCE(max(cp.updated_at) OVER ()::text, '') AS context_latest_update
            FROM canonical_product cp
            LEFT JOIN LATERAL (
              SELECT n.document->'normalized' AS normalized
              FROM product_detail_normalization n
              JOIN product_detail_snapshot s
                ON s.id = n.product_detail_snapshot_id
              WHERE s.canonical_product_id = cp.id
                AND n.normalizer_version = :normalizer_version
                AND n.status = 'succeeded'
              ORDER BY s.observed_at DESC, n.completed_at DESC, n.id DESC
              LIMIT 1
            ) revision ON true
            WHERE cp.retailer_id = :retailer_id
              AND cp.retailer_product_id = ANY(CAST(:product_ids AS text[]))
            """
        )
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        statement,
                        {
                            "retailer_id": retailer_id,
                            "product_ids": product_ids,
                            "normalizer_version": PRODUCT_DETAIL_NORMALIZER_VERSION,
                        },
                    )
                )
                .mappings()
                .all()
            )
            context: dict[str, dict[str, Any]] = {}
            for row in rows:
                identity = dict(row["identity"])
                normalized = dict(row["normalized"]) if isinstance(row["normalized"], dict) else {}
                media = (
                    dict(normalized["media"]) if isinstance(normalized.get("media"), dict) else {}
                )
                commerce = (
                    dict(normalized["commerce"])
                    if isinstance(normalized.get("commerce"), dict)
                    else {}
                )
                relationships = (
                    dict(normalized["relationships"])
                    if isinstance(normalized.get("relationships"), dict)
                    else {}
                )
                seller = normalized.get("seller") if normalized else identity.get("seller")
                context[f"{row['retailer_id']}:{row['retailer_product_id']}"] = {
                    "name": normalized.get("name") or identity.get("name"),
                    "brand": normalized.get("brand") or identity.get("brand"),
                    "seller": seller,
                    "image_url": media.get("image_primary") or identity.get("image_primary"),
                    "url": normalized.get("url") or identity.get("url"),
                    "pdp": {
                        "enriched": bool(normalized),
                        "item_condition": commerce.get("item_condition")
                        or identity.get("item_condition"),
                        "description_short": normalized.get("description_short")
                        or identity.get("description_short"),
                        "description_full": normalized.get("description_full")
                        or identity.get("description_full"),
                        "category_path": normalized.get("category_path")
                        or identity.get("category_path"),
                        "identifiers": dict(row["identifiers"]),
                        "specification": normalized.get("specification")
                        or identity.get("specification", {}),
                        "physical_properties": normalized.get("physical_properties")
                        or identity.get("physical_properties", {}),
                        "variant_configuration": normalized.get("variant_configuration")
                        or identity.get("variant_configuration", {}),
                        "commerce": {
                            key: value for key, value in commerce.items() if key != "offers"
                        },
                        "media": {
                            "images": [
                                str(value)
                                for value in media.get("images", [])
                                if isinstance(value, str) and value.strip()
                            ][:12]
                            if isinstance(media.get("images"), list)
                            else [],
                            "image_count": len(media.get("images", []))
                            if isinstance(media.get("images"), list)
                            else 0,
                            "video_count": len(media.get("videos", []))
                            if isinstance(media.get("videos"), list)
                            else 0,
                        },
                        "fulfillment": normalized.get("fulfillment", {}),
                        "reviews": normalized.get("reviews", {}),
                        "demand": normalized.get("demand", {}),
                        "content": normalized.get("content", {}),
                        "relationship_counts": {
                            key: len(value) if isinstance(value, list) else 0
                            for key, value in relationships.items()
                        },
                        "source_context": normalized.get("source_context", {}),
                        "source_field_count": len(normalized.get("source_field_inventory", [])),
                        "unmapped_source_fields": normalized.get("unmapped_source_fields", []),
                        "authority": {
                            "identity": "pdp" if normalized else "search",
                            "price": "search",
                            "availability": "search",
                        },
                    },
                }
            first_row = rows[0] if rows else None
            revision = (
                f"{int(first_row['context_product_count'])}:{first_row['context_latest_update']}"
                if first_row is not None
                else "0:"
            )
            return context, revision

    async def product_context_revision(
        self,
        retailer_id: str,
        product_ids: list[str],
    ) -> str:
        if not product_ids:
            return "0:"
        statement = text(
            """
            SELECT count(*)::integer AS product_count,
              COALESCE(max(updated_at)::text, '') AS latest_update
            FROM canonical_product
            WHERE retailer_id = :retailer_id
              AND retailer_product_id = ANY(CAST(:product_ids AS text[]))
            """
        )
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        statement,
                        {"retailer_id": retailer_id, "product_ids": product_ids},
                    )
                )
                .mappings()
                .one()
            )
        return f"{int(row['product_count'])}:{row['latest_update']}"

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
                (
                  CAST(:revision_id AS text) IS NOT NULL
                  AND id::text = CAST(:revision_id AS text)
                )
                OR (
                  CAST(:revision_id AS text) IS NULL
                  AND product_pack_id = :product_pack_id
                  AND product_pack_version = :product_pack_version
                  AND benchmark_retailer_id = :benchmark_retailer_id
                  AND status = 'current'
                )
              )
              ORDER BY revision DESC
              LIMIT 1
            )
            SELECT retailer_id, normalized_brand, display_brand, role, decision,
              NULLIF(evidence->>'canonical_brand_id', '') AS canonical_brand_id,
              NULLIF(evidence->>'canonical_brand_name', '') AS canonical_brand_name
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
        self._prepared_cache: dict[tuple[str, str], PreparedPriceMonitoringData] = {}
        self._prepared_locks: dict[tuple[str, str], asyncio.Lock] = {}
        self._projector_cache: dict[str, PriceMonitoringProjector] = {}
        self._projector_locks: dict[str, asyncio.Lock] = {}
        self._view_cache: dict[tuple[str, ...], dict[str, Any]] = {}
        self._view_tasks: dict[tuple[str, ...], asyncio.Task[dict[str, Any]]] = {}
        self._map_cache: dict[tuple[str, ...], dict[str, Any]] = {}
        self._architecture_cache: dict[tuple[str, ...], dict[str, Any]] = {}
        self._product_observation_cache: dict[
            tuple[str, ...], dict[str, tuple[ProductPriceObservation, ...]]
        ] = {}
        self._product_observation_locks: dict[tuple[str, ...], asyncio.Lock] = {}
        catalog = json.loads((repository_root / "config" / "retailer-catalog.json").read_text())
        self._retailer_names = {
            str(row["id"]): str(row["display_name"])
            for row in catalog.get("retailers", [])
            if isinstance(row, dict) and row.get("id") and row.get("display_name")
        }

    async def _projector_for_analysis(
        self,
        analysis: Any,
        benchmark_retailer_id: str,
    ) -> PriceMonitoringProjector:
        """Load one governed projector shared by full and selective read paths."""

        cache_key = str(analysis.analysis_id)
        cached = self._projector_cache.get(cache_key)
        if cached is not None:
            return cached
        lock = self._projector_locks.setdefault(cache_key, asyncio.Lock())
        async with lock:
            cached = self._projector_cache.get(cache_key)
            if cached is not None:
                return cached
            source = analysis.result.get("source", {})
            revision_id = (
                str(source["brand_revision_id"]) if source.get("brand_revision_id") else None
            )
            overrides, pack = await asyncio.gather(
                self._repository.brand_overrides(
                    revision_id=revision_id,
                    product_pack_id=analysis.product_pack_id,
                    product_pack_version=analysis.product_pack_version,
                    benchmark_retailer_id=benchmark_retailer_id,
                ),
                self._packs.load(
                    analysis.product_pack_id,
                    analysis.product_pack_version,
                ),
            )
            resolver = GovernedBrandResolver.from_repository(self._root).with_overrides(overrides)
            projector = PriceMonitoringProjector(
                pack,
                resolver,
                retailer_names=self._retailer_names,
                seller_resolver=GovernedSellerResolver.from_repository(self._root),
            )
            if len(self._projector_cache) >= 16:
                self._projector_cache.pop(next(iter(self._projector_cache)))
            self._projector_cache[cache_key] = projector
            return projector

    async def _prepare(
        self,
        analysis_id: str,
        retailer_id: str,
    ) -> PreparedPriceMonitoringData:
        cache_key = (analysis_id, retailer_id)
        cached = self._prepared_cache.get(cache_key)
        if cached is not None:
            product_ids = sorted(
                {
                    offer.offer.retailer_product_id
                    for offer in cached.offers
                    if offer.offer.retailer_id == retailer_id and offer.in_scope
                }
            )
            revision = await self._repository.product_context_revision(
                retailer_id,
                product_ids,
            )
            if revision == cached.product_context_revision:
                return cached
            product_context, revision = await self._repository.product_context_bundle(
                retailer_id,
                product_ids,
            )
            population = await asyncio.to_thread(
                cached.projector.canonical_population,
                cached.offers,
                retailer_id=retailer_id,
                location_index=cached.location_index,
                eligible_location_index=cached.eligible_location_index,
                product_context=product_context,
                retailer_options=cached.retailer_options,
            )
            refreshed = PreparedPriceMonitoringData(
                analysis=cached.analysis,
                projector=cached.projector,
                offers=cached.offers,
                location_index=cached.location_index,
                eligible_location_index=cached.eligible_location_index,
                expected_locations=cached.expected_locations,
                source_rows=cached.source_rows,
                artifact_checksums=cached.artifact_checksums,
                product_context=product_context,
                product_context_revision=revision,
                retailer_options=cached.retailer_options,
                population=population,
            )
            self._prepared_cache[cache_key] = refreshed
            return refreshed
        lock = self._prepared_locks.setdefault(cache_key, asyncio.Lock())
        async with lock:
            cached = self._prepared_cache.get(cache_key)
            if cached is not None:
                return cached
            analysis = await self._analyses.get(analysis_id)
            result = analysis.result
            benchmark = str(result["benchmark_retailer"])
            retailer_options = (benchmark, *(str(value) for value in result["competitors"]))
            if retailer_id not in retailer_options:
                raise ValueError(f"retailer {retailer_id!r} is not in this analysis")
            artifacts = await self._repository.artifacts(
                analysis.collection_run_id,
                retailer_id,
            )
            if not artifacts:
                raise LookupError(f"classified Search evidence for {retailer_id!r} is unavailable")
            artifacts = select_evidence_artifacts(
                artifacts,
                _classified_evidence_set(result, retailer_id),
            )
            records: list[dict[str, Any]] = []
            for artifact in artifacts:
                records.extend(await self._reader.read(artifact))
            offers = await asyncio.to_thread(
                lambda: tuple(classified_offer_from_record(record) for record in records)
            )
            product_ids = sorted(
                {
                    offer.offer.retailer_product_id
                    for offer in offers
                    if offer.offer.retailer_id == retailer_id and offer.in_scope
                }
            )
            (
                location_index,
                eligible_location_index,
                expected_locations,
            ) = await self._repository.location_context(
                analysis.collection_run_id,
                retailer_id,
            )
            (
                product_context,
                product_context_revision,
            ) = await self._repository.product_context_bundle(
                retailer_id,
                product_ids,
            )
            projector = await self._projector_for_analysis(analysis, benchmark)
            population = await asyncio.to_thread(
                projector.canonical_population,
                offers,
                retailer_id=retailer_id,
                location_index=location_index,
                eligible_location_index=eligible_location_index,
                product_context=product_context,
                retailer_options=retailer_options,
            )
            prepared = PreparedPriceMonitoringData(
                analysis=analysis,
                projector=projector,
                offers=offers,
                location_index=location_index,
                eligible_location_index=eligible_location_index,
                expected_locations=expected_locations,
                source_rows=await self._repository.source_rows(
                    analysis.collection_run_id,
                    retailer_id,
                ),
                artifact_checksums=tuple(artifact.checksum for artifact in artifacts),
                product_context=product_context,
                product_context_revision=product_context_revision,
                retailer_options=retailer_options,
                population=population,
            )
            # A cross-retailer architecture request commonly prepares 14+ sources.
            # Retaining fewer entries caused every subsequent matrix view to churn
            # immutable populations back out of object storage.
            if len(self._prepared_cache) >= 64:
                self._prepared_cache.pop(next(iter(self._prepared_cache)))
            self._prepared_cache[cache_key] = prepared
            return prepared

    @staticmethod
    def _view_key(analysis_id: str, filters: PriceMonitoringFilters) -> tuple[str, ...]:
        return (
            analysis_id,
            filters.retailer_id,
            filters.brand_type,
            filters.state or "",
            filters.city or "",
            filters.zipcode or "",
            filters.product_id or "",
        )

    def _project(
        self,
        prepared: PreparedPriceMonitoringData,
        filters: PriceMonitoringFilters,
        *,
        location_limit: int | None = 1_200,
        product_location_limit: int | None = 200,
    ) -> dict[str, Any]:
        analysis = prepared.analysis
        return prepared.projector.build(
            prepared.offers,
            analysis_id=analysis.analysis_id,
            generated_at=analysis.created_at.isoformat(),
            filters=filters,
            location_index=prepared.location_index,
            eligible_location_index=prepared.eligible_location_index,
            expected_location_count=prepared.expected_locations,
            source_rows=prepared.source_rows,
            artifact_checksums=prepared.artifact_checksums,
            product_context=prepared.product_context,
            retailer_options=prepared.retailer_options,
            location_limit=location_limit,
            product_location_limit=product_location_limit,
            population=prepared.population,
        )

    async def view(self, analysis_id: str, filters: PriceMonitoringFilters) -> dict[str, Any]:
        if filters.city is not None and filters.state is None:
            raise ValueError("a city filter requires its state")
        prepared = await self._prepare(analysis_id, filters.retailer_id)
        cache_key = (*self._view_key(analysis_id, filters), prepared.product_context_revision)
        cached = self._view_cache.get(cache_key)
        if cached is not None:
            return cached
        existing_task = self._view_tasks.get(cache_key)
        if existing_task is not None:
            return await asyncio.shield(existing_task)

        def project_and_validate() -> dict[str, Any]:
            projected = self._project(
                prepared,
                filters,
                product_location_limit=200 if filters.product_id else 0,
            )
            validate_instance(
                self._root,
                "price-monitoring-view.schema.json",
                projected,
                label=(f"price-monitoring:{prepared.analysis.analysis_id}:{filters.retailer_id}"),
            )
            return projected

        async def populate_cache() -> dict[str, Any]:
            # Building a large product-location catalog is CPU-heavy. Running it
            # on the event-loop thread can make even /health/ready and small
            # analysis reads time out, which presents a healthy process as an
            # API outage.
            projected = await asyncio.to_thread(project_and_validate)
            if len(self._view_cache) >= 96:
                self._view_cache.pop(next(iter(self._view_cache)))
            self._view_cache[cache_key] = projected
            return projected

        task = asyncio.create_task(populate_cache())
        self._view_tasks[cache_key] = task

        def discard(completed: asyncio.Task[dict[str, Any]]) -> None:
            if self._view_tasks.get(cache_key) is completed:
                self._view_tasks.pop(cache_key, None)
            if not completed.cancelled():
                # Retrieve a background exception even when the initiating HTTP
                # client disconnected before the projection completed.
                completed.exception()

        task.add_done_callback(discard)
        # Client timeouts must not cancel the shared cold build. Later requests
        # join the same task and the completed result remains cached.
        return await asyncio.shield(task)

    async def materialize_catalog(
        self,
        analysis_id: str,
        retailer_id: str,
        *,
        refresh: bool = False,
        publish: bool = True,
    ) -> dict[str, Any]:
        if not refresh:
            stored = await self._repository.catalog_materialization(
                analysis_id, retailer_id
            )
            if stored is not None:
                return stored
        full_view = await self.view(
            analysis_id,
            PriceMonitoringFilters(retailer_id=retailer_id),
        )
        document = compact_price_monitoring_catalog(full_view)
        validate_instance(
            self._root,
            "price-monitoring-view.schema.json",
            document,
            label=f"price-monitoring-catalog:{analysis_id}:{retailer_id}",
        )
        if publish:
            source_revision = hashlib.sha256(
                json.dumps(
                    document,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            await self._repository.store_catalog_materialization(
                analysis_id,
                retailer_id=retailer_id,
                source_revision=source_revision,
                document=document,
            )
        return document

    async def catalog_page(
        self,
        analysis_id: str,
        retailer_id: str,
        *,
        query: str | None = None,
        brand_type: BrandFilter = "all",
        brand: str | None = None,
        seller: str | None = None,
        offset: int = 0,
        limit: int = 40,
    ) -> dict[str, Any]:
        document = await self._repository.catalog_materialization(
            analysis_id, retailer_id
        )
        if document is None:
            raise LookupError(
                "The Price Intelligence catalog has not been materialized for this report."
            )
        all_products = [
            dict(row) for row in document.get("products", []) if isinstance(row, dict)
        ]
        normalized_query = (query or "").strip().casefold()
        normalized_brand = (brand or "").strip()
        normalized_seller = (seller or "").strip()

        def included(product: dict[str, Any]) -> bool:
            searchable = " ".join(
                str(product.get(field) or "")
                for field in ("name", "product_id", "brand", "seller")
            ).casefold()
            return bool(
                (not normalized_query or normalized_query in searchable)
                and (brand_type == "all" or product.get("brand_type") == brand_type)
                and (not normalized_brand or product.get("brand") == normalized_brand)
                and (not normalized_seller or product.get("seller") == normalized_seller)
            )

        filtered = [product for product in all_products if included(product)]
        filtered.sort(
            key=lambda product: (
                -int(dict(product.get("presence") or {}).get("observed_locations") or 0),
                str(product.get("name") or "").casefold(),
                str(product.get("product_id") or ""),
            )
        )
        page = filtered[offset : offset + limit]
        page_view = {**document, "products": page}
        brands = sorted(
            {
                str(product["brand"])
                for product in all_products
                if product.get("brand")
            },
            key=str.casefold,
        )
        sellers = sorted(
            {
                str(product["seller"])
                for product in all_products
                if product.get("seller")
            },
            key=str.casefold,
        )
        brand_types = sorted(
            {str(product.get("brand_type") or "unclassified") for product in all_products}
        )
        return {
            "schema_version": "1.0.0-price-monitoring-catalog-page",
            "view": page_view,
            "pagination": {
                "offset": offset,
                "limit": limit,
                "returned": len(page),
                "filtered_total": len(filtered),
                "total": len(all_products),
                "has_more": offset + len(page) < len(filtered),
            },
            "filters": {
                "query": query or "",
                "brand_type": brand_type,
                "brand": normalized_brand or None,
                "seller": normalized_seller or None,
            },
            "facets": {
                "brands": brands,
                "brand_types": brand_types,
                "sellers": sellers,
            },
        }

    @staticmethod
    def _architecture_retailer_input(
        prepared: PreparedPriceMonitoringData,
        *,
        brand_type: BrandFilter,
        state: str | None,
        city: str | None,
        zipcode: str | None,
        retailer_name: str,
    ) -> PriceArchitectureRetailerInput:
        population = prepared.population
        if population is None:
            raise RuntimeError("canonical product-location population is unavailable")

        def location_matches(scope_key: str) -> bool:
            location = population.source_locations.get(scope_key)
            return bool(
                location is not None
                and (state is None or location.state == state)
                and (city is None or location.city == city)
                and (zipcode is None or location.zipcode == zipcode)
            )

        observations = tuple(
            row
            for row in population.observations
            if (brand_type == "all" or row.brand_type == brand_type)
            and location_matches(row.location.scope_key)
        )
        eligible_scope_keys = frozenset(
            scope_key for scope_key in population.eligible_scope_keys if location_matches(scope_key)
        )
        location_dimension: Literal["store", "service_area"] = (
            "service_area"
            if observations and all(row.location.kind == "service_area" for row in observations)
            else "service_area"
            if population.retailer_id == "amazon_us_same_day"
            else "store"
        )
        return PriceArchitectureRetailerInput(
            retailer_id=population.retailer_id,
            retailer_name=retailer_name,
            location_dimension=location_dimension,
            eligible_scope_keys=eligible_scope_keys,
            observations=observations,
            population_checksum=population.checksum,
        )

    async def architecture_matrix(
        self,
        analysis_id: str,
        *,
        mode: PriceArchitectureMode = "benchmark_anchored",
        fixed_increment: float = 0.5,
        brand_type: BrandFilter = "all",
        brand: str | None = None,
        state: str | None = None,
        city: str | None = None,
        zipcode: str | None = None,
        refresh: bool = False,
        publish: bool = True,
    ) -> dict[str, Any]:
        """Build unmatched assortment architecture across every analysis retailer."""

        if city is not None and state is None:
            raise ValueError("a city filter requires its state")
        if mode == "fixed_range" and fixed_increment not in {0.5, 1.0}:
            raise ValueError("fixed price-rung increment must be 0.50 or 1.00")
        if publish and not refresh:
            stored = await self._repository.architecture_materialization(
                analysis_id,
                mode=mode,
                fixed_increment=fixed_increment,
                brand_type=brand_type,
                brand=brand,
                state=state,
                city=city,
                zipcode=zipcode,
            )
            if stored is not None:
                validate_instance(
                    self._root,
                    "price-architecture-matrix.schema.json",
                    stored,
                    label=f"materialized-price-architecture-matrix:{analysis_id}",
                )
                return stored
        analysis = await self._analyses.get(analysis_id)
        benchmark = str(analysis.result["benchmark_retailer"])
        retailer_ids = tuple(
            dict.fromkeys(
                (
                    benchmark,
                    *(str(value) for value in analysis.result.get("competitors", [])),
                )
            )
        )
        # Population preparation is dominated by independent object-store and
        # database reads. Eight-way concurrency materially reduces the cold path
        # while keeping connection pressure bounded.
        semaphore = asyncio.Semaphore(8)

        async def prepare(retailer_id: str) -> PreparedPriceMonitoringData:
            async with semaphore:
                return await self._prepare(analysis_id, retailer_id)

        outcomes = await asyncio.gather(
            *(prepare(retailer_id) for retailer_id in retailer_ids),
            return_exceptions=True,
        )
        prepared_rows: list[PreparedPriceMonitoringData] = []
        unavailable: list[dict[str, Any]] = []
        for retailer_id, outcome in zip(retailer_ids, outcomes, strict=True):
            if isinstance(outcome, BaseException):
                if retailer_id == benchmark:
                    raise RuntimeError(
                        "benchmark Search evidence is unavailable; price rungs cannot be defined"
                    ) from outcome
                unavailable.append(
                    {
                        "id": retailer_id,
                        "name": self._retailer_names.get(
                            retailer_id, retailer_id.replace("_", " ").title()
                        ),
                        "status": "unavailable",
                        "location_dimension": (
                            "service_area" if retailer_id == "amazon_us_same_day" else "store"
                        ),
                        "sku_count": 0,
                        "eligible_locations": 0,
                        "observed_locations": 0,
                        "verified_first_party_skus": 0,
                        "seller_unverified_skus": 0,
                        "seller_not_governed_skus": 0,
                        "population_checksum": None,
                        "reason": (
                            "Governed Search evidence is unavailable for this retailer "
                            "in the analysis."
                        ),
                    }
                )
                continue
            prepared_rows.append(outcome)

        revisions = tuple(
            sorted(
                (
                    f"{row.population.checksum if row.population else ''}:"
                    f"{row.product_context_revision}"
                )
                for row in prepared_rows
            )
        )
        source_revision = hashlib.sha256("|".join(revisions).encode()).hexdigest()
        cache_key = (
            analysis_id,
            mode,
            f"{fixed_increment:.2f}",
            brand_type,
            brand or "",
            state or "",
            city or "",
            zipcode or "",
            *revisions,
        )
        cached = self._architecture_cache.get(cache_key)
        if cached is not None and not refresh and publish:
            return cached

        pack = await self._packs.load(
            analysis.product_pack_id,
            analysis.product_pack_version,
        )
        inputs = [
            self._architecture_retailer_input(
                prepared,
                brand_type=brand_type,
                state=state,
                city=city,
                zipcode=zipcode,
                retailer_name=self._retailer_names.get(
                    prepared.population.retailer_id if prepared.population else "",
                    prepared.population.retailer_id.replace("_", " ").title()
                    if prepared.population
                    else "Unknown retailer",
                ),
            )
            for prepared in prepared_rows
        ]
        matrix = PriceArchitectureMatrixProjector().build(
            analysis_id=analysis_id,
            generated_at=analysis.created_at.isoformat(),
            product_pack={"id": pack.id, "name": pack.name, "version": pack.version},
            anchor_retailer_id=benchmark,
            retailers=inputs,
            mode=mode,
            fixed_increment=fixed_increment,
            brand_type=brand_type,
            brand=brand,
            state=state,
            city=city,
            zipcode=zipcode,
            unavailable_retailers=unavailable,
        )
        validate_instance(
            self._root,
            "price-architecture-matrix.schema.json",
            matrix,
            label=f"price-architecture-matrix:{analysis_id}",
        )
        if publish:
            await self._repository.store_architecture_materialization(
                analysis_id,
                mode=mode,
                fixed_increment=fixed_increment,
                brand_type=brand_type,
                brand=brand,
                state=state,
                city=city,
                zipcode=zipcode,
                source_revision=source_revision,
                document=matrix,
            )
            if len(self._architecture_cache) >= 24:
                self._architecture_cache.pop(next(iter(self._architecture_cache)))
            self._architecture_cache[cache_key] = matrix
        return matrix

    async def pre_materialize_architecture_matrices(
        self,
        analysis_id: str,
        *,
        refresh: bool = False,
        publish: bool = True,
    ) -> list[dict[str, Any]]:
        """Persist the three default category-level matrices for immediate reads."""

        return list(
            await asyncio.gather(
                self.architecture_matrix(
                    analysis_id,
                    mode="benchmark_anchored",
                    fixed_increment=0.5,
                    refresh=refresh,
                    publish=publish,
                ),
                self.architecture_matrix(
                    analysis_id,
                    mode="fixed_range",
                    fixed_increment=0.5,
                    refresh=refresh,
                    publish=publish,
                ),
                self.architecture_matrix(
                    analysis_id,
                    mode="fixed_range",
                    fixed_increment=1.0,
                    refresh=refresh,
                    publish=publish,
                ),
            )
        )

    async def product_observations(
        self,
        analysis_id: str,
        *,
        retailer_id: str,
        product_id: str,
        comparison_metric: str,
    ) -> list[ProductPriceObservation]:
        """Return latest positive Search evidence at exact product-location grain."""

        grouped = await self.product_observations_for_products(
            analysis_id,
            retailer_id=retailer_id,
            product_ids=[product_id],
            comparison_metric=comparison_metric,
        )
        return list(grouped.get(product_id, ()))

    async def product_observations_for_products(
        self,
        analysis_id: str,
        *,
        retailer_id: str,
        product_ids: list[str],
        comparison_metric: str,
    ) -> dict[str, tuple[ProductPriceObservation, ...]]:
        """Return selected product evidence without preparing unrelated retailer offers."""

        selected_product_ids = sorted({value for value in product_ids if value})
        if not selected_product_ids:
            return {}
        cache_key = (
            analysis_id,
            retailer_id,
            comparison_metric,
            *selected_product_ids,
        )
        cached = self._product_observation_cache.get(cache_key)
        if cached is not None:
            return cached
        cache_prefix = (analysis_id, retailer_id, comparison_metric)
        selected_product_id_set = set(selected_product_ids)
        for candidate_key, candidate_rows in reversed(
            list(self._product_observation_cache.items())
        ):
            if candidate_key[:3] == cache_prefix and selected_product_id_set.issubset(
                candidate_key[3:]
            ):
                return {
                    product_id: candidate_rows.get(product_id, ())
                    for product_id in selected_product_ids
                }
        lock = self._product_observation_locks.setdefault(cache_key, asyncio.Lock())
        async with lock:
            cached = self._product_observation_cache.get(cache_key)
            if cached is not None:
                return cached
            for candidate_key, candidate_rows in reversed(
                list(self._product_observation_cache.items())
            ):
                if candidate_key[:3] == cache_prefix and selected_product_id_set.issubset(
                    candidate_key[3:]
                ):
                    return {
                        product_id: candidate_rows.get(product_id, ())
                        for product_id in selected_product_ids
                    }
            prepared = self._prepared_cache.get((analysis_id, retailer_id))
            if prepared is not None:
                offers = prepared.offers
                location_index = prepared.location_index
                product_context = prepared.product_context
                projector = prepared.projector
            else:
                analysis = await self._analyses.get(analysis_id)
                result = analysis.result
                benchmark = str(result["benchmark_retailer"])
                retailer_options = (benchmark, *(str(value) for value in result["competitors"]))
                if retailer_id not in retailer_options:
                    raise ValueError(f"retailer {retailer_id!r} is not in this analysis")
                artifacts = await self._repository.artifacts(
                    analysis.collection_run_id,
                    retailer_id,
                )
                if not artifacts:
                    raise LookupError(
                        f"classified Search evidence for {retailer_id!r} is unavailable"
                    )
                artifacts = select_evidence_artifacts(
                    artifacts,
                    _classified_evidence_set(result, retailer_id),
                )
                row_groups, location_context, product_context, projector = await asyncio.gather(
                    asyncio.gather(
                        *(
                            self._reader.read_products(
                                artifact,
                                retailer_id=retailer_id,
                                product_ids=selected_product_ids,
                            )
                            for artifact in artifacts
                        )
                    ),
                    self._repository.location_context(
                        analysis.collection_run_id,
                        retailer_id,
                    ),
                    self._repository.product_context(
                        retailer_id,
                        selected_product_ids,
                    ),
                    self._projector_for_analysis(analysis, benchmark),
                )
                offers = tuple(
                    classified_offer_from_record(record) for group in row_groups for record in group
                )
                location_index = location_context[0]
            grouped = projector.comparison_observations(
                offers,
                retailer_id=retailer_id,
                product_ids=set(selected_product_ids),
                comparison_metric=comparison_metric,
                location_index=location_index,
                product_context=product_context,
            )
            if len(self._product_observation_cache) >= 128:
                self._product_observation_cache.pop(next(iter(self._product_observation_cache)))
            self._product_observation_cache[cache_key] = grouped
            return grouped

    async def evidence_csv(
        self,
        analysis_id: str,
        filters: PriceMonitoringFilters,
    ) -> str:
        if not filters.product_id:
            raise ValueError("a product_id is required for evidence export")
        prepared = await self._prepare(analysis_id, filters.retailer_id)
        view = await asyncio.to_thread(
            self._project,
            prepared,
            filters,
            location_limit=None,
            product_location_limit=None,
        )
        products = view["products"]
        if not products:
            raise LookupError("no exact-product Search evidence matched the export filters")
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "retailer",
                "product_id",
                "store_number",
                "store_name",
                "zipcode",
                "city",
                "state",
                "price",
                "is_sponsored",
                "observed_at",
            ]
        )
        for row in products[0]["sample_locations"]:
            writer.writerow(
                [
                    view["retailer"]["name"],
                    filters.product_id,
                    row["store_number"],
                    row["store_name"],
                    row["zipcode"],
                    row["city"],
                    row["state"],
                    row["price"],
                    row["is_sponsored"],
                    row["observed_at"],
                ]
            )
        return output.getvalue()

    async def map_view(
        self,
        analysis_id: str,
        filters: PriceMonitoringFilters,
        *,
        detail: Literal["summary", "full"] = "full",
    ) -> dict[str, Any]:
        if not filters.product_id:
            raise ValueError("a product_id is required for the price footprint map")
        if filters.city is not None and filters.state is None:
            raise ValueError("a city filter requires its state")
        cache_key = (*self._view_key(analysis_id, filters), "map-v2", detail)
        cached = self._map_cache.get(cache_key)
        if cached is not None:
            return cached

        prepared = await self._prepare(analysis_id, filters.retailer_id)
        view = await asyncio.to_thread(
            self._project,
            prepared,
            filters,
            location_limit=None,
            product_location_limit=0,
        )
        products = view["products"]
        if not products:
            raise LookupError("no exact-product Search evidence matched the map filters")

        reference_price = products[0]["price_stats"]["observation_median"]
        point_limit = 1_200 if detail == "summary" else 6_000

        def map_point(row: dict[str, Any], status_value: str) -> dict[str, Any]:
            price = row.get("median_price") if status_value == "observed" else None
            difference = (
                round(float(price) - float(reference_price), 4)
                if price is not None and reference_price is not None
                else None
            )
            return {
                "scope_key": str(row["scope_key"]),
                "status": status_value,
                "kind": row["kind"],
                "store_number": row.get("store_number"),
                "store_name": row.get("store_name"),
                "zipcode": row.get("zipcode"),
                "city": row.get("city"),
                "state": row.get("state"),
                "country": row["country"],
                "latitude": float(row["latitude"]),
                "longitude": float(row["longitude"]),
                "price": price,
                "difference_from_reference": difference,
            }

        observed_rows = list(view["locations"])
        not_observed_rows = list(view["distribution_gaps"]["locations"])
        observed_with_coordinates = [
            row
            for row in observed_rows
            if row.get("latitude") is not None and row.get("longitude") is not None
        ]
        not_observed_with_coordinates = [
            row
            for row in not_observed_rows
            if row.get("latitude") is not None and row.get("longitude") is not None
        ]
        price_positions = {"below": 0, "at": 0, "above": 0}
        if reference_price is not None:
            for row in observed_rows:
                price = row.get("median_price")
                if price is None:
                    continue
                difference = float(price) - float(reference_price)
                if difference < -0.005:
                    price_positions["below"] += 1
                elif difference > 0.005:
                    price_positions["above"] += 1
                else:
                    price_positions["at"] += 1

        def evenly_sample(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
            if len(rows) <= point_limit:
                return rows
            step = len(rows) / point_limit
            return [rows[int(index * step)] for index in range(point_limit)]

        observed_points = [
            map_point(row, "observed") for row in evenly_sample(observed_with_coordinates)
        ]
        not_observed_points = [
            map_point(row, "not_observed") for row in evenly_sample(not_observed_with_coordinates)
        ]
        result = {
            "schema_version": "1.1.0",
            "analysis_id": analysis_id,
            "retailer": {
                "id": view["retailer"]["id"],
                "name": view["retailer"]["name"],
            },
            "product": {
                "id": products[0]["product_id"],
                "name": products[0]["name"],
            },
            "filters": {
                "state": filters.state,
                "city": filters.city,
                "zipcode": filters.zipcode,
                "detail": detail,
            },
            "source": {
                "authority": "Search",
                "location_authority": "Retailer location master",
                "definition": (
                    "Observed points have positive Search prices. Not observed points are "
                    "planned collection locations where the exact product did not appear "
                    "in the successful Search result; they are review signals, not proof "
                    "of non-carriage."
                ),
            },
            "reference_price": reference_price,
            "display": {
                "observed_locations": int(view["location_display"]["total"]),
                "observed_points": len(observed_points),
                "observed_missing_coordinates": max(
                    0,
                    int(view["location_display"]["total"]) - len(observed_with_coordinates),
                ),
                "observed_sampled": len(observed_with_coordinates) > point_limit,
                "below_reference_locations": price_positions["below"],
                "at_reference_locations": price_positions["at"],
                "above_reference_locations": price_positions["above"],
                "not_observed_locations": int(
                    view["distribution_gaps"]["location_display"]["total"]
                ),
                "not_observed_points": len(not_observed_points),
                "not_observed_missing_coordinates": max(
                    0,
                    int(view["distribution_gaps"]["location_display"]["total"])
                    - len(not_observed_with_coordinates),
                ),
                "not_observed_sampled": len(not_observed_with_coordinates) > point_limit,
            },
            "points": [*observed_points, *not_observed_points],
        }
        validate_instance(
            self._root,
            "price-monitoring-map.schema.json",
            result,
            label=f"price-monitoring-map:{analysis_id}:{filters.retailer_id}",
        )
        if len(self._map_cache) >= 96:
            self._map_cache.pop(next(iter(self._map_cache)))
        self._map_cache[cache_key] = result
        return result


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


def _require_internal_materialization_token(provided: str | None) -> None:
    expected = os.getenv("RCI_INTERNAL_SERVICE_TOKEN", "").strip()
    if not expected or not provided or not secrets.compare_digest(expected, provided):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated internal service access is required.",
        )


@router.get("/analyses/{analysis_id}/price-monitoring")
async def price_monitoring_view(
    analysis_id: str,
    service: ServiceDependency,
    retailer: str = Query(min_length=1),
    brand_type: BrandFilter = "all",
    state_filter: str | None = Query(default=None, alias="state"),
    city: str | None = None,
    zipcode: str | None = None,
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
                zipcode=zipcode,
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


@router.get("/analyses/{analysis_id}/price-monitoring/catalog")
async def price_monitoring_catalog(
    analysis_id: str,
    service: ServiceDependency,
    retailer: str = Query(min_length=1),
    query: str | None = Query(default=None, alias="q", max_length=200),
    brand_type: BrandFilter = "all",
    brand: str | None = Query(default=None, max_length=200),
    seller: str | None = Query(default=None, max_length=200),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=40, ge=1, le=100),
) -> dict[str, Any]:
    try:
        return await service.catalog_page(
            analysis_id,
            retailer,
            query=query,
            brand_type=brand_type,
            brand=brand,
            seller=seller,
            offset=offset,
            limit=limit,
        )
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/internal/analyses/{analysis_id}/price-monitoring/catalog/materialize")
async def materialize_price_monitoring_catalog(
    analysis_id: str,
    service: ServiceDependency,
    retailer: str = Query(min_length=1),
    x_rci_internal_token: Annotated[str | None, Header(alias="X-RCI-Internal-Token")] = None,
) -> dict[str, Any]:
    _require_internal_materialization_token(x_rci_internal_token)
    try:
        document = await service.materialize_catalog(
            analysis_id,
            retailer,
            refresh=True,
            publish=True,
        )
        return {
            "analysis_id": analysis_id,
            "retailer_id": retailer,
            "status": "materialized",
            "product_count": len(document.get("products", [])),
            "provider_calls_queued": 0,
        }
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.get("/analyses/{analysis_id}/price-architecture-matrix")
async def price_architecture_matrix(
    analysis_id: str,
    service: ServiceDependency,
    mode: PriceArchitectureMode = "benchmark_anchored",
    fixed_increment: float = Query(default=0.5, alias="fixed_increment"),
    brand_type: BrandFilter = "all",
    brand: str | None = None,
    state_filter: str | None = Query(default=None, alias="state"),
    city: str | None = None,
    zipcode: str | None = None,
) -> dict[str, Any]:
    try:
        return await service.architecture_matrix(
            analysis_id,
            mode=mode,
            fixed_increment=fixed_increment,
            brand_type=brand_type,
            brand=brand,
            state=state_filter,
            city=city,
            zipcode=zipcode,
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


@router.post("/internal/analyses/{analysis_id}/price-architecture-matrix/materialize")
async def materialize_price_architecture_matrix(
    analysis_id: str,
    service: ServiceDependency,
    x_rci_internal_token: Annotated[str | None, Header(alias="X-RCI-Internal-Token")] = None,
) -> dict[str, Any]:
    _require_internal_materialization_token(x_rci_internal_token)
    try:
        matrices = await service.pre_materialize_architecture_matrices(
            analysis_id,
            refresh=True,
        )
        return {
            "analysis_id": analysis_id,
            "status": "materialized",
            "matrix_count": len(matrices),
            "provider_calls_queued": 0,
        }
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (LookupError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.get("/analyses/{analysis_id}/price-monitoring/map")
async def price_monitoring_map(
    analysis_id: str,
    service: ServiceDependency,
    retailer: str = Query(min_length=1),
    brand_type: BrandFilter = "all",
    state_filter: str | None = Query(default=None, alias="state"),
    city: str | None = None,
    zipcode: str | None = None,
    product_id: str = Query(min_length=1),
    detail: Literal["summary", "full"] = "full",
) -> dict[str, Any]:
    try:
        return await service.map_view(
            analysis_id,
            PriceMonitoringFilters(
                retailer_id=retailer,
                brand_type=brand_type,
                state=state_filter,
                city=city,
                zipcode=zipcode,
                product_id=product_id,
            ),
            detail=detail,
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


@router.get("/analyses/{analysis_id}/price-monitoring/evidence.csv")
async def price_monitoring_evidence_csv(
    analysis_id: str,
    service: ServiceDependency,
    retailer: str = Query(min_length=1),
    product_id: str = Query(min_length=1),
    brand_type: BrandFilter = "all",
    state_filter: str | None = Query(default=None, alias="state"),
    city: str | None = None,
    zipcode: str | None = None,
) -> Response:
    try:
        body = await service.evidence_csv(
            analysis_id,
            PriceMonitoringFilters(
                retailer_id=retailer,
                brand_type=brand_type,
                state=state_filter,
                city=city,
                zipcode=zipcode,
                product_id=product_id,
            ),
        )
        safe_retailer = "".join(
            character for character in retailer if character.isalnum() or character in "_-"
        )
        safe_product_id = "".join(
            character for character in product_id if character.isalnum() or character in "_-"
        )
        filename = (
            f"{safe_retailer or 'retailer'}-{safe_product_id or 'product'}-price-evidence.csv"
        )
        return Response(
            content=body,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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
