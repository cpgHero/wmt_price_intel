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
    GoldSetReplayRequest,
    ImportReviewQueueRequest,
    MatchingV2ReviewService,
    PostgresMatchingV2ReviewRepository,
    ReviewSubmissionRequest,
    _active_certification_policy,
    _apply_active_certification_policy,
    _apply_observed_location_sidecar,
    _bulk_ai_certification_eligibility,
    _bulk_preview_document,
    _has_complete_observed_location_evidence,
    _is_ai_retry_integrity_failure,
    _matching_v2_certification_coverage,
    _review_queue_quarantine,
    get_matching_v2_review_service,
)
from rci_contracts import validate_instance

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_spring_valley_legacy_queue_is_explicitly_quarantined() -> None:
    quarantine = _review_queue_quarantine(
        REPOSITORY_ROOT,
        "vitamins_supplements-matching-v2-operational-certification",
        "2026.08.23-spring-valley-4",
    )

    assert quarantine is not None
    assert quarantine["carry_forward_allowed"] is False
    assert quarantine["reporting_release_allowed"] is False
    assert quarantine["successor_product_pack_version"] == "1.1.2"


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


def test_ai_review_requires_both_search_observed_footprints() -> None:
    case = {
        "benchmark_listing": {"observed_location_count": 4_525},
        "competitor_listing": {"observed_location_count": 2_595},
    }

    assert _has_complete_observed_location_evidence(case)
    case["competitor_listing"]["observed_location_count"] = 0
    assert not _has_complete_observed_location_evidence(case)
    case["competitor_listing"]["observed_location_count"] = None
    assert not _has_complete_observed_location_evidence(case)


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


def test_release_gold_set_accepts_reviewed_insufficient_evidence_exclusion() -> None:
    validate_instance(
        REPOSITORY_ROOT,
        "matching-v2-gold-set.schema.json",
        {
            "schema_version": "2.0.0",
            "gold_set_id": "reviewed-exclusion-release",
            "version": "1.0.0",
            "purpose": "release_certification",
            "product_pack": {"id": "fresh_shell_eggs", "version": "1.2.3"},
            "source_evidence": ["artifact://egg-evidence"],
            "labels": [
                {
                    "case_id": "case-certified",
                    "benchmark_listing_id": "walmart_us:one",
                    "competitor_listing_id": "kroger_us:one",
                    "expected_comparable": True,
                    "allowed_tiers": ["equivalent_product"],
                    "critical": True,
                    "stratum": "exact_specification",
                    "review_status": "single_reviewed",
                    "reviewers": ["reviewer@cpghero.com"],
                    "evidence_refs": ["artifact://egg-evidence"],
                    "rationale": "The governed package attributes agree.",
                }
            ],
            "exclusions": [
                {
                    "case_id": "case-insufficient",
                    "benchmark_listing_id": "walmart_us:two",
                    "competitor_listing_id": "kroger_us:two",
                    "reason": "insufficient_evidence",
                    "critical": False,
                    "stratum": "edge_case",
                    "review_status": "single_reviewed",
                    "reviewers": ["reviewer@cpghero.com"],
                    "evidence_refs": ["artifact://egg-evidence"],
                    "rationale": "Housing evidence remains unknown for one product.",
                }
            ],
        },
        label="release gold set with reviewed exclusion",
    )


def test_certification_coverage_preserves_each_retailer_funnel() -> None:
    coverage = _matching_v2_certification_coverage(
        [
            {"case_id": "aldi-comparable", "expected_comparable": True},
            {"case_id": "aldi-rejected", "expected_comparable": False},
            {"case_id": "target-comparable", "expected_comparable": True},
        ],
        [
            {"case_id": "aldi-comparable", "competitor_retailer_id": "aldi_us"},
            {"case_id": "aldi-rejected", "competitor_retailer_id": "aldi_us"},
            {"case_id": "aldi-unresolved", "competitor_retailer_id": "aldi_us"},
            {"case_id": "target-comparable", "competitor_retailer_id": "target_us"},
        ],
    )

    assert coverage["queue_case_count"] == 4
    assert coverage["source_candidate_count"] == 4
    assert coverage["selected_candidate_count"] == 4
    assert coverage["selection_complete"] is True
    assert coverage["selection_coverage_rate"] == 1.0
    assert coverage["certified_label_count"] == 3
    assert coverage["certified_comparable_count"] == 2
    assert coverage["unresolved_excluded_count"] == 1
    assert coverage["reviewed_insufficient_evidence_count"] == 0
    assert coverage["pending_unreviewed_count"] == 1
    assert coverage["retailers"] == [
        {
            "competitor_retailer_id": "aldi_us",
            "candidate_count": 3,
            "certified_count": 2,
            "certified_comparable_count": 1,
            "certified_not_comparable_count": 1,
            "reviewed_insufficient_evidence_count": 0,
            "pending_unreviewed_count": 1,
            "unresolved_count": 1,
        },
        {
            "competitor_retailer_id": "target_us",
            "candidate_count": 1,
            "certified_count": 1,
            "certified_comparable_count": 1,
            "certified_not_comparable_count": 0,
            "reviewed_insufficient_evidence_count": 0,
            "pending_unreviewed_count": 0,
            "unresolved_count": 0,
        },
    ]


def test_certification_coverage_distinguishes_final_insufficient_from_pending() -> None:
    coverage = _matching_v2_certification_coverage(
        [{"case_id": "certified", "expected_comparable": True}],
        [
            {
                "case_id": "certified",
                "competitor_retailer_id": "kroger_us",
                "final_verdict": "comparable",
            },
            {
                "case_id": "insufficient",
                "competitor_retailer_id": "kroger_us",
                "final_verdict": "insufficient_evidence",
            },
        ],
    )

    assert coverage["unresolved_excluded_count"] == 1
    assert coverage["reviewed_insufficient_evidence_count"] == 1
    assert coverage["pending_unreviewed_count"] == 0
    assert coverage["retailers"][0]["reviewed_insufficient_evidence_count"] == 1
    assert coverage["retailers"][0]["pending_unreviewed_count"] == 0


def test_certification_coverage_rejects_labels_outside_the_queue() -> None:
    with pytest.raises(ValueError, match="absent from its queue"):
        _matching_v2_certification_coverage(
            [{"case_id": "unknown", "expected_comparable": True}],
            [{"case_id": "known", "competitor_retailer_id": "aldi_us"}],
        )


def test_certification_coverage_exposes_sampled_queue_as_incomplete() -> None:
    coverage = _matching_v2_certification_coverage(
        [{"case_id": "selected", "expected_comparable": True}],
        [{"case_id": "selected", "competitor_retailer_id": "aldi_us"}],
        sampling={
            "available_counts": {"aldi_us:candidate": 10},
            "selected_counts": {"aldi_us:candidate": 1},
        },
    )

    assert coverage["source_candidate_count"] == 10
    assert coverage["selected_candidate_count"] == 1
    assert coverage["selection_complete"] is False
    assert coverage["selection_coverage_rate"] == 0.1


class ReviewRepository:
    def __init__(self) -> None:
        self.imported: dict[str, Any] | None = None
        self.submissions: list[dict[str, Any]] = []
        self.adjudications: list[dict[str, Any]] = []
        self.ai_drafts: list[dict[str, Any]] = []
        self.ai_retries: list[dict[str, Any]] = []
        self.bulk_commits: list[dict[str, Any]] = []
        self.replays: list[dict[str, Any]] = []

    async def list_queues(self, *, limit: int) -> list[dict[str, Any]]:
        assert limit > 0
        return []

    async def import_queue(
        self,
        organization_id: str,
        queue: Mapping[str, Any],
        *,
        imported_by: str,
        successor_of_version: str | None = None,
        carry_forward_certified: bool = False,
        scope_only_pack_revision: bool = False,
    ) -> dict[str, Any]:
        self.imported = {
            "organization_id": organization_id,
            "queue": dict(queue),
            "imported_by": imported_by,
            "successor_of_version": successor_of_version,
            "carry_forward_certified": carry_forward_certified,
            "scope_only_pack_revision": scope_only_pack_revision,
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

    async def eligible_ai_review_cases(
        self,
        external_queue_id: str,
        *,
        competitor_retailer_id: str | None,
        limit: int,
    ) -> dict[str, Any]:
        case_ids = [f"case-{index}" for index in range(30)][:limit]
        return {
            "queue_id": external_queue_id,
            "competitor_retailer_id": competitor_retailer_id,
            "eligible_case_count": 30,
            "selected_case_count": len(case_ids),
            "deferred_case_count": 30 - len(case_ids),
            "case_ids": case_ids,
        }

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
            "certified_case_ids": list(external_case_ids),
            "certified_case_count": len(external_case_ids),
            "comparable_case_count": len(external_case_ids),
            "not_comparable_case_count": 0,
            "approved_case_ids": list(external_case_ids),
            "reviewer_id": reviewer_id,
            "confirmation_checksum": confirmation_checksum,
        }
        self.bulk_commits.append(result)
        return result

    async def create_gold_set_replay(
        self,
        external_queue_id: str,
        gold_set: Mapping[str, Any],
        **values: Any,
    ) -> dict[str, Any]:
        record = {"queue_id": external_queue_id, "gold_set": dict(gold_set), **values}
        self.replays.append(record)
        return {"analysis_run_id": "run-1", "analysis_status": "queued", **record}


async def test_gold_set_replay_binds_exact_certified_snapshot(monkeypatch: Any) -> None:
    repository = ReviewRepository()
    service = MatchingV2ReviewService(repository, REPOSITORY_ROOT)
    gold_set = {
        "gold_set_id": "egg-gold",
        "version": "1.2.0",
        "labels": [{"case_id": "case-1", "expected_comparable": True}],
    }

    async def current_gold_set(_queue_id: str) -> dict[str, Any]:
        return gold_set

    monkeypatch.setattr(service, "gold_set", current_gold_set)
    result = await service.create_gold_set_replay(
        "egg-queue",
        GoldSetReplayRequest(source_analysis_id="egg-analysis", released_by="owner"),
    )

    assert result["analysis_status"] == "queued"
    assert repository.replays[0]["gold_set"] == gold_set
    assert (
        repository.replays[0]["document_checksum"]
        == hashlib.sha256(_canonical(gold_set).encode()).hexdigest()
    )
    assert repository.replays[0]["force_rebuild"] is False
    assert repository.replays[0]["rebuild_reason"] is None

    await service.create_gold_set_replay(
        "egg-queue",
        GoldSetReplayRequest(
            source_analysis_id="egg-analysis",
            released_by="owner",
            force_rebuild=True,
            rebuild_reason="Regenerate current reporting projections after governed code change",
        ),
    )
    assert repository.replays[1]["force_rebuild"] is True
    assert repository.replays[1]["rebuild_reason"].startswith("Regenerate")


async def test_gold_set_preserves_final_insufficient_evidence_as_audited_exclusion(
    monkeypatch: Any,
) -> None:
    repository = ReviewRepository()
    service = MatchingV2ReviewService(repository, REPOSITORY_ROOT)
    certified_decision = {
        "id": "decision-certified",
        "source": "review_submission",
        "reviewer_id": "owner@cpghero.com",
        "verdict": "comparable",
        "allowed_tiers": ["equivalent_product"],
        "rationale": "Count, size, shell color, and housing method agree.",
        "evidence_refs": ["artifact://certified"],
        "submission_ids": [],
    }
    insufficient_decision = {
        "id": "decision-insufficient",
        "source": "review_submission",
        "reviewer_id": "owner@cpghero.com",
        "verdict": "insufficient_evidence",
        "allowed_tiers": [],
        "rationale": "Housing evidence remains unknown for one product.",
        "evidence_refs": ["artifact://insufficient"],
        "submission_ids": [],
    }
    view = {
        "queue": {
            "version": "4.0.0",
            "product_pack": {"id": "fresh_shell_eggs", "version": "1.2.3"},
        },
        "cases": [
            {
                "case_id": "case-certified",
                "benchmark_listing_id": "walmart_us:one",
                "competitor_listing_id": "kroger_us:one",
                "critical": True,
                "stratum": "exact_specification",
                "review_status": "approved",
                "certification_blockers": [],
                "evidence_refs": ["artifact://certified"],
                "review_submissions": [],
                "final_decision": certified_decision,
            },
            {
                "case_id": "case-insufficient",
                "benchmark_listing_id": "walmart_us:two",
                "competitor_listing_id": "kroger_us:two",
                "critical": False,
                "stratum": "edge_case",
                "review_status": "flagged",
                "certification_blockers": [],
                "evidence_refs": ["artifact://insufficient"],
                "review_submissions": [],
                "final_decision": insufficient_decision,
            },
        ],
    }

    async def queue_view(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return view

    monkeypatch.setattr(service, "queue_view", queue_view)
    gold_set = await service.gold_set("egg-queue")

    assert len(gold_set["labels"]) == 1
    assert gold_set["exclusions"] == [
        {
            "case_id": "case-insufficient",
            "benchmark_listing_id": "walmart_us:two",
            "competitor_listing_id": "kroger_us:two",
            "reason": "insufficient_evidence",
            "critical": False,
            "stratum": "edge_case",
            "review_status": "single_reviewed",
            "reviewers": ["owner@cpghero.com"],
            "evidence_refs": ["artifact://insufficient"],
            "rationale": "Housing evidence remains unknown for one product.",
        }
    ]
    assert gold_set["source_evidence"] == [
        "artifact://certified",
        "artifact://insufficient",
    ]

    without_exclusion = {**gold_set, "exclusions": []}
    assert (
        hashlib.sha256(_canonical(gold_set).encode()).hexdigest()
        != hashlib.sha256(_canonical(without_exclusion).encode()).hexdigest()
    )


def test_forced_gold_set_replay_requires_an_audit_reason() -> None:
    with pytest.raises(ValueError, match="requires a rebuild reason"):
        GoldSetReplayRequest(
            source_analysis_id="egg-analysis",
            released_by="owner",
            force_rebuild=True,
        )


def test_postgres_replay_reconciles_reviewed_exclusions_to_current_queue() -> None:
    source = inspect.getsource(PostgresMatchingV2ReviewRepository.create_gold_set_replay)

    assert "label_case_ids & exclusion_case_ids" in source
    assert "current_insufficient_case_ids" in source
    assert "exclusion_case_ids != current_insufficient_case_ids" in source


def test_postgres_forced_replay_generation_matches_collection_release_identity() -> None:
    source = inspect.getsource(PostgresMatchingV2ReviewRepository.create_gold_set_replay)

    assert "coalesce(max(replay_generation), 0) + 1" in source
    assert "WHERE collection_run_id = CAST(:collection_run_id AS uuid)" in source
    assert "AND product_pack_id = :product_pack_id" in source
    assert "AND product_pack_version = :product_pack_version" in source
    assert "AND match_revision_id IS NULL" in source
    assert "AND brand_revision_id IS NULL" in source
    assert "ON CONFLICT DO NOTHING" in source


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


async def test_review_service_passes_governed_successor_options() -> None:
    repository = ReviewRepository()
    service = MatchingV2ReviewService(repository, REPOSITORY_ROOT)

    await service.import_queue(
        ImportReviewQueueRequest(
            organization_id="00000000-0000-0000-0000-000000000001",
            imported_by="review-admin",
            queue=_queue(),
            successor_of_version="1.0.0",
            carry_forward_certified=True,
            scope_only_pack_revision=True,
        )
    )

    assert repository.imported is not None
    assert repository.imported["successor_of_version"] == "1.0.0"
    assert repository.imported["carry_forward_certified"] is True
    assert repository.imported["scope_only_pack_revision"] is True


def test_review_queue_successor_requires_explicit_predecessor() -> None:
    with pytest.raises(ValueError, match="successor_of_version"):
        ImportReviewQueueRequest(
            organization_id="00000000-0000-0000-0000-000000000001",
            imported_by="review-admin",
            queue=_queue(),
            carry_forward_certified=True,
        )


def test_scope_only_successor_requires_certified_carry_forward() -> None:
    with pytest.raises(ValueError, match="scope_only_pack_revision"):
        ImportReviewQueueRequest(
            organization_id="00000000-0000-0000-0000-000000000001",
            imported_by="review-admin",
            queue=_queue(),
            successor_of_version="1.0.0",
            scope_only_pack_revision=True,
        )


def test_successor_compatibility_ignores_only_additive_image_arrays() -> None:
    predecessor = {
        "case_id": "case-1",
        "benchmark_listing": {"title": "Milk", "image_url": "primary.jpg"},
        "competitor_listing": {"title": "Competitor milk", "image_url": "other.jpg"},
        "edge": {"proposal": "review"},
    }
    successor = {
        **predecessor,
        "benchmark_listing": {
            **predecessor["benchmark_listing"],
            "image_url": "nutrition.jpg",
            "image_urls": ["primary.jpg", "nutrition.jpg"],
        },
    }

    sanitize = PostgresMatchingV2ReviewRepository._without_additive_image_evidence

    assert sanitize(predecessor) == sanitize(successor)
    assert PostgresMatchingV2ReviewRepository._image_evidence_is_additive(predecessor, successor)
    changed = {**successor, "edge": {"proposal": "comparable"}}
    assert sanitize(predecessor) != sanitize(changed)
    replaced = {
        **successor,
        "benchmark_listing": {
            **successor["benchmark_listing"],
            "image_urls": ["nutrition.jpg"],
        },
    }
    assert not PostgresMatchingV2ReviewRepository._image_evidence_is_additive(predecessor, replaced)


def test_scope_only_pack_compatibility_requires_strictly_additive_exclusions() -> None:
    predecessor = {
        "id": "fresh_shell_eggs",
        "version": "1.0.0",
        "scope": {
            "target_terms": ["egg", "eggs"],
            "hard_exclusion_patterns": ["liquid egg"],
        },
        "matching_v2": {"policy_version": "2.0.0", "attribute_roles": {}},
        "attributes": [{"name": "count"}],
        "reporting": {
            "report_blueprint": {"id": "fresh_shell_eggs_leadership", "version": "1.0.0"}
        },
    }
    successor = json.loads(json.dumps(predecessor))
    successor["version"] = "1.0.1"
    successor["scope"]["hard_exclusion_patterns"].append("egg salad")
    successor["reporting"]["report_blueprint"]["version"] = "1.0.1"

    compatible = PostgresMatchingV2ReviewRepository._scope_only_pack_revision_is_compatible

    assert compatible(predecessor, successor)
    changed_policy = json.loads(json.dumps(successor))
    changed_policy["matching_v2"]["policy_version"] = "2.0.1"
    assert not compatible(predecessor, changed_policy)
    removed_exclusion = json.loads(json.dumps(successor))
    removed_exclusion["scope"]["hard_exclusion_patterns"] = ["egg salad"]
    assert not compatible(predecessor, removed_exclusion)


def test_scope_only_case_compatibility_ignores_only_revision_derived_ids() -> None:
    predecessor = {
        "case_id": "case-old",
        "benchmark_listing_id": "walmart_us:1",
        "competitor_listing_id": "aldi_us:2",
        "benchmark_listing": {"title": "Large Eggs", "image_url": "one.jpg"},
        "competitor_listing": {"title": "Large Eggs", "image_url": "two.jpg"},
        "engine_proposal": {"edge_id": "edge-old", "tier": "equivalent_product"},
        "evidence_refs": ["source-bundle:aldi#sha256=abc|edge_id=edge-old"],
        "edge": {
            "edge_id": "edge-old",
            "policy": {
                "checksum": "a" * 64,
                "product_pack_version": "1.0.0",
                "policy_version": "2.0.0",
            },
            "attribute_evidence": [{"attribute": "count", "status": "matched"}],
        },
    }
    successor = json.loads(json.dumps(predecessor))
    successor["case_id"] = "case-new"
    successor["engine_proposal"]["edge_id"] = "edge-new"
    successor["evidence_refs"] = ["source-bundle:aldi#sha256=abc|edge_id=edge-new"]
    successor["edge"]["edge_id"] = "edge-new"
    successor["edge"]["policy"]["checksum"] = "b" * 64
    successor["edge"]["policy"]["product_pack_version"] = "1.0.1"

    sanitize = PostgresMatchingV2ReviewRepository._without_scope_revision_metadata

    assert sanitize(predecessor) == sanitize(successor)
    successor["edge"]["attribute_evidence"][0]["status"] = "conflicting"
    assert sanitize(predecessor) != sanitize(successor)


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
                "benchmark_product_id": "w-1",
                "competitor_product_id": "a-1",
                "review_status": "pending",
                "limit": 20,
            },
        )

    assert response.status_code == 200
    assert response.json()["authoritative"] is False
    assert response.json()["filters"]["competitor_retailer_id"] == "aldi_us"
    assert response.json()["filters"]["benchmark_product_id"] == "w-1"
    assert response.json()["filters"]["competitor_product_id"] == "a-1"


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


def test_ai_review_batch_supports_active_release_queue_scale() -> None:
    request = AIReviewBatchRequest(
        requested_by="reviewer-a",
        case_ids=[f"case-{index}" for index in range(1_217)],
    )

    assert len(request.case_ids) == 1_217
    with pytest.raises(ValueError):
        AIReviewBatchRequest(
            requested_by="reviewer-a",
            case_ids=[f"case-{index}" for index in range(1_501)],
        )


async def test_ai_review_eligible_scope_is_queue_wide_and_retailer_scoped() -> None:
    repository = ReviewRepository()
    service = MatchingV2ReviewService(repository, REPOSITORY_ROOT)

    result = await service.eligible_ai_review_cases(
        "queue-1",
        competitor_retailer_id="aldi_us",
    )

    assert result["competitor_retailer_id"] == "aldi_us"
    assert result["eligible_case_count"] == 30
    assert result["selected_case_count"] == 30
    assert result["deferred_case_count"] == 0
    assert result["case_ids"][0] == "case-0"


def test_postgres_ai_review_scope_excludes_finalized_existing_drafts_and_third_party() -> None:
    source = inspect.getsource(PostgresMatchingV2ReviewRepository.eligible_ai_review_cases)

    assert "NOT IN ('comparable', 'not_comparable')" in source
    assert "matching_v2_ai_review_task" in source
    assert "_case_has_known_third_party_seller" in source
    assert "documents.sort(key=_case_order_key)" in source
    request_source = inspect.getsource(PostgresMatchingV2ReviewRepository.request_ai_drafts)
    assert '"case_document": sidecar_documents[case_id]' in request_source
    assert "nonzero Search-derived observed-location evidence" in request_source


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
    assert "_active_certification_policy" in source
    assert "certification_policy=certification_policy" in source


def test_all_comparable_certification_paths_apply_current_product_pack_hard_blockers() -> None:
    submit_source = inspect.getsource(PostgresMatchingV2ReviewRepository.submit_review)
    adjudicate_source = inspect.getsource(PostgresMatchingV2ReviewRepository.adjudicate)
    bulk_source = inspect.getsource(PostgresMatchingV2ReviewRepository._bulk_ai_snapshot)
    gold_source = inspect.getsource(MatchingV2ReviewService.gold_set)

    assert "_active_certification_policy" in submit_source
    assert 'submission["verdict"] == "comparable"' in submit_source
    assert "_disallowed_certification_tiers" in submit_source
    assert "_active_certification_policy" in adjudicate_source
    assert 'adjudication["verdict"] == "comparable"' in adjudicate_source
    assert "_disallowed_certification_tiers" in adjudicate_source
    assert "_apply_active_certification_policy" in bulk_source
    assert 'case["review_status"] == "approved"' in gold_source
    assert '"certification_release_blocked"' in gold_source


def test_current_milk_policy_upgrades_legacy_volume_evidence_to_hard_blocker() -> None:
    legacy = _queue()["cases"][0]
    legacy["edge"]["attribute_evidence"].append(
        {
            "attribute": "volume_oz",
            "role": "soft_comparator",
            "benchmark_value": 128,
            "competitor_value": 64,
            "outcome": "conflict",
            "benchmark_source": "pdp:walmart_us:w1",
            "competitor_source": "pdp:aldi_us:a1",
            "weight": 5,
            "reliability": 0.95,
            "rationale": None,
        }
    )

    policy = _active_certification_policy("fresh_fluid_milk")
    governed = _apply_active_certification_policy(legacy, policy)
    volume = next(
        row for row in governed["edge"]["attribute_evidence"] if row["attribute"] == "volume_oz"
    )

    assert policy["product_pack_version"] == "1.6.0"
    assert volume["queue_role"] == "soft_comparator"
    assert volume["role"] == "hard_blocker"
    assert any(
        issue["attribute"] == "volume_oz" and issue["outcome"] == "conflict"
        for issue in governed["certification_blockers"]
    )


def test_current_egg_policy_tolerates_unknown_organic_but_blocks_color_conflict() -> None:
    case = _queue()["cases"][0]
    case["edge"]["attribute_evidence"] = [
        {
            "attribute": "size",
            "role": "hard_blocker",
            "benchmark_value": {"value": 12, "unit": "count"},
            "competitor_value": {"value": 12, "unit": "count"},
            "outcome": "match",
        },
        {
            "attribute": "housing",
            "role": "hard_blocker",
            "benchmark_value": "cage_free",
            "competitor_value": "cage_free",
            "outcome": "match",
        },
        {
            "attribute": "organic",
            "role": "hard_blocker",
            "benchmark_value": None,
            "competitor_value": None,
            "outcome": "unknown",
        },
        {
            "attribute": "shell_color",
            "role": "soft_comparator",
            "benchmark_value": "White",
            "competitor_value": "Brown",
            "outcome": "conflict",
        },
    ]

    policy = _active_certification_policy("fresh_shell_eggs")
    governed = _apply_active_certification_policy(case, policy)

    assert policy["product_pack_version"] == "1.2.3"
    assert policy["hard_blocker_unknown_is_blocking"]["organic"] is False
    assert governed["certification_unknown_nonblocking_attributes"] == ["organic"]
    assert [issue["attribute"] for issue in governed["certification_blockers"]] == ["shell_color"]
    shell_color = next(
        row for row in governed["edge"]["attribute_evidence"] if row["attribute"] == "shell_color"
    )
    assert shell_color["queue_role"] == "soft_comparator"
    assert shell_color["role"] == "hard_blocker"


def test_current_vitamin_policy_blocks_audience_ingredient_and_broad_substitute_tier() -> None:
    case = _queue()["cases"][0]
    case["edge"]["attribute_evidence"] = [
        {
            "attribute": "active_ingredient",
            "role": "soft_comparator",
            "benchmark_value": "Multivitamin",
            "competitor_value": "Multivitamin",
            "outcome": "match",
        },
        {
            "attribute": "strength",
            "role": "hard_blocker",
            "benchmark_value": 1,
            "competitor_value": 1,
            "outcome": "match",
        },
        {
            "attribute": "strength_unit",
            "role": "hard_blocker",
            "benchmark_value": "mg",
            "competitor_value": "mg",
            "outcome": "match",
        },
        {
            "attribute": "dosage_form",
            "role": "hard_blocker",
            "benchmark_value": "Tablet",
            "competitor_value": "Tablet",
            "outcome": "match",
        },
        {
            "attribute": "release_profile",
            "role": "hard_blocker",
            "benchmark_value": "Standard",
            "competitor_value": "Standard",
            "outcome": "match",
        },
        {
            "attribute": "life_stage",
            "role": "soft_comparator",
            "benchmark_value": "Senior",
            "competitor_value": "Children",
            "outcome": "conflict",
        },
    ]
    case["review_status"] = "approved"
    case["final_decision"] = {
        "verdict": "comparable",
        "allowed_tiers": ["comparable_substitute"],
    }

    policy = _active_certification_policy("vitamins_supplements")
    governed = _apply_active_certification_policy(case, policy)

    assert policy["product_pack_version"] == "1.1.2"
    assert policy["allow_comparable_substitute"] is False
    assert "comparable_substitute" not in policy["allowed_tiers"]
    assert [issue["attribute"] for issue in governed["certification_blockers"]] == ["life_stage"]
    assert governed["certification_tier_blockers"] == ["comparable_substitute"]
    assert governed["certification_release_blocked"] is True


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


def _bulk_not_comparable_case() -> dict[str, Any]:
    case = _bulk_eligible_case()
    case["case_id"] = "case-not-comparable"
    case["case_checksum"] = "d" * 64
    case["ai_output_checksum"] = "e" * 64
    case["ai_draft"]["id"] = "ai-task-not-comparable"
    result = case["ai_draft"]["output_document"]["result"]
    result["verdict_proposal"] = "not_comparable"
    result["tier_proposal"] = None
    result["rationale"] = "The governed package facts contain a material conflict."
    case["engine_proposal"]["tier"] = None
    case["engine_proposal"]["status"] = "rejected"
    case["edge"]["attribute_evidence"].append(
        {
            "attribute": "dosage_form",
            "role": "hard_blocker",
            "benchmark_value": "Tablet",
            "competitor_value": "Capsule",
            "outcome": "conflict",
        }
    )
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


def test_bulk_ai_certification_accepts_not_comparable_but_not_insufficient_evidence() -> None:
    not_comparable = _bulk_not_comparable_case()

    accepted = _bulk_ai_certification_eligibility(not_comparable)

    assert accepted["eligible"] is True
    assert accepted["recommended_verdict"] == "not_comparable"
    assert accepted["recommended_tier"] is None
    assert accepted["reason_codes"] == []

    insufficient = _bulk_not_comparable_case()
    result = insufficient["ai_draft"]["output_document"]["result"]
    result["verdict_proposal"] = "insufficient_evidence"

    blocked = _bulk_ai_certification_eligibility(insufficient)

    assert blocked["eligible"] is False
    assert blocked["reason_codes"] == ["ai_verdict_not_certifiable"]


def test_bulk_ai_certification_blocks_ai_only_not_comparable_rejection() -> None:
    not_comparable = _bulk_not_comparable_case()
    not_comparable["edge"]["attribute_evidence"] = [
        evidence
        for evidence in not_comparable["edge"]["attribute_evidence"]
        if evidence.get("outcome") != "conflict"
    ]

    blocked = _bulk_ai_certification_eligibility(not_comparable)

    assert blocked["eligible"] is False
    assert blocked["reason_codes"] == ["not_comparable_conflict_unverified"]


def test_bulk_certification_blocks_cross_volume_comparable_but_allows_rejection() -> None:
    case = _bulk_eligible_case()
    case["edge"]["attribute_evidence"] = [
        {
            "attribute": "volume_oz",
            "role": "soft_comparator",
            "benchmark_value": 128,
            "competitor_value": 64,
            "outcome": "conflict",
        }
    ]
    governed = _apply_active_certification_policy(
        case,
        {
            "product_pack_id": "fresh_fluid_milk",
            "product_pack_version": "1.5.0",
            "attribute_roles": {"volume_oz": "hard_blocker"},
            "hard_blocker_attributes": ["volume_oz"],
            "policy_checksum": "f" * 64,
            "queue_evidence_is_immutable": True,
            "stricter_active_policy_wins": True,
        },
    )

    blocked = _bulk_ai_certification_eligibility(governed)

    assert blocked["eligible"] is False
    assert blocked["reason_codes"] == ["hard_blocker_conflict"]
    assert blocked["hard_blocker_issues"][0]["attribute"] == "volume_oz"

    result = governed["ai_draft"]["output_document"]["result"]
    result["verdict_proposal"] = "not_comparable"
    result["tier_proposal"] = None
    governed["engine_proposal"]["tier"] = None
    governed["engine_proposal"]["status"] = "rejected"

    accepted_rejection = _bulk_ai_certification_eligibility(governed)

    assert accepted_rejection["eligible"] is True
    assert "hard_blocker_conflict" not in accepted_rejection["reason_codes"]


def test_bulk_ai_certification_rejects_not_comparable_with_a_match_tier() -> None:
    invalid = _bulk_not_comparable_case()
    invalid["ai_draft"]["output_document"]["result"]["tier_proposal"] = "exact_specification"

    evaluation = _bulk_ai_certification_eligibility(invalid)

    assert evaluation["eligible"] is False
    assert evaluation["reason_codes"] == ["not_comparable_tier_present"]


def test_bulk_ai_certification_obeys_active_product_pack_tier_policy() -> None:
    case = _bulk_eligible_case()
    case["ai_draft"]["output_document"]["result"]["tier_proposal"] = "comparable_substitute"
    case["engine_proposal"]["tier"] = "comparable_substitute"
    case["certification_allowed_tiers"] = [
        "exact_item",
        "exact_specification",
        "equivalent_product",
        "custom_approved",
    ]

    evaluation = _bulk_ai_certification_eligibility(case)

    assert evaluation["eligible"] is False
    assert evaluation["reason_codes"] == ["tier_disallowed_by_product_pack"]


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


def test_bulk_ai_preview_binds_recommended_verdict_to_confirmation_checksum() -> None:
    comparable = _bulk_eligible_case()
    not_comparable = _bulk_not_comparable_case()
    not_comparable["case_id"] = comparable["case_id"]
    not_comparable["case_checksum"] = comparable["case_checksum"]
    not_comparable["ai_draft"]["id"] = comparable["ai_draft"]["id"]
    not_comparable["ai_output_checksum"] = comparable["ai_output_checksum"]

    comparable_preview = _bulk_preview_document(
        queue_id="queue-one",
        queue_version="1.0.0",
        snapshots=[comparable],
    )
    not_comparable_preview = _bulk_preview_document(
        queue_id="queue-one",
        queue_version="1.0.0",
        snapshots=[not_comparable],
    )

    assert (
        comparable_preview["confirmation_checksum"]
        != (not_comparable_preview["confirmation_checksum"])
    )


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
    assert committed["certified_case_ids"] == ["case-1", "case-2"]
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
    assert "'certify_ai_recommendations'" in source
    assert '"verdict": recommended_verdict' in source
    assert "else []" in source


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


async def test_ai_review_eligible_scope_route_is_lightweight_and_human_gated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = ReviewRepository()
    service = MatchingV2ReviewService(repository, REPOSITORY_ROOT)
    app = create_app()
    app.dependency_overrides[get_matching_v2_review_service] = lambda: service
    monkeypatch.setenv("MATCHING_V2_AI_REVIEW_ENABLED", "true")
    monkeypatch.setenv("OPENAI_MODEL_MATCHING_REVIEW", "gpt-5.6-terra")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/matching-v2/review-queues/queue-1/ai-drafts/eligible-cases",
            params={"competitor_retailer_id": "aldi_us"},
        )

    assert response.status_code == 200
    document = response.json()
    assert document["authoritative"] is False
    assert document["human_review_required"] is True
    assert document["competitor_retailer_id"] == "aldi_us"
    assert document["selected_case_count"] == 30
    assert document["policy"]["max_batch_cases"] == 1_500
    assert document["policy"]["queue_wide_selection"] is True


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
