#!/usr/bin/env python3
"""Create immutable Retailer Pack patch releases for a Brand Foundation release."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _version_key(value: str) -> tuple[int, int, int]:
    major, minor, patch = value.split(".")
    return int(major), int(minor), int(patch)


def _next_patch(value: str) -> str:
    major, minor, patch = _version_key(value)
    return f"{major}.{minor}.{patch + 1}"


def release(root: Path, foundation_id: str, foundation_version: str) -> list[dict[str, Any]]:
    index_path = root / "retailer-packs" / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    active: dict[str, dict[str, Any]] = {}
    for summary in index["packs"]:
        retailer_id = str(summary["id"])
        current = active.get(retailer_id)
        if current is None or _version_key(str(summary["version"])) > _version_key(
            str(current["version"])
        ):
            active[retailer_id] = summary

    created: list[dict[str, Any]] = []
    existing = {(str(row["id"]), str(row["version"])) for row in index["packs"]}
    for retailer_id, summary in sorted(active.items()):
        source = root / "retailer-packs" / str(summary["file"])
        document = json.loads(source.read_text(encoding="utf-8"))
        if document["brand_foundation"] == {
            "id": foundation_id,
            "version": foundation_version,
        }:
            continue
        version = _next_patch(str(document["version"]))
        if (retailer_id, version) in existing:
            raise ValueError(f"Retailer Pack {retailer_id}@{version} already exists")
        document["version"] = version
        document["brand_foundation"] = {
            "id": foundation_id,
            "version": foundation_version,
        }
        relative = Path(retailer_id) / f"{version}.json"
        destination = root / "retailer-packs" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            f"{json.dumps(document, ensure_ascii=False, indent=2)}\n",
            encoding="utf-8",
        )
        created.append(
            {
                "id": retailer_id,
                "version": version,
                "file": str(relative),
            }
        )
    index["packs"].extend(created)
    index_path.write_text(
        f"{json.dumps(index, ensure_ascii=False, indent=2)}\n",
        encoding="utf-8",
    )
    return created


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--foundation-id", default="cpg_brand_foundation")
    parser.add_argument("--foundation-version", required=True)
    args = parser.parse_args()
    created = release(
        args.repository_root.resolve(),
        args.foundation_id,
        args.foundation_version,
    )
    print(json.dumps({"created": created}, indent=2))


if __name__ == "__main__":
    main()
