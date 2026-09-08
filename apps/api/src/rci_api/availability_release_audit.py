"""Independent semantic trust checks for availability-bearing read models."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from statistics import mean
from typing import Any

Finding = dict[str, Any]
_RATE_TOLERANCE = 0.00011
_VALUE_TOLERANCE = 0.0006


def _rows(value: object) -> list[dict[str, Any]]:
    return [dict(row) for row in value] if isinstance(value, list) else []


def _integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("value is not an integer count")
    return value


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("value is not numeric")
    return float(value)


def _close(left: object, right: object, tolerance: float = _VALUE_TOLERANCE) -> bool:
    if left is None or right is None:
        return left is right
    try:
        return abs(_number(left) - _number(right)) <= tolerance
    except ValueError:
        return False


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _finding(code: str, message: str, *, path: str, **context: object) -> Finding:
    return {
        "severity": "error",
        "code": code,
        "message": message,
        "context": {"path": path, **context},
    }


def audit_price_monitoring_catalog(
    document: Mapping[str, Any],
    *,
    expected_retailer_id: str | None = None,
) -> list[Finding]:
    """Reconcile publication catalog availability from independent aggregates."""

    findings: list[Finding] = []

    def check(condition: bool, code: str, message: str, path: str, **context: object) -> None:
        if not condition:
            findings.append(_finding(code, message, path=path, **context))

    try:
        check(
            document.get("schema_version") == "1.4.0",
            "price_catalog_contract_version_invalid",
            "Price Intelligence catalog is not on the current availability contract.",
            "schema_version",
            actual=document.get("schema_version"),
        )
        retailer = dict(document.get("retailer") or {})
        if expected_retailer_id is not None:
            check(
                retailer.get("id") == expected_retailer_id,
                "price_catalog_retailer_scope_mismatch",
                "Catalog retailer does not match its staged publication scope.",
                "retailer.id",
                expected=expected_retailer_id,
                actual=retailer.get("id"),
            )
        source = dict(document.get("source") or {})
        check(
            source.get("observation_schema_version") == "1.2.0",
            "price_catalog_observation_contract_invalid",
            "Catalog evidence was not projected from the current observation contract.",
            "source.observation_schema_version",
            actual=source.get("observation_schema_version"),
        )

        summary = dict(document.get("summary") or {})
        presence = dict(document.get("presence") or {})
        availability = dict(document.get("availability") or {})
        observed_locations = _integer(summary.get("observed_locations"))
        verified_locations = _integer(summary.get("verified_available_locations"))
        expected_locations = _integer(summary.get("expected_locations"))
        observed_products = _integer(summary.get("observed_products"))
        verified_products = _integer(summary.get("verified_available_products"))
        search_observations = _integer(summary.get("search_price_observations"))
        verified_observations = _integer(summary.get("verified_availability_observations"))
        check(
            0 < verified_locations <= observed_locations <= expected_locations,
            "price_catalog_location_counts_invalid",
            "Verified, Search-observed, and eligible location counts do not reconcile.",
            "summary",
            verified=verified_locations,
            observed=observed_locations,
            eligible=expected_locations,
        )
        check(
            0 < verified_products <= observed_products,
            "price_catalog_product_counts_invalid",
            "Verified and Search-observed product counts do not reconcile.",
            "summary",
            verified=verified_products,
            observed=observed_products,
        )
        check(
            0 < verified_observations <= search_observations,
            "price_catalog_observation_counts_invalid",
            "Verified availability observations exceed or lack Search evidence.",
            "summary",
            verified=verified_observations,
            search=search_observations,
        )
        check(
            _integer(summary.get("eligible_observations")) == verified_observations,
            "price_catalog_eligible_observations_invalid",
            "Eligible price observations differ from verified availability observations.",
            "summary.eligible_observations",
        )
        check(
            _integer(presence.get("observed_locations")) == observed_locations
            and _integer(presence.get("eligible_locations")) == expected_locations
            and _integer(presence.get("not_observed_locations"))
            == expected_locations - observed_locations,
            "price_catalog_presence_counts_invalid",
            "Catalog Search-presence counts do not reconcile to the summary.",
            "presence",
        )
        check(
            _close(
                presence.get("observed_presence_rate"),
                _rate(observed_locations, expected_locations),
                _RATE_TOLERANCE,
            ),
            "price_catalog_presence_rate_invalid",
            "Catalog Search-presence rate does not reconcile to its numerator and denominator.",
            "presence.observed_presence_rate",
        )
        out_locations = _integer(availability.get("explicitly_out_of_stock_locations"))
        unverified_locations = _integer(availability.get("unverified_locations"))
        check(
            availability.get("status") == "verified"
            and _integer(availability.get("verified_available_locations")) == verified_locations
            and _integer(availability.get("eligible_locations")) == expected_locations,
            "price_catalog_availability_summary_invalid",
            "Catalog availability status or totals differ from the verified summary.",
            "availability",
        )
        check(
            verified_locations + out_locations + unverified_locations == observed_locations,
            "price_catalog_availability_partition_invalid",
            "Verified, out-of-stock, and unverified locations do not partition Search presence.",
            "availability",
        )
        check(
            _close(
                availability.get("verified_availability_rate"),
                _rate(verified_locations, expected_locations),
                _RATE_TOLERANCE,
            ),
            "price_catalog_availability_rate_invalid",
            "Verified availability rate does not reconcile to eligible locations.",
            "availability.verified_availability_rate",
        )
        check(
            _integer(dict(document.get("price_distribution") or {}).get("observation_count"))
            == verified_observations
            and _integer(
                dict(document.get("search_price_distribution") or {}).get("observation_count")
            )
            == search_observations,
            "price_catalog_price_population_invalid",
            "Verified and Search price distributions use inconsistent observation populations.",
            "price_distribution",
        )

        products = _rows(document.get("products"))
        product_ids = [str(row.get("product_id") or "") for row in products]
        check(
            len(product_ids) == observed_products
            and all(product_ids)
            and len(product_ids) == len(set(product_ids)),
            "price_catalog_product_population_invalid",
            "Catalog product rows do not uniquely reconcile to the reported product count.",
            "products",
        )
        check(
            sum(_integer(row.get("verified_available_locations")) > 0 for row in products)
            == verified_products,
            "price_catalog_verified_product_total_invalid",
            "Catalog verified-product total does not reconcile to product rows.",
            "summary.verified_available_products",
        )
        product_search_observations_total = 0
        product_verified_observations_total = 0
        for index, product in enumerate(products):
            path = f"products[{index}]"
            product_verified_locations = _integer(product.get("verified_available_locations"))
            product_search_locations = _integer(product.get("search_observed_locations"))
            check(
                _integer(product.get("locations")) == product_verified_locations
                and 0 <= product_verified_locations <= product_search_locations,
                "price_catalog_product_location_counts_invalid",
                "Product footprint does not reconcile verified availability to Search presence.",
                path,
                product_id=product.get("product_id"),
            )
            for verified_field, search_field in (
                ("verified_available_states", "search_observed_states"),
                ("verified_available_cities", "search_observed_cities"),
                ("verified_available_zipcodes", "search_observed_zipcodes"),
            ):
                check(
                    _integer(product.get(verified_field)) <= _integer(product.get(search_field)),
                    "price_catalog_product_geography_counts_invalid",
                    "Verified product geography exceeds Search-observed geography.",
                    f"{path}.{verified_field}",
                    product_id=product.get("product_id"),
                )
            product_availability = dict(product.get("availability") or {})
            product_search_observations = _integer(product_availability.get("search_observations"))
            product_verified_observations = _integer(
                product_availability.get("verified_in_stock_observations")
            )
            product_search_observations_total += product_search_observations
            product_verified_observations_total += product_verified_observations
            product_out_observations = _integer(
                product_availability.get("explicitly_out_of_stock_observations")
            )
            product_unverified_observations = _integer(
                product_availability.get("unverified_observations")
            )
            known_observations = product_verified_observations + product_out_observations
            expected_status = "verified" if product_verified_observations else "unverified"
            check(
                product_availability.get("status") == expected_status
                and _integer(product_availability.get("known_observations")) == known_observations
                and _integer(product_availability.get("in_stock_observations"))
                == product_verified_observations
                and product_verified_observations
                + product_out_observations
                + product_unverified_observations
                == product_search_observations,
                "price_catalog_product_availability_observations_invalid",
                "Product availability observations do not form the governed partition.",
                f"{path}.availability",
                product_id=product.get("product_id"),
            )
            check(
                product_search_observations == product_search_locations
                and product_verified_observations == product_verified_locations,
                "price_catalog_product_grain_invalid",
                (
                    "Product observations do not reconcile to the canonical latest "
                    "product-location grain."
                ),
                f"{path}.availability",
                product_id=product.get("product_id"),
            )
            check(
                _integer(product.get("states"))
                == _integer(product.get("verified_available_states"))
                and _integer(product.get("cities"))
                == _integer(product.get("verified_available_cities")),
                "price_catalog_product_geography_alias_invalid",
                "Legacy product geography aliases are not verified-availability counts.",
                path,
                product_id=product.get("product_id"),
            )
            check(
                _close(
                    product_availability.get("rate"),
                    _rate(product_verified_observations, known_observations),
                    _RATE_TOLERANCE,
                ),
                "price_catalog_product_availability_rate_invalid",
                "Product availability rate does not reconcile to known stock observations.",
                f"{path}.availability.rate",
                product_id=product.get("product_id"),
            )
            product_out_locations = _integer(
                product_availability.get("explicitly_out_of_stock_locations")
            )
            product_unverified_locations = _integer(
                product_availability.get("unverified_locations")
            )
            check(
                _integer(product_availability.get("search_observed_locations"))
                == product_search_locations
                and _integer(product_availability.get("verified_available_locations"))
                == product_verified_locations
                and product_verified_locations
                + product_out_locations
                + product_unverified_locations
                == product_search_locations,
                "price_catalog_product_availability_locations_invalid",
                "Product availability locations do not partition Search-observed locations.",
                f"{path}.availability",
                product_id=product.get("product_id"),
            )
            product_presence = dict(product.get("presence") or {})
            eligible_product_locations = _integer(product_presence.get("eligible_locations"))
            check(
                _integer(product_presence.get("observed_locations")) == product_search_locations
                and eligible_product_locations >= product_search_locations
                and _integer(product_presence.get("not_observed_locations"))
                == eligible_product_locations - product_search_locations,
                "price_catalog_product_presence_invalid",
                "Product Search-presence counts do not reconcile.",
                f"{path}.presence",
                product_id=product.get("product_id"),
            )
            check(
                _close(
                    product_presence.get("observed_rate"),
                    _rate(product_search_locations, eligible_product_locations),
                    _RATE_TOLERANCE,
                )
                and _close(
                    product_presence.get("not_observed_rate"),
                    _rate(
                        eligible_product_locations - product_search_locations,
                        eligible_product_locations,
                    ),
                    _RATE_TOLERANCE,
                ),
                "price_catalog_product_presence_rates_invalid",
                "Product Search-presence rates do not reconcile.",
                f"{path}.presence",
                product_id=product.get("product_id"),
            )
            check(
                _integer(dict(product.get("price_stats") or {}).get("observation_count"))
                == product_verified_observations
                and _integer(dict(product.get("search_price_stats") or {}).get("observation_count"))
                == product_search_observations,
                "price_catalog_product_price_population_invalid",
                "Product price distributions do not use the declared evidence populations.",
                path,
                product_id=product.get("product_id"),
            )

        check(
            product_search_observations_total == search_observations
            and product_verified_observations_total == verified_observations,
            "price_catalog_product_observation_totals_invalid",
            "Product evidence populations do not reconcile to catalog totals.",
            "products",
        )

        brand_rows = _rows(document.get("brand_portfolio"))
        brand_types = [str(row.get("brand_type") or "") for row in brand_rows]
        check(
            len(brand_types) == len(set(brand_types)),
            "price_catalog_brand_population_invalid",
            "Brand portfolio contains duplicate brand-type rows.",
            "brand_portfolio",
        )
        for index, row in enumerate(brand_rows):
            check(
                _integer(row.get("locations"))
                == _integer(row.get("verified_available_locations"))
                <= _integer(row.get("search_observed_locations"))
                and _integer(row.get("products")) <= _integer(row.get("search_observed_products")),
                "price_catalog_brand_availability_invalid",
                "Brand footprint promotes Search presence beyond verified availability.",
                f"brand_portfolio[{index}]",
            )
        check(
            sum(_integer(row.get("observations")) for row in brand_rows) == search_observations
            and sum(_integer(row.get("products")) for row in brand_rows) == verified_products
            and sum(_integer(row.get("search_observed_products")) for row in brand_rows)
            == observed_products,
            "price_catalog_brand_totals_invalid",
            "Brand portfolio populations do not reconcile to catalog totals.",
            "brand_portfolio",
        )

        geography_rows = _rows(document.get("geographies"))
        geography_keys = [
            (str(row.get("level") or ""), str(row.get("key") or "")) for row in geography_rows
        ]
        check(
            bool(geography_rows)
            and all(level and key for level, key in geography_keys)
            and len(geography_keys) == len(set(geography_keys)),
            "price_catalog_geography_population_invalid",
            "Catalog geography rows are empty, duplicated, or unidentified.",
            "geographies",
        )
        for index, row in enumerate(geography_rows):
            geography_search_locations = _integer(row.get("search_observed_locations"))
            geography_verified_locations = _integer(row.get("verified_available_locations"))
            geography_out_locations = _integer(row.get("explicitly_out_of_stock_locations"))
            geography_unverified_locations = _integer(row.get("unverified_locations"))
            geography_observations = _integer(row.get("observations"))
            geography_verified_observations = _integer(
                row.get("verified_availability_observations")
            )
            check(
                _integer(row.get("locations")) == geography_verified_locations
                and geography_verified_locations
                + geography_out_locations
                + geography_unverified_locations
                == geography_search_locations,
                "price_catalog_geography_availability_invalid",
                "Geography location populations do not form the governed partition.",
                f"geographies[{index}]",
            )
            check(
                _integer(row.get("products"))
                == _integer(row.get("verified_available_products"))
                <= _integer(row.get("search_observed_products"))
                and 0 <= geography_verified_observations <= geography_observations,
                "price_catalog_geography_product_counts_invalid",
                "Geography verified products or observations exceed Search evidence.",
                f"geographies[{index}]",
            )
            check(
                _integer(dict(row.get("price_stats") or {}).get("observation_count"))
                == geography_verified_observations
                and _integer(dict(row.get("search_price_stats") or {}).get("observation_count"))
                == geography_observations,
                "price_catalog_geography_price_population_invalid",
                "Geography price populations differ from their evidence populations.",
                f"geographies[{index}]",
            )
        check(
            sum(_integer(row.get("observations")) for row in geography_rows) == search_observations
            and sum(
                _integer(row.get("verified_availability_observations")) for row in geography_rows
            )
            == verified_observations
            and sum(_integer(row.get("search_observed_locations")) for row in geography_rows)
            == observed_locations
            and sum(_integer(row.get("verified_available_locations")) for row in geography_rows)
            == verified_locations,
            "price_catalog_geography_totals_invalid",
            "Geography evidence populations do not reconcile to catalog totals.",
            "geographies",
        )

        location_rows = _rows(document.get("locations"))
        location_display = dict(document.get("location_display") or {})
        check(
            _integer(location_display.get("returned")) == len(location_rows)
            and _integer(location_display.get("total")) >= len(location_rows)
            and bool(location_display.get("sampled"))
            == (_integer(location_display.get("total")) > len(location_rows)),
            "price_catalog_location_display_invalid",
            "Location sample metadata does not reconcile to returned rows.",
            "location_display",
        )
        quality = dict(document.get("quality") or {})
        check(
            quality.get("status") != "blocked",
            "price_catalog_quality_blocked",
            "A catalog with blocking data-quality findings cannot be published.",
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
    """Recompute matrix totals and reject Search-only availability promotion."""

    findings: list[Finding] = []

    def check(condition: bool, code: str, message: str, path: str, **context: object) -> None:
        if not condition:
            findings.append(_finding(code, message, path=path, **context))

    try:
        check(
            document.get("schema_version") == "1.2.0",
            "price_architecture_contract_version_invalid",
            "Price Architecture is not on the current availability contract.",
            "schema_version",
            actual=document.get("schema_version"),
        )
        filters = dict(document.get("filters") or {})
        anchor_id = str(filters.get("anchor_retailer_id") or "")
        retailers = _rows(document.get("retailers"))
        retailer_ids = [str(row.get("id") or "") for row in retailers]
        check(
            bool(anchor_id) and all(retailer_ids) and len(retailer_ids) == len(set(retailer_ids)),
            "price_architecture_retailer_scope_invalid",
            "Price Architecture retailer scope is empty or duplicated.",
            "retailers",
        )
        if expected_retailer_ids is not None:
            expected_scope = {str(value) for value in expected_retailer_ids}
            check(
                set(retailer_ids) == expected_scope,
                "price_architecture_retailer_scope_mismatch",
                "Price Architecture retailer scope differs from the configured report scope.",
                "retailers",
                expected=sorted(expected_scope),
                actual=sorted(set(retailer_ids)),
            )
        retailer_index = {str(row.get("id")): row for row in retailers}
        available_retailer_ids = {
            retailer_id
            for retailer_id, row in retailer_index.items()
            if row.get("status") == "available"
        }
        if expected_catalog_retailer_ids is not None:
            expected_catalog_scope = {str(value) for value in expected_catalog_retailer_ids}
            check(
                available_retailer_ids == expected_catalog_scope,
                "price_architecture_catalog_scope_mismatch",
                ("Available Price Architecture retailers differ from the certified catalog scope."),
                "retailers",
                expected=sorted(expected_catalog_scope),
                actual=sorted(available_retailer_ids),
            )
        anchor = retailer_index.get(anchor_id, {})
        check(
            anchor.get("status") == "available" and _integer(anchor.get("sku_count")) > 0,
            "price_architecture_anchor_unavailable",
            "The benchmark retailer lacks verified products for price-rung construction.",
            "filters.anchor_retailer_id",
            anchor_retailer_id=anchor_id,
        )

        rungs = _rows(document.get("rungs"))
        rung_ids = [str(row.get("id") or "") for row in rungs]
        check(
            all(rung_ids)
            and len(rung_ids) == len(set(rung_ids))
            and [_integer(row.get("rank")) for row in rungs] == list(range(1, len(rungs) + 1)),
            "price_architecture_rungs_invalid",
            "Price Architecture rungs are duplicated or not contiguous.",
            "rungs",
        )
        products_by_retailer: dict[str, list[dict[str, Any]]] = defaultdict(list)
        seller_counts: dict[str, Counter[str]] = defaultdict(Counter)
        competitor_counts: list[int] = []
        for rung_index, rung in enumerate(rungs):
            path = f"rungs[{rung_index}]"
            cells = _rows(rung.get("cells"))
            cell_ids = [str(cell.get("retailer_id") or "") for cell in cells]
            check(
                all(cell_ids)
                and len(cell_ids) == len(set(cell_ids))
                and set(cell_ids) == available_retailer_ids,
                "price_architecture_cells_invalid",
                "A price rung does not contain exactly one cell per available retailer.",
                f"{path}.cells",
            )
            cell_index = {str(cell.get("retailer_id")): cell for cell in cells}
            anchor_product_ids = {
                str(row.get("product_id") or "") for row in _rows(rung.get("anchor_products"))
            }
            cell_anchor_product_ids = {
                str(row.get("product_id") or "")
                for row in _rows(cell_index.get(anchor_id, {}).get("products"))
            }
            check(
                anchor_product_ids == cell_anchor_product_ids,
                "price_architecture_anchor_products_invalid",
                "Rung anchor products differ from the benchmark cell.",
                f"{path}.anchor_products",
            )
            expected_competitor_skus = 0
            for cell_index_value, cell in enumerate(cells):
                retailer_id = str(cell.get("retailer_id") or "")
                products = _rows(cell.get("products"))
                check(
                    _integer(cell.get("sku_count")) == len(products),
                    "price_architecture_cell_sku_count_invalid",
                    "Cell SKU count does not reconcile to its product rows.",
                    f"{path}.cells[{cell_index_value}]",
                    retailer_id=retailer_id,
                )
                if (
                    retailer_id != anchor_id
                    and retailer_index.get(retailer_id, {}).get("status") == "available"
                ):
                    expected_competitor_skus += len(products)
                median_prices: list[float] = []
                for product_index, product in enumerate(products):
                    product_path = f"{path}.cells[{cell_index_value}].products[{product_index}]"
                    product_id = str(product.get("product_id") or "")
                    verified_locations = _integer(product.get("verified_available_locations"))
                    search_locations = _integer(product.get("search_observed_locations"))
                    minimum = _number(product.get("minimum_price"))
                    median_price = _number(product.get("median_price"))
                    maximum = _number(product.get("maximum_price"))
                    median_prices.append(median_price)
                    check(
                        _integer(product.get("observed_locations")) == verified_locations
                        and 0 < verified_locations <= search_locations,
                        "price_architecture_product_availability_invalid",
                        (
                            "Architecture product footprint is not verified or exceeds "
                            "Search presence."
                        ),
                        product_path,
                        retailer_id=retailer_id,
                        product_id=product_id,
                    )
                    check(
                        0 < minimum <= median_price <= maximum,
                        "price_architecture_product_price_invalid",
                        "Architecture product price range is invalid.",
                        product_path,
                        retailer_id=retailer_id,
                        product_id=product_id,
                    )
                    lower = rung.get("lower_bound")
                    upper = rung.get("upper_bound")
                    check(
                        (lower is None or median_price >= _number(lower))
                        and (upper is None or median_price < _number(upper)),
                        "price_architecture_product_rung_invalid",
                        "Product median price falls outside its declared rung.",
                        product_path,
                        retailer_id=retailer_id,
                        product_id=product_id,
                    )
                    products_by_retailer[retailer_id].append(product)
                    seller_counts[retailer_id][str(product.get("seller_status") or "")] += 1
                expected_average = round(mean(median_prices), 4) if median_prices else None
                check(
                    _close(cell.get("average_price"), expected_average),
                    "price_architecture_cell_average_invalid",
                    "Cell average price does not reconcile to product medians.",
                    f"{path}.cells[{cell_index_value}].average_price",
                    retailer_id=retailer_id,
                )
            competitor_counts.append(expected_competitor_skus)
            check(
                _integer(rung.get("competitor_sku_count")) == expected_competitor_skus,
                "price_architecture_rung_competitor_count_invalid",
                "Rung competitor SKU count does not reconcile to verified product rows.",
                f"{path}.competitor_sku_count",
            )

        for retailer_index_value, retailer in enumerate(retailers):
            retailer_id = str(retailer.get("id") or "")
            products = products_by_retailer.get(retailer_id, [])
            product_ids = [str(row.get("product_id") or "") for row in products]
            sku_count = _integer(retailer.get("sku_count"))
            verified_locations = _integer(retailer.get("verified_available_locations") or 0)
            observed_locations = _integer(retailer.get("observed_locations") or 0)
            search_locations = _integer(retailer.get("search_observed_locations") or 0)
            search_skus = _integer(retailer.get("search_observed_skus") or 0)
            expected_status = "available" if products else "unavailable"
            check(
                all(product_ids)
                and len(product_ids) == len(set(product_ids))
                and sku_count == len(products)
                and retailer.get("status") == expected_status,
                "price_architecture_retailer_skus_invalid",
                "Retailer SKU population is duplicated or does not reconcile to its status.",
                f"retailers[{retailer_index_value}]",
                retailer_id=retailer_id,
            )
            check(
                verified_locations == observed_locations <= search_locations
                and sku_count <= search_skus,
                "price_architecture_retailer_availability_invalid",
                ("Retailer verified products or footprint differ from or exceed Search presence."),
                f"retailers[{retailer_index_value}]",
                retailer_id=retailer_id,
            )
            counts = seller_counts[retailer_id]
            check(
                _integer(retailer.get("verified_first_party_skus"))
                == counts["verified_first_party"]
                and _integer(retailer.get("seller_unverified_skus")) == counts["seller_unverified"]
                and _integer(retailer.get("seller_not_governed_skus")) == counts["not_governed"]
                and sum(counts.values()) == sku_count,
                "price_architecture_seller_counts_invalid",
                "Retailer seller-governance counts do not reconcile to products.",
                f"retailers[{retailer_index_value}]",
                retailer_id=retailer_id,
            )
            if retailer.get("status") == "unavailable":
                check(
                    sku_count == 0
                    and verified_locations == 0
                    and observed_locations == 0
                    and search_locations == 0
                    and search_skus == 0
                    and _integer(retailer.get("eligible_locations") or 0) == 0
                    and sum(counts.values()) == 0
                    and bool(str(retailer.get("reason") or "").strip()),
                    "price_architecture_unavailable_retailer_invalid",
                    "Unavailable retailer is not an explicit zero-valued, reasoned row.",
                    f"retailers[{retailer_index_value}]",
                    retailer_id=retailer_id,
                )

        for rung_index, rung in enumerate(rungs):
            for cell_index_value, cell in enumerate(_rows(rung.get("cells"))):
                retailer_id = str(cell.get("retailer_id") or "")
                retailer_skus = _integer(retailer_index.get(retailer_id, {}).get("sku_count") or 0)
                cell_skus = _integer(cell.get("sku_count"))
                check(
                    _close(
                        cell.get("assortment_share"),
                        _rate(cell_skus, retailer_skus),
                        _RATE_TOLERANCE,
                    ),
                    "price_architecture_cell_share_invalid",
                    "Cell assortment share does not reconcile to retailer SKU count.",
                    f"rungs[{rung_index}].cells[{cell_index_value}].assortment_share",
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
            _integer(summary.get("rung_count")) == len(rungs)
            and _integer(summary.get("anchor_skus")) == len(anchor_products)
            and _integer(summary.get("competitor_skus")) == competitor_skus
            and _integer(summary.get("whitespace_rung_count"))
            == sum(count == 0 for count in competitor_counts)
            and str(summary.get("most_crowded_rung_id")) in crowded_ids,
            "price_architecture_summary_invalid",
            "Price Architecture summary does not reconcile to verified product rows.",
            "summary",
        )
        if filters.get("brand") is None:
            check(
                _integer(summary.get("anchor_price_points"))
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
