"""Immutable brand-role governance and analysis-scoped workbench projection."""

from __future__ import annotations

import asyncio
import copy
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncEngine

from rci_results.models import AnalysisRecord, JsonObject
from rci_results.repository import DEFAULT_ORGANIZATION_ID
from rci_results.service import AnalysisResultService
from rci_retailer_packs import GovernedBrandResolver


class BrandRevisionConflictError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class BrandRevisionRecord:
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
class BrandRuleRecord:
    id: str
    revision_id: str
    retailer_id: str
    normalized_brand: str
    display_brand: str
    role: str
    decision: str
    origin: str
    reason: str | None
    evidence: JsonObject
    created_at: datetime


@dataclass(frozen=True, slots=True)
class BrandDecisionCommand:
    expected_revision: int
    retailer_id: str
    normalized_brand: str
    role: str
    decision: str
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class BrandReanalysisRecord:
    analysis_run_id: str
    source_analysis_id: str
    brand_revision_id: str
    status: str
    applied_to_future_runs: bool


class ProductPackDocument(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def document(self) -> JsonObject: ...


class ExactProductPackLoader(Protocol):
    async def load(self, pack_id: str, version: str) -> ProductPackDocument: ...


class BrandReviewRepository(Protocol):
    async def latest_revision(
        self, *, product_pack_id: str, product_pack_version: str, benchmark_retailer_id: str
    ) -> BrandRevisionRecord | None: ...

    async def rules(self, revision_id: str) -> list[BrandRuleRecord]: ...

    async def future_revision(
        self, *, product_pack_id: str, product_pack_version: str, benchmark_retailer_id: str
    ) -> BrandRevisionRecord | None: ...

    async def save_decision(
        self,
        analysis: AnalysisRecord,
        *,
        benchmark_retailer_id: str,
        command: BrandDecisionCommand,
        display_brand: str,
        evidence: JsonObject,
        actor: str,
    ) -> BrandRevisionRecord: ...

    async def enqueue_reanalysis(
        self,
        analysis: AnalysisRecord,
        revision: BrandRevisionRecord,
        *,
        apply_to_future_runs: bool,
        actor: str,
    ) -> BrandReanalysisRecord: ...


def _revision(row: RowMapping | dict[str, Any]) -> BrandRevisionRecord:
    return BrandRevisionRecord(
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


def _rule(row: RowMapping | dict[str, Any]) -> BrandRuleRecord:
    return BrandRuleRecord(
        id=str(row["id"]),
        revision_id=str(row["revision_id"]),
        retailer_id=str(row["retailer_id"]),
        normalized_brand=str(row["normalized_brand"]),
        display_brand=str(row["display_brand"]),
        role=str(row["role"]),
        decision=str(row["decision"]),
        origin=str(row["origin"]),
        reason=str(row["reason"]) if row.get("reason") is not None else None,
        evidence=dict(row.get("evidence") or {}),
        created_at=row["created_at"],
    )


def _normalize_brand_name(value: str) -> str:
    return " ".join(
        "".join(character if character.isalnum() else " " for character in value.casefold()).split()
    )


class PostgresBrandReviewRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def latest_revision(
        self, *, product_pack_id: str, product_pack_version: str, benchmark_retailer_id: str
    ) -> BrandRevisionRecord | None:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT * FROM brand_classification_revision
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

    async def rules(self, revision_id: str) -> list[BrandRuleRecord]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        "SELECT * FROM brand_classification_rule "
                        "WHERE revision_id = CAST(:revision_id AS uuid) "
                        "ORDER BY retailer_id, normalized_brand"
                    ),
                    {"revision_id": revision_id},
                )
            ).mappings()
            return [_rule(row) for row in rows]

    async def future_revision(
        self, *, product_pack_id: str, product_pack_version: str, benchmark_retailer_id: str
    ) -> BrandRevisionRecord | None:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT revision.*
                            FROM brand_classification_application_policy policy
                            JOIN brand_classification_revision revision
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
        command: BrandDecisionCommand,
        display_brand: str,
        evidence: JsonObject,
        actor: str,
    ) -> BrandRevisionRecord:
        lock_key = "|".join(
            (
                DEFAULT_ORGANIZATION_ID,
                analysis.product_pack_id,
                analysis.product_pack_version,
                benchmark_retailer_id,
                "brand",
            )
        )
        async with self._engine.begin() as connection:
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:scope_key, 0))"),
                {"scope_key": lock_key},
            )
            current_row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT * FROM brand_classification_revision
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
                raise BrandRevisionConflictError(
                    f"expected revision {command.expected_revision}, current revision is "
                    f"{current_revision}"
                )
            existing: list[dict[str, Any]] = []
            if current_row is not None:
                existing = [
                    dict(row)
                    for row in (
                        await connection.execute(
                            text(
                                "SELECT * FROM brand_classification_rule "
                                "WHERE revision_id = CAST(:revision_id AS uuid)"
                            ),
                            {"revision_id": str(current_row["id"])},
                        )
                    )
                    .mappings()
                    .all()
                ]
            next_rows = self._apply(existing, command, display_brand, evidence)
            if current_row is not None:
                await connection.execute(
                    text(
                        "UPDATE brand_classification_revision SET status = 'superseded' "
                        "WHERE id = CAST(:revision_id AS uuid)"
                    ),
                    {"revision_id": str(current_row["id"])},
                )
            revision_row = (
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO brand_classification_revision (
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
                await connection.execute(
                    text(
                        """
                        INSERT INTO brand_classification_rule (
                          revision_id, retailer_id, normalized_brand, display_brand,
                          role, decision, origin, reason, evidence
                        ) VALUES (
                          CAST(:revision_id AS uuid), :retailer_id, :normalized_brand,
                          :display_brand, :role, :decision, :origin, :reason,
                          CAST(:evidence AS jsonb)
                        )
                        """
                    ),
                    {
                        "revision_id": revision_id,
                        **{
                            key: row[key]
                            for key in (
                                "retailer_id",
                                "normalized_brand",
                                "display_brand",
                                "role",
                                "decision",
                                "origin",
                                "reason",
                            )
                        },
                        "evidence": json.dumps(row["evidence"], sort_keys=True),
                    },
                )
            await connection.execute(
                text(
                    """
                    INSERT INTO brand_classification_review_event (
                      revision_id, event_type, actor, details
                    ) VALUES (
                      CAST(:revision_id AS uuid), :event_type, :actor, CAST(:details AS jsonb)
                    )
                    """
                ),
                {
                    "revision_id": revision_id,
                    "event_type": f"brand_{command.decision}",
                    "actor": actor,
                    "details": json.dumps(
                        {**asdict(command), "revision": current_revision + 1}, sort_keys=True
                    ),
                },
            )
            return _revision(revision_row)

    @staticmethod
    def _apply(
        existing: list[dict[str, Any]],
        command: BrandDecisionCommand,
        display_brand: str,
        evidence: JsonObject,
    ) -> list[dict[str, Any]]:
        target = lambda row: (  # noqa: E731
            str(row["retailer_id"]) == command.retailer_id
            and str(row["normalized_brand"]) == command.normalized_brand
        )
        remaining = [row for row in existing if not target(row)]
        if command.decision == "reset":
            return remaining
        if command.decision not in {"confirmed", "rejected"}:
            raise ValueError(f"unsupported brand decision {command.decision!r}")
        if command.role not in {"private_label", "regional", "national", "unclassified"}:
            raise ValueError(f"unsupported brand role {command.role!r}")
        return [
            *remaining,
            {
                "retailer_id": command.retailer_id,
                "normalized_brand": command.normalized_brand,
                "display_brand": display_brand,
                "role": command.role,
                "decision": command.decision,
                "origin": "user",
                "reason": command.reason,
                "evidence": copy.deepcopy(evidence),
            },
        ]

    async def enqueue_reanalysis(
        self,
        analysis: AnalysisRecord,
        revision: BrandRevisionRecord,
        *,
        apply_to_future_runs: bool,
        actor: str,
    ) -> BrandReanalysisRecord:
        async with self._engine.begin() as connection:
            if apply_to_future_runs:
                await connection.execute(
                    text(
                        """
                        INSERT INTO brand_classification_application_policy (
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
                              match_revision_id, brand_revision_id, source_analysis_result_id
                            )
                            SELECT ar.collection_run_id, ar.input_set_id, ar.product_pack_id,
                              ar.product_pack_version, 'queued', ar.code_version, ar.max_attempts,
                              ar.match_revision_id, CAST(:brand_revision_id AS uuid),
                              CAST(:source_analysis_result_id AS uuid)
                            FROM analysis_run ar
                            WHERE ar.id = CAST(:source_analysis_run_id AS uuid)
                            ON CONFLICT ON CONSTRAINT analysis_run_collection_pack_match_revision_uq
                            DO UPDATE SET available_at = LEAST(analysis_run.available_at, now())
                            RETURNING id::text, status
                            """
                        ),
                        {
                            "brand_revision_id": revision.id,
                            "source_analysis_result_id": analysis.id,
                            "source_analysis_run_id": analysis.analysis_run_id,
                        },
                    )
                )
                .mappings()
                .one()
            )
        return BrandReanalysisRecord(
            analysis_run_id=str(row["id"]),
            source_analysis_id=analysis.analysis_id,
            brand_revision_id=revision.id,
            status=str(row["status"]),
            applied_to_future_runs=apply_to_future_runs,
        )


class InMemoryBrandReviewRepository:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._revisions: list[BrandRevisionRecord] = []
        self._rules: dict[str, list[BrandRuleRecord]] = {}
        self._future_revision_ids: dict[tuple[str, str, str], str] = {}

    async def latest_revision(
        self, *, product_pack_id: str, product_pack_version: str, benchmark_retailer_id: str
    ) -> BrandRevisionRecord | None:
        async with self._lock:
            candidates = [
                row
                for row in self._revisions
                if row.product_pack_id == product_pack_id
                and row.product_pack_version == product_pack_version
                and row.benchmark_retailer_id == benchmark_retailer_id
                and row.status == "current"
            ]
            return copy.deepcopy(candidates[-1]) if candidates else None

    async def rules(self, revision_id: str) -> list[BrandRuleRecord]:
        async with self._lock:
            return copy.deepcopy(self._rules.get(revision_id, []))

    async def future_revision(
        self, *, product_pack_id: str, product_pack_version: str, benchmark_retailer_id: str
    ) -> BrandRevisionRecord | None:
        async with self._lock:
            revision_id = self._future_revision_ids.get(
                (product_pack_id, product_pack_version, benchmark_retailer_id)
            )
            row = next((value for value in self._revisions if value.id == revision_id), None)
            return copy.deepcopy(row)

    async def save_decision(
        self,
        analysis: AnalysisRecord,
        *,
        benchmark_retailer_id: str,
        command: BrandDecisionCommand,
        display_brand: str,
        evidence: JsonObject,
        actor: str,
    ) -> BrandRevisionRecord:
        async with self._lock:
            current = next(
                (
                    row
                    for row in reversed(self._revisions)
                    if row.product_pack_id == analysis.product_pack_id
                    and row.product_pack_version == analysis.product_pack_version
                    and row.benchmark_retailer_id == benchmark_retailer_id
                    and row.status == "current"
                ),
                None,
            )
            number = current.revision if current is not None else 0
            if command.expected_revision != number:
                raise BrandRevisionConflictError(
                    f"expected revision {command.expected_revision}, current revision is {number}"
                )
            source = [asdict(row) for row in self._rules.get(current.id, [])] if current else []
            next_rows = PostgresBrandReviewRepository._apply(
                source, command, display_brand, evidence
            )
            if current is not None:
                self._revisions[self._revisions.index(current)] = BrandRevisionRecord(
                    **{**asdict(current), "status": "superseded"}
                )
            now = datetime.now(UTC)
            revision = BrandRevisionRecord(
                id=str(uuid4()),
                organization_id=DEFAULT_ORGANIZATION_ID,
                product_pack_id=analysis.product_pack_id,
                product_pack_version=analysis.product_pack_version,
                benchmark_retailer_id=benchmark_retailer_id,
                source_analysis_result_id=analysis.id,
                revision=number + 1,
                status="current",
                created_by=actor,
                created_at=now,
            )
            self._revisions.append(revision)
            self._rules[revision.id] = [
                BrandRuleRecord(
                    id=str(row.get("id") or uuid4()),
                    revision_id=revision.id,
                    retailer_id=str(row["retailer_id"]),
                    normalized_brand=str(row["normalized_brand"]),
                    display_brand=str(row["display_brand"]),
                    role=str(row["role"]),
                    decision=str(row["decision"]),
                    origin=str(row["origin"]),
                    reason=str(row["reason"]) if row.get("reason") is not None else None,
                    evidence=copy.deepcopy(row.get("evidence") or {}),
                    created_at=now,
                )
                for row in next_rows
            ]
            return copy.deepcopy(revision)

    async def enqueue_reanalysis(
        self,
        analysis: AnalysisRecord,
        revision: BrandRevisionRecord,
        *,
        apply_to_future_runs: bool,
        actor: str,
    ) -> BrandReanalysisRecord:
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
        return BrandReanalysisRecord(
            analysis_run_id=str(uuid4()),
            source_analysis_id=analysis.analysis_id,
            brand_revision_id=revision.id,
            status="queued",
            applied_to_future_runs=apply_to_future_runs,
        )


class BrandReviewService:
    def __init__(
        self,
        results: AnalysisResultService,
        repository: BrandReviewRepository,
        product_packs: ExactProductPackLoader,
        *,
        retailer_names: dict[str, str] | None = None,
        brand_resolver: GovernedBrandResolver | None = None,
    ) -> None:
        self._results = results
        self._repository = repository
        self._product_packs = product_packs
        self._retailer_names = dict(retailer_names or {})
        self._brand_resolver = brand_resolver

    async def view(self, analysis_id: str) -> JsonObject:
        analysis = await self._results.get(analysis_id)
        publication = await self._results.latest_publication(analysis.analysis_id)
        document = publication.result if publication is not None else analysis.result
        context = publication.presentation_context if publication is not None else {}
        benchmark = str(document["benchmark_retailer"])
        retailer_ids = [benchmark, *[str(value) for value in document.get("competitors", [])]]
        revision = await self._repository.latest_revision(
            product_pack_id=analysis.product_pack_id,
            product_pack_version=analysis.product_pack_version,
            benchmark_retailer_id=benchmark,
        )
        future = await self._repository.future_revision(
            product_pack_id=analysis.product_pack_id,
            product_pack_version=analysis.product_pack_version,
            benchmark_retailer_id=benchmark,
        )
        rules = await self._repository.rules(revision.id) if revision is not None else []
        pack = await self._product_packs.load(
            analysis.product_pack_id, analysis.product_pack_version
        )
        brands = self._brands(
            document,
            context,
            retailer_ids,
            pack,
            rules,
            brand_resolver=self._brand_resolver,
        )
        return {
            "schema_version": "1.0.0",
            "analysis_id": analysis.analysis_id,
            "product_pack_id": analysis.product_pack_id,
            "product_pack_version": analysis.product_pack_version,
            "revision_id": revision.id if revision else None,
            "revision": revision.revision if revision else 0,
            "current_publication_revision_id": (
                document.get("source", {}).get("brand_revision_id")
                if isinstance(document.get("source"), dict)
                else None
            ),
            "future_application": (
                {"revision_id": future.id, "revision": future.revision} if future else None
            ),
            "retailers": [
                {
                    "id": retailer_id,
                    "name": self._retailer_names.get(
                        retailer_id, retailer_id.replace("_", " ").title()
                    ),
                }
                for retailer_id in retailer_ids
            ],
            "brands": brands,
            "summary": {
                status: sum(row["status"] == status for row in brands)
                for status in ("suggested", "confirmed", "rejected", "unclassified")
            },
        }

    async def decide(
        self, analysis_id: str, command: BrandDecisionCommand, *, actor: str
    ) -> JsonObject:
        view = await self.view(analysis_id)
        target = next(
            (
                row
                for row in view["brands"]
                if row["retailer_id"] == command.retailer_id
                and row["normalized_brand"] == command.normalized_brand
            ),
            None,
        )
        if target is None:
            raise ValueError("brand is not present in this analysis")
        analysis = await self._results.get(analysis_id)
        revision = await self._repository.save_decision(
            analysis,
            benchmark_retailer_id=str(analysis.result["benchmark_retailer"]),
            command=command,
            display_brand=str(target["display_brand"]),
            evidence={
                key: target[key]
                for key in (
                    "observed_products",
                    "observed_locations",
                    "observed_zipcodes",
                    "location_share",
                    "distribution_tier",
                )
            },
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
    ) -> BrandReanalysisRecord:
        analysis = await self._results.get(analysis_id)
        benchmark = str(analysis.result["benchmark_retailer"])
        revision = await self._repository.latest_revision(
            product_pack_id=analysis.product_pack_id,
            product_pack_version=analysis.product_pack_version,
            benchmark_retailer_id=benchmark,
        )
        if revision is None:
            raise ValueError("save at least one brand decision before reanalysis")
        if revision.revision != expected_revision:
            raise BrandRevisionConflictError(
                f"expected revision {expected_revision}, current revision is {revision.revision}"
            )
        return await self._repository.enqueue_reanalysis(
            analysis,
            revision,
            apply_to_future_runs=apply_to_future_runs,
            actor=actor,
        )

    @staticmethod
    def _brands(
        document: JsonObject,
        context: JsonObject,
        retailer_ids: list[str],
        pack: ProductPackDocument,
        rules: list[BrandRuleRecord],
        *,
        brand_resolver: GovernedBrandResolver | None = None,
    ) -> list[JsonObject]:
        aliases: dict[str, str] = {}
        for canonical, values in pack.document.get("brand_rules", {}).get("aliases", {}).items():
            normalized_canonical = _normalize_brand_name(str(canonical))
            for value in (canonical, *values):
                aliases[_normalize_brand_name(str(value))] = normalized_canonical

        def normalize(value: str) -> str:
            normalized = _normalize_brand_name(value)
            return aliases.get(normalized, normalized)

        configured: dict[tuple[str, str], tuple[str, str]] = {}
        for portfolio in pack.document.get("brand_rules", {}).get("portfolios", []):
            for retailer_id in portfolio["retailer_ids"]:
                for brand in portfolio["brands"]:
                    configured[(str(retailer_id), normalize(str(brand)))] = (
                        str(portfolio["role"]),
                        "product_pack",
                    )
        for retailer_id, values in (
            pack.document.get("brand_rules", {}).get("private_labels", {}).items()
        ):
            for brand in values:
                configured.setdefault(
                    (str(retailer_id), normalize(str(brand))),
                    ("private_label", "product_pack"),
                )
        if brand_resolver is not None:
            for retailer_id in retailer_ids:
                summary_value = context.get("assortment_analysis") or document.get(
                    "assortment_analysis"
                )
                if not isinstance(summary_value, dict):
                    continue
                retailer_summary = next(
                    (
                        row
                        for row in summary_value.get("retailers", [])
                        if isinstance(row, dict) and str(row.get("retailer")) == retailer_id
                    ),
                    {},
                )
                for brand_row in retailer_summary.get("brands", []):
                    if not isinstance(brand_row, dict) or not brand_row.get("brand"):
                        continue
                    resolution = brand_resolver.resolve(
                        retailer_id,
                        str(brand_row["brand"]),
                        category=pack.name,
                    )
                    if resolution.status == "resolved" and resolution.role != "unclassified":
                        configured.setdefault(
                            (
                                retailer_id,
                                _normalize_brand_name(
                                    resolution.canonical_brand_name or str(brand_row["brand"])
                                ),
                            ),
                            (resolution.role, "deterministic"),
                        )
        persisted = {(row.retailer_id, normalize(row.normalized_brand)): row for row in rules}
        examples: dict[tuple[str, str], list[JsonObject]] = {}
        highlighted_products: dict[tuple[str, str], set[str]] = {}
        highlighted_display: dict[tuple[str, str], str] = {}
        for row in context.get("product_highlights", []):
            if not isinstance(row, dict):
                continue
            canonical = str(row.get("canonical_product_id") or "")
            retailer_id, _, product_id = canonical.partition(":")
            brand = str(row.get("brand") or "").strip()
            if not retailer_id or not product_id or not brand:
                continue
            key = (retailer_id, normalize(brand))
            highlighted_products.setdefault(key, set()).add(product_id)
            highlighted_display.setdefault(key, brand)
            if not any(str(value["product_id"]) == product_id for value in examples.get(key, [])):
                examples.setdefault(key, []).append(
                    {
                        "product_id": product_id,
                        "name": str(row.get("name") or product_id),
                        "image_url": row.get("image_url"),
                    }
                )

        benchmark_retailer = str(document.get("benchmark_retailer") or retailer_ids[0])
        product_zip_lower_bounds: dict[tuple[str, str], int] = {}
        product_location_lower_bounds: dict[tuple[str, str], int] = {}
        for row in context.get("match_candidates", []):
            if not isinstance(row, dict):
                continue
            competitor_id = str(row.get("competitor") or "")
            pairs = (
                (benchmark_retailer, str(row.get("benchmark_product_id") or "")),
                (competitor_id, str(row.get("competitor_product_id") or "")),
            )
            market_count = max(0, int(row.get("geographies") or 0))
            location_count = len(
                {str(value) for value in row.get("benchmark_location_scope_keys", []) if value}
            )
            for retailer_id, product_id in pairs:
                if not retailer_id or not product_id:
                    continue
                key = (retailer_id, product_id)
                product_zip_lower_bounds[key] = max(
                    product_zip_lower_bounds.get(key, 0), market_count
                )
                product_location_lower_bounds[key] = max(
                    product_location_lower_bounds.get(key, 0),
                    location_count if retailer_id == benchmark_retailer else 0,
                )

        assortment_value = (
            context.get("assortment_analysis")
            or document.get("assortment_analysis")
            or document.get("assortment", {})
        )
        assortment = assortment_value if isinstance(assortment_value, dict) else {}
        summaries = {
            str(row.get("retailer")): row
            for row in assortment.get("retailers", [])
            if isinstance(row, dict)
        }
        output: list[JsonObject] = []
        for retailer_id in retailer_ids:
            summary = summaries.get(retailer_id, {})
            brand_values = summary.get("brands") or summary.get("top_brands", [])
            if not isinstance(brand_values, list):
                brand_values = []
            brand_summaries: dict[tuple[str, str], JsonObject] = {}
            for row in brand_values:
                if not isinstance(row, dict):
                    continue
                display = str(row.get("brand") or "").strip()
                if not display:
                    continue
                brand_summaries[(retailer_id, normalize(display))] = row
            brand_keys = {
                *brand_summaries,
                *(key for key in highlighted_products if key[0] == retailer_id),
            }
            for key in sorted(brand_keys):
                row = brand_summaries.get(key)
                display = (
                    str(row.get("brand") or "").strip()
                    if row is not None
                    else highlighted_display[key]
                )
                normalized = key[1]
                rule = persisted.get((retailer_id, normalized))
                configured_role, configured_origin = configured.get(
                    (retailer_id, normalized), ("unclassified", "deterministic")
                )
                product_ids = highlighted_products.get(key, set())
                if row is not None:
                    products = max(1, int(row.get("distinct_products") or len(product_ids) or 1))
                    locations = max(0, int(row.get("observed_locations") or 0))
                    zipcodes = max(0, int(row.get("observed_zipcodes") or 0))
                    share = float(row.get("location_share") or 0)
                    distribution_evidence = "search_brand_field"
                else:
                    products = max(1, len(product_ids))
                    zipcodes = max(
                        (
                            product_zip_lower_bounds.get((retailer_id, value), 0)
                            for value in product_ids
                        ),
                        default=0,
                    )
                    locations = max(
                        (
                            product_location_lower_bounds.get((retailer_id, value), 0)
                            for value in product_ids
                        ),
                        default=0,
                    )
                    share = 0.0
                    distribution_evidence = (
                        "pdp_identity_joined_to_matched_search" if zipcodes else "pdp_identity_only"
                    )
                tier = (
                    "unknown"
                    if distribution_evidence != "search_brand_field" or locations <= 0
                    else "single_location"
                    if locations <= 1
                    else "broad"
                    if share >= 0.75
                    else "multi_market"
                    if share >= 0.25
                    else "concentrated"
                )
                output.append(
                    {
                        "retailer_id": retailer_id,
                        "normalized_brand": normalized,
                        "display_brand": display,
                        "role": rule.role if rule else configured_role,
                        "status": (
                            rule.decision
                            if rule
                            else "suggested"
                            if configured_role != "unclassified"
                            else "unclassified"
                        ),
                        "origin": rule.origin if rule else configured_origin,
                        "reason": rule.reason if rule else None,
                        "observed_products": products,
                        "observed_locations": locations,
                        "observed_zipcodes": zipcodes,
                        "location_share": min(1.0, max(0.0, share)),
                        "distribution_tier": tier,
                        "distribution_evidence": distribution_evidence,
                        "product_examples": examples.get(key, [])[:4],
                    }
                )
        return sorted(
            output,
            key=lambda row: (
                retailer_ids.index(str(row["retailer_id"])),
                {"unclassified": 0, "suggested": 1, "confirmed": 2, "rejected": 3}[
                    str(row["status"])
                ],
                -int(row["observed_locations"]),
                str(row["display_brand"]).casefold(),
            ),
        )
