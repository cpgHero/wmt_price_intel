"""Product identity and PDP enrichment value objects."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

JsonObject = dict[str, Any]
ProductDetailStatus = Literal["queued", "running", "succeeded", "failed", "canceled"]
PRODUCT_DETAIL_NORMALIZER_VERSION = "2.0.0"


def canonical_json(value: JsonObject) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_document(value: JsonObject) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class ProductDetailEndpoint:
    retailer_id: str
    provider_retailer: str
    domain: str
    endpoint_id: str
    method: str
    path: str
    credits_per_successful_page: int
    paid_calls_enabled: bool
    required_params: tuple[str, ...]
    supported_params: tuple[str, ...]
    contract_version: str = "1.0.0"
    default_params: tuple[tuple[str, str], ...] = ()
    fixed_params: tuple[tuple[str, str], ...] = ()
    identity_param: Literal["product_id", "url"] | None = None
    product_id_left_pad_width: int | None = None

    def defaults(self) -> JsonObject:
        return dict(self.default_params)

    def fixed(self) -> JsonObject:
        return dict(self.fixed_params)

    def request_parameters(self, parameters: JsonObject) -> JsonObject:
        """Apply the versioned retailer contract without retailer branches."""

        supplied = {**self.defaults(), **parameters, **self.fixed()}
        requested = {
            name: supplied[name]
            for name in self.supported_params
            if name in supplied and str(supplied[name]).strip()
        }
        if self.identity_param is not None:
            for name in ("product_id", "url"):
                if name != self.identity_param:
                    requested.pop(name, None)
        product_id = requested.get("product_id")
        if (
            product_id is not None
            and self.product_id_left_pad_width is not None
            and str(product_id).isdigit()
        ):
            requested["product_id"] = str(product_id).zfill(self.product_id_left_pad_width)
        return requested


@dataclass(frozen=True, slots=True)
class ProductDetailRequestContext:
    product_id: str
    zipcode: str | None = None
    store: str | None = None
    fulfillment_type: str | None = None
    shopping_type: str | None = None
    url: str | None = None

    def parameters(self) -> JsonObject:
        return {
            name: value
            for name, value in {
                "product_id": self.product_id,
                "url": self.url,
                "zipcode": self.zipcode,
                "store": self.store,
                "fulfillment_type": self.fulfillment_type,
                "shopping_type": self.shopping_type,
            }.items()
            if value is not None and str(value).strip()
        }

    def cache_identity(self, endpoint: ProductDetailEndpoint) -> JsonObject:
        supplied = endpoint.request_parameters(self.parameters())
        identity: JsonObject = {
            "provider": "metricscart",
            "retailer_id": endpoint.retailer_id,
            "endpoint_id": endpoint.endpoint_id,
            "endpoint_version": endpoint.contract_version,
            "product_id": supplied.get("product_id"),
            "url": supplied.get("url"),
            "zipcode": supplied.get("zipcode"),
            "store": supplied.get("store"),
            "fulfillment_type": supplied.get("fulfillment_type"),
        }
        if "shopping_type" in supplied:
            identity["shopping_type"] = supplied["shopping_type"]
        return identity

    def checksum(self, endpoint: ProductDetailEndpoint) -> str:
        return sha256_document(self.cache_identity(endpoint))


@dataclass(frozen=True, slots=True)
class ProductDetailRawArtifact:
    artifact_id: str
    storage_uri: str
    checksum: str
    byte_size: int
    metadata: JsonObject


@dataclass(frozen=True, slots=True)
class NormalizedProductDetail:
    retailer_product_id: str
    name: str
    brand: str | None
    seller: str | None
    url: str | None
    description_short: str | None
    description_full: str | None
    category_path: str | None
    identifiers: JsonObject
    specification: JsonObject
    physical_properties: JsonObject
    variant_configuration: JsonObject
    price: float | None
    price_currency: str | None
    stock_available: bool | None
    pickup_available: bool | None
    stock_quantity: float | None
    pickup_store_id: str | None
    shipping_type: str | None
    image_primary: str | None
    images: tuple[str, ...]
    videos: tuple[object, ...]
    commerce: JsonObject
    fulfillment: JsonObject
    reviews: JsonObject
    demand: JsonObject
    content: JsonObject
    relationships: JsonObject
    source_context: JsonObject
    source_field_inventory: tuple[str, ...]
    unmapped_source_fields: tuple[str, ...]
    extras: JsonObject

    def identity_document(self) -> JsonObject:
        return {
            "name": self.name,
            "brand": self.brand,
            "seller": self.seller,
            "url": self.url,
            "image_primary": self.image_primary,
            "description_short": self.description_short,
            "description_full": self.description_full,
            "category_path": self.category_path,
            "model_number": self.content.get("model_number") or self.identifiers.get("model"),
            "item_condition": self.commerce.get("item_condition"),
            "specification": self.specification,
            "physical_properties": self.physical_properties,
            "variant_configuration": self.variant_configuration,
        }

    def contract_document(self) -> JsonObject:
        return {
            "normalizer_version": PRODUCT_DETAIL_NORMALIZER_VERSION,
            "retailer_product_id": self.retailer_product_id,
            "name": self.name,
            "brand": self.brand,
            "seller": self.seller,
            "url": self.url,
            "description_short": self.description_short,
            "description_full": self.description_full,
            "category_path": self.category_path,
            "identifiers": self.identifiers,
            "specification": self.specification,
            "physical_properties": self.physical_properties,
            "variant_configuration": self.variant_configuration,
            "price": self.price,
            "price_currency": self.price_currency,
            "availability": {
                "stock_available": self.stock_available,
                "pickup_available": self.pickup_available,
                "stock_quantity": self.stock_quantity,
                "pickup_store_id": self.pickup_store_id,
                "shipping_type": self.shipping_type,
            },
            "media": {
                "image_primary": self.image_primary,
                "images": list(self.images),
                "videos": list(self.videos),
            },
            "commerce": self.commerce,
            "fulfillment": self.fulfillment,
            "reviews": self.reviews,
            "demand": self.demand,
            "content": self.content,
            "relationships": self.relationships,
            "source_context": self.source_context,
            "source_field_inventory": list(self.source_field_inventory),
            "unmapped_source_fields": list(self.unmapped_source_fields),
            "extras": self.extras,
        }


@dataclass(frozen=True, slots=True)
class ProductDetailFetchResult:
    observed_at: datetime
    http_status: int
    billable: bool
    credits: int
    raw_artifact: ProductDetailRawArtifact
    normalized: NormalizedProductDetail | None = None
    failure_class: str | None = None
    failure_message: str | None = None
    should_retry: bool = False
    retry_delay_seconds: float = 0


@dataclass(frozen=True, slots=True)
class CanonicalProductRecord:
    id: str
    canonical_product_id: str
    retailer_id: str
    retailer_product_id: str
    identifiers: JsonObject
    identity: JsonObject
    identity_checksum: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ProductDetailRun:
    id: str
    max_credits: int
    planned_credits: int
    actual_credits: int
    status: str


@dataclass(frozen=True, slots=True)
class ProductDetailJob:
    id: str
    run_id: str
    canonical_product_db_id: str
    canonical_product_id: str
    retailer_id: str
    endpoint: ProductDetailEndpoint
    context: ProductDetailRequestContext
    request_checksum: str
    credits_per_call: int
    status: ProductDetailStatus
    attempt_count: int
    max_attempts: int


@dataclass(frozen=True, slots=True)
class EnqueueProductDetailResult:
    job_id: str | None
    snapshot_id: str | None
    request_checksum: str
    cached: bool
    created: bool


@dataclass(frozen=True, slots=True)
class ProductDetailSnapshotRecord:
    id: str
    canonical_product_db_id: str
    canonical_product_id: str
    request_checksum: str
    document: JsonObject
    cache_expires_at: datetime | None


@dataclass(frozen=True, slots=True)
class ProductDetailNormalizationCandidate:
    id: str
    snapshot_id: str
    normalizer_version: str
    canonical_product_db_id: str
    canonical_product_id: str
    retailer_id: str
    raw_storage_uri: str
    raw_checksum: str
    endpoint: ProductDetailEndpoint
    context: ProductDetailRequestContext
    attempt_count: int


@dataclass(frozen=True, slots=True)
class ProductDetailNormalizationRecord:
    id: str
    snapshot_id: str
    normalizer_version: str
    document: JsonObject
    document_checksum: str
