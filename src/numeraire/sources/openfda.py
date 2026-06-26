"""openFDA connector — keyless FDA drug data (catalysts for pharma/biotech investing).

Drug approvals, supplements, and their dates are *binary catalysts* that move biotech
equities. openFDA's drugsfda endpoint is keyless (240 req/min). Each approval/submission
is landed as a dated event keyed to a sponsor, so it can be joined to a ticker (via the
sponsor name) and aligned point-in-time with price/fundamentals.

Pairs with the aqueduct bridge (clinical-trial pipeline + drug->target graph) and EDGAR
financials to form the pharma/biotech research surface. See docs/ARCHITECTURE.md ADR-8.
"""

from __future__ import annotations

import json
import urllib.parse
from datetime import datetime, timezone

from .. import config, net
from ..landing import merge_jsonl

DRUGSFDA = "https://api.fda.gov/drug/drugsfda.json"
KEY = ("application_number", "submission_type", "submission_number")


def _events(payload: dict):
    fetched = datetime.now(timezone.utc).isoformat()
    for r in payload.get("results", []):
        app = r.get("application_number")
        sponsor = r.get("sponsor_name")
        products = r.get("products") or []
        brand = "; ".join(sorted({p.get("brand_name", "") for p in products if p.get("brand_name")}))
        substance = "; ".join(sorted({s for p in products for s in (p.get("active_ingredients") or [])
                                      if isinstance(s, str)})) or \
                    "; ".join(sorted({ai.get("name", "") for p in products
                                      for ai in (p.get("active_ingredients") or []) if isinstance(ai, dict)}))
        for sub in (r.get("submissions") or []):
            sd = sub.get("submission_status_date")  # YYYYMMDD
            iso = f"{sd[:4]}-{sd[4:6]}-{sd[6:8]}" if sd and len(sd) == 8 else None
            yield {
                "application_number": app, "sponsor_name": sponsor,
                "brand": brand, "substance": substance,
                "submission_type": sub.get("submission_type"),
                "submission_number": sub.get("submission_number"),
                "submission_status": sub.get("submission_status"),
                "event_date": iso,            # the catalyst date (approval/supplement)
                "review_priority": sub.get("review_priority"),
                "fetched_at": fetched,
            }


def ingest(sponsor: str, limit: int = 1000) -> tuple[str, int, int]:
    """Land FDA drug approval/submission events for a sponsor (company) name."""
    q = sponsor.replace('"', "")
    url = f'{DRUGSFDA}?search=sponsor_name:"{urllib.parse.quote(q)}"&limit=100'
    try:
        payload = json.loads(net.request(url, timeout=30))
    except net.PermanentError as e:
        if getattr(e, "status", None) == 404:   # openFDA's "no matches" (e.g. biologics-only)
            print(f"[openfda]  {sponsor}: no drugsfda matches (biologics live in CBER/trials)")
            return ("", 0, 0)
        print(f"[openfda]  {sponsor}: {e}"); return ("", 0, 0)
    except net.NetworkError as e:
        print(f"[openfda]  {sponsor}: {e}"); return ("", 0, 0)
    rows = list(_events(payload))
    src = config.raw_source_dir("openfda")
    safe = "".join(c if c.isalnum() else "_" for c in sponsor)[:40]
    path = src / f"{safe}.jsonl"
    total, added = merge_jsonl(path, rows, KEY)
    print(f"[openfda]  {sponsor}: {len(rows)} events, +{added} new ({total}) -> {path.name}")
    return (config.rel_data_path(path), total, added)
