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
    overrides = json.loads(
        (REPOSITORY_ROOT / "config/metricscart-endpoint-overrides.json").read_text(encoding="utf-8")
    )
    configured = {(row["retailer_id"], row["endpoint_id"]): row for row in catalog["endpoints"]}
    approved_paths = {
        (row["retailer_id"], row["endpoint_id"]): row for row in overrides["overrides"]
    }
    with (REPOSITORY_ROOT / catalog["source"]).open(newline="", encoding="utf-8-sig") as handle:
        supplied = list(csv.DictReader(handle))

    assert len(supplied) == len(configured) == 20
    for row in supplied:
        key = (row["retailer_id"], row["endpoint_id"])
        endpoint = configured[key]
        assert endpoint["endpoint_id"] == row["endpoint_id"]
        assert endpoint["provider_retailer"] == row["provider"]
        assert endpoint["domain"] == row["domain"]
        assert endpoint["method"] == row["method"]
        if endpoint["path"].rstrip("/") != row["inferred_metricscart_path"].rstrip("/"):
            override = approved_paths[key]
            assert override["provider_catalog_path"] == row["inferred_metricscart_path"]
            assert override["runtime_path"] == endpoint["path"]
        assert endpoint["credits_per_successful_page"] == int(row["credits"])
        assert endpoint["required_params"] == (
            row["required_params"].split("|") if row["required_params"] else []
        )
        assert endpoint["supported_params"] == row["all_params"].split("|")

    assert configured[("kroger_us", "105")]["paid_calls_enabled"] is True
    assert configured[("kroger_us", "105")]["path"] == "/kroger/pdp/zipcode/"
    assert approved_paths[("kroger_us", "105")]["disposition"] == ("owner_verified_runtime_path")
    assert configured[("target_us", "172")]["path"] == "/mc/target/pdp/zipcode/"
    assert configured[("target_us", "172")]["identity_param"] == "url"
    assert approved_paths[("target_us", "172")]["runtime_identity_param"] == "url"
    assert configured[("sams_club_us", "155")]["path"] == "/mc/samsclub/pdp/zipcode/"
    assert configured[("sams_club_us", "155")]["identity_param"] == "url"
    assert approved_paths[("sams_club_us", "155")]["runtime_identity_param"] == "url"
    assert configured[("trader_joes_us", "178")]["product_id_left_pad_width"] == 6
    assert approved_paths[("trader_joes_us", "178")]["product_id_left_pad_width"] == 6


def test_normalized_metricscart_catalog_has_full_auditable_provenance() -> None:
    catalog = json.loads(
        (REPOSITORY_ROOT / "config/metricscart-api-catalog-20260816.json").read_text(
            encoding="utf-8"
        )
    )
    manifest = json.loads(
        (
            REPOSITORY_ROOT / "source_material/metricscart-api-catalog-20260816.manifest.json"
        ).read_text(encoding="utf-8")
    )

    assert catalog["counts"] == {
        "retailers": 81,
        "endpoints": 217,
        "active_endpoints": 217,
        "endpoints_with_sample_response": 217,
    }
    assert manifest["archive_crc_valid"] is True
    assert manifest["source_archive"] == catalog["source_archive"]
    assert len(manifest["files"]) == 7
    assert all(len(row["sample_response"]["sha256"]) == 64 for row in catalog["endpoints"])


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
    map_view = json.loads(
        (REPOSITORY_ROOT / "examples/price-monitoring-map.example.json").read_text()
    )

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
    validate_instance(
        REPOSITORY_ROOT,
        "price-monitoring-map.schema.json",
        map_view,
        label="price monitoring map example",
    )
    assert observation["source_authority"] == "search_location_observation"
    assert view["source"]["authority"] == "Search"


def test_canonical_report_dataset_contract_preserves_reporting_trust_boundaries() -> None:
    dataset = json.loads(
        (REPOSITORY_ROOT / "examples/canonical-report-dataset.bananas.json").read_text()
    )

    validate_instance(
        REPOSITORY_ROOT,
        "canonical-report-dataset.schema.json",
        dataset,
        label="canonical bananas report dataset example",
    )

    relationship = dataset["product_relationships"][0]
    assert relationship["benchmark_product"]["retailer_product_id"] == "44390948"
    assert relationship["benchmark_product"]["seller_status"] == "qualified"
    assert dataset["contracts"]["distribution"] == {
        "version": "1.0.0",
        "basis": "positive_price_store_search_result",
        "grain": "retailer_product_id_x_store_id",
        "deduplication": "distinct_store_id_per_product",
        "price_rule": "price_gt_zero",
        "inventory_claim": False,
        "stock_status_used": False,
        "sponsorship_used": False,
        "extrapolation": False,
    }
    assert dataset["price_normalization"]["zero_price_sentinel_rule"] == (
        "zero_regular_or_discounted_price_is_missing"
    )


def test_canonical_report_dataset_rejects_zero_prices_inventory_claims_and_bad_ids() -> None:
    dataset = json.loads(
        (REPOSITORY_ROOT / "examples/canonical-report-dataset.bananas.json").read_text()
    )

    zero_reporting_price = deepcopy(dataset)
    zero_reporting_price["product_relationships"][0]["benchmark_product"]["price"][
        "reporting_price"
    ] = 0
    with pytest.raises(ContractError):
        validate_instance(
            REPOSITORY_ROOT,
            "canonical-report-dataset.schema.json",
            zero_reporting_price,
            label="canonical report dataset with zero reporting price",
        )

    zero_discounted_price = deepcopy(dataset)
    zero_discounted_price["product_relationships"][0]["competitor_product"]["price"][
        "discounted_price"
    ] = 0
    with pytest.raises(ContractError):
        validate_instance(
            REPOSITORY_ROOT,
            "canonical-report-dataset.schema.json",
            zero_discounted_price,
            label="canonical report dataset with zero discounted price sentinel",
        )

    inventory_claim = deepcopy(dataset)
    inventory_claim["contracts"]["distribution"]["inventory_claim"] = True
    with pytest.raises(ContractError):
        validate_instance(
            REPOSITORY_ROOT,
            "canonical-report-dataset.schema.json",
            inventory_claim,
            label="canonical report dataset with inventory claim",
        )

    numeric_product_id = deepcopy(dataset)
    numeric_product_id["product_relationships"][0]["benchmark_product"]["retailer_product_id"] = (
        44390948
    )
    with pytest.raises(ContractError):
        validate_instance(
            REPOSITORY_ROOT,
            "canonical-report-dataset.schema.json",
            numeric_product_id,
            label="canonical report dataset with numeric product id",
        )

    unqualified_benchmark_seller = deepcopy(dataset)
    unqualified_benchmark_seller["product_relationships"][0]["benchmark_product"][
        "seller_status"
    ] = "not_qualified"
    with pytest.raises(ContractError):
        validate_instance(
            REPOSITORY_ROOT,
            "canonical-report-dataset.schema.json",
            unqualified_benchmark_seller,
            label="canonical report dataset with unqualified benchmark seller",
        )


def test_distribution_contracts_reject_inventory_fields_and_invalid_store_identity() -> None:
    observation = json.loads(
        (REPOSITORY_ROOT / "examples/price-observation.example.json").read_text()
    )
    organic_observation = deepcopy(observation)
    organic_observation["is_sponsored"] = False
    validate_instance(
        REPOSITORY_ROOT,
        "price-observation.schema.json",
        organic_observation,
        label="organic positive-price Search observation",
    )

    inventory_claim = deepcopy(observation)
    inventory_claim["in_stock"] = True

    with pytest.raises(ContractError):
        validate_instance(
            REPOSITORY_ROOT,
            "price-observation.schema.json",
            inventory_claim,
            label="Search observation containing a store-level inventory claim",
        )

    missing_store_identity = deepcopy(observation)
    missing_store_identity["distribution_store_id"] = None
    with pytest.raises(ContractError):
        validate_instance(
            REPOSITORY_ROOT,
            "price-observation.schema.json",
            missing_store_identity,
            label="store observation missing its distribution store ID",
        )

    map_view = json.loads(
        (REPOSITORY_ROOT / "examples/price-monitoring-map.example.json").read_text()
    )
    not_observed_with_price = deepcopy(map_view)
    not_observed_with_price["points"][2]["search_observed"] = True
    not_observed_with_price["points"][2]["price"] = 12.34

    with pytest.raises(ContractError):
        validate_instance(
            REPOSITORY_ROOT,
            "price-monitoring-map.schema.json",
            not_observed_with_price,
            label="not-observed map point claiming Search price evidence",
        )

    zero_reference_price = deepcopy(map_view)
    zero_reference_price["reference_price"] = 0
    with pytest.raises(ContractError):
        validate_instance(
            REPOSITORY_ROOT,
            "price-monitoring-map.schema.json",
            zero_reference_price,
            label="zero map reference price",
        )

    view = json.loads((REPOSITORY_ROOT / "examples/price-monitoring-view.example.json").read_text())
    zero_aggregate_price = deepcopy(view)
    zero_aggregate_price["price_distribution"]["observation_median"] = 0
    with pytest.raises(ContractError):
        validate_instance(
            REPOSITORY_ROOT,
            "price-monitoring-view.schema.json",
            zero_aggregate_price,
            label="zero aggregate price",
        )


def test_matching_v2_examples_preserve_evidence_and_search_price_authority() -> None:
    identity = json.loads(
        (REPOSITORY_ROOT / "examples/product-identity-evidence.milk.json").read_text()
    )
    edge = json.loads((REPOSITORY_ROOT / "examples/product-match-edge-v2.milk.json").read_text())
    comparison = json.loads(
        (REPOSITORY_ROOT / "examples/local-comparison-observation-v2.milk.json").read_text()
    )

    validate_instance(
        REPOSITORY_ROOT,
        "product-identity-evidence.schema.json",
        identity,
        label="matching v2 identity evidence",
    )
    validate_instance(
        REPOSITORY_ROOT,
        "product-match-edge-v2.schema.json",
        edge,
        label="matching v2 edge",
    )
    validate_instance(
        REPOSITORY_ROOT,
        "local-comparison-observation-v2.schema.json",
        comparison,
        label="matching v2 local comparison",
    )

    assert edge["evidence_coverage"]["critical_coverage"] == 1
    assert comparison["source_authority"] == "search_location_observation"
    assert comparison["result"]["competitor_minus_benchmark"] == pytest.approx(-0.09)


def test_matching_v2_synthetic_gold_fixture_cannot_claim_release_review() -> None:
    gold_set = json.loads((REPOSITORY_ROOT / "examples/matching-v2-gold-set.milk.json").read_text())
    validate_instance(
        REPOSITORY_ROOT,
        "matching-v2-gold-set.schema.json",
        gold_set,
        label="matching v2 synthetic gold set",
    )
    gold_set["purpose"] = "release_certification"

    with pytest.raises(ContractError, match="adjudicated"):
        validate_instance(
            REPOSITORY_ROOT,
            "matching-v2-gold-set.schema.json",
            gold_set,
            label="invalid release gold set",
        )


def test_matching_v2_review_queue_is_explicitly_non_authoritative() -> None:
    queue = json.loads(
        (REPOSITORY_ROOT / "examples/matching-v2-review-queue.milk.json").read_text()
    )
    validate_instance(
        REPOSITORY_ROOT,
        "matching-v2-review-queue.schema.json",
        queue,
        label="matching v2 review queue",
    )

    assert queue["authoritative"] is False
    assert {case["review_state"] for case in queue["cases"]} == {"pending"}


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
