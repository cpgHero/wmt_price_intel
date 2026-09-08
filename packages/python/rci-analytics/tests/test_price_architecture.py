from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest

from rci_analytics import (
    PriceArchitectureMatrixProjector,
    PriceArchitectureRetailerInput,
    PriceLocation,
    ProductLocationObservation,
)
from rci_contracts import ContractError, validate_instance

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def _observation(
    retailer_id: str,
    product_id: str,
    price: float,
    store_number: str,
    *,
    name: str | None = None,
    in_stock: bool | None = True,
    is_sponsored: bool | None = False,
) -> ProductLocationObservation:
    return ProductLocationObservation(
        observation_id=f"{retailer_id}:{product_id}:{store_number}",
        retailer_id=retailer_id,
        retailer_name={
            "walmart_us": "Walmart (US)",
            "aldi_us": "ALDI",
            "target_us": "Target",
        }[retailer_id],
        product_id=product_id,
        product_name=name or f"Product {product_id}",
        brand="Great Value" if retailer_id == "walmart_us" else None,
        brand_type="private_label",
        brand_origin="retailer_pack",
        brand_status="governed",
        image_url=f"https://example.com/{product_id}.jpg",
        product_url=f"https://example.com/{product_id}",
        identity_authority="pdp",
        location=PriceLocation(
            scope_key=f"{retailer_id}:store:{store_number}",
            kind="store",
            store_number=store_number,
            store_name=f"Store {store_number}",
            zipcode="72712",
            city="Bentonville",
            state="AR",
            country="USA",
            latitude=36.37,
            longitude=-94.21,
        ),
        package_price=price,
        regular_price=price,
        discounted_price=None,
        is_sponsored=is_sponsored,
        observed_at="2026-08-19T12:00:00Z",
        offer_id=f"offer:{retailer_id}:{product_id}:{store_number}",
        metric_values=(),
        in_stock=in_stock,
    )


def _retailer(
    retailer_id: str,
    observations: list[ProductLocationObservation],
    eligible_stores: int = 4,
) -> PriceArchitectureRetailerInput:
    return PriceArchitectureRetailerInput(
        retailer_id=retailer_id,
        retailer_name=observations[0].retailer_name,
        location_dimension="store",
        eligible_scope_keys=frozenset(
            f"{retailer_id}:store:{index}" for index in range(1, eligible_stores + 1)
        ),
        observations=tuple(observations),
        population_checksum=(retailer_id[0] * 64),
    )


def _matrix(
    *, mode: str = "benchmark_anchored", increment: float = 0.5, brand: str | None = None
) -> dict:
    walmart = _retailer(
        "walmart_us",
        [
            _observation("walmart_us", "w1", 2.0, "1"),
            _observation("walmart_us", "w1", 2.0, "2"),
            _observation("walmart_us", "w2", 4.0, "1"),
            _observation("walmart_us", "w3", 4.0, "2"),
            _observation("walmart_us", "w4", 6.0, "3"),
        ],
    )
    aldi = _retailer(
        "aldi_us",
        [
            _observation("aldi_us", "a1", 2.5, "1"),
            _observation("aldi_us", "a2", 3.0, "1"),
            _observation("aldi_us", "a2", 5.0, "2"),
            _observation("aldi_us", "a3", 6.5, "3"),
        ],
    )
    target = _retailer(
        "target_us",
        [
            _observation("target_us", "t1", 4.5, "1"),
            _observation("target_us", "t2", 4.6, "1"),
            _observation("target_us", "t2", 4.6, "2"),
        ],
    )
    return PriceArchitectureMatrixProjector().build(
        analysis_id="architecture-test",
        generated_at=datetime.now(UTC).isoformat(),
        product_pack={"id": "fresh_shell_eggs", "name": "Fresh shell eggs", "version": "1.0.0"},
        anchor_retailer_id="walmart_us",
        retailers=[walmart, aldi, target],
        mode=mode,  # type: ignore[arg-type]
        fixed_increment=increment,
        brand=brand,
    )


def test_benchmark_rungs_use_distinct_product_medians_and_true_midpoints() -> None:
    matrix = _matrix()

    validate_instance(
        REPOSITORY_ROOT,
        "price-architecture-matrix.schema.json",
        matrix,
        label="price architecture matrix",
    )
    assert matrix["summary"]["anchor_skus"] == 4
    assert matrix["summary"]["anchor_price_points"] == 3
    assert [(rung["lower_bound"], rung["upper_bound"]) for rung in matrix["rungs"]] == [
        (None, 3.0),
        (3.0, 5.0),
        (5.0, None),
    ]
    assert [rung["rank"] for rung in matrix["rungs"]] == [1, 2, 3]


@pytest.mark.parametrize(
    "field",
    [
        "verified_available_locations",
        "search_observed_locations",
        "search_observed_skus",
    ],
)
def test_matrix_contract_requires_explicit_retailer_evidence_counts(field: str) -> None:
    matrix = deepcopy(_matrix())
    del matrix["retailers"][0][field]

    with pytest.raises(ContractError):
        validate_instance(
            REPOSITORY_ROOT,
            "price-architecture-matrix.schema.json",
            matrix,
            label=f"matrix missing {field}",
        )


def test_matrix_contract_rejects_available_status_without_verified_breadth() -> None:
    matrix = deepcopy(_matrix())
    matrix["retailers"][0]["verified_available_locations"] = 0
    matrix["retailers"][0]["observed_locations"] = 0

    with pytest.raises(ContractError):
        validate_instance(
            REPOSITORY_ROOT,
            "price-architecture-matrix.schema.json",
            matrix,
            label="available matrix retailer without verified breadth",
        )


def test_boundary_price_enters_the_higher_anchor_rung_and_skus_are_unique() -> None:
    matrix = _matrix()
    middle = next(rung for rung in matrix["rungs"] if rung["lower_bound"] == 3.0)
    aldi_cell = next(cell for cell in middle["cells"] if cell["retailer_id"] == "aldi_us")

    assert [product["product_id"] for product in aldi_cell["products"]] == ["a2"]
    assert aldi_cell["products"][0]["median_price"] == 4.0
    assigned_aldi_ids = [
        product["product_id"]
        for rung in matrix["rungs"]
        for cell in rung["cells"]
        if cell["retailer_id"] == "aldi_us"
        for product in cell["products"]
    ]
    assert sorted(assigned_aldi_ids) == ["a1", "a2", "a3"]


def test_store_coverage_is_union_of_distinct_locations_not_product_sum() -> None:
    matrix = _matrix()
    middle = next(rung for rung in matrix["rungs"] if rung["lower_bound"] == 3.0)
    walmart_cell = next(cell for cell in middle["cells"] if cell["retailer_id"] == "walmart_us")

    assert walmart_cell["sku_count"] == 2
    assert walmart_cell["store_coverage"] == 0.5
    assert walmart_cell["assortment_share"] == 0.5
    for retailer_id in ("walmart_us", "aldi_us", "target_us"):
        shares = [
            cell["assortment_share"]
            for rung in matrix["rungs"]
            for cell in rung["cells"]
            if cell["retailer_id"] == retailer_id
        ]
        assert sum(float(value or 0) for value in shares) == pytest.approx(1, abs=0.0001)


def test_products_within_each_rung_are_materialized_by_verified_store_count() -> None:
    matrix = _matrix()
    middle = next(rung for rung in matrix["rungs"] if rung["lower_bound"] == 3.0)
    target_cell = next(cell for cell in middle["cells"] if cell["retailer_id"] == "target_us")

    assert [product["product_id"] for product in target_cell["products"]] == ["t2", "t1"]
    assert [product["observed_locations"] for product in target_cell["products"]] == [2, 1]


def test_price_architecture_excludes_unverified_search_only_products() -> None:
    walmart = _retailer(
        "walmart_us",
        [
            _observation("walmart_us", "verified", 4.0, "1"),
            _observation("walmart_us", "verified-high", 5.0, "4"),
            _observation(
                "walmart_us",
                "sponsored",
                3.0,
                "2",
                in_stock=None,
                is_sponsored=True,
            ),
            _observation(
                "walmart_us",
                "out-of-stock",
                2.0,
                "3",
                in_stock=False,
                is_sponsored=True,
            ),
        ],
    )
    aldi = _retailer("aldi_us", [_observation("aldi_us", "verified-a", 4.5, "1")])

    matrix = PriceArchitectureMatrixProjector().build(
        analysis_id="verified-architecture-test",
        generated_at=datetime.now(UTC).isoformat(),
        product_pack={"id": "fresh_shell_eggs", "name": "Fresh shell eggs", "version": "1"},
        anchor_retailer_id="walmart_us",
        retailers=[walmart, aldi],
    )

    walmart_summary = next(row for row in matrix["retailers"] if row["id"] == "walmart_us")
    assert walmart_summary["sku_count"] == 2
    assert walmart_summary["observed_locations"] == 2
    assert walmart_summary["verified_available_locations"] == 2
    assert walmart_summary["search_observed_locations"] == 4
    assert walmart_summary["search_observed_skus"] == 4
    products = [
        product
        for rung in matrix["rungs"]
        for cell in rung["cells"]
        if cell["retailer_id"] == "walmart_us"
        for product in cell["products"]
    ]
    assert {row["product_id"] for row in products} == {"verified", "verified-high"}


def test_fixed_rungs_use_stable_intervals_with_benchmark_bounded_edges() -> None:
    matrix = _matrix(mode="fixed_range", increment=1.0)
    assert matrix["source"]["anchor_rule"] == "fixed $1.00 package-price bands"
    assert len(matrix["rungs"]) == 5
    assert matrix["rungs"][0]["lower_bound"] is None
    assert matrix["rungs"][0]["upper_bound"] == 3.0
    assert matrix["rungs"][-1]["lower_bound"] == 6.0
    assert matrix["rungs"][-1]["upper_bound"] is None
    top_aldi = next(
        cell for cell in matrix["rungs"][-1]["cells"] if cell["retailer_id"] == "aldi_us"
    )
    assert [product["product_id"] for product in top_aldi["products"]] == ["a3"]

    with pytest.raises(ValueError, match=r"0\.50 or 1\.00"):
        _matrix(mode="fixed_range", increment=0.25)


def test_brand_filter_preserves_walmart_rungs_and_filters_displayed_products() -> None:
    matrix = _matrix(brand="Great Value")

    assert len(matrix["rungs"]) == 3
    assert matrix["summary"]["anchor_price_points"] == 3
    assert matrix["summary"]["anchor_skus"] == 4
    assert matrix["summary"]["competitor_skus"] == 0
    assert matrix["filters"]["brand"] == "Great Value"
    assert matrix["brand_options"] == [
        {"name": "Great Value", "retailer_ids": ["walmart_us"], "product_count": 4}
    ]
    assert all(
        cell["sku_count"] == 0
        for rung in matrix["rungs"]
        for cell in rung["cells"]
        if cell["retailer_id"] != "walmart_us"
    )
    walmart = next(row for row in matrix["retailers"] if row["id"] == "walmart_us")
    aldi = next(row for row in matrix["retailers"] if row["id"] == "aldi_us")
    assert walmart["verified_available_locations"] == 3
    assert walmart["search_observed_locations"] == 3
    assert walmart["search_observed_skus"] == 4
    assert aldi["verified_available_locations"] == 0
    assert aldi["search_observed_locations"] == 0
    assert aldi["search_observed_skus"] == 0


def test_brand_without_walmart_products_keeps_reference_rungs_contract_valid() -> None:
    matrix = _matrix(brand="A competitor-only brand")

    validate_instance(
        REPOSITORY_ROOT,
        "price-architecture-matrix.schema.json",
        matrix,
        label="competitor-only brand price architecture matrix",
    )
    assert matrix["summary"]["anchor_price_points"] == 3
    assert matrix["summary"]["anchor_skus"] == 0
    assert len(matrix["rungs"]) == 3
