"""Decide every answered slot: apply, or skip with the rule that said so.

An ordered table; the first rule that matches decides. There is no review
tier. Conservatism lives in the order: everything that can refuse comes
before the one rule that applies, and that rule demands a mechanical channel
agreeing with the model.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Callable


from peptree import signals, wd
from peptree.load import has, values

MIN_QUOTE = 4


@dataclass
class Slot:
    qid: str
    prop: str
    gap: str
    candidates: list[str]
    answer: dict[str, Any]
    message: str
    facts: signals.Facts | None
    load_rev: int | None
    live_rev: int | None
    live_entity: dict[str, Any] | None
    value: str | None = None
    channels: list[str] = field(default_factory=list)


ESCAPE = re.compile(r"\\(u[0-9a-fA-F]{4}|[nrt\"\\/])")
SIMPLE_ESCAPES = {"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\", "/": "/"}


def _unescape(text: str) -> str:
    """Undo JSON escapes a model wrote out literally ("\\u00c4kim" for "Äkim")."""
    def one(m: re.Match) -> str:
        code = m.group(1)
        return chr(int(code[1:], 16)) if code[0] == "u" and len(code) == 5 else SIMPLE_ESCAPES.get(code, m.group(0))
    return ESCAPE.sub(one, text)


def _norm(text: str) -> str:
    text = "".join(" " if unicodedata.category(ch) == "Cc" else ch for ch in text)
    return re.sub(r"\s+", " ", text).strip().lower()


def quoted(slot: Slot) -> bool:
    """The quote is non-trivial and appears verbatim in what the model was shown."""
    quote = _norm(_unescape(slot.answer.get("quote") or "")).strip("\"'«»„“”. ")
    return len(quote) >= MIN_QUOTE and quote in _norm(slot.message)


def era_mismatch(slot: Slot) -> bool:
    """A country or jurisdiction that did not exist while the office did."""
    return slot.prop in ("P17", "P1001") and slot.facts is not None and not signals.era_ok(slot.facts, slot.value)


def _in_range(slot: Slot) -> bool:
    c = slot.answer.get("choice")
    return isinstance(c, int) and 0 <= c < len(slot.candidates)


def _present_now(slot: Slot) -> bool:
    ent = slot.live_entity or {}
    if slot.gap == "classfix":
        return slot.value in values(ent, "P279", any_rank=True)
    if slot.prop == "P31":
        return bool(set(values(ent, "P31")) & {"Q4164871", "Q294414", "Q17279032"})
    return has(ent, slot.prop)


#: Channels strong enough to carry a P31. `state_office` is not: it reads only
#: the item's kind and a non-state label pattern, so it agrees with nearly any
#: "public office" answer.
STRONG_P31 = {"siblings", "category"}


def _strong_p31(slot: Slot) -> bool:
    return bool(STRONG_P31 & set(slot.channels))


#: (rule, predicate, disposition). First match wins.
RULES: list[tuple[str, Callable[[Slot], bool], str]] = [
    ("item_gone", lambda s: s.live_entity is None, "skip"),
    ("revision_moved", lambda s: s.live_rev != s.load_rev, "skip"),
    ("declined", lambda s: s.answer.get("choice") is None, "skip"),
    ("bad_index", lambda s: not _in_range(s), "skip"),
    ("present_now", _present_now, "skip"),
    ("low_confidence", lambda s: s.answer.get("confidence") not in ("high", "medium"), "skip"),
    ("no_quote", lambda s: not quoted(s), "skip"),
    ("era_mismatch", era_mismatch, "skip"),
    ("label_conflict", lambda s: signals.conflict(s.prop, s.value, s.facts), "skip"),
    ("p31_weak_channel", lambda s: s.prop == "P31" and not _strong_p31(s), "skip"),
    ("two_channels", lambda s: bool(s.channels), "apply"),
    ("one_channel", lambda s: True, "skip"),
]


def decide(slot: Slot) -> tuple[str, str]:
    if _in_range(slot):
        slot.value = slot.candidates[slot.answer["choice"]]
        if slot.facts is not None:
            slot.channels = signals.channels(slot.prop, slot.value, slot.facts)
    for name, pred, disposition in RULES:
        if pred(slot):
            return disposition, name
    raise AssertionError("the last rule always matches")


def source_of(answer: dict[str, Any]) -> str | None:
    """`article_<lang>` for an article quote (the language rides in `article`), else the source as given."""
    source = answer.get("source")
    if source == "article" and answer.get("article"):
        return f"article_{answer['article']}"
    return source


def run_rules(cc: str, reqs: list[dict[str, Any]], run: Any, log: Any = print) -> list[dict[str, Any]]:
    """Decide every slot of every answered request and store the decisions."""
    qids = [r["qid"] for r in reqs]
    live = wd.fetch_items(qids)  # max_age=0: what Wikidata holds now
    if hasattr(run, "spans_for"):  # when each candidate state or place existed, for the era rule
        run.spans_for([v for r in reqs for prop in ("P17", "P1001") for v in r["candidates"].get(prop, [])])
    out = []
    for r in reqs:
        answer = r.get("answer")
        if not answer:
            continue
        item = run.by_qid[r["qid"]]
        facts = run.facts(item)
        ent = live.get(r["qid"])
        for prop, cands in r["candidates"].items():
            gap, _cat = run.gaps[r["qid"]][prop]
            slot = Slot(qid=r["qid"], prop=prop, gap=gap, candidates=cands, answer=answer[prop],
                        message=r["message"], facts=facts, load_rev=item["lastrevid"],
                        live_rev=(ent or {}).get("lastrevid"), live_entity=ent)
            disposition, rule = decide(slot)
            out.append({"qid": r["qid"], "prop": prop, "gap": gap, "value": slot.value,
                        "disposition": disposition, "rule": rule, "channels": slot.channels,
                        "confidence": slot.answer.get("confidence"), "quote": slot.answer.get("quote"),
                        "source": source_of(slot.answer), "decline_reason": slot.answer.get("decline_reason"),
                        "key": r["key"], "articles": dict(r.get("articles") or [])})
    con = wd.conn()
    with con.transaction():
        con.execute("DELETE FROM ptree_decision WHERE country = %s", (cc,))
        with con.cursor() as cur:
            cur.executemany(
                "INSERT INTO ptree_decision (country, qid, prop, value, disposition, rule, channels, confidence,"
                " evidence, source, call_key) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                [(cc, d["qid"], d["prop"], d["value"], d["disposition"], d["rule"], d["channels"], d["confidence"],
                  d["quote"], d["source"], d["key"]) for d in out])
    return out
