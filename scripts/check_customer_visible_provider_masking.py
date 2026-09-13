#!/usr/bin/env python3
"""Fail CI when customer-visible surfaces expose private provider terms.

The forbidden terms are stored as SHA-256 hashes so this guard does not put the
private provider brand or credential parameter names into the script body.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

CUSTOMER_VISIBLE_ROOTS = (
    Path("apps/web/src/app"),
    Path("docs/170_PHASE_14_00_CPGHERO_PLATFORM_VISION_BLUEPRINT.md"),
    Path("docs/171_PHASE_14_01_CPGHERO_PLATFORM_CURRENT_STATE_AUDIT.md"),
    Path("docs/172_PHASE_14_02_CPGHERO_VISIBILITY_BOUNDARY.md"),
)

INTERNAL_PATH_PREFIXES = (
    "apps/web/src/app/admin/",
    "apps/web/src/app/api/admin/",
)

TEXT_SUFFIXES = {
    ".css",
    ".html",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".mjs",
    ".ts",
    ".tsx",
}

FORBIDDEN_TOKEN_HASHES = dict(
    [
        (
            "6600cbeacebb433efc02e6b982ce057db7e096ee5e2cd8c30f04666da1290dd5",
            "upstream provider brand",
        ),
        (
            "fa31957f97bbdf0c5efc6d10fd24b7ab33ea13fb669fa3b2631c184a8c7fd068",
            "upstream provider host",
        ),
        (
            "b27ef9f988acda1c21fd0c97989341a8c08bde875f573ef7542f32229e24a8b9",
            "provider API-key query parameter",
        ),
        (
            "6fcd68e24faedc1b6ef4db7341ba5dd28647eb1ffd4e2c4ad8410677e6db9f84",
            "upstream provider secret environment name",
        ),
    ]
)

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_.-]+")


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _candidate_paths() -> list[Path]:
    paths: list[Path] = []
    for root in CUSTOMER_VISIBLE_ROOTS:
        full = REPOSITORY_ROOT / root
        if not full.exists():
            continue
        if full.is_file():
            paths.append(full)
            continue
        for path in full.rglob("*"):
            if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
                continue
            relative = path.relative_to(REPOSITORY_ROOT).as_posix()
            if any(relative.startswith(prefix) for prefix in INTERNAL_PATH_PREFIXES):
                continue
            paths.append(path)
    return sorted(paths)


def _line_findings(path: Path) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    try:
        body = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        body = path.read_text(errors="ignore")
    for line_number, line in enumerate(body.splitlines(), start=1):
        labels: set[str] = set()
        for token in TOKEN_PATTERN.findall(line):
            digest = _hash(token.lower())
            if digest in FORBIDDEN_TOKEN_HASHES:
                labels.add(FORBIDDEN_TOKEN_HASHES[digest])
        if labels:
            findings.append((line_number, ", ".join(sorted(labels))))
    return findings


def main() -> int:
    violations: list[str] = []
    for path in _candidate_paths():
        for line_number, labels in _line_findings(path):
            relative = path.relative_to(REPOSITORY_ROOT).as_posix()
            violations.append(f"{relative}:{line_number}: {labels}")

    if violations:
        print("Customer-visible provider masking gate failed:")
        for violation in violations:
            print(f"- {violation}")
        return 1

    print("Customer-visible provider masking gate passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
