"""Central configuration: filesystem paths for each pipeline layer.

Adapted from aqueduct — same layered layout (landing zone + DuckDB warehouse),
state lives off-repo and is portable (relative paths) so it can sync via OneDrive.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("NUMERAIRE_DATA_DIR", ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"  # landing zone (as-of, immutable)
WAREHOUSE = DATA_DIR / "warehouse.duckdb"  # bitemporal DuckDB warehouse

# SEC requires a descriptive User-Agent with a contact address, or it 403s.
SEC_USER_AGENT = os.environ.get("NUMERAIRE_SEC_UA", "numeraire/0.1 (work@supercriticalbooks.com)")


def ensure_dirs() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)


def raw_source_dir(source: str) -> Path:
    d = RAW_DIR / source
    d.mkdir(parents=True, exist_ok=True)
    return d


def rel_data_path(p: Path | str) -> str:
    rp = Path(p).resolve()
    try:
        return str(rp.relative_to(DATA_DIR))
    except ValueError:
        return str(rp)
