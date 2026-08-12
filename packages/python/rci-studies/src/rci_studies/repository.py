"""Postgres persistence and leased jobs for governed study discovery."""

from __future__ import annotations

import builtins
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from rci_studies.models import DiscoveryProfile, JsonObject, StudyJob, StudyRecord

DEFAULT_ORGANIZATION_ID = "00000000-0000-0000-0000-000000000001"


class StudyNotFoundError(LookupError):
    pass


class StudyStateError(ValueError):
    pass


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _record(row: RowMapping) -> StudyRecord:
    return StudyRecord(
        id=str(row["id"]),
        name=str(row["name"]),
        status=str(row["status"]),
        intake=dict(row["intake"]),
        query_plan=dict(row["query_plan"]),
        query_plan_checksum=str(row["query_plan_checksum"]),
        approval_state=dict(row["approval_state"]),
        geography_resolution_id=(
            str(row["geography_resolution_id"])
            if row["geography_resolution_id"] is not None
            else None
        ),
        search_scope_estimate_id=(
            str(row["search_scope_estimate_id"])
            if row["search_scope_estimate_id"] is not None
            else None
        ),
        collection_run_id=(
            str(row["collection_run_id"]) if row["collection_run_id"] is not None else None
        ),
        pdp_estimate=dict(row["pdp_estimate"]) if row["pdp_estimate"] is not None else None,
        pdp_plan_checksum=(
            str(row["pdp_plan_checksum"]) if row["pdp_plan_checksum"] is not None else None
        ),
        pdp_run_id=str(row["pdp_run_id"]) if row["pdp_run_id"] is not None else None,
        product_pack_draft_id=(
            str(row["product_pack_draft_id"]) if row["product_pack_draft_id"] is not None else None
        ),
        profile_summary=dict(row["profile_summary"] or {}),
        last_error=str(row["last_error"]) if row["last_error"] is not None else None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


_SELECT = """
SELECT id::text, name, status, intake, query_plan, query_plan_checksum,
       approval_state, geography_resolution_id::text, search_scope_estimate_id::text,
       collection_run_id::text, pdp_estimate, pdp_plan_checksum, pdp_run_id::text,
       product_pack_draft_id::text, profile_summary, last_error, created_at, updated_at
FROM study_discovery
"""


class PostgresStudyRepository:
    def __init__(
        self,
        engine: AsyncEngine,
        *,
        organization_id: str = DEFAULT_ORGANIZATION_ID,
    ) -> None:
        self._engine = engine
        self._organization_id = organization_id

    async def create(
        self,
        *,
        name: str,
        intake: JsonObject,
        query_plan: JsonObject,
        query_plan_checksum: str,
        approval_state: JsonObject,
        actor: str,
    ) -> StudyRecord:
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            f"""
                            INSERT INTO study_discovery (
                              organization_id, name, intake, query_plan,
                              query_plan_checksum, approval_state, created_by, updated_by
                            ) VALUES (
                              CAST(:organization_id AS uuid), :name, CAST(:intake AS jsonb),
                              CAST(:query_plan AS jsonb), :checksum,
                              CAST(:approval_state AS jsonb), :actor, :actor
                            ) RETURNING {self._returning_columns()}
                            """
                        ),
                        {
                            "organization_id": self._organization_id,
                            "name": name,
                            "intake": _json(intake),
                            "query_plan": _json(query_plan),
                            "checksum": query_plan_checksum,
                            "approval_state": _json(approval_state),
                            "actor": actor,
                        },
                    )
                )
                .mappings()
                .one()
            )
            await self._audit(connection, "study_discovery_created", str(row["id"]), actor, {})
        return _record(row)

    @staticmethod
    def _returning_columns() -> str:
        return (
            "id::text AS id, name, status, intake, query_plan, query_plan_checksum, "
            "approval_state, geography_resolution_id::text AS geography_resolution_id, "
            "search_scope_estimate_id::text AS search_scope_estimate_id, "
            "collection_run_id::text AS collection_run_id, pdp_estimate, pdp_plan_checksum, "
            "pdp_run_id::text AS pdp_run_id, "
            "product_pack_draft_id::text AS product_pack_draft_id, profile_summary, "
            "last_error, created_at, updated_at"
        )

    async def list(self) -> list[StudyRecord]:
        async with self._engine.connect() as connection:
            rows = (
                (await connection.execute(text(f"{_SELECT} ORDER BY updated_at DESC, id")))
                .mappings()
                .all()
            )
        return [_record(row) for row in rows]

    async def get(self, study_id: str) -> StudyRecord:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(f"{_SELECT} WHERE id::text = :study_id"),
                        {"study_id": study_id},
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            raise StudyNotFoundError(f"study {study_id!r} was not found")
        return _record(row)

    async def update_query_plan(
        self,
        study_id: str,
        *,
        query_plan: JsonObject,
        checksum: str,
        actor: str,
    ) -> StudyRecord:
        async with self._engine.begin() as connection:
            current = await self._locked(connection, study_id)
            if str(current["status"]) not in {"query_review", "search_estimated"}:
                raise StudyStateError("the query plan cannot change after Search has launched")
            approval = dict(current["approval_state"])
            approval["search"] = _approval("not_requested", unit="credits")
            row = (
                (
                    await connection.execute(
                        text(
                            f"""
                            UPDATE study_discovery SET query_plan = CAST(:query_plan AS jsonb),
                              query_plan_checksum = :checksum,
                              approval_state = CAST(:approval AS jsonb), status = 'query_review',
                              geography_resolution_id = NULL, search_scope_estimate_id = NULL,
                              updated_by = :actor, updated_at = now()
                            WHERE id::text = :study_id RETURNING {self._returning_columns()}
                            """
                        ),
                        {
                            "study_id": study_id,
                            "query_plan": _json(query_plan),
                            "checksum": checksum,
                            "approval": _json(approval),
                            "actor": actor,
                        },
                    )
                )
                .mappings()
                .one()
            )
            await self._audit(
                connection,
                "study_query_plan_revised",
                study_id,
                actor,
                {"query_plan_checksum": checksum},
            )
        return _record(row)

    async def revise_profile_scope(
        self,
        study_id: str,
        *,
        query_plan: JsonObject,
        checksum: str,
        actor: str,
    ) -> StudyRecord:
        """Re-profile persisted Search evidence without buying another collection."""

        async with self._engine.begin() as connection:
            current = await self._locked(connection, study_id)
            if str(current["status"]) not in {"profile_ready", "pdp_estimated"}:
                raise StudyStateError("profile scope can only change before PDP enrichment")
            if current["collection_run_id"] is None:
                raise StudyStateError("profile scope requires a completed Search collection")
            approval = dict(current["approval_state"])
            approval["pdp"] = _approval("not_requested", unit="credits")
            await connection.execute(
                text(
                    """
                    INSERT INTO study_discovery_job (
                      study_id, kind, idempotency_key, payload
                    ) VALUES (
                      CAST(:study_id AS uuid), 'profile', 'profile:' || :checksum,
                      jsonb_build_object(
                        'collection_run_id', CAST(:run_id AS uuid),
                        'query_plan_checksum', :checksum
                      )
                    )
                    """
                ),
                {
                    "study_id": study_id,
                    "run_id": str(current["collection_run_id"]),
                    "checksum": checksum,
                },
            )
            row = (
                (
                    await connection.execute(
                        text(
                            f"""
                            UPDATE study_discovery SET status = 'profiling',
                              query_plan = CAST(:query_plan AS jsonb),
                              query_plan_checksum = :checksum,
                              approval_state = CAST(:approval AS jsonb),
                              pdp_estimate = NULL, pdp_plan_checksum = NULL,
                              last_error = NULL, updated_by = :actor, updated_at = now()
                            WHERE id::text = :study_id
                            RETURNING {self._returning_columns()}
                            """
                        ),
                        {
                            "study_id": study_id,
                            "query_plan": _json(query_plan),
                            "checksum": checksum,
                            "approval": _json(approval),
                            "actor": actor,
                        },
                    )
                )
                .mappings()
                .one()
            )
            await self._audit(
                connection,
                "study_profile_scope_revised",
                study_id,
                actor,
                {
                    "query_plan_checksum": checksum,
                    "collection_run_id": str(current["collection_run_id"]),
                },
            )
        return _record(row)

    async def record_search_estimate(
        self,
        study_id: str,
        *,
        geography_resolution_id: str,
        estimate_id: str,
        estimated_credits: int,
        actor: str,
    ) -> StudyRecord:
        async with self._engine.begin() as connection:
            current = await self._locked(connection, study_id)
            if str(current["status"]) not in {"query_review", "search_estimated"}:
                raise StudyStateError("Search can only be estimated before collection begins")
            approval = dict(current["approval_state"])
            approval["search"] = _approval(
                "estimated",
                maximum_cost=estimated_credits,
                unit="credits",
            )
            return _record(
                (
                    await connection.execute(
                        text(
                            f"""
                                UPDATE study_discovery SET status = 'search_estimated',
                                  geography_resolution_id = CAST(:resolution_id AS uuid),
                                  search_scope_estimate_id = CAST(:estimate_id AS uuid),
                                  approval_state = CAST(:approval AS jsonb), updated_by = :actor,
                                  updated_at = now()
                                WHERE id::text = :study_id
                                RETURNING {self._returning_columns()}
                                """
                        ),
                        {
                            "study_id": study_id,
                            "resolution_id": geography_resolution_id,
                            "estimate_id": estimate_id,
                            "approval": _json(approval),
                            "actor": actor,
                        },
                    )
                )
                .mappings()
                .one()
            )

    async def record_search_launch(
        self,
        study_id: str,
        *,
        collection_run_id: str,
        approved_by: str,
    ) -> StudyRecord:
        async with self._engine.begin() as connection:
            current = await self._locked(connection, study_id)
            if (
                current["collection_run_id"] is not None
                and str(current["collection_run_id"]) == collection_run_id
                and str(current["status"]) in {"collecting", "profiling", "profile_ready"}
            ):
                return _record(current)
            if str(current["status"]) != "search_estimated":
                raise StudyStateError("Search must have a current estimate before approval")
            approval = dict(current["approval_state"])
            search = dict(approval["search"])
            search.update(
                {
                    "status": "consumed",
                    "approved_by": approved_by,
                    "approved_at": datetime.now(UTC).isoformat(),
                    "approved_checksum": str(current["query_plan_checksum"]),
                }
            )
            approval["search"] = search
            row = (
                (
                    await connection.execute(
                        text(
                            f"""
                            UPDATE study_discovery SET status = 'collecting',
                              collection_run_id = CAST(:run_id AS uuid),
                              approval_state = CAST(:approval AS jsonb), updated_by = :actor,
                              updated_at = now()
                            WHERE id::text = :study_id
                            RETURNING {self._returning_columns()}
                            """
                        ),
                        {
                            "study_id": study_id,
                            "run_id": collection_run_id,
                            "approval": _json(approval),
                            "actor": approved_by,
                        },
                    )
                )
                .mappings()
                .one()
            )
            await self._audit(
                connection,
                "study_search_approved",
                study_id,
                approved_by,
                {"collection_run_id": collection_run_id, "approval": search},
            )
        return _record(row)

    async def materialize_profile_jobs(self) -> int:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    UPDATE study_discovery s SET status = 'failed',
                      last_error = 'Discovery Search collection failed', updated_at = now()
                    FROM collection_run r
                    WHERE s.collection_run_id = r.id AND s.status = 'collecting'
                      AND r.status IN ('failed','canceled')
                    """
                )
            )
            rows = (
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO study_discovery_job (
                              study_id, kind, idempotency_key, payload
                            )
                            SELECT s.id, 'profile', 'profile:' || s.query_plan_checksum,
                              jsonb_build_object(
                                'collection_run_id', s.collection_run_id,
                                'query_plan_checksum', s.query_plan_checksum
                              )
                            FROM study_discovery s
                            JOIN collection_run r ON r.id = s.collection_run_id
                            WHERE s.status = 'collecting'
                              AND r.status IN ('succeeded','completed_with_warnings')
                            ON CONFLICT (study_id, idempotency_key) DO NOTHING
                            RETURNING study_id::text
                            """
                        )
                    )
                )
                .scalars()
                .all()
            )
            if rows:
                await connection.execute(
                    text(
                        "UPDATE study_discovery SET status = 'profiling', updated_at = now() "
                        "WHERE id::text = ANY(CAST(:study_ids AS text[]))"
                    ),
                    {"study_ids": list(rows)},
                )
        return len(rows)

    async def claim_jobs(
        self,
        worker_id: str,
        *,
        limit: int,
        lease_seconds: int,
    ) -> builtins.list[StudyJob]:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    UPDATE study_discovery_job SET status = 'failed',
                      last_error = 'Lease expired after maximum attempts', completed_at = now(),
                      locked_by = NULL, locked_at = NULL, lease_expires_at = NULL
                    WHERE status = 'running' AND lease_expires_at <= now()
                      AND attempt_count >= max_attempts
                    """
                )
            )
            rows = (
                (
                    await connection.execute(
                        text(
                            """
                            WITH candidates AS (
                              SELECT id FROM study_discovery_job
                              WHERE ((status = 'queued' AND available_at <= now()) OR
                                     (status = 'running' AND lease_expires_at <= now()))
                                AND attempt_count < max_attempts
                                AND cancel_requested_at IS NULL
                              ORDER BY available_at, created_at, id
                              FOR UPDATE SKIP LOCKED LIMIT :limit
                            )
                            UPDATE study_discovery_job job SET status = 'running',
                              locked_by = :worker_id, locked_at = now(),
                              lease_expires_at = now() + make_interval(secs => :lease_seconds),
                              attempt_count = job.attempt_count + 1,
                              started_at = COALESCE(job.started_at, now())
                            FROM candidates WHERE job.id = candidates.id
                            RETURNING job.id::text, job.study_id::text, job.kind,
                              job.payload, job.attempt_count, job.max_attempts
                            """
                        ),
                        {"worker_id": worker_id, "limit": limit, "lease_seconds": lease_seconds},
                    )
                )
                .mappings()
                .all()
            )
        return [
            StudyJob(
                id=str(row["id"]),
                study_id=str(row["study_id"]),
                kind=str(row["kind"]),
                payload=dict(row["payload"]),
                attempt_count=int(row["attempt_count"]),
                max_attempts=int(row["max_attempts"]),
            )
            for row in rows
        ]

    async def complete_profile(
        self,
        job: StudyJob,
        worker_id: str,
        profile: DiscoveryProfile,
    ) -> None:
        async with self._engine.begin() as connection:
            locked = (
                await connection.execute(
                    text(
                        "SELECT id FROM study_discovery_job WHERE id::text = :job_id "
                        "AND status = 'running' AND locked_by = :worker_id "
                        "AND lease_expires_at > now() FOR UPDATE"
                    ),
                    {"job_id": job.id, "worker_id": worker_id},
                )
            ).first()
            if locked is None:
                raise StudyStateError("study profile lease is no longer owned")
            await connection.execute(
                text("DELETE FROM study_discovery_product WHERE study_id::text = :study_id"),
                {"study_id": job.study_id},
            )
            for product in profile.products:
                await connection.execute(
                    text(
                        """
                        INSERT INTO study_discovery_product (
                          study_id, retailer_id, retailer_product_id, title, brand, url,
                          image_url, admission_status, admission_reason, observation_count,
                          store_count, zipcode_count, price_min, price_max, price_contexts,
                          representative_context, brand_resolution, identifiers,
                          source_artifact_ids
                        ) VALUES (
                          CAST(:study_id AS uuid), :retailer_id, :product_id, :title, :brand,
                          :url, :image_url, :admission_status, :admission_reason,
                          :observation_count, :store_count, :zipcode_count, :price_min,
                          :price_max, CAST(:price_contexts AS jsonb),
                          CAST(:representative_context AS jsonb),
                          CAST(:brand_resolution AS jsonb), CAST(:identifiers AS jsonb),
                          CAST(:source_artifact_ids AS jsonb)
                        )
                        """
                    ),
                    {
                        "study_id": job.study_id,
                        "retailer_id": product.retailer_id,
                        "product_id": product.retailer_product_id,
                        "title": product.title,
                        "brand": product.brand,
                        "url": product.url,
                        "image_url": product.image_url,
                        "admission_status": product.admission_status,
                        "admission_reason": product.admission_reason,
                        "observation_count": product.observation_count,
                        "store_count": product.store_count,
                        "zipcode_count": product.zipcode_count,
                        "price_min": product.price_min,
                        "price_max": product.price_max,
                        "price_contexts": _json(product.price_contexts),
                        "representative_context": _json(product.representative_context),
                        "brand_resolution": _json(product.brand_resolution),
                        "identifiers": _json(product.identifiers),
                        "source_artifact_ids": _json(product.source_artifact_ids),
                    },
                )
                resolution = product.brand_resolution
                if resolution.get("status") == "unresolved" and resolution.get("normalized_brand"):
                    await connection.execute(
                        text(
                            """
                            INSERT INTO brand_discovery_queue (
                              retailer_id, observed_brand_raw, observed_brand_normalized,
                              source_job_id, evidence, confidence_score
                            ) VALUES (
                              :retailer_id, :observed, :normalized, :source_job_id,
                              CAST(:evidence AS jsonb), 25
                            )
                            ON CONFLICT (retailer_id, observed_brand_normalized)
                              WHERE status IN ('Pending','Needs Evidence')
                            DO UPDATE SET evidence =
                              brand_discovery_queue.evidence || EXCLUDED.evidence
                            """
                        ),
                        {
                            "retailer_id": product.retailer_id,
                            "observed": product.brand or "",
                            "normalized": str(resolution["normalized_brand"]),
                            "source_job_id": job.id,
                            "evidence": _json(
                                {
                                    "study_id": job.study_id,
                                    "product_id": product.retailer_product_id,
                                    "title": product.title,
                                }
                            ),
                        },
                    )
            await connection.execute(
                text(
                    """
                    UPDATE study_discovery SET status = 'profile_ready',
                      profile_summary = CAST(:summary AS jsonb), last_error = NULL,
                      updated_at = now() WHERE id::text = :study_id
                    """
                ),
                {"study_id": job.study_id, "summary": _json(profile.summary)},
            )
            await connection.execute(
                text(
                    """
                    UPDATE study_discovery_job SET status = 'succeeded',
                      result = CAST(:result AS jsonb), completed_at = now(),
                      locked_by = NULL, locked_at = NULL, lease_expires_at = NULL
                    WHERE id::text = :job_id AND locked_by = :worker_id
                    """
                ),
                {"job_id": job.id, "worker_id": worker_id, "result": _json(profile.summary)},
            )

    async def fail_job(self, job: StudyJob, worker_id: str, error: str) -> None:
        retry = job.attempt_count < job.max_attempts
        delay = min(30 * (2 ** max(job.attempt_count - 1, 0)), 300)
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    UPDATE study_discovery_job SET status = :status,
                      available_at = now() + make_interval(secs => :delay),
                      completed_at = CASE WHEN :retry THEN NULL ELSE now() END,
                      last_error = :error, locked_by = NULL, locked_at = NULL,
                      lease_expires_at = NULL
                    WHERE id::text = :job_id AND status = 'running' AND locked_by = :worker_id
                    """
                ),
                {
                    "status": "queued" if retry else "failed",
                    "delay": delay,
                    "retry": retry,
                    "error": error[:4000],
                    "job_id": job.id,
                    "worker_id": worker_id,
                },
            )
            if not retry:
                await connection.execute(
                    text(
                        "UPDATE study_discovery SET status = 'failed', last_error = :error, "
                        "updated_at = now() WHERE id::text = :study_id"
                    ),
                    {"study_id": job.study_id, "error": error[:4000]},
                )

    async def list_products(
        self,
        study_id: str,
        *,
        admission_status: str | None = None,
    ) -> builtins.list[JsonObject]:
        await self.get(study_id)
        where = "WHERE study_id::text = :study_id"
        parameters: dict[str, Any] = {"study_id": study_id}
        if admission_status:
            where += " AND admission_status = :admission_status"
            parameters["admission_status"] = admission_status
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            f"""
                            SELECT retailer_id, retailer_product_id, title, brand, url,
                              image_url, admission_status, admission_reason, observation_count,
                              store_count, zipcode_count, price_min, price_max, price_contexts,
                              representative_context, brand_resolution, identifiers,
                              source_artifact_ids
                            FROM study_discovery_product {where}
                            ORDER BY admission_status, retailer_id, title, retailer_product_id
                            """
                        ),
                        parameters,
                    )
                )
                .mappings()
                .all()
            )
        return [
            {
                **dict(row),
                "price_min": float(row["price_min"]) if row["price_min"] is not None else None,
                "price_max": float(row["price_max"]) if row["price_max"] is not None else None,
            }
            for row in rows
        ]

    async def update_product_disposition(
        self,
        study_id: str,
        *,
        retailer_id: str,
        retailer_product_id: str,
        admission_status: str,
        reason: str,
        actor: str,
    ) -> StudyRecord:
        if admission_status not in {
            "provisionally_admitted",
            "excluded",
            "review_required",
        }:
            raise ValueError("unsupported product admission status")
        async with self._engine.begin() as connection:
            current = await self._locked(connection, study_id)
            if str(current["status"]) not in {"profile_ready", "pdp_estimated"}:
                raise StudyStateError("product dispositions lock when PDP enrichment begins")
            updated = await connection.execute(
                text(
                    """
                    UPDATE study_discovery_product SET admission_status = :admission_status,
                      admission_reason = :reason, updated_at = now()
                    WHERE study_id::text = :study_id AND retailer_id = :retailer_id
                      AND retailer_product_id = :product_id
                    RETURNING retailer_product_id
                    """
                ),
                {
                    "study_id": study_id,
                    "retailer_id": retailer_id,
                    "product_id": retailer_product_id,
                    "admission_status": admission_status,
                    "reason": reason[:1000],
                },
            )
            if updated.first() is None:
                raise StudyNotFoundError("study product was not found")
            counts = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT count(*)::integer AS unique_products,
                              COALESCE(sum(observation_count), 0)::integer AS raw_observations,
                              count(*) FILTER (
                                WHERE admission_status = 'provisionally_admitted'
                              )::integer AS admitted,
                              count(*) FILTER (
                                WHERE admission_status = 'excluded'
                              )::integer AS excluded,
                              count(*) FILTER (
                                WHERE admission_status = 'review_required'
                              )::integer AS review_required,
                              count(DISTINCT (
                                retailer_id,
                                brand_resolution->>'normalized_brand'
                              )) FILTER (
                                WHERE brand_resolution->>'status' = 'unresolved'
                                  AND COALESCE(
                                    brand_resolution->>'normalized_brand', ''
                                  ) <> ''
                              )::integer AS unknown_brands,
                              COALESCE(sum(
                                GREATEST(jsonb_array_length(price_contexts) - 1, 0)
                              ) FILTER (
                                WHERE admission_status = 'provisionally_admitted'
                              ), 0)::integer AS price_variant_contexts,
                              COALESCE(sum(jsonb_array_length(price_contexts)) FILTER (
                                WHERE admission_status = 'provisionally_admitted'
                              ), 0)::integer AS pdp_contexts
                            FROM study_discovery_product WHERE study_id::text = :study_id
                            """
                        ),
                        {"study_id": study_id},
                    )
                )
                .mappings()
                .one()
            )
            summary = {
                "raw_observations": int(counts["raw_observations"]),
                "unique_products": int(counts["unique_products"]),
                "provisionally_admitted_products": int(counts["admitted"]),
                "excluded_products": int(counts["excluded"]),
                "review_required_products": int(counts["review_required"]),
                "unknown_brands": int(counts["unknown_brands"]),
                "price_variant_contexts": int(counts["price_variant_contexts"]),
                "pdp_contexts": int(counts["pdp_contexts"]),
            }
            approval = dict(current["approval_state"])
            approval["pdp"] = _approval("not_requested", unit="credits")
            row = (
                (
                    await connection.execute(
                        text(
                            f"""
                            UPDATE study_discovery SET status = 'profile_ready',
                              profile_summary = CAST(:summary AS jsonb), pdp_estimate = NULL,
                              pdp_plan_checksum = NULL, pdp_run_id = NULL,
                              approval_state = CAST(:approval AS jsonb), updated_by = :actor,
                              updated_at = now() WHERE id::text = :study_id
                            RETURNING {self._returning_columns()}
                            """
                        ),
                        {
                            "study_id": study_id,
                            "summary": _json(summary),
                            "approval": _json(approval),
                            "actor": actor,
                        },
                    )
                )
                .mappings()
                .one()
            )
            await self._audit(
                connection,
                "study_product_disposition_changed",
                study_id,
                actor,
                {
                    "retailer_id": retailer_id,
                    "retailer_product_id": retailer_product_id,
                    "admission_status": admission_status,
                    "reason": reason[:1000],
                },
            )
        return _record(row)

    async def record_pdp_estimate(
        self,
        study_id: str,
        *,
        estimate: JsonObject,
        checksum: str,
        actor: str,
    ) -> StudyRecord:
        async with self._engine.begin() as connection:
            current = await self._locked(connection, study_id)
            if str(current["status"]) not in {"profile_ready", "pdp_estimated"}:
                raise StudyStateError("PDP can only be estimated after profiling")
            approval = dict(current["approval_state"])
            approval["pdp"] = _approval(
                "estimated",
                maximum_cost=float(estimate["estimated_credits"]),
                unit="credits",
            )
            row = (
                (
                    await connection.execute(
                        text(
                            f"""
                            UPDATE study_discovery SET status = 'pdp_estimated',
                              pdp_estimate = CAST(:estimate AS jsonb),
                              pdp_plan_checksum = :checksum,
                              approval_state = CAST(:approval AS jsonb), updated_by = :actor,
                              updated_at = now() WHERE id::text = :study_id
                            RETURNING {self._returning_columns()}
                            """
                        ),
                        {
                            "study_id": study_id,
                            "estimate": _json(estimate),
                            "checksum": checksum,
                            "approval": _json(approval),
                            "actor": actor,
                        },
                    )
                )
                .mappings()
                .one()
            )
        return _record(row)

    async def record_pdp_launch(
        self,
        study_id: str,
        *,
        pdp_run_id: str,
        approved_by: str,
    ) -> StudyRecord:
        async with self._engine.begin() as connection:
            current = await self._locked(connection, study_id)
            if str(current["status"]) != "pdp_estimated":
                raise StudyStateError("PDP must have a current estimate before approval")
            activated = await connection.execute(
                text(
                    "UPDATE product_detail_enrichment_run SET status = 'active' "
                    "WHERE id::text = :run_id AND status = 'planning' RETURNING id"
                ),
                {"run_id": pdp_run_id},
            )
            if activated.first() is None:
                raise StudyStateError("PDP run is not staged for activation")
            job_count = int(
                await connection.scalar(
                    text(
                        "SELECT count(*) FROM product_detail_job "
                        "WHERE enrichment_run_id = CAST(:run_id AS uuid)"
                    ),
                    {"run_id": pdp_run_id},
                )
                or 0
            )
            next_status = "enriching" if job_count else "profile_ready"
            if not job_count:
                await connection.execute(
                    text(
                        "UPDATE product_detail_enrichment_run SET status = 'completed', "
                        "completed_at = now() WHERE id::text = :run_id AND status = 'active'"
                    ),
                    {"run_id": pdp_run_id},
                )
            approval = dict(current["approval_state"])
            pdp = dict(approval["pdp"])
            pdp.update(
                {
                    "status": "consumed",
                    "approved_by": approved_by,
                    "approved_at": datetime.now(UTC).isoformat(),
                    "approved_checksum": str(current["pdp_plan_checksum"]),
                }
            )
            approval["pdp"] = pdp
            row = (
                (
                    await connection.execute(
                        text(
                            f"""
                            UPDATE study_discovery SET status = :next_status,
                              pdp_run_id = CAST(:run_id AS uuid),
                              approval_state = CAST(:approval AS jsonb), updated_by = :actor,
                              updated_at = now() WHERE id::text = :study_id
                            RETURNING {self._returning_columns()}
                            """
                        ),
                        {
                            "study_id": study_id,
                            "run_id": pdp_run_id,
                            "approval": _json(approval),
                            "actor": approved_by,
                            "next_status": next_status,
                        },
                    )
                )
                .mappings()
                .one()
            )
            await self._audit(
                connection,
                "study_pdp_approved",
                study_id,
                approved_by,
                {"pdp_run_id": pdp_run_id, "approval": pdp},
            )
        return _record(row)

    async def reconcile_enrichment(self) -> int:
        async with self._engine.begin() as connection:
            result = await connection.execute(
                text(
                    """
                    UPDATE study_discovery s SET status = CASE
                      WHEN s.product_pack_draft_id IS NULL THEN 'profile_ready'
                      ELSE 'draft_ready'
                    END, updated_at = now()
                    FROM product_detail_enrichment_run r
                    WHERE s.pdp_run_id = r.id AND s.status = 'enriching'
                      AND r.status IN ('completed','completed_with_errors')
                    RETURNING s.id
                    """
                )
            )
            return len(result.all())

    async def reconcile_product_pack_status(self) -> int:
        async with self._engine.begin() as connection:
            result = await connection.execute(
                text(
                    """
                    UPDATE study_discovery s SET status = CASE d.status
                      WHEN 'validating' THEN 'certifying'
                      WHEN 'certified' THEN 'certified'
                      WHEN 'published' THEN 'published'
                      ELSE 'draft_ready'
                    END, updated_at = now()
                    FROM product_pack_draft d
                    WHERE s.product_pack_draft_id = d.id
                      AND s.status IN ('draft_ready','certifying','certified')
                      AND s.status <> CASE d.status
                        WHEN 'validating' THEN 'certifying'
                        WHEN 'certified' THEN 'certified'
                        WHEN 'published' THEN 'published'
                        ELSE 'draft_ready'
                      END
                    RETURNING s.id
                    """
                )
            )
            return len(result.all())

    async def link_draft(self, study_id: str, draft_id: str, actor: str) -> StudyRecord:
        async with self._engine.begin() as connection:
            current = await self._locked(connection, study_id)
            if (
                str(current["status"]) == "draft_ready"
                and current["product_pack_draft_id"] is not None
                and str(current["product_pack_draft_id"]) == draft_id
            ):
                return _record(current)
            if str(current["status"]) != "profile_ready" or current["pdp_run_id"] is None:
                raise StudyStateError(
                    "a Product Pack draft requires completed PDP enrichment of admitted products"
                )
            run_status = await connection.scalar(
                text(
                    "SELECT status FROM product_detail_enrichment_run "
                    "WHERE id = CAST(:run_id AS uuid)"
                ),
                {"run_id": str(current["pdp_run_id"])},
            )
            if run_status not in {"completed", "completed_with_errors"}:
                raise StudyStateError("PDP enrichment must finish before a Product Pack draft")
            row = (
                (
                    await connection.execute(
                        text(
                            f"""
                            UPDATE study_discovery SET status = 'draft_ready',
                              product_pack_draft_id = CAST(:draft_id AS uuid), updated_by = :actor,
                              updated_at = now() WHERE id::text = :study_id
                            RETURNING {self._returning_columns()}
                            """
                        ),
                        {
                            "study_id": study_id,
                            "draft_id": draft_id,
                            "actor": actor,
                        },
                    )
                )
                .mappings()
                .one()
            )
        return _record(row)

    async def reopen_draft_handoff(self, study_id: str, actor: str) -> StudyRecord:
        """Detach a mutable candidate so corrected handoff logic can regenerate it."""

        async with self._engine.begin() as connection:
            current = await self._locked(connection, study_id)
            if current["product_pack_draft_id"] is None:
                return _record(current)
            if str(current["status"]) not in {"draft_ready", "certifying", "certified"}:
                raise StudyStateError("only an unpublished Product Pack handoff can be regenerated")
            draft_status = await connection.scalar(
                text("SELECT status FROM product_pack_draft WHERE id = CAST(:draft_id AS uuid)"),
                {"draft_id": str(current["product_pack_draft_id"])},
            )
            if draft_status == "published":
                raise StudyStateError("a published Product Pack handoff cannot be regenerated")
            row = (
                (
                    await connection.execute(
                        text(
                            f"""
                            UPDATE study_discovery SET status = 'profile_ready',
                              product_pack_draft_id = NULL, updated_by = :actor,
                              updated_at = now() WHERE id::text = :study_id
                            RETURNING {self._returning_columns()}
                            """
                        ),
                        {"study_id": study_id, "actor": actor},
                    )
                )
                .mappings()
                .one()
            )
            await self._audit(
                connection,
                "study_product_pack_handoff_reopened",
                study_id,
                actor,
                {"superseded_draft_id": str(current["product_pack_draft_id"])},
            )
        return _record(row)

    async def _locked(self, connection: AsyncConnection, study_id: str) -> RowMapping:
        row = (
            (
                await connection.execute(
                    text("SELECT * FROM study_discovery WHERE id::text = :study_id FOR UPDATE"),
                    {"study_id": study_id},
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise StudyNotFoundError(f"study {study_id!r} was not found")
        return row

    async def _audit(
        self,
        connection: AsyncConnection,
        event_type: str,
        study_id: str,
        actor: str,
        details: JsonObject,
    ) -> None:
        await connection.execute(
            text(
                """
                INSERT INTO audit_event (
                  organization_id, event_type, entity_type, entity_id, details
                ) VALUES (
                  CAST(:organization_id AS uuid), :event_type, 'study_discovery',
                  :study_id, CAST(:details AS jsonb)
                )
                """
            ),
            {
                "organization_id": self._organization_id,
                "event_type": event_type,
                "study_id": study_id,
                "actor": actor,
                "details": _json({"actor": actor, **details}),
            },
        )


def _approval(
    status: str,
    *,
    maximum_cost: float | int | None = None,
    unit: str | None = None,
) -> JsonObject:
    return {
        "status": status,
        "maximum_cost": maximum_cost,
        "unit": unit,
        "approved_by": None,
        "approved_at": None,
        "approved_checksum": None,
    }


def initial_approval_state() -> JsonObject:
    return {
        "search": _approval("not_requested", unit="credits"),
        "pdp": _approval("not_requested", unit="credits"),
        "ai": _approval("not_requested", unit="usd"),
    }
