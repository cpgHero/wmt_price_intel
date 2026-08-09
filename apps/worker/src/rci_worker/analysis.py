"""Durable post-collection orchestration for the generic analytics vertical slice."""

from __future__ import annotations

import asyncio
import csv
import gzip
import hashlib
import io
import json
import logging
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncEngine

from rci_analytics import (
    CanonicalOfferNormalizer,
    ComparisonEngine,
    OfferClassifier,
    ParquetDatasetWriter,
    ProductPackLoader,
)
from rci_analytics.historical_repository import PostgresAnalysisInputRepository
from rci_analytics.normalization import RetailerIdentityMap
from rci_collections.models import QueueTask
from rci_collections.repository import PostgresCollectionRepository
from rci_providers import MetricsCartAdapterRegistry
from rci_results import AnalysisResultService

logger = logging.getLogger(__name__)


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
                                  :historical_replay_enabled OR
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
                              ar.attempt_count, ar.max_attempts, v.config
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

    async def process(self, job: AnalysisJob) -> str:
        pack = ProductPackLoader(self._root).load(job.product_pack_id)
        if pack.version != job.product_pack_version:
            raise ValueError(
                f"Product Pack version mismatch: requested {job.product_pack_version}, "
                f"loaded {pack.version}"
            )
        provider_rows: list[dict[str, Any]] = []
        raw_artifact_ids: list[str] = []
        source_artifact_count = 0
        if job.source_kind == "live_collection":
            pages = await self._queue.pages(job.collection_run_id)
            if not pages:
                raise ValueError("completed collection has no successful raw provider pages")
            source_artifact_count = len(pages)
            for page in pages:
                payload = await self._raw_reader.read(page)
                adapter = self._adapters.get(page.task.adapter_id)
                for result in adapter.extract_result_array(payload):
                    provider_rows.append(
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
        elif job.source_kind == "historical_import":
            if self._historical_reader is None:
                raise ValueError("historical input reader is not configured")
            sources = await self._queue.historical_sources(job.input_set_id)
            if not sources:
                raise ValueError("historical input set has no source artifacts")
            source_artifact_count = len(sources)
            for source in sources:
                rows = await self._historical_reader.read(source)
                provider_rows.extend({**row, "retailer_id": source.retailer_id} for row in rows)
                raw_artifact_ids.append(source.dataset_artifact_id)
        else:
            raise ValueError(f"unsupported analysis input kind {job.source_kind!r}")

        normalizer = CanonicalOfferNormalizer(
            RetailerIdentityMap.from_catalog(self._root / "config" / "retailer-catalog.json")
        )
        normalized = normalizer.normalize_many(provider_rows)
        classified = OfferClassifier(pack).classify_many(normalized)
        engine = ComparisonEngine(pack)
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

        derived_artifact_ids: list[str] = []
        by_retailer: dict[str, list[Any]] = defaultdict(list)
        classified_by_retailer: dict[str, list[Any]] = defaultdict(list)
        for normalized_offer in normalized:
            by_retailer[normalized_offer.retailer_id].append(normalized_offer)
        for classified_offer in classified:
            classified_by_retailer[classified_offer.offer.retailer_id].append(classified_offer)
        for retailer_id in sorted(by_retailer):
            normalized_artifact = await self._dataset_writer.write_normalized(
                by_retailer[retailer_id],
                run_id=job.collection_run_id,
                retailer_id=retailer_id,
            )
            classified_artifact = await self._dataset_writer.write_classified(
                classified_by_retailer[retailer_id],
                run_id=job.collection_run_id,
                retailer_id=retailer_id,
            )
            derived_artifact_ids.extend(
                [
                    await self._collections.record_artifact(
                        job.collection_run_id, normalized_artifact
                    ),
                    await self._collections.record_artifact(
                        job.collection_run_id, classified_artifact
                    ),
                ]
            )

        summaries: list[dict[str, Any]] = []
        match_evidence: list[dict[str, Any]] = []
        for competitor in competitors:
            competitor_matches = []
            for profile in selected_profiles:
                matches = engine.compare(
                    classified,
                    benchmark_id=benchmark,
                    competitor_id=competitor,
                    profile_id=str(profile["id"]),
                )
                if not matches:
                    continue
                competitor_matches.extend(matches)
                summary = asdict(engine.summarize(matches))
                summaries.append(summary)
                match_evidence.append(
                    {
                        "competitor_id": competitor,
                        "profile_id": str(profile["id"]),
                        "matches": len(matches),
                    }
                )
            if competitor_matches:
                artifact = await self._dataset_writer.write_matches(
                    competitor_matches,
                    run_id=job.collection_run_id,
                    retailer_id=competitor,
                )
                derived_artifact_ids.append(
                    await self._collections.record_artifact(job.collection_run_id, artifact)
                )

        coverage = [
            {
                "retailer_id": retailer_id,
                "offers": len(offers),
                "in_scope_offers": sum(
                    value.in_scope for value in classified_by_retailer[retailer_id]
                ),
                "in_scope_zips": len(
                    {
                        value.offer.zipcode
                        for value in classified_by_retailer[retailer_id]
                        if value.in_scope and value.offer.zipcode is not None
                    }
                ),
                "in_scope_stores": len(
                    {
                        value.offer.store_number
                        for value in classified_by_retailer[retailer_id]
                        if value.in_scope and value.offer.store_number is not None
                    }
                ),
            }
            for retailer_id, offers in sorted(by_retailer.items())
        ]
        generated_at = datetime.now(UTC)
        analysis_id = f"{pack.id}-{job.collection_run_id}"
        findings, recommendations = self._narrative(summaries, benchmark)
        matched_competitors = {str(summary["competitor_id"]) for summary in summaries}
        ready_to_share = bool(summaries) and matched_competitors == set(competitors)
        document: dict[str, Any] = {
            "schema_version": "1.0.0",
            "analysis_id": analysis_id,
            "collection_run_id": job.collection_run_id,
            "generated_at": generated_at.isoformat(),
            "benchmark_retailer": benchmark,
            "competitors": competitors,
            "product_pack": {"id": pack.id, "version": pack.version},
            "source_summary": {
                "source_kind": job.source_kind,
                "input_set_id": job.input_set_id,
                "raw_pages": source_artifact_count,
                "provider_rows": len(provider_rows),
                "normalized_offers": len(normalized),
                "classified_offers": len(classified),
                "raw_dataset_ids": sorted(set(raw_artifact_ids)),
            },
            "coverage": coverage,
            "comparisons": summaries,
            "data_quality": {
                "normalization_rejections": len(provider_rows) - len(normalized),
                "review_offers": sum(bool(value.review_reasons) for value in classified),
                "zero_or_missing_price_offers": sum(
                    value.offer.price is None or value.offer.price <= 0 for value in classified
                ),
            },
            "validation": {
                "status": "ready_to_share" if ready_to_share else "needs_review",
                "checks": match_evidence,
            },
            "findings": findings,
            "recommendations": recommendations,
            "artifacts": [],
            "provenance": {
                "analytics_code_version": self._code_version,
                "product_pack_checksum": pack.checksum,
                "derived_dataset_artifact_ids": derived_artifact_ids,
                "match_evidence": match_evidence,
            },
        }
        record = await self._results.publish(document, collection_run_id=job.collection_run_id)
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

    @staticmethod
    def _narrative(
        summaries: list[dict[str, Any]], benchmark: str
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        findings: list[dict[str, Any]] = []
        recommendations: list[dict[str, Any]] = []
        for summary in summaries:
            competitor = str(summary["competitor_id"])
            profile = str(summary["profile_id"])
            competitor_rate = float(summary["competitor_lower_rate"])
            benchmark_rate = float(summary["benchmark_lower_rate"])
            if competitor_rate > benchmark_rate:
                severity = "high"
                text_value = (
                    f"{competitor} is lower more often than {benchmark} in {profile} comparisons."
                )
                recommendations.append(
                    {
                        "priority": 1,
                        "text": (
                            f"Review {competitor} {profile} losses and underlying match evidence."
                        ),
                    }
                )
            else:
                severity = "positive"
                text_value = f"{benchmark} is lower at least as often as {competitor} in {profile}."
            findings.append(
                {
                    "id": f"{competitor}-{profile}",
                    "severity": severity,
                    "text": text_value,
                }
            )
        return findings, recommendations


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
