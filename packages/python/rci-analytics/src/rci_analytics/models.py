"""Typed analytics records independent of any product category."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

JsonObject = dict[str, Any]


@dataclass(frozen=True, slots=True)
class NormalizedOffer:
    offer_id: str
    retailer_id: str
    retailer_product_id: str
    title: str
    brand: str | None
    price: Decimal | None
    currency: str
    zipcode: str | None
    store_number: str | None
    latitude: float | None
    longitude: float | None
    in_stock: bool | None
    product_url: str | None
    image_url: str | None
    collected_at: str | None
    raw: JsonObject

    def to_record(self) -> JsonObject:
        return {
            "offer_id": self.offer_id,
            "retailer_id": self.retailer_id,
            "retailer_product_id": self.retailer_product_id,
            "title": self.title,
            "brand": self.brand,
            "price": float(self.price) if self.price is not None else None,
            "currency": self.currency,
            "zipcode": self.zipcode,
            "store_number": self.store_number,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "in_stock": self.in_stock,
            "product_url": self.product_url,
            "image_url": self.image_url,
            "collected_at": self.collected_at,
        }


@dataclass(frozen=True, slots=True)
class ClassifiedOffer:
    offer: NormalizedOffer
    in_scope: bool
    scope_reason: str | None
    attributes: JsonObject
    metrics: dict[str, Decimal | None]
    review_reasons: tuple[str, ...]

    def to_record(self) -> JsonObject:
        import json

        return {
            **self.offer.to_record(),
            "in_scope": self.in_scope,
            "scope_reason": self.scope_reason,
            "attributes_json": json.dumps(self.attributes, sort_keys=True),
            "metrics_json": json.dumps(
                {
                    key: float(value) if value is not None else None
                    for key, value in self.metrics.items()
                },
                sort_keys=True,
            ),
            "review_reasons_json": json.dumps(self.review_reasons),
        }


@dataclass(frozen=True, slots=True)
class MatchRecord:
    profile_id: str
    competitor_id: str
    geography_key: str
    benchmark_offer_id: str
    competitor_offer_id: str
    attributes: JsonObject
    comparison_metric: str
    benchmark_value: Decimal
    competitor_value: Decimal
    gap: Decimal
    winner: str
    distance_miles: float | None = None
    benchmark_interval_low: Decimal | None = None
    benchmark_interval_high: Decimal | None = None
    competitor_interval_low: Decimal | None = None
    competitor_interval_high: Decimal | None = None


@dataclass(frozen=True, slots=True)
class ProductMatchRule:
    competitor_id: str
    profile_id: str
    benchmark_product_id: str
    competitor_product_id: str
    decision: str
    eligible_profile_ids: tuple[str, ...] = ()
    comparison_family_key: str = "legacy"
    relationship_role: str = "primary"
    scope_mode: str = "global"
    scope_definition: JsonObject | None = None
    scope_checksum: str = ""


@dataclass(frozen=True, slots=True)
class ComparisonSummary:
    profile_id: str
    competitor_id: str
    matches: int
    unique_geographies: int
    benchmark_lower: int
    competitor_lower: int
    parity: int
    benchmark_lower_rate: float
    competitor_lower_rate: float
    parity_rate: float
    benchmark_median: float
    competitor_median: float
    median_gap: float | None
    mean_gap: float
