from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from rci_analytics.classification import OfferClassifier
from rci_analytics.matching import ComparisonEngine
from rci_analytics.models import NormalizedOffer
from rci_analytics.product_pack import ProductPackLoader
from rci_retailer_packs import GovernedBrandResolver

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def _offer(
    retailer_id: str,
    product_id: str,
    brand: str,
    title: str,
    price: str,
) -> NormalizedOffer:
    return NormalizedOffer(
        offer_id=f"{retailer_id}:{product_id}",
        retailer_id=retailer_id,
        retailer_product_id=product_id,
        title=title,
        brand=brand,
        price=Decimal(price),
        currency="USD",
        zipcode="72712",
        store_number="100",
        latitude=36.37,
        longitude=-94.2,
        in_stock=True,
        product_url=None,
        image_url=None,
        collected_at="2026-08-11T12:00:00Z",
        raw={},
    )


def test_classifier_adds_brand_governance_without_changing_search_price_or_location() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_fluid_milk")
    resolver = GovernedBrandResolver.from_repository(REPOSITORY_ROOT)
    classifier = OfferClassifier(pack, resolver)
    offer = _offer(
        "walmart_us",
        "milk-1",
        "Great Value",
        "Great Value Whole Milk, 1 Gallon",
        "3.97",
    )

    classified = classifier.classify(offer)

    assert classified.offer.price == Decimal("3.97")
    assert classified.offer.store_number == "100"
    assert classified.offer.zipcode == "72712"
    assert classified.attributes["_brand_governance"]["canonical_brand_id"] == (
        "walmart__great_value"
    )
    assert classified.attributes["_brand_governance"]["strict_private_label"] is True


def test_private_label_identity_cannot_override_product_pack_compatibility() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_fluid_milk")
    document = deepcopy(pack.document)
    for retailer in ("walmart_us", "aldi_us"):
        document["retailer_overrides"][retailer]["catalog_policy"] = "rules_only"
        document["retailer_overrides"][retailer]["products"] = {}
    pack = replace(pack, document=document)
    resolver = GovernedBrandResolver.from_repository(REPOSITORY_ROOT)
    classifier = OfferClassifier(pack, resolver)
    engine = ComparisonEngine(pack, resolver)
    offers = classifier.classify_many(
        [
            _offer(
                "walmart_us",
                "w-1",
                "Great Value",
                "Great Value Whole Milk, 1 Gallon",
                "3.97",
            ),
            _offer(
                "aldi_us",
                "a-1",
                "Friendly Farms",
                "Friendly Farms Whole Milk, Half Gallon",
                "2.49",
            ),
        ]
    )

    assert all(
        offer.attributes["_brand_governance"]["strict_private_label"] is True for offer in offers
    )
    assert (
        engine.compare_products(
            offers,
            benchmark_id="walmart_us",
            competitor_id="aldi_us",
            profile_id="private_label",
        )
        == []
    )


def test_certified_product_pack_can_fill_missing_retailer_foundation_coverage() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_fluid_milk")
    document = deepcopy(pack.document)
    for attribute in document["attributes"]:
        if attribute["name"] in {
            "flavor",
            "organic",
            "lactose_free",
            "ultrafiltered",
            "a2",
            "grass_fed",
            "omega_3_dha",
            "kids",
            "protein_fortified",
        }:
            attribute["extraction_rules"][0]["absence_policy"] = "infer_default"
    pack = replace(pack, document=document)
    resolver = GovernedBrandResolver.from_repository(REPOSITORY_ROOT)
    classifier = OfferClassifier(pack, resolver)
    engine = ComparisonEngine(pack, resolver)
    offers = classifier.classify_many(
        [
            _offer(
                "walmart_us",
                "w-1",
                "Great Value",
                "Great Value Whole Milk, 1 Gallon",
                "3.97",
            ),
            _offer(
                "amazon_us_same_day",
                "m-1",
                "Amazon Fresh",
                "Amazon Fresh Whole Milk, 1 Gallon",
                "4.29",
            ),
        ]
    )

    assert offers[1].attributes["_brand_governance"]["status"] == "unresolved"
    matches = engine.compare_products(
        offers,
        benchmark_id="walmart_us",
        competitor_id="amazon_us_same_day",
        profile_id="private_label",
    )

    assert len(matches) == 1
    assert matches[0].benchmark_offer_id == "walmart_us:w-1"
    assert matches[0].competitor_offer_id == "amazon_us_same_day:m-1"
