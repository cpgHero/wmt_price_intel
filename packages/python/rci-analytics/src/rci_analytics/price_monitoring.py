"""Deterministic retailer-within-location price monitoring projections."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from statistics import median
from typing import Any, Literal, cast

from rci_analytics.models import ClassifiedOffer, JsonObject, NormalizedOffer
from rci_analytics.product_pack import ProductPack
from rci_retailer_packs import GovernedBrandResolver

BrandType = Literal["private_label", "regional", "national", "unclassified"]


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


@dataclass(frozen=True, slots=True)
class PriceMonitoringFilters:
    retailer_id: str
    brand_type: BrandType | Literal["all"] = "all"
    state: str | None = None
    city: str | None = None
    product_id: str | None = None


def _round(value: float | int | None, places: int = 4) -> float | None:
    return round(float(value), places) if value is not None else None


def _quantile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    low = int(position)
    high = min(len(ordered) - 1, low + 1)
    fraction = position - low
    return ordered[low] * (1 - fraction) + ordered[high] * fraction


def _price_stats(values: Iterable[float], *, product_medians: Iterable[float] = ()) -> JsonObject:
    prices = sorted(round(float(value), 4) for value in values)
    products = [float(value) for value in product_medians]
    if not prices:
        return {
            "minimum": None,
            "q1": None,
            "observation_median": None,
            "product_equal_weighted_median": None,
            "q3": None,
            "maximum": None,
            "range": None,
            "modal_price": None,
            "modal_share": None,
            "observation_count": 0,
        }
    counts = Counter(prices)
    modal_count = max(counts.values())
    modal_price = min(price for price, count in counts.items() if count == modal_count)
    return {
        "minimum": _round(prices[0]),
        "q1": _round(_quantile(prices, 0.25)),
        "observation_median": _round(median(prices)),
        "product_equal_weighted_median": _round(median(products)) if products else None,
        "q3": _round(_quantile(prices, 0.75)),
        "maximum": _round(prices[-1]),
        "range": _round(prices[-1] - prices[0]),
        "modal_price": _round(modal_price),
        "modal_share": _round(modal_count / len(prices)),
        "observation_count": len(prices),
    }


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
        store_name=(str(lookup["store_name"]) if lookup.get("store_name") else None),
        zipcode=value.zipcode or (str(lookup["zipcode"]) if lookup.get("zipcode") else None),
        city=str(lookup["city"]) if lookup.get("city") else None,
        state=str(lookup["state"]) if lookup.get("state") else None,
        country=str(lookup.get("country") or "USA"),
        latitude=(
            value.latitude
            if value.latitude is not None
            else float(lookup["latitude"])
            if lookup.get("latitude") is not None
            else None
        ),
        longitude=(
            value.longitude
            if value.longitude is not None
            else float(lookup["longitude"])
            if lookup.get("longitude") is not None
            else None
        ),
    )


def _observed_at(value: str | None) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=UTC)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=UTC)


def classified_offer_from_record(record: JsonObject) -> ClassifiedOffer:
    """Restore an immutable classified Parquet row to its typed analytics record."""

    def document(field: str, default: Any) -> Any:
        value = record.get(field)
        if value in (None, ""):
            return default
        if isinstance(value, str):
            return json.loads(value)
        return value

    attributes = document("attributes_json", {})
    metrics = document("metrics_json", {})
    review_reasons = document("review_reasons_json", [])
    return ClassifiedOffer(
        offer=NormalizedOffer(
            offer_id=str(record["offer_id"]),
            retailer_id=str(record["retailer_id"]),
            retailer_product_id=str(record["retailer_product_id"]),
            title=str(record.get("title") or "Untitled product"),
            brand=str(record["brand"]) if record.get("brand") not in (None, "") else None,
            price=(
                Decimal(str(record["price"])) if record.get("price") not in (None, "") else None
            ),
            currency=str(record.get("currency") or "USD"),
            zipcode=(
                str(record["zipcode"]).zfill(5) if record.get("zipcode") not in (None, "") else None
            ),
            store_number=(
                str(record["store_number"])
                if record.get("store_number") not in (None, "")
                else None
            ),
            latitude=(
                float(record["latitude"]) if record.get("latitude") not in (None, "") else None
            ),
            longitude=(
                float(record["longitude"]) if record.get("longitude") not in (None, "") else None
            ),
            in_stock=(bool(record["in_stock"]) if record.get("in_stock") is not None else None),
            product_url=(
                str(record["product_url"]) if record.get("product_url") not in (None, "") else None
            ),
            image_url=(
                str(record["image_url"]) if record.get("image_url") not in (None, "") else None
            ),
            collected_at=(
                str(record["collected_at"])
                if record.get("collected_at") not in (None, "")
                else None
            ),
            raw={},
        ),
        in_scope=bool(record.get("in_scope")),
        scope_reason=(
            str(record["scope_reason"]) if record.get("scope_reason") not in (None, "") else None
        ),
        attributes=dict(attributes) if isinstance(attributes, dict) else {},
        metrics={
            str(key): Decimal(str(value)) if value is not None else None
            for key, value in dict(metrics).items()
        }
        if isinstance(metrics, dict)
        else {},
        review_reasons=tuple(str(value) for value in review_reasons),
    )


class PriceMonitoringProjector:
    """Build a filter-scoped view without using cross-retailer matches."""

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
        self._parity_tolerance = Decimal(
            str(pack.document.get("qa_rules", {}).get("parity_tolerance_dollars", 0.01))
        )

    def build(
        self,
        offers: Iterable[ClassifiedOffer],
        *,
        analysis_id: str,
        generated_at: str,
        filters: PriceMonitoringFilters,
        location_index: dict[tuple[str, str], JsonObject] | None = None,
        expected_location_count: int = 0,
        source_rows: int = 0,
        artifact_checksums: Iterable[str] = (),
        product_context: dict[str, JsonObject] | None = None,
        retailer_options: Iterable[str] = (),
    ) -> JsonObject:
        location_lookup = location_index or {}
        context = product_context or {}
        admitted: list[JsonObject] = []
        excluded = Counter[str]()
        seen_keys: dict[tuple[str, str], JsonObject] = {}
        conflicting_keys: set[tuple[str, str]] = set()
        duplicate_rows = 0
        classified_rows = 0
        eligible_input_rows = 0
        excluded_rows = 0
        source_locations: dict[str, PriceLocation] = {}
        all_retailers: set[str] = set(retailer_options)

        for classified in offers:
            offer = classified.offer
            all_retailers.add(offer.retailer_id)
            if offer.retailer_id != filters.retailer_id:
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

            key = (offer.retailer_product_id, location.scope_key)
            product_key = f"{offer.retailer_id}:{offer.retailer_product_id}"
            product = context.get(product_key, {})
            observed_brand = str(product.get("brand") or offer.brand or "").strip() or None
            brand_governance = classified.attributes.get("_brand_governance")
            resolution = self._brands.resolve(
                offer.retailer_id,
                observed_brand,
                category=self._pack.name,
            )
            if resolution.resolution_method == "governed_override":
                brand_type = resolution.role
                brand_origin = "user"
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
            row: JsonObject = {
                "observation_id": offer.offer_id,
                "product_id": offer.retailer_product_id,
                "name": str(product.get("name") or offer.title),
                "brand": brand_name or product.get("brand") or observed_brand,
                "brand_type": brand_type,
                "brand_origin": brand_origin,
                "brand_status": brand_status,
                "image_url": product.get("image_url") or offer.image_url,
                "url": product.get("url") or offer.product_url,
                "location": location,
                "price": float(offer.price),
                "observed_at": offer.collected_at,
                "offer_id": offer.offer_id,
            }
            existing = seen_keys.get(key)
            if existing is None:
                seen_keys[key] = row
                continue
            duplicate_rows += 1
            if existing["price"] != row["price"]:
                conflicting_keys.add(key)
            current_rank = (
                _observed_at(str(existing.get("observed_at") or "")),
                str(existing["offer_id"]),
            )
            next_rank = (_observed_at(str(row.get("observed_at") or "")), str(row["offer_id"]))
            if next_rank > current_rank:
                seen_keys[key] = row

        admitted = list(seen_keys.values())
        brand_types = Counter(str(row["brand_type"]) for row in admitted)
        states = Counter(row["location"].state for row in admitted if row["location"].state)
        state_scoped = [
            row
            for row in admitted
            if filters.state is None or row["location"].state == filters.state
        ]
        cities = Counter(row["location"].city for row in state_scoped if row["location"].city)
        visible = [
            row
            for row in admitted
            if (filters.brand_type == "all" or row["brand_type"] == filters.brand_type)
            and (filters.state is None or row["location"].state == filters.state)
            and (filters.city is None or row["location"].city == filters.city)
            and (filters.product_id is None or row["product_id"] == filters.product_id)
        ]

        product_groups: dict[str, list[JsonObject]] = defaultdict(list)
        location_groups: dict[str, list[JsonObject]] = defaultdict(list)
        brand_groups: dict[str, list[JsonObject]] = defaultdict(list)
        for row in visible:
            product_groups[str(row["product_id"])].append(row)
            location_groups[row["location"].scope_key].append(row)
            brand_groups[str(row["brand_type"])].append(row)

        product_medians = [
            median(float(row["price"]) for row in values) for values in product_groups.values()
        ]
        distribution = _price_stats(
            (float(row["price"]) for row in visible),
            product_medians=product_medians,
        )
        product_summaries: list[JsonObject] = []
        consistent_observations = 0
        for product_id, rows in product_groups.items():
            prices = [float(row["price"]) for row in rows]
            stats = _price_stats(prices)
            reference = stats["modal_price"]
            consistent = (
                sum(
                    abs(Decimal(str(value)) - Decimal(str(reference))) <= self._parity_tolerance
                    for value in prices
                )
                if reference is not None
                else 0
            )
            consistent_observations += consistent
            sample_limit = len(rows) if filters.product_id == product_id else 20
            sample = sorted(
                rows,
                key=lambda row: (
                    str(row["location"].state or ""),
                    str(row["location"].city or ""),
                    str(row["location"].store_number or row["location"].zipcode or ""),
                ),
            )[:sample_limit]
            identity = rows[0]
            product_summaries.append(
                {
                    "product_id": product_id,
                    "name": identity["name"],
                    "brand": identity["brand"],
                    "brand_type": identity["brand_type"],
                    "brand_origin": identity["brand_origin"],
                    "brand_status": identity["brand_status"],
                    "image_url": identity["image_url"],
                    "url": identity["url"],
                    "locations": len({row["location"].scope_key for row in rows}),
                    "states": len({row["location"].state for row in rows if row["location"].state}),
                    "cities": len(
                        {
                            (row["location"].state, row["location"].city)
                            for row in rows
                            if row["location"].city
                        }
                    ),
                    "price_stats": stats,
                    "consistency_rate": _round(consistent / len(rows)) if rows else None,
                    "sample_locations": [
                        {
                            "scope_key": row["location"].scope_key,
                            "store_number": row["location"].store_number,
                            "store_name": row["location"].store_name,
                            "zipcode": row["location"].zipcode,
                            "city": row["location"].city,
                            "state": row["location"].state,
                            "price": _round(float(row["price"])),
                            "observed_at": row["observed_at"],
                        }
                        for row in sample
                    ],
                }
            )

        product_summaries.sort(
            key=lambda row: (
                -int(row["locations"]),
                str(row["name"]).casefold(),
                str(row["product_id"]),
            )
        )
        location_summaries = [self._location_summary(rows) for rows in location_groups.values()]
        location_summaries.sort(
            key=lambda row: (
                str(row["state"] or ""),
                str(row["city"] or ""),
                str(row["store_number"] or row["zipcode"] or ""),
            )
        )
        location_limit = 3_000
        location_display = {
            "returned": min(len(location_summaries), location_limit),
            "total": len(location_summaries),
            "sampled": len(location_summaries) > location_limit,
        }
        location_summaries = location_summaries[:location_limit]

        geography_level: Literal["state", "city"] = "city" if filters.state else "state"
        geography_groups: dict[str, list[JsonObject]] = defaultdict(list)
        for row in visible:
            if geography_level == "state":
                geography_key = row["location"].state or "Unknown state"
            else:
                geography_key = row["location"].city or "Unknown city"
            geography_groups[str(geography_key)].append(row)
        geographies = [
            self._geography_summary(geography_level, key, rows, state=filters.state)
            for key, rows in geography_groups.items()
        ]
        geographies.sort(key=lambda row: (-int(row["observations"]), str(row["label"])))

        total_considered = classified_rows
        unresolved = sum(row["brand_type"] == "unclassified" for row in admitted)
        missing_geography = sum(
            not row["location"].state or not row["location"].city for row in admitted
        )
        quality_checks = [
            self._quality_check(
                "missing-or-zero-price",
                "Missing or zero price",
                excluded["missing_or_zero_price"],
                total_considered,
                "warning",
                "Search observations without a positive USD package price are "
                "excluded from price metrics.",
            ),
            self._quality_check(
                "duplicate-product-location",
                "Duplicate product-location rows",
                duplicate_rows,
                max(1, len(admitted) + duplicate_rows),
                "warning",
                "The latest Search observation is selected for a product-location pair; "
                "all earlier duplicate rows remain an auditable quality count.",
            ),
            self._quality_check(
                "conflicting-product-location-price",
                "Conflicting prices within the run",
                len(conflicting_keys),
                max(1, len(admitted)),
                "warning",
                "A product-location pair had more than one price in the run; the latest "
                "observation controls the current view.",
            ),
            self._quality_check(
                "unclassified-brand",
                "Unclassified brand",
                unresolved,
                max(1, len(admitted)),
                "warning",
                "Brand role is unresolved and remains visible for Brand Workbench review.",
            ),
            self._quality_check(
                "incomplete-geography",
                "Incomplete city or state",
                missing_geography,
                max(1, len(admitted)),
                "warning",
                "The observation is retained, but country/state/city drill-through may "
                "be incomplete.",
            ),
        ]
        quality_status = "warning" if any(row["count"] for row in quality_checks) else "ready"
        observed_locations = len(location_groups)
        scoped_expected_location_count = expected_location_count or len(source_locations)
        if filters.state is not None:
            scoped_expected_location_count = len(
                {
                    location.scope_key
                    for location in source_locations.values()
                    if location.state == filters.state
                    and (filters.city is None or location.city == filters.city)
                }
            )
        source_values = [str(row.get("observed_at")) for row in admitted if row.get("observed_at")]
        all_retailer_options = sorted(all_retailers or {filters.retailer_id})
        return {
            "schema_version": "1.0.0",
            "analysis_id": analysis_id,
            "generated_at": generated_at,
            "product_pack": {
                "id": self._pack.id,
                "name": self._pack.name,
                "version": self._pack.version,
            },
            "retailer": {
                "id": filters.retailer_id,
                "name": self._retailer_names.get(
                    filters.retailer_id, filters.retailer_id.replace("_", " ").title()
                ),
                "location_dimension": "service_area"
                if visible and all(row["location"].kind == "service_area" for row in visible)
                else "store",
            },
            "source": {
                "authority": "Search",
                "grain": "retailer product x retailer location x latest observation in run",
                "observed_start": min(source_values) if source_values else None,
                "observed_end": max(source_values) if source_values else None,
                "source_rows": source_rows,
                "classified_rows": classified_rows,
                "artifact_checksums": sorted(set(artifact_checksums)),
            },
            "filters": {
                "retailer_id": filters.retailer_id,
                "brand_type": filters.brand_type,
                "state": filters.state,
                "city": filters.city,
                "product_id": filters.product_id,
            },
            "filter_options": {
                "retailers": [
                    {
                        "id": value,
                        "name": self._retailer_names.get(value, value.replace("_", " ").title()),
                    }
                    for value in all_retailer_options
                ],
                "brand_types": [
                    {
                        "value": value,
                        "label": value.replace("_", " ").title(),
                        "count": brand_types[value],
                    }
                    for value in ("private_label", "regional", "national", "unclassified")
                ],
                "states": [
                    {"value": str(value), "label": str(value), "count": count}
                    for value, count in sorted(states.items())
                ],
                "cities": [
                    {"value": str(value), "label": str(value), "count": count}
                    for value, count in sorted(cities.items())
                ],
            },
            "summary": {
                "observed_locations": observed_locations,
                "expected_locations": max(0, scoped_expected_location_count),
                "coverage_rate": _round(observed_locations / scoped_expected_location_count)
                if scoped_expected_location_count
                else None,
                "observed_products": len(product_groups),
                "eligible_observations": len(visible),
                "usable_price_rate": _round(eligible_input_rows / total_considered)
                if total_considered
                else 0.0,
                "price_consistency_rate": _round(consistent_observations / len(visible))
                if visible
                else None,
            },
            "price_distribution": distribution,
            "brand_portfolio": [
                {
                    "brand_type": value,
                    "products": len({row["product_id"] for row in rows}),
                    "locations": len({row["location"].scope_key for row in rows}),
                    "observations": len(rows),
                    "median_price": _round(median(float(row["price"]) for row in rows))
                    if rows
                    else None,
                }
                for value in ("private_label", "regional", "national", "unclassified")
                if (rows := brand_groups.get(value, []))
            ],
            "geographies": geographies,
            "locations": location_summaries,
            "location_display": location_display,
            "products": product_summaries,
            "quality": {"status": quality_status, "checks": quality_checks},
            "movement": {
                "status": "unavailable",
                "reason": (
                    "A second complete comparable snapshot is required before price "
                    "movement is calculated."
                ),
            },
        }

    @staticmethod
    def _quality_check(
        check_id: str,
        label: str,
        count: int,
        denominator: int,
        severity: str,
        definition: str,
    ) -> JsonObject:
        return {
            "id": check_id,
            "label": label,
            "count": int(count),
            "rate": _round(count / denominator) or 0.0,
            "severity": severity,
            "definition": definition,
        }

    @staticmethod
    def _location_summary(rows: list[JsonObject]) -> JsonObject:
        location: PriceLocation = rows[0]["location"]
        prices = [float(row["price"]) for row in rows]
        return {
            "scope_key": location.scope_key,
            "kind": location.kind,
            "store_number": location.store_number,
            "store_name": location.store_name,
            "zipcode": location.zipcode,
            "city": location.city,
            "state": location.state,
            "country": location.country,
            "latitude": location.latitude,
            "longitude": location.longitude,
            "products": len({row["product_id"] for row in rows}),
            "observations": len(rows),
            "minimum_price": _round(min(prices)),
            "median_price": _round(median(prices)),
            "maximum_price": _round(max(prices)),
        }

    @staticmethod
    def _geography_summary(
        level: Literal["state", "city"],
        key: str,
        rows: list[JsonObject],
        *,
        state: str | None,
    ) -> JsonObject:
        prices = [float(row["price"]) for row in rows]
        latitudes = [
            row["location"].latitude for row in rows if row["location"].latitude is not None
        ]
        longitudes = [
            row["location"].longitude for row in rows if row["location"].longitude is not None
        ]
        return {
            "level": level,
            "key": key,
            "label": key,
            "state": key if level == "state" else state,
            "city": key if level == "city" else None,
            "locations": len({row["location"].scope_key for row in rows}),
            "products": len({row["product_id"] for row in rows}),
            "observations": len(rows),
            "latitude": _round(median(latitudes), 6) if latitudes else None,
            "longitude": _round(median(longitudes), 6) if longitudes else None,
            "price_stats": _price_stats(prices),
        }
