"""Pin the ledger's judgements, offline: what a strike vetoes, what counts as our own edit, which notes strike.

    .venv/bin/python -m peptree.check_ledger
"""

from typing import Any

from peptree import ledger, qs, removals
from peptree.check_filter import expect
from peptree.migrate_ledger import STATUS, note_strikes

URL = "https://de.wikipedia.org/wiki/Kantonsarzt"
OURS = f'Q1\tP31\tQ294414\tS854\t"{URL}"\tS813\t+2026-10-08T00:00:00Z/11 /* peptree repair ch 2026-10-08 */'


def claim(guid: str, value: str, *urls: str, other: bool = False) -> dict:
    refs: list[dict[str, Any]] = [{"snaks": {"P854": [{"datavalue": {"value": u}}]}} for u in urls]
    if other:
        refs.append({"snaks": {"P143": [{"datavalue": {"value": {"id": "Q328"}}}]}})
    return {"id": guid, "mainsnak": {"datavalue": {"value": {"id": value}}}, "references": refs}


def main() -> None:
    exact = ledger.Strike("Q1", "P279", "Q3", "no", "why")
    every = ledger.Strike("Q2", "P17", ledger.ANY, "jp", "why")
    expect(exact.matches("Q1", "P279", "Q3") and not exact.matches("Q1", "P279", "Q4"),
           "a strike with a value vetoes only that value")
    expect(every.matches("Q2", "P17", "Q17") and every.matches("Q2", "P17", "Q29") and not every.matches("Q2", "P1001", "Q17"),
           "a strike without a value vetoes every value of that property, and no other property")
    expect(ledger.struck("Q1\tP279\tQ3 /* a */", [exact, every]) == exact and ledger.struck("Q1\tP279\tQ5 /* a */", [exact]) is None,
           "a line is struck by the strike that matches its statement")

    expect(ledger.ours_urls(OURS) == {URL} and ledger.ours_urls("Q1\tP17\tQ9 /* a */") == set(),
           "our line's cited URLs are its S854 values, unquoted")
    expect(ledger.candidates([claim("Q1$a", "Q294414", URL)], "Q294414", {URL}) == [("Q1$a", True)],
           "the only statement with the value, citing only what we cited, is ours")
    expect(ledger.candidates([claim("Q1$a", "Q294414")], "Q294414", set()) == [("Q1$a", True)],
           "an unreferenced statement from an unreferenced line of ours is ours")
    expect(ledger.candidates([claim("Q1$a", "Q294414", URL, other=True)], "Q294414", {URL}) == [("Q1$a", False)],
           "someone else's reference on it makes it not only ours")
    expect(ledger.candidates([claim("Q1$a", "Q294414"), claim("Q1$b", "Q294414")], "Q294414", set())
           == [("Q1$a", False), ("Q1$b", False)], "two statements with the value: neither is assumed ours")
    expect(ledger.candidates([claim("Q1$a", "Q5")], "Q294414", set()) == [], "a statement with another value is no candidate")

    notes = {
        "jp": "large place: 401 asked; strike Q136230953 P17 (Catalan delegation), Q5152815 P1001 (NPB commissioner),"
              " Q136213809 P279 Q83307 (generic)",
        "il": "strike Q139083417 P17 (a CV entry: Head Radiologist, Maccabi Haifa F.C.) before pasting; 4 sibling CV entries",
        "no": "large place; strike Q50810280 P279 Q3368517 (military generaladvokat is no prosecutor general); QS3 59046",
        "ai": "QS 289612; 289612 added Q112973320 P279 minister (deputy-phrase bug); removed 2026-10-05",
    }
    found = {(s.country, s.qid, s.prop, s.value) for s in note_strikes(notes)}
    expect(found == {("jp", "Q136230953", "P17", "*"), ("jp", "Q5152815", "P1001", "*"),
                     ("jp", "Q136213809", "P279", "Q83307"), ("il", "Q139083417", "P17", "*"),
                     ("no", "Q50810280", "P279", "Q3368517")},
           "every `strike` clause in the notes is read, value or not; a note about an old removal strikes nothing")
    guid = "Q1$12774DF1-9BD0-49A0-998E-C1271E593A3B"
    line = qs.removal_line(guid, "why */ not")
    expect(line == f"-STATEMENT\t{guid} /* why / not */" and qs.validate_removals([line]) == [],
           "a removal goes by GUID, and a reason cannot close its own comment")
    expect(qs.validate_removals(["-Q1\tP279\tQ3 /* a */"]) != [], "removal by value is refused: it takes only the first match")
    expect(qs.validate_removals(["-STATEMENT\tQ1$nope /* a */"]) != [], "a malformed GUID is refused")
    expect(qs.validate_removals([line, line]) != [], "a GUID twice in one batch is refused")
    expect(qs.validate_removals(["q42$12774df1-9bd0-49a0-998e-c1271e593a3b".join(["-STATEMENT\t", ""])]) == [],
           "an old lowercase GUID is well-formed")
    expect(qs.validate([line]) != [], "an add batch still refuses a removal")
    rows = [{"guid": f"Q1${g}", "qid": "Q1", "value": "Q3"} for g in ("a", "b", "c")]
    ents = {"Q1": {"claims": {"P279": [claim("Q1$a", "Q3"), claim("Q1$c", "Q9")]}}}
    sorted_ = removals.preflight(rows, ents)
    expect([r["guid"] for r in sorted_["send"]] == ["Q1$a"] and [r["guid"] for r in sorted_["gone"]] == ["Q1$b"]
           and [r["guid"] for r in sorted_["moved"]] == ["Q1$c"],
           "pre-flight sends what still holds its value, records the absent as gone, holds the changed")
    expect(STATUS == {"landed": "landed", "reverted": "reverted", "emitted": "failed"},
           "a paste-era line that never landed is a failed edit, not one still in flight")


if __name__ == "__main__":
    main()
