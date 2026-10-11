"""Submit V1 batches to QuickStatements 3.0 and read them back.

How peptree and peploop write to Wikidata: QS3 runs a batch server-side under
the user's account and groups its edits in EditGroups. Callers go through
`send.py`, which records every batch in the ledger before the request.

What QS3 does, measured on the sandbox item:

- A plain line merges into the *first* statement with an exactly equal value
  (a date at the same precision too); re-sending a qualifier or reference it
  already has changes nothing, so a plain line is safe to submit twice.
- A `+` line always creates a statement, and duplicates on a re-run: the
  caller's ledger must never send one twice.
- `SWITCH_VALUE` changes a value in place by exact match and keeps the GUID.
- `-Q|P|value` removes only the first statement with the value; remove by
  `-STATEMENT|GUID` only.
- `combine_commands` folds an item's consecutive lines into one edit, and one
  bad command then fails them all.
- A failed command reports status -1 and its raw line, never the reason: the
  reason is on the web report, which a token cannot read.
- There is no preview step and no maxlag handling (it backs off on HTTP 429
  only). The `wikibase` field of a submit is left out: its validator rejects
  any unblocked user.

    QS3_TOKEN  the API token from https://qs-dev.toolforge.org/auth/profile/
"""

import os
import re
import time
from typing import Any, Callable

from peploop import http

BASE = "https://qs-dev.toolforge.org"
API = f"{BASE}/api/v1"
EDITGROUPS = "https://editgroups.toolforge.org/b/QSv3/{}/"
#: Batch status codes, per the QS3 API.
DONE, BLOCKED, STOPPED = 3, -1, -2
FINISHED = (DONE, BLOCKED, STOPPED)
#: Command status for an error, and for one done (read off batch 59094).
ERROR = -1
COMMAND_DONE = 2


def _headers() -> dict[str, str]:
    token = os.environ.get("QS3_TOKEN")
    if not token:
        raise RuntimeError("QS3_TOKEN is not set")
    return {"Authorization": f"Token {token}"}


def _get(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    res = http.session().get(url, params=params, headers=_headers())
    res.raise_for_status()
    return res.json()


def submit(lines: list[str], name: str, combine: bool = True) -> int:
    """Start a batch; returns its id. Runs at once: the API has no preview step.

    `combine` folds consecutive commands on one item into one edit, so lines
    should arrive grouped by item.
    """
    body: dict[str, Any] = {"name": name, "v1": "\n".join(lines), "combine_commands": combine}
    res = http.session().post(f"{API}/batches/", json=body, headers=_headers())
    if res.status_code != 201:
        raise RuntimeError(f"QS3 refused the batch: HTTP {res.status_code} {res.text[:300]}")
    found = re.search(r"/batches/(\d+)/", res.json().get("url", ""))
    if found is None:
        raise RuntimeError(f"QS3 answered without a batch url: {res.text[:300]}")
    return int(found.group(1))


def info(batch: int) -> dict[str, Any]:
    """The batch row: `status.code`, `summary` counts by command status, `message`."""
    return _get(f"{API}/batches/{batch}/")


def wait(batch: int, log: Callable[[str], None] = print, every: float = 10.0) -> dict[str, Any]:
    """Poll until the batch has finished, logging progress when it moves."""
    last = None
    while True:
        row = info(batch)
        counts = row.get("summary") or {}
        seen = (counts.get("done_commands"), counts.get("error_commands"))
        if seen != last:
            log(f"QS3 batch {batch}: {row['status']['display']}, {seen[0]} done, {seen[1]} errors "
                f"of {counts.get('total_commands')}")
            last = seen
        if row["status"]["code"] in FINISHED:
            return row
        time.sleep(every)


def failed(batch: int) -> list[str]:
    """The raw lines of the batch's failed commands."""
    out: list[int] = []
    url: str | None = f"{API}/batches/{batch}/commands/"
    while url:
        page = _get(url)
        out += [c["pk"] for c in page["commands"] if c["status"] == ERROR]
        url = (page.get("links") or {}).get("next")
    return [_get(f"{API}/commands/{pk}")["raw"] for pk in out]


def commands(batch: int) -> list[dict[str, Any]]:
    """Every command of a batch in line order: `index`, `status`, and `response_id`.

    `response_id` is the entity a command acted on, so for a `CREATE` it is the
    new item's QID: how a creation is read back without searching the edit log.
    """
    out: list[dict[str, Any]] = []
    url: str | None = f"{API}/batches/{batch}/commands/"
    while url:
        page = _get(url)
        out += [{"index": c["index"], "status": c["status"], "response_id": c.get("response_id")}
                for c in page["commands"]]
        url = (page.get("links") or {}).get("next")
    return sorted(out, key=lambda c: c["index"])


def find(name: str, username: str, pages: int = 3) -> int | None:
    """The id of the user's most recent batch with this exact name, among the newest few pages."""
    url: str | None = f"{API}/batches/"
    params: dict[str, Any] | None = {"username": username}
    for _ in range(pages):
        if url is None:
            break
        page = _get(url, params)
        for row in page.get("batches", []):
            if row.get("name") == name:
                return int(row["pk"])
        url, params = (page.get("links") or {}).get("next"), None
    return None


def link(batch: int) -> str:
    return f"{BASE}/batch/{batch}/"
