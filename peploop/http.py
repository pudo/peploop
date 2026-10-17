"""Fetch things over HTTP, politely and with a cache.

Wikimedia 403s the default requests User-Agent and throttles anonymous
clients, so every request carries a descriptive one and is paced by a
per-host limiter shared across the driver's threads. Cached bodies live in
the `http_cache` table; Wikidata items and Wikipedia articles do not go
through here, because they are state invalidated by revision.
"""

import fcntl
import json
import threading
import time
from pathlib import Path
from functools import partial
from typing import Any
from urllib.parse import urlsplit

import requests
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
    "petscan.wmcloud.org": 0.5,
    # The query service is a shared analytics cluster, not an API: one at a
    # time. Named in full because the suffix fallback below would not find it
    # — only `www.wikidata.org` is a key, `wikidata.org` is not.
    "query.wikidata.org": 1.0,
    "qlever.dev": 1.0,
}
DEFAULT_RATE = 2.0
#: Wikimedia's API limit is per IP across every wiki, not per host: a fetch
#: reading five languages at 8/s each plus Wikidata at 4/s was answered 429 on
#: every request, and probing it sustained 4/s in total and tripped at 8/s.
#: So the wikis and Wikidata's API share one pacer; the query service keeps
#: its own, being a different cluster with its own limit.
WIKIMEDIA_RATE = 4.0
WIKIMEDIA_SUFFIXES = ("wikipedia.org", "www.wikidata.org")
#: Where processes on this machine share the Wikimedia pacer: the limit is the
#: IP's, so several runs at once must split one rate, not each take it whole.
SHARED_PACER = Path(__file__).resolve().parents[1] / "data" / ".wikimedia-pacer"

#: How often, and how patiently, a GET whose body was cut off is sent again.
BODY_RETRIES = 3
BODY_BACKOFF = 10.0

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


class _SharedPacer(_Pacer):
    """A pacer whose next slot lives in a locked file, so every process on the machine draws from it."""

    def __init__(self, rate: float, path: Path) -> None:
        super().__init__(rate)
        self.path = path

    def take(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock, open(self.path, "a+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.seek(0)
            try:
                next_at = float(f.read() or 0)
            except ValueError:
                next_at = 0.0
            now = time.time()
            wait = max(0.0, next_at - now)
            f.seek(0)
            f.truncate()
            f.write(repr(max(now, next_at) + self.interval))
            f.flush()
            fcntl.flock(f, fcntl.LOCK_UN)
        if wait > 0:
            time.sleep(wait)


def _bucket(host: str) -> tuple[str, float]:
    """Name the pacer a host draws from, and that pacer's rate."""
    if host in HOST_RATES:
        return host, HOST_RATES[host]
    if host.endswith(WIKIMEDIA_SUFFIXES):
        return "wikimedia", WIKIMEDIA_RATE
    suffix = ".".join(host.rsplit(".", 2)[-2:])
    return host, HOST_RATES.get(suffix, DEFAULT_RATE)


def _pacer(url: str) -> _Pacer:
    key, rate = _bucket(urlsplit(url).hostname or "")
    with _buckets_lock:
        if key not in _buckets:
            _buckets[key] = _SharedPacer(rate, SHARED_PACER) if key == "wikimedia" else _Pacer(rate)
        return _buckets[key]


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


def get(
    url: str, params: dict[str, Any] | None = None, timeout: int | None = None
) -> Response:
    """GET a URL through the rate limiter, raising for an error status.

    `timeout` overrides the session default for one request. A SPARQL query
    that groups over a whole country legitimately runs longer than any API
    call does, so the endpoint that needs it asks for it rather than the
    whole session waiting that long for a 404.
    """
    kwargs: dict[str, Any] = {} if timeout is None else {"timeout": timeout}
    for attempt in range(BODY_RETRIES + 1):
        _pacer(url).take()
        try:
            res = session().get(url, params=params, **kwargs)
            break
        # A body the server stops sending part way arrives after the status
        # line, where the adapter's retry policy no longer looks; the query
        # service does this often enough to kill an hours-long verify pass.
        except requests.exceptions.ChunkedEncodingError:
            if attempt == BODY_RETRIES:
                raise
            time.sleep(BODY_BACKOFF * (attempt + 1))
    res.raise_for_status()
    return res


def get_text(
    url: str,
    params: dict[str, Any] | None = None,
    max_age: int = CACHE_MAX_AGE,
    timeout: int | None = None,
) -> str:
    """GET a URL as text, via `http_cache`. `max_age=0` skips the cache both ways."""
    cached = db.cache_get(url, params, max_age)
    if cached is not None:
        return cached
    text = get(url, params=params, timeout=timeout).text
    if max_age > 0:
        db.cache_put(url, params, text)
    return text


def get_json(
    url: str,
    params: dict[str, Any] | None = None,
    max_age: int = CACHE_MAX_AGE,
    timeout: int | None = None,
) -> Any:
    """GET a URL and parse it as JSON, via `http_cache`."""
    return json.loads(get_text(url, params=params, max_age=max_age, timeout=timeout))
