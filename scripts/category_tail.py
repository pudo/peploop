#!/usr/bin/env python
"""Resolve the tail of `wd_categories.yml` positions that name-search missed.

    python scripts/category_tail.py                  # ambiguous + unmatched
    python scripts/category_tail.py --statuses=bucket
    python scripts/category_tail.py "ru:Депутаты Московской городской думы"

`category_positions.py` resolves a position name to a QID by searching for
the name — which fails whenever the yml's English paraphrase isn't what
Wikidata calls the office ("Deputy of the Moscow City Duma" vs "member of
the Moscow City Duma"), and cannot choose between duplicates. Two signals
that don't depend on the wording pick up that tail:

* the **category item** itself — `{lang}wiki:Category:X` usually exists on
  Wikidata with P301 (main topic) / P971 (combines topics) pointing at the
  body or the office, plus the P4224 class of its members;
* a **P39 tally over the category's members** — whatever office the people
  in the category already hold on Wikidata, counted. The office the category
  is named after normally tops the tally by a wide margin.

Output: data/categories/tail.json + tail.md (review), and chunk files for
the verification agents.
"""

import json
import re
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.api import (
    best_description,
    best_label,
    claim_qids,
    fetch_entities,
    sparql,
    WD_API,
)
from wd.http import REPO_ROOT, get_text, make_session
from wd.petscan import category_members
from wd.positions import (
    LIST_ARTICLE,
    country_qid,
    lookup_position,
    norm_label,
    query_variants,
)

OUT_DIR = REPO_ROOT / "data" / "categories"
TAIL_STATUSES = ("ambiguous", "unmatched")
# Members sampled per category for the P39 tally: three wbgetentities calls
# is plenty to separate the category's office from incidental ones.
TALLY_MEMBERS = 150
# Politicians accumulate offices, so a category's own office has to *lead*
# the tally, not merely appear in it: this share, and this much of a margin
# over the runner-up (Moscow city deputies move on to the State Duma often
# enough that the two run neck and neck — correctly inconclusive).
TALLY_MIN_SHARE = 0.4
TALLY_MIN_RATIO = 1.5

# Some yml specs name a category in the local language but leave `language`
# at the default (en), so the crawler queries the wrong wiki entirely. Try
# the wikis the spec's country would plausibly use, and report which one
# actually holds the category.
COUNTRY_LANGS = {
    "by": ("ru", "be"), "cz": ("cs",), "ru": ("ru",), "ua-cri": ("ru", "uk"),
    "es": ("es",), "ec": ("es",), "co": ("es",), "ve": ("es",), "mx": ("es",),
    "gt": ("es",), "ni": ("es",), "mm": ("my",), "au": ("en",), "sg": ("en",),
}


def category_sites(language: str, country: Optional[str]) -> List[str]:
    langs = [language, *COUNTRY_LANGS.get(country or "", ()), "en"]
    return list(dict.fromkeys(f"{lang}wiki" for lang in langs))


def category_item(
    session, sites: Sequence[str], category: str
) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    """The Wikidata item for a Wikipedia category page, and the wiki it was
    found on. `sites` is tried one request per site so the caller learns
    *which* wiki has the category, not just that one does.

    `normalize=1` is load-bearing: every wiki localizes the category
    namespace ("Категория:", "Kategorie:"), and without it the English
    `Category:` prefix simply misses on non-English wikis.
    """
    title = "Category:" + category.replace("_", " ").strip()
    for site in sites:
        raw = get_text(
            session,
            WD_API,
            params={
                "action": "wbgetentities", "format": "json",
                "sites": site, "titles": title, "normalize": "1",
                "props": "labels|descriptions|claims|sitelinks",
            },
        )
        entities = json.loads(raw).get("entities", {})
        for qid, entity in entities.items():
            if qid.startswith("-") or "missing" in entity:
                continue
            return entity, site[: -len("wiki")]
    return None, None


def topic_hints(entity: Optional[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Category-item links that name what the category is about."""
    if entity is None:
        return {}
    hints = {}
    for prop in ("P301", "P971", "P4224", "P910", "P2517"):
        qids = claim_qids(entity, prop)
        if qids:
            hints[prop] = qids
    return hints


def p39_tally(session, language: str, category: str, depth: int) -> Dict[str, Any]:
    """Count the P39 values held by the category's members (all ranks —
    `wdt:P39` would only show each person's preferred statement)."""
    try:
        members = category_members(session, category, language, depth=depth)
    except Exception as exc:  # PETScan is flaky; the other signals still work
        return {"error": f"{type(exc).__name__}: {exc}", "members": 0, "top": []}
    sample = [qid for qid, _ in members][:TALLY_MEMBERS]
    if not sample:
        return {"members": 0, "sampled": 0, "top": []}
    entities = fetch_entities(session, sample, props="claims")
    counts: Counter = Counter()
    for entity in entities.values():
        counts.update(set(claim_qids(entity, "P39")))
    sampled = len(entities)
    top = [
        {"qid": qid, "holders": n, "share": round(n / sampled, 3)}
        for qid, n in counts.most_common(8)
    ]
    return {"members": len(members), "sampled": sampled, "top": top}


def describe(session, qids: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    """Label / description / type / country for candidate QIDs."""
    out: Dict[str, Dict[str, Any]] = {}
    if not qids:
        return out
    entities = fetch_entities(
        session, qids, props="labels|aliases|descriptions|claims")
    for qid in qids:
        entity = entities.get(qid)
        if entity is None:
            continue
        types = claim_qids(entity, "P31")
        out[qid] = {
            "qid": entity["id"],
            "label": best_label(entity) or "",
            "description": best_description(entity),
            "types": types,
            "subclass_of": claim_qids(entity, "P279"),
            "country_qids": sorted(
                set(claim_qids(entity, "P17")) | set(claim_qids(entity, "P1001"))),
            "part_of": claim_qids(entity, "P361") + claim_qids(entity, "P2389"),
            "holder_count": len(entity.get("claims", {}).get("P1308", [])),
            "is_list": LIST_ARTICLE in types,
            "aliases": sorted({
                a["value"] for lst in entity.get("aliases", {}).values()
                for a in lst
            })[:12],
        }
    return out


def position_closure(session, qids: Sequence[str]) -> set:
    """Which of these items are actually offices?

    Needed because a category's P301 often names the *body* (the Moscow City
    Duma, the Council of Ministers) rather than the *seat* in it, and P39
    wants the seat. Walks P31/P279 up to the position/office roots.

    The first hop is `p:/ps:` rather than `wdt:`: rank filtering applies to
    every property, not just P39. One preferred P31 hides all the others
    (Q12251224 "Crown Prince of Saudi Arabia" reads as *only* a crown prince,
    not a position), and a deprecated P31 disappears from `wdt:` entirely
    (Q68081922). Both are real positions that `wdt:P31` misses.
    """
    if not qids:
        return set()
    values = " ".join(f"wd:{q}" for q in qids)
    rows = sparql(session, f"""
        SELECT DISTINCT ?item WHERE {{
          VALUES ?item {{ {values} }}
          {{ ?item p:P31/ps:P31/wdt:P279* ?root }}
          UNION
          {{ ?item p:P279/ps:P279/wdt:P279* ?root }}
          VALUES ?root {{ wd:Q4164871 wd:Q294414 wd:Q702269 wd:Q1799072 }}
        }}""")
    return {r["item"] for r in rows}


def dominant(tally: Dict[str, Any]) -> Optional[str]:
    """The one P39 target the category's members overwhelmingly share."""
    top = tally.get("top") or []
    if not top or top[0]["share"] < TALLY_MIN_SHARE:
        return None
    if len(top) > 1 and top[1]["share"] * TALLY_MIN_RATIO > top[0]["share"]:
        return None
    return top[0]["qid"]


def resolve_row(session, row: Dict[str, Any]) -> Dict[str, Any]:
    name, country = row["position_name"], row["position_country"]
    expected = country_qid(country)
    sites = category_sites(row["language"], country or row["os_country"])
    cat_entity, cat_lang = category_item(session, sites, row["category"])
    hints = topic_hints(cat_entity)
    tally = p39_tally(
        session, cat_lang or row["language"], row["category"], min(row["depth"], 1))

    lead = dominant(tally)
    tally_qids = [lead] if lead else []
    hint_qids = [q for qids in hints.values() for q in qids]
    search_qids = [c["qid"] for c in row["wd_candidates"]]
    pool = list(dict.fromkeys(
        [t["qid"] for t in tally["top"]] + hint_qids + search_qids))
    info = describe(session, pool)

    variants = {norm_label(q) for q in query_variants(name, country)}
    shares = {t["qid"]: t["share"] for t in tally["top"]}
    offices = position_closure(session, [q for q in pool if q in info])
    main_topics = set(hints.get("P301", ())) | set(hints.get("P2517", ()))
    candidates = []
    for qid in pool:
        item = info.get(qid)
        if item is None:
            continue
        aliases = {norm_label(a) for a in item["aliases"]}
        item = dict(item)
        item["label_match"] = norm_label(item["label"]) in variants or bool(
            aliases & variants)
        item["country_match"] = expected is not None and (
            expected in item["country_qids"])
        item["holder_share"] = shares.get(qid, 0.0)
        item["from_tally"] = qid in tally_qids
        item["from_category"] = qid in hint_qids
        item["main_topic"] = qid in main_topics
        item["from_search"] = qid in search_qids
        item["is_position"] = qid in offices or bool(item["holder_count"])
        candidates.append(item)

    # Transitive country agreement: a regional body carries the subdivision.
    if expected is not None:
        indirect = {
            q for c in candidates if not c["country_match"]
            for q in c["country_qids"]
        }
        if indirect:
            parents = {
                qid: set(claim_qids(e, "P17"))
                for qid, e in fetch_entities(
                    session, indirect, props="claims").items()
            }
            for c in candidates:
                if not c["country_match"]:
                    c["country_match"] = any(
                        expected in parents.get(q, set()) for q in c["country_qids"])

    candidates.sort(key=lambda c: (-c["holder_share"], not c["label_match"], c["qid"]))
    row = dict(row)
    row["category_qid"] = cat_entity["id"] if cat_entity else None
    row["category_lang"] = cat_lang
    row["language_mismatch"] = bool(cat_lang) and cat_lang != row["language"]
    row["category_hints"] = hints
    row["tally"] = tally
    row["candidates"] = candidates
    row["tail_status"], row["tail_qid"], row["duplicates"] = score(candidates)
    return row


def score(
    candidates: List[Dict[str, Any]]
) -> tuple[str, Optional[str], List[str]]:
    """Two agreeing signals promote a candidate; anything else is review.

    The signals are deliberately different in kind: what the office is
    *called* (label/alias variant), where it *belongs* (country agreement),
    what the category says it is *about* (P301 main topic), and who *holds*
    it (the P39 tally lead). Wikidata carries plenty of duplicate position
    items, so when the survivors are label-equal near-twins the one people's
    statements actually point at wins and the others are reported as merge
    candidates.
    """
    usable = [c for c in candidates if c["is_position"]]

    def strong_enough(c):
        # Country agreement and the tally lead are NOT independent: for a big
        # country every office matches the country, and regional deputies
        # overwhelmingly go on to hold the *national* seat, so that pair alone
        # matched "member of the State Duma" to four regional dumas. Require
        # either the name or the category's curated P301 to be one of the two.
        if c["label_match"]:
            return c["country_match"] or c["main_topic"] or c["from_tally"]
        if c["main_topic"]:
            return c["country_match"] or c["from_tally"]
        return False

    strong = [c for c in usable if strong_enough(c)]
    if len(strong) == 1:
        return "tail-matched", strong[0]["qid"], []
    if len(strong) > 1:
        labels = {norm_label(c["label"]) for c in strong}
        used = [c for c in strong if c["holder_share"] or c["holder_count"]]
        if len(labels) == 1 and len(used) == 1:
            return ("tail-matched", used[0]["qid"],
                    [c["qid"] for c in strong if c["qid"] != used[0]["qid"]])
        return "tail-ambiguous", None, []
    return "tail-unresolved", None, []


def render(rows: List[Dict[str, Any]]) -> str:
    by_status = Counter(r["tail_status"] for r in rows)
    md = [
        "# wd_categories positions — tail resolution",
        "",
        f"{len(rows)} rows the name search left ambiguous/unmatched: "
        f"{dict(by_status)}",
        "",
        "Signals per candidate: `L` label/alias variant match, `C` country "
        "agreement (P17/P1001, one hop up), `K` linked from the Wikipedia "
        "category item, `T` held by >= "
        f"{int(TALLY_MIN_SHARE * 100)}% of sampled category members.",
        "",
    ]
    for status in ("tail-matched", "tail-ambiguous", "tail-unresolved"):
        md.append(f"## {status}")
        for r in rows:
            if r["tail_status"] != status:
                continue
            tally = r["tally"]
            md.append("")
            md.append(
                f"### {r['position_name']} ({r['position_country']}) "
                f"— {r['language']}:{r['category']}")
            if r["tail_qid"]:
                md.append(f"→ **{r['tail_qid']}**"
                          + (f" (merge candidates: {', '.join(r['duplicates'])})"
                             if r["duplicates"] else ""))
            md.append(
                f"category item {r['category_qid']}, hints "
                f"{r['category_hints'] or '{}'}, "
                f"{tally.get('members', 0)} members "
                f"({tally.get('sampled', 0)} sampled)"
                + (f", PETScan {tally['error']}" if tally.get("error") else ""))
            if r["language_mismatch"]:
                md.append(
                    f"⚠ yml says `language: {r['language']}` but the category "
                    f"lives on {r['category_lang']}wiki — the crawler is "
                    f"querying the wrong wiki and this spec matches nobody.")
            elif r["category_qid"] is None:
                md.append("⚠ no Wikidata item found for the category page.")
            for c in r["candidates"][:6]:
                flags = "".join([
                    "L" if c["label_match"] else "-",
                    "C" if c["country_match"] else "-",
                    "K" if c["main_topic"] else ("k" if c["from_category"] else "-"),
                    "T" if c["from_tally"] else "-",
                ])
                extra = " ⚠list" if c["is_list"] else ""
                if not c["is_position"]:
                    extra += " ⚠not-a-position"
                md.append(
                    f"* [{flags}] {c['qid']} {c['label']} — "
                    f"{(c['description'] or '')[:110]} "
                    f"(share {c['holder_share']}, {c['holder_count']} P1308)"
                    f"{extra}")
        md.append("")
    return "\n".join(md) + "\n"


def rescore(out_name: str) -> None:
    """Re-apply score() to a finished run — the candidate evidence is all in
    the json, so tuning the rule costs no API calls."""
    path = OUT_DIR / f"{out_name}.json"
    rows = json.load(path.open())
    for row in rows:
        row["tail_status"], row["tail_qid"], row["duplicates"] = score(
            row["candidates"])
    path.write_text(json.dumps(rows, indent=1, ensure_ascii=False))
    (OUT_DIR / f"{out_name}.md").write_text(render(rows))
    print(dict(Counter(r["tail_status"] for r in rows)))


def main(argv: List[str]) -> None:
    if argv and argv[0].startswith("--rescore"):
        return rescore(argv[1] if len(argv) > 1 else "tail")
    rows = json.load((OUT_DIR / "positions.json").open())
    statuses, out_name = TAIL_STATUSES, "tail"
    if argv and argv[0].startswith("--statuses="):
        statuses = tuple(argv.pop(0).split("=", 1)[1].split(","))
        out_name = "_".join(statuses)
    keys = set(argv) or None
    tail = [
        r for r in rows
        if r["status"] in statuses and (keys is None or r["key"] in keys)
    ]
    session = make_session()
    out = []
    for i, row in enumerate(tail, 1):
        print(f"[{i}/{len(tail)}] {row['key']} — {row['position_name']}",
              file=sys.stderr)
        out.append(resolve_row(session, row))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"{out_name}.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False))
    (OUT_DIR / f"{out_name}.md").write_text(render(out))
    print(dict(Counter(r["tail_status"] for r in out)))


if __name__ == "__main__":
    main(sys.argv[1:])
