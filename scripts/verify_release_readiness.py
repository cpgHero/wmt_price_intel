#!/usr/bin/env python3
"""Zero-credit public health and release-version verifier."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    url: str
    passed: bool
    status_code: int | None
    detail: str


def _get_json(url: str, timeout: float) -> tuple[int, dict[str, Any]]:
    request = Request(url, headers={"accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - operator-selected URL
        body = json.loads(response.read().decode("utf-8"))
        return int(response.status), body


def verify_endpoint(
    name: str,
    url: str,
    *,
    expected_status: str,
    timeout: float,
) -> CheckResult:
    try:
        status_code, body = _get_json(url, timeout)
    except HTTPError as exc:
        return CheckResult(name, url, False, exc.code, f"HTTP {exc.code}")
    except (URLError, TimeoutError, ValueError) as exc:
        return CheckResult(name, url, False, None, exc.__class__.__name__)
    observed = str(body.get("status") or "")
    passed = status_code == 200 and observed == expected_status
    return CheckResult(
        name,
        url,
        passed,
        status_code,
        f"status={observed or 'missing'}",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--web-base", required=True)
    parser.add_argument("--api-base", required=True)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--output")
    args = parser.parse_args()
    web = args.web_base.rstrip("/")
    api = args.api_base.rstrip("/")
    checks = [
        verify_endpoint("web liveness", f"{web}/health", expected_status="ok", timeout=args.timeout),
        verify_endpoint(
            "web readiness", f"{web}/health/ready", expected_status="ready", timeout=args.timeout
        ),
        verify_endpoint(
            "api liveness", f"{api}/health/live", expected_status="ok", timeout=args.timeout
        ),
        verify_endpoint(
            "api readiness", f"{api}/health/ready", expected_status="ready", timeout=args.timeout
        ),
    ]
    document = {
        "schema_version": "1.0.0-release-readiness-check",
        "passed": all(check.passed for check in checks),
        "paid_provider_calls": 0,
        "checks": [asdict(check) for check in checks],
    }
    output = json.dumps(document, indent=2, sort_keys=True)
    print(output)
    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
    return 0 if document["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
