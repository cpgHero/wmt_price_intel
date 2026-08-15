"""Authenticated human review and adjudication API for Matching v2."""

from __future__ import annotations

import hashlib
import json
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
    queue: dict[str, Any]


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
        documents = self._case_documents(cases, submissions, adjudications)
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
            "status_counts": dict(sorted(summary_counts.items())),
            "total_cases": total_cases,
            "selected_case_count": len(documents),
            "offset": offset,
            "limit": limit,
            "cases": documents[offset : offset + limit],
        }

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
                      AND (:competitor_retailer_id IS NULL
                           OR competitor_retailer_id = :competitor_retailer_id)
                      AND (:stratum IS NULL OR stratum = :stratum)
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
                    SELECT DISTINCT ON (review_case_id, reviewer_id)
                           id::text, review_case_id::text, reviewer_id, verdict,
                           allowed_tiers, rationale, evidence_refs,
                           submission_checksum, supersedes_submission_id::text, created_at
                    FROM matching_v2_review_submission
                    WHERE review_case_id = ANY(CAST(:case_ids AS uuid[]))
                    ORDER BY review_case_id, reviewer_id, created_at DESC, id DESC
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
    def _case_documents(
        cases: Sequence[Mapping[str, Any]],
        submissions: Sequence[Mapping[str, Any]],
        adjudications: Sequence[Mapping[str, Any]],
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
        output: list[dict[str, Any]] = []
        for row in cases:
            case_id = str(row["id"])
            reviews = submissions_by_case.get(case_id, [])
            adjudication = adjudication_by_case.get(case_id)
            if adjudication is not None:
                review_status = "adjudicated"
            elif len({str(review["reviewer_id"]) for review in reviews}) >= 2:
                review_status = "ready_for_adjudication"
            elif reviews:
                review_status = "in_review"
            else:
                review_status = "pending"
            output.append(
                {
                    **dict(row["case_document"]),
                    "database_id": case_id,
                    "review_status": review_status,
                    "review_submissions": reviews,
                    "adjudication": adjudication,
                }
            )
        return output

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
            finalized = await connection.scalar(
                text(
                    """
                    SELECT EXISTS (
                      SELECT 1 FROM matching_v2_adjudication
                      WHERE review_case_id = CAST(:case_id AS uuid)
                    )
                    """
                ),
                {"case_id": case_id},
            )
            if finalized:
                raise ValueError("an adjudicated review case cannot accept new submissions")
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
                                  AND reviewer_id = :reviewer_id
                                """
                            ),
                            {
                                "submission_id": supersedes_submission_id,
                                "case_id": case_id,
                                "reviewer_id": submission["reviewer_id"],
                            },
                        )
                    )
                    .mappings()
                    .first()
                )
                if superseded is None:
                    raise ValueError(
                        "a superseded review must belong to the same case and reviewer"
                    )
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
                    SELECT id::text
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
        try:
            validate_instance(
                self._root,
                "matching-v2-review-queue.schema.json",
                request.queue,
                label="matching v2 review queue import",
            )
        except ContractError as exc:
            raise ValueError(str(exc)) from exc
        expected_checksum = str(request.queue["checksum"])
        unsigned = dict(request.queue)
        unsigned.pop("checksum", None)
        if _checksum(unsigned) != expected_checksum:
            raise ValueError("review queue checksum does not match its canonical document")
        return await self._repository.import_queue(
            request.organization_id,
            request.queue,
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
            review_status="adjudicated",
            offset=0,
            limit=1_000_000,
        )
        labels: list[dict[str, Any]] = []
        for case in view["cases"]:
            adjudication = case["adjudication"]
            if adjudication["verdict"] == "insufficient_evidence":
                continue
            linked = set(adjudication["submission_ids"])
            reviews = [review for review in case["review_submissions"] if review["id"] in linked]
            evidence_refs = sorted(
                {
                    *case["evidence_refs"],
                    *adjudication["evidence_refs"],
                    *(reference for review in reviews for reference in review["evidence_refs"]),
                }
            )
            labels.append(
                {
                    "case_id": case["case_id"],
                    "benchmark_listing_id": case["benchmark_listing_id"],
                    "competitor_listing_id": case["competitor_listing_id"],
                    "expected_comparable": adjudication["verdict"] == "comparable",
                    "allowed_tiers": list(adjudication["allowed_tiers"]),
                    "critical": case["critical"],
                    "stratum": case["stratum"],
                    "review_status": "adjudicated",
                    "reviewers": sorted({str(review["reviewer_id"]) for review in reviews}),
                    "evidence_refs": evidence_refs,
                    "rationale": adjudication["rationale"],
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
                label="matching v2 adjudicated gold set",
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
        return await service.queue_view(
            queue_id,
            competitor_retailer_id=competitor_retailer_id,
            stratum=stratum,
            review_status=review_status,
            offset=offset,
            limit=limit,
        )
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
