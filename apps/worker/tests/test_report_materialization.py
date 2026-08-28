from __future__ import annotations

from typing import Any

from rci_worker.report_materialization import (
    ReportMaterializationJob,
    ReportMaterializationWorker,
)


class FakeQueue:
    def __init__(self, job: ReportMaterializationJob) -> None:
        self.job = job
        self.failed: list[str] = []

    async def claim(
        self, worker_id: str, *, limit: int, lease_seconds: int
    ) -> list[ReportMaterializationJob]:
        job, self.job = self.job, None  # type: ignore[assignment]
        return [job] if job is not None else []

    async def extend_lease(self, job_id: str, worker_id: str, lease_seconds: int) -> bool:
        return True

    async def fail(self, job: ReportMaterializationJob, worker_id: str, error: str) -> None:
        self.failed.append(error)


class FakeClient:
    def __init__(self, *, fail_finalize: bool = False) -> None:
        self.calls: list[str] = []
        self.fail_finalize = fail_finalize

    async def prepare(self, job_id: str) -> dict[str, Any]:
        self.calls.append("prepare")
        return {
            "price_scopes": [
                "benchmark_anchored:0.50",
                "fixed_range:0.50",
                "fixed_range:1.00",
            ],
            "catalog_retailers": ["walmart_us", "aldi_us"],
            "portfolio_scopes": ["strict:1", "strict:3", "strict:5"],
            "completed_scopes": [
                "price_architecture:benchmark_anchored:0.50",
                "price_architecture:fixed_range:0.50",
                "price_architecture:fixed_range:1.00",
                "price_catalog:walmart_us",
                "competitive_portfolio:strict:1",
            ],
        }

    async def price_architecture(self, job_id: str) -> None:
        self.calls.append("price")

    async def price_catalog(self, job_id: str, retailer_id: str) -> None:
        self.calls.append(f"catalog:{retailer_id}")

    async def portfolio(self, job_id: str, profile_id: str, radius_miles: int) -> None:
        self.calls.append(f"portfolio:{profile_id}:{radius_miles}")

    async def finalize(self, job_id: str) -> None:
        self.calls.append("finalize")
        if self.fail_finalize:
            raise RuntimeError("semantic gate failed")


def _job() -> ReportMaterializationJob:
    return ReportMaterializationJob(
        id="job-1",
        analysis_id="analysis-1",
        attempt_count=1,
        max_attempts=3,
    )


async def test_worker_resumes_completed_scopes_and_finalizes() -> None:
    queue = FakeQueue(_job())
    client = FakeClient()
    worker = ReportMaterializationWorker(  # type: ignore[arg-type]
        queue,
        client,  # type: ignore[arg-type]
        worker_id="worker-1",
        lease_seconds=30,
    )

    assert await worker.run_once() == 1
    assert client.calls == [
        "prepare",
        "catalog:aldi_us",
        "portfolio:strict:3",
        "portfolio:strict:5",
        "finalize",
    ]
    assert queue.failed == []


async def test_worker_releases_failure_to_durable_retry_policy() -> None:
    queue = FakeQueue(_job())
    client = FakeClient(fail_finalize=True)
    worker = ReportMaterializationWorker(  # type: ignore[arg-type]
        queue,
        client,  # type: ignore[arg-type]
        worker_id="worker-1",
        lease_seconds=30,
    )

    assert await worker.run_once() == 1
    assert queue.failed == ["semantic gate failed"]
