from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from rci_analytics.classification import OfferClassifier
from rci_analytics.matching import ComparisonEngine
from rci_analytics.normalization import CanonicalOfferNormalizer, RetailerIdentityMap
from rci_analytics.product_pack import ProductPackLoader

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
PACK_ORDER = (
    "fresh_strawberries",
    "fresh_shell_eggs",
    "fresh_fluid_milk",
    "fresh_bananas",
    "fresh_ground_beef",
)
CORE_SOURCE_ROOTS = (
    "apps/api/src",
    "apps/scheduler/src",
    "apps/worker/src",
    "apps/web/src",
    "packages/python/rci-analytics/src",
    "packages/python/rci-automation/src",
    "packages/python/rci-collections/src",
    "packages/python/rci-contracts/src",
    "packages/python/rci-core/src",
    "packages/python/rci-db/src",
    "packages/python/rci-locations/src",
    "packages/python/rci-providers/src",
    "packages/python/rci-results/src",
    "packages/typescript/contracts/src",
)
NON_EXECUTABLE_CONTENT_PATHS = {
    "apps/web/src/lib/platform-docs.ts",
}


@pytest.fixture(scope="module")
def normalizer() -> CanonicalOfferNormalizer:
    return CanonicalOfferNormalizer(
        RetailerIdentityMap.from_catalog(REPOSITORY_ROOT / "config" / "retailer-catalog.json")
    )


def _row(
    retailer_id: str,
    product_id: str,
    title: str,
    price: str,
    *,
    brand: str | None = None,
    zipcode: str = "01234",
) -> dict[str, object]:
    return {
        "retailer_id": retailer_id,
        "retailer_product_id": product_id,
        "title": title,
        "brand": brand,
        "price": price,
        "zipcode": zipcode,
        "stock_availability": True,
    }


def _pipeline(pack_id: str, normalizer: CanonicalOfferNormalizer, rows: list[dict[str, object]]):
    pack = ProductPackLoader(REPOSITORY_ROOT).load(pack_id)
    offers = OfferClassifier(pack).classify_many(normalizer.normalize_many(rows))
    return offers, ComparisonEngine(pack)


def test_product_packs_load_in_required_expansion_order() -> None:
    loader = ProductPackLoader(REPOSITORY_ROOT)
    assert tuple(loader.load(pack_id).id for pack_id in PACK_ORDER) == PACK_ORDER


@pytest.mark.parametrize(
    ("pack_id", "row", "expected_attributes", "metric", "expected_metric"),
    [
        (
            "fresh_shell_eggs",
            _row(
                "walmart_us",
                "egg-1",
                "Organic Cage-Free Grade AA Extra Large Brown Eggs, 18 Count",
                "5.40",
            ),
            {
                "count": 18.0,
                "size": "Extra Large",
                "shell_color": "Brown",
                "grade": "AA",
                "organic": True,
                "housing": "Cage-Free",
            },
            "price_per_dozen",
            Decimal("3.60"),
        ),
        (
            "fresh_fluid_milk",
            _row(
                "walmart_us",
                "milk-1",
                "Plain Organic Lactose-Free Ultra-Filtered Whole Milk, Half Gallon",
                "4.00",
            ),
            {
                "volume_oz": 64.0,
                "fat_type": "Whole",
                "flavor": None,
                "organic": True,
                "lactose_free": True,
                "ultrafiltered": True,
            },
            "price_per_gallon",
            Decimal("8.00"),
        ),
        (
            "fresh_bananas",
            _row(
                "walmart_us",
                "banana-1",
                "Organic Standard Yellow Banana Bunch (4-5 Count), 3 lb Package",
                "1.50",
            ),
            {
                "variety": None,
                "organic": True,
                "selling_unit": "fixed_weight_package",
                "weight_lb": 3.0,
                "count_min": 4.0,
                "count_max": 5.0,
            },
            "price_per_lb",
            Decimal("0.50"),
        ),
        (
            "fresh_ground_beef",
            _row(
                "walmart_us",
                "15136795",
                "73% Lean / 27% Fat Ground Beef, 5 lb Roll, Fresh, All Natural",
                "24.95",
            ),
            {
                "lean_pct": 73,
                "fat_pct": 27,
                "weight_lb": 5.0,
                "organic": False,
                "grass_fed": False,
                "premium_tier": "standard",
            },
            "price_per_lb",
            Decimal("4.99"),
        ),
    ],
)
def test_declarative_rules_classify_each_expansion_pack(
    pack_id: str,
    row: dict[str, object],
    expected_attributes: dict[str, object],
    metric: str,
    expected_metric: Decimal,
    normalizer: CanonicalOfferNormalizer,
) -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load(pack_id)
    result = OfferClassifier(pack).classify(normalizer.normalize(row))

    assert result.in_scope
    assert {name: result.attributes[name] for name in expected_attributes} == expected_attributes
    assert result.metrics[metric] == expected_metric


@pytest.mark.parametrize(
    ("pack_id", "title"),
    [
        ("fresh_shell_eggs", "Liquid Egg Whites, 16 oz"),
        (
            "fresh_shell_eggs",
            "Sunny Fresh Cage Free Selections Whole Eggs with Citric Acid, 2 Pound -- 12 per case.",
        ),
        ("fresh_fluid_milk", "Unsweetened Almond Milk, Half Gallon"),
        ("fresh_bananas", "Freeze-Dried Banana Chips"),
    ],
)
def test_scope_exclusions_remain_product_pack_data(
    pack_id: str,
    title: str,
    normalizer: CanonicalOfferNormalizer,
) -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load(pack_id)
    result = OfferClassifier(pack).classify(
        normalizer.normalize(_row("walmart_us", "noise", title, "2.00"))
    )
    assert not result.in_scope


@pytest.mark.parametrize(
    "title",
    [
        "Old Fashioned Egg Nog, 1 Quart",
        "Hard-Cooked Peeled Eggs, 6 Count",
        "Plant-Based Egg Replacer",
        "Frozen Sausage Egg Bites",
        "Vegetable Egg Rolls, 12 Count",
        "Decorative Easter Eggs",
        "Pickled Eggs in Brine",
        "Chicken and Egg Recipe Dog Food",
        "Egg Graphic Tank Top",
        "Egg Ornament",
        "The Perfect Egg Cookbook, Hardcover",
        "Egg Peptide Face Serum",
        "Signature Cafe Egg Salad",
        "Egg Lands Best Omelet Meat Lovers 2pk",
        "Just Crack an Egg Meat Lovers Scramble Kit",
        "Just Egg Folded, Plant-Based Egg, 4 Ct",
        "Wegmans Medium Egg Noodles Pasta",
        "Meijer Hot Dog Egg Buns, 8 ct",
        "Fresh Baked Egg Bagel, Single",
        "Zomick's Bread, Egg Challah",
        "Bacon, Egg & Cheddar Muffin",
        "Egg, Bacon, Potato & Cheese Burrito",
        "Burnbrae Farms Mini Frittatas made with Cage-Free Whole Eggs",
        "Holika Holika Smooth Egg Skin Cleansing Foam",
        "Egg Pore Blackhead Steam Balm Facial Cleanser",
        "Hrd Boiled Egg 2/12",
    ],
)
def test_egg_pack_rejects_known_search_noise_before_paid_enrichment(
    title: str,
    normalizer: CanonicalOfferNormalizer,
) -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_shell_eggs")
    result = OfferClassifier(pack).classify(
        normalizer.normalize(_row("target_us", "noise", title, "4.99"))
    )

    assert not result.in_scope
    assert result.scope_reason and result.scope_reason.startswith("excluded scope pattern:")


@pytest.mark.parametrize(
    "title",
    [
        "Grade A Large White Eggs, 12 Count",
        "Organic Cage-Free Brown Eggs, 18 Count",
        "Pasture-Raised Extra Large Shell Eggs, One Dozen",
        "Happy Egg Pasture Raised 12ct",
        "Eggland's Best Large Egg, 12 Count",
        "Wilcox Farms Free-Range 6 Individually Wrapped Eggs",
        "Happy Egg Co. Eggs Free Range Large, 12 Count",
    ],
)
def test_egg_scope_hardening_preserves_true_shell_eggs(
    title: str,
    normalizer: CanonicalOfferNormalizer,
) -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_shell_eggs")
    result = OfferClassifier(pack).classify(
        normalizer.normalize(_row("target_us", "egg", title, "4.99"))
    )

    assert result.in_scope


def test_curated_product_include_overrides_broad_scope_patterns(
    normalizer: CanonicalOfferNormalizer,
) -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_fluid_milk")
    document = dict(pack.document)
    document["retailer_overrides"] = {
        "walmart_us": {
            "catalog_policy": "rules_only",
            "products": {
                "creamline-1": {
                    "scope": "include",
                    "attributes": {
                        "volume_oz": 64,
                        "fat_type": "Whole",
                        "flavor": "Plain",
                        "organic": False,
                        "lactose_free": False,
                        "ultrafiltered": False,
                        "a2": False,
                        "grass_fed": False,
                        "brand": "Example Dairy",
                    },
                }
            },
        }
    }
    curated = type(pack)(
        id=pack.id,
        name=pack.name,
        version=pack.version,
        checksum=pack.checksum,
        document=document,
    )

    result = OfferClassifier(curated).classify(
        normalizer.normalize(
            _row(
                "walmart_us",
                "creamline-1",
                "Example Dairy Creamline Whole Milk, Half Gallon",
                "4.00",
            )
        )
    )

    assert result.in_scope
    assert result.attributes["volume_oz"] == 64


def test_egg_compatible_profile_supports_one_sided_unknown_wildcards(
    normalizer: CanonicalOfferNormalizer,
) -> None:
    rows = [
        _row(
            "walmart_us",
            "w",
            "Organic Grade A Large White Eggs, Cage-Free, 12 Count",
            "3.00",
        ),
        _row(
            "aldi_us",
            "a",
            "Organic Grade A Large Eggs, Cage-Free, 12 Count",
            "3.50",
        ),
    ]
    offers, engine = _pipeline("fresh_shell_eggs", normalizer, rows)

    matches = engine.compare(
        offers,
        benchmark_id="walmart_us",
        competitor_id="aldi_us",
        profile_id="compatible",
    )

    assert len(matches) == 1
    assert matches[0].attributes["count"] == 12.0
    assert matches[0].attributes["shell_color"] == "White"
    assert matches[0].winner == "benchmark_lower"


def test_egg_compatible_profile_does_not_wildcard_required_dimensions_or_two_unknowns(
    normalizer: CanonicalOfferNormalizer,
) -> None:
    missing_count = [
        _row("walmart_us", "w-count", "Grade A Large White Eggs, Cage-Free", "3.00"),
        _row(
            "aldi_us",
            "a-count",
            "Grade A Large White Eggs, Cage-Free, 12 Count",
            "3.50",
        ),
    ]
    both_unknown_grade = [
        _row("walmart_us", "w-grade", "Large White Eggs, Cage-Free, 12 Count", "3.00"),
        _row("aldi_us", "a-grade", "Large Eggs, Cage-Free, 12 Count", "3.50"),
    ]

    for rows in (missing_count, both_unknown_grade):
        offers, engine = _pipeline("fresh_shell_eggs", normalizer, rows)
        assert (
            engine.compare(
                offers,
                benchmark_id="walmart_us",
                competitor_id="aldi_us",
                profile_id="compatible",
            )
            == []
        )


def test_milk_brand_policies_are_enforced_generically(
    normalizer: CanonicalOfferNormalizer,
) -> None:
    rows = [
        _row("walmart_us", "w-pl", "Great Value Whole Milk, 1 Gallon", "3.00", brand="Great Value"),
        _row(
            "aldi_us", "a-pl", "Friendly Farms Whole Milk, 1 Gallon", "3.50", brand="Friendly Farms"
        ),
        _row("walmart_us", "w-nb", "Lactaid Whole Milk, 1 Gallon", "5.00", brand="Lactaid"),
        _row("aldi_us", "a-nb", "Lactaid Whole Milk, 1 Gallon", "5.25", brand="Lactaid"),
    ]
    offers, engine = _pipeline("fresh_fluid_milk", normalizer, rows)
    explicit_identity = {
        "flavor": "Plain",
        "organic": False,
        "lactose_free": False,
        "ultrafiltered": False,
        "a2": False,
        "grass_fed": False,
        "omega_3_dha": False,
        "kids": False,
        "protein_fortified": False,
    }
    offers = [replace(item, attributes={**item.attributes, **explicit_identity}) for item in offers]

    same_brand = engine.compare(
        offers,
        benchmark_id="walmart_us",
        competitor_id="aldi_us",
        profile_id="same_brand_exact",
    )
    private_label = engine.compare(
        offers,
        benchmark_id="walmart_us",
        competitor_id="aldi_us",
        profile_id="private_label",
    )

    assert len(same_brand) == 1
    assert same_brand[0].benchmark_offer_id == offers[2].offer.offer_id
    assert len(private_label) == 1
    assert private_label[0].benchmark_offer_id == offers[0].offer.offer_id


def test_banana_profiles_choose_explicit_category_neutral_metrics(
    normalizer: CanonicalOfferNormalizer,
) -> None:
    rows = [
        _row(
            "walmart_us",
            "w-weight",
            "Conventional Standard Yellow Bananas, 3 lb Package",
            "1.50",
        ),
        _row(
            "aldi_us",
            "a-weight",
            "Conventional Standard Yellow Bananas, 3 lb Package",
            "1.20",
        ),
        _row(
            "walmart_us",
            "w-count",
            "Conventional Standard Yellow Banana Bunch (4-5 Count)",
            "1.00",
        ),
        _row(
            "aldi_us",
            "a-count",
            "Conventional Standard Yellow Banana Bunch (5-6 Count)",
            "0.90",
        ),
    ]
    offers, engine = _pipeline("fresh_bananas", normalizer, rows)
    offers = [
        replace(
            item,
            attributes={**item.attributes, "variety": "Standard Yellow", "organic": False},
        )
        for item in offers
    ]

    weight = engine.compare(
        offers,
        benchmark_id="walmart_us",
        competitor_id="aldi_us",
        profile_id="weight_normalized",
    )
    count = engine.compare(
        offers,
        benchmark_id="walmart_us",
        competitor_id="aldi_us",
        profile_id="count_compatible",
    )

    assert len(weight) == len(count) == 1
    assert weight[0].comparison_metric == "price_per_lb"
    assert weight[0].benchmark_value == Decimal("0.50")
    assert count[0].comparison_metric == "midpoint_price_per_each"
    assert count[0].benchmark_value == Decimal("1") / Decimal("4.5")


def test_profiles_support_asymmetric_retailer_role_constraints(
    normalizer: CanonicalOfferNormalizer,
) -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_bananas")
    document = dict(pack.document)
    document["matching_profiles"] = [
        {
            "id": "each_to_bunch",
            "label": "Each-to-bunch midpoint",
            "geography": "exact_zip",
            "dimensions": ["variety", "organic"],
            "benchmark_attribute_constraints": {"selling_unit": ["each"]},
            "competitor_attribute_constraints": {"selling_unit": ["bunch"]},
            "brand_policy": "ignore_brand",
            "unknown_policy": "reject",
            "price_selection": "lowest_positive",
            "comparison_metric": "midpoint_price_per_each",
        }
    ]
    configured = type(pack)(
        id=pack.id,
        name=pack.name,
        version=pack.version,
        checksum=pack.checksum,
        document=document,
    )
    rows = [
        _row(
            "walmart_us",
            "w-each",
            "Conventional Standard Yellow Banana, 1 Each",
            "0.20",
        ),
        _row(
            "aldi_us",
            "a-bunch",
            "Conventional Standard Yellow Banana Bunch (4-5 Count)",
            "0.90",
        ),
        _row(
            "aldi_us",
            "a-each",
            "Conventional Standard Yellow Banana, 1 Each",
            "0.15",
        ),
    ]
    offers = OfferClassifier(configured).classify_many(normalizer.normalize_many(rows))
    offers = [
        replace(
            item,
            attributes={**item.attributes, "variety": "Standard Yellow", "organic": False},
        )
        for item in offers
    ]

    matches = ComparisonEngine(configured).compare(
        offers,
        benchmark_id="walmart_us",
        competitor_id="aldi_us",
        profile_id="each_to_bunch",
    )

    assert len(matches) == 1
    assert matches[0].competitor_value == Decimal("0.90") / Decimal("4.5")


def test_core_engine_contains_no_product_specific_code_paths() -> None:
    prohibited = (
        "strawberr",
        "egg",
        "milk",
        "banana",
        "plantain",
        "ground_beef",
        "ground beef",
    )
    findings = {
        str(path.relative_to(REPOSITORY_ROOT)): token
        for relative_root in CORE_SOURCE_ROOTS
        for path in (REPOSITORY_ROOT / relative_root).rglob("*")
        if path.suffix in {".py", ".ts", ".tsx"}
        and ".test." not in path.name
        and str(path.relative_to(REPOSITORY_ROOT)) not in NON_EXECUTABLE_CONTENT_PATHS
        for token in prohibited
        if token in path.read_text(encoding="utf-8").casefold()
    }
    assert findings == {}
