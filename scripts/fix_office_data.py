#!/usr/bin/env python
"""Plan, and on request make, four office-data fixes found during peploop runs.

    .venv/bin/python scripts/fix_office_data.py            # dry, the default
    .venv/bin/python scripts/fix_office_data.py --apply    # HUMAN GATE

Each fix is a planner that reads its items live (no cache) and returns only the
edits whose result is not already on Wikidata, so a run after `--apply` plans
nothing. `--apply` makes one edit, re-reads, and re-plans, which keeps every
edit against the state it was planned from (`--baserevid`) and lets the one
removal wait for the statement replacing it.

1. Burundi's `P150` still lists the provinces dissolved by the 2025 reform as
   if current: end each with `P582` from the province's own `P576`, and add the
   five new provinces once their items say they are current provinces.
2. The Prime Minister of Burundi carries only its 1998 `P576`, though the office
   was restored in 2020: add a second `P571`, which is how restored offices are
   modelled (plain normal-rank values; no rank change).
3. Belarus's Constitutional Court judge office has no `P31`.
4. Belarus's KGB chair has a person as `P1001`: add the state, then remove the
   person-valued statement (the one destructive edit, flagged as such).
"""

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.http import make_session  # noqa: E402

USER_AGENT = "opensanctions-workbench/0.1 (friedrich@opensanctions.org)"
API = "https://www.wikidata.org/w/api.php"
WDQS = "https://query.wikidata.org/sparql"
MAXLAG = 5
WRITE_TIMEOUT = 420
TODAY = date.today().isoformat()

# Fix 1 ---------------------------------------------------------------------
BURUNDI = "Q967"
NEW_PROVINCES = ["Q131844468", "Q15478219", "Q131844612", "Q131844755"]
PROVINCE_CLASSES = {"Q476075", "Q34876"}  # province of Burundi; province
GITEGA = "Q720843"  # kept its name and P150 statement through the reform
RUMONGE = "Q20669646"  # dissolved in 2025 but not in P150: reported only
REFORM_URL = (
    "https://www.burunditimes.com/"
    "burundis-new-governors-sworn-in-following-major-provincial-reforms/"
)
REFORM_QUOTE = (
    "Burundi’s five newly appointed provincial governors officially took "
    "office Friday, completing a sweeping administrative overhaul that reduced "
    "the country’s provinces from 18 to 5."
)

# Fix 2 ---------------------------------------------------------------------
BURUNDI_PM = "Q52728003"
PM_RESTORED = "2020"
PM_URL = (
    "https://www.aa.com.tr/en/africa/"
    "burundi-gets-new-prime-minister-after-22-years/1887807"
)
PM_QUOTE = (
    "The office of the prime minister was abolished in 1998, and reinstated in "
    "2020 with the appointment of Bunyoni."
)

# Fix 3 ---------------------------------------------------------------------
BELARUS = "Q184"
BY_JUDGE = "Q122831383"
#: Belarus's other court offices, read for the judge class they use.
BY_COURT_SIBLINGS = ["Q122920176", "Q141627785"]
JUDGE = "Q16533"

# Fix 4 ---------------------------------------------------------------------
BY_KGB_CHAIR = "Q4436588"
HUMAN = "Q5"


@dataclass
class Edit:
    """One `wb` call and why."""

    args: List[str]
    reason: str
    qids: List[str] = field(default_factory=list)
    destructive: bool = False
    #: A removal waits until the statement replacing it is live.
    blocked: Optional[str] = None


class Reader:
    """Live reads only: every call goes to the API, nothing is cached."""

    def __init__(self) -> None:
        self.session = make_session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.labels: Dict[str, str] = {}

    def entity(self, qid: str) -> Dict[str, Any]:
        return self.entities([qid])[qid]

    def entities(self, qids: Iterable[str]) -> Dict[str, Any]:
        qids = list(dict.fromkeys(qids))
        out: Dict[str, Any] = {}
        for i in range(0, len(qids), 50):
            resp = self.session.get(API, params={
                "action": "wbgetentities", "ids": "|".join(qids[i:i + 50]),
                "props": "info|labels|claims", "format": "json",
            })
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise RuntimeError(f"wbgetentities: {data['error']}")
            for qid, ent in data["entities"].items():
                out[qid] = ent
                self.labels[qid] = _pick_label(ent)
        return out

    def label(self, qid: str) -> str:
        if qid not in self.labels:
            self.entities([qid])
        return self.labels[qid]

    def sparql(self, query: str) -> List[Dict[str, str]]:
        resp = self.session.get(WDQS, params={"query": query, "format": "json"},
                                headers={"Cache-Control": "no-cache"})
        resp.raise_for_status()
        return [{k: v["value"].rsplit("/", 1)[-1] for k, v in row.items()}
                for row in resp.json()["results"]["bindings"]]


def _pick_label(ent: Dict[str, Any]) -> str:
    labels = ent.get("labels", {})
    for lang in ("en", "mul", "fr", "ru", "be"):
        if lang in labels:
            return labels[lang]["value"]
    for value in labels.values():
        return f"{value['value']} [{value['language']}]"
    return "(no label)"


def claims(ent: Dict[str, Any], prop: str) -> List[Dict[str, Any]]:
    return ent.get("claims", {}).get(prop, [])


def item_value(snak: Dict[str, Any]) -> Optional[str]:
    value = (snak.get("datavalue") or {}).get("value")
    return value.get("id") if isinstance(value, dict) else None


def time_value(snak: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    value = (snak.get("datavalue") or {}).get("value")
    return value if isinstance(value, dict) and "time" in value else None


def wb_time(tv: Dict[str, Any]) -> str:
    """A time value as the string wikibase-edit parses back to the same value.

    wikibase-edit infers precision from the string's length (`2025` is 9,
    `2025-07` is 10, `2025-07-04` is 11), so trimming to the precision keeps it
    exact. Anything coarser than a year or finer than a day is refused rather
    than rounded.
    """
    precision = tv["precision"]
    if precision not in (9, 10, 11):
        raise ValueError(f"unsupported precision {precision}: {tv['time']}")
    stamp = tv["time"].lstrip("+").split("T")[0]
    return {9: stamp[:4], 10: stamp[:7], 11: stamp}[precision]


def is_past(tv: Dict[str, Any]) -> bool:
    return wb_time(tv) <= TODAY[: len(wb_time(tv))]


def L(reader: Reader, qid: str) -> str:
    return f"{qid} ({reader.label(qid)})"


def summary(reason: str) -> List[str]:
    return ["--summary", f"office data fix: {reason}", "--maxlag", str(MAXLAG)]


# --- planners ---------------------------------------------------------------


def plan_burundi_provinces(reader: Reader, notes: List[str]) -> List[Edit]:
    country = reader.entity(BURUNDI)
    rev = str(country["lastrevid"])
    statements = claims(country, "P150")
    listed = {item_value(c["mainsnak"]) for c in statements}
    targets = reader.entities([q for q in listed if q] + NEW_PROVINCES + [RUMONGE])
    edits: List[Edit] = []

    for claim in statements:
        target = item_value(claim["mainsnak"])
        if target is None or target == GITEGA:
            continue
        ends = [time_value(c["mainsnak"]) for c in claims(targets[target], "P576")]
        ends = [e for e in ends if e]
        if not ends:
            continue
        if len({json.dumps(e, sort_keys=True) for e in ends}) > 1:
            notes.append(f"skip P582 on P150 {L(reader, target)}: several P576 values")
            continue
        end = ends[0]
        if not is_past(end):
            continue
        if "P582" in claim.get("qualifiers", {}):
            continue
        reason = (f"end P150 {L(reader, target)} on {L(reader, BURUNDI)} at its "
                  f"P576 dissolution ({wb_time(end)})")
        edits.append(Edit(
            args=["wb", "add-qualifier", claim["id"], "P582", wb_time(end),
                  *summary(reason), "--baserevid", rev],
            reason=reason, qids=[BURUNDI, target]))

    for qid in NEW_PROVINCES:
        if qid in listed:
            continue
        ent = targets[qid]
        p31 = {item_value(c["mainsnak"]) for c in claims(ent, "P31")}
        p17 = {item_value(c["mainsnak"]) for c in claims(ent, "P17")}
        starts = [t for t in (time_value(c["mainsnak"]) for c in claims(ent, "P571")) if t]
        problems = []
        if not p31 & PROVINCE_CLASSES:
            problems.append(f"P31 is {sorted(p31)}, not a province class")
        if BURUNDI not in p17:
            problems.append(f"P17 is {sorted(p17)}, not {BURUNDI}")
        if claims(ent, "P576"):
            problems.append("carries a P576")
        if len(starts) != 1:
            problems.append(f"has {len(starts)} P571 values, needs exactly one")
        elif not wb_time(starts[0]).startswith("2025"):
            problems.append(f"P571 is {wb_time(starts[0])}, not in 2025")
        if problems:
            notes.append(f"skip P150 {L(reader, qid)}: " + "; ".join(problems))
            continue
        start = wb_time(starts[0])
        reason = (f"add current province {L(reader, qid)} to P150 of "
                  f"{L(reader, BURUNDI)}, from its P571 {start}")
        payload = {"id": BURUNDI, "claims": {"P150": [{
            "value": qid,
            "qualifiers": {"P580": start},
            "references": [{"P854": REFORM_URL, "P813": TODAY}],
        }]}}
        edits.append(Edit(
            args=["wb", "edit-entity", json.dumps(payload, ensure_ascii=False),
                  *summary(reason), "--baserevid", rev],
            reason=reason, qids=[BURUNDI, qid]))

    rumonge = targets[RUMONGE]
    notes.append(
        f"report {L(reader, RUMONGE)}: in P150 of {BURUNDI}: {RUMONGE in listed}; "
        f"P576: {[wb_time(t) for t in (time_value(c['mainsnak']) for c in claims(rumonge, 'P576')) if t] or 'none'}; "
        f"P31 qualifiers: {[sorted(c.get('qualifiers', {})) for c in claims(rumonge, 'P31')]}"
        " — no edit planned")
    return edits


def plan_burundi_pm(reader: Reader, notes: List[str]) -> List[Edit]:
    ent = reader.entity(BURUNDI_PM)
    starts = [t for t in (time_value(c["mainsnak"]) for c in claims(ent, "P571")) if t]
    if any(wb_time(t).startswith(PM_RESTORED) for t in starts):
        return []
    ends = [wb_time(t) for t in (time_value(c["mainsnak"]) for c in claims(ent, "P576")) if t]
    reason = (f"{L(reader, BURUNDI_PM)} was restored in {PM_RESTORED} after its "
              f"P576 {', '.join(ends)}: second normal-rank P571")
    payload = {"id": BURUNDI_PM, "claims": {"P571": [{
        "value": PM_RESTORED,
        "references": [{"P854": PM_URL, "P813": TODAY}],
    }]}}
    notes.append(f"{BURUNDI_PM}: no rank change — restored offices keep every "
                 "P571/P576 at normal rank")
    return [Edit(
        args=["wb", "edit-entity", json.dumps(payload, ensure_ascii=False),
              *summary(reason), "--baserevid", str(ent["lastrevid"])],
        reason=reason, qids=[BURUNDI_PM])]


def plan_by_judge(reader: Reader, notes: List[str]) -> List[Edit]:
    ent = reader.entity(BY_JUDGE)
    rev = str(ent["lastrevid"])
    edits: List[Edit] = []

    # Which metaclass Belarus's offices use, counted over offices with holders.
    rows = reader.sparql(f"""
        SELECT ?cls (COUNT(DISTINCT ?item) AS ?n) WHERE {{
          ?item wdt:P1001 wd:{BELARUS} .
          ?item p:P31/ps:P31 ?cls .
          FILTER EXISTS {{ ?holder p:P39/ps:P39 ?item }}
        }} GROUP BY ?cls ORDER BY DESC(?n) LIMIT 5""")
    if not rows:
        notes.append(f"skip P31 on {L(reader, BY_JUDGE)}: no Belarus metaclass measured")
        return edits
    counts = ", ".join(f"{r['cls']} ({reader.label(r['cls'])}) {r['n']}" for r in rows[:3])
    notes.append(f"Belarus offices with P1001 {BELARUS} and holders, by P31: {counts}")
    metaclass = rows[0]["cls"]
    if not claims(ent, "P31"):
        reason = (f"type {L(reader, BY_JUDGE)} as {L(reader, metaclass)}, the "
                  f"metaclass of {rows[0]['n']} Belarus offices")
        edits.append(Edit(
            args=["wb", "add-claim", BY_JUDGE, "P31", metaclass,
                  *summary(reason), "--baserevid", rev],
            reason=reason, qids=[BY_JUDGE, metaclass]))

    siblings = reader.entities(BY_COURT_SIBLINGS)
    for qid, sib in siblings.items():
        p279 = [item_value(c["mainsnak"]) for c in claims(sib, "P279")]
        notes.append(f"sibling {L(reader, qid)}: P279 "
                     + ", ".join(L(reader, q) for q in p279 if q))
    own = [item_value(c["mainsnak"]) for c in claims(ent, "P279")]
    if JUDGE in own:
        notes.append(f"{L(reader, BY_JUDGE)} already has P279 {L(reader, JUDGE)}, "
                     "the class its judge sibling uses — no P279 planned")
    elif not own:
        reason = f"subclass {L(reader, BY_JUDGE)} of {L(reader, JUDGE)}, as its siblings"
        edits.append(Edit(
            args=["wb", "add-claim", BY_JUDGE, "P279", JUDGE,
                  *summary(reason), "--baserevid", rev],
            reason=reason, qids=[BY_JUDGE, JUDGE]))
    else:
        notes.append(f"{BY_JUDGE} has P279 {own}; left alone")
    return edits


def plan_kgb_chair(reader: Reader, notes: List[str]) -> List[Edit]:
    ent = reader.entity(BY_KGB_CHAIR)
    rev = str(ent["lastrevid"])
    p1001 = claims(ent, "P1001")
    values = {item_value(c["mainsnak"]) for c in p1001}
    edits: List[Edit] = []
    if BELARUS not in values:
        reason = (f"{L(reader, BY_KGB_CHAIR)} is exercised over "
                  f"{L(reader, BELARUS)}: add P1001")
        edits.append(Edit(
            args=["wb", "add-claim", BY_KGB_CHAIR, "P1001", BELARUS,
                  *summary(reason), "--baserevid", rev],
            reason=reason, qids=[BY_KGB_CHAIR, BELARUS]))

    others = [c for c in p1001 if item_value(c["mainsnak"]) not in (BELARUS, None)]
    people = reader.entities([item_value(c["mainsnak"]) for c in others]) if others else {}
    holders = {item_value(c["mainsnak"]) for c in claims(ent, "P1308")}
    for claim in others:
        person = item_value(claim["mainsnak"])
        kinds = {item_value(c["mainsnak"]) for c in claims(people[person], "P31")}
        if HUMAN not in kinds:
            notes.append(f"skip P1001 {L(reader, person)} on {BY_KGB_CHAIR}: "
                         "not typed human, left alone")
            continue
        held = {item_value(c["mainsnak"]) for c in claims(people[person], "P39")}
        notes.append(
            f"P1308 of {L(reader, BY_KGB_CHAIR)} records {L(reader, person)}: "
            f"{person in holders}; {person} holds P39 {BY_KGB_CHAIR}: "
            f"{BY_KGB_CHAIR in held} — nothing planned")
        reason = (f"P1001 of {L(reader, BY_KGB_CHAIR)} names a person, "
                  f"{L(reader, person)}, not a jurisdiction: remove it")
        edits.append(Edit(
            args=["wb", "remove-claim", claim["id"], *summary(reason),
                  "--baserevid", rev],
            reason=reason, qids=[BY_KGB_CHAIR, person], destructive=True,
            blocked=None if BELARUS in values else
            f"waits for P1001 {BELARUS} to be live on {BY_KGB_CHAIR}"))
    return edits


PLANNERS = [
    ("1. Burundi P150 after the 2025 province reform", plan_burundi_provinces),
    ("2. Prime Minister of Burundi restored in 2020", plan_burundi_pm),
    ("3. Belarus Constitutional Court judge type", plan_by_judge),
    ("4. Belarus KGB chair jurisdiction", plan_kgb_chair),
]


# --- output and execution ---------------------------------------------------


def render(edit: Edit) -> str:
    def quote(arg: str) -> str:
        return "'" + arg.replace("'", "'\\''") + "'" if any(
            ch in arg for ch in " $\"'{}:(),") else arg
    flag = "[DESTRUCTIVE] " if edit.destructive else ""
    wait = f"\n      (blocked: {edit.blocked})" if edit.blocked else ""
    return f"  {flag}# {edit.reason}{wait}\n  {' '.join(quote(a) for a in edit.args)}"


def run(args: List[str]) -> None:
    result = subprocess.run(args, capture_output=True, text=True,
                            timeout=WRITE_TIMEOUT, stdin=subprocess.DEVNULL)
    if result.stderr.strip():
        print(result.stderr.strip()[-600:])
    if result.returncode != 0:
        raise SystemExit(f"{' '.join(args[:2])} failed: "
                         f"{(result.stderr or result.stdout).strip()[:400]}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true",
                        help="Make the edits; without it nothing is written")
    opts = parser.parse_args()

    reader = Reader()
    total = 0
    for title, planner in PLANNERS:
        print(f"\n== {title}")
        notes: List[str] = []
        edits = planner(reader, notes)
        for edit in edits:
            print(render(edit))
        for note in notes:
            print(f"  note: {note}")
        if not edits:
            print("  (nothing to do)")
        total += len(edits)
        if not opts.apply:
            continue
        # One edit, then a fresh read and a fresh plan: each edit goes out
        # against the revision it was planned from, and a blocked removal
        # becomes runnable only once its replacement is live.
        for _ in range(len(edits) + 2):
            ready = [e for e in edits if not e.blocked]
            if not ready:
                break
            print(f"  applying: {ready[0].reason}")
            run(ready[0].args)
            edits = planner(reader, [])
        if edits:
            raise SystemExit(f"{title}: {len(edits)} edit(s) still planned after applying")

    mode = "applied" if opts.apply else "planned (dry run; pass --apply to write)"
    print(f"\n{total} edit(s) {mode}")


if __name__ == "__main__":
    main()
