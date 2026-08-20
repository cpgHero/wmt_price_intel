"""Category-neutral assortment coverage and relationship diagnostics."""

from __future__ import annotations

import copy
import json
import statistics
from collections import defaultdict
from collections.abc import Iterable
from typing import TypedDict

from rci_analytics.models import ClassifiedOffer, JsonObject, MatchRecord


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
    location_share: float


class _BreadthGap(TypedDict):
    zipcode: str
    benchmark_products: int
    competitor_products: int
    product_count_gap: int


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


class AssortmentAccumulator:
    """Accumulate distinct in-scope products and store/ZIP breadth from Search."""

    def __init__(self) -> None:
        self._offers: dict[str, ClassifiedOffer] = {}
        self._products: dict[str, dict[str, JsonObject]] = defaultdict(dict)
        self._locations: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        self._zips: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))

    def add(self, item: ClassifiedOffer) -> None:
        if not item.in_scope:
            return
        offer = item.offer
        self._offers[offer.offer_id] = item
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
                "attribute_variants": {},
            },
        )
        visible_attributes = {
            str(name): value
            for name, value in item.attributes.items()
            if not str(name).startswith("_")
        }
        signature = json.dumps(visible_attributes, sort_keys=True, default=str)
        product["attribute_variants"][signature] = visible_attributes
        if not product.get("image_url") and offer.image_url:
            product["image_url"] = offer.image_url
        if product.get("brand_type") == "unclassified":
            product["brand_type"] = _brand_type(item)
        zipcode = offer.zipcode or "unknown-zip"
        location = f"{zipcode}|{offer.store_number}" if offer.store_number else zipcode
        product["locations"].add(location)
        product["zipcodes"].add(zipcode)
        self._locations[offer.retailer_id][location].add(offer.retailer_product_id)
        self._zips[offer.retailer_id][zipcode].add(offer.retailer_product_id)

    def finalize(
        self,
        *,
        benchmark_retailer: str,
        competitors: Iterable[str],
        matches: Iterable[MatchRecord],
        profiles: Iterable[JsonObject],
        ambiguous_groups: Iterable[JsonObject] = (),
    ) -> JsonObject:
        profile_labels = {
            str(profile["id"]): str(profile.get("label") or profile["id"]) for profile in profiles
        }
        match_rows = list(matches)
        ambiguous_rows = list(ambiguous_groups)
        retailers = [benchmark_retailer, *[str(value) for value in competitors]]
        return {
            "source": "Search results classified in scope by the Product Pack",
            "grain": (
                "Distinct retailer product IDs; store breadth uses ZIP + store ID when available"
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
                )
                for competitor in retailers
                if competitor != benchmark_retailer
            ],
        }

    def _retailer_summary(self, retailer: str) -> JsonObject:
        products = self._products.get(retailer, {})
        counts = [len(values) for values in self._locations.get(retailer, {}).values()]
        brands: dict[str, _BrandWorking] = {}
        unbranded_products = 0
        for product in products.values():
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
            "distinct_products": len(products),
            "observed_locations": len(self._locations.get(retailer, {})),
            "observed_zipcodes": len(self._zips.get(retailer, {})),
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
                        if key not in {"locations", "zipcodes", "attribute_variants"}
                    },
                    "observed_locations": len(product["locations"]),
                    "observed_zipcodes": len(product["zipcodes"]),
                    "location_scope_keys": sorted(
                        f"{retailer}|{location}" for location in product["locations"]
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
    ) -> JsonObject:
        benchmark_products = self._products.get(benchmark, {})
        competitor_products = self._products.get(competitor, {})
        pair_profiles: dict[tuple[str, str], set[str]] = defaultdict(set)
        for match in matches:
            if match.competitor_id != competitor:
                continue
            benchmark_offer = self._offers.get(match.benchmark_offer_id)
            competitor_offer = self._offers.get(match.competitor_offer_id)
            if benchmark_offer is None or competitor_offer is None:
                continue
            pair_profiles[
                (
                    benchmark_offer.offer.retailer_product_id,
                    competitor_offer.offer.retailer_product_id,
                )
            ].add(match.profile_id)
        matched_benchmark = {pair[0] for pair in pair_profiles}
        matched_competitor = {pair[1] for pair in pair_profiles}
        ambiguous_benchmark = {
            str(candidate.get("benchmark_product_id"))
            for group in ambiguous_groups
            if str(group.get("competitor_id")) == competitor
            for candidate in group.get("candidates", [])
            if candidate.get("benchmark_product_id")
        }
        ambiguous_competitor = {
            str(candidate.get("competitor_product_id"))
            for group in ambiguous_groups
            if str(group.get("competitor_id")) == competitor
            for candidate in group.get("candidates", [])
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
            "ambiguous_candidate_groups": sum(
                str(group.get("competitor_id")) == competitor for group in ambiguous_groups
            ),
            "matched_benchmark_products": len(matched_benchmark),
            "matched_competitor_products": len(matched_competitor),
            "benchmark_match_coverage": _rate(len(matched_benchmark), len(benchmark_products)),
            "competitor_match_coverage": _rate(len(matched_competitor), len(competitor_products)),
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
                    f"{_rate(len(matched_benchmark), len(benchmark_products)):.0%} of the "
                    "primary retailer's observed products."
                ),
                (
                    f"{len(competitor_only):,} competitor products have no admitted primary "
                    "counterpart; treat these as assortment whitespace to review, not "
                    "automatic substitutes."
                ),
                (
                    f"Across {len(shared_zips):,} shared ZIPs, the primary retailer has "
                    f"broader observed variety in {benchmark_broader:,} and the competitor "
                    f"in {competitor_broader:,}."
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
                        if key not in {"locations", "zipcodes", "attribute_variants"}
                    },
                    "observed_locations": len(product["locations"]),
                    "observed_zipcodes": len(product["zipcodes"]),
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
    """Overlay PDP identity without replacing Search-derived assortment metrics."""

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
        # review surface. Search remains the sole authority for observed price,
        # availability, sponsorship, and retailer-location facts.
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
