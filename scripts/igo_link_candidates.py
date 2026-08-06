#!/usr/bin/env python
"""Second-pass hunt for positions that should link to zavod's IGO registry.

    python scripts/igo_link_candidates.py

The first pass (`igo_positions.py`) only label-matched over
`bare_positions.json` — positions with *no* P17/P1001 at all. That misses
the FIFA-shaped cases: positions carrying junk HQ countries or the org
itself as jurisdiction. This pass hunts against the full item universe,
keyed on the registry orgs in zavod's `igo.py`, via four channels:

* **search** — CirrusSearch `inlabel:"<org name>"` per registry-org name;
  candidates are gated on real P39/P1308 use and label-tail matching.
* **jurisdiction** — WDQS: in-use positions whose P1001/P17 points AT a
  registry org (org-as-jurisdiction junk) but that lack any org link.
* **employer** — WDQS: positions held by people with P108 = registry org;
  corroboration only, never sufficient alone.
* **sub-orgs** — positions linked to a non-registry org that is P361-part
  of a registry org: reported as registry *expansion* suggestions.

Auto rows need two independent signals (exact single-org label tail + one
of context/jurisdiction/employer agreeing on the same org) and follow the
measured convention: head roles → P2389, other offices → P361. One `.qs`
per property (single-concern batches).

Output: data/igo/igo_link_candidates.json, igo_links2_plan.md,
igo_links2_p2389.qs, igo_links2_p361.qs.
"""

import argparse
import json
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from igo_positions import CUTOFF_YEAR, first_year, is_head_role, label_tails
from wd.api import WD_API, best_description, best_label, claim_qids, fetch_entities, sparql
from wd.http import REPO_ROOT, get_text, make_session

OUT_DIR = REPO_ROOT / "data" / "igo"

# The zavod registry is the source of truth for which orgs matter; read it
# from the working tree once PR #5313 merges, from the branch until then.
ZAVOD_REPO = Path("/Users/pudo/Code/opensanctions")
IGO_PATH = "zavod/zavod/shed/wikidata/igo.py"
IGO_BRANCH = "pudo/wd-igo-positions"

LIST_TYPE = "Q13406463"  # Wikimedia list article
HUMAN_TYPE = "Q5"

# Search caps: relevance ranking front-loads label matches, so the tail we
# drop is mostly articles/albums, but log every truncation (no silent caps).
MAX_HITS_PER_PHRASE = 200
SEARCH_PAGE = 50
# Names shorter than this are skipped for search AND matching: 2-3 letter
# acronyms ("EU", "OAS") collide with unrelated label tails.
MIN_NAME_LEN = 4

VALUES_CHUNK = 120  # stay under the ~150-item GET/URI ceiling

NAME_LANGS = ("en", "mul")


def org_en_names(entity: dict) -> set[str]:
    """en/mul label + aliases, casefolded. All-language aliases (the first
    pass's org_names) explode into hundreds of search phrases for the UN;
    en/mul is what our tail matching reads anyway."""
    names: set[str] = set()
    for lang in NAME_LANGS:
        label = entity.get("labels", {}).get(lang)
        if label:
            names.add(label["value"].casefold())
        for alias in entity.get("aliases", {}).get(lang, []):
            names.add(alias["value"].casefold())
    return names


def registry_qids() -> list[str]:
    """Org QIDs from zavod's igo.py — dict keys only, in file order."""
    path = ZAVOD_REPO / IGO_PATH
    if path.exists():
        text = path.read_text()
    else:
        text = subprocess.run(
            ["git", "-C", str(ZAVOD_REPO), "show", f"{IGO_BRANCH}:{IGO_PATH}"],
            capture_output=True, text=True, check=True,
        ).stdout
    import re

    return list(dict.fromkeys(re.findall(r'"(Q\d+)": IntlOrg', text)))


def patient_sparql(session, query: str, tries: int = 6, wait: float = 45.0) -> list[dict]:
    for attempt in range(tries):
        try:
            return sparql(session, query)
        except Exception as exc:
            print(f"  attempt {attempt + 1}/{tries} failed: {exc}", file=sys.stderr)
            if attempt + 1 < tries:
                time.sleep(wait)
    raise SystemExit("WDQS would not answer; try again later")


def search_inlabel(session, phrase: str) -> tuple[list[str], int]:
    """QIDs of items whose label/alias (any language) contains the phrase."""
    hits: list[str] = []
    offset = 0
    total = 0
    while offset < MAX_HITS_PER_PHRASE:
        params = {
            "format": "json", "action": "query", "list": "search",
            "srsearch": f'inlabel:"{phrase}"', "srnamespace": "0",
            "srlimit": str(SEARCH_PAGE), "sroffset": str(offset),
        }
        data = json.loads(get_text(session, WD_API, params=params))
        total = data.get("query", {}).get("searchinfo", {}).get("totalhits", 0)
        batch = [h["title"] for h in data.get("query", {}).get("search", [])]
        hits.extend(h for h in batch if h.startswith("Q"))
        if "continue" not in data or not batch:
            break
        offset += SEARCH_PAGE
    return hits, total


def chunked_position_evidence(session, qids: list[str]) -> tuple[dict[str, int], set[str]]:
    """P39 holder counts and P1308-officeholder flags, VALUES-chunked."""
    holders: dict[str, int] = {}
    officeholder: set[str] = set()
    todo = sorted(qids)
    for i in range(0, len(todo), VALUES_CHUNK):
        chunk = todo[i : i + VALUES_CHUNK]
        values = " ".join(f"wd:{q}" for q in chunk)
        rows = patient_sparql(session, f"""
        SELECT ?pos (COUNT(DISTINCT ?p) AS ?n) WHERE {{
          VALUES ?pos {{ {values} }} ?p wdt:P39 ?pos .
        }} GROUP BY ?pos
        """)
        for row in rows:
            holders[row["pos"]] = int(row["n"])
        rows = patient_sparql(session, f"""
        SELECT DISTINCT ?pos WHERE {{
          VALUES ?pos {{ {values} }} ?pos wdt:P1308 [] .
        }}
        """)
        officeholder.update(row["pos"] for row in rows)
        print(f"  evidence {i + len(chunk)}/{len(todo)}", file=sys.stderr)
    return holders, officeholder


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tries", type=int, default=6)
    parser.add_argument("--wait", type=float, default=45.0)
    args = parser.parse_args()

    session = make_session()
    org_qids = registry_qids()
    print(f"{len(org_qids)} registry orgs", file=sys.stderr)
    orgs = fetch_entities(session, org_qids)
    values = " ".join(f"wd:{q}" for q in org_qids)

    # Names per org: all-language labels + aliases for matching; the search
    # phrases are the same set (inlabel matches any language, but only for
    # strings we actually query — translated names we don't know stay dark).
    names_by_org: dict[str, set[str]] = {}
    name_index: dict[str, set[str]] = defaultdict(set)
    for qid in org_qids:
        entity = orgs.get(qid)
        if entity is None:
            continue
        names = {n for n in org_en_names(entity) if len(n) >= MIN_NAME_LEN}
        names_by_org[qid] = names
        for name in names:
            name_index[name].add(qid)

    # --- Channel: jurisdiction (P1001/P17 pointing at a registry org) ---
    print("jurisdiction channel…", file=sys.stderr)
    juris_hits: dict[str, set[str]] = defaultdict(set)
    rows = patient_sparql(session, f"""
    SELECT DISTINCT ?pos ?org WHERE {{
      ?pos wdt:P1001|wdt:P17 ?org .
      VALUES ?org {{ {values} }}
      FILTER NOT EXISTS {{ ?pos wdt:P2389 [] }}
      FILTER NOT EXISTS {{ ?pos wdt:P361 [] }}
      {{ ?h wdt:P39 ?pos . ?h wdt:P31 wd:Q5 . }} UNION {{ ?pos wdt:P1308 [] }}
    }}
    """, args.tries, args.wait)
    for row in rows:
        juris_hits[row["pos"]].add(row["org"])
    print(f"  {len(juris_hits)} positions", file=sys.stderr)

    # --- Channel: employer (P108 holders; corroboration only) -----------
    print("employer channel…", file=sys.stderr)
    employer_hits: dict[str, dict[str, int]] = defaultdict(dict)
    rows = patient_sparql(session, f"""
    SELECT ?pos ?org (COUNT(DISTINCT ?h) AS ?n) WHERE {{
      ?h wdt:P108 ?org .
      VALUES ?org {{ {values} }}
      ?h wdt:P39 ?pos .
      FILTER NOT EXISTS {{ ?pos wdt:P2389 [] }}
      FILTER NOT EXISTS {{ ?pos wdt:P361 [] }}
    }} GROUP BY ?pos ?org
    """, args.tries, args.wait)
    for row in rows:
        employer_hits[row["pos"]][row["org"]] = int(row["n"])
    print(f"  {len(employer_hits)} positions", file=sys.stderr)

    # --- Channel: sub-orgs (registry expansion suggestions) -------------
    print("sub-org channel…", file=sys.stderr)
    suborg_rows = patient_sparql(session, f"""
    SELECT DISTINCT ?pos ?suborg ?parent WHERE {{
      ?pos wdt:P2389|wdt:P361 ?suborg .
      ?suborg wdt:P361 ?parent .
      VALUES ?parent {{ {values} }}
      FILTER(?suborg NOT IN ({", ".join(f"wd:{q}" for q in org_qids)}))
      {{ ?h wdt:P39 ?pos . ?h wdt:P31 wd:Q5 . }} UNION {{ ?pos wdt:P1308 [] }}
    }}
    """, args.tries, args.wait)
    suborg_positions: dict[str, set[str]] = defaultdict(set)
    suborg_parent: dict[str, str] = {}
    for row in suborg_rows:
        suborg_positions[row["suborg"]].add(row["pos"])
        suborg_parent[row["suborg"]] = row["parent"]
    print(f"  {len(suborg_positions)} sub-orgs", file=sys.stderr)

    # --- Convention check: how existing links split by role shape -------
    convention = {"P2389": {"head": 0, "other": 0}, "P361": {"head": 0, "other": 0}}
    linked_qids: set[str] = set()
    linked_by_prop: dict[str, set[str]] = {}
    for prop in ("P2389", "P361"):
        rows = patient_sparql(session, f"""
        SELECT DISTINCT ?pos WHERE {{ ?pos wdt:{prop} ?org . VALUES ?org {{ {values} }} }}
        """, args.tries, args.wait)
        linked_by_prop[prop] = {row["pos"] for row in rows}
        linked_qids.update(linked_by_prop[prop])
    linked_entities = fetch_entities(session, sorted(linked_qids), props="labels")
    for prop, qids in linked_by_prop.items():
        for qid in qids:
            entity = linked_entities.get(qid)
            label = best_label(entity) if entity else None
            if label:
                convention[prop]["head" if is_head_role(label) else "other"] += 1

    # --- Channel: label search ------------------------------------------
    print("search channel…", file=sys.stderr)
    search_hits: dict[str, set[str]] = defaultdict(set)  # candidate → orgs whose name hit
    truncated: list[tuple[str, str, int]] = []
    phrases = sorted({(name, qid) for qid, names in names_by_org.items() for name in names})
    for idx, (phrase, org_qid) in enumerate(phrases):
        hits, total = search_inlabel(session, phrase)
        if total > MAX_HITS_PER_PHRASE:
            truncated.append((phrase, org_qid, total))
        for hit in hits:
            search_hits[hit].add(org_qid)
        if idx % 50 == 0:
            print(f"  searched {idx}/{len(phrases)} phrases", file=sys.stderr)
    print(f"  {len(search_hits)} raw hits, {len(truncated)} truncated phrases",
          file=sys.stderr)

    # --- Merge candidates, gate on position evidence --------------------
    candidate_qids = (set(search_hits) | set(juris_hits) | set(employer_hits))
    candidate_qids.difference_update(org_qids)
    candidate_qids.difference_update(linked_qids)
    print(f"{len(candidate_qids)} merged candidates; fetching…", file=sys.stderr)
    entities = fetch_entities(session, sorted(candidate_qids))

    plausible: dict[str, dict] = {}
    for qid, entity in entities.items():
        if qid not in candidate_qids:
            continue  # redirect target
        types = set(claim_qids(entity, "P31"))
        if HUMAN_TYPE in types:
            continue
        if types == {LIST_TYPE}:
            continue
        if claim_qids(entity, "P2389") or claim_qids(entity, "P361"):
            continue  # linked since the sweep (or to a non-registry org)
        abolished = first_year(entity, "P576")
        if abolished and abolished < CUTOFF_YEAR:
            continue
        plausible[qid] = entity

    holders, officeholder = chunked_position_evidence(session, list(plausible))
    used = {q for q in plausible if holders.get(q, 0) > 0 or q in officeholder}
    print(f"{len(plausible)} plausible → {len(used)} in actual P39/P1308 use",
          file=sys.stderr)

    candidates = []
    for qid in sorted(used):
        entity = plausible[qid]
        label = best_label(entity) or ""
        en_names = [label]
        for lang in NAME_LANGS:
            for alias in entity.get("aliases", {}).get(lang, []):
                en_names.append(alias["value"])
        # Tail matching with a specificity guard: when nested tails both
        # match ("Parliamentary Assembly of the Council of Europe" and
        # "Council of Europe"), only the most specific org counts; when the
        # longer tail names an org we DON'T know ("Council of the European
        # Union" vs "European Union"), linking the shorter match would tie
        # the position to the wrong body — flag it and keep it out of auto.
        tail_orgs: set[str] = set()
        specific_unmatched: set[str] = set()
        for name in en_names:
            tails = sorted(label_tails(name), key=len, reverse=True)
            matched_tails: list[str] = []
            for tail in tails:
                if any(tail.casefold() in m.casefold() for m in matched_tails):
                    continue  # nested inside an already-matched longer tail
                orgs_for_tail = name_index.get(tail.casefold(), set())
                if orgs_for_tail:
                    matched_tails.append(tail)
                    tail_orgs.update(orgs_for_tail)
            if matched_tails and tails:
                longest = tails[0]
                if (
                    longest not in matched_tails
                    and any(m.casefold() in longest.casefold() for m in matched_tails)
                    and longest.casefold()
                    not in {s.casefold() for s in specific_unmatched}
                ):
                    specific_unmatched.add(longest)
        # Non-English labels ("Presidente de la Interpol") never tail-match;
        # an org name sitting inside any label keeps the item for review.
        substring_orgs = {
            org
            for org in search_hits.get(qid, set())
            if any(n in label.casefold() for n in names_by_org.get(org, set()))
        } - tail_orgs
        context = f"{best_description(entity) or ''} " \
                  f"{(entity.get('sitelinks', {}).get('enwiki') or {}).get('title', '')}".casefold()
        context_orgs = {
            org for org in (tail_orgs | search_hits.get(qid, set()))
            if any(n in context for n in names_by_org.get(org, set()))
        }
        signals = {
            "tail": sorted(tail_orgs),
            "substring": sorted(substring_orgs),
            "context": sorted(context_orgs),
            "jurisdiction": sorted(juris_hits.get(qid, set())),
            "employer": employer_hits.get(qid, {}),
        }
        all_orgs = (
            tail_orgs | substring_orgs
            | set(signals["jurisdiction"]) | set(signals["employer"])
        )
        if not all_orgs:
            continue  # search hit with no structural or tail tie — noise
        # An employer-only tie is corpus noise unless the org's staff make
        # up the bulk of the holders ("director": 40 of 8072 holders once
        # worked at some registry org; SRSG Kosovo: 9 of 9 are UN staff).
        n_employed = sum(signals["employer"].values())
        if not (tail_orgs or substring_orgs or signals["jurisdiction"]):
            if n_employed < 3 or n_employed < 0.5 * max(holders.get(qid, 0), 1):
                continue
        corroborated = (
            set(context_orgs) | set(signals["jurisdiction"]) | set(signals["employer"])
        )
        diplomatic = " to " in label.casefold()
        head = is_head_role(label)
        auto = (
            len(tail_orgs) == 1
            and next(iter(tail_orgs)) in corroborated
            and not diplomatic
            and not specific_unmatched
        )
        candidates.append({
            "qid": qid,
            "label": label,
            "description": best_description(entity),
            "holders": holders.get(qid, 0),
            "head_role": head,
            "diplomatic": diplomatic,
            "signals": signals,
            "orgs": sorted(all_orgs),
            "specific_unmatched": sorted(specific_unmatched),
            "auto": auto,
            "property": "P2389" if head else "P361",
        })

    # --- Sub-org report ---------------------------------------------------
    suborg_entities = fetch_entities(session, sorted(suborg_positions), props="labels|descriptions")
    suborg_report = []
    for sub, positions in sorted(suborg_positions.items(), key=lambda kv: -len(kv[1])):
        entity = suborg_entities.get(sub)
        suborg_report.append({
            "qid": sub,
            "label": best_label(entity) if entity else None,
            "description": best_description(entity) if entity else None,
            "parent": suborg_parent[sub],
            "parent_label": best_label(orgs[suborg_parent[sub]]) if suborg_parent[sub] in orgs else None,
            "positions": len(positions),
            "examples": sorted(positions)[:5],
        })

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = OUT_DIR / "igo_link_candidates.json"
    raw_path.write_text(json.dumps({
        "candidates": candidates,
        "suborgs": suborg_report,
        "convention": convention,
        "truncated_searches": [
            {"phrase": p, "org": o, "totalhits": t} for p, o, t in truncated
        ],
    }, indent=2, ensure_ascii=False))
    print(f"Wrote {raw_path}", file=sys.stderr)

    render(candidates, suborg_report, convention, truncated,
           {q: best_label(e) for q, e in orgs.items()})


def render(candidates, suborg_report, convention, truncated, org_labels) -> None:
    auto = sorted((c for c in candidates if c["auto"]), key=lambda c: -c["holders"])
    review = sorted((c for c in candidates if not c["auto"]), key=lambda c: -c["holders"])

    def org_ref(qid: str) -> str:
        return f"{qid} {org_labels.get(qid) or '?'}"

    def signal_note(c: dict) -> str:
        bits = []
        if c["signals"]["tail"]:
            bits.append("label tail")
        elif c["signals"]["substring"]:
            bits.append("label substring")
        if c["signals"]["context"]:
            bits.append("context")
        if c["signals"]["jurisdiction"]:
            bits.append("P1001/P17→org")
        if c["signals"]["employer"]:
            n = sum(c["signals"]["employer"].values())
            bits.append(f"{n} holder(s) employed")
        return ", ".join(bits) or "structural only"

    lines = [
        "# IGO org-link candidates, second pass",
        "",
        "Generated by `scripts/igo_link_candidates.py`. Hunts the full item",
        "universe (CirrusSearch labels + jurisdiction-junk + holder-employer)",
        "for positions that should link to a zavod-registry org. Auto rows",
        "carry two independent signals; head roles get P2389, other offices",
        "P361, per the measured convention below.",
        "",
        "## Existing link convention (registry-linked positions)",
        "",
        f"* P2389 (directed by office): {convention['P2389']['head']} head-role, "
        f"{convention['P2389']['other']} other",
        f"* P361 (part of): {convention['P361']['head']} head-role, "
        f"{convention['P361']['other']} other",
        "",
        f"## Auto additions ({len(auto)}; two agreeing signals)",
        "",
    ]
    for c in auto:
        org = c["signals"]["tail"][0]
        lines.append(
            f"* {c['qid']} “{c['label']}” ({c['holders']} holders) → "
            f"{c['property']} {org_ref(org)} [{signal_note(c)}]"
        )

    lines += ["", f"## Review ({len(review)}; single-signal, multi-org or diplomatic)", ""]
    unmatched_names: dict[str, int] = {}
    for c in review:
        orgs_txt = ", ".join(org_ref(q) for q in c["orgs"])
        flags = " DIPLOMATIC" if c["diplomatic"] else ""
        if c["specific_unmatched"]:
            flags += f" UNREGISTERED-ORG: {'; '.join(c['specific_unmatched'])}"
            for name in c["specific_unmatched"]:
                unmatched_names[name] = unmatched_names.get(name, 0) + c["holders"]
        lines.append(
            f"* {c['qid']} “{c['label']}” ({c['holders']} holders) — "
            f"{orgs_txt} [{signal_note(c)}]{flags} — desc: {c['description'] or '—'}"
        )

    if unmatched_names:
        lines += [
            "",
            "## Unregistered specific orgs (label names a body inside a registry",
            "org — registry and/or Wikidata-link expansion leads, by holders)",
            "",
        ]
        for name, n in sorted(unmatched_names.items(), key=lambda kv: -kv[1]):
            lines.append(f"* “{name}” ({n} holders)")

    lines += ["", "## Registry expansion suggestions (sub-orgs with linked positions)", ""]
    for s in suborg_report:
        lines.append(
            f"* {s['qid']} {s['label']} (part of {s['parent']} {s['parent_label']}) — "
            f"{s['positions']} linked positions — desc: {s['description'] or '—'}"
        )

    if truncated:
        lines += ["", "## Truncated searches (coverage gaps — hits beyond the cap unseen)", ""]
        for phrase, org_qid, total in sorted(truncated, key=lambda t: -t[2]):
            lines.append(f"* “{phrase}” ({org_ref(org_qid)}): {total} total hits")

    plan_path = OUT_DIR / "igo_links2_plan.md"
    plan_path.write_text("\n".join(lines) + "\n")
    print(f"Wrote {plan_path}", file=sys.stderr)

    for prop in ("P2389", "P361"):
        rows = [c for c in auto if c["property"] == prop]
        qs_path = OUT_DIR / f"igo_links2_{prop.lower()}.qs"
        qs_path.write_text(
            "\n".join(f"{c['qid']}|{prop}|{c['signals']['tail'][0]}" for c in rows) + "\n"
        )
        print(f"Wrote {qs_path} ({len(rows)} statements)", file=sys.stderr)


if __name__ == "__main__":
    main()
