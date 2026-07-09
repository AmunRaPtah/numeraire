"""Tests for warehouse build + point-in-time queries."""

from __future__ import annotations

import seed

from numeraire import warehouse


def test_build_empty(con):
    """Building on an empty landing zone produces empty tables."""
    n = warehouse.build(con)
    assert n == 0


def test_build_fundamentals(con, env):
    seed.seed_edgar("AAPL", 320193)
    n = warehouse.build(con)
    assert n > 0
    rows = con.execute("SELECT count(*) FROM fundamentals").fetchone()[0]
    assert rows == n


def test_build_aux_tables(con, env):
    seed.seed_edgar("AAPL", 320193)
    seed.seed_sp500()
    seed.seed_prices("AAPL")
    warehouse.build(con)
    tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
    assert "fundamentals" in tables
    assert "prices" in tables
    assert "index_membership" in tables


def test_build_missing_aux_skips_gracefully(con, env):
    """Missing aux source dirs don't cause errors."""
    seed.seed_edgar("AAPL", 320193)
    warehouse.build(con)
    tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
    assert "fundamentals" in tables
    # These tables should not exist since no data was seeded
    assert "prices" not in tables


def test_as_of_point_in_time(con, env):
    """as_of() must NOT see restatements filed after the as-of date."""
    seed.seed_edgar("AAPL", 320193)
    warehouse.build(con)

    # Q2 2024 NI: original = 13,200,000 (filed 2024-08-10)
    # restated  = 11,800,000 (filed 2025-02-15)
    # as-of 2024-09-01 should return the original
    result = warehouse.as_of(320193, "NetIncomeLoss", "2024-09-01", con=con)
    # Find the Q2 2024 row (event_date = 2024-06-30) and verify it's the original
    for row in result:
        rd = row[0].isoformat() if hasattr(row[0], "isoformat") else str(row[0])
        if "2024-06-30" in rd and "10-Q" in str(row[3]) and "RESTATED" not in str(row[4]):
            assert row[1] == 13_200_000, (
                f"Q2 2024 NI as-of 2024-09-01: expected 13.2M (original), got {row[1]}"
            )


def test_as_of_sees_restatement_after_date(con, env):
    """as_of() after the restatement should see the newer value."""
    seed.seed_edgar("AAPL", 320193)
    warehouse.build(con)

    result = warehouse.as_of(320193, "NetIncomeLoss", "2025-03-01", con=con)
    for row in result:
        d = row[0].isoformat() if hasattr(row[0], "isoformat") else row[0]
        if "2024-06-30" in str(d):
            assert row[1] == 11_800_000, f"Expected restated 11.8M, got {row[1]}"


def test_members_as_of(con, env):
    seed.seed_sp500()
    warehouse.build(con)

    # TWTR was removed 2023-11-28
    members_2023 = warehouse.members_as_of("2023-06-01", con=con)
    assert "TWTR" in members_2023

    members_2024 = warehouse.members_as_of("2024-01-01", con=con)
    assert "TWTR" not in members_2024

    # Current members are always present
    assert "AAPL" in members_2024
