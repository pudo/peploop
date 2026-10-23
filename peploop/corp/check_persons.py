"""Pin person matching: how names fit, whose life holds a seat, which candidate a seat resolves to, and how a matched seat is written.

    .venv/bin/python -m peploop.corp.check_persons
"""

from datetime import date

from peploop.corp import match, persons, rules
from peploop.corp.check_rules import answer, ent, seat
from peploop.checks import expect

TODAY = date(2026, 10, 18)


def names() -> None:
    fits = persons.name_fits
    expect(fits("Kim Younes Charbit", "Kim Younes"), "a second surname one side leaves out fits")
    expect(fits("Baranyay László", "László Baranyay"), "family name first fits the given name first")
    expect(fits("JUDr. Ing. Erika Musterová, Ph.D.", "Erika Musterová"), "titles and degrees fall away")
    expect(fits("Ερίκα Μουστεράκη", "Erika Mousteraki"), "a Greek name fits its transliteration")
    expect(fits("Ерика Мустерова", "Erika Musterova"), "a Cyrillic name fits its transliteration")
    expect(fits("Erika Müller", "Erika Mueller"), "an umlaut written out fits")
    expect(fits("Jan van der Probe", "Jan Probe"), "a particle one side leaves out fits")
    expect(fits("Erika M. Muster", "Erika Maria Muster"), "an initial fits its name")
    expect(not fits("Muster", "Erika Muster"), "a lone surname never fits")
    expect(not fits("E. Muster", "Erika Muster"), "an initial and a surname are too weak")
    expect(not fits("Erika Muster", "Hanna Muster"), "another given name does not fit")
    expect(not fits("Erika Muster", "Erika Probe-Lang"), "a different surname does not fit")
    expect(not fits("Max Probe", "Max Probst"), "short names one letter apart are other names")


def lifetimes() -> None:
    def person(born: int | None = None, died: int | None = None) -> dict:
        claims = {}
        for prop, y in (("P569", born), ("P570", died)):
            if y:
                claims[prop] = [{"mainsnak": {"datavalue": {"value": {"time": f"+{y}-01-01T00:00:00Z"}}}}]
        return {"claims": claims}
    fit = match.dates_fit
    expect(fit(person(1970), 2020, None, True, 2026), "a 50-year-old's seat fits")
    expect(not fit(person(1999), 2010, None, False, 2026), "a child holds no seat")
    expect(not fit(person(1900, 1960), 2015, None, False, 2026), "the dead hold no seat begun after their death")
    expect(not fit(person(1920), None, None, True, 2026), "a centenarian holds no current seat")
    expect(fit(person(), None, None, True, 2026), "no dates on either side: nothing contradicts")


def choosing() -> None:
    v = lambda tier, same=True: {"tier": tier, "verdict": "supported" if same else "wrong-person",  # noqa: E731
                                 "confidence": "high", "evidence": "", "reason": ""}
    expect(match.choose({"Q901": v("institution")}) == ("Q901", "institution"), "the page names the body: matched")
    expect(match.choose({"Q901": v("domain"), "Q902": v("none")}) == ("Q901", "domain"),
           "the one candidate in the body's field among few namesakes: matched")
    expect(match.choose({"Q901": v("domain"), "Q902": v("institution")}) == ("Q902", "institution"),
           "the page naming the body wins over one in its field")
    expect(match.choose({"Q901": v("domain"), "Q902": v("domain")}) == (None, "ambiguous"),
           "two namesakes in the same field: no match")
    expect(match.choose({"Q901": v("institution"), "Q902": v("institution")}) == (None, "ambiguous"),
           "two pages naming the body: no match")
    crowd = {"Q901": v("domain"), "Q902": v("none"), "Q903": v("none"), "Q904": v("none")}
    expect(match.choose(crowd) == (None, "crowded_domain"), "among many namesakes a field alone is too weak")
    expect(match.choose({**crowd, "Q901": v("institution")}) == ("Q901", "institution"),
           "among many namesakes the one whose page names the body is matched")
    expect(match.choose({"Q901": v("institution", False)}) == (None, "rejected"),
           "the body named but the person not the same (a conflict): no match")
    expect(match.choose({"Q901": v("none"), "Q902": v("conflict")}) == (None, "rejected"), "no evidence: no match")
    low = {**v("institution"), "confidence": "low"}
    expect(match.choose({"Q901": low}) == (None, "rejected"), "the same person at low confidence: no match")
    expect(match.choose({}) == (None, "no_candidate"), "no candidate checked")
    item = {"tier": "item", "verdict": "supported", "confidence": "high", "evidence": "", "reason": "", "foreign": False}
    expect(match.choose({"Q901": item, "Q902": v("domain")}) == ("Q901", "item"),
           "an item whose own data names the body counts like a page that does")
    expect(match.choose({"Q901": item, "Q902": v("institution")}) == (None, "ambiguous"),
           "an item and a page naming the body for two namesakes cannot be told apart")
    claim = lambda prop, value, quals=None: {"mainsnak": {"datavalue": {"value": {"id": value}}},  # noqa: E731
                                             "qualifiers": quals or {}}
    body = "Q900500"
    expect(match.item_ties({"claims": {"P108": [claim("P108", body)]}}, body, []) is not None,
           "an employer statement naming the body ties the item")
    expect(match.item_ties({"claims": {"P39": [claim("P39", "Q900501", {"P642": [{"datavalue": {"value": {"id": body}}}]})]}},
                           body, []) is not None, "so does a position held of the body")
    expect(match.item_ties({"descriptions": {"en": {"value": "Director of the Office of Probes"}}},
                           body, ["Office of Probes"]) is not None, "so does a description naming it")
    expect(match.item_ties({"descriptions": {"en": {"value": "Swiss engineer"}}, "claims": {"P108": [claim("P108", "Q9")]}},
                           body, ["Probe", "Office of Probes"]) is None, "nothing naming the body: no tie")
    expect(match.item_ties({"descriptions": {"en": {"value": "SBB engineer"}}}, body, ["SBB"]) is None,
           "a short abbreviation in a description is too ambiguous")
    foreign = {**v("domain"), "foreign": True}
    expect(match.choose({"Q901": foreign}) == (None, "rejected"),
           "a citizen of another country only, in the body's field: no match (namesakes share fields across borders)")
    expect(match.choose({"Q901": {**v("institution"), "foreign": True}}) == ("Q901", "institution"),
           "a foreigner whose page names the body is matched")


def pages() -> None:
    text = "Lead paragraph.\n" + "x " * 100 + "\nLater she chaired the Probe Agency board.\nUnrelated paragraph."
    cut = match.excerpt(text, ["Probe Agency"], chars=100)
    expect(cut.startswith("Lead paragraph.") and "chaired the Probe Agency" in cut and "Unrelated" not in cut,
           "a long page is cut, keeping its opening and the paragraphs naming the body")
    expect(match.excerpt("Short page.", ["Probe Agency"]) == "Short page.", "a short page is shown whole")


def seats() -> None:
    message = "Erika Muster sits on the supervisory board. Max Probe runs it."
    base = {"qid": "Q900500", "offered": [], "articles": [{"lang": "xx", "url": "u", "rev": 1}],
            "message": message, "links": {"xx": {"Max Probe": "Q901001", "M. Probe": "Q901002"}}}
    one = {**base, "answer": answer(seats=[seat()])}
    rows = rules.seat_rows(one, {"Q901000"}, TODAY, matched={("Q900500", "Erika Muster"): "Q901000"})
    expect(rows[0]["_rule"] is None and rows[0]["value"]["id"] == "Q901000" and rows[0]["_via"] == "matched",
           "an unlinked seat matched by name is written, marked as matched")
    rows = rules.seat_rows(one, {"Q901000"}, TODAY, dead=frozenset({"Q901000"}),
                           matched={("Q900500", "Erika Muster"): "Q901000"})
    expect(rows[0]["_rule"] == "holder_dead", "a matched person passes the same seat rules: no open seat for the dead")
    expect(rules.seat_rows(one, set(), TODAY)[0]["_rule"] == "person_unlinked", "an unmatched seat stays unlinked")
    old = {**base, "answer": answer(seats=[seat(start="1990", end="1995", current=False)])}
    expect(rules.seat_rows(old, set(), TODAY)[0]["_rule"] == "tenure_ended",
           "an unlinked seat its dates rule out is skipped by the dates, never sent to the matcher")
    head = {**base, "answer": answer(seats=[seat(name="Max Probe", body="executive", role="head", quote="Max Probe runs it.")])}
    rows = rules.seat_rows(head, {"Q901001"}, TODAY, titles={"Q901001": {"Max Probe"}})
    expect(rows[0]["_via"] == "link", "a name that is the linked page's title resolves by link")
    anchor = {**head, "answer": answer(seats=[seat(name="Maxem Probem", body="executive", role="head", quote="Max Probe runs it.")])}
    anchor["links"] = {"xx": {"Maxem Probem": "Q901001"}}
    rows = rules.seat_rows(anchor, {"Q901001"}, TODAY, titles={"Q901001": {"Max Probe"}})
    expect(rows[0]["_via"] == "anchor", "a name only the link's text gives resolves by anchor")
    rows = rules.seat_rows(head, {"Q901001"}, TODAY, titles={"Q901001": {"Max Probe"}},
                           unconfirmed={("Q900500", "Max Probe")})
    expect(rows[0]["_rule"] == "person_unconfirmed", "a linked person whose page does not bear out the seat is not written")
    written = [{"qid": "Q900500", "prop": "P1037", "value": "Q901001", "disposition": "apply", "rule": "write",
                "detail": {"name": "Max Probe", "via": "link"}},
               {"qid": "Q900500", "prop": "P5052", "value": "Q901000", "disposition": "apply", "rule": "write",
                "detail": {"name": "Erika Muster", "via": "matched"}},
               {"qid": "Q900500", "prop": "P5052", "value": "Q901003", "disposition": "skip", "rule": "tenure_ended",
                "detail": {"name": "Hans Alt", "via": "anchor"}}]
    both = {**head, "answer": answer(kind="institution", seats=[seat(name="Max Probe", body="executive", role="head"),
                                                                 seat(), seat(name="Hans Alt")])}
    found = match.linked(written, [both])
    expect([(s["qid"], s["seat"]["name"], s["person"]) for s in found] == [("Q900500", "Max Probe", "Q901001")],
           "only written seats whose person the article links go to the page check")
    decisions = [{"qid": "Q900500", "rule": "person_unlinked", "detail": {"name": "Erika Muster"}},
                 {"qid": "Q900500", "rule": "tenure_ended", "detail": {"name": "Max Probe"}}]
    found = match.unlinked(decisions, [{**one, "answer": answer(kind="institution", seats=[seat()])}])
    expect([(s["qid"], s["kind"], s["seat"]["name"]) for s in found] == [("Q900500", "institution", "Erika Muster")],
           "only the seats skipped for want of a person go to the matcher")


def main() -> None:
    names()
    lifetimes()
    choosing()
    pages()
    seats()


if __name__ == "__main__":
    main()
