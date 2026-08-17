"""Contract document builders for product identity and PDP evidence."""

from __future__ import annotations

from datetime import UTC, datetime

from rci_products.models import (
    CanonicalProductRecord,
    JsonObject,
    NormalizedProductDetail,
    ProductDetailFetchResult,
    ProductDetailJob,
    ProductDetailNormalizationCandidate,
    sha256_document,
)


def normalization_document(
    candidate: ProductDetailNormalizationCandidate,
    normalized: NormalizedProductDetail,
) -> JsonObject:
    normalized_document = normalized.contract_document()
    if normalized_document["normalizer_version"] != candidate.normalizer_version:
        raise ValueError("normalizer version does not match the claimed revision")
    return {
        "normalizer_version": candidate.normalizer_version,
        "snapshot_id": candidate.snapshot_id,
        "canonical_product_id": candidate.canonical_product_id,
        "retailer_id": candidate.retailer_id,
        "source_raw_checksum_sha256": candidate.raw_checksum,
        "normalized": normalized_document,
    }


def identity_from_normalized_document(normalized: JsonObject) -> JsonObject:
    content = normalized.get("content", {})
    commerce = normalized.get("commerce", {})
    media = normalized.get("media", {})
    identifiers = normalized.get("identifiers", {})
    return {
        "name": normalized.get("name"),
        "brand": normalized.get("brand"),
        "seller": normalized.get("seller"),
        "url": normalized.get("url"),
        "image_primary": media.get("image_primary") if isinstance(media, dict) else None,
        "description_short": normalized.get("description_short"),
        "description_full": normalized.get("description_full"),
        "category_path": normalized.get("category_path"),
        "model_number": (content.get("model_number") if isinstance(content, dict) else None)
        or (identifiers.get("model") if isinstance(identifiers, dict) else None),
        "item_condition": (commerce.get("item_condition") if isinstance(commerce, dict) else None),
        "specification": normalized.get("specification", {}),
        "physical_properties": normalized.get("physical_properties", {}),
        "variant_configuration": normalized.get("variant_configuration", {}),
    }


def snapshot_document(
    job: ProductDetailJob,
    result: ProductDetailFetchResult,
    *,
    snapshot_id: str,
) -> JsonObject:
    context = job.context
    request_parameters = {**job.endpoint.defaults(), **context.parameters()}
    document: JsonObject = {
        "schema_version": "1.0.0",
        "snapshot_id": snapshot_id,
        "canonical_product_id": job.canonical_product_id,
        "provider": "metricscart",
        "retailer_id": job.retailer_id,
        "endpoint": {
            "endpoint_id": job.endpoint.endpoint_id,
            "path": job.endpoint.path,
            "method": job.endpoint.method,
            "contract_version": job.endpoint.contract_version,
        },
        "request_context": {
            "product_id": context.product_id,
            "url": context.url,
            "zipcode": context.zipcode,
            "store": context.store,
            "fulfillment_type": request_parameters.get("fulfillment_type"),
            "shopping_type": request_parameters.get("shopping_type"),
            "request_checksum_sha256": job.request_checksum,
        },
        "observed_at": result.observed_at.isoformat(),
        "http_status": result.http_status,
        "billing": {"billable": result.billable, "credits": result.credits},
        "raw_artifact": {
            "artifact_id": result.raw_artifact.artifact_id,
            "storage_uri": result.raw_artifact.storage_uri,
            "checksum_sha256": result.raw_artifact.checksum,
            "immutable": True,
        },
        "source_authority": {
            "serp_price_authoritative": True,
            "serp_availability_authoritative": True,
            "pdp_identity_authoritative": True,
            "pdp_package_semantics_allowed": True,
        },
    }
    if result.normalized is not None:
        document["normalized"] = result.normalized.contract_document()
    else:
        document["failure"] = {
            "failure_class": result.failure_class or "unknown",
            "message": result.failure_message or "Product Details request failed",
            "should_retry": result.should_retry,
        }
    return document


def canonical_product_document(
    product: CanonicalProductRecord,
    *,
    source_contexts: list[JsonObject],
    snapshot_ids: list[str],
    classification: JsonObject | None = None,
) -> JsonObject:
    identifiers = [
        {
            "scheme": "retailer_product_id",
            "value": product.retailer_product_id,
            "issuer": product.retailer_id,
            "primary": True,
        }
    ]
    for scheme, value in sorted(product.identifiers.items()):
        normalized = str(value).strip() if value is not None else ""
        if not normalized or (
            scheme == "retailer_product_id" and normalized == product.retailer_product_id
        ):
            continue
        identifiers.append(
            {
                "scheme": scheme
                if scheme
                in {
                    "product_id",
                    "item_id",
                    "asin",
                    "upc",
                    "gtin",
                    "gtin13",
                    "model",
                    "sku",
                }
                else "other",
                "value": normalized,
                "issuer": "metricscart",
                "primary": False,
            }
        )
    document: JsonObject = {
        "schema_version": "1.0.0",
        "canonical_product_id": product.canonical_product_id,
        "retailer_id": product.retailer_id,
        "retailer_product_id": product.retailer_product_id,
        "identifiers": identifiers,
        "identity": product.identity,
        "source_contexts": source_contexts,
        "pdp_snapshot_ids": sorted(set(snapshot_ids)),
        "provenance": {
            "identity_checksum_sha256": product.identity_checksum,
            "created_at": product.created_at.isoformat(),
            "updated_at": product.updated_at.isoformat(),
        },
    }
    if classification is not None:
        document["classification"] = classification
    return document


def serp_identity(
    *,
    name: str,
    brand: str | None,
    url: str,
    image_primary: str | None,
) -> tuple[JsonObject, str]:
    identity: JsonObject = {
        "name": name,
        "brand": brand,
        "url": url,
        "image_primary": image_primary,
        "description_short": None,
        "description_full": None,
        "category_path": None,
        "model_number": None,
        "specification": {},
        "physical_properties": {},
        "variant_configuration": {},
    }
    return identity, sha256_document(identity)


def source_context(
    *,
    source: str,
    observed_at: datetime,
    zipcode: str | None = None,
    store_number: str | None = None,
    fulfillment_type: str | None = None,
    source_artifact_id: str | None = None,
) -> JsonObject:
    document: JsonObject = {
        "source": source,
        "observed_at": observed_at.astimezone(UTC).isoformat(),
    }
    for name, value in {
        "zipcode": zipcode,
        "store_number": store_number,
        "fulfillment_type": fulfillment_type,
        "source_artifact_id": source_artifact_id,
    }.items():
        if value is not None:
            document[name] = value
    return document


def attach_product_identity(
    observations: list[JsonObject],
    product: JsonObject,
    *,
    snapshot_id: str,
) -> list[JsonObject]:
    """Attach cached identity without changing authoritative SERP observation fields."""

    retailer_id = str(product["retailer_id"])
    retailer_product_id = str(product["retailer_product_id"])
    enriched: list[JsonObject] = []
    for observation in observations:
        copied = dict(observation)
        if (
            str(observation.get("retailer_id")) == retailer_id
            and str(observation.get("retailer_product_id")) == retailer_product_id
        ):
            copied["canonical_product_id"] = product["canonical_product_id"]
            copied["product_identity"] = product["identity"]
            copied["pdp_snapshot_id"] = snapshot_id
        enriched.append(copied)
    return enriched
