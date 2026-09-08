from __future__ import annotations

import csv
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from rci_analytics.classification import FormulaEvaluator, OfferClassifier
from rci_analytics.normalization import (
    BooleanAliasValidationError,
    CanonicalOfferNormalizer,
    RetailerIdentityMap,
)
from rci_analytics.product_pack import ProductPackLoader

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture(scope="module")
def normalizer() -> CanonicalOfferNormalizer:
    return CanonicalOfferNormalizer(
        RetailerIdentityMap.from_catalog(REPOSITORY_ROOT / "config" / "retailer-catalog.json")
    )


@pytest.fixture(scope="module")
def classifier() -> OfferClassifier:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_strawberries")
    document = dict(pack.document)
    document.pop("retailer_overrides")
    return OfferClassifier(replace(pack, document=document))


@pytest.fixture(scope="module")
def configured_classifier() -> OfferClassifier:
    return OfferClassifier(ProductPackLoader(REPOSITORY_ROOT).load("fresh_strawberries"))


def _row(title: str, price: object = "$2.38", **values: object) -> dict[str, object]:
    return {
        "retailer_id": "walmart_us",
        "retailer_product_id": values.pop("product_id", "product-1"),
        "title": title,
        "price": price,
        "zipcode": values.pop("zipcode", "01234"),
        "store_number": values.pop("store_number", "0007"),
        "stock_availability": values.pop("stock", True),
        "url": values.pop("url", "https://retailer.test/product"),
        **values,
    }


def test_normalizes_aliases_prices_and_leading_zero_identifiers(
    normalizer: CanonicalOfferNormalizer,
) -> None:
    offer = normalizer.normalize(
        {
            "Retailer": "walmart.com",
            "Retailer Product Id": "000123",
            "Product Name": "Fresh Strawberries, 1 lb Container",
            "Price": "$2.38",
            "Zipcode": "617",
            "Retailer Store Id": "0007",
            "Latitude": "41.1",
            "Longitude": "-87.2",
        }
    )

    assert offer.retailer_id == "walmart_us"
    assert offer.retailer_product_id == "000123"
    assert offer.zipcode == "00617"
    assert offer.store_number == "0007"
    assert offer.price == Decimal("2.3800")


def test_normalizes_search_sponsorship_boolean(
    normalizer: CanonicalOfferNormalizer,
) -> None:
    sponsored = normalizer.normalize(_row("Fresh Strawberries, 1 lb", is_sponsored=True))
    organic = normalizer.normalize(
        _row("Fresh Strawberries, 2 lb", product_id="product-2", is_sponsored=False)
    )

    assert sponsored.is_sponsored is True
    assert organic.is_sponsored is False


@pytest.mark.parametrize(
    ("aliases", "expected"),
    [
        (
            {
                "in_stock": True,
                "stock_availability": "true",
                "available": "yes",
                "Stock Availability": "1",
            },
            True,
        ),
        (
            {
                "in_stock": "out of stock",
                "stock_availability": False,
                "available": "0",
            },
            False,
        ),
    ],
)
def test_consistent_availability_aliases_are_preserved(
    aliases: dict[str, object],
    expected: bool,
    normalizer: CanonicalOfferNormalizer,
) -> None:
    offer = normalizer.normalize({**_row("Fresh Strawberries, 1 lb"), **aliases})

    assert offer.in_stock is expected


def test_consistent_sponsorship_aliases_are_preserved(
    normalizer: CanonicalOfferNormalizer,
) -> None:
    offer = normalizer.normalize(
        _row(
            "Fresh Strawberries, 1 lb",
            is_sponsored=False,
            sponsored="false",
            **{"Is Sponsored": "no"},
        )
    )

    assert offer.is_sponsored is False


@pytest.mark.parametrize(
    "aliases",
    [
        {"stock_availability": True, "in_stock": False},
        {"stock_availability": "false", "available": "true"},
    ],
)
def test_rejects_conflicting_availability_aliases(
    aliases: dict[str, object],
    normalizer: CanonicalOfferNormalizer,
) -> None:
    with pytest.raises(ValueError, match="conflicting availability aliases"):
        normalizer.normalize({**_row("Fresh Strawberries, 1 lb"), **aliases})


@pytest.mark.parametrize(
    "aliases",
    [
        {"is_sponsored": True, "sponsored": False},
        {"is_sponsored": "false", "sponsored": "true"},
    ],
)
def test_rejects_conflicting_sponsorship_aliases(
    aliases: dict[str, object],
    normalizer: CanonicalOfferNormalizer,
) -> None:
    with pytest.raises(ValueError, match="conflicting sponsorship aliases"):
        normalizer.normalize(_row("Fresh Strawberries, 1 lb", **aliases))


@pytest.mark.parametrize(
    ("aliases", "semantic", "field"),
    [
        (
            {"stock_availability": True, "available": "sometimes"},
            "availability",
            "available",
        ),
        (
            {"is_sponsored": False, "sponsored": "promoted"},
            "sponsorship",
            "sponsored",
        ),
    ],
)
def test_rejects_malformed_boolean_alias_even_after_valid_alias(
    aliases: dict[str, object],
    semantic: str,
    field: str,
    normalizer: CanonicalOfferNormalizer,
) -> None:
    with pytest.raises(
        ValueError,
        match=rf"{semantic} alias '{field}' has invalid boolean value",
    ):
        normalizer.normalize({**_row("Fresh Strawberries, 1 lb"), **aliases})


def test_normalize_many_fails_closed_on_newer_conflicting_alias_row(
    normalizer: CanonicalOfferNormalizer,
) -> None:
    older_verified = _row(
        "Fresh Strawberries, 1 lb",
        product_id="same-product",
        collected_at="2026-08-07T06:00:00Z",
        is_sponsored=False,
    )
    newer_contradictory = {
        **older_verified,
        "collected_at": "2026-08-07T07:00:00Z",
        "in_stock": False,
    }

    with pytest.raises(BooleanAliasValidationError, match="conflicting availability aliases"):
        normalizer.normalize_many([older_verified, newer_contradictory])


def test_normalize_many_still_skips_unrelated_invalid_rows(
    normalizer: CanonicalOfferNormalizer,
) -> None:
    valid = _row("Fresh Strawberries, 1 lb", product_id="valid")
    missing_retailer = {**valid, "retailer_id": ""}

    assert [
        offer.retailer_product_id for offer in normalizer.normalize_many([missing_retailer, valid])
    ] == ["valid"]


def test_recovers_lossy_scientific_product_identifier_from_retailer_url(
    normalizer: CanonicalOfferNormalizer,
) -> None:
    offer = normalizer.normalize(
        {
            "Retailer": "shoprite.com",
            "Retailer Product Id": "8.15652E+11",
            "Product Name": "Nellie's Free Range Large Fresh Brown Eggs, 12 count",
            "Price": "5.49",
            "Zipcode": "07083",
            "Retailer Store Id": "262",
            "Url": ("https://www.shoprite.com/sm/pickup/rsid/447/product/id-00815652004180"),
        }
    )

    assert offer.retailer_product_id == "00815652004180"


def test_rejects_lossy_scientific_product_identifier_without_recovery_source(
    normalizer: CanonicalOfferNormalizer,
) -> None:
    with pytest.raises(ValueError, match="lossy scientific notation"):
        normalizer.normalize(
            {
                "Retailer": "shoprite.com",
                "Retailer Product Id": "8.15652E+11",
                "Product Name": "Fresh Eggs, 12 count",
                "Price": "5.49",
                "Zipcode": "07083",
            }
        )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-08-07T05:03:04.869637", "2026-08-07T05:03:04.869637Z"),
        ("2026-08-07T00:03:04-05:00", "2026-08-07T05:03:04Z"),
        ("1.786118963679E+12", "2026-08-07T16:09:23.679000Z"),
        ("not-a-timestamp", None),
    ],
)
def test_normalizes_iso_and_epoch_timestamps_to_utc(
    value: str,
    expected: str | None,
    normalizer: CanonicalOfferNormalizer,
) -> None:
    offer = normalizer.normalize(_row("Fresh Strawberries, 1 lb", Date=value))

    assert offer.collected_at == expected


@pytest.mark.parametrize(
    ("domain", "retailer_id"),
    [
        ("albertsons.com", "albertsons_us"),
        ("aldi.us", "aldi_us"),
        ("amazon.com", "amazon_us_same_day"),
        ("gianteagle.com", "giant_eagle_us"),
        ("heb.com", "heb_us"),
        ("kroger.com", "kroger_us"),
        ("meijer.com", "meijer_us"),
        ("safeway.com", "safeway_us"),
        ("samsclub.com", "sams_club_us"),
        ("shoprite.com", "shoprite_us"),
        ("target.com", "target_us"),
        ("traderjoes.com", "trader_joes_us"),
        ("walmart.com", "walmart_us"),
        ("wegmans.com", "wegmans_us"),
    ],
)
def test_consolidated_export_retailer_aliases_are_normalization_only(
    domain: str,
    retailer_id: str,
    normalizer: CanonicalOfferNormalizer,
) -> None:
    offer = normalizer.normalize({**_row("Fresh Eggs, 12 Count"), "retailer_id": domain})

    assert offer.retailer_id == retailer_id


def test_normalize_many_deduplicates_identical_canonical_observations(
    normalizer: CanonicalOfferNormalizer,
) -> None:
    row = _row("Fresh Strawberries, 1 lb Container", product_id="44391605")

    assert len(normalizer.normalize_many([row, dict(row)])) == 1


def test_normalize_many_preserves_same_offer_state_observed_at_different_times(
    normalizer: CanonicalOfferNormalizer,
) -> None:
    base = _row("Fresh Strawberries, 1 lb Container", product_id="44391605")
    older = {**base, "collected_at": "2026-08-07T06:00:00Z"}
    newer = {**base, "collected_at": "2026-08-07T07:00:00Z"}

    observations = normalizer.normalize_many([older, newer])

    assert len(observations) == 2
    assert observations[0].offer_id != observations[1].offer_id
    assert [row.collected_at for row in observations] == [
        "2026-08-07T06:00:00Z",
        "2026-08-07T07:00:00Z",
    ]


def test_offer_identity_preserves_distinct_availability_and_sponsorship_evidence(
    normalizer: CanonicalOfferNormalizer,
) -> None:
    base = _row("Fresh Strawberries, 1 lb Container", product_id="44391605")
    organic_in_stock = normalizer.normalize({**base, "is_sponsored": False})
    sponsored_in_stock = normalizer.normalize({**base, "is_sponsored": True})
    organic_out_of_stock = normalizer.normalize(
        {**base, "is_sponsored": False, "stock_availability": False}
    )

    assert (
        len(
            {
                organic_in_stock.offer_id,
                sponsored_in_stock.offer_id,
                organic_out_of_stock.offer_id,
            }
        )
        == 3
    )
    assert (
        len(
            normalizer.normalize_many(
                [
                    {**base, "is_sponsored": False},
                    {**base, "is_sponsored": True},
                    {**base, "is_sponsored": False, "stock_availability": False},
                ]
            )
        )
        == 3
    )


def test_classifies_scope_attributes_and_leaves_unproven_claims_unknown(
    normalizer: CanonicalOfferNormalizer, classifier: OfferClassifier
) -> None:
    conventional = classifier.classify(
        normalizer.normalize(_row("Fresh Conventional Standard Strawberries, 1 lb Container"))
    )
    organic = classifier.classify(
        normalizer.normalize(
            _row("Fresh USDA Organic Hydroponic Strawberries, 2 lb Container", "$6.66")
        )
    )

    assert conventional.in_scope
    assert conventional.attributes == {
        "weight_oz": 16.0,
        "organic": None,
        "form": "Fresh Whole",
        "specialty_claim": None,
        "count_each": None,
        "brand": None,
        "_attribute_provenance": {
            "weight_oz": "search",
            "organic": "unresolved",
            "form": "product_pack_constant",
            "specialty_claim": "unresolved",
            "count_each": "unresolved",
            "brand": "unresolved",
        },
    }
    assert conventional.metrics["price_per_lb"] == Decimal("2.3800")
    assert organic.attributes["weight_oz"] == 32.0
    assert organic.attributes["organic"] is True
    assert organic.attributes["specialty_claim"] == "Hydroponic"
    assert organic.metrics["price_per_lb"] == Decimal("3.3300")


def test_product_pack_must_explicitly_authorize_absence_as_default_evidence(
    normalizer: CanonicalOfferNormalizer,
) -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_strawberries")
    document = deepcopy(pack.document)
    document.pop("retailer_overrides")
    organic = next(row for row in document["attributes"] if row["name"] == "organic")
    organic["extraction_rules"][0]["absence_policy"] = "infer_default"
    configured = ProductPackLoader(REPOSITORY_ROOT).load_document(document)

    result = OfferClassifier(configured).classify(
        normalizer.normalize(_row("Fresh Strawberries, 1 lb Container"))
    )

    assert result.attributes["organic"] is False
    assert result.attributes["_attribute_provenance"]["organic"] == "product_pack_default"


@pytest.mark.parametrize(
    "title",
    [
        "Frozen Strawberries, 16 oz",
        "Freeze-Dried Strawberry Slices, 8 oz",
        "Strawberry Live Plants and Seeds",
        "Strawberry Fruit Snack Gummies",
        "Strawberry Juice Drink",
    ],
)
def test_product_pack_scope_exclusions_are_compiled_generically(
    title: str,
    normalizer: CanonicalOfferNormalizer,
    classifier: OfferClassifier,
) -> None:
    result = classifier.classify(normalizer.normalize(_row(title)))
    assert not result.in_scope
    assert result.scope_reason


def test_formula_evaluator_allows_arithmetic_but_not_code_execution() -> None:
    evaluator = FormulaEvaluator()
    assert evaluator.evaluate(
        "price * 16 / weight_oz",
        {"price": Decimal("4.00"), "weight_oz": Decimal("32")},
    ) == Decimal("2.00")
    assert (
        evaluator.evaluate(
            "__import__('os').system('false')",
            {"price": Decimal("4.00"), "weight_oz": Decimal("32")},
        )
        is None
    )


def test_retailer_catalog_override_is_generic_and_fail_closed(
    normalizer: CanonicalOfferNormalizer,
    configured_classifier: OfferClassifier,
) -> None:
    accepted = configured_classifier.classify(
        normalizer.normalize(
            _row(
                "Fresh Strawberries, package",
                product_id="44391605",
                url="https://retailer.test/no-weight-in-url",
            )
        )
    )
    unknown = configured_classifier.classify(
        normalizer.normalize(_row("Fresh Strawberries, 1 lb", product_id="unknown"))
    )

    assert accepted.in_scope
    assert accepted.attributes["weight_oz"] == 16
    assert accepted.attributes["organic"] is False
    assert not unknown.in_scope
    assert unknown.scope_reason == "retailer product is not in the configured allowlist"


def test_supplied_compact_rows_normalize_and_classify_deterministically(
    normalizer: CanonicalOfferNormalizer, configured_classifier: OfferClassifier
) -> None:
    rows: list[dict[str, object]] = []
    for path in sorted(
        (REPOSITORY_ROOT / "fixtures" / "golden" / "strawberries").glob("*.sample.csv")
    ):
        with path.open(newline="", encoding="utf-8-sig") as handle:
            rows.extend(dict(row) for row in csv.DictReader(handle))

    normalized = normalizer.normalize_many(rows)
    classified = configured_classifier.classify_many(normalized)

    assert len(rows) == len(normalized) == len(classified) == 1500
    # Stock metadata does not exclude otherwise qualifying positive-price Search rows.
    assert sum(item.in_scope for item in classified) == 182
    assert all("price_per_strawberry" not in item.metrics for item in classified)
