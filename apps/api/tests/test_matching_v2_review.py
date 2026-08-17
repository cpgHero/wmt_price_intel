from __future__ import annotations

import hashlib
import inspect
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from rci_api.main import create_app
from rci_api.matching_v2_review import (
    AdjudicationRequest,
    AIBulkCertificationCommitRequest,
    AIBulkCertificationPreviewRequest,
    AIReviewBatchRequest,
    AIReviewDraftRequest,
    AIReviewRetryRequest,
    ImportReviewQueueRequest,
    MatchingV2ReviewService,
    PostgresMatchingV2ReviewRepository,
    ReviewSubmissionRequest,
    _apply_observed_location_sidecar,
    _bulk_ai_certification_eligibility,
    _bulk_preview_document,
    _is_ai_retry_integrity_failure,
    get_matching_v2_review_service,
)
from rci_contracts import validate_instance

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


def test_observed_location_sidecar_backfills_legacy_queue_without_overwriting(
    tmp_path: Path,
) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "matching-v2-review-footprints.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "queues": [
                    {
                        "queue_id": "banana-review",
                        "queue_version": "1.1.0",
                        "listings": {
                            "walmart_us:one": {
                                "observed_location_count": 4200,
                                "seller_governance": {
                                    "eligible": True,
                                    "status": "verified_first_party",
                                },
                            },
                            "aldi_us:one": {"observed_location_count": 1700},
                        },
                        "cases": {
                            "case-one": {
                                "competitor_observed_location_count": 1600,
                            }
                        },
                    }
                ],
            }
        )
    )
    documents = [
        {
            "case_id": "case-one",
            "benchmark_listing_id": "walmart_us:one",
            "competitor_listing_id": "aldi_us:one",
            "benchmark_listing": {"listing_id": "walmart_us:one"},
            "competitor_listing": {
                "listing_id": "aldi_us:one",
                "observed_location_count": 12,
            },
        }
    ]

    _apply_observed_location_sidecar(
        documents,
        queue_id="banana-review",
        queue_version="1.1.0",
        root=tmp_path,
    )

    assert documents[0]["benchmark_listing"]["observed_location_count"] == 4200
    assert documents[0]["competitor_listing"]["observed_location_count"] == 12
    assert documents[0]["benchmark_listing"]["seller_governance"] == {
        "eligible": True,
        "status": "verified_first_party",
        "source": "reconciled_release_evidence",
        "resolution_method": "legacy_queue_sidecar",
    }


def test_active_release_queue_reconciliation_is_complete_and_has_no_known_third_party() -> None:
    catalog = json.loads(
        (REPOSITORY_ROOT / "config/matching-v2-review-footprints.json").read_text()
    )
    expected = {
        "fresh_bananas-matching-v2-release-review": ("1.1.0", 94),
        "fresh_strawberries-matching-v2-release-review": ("1.1.0", 72),
        "fresh_ground_beef-matching-v2-release-review": ("1.1.0", 210),
        "fresh_fluid_milk-matching-v2-release-review": ("1.0.0", 311),
        "fresh_shell_eggs-matching-v2-release-review": ("1.1.0", 1217),
    }
    queues = {queue["queue_id"]: queue for queue in catalog["queues"]}

    assert catalog["schema_version"] == "2.0.0"
    assert set(queues) == set(expected)
    for queue_id, (queue_version, case_count) in expected.items():
        queue = queues[queue_id]
        assert queue["queue_version"] == queue_version
        assert queue["source"]["replay_case_count"] == case_count
        assert queue["listings"]
        for listing in queue["listings"].values():
            assert listing["observed_location_count"] > 0
            assert listing["seller_governance"]["eligible"] is True
            assert listing["seller_governance"]["status"] in {
                "verified_first_party",
                "seller_unverified",
                "not_governed",
            }


def test_latest_human_decision_is_final_until_flagged_and_then_replaced() -> None:
    created = datetime(2026, 8, 16, tzinfo=UTC)
    cases = [
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "case_document": {"case_id": "case-one"},
        }
    ]
    approval = {
        "id": "approval",
        "review_case_id": cases[0]["id"],
        "reviewer_id": "reviewer-a",
        "verdict": "comparable",
        "allowed_tiers": ["equivalent_product"],
        "rationale": "Attributes agree.",
        "evidence_refs": ["artifact://approval"],
        "created_at": created,
    }
    flag = {
        "id": "flag",
        "review_case_id": cases[0]["id"],
        "reviewer_id": "reviewer-b",
        "verdict": "insufficient_evidence",
        "allowed_tiers": [],
        "rationale": "Package image conflicts.",
        "evidence_refs": ["artifact://flag"],
        "created_at": created + timedelta(minutes=1),
    }
    replacement = {
        "id": "replacement",
        "review_case_id": cases[0]["id"],
        "reviewer_id": "reviewer-c",
        "verdict": "not_comparable",
        "allowed_tiers": [],
        "rationale": "Package forms differ.",
        "evidence_refs": ["artifact://replacement"],
        "created_at": created + timedelta(minutes=2),
    }

    approved = PostgresMatchingV2ReviewRepository._case_documents(cases, [approval], [], [])[0]
    flagged = PostgresMatchingV2ReviewRepository._case_documents(cases, [flag, approval], [], [])[0]
    rejected = PostgresMatchingV2ReviewRepository._case_documents(
        cases, [replacement, flag, approval], [], []
    )[0]

    assert approved["review_status"] == "approved"
    assert approved["final_decision"]["source"] == "review_submission"
    assert flagged["review_status"] == "flagged"
    assert rejected["review_status"] == "rejected"
    assert rejected["final_decision"]["reviewer_id"] == "reviewer-c"


def test_finalized_case_requires_flag_before_replacement_submission() -> None:
    source = inspect.getsource(PostgresMatchingV2ReviewRepository.submit_review)

    assert "must be flagged before its decision can change" in source
    assert 'submission["verdict"] != "insufficient_evidence"' in source


def test_release_gold_set_accepts_one_final_human_reviewer() -> None:
    validate_instance(
        REPOSITORY_ROOT,
        "matching-v2-gold-set.schema.json",
        {
            "schema_version": "2.0.0",
            "gold_set_id": "single-review-release",
            "version": "1.0.0",
            "purpose": "release_certification",
            "product_pack": {"id": "fresh_bananas", "version": "1.2.0"},
            "source_evidence": ["artifact://banana-evidence"],
            "labels": [
                {
                    "case_id": "case-one",
                    "benchmark_listing_id": "walmart_us:one",
                    "competitor_listing_id": "aldi_us:one",
                    "expected_comparable": True,
                    "allowed_tiers": ["equivalent_product"],
                    "critical": True,
                    "stratum": "exact_specification",
                    "review_status": "single_reviewed",
                    "reviewers": ["reviewer@cpghero.com"],
                    "evidence_refs": ["artifact://banana-evidence"],
                    "rationale": "The governed package attributes agree.",
                }
            ],
        },
        label="single-review release gold set",
    )


class ReviewRepository:
    def __init__(self) -> None:
        self.imported: dict[str, Any] | None = None
        self.submissions: list[dict[str, Any]] = []
        self.adjudications: list[dict[str, Any]] = []
        self.ai_drafts: list[dict[str, Any]] = []
        self.ai_retries: list[dict[str, Any]] = []
        self.bulk_commits: list[dict[str, Any]] = []

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
            "batch_id": "00000000-0000-0000-0000-000000000099",
            "created_at": "2026-08-16T12:00:00+00:00",
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

    async def retry_ai_drafts(
        self,
        external_queue_id: str,
        external_case_ids: Sequence[str],
        *,
        requested_by: str,
        model_id: str,
        prompt: Mapping[str, str],
        retry_reason: str,
    ) -> list[dict[str, Any]]:
        tasks = [
            {
                "queue_id": external_queue_id,
                "case_id": case_id,
                "batch_id": "00000000-0000-0000-0000-000000000199",
                "created_at": "2026-08-16T13:00:00+00:00",
                "requested_by": requested_by,
                "model_id": model_id,
                "prompt": prompt,
                "retry_of_task_id": f"failed-{case_id}",
                "retry_sequence": 1,
                "retry_reason": retry_reason,
                "authoritative": False,
                "human_review_required": True,
            }
            for case_id in external_case_ids
        ]
        self.ai_retries.extend(tasks)
        return tasks

    async def preview_ai_bulk_certification(
        self,
        external_queue_id: str,
        external_case_ids: Sequence[str],
    ) -> dict[str, Any]:
        return {
            "queue_id": external_queue_id,
            "eligible_case_count": len(external_case_ids),
            "eligible_cases": [{"case_id": case_id} for case_id in external_case_ids],
            "confirmation_checksum": "a" * 64,
        }

    async def commit_ai_bulk_certification(
        self,
        external_queue_id: str,
        external_case_ids: Sequence[str],
        *,
        reviewer_id: str,
        confirmation_checksum: str,
    ) -> dict[str, Any]:
        result = {
            "queue_id": external_queue_id,
            "approved_case_ids": list(external_case_ids),
            "reviewer_id": reviewer_id,
            "confirmation_checksum": confirmation_checksum,
        }
        self.bulk_commits.append(result)
        return result


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


async def test_review_service_rejects_known_third_party_seller_queue() -> None:
    repository = ReviewRepository()
    service = MatchingV2ReviewService(repository, REPOSITORY_ROOT)
    document = _queue()
    document["cases"][0]["benchmark_listing"]["seller_governance"] = {
        "eligible": False,
        "status": "excluded_third_party",
    }
    document.pop("checksum")
    document["checksum"] = hashlib.sha256(_canonical(document).encode()).hexdigest()

    with pytest.raises(ValueError, match="known third-party marketplace seller"):
        await service.import_queue(
            ImportReviewQueueRequest(
                organization_id="00000000-0000-0000-0000-000000000001",
                imported_by="review-admin",
                queue=document,
            )
        )

    assert repository.imported is None


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
    assert result["batch"] == {
        "id": "00000000-0000-0000-0000-000000000099",
        "created_at": "2026-08-16T12:00:00+00:00",
        "requested_case_count": 2,
    }
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


async def test_ai_review_retry_is_new_linked_advisory_work_with_preserved_history() -> None:
    repository = ReviewRepository()
    service = MatchingV2ReviewService(repository, REPOSITORY_ROOT)

    result = await service.retry_ai_drafts(
        "queue-1",
        AIReviewRetryRequest(
            requested_by="reviewer-a",
            case_ids=["case-1", "case-2"],
            retry_reason="Administrator inspected the terminal failures.",
        ),
        model_id="gpt-5.6-terra",
    )

    assert result["authoritative"] is False
    assert result["human_review_required"] is True
    assert result["history_preserved"] is True
    assert result["requested_case_count"] == 2
    assert result["batch"]["id"] == "00000000-0000-0000-0000-000000000199"
    assert [task["retry_of_task_id"] for task in repository.ai_retries] == [
        "failed-case-1",
        "failed-case-2",
    ]
    with pytest.raises(ValueError, match="unique"):
        await service.retry_ai_drafts(
            "queue-1",
            AIReviewRetryRequest(
                requested_by="reviewer-a",
                case_ids=["case-1", "case-1"],
                retry_reason="Retry duplicate should fail.",
            ),
            model_id="gpt-5.6-terra",
        )


def test_ai_review_retry_blocks_governed_integrity_failures() -> None:
    assert _is_ai_retry_integrity_failure(
        "AI matching review task does not match governed input or prompt"
    )
    assert not _is_ai_retry_integrity_failure("Provider timed out before returning output")


def test_postgres_ai_review_retry_preserves_history_and_reapplies_guardrails() -> None:
    source = inspect.getsource(PostgresMatchingV2ReviewRepository.retry_ai_drafts)

    assert "UPDATE matching_v2_ai_review_task" not in source
    assert "_insert_ai_retry_task" in source
    assert "known third-party marketplace seller cases cannot retry" in source
    assert "finalized review cases cannot retry" in source
    assert "governed input or prompt integrity failures" in source
    assert "pg_advisory_xact_lock" in source


def _bulk_eligible_case() -> dict[str, Any]:
    case = _queue()["cases"][0]
    case["review_status"] = "pending"
    case["case_checksum"] = "b" * 64
    case["ai_output_checksum"] = "c" * 64
    case["benchmark_listing"]["seller_governance"] = {"status": "verified_first_party"}
    case["competitor_listing"]["seller_governance"] = {"status": "not_governed"}
    case["ai_draft"] = {
        "id": "ai-task-one",
        "status": "succeeded",
        "output_document": {
            "authoritative": False,
            "human_review_required": True,
            "result": {
                "verdict_proposal": "comparable",
                "tier_proposal": "exact_specification",
                "rationale": "The governed package facts agree.",
                "attribute_proposals": [],
                "conflicts": [],
                "requires_human_review": True,
            },
        },
    }
    return case


def test_bulk_ai_certification_accepts_affirmative_recommendations_with_warnings() -> None:
    eligible = _bulk_eligible_case()

    evaluation = _bulk_ai_certification_eligibility(eligible)

    assert evaluation["eligible"] is True
    assert evaluation["reason_codes"] == []
    assert evaluation["warning_codes"] == []
    assert evaluation["recommended_tier"] == "exact_specification"

    conflicting = _bulk_eligible_case()
    conflicting["ai_draft"]["output_document"]["result"]["conflicts"] = [
        "Package count is unresolved."
    ]
    conflicting["competitor_listing"]["seller_governance"] = {"status": "excluded_third_party"}
    conflicting["ai_draft"]["output_document"]["result"]["tier_proposal"] = "comparable_substitute"

    rejected = _bulk_ai_certification_eligibility(conflicting)

    assert rejected["eligible"] is False
    assert rejected["reason_codes"] == ["known_third_party_seller"]
    assert {
        "ai_engine_tier_disagreement",
        "ai_conflict_present",
    }.issubset(rejected["warning_codes"])

    administrator_approvable = _bulk_eligible_case()
    administrator_approvable["ai_draft"]["output_document"]["result"]["conflicts"] = [
        "Package count is unresolved."
    ]
    administrator_approvable["ai_draft"]["output_document"]["result"]["attribute_proposals"] = [
        {
            "attribute": "package_count",
            "value": "1",
            "confidence": 0.6,
            "evidence_source": "structured",
            "visible_text": None,
            "source_image_url": None,
        }
    ]

    warned = _bulk_ai_certification_eligibility(administrator_approvable)

    assert warned["eligible"] is True
    assert warned["reason_codes"] == []
    assert warned["warning_codes"] == [
        "ai_conflict_present",
        "low_confidence_ai_attribute",
    ]


def test_bulk_ai_preview_binds_eligible_ai_output_and_policy_to_checksum() -> None:
    first = _bulk_eligible_case()
    preview = _bulk_preview_document(
        queue_id="queue-one",
        queue_version="1.0.0",
        snapshots=[first],
    )
    changed = _bulk_eligible_case()
    changed["ai_output_checksum"] = "d" * 64
    changed_preview = _bulk_preview_document(
        queue_id="queue-one",
        queue_version="1.0.0",
        snapshots=[changed],
    )

    assert preview["eligible_case_count"] == 1
    assert preview["excluded_case_count"] == 0
    assert len(preview["confirmation_checksum"]) == 64
    assert preview["confirmation_checksum"] != changed_preview["confirmation_checksum"]
    assert preview["human_confirmation_required"] is True
    assert preview["automatically_changes_reporting"] is False


def test_bulk_ai_preview_surfaces_advisory_warnings_without_blocking_confirmation() -> None:
    warned = _bulk_eligible_case()
    warned["ai_draft"]["output_document"]["result"]["conflicts"] = [
        "A governed attribute needs administrator judgment."
    ]

    preview = _bulk_preview_document(
        queue_id="queue-one",
        queue_version="1.0.0",
        snapshots=[warned],
    )

    assert preview["eligible_case_count"] == 1
    assert preview["excluded_case_count"] == 0
    assert preview["eligible_cases"][0]["warnings"] == [
        "The AI draft identifies one or more unresolved conflicts."
    ]
    assert preview["warning_summary"] == [
        {
            "warning_code": "ai_conflict_present",
            "warning": "The AI draft identifies one or more unresolved conflicts.",
            "case_count": 1,
        }
    ]
    assert len(preview["confirmation_checksum"]) == 64


def test_bulk_ai_preview_assesses_queue_wide_candidates_but_bounds_confirmation() -> None:
    snapshots = []
    for index in range(55):
        case = _bulk_eligible_case()
        case["case_id"] = f"case-{index:03d}"
        case["case_checksum"] = f"{index:064x}"
        case["ai_draft"] = {**case["ai_draft"], "id": f"ai-task-{index:03d}"}
        case["ai_output_checksum"] = f"{index + 100:064x}"
        snapshots.append(case)

    preview = _bulk_preview_document(
        queue_id="queue-one",
        queue_version="1.0.0",
        snapshots=snapshots,
    )

    assert preview["requested_case_count"] == 55
    assert preview["eligible_case_count"] == 50
    assert preview["excluded_case_count"] == 5
    assert preview["exclusion_summary"] == [
        {
            "reason_code": "bulk_batch_limit",
            "reason": (
                "The relationship passed the required gates but is deferred to the next "
                "50-case confirmation batch."
            ),
            "case_count": 5,
        }
    ]


async def test_bulk_ai_certification_service_requires_unique_cases_and_human_identity() -> None:
    repository = ReviewRepository()
    service = MatchingV2ReviewService(repository, REPOSITORY_ROOT)

    preview = await service.preview_ai_bulk_certification(
        "queue-1",
        AIBulkCertificationPreviewRequest(case_ids=["case-1", "case-2"]),
    )
    committed = await service.commit_ai_bulk_certification(
        "queue-1",
        AIBulkCertificationCommitRequest(
            reviewer_id="reviewer@cpghero.com",
            case_ids=["case-1", "case-2"],
            confirmation_checksum="a" * 64,
        ),
    )

    assert preview["eligible_case_count"] == 2
    assert committed["approved_case_ids"] == ["case-1", "case-2"]
    assert repository.bulk_commits[0]["reviewer_id"] == "reviewer@cpghero.com"
    with pytest.raises(ValueError, match="unique"):
        await service.preview_ai_bulk_certification(
            "queue-1",
            AIBulkCertificationPreviewRequest(case_ids=["case-1", "case-1"]),
        )


def test_postgres_bulk_certification_copies_warnings_and_complete_ai_rationale() -> None:
    source = inspect.getsource(PostgresMatchingV2ReviewRepository.commit_ai_bulk_certification)

    assert "Advisory warnings acknowledged:" in source
    assert "AI evidence rationale:" in source
    assert "candidate['ai_rationale']" in source


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


async def test_ai_review_retry_route_requires_explicit_confirmation_context(
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
            "/api/v1/matching-v2/review-queues/queue-1/ai-drafts/retry",
            json={
                "requested_by": "reviewer-a",
                "case_ids": ["case-1"],
                "retry_reason": "Administrator inspected the terminal failure.",
            },
        )

    assert response.status_code == 202
    assert response.json()["history_preserved"] is True
    assert response.json()["human_review_required"] is True
    assert repository.ai_retries[0]["case_id"] == "case-1"
