"""Pick the bodies whose stored answer a decide prompt change would alter, to ask only those again.

A decide prompt change re-keys every request, and asking a whole country
again costs far more than the bodies it affects. Each class here is read
from the newest stored answers: seats with no date at all (snapshot lists),
seats whose end quote names an arrest or an investigation (an event read as
an end), and institutions whose head the quote calls a conductor, artistic
director, curator or editor. Only bodies that passed their gates in the
last plan are counted: the others write nothing whatever their seats say.

    .venv/bin/python -m peploop.corp.reask [cc …]
"""

import re
import sys
from typing import Any

from peploop import llm
from peploop.corp import decide, wd

#: An end read from an event rather than from the tenure ending, by language (stems).
EVENTS = re.compile(
    r"arrest|charged|indict|investigat|suspend|detain|"
    r"verhaftet|festgenommen|ermittl|angeklagt|suspendiert|"
    r"arrêté|interpellé|mis en examen|enquête|suspendu|"
    r"detenid|arrestad|investigaci|imputad|arrestat|indagat|indagine|sospes|detid|investigaç|"
    r"zatrzyman|aresztowan|śledztw|zarzut|zawieszon|zatčen|obviněn|vyšetřov|obvinen|zadržan|"
    r"letartóztat|őrizetbe|nyomozás|vádat|felfüggeszt|reținut|anchet|inculpat|suspendat|"
    r"арестуван|задържан|разследван|обвин|отстранен|συνελήφθη|δίωξη|έρευνα|"
    r"uhićen|pritvoren|istrag|optužen|aretiran|preiskav|vahistati|kahtlustus|aizturēt|apcietināt|"
    r"izmeklēšan|apsūdz|sulaikyt|suimt|ikiteisminį|pidätet|tutkinta|syyte|"
    r"anhållen|häktad|anholdt|sigtet|gearresteerd|aangehouden|geschorst", re.IGNORECASE)
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
        if seat.get("end") and EVENTS.search(seat.get("quote") or ""):
            out.add("event_end")
        if answer.get("kind") == "institution" and seat.get("role") == "head" and ARTISTIC.search(seat.get("quote") or ""):
            out.add("artistic_head")
    return out


def select(cc: str) -> dict[str, set[str]]:
    """{QID: its classes} for a country's bodies to ask again."""
    passed = {r[0] for r in wd.conn().execute(
        "SELECT DISTINCT qid FROM pcorp_decision WHERE country = %s AND prop <> '-'", (cc,))}
    return {r["qid"]: c for r in decide.from_ledger(cc) if r["qid"] in passed and (c := classes(r["answer"]))}


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
        tally = {k: sum(k in c for c in picked.values()) for k in ("undated", "event_end", "artistic_head")}
        print(f"{cc}: {len(picked)} of {bodies} bodies, ~${price:.2f} ({', '.join(f'{k} {v}' for k, v in tally.items())})")
        print("  " + " ".join(sorted(picked)))
        total += len(picked)
        dollars += price
    print(f"total: {total} bodies, ~${dollars:.2f}")


if __name__ == "__main__":
    wd.init()
    main(sys.argv[1:])
