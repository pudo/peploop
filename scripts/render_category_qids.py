#!/usr/bin/env python
"""Merge every resolution pass into one verdict per wd_categories spec.

    python scripts/render_category_qids.py

Three passes have looked at the 273 `position:` blocks in wd_categories.yml:
the name-search resolution + its agent verification (positions.json), the
category-item/P39-tally tail (tail.json, bucket.json), and the agent
adjudication of that tail (verdicts/tail_*.jsonl). This collapses them into

* data/categories/resolved.json — key → qid | null + why, the input to
  `patch_categories_yml.py`;
* data/categories/qid_plan.md — the human review document, grouped by what
  the reviewer has to decide;
* data/categories/create_positions.qs — QuickStatements CREATE commands for
  the offices that genuinely have no item.

Later passes win: a tail verdict overrides the mechanical tail status, which
overrides the original name-search resolution.
"""

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.api import best_label, fetch_entities
from wd.http import REPO_ROOT, make_session

YML = Path(
    "/Users/pudo/Code/opensanctions/datasets/_wikidata/categories/wd_categories.yml"
)
OUT_DIR = REPO_ROOT / "data" / "categories"
VERDICT_DIR = OUT_DIR / "verdicts"

# Verdicts that mean "no P39 target should exist", with the reason class.
NO_TARGET = {"no-p39-target"}


def load_verdicts(pattern: str) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    for path in sorted(VERDICT_DIR.glob(pattern)):
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            out[row["key"]] = row
    return out


def resolve(
    spec: dict, tail: Optional[dict], verdict: Optional[dict]
) -> Dict[str, Any]:
    """One spec's final answer, and the pass that produced it."""
    out = {
        "key": spec["key"],
        "category": spec["category"],
        "language": spec["language"],
        "position_name": spec["position_name"],
        "position_country": spec["position_country"],
        "granularity": spec["granularity"],
        "declared_qid": spec["declared_qid"],
        "qid": None,
        "source": None,
        "status": None,
        "confidence": None,
        "reason": None,
        "scope_note": None,
        "create": None,
        "duplicates": (tail or {}).get("duplicates") or [],
        "language_mismatch": (tail or {}).get("language_mismatch", False),
        "category_lang": (tail or {}).get("category_lang"),
    }

    if verdict is not None:
        out["confidence"] = verdict.get("confidence")
        out["reason"] = verdict.get("reason")
        out["scope_note"] = verdict.get("scope_note")
        kind = verdict["verdict"]
        out["source"] = "agent-tail"
        if kind in ("confirm", "replace") and verdict.get("qid"):
            out["qid"], out["status"] = verdict["qid"], "resolved"
        elif kind == "create":
            out["status"], out["create"] = "create", verdict.get("create")
        elif kind in NO_TARGET:
            out["status"] = "no-p39-target"
        else:
            out["status"] = "unclear"
        return out

    # Rows that never entered the tail: the original resolution + its
    # verification agent pass.
    check = spec.get("verification") or {}
    out["confidence"] = check.get("confidence")
    out["reason"] = check.get("reason")
    out["scope_note"] = check.get("scope_note")
    out["source"] = "name-search" if check else "declared"
    if check.get("verdict") == "reject":
        out["status"] = "no-p39-target"
    elif spec.get("resolved_qid"):
        out["qid"], out["status"] = spec["resolved_qid"], "resolved"
    else:
        out["status"] = "unclear"
    return out


def dedupe_creates(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One CREATE per office, not per spec.

    Several offices are named by two specs — the English category and its
    local-language sibling (`Presidents_of_the_National_Congress_(Ecuador)`
    and `Presidentes_del_Congreso_Nacional_de_Ecuador`). Emitting both would
    create two items for one office, which is the exact duplication this
    campaign keeps having to clean up.
    """
    seen: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        spec = row["create"] or {}
        label = (spec.get("label") or "").casefold()
        if not label:
            continue
        if label in seen:
            seen[label]["shared_with"].append(row["key"])
            continue
        row = dict(row)
        row["shared_with"] = []
        seen[label] = row
    return list(seen.values())


def qs_create(rows: List[Dict[str, Any]]) -> str:
    """QuickStatements V1 CREATE batch for the offices with no item.

    Additive and single-concern per the workbench rules: item creation only,
    no P39 statements — those follow once the QIDs exist.
    """
    lines: List[str] = []
    for row in rows:
        spec = row["create"] or {}
        label = spec.get("label")
        if not label:
            continue
        lines.append("CREATE")
        lines.append(f'LAST\tLen\t"{label}"')
        if spec.get("description"):
            lines.append(f'LAST\tDen\t"{spec["description"]}"')
        for qid in spec.get("P31") or []:
            lines.append(f"LAST\tP31\t{qid}")
        for qid in spec.get("P279") or []:
            lines.append(f"LAST\tP279\t{qid}")
        for prop in ("P17", "P1001", "P361", "P2389"):
            if spec.get(prop):
                lines.append(f"LAST\t{prop}\t{spec[prop]}")
        lines.append("")
    return "\n".join(lines)


def specs_from_yml() -> List[Dict[str, Any]]:
    """The spec list, read from the yml rather than the cached
    positions.json — upstream adds `position:` blocks between sessions (the
    Lithuanian block appeared after the first snapshot and went unresolved),
    and a cached list silently drops them."""
    import yaml

    data = yaml.safe_load(YML.read_text())["config"]["categories"]
    cached = {r["key"]: r for r in json.load((OUT_DIR / "positions.json").open())}
    out = []
    for spec in data:
        if "position" not in spec:
            continue
        pos = spec["position"]
        key = f"{spec.get('language', 'en')}:{spec['category']}"
        row = cached.get(key)
        if row is None:
            row = {
                "key": key,
                "category": spec["category"],
                "language": spec.get("language", "en"),
                "position_name": pos["name"],
                "position_country": pos.get("country") or spec.get("country"),
                "granularity": "office",
                "declared_qid": pos.get("wikidata_id"),
                "resolved_qid": pos.get("wikidata_id"),
                "verification": None,
            }
        out.append(row)
    return out


def main() -> None:
    specs = specs_from_yml()
    tail_rows: Dict[str, dict] = {}
    for name in ("tail", "bucket"):
        path = OUT_DIR / f"{name}.json"
        if path.exists():
            for row in json.load(path.open()):
                tail_rows[row["key"]] = row
    verdicts = load_verdicts("tail_*.jsonl")

    rows = [resolve(s, tail_rows.get(s["key"]), verdicts.get(s["key"]))
            for s in specs]

    # Label the resolved QIDs so the review document is readable.
    session = make_session()
    qids = sorted({r["qid"] for r in rows if r["qid"]})
    entities = fetch_entities(session, qids, props="labels|descriptions")
    labels = {q: best_label(e) or "" for q, e in entities.items()}
    for row in rows:
        row["qid_label"] = labels.get(row["qid"] or "", "")

    (OUT_DIR / "resolved.json").write_text(
        json.dumps(rows, indent=1, ensure_ascii=False))

    creates = dedupe_creates(
        [r for r in rows if r["status"] == "create" and r["create"]])
    (OUT_DIR / "create_positions.qs").write_text(qs_create(creates))

    by_status = Counter(r["status"] for r in rows)
    md = [
        "# wd_categories.yml — position QIDs",
        "",
        f"{len(rows)} `position:` blocks: {dict(by_status)}",
        "",
        "`resolved` rows are ready to write back as `wikidata_id:` "
        "(`scripts/patch_categories_yml.py`). Everything else needs a call.",
        "",
    ]

    md.append("## Resolved\n")
    md.append("| QID | Wikidata label | yml position name | country | category |")
    md.append("|---|---|---|---|---|")
    for r in sorted((r for r in rows if r["status"] == "resolved"),
                    key=lambda r: (r["position_country"] or "", r["qid"])):
        md.append(
            f"| [{r['qid']}](https://www.wikidata.org/wiki/{r['qid']}) "
            f"| {r['qid_label']} | {r['position_name']} "
            f"| {r['position_country'] or '—'} | `{r['category']}` |")

    notes = [r for r in rows if r["status"] == "resolved" and r["scope_note"]]
    md.append(f"\n### Scope notes on resolved rows ({len(notes)})\n")
    for r in notes:
        md.append(f"* **{r['qid']}** {r['position_name']} — {r['scope_note']}")

    md.append("\n## Item creation proposed\n")
    for r in creates:
        c = r["create"]
        md.append(
            f"### {c.get('label')} — `{r['category']}`\n\n"
            f"* {c.get('description')}\n"
            f"* P31 {c.get('P31')}, P279 {c.get('P279')}, "
            f"P17 {c.get('P17')}, P1001 {c.get('P1001')}, "
            f"P361 {c.get('P361')}, P2389 {c.get('P2389')}\n"
            f"* {c.get('notes') or ''}\n"
            + (f"* also named by: {', '.join(r['shared_with'])}\n"
               if r.get("shared_with") else "")
            + f"* evidence: {r['reason']}\n")

    md.append("## No P39 target (the yml models something that isn't an office)\n")
    for r in rows:
        if r["status"] == "no-p39-target":
            md.append(
                f"* **{r['position_name']}** ({r['position_country'] or '—'}) "
                f"← `{r['category']}` — {r['reason']}")

    md.append("\n## Unresolved — needs a human call\n")
    for r in rows:
        if r["status"] == "unclear":
            md.append(
                f"* **{r['position_name']}** ({r['position_country'] or '—'}) "
                f"← `{r['category']}` — {r['reason'] or 'no verdict'}")

    dups = [r for r in rows if r["duplicates"]]
    md.append(f"\n## Duplicate items worth merging ({len(dups)})\n")
    for r in dups:
        md.append(
            f"* {r['position_name']}: keeping **{r['qid']}**, "
            f"duplicates {', '.join(r['duplicates'])}")

    mism = [r for r in rows if r["language_mismatch"]]
    md.append(f"\n## Specs querying the wrong wiki ({len(mism)})\n")
    md.append("See `langcheck.md` for the full sweep over all 594 specs.\n")
    for r in mism:
        md.append(
            f"* `{r['category']}` — yml says `language: {r['language']}`, "
            f"category lives on {r['category_lang']}wiki")

    (OUT_DIR / "qid_plan.md").write_text("\n".join(md) + "\n")
    print(dict(by_status))
    print(f"{len(creates)} creations → create_positions.qs")


if __name__ == "__main__":
    main()
