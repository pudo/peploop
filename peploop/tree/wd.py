"""The label languages of one country's run, and the readers peptree's modules share.

Live state (the items being repaired, their holders) goes through
`peploop.wikidata`, which never caches; slow-moving context goes through
`peploop.memo`, and type closures through `peploop.typegraph`. What is peptree's
own here is the language order: a run labels in its country's languages.
"""

import json
from pathlib import Path
from typing import Any, Iterable, Sequence

from peploop import db as pdb
from peploop import memo
from peploop.wikidata import (  # noqa: F401  (re-exported for peptree modules)
    best_label, claim_qids, fetch_items, sparql, values_block, values_chunks,
)

SCHEMA = Path(__file__).resolve().parent / "schema.sql"
DAY = memo.DAY

#: Label languages, best first. English and `mul` until a country is chosen;
#: `country.get` puts the country's own languages between them.
LANGS: tuple[str, ...] = ("en", "mul")


def set_langs(langs: Sequence[str]) -> None:
    """Make `langs` the label languages for this process (one country per run)."""
    global LANGS
    LANGS = tuple(dict.fromkeys(langs))


def conn():
    return pdb.conn()


_ready = False


def init() -> None:
    """Create the `ptree_` tables if they are missing, and peploop's (the send ledger and caches among them)."""
    global _ready
    if not _ready:
        pdb.init_schema()
        conn().execute(SCHEMA.read_text())
        _ready = True


def label(entity: dict[str, Any]) -> str:
    return best_label(entity, LANGS) or ""


def labels_of(qids: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Labels in this run's languages and the English description, kept a month."""
    return memo.labels_of(qids, LANGS)


def name(info: dict[str, Any] | None) -> str:
    if not info:
        return ""
    labels = info.get("labels", {})
    for lg in LANGS:
        if lg in labels:
            return labels[lg]
    return next(iter(labels.values()), "")


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)
