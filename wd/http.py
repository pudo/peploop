"""HTTP plumbing shared by all workbench scripts.

Wikimedia 403s the default requests User-Agent and throttles anonymous
clients, so every request goes through a session with a descriptive UA and
Retry-After-honouring retries. Responses are cached as JSON files under
data/cache/ so iterating on a script doesn't re-hit the APIs.
"""

import hashlib
import json
import time
from functools import partial
from pathlib import Path
from typing import Any, Dict, Optional

from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

USER_AGENT = (
    "opensanctions-workbench/0.1 "
    "(https://opensanctions.org; friedrich@opensanctions.org)"
)
HTTP_TIMEOUT = 90
RETRY_STATUSES = [500, 502, 504, 429, 503]

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / "data" / "cache"
CACHE_MAX_AGE = 7 * 24 * 3600  # seconds


def make_session(timeout: int = HTTP_TIMEOUT) -> Session:
    session = Session()
    session.headers["User-Agent"] = USER_AGENT
    session.request = partial(session.request, timeout=timeout)  # type: ignore
    # Six attempts over ~2 minutes, not three over seven seconds. A run's
    # setup makes fifteen-odd sequential WDQS calls at `max_age=0` — the
    # gazetteer, its type closure, its holder counts, each qualifier set — and
    # a single one of them failing kills the run *before* it reaches anything
    # the verdict ledger protects. Three Czech runs died that way, two of them
    # after spending nothing, while the network flapped for minutes at a time:
    # `1, 2, 4` seconds of backoff never outlasts that, `2, 4, 8, 16, 32, 64`
    # does. `total` covers connect errors too, which is what a DNS failure
    # arrives as.
    retries = Retry(
        total=6,
        backoff_factor=2.0,
        backoff_max=120,
        status_forcelist=RETRY_STATUSES,
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _cache_path(url: str, params: Optional[Dict[str, Any]]) -> Path:
    key = url + "?" + json.dumps(params or {}, sort_keys=True)
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{digest}.json"


def drop_cache(url: str, params: Optional[Dict[str, Any]] = None) -> None:
    """Remove a cached response, e.g. after discovering it holds a non-JSON
    error body a 200-status upstream timeout smuggled past raise_for_status."""
    _cache_path(url, params).unlink(missing_ok=True)


def get_text(
    session: Session,
    url: str,
    params: Optional[Dict[str, Any]] = None,
    max_age: int = CACHE_MAX_AGE,
) -> str:
    """GET a URL with disk caching. Pass max_age=0 to bypass the cache."""
    path = _cache_path(url, params)
    if max_age > 0 and path.exists():
        record = json.loads(path.read_text())
        if time.time() - record["fetched_at"] < max_age:
            return record["text"]
    res = session.get(url, params=params)
    res.raise_for_status()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    record = {"url": res.url, "fetched_at": time.time(), "text": res.text}
    path.write_text(json.dumps(record))
    return res.text
