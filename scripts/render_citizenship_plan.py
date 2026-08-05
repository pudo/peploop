#!/usr/bin/env python
"""Render the citizenship-inference verdicts into a conservative edit plan.

    python scripts/render_citizenship_plan.py

Reads data/jurisdictions/verdicts/citizen_*.jsonl and writes:
  data/jurisdictions/citizenship_plan.md  - full breakdown for human review
  data/jurisdictions/citizenship_plan.qs  - additive P1001/P17 statements

A row only reaches the .qs when every gate passes:
  * verdict fix-current at high confidence, kind is an actual office
    (diplomatic / generic-occupation / academy-or-award / list-or-class are
    excluded no matter the confidence);
  * two independent signals agree: the classifier's country must match the
    holder-citizenship majority that generated the candidate;
  * a subnational jurisdiction QID is only used after mechanical
    verification (its own P17 matches the country AND one of its labels
    appears in the position label) — otherwise the row goes to review;
  * subnational/municipal offices without a verified entity QID go to
    review rather than getting a country-level P1001.
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.api import best_label, fetch_entities
from wd.http import REPO_ROOT, make_session

BASE = REPO_ROOT / "data" / "jurisdictions"
EXCLUDED_KINDS = {"diplomatic", "generic-occupation", "academy-or-award",
                  "list-or-class"}
SUBNATIONAL_KINDS = {"subnational", "municipal"}
# Church offices: the classifiers split on whether a vicariate "applies to"
# the state (chunk 10/11 said France, chunk 07 skipped bishoprics as
# diocese-scoped). Convention unsettled → review, never auto.
REVIEW_KINDS = {"religious"}
# Party-internal offices: most chunks skipped them per precedent, one chunk
# asserted devolved-party leaderships. Same unsettled-convention treatment.
PARTY_RE = re.compile(r"\b(part(?:y|ido|it|ija|ei)|labour|democrats)\b", re.I)


def current_p17(entity: dict) -> str | None:
    claims = [
        c for c in entity.get("claims", {}).get("P17", [])
        if c.get("rank") != "deprecated"
        and "id" in c.get("mainsnak", {}).get("datavalue", {}).get("value", {})
    ]
    preferred = [c for c in claims if c.get("rank") == "preferred"]
    current = [c for c in claims if "P582" not in c.get("qualifiers", {})]
    for pool in (preferred, current, claims):
        values = {c["mainsnak"]["datavalue"]["value"]["id"] for c in pool}
        if len(values) == 1:
            return values.pop()
    return None


def entity_names(entity: dict) -> set[str]:
    names = set()
    for obj in entity.get("labels", {}).values():
        names.add(obj["value"].casefold())
    for alias_list in entity.get("aliases", {}).values():
        for obj in alias_list:
            names.add(obj["value"].casefold())
    return names


def verify_jurisdictions(session, rows: list[dict]) -> dict[str, bool]:
    """Mechanically check agent-supplied subnational QIDs: the entity's own
    country must match the verdict's country, and one of its names must
    actually occur in the position label (guards against hallucinated or
    mistyped QIDs)."""
    qids = {v["jurisdiction_qid"] for v in rows}
    entities = fetch_entities(session, qids, props="labels|aliases|claims")
    ok: dict[str, bool] = {}
    for v in rows:
        entity = entities.get(v["jurisdiction_qid"])
        if entity is None:
            ok[v["qid"]] = False
            continue
        label = v["label"].casefold()
        named = any(
            name and len(name) >= 3 and name in label
            for name in entity_names(entity)
        )
        ok[v["qid"]] = named and current_p17(entity) == v["country_qid"]
    return ok


def admin_index(session, country_qid: str) -> list[tuple[set[str], str]]:
    """Names of a country's first-level subdivisions (its own P150 targets),
    for matching region names inside position labels."""
    country = fetch_entities(session, [country_qid], props="claims").get(country_qid)
    if country is None:
        return []
    targets = [
        c["mainsnak"]["datavalue"]["value"]["id"]
        for c in country.get("claims", {}).get("P150", [])
        if c.get("rank") != "deprecated"
        and "id" in c.get("mainsnak", {}).get("datavalue", {}).get("value", {})
    ]
    index = []
    for qid, entity in fetch_entities(session, targets, props="labels|aliases").items():
        names = {n for n in entity_names(entity) if len(n) >= 4}
        if names:
            index.append((names, (best_label(entity) or "").casefold(), qid))
    return index


TAIL_RE = re.compile(
    r".*(?:\bof\b|\bde\b|\bdu\b|\bdes\b|\bdel\b|\bin\b|\bd')\s*", re.I)
ARTICLE_RE = re.compile(r"^(?:the|la|le|les|l'|el|los)\s+", re.I)


def label_tail(label: str) -> str | None:
    """The entity name after the label's last preposition ("member of the
    X Oblast Duma" won't parse; "Duma of the Astrakhan Region" → "astrakhan
    region"). Substring matching proved too loose (alias "Loire" fired
    inside "Indre-et-Loire", "the North" hit the North Riding), so only this
    tail is compared — and only for exact name equality."""
    m = TAIL_RE.match(label)
    if m is None:
        return None
    tail = label[m.end():].strip().strip(".,;:()")
    tail = ARTICLE_RE.sub("", tail)
    return tail.casefold() or None


def match_admin(index: list[tuple[set[str], str, str]], label: str) -> str | None:
    """The subdivision one of whose names IS the label's tail — unambiguous
    matches only. A bare-eponym alias of a suffixed subdivision ("Gombe" for
    "Gombe State", "Mandalay" for "Mandalay Region") is rejected: those
    labels name the city/traditional polity, not the subdivision."""
    tail = label_tail(label)
    if tail is None:
        return None
    found = {
        qid
        for names, primary, qid in index
        if tail in names and not primary.startswith(tail + " ")
    }
    return found.pop() if len(found) == 1 else None


def main() -> None:
    verdicts = []
    for path in sorted(BASE.glob("verdicts/citizen_*.jsonl")):
        for line in path.read_text().splitlines():
            if line.strip():
                verdicts.append(json.loads(line))

    candidates = {
        c["qid"]: c
        for c in json.loads((BASE / "citizenship_candidates.json").read_text())
    }
    for v in verdicts:
        cand = candidates.get(v["qid"], {})
        v["holders"] = cand.get("holders", 0)
        v["prior"] = cand.get("top")

    session = make_session()

    def prior_agrees(v: dict) -> bool:
        prior = v.get("prior") or {}
        return v.get("country_qid") == prior.get("qid") or (
            v.get("country_code") is not None
            and v.get("country_code") == prior.get("code")
        )

    fix_current = [v for v in verdicts if v["verdict"] == "fix-current"]
    eligible, excluded_kind, kind_review, low_conf, disagree = [], [], [], [], []
    for v in fix_current:
        kind = v.get("kind") or "other"
        if kind in EXCLUDED_KINDS:
            excluded_kind.append(v)
        elif kind in REVIEW_KINDS or PARTY_RE.search(v["label"]):
            kind_review.append(v)
        elif v.get("confidence") != "high":
            low_conf.append(v)
        elif not prior_agrees(v):
            disagree.append(v)
        else:
            eligible.append(v)

    # Verify agent-supplied subnational entity QIDs in one batch:
    with_juris = [
        v for v in eligible
        if v.get("jurisdiction_qid") and v["jurisdiction_qid"] != v["country_qid"]
    ]
    juris_ok = verify_jurisdictions(session, with_juris) if with_juris else {}

    admin_cache: dict[str, list[tuple[set[str], str]]] = {}
    auto, subnational_review = [], []
    qs: list[str] = []
    seen: set[tuple[str, str]] = set()
    for v in eligible:
        kind = v.get("kind") or "other"
        juris = v.get("jurisdiction_qid")
        if juris and juris != v["country_qid"]:
            if juris_ok.get(v["qid"]):
                v["target"] = juris
                v["via"] = "verified-subnational"
            else:
                subnational_review.append(v)
                continue
        elif kind == "subnational":
            # A country-level P1001 on a regional office is sloppy; try to
            # pin the region mechanically: the country's own P150 subdivision
            # whose name is the label's tail. Municipal offices never get
            # this treatment — a first-level subdivision is the wrong
            # granularity for a city office.
            country = v.get("country_qid") or ""
            if country not in admin_cache:
                admin_cache[country] = admin_index(session, country) if country else []
            matched = match_admin(admin_cache[country], v["label"].casefold())
            if matched is None:
                subnational_review.append(v)
                continue
            v["target"] = matched
            v["via"] = "label-matched subnational"
        elif kind in SUBNATIONAL_KINDS:
            subnational_review.append(v)
            continue
        else:
            v["target"] = v["country_qid"]
            v["via"] = "country"
        # P17 wants a country; when the target is a subnational entity the
        # only defensible property is P1001, whatever the agent chose:
        prop = v.get("prop") or "P1001"
        if v["target"] != v.get("country_qid"):
            prop = "P1001"
        if not re.fullmatch(r"Q\d+", v["target"] or "") or prop not in ("P1001", "P17"):
            subnational_review.append(v)
            continue
        key = (v["qid"], prop)
        if key in seen:
            continue
        seen.add(key)
        auto.append(v)
        qs.append(f"{v['qid']}\t{prop}\t{v['target']}")

    # Resolve target labels so the review .md is readable:
    target_qids = {v["target"] for v in auto}
    target_labels = {
        qid: best_label(e)
        for qid, e in fetch_entities(session, target_qids, props="labels").items()
    }

    by_verdict = Counter(v["verdict"] for v in verdicts)
    md = [
        "# Citizenship-inference jurisdiction plan",
        "",
        f"{len(verdicts)} verdicts: {dict(by_verdict)}",
        f"fix-current {len(fix_current)}: auto {len(auto)}, "
        f"subnational-review {len(subnational_review)}, disagree {len(disagree)}, "
        f"low-confidence {len(low_conf)}, kind-review {len(kind_review)}, "
        f"excluded-kind {len(excluded_kind)}",
        "",
        f"## auto ({len(auto)} rows in .qs, "
        f"{sum(v['holders'] for v in auto)} P39 holders)",
    ]
    for v in sorted(auto, key=lambda v: -v["holders"]):
        tlabel = target_labels.get(v["target"]) or v["target"]
        md.append(
            f"* {v['qid']} **{v['label']}** → {v.get('prop') or 'P1001'} "
            f"{v['target']} ({tlabel}) — {v['holders']} holders, {v.get('kind')}"
            + (" ⟵ verified subnational" if v["via"] == "verified-subnational" else "")
            + f": {v.get('reason')}"
        )

    md.append(f"\n## subnational, entity unverified — review ({len(subnational_review)})")
    for v in sorted(subnational_review, key=lambda v: -v["holders"]):
        md.append(
            f"* {v['qid']} {v['label']} — {v.get('country_code')} "
            f"{v.get('jurisdiction_qid') or 'no entity QID'} "
            f"({v.get('jurisdiction_label')}), {v['holders']} holders: {v.get('reason')}"
        )

    md.append(f"\n## classifier vs citizenship-prior disagreements — review ({len(disagree)})")
    for v in sorted(disagree, key=lambda v: -v["holders"]):
        prior = v.get("prior") or {}
        md.append(
            f"* {v['qid']} {v['label']} — classifier {v.get('country_qid')} "
            f"({v.get('country_code')}) vs prior {prior.get('qid')} "
            f"({prior.get('code')}, share {prior.get('share')}), "
            f"{v['holders']} holders: {v.get('reason')}"
        )

    md.append(f"\n## unsettled conventions (church & party offices) — review ({len(kind_review)})")
    for v in sorted(kind_review, key=lambda v: -v["holders"]):
        md.append(
            f"* {v['qid']} {v['label']} — {v.get('prop')} {v.get('country_qid')} "
            f"({v.get('country_code')}), {v.get('kind')}, {v.get('confidence')}, "
            f"{v['holders']} holders: {v.get('reason')}"
        )

    md.append(f"\n## fix-current below high confidence — review ({len(low_conf)})")
    for v in sorted(low_conf, key=lambda v: -v["holders"]):
        md.append(
            f"* {v['qid']} {v['label']} — {v.get('country_code')} "
            f"{v.get('confidence')}, {v['holders']} holders: {v.get('reason')}"
        )

    hist = [v for v in verdicts if v["verdict"] == "fix-historical"]
    md.append(f"\n## fix-historical — no edits proposed ({len(hist)})")
    for v in sorted(hist, key=lambda v: -v["holders"])[:80]:
        md.append(f"* {v['qid']} {v['label']} — {v.get('country_qid')}: {v.get('reason')}")
    if len(hist) > 80:
        md.append(f"* ... and {len(hist) - 80} more")

    unclear = [v for v in verdicts if v["verdict"] == "unclear"]
    md.append(f"\n## unclear ({len(unclear)})")
    for v in sorted(unclear, key=lambda v: -v["holders"])[:60]:
        md.append(f"* {v['qid']} {v['label']} — {v['holders']} holders: {v.get('reason')}")
    if len(unclear) > 60:
        md.append(f"* ... and {len(unclear) - 60} more")

    skips = Counter(
        (v.get("kind") or "?") for v in verdicts if v["verdict"] == "skip"
    )
    md.append(f"\n## skip ({by_verdict.get('skip', 0)}, by kind: {dict(skips)})")
    excl = Counter((v.get("kind") or "?") for v in excluded_kind)
    md.append(f"\n## fix-current in excluded kinds — not batched ({dict(excl)})")

    (BASE / "citizenship_plan.md").write_text("\n".join(md) + "\n")
    (BASE / "citizenship_plan.qs").write_text("\n".join(qs) + "\n")
    print(f"{len(verdicts)} verdicts: {dict(by_verdict)}")
    print(f"auto: {len(auto)} QS lines covering {sum(v['holders'] for v in auto)} holders "
          f"({sum(1 for v in auto if v['via'] == 'verified-subnational')} verified subnational)")
    print(f"review: subnational {len(subnational_review)}, disagree {len(disagree)}, "
          f"low-conf {len(low_conf)}, excluded kinds {len(excluded_kind)}")
    print(f"Wrote {BASE / 'citizenship_plan.md'} and {BASE / 'citizenship_plan.qs'}")


if __name__ == "__main__":
    main()
