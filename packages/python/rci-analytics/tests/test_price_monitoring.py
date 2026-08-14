from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from rci_analytics import (
    PriceMonitoringFilters,
    PriceMonitoringProjector,
    ProductPackLoader,
    classified_offer_from_record,
)
from rci_analytics.models import ClassifiedOffer, NormalizedOffer
from rci_contracts import validate_instance
from rci_retailer_packs import BrandDecisionOverride, GovernedBrandResolver

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def _classified(
    *,
    offer_id: str,
    product_id: str,
    store: str,
    price: str | None,
    collected_at: str,
    in_scope: bool = True,
    in_stock: bool | None = True,
    is_sponsored: bool | None = None,
) -> ClassifiedOffer:
    return ClassifiedOffer(
        offer=NormalizedOffer(
            offer_id=offer_id,
            retailer_id="walmart_us",
            retailer_product_id=product_id,
            title=f"Product {product_id}",
            brand="Great Value",
            price=Decimal(price) if price is not None else None,
            currency="USD",
            zipcode="72712",
            store_number=store,
            latitude=36.37,
            longitude=-94.21,
            in_stock=in_stock,
            product_url=f"https://www.walmart.com/ip/{product_id}",
            image_url=None,
            collected_at=collected_at,
            raw={},
            is_sponsored=is_sponsored,
        ),
        in_scope=in_scope,
        scope_reason=None if in_scope else "excluded by Product Pack",
        attributes={},
        metrics={},
        review_reasons=(),
    )


def test_price_monitoring_is_search_authoritative_and_contract_valid() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_ground_beef")
    projector = PriceMonitoringProjector(
        pack,
        GovernedBrandResolver.from_repository(REPOSITORY_ROOT),
        retailer_names={"walmart_us": "Walmart (US)", "aldi_us": "ALDI"},
    )
    offers = [
        _classified(
            offer_id="old",
            product_id="100",
            store="1",
            price="5.00",
            collected_at="2026-08-07T05:00:00Z",
        ),
        _classified(
            offer_id="new",
            product_id="100",
            store="1",
            price="6.00",
            # Production historical rows can contain a timezone-naive UTC value.
            collected_at="2026-08-07T06:00:00",
        ),
        _classified(
            offer_id="second",
            product_id="100",
            store="2",
            price="6.00",
            collected_at="2026-08-07T06:00:00Z",
        ),
        _classified(
            offer_id="other",
            product_id="200",
            store="2",
            price="4.00",
            collected_at="2026-08-07T06:00:00Z",
        ),
        _classified(
            offer_id="noise",
            product_id="noise",
            store="1",
            price="9.00",
            collected_at="2026-08-07T06:00:00Z",
            in_scope=False,
        ),
        _classified(
            offer_id="zero",
            product_id="zero",
            store="1",
            price=None,
            collected_at="2026-08-07T06:00:00Z",
        ),
    ]
    location_index = {
        ("walmart_us", "1"): {
            "store_name": "Bentonville Supercenter",
            "zipcode": "72712",
            "city": "Bentonville",
            "state": "AR",
            "country": "USA",
            "latitude": 36.37,
            "longitude": -94.21,
        },
        ("walmart_us", "2"): {
            "store_name": "Rogers Supercenter",
            "zipcode": "72756",
            "city": "Rogers",
            "state": "AR",
            "country": "USA",
            "latitude": 36.33,
            "longitude": -94.12,
        },
    }
    view = projector.build(
        offers,
        analysis_id="price-test",
        generated_at=datetime.now(UTC).isoformat(),
        filters=PriceMonitoringFilters(retailer_id="walmart_us"),
        location_index=location_index,
        expected_location_count=2,
        source_rows=6,
        artifact_checksums=["a" * 64],
        retailer_options=["walmart_us", "aldi_us"],
        product_context={
            "walmart_us:100": {
                "name": "Great Value Ground Beef",
                "brand": "Great Value",
                "image_url": "https://i5.walmartimages.com/product.jpg",
            }
        },
    )

    validate_instance(
        REPOSITORY_ROOT,
        "price-monitoring-view.schema.json",
        view,
        label="price monitoring test view",
    )
    assert view["summary"] == {
        "observed_locations": 2,
        "expected_locations": 2,
        "coverage_rate": 1.0,
        "observed_products": 2,
        "eligible_observations": 3,
        "usable_price_rate": 0.6667,
        "price_consistency_rate": 1.0,
    }
    assert view["source"]["observed_start"] == "2026-08-07T06:00:00Z"
    assert view["source"]["observed_end"] == "2026-08-07T06:00:00Z"
    assert {
        location["observed_at"]
        for product in view["products"]
        for location in product["sample_locations"]
    } == {"2026-08-07T06:00:00Z"}
    assert view["price_distribution"]["observation_median"] == 6.0
    assert view["price_distribution"]["product_equal_weighted_median"] == 5.0
    assert view["products"][0]["price_stats"]["minimum"] == 6.0
    assert view["products"][0]["presence"] == {
        "observed_locations": 2,
        "eligible_locations": 2,
        "not_observed_locations": 0,
        "observed_rate": 1.0,
        "not_observed_rate": 0.0,
        "definition": (
            "Observed means the exact product appeared in successful Search with a positive "
            "price. Not observed is a Search non-observation within the retailer's eligible "
            "location scope, not proof of non-carriage."
        ),
    }
    assert view["products"][1]["presence"]["observed_locations"] == 1
    assert view["products"][1]["presence"]["not_observed_locations"] == 1
    assert view["products"][1]["presence"]["observed_rate"] == 0.5
    assert view["presence"] == {
        "status": "observed_only",
        "observed_locations": 2,
        "eligible_locations": 2,
        "observed_presence_rate": 1.0,
        "not_observed_locations": 0,
        "confirmed_gap_locations": 0,
        "definition": (
            "Observed presence means the selected product appeared in successful Search "
            "evidence. A Search non-observation is not proof that a store does not carry "
            "the product."
        ),
    }
    assert view["filter_options"]["products"][0]["value"] == "100"
    assert view["filter_options"]["cities"] == []
    assert view["filter_options"]["zipcodes"] == []
    assert sum(row["count"] for row in view["price_histogram"]) == 3
    checks = {row["id"]: row for row in view["quality"]["checks"]}
    assert checks["duplicate-product-location"]["count"] == 1
    assert checks["conflicting-product-location-price"]["count"] == 1
    assert checks["missing-or-zero-price"]["count"] == 1
    assert {row["id"] for row in view["filter_options"]["retailers"]} == {
        "walmart_us",
        "aldi_us",
    }

    product_view = projector.build(
        offers,
        analysis_id="price-test",
        generated_at=datetime.now(UTC).isoformat(),
        filters=PriceMonitoringFilters(
            retailer_id="walmart_us",
            state="AR",
            city="Bentonville",
            product_id="100",
        ),
        location_index=location_index,
        expected_location_count=2,
        source_rows=6,
        artifact_checksums=["a" * 64],
    )
    validate_instance(
        REPOSITORY_ROOT,
        "price-monitoring-view.schema.json",
        product_view,
        label="filtered product price monitoring view",
    )
    assert product_view["summary"]["observed_locations"] == 1
    assert product_view["summary"]["expected_locations"] == 1
    assert product_view["summary"]["coverage_rate"] == 1.0
    assert product_view["products"][0]["sample_locations"][0]["store_name"] == (
        "Bentonville Supercenter"
    )
    assert product_view["filter_options"]["cities"]
    assert product_view["filter_options"]["zipcodes"] == [
        {"value": "72712", "label": "72712", "count": 1}
    ]


def test_classified_parquet_record_round_trip_preserves_provider_ids() -> None:
    source = _classified(
        offer_id="offer-1",
        product_id="0000000000008696",
        store="0042",
        price="6.59",
        collected_at="2026-08-07T06:00:00Z",
    )
    restored = classified_offer_from_record(source.to_record())

    assert restored.offer.retailer_product_id == "0000000000008696"
    assert restored.offer.store_number == "0042"
    assert restored.offer.zipcode == "72712"
    assert restored.offer.price == Decimal("6.59")


def test_classified_parquet_record_preserves_explicit_price_components() -> None:
    source = _classified(
        offer_id="offer-promo",
        product_id="100",
        store="0042",
        price="5.49",
        collected_at="2026-08-07T06:00:00Z",
    )
    source = replace(
        source,
        offer=replace(
            source.offer,
            regular_price=Decimal("5.99"),
            discounted_price=Decimal("5.49"),
            is_sponsored=True,
        ),
    )

    restored = classified_offer_from_record(source.to_record())

    assert restored.offer.regular_price == Decimal("5.99")
    assert restored.offer.discounted_price == Decimal("5.49")
    assert restored.offer.is_sponsored is True


def test_price_monitoring_uses_positive_search_price_for_stock_and_boolean_for_sponsorship() -> (
    None
):
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_ground_beef")
    projector = PriceMonitoringProjector(
        pack,
        GovernedBrandResolver.from_repository(REPOSITORY_ROOT),
    )
    offers = [
        _classified(
            offer_id="sponsored",
            product_id="100",
            store="1",
            price="5.00",
            collected_at="2026-08-07T06:00:00Z",
            in_stock=False,
            is_sponsored=True,
        ),
        _classified(
            offer_id="organic",
            product_id="100",
            store="2",
            price="5.25",
            collected_at="2026-08-07T06:00:00Z",
            in_stock=None,
            is_sponsored=False,
        ),
    ]
    locations = {
        ("walmart_us", "1"): {
            "store_name": "Store One",
            "zipcode": "72712",
            "city": "Bentonville",
            "state": "AR",
            "country": "USA",
        },
        ("walmart_us", "2"): {
            "store_name": "Store Two",
            "zipcode": "72756",
            "city": "Rogers",
            "state": "AR",
            "country": "USA",
        },
        ("walmart_us", "3"): {
            "store_name": "Store Three",
            "zipcode": "75201",
            "city": "Dallas",
            "state": "TX",
            "country": "USA",
        },
    }
    view = projector.build(
        offers,
        analysis_id="signals-test",
        generated_at=datetime.now(UTC).isoformat(),
        filters=PriceMonitoringFilters(
            retailer_id="walmart_us",
            product_id="100",
        ),
        location_index=locations,
        eligible_location_index=locations,
        expected_location_count=3,
    )

    product = view["products"][0]
    assert product["availability"] == {
        "status": "observed",
        "known_observations": 2,
        "in_stock_observations": 2,
        "rate": 1.0,
        "definition": (
            "A product observed in Search with a price greater than zero is treated "
            "as available/in stock at that location."
        ),
    }
    assert product["sponsorship"]["rate"] == 0.5
    assert view["presence"]["not_observed_locations"] == 1
    assert view["distribution_gaps"]["locations"][0]["store_name"] == "Store Three"
    tx_gap = next(row for row in view["distribution_gaps"]["geographies"] if row["key"] == "TX")
    assert tx_gap["not_observed_locations"] == 1
    assert tx_gap["observed_rate"] == 0.0


def test_price_monitoring_flags_exact_product_modal_price_exception() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_ground_beef")
    projector = PriceMonitoringProjector(
        pack,
        GovernedBrandResolver.from_repository(REPOSITORY_ROOT),
    )
    offers = [
        _classified(
            offer_id=f"offer-{store}",
            product_id="100",
            store=store,
            price="5.00" if store != "5" else "8.00",
            collected_at="2026-08-07T06:00:00Z",
        )
        for store in ("1", "2", "3", "4", "5")
    ]
    locations = {
        ("walmart_us", store): {
            "zipcode": f"7271{store}",
            "city": "Bentonville",
            "state": "AR",
            "country": "USA",
        }
        for store in ("1", "2", "3", "4", "5")
    }

    view = projector.build(
        offers,
        analysis_id="price-exception-test",
        generated_at=datetime.now(UTC).isoformat(),
        filters=PriceMonitoringFilters(retailer_id="walmart_us", product_id="100"),
        location_index=locations,
        expected_location_count=5,
    )

    assert len(view["exceptions"]) == 1
    assert view["exceptions"][0]["store_number"] == "5"
    assert view["exceptions"][0]["difference"] == 3.0
    assert "Product Pack tolerance" in view["exceptions"][0]["reason"]


def test_price_monitoring_uses_governed_canonical_external_brand_identity() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_fluid_milk")
    projector = PriceMonitoringProjector(
        pack,
        GovernedBrandResolver.from_repository(REPOSITORY_ROOT),
        retailer_names={"walmart_us": "Walmart (US)"},
    )
    offer = _classified(
        offer_id="fairlife-1",
        product_id="fairlife-product",
        store="1",
        price="4.98",
        collected_at="2026-08-07T06:00:00Z",
    )
    offer = replace(offer, offer=replace(offer.offer, brand="Fairlife"))
    view = projector.build(
        [offer],
        analysis_id="milk-brand-foundation-test",
        generated_at=datetime.now(UTC).isoformat(),
        filters=PriceMonitoringFilters(retailer_id="walmart_us"),
        location_index={
            ("walmart_us", "1"): {
                "zipcode": "72712",
                "city": "Bentonville",
                "state": "AR",
                "country": "USA",
            }
        },
    )

    assert view["products"][0]["brand"] == "fairlife"
    assert view["products"][0]["brand_type"] == "national"
    assert view["brand_portfolio"][0]["brand_type"] == "national"


def test_price_monitoring_applies_a_confirmed_canonical_brand_mapping() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_fluid_milk")
    resolver = GovernedBrandResolver.from_repository(REPOSITORY_ROOT).with_overrides(
        [
            BrandDecisionOverride(
                retailer_id="walmart_us",
                normalized_brand="mayfield",
                display_brand="Mayfield",
                role="regional",
                decision="confirmed",
                canonical_brand_id="regional__mayfield_dairy_farms",
                canonical_brand_name="Mayfield Dairy Farms",
            )
        ]
    )
    projector = PriceMonitoringProjector(
        pack,
        resolver,
        retailer_names={"walmart_us": "Walmart (US)"},
    )
    offer = _classified(
        offer_id="mayfield-1",
        product_id="mayfield-product",
        store="1",
        price="4.12",
        collected_at="2026-08-07T06:00:00Z",
    )
    offer = replace(offer, offer=replace(offer.offer, brand="Mayfield"))

    view = projector.build(
        [offer],
        analysis_id="milk-governed-brand-mapping-test",
        generated_at=datetime.now(UTC).isoformat(),
        filters=PriceMonitoringFilters(retailer_id="walmart_us"),
        location_index={
            ("walmart_us", "1"): {
                "zipcode": "72712",
                "city": "Bentonville",
                "state": "AR",
                "country": "USA",
            }
        },
    )

    assert view["products"][0]["brand"] == "Mayfield Dairy Farms"
    assert view["products"][0]["brand_type"] == "regional"
    assert view["products"][0]["brand_origin"] == "user"
