"""Search-authoritative retailer price-monitoring read model and API."""

from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import os
from dataclasses import dataclass
from io import BytesIO, StringIO
from pathlib import Path
from typing import Annotated, Any, Literal

import polars as pl
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from rci_analytics import (
    CatalogProductPackLoader,
    PriceMonitoringFilters,
    PriceMonitoringProjector,
    ProductPriceObservation,
    classified_offer_from_record,
    location_scope_key,
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
    retailer_options: tuple[str, ...]


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
        frame = await asyncio.to_thread(pl.read_parquet, BytesIO(body))
        available = [column for column in columns if column in frame.columns]
        return frame.select(available).to_dicts()


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
        self._view_cache: dict[tuple[str, ...], dict[str, Any]] = {}
        self._map_cache: dict[tuple[str, ...], dict[str, Any]] = {}
        catalog = json.loads((repository_root / "config" / "retailer-catalog.json").read_text())
        self._retailer_names = {
            str(row["id"]): str(row["display_name"])
            for row in catalog.get("retailers", [])
            if isinstance(row, dict) and row.get("id") and row.get("display_name")
        }

    async def _prepare(
        self,
        analysis_id: str,
        retailer_id: str,
    ) -> PreparedPriceMonitoringData:
        cache_key = (analysis_id, retailer_id)
        cached = self._prepared_cache.get(cache_key)
        if cached is not None:
            return cached
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
            records: list[dict[str, Any]] = []
            for artifact in artifacts:
                records.extend(await self._reader.read(artifact))
            offers = tuple(classified_offer_from_record(record) for record in records)
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
            product_context = await self._repository.product_context(
                retailer_id,
                product_ids,
            )
            source = result.get("source", {})
            revision_id = (
                str(source["brand_revision_id"]) if source.get("brand_revision_id") else None
            )
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
            prepared = PreparedPriceMonitoringData(
                analysis=analysis,
                projector=PriceMonitoringProjector(
                    pack,
                    resolver,
                    retailer_names=self._retailer_names,
                ),
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
                retailer_options=retailer_options,
            )
            if len(self._prepared_cache) >= 8:
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
        )

    async def view(self, analysis_id: str, filters: PriceMonitoringFilters) -> dict[str, Any]:
        if filters.city is not None and filters.state is None:
            raise ValueError("a city filter requires its state")
        cache_key = self._view_key(analysis_id, filters)
        cached = self._view_cache.get(cache_key)
        if cached is not None:
            return cached
        prepared = await self._prepare(analysis_id, filters.retailer_id)
        view = self._project(
            prepared,
            filters,
            product_location_limit=200 if filters.product_id else 0,
        )
        validate_instance(
            self._root,
            "price-monitoring-view.schema.json",
            view,
            label=f"price-monitoring:{prepared.analysis.analysis_id}:{filters.retailer_id}",
        )
        if len(self._view_cache) >= 96:
            self._view_cache.pop(next(iter(self._view_cache)))
        self._view_cache[cache_key] = view
        return view

    async def product_observations(
        self,
        analysis_id: str,
        *,
        retailer_id: str,
        product_id: str,
        comparison_metric: str,
    ) -> list[ProductPriceObservation]:
        """Return latest positive Search evidence at exact product-location grain."""

        prepared = await self._prepare(analysis_id, retailer_id)
        context = prepared.product_context.get(f"{retailer_id}:{product_id}", {})
        selected: dict[str, tuple[tuple[str, str], ProductPriceObservation]] = {}
        for classified in prepared.offers:
            offer = classified.offer
            comparison_value = (
                offer.price
                if comparison_metric == "package_price"
                else classified.metrics.get(comparison_metric)
            )
            if (
                not classified.in_scope
                or offer.retailer_id != retailer_id
                or offer.retailer_product_id != product_id
                or offer.price is None
                or offer.price <= 0
                or comparison_value is None
                or comparison_value <= 0
                or offer.currency != "USD"
            ):
                continue
            location_kind: Literal["store", "service_area"] = (
                "store" if offer.store_number is not None else "service_area"
            )
            location_key = offer.store_number or (
                f"zip:{offer.zipcode}" if offer.zipcode is not None else None
            )
            if location_key is None:
                continue
            location = prepared.location_index.get((retailer_id, location_key), {})
            scope_key = location_scope_key(offer)
            observation = ProductPriceObservation(
                retailer_id=retailer_id,
                retailer_name=self._retailer_names.get(
                    retailer_id, retailer_id.replace("_", " ").title()
                ),
                product_id=product_id,
                product_name=str(context.get("name") or offer.title),
                image_url=(
                    str(context["image_url"]) if context.get("image_url") else offer.image_url
                ),
                scope_key=scope_key,
                location_kind=location_kind,
                store_number=offer.store_number,
                store_name=(str(location["store_name"]) if location.get("store_name") else None),
                zipcode=(str(location["zipcode"]) if location.get("zipcode") else offer.zipcode),
                city=str(location["city"]) if location.get("city") else None,
                state=str(location["state"]) if location.get("state") else None,
                country=str(location.get("country") or "USA"),
                latitude=(
                    float(location["latitude"])
                    if location.get("latitude") is not None
                    else offer.latitude
                ),
                longitude=(
                    float(location["longitude"])
                    if location.get("longitude") is not None
                    else offer.longitude
                ),
                package_price=float(offer.price),
                comparison_value=float(comparison_value),
                observed_at=offer.collected_at,
            )
            rank = (str(offer.collected_at or ""), offer.offer_id)
            previous = selected.get(scope_key)
            if previous is None or rank > previous[0]:
                selected[scope_key] = (rank, observation)
        return [
            value[1]
            for _scope, value in sorted(
                selected.items(),
                key=lambda item: (
                    str(item[1][1].state or ""),
                    str(item[1][1].city or ""),
                    str(item[1][1].store_number or item[1][1].zipcode or ""),
                ),
            )
        ]

    async def evidence_csv(
        self,
        analysis_id: str,
        filters: PriceMonitoringFilters,
    ) -> str:
        if not filters.product_id:
            raise ValueError("a product_id is required for evidence export")
        prepared = await self._prepare(analysis_id, filters.retailer_id)
        view = self._project(
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
        view = self._project(
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
