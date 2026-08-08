"""Small dependency-free HTTP health server for non-HTTP Railway processes."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping

ReadinessCheck = Callable[[], Awaitable[bool]]


class AsyncHealthServer:
    def __init__(
        self,
        service: str,
        readiness: ReadinessCheck,
        *,
        host: str = "0.0.0.0",
        port: int = 8080,
        metadata: Mapping[str, str] | None = None,
    ) -> None:
        self.service = service
        self.readiness = readiness
        self.host = host
        self.port = port
        self.metadata = dict(metadata or {})
        self._server: asyncio.Server | None = None

    @property
    def bound_port(self) -> int:
        if self._server is None or not self._server.sockets:
            raise RuntimeError("health server has not started")
        return int(self._server.sockets[0].getsockname()[1])

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, self.host, self.port)

    async def close(self) -> None:
        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()
        self._server = None

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request_line = await asyncio.wait_for(reader.readline(), timeout=2)
            parts = request_line.decode("ascii", errors="replace").strip().split()
            method = parts[0] if len(parts) >= 1 else ""
            path = parts[1].split("?", 1)[0] if len(parts) >= 2 else ""
            while await asyncio.wait_for(reader.readline(), timeout=2) not in {
                b"\r\n",
                b"\n",
                b"",
            }:
                pass
            status, body = await self._response(method, path)
            encoded = json.dumps(body, separators=(",", ":")).encode()
            writer.write(
                f"HTTP/1.1 {status}\r\n".encode()
                + b"Content-Type: application/json\r\n"
                + f"Content-Length: {len(encoded)}\r\n".encode()
                + b"Connection: close\r\n\r\n"
                + encoded
            )
            await writer.drain()
        except (TimeoutError, ValueError):
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    async def _response(self, method: str, path: str) -> tuple[str, dict[str, object]]:
        if method != "GET":
            return "405 Method Not Allowed", {"status": "method_not_allowed"}
        if path == "/health/live":
            return "200 OK", {"status": "ok", "service": self.service, **self.metadata}
        if path == "/health/ready":
            ready = await self.readiness()
            return (
                "200 OK" if ready else "503 Service Unavailable",
                {
                    "status": "ready" if ready else "not_ready",
                    "service": self.service,
                    "dependencies": {"postgres": "ok" if ready else "unavailable"},
                    **self.metadata,
                },
            )
        return "404 Not Found", {"status": "not_found"}
