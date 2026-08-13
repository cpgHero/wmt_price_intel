from __future__ import annotations

import csv
import json
from copy import deepcopy
from pathlib import Path

import pytest

from rci_contracts import ContractError, validate_document, validate_handoff, validate_instance

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def test_supplied_handoff_documents_validate() -> None:
    assert validate_handoff(REPOSITORY_ROOT) >= 7


def test_provider_error_contract_accepts_normalized_failure(tmp_path: Path) -> None:
    document = tmp_path / "provider-error.json"
    document.write_text(
        json.dumps(
            {
                "success": False,
                "provider": "metricscart",
                "failure_class": "rate_limit",
                "should_retry": True,
            }
        ),
        encoding="utf-8",
    )

    validate_document(REPOSITORY_ROOT, "provider-error.schema.json", document)


def test_contract_failure_has_document_path(tmp_path: Path) -> None:
    document = tmp_path / "invalid.json"
    document.write_text("{}", encoding="utf-8")

    with pytest.raises(ContractError, match=r"invalid\.json"):
        validate_document(REPOSITORY_ROOT, "provider-error.schema.json", document)


def test_product_detail_catalog_reconciles_to_supplied_endpoint_source() -> None:
    catalog = json.loads(
        (REPOSITORY_ROOT / "config/product-detail-catalog.json").read_text(encoding="utf-8")
    )
    configured = {(row["provider_retailer"], row["domain"]): row for row in catalog["endpoints"]}
    with (REPOSITORY_ROOT / "source_material/metricscart_product_details_by_zipcode_apis.csv").open(
        newline="", encoding="utf-8-sig"
    ) as handle:
        supplied = list(csv.DictReader(handle))

    assert len(supplied) == len(configured) == 10
    for row in supplied:
        endpoint = configured[(row["provider"], row["domain"])]
        assert endpoint["endpoint_id"] == row["endpoint_id"]
        assert endpoint["method"] == row["method"]
        assert endpoint["path"].rstrip("/") == row["inferred_metricscart_path"].rstrip("/")
        assert endpoint["credits_per_successful_page"] == int(row["credits"])
        assert endpoint["required_params"] == (
            row["required_params"].split("|") if row["required_params"] else []
        )
        assert endpoint["supported_params"] == row["all_params"].split("|")


def test_phase_9_5_contracts_preserve_identifiers_and_source_authority() -> None:
    snapshot = json.loads(
        (REPOSITORY_ROOT / "examples/product-detail-snapshot.aldi.json").read_text(encoding="utf-8")
    )

    assert snapshot["request_context"]["product_id"] == "0000000000008696"
    assert snapshot["request_context"]["store"] == "479-149"
    assert snapshot["request_context"]["zipcode"] == "90001"
    assert snapshot["source_authority"] == {
        "serp_price_authoritative": True,
        "serp_availability_authoritative": True,
        "pdp_identity_authoritative": True,
        "pdp_package_semantics_allowed": True,
    }


def test_price_monitoring_examples_are_contract_valid_and_search_authoritative() -> None:
    observation = json.loads(
        (REPOSITORY_ROOT / "examples/price-observation.example.json").read_text()
    )
    view = json.loads((REPOSITORY_ROOT / "examples/price-monitoring-view.example.json").read_text())

    validate_instance(
        REPOSITORY_ROOT,
        "price-observation.schema.json",
        observation,
        label="price observation example",
    )
    validate_instance(
        REPOSITORY_ROOT,
        "price-monitoring-view.schema.json",
        view,
        label="price monitoring view example",
    )
    assert observation["source_authority"] == "search_location_observation"
    assert view["source"]["authority"] == "Search"


def test_agent_contract_forbids_authoritative_metric_computation() -> None:
    output = json.loads(
        (REPOSITORY_ROOT / "examples/agent-output.ground-beef-insight.json").read_text(
            encoding="utf-8"
        )
    )
    output["authoritative_metrics_computed"] = True

    with pytest.raises(ContractError, match="authoritative_metrics_computed"):
        validate_instance(
            REPOSITORY_ROOT,
            "agent-output.schema.json",
            output,
            label="invalid-agent-output",
        )


def test_study_discovery_contract_preserves_separate_paid_approval_gates() -> None:
    study = json.loads(
        (REPOSITORY_ROOT / "examples/study-discovery.example.json").read_text(encoding="utf-8")
    )

    validate_instance(
        REPOSITORY_ROOT,
        "study-discovery.schema.json",
        study,
        label="study-discovery",
    )
    assert study["approval_state"]["search"]["status"] == "not_requested"
    assert study["approval_state"]["pdp"]["status"] == "not_requested"
    assert study["approval_state"]["ai"]["status"] == "not_requested"


def test_discovery_collection_allows_no_product_pack_but_analysis_does_not() -> None:
    discovery = {
        "id": "study-00000000-0000-0000-0000-000000000099",
        "name": "Discovery Test",
        "version": "1.0.0",
        "purpose": "study_discovery",
        "benchmark_retailer": "walmart_us",
        "product_pack": None,
        "study_discovery": {
            "study_id": "00000000-0000-0000-0000-000000000099",
            "query_plan_checksum": "a" * 64,
        },
        "query": {"keyword": "milk"},
        "retailers": [
            {
                "retailer_id": "walmart_us",
                "adapter_id": "metricscart_walmart_search_zipcode_v2",
                "enabled": True,
            }
        ],
        "geography": {"strategy": "custom_zips", "zipcodes": ["72712"]},
        "pagination": {"max_pages": 1, "stop_on_empty": True},
        "analysis": None,
        "delivery": {"web_report": False, "excel": False, "leadership_email": False},
    }
    validate_instance(
        REPOSITORY_ROOT,
        "collection-definition.schema.json",
        discovery,
        label="discovery collection",
    )

    invalid = deepcopy(discovery)
    invalid["purpose"] = "analysis"
    invalid["study_discovery"] = None
    with pytest.raises(ContractError, match="product_pack"):
        validate_instance(
            REPOSITORY_ROOT,
            "collection-definition.schema.json",
            invalid,
            label="analysis without Product Pack",
        )


def test_analysis_result_v2_requires_narrative_metric_evidence() -> None:
    result = json.loads(
        (REPOSITORY_ROOT / "examples/analysis-result-v2.ground-beef.json").read_text(
            encoding="utf-8"
        )
    )
    invalid = deepcopy(result)
    invalid["narratives"]["sections"][0]["metric_refs"] = []

    with pytest.raises(ContractError, match="metric_refs"):
        validate_instance(
            REPOSITORY_ROOT,
            "analysis-result-v2.schema.json",
            invalid,
            label="invalid-analysis-result-v2",
        )


def test_collection_geography_resolution_resolves_shared_request_schema() -> None:
    document = {
        "id": "00000000-0000-0000-0000-000000000201",
        "request": {
            "primary_retailer_id": "walmart_us",
            "competitor_retailer_ids": ["aldi_us"],
            "country": "USA",
            "primary_selection": {"mode": "custom_zips", "zipcodes": ["03038"]},
            "competitor_correspondence": {"mode": "same_zip"},
        },
        "checksum": "a" * 64,
        "status": "ready",
        "counts": {"total": 0, "primary": 0, "competitors": {"aldi_us": 0}},
        "locations": [],
        "edges": [],
        "created_at": "2026-08-11T00:00:00Z",
    }
    validate_instance(
        REPOSITORY_ROOT,
        "collection-geography-resolution.schema.json",
        document,
        label="collection-geography-resolution",
    )

    invalid = deepcopy(document)
    invalid["request"]["primary_selection"] = {"mode": "not-a-mode"}
    with pytest.raises(ContractError, match="not-a-mode"):
        validate_instance(
            REPOSITORY_ROOT,
            "collection-geography-resolution.schema.json",
            invalid,
            label="invalid-collection-geography-resolution",
        )
