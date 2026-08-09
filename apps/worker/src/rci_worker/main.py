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
    OpenAIResponsesProvider,
    PostgresAgentTaskRepository,
)

from rci_analytics import ParquetDatasetWriter
from rci_analytics.parquet import S3DatasetStore
from rci_collections import FakeProvider, PostgresCollectionRepository, QueueWorker
from rci_collections.worker import CollectionProvider
from rci_core import APP_VERSION, AppSettings, AsyncHealthServer, configure_logging
from rci_db import DatabaseProbe
from rci_products import (
    MetricsCartProductDetailClient,
    PostgresProductDetailLimiterRegistry,
    PostgresProductDetailRepository,
    ProductDetailCatalog,
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
    PostgresResultsRepository,
    S3ReportObjectStore,
)
from rci_worker.analysis import (
    AnalysisProcessor,
    AnalysisWorker,
    PostgresAnalysisQueue,
    S3HistoricalCSVReader,
    S3RawPageReader,
)


def _enabled(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


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
    worker_id = (
        os.getenv("WORKER_ID")
        or os.getenv("RAILWAY_REPLICA_ID")
        or f"{socket.gethostname()}-{uuid4()}"
    )
    provider_mode = os.getenv("COLLECTION_PROVIDER", "fake").strip().lower()
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
    else:
        raise ValueError("COLLECTION_PROVIDER must be 'fake' or 'metricscart'")
    worker = QueueWorker(
        collection_repository,
        provider,
        worker_id=worker_id,
        claim_limit=int(os.getenv("WORKER_CLAIM_LIMIT", "10")),
        lease_seconds=int(os.getenv("WORKER_LEASE_SECONDS", "300")),
    )
    assistant: GovernedAnalysisAssistant | None = None
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
    analysis_worker: AnalysisWorker | None = None
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
                ),
                code_version=settings.app_version or APP_VERSION,
                assistant=assistant,
            ),
            worker_id=f"{worker_id}-analysis",
            claim_limit=int(os.getenv("ANALYSIS_CLAIM_LIMIT", "1")),
            lease_seconds=int(os.getenv("ANALYSIS_LEASE_SECONDS", "600")),
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
            claim_limit=int(os.getenv("PRODUCT_DETAIL_CLAIM_LIMIT", "1")),
            lease_seconds=int(os.getenv("PRODUCT_DETAIL_LEASE_SECONDS", "300")),
            cache_ttl_seconds=int(os.getenv("PRODUCT_DETAIL_CACHE_TTL_SECONDS", "604800")),
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
            "status": "ready",
        },
    )
    try:
        while not stop.is_set():
            claimed = await worker.run_once()
            analyses = await analysis_worker.run_once() if analysis_worker is not None else 0
            product_details = (
                await product_detail_worker.run_once() if product_detail_worker is not None else 0
            )
            if claimed + analyses + product_details == 0:
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
