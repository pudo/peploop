#!/usr/bin/env python
"""Plan, and on request make, the cleanup of peploop's 2026-10-03 Trinidad and Tobago writes.

    .venv/bin/python scripts/fix_tt_writes.py            # dry, the default
    .venv/bin/python scripts/fix_tt_writes.py --apply    # HUMAN GATE

Each part reads its items live (no cache) and plans only what is not already
true on Wikidata, so a run after `--apply` plans nothing. `--apply` makes one
edit, re-reads, and re-plans, so every edit goes out against the revision it was
planned from (`--baserevid`).

1. Two apply runs on the same queue (EditGroups `4c278983e7`, `7c1fab3a0d`)
   wrote 24 statements twice. Of each exact twin (same property, value and
   qualifier snak hashes) keep the copy whose GUID the peploop DB recorded as
   `proposal.claim_guid`, so the DB keeps pointing at a live statement; if
   neither is recorded, keep the one that appeared first in the item history.
   Removals are destructive and flagged as such.
2. Seven P39 statements went out open although the tenure had ended. Each gets
   the `P582` its source gives, plus a reference to that source.
3. Four current House terms that apply skipped as `apply:termed` are only
   reported: whether Wikidata records them already, or they are missing.
"""

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.http import make_session  # noqa: E402

USER_AGENT = "opensanctions-workbench/0.1 (friedrich@opensanctions.org)"
API = "https://www.wikidata.org/w/api.php"
MAXLAG = 5
WRITE_TIMEOUT = 420
TODAY = date.today().isoformat()
DB = os.environ.get("PEPLOOP_DB", "postgresql:///peploop")
ENWIKI = "Q328"

# Part 1 --------------------------------------------------------------------
BATCHES = ("4c278983e7", "7c1fab3a0d")
TWIN_ITEMS = [
    "Q134396252", "Q134403782", "Q134432225", "Q134513952", "Q134574191",
    "Q135976317", "Q136309626", "Q136309775", "Q136807231", "Q137612135",
    "Q16185455", "Q1673889", "Q17146729",
]
EXPECTED_TWINS = 24

# Part 2 --------------------------------------------------------------------
#: Parliament dissolved on 2025-03-18, which ended every 12th-Parliament
#: senator's seat (the Parliament's own record ends each one that day).
DISSOLUTION = "2025-03-18"
ELECTION_ARTICLE = "2025_Trinidad_and_Tobago_general_election"
DISSOLUTION_QUOTE = (
    "President Christine Kangaloo, on the advice of Prime Minister Stuart "
    "Young, dissolved parliament and issued the writs for election on "
    "18 March 2025.")
#: Persad-Bissessar's appointment as Prime Minister vacated the Young
#: government's ministries (her cabinet followed on 3 May).
NEW_GOVERNMENT = "2025-05-01"
NEW_GOVERNMENT_QUOTE = (
    "Kamla Persad-Bissessar and John Jeremie were sworn in as Prime Minister "
    "and Attorney General respectively on May 1.")
PARLIAMENT = "https://www.ttparliament.org/members/member/{}/parliamentary-career/"


@dataclass
class Stale:
    """One open P39 that should carry an end, and the evidence for it."""

    person: str
    office: str
    start: str  # the P580 as written, to identify the proposal
    end: str  # wikibase-edit time string; precision follows its length
    quote: str
    url: Optional[str] = None  # a P854 source
    wiki: Optional[str] = None  # an enwiki article, cited as P143 + P4656
    note: str = ""


STALE = [
    Stale("Q107504795", "Q107861222", "2015", "2016-10-30",
          url=PARLIAMENT.format("fitzgerald-hinds"),
          quote="11th Republican Parliament (11 Sep 2015 - 30 Oct 2016) "
                "Minister of Works and Transport",
          note="Rohan Sinanan's record has him Minister of Works and Transport "
               "from 31 Oct 2016"),
    Stale("Q107861234", "Q107861237", "2016-03-18", "2018-04-08",
          url=PARLIAMENT.format("randall-mitchell"),
          quote="11th Republican Parliament (18 Mar 2016 - 8 Apr 2018) "
                "Minister of Housing and Urban Development",
          note="his en.wikipedia article: 'On 9 April 2018, he became Minister "
               "of Tourism'"),
    Stale("Q107861285", "Q107861278", "2017-06-30", "2020-08",
          url=PARLIAMENT.format("allyson-west"),
          quote="11th Republican Parliament (14 Aug 2019 - 9 Aug 2020) Minister "
                "of Public Administration and Minister in the Ministry of "
                "Finance; 12th Republican Parliament (19 Aug 2020 - 11 Jul 2021) "
                "Minister of Public Administration and Digital Transformation",
          note="month precision: the record ends the post at 9 Aug 2020 and "
               "the next cabinet, without it, began 19 Aug 2020; she kept it "
               "past the 2019 reshuffle, so not 2025-05-01"),
    Stale("Q115797651", "Q19319420", "2021-06-11", DISSOLUTION,
          url=PARLIAMENT.format("dr-muhammad-yunus-ibrahim"),
          quote="12th Republican Parliament (22 Mar 2022 - 18 Mar 2025)",
          note=f"dissolution, en:{ELECTION_ARTICLE}: '{DISSOLUTION_QUOTE}'"),
    Stale("Q134119903", "Q19319420", "2022-03-22", DISSOLUTION,
          url=PARLIAMENT.format("laurence-hislop"),
          quote="12th Republican Parliament (22 Mar 2022 - 18 Mar 2025) "
                "Senate Government Senator",
          note=f"dissolution, en:{ELECTION_ARTICLE}: '{DISSOLUTION_QUOTE}'"),
    Stale("Q134119901", "Q19319420", "2024-09-25", DISSOLUTION,
          url=PARLIAMENT.format("ancil-dennis"),
          quote="12th Republican Parliament (21 Oct 2024 - 18 Mar 2025) "
                "Senate Government Senator",
          note="the record starts him 21 Oct 2024, not the P580 2024-09-25 "
               "(left alone)"),
    Stale("Q107504750", "Q107861256", "2025-03", NEW_GOVERNMENT,
          wiki=ELECTION_ARTICLE, quote=NEW_GOVERNMENT_QUOTE,
          note="the Parliament's record closes his row at 28 Apr 2025, the "
               "election; the office ran to the new Prime Minister's swearing-in"),
]

# Part 3 --------------------------------------------------------------------
HOUSE = "Q18719159"
PARLIAMENT_13 = "Q134300818"  # 13th Republican Parliament of Trinidad and Tobago
TERMED = [  # person, P580 apply withheld
    ("Q107504936", "2025-04-28"),  # Davendranath Tancoo
    ("Q107504931", "2025-04-28"),  # David Lee
    ("Q107504779", "2025-04-28"),  # Lackram Bodoe
    ("Q107504943", "2025-05-03"),  # Barry Padarath
]


@dataclass
class Edit:
    """One `wb` call and why."""

    args: List[str]
    reason: str
    destructive: bool = False
    blocked: Optional[str] = None


class Reader:
    """Live reads only: every call goes to the API, nothing is cached."""

    def __init__(self) -> None:
        self.session = make_session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.labels: Dict[str, str] = {}

    def get(self, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
        resp = self.session.get(url, params={**params, "format": "json"},
                                headers={"Cache-Control": "no-cache"})
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"{params.get('action')}: {data['error']}")
        return data

    def entity(self, qid: str) -> Dict[str, Any]:
        return self.entities([qid])[qid]

    def entities(self, qids: Iterable[str]) -> Dict[str, Any]:
        qids = list(dict.fromkeys(qids))
        out: Dict[str, Any] = {}
        for i in range(0, len(qids), 50):
            data = self.get(API, {"action": "wbgetentities",
                                  "ids": "|".join(qids[i:i + 50]),
                                  "props": "info|labels|claims"})
            for qid, ent in data["entities"].items():
                out[qid] = ent
                self.labels[qid] = _pick_label(ent)
        return out

    def label(self, qid: str) -> str:
        if qid not in self.labels:
            self.entities([qid])
        return self.labels[qid]

    def first_revision_with(self, qid: str, guids: List[str]) -> Dict[str, int]:
        """The earliest revision id at which each GUID appears in the item."""
        seen: Dict[str, int] = {}
        params = {"action": "query", "prop": "revisions", "titles": qid,
                  "rvprop": "ids|content", "rvslots": "main", "rvdir": "newer",
                  "rvstart": f"{TODAY}T00:00:00Z", "rvlimit": "50"}
        while True:
            data = self.get(API, params)
            for page in data["query"]["pages"].values():
                for rev in page.get("revisions", []):
                    content = rev["slots"]["main"].get("*", "")
                    for guid in guids:
                        if guid not in seen and guid in content:
                            seen[guid] = rev["revid"]
            if "continue" not in data or len(seen) == len(guids):
                return seen
            params.update(data["continue"])

    def wikipedia_revid(self, title: str) -> int:
        resp = self.session.get("https://en.wikipedia.org/w/api.php", params={
            "action": "query", "prop": "revisions", "titles": title,
            "rvprop": "ids", "format": "json"})
        resp.raise_for_status()
        page = next(iter(resp.json()["query"]["pages"].values()))
        return page["revisions"][0]["revid"]


def _pick_label(ent: Dict[str, Any]) -> str:
    labels = ent.get("labels", {})
    for lang in ("en", "mul"):
        if lang in labels:
            return labels[lang]["value"]
    for value in labels.values():
        return f"{value['value']} [{value['language']}]"
    return "(no label)"


def db_rows(sql: str) -> List[List[str]]:
    """Read the peploop DB through psql: this script never writes to it."""
    out = subprocess.run(["psql", DB, "-X", "-A", "-t", "-F", "\t", "-c", sql],
                         capture_output=True, text=True, check=True).stdout
    return [line.split("\t") for line in out.splitlines() if line]


def claims(ent: Dict[str, Any], prop: str) -> List[Dict[str, Any]]:
    return ent.get("claims", {}).get(prop, [])


def item_value(snak: Dict[str, Any]) -> Optional[str]:
    value = (snak.get("datavalue") or {}).get("value")
    return value.get("id") if isinstance(value, dict) else None


def wb_time(tv: Dict[str, Any]) -> str:
    stamp = tv["time"].lstrip("+").split("T")[0]
    return {9: stamp[:4], 10: stamp[:7], 11: stamp}.get(tv["precision"], tv["time"])


def qualifier_times(claim: Dict[str, Any], prop: str) -> List[str]:
    return [wb_time(s["datavalue"]["value"]) if s.get("datavalue") else s["snaktype"]
            for s in claim.get("qualifiers", {}).get(prop, [])]


def L(reader: Reader, qid: str) -> str:
    return f"{qid} ({reader.label(qid)})"


def summary(reason: str) -> List[str]:
    return ["--summary", f"peploop cleanup: {reason}", "--maxlag", str(MAXLAG)]


def twin_key(claim: Dict[str, Any]) -> str:
    """Same property, value and qualifiers: the mainsnak's value plus every
    qualifier snak hash (references and rank deliberately ignored)."""
    snak = claim["mainsnak"]
    quals = sorted(s["hash"] for snaks in claim.get("qualifiers", {}).values()
                   for s in snaks)
    return json.dumps([snak["property"], snak["snaktype"],
                       snak.get("datavalue"), quals], sort_keys=True)


# --- planners ---------------------------------------------------------------


def plan_twins(reader: Reader, notes: List[str]) -> List[Edit]:
    recorded: Set[str] = {row[0] for row in db_rows(
        "SELECT claim_guid FROM proposal WHERE claim_guid IS NOT NULL AND "
        f"person_qid IN ({','.join(repr(q) for q in TWIN_ITEMS)})")}
    peploop_guids: Set[str] = {row[0] for row in db_rows(
        "SELECT claim_guid FROM proposal WHERE claim_guid IS NOT NULL AND "
        f"applied_batch IN ({','.join(repr(b) for b in BATCHES)})")}
    ents = reader.entities(TWIN_ITEMS)
    edits: List[Edit] = []
    for qid in TWIN_ITEMS:
        ent = ents[qid]
        rev = str(ent["lastrevid"])
        for prop, statements in ent.get("claims", {}).items():
            groups: Dict[str, List[Dict[str, Any]]] = {}
            for claim in statements:
                groups.setdefault(twin_key(claim), []).append(claim)
            for group in groups.values():
                if len(group) < 2:
                    continue
                guids = [c["id"] for c in group]
                if not any(g in peploop_guids for g in guids):
                    notes.append(f"{qid} {prop}: twins {guids} carry no GUID "
                                 "from the two batches — left alone")
                    continue
                keep = [g for g in guids if g in recorded]
                why = "the DB's claim_guid"
                if len(keep) != 1:
                    first = reader.first_revision_with(qid, guids)
                    if len(first) != len(guids) or len(set(first.values())) != len(guids):
                        notes.append(f"{qid} {prop}: twins {guids}, DB records "
                                     f"{keep or 'neither'} and history cannot "
                                     "order them — left alone")
                        continue
                    keep = [min(guids, key=first.__getitem__)]
                    why = f"first in history (r{first[keep[0]]})"
                value = item_value(group[0]["mainsnak"])
                for claim in group:
                    if claim["id"] == keep[0]:
                        continue
                    reason = (f"remove duplicate {prop} {L(reader, value) if value else ''} "
                              f"on {L(reader, qid)}, an exact twin of {keep[0]} "
                              f"({why}) written twice by concurrent apply runs")
                    edits.append(Edit(
                        args=["wb", "remove-claim", claim["id"], *summary(reason),
                              "--baserevid", rev],
                        reason=reason, destructive=True))
    by_prop: Dict[str, int] = {}
    for edit in edits:
        prop = edit.reason.split()[2]
        by_prop[prop] = by_prop.get(prop, 0) + 1
    counts = ", ".join(f"{p} {n}" for p, n in sorted(by_prop.items())) or "none"
    flag = "" if len(edits) == EXPECTED_TWINS else f" — EXPECTED {EXPECTED_TWINS}"
    notes.append(f"{len(edits)} duplicate(s) planned for removal ({counts}){flag}")
    return edits


def plan_stale(reader: Reader, notes: List[str]) -> List[Edit]:
    rows = db_rows(
        "SELECT pr.person_qid, pr.value->>'id', pr.qualifiers->'P580'->>'time', "
        "pr.claim_guid FROM proposal pr JOIN person p ON p.qid = pr.person_qid "
        "WHERE p.country = 'tt' AND pr.property = 'P39' AND pr.status = 'applied' "
        "AND pr.decided_at::date = DATE '2026-10-03' AND NOT pr.qualifiers ? 'P582'")
    guids: Dict[tuple, List[str]] = {}
    for person, office, start, guid in rows:
        stamp = start.lstrip("+").split("T")[0].replace("-00", "")
        guids.setdefault((person, office, stamp), []).append(guid)
    ents = reader.entities([s.person for s in STALE])
    reader.entities([s.office for s in STALE])
    edits: List[Edit] = []
    wiki_revs: Dict[str, int] = {}
    for stale in STALE:
        found = guids.get((stale.person, stale.office, stale.start), [])
        who = f"{L(reader, stale.person)} P39 {L(reader, stale.office)} from {stale.start}"
        if len(found) != 1:
            notes.append(f"skip {who}: {len(found)} matching proposal(s) in the DB")
            continue
        guid = found[0]
        ent = ents[stale.person]
        claim = next((c for c in claims(ent, "P39") if c["id"] == guid), None)
        if claim is None:
            notes.append(f"skip {who}: {guid} is not live")
            continue
        rev = str(ent["lastrevid"])
        source = stale.url or f"en:{stale.wiki}"
        ends = qualifier_times(claim, "P582")
        if ends and ends != [stale.end]:
            notes.append(f"skip {who}: already ends {ends}, source says {stale.end}")
        elif not ends:
            reason = (f"end {who} at {stale.end}: {source} — \"{stale.quote}\"")
            edits.append(Edit(
                args=["wb", "add-qualifier", guid, "P582", stale.end,
                      *summary(f"end {who} at {stale.end} ({source})"),
                      "--baserevid", rev],
                reason=reason))
        if stale.note:
            notes.append(f"{stale.person}: {stale.note}")

        refs = [r["snaks"] for r in claim.get("references", [])]
        if stale.url:
            have = any(s.get("datavalue", {}).get("value") == stale.url
                       for r in refs for s in r.get("P854", []))
            snaks: Dict[str, Any] = {"P854": stale.url, "P813": TODAY}
        else:
            wiki_revs.setdefault(stale.wiki, reader.wikipedia_revid(stale.wiki))
            permalink = (f"https://en.wikipedia.org/w/index.php?title={stale.wiki}"
                         f"&oldid={wiki_revs[stale.wiki]}")
            have = any(str(s.get("datavalue", {}).get("value", "")).startswith(
                f"https://en.wikipedia.org/w/index.php?title={stale.wiki}&")
                for r in refs for s in r.get("P4656", []))
            snaks = {"P143": ENWIKI, "P4656": permalink, "P813": TODAY}
        if not have:
            reason = f"reference the end of {who}: {source}"
            edits.append(Edit(
                args=["wb", "add-reference",
                      json.dumps({"guid": guid, "snaks": snaks}, ensure_ascii=False),
                      *summary(reason), "--baserevid", rev],
                reason=reason))
    return edits


def plan_termed(reader: Reader, notes: List[str]) -> List[Edit]:
    ents = reader.entities([p for p, _ in TERMED])
    for person, start in TERMED:
        held = [c for c in claims(ents[person], "P39")
                if item_value(c["mainsnak"]) == HOUSE]
        current = [c for c in held if not c.get("qualifiers", {}).get("P582") and (
            any(t >= "2025" for t in qualifier_times(c, "P580"))
            or PARLIAMENT_13 in {item_value(s) for s in c.get("qualifiers", {}).get("P2937", [])})]
        shapes = "; ".join(
            f"{c['id']} P580 {qualifier_times(c, 'P580') or '-'} P582 "
            f"{qualifier_times(c, 'P582') or '-'} P2937 "
            f"{[item_value(s) for s in c.get('qualifiers', {}).get('P2937', [])] or '-'}"
            for c in held) or "no P39 " + HOUSE
        verdict = ("recorded open — nothing needed" if current else
                   f"MISSING: no open {HOUSE} term from {start} or in "
                   f"{PARLIAMENT_13}")
        notes.append(f"{L(reader, person)} House from {start}: {verdict} [{shapes}]")
    return []


PARTS = [
    ("1. Duplicate statements from concurrent apply runs", plan_twins),
    ("2. Open P39 tenures that had ended", plan_stale),
    ("3. Current House terms withheld as apply:termed (report only)", plan_termed),
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
    for title, planner in PARTS:
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
        # against the revision it was planned from.
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
