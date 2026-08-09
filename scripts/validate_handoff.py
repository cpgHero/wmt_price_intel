import csv
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


def load_json(p):
    return json.loads((ROOT / p).read_text(encoding="utf-8"))


def validate(schema_path, object_path):
    schema = load_json(schema_path)
    obj = load_json(object_path)
    errs = list(Draft202012Validator(schema).iter_errors(obj))
    if errs:
        for e in errs[:20]:
            print(f"ERROR {object_path}: {e.json_path}: {e.message}")
        return False
    print(f"OK schema {object_path}")
    return True


def as_number(value):
    if isinstance(value, (int, float)):
        return float(value)
    if value is None or value == "":
        raise ValueError("empty value is not numeric")
    return float(value)


def walk_path(obj, path):
    cur = obj
    for token in path:
        cur = cur[token]
    return cur


def select_assertion(assertion):
    source_path = ROOT / "fixtures" / "golden" / assertion["source"]
    selector = assertion["selector"]
    source_format = assertion["source_format"]

    if source_format == "json":
        data = json.loads(source_path.read_text(encoding="utf-8"))
        stype = selector["type"]
        if stype == "json_path":
            return as_number(walk_path(data, selector["path"]))
        if stype == "list_filter":
            rows = walk_path(data, selector["path"])
            matches = [r for r in rows if all(r.get(k) == v for k, v in selector["where"].items())]
            if len(matches) != 1:
                raise AssertionError(
                    f"list_filter expected 1 row, found {len(matches)} for {selector}"
                )
            return as_number(matches[0][selector["field"]])
        raise ValueError(f"unsupported JSON selector: {stype}")

    if source_format == "csv":
        with source_path.open(newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        stype = selector["type"]
        if stype == "row_filter":
            matches = [
                r for r in rows if all(r.get(k) == str(v) for k, v in selector["where"].items())
            ]
            if len(matches) != 1:
                raise AssertionError(
                    f"row_filter expected 1 row, found {len(matches)} for {selector}"
                )
            return as_number(matches[0][selector["field"]])
        if stype == "aggregate" and selector["operation"] == "sum":
            return sum(
                as_number(r[selector["field"]])
                for r in rows
                if r.get(selector["field"]) not in (None, "")
            )
        if stype == "ratio_of_sums":
            num = sum(
                as_number(r[selector["numerator_field"]])
                for r in rows
                if r.get(selector["numerator_field"]) not in (None, "")
            )
            den = sum(
                as_number(r[selector["denominator_field"]])
                for r in rows
                if r.get(selector["denominator_field"]) not in (None, "")
            )
            if den == 0:
                raise ZeroDivisionError("golden benchmark denominator is zero")
            return num / den
        raise ValueError(f"unsupported CSV selector: {stype}")

    raise ValueError(f"unsupported source format: {source_format}")


def validate_golden_benchmarks():
    ok = validate("schemas/golden-benchmarks.schema.json", "fixtures/golden/benchmarks.json")
    if not ok:
        return False
    bench = load_json("fixtures/golden/benchmarks.json")
    golden_ok = True
    for category, config in bench["categories"].items():
        for assertion in config["assertions"]:
            try:
                actual = select_assertion(assertion)
                expected = float(assertion["expected"])
                tol = float(assertion["tolerance_abs"])
                passed = abs(actual - expected) <= tol + 1e-12
                print(
                    ("OK" if passed else "ERROR"),
                    f"golden {category}.{assertion['name']}: "
                    f"actual={actual:.12g} expected={expected:.12g} tol={tol:g}",
                )
                golden_ok &= passed
            except Exception as exc:
                print("ERROR", f"golden {category}.{assertion['name']}: {exc}")
                golden_ok = False
    return golden_ok


ok = True
ok &= validate(
    "schemas/collection-definition.schema.json", "examples/collection-definition.strawberries.json"
)
ok &= validate("schemas/analysis-result.schema.json", "examples/analysis-result.strawberries.json")
ok &= validate(
    "schemas/analysis-result-v2.schema.json", "examples/analysis-result-v2.ground-beef.json"
)
ok &= validate(
    "schemas/analysis-evidence.schema.json", "examples/analysis-evidence.ground-beef.json"
)
ok &= validate(
    "schemas/canonical-product.schema.json", "examples/canonical-product.ground-beef.json"
)
ok &= validate(
    "schemas/product-detail-snapshot.schema.json", "examples/product-detail-snapshot.aldi.json"
)
ok &= validate("schemas/agent-output.schema.json", "examples/agent-output.ground-beef-insight.json")
ok &= validate("schemas/report-blueprint.schema.json", "examples/report-blueprint.ground-beef.json")
for p in sorted((ROOT / "examples").glob("historical-input-manifest.*.json")):
    ok &= validate("schemas/historical-input-manifest.schema.json", str(p.relative_to(ROOT)))
ok &= validate(
    "schemas/alert-definition.schema.json",
    "examples/alert-definition.amazon-pressure.json",
)
for p in sorted((ROOT / "product-packs").glob("fresh_*.json")):
    ok &= validate("schemas/product-pack.schema.json", str(p.relative_to(ROOT)))
for p in sorted((ROOT / "report-blueprints").glob("*.json")):
    ok &= validate("schemas/report-blueprint.schema.json", str(p.relative_to(ROOT)))
for p in sorted((ROOT / "agent-prompts").glob("*.json")):
    ok &= validate("schemas/agent-prompt.schema.json", str(p.relative_to(ROOT)))

# Fixture presence and known location-profile checks.
prof = load_json("fixtures/location_master/locations.profile.json")
checks = [
    (prof["rows"] == 157806, "location row count"),
    (prof["providers"] == 83, "provider count"),
    (prof["relevant_retailers"]["Walmart"]["locations"] == 4683, "Walmart location count"),
    (
        prof["relevant_retailers"]["Walmart"]["normalized_unique_zips"] == 4190,
        "Walmart normalized ZIP count",
    ),
    (prof["relevant_retailers"]["ALDI"]["locations"] == 2627, "ALDI location count"),
]
for passed, label in checks:
    print(("OK" if passed else "ERROR"), label)
    ok &= passed

ok &= validate_golden_benchmarks()

if not ok:
    sys.exit(2)
print("HANDOFF_VALIDATION_PASSED")
