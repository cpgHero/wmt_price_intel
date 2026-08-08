"""Railway-ready schedule, alert-evaluation, and email-delivery process."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

from rci_automation import (
    AutomationService,
    PostgresAutomationRepository,
    SMTPEmailSender,
    SMTPSettings,
    UnavailableEmailSender,
)
from rci_collections import (
    CollectionPlanner,
    CollectionRetailerCatalog,
    PostgresCollectionRepository,
)
from rci_collections.service import CollectionService
from rci_core import APP_VERSION, AppSettings, AsyncHealthServer, configure_logging
from rci_db import DatabaseProbe


async def run() -> None:
    settings = AppSettings.from_env()
    configure_logging("scheduler", settings.log_level)
    logger = logging.getLogger(__name__)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stop.set)
    database = DatabaseProbe(settings.database_url)
    repository_root = Path(os.getenv("RCI_REPOSITORY_ROOT", Path.cwd())).resolve()
    collection_repository = PostgresCollectionRepository(database.engine)
    collection_service = CollectionService(
        collection_repository,
        CollectionPlanner(
            collection_repository,
            CollectionRetailerCatalog.from_path(
                repository_root / "config" / "retailer-catalog.json"
            ),
            max_attempts=int(os.getenv("METRICSCART_MAX_ATTEMPTS", "5")),
        ),
        repository_root,
    )
    email_sender = (
        SMTPEmailSender(SMTPSettings.from_env())
        if os.getenv("SMTP_HOST") and os.getenv("SMTP_FROM_EMAIL")
        else UnavailableEmailSender()
    )
    automation = AutomationService(
        PostgresAutomationRepository(database.engine),
        collection_service,
        email_sender,
        repository_root,
    )
    scheduler_id = (
        os.getenv("SCHEDULER_ID")
        or os.getenv("RAILWAY_REPLICA_ID")
        or f"{socket.gethostname()}-{uuid4()}"
    )
    health_server = AsyncHealthServer(
        "scheduler",
        database.is_ready,
        port=int(os.getenv("PORT", "8080")),
        metadata={"version": settings.app_version or APP_VERSION},
    )
    await health_server.start()
    logger.info(
        "scheduler started",
        extra={
            "event": "service_started",
            "status": "ready",
            "worker_id": scheduler_id,
        },
    )
    try:
        while not stop.is_set():
            try:
                result = await automation.tick(
                    scheduler_id,
                    claim_limit=int(os.getenv("SCHEDULER_CLAIM_LIMIT", "10")),
                    lease_seconds=int(os.getenv("SCHEDULER_LEASE_SECONDS", "300")),
                )
                logger.info(
                    "automation tick completed",
                    extra={
                        "event": "automation_tick_completed",
                        "worker_id": scheduler_id,
                        "status": "ok" if result.failures == 0 else "partial",
                        "result_count": result.analyses_evaluated,
                        "failure_count": result.failures,
                        "scheduled_runs": result.scheduled_runs_created,
                        "alert_events": result.alert_events_triggered,
                        "emails_sent": result.emails_sent,
                    },
                )
            except Exception:
                logger.exception(
                    "automation tick failed",
                    extra={
                        "event": "automation_tick_failed",
                        "worker_id": scheduler_id,
                        "status": "failed",
                    },
                )
            with suppress(TimeoutError):
                await asyncio.wait_for(
                    stop.wait(), timeout=float(os.getenv("SCHEDULER_POLL_SECONDS", "30"))
                )
    finally:
        logger.info("scheduler stopping", extra={"event": "service_stopping"})
        await health_server.close()
        await database.dispose()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
