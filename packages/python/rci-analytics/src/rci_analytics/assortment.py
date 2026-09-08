"""Category-neutral assortment coverage and relationship diagnostics."""

from __future__ import annotations

import copy
import json
import statistics
from collections import defaultdict
from collections.abc import Iterable
from typing import TypedDict

from rci_analytics.latest_product_location import (
    LatestProductLocationSelector,
    add_classified_offer,
    is_product_location_state,
    is_seller_policy_exclusion,
    product_location_key,
)
from rci_analytics.models import ClassifiedOffer, JsonObject, MatchRecord
from rci_analytics.product_location import store_search_distribution_contract


def _brand_type(item: ClassifiedOffer) -> str:
    governance = item.attributes.get("_brand_governance")
    if isinstance(governance, dict):
        value = str(governance.get("role") or governance.get("brand_type") or "")
        if value in {"private_label", "regional", "national"}:
            return value
    return "unclassified"


class _BrandWorking(TypedDict):
    brand: str
    product_ids: set[str]
    locations: set[str]
    service_areas: set[str]
    zipcodes: set[str]


class _BrandSummary(TypedDict):
    brand: str
    distinct_products: int
    observed_locations: int
    observed_zipcodes: int
    distribution_store_count: int
    service_area_presence_count: int
    location_share: float


class _BreadthGap(TypedDict):
    zipcode: str
    benchmark_products: int
    competitor_products: int
    product_count_gap: int


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


_PRODUCT_INTERNAL_FIELDS = {
    "locations",
    "zipcodes",
    "search_locations",
    "search_zipcodes",
    "service_areas",
    "attribute_variants",
}


class AssortmentAccumulator:
    """Accumulate positive-price Search assortment and distribution breadth."""

    def __init__(self) -> None:
        self._products: dict[str, dict[str, JsonObject]] = defaultdict(dict)
        self._locations: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        self._zips: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        self._service_areas: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        self._latest_search_rows: LatestProductLocationSelector[ClassifiedOffer] = (
            LatestProductLocationSelector()
        )

    def add(self, item: ClassifiedOffer) -> None:
        if not is_product_location_state(item):
            return
        offer = item.offer
        if is_seller_policy_exclusion(item):
            add_classified_offer(self._latest_search_rows, item)
            return
        product = self._products[offer.retailer_id].setdefault(
            offer.retailer_product_id,
            {
                "product_id": offer.retailer_product_id,
                "canonical_product_id": f"{offer.retailer_id}:{offer.retailer_product_id}",
                "name": offer.title,
                "brand": item.attributes.get("brand") or offer.brand,
                "brand_type": _brand_type(item),
                "image_url": offer.image_url,
                "url": offer.product_url,
                "locations": set(),
                "zipcodes": set(),
                "search_locations": set(),
                "search_zipcodes": set(),
                "service_areas": set(),
                "attribute_variants": {},
            },
        )
        visible_attributes = {
            str(name): value
            for name, value in item.attributes.items()
            if not str(name).startswith("_")
        }
        if visible_attributes:
            signature = json.dumps(visible_attributes, sort_keys=True, default=str)
            product["attribute_variants"][signature] = visible_attributes
        if not product.get("image_url") and offer.image_url:
            product["image_url"] = offer.image_url
        observed_brand = item.attributes.get("brand") or offer.brand
        if not product.get("brand") and observed_brand:
            product["brand"] = observed_brand
        if product.get("brand_type") == "unclassified":
            product["brand_type"] = _brand_type(item)
        identity = product_location_key(
            retailer_id=offer.retailer_id,
            product_id=offer.retailer_product_id,
            store_number=offer.store_number,
            zipcode=offer.zipcode,
        )
        if identity is None:
            return
        add_classified_offer(self._latest_search_rows, item)

    def _rebuild_distribution(self) -> None:
        self._locations.clear()
        self._zips.clear()
        self._service_areas.clear()
        for retailer_products in self._products.values():
            for product in retailer_products.values():
                for field in (
                    "locations",
                    "zipcodes",
                    "search_locations",
                    "search_zipcodes",
                    "service_areas",
                ):
                    product[field].clear()
        for item in self._latest_search_rows.values():
            offer = item.offer
            selected_product = self._products.get(offer.retailer_id, {}).get(
                offer.retailer_product_id
            )
            if (
                selected_product is None
                or is_seller_policy_exclusion(item)
                or offer.price is None
                or offer.price <= 0
            ):
                continue
            distribution_store_id = str(offer.store_number or "").strip()
            if distribution_store_id:
                location = distribution_store_id
                selected_product["locations"].add(location)
                selected_product["search_locations"].add(f"store:{location}")
                self._locations[offer.retailer_id][location].add(offer.retailer_product_id)
            else:
                service_area = str(offer.zipcode or "").strip()
                if not service_area:
                    continue
                selected_product["service_areas"].add(service_area)
                selected_product["search_locations"].add(f"service_area:{service_area}")
                self._service_areas[offer.retailer_id][service_area].add(offer.retailer_product_id)
            if offer.zipcode is not None:
                selected_product["zipcodes"].add(offer.zipcode)
                selected_product["search_zipcodes"].add(offer.zipcode)
                self._zips[offer.retailer_id][offer.zipcode].add(offer.retailer_product_id)

    def finalize(
        self,
        *,
        benchmark_retailer: str,
        competitors: Iterable[str],
        matches: Iterable[MatchRecord],
        profiles: Iterable[JsonObject],
        ambiguous_groups: Iterable[JsonObject] = (),
        relationships: Iterable[JsonObject] = (),
    ) -> JsonObject:
        self._rebuild_distribution()
        profile_labels = {
            str(profile["id"]): str(profile.get("label") or profile["id"]) for profile in profiles
        }
        match_rows = list(matches)
        ambiguous_rows = list(ambiguous_groups)
        relationship_rows = list(relationships)
        retailers = [benchmark_retailer, *[str(value) for value in competitors]]
        return {
            "source": "Positive-priced Search results admitted by Product Pack category rules",
            "grain": (
                "Retailer product x distinct store ID for distribution; service-area Search "
                "presence is reported separately"
            ),
            "distribution_contract": store_search_distribution_contract(),
            "benchmark_retailer": benchmark_retailer,
            "retailers": [self._retailer_summary(retailer) for retailer in retailers],
            "comparisons": [
                self._comparison(
                    benchmark_retailer,
                    competitor,
                    match_rows,
                    profile_labels,
                    ambiguous_rows,
                    relationship_rows,
                )
                for competitor in retailers
                if competitor != benchmark_retailer
            ],
        }

    def _retailer_summary(self, retailer: str) -> JsonObject:
        products = self._products.get(retailer, {})
        observed_products = {
            product_id: product
            for product_id, product in products.items()
            if product["locations"] or product["service_areas"]
        }
        counts = [
            len(values)
            for values in (
                *self._locations.get(retailer, {}).values(),
                *self._service_areas.get(retailer, {}).values(),
            )
        ]
        brands: dict[str, _BrandWorking] = {}
        unbranded_products = 0
        for product in observed_products.values():
            brand = str(product.get("brand") or "").strip()
            if not brand:
                unbranded_products += 1
                continue
            key = brand.casefold()
            row = brands.setdefault(
                key,
                {
                    "brand": brand,
                    "product_ids": set(),
                    "locations": set(),
                    "service_areas": set(),
                    "zipcodes": set(),
                },
            )
            row["product_ids"].add(str(product["product_id"]))
            row["locations"].update(product["locations"])
            row["service_areas"].update(product["service_areas"])
            row["zipcodes"].update(product["zipcodes"])
        retailer_location_count = len(self._locations.get(retailer, {})) + len(
            self._service_areas.get(retailer, {})
        )
        brand_rows: list[_BrandSummary] = [
            {
                "brand": str(row["brand"]),
                "distinct_products": len(row["product_ids"]),
                "observed_locations": len(row["locations"]) + len(row["service_areas"]),
                "observed_zipcodes": len(row["zipcodes"]),
                "distribution_store_count": len(row["locations"]),
                "service_area_presence_count": len(row["service_areas"]),
                "location_share": _rate(
                    len(row["locations"]) + len(row["service_areas"]),
                    retailer_location_count,
                ),
            }
            for row in brands.values()
        ]
        brand_rows.sort(
            key=lambda row: (
                -int(row["observed_locations"]),
                -int(row["distinct_products"]),
                str(row["brand"]).casefold(),
            )
        )
        concentrated_brands = sorted(
            (
                row
                for row in brand_rows
                if int(row["observed_locations"]) >= 2 and float(row["location_share"]) <= 0.25
            ),
            key=lambda row: (
                -int(row["distinct_products"]),
                -int(row["observed_locations"]),
                str(row["brand"]).casefold(),
            ),
        )
        return {
            "retailer": retailer,
            "distinct_products": len(observed_products),
            "search_distinct_products": len(observed_products),
            "observed_locations": retailer_location_count,
            "observed_zipcodes": len(self._zips.get(retailer, {})),
            "distribution_store_count": len(self._locations.get(retailer, {})),
            "service_area_presence_count": len(self._service_areas.get(retailer, {})),
            "median_products_per_location": (
                round(float(statistics.median(counts)), 1) if counts else 0.0
            ),
            "distinct_brands": len(brand_rows),
            "unbranded_products": unbranded_products,
            "brands": brand_rows,
            "top_brands": brand_rows[:12],
            "geographically_concentrated_brands": concentrated_brands[:12],
            "products": [
                {
                    **{
                        key: value
                        for key, value in product.items()
                        if key not in _PRODUCT_INTERNAL_FIELDS
                    },
                    "observed_locations": len(product["locations"]),
                    "observed_zipcodes": len(product["zipcodes"]),
                    "distribution_store_count": len(product["locations"]),
                    "service_area_presence_count": len(product["service_areas"]),
                    "location_scope_keys": sorted(
                        [f"{retailer}|store|{location}" for location in product["locations"]]
                        + [
                            f"{retailer}|service_area|{location}"
                            for location in product["service_areas"]
                        ]
                    ),
                    "attributes": next(iter(product["attribute_variants"].values()), {}),
                    "attribute_variants": sorted(
                        product["attribute_variants"].values(),
                        key=lambda value: json.dumps(value, sort_keys=True, default=str),
                    ),
                    "attribute_conflict": len(product["attribute_variants"]) > 1,
                }
                for product in sorted(
                    observed_products.values(),
                    key=lambda value: (
                        str(value["name"]).casefold(),
                        str(value["product_id"]),
                    ),
                )
            ],
        }

    def _comparison(
        self,
        benchmark: str,
        competitor: str,
        matches: list[MatchRecord],
        profile_labels: dict[str, str],
        ambiguous_groups: list[JsonObject],
        relationships: list[JsonObject],
    ) -> JsonObject:
        benchmark_products = {
            product_id: product
            for product_id, product in self._products.get(benchmark, {}).items()
            if product["locations"] or product["service_areas"]
        }
        competitor_products = {
            product_id: product
            for product_id, product in self._products.get(competitor, {}).items()
            if product["locations"] or product["service_areas"]
        }
        observed_benchmark_ids = set(benchmark_products)
        observed_competitor_ids = set(competitor_products)
        latest_offers = {item.offer.offer_id: item for item in self._latest_search_rows.values()}
        pair_profiles: dict[tuple[str, str], set[str]] = defaultdict(set)
        for match in matches:
            if match.competitor_id != competitor:
                continue
            benchmark_offer = latest_offers.get(match.benchmark_offer_id)
            competitor_offer = latest_offers.get(match.competitor_offer_id)
            if benchmark_offer is None or competitor_offer is None:
                continue
            benchmark_product_id = benchmark_offer.offer.retailer_product_id
            competitor_product_id = competitor_offer.offer.retailer_product_id
            if (
                benchmark_offer.offer.retailer_id != benchmark
                or competitor_offer.offer.retailer_id != competitor
                or benchmark_product_id not in observed_benchmark_ids
                or competitor_product_id not in observed_competitor_ids
            ):
                continue
            pair_profiles[(benchmark_product_id, competitor_product_id)].add(match.profile_id)
        for relationship in relationships:
            if str(relationship.get("competitor_id")) != competitor or str(
                relationship.get("status")
            ) not in {"confirmed", "suggested"}:
                continue
            benchmark_product_id = str(relationship.get("benchmark_product_id") or "")
            competitor_product_id = str(relationship.get("competitor_product_id") or "")
            if (
                not benchmark_product_id
                or not competitor_product_id
                or benchmark_product_id not in observed_benchmark_ids
                or competitor_product_id not in observed_competitor_ids
            ):
                continue
            eligible_profiles = relationship.get("eligible_profile_ids")
            profile_ids = (
                [str(value) for value in eligible_profiles]
                if isinstance(eligible_profiles, list)
                else []
            )
            pair_profiles[(benchmark_product_id, competitor_product_id)].update(profile_ids)
        matched_benchmark = {pair[0] for pair in pair_profiles}
        matched_competitor = {pair[1] for pair in pair_profiles}
        matched_observed_benchmark = matched_benchmark & set(benchmark_products)
        matched_observed_competitor = matched_competitor & set(competitor_products)
        observed_ambiguous_candidates: list[JsonObject] = []
        observed_ambiguous_group_count = 0
        for group in ambiguous_groups:
            if str(group.get("competitor_id")) != competitor:
                continue
            group_has_observed_pair = False
            for candidate in group.get("candidates", []):
                if not isinstance(candidate, dict):
                    continue
                benchmark_product_id = str(candidate.get("benchmark_product_id") or "")
                competitor_product_id = str(candidate.get("competitor_product_id") or "")
                if (
                    benchmark_product_id in observed_benchmark_ids
                    and competitor_product_id in observed_competitor_ids
                ):
                    observed_ambiguous_candidates.append(candidate)
                    group_has_observed_pair = True
            observed_ambiguous_group_count += group_has_observed_pair
        ambiguous_benchmark = {
            str(candidate.get("benchmark_product_id"))
            for candidate in observed_ambiguous_candidates
            if candidate.get("benchmark_product_id")
        }
        ambiguous_competitor = {
            str(candidate.get("competitor_product_id"))
            for candidate in observed_ambiguous_candidates
            if candidate.get("competitor_product_id")
        }
        benchmark_only = set(benchmark_products) - matched_benchmark - ambiguous_benchmark
        competitor_only = set(competitor_products) - matched_competitor - ambiguous_competitor
        benchmark_zips = self._zips.get(benchmark, {})
        competitor_zips = self._zips.get(competitor, {})
        shared_zips = set(benchmark_zips) & set(competitor_zips)
        benchmark_broader = sum(
            len(benchmark_zips[zipcode]) > len(competitor_zips[zipcode]) for zipcode in shared_zips
        )
        competitor_broader = sum(
            len(competitor_zips[zipcode]) > len(benchmark_zips[zipcode]) for zipcode in shared_zips
        )
        parity = len(shared_zips) - benchmark_broader - competitor_broader
        breadth_gaps = [
            len(benchmark_zips[zipcode]) - len(competitor_zips[zipcode]) for zipcode in shared_zips
        ]
        breadth_rows: list[_BreadthGap] = [
            {
                "zipcode": zipcode,
                "benchmark_products": len(benchmark_zips[zipcode]),
                "competitor_products": len(competitor_zips[zipcode]),
                "product_count_gap": len(benchmark_zips[zipcode]) - len(competitor_zips[zipcode]),
            }
            for zipcode in shared_zips
        ]
        benchmark_gap_rows = sorted(
            (row for row in breadth_rows if int(row["product_count_gap"]) > 0),
            key=lambda row: (-int(row["product_count_gap"]), str(row["zipcode"])),
        )[:12]
        competitor_gap_rows = sorted(
            (row for row in breadth_rows if int(row["product_count_gap"]) < 0),
            key=lambda row: (int(row["product_count_gap"]), str(row["zipcode"])),
        )[:12]
        profiles = [
            {
                "profile_id": profile_id,
                "profile_label": profile_labels.get(profile_id, profile_id),
                "relationships": sum(profile_id in values for values in pair_profiles.values()),
            }
            for profile_id in profile_labels
        ]
        return {
            "competitor": competitor,
            "product_relationships": len(pair_profiles),
            "ambiguous_candidate_groups": observed_ambiguous_group_count,
            "matched_benchmark_products": len(matched_observed_benchmark),
            "matched_competitor_products": len(matched_observed_competitor),
            "benchmark_match_coverage": _rate(
                len(matched_observed_benchmark), len(benchmark_products)
            ),
            "competitor_match_coverage": _rate(
                len(matched_observed_competitor), len(competitor_products)
            ),
            "ambiguous_benchmark_products": len(ambiguous_benchmark - matched_benchmark),
            "ambiguous_competitor_products": len(ambiguous_competitor - matched_competitor),
            "benchmark_only_products": len(benchmark_only),
            "competitor_whitespace_products": len(competitor_only),
            "profiles": profiles,
            "geography": {
                "shared_zipcodes": len(shared_zips),
                "benchmark_only_zipcodes": len(set(benchmark_zips) - set(competitor_zips)),
                "competitor_only_zipcodes": len(set(competitor_zips) - set(benchmark_zips)),
                "benchmark_broader_zipcodes": benchmark_broader,
                "competitor_broader_zipcodes": competitor_broader,
                "parity_zipcodes": parity,
                "median_product_count_gap": (
                    round(float(statistics.median(breadth_gaps)), 1) if breadth_gaps else 0.0
                ),
                "top_benchmark_breadth_gaps": benchmark_gap_rows,
                "top_competitor_breadth_gaps": competitor_gap_rows,
            },
            "top_benchmark_only": self._rank_products(benchmark, benchmark_only),
            "top_competitor_whitespace": self._rank_products(competitor, competitor_only),
            "top_ambiguous_benchmark": self._rank_products(
                benchmark, ambiguous_benchmark - matched_benchmark
            ),
            "top_ambiguous_competitor": self._rank_products(
                competitor, ambiguous_competitor - matched_competitor
            ),
            "key_points": [
                (
                    f"{len(pair_profiles):,} distinct Product Pack pairings cover "
                    f"{_rate(len(matched_observed_benchmark), len(benchmark_products)):.0%} "
                    "of the primary retailer's Search-observed products."
                ),
                (
                    f"{len(competitor_only):,} competitor products have no admitted primary "
                    "counterpart; treat these as assortment whitespace to review, not "
                    "automatic substitutes."
                ),
                (
                    f"Across {len(shared_zips):,} shared ZIPs, the primary retailer has "
                    f"broader Search-observed variety in {benchmark_broader:,} and the "
                    f"competitor in {competitor_broader:,}."
                ),
            ],
        }

    def _rank_products(self, retailer: str, product_ids: set[str]) -> list[JsonObject]:
        rows = []
        for product_id in product_ids:
            product = self._products[retailer][product_id]
            rows.append(
                {
                    **{
                        key: value
                        for key, value in product.items()
                        if key not in _PRODUCT_INTERNAL_FIELDS
                    },
                    "observed_locations": len(product["locations"]),
                    "observed_zipcodes": len(product["zipcodes"]),
                    "distribution_store_count": len(product["locations"]),
                    "service_area_presence_count": len(product["service_areas"]),
                }
            )
        return sorted(
            rows,
            key=lambda row: (-int(row["observed_locations"]), str(row["name"]).lower()),
        )[:12]


def merge_assortment_product_context(
    assortment: JsonObject,
    highlights: Iterable[JsonObject],
) -> JsonObject:
    """Overlay PDP identity without replacing Search distribution metrics."""

    enriched = copy.deepcopy(assortment)
    context = {
        str(row.get("canonical_product_id")): row
        for row in highlights
        if row.get("canonical_product_id")
    }

    def enrich_product(product: JsonObject) -> None:
        # Preserve the exact Search-derived brand used to calculate the brand
        # scorecard before PDP is allowed to improve the display identity.
        # Attribute variants may conflict and cannot reconstruct membership.
        product.setdefault("observed_brand", product.get("brand"))
        pdp = context.get(str(product.get("canonical_product_id")))
        if not pdp:
            return
        # These fields describe the retailer product and can safely improve the
        # review surface. Search remains the sole source for price and observed
        # store distribution; PDP content cannot create a store observation.
        for key in (
            "name",
            "brand",
            "seller",
            "image_url",
            "url",
            "description",
            "category_path",
            "identifiers",
            "specification",
            "physical_properties",
            "variant_configuration",
            "item_condition",
            "fulfillment",
            "reviews",
            "demand",
            "content",
            "relationships",
            "media",
            "pdp_source_field_inventory",
            "pdp_unmapped_source_fields",
            "role",
        ):
            if pdp.get(key) not in (None, "", {}, []):
                product[key] = copy.deepcopy(pdp[key])
        if pdp.get("price") is not None:
            product["pdp_reference_price"] = pdp["price"]
        if pdp.get("price_currency"):
            product["pdp_reference_currency"] = pdp["price_currency"]

    for comparison in enriched.get("comparisons", []):
        for field in ("top_benchmark_only", "top_competitor_whitespace"):
            for product in comparison.get(field, []):
                enrich_product(product)
    for retailer in enriched.get("retailers", []):
        for product in retailer.get("products", []):
            enrich_product(product)
    return enriched
