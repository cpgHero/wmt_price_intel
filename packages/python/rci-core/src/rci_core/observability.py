"""Structured service logging with explicit safe context fields and secret redaction."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import UTC, datetime
from typing import Final

_SECRET_PATTERNS: Final = (
    re.compile(r"(?i)(x-api-key=)[^&\s]+"),
    re.compile(r"(?i)(METRICSCART_API_KEY=)[^&\s]+"),
    re.compile(r"(?i)(OPENAI_API_KEY=)[^&\s]+"),
    re.compile(r"(?i)(SMTP_PASSWORD=)[^&\s]+"),
    re.compile(r"(?i)(OBJECT_STORAGE_SECRET_ACCESS_KEY=)[^&\s]+"),
    re.compile(r"(?i)(APP_SESSION_SECRET=)[^&\s]+"),
)
_CONTEXT_FIELDS: Final = (
    "event",
    "run_id",
    "task_id",
    "retailer_id",
    "location_key",
    "page",
    "worker_id",
    "attempt",
    "status",
    "http_status",
    "result_count",
    "failure_class",
    "latency_ms",
    "claimed_tasks",
    "failure_count",
    "scheduled_runs",
    "alert_events",
    "emails_sent",
)


def redact_secrets(value: str) -> str:
    redacted = value
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(r"\1[REDACTED]", redacted)
    return redacted


class JsonLogFormatter(logging.Formatter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self._base = {
            "service": service,
            "environment": os.getenv("APP_ENV", "development"),
        }
        for target, source in (
            ("deployment_id", "RAILWAY_DEPLOYMENT_ID"),
            ("replica_id", "RAILWAY_REPLICA_ID"),
            ("replica_region", "RAILWAY_REPLICA_REGION"),
        ):
            value = os.getenv(source)
            if value:
                self._base[target] = value

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            **self._base,
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": redact_secrets(record.getMessage()),
        }
        for field in _CONTEXT_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = redact_secrets(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(service: str, level: str = "INFO") -> None:
    """Install one stdout JSON handler for application and dependency logs."""

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter(service))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
