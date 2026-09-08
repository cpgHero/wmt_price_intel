"""Canonical Search-observed price-placement/product-location evidence.

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
from typing import Literal, cast

from rci_analytics.classification import OfferClassifier
from rci_analytics.latest_product_location import (
    SELLER_POLICY_EXCLUSION_REASON,
    LatestProductLocationSelector,
    is_product_location_state,
    normalized_observed_at,
    product_location_key,
)
from rci_analytics.models import ClassifiedOffer, JsonObject
from rci_analytics.pdp_attributes import complete_attributes_from_pdp
from rci_analytics.product_pack import ProductPack
from rci_retailer_packs import GovernedBrandResolver, GovernedSellerResolver

PRODUCT_LOCATION_OBSERVATION_SCHEMA_VERSION = "1.3.0"
STORE_SEARCH_DISTRIBUTION_CONTRACT_VERSION = "1.0.0"

BrandType = Literal["private_label", "regional", "national", "unclassified"]
BrandOrigin = Literal["user", "retailer_pack", "search", "pdp", "unresolved"]
SellerStatus = Literal["verified_first_party", "seller_unverified", "not_governed"]
AvailabilityStatus = Literal[
    "verified_in_stock",
    "explicitly_out_of_stock",
    "unverified_sponsored",
    "unverified",
]
PriceEvidenceScope = Literal["verified_local", "search_presence"]


def store_search_distribution_contract() -> JsonObject:
    """Return the exact, versioned definition used by report projections."""

    return {
        "version": STORE_SEARCH_DISTRIBUTION_CONTRACT_VERSION,
        "basis": "positive_price_store_search_result",
        "grain": "retailer_product_id_x_store_id",
        "deduplication": "distinct_store_id_per_product",
        "price_rule": "price_gt_zero",
        "inventory_claim": False,
        "stock_status_used": False,
        "sponsorship_used": False,
    }


def classify_local_availability(
    *,
    in_stock: bool | None,
    is_sponsored: bool | None,
) -> AvailabilityStatus:
    """Return the canonical trust classification for store-level availability."""

    if in_stock is False:
        return "explicitly_out_of_stock"
    if is_sponsored is True:
        return "unverified_sponsored"
    if in_stock is True and is_sponsored is False:
        return "verified_in_stock"
    return "unverified"


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
    in_stock: bool | None = None
    search_observed: bool = True
    availability_status: AvailabilityStatus = "unverified"
    verified_local_availability: bool = False


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
    in_stock: bool | None = None
    seller: str | None = None
    seller_status: SellerStatus = "not_governed"

    @property
    def availability_status(self) -> AvailabilityStatus:
        """Classify local availability without promoting Search presence to carriage.

        Search can establish that an item and price were listed for a store-scoped
        query.  Verified local availability is intentionally stricter: the provider
        must explicitly report in-stock *and* the result must be organic.  Sponsored
        placements and legacy rows with missing sponsorship evidence remain useful
        Search/price signals, but they cannot establish store carriage.
        """

        return classify_local_availability(
            in_stock=self.in_stock,
            is_sponsored=self.is_sponsored,
        )

    @property
    def verified_local_availability(self) -> bool:
        return self.availability_status == "verified_in_stock"

    @property
    def distribution_store_id(self) -> str | None:
        """Return the store ID counted by distribution, if this is a store row."""

        if self.location.kind != "store":
            return None
        store_number = str(self.location.store_number or "").strip()
        return store_number or None

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
            "search_observed": True,
            "is_sponsored": self.is_sponsored,
            "distribution_store_id": self.distribution_store_id,
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
            "search_observed": True,
            "is_sponsored": self.is_sponsored,
            "distribution_store_id": self.distribution_store_id,
            "distribution_contract": store_search_distribution_contract(),
            "price_metrics": dict(self.metric_values),
            "observed_at": self.observed_at,
            "source_authority": "search_location_observation",
            "location_authority": "retailer_location_master",
            "eligible": True,
            "exclusion_reasons": [],
        }

    def for_comparison(
        self,
        metric: str,
        *,
        evidence_scope: PriceEvidenceScope = "search_presence",
    ) -> ProductPriceObservation | None:
        # ``verified_local`` remains accepted while callers migrate, but it no
        # longer invokes stock/sponsorship eligibility. Both values identify the
        # same positive-priced Search evidence population.
        if evidence_scope not in {"verified_local", "search_presence"}:
            raise ValueError(f"unsupported price evidence scope {evidence_scope!r}")
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
            in_stock=self.in_stock,
            search_observed=True,
            availability_status=self.availability_status,
            verified_local_availability=self.verified_local_availability,
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
    conflicting_availability_keys: frozenset[tuple[str, str]]
    checksum: str

    def comparison_observations(
        self,
        product_ids: set[str],
        comparison_metric: str,
        *,
        evidence_scope: PriceEvidenceScope = "search_presence",
    ) -> dict[str, tuple[ProductPriceObservation, ...]]:
        grouped: dict[str, list[ProductPriceObservation]] = {
            product_id: [] for product_id in product_ids
        }
        for observation in self.observations:
            if observation.product_id not in product_ids:
                continue
            projected = observation.for_comparison(
                comparison_metric,
                evidence_scope=evidence_scope,
            )
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


def _location_from_offer(
    offer: ClassifiedOffer,
    location_index: dict[tuple[str, str], JsonObject],
) -> PriceLocation:
    value = offer.offer
    store_number = str(value.store_number or "").strip() or None
    kind: Literal["store", "service_area"] = "store" if store_number else "service_area"
    lookup = (
        location_index.get((value.retailer_id, store_number))
        if store_number is not None
        else location_index.get((value.retailer_id, f"zip:{value.zipcode}"))
        if value.zipcode is not None
        else None
    ) or {}
    scope_value = store_number or value.zipcode or "unknown"
    return PriceLocation(
        scope_key=f"{value.retailer_id}|{kind}|{scope_value}",
        kind=kind,
        store_number=store_number,
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
            "seller": row.seller,
            "seller_status": row.seller_status,
            "scope_key": row.location.scope_key,
            "location": row.location.to_contract(),
            "offer_id": row.offer_id,
            "price": row.package_price,
            "regular_price": row.regular_price,
            "discounted_price": row.discounted_price,
            "is_sponsored": row.is_sponsored,
            "distribution_store_id": row.distribution_store_id,
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
    """Build canonical latest Search-listed price evidence for one retailer."""

    def __init__(
        self,
        pack: ProductPack,
        brand_resolver: GovernedBrandResolver,
        *,
        retailer_names: dict[str, str] | None = None,
        seller_resolver: GovernedSellerResolver | None = None,
    ) -> None:
        self._pack = pack
        self._brands = brand_resolver
        self._retailer_names = dict(retailer_names or {})
        self._sellers = seller_resolver
        self._classifier = OfferClassifier(pack, brand_resolver)

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
        selector: LatestProductLocationSelector[ProductLocationObservation | None] = (
            LatestProductLocationSelector()
        )
        conflicting_keys: set[tuple[str, str]] = set()
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
            product_key = f"{offer.retailer_id}:{offer.retailer_product_id}"
            product = context.get(product_key, {})
            classified = complete_attributes_from_pdp(
                classified,
                product,
                classifier=self._classifier,
                pack=self._pack,
                seller_resolver=None,
            )
            observed_seller = (
                str(product["seller"]).strip() or None
                if product.get("seller") is not None
                else None
            )
            seller_status: SellerStatus = "not_governed"
            if classified.scope_reason == SELLER_POLICY_EXCLUSION_REASON:
                reasons.append("known_third_party_seller")
            if self._sellers is not None:
                seller_resolution = self._sellers.resolve(
                    offer.retailer_id,
                    observed_seller,
                )
                if not seller_resolution.eligible and "known_third_party_seller" not in reasons:
                    reasons.append("known_third_party_seller")
                elif seller_resolution.status in {
                    "verified_first_party",
                    "seller_unverified",
                    "not_governed",
                }:
                    seller_status = seller_resolution.status
            if not is_product_location_state(classified):
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
                if "known_third_party_seller" not in reasons:
                    continue
                selector.add(
                    None,
                    retailer_id=offer.retailer_id,
                    product_id=offer.retailer_product_id,
                    store_number=location.store_number,
                    zipcode=location.zipcode,
                    observed_at=normalized_observed_at(offer.collected_at),
                    in_stock=offer.in_stock,
                    is_sponsored=offer.is_sponsored,
                    tie_breaker=offer.offer_id,
                )
                continue
            eligible_input_rows += 1
            assert offer.price is not None

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
                observed_at=normalized_observed_at(offer.collected_at),
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
                in_stock=offer.in_stock,
                seller=observed_seller,
                seller_status=seller_status,
            )
            selection_key = product_location_key(
                retailer_id=observation.retailer_id,
                product_id=observation.product_id,
                store_number=observation.location.store_number,
                zipcode=observation.location.zipcode,
            )
            assert selection_key is not None
            existing = selector.get(selection_key)
            if existing is not None and existing.package_price != observation.package_price:
                conflicting_keys.add((observation.product_id, observation.location.scope_key))
            selector.add(
                observation,
                retailer_id=observation.retailer_id,
                product_id=observation.product_id,
                store_number=observation.location.store_number,
                zipcode=observation.location.zipcode,
                observed_at=observation.observed_at,
                in_stock=observation.in_stock,
                is_sponsored=observation.is_sponsored,
                tie_breaker=observation.offer_id,
            )

        observations = tuple(
            sorted(
                (row for row in selector.values() if row is not None),
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
            duplicate_rows=selector.duplicate_rows,
            conflicting_keys=frozenset(conflicting_keys),
            conflicting_availability_keys=frozenset(
                (product_id, f"{location_retailer_id}|{kind}|{location_value}")
                for location_retailer_id, product_id, kind, location_value in (
                    selector.conflicting_availability_keys
                )
            ),
            checksum=_population_checksum(observations),
        )
