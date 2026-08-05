#!/usr/bin/env python
"""Extract the synthetic PETScan positions from wd_categories.yml.

    python scripts/category_positions.py

The OpenSanctions category crawler assigns members of some Wikipedia
categories a made-up position entity (name + country, no Wikidata id).
This script turns those `position:` blocks into P39-verification candidates
(tasks/category_positions.md): classify each name's granularity (single
office / body membership / per-person bucket), then resolve office and
membership names to actual Wikidata position items via
`wd.positions.lookup_position`.

Output: data/categories/positions.json (interim format) + positions.md.
"""

import json
import re
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.http import REPO_ROOT, make_session
from wd.positions import country_names, lookup_position

YML = Path(
    "/Users/pudo/Code/opensanctions/datasets/_wikidata/categories/wd_categories.yml"
)
OUT_DIR = REPO_ROOT / "data" / "categories"


def classify(name: str, country: str | None) -> str:
    low = name.casefold().strip()
    if re.search(r"\b(?:a|an)\s+[a-z]", low) or low in ("mayor", "mayor (spain)"):
        return "bucket"
    # Class assignments over many distinct offices, not one seat:
    if re.match(r"^local councillor\b", low) or re.search(
        r"\b(advisor|leadership)$", low
    ):
        return "bucket"
    # "Minister of <own country>" = any portfolio, not one office:
    for cname in country_names(country):
        if re.fullmatch(
            rf"(?:deputy )?(?:minister|member of the government) of (?:the )?{re.escape(cname)}",
            low,
        ):
            return "bucket"
    if re.match(r"^(?:member|deputy|senator|mp) (?:of|at|in)\b", low):
        return "membership"
    return "office"


def main() -> None:
    data = yaml.safe_load(YML.read_text())

    def find(node, key):
        if isinstance(node, dict):
            if key in node:
                return node[key]
            for value in node.values():
                found = find(value, key)
                if found is not None:
                    return found
        return None

    specs = [c for c in find(data, "categories") if "position" in c]
    session = make_session()

    records = []
    for spec in specs:
        pos = spec["position"]
        country = pos.get("country") or spec.get("country")
        name = pos["name"]
        record = {
            "key": f"{spec.get('language', 'en')}:{spec['category']}",
            "category": spec["category"],
            "language": spec.get("language", "en"),
            "depth": spec.get("depth", 0),
            "os_topic": spec.get("topic") or (spec.get("topics") or [None])[0],
            "os_country": spec.get("country"),
            "position_name": name,
            "position_country": country,
            "position_topics": pos.get("topics", []),
            "declared_qid": pos.get("wikidata_id"),
            "granularity": classify(name, country),
            "wd_candidates": [],
            "resolved_qid": None,
            "status": None,
        }
        if record["declared_qid"]:
            record["status"] = "declared"
            record["resolved_qid"] = record["declared_qid"]
        elif record["granularity"] == "bucket":
            record["status"] = "bucket"
        else:
            lookup = lookup_position(session, name, country)
            record["status"] = lookup.status
            record["resolved_qid"] = lookup.resolved_qid
            record["wd_candidates"] = [asdict(c) for c in lookup.candidates]
        records.append(record)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "positions.json").write_text(
        json.dumps(records, indent=1, ensure_ascii=False))

    def resolved_candidate(r):
        return next(
            (c for c in r["wd_candidates"] if c["qid"] == r["resolved_qid"]), {})

    by_status = Counter(r["status"] for r in records)
    md = [
        "# Synthetic PETScan positions — resolution report",
        "",
        f"{len(records)} position-bearing category specs: {dict(by_status)}",
        "",
        "## matched (label + country agree — spot-check, then pipeline-ready)",
    ]
    for r in records:
        if r["status"] == "matched":
            c = resolved_candidate(r)
            flag = "  ⚠ dual-typed list article" if c.get("is_list") else ""
            md.append(
                f"* {r['resolved_qid']} **{r['position_name']}** "
                f"({r['position_country']}) ← {r['category']} — {c.get('description')}{flag}"
            )
    md.append("\n## label-only (exact label, item itself has no country data)")
    for r in records:
        if r["status"] == "label-only":
            c = resolved_candidate(r)
            md.append(
                f"* {r['resolved_qid']} **{r['position_name']}** "
                f"({r['position_country']}) ← {r['category']} — {c.get('description')}"
            )
    md.append("\n## declared in yml (trusted)")
    for r in records:
        if r["status"] == "declared":
            md.append(f"* {r['declared_qid']} {r['position_name']} ← {r['category']}")
    md.append("\n## ambiguous (candidates found, no unique two-signal match)")
    for r in records:
        if r["status"] == "ambiguous":
            md.append(f"* **{r['position_name']}** ({r['position_country']}) ← {r['category']}")
            for c in r["wd_candidates"][:4]:
                flags = ("L" if c["label_match"] else "-") + ("C" if c["country_match"] else "-")
                md.append(f"  * [{flags}] {c['qid']} {c['label']} — {c['description']}")
    md.append("\n## unmatched (no search hits — likely no item exists yet)")
    for r in records:
        if r["status"] == "unmatched":
            md.append(f"* {r['position_name']} ({r['position_country']}) ← {r['category']}")
    md.append("\n## bucket (per-person narrowing pass, separate design)")
    for r in records:
        if r["status"] == "bucket":
            md.append(f"* {r['position_name']} ({r['position_country']}) ← {r['category']} [{r['language']}]")

    (OUT_DIR / "positions.md").write_text("\n".join(md) + "\n")
    print(f"{len(records)} specs: {dict(by_status)}")
    print(f"Wrote {OUT_DIR / 'positions.json'} and {OUT_DIR / 'positions.md'}")


if __name__ == "__main__":
    main()
