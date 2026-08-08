"""Generic nested provider result-array extraction."""

from __future__ import annotations

from typing import Any

DEFAULT_RESULT_PATHS = (
    ("results",),
    ("items",),
    ("products",),
    ("result", "results"),
    ("result", "items"),
    ("data", "results"),
    ("data", "items"),
    ("data",),
)


def extract_result_array(
    payload: Any, paths: tuple[tuple[str, ...], ...] = DEFAULT_RESULT_PATHS
) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    for path in paths:
        current = payload
        for key in path:
            if not isinstance(current, dict) or key not in current:
                current = None
                break
            current = current[key]
        if isinstance(current, list):
            return [item for item in current if isinstance(item, dict)]
    return []
