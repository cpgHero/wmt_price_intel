#!/usr/bin/env python3
"""Fail CI when behavioral changes omit owner/admin documentation."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

PLATFORM_DOCS = "apps/web/src/lib/platform-docs.ts"


def _behavioral_change(path: str) -> bool:
    if path == PLATFORM_DOCS or path.startswith("docs/"):
        return False
    if any(part in path for part in ("/tests/", ".test.", ".spec.", "__pycache__")):
        return False
    if path.endswith((".md", ".png", ".jpg", ".jpeg")):
        return False
    roots = (
        "apps/api/src/",
        "apps/worker/src/",
        "apps/scheduler/src/",
        "apps/web/src/app/",
        "apps/web/src/lib/",
        "packages/python/",
        "packages/typescript/",
        "database/migrations/",
        "schemas/",
        "config/",
        "product-packs/",
        "retailer-packs/",
        "brand-foundations/",
        "agent-prompts/",
        "report-blueprints/",
        "infra/railway/",
    )
    return path.startswith(roots)


def documentation_gate_violations(changed_paths: list[str]) -> list[str]:
    if not any(_behavioral_change(path) for path in changed_paths):
        return []
    violations: list[str] = []
    if PLATFORM_DOCS not in changed_paths:
        violations.append(
            "behavioral changes require an update to apps/web/src/lib/platform-docs.ts"
        )
    phase_records = [
        path
        for path in changed_paths
        if path.startswith("docs/") and path.endswith(".md") and Path(path).name[:1].isdigit()
    ]
    if not phase_records:
        violations.append("behavioral changes require a numbered docs/ phase or change record")
    return violations


def changed_paths(base_ref: str) -> list[str]:
    normalized = base_ref.strip()
    if not normalized or set(normalized) == {"0"}:
        normalized = "HEAD^"
    command = ["git", "diff", "--name-only", f"{normalized}...HEAD"]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD^", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-ref", required=True)
    args = parser.parse_args()
    paths = changed_paths(args.base_ref)
    violations = documentation_gate_violations(paths)
    if violations:
        print("Platform Docs coverage gate failed:")
        for violation in violations:
            print(f"- {violation}")
        return 1
    print(f"Platform Docs coverage gate passed for {len(paths)} changed files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
