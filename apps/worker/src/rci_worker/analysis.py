"""Durable post-collection orchestration for the generic analytics vertical slice."""

from __future__ import annotations

import asyncio
import copy
import csv
import gzip
import hashlib
import io
import json
import logging
import tempfile
from collections import Counter, defaultdict
from collections.abc import AsyncIterator, Iterable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rci_agents import GovernedAnalysisAssistant
from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncEngine

from rci_analytics import (
    AnalysisResultV2Builder,
    AssortmentAccumulator,
    CanonicalOfferNormalizer,
    CatalogProductPackLoader,
    ComparisonEngine,
    ComparisonFact,
    ComparisonInputReducer,
    ListingEvidenceAccumulatorV2,
    MatchingShadowEvaluatorV2,
    OfferClassifier,
    ParquetDatasetWriter,
    ProductMatchRule,
    ProductPackLoader,
    RelationshipInputReducer,
    benchmark_product_decisions,
    benchmark_product_map_points,
    benchmark_product_match_candidates,
    complete_attributes_from_pdp,
    evidence_set,
    merge_assortment_product_context,
    product_context_index,
    resolve_one_to_one_relationships,
)
from rci_analytics.historical_repository import PostgresAnalysisInputRepository
from rci_analytics.models import MatchRecord
from rci_analytics.normalization import RetailerIdentityMap
from rci_analytics.product_pack import ProductPack
from rci_collections.models import QueueTask
from rci_collections.repository import PostgresCollectionRepository
from rci_products import ProductDetailRepository
from rci_providers import MetricsCartAdapterRegistry
from rci_results import AnalysisResultService, ReportBlueprintLoader
from rci_results.brand_review import BrandReviewRepository, BrandRuleRecord
from rci_results.match_review import MatchReviewRepository
from rci_retailer_packs import (
    BrandDecisionOverride,
    GovernedBrandResolver,
    GovernedSellerResolver,
)

logger = logging.getLogger(__name__)


def _normalized_brand_name(value: str) -> str:
    return " ".join(
        "".join(character if character.isalnum() else " " for character in value.casefold()).split()
    )


def apply_brand_classification_rules(
    pack: ProductPack, rules: Iterable[BrandRuleRecord]
) -> ProductPack:
    """Overlay a governed brand revision without mutating the exact catalog version."""

    document = copy.deepcopy(pack.document)
    private_labels = document.setdefault("brand_rules", {}).setdefault("private_labels", {})
    for rule in rules:
        values = [
            str(value)
            for value in private_labels.get(rule.retailer_id, [])
            if _normalized_brand_name(str(value)) != rule.normalized_brand
        ]
        if rule.decision == "confirmed" and rule.role == "private_label":
            values.append(rule.display_brand)
        private_labels[rule.retailer_id] = sorted(set(values), key=str.casefold)
    return replace(pack, document=document)


@dataclass(frozen=True, slots=True)
class AnalysisJob:
    id: str
    collection_run_id: str
    input_set_id: str
    source_kind: str
    product_pack_id: str
    product_pack_version: str
    definition_config: dict[str, Any]
    attempt_count: int
    max_attempts: int
    match_revision_id: str | None = None
    brand_revision_id: str | None = None
    source_analysis_id: str | None = None


@dataclass(frozen=True, slots=True)
class CollectedPage:
    task: QueueTask
    storage_uri: str
    checksum: str
    collected_at: datetime
    latitude: float | None
    longitude: float | None


@dataclass(frozen=True, slots=True)
class HistoricalSource:
    dataset_artifact_id: str
    input_set_id: str
    ordinal: int
    retailer_id: str
    adapter_id: str
    source_name: str
    source_format: str
    storage_uri: str
    checksum: str
    row_count: int


def historical_source_row(row: dict[str, str], source: HistoricalSource) -> dict[str, str]:
    """Preserve row retailer identity for consolidated multi-retailer exports."""

    if source.source_format == "metricscart_consolidated_serp_csv":
        return dict(row)
    return {**row, "retailer_id": source.retailer_id}


def _task(row: RowMapping) -> QueueTask:
    return QueueTask(
        id=str(row["id"]),
        collection_run_id=str(row["collection_run_id"]),
        retailer_id=str(row["retailer_id"]),
        retailer_location_id=(
            str(row["retailer_location_id"]) if row["retailer_location_id"] is not None else None
        ),
        adapter_id=str(row["adapter_id"]),
        location_scope_key=str(row["location_scope_key"]),
        zipcode=str(row["zipcode"]),
        store_number=str(row["store_number"]) if row["store_number"] is not None else None,
        page_number=int(row["page_number"]),
        max_pages=int(row["max_pages"]),
        stop_on_empty=bool(row["stop_on_empty"]),
        stop_on_short_page=bool(row["stop_on_short_page"]),
        credits_per_success=int(row["credits_per_success"]),
        request_payload=dict(row["request_payload"]),
        request_fingerprint=str(row["request_fingerprint"]),
        status=str(row["status"]),
        priority=int(row["priority"]),
        attempt_count=int(row["attempt_count"]),
        max_attempts=int(row["max_attempts"]),
        available_at=row["available_at"],
        locked_by=str(row["locked_by"]) if row["locked_by"] is not None else None,
        lease_expires_at=row["lease_expires_at"],
        created_at=row["created_at"],
        http_status=int(row["http_status"]) if row["http_status"] is not None else None,
        result_count=int(row["result_count"]) if row["result_count"] is not None else None,
        failure_class=(str(row["failure_class"]) if row["failure_class"] is not None else None),
        last_error=str(row["last_error"]) if row["last_error"] is not None else None,
        billable_credits=int(row["billable_credits"]),
        raw_artifact_id=(
            str(row["raw_artifact_id"]) if row["raw_artifact_id"] is not None else None
        ),
        is_preflight=bool(row["is_preflight"]),
    )


class PostgresAnalysisQueue:
    def __init__(
        self,
        engine: AsyncEngine,
        *,
        code_version: str,
        max_attempts: int = 3,
        historical_replay_enabled: bool = False,
    ) -> None:
        self._engine = engine
        self._code_version = code_version
        self._max_attempts = max_attempts
        self._historical_replay_enabled = historical_replay_enabled
        self._inputs = PostgresAnalysisInputRepository(engine)

    async def materialize(self) -> int:
        return await self._inputs.materialize_live(
            code_version=self._code_version,
            max_attempts=self._max_attempts,
        )

    async def claim(self, worker_id: str, *, limit: int, lease_seconds: int) -> list[AnalysisJob]:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    UPDATE analysis_run
                    SET status = 'failed', completed_at = now(),
                        last_error = 'Analysis lease expired after maximum attempts',
                        locked_by = NULL, locked_at = NULL, lease_expires_at = NULL
                    WHERE status = 'running' AND lease_expires_at <= now()
                      AND attempt_count >= max_attempts
                    """
                )
            )
            rows = (
                (
                    await connection.execute(
                        text(
                            """
                            WITH candidates AS (
                              SELECT ar.id
                              FROM analysis_run ar
                              WHERE (
                                (ar.status = 'queued' AND ar.available_at <= now()) OR
                                (ar.status = 'running' AND ar.lease_expires_at <= now())
                              )
                                AND ar.attempt_count < ar.max_attempts
                                AND (
                                  :historical_replay_enabled OR ar.match_revision_id IS NOT NULL OR
                                  ar.brand_revision_id IS NOT NULL OR
                                  NOT EXISTS (
                                    SELECT 1 FROM analysis_input_set source
                                    WHERE source.id = ar.input_set_id
                                      AND source.source_kind = 'historical_import'
                                  )
                                )
                              ORDER BY ar.available_at, ar.created_at, ar.id
                              FOR UPDATE OF ar SKIP LOCKED
                              LIMIT :limit
                            )
                            UPDATE analysis_run ar
                            SET status = 'running', locked_by = :worker_id, locked_at = now(),
                                lease_expires_at = now() + make_interval(secs => :lease_seconds),
                                attempt_count = ar.attempt_count + 1,
                                started_at = COALESCE(ar.started_at, now()), completed_at = NULL
                            FROM candidates c,
                                 analysis_input_set i,
                                 collection_run cr,
                                 collection_definition_version v
                            WHERE ar.id = c.id AND cr.id = ar.collection_run_id
                              AND i.id = ar.input_set_id AND i.status = 'ready'
                              AND v.id = cr.definition_version_id
                            RETURNING ar.id::text, ar.collection_run_id::text,
                              ar.input_set_id::text, i.source_kind,
                              ar.product_pack_id, ar.product_pack_version,
                              ar.attempt_count, ar.max_attempts, v.config,
                              ar.match_revision_id::text,
                              ar.brand_revision_id::text,
                              (
                                SELECT source_result.analysis_id
                                FROM analysis_result source_result
                                WHERE source_result.id = ar.source_analysis_result_id
                              ) AS source_analysis_id
                            """
                        ),
                        {
                            "worker_id": worker_id,
                            "limit": limit,
                            "lease_seconds": lease_seconds,
                            "historical_replay_enabled": self._historical_replay_enabled,
                        },
                    )
                )
                .mappings()
                .all()
            )
            return [
                AnalysisJob(
                    id=str(row["id"]),
                    collection_run_id=str(row["collection_run_id"]),
                    input_set_id=str(row["input_set_id"]),
                    source_kind=str(row["source_kind"]),
                    product_pack_id=str(row["product_pack_id"]),
                    product_pack_version=str(row["product_pack_version"]),
                    definition_config=dict(row["config"]),
                    attempt_count=int(row["attempt_count"]),
                    max_attempts=int(row["max_attempts"]),
                    match_revision_id=(
                        str(row["match_revision_id"])
                        if row["match_revision_id"] is not None
                        else None
                    ),
                    brand_revision_id=(
                        str(row["brand_revision_id"])
                        if row["brand_revision_id"] is not None
                        else None
                    ),
                    source_analysis_id=(
                        str(row["source_analysis_id"])
                        if row["source_analysis_id"] is not None
                        else None
                    ),
                )
                for row in rows
            ]

    async def extend_lease(self, job_id: str, worker_id: str, lease_seconds: int) -> bool:
        async with self._engine.begin() as connection:
            result = await connection.execute(
                text(
                    """
                    UPDATE analysis_run
                    SET lease_expires_at = now() + make_interval(secs => :lease_seconds)
                    WHERE id::text = :job_id AND status = 'running'
                      AND locked_by = :worker_id AND lease_expires_at > now()
                    RETURNING id
                    """
                ),
                {
                    "job_id": job_id,
                    "worker_id": worker_id,
                    "lease_seconds": lease_seconds,
                },
            )
            return result.first() is not None

    async def fail(self, job: AnalysisJob, worker_id: str, error: str) -> None:
        retry = job.attempt_count < job.max_attempts
        delay = min(30 * (2 ** max(job.attempt_count - 1, 0)), 300)
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    UPDATE analysis_run
                    SET status = :status,
                        available_at = now() + make_interval(secs => :delay),
                        completed_at = CASE WHEN :retry THEN NULL ELSE now() END,
                        locked_by = NULL, locked_at = NULL, lease_expires_at = NULL,
                        last_error = :error
                    WHERE id::text = :job_id AND status = 'running'
                      AND locked_by = :worker_id
                    """
                ),
                {
                    "job_id": job.id,
                    "worker_id": worker_id,
                    "status": "queued" if retry else "failed",
                    "delay": delay,
                    "retry": retry,
                    "error": error[:4_000],
                },
            )

    async def pages(self, run_id: str) -> list[CollectedPage]:
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT t.*, da.storage_uri, da.checksum,
                                   da.created_at AS artifact_created_at,
                                   l.latitude, l.longitude
                            FROM collection_task t
                            JOIN dataset_artifact da ON da.id = t.raw_artifact_id
                            LEFT JOIN retailer_location l ON l.id = t.retailer_location_id
                            WHERE t.collection_run_id::text = :run_id
                              AND t.status = 'succeeded'
                              AND t.http_status BETWEEN 200 AND 299
                            ORDER BY t.retailer_id, t.location_scope_key, t.page_number, t.id
                            """
                        ),
                        {"run_id": run_id},
                    )
                )
                .mappings()
                .all()
            )
        return [
            CollectedPage(
                task=_task(row),
                storage_uri=str(row["storage_uri"]),
                checksum=str(row["checksum"]),
                collected_at=row["artifact_created_at"],
                latitude=float(row["latitude"]) if row["latitude"] is not None else None,
                longitude=float(row["longitude"]) if row["longitude"] is not None else None,
            )
            for row in rows
        ]

    async def historical_sources(self, input_set_id: str) -> list[HistoricalSource]:
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT ia.input_set_id::text, ia.ordinal, ia.retailer_id,
                                   ia.adapter_id, ia.source_name, ia.source_format,
                                   ia.row_count, da.id::text AS dataset_artifact_id,
                                   da.storage_uri, da.checksum
                            FROM analysis_input_artifact ia
                            JOIN dataset_artifact da ON da.id = ia.dataset_artifact_id
                            JOIN analysis_input_set i ON i.id = ia.input_set_id
                            WHERE ia.input_set_id::text = :input_set_id
                              AND i.source_kind = 'historical_import'
                              AND i.status = 'ready'
                            ORDER BY ia.ordinal
                            """
                        ),
                        {"input_set_id": input_set_id},
                    )
                )
                .mappings()
                .all()
            )
        return [
            HistoricalSource(
                dataset_artifact_id=str(row["dataset_artifact_id"]),
                input_set_id=str(row["input_set_id"]),
                ordinal=int(row["ordinal"]),
                retailer_id=str(row["retailer_id"]),
                adapter_id=str(row["adapter_id"]),
                source_name=str(row["source_name"]),
                source_format=str(row["source_format"]),
                storage_uri=str(row["storage_uri"]),
                checksum=str(row["checksum"]),
                row_count=int(row["row_count"]),
            )
            for row in rows
        ]


class S3RawPageReader:
    def __init__(self, *, bucket: str, client: Any) -> None:
        self._bucket = bucket
        self._client = client

    async def read(self, page: CollectedPage) -> object:
        prefix = f"s3://{self._bucket}/"
        if not page.storage_uri.startswith(prefix):
            raise ValueError("raw provider object belongs to a different bucket")
        key = page.storage_uri.removeprefix(prefix)

        def get() -> bytes:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
            return bytes(response["Body"].read())

        compressed = await asyncio.to_thread(get)
        if hashlib.sha256(compressed).hexdigest() != page.checksum:
            raise ValueError(f"raw provider checksum mismatch for task {page.task.id}")
        return json.loads(gzip.decompress(compressed))


class S3HistoricalCSVReader:
    def __init__(self, *, bucket: str, client: Any) -> None:
        self._bucket = bucket
        self._client = client

    async def read(self, source: HistoricalSource) -> list[dict[str, str]]:
        prefix = f"s3://{self._bucket}/"
        if not source.storage_uri.startswith(prefix):
            raise ValueError("historical source object belongs to a different bucket")
        key = source.storage_uri.removeprefix(prefix)

        def get() -> list[dict[str, str]]:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
            body = bytes(response["Body"].read())
            if hashlib.sha256(body).hexdigest() != source.checksum:
                raise ValueError(f"historical source checksum mismatch for {source.source_name}")
            reader = csv.DictReader(io.StringIO(body.decode("utf-8-sig"), newline=""))
            rows = [dict(row) for row in reader]
            if len(rows) != source.row_count:
                raise ValueError(
                    f"historical source row count mismatch for {source.source_name}: "
                    f"expected {source.row_count}, found {len(rows)}"
                )
            return rows

        return await asyncio.to_thread(get)

    async def iter_batches(
        self,
        source: HistoricalSource,
        *,
        batch_size: int = 5_000,
    ) -> AsyncIterator[list[dict[str, str]]]:
        """Download with checksum verification, then yield bounded CSV row batches."""

        if batch_size < 1:
            raise ValueError("historical CSV batch size must be positive")
        prefix = f"s3://{self._bucket}/"
        if not source.storage_uri.startswith(prefix):
            raise ValueError("historical source object belongs to a different bucket")
        key = source.storage_uri.removeprefix(prefix)

        def download() -> Path:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
            digest = hashlib.sha256()
            path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="wb", prefix="rci-historical-", suffix=".csv", delete=False
                ) as target:
                    path = Path(target.name)
                    body = response["Body"]
                    while chunk := body.read(1024 * 1024):
                        digest.update(chunk)
                        target.write(chunk)
            except Exception:
                if path is not None:
                    path.unlink(missing_ok=True)
                raise
            assert path is not None
            if digest.hexdigest() != source.checksum:
                path.unlink(missing_ok=True)
                raise ValueError(f"historical source checksum mismatch for {source.source_name}")
            return path

        path = await asyncio.to_thread(download)
        row_count = 0
        try:
            with path.open(newline="", encoding="utf-8-sig") as handle:
                reader = csv.DictReader(handle)
                batch: list[dict[str, str]] = []
                for row in reader:
                    batch.append(dict(row))
                    row_count += 1
                    if len(batch) >= batch_size:
                        yield batch
                        batch = []
                        await asyncio.sleep(0)
                if batch:
                    yield batch
            if row_count != source.row_count:
                raise ValueError(
                    f"historical source row count mismatch for {source.source_name}: "
                    f"expected {source.row_count}, found {row_count}"
                )
        finally:
            path.unlink(missing_ok=True)


class AnalysisProcessor:
    def __init__(
        self,
        *,
        repository_root: Path,
        queue: PostgresAnalysisQueue,
        adapters: MetricsCartAdapterRegistry,
        raw_reader: S3RawPageReader,
        dataset_writer: ParquetDatasetWriter,
        collections: PostgresCollectionRepository,
        results: AnalysisResultService,
        code_version: str,
        historical_reader: S3HistoricalCSVReader | None = None,
        assistant: GovernedAnalysisAssistant | None = None,
        match_reviews: MatchReviewRepository | None = None,
        brand_reviews: BrandReviewRepository | None = None,
        product_packs: CatalogProductPackLoader | None = None,
        product_details: ProductDetailRepository | None = None,
        matching_v2_shadow_enabled: bool = False,
    ) -> None:
        self._root = repository_root
        self._queue = queue
        self._adapters = adapters
        self._raw_reader = raw_reader
        self._historical_reader = historical_reader
        self._dataset_writer = dataset_writer
        self._collections = collections
        self._results = results
        self._code_version = code_version
        self._assistant = assistant
        self._match_reviews = match_reviews
        self._brand_reviews = brand_reviews
        self._product_packs = product_packs
        self._product_details = product_details
        self._matching_v2_shadow_enabled = matching_v2_shadow_enabled

    async def process(self, job: AnalysisJob) -> str:
        pack = (
            await self._product_packs.load(job.product_pack_id, job.product_pack_version)
            if self._product_packs is not None
            else ProductPackLoader(self._root).load(job.product_pack_id)
        )
        if pack.version != job.product_pack_version:
            raise ValueError(
                f"Product Pack version mismatch: requested {job.product_pack_version}, "
                f"loaded {pack.version}"
            )
        if job.brand_revision_id is not None:
            if self._brand_reviews is None:
                raise ValueError("governed reanalysis requires a brand-review repository")
            brand_rules = await self._brand_reviews.rules(job.brand_revision_id)
            pack = apply_brand_classification_rules(pack, brand_rules)
        else:
            brand_rules = []
        benchmark = str(job.definition_config["benchmark_retailer"])
        analysis_options = job.definition_config.get("analysis", {})
        configured_profiles = (
            analysis_options.get("comparison_profiles", [])
            if isinstance(analysis_options, dict)
            else []
        )
        requested_profile_ids = {str(profile_id) for profile_id in configured_profiles}
        available_profile_ids = {str(profile["id"]) for profile in pack.matching_profiles}
        unknown_profile_ids = requested_profile_ids - available_profile_ids
        if unknown_profile_ids:
            raise ValueError(
                f"Product Pack has no comparison profiles {sorted(unknown_profile_ids)}"
            )
        selected_profiles = [
            profile
            for profile in pack.matching_profiles
            if not requested_profile_ids or str(profile["id"]) in requested_profile_ids
        ]
        configured_retailers = [
            str(value["retailer_id"])
            for value in job.definition_config.get("retailers", [])
            if isinstance(value, dict) and bool(value.get("enabled"))
        ]
        competitors = [value for value in configured_retailers if value != benchmark]

        normalizer = CanonicalOfferNormalizer(
            RetailerIdentityMap.from_catalog(self._root / "config" / "retailer-catalog.json")
        )
        brand_resolver = GovernedBrandResolver.from_repository(self._root)
        if brand_rules:
            brand_resolver = brand_resolver.with_overrides(
                [
                    BrandDecisionOverride(
                        retailer_id=rule.retailer_id,
                        normalized_brand=rule.normalized_brand,
                        display_brand=rule.display_brand,
                        role=rule.role,  # type: ignore[arg-type]
                        decision=rule.decision,  # type: ignore[arg-type]
                        canonical_brand_id=(
                            str(rule.evidence["canonical_brand_id"])
                            if rule.evidence.get("canonical_brand_id")
                            else None
                        ),
                        canonical_brand_name=(
                            str(rule.evidence["canonical_brand_name"])
                            if rule.evidence.get("canonical_brand_name")
                            else None
                        ),
                    )
                    for rule in brand_rules
                ]
            )
        classifier = OfferClassifier(pack, brand_resolver)
        seller_resolver = GovernedSellerResolver.from_repository(self._root)
        engine = ComparisonEngine(pack, brand_resolver)
        governed_rules: list[ProductMatchRule] = []
        if job.match_revision_id is not None:
            if self._match_reviews is None:
                raise ValueError("governed reanalysis requires a match-review repository")
            governed_rules = [
                ProductMatchRule(
                    competitor_id=rule.competitor_retailer_id,
                    profile_id=rule.source_profile_id,
                    benchmark_product_id=rule.benchmark_product_id,
                    competitor_product_id=rule.competitor_product_id,
                    decision=rule.decision,
                    eligible_profile_ids=rule.eligible_profile_ids,
                    comparison_family_key=rule.comparison_family_key,
                    relationship_role=rule.relationship_role,
                    scope_mode=rule.scope_mode,
                    scope_definition=rule.scope_definition,
                    scope_checksum=rule.scope_checksum,
                )
                for rule in await self._match_reviews.rules(job.match_revision_id)
            ]
        reducer = ComparisonInputReducer(pack, profile_ids=requested_profile_ids)
        relationship_reducer = RelationshipInputReducer(pack, profile_ids=requested_profile_ids)
        assortment_accumulator = AssortmentAccumulator()
        matching_v2_accumulator = (
            ListingEvidenceAccumulatorV2(pack)
            if self._matching_v2_shadow_enabled and pack.matching_v2 is not None
            else None
        )
        pdp_context: dict[str, dict[str, Any]] = {}
        raw_artifact_ids: list[str] = []
        source_evidence_artifacts: list[tuple[str, str, int]] = []
        provider_rows_count = 0
        normalized_count = 0
        review_offer_count = 0
        zero_or_missing_price_count = 0
        seen_offer_ids: set[str] = set()
        offer_counts: dict[str, int] = defaultdict(int)
        in_scope_counts: dict[str, int] = defaultdict(int)
        in_scope_zips: dict[str, set[str]] = defaultdict(set)
        in_scope_stores: dict[str, set[str]] = defaultdict(set)
        seller_status_counts: dict[str, Counter[str]] = defaultdict(Counter)
        classified_evidence_artifacts: dict[str, list[tuple[str, str, int]]] = defaultdict(list)
        observed_values: list[str] = []
        normalized_batches: dict[str, list[Any]] = defaultdict(list)
        classified_batches: dict[str, list[Any]] = defaultdict(list)
        partitions: dict[str, int] = defaultdict(int)
        batch_size = 5_000

        async def flush(retailer_id: str) -> None:
            normalized_batch = normalized_batches[retailer_id]
            if not normalized_batch:
                return
            classified_batch = classified_batches[retailer_id]
            partition = partitions[retailer_id]
            normalized_artifact = await self._dataset_writer.write_normalized(
                normalized_batch,
                run_id=job.collection_run_id,
                retailer_id=retailer_id,
                partition=partition,
            )
            classified_artifact = await self._dataset_writer.write_classified(
                classified_batch,
                run_id=job.collection_run_id,
                retailer_id=retailer_id,
                partition=partition,
            )
            await self._collections.record_artifact(job.collection_run_id, normalized_artifact)
            classified_artifact_id = await self._collections.record_artifact(
                job.collection_run_id, classified_artifact
            )
            classified_evidence_artifacts[retailer_id].append(
                (
                    classified_artifact_id,
                    classified_artifact.checksum,
                    int(classified_artifact.row_count or 0),
                )
            )
            normalized_batch.clear()
            classified_batch.clear()
            partitions[retailer_id] += 1

        async def consume(row: dict[str, Any]) -> None:
            nonlocal provider_rows_count
            nonlocal normalized_count
            nonlocal review_offer_count
            nonlocal zero_or_missing_price_count
            provider_rows_count += 1
            try:
                normalized_offer = normalizer.normalize(row)
            except ValueError:
                return
            if normalized_offer.offer_id in seen_offer_ids:
                return
            seen_offer_ids.add(normalized_offer.offer_id)
            normalized_count += 1
            if normalized_offer.collected_at:
                observed_values.append(normalized_offer.collected_at)
            retailer_id = normalized_offer.retailer_id
            offer_counts[retailer_id] += 1
            classified_offer = complete_attributes_from_pdp(
                classifier.classify(normalized_offer),
                pdp_context.get(
                    f"{normalized_offer.retailer_id}:{normalized_offer.retailer_product_id}"
                ),
                classifier=classifier,
                pack=pack,
                seller_resolver=seller_resolver,
            )
            review_offer_count += bool(classified_offer.review_reasons)
            zero_or_missing_price_count += (
                normalized_offer.price is None or normalized_offer.price <= 0
            )
            seller_governance = classified_offer.attributes.get("_seller_governance")
            if isinstance(seller_governance, dict) and seller_governance.get("status"):
                seller_status_counts[retailer_id][str(seller_governance["status"])] += 1
            if classified_offer.in_scope:
                in_scope_counts[retailer_id] += 1
                if normalized_offer.zipcode is not None:
                    in_scope_zips[retailer_id].add(normalized_offer.zipcode)
                if normalized_offer.store_number is not None:
                    in_scope_stores[retailer_id].add(normalized_offer.store_number)
            reducer.add(classified_offer)
            relationship_reducer.add(classified_offer)
            assortment_accumulator.add(classified_offer)
            if matching_v2_accumulator is not None:
                matching_v2_accumulator.add(classified_offer)
            normalized_batches[retailer_id].append(normalized_offer)
            classified_batches[retailer_id].append(classified_offer)
            if len(normalized_batches[retailer_id]) >= batch_size:
                await flush(retailer_id)

        if job.source_kind == "live_collection":
            pages = await self._queue.pages(job.collection_run_id)
            if not pages:
                raise ValueError("completed collection has no successful raw provider pages")
            if self._product_details is not None:
                pdp_context = product_context_index(
                    await self._product_details.publication_highlights(
                        [
                            str(page.task.raw_artifact_id)
                            for page in pages
                            if page.task.raw_artifact_id is not None
                        ],
                        limit=1_000_000,
                        per_retailer_limit=1_000_000,
                    )
                )
            for page in pages:
                payload = await self._raw_reader.read(page)
                adapter = self._adapters.get(page.task.adapter_id)
                for result in adapter.extract_result_array(payload):
                    await consume(
                        {
                            **result,
                            **adapter.normalize_result(result, page.task),
                            "latitude": page.latitude,
                            "longitude": page.longitude,
                            "collected_at": page.collected_at.isoformat(),
                        }
                    )
                if page.task.raw_artifact_id is not None:
                    raw_artifact_ids.append(page.task.raw_artifact_id)
                    source_evidence_artifacts.append(
                        (
                            page.task.raw_artifact_id,
                            page.checksum,
                            int(page.task.result_count or 0),
                        )
                    )
        elif job.source_kind == "historical_import":
            if self._historical_reader is None:
                raise ValueError("historical input reader is not configured")
            sources = await self._queue.historical_sources(job.input_set_id)
            if not sources:
                raise ValueError("historical input set has no source artifacts")
            if self._product_details is not None:
                pdp_context = product_context_index(
                    await self._product_details.publication_highlights(
                        [source.dataset_artifact_id for source in sources],
                        limit=1_000_000,
                        per_retailer_limit=1_000_000,
                    )
                )
            for source in sources:
                iter_batches = getattr(self._historical_reader, "iter_batches", None)
                if callable(iter_batches):
                    async for rows in iter_batches(source, batch_size=batch_size):
                        for row in rows:
                            await consume(historical_source_row(row, source))
                else:
                    rows = await self._historical_reader.read(source)
                    for row in rows:
                        await consume(historical_source_row(row, source))
                raw_artifact_ids.append(source.dataset_artifact_id)
                source_evidence_artifacts.append(
                    (source.dataset_artifact_id, source.checksum, source.row_count)
                )
        else:
            raise ValueError(f"unsupported analysis input kind {job.source_kind!r}")

        for retailer_id in sorted(normalized_batches):
            await flush(retailer_id)

        comparison_offers = reducer.offers()
        relationship_offers = relationship_reducer.offers()

        if matching_v2_accumulator is not None:
            preferred_profile_id = str(
                pack.reporting["decision_rules"]["preferred_scorecard_profile_id"]
            )
            shadow_evaluator = MatchingShadowEvaluatorV2(pack, preferred_profile_id)
            shadow_decided_at = (
                max(observed_values) if observed_values else datetime.now(UTC).isoformat()
            )
            maximum_candidate_pairs = int(
                (pack.matching_v2 or {}).get("maximum_candidate_pairs", 250_000)
            )
            benchmark_listings = matching_v2_accumulator.listings(benchmark)
            for competitor_index, competitor in enumerate(competitors):
                try:
                    shadow_result = shadow_evaluator.evaluate_listings(
                        benchmark_listings,
                        matching_v2_accumulator.listings(competitor),
                        benchmark_retailer_id=benchmark,
                        competitor_retailer_id=competitor,
                        decided_at=shadow_decided_at,
                        maximum_candidate_pairs=maximum_candidate_pairs,
                    )
                    shadow_document = {
                        **shadow_result.summary(),
                        "analysis_run_id": job.id,
                        "collection_run_id": job.collection_run_id,
                        "authoritative_metrics_affected": False,
                        "edges": [edge.to_contract() for edge in shadow_result.edges],
                        "blocked_review_edges": [
                            edge.to_contract() for edge in shadow_result.blocked_review_edges
                        ],
                    }
                    shadow_artifact = await self._dataset_writer.write_matching_v2_shadow(
                        shadow_document,
                        run_id=job.collection_run_id,
                        retailer_id=competitor,
                        partition=competitor_index,
                    )
                    await self._collections.record_artifact(job.collection_run_id, shadow_artifact)
                    logger.info(
                        "matching v2 shadow projection completed",
                        extra={
                            "event": "matching_v2_shadow_completed",
                            "collection_run_id": job.collection_run_id,
                            "competitor_retailer_id": competitor,
                            "evaluated_pairs": shadow_result.evaluated_pairs,
                            "blocked_pairs": shadow_result.blocked_pairs,
                        },
                    )
                except Exception:
                    logger.exception(
                        "matching v2 shadow projection failed without affecting analysis",
                        extra={
                            "event": "matching_v2_shadow_failed",
                            "collection_run_id": job.collection_run_id,
                            "competitor_retailer_id": competitor,
                        },
                    )

        comparison_facts: list[ComparisonFact] = []
        comparison_evidence_sets: list[dict[str, Any]] = []
        map_matches: list[MatchRecord] = []
        review_matches: list[MatchRecord] = []
        candidate_matches: list[MatchRecord] = []
        match_relationships: list[dict[str, Any]] = []
        ambiguous_match_groups: list[dict[str, Any]] = []
        headline_segments = tuple(str(value) for value in pack.reporting["headline_segments"])
        decision_rules = pack.reporting["decision_rules"]
        profile_priority = [
            str(value)
            for value in decision_rules["profile_priority"]
            if any(
                str(profile["id"]) == str(value) and str(profile["geography"]) == "exact_zip"
                for profile in selected_profiles
            )
        ]
        for competitor in competitors:
            mapped_competitor = False
            ungoverned_by_profile: dict[str, list[MatchRecord]] = {}
            for profile in selected_profiles:
                profile_id = str(profile["id"])
                ungoverned_by_profile[profile_id] = (
                    engine.compare_governed(
                        relationship_offers,
                        benchmark_id=benchmark,
                        competitor_id=competitor,
                        profile_id=profile_id,
                        rules=governed_rules,
                        product_candidates=True,
                    )
                    if job.match_revision_id is not None
                    else engine.compare_products(
                        relationship_offers,
                        benchmark_id=benchmark,
                        competitor_id=competitor,
                        profile_id=profile_id,
                    )
                )
                if str(profile["geography"]) == "exact_zip":
                    candidate_matches.extend(ungoverned_by_profile[profile_id])
            resolution = resolve_one_to_one_relationships(
                relationship_offers,
                (
                    match
                    for profile_matches in ungoverned_by_profile.values()
                    for match in profile_matches
                ),
                benchmark_retailer=benchmark,
                profile_priority=profile_priority,
                profile_scope_policies={
                    str(profile["id"]): dict(profile.get("relationship_scope_policy", {}))
                    for profile in selected_profiles
                },
            )
            match_relationships.extend(dict(row) for row in resolution.relationships)
            ambiguous_match_groups.extend(dict(row) for row in resolution.ambiguous_groups)
            resolved_by_profile: dict[str, list[MatchRecord]] = defaultdict(list)
            for match in resolution.matches:
                resolved_by_profile[match.profile_id].append(match)
            for profile_index, profile in enumerate(selected_profiles):
                matches = resolved_by_profile.get(str(profile["id"]), [])
                if not matches:
                    continue
                artifact = await self._dataset_writer.write_matches(
                    matches,
                    run_id=job.collection_run_id,
                    retailer_id=competitor,
                    partition=profile_index,
                )
                artifact_id = await self._collections.record_artifact(
                    job.collection_run_id, artifact
                )
                profile_id = str(profile["id"])
                evidence_ref = f"evidence.matches.{competitor}.{profile_id}"
                geography = str(profile["geography"])
                comparison_metric = matches[0].comparison_metric
                if geography == "exact_zip":
                    review_matches.extend(matches)
                if (
                    not mapped_competitor
                    and geography == "exact_zip"
                    and comparison_metric == "package_price"
                ):
                    map_matches.extend(matches)
                    mapped_competitor = True
                if geography == "radius":
                    evidence_kind = "proximity_matches"
                elif comparison_metric != "package_price":
                    evidence_kind = "normalized_matches"
                elif str(profile.get("unknown_policy", "reject")) == "reject":
                    evidence_kind = "exact_matches"
                else:
                    evidence_kind = "compatible_matches"
                comparison_evidence_sets.append(
                    evidence_set(
                        evidence_ref,
                        evidence_kind,
                        [(artifact_id, artifact.checksum, int(artifact.row_count or 0))],
                    )
                )
                summary = asdict(engine.summarize(matches))
                summary_values = {
                    key: value
                    for key, value in summary.items()
                    if key not in {"profile_id", "competitor_id"}
                }
                profile_label = str(profile["label"])
                dimensions = tuple(str(value) for value in profile["dimensions"])
                radius_miles = float(profile["radius_miles"]) if geography == "radius" else None
                comparison_facts.append(
                    ComparisonFact(
                        values=summary_values,
                        competitor_id=competitor,
                        profile_id=profile_id,
                        profile_label=profile_label,
                        geography=geography,
                        comparison_metric=comparison_metric,
                        dimensions=dimensions,
                        evidence_ref=evidence_ref,
                        radius_miles=radius_miles,
                    )
                )
                segment_groups: dict[str, list[Any]] = defaultdict(list)
                segment_attributes: dict[str, dict[str, Any]] = {}
                for match in matches:
                    attributes = {
                        name: match.attributes.get(name)
                        for name in headline_segments
                        if name in match.attributes
                    }
                    if not attributes:
                        continue
                    key = json.dumps(attributes, ensure_ascii=False, sort_keys=True)
                    segment_groups[key].append(match)
                    segment_attributes[key] = attributes
                for segment_key, segment_matches in sorted(
                    segment_groups.items(),
                    key=lambda item: (-len(item[1]), item[0]),
                ):
                    attributes = segment_attributes[segment_key]
                    segment_id = f"segment-{hashlib.sha256(segment_key.encode()).hexdigest()[:16]}"
                    segment_label = " / ".join(
                        f"{name.replace('_', ' ').title()}: {value}"
                        for name, value in attributes.items()
                    )
                    segment_summary = asdict(engine.summarize(segment_matches))
                    segment_values = {
                        key: value
                        for key, value in segment_summary.items()
                        if key not in {"profile_id", "competitor_id"}
                    }
                    comparison_facts.append(
                        ComparisonFact(
                            values=segment_values,
                            segment_id=segment_id,
                            segment_label=segment_label,
                            attributes=attributes,
                            competitor_id=competitor,
                            profile_id=profile_id,
                            profile_label=profile_label,
                            geography=geography,
                            comparison_metric=comparison_metric,
                            dimensions=dimensions,
                            evidence_ref=evidence_ref,
                            radius_miles=radius_miles,
                        )
                    )

        coverage = [
            {
                "retailer_id": retailer_id,
                "offers": offers,
                "in_scope_offers": in_scope_counts[retailer_id],
                "in_scope_zips": len(in_scope_zips[retailer_id]),
                "in_scope_stores": len(in_scope_stores[retailer_id]),
                "seller_verified_first_party_offers": seller_status_counts[retailer_id][
                    "verified_first_party"
                ],
                "seller_unverified_offers": seller_status_counts[retailer_id]["seller_unverified"],
                "third_party_excluded_offers": seller_status_counts[retailer_id][
                    "excluded_third_party"
                ],
                "evidence_ref": f"evidence.classified.{retailer_id}",
            }
            for retailer_id, offers in sorted(offer_counts.items())
        ]
        generated_at = datetime.now(UTC)
        analysis_id = f"{pack.id}-{job.collection_run_id}"
        if job.match_revision_id is not None:
            analysis_id = f"{analysis_id}-match-{job.match_revision_id[:8]}"
        if job.brand_revision_id is not None:
            analysis_id = f"{analysis_id}-brand-{job.brand_revision_id[:8]}"
        if not source_evidence_artifacts:
            raise ValueError("analysis input has no immutable source-artifact evidence")
        evidence_sets = [
            evidence_set("evidence.source", "source_manifest", source_evidence_artifacts),
            *[
                evidence_set(
                    f"evidence.classified.{retailer_id}",
                    "classified_offers",
                    artifacts,
                )
                for retailer_id, artifacts in sorted(classified_evidence_artifacts.items())
            ],
            *comparison_evidence_sets,
        ]
        document = AnalysisResultV2Builder(pack, code_version=self._code_version).build(
            analysis_id=analysis_id,
            analysis_run_id=job.id,
            generated_at=generated_at.isoformat(),
            source={
                "input_set_id": job.input_set_id,
                "kind": job.source_kind,
                "collection_run_id": (
                    job.collection_run_id if job.source_kind == "live_collection" else None
                ),
                "match_revision_id": job.match_revision_id,
                "brand_revision_id": job.brand_revision_id,
                "source_analysis_id": job.source_analysis_id,
                "observed_start": min(observed_values) if observed_values else None,
                "observed_end": max(observed_values) if observed_values else None,
                "sampling": bool(
                    analysis_options.get("sampling", False)
                    if isinstance(analysis_options, dict)
                    else False
                ),
                "total_rows": provider_rows_count,
                "source_artifact_ids": sorted(set(raw_artifact_ids)),
            },
            benchmark_retailer=benchmark,
            competitors=competitors,
            coverage_facts=coverage,
            comparison_facts=comparison_facts,
            data_quality_facts={
                "normalization_rejections": provider_rows_count - normalized_count,
                "review_offers": review_offer_count,
                "zero_or_missing_price_offers": zero_or_missing_price_count,
            },
            evidence_sets=evidence_sets,
            raw_source_artifact_ids=raw_artifact_ids,
            retailer_packs=brand_resolver.provenance([benchmark, *competitors]),
        )
        decision_rows = benchmark_product_decisions(
            relationship_offers,
            map_matches,
            benchmark_retailer=benchmark,
            decision_rules=decision_rules,
            qa_rules=pack.document["qa_rules"],
        )
        product_decisions = [row for row in decision_rows if row["qa_status"] == "ready"]
        suppressed_product_decisions = [row for row in decision_rows if row["qa_status"] != "ready"]
        map_points = benchmark_product_map_points(
            relationship_offers,
            map_matches,
            benchmark_retailer=benchmark,
            allowed_relationship_ids={
                str(row["relationship_id"])
                for row in product_decisions
                if row.get("relationship_id")
            },
        )
        match_candidates = benchmark_product_match_candidates(
            relationship_offers,
            candidate_matches,
            benchmark_retailer=benchmark,
            profiles=selected_profiles,
            max_rows=2_000,
            max_locations_per_row=1,
        )
        relationship_index: dict[tuple[str, str, str], dict[str, Any]] = {
            (
                str(row["competitor_id"]),
                str(row["benchmark_product_id"]),
                str(row["competitor_product_id"]),
            ): row
            for row in match_relationships
        }
        ambiguous_index: dict[tuple[str, str, str], str] = {
            (
                str(group["competitor_id"]),
                str(candidate["benchmark_product_id"]),
                str(candidate["competitor_product_id"]),
            ): str(group["candidate_group_id"])
            for group in ambiguous_match_groups
            for candidate in group["candidates"]
        }
        for candidate in match_candidates:
            relationship_key = (
                str(candidate["competitor"]),
                str(candidate["benchmark_product_id"]),
                str(candidate["competitor_product_id"]),
            )
            relationship = relationship_index.get(relationship_key)
            candidate["relationship_id"] = (
                str(relationship["relationship_id"]) if relationship is not None else None
            )
            candidate["relationship_status"] = (
                str(relationship["status"])
                if relationship is not None
                else "ambiguous"
                if relationship_key in ambiguous_index
                else "unmatched"
            )
            candidate["candidate_group_id"] = ambiguous_index.get(relationship_key)
            candidate["qa_status"] = (
                "review_required" if candidate["relationship_status"] == "ambiguous" else "ready"
            )
            candidate["suppression_reasons"] = (
                ["Automatic candidates do not have a unique one-to-one assignment"]
                if candidate["relationship_status"] == "ambiguous"
                else []
            )
        assortment_analysis = merge_assortment_product_context(
            assortment_accumulator.finalize(
                benchmark_retailer=benchmark,
                competitors=competitors,
                matches=review_matches,
                profiles=selected_profiles,
                ambiguous_groups=ambiguous_match_groups,
            ),
            pdp_context.values(),
        )
        assortment_analysis["comparison_population"] = {
            "reported_price_outcomes": "relationship_resolved_products",
            "market_floor_retained_offers": len(comparison_offers),
            "relationship_retained_offers": len(relationship_offers),
            "pdp_identity_products": len(pdp_context),
        }
        if (
            self._assistant is not None
            and job.match_revision_id is None
            and job.brand_revision_id is None
            and isinstance(analysis_options, dict)
            and bool(analysis_options.get("enable_ai_fallback", True))
        ):
            blueprint = ReportBlueprintLoader(self._root).load(str(pack.report_blueprint["id"]))
            document = await self._assistant.enrich(
                document,
                product_pack=pack.document,
                report_blueprint=blueprint.document,
                product_decisions=product_decisions,
            )
        record = await self._results.publish(document, collection_run_id=job.collection_run_id)
        if map_points or product_decisions or suppressed_product_decisions or match_relationships:
            await self._results.publish_publication(
                record.analysis_id,
                document,
                presentation_context={
                    "map_points": map_points,
                    "product_decisions": product_decisions,
                    "suppressed_product_decisions": suppressed_product_decisions,
                    "match_candidates": match_candidates,
                    "match_relationships": match_relationships,
                    "ambiguous_match_groups": ambiguous_match_groups,
                    "assortment_analysis": assortment_analysis,
                    "notes": [
                        "Price outcomes use unique relationship-resolved product pairs, not the "
                        "lowest interchangeable item in each market.",
                        "Retailer Search is authoritative for store-specific price; Product "
                        "Details supplies identity and attribute context.",
                    ],
                },
            )
        await self._generate_deliveries(record.analysis_id, job.definition_config)
        return record.analysis_id

    async def _generate_deliveries(
        self, analysis_id: str, definition_config: dict[str, Any]
    ) -> None:
        delivery = definition_config.get("delivery", {})
        if not isinstance(delivery, dict):
            return
        requested = [
            *(["html"] if bool(delivery.get("web_report")) else []),
            *(["xlsx"] if bool(delivery.get("excel")) else []),
            *(["leadership_email"] if bool(delivery.get("leadership_email")) else []),
            *(["audit_zip"] if bool(delivery.get("audit_package", True)) else []),
        ]
        for artifact_type in requested:
            try:
                await self._results.generate_artifact(analysis_id, artifact_type)  # type: ignore[arg-type]
            except Exception:
                logger.exception(
                    "analysis delivery artifact failed",
                    extra={
                        "event": "analysis_artifact_failed",
                        "analysis_id": analysis_id,
                        "artifact_type": artifact_type,
                    },
                )


class AnalysisWorker:
    def __init__(
        self,
        queue: PostgresAnalysisQueue,
        processor: AnalysisProcessor,
        *,
        worker_id: str,
        claim_limit: int = 1,
        lease_seconds: int = 600,
    ) -> None:
        self._queue = queue
        self._processor = processor
        self._worker_id = worker_id
        self._claim_limit = claim_limit
        self._lease_seconds = lease_seconds

    async def run_once(self) -> int:
        await self._queue.materialize()
        jobs = await self._queue.claim(
            self._worker_id,
            limit=self._claim_limit,
            lease_seconds=self._lease_seconds,
        )
        await asyncio.gather(*(self._execute(job) for job in jobs))
        return len(jobs)

    async def _execute(self, job: AnalysisJob) -> None:
        finished = asyncio.Event()
        heartbeat = asyncio.create_task(self._heartbeat(job.id, finished))
        try:
            analysis_id = await self._processor.process(job)
            logger.info(
                "analysis completed",
                extra={
                    "event": "analysis_completed",
                    "analysis_id": analysis_id,
                    "run_id": job.collection_run_id,
                },
            )
        except Exception as exc:
            await self._queue.fail(job, self._worker_id, str(exc))
            logger.exception(
                "analysis failed",
                extra={
                    "event": "analysis_failed",
                    "analysis_job_id": job.id,
                    "run_id": job.collection_run_id,
                },
            )
        finally:
            finished.set()
            await heartbeat

    async def _heartbeat(self, job_id: str, finished: asyncio.Event) -> None:
        interval = max(self._lease_seconds / 3, 1)
        while not finished.is_set():
            try:
                await asyncio.wait_for(finished.wait(), timeout=interval)
            except TimeoutError:
                if not await self._queue.extend_lease(job_id, self._worker_id, self._lease_seconds):
                    return
