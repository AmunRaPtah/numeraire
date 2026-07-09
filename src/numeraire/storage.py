"""DuckDB warehouse connection (adapted from aqueduct): memory-capped + lock-retry."""

from __future__ import annotations

import os
import time

import duckdb

from . import config

_DB_MEMORY_LIMIT = os.environ.get("NUMERAIRE_DB_MEMORY_LIMIT", "1GB")
_DB_THREADS = os.environ.get("NUMERAIRE_DB_THREADS", "2")


def connect(retries: int = 8, wait: float = 3.0) -> duckdb.DuckDBPyConnection:
    config.ensure_dirs()
    cfg = {
        "memory_limit": _DB_MEMORY_LIMIT,
        "threads": _DB_THREADS,
        "temp_directory": str(config.DATA_DIR / ".duckdb_tmp"),
    }
    last: Exception | None = None
    for _ in range(max(retries, 1)):
        try:
            return duckdb.connect(str(config.WAREHOUSE), config=cfg)
        except duckdb.IOException as e:
            last = e
            time.sleep(wait)
    raise last  # type: ignore[misc]
