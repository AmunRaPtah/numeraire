"""Test fixtures: isolated temp DuckDB warehouse for every test.

Pattern adapted from aqueduct — same config/warehouse seam, same two-fixture shape.
Each test gets a real (but ephemeral) DuckDB database with no network access needed.
"""

from __future__ import annotations

import pytest

from numeraire import config
from numeraire.storage import connect


@pytest.fixture
def env(monkeypatch, tmp_path):
    """Redirect all data paths to a temporary directory.

    Every test using this fixture gets an isolated landing zone + warehouse
    that is automatically cleaned up. No state leaks between tests.
    """
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "WAREHOUSE", tmp_path / "warehouse.duckdb")
    (tmp_path / "raw").mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture
def con(env):
    """Open a real DuckDB connection to an isolated temp warehouse.

    Note: functions that receive `con` do NOT close it (they check owns=con is None).
    The fixture closes it at teardown.
    """
    c = connect()
    yield c
    try:
        c.close()
    except Exception:
        pass
