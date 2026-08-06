"""The only place this workbench writes to Wikidata.

Statements go out as QuickStatements files the user runs, which are
mass-revertable and show up in EditGroups. Position *items* cannot: a
QuickStatements `CREATE` gives no way to reference the new item as a statement
value in the same batch, so every holder waiting on a new office would need a
second batch after a human read back the QID. That round trip is the stall this
project exists to remove, so items are created here, one atomic
`wb create-entity` call each.

Three properties are non-negotiable, because creation is the least reversible
thing here — undoing it takes a deletion or a merge, both reserved for a human:

* **A ledger.** QuickStatements de-duplicates statements but nothing
  de-duplicates a creation, so a second run must recognise what the first one
  made. `data/<campaign>/created.json` maps a stable ref to the QID.
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

#: Be polite on writes: pause when the replication lag climbs.
MAXLAG = 5


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


def _run(args: list, timeout: int = 120) -> str:
    result = subprocess.run(
        args, capture_output=True, text=True, timeout=timeout, check=False
    )
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
