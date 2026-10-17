"""The readers pepcorp's modules share, and its tables.

Live state (the enterprises, their leadership) goes through `peploop.wikidata`,
which never caches; QLever answers the one discovery query the query service
cannot (every ownership pair of a country), and type closures go through
`peploop.typegraph`.
"""

import json
from pathlib import Path
from typing import Any

from peploop import db as pdb
from peploop.wikidata import (  # noqa: F401  (re-exported for pepcorp modules)
    best_label, bisect, claim_qids, fetch_items, qlever, sparql, values_block, values_chunks,
)

SCHEMA = Path(__file__).resolve().parent / "schema.sql"


def conn():
    return pdb.conn()


_ready = False


def init() -> None:
    """Create the `pcorp_` tables if they are missing, and peploop's (the send ledger and article store among them)."""
    global _ready
    if not _ready:
        pdb.init_schema()
        conn().execute(SCHEMA.read_text())
        _ready = True


def values(entity: dict[str, Any], prop: str) -> list[str]:
    """The item values of a property at any rank but deprecated."""
    return claim_qids(entity, prop, include_deprecated=False)


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)
