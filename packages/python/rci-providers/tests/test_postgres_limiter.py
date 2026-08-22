from __future__ import annotations

import asyncio
import os
import time
from uuid import uuid4

import pytest
from sqlalchemy import text

from rci_db import DatabaseProbe
from rci_providers.limiter import PostgresProviderLimiter


@pytest.mark.skipif(
    not os.getenv("RCI_TEST_DATABASE_URL"),
    reason="set RCI_TEST_DATABASE_URL to run shared Postgres limiter integration",
)
async def test_postgres_replicas_enforce_scoped_per_second_limit_and_cooldown() -> None:
    database = DatabaseProbe(os.environ["RCI_TEST_DATABASE_URL"])
    budget_key = f"limiter-test-{uuid4()}"
    replicas = [
        PostgresProviderLimiter(
            database.engine,
            provider="metricscart",
            budget_key=budget_key,
            rps=2,
            rpm=108,
        )
        for _ in range(3)
    ]
    try:
        started = time.monotonic()
        await asyncio.gather(*(limiter.acquire("search:walmart_us") for limiter in replicas))
        assert time.monotonic() - started >= 0.75

        started = time.monotonic()
        await asyncio.gather(
            replicas[0].acquire("search:aldi_us"),
            replicas[1].acquire("search:target_us"),
        )
        assert time.monotonic() - started < 0.2

        cooldown_key = f"cooldown-test-{uuid4()}"
        first = PostgresProviderLimiter(
            database.engine,
            provider="metricscart",
            budget_key=cooldown_key,
            rps=100,
            rpm=1000,
        )
        second = PostgresProviderLimiter(
            database.engine,
            provider="metricscart",
            budget_key=cooldown_key,
            rps=100,
            rpm=1000,
        )
        await first.pause(0.25, "search:aldi_us")
        started = time.monotonic()
        await second.acquire("search:aldi_us")
        assert time.monotonic() - started >= 0.15
    finally:
        async with database.engine.begin() as connection:
            await connection.execute(
                text(
                    "DELETE FROM provider_rate_limit_state "
                    "WHERE provider LIKE 'metricscart:%' AND budget_key LIKE '%-test-%'"
                )
            )
        await database.dispose()
