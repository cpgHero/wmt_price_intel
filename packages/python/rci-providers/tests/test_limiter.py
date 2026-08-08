from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field

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
            rpm=108,
            state=state,
            lock=lock,
            clock=clock.read,
            sleep=clock.sleep,
        )
        for _ in range(3)
    ]

    await asyncio.gather(*(replica.acquire() for replica in replicas))

    assert clock.now == 1
    assert clock.sleeps == [1]


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
    assert clock.now == 60

    await first.pause(120)
    await second.acquire()
    assert clock.now == 180


def test_postgres_limiter_serializes_permits_under_row_lock() -> None:
    source = inspect.getsource(PostgresProviderLimiter)
    assert "FOR UPDATE" in source
    assert "provider_rate_limit_state" in source
    assert "paused_until = GREATEST" in source
