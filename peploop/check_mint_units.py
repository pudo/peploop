"""Pin how a unit's own article becomes the one attestation of its office.

A mayoralty or council seat minted from a local area's article has no seeded
holder, so what stands in for one -- the infobox's named head, the council
section's prose -- is read by regular expressions and must fail closed: a
vacant seat, a missing section or a former unit gives no candidate. Pure
functions over fixed text; no network, no database. Run it as
`python -m peploop.check_mint_units` from the repository root.
"""

import sys
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from peploop import mint, mint_units as mu, offices

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

    print("the units of a level:")
    expect(mu.unit_pattern(LEVEL, "Q408"), "?u wdt:P31/wdt:P279* wd:" + LEVEL.of + " ; wdt:P17 wd:Q408 .",
           "a class names the units it types")
    listed = mu.Level(key="lc_mayor", archetype="mayor", institution_class="subnational.municipal", of="P150")
    expect(mu.unit_pattern(listed, "Q233"), "wd:Q233 wdt:P150 ?sub . ?sub wdt:P150 ?u .",
           "P150 names the units the subdivisions list, each under its subdivision")

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
    expect(mint.attested_aliases([att], {"en": "Shire President of the Shire of Lindo"}, ["Aland"], "mayor"), {},
           "and gives the item no alias: an infobox line is not a name of the office")
    verdict = mint.MintVerdict(verdict="mint", real=True, current=True, missing=True, shape="agree",
                               confidence="medium")
    expect(mint.agreed(mint.Case(cand, None, verdict, [], None)), (mint.GUARDED, "mint:agreed-unit"),
           "a unit's office passes at medium: its undated infobox is all the lane has")
    other = mint.Candidate(id=2, country="zz", ref="x", origin=("mention",), attestations=[att])
    expect(mint.agreed(mint.Case(other, None, verdict, [], None)), (mint.SKIPPED, "verify:confidence/medium"),
           "any other office still needs high")
    anchor = mint.Candidate(id=3, country="zz", ref="supreme_judge", origin=("reconcile", "census"),
                            attestations=[att])
    expect(mint.agreed(mint.Case(anchor, None, verdict, [], None)), (mint.GUARDED, "mint:agreed-census"),
           "a census anchor passes at medium when the verifier agreed with its shape")
    expect((cand.holders, cand.current_holders), (1, 1), "and counts as one current holder for the guard")

    print("the census leaves units to this lane:")
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "zz.yml"
        path.write_text("- key: lga_mayor\n  class: subnational.municipal\n  archetype: mayor\n"
                        "  per: units\n  of: Q1\n  sources: {Q10: https://example.org/level}\n")
        expect(mint.census("zz", path=path), [], "categorize sees no anchor for a level")
        expect([(lv.key, lv.of, lv.sources) for lv in mu.levels("zz", path=path)],
               [("lga_mayor", "Q1", {"Q10": "https://example.org/level"})], "and the lane reads it")

    check_amlr(expect)
    print(f"{len(failures)} failures")
    return 1 if failures else 0


def _p6(qid: str, rank: str = "normal", start: str | None = None, end: bool = False,
        url: str | None = None) -> dict[str, Any]:
    quals: dict[str, Any] = {}
    if start:
        quals["P580"] = [{"datavalue": {"value": {"time": start}}}]
    if end:
        quals["P582"] = [{"datavalue": {"value": {"time": "+2020-01-01T00:00:00Z"}}}]
    refs = [{"snaks": {"P854": [{"datavalue": {"value": url}}]}}] if url else []
    return {"rank": rank, "mainsnak": {"datavalue": {"value": {"id": qid}}}, "qualifiers": quals, "references": refs}


def _human(name: str, dead: bool = False) -> dict[str, Any]:
    claims: dict[str, Any] = {"P31": [{"rank": "normal", "mainsnak": {"datavalue": {"value": {"id": "Q5"}}}}]}
    if dead:
        claims["P570"] = [{"rank": "normal", "mainsnak": {"datavalue": {"value": {"time": "+2024-01-01T00:00:00Z",
                                                                                 "precision": 11}}}}]
    return {"labels": {"de": {"value": name}}, "claims": claims}


DE = mu.Level(key="amlr_municipal_head", archetype="mayor", institution_class="subnational.municipal",
              of="amlr:municipal", sources={"*": "https://example.org/law"}, lang="de", title="Bürgermeister",
              labels={"de": "{title} von {name}", "en": "Mayor of {name}",
                      "en/Oberbürgermeister": "Lord Mayor of {name}"},
              parents={"Oberbürgermeister": "Q109862464", "Bürgermeister": "Q17175157"})


def check_amlr(expect: Any) -> None:
    """The EU levels: units by AMLR level, the holder from P6 or a local infobox, labels from templates."""
    print("an AMLR level:")
    expect((DE.amlr_level, LEVEL.amlr_level), ("municipal", None), "`of: amlr:<level>` names a level, a QID none")
    expect((DE.source_for("Q10"), LEVEL.source_for("Q11")), ("https://example.org/law", None),
           "`*` is a source for every subdivision; otherwise a subdivision needs its own")
    it = mu.Level(key="m", archetype="mayor", institution_class="subnational.municipal", of="amlr:municipal",
                  parent="Q670106", parents={"Q1210": "Q98960787"})
    expect((it.parent_for("sindaco", "Q1210"), it.parent_for("sindaco", "Q1460"), DE.parent_for("Oberbürgermeister", None)),
           ("Q98960787", "Q670106", "Q109862464"), "the parent goes by title, then subdivision, then the level's")
    expect("grouping_head" not in mint.CATEGORIZE_ARCHETYPES and "mayor" in mint.CATEGORIZE_ARCHETYPES, True,
           "a unit-only archetype is never offered to categorize, whose prompt stays as it was")

    print("a local infobox:")
    for lang, line, want in (
            ("de", "Oberbürgermeister:: Frank Nopper (CDU)", ("Oberbürgermeister", "Frank Nopper")),
            ("de", "Oberbürgermeisterin:: Ann Weber (SPD)", ("Oberbürgermeister", "Ann Weber")),
            ("de", "Bezirksbürgermeister:: Ann Weber", None),
            ("pl", "Prezydent: Agata Wojda", ("prezydent miasta", "Agata Wojda")),
            ("pl", "Prezydent: Zdzisław Wolski (p.f.)", None),
            ("pl", "Starosta: Andrzej Płonka", ("starosta", "Andrzej Płonka")),
            ("el", "Δήμαρχος: Βασιλόπουλος Αθανάσιος (01-09-2019) - (31-12-2023)", None),
            ("it", "Sindaco: Riccardo Righi (indipendente) dal 10-6-2024", ("sindaco", "Riccardo Righi")),
            ("it", "Sindaco metropolitano: Giuseppe Mascia (PD) dal 30-9-2025",
             ("sindaco metropolitano", "Giuseppe Mascia")),
            ("pt", "Presidente da câmara municipal: Marco Almeida (PSD, 2025-2029)",
             ("presidente da câmara municipal", "Marco Almeida")),
            ("lv", "Domes priekšsēdētājs (2026-):: Andris Krauja (NA)", ("domes priekšsēdētājs", "Andris Krauja")),
            ("cs", "Primátor: post uprázdněn", None),
            ("it", "Sindaco: Raffaele Giordano (PD) dall'8-10-2025", ("sindaco", "Raffaele Giordano")),
            ("it", "Sindaco: Vincenza Filippi, Enza Caporale, Rita Guida (commissione straordinaria)", None),
            ("it", "Sindaco: Vincenzo Cardellicchio, Fabio Giombini, Michele Albertini", None),
            ("fi", "Hallituksen puheenjohtaja: Jasmin Granholm", None),
            ("fr", "Président: Alain Iriart (EHBAI)", ("président", "Alain Iriart"))):
        expect(mu.head_of(line, lang), want, f"{lang}: {line!r}")

    print("labels from templates:")
    gr = mu.Level(key="g", archetype="mayor", institution_class="x", of="amlr:municipal", lang="el",
                  labels={"el": "Δήμαρχος {name}", "en": "Mayor of {name}"},
                  forms={"el": [("^Δήμος ", "")], "en": [(r"\s+[Mm]unicipality$", "")]})
    unit = mu.Unit("Q20", "x", None, None, None, None, names={"el": "Δήμος Καλαμάτας", "en": "Kalamata Municipality"})
    expect(mu.office_labels(gr, unit, "δήμαρχος"), {"el": "Δήμαρχος Καλαμάτας", "en": "Mayor of Kalamata"},
           "the forms make the unit's name the head's: Δήμος Καλαμάτας, Δήμαρχος Καλαμάτας")
    bare = mu.Unit("Q20", "x", None, None, None, None, names={"el": "Πάτρα", "en": "Patras"})
    expect(mu.office_labels(gr, bare, "δήμαρχος"), {"en": "Mayor of Patras"},
           "a name the own language's forms cannot rewrite gives no label in it")
    fi = mu.Level(key="f", archetype="mayor", institution_class="x", of="amlr:municipal", lang="fi",
                  labels={"fi": "{council} {title}", "en": "City Manager of {name}", "en/pormestari": "Mayor of {name}"},
                  forms={"fi": [(r"\s+(?:kaupungin|kunnan)?valtuusto$", "")]})
    rov = mu.Unit("Q20", "x", None, None, "Q21", None, names={"en": "Rovaniemi"},
                  council_names={"fi": "Rovaniemen kaupunginvaltuusto"})
    expect((mu.office_labels(fi, rov, "kaupunginjohtaja"), mu.office_labels(fi, rov, "pormestari")["en"]),
           ({"fi": "Rovaniemen kaupunginjohtaja", "en": "City Manager of Rovaniemi"}, "Mayor of Rovaniemi"),
           "the genitive comes from the council's label, and a title may word the English apart")
    pt_forms = [("^(Póvoa|Maia|Moita)\\b", "da \\1"), ("^(Caldas)\\b", "das \\1"), ("^(Seixal|Montijo)$", "do \\1"),
                ("^(?!(?:da|das|do|dos) )", "de ")]
    pt = mu.Level(key="p", archetype="mayor", institution_class="x", of="amlr:municipal", lang="pt",
                  labels={"pt": "Presidente da Câmara Municipal {name}"}, forms={"pt": pt_forms})
    for name, want in (("Sintra", "de Sintra"), ("Póvoa de Varzim", "da Póvoa de Varzim"),
                       ("Caldas da Rainha", "das Caldas da Rainha"), ("Seixal", "do Seixal")):
        got = mu.office_labels(pt, mu.Unit("Q20", "x", None, None, None, None, names={"pt": name}), "x")
        expect(got, {"pt": f"Presidente da Câmara Municipal {want}"}, f"the article {name} takes")
    fr = mu.Level(key="e", archetype="grouping_head", institution_class="x", of="amlr:grouping", lang="fr",
                  labels={"fr": "président {name}"},
                  forms={"fr": [("^((?:[Cc]ommunauté|[Mm]étropole)\\b)", "de la \\1"), ("^([Aa]gglomération)\\b", "de l'\\1"),
                                ("^Le ", "du "), ("^([AEIOUaeiou])", "d'\\1"), ("^(?!(?:de |du |des |d'))", "de ")]})
    for name, want in (("communauté d'agglomération du Pays Basque",
                        "président de la communauté d'agglomération du Pays Basque"),
                       ("Bordeaux Métropole", "président de Bordeaux Métropole"),
                       ("Agglomération montargoise", "président de l'Agglomération montargoise"),
                       ("Le Muretain Agglo", "président du Muretain Agglo"),
                       ("Agglo Pays d'Issoire", "président d'Agglo Pays d'Issoire")):
        got = mu.office_labels(fr, mu.Unit("Q20", "x", None, None, None, None, names={"fr": name}), "président")
        expect(got, {"fr": want}, f"an EPCI's president: {want!r}")

    prose = ("Zgierz – miasto w województwie łódzkim. Prezydentem Zgierza jest Przemysław Staniszewski. "
             "Droga do Zgierza prowadzi z Łodzi. Prezydent miasta Zgierz podpisał umowę.")
    expect(mu.genitive(prose, "pl", "Zgierz"), "Zgierza", "the genitive the article writes after a cue, not the nominative")
    expect(mu.genitive("Pociągi jeżdżą do Gorzowa Wielkopolskiego i od Gorzowa Wielkopolskiego.", "pl",
                       "Gorzów Wielkopolski"), "Gorzowa Wielkopolskiego", "every word of the name declined")
    expect(mu.genitive("Autobus do Jastrzębia jedzie.", "pl", "Jastrzębie-Zdrój"), None,
           "a form that drops the name's hyphened part is not its genitive")
    expect(mu.genitive("Piła leży nad Gwdą.", "pl", "Piła"), None, "no cue, no genitive, and no label")
    pl = mu.Level(key="m", archetype="mayor", institution_class="x", of="amlr:municipal", lang="pl",
                  labels={"pl": "prezydent {genitive}", "en": "Mayor of {name}"})
    zg = mu.Unit("Q20", "x", None, None, None, None, names={"pl": "Zgierz", "en": "Zgierz"})
    expect(mu.office_labels(pl, zg, "prezydent miasta", prose), {"pl": "prezydent Zgierza", "en": "Mayor of Zgierz"},
           "a Polish city's head is labelled with the city in the genitive")

    print("the unit's own P6:")
    holders = {"Q1": _human("Ann Weber"), "Q2": _human("Bob Roth"), "Q3": _human("Old Man", dead=True),
               "Q4": {"labels": {}, "claims": {}}}
    head, why = mu.current_head({"claims": {"P6": [_p6("Q1", start="+2021-05-01T00:00:00Z", url="https://x.org")]}},
                                holders, ["de"], this_year=2026)
    expect((head.qid, head.label, head.start, head.reference, why),
           ("Q1", "Ann Weber", "2021-05-01", "https://x.org", None), "one current human, with its start and reference")
    cases = (
        ({"P6": [_p6("Q2", end=True), _p6("Q1")]}, ("Q1", None), "an ended statement is history"),
        ({"P6": [_p6("Q2"), _p6("Q1", rank="preferred")]}, ("Q1", None), "a preferred one stands alone"),
        ({"P6": [_p6("Q2"), _p6("Q1")]}, (None, "p6/several"), "two current statements are a list nobody ended"),
        ({"P6": [_p6("Q3")]}, (None, "p6/dead"), "a dead holder holds nothing"),
        ({"P6": [_p6("Q4")]}, (None, "p6/not-human"), "nor does a non-human"),
        ({"P6": [_p6("Q1", start="+2009-01-01T00:00:00Z")]}, (None, "p6/stale"),
         "a tenure begun before the current window is not current"),
        ({}, (None, None), "no P6, nothing to say"))
    for claims, want, message in cases:
        head, why = mu.current_head({"claims": claims}, holders, ["de"], this_year=2026)
        expect((head.qid if head else None, why), want, message)

    print("drafting an AMLR office:")
    stuttgart = mu.Unit("Q1022", "Stuttgart", "Stuttgart", "Q985", "Q1360830", "Gemeinderat Stuttgart",
                        names={"de": "Stuttgart", "en": "Stuttgart"}, head=mu.Head("Q1", "Frank Nopper", "2021-01-07"))
    text = "Basisdaten\nOberbürgermeister:: Frank Nopper (CDU)\nStuttgart ist die Landeshauptstadt.\n"
    draft, why = mu.draft_for(DE, stuttgart, text, "https://de.wikipedia.org/wiki/Stuttgart")
    expect((why, draft["labels"], draft["parent_qid"], draft["body_qid"], draft["jurisdiction_qid"]),
           ("unit/drafted", {"de": "Oberbürgermeister von Stuttgart", "en": "Lord Mayor of Stuttgart"},
            "Q109862464", "Q1360830", "Q1022"),
           "the infobox's title names and types the office, in the unit's council")
    expect((draft["unit"]["holder_qid"], len(draft["unit"]["quotes"]), draft["unit"]["source"], draft["unit"]["lang"]),
           ("Q1", 2, "https://example.org/law", "de"), "the P6 holder attests it, the infobox line beside it")
    moved = mu.Unit(**{**stuttgart.__dict__, "head": mu.Head("Q2", "Fritz Kuhn")})
    draft, _why = mu.draft_for(DE, moved, text, "u")
    expect((draft["unit"]["holder"], draft["unit"]["holder_qid"]), ("Frank Nopper", None),
           "a P6 the infobox contradicts is the mayor before last: the article's holder attests it")
    only = mu.Unit(**{**stuttgart.__dict__, "title": None})
    draft, _why = mu.draft_for(DE, only, "", "https://www.wikidata.org/wiki/Q1022")
    expect((draft["labels"]["de"], draft["parent_qid"], len(draft["unit"]["quotes"])),
           ("Bürgermeister von Stuttgart", "Q17175157", 1), "a P6 alone takes the level's title")
    nobody = mu.Unit(**{**stuttgart.__dict__, "head": None})
    expect(mu.draft_for(DE, nobody, "Basisdaten\n", "u"), (None, "unit/no-named-holder"),
           "neither a P6 nor an infobox line: no candidate")

    twin = {"labels": {"pl": "starosta bielski", "en": "Starost of Bielsko County"}, "jurisdiction_qid": "Q1"}
    other = {"labels": {"pl": "starosta bielski", "en": "Starost of Bielsk County"}, "jurisdiction_qid": "Q2"}
    alone = {"labels": {"pl": "starosta poznański", "en": "Starost of Poznań County"}, "jurisdiction_qid": "Q3"}
    expect(mu.homonyms([twin, other, alone]), {"Q1", "Q2"},
           "two units whose offices share a label in any language are both left out")

    print("the unit's parent survives the spec:")
    draft, _why = mu.draft_for(DE, stuttgart, text, "u")
    cand = mint.Candidate(id=9, country="zz", ref="unit/amlr_municipal_head/Q1022", origin=("unit",),
                          archetype="mayor", draft=draft,
                          attestations=[mint.unit_attestation(draft["unit"])])
    ctx = mint.Context("zz", state_qid="Q183", langs=["de"], state_names=["Deutschland"],
                       siblings=offices.Siblings(parents={"mayor": Counter({"Q30185": 9})}),
                       closure={"Q109862464"}, index=[], labels_of=lambda q: {}, terms=lambda q: {},
                       resolve=lambda q: {}, run_labels=lambda c: [], lookup=lambda *a: [],
                       items=lambda q: {}, subdivisions=["Q985"], anchors=[], claims=lambda q: {},
                       diplomatic=lambda q: False)
    spec, _problems = mint.build_spec(cand, ctx)
    expect((spec.parent, spec.body_qid, spec.jurisdiction_qid), ("Q109862464", "Q1360830", "Q1022"),
           "the level's measured parent outranks the siblings' tally, as a census anchor's does")
    expect(cand.attestations[0].lang, "de", "and the attestation is in the article's language")

    print("the census reads an AMLR level:")
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "zz.yml"
        path.write_text("- key: amlr_municipal_head\n  class: subnational.municipal\n  archetype: mayor\n"
                        "  per: units\n  of: amlr:municipal\n  lang: el\n  title: δήμαρχος\n"
                        "  labels: {el: 'Δήμαρχος {name}'}\n  forms: {el: [['^Δήμος ', '']]}\n"
                        "  parent: Q30185\n  sources: {'*': https://example.org/law}\n")
        (lv,) = mu.levels("zz", path=path)
        expect((lv.amlr_level, lv.lang, lv.title, lv.forms, lv.parent, lv.source_for(None)),
               ("municipal", "el", "δήμαρχος", {"el": [("^Δήμος ", "")]}, "Q30185", "https://example.org/law"),
               "every key of the entry")


if __name__ == "__main__":
    sys.exit(main())
