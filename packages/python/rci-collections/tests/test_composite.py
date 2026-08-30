from __future__ import annotations

import json
from typing import Any

import pytest

import rci_collections.composite as composite_module
from rci_collections.composite import (
    ContinuationLineageComponent,
    PostgresCompositeEvidenceRepository,
    build_continuation_preview,
    build_exact_recovery_task_contracts,
    build_recovery_preview,
    canonical_request_key,
    composite_trust_state,
    effective_request_identity,
    evidence_outcome,
    outbound_query_contract,
    partition_uncovered_recovery_keys,
    recovery_adequacy,
    request_identity_provenance_manifest,
    resolve_task_precedence,
    retailer_collection_readiness,
)


def _provider_contract(retailer_id: str, adapter_id: str) -> dict[str, Any]:
    supported = ["keyword", "page", "zipcode", "sort"]
    required = ["keyword", "page", "zipcode"]
    if retailer_id == "amazon_us_same_day":
        supported = ["url", "page", "zipcode"]
        required = ["url", "page", "zipcode"]
    else:
        supported.append("store")
        required.append("store")
    return {
        "retailer_id": retailer_id,
        "adapter_id": adapter_id,
        "method": "GET",
        "path": f"/mc/{retailer_id}/search/zipcode/",
        "supported_params": supported,
        "required_params": required,
        "default_sort": "Best Match" if "sort" in supported else None,
        "default_request_params": {},
    }


def _task(
    task_id: str,
    scope: str,
    *,
    retailer_id: str = "walmart_us",
    status: str = "succeeded",
    gate_status: str = "passed",
    http_status: int | None = 200,
    failure_class: str | None = None,
    billable_credits: int = 2,
    raw_artifact_id: str | None = "artifact-base",
    is_preflight: bool = False,
) -> dict[str, Any]:
    zipcode = scope.rsplit(":", 1)[-1].zfill(5)
    payload = {
        "retailer_id": retailer_id,
        "adapter_id": f"metricscart_{retailer_id}_search_zipcode",
        "keyword": "milk",
        "zipcode": zipcode,
        "store_number": scope,
        "page": 1,
        "sort": "Best Match",
        "request_overrides": {},
        "_provider_request_contract": _provider_contract(
            retailer_id, f"metricscart_{retailer_id}_search_zipcode"
        ),
    }
    return {
        "id": task_id,
        "collection_run_id": "base-run",
        "retailer_id": retailer_id,
        "retailer_location_id": f"location-{scope}",
        "adapter_id": f"metricscart_{retailer_id}_search_zipcode",
        "location_scope_key": scope,
        "zipcode": zipcode,
        "store_number": scope,
        "page_number": 1,
        "max_pages": 1,
        "stop_on_empty": True,
        "stop_on_short_page": True,
        "credits_per_success": 2,
        "request_payload": payload,
        "request_fingerprint": f"fingerprint-{scope}",
        "status": status,
        "priority": 100,
        "attempt_count": 1,
        "max_attempts": 5,
        "is_preflight": is_preflight,
        "retailer_gate_status": gate_status,
        "http_status": http_status,
        "failure_class": failure_class,
        "billable_credits": billable_credits,
        "raw_artifact_id": raw_artifact_id,
        "result_count": 3 if status == "succeeded" else None,
    }


def _recovery(base: dict[str, Any], task_id: str, **changes: Any) -> dict[str, Any]:
    row = {**base, "id": task_id, "collection_run_id": "recovery-run"}
    row.update(changes)
    return row


def test_failed_gate_selects_only_uncalled_and_non_404_failures() -> None:
    rows = [
        _task("success", "location:1", gate_status="failed"),
        _task(
            "paid-404",
            "location:2",
            status="failed",
            gate_status="failed",
            http_status=404,
            failure_class="invalid_request",
            raw_artifact_id="artifact-404",
        ),
        _task(
            "cancelled",
            "location:3",
            status="cancelled",
            gate_status="failed",
            http_status=None,
            failure_class=None,
            billable_credits=0,
            raw_artifact_id=None,
        ),
        _task(
            "timeout",
            "location:4",
            status="failed",
            gate_status="failed",
            http_status=None,
            failure_class="timeout",
            billable_credits=0,
            raw_artifact_id=None,
        ),
    ]
    preview = build_recovery_preview("base-run", rows, definition_checksum="definition")

    assert {item.source_task_id for item in preview.items} == {"cancelled", "timeout"}
    assert preview.selected_task_count == 2
    assert preview.maximum_provider_attempts == 10
    assert preview.maximum_credits == 20
    assert preview.retailers[0].maximum_provider_attempts == 10
    assert preview.retailers[0].reused_successes == 1
    assert preview.retailers[0].retained_billable_404s == 1
    assert preview.retailers[0].retained_billable_404_credits == 2


def test_passed_gate_exposes_hard_failures_and_optional_transport_gaps() -> None:
    rows = [
        _task(
            "lease",
            "location:1",
            status="failed",
            http_status=500,
            failure_class="lease_exhausted",
            billable_credits=0,
            raw_artifact_id=None,
        ),
        _task(
            "schema",
            "location:2",
            status="failed",
            http_status=200,
            failure_class="schema_drift",
            raw_artifact_id="artifact-null",
        ),
        _task(
            "timeout",
            "location:3",
            status="failed",
            http_status=None,
            failure_class="timeout",
            billable_credits=0,
            raw_artifact_id=None,
        ),
    ]
    preview = build_recovery_preview("base-run", rows, definition_checksum="definition")

    assert {item.source_task_id for item in preview.items} == {"lease", "schema", "timeout"}
    by_id = {item.source_task_id: item for item in preview.items}
    assert by_id["lease"].required_for_assembly is True
    assert by_id["schema"].required_for_assembly is True
    assert by_id["timeout"].selection_reason == "transient_gap"
    assert by_id["timeout"].required_for_assembly is False
    assert preview.retailers[0].required_tasks == 2
    assert preview.retailers[0].optional_transient_tasks == 1
    assert evidence_outcome(rows[1]) == "contract_missing"
    assert evidence_outcome(rows[2]) == "zero_credit_missing"


def test_failure_only_preview_refuses_currently_ineligible_location_scope() -> None:
    row = _task(
        "cancelled-kroger",
        "location:legacy-seven-digit",
        retailer_id="kroger_us",
        status="cancelled",
        gate_status="failed",
        http_status=None,
        billable_credits=0,
        raw_artifact_id=None,
    )
    row["current_location_eligible"] = False

    with pytest.raises(ValueError, match="currently ineligible kroger_us location"):
        build_recovery_preview("base-run", [row], definition_checksum="definition")

    audit_only = build_recovery_preview(
        "base-run",
        [row],
        definition_checksum="definition",
        allow_ineligible_locations=True,
    )
    assert audit_only.selected_task_count == 1


async def test_offline_spend_authorization_rejects_request_controlled_credit_rate() -> None:
    repository = PostgresCompositeEvidenceRepository(  # type: ignore[arg-type]
        None, provider_request_contracts={}
    )

    with pytest.raises(ValueError, match=r"fixed at \$0\.002000"):
        await repository.authorize_recovery_spend(
            organization_id="organization",
            phase_key="phase-13.77",
            approved_credit_ceiling=100_000,
            unit_cost_usd="0.001",
            currency="USD",
            reason="owner authorized exactly $200",
            authorized_by="offline-platform-owner",
            collection_run_ids=("run-1",),
        )


def test_preview_is_order_independent_and_retailer_scoped() -> None:
    walmart = _task(
        "walmart-failure",
        "location:1",
        status="failed",
        http_status=500,
        failure_class="lease_exhausted",
        billable_credits=0,
        raw_artifact_id=None,
    )
    aldi = _task(
        "aldi-failure",
        "location:2",
        retailer_id="aldi_us",
        status="failed",
        http_status=500,
        failure_class="lease_exhausted",
        billable_credits=0,
        raw_artifact_id=None,
    )
    first = build_recovery_preview(
        "base-run",
        [walmart, aldi],
        definition_checksum="definition",
        retailer_ids=("aldi_us",),
    )
    second = build_recovery_preview(
        "base-run",
        [aldi, walmart],
        definition_checksum="definition",
        retailer_ids=("aldi_us",),
    )

    assert first.selection_checksum == second.selection_checksum
    assert first.base_snapshot_checksum == second.base_snapshot_checksum
    assert [item.source_task_id for item in first.items] == ["aldi-failure"]


def test_legacy_full_scope_precedence_preserves_one_lineage_row_per_request() -> None:
    base_success = _task("base-success", "location:1", raw_artifact_id="base-success-artifact")
    base_404 = _task(
        "base-404",
        "location:2",
        status="failed",
        http_status=404,
        failure_class="invalid_request",
        raw_artifact_id="base-404-artifact",
    )
    base_cancelled = _task(
        "base-cancelled",
        "location:3",
        status="cancelled",
        gate_status="failed",
        http_status=None,
        failure_class=None,
        billable_credits=0,
        raw_artifact_id=None,
    )
    base_hard = _task(
        "base-hard",
        "location:4",
        status="failed",
        gate_status="failed",
        http_status=500,
        failure_class="lease_exhausted",
        billable_credits=0,
        raw_artifact_id=None,
    )
    recovery = [
        _recovery(base_success, "recovery-success-duplicate", raw_artifact_id="duplicate"),
        _recovery(
            base_404,
            "recovery-404-duplicate",
            raw_artifact_id="recovery-404-artifact",
        ),
        _recovery(
            base_cancelled,
            "recovery-cancelled-gap",
            status="succeeded",
            gate_status="passed",
            http_status=200,
            failure_class=None,
            billable_credits=2,
            raw_artifact_id="recovered-cancelled-artifact",
        ),
        _recovery(
            base_hard,
            "recovery-hard-gap",
            status="succeeded",
            gate_status="passed",
            http_status=200,
            failure_class=None,
            billable_credits=2,
            raw_artifact_id="recovered-hard-artifact",
        ),
    ]
    approved = [
        canonical_request_key(base_cancelled),
        canonical_request_key(base_hard),
    ]
    resolved = resolve_task_precedence(
        [base_success, base_404, base_cancelled, base_hard],
        recovery,
        approved_recovery_keys=approved,
    )
    by_key = {row.canonical_request_key: row for row in resolved}

    assert len(resolved) == 4
    assert len(by_key) == 4
    assert by_key[canonical_request_key(base_success)].selected_task_id == "base-success"
    assert by_key[canonical_request_key(base_success)].selected_raw_artifact_id == (
        "base-success-artifact"
    )
    assert by_key[canonical_request_key(base_success)].redundant_task_ids == (
        "recovery-success-duplicate",
    )
    assert by_key[canonical_request_key(base_404)].selected_task_id == "base-404"
    assert by_key[canonical_request_key(base_404)].redundant_task_ids == ("recovery-404-duplicate",)
    assert by_key[canonical_request_key(base_cancelled)].selected_raw_artifact_id == (
        "recovered-cancelled-artifact"
    )
    assert by_key[canonical_request_key(base_hard)].selected_raw_artifact_id == (
        "recovered-hard-artifact"
    )


def test_legacy_extra_success_can_fill_a_non_usable_base_gap() -> None:
    base = _task(
        "base-tolerated-gap",
        "location:1",
        status="failed",
        http_status=None,
        failure_class="timeout",
        billable_credits=0,
        raw_artifact_id=None,
    )
    recovery = _recovery(
        base,
        "recovery-success",
        status="succeeded",
        http_status=200,
        failure_class=None,
        billable_credits=2,
        raw_artifact_id="recovery-artifact",
    )

    resolved = resolve_task_precedence([base], [recovery], approved_recovery_keys=())

    assert resolved[0].selected_task_id == "recovery-success"
    assert resolved[0].selected_raw_artifact_id == "recovery-artifact"
    assert resolved[0].superseded_task_id == "base-tolerated-gap"


def test_canonical_request_identity_ignores_run_and_unrelated_planning_metadata() -> None:
    base = _task("base", "location:1")
    changed = {
        **base,
        "id": "another-task",
        "collection_run_id": "another-run",
        "retailer_location_id": "another-location-row",
        "location_scope_key": "a-renamed-frozen-scope",
        "max_pages": 10,
        "stop_on_empty": False,
        "stop_on_short_page": False,
        "request_fingerprint": "another-planner-fingerprint",
        "is_preflight": True,
        "request_payload": {
            **base["request_payload"],
            "amazon_same_day_url_template": "https://irrelevant.example/{{keyword}}",
            "planning_note": "not outbound",
        },
    }

    assert canonical_request_key(base) == canonical_request_key(changed)
    assert effective_request_identity(changed)["params"]["keyword"] == "milk"


def test_canonical_request_identity_changes_for_each_effective_outbound_field() -> None:
    base = _task("base", "location:1")
    variants: list[dict[str, Any]] = [
        {
            **base,
            "adapter_id": "another-adapter",
            "request_payload": {
                **base["request_payload"],
                "_provider_request_contract": _provider_contract("walmart_us", "another-adapter"),
            },
        },
        {
            **base,
            "retailer_id": "aldi_us",
            "adapter_id": "metricscart_aldi_us_search_zipcode",
            "request_payload": {
                **base["request_payload"],
                "_provider_request_contract": _provider_contract(
                    "aldi_us", "metricscart_aldi_us_search_zipcode"
                ),
            },
        },
        {
            **base,
            "request_payload": {**base["request_payload"], "keyword": "whole milk"},
        },
        {**base, "zipcode": "90210"},
        {**base, "store_number": "9999"},
        {**base, "page_number": 2},
        {
            **base,
            "request_payload": {**base["request_payload"], "sort": "Price Low"},
        },
        {
            **base,
            "request_payload": {
                **base["request_payload"],
                "request_overrides": {"shopping_type": "delivery"},
            },
        },
    ]

    key = canonical_request_key(base)
    assert all(canonical_request_key(variant) != key for variant in variants)
    changed_path = {**base, "request_payload": dict(base["request_payload"])}
    changed_path["request_payload"]["_provider_request_contract"] = {
        **base["request_payload"]["_provider_request_contract"],
        "path": "/mc/walmart/search/zipcode/v3/",
    }
    assert canonical_request_key(changed_path) != key


def test_amazon_identity_uses_resolved_url_but_not_unrelated_store_metadata() -> None:
    base = _task("amazon", "service:1", retailer_id="amazon_us_same_day")
    base["store_number"] = None
    base["request_payload"] = {
        **base["request_payload"],
        "_provider_request_contract": _provider_contract(
            "amazon_us_same_day", "metricscart_amazon_us_same_day_search_zipcode"
        ),
        "amazon_same_day_url_template": "https://amazon.example/s?k={{keyword}}&i=sameday",
    }
    changed_template = {
        **base,
        "request_payload": {
            **base["request_payload"],
            "amazon_same_day_url_template": "https://amazon.example/other?q={{keyword}}",
        },
    }
    changed_keyword = {
        **base,
        "request_payload": {**base["request_payload"], "keyword": "2% milk"},
    }

    assert effective_request_identity(base)["params"]["url"].endswith("milk&i=sameday")
    assert canonical_request_key(changed_template) != canonical_request_key(base)
    assert canonical_request_key(changed_keyword) != canonical_request_key(base)


def test_exact_recovery_contract_is_checksum_bound_and_disables_preflight() -> None:
    failed = _task(
        "failed",
        "location:1",
        status="failed",
        gate_status="failed",
        http_status=500,
        failure_class="lease_exhausted",
        billable_credits=0,
        raw_artifact_id=None,
        is_preflight=True,
    )
    preview = build_recovery_preview("base-run", [failed], definition_checksum="definition")

    contracts = build_exact_recovery_task_contracts(
        preview,
        selection_checksum=preview.selection_checksum,
        base_snapshot_checksum=preview.base_snapshot_checksum,
        approved_credit_ceiling=preview.maximum_credits,
    )

    assert len(contracts) == 1
    assert contracts[0]["is_preflight"] is False
    assert contracts[0]["request_payload"] == failed["request_payload"]
    with pytest.raises(ValueError, match="must equal the immutable selection maximum"):
        build_exact_recovery_task_contracts(
            preview,
            selection_checksum=preview.selection_checksum,
            base_snapshot_checksum=preview.base_snapshot_checksum,
            approved_credit_ceiling=preview.maximum_credits + 999_999,
        )
    try:
        build_exact_recovery_task_contracts(
            preview,
            selection_checksum="stale",
            base_snapshot_checksum=preview.base_snapshot_checksum,
            approved_credit_ceiling=preview.maximum_credits,
        )
    except ValueError as exc:
        assert "selection" in str(exc)
    else:
        raise AssertionError("stale exact recovery selection should fail closed")


def test_exact_recovery_rejects_unapproved_pagination_descendants() -> None:
    failed = _task(
        "failed",
        "location:1",
        status="failed",
        gate_status="failed",
        http_status=500,
        failure_class="lease_exhausted",
        billable_credits=0,
        raw_artifact_id=None,
    )
    failed["max_pages"] = 2
    preview = build_recovery_preview("base-run", [failed], definition_checksum="definition")
    try:
        build_exact_recovery_task_contracts(
            preview,
            selection_checksum=preview.selection_checksum,
            base_snapshot_checksum=preview.base_snapshot_checksum,
            approved_credit_ceiling=preview.maximum_credits,
        )
    except ValueError as exc:
        assert "multi-page continuation recovery is not supported" in str(exc)
    else:
        raise AssertionError("unbounded pagination must fail closed")


def _lineage_component(
    base: dict[str, Any],
    recovery: dict[str, Any],
    *,
    plan_id: str = "plan-root",
    parent_plan_id: str | None = None,
    depth: int = 0,
) -> ContinuationLineageComponent:
    return ContinuationLineageComponent(
        recovery_plan_id=plan_id,
        recovery_collection_run_id=str(recovery["collection_run_id"]),
        continuation_of_recovery_plan_id=parent_plan_id,
        continuation_depth=depth,
        selection_checksum=f"selection-{plan_id}",
        selection_keys=(canonical_request_key(base),),
        adopted_keys=(),
        recovery_rows=(recovery,),
    )


def test_continuation_retries_only_enough_zero_credit_gaps_for_readiness() -> None:
    base_rows = [_task(f"success-{index}", f"location:{index}") for index in range(94)]
    base_rows.extend(
        _task(
            f"gap-{index}",
            f"location:{index}",
            status="failed",
            http_status=None,
            failure_class="timeout",
            billable_credits=0,
            raw_artifact_id=None,
        )
        for index in range(94, 100)
    )
    parent_gap = base_rows[-1]
    parent_recovery = _recovery(
        parent_gap,
        "parent-recovery-gap",
        status="failed",
        http_status=None,
        failure_class="timeout",
        billable_credits=0,
        raw_artifact_id=None,
    )

    preview = build_continuation_preview(
        "base-run",
        base_rows,
        [_lineage_component(parent_gap, parent_recovery)],
        definition_checksum="definition",
        continuation_of_recovery_plan_id="plan-root",
    )

    assert preview.conclusive_before_count == 94
    assert preview.selected_task_count == 1
    assert preview.retailers[0].optional_transient_tasks == 1
    assert preview.retailers[0].required_tasks == 0


def test_continuation_repairs_coverage_below_threshold_without_recalling_successes() -> None:
    base_rows = [_task(f"success-{index}", f"location:{index}") for index in range(92)]
    base_rows.extend(
        _task(
            f"gap-{index}",
            f"location:{index}",
            status="failed",
            http_status=None,
            failure_class="timeout",
            billable_credits=0,
            raw_artifact_id=None,
        )
        for index in range(92, 100)
    )
    parent_gap = base_rows[-1]
    parent_recovery = _recovery(
        parent_gap,
        "parent-recovery-gap",
        status="failed",
        http_status=None,
        failure_class="timeout",
        billable_credits=0,
        raw_artifact_id=None,
    )

    preview = build_continuation_preview(
        "base-run",
        base_rows,
        [_lineage_component(parent_gap, parent_recovery)],
        definition_checksum="definition",
        continuation_of_recovery_plan_id="plan-root",
    )

    assert preview.selected_task_count == 3
    selected_ids = {item.source_task_id for item in preview.items}
    assert not selected_ids & {f"success-{index}" for index in range(92)}


def test_continuation_never_recalls_success_or_retained_404_and_always_selects_hard_gap() -> None:
    base_success = _task("base-success", "location:1")
    base_404 = _task(
        "base-404",
        "location:2",
        status="failed",
        http_status=404,
        failure_class="invalid_request",
        raw_artifact_id="artifact-404",
    )
    base_hard = _task(
        "base-hard",
        "location:3",
        status="failed",
        http_status=200,
        failure_class="schema_drift",
        raw_artifact_id="artifact-schema",
    )
    parent_recovery = _recovery(
        base_hard,
        "parent-hard",
        status="failed",
        http_status=200,
        failure_class="schema_drift",
        raw_artifact_id="artifact-schema-parent",
    )

    preview = build_continuation_preview(
        "base-run",
        [base_success, base_404, base_hard],
        [_lineage_component(base_hard, parent_recovery)],
        definition_checksum="definition",
        continuation_of_recovery_plan_id="plan-root",
    )

    assert [item.source_task_id for item in preview.items] == ["base-hard"]
    assert preview.items[0].required_for_assembly is True
    assert preview.retained_success_count == 1
    assert preview.retained_billable_404_count == 1


def test_continuation_enforces_governed_task_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    hard_rows = [
        _task(
            f"hard-{index}",
            f"location:{index}",
            status="failed",
            http_status=200,
            failure_class="schema_drift",
            raw_artifact_id=f"artifact-schema-{index}",
        )
        for index in range(2)
    ]
    parent_recovery = _recovery(hard_rows[0], "parent-hard")
    monkeypatch.setattr(composite_module, "MAXIMUM_CONTINUATION_TASKS", 1)

    with pytest.raises(ValueError, match="above the governed 1-task cap"):
        build_continuation_preview(
            "base-run",
            hard_rows,
            [_lineage_component(hard_rows[0], parent_recovery)],
            definition_checksum="definition",
            continuation_of_recovery_plan_id="plan-root",
        )


def test_continuation_stops_after_prior_recovery_becomes_conclusive() -> None:
    base_gap = _task(
        "base-gap",
        "location:1",
        status="failed",
        http_status=None,
        failure_class="timeout",
        billable_credits=0,
        raw_artifact_id=None,
    )
    recovered = _recovery(
        base_gap,
        "recovered-success",
        status="succeeded",
        http_status=200,
        failure_class=None,
        billable_credits=2,
        raw_artifact_id="recovered-artifact",
        result_count=3,
    )

    preview = build_continuation_preview(
        "base-run",
        [base_gap],
        [_lineage_component(base_gap, recovered)],
        definition_checksum="definition",
        continuation_of_recovery_plan_id="plan-root",
    )

    assert preview.selected_task_count == 0
    assert preview.resolved_before_count == 1
    assert preview.conclusive_before_count == 1


def test_banana_continuation_projection_selects_exact_governed_65_tasks() -> None:
    def population(
        retailer_id: str,
        *,
        successes: int,
        retained_404s: int,
        zero_gaps: int,
        contract_gaps: int = 0,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        ordinal = 0
        for _ in range(successes):
            rows.append(
                _task(
                    f"{retailer_id}-success-{ordinal}",
                    f"location:{retailer_id}:{ordinal}",
                    retailer_id=retailer_id,
                )
            )
            ordinal += 1
        for _ in range(retained_404s):
            rows.append(
                _task(
                    f"{retailer_id}-404-{ordinal}",
                    f"location:{retailer_id}:{ordinal}",
                    retailer_id=retailer_id,
                    status="failed",
                    http_status=404,
                    failure_class="invalid_request",
                    raw_artifact_id=f"artifact-404-{ordinal}",
                )
            )
            ordinal += 1
        for _ in range(zero_gaps):
            rows.append(
                _task(
                    f"{retailer_id}-gap-{ordinal}",
                    f"location:{retailer_id}:{ordinal}",
                    retailer_id=retailer_id,
                    status="failed",
                    http_status=None,
                    failure_class="lease_exhausted",
                    billable_credits=0,
                    raw_artifact_id=None,
                )
            )
            ordinal += 1
        for _ in range(contract_gaps):
            rows.append(
                _task(
                    f"{retailer_id}-contract-{ordinal}",
                    f"location:{retailer_id}:{ordinal}",
                    retailer_id=retailer_id,
                    status="failed",
                    http_status=200,
                    failure_class="schema_drift",
                    raw_artifact_id=f"artifact-contract-{ordinal}",
                )
            )
            ordinal += 1
        return rows

    aldi = population("aldi_us", successes=1_835, retained_404s=655, zero_gaps=197)
    amazon = population(
        "amazon_us_same_day",
        successes=4_151,
        retained_404s=0,
        zero_gaps=37,
        contract_gaps=2,
    )
    for row in amazon:
        row["store_number"] = None
        row["request_payload"]["amazon_same_day_url_template"] = (
            "https://amazon.example/s?k={{keyword}}&i=sameday"
        )
    walmart = population("walmart_us", successes=4_551, retained_404s=56, zero_gaps=76)
    parent_gap = walmart[-1]
    parent_recovery = _recovery(
        parent_gap,
        "walmart-parent-gap",
        status="failed",
        http_status=None,
        failure_class="lease_exhausted",
        billable_credits=0,
        raw_artifact_id=None,
    )

    preview = build_continuation_preview(
        "base-run",
        [*aldi, *amazon, *walmart],
        [_lineage_component(parent_gap, parent_recovery)],
        definition_checksum="definition",
        continuation_of_recovery_plan_id="plan-root",
    )

    by_retailer = {row.retailer_id: row for row in preview.retailers}
    assert preview.selected_task_count == 65
    assert preview.maximum_credits == 650
    assert by_retailer["aldi_us"].optional_transient_tasks == 63
    assert by_retailer["amazon_us_same_day"].required_tasks == 2
    assert by_retailer["walmart_us"].selected_tasks == 0


def test_continuation_selects_exact_minimum_for_zero_success_heb_shape() -> None:
    base_rows = [
        _task(
            f"heb-404-{index}",
            f"location:heb:{index}",
            retailer_id="heb_us",
            status="failed",
            http_status=404,
            failure_class="invalid_request",
            raw_artifact_id=f"artifact-404-{index}",
        )
        for index in range(3)
    ]
    base_rows.extend(
        _task(
            f"heb-gap-{index}",
            f"location:heb:{index}",
            retailer_id="heb_us",
            status="failed",
            http_status=None,
            failure_class="timeout",
            billable_credits=0,
            raw_artifact_id=None,
        )
        for index in range(3, 365)
    )
    parent_gap = base_rows[-1]
    parent_recovery = _recovery(
        parent_gap,
        "heb-parent-gap",
        status="failed",
        http_status=None,
        failure_class="timeout",
        billable_credits=0,
        raw_artifact_id=None,
    )

    preview = build_continuation_preview(
        "base-run",
        base_rows,
        [_lineage_component(parent_gap, parent_recovery)],
        definition_checksum="definition",
        continuation_of_recovery_plan_id="plan-root",
    )

    assert preview.selected_task_count == 344
    assert preview.maximum_credits == 3_440


def test_continuation_requires_a_nonempty_success_even_with_95_percent_artifacts() -> None:
    base_rows = [_task(f"empty-{index}", f"location:{index}") for index in range(95)]
    for row in base_rows:
        row["result_count"] = 0
    base_rows.extend(
        _task(
            f"gap-{index}",
            f"location:{index}",
            status="failed",
            http_status=None,
            failure_class="timeout",
            billable_credits=0,
            raw_artifact_id=None,
        )
        for index in range(95, 100)
    )
    parent_gap = base_rows[-1]
    parent_recovery = _recovery(
        parent_gap,
        "parent-gap",
        status="failed",
        http_status=None,
        failure_class="timeout",
        billable_credits=0,
        raw_artifact_id=None,
    )

    preview = build_continuation_preview(
        "base-run",
        base_rows,
        [_lineage_component(parent_gap, parent_recovery)],
        definition_checksum="definition",
        continuation_of_recovery_plan_id="plan-root",
    )

    assert preview.selected_task_count == 1


def test_uncovered_zero_credit_gaps_follow_readiness_tolerance_not_100_percent() -> None:
    walmart = _task(
        "walmart-gap",
        "location:1",
        status="failed",
        http_status=500,
        failure_class="lease_exhausted",
        billable_credits=0,
        raw_artifact_id=None,
    )
    aldi = _task(
        "aldi-gap",
        "location:2",
        retailer_id="aldi_us",
        status="failed",
        http_status=500,
        failure_class="lease_exhausted",
        billable_credits=0,
        raw_artifact_id=None,
    )
    amazon = _task(
        "amazon-contract",
        "location:3",
        retailer_id="amazon_us_same_day",
        status="failed",
        http_status=200,
        failure_class="schema_drift",
        raw_artifact_id="artifact-contract",
    )
    amazon["store_number"] = None
    amazon["request_payload"]["amazon_same_day_url_template"] = (
        "https://amazon.example/s?k={{keyword}}&i=sameday"
    )
    base_by_key = {canonical_request_key(row): row for row in (walmart, aldi, amazon)}
    chosen_by_key = {key: (row, evidence_outcome(row)) for key, row in base_by_key.items()}

    blocking, unavailable, tolerated = partition_uncovered_recovery_keys(
        set(base_by_key),
        base_by_key=base_by_key,
        chosen_by_key=chosen_by_key,
        collection_readiness_manifest={
            "walmart_us": {"status": "warning"},
            "aldi_us": {"status": "blocking_integrity"},
            "amazon_us_same_day": {"status": "blocking_integrity"},
        },
        unavailable_retailer_ids=set(),
    )

    assert unavailable == set()
    assert canonical_request_key(walmart) in tolerated
    assert canonical_request_key(aldi) in blocking
    assert canonical_request_key(amazon) in blocking


def test_continuation_refuses_spend_when_unresolved_tasks_cannot_fix_404_rate() -> None:
    base_rows = [_task(f"success-{index}", f"location:{index}") for index in range(218)]
    base_rows.extend(
        _task(
            f"not-found-{index}",
            f"location:{index}",
            status="failed",
            http_status=404,
            failure_class="invalid_request",
            raw_artifact_id=f"artifact-404-{index}",
        )
        for index in range(218, 663)
    )
    base_rows.extend(
        _task(
            f"gap-{index}",
            f"location:{index}",
            status="failed",
            http_status=None,
            failure_class="timeout",
            billable_credits=0,
            raw_artifact_id=None,
        )
        for index in range(663, 670)
    )
    parent_gap = base_rows[-1]
    parent_recovery = _recovery(
        parent_gap,
        "parent-gap",
        status="failed",
        http_status=None,
        failure_class="timeout",
        billable_credits=0,
        raw_artifact_id=None,
    )

    with pytest.raises(ValueError, match="cannot satisfy collection readiness"):
        build_continuation_preview(
            "base-run",
            base_rows,
            [_lineage_component(parent_gap, parent_recovery)],
            definition_checksum="definition",
            continuation_of_recovery_plan_id="plan-root",
            maximum_404_rate=0.5,
        )


def test_composite_contract_missing_and_quarantine_block_analysis() -> None:
    assert composite_trust_state(["usable_success", "zero_credit_missing"]) == (
        "ready_with_warnings"
    )
    assert composite_trust_state(["usable_success", "retained_billable_404"]) == "ready"
    assert composite_trust_state(["contract_missing"]) == "blocked"
    assert composite_trust_state(["quarantined"]) == "blocked"
    assert composite_trust_state(["usable_success"], has_uncovered_recovery=True) == "blocked"


def test_recovery_adequacy_allows_bounded_gaps_but_blocks_unrepaired_retailer() -> None:
    blocked, healthy = recovery_adequacy(
        {"banana_retailer": ["usable_success"] * 984 + ["zero_credit_missing"] * 16}
    )
    assert blocked is False
    assert healthy["banana_retailer"]["status"] == "warning"

    blocked, unhealthy = recovery_adequacy(
        {"meijer_us": ["usable_success"] * 3 + ["zero_credit_missing"] * 275}
    )
    assert blocked is True
    assert unhealthy["meijer_us"]["status"] == "blocked"

    blocked, unavailable = recovery_adequacy(
        {"healthy_base_retailer": ["retained_billable_404"] * 2}
    )
    assert blocked is False
    assert unavailable["healthy_base_retailer"]["definitive_requests"] == 2


def test_retailer_collection_readiness_blocks_all_404_or_sparse_evidence() -> None:
    blocked, rows = retailer_collection_readiness(
        {
            "all_404": ["retained_billable_404"] * 20,
            "sparse": ["usable_success"] * 3 + ["zero_credit_missing"] * 275,
        },
        minimum_successes=1,
        maximum_404_rate=0.5,
    )
    assert blocked is True
    assert rows["all_404"]["status"] == "blocking_integrity"
    assert rows["sparse"]["conclusive_coverage"] < 0.95

    blocked, approved = retailer_collection_readiness(
        {"meijer_us": ["usable_success"] * 3 + ["zero_credit_missing"] * 275},
        minimum_successes=1,
        maximum_404_rate=0.5,
        nonempty_successes_by_retailer={"meijer_us": 3},
        unavailability_approvals={
            "meijer_us": {
                "id": "approval-1",
                "reason": "provider instability is unresolved",
                "approved_by": "platform-admin",
                "base_snapshot_checksum": "snapshot",
            }
        },
    )
    assert blocked is False
    assert approved["meijer_us"]["status"] == "unavailable"

    blocked, scope_invalid = retailer_collection_readiness(
        {"kroger_us": ["usable_success"] * 100},
        minimum_successes=1,
        maximum_404_rate=0.5,
        nonempty_successes_by_retailer={"kroger_us": 100},
        unavailability_approvals={
            "kroger_us": {
                "id": "approval-scope-invalid",
                "reason": "frozen run contains retired seven-digit location aliases",
                "approved_by": "platform-admin",
                "base_snapshot_checksum": "snapshot",
            }
        },
    )
    assert blocked is False
    assert scope_invalid["kroger_us"]["status"] == "unavailable"

    blocked, integrity = retailer_collection_readiness(
        {"meijer_us": ["contract_missing"]},
        minimum_successes=1,
        maximum_404_rate=0.5,
        unavailability_approvals={
            "meijer_us": {
                "id": "approval-1",
                "reason": "cannot waive contract drift",
                "approved_by": "platform-admin",
                "base_snapshot_checksum": "snapshot",
            }
        },
    )
    assert blocked is True
    assert integrity["meijer_us"]["status"] == "blocking_integrity"


def test_nonconclusive_recovery_never_loosens_a_blocker() -> None:
    cases = (
        ("quarantined", "zero_credit_missing", "quarantined"),
        ("contract_missing", "zero_credit_missing", "contract_missing"),
        ("zero_credit_missing", "contract_missing", "contract_missing"),
    )
    for base_outcome, recovery_outcome, expected in cases:
        base = _task("base", "location:1")
        recovery = _recovery(base, "recovery")
        configurations = {
            "quarantined": dict(
                status="failed",
                http_status=500,
                failure_class="unknown",
                billable_credits=0,
                raw_artifact_id=None,
            ),
            "contract_missing": dict(
                status="failed",
                http_status=200,
                failure_class="schema_drift",
                billable_credits=2,
                raw_artifact_id="contract-artifact",
            ),
            "zero_credit_missing": dict(
                status="failed",
                http_status=None,
                failure_class="timeout",
                billable_credits=0,
                raw_artifact_id=None,
            ),
        }
        base.update(configurations[base_outcome])
        recovery.update(configurations[recovery_outcome])
        resolved = resolve_task_precedence(
            [base], [recovery], approved_recovery_keys=[canonical_request_key(base)]
        )
        assert resolved[0].evidence_outcome == expected


def test_legacy_query_contract_ignores_administrative_notes_only() -> None:
    base = {"query": {"keyword": "bananas", "notes": "primary"}}
    recovery = {"query": {"keyword": "bananas", "notes": "recovery note"}}
    assert outbound_query_contract(base) == outbound_query_contract(recovery)
    recovery["query"] = {"keyword": "milk", "notes": "primary"}
    assert outbound_query_contract(base) != outbound_query_contract(recovery)


def test_reconstructed_legacy_identity_validates_success_and_retained_404_artifacts() -> None:
    success = _task("legacy-success", "location:1")
    retained_404 = _task(
        "legacy-404",
        "location:2",
        status="failed",
        http_status=404,
        failure_class="invalid_request",
        raw_artifact_id="legacy-404-artifact",
    )
    for row in (success, retained_404):
        identity = effective_request_identity(row)
        row["_request_contract_provenance"] = "reconstructed_current_catalog"
        row["raw_artifact_metadata"] = {
            "request_method": identity["method"],
            "request_path": identity["path"],
            "request_parameter_names": sorted(identity["params"]),
        }

    manifest = request_identity_provenance_manifest(
        {"base": [success], "legacy-recovery": [retained_404]}
    )

    assert manifest["mode_counts"] == {"reconstructed_current_catalog": 2}
    assert manifest["outcome_counts"] == {
        "retained_billable_404": 1,
        "usable_success": 1,
    }
    assert manifest["validated_conclusive_task_count"] == 2
    retained_404["raw_artifact_metadata"]["request_path"] = "/obsolete/endpoint"
    try:
        request_identity_provenance_manifest({"legacy-recovery": [retained_404]})
    except ValueError as exc:
        assert "does not match" in str(exc)
    else:
        raise AssertionError("legacy artifact request drift must fail closed")


@pytest.mark.parametrize("first_lookup_misses", [False, True])
async def test_composite_analysis_queue_returns_initial_run_when_input_has_replays(
    first_lookup_misses: bool,
) -> None:
    class ScalarResult:
        def __init__(self, value: str | None) -> None:
            self.value = value

        def scalar_one_or_none(self) -> str | None:
            return self.value

    class MultipleRunConnection:
        def __init__(self) -> None:
            self.select_count = 0
            self.insert_count = 0

        async def execute(self, statement: object, _parameters: dict[str, object]) -> ScalarResult:
            sql = " ".join(str(statement).split())
            if sql.startswith("SELECT id::text FROM analysis_run"):
                self.select_count += 1
                # Two governed replays may legitimately share one immutable input set.
                # The queue helper must select the original run deterministically instead
                # of asking SQLAlchemy to coerce multiple rows into one scalar.
                assert "ORDER BY created_at, id LIMIT 1" in sql
                if first_lookup_misses and self.select_count == 1:
                    return ScalarResult(None)
                return ScalarResult("analysis-run-initial")
            if sql.startswith("INSERT INTO analysis_run"):
                self.insert_count += 1
                # Simulate a concurrent unique-identity winner. The fallback lookup now
                # sees the initial run plus a later governed replay for the same input.
                return ScalarResult(None)
            raise AssertionError(f"unexpected SQL: {sql}")

    repository = PostgresCompositeEvidenceRepository(  # type: ignore[arg-type]
        None,
        provider_request_contracts={},
    )
    connection = MultipleRunConnection()

    analysis_run_id = await repository._queue_composite_analysis(
        connection,  # type: ignore[arg-type]
        "composite-input",
        queue_allowed=True,
    )

    assert analysis_run_id == "analysis-run-initial"
    assert connection.select_count == (2 if first_lookup_misses else 1)
    assert connection.insert_count == (1 if first_lookup_misses else 0)


async def test_task_rows_snapshot_uses_frozen_geography_not_mutable_location_master() -> None:
    row = {
        **_task("task-1", "location:1"),
        "retailer_location_id": "retailer-location-1",
        "raw_artifact_metadata": {},
        "raw_artifact_checksum": "a" * 64,
        "geography_resolution_id": "resolution-1",
        "frozen_geography_location_id": "geography-location-1",
        "frozen_retailer_location_id": "retailer-location-1",
        "frozen_zipcode": "00001",
        "frozen_store_number": "location:1",
        "frozen_latitude": 41.1,
        "frozen_longitude": -87.1,
        "frozen_city": "Frozen City",
        "frozen_state": "IL",
        "frozen_country": "USA",
        "current_location_eligible": True,
    }

    class MappingResult:
        def mappings(self) -> MappingResult:
            return self

        def all(self) -> list[dict[str, Any]]:
            return [row]

    class FrozenGeographyConnection:
        sql = ""

        async def execute(self, statement: object, _parameters: dict[str, object]) -> MappingResult:
            self.sql = " ".join(str(statement).split())
            return MappingResult()

    connection = FrozenGeographyConnection()
    repository = PostgresCompositeEvidenceRepository(  # type: ignore[arg-type]
        None,
        provider_request_contracts={},
    )

    tasks = await repository._task_rows(connection, "run-1")  # type: ignore[arg-type]
    snapshot = composite_module._task_snapshot(tasks[0])

    assert "gl.latitude AS frozen_latitude" in connection.sql
    assert "SELECT l.latitude AS frozen_latitude" not in connection.sql
    assert ", l.latitude AS frozen_latitude" not in connection.sql
    assert snapshot["location_snapshot"] == {
        "latitude": 41.1,
        "longitude": -87.1,
        "city": "Frozen City",
        "state": "IL",
    }


def test_task_snapshot_preserves_legacy_location_checksum_contract() -> None:
    task = {
        **_task("task-1", "location:1"),
        "geography_resolution_id": "resolution-1",
        "frozen_geography_location_id": "geography-location-1",
        "frozen_retailer_location_id": "location-location:1",
        "frozen_zipcode": "00001",
        "frozen_store_number": "location:1",
        "frozen_latitude": 41.1,
        "frozen_longitude": -87.1,
        "frozen_city": "Frozen City",
        "frozen_state": "IL",
        "frozen_country": "USA",
    }

    snapshot = composite_module._task_snapshot(task)

    assert set(snapshot["location_snapshot"]) == {"latitude", "longitude", "city", "state"}
    assert composite_module.canonical_checksum({"tasks": [snapshot]}) == (
        "e32e0f605604ebd1bc9a1ee4a37b49997e3a4be0551054680d01be3b1c777551"
    )


async def test_task_rows_fails_closed_when_frozen_geography_scope_is_missing() -> None:
    row = {
        **_task("task-1", "location:1"),
        "raw_artifact_metadata": {},
        "raw_artifact_checksum": "a" * 64,
        "geography_resolution_id": "resolution-1",
        "frozen_geography_location_id": None,
    }

    class MappingResult:
        def mappings(self) -> MappingResult:
            return self

        def all(self) -> list[dict[str, Any]]:
            return [row]

    class MissingScopeConnection:
        async def execute(
            self, _statement: object, _parameters: dict[str, object]
        ) -> MappingResult:
            return MappingResult()

    repository = PostgresCompositeEvidenceRepository(  # type: ignore[arg-type]
        None,
        provider_request_contracts={},
    )
    with pytest.raises(ValueError, match="immutable geography resolution"):
        await repository._task_rows(  # type: ignore[arg-type]
            MissingScopeConnection(),
            "run-1",
        )


async def test_composite_evidence_materialization_uses_bounded_bulk_writes() -> None:
    task_count = composite_module.MATERIALIZATION_WRITE_BATCH_SIZE * 2 + 1
    chosen: list[tuple[str, dict[str, Any], None, str]] = []
    expected_artifacts: list[dict[str, Any]] = []
    task_artifacts: dict[str, tuple[str, str]] = {}
    for ordinal in range(task_count):
        task = _task(f"task-{ordinal}", f"location:{ordinal}")
        task["raw_artifact_id"] = f"artifact-{ordinal}"
        task["raw_artifact_checksum"] = f"checksum-{ordinal}"
        key = canonical_request_key(task)
        chosen.append((key, task, None, "usable_success"))
        expected_artifacts.append(
            {
                "ordinal": ordinal,
                "canonical_request_key": key,
                "dataset_artifact_id": f"artifact-{ordinal}",
                "checksum": f"checksum-{ordinal}",
            }
        )
        task_artifacts[f"task-{ordinal}"] = (f"artifact-{ordinal}", f"checksum-{ordinal}")

    class BulkResult:
        def __init__(
            self,
            *,
            scalar_values: list[str] | None = None,
            mapping_values: list[dict[str, Any]] | None = None,
        ) -> None:
            self.scalar_values = scalar_values or []
            self.mapping_values = mapping_values or []

        def scalars(self) -> BulkResult:
            return self

        def __iter__(self):  # type: ignore[no-untyped-def]
            return iter(self.scalar_values)

        def mappings(self) -> BulkResult:
            return self

        def all(self) -> list[dict[str, Any]]:
            return self.mapping_values

    class BulkConnection:
        def __init__(self) -> None:
            self.lineage_queries = 0
            self.artifact_queries = 0

        async def execute(self, statement: object, parameters: dict[str, object]) -> BulkResult:
            sql = " ".join(str(statement).split())
            rows = json.loads(str(parameters["rows"]))
            if "INSERT INTO analysis_input_task_lineage" in sql:
                self.lineage_queries += 1
                return BulkResult(scalar_values=[str(row["canonical_request_key"]) for row in rows])
            if "INSERT INTO analysis_input_artifact" in sql:
                self.artifact_queries += 1
                return BulkResult(
                    mapping_values=[
                        {
                            "ordinal": int(row["ordinal"]),
                            "canonical_request_key": str(row["canonical_request_key"]),
                            "dataset_artifact_id": task_artifacts[str(row["task_id"])][0],
                            "checksum": task_artifacts[str(row["task_id"])][1],
                        }
                        for row in rows
                    ]
                )
            raise AssertionError(f"unexpected SQL: {sql}")

    connection = BulkConnection()
    repository = PostgresCompositeEvidenceRepository(  # type: ignore[arg-type]
        None,
        provider_request_contracts={},
    )

    await repository._insert_selected_evidence(  # type: ignore[arg-type]
        connection,
        "input-set-1",
        chosen,  # type: ignore[arg-type]
        expected_usable_artifacts=expected_artifacts,
    )

    assert connection.lineage_queries == 3
    assert connection.artifact_queries == 3
    assert connection.lineage_queries + connection.artifact_queries == 6
