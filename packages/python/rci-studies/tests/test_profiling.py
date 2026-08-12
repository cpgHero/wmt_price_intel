from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from rci_retailer_packs import GovernedBrandResolver
from rci_studies import (
    DiscoveryObservation,
    canonical_checksum,
    initial_query_plan,
    profile_products,
    safe_product_pack_id,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def _observation(
    *,
    product_id: str,
    title: str,
    brand: str | None,
    price: str,
    store: str,
    zipcode: str,
) -> DiscoveryObservation:
    return DiscoveryObservation(
        retailer_id="walmart_us",
        retailer_product_id=product_id,
        title=title,
        brand=brand,
        price=Decimal(price),
        zipcode=zipcode,
        store_number=store,
        url=f"https://www.walmart.com/ip/{product_id}",
        image_url=None,
        source_artifact_id=f"artifact-{store}",
        identifiers={"product_id": product_id},
        fulfillment_type="pickup",
    )


def test_initial_query_plan_is_conservative_editable_and_singular_aware() -> None:
    plan = initial_query_plan(
        "Fresh shell eggs sold by the dozen.",
        known_inclusions=["fresh shell eggs"],
        known_exclusions=["chocolate eggs"],
    )

    assert plan["keyword"] == "fresh shell eggs"
    assert {"egg", "eggs"}.issubset(plan["target_terms"])
    assert plan["source"] == "deterministic"
    assert len(canonical_checksum(plan)) == 64


def test_profile_deduplicates_products_and_keeps_one_context_per_price_state() -> None:
    plan = initial_query_plan(
        "Fresh milk",
        known_inclusions=["milk"],
        known_exclusions=["chocolate milk"],
    )
    observations = [
        _observation(
            product_id="100",
            title="Great Value Whole Milk, 1 Gallon",
            brand="Great Value",
            price="3.25",
            store="1",
            zipcode="72712",
        ),
        _observation(
            product_id="100",
            title="Great Value Whole Milk, 1 Gallon",
            brand="Great Value",
            price="3.25",
            store="2",
            zipcode="72713",
        ),
        _observation(
            product_id="100",
            title="Great Value Whole Milk, 1 Gallon",
            brand="Great Value",
            price="3.45",
            store="3",
            zipcode="72714",
        ),
        _observation(
            product_id="200",
            title="Chocolate Milk Candy Bar",
            brand="Unknown Brand",
            price="1.25",
            store="1",
            zipcode="72712",
        ),
    ]

    profile = profile_products(
        observations,
        query_plan=plan,
        brand_resolver=GovernedBrandResolver.from_repository(REPOSITORY_ROOT),
    )

    assert profile.summary["raw_observations"] == 4
    assert profile.summary["unique_products"] == 2
    admitted = next(row for row in profile.products if row.retailer_product_id == "100")
    excluded = next(row for row in profile.products if row.retailer_product_id == "200")
    assert admitted.admission_status == "provisionally_admitted"
    assert admitted.observation_count == 3
    assert admitted.store_count == 3
    assert len(admitted.price_contexts) == 2
    assert profile.summary["price_variant_contexts"] == 1
    assert profile.summary["pdp_contexts"] == 2
    assert admitted.brand_resolution["strict_private_label"] is True
    assert excluded.admission_status == "excluded"
    assert "chocolate milk" in excluded.admission_reason


def test_unknown_brand_fails_closed_and_enters_profile_review_count() -> None:
    profile = profile_products(
        [
            _observation(
                product_id="300",
                title="Local Dairy Whole Milk, 1 Gallon",
                brand="A New Local Dairy",
                price="4.10",
                store="1",
                zipcode="72712",
            )
        ],
        query_plan=initial_query_plan("Fresh milk", known_inclusions=["milk"]),
        brand_resolver=GovernedBrandResolver.from_repository(REPOSITORY_ROOT),
    )

    assert profile.summary["unknown_brands"] == 1
    assert profile.products[0].brand_resolution["status"] == "unresolved"
    assert profile.products[0].brand_resolution["strict_private_label"] is False


def test_scope_terms_are_token_aware_and_match_reviewed_exclusion_concepts() -> None:
    plan = initial_query_plan(
        "Fresh strawberries",
        known_inclusions=["strawberries"],
        known_exclusions=[
            "chocolate-dipped strawberries",
            "dried or freeze-dried strawberries",
            "frozen strawberries",
            "shelf-stable strawberries",
            "strawberry bowls",
            "strawberry cups",
        ],
    )
    observations = [
        _observation(
            product_id="fresh",
            title="Fresh Strawberries, 1 lb Container",
            brand=None,
            price="2.46",
            store="1",
            zipcode="72712",
        ),
        _observation(
            product_id="frozen",
            title="Great Value Organic Whole Strawberries, 10 oz (Frozen)",
            brand="Great Value",
            price="2.64",
            store="1",
            zipcode="72712",
        ),
        _observation(
            product_id="dried",
            title="Simply Nature Freeze-Dried Strawberries, 1.2 oz",
            brand="Simply Nature",
            price="8.99",
            store="1",
            zipcode="72712",
        ),
        _observation(
            product_id="unrelated",
            title="Strawberry Plant Stakes",
            brand=None,
            price="4.99",
            store="1",
            zipcode="72712",
        ),
        _observation(
            product_id="dipped",
            title="Chocolate Hand-Dipped Strawberries",
            brand=None,
            price="8.99",
            store="1",
            zipcode="72712",
        ),
        _observation(
            product_id="cup",
            title="Strawberry & Kiwi Cup",
            brand=None,
            price="4.00",
            store="1",
            zipcode="72712",
        ),
        _observation(
            product_id="shelf-stable",
            title="ReadyWise Sliced Strawberries Whole Shelf-Stable",
            brand=None,
            price="31.99",
            store="1",
            zipcode="72712",
        ),
    ]

    profile = profile_products(
        observations,
        query_plan=plan,
        brand_resolver=GovernedBrandResolver.from_repository(REPOSITORY_ROOT),
    )

    statuses = {row.retailer_product_id: row.admission_status for row in profile.products}
    assert statuses == {
        "cup": "excluded",
        "dried": "excluded",
        "dipped": "excluded",
        "fresh": "provisionally_admitted",
        "frozen": "excluded",
        "shelf-stable": "excluded",
        "unrelated": "provisionally_admitted",
    }


def test_target_matching_does_not_treat_partial_words_as_category_evidence() -> None:
    profile = profile_products(
        [
            _observation(
                product_id="eggplant",
                title="Fresh Eggplant",
                brand=None,
                price="1.25",
                store="1",
                zipcode="72712",
            )
        ],
        query_plan=initial_query_plan("Fresh shell eggs", known_inclusions=["eggs"]),
        brand_resolver=GovernedBrandResolver.from_repository(REPOSITORY_ROOT),
    )

    assert profile.products[0].admission_status == "review_required"


def test_product_pack_id_is_generic_and_category_agnostic() -> None:
    assert safe_product_pack_id("Fresh Local Fluid Milk Discovery") == (
        "fresh_local_fluid_milk_discovery"
    )
