"""Postgres implementation of location import and query ports."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from rci_locations.eligibility import eligibility_plan_sha256, eligibility_snapshot_sha256
from rci_locations.models import (
    EligibilityReconciliationPlan,
    ImportState,
    ImportSummary,
    LocationEligibilityState,
    LocationRecord,
    LocationSearchResult,
    RetailerAlias,
    RetailerCount,
    RetailerDefinition,
)

LOCATION_POLICY_LOCK_NAMESPACE = 1_381_124_633
LOCATION_POLICY_LOCK_KEY = 1


class PostgresLocationRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    @asynccontextmanager
    async def location_policy_operation_lock(self) -> AsyncIterator[None]:
        """Serialize whole imports and eligibility applies across service replicas."""

        async with self._engine.connect() as connection:
            await connection.execute(
                text("SELECT pg_advisory_lock(:namespace, :lock_key)"),
                {
                    "namespace": LOCATION_POLICY_LOCK_NAMESPACE,
                    "lock_key": LOCATION_POLICY_LOCK_KEY,
                },
            )
            body_error: BaseException | None = None
            try:
                yield
            except BaseException as exc:
                body_error = exc
                raise
            finally:
                try:
                    unlocked = await connection.scalar(
                        text("SELECT pg_advisory_unlock(:namespace, :lock_key)"),
                        {
                            "namespace": LOCATION_POLICY_LOCK_NAMESPACE,
                            "lock_key": LOCATION_POLICY_LOCK_KEY,
                        },
                    )
                    if unlocked is not True:
                        raise RuntimeError("location policy operation lock was not held")
                except BaseException:
                    # A session lock survives a pooled transaction reset. Force-close the
                    # physical connection if normal unlock cannot be proven.
                    await connection.invalidate()
                    if body_error is None:
                        raise

    async def begin_import(self, source_path: str, source_sha256: str) -> str:
        statement = text(
            """
            INSERT INTO location_import_run (source_path, source_sha256, status)
            VALUES (:source_path, :source_sha256, 'running')
            RETURNING id::text
            """
        )
        async with self._engine.begin() as connection:
            result = await connection.execute(
                statement,
                {"source_path": source_path, "source_sha256": source_sha256},
            )
            return str(result.scalar_one())

    async def upsert_retailers(
        self,
        retailers: Sequence[RetailerDefinition],
        aliases: Sequence[RetailerAlias],
    ) -> None:
        retailer_statement = text(
            """
            INSERT INTO retailer (id, display_name, country, active, catalogued)
            VALUES (:id, :display_name, :country, :active, :catalogued)
            ON CONFLICT (id) DO UPDATE SET
              display_name = EXCLUDED.display_name,
              country = EXCLUDED.country,
              active = EXCLUDED.active,
              catalogued = EXCLUDED.catalogued
            """
        )
        alias_statement = text(
            """
            INSERT INTO retailer_alias (alias, country, retailer_id)
            VALUES (:alias, :country, :retailer_id)
            ON CONFLICT (alias, country) DO UPDATE SET retailer_id = EXCLUDED.retailer_id
            """
        )
        async with self._engine.begin() as connection:
            if retailers:
                await connection.execute(
                    retailer_statement,
                    [
                        {
                            "id": item.id,
                            "display_name": item.display_name,
                            "country": item.country,
                            "active": item.active,
                            "catalogued": item.catalogued,
                        }
                        for item in retailers
                    ],
                )
            if aliases:
                await connection.execute(
                    alias_statement,
                    [
                        {
                            "alias": item.alias,
                            "country": item.country,
                            "retailer_id": item.retailer_id,
                        }
                        for item in aliases
                    ],
                )

    async def upsert_locations(self, import_id: str, locations: Sequence[LocationRecord]) -> None:
        statement = text(
            """
            INSERT INTO retailer_location (
              retailer_id, provider, provider_location_id, store_number, store_name,
              raw_zipcode, zipcode, street, address, city, state, county, country,
              latitude, longitude, status, collection_eligible,
              collection_eligibility_reason, source_created_at, source_row_id,
              last_import_id, raw_row
            ) VALUES (
              :retailer_id, :provider, :provider_location_id, :store_number, :store_name,
              :raw_zipcode, :zipcode, :street, :address, :city, :state, :county, :country,
              :latitude, :longitude, :status, :collection_eligible,
              :collection_eligibility_reason, :source_created_at, :source_row_id,
              CAST(:last_import_id AS uuid), CAST(:raw_row AS jsonb)
            )
            ON CONFLICT (retailer_id, provider, store_number, country) DO UPDATE SET
              provider_location_id = EXCLUDED.provider_location_id,
              store_name = EXCLUDED.store_name,
              raw_zipcode = EXCLUDED.raw_zipcode,
              zipcode = EXCLUDED.zipcode,
              street = EXCLUDED.street,
              address = EXCLUDED.address,
              city = EXCLUDED.city,
              state = EXCLUDED.state,
              county = EXCLUDED.county,
              latitude = EXCLUDED.latitude,
              longitude = EXCLUDED.longitude,
              status = EXCLUDED.status,
              collection_eligible = EXCLUDED.collection_eligible,
              collection_eligibility_reason = EXCLUDED.collection_eligibility_reason,
              source_created_at = EXCLUDED.source_created_at,
              source_row_id = EXCLUDED.source_row_id,
              last_import_id = EXCLUDED.last_import_id,
              imported_at = now(),
              raw_row = EXCLUDED.raw_row
            """
        )
        parameters = [self._location_parameters(import_id, item) for item in locations]
        async with self._engine.begin() as connection:
            if parameters:
                await connection.execute(statement, parameters)

    @staticmethod
    def _location_parameters(import_id: str, item: LocationRecord) -> dict[str, Any]:
        return {
            "retailer_id": item.retailer_id,
            "provider": item.provider,
            "provider_location_id": item.provider_location_id,
            "store_number": item.store_number,
            "store_name": item.store_name,
            "raw_zipcode": item.raw_zipcode,
            "zipcode": item.zipcode,
            "street": item.street,
            "address": item.address,
            "city": item.city,
            "state": item.state,
            "county": item.county,
            "country": item.country,
            "latitude": item.latitude,
            "longitude": item.longitude,
            "status": item.status,
            "collection_eligible": item.collection_eligible,
            "collection_eligibility_reason": item.collection_eligibility_reason,
            "source_created_at": item.source_created_at,
            "source_row_id": item.source_row_id,
            "last_import_id": import_id,
            "raw_row": json.dumps(item.raw_row, ensure_ascii=False, separators=(",", ":")),
        }

    async def retire_missing_locations(self, import_id: str, retailer_ids: Sequence[str]) -> None:
        if not retailer_ids:
            return
        statement = text(
            """
            UPDATE retailer_location
            SET status = 'superseded',
                collection_eligible = false,
                collection_eligibility_reason = 'superseded_by_authoritative_import',
                imported_at = now()
            WHERE retailer_id = ANY(CAST(:retailer_ids AS text[]))
              AND last_import_id IS DISTINCT FROM CAST(:import_id AS uuid)
            """
        )
        async with self._engine.begin() as connection:
            await connection.execute(
                statement,
                {"import_id": import_id, "retailer_ids": list(retailer_ids)},
            )

    async def complete_import(self, summary: ImportSummary) -> None:
        statement = text(
            """
            UPDATE location_import_run
            SET status = 'completed', total_rows = :total_rows,
                imported_rows = :imported_rows, skipped_rows = :skipped_rows,
                retailer_count = :retailer_count, completed_at = now()
            WHERE id = CAST(:id AS uuid)
            """
        )
        async with self._engine.begin() as connection:
            await connection.execute(
                statement,
                {
                    "id": summary.import_id,
                    "total_rows": summary.total_rows,
                    "imported_rows": summary.imported_rows,
                    "skipped_rows": summary.skipped_rows,
                    "retailer_count": summary.retailer_count,
                },
            )

    async def update_import_progress(
        self,
        import_id: str,
        *,
        total_rows: int,
        imported_rows: int,
        skipped_rows: int,
        retailer_count: int,
    ) -> None:
        statement = text(
            """
            UPDATE location_import_run
            SET total_rows = :total_rows, imported_rows = :imported_rows,
                skipped_rows = :skipped_rows, retailer_count = :retailer_count
            WHERE id = CAST(:id AS uuid) AND status = 'running'
            """
        )
        async with self._engine.begin() as connection:
            await connection.execute(
                statement,
                {
                    "id": import_id,
                    "total_rows": total_rows,
                    "imported_rows": imported_rows,
                    "skipped_rows": skipped_rows,
                    "retailer_count": retailer_count,
                },
            )

    async def fail_import(self, import_id: str, error_message: str) -> None:
        statement = text(
            """
            UPDATE location_import_run
            SET status = 'failed', error_message = :error_message, completed_at = now()
            WHERE id = CAST(:id AS uuid)
            """
        )
        async with self._engine.begin() as connection:
            await connection.execute(
                statement,
                {"id": import_id, "error_message": error_message[:4_000]},
            )

    async def list_retailers(self, country: str | None = None) -> list[RetailerCount]:
        statement = text(
            """
            SELECT r.id, r.display_name, r.country, r.active, r.catalogued,
                   count(l.id)::integer AS location_count
            FROM retailer r
            LEFT JOIN retailer_location l
              ON l.retailer_id = r.id AND l.collection_eligible
            WHERE (:country IS NULL OR r.country = :country)
            GROUP BY r.id, r.display_name, r.country, r.active, r.catalogued
            ORDER BY r.display_name, r.country, r.id
            """
        )
        async with self._engine.connect() as connection:
            rows = (await connection.execute(statement, {"country": country})).mappings()
            return [RetailerCount(**dict(row)) for row in rows]

    async def count_locations(self, retailer_id: str) -> int:
        statement = text(
            "SELECT count(*)::integer FROM retailer_location "
            "WHERE retailer_id = :retailer_id AND collection_eligible"
        )
        async with self._engine.connect() as connection:
            result = await connection.execute(statement, {"retailer_id": retailer_id})
            return int(result.scalar_one())

    async def search_locations(
        self,
        *,
        retailer_id: str | None,
        country: str | None,
        query: str | None,
        zipcode: str | None,
        limit: int,
        offset: int,
    ) -> list[LocationSearchResult]:
        statement = text(
            """
            SELECT id::text AS id, retailer_id, provider, provider_location_id,
                   store_number, store_name, raw_zipcode, zipcode, city, state,
                   country, latitude, longitude
            FROM retailer_location
            WHERE collection_eligible
              AND (:retailer_id IS NULL OR retailer_id = :retailer_id)
              AND (:country IS NULL OR country = :country)
              AND (:zipcode IS NULL OR zipcode = :zipcode)
              AND (
                :query IS NULL OR
                concat_ws(' ', store_number, store_name, address, city, state) ILIKE
                  ('%' || :query || '%')
              )
            ORDER BY retailer_id, store_number, id
            LIMIT :limit OFFSET :offset
            """
        )
        parameters = {
            "retailer_id": retailer_id,
            "country": country,
            "query": query,
            "zipcode": zipcode,
            "limit": limit,
            "offset": offset,
        }
        async with self._engine.connect() as connection:
            rows = (await connection.execute(statement, parameters)).mappings()
            return [LocationSearchResult(**dict(row)) for row in rows]

    async def list_imports(self, limit: int = 20) -> list[ImportState]:
        statement = text(
            """
            SELECT id::text AS id, source_path, source_sha256, status, total_rows,
                   imported_rows, skipped_rows, retailer_count, error_message,
                   started_at, completed_at
            FROM location_import_run
            ORDER BY started_at DESC
            LIMIT :limit
            """
        )
        async with self._engine.connect() as connection:
            rows = (await connection.execute(statement, {"limit": limit})).mappings()
            return [ImportState(**dict(row)) for row in rows]

    @staticmethod
    async def _location_eligibility_states(
        connection: AsyncConnection,
        retailer_ids: Sequence[str],
    ) -> list[LocationEligibilityState]:
        statement = text(
            """
            SELECT id::text AS id, retailer_id, store_number, status,
                   collection_eligible, collection_eligibility_reason
            FROM retailer_location
            WHERE cardinality(CAST(:retailer_ids AS text[])) = 0
               OR retailer_id = ANY(CAST(:retailer_ids AS text[]))
            ORDER BY id
            """
        )
        rows = (
            await connection.execute(statement, {"retailer_ids": list(retailer_ids)})
        ).mappings()
        return [LocationEligibilityState(**dict(row)) for row in rows]

    async def list_location_eligibility_states(
        self,
        retailer_ids: Sequence[str],
    ) -> list[LocationEligibilityState]:
        async with self._engine.connect() as connection:
            return await self._location_eligibility_states(connection, retailer_ids)

    async def begin_eligibility_reconciliation(
        self,
        plan: EligibilityReconciliationPlan,
        *,
        requested_by: str,
        change_reason: str,
    ) -> str:
        statement = text(
            """
            INSERT INTO location_eligibility_reconciliation_run (
              catalog_path, catalog_sha256, snapshot_sha256, reviewed_plan_sha256,
              retailer_ids,
              requested_by, change_reason, status, scanned_rows, changed_rows,
              eligible_before, eligible_after, enabled_rows, disabled_rows,
              reason_counts_before, reason_counts_after, changes
            ) VALUES (
              :catalog_path, :catalog_sha256, :snapshot_sha256, :reviewed_plan_sha256,
              CAST(:retailer_ids AS text[]), :requested_by, :change_reason,
              'running', :scanned_rows, :changed_rows, :eligible_before,
              :eligible_after, :enabled_rows, :disabled_rows,
              CAST(:reason_counts_before AS jsonb),
              CAST(:reason_counts_after AS jsonb), CAST(:changes AS jsonb)
            )
            RETURNING id::text
            """
        )
        parameters = {
            "catalog_path": plan.catalog_path,
            "catalog_sha256": plan.catalog_sha256,
            "snapshot_sha256": plan.snapshot_sha256,
            "reviewed_plan_sha256": eligibility_plan_sha256(plan),
            "retailer_ids": list(plan.retailer_ids),
            "requested_by": requested_by,
            "change_reason": change_reason,
            "scanned_rows": plan.scanned_rows,
            "changed_rows": plan.changed_rows,
            "eligible_before": plan.eligible_before,
            "eligible_after": plan.eligible_after,
            "enabled_rows": plan.enabled_rows,
            "disabled_rows": plan.disabled_rows,
            "reason_counts_before": json.dumps(plan.reason_counts_before, sort_keys=True),
            "reason_counts_after": json.dumps(plan.reason_counts_after, sort_keys=True),
            "changes": json.dumps(
                [asdict(change) for change in plan.changes],
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
        }
        async with self._engine.begin() as connection:
            result = await connection.execute(statement, parameters)
            return str(result.scalar_one())

    async def apply_eligibility_reconciliation(
        self,
        audit_run_id: str,
        plan: EligibilityReconciliationPlan,
    ) -> None:
        async with self._engine.begin() as connection:
            # Block concurrent location imports while the planned snapshot is rechecked
            # and the complete correction set is applied atomically.
            await connection.execute(
                text("LOCK TABLE retailer_location IN SHARE ROW EXCLUSIVE MODE")
            )
            current = await self._location_eligibility_states(
                connection,
                plan.retailer_ids,
            )
            current_sha256 = eligibility_snapshot_sha256(current)
            if current_sha256 != plan.snapshot_sha256:
                raise RuntimeError(
                    "location eligibility snapshot changed after dry run; rerun reconciliation"
                )

            if plan.changes:
                update_statement = text(
                    """
                    WITH proposed AS (
                      SELECT *
                      FROM jsonb_to_recordset(CAST(:changes AS jsonb)) AS proposed_row(
                        id uuid,
                        status text,
                        before_eligible boolean,
                        before_reason text,
                        after_eligible boolean,
                        after_reason text
                      )
                    ), updated AS (
                      UPDATE retailer_location AS location
                      SET collection_eligible = proposed.after_eligible,
                          collection_eligibility_reason = proposed.after_reason
                      FROM proposed
                      WHERE location.id = proposed.id
                        AND location.status IS NOT DISTINCT FROM proposed.status
                        AND location.collection_eligible IS NOT DISTINCT FROM
                            proposed.before_eligible
                        AND location.collection_eligibility_reason IS NOT DISTINCT FROM
                            proposed.before_reason
                      RETURNING location.id
                    )
                    SELECT count(*)::integer FROM updated
                    """
                )
                changes = [
                    {
                        "id": change.id,
                        "status": change.status,
                        "before_eligible": change.before_eligible,
                        "before_reason": change.before_reason,
                        "after_eligible": change.after_eligible,
                        "after_reason": change.after_reason,
                    }
                    for change in plan.changes
                ]
                updated = int(
                    (
                        await connection.execute(
                            update_statement,
                            {
                                "changes": json.dumps(
                                    changes,
                                    ensure_ascii=False,
                                    separators=(",", ":"),
                                    sort_keys=True,
                                )
                            },
                        )
                    ).scalar_one()
                )
                if updated != plan.changed_rows:
                    raise RuntimeError(
                        "location eligibility update count did not match the audited plan: "
                        f"expected {plan.changed_rows}, updated {updated}"
                    )

            completed = await connection.execute(
                text(
                    """
                    UPDATE location_eligibility_reconciliation_run
                    SET status = 'completed', completed_at = now()
                    WHERE id = CAST(:id AS uuid) AND status = 'running'
                    RETURNING id
                    """
                ),
                {"id": audit_run_id},
            )
            if completed.scalar_one_or_none() is None:
                raise RuntimeError("eligibility reconciliation audit run is not applyable")

    async def fail_eligibility_reconciliation(
        self,
        audit_run_id: str,
        error_message: str,
    ) -> None:
        statement = text(
            """
            UPDATE location_eligibility_reconciliation_run
            SET status = 'failed', error_message = :error_message, completed_at = now()
            WHERE id = CAST(:id AS uuid) AND status = 'running'
            """
        )
        async with self._engine.begin() as connection:
            await connection.execute(
                statement,
                {"id": audit_run_id, "error_message": error_message[:4_000]},
            )
