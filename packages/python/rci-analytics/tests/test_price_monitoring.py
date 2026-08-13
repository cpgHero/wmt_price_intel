from __future__ import annotations

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
from rci_retailer_packs import GovernedBrandResolver

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def _classified(
    *,
    offer_id: str,
    product_id: str,
    store: str,
    price: str | None,
    collected_at: str,
    in_scope: bool = True,
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
            in_stock=True,
            product_url=f"https://www.walmart.com/ip/{product_id}",
            image_url=None,
            collected_at=collected_at,
            raw={},
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
            collected_at="2026-08-07T06:00:00Z",
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
    assert view["price_distribution"]["observation_median"] == 6.0
    assert view["price_distribution"]["product_equal_weighted_median"] == 5.0
    assert view["products"][0]["price_stats"]["minimum"] == 6.0
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
