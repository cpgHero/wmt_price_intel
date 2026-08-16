from __future__ import annotations

import hashlib
import inspect
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from rci_api.main import create_app
from rci_api.matching_v2_review import (
    AdjudicationRequest,
    AIReviewBatchRequest,
    AIReviewDraftRequest,
    ImportReviewQueueRequest,
    MatchingV2ReviewService,
    PostgresMatchingV2ReviewRepository,
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


def test_postgres_review_filters_cast_nullable_text_parameters() -> None:
    source = inspect.getsource(PostgresMatchingV2ReviewRepository._case_rows)

    assert "CAST(:competitor_retailer_id AS text) IS NULL" in source
    assert "competitor_retailer_id = CAST(:competitor_retailer_id AS text)" in source
    assert "CAST(:stratum AS text) IS NULL" in source
    assert "stratum = CAST(:stratum AS text)" in source


def test_postgres_review_case_lookup_qualifies_joined_primary_key() -> None:
    source = inspect.getsource(PostgresMatchingV2ReviewRepository._case_id)

    assert "SELECT c.id::text" in source
    assert "SELECT id::text" not in source


def test_review_cases_order_by_observed_benchmark_then_competitor_footprint() -> None:
    from rci_api.matching_v2_review import _case_order_key

    cases = [
        {
            "case_id": "small-primary",
            "critical": True,
            "stratum": "critical",
            "benchmark_listing": {"observed_location_count": 10},
            "competitor_listing": {"observed_location_count": 100},
        },
        {
            "case_id": "large-primary-small-competitor",
            "critical": False,
            "stratum": "review",
            "benchmark_listing": {"observed_location_count": 500},
            "competitor_listing": {"observed_location_count": 20},
        },
        {
            "case_id": "large-primary-large-competitor",
            "critical": False,
            "stratum": "review",
            "benchmark_listing": {"observed_location_count": 500},
            "competitor_listing": {"observed_location_count": 80},
        },
    ]

    ordered = sorted(cases, key=_case_order_key)

    assert [row["case_id"] for row in ordered] == [
        "large-primary-large-competitor",
        "large-primary-small-competitor",
        "small-primary",
    ]


class ReviewRepository:
    def __init__(self) -> None:
        self.imported: dict[str, Any] | None = None
        self.submissions: list[dict[str, Any]] = []
        self.adjudications: list[dict[str, Any]] = []
        self.ai_drafts: list[dict[str, Any]] = []

    async def list_queues(self, *, limit: int) -> list[dict[str, Any]]:
        assert limit > 0
        return []

    async def import_queue(
        self,
        organization_id: str,
        queue: Mapping[str, Any],
        *,
        imported_by: str,
    ) -> dict[str, Any]:
        self.imported = {
            "organization_id": organization_id,
            "queue": dict(queue),
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
        submission: Mapping[str, Any],
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
        adjudication: Mapping[str, Any],
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

    async def request_ai_draft(
        self,
        external_queue_id: str,
        external_case_id: str,
        *,
        requested_by: str,
        model_id: str,
        prompt: Mapping[str, str],
    ) -> dict[str, Any]:
        draft = {
            "queue_id": external_queue_id,
            "case_id": external_case_id,
            "requested_by": requested_by,
            "model_id": model_id,
            "prompt": prompt,
            "authoritative": False,
        }
        self.ai_drafts.append(draft)
        return draft

    async def request_ai_drafts(
        self,
        external_queue_id: str,
        external_case_ids: Sequence[str],
        *,
        requested_by: str,
        model_id: str,
        prompt: Mapping[str, str],
    ) -> list[dict[str, Any]]:
        return [
            await self.request_ai_draft(
                external_queue_id,
                case_id,
                requested_by=requested_by,
                model_id=model_id,
                prompt=prompt,
            )
            for case_id in external_case_ids
        ]


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


async def test_review_service_preserves_large_integers_from_raw_queue_json() -> None:
    repository = ReviewRepository()
    service = MatchingV2ReviewService(repository, REPOSITORY_ROOT)
    document = _queue()
    large_integer = 10_000_000_000_000_001
    document["cases"][0]["benchmark_listing"]["attributes"]["provider_sequence"] = {
        "value": large_integer,
        "source": "search",
        "reliability": 1.0,
        "review_status": "unreviewed",
    }
    document.pop("checksum")
    document["checksum"] = hashlib.sha256(_canonical(document).encode()).hexdigest()
    request = ImportReviewQueueRequest(
        organization_id="00000000-0000-0000-0000-000000000001",
        imported_by="review-admin",
        queue_json=json.dumps(document, ensure_ascii=False),
    )

    result = await service.import_queue(request)

    assert result["imported"] is True
    assert repository.imported is not None
    imported_value = repository.imported["queue"]["cases"][0]["benchmark_listing"]["attributes"][
        "provider_sequence"
    ]["value"]
    assert imported_value == large_integer


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
            params={
                "competitor_retailer_id": "aldi_us",
                "review_status": "pending",
                "limit": 20,
            },
        )

    assert response.status_code == 200
    assert response.json()["authoritative"] is False
    assert response.json()["filters"]["competitor_retailer_id"] == "aldi_us"


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


async def test_ai_review_draft_is_advisory_and_uses_versioned_prompt() -> None:
    repository = ReviewRepository()
    service = MatchingV2ReviewService(repository, REPOSITORY_ROOT)

    result = await service.request_ai_draft(
        "queue-1",
        "case-1",
        AIReviewDraftRequest(requested_by="reviewer-a"),
        model_id="gpt-5.6-terra",
    )

    assert result["authoritative"] is False
    assert repository.ai_drafts[0]["model_id"] == "gpt-5.6-terra"
    assert repository.ai_drafts[0]["prompt"]["id"] == "matching_v2_evidence_review"
    assert len(repository.ai_drafts[0]["prompt"]["checksum"]) == 64


async def test_ai_review_batch_is_bounded_idempotent_input_and_human_gated() -> None:
    repository = ReviewRepository()
    service = MatchingV2ReviewService(repository, REPOSITORY_ROOT)

    result = await service.request_ai_drafts(
        "queue-1",
        AIReviewBatchRequest(
            requested_by="reviewer-a",
            case_ids=["case-1", "case-2"],
        ),
        model_id="gpt-5.6-terra",
    )

    assert result["authoritative"] is False
    assert result["human_review_required"] is True
    assert result["requested_case_count"] == 2
    assert [draft["case_id"] for draft in repository.ai_drafts] == ["case-1", "case-2"]
    assert len({draft["prompt"]["checksum"] for draft in repository.ai_drafts}) == 1

    with pytest.raises(ValueError, match="unique"):
        await service.request_ai_drafts(
            "queue-1",
            AIReviewBatchRequest(
                requested_by="reviewer-a",
                case_ids=["case-1", "case-1"],
            ),
            model_id="gpt-5.6-terra",
        )


async def test_ai_review_batch_route_requires_explicit_enablement_and_remains_advisory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = ReviewRepository()
    service = MatchingV2ReviewService(repository, REPOSITORY_ROOT)
    app = create_app()
    app.dependency_overrides[get_matching_v2_review_service] = lambda: service
    monkeypatch.setenv("MATCHING_V2_AI_REVIEW_ENABLED", "true")
    monkeypatch.setenv("OPENAI_MODEL_MATCHING_REVIEW", "gpt-5.6-terra")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/matching-v2/review-queues/queue-1/ai-drafts",
            json={"requested_by": "reviewer-a", "case_ids": ["case-1", "case-2"]},
        )

    assert response.status_code == 202
    assert response.json()["authoritative"] is False
    assert response.json()["human_review_required"] is True
    assert response.json()["requested_case_count"] == 2
    assert [draft["case_id"] for draft in repository.ai_drafts] == ["case-1", "case-2"]
