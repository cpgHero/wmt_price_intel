"""Deterministic retailer-within-location price monitoring projections."""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from statistics import median
from typing import Any, Literal

from rci_analytics.models import ClassifiedOffer, JsonObject, NormalizedOffer
from rci_analytics.product_location import (
    PRODUCT_LOCATION_OBSERVATION_SCHEMA_VERSION,
    BrandType,
    PriceLocation,
    ProductLocationPopulation,
    ProductLocationProjector,
    ProductPriceObservation,
)
from rci_analytics.product_pack import ProductPack
from rci_retailer_packs import GovernedBrandResolver


@dataclass(frozen=True, slots=True)
class PriceMonitoringFilters:
    retailer_id: str
    brand_type: BrandType | Literal["all"] = "all"
    state: str | None = None
    city: str | None = None
    zipcode: str | None = None
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


def _price_histogram(values: Iterable[float], *, maximum_bins: int = 8) -> list[JsonObject]:
    """Return deterministic equal-width bins for one product's observed store prices."""

    prices = sorted(round(float(value), 4) for value in values)
    if not prices:
        return []
    if prices[0] == prices[-1]:
        return [
            {
                "lower": prices[0],
                "upper": prices[-1],
                "count": len(prices),
                "share": 1.0,
            }
        ]
    bin_count = min(maximum_bins, max(2, math.ceil(math.sqrt(len(prices)))))
    width = (prices[-1] - prices[0]) / bin_count
    counts = [0] * bin_count
    for price in prices:
        index = min(bin_count - 1, int((price - prices[0]) / width))
        counts[index] += 1
    return [
        {
            "lower": _round(prices[0] + index * width),
            "upper": _round(prices[0] + (index + 1) * width),
            "count": count,
            "share": _round(count / len(prices)),
        }
        for index, count in enumerate(counts)
    ]


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
            regular_price=(
                Decimal(str(record["regular_price"]))
                if record.get("regular_price") not in (None, "")
                else None
            ),
            discounted_price=(
                Decimal(str(record["discounted_price"]))
                if record.get("discounted_price") not in (None, "")
                else None
            ),
            is_sponsored=(
                bool(record["is_sponsored"]) if record.get("is_sponsored") is not None else None
            ),
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
        self._population = ProductLocationProjector(
            pack,
            brand_resolver,
            retailer_names=self._retailer_names,
        )
        self._parity_tolerance = Decimal(
            str(pack.document.get("qa_rules", {}).get("parity_tolerance_dollars", 0.01))
        )
        secondary_metrics = [
            str(value)
            for value in pack.document.get("normalization", {}).get("secondary_metrics", [])
        ]
        self._unit_price_metric = next(
            (
                value
                for value in secondary_metrics
                if value.startswith("price_per_") and not value.endswith(("_low", "_high"))
            ),
            None,
        )

    def canonical_population(
        self,
        offers: Iterable[ClassifiedOffer],
        *,
        retailer_id: str,
        location_index: dict[tuple[str, str], JsonObject] | None = None,
        eligible_location_index: dict[tuple[str, str], JsonObject] | None = None,
        product_context: dict[str, JsonObject] | None = None,
        retailer_options: Iterable[str] = (),
    ) -> ProductLocationPopulation:
        """Project the governed product-location population shared by every module."""

        return self._population.build(
            offers,
            retailer_id=retailer_id,
            location_index=location_index or {},
            eligible_location_index=eligible_location_index or location_index or {},
            product_context=product_context or {},
            retailer_options=retailer_options,
        )

    def comparison_observations(
        self,
        offers: Iterable[ClassifiedOffer],
        *,
        retailer_id: str,
        product_ids: set[str],
        comparison_metric: str,
        location_index: dict[tuple[str, str], JsonObject] | None = None,
        product_context: dict[str, JsonObject] | None = None,
    ) -> dict[str, tuple[ProductPriceObservation, ...]]:
        """Return comparison-ready rows derived from the canonical population."""

        return self.canonical_population(
            offers,
            retailer_id=retailer_id,
            location_index=location_index,
            product_context=product_context,
        ).comparison_observations(
            product_ids=product_ids,
            comparison_metric=comparison_metric,
        )

    def build(
        self,
        offers: Iterable[ClassifiedOffer],
        *,
        analysis_id: str,
        generated_at: str,
        filters: PriceMonitoringFilters,
        location_index: dict[tuple[str, str], JsonObject] | None = None,
        eligible_location_index: dict[tuple[str, str], JsonObject] | None = None,
        expected_location_count: int = 0,
        source_rows: int = 0,
        artifact_checksums: Iterable[str] = (),
        product_context: dict[str, JsonObject] | None = None,
        retailer_options: Iterable[str] = (),
        location_limit: int | None = 1_200,
        product_location_limit: int | None = 200,
    ) -> JsonObject:
        context = product_context or {}
        population = self.canonical_population(
            offers,
            retailer_id=filters.retailer_id,
            location_index=location_index or {},
            eligible_location_index=eligible_location_index or location_index or {},
            product_context=context,
            retailer_options=retailer_options,
        )
        admitted = [row.to_price_monitoring_row() for row in population.observations]
        excluded = Counter(dict(population.exclusion_counts))
        conflicting_keys = set(population.conflicting_keys)
        duplicate_rows = population.duplicate_rows
        classified_rows = population.classified_rows
        eligible_input_rows = population.eligible_input_rows
        source_locations = dict(population.source_locations)
        eligible_scope_keys = set(population.eligible_scope_keys)
        all_retailers = set(population.all_retailers)

        brand_types = Counter(str(row["brand_type"]) for row in admitted)
        states = Counter(row["location"].state for row in admitted if row["location"].state)
        state_scoped = [
            row
            for row in admitted
            if filters.state is None or row["location"].state == filters.state
        ]
        cities = (
            Counter(row["location"].city for row in state_scoped if row["location"].city)
            if filters.state is not None
            else Counter()
        )
        city_scoped = [
            row
            for row in state_scoped
            if filters.city is None or row["location"].city == filters.city
        ]
        zipcodes = (
            Counter(row["location"].zipcode for row in city_scoped if row["location"].zipcode)
            if filters.city is not None
            else Counter()
        )
        product_option_rows = [
            row
            for row in admitted
            if (filters.brand_type == "all" or row["brand_type"] == filters.brand_type)
            and (filters.state is None or row["location"].state == filters.state)
            and (filters.city is None or row["location"].city == filters.city)
            and (filters.zipcode is None or row["location"].zipcode == filters.zipcode)
        ]
        visible = [
            row
            for row in admitted
            if (filters.brand_type == "all" or row["brand_type"] == filters.brand_type)
            and (filters.state is None or row["location"].state == filters.state)
            and (filters.city is None or row["location"].city == filters.city)
            and (filters.zipcode is None or row["location"].zipcode == filters.zipcode)
            and (filters.product_id is None or row["product_id"] == filters.product_id)
        ]
        scoped_eligible_locations = [
            source_locations[key]
            for key in eligible_scope_keys
            if key in source_locations
            and (filters.state is None or source_locations[key].state == filters.state)
            and (filters.city is None or source_locations[key].city == filters.city)
            and (filters.zipcode is None or source_locations[key].zipcode == filters.zipcode)
        ]
        scoped_expected_location_count = (
            len(scoped_eligible_locations)
            if filters.state is not None or filters.city is not None or filters.zipcode is not None
            else expected_location_count or len(scoped_eligible_locations)
        )

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
        product_options: list[JsonObject] = []
        option_groups: dict[str, list[JsonObject]] = defaultdict(list)
        for row in product_option_rows:
            option_groups[str(row["product_id"])].append(row)
        for product_id, rows in option_groups.items():
            identity = rows[0]
            product_options.append(
                {
                    "value": product_id,
                    "label": str(identity["name"]),
                    "count": len({row["location"].scope_key for row in rows}),
                    "brand": identity["brand"],
                    "brand_type": identity["brand_type"],
                    "image_url": identity["image_url"],
                }
            )
        product_options.sort(key=lambda row: (-int(row["count"]), str(row["label"]).casefold()))
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
            sample_limit = (
                len(rows)
                if product_location_limit is None and filters.product_id == product_id
                else product_location_limit
                if filters.product_id == product_id
                else 20
            )
            sample = sorted(
                rows,
                key=lambda row: (
                    str(row["location"].state or ""),
                    str(row["location"].city or ""),
                    str(row["location"].store_number or row["location"].zipcode or ""),
                ),
            )[:sample_limit]
            identity = rows[0]
            product_identity = context.get(f"{filters.retailer_id}:{product_id}", {})
            observed_product_locations = len({row["location"].scope_key for row in rows})
            eligible_product_locations = max(
                scoped_expected_location_count,
                observed_product_locations,
            )
            not_observed_product_locations = max(
                0,
                eligible_product_locations - observed_product_locations,
            )
            product_summaries.append(
                {
                    "product_id": product_id,
                    "name": identity["name"],
                    "brand": identity["brand"],
                    "seller": product_identity.get("seller"),
                    "pdp": product_identity.get(
                        "pdp",
                        {
                            "enriched": False,
                            "authority": {
                                "identity": "search",
                                "price": "search",
                                "availability": "search",
                            },
                        },
                    ),
                    "brand_type": identity["brand_type"],
                    "brand_origin": identity["brand_origin"],
                    "brand_status": identity["brand_status"],
                    "image_url": identity["image_url"],
                    "url": identity["url"],
                    "locations": observed_product_locations,
                    "states": len({row["location"].state for row in rows if row["location"].state}),
                    "cities": len(
                        {
                            (row["location"].state, row["location"].city)
                            for row in rows
                            if row["location"].city
                        }
                    ),
                    "price_stats": stats,
                    "unit_price": self._unit_price_summary(rows),
                    "consistency_rate": _round(consistent / len(rows)) if rows else None,
                    "availability": self._availability_summary(rows),
                    "promotion": self._promotion_summary(rows),
                    "sponsorship": self._sponsorship_summary(rows),
                    "presence": {
                        "observed_locations": observed_product_locations,
                        "eligible_locations": eligible_product_locations,
                        "not_observed_locations": not_observed_product_locations,
                        "observed_rate": (
                            _round(observed_product_locations / eligible_product_locations)
                            if eligible_product_locations
                            else None
                        ),
                        "not_observed_rate": (
                            _round(not_observed_product_locations / eligible_product_locations)
                            if eligible_product_locations
                            else None
                        ),
                        "definition": (
                            "Observed means the exact product appeared in successful Search "
                            "with a positive price. Not observed is a Search non-observation "
                            "within the retailer's eligible location scope, not proof of "
                            "non-carriage."
                        ),
                    },
                    "price_histogram": _price_histogram(prices),
                    "sample_locations": [
                        {
                            "scope_key": row["location"].scope_key,
                            "store_number": row["location"].store_number,
                            "store_name": row["location"].store_name,
                            "zipcode": row["location"].zipcode,
                            "city": row["location"].city,
                            "state": row["location"].state,
                            "price": _round(float(row["price"])),
                            "is_sponsored": row["is_sponsored"],
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
        location_summaries = (
            [self._location_summary(rows) for rows in location_groups.values()]
            if filters.product_id is not None
            else []
        )
        location_summaries.sort(
            key=lambda row: (
                str(row["state"] or ""),
                str(row["city"] or ""),
                str(row["store_number"] or row["zipcode"] or ""),
            )
        )
        location_display = {
            "returned": (
                len(location_summaries)
                if location_limit is None
                else min(len(location_summaries), location_limit)
            ),
            "total": len(location_summaries),
            "sampled": location_limit is not None and len(location_summaries) > location_limit,
        }
        if location_limit is not None:
            location_summaries = location_summaries[:location_limit]

        geography_level: Literal["state", "city", "zipcode"] = (
            "zipcode" if filters.city else "city" if filters.state else "state"
        )
        geography_groups: dict[str, list[JsonObject]] = defaultdict(list)
        for row in visible:
            if geography_level == "state":
                geography_key = row["location"].state or "Unknown state"
            elif geography_level == "city":
                geography_key = row["location"].city or "Unknown city"
            else:
                geography_key = row["location"].zipcode or "Unknown ZIP"
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
        observed_location_keys = set(location_groups)
        observed_locations = len(observed_location_keys)
        source_values = [str(row.get("observed_at")) for row in admitted if row.get("observed_at")]
        presence_rate = (
            _round(observed_locations / scoped_expected_location_count)
            if scoped_expected_location_count
            else None
        )
        not_observed_count = max(0, scoped_expected_location_count - observed_locations)
        known_not_observed = [
            location
            for location in scoped_eligible_locations
            if location.scope_key not in observed_location_keys
        ]
        known_not_observed.sort(
            key=lambda location: (
                str(location.state or ""),
                str(location.city or ""),
                str(location.zipcode or ""),
                str(location.store_number or ""),
            )
        )
        gap_groups: dict[str, list[PriceLocation]] = defaultdict(list)
        eligible_groups: dict[str, list[PriceLocation]] = defaultdict(list)
        for location in scoped_eligible_locations:
            if geography_level == "state":
                gap_key = location.state or "Unknown state"
            elif geography_level == "city":
                gap_key = location.city or "Unknown city"
            else:
                gap_key = location.zipcode or "Unknown ZIP"
            eligible_groups[gap_key].append(location)
            if location.scope_key not in observed_location_keys:
                gap_groups[gap_key].append(location)
        gap_geographies = [
            self._gap_geography_summary(
                geography_level,
                key,
                eligible_rows,
                gap_groups.get(key, []),
                state=filters.state,
                city=filters.city,
            )
            for key, eligible_rows in eligible_groups.items()
        ]
        gap_geographies.sort(
            key=lambda row: (
                -int(row["not_observed_locations"]),
                float(row["observed_rate"] or 0),
                str(row["label"]),
            )
        )
        gap_locations = [self._gap_location(location) for location in known_not_observed]
        gap_location_limit = (
            len(gap_locations) if location_limit is None else max(1_000, location_limit)
        )
        gap_display = {
            "returned": min(len(gap_locations), gap_location_limit),
            "total": not_observed_count,
            "sampled": len(gap_locations) > gap_location_limit,
            "missing_location_details": max(0, not_observed_count - len(gap_locations)),
        }
        gap_locations = gap_locations[:gap_location_limit]
        exceptions = self._price_exceptions(visible) if filters.product_id else []
        all_retailer_options = sorted(all_retailers or {filters.retailer_id})
        return {
            "schema_version": "1.3.0",
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
                "location_authority": "Retailer location master",
                "grain": "retailer product x retailer location x latest observation in run",
                "observed_start": min(source_values) if source_values else None,
                "observed_end": max(source_values) if source_values else None,
                "source_rows": source_rows,
                "classified_rows": classified_rows,
                "observation_schema_version": PRODUCT_LOCATION_OBSERVATION_SCHEMA_VERSION,
                "observation_population_checksum": population.checksum,
                "artifact_checksums": sorted(set(artifact_checksums)),
            },
            "filters": {
                "retailer_id": filters.retailer_id,
                "brand_type": filters.brand_type,
                "state": filters.state,
                "city": filters.city,
                "zipcode": filters.zipcode,
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
                "zipcodes": [
                    {"value": str(value), "label": str(value), "count": count}
                    for value, count in sorted(zipcodes.items())
                ],
                "products": product_options,
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
            "presence": {
                "status": "observed_only",
                "observed_locations": observed_locations,
                "eligible_locations": max(0, scoped_expected_location_count),
                "observed_presence_rate": presence_rate,
                "not_observed_locations": not_observed_count,
                "confirmed_gap_locations": 0,
                "definition": (
                    "Observed presence means the selected product appeared in successful "
                    "Search evidence. A Search non-observation is not proof that a store "
                    "does not carry the product."
                ),
            },
            "distribution_gaps": {
                "status": "search_non_observation",
                "definition": (
                    "Not observed means the selected product did not appear in the "
                    "successful Search result for a planned location. It is a location "
                    "review signal, not proof that the retailer does not carry the item."
                ),
                "location_display": gap_display,
                "geographies": gap_geographies,
                "locations": gap_locations,
            },
            "price_distribution": distribution,
            "price_histogram": _price_histogram(float(row["price"]) for row in visible),
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
            "exceptions": exceptions,
            "quality": {"status": quality_status, "checks": quality_checks},
            "movement": {
                "status": "unavailable",
                "reason": (
                    "A second complete comparable snapshot is required before price "
                    "movement is calculated."
                ),
            },
        }

    def _unit_price_summary(self, rows: list[JsonObject]) -> JsonObject:
        metric = self._unit_price_metric
        labels = {
            "price_per_lb": ("Price per pound", "lb"),
            "price_per_dozen": ("Price per dozen", "dozen"),
            "price_per_gallon": ("Price per gallon", "gal"),
            "price_per_each": ("Price per item", "each"),
        }
        if metric is None:
            label = None
            unit = None
        else:
            label, unit = labels.get(
                metric,
                (
                    metric.replace("_", " ").title(),
                    metric.removeprefix("price_per_").replace("_", " "),
                ),
            )
        values = [
            float(value)
            for row in rows
            if metric
            and isinstance(row.get("price_metrics"), dict)
            and (value := row["price_metrics"].get(metric)) is not None
            and float(value) > 0
        ]
        return {
            "status": "observed" if values else "unavailable",
            "metric": metric,
            "label": label,
            "unit": unit,
            "price_stats": _price_stats(values),
            "known_observations": len(values),
            "total_observations": len(rows),
            "coverage_rate": _round(len(values) / len(rows)) if rows else None,
            "definition": (
                "Derived deterministically from the Search package price and the Product "
                "Pack's parsed package quantity. It is unavailable when package evidence "
                "is missing or ambiguous."
            ),
        }

    @staticmethod
    def _availability_summary(rows: list[JsonObject]) -> JsonObject:
        # A positive Search price is the governed in-stock signal for this module.
        # Rows reach this projection only after the positive-price admission rule.
        return {
            "status": "observed" if rows else "unavailable",
            "known_observations": len(rows),
            "in_stock_observations": len(rows),
            "rate": 1.0 if rows else None,
            "definition": (
                "A product observed in Search with a price greater than zero is treated "
                "as available/in stock at that location."
            ),
        }

    @staticmethod
    def _promotion_summary(rows: list[JsonObject]) -> JsonObject:
        known = [
            row
            for row in rows
            if row.get("regular_price") is not None or row.get("discounted_price") is not None
        ]
        promoted = [
            row
            for row in known
            if (
                row.get("regular_price") is not None
                and float(row["regular_price"]) > float(row["price"])
            )
            or row.get("discounted_price") is not None
        ]
        return {
            "status": "observed" if known else "unavailable",
            "known_observations": len(known),
            "promotion_observations": len(promoted),
            "rate": _round(len(promoted) / len(known)) if known else None,
            "definition": (
                "Promotion requires an explicit regular or discounted price from Search; "
                "price variation alone is not called a promotion."
            ),
        }

    @staticmethod
    def _sponsorship_summary(rows: list[JsonObject]) -> JsonObject:
        known = [bool(row["is_sponsored"]) for row in rows if row.get("is_sponsored") is not None]
        sponsored = sum(known)
        return {
            "status": "observed" if known else "unavailable",
            "known_observations": len(known),
            "sponsorship_observations": sponsored,
            "rate": _round(sponsored / len(known)) if known else None,
            "definition": (
                "Sponsorship uses the Search result is_sponsored boolean. Missing values "
                "remain unavailable and are not inferred from rank or title."
            ),
        }

    def _price_exceptions(self, rows: list[JsonObject]) -> list[JsonObject]:
        if len(rows) < 4:
            return []
        prices = [float(row["price"]) for row in rows]
        q1 = _quantile(prices, 0.25)
        q3 = _quantile(prices, 0.75)
        if q1 is None or q3 is None:
            return []
        if q3 > q1:
            iqr = q3 - q1
            lower = max(0.0, q1 - 1.5 * iqr)
            upper = q3 + 1.5 * iqr
            rule_description = "the 1.5x IQR range"
        else:
            modal = Counter(prices).most_common(1)[0][0]
            tolerance = float(self._parity_tolerance)
            lower = max(0.0, modal - tolerance)
            upper = modal + tolerance
            rule_description = "the Product Pack tolerance around the modal price"
        center = float(median(prices))
        exceptions: list[JsonObject] = []
        for row in rows:
            price = float(row["price"])
            if lower <= price <= upper:
                continue
            location: PriceLocation = row["location"]
            exceptions.append(
                {
                    "id": f"price-outlier:{row['product_id']}:{location.scope_key}",
                    "type": "price_outlier",
                    "severity": "high" if abs(price - center) / center >= 0.1 else "review",
                    "scope_key": location.scope_key,
                    "store_number": location.store_number,
                    "store_name": location.store_name,
                    "zipcode": location.zipcode,
                    "city": location.city,
                    "state": location.state,
                    "price": _round(price),
                    "reference_price": _round(center),
                    "difference": _round(price - center),
                    "observed_at": row["observed_at"],
                    "reason": (
                        f"Observed price falls outside {rule_description} for this exact "
                        "retailer product across visible locations."
                    ),
                }
            )
        exceptions.sort(key=lambda row: (-abs(float(row["difference"])), str(row["scope_key"])))
        return exceptions[:200]

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
        sponsorship = [
            bool(row["is_sponsored"]) for row in rows if row.get("is_sponsored") is not None
        ]
        sponsorship_status = (
            "unknown"
            if not sponsorship
            else "sponsored"
            if all(sponsorship)
            else "organic"
            if not any(sponsorship)
            else "mixed"
        )
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
            "sponsorship_status": sponsorship_status,
        }

    @staticmethod
    def _geography_summary(
        level: Literal["state", "city", "zipcode"],
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
            "zipcode": key if level == "zipcode" else None,
            "locations": len({row["location"].scope_key for row in rows}),
            "products": len({row["product_id"] for row in rows}),
            "observations": len(rows),
            "latitude": _round(median(latitudes), 6) if latitudes else None,
            "longitude": _round(median(longitudes), 6) if longitudes else None,
            "price_stats": _price_stats(prices),
        }

    @staticmethod
    def _gap_location(location: PriceLocation) -> JsonObject:
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
        }

    @staticmethod
    def _gap_geography_summary(
        level: Literal["state", "city", "zipcode"],
        key: str,
        eligible: list[PriceLocation],
        not_observed: list[PriceLocation],
        *,
        state: str | None,
        city: str | None,
    ) -> JsonObject:
        eligible_count = len(eligible)
        not_observed_count = len(not_observed)
        observed_count = max(0, eligible_count - not_observed_count)
        return {
            "level": level,
            "key": key,
            "label": key,
            "state": key if level == "state" else state,
            "city": key if level == "city" else city,
            "zipcode": key if level == "zipcode" else None,
            "eligible_locations": eligible_count,
            "observed_locations": observed_count,
            "not_observed_locations": not_observed_count,
            "observed_rate": _round(observed_count / eligible_count) if eligible_count else None,
        }
