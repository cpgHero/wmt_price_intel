from __future__ import annotations

from pathlib import Path

from rci_retailer_packs import (
    BrandDecisionOverride,
    BrandFoundationLoader,
    FileRetailerPackCatalog,
    GovernedBrandResolver,
    canonical_checksum,
    normalize_brand_name,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def test_file_catalog_validates_every_versioned_retailer_pack() -> None:
    records = FileRetailerPackCatalog(REPOSITORY_ROOT).versions()

    assert {record.id for record in records} >= {
        "walmart_us",
        "aldi_us",
        "amazon_us_same_day",
    }
    assert all(record.checksum == canonical_checksum(record.document) for record in records)


def test_brand_foundation_preserves_complete_supplied_master_and_aliases() -> None:
    foundation = BrandFoundationLoader(REPOSITORY_ROOT).load(
        "private_label_brand_foundation", "1.0.0"
    )

    assert len(foundation.document["brands"]) == 172
    assert len(foundation.document["aliases"]) == 45
    assert foundation.document["retailer_id_map"]["walmart"] == "walmart_us"


def test_brand_universe_v2_reconciles_governed_private_and_external_sources() -> None:
    foundation = BrandFoundationLoader(REPOSITORY_ROOT).load("cpg_brand_foundation", "2.0.0")

    assert len(foundation.document["brands"]) == 224
    assert len(foundation.document["external_brands"]) == 483
    assert len(foundation.document["priority_brand_ids"]) == 185
    assert len(foundation.document["aliases"]) == 105
    assert foundation.document["alias_conflicts"] == [
        {
            "retailer_id": "whole_foods_market_us",
            "alias_normalized": "whole_foods_market_kitchen",
            "candidate_brand_ids": [
                "whole_foods_market__whole_foods_market",
                "whole_foods_market__whole_foods_market_kitchens",
            ],
            "resolution": "quarantined_unresolved",
        }
    ]


def test_brand_normalization_matches_governed_possessive_and_ampersand_keys() -> None:
    assert normalize_brand_name("Sam's Choice") == "sams_choice"
    assert normalize_brand_name("Good & Gather") == "good_and_gather"
    assert normalize_brand_name("CAFE Olé") == "cafe_ole"


def test_resolution_is_retailer_scoped_exact_and_fail_closed() -> None:
    resolver = GovernedBrandResolver.from_repository(REPOSITORY_ROOT)

    canonical = resolver.resolve("walmart_us", "Great Value")
    alias = resolver.resolve("walmart_us", "Better Goods")
    wrong_retailer = resolver.resolve("aldi_us", "Great Value")
    unknown = resolver.resolve("walmart_us", "Totally New Scraped Brand")

    assert canonical.canonical_brand_id == "walmart__great_value"
    assert canonical.strict_private_label is True
    assert alias.canonical_brand_id == "walmart__bettergoods"
    assert alias.resolution_method == "exact_alias"
    assert wrong_retailer.status == "unresolved"
    assert unknown.status == "unresolved"
    assert unknown.strict_private_label is False


def test_acquired_brand_is_not_strict_private_label() -> None:
    resolver = GovernedBrandResolver.from_repository(REPOSITORY_ROOT)
    acquired = next(
        row
        for row in resolver.foundation.document["brands"]
        if row["brand_class"] == "acquired_brand"
    )

    resolution = resolver.resolve(str(acquired["retailer_id"]), str(acquired["brand_name"]))

    assert resolution.brand_class == "acquired_brand"
    assert resolution.strict_private_label is False
    assert resolution.role == "unclassified"


def test_external_brands_resolve_globally_but_private_labels_remain_retailer_scoped() -> None:
    resolver = GovernedBrandResolver.from_repository(REPOSITORY_ROOT)

    walmart_fairlife = resolver.resolve("walmart_us", "fairlife", category="Fresh Fluid Milk")
    aldi_fairlife = resolver.resolve("aldi_us", "fairlife", category="Fresh Fluid Milk")
    aldi_great_value = resolver.resolve("aldi_us", "Great Value", category="Fresh Fluid Milk")

    assert walmart_fairlife.canonical_brand_id == "national__fairlife"
    assert walmart_fairlife.role == "national"
    assert walmart_fairlife.strict_private_label is False
    assert aldi_fairlife.canonical_brand_id == "national__fairlife"
    assert aldi_great_value.status == "unresolved"


def test_category_gated_global_alias_fails_closed_without_matching_category() -> None:
    resolver = GovernedBrandResolver.from_repository(REPOSITORY_ROOT)

    milk = resolver.resolve("walmart_us", "Borden Milk", category="Fresh Fluid Milk")
    beef = resolver.resolve("walmart_us", "Borden Milk", category="Fresh Ground Beef")

    assert milk.canonical_brand_id == "national__borden_dairy"
    assert beef.status == "unresolved"


def test_exclusive_without_retailer_ownership_is_not_strict_private_label() -> None:
    resolver = GovernedBrandResolver.from_repository(REPOSITORY_ROOT)
    exclusive = next(
        row
        for row in resolver.foundation.document["brands"]
        if row["ownership_model"] == "retailer_exclusive"
        and row["in_private_label_matching"] is True
    )

    resolution = resolver.resolve(str(exclusive["retailer_id"]), str(exclusive["brand_name"]))

    assert resolution.status == "resolved"
    assert resolution.strict_private_label is False
    assert resolution.role == "unclassified"


def test_governed_rejection_overrides_foundation_without_mutating_it() -> None:
    resolver = GovernedBrandResolver.from_repository(REPOSITORY_ROOT)
    governed = resolver.with_overrides(
        [
            BrandDecisionOverride(
                retailer_id="walmart_us",
                normalized_brand="great_value",
                display_brand="Great Value",
                role="private_label",
                decision="rejected",
            )
        ]
    )

    assert governed.resolve("walmart_us", "Great Value").strict_private_label is False
    assert resolver.resolve("walmart_us", "Great Value").strict_private_label is True
