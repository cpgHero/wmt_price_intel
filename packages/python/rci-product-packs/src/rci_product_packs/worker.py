"""Leased worker for deterministic Product Pack certification jobs."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable

from rci_product_packs.models import ProductPackDraft, ProductPackEvidence, ProductPackValidationRun
from rci_product_packs.repository import PostgresProductPackAuthoringRepository

ValidationGate = dict[str, object]
BundleValidator = Callable[
    [ProductPackDraft, tuple[ProductPackEvidence, ...], str],
    list[ValidationGate] | Awaitable[list[ValidationGate]],
]


class ProductPackValidationWorker:
    def __init__(
        self,
        repository: PostgresProductPackAuthoringRepository,
        validator: BundleValidator,
        *,
        worker_id: str,
        claim_limit: int = 1,
        lease_seconds: int = 900,
    ) -> None:
        self._repository = repository
        self._validator = validator
        self._worker_id = worker_id
        self._claim_limit = claim_limit
        self._lease_seconds = lease_seconds

    async def run_once(self) -> int:
        jobs = await self._repository.claim_validations(
            worker_id=self._worker_id,
            limit=self._claim_limit,
            lease_seconds=self._lease_seconds,
        )
        for job in jobs:
            await self._run(job)
        return len(jobs)

    async def _run(self, job: ProductPackValidationRun) -> None:
        try:
            draft = await self._repository.get_draft(job.draft_id)
            if draft.revision != job.draft_revision or draft.checksum != job.draft_checksum:
                gates: list[ValidationGate] = [
                    {
                        "id": "draft_revision",
                        "label": "Draft revision",
                        "status": "failed",
                        "message": "The draft changed after this validation was requested.",
                    }
                ]
            else:
                evidence = tuple(await self._repository.list_evidence(job.draft_id))
                result = self._validator(draft, evidence, job.suite)
                gates = await result if inspect.isawaitable(result) else result
            passed = all(str(gate.get("status")) in {"passed", "warning"} for gate in gates)
            await self._repository.complete_validation(
                job.id,
                worker_id=self._worker_id,
                passed=passed,
                gates=gates,
                error=None if passed else "One or more certification gates failed.",
            )
        except Exception as exc:
            await self._repository.fail_validation_attempt(
                job.id,
                worker_id=self._worker_id,
                error=str(exc),
            )
