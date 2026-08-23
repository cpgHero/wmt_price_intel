"""Durable collection and post-collection analysis worker."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

from rci_agents import (
    GovernedAnalysisAssistant,
    MatchingReviewAIWorker,
    OpenAIMatchingReviewProvider,
    OpenAIResponsesProvider,
    PostgresAgentTaskRepository,
    PostgresMatchingReviewTaskRepository,
)

from rci_analytics import CatalogProductPackLoader, ParquetDatasetWriter
from rci_analytics.parquet import S3DatasetStore
from rci_collections import FakeProvider, PostgresCollectionRepository, QueueWorker
from rci_collections.worker import CollectionProvider
from rci_core import APP_VERSION, AppSettings, AsyncHealthServer, configure_logging
from rci_db import DatabaseProbe
from rci_product_packs import (
    PostgresProductPackAuthoringRepository,
    PostgresProductPackCatalog,
    ProductPackValidationWorker,
)
from rci_products import (
    DEFAULT_PRODUCT_DETAIL_CACHE_TTL_SECONDS,
    MetricsCartProductDetailClient,
    PostgresProductDetailLimiterRegistry,
    PostgresProductDetailRepository,
    ProductDetailCatalog,
    ProductDetailRenormalizationWorker,
    ProductDetailWorker,
    S3ProductDetailRawObjectStore,
)
from rci_providers import (
    MetricsCartAdapterRegistry,
    MetricsCartClient,
    MetricsCartSettings,
    PostgresProviderLimiter,
    S3RawObjectStore,
)
from rci_providers.client import credential_budget_key
from rci_results import (
    AnalysisResultService,
    AnalysisResultValidator,
    ArtifactRenderer,
    PostgresBrandReviewRepository,
    PostgresMatchReviewRepository,
    PostgresResultsRepository,
    S3ReportObjectStore,
)
from rci_studies import PostgresStudyRepository
from rci_worker.analysis import (
    AnalysisProcessor,
    AnalysisWorker,
    PostgresAnalysisQueue,
    S3HistoricalCSVReader,
    S3RawPageReader,
)
from rci_worker.product_pack_validation import validate_product_pack_draft
from rci_worker.report_materialization import (
    PostgresReportMaterializationQueue,
    ReportMaterializationClient,
    ReportMaterializationWorker,
)
from rci_worker.study_discovery import StudyDiscoveryWorker


def _enabled(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _collection_provider_mode(*, app_env: str, configured: str | None) -> str:
    """Resolve the provider without allowing an accidental production fake run."""

    mode = (configured or "fake").strip().lower()
    if mode not in {"fake", "metricscart"}:
        raise ValueError("COLLECTION_PROVIDER must be 'fake' or 'metricscart'")
    if app_env.strip().lower() == "production" and mode == "fake":
        raise ValueError(
            "COLLECTION_PROVIDER=fake is prohibited when APP_ENV=production; "
            "use a non-production environment for simulated collections"
        )
    return mode


async def run() -> None:
    # MetricsCart authenticates in the query string. Suppress dependency request logs so
    # the credential can never be emitted as part of a rendered URL.
    settings = AppSettings.from_env()
    configure_logging("worker", settings.log_level)
    logger = logging.getLogger(__name__)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stop.set)
    database = DatabaseProbe(settings.database_url)
    repository_root = Path(os.getenv("RCI_REPOSITORY_ROOT", Path.cwd())).resolve()
    collection_repository = PostgresCollectionRepository(database.engine)
    product_pack_catalog = PostgresProductPackCatalog(database.engine)
    worker_id = (
        os.getenv("WORKER_ID")
        or os.getenv("RAILWAY_REPLICA_ID")
        or f"{socket.gethostname()}-{uuid4()}"
    )
    product_pack_validation_worker = ProductPackValidationWorker(
        PostgresProductPackAuthoringRepository(database.engine),
        lambda draft, evidence, suite: validate_product_pack_draft(
            repository_root,
            draft,
            evidence,
            suite,
        ),
        worker_id=f"{worker_id}-product-pack",
        claim_limit=int(os.getenv("PRODUCT_PACK_VALIDATION_CLAIM_LIMIT", "1")),
        lease_seconds=int(os.getenv("PRODUCT_PACK_VALIDATION_LEASE_SECONDS", "900")),
    )
    provider_mode = _collection_provider_mode(
        app_env=settings.app_env,
        configured=os.getenv("COLLECTION_PROVIDER"),
    )
    metricscart_client: MetricsCartClient | None = None
    provider: CollectionProvider
    adapter_registry = MetricsCartAdapterRegistry.from_catalog(
        repository_root / "config" / "retailer-catalog.json"
    )
    if provider_mode == "fake":
        provider = FakeProvider()
    elif provider_mode == "metricscart":
        metricscart_settings = MetricsCartSettings.from_env()
        limiter = PostgresProviderLimiter(
            database.engine,
            provider="metricscart",
            budget_key=credential_budget_key(metricscart_settings.api_key),
            rps=int(os.getenv("METRICSCART_GLOBAL_RPS", "2")),
            rpm=int(os.getenv("METRICSCART_GLOBAL_RPM", "108")),
        )
        object_store = S3RawObjectStore.create(
            bucket=os.environ["OBJECT_STORAGE_BUCKET"],
            endpoint_url=os.getenv("OBJECT_STORAGE_ENDPOINT"),
            region_name=os.getenv("OBJECT_STORAGE_REGION"),
            access_key_id=os.getenv("OBJECT_STORAGE_ACCESS_KEY_ID"),
            secret_access_key=os.getenv("OBJECT_STORAGE_SECRET_ACCESS_KEY"),
            force_path_style=_enabled(os.getenv("OBJECT_STORAGE_FORCE_PATH_STYLE"), default=True),
        )
        metricscart_client = MetricsCartClient(
            metricscart_settings,
            adapter_registry,
            limiter,
            object_store,
        )
        provider = metricscart_client
    worker = QueueWorker(
        collection_repository,
        provider,
        worker_id=worker_id,
        claim_limit=int(os.getenv("WORKER_CLAIM_LIMIT", "10")),
        lease_seconds=int(os.getenv("WORKER_LEASE_SECONDS", "300")),
    )
    assistant: GovernedAnalysisAssistant | None = None
    matching_review_worker: MatchingReviewAIWorker | None = None
    matching_review_concurrency = max(
        1,
        min(int(os.getenv("MATCHING_V2_AI_REVIEW_CONCURRENCY", "2")), 4),
    )
    if _enabled(os.getenv("AI_ENABLED")):
        assistant = GovernedAnalysisAssistant(
            repository_root=repository_root,
            provider=OpenAIResponsesProvider(
                api_key=os.environ["OPENAI_API_KEY"],
                timeout_seconds=float(os.getenv("OPENAI_TIMEOUT_SECONDS", "60")),
                max_output_tokens=int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "8000")),
                max_request_cost_usd=float(os.getenv("OPENAI_MAX_REQUEST_COST_USD", "1.00")),
                reasoning_effort=os.getenv("OPENAI_REASONING_EFFORT", "high"),
            ),
            repository=PostgresAgentTaskRepository(database.engine),
            worker_id=f"{worker_id}-agent",
            insight_model=os.environ["OPENAI_MODEL_INSIGHT"],
            narrative_model=os.environ["OPENAI_MODEL_NARRATIVE"],
            max_metrics=int(os.getenv("AI_MAX_METRICS", "360")),
            max_attempts=int(os.getenv("AI_MAX_ATTEMPTS", "2")),
            lease_seconds=int(os.getenv("AI_LEASE_SECONDS", "900")),
        )
        if _enabled(os.getenv("MATCHING_V2_AI_REVIEW_ENABLED")):
            matching_model = (
                os.getenv("OPENAI_MODEL_MATCHING_REVIEW")
                or os.getenv("OPENAI_MODEL_NARRATIVE")
                or ""
            ).strip()
            if not matching_model:
                raise ValueError("OPENAI_MODEL_MATCHING_REVIEW is required for AI match review")
            matching_review_worker = MatchingReviewAIWorker(
                PostgresMatchingReviewTaskRepository(database.engine),
                OpenAIMatchingReviewProvider(
                    api_key=os.environ["OPENAI_API_KEY"],
                    timeout_seconds=float(os.getenv("OPENAI_MATCHING_TIMEOUT_SECONDS", "90")),
                    max_output_tokens=int(os.getenv("OPENAI_MATCHING_MAX_OUTPUT_TOKENS", "3000")),
                    max_request_cost_usd=float(
                        os.getenv("OPENAI_MATCHING_MAX_REQUEST_COST_USD", "0.35")
                    ),
                    reasoning_effort=os.getenv("OPENAI_MATCHING_REASONING_EFFORT", "high"),
                ),
                repository_root=repository_root,
                worker_id=f"{worker_id}-matching-agent",
                lease_seconds=int(os.getenv("AI_LEASE_SECONDS", "900")),
            )
    analysis_worker: AnalysisWorker | None = None
    report_materialization_worker: ReportMaterializationWorker | None = None
    study_discovery_worker: StudyDiscoveryWorker | None = None
    if _enabled(os.getenv("ANALYSIS_PIPELINE_ENABLED"), default=True) and os.getenv(
        "OBJECT_STORAGE_BUCKET"
    ):
        import boto3  # type: ignore[import-untyped]
        from botocore.config import Config  # type: ignore[import-untyped]

        force_path_style = _enabled(os.getenv("OBJECT_STORAGE_FORCE_PATH_STYLE"), default=True)
        s3_client = boto3.client(
            "s3",
            endpoint_url=os.getenv("OBJECT_STORAGE_ENDPOINT") or None,
            region_name=os.getenv("OBJECT_STORAGE_REGION") or None,
            aws_access_key_id=os.getenv("OBJECT_STORAGE_ACCESS_KEY_ID") or None,
            aws_secret_access_key=os.getenv("OBJECT_STORAGE_SECRET_ACCESS_KEY") or None,
            config=Config(s3={"addressing_style": "path" if force_path_style else "virtual"}),
        )
        bucket = os.environ["OBJECT_STORAGE_BUCKET"]
        analysis_queue = PostgresAnalysisQueue(
            database.engine,
            code_version=settings.app_version or APP_VERSION,
            max_attempts=int(os.getenv("ANALYSIS_MAX_ATTEMPTS", "3")),
            historical_replay_enabled=_enabled(
                os.getenv("ANALYSIS_HISTORICAL_REPLAY_ENABLED"), default=False
            ),
        )
        study_discovery_worker = StudyDiscoveryWorker(
            repository_root=repository_root,
            repository=PostgresStudyRepository(database.engine),
            page_repository=analysis_queue,
            raw_reader=S3RawPageReader(bucket=bucket, client=s3_client),
            adapters=adapter_registry,
            worker_id=f"{worker_id}-study",
            claim_limit=int(os.getenv("STUDY_DISCOVERY_CLAIM_LIMIT", "1")),
            lease_seconds=int(os.getenv("STUDY_DISCOVERY_LEASE_SECONDS", "600")),
        )
        analysis_worker = AnalysisWorker(
            analysis_queue,
            AnalysisProcessor(
                repository_root=repository_root,
                queue=analysis_queue,
                adapters=adapter_registry,
                raw_reader=S3RawPageReader(bucket=bucket, client=s3_client),
                historical_reader=S3HistoricalCSVReader(bucket=bucket, client=s3_client),
                dataset_writer=ParquetDatasetWriter(
                    S3DatasetStore(bucket=bucket, client=s3_client)
                ),
                collections=collection_repository,
                results=AnalysisResultService(
                    PostgresResultsRepository(database.engine),
                    AnalysisResultValidator(repository_root),
                    S3ReportObjectStore(bucket=bucket, client=s3_client),
                    ArtifactRenderer(repository_root),
                    product_pack_catalog,
                ),
                code_version=settings.app_version or APP_VERSION,
                assistant=assistant,
                match_reviews=PostgresMatchReviewRepository(database.engine),
                brand_reviews=PostgresBrandReviewRepository(database.engine),
                product_packs=CatalogProductPackLoader(
                    repository_root,
                    product_pack_catalog,
                ),
                product_details=PostgresProductDetailRepository(
                    database.engine,
                    repository_root,
                ),
                matching_v2_shadow_enabled=_enabled(
                    os.getenv("MATCHING_V2_SHADOW_ENABLED"), default=False
                ),
            ),
            worker_id=f"{worker_id}-analysis",
            claim_limit=int(os.getenv("ANALYSIS_CLAIM_LIMIT", "1")),
            lease_seconds=int(os.getenv("ANALYSIS_LEASE_SECONDS", "600")),
        )
        internal_api_url = os.getenv("RCI_API_INTERNAL_URL", "").strip()
        internal_token = os.getenv("RCI_INTERNAL_SERVICE_TOKEN", "").strip()
        if internal_api_url and internal_token:
            materialization_worker_id = f"{worker_id}-report-materialization"
            report_materialization_worker = ReportMaterializationWorker(
                PostgresReportMaterializationQueue(database.engine),
                ReportMaterializationClient(
                    api_url=internal_api_url,
                    token=internal_token,
                    worker_id=materialization_worker_id,
                ),
                worker_id=materialization_worker_id,
                claim_limit=int(os.getenv("REPORT_MATERIALIZATION_CLAIM_LIMIT", "1")),
                lease_seconds=int(os.getenv("REPORT_MATERIALIZATION_LEASE_SECONDS", "1800")),
            )
    product_detail_client: MetricsCartProductDetailClient | None = None
    product_detail_worker: ProductDetailWorker | None = None
    if _enabled(os.getenv("PRODUCT_DETAIL_ENRICHMENT_ENABLED")):
        metricscart_settings = MetricsCartSettings.from_env()
        product_detail_client = MetricsCartProductDetailClient(
            metricscart_settings,
            ProductDetailCatalog.from_path(repository_root),
            PostgresProductDetailLimiterRegistry(
                database.engine,
                api_key=metricscart_settings.api_key,
                rps=int(os.getenv("PRODUCT_DETAIL_RPS", "3")),
                rpm=int(os.getenv("PRODUCT_DETAIL_RPM", "180")),
            ),
            S3ProductDetailRawObjectStore.create(
                bucket=os.environ["OBJECT_STORAGE_BUCKET"],
                endpoint_url=os.getenv("OBJECT_STORAGE_ENDPOINT"),
                region_name=os.getenv("OBJECT_STORAGE_REGION"),
                access_key_id=os.getenv("OBJECT_STORAGE_ACCESS_KEY_ID"),
                secret_access_key=os.getenv("OBJECT_STORAGE_SECRET_ACCESS_KEY"),
                force_path_style=_enabled(
                    os.getenv("OBJECT_STORAGE_FORCE_PATH_STYLE"), default=True
                ),
            ),
        )
        product_detail_worker = ProductDetailWorker(
            PostgresProductDetailRepository(database.engine, repository_root),
            product_detail_client,
            worker_id=f"{worker_id}-pdp",
            claim_limit=int(os.getenv("PRODUCT_DETAIL_CLAIM_LIMIT", "18")),
            lease_seconds=int(os.getenv("PRODUCT_DETAIL_LEASE_SECONDS", "300")),
            cache_ttl_seconds=int(
                os.getenv(
                    "PRODUCT_DETAIL_CACHE_TTL_SECONDS",
                    str(DEFAULT_PRODUCT_DETAIL_CACHE_TTL_SECONDS),
                )
            ),
        )
    product_detail_renormalization_worker: ProductDetailRenormalizationWorker | None = None
    if _enabled(os.getenv("PRODUCT_DETAIL_RENORMALIZATION_ENABLED")):
        product_detail_renormalization_worker = ProductDetailRenormalizationWorker(
            PostgresProductDetailRepository(database.engine, repository_root),
            S3ProductDetailRawObjectStore.create(
                bucket=os.environ["OBJECT_STORAGE_BUCKET"],
                endpoint_url=os.getenv("OBJECT_STORAGE_ENDPOINT"),
                region_name=os.getenv("OBJECT_STORAGE_REGION"),
                access_key_id=os.getenv("OBJECT_STORAGE_ACCESS_KEY_ID"),
                secret_access_key=os.getenv("OBJECT_STORAGE_SECRET_ACCESS_KEY"),
                force_path_style=_enabled(
                    os.getenv("OBJECT_STORAGE_FORCE_PATH_STYLE"), default=True
                ),
            ),
            worker_id=f"{worker_id}-pdp-normalizer",
            claim_limit=int(os.getenv("PRODUCT_DETAIL_RENORMALIZATION_CLAIM_LIMIT", "8")),
            lease_seconds=int(os.getenv("PRODUCT_DETAIL_RENORMALIZATION_LEASE_SECONDS", "300")),
        )
    health_server = AsyncHealthServer(
        "worker",
        database.is_ready,
        port=int(os.getenv("PORT", "8080")),
        metadata={"version": settings.app_version or APP_VERSION},
    )
    await health_server.start()
    logger.info(
        "worker started",
        extra={
            "event": "service_started",
            "worker_id": worker_id,
            "matching_review_concurrency": matching_review_concurrency,
            "status": "ready",
        },
    )
    try:
        while not stop.is_set():
            claimed = await worker.run_once()
            analyses = await analysis_worker.run_once() if analysis_worker is not None else 0
            report_materializations = (
                await report_materialization_worker.run_once()
                if report_materialization_worker is not None
                else 0
            )
            product_details = (
                await product_detail_worker.run_once() if product_detail_worker is not None else 0
            )
            product_detail_normalizations = (
                await product_detail_renormalization_worker.run_once()
                if product_detail_renormalization_worker is not None
                else 0
            )
            product_pack_validations = await product_pack_validation_worker.run_once()
            study_jobs = (
                await study_discovery_worker.run_once() if study_discovery_worker is not None else 0
            )
            matching_reviews = (
                await matching_review_worker.run_many(matching_review_concurrency)
                if matching_review_worker is not None
                else 0
            )
            if (
                claimed
                + analyses
                + report_materializations
                + product_details
                + product_detail_normalizations
                + product_pack_validations
                + study_jobs
                + matching_reviews
                == 0
            ):
                with suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=1)
    finally:
        logger.info(
            "worker stopping",
            extra={"event": "service_stopping", "worker_id": worker_id},
        )
        await health_server.close()
        if metricscart_client is not None:
            await metricscart_client.close()
        if product_detail_client is not None:
            await product_detail_client.close()
        await database.dispose()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
