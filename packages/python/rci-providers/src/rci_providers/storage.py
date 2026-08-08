"""Immutable raw provider response persistence."""

from __future__ import annotations

import asyncio
import gzip
import hashlib
from dataclasses import dataclass, field
from typing import Any, Protocol

from rci_collections.models import QueueTask, RawArtifact
from rci_providers.models import ProviderRequest


class RawObjectStore(Protocol):
    async def put_response(
        self,
        task: QueueTask,
        request: ProviderRequest,
        *,
        http_status: int,
        body: bytes,
        response_content_type: str | None,
    ) -> RawArtifact: ...


def _raw_object(
    bucket: str,
    task: QueueTask,
    request: ProviderRequest,
    *,
    http_status: int,
    body: bytes,
    response_content_type: str | None,
) -> tuple[str, bytes, RawArtifact]:
    body_checksum = hashlib.sha256(body).hexdigest()
    compressed = gzip.compress(body, mtime=0)
    checksum = hashlib.sha256(compressed).hexdigest()
    key = (
        "raw/provider=metricscart/"
        f"run_id={task.collection_run_id}/retailer_id={task.retailer_id}/"
        f"task_id={task.id}/page={task.page_number:04d}/attempt={task.attempt_count:04d}/"
        f"body-{body_checksum[:16]}.json.gz"
    )
    uri = f"s3://{bucket}/{key}"
    artifact = RawArtifact(
        storage_uri=uri,
        content_type="application/json",
        byte_size=len(compressed),
        checksum=checksum,
        metadata={
            "provider": "metricscart",
            "retailer_id": task.retailer_id,
            "adapter_id": task.adapter_id,
            "page": task.page_number,
            "attempt": task.attempt_count,
            "http_status": http_status,
            "request_method": request.method,
            "request_path": request.path,
            "request_parameter_names": sorted(request.params),
            "response_content_type": response_content_type,
            "content_encoding": "gzip",
            "body_checksum": body_checksum,
        },
    )
    return key, compressed, artifact


@dataclass(slots=True)
class InMemoryRawObjectStore:
    bucket: str = "test-raw"
    objects: dict[str, bytes] = field(default_factory=dict)

    async def put_response(
        self,
        task: QueueTask,
        request: ProviderRequest,
        *,
        http_status: int,
        body: bytes,
        response_content_type: str | None,
    ) -> RawArtifact:
        key, compressed, artifact = _raw_object(
            self.bucket,
            task,
            request,
            http_status=http_status,
            body=body,
            response_content_type=response_content_type,
        )
        previous = self.objects.setdefault(key, compressed)
        if previous != compressed:
            raise RuntimeError(f"immutable raw object collision at {key}")
        return artifact


class S3RawObjectStore:
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
    ) -> S3RawObjectStore:
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

    async def put_response(
        self,
        task: QueueTask,
        request: ProviderRequest,
        *,
        http_status: int,
        body: bytes,
        response_content_type: str | None,
    ) -> RawArtifact:
        key, compressed, artifact = _raw_object(
            self.bucket,
            task,
            request,
            http_status=http_status,
            body=body,
            response_content_type=response_content_type,
        )
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=compressed,
            ContentType="application/json",
            ContentEncoding="gzip",
            IfNoneMatch="*",
            Metadata={
                "provider": "metricscart",
                "retailer-id": task.retailer_id,
                "task-id": task.id,
                "body-sha256": str(artifact.metadata["body_checksum"]),
            },
        )
        return artifact
