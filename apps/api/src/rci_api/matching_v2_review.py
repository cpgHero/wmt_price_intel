"""Authenticated human certification API for Matching v2."""

from __future__ import annotations

import hashlib
import json
import math
import os
import secrets
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Annotated, Any, Literal, Protocol

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from rci_contracts import ContractError, validate_instance

router = APIRouter(prefix="/api/v1/matching-v2", tags=["matching-v2-review"])

MatchTier = Literal[
    "exact_item",
    "exact_specification",
    "equivalent_product",
    "comparable_substitute",
    "custom_approved",
]
ReviewVerdict = Literal["comparable", "not_comparable", "insufficient_evidence"]


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)


def _checksum(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _observed_location_count(case: Mapping[str, Any], side: str) -> int:
    listing = case.get(f"{side}_listing")
    if not isinstance(listing, Mapping):
        return 0
    value = listing.get("observed_location_count", 0)
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _case_order_key(case: Mapping[str, Any]) -> tuple[int, int, int, str, str]:
    """Rank the benchmark footprint first, then competitor reach and review risk."""

    return (
        -_observed_location_count(case, "benchmark"),
        -_observed_location_count(case, "competitor"),
        -int(bool(case.get("critical"))),
        str(case.get("stratum") or ""),
        str(case.get("case_id") or ""),
    )


def _apply_observed_location_sidecar(
    documents: Sequence[dict[str, Any]],
    *,
    queue_id: str,
    queue_version: str,
    root: Path,
) -> None:
    """Complete legacy read views without mutating immutable review evidence."""

    catalog_path = root / "config" / "matching-v2-review-footprints.json"
    if not catalog_path.is_file():
        return
    try:
        catalog = json.loads(catalog_path.read_text())
    except (OSError, json.JSONDecodeError):
        return
    queues = catalog.get("queues") if isinstance(catalog, Mapping) else None
    if not isinstance(queues, list):
        return
    matching_queue = next(
        (
            item
            for item in queues
            if isinstance(item, Mapping)
            and item.get("queue_id") == queue_id
            and item.get("queue_version") == queue_version
        ),
        None,
    )
    counts_by_case = matching_queue.get("cases") if isinstance(matching_queue, Mapping) else None
    listings_by_id = matching_queue.get("listings") if isinstance(matching_queue, Mapping) else None
    if not isinstance(counts_by_case, Mapping):
        counts_by_case = {}
    if not isinstance(listings_by_id, Mapping):
        listings_by_id = {}
    for document in documents:
        counts = counts_by_case.get(document.get("case_id"))
        if not isinstance(counts, Mapping):
            counts = {}
        for side in ("benchmark", "competitor"):
            listing = document.get(f"{side}_listing")
            if not isinstance(listing, dict):
                continue
            listing_id = str(
                listing.get("listing_id")
                or document.get(f"{side}_listing_id")
                or (
                    f"{listing.get('retailer_id')}:{listing.get('retailer_product_id')}"
                    if listing.get("retailer_id") and listing.get("retailer_product_id")
                    else ""
                )
                or ""
            )
            listing_evidence = listings_by_id.get(listing_id)
            if not isinstance(listing_evidence, Mapping):
                listing_evidence = {}
            count = counts.get(
                f"{side}_observed_location_count",
                listing_evidence.get("observed_location_count"),
            )
            if (
                "observed_location_count" not in listing
                and isinstance(count, int)
                and not isinstance(count, bool)
                and count >= 0
            ):
                listing["observed_location_count"] = count
            governance = listing.get("seller_governance")
            sidecar_governance = listing_evidence.get("seller_governance")
            if not isinstance(governance, Mapping) and isinstance(sidecar_governance, Mapping):
                listing["seller_governance"] = {
                    **dict(sidecar_governance),
                    "source": "reconciled_release_evidence",
                    "resolution_method": "legacy_queue_sidecar",
                }


def _enabled(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _repository_root() -> Path:
    return Path(os.getenv("RCI_REPOSITORY_ROOT", Path.cwd())).resolve()


class ImportReviewQueueRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    organization_id: str = Field(min_length=1)
    imported_by: str = Field(min_length=1, max_length=200)
    queue: dict[str, Any] | None = None
    queue_json: str | None = Field(default=None, min_length=2)


class ReviewSubmissionRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    reviewer_id: str = Field(min_length=1, max_length=200)
    verdict: ReviewVerdict
    allowed_tiers: list[MatchTier] = Field(default_factory=list)
    rationale: str = Field(min_length=1, max_length=10_000)
    evidence_refs: list[str] = Field(min_length=1)
    supersedes_submission_id: str | None = None


class AdjudicationRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    adjudicator_id: str = Field(min_length=1, max_length=200)
    verdict: ReviewVerdict
    allowed_tiers: list[MatchTier] = Field(default_factory=list)
    rationale: str = Field(min_length=1, max_length=10_000)
    evidence_refs: list[str] = Field(min_length=1)
    submission_ids: list[str] = Field(min_length=2)
    supersedes_adjudication_id: str | None = None


class AIReviewDraftRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    requested_by: str = Field(min_length=1, max_length=200)


class AIReviewBatchRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    requested_by: str = Field(min_length=1, max_length=200)
    case_ids: list[str] = Field(min_length=1, max_length=25)


class AIBulkCertificationPreviewRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    case_ids: list[str] = Field(min_length=1, max_length=50)


class AIBulkCertificationCommitRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    reviewer_id: str = Field(min_length=1, max_length=200)
    case_ids: list[str] = Field(min_length=1, max_length=50)
    confirmation_checksum: str = Field(pattern=r"^[a-f0-9]{64}$")


_AI_BULK_CERTIFICATION_POLICY: dict[str, Any] = {
    "id": "guarded_ai_match_bulk_accept",
    "version": "1.0.0",
    "max_cases": 50,
    "action": "approve_ai_matches",
    "allowed_tiers": [
        "exact_item",
        "exact_specification",
        "equivalent_product",
    ],
    "minimum_critical_coverage": 1.0,
    "minimum_ai_attribute_confidence": 0.85,
    "require_ai_engine_tier_agreement": True,
    "require_zero_ai_conflicts": True,
    "require_no_hard_blocker_conflicts": True,
    "require_no_known_third_party_seller": True,
    "final_decision": "final_until_flagged",
}


_AI_BULK_REASON_LABELS = {
    "final_decision_exists": "A final human decision already exists.",
    "ai_draft_not_ready": "The latest AI draft is not successfully completed.",
    "ai_draft_invalid": "The completed AI draft does not contain valid governed output.",
    "ai_not_comparable": "The AI recommendation is not an affirmative comparable match.",
    "tier_not_bulk_eligible": "The recommended tier requires individual review.",
    "engine_tier_missing": "The deterministic engine did not propose a match tier.",
    "ai_engine_tier_disagreement": "The AI and deterministic engine propose different tiers.",
    "engine_proposal_blocked": "The deterministic engine marked the pair ineligible or rejected.",
    "critical_evidence_incomplete": "Critical deterministic evidence is incomplete.",
    "ai_conflict_present": "The AI draft identifies one or more unresolved conflicts.",
    "hard_blocker_conflict": "A Product Pack hard-blocker attribute conflicts or is unresolved.",
    "low_confidence_ai_attribute": "An AI-proposed attribute is below the bulk confidence floor.",
    "known_third_party_seller": (
        "A known third-party marketplace seller makes the listing ineligible."
    ),
    "evidence_refs_missing": "The case has no immutable source-evidence references.",
}


def _known_third_party_seller(listing: Mapping[str, Any]) -> bool:
    governance = listing.get("seller_governance")
    if not isinstance(governance, Mapping):
        return False
    if governance.get("eligible") is False:
        return True
    status_value = (
        str(governance.get("status") or governance.get("eligibility") or "").strip().lower()
    )
    if not status_value:
        return False
    if "first_party" in status_value or "first-party" in status_value:
        return False
    return any(token in status_value for token in ("third_party", "third-party", "excluded"))


def _case_has_known_third_party_seller(case: Mapping[str, Any]) -> bool:
    return any(
        _known_third_party_seller(listing)
        for listing in (
            case.get("benchmark_listing"),
            case.get("competitor_listing"),
        )
        if isinstance(listing, Mapping)
    )


def _bulk_ai_certification_eligibility(case: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate a case under deterministic, server-owned bulk-certification guardrails."""

    reason_codes: list[str] = []
    if case.get("review_status") != "pending":
        reason_codes.append("final_decision_exists")

    ai_draft = case.get("ai_draft")
    if not isinstance(ai_draft, Mapping) or ai_draft.get("status") != "succeeded":
        reason_codes.append("ai_draft_not_ready")
        result: Mapping[str, Any] = {}
    else:
        output = ai_draft.get("output_document")
        candidate_result = output.get("result") if isinstance(output, Mapping) else None
        output_checksum = str(case.get("ai_output_checksum") or "")
        if (
            not isinstance(output, Mapping)
            or output.get("authoritative") is not False
            or output.get("human_review_required") is not True
            or not isinstance(candidate_result, Mapping)
            or candidate_result.get("requires_human_review") is not True
            or len(output_checksum) != 64
        ):
            reason_codes.append("ai_draft_invalid")
            result = {}
        else:
            result = candidate_result

    verdict = str(result.get("verdict_proposal") or "")
    ai_tier = str(result.get("tier_proposal") or "")
    if result and verdict != "comparable":
        reason_codes.append("ai_not_comparable")
    if result and ai_tier not in _AI_BULK_CERTIFICATION_POLICY["allowed_tiers"]:
        reason_codes.append("tier_not_bulk_eligible")

    engine = case.get("engine_proposal")
    engine = engine if isinstance(engine, Mapping) else {}
    engine_tier = str(engine.get("tier") or "")
    if not engine_tier:
        reason_codes.append("engine_tier_missing")
    elif ai_tier and ai_tier != engine_tier:
        reason_codes.append("ai_engine_tier_disagreement")
    engine_status = str(engine.get("status") or "").lower()
    if any(token in engine_status for token in ("reject", "block", "ineligible")):
        reason_codes.append("engine_proposal_blocked")

    coverage = engine.get("evidence_coverage")
    coverage = coverage if isinstance(coverage, Mapping) else {}
    try:
        critical_coverage = float(coverage.get("critical_coverage", 0))
    except (TypeError, ValueError):
        critical_coverage = 0.0
    if critical_coverage < _AI_BULK_CERTIFICATION_POLICY["minimum_critical_coverage"]:
        reason_codes.append("critical_evidence_incomplete")

    conflicts = result.get("conflicts", []) if result else []
    if isinstance(conflicts, list) and conflicts:
        reason_codes.append("ai_conflict_present")

    edge = case.get("edge")
    edge = edge if isinstance(edge, Mapping) else {}
    attribute_evidence = edge.get("attribute_evidence", [])
    if isinstance(attribute_evidence, list) and any(
        isinstance(evidence, Mapping)
        and str(evidence.get("role") or "") == "hard_blocker"
        and str(evidence.get("outcome") or "") != "match"
        for evidence in attribute_evidence
    ):
        reason_codes.append("hard_blocker_conflict")

    attribute_proposals = result.get("attribute_proposals", []) if result else []
    if isinstance(attribute_proposals, list):
        for proposal in attribute_proposals:
            if not isinstance(proposal, Mapping):
                reason_codes.append("low_confidence_ai_attribute")
                break
            try:
                confidence = float(proposal.get("confidence", 0))
            except (TypeError, ValueError):
                confidence = 0.0
            if confidence < _AI_BULK_CERTIFICATION_POLICY["minimum_ai_attribute_confidence"]:
                reason_codes.append("low_confidence_ai_attribute")
                break

    if any(
        _known_third_party_seller(listing)
        for listing in (
            case.get("benchmark_listing"),
            case.get("competitor_listing"),
        )
        if isinstance(listing, Mapping)
    ):
        reason_codes.append("known_third_party_seller")
    if not case.get("evidence_refs"):
        reason_codes.append("evidence_refs_missing")

    reason_codes = list(dict.fromkeys(reason_codes))
    return {
        "case_id": str(case.get("case_id") or ""),
        "eligible": not reason_codes,
        "reason_codes": reason_codes,
        "reasons": [_AI_BULK_REASON_LABELS[code] for code in reason_codes],
        "recommended_tier": ai_tier or None,
        "critical_coverage": critical_coverage,
        "engine_status": engine_status or None,
        "ai_task_id": (str(ai_draft.get("id")) if isinstance(ai_draft, Mapping) else None),
        "ai_rationale": str(result.get("rationale") or "") or None,
        "benchmark_product": _bulk_product_summary(case.get("benchmark_listing")),
        "competitor_product": _bulk_product_summary(case.get("competitor_listing")),
    }


def _bulk_product_summary(value: Any) -> dict[str, Any]:
    listing = value if isinstance(value, Mapping) else {}
    return {
        "retailer_id": listing.get("retailer_id"),
        "retailer_product_id": listing.get("retailer_product_id"),
        "title": listing.get("title"),
        "brand": listing.get("brand"),
        "image_url": listing.get("image_url"),
        "observed_location_count": _observed_location_count({"listing": listing}, "listing"),
    }


def _ai_bulk_certification_policy() -> dict[str, Any]:
    return {
        **_AI_BULK_CERTIFICATION_POLICY,
        "checksum": _checksum(_AI_BULK_CERTIFICATION_POLICY),
        "human_confirmation_required": True,
        "automatically_changes_reporting": False,
    }


def _bulk_confirmation_checksum(
    *,
    queue_id: str,
    queue_version: str,
    candidates: Sequence[Mapping[str, Any]],
) -> str:
    policy = _ai_bulk_certification_policy()
    return _checksum(
        {
            "queue_id": queue_id,
            "queue_version": queue_version,
            "policy_checksum": policy["checksum"],
            "cases": [
                {
                    "case_id": candidate["case_id"],
                    "case_checksum": candidate["case_checksum"],
                    "ai_task_id": candidate["ai_task_id"],
                    "ai_output_checksum": candidate["ai_output_checksum"],
                    "recommended_tier": candidate["recommended_tier"],
                }
                for candidate in sorted(candidates, key=lambda row: str(row["case_id"]))
            ],
        }
    )


def _bulk_preview_document(
    *,
    queue_id: str,
    queue_version: str,
    snapshots: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    evaluated: list[dict[str, Any]] = []
    for snapshot in snapshots:
        candidate = _bulk_ai_certification_eligibility(snapshot)
        candidate["case_checksum"] = str(snapshot.get("case_checksum") or "")
        candidate["ai_output_checksum"] = str(snapshot.get("ai_output_checksum") or "")
        evaluated.append(candidate)
    eligible = [candidate for candidate in evaluated if candidate["eligible"]]
    excluded = [candidate for candidate in evaluated if not candidate["eligible"]]
    reason_counts: dict[str, int] = defaultdict(int)
    for candidate in excluded:
        for reason_code in candidate["reason_codes"]:
            reason_counts[reason_code] += 1
    return {
        "schema_version": "1.0.0-ai-bulk-certification-preview",
        "queue_id": queue_id,
        "queue_version": queue_version,
        "policy": _ai_bulk_certification_policy(),
        "requested_case_count": len(evaluated),
        "eligible_case_count": len(eligible),
        "excluded_case_count": len(excluded),
        "eligible_cases": eligible,
        "excluded_cases": excluded,
        "exclusion_summary": [
            {
                "reason_code": reason_code,
                "reason": _AI_BULK_REASON_LABELS[reason_code],
                "case_count": count,
            }
            for reason_code, count in sorted(reason_counts.items())
        ],
        "confirmation_checksum": (
            _bulk_confirmation_checksum(
                queue_id=queue_id,
                queue_version=queue_version,
                candidates=eligible,
            )
            if eligible
            else None
        ),
        "human_confirmation_required": True,
        "final_until_flagged": True,
        "automatically_changes_reporting": False,
    }


class MatchingV2ReviewRepository(Protocol):
    async def list_queues(self, *, limit: int) -> list[dict[str, Any]]: ...

    async def import_queue(
        self,
        organization_id: str,
        queue: Mapping[str, Any],
        *,
        imported_by: str,
    ) -> dict[str, Any]: ...

    async def queue_view(
        self,
        external_queue_id: str,
        *,
        competitor_retailer_id: str | None,
        stratum: str | None,
        review_status: str | None,
        offset: int,
        limit: int,
    ) -> dict[str, Any]: ...

    async def submit_review(
        self,
        external_queue_id: str,
        external_case_id: str,
        submission: Mapping[str, Any],
        *,
        submission_checksum: str,
    ) -> dict[str, Any]: ...

    async def adjudicate(
        self,
        external_queue_id: str,
        external_case_id: str,
        adjudication: Mapping[str, Any],
        *,
        adjudication_checksum: str,
    ) -> dict[str, Any]: ...

    async def request_ai_draft(
        self,
        external_queue_id: str,
        external_case_id: str,
        *,
        requested_by: str,
        model_id: str,
        prompt: Mapping[str, str],
    ) -> dict[str, Any]: ...

    async def request_ai_drafts(
        self,
        external_queue_id: str,
        external_case_ids: Sequence[str],
        *,
        requested_by: str,
        model_id: str,
        prompt: Mapping[str, str],
    ) -> list[dict[str, Any]]: ...

    async def preview_ai_bulk_certification(
        self,
        external_queue_id: str,
        external_case_ids: Sequence[str],
    ) -> dict[str, Any]: ...

    async def commit_ai_bulk_certification(
        self,
        external_queue_id: str,
        external_case_ids: Sequence[str],
        *,
        reviewer_id: str,
        confirmation_checksum: str,
    ) -> dict[str, Any]: ...


class PostgresMatchingV2ReviewRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def list_queues(self, *, limit: int) -> list[dict[str, Any]]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        SELECT q.external_queue_id, q.version, q.product_pack_id,
                               q.product_pack_version, q.policy_checksum,
                               q.document_checksum, q.imported_by, q.created_at,
                               count(DISTINCT c.id) AS case_count,
                               count(DISTINCT s.review_case_id)
                                 FILTER (WHERE s.review_case_id IS NOT NULL) AS reviewed_case_count,
                               count(DISTINCT a.review_case_id)
                                 FILTER (WHERE a.review_case_id IS NOT NULL)
                                 AS adjudicated_case_count
                        FROM matching_v2_review_queue q
                        LEFT JOIN matching_v2_review_case c ON c.review_queue_id = q.id
                        LEFT JOIN matching_v2_review_submission s ON s.review_case_id = c.id
                        LEFT JOIN matching_v2_adjudication a ON a.review_case_id = c.id
                        GROUP BY q.id
                        ORDER BY q.created_at DESC
                        LIMIT :limit
                        """
                    ),
                    {"limit": limit},
                )
            ).mappings()
            return [
                {
                    "queue_id": row["external_queue_id"],
                    "version": row["version"],
                    "product_pack": {
                        "id": row["product_pack_id"],
                        "version": row["product_pack_version"],
                    },
                    "policy_checksum": row["policy_checksum"],
                    "checksum": row["document_checksum"],
                    "imported_by": row["imported_by"],
                    "created_at": row["created_at"].isoformat(),
                    "case_count": int(row["case_count"]),
                    "reviewed_case_count": int(row["reviewed_case_count"]),
                    "adjudicated_case_count": int(row["adjudicated_case_count"]),
                }
                for row in rows
            ]

    async def import_queue(
        self,
        organization_id: str,
        queue: Mapping[str, Any],
        *,
        imported_by: str,
    ) -> dict[str, Any]:
        async with self._engine.begin() as connection:
            existing = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT id::text, document_checksum
                        FROM matching_v2_review_queue
                        WHERE organization_id = CAST(:organization_id AS uuid)
                          AND external_queue_id = :queue_id
                          AND version = :version
                        """
                        ),
                        {
                            "organization_id": organization_id,
                            "queue_id": queue["queue_id"],
                            "version": queue["version"],
                        },
                    )
                )
                .mappings()
                .first()
            )
            if existing is not None:
                if str(existing["document_checksum"]) != str(queue["checksum"]):
                    raise ValueError("queue ID/version already exists with a different checksum")
                return {
                    "id": str(existing["id"]),
                    "queue_id": queue["queue_id"],
                    "version": queue["version"],
                    "checksum": queue["checksum"],
                    "imported": False,
                    "case_count": len(queue["cases"]),
                }
            row = (
                (
                    await connection.execute(
                        text(
                            """
                        INSERT INTO matching_v2_review_queue (
                          organization_id, external_queue_id, version,
                          product_pack_id, product_pack_version, policy_checksum,
                          source_evidence, sampling, document, document_checksum, imported_by
                        ) VALUES (
                          CAST(:organization_id AS uuid), :queue_id, :version,
                          :product_pack_id, :product_pack_version, :policy_checksum,
                          CAST(:source_evidence AS jsonb), CAST(:sampling AS jsonb),
                          CAST(:document AS jsonb), :document_checksum, :imported_by
                        )
                        RETURNING id::text
                        """
                        ),
                        {
                            "organization_id": organization_id,
                            "queue_id": queue["queue_id"],
                            "version": queue["version"],
                            "product_pack_id": queue["product_pack"]["id"],
                            "product_pack_version": queue["product_pack"]["version"],
                            "policy_checksum": queue["policy_checksum"],
                            "source_evidence": _canonical(queue["source_evidence"]),
                            "sampling": _canonical(queue["sampling"]),
                            "document": _canonical(queue),
                            "document_checksum": queue["checksum"],
                            "imported_by": imported_by,
                        },
                    )
                )
                .mappings()
                .one()
            )
            review_queue_id = str(row["id"])
            for case in queue["cases"]:
                await self._insert_case(connection, review_queue_id, case)
        return {
            "id": review_queue_id,
            "queue_id": queue["queue_id"],
            "version": queue["version"],
            "checksum": queue["checksum"],
            "imported": True,
            "case_count": len(queue["cases"]),
        }

    @staticmethod
    async def _insert_case(
        connection: AsyncConnection,
        review_queue_id: str,
        case: Mapping[str, Any],
    ) -> None:
        await connection.execute(
            text(
                """
                INSERT INTO matching_v2_review_case (
                  review_queue_id, external_case_id, benchmark_listing_id,
                  competitor_listing_id, competitor_retailer_id, stratum,
                  critical, case_document, case_checksum
                ) VALUES (
                  CAST(:review_queue_id AS uuid), :external_case_id, :benchmark_listing_id,
                  :competitor_listing_id, :competitor_retailer_id, :stratum,
                  :critical, CAST(:case_document AS jsonb), :case_checksum
                )
                """
            ),
            {
                "review_queue_id": review_queue_id,
                "external_case_id": case["case_id"],
                "benchmark_listing_id": case["benchmark_listing_id"],
                "competitor_listing_id": case["competitor_listing_id"],
                "competitor_retailer_id": case["competitor_retailer_id"],
                "stratum": case["stratum"],
                "critical": case["critical"],
                "case_document": _canonical(case),
                "case_checksum": _checksum(case),
            },
        )

    async def queue_view(
        self,
        external_queue_id: str,
        *,
        competitor_retailer_id: str | None,
        stratum: str | None,
        review_status: str | None,
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        async with self._engine.connect() as connection:
            queue = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT id::text, external_queue_id, version, product_pack_id,
                               product_pack_version, policy_checksum, document_checksum,
                               imported_by, created_at
                        FROM matching_v2_review_queue
                        WHERE external_queue_id = :queue_id
                        ORDER BY created_at DESC
                        LIMIT 1
                        """
                        ),
                        {"queue_id": external_queue_id},
                    )
                )
                .mappings()
                .first()
            )
            if queue is None:
                raise KeyError(f"matching v2 review queue {external_queue_id!r} was not found")
            cases = await self._case_rows(
                connection,
                str(queue["id"]),
                competitor_retailer_id=competitor_retailer_id,
                stratum=stratum,
            )
            case_ids = [str(case["id"]) for case in cases]
            submissions = await self._submission_rows(connection, case_ids)
            adjudications = await self._adjudication_rows(connection, case_ids)
            ai_drafts = await self._ai_draft_rows(connection, case_ids)
            ai_review_summary = await self._ai_review_summary(connection, str(queue["id"]))
        documents = self._case_documents(cases, submissions, adjudications, ai_drafts)
        _apply_observed_location_sidecar(
            documents,
            queue_id=external_queue_id,
            queue_version=str(queue["version"]),
            root=_repository_root(),
        )
        documents = [
            document for document in documents if not _case_has_known_third_party_seller(document)
        ]
        documents.sort(key=_case_order_key)
        competitor_counts: dict[str, int] = defaultdict(int)
        for document in documents:
            retailer_id = str(document.get("competitor_retailer_id") or "")
            if retailer_id:
                competitor_counts[retailer_id] += 1
        competitor_retailers = [
            {"retailer_id": retailer_id, "case_count": case_count}
            for retailer_id, case_count in sorted(competitor_counts.items())
        ]
        summary_counts: dict[str, int] = defaultdict(int)
        for row in documents:
            summary_counts[str(row["review_status"])] += 1
        total_cases = len(documents)
        if review_status is not None:
            documents = [row for row in documents if row["review_status"] == review_status]
        return {
            "schema_version": "2.0.0-review-view",
            "authoritative": False,
            "queue": {
                "id": str(queue["id"]),
                "queue_id": queue["external_queue_id"],
                "version": queue["version"],
                "product_pack": {
                    "id": queue["product_pack_id"],
                    "version": queue["product_pack_version"],
                },
                "policy_checksum": queue["policy_checksum"],
                "checksum": queue["document_checksum"],
                "imported_by": queue["imported_by"],
                "created_at": queue["created_at"].isoformat(),
            },
            "filters": {
                "competitor_retailer_id": competitor_retailer_id,
                "stratum": stratum,
                "review_status": review_status,
            },
            "competitor_retailers": competitor_retailers,
            "ai_review_summary": ai_review_summary,
            "status_counts": dict(sorted(summary_counts.items())),
            "total_cases": total_cases,
            "selected_case_count": len(documents),
            "offset": offset,
            "limit": limit,
            "cases": documents[offset : offset + limit],
        }

    @staticmethod
    async def _competitor_retailers(
        connection: AsyncConnection,
        review_queue_id: str,
        *,
        stratum: str | None,
    ) -> list[dict[str, Any]]:
        rows = (
            await connection.execute(
                text(
                    """
                    SELECT competitor_retailer_id, count(*) AS case_count
                    FROM matching_v2_review_case
                    WHERE review_queue_id = CAST(:review_queue_id AS uuid)
                      AND (CAST(:stratum AS text) IS NULL
                           OR stratum = CAST(:stratum AS text))
                    GROUP BY competitor_retailer_id
                    ORDER BY competitor_retailer_id
                    """
                ),
                {
                    "review_queue_id": review_queue_id,
                    "stratum": stratum,
                },
            )
        ).mappings()
        return [
            {
                "retailer_id": str(row["competitor_retailer_id"]),
                "case_count": int(row["case_count"]),
            }
            for row in rows
        ]

    @staticmethod
    async def _case_rows(
        connection: AsyncConnection,
        review_queue_id: str,
        *,
        competitor_retailer_id: str | None,
        stratum: str | None,
    ) -> list[Mapping[str, Any]]:
        rows = (
            await connection.execute(
                text(
                    """
                    SELECT id::text, external_case_id, competitor_retailer_id,
                           stratum, critical, case_document, created_at
                    FROM matching_v2_review_case
                    WHERE review_queue_id = CAST(:review_queue_id AS uuid)
                      AND (CAST(:competitor_retailer_id AS text) IS NULL
                           OR competitor_retailer_id = CAST(:competitor_retailer_id AS text))
                      AND (CAST(:stratum AS text) IS NULL
                           OR stratum = CAST(:stratum AS text))
                    ORDER BY critical DESC, stratum, external_case_id
                    """
                ),
                {
                    "review_queue_id": review_queue_id,
                    "competitor_retailer_id": competitor_retailer_id,
                    "stratum": stratum,
                },
            )
        ).mappings()
        return [dict(row) for row in rows]

    @staticmethod
    async def _submission_rows(
        connection: AsyncConnection, case_ids: Sequence[str]
    ) -> list[Mapping[str, Any]]:
        if not case_ids:
            return []
        rows = (
            await connection.execute(
                text(
                    """
                    SELECT id::text, review_case_id::text, reviewer_id, verdict,
                           allowed_tiers, rationale, evidence_refs,
                           submission_checksum, supersedes_submission_id::text,
                           bulk_action_id::text, created_at
                    FROM matching_v2_review_submission
                    WHERE review_case_id = ANY(CAST(:case_ids AS uuid[]))
                    ORDER BY review_case_id, created_at DESC, id DESC
                    """
                ),
                {"case_ids": list(case_ids)},
            )
        ).mappings()
        return [dict(row) for row in rows]

    @staticmethod
    async def _adjudication_rows(
        connection: AsyncConnection, case_ids: Sequence[str]
    ) -> list[Mapping[str, Any]]:
        if not case_ids:
            return []
        rows = (
            await connection.execute(
                text(
                    """
                    SELECT DISTINCT ON (a.review_case_id)
                           a.id::text, a.review_case_id::text, a.adjudicator_id,
                           a.verdict, a.allowed_tiers, a.rationale, a.evidence_refs,
                           a.adjudication_checksum, a.created_at,
                           coalesce(array_agg(link.submission_id::text)
                             FILTER (WHERE link.submission_id IS NOT NULL), ARRAY[]::text[])
                             AS submission_ids
                    FROM matching_v2_adjudication a
                    LEFT JOIN matching_v2_adjudication_submission link
                      ON link.adjudication_id = a.id
                    WHERE a.review_case_id = ANY(CAST(:case_ids AS uuid[]))
                    GROUP BY a.id
                    ORDER BY a.review_case_id, a.created_at DESC, a.id DESC
                    """
                ),
                {"case_ids": list(case_ids)},
            )
        ).mappings()
        return [dict(row) for row in rows]

    @staticmethod
    async def _ai_draft_rows(
        connection: AsyncConnection, case_ids: Sequence[str]
    ) -> list[Mapping[str, Any]]:
        if not case_ids:
            return []
        rows = (
            await connection.execute(
                text(
                    """
                    SELECT DISTINCT ON (review_case_id)
                           id::text, batch_id::text, review_case_id::text,
                           status, requested_by,
                           model_provider, model_id, prompt_id, prompt_version,
                           prompt_checksum, input_checksum, output_checksum,
                           output_document, usage, attempt_count, max_attempts,
                           last_error_type, last_error_message, created_at,
                           updated_at, locked_at, lease_expires_at, completed_at
                    FROM matching_v2_ai_review_task
                    WHERE review_case_id = ANY(CAST(:case_ids AS uuid[]))
                    ORDER BY review_case_id, created_at DESC, id DESC
                    """
                ),
                {"case_ids": list(case_ids)},
            )
        ).mappings()
        return [dict(row) for row in rows]

    @staticmethod
    async def _ai_review_summary(
        connection: AsyncConnection, review_queue_id: str
    ) -> dict[str, Any]:
        status_row = (
            (
                await connection.execute(
                    text(
                        """
                        WITH latest AS (
                          SELECT DISTINCT ON (task.review_case_id)
                                 task.status
                          FROM matching_v2_ai_review_task task
                          JOIN matching_v2_review_case review_case
                            ON review_case.id = task.review_case_id
                          WHERE review_case.review_queue_id = CAST(:review_queue_id AS uuid)
                          ORDER BY task.review_case_id, task.created_at DESC, task.id DESC
                        )
                        SELECT count(*) FILTER (WHERE status = 'queued') AS queued,
                               count(*) FILTER (WHERE status = 'running') AS running,
                               count(*) FILTER (WHERE status = 'succeeded') AS succeeded,
                               count(*) FILTER (WHERE status = 'needs_review') AS needs_review
                        FROM latest
                        """
                    ),
                    {"review_queue_id": review_queue_id},
                )
            )
            .mappings()
            .one()
        )
        batch = (
            (
                await connection.execute(
                    text(
                        """
                        SELECT batch.id::text, batch.requested_by, batch.model_provider,
                               batch.model_id, batch.requested_case_count,
                               batch.created_at AS submitted_at,
                               min(task.locked_at) AS started_at,
                               max(task.updated_at) AS last_activity_at,
                               CASE
                                 WHEN count(task.id) > 0
                                  AND count(task.id) FILTER (
                                    WHERE task.status IN ('queued', 'running')
                                  ) = 0
                                 THEN max(coalesce(task.completed_at, task.updated_at))
                                 ELSE NULL
                               END AS completed_at,
                               count(task.id) AS task_count,
                               count(task.id) FILTER (WHERE task.status = 'queued') AS queued,
                               count(task.id) FILTER (WHERE task.status = 'running') AS running,
                               count(task.id) FILTER (WHERE task.status = 'succeeded') AS succeeded,
                               count(task.id) FILTER (
                                 WHERE task.status = 'needs_review'
                               ) AS needs_review,
                               coalesce(sum(
                                 CASE
                                   WHEN task.usage ? 'estimated_cost_usd'
                                   THEN (task.usage->>'estimated_cost_usd')::numeric
                                   ELSE 0
                                 END
                               ), 0) AS estimated_cost_usd
                        FROM matching_v2_ai_review_batch batch
                        LEFT JOIN matching_v2_ai_review_task task
                          ON task.batch_id = batch.id
                        WHERE batch.review_queue_id = CAST(:review_queue_id AS uuid)
                        GROUP BY batch.id
                        ORDER BY batch.created_at DESC, batch.id DESC
                        LIMIT 1
                        """
                    ),
                    {"review_queue_id": review_queue_id},
                )
            )
            .mappings()
            .first()
        )
        counts = {
            key: int(status_row[key] or 0)
            for key in ("queued", "running", "succeeded", "needs_review")
        }
        if batch is None:
            return {
                "active_task_count": counts["queued"] + counts["running"],
                "status_counts": counts,
                "latest_batch": None,
            }
        batch_counts = {
            key: int(batch[key] or 0) for key in ("queued", "running", "succeeded", "needs_review")
        }
        completed_count = batch_counts["succeeded"] + batch_counts["needs_review"]
        task_count = int(batch["task_count"] or 0)
        estimated_seconds_remaining: int | None = None
        if completed_count and batch_counts["queued"] + batch_counts["running"]:
            elapsed = max(
                0.0,
                (batch["last_activity_at"] - batch["submitted_at"]).total_seconds(),
            )
            estimated_seconds_remaining = math.ceil(
                (elapsed / completed_count) * (task_count - completed_count)
            )
        iso_fields = {
            key: (batch[key].isoformat() if batch[key] is not None else None)
            for key in ("submitted_at", "started_at", "last_activity_at", "completed_at")
        }
        return {
            "active_task_count": counts["queued"] + counts["running"],
            "status_counts": counts,
            "latest_batch": {
                "id": str(batch["id"]),
                "requested_by": str(batch["requested_by"]),
                "model_provider": str(batch["model_provider"]),
                "model_id": str(batch["model_id"]),
                "requested_case_count": int(batch["requested_case_count"]),
                "task_count": task_count,
                **batch_counts,
                "completed_count": completed_count,
                "progress_percent": (
                    round((completed_count / task_count) * 100, 1) if task_count else 0.0
                ),
                "estimated_seconds_remaining": estimated_seconds_remaining,
                "estimated_cost_usd": float(batch["estimated_cost_usd"] or 0),
                **iso_fields,
            },
        }

    @staticmethod
    def _case_documents(
        cases: Sequence[Mapping[str, Any]],
        submissions: Sequence[Mapping[str, Any]],
        adjudications: Sequence[Mapping[str, Any]],
        ai_drafts: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        submissions_by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in submissions:
            submissions_by_case[str(row["review_case_id"])].append(
                {key: value for key, value in row.items() if key != "review_case_id"}
            )
        adjudication_by_case = {
            str(row["review_case_id"]): {
                key: value for key, value in row.items() if key != "review_case_id"
            }
            for row in adjudications
        }
        ai_draft_by_case = {
            str(row["review_case_id"]): {
                key: (value.isoformat() if hasattr(value, "isoformat") else value)
                for key, value in row.items()
                if key != "review_case_id"
            }
            for row in ai_drafts
        }
        output: list[dict[str, Any]] = []
        for row in cases:
            case_id = str(row["id"])
            reviews = submissions_by_case.get(case_id, [])
            adjudication = adjudication_by_case.get(case_id)
            decision_candidates: list[dict[str, Any]] = []
            if reviews:
                decision_candidates.append(
                    {
                        **reviews[0],
                        "source": "review_submission",
                        "reviewer_id": reviews[0]["reviewer_id"],
                    }
                )
            if adjudication is not None:
                decision_candidates.append(
                    {
                        **adjudication,
                        "source": "legacy_adjudication",
                        "reviewer_id": adjudication["adjudicator_id"],
                    }
                )
            final_decision = max(
                decision_candidates,
                key=lambda decision: decision["created_at"],
                default=None,
            )
            if final_decision is None:
                review_status = "pending"
            elif final_decision["verdict"] == "comparable":
                review_status = "approved"
            elif final_decision["verdict"] == "not_comparable":
                review_status = "rejected"
            else:
                review_status = "flagged"
            output.append(
                {
                    **dict(row["case_document"]),
                    "database_id": case_id,
                    "review_status": review_status,
                    "review_submissions": reviews,
                    "adjudication": adjudication,
                    "final_decision": final_decision,
                    "ai_draft": ai_draft_by_case.get(case_id),
                }
            )
        return output

    @staticmethod
    async def _bulk_ai_snapshot(
        connection: AsyncConnection,
        external_queue_id: str,
        external_case_ids: Sequence[str],
        *,
        lock_cases: bool,
    ) -> tuple[str, str, list[dict[str, Any]]]:
        lock_clause = "FOR UPDATE OF review_case" if lock_cases else ""
        rows = list(
            (
                await connection.execute(
                    text(
                        f"""
                        WITH selected_queue AS (
                          SELECT id, version
                          FROM matching_v2_review_queue
                          WHERE external_queue_id = :queue_id
                          ORDER BY created_at DESC
                          LIMIT 1
                        )
                        SELECT selected_queue.id::text AS review_queue_id,
                               selected_queue.version AS queue_version,
                               review_case.id::text AS review_case_id,
                               review_case.external_case_id,
                               review_case.case_document,
                               review_case.case_checksum,
                               current_decision.verdict AS current_verdict,
                               ai_task.id::text AS ai_task_id,
                               ai_task.status AS ai_status,
                               ai_task.output_document AS ai_output_document,
                               ai_task.output_checksum AS ai_output_checksum,
                               ai_task.model_id AS ai_model_id,
                               ai_task.requested_by AS ai_requested_by,
                               ai_task.created_at AS ai_created_at,
                               ai_task.updated_at AS ai_updated_at
                        FROM selected_queue
                        JOIN matching_v2_review_case review_case
                          ON review_case.review_queue_id = selected_queue.id
                        LEFT JOIN LATERAL (
                          SELECT decision.verdict
                          FROM (
                            SELECT submission.verdict, submission.created_at, submission.id
                            FROM matching_v2_review_submission submission
                            WHERE submission.review_case_id = review_case.id
                            UNION ALL
                            SELECT adjudication.verdict, adjudication.created_at, adjudication.id
                            FROM matching_v2_adjudication adjudication
                            WHERE adjudication.review_case_id = review_case.id
                          ) decision
                          ORDER BY decision.created_at DESC, decision.id DESC
                          LIMIT 1
                        ) current_decision ON true
                        LEFT JOIN LATERAL (
                          SELECT task.id, task.status, task.output_document,
                                 task.output_checksum, task.model_id, task.requested_by,
                                 task.created_at, task.updated_at
                          FROM matching_v2_ai_review_task task
                          WHERE task.review_case_id = review_case.id
                          ORDER BY task.created_at DESC, task.id DESC
                          LIMIT 1
                        ) ai_task ON true
                        WHERE review_case.external_case_id = ANY(CAST(:case_ids AS text[]))
                        ORDER BY review_case.external_case_id
                        {lock_clause}
                        """
                    ),
                    {"queue_id": external_queue_id, "case_ids": list(external_case_ids)},
                )
            )
            .mappings()
            .all()
        )
        if not rows:
            raise KeyError(f"matching v2 review queue {external_queue_id!r} was not found")
        rows_by_case = {str(row["external_case_id"]): row for row in rows}
        missing = [case_id for case_id in external_case_ids if case_id not in rows_by_case]
        if missing:
            raise KeyError(
                f"matching v2 review cases {missing!r} were not found in queue "
                f"{external_queue_id!r}"
            )
        snapshots: list[dict[str, Any]] = []
        for external_case_id in external_case_ids:
            row = rows_by_case[external_case_id]
            document = dict(row["case_document"])
            current_verdict = row["current_verdict"]
            if current_verdict is None:
                review_status = "pending"
            elif current_verdict == "comparable":
                review_status = "approved"
            elif current_verdict == "not_comparable":
                review_status = "rejected"
            else:
                review_status = "flagged"
            ai_draft = None
            if row["ai_task_id"] is not None:
                ai_draft = {
                    "id": str(row["ai_task_id"]),
                    "status": str(row["ai_status"]),
                    "output_document": row["ai_output_document"],
                    "output_checksum": row["ai_output_checksum"],
                    "model_id": row["ai_model_id"],
                    "requested_by": row["ai_requested_by"],
                    "created_at": row["ai_created_at"].isoformat(),
                    "updated_at": row["ai_updated_at"].isoformat(),
                }
            snapshots.append(
                {
                    **document,
                    "review_case_id": str(row["review_case_id"]),
                    "case_checksum": str(row["case_checksum"]),
                    "review_status": review_status,
                    "ai_draft": ai_draft,
                    "ai_output_checksum": str(row["ai_output_checksum"] or ""),
                }
            )
        queue_version = str(rows[0]["queue_version"])
        _apply_observed_location_sidecar(
            snapshots,
            queue_id=external_queue_id,
            queue_version=queue_version,
            root=_repository_root(),
        )
        return str(rows[0]["review_queue_id"]), queue_version, snapshots

    async def preview_ai_bulk_certification(
        self,
        external_queue_id: str,
        external_case_ids: Sequence[str],
    ) -> dict[str, Any]:
        async with self._engine.connect() as connection:
            _, queue_version, snapshots = await self._bulk_ai_snapshot(
                connection,
                external_queue_id,
                external_case_ids,
                lock_cases=False,
            )
        return _bulk_preview_document(
            queue_id=external_queue_id,
            queue_version=queue_version,
            snapshots=snapshots,
        )

    async def commit_ai_bulk_certification(
        self,
        external_queue_id: str,
        external_case_ids: Sequence[str],
        *,
        reviewer_id: str,
        confirmation_checksum: str,
    ) -> dict[str, Any]:
        idempotency_key = _checksum(
            {
                "queue_id": external_queue_id,
                "reviewer_id": reviewer_id,
                "confirmation_checksum": confirmation_checksum,
            }
        )
        async with self._engine.begin() as connection:
            existing = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT id::text, case_ids, case_count, created_at
                            FROM matching_v2_bulk_certification_action
                            WHERE idempotency_key = :idempotency_key
                            """
                        ),
                        {"idempotency_key": idempotency_key},
                    )
                )
                .mappings()
                .first()
            )
            if existing is not None:
                return {
                    "action_id": str(existing["id"]),
                    "queue_id": external_queue_id,
                    "approved_case_ids": list(existing["case_ids"]),
                    "approved_case_count": int(existing["case_count"]),
                    "confirmation_checksum": confirmation_checksum,
                    "created_at": existing["created_at"].isoformat(),
                    "idempotent_replay": True,
                    "final_until_flagged": True,
                    "automatically_changes_reporting": False,
                }

            case_id_rows = list(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT review_case.id::text
                            FROM matching_v2_review_case review_case
                            JOIN matching_v2_review_queue review_queue
                              ON review_queue.id = review_case.review_queue_id
                            WHERE review_queue.external_queue_id = :queue_id
                              AND review_case.external_case_id = ANY(CAST(:case_ids AS text[]))
                            ORDER BY review_case.id
                            """
                        ),
                        {
                            "queue_id": external_queue_id,
                            "case_ids": list(external_case_ids),
                        },
                    )
                )
                .scalars()
                .all()
            )
            for review_case_id in case_id_rows:
                await connection.execute(
                    text("SELECT pg_advisory_xact_lock(hashtextextended(:case_id, 0))"),
                    {"case_id": str(review_case_id)},
                )

            review_queue_id, queue_version, snapshots = await self._bulk_ai_snapshot(
                connection,
                external_queue_id,
                external_case_ids,
                lock_cases=True,
            )
            preview = _bulk_preview_document(
                queue_id=external_queue_id,
                queue_version=queue_version,
                snapshots=snapshots,
            )
            if preview["excluded_case_count"]:
                excluded = ", ".join(
                    f"{candidate['case_id']} ({', '.join(candidate['reason_codes'])})"
                    for candidate in preview["excluded_cases"]
                )
                raise ValueError(
                    "bulk certification stopped because one or more cases changed or no "
                    f"longer pass policy: {excluded}"
                )
            current_checksum = str(preview["confirmation_checksum"] or "")
            if not secrets.compare_digest(current_checksum, confirmation_checksum):
                raise ValueError(
                    "bulk certification preview is stale; assess the recommendations again"
                )

            policy = _ai_bulk_certification_policy()
            audit_document = {
                "schema_version": "1.0.0-ai-bulk-certification-action",
                "queue_id": external_queue_id,
                "queue_version": queue_version,
                "reviewer_id": reviewer_id,
                "policy": policy,
                "confirmation_checksum": confirmation_checksum,
                "cases": [
                    {
                        "case_id": candidate["case_id"],
                        "case_checksum": candidate["case_checksum"],
                        "ai_task_id": candidate["ai_task_id"],
                        "ai_output_checksum": candidate["ai_output_checksum"],
                        "recommended_tier": candidate["recommended_tier"],
                    }
                    for candidate in preview["eligible_cases"]
                ],
                "human_confirmation_required": True,
                "final_until_flagged": True,
                "automatically_changes_reporting": False,
            }
            action = (
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO matching_v2_bulk_certification_action (
                              review_queue_id, reviewer_id, action_type, policy_id,
                              policy_version, policy_checksum, confirmation_checksum,
                              idempotency_key, case_ids, case_count, audit_document
                            ) VALUES (
                              CAST(:review_queue_id AS uuid), :reviewer_id,
                              'approve_ai_matches', :policy_id, :policy_version,
                              :policy_checksum, :confirmation_checksum, :idempotency_key,
                              :case_ids, :case_count, CAST(:audit_document AS jsonb)
                            )
                            RETURNING id::text, created_at
                            """
                        ),
                        {
                            "review_queue_id": review_queue_id,
                            "reviewer_id": reviewer_id,
                            "policy_id": policy["id"],
                            "policy_version": policy["version"],
                            "policy_checksum": policy["checksum"],
                            "confirmation_checksum": confirmation_checksum,
                            "idempotency_key": idempotency_key,
                            "case_ids": list(external_case_ids),
                            "case_count": len(external_case_ids),
                            "audit_document": _canonical(audit_document),
                        },
                    )
                )
                .mappings()
                .one()
            )
            action_id = str(action["id"])
            snapshots_by_case = {str(row["case_id"]): row for row in snapshots}
            preview_by_case = {str(row["case_id"]): row for row in preview["eligible_cases"]}
            decisions: list[dict[str, Any]] = []
            for external_case_id in external_case_ids:
                snapshot = snapshots_by_case[external_case_id]
                candidate = preview_by_case[external_case_id]
                ai_reference = (
                    f"matching-v2-ai-review://{candidate['ai_task_id']}"
                    f"#sha256={candidate['ai_output_checksum']}"
                )
                evidence_refs = list(
                    dict.fromkeys([*snapshot.get("evidence_refs", []), ai_reference])
                )
                rationale = (
                    "Administrator bulk-certified this AI recommendation after the "
                    f"{policy['id']} v{policy['version']} preview passed every guardrail. "
                    f"AI evidence rationale: {candidate['ai_rationale']}"
                )
                submission_checksum = _checksum(
                    {
                        "queue_id": external_queue_id,
                        "case_id": external_case_id,
                        "reviewer_id": reviewer_id,
                        "verdict": "comparable",
                        "allowed_tiers": [candidate["recommended_tier"]],
                        "rationale": rationale,
                        "evidence_refs": evidence_refs,
                        "bulk_action_id": action_id,
                    }
                )
                submission = (
                    (
                        await connection.execute(
                            text(
                                """
                                INSERT INTO matching_v2_review_submission (
                                  review_case_id, reviewer_id, verdict, allowed_tiers,
                                  rationale, evidence_refs, submission_checksum,
                                  supersedes_submission_id, bulk_action_id
                                ) VALUES (
                                  CAST(:review_case_id AS uuid), :reviewer_id,
                                  'comparable', :allowed_tiers, :rationale,
                                  CAST(:evidence_refs AS jsonb), :submission_checksum,
                                  NULL, CAST(:bulk_action_id AS uuid)
                                )
                                RETURNING id::text, created_at
                                """
                            ),
                            {
                                "review_case_id": snapshot["review_case_id"],
                                "reviewer_id": reviewer_id,
                                "allowed_tiers": [candidate["recommended_tier"]],
                                "rationale": rationale,
                                "evidence_refs": _canonical(evidence_refs),
                                "submission_checksum": submission_checksum,
                                "bulk_action_id": action_id,
                            },
                        )
                    )
                    .mappings()
                    .one()
                )
                decisions.append(
                    {
                        "case_id": external_case_id,
                        "submission_id": str(submission["id"]),
                        "tier": candidate["recommended_tier"],
                        "created_at": submission["created_at"].isoformat(),
                    }
                )
        return {
            "action_id": action_id,
            "queue_id": external_queue_id,
            "approved_case_ids": list(external_case_ids),
            "approved_case_count": len(external_case_ids),
            "confirmation_checksum": confirmation_checksum,
            "decisions": decisions,
            "created_at": action["created_at"].isoformat(),
            "idempotent_replay": False,
            "final_until_flagged": True,
            "automatically_changes_reporting": False,
        }

    async def request_ai_draft(
        self,
        external_queue_id: str,
        external_case_id: str,
        *,
        requested_by: str,
        model_id: str,
        prompt: Mapping[str, str],
    ) -> dict[str, Any]:
        tasks = await self.request_ai_drafts(
            external_queue_id,
            [external_case_id],
            requested_by=requested_by,
            model_id=model_id,
            prompt=prompt,
        )
        return tasks[0]

    async def request_ai_drafts(
        self,
        external_queue_id: str,
        external_case_ids: Sequence[str],
        *,
        requested_by: str,
        model_id: str,
        prompt: Mapping[str, str],
    ) -> list[dict[str, Any]]:
        async with self._engine.begin() as connection:
            rows = list(
                (
                    await connection.execute(
                        text(
                            """
                            WITH selected_queue AS (
                              SELECT id, version
                              FROM matching_v2_review_queue
                              WHERE external_queue_id = :queue_id
                              ORDER BY created_at DESC
                              LIMIT 1
                            )
                            SELECT c.id::text, c.external_case_id, c.case_document,
                                   c.case_checksum, c.review_queue_id::text,
                                   q.version AS queue_version,
                                   (
                                     SELECT decision.verdict
                                     FROM (
                                       SELECT s.verdict, s.created_at, s.id
                                       FROM matching_v2_review_submission s
                                       WHERE s.review_case_id = c.id
                                       UNION ALL
                                       SELECT a.verdict, a.created_at, a.id
                                       FROM matching_v2_adjudication a
                                       WHERE a.review_case_id = c.id
                                     ) decision
                                     ORDER BY decision.created_at DESC, decision.id DESC
                                     LIMIT 1
                                   ) AS current_verdict
                            FROM matching_v2_review_case c
                            JOIN selected_queue q ON q.id = c.review_queue_id
                            WHERE c.external_case_id = ANY(CAST(:case_ids AS text[]))
                            """
                        ),
                        {"queue_id": external_queue_id, "case_ids": list(external_case_ids)},
                    )
                )
                .mappings()
                .all()
            )
            rows_by_case = {str(row["external_case_id"]): row for row in rows}
            missing = [case_id for case_id in external_case_ids if case_id not in rows_by_case]
            if missing:
                raise KeyError(
                    f"matching v2 review cases {missing!r} were not found in queue "
                    f"{external_queue_id!r}"
                )
            sidecar_documents = {
                case_id: dict(rows_by_case[case_id]["case_document"])
                for case_id in external_case_ids
            }
            _apply_observed_location_sidecar(
                list(sidecar_documents.values()),
                queue_id=external_queue_id,
                queue_version=str(rows[0]["queue_version"]),
                root=_repository_root(),
            )
            excluded_seller_cases = [
                case_id
                for case_id in external_case_ids
                if _case_has_known_third_party_seller(sidecar_documents[case_id])
            ]
            if excluded_seller_cases:
                raise ValueError(
                    "known third-party marketplace seller cases cannot request AI drafts: "
                    f"{excluded_seller_cases!r}"
                )
            finalized = [
                case_id
                for case_id in external_case_ids
                if rows_by_case[case_id]["current_verdict"] in {"comparable", "not_comparable"}
            ]
            if finalized:
                raise ValueError(f"finalized review cases cannot request AI drafts: {finalized!r}")
            batch = await self._insert_ai_review_batch(
                connection,
                review_queue_id=str(rows[0]["review_queue_id"]),
                external_case_ids=external_case_ids,
                requested_by=requested_by,
                model_id=model_id,
                prompt=prompt,
            )
            tasks = [
                await self._insert_ai_draft_task(
                    connection,
                    dict(rows_by_case[case_id]),
                    batch_id=str(batch["id"]),
                    requested_by=requested_by,
                    model_id=model_id,
                    prompt=prompt,
                )
                for case_id in external_case_ids
            ]
            if any(str(task["batch_id"]) != str(batch["id"]) for task in tasks):
                raise ValueError(
                    "one or more selected cases already belong to a different AI review batch"
                )
        return tasks

    @staticmethod
    async def _insert_ai_review_batch(
        connection: AsyncConnection,
        *,
        review_queue_id: str,
        external_case_ids: Sequence[str],
        requested_by: str,
        model_id: str,
        prompt: Mapping[str, str],
    ) -> dict[str, Any]:
        idempotency_key = _checksum(
            {
                "review_queue_id": review_queue_id,
                "case_ids": sorted(external_case_ids),
                "model_id": model_id,
                "prompt_checksum": prompt["checksum"],
            }
        )
        row = (
            (
                await connection.execute(
                    text(
                        """
                        INSERT INTO matching_v2_ai_review_batch (
                          review_queue_id, idempotency_key, requested_by,
                          model_provider, model_id, prompt_id, prompt_version,
                          prompt_checksum, requested_case_count
                        ) VALUES (
                          CAST(:review_queue_id AS uuid), :idempotency_key,
                          :requested_by, 'openai', :model_id, :prompt_id,
                          :prompt_version, :prompt_checksum, :requested_case_count
                        )
                        ON CONFLICT (idempotency_key) DO UPDATE SET
                          updated_at = matching_v2_ai_review_batch.updated_at
                        RETURNING id::text, created_at, requested_case_count
                        """
                    ),
                    {
                        "review_queue_id": review_queue_id,
                        "idempotency_key": idempotency_key,
                        "requested_by": requested_by,
                        "model_id": model_id,
                        "prompt_id": prompt["id"],
                        "prompt_version": prompt["version"],
                        "prompt_checksum": prompt["checksum"],
                        "requested_case_count": len(external_case_ids),
                    },
                )
            )
            .mappings()
            .one()
        )
        return dict(row)

    @staticmethod
    async def _insert_ai_draft_task(
        connection: AsyncConnection,
        row: Mapping[str, Any],
        *,
        batch_id: str,
        requested_by: str,
        model_id: str,
        prompt: Mapping[str, str],
    ) -> dict[str, Any]:
        input_document = dict(row["case_document"])
        input_checksum = _checksum(input_document)
        idempotency_key = _checksum(
            {
                "review_case_id": str(row["id"]),
                "case_checksum": str(row["case_checksum"]),
                "model_id": model_id,
                "prompt_checksum": prompt["checksum"],
                "input_checksum": input_checksum,
            }
        )
        task = (
            (
                await connection.execute(
                    text(
                        """
                        INSERT INTO matching_v2_ai_review_task (
                          review_case_id, batch_id, idempotency_key, requested_by, status,
                          prompt_id, prompt_version, prompt_checksum,
                          model_provider, model_id, input_checksum, input_document
                        ) VALUES (
                          CAST(:review_case_id AS uuid), CAST(:batch_id AS uuid),
                          :idempotency_key, :requested_by,
                          'queued', :prompt_id, :prompt_version, :prompt_checksum,
                          'openai', :model_id, :input_checksum,
                          CAST(:input_document AS jsonb)
                        )
                        ON CONFLICT (idempotency_key) DO UPDATE SET
                          requested_by = matching_v2_ai_review_task.requested_by
                        RETURNING id::text, batch_id::text, status, model_provider, model_id,
                                  prompt_id, prompt_version, input_checksum,
                                  attempt_count, max_attempts, created_at
                        """
                    ),
                    {
                        "review_case_id": str(row["id"]),
                        "batch_id": batch_id,
                        "idempotency_key": idempotency_key,
                        "requested_by": requested_by,
                        "prompt_id": prompt["id"],
                        "prompt_version": prompt["version"],
                        "prompt_checksum": prompt["checksum"],
                        "model_id": model_id,
                        "input_checksum": input_checksum,
                        "input_document": _canonical(input_document),
                    },
                )
            )
            .mappings()
            .one()
        )
        return {
            **{
                key: (value.isoformat() if hasattr(value, "isoformat") else value)
                for key, value in task.items()
            },
            "authoritative": False,
            "human_review_required": True,
        }

    async def submit_review(
        self,
        external_queue_id: str,
        external_case_id: str,
        submission: Mapping[str, Any],
        *,
        submission_checksum: str,
    ) -> dict[str, Any]:
        async with self._engine.begin() as connection:
            case_id = await self._case_id(connection, external_queue_id, external_case_id)
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:case_id, 0))"),
                {"case_id": case_id},
            )
            case_row = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT review_case.case_document, review_queue.version
                        FROM matching_v2_review_case review_case
                        JOIN matching_v2_review_queue review_queue
                          ON review_queue.id = review_case.review_queue_id
                        WHERE review_case.id = CAST(:case_id AS uuid)
                        """
                        ),
                        {"case_id": case_id},
                    )
                )
                .mappings()
                .one()
            )
            case_document = dict(case_row["case_document"])
            _apply_observed_location_sidecar(
                [case_document],
                queue_id=external_queue_id,
                queue_version=str(case_row["version"]),
                root=_repository_root(),
            )
            if _case_has_known_third_party_seller(case_document):
                raise ValueError("a known third-party marketplace seller case cannot be certified")
            existing = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT id::text, created_at
                            FROM matching_v2_review_submission
                            WHERE submission_checksum = :checksum
                            """
                        ),
                        {"checksum": submission_checksum},
                    )
                )
                .mappings()
                .first()
            )
            if existing is not None:
                return {
                    "id": str(existing["id"]),
                    "queue_id": external_queue_id,
                    "case_id": external_case_id,
                    "checksum": submission_checksum,
                    "created_at": existing["created_at"].isoformat(),
                }
            current_decision = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT decision.verdict
                            FROM (
                              SELECT verdict, created_at, id
                              FROM matching_v2_review_submission
                              WHERE review_case_id = CAST(:case_id AS uuid)
                              UNION ALL
                              SELECT verdict, created_at, id
                              FROM matching_v2_adjudication
                              WHERE review_case_id = CAST(:case_id AS uuid)
                            ) decision
                            ORDER BY decision.created_at DESC, decision.id DESC
                            LIMIT 1
                            """
                        ),
                        {"case_id": case_id},
                    )
                )
                .mappings()
                .first()
            )
            if (
                current_decision is not None
                and current_decision["verdict"] in {"comparable", "not_comparable"}
                and submission["verdict"] != "insufficient_evidence"
            ):
                raise ValueError(
                    "a finalized review case must be flagged before its decision can change"
                )
            supersedes_submission_id = submission.get("supersedes_submission_id")
            if supersedes_submission_id is not None:
                superseded = (
                    (
                        await connection.execute(
                            text(
                                """
                                SELECT id::text
                                FROM matching_v2_review_submission
                                WHERE id = CAST(:submission_id AS uuid)
                                  AND review_case_id = CAST(:case_id AS uuid)
                                """
                            ),
                            {
                                "submission_id": supersedes_submission_id,
                                "case_id": case_id,
                            },
                        )
                    )
                    .mappings()
                    .first()
                )
                if superseded is None:
                    raise ValueError("a superseded review must belong to the same case")
            row = (
                (
                    await connection.execute(
                        text(
                            """
                        INSERT INTO matching_v2_review_submission (
                          review_case_id, reviewer_id, verdict, allowed_tiers,
                          rationale, evidence_refs, submission_checksum,
                          supersedes_submission_id
                        ) VALUES (
                          CAST(:case_id AS uuid), :reviewer_id, :verdict, :allowed_tiers,
                          :rationale, CAST(:evidence_refs AS jsonb), :submission_checksum,
                          CAST(:supersedes_submission_id AS uuid)
                        )
                        ON CONFLICT (submission_checksum) DO NOTHING
                        RETURNING id::text, created_at
                        """
                        ),
                        {
                            "case_id": case_id,
                            "reviewer_id": submission["reviewer_id"],
                            "verdict": submission["verdict"],
                            "allowed_tiers": list(submission["allowed_tiers"]),
                            "rationale": submission["rationale"],
                            "evidence_refs": _canonical(submission["evidence_refs"]),
                            "submission_checksum": submission_checksum,
                            "supersedes_submission_id": supersedes_submission_id,
                        },
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                row = (
                    (
                        await connection.execute(
                            text(
                                """
                            SELECT id::text, created_at
                            FROM matching_v2_review_submission
                            WHERE submission_checksum = :checksum
                            """
                            ),
                            {"checksum": submission_checksum},
                        )
                    )
                    .mappings()
                    .one()
                )
        return {
            "id": str(row["id"]),
            "queue_id": external_queue_id,
            "case_id": external_case_id,
            "checksum": submission_checksum,
            "created_at": row["created_at"].isoformat(),
        }

    async def adjudicate(
        self,
        external_queue_id: str,
        external_case_id: str,
        adjudication: Mapping[str, Any],
        *,
        adjudication_checksum: str,
    ) -> dict[str, Any]:
        submission_ids = list(adjudication["submission_ids"])
        async with self._engine.begin() as connection:
            case_id = await self._case_id(connection, external_queue_id, external_case_id)
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:case_id, 0))"),
                {"case_id": case_id},
            )
            submissions = list(
                (
                    await connection.execute(
                        text(
                            """
                            WITH latest AS (
                              SELECT DISTINCT ON (reviewer_id) id, reviewer_id
                              FROM matching_v2_review_submission
                              WHERE review_case_id = CAST(:case_id AS uuid)
                              ORDER BY reviewer_id, created_at DESC, id DESC
                            )
                            SELECT id::text, reviewer_id
                            FROM latest
                            WHERE id = ANY(CAST(:submission_ids AS uuid[]))
                            """
                        ),
                        {"case_id": case_id, "submission_ids": submission_ids},
                    )
                ).mappings()
            )
            if len(submissions) != len(set(submission_ids)):
                raise ValueError(
                    "every adjudication submission must be the current review for its "
                    "reviewer and belong to the case"
                )
            if len({str(row["reviewer_id"]) for row in submissions}) < 2:
                raise ValueError("adjudication requires two independent reviewers")
            existing_adjudication_id = await connection.scalar(
                text(
                    """
                    SELECT id::text
                    FROM matching_v2_adjudication
                    WHERE review_case_id = CAST(:case_id AS uuid)
                    ORDER BY created_at DESC, id DESC
                    LIMIT 1
                    """
                ),
                {"case_id": case_id},
            )
            supersedes_adjudication_id = adjudication.get("supersedes_adjudication_id")
            if existing_adjudication_id is None and supersedes_adjudication_id is not None:
                raise ValueError("there is no prior adjudication to supersede")
            if existing_adjudication_id is not None and str(existing_adjudication_id) != str(
                supersedes_adjudication_id
            ):
                raise ValueError(
                    "a replacement adjudication must supersede the latest case adjudication"
                )
            row = (
                (
                    await connection.execute(
                        text(
                            """
                        INSERT INTO matching_v2_adjudication (
                          review_case_id, adjudicator_id, verdict, allowed_tiers,
                          rationale, evidence_refs, adjudication_checksum,
                          supersedes_adjudication_id
                        ) VALUES (
                          CAST(:case_id AS uuid), :adjudicator_id, :verdict, :allowed_tiers,
                          :rationale, CAST(:evidence_refs AS jsonb), :adjudication_checksum,
                          CAST(:supersedes_adjudication_id AS uuid)
                        )
                        ON CONFLICT (adjudication_checksum) DO NOTHING
                        RETURNING id::text, created_at
                        """
                        ),
                        {
                            "case_id": case_id,
                            "adjudicator_id": adjudication["adjudicator_id"],
                            "verdict": adjudication["verdict"],
                            "allowed_tiers": list(adjudication["allowed_tiers"]),
                            "rationale": adjudication["rationale"],
                            "evidence_refs": _canonical(adjudication["evidence_refs"]),
                            "adjudication_checksum": adjudication_checksum,
                            "supersedes_adjudication_id": supersedes_adjudication_id,
                        },
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                row = (
                    (
                        await connection.execute(
                            text(
                                """
                            SELECT id::text, created_at
                            FROM matching_v2_adjudication
                            WHERE adjudication_checksum = :checksum
                            """
                            ),
                            {"checksum": adjudication_checksum},
                        )
                    )
                    .mappings()
                    .one()
                )
            for submission_id in sorted(set(submission_ids)):
                await connection.execute(
                    text(
                        """
                        INSERT INTO matching_v2_adjudication_submission (
                          adjudication_id, submission_id
                        ) VALUES (CAST(:adjudication_id AS uuid), CAST(:submission_id AS uuid))
                        ON CONFLICT DO NOTHING
                        """
                    ),
                    {"adjudication_id": row["id"], "submission_id": submission_id},
                )
        return {
            "id": str(row["id"]),
            "queue_id": external_queue_id,
            "case_id": external_case_id,
            "checksum": adjudication_checksum,
            "created_at": row["created_at"].isoformat(),
        }

    @staticmethod
    async def _case_id(
        connection: AsyncConnection,
        external_queue_id: str,
        external_case_id: str,
    ) -> str:
        row = (
            (
                await connection.execute(
                    text(
                        """
                    SELECT c.id::text
                    FROM matching_v2_review_case c
                    JOIN matching_v2_review_queue q ON q.id = c.review_queue_id
                    WHERE q.external_queue_id = :queue_id
                      AND c.external_case_id = :case_id
                    ORDER BY q.created_at DESC
                    LIMIT 1
                    """
                    ),
                    {"queue_id": external_queue_id, "case_id": external_case_id},
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise KeyError(
                f"matching v2 review case {external_case_id!r} was not found "
                f"in queue {external_queue_id!r}"
            )
        return str(row["id"])


class MatchingV2ReviewService:
    def __init__(self, repository: MatchingV2ReviewRepository, repository_root: Path) -> None:
        self._repository = repository
        self._root = repository_root

    async def list_queues(self, *, limit: int) -> dict[str, Any]:
        queues = await self._repository.list_queues(limit=limit)
        return {
            "schema_version": "2.0.0-review-queue-index",
            "authoritative": False,
            "queues": queues,
        }

    async def import_queue(self, request: ImportReviewQueueRequest) -> dict[str, Any]:
        if request.queue_json is not None:
            try:
                queue = json.loads(request.queue_json)
            except json.JSONDecodeError as exc:
                raise ValueError("review queue JSON is invalid") from exc
            if not isinstance(queue, dict):
                raise ValueError("review queue JSON must contain an object")
        elif request.queue is not None:
            queue = request.queue
        else:
            raise ValueError("review queue import requires queue_json or queue")
        try:
            validate_instance(
                self._root,
                "matching-v2-review-queue.schema.json",
                queue,
                label="matching v2 review queue import",
            )
        except ContractError as exc:
            raise ValueError(str(exc)) from exc
        expected_checksum = str(queue["checksum"])
        unsigned = dict(queue)
        unsigned.pop("checksum", None)
        if _checksum(unsigned) != expected_checksum:
            raise ValueError("review queue checksum does not match its canonical document")
        excluded_seller_cases = [
            str(case.get("case_id") or "")
            for case in queue["cases"]
            if _case_has_known_third_party_seller(case)
        ]
        if excluded_seller_cases:
            raise ValueError(
                "review queue contains known third-party marketplace seller cases: "
                f"{excluded_seller_cases!r}"
            )
        return await self._repository.import_queue(
            request.organization_id,
            queue,
            imported_by=request.imported_by,
        )

    async def queue_view(self, external_queue_id: str, **filters: Any) -> dict[str, Any]:
        return await self._repository.queue_view(external_queue_id, **filters)

    async def submit_review(
        self,
        external_queue_id: str,
        external_case_id: str,
        request: ReviewSubmissionRequest,
    ) -> dict[str, Any]:
        self._validate_tiers(request.verdict, request.allowed_tiers)
        payload = request.model_dump(mode="json")
        checksum = _checksum(
            {"queue_id": external_queue_id, "case_id": external_case_id, **payload}
        )
        return await self._repository.submit_review(
            external_queue_id,
            external_case_id,
            payload,
            submission_checksum=checksum,
        )

    async def request_ai_draft(
        self,
        external_queue_id: str,
        external_case_id: str,
        request: AIReviewDraftRequest,
        *,
        model_id: str,
    ) -> dict[str, Any]:
        prompt = self._matching_review_prompt()
        return await self._repository.request_ai_draft(
            external_queue_id,
            external_case_id,
            requested_by=request.requested_by,
            model_id=model_id,
            prompt=prompt,
        )

    async def request_ai_drafts(
        self,
        external_queue_id: str,
        request: AIReviewBatchRequest,
        *,
        model_id: str,
    ) -> dict[str, Any]:
        case_ids = list(dict.fromkeys(request.case_ids))
        if len(case_ids) != len(request.case_ids):
            raise ValueError("AI draft batch case IDs must be unique")
        prompt = self._matching_review_prompt()
        tasks = await self._repository.request_ai_drafts(
            external_queue_id,
            case_ids,
            requested_by=request.requested_by,
            model_id=model_id,
            prompt=prompt,
        )
        return {
            "authoritative": False,
            "human_review_required": True,
            "queue_id": external_queue_id,
            "requested_case_count": len(case_ids),
            "batch": (
                {
                    "id": tasks[0]["batch_id"],
                    "created_at": tasks[0]["created_at"],
                    "requested_case_count": len(case_ids),
                }
                if tasks
                else None
            ),
            "tasks": tasks,
        }

    async def preview_ai_bulk_certification(
        self,
        external_queue_id: str,
        request: AIBulkCertificationPreviewRequest,
    ) -> dict[str, Any]:
        case_ids = list(dict.fromkeys(request.case_ids))
        if len(case_ids) != len(request.case_ids):
            raise ValueError("bulk certification case IDs must be unique")
        return await self._repository.preview_ai_bulk_certification(
            external_queue_id,
            case_ids,
        )

    async def commit_ai_bulk_certification(
        self,
        external_queue_id: str,
        request: AIBulkCertificationCommitRequest,
    ) -> dict[str, Any]:
        case_ids = list(dict.fromkeys(request.case_ids))
        if len(case_ids) != len(request.case_ids):
            raise ValueError("bulk certification case IDs must be unique")
        return await self._repository.commit_ai_bulk_certification(
            external_queue_id,
            case_ids,
            reviewer_id=request.reviewer_id,
            confirmation_checksum=request.confirmation_checksum,
        )

    def _matching_review_prompt(self) -> dict[str, str]:
        path = self._root / "agent-prompts" / "matching_v2_evidence_review.json"
        body = path.read_bytes()
        document = json.loads(body)
        validate_instance(self._root, "agent-prompt.schema.json", document, label=str(path))
        if document["role"] != "matching_review":
            raise ValueError("matching review prompt has the wrong role")
        return {
            "id": str(document["id"]),
            "version": str(document["version"]),
            "checksum": hashlib.sha256(body).hexdigest(),
        }

    async def adjudicate(
        self,
        external_queue_id: str,
        external_case_id: str,
        request: AdjudicationRequest,
    ) -> dict[str, Any]:
        self._validate_tiers(request.verdict, request.allowed_tiers)
        if len(set(request.submission_ids)) < 2:
            raise ValueError("adjudication requires two distinct submission IDs")
        payload = request.model_dump(mode="json")
        checksum = _checksum(
            {"queue_id": external_queue_id, "case_id": external_case_id, **payload}
        )
        return await self._repository.adjudicate(
            external_queue_id,
            external_case_id,
            payload,
            adjudication_checksum=checksum,
        )

    async def gold_set(self, external_queue_id: str) -> dict[str, Any]:
        view = await self._repository.queue_view(
            external_queue_id,
            competitor_retailer_id=None,
            stratum=None,
            review_status=None,
            offset=0,
            limit=1_000_000,
        )
        labels: list[dict[str, Any]] = []
        for case in view["cases"]:
            if case["review_status"] not in {"approved", "rejected"}:
                continue
            decision = case["final_decision"]
            if decision is None:
                continue
            linked = set(decision.get("submission_ids", []))
            reviews = (
                [review for review in case["review_submissions"] if review["id"] in linked]
                if linked
                else [decision]
            )
            evidence_refs = sorted(
                {
                    *case["evidence_refs"],
                    *decision["evidence_refs"],
                    *(reference for review in reviews for reference in review["evidence_refs"]),
                }
            )
            legacy_adjudication = decision["source"] == "legacy_adjudication"
            labels.append(
                {
                    "case_id": case["case_id"],
                    "benchmark_listing_id": case["benchmark_listing_id"],
                    "competitor_listing_id": case["competitor_listing_id"],
                    "expected_comparable": decision["verdict"] == "comparable",
                    "allowed_tiers": list(decision["allowed_tiers"]),
                    "critical": case["critical"],
                    "stratum": case["stratum"],
                    "review_status": ("adjudicated" if legacy_adjudication else "single_reviewed"),
                    "reviewers": sorted(
                        {
                            str(review.get("reviewer_id") or review.get("adjudicator_id"))
                            for review in reviews
                        }
                    ),
                    "evidence_refs": evidence_refs,
                    "rationale": decision["rationale"],
                }
            )
        document = {
            "schema_version": "2.0.0",
            "gold_set_id": f"{external_queue_id}-gold-set",
            "version": view["queue"]["version"],
            "purpose": "release_certification",
            "product_pack": view["queue"]["product_pack"],
            "source_evidence": sorted(
                {reference for label in labels for reference in label["evidence_refs"]}
            ),
            "labels": labels,
        }
        if labels:
            validate_instance(
                self._root,
                "matching-v2-gold-set.schema.json",
                document,
                label="matching v2 certified gold set",
            )
        return document

    @staticmethod
    def _validate_tiers(verdict: ReviewVerdict, tiers: Sequence[MatchTier]) -> None:
        if verdict == "comparable" and not tiers:
            raise ValueError("a comparable verdict requires at least one allowed tier")
        if verdict != "comparable" and tiers:
            raise ValueError("a non-comparable or insufficient verdict cannot allow tiers")


def _require_review_access(request: Request, provided_token: str | None) -> None:
    enabled = _enabled(
        os.getenv("MATCHING_V2_REVIEW_API_ENABLED"),
        default=not request.app.state.settings.is_production,
    )
    if not enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Matching v2 human review is not enabled.",
        )
    expected = os.getenv("PRODUCT_PACK_ADMIN_TOKEN")
    if request.app.state.settings.is_production and (
        not expected or not provided_token or not secrets.compare_digest(expected, provided_token)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated administrator access is required.",
        )


def get_matching_v2_review_service(request: Request) -> MatchingV2ReviewService:
    return MatchingV2ReviewService(
        PostgresMatchingV2ReviewRepository(request.app.state.database_probe.engine),
        _repository_root(),
    )


MatchingV2ReviewServiceDependency = Annotated[
    MatchingV2ReviewService,
    Depends(get_matching_v2_review_service),
]
AdminToken = Annotated[str | None, Header(alias="X-RCI-Admin-Token")]


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, KeyError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


def _matching_ai_review_policy() -> dict[str, Any]:
    enabled = _enabled(os.getenv("MATCHING_V2_AI_REVIEW_ENABLED"))
    model_id = (
        os.getenv("OPENAI_MODEL_MATCHING_REVIEW") or os.getenv("OPENAI_MODEL_NARRATIVE") or ""
    ).strip()
    try:
        max_request_cost_usd = float(os.getenv("OPENAI_MATCHING_MAX_REQUEST_COST_USD", "0.35"))
    except ValueError:
        max_request_cost_usd = 0.35
    return {
        "enabled": enabled and bool(model_id),
        "model_id": model_id or None,
        "max_batch_cases": 25,
        "max_request_cost_usd": max_request_cost_usd,
        "vision_policy": "missing_or_conflicting_critical_evidence_only",
        "authoritative": False,
        "human_review_required": True,
    }


def _require_matching_ai_review() -> str:
    policy = _matching_ai_review_policy()
    if not _enabled(os.getenv("MATCHING_V2_AI_REVIEW_ENABLED")):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Matching v2 AI draft review is not enabled.",
        )
    model_id = str(policy["model_id"] or "")
    if not model_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No Matching v2 AI review model is configured.",
        )
    return model_id


@router.post("/review-queues/import", status_code=status.HTTP_201_CREATED)
async def import_matching_v2_review_queue(
    request: Request,
    body: ImportReviewQueueRequest,
    service: MatchingV2ReviewServiceDependency,
    x_rci_admin_token: AdminToken = None,
) -> dict[str, Any]:
    _require_review_access(request, x_rci_admin_token)
    try:
        return await service.import_queue(body)
    except (ContractError, KeyError, ValueError) as exc:
        raise _http_error(exc) from exc


@router.get("/review-queues")
async def list_matching_v2_review_queues(
    request: Request,
    service: MatchingV2ReviewServiceDependency,
    x_rci_admin_token: AdminToken = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    _require_review_access(request, x_rci_admin_token)
    return await service.list_queues(limit=limit)


@router.get("/review-queues/{queue_id}")
async def get_matching_v2_review_queue(
    queue_id: str,
    request: Request,
    service: MatchingV2ReviewServiceDependency,
    x_rci_admin_token: AdminToken = None,
    competitor_retailer_id: str | None = Query(default=None),
    stratum: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    _require_review_access(request, x_rci_admin_token)
    try:
        document = await service.queue_view(
            queue_id,
            competitor_retailer_id=competitor_retailer_id,
            stratum=stratum,
            review_status=review_status,
            offset=offset,
            limit=limit,
        )
        document["ai_review_policy"] = _matching_ai_review_policy()
        document["ai_bulk_certification_policy"] = _ai_bulk_certification_policy()
        return document
    except KeyError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/review-queues/{queue_id}/cases/{case_id}/submissions",
    status_code=status.HTTP_201_CREATED,
)
async def submit_matching_v2_review(
    queue_id: str,
    case_id: str,
    request: Request,
    body: ReviewSubmissionRequest,
    service: MatchingV2ReviewServiceDependency,
    x_rci_admin_token: AdminToken = None,
) -> dict[str, Any]:
    _require_review_access(request, x_rci_admin_token)
    try:
        return await service.submit_review(queue_id, case_id, body)
    except (KeyError, ValueError) as exc:
        raise _http_error(exc) from exc


@router.post(
    "/review-queues/{queue_id}/cases/{case_id}/ai-drafts",
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_matching_v2_ai_draft(
    queue_id: str,
    case_id: str,
    request: Request,
    body: AIReviewDraftRequest,
    service: MatchingV2ReviewServiceDependency,
    x_rci_admin_token: AdminToken = None,
) -> dict[str, Any]:
    _require_review_access(request, x_rci_admin_token)
    model_id = _require_matching_ai_review()
    try:
        return await service.request_ai_draft(
            queue_id,
            case_id,
            body,
            model_id=model_id,
        )
    except (ContractError, KeyError, OSError, ValueError) as exc:
        raise _http_error(exc) from exc


@router.post(
    "/review-queues/{queue_id}/ai-drafts",
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_matching_v2_ai_draft_batch(
    queue_id: str,
    request: Request,
    body: AIReviewBatchRequest,
    service: MatchingV2ReviewServiceDependency,
    x_rci_admin_token: AdminToken = None,
) -> dict[str, Any]:
    _require_review_access(request, x_rci_admin_token)
    model_id = _require_matching_ai_review()
    try:
        return await service.request_ai_drafts(queue_id, body, model_id=model_id)
    except (ContractError, KeyError, OSError, ValueError) as exc:
        raise _http_error(exc) from exc


@router.post("/review-queues/{queue_id}/ai-bulk-certification/preview")
async def preview_matching_v2_ai_bulk_certification(
    queue_id: str,
    request: Request,
    body: AIBulkCertificationPreviewRequest,
    service: MatchingV2ReviewServiceDependency,
    x_rci_admin_token: AdminToken = None,
) -> dict[str, Any]:
    _require_review_access(request, x_rci_admin_token)
    try:
        return await service.preview_ai_bulk_certification(queue_id, body)
    except (KeyError, ValueError) as exc:
        raise _http_error(exc) from exc


@router.post(
    "/review-queues/{queue_id}/ai-bulk-certification/commit",
    status_code=status.HTTP_201_CREATED,
)
async def commit_matching_v2_ai_bulk_certification(
    queue_id: str,
    request: Request,
    body: AIBulkCertificationCommitRequest,
    service: MatchingV2ReviewServiceDependency,
    x_rci_admin_token: AdminToken = None,
) -> dict[str, Any]:
    _require_review_access(request, x_rci_admin_token)
    try:
        return await service.commit_ai_bulk_certification(queue_id, body)
    except (KeyError, ValueError) as exc:
        raise _http_error(exc) from exc


@router.post(
    "/review-queues/{queue_id}/cases/{case_id}/adjudications",
    status_code=status.HTTP_201_CREATED,
)
async def adjudicate_matching_v2_review(
    queue_id: str,
    case_id: str,
    request: Request,
    body: AdjudicationRequest,
    service: MatchingV2ReviewServiceDependency,
    x_rci_admin_token: AdminToken = None,
) -> dict[str, Any]:
    _require_review_access(request, x_rci_admin_token)
    try:
        return await service.adjudicate(queue_id, case_id, body)
    except (KeyError, ValueError) as exc:
        raise _http_error(exc) from exc


@router.get("/review-queues/{queue_id}/gold-set")
async def export_matching_v2_gold_set(
    queue_id: str,
    request: Request,
    service: MatchingV2ReviewServiceDependency,
    x_rci_admin_token: AdminToken = None,
) -> dict[str, Any]:
    _require_review_access(request, x_rci_admin_token)
    try:
        return await service.gold_set(queue_id)
    except (ContractError, KeyError, ValueError) as exc:
        raise _http_error(exc) from exc
