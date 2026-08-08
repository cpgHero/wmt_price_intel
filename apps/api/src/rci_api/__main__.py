"""Production API process with JSON logging and Railway PORT binding."""

from __future__ import annotations

import os

import uvicorn

from rci_core import AppSettings, configure_logging


def main() -> None:
    settings = AppSettings.from_env()
    configure_logging("api", settings.log_level)
    uvicorn.run(
        "rci_api.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        log_config=None,
        access_log=True,
        proxy_headers=True,
    )


if __name__ == "__main__":
    main()
