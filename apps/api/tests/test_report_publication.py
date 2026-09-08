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


def _certified_catalog() -> dict[str, object]:
    return {
        "schema_version": "1.4.0",
        "retailer": {"id": "walmart_us"},
        "source": {"observation_schema_version": "1.2.0"},
        "summary": {
            "observed_locations": 3,
            "verified_available_locations": 2,
            "expected_locations": 5,
            "observed_products": 1,
            "verified_available_products": 1,
            "eligible_observations": 2,
            "search_price_observations": 3,
            "verified_availability_observations": 2,
        },
        "presence": {
            "observed_locations": 3,
            "eligible_locations": 5,
            "not_observed_locations": 2,
            "observed_presence_rate": 0.6,
        },
        "availability": {
            "status": "verified",
            "verified_available_locations": 2,
            "eligible_locations": 5,
            "verified_availability_rate": 0.4,
            "explicitly_out_of_stock_locations": 1,
            "unverified_locations": 0,
        },
        "price_distribution": {"observation_count": 2},
        "search_price_distribution": {"observation_count": 3},
        "products": [
            {
                "product_id": "wmt-milk-verified-fixture",
                "locations": 2,
                "states": 1,
                "cities": 2,
                "verified_available_locations": 2,
                "verified_available_states": 1,
                "verified_available_cities": 2,
                "verified_available_zipcodes": 2,
                "search_observed_locations": 3,
                "search_observed_states": 1,
                "search_observed_cities": 3,
                "search_observed_zipcodes": 3,
                "availability": {
                    "status": "verified",
                    "search_observations": 3,
                    "known_observations": 3,
                    "in_stock_observations": 2,
                    "verified_in_stock_observations": 2,
                    "explicitly_out_of_stock_observations": 1,
                    "unverified_observations": 0,
                    "search_observed_locations": 3,
                    "verified_available_locations": 2,
                    "explicitly_out_of_stock_locations": 1,
                    "unverified_locations": 0,
                    "rate": 0.6667,
                },
                "presence": {
                    "observed_locations": 3,
                    "eligible_locations": 5,
                    "not_observed_locations": 2,
                    "observed_rate": 0.6,
                    "not_observed_rate": 0.4,
                },
                "price_stats": {"observation_count": 2},
                "search_price_stats": {"observation_count": 3},
            }
        ],
        "brand_portfolio": [
            {
                "locations": 2,
                "verified_available_locations": 2,
                "search_observed_locations": 3,
                "products": 1,
                "search_observed_products": 1,
                "observations": 3,
            }
        ],
        "geographies": [
            {
                "level": "state",
                "key": "CA",
                "locations": 2,
                "products": 1,
                "observations": 3,
                "search_observed_locations": 3,
                "verified_available_locations": 2,
                "explicitly_out_of_stock_locations": 1,
                "unverified_locations": 0,
                "search_observed_products": 1,
                "verified_available_products": 1,
                "verified_availability_observations": 2,
                "price_stats": {"observation_count": 2},
                "search_price_stats": {"observation_count": 3},
            }
        ],
        "locations": [],
        "location_display": {"returned": 0, "total": 0, "sampled": False},
        "quality": {"status": "ready"},
    }


def _architecture_product(product_id: str, price: float) -> dict[str, object]:
    return {
        "product_id": product_id,
        "median_price": price,
        "minimum_price": price,
        "maximum_price": price,
        "observed_locations": 2,
        "verified_available_locations": 2,
        "search_observed_locations": 2,
        "seller_status": "verified_first_party",
    }


def _certified_architecture() -> dict[str, object]:
    benchmark_product = _architecture_product("wmt-milk-verified-fixture", 4.0)
    competitor_product = _architecture_product("aldi-1", 3.5)
    return {
        "schema_version": "1.2.0",
        "filters": {"anchor_retailer_id": "walmart_us", "brand": None},
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
                "observed_locations": 2,
                "verified_available_locations": 2,
                "search_observed_locations": 2,
                "search_observed_skus": 1,
                "verified_first_party_skus": 1,
                "seller_unverified_skus": 0,
                "seller_not_governed_skus": 0,
                "reason": None,
            },
            {
                "id": "aldi_us",
                "status": "available",
                "sku_count": 1,
                "observed_locations": 2,
                "verified_available_locations": 2,
                "search_observed_locations": 2,
                "search_observed_skus": 1,
                "verified_first_party_skus": 1,
                "seller_unverified_skus": 0,
                "seller_not_governed_skus": 0,
                "reason": None,
            },
        ],
        "rungs": [
            {
                "id": "rung-1",
                "rank": 1,
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
                        "products": [benchmark_product],
                    },
                    {
                        "retailer_id": "aldi_us",
                        "sku_count": 1,
                        "assortment_share": 1.0,
                        "average_price": 3.5,
                        "products": [competitor_product],
                    },
                ],
            }
        ],
    }


def test_price_catalog_release_audit_rejects_inflated_product_availability() -> None:
    catalog = _certified_catalog()
    assert audit_price_monitoring_catalog(catalog, expected_retailer_id="walmart_us") == []

    inflated = copy.deepcopy(catalog)
    inflated["products"][0]["verified_available_locations"] = 4_510  # type: ignore[index]
    codes = {
        finding["code"]
        for finding in audit_price_monitoring_catalog(inflated, expected_retailer_id="walmart_us")
    }

    assert "price_catalog_product_location_counts_invalid" in codes
    assert "price_catalog_product_availability_locations_invalid" in codes


def test_price_architecture_release_audit_rejects_search_only_footprint() -> None:
    matrix = _certified_architecture()
    assert audit_price_architecture_matrix(matrix) == []

    inflated = copy.deepcopy(matrix)
    inflated["rungs"][0]["cells"][0]["products"][0][  # type: ignore[index]
        "verified_available_locations"
    ] = 4_510
    codes = {finding["code"] for finding in audit_price_architecture_matrix(inflated)}

    assert "price_architecture_product_availability_invalid" in codes


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
