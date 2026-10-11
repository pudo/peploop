#!/usr/bin/env python
"""Propose P53, P22, P25 and P26 for the Hashemites of Jordan.

    python scripts/jo_family.py

The kinship half of the Jordan campaign; the offices are `scripts/jo_offices.py`
and the machinery is `wd/kinship.py`. Writes `jordan_family.jsonl` into the same
verdict directory, so `render_edit_plan.py --campaign jordan` puts both halves in
one batch — `Campaign.extra_verdicts` is what makes the manifest own this file.

Four things about this source are worth stating once.

* **The article is mostly unreadable, and the readable part is the part wanted.**
  `en:Hashemites` renders the Sharifian lineage as 93 `{{tree chart}}` templates,
  which is the box-drawing markup that made Kuwait's House of Sabah impossible.
  The three "Descendants of King …" sections are ordinary nested bullet lists,
  and they are the modern dynasty.

* **Descent is stated by indentation, not by heading.** Where
  `en:Descendants of Ibn Saud` heads a section per wife, this article nests a
  wife's children under her own bullet and theirs under that. The enclosing
  bullet is the assertion, and `wd.kinship.parse_genealogy` carries it down as
  `parent`/`parent_link`.

* **The gloss beside each name describes a different relation from the nesting.**
  Hamzah is nested under Queen Noor — she is his mother — and annotated "(The
  King's half-brother)", which is his relation to the *reigning* king, Abdullah
  II, and not to the bullet above him. Reading the parenthetical instead of the
  structure would emit sibling edges where the article asserts parent edges.
  Nothing here reads it; `glosses=True` cuts it off the name entirely.

* **Half the people listed have no article.** 47 of the 87 entries in the
  descendant sections carry a wikilink; the rest — mostly the youngest
  generation — are a bare name, which is one channel and never enough. They are
  the item-creation byproduct list at the foot of the audit, not a lane that
  underperformed.

The father lane leans on the patronymic, as in Saudi Arabia: a Jordanian royal's
item is "Hamzah bin Al Hussein", so the section's own hatnote — "See also:
Hussein of Jordan" — closes the candidate set to one man and the name confirms
him. The mother lane leans on the pairing: where a bullet names a couple, the
children below take one parent from each, and `mother_records` still refuses
unless the item already records the father, so a mis-nested row joins nothing.

Deliberately not emitted, decided once and shared with `sa_family.py`: **P40**
(the bot-maintained reciprocal of P22) and **P3373** (combinatorial and redundant
once both parents are recorded).
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.api import best_label, claim_qids, fetch_entities
from wd.campaign import resolve_titles, year_of
from wd.http import REPO_ROOT, make_session
from wd.kinship import (
    Kin,
    contradictory_links,
    father_records,
    house_records,
    mother_records,
    parse_genealogy,
    spouse_records,
)
from wd.record import dumps
from wd.wikipedia import fetch_html, permalink

OUT_DIR = REPO_ROOT / "data" / "jordan"
LANG = "en"
ARTICLE = "Hashemites"

#: The house itself — `Q1774915`, the royal family, not the disambiguation page
#: (`Q20811513`) and not `Q41874964` "Hashemites of Iran", who are a different
#: descent claim entirely.
HOUSE = "Q1774915"

#: Name fragments that say "of this house". Kept to the dynasty's own
#: patronymics and to the territorial style its members carry, because the house
#: name is not part of a Jordanian royal's name the way "Al Saud" is: they are
#: "Hamzah bin Al Hussein", "Hassan bin Talal", "Abdullah II of Jordan".
#: "bin abdullah" is deliberately absent — it is one of the commonest names in
#: Arabic and would be a namesake channel rather than a house one.
MARKERS = (
    "bin al hussein", "bint al hussein", "bin talal", "bint talal",
    "of jordan", "hashemite", "hashimi", "bin naif", "bint naif",
    "bin muhammad", "bint muhammad",
)

#: Wikidata's sex-or-gender values, which decide whether a parent bullet is the
#: father or the mother.
MALE = "Q6581097"
FEMALE = "Q6581072"

#: The sections this lane reads. Everything else on the page is the medieval
#: Sharifate, drawn as tree charts.
SECTIONS = ("Main branch", "Descendants of King Hussein of Jordan",
            "Descendants of King Talal of Jordan",
            "Descendants of King Abdullah I of Jordan")

#: Every rule that does not apply, skips, with its reason on the record. There is
#: no review queue — see `recipes/country_sweep.md`.
DISPOSITIONS = {
    "mother.unresolved": "skip",
    "mother.father_not_recorded": "skip",
    "father.ambiguous": "skip",
    "father.generation_contradicted": "skip",
    "father.unresolved": "skip",
    "house.one_channel": "skip",
    "spouse.no_issue": "skip",
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
                        help="p53, p22, p25, p26 (default: all)")
    args = parser.parse_args()
    lanes = set(args.lane or ("p53", "p22", "p25", "p26"))

    session = make_session()
    page = fetch_html(session, LANG, ARTICLE)
    if page is None:
        raise SystemExit(f"{LANG}:{ARTICLE} is missing")
    source = permalink(LANG, page["revid"])
    everyone = parse_genealogy(page["html"], glosses=True)
    listed = [entry for entry in everyone if entry.section in SECTIONS]
    print(f"{len(everyone)} people listed on {ARTICLE}, "
          f"{len(listed)} in the descendant sections")

    titles = [entry.link for entry in listed if entry.link]
    titles += [t for entry in listed for t in entry.section_links]
    people = build_kin(session, titles)
    print(f"{len(set(titles))} distinct links → {len(people)} human items")

    # Each section's hatnote names the king it descends from — "See also:
    # Hussein of Jordan" — which is the article's own statement of whose
    # children these are, and closes the candidate set for a patronymic.
    ancestors: dict = {}
    for entry in listed:
        if entry.section in ancestors or not entry.section_links:
            continue
        found = next((people[t].qid for t in entry.section_links if t in people),
                     None)
        if found:
            ancestors[entry.section] = found

    # The bullets that have children nested under them. The key is the bullet's
    # own link, because two bullets in different sections can print the same
    # name — "Princess Iman" is both the King's sister and his granddaughter.
    heads = {entry.link: entry for entry in listed if entry.link}
    groups: dict = {}
    for entry in listed:
        if entry.parent_link:
            groups.setdefault(entry.parent_link, []).append(entry)

    # Every lane about *descent* reads this list, not `listed`: the second half
    # of a couple bullet is listed under the family without descending from it.
    # Left in, they cost one wrong statement and eleven wasted skips — a wife's
    # married name ("Princess Ghazi of Jordan") read as evidence of her own
    # descent, and every in-law resolved against the wrong parent.
    descent = [entry for entry in listed if not entry.married_in]
    print(f"{len(descent)} descend from the house, "
          f"{len(listed) - len(descent)} married into it")

    records = []
    resolved: list = []
    if "p53" in lanes:
        kin_qids = {kin.qid for kin in people.values()}
        records += house_records(
            campaign="jordan", lane="family_house", listed=descent,
            people=people, house=HOUSE, markers=MARKERS, kin_qids=kin_qids,
            source=source, dispositions=DISPOSITIONS,
        )
    if "p22" in lanes:
        contradictory = contradictory_links(descent)
        if contradictory:
            print(f"! {len(contradictory)} link(s) listed in two generations: "
                  + ", ".join(sorted(contradictory)))
        for section, ancestor in ancestors.items():
            king = next((k for k in people.values() if k.qid == ancestor), None)
            rows = [e for e in descent if e.section == section]
            if king is None or not rows:
                continue
            records += father_records(
                campaign="jordan", lane="family_father", listed=rows,
                people=people, pool=[king],
                generation=f"child of {king.label}",
                source=source, dispositions=DISPOSITIONS,
                contradictory=contradictory,
            )
    if "p25" in lanes:
        for parent_link, children in groups.items():
            head = heads.get(parent_link)
            parent = people.get(parent_link)
            if head is None or parent is None:
                continue
            partner = people.get(head.partner_link or "")
            # Which of the pair is the mother, and which father the children
            # must already record for her to join it. A lone woman's bullet
            # names no husband, so the section's own king stands in — and where
            # that is the wrong man (a daughter-in-law nested at the same depth)
            # `mother_records` refuses, because the children record someone else.
            if parent.gender == FEMALE:
                mother, father = parent, partner
            elif partner is not None and partner.gender == FEMALE:
                mother, father = partner, parent
            else:
                continue
            ancestor = (father.qid if father is not None
                        else ancestors.get(head.section))
            if ancestor is None:
                continue
            key = f"{head.name} ({mother.label})"
            resolved.append((head.section, key, len(children), mother.qid,
                             ancestor))
            records += mother_records(
                campaign="jordan", lane="family_mother",
                sections={key: children}, people=people,
                mothers={key: mother.qid}, ancestor=ancestor, source=source,
                dispositions=DISPOSITIONS,
            )
    if "p26" in lanes:
        # One direction only, from the half who descends. P26 is bot-reciprocated
        # like P40, and emitting both would double the batch for no new fact.
        couples = [
            (entry, len(groups.get(entry.link or "", [])))
            for entry in descent
            if entry.partner_link and entry.link
        ]
        records += spouse_records(
            campaign="jordan", lane="family_spouse", couples=couples,
            people=people, source=source, dispositions=DISPOSITIONS,
        )

    verdict_dir = OUT_DIR / "verdicts"
    verdict_dir.mkdir(parents=True, exist_ok=True)
    (verdict_dir / "jordan_family.jsonl").write_text(dumps(records))

    linked = sum(1 for e in listed if e.link)
    audit = ["# Jordan — kinship audit", "",
             f"Source: {source}", "",
             f"{len(listed)} people listed in the descendant sections · "
             f"{linked} with a wikilink · {len(people)} with a Wikidata item",
             "",
             "## Sections, and the king each descends from", "",
             "| section | entries | linked | ancestor (from the hatnote) |",
             "|---|---|---|---|"]
    for section in SECTIONS:
        rows = [e for e in listed if e.section == section]
        if not rows:
            continue
        audit.append(
            f"| {section} | {len(rows)} | {sum(1 for e in rows if e.link)} | "
            f"{ancestors.get(section) or '— none linked'} |"
        )
    if resolved:
        audit += ["", "## Parent bullets, and the parentage each proposes", "",
                  "The mother comes from the bullet; the father is whom the "
                  "child must already record for her to be added.", "",
                  "| section | bullet | children | mother | father required |",
                  "|---|---|---|---|---|"]
        for section, key, count, mother, ancestor in resolved:
            audit.append(f"| {section} | {key} | {count} | {mother} | {ancestor} |")

    # The ceiling, stated rather than implied: a person with no article cannot be
    # the subject of anything here, and they are most of the last generation.
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
