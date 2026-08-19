from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from rci_analytics import (
    PriceMonitoringFilters,
    PriceMonitoringProjector,
    ProductLocationProjector,
    ProductPackLoader,
)
from rci_analytics.models import ClassifiedOffer, NormalizedOffer
from rci_contracts import validate_instance
from rci_retailer_packs import GovernedBrandResolver, GovernedSellerResolver

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def _classified(
    *,
    offer_id: str,
    product_id: str = "000123",
    price: str | None,
    collected_at: str,
    in_scope: bool = True,
    zipcode: str = "99999",
    store_number: str | None = "0017",
    sponsored: bool | None = True,
    metric: str | None = None,
) -> ClassifiedOffer:
    return ClassifiedOffer(
        offer=NormalizedOffer(
            offer_id=offer_id,
            retailer_id="walmart_us",
            retailer_product_id=product_id,
            title="Search identity must not override PDP",
            brand="Search Brand",
            price=Decimal(price) if price is not None else None,
            currency="USD",
            zipcode=zipcode,
            store_number=store_number,
            latitude=1.0,
            longitude=2.0,
            in_stock=False,
            product_url="https://search.example/product",
            image_url="https://search.example/image.jpg",
            collected_at=collected_at,
            raw={},
            regular_price=Decimal("7.00") if price is not None else None,
            discounted_price=Decimal(price) if price is not None else None,
            is_sponsored=sponsored,
        ),
        in_scope=in_scope,
        scope_reason="matched" if in_scope else "noise",
        attributes={},
        metrics={"price_per_lb": Decimal(metric)} if metric is not None else {},
        review_reasons=(),
    )


def _projector() -> ProductLocationProjector:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_ground_beef")
    return ProductLocationProjector(
        pack,
        GovernedBrandResolver.from_repository(REPOSITORY_ROOT),
        retailer_names={"walmart_us": "Walmart (US)"},
    )


def test_canonical_population_governs_authority_dedupe_identity_and_contract() -> None:
    offers = [
        _classified(
            offer_id="old",
            price="5.00",
            metric="2.50",
            collected_at="2026-08-07T05:00:00Z",
        ),
        _classified(
            offer_id="new",
            price="6.00",
            metric="3.00",
            collected_at="2026-08-07T06:00:00Z",
        ),
        _classified(
            offer_id="zero",
            product_id="000999",
            price=None,
            collected_at="2026-08-07T06:00:00Z",
        ),
        _classified(
            offer_id="noise",
            product_id="000888",
            price="9.00",
            collected_at="2026-08-07T06:00:00Z",
            in_scope=False,
        ),
    ]
    location_index = {
        ("walmart_us", "0017"): {
            "store_name": "Derry Supercenter",
            "zipcode": "03038",
            "city": "Derry",
            "state": "NH",
            "country": "USA",
            "latitude": 42.8806,
            "longitude": -71.3273,
        }
    }
    product_context = {
        "walmart_us:000123": {
            "name": "Great Value 93% Lean Ground Beef, 1 lb",
            "brand": "Great Value",
            "image_url": "https://pdp.example/image.jpg",
            "url": "https://pdp.example/product/000123",
        }
    }

    population = _projector().build(
        offers,
        retailer_id="walmart_us",
        location_index=location_index,
        product_context=product_context,
    )

    assert len(population.observations) == 1
    observation = population.observations[0]
    assert observation.observation_id == "new"
    assert observation.product_id == "000123"
    assert observation.product_name == "Great Value 93% Lean Ground Beef, 1 lb"
    assert observation.brand == "Great Value"
    assert observation.brand_type == "private_label"
    assert observation.identity_authority == "pdp"
    assert observation.package_price == 6.0
    assert observation.location.store_number == "0017"
    assert observation.location.zipcode == "03038"
    assert observation.location.latitude == 42.8806
    assert observation.is_sponsored is True
    assert observation.to_price_monitoring_row()["in_stock"] is True
    assert dict(population.exclusion_counts) == {
        "missing_or_zero_price": 1,
        "out_of_scope": 1,
    }
    assert population.duplicate_rows == 1
    assert population.conflicting_keys == {("000123", "walmart_us|store|0017")}

    contract = observation.to_price_observation_contract(
        analysis_id="analysis-1",
        product_pack_id="fresh_ground_beef",
        product_pack_version="1.0.0",
    )
    validate_instance(
        REPOSITORY_ROOT,
        "price-observation.schema.json",
        contract,
        label="canonical product-location observation",
    )
    assert contract["source_authority"] == "search_location_observation"
    assert contract["location_authority"] == "retailer_location_master"

    package_rows = population.comparison_observations(
        {"000123"},
        "package_price",
    )
    unit_rows = population.comparison_observations(
        {"000123"},
        "price_per_lb",
    )
    assert package_rows["000123"][0].comparison_value == 6.0
    assert unit_rows["000123"][0].comparison_value == 3.0
    assert unit_rows["000123"][0].brand_type == "private_label"

    replay = _projector().build(
        reversed(offers),
        retailer_id="walmart_us",
        location_index=location_index,
        product_context=product_context,
    )
    assert replay.checksum == population.checksum


def test_canonical_population_excludes_known_third_party_sellers_but_keeps_missing_seller() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_ground_beef")
    projector = ProductLocationProjector(
        pack,
        GovernedBrandResolver.from_repository(REPOSITORY_ROOT),
        seller_resolver=GovernedSellerResolver.from_repository(REPOSITORY_ROOT),
    )
    offers = [
        _classified(
            offer_id="marketplace",
            product_id="marketplace-product",
            price="188.58",
            collected_at="2026-08-07T06:00:00Z",
            store_number="0017",
        ),
        _classified(
            offer_id="unknown-seller",
            product_id="unknown-product",
            price="4.25",
            collected_at="2026-08-07T06:00:00Z",
            store_number="0018",
        ),
    ]

    population = projector.build(
        offers,
        retailer_id="walmart_us",
        product_context={
            "walmart_us:marketplace-product": {"seller": "Food Service Direct"},
            "walmart_us:unknown-product": {"seller": None},
        },
    )

    assert [row.product_id for row in population.observations] == ["unknown-product"]
    assert dict(population.exclusion_counts) == {"known_third_party_seller": 1}


def test_unknown_location_is_excluded_from_every_downstream_projection() -> None:
    population = _projector().build(
        [
            _classified(
                offer_id="unknown",
                price="4.00",
                metric="2.00",
                collected_at="2026-08-07T06:00:00Z",
                zipcode="",
                store_number=None,
            )
        ],
        retailer_id="walmart_us",
    )

    assert population.observations == ()
    assert dict(population.exclusion_counts) == {"missing_location_identity": 1}
    assert population.comparison_observations({"000123"}, "package_price") == {"000123": ()}


def test_canonical_population_orders_mixed_naive_and_aware_timestamps() -> None:
    population = _projector().build(
        [
            _classified(
                offer_id="earlier-aware",
                price="3.49",
                metric="3.49",
                collected_at="2026-08-07T05:00:00Z",
            ),
            _classified(
                offer_id="later-naive",
                price="3.59",
                metric="3.59",
                collected_at="2026-08-07T06:00:00",
            ),
        ],
        retailer_id="walmart_us",
    )

    assert len(population.observations) == 1
    assert population.observations[0].offer_id == "later-naive"
    assert population.observations[0].package_price == 3.59


def test_price_and_competitive_projections_reconcile_to_one_population() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_ground_beef")
    projector = PriceMonitoringProjector(
        pack,
        GovernedBrandResolver.from_repository(REPOSITORY_ROOT),
        retailer_names={"walmart_us": "Walmart (US)"},
    )
    offers = [
        _classified(
            offer_id="store-17",
            price="6.00",
            metric="3.00",
            collected_at="2026-08-07T06:00:00Z",
        )
    ]
    locations = {
        ("walmart_us", "0017"): {
            "store_name": "Derry Supercenter",
            "zipcode": "03038",
            "city": "Derry",
            "state": "NH",
            "country": "USA",
            "latitude": 42.8806,
            "longitude": -71.3273,
        }
    }
    identity = {
        "walmart_us:000123": {
            "name": "Great Value 93% Lean Ground Beef, 1 lb",
            "brand": "Great Value",
        }
    }

    view = projector.build(
        offers,
        analysis_id="analysis-1",
        generated_at="2026-08-07T06:00:00Z",
        filters=PriceMonitoringFilters(retailer_id="walmart_us"),
        location_index=locations,
        product_context=identity,
    )
    comparison = projector.comparison_observations(
        offers,
        retailer_id="walmart_us",
        product_ids={"000123"},
        comparison_metric="package_price",
        location_index=locations,
        product_context=identity,
    )["000123"][0]
    population = projector.canonical_population(
        offers,
        retailer_id="walmart_us",
        location_index=locations,
        product_context=identity,
    )

    assert view["source"]["observation_population_checksum"] == population.checksum
    assert view["products"][0]["product_id"] == comparison.product_id
    assert view["products"][0]["name"] == comparison.product_name
    assert view["products"][0]["brand_type"] == comparison.brand_type
    assert view["products"][0]["price_stats"]["observation_median"] == (comparison.package_price)
    assert view["products"][0]["sample_locations"][0]["store_number"] == (comparison.store_number)
