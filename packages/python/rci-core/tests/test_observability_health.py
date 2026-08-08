from __future__ import annotations

import asyncio
import json
import logging

from rci_core.health import AsyncHealthServer
from rci_core.observability import JsonLogFormatter


def test_json_logging_redacts_secrets_and_keeps_safe_context(monkeypatch) -> None:
    monkeypatch.setenv("RAILWAY_REPLICA_ID", "replica-1")
    formatter = JsonLogFormatter("worker")
    record = logging.LogRecord(
        "rci.worker",
        logging.INFO,
        __file__,
        1,
        "request x-api-key=secret-value&zipcode=00123 SMTP_PASSWORD=mail-secret",
        (),
        None,
    )
    record.run_id = "run-1"
    record.task_id = "task-1"

    payload = json.loads(formatter.format(record))

    assert payload["message"] == (
        "request x-api-key=[REDACTED]&zipcode=00123 SMTP_PASSWORD=[REDACTED]"
    )
    assert payload["replica_id"] == "replica-1"
    assert payload["run_id"] == "run-1"
    assert payload["task_id"] == "task-1"


async def _request(port: int, path: str) -> tuple[str, dict[str, object]]:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(f"GET {path} HTTP/1.1\r\nHost: local\r\n\r\n".encode())
    await writer.drain()
    status = (await reader.readline()).decode().strip()
    while await reader.readline() not in {b"\r\n", b"\n", b""}:
        pass
    body = json.loads(await reader.read())
    writer.close()
    await writer.wait_closed()
    return status, body


async def test_async_health_server_exposes_live_and_dependency_readiness() -> None:
    ready = False

    async def readiness() -> bool:
        return ready

    server = AsyncHealthServer(
        "worker", readiness, host="127.0.0.1", port=0, metadata={"version": "1.2.3"}
    )
    await server.start()
    try:
        live_status, live = await _request(server.bound_port, "/health/live")
        assert live_status == "HTTP/1.1 200 OK"
        assert live == {"status": "ok", "service": "worker", "version": "1.2.3"}

        ready_status, result = await _request(server.bound_port, "/health/ready")
        assert ready_status == "HTTP/1.1 503 Service Unavailable"
        assert result["dependencies"] == {"postgres": "unavailable"}

        ready = True
        ready_status, result = await _request(server.bound_port, "/health/ready")
        assert ready_status == "HTTP/1.1 200 OK"
        assert result["status"] == "ready"
    finally:
        await server.close()
