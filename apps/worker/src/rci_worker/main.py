"""Durable queue worker using the Phase 2 fake provider."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

from rci_collections import FakeProvider, PostgresCollectionRepository, QueueWorker
from rci_collections.worker import CollectionProvider
from rci_core import APP_VERSION, AppSettings, AsyncHealthServer, configure_logging
from rci_db import DatabaseProbe
from rci_providers import (
    MetricsCartAdapterRegistry,
    MetricsCartClient,
    MetricsCartSettings,
    PostgresProviderLimiter,
    S3RawObjectStore,
)
from rci_providers.client import credential_budget_key


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
    worker_id = (
        os.getenv("WORKER_ID")
        or os.getenv("RAILWAY_REPLICA_ID")
        or f"{socket.gethostname()}-{uuid4()}"
    )
    provider_mode = os.getenv("COLLECTION_PROVIDER", "fake").strip().lower()
    metricscart_client: MetricsCartClient | None = None
    provider: CollectionProvider
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
            MetricsCartAdapterRegistry.from_catalog(Path("config/retailer-catalog.json")),
            limiter,
            object_store,
        )
        provider = metricscart_client
    else:
        raise ValueError("COLLECTION_PROVIDER must be 'fake' or 'metricscart'")
    worker = QueueWorker(
        PostgresCollectionRepository(database.engine),
        provider,
        worker_id=worker_id,
        claim_limit=int(os.getenv("WORKER_CLAIM_LIMIT", "10")),
        lease_seconds=int(os.getenv("WORKER_LEASE_SECONDS", "300")),
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
            if claimed == 0:
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
        await database.dispose()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
