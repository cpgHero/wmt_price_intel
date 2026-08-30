"""Canonical MetricsCart request construction shared by planning and execution.

The canonical request identity must describe the request that the provider
actually receives.  Planning-only metadata is deliberately excluded.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote_plus

PROTECTED_REQUEST_OVERRIDES = frozenset({"x-api-key", "page", "zipcode", "store"})


def _checksum(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def provider_request_contract_from_catalog_item(item: Mapping[str, Any]) -> dict[str, Any]:
    """Return only catalog fields that can alter an outbound Search request."""

    contract = {
        "retailer_id": str(item["id"]),
        "adapter_id": str(item.get("adapter_id") or ""),
        "method": str(item.get("method", "GET")).upper(),
        "path": str(item["endpoint"]),
        "supported_params": sorted(str(value) for value in item.get("supported_params", [])),
        "required_params": sorted(str(value) for value in item.get("required_params", [])),
        "default_sort": (str(item["default_sort"]) if item.get("default_sort") else None),
        "default_request_params": {
            str(key): value for key, value in item.get("default_request_params", {}).items()
        },
    }
    if not contract["adapter_id"]:
        raise ValueError(f"retailer {contract['retailer_id']!r} has no adapter_id")
    return contract


def provider_request_contract_from_spec(
    *,
    retailer_id: str,
    adapter_id: str,
    endpoint: str,
    method: str,
    supported_params: tuple[str, ...],
    required_params: tuple[str, ...],
    default_sort: str | None,
    default_request_params: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "retailer_id": retailer_id,
        "adapter_id": adapter_id,
        "method": method.upper(),
        "path": endpoint,
        "supported_params": sorted(supported_params),
        "required_params": sorted(required_params),
        "default_sort": default_sort,
        "default_request_params": dict(default_request_params),
    }


def build_effective_provider_request(
    row: Mapping[Any, Any],
    *,
    provider_contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the exact provider request plus its frozen catalog checksum.

    New tasks carry ``_provider_request_contract`` in their immutable request
    payload.  A caller may supply the current catalog contract for legacy tasks.
    When both exist they must agree, preventing silent endpoint/default drift.
    """

    payload = dict(row["request_payload"])
    frozen = payload.get("_provider_request_contract")
    if frozen is not None and not isinstance(frozen, Mapping):
        raise ValueError("_provider_request_contract must be an object")
    if provider_contract is None:
        provider_contract = frozen
    elif frozen is not None and _checksum(dict(frozen)) != _checksum(dict(provider_contract)):
        raise ValueError("task provider request contract differs from the active retailer catalog")
    if provider_contract is None:
        raise ValueError("provider request identity requires a frozen or supplied catalog contract")

    contract = dict(provider_contract)
    retailer_id = str(row["retailer_id"])
    adapter_id = str(row["adapter_id"])
    if str(contract.get("retailer_id") or "") != retailer_id:
        raise ValueError("provider request contract retailer does not match the task")
    if str(contract.get("adapter_id") or "") != adapter_id:
        raise ValueError("provider request contract adapter does not match the task")

    supported = {str(value) for value in contract.get("supported_params", [])}
    params: dict[str, Any] = {
        str(key): value for key, value in dict(contract.get("default_request_params") or {}).items()
    }
    if "zipcode" in supported:
        params["zipcode"] = str(row["zipcode"])
    if "page" in supported:
        params["page"] = int(row["page_number"])

    keyword = str(payload.get("keyword") or "").strip()
    if retailer_id == "amazon_us_same_day":
        template = payload.get("amazon_same_day_url_template")
        if not isinstance(template, str) or not template.strip():
            raise ValueError("Amazon Same Day requires amazon_same_day_url_template")
        params["url"] = template.replace("{{keyword}}", quote_plus(keyword))
    else:
        if not keyword:
            raise ValueError(f"{retailer_id} requires a keyword")
        params["keyword"] = keyword
        if "store" in supported:
            store_number = row.get("store_number")
            if store_number is None:
                raise ValueError(f"{retailer_id} requires a store number")
            params["store"] = str(store_number)

    sort = payload.get("sort") or contract.get("default_sort")
    if sort and "sort" in supported:
        params["sort"] = str(sort)
    overrides = payload.get("request_overrides", {})
    if not isinstance(overrides, Mapping):
        raise ValueError("request_overrides must be an object")
    protected = PROTECTED_REQUEST_OVERRIDES.intersection(str(key) for key in overrides)
    if protected:
        raise ValueError(
            "request_overrides cannot set protected parameters: " + ", ".join(sorted(protected))
        )
    params.update({str(key): value for key, value in overrides.items() if value is not None})
    missing = [
        str(name) for name in contract.get("required_params", []) if not params.get(str(name))
    ]
    if missing:
        raise ValueError("missing required provider parameters: " + ", ".join(missing))

    normalized_contract = {
        "retailer_id": retailer_id,
        "adapter_id": adapter_id,
        "method": str(contract.get("method", "GET")).upper(),
        "path": str(contract["path"]),
        "supported_params": sorted(supported),
        "required_params": sorted(str(value) for value in contract.get("required_params", [])),
        "default_sort": contract.get("default_sort"),
        "default_request_params": dict(contract.get("default_request_params") or {}),
    }
    return {
        "retailer_id": retailer_id,
        "adapter_id": adapter_id,
        "catalog_contract_checksum": _checksum(normalized_contract),
        "method": normalized_contract["method"],
        "path": normalized_contract["path"],
        "params": params,
    }
