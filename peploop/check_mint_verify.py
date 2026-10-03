"""Pin the verify pass and the rules that decide every candidate.

Minting is unsupervised, so the order of `mint.RULES` is the whole policy: a
duplicate must beat a `mint` verdict, a disagreement must be a skip and never a
queue, and nothing under the floor may cost a token. Each rule gets a fixture
that it, and no earlier rule, decides. The spec builder's alias and parent
rules, the gate on the verifier's QIDs, the prompt's coverage of every closed
value, and the ledger and audit protections are pinned beside them. Every live
read goes through a stubbed `Context`; the ledger case runs against temporary
tables shadowing the real ones, so nothing stored is touched.

Run it as `python -m peploop.check_mint_verify` from the repository root.
"""

import sys
from collections import Counter
from typing import Any

import psycopg

from peploop import db, mint, offices
from peploop.mint import Attestation, Candidate, Context, MintVerdict, PositionRow

STATE = "Q900"
BODY = "Q910"
SIB_PARENT = "Q920"  # the state's own "minister of Alvania" class

LABELS = {STATE: "Alvania", BODY: "Ministry of Health of Alvania", SIB_PARENT: "minister of Alvania",
          "Q83307": "minister", "Q294414": "public office", "Q901": "Ostra"}

BODY_ITEM = {
    "id": BODY, "labels": {"en": {"language": "en", "value": "Ministry of Health of Alvania"}},
    "claims": {"P31": [{"rank": "normal", "mainsnak": {"datavalue": {"value": {"id": "Q327333"}}}}],
               "P17": [{"rank": "normal", "mainsnak": {"datavalue": {"value": {"id": STATE}}}}]},
}


def _claim(prop: str, *qids: str) -> list[dict[str, Any]]:
    return [{"rank": "normal", "mainsnak": {"datavalue": {"value": {"id": q}}}} for q in qids]


#: What the stubbed item reader answers for the QIDs an `exists` may name.
CLAIMS = {
    "Q950": {"claims": {"P17": _claim("P17", STATE)}},        # the state's own office
    "Q952": {"claims": {"P1001": _claim("P1001", "Q901")}},   # a subdivision's office
    "Q953": {"claims": {"P17": _claim("P17", "Q999")}},       # another state's
    "Q954": {"claims": {"P17": _claim("P17", STATE)}},        # a mission, see DIPLOMATIC
}
DIPLOMATIC = {"Q954"}
COUNCIL = "Q930"  # the council every minister of the state sits in


def siblings() -> offices.Siblings:
    return offices.Siblings(
        parents={"minister": Counter({SIB_PARENT: 5})},
        metaclass_by_parent={SIB_PARENT: Counter({"Q294414": 5})},
        metaclasses=Counter({"Q294414": 9}),
        bodies=Counter({BODY: 1, COUNCIL: 12}),
    )


def ctx(**kw: Any) -> Context:
    base: dict[str, Any] = dict(
        state_qid=STATE, langs=["es"], state_names=["Alvania", "República de Alvania"],
        siblings=siblings(), closure={SIB_PARENT, "Q83307", "Q1501800", "Q140686"},
        index=[PositionRow("Q950", "Minister of Finance of Alvania", ["minister of Alvania"])],
        labels_of=lambda qids: {q: LABELS[q] for q in qids if q in LABELS},
        resolve=lambda qids: {q: BODY_ITEM for q in qids if q == BODY},
        run_labels=lambda _cand: [], source_ok=lambda _url: True,
        lookup=lambda _text, _lang, _state: [], items=lambda _qids: {},
        subdivisions=["Q901"],
        anchors=[mint.Anchor("gov/Q901", "subnational.executive", "governor",
                             {"en": "Governor of Ostra", "es": "gobernador de Ostra"},
                             jurisdiction="Q901")],
        claims=lambda qids: {q: CLAIMS.get(q, {}) for q in qids},
        diplomatic=lambda qid: qid in DIPLOMATIC,
    )
    base.update(kw)
    return Context("zz", **base)


def att(person: str, current: bool = False, title: str | None = None, lang: str | None = "es") -> Attestation:
    return Attestation(person=person, current=current, title=title, lang=lang,
                       start="2021" if current else "1990", end=None if current else "1994")


def cand(**kw: Any) -> Candidate:
    draft = dict(decision="office", archetype="minister", single_seat=True,
                 labels={"en": "Minister of Health of Alvania", "es": "ministro de Salud de Alvania"},
                 parent_qid=None, body_qid=BODY, jurisdiction_qid=None, replaces_qid=None,
                 exists_qid=None)
    draft.update(kw.pop("draft", {}))
    base: dict[str, Any] = dict(
        id=kw.pop("id", 1), country="zz", ref="minister-of-health@", origin=("reconcile",),
        archetype=draft.get("archetype"), draft=draft,
        attestations=[att("Q1", current=True), att("Q2")],
    )
    base.update(kw)
    return Candidate(**base)


def verdict(**kw: Any) -> MintVerdict:
    base: dict[str, Any] = dict(verdict="mint", real=True, current=True, missing=True,
                                shape="agree", confidence="high",
                                corrections={f: None for f in mint.CORRECTION_FIELDS})
    base.update(kw)
    return MintVerdict(**base)


def decide(c: Candidate, v: MintVerdict | None = None, reasons: list[str] | None = None,
           dup: str | None = None) -> tuple[str, str]:
    spec, _problems = mint.build_spec(c, ctx())
    return mint.disposition(c, spec, v if v is not None else verdict(), reasons or [], dup)


def check_rules(expect: Any) -> None:
    """One fixture per rule, in order, each decided by its own rule."""
    cases: list[tuple[str, Candidate, MintVerdict | None, list[str], str | None, tuple[str, str]]] = [
        ("1 census anchor nobody attests",
         cand(origin=("census",), draft={"decision": None}, attestations=[]), verdict(), [], None,
         ("skipped", "census/unattested")),
        ("2 categorize refused", cand(draft={"decision": "body"}), verdict(), [], None,
         ("skipped", "categorize/body")),
        ("3 an ambassadorship", cand(draft={"archetype": "ambassador"}), verdict(), [], None,
         ("skipped", "diplomatic/deferred")),
        ("3 an ambassadorship categorize says exists comes before it",
         cand(draft={"archetype": "ambassador", "decision": "exists", "exists_qid": "Q950"}),
         verdict(), [], None, ("skipped", "diplomatic/deferred")),
        ("4 categorize named the item", cand(draft={"decision": "exists", "exists_qid": "Q950"}),
         verdict(), [], None, ("found", "categorize:exists")),
        ("3 a bilateral label on another archetype",
         cand(draft={"labels": {"en": "Ambassador of Alvania to Brena"}}), verdict(), [], None,
         ("skipped", "diplomatic/deferred")),
        ("5 no archetype", cand(draft={"archetype": None}), verdict(), [], None,
         ("skipped", "archetype/none")),
        ("6 one person", cand(attestations=[att("Q1", True), att("Q1", True)]), verdict(), [], None,
         ("skipped", "holders/1")),
        ("6 nobody current", cand(attestations=[att("Q1"), att("Q2")]), verdict(), [], None,
         ("skipped", "not-current")),
        ("7 a live duplicate beats a mint verdict", cand(), verdict(), ["duplicate/Q960"], "Q960",
         ("found", "guard:duplicate")),
        ("8 the verifier names the item", cand(), verdict(verdict="exists", exists_qid="Q950"),
         [], None, ("found", "verify:exists")),
        ("9 the verifier refuses", cand(), verdict(verdict="not-distinct"), [], None,
         ("skipped", "verify:not-distinct")),
        ("9 a mint that says it is not missing", cand(), verdict(missing=False), [], None,
         ("skipped", "verify:mint/not-missing")),
        ("9 no verdict at all", cand(), None, [], None, ("skipped", "verify:none")),
        ("10 a shape disagreement", cand(),
         verdict(shape="correct", corrections={**{f: None for f in mint.CORRECTION_FIELDS},
                                               "parent_qid": "Q83307"}),
         [], None, ("skipped", "disagree/shape:parent_qid")),
        ("11 a guard reason", cand(), verdict(), ["body-word/Q910", "label/es"], None,
         ("skipped", "guard:body-word/Q910")),
        ("12 all three agree", cand(), verdict(), [], None, ("guarded", "mint:agreed")),
        ("12 agreed at medium confidence", cand(), verdict(confidence="medium"), [], None,
         ("skipped", "verify:confidence/medium")),
    ]
    statuses = set()
    # An `exists` naming no office of this state falls through to the rules below.
    fell = cand(draft={"decision": "exists", "exists_qid": "Q953", "archetype": None})
    spec, _p = mint.build_spec(fell, ctx())
    got = mint.disposition(fell, spec, verdict(), [], None, exists_problem="exists-unscoped/Q953")
    expect(got == ("skipped", "archetype/none"),
           f"rule 4 an exists that is not this state's office falls through: {got}")
    got = mint.disposition(cand(), spec, verdict(verdict="exists", exists_qid="Q953"), [], None,
                           verify_exists_problem="exists-unscoped/Q953")
    expect(got == ("skipped", "verify:exists"),
           f"rule 8 a verifier's exists that is not this state's office is a skip: {got}")
    for name, c, v, reasons, dup, want in cases:
        spec, _p = mint.build_spec(c, ctx())
        # Rules 1-6 are handed a `mint` verdict: they must win over it.
        got = mint.disposition(c, spec, v, reasons, dup)
        statuses.add(got[0])
        expect(got == want, f"rule {name}: {got}")
        number = int(name.split()[0])
        if number <= 6:
            early = mint._first(mint.Case(c, spec, None, [], None), mint.MODEL_FREE)
            expect(early == want, f"rule {name} is decided without the model")
    expect(statuses <= set(mint.DISPOSITION_STATUSES),
           f"no status but skipped/found/guarded: {sorted(statuses)}")
    expect(mint.DISPOSITION_STATUSES == ("skipped", "found", "guarded"),
           "a disagreement has nowhere to queue: three statuses and no review")
    expect(mint.found_qid("guard:duplicate", cand(), verdict(), "Q960") == "Q960"
           and mint.found_qid("verify:exists", cand(), verdict(exists_qid="Q950"), None) == "Q950"
           and mint.found_qid("categorize:exists", cand(draft={"exists_qid": "Q951"}), None, None)
           == "Q951", "a found row names the item its rule found")
    unscoped = offices.Found("Q970", label_match=True, country_match=False)
    scoped = offices.Found("Q971", label_match=True, country_match=True)
    expect(mint.scoped_duplicate([unscoped]) is None and mint.scoped_duplicate([unscoped, scoped]) == "Q971",
           "only a duplicate naming the state is taken as found; a countryless one only blocks")


def check_exists_problem(expect: Any) -> None:
    """An item named as existing must be this state's office, not a class or a mission."""
    c = ctx()
    expect(c.exists_problem("Q950") is None, "the state's own office is accepted")
    expect(c.exists_problem("Q952") is None, "an office scoped to a subdivision is accepted")
    expect(c.exists_problem("Q953") == "exists-unscoped/Q953", "another state's office is refused")
    expect(c.exists_problem("Q954") == "exists-diplomatic/Q954", "a diplomatic post is refused")
    expect(c.exists_problem("Q83307") == "exists-class/Q83307", "an archetype's parent is a class")
    expect(c.exists_problem(SIB_PARENT) == f"exists-class/{SIB_PARENT}",
           "a kind the state's own offices subclass is a class")
    expect(c.exists_problem("Q294414") == "exists-class/Q294414", "a metaclass is a class")


def check_offices_fixes(expect: Any) -> None:
    """The guard, description and sibling rules the first run showed were wrong."""
    spec, _p = mint.build_spec(cand(draft={"body_qid": COUNCIL}), ctx())
    council = {"id": COUNCIL, "labels": {"en": {"language": "en", "value": "Council of Ministers"}},
               "claims": {"P17": _claim("P17", STATE)}}
    common = dict(holders=2, current_holders=1, single_seat_source_ok=False, duplicates=[],
                  run_labels=[], body=council, jurisdiction=None, closure={SIB_PARENT},
                  langs=["es"], state_names=["Alvania"])
    bare = offices.guard(spec, **common)
    known = offices.guard(spec, **common, known_bodies={COUNCIL})
    expect(f"body-word/{COUNCIL}" in bare and f"body-word/{COUNCIL}" not in known,
           "Minister of X in the Council of Ministers: a measured body skips the word check")
    guarded = mint.guard_reasons(cand(draft={"body_qid": COUNCIL}), spec,
                                 ctx(resolve=lambda qids: {q: council for q in qids}), [])
    expect(f"body-word/{COUNCIL}" not in guarded,
           "guard_reasons passes the bodies twelve siblings use as measured")
    party = cand(draft={"archetype": "politburo_member", "body_qid": BODY, "single_seat": False,
                        "labels": {"en": "member of the Politburo of the Alvania Party"}})
    pspec, _p = mint.build_spec(party, ctx())
    expect(pspec.descriptions.get("en") == "member of the political bureau of the Ministry of Health of Alvania"
           and "Politburo" in pspec.labels["en"],
           f"a politburo seat is described as one, and its label keeps the word: {pspec.descriptions}")
    gov = cand(draft={"archetype": "governor", "jurisdiction_qid": "Q901", "body_qid": None,
                      "labels": {"es": "gobernador de la provincia de Ostra"}},
               census_key="gov/Q901", ref="gov/Q901")
    gspec, _p = mint.build_spec(gov, ctx())
    expect(gspec.labels == {"es": "gobernador de la provincia de Ostra", "en": "Governor of Ostra"},
           f"a census anchor fills the languages the draft lacks, never the ones it has: {gspec.labels}")
    old = {"claims": {}}
    expect(offices.historical({"claims": {"P576": _claim("P576", "Q1")}}, None, 2026),
           "a dissolved office is history")
    expect(offices.historical({"claims": {"P31": _claim("P31", "Q114962596")}}, 2025, 2026),
           "a declared historical position is history")
    expect(offices.historical(old, 1906, 2026) and not offices.historical(old, 2000, 2026),
           "an office last held over thirty years ago is history; one held within it is not")
    expect(not offices.historical(old, None, 2026), "no dated holder is no evidence either way")


def check_build_spec(expect: Any) -> None:
    """The spec follows the siblings, and the aliases are the holders' own words."""
    titles = [att("Q1", True, "Ministra de Salud"), att("Q2", False, "ministra de  salud"),
              att("Q3", False, "Ministro de Salud Pública"), att("Q4", False, "ministro de Salud de Alvania"),
              att("Q5", False, "Ministro"), att("Q6", False, "Minister of Health", lang="en"),
              att("Q7", False, "Minister of Health of Alvania", lang="en")]
    titles += [att(f"Q{10 + i}", False, f"Ministro de Salud y Ramo {i}") for i in range(6)]
    spec, problems = mint.build_spec(cand(attestations=titles), ctx())
    es = spec.aliases.get("es", [])
    expect(es[0] == "Ministra de Salud", f"the most-held title leads, folded once: {es}")
    expect(len(es) == mint.ALIASES_PER_LANG, f"at most five aliases a language: {len(es)}")
    expect("ministro de Salud de Alvania" not in es and "Minister of Health of Alvania"
           not in spec.aliases.get("en", []), "an alias never repeats a label")
    expect("Ministro" not in es, "a bare seat word is never an alias")
    other = mint.attested_aliases(
        [mint.Attestation(person=f"Q{i}", title=t, lang="en", current=True) for i, t in enumerate(
            ["Co-Judge of the Constitutional Court", "Acting President of the Court",
             "Magistrate of the Constitutional Court"])],
        {"en": "Justice of the Constitutional Court"})
    expect(other.get("en") == ["Magistrate of the Constitutional Court"],
           "a title that names another seat (a co-judge, an acting holder) is never an alias")
    expect(spec.aliases.get("en") == ["Minister of Health"], "aliases are kept per language")
    quoted = mint.attested_aliases(
        [mint.Attestation(person="Q1", title="Secretary-General of the Unity Party", lang="fr", current=True),
         mint.Attestation(person="Q2", title="secrétaire général du Parti de l'Unité", lang="fr", current=True),
         mint.Attestation(person="Q3", title="Secretary General of the Unity Party", lang="en", current=True),
         mint.Attestation(person="Q4", title="Katibu Mkuu wa Unity Party", lang="sw", current=True)],
        {"en": "General Secretary of the Unity Party", "fr": "secrétaire général du Parti de l'Unité, Alvania"},
        ["Alvania"])
    expect("Secretary-General of the Unity Party" not in quoted.get("fr", []),
           f"an English title quoted in a French article is not a French alias: {quoted}")
    expect(quoted.get("fr") == ["secrétaire général du Parti de l'Unité"]
           and quoted.get("en") == ["Secretary General of the Unity Party"]
           and quoted.get("sw") == ["Katibu Mkuu wa Unity Party"],
           f"while a same-language variant, and a language with no label, keep theirs: {quoted}")
    expect(spec.parent == SIB_PARENT and spec.metaclass == "Q294414",
           f"the parent and metaclass are the siblings': {spec.parent} {spec.metaclass}")
    expect(spec.jurisdiction_qid == STATE, "a null jurisdiction on a scoped seat is the state")
    expect(spec.descriptions == {"en": "minister in the government of Alvania"},
           f"the description is described from resolved labels: {spec.descriptions}")
    expect(problems == [], f"a clean draft has no problems: {problems}")
    _s, replaced = mint.build_spec(cand(draft={"parent_qid": "Q999"}), ctx())
    expect(_s.parent == SIB_PARENT and replaced == ["parent-replaced/Q999"],
           "a drafted parent no sibling uses is replaced, and the replacement recorded")
    kept, _p = mint.build_spec(cand(draft={"parent_qid": SIB_PARENT}), ctx())
    expect(kept.parent == SIB_PARENT, "a drafted sibling class is kept")
    soe, _p = mint.build_spec(cand(draft={"archetype": "soe_head", "parent_qid": "Q140686",
                                          "labels": {"en": "Chair of Alvania Oil"}}), ctx())
    expect(soe.parent == "Q140686" and soe.jurisdiction_qid is None,
           "an enterprise head keeps its drafted title class and governs no polity")
    unlabelled, problems = mint.build_spec(
        cand(draft={"archetype": "legislator", "body_qid": "Q999"}), ctx())
    expect(unlabelled.descriptions == {} and "description" in problems,
           "an unresolved body label refuses a description rather than writing a QID")
    none, problems = mint.build_spec(cand(draft={"archetype": "ambassador"}), ctx())
    expect(none is None and problems == ["archetype/ambassador"], "no archetype, no spec")
    data = offices.entity_data(spec)
    expect([c["mainsnak"]["property"] for c in data["claims"]] == ["P31", "P279", "P17", "P1001", "P361"],
           "the payload carries the five structural claims")
    expect(mint.spec_from(mint.asdict(spec)) == spec, "a stored spec reads back equal")


def check_settle(expect: Any) -> None:
    """An answer may cite only what the request showed."""
    answer = mint.VerifyAnswer(
        verdict="exists", exists_qid="Q999", real=True, current=True, missing=False,
        shape="correct", corrections=mint.Corrections(
            parent_qid="Q83307", body_qid="Q12345", jurisdiction_qid=None, metaclass=None,
            label_en=None, label_local="ministra de Salud"),
        confidence="high", evidence="x", reason="y")
    ev = mint.Evidence("", "", "", "", "", shown={"Q83307", "Q950"}, office_qids={"Q950"})
    v = mint.settle_verify(answer, ev, call=7)
    expect(v.exists_qid is None and "off-list:exists_qid:Q999" in v.problems,
           "an exists QID that was not shown is removed")
    expect(v.corrections["body_qid"] is None and v.corrections["parent_qid"] == "Q83307"
           and "off-list:body_qid:Q12345" in v.problems, "an off-list correction QID is nulled")
    expect(mint.disposition(cand(), None, v, [], None) == ("skipped", "verify:exists"),
           "an exists that named nothing shown is a skip, never a found")
    ok = mint.settle_verify(answer.model_copy(update={"exists_qid": "Q950"}), ev)
    expect(ok.exists_qid == "Q950", "an exists QID that was shown is kept")


def check_evidence(expect: Any) -> None:
    """The request shows each person once, the hits worth reading, and the draft labelled."""
    hits = [offices.Found("Q960", label_match=True, country_match=True, country_qids=(STATE,),
                          types=frozenset({"Q294414"})),
            offices.Found("Q5000", label_match=True, types=frozenset({"Q5"}))]
    c = cand(attestations=[att("Q1", True, "Ministra de Salud"), att("Q1", True, "Ministra"),
                           att("Q2", False, "Ministro de Salud")])
    ev = mint.evidence(c, ctx=ctx(), found=hits)
    expect(ev.attestations.count("## Q1") == 1 and ev.attestations.count("## Q2") == 1,
           "one block per distinct person")
    expect("Q960" in ev.duplicates and "Q5000" not in ev.duplicates and "exact name" in ev.duplicates,
           "humans are dropped from the hits, and a name match is marked")
    expect("Q920 minister of Alvania" in ev.draft and f"{BODY} Ministry of Health" in ev.draft,
           "every draft QID is shown with its label")
    expect({"Q960", "Q950"} <= ev.office_qids and BODY in ev.shown,
           "a duplicate and an index row may be named as existing; the body may be cited")


def check_prompt(expect: Any) -> None:
    """The prompt names every value the answer may take."""
    text, _hash = mint.verify_prompt()
    values = (*mint.VERIFY_VERDICTS, *mint.SHAPES, *mint.CONFIDENCES, *mint.CORRECTION_FIELDS,
              "exists_qid", "real", "current", "missing")
    missing = [v for v in values if f"`{v}`" not in text]
    expect(not missing, f"every verdict, shape, confidence and field is in the prompt: {missing}")


TABLES = ("mint_call", "office_candidate", "office_attestation", "office_unassigned")


def check_ledger(expect: Any) -> None:
    """A rerun asks nothing; guarded rows carry data, found rows a QID; audits stand."""
    try:
        conn = db.conn()
    except psycopg.OperationalError as exc:
        print(f"  skip no database ({exc.__class__.__name__})")
        return
    for table in TABLES:
        conn.execute(f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING DEFAULTS"
                     " INCLUDING INDEXES INCLUDING CONSTRAINTS)")
    for table in ("mint_call", "office_candidate"):
        conn.execute(f"CREATE TEMP SEQUENCE {table}_seq")
        conn.execute(f"ALTER TABLE pg_temp.{table} ALTER COLUMN id SET DEFAULT"
                     f" nextval('pg_temp.{table}_seq')")
    calls: list[str] = []

    def ask(message: str, model: str) -> tuple[mint.VerifyAnswer, dict[str, int]]:
        calls.append(message)
        return mint.VerifyAnswer(
            verdict="mint", exists_qid=None, real=True, current=True, missing=True, shape="agree",
            corrections=mint.Corrections(parent_qid=None, body_qid=None, jurisdiction_qid=None,
                                         metaclass=None, label_en=None, label_local=None),
            confidence="high", evidence="“x”", reason="y"), {"input_tokens": 10, "output_tokens": 5}

    def insert(ref: str, draft: dict[str, Any], people: list[tuple[str, bool]], **cols: Any) -> int:
        cid = conn.execute(
            "INSERT INTO office_candidate (country, ref, origin, archetype, draft, status, decided_by)"
            " VALUES ('zz', %s, '{reconcile}', %s, %s, %s, %s) RETURNING id",
            (ref, draft.get("archetype"), mint.Jsonb(draft), cols.get("status", "categorized"),
             cols.get("decided_by"))).fetchone()[0]
        for i, (person, current) in enumerate(people):
            conn.execute(mint.ATTESTATION_SQL, (cid, None, 10_000_000 + cid, i, person, current))
        return cid

    saved = mint.ask_verify
    mint.ask_verify = ask
    quiet = lambda _line: None
    try:
        base = cand().draft
        good = insert("health", base, [("Q1", True), ("Q2", False)])
        known = insert("finance", {**base, "decision": "exists", "exists_qid": "Q950"}, [("Q3", True)])
        audited = insert("audited", base, [("Q4", True), ("Q5", False)],
                         status="skipped", decided_by="audit:someone")
        first = mint.verify("zz", ctx=ctx(), log=quiet, threads=1)
        rows = {r[0]: r[1:] for r in conn.execute(
            "SELECT id, status, rule, qid, data IS NOT NULL, verify_call FROM office_candidate")}
        expect(rows[good][:2] == ("guarded", "mint:agreed") and rows[good][3] and rows[good][4],
               f"an agreed candidate is guarded with its payload and its call: {rows[good]}")
        data = conn.execute("SELECT data, spec FROM office_candidate WHERE id = %s", (good,)).fetchone()
        expect(data[0] == offices.entity_data(mint.spec_from(data[1])),
               "a guarded row's data is entity_data of its stored spec")
        expect(rows[known][:3] == ("found", "categorize:exists", "Q950"),
               f"a found row carries its QID: {rows[known]}")
        expect(rows[audited][:2] == ("skipped", None),
               "an audited skip is never re-decided by verify")
        expect(len(calls) == 1 and first["asked"] == 1, "only the candidate past the rules is asked")
        expect(set(s for s, _r in first["funnel"]) <= set(mint.DISPOSITION_STATUSES),
               "the funnel holds no status but the three")
        conn.execute("UPDATE office_candidate SET status = 'categorized' WHERE id = %s", (good,))
        second = mint.verify("zz", ctx=ctx(), log=quiet, threads=1)
        expect(len(calls) == 1 and second["asked"] == 0 and second["recorded"] == 1,
               "a rerun over unchanged evidence asks nothing")
        expect(mint.reguard({"id": good, "country": "zz", "ref": "health", "origin": ["reconcile"],
                             "archetype": "minister", "draft": base, "spec": data[1],
                             "status": "guarded", "problems": []}, ctx()) == [],
               "reguard over the stored row finds nothing new")
        expect(mint.reguard(good, ctx(lookup=lambda _t, _l, _s: [offices.Found(
            "Q961", label_match=True, country_match=True, country_qids=(STATE,))]))
            == ["duplicate/Q961"], "reguard reads the searches again and names a new duplicate")
        # A categorize rerun leaves an audited row alone, on upsert and on supersede.
        group = mint.Group("audited|", [mint.Row(1, 1, 0, "Q4", "x", current=True)])
        cluster = mint.Cluster("audited", [group])
        mint.write_candidates("zz", {"audited": cluster}, [], complete=True)
        mint.write_candidates("zz", {}, [], complete=True)
        expect(conn.execute("SELECT status, decided_by FROM office_candidate WHERE id = %s",
                            (audited,)).fetchone() == ("skipped", "audit:someone"),
               "a categorize rerun neither resets nor supersedes an audited skip")
    finally:
        mint.ask_verify = saved
        for table in TABLES:
            conn.execute(f"DROP TABLE IF EXISTS pg_temp.{table}")
        for table in ("mint_call", "office_candidate"):
            conn.execute(f"DROP SEQUENCE IF EXISTS pg_temp.{table}_seq")


def main() -> int:
    """Run every pin and report."""
    failures: list[str] = []

    def expect(condition: bool, message: str) -> None:
        print(("  ok   " if condition else "  FAIL ") + message)
        if not condition:
            failures.append(message)

    for name, check in (
        ("rules", check_rules),
        ("exists_problem", check_exists_problem),
        ("offices_fixes", check_offices_fixes),
        ("build_spec", check_build_spec),
        ("settle", check_settle),
        ("evidence", check_evidence),
        ("prompt", check_prompt),
        ("ledger", check_ledger),
    ):
        print(f"{name}:")
        check(expect)
    print(f"{len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
