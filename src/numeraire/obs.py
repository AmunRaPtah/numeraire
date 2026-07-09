"""Minimal structured observability (stderr JSON lines). Keeps net.py faithful to
aqueduct's resilient-HTTP module without pulling its full telemetry stack."""

from __future__ import annotations

import contextlib
import json
import sys


def log(event: str, **fields) -> None:
    with contextlib.suppress(Exception):
        sys.stderr.write(json.dumps({"event": event, **fields}) + "\n")
