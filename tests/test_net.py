"""Tests for the resilient HTTP client — rate limiter, circuit breaker, retry.

All tests monkeypatch the module-level _open/_sleep/_monotonic seam so nothing
touches the network (same pattern as aqueduct).
"""

from __future__ import annotations

from io import BytesIO

import pytest

from numeraire import net


class _Resp(BytesIO):
    """Minimal mock HTTP response with headers."""

    def __init__(self, body: bytes, status: int = 200, headers: dict | None = None):
        super().__init__(body)
        self.status = status
        self._hdrs = headers or {}
        self.headers = self._hdrs

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


@pytest.fixture
def nosleep(monkeypatch):
    """Replace sleep with a mock clock. Callers advance clock.t manually."""
    clock = [1000.0]
    monkeypatch.setattr(net, "_monotonic", lambda: clock[0])
    monkeypatch.setattr(net, "_sleep", lambda s: clock.__setitem__(0, clock[0] + s))
    monkeypatch.setattr(net, "LIMITER", net.RateLimiter())
    return clock


# ── Rate limiter ──────────────────────────────────────────────────────────


def test_rate_limiter_before_blocks(nosleep):
    lr = net.RateLimiter(min_interval=1.0)
    lr.on_success("example.com")  # sets next_allowed = now + 1.0
    # Should not raise (next_allowed = 1000 + 1.0 = 1001, now = 1000)
    lr.before("example.com")


def test_rate_limiter_before_parks(nosleep):
    """Calling before() while next_allowed > now should sleep."""
    lr = net.RateLimiter(min_interval=5.0)
    lr.on_success("example.com")  # next_allowed = 1000 + 5.0 = 1005
    clock = nosleep
    lr.before("example.com")  # parks 5s -> clock=1005
    assert clock[0] == 1005.0


def test_circuit_breaker_opens(nosleep):
    lr = net.RateLimiter(threshold=3, cooldown=10.0)
    host = "down.example.com"
    lr.on_failure(host)
    lr.on_failure(host)
    lr.on_failure(host)  # threshold reached -> open
    assert lr.is_open(host)
    with pytest.raises(net.CircuitOpenError):
        lr.before(host)


def test_circuit_breaker_recovers(nosleep):
    lr = net.RateLimiter(threshold=2, cooldown=5.0)
    host = "down.example.com"
    lr.on_failure(host)
    lr.on_failure(host)
    assert lr.is_open(host)
    clock = nosleep
    clock[0] += 10.0  # advance past cooldown
    assert not lr.is_open(host)
    lr.before(host)  # should not raise


def test_on_success_resets_fails(nosleep):
    lr = net.RateLimiter(threshold=2)
    host = "ex.com"
    lr.on_failure(host)
    assert lr._state(host).fails == 1
    lr.on_success(host)
    assert lr._state(host).fails == 0
    assert lr.is_open(host) is False


# ── HTTP request ──────────────────────────────────────────────────────────


def test_get_bytes_success(monkeypatch, nosleep):
    monkeypatch.setattr(net, "_open", lambda req, timeout: _Resp(b"ok", 200))
    body = net.get_bytes("http://example.com/data", retries=1)
    assert body == b"ok"


def test_get_json_success(monkeypatch, nosleep):
    monkeypatch.setattr(net, "_open", lambda req, timeout: _Resp(b'{"a": 1}', 200))
    data = net.get_json("http://example.com/data", retries=1)
    assert data == {"a": 1}


def test_retry_on_500(monkeypatch, nosleep):
    calls = []

    def flaky(req, timeout):
        calls.append(req.full_url)
        if len(calls) < 3:
            raise urllib.error.HTTPError(req.full_url, 500, "Server Error", {}, BytesIO())
        return _Resp(b"finally ok", 200)

    import urllib.error

    monkeypatch.setattr(net, "_open", flaky)
    body = net.get_bytes("http://example.com/retry", retries=3)
    assert body == b"finally ok"
    assert len(calls) == 3


def test_raise_permanent_on_404(monkeypatch, nosleep):
    import urllib.error

    monkeypatch.setattr(
        net,
        "_open",
        lambda req, timeout: (_ for _ in ()).throw(
            urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, BytesIO())
        ),
    )
    with pytest.raises(net.PermanentError):
        net.get_bytes("http://example.com/404", retries=2)


def test_gzip_decompression(monkeypatch, nosleep):
    import gzip

    compressed = gzip.compress(b'{"compressed": true}')
    monkeypatch.setattr(
        net, "_open", lambda req, timeout: _Resp(compressed, 200, {"Content-Encoding": "gzip"})
    )
    data = net.get_json("http://example.com/gzip", retries=1)
    assert data == {"compressed": True}


def test_rate_limiter_host_isolation(monkeypatch):
    """Failure on one host shouldn't affect another."""
    lr = net.RateLimiter(threshold=1, cooldown=30.0)
    lr.on_failure("bad.com")
    # good.com should be unaffected
    lr.before("good.com")  # should not raise
