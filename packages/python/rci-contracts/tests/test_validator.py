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
        assert endpoint["path"] == row["inferred_metricscart_path"]
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
