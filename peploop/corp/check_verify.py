"""Pin the narrow checks' plumbing: what each call is told, and which statements go to it, offline.

    .venv/bin/python -m peploop.corp.check_verify
"""

from peploop import memo
from peploop.corp import decide, rules, verify, wd
from peploop.corp.check_rules import answer
from peploop.checks import expect

MESSAGE = ("# Item Q900999\n\n```article lang=xx title='Probe' url=u\nProbe\nFormed: 2008\n\n"
           "The Probe Office keeps the register of companies and publishes their accounts for anyone to read online.\n"
           "It belongs to the state.\n```")


def messages() -> None:
    names = {"Q900999": "Probe Office", "Q900001": "Probeland"}
    text = verify.message("Q900999", "Q900001", verify.PROPERTIES["P127"], "It belongs to the state.", names)
    expect("Link: owned by" in text, "an owner link is checked as owned by")
    text = verify.message("Q900999", "Q900002", verify.PROPERTIES["P749"], "It is part of the ministry.", names)
    expect("Link: parent organization" in text, "a parent link is checked as parent organization")
    opening = verify.opening(MESSAGE, "xx")
    expect(opening.startswith("The Probe Office keeps"), "a class is shown with the article's opening, past its infobox")
    text = verify.class_message("Q900999", rules.STATUTORY["regulator"], "It belongs to the state.", opening, names)
    expect("Claim: a regulator" in text and "keeps the register" in text, "the class claim carries the opening")


def routing() -> None:
    """Every written class goes to the check; a refused one comes back."""
    req = {"qid": "Q900999", "offered": ["Q900001"], "message": MESSAGE, "links": {}, "articles": [],
           "answer": {**answer(kind="institution", owners=(), quote="It belongs to the state."), "statutory": "regulator"}}
    decisions = [{"qid": "Q900999", "prop": "P31", "value": rules.STATUTORY["regulator"], "disposition": "apply"},
                 {"qid": "Q900999", "prop": "P31", "value": "Q1780371", "disposition": "apply"}]
    asked: list[str] = []
    store: dict[str, dict] = {}

    class Conn:
        def execute(self, sql, args):
            store[args[0]] = {"supports": False}

    real = verify.ask, decide.recorded, wd.conn, memo.labels_of
    verify.ask = lambda text: (asked.append(text) or verify.Verdict(supports=False, reason=""), {})  # type: ignore[assignment]
    decide.recorded = lambda key: store.get(key)  # type: ignore[assignment]
    wd.conn = lambda: Conn()  # type: ignore[assignment]
    memo.labels_of = lambda qids, langs: {}  # type: ignore[assignment]
    try:
        out = verify.refused("xx", decisions, [req], log=lambda m: None)
    finally:
        verify.ask, decide.recorded, wd.conn, memo.labels_of = real  # type: ignore[assignment]
    expect(out == {("Q900999", "P31", rules.STATUTORY["regulator"])} and len(asked) == 1,
           "a written statutory class is checked once and comes back refused; the municipal marker is no class")


def main() -> None:
    messages()
    routing()


if __name__ == "__main__":
    main()
