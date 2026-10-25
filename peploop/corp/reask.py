"""Pick the bodies whose stored answer a decide prompt change would alter, to ask only those again.

A decide prompt change re-keys every request, and asking a whole country
again costs far more than the bodies it affects. Each class here is read
from the newest stored answers: seats with no date at all (snapshot lists),
seats whose end quote names an arrest or an investigation (an event read as
an end), and institutions whose head the quote calls a conductor, artistic
director, curator or editor. Only bodies that passed their gates in the
last plan are counted for these: the others write nothing whatever their
seats say. One class is about control instead, and counts in a country
whose spec writes the municipal tier: bodies the answer put at the
municipal level without calling them controlled (several municipalities
holding it together, an inter-municipal owner), which the prompt now
calls control.

    .venv/bin/python -m peploop.corp.reask [cc …]
"""

import re
import sys
from typing import Any

from peploop import llm, tenure
from peploop.corp import country, decide, wd

#: A head named by an artistic or editorial title, in the languages run.
ARTISTIC = re.compile(
    r"conduct|dirigent|chef d'orchestre|direttore musicale|artistic|artisti|künstler|kunstner|konstnär|"
    r"umělec|umeleck|artystyczn|művészeti|taiteellin|καλλιτεχν|curator|kurator|conservat|"
    r"editor|rédact|redakt|redatt|chefredakt|főszerkeszt|šéfredakt", re.IGNORECASE)


def classes(answer: dict[str, Any]) -> set[str]:
    """Which re-ask classes an answer falls in."""
    out = set()
    for seat in answer.get("seats", []):
        if not seat.get("start") and not seat.get("end"):
            out.add("undated")
        if seat.get("end") and tenure.names_end_event(seat.get("quote")):
            out.add("event_end")
        if answer.get("kind") == "institution" and seat.get("role") == "head" and ARTISTIC.search(seat.get("quote") or ""):
            out.add("artistic_head")
    control = answer.get("control") or {}
    if control.get("level") == "municipal" and control.get("verdict") != "state" and answer.get("active"):
        out.add("municipal_uncontrolled")
    return out


def select(cc: str) -> dict[str, set[str]]:
    """{QID: its classes} for a country's bodies to ask again."""
    passed = {r[0] for r in wd.conn().execute(
        "SELECT DISTINCT qid FROM pcorp_decision WHERE country = %s AND prop <> '-'", (cc,))}
    municipal = "municipal" in country.get(cc).tiers
    out = {}
    for r in decide.from_ledger(cc):
        c = classes(r["answer"])
        c = (c if r["qid"] in passed else set()) | (c & {"municipal_uncontrolled"} if municipal else set())
        if c:
            out[r["qid"]] = c
    return out


def unit_cost(cc: str) -> float:
    """The mean list price of one decide call for this country, from its newest answers."""
    rows = wd.conn().execute(
        "SELECT DISTINCT ON (qid) model, usage FROM pcorp_call WHERE country = %s AND request ? 'offered'"
        " ORDER BY qid, created_at DESC", (cc,)).fetchall()
    costs = [llm.cost(m, u) or 0.0 for m, u in rows]
    return sum(costs) / len(costs) if costs else 0.0


def main(ccs: list[str]) -> None:
    ccs = ccs or [r[0] for r in wd.conn().execute("SELECT DISTINCT country FROM pcorp_decision ORDER BY 1")]
    total, dollars = 0, 0.0
    for cc in ccs:
        picked = select(cc)
        bodies = len(decide.from_ledger(cc))
        price = unit_cost(cc) * len(picked)
        tally = {k: sum(k in c for c in picked.values())
                 for k in ("undated", "event_end", "artistic_head", "municipal_uncontrolled")}
        print(f"{cc}: {len(picked)} of {bodies} bodies, ~${price:.2f} ({', '.join(f'{k} {v}' for k, v in tally.items())})")
        print("  " + " ".join(sorted(picked)))
        total += len(picked)
        dollars += price
    print(f"total: {total} bodies, ~${dollars:.2f}")


if __name__ == "__main__":
    wd.init()
    main(sys.argv[1:])
