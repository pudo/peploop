"""Fetch things over HTTP, politely and with a cache.

Wikimedia 403s the default requests User-Agent and throttles anonymous
clients, so every request carries a descriptive one and is paced by a
per-host limiter shared across the driver's threads. Cached bodies live in
the `http_cache` table; Wikidata items and Wikipedia articles do not go
through here, because they are state invalidated by revision.
"""

import json
import threading
import time
from functools import partial
from typing import Any
from urllib.parse import urlsplit

from requests import Response, Session
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from peploop import db

USER_AGENT = (
    "peploop/0.1 (https://opensanctions.org; friedrich@opensanctions.org)"
)
HTTP_TIMEOUT = 90
CACHE_MAX_AGE = 7 * 24 * 3600
RETRY_STATUSES = [429, 500, 502, 503, 504]

# Requests per second per host. Reads are cheap; the point is that a
# many-threaded run does not get the IP throttled.
HOST_RATES = {
    "www.wikidata.org": 4.0,
    "wikipedia.org": 8.0,
    "petscan.wmcloud.org": 0.5,
}
DEFAULT_RATE = 2.0

_local = threading.local()
_buckets: dict[str, "_Pacer"] = {}
_buckets_lock = threading.Lock()


class _Pacer:
    """Hand out one slot every 1/rate seconds, to all threads together."""

    def __init__(self, rate: float) -> None:
        self.interval = 1.0 / rate
        self.next_at = 0.0
        self.lock = threading.Lock()

    def take(self) -> None:
        """Block until this host's next slot is due."""
        with self.lock:
            now = time.monotonic()
            wait = max(0.0, self.next_at - now)
            self.next_at = max(now, self.next_at) + self.interval
        if wait > 0:
            time.sleep(wait)


def _pacer(url: str) -> _Pacer:
    host = urlsplit(url).hostname or ""
    rate = HOST_RATES.get(host)
    if rate is None:
        suffix = ".".join(host.rsplit(".", 2)[-2:])
        rate = HOST_RATES.get(suffix, DEFAULT_RATE)
    with _buckets_lock:
        if host not in _buckets:
            _buckets[host] = _Pacer(rate)
        return _buckets[host]


def session() -> Session:
    """Return this thread's requests session, with retries and the UA set."""
    existing = getattr(_local, "session", None)
    if existing is not None:
        return existing
    sess = Session()
    sess.headers["User-Agent"] = USER_AGENT
    sess.request = partial(sess.request, timeout=HTTP_TIMEOUT)  # type: ignore[method-assign]
    retries = Retry(
        total=6,
        backoff_factor=2.0,
        backoff_max=120,
        status_forcelist=RETRY_STATUSES,
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retries)
    sess.mount("https://", adapter)
    sess.mount("http://", adapter)
    _local.session = sess
    return sess


def get(url: str, params: dict[str, Any] | None = None) -> Response:
    """GET a URL through the rate limiter, raising for an error status."""
    _pacer(url).take()
    res = session().get(url, params=params)
    res.raise_for_status()
    return res


def get_text(
    url: str, params: dict[str, Any] | None = None, max_age: int = CACHE_MAX_AGE
) -> str:
    """GET a URL as text, via `http_cache`. `max_age=0` skips the cache both ways."""
    cached = db.cache_get(url, params, max_age)
    if cached is not None:
        return cached
    text = get(url, params=params).text
    if max_age > 0:
        db.cache_put(url, params, text)
    return text


def get_json(
    url: str, params: dict[str, Any] | None = None, max_age: int = CACHE_MAX_AGE
) -> Any:
    """GET a URL and parse it as JSON, via `http_cache`."""
    return json.loads(get_text(url, params=params, max_age=max_age))
