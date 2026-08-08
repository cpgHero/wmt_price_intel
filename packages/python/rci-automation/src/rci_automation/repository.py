"""PostgreSQL automation persistence with leased SKIP LOCKED claims."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncEngine

from rci_automation.models import (
    AlertDefinitionRecord,
    AlertEvaluation,
    AlertEventRecord,
    AnalysisContext,
    EmailDeliveryRecord,
    JsonObject,
    ScheduleRecord,
    ScheduleSource,
)
from rci_results.models import AnalysisRecord

DEFAULT_ORGANIZATION_ID = "00000000-0000-0000-0000-000000000001"


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _schedule(row: RowMapping) -> ScheduleRecord:
    return ScheduleRecord(
        id=str(row["id"]),
        definition_id=str(row["definition_id"]),
        definition_key=str(row["definition_key"]),
        cron_expression=str(row["cron_expression"]),
        timezone=str(row["timezone"]),
        enabled=bool(row["enabled"]),
        next_run_at=row["next_run_at"],
        last_scheduled_for=row["last_scheduled_for"],
        last_collection_run_id=(
            str(row["last_collection_run_id"])
            if row["last_collection_run_id"] is not None
            else None
        ),
        lease_owner=str(row["lease_owner"]) if row["lease_owner"] is not None else None,
        lease_expires_at=row["lease_expires_at"],
        last_error=str(row["last_error"]) if row["last_error"] is not None else None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _alert(row: RowMapping) -> AlertDefinitionRecord:
    return AlertDefinitionRecord(
        id=str(row["id"]),
        stable_key=str(row["stable_key"]),
        name=str(row["name"]),
        active=bool(row["active"]),
        version_id=str(row["version_id"]),
        version=int(row["version"]),
        checksum=str(row["checksum"]),
        config=dict(row["config"]),
        created_at=row["created_at"],
    )


def _context(row: RowMapping) -> AnalysisContext:
    analysis = AnalysisRecord(
        id=str(row["result_id"]),
        analysis_run_id=str(row["analysis_run_id"]),
        analysis_id=str(row["analysis_id"]),
        collection_run_id=str(row["collection_run_id"]),
        status=str(row["analysis_status"]),
        product_pack_id=str(row["product_pack_id"]),
        product_pack_version=str(row["product_pack_version"]),
        schema_version=str(row["schema_version"]),
        checksum=str(row["analysis_checksum"]),
        result=dict(row["result"]),
        created_at=row["analysis_created_at"],
    )
    return AnalysisContext(
        analysis=analysis,
        analysis_result_id=str(row["result_id"]),
        collection_definition_id=str(row["collection_definition_id"]),
        collection_definition_key=str(row["collection_definition_key"]),
        collection_config=dict(row["collection_config"]),
    )


def _event(row: RowMapping | dict[str, Any]) -> AlertEventRecord:
    return AlertEventRecord(
        id=str(row["id"]),
        alert_definition_version_id=str(row["alert_definition_version_id"]),
        alert_key=str(row["alert_key"]),
        analysis_result_id=str(row["analysis_result_id"]),
        analysis_id=str(row["analysis_id"]),
        baseline_analysis_result_id=(
            str(row["baseline_analysis_result_id"])
            if row["baseline_analysis_result_id"] is not None
            else None
        ),
        baseline_analysis_id=(
            str(row["baseline_analysis_id"]) if row["baseline_analysis_id"] is not None else None
        ),
        status=str(row["status"]),
        current_value=Decimal(row["current_value"]) if row["current_value"] is not None else None,
        baseline_value=(
            Decimal(row["baseline_value"]) if row["baseline_value"] is not None else None
        ),
        change_value=Decimal(row["change_value"]) if row["change_value"] is not None else None,
        evidence=dict(row["evidence"]),
        created_at=row["created_at"],
    )


def _email(row: RowMapping) -> EmailDeliveryRecord:
    return EmailDeliveryRecord(
        id=str(row["id"]),
        alert_event_id=str(row["alert_event_id"]) if row["alert_event_id"] else None,
        analysis_result_id=str(row["analysis_result_id"]),
        analysis_id=str(row["analysis_id"]),
        delivery_type=str(row["delivery_type"]),
        recipients=tuple(str(value) for value in row["recipients"]),
        subject=str(row["subject"]),
        text_body=str(row["text_body"]),
        html_body=str(row["html_body"]) if row["html_body"] is not None else None,
        evidence=dict(row["evidence"]),
        idempotency_key=str(row["idempotency_key"]),
        status=str(row["status"]),
        attempt_count=int(row["attempt_count"]),
        max_attempts=int(row["max_attempts"]),
        available_at=row["available_at"],
        locked_by=str(row["locked_by"]) if row["locked_by"] is not None else None,
        lease_expires_at=row["lease_expires_at"],
        provider_message_id=(
            str(row["provider_message_id"]) if row["provider_message_id"] is not None else None
        ),
        last_error=str(row["last_error"]) if row["last_error"] is not None else None,
        created_at=row["created_at"],
        sent_at=row["sent_at"],
    )


_SCHEDULE_SELECT = """
SELECT s.*, d.stable_key AS definition_key
FROM collection_schedule s
JOIN collection_definition d ON d.id = s.definition_id
"""

_ALERT_SELECT = """
SELECT d.id::text AS id, d.stable_key, d.name, d.active,
       v.id::text AS version_id, v.version, v.checksum, v.config, v.created_at
FROM alert_definition d
JOIN LATERAL (
  SELECT * FROM alert_definition_version
  WHERE alert_definition_id = d.id ORDER BY version DESC LIMIT 1
) v ON true
"""

_CONTEXT_SELECT = """
SELECT r.id::text AS result_id, r.analysis_run_id::text AS analysis_run_id,
       r.analysis_id, ar.collection_run_id::text AS collection_run_id,
       ar.status AS analysis_status, ar.product_pack_id, ar.product_pack_version,
       r.schema_version, r.checksum AS analysis_checksum, r.result,
       r.created_at AS analysis_created_at,
       d.id::text AS collection_definition_id,
       d.stable_key AS collection_definition_key, cv.config AS collection_config
FROM analysis_result r
JOIN analysis_run ar ON ar.id = r.analysis_run_id
JOIN collection_run cr ON cr.id = ar.collection_run_id
JOIN collection_definition_version cv ON cv.id = cr.definition_version_id
JOIN collection_definition d ON d.id = cv.definition_id
"""

_EVENT_SELECT = """
SELECT e.*, d.stable_key AS alert_key, current.analysis_id,
       baseline.analysis_id AS baseline_analysis_id
FROM alert_event e
JOIN alert_definition_version v ON v.id = e.alert_definition_version_id
JOIN alert_definition d ON d.id = v.alert_definition_id
JOIN analysis_result current ON current.id = e.analysis_result_id
LEFT JOIN analysis_result baseline ON baseline.id = e.baseline_analysis_result_id
"""

_EMAIL_SELECT = """
SELECT e.*, r.analysis_id
FROM email_delivery e
JOIN analysis_result r ON r.id = e.analysis_result_id
"""


class PostgresAutomationRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def schedule_sources(self) -> list[ScheduleSource]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        SELECT d.id::text AS definition_id, d.stable_key, d.active, v.config
                        FROM collection_definition d
                        JOIN LATERAL (
                          SELECT config FROM collection_definition_version
                          WHERE definition_id = d.id ORDER BY version DESC LIMIT 1
                        ) v ON true
                        WHERE d.organization_id = CAST(:organization_id AS uuid)
                        ORDER BY d.stable_key
                        """
                    ),
                    {"organization_id": DEFAULT_ORGANIZATION_ID},
                )
            ).mappings()
            return [ScheduleSource(**dict(row)) for row in rows]

    async def upsert_schedule(
        self,
        source: ScheduleSource,
        *,
        cron_expression: str,
        timezone: str,
        enabled: bool,
        next_run_at: datetime,
    ) -> ScheduleRecord:
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                        INSERT INTO collection_schedule (
                          organization_id, definition_id, cron_expression, timezone,
                          enabled, next_run_at
                        ) VALUES (
                          CAST(:organization_id AS uuid), CAST(:definition_id AS uuid),
                          :cron_expression, :timezone, :enabled, :next_run_at
                        )
                        ON CONFLICT (definition_id) DO UPDATE SET
                          next_run_at = CASE
                            WHEN collection_schedule.cron_expression IS DISTINCT FROM
                                 EXCLUDED.cron_expression
                              OR collection_schedule.timezone IS DISTINCT FROM EXCLUDED.timezone
                            THEN EXCLUDED.next_run_at ELSE collection_schedule.next_run_at END,
                          cron_expression = EXCLUDED.cron_expression,
                          timezone = EXCLUDED.timezone, enabled = EXCLUDED.enabled,
                          updated_at = now()
                        RETURNING *, :definition_key AS definition_key
                        """
                        ),
                        {
                            "organization_id": DEFAULT_ORGANIZATION_ID,
                            "definition_id": source.definition_id,
                            "definition_key": source.stable_key,
                            "cron_expression": cron_expression,
                            "timezone": timezone,
                            "enabled": enabled,
                            "next_run_at": next_run_at,
                        },
                    )
                )
                .mappings()
                .one()
            )
            return _schedule(row)

    async def disable_schedule(self, definition_id: str) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE collection_schedule SET enabled = false, updated_at = now(), "
                    "lease_owner = NULL, lease_expires_at = NULL "
                    "WHERE definition_id::text = :definition_id"
                ),
                {"definition_id": definition_id},
            )

    async def list_schedules(self) -> list[ScheduleRecord]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(text(f"{_SCHEDULE_SELECT} ORDER BY d.stable_key"))
            ).mappings()
            return [_schedule(row) for row in rows]

    async def claim_due_schedules(
        self, worker_id: str, *, limit: int, lease_seconds: int
    ) -> list[ScheduleRecord]:
        async with self._engine.begin() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        WITH candidates AS (
                          SELECT id FROM collection_schedule
                          WHERE enabled AND next_run_at <= now()
                            AND (lease_expires_at IS NULL OR lease_expires_at <= now())
                          ORDER BY next_run_at, id FOR UPDATE SKIP LOCKED LIMIT :limit
                        ), claimed AS (
                          UPDATE collection_schedule s
                          SET lease_owner = :worker_id,
                              lease_expires_at = now() + make_interval(secs => :lease_seconds),
                              updated_at = now()
                          FROM candidates c WHERE s.id = c.id RETURNING s.*
                        )
                        SELECT claimed.*, d.stable_key AS definition_key
                        FROM claimed JOIN collection_definition d ON d.id = claimed.definition_id
                        ORDER BY claimed.next_run_at
                        """
                    ),
                    {"worker_id": worker_id, "lease_seconds": lease_seconds, "limit": limit},
                )
            ).mappings()
            return [_schedule(row) for row in rows]

    async def complete_schedule(
        self,
        schedule: ScheduleRecord,
        *,
        next_run_at: datetime,
        collection_run_id: str | None,
        error: str | None,
    ) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    UPDATE collection_schedule SET next_run_at = :next_run_at,
                      last_scheduled_for = :scheduled_for,
                      last_collection_run_id = COALESCE(
                        CAST(:collection_run_id AS uuid), last_collection_run_id
                      ),
                      last_error = :error, lease_owner = NULL, lease_expires_at = NULL,
                      updated_at = now()
                    WHERE id::text = :id AND lease_owner = :lease_owner
                    """
                ),
                {
                    "id": schedule.id,
                    "lease_owner": schedule.lease_owner,
                    "next_run_at": next_run_at,
                    "scheduled_for": schedule.next_run_at,
                    "collection_run_id": collection_run_id,
                    "error": error,
                },
            )

    async def publish_alert(self, config: JsonObject, checksum: str) -> AlertDefinitionRecord:
        stable_key = str(config["id"])
        async with self._engine.begin() as connection:
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"alert:{stable_key}"},
            )
            definition_id = (
                await connection.execute(
                    text(
                        """
                        INSERT INTO alert_definition (
                          organization_id, stable_key, name, active
                        ) VALUES (
                          CAST(:organization_id AS uuid), :stable_key, :name, :active
                        ) ON CONFLICT (organization_id, stable_key) DO UPDATE
                          SET name = EXCLUDED.name, active = EXCLUDED.active
                        RETURNING id::text
                        """
                    ),
                    {
                        "organization_id": DEFAULT_ORGANIZATION_ID,
                        "stable_key": stable_key,
                        "name": str(config["name"]),
                        "active": bool(config["enabled"]),
                    },
                )
            ).scalar_one()
            existing = (
                (
                    await connection.execute(
                        text(
                            f"{_ALERT_SELECT} WHERE d.id::text = :definition_id "
                            "AND v.checksum = :checksum"
                        ),
                        {"definition_id": definition_id, "checksum": checksum},
                    )
                )
                .mappings()
                .first()
            )
            if existing is not None:
                return _alert(existing)
            version = int(
                (
                    await connection.execute(
                        text(
                            "SELECT COALESCE(max(version), 0) + 1 "
                            "FROM alert_definition_version "
                            "WHERE alert_definition_id::text = :definition_id"
                        ),
                        {"definition_id": definition_id},
                    )
                ).scalar_one()
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO alert_definition_version (
                      alert_definition_id, version, config, checksum
                    ) VALUES (
                      CAST(:definition_id AS uuid), :version, CAST(:config AS jsonb), :checksum
                    )
                    """
                ),
                {
                    "definition_id": definition_id,
                    "version": version,
                    "config": _json(config),
                    "checksum": checksum,
                },
            )
            row = (
                (
                    await connection.execute(
                        text(f"{_ALERT_SELECT} WHERE d.id::text = :definition_id"),
                        {"definition_id": definition_id},
                    )
                )
                .mappings()
                .one()
            )
            return _alert(row)

    async def list_alerts(self) -> list[AlertDefinitionRecord]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        f"{_ALERT_SELECT} WHERE d.organization_id = "
                        "CAST(:organization_id AS uuid) ORDER BY d.stable_key"
                    ),
                    {"organization_id": DEFAULT_ORGANIZATION_ID},
                )
            ).mappings()
            return [_alert(row) for row in rows]

    async def list_alert_events(self, limit: int = 100) -> list[AlertEventRecord]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(f"{_EVENT_SELECT} ORDER BY e.created_at DESC LIMIT :limit"),
                    {"limit": limit},
                )
            ).mappings()
            return [_event(row) for row in rows]

    async def get_analysis(self, identifier: str) -> AnalysisContext | None:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            f"{_CONTEXT_SELECT} WHERE r.analysis_id = :identifier "
                            "OR r.id::text = :identifier"
                        ),
                        {"identifier": identifier},
                    )
                )
                .mappings()
                .first()
            )
            return _context(row) if row is not None else None

    async def previous_analysis(self, current: AnalysisContext) -> AnalysisContext | None:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            f"{_CONTEXT_SELECT} WHERE d.id::text = :definition_id "
                            "AND ar.product_pack_id = :product_pack_id "
                            "AND r.created_at < :created_at ORDER BY r.created_at DESC LIMIT 1"
                        ),
                        {
                            "definition_id": current.collection_definition_id,
                            "product_pack_id": current.analysis.product_pack_id,
                            "created_at": current.analysis.created_at,
                        },
                    )
                )
                .mappings()
                .first()
            )
            return _context(row) if row is not None else None

    async def claim_analyses(
        self, worker_id: str, *, limit: int, lease_seconds: int
    ) -> list[AnalysisContext]:
        async with self._engine.begin() as connection:
            ids = list(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT r.id::text
                            FROM analysis_result r
                            LEFT JOIN analysis_automation_state s ON s.analysis_result_id = r.id
                            WHERE s.analysis_result_id IS NULL OR s.status = 'failed'
                               OR (s.status = 'processing' AND s.lease_expires_at <= now())
                            ORDER BY r.created_at, r.id
                            FOR UPDATE OF r SKIP LOCKED LIMIT :limit
                            """
                        ),
                        {"limit": limit},
                    )
                ).scalars()
            )
            if not ids:
                return []
            await connection.execute(
                text(
                    """
                    INSERT INTO analysis_automation_state (
                      analysis_result_id, status, locked_by, lease_expires_at
                    ) SELECT value::uuid, 'processing', :worker_id,
                      now() + make_interval(secs => :lease_seconds)
                    FROM unnest(CAST(:ids AS text[])) value
                    ON CONFLICT (analysis_result_id) DO UPDATE SET
                      status = 'processing', locked_by = EXCLUDED.locked_by,
                      lease_expires_at = EXCLUDED.lease_expires_at, last_error = NULL
                    """
                ),
                {"ids": ids, "worker_id": worker_id, "lease_seconds": lease_seconds},
            )
            rows = (
                await connection.execute(
                    text(f"{_CONTEXT_SELECT} WHERE r.id = ANY(CAST(:ids AS uuid[]))"),
                    {"ids": ids},
                )
            ).mappings()
            return [_context(row) for row in rows]

    async def complete_analysis(
        self, analysis_result_id: str, worker_id: str, error: str | None
    ) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    UPDATE analysis_automation_state
                    SET status = :status, locked_by = NULL, lease_expires_at = NULL,
                        last_error = CAST(:error AS text),
                        evaluated_at = CASE
                          WHEN CAST(:error AS text) IS NULL THEN now()
                          ELSE evaluated_at
                        END
                    WHERE analysis_result_id::text = :id AND locked_by = :worker_id
                    """
                ),
                {
                    "id": analysis_result_id,
                    "worker_id": worker_id,
                    "status": "failed" if error else "processed",
                    "error": error,
                },
            )

    async def record_alert_event(
        self,
        definition: AlertDefinitionRecord,
        current: AnalysisContext,
        baseline: AnalysisContext | None,
        evaluation: AlertEvaluation,
        *,
        cooldown_minutes: int,
    ) -> AlertEventRecord:
        async with self._engine.begin() as connection:
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"alert-cooldown:{definition.id}"},
            )
            suppressed = False
            if evaluation.triggered and cooldown_minutes > 0:
                suppressed = bool(
                    (
                        await connection.execute(
                            text(
                                """
                                SELECT 1 FROM alert_event e
                                JOIN alert_definition_version v
                                  ON v.id = e.alert_definition_version_id
                                WHERE v.alert_definition_id::text = :definition_id
                                  AND e.status = 'triggered'
                                  AND e.created_at >= now() - make_interval(mins => :minutes)
                                LIMIT 1
                                """
                            ),
                            {
                                "definition_id": definition.id,
                                "minutes": cooldown_minutes,
                            },
                        )
                    ).scalar_one_or_none()
                )
            status = (
                "suppressed"
                if suppressed
                else ("triggered" if evaluation.triggered else "not_triggered")
            )
            row = (
                (
                    await connection.execute(
                        text(
                            """
                        INSERT INTO alert_event (
                          alert_definition_version_id, analysis_result_id,
                          baseline_analysis_result_id, status, current_value,
                          baseline_value, change_value, evidence
                        ) VALUES (
                          CAST(:version_id AS uuid), CAST(:analysis_result_id AS uuid),
                          CAST(:baseline_id AS uuid), :status, :current_value,
                          :baseline_value, :change_value, CAST(:evidence AS jsonb)
                        ) ON CONFLICT (
                          alert_definition_version_id, analysis_result_id
                        ) DO UPDATE SET status = alert_event.status
                        RETURNING *
                        """
                        ),
                        {
                            "version_id": definition.version_id,
                            "analysis_result_id": current.analysis_result_id,
                            "baseline_id": baseline.analysis_result_id if baseline else None,
                            "status": status,
                            "current_value": evaluation.current_value,
                            "baseline_value": evaluation.baseline_value,
                            "change_value": evaluation.change_value,
                            "evidence": _json(evaluation.evidence),
                        },
                    )
                )
                .mappings()
                .one()
            )
            combined = dict(row)
            combined.update(
                {
                    "alert_key": definition.stable_key,
                    "analysis_id": current.analysis.analysis_id,
                    "baseline_analysis_id": (
                        baseline.analysis.analysis_id if baseline is not None else None
                    ),
                }
            )
            return _event(combined)

    async def enqueue_email(
        self,
        current: AnalysisContext,
        *,
        alert_event: AlertEventRecord | None,
        delivery_type: str,
        recipients: tuple[str, ...],
        subject: str,
        text_body: str,
        html_body: str | None,
        evidence: JsonObject,
        idempotency_key: str,
    ) -> EmailDeliveryRecord:
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                        WITH inserted AS (
                          INSERT INTO email_delivery (
                            alert_event_id, analysis_result_id, delivery_type, recipients,
                            subject, text_body, html_body, evidence, idempotency_key
                          ) VALUES (
                            CAST(:alert_event_id AS uuid), CAST(:analysis_result_id AS uuid),
                            :delivery_type, CAST(:recipients AS jsonb), :subject, :text_body,
                            :html_body, CAST(:evidence AS jsonb), :idempotency_key
                          ) ON CONFLICT (idempotency_key) DO UPDATE
                            SET idempotency_key = email_delivery.idempotency_key
                          RETURNING *
                        )
                        SELECT inserted.*, r.analysis_id FROM inserted
                        JOIN analysis_result r ON r.id = inserted.analysis_result_id
                        """
                        ),
                        {
                            "alert_event_id": alert_event.id if alert_event else None,
                            "analysis_result_id": current.analysis_result_id,
                            "delivery_type": delivery_type,
                            "recipients": _json(list(recipients)),
                            "subject": subject,
                            "text_body": text_body,
                            "html_body": html_body,
                            "evidence": _json(evidence),
                            "idempotency_key": idempotency_key,
                        },
                    )
                )
                .mappings()
                .one()
            )
            return _email(row)

    async def claim_emails(
        self, worker_id: str, *, limit: int, lease_seconds: int
    ) -> list[EmailDeliveryRecord]:
        async with self._engine.begin() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        WITH candidates AS (
                          SELECT id FROM email_delivery
                          WHERE attempt_count < max_attempts AND (
                            (status = 'pending' AND available_at <= now()) OR
                            (status = 'sending' AND lease_expires_at <= now())
                          ) ORDER BY created_at, id FOR UPDATE SKIP LOCKED LIMIT :limit
                        ), claimed AS (
                          UPDATE email_delivery e SET status = 'sending',
                            attempt_count = attempt_count + 1, locked_by = :worker_id,
                            lease_expires_at = now() + make_interval(secs => :lease_seconds)
                          FROM candidates c WHERE e.id = c.id RETURNING e.*
                        )
                        SELECT claimed.*, r.analysis_id FROM claimed
                        JOIN analysis_result r ON r.id = claimed.analysis_result_id
                        ORDER BY claimed.created_at
                        """
                    ),
                    {"worker_id": worker_id, "lease_seconds": lease_seconds, "limit": limit},
                )
            ).mappings()
            return [_email(row) for row in rows]

    async def complete_email(
        self,
        delivery_id: str,
        worker_id: str,
        *,
        provider_message_id: str | None,
        error: str | None,
        retry_delay_seconds: int,
    ) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    UPDATE email_delivery SET
                      status = CASE WHEN :error IS NULL THEN 'sent'
                        WHEN attempt_count >= max_attempts THEN 'failed' ELSE 'pending' END,
                      available_at = now() + make_interval(secs => :retry_delay),
                      locked_by = NULL, lease_expires_at = NULL,
                      provider_message_id = :message_id, last_error = :error,
                      sent_at = CASE WHEN :error IS NULL THEN now() ELSE NULL END
                    WHERE id::text = :id AND locked_by = :worker_id
                    """
                ),
                {
                    "id": delivery_id,
                    "worker_id": worker_id,
                    "message_id": provider_message_id,
                    "error": error,
                    "retry_delay": retry_delay_seconds,
                },
            )

    async def list_email_deliveries(self, limit: int = 100) -> list[EmailDeliveryRecord]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(f"{_EMAIL_SELECT} ORDER BY e.created_at DESC LIMIT :limit"),
                    {"limit": limit},
                )
            ).mappings()
            return [_email(row) for row in rows]
