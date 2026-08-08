from __future__ import annotations

import csv
import json
import os
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from rci_analytics.matching import ComparisonEngine
from rci_analytics.models import ClassifiedOffer, MatchRecord, NormalizedOffer
from rci_analytics.normalization import CanonicalOfferNormalizer, RetailerIdentityMap
from rci_analytics.product_pack import ProductPackLoader
from rci_locations.normalization import normalize_zipcode

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
INPUT = os.getenv("RCI_GOLDEN_EGGS_CSV")
FIXTURE_ROOT = REPOSITORY_ROOT / "fixtures" / "golden" / "eggs"

DOMAIN_TO_ID = {
    "albertsons.com": "albertsons_us",
    "aldi.us": "aldi_us",
    "amazon.com": "amazon_us_same_day",
    "gianteagle.com": "giant_eagle_us",
    "heb.com": "heb_us",
    "kroger.com": "kroger_us",
    "meijer.com": "meijer_us",
    "safeway.com": "safeway_us",
    "samsclub.com": "sams_club_us",
    "shoprite.com": "shoprite_us",
    "target.com": "target_us",
    "traderjoes.com": "trader_joes_us",
    "walmart.com": "walmart_us",
    "wegmans.com": "wegmans_us",
}
DISPLAY_TO_DOMAIN = {
    "Albertsons": "albertsons.com",
    "ALDI": "aldi.us",
    "Amazon": "amazon.com",
    "Giant Eagle": "gianteagle.com",
    "H-E-B": "heb.com",
    "Kroger": "kroger.com",
    "Meijer": "meijer.com",
    "Safeway": "safeway.com",
    "Sam's Club": "samsclub.com",
    "ShopRite": "shoprite.com",
    "Target": "target.com",
    "Trader Joe's": "traderjoes.com",
    "Walmart": "walmart.com",
    "Wegmans": "wegmans.com",
}


def _expected() -> dict[str, Any]:
    return json.loads((FIXTURE_ROOT / "validated_summary.json").read_text(encoding="utf-8"))


def _validated_catalog() -> set[tuple[str, str, str]]:
    with (FIXTURE_ROOT / "product_catalog.csv").open(newline="", encoding="utf-8-sig") as handle:
        return {
            (
                DISPLAY_TO_DOMAIN[row["Retailer"]],
                row["Product ID"],
                row["Title"],
            )
            for row in csv.DictReader(handle)
        }


@pytest.mark.skipif(not INPUT, reason="set RCI_GOLDEN_EGGS_CSV for the full source regression")
def test_full_egg_consolidated_source_profile() -> None:
    assert INPUT is not None
    expected = _expected()
    catalog = _validated_catalog()
    normalizer = CanonicalOfferNormalizer(
        RetailerIdentityMap.from_catalog(REPOSITORY_ROOT / "config/retailer-catalog.json")
    )
    raw_counts: Counter[str] = Counter()
    fresh_counts: Counter[str] = Counter()
    fresh_zips: dict[str, set[str]] = defaultdict(set)
    fresh_stores: dict[str, set[str]] = defaultdict(set)
    fresh_products: dict[str, set[str]] = defaultdict(set)
    normalized_retailers: dict[str, str] = {}
    seen: set[tuple[str, str, str, str, str]] = set()
    all_seen: set[tuple[str, str, str, str, str]] = set()
    keyword_counts: Counter[str] = Counter()
    stock_counts: Counter[str] = Counter()
    short_zip_rows = 0
    duplicate_grain_rows = 0
    nonpositive_price_rows = 0
    scientific_timestamp_rows = 0
    required_blank_rows = 0

    with Path(INPUT).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == [
            "Date",
            "Retailer",
            "Keyword",
            "Retailer Store Id",
            "Retailer Store Name",
            "Zipcode",
            "Page Number",
            "Result Position",
            "Product Name",
            "Brand",
            "Is Sponsored",
            "Badges",
            "Price",
            "Price Regular",
            "Price Discounted",
            "Stock Availability",
            "Rating",
            "Rating Count",
            "Reviews Count",
            "Monthly Sales Volume",
            "Weekly Sales Volume",
            "Image Url",
            "Url",
            "Shipping Extras",
            "Retailer Product Id",
            "Latitude",
            "Longitude",
        ]
        for row in reader:
            retailer = row["Retailer"]
            raw_counts[retailer] += 1
            keyword_counts[row["Keyword"]] += 1
            stock_counts[row["Stock Availability"].strip().casefold() or "blank"] += 1
            required_blank_rows += any(
                not row[column].strip()
                for column in (
                    "Date",
                    "Retailer",
                    "Keyword",
                    "Zipcode",
                    "Product Name",
                    "Retailer Product Id",
                )
            )
            if retailer not in normalized_retailers:
                normalized_retailers[retailer] = normalizer.normalize(dict(row)).retailer_id

            raw_zipcode = row["Zipcode"]
            short_zip_rows += len(raw_zipcode) < 5
            zipcode = normalize_zipcode(raw_zipcode, "USA")
            product_id = row["Retailer Product Id"]
            title = row["Product Name"]
            source_key = (
                retailer,
                zipcode,
                row["Retailer Store Id"],
                product_id,
                title.casefold(),
            )
            duplicate_grain_rows += source_key in all_seen
            all_seen.add(source_key)
            nonpositive_price_rows += Decimal(row["Price"]) <= 0
            scientific_timestamp_rows += "e+" in row["Date"].casefold()
            if (retailer, product_id, title) not in catalog:
                continue
            if retailer == "amazon.com" and row["Stock Availability"].strip().casefold() == "false":
                continue
            store_id = row["Retailer Store Id"]
            key = (retailer, zipcode, store_id, product_id, title)
            if key in seen:
                continue
            seen.add(key)
            fresh_counts[retailer] += 1
            fresh_zips[retailer].add(zipcode)
            if store_id:
                fresh_stores[retailer].add(store_id)
            fresh_products[retailer].add(product_id)

    assert sum(raw_counts.values()) == expected["raw_rows"] == 386_889
    assert len(raw_counts) == expected["retailer_domains"] == 14
    assert normalized_retailers == DOMAIN_TO_ID
    quality = expected["source_quality"]
    assert keyword_counts == quality["keyword_rows"]
    assert short_zip_rows == quality["short_zip_rows"]
    assert duplicate_grain_rows == quality["duplicate_candidate_grain_rows"]
    assert nonpositive_price_rows == quality["nonpositive_price_rows"]
    assert scientific_timestamp_rows == quality["scientific_timestamp_rows"]
    assert stock_counts == quality["stock_availability_rows"]
    assert required_blank_rows == quality["required_identity_blank_rows"]
    assert all(len(zipcode) == 5 for values in fresh_zips.values() for zipcode in values)

    for row in expected["retailer_scorecard"]:
        retailer = str(row["retailer"])
        assert raw_counts[retailer] == row["raw_rows"]
        assert fresh_counts[retailer] == row["fresh_egg_rows_dedup"]
        assert len(fresh_zips[retailer]) == row["fresh_egg_zips"]
        assert len(fresh_stores[retailer]) == row["fresh_egg_stores"]
        assert len(fresh_products[retailer]) == row["fresh_egg_products"]


def _decimal(value: str) -> Decimal:
    return Decimal(value)


def _boolean(value: str) -> bool:
    return value.strip().casefold() in {"1", "true", "yes"}


def _offer(
    *,
    offer_id: str,
    retailer_id: str,
    zipcode: str,
    title: str,
    brand: str,
    package_price: str,
    price_per_dozen: str,
    attributes: dict[str, object],
) -> ClassifiedOffer:
    normalized = NormalizedOffer(
        offer_id=offer_id,
        retailer_id=retailer_id,
        retailer_product_id=offer_id,
        title=title,
        brand=brand or None,
        price=_decimal(package_price),
        currency="USD",
        zipcode=zipcode,
        store_number=None,
        latitude=None,
        longitude=None,
        in_stock=True,
        product_url=None,
        image_url=None,
        collected_at=None,
        raw={},
    )
    return ClassifiedOffer(
        offer=normalized,
        in_scope=True,
        scope_reason=None,
        attributes=attributes,
        metrics={"price_per_dozen": _decimal(price_per_dozen)},
        review_reasons=(),
    )


def _strict_offers() -> list[ClassifiedOffer]:
    offers: list[ClassifiedOffer] = []
    with (FIXTURE_ROOT / "strict_matches.csv").open(newline="", encoding="utf-8-sig") as handle:
        for index, row in enumerate(csv.DictReader(handle), start=1):
            attributes: dict[str, object] = {
                "count": float(row["Count"]),
                "size": row["Size"],
                "shell_color": row["Color"],
                "grade": row["Grade"],
                "organic": _boolean(row["Organic"]),
                "housing": row["Housing"],
            }
            competitor_id = DOMAIN_TO_ID[row["Competitor"]]
            offers.extend(
                [
                    _offer(
                        offer_id=f"walmart:{index}",
                        retailer_id="walmart_us",
                        zipcode=row["ZIP"],
                        title=row["Walmart Product"],
                        brand=row["Walmart Brand"],
                        package_price=row["Walmart Price"],
                        price_per_dozen=row["Walmart $/Dozen"],
                        attributes=attributes,
                    ),
                    _offer(
                        offer_id=f"{competitor_id}:{index}",
                        retailer_id=competitor_id,
                        zipcode=row["ZIP"],
                        title=row["Competitor Product"],
                        brand=row["Competitor Brand"],
                        package_price=row["Competitor Price"],
                        price_per_dozen=row["Competitor $/Dozen"],
                        attributes=attributes,
                    ),
                ]
            )
    return offers


def _assert_strict_summary(
    engine: ComparisonEngine,
    matches: list[MatchRecord],
    expected: dict[str, Any],
) -> None:
    if not matches:
        assert expected["matches"] == 0
        return
    summary = engine.summarize(matches)
    assert summary.matches == expected["matches"]
    assert summary.unique_geographies == expected["matched_zips"]
    assert summary.benchmark_lower == expected["walmart_lower_count"]
    assert summary.competitor_lower == expected["competitor_lower_count"]
    assert summary.parity == expected["parity_count"]
    assert summary.benchmark_lower_rate == pytest.approx(expected["walmart_lower_rate"], abs=1e-12)
    assert summary.competitor_lower_rate == pytest.approx(
        expected["competitor_lower_rate"], abs=1e-12
    )
    assert summary.parity_rate == pytest.approx(expected["parity_rate"], abs=1e-12)
    assert summary.median_gap == pytest.approx(expected["median_unit_gap_per_dozen"], abs=1e-12)


def test_full_egg_strict_match_golden_regression() -> None:
    expected = _expected()
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_shell_eggs")
    engine = ComparisonEngine(pack)
    offers = _strict_offers()
    all_matches: list[MatchRecord] = []

    for expected_row in expected["strict_summary"]:
        competitor_id = DOMAIN_TO_ID[str(expected_row["retailer"])]
        matches = engine.compare(
            offers,
            benchmark_id="walmart_us",
            competitor_id=competitor_id,
            profile_id="strict",
        )
        _assert_strict_summary(engine, matches, expected_row)
        all_matches.extend(matches)

    assert len(all_matches) == 5_155
    walmart_lower = sum(match.winner == "benchmark_lower" for match in all_matches)
    assert walmart_lower / len(all_matches) == pytest.approx(0.7468477206595538, abs=1e-12)
    aldi = [match for match in all_matches if match.competitor_id == "aldi_us"]
    assert sum(match.winner == "competitor_lower" for match in aldi) / len(aldi) == pytest.approx(
        0.5525040387722132,
        abs=1e-12,
    )
    assert all(match.comparison_metric == "price_per_dozen" for match in all_matches)
