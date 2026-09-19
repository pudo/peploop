"""Decide which Wikidata position item an office name refers to.

Reach for this when a source names an office in prose and the run needs the
item behind it — the enrichment loop's placement lane, and any campaign asking
"does this office already exist, or must it be created?".

The pass exists because name overlap cannot answer the question. Ranked by
words alone, "Minister of Family, Labour and Social Policy" and `Q25919989`
*Minister of Family and Social Policy* look exactly like "Mayor of Chełm" and
`Q177529` *mayor*: a candidate carrying a subset of the query's words. The
first pair is one office renamed and the second is a specific seat against the
occupation class every mayor belongs to. Separating them needs the item's own
description, kind, polity and holder count, which is what the shortlist shows.

Three stages, and the middle one is cheap:

1. `wd/positions.py:OfficeIndex` retrieves, tuned for recall — measured on
   Poland's 71 queued offices, it surfaced a covering match for the two that
   really existed and something for all 71, so a mechanical top-1 would have
   been wrong 69 times.
2. `wd/gazetteer.py:describe` fully describes only the shortlist.
3. This module's prompt (`prompts/office_rerank.md`) chooses one, or refuses.

The verdict is one channel. `gate` is the other, and it is the same two-signal
rule the rest of the workbench uses: a chosen item must name the polity it
governs, or the choice is recorded and not applied.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from requests import Session

from wd.api import claim_qids, fetch_entities
from wd.gazetteer import Entry, describe
from wd.positions import Hit, OfficeIndex
from wd.verdicts import EFFORT, MODEL, Ledger, Usage, classify

#: How many candidates the model sees. Wide enough that recall is retrieval's
#: problem and not the shortlist's, small enough that every candidate can be
#: rendered in full — the whole point is that the model reads the *item*.
SHORTLIST = 12

#: Verdict kinds. Only the first two are matches; the rest name a way the
#: shortlist tried to mislead, and each one is a real case from Poland's run.
MATCH_KINDS = ("same-office", "renamed")
KINDS = MATCH_KINDS + ("generic-class", "body-not-seat", "wrong-office", "none")

RERANK_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        #: Echoed back so `classify` can verify the batch it got answers for.
        "office": {"type": "string"},
        "qid": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "kind": {"type": "string", "enum": list(KINDS)},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "reason": {"type": "string"},
    },
    "required": ["office", "qid", "kind", "confidence", "reason"],
    "additionalProperties": False,
}


@dataclass
class Mention:
    """An office name as some source wrote it, with what attests to it."""

    name: str
    #: Query expansion from the pass that read the person — the native
    #: spelling, the bare proper noun, the kind on its own. See
    #: `prompts/person_enrichment.md`.
    terms: List[str] = field(default_factory=list)
    #: `{qid, start, end, quote}` per attested holder. The dates rule out a
    #: predecessor whose `exists:` span closed before the tenure began.
    holders: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class Placement:
    """What the two channels made of one office name."""

    office: str
    #: The item, or None. Set only when the model matched *and* the gate agreed.
    qid: Optional[str] = None
    kind: str = "none"
    confidence: str = "low"
    reason: str = ""
    #: Every QID the model was shown, so a wrong answer can be re-read against
    #: what it actually saw rather than against what we assume it saw.
    shortlist: List[str] = field(default_factory=list)
    #: The model's pick, kept even when the gate refused it.
    chosen: Optional[str] = None
    #: Why the gate refused, if it did.
    veto: Optional[str] = None

    @property
    def placed(self) -> bool:
        return self.qid is not None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "office": self.office, "qid": self.qid, "kind": self.kind,
            "confidence": self.confidence, "reason": self.reason,
            "shortlist": list(self.shortlist), "chosen": self.chosen,
            "veto": self.veto,
        }


def shortlist_for(
    index: OfficeIndex, mention: Mention, limit: int = SHORTLIST
) -> List[Hit]:
    """The candidates one office name retrieves, name and search terms both."""
    from wd.enrich import name_variants          # circular at import time only

    primary, extras = name_variants(mention.name)
    queries = [primary, *extras, mention.name, *mention.terms]
    return index.search([q for q in queries if q and q.strip()], limit=limit)


def render_candidates(hits: Sequence[Hit], entries: Dict[str, Entry]) -> str:
    """The shortlist as the model sees it: the whole item, one per line."""
    lines = []
    for hit in hits:
        entry = entries.get(hit.qid)
        line = entry.line() if entry else f"{hit.qid} | {hit.name}"
        lines.append(f"- {line}  [matched on: {hit.name}]")
    return "\n".join(lines) or "- (nothing retrieved)"


def render_mention(
    mention: Mention, hits: Sequence[Hit], entries: Dict[str, Entry]
) -> str:
    """One office name and its evidence, as the pass's user turn."""
    parts = [f"# Office as written\n\n{mention.name}\n"]
    if mention.terms:
        parts.append("Search terms the reader's pass proposed: "
                     + ", ".join(mention.terms) + "\n")
    if mention.holders:
        parts.append("# Attested holders\n")
        for holder in mention.holders:
            span = "–".join(
                [holder.get("start") or "", holder.get("end") or ""]
            ).strip("–") or "no dates"
            parts.append(f"- {holder.get('qid')} · {span}\n"
                         f"  “{holder.get('quote', '')}”")
        parts.append("")
    parts.append("# Candidate position items\n")
    parts.append(render_candidates(hits, entries))
    parts.append("\nWhich of these is the office named above? Answer `none` "
                 "rather than the closest one.")
    return "\n".join(parts)


def settle(
    kind: str, chosen: Optional[str], shortlist: Sequence[str],
    polity_veto: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Turn one rerank verdict into an applied QID, or a recorded refusal.

    The two-signal rule, in one pure place so it can be pinned offline. Returns
    `(qid, veto)` — `qid` is set only when nothing objected.

    Three ways a verdict does not become a statement, and each has cost
    something somewhere in this workbench:

    * the verdict is not a **match** — `generic-class`, `body-not-seat`,
      `wrong-office` and `none` all mean no item exists *for this office*,
      however close the nearest candidate came;
    * the pick was **not on the shortlist** it was shown, which is a QID the
      model produced from somewhere else and the one thing the closed-set
      design exists to forbid;
    * the item **names no polity it governs**, the `Q98637505 wójt` refusal.
    """
    if kind not in MATCH_KINDS:
        return None, None
    if not chosen:
        return None, "match-without-qid"
    if chosen not in set(shortlist):
        return None, "off-shortlist"
    if polity_veto:
        return None, polity_veto
    return chosen, None


def gate(session: Session, qid: str) -> Optional[str]:
    """The second signal: does the item name the polity it governs?

    An office scoped to no polity is a defect by `recipes/position_items.md`,
    and it is how a *generic* class passes a country check — `Q98637505 wójt`
    carries `P17` Poland and no `P1001` at all, so "is this Polish" says yes
    about the administrative rank as readily as about a village mayoralty.
    Returns the refusal reason, or None when the item passes.
    """
    entity = fetch_entities(session, [qid], props="claims", max_age=0).get(qid)
    if not entity:
        return "no-entity"
    if not claim_qids(entity, "P1001"):
        return "no-polity"
    return None


def place_offices(
    session: Session,
    index: OfficeIndex,
    mentions: Sequence[Mention],
    *,
    prompt: str,
    ledger_path: Path,
    limit: int = SHORTLIST,
    model: str = MODEL,
    effort: str = EFFORT,
    workers: int = 6,
    usage: Optional[Usage] = None,
    log: Any = print,
) -> Dict[str, Placement]:
    """Place every named office, one request each, resumable.

    Keyed by office name and not by person: a category's members hold the same
    handful of other offices between them, and Poland's 106 people named 67
    offices. The ledger means a re-run costs only the names that are new.
    """
    hits = {m.name: shortlist_for(index, m, limit) for m in mentions}
    wanted = sorted({h.qid for hs in hits.values() for h in hs})
    log(f"shortlists: {len(mentions)} offices, {len(wanted)} distinct candidates")
    entries = {e.qid: e for e in describe(session, wanted)} if wanted else {}

    ledger = Ledger(ledger_path, key="office").load()
    if ledger.stale_for(prompt):
        log(f"! {ledger_path.name} was judged under a different prompt; those "
            "rows will not be re-asked — move the file aside to re-judge.")
    by_name = {m.name: m for m in mentions}
    classify(
        [{"office": m.name} for m in mentions],
        prompt=prompt,
        item_schema=RERANK_SCHEMA,
        ledger=ledger,
        render=lambda batch: render_mention(
            by_name[batch[0]["office"]], hits[batch[0]["office"]], entries
        ),
        batch_size=1,          # one office per request; see the prompt's close
        workers=workers,
        model=model,
        effort=effort,
        usage=usage,
        log=log,
    )

    out: Dict[str, Placement] = {}
    for line in ledger_path.read_text().splitlines() if ledger_path.exists() else []:
        if not line.strip():
            continue
        row = json.loads(line)
        name = row.get("office")
        if name not in by_name:
            continue
        placement = Placement(
            office=name,
            kind=row.get("kind") or "none",
            confidence=row.get("confidence") or "low",
            reason=row.get("reason") or "",
            shortlist=[h.qid for h in hits.get(name, ())],
            chosen=row.get("qid"),
        )
        # The polity check costs a request, so only ask for a pick that has
        # already survived the offline half of `settle`.
        polity_veto = None
        if (placement.kind in MATCH_KINDS and placement.chosen
                and placement.chosen in set(placement.shortlist)):
            polity_veto = gate(session, placement.chosen)
        placement.qid, placement.veto = settle(
            placement.kind, placement.chosen, placement.shortlist, polity_veto
        )
        out[name] = placement
    return out
