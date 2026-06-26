"""Data connectors (keyless-first), mirroring aqueduct's source pattern.

Planned: edgar (SEC filings + fundamentals, keyless point-in-time backbone),
fred (macro), prices (stooq/yahoo EOD), crypto (coingecko/binance), fx
(frankfurter/ecb), openfigi (security-master IDs). Each lands as-of-stamped raw
payloads into the landing zone; normalization is bitemporal. See docs/ARCHITECTURE.md.
"""
