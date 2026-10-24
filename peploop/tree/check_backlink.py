"""Pin the back-link lane offline: which unit gets a `P1313`, and what its office gets back.

    .venv/bin/python -m peploop.tree.check_backlink
"""

from peploop.tree import backlink, qs
from peploop.checks import ent, expect
from peploop.tree.check_fixture import XX

UNIT, COUNCIL, OTHER = "Q910001", "Q910002", "Q910003"
MAYOR, LANDRAT, COUNCILLOR, GENERIC = "Q30185", "Q514725", "Q708492", "Q920099"


def office(qid: str, label: str, head: str | None, named_by: set[str] | None = None, **claims: list[str]) -> backlink.Office:
    types = {qid, *([head] if head else []), *claims.get("P279", [])}
    return backlink.Office(qid, ent({"en": label}, **claims), types, named_by or set())


def ended(o: backlink.Office, prop: str = "P576") -> backlink.Office:
    o.entity["claims"][prop] = [{"rank": "normal", "mainsnak": {"datavalue": {"value": {
        "time": "+2014-01-01T00:00:00Z", "precision": 9}}}}]
    return o


def main() -> None:
    unit = ent({"en": "Lindau"}, P194=[COUNCIL])
    mayor = office("Q930001", "mayor of Lindau", MAYOR, P279=[MAYOR], P1001=[UNIT])
    plan = backlink.plan_unit(UNIT, unit, {mayor.qid: mayor})
    expect(plan.verdict == "line" and plan.office == mayor.qid, "one current head office scoped to the unit: a line")
    via_council = office("Q930002", "Landrat of Lindau", LANDRAT, P279=[LANDRAT], P2389=[COUNCIL])
    expect(backlink.plan_unit(UNIT, unit, {via_council.qid: via_council}).office == via_council.qid,
           "a measured local head scoped through the unit's council counts")
    lord = office("Q930003", "lord mayor of Lindau", MAYOR, P279=[MAYOR], P1001=[UNIT])
    plan = backlink.plan_unit(UNIT, unit, {mayor.qid: mayor, lord.qid: lord})
    expect(plan.verdict == "two_heads" and plan.office is None, "two current head offices: skipped, not guessed")
    old = ended(office("Q930004", "mayor of Lindau (1950-2014)", MAYOR, P279=[MAYOR], P1001=[UNIT]))
    expect(backlink.plan_unit(UNIT, unit, {old.qid: old}).verdict == "only_ended", "an abolished office: no line")
    expect(backlink.plan_unit(UNIT, unit, {old.qid: old, mayor.qid: mayor}).office == mayor.qid,
           "an abolished office beside a current one does not make two")
    podesta = office("Q930005", "podestà of Lindau", MAYOR, P279=["Q694019"], P1001=[UNIT])
    expect(backlink.plan_unit(UNIT, unit, {podesta.qid: podesta}).verdict == "only_ended",
           "an office of a regime that ended is history, though its item records no end")
    linked = ent({"en": "Lindau"}, P1313=[mayor.qid])
    expect(backlink.plan_unit(UNIT, linked, {mayor.qid: mayor}).verdict == "linked",
           "a unit that already has P1313: no line")
    councillor = office("Q930006", "member of Lindau council", None, P279=[COUNCILLOR], P2389=[COUNCIL])
    expect(backlink.plan_unit(UNIT, unit, {councillor.qid: councillor}).verdict == "no_office",
           "a councillor is no head: the unit goes to the mint queue")
    expect(backlink.plan_unit(UNIT, unit, {councillor.qid: councillor, mayor.qid: mayor}).office == mayor.qid,
           "a councillor beside the mayor is ignored")
    elsewhere = office("Q930007", "mayor of Lindau", MAYOR, {OTHER}, P279=[MAYOR], P2389=[COUNCIL])
    expect(backlink.plan_unit(UNIT, unit, {elsewhere.qid: elsewhere}).verdict == "heads_another",
           "an office reached only through a council and linked by another place may be that place's")
    seat = office("Q930008", "mayor of Lindau", MAYOR, {OTHER}, P279=[MAYOR], P1001=[UNIT])
    expect(backlink.plan_unit(UNIT, unit, {seat.qid: seat}).office == seat.qid,
           "the town the unit seats may share the unit's own head office")

    generic = office(GENERIC, "mayor of a place in Ruritania", MAYOR, {UNIT, OTHER}, P279=[MAYOR])
    on_generic = ent({"en": "Lindau"}, P1313=[GENERIC])
    plan = backlink.plan_unit(UNIT, on_generic, {GENERIC: generic})
    expect(plan.verdict == "linked" and plan.linked is None, "a generic class in P1313: no action, not ours to fix")
    listed = office("Q930009", "mayor", MAYOR, {UNIT}, P279=[MAYOR])
    expect(backlink.plan_unit(UNIT, ent({"en": "Lindau"}, P1313=[listed.qid]), {listed.qid: listed},
                              generic={listed.qid}).linked is None, "a class on the generic list is not completed")
    bare = office("Q930010", "mayor of Lindau", MAYOR, {UNIT}, P279=[MAYOR])
    plan = backlink.plan_unit(UNIT, ent({"en": "Lindau"}, P1313=[bare.qid]), {bare.qid: bare})
    expect(plan.linked == bare.qid, "the unit's own office in its P1313 is completed")

    got = {(d["prop"], d["value"], d["disposition"]) for d in backlink.office_decisions(bare, UNIT, XX)}
    expect(got == {("P1001", UNIT, "apply"), ("P17", "Q900001", "apply")},
           "an office with no scope gets the unit as P1001 and the state as P17")
    expect(backlink.office_decisions(mayor, UNIT, XX) == [{"qid": mayor.qid, "prop": "P17", "value": "Q900001",
                                                          "disposition": "apply", "rule": "jurisdiction"}],
           "an office already scoped to the unit gets only its state")
    abroad = office("Q930011", "mayor of Lindau", MAYOR, P279=[MAYOR], P1001=[OTHER])
    expect(backlink.office_decisions(abroad, UNIT, XX) == [], "an office scoped elsewhere is left to the repair")
    national = office("Q930012", "mayor of Lindau", MAYOR, P279=[MAYOR], P1001=[UNIT, "Q900001"])
    expect(backlink.office_decisions(national, UNIT, XX) == [], "no P17 beside a P1001 that names the state")
    before = office("Q930013", "mayor of Lindau", MAYOR, P279=[MAYOR], P1001=[UNIT])
    before.entity["claims"]["P576"] = [{"rank": "normal", "mainsnak": {"datavalue": {"value": {
        "time": "+1980-01-01T00:00:00Z", "precision": 9}}}}]
    before.entity["claims"]["P571"] = [{"rank": "normal", "mainsnak": {"datavalue": {"value": {
        "time": "+1960-01-01T00:00:00Z", "precision": 9}}}}]
    d = backlink.office_decisions(before, UNIT, XX)
    expect([(x["prop"], x["disposition"], x["rule"]) for x in d] == [("P17", "skip", "era_mismatch")],
           "no P17 for a state that did not exist while the office did")

    line = backlink.unit_line(UNIT, mayor.qid)
    expect(line.startswith(f"{UNIT}\tP1313\t{mayor.qid} /* ") and "heads its government" in line
           and "peptree" not in line and "2026" not in line,
           "a unit's line is plain, and its summary names neither the tool nor a date")
    expect(qs.validate([line, qs.line({"qid": mayor.qid, "prop": "P1001", "value": UNIT})]) == [],
           "a place's P1313 and its office's P1001 pass one batch")
    errs = qs.validate([line, qs.line({"qid": UNIT, "prop": "P17", "value": "Q900001"})])
    expect(len(errs) == 1 and "a place" in errs[0], "a place carries no office statement beside its P1313")
    expect(qs.validate([line, backlink.unit_line(OTHER, mayor.qid)]) == [],
           "two places may share one head office")
    expect(any("is no property" in e for e in qs.validate([f"{UNIT}\tP6\tQ5 /* x */"])),
           "a property peptree does not write is refused")
    expect(qs.validate([line, backlink.unit_line(UNIT, lord.qid)]) != [], "one place, one head office per batch")


if __name__ == "__main__":
    main()
