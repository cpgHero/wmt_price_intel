from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def _script() -> ModuleType:
    path = REPOSITORY_ROOT / "scripts" / "check_platform_docs_coverage.py"
    spec = importlib.util.spec_from_file_location("check_platform_docs_coverage", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_behavioral_change_requires_platform_docs_and_phase_record() -> None:
    gate = _script()
    assert len(gate.documentation_gate_violations(["apps/api/src/rci_api/operations.py"])) == 2
    assert (
        gate.documentation_gate_violations(
            [
                "apps/api/src/rci_api/operations.py",
                "apps/web/src/lib/platform-docs.ts",
                "docs/127_PHASE_13_73_PRODUCTION_OPERATIONS.md",
            ]
        )
        == []
    )


def test_tests_and_documentation_only_changes_do_not_require_change_order() -> None:
    gate = _script()
    assert (
        gate.documentation_gate_violations(["apps/api/tests/test_operations.py", "docs/README.md"])
        == []
    )
