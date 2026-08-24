#!/usr/bin/env python
"""Propose P25, P22 and P53 for the House of Saud.

    python scripts/sa_family.py

The kinship half of the Saudi campaign; the offices are `scripts/sa_offices.py`
and the machinery is `wd/kinship.py`. Writes `saudi_family.jsonl` into the same
verdict directory, so `render_edit_plan.py --campaign saudi` puts both halves in
one batch — `Campaign.extra_verdicts` is what makes the manifest own this file.

Why a separate lane at all. Of the 411 people recording `P53 = Q31711`:
**346 record a father, 72 a mother, 81 any position.** The father is largely
done and the mother is the gap, and no roster can fix that, because the office
lane can only speak about people who held office — which four fifths of this
house did not. `en:Descendants of Ibn Saud` can: it is sectioned **by wife**,
which makes the mother a property of the heading rather than of the row.

Three things about this source are worth stating once.

* **Only 2 of the 21 wife sections name the wife's own item.** The rest give her
  name as a heading and nothing else, so the mother is resolved from the
  section's *own children* — where two or more of them already record the same
  `P25`, that is an assertion by editors who are not this run, and it carries the
  other siblings. Sections where it cannot be resolved are reported, not guessed.

* **The generations are the candidate set.** "Patrilineal grandsons" means the
  father is a son of Ibn Saud, so a patronymic is resolved against 72 people
  rather than against Wikidata. Where the name states the grandfather too
  ("Mohammed bin Salman bin Abdulaziz") the whole chain has to agree.

* **Same-named brothers are the normal case.** At least six of Ibn Saud's sons
  share a given name with an infant brother who died first — Turki I and Turki
  II, Badr I and Badr, Fahd I and Fahd, Talal I and Talal, Majid I and Majid,
  Khalid I and Khalid II. The lifetime gate is what separates them, and where it
  cannot, the row is skipped as `father.ambiguous` rather than resolved to the
  likelier one.

Deliberately not emitted, decided once: **P40** (the bot-maintained reciprocal of
P22 — emitting both doubles the batch and invites a constraint conflict),
**P3373** (combinatorial and redundant once both parents are recorded: the
Sudairi Seven alone would be 42 statements), and **P26**, whose evidence here is
prose about cousin marriages rather than rows.
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.api import best_label, claim_qids, fetch_entities, sparql
from wd.campaign import resolve_titles, year_of
from wd.http import REPO_ROOT, make_session
from wd.kinship import (
    Kin,
    contradictory_links,
    father_records,
    house_records,
    mother_records,
    parse_genealogy,
    spouse_matches,
)
from wd.record import dumps
from wd.wikipedia import fetch_html, permalink

OUT_DIR = REPO_ROOT / "data" / "saudi"
LANG = "en"
ARTICLE = "Descendants of Ibn Saud"

#: Ibn Saud, whose descendants this article is.
ANCESTOR = "Q151509"
#: The house itself.
HOUSE = "Q31711"
#: Name fragments that say "of this house", folded by `wd.kinship`. Kept to the
#: dynasty's own name: a tribal name a wife brought (Al Sudairi, Al Shammari)
#: says the opposite of what is wanted here.
MARKERS = ("al saud", "as saud", "ibn saud", "bin abdulaziz", "bint abdulaziz")

#: The chapter whose sections are wives rather than generations.
WIVES_CHAPTER = "Wives and their children"
#: Section headings that assert descent through the male line, and so close the
#: candidate set for a patronymic. `Granddaughters` and `Great-granddaughters`
#: are excluded on purpose: their headings assert a generation but not a line,
#: and the article keeps a separate chapter for non-patrilineal descendants.
PATRILINE = {
    "Patrilineal grandsons": ("grandson of Ibn Saud", "sons"),
    "Deceased": ("grandson of Ibn Saud", "sons"),
    "Patrilineal great-grandsons of Ibn Saud": (
        "great-grandson of Ibn Saud", "grandsons"
    ),
}

#: How many siblings must already record a mother before her item is believed.
#: Two, not one: a single recorded value can itself be an error, and the point of
#: this channel is that it is independent of this run.
MOTHER_WITNESSES = 2

#: Every rule that does not apply, skips, with its reason on the record. There is
#: no review queue — see `recipes/country_sweep.md`.
DISPOSITIONS = {
    "mother.unresolved": "skip",
    "mother.father_not_recorded": "skip",
    "father.ambiguous": "skip",
    "father.generation_contradicted": "skip",
    "father.unresolved": "skip",
    "house.one_channel": "skip",
}


def build_kin(session, titles) -> dict:
    """Article title → resolved person, for every title the article links."""
    by_title = resolve_titles(session, LANG, titles)
    entities = fetch_entities(
        session, sorted(set(by_title.values())),
        props="labels|aliases|claims|sitelinks",
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
        people[title] = Kin(
            qid=qid,
            label=best_label(entity) or title,
            names=list(dict.fromkeys(names)),
            p22=claim_qids(entity, "P22"),
            p25=claim_qids(entity, "P25"),
            p53=claim_qids(entity, "P53"),
            birth=year_of(entity, "P569"),
            death=year_of(entity, "P570"),
        )
    return people


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lane", nargs="*", default=None,
                        help="p25, p22, p53 (default: all)")
    args = parser.parse_args()
    lanes = set(args.lane or ("p25", "p22", "p53"))

    session = make_session()
    page = fetch_html(session, LANG, ARTICLE)
    if page is None:
        raise SystemExit(f"{LANG}:{ARTICLE} is missing")
    source = permalink(LANG, page["revid"])
    listed = parse_genealogy(page["html"])
    print(f"{len(listed)} people listed on {ARTICLE}")

    titles = [entry.link for entry in listed if entry.link]
    titles += [t for entry in listed for t in entry.section_links]
    people = build_kin(session, titles)
    print(f"{len(set(titles))} distinct links → {len(people)} human items")

    # The wives chapter, section by section.
    sections: dict = {}
    for entry in listed:
        if entry.chapter == WIVES_CHAPTER and entry.section:
            sections.setdefault(entry.section, []).append(entry)

    # A wife's item, by whichever channel resolves her, strongest first. All
    # three are somebody other than this run asserting the identity.
    mothers: dict = {}
    how: dict = {}
    for section, entries in sections.items():
        hatnote = next(
            (people[t].qid for entry in entries for t in entry.section_links
             if t in people),
            None,
        )
        if hatnote:
            mothers[section] = hatnote
            how[section] = "hatnote"
            continue
        recorded = Counter(
            qid for entry in entries
            if entry.link in people
            for qid in people[entry.link].p25
        )
        if recorded:
            qid, count = recorded.most_common(1)[0]
            if count >= MOTHER_WITNESSES:
                mothers[section] = qid
                how[section] = f"{count} siblings already record it"

    # The third channel, and the one that reaches the sections that need it.
    #
    # The sibling plurality above is structurally blind exactly where the gap
    # is: it can only resolve a wife *some* of whose children already record
    # her, and a section where none of them does is precisely a section with
    # nothing to derive from. Sixteen of the twenty-one were unresolved on those
    # two channels alone, and they held every one of the missing mothers.
    #
    # So: the ancestor's own recorded spouses, matched by name against the
    # section heading. Two channels still — the article names her as his wife,
    # and her item records `P26` to him — and required to be 1:1, because
    # "Bazza" alone would otherwise claim both the Bazza (I) and Bazza (II)
    # sections and the wrong mother is worse than none.
    # Both directions of P26, plus any woman recorded as the mother of one of
    # his children. P26 is bot-maintained but not guaranteed symmetric, and
    # Baraka Al Yamaniyah is the case: she records no P26 at all and is reachable
    # only as Muqrin's mother.
    spouse_qids = [
        row["w"] for row in sparql(session, f"""
            SELECT DISTINCT ?w WHERE {{
              {{ wd:{ANCESTOR} p:P26/ps:P26 ?w }}
              UNION {{ ?w p:P26/ps:P26 wd:{ANCESTOR} }}
              UNION {{ ?w p:P40/ps:P40 ?c . ?c p:P22/ps:P22 wd:{ANCESTOR} .
                       ?w wdt:P21 wd:Q6581072 }}
            }}""")
    ]
    spouses = fetch_entities(session, spouse_qids, props="labels|aliases|claims")
    unresolved = [s for s in sections if s not in mothers]
    pairs: dict = {}
    for qid, entity in spouses.items():
        names = [best_label(entity) or ""]
        for lang in ("en", "ar", "mul"):
            for alias in entity.get("aliases", {}).get(lang, []):
                names.append(alias["value"])
            term = entity.get("labels", {}).get(lang)
            if term:
                names.append(term["value"])
        hit = [
            section for section in unresolved
            if any(spouse_matches(section, name) for name in names if name)
        ]
        if len(hit) == 1:
            pairs.setdefault(hit[0], []).append(qid)
    for section, qids in pairs.items():
        if len(qids) == 1:
            mothers[section] = qids[0]
            how[section] = "her item records P26 to Ibn Saud"
        else:
            how[section] = (
                f"ambiguous — {len(qids)} of his recorded spouses match this name"
            )

    records = []
    if "p25" in lanes:
        records += mother_records(
            campaign="saudi", lane="family_mother", sections=sections,
            people=people, mothers=mothers, ancestor=ANCESTOR, source=source,
            dispositions=DISPOSITIONS,
        )
    if "p22" in lanes:
        # The pools, in order: Ibn Saud's own children are the fathers of the
        # grandsons; the grandsons are the fathers of the great-grandsons.
        pools = {
            "sons": [people[e.link] for e in listed
                     if e.chapter == WIVES_CHAPTER and e.link in people],
            "grandsons": [people[e.link] for e in listed
                          if e.section in ("Patrilineal grandsons", "Deceased")
                          and e.link in people],
        }
        contradictory = contradictory_links(listed)
        if contradictory:
            print(f"! {len(contradictory)} link(s) listed in two generations: "
                  + ", ".join(sorted(contradictory)))
        for section, (generation, pool) in PATRILINE.items():
            rows = [e for e in listed if e.section == section]
            if not rows or not pools[pool]:
                continue
            records += father_records(
                campaign="saudi", lane="family_father", listed=rows,
                people=people, pool=pools[pool], generation=generation,
                source=source, dispositions=DISPOSITIONS,
                contradictory=contradictory,
            )
    if "p53" in lanes:
        kin_qids = {kin.qid for kin in people.values()} | {ANCESTOR}
        records += house_records(
            campaign="saudi", lane="family_house", listed=listed,
            people=people, house=HOUSE, markers=MARKERS, kin_qids=kin_qids,
            source=source, dispositions=DISPOSITIONS,
        )

    verdict_dir = OUT_DIR / "verdicts"
    verdict_dir.mkdir(parents=True, exist_ok=True)
    (verdict_dir / "saudi_family.jsonl").write_text(dumps(records))

    # The audit: what each channel resolved, and every section it could not.
    audit = ["# Saudi — kinship audit", "",
             f"Source: {source}", "",
             f"{len(listed)} people listed · {len(people)} with a Wikidata item",
             "", "## Wives, and how each was resolved", "",
             "| section | children | listed with an item | mother item | how |",
             "|---|---|---|---|---|"]
    for section, entries in sections.items():
        with_item = sum(1 for e in entries if e.link in people)
        audit.append(
            f"| {section} | {len(entries)} | {with_item} | "
            f"{mothers.get(section) or '— unresolved'} | {how.get(section, '—')} |"
        )
    # The ceiling on this lane, stated rather than implied: a wife with no item
    # cannot be the value of anyone's P25, and eleven of the twenty-one sections
    # are in that position. Creating those items is the prerequisite, not a
    # nicety, and it is a human gate — so it goes out as a byproduct list.
    orphan = [
        (section, entries) for section, entries in sections.items()
        if section not in mothers
        and any(e.link in people and not people[e.link].p25 for e in entries)
    ]
    if orphan:
        audit += ["", "## Wives with no Wikidata item, and the P25 they block", "",
                  "These sections resolved to nothing because the wife herself "
                  "has no item. Creating them is what unblocks the remaining "
                  "mothers; until then there is nothing for a P25 to point at.",
                  ""]
        for section, entries in orphan:
            waiting = [
                f"{people[e.link].qid} {people[e.link].label}"
                for e in entries if e.link in people and not people[e.link].p25
            ]
            audit.append(f"* **{section}** — {len(waiting)} child(ren) waiting: "
                         + ", ".join(waiting))
    audit += ["", "## Decisions by rule", ""]
    tally = Counter(f"{r.decision.rule} → {r.decision.action}" for r in records)
    for rule, count in tally.most_common():
        audit.append(f"* `{rule}` — {count}")
    audit += ["", "## Every proposal and every skip", "",
              "| person | property | value | rule | evidence |", "|---|---|---|---|---|"]
    for record in records:
        statement = record.statements[0]
        # A skipped record still carries a statement object, whose value is
        # whichever candidate came first — printing it would read as a proposal.
        value = statement.value.id if record.decision.action == "apply" else "—"
        audit.append(
            f"| {record.subject.qid} {record.subject.label} | "
            f"{statement.property} | {value} | "
            f"`{record.decision.rule}` ({record.decision.action}) | "
            f"{record.signals[0].detail} |"
        )
    (OUT_DIR / "kinship_audit.md").write_text("\n".join(audit) + "\n")

    applied = sum(1 for r in records if r.decision.action == "apply")
    print(f"\n{len(mothers)}/{len(sections)} wives resolved to an item")
    print(f"{len(records)} records, {applied} apply")
    for rule, count in tally.most_common():
        print(f"  {rule:<44} {count}")
    print(f"Wrote {OUT_DIR / 'kinship_audit.md'}")


if __name__ == "__main__":
    main()
