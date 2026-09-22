"""Pin the offline half of the reconciliation turn: no network, no key, no tokens.

The turn that asks a model which position item an office names cannot be run
on a host with no credential, but almost none of it is the request. The
shortlist rendering, the closed verdict set, the schema that constrains the
pick and the gate that refuses an off-list QID are all pure functions over
their arguments, and this runs every one of them.

Four things are pinned, and each is a way the pass could go wrong silently:

* **the rendering**, line for line, because a field that stops being printed
  is a signal the model stops seeing while the ranking keeps using it;
* **`settle` on every verdict kind**, because the closed set is only closed
  if each member routes somewhere;
* **off-shortlist refusal** by the gate, and that the schema is one shape for
  every request — a per-request schema is what defeated the prompt cache;
* **the prompt's hash and its coverage**, because a verdict is stored under
  the hash, and because every tag the ranking can derive has to be explained
  in the prompt or it moved a row without saying so.

Run it as `python -m peploop.check_reconcile` from the repository root.
"""

import dataclasses
import hashlib
import sys
from typing import Any

from pydantic import ValidationError

from peploop import check_neutral, positions, reconcile

#: A state to be local to, so the holder counts below mean something.
STATE = "Q1"

#: One synthetic row per tag the ranking can derive, with the tenure that
#: provokes it. The union of what these produce is checked against
#: `reconcile.TAGS`, which is in turn checked against the prompt — so a tag
#: added to `positions.tags_for` and explained nowhere fails here.
TAG_CASES: tuple[tuple[str, dict[str, Any], Any, Any], ...] = (
    ("not-office", {"not_office": True}, None, None),
    ("unheld", {"holders_by_country": {STATE: 0}}, None, None),
    ("abstract", {"instance_count": 1, "holders_by_country": {STATE: 5}}, None, None),
    ("generic-by-convention",
     {"instance_count": 1, "holders_by_country": {STATE: 1260}}, None, None),
    ("abolished", {"abolished": "1990-01-01"}, None, None),
    ("date-conflict", {"abolished": "1990-01-01"}, "2000-01-01", None),
    ("date-fit", {"inception": "1900-01-01"}, "1950-01-01", None),
    ("diplomatic", {"diplomatic": True, "jurisdiction_qid": "Q2"}, None, None),
    ("inbound-diplomatic", {"diplomatic": True, "jurisdiction_qid": STATE}, None, None),
    ("foreign-scoped", {"sources": ["citizen"], "country_qid": "Q2"}, None, None),
)

#: The shortlist the rendering is pinned against. Four shapes the prompt has
#: a rule for — a concrete seat, the body it sits in, a generic office a
#: state uses by convention, and an abolished foreign one — plus a fifth
#: that carries a scoping qualifier without the tag that makes it relevant.
SHORTLIST = (
    reconcile.Candidate(
        qid="Q10",
        label="Minister of Justice",
        description="head of the justice ministry",
        kinds=["minister"],
        body="Ministry of Justice",
        inception="1918-01-01",
        holders=34,
        tags=("date-fit",),
        matched="Minister of Justice",
    ),
    reconcile.Candidate(
        qid="Q11",
        label="Ministry of Justice",
        kinds=["ministry"],
        tags=("not-office",),
        matched="Ministry of Justice",
    ),
    reconcile.Candidate(
        qid="Q12",
        label="mayor",
        description="head of a municipality",
        kinds=["public office"],
        holders=1260,
        tags=("generic-by-convention",),
        scope_qualifier="P642",
        matched="mayor",
    ),
    reconcile.Candidate(
        qid="Q13",
        label="Commissioner for Supply",
        inception="1948-01-01",
        abolished="1990-01-01",
        holders=0,
        tags=("unheld", "abolished", "date-conflict", "foreign-scoped"),
        matched="Commissioner",
    ),
    reconcile.Candidate(
        qid="Q14",
        label="deputy minister",
        holders=7,
        scope_qualifier="P642",
        matched="deputy minister",
    ),
    # Not class-like, so no tag -- and still recorded with a qualifier by
    # enough of the state's own holders to be the concrete office.
    reconcile.Candidate(
        qid="Q15",
        label="deputy governor of a region",
        kinds=["deputy"],
        holders=56,
        scope_qualifier="P1001",
        matched="deputy governor",
    ),
)

EXPECTED_LINES = (
    "Q10 | Minister of Justice | head of the justice ministry | kind: minister"
    " | part of: Ministry of Justice | exists: 1918-01-01 | holders: 34"
    " | tags: date-fit | matched: Minister of Justice",
    "Q11 | Ministry of Justice | (no description) | kind: ministry"
    " | holders: uncounted | tags: not-office | matched: Ministry of Justice",
    "Q12 | mayor | head of a municipality | kind: public office | holders: 1260"
    " | tags: generic-by-convention | used with: P642 | matched: mayor",
    "Q13 | Commissioner for Supply | (no description) | exists: 1948-01-01–1990-01-01"
    " | holders: 0 | tags: unheld, abolished, date-conflict, foreign-scoped"
    " | matched: Commissioner",
    "Q14 | deputy minister | (no description) | holders: 7 | matched: deputy minister",
    "Q15 | deputy governor of a region | (no description) | kind: deputy | holders: 56"
    " | used with: P1001 | matched: deputy governor",
)

MENTION = reconcile.Mention(
    title="Minister of Justice and Public Administration",
    jurisdiction="the republic",
    start="1994",
    end="1996",
    quotes=["He served as Minister of Justice and Public Administration from 1994."],
    lang="en",
)

EXPECTED_MENTION = """# The office as written

Minister of Justice and Public Administration
jurisdiction as written: the republic
tenure: 1994–1996
article language: en

# What the article says

- “He served as Minister of Justice and Public Administration from 1994.”

# Candidate position items

- %s

Which of these is the office named above? Answer `none` rather than the closest one.""" % (
    "\n- ".join(EXPECTED_LINES),
)

#: Phrases the prompt has to keep. Each one is a rule that was got wrong
#: somewhere before it was written down.
REQUIRED_PHRASES = (
    "is the seat in it",          # a body is not the office in it
    "body-not-seat",              # ...and the verdict that says so
    "used with:",                 # the qualifier a generic office is used with
    "uncounted",                  # an uncounted holder count is not zero
    "matched",                    # a match is an explanation, not evidence
    "Prefer `none`",              # a refusal is a complete answer
)


def check_rendering(expect: Any) -> None:
    """Pin the shortlist and the whole per-office message, line for line."""
    for candidate, wanted in zip(SHORTLIST, EXPECTED_LINES):
        got = candidate.line()
        expect(got == wanted, f"{candidate.qid} renders as documented")
        if got != wanted:
            print(f"    want: {wanted}\n    got:  {got}")
    expect(
        reconcile.render_shortlist(()) == "- (nothing retrieved)",
        "an empty shortlist says so rather than rendering nothing",
    )
    expect(
        "used with:" not in SHORTLIST[4].line(),
        "a scoping qualifier below the convention floor and untagged is not shown",
    )
    expect(
        "used with: P1001" in SHORTLIST[5].line(),
        "a scoping qualifier at the floor is shown without the tag",
    )
    short = dataclasses.replace(MENTION, article="He was minister. Then he was not.")
    got = reconcile.render_mention(short, SHORTLIST)
    expect(
        "# The article (en)\n\nHe was minister. Then he was not.\n" in got,
        "an article under the cap is rendered whole after the quotes",
    )
    long = dataclasses.replace(MENTION, article="x" * (reconcile.ARTICLE_CAP + 1))
    got = reconcile.render_mention(long, SHORTLIST)
    expect(
        f"article omitted: {reconcile.ARTICLE_CAP + 1:,} characters, over the cap" in got
        and "xxxx" not in got,
        "an article over the cap is named and left out",
    )
    got = reconcile.render_mention(MENTION, SHORTLIST)
    expect(got == EXPECTED_MENTION, "the per-office message renders as documented")
    if got != EXPECTED_MENTION:
        print("    --- want ---\n" + EXPECTED_MENTION)
        print("    --- got ---\n" + got)


def check_settle(expect: Any) -> None:
    """Pin the gate on every verdict kind, and on both ways a match fails."""
    offered = [c.qid for c in SHORTLIST]
    cases = (
        ("same-office", "Q10", ("Q10", None)),
        ("renamed", "Q11", ("Q11", None)),
        ("generic-class", "Q12", (None, None)),
        ("body-not-seat", "Q11", (None, None)),
        ("wrong-office", "Q13", (None, None)),
        ("none", None, (None, None)),
    )
    for kind, chosen, wanted in cases:
        got = reconcile.settle(kind, chosen, offered)
        expect(got == wanted, f"settle({kind}, {chosen}) is {wanted}, got {got}")
    expect(
        {kind for kind, _chosen, _wanted in cases} == set(reconcile.KINDS),
        "every verdict kind in the closed set is exercised",
    )
    expect(
        reconcile.settle("same-office", None, offered) == (None, "match-without-qid"),
        "a match naming no item is refused",
    )
    expect(
        reconcile.settle("same-office", "Q99", offered) == (None, "off-shortlist"),
        "a QID that was never offered is refused by the gate",
    )
    expect(
        reconcile.settle("renamed", "Q10", []) == (None, "off-shortlist"),
        "nothing is resolvable against an empty shortlist",
    )


def check_schema(expect: Any) -> None:
    """Pin the answer shape, and that it is the same shape for every request.

    The pick is *not* closed by the schema: it was, and the per-request
    `Literal` put the shortlist inside the cached prefix, so every request
    wrote the prompt to cache and read nothing. `settle` is the gate.
    """
    model = reconcile.verdict_schema()
    expect(model is reconcile.verdict_schema(), "the schema is one object for all requests")
    good = {"qid": "Q10", "kind": "same-office", "confidence": "high",
            "evidence": "Minister of Justice", "reason": "same seat"}
    expect(model(**good).qid == "Q10", "an offered QID validates")
    expect(
        model(**{**good, "qid": None, "kind": "none"}).qid is None,
        "a null pick validates, which is how a refusal is expressed",
    )
    expect(
        model(**{**good, "qid": "Q99"}).qid == "Q99"
        and reconcile.settle("same-office", "Q99", [c.qid for c in SHORTLIST])
        == (None, "off-shortlist"),
        "an off-shortlist QID passes the schema and is stopped by the gate",
    )
    for field, value, what in (
        ("kind", "maybe", "a verdict outside the closed set"),
        ("confidence", "certain", "a confidence outside the three levels"),
    ):
        try:
            model(**{**good, field: value})
        except ValidationError:
            expect(True, f"{what} is rejected by the schema")
        else:
            expect(False, f"{what} is rejected by the schema")
    try:
        model(**{**good, "note": "extra"})
    except ValidationError:
        expect(True, "an unknown key is rejected by the schema")
    else:
        expect(False, "an unknown key is rejected by the schema")


def check_prompt(expect: Any) -> None:
    """Pin the prompt's hash, its coverage of the verdicts, and of the tags."""
    text, digest = reconcile.system_prompt()
    again, digest_again = reconcile.system_prompt()
    expect(digest == digest_again and text == again, "the prompt reads stably")
    expect(
        digest == hashlib.sha256(reconcile.PROMPT_PATH.read_bytes()).hexdigest(),
        f"the hash is the sha256 of the file: {digest[:12]}",
    )
    missing = [kind for kind in reconcile.KINDS if kind not in text]
    expect(not missing, f"every verdict kind is explained in the prompt {missing or ''}")
    missing = [tag for tag in reconcile.TAGS if tag not in text]
    expect(not missing, f"every tag is explained in the prompt {missing or ''}")
    missing = [phrase for phrase in REQUIRED_PHRASES if phrase not in text]
    expect(not missing, f"the prompt keeps its hard-won rules {missing or ''}")
    expect(
        reconcile.PROMPT_PATH in check_neutral.files(),
        "the prompt is covered by the neutrality check",
    )


def check_tags(expect: Any) -> None:
    """Pin that the tags the ranking derives are exactly the ones documented."""
    produced: set[str] = set()
    for tag, row, start, end in TAG_CASES:
        tags = positions.tags_for(row, STATE, start, end)
        expect(tag in tags, f"a row with {sorted(row)} is tagged {tag} (got {tags})")
        produced.update(tags)
    expect(
        produced == set(reconcile.TAGS),
        f"the tags the ranking derives are the ones the prompt lists"
        f" (only here: {sorted(produced - set(reconcile.TAGS))};"
        f" only listed: {sorted(set(reconcile.TAGS) - produced)})",
    )


def check_request(expect: Any) -> None:
    """Pin the request's shape, assembled without a key and without sending it."""
    request = reconcile.request_for(MENTION, SHORTLIST)
    text, _digest = reconcile.system_prompt()
    expect(request["system"][0]["text"] == text, "the frozen prompt is the system block")
    expect(
        request["system"][0].get("cache_control") == {"type": "ephemeral"},
        "the system block carries the cache breakpoint",
    )
    expect(
        [m["role"] for m in request["messages"]] == ["user"],
        "one user turn carries the office and its candidates",
    )
    expect(
        request["messages"][0]["content"] == EXPECTED_MENTION,
        "the user turn is the rendering pinned above",
    )
    expect(
        request["thinking"] == {"type": "adaptive"}
        and request["output_config"]["effort"] == reconcile.EFFORT,
        "thinking and effort are set the way the rest of peploop sets them",
    )


def main() -> int:
    """Run every pin and report, without touching the network or a key."""
    failures: list[str] = []

    def expect(condition: bool, message: str) -> None:
        print(("  ok   " if condition else "  FAIL ") + message)
        if not condition:
            failures.append(message)

    for name, check in (
        ("rendering", check_rendering),
        ("settle", check_settle),
        ("schema", check_schema),
        ("prompt", check_prompt),
        ("tags", check_tags),
        ("request", check_request),
    ):
        print(f"{name}:")
        check(expect)
    print(f"{len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
