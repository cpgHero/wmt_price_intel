"""Versioned retailer semantics and conservative retailer-scoped brand resolution."""

from rci_retailer_packs.catalog import (
    BrandCandidateSuggestion,
    BrandDecisionOverride,
    BrandFoundation,
    BrandFoundationLoader,
    BrandResolution,
    FileRetailerPackCatalog,
    GovernedBrandResolver,
    RetailerPack,
    canonical_checksum,
    normalize_brand_name,
)

__all__ = [
    "BrandCandidateSuggestion",
    "BrandDecisionOverride",
    "BrandFoundation",
    "BrandFoundationLoader",
    "BrandResolution",
    "FileRetailerPackCatalog",
    "GovernedBrandResolver",
    "RetailerPack",
    "canonical_checksum",
    "normalize_brand_name",
]
