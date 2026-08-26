from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from rci_analytics.classification import OfferClassifier
from rci_analytics.models import NormalizedOffer
from rci_analytics.pdp_attributes import complete_attributes_from_pdp, product_context_index
from rci_analytics.product_pack import ProductPackLoader
from rci_retailer_packs import GovernedBrandResolver, GovernedSellerResolver

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
            "image_url": "https://example.com/front.jpg",
            "image_urls": [
                "https://example.com/front.jpg",
                "https://example.com/label.jpg",
            ],
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
    assert enriched.attributes["_pdp_evidence"]["image_urls"] == [
        "https://example.com/front.jpg",
        "https://example.com/label.jpg",
    ]


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


def test_structured_pdp_fields_complete_product_pack_raw_attribute_sources() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("vitamins_supplements")
    classifier = OfferClassifier(pack)
    offer = NormalizedOffer(
        offer_id="vitamin-1",
        retailer_id="walmart_us",
        retailer_product_id="6139509340",
        title="Spring Valley Vitamin C with Rose Hips, 500 mg, 100 Count Tablets",
        brand="Spring Valley",
        price=Decimal("4.88"),
        currency="USD",
        zipcode="72712",
        store_number="100",
        latitude=36.37,
        longitude=-94.2,
        in_stock=True,
        product_url="https://example.com/vitamin-c",
        image_url=None,
        collected_at=None,
        raw={},
    )
    search_classified = classifier.classify(offer)
    assert search_classified.attributes["active_ingredient"] == "vitamin_c_rose_hips"

    enriched = complete_attributes_from_pdp(
        search_classified,
        {
            "name": offer.title,
            "specification": {"primary_ingredient": "Vitamin C"},
        },
        classifier=classifier,
        pack=pack,
    )

    assert enriched.attributes["active_ingredient"] == "vitamin_c_rose_hips"
    assert enriched.attributes["_attribute_provenance"]["active_ingredient"] == "search"


def test_pdp_category_breadcrumb_resolves_national_brand_without_private_label_inference() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("vitamins_supplements")
    classifier = OfferClassifier(pack, GovernedBrandResolver.from_repository(REPOSITORY_ROOT))
    offer = NormalizedOffer(
        offer_id="meijer-vitamin-c",
        retailer_id="meijer_us",
        retailer_product_id="3160401485",
        title="Nature Made Vitamin C 500 mg Tablets, 100 Count",
        brand=None,
        price=Decimal("8.49"),
        currency="USD",
        zipcode="43219",
        store_number="58",
        latitude=40.0,
        longitude=-83.0,
        in_stock=True,
        product_url="https://www.meijer.com/product/3160401485",
        image_url=None,
        collected_at=None,
        raw={},
    )

    enriched = complete_attributes_from_pdp(
        classifier.classify(offer),
        {
            "name": offer.title,
            "brand": "Nature Made Nutritional Products",
            "category_path": ["Meijer", offer.title],
            "description": "Nature Made Vitamin C for adults.",
        },
        classifier=classifier,
        pack=pack,
    )

    assert enriched.attributes["brand"] == "Nature Made"
    assert enriched.attributes["_brand_governance"]["status"] == "resolved"
    assert enriched.attributes["_brand_governance"]["canonical_brand_name"] == "Nature Made"
    assert enriched.attributes["_brand_governance"]["role"] == "national"


def test_vitamin_formulation_terms_do_not_collapse_to_one_shared_minor_ingredient() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("vitamins_supplements")
    classifier = OfferClassifier(pack)

    def classify(product_id: str, retailer_id: str, title: str) -> object:
        return classifier.classify(
            NormalizedOffer(
                offer_id=f"{retailer_id}:{product_id}",
                retailer_id=retailer_id,
                retailer_product_id=product_id,
                title=title,
                brand="Spring Valley" if retailer_id == "walmart_us" else "Nature Made",
                price=Decimal("9.99"),
                currency="USD",
                zipcode="43219",
                store_number="100",
                latitude=40.0,
                longitude=-83.0,
                in_stock=True,
                product_url=None,
                image_url=None,
                collected_at=None,
                raw={},
            )
        ).attributes["active_ingredient"]

    assert (
        classify(
            "15083853537",
            "walmart_us",
            "Spring Valley Advanced Formula Blood Sugar Support, 500 mcg Chromium",
        )
        == "blood_sugar_support_formula"
    )
    assert (
        classify(
            "94981479",
            "target_us",
            (
                "Nature Made Metabolyze Capsules, Chromium Picolinate, "
                "Green Tea Extract and Vitamin B12"
            ),
        )
        == "metabolyze_formula"
    )
    assert (
        classify(
            "6139509340",
            "walmart_us",
            "Spring Valley Vitamin C with Rose Hips 500 mg Tablets",
        )
        == "vitamin_c_rose_hips"
    )
    assert (
        classify(
            "93731917",
            "target_us",
            "Nature Made Vitamin C 500 mg Tablets",
        )
        == "vitamin_c"
    )


def test_pdp_warning_and_broad_age_eligibility_do_not_create_child_audience() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("vitamins_supplements")
    classifier = OfferClassifier(pack)
    offer = NormalizedOffer(
        offer_id="digestive-enzyme-1",
        retailer_id="walmart_us",
        retailer_product_id="770495984",
        title="Advanced Digestive Enzymes Vegetarian Capsules, 60 Count",
        brand="Spring Valley",
        price=Decimal("9.88"),
        currency="USD",
        zipcode="72712",
        store_number="100",
        latitude=36.37,
        longitude=-94.2,
        in_stock=True,
        product_url=None,
        image_url=None,
        collected_at=None,
        raw={},
    )

    enriched = complete_attributes_from_pdp(
        classifier.classify(offer),
        {
            "name": offer.title,
            "specification": {
                "age_group": "Adult, Senior, Teen",
                "product_warning": "Keep out of reach of children",
                "stop_use_indications": "Consult a doctor and keep out of reach of children",
            },
        },
        classifier=classifier,
        pack=pack,
    )

    assert enriched.attributes["life_stage"] == "General"
    assert enriched.attributes["_attribute_provenance"]["life_stage"] == "unresolved"


def test_pdp_can_complete_unresolved_governed_brand_without_changing_search_fact() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_fluid_milk")
    classifier = OfferClassifier(
        pack,
        GovernedBrandResolver.from_repository(REPOSITORY_ROOT),
    )
    offer = NormalizedOffer(
        offer_id="milk-brand-1",
        retailer_id="walmart_us",
        retailer_product_id="milk-brand-product",
        title="Whole Milk, 1 Gallon",
        brand=None,
        price=Decimal("3.97"),
        currency="USD",
        zipcode="72712",
        store_number="100",
        latitude=36.37,
        longitude=-94.2,
        in_stock=True,
        product_url="https://example.com/milk-brand-product",
        image_url=None,
        collected_at=None,
        raw={},
    )
    search_classified = classifier.classify(offer)
    assert search_classified.attributes["_brand_governance"]["status"] == "unresolved"

    enriched = complete_attributes_from_pdp(
        search_classified,
        {
            "name": "Great Value Whole Milk, 1 Gallon",
            "brand": "Great Value",
            "description": "Grade A whole milk",
        },
        classifier=classifier,
        pack=pack,
    )

    assert enriched.offer.price == Decimal("3.97")
    assert enriched.offer.store_number == "100"
    assert enriched.attributes["_brand_governance"]["canonical_brand_id"] == (
        "walmart__great_value"
    )
    assert enriched.attributes["_brand_governance"]["strict_private_label"] is True


def test_pdp_structured_brand_supersedes_unrelated_title_fallback() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("vitamins_supplements")
    classifier = OfferClassifier(
        pack,
        GovernedBrandResolver.from_repository(REPOSITORY_ROOT),
    )
    offer = NormalizedOffer(
        offer_id="amazon-black-seed-oil",
        retailer_id="amazon_us_same_day",
        retailer_product_id="B0C7NC3WNM",
        title="GuruNanda Black Seed Oil with Vitamin D3, K2 & E",
        brand=None,
        price=Decimal("18.99"),
        currency="USD",
        zipcode="72712",
        store_number=None,
        latitude=36.37,
        longitude=-94.2,
        in_stock=True,
        product_url=None,
        image_url=None,
        collected_at=None,
        raw={},
    )
    search_classified = classifier.classify(offer)
    assert search_classified.attributes["brand"] == "Seed"
    assert search_classified.attributes["_attribute_provenance"]["brand"] == "retailer_pack_title"

    enriched = complete_attributes_from_pdp(
        search_classified,
        {
            "name": offer.title,
            "brand": "GuruNanda",
        },
        classifier=classifier,
        pack=pack,
    )

    assert enriched.attributes["brand"] == "GuruNanda"
    assert enriched.attributes["_attribute_provenance"]["brand"] == "pdp_unclassified"
    assert enriched.attributes["_brand_governance"]["status"] == "unresolved"
    assert enriched.attributes["_brand_governance"]["observed_brand"] == "GuruNanda"


def test_pdp_seller_policy_excludes_known_third_party_but_retains_missing() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_shell_eggs")
    classifier = OfferClassifier(pack, GovernedBrandResolver.from_repository(REPOSITORY_ROOT))
    seller_resolver = GovernedSellerResolver.from_repository(REPOSITORY_ROOT)
    offer = NormalizedOffer(
        offer_id="egg-1",
        retailer_id="walmart_us",
        retailer_product_id="egg-product",
        title="Marketside Large Eggs, 12 Count",
        brand=None,
        price=Decimal("3.97"),
        currency="USD",
        zipcode="72712",
        store_number="100",
        latitude=36.37,
        longitude=-94.2,
        in_stock=True,
        product_url=None,
        image_url=None,
        collected_at=None,
        raw={},
    )
    classified = classifier.classify(offer)

    third_party = complete_attributes_from_pdp(
        classified,
        {"name": offer.title, "seller": "Food Service Direct"},
        classifier=classifier,
        pack=pack,
        seller_resolver=seller_resolver,
    )
    missing = complete_attributes_from_pdp(
        classified,
        {"name": offer.title, "seller": None},
        classifier=classifier,
        pack=pack,
        seller_resolver=seller_resolver,
    )

    assert third_party.in_scope is False
    assert third_party.metrics == {}
    assert third_party.attributes["_seller_governance"]["status"] == "excluded_third_party"
    assert missing.in_scope is True
    assert missing.attributes["_seller_governance"]["status"] == "seller_unverified"
    assert missing.attributes["_brand_governance"]["canonical_brand_name"] == "Marketside"
