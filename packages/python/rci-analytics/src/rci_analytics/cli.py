"""Run the generic analytics engine against compact CSV fixtures."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict
from pathlib import Path

from rci_analytics.classification import OfferClassifier
from rci_analytics.matching import ComparisonEngine, geographic_overlap
from rci_analytics.normalization import CanonicalOfferNormalizer, RetailerIdentityMap
from rci_analytics.product_pack import ProductPackLoader


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--product-pack", required=True)
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--competitor", action="append", default=[])
    parser.add_argument("inputs", nargs="+", type=Path)
    return parser.parse_args()


def _rows(path: Path) -> list[dict[str, object]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def main() -> None:
    args = _arguments()
    root = args.root.resolve()
    pack = ProductPackLoader(root).load(args.product_pack)
    normalizer = CanonicalOfferNormalizer(
        RetailerIdentityMap.from_catalog(root / "config" / "retailer-catalog.json")
    )
    normalized = [
        offer
        for input_path in args.inputs
        for offer in normalizer.normalize_many(_rows(input_path))
    ]
    classified = OfferClassifier(pack).classify_many(normalized)
    engine = ComparisonEngine(pack)
    summaries = []
    for competitor in args.competitor:
        for profile in pack.matching_profiles:
            matches = engine.compare(
                classified,
                benchmark_id=args.benchmark,
                competitor_id=competitor,
                profile_id=str(profile["id"]),
            )
            if matches:
                summaries.append(asdict(engine.summarize(matches)))
    output = {
        "product_pack": {"id": pack.id, "version": pack.version},
        "source_rows": sum(len(_rows(path)) for path in args.inputs),
        "normalized_rows": len(normalized),
        "in_scope_rows": sum(item.in_scope for item in classified),
        "coverage": {
            competitor: len(geographic_overlap(classified, args.benchmark, competitor))
            for competitor in args.competitor
        },
        "comparisons": summaries,
    }
    print(json.dumps(output, indent=2, default=str))


if __name__ == "__main__":
    main()
