"""Generic nested provider result-array extraction."""

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class ResultArrayExtraction:
    results: list[dict[str, Any]]
    path: tuple[str, ...] | None
    source_count: int = 0

    @property
    def recognized(self) -> bool:
        return self.path is not None


def inspect_result_array(
    payload: Any, paths: tuple[tuple[str, ...], ...] = DEFAULT_RESULT_PATHS
) -> ResultArrayExtraction:
    """Return results and the recognized provider path, including valid empty arrays."""

    if isinstance(payload, list):
        return ResultArrayExtraction(
            results=[item for item in payload if isinstance(item, dict)],
            path=(),
            source_count=len(payload),
        )
    for path in paths:
        current = payload
        for key in path:
            if not isinstance(current, dict) or key not in current:
                current = None
                break
            current = current[key]
        if isinstance(current, list):
            return ResultArrayExtraction(
                results=[item for item in current if isinstance(item, dict)],
                path=path,
                source_count=len(current),
            )
    return ResultArrayExtraction(results=[], path=None, source_count=0)


def extract_result_array(
    payload: Any, paths: tuple[tuple[str, ...], ...] = DEFAULT_RESULT_PATHS
) -> list[dict[str, Any]]:
    return inspect_result_array(payload, paths).results
