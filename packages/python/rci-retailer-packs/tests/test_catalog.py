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
