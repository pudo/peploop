"""The only place this workbench writes to Wikidata.

Most statements go out as QuickStatements files the user runs, which are
mass-revertable and show up in EditGroups. Two kinds cannot, and both are
written here instead, one atomic `wb` call each:

* **Position items.** A QuickStatements `CREATE` gives no way to reference the
  new item as a statement value in the same batch, so every holder waiting on a
  new office would need a second batch after a human read back the QID. That
  round trip is the stall this project exists to remove.
* **A person's several tenures in one office.** QuickStatements matches an
  incoming line on subject, property and value alone, so two lines for two
  spells become *one* statement carrying both starts and both ends, with nothing
  to say which start goes with which end (`wd.validate.collapsing_groups`
  finds them; the damage is live on Wikidata from the Ecuador batch). The API
  has no such behaviour: each claim listed is created.

Three properties are non-negotiable, because both of these are the least
reversible things here — undoing a creation takes a deletion or a merge, and
undoing a duplicated claim takes a statement removal, all reserved for a human:

* **A ledger.** QuickStatements de-duplicates statements but nothing
  de-duplicates a creation, and — the reason the claims path needs one just as
  much — nothing de-duplicates an API claim either, so re-running would write a
  second copy of every tenure. `data/<campaign>/created.json` and
  `claims_written.json` map a stable ref to what was written.
* **Dry by default.** Nothing is written unless the caller asks twice, once by
  passing `apply=True` and once by having a spec that cleared `create.guard`.
* **An edit log.** Every write appends to `data/<campaign>/applied.jsonl` with
  the payload sent and the QID returned, so a bad run can be undone by hand.
"""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

#: Be polite on writes: pause when the lag climbs. Wikidata asks bots for 5, and
#: on a write this covers the **query-service updaters**, not just database
#: replication — so `action=query&siprop=dbrepllag` reporting 0.9s says nothing
#: about whether a write will be accepted. A lagged updater rejects the edit and
#: `wikibase-edit` retries with backoff; the answer is to wait, not to raise this
#: number, which would mean adding load while the site is already behind.
MAXLAG = 5
#: Writes need far longer than reads, because a maxlag rejection is answered by
#: retrying rather than failing: one Kuwait edit sat through "Waiting for
#: wdqs1013: 27.3 seconds lagged" for over four minutes. The old 120s default
#: read as a hang.
WRITE_TIMEOUT = 420


class WriteError(RuntimeError):
    pass


@dataclass
class Ledger:
    """What this campaign has already created, keyed by a stable ref."""

    path: Path
    entries: Dict[str, dict]

    @staticmethod
    def load(path: Path) -> "Ledger":
        entries = json.loads(path.read_text()) if path.exists() else {}
        return Ledger(path=path, entries=entries)

    def qid(self, ref: str) -> Optional[str]:
        entry = self.entries.get(ref)
        return entry.get("qid") if entry else None

    def record(self, ref: str, qid: str, payload: dict) -> None:
        self.entries[ref] = {"qid": qid, "payload": payload}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.entries, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        )


def _run(args: list, timeout: int = WRITE_TIMEOUT) -> str:
    """Run one `wb` command, and never swallow why it failed.

    The stderr relay is not decoration. `wikibase-edit` reports a maxlag
    rejection there — "Waiting for wdqs1013: 27.3 seconds lagged, retrying in
    5s" — and captured-then-discarded that message turned a perfectly clear
    diagnosis into three rounds of guessing at credentials and the network. A
    timeout is the case that most needs the explanation, so it is the case that
    reports it.
    """
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout,
            check=False, stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired as exc:
        detail = (exc.stderr or exc.stdout or b"")
        if isinstance(detail, bytes):
            detail = detail.decode("utf-8", "replace")
        raise WriteError(
            f"{' '.join(args[:2])} timed out after {timeout}s. Last output: "
            f"{detail.strip()[-400:] or '(nothing — the process wrote nothing at all)'}"
        ) from exc
    if result.stderr and result.stderr.strip():
        # Warnings on a *successful* write matter too: a retried maxlag edit
        # succeeds while telling you the site is struggling.
        print(result.stderr.strip()[-600:])
    if result.returncode != 0:
        raise WriteError(
            f"{' '.join(args[:2])} failed ({result.returncode}): "
            f"{(result.stderr or result.stdout).strip()[:400]}"
        )
    return result.stdout


def create_entity(
    payload: dict, summary: str, ledger: Ledger, ref: str, apply: bool = False
) -> Optional[str]:
    """Create one item, or report what would be created.

    Returns the QID — the recorded one when the ledger has already seen this
    ref, so a re-run fills in statements against the existing item instead of
    minting a second.
    """
    existing = ledger.qid(ref)
    if existing:
        return existing

    args = [
        "wb", "create-entity", json.dumps(payload, ensure_ascii=False),
        "--summary", summary, "--maxlag", str(MAXLAG),
    ]
    if not apply:
        _run(args + ["--dry"])
        return None

    output = _run(args)
    qid = _first_qid(output)
    if not qid:
        raise WriteError(f"no QID in wb output: {output.strip()[:200]}")
    ledger.record(ref, qid, payload)
    return qid


def edit_entity(
    payload: dict, summary: str, ledger: Ledger, ref: str, apply: bool = False
) -> bool:
    """Add claims to an existing item, or report what would be added.

    Reach for this for the statements QuickStatements cannot express — today
    that means a person's several tenures in one office, which QS folds into a
    single statement with every date on it. `payload` is a wikibase-edit entity
    blob (`{"id": …, "claims": {…}}`), so all of one person's tenures go in one
    atomic edit and either all land or none do.

    Returns whether anything was written. The ledger is what makes a re-run
    safe: unlike QuickStatements, the API creates every claim it is given, so
    without it a second run silently doubles each tenure.
    """
    if ledger.qid(ref):
        return False

    args = [
        "wb", "edit-entity", json.dumps(payload, ensure_ascii=False),
        "--summary", summary, "--maxlag", str(MAXLAG),
    ]
    if not apply:
        _run(args + ["--dry"])
        return False

    output = _run(args)
    ledger.record(ref, payload["id"], {"payload": payload, "response": output[:400]})
    return True


def _first_qid(output: str) -> Optional[str]:
    """The created item's id, wherever `wb` chose to put it in its output."""
    try:
        data = json.loads(output)
    except ValueError:
        for token in output.split():
            cleaned = token.strip("\"',{}[]:")
            if cleaned.startswith("Q") and cleaned[1:].isdigit():
                return cleaned
        return None
    if isinstance(data, dict):
        for key in ("id", "entity", "qid"):
            value = data.get(key)
            if isinstance(value, str) and value.startswith("Q"):
                return value
            if isinstance(value, dict) and isinstance(value.get("id"), str):
                return value["id"]
    return None


def log(path: Path, entry: dict) -> None:
    """Append one write to the campaign's edit log."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
