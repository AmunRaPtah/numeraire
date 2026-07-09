"""Tests for openFDA drug event connector."""

from __future__ import annotations

import json

from numeraire.sources import openfda


def test_ingest(monkeypatch, env):
    """ingest() should parse FDA drug approval events."""
    payload = {
        "results": [{
            "application_number": "NDA208604",
            "sponsor_name": "ABBVIE INC.",
            "products": [{"brand_name": "VENCLEXTA",
                          "active_ingredients": [{"name": "venetoclax"}]}],
            "submissions": [{
                "submission_type": "SUPPLEMENT",
                "submission_number": "S-012",
                "submission_status": "APPR",
                "submission_status_date": "20240615",
            }],
        }]
    }
    monkeypatch.setattr(openfda.net, "request",
                        lambda url, **kw: json.dumps(payload).encode())
    result = openfda.ingest("ABBVIE", limit=10)
    path, total, added = result
    assert total > 0
    assert added > 0


def test_ingest_no_results(monkeypatch, env):
    """ingest() with no results should return 0."""
    monkeypatch.setattr(openfda.net, "request",
                        lambda url, **kw: json.dumps({"results": []}).encode())
    result = openfda.ingest("FAKECO", limit=10)
    # Returns (path, 0, 0) even when empty (writes 0 records)
    path, total, added = result
    assert total == 0


def test_ingest_404(monkeypatch, env):
    """ingest() with 404 should return 0 (no data for biologics/sponsors)."""
    from numeraire import net
    monkeypatch.setattr(openfda.net, "request",
                        lambda url, **kw: (_ for _ in ()).throw(
                            net.PermanentError("HTTP 404", status=404)))
    result = openfda.ingest("BIOTECHCO", limit=10)
    assert result == ("", 0, 0)


def test_ingest_error(monkeypatch, env):
    """ingest() on network error returns 0."""
    from numeraire import net
    monkeypatch.setattr(openfda.net, "request",
                        lambda url, **kw: (_ for _ in ()).throw(
                            net.NetworkError("fail")))
    result = openfda.ingest("ABBVIE", limit=10)
    assert result == ("", 0, 0)
