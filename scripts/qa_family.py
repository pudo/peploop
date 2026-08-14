#!/usr/bin/env python
"""Propose P53 and P22 for the House of Thani.

    python scripts/qa_family.py --lane p53 p22

The kinship half of the Qatar campaign; the offices are `scripts/qa_offices.py`
and the machinery is `wd/kinship.py`. Writes `qatar_family.jsonl` into the same
verdict directory, so `render_edit_plan.py --campaign qatar` puts both halves in
one batch — `Campaign.extra_verdicts` is what makes the manifest own this file.

Four things about this source decide what the lane can be.

* **The readable genealogy is not the one the article leads with.**
  `en:House of Thani` opens its family-tree section with 15 `{{Tree chart}}`
  calls, the box-drawing markup that made Kuwait's House of Sabah impossible —
  but those hold only the ten-ruler succession line. The three "… branch"
  sections below them are `{{Tree list}}`: ordinary nested bullets, seven
  generations deep, and they are the house proper.

* **Descent is stated by indentation and confirmed by the patronymic.** Unlike
  Jordan, where a section hatnote names the king a generation descends from,
  every bullet here names its own father one level up. So the pool handed to
  `father_records` is that one linked parent, and the gate is whether the
  child's *own* name says the same man — the article asserts the edge, the name
  confirms it, and an edge with only one of the two skips.

* **Half the house has no article.** 87 of the 179 anchors in these three
  sections are redlinks; the 92 that are blue resolve to 56 distinct titles and
  48 human items. That is the ceiling, and the redlinks are the item-creation
  byproduct at the foot of the audit rather than rows the lane failed on.

* **Most of what is reachable is already recorded.** 39 of the 48 people under a
  linked parent already carry `P22`. The lane is therefore small by arithmetic,
  not by conservatism: nine open cases, of which the patronymic resolves seven.

Deliberately not emitted, and not because a rule refused:

* **P25** — no source states a mother. The branch lists are purely patrilineal
  and the tree charts carry no marriage join, so there is nothing to read. It is
  a deferred lane in `tasks/followups.md`, not a lane that returned nothing.
* **P26** — for the same reason: not one bullet in these sections names a couple.
* **P40** and **P3373**, decided once and shared with `sa_family.py` and
  `jo_family.py`: the first is bot-reciprocated from P22, the second
  combinatorial and redundant once both parents are recorded.
"""

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.api import best_label, claim_qids, fetch_entities
from wd.campaign import STATE_MAX_AGE, resolve_titles, year_of
from wd.http import REPO_ROOT, make_session
from wd.kinship import (
    Kin,
    contradictory_links,
    father_records,
    house_records,
    parse_genealogy,
)
from wd.record import dumps
from wd.wikipedia import fetch_html, permalink

OUT_DIR = REPO_ROOT / "data" / "qatar"
LANG = "en"
ARTICLE = "House of Thani"

#: The ruling house itself — the dynasty, not `Q846` the state.
HOUSE = "Q2502270"

#: Name fragments that say "of this house". Qatari naming makes this stronger
#: than it is for the Hashemites: the house name *is* part of a member's name
#: ("Tamim bin Hamad Al Thani"), where a Jordanian royal is "Hamzah bin Al
#: Hussein" and carries no house word at all. "bin thani" covers the first
#: generation, who predate the house name and are styled after Thani himself.
MARKERS = ("al thani", "al-thani", "bin thani", "آل ثاني")

#: The three branch sections. Everything above them on the page is the ruler
#: succession, drawn as tree charts and already covered by the office lane.
SECTIONS = (
    "Jassim bin Mohammed Al Thani branch",
    "The Ahmed bin Muhammed Al Thani branch",
    "The Jaber bin Muhammed Al Thani branch",
)

#: Every rule that does not apply, skips, with its reason on the record. There
#: is no review queue — see `recipes/country_sweep.md`.
DISPOSITIONS = {
    "father.ambiguous": "skip",
    "father.generation_contradicted": "skip",
    "father.unresolved": "skip",
    "house.one_channel": "skip",
}


def build_kin(session, titles) -> dict:
    """Article title → resolved person, for every title the article links."""
    by_title = resolve_titles(session, LANG, titles)
    # `STATE_MAX_AGE`, not the seven-day default: this read answers "what does
    # Wikidata already record", which is precisely what this campaign's own
    # writes change. `sa_family.py` and `jo_family.py` still take the cached
    # answer, which is why a re-run of Saudi Arabia still offers a P53 that has
    # been live on Q99162142 for days — a followup, not this lane's to fix.
    entities = fetch_entities(
        session, sorted(set(by_title.values())),
        props="labels|aliases|claims|sitelinks", max_age=STATE_MAX_AGE,
    )
    people = {}
    for title, qid in by_title.items():
        entity = entities.get(qid)
        if entity is None or "Q5" not in claim_qids(entity, "P31"):
            continue
        names = [title]
        for lang in ("en", "ar", "mul"):
            term = entity.get("labels", {}).get(lang)
            if term:
                names.append(term["value"])
            for alias in entity.get("aliases", {}).get(lang, []):
                names.append(alias["value"])
        genders = claim_qids(entity, "P21")
        people[title] = Kin(
            qid=qid,
            label=best_label(entity) or title,
            names=list(dict.fromkeys(names)),
            p22=claim_qids(entity, "P22"),
            p25=claim_qids(entity, "P25"),
            p53=claim_qids(entity, "P53"),
            p26=claim_qids(entity, "P26"),
            gender=genders[0] if genders else None,
            birth=year_of(entity, "P569"),
            death=year_of(entity, "P570"),
        )
    return people


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lane", nargs="*", default=None,
                        help="p53, p22 (default: both)")
    args = parser.parse_args()
    lanes = set(args.lane or ("p53", "p22"))

    session = make_session()
    page = fetch_html(session, LANG, ARTICLE)
    if page is None:
        raise SystemExit(f"{LANG}:{ARTICLE} is missing")
    source = permalink(LANG, page["revid"])
    everyone = parse_genealogy(page["html"], glosses=True)
    listed = [entry for entry in everyone if entry.section in SECTIONS]
    print(f"{len(everyone)} people listed on {ARTICLE}, "
          f"{len(listed)} in the three branch sections")

    people = build_kin(session, [e.link for e in listed if e.link])
    linked = sum(1 for e in listed if e.link)
    print(f"{linked} linked entries → {len(people)} human items")

    # The bullets that have children nested under them. Keyed on the parent's
    # link, not their printed name: this article prints "Sheikh Abdullah bin
    # Jassim Al Thani" in two different generations.
    groups: dict = defaultdict(list)
    for entry in listed:
        if entry.parent_link and entry.link:
            groups[entry.parent_link].append(entry)

    records = []
    # `contradictory_links` asks whether a link appears in two *chapters*, which
    # is the right question for `en:Descendants of Ibn Saud` where each wife
    # heads one. It is inert here: all three branches sit under a single "Family
    # tree" h2, so every entry shares one chapter and nothing is ever flagged.
    #
    # The question this article poses instead is whether a link is nested under
    # two different *fathers*, which it is for several — Khalifa bin Jassim
    # hangs off both Jassim bin Mohammed and Jassim bin Muhammed bin Jassim, who
    # are different men a generation apart. A bullet listed at the top level as
    # well as under its parent is not a disagreement, so an absent parent does
    # not count; two named ones do, and both skip.
    parents_of: dict = defaultdict(set)
    for entry in listed:
        if entry.link and entry.parent_link:
            parents_of[entry.link].add(entry.parent_link)
    contradictory = contradictory_links(listed) | {
        link for link, seen in parents_of.items() if len(seen) > 1
    }
    if contradictory:
        print(f"! {len(contradictory)} link(s) listed under two different "
              "fathers: " + ", ".join(sorted(contradictory)))
    if "p22" in lanes:
        # One pool per parent bullet, of exactly one man. `father_records` still
        # requires the child's own patronymic to name him, so the article and
        # the item have to agree before anything is proposed.
        for parent_link, children in sorted(groups.items()):
            parent = people.get(parent_link)
            if parent is None:
                continue
            records += father_records(
                campaign="qatar", lane="family_father", listed=children,
                people=people, pool=[parent],
                generation=f"child of {parent.label}",
                source=source, dispositions=DISPOSITIONS,
                contradictory=contradictory,
            )
    if "p53" in lanes:
        records += house_records(
            campaign="qatar", lane="family_house", listed=listed,
            people=people, house=HOUSE, markers=MARKERS,
            kin_qids={kin.qid for kin in people.values()},
            source=source, dispositions=DISPOSITIONS,
        )

    verdict_dir = OUT_DIR / "verdicts"
    verdict_dir.mkdir(parents=True, exist_ok=True)
    (verdict_dir / "qatar_family.jsonl").write_text(dumps(records))

    audit = ["# Qatar — kinship audit", "",
             f"Source: {source}", "",
             f"{len(listed)} people listed in the three branch sections · "
             f"{linked} with a wikilink · {len(people)} with a Wikidata item",
             "",
             "## Sections, and what each reaches", "",
             "| section | entries | linked | items |", "|---|---|---|---|"]
    for section in SECTIONS:
        rows = [e for e in listed if e.section == section]
        if not rows:
            continue
        items = len({e.link for e in rows if e.link and e.link in people})
        audit.append(f"| {section} | {len(rows)} | "
                     f"{sum(1 for e in rows if e.link)} | {items} |")

    audit += ["", "## Parent bullets, and the children each closes", "",
              "The pool handed to the patronymic gate is one man: the bullet "
              "directly above. A child whose own name does not name him skips.",
              "", "| parent | item | children listed |", "|---|---|---|"]
    for parent_link, children in sorted(groups.items()):
        parent = people.get(parent_link)
        audit.append(f"| {parent_link} | {parent.qid if parent else '— no item'} "
                     f"| {len(children)} |")

    # The ceiling, stated rather than implied: a person with no article cannot be
    # the subject of anything here, and here they are half the house.
    nameless = [e for e in listed if not e.link]
    if nameless:
        audit += ["", "## Listed with no article, and so with no item", "",
                  "A bare name is one channel. These are the item-creation "
                  "byproduct of this lane, not rows it failed on.", ""]
        for entry in nameless:
            parent = f" — listed under {entry.parent}" if entry.parent else ""
            audit.append(f"* {entry.name} ({entry.section}){parent}")

    tally = Counter(f"{r.decision.rule} → {r.decision.action}" for r in records)
    audit += ["", "## Decisions by rule", ""]
    for rule, count in tally.most_common():
        audit.append(f"* `{rule}` — {count}")
    audit += ["", "## Every proposal and every skip", "",
              "| person | property | value | rule | evidence |",
              "|---|---|---|---|---|"]
    for record in records:
        statement = record.statements[0]
        value = statement.value.id if record.decision.action == "apply" else "—"
        audit.append(
            f"| {record.subject.qid} {record.subject.label} | "
            f"{statement.property} | {value} | "
            f"`{record.decision.rule}` ({record.decision.action}) | "
            f"{record.signals[0].detail} |"
        )
    (OUT_DIR / "kinship_audit.md").write_text("\n".join(audit) + "\n")

    applied = sum(1 for r in records if r.decision.action == "apply")
    print(f"\n{len(records)} records, {applied} apply")
    for rule, count in tally.most_common():
        print(f"  {rule:<44} {count}")
    print(f"Wrote {OUT_DIR / 'kinship_audit.md'}")


if __name__ == "__main__":
    main()
