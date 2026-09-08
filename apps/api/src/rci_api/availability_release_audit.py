"""Independent semantic trust checks for distribution-bearing read models."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from statistics import mean
from typing import Any

Finding = dict[str, Any]
_RATE_TOLERANCE = 0.00011
_VALUE_TOLERANCE = 0.0006
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
_INVENTORY_FIELDS = frozenset(
    {
        "availability",
        "availability_status",
        "verified_local_availability",
        "verified_available_locations",
        "verified_available_products",
        "verified_available_states",
        "verified_available_cities",
        "verified_available_zipcodes",
        "verified_availability_observations",
        "verified_availability_rate",
        "verified_in_stock_observations",
        "explicitly_out_of_stock_locations",
        "explicitly_out_of_stock_observations",
        "unverified_locations",
        "unverified_observations",
        "in_stock",
        "in_stock_observations",
        "stock_status",
    }
)
_PRICE_FIELDS = (
    "minimum",
    "q1",
    "observation_median",
    "product_equal_weighted_median",
    "q3",
    "maximum",
    "range",
    "modal_price",
    "modal_share",
)


def _rows(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(row, Mapping) for row in value):
        raise ValueError("value is not an array of objects")
    return [dict(row) for row in value]


def _integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("value is not an integer")
    return value


def _count(value: object) -> int:
    value = _integer(value)
    if value < 0:
        raise ValueError("count is negative")
    return value


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("value is not numeric")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("value is not finite")
    return value


def _close(left: object, right: object, tolerance: float = _VALUE_TOLERANCE) -> bool:
    if left is None or right is None:
        return left is right
    try:
        return abs(_number(left) - _number(right)) <= tolerance
    except ValueError:
        return False


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _nonblank(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _finding(code: str, message: str, *, path: str, **context: object) -> Finding:
    return {
        "severity": "error",
        "code": code,
        "message": message,
        "context": {"path": path, **context},
    }


def _inventory_paths(value: object, path: str = "<root>") -> list[str]:
    paths: list[str] = []
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key)
            child_path = key if path == "<root>" else f"{path}.{key}"
            if key in _INVENTORY_FIELDS:
                paths.append(child_path)
            paths.extend(_inventory_paths(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            paths.extend(_inventory_paths(child, f"{path}[{index}]"))
    return paths


def _price_stats_valid(value: object, expected_count: int) -> bool:
    if not isinstance(value, Mapping):
        return False
    stats = dict(value)
    try:
        count = _count(stats.get("observation_count"))
        if count != expected_count:
            return False
        if count == 0:
            return all(stats.get(field) is None for field in _PRICE_FIELDS)
        minimum = _number(stats.get("minimum"))
        q1 = _number(stats.get("q1"))
        observation_median = _number(stats.get("observation_median"))
        q3 = _number(stats.get("q3"))
        maximum = _number(stats.get("maximum"))
        price_range = _number(stats.get("range"))
        modal_price = _number(stats.get("modal_price"))
        modal_share = _number(stats.get("modal_share"))
        product_median = stats.get("product_equal_weighted_median")
        return (
            0 < minimum <= q1 <= observation_median <= q3 <= maximum
            and minimum <= modal_price <= maximum
            and price_range >= 0
            and _close(price_range, maximum - minimum)
            and 0 < modal_share <= 1
            and (product_median is None or _number(product_median) > 0)
        )
    except ValueError:
        return False


def _positive_price_range(product: Mapping[str, Any]) -> tuple[float, float, float] | None:
    try:
        prices = (
            _number(product.get("minimum_price")),
            _number(product.get("median_price")),
            _number(product.get("maximum_price")),
        )
    except ValueError:
        return None
    return prices if 0 < prices[0] <= prices[1] <= prices[2] else None


def audit_price_monitoring_catalog(
    document: Mapping[str, Any],
    *,
    expected_retailer_id: str | None = None,
) -> list[Finding]:
    """Reconcile a positive-price Search distribution catalog.

    Compact catalogs do not contain the full store-ID population. Exact distinct-ID
    reconstruction is therefore limited to product-filtered, explicitly unsampled
    location payloads.
    """

    findings: list[Finding] = []

    def check(condition: bool, code: str, message: str, path: str, **context: object) -> None:
        if not condition:
            findings.append(_finding(code, message, path=path, **context))

    try:
        check(
            document.get("schema_version") == "1.5.0",
            "price_catalog_contract_version_invalid",
            "Price Intelligence catalog is not on distribution contract 1.5.0.",
            "schema_version",
            actual=document.get("schema_version"),
        )
        check(
            document.get("distribution_contract") == _DISTRIBUTION_CONTRACT,
            "price_catalog_distribution_contract_invalid",
            "Catalog lacks the exact positive-price store-Search distribution contract.",
            "distribution_contract",
        )
        inventory_paths = _inventory_paths(document)
        check(
            not inventory_paths,
            "price_catalog_inventory_claim_present",
            "Catalog exposes inventory claims outside the distribution contract.",
            inventory_paths[0] if inventory_paths else "<root>",
            claim_paths=inventory_paths,
        )

        retailer = dict(document.get("retailer") or {})
        retailer_id = retailer.get("id")
        if expected_retailer_id is not None:
            check(
                retailer_id == expected_retailer_id,
                "price_catalog_retailer_scope_mismatch",
                "Catalog retailer does not match its staged publication scope.",
                "retailer.id",
                expected=expected_retailer_id,
                actual=retailer_id,
            )
        filters = dict(document.get("filters") or {})
        check(
            filters.get("retailer_id") == retailer_id,
            "price_catalog_filter_scope_invalid",
            "Catalog filter retailer does not match its retailer.",
            "filters.retailer_id",
        )
        source = dict(document.get("source") or {})
        check(
            source.get("authority") == "Search"
            and source.get("grain")
            == "retailer product x retailer location x latest observation in run"
            and source.get("observation_schema_version") == "1.3.0",
            "price_catalog_observation_contract_invalid",
            "Catalog is not projected from the canonical Search observation contract.",
            "source",
        )

        summary = dict(document.get("summary") or {})
        stores = _count(summary.get("distribution_store_count"))
        services = _count(summary.get("service_area_presence_count"))
        observed_locations = _count(summary.get("observed_locations"))
        expected_locations = _count(summary.get("expected_locations"))
        observed_products = _count(summary.get("observed_products"))
        observations = _count(summary.get("search_price_observations"))
        eligible_observations = _count(summary.get("eligible_observations"))
        source_rows = _count(source.get("source_rows"))
        classified_rows = _count(source.get("classified_rows"))
        check(
            observed_locations == stores + services,
            "price_catalog_distribution_counts_invalid",
            "Store distribution and service-area presence do not reconcile.",
            "summary",
        )
        check(
            expected_locations == 0 or observed_locations <= expected_locations,
            "price_catalog_location_scope_invalid",
            "Observed Search locations exceed the declared eligible scope.",
            "summary.expected_locations",
        )
        check(
            eligible_observations == observations <= classified_rows <= source_rows,
            "price_catalog_observation_counts_invalid",
            "Positive-price observations do not reconcile to the source population.",
            "summary.search_price_observations",
        )
        check(
            observed_products <= observations,
            "price_catalog_product_counts_invalid",
            "Observed products exceed the product-location population.",
            "summary.observed_products",
        )
        check(
            _close(summary.get("coverage_rate"), _rate(observed_locations, expected_locations)),
            "price_catalog_coverage_rate_invalid",
            "Coverage rate does not reconcile to its declared scope.",
            "summary.coverage_rate",
        )
        usable_rate = _number(summary.get("usable_price_rate"))
        consistency_rate = summary.get("price_consistency_rate")
        check(
            0 <= usable_rate <= 1
            and (
                consistency_rate is None
                if observations == 0
                else 0 <= _number(consistency_rate) <= 1
            ),
            "price_catalog_summary_rates_invalid",
            "Catalog price-quality rates are outside valid bounds.",
            "summary",
        )

        presence = dict(document.get("presence") or {})
        not_observed = _count(presence.get("not_observed_locations"))
        check(
            presence.get("status") == "observed_only"
            and _count(presence.get("observed_locations")) == observed_locations
            and _count(presence.get("distribution_store_count")) == stores
            and _count(presence.get("service_area_presence_count")) == services
            and _count(presence.get("eligible_locations")) == expected_locations
            and not_observed == max(0, expected_locations - observed_locations)
            and _count(presence.get("confirmed_gap_locations")) == 0,
            "price_catalog_presence_counts_invalid",
            "Search-presence counts do not reconcile.",
            "presence",
        )
        check(
            _close(
                presence.get("observed_presence_rate"),
                _rate(observed_locations, expected_locations),
            ),
            "price_catalog_presence_rate_invalid",
            "Search-presence rate does not reconcile.",
            "presence.observed_presence_rate",
        )

        price_distribution = dict(document.get("price_distribution") or {})
        search_distribution = dict(document.get("search_price_distribution") or {})
        check(
            _price_stats_valid(price_distribution, observations)
            and _price_stats_valid(search_distribution, observations)
            and price_distribution == search_distribution,
            "price_catalog_price_population_invalid",
            "Price distributions do not use the same positive-price Search population.",
            "price_distribution",
        )

        products = _rows(document.get("products"))
        product_ids = [str(row.get("product_id") or "").strip() for row in products]
        check(
            len(products) == observed_products
            and all(product_ids)
            and len(product_ids) == len(set(product_ids)),
            "price_catalog_product_population_invalid",
            "Product rows are missing, duplicated, or do not reconcile.",
            "products",
        )
        selected_product_id = filters.get("product_id")
        if selected_product_id is not None:
            check(
                len(products) <= 1
                and all(value == str(selected_product_id) for value in product_ids),
                "price_catalog_product_filter_invalid",
                "Product-filtered catalog contains a product outside its scope.",
                "products",
            )

        product_observations = 0
        for index, product in enumerate(products):
            path = f"products[{index}]"
            product_stores = _count(product.get("distribution_store_count"))
            product_services = _count(product.get("service_area_presence_count"))
            product_locations = _count(product.get("search_observed_locations"))
            price_stats = dict(product.get("price_stats") or {})
            search_price_stats = dict(product.get("search_price_stats") or {})
            product_count = _count(price_stats.get("observation_count"))
            product_observations += product_count
            check(
                _count(product.get("locations")) == product_stores
                and product_locations == product_stores + product_services,
                "price_catalog_product_distribution_invalid",
                "Product store distribution is not separate from service-area presence.",
                path,
            )
            check(
                product_count == product_locations,
                "price_catalog_product_grain_invalid",
                "Product observations do not reconcile to latest product-location grain.",
                path,
            )
            state_count = _count(product.get("search_observed_states"))
            city_count = _count(product.get("search_observed_cities"))
            zip_count = _count(product.get("search_observed_zipcodes"))
            check(
                _count(product.get("states")) == state_count
                and _count(product.get("cities")) == city_count
                and max(state_count, city_count, zip_count) <= product_locations,
                "price_catalog_product_geography_counts_invalid",
                "Product geography counts exceed Search evidence.",
                path,
            )
            check(
                _price_stats_valid(price_stats, product_count)
                and _price_stats_valid(search_price_stats, product_count)
                and price_stats == search_price_stats,
                "price_catalog_product_price_population_invalid",
                "Product prices do not use its positive-price Search population.",
                path,
            )
            product_presence = dict(product.get("presence") or {})
            product_eligible = _count(product_presence.get("eligible_locations"))
            product_missing = _count(product_presence.get("not_observed_locations"))
            check(
                _count(product_presence.get("observed_locations")) == product_locations
                and product_eligible >= product_locations
                and product_missing == product_eligible - product_locations,
                "price_catalog_product_presence_invalid",
                "Product Search-presence counts do not reconcile.",
                f"{path}.presence",
            )
            check(
                _close(
                    product_presence.get("observed_rate"),
                    _rate(product_locations, product_eligible),
                )
                and _close(
                    product_presence.get("not_observed_rate"),
                    _rate(product_missing, product_eligible),
                ),
                "price_catalog_product_presence_rates_invalid",
                "Product Search-presence rates do not reconcile.",
                f"{path}.presence",
            )
            samples = _rows(product.get("sample_locations"))
            sample_keys = [str(row.get("scope_key") or "").strip() for row in samples]
            samples_valid = (
                len(samples) <= product_locations
                and all(sample_keys)
                and len(sample_keys) == len(set(sample_keys))
            )
            for sample in samples:
                try:
                    samples_valid = (
                        samples_valid
                        and _number(sample.get("price")) > 0
                        and sample.get("search_observed") is True
                    )
                except ValueError:
                    samples_valid = False
                store_number = sample.get("store_number")
                distribution_id = sample.get("distribution_store_id")
                samples_valid = samples_valid and (
                    store_number is None
                    if distribution_id is None
                    else _nonblank(distribution_id) and distribution_id == store_number
                )
            check(
                samples_valid,
                "price_catalog_product_sample_invalid",
                "Product sample has duplicate, nonpositive, or misidentified Search evidence.",
                f"{path}.sample_locations",
            )
        check(
            product_observations == observations,
            "price_catalog_product_observation_totals_invalid",
            "Product observations do not reconcile to the catalog total.",
            "products",
        )

        brand_rows = _rows(document.get("brand_portfolio"))
        brand_types = [str(row.get("brand_type") or "") for row in brand_rows]
        check(
            all(brand_types) and len(brand_types) == len(set(brand_types)),
            "price_catalog_brand_population_invalid",
            "Brand portfolio contains missing or duplicate rows.",
            "brand_portfolio",
        )
        for index, row in enumerate(brand_rows):
            row_stores = _count(row.get("distribution_store_count"))
            row_services = _count(row.get("service_area_presence_count"))
            row_locations = _count(row.get("search_observed_locations"))
            row_products = _count(row.get("products"))
            row_observations = _count(row.get("observations"))
            check(
                _count(row.get("locations")) == row_stores
                and row_locations == row_stores + row_services
                and row_products == _count(row.get("search_observed_products"))
                and row_products <= row_observations,
                "price_catalog_brand_distribution_invalid",
                "Brand distribution does not reconcile.",
                f"brand_portfolio[{index}]",
            )
            median_price = row.get("median_price")
            check(
                (
                    row_observations == 0
                    and median_price is None
                    and row.get("search_median_price") is None
                )
                or (
                    row_observations > 0
                    and _number(median_price) > 0
                    and _close(median_price, row.get("search_median_price"))
                ),
                "price_catalog_brand_price_invalid",
                "Brand median is not based on positive Search prices.",
                f"brand_portfolio[{index}]",
            )
        check(
            sum(_count(row.get("observations")) for row in brand_rows) == observations
            and sum(_count(row.get("products")) for row in brand_rows) == observed_products
            and sum(_count(row.get("search_observed_products")) for row in brand_rows)
            == observed_products,
            "price_catalog_brand_totals_invalid",
            "Brand populations do not reconcile to catalog totals.",
            "brand_portfolio",
        )

        geography_rows = _rows(document.get("geographies"))
        geography_keys = [
            (str(row.get("level") or ""), str(row.get("key") or "")) for row in geography_rows
        ]
        check(
            all(level and key for level, key in geography_keys)
            and len(geography_keys) == len(set(geography_keys)),
            "price_catalog_geography_population_invalid",
            "Geography rows are duplicated or unidentified.",
            "geographies",
        )
        for index, row in enumerate(geography_rows):
            row_stores = _count(row.get("distribution_store_count"))
            row_services = _count(row.get("service_area_presence_count"))
            row_locations = _count(row.get("search_observed_locations"))
            row_observations = _count(row.get("observations"))
            price_stats = dict(row.get("price_stats") or {})
            search_price_stats = dict(row.get("search_price_stats") or {})
            check(
                _count(row.get("locations")) == row_stores
                and row_locations == row_stores + row_services
                and _count(row.get("products"))
                == _count(row.get("search_observed_products"))
                <= row_observations,
                "price_catalog_geography_distribution_invalid",
                "Geography distribution does not reconcile.",
                f"geographies[{index}]",
            )
            check(
                _price_stats_valid(price_stats, row_observations)
                and _price_stats_valid(search_price_stats, row_observations)
                and price_stats == search_price_stats,
                "price_catalog_geography_price_population_invalid",
                "Geography prices do not use its Search population.",
                f"geographies[{index}]",
            )
        if geography_rows:
            check(
                sum(_count(row.get("observations")) for row in geography_rows) == observations
                and sum(_count(row.get("search_observed_locations")) for row in geography_rows)
                == observed_locations
                and sum(_count(row.get("distribution_store_count")) for row in geography_rows)
                == stores
                and sum(_count(row.get("service_area_presence_count")) for row in geography_rows)
                == services,
                "price_catalog_geography_totals_invalid",
                "Geography populations do not reconcile to catalog totals.",
                "geographies",
            )

        location_rows = _rows(document.get("locations"))
        location_display = dict(document.get("location_display") or {})
        returned = _count(location_display.get("returned"))
        total = _count(location_display.get("total"))
        sampled = location_display.get("sampled")
        check(
            returned == len(location_rows)
            and total >= returned
            and isinstance(sampled, bool)
            and sampled == (total > returned),
            "price_catalog_location_display_invalid",
            "Location display metadata does not reconcile.",
            "location_display",
        )
        location_keys = [str(row.get("scope_key") or "").strip() for row in location_rows]
        check(
            all(location_keys) and len(location_keys) == len(set(location_keys)),
            "price_catalog_location_population_invalid",
            "Returned locations are missing or duplicated.",
            "locations",
        )
        for index, row in enumerate(location_rows):
            kind = row.get("kind")
            is_store = kind == "store"
            is_service = kind == "service_area"
            row_stores = _count(row.get("distribution_store_count"))
            row_services = _count(row.get("service_area_presence_count"))
            check(
                (is_store or is_service)
                and row_stores == int(is_store)
                and row_services == int(is_service)
                and (
                    _nonblank(row.get("store_number"))
                    if is_store
                    else row.get("store_number") is None
                ),
                "price_catalog_location_kind_invalid",
                "Location is misclassified between store and service-area evidence.",
                f"locations[{index}]",
            )
            price_range = _positive_price_range(row)
            check(
                _count(row.get("products"))
                == _count(row.get("search_observed_products"))
                == _count(row.get("observations"))
                and _count(row.get("observations")) > 0
                and row.get("search_observed") is True
                and price_range is not None
                and _close(row.get("minimum_price"), row.get("search_minimum_price"))
                and _close(row.get("median_price"), row.get("search_median_price"))
                and _close(row.get("maximum_price"), row.get("search_maximum_price")),
                "price_catalog_location_price_population_invalid",
                "Location is not a positive-price canonical Search population.",
                f"locations[{index}]",
            )

        if selected_product_id is not None:
            selected_locations = sum(
                _count(product.get("search_observed_locations")) for product in products
            )
            check(
                total == selected_locations == observed_locations,
                "price_catalog_product_location_display_invalid",
                "Product-filtered location total does not reconcile.",
                "location_display.total",
            )
            # Only an explicitly complete location array supports an independent
            # distinct-ID check. Compact or sampled documents remain aggregate audits.
            if sampled is False:
                evidence_stores = {
                    str(row.get("store_number"))
                    for row in location_rows
                    if row.get("kind") == "store" and _nonblank(row.get("store_number"))
                }
                evidence_services = {
                    str(row.get("scope_key"))
                    for row in location_rows
                    if row.get("kind") == "service_area" and _nonblank(row.get("scope_key"))
                }
                check(
                    len(evidence_stores) == stores
                    and len(evidence_services) == services
                    and len(evidence_stores) + len(evidence_services) == observed_locations,
                    "price_catalog_full_location_distribution_invalid",
                    "Complete locations do not support the reported distinct-store distribution.",
                    "locations",
                    evidence_stores=len(evidence_stores),
                    reported_stores=stores,
                )

        check(
            dict(document.get("quality") or {}).get("status") != "blocked",
            "price_catalog_quality_blocked",
            "A catalog with blocking quality findings cannot be published.",
            "quality.status",
        )
    except (KeyError, TypeError, ValueError) as exc:
        findings.append(
            _finding(
                "price_catalog_semantic_audit_error",
                "Price Intelligence catalog could not be semantically certified.",
                path="<root>",
                error=str(exc),
            )
        )
    return findings


def audit_price_architecture_matrix(
    document: Mapping[str, Any],
    *,
    expected_retailer_ids: Iterable[str] | None = None,
    expected_catalog_retailer_ids: Iterable[str] | None = None,
) -> list[Finding]:
    """Recompute matrix price-rung, seller, SKU, and distribution aggregates."""

    findings: list[Finding] = []

    def check(condition: bool, code: str, message: str, path: str, **context: object) -> None:
        if not condition:
            findings.append(_finding(code, message, path=path, **context))

    try:
        check(
            document.get("schema_version") == "1.3.0",
            "price_architecture_contract_version_invalid",
            "Price Architecture is not on distribution contract 1.3.0.",
            "schema_version",
            actual=document.get("schema_version"),
        )
        check(
            document.get("distribution_contract") == _DISTRIBUTION_CONTRACT,
            "price_architecture_distribution_contract_invalid",
            "Price Architecture lacks the positive-price Search distribution contract.",
            "distribution_contract",
        )
        inventory_paths = _inventory_paths(document)
        check(
            not inventory_paths,
            "price_architecture_inventory_claim_present",
            "Price Architecture exposes inventory claims.",
            inventory_paths[0] if inventory_paths else "<root>",
            claim_paths=inventory_paths,
        )
        source = dict(document.get("source") or {})
        check(
            source.get("authority") == "Search"
            and source.get("price_grain")
            == (
                "retailer product x median positive Search-listed package price across "
                "observed Search locations"
            )
            and source.get("distribution_rule")
            == (
                "distinct store IDs where the product appears in store-level Search "
                "with price greater than zero; not an in-stock indicator"
            )
            and source.get("assignment_rule")
            == "price only; no product-match relationship is used",
            "price_architecture_source_contract_invalid",
            "Matrix source rules are not the positive-price Search contract.",
            "source",
        )

        filters = dict(document.get("filters") or {})
        anchor_id = str(filters.get("anchor_retailer_id") or "").strip()
        retailers = _rows(document.get("retailers"))
        retailer_ids = [str(row.get("id") or "").strip() for row in retailers]
        check(
            bool(anchor_id)
            and anchor_id in retailer_ids
            and all(retailer_ids)
            and len(retailer_ids) == len(set(retailer_ids)),
            "price_architecture_retailer_scope_invalid",
            "Retailer scope is empty, duplicated, or lacks the benchmark.",
            "retailers",
        )
        if expected_retailer_ids is not None:
            expected_scope = {str(value) for value in expected_retailer_ids}
            check(
                set(retailer_ids) == expected_scope,
                "price_architecture_retailer_scope_mismatch",
                "Matrix retailer scope differs from the configured report scope.",
                "retailers",
                expected=sorted(expected_scope),
                actual=sorted(set(retailer_ids)),
            )
        retailer_index = {str(row.get("id")): row for row in retailers}

        rungs = _rows(document.get("rungs"))
        rung_ids = [str(row.get("id") or "").strip() for row in rungs]
        check(
            bool(rungs)
            and all(rung_ids)
            and len(rung_ids) == len(set(rung_ids))
            and [_integer(row.get("rank")) for row in rungs] == list(range(1, len(rungs) + 1)),
            "price_architecture_rungs_invalid",
            "Price rungs are missing, duplicated, or not contiguous.",
            "rungs",
        )
        cell_retailer_ids = (
            {str(cell.get("retailer_id") or "") for cell in _rows(rungs[0].get("cells"))}
            if rungs
            else set()
        )
        check(
            anchor_id in cell_retailer_ids and cell_retailer_ids.issubset(retailer_index),
            "price_architecture_catalog_scope_invalid",
            "Matrix cells omit the benchmark or contain an unknown retailer.",
            "rungs[0].cells",
        )
        if expected_catalog_retailer_ids is not None:
            expected_catalog_scope = {str(value) for value in expected_catalog_retailer_ids}
            check(
                cell_retailer_ids == expected_catalog_scope,
                "price_architecture_catalog_scope_mismatch",
                "Matrix cells differ from the certified catalog scope.",
                "rungs",
                expected=sorted(expected_catalog_scope),
                actual=sorted(cell_retailer_ids),
            )

        products_by_retailer: dict[str, list[dict[str, Any]]] = defaultdict(list)
        seller_counts: dict[str, Counter[str]] = defaultdict(Counter)
        competitor_counts: list[int] = []
        available_retailer_ids = {
            retailer_id
            for retailer_id, row in retailer_index.items()
            if row.get("status") == "available"
        }
        previous_upper: object = None
        for rung_index, rung in enumerate(rungs):
            path = f"rungs[{rung_index}]"
            lower = rung.get("lower_bound")
            upper = rung.get("upper_bound")
            bounds_valid = True
            try:
                if lower is not None:
                    bounds_valid = bounds_valid and _number(lower) >= 0
                if upper is not None:
                    bounds_valid = bounds_valid and _number(upper) > 0
                if lower is not None and upper is not None:
                    bounds_valid = bounds_valid and _number(lower) < _number(upper)
                if rung_index > 0:
                    bounds_valid = bounds_valid and _close(previous_upper, lower)
            except ValueError:
                bounds_valid = False
            check(
                bounds_valid,
                "price_architecture_rung_bounds_invalid",
                "Rung boundaries are invalid or discontinuous.",
                path,
            )
            previous_upper = upper

            cells = _rows(rung.get("cells"))
            cell_ids = [str(cell.get("retailer_id") or "") for cell in cells]
            check(
                all(cell_ids)
                and len(cell_ids) == len(set(cell_ids))
                and set(cell_ids) == cell_retailer_ids,
                "price_architecture_cells_invalid",
                "A rung does not contain exactly one cell per catalog retailer.",
                f"{path}.cells",
            )
            cell_index = {str(cell.get("retailer_id")): cell for cell in cells}
            anchor_products = _rows(rung.get("anchor_products"))
            anchor_cell_products = _rows(dict(cell_index.get(anchor_id) or {}).get("products"))
            anchor_product_ids = [
                str(row.get("product_id") or "").strip() for row in anchor_products
            ]
            check(
                all(anchor_product_ids)
                and len(anchor_product_ids) == len(set(anchor_product_ids))
                and anchor_products == anchor_cell_products,
                "price_architecture_anchor_products_invalid",
                "Rung anchor products differ from the benchmark cell.",
                f"{path}.anchor_products",
            )
            expected_competitor_skus = 0
            for cell_index_value, cell in enumerate(cells):
                retailer_id = str(cell.get("retailer_id") or "")
                cell_path = f"{path}.cells[{cell_index_value}]"
                products = _rows(cell.get("products"))
                product_ids = [str(product.get("product_id") or "").strip() for product in products]
                cell_skus = _count(cell.get("sku_count"))
                check(
                    cell_skus == len(products)
                    and all(product_ids)
                    and len(product_ids) == len(set(product_ids)),
                    "price_architecture_cell_sku_count_invalid",
                    "Cell SKU count or product population does not reconcile.",
                    cell_path,
                    retailer_id=retailer_id,
                )
                if retailer_id != anchor_id and retailer_id in available_retailer_ids:
                    expected_competitor_skus += len(products)
                median_prices: list[float] = []
                for product_index, product in enumerate(products):
                    product_path = f"{cell_path}.products[{product_index}]"
                    stores = _count(product.get("distribution_store_count"))
                    services = _count(product.get("service_area_presence_count"))
                    observed = _count(product.get("observed_locations"))
                    search_observed = _count(product.get("search_observed_locations"))
                    price_range = _positive_price_range(product)
                    check(
                        observed == stores + services
                        and search_observed == observed
                        and observed > 0,
                        "price_architecture_product_distribution_invalid",
                        "Product distribution does not reconcile store and service-area evidence.",
                        product_path,
                        retailer_id=retailer_id,
                    )
                    check(
                        price_range is not None,
                        "price_architecture_product_price_invalid",
                        "Product price range is not strictly positive and ordered.",
                        product_path,
                        retailer_id=retailer_id,
                    )
                    median_price = price_range[1] if price_range else 0.0
                    median_prices.append(median_price)
                    check(
                        (lower is None or median_price >= _number(lower))
                        and (upper is None or median_price < _number(upper)),
                        "price_architecture_product_rung_invalid",
                        "Product median price falls outside its rung.",
                        product_path,
                        retailer_id=retailer_id,
                    )
                    seller_status = str(product.get("seller_status") or "")
                    check(
                        seller_status
                        in {
                            "verified_first_party",
                            "seller_unverified",
                            "not_governed",
                        },
                        "price_architecture_product_seller_status_invalid",
                        "Product has an unknown seller-governance status.",
                        f"{product_path}.seller_status",
                        retailer_id=retailer_id,
                    )
                    products_by_retailer[retailer_id].append(product)
                    seller_counts[retailer_id][seller_status] += 1
                expected_average = round(mean(median_prices), 4) if median_prices else None
                check(
                    _close(cell.get("average_price"), expected_average),
                    "price_architecture_cell_average_invalid",
                    "Cell average does not reconcile to product medians.",
                    f"{cell_path}.average_price",
                    retailer_id=retailer_id,
                )
                finite_width = (
                    _number(upper) - _number(lower)
                    if lower is not None and upper is not None
                    else None
                )
                expected_density = (
                    round(cell_skus / finite_width, 4) if cell_skus and finite_width else None
                )
                check(
                    _close(cell.get("price_density"), expected_density),
                    "price_architecture_cell_density_invalid",
                    "Cell density does not reconcile to SKU count and rung width.",
                    f"{cell_path}.price_density",
                    retailer_id=retailer_id,
                )
            competitor_counts.append(expected_competitor_skus)
            check(
                _count(rung.get("competitor_sku_count")) == expected_competitor_skus,
                "price_architecture_rung_competitor_count_invalid",
                "Rung competitor count does not reconcile.",
                f"{path}.competitor_sku_count",
            )

        for index, retailer in enumerate(retailers):
            retailer_id = str(retailer.get("id") or "")
            path = f"retailers[{index}]"
            products = products_by_retailer.get(retailer_id, [])
            product_ids = [str(row.get("product_id") or "") for row in products]
            sku_count = _count(retailer.get("sku_count"))
            search_skus = _count(retailer.get("search_observed_skus"))
            stores = _count(retailer.get("distribution_store_count"))
            services = _count(retailer.get("service_area_presence_count"))
            observed = _count(retailer.get("observed_locations"))
            search_observed = _count(retailer.get("search_observed_locations"))
            eligible = _count(retailer.get("eligible_locations"))
            expected_status = "available" if products else "unavailable"
            check(
                all(product_ids)
                and len(product_ids) == len(set(product_ids))
                and sku_count == search_skus == len(products)
                and retailer.get("status") == expected_status,
                "price_architecture_retailer_skus_invalid",
                "Retailer SKU population does not reconcile to its status.",
                path,
                retailer_id=retailer_id,
            )
            check(
                observed == stores + services and search_observed == observed,
                "price_architecture_retailer_distribution_invalid",
                "Retailer distribution does not reconcile store and service-area evidence.",
                path,
                retailer_id=retailer_id,
            )
            if products:
                product_store_counts = [
                    _count(product.get("distribution_store_count")) for product in products
                ]
                product_service_counts = [
                    _count(product.get("service_area_presence_count")) for product in products
                ]
                check(
                    max(product_store_counts, default=0) <= stores <= sum(product_store_counts)
                    and max(product_service_counts, default=0)
                    <= services
                    <= sum(product_service_counts),
                    "price_architecture_retailer_distribution_bounds_invalid",
                    "Retailer union footprint falls outside product distribution bounds.",
                    path,
                    retailer_id=retailer_id,
                )
            counts = seller_counts[retailer_id]
            first_party = _count(retailer.get("verified_first_party_skus"))
            seller_unverified = _count(retailer.get("seller_unverified_skus"))
            not_governed = _count(retailer.get("seller_not_governed_skus"))
            check(
                first_party == counts["verified_first_party"]
                and seller_unverified == counts["seller_unverified"]
                and not_governed == counts["not_governed"]
                and first_party + seller_unverified + not_governed == sku_count,
                "price_architecture_seller_counts_invalid",
                "Seller-governance counts do not reconcile to products.",
                path,
                retailer_id=retailer_id,
            )
            if retailer.get("status") == "unavailable":
                valid_unavailable = (
                    sku_count == 0
                    and stores == services == observed == search_observed == search_skus == 0
                    and first_party == seller_unverified == not_governed == 0
                    and _nonblank(retailer.get("reason"))
                )
                if retailer_id not in cell_retailer_ids:
                    valid_unavailable = (
                        valid_unavailable
                        and eligible == 0
                        and retailer.get("population_checksum") is None
                    )
                check(
                    valid_unavailable,
                    "price_architecture_unavailable_retailer_invalid",
                    "Unavailable retailer is not an explicit zero-valued, reasoned row.",
                    path,
                    retailer_id=retailer_id,
                )
            elif retailer_id in cell_retailer_ids:
                check(
                    _nonblank(retailer.get("population_checksum")),
                    "price_architecture_population_checksum_invalid",
                    "Available retailer lacks a population checksum.",
                    f"{path}.population_checksum",
                    retailer_id=retailer_id,
                )

        for rung_index, rung in enumerate(rungs):
            for cell_position, cell in enumerate(_rows(rung.get("cells"))):
                retailer_id = str(cell.get("retailer_id") or "")
                retailer_skus = _count(retailer_index[retailer_id].get("sku_count"))
                cell_skus = _count(cell.get("sku_count"))
                check(
                    _close(cell.get("assortment_share"), _rate(cell_skus, retailer_skus)),
                    "price_architecture_cell_share_invalid",
                    "Cell assortment share does not reconcile.",
                    f"rungs[{rung_index}].cells[{cell_position}].assortment_share",
                    retailer_id=retailer_id,
                )

        summary = dict(document.get("summary") or {})
        anchor_products = products_by_retailer.get(anchor_id, [])
        competitor_skus = sum(
            len(products)
            for retailer_id, products in products_by_retailer.items()
            if retailer_id != anchor_id
        )
        max_competitor_skus = max(competitor_counts, default=0)
        crowded_ids = {
            str(rung.get("id"))
            for rung, count in zip(rungs, competitor_counts, strict=True)
            if count == max_competitor_skus
        }
        check(
            _count(summary.get("rung_count")) == len(rungs)
            and _count(summary.get("anchor_skus")) == len(anchor_products)
            and _count(summary.get("competitor_skus")) == competitor_skus
            and _count(summary.get("whitespace_rung_count"))
            == sum(count == 0 for count in competitor_counts)
            and str(summary.get("most_crowded_rung_id")) in crowded_ids,
            "price_architecture_summary_invalid",
            "Matrix summary does not reconcile to product rows.",
            "summary",
        )
        anchor_price_points = _count(summary.get("anchor_price_points"))
        if filters.get("mode") == "benchmark_anchored":
            rung_anchor_prices = [rung.get("anchor_price") for rung in rungs]
            check(
                all(price is not None and _number(price) > 0 for price in rung_anchor_prices)
                and len({_number(price) for price in rung_anchor_prices}) == anchor_price_points,
                "price_architecture_anchor_price_points_invalid",
                "Benchmark price-point count does not reconcile to anchored rungs.",
                "summary.anchor_price_points",
            )
        elif filters.get("brand") is None:
            check(
                anchor_price_points
                == len({_number(row.get("median_price")) for row in anchor_products}),
                "price_architecture_anchor_price_points_invalid",
                "Benchmark price-point count does not reconcile to benchmark products.",
                "summary.anchor_price_points",
            )
    except (KeyError, TypeError, ValueError) as exc:
        findings.append(
            _finding(
                "price_architecture_semantic_audit_error",
                "Price Architecture matrix could not be semantically certified.",
                path="<root>",
                error=str(exc),
            )
        )
    return findings
