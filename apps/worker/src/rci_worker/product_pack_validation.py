"""Deterministic Product Pack authoring certification gates."""

from __future__ import annotations

from pathlib import Path

from rci_analytics import ProductPackLoader
from rci_product_packs.models import ProductPackDraft, ProductPackEvidence
from rci_results import ReportBlueprintLoader

JsonObject = dict[str, object]


def validate_product_pack_draft(
    repository_root: Path,
    draft: ProductPackDraft,
    evidence: tuple[ProductPackEvidence, ...],
    suite: str,
) -> list[JsonObject]:
    gates: list[JsonObject] = []
    try:
        pack = ProductPackLoader(repository_root).load_document(
            draft.config,
            label=f"Product Pack draft {draft.id} revision {draft.revision}",
            report_blueprint=draft.report_blueprint,
        )
        gates.append(
            {
                "id": "product_pack_contract",
                "label": "Product Pack contract",
                "status": "passed",
                "message": "Schema, semantic references, formulas, and extraction rules are valid.",
            }
        )
    except Exception as exc:
        return [
            {
                "id": "product_pack_contract",
                "label": "Product Pack contract",
                "status": "failed",
                "message": str(exc),
            }
        ]
    try:
        blueprint = ReportBlueprintLoader(repository_root).load_document(
            draft.report_blueprint,
            label=f"Product Pack draft {draft.id} report blueprint",
        )
        if (blueprint.product_pack_id, blueprint.product_pack_version) != (
            pack.id,
            pack.version,
        ):
            raise ValueError("Report blueprint belongs to a different Product Pack version")
        gates.append(
            {
                "id": "report_blueprint_contract",
                "label": "Report blueprint",
                "status": "passed",
                "message": "Every report section and artifact profile resolves deterministically.",
            }
        )
    except Exception as exc:
        gates.append(
            {
                "id": "report_blueprint_contract",
                "label": "Report blueprint",
                "status": "failed",
                "message": str(exc),
            }
        )
    identity_matches = (pack.id, pack.version) == (
        draft.product_pack_id,
        draft.proposed_version,
    )
    gates.append(
        {
            "id": "immutable_identity",
            "label": "Immutable identity",
            "status": "passed" if identity_matches else "failed",
            "message": (
                "Draft and document IDs and versions agree."
                if identity_matches
                else "Draft identity differs from the Product Pack document."
            ),
        }
    )
    normalization = draft.config.get("normalization", {})
    profiles = draft.config.get("matching_profiles", [])
    deprecated = (
        isinstance(normalization, dict)
        and normalization.get("package_equivalence_policy") == "category_specific"
    ) or any(
        isinstance(profile, dict) and profile.get("brand_policy") == "category_specific"
        for profile in profiles
        if isinstance(profiles, list)
    )
    gates.append(
        {
            "id": "generic_capabilities_only",
            "label": "Generic capability boundary",
            "status": "failed" if deprecated else "passed",
            "message": (
                "New publication cannot use a legacy category-specific policy."
                if deprecated
                else "The pack uses only named category-neutral capabilities."
            ),
        }
    )
    long_patterns: list[str] = []
    for attribute in draft.config.get("attributes", []):
        if not isinstance(attribute, dict):
            continue
        for rule in attribute.get("extraction_rules", []):
            if not isinstance(rule, dict):
                continue
            for pattern in rule.get("patterns", []):
                if len(str(pattern)) > 500:
                    long_patterns.append(str(attribute.get("name", "unknown")))
    gates.append(
        {
            "id": "bounded_patterns",
            "label": "Bounded extraction patterns",
            "status": "failed" if long_patterns else "passed",
            "message": (
                f"Patterns exceed 500 characters for {sorted(set(long_patterns))}."
                if long_patterns
                else "Configured extraction patterns stay within the authoring safety limit."
            ),
        }
    )
    evidence_kinds = {item.kind for item in evidence}
    required_evidence: set[str] = set()
    if suite in {"compact", "full", "publication"}:
        required_evidence.add("compact_golden")
    if suite in {"full", "publication"}:
        required_evidence.add("full_golden")
    missing_evidence = required_evidence - evidence_kinds
    gates.append(
        {
            "id": "golden_evidence",
            "label": "Golden evidence",
            "status": "failed" if missing_evidence else "passed",
            "message": (
                f"Missing evidence manifests: {sorted(missing_evidence)}."
                if missing_evidence
                else (
                    "Required compact and full-source golden manifests are attached."
                    if required_evidence
                    else "Golden manifests are not required for the quick contract suite."
                )
            ),
        }
    )
    regression = draft.config.get("regression", {})
    dataset_ids = regression.get("golden_dataset_ids", []) if isinstance(regression, dict) else []
    needs_regression = suite in {"full", "publication"}
    gates.append(
        {
            "id": "regression_contract",
            "label": "Regression contract",
            "status": "failed" if needs_regression and not dataset_ids else "passed",
            "message": (
                "At least one immutable golden dataset ID is required."
                if needs_regression and not dataset_ids
                else "Golden dataset identities are explicit."
            ),
        }
    )
    return gates
