"""Pin how a unit's own article becomes the one attestation of its office.

A mayoralty or council seat minted from a local area's article has no seeded
holder, so what stands in for one -- the infobox's named head, the council
section's prose -- is read by regular expressions and must fail closed: a
vacant seat, a missing section or a former unit gives no candidate. Pure
functions over fixed text; no network, no database. Run it as
`python -m peploop.check_mint_units` from the repository root.
"""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from peploop import mint, mint_units as mu

LEVEL = mu.Level(key="lga_mayor", archetype="mayor", institution_class="subnational.municipal",
                 of="Q1", sources={"Q10": "https://example.org/level"})
SEATS = mu.Level(key="lga_councillor", archetype="councillor",
                 institution_class="subnational.assemblies", of="Q1")
UNIT = mu.Unit(qid="Q20", label="Shire of Lindo", title="Shire of Lindo", subdivision="Q10",
               council="Q21", council_label="Lindo Shire Council")
ARTICLE = """Shire of Lindo
Local government area
Government
• Shire President: Cr Ann Smith[3]
• State electorate: Lindo
## Council
The council is composed of nine councillors elected from three wards.
"""


def main() -> int:
    failures: list[str] = []

    def expect(got: Any, want: Any, message: str) -> None:
        ok = got == want
        print(("  ok   " if ok else "  FAIL ") + message + ("" if ok else f" (got {got!r})"))
        if not ok:
            failures.append(message)

    print("reading a unit's article:")
    expect(mu.head_of(ARTICLE), ("shire president", "Ann Smith"),
           "the infobox head is read with its title, without the councillor style or a footnote")
    expect(mu.head_of("• Mayor: Vacant"), None, "a vacant seat names nobody")
    expect(mu.head_of("• Mayor: Administrator (appointed)"), None, "nor does an administrator")
    expect(mu.head_of("The mayor is Ann Smith."), None, "prose is not the infobox")
    expect(mu.council_quote(ARTICLE), "The council is composed of nine councillors elected from three wards.",
           "the council section's first prose is the seat's evidence")
    expect(mu.council_quote("## Council\n## Current composition\nShort.\n## History\nThe council was"
                            " formed by a merger of two shires in 2008."), None,
           "and prose under another heading is not")
    for label, want in (("City of Bray", "Bray"), ("Bathurst Regional Council", "Bathurst"),
                        ("Mornington Peninsula Shire", "Mornington Peninsula"),
                        ("Municipality of Kingborough", "Kingborough"), ("Lindo", "Lindo")):
        expect(mu.place_name(label), want, f"the place {label!r} names")

    print("drafting the office:")
    draft, why = mu.draft_for(LEVEL, UNIT, ARTICLE, "https://en.wikipedia.org/wiki/Shire_of_Lindo")
    expect(why, "unit/drafted", "a named head drafts the mayoralty")
    expect((draft["labels"], draft["parent_qid"], draft["jurisdiction_qid"], draft["body_qid"]),
           ({"en": "Shire President of the Shire of Lindo"}, "Q30185", "Q20", "Q21"),
           "a shire president is that seat, of the unit, in its council")
    expect(draft["unit"]["source"], "https://example.org/level", "the level's source travels with it")
    lord = ARTICLE.replace("Shire President: Cr Ann Smith[3]", "Lord Mayor: Ann Smith")
    draft, _why = mu.draft_for(LEVEL, UNIT, lord, "u")
    expect((draft["labels"]["en"], draft["parent_qid"]), ("Lord Mayor of the Shire of Lindo", "Q30185"),
           "a lord mayor is named so, and is a mayoralty of the place")
    former = ("• Mayor: Ann Smith\nThe Town of Lindo was a local government area of the north of the country,"
              " based in the town of Lindo.\n")
    expect(mu.draft_for(LEVEL, UNIT, former, "u"), (None, "unit/former"),
           "a unit its article puts in the past is history, whatever its infobox still says")
    expect(mu.draft_for(LEVEL, UNIT, "## Council\nNine councillors.", "u"), (None, "unit/no-named-holder"),
           "no named head, no candidate")
    seat, why = mu.draft_for(SEATS, UNIT, ARTICLE, "u")
    expect((why, seat["labels"]["en"], seat["single_seat"], seat["body_qid"]),
           ("unit/drafted", "member of Lindo Shire Council", False, "Q21"),
           "a council seat is named by its council, many to a body")
    bare = mu.Unit(qid="Q22", label="Shire of Bray", title="Shire of Bray", subdivision="Q10",
                   council=None, council_label=None)
    named = ARTICLE + "The Bray Shire Council meets monthly.\n"
    expect(mu.draft_for(SEATS, bare, named, "u")[0]["labels"]["en"], "member of Bray Shire Council",
           "and by the council its article names where no council item exists")
    expect(mu.draft_for(SEATS, bare, ARTICLE, "u"), (None, "unit/no-council-name"),
           "and not at all where the article names none")
    for label, want in (("Shire of Capel", "of the Shire of Capel"), ("Coonamble Shire", "of Coonamble Shire"),
                        ("The Hills Shire", "of The Hills Shire")):
        expect(mu.of_unit(label), want, f"the unit's full name, as the siblings word it: {label!r}")
    expect(mu.draft_for(SEATS, UNIT, ARTICLE.split("## Council")[0], "u"), (None, "unit/no-council-section"),
           "a council seat needs the article's council section")

    print("which sets are started:")
    held = [mu.Unit(f"Q3{i}", "x", "x", "Q10", None, None, has_office=i < 3) for i in range(4)]
    held += [mu.Unit("Q40", "x", "x", "Q11", None, None)]
    expect(mu.started(held), {"Q10": 0.75, "Q11": 0.0}, "the share of each subdivision's units holding it")

    print("the unit as an attestation:")
    att = mint.unit_attestation({"qid": "Q20", "label": "Shire of Lindo", "url": "u", "holder": "Ann Smith",
                                 "quote": "Shire President: Ann Smith", "source": "https://example.org/level"})
    expect((att.person, att.current, len(att.quotes)), ("unit:Q20", True, 2),
           "one current holder, quoting the article and the level's source")
    cand = mint.Candidate(id=1, country="zz", ref="unit/lga_mayor/Q20", origin=("unit",), attestations=[att])
    expect(mint.floor(cand), None, "which clears the floor")
    verdict = mint.MintVerdict(verdict="mint", real=True, current=True, missing=True, shape="agree",
                               confidence="medium")
    expect(mint.agreed(mint.Case(cand, None, verdict, [], None)), (mint.GUARDED, "mint:agreed-unit"),
           "a unit's office passes at medium: its undated infobox is all the lane has")
    other = mint.Candidate(id=2, country="zz", ref="x", origin=("mention",), attestations=[att])
    expect(mint.agreed(mint.Case(other, None, verdict, [], None)), (mint.SKIPPED, "verify:confidence/medium"),
           "any other office still needs high")
    expect((cand.holders, cand.current_holders), (1, 1), "and counts as one current holder for the guard")

    print("the census leaves units to this lane:")
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "zz.yml"
        path.write_text("- key: lga_mayor\n  class: subnational.municipal\n  archetype: mayor\n"
                        "  per: units\n  of: Q1\n  sources: {Q10: https://example.org/level}\n")
        expect(mint.census("zz", path=path), [], "categorize sees no anchor for a level")
        expect([(lv.key, lv.of, lv.sources) for lv in mu.levels("zz", path=path)],
               [("lga_mayor", "Q1", {"Q10": "https://example.org/level"})], "and the lane reads it")

    print(f"{len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
