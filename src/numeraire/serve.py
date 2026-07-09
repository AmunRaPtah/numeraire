"""CLI entry: ``numeraire serve [--port 8100]``

Starts the Numeraire live signal API server.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="numeraire serve",
        description="Start the Numeraire live signal API server",
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=int(os.environ.get("NUMERAIRE_PORT", 8100)),
        help="Port to bind (default: 8100, env: NUMERAIRE_PORT)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="info",
        choices=["debug", "info", "warning", "error"],
        help="Logging level (default: info)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    try:
        import uvicorn
    except ImportError:
        print("uvicorn not installed. Install with: uv sync --extra serve", file=sys.stderr)
        sys.exit(1)

    print(f"Starting Numeraire Signal API on http://{args.host}:{args.port}")
    sys.stdout.flush()

    uvicorn.run(
        "numeraire.api:app",
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        reload=False,
    )
