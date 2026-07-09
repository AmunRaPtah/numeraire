"""Resilient HTTP for connectors (adapted from aqueduct).

One consistent failure policy for every outbound call:
- Structured errors: TransientError (retry: timeout/5xx/429/reset) vs PermanentError (4xx).
- Per-host rate limiting that honors Retry-After / 429 (parks the host).
- Exponential backoff + full jitter, capped.
- Per-host circuit breaker (fail fast after repeated failures).

Tuned for SEC EDGAR: a per-host min interval keeps us under SEC's ~10 req/s limit,
and the default User-Agent carries a contact address (SEC 403s otherwise).
"""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request

from . import obs
from .config import SEC_USER_AGENT

USER_AGENT = SEC_USER_AGENT

DEFAULT_RETRIES = 3
BACKOFF_BASE = 1.0
BACKOFF_CAP = 30.0
BREAKER_THRESHOLD = 5
BREAKER_COOLDOWN = 30.0
DEFAULT_MIN_INTERVAL = 0.0
MAX_PARK = 60.0


def _open(req, timeout):  # pragma: no cover
    return urllib.request.urlopen(req, timeout=timeout)


_sleep = time.sleep
_monotonic = time.monotonic


class NetworkError(Exception):
    def __init__(self, message: str, *, url: str | None = None, status: int | None = None):
        super().__init__(message)
        self.url = url
        self.status = status


class TransientError(NetworkError): ...


class PermanentError(NetworkError): ...


class RateLimitError(TransientError):
    def __init__(self, message: str, *, url=None, status=429, retry_after: float | None = None):
        super().__init__(message, url=url, status=status)
        self.retry_after = retry_after


class CircuitOpenError(TransientError): ...


class _HostState:
    __slots__ = ("next_allowed", "fails", "open_until")

    def __init__(self):
        self.next_allowed = 0.0
        self.fails = 0
        self.open_until = 0.0


class RateLimiter:
    def __init__(
        self, min_interval=DEFAULT_MIN_INTERVAL, threshold=BREAKER_THRESHOLD, cooldown=BREAKER_COOLDOWN
    ):
        self.min_interval = min_interval
        self.threshold = threshold
        self.cooldown = cooldown
        self._hosts: dict[str, _HostState] = {}
        self.intervals: dict[str, float] = {}

    def _state(self, host):
        return self._hosts.setdefault(host, _HostState())

    def before(self, host):
        st = self._state(host)
        now = _monotonic()
        if st.open_until > now:
            raise CircuitOpenError(f"circuit open for {host} ({st.open_until - now:.1f}s left)", url=host)
        wait = st.next_allowed - now
        if wait > 0:
            _sleep(min(wait, MAX_PARK))

    def _interval(self, host):
        return self.intervals.get(host, self.min_interval)

    def on_success(self, host):
        st = self._state(host)
        st.fails = 0
        st.open_until = 0.0
        st.next_allowed = _monotonic() + self._interval(host)

    def on_failure(self, host, *, retry_after=None):
        st = self._state(host)
        st.fails += 1
        park = retry_after if retry_after is not None else self._interval(host)
        st.next_allowed = _monotonic() + min(max(park, 0.0), MAX_PARK)
        if st.fails >= self.threshold:
            st.open_until = _monotonic() + self.cooldown
            obs.log("net.circuit_open", host=host, fails=st.fails, cooldown=self.cooldown)

    def is_open(self, host):
        return self._state(host).open_until > _monotonic()


LIMITER = RateLimiter()
# SEC limit is ~10 req/s across both hosts; 0.12s floor => ~8 req/s, comfortably under.
LIMITER.intervals["data.sec.gov"] = 0.12
LIMITER.intervals["www.sec.gov"] = 0.12


def _host(url):
    try:
        return urllib.parse.urlparse(url).netloc or url
    except Exception:
        return url


def _retry_after(headers):
    if headers is None:
        return None
    val = headers.get("Retry-After")
    if not val:
        return None
    try:
        return max(0.0, float(val))
    except (TypeError, ValueError):
        return None


def _backoff(attempt, retry_after):
    if retry_after is not None:
        return min(retry_after, BACKOFF_CAP)
    base = min(BACKOFF_BASE * (2**attempt), BACKOFF_CAP)
    return base / 2 + random.uniform(0, base / 2)


def request(url, *, data=None, headers=None, timeout=30, retries=DEFAULT_RETRIES, limiter=None):
    limiter = limiter or LIMITER
    host = _host(url)
    hdrs = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate", **(headers or {})}
    last = None
    for attempt in range(retries):
        limiter.before(host)
        try:
            req = urllib.request.Request(url, data=data, headers=hdrs)
            with _open(req, timeout) as resp:
                body = resp.read()
                enc = resp.headers.get("Content-Encoding", "")
            if "gzip" in enc:
                import gzip

                body = gzip.decompress(body)
            elif "deflate" in enc:
                import zlib

                body = zlib.decompress(body)
            limiter.on_success(host)
            return body
        except urllib.error.HTTPError as e:
            ra = _retry_after(getattr(e, "headers", None))
            if e.code == 429:
                err = RateLimitError(f"429 rate limited: {url}", url=url, retry_after=ra)
            elif e.code == 408 or 500 <= e.code < 600:
                err = TransientError(f"HTTP {e.code}: {url}", url=url, status=e.code)
            else:
                limiter.on_failure(host, retry_after=ra)
                raise PermanentError(f"HTTP {e.code}: {url}", url=url, status=e.code) from e
            limiter.on_failure(host, retry_after=ra)
            last = err
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            limiter.on_failure(host)
            last = TransientError(f"{type(e).__name__}: {url} ({e})", url=url)
        if attempt < retries - 1:
            delay = _backoff(attempt, getattr(last, "retry_after", None))
            obs.log("net.retry", host=host, attempt=attempt + 1, delay=round(delay, 2), error=str(last))
            _sleep(delay)
    raise last or TransientError(f"request failed: {url}", url=url)


def get_bytes(url, *, timeout=30, retries=DEFAULT_RETRIES, headers=None):
    return request(url, timeout=timeout, retries=retries, headers=headers)


def get_json(url, *, timeout=30, retries=DEFAULT_RETRIES, headers=None):
    return json.loads(request(url, timeout=timeout, retries=retries, headers=headers))
