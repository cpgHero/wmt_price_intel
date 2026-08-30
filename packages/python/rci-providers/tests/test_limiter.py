from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from rci_providers.limiter import (
    InMemoryProviderLimiter,
    MemoryProviderLimitState,
    PostgresProviderLimiter,
)


@dataclass
class ManualClock:
    now: float = 0
    sleeps: list[float] = field(default_factory=list)

    def read(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


async def test_multiple_replicas_share_two_rps_budget() -> None:
    clock = ManualClock()
    state = MemoryProviderLimitState()
    lock = asyncio.Lock()
    replicas = [
        InMemoryProviderLimiter(
            rps=2,
            rpm=120,
            state=state,
            lock=lock,
            clock=clock.read,
            sleep=clock.sleep,
        )
        for _ in range(3)
    ]

    for replica in replicas:
        await replica.acquire()

    assert clock.now == pytest.approx(1.02)
    assert clock.sleeps == pytest.approx([0.51, 0.51])


async def test_minute_limit_and_shared_cooldown_gate_every_replica() -> None:
    clock = ManualClock()
    state = MemoryProviderLimitState()
    lock = asyncio.Lock()
    first = InMemoryProviderLimiter(
        rps=200,
        rpm=108,
        state=state,
        lock=lock,
        clock=clock.read,
        sleep=clock.sleep,
    )
    second = InMemoryProviderLimiter(
        rps=200,
        rpm=108,
        state=state,
        lock=lock,
        clock=clock.read,
        sleep=clock.sleep,
    )

    for _ in range(108):
        await first.acquire()
    await second.acquire()
    assert clock.now == pytest.approx(61.2)

    await first.pause(120)
    await second.acquire()
    assert clock.now == pytest.approx(181.2)


def test_postgres_limiter_serializes_permits_under_row_lock() -> None:
    source = inspect.getsource(PostgresProviderLimiter)
    assert "FOR UPDATE" in source
    assert "provider_rate_limit_state" in source
    assert "next_permit_at" in source
    assert "paused_until = GREATEST" in source
    assert "last_429_at" in source


def test_postgres_limiter_temporarily_slows_only_after_recent_429() -> None:
    limiter = PostgresProviderLimiter(
        object(),  # type: ignore[arg-type]
        provider="metricscart",
        budget_key="test",
        rps=3,
        rpm=180,
        post_429_rps=2,
        post_429_rpm=108,
        post_429_recovery_seconds=1800,
    )
    now = datetime.now(UTC)

    assert limiter._effective_permit_interval(now, None) == pytest.approx(0.34)
    assert limiter._effective_permit_interval(now, now - timedelta(minutes=5)) == pytest.approx(
        60 / 108 * 1.02
    )
    assert limiter._effective_permit_interval(now, now - timedelta(minutes=31)) == pytest.approx(
        0.34
    )
