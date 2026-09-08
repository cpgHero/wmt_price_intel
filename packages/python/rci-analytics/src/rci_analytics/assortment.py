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
from rci_analytics.product_location import classify_local_availability


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
    zipcodes: set[str]


class _BrandSummary(TypedDict):
    brand: str
    distinct_products: int
    observed_locations: int
    observed_zipcodes: int
    verified_available_products: int
    verified_available_locations: int
    verified_available_zipcodes: int
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
    "explicitly_out_of_stock_locations",
    "unverified_locations",
    "unverified_sponsored_locations",
    "attribute_variants",
}


class AssortmentAccumulator:
    """Separate Search discovery from verified local assortment breadth."""

    def __init__(self) -> None:
        self._products: dict[str, dict[str, JsonObject]] = defaultdict(dict)
        self._locations: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        self._zips: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        self._search_locations: dict[str, dict[str, set[str]]] = defaultdict(
            lambda: defaultdict(set)
        )
        self._search_zips: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        self._latest_location_availability: LatestProductLocationSelector[ClassifiedOffer] = (
            LatestProductLocationSelector()
        )

    def add(self, item: ClassifiedOffer) -> None:
        if not is_product_location_state(item):
            return
        offer = item.offer
        if is_seller_policy_exclusion(item):
            add_classified_offer(self._latest_location_availability, item)
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
                "explicitly_out_of_stock_locations": set(),
                "unverified_locations": set(),
                "unverified_sponsored_locations": set(),
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
        zipcode = offer.zipcode
        location = (
            f"{zipcode or 'unknown-zip'}|{offer.store_number}"
            if offer.store_number
            else str(zipcode)
        )
        product["search_locations"].add(location)
        self._search_locations[offer.retailer_id][location].add(offer.retailer_product_id)
        if zipcode is not None:
            product["search_zipcodes"].add(zipcode)
            self._search_zips[offer.retailer_id][zipcode].add(offer.retailer_product_id)
        add_classified_offer(self._latest_location_availability, item)

    def _rebuild_local_availability(self) -> None:
        self._locations.clear()
        self._zips.clear()
        for retailer_products in self._products.values():
            for product in retailer_products.values():
                for field in (
                    "locations",
                    "zipcodes",
                    "explicitly_out_of_stock_locations",
                    "unverified_locations",
                    "unverified_sponsored_locations",
                ):
                    product[field].clear()
        for item in self._latest_location_availability.values():
            offer = item.offer
            selected_product = self._products.get(offer.retailer_id, {}).get(
                offer.retailer_product_id
            )
            if selected_product is None:
                continue
            location = (
                f"{offer.zipcode or 'unknown-zip'}|{offer.store_number}"
                if offer.store_number
                else str(offer.zipcode)
            )
            status = classify_local_availability(
                in_stock=offer.in_stock,
                is_sponsored=offer.is_sponsored,
            )
            if item.in_scope and status == "verified_in_stock":
                selected_product["locations"].add(location)
                self._locations[offer.retailer_id][location].add(offer.retailer_product_id)
                if offer.zipcode is not None:
                    selected_product["zipcodes"].add(offer.zipcode)
                    self._zips[offer.retailer_id][offer.zipcode].add(offer.retailer_product_id)
            elif status == "explicitly_out_of_stock":
                selected_product["explicitly_out_of_stock_locations"].add(location)
            elif status == "unverified_sponsored":
                selected_product["unverified_sponsored_locations"].add(location)
            else:
                selected_product["unverified_locations"].add(location)

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
        self._rebuild_local_availability()
        profile_labels = {
            str(profile["id"]): str(profile.get("label") or profile["id"]) for profile in profiles
        }
        match_rows = list(matches)
        ambiguous_rows = list(ambiguous_groups)
        relationship_rows = list(relationships)
        retailers = [benchmark_retailer, *[str(value) for value in competitors]]
        return {
            "source": (
                "Search results admitted by Product Pack category rules; local assortment "
                "requires the latest explicit in-stock and non-sponsored location state"
            ),
            "grain": (
                "Distinct retailer product IDs; verified store breadth uses ZIP + store ID "
                "when available; Search reach is reported separately"
            ),
            "availability_definition": (
                "Verified local availability requires in_stock=true and is_sponsored=false. "
                "Sponsored, explicitly out-of-stock, or unknown evidence remains Search-only."
            ),
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
        verified_products = {
            product_id: product for product_id, product in products.items() if product["locations"]
        }
        counts = [len(values) for values in self._locations.get(retailer, {}).values()]
        brands: dict[str, _BrandWorking] = {}
        unbranded_products = 0
        for product in verified_products.values():
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
                    "zipcodes": set(),
                },
            )
            row["product_ids"].add(str(product["product_id"]))
            row["locations"].update(product["locations"])
            row["zipcodes"].update(product["zipcodes"])
        retailer_location_count = len(self._locations.get(retailer, {}))
        brand_rows: list[_BrandSummary] = [
            {
                "brand": str(row["brand"]),
                "distinct_products": len(row["product_ids"]),
                "observed_locations": len(row["locations"]),
                "observed_zipcodes": len(row["zipcodes"]),
                "verified_available_products": len(row["product_ids"]),
                "verified_available_locations": len(row["locations"]),
                "verified_available_zipcodes": len(row["zipcodes"]),
                "location_share": _rate(len(row["locations"]), retailer_location_count),
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
            "distinct_products": len(verified_products),
            "verified_available_products": len(verified_products),
            "search_distinct_products": len(products),
            "observed_locations": len(self._locations.get(retailer, {})),
            "observed_zipcodes": len(self._zips.get(retailer, {})),
            "verified_available_locations": len(self._locations.get(retailer, {})),
            "verified_available_zipcodes": len(self._zips.get(retailer, {})),
            "search_observed_locations": len(self._search_locations.get(retailer, {})),
            "search_observed_zipcodes": len(self._search_zips.get(retailer, {})),
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
                    "verified_available_locations": len(product["locations"]),
                    "verified_available_zipcodes": len(product["zipcodes"]),
                    "search_observed_locations": len(product["search_locations"]),
                    "search_observed_zipcodes": len(product["search_zipcodes"]),
                    "location_scope_keys": sorted(
                        f"{retailer}|{location}" for location in product["locations"]
                    ),
                    "verified_location_scope_keys": sorted(
                        f"{retailer}|{location}" for location in product["locations"]
                    ),
                    "search_location_scope_keys": sorted(
                        f"{retailer}|{location}" for location in product["search_locations"]
                    ),
                    "availability_status": self._product_availability_status(product),
                    "explicitly_out_of_stock_locations": len(
                        product["explicitly_out_of_stock_locations"]
                    ),
                    "unverified_locations": len(product["unverified_locations"]),
                    "unverified_sponsored_locations": len(
                        product["unverified_sponsored_locations"]
                    ),
                    "attributes": next(iter(product["attribute_variants"].values()), {}),
                    "attribute_variants": sorted(
                        product["attribute_variants"].values(),
                        key=lambda value: json.dumps(value, sort_keys=True, default=str),
                    ),
                    "attribute_conflict": len(product["attribute_variants"]) > 1,
                }
                for product in sorted(
                    products.values(),
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
            if product["locations"]
        }
        competitor_products = {
            product_id: product
            for product_id, product in self._products.get(competitor, {}).items()
            if product["locations"]
        }
        verified_benchmark_ids = set(benchmark_products)
        verified_competitor_ids = set(competitor_products)
        latest_offers = {
            item.offer.offer_id: item for item in self._latest_location_availability.values()
        }
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
                or benchmark_product_id not in verified_benchmark_ids
                or competitor_product_id not in verified_competitor_ids
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
                or benchmark_product_id not in verified_benchmark_ids
                or competitor_product_id not in verified_competitor_ids
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
        verified_ambiguous_candidates: list[JsonObject] = []
        verified_ambiguous_group_count = 0
        for group in ambiguous_groups:
            if str(group.get("competitor_id")) != competitor:
                continue
            group_has_verified_pair = False
            for candidate in group.get("candidates", []):
                if not isinstance(candidate, dict):
                    continue
                benchmark_product_id = str(candidate.get("benchmark_product_id") or "")
                competitor_product_id = str(candidate.get("competitor_product_id") or "")
                if (
                    benchmark_product_id in verified_benchmark_ids
                    and competitor_product_id in verified_competitor_ids
                ):
                    verified_ambiguous_candidates.append(candidate)
                    group_has_verified_pair = True
            verified_ambiguous_group_count += group_has_verified_pair
        ambiguous_benchmark = {
            str(candidate.get("benchmark_product_id"))
            for candidate in verified_ambiguous_candidates
            if candidate.get("benchmark_product_id")
        }
        ambiguous_competitor = {
            str(candidate.get("competitor_product_id"))
            for candidate in verified_ambiguous_candidates
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
            "ambiguous_candidate_groups": verified_ambiguous_group_count,
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
                    "of the primary retailer's verified-available products."
                ),
                (
                    f"{len(competitor_only):,} competitor products have no admitted primary "
                    "counterpart; treat these as assortment whitespace to review, not "
                    "automatic substitutes."
                ),
                (
                    f"Across {len(shared_zips):,} shared ZIPs, the primary retailer has "
                    f"broader verified-available variety in {benchmark_broader:,} and the "
                    f"competitor in {competitor_broader:,}."
                ),
            ],
        }

    @staticmethod
    def _product_availability_status(product: JsonObject) -> str:
        if product["locations"]:
            return "verified_in_stock"
        if product["unverified_sponsored_locations"]:
            return "unverified_sponsored"
        if product["unverified_locations"]:
            return "unverified"
        if product["explicitly_out_of_stock_locations"]:
            return "explicitly_out_of_stock"
        return "unverified"

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
                    "verified_available_locations": len(product["locations"]),
                    "verified_available_zipcodes": len(product["zipcodes"]),
                    "search_observed_locations": len(product["search_locations"]),
                    "search_observed_zipcodes": len(product["search_zipcodes"]),
                    "availability_status": self._product_availability_status(product),
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
    """Overlay PDP identity without replacing verified/Search evidence metrics."""

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
        # review surface. Search remains the price-placement source; only explicit
        # non-sponsored in-stock evidence establishes verified local availability.
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
