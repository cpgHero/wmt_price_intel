"""Canonical Search-authoritative product/location observations.

This module is the shared upstream boundary for retailer Price Intelligence and
cross-retailer Competitive Intelligence.  It owns admission, location-master
enrichment, governed product/brand identity, and latest-observation selection.
Downstream projections may calculate different metrics, but they must not
rebuild this population independently.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast

from rci_analytics.models import ClassifiedOffer, JsonObject
from rci_analytics.product_pack import ProductPack
from rci_retailer_packs import GovernedBrandResolver

PRODUCT_LOCATION_OBSERVATION_SCHEMA_VERSION = "1.1.0"

BrandType = Literal["private_label", "regional", "national", "unclassified"]
BrandOrigin = Literal["user", "retailer_pack", "search", "pdp", "unresolved"]


@dataclass(frozen=True, slots=True)
class PriceLocation:
    scope_key: str
    kind: Literal["store", "service_area"]
    store_number: str | None
    store_name: str | None
    zipcode: str | None
    city: str | None
    state: str | None
    country: str
    latitude: float | None
    longitude: float | None

    def to_contract(self) -> JsonObject:
        return {
            "scope_key": self.scope_key,
            "kind": self.kind,
            "store_number": self.store_number,
            "store_name": self.store_name,
            "zipcode": self.zipcode,
            "city": self.city,
            "state": self.state,
            "country": self.country,
            "latitude": self.latitude,
            "longitude": self.longitude,
        }


@dataclass(frozen=True, slots=True)
class ProductPriceObservation:
    """A comparison-basis projection of one canonical observation.

    This backward-compatible adapter remains the input to the competitive
    leadership scorer.  It is derived only from ``ProductLocationObservation``.
    """

    retailer_id: str
    retailer_name: str
    product_id: str
    product_name: str
    image_url: str | None
    scope_key: str
    location_kind: Literal["store", "service_area"]
    store_number: str | None
    store_name: str | None
    zipcode: str | None
    city: str | None
    state: str | None
    country: str
    latitude: float | None
    longitude: float | None
    package_price: float
    comparison_value: float
    observed_at: str | None
    offer_id: str | None = None
    brand: str | None = None
    brand_type: BrandType = "unclassified"
    brand_origin: BrandOrigin = "unresolved"
    brand_status: str = "unclassified"
    product_url: str | None = None
    regular_price: float | None = None
    discounted_price: float | None = None
    is_sponsored: bool | None = None
    in_stock: bool = True


@dataclass(frozen=True, slots=True)
class ProductLocationObservation:
    observation_id: str
    retailer_id: str
    retailer_name: str
    product_id: str
    product_name: str
    brand: str | None
    brand_type: BrandType
    brand_origin: BrandOrigin
    brand_status: str
    image_url: str | None
    product_url: str | None
    identity_authority: Literal["search", "pdp"]
    location: PriceLocation
    package_price: float
    regular_price: float | None
    discounted_price: float | None
    is_sponsored: bool | None
    observed_at: str | None
    offer_id: str
    metric_values: tuple[tuple[str, float], ...]

    def comparison_value(self, metric: str) -> float | None:
        if metric == "package_price":
            return self.package_price
        return dict(self.metric_values).get(metric)

    def to_price_monitoring_row(self) -> JsonObject:
        return {
            "observation_id": self.observation_id,
            "product_id": self.product_id,
            "name": self.product_name,
            "brand": self.brand,
            "brand_type": self.brand_type,
            "brand_origin": self.brand_origin,
            "brand_status": self.brand_status,
            "image_url": self.image_url,
            "url": self.product_url,
            "location": self.location,
            "price": self.package_price,
            "price_metrics": dict(self.metric_values),
            "regular_price": self.regular_price,
            "discounted_price": self.discounted_price,
            # Positive Search price is the governed availability signal.
            "in_stock": True,
            "is_sponsored": self.is_sponsored,
            "observed_at": self.observed_at,
            "offer_id": self.offer_id,
        }

    def to_price_observation_contract(
        self,
        *,
        analysis_id: str,
        product_pack_id: str,
        product_pack_version: str,
    ) -> JsonObject:
        return {
            "schema_version": PRODUCT_LOCATION_OBSERVATION_SCHEMA_VERSION,
            "observation_id": self.observation_id,
            "analysis_id": analysis_id,
            "product_pack_id": product_pack_id,
            "product_pack_version": product_pack_version,
            "retailer_id": self.retailer_id,
            "retailer_name": self.retailer_name,
            "retailer_product_id": self.product_id,
            "product_name": self.product_name,
            "brand": self.brand,
            "brand_type": self.brand_type,
            "brand_origin": self.brand_origin,
            "brand_status": self.brand_status,
            "image_url": self.image_url,
            "product_url": self.product_url,
            "identity_authority": self.identity_authority,
            "location": self.location.to_contract(),
            "price": self.package_price,
            "regular_price": self.regular_price,
            "discounted_price": self.discounted_price,
            "currency": "USD",
            "in_stock": True,
            "is_sponsored": self.is_sponsored,
            "price_metrics": dict(self.metric_values),
            "observed_at": self.observed_at,
            "source_authority": "search_location_observation",
            "location_authority": "retailer_location_master",
            "eligible": True,
            "exclusion_reasons": [],
        }

    def for_comparison(self, metric: str) -> ProductPriceObservation | None:
        value = self.comparison_value(metric)
        if value is None or value <= 0:
            return None
        return ProductPriceObservation(
            retailer_id=self.retailer_id,
            retailer_name=self.retailer_name,
            product_id=self.product_id,
            product_name=self.product_name,
            image_url=self.image_url,
            scope_key=self.location.scope_key,
            location_kind=self.location.kind,
            store_number=self.location.store_number,
            store_name=self.location.store_name,
            zipcode=self.location.zipcode,
            city=self.location.city,
            state=self.location.state,
            country=self.location.country,
            latitude=self.location.latitude,
            longitude=self.location.longitude,
            package_price=self.package_price,
            comparison_value=value,
            observed_at=self.observed_at,
            offer_id=self.offer_id,
            brand=self.brand,
            brand_type=self.brand_type,
            brand_origin=self.brand_origin,
            brand_status=self.brand_status,
            product_url=self.product_url,
            regular_price=self.regular_price,
            discounted_price=self.discounted_price,
            is_sponsored=self.is_sponsored,
        )


@dataclass(frozen=True, slots=True)
class ProductLocationPopulation:
    retailer_id: str
    observations: tuple[ProductLocationObservation, ...]
    source_locations: dict[str, PriceLocation]
    eligible_scope_keys: frozenset[str]
    all_retailers: frozenset[str]
    classified_rows: int
    eligible_input_rows: int
    excluded_rows: int
    exclusion_counts: tuple[tuple[str, int], ...]
    duplicate_rows: int
    conflicting_keys: frozenset[tuple[str, str]]
    checksum: str

    def comparison_observations(
        self,
        product_ids: set[str],
        comparison_metric: str,
    ) -> dict[str, tuple[ProductPriceObservation, ...]]:
        grouped: dict[str, list[ProductPriceObservation]] = {
            product_id: [] for product_id in product_ids
        }
        for observation in self.observations:
            if observation.product_id not in product_ids:
                continue
            projected = observation.for_comparison(comparison_metric)
            if projected is not None:
                grouped[observation.product_id].append(projected)
        return {
            product_id: tuple(
                sorted(
                    observations,
                    key=lambda row: (
                        str(row.state or ""),
                        str(row.city or ""),
                        str(row.store_number or row.zipcode or ""),
                    ),
                )
            )
            for product_id, observations in grouped.items()
        }


def _observed_at(value: str | None) -> datetime:
    normalized = _normalized_observed_at(value)
    if normalized is None:
        return datetime.min.replace(tzinfo=UTC)
    return datetime.fromisoformat(normalized.replace("Z", "+00:00"))


def _normalized_observed_at(value: str | None) -> str | None:
    """Return a Search timestamp as an explicit RFC 3339 UTC instant.

    Historical database rows may contain timezone-naive ISO values even though
    collection timestamps are UTC. Normalize once at the canonical
    product-location boundary so every downstream contract receives the same
    unambiguous value.
    """

    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    parsed = parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    return parsed.isoformat().replace("+00:00", "Z")


def _location_from_offer(
    offer: ClassifiedOffer,
    location_index: dict[tuple[str, str], JsonObject],
) -> PriceLocation:
    value = offer.offer
    kind: Literal["store", "service_area"] = (
        "store" if value.store_number is not None else "service_area"
    )
    lookup = (
        location_index.get((value.retailer_id, value.store_number))
        if value.store_number is not None
        else location_index.get((value.retailer_id, f"zip:{value.zipcode}"))
        if value.zipcode is not None
        else None
    ) or {}
    scope_value = value.store_number or value.zipcode or "unknown"
    return PriceLocation(
        scope_key=f"{value.retailer_id}|{kind}|{scope_value}",
        kind=kind,
        store_number=value.store_number,
        store_name=str(lookup["store_name"]) if lookup.get("store_name") else None,
        zipcode=(
            str(lookup["zipcode"])
            if lookup.get("zipcode")
            else value.zipcode
            if kind == "service_area"
            else None
        ),
        city=str(lookup["city"]) if lookup.get("city") else None,
        state=str(lookup["state"]) if lookup.get("state") else None,
        country=str(lookup.get("country") or "USA"),
        latitude=float(lookup["latitude"]) if lookup.get("latitude") is not None else None,
        longitude=float(lookup["longitude"]) if lookup.get("longitude") is not None else None,
    )


def _population_checksum(observations: Iterable[ProductLocationObservation]) -> str:
    payload = [
        {
            "retailer_id": row.retailer_id,
            "product_id": row.product_id,
            "product_name": row.product_name,
            "brand": row.brand,
            "brand_type": row.brand_type,
            "brand_origin": row.brand_origin,
            "brand_status": row.brand_status,
            "identity_authority": row.identity_authority,
            "scope_key": row.location.scope_key,
            "location": row.location.to_contract(),
            "offer_id": row.offer_id,
            "price": row.package_price,
            "regular_price": row.regular_price,
            "discounted_price": row.discounted_price,
            "is_sponsored": row.is_sponsored,
            "observed_at": row.observed_at,
            "metrics": row.metric_values,
        }
        for row in sorted(
            observations,
            key=lambda value: (
                value.retailer_id,
                value.product_id,
                value.location.scope_key,
            ),
        )
    ]
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(body.encode()).hexdigest()


class ProductLocationProjector:
    """Build the canonical latest positive Search population for one retailer."""

    def __init__(
        self,
        pack: ProductPack,
        brand_resolver: GovernedBrandResolver,
        *,
        retailer_names: dict[str, str] | None = None,
    ) -> None:
        self._pack = pack
        self._brands = brand_resolver
        self._retailer_names = dict(retailer_names or {})

    def build(
        self,
        offers: Iterable[ClassifiedOffer],
        *,
        retailer_id: str,
        location_index: dict[tuple[str, str], JsonObject] | None = None,
        eligible_location_index: dict[tuple[str, str], JsonObject] | None = None,
        product_context: dict[str, JsonObject] | None = None,
        retailer_options: Iterable[str] = (),
    ) -> ProductLocationPopulation:
        location_lookup = location_index or {}
        eligible_location_lookup = eligible_location_index or location_lookup
        context = product_context or {}
        excluded = Counter[str]()
        selected: dict[tuple[str, str], ProductLocationObservation] = {}
        conflicting_keys: set[tuple[str, str]] = set()
        duplicate_rows = 0
        classified_rows = 0
        eligible_input_rows = 0
        excluded_rows = 0
        source_locations: dict[str, PriceLocation] = {}
        eligible_scope_keys: set[str] = set()
        all_retailers: set[str] = set(retailer_options)

        for (location_retailer_id, location_key), lookup in eligible_location_lookup.items():
            if location_retailer_id != retailer_id:
                continue
            service_area = location_key.startswith("zip:")
            scope_value = location_key.removeprefix("zip:") if service_area else location_key
            location = PriceLocation(
                scope_key=(
                    f"{retailer_id}|service_area|{scope_value}"
                    if service_area
                    else f"{retailer_id}|store|{scope_value}"
                ),
                kind="service_area" if service_area else "store",
                store_number=None if service_area else location_key,
                store_name=str(lookup["store_name"]) if lookup.get("store_name") else None,
                zipcode=str(lookup["zipcode"]) if lookup.get("zipcode") else None,
                city=str(lookup["city"]) if lookup.get("city") else None,
                state=str(lookup["state"]) if lookup.get("state") else None,
                country=str(lookup.get("country") or "USA"),
                latitude=(
                    float(lookup["latitude"]) if lookup.get("latitude") is not None else None
                ),
                longitude=(
                    float(lookup["longitude"]) if lookup.get("longitude") is not None else None
                ),
            )
            source_locations[location.scope_key] = location
            eligible_scope_keys.add(location.scope_key)

        for classified in offers:
            offer = classified.offer
            all_retailers.add(offer.retailer_id)
            if offer.retailer_id != retailer_id:
                continue
            classified_rows += 1
            location = _location_from_offer(classified, location_lookup)
            if not location.scope_key.endswith("|unknown"):
                source_locations[location.scope_key] = location
            reasons: list[str] = []
            if not classified.in_scope:
                reasons.append("out_of_scope")
            if offer.price is None or offer.price <= 0:
                reasons.append("missing_or_zero_price")
            if offer.currency != "USD":
                reasons.append("unsupported_currency")
            if location.scope_key.endswith("|unknown"):
                reasons.append("missing_location_identity")
            if reasons:
                excluded_rows += 1
                excluded.update(reasons)
                continue
            eligible_input_rows += 1
            assert offer.price is not None

            product_key = f"{offer.retailer_id}:{offer.retailer_product_id}"
            product = context.get(product_key, {})
            pdp_identity_available = any(
                product.get(field) for field in ("name", "brand", "image_url", "url")
            )
            observed_brand = str(product.get("brand") or offer.brand or "").strip() or None
            brand_governance = classified.attributes.get("_brand_governance")
            resolution = self._brands.resolve(
                offer.retailer_id,
                observed_brand,
                category=self._pack.name,
            )
            if resolution.resolution_method == "governed_override":
                brand_type = resolution.role
                brand_origin: BrandOrigin = "user"
                brand_status = resolution.override_decision or "suggested"
                brand_name = resolution.canonical_brand_name or observed_brand
            elif (
                isinstance(brand_governance, dict) and brand_governance.get("status") == "resolved"
            ):
                governed_role = str(brand_governance.get("role") or resolution.role)
                brand_type = cast(
                    BrandType,
                    governed_role
                    if governed_role in {"private_label", "regional", "national", "unclassified"}
                    else "unclassified",
                )
                brand_origin = "pdp" if product.get("brand") else "search"
                brand_status = "suggested"
                brand_name = (
                    str(
                        brand_governance.get("canonical_brand_name") or observed_brand or ""
                    ).strip()
                    or None
                )
            else:
                brand_type = resolution.role
                brand_origin = (
                    "pdp"
                    if product.get("brand")
                    else "retailer_pack"
                    if resolution.status == "resolved"
                    else "unresolved"
                )
                brand_status = "suggested" if resolution.status == "resolved" else "unclassified"
                brand_name = resolution.canonical_brand_name or observed_brand

            observation = ProductLocationObservation(
                observation_id=offer.offer_id,
                retailer_id=offer.retailer_id,
                retailer_name=self._retailer_names.get(
                    offer.retailer_id,
                    offer.retailer_id.replace("_", " ").title(),
                ),
                product_id=offer.retailer_product_id,
                product_name=str(product.get("name") or offer.title),
                brand=brand_name or product.get("brand") or observed_brand,
                brand_type=brand_type,
                brand_origin=brand_origin,
                brand_status=brand_status,
                image_url=(
                    str(product["image_url"]) if product.get("image_url") else offer.image_url
                ),
                product_url=(str(product["url"]) if product.get("url") else offer.product_url),
                identity_authority="pdp" if pdp_identity_available else "search",
                location=location,
                package_price=float(offer.price),
                regular_price=(
                    float(offer.regular_price) if offer.regular_price is not None else None
                ),
                discounted_price=(
                    float(offer.discounted_price) if offer.discounted_price is not None else None
                ),
                is_sponsored=offer.is_sponsored,
                observed_at=_normalized_observed_at(offer.collected_at),
                offer_id=offer.offer_id,
                metric_values=tuple(
                    sorted(
                        {
                            **{
                                str(key): float(value)
                                for key, value in classified.metrics.items()
                                if value is not None
                            },
                            "package_price": float(offer.price),
                        }.items()
                    )
                ),
            )
            key = (observation.product_id, observation.location.scope_key)
            existing = selected.get(key)
            if existing is None:
                selected[key] = observation
                continue
            duplicate_rows += 1
            if existing.package_price != observation.package_price:
                conflicting_keys.add(key)
            current_rank = (_observed_at(existing.observed_at), existing.offer_id)
            next_rank = (_observed_at(observation.observed_at), observation.offer_id)
            if next_rank > current_rank:
                selected[key] = observation

        observations = tuple(
            sorted(
                selected.values(),
                key=lambda row: (
                    row.product_id,
                    row.location.state or "",
                    row.location.city or "",
                    row.location.store_number or row.location.zipcode or "",
                ),
            )
        )
        return ProductLocationPopulation(
            retailer_id=retailer_id,
            observations=observations,
            source_locations=source_locations,
            eligible_scope_keys=frozenset(eligible_scope_keys),
            all_retailers=frozenset(all_retailers),
            classified_rows=classified_rows,
            eligible_input_rows=eligible_input_rows,
            excluded_rows=excluded_rows,
            exclusion_counts=tuple(sorted(excluded.items())),
            duplicate_rows=duplicate_rows,
            conflicting_keys=frozenset(conflicting_keys),
            checksum=_population_checksum(observations),
        )
