from __future__ import annotations

import copy
import os
from uuid import uuid4

import pytest
from sqlalchemy import text

from rci_api.availability_release_audit import (
    audit_price_architecture_matrix,
    audit_price_monitoring_catalog,
)
from rci_api.report_publication import (
    _archive_publication_predecessors,
    _canonical_architecture_retailer_ids,
    _canonical_catalog_retailer_ids,
)
from rci_db import DatabaseProbe


def test_catalog_materialization_uses_canonical_retailer_ids_not_display_names() -> None:
    report = {
        "benchmark_retailer": "Walmart (US)",
        "competitors": ["ALDI", "Amazon Same Day"],
        "retailer_scope": {
            "benchmark": {"id": "walmart_us", "name": "Walmart (US)"},
            "competitors": [
                {"id": "aldi_us", "name": "ALDI"},
                {"id": "amazon_us_same_day", "name": "Amazon Same Day"},
            ],
        },
    }

    assert _canonical_catalog_retailer_ids(report) == [
        "aldi_us",
        "amazon_us_same_day",
        "walmart_us",
    ]


def test_catalog_materialization_excludes_governed_unavailable_retailers() -> None:
    report = {
        "scoreable_retailers": ["aldi_us"],
        "unavailable_retailers": ["wegmans_us"],
        "retailer_scope": {
            "benchmark": {"id": "walmart_us", "name": "Walmart (US)"},
            "competitors": [
                {"id": "aldi_us", "name": "ALDI"},
                {"id": "wegmans_us", "name": "Wegmans"},
            ],
        },
    }

    assert _canonical_catalog_retailer_ids(report) == ["aldi_us", "walmart_us"]
    assert _canonical_architecture_retailer_ids(report) == [
        "aldi_us",
        "walmart_us",
        "wegmans_us",
    ]


@pytest.mark.parametrize(
    "retailer_scope",
    [
        None,
        {},
        {"benchmark": {"id": "walmart_us"}},
        {"benchmark": {"id": ""}, "competitors": []},
        {"benchmark": {"id": "walmart_us"}, "competitors": [{"name": "ALDI"}]},
    ],
)
def test_catalog_materialization_fails_closed_without_canonical_scope(
    retailer_scope: object,
) -> None:
    with pytest.raises(ValueError, match="retailer"):
        _canonical_catalog_retailer_ids({"retailer_scope": retailer_scope})


def test_catalog_materialization_rejects_unconfigured_scoreable_retailer() -> None:
    report = {
        "scoreable_retailers": ["target_us"],
        "retailer_scope": {
            "benchmark": {"id": "walmart_us"},
            "competitors": [{"id": "aldi_us"}],
        },
    }

    with pytest.raises(ValueError, match="unconfigured IDs: target_us"):
        _canonical_catalog_retailer_ids(report)


_DISTRIBUTION_CONTRACT = {
    "version": "1.0.0",
    "basis": "positive_price_store_search_result",
    "grain": "retailer_product_id_x_store_id",
    "deduplication": "distinct_store_id_per_product",
    "price_rule": "price_gt_zero",
    "inventory_claim": False,
    "stock_status_used": False,
    "sponsorship_used": False,
}


def _price_stats(count: int, price: float = 4.0) -> dict[str, object]:
    if count == 0:
        return {
            "minimum": None,
            "q1": None,
            "observation_median": None,
            "product_equal_weighted_median": None,
            "q3": None,
            "maximum": None,
            "range": None,
            "modal_price": None,
            "modal_share": None,
            "observation_count": 0,
        }
    return {
        "minimum": price,
        "q1": price,
        "observation_median": price,
        "product_equal_weighted_median": price,
        "q3": price,
        "maximum": price,
        "range": 0.0,
        "modal_price": price,
        "modal_share": 1.0,
        "observation_count": count,
    }


def _catalog_location(scope_key: str, kind: str, store_number: str | None) -> dict[str, object]:
    return {
        "scope_key": scope_key,
        "kind": kind,
        "store_number": store_number,
        "products": 1,
        "distribution_store_count": int(kind == "store"),
        "service_area_presence_count": int(kind == "service_area"),
        "search_observed_products": 1,
        "observations": 1,
        "minimum_price": 4.0,
        "median_price": 4.0,
        "maximum_price": 4.0,
        "search_minimum_price": 4.0,
        "search_median_price": 4.0,
        "search_maximum_price": 4.0,
        "search_observed": True,
    }


def _certified_catalog() -> dict[str, object]:
    price_stats = _price_stats(3)
    product_id = "46942839"
    locations = [
        _catalog_location("walmart_us:store:3212", "store", "3212"),
        _catalog_location("walmart_us:store:3522", "store", "3522"),
        _catalog_location("walmart_us:service-area:90210", "service_area", None),
    ]
    return {
        "schema_version": "1.5.0",
        "distribution_contract": copy.deepcopy(_DISTRIBUTION_CONTRACT),
        "retailer": {"id": "walmart_us"},
        "source": {
            "authority": "Search",
            "grain": "retailer product x retailer location x latest observation in run",
            "observation_schema_version": "1.3.0",
            "source_rows": 3,
            "classified_rows": 3,
        },
        "filters": {"retailer_id": "walmart_us", "product_id": product_id},
        "summary": {
            "observed_locations": 3,
            "distribution_store_count": 2,
            "service_area_presence_count": 1,
            "expected_locations": 5,
            "coverage_rate": 0.6,
            "observed_products": 1,
            "eligible_observations": 3,
            "search_price_observations": 3,
            "usable_price_rate": 1.0,
            "price_consistency_rate": 1.0,
        },
        "presence": {
            "status": "observed_only",
            "observed_locations": 3,
            "distribution_store_count": 2,
            "service_area_presence_count": 1,
            "eligible_locations": 5,
            "not_observed_locations": 2,
            "confirmed_gap_locations": 0,
            "observed_presence_rate": 0.6,
        },
        "price_distribution": copy.deepcopy(price_stats),
        "search_price_distribution": copy.deepcopy(price_stats),
        "products": [
            {
                "product_id": product_id,
                "locations": 2,
                "states": 1,
                "cities": 3,
                "distribution_store_count": 2,
                "service_area_presence_count": 1,
                "search_observed_locations": 3,
                "search_observed_states": 1,
                "search_observed_cities": 3,
                "search_observed_zipcodes": 3,
                "price_stats": copy.deepcopy(price_stats),
                "search_price_stats": copy.deepcopy(price_stats),
                "presence": {
                    "observed_locations": 3,
                    "eligible_locations": 5,
                    "not_observed_locations": 2,
                    "observed_rate": 0.6,
                    "not_observed_rate": 0.4,
                },
                "sample_locations": [
                    {
                        "scope_key": location["scope_key"],
                        "store_number": location["store_number"],
                        "price": 4.0,
                        "search_observed": True,
                        "distribution_store_id": location["store_number"],
                    }
                    for location in locations
                ],
            }
        ],
        "brand_portfolio": [
            {
                "brand_type": "regional",
                "locations": 2,
                "distribution_store_count": 2,
                "service_area_presence_count": 1,
                "search_observed_locations": 3,
                "products": 1,
                "search_observed_products": 1,
                "observations": 3,
                "median_price": 4.0,
                "search_median_price": 4.0,
            }
        ],
        "geographies": [
            {
                "level": "state",
                "key": "CA",
                "locations": 2,
                "distribution_store_count": 2,
                "service_area_presence_count": 1,
                "search_observed_locations": 3,
                "products": 1,
                "search_observed_products": 1,
                "observations": 3,
                "price_stats": copy.deepcopy(price_stats),
                "search_price_stats": copy.deepcopy(price_stats),
            }
        ],
        "locations": locations,
        "location_display": {"returned": 3, "total": 3, "sampled": False},
        "quality": {"status": "ready"},
    }


def _architecture_product(
    product_id: str,
    price: float,
    *,
    stores: int = 2,
    service_areas: int = 0,
) -> dict[str, object]:
    return {
        "product_id": product_id,
        "median_price": price,
        "minimum_price": price,
        "maximum_price": price,
        "observed_locations": stores + service_areas,
        "distribution_store_count": stores,
        "service_area_presence_count": service_areas,
        "search_observed_locations": stores + service_areas,
        "seller_status": "verified_first_party",
    }


def _certified_architecture() -> dict[str, object]:
    benchmark_product = _architecture_product("46942839", 4.0, service_areas=1)
    competitor_product = _architecture_product("aldi-1", 3.5)
    return {
        "schema_version": "1.3.0",
        "distribution_contract": copy.deepcopy(_DISTRIBUTION_CONTRACT),
        "source": {
            "authority": "Search",
            "price_grain": (
                "retailer product x median positive Search-listed package price across "
                "observed Search locations"
            ),
            "distribution_rule": (
                "distinct store IDs where the product appears in store-level Search "
                "with price greater than zero; not an in-stock indicator"
            ),
            "assignment_rule": "price only; no product-match relationship is used",
        },
        "filters": {
            "anchor_retailer_id": "walmart_us",
            "mode": "benchmark_anchored",
            "brand": None,
        },
        "summary": {
            "anchor_price_points": 1,
            "rung_count": 1,
            "anchor_skus": 1,
            "competitor_skus": 1,
            "most_crowded_rung_id": "rung-1",
            "whitespace_rung_count": 0,
        },
        "retailers": [
            {
                "id": "walmart_us",
                "status": "available",
                "sku_count": 1,
                "eligible_locations": 5,
                "observed_locations": 3,
                "distribution_store_count": 2,
                "service_area_presence_count": 1,
                "search_observed_locations": 3,
                "search_observed_skus": 1,
                "verified_first_party_skus": 1,
                "seller_unverified_skus": 0,
                "seller_not_governed_skus": 0,
                "population_checksum": "w" * 64,
                "reason": None,
            },
            {
                "id": "aldi_us",
                "status": "available",
                "sku_count": 1,
                "eligible_locations": 5,
                "observed_locations": 2,
                "distribution_store_count": 2,
                "service_area_presence_count": 0,
                "search_observed_locations": 2,
                "search_observed_skus": 1,
                "verified_first_party_skus": 1,
                "seller_unverified_skus": 0,
                "seller_not_governed_skus": 0,
                "population_checksum": "a" * 64,
                "reason": None,
            },
        ],
        "rungs": [
            {
                "id": "rung-1",
                "rank": 1,
                "anchor_price": 4.0,
                "lower_bound": None,
                "upper_bound": None,
                "anchor_products": [benchmark_product],
                "competitor_sku_count": 1,
                "cells": [
                    {
                        "retailer_id": "walmart_us",
                        "sku_count": 1,
                        "assortment_share": 1.0,
                        "average_price": 4.0,
                        "price_density": None,
                        "products": [benchmark_product],
                    },
                    {
                        "retailer_id": "aldi_us",
                        "sku_count": 1,
                        "assortment_share": 1.0,
                        "average_price": 3.5,
                        "price_density": None,
                        "products": [competitor_product],
                    },
                ],
            }
        ],
    }


def test_price_catalog_release_audit_accepts_compact_aggregate_payload() -> None:
    catalog = _certified_catalog()
    catalog["filters"]["product_id"] = None  # type: ignore[index]
    catalog["geographies"] = []
    catalog["locations"] = []
    catalog["location_display"] = {"returned": 0, "total": 0, "sampled": False}
    catalog["products"][0]["sample_locations"] = []  # type: ignore[index]

    assert audit_price_monitoring_catalog(catalog, expected_retailer_id="walmart_us") == []


def test_price_catalog_release_audit_does_not_require_master_store_extrapolation() -> None:
    catalog = _certified_catalog()
    catalog["summary"]["expected_locations"] = 0  # type: ignore[index]
    catalog["summary"]["coverage_rate"] = None  # type: ignore[index]
    catalog["presence"].update(  # type: ignore[union-attr]
        {
            "eligible_locations": 0,
            "not_observed_locations": 0,
            "observed_presence_rate": None,
        }
    )
    catalog["products"][0]["presence"] = {  # type: ignore[index]
        "observed_locations": 3,
        "eligible_locations": 3,
        "not_observed_locations": 0,
        "observed_rate": 1.0,
        "not_observed_rate": 0.0,
    }

    assert audit_price_monitoring_catalog(catalog, expected_retailer_id="walmart_us") == []


def test_price_catalog_release_audit_accepts_zero_distribution_population() -> None:
    catalog = _certified_catalog()
    catalog["source"]["source_rows"] = 0  # type: ignore[index]
    catalog["source"]["classified_rows"] = 0  # type: ignore[index]
    catalog["summary"].update(  # type: ignore[union-attr]
        {
            "observed_locations": 0,
            "distribution_store_count": 0,
            "service_area_presence_count": 0,
            "coverage_rate": 0.0,
            "observed_products": 0,
            "eligible_observations": 0,
            "search_price_observations": 0,
            "usable_price_rate": 0.0,
            "price_consistency_rate": None,
        }
    )
    catalog["presence"].update(  # type: ignore[union-attr]
        {
            "observed_locations": 0,
            "distribution_store_count": 0,
            "service_area_presence_count": 0,
            "not_observed_locations": 5,
            "observed_presence_rate": 0.0,
        }
    )
    catalog["price_distribution"] = _price_stats(0)
    catalog["search_price_distribution"] = _price_stats(0)
    catalog["products"] = []
    catalog["brand_portfolio"] = []
    catalog["geographies"] = []
    catalog["locations"] = []
    catalog["location_display"] = {"returned": 0, "total": 0, "sampled": False}

    assert audit_price_monitoring_catalog(catalog, expected_retailer_id="walmart_us") == []


def test_price_catalog_release_audit_rejects_inflated_complete_store_evidence() -> None:
    inflated = _certified_catalog()
    inflated_count = 4_511
    inflated["source"]["source_rows"] = inflated_count  # type: ignore[index]
    inflated["source"]["classified_rows"] = inflated_count  # type: ignore[index]
    inflated["summary"].update(  # type: ignore[union-attr]
        {
            "observed_locations": inflated_count,
            "distribution_store_count": 4_510,
            "service_area_presence_count": 1,
            "expected_locations": inflated_count,
            "coverage_rate": 1.0,
            "eligible_observations": inflated_count,
            "search_price_observations": inflated_count,
        }
    )
    inflated["presence"].update(  # type: ignore[union-attr]
        {
            "observed_locations": inflated_count,
            "distribution_store_count": 4_510,
            "service_area_presence_count": 1,
            "eligible_locations": inflated_count,
            "not_observed_locations": 0,
            "observed_presence_rate": 1.0,
        }
    )
    inflated["price_distribution"] = _price_stats(inflated_count)
    inflated["search_price_distribution"] = _price_stats(inflated_count)
    product = inflated["products"][0]  # type: ignore[index]
    product.update(
        {
            "locations": 4_510,
            "distribution_store_count": 4_510,
            "service_area_presence_count": 1,
            "search_observed_locations": inflated_count,
            "price_stats": _price_stats(inflated_count),
            "search_price_stats": _price_stats(inflated_count),
            "presence": {
                "observed_locations": inflated_count,
                "eligible_locations": inflated_count,
                "not_observed_locations": 0,
                "observed_rate": 1.0,
                "not_observed_rate": 0.0,
            },
        }
    )
    for key in ("brand_portfolio", "geographies"):
        row = inflated[key][0]  # type: ignore[index]
        row.update(
            {
                "locations": 4_510,
                "distribution_store_count": 4_510,
                "service_area_presence_count": 1,
                "search_observed_locations": inflated_count,
                "observations": inflated_count,
            }
        )
        if key == "geographies":
            row["price_stats"] = _price_stats(inflated_count)
            row["search_price_stats"] = _price_stats(inflated_count)

    codes = {
        finding["code"]
        for finding in audit_price_monitoring_catalog(inflated, expected_retailer_id="walmart_us")
    }

    assert "price_catalog_product_location_display_invalid" in codes
    assert "price_catalog_full_location_distribution_invalid" in codes


def test_price_catalog_release_audit_rejects_inventory_claim_and_nonpositive_price() -> None:
    catalog = _certified_catalog()
    catalog["products"][0]["availability_status"] = "in_stock"  # type: ignore[index]
    catalog["products"][0]["price_stats"]["minimum"] = 0.0  # type: ignore[index]

    codes = {finding["code"] for finding in audit_price_monitoring_catalog(catalog)}

    assert "price_catalog_inventory_claim_present" in codes
    assert "price_catalog_product_price_population_invalid" in codes


def test_price_architecture_release_audit_accepts_zero_store_service_area_product() -> None:
    matrix = _certified_architecture()
    product = matrix["rungs"][0]["cells"][0]["products"][0]  # type: ignore[index]
    product.update(
        {
            "distribution_store_count": 0,
            "service_area_presence_count": 3,
            "observed_locations": 3,
            "search_observed_locations": 3,
        }
    )
    matrix["rungs"][0]["anchor_products"][0] = product  # type: ignore[index]
    matrix["retailers"][0].update(  # type: ignore[index]
        {
            "distribution_store_count": 0,
            "service_area_presence_count": 3,
            "observed_locations": 3,
            "search_observed_locations": 3,
        }
    )

    assert audit_price_architecture_matrix(matrix) == []


def test_price_architecture_release_audit_rejects_inflated_product_footprint() -> None:
    inflated = _certified_architecture()
    product = inflated["rungs"][0]["cells"][0]["products"][0]  # type: ignore[index]
    product.update(
        {
            "distribution_store_count": 4_510,
            "service_area_presence_count": 1,
            "observed_locations": 4_511,
            "search_observed_locations": 4_511,
        }
    )
    inflated["rungs"][0]["anchor_products"][0] = product  # type: ignore[index]

    codes = {finding["code"] for finding in audit_price_architecture_matrix(inflated)}

    assert "price_architecture_retailer_distribution_bounds_invalid" in codes


def test_price_architecture_release_audit_rejects_omitted_configured_retailer() -> None:
    matrix = _certified_architecture()

    codes = {
        finding["code"]
        for finding in audit_price_architecture_matrix(
            matrix,
            expected_retailer_ids={"walmart_us", "aldi_us", "target_us"},
            expected_catalog_retailer_ids={"walmart_us", "aldi_us", "target_us"},
        )
    }

    assert "price_architecture_retailer_scope_mismatch" in codes
    assert "price_architecture_catalog_scope_mismatch" in codes


@pytest.mark.skipif(
    not os.getenv("RCI_TEST_DATABASE_URL"),
    reason="set RCI_TEST_DATABASE_URL to run Postgres publication isolation integration",
)
async def test_publication_archives_only_same_tenant_predecessor() -> None:
    database = DatabaseProbe(os.environ["RCI_TEST_DATABASE_URL"])
    tenant_a = str(uuid4())
    tenant_b = str(uuid4())
    result_ids: dict[str, str] = {}
    async with database.engine.connect() as connection:
        transaction = await connection.begin()
        try:
            for label, organization_id in (("a", tenant_a), ("b", tenant_b)):
                definition_id = str(uuid4())
                definition_version_id = str(uuid4())
                collection_run_id = str(uuid4())
                analysis_run_id = str(uuid4())
                result_id = str(uuid4())
                result_ids[label] = result_id
                await connection.execute(
                    text("INSERT INTO organization (id, name) VALUES (CAST(:id AS uuid), :name)"),
                    {"id": organization_id, "name": f"publication-tenant-{label}-{uuid4()}"},
                )
                await connection.execute(
                    text(
                        "INSERT INTO collection_definition "
                        "(id, organization_id, stable_key, name) "
                        "VALUES (CAST(:id AS uuid), CAST(:organization_id AS uuid), "
                        ":stable_key, :name)"
                    ),
                    {
                        "id": definition_id,
                        "organization_id": organization_id,
                        "stable_key": f"publication-{label}-{uuid4()}",
                        "name": f"publication-{label}",
                    },
                )
                await connection.execute(
                    text(
                        "INSERT INTO collection_definition_version "
                        "(id, definition_id, version, config, checksum) "
                        "VALUES (CAST(:id AS uuid), CAST(:definition_id AS uuid), "
                        "1, '{}', :checksum)"
                    ),
                    {
                        "id": definition_version_id,
                        "definition_id": definition_id,
                        "checksum": f"publication-{label}",
                    },
                )
                await connection.execute(
                    text(
                        "INSERT INTO collection_run "
                        "(id, organization_id, definition_version_id, status, "
                        "estimated_pages, estimated_credits) "
                        "VALUES (CAST(:id AS uuid), CAST(:organization_id AS uuid), "
                        "CAST(:definition_version_id AS uuid), 'succeeded', 0, 0)"
                    ),
                    {
                        "id": collection_run_id,
                        "organization_id": organization_id,
                        "definition_version_id": definition_version_id,
                    },
                )
                await connection.execute(
                    text(
                        "INSERT INTO analysis_run "
                        "(id, collection_run_id, product_pack_id, product_pack_version, status) "
                        "VALUES (CAST(:id AS uuid), CAST(:collection_run_id AS uuid), "
                        "'milk', '1.0.0', 'succeeded')"
                    ),
                    {"id": analysis_run_id, "collection_run_id": collection_run_id},
                )
                await connection.execute(
                    text(
                        "INSERT INTO analysis_result "
                        "(id, analysis_run_id, analysis_id, schema_version, result, checksum, "
                        "reporting_status) VALUES (CAST(:id AS uuid), "
                        "CAST(:analysis_run_id AS uuid), :analysis_id, "
                        "'2.0.0', '{}', :checksum, 'ready')"
                    ),
                    {
                        "id": result_id,
                        "analysis_run_id": analysis_run_id,
                        "analysis_id": f"publication-analysis-{label}-{uuid4()}",
                        "checksum": f"publication-result-{label}",
                    },
                )

            current_result_id = str(uuid4())
            current_run_id = str(uuid4())
            tenant_a_collection_run_id = str(
                await connection.scalar(
                    text(
                        "SELECT run.collection_run_id FROM analysis_run run "
                        "JOIN analysis_result result ON result.analysis_run_id = run.id "
                        "WHERE result.id = CAST(:result_id AS uuid)"
                    ),
                    {"result_id": result_ids["a"]},
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO analysis_run "
                    "(id, collection_run_id, product_pack_id, product_pack_version, status, "
                    "replay_generation) VALUES (CAST(:id AS uuid), "
                    "CAST(:collection_run_id AS uuid), 'milk', '1.0.0', "
                    "'succeeded', 2)"
                ),
                {"id": current_run_id, "collection_run_id": tenant_a_collection_run_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO analysis_result "
                    "(id, analysis_run_id, analysis_id, schema_version, result, checksum, "
                    "reporting_status) VALUES (CAST(:id AS uuid), "
                    "CAST(:analysis_run_id AS uuid), :analysis_id, "
                    "'2.0.0', '{}', :checksum, 'pending')"
                ),
                {
                    "id": current_result_id,
                    "analysis_run_id": current_run_id,
                    "analysis_id": f"publication-current-{uuid4()}",
                    "checksum": f"publication-current-{uuid4()}",
                },
            )

            archived = await _archive_publication_predecessors(
                connection,
                analysis_result_id=current_result_id,
                product_pack_id="milk",
                organization_id=tenant_a,
            )
            states = dict(
                (
                    await connection.execute(
                        text(
                            "SELECT id::text, archived_at IS NOT NULL AS archived "
                            "FROM analysis_result WHERE id IN "
                            "(CAST(:a AS uuid), CAST(:b AS uuid), CAST(:current AS uuid))"
                        ),
                        {
                            "a": result_ids["a"],
                            "b": result_ids["b"],
                            "current": current_result_id,
                        },
                    )
                ).all()
            )

            assert archived == [result_ids["a"]]
            assert states == {
                result_ids["a"]: True,
                result_ids["b"]: False,
                current_result_id: False,
            }
        finally:
            await transaction.rollback()
    await database.dispose()
