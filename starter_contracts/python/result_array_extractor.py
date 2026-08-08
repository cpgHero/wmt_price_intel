"""Reference generic result-array extraction based on product-owner supplied behavior."""
from typing import Any

PATHS = [
    ("results",), ("items",), ("products",),
    ("result","results"), ("result","items"),
    ("data","results"), ("data","items"), ("data",)
]

def _get(payload: Any, path: tuple[str, ...]) -> Any:
    cur = payload
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur

def extract_result_array(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    for path in PATHS:
        value = _get(payload, path)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    return []
