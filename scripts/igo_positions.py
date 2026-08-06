#!/usr/bin/env python
"""Census of positions at international bodies, and the registry seed / P2389
enrichment plan derived from it.

    python scripts/igo_positions.py

Two channels (see tasks/international_positions.md):

* **org-link channel** — WDQS: every P39-used position whose P2389/P361
  points at an org in the international-body class closures. This includes
  positions with junk P17 (FIFA president → Switzerland).
* **label channel** — over data/jurisdictions/bare_positions.json: positions
  with *no* org link whose label tail names an org found by the first
  channel. These are the P2389-addition candidates (the Interpol SG case).

Output: data/igo/igo_positions.json (raw), data/igo/igo_plan.md (registry
seed table + P2389 candidates for review), data/igo/igo_links.qs (additive
P2389 statements for the two-signal rows only).
"""

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.api import best_description, best_label, claim_qids, fetch_entities, sparql
from wd.http import REPO_ROOT, make_session

OUT_DIR = REPO_ROOT / "data" / "igo"
BARE_POSITIONS = REPO_ROOT / "data" / "jurisdictions" / "bare_positions.json"

# Class closures the org sweep matches against. Q484652 is deliberately the
# last and broadest: it drags in NGOs, sports bodies, historical leagues and
# the College of Cardinals — the census tags which class matched and the
# per-org review is the filter.
ORG_CLASSES = {
    "Q245065": "igo",  # intergovernmental organization
    "Q1262438": "court",  # international court
    "Q15925165": "un-agency",  # specialized agency of the United Nations
    "Q11422536": "sport",  # international sport governing body
    "Q484652": "intl-org",  # international organization (broad)
}

# Positions abolished before this never confer PEP status (zavod's
# POSITION_ABOLISHED_CUTOFF); orgs dissolved before it are excluded too.
CUTOFF_YEAR = 1990

UN_QID = "Q1065"
EU_QID = "Q458"

# States wander into the org sweep via classes like "member state of the
# United Nations" that sit inside the Q484652 closure; a country is never a
# registry org. (rigour territories cover the same ground, but P31 is enough
# here and saves the dependency.)
STATE_TYPES = {"Q3624078", "Q6256", "Q7275"}  # sovereign state, country, state
LIST_TYPE = "Q13406463"  # Wikimedia list article — not a position

# Auto P2389 rows are limited to offices that plausibly *direct* the org —
# that's what P2389 asserts. Judges, members, envoys and "Representative
# to X" accreditation posts go to review (P361 may fit them better).
HEAD_ROLES = (
    "secretary general",
    "secretary-general",
    "director general",
    "director-general",
    "president",
    "chairperson",
    "chairman",
    "chair",
    "managing director",
    "executive director",
    "high commissioner",
    "commissioner-general",
    "administrator",
    "head",
)

SWEEP_QUERY = """
SELECT ?org ?pos ?holders WHERE {{
  {{ SELECT ?pos (COUNT(DISTINCT ?p) AS ?holders) WHERE {{
       ?p wdt:P39 ?pos .
     }} GROUP BY ?pos }}
  ?pos wdt:P2389|wdt:P361 ?org .
  ?org wdt:P31/wdt:P279* wd:{cls} .
}}
"""


def patient_sparql(session, query: str, tries: int, wait: float) -> list[dict]:
    for attempt in range(tries):
        try:
            return sparql(session, query)
        except Exception as exc:
            print(f"  attempt {attempt + 1}/{tries} failed: {exc}", file=sys.stderr)
            if attempt + 1 < tries:
                time.sleep(wait)
    raise SystemExit("WDQS would not answer; try again later")


def first_year(entity: dict, prop: str) -> int | None:
    for claim in entity.get("claims", {}).get(prop, []):
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, dict) and "time" in value:
            if value.get("precision", 11) >= 9:
                try:
                    return int(value["time"].lstrip("+")[:4])
                except ValueError:
                    return None
    return None


def org_names(entity: dict) -> set[str]:
    """Label + all aliases, casefolded, for label-tail matching."""
    names: set[str] = set()
    label = best_label(entity)
    if label:
        names.add(label.casefold())
    for alias_list in entity.get("aliases", {}).values():
        for alias in alias_list:
            names.add(alias["value"].casefold())
    return names


def label_tails(label: str) -> list[str]:
    """Candidate org-name substrings of a position label.

    Conservative on purpose (substring matching is too loose — see the
    repo gotchas): the tail after ' of ' / ' at ', with a leading 'the '
    stripped, must equal an org name *exactly*. Both the first and last
    separator are tried — org names contain ' of ' themselves ("Council
    of Europe"), so a last-only split truncates them to "Europe"."""
    tails = []
    for sep in (" of ", " at "):
        for head, _, tail in (label.partition(sep), label.rpartition(sep)):
            if head and tail:
                tail = tail.strip().strip(",")
                if tail.casefold().startswith("the "):
                    tail = tail[4:]
                if tail and tail not in tails:
                    tails.append(tail)
    return tails


def is_head_role(label: str) -> bool:
    head = label.casefold().partition(" of ")[0]
    if any(mod in head for mod in ("assistant", "deputy", "vice", "under-")):
        return False
    return any(role in head for role in HEAD_ROLES)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tries", type=int, default=6)
    parser.add_argument("--wait", type=float, default=45.0)
    args = parser.parse_args()

    session = make_session()

    # --- Channel 1: org-link sweep -------------------------------------
    org_classes: dict[str, set[str]] = defaultdict(set)
    pos_orgs: dict[str, set[str]] = defaultdict(set)
    pos_holders: dict[str, int] = {}
    for cls, slug in ORG_CLASSES.items():
        print(f"sweep {slug} ({cls})…", file=sys.stderr)
        rows = patient_sparql(session, SWEEP_QUERY.format(cls=cls), args.tries, args.wait)
        print(f"  {len(rows)} rows", file=sys.stderr)
        for row in rows:
            org_classes[row["org"]].add(slug)
            pos_orgs[row["pos"]].add(row["org"])
            pos_holders[row["pos"]] = int(row["holders"])

    print(f"{len(org_classes)} orgs, {len(pos_orgs)} linked positions", file=sys.stderr)
    orgs = fetch_entities(session, sorted(org_classes))
    positions = fetch_entities(session, sorted(pos_orgs))

    org_rows = {}
    for qid, entity in orgs.items():
        if qid not in org_classes:
            continue  # redirect target fetched under a different id
        if STATE_TYPES.intersection(claim_qids(entity, "P31")):
            continue
        org_rows[qid] = {
            "qid": qid,
            "label": best_label(entity),
            "description": best_description(entity),
            "classes": sorted(org_classes[qid]),
            "dissolved": first_year(entity, "P576"),
            "un_system": qid == UN_QID
            or UN_QID in claim_qids(entity, "P361")
            or "un-agency" in org_classes[qid],
            "eu_hint": EU_QID in claim_qids(entity, "P361"),
            "names": sorted(org_names(entity)),
            "positions": [],
        }

    for qid, entity in positions.items():
        if qid not in pos_orgs:
            continue
        row = {
            "qid": qid,
            "label": best_label(entity),
            "description": best_description(entity),
            "holders": pos_holders.get(qid, 0),
            "abolished": first_year(entity, "P576"),
            "p17": claim_qids(entity, "P17"),
            "p1001": claim_qids(entity, "P1001"),
            "enwiki": (entity.get("sitelinks", {}).get("enwiki") or {}).get("title"),
        }
        for org_qid in pos_orgs[qid]:
            if org_qid in org_rows:
                org_rows[org_qid]["positions"].append(row)

    # --- Channel 2: label-tail candidates over the bare census ----------
    name_index: dict[str, set[str]] = defaultdict(set)
    for org in org_rows.values():
        if org["dissolved"] and org["dissolved"] < CUTOFF_YEAR:
            continue
        for name in org["names"]:
            name_index[name].add(org["qid"])

    candidates = []
    bare = json.loads(BARE_POSITIONS.read_text())
    for pos in bare:
        if pos["qid"] in pos_orgs:
            continue  # already linked
        if "P361" in pos["traversal_props"] or "P2389" in pos["traversal_props"]:
            continue  # has an org link, just not to a matched org
        if pos["abolished"] and int(pos["abolished"]) < CUTOFF_YEAR:
            continue
        if any(t["qid"] == LIST_TYPE for t in pos["instance_of"]):
            continue
        label = pos["label"] or ""
        matched: set[str] = set()
        for tail in label_tails(label):
            matched.update(name_index.get(tail.casefold(), set()))
        if not matched:
            continue
        # Second, independent-ish signal: the org is named in the position's
        # description or enwiki title as well as the label.
        context = f"{pos['description'] or ''} {pos['enwiki'] or ''}".casefold()
        confirmed = {
            qid
            for qid in matched
            if any(name in context for name in org_rows[qid]["names"] if len(name) > 3)
        }
        # Accreditation posts ("Permanent Representative to X") are directed
        # at the org, they don't direct it — P2389 would be wrong.
        diplomatic = " to " in label.casefold()
        candidates.append(
            {
                "qid": pos["qid"],
                "label": label,
                "description": pos["description"],
                "holders": pos["holders"],
                "orgs": sorted(matched),
                "confirmed": sorted(confirmed),
                "auto": len(matched) == 1
                and matched == confirmed
                and not diplomatic
                and is_head_role(label),
            }
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = OUT_DIR / "igo_positions.json"
    raw_path.write_text(
        json.dumps(
            {"orgs": sorted(org_rows.values(), key=lambda o: o["qid"]),
             "link_candidates": candidates},
            indent=2,
            ensure_ascii=False,
        )
    )
    print(f"Wrote {raw_path}", file=sys.stderr)

    render(org_rows, candidates)


def render(org_rows: dict, candidates: list[dict]) -> None:
    active, historical = [], []
    for org in org_rows.values():
        org["total_holders"] = sum(p["holders"] for p in org["positions"])
        org["positions"].sort(key=lambda p: -p["holders"])
        if org["dissolved"] and org["dissolved"] < CUTOFF_YEAR:
            historical.append(org)
        else:
            active.append(org)
    active.sort(key=lambda o: -o["total_holders"])

    # User call (2026-08-05): the Bretton Woods institutions are global
    # bodies, not UN-system for country-code purposes.
    code_overrides = {"Q7804": "zz", "Q320863": "zz"}  # IMF, World Bank Group

    def code(org: dict) -> str:
        if org["qid"] in code_overrides:
            return code_overrides[org["qid"]]
        if org["un_system"]:
            return "un"
        if org["eu_hint"]:
            return "eu?"
        return "zz"

    def topics(org: dict) -> str:
        return "poi (sports)" if "sport" in org["classes"] else "gov.igo"

    lines = [
        "# International-body positions: registry seed + P2389 plan",
        "",
        "Generated by `scripts/igo_positions.py`. Review the registry table",
        "(which orgs belong in zavod's `igo.py`, and their country code /",
        "topics), then the P2389 addition candidates. `igo_links.qs` holds",
        "only the auto rows (single org match + description/enwiki",
        "confirmation). Everything else stays here for review.",
        "",
        "## Registry seed (active orgs, by total P39 holders)",
        "",
        "| org | label | classes | positions | holders | code | topics |",
        "|---|---|---|---|---|---|---|",
    ]
    for org in active:
        lines.append(
            f"| {org['qid']} | {org['label']} | {', '.join(org['classes'])} "
            f"| {len(org['positions'])} | {org['total_holders']} "
            f"| {code(org)} | {topics(org)} |"
        )

    lines += ["", "## Positions per org (top 3 shown, with P17 junk flagged)", ""]
    for org in active:
        if not org["positions"]:
            continue
        lines.append(f"### {org['qid']} {org['label']}")
        lines.append("")
        for pos in org["positions"][:3]:
            p17 = f" — P17 junk: {', '.join(pos['p17'])}" if pos["p17"] else ""
            lines.append(
                f"* {pos['qid']} {pos['label']} ({pos['holders']} holders){p17}"
            )
        rest = len(org["positions"]) - 3
        if rest > 0:
            lines.append(f"* … {rest} more")
        lines.append("")

    auto = [c for c in candidates if c["auto"]]
    review = [c for c in candidates if not c["auto"]]
    auto.sort(key=lambda c: -c["holders"])
    review.sort(key=lambda c: -c["holders"])

    lines += [
        "## P2389 additions — auto (label tail + description/enwiki agree)",
        "",
    ]
    for c in auto:
        org = c["orgs"][0]
        lines.append(
            f"* {c['qid']} “{c['label']}” ({c['holders']} holders) "
            f"→ P2389 {org} {org_rows[org]['label']}"
        )
    lines += ["", "## P2389 additions — review (ambiguous or single-signal)", ""]
    for c in review:
        orgs = ", ".join(f"{q} {org_rows[q]['label']}" for q in c["orgs"])
        lines.append(
            f"* {c['qid']} “{c['label']}” ({c['holders']} holders) — "
            f"candidates: {orgs} — desc: {c['description'] or '—'}"
        )

    if historical:
        lines += ["", "## Excluded: orgs dissolved before 1990", ""]
        for org in sorted(historical, key=lambda o: -o["total_holders"]):
            lines.append(
                f"* {org['qid']} {org['label']} (dissolved {org['dissolved']}, "
                f"{org['total_holders']} holders)"
            )

    plan_path = OUT_DIR / "igo_plan.md"
    plan_path.write_text("\n".join(lines) + "\n")
    print(f"Wrote {plan_path}", file=sys.stderr)

    qs_lines = [f"{c['qid']}|P2389|{c['orgs'][0]}" for c in auto]
    qs_path = OUT_DIR / "igo_links.qs"
    qs_path.write_text("\n".join(qs_lines) + "\n")
    print(f"Wrote {qs_path} ({len(qs_lines)} statements)", file=sys.stderr)


if __name__ == "__main__":
    main()
