"""Normative AnalysisResult validation and canonical serialization."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from rci_contracts import validate_instance
from rci_results.models import JsonObject


def canonical_result_bytes(document: JsonObject) -> bytes:
    return json.dumps(
        document,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def result_checksum(document: JsonObject) -> str:
    return hashlib.sha256(canonical_result_bytes(document)).hexdigest()


class AnalysisResultValidator:
    def __init__(self, repository_root: Path) -> None:
        self._root = repository_root

    def validate(self, document: dict[str, Any]) -> JsonObject:
        validate_instance(
            self._root,
            "analysis-result.schema.json",
            document,
            label="AnalysisResult",
        )
        canonical = json.loads(canonical_result_bytes(document))
        assert isinstance(canonical, dict)
        return canonical
