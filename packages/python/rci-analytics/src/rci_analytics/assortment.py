"""Category-neutral assortment coverage and relationship diagnostics."""

from __future__ import annotations

import copy
import statistics
from collections import defaultdict
from collections.abc import Iterable

from rci_analytics.models import ClassifiedOffer, JsonObject, MatchRecord


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
                "brand": offer.brand,
                "image_url": offer.image_url,
                "url": offer.product_url,
                "locations": set(),
                "zipcodes": set(),
            },
        )
        if not product.get("image_url") and offer.image_url:
            product["image_url"] = offer.image_url
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
    ) -> JsonObject:
        profile_labels = {
            str(profile["id"]): str(profile.get("label") or profile["id"]) for profile in profiles
        }
        match_rows = list(matches)
        retailers = [benchmark_retailer, *[str(value) for value in competitors]]
        return {
            "source": "Search results classified in scope by the Product Pack",
            "grain": (
                "Distinct retailer product IDs; store breadth uses ZIP + store ID when available"
            ),
            "benchmark_retailer": benchmark_retailer,
            "retailers": [self._retailer_summary(retailer) for retailer in retailers],
            "comparisons": [
                self._comparison(benchmark_retailer, competitor, match_rows, profile_labels)
                for competitor in retailers
                if competitor != benchmark_retailer
            ],
        }

    def _retailer_summary(self, retailer: str) -> JsonObject:
        products = self._products.get(retailer, {})
        counts = [len(values) for values in self._locations.get(retailer, {}).values()]
        return {
            "retailer": retailer,
            "distinct_products": len(products),
            "observed_locations": len(self._locations.get(retailer, {})),
            "observed_zipcodes": len(self._zips.get(retailer, {})),
            "median_products_per_location": (
                round(float(statistics.median(counts)), 1) if counts else 0.0
            ),
        }

    def _comparison(
        self,
        benchmark: str,
        competitor: str,
        matches: list[MatchRecord],
        profile_labels: dict[str, str],
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
        benchmark_only = set(benchmark_products) - matched_benchmark
        competitor_only = set(competitor_products) - matched_competitor
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
            "matched_benchmark_products": len(matched_benchmark),
            "matched_competitor_products": len(matched_competitor),
            "benchmark_match_coverage": _rate(len(matched_benchmark), len(benchmark_products)),
            "competitor_match_coverage": _rate(len(matched_competitor), len(competitor_products)),
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
            },
            "top_benchmark_only": self._rank_products(benchmark, benchmark_only),
            "top_competitor_whitespace": self._rank_products(competitor, competitor_only),
            "key_points": [
                (
                    f"{len(pair_profiles):,} distinct one-to-one product relationships cover "
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
                        if key not in {"locations", "zipcodes"}
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
    for comparison in enriched.get("comparisons", []):
        for field in ("top_benchmark_only", "top_competitor_whitespace"):
            for product in comparison.get(field, []):
                pdp = context.get(str(product.get("canonical_product_id")))
                if not pdp:
                    continue
                for key in ("name", "brand", "image_url", "url"):
                    if pdp.get(key):
                        product[key] = pdp[key]
    return enriched
