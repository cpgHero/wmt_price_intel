from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from rci_analytics.classification import OfferClassifier
from rci_analytics.models import NormalizedOffer
from rci_analytics.pdp_attributes import complete_attributes_from_pdp, product_context_index
from rci_analytics.product_pack import ProductPackLoader

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def test_product_context_index_excludes_search_only_identity_rows() -> None:
    values = [
        {
            "canonical_product_id": "walmart_us:search-only",
            "role": "Search identity reference",
        },
        {
            "canonical_product_id": "walmart_us:pdp",
            "role": "PDP-enriched reference",
        },
    ]

    assert product_context_index(values) == {
        "walmart_us:pdp": values[1],
    }


def test_pdp_completes_only_unresolved_attributes_and_preserves_search_price() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_ground_beef")
    document = deepcopy(pack.document)
    document["retailer_overrides"]["walmart_us"]["catalog_policy"] = "rules_only"
    document["retailer_overrides"]["walmart_us"]["products"] = {}
    pack = replace(pack, document=document)
    classifier = OfferClassifier(pack)
    offer = NormalizedOffer(
        offer_id="offer-1",
        retailer_id="walmart_us",
        retailer_product_id="test-product",
        title="Fresh Ground Beef",
        brand=None,
        price=Decimal("8.97"),
        currency="USD",
        zipcode="72712",
        store_number="100",
        latitude=36.37,
        longitude=-94.2,
        in_stock=True,
        product_url="https://example.com/ground-beef",
        image_url=None,
        collected_at=None,
        raw={},
    )
    search_classified = classifier.classify(offer)

    enriched = complete_attributes_from_pdp(
        search_classified,
        {
            "name": "All Natural 80% Lean / 20% Fat Ground Beef, 2.25 lb Tray",
            "description": "Fresh family-size tray",
            "physical_properties": {"weight": "2.25 lb"},
        },
        classifier=classifier,
        pack=pack,
    )

    assert enriched.offer.price == Decimal("8.97")
    assert enriched.offer.title == "Fresh Ground Beef"
    assert enriched.attributes["lean_pct"] == 80
    assert enriched.attributes["fat_pct"] == 20
    assert enriched.attributes["weight_lb"] == 2.25
    assert enriched.attributes["_attribute_provenance"]["lean_pct"] == "pdp"


def test_missing_claims_remain_unknown_and_pdp_can_resolve_them() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_fluid_milk")
    classifier = OfferClassifier(pack)
    offer = NormalizedOffer(
        offer_id="milk-1",
        retailer_id="walmart_us",
        retailer_product_id="milk-product",
        title="Whole Milk, 1 Gallon",
        brand=None,
        price=Decimal("3.97"),
        currency="USD",
        zipcode="72712",
        store_number="100",
        latitude=36.37,
        longitude=-94.2,
        in_stock=True,
        product_url="https://example.com/milk-product",
        image_url=None,
        collected_at=None,
        raw={},
    )

    search_classified = classifier.classify(offer)
    assert search_classified.attributes["organic"] is None
    assert search_classified.attributes["lactose_free"] is None

    enriched = complete_attributes_from_pdp(
        search_classified,
        {
            "name": "Organic Lactose Free Whole Milk, 1 Gallon",
            "description": "USDA organic lactose-free whole milk",
        },
        classifier=classifier,
        pack=pack,
    )

    assert enriched.attributes["organic"] is True
    assert enriched.attributes["lactose_free"] is True
    assert enriched.attributes["_attribute_provenance"]["organic"] == "pdp"
    assert enriched.attributes["_attribute_provenance"]["lactose_free"] == "pdp"
