"""Canonical Python validator for repository JSON contracts."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource


@dataclass(frozen=True, slots=True)
class ContractTarget:
    schema: str
    document: Path


class ContractError(ValueError):
    """Raised when a document violates a normative contract."""


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"Could not read JSON document {path}: {exc}") from exc


def _format_error(path: Path, error: ValidationError) -> str:
    location = ".".join(str(part) for part in error.absolute_path) or "<root>"
    return f"{path}: {location}: {error.message}"


def validate_document(root: Path, schema_name: str, document_path: Path) -> None:
    """Validate one JSON document against a named repository schema."""

    document = _load_json(document_path)
    validate_instance(root, schema_name, document, label=str(document_path))


def validate_instance(
    root: Path,
    schema_name: str,
    document: Any,
    *,
    label: str = "<instance>",
) -> None:
    """Validate an in-memory object against a named repository schema."""

    schema_path = root / "schemas" / schema_name
    schema = _load_json(schema_path)
    registry = Registry()
    for candidate in sorted((root / "schemas").glob("*.json")):
        candidate_schema = _load_json(candidate)
        resource = Resource.from_contents(candidate_schema)
        registry = registry.with_resource(candidate.resolve().as_uri(), resource)
        schema_id = candidate_schema.get("$id") if isinstance(candidate_schema, dict) else None
        if isinstance(schema_id, str):
            registry = registry.with_resource(schema_id, resource)
    validator = Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
        registry=registry,
    )
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.absolute_path))
    if errors:
        messages = "\n".join(_format_error(Path(label), error) for error in errors)
        raise ContractError(messages)


def _targets(root: Path) -> Iterable[ContractTarget]:
    for definition in sorted((root / "examples").glob("collection-definition.*.json")):
        yield ContractTarget("collection-definition.schema.json", definition)
    for result in sorted((root / "examples").glob("analysis-result.*.json")):
        yield ContractTarget("analysis-result.schema.json", result)
    yield ContractTarget(
        "analysis-result-v2.schema.json",
        root / "examples" / "analysis-result-v2.ground-beef.json",
    )
    yield ContractTarget(
        "analysis-evidence.schema.json",
        root / "examples" / "analysis-evidence.ground-beef.json",
    )
    yield ContractTarget(
        "canonical-product.schema.json",
        root / "examples" / "canonical-product.ground-beef.json",
    )
    yield ContractTarget(
        "product-detail-snapshot.schema.json",
        root / "examples" / "product-detail-snapshot.aldi.json",
    )
    yield ContractTarget(
        "agent-output.schema.json",
        root / "examples" / "agent-output.ground-beef-insight.json",
    )
    yield ContractTarget(
        "report-blueprint.schema.json",
        root / "examples" / "report-blueprint.ground-beef.json",
    )
    for manifest in sorted((root / "examples").glob("historical-input-manifest.*.json")):
        yield ContractTarget("historical-input-manifest.schema.json", manifest)
    yield ContractTarget(
        "alert-definition.schema.json",
        root / "examples" / "alert-definition.amazon-pressure.json",
    )
    yield ContractTarget(
        "golden-benchmarks.schema.json",
        root / "fixtures" / "golden" / "benchmarks.json",
    )
    yield ContractTarget(
        "product-detail-catalog.schema.json",
        root / "config" / "product-detail-catalog.json",
    )
    for product_pack in sorted((root / "product-packs").glob("fresh_*.json")):
        yield ContractTarget("product-pack.schema.json", product_pack)
    for blueprint in sorted((root / "report-blueprints").glob("*.json")):
        yield ContractTarget("report-blueprint.schema.json", blueprint)
    for prompt in sorted((root / "agent-prompts").glob("*.json")):
        yield ContractTarget("agent-prompt.schema.json", prompt)


def _validate_json_parseability(root: Path) -> int:
    paths = [
        *sorted((root / "schemas").glob("*.json")),
        *sorted((root / "config").glob("*.json")),
        *sorted((root / "fixtures" / "api_samples").glob("*.json")),
        root / "fixtures" / "location_master" / "locations.profile.json",
        root / "product-packs" / "index.json",
        *sorted((root / "report-blueprints").glob("*.json")),
        *sorted((root / "agent-prompts").glob("*.json")),
    ]
    for path in paths:
        _load_json(path)
    return len(paths)


def _validate_location_profile(root: Path) -> None:
    profile_path = root / "fixtures" / "location_master" / "locations.profile.json"
    profile = _load_json(profile_path)
    expected_counts = {"Walmart": 4683, "ALDI": 2627, "Target": 2148}
    if profile.get("rows") != 157806:
        raise ContractError(f"{profile_path}: expected 157806 rows")
    retailers = profile.get("relevant_retailers", {})
    for retailer, expected in expected_counts.items():
        actual = retailers.get(retailer, {}).get("locations")
        if actual != expected:
            raise ContractError(
                f"{profile_path}: expected {expected} {retailer} locations, found {actual}"
            )


def validate_handoff(root: Path) -> int:
    """Validate normative examples plus the supplied handoff JSON inventory."""

    count = _validate_json_parseability(root)
    for target in _targets(root):
        validate_document(root, target.schema, target.document)
        count += 1
    _validate_location_profile(root)
    return count
