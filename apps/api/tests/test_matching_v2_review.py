from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from rci_api.main import create_app
from rci_api.matching_v2_review import (
    AdjudicationRequest,
    ImportReviewQueueRequest,
    MatchingV2ReviewService,
    ReviewSubmissionRequest,
    get_matching_v2_review_service,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)


def _queue() -> dict[str, Any]:
    document = json.loads(
        (REPOSITORY_ROOT / "examples/matching-v2-review-queue.milk.json").read_text()
    )
    document.pop("checksum")
    document["checksum"] = hashlib.sha256(_canonical(document).encode()).hexdigest()
    return document


class ReviewRepository:
    def __init__(self) -> None:
        self.imported: dict[str, Any] | None = None
        self.submissions: list[dict[str, Any]] = []
        self.adjudications: list[dict[str, Any]] = []

    async def list_queues(self, *, limit: int) -> list[dict[str, Any]]:
        assert limit > 0
        return []

    async def import_queue(
        self,
        organization_id: str,
        queue: dict[str, Any],
        *,
        imported_by: str,
    ) -> dict[str, Any]:
        self.imported = {
            "organization_id": organization_id,
            "queue": queue,
            "imported_by": imported_by,
        }
        return {"queue_id": queue["queue_id"], "imported": True, "case_count": 1}

    async def queue_view(self, external_queue_id: str, **filters: Any) -> dict[str, Any]:
        assert external_queue_id == "milk-release-review-contract-fixture"
        return {
            "schema_version": "2.0.0-review-view",
            "authoritative": False,
            "queue": {
                "queue_id": external_queue_id,
                "version": "1.0.0",
                "product_pack": {"id": "fresh_fluid_milk", "version": "1.3.0"},
            },
            "total_cases": 1,
            "status_counts": {"pending": 1},
            "filters": filters,
            "cases": [],
        }

    async def submit_review(
        self,
        external_queue_id: str,
        external_case_id: str,
        submission: dict[str, Any],
        *,
        submission_checksum: str,
    ) -> dict[str, Any]:
        self.submissions.append(
            {
                "queue_id": external_queue_id,
                "case_id": external_case_id,
                **submission,
                "checksum": submission_checksum,
            }
        )
        return {"case_id": external_case_id, "checksum": submission_checksum}

    async def adjudicate(
        self,
        external_queue_id: str,
        external_case_id: str,
        adjudication: dict[str, Any],
        *,
        adjudication_checksum: str,
    ) -> dict[str, Any]:
        self.adjudications.append(
            {
                "queue_id": external_queue_id,
                "case_id": external_case_id,
                **adjudication,
                "checksum": adjudication_checksum,
            }
        )
        return {"case_id": external_case_id, "checksum": adjudication_checksum}


async def test_review_service_validates_queue_checksum_before_import() -> None:
    repository = ReviewRepository()
    service = MatchingV2ReviewService(repository, REPOSITORY_ROOT)
    request = ImportReviewQueueRequest(
        organization_id="00000000-0000-0000-0000-000000000001",
        imported_by="review-admin",
        queue=_queue(),
    )

    result = await service.import_queue(request)

    assert result["imported"] is True
    assert repository.imported is not None
    invalid = request.model_copy(deep=True)
    invalid.queue["checksum"] = "0" * 64
    with pytest.raises(ValueError, match="checksum"):
        await service.import_queue(invalid)


async def test_review_and_adjudication_require_governed_tiers_and_two_submissions() -> None:
    repository = ReviewRepository()
    service = MatchingV2ReviewService(repository, REPOSITORY_ROOT)
    await service.submit_review(
        "queue-1",
        "case-1",
        ReviewSubmissionRequest(
            reviewer_id="reviewer-a",
            verdict="comparable",
            allowed_tiers=["equivalent_product"],
            rationale="Package and claims agree.",
            evidence_refs=["artifact://evidence/a"],
        ),
    )
    assert len(repository.submissions) == 1

    with pytest.raises(ValueError, match="distinct submission"):
        await service.adjudicate(
            "queue-1",
            "case-1",
            AdjudicationRequest(
                adjudicator_id="reviewer-a",
                verdict="comparable",
                allowed_tiers=["equivalent_product"],
                rationale="Consensus.",
                evidence_refs=["artifact://evidence/a"],
                submission_ids=["submission-1", "submission-1"],
            ),
        )


async def test_review_queue_route_is_authenticated_surface_and_non_authoritative() -> None:
    repository = ReviewRepository()
    service = MatchingV2ReviewService(repository, REPOSITORY_ROOT)
    app = create_app()
    app.dependency_overrides[get_matching_v2_review_service] = lambda: service
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/matching-v2/review-queues/milk-release-review-contract-fixture",
            params={"review_status": "pending", "limit": 20},
        )

    assert response.status_code == 200
    assert response.json()["authoritative"] is False


async def test_review_submission_route_is_scoped_to_its_queue() -> None:
    repository = ReviewRepository()
    service = MatchingV2ReviewService(repository, REPOSITORY_ROOT)
    app = create_app()
    app.dependency_overrides[get_matching_v2_review_service] = lambda: service
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/matching-v2/review-queues/queue-1/cases/case-1/submissions",
            json={
                "reviewer_id": "reviewer-a",
                "verdict": "comparable",
                "allowed_tiers": ["equivalent_product"],
                "rationale": "Package and governed claims agree.",
                "evidence_refs": ["artifact://evidence/a"],
            },
        )

    assert response.status_code == 201
    assert repository.submissions[0]["queue_id"] == "queue-1"
    assert repository.submissions[0]["case_id"] == "case-1"
