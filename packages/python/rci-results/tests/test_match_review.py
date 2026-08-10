from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from rci_contracts import validate_instance
from rci_results.match_review import (
    InMemoryMatchReviewRepository,
    MatchDecisionCommand,
    MatchOneToOneConflictError,
    MatchReviewService,
    MatchRevisionConflictError,
)
from rci_results.models import AnalysisPublicationRecord, AnalysisRecord

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def _analysis() -> AnalysisRecord:
    return AnalysisRecord(
        id="00000000-0000-0000-0000-000000000501",
        analysis_run_id="00000000-0000-0000-0000-000000000401",
        analysis_id="fresh-ground-beef-example",
        collection_run_id="00000000-0000-0000-0000-000000000301",
        status="succeeded",
        product_pack_id="fresh_ground_beef",
        product_pack_version="1.0.0",
        schema_version="2.0.0",
        checksum="a" * 64,
        result={
            "benchmark_retailer": "walmart_us",
            "competitors": ["aldi_us"],
            "comparison_modes": [
                {
                    "profile_id": "strict",
                    "label": "Strict exact package",
                    "geography": "exact_zip",
                    "comparison_metric": "package_price",
                },
                {
                    "profile_id": "unit_price",
                    "label": "Price per pound",
                    "geography": "exact_zip",
                    "comparison_metric": "price_per_lb",
                },
                {
                    "profile_id": "radius",
                    "label": "Radius",
                    "geography": "radius",
                    "comparison_metric": "package_price",
                },
            ],
        },
        created_at=datetime.now(UTC),
    )


def _publication(analysis: AnalysisRecord) -> AnalysisPublicationRecord:
    return AnalysisPublicationRecord(
        id="00000000-0000-0000-0000-000000000601",
        analysis_result_id=analysis.id,
        analysis_id=analysis.analysis_id,
        version=1,
        status="ready_to_share",
        source_result_checksum=analysis.checksum,
        publication_checksum="b" * 64,
        result=analysis.result,
        presentation_context={
            "product_highlights": [
                {
                    "canonical_product_id": "walmart_us:w1",
                    "retailer": "walmart_us",
                    "name": "Walmart 93/7 Ground Beef",
                    "image_url": "https://example.test/w1.png",
                    "price": 5.47,
                },
                {
                    "canonical_product_id": "walmart_us:w2",
                    "retailer": "walmart_us",
                    "name": "Walmart 80/20 Ground Beef",
                    "price": 4.97,
                },
                {
                    "canonical_product_id": "aldi_us:a1",
                    "retailer": "aldi_us",
                    "name": "ALDI 93/7 Ground Beef",
                    "price": 5.29,
                },
                {
                    "canonical_product_id": "aldi_us:a2",
                    "retailer": "aldi_us",
                    "name": "ALDI 80/20 Ground Beef",
                    "price": 4.79,
                },
            ],
            "match_candidates": [
                {
                    "id": "automatic-w1-a1",
                    "profile_id": "strict",
                    "profile_label": "Strict exact package",
                    "comparison_metric": "package_price",
                    "match_basis": "exact_package",
                    "competitor": "aldi_us",
                    "benchmark_product_id": "w1",
                    "benchmark_product_name": "Walmart 93/7 Ground Beef",
                    "competitor_product_id": "a1",
                    "competitor_product_name": "ALDI 93/7 Ground Beef",
                    "matches": 120,
                    "geographies": 100,
                    "median_gap": -0.18,
                    "match_attributes": {"lean_pct": 93, "fat_pct": 7},
                    "match_rationale": "Product Pack attributes align on lean and fat",
                    "plain_insight": "ALDI is lower in the matched markets.",
                },
                {
                    "id": "automatic-w1-a1-unit",
                    "profile_id": "unit_price",
                    "profile_label": "Price per pound",
                    "comparison_metric": "price_per_lb",
                    "match_basis": "normalized_unit",
                    "competitor": "aldi_us",
                    "benchmark_product_id": "w1",
                    "benchmark_product_name": "Walmart 93/7 Ground Beef",
                    "competitor_product_id": "a1",
                    "competitor_product_name": "ALDI 93/7 Ground Beef",
                    "matches": 118,
                    "geographies": 98,
                    "median_gap": -0.08,
                    "match_attributes": {"lean_pct": 93, "fat_pct": 7},
                    "match_rationale": "Product Pack attributes align on lean and fat",
                    "plain_insight": "ALDI has a lower normalized unit price.",
                },
            ],
        },
        created_at=datetime.now(UTC),
    )


class FakeResults:
    def __init__(self) -> None:
        self.analysis = _analysis()
        self.publication = _publication(self.analysis)

    async def get(self, _identifier: str) -> AnalysisRecord:
        return self.analysis

    async def latest_publication(self, _identifier: str) -> AnalysisPublicationRecord:
        return self.publication


def _command(
    *,
    revision: int,
    benchmark: str = "w1",
    competitor: str = "a1",
    profile: str = "strict",
    decision: str = "confirmed",
    replace: bool = False,
) -> MatchDecisionCommand:
    return MatchDecisionCommand(
        expected_revision=revision,
        competitor_retailer_id="aldi_us",
        profile_id=profile,
        benchmark_product_id=benchmark,
        competitor_product_id=competitor,
        decision=decision,
        replace_conflicts=replace,
    )


async def test_match_review_overlays_durable_user_decisions() -> None:
    repository = InMemoryMatchReviewRepository()
    service = MatchReviewService(  # type: ignore[arg-type]
        FakeResults(), repository, retailer_names={"walmart_us": "Walmart", "aldi_us": "ALDI"}
    )

    initial = await service.view("fresh-ground-beef-example")
    validate_instance(
        REPOSITORY_ROOT,
        "product-match-review.schema.json",
        initial,
        label="match-review",
    )
    assert initial["revision"] == 0
    assert initial["future_application"] is None
    assert initial["summary"]["suggested"] == 1
    assert [row["id"] for row in initial["profiles"]] == ["strict", "unit_price"]
    assert initial["connections"][0]["eligible_profile_ids"] == ["strict", "unit_price"]
    assert len(initial["connections"][0]["profile_evidence"]) == 2

    saved = await service.decide(
        "fresh-ground-beef-example", _command(revision=0), actor="reviewer@example.test"
    )
    assert saved["revision"] == 1
    reviewed = await service.view("fresh-ground-beef-example")
    assert reviewed["summary"] == {
        "suggested": 0,
        "confirmed": 1,
        "rejected": 0,
        "unmatched": 2,
    }
    assert reviewed["connections"][0]["status"] == "confirmed"


async def test_match_review_is_optimistic_and_strictly_one_to_one() -> None:
    repository = InMemoryMatchReviewRepository()
    service = MatchReviewService(FakeResults(), repository)  # type: ignore[arg-type]
    await service.decide("analysis", _command(revision=0), actor="reviewer")

    with pytest.raises(MatchRevisionConflictError, match="current revision is 1"):
        await service.decide("analysis", _command(revision=0), actor="stale-reviewer")

    with pytest.raises(MatchOneToOneConflictError):
        await service.decide(
            "analysis",
            _command(revision=1, benchmark="w1", competitor="a2", profile="unit_price"),
            actor="reviewer",
        )

    await service.decide(
        "analysis",
        _command(
            revision=1,
            benchmark="w1",
            competitor="a2",
            profile="unit_price",
            replace=True,
        ),
        actor="reviewer",
    )
    reviewed = await service.view("analysis")
    confirmed = [row for row in reviewed["connections"] if row["status"] == "confirmed"]
    assert [(row["benchmark_product_id"], row["competitor_product_id"]) for row in confirmed] == [
        ("w1", "a2")
    ]


async def test_reanalysis_uses_latest_revision_without_provider_tasks() -> None:
    repository = InMemoryMatchReviewRepository()
    service = MatchReviewService(FakeResults(), repository)  # type: ignore[arg-type]
    await service.decide("analysis", _command(revision=0, decision="rejected"), actor="reviewer")

    staged = await service.view("analysis")
    assert staged["future_application"] is None

    queued = await service.recompute(
        "analysis",
        expected_revision=1,
        apply_to_future_runs=False,
        actor="reviewer",
    )

    assert queued.status == "queued"
    assert queued.source_analysis_id == "fresh-ground-beef-example"
    assert queued.match_revision_id
    assert queued.applied_to_future_runs is False
    assert (await service.view("analysis"))["future_application"] is None


async def test_reanalysis_only_updates_future_policy_after_explicit_confirmation() -> None:
    repository = InMemoryMatchReviewRepository()
    service = MatchReviewService(FakeResults(), repository)  # type: ignore[arg-type]
    await service.decide("analysis", _command(revision=0), actor="reviewer")

    queued = await service.recompute(
        "analysis",
        expected_revision=1,
        apply_to_future_runs=True,
        actor="reviewer",
    )

    assert queued.applied_to_future_runs is True
    view = await service.view("analysis")
    assert view["future_application"] == {
        "revision_id": queued.match_revision_id,
        "revision": 1,
    }
