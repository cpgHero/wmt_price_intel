from __future__ import annotations

import pytest

from rci_api.report_publication import _canonical_catalog_retailer_ids


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
