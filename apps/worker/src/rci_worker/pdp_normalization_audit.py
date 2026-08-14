"""Print a secret-free production PDP normalization completeness audit."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from rci_core import AppSettings
from rci_db import DatabaseProbe
from rci_products import PRODUCT_DETAIL_NORMALIZER_VERSION, PostgresProductDetailRepository


async def run() -> None:
    settings = AppSettings.from_env()
    database = DatabaseProbe(settings.database_url)
    repository_root = Path(os.getenv("RCI_REPOSITORY_ROOT", Path.cwd())).resolve()
    try:
        audit = await PostgresProductDetailRepository(
            database.engine,
            repository_root,
        ).normalization_audit(PRODUCT_DETAIL_NORMALIZER_VERSION)
        print(json.dumps(audit, indent=2, sort_keys=True))
    finally:
        await database.dispose()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
