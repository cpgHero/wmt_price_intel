"""Private immutable report-object storage and short-lived download links."""

from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from rci_results.models import ArtifactPayload

_SAFE_COMPONENT = re.compile(r"^[a-zA-Z0-9_.-]+$")


class ReportObjectStore(Protocol):
    async def put(self, analysis_id: str, payload: ArtifactPayload) -> str: ...

    async def presign(self, storage_uri: str, *, expires_in_seconds: int) -> str: ...


class UnavailableReportObjectStore:
    def __init__(self, reason: str = "object storage is not configured") -> None:
        self._reason = reason

    async def put(self, analysis_id: str, payload: ArtifactPayload) -> str:
        del analysis_id, payload
        raise RuntimeError(self._reason)

    async def presign(self, storage_uri: str, *, expires_in_seconds: int) -> str:
        del storage_uri, expires_in_seconds
        raise RuntimeError(self._reason)


def artifact_key(analysis_id: str, payload: ArtifactPayload) -> str:
    if not _SAFE_COMPONENT.fullmatch(analysis_id):
        raise ValueError(f"unsafe analysis ID {analysis_id!r}")
    checksum = hashlib.sha256(payload.body).hexdigest()
    return (
        f"reports/analysis_id={analysis_id}/type={payload.artifact_type}/"
        f"{checksum[:16]}-{payload.filename}"
    )


@dataclass(slots=True)
class InMemoryReportObjectStore:
    bucket: str = "test-reports"
    objects: dict[str, bytes] = field(default_factory=dict)

    async def put(self, analysis_id: str, payload: ArtifactPayload) -> str:
        key = artifact_key(analysis_id, payload)
        previous = self.objects.setdefault(key, payload.body)
        if previous != payload.body:
            raise RuntimeError(f"immutable report collision at {key}")
        return f"s3://{self.bucket}/{key}"

    async def presign(self, storage_uri: str, *, expires_in_seconds: int) -> str:
        prefix = f"s3://{self.bucket}/"
        if not storage_uri.startswith(prefix):
            raise ValueError("report object belongs to a different bucket")
        key = storage_uri.removeprefix(prefix)
        return f"https://download.test/{key}?expires={expires_in_seconds}"


class S3ReportObjectStore:
    def __init__(self, *, bucket: str, client: Any) -> None:
        if not bucket:
            raise ValueError("OBJECT_STORAGE_BUCKET is required")
        self.bucket = bucket
        self._client = client

    @classmethod
    def create(
        cls,
        *,
        bucket: str,
        endpoint_url: str | None,
        region_name: str | None,
        access_key_id: str | None,
        secret_access_key: str | None,
        force_path_style: bool = True,
    ) -> S3ReportObjectStore:
        import boto3  # type: ignore[import-untyped]
        from botocore.config import Config  # type: ignore[import-untyped]

        client = boto3.client(
            "s3",
            endpoint_url=endpoint_url or None,
            region_name=region_name or None,
            aws_access_key_id=access_key_id or None,
            aws_secret_access_key=secret_access_key or None,
            config=Config(s3={"addressing_style": "path" if force_path_style else "virtual"}),
        )
        return cls(bucket=bucket, client=client)

    async def put(self, analysis_id: str, payload: ArtifactPayload) -> str:
        key = artifact_key(analysis_id, payload)
        checksum = hashlib.sha256(payload.body).hexdigest()

        def put_once() -> None:
            try:
                self._client.put_object(
                    Bucket=self.bucket,
                    Key=key,
                    Body=payload.body,
                    ContentType=payload.content_type,
                    IfNoneMatch="*",
                    Metadata={"sha256": checksum},
                )
            except Exception as exc:
                response = getattr(exc, "response", {})
                error = response.get("Error", {}) if isinstance(response, dict) else {}
                code = str(error.get("Code", "")) if isinstance(error, dict) else ""
                if code not in {"PreconditionFailed", "412"}:
                    raise
                existing = self._client.head_object(Bucket=self.bucket, Key=key)
                metadata = existing.get("Metadata", {})
                if not isinstance(metadata, dict) or metadata.get("sha256") != checksum:
                    raise RuntimeError(f"immutable report collision at {key}") from exc

        await asyncio.to_thread(put_once)
        return f"s3://{self.bucket}/{key}"

    async def presign(self, storage_uri: str, *, expires_in_seconds: int) -> str:
        prefix = f"s3://{self.bucket}/"
        if not storage_uri.startswith(prefix):
            raise ValueError("report object belongs to a different bucket")
        key = storage_uri.removeprefix(prefix)
        return str(
            await asyncio.to_thread(
                self._client.generate_presigned_url,
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expires_in_seconds,
            )
        )
