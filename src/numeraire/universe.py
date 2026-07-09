"""Starter investable universe (curated). A real run reconstructs this point-in-time
from listings + survivorship-free membership (ADR-2); this fixed list is enough to
exercise the research loop. Mix of liquid large-caps + pharma/biotech.
"""

GENERAL = [
    "AAPL",
    "MSFT",
    "GOOGL",
    "AMZN",
    "NVDA",
    "META",
    "JPM",
    "XOM",
    "WMT",
    "KO",
    "PG",
    "HD",
    "DIS",
    "INTC",
    "CSCO",
]
PHARMA_BIOTECH = ["JNJ", "PFE", "MRK", "ABBV", "LLY", "GILD", "AMGN", "MRNA", "BIIB", "REGN", "VRTX", "BMY"]

DEFAULT = GENERAL + PHARMA_BIOTECH

# Yahoo's chart endpoint (sources/prices.py) serves crypto pairs on the same API as
# equities, so spot price + basic history needs no new connector — just a curated
# list, for the crypto_macro strategy's price leg (macro/on-chain data stays live-only).
CRYPTO = [
    "BTC-USD",
    "ETH-USD",
    "SOL-USD",
    "BNB-USD",
    "XRP-USD",
    "ADA-USD",
    "DOGE-USD",
    "AVAX-USD",
    "LINK-USD",
    "DOT-USD",
]
