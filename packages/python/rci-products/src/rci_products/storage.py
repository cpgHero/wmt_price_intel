"""Immutable MetricsCart Product Details raw-response storage."""

from __future__ import annotations

import asyncio
import gzip
import hashlib
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlparse

from rci_products.models import ProductDetailJob, ProductDetailRawArtifact
from rci_providers.models import ProviderRequest


class ProductDetailRawObjectStore(Protocol):
    async def put_response(
        self,
        job: ProductDetailJob,
        request: ProviderRequest,
        *,
        http_status: int,
        body: bytes,
        response_content_type: str | None,
    ) -> ProductDetailRawArtifact: ...


class ProductDetailRawObjectReader(Protocol):
    async def get_response(self, storage_uri: str, *, expected_checksum: str) -> bytes: ...


def _raw_object(
    bucket: str,
    job: ProductDetailJob,
    request: ProviderRequest,
    *,
    http_status: int,
    body: bytes,
    response_content_type: str | None,
) -> tuple[str, bytes, ProductDetailRawArtifact]:
    body_checksum = hashlib.sha256(body).hexdigest()
    compressed = gzip.compress(body, mtime=0)
    checksum = hashlib.sha256(compressed).hexdigest()
    key = (
        "raw/provider=metricscart/type=pdp/"
        f"retailer_id={job.retailer_id}/endpoint_id={job.endpoint.endpoint_id}/"
        f"request={job.request_checksum}/attempt={job.attempt_count:04d}/"
        f"body-{body_checksum[:16]}.json.gz"
    )
    uri = f"s3://{bucket}/{key}"
    return (
        key,
        compressed,
        ProductDetailRawArtifact(
            artifact_id=f"pdp-raw-{hashlib.sha256(key.encode()).hexdigest()[:32]}",
            storage_uri=uri,
            checksum=checksum,
            byte_size=len(compressed),
            metadata={
                "provider": "metricscart",
                "source_type": "pdp",
                "retailer_id": job.retailer_id,
                "endpoint_id": job.endpoint.endpoint_id,
                "attempt": job.attempt_count,
                "http_status": http_status,
                "request_method": request.method,
                "request_path": request.path,
                "request_parameter_names": sorted(request.params),
                "response_content_type": response_content_type,
                "content_encoding": "gzip",
                "body_checksum": body_checksum,
            },
        ),
    )


@dataclass(slots=True)
class InMemoryProductDetailRawObjectStore:
    bucket: str = "test-product-detail-raw"
    objects: dict[str, bytes] = field(default_factory=dict)

    async def put_response(
        self,
        job: ProductDetailJob,
        request: ProviderRequest,
        *,
        http_status: int,
        body: bytes,
        response_content_type: str | None,
    ) -> ProductDetailRawArtifact:
        key, compressed, artifact = _raw_object(
            self.bucket,
            job,
            request,
            http_status=http_status,
            body=body,
            response_content_type=response_content_type,
        )
        previous = self.objects.setdefault(key, compressed)
        if previous != compressed:
            raise RuntimeError(f"immutable Product Details collision at {key}")
        return artifact

    async def get_response(self, storage_uri: str, *, expected_checksum: str) -> bytes:
        parsed = urlparse(storage_uri)
        compressed = self.objects[parsed.path.lstrip("/")]
        if hashlib.sha256(compressed).hexdigest() != expected_checksum:
            raise RuntimeError(f"Product Details raw checksum mismatch at {storage_uri}")
        return gzip.decompress(compressed)


class S3ProductDetailRawObjectStore:
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
    ) -> S3ProductDetailRawObjectStore:
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
        job: ProductDetailJob,
        request: ProviderRequest,
        *,
        http_status: int,
        body: bytes,
        response_content_type: str | None,
    ) -> ProductDetailRawArtifact:
        key, compressed, artifact = _raw_object(
            self.bucket,
            job,
            request,
            http_status=http_status,
            body=body,
            response_content_type=response_content_type,
        )

        def put_once() -> None:
            metadata = {
                "provider": "metricscart",
                "source-type": "pdp",
                "retailer-id": job.retailer_id,
                "request-sha256": job.request_checksum,
                "body-sha256": str(artifact.metadata["body_checksum"]),
                "sha256": artifact.checksum,
                "http-status": str(http_status),
            }
            if response_content_type:
                metadata["response-content-type"] = response_content_type
            try:
                self._client.put_object(
                    Bucket=self.bucket,
                    Key=key,
                    Body=compressed,
                    ContentType="application/json",
                    ContentEncoding="gzip",
                    IfNoneMatch="*",
                    Metadata=metadata,
                )
            except Exception as exc:
                response = getattr(exc, "response", {})
                error = response.get("Error", {}) if isinstance(response, dict) else {}
                code = str(error.get("Code", "")) if isinstance(error, dict) else ""
                if code not in {"PreconditionFailed", "412"}:
                    raise
                existing = self._client.head_object(Bucket=self.bucket, Key=key)
                metadata = existing.get("Metadata", {})
                if not isinstance(metadata, dict) or metadata.get("sha256") != artifact.checksum:
                    raise RuntimeError(f"immutable Product Details collision at {key}") from exc

        await asyncio.to_thread(put_once)
        return artifact

    async def get_response(self, storage_uri: str, *, expected_checksum: str) -> bytes:
        parsed = urlparse(storage_uri)
        if parsed.scheme != "s3" or parsed.netloc != self.bucket:
            raise ValueError(f"unexpected Product Details raw storage URI: {storage_uri}")
        key = parsed.path.lstrip("/")

        def read() -> bytes:
            response = self._client.get_object(Bucket=self.bucket, Key=key)
            compressed = response["Body"].read()
            if hashlib.sha256(compressed).hexdigest() != expected_checksum:
                raise RuntimeError(f"Product Details raw checksum mismatch at {storage_uri}")
            return gzip.decompress(compressed)

        return await asyncio.to_thread(read)
