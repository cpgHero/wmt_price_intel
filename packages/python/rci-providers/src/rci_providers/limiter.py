"""Replica-safe provider permitting and shared cooldown."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


class ProviderLimiter(Protocol):
    async def acquire(self, scope_key: str | None = None) -> None: ...

    async def pause(self, seconds: float, scope_key: str | None = None) -> None: ...


@dataclass(slots=True)
class MemoryProviderLimitState:
    second_start: float = 0
    second_count: int = 0
    minute_start: float = 0
    minute_count: int = 0
    paused_until: float = 0
    next_permit_at: float = 0


class InMemoryProviderLimiter:
    """Deterministic limiter for tests; all instances may share one state and lock."""

    def __init__(
        self,
        *,
        rps: int = 2,
        rpm: int = 108,
        state: MemoryProviderLimitState | None = None,
        lock: asyncio.Lock | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if rps < 1 or rpm < 1:
            raise ValueError("provider limits must be positive")
        self.rps = rps
        self.rpm = rpm
        self._permit_interval = max(1 / rps, 60 / rpm) * 1.02
        self._state = state or MemoryProviderLimitState()
        self._lock = lock or asyncio.Lock()
        self._clock = clock
        self._sleep = sleep

    async def acquire(self, scope_key: str | None = None) -> None:
        del scope_key
        while True:
            async with self._lock:
                now = self._clock()
                wait = self._wait_or_consume(now)
            if wait <= 0:
                return
            await self._sleep(wait)

    def _wait_or_consume(self, now: float) -> float:
        state = self._state
        waits = []
        if state.paused_until > now:
            waits.append(state.paused_until - now)
        if state.next_permit_at > now:
            waits.append(state.next_permit_at - now)
        if waits:
            return max(waits)
        if now - state.second_start >= 1:
            state.second_start = now
            state.second_count = 0
        if now - state.minute_start >= 60:
            state.minute_start = now
            state.minute_count = 0
        state.next_permit_at = now + self._permit_interval
        state.second_count += 1
        state.minute_count += 1
        return 0

    async def pause(self, seconds: float, scope_key: str | None = None) -> None:
        del scope_key
        async with self._lock:
            self._state.paused_until = max(
                self._state.paused_until, self._clock() + max(seconds, 0)
            )


class PostgresProviderLimiter:
    """Issue permits under a row lock using the database clock."""

    def __init__(
        self,
        engine: AsyncEngine,
        *,
        provider: str,
        budget_key: str,
        rps: int = 2,
        rpm: int = 108,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if rps < 1 or rpm < 1:
            raise ValueError("provider limits must be positive")
        self._engine = engine
        self.provider = provider
        self.budget_key = budget_key
        self.rps = rps
        self.rpm = rpm
        self._permit_interval = max(1 / rps, 60 / rpm) * 1.02
        self._sleep = sleep

    async def acquire(self, scope_key: str | None = None) -> None:
        provider = self._scoped_provider(scope_key)
        while True:
            wait = await self._try_acquire(provider)
            if wait <= 0:
                return
            await self._sleep(wait)

    async def _try_acquire(self, provider: str) -> float:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO provider_rate_limit_state (provider, budget_key)
                    VALUES (:provider, :budget_key)
                    ON CONFLICT (provider, budget_key) DO NOTHING
                    """
                ),
                {"provider": provider, "budget_key": self.budget_key},
            )
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT *, clock_timestamp() AS database_now
                            FROM provider_rate_limit_state
                            WHERE provider = :provider AND budget_key = :budget_key
                            FOR UPDATE
                            """
                        ),
                        {"provider": provider, "budget_key": self.budget_key},
                    )
                )
                .mappings()
                .one()
            )
            now: datetime = row["database_now"]
            second_start = row["second_window_start"]
            second_count = int(row["second_count"])
            minute_start = row["minute_window_start"]
            minute_count = int(row["minute_count"])
            next_permit_at = row["next_permit_at"]
            if second_start is None or (now - second_start).total_seconds() >= 1:
                second_start, second_count = now, 0
            if minute_start is None or (now - minute_start).total_seconds() >= 60:
                minute_start, minute_count = now, 0
            waits = []
            if row["paused_until"] is not None and row["paused_until"] > now:
                waits.append((row["paused_until"] - now).total_seconds())
            if next_permit_at is not None and next_permit_at > now:
                waits.append((next_permit_at - now).total_seconds())
            if waits:
                return max(waits)
            await connection.execute(
                text(
                    """
                    UPDATE provider_rate_limit_state
                    SET second_window_start = :second_start,
                        second_count = :second_count,
                        minute_window_start = :minute_start,
                        minute_count = :minute_count,
                        next_permit_at = :next_permit_at,
                        updated_at = clock_timestamp()
                    WHERE provider = :provider AND budget_key = :budget_key
                    """
                ),
                {
                    "provider": provider,
                    "budget_key": self.budget_key,
                    "second_start": second_start,
                    "second_count": second_count + 1,
                    "minute_start": minute_start,
                    "minute_count": minute_count + 1,
                    "next_permit_at": now + timedelta(seconds=self._permit_interval),
                },
            )
            return 0

    async def pause(self, seconds: float, scope_key: str | None = None) -> None:
        await self._pause(max(seconds, 0), self._scoped_provider(scope_key))

    async def _pause(self, seconds: float, provider: str) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO provider_rate_limit_state (
                      provider, budget_key, paused_until, last_429_at
                    ) VALUES (
                      :provider, :budget_key,
                      clock_timestamp() + make_interval(secs => :seconds),
                      clock_timestamp()
                    )
                    ON CONFLICT (provider, budget_key) DO UPDATE
                    SET paused_until = GREATEST(
                          COALESCE(
                            provider_rate_limit_state.paused_until,
                            '-infinity'::timestamptz
                          ),
                          EXCLUDED.paused_until
                        ),
                        last_429_at = EXCLUDED.last_429_at,
                        updated_at = clock_timestamp()
                    """
                ),
                {
                    "provider": provider,
                    "budget_key": self.budget_key,
                    "seconds": seconds,
                },
            )

    def _scoped_provider(self, scope_key: str | None) -> str:
        normalized = str(scope_key or "global").strip().lower().replace(" ", "_")
        return f"{self.provider}:{normalized}"
