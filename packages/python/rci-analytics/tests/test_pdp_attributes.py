from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from rci_analytics.classification import OfferClassifier
from rci_analytics.models import NormalizedOffer
from rci_analytics.pdp_attributes import complete_attributes_from_pdp
from rci_analytics.product_pack import ProductPackLoader

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


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
