"""Fail-closed administrator CLI for location-eligibility reconciliation."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from rci_core import AppSettings
from rci_db import DatabaseProbe
from rci_locations.catalog import RetailerCatalog
from rci_locations.eligibility import EligibilityReconciler, plan_as_json, plan_from_json
from rci_locations.repository import PostgresLocationRepository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Re-evaluate persisted location collection eligibility from the current "
            "retailer catalog. The default is a read-only dry run."
        )
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path("config/retailer-catalog.json"),
    )
    parser.add_argument(
        "--retailer",
        action="append",
        default=[],
        help="Catalogued retailer ID to reconcile. Repeat as needed; omit to inspect all rows.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply an exact reviewed dry-run plan inside a guarded transaction.",
    )
    parser.add_argument(
        "--reviewed-plan",
        type=Path,
        help="Dry-run JSON artifact to verify and apply. Required with --apply.",
    )
    parser.add_argument(
        "--requested-by",
        help="Identified administrator/operator. Required with --apply.",
    )
    parser.add_argument(
        "--change-reason",
        help="Operational reason for the correction. Required with --apply.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path for the complete JSON audit document.",
    )
    return parser


async def run_reconciliation(
    *,
    catalog_path: Path,
    retailer_ids: set[str],
    apply: bool,
    requested_by: str | None,
    change_reason: str | None,
    reviewed_plan_path: Path | None,
    output: Path | None,
) -> int:
    if apply and (not requested_by or not requested_by.strip()):
        raise ValueError("--requested-by is required with --apply")
    if apply and (not change_reason or not change_reason.strip()):
        raise ValueError("--change-reason is required with --apply")
    if apply and reviewed_plan_path is None:
        raise ValueError("--reviewed-plan is required with --apply")
    if not apply and reviewed_plan_path is not None:
        raise ValueError("--reviewed-plan may only be used with --apply")
    if apply and retailer_ids:
        raise ValueError("--retailer cannot override the scope in --reviewed-plan")
    if (
        reviewed_plan_path is not None
        and output is not None
        and reviewed_plan_path.resolve() == output.resolve()
    ):
        raise ValueError("--output cannot overwrite --reviewed-plan")

    reviewed_plan = None
    if reviewed_plan_path is not None:
        reviewed_plan = plan_from_json(
            json.loads(reviewed_plan_path.resolve().read_text(encoding="utf-8"))
        )

    database = DatabaseProbe(AppSettings.from_env().database_url)
    try:
        repository = PostgresLocationRepository(database.engine)
        resolved_catalog = catalog_path.resolve()
        reconciler = EligibilityReconciler(
            repository,
            RetailerCatalog.from_path(resolved_catalog),
            catalog_path=resolved_catalog,
        )
        if apply:
            if reviewed_plan is None:
                raise RuntimeError("reviewed plan validation did not produce a plan")
            plan = await reconciler.apply(
                reviewed_plan,
                requested_by=requested_by or "",
                change_reason=change_reason or "",
            )
        else:
            plan = await reconciler.plan(retailer_ids=retailer_ids or None)
        document = plan_as_json(plan)
        serialized = json.dumps(document, indent=2, sort_keys=True) + "\n"
        if output is not None:
            resolved_output = output.resolve()
            resolved_output.parent.mkdir(parents=True, exist_ok=True)
            resolved_output.write_text(serialized, encoding="utf-8")
            print(
                json.dumps(
                    {
                        "audit_run_id": plan.audit_run_id,
                        "changed_rows": plan.changed_rows,
                        "mode": document["mode"],
                        "output": str(resolved_output),
                        "scanned_rows": plan.scanned_rows,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(serialized, end="")
    finally:
        await database.dispose()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return asyncio.run(
        run_reconciliation(
            catalog_path=args.catalog,
            retailer_ids=set(args.retailer),
            apply=args.apply,
            requested_by=args.requested_by,
            change_reason=args.change_reason,
            reviewed_plan_path=args.reviewed_plan,
            output=args.output,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
