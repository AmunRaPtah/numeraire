"""
Real-time price ingestion for Numeraire.

Provides background polling of yfinance for live price data, stored in a
``realtime_prices`` DuckDB table. Supports an LRU-managed watch list that
auto-rotates as Hermes strategies change their interest.

Usage:
    from numeraire.sources.realtime import get_realtime_price, watch_ticker
    ingester = RealtimeIngester()
    await ingester.poll_prices()  # one-shot poll
    await ingester.watch_loop()   # continuous polling
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import OrderedDict

log = logging.getLogger("numeraire.realtime")


# ── In-memory LRU watch list ────────────────────────────────────────────────

_MAX_WATCHED = 500


class LRUSet:
    """LRU-evicting set of watched symbols."""

    def __init__(self, maxsize: int = _MAX_WATCHED) -> None:
        self._data: OrderedDict[str, float] = OrderedDict()
        self._maxsize = maxsize

    def add(self, symbol: str) -> None:
        """Add or touch a symbol."""
        self._data[symbol] = time.time()
        self._data.move_to_end(symbol)
        while len(self._data) > self._maxsize:
            self._data.popitem(last=False)

    def remove(self, symbol: str) -> None:
        self._data.pop(symbol, None)

    def __contains__(self, symbol: str) -> bool:
        return symbol in self._data

    def __len__(self) -> int:
        return len(self._data)

    def items(self) -> list[str]:
        return list(self._data.keys())


_watch_list = LRUSet()


# ── DuckDB storage ──────────────────────────────────────────────────────────

_REALTIME_TABLE_DDL = """
    CREATE TABLE IF NOT EXISTS realtime_prices (
        ticker      VARCHAR,
        price       DOUBLE,
        change      DOUBLE,
        volume      BIGINT,
        ts          TIMESTAMP,
        source      VARCHAR   -- 'yfinance_poll' | 'yfinance_stream'
    )
"""

_REALTIME_TABLE_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_realtime_ticker_ts
    ON realtime_prices (ticker, ts DESC)
"""


def ensure_table(con) -> None:
    """Create the realtime_prices table and index if they don't exist."""
    con.execute(_REALTIME_TABLE_DDL)
    # index may already exist
    with contextlib.suppress(Exception):
        con.execute(_REALTIME_TABLE_INDEX)


def _store_tick(
    con, ticker: str, price: float, change: float, volume: int, source: str = "yfinance_poll"
) -> None:
    """Write one tick to DuckDB."""
    ensure_table(con)
    con.execute(
        "INSERT INTO realtime_prices (ticker, price, change, volume, ts, source) "
        "VALUES (?, ?, ?, ?, now(), ?)",
        [ticker, price, change, volume, source],
    )


def latest_tick(con, ticker: str) -> dict | None:
    """Return the most recent tick for a symbol, or None."""
    try:
        row = con.execute(
            "SELECT price, change, volume, ts, source FROM realtime_prices "
            "WHERE ticker = ? ORDER BY ts DESC LIMIT 1",
            [ticker],
        ).fetchone()
        if row:
            return {
                "ticker": ticker,
                "price": float(row[0]),
                "change": float(row[1]) if row[1] else 0.0,
                "volume": int(row[2]) if row[2] else 0,
                "timestamp": str(row[3]) if row[3] else None,
                "source": row[4],
            }
    except Exception:
        pass
    return None


def recent_ticks(con, ticker: str, n: int = 20) -> list[dict]:
    """Return the last N ticks for a symbol."""
    try:
        rows = con.execute(
            "SELECT price, change, volume, ts, source FROM realtime_prices "
            "WHERE ticker = ? ORDER BY ts DESC LIMIT ?",
            [ticker, n],
        ).fetchall()
        return [
            {
                "price": float(r[0]),
                "change": float(r[1]) if r[1] else 0.0,
                "volume": int(r[2]) if r[2] else 0,
                "timestamp": str(r[3]) if r[3] else None,
                "source": r[4],
            }
            for r in rows
        ]
    except Exception:
        return []


def cleanup_old_ticks(con, keep_hours: int = 24) -> int:
    """Remove ticks older than ``keep_hours``. Returns count deleted."""
    try:
        result = con.execute(
            "DELETE FROM realtime_prices WHERE ts < now() - INTERVAL ? HOUR",
            [keep_hours],
        )
        return result.fetchone()[0] if result else 0
    except Exception:
        return 0


# ── YFinance polling ────────────────────────────────────────────────────────


def _yf_bars(symbol: str) -> dict | None:
    """Fetch latest price bar from yfinance (blocking — run in executor)."""
    try:
        import yfinance as yf

        tk = yf.Ticker(symbol)
        hist = tk.history(period="2d", interval="1d")
        if hist.empty:
            return None
        latest = hist.iloc[-1]
        prev_close = hist.iloc[-2]["Close"] if len(hist) >= 2 else latest["Close"]
        change = ((latest["Close"] - prev_close) / prev_close) * 100
        return {
            "price": float(latest["Close"]),
            "change": float(change),
            "volume": int(latest["Volume"]) if latest["Volume"] else 0,
        }
    except Exception as exc:
        log.debug("yfinance poll failed for %s: %s", symbol, exc)
        return None


# ── RealtimeIngester ────────────────────────────────────────────────────────


class RealtimeIngester:
    """Background poller for real-time prices.

    Call ``poll_prices()`` for a one-shot fetch, or ``watch_loop()`` for
    continuous polling at a fixed interval.
    """

    def __init__(self, poll_interval: int = 60, con=None) -> None:
        self.poll_interval = poll_interval
        self._con = con  # optional shared connection
        self._running = False

    async def poll_prices(self) -> dict[str, dict]:
        """One-shot poll of all watched symbols.

        Returns dict of {symbol: tick_data} for symbols that were successfully
        fetched. Stores results to the DuckDB realtime_prices table.
        """
        symbols = _watch_list.items()
        if not symbols:
            return {}

        from numeraire.storage import connect

        con = self._con or connect()
        owns = self._con is None
        try:
            ensure_table(con)
            results: dict[str, dict] = {}

            loop = asyncio.get_event_loop()
            for sym in symbols:
                tick = await loop.run_in_executor(None, _yf_bars, sym)
                if tick:
                    _store_tick(
                        con,
                        sym,
                        tick["price"],
                        tick["change"],
                        tick["volume"],
                        source="yfinance_poll",
                    )
                    results[sym] = tick
                await asyncio.sleep(0.05)  # rate-limit: 20 req/s

            return results
        finally:
            if owns:
                con.close()

    async def watch_loop(self) -> None:
        """Continuously poll watched symbols at ``self.poll_interval``."""
        self._running = True
        log.info("Realtime ingester started (interval=%ds)", self.poll_interval)

        while self._running:
            try:
                n = len(_watch_list)
                if n:
                    results = await self.poll_prices()
                    log.debug("Polled %d/%d symbols", len(results), n)
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("Realtime poll error: %s", exc)
                await asyncio.sleep(self.poll_interval)

        log.info("Realtime ingester stopped")

    def stop(self) -> None:
        """Stop the watch loop."""
        self._running = False


# ── Module-level helpers ────────────────────────────────────────────────────


def watch(symbols: str | list[str]) -> None:
    """Add symbol(s) to the watch list."""
    if isinstance(symbols, str):
        symbols = [symbols]
    for s in symbols:
        _watch_list.add(s.upper())


def unwatch(symbols: str | list[str]) -> None:
    """Remove symbol(s) from the watch list."""
    if isinstance(symbols, str):
        symbols = [symbols]
    for s in symbols:
        _watch_list.remove(s.upper())


def watched_symbols() -> list[str]:
    """Return the current watch list."""
    return _watch_list.items()
