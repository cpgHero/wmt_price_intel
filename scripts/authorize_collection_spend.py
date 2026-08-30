#!/usr/bin/env python3
"""Create one immutable, offline collection-spend authorization.

This command is deliberately not an HTTP endpoint. It is the audited operator
boundary between an owner's explicit authorization and recovery-batch creation.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from rci_collections import CollectionRetailerCatalog
from rci_collections.composite import PostgresCompositeEvidenceRepository
from rci_core import AppSettings
from rci_db import DatabaseProbe


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--phase-key", required=True)
    parser.add_argument("--collection-run-id", action="append", required=True, dest="run_ids")
    parser.add_argument("--approved-credit-ceiling", type=int, required=True)
    parser.add_argument("--unit-cost-usd", default="0.002000")
    parser.add_argument("--currency", default="USD")
    parser.add_argument("--reason", required=True)
    parser.add_argument("--authorized-by", required=True)
    parser.add_argument(
        "--confirm-owner-authorization",
        action="store_true",
        help="Required acknowledgement that the exact inventory and ceiling were owner-approved.",
    )
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> dict[str, object]:
    if not args.confirm_owner_authorization:
        raise ValueError("--confirm-owner-authorization is required")
    root = args.repository_root.resolve(strict=True)
    settings = AppSettings.from_env()
    database = DatabaseProbe(settings.database_url)
    try:
        catalog = CollectionRetailerCatalog.from_path(root / "config" / "retailer-catalog.json")
        repository = PostgresCompositeEvidenceRepository(
            database.engine,
            provider_request_contracts=catalog.provider_request_contracts(),
        )
        record = await repository.authorize_recovery_spend(
            organization_id=args.organization_id,
            phase_key=args.phase_key,
            approved_credit_ceiling=args.approved_credit_ceiling,
            unit_cost_usd=args.unit_cost_usd,
            currency=args.currency,
            reason=args.reason,
            authorized_by=args.authorized_by,
            collection_run_ids=tuple(args.run_ids),
        )
        return asdict(record)
    finally:
        await database.dispose()


if __name__ == "__main__":
    print(json.dumps(asyncio.run(_run(_arguments())), default=str, sort_keys=True))
