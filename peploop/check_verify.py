"""Pin the offline half of the verifier: no network, no key, no tokens.

The verifier is the last gate before an edit is written, and almost none of
it is the request. What the model is shown, the one answer shape every
request shares, the key a verdict is stored under, and how each verdict lands
in the policy are all pure functions over their arguments; this runs every one
of them. Four things are pinned, each a way the stage could go wrong silently:

* **the rendering**, line for line, because a field that stops being printed
  is evidence the model stops seeing;
* **the key**, because a verdict filed under the wrong content is either
  re-asked forever or never re-asked;
* **the prompt's coverage**, because every verdict the schema allows and
  every tag the policy rejects on has to be explained, or the model is asked
  about something it was never told;
* **the policy's reading of each verdict**, because `supported` is the only
  one that passes and that has to stay true whatever the prompt says.

Run it as `python -m peploop.check_verify` from the repository root.
"""

import hashlib
import sys
from dataclasses import replace

from pydantic import ValidationError

from peploop import check_neutral, check_policy, dates, policy, reconcile, verify

PERSON = "Q0000009"
OFFICE = "Q0000001"

OFFICE_LINE = reconcile.Candidate(
    qid=OFFICE,
    label="Minister of Justice",
    description="head of the justice ministry",
    kinds=["minister"],
    body="Ministry of Justice",
    inception="1918-01-01",
    holders=34,
    tags=("date-fit",),
)

POSITION = verify.Edit(
    person_qid=PERSON,
    person_label="Ana Example",
    property="P39",
    value={"entity-type": "item", "id": OFFICE},
    value_label="Minister of Justice",
    value_description="head of the justice ministry",
    qualifiers={"P580": dates.time_value("2018"), "P582": dates.time_value("2022-05-13")},
    office=OFFICE_LINE,
    mention={"title": "ministrica za pravosodje", "jurisdiction": "Republika",
             "start": "2018", "end": "2022-05-13", "lang": "aa"},
    existing=[f"{OFFICE} Minister of Justice [2010..2014]"],
    quotes=[("aa", "Leta 2018 je postala ministrica za pravosodje.")],
    article_lang="aa",
    article="Ana Example je politik. Leta 2018 je postala ministrica za pravosodje.",
)

EXPECTED_POSITION = """# The edit as it would land

item: Q0000009 Ana Example
property: P39 position
value: Q0000001 Minister of Justice -- head of the justice ministry
qualifiers: start: 2018 (year); end: 2022-05-13 (day)

# The office, as an item

Q0000001 | Minister of Justice | head of the justice ministry | kind: minister\
 | part of: Ministry of Justice | exists: 1918-01-01 | holders: 34 | tags: date-fit

# The office, as the article wrote it

ministrica za pravosodje
jurisdiction as written: Republika
tenure as written: 2018–2022-05-13

# What the item already records for P39

- Q0000001 Minister of Justice [2010..2014]

# The quotes

- (aa) “Leta 2018 je postala ministrica za pravosodje.”

# The article (aa)

Ana Example je politik. Leta 2018 je postala ministrica za pravosodje.

Does this article support exactly this edit, about this person, at this precision?\
 Answer with the verdict that names what is wrong, or `supported`."""

BIRTH = verify.Edit(
    person_qid=PERSON,
    person_label="Ana Example",
    property="P569",
    value=dates.time_value("1970-01-02"),
    existing=["1970 (year)"],
    quotes=[("aa", "rojena 2. januarja 1970")],
    article_lang="aa",
    article="x" * (verify.ARTICLE_CAP + 1),
)

EXPECTED_BIRTH = """# The edit as it would land

item: Q0000009 Ana Example
property: P569 birth date
value: 1970-01-02 (day)
qualifiers: none

# What the item already records for P569

- 1970 (year)

# The quotes

- (aa) “rojena 2. januarja 1970”

# The article (aa)

article omitted: 20,001 characters, over the cap

Does this article support exactly this edit, about this person, at this precision?\
 Answer with the verdict that names what is wrong, or `supported`."""

#: Phrases the prompt must keep: each is a rule a reviewed rejection taught.
REQUIRED_PHRASES = (
    "A demonym is a citizenship of the state it names",
    "A year is not a day",
    "An office of a named body needs the body on the edit",
    "an incumbent has no end date",
    "Background knowledge may inform, never decide",
    "is exactly what an edit carrying the article's dates sharpens",
    "names a people,\n  not a passport",
    "A scheduled date is not a recorded one",
    "is a date, not a fact",
    "An election year dates the seat it won, at year precision and no finer",
    "seated only in\n  the year after its election",
    "A career span is not a tenure",
    "65 members of both\n  chambers of one national assembly",
)


def main() -> int:
    failures: list[str] = []

    def expect(ok: bool, message: str) -> None:
        print(("  ok   " if ok else "  FAIL ") + message)
        if not ok:
            failures.append(message)

    print("rendering:")
    got = verify.render_edit(POSITION)
    expect(got == EXPECTED_POSITION, "a position edit renders as pinned")
    if got != EXPECTED_POSITION:
        print("    --- want ---\n" + EXPECTED_POSITION + "\n    --- got ---\n" + got)
    got = verify.render_edit(BIRTH)
    expect(got == EXPECTED_BIRTH, "a date edit renders as pinned, the long article omitted")
    if got != EXPECTED_BIRTH:
        print("    --- want ---\n" + EXPECTED_BIRTH + "\n    --- got ---\n" + got)
    bare = verify.render_edit(verify.Edit(person_qid=PERSON, person_label=None, property="P27",
                                          value={"entity-type": "item", "id": "Q2"}))
    expect("- nothing" in bare and "- none" in bare and "article not available" in bare,
           "an edit with nothing behind it says so in every section")
    noted = verify.render_edit(replace(POSITION, note=verify.CAREER_NOTE.format(
        terms=2, end=", open as the last term is")))
    expect("note: The item keeps one statement for this office" in noted
           and "\n".join(line for line in noted.split("\n")
                          if not line.startswith("note: ")) == EXPECTED_POSITION,
           "a career's note is one line after the qualifiers, and nothing else moves")

    print("the key:")
    quals = {"P580": dates.time_value("2018"), "_sources": [{"lang": "aa", "rev": 7}]}
    key = verify.content_key(PERSON, "P39", POSITION.value, quals)
    expect(key == verify.content_key(PERSON, "P39", POSITION.value,
                                     {**quals, "_reason": "x", "_basis": "y"}),
           "peploop's own bookkeeping keys are not part of it")
    expect(key != verify.content_key(PERSON, "P39", POSITION.value,
                                     {**quals, "_sources": [{"lang": "aa", "rev": 8}]}),
           "a re-fetched article is a new question")
    expect(key != verify.content_key(PERSON, "P39", POSITION.value,
                                     {**quals, "P580": dates.time_value("2019")}),
           "a different tenure is a different question")
    expect(key != verify.content_key("Q0000010", "P39", POSITION.value, quals),
           "and so is the same edit on another person")
    expect(key != verify.content_key(PERSON, "P39", POSITION.value, {**quals, "_terms": 2}),
           "and a career dated from its terms, which the verifier is told about")
    expect(key != verify.content_key(PERSON, "P39", POSITION.value,
                                     {**quals, "_sources": [{"lang": "aa", "rev": 7, "dates": "P582"}]}),
           "and a source shown as dating the end")

    print("the answer shape:")
    answer = verify.Answer(verdict="supported", confidence="high", evidence="e", reason="r")
    expect(answer.verdict == "supported", "an answer parses")
    try:
        verify.Answer(verdict="probably", confidence="high", evidence="e", reason="r")
        expect(False, "an off-set verdict is refused by the schema")
    except ValidationError:
        expect(True, "an off-set verdict is refused by the schema")
    try:
        verify.Answer(verdict="supported", confidence="high", evidence="e", reason="r", qid="Q1")
        expect(False, "an unknown key is refused by the schema")
    except ValidationError:
        expect(True, "an unknown key is refused by the schema")

    print("the request:")
    request = verify.request_for(BIRTH)
    text, digest = verify.system_prompt()
    expect(request["system"][0]["text"] == text, "the frozen prompt is the system block")
    expect(request["system"][0].get("cache_control") == {"type": "ephemeral"},
           "and carries the cache breakpoint")
    expect([m["role"] for m in request["messages"]] == ["user"]
           and request["messages"][0]["content"] == EXPECTED_BIRTH,
           "one user turn carries the rendering pinned above")
    expect(request["thinking"] == {"type": "adaptive"}
           and request["output_config"]["effort"] == verify.EFFORT,
           "thinking is adaptive and the effort is set explicitly")
    expect(request["model"] == verify.MODEL, "the model is the verifier's, not the extractor's")

    print("the prompt:")
    expect(digest == hashlib.sha256(verify.PROMPT_PATH.read_bytes()).hexdigest(),
           f"the hash is the sha256 of the file: {digest[:12]}")
    missing = [v for v in verify.VERDICTS if f"`{v}`" not in text]
    expect(not missing, f"every verdict is explained in the prompt {missing or ''}")
    missing = [t for t in policy.REJECTING_TAGS if f"`{t}`" not in text]
    expect(not missing, f"every tag the policy rejects on is explained {missing or ''}")
    missing = [p for p in REQUIRED_PHRASES if p not in text]
    expect(not missing, f"the prompt keeps its hard-won rules {missing or ''}")
    expect(verify.PROMPT_PATH in check_neutral.files(),
           "the prompt is covered by the neutrality check")

    print("what the policy makes of each verdict:")
    for verdict in verify.VERDICTS:
        case = check_policy.case(verification={"verdict": verdict, "confidence": "high"})
        got = policy.decide(case)
        want = policy.ACCEPTED if verdict == verify.SUPPORTED else policy.SKIPPED
        expect(got.status == want, f"{verdict} at high confidence -> {want} ({got.rule})")
    case = check_policy.case(verification={"verdict": "supported", "confidence": "low"})
    expect(policy.decide(case).status == policy.SKIPPED,
           "supported at low confidence is still skipped")
    expect(policy.SUPPORTED == verify.SUPPORTED, "the policy and the verifier agree on the word")

    print(f"{len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
