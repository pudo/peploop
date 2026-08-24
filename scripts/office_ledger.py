#!/usr/bin/env python
"""Consolidate the offices enrichment runs named but could not place.

    python scripts/office_ledger.py

Every run leaves two artifacts under gitignored `data/`: `*_offices.json`, what
`wd/positions.py:lookup_position` made of each office name the model reported,
and `unresolved.json`, the attested holder and quote behind it. This joins them
into `coverage/offices_named.md`, which is committed, because a creation queue
that lives only in `data/` is not a queue — it is a thing that gets re-derived.

Each name gets a disposition, in the same spirit as every other ledger here:

* `create`   — no item found. **This is the list positions-mapping work wants.**
  Unlike the ~150 offices nine campaigns listed and never minted, each row
  arrives with a holder, dates and a verbatim quote from the article.
* `placed`   — `lookup_position` matched an item on two signals, and the run
  already wrote the P39. Nothing to do.
* `ambiguous` — candidates found, no unique two-signal match. A human picks.
* `no-polity` — matched an item that names no polity it governs, so it was
  refused: "Mayor (wójt) of Świlcza" matching the generic Polish rank `wójt` is
  the case this exists for. Either the item wants a `P1001` or a real item wants
  creating.
"""

import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.http import REPO_ROOT

DATA = REPO_ROOT / "data" / "enrich"
LEDGER = REPO_ROOT / "coverage" / "offices_named.md"
STATE = REPO_ROOT / "coverage" / "offices_named.json"

DISPOSITION = {"unmatched": "create", "matched": "placed",
               "ambiguous": "ambiguous", "no-polity": "no-polity"}
ORDER = ["create", "ambiguous", "no-polity", "placed"]

BLURB = {
    "create": (
        "**No item exists.** This is the queue: each row names an office, a "
        "person attested to have held it, the dates, and the sentence that says "
        "so. `wd/create.py:guard` still applies — a duplicate search, a holder "
        "floor and a body-label check — but the holder floor is already met, "
        "which is what nine campaigns' creation lists never had."
    ),
    "ambiguous": (
        "Candidates found and no unique two-signal match. A human picks, or the "
        "name is too coarse to place at all."
    ),
    "no-polity": (
        "An item matched and was **refused** because it names no polity it "
        "governs — `recipes/position_items.md` calls that a defect, and writing a "
        "specific mayoralty onto a generic administrative rank is the "
        "generic-occupation trap. Either the item wants a `P1001` or a real "
        "office wants creating."
    ),
    "placed": "Matched on two signals; the run already wrote the P39.",
}


def main() -> None:
    rows: dict = {}
    evidence: dict = defaultdict(list)
    for path in sorted(DATA.glob("*/*_offices.json")):
        spec = path.parent.name
        for name, found in json.loads(path.read_text()).items():
            row = rows.setdefault(name, {
                "office_name": name, "specs": [],
                "disposition": DISPOSITION.get(found["status"], found["status"]),
                "qid": found.get("qid"),
                "candidates": found.get("candidates", [])[:2],
            })
            if spec not in row["specs"]:
                row["specs"].append(spec)
    for path in sorted(DATA.glob("*/unresolved.json")):
        spec = path.parent.name
        for entry in json.loads(path.read_text()):
            evidence[entry["office_name"]].append(entry)
    if not rows:
        raise SystemExit(f"no *_offices.json under {DATA} — run scripts/enrich.py")

    for name, row in rows.items():
        seen = set()
        row["holders"] = []
        for e in evidence.get(name, []):
            key = (e["holder"], e.get("start"), e.get("end"))
            if key in seen:
                continue
            seen.add(key)
            row["holders"].append(
                {"qid": e["holder"], "start": e.get("start"),
                 "end": e.get("end"), "quote": (e.get("quote") or "")[:160]})

    grouped: dict = defaultdict(list)
    for row in rows.values():
        grouped[row["disposition"]].append(row)
    ordered = [r for name in ORDER for r in sorted(
        grouped.get(name, []), key=lambda r: (-len(r["holders"]), r["office_name"]))]
    STATE.write_text(json.dumps(ordered, indent=1, ensure_ascii=False) + "\n")

    md = [
        "# Offices the enrichment loop named",
        "",
        f"Measured {date.today().isoformat()} by `scripts/office_ledger.py` over "
        "every run under `data/enrich/`.",
        "",
        "A run's gazetteer holds the office its spec names and, for a",
        "single-target spec, nothing else — so **every other office a person",
        "turns out to have held** reads as unresolved by construction.",
        "`wd/positions.py:lookup_position` places what it can; what is left is a",
        "creation queue with evidence attached, which is the thing",
        "`tasks/category_positions.md` has wanted since 2026-08-05.",
        "",
        "One row per office, merged across the runs that named it: an item is",
        "created per office, and two specs naming the same one is corroboration",
        "rather than two jobs.",
        "",
        "| disposition | offices | with an attested holder |",
        "|---|---:|---:|",
    ]
    for name in ORDER:
        group = grouped.get(name, [])
        if group:
            md.append(f"| `{name}` | {len(group)} | "
                      f"{sum(1 for r in group if r['holders'])} |")
    md.append("")
    for name in ORDER:
        group = [r for r in ordered if r["disposition"] == name]
        if not group:
            continue
        md += [f"## `{name}` ({len(group)})", "", BLURB[name], ""]
        for row in group:
            head = f"* **{row['office_name']}**"
            if row["qid"]:
                head += f" → {row['qid']}"
            md.append(head + "  ·  " + ", ".join(
                f"`{spec[:38]}`" for spec in row["specs"]))
            for holder in row["holders"][:3]:
                span = "–".join(
                    filter(None, (holder["start"], holder["end"]))) or "undated"
                md.append(f"  * {holder['qid']} {span} — “{holder['quote']}”")
            for cand in row["candidates"]:
                flags = ("L" if cand.get("label_match") else "-") + \
                        ("C" if cand.get("country_match") else "-")
                md.append(f"  * candidate [{flags}] {cand['qid']} {cand.get('label')}")
        md.append("")
    LEDGER.write_text("\n".join(md) + "\n")
    print(" ".join(f"{n}={len(grouped.get(n, []))}" for n in ORDER))
    print(f"Wrote {LEDGER} and {STATE}")


if __name__ == "__main__":
    main()
