"""Persistent one-to-one product-match decisions and review projections."""

from __future__ import annotations

import asyncio
import copy
import json
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncEngine

from rci_results.models import AnalysisRecord, JsonObject
from rci_results.repository import DEFAULT_ORGANIZATION_ID
from rci_results.service import AnalysisResultService


class MatchRevisionConflictError(RuntimeError):
    pass


class MatchOneToOneConflictError(RuntimeError):
    def __init__(self, conflicts: list[JsonObject]) -> None:
        super().__init__("the selected product already has a confirmed match")
        self.conflicts = conflicts


@dataclass(frozen=True, slots=True)
class MatchRevisionRecord:
    id: str
    organization_id: str
    product_pack_id: str
    product_pack_version: str
    benchmark_retailer_id: str
    source_analysis_result_id: str
    revision: int
    status: str
    created_by: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class MatchRuleRecord:
    id: str
    revision_id: str
    competitor_retailer_id: str
    source_profile_id: str
    eligible_profile_ids: tuple[str, ...]
    benchmark_product_id: str
    competitor_product_id: str
    decision: str
    origin: str
    reason: str | None
    benchmark_snapshot: JsonObject
    competitor_snapshot: JsonObject
    created_at: datetime


@dataclass(frozen=True, slots=True)
class MatchReanalysisRecord:
    analysis_run_id: str
    source_analysis_id: str
    match_revision_id: str
    status: str
    applied_to_future_runs: bool


@dataclass(frozen=True, slots=True)
class MatchDecisionCommand:
    expected_revision: int
    competitor_retailer_id: str
    profile_id: str
    benchmark_product_id: str
    competitor_product_id: str
    decision: str
    replace_conflicts: bool = False
    reason: str | None = None
    eligible_profile_ids: tuple[str, ...] = ()


class MatchReviewRepository(Protocol):
    async def latest_revision(
        self,
        *,
        product_pack_id: str,
        product_pack_version: str,
        benchmark_retailer_id: str,
    ) -> MatchRevisionRecord | None: ...

    async def rules(self, revision_id: str) -> list[MatchRuleRecord]: ...

    async def future_revision(
        self,
        *,
        product_pack_id: str,
        product_pack_version: str,
        benchmark_retailer_id: str,
    ) -> MatchRevisionRecord | None: ...

    async def save_decision(
        self,
        analysis: AnalysisRecord,
        *,
        benchmark_retailer_id: str,
        command: MatchDecisionCommand,
        benchmark_snapshot: JsonObject,
        competitor_snapshot: JsonObject,
        actor: str,
    ) -> MatchRevisionRecord: ...

    async def enqueue_reanalysis(
        self,
        analysis: AnalysisRecord,
        revision: MatchRevisionRecord,
        *,
        apply_to_future_runs: bool,
        actor: str,
    ) -> MatchReanalysisRecord: ...


def _revision(row: RowMapping | dict[str, Any]) -> MatchRevisionRecord:
    return MatchRevisionRecord(
        id=str(row["id"]),
        organization_id=str(row["organization_id"]),
        product_pack_id=str(row["product_pack_id"]),
        product_pack_version=str(row["product_pack_version"]),
        benchmark_retailer_id=str(row["benchmark_retailer_id"]),
        source_analysis_result_id=str(row["source_analysis_result_id"]),
        revision=int(row["revision"]),
        status=str(row["status"]),
        created_by=str(row["created_by"]),
        created_at=row["created_at"],
    )


def _rule(row: RowMapping | dict[str, Any]) -> MatchRuleRecord:
    return MatchRuleRecord(
        id=str(row["id"]),
        revision_id=str(row["revision_id"]),
        competitor_retailer_id=str(row["competitor_retailer_id"]),
        source_profile_id=str(row["profile_id"]),
        eligible_profile_ids=tuple(str(value) for value in row["eligible_profile_ids"]),
        benchmark_product_id=str(row["benchmark_product_id"]),
        competitor_product_id=str(row["competitor_product_id"]),
        decision=str(row["decision"]),
        origin=str(row["origin"]),
        reason=str(row["reason"]) if row.get("reason") is not None else None,
        benchmark_snapshot=dict(row["benchmark_snapshot"]),
        competitor_snapshot=dict(row["competitor_snapshot"]),
        created_at=row["created_at"],
    )


class PostgresMatchReviewRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def latest_revision(
        self,
        *,
        product_pack_id: str,
        product_pack_version: str,
        benchmark_retailer_id: str,
    ) -> MatchRevisionRecord | None:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT * FROM product_match_revision
                            WHERE organization_id = CAST(:organization_id AS uuid)
                              AND product_pack_id = :product_pack_id
                              AND product_pack_version = :product_pack_version
                              AND benchmark_retailer_id = :benchmark_retailer_id
                              AND status = 'current'
                            """
                        ),
                        {
                            "organization_id": DEFAULT_ORGANIZATION_ID,
                            "product_pack_id": product_pack_id,
                            "product_pack_version": product_pack_version,
                            "benchmark_retailer_id": benchmark_retailer_id,
                        },
                    )
                )
                .mappings()
                .first()
            )
        return _revision(row) if row is not None else None

    async def rules(self, revision_id: str) -> list[MatchRuleRecord]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        SELECT * FROM product_match_rule
                        WHERE revision_id = CAST(:revision_id AS uuid)
                        ORDER BY competitor_retailer_id, profile_id,
                          benchmark_product_id, competitor_product_id
                        """
                    ),
                    {"revision_id": revision_id},
                )
            ).mappings()
            return [_rule(row) for row in rows]

    async def future_revision(
        self,
        *,
        product_pack_id: str,
        product_pack_version: str,
        benchmark_retailer_id: str,
    ) -> MatchRevisionRecord | None:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT revision.*
                            FROM product_match_application_policy policy
                            JOIN product_match_revision revision
                              ON revision.id = policy.revision_id
                            WHERE policy.organization_id = CAST(:organization_id AS uuid)
                              AND policy.product_pack_id = :product_pack_id
                              AND policy.product_pack_version = :product_pack_version
                              AND policy.benchmark_retailer_id = :benchmark_retailer_id
                            """
                        ),
                        {
                            "organization_id": DEFAULT_ORGANIZATION_ID,
                            "product_pack_id": product_pack_id,
                            "product_pack_version": product_pack_version,
                            "benchmark_retailer_id": benchmark_retailer_id,
                        },
                    )
                )
                .mappings()
                .first()
            )
        return _revision(row) if row is not None else None

    async def save_decision(
        self,
        analysis: AnalysisRecord,
        *,
        benchmark_retailer_id: str,
        command: MatchDecisionCommand,
        benchmark_snapshot: JsonObject,
        competitor_snapshot: JsonObject,
        actor: str,
    ) -> MatchRevisionRecord:
        scope_key = "|".join(
            (
                DEFAULT_ORGANIZATION_ID,
                analysis.product_pack_id,
                analysis.product_pack_version,
                benchmark_retailer_id,
            )
        )
        async with self._engine.begin() as connection:
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:scope_key, 0))"),
                {"scope_key": scope_key},
            )
            current_row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT * FROM product_match_revision
                            WHERE organization_id = CAST(:organization_id AS uuid)
                              AND product_pack_id = :product_pack_id
                              AND product_pack_version = :product_pack_version
                              AND benchmark_retailer_id = :benchmark_retailer_id
                              AND status = 'current'
                            FOR UPDATE
                            """
                        ),
                        {
                            "organization_id": DEFAULT_ORGANIZATION_ID,
                            "product_pack_id": analysis.product_pack_id,
                            "product_pack_version": analysis.product_pack_version,
                            "benchmark_retailer_id": benchmark_retailer_id,
                        },
                    )
                )
                .mappings()
                .first()
            )
            current_revision = int(current_row["revision"]) if current_row is not None else 0
            if command.expected_revision != current_revision:
                raise MatchRevisionConflictError(
                    f"expected revision {command.expected_revision}, current revision is "
                    f"{current_revision}"
                )
            existing_rows = []
            if current_row is not None:
                existing_rows = [
                    dict(row)
                    for row in (
                        await connection.execute(
                            text(
                                "SELECT * FROM product_match_rule "
                                "WHERE revision_id = CAST(:revision_id AS uuid)"
                            ),
                            {"revision_id": str(current_row["id"])},
                        )
                    )
                    .mappings()
                    .all()
                ]
            next_rows = self._apply_command(existing_rows, command)
            if current_row is not None:
                await connection.execute(
                    text(
                        "UPDATE product_match_revision SET status = 'superseded' "
                        "WHERE id = CAST(:revision_id AS uuid)"
                    ),
                    {"revision_id": str(current_row["id"])},
                )
            revision_row = (
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO product_match_revision (
                              organization_id, product_pack_id, product_pack_version,
                              benchmark_retailer_id, source_analysis_result_id,
                              revision, status, created_by
                            ) VALUES (
                              CAST(:organization_id AS uuid), :product_pack_id,
                              :product_pack_version, :benchmark_retailer_id,
                              CAST(:source_analysis_result_id AS uuid), :revision,
                              'current', :created_by
                            ) RETURNING *
                            """
                        ),
                        {
                            "organization_id": DEFAULT_ORGANIZATION_ID,
                            "product_pack_id": analysis.product_pack_id,
                            "product_pack_version": analysis.product_pack_version,
                            "benchmark_retailer_id": benchmark_retailer_id,
                            "source_analysis_result_id": analysis.id,
                            "revision": current_revision + 1,
                            "created_by": actor,
                        },
                    )
                )
                .mappings()
                .one()
            )
            revision_id = str(revision_row["id"])
            for row in next_rows:
                is_target = (
                    str(row["competitor_retailer_id"]) == command.competitor_retailer_id
                    and str(row["benchmark_product_id"]) == command.benchmark_product_id
                    and str(row["competitor_product_id"]) == command.competitor_product_id
                )
                await connection.execute(
                    text(
                        """
                        INSERT INTO product_match_rule (
                          revision_id, competitor_retailer_id, profile_id,
                          eligible_profile_ids,
                          benchmark_product_id, competitor_product_id, decision,
                          origin, reason, benchmark_snapshot, competitor_snapshot
                        ) VALUES (
                          CAST(:revision_id AS uuid), :competitor_retailer_id,
                          :profile_id, CAST(:eligible_profile_ids AS text[]),
                          :benchmark_product_id, :competitor_product_id, :decision,
                          :origin, :reason, CAST(:benchmark_snapshot AS jsonb),
                          CAST(:competitor_snapshot AS jsonb)
                        )
                        """
                    ),
                    {
                        "revision_id": revision_id,
                        "competitor_retailer_id": str(row["competitor_retailer_id"]),
                        "profile_id": str(row.get("source_profile_id") or row.get("profile_id")),
                        "eligible_profile_ids": list(row["eligible_profile_ids"]),
                        "benchmark_product_id": str(row["benchmark_product_id"]),
                        "competitor_product_id": str(row["competitor_product_id"]),
                        "decision": str(row["decision"]),
                        "origin": str(row.get("origin") or "user"),
                        "reason": command.reason if is_target else row.get("reason"),
                        "benchmark_snapshot": json.dumps(
                            benchmark_snapshot if is_target else row.get("benchmark_snapshot", {})
                        ),
                        "competitor_snapshot": json.dumps(
                            competitor_snapshot if is_target else row.get("competitor_snapshot", {})
                        ),
                    },
                )
            details = {
                **asdict(command),
                "previous_revision": current_revision,
                "revision": current_revision + 1,
            }
            await connection.execute(
                text(
                    """
                    INSERT INTO product_match_review_event (
                      revision_id, event_type, actor, details
                    ) VALUES (
                      CAST(:revision_id AS uuid), :event_type, :actor,
                      CAST(:details AS jsonb)
                    )
                    """
                ),
                {
                    "revision_id": revision_id,
                    "event_type": f"match_{command.decision}",
                    "actor": actor,
                    "details": json.dumps(details, sort_keys=True),
                },
            )
            return _revision(revision_row)

    @staticmethod
    def _apply_command(
        existing: list[dict[str, Any]], command: MatchDecisionCommand
    ) -> list[dict[str, Any]]:
        def target(row: dict[str, Any]) -> bool:
            return (
                str(row["competitor_retailer_id"]) == command.competitor_retailer_id
                and str(row["benchmark_product_id"]) == command.benchmark_product_id
                and str(row["competitor_product_id"]) == command.competitor_product_id
            )

        remaining = [row for row in existing if not target(row)]
        if command.decision == "reset":
            return remaining
        if command.decision not in {"confirmed", "rejected"}:
            raise ValueError(f"unsupported product-match decision {command.decision!r}")
        if command.decision == "confirmed":
            conflicts = [
                row
                for row in remaining
                if str(row["decision"]) == "confirmed"
                and str(row["competitor_retailer_id"]) == command.competitor_retailer_id
                and (
                    str(row["benchmark_product_id"]) == command.benchmark_product_id
                    or str(row["competitor_product_id"]) == command.competitor_product_id
                )
            ]
            if conflicts and not command.replace_conflicts:
                raise MatchOneToOneConflictError(
                    [
                        {
                            "benchmark_product_id": str(row["benchmark_product_id"]),
                            "competitor_product_id": str(row["competitor_product_id"]),
                        }
                        for row in conflicts
                    ]
                )
            conflict_ids = {str(row["id"]) for row in conflicts}
            remaining = [row for row in remaining if str(row.get("id")) not in conflict_ids]
        return [
            *remaining,
            {
                "id": str(uuid4()),
                "competitor_retailer_id": command.competitor_retailer_id,
                "source_profile_id": command.profile_id,
                "eligible_profile_ids": list(command.eligible_profile_ids or (command.profile_id,)),
                "benchmark_product_id": command.benchmark_product_id,
                "competitor_product_id": command.competitor_product_id,
                "decision": command.decision,
                "origin": "user",
                "reason": command.reason,
                "benchmark_snapshot": {},
                "competitor_snapshot": {},
            },
        ]

    async def enqueue_reanalysis(
        self,
        analysis: AnalysisRecord,
        revision: MatchRevisionRecord,
        *,
        apply_to_future_runs: bool,
        actor: str,
    ) -> MatchReanalysisRecord:
        async with self._engine.begin() as connection:
            if apply_to_future_runs:
                await connection.execute(
                    text(
                        """
                        INSERT INTO product_match_application_policy (
                          organization_id, product_pack_id, product_pack_version,
                          benchmark_retailer_id, revision_id, updated_by
                        ) VALUES (
                          CAST(:organization_id AS uuid), :product_pack_id,
                          :product_pack_version, :benchmark_retailer_id,
                          CAST(:revision_id AS uuid), :updated_by
                        )
                        ON CONFLICT (
                          organization_id, product_pack_id, product_pack_version,
                          benchmark_retailer_id
                        ) DO UPDATE SET revision_id = EXCLUDED.revision_id,
                          updated_by = EXCLUDED.updated_by, updated_at = now()
                        """
                    ),
                    {
                        "organization_id": revision.organization_id,
                        "product_pack_id": revision.product_pack_id,
                        "product_pack_version": revision.product_pack_version,
                        "benchmark_retailer_id": revision.benchmark_retailer_id,
                        "revision_id": revision.id,
                        "updated_by": actor,
                    },
                )
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO analysis_run (
                              collection_run_id, input_set_id, product_pack_id,
                              product_pack_version, status, code_version, max_attempts,
                              match_revision_id, source_analysis_result_id
                            )
                            SELECT ar.collection_run_id, ar.input_set_id, ar.product_pack_id,
                              ar.product_pack_version, 'queued', ar.code_version, ar.max_attempts,
                              CAST(:match_revision_id AS uuid),
                              CAST(:source_analysis_result_id AS uuid)
                            FROM analysis_run ar
                            WHERE ar.id = CAST(:source_analysis_run_id AS uuid)
                            ON CONFLICT ON CONSTRAINT analysis_run_collection_pack_match_revision_uq
                            DO UPDATE SET available_at = LEAST(analysis_run.available_at, now())
                            RETURNING id::text, status
                            """
                        ),
                        {
                            "match_revision_id": revision.id,
                            "source_analysis_result_id": analysis.id,
                            "source_analysis_run_id": analysis.analysis_run_id,
                        },
                    )
                )
                .mappings()
                .one()
            )
            return MatchReanalysisRecord(
                analysis_run_id=str(row["id"]),
                source_analysis_id=analysis.analysis_id,
                match_revision_id=revision.id,
                status=str(row["status"]),
                applied_to_future_runs=apply_to_future_runs,
            )


class InMemoryMatchReviewRepository:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._revisions: list[MatchRevisionRecord] = []
        self._rules: dict[str, list[MatchRuleRecord]] = {}
        self._future_revision_ids: dict[tuple[str, str, str], str] = {}

    async def latest_revision(
        self,
        *,
        product_pack_id: str,
        product_pack_version: str,
        benchmark_retailer_id: str,
    ) -> MatchRevisionRecord | None:
        async with self._lock:
            candidates = [
                revision
                for revision in self._revisions
                if revision.product_pack_id == product_pack_id
                and revision.product_pack_version == product_pack_version
                and revision.benchmark_retailer_id == benchmark_retailer_id
                and revision.status == "current"
            ]
            return copy.deepcopy(candidates[-1]) if candidates else None

    async def rules(self, revision_id: str) -> list[MatchRuleRecord]:
        async with self._lock:
            return copy.deepcopy(self._rules.get(revision_id, []))

    async def future_revision(
        self,
        *,
        product_pack_id: str,
        product_pack_version: str,
        benchmark_retailer_id: str,
    ) -> MatchRevisionRecord | None:
        async with self._lock:
            revision_id = self._future_revision_ids.get(
                (product_pack_id, product_pack_version, benchmark_retailer_id)
            )
            revision = next((row for row in self._revisions if row.id == revision_id), None)
            return copy.deepcopy(revision)

    async def save_decision(
        self,
        analysis: AnalysisRecord,
        *,
        benchmark_retailer_id: str,
        command: MatchDecisionCommand,
        benchmark_snapshot: JsonObject,
        competitor_snapshot: JsonObject,
        actor: str,
    ) -> MatchRevisionRecord:
        async with self._lock:
            current = next(
                (
                    revision
                    for revision in reversed(self._revisions)
                    if revision.product_pack_id == analysis.product_pack_id
                    and revision.product_pack_version == analysis.product_pack_version
                    and revision.benchmark_retailer_id == benchmark_retailer_id
                    and revision.status == "current"
                ),
                None,
            )
            current_number = current.revision if current is not None else 0
            if command.expected_revision != current_number:
                raise MatchRevisionConflictError(
                    f"expected revision {command.expected_revision}, current revision is "
                    f"{current_number}"
                )
            source_rows = (
                [asdict(row) for row in self._rules.get(current.id, [])] if current else []
            )
            next_rows = PostgresMatchReviewRepository._apply_command(source_rows, command)
            if current is not None:
                self._revisions[self._revisions.index(current)] = MatchRevisionRecord(
                    **{**asdict(current), "status": "superseded"}
                )
            now = datetime.now(UTC)
            revision = MatchRevisionRecord(
                id=str(uuid4()),
                organization_id=DEFAULT_ORGANIZATION_ID,
                product_pack_id=analysis.product_pack_id,
                product_pack_version=analysis.product_pack_version,
                benchmark_retailer_id=benchmark_retailer_id,
                source_analysis_result_id=analysis.id,
                revision=current_number + 1,
                status="current",
                created_by=actor,
                created_at=now,
            )
            self._revisions.append(revision)
            self._rules[revision.id] = [
                MatchRuleRecord(
                    id=str(row.get("id") or uuid4()),
                    revision_id=revision.id,
                    competitor_retailer_id=str(row["competitor_retailer_id"]),
                    source_profile_id=str(row["source_profile_id"]),
                    eligible_profile_ids=tuple(str(value) for value in row["eligible_profile_ids"]),
                    benchmark_product_id=str(row["benchmark_product_id"]),
                    competitor_product_id=str(row["competitor_product_id"]),
                    decision=str(row["decision"]),
                    origin=str(row.get("origin") or "user"),
                    reason=(str(row["reason"]) if row.get("reason") is not None else None),
                    benchmark_snapshot=(
                        copy.deepcopy(benchmark_snapshot)
                        if str(row["benchmark_product_id"]) == command.benchmark_product_id
                        and str(row["competitor_product_id"]) == command.competitor_product_id
                        else copy.deepcopy(row.get("benchmark_snapshot", {}))
                    ),
                    competitor_snapshot=(
                        copy.deepcopy(competitor_snapshot)
                        if str(row["benchmark_product_id"]) == command.benchmark_product_id
                        and str(row["competitor_product_id"]) == command.competitor_product_id
                        else copy.deepcopy(row.get("competitor_snapshot", {}))
                    ),
                    created_at=now,
                )
                for row in next_rows
            ]
            return copy.deepcopy(revision)

    async def enqueue_reanalysis(
        self,
        analysis: AnalysisRecord,
        revision: MatchRevisionRecord,
        *,
        apply_to_future_runs: bool,
        actor: str,
    ) -> MatchReanalysisRecord:
        del actor
        if apply_to_future_runs:
            async with self._lock:
                self._future_revision_ids[
                    (
                        revision.product_pack_id,
                        revision.product_pack_version,
                        revision.benchmark_retailer_id,
                    )
                ] = revision.id
        return MatchReanalysisRecord(
            analysis_run_id=str(uuid4()),
            source_analysis_id=analysis.analysis_id,
            match_revision_id=revision.id,
            status="queued",
            applied_to_future_runs=apply_to_future_runs,
        )


class MatchReviewService:
    def __init__(
        self,
        results: AnalysisResultService,
        repository: MatchReviewRepository,
        *,
        retailer_names: dict[str, str] | None = None,
    ) -> None:
        self._results = results
        self._repository = repository
        self._retailer_names = dict(retailer_names or {})

    async def view(self, analysis_id: str) -> JsonObject:
        analysis = await self._results.get(analysis_id)
        publication = await self._results.latest_publication(analysis.analysis_id)
        document = publication.result if publication is not None else analysis.result
        context = publication.presentation_context if publication is not None else {}
        benchmark = str(document["benchmark_retailer"])
        competitors = [str(value) for value in document.get("competitors", [])]
        revision = await self._repository.latest_revision(
            product_pack_id=analysis.product_pack_id,
            product_pack_version=analysis.product_pack_version,
            benchmark_retailer_id=benchmark,
        )
        future_revision = await self._repository.future_revision(
            product_pack_id=analysis.product_pack_id,
            product_pack_version=analysis.product_pack_version,
            benchmark_retailer_id=benchmark,
        )
        rules = await self._repository.rules(revision.id) if revision is not None else []
        profiles = self._profiles(document)
        products = self._products(context, benchmark, competitors, rules)
        connections = self._connections(
            context,
            rules,
            default_profile_id=(profiles[0]["id"] if profiles else "strict"),
            profile_ids={str(profile["id"]) for profile in profiles},
        )
        for product in products:
            participation: list[JsonObject] = []
            for connection in connections:
                is_benchmark = str(product["retailer_id"]) == benchmark and str(
                    product["product_id"]
                ) == str(connection["benchmark_product_id"])
                is_competitor = str(product["retailer_id"]) == str(
                    connection["competitor_retailer_id"]
                ) and str(product["product_id"]) == str(connection["competitor_product_id"])
                if not (is_benchmark or is_competitor):
                    continue
                participation.extend(
                    {
                        "profile_id": str(profile_id),
                        "status": str(connection["status"]),
                    }
                    for profile_id in connection.get("eligible_profile_ids", [])
                )
            product["other_lens_participation"] = sorted(
                participation,
                key=lambda row: (str(row["profile_id"]), str(row["status"])),
            )
        connected = {
            (connection["competitor_retailer_id"], connection["competitor_product_id"])
            for connection in connections
            if connection["status"] != "rejected"
        } | {
            (benchmark, connection["benchmark_product_id"])
            for connection in connections
            if connection["status"] != "rejected"
        }
        summary = {
            status: sum(connection["status"] == status for connection in connections)
            for status in ("suggested", "confirmed", "rejected", "ambiguous")
        }
        summary["unmatched"] = sum(
            (product["retailer_id"], product["product_id"]) not in connected for product in products
        )
        return {
            "analysis_id": analysis.analysis_id,
            "product_pack_id": analysis.product_pack_id,
            "product_pack_version": analysis.product_pack_version,
            "revision_id": revision.id if revision is not None else None,
            "revision": revision.revision if revision is not None else 0,
            "current_publication_revision_id": (
                document.get("source", {}).get("match_revision_id")
                if isinstance(document.get("source"), dict)
                else None
            ),
            "staged_revision_id": (
                revision.id
                if revision is not None
                and revision.id
                != (
                    document.get("source", {}).get("match_revision_id")
                    if isinstance(document.get("source"), dict)
                    else None
                )
                else None
            ),
            "future_application": (
                {
                    "revision_id": future_revision.id,
                    "revision": future_revision.revision,
                }
                if future_revision is not None
                else None
            ),
            "benchmark_retailer": {
                "id": benchmark,
                "name": self._retailer_names.get(benchmark, benchmark.replace("_", " ").title()),
            },
            "competitors": [
                {
                    "id": competitor,
                    "name": self._retailer_names.get(
                        competitor, competitor.replace("_", " ").title()
                    ),
                }
                for competitor in competitors
            ],
            "profiles": profiles,
            "products": products,
            "connections": connections,
            "summary": summary,
        }

    async def decide(
        self,
        analysis_id: str,
        command: MatchDecisionCommand,
        *,
        actor: str,
    ) -> JsonObject:
        view = await self.view(analysis_id)
        competitor_ids = {str(row["id"]) for row in view["competitors"]}
        profile_ids = {str(row["id"]) for row in view["profiles"]}
        if command.competitor_retailer_id not in competitor_ids:
            raise ValueError("competitor retailer is not part of this analysis")
        if command.profile_id not in profile_ids:
            raise ValueError("comparison profile is not reviewable")
        products = {
            (str(row["retailer_id"]), str(row["product_id"])): dict(row) for row in view["products"]
        }
        benchmark_id = str(view["benchmark_retailer"]["id"])
        benchmark_key = (benchmark_id, command.benchmark_product_id)
        competitor_key = (command.competitor_retailer_id, command.competitor_product_id)
        if benchmark_key not in products or competitor_key not in products:
            raise ValueError("both products must be present in the analysis product catalog")
        connection = next(
            (
                row
                for row in view["connections"]
                if str(row["competitor_retailer_id"]) == command.competitor_retailer_id
                and str(row["benchmark_product_id"]) == command.benchmark_product_id
                and str(row["competitor_product_id"]) == command.competitor_product_id
            ),
            None,
        )
        eligible_profile_ids = tuple(
            sorted(
                {
                    command.profile_id,
                    *(
                        str(value)
                        for value in (
                            connection.get("eligible_profile_ids", [])
                            if isinstance(connection, dict)
                            else []
                        )
                        if str(value) in profile_ids
                    ),
                }
            )
        )
        effective_command = replace(
            command,
            eligible_profile_ids=eligible_profile_ids,
        )
        analysis = await self._results.get(analysis_id)
        revision = await self._repository.save_decision(
            analysis,
            benchmark_retailer_id=benchmark_id,
            command=effective_command,
            benchmark_snapshot=products[benchmark_key],
            competitor_snapshot=products[competitor_key],
            actor=actor,
        )
        return {"revision_id": revision.id, "revision": revision.revision, "status": "saved"}

    async def recompute(
        self,
        analysis_id: str,
        *,
        expected_revision: int,
        apply_to_future_runs: bool,
        actor: str,
    ) -> MatchReanalysisRecord:
        analysis = await self._results.get(analysis_id)
        benchmark = str(analysis.result["benchmark_retailer"])
        revision = await self._repository.latest_revision(
            product_pack_id=analysis.product_pack_id,
            product_pack_version=analysis.product_pack_version,
            benchmark_retailer_id=benchmark,
        )
        if revision is None:
            raise ValueError("save at least one match decision before reanalysis")
        if revision.revision != expected_revision:
            raise MatchRevisionConflictError(
                f"expected revision {expected_revision}, current revision is {revision.revision}"
            )
        return await self._repository.enqueue_reanalysis(
            analysis,
            revision,
            apply_to_future_runs=apply_to_future_runs,
            actor=actor,
        )

    @staticmethod
    def _profiles(document: JsonObject) -> list[JsonObject]:
        return [
            {
                "id": str(row["profile_id"]),
                "label": str(row["label"]),
                "geography": str(row["geography"]),
                "comparison_metric": str(row["comparison_metric"]),
            }
            for row in document.get("comparison_modes", [])
            if isinstance(row, dict) and str(row.get("geography")) == "exact_zip"
        ]

    @staticmethod
    def _products(
        context: JsonObject,
        benchmark: str,
        competitors: list[str],
        rules: list[MatchRuleRecord],
    ) -> list[JsonObject]:
        products: dict[tuple[str, str], JsonObject] = {}
        allowed = {benchmark, *competitors}
        for row in context.get("product_highlights", []):
            if not isinstance(row, dict):
                continue
            canonical = str(row.get("canonical_product_id") or "")
            retailer = str(row.get("retailer") or canonical.partition(":")[0])
            product_id = canonical.partition(":")[2]
            if retailer not in allowed or not product_id:
                continue
            products[(retailer, product_id)] = {
                **dict(row),
                "retailer_id": retailer,
                "product_id": product_id,
                "canonical_product_id": f"{retailer}:{product_id}",
                "name": str(row.get("name") or product_id),
            }
        candidate_rows = context.get("match_candidates", context.get("product_decisions", [])) or []
        for row in candidate_rows:
            if not isinstance(row, dict):
                continue
            for prefix, retailer in (
                ("benchmark", benchmark),
                ("competitor", str(row.get("competitor") or "")),
            ):
                product_id = str(row.get(f"{prefix}_product_id") or "")
                if retailer not in allowed or not product_id:
                    continue
                products.setdefault(
                    (retailer, product_id),
                    {
                        "retailer_id": retailer,
                        "product_id": product_id,
                        "canonical_product_id": f"{retailer}:{product_id}",
                        "name": str(row.get(f"{prefix}_product_name") or product_id),
                        "image_url": row.get(f"{prefix}_image_url"),
                        "url": row.get(f"{prefix}_product_url"),
                        "brand": row.get(f"{prefix}_brand"),
                        "price": row.get(f"median_{prefix}_price"),
                    },
                )
        for rule in rules:
            for retailer, product_id, snapshot in (
                (benchmark, rule.benchmark_product_id, rule.benchmark_snapshot),
                (
                    rule.competitor_retailer_id,
                    rule.competitor_product_id,
                    rule.competitor_snapshot,
                ),
            ):
                if retailer not in allowed or not product_id:
                    continue
                products.setdefault(
                    (retailer, product_id),
                    {
                        **dict(snapshot),
                        "retailer_id": retailer,
                        "product_id": product_id,
                        "canonical_product_id": f"{retailer}:{product_id}",
                        "name": str(snapshot.get("name") or product_id),
                    },
                )
        return sorted(
            products.values(),
            key=lambda row: (str(row["retailer_id"]), str(row["name"]), str(row["product_id"])),
        )

    @staticmethod
    def _connections(
        context: JsonObject,
        rules: list[MatchRuleRecord],
        *,
        default_profile_id: str,
        profile_ids: set[str],
    ) -> list[JsonObject]:
        persisted = {
            (
                rule.competitor_retailer_id,
                rule.benchmark_product_id,
                rule.competitor_product_id,
            ): rule
            for rule in rules
        }
        connections: dict[tuple[str, str, str], JsonObject] = {}
        candidate_rows = context.get("match_candidates", context.get("product_decisions", [])) or []
        for row in candidate_rows:
            if not isinstance(row, dict):
                continue
            key = (
                str(row.get("competitor") or ""),
                str(row.get("benchmark_product_id") or ""),
                str(row.get("competitor_product_id") or ""),
            )
            if not all(key):
                continue
            candidate_status = str(row.get("relationship_status") or "suggested")
            if candidate_status == "unmatched":
                continue
            candidate_profile_id = str(row.get("profile_id") or default_profile_id)
            if candidate_profile_id not in profile_ids:
                continue
            connection = connections.setdefault(
                key,
                {
                    "id": str(row.get("relationship_id") or row.get("id") or "automatic"),
                    "relationship_id": row.get("relationship_id"),
                    "candidate_group_id": row.get("candidate_group_id"),
                    "competitor_retailer_id": key[0],
                    "source_profile_id": candidate_profile_id,
                    "eligible_profile_ids": [],
                    "benchmark_product_id": key[1],
                    "competitor_product_id": key[2],
                    "status": candidate_status,
                    "origin": "automatic",
                    "reason": str(
                        row.get("match_rationale")
                        or "Product Pack comparison rules admitted this pair"
                    ),
                    "matches": 0,
                    "geographies": 0,
                    "median_gap": row.get("median_gap"),
                    "qa_status": str(row.get("qa_status") or "ready"),
                    "suppression_reasons": list(row.get("suppression_reasons") or []),
                    "match_basis": str(row.get("match_basis") or "exact_package"),
                    "profile_evidence": [],
                },
            )
            eligible = connection["eligible_profile_ids"]
            if isinstance(eligible, list) and candidate_profile_id not in eligible:
                eligible.append(candidate_profile_id)
            evidence = connection["profile_evidence"]
            if isinstance(evidence, list):
                evidence.append(
                    {
                        "profile_id": candidate_profile_id,
                        "profile_label": str(row.get("profile_label") or candidate_profile_id),
                        "comparison_metric": str(row.get("comparison_metric") or "package_price"),
                        "match_basis": str(row.get("match_basis") or "exact_package"),
                        "matches": row.get("matches"),
                        "geographies": row.get("geographies"),
                        "median_gap": row.get("median_gap"),
                        "match_attributes": dict(row.get("match_attributes") or {}),
                        "rationale": str(
                            row.get("match_rationale")
                            or "Product Pack comparison rules admitted this pair"
                        ),
                    }
                )
            connection["matches"] = max(
                int(connection.get("matches") or 0), int(row.get("matches") or 0)
            )
            connection["geographies"] = max(
                int(connection.get("geographies") or 0),
                int(row.get("geographies") or 0),
            )
            if connection["match_basis"] != str(row.get("match_basis") or "exact_package"):
                connection["match_basis"] = "multiple"

        for key, connection in connections.items():
            rule = persisted.get(key)
            connection["eligible_profile_ids"] = sorted(
                str(value) for value in connection["eligible_profile_ids"]
            )
            connection["profile_evidence"] = sorted(
                connection["profile_evidence"], key=lambda value: str(value["profile_id"])
            )
            if rule is None:
                continue
            connection.update(
                {
                    "id": rule.id,
                    "relationship_id": rule.id,
                    "candidate_group_id": None,
                    "source_profile_id": rule.source_profile_id,
                    "eligible_profile_ids": list(rule.eligible_profile_ids),
                    "status": rule.decision,
                    "origin": rule.origin,
                    "reason": rule.reason or connection["reason"],
                }
            )
            connection["profile_evidence"] = [
                evidence
                for evidence in connection["profile_evidence"]
                if evidence["profile_id"] in rule.eligible_profile_ids
            ]
        for key, rule in persisted.items():
            connections.setdefault(
                key,
                {
                    "id": rule.id,
                    "relationship_id": rule.id,
                    "candidate_group_id": None,
                    "competitor_retailer_id": key[0],
                    "source_profile_id": rule.source_profile_id,
                    "eligible_profile_ids": list(rule.eligible_profile_ids),
                    "benchmark_product_id": key[1],
                    "competitor_product_id": key[2],
                    "status": rule.decision,
                    "origin": rule.origin,
                    "reason": rule.reason,
                    "matches": None,
                    "geographies": None,
                    "median_gap": None,
                    "qa_status": "ready",
                    "suppression_reasons": [],
                    "match_basis": "user_defined",
                    "profile_evidence": [],
                },
            )
        confirmed = [row for row in connections.values() if row["status"] == "confirmed"]
        locked_benchmark = {
            (row["competitor_retailer_id"], row["benchmark_product_id"]) for row in confirmed
        }
        locked_competitor = {
            (row["competitor_retailer_id"], row["competitor_product_id"]) for row in confirmed
        }
        return sorted(
            (
                row
                for row in connections.values()
                if row["status"] != "suggested"
                or (
                    (
                        row["competitor_retailer_id"],
                        row["benchmark_product_id"],
                    )
                    not in locked_benchmark
                    and (
                        row["competitor_retailer_id"],
                        row["competitor_product_id"],
                    )
                    not in locked_competitor
                )
            ),
            key=lambda row: (
                str(row["competitor_retailer_id"]),
                {"confirmed": 0, "suggested": 1, "ambiguous": 2, "rejected": 3}[str(row["status"])],
                -int(row.get("matches") or 0),
                str(row["benchmark_product_id"]),
            ),
        )
