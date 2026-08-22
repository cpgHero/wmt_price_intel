"""Durable report materialization worker with leases, retries, and resume support."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


@dataclass(frozen=True, slots=True)
class ReportMaterializationJob:
    id: str
    analysis_id: str
    attempt_count: int
    max_attempts: int


class PostgresReportMaterializationQueue:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def claim(
        self, worker_id: str, *, limit: int, lease_seconds: int
    ) -> list[ReportMaterializationJob]:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    WITH expired AS (
                      SELECT id, analysis_result_id, attempt_count, max_attempts
                      FROM report_materialization_job
                      WHERE status = 'running' AND lease_expires_at <= now()
                      FOR UPDATE SKIP LOCKED
                    ), updated AS (
                      UPDATE report_materialization_job job
                      SET status = CASE
                            WHEN expired.attempt_count >= expired.max_attempts
                              THEN 'blocked' ELSE 'retry_wait' END,
                          stage = CASE
                            WHEN expired.attempt_count >= expired.max_attempts
                              THEN 'blocked' ELSE 'retry_wait' END,
                          available_at = now() + interval '15 seconds',
                          locked_by = NULL, locked_at = NULL, lease_expires_at = NULL,
                          last_error = 'Worker lease expired', updated_at = now()
                      FROM expired WHERE job.id = expired.id
                      RETURNING job.analysis_result_id, job.status
                    )
                    UPDATE analysis_result result
                    SET reporting_status = 'blocked'
                    FROM updated
                    WHERE result.id = updated.analysis_result_id
                      AND updated.status = 'blocked'
                    """
                )
            )
            rows = (
                await connection.execute(
                    text(
                        """
                        WITH candidates AS (
                          SELECT id
                          FROM report_materialization_job
                          WHERE status IN ('queued', 'retry_wait')
                            AND available_at <= now()
                            AND attempt_count < max_attempts
                          ORDER BY available_at, created_at
                          FOR UPDATE SKIP LOCKED
                          LIMIT :limit
                        )
                        UPDATE report_materialization_job job
                        SET status = 'running', stage = 'preparing',
                            attempt_count = attempt_count + 1,
                            locked_by = :worker_id, locked_at = now(),
                            lease_expires_at = now() + make_interval(secs => :lease_seconds),
                            started_at = COALESCE(started_at, now()), updated_at = now()
                        FROM candidates, analysis_result result
                        WHERE job.id = candidates.id AND result.id = job.analysis_result_id
                        RETURNING job.id::text, result.analysis_id,
                          job.attempt_count, job.max_attempts
                        """
                    ),
                    {
                        "limit": limit,
                        "worker_id": worker_id,
                        "lease_seconds": lease_seconds,
                    },
                )
            ).mappings()
            return [
                ReportMaterializationJob(
                    id=str(row["id"]),
                    analysis_id=str(row["analysis_id"]),
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
                    UPDATE report_materialization_job
                    SET lease_expires_at = now() + make_interval(secs => :lease_seconds),
                        updated_at = now()
                    WHERE id = CAST(:job_id AS uuid) AND status = 'running'
                      AND locked_by = :worker_id AND lease_expires_at > now()
                    """
                ),
                {
                    "job_id": job_id,
                    "worker_id": worker_id,
                    "lease_seconds": lease_seconds,
                },
            )
            return bool(result.rowcount)

    async def fail(self, job: ReportMaterializationJob, worker_id: str, error: str) -> None:
        non_retryable = any(
            marker in error.casefold()
            for marker in (
                "trust gate failed",
                "report is not decision-ready",
                "no governed comparison basis",
            )
        )
        terminal = non_retryable or job.attempt_count >= job.max_attempts
        async with self._engine.begin() as connection:
            result = await connection.execute(
                text(
                    """
                    UPDATE report_materialization_job
                    SET status = :status, stage = :stage,
                        available_at = CASE WHEN :terminal
                          THEN available_at
                          ELSE now() + make_interval(
                            secs => LEAST(300, 15 * power(2, attempt_count))::double precision
                          )
                        END,
                        locked_by = NULL, locked_at = NULL, lease_expires_at = NULL,
                        last_error = :error, updated_at = now()
                    WHERE id = CAST(:job_id AS uuid) AND status = 'running'
                      AND locked_by = :worker_id
                    RETURNING analysis_result_id::text
                    """
                ),
                {
                    "job_id": job.id,
                    "worker_id": worker_id,
                    "status": "blocked" if terminal else "retry_wait",
                    "stage": "blocked" if terminal else "retry_wait",
                    "terminal": terminal,
                    "error": error[:8000],
                },
            )
            analysis_result_id = result.scalar_one_or_none()
            if analysis_result_id is None:
                return
            if terminal:
                await connection.execute(
                    text(
                        "UPDATE analysis_result SET reporting_status = 'blocked' "
                        "WHERE id::text = :analysis_result_id"
                    ),
                    {"analysis_result_id": str(analysis_result_id)},
                )


class ReportMaterializationClient:
    def __init__(self, *, api_url: str, token: str, worker_id: str) -> None:
        self._base = api_url.rstrip("/")
        self._headers = {
            "X-RCI-Internal-Token": token,
            "X-RCI-Worker-ID": worker_id,
        }

    async def _post(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=httpx.Timeout(1800.0, connect=30.0)) as client:
            response = await client.post(f"{self._base}{path}", headers=self._headers, json=body)
        if response.is_error:
            try:
                detail = response.json().get("detail")
            except Exception:
                detail = response.text
            raise RuntimeError(f"materialization API {response.status_code}: {detail}")
        return dict(response.json())

    async def prepare(self, job_id: str) -> dict[str, Any]:
        return await self._post(f"/api/v1/internal/report-materialization-jobs/{job_id}/prepare")

    async def price_architecture(self, job_id: str) -> None:
        await self._post(
            f"/api/v1/internal/report-materialization-jobs/{job_id}/price-architecture"
        )

    async def portfolio(self, job_id: str, profile_id: str, radius_miles: int) -> None:
        await self._post(
            f"/api/v1/internal/report-materialization-jobs/{job_id}/competitive-portfolio",
            {"profile_id": profile_id, "radius_miles": radius_miles},
        )

    async def finalize(self, job_id: str) -> None:
        await self._post(f"/api/v1/internal/report-materialization-jobs/{job_id}/finalize")


class ReportMaterializationWorker:
    def __init__(
        self,
        queue: PostgresReportMaterializationQueue,
        client: ReportMaterializationClient,
        *,
        worker_id: str,
        claim_limit: int = 1,
        lease_seconds: int = 900,
    ) -> None:
        self._queue = queue
        self._client = client
        self._worker_id = worker_id
        self._claim_limit = claim_limit
        self._lease_seconds = lease_seconds

    async def run_once(self) -> int:
        jobs = await self._queue.claim(
            self._worker_id,
            limit=self._claim_limit,
            lease_seconds=self._lease_seconds,
        )
        await asyncio.gather(*(self._execute(job) for job in jobs))
        return len(jobs)

    async def _execute(self, job: ReportMaterializationJob) -> None:
        finished = asyncio.Event()
        heartbeat = asyncio.create_task(self._heartbeat(job.id, finished))
        try:
            plan = await self._client.prepare(job.id)
            completed = set(plan.get("completed_scopes", []))
            price_scopes = {f"price_architecture:{scope}" for scope in plan.get("price_scopes", [])}
            if not price_scopes.issubset(completed):
                await self._client.price_architecture(job.id)
            for scope in plan.get("portfolio_scopes", []):
                completed_key = f"competitive_portfolio:{scope}"
                if completed_key in completed:
                    continue
                profile_id, radius = str(scope).rsplit(":", 1)
                await self._client.portfolio(job.id, profile_id, int(radius))
            await self._client.finalize(job.id)
        except Exception as exc:
            await self._queue.fail(job, self._worker_id, str(exc))
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
