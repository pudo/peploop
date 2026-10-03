"""Pin the categorize pass: what it is shown, and what of its answer survives.

The model clusters and drafts; everything around it is mechanical and pinned
here without a key or a request. The ordering that decides which groups share a
context, the gate that refuses an off-list QID or a group assigned twice, the
census expansion, the prompt's coverage of every closed value, and the ledger
that makes a rerun free. The ledger case runs against temporary tables
shadowing the real ones and a stubbed model, so nothing stored is touched.

Run it as `python -m peploop.check_mint_categorize` from the repository root.
"""

import sys
import tempfile
from pathlib import Path
from typing import Any

import psycopg

from peploop import db, mint
from peploop.mint import (
    Anchor, CategorizeAnswer, Group, Label, OfficeAnswer, Offered, PositionRow, Row,
    UnassignedAnswer,
)

STATE = "Q900"


def row(person: str, title: str, jurisdiction: str | None = None, **kw: Any) -> Row:
    base = dict(resolution_id=int(person[1:]), extraction_id=int(person[1:]), mention_idx=0,
                person=person, title=title, jurisdiction=jurisdiction)
    base.update(kw)
    return Row(**base)


def group(title: str, *people: str, jurisdiction: str | None = None, current: bool = False) -> Group:
    rows = [row(p, title, jurisdiction, current=current) for p in people]
    return Group(mint.group_key(rows[0]), rows)


def office(groups: list[str], **kw: Any) -> OfficeAnswer:
    base: dict[str, Any] = dict(
        groups=groups, decision="office", exists_qid=None, census_key=None,
        institution_class="subnational.municipal", archetype="mayor", single_seat=True,
        labels=[Label(lang="en", text="Mayor of Velmora")], description_en=None,
        parent_qid=None, body_qid=None, jurisdiction_qid=None, jurisdiction_name=None,
        replaces_qid=None, evidence="", reason="",
    )
    base.update(kw)
    return OfficeAnswer(**base)


def offered(**kw: Any) -> Offered:
    base: dict[str, Any] = dict(
        state_qid=STATE, state_label="Alvania", subdivisions={"Q901": "Ostra"},
        positions=[PositionRow("Q950", "Mayor of Bray", ["mayor"]),
                   PositionRow("Q951", "Senate of Alvania", [], not_office=True)],
        census_keys={"court"},
    )
    base.update(kw)
    return Offered(**base)


def check_order(expect: Any) -> None:
    state = mint.state_stems(["Alvania", "República de Alvania"])
    forms = [group("Alcaldesa de Velmora", "Q1"), group("Alcalde de Velmora", "Q2"),
             group("Mayor of Velmora", "Q3")]
    keys = {mint.chunk_order(g, state)[0] for g in forms}
    expect(keys == {("velmor",)}, f"gendered and English forms of one mayoralty share a key: {keys}")
    senate = group("Senador de la República de Alvania", "Q4", jurisdiction="Alvania")
    expect(mint.chunk_order(senate, state)[0] == (),
           "the seat word, the role words and the state's own name all drop out")
    others = [group("Alcalde de Abrel", "Q5"), group("Gobernador de Zuria", "Q6"),
              group("Ministro de Hacienda", "Q7")]
    pool = [others[2], forms[0], others[1], forms[2], senate, others[0], forms[1]]
    ordered = [g for c in mint.chunks(pool, state, size=3) for g in c]
    at = [ordered.index(g) for g in forms]
    expect(max(at) - min(at) == 2, "the three forms are adjacent in the request order")
    cut = mint.chunks(pool, state, size=3)
    expect([len(c) for c in cut] == [3, 3, 1], "groups are cut into chunks of the given size")
    expect(mint.chunks(list(reversed(pool)), state, size=3) == cut,
           "the order is total, so a rerun renders the same chunks")


def check_settle(expect: Any) -> None:
    chunk = [group("Alcalde de Velmora", "Q1"), group("Mayor of Velmora", "Q2"),
             group("Partido Azul", "Q3"), group("Juez", "Q4")]
    o = offered()
    answer = CategorizeAnswer(
        offices=[
            office(["g1", "g2"], jurisdiction_qid="Q999", parent_qid="Q950"),
            office(["g3", "g2"], decision="party-membership", archetype=None),
            office(["g9"]),
        ],
        unassigned=[],
    )
    settled, left, problems = mint.settle_categorize(answer, chunk, o)
    first = settled[0]
    expect(first.jurisdiction_qid is None and "off-list:jurisdiction_qid:Q999" in first.problems,
           "an off-list QID is nulled and recorded on the office")
    expect(first.parent_qid == "Q950", "an offered QID is kept")
    expect([g.key for g in settled[1].groups] == [chunk[2].key]
           and f"group-twice:{chunk[1].key}" in problems,
           "a group assigned twice keeps its first office, and the second is a problem")
    expect(len(settled) == 2 and "unknown-group:g9" in problems and "office-without-groups" in problems,
           "an unknown group id is refused, and an office left with no groups is dropped")
    expect([(g.key, r) for g, r in left] == [(chunk[3].key, "categorize/missing")]
           and f"group-missing:{chunk[3].key}" in problems,
           "a group the answer left out is unassigned under a recorded problem")

    answer = CategorizeAnswer(offices=[
        office(["g1"], decision="exists", exists_qid="Q951"),
        office(["g2"], decision="exists", exists_qid="Q950"),
        office(["g3"], institution_class="judiciary.top", archetype="emperor"),
        office(["g4"], archetype="ambassador", institution_class="diplomatic.outbound",
               census_key="nonesuch"),
    ], unassigned=[])
    settled, left, problems = mint.settle_categorize(answer, chunk, o)
    expect(settled[0].decision == "unclear" and settled[0].exists_qid is None,
           "`exists` naming a body rather than an office becomes `unclear`")
    expect(settled[1].decision == "exists" and settled[1].exists_qid == "Q950",
           "`exists` naming an offered office is kept")
    expect(settled[2].institution_class is None and settled[2].archetype is None
           and {"unknown-class:judiciary.top", "unknown-archetype:emperor"} <= set(settled[2].problems),
           "an unknown class and archetype are nulled and recorded")
    expect(settled[3].archetype == "ambassador" and settled[3].census_key is None
           and "unknown-census:nonesuch" in problems,
           "`ambassador` is a valid archetype, and an unknown census key is nulled")
    expect(left == [], "every group assigned leaves nothing unassigned")
    unassigned = CategorizeAnswer(offices=[], unassigned=[
        UnassignedAnswer(group=f"g{i}", reason="noise") for i in range(1, 5)])
    _s, left, problems = mint.settle_categorize(unassigned, chunk, o)
    expect(len(left) == 4 and problems == [], "an answer may leave every group unassigned")


def check_floor(expect: Any) -> None:
    a = group("Alcalde de Velmora", "Q1", current=True)
    b = group("Mayor of Velmora", "Q2")
    c = group("Alcaldesa de Velmora", "Q1")
    drafted = mint.Drafted(groups=[a, b, c], decision="office", labels={"en": "Mayor of Velmora"})
    cluster = mint.merge([(drafted, 1)], [])[mint.candidate_ref(drafted)]
    expect((cluster.holders, cluster.current_holders) == (2, 1),
           "a merged candidate counts distinct people across its groups")
    expect(mint.floor(a) == "holders/1" and mint.floor(cluster) is None,
           "groups of one person each clear the floor once clustered")
    anchor = Anchor("court", "judiciary.apex", "court_president", {"en": "President of the Court"})
    clusters = mint.merge([], [anchor])
    expect(mint.floor(clusters["court"]) == "census/unattested",
           "an anchor no group names still gets a candidate, refused as unattested")
    expect(mint.candidate_ref(drafted) == "mayor-of-velmora@",
           "a ref is the folded English label and the jurisdiction")
    vice = mint.Drafted(groups=[a], decision="office", jurisdiction_qid="Q9",
                        labels={"en": "Vice Minister of Health", "es": "viceministro de Salud"})
    deputy = mint.Drafted(groups=[b], decision="office",
                          labels={"en": "Deputy Minister of Health", "es": "Viceministro de Salud"})
    merged = mint.merge([(vice, 1), (deputy, 2)], [], state_qid="Q9")
    expect(len(merged) == 1 and next(iter(merged.values())).holders == 2,
           "two chunks' drafts sharing a label in any language are one candidate")
    gov = Anchor("gov/Q5", "subnational.executive", "governor", {"es": "Gobernador de Brena"},
                 jurisdiction="Q5")
    loose = mint.Drafted(groups=[a], decision="office", jurisdiction_qid="Q5",
                         labels={"es": "gobernador de Brena"})
    expect(set(mint.merge([(loose, 1)], [gov], state_qid="Q9")) == {"gov/Q5"},
           "and a draft that forgot its census key still joins the anchor it names")


CENSUS = """
- key: governor
  class: subnational.executive
  archetype: governor
  labels: {en: "Governor of {name}"}
  per: subdivisions
  exclude: [Q12]
"""


def check_census_exclude(expect: Any) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "zz.yml"
        path.write_text(CENSUS)
        anchors = mint.census("fr", path=path, subdivisions=lambda _s: ["Q11", "Q12", "Q13"],
                              labels_of=lambda qids: {q: {"en": q} for q in qids})
        expect({a.key for a in anchors} == {"governor/Q11", "governor/Q13"},
               "an excluded subdivision gets no anchor")


def check_prompt(expect: Any) -> None:
    text, _hash = mint.categorize_prompt()
    for value in mint.DECISIONS:
        expect(f"`{value}`" in text, f"the prompt explains decision {value}")
    for name in mint.CATEGORIZE_ARCHETYPES:
        expect(f"`{name}`" in text, f"the prompt explains archetype {name}")
    expect("deputy speaker of a chamber is not `speaker`, it is null" in text,
           "a chamber's deputy speaker is not a speaker: no archetype, like a vice-minister")
    expect('marked "(dissolved)"' in text, "the prompt says what a dissolved subdivision is for")
    missing = [c for c in mint.INSTITUTION_CLASSES if f"`{c}`" not in text]
    expect(not missing, f"the prompt lists every institution class {missing or ''}")
    rendered = mint.render_categorize([group("Alcalde de Velmora", "Q1")], [], "mayor 3", offered())
    expect("g1 | Alcalde de Velmora" in rendered and "Q950 | Mayor of Bray | mayor" in rendered
           and "(not an office)" in rendered, "a request numbers its groups and lists the offices")


TABLES = ("mint_call", "office_candidate", "office_attestation", "office_unassigned")


def check_worth_asking(expect: Any) -> None:
    """Groups that could never reach a current holder cost no tokens."""
    state = mint.state_stems(["Alvania"])
    now = group("Alcalde de Velmora", "Q1", current=True)
    piece = group("Alcaldesa de Velmora", "Q2")
    past = group("Gobernador de Brena", "Q3")
    generic = group("magistrado", "Q4")
    keep, drop = mint.worth_asking([now, piece, past, generic], state)
    expect([g.key for g in keep] == [now.key, piece.key],
           "a current group and a piece that shares its place are asked")
    expect([g.key for g in drop] == [past.key, generic.key],
           "a historical office and a bare generic title are not")


def check_ledger(expect: Any) -> None:
    """A rerun over the same groups asks nothing; a changed answer supersedes."""
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
    gs = [group("Alcalde de Velmora", "Q1", current=True), group("Mayor of Velmora", "Q2"),
          group("Partido Azul", "Q3", current=True)]
    calls: list[str] = []
    answers = {"n": 0}

    def ask(message: str, model: str) -> tuple[CategorizeAnswer, dict[str, int]]:
        calls.append(message)
        ids = {line.split(" | ")[1]: line.split(" | ")[0]
               for line in message.splitlines() if line.startswith("g")}
        label = "Mayor of Velmora" if answers["n"] == 0 else "Mayor of Velmora Town"
        return CategorizeAnswer(
            offices=[office([ids["Alcalde de Velmora"], ids["Mayor of Velmora"]],
                            labels=[Label(lang="en", text=label)])],
            unassigned=[UnassignedAnswer(group=ids["Partido Azul"], reason="party membership")],
        ), {"input_tokens": 10, "output_tokens": 5}

    saved = {name: getattr(mint, name) for name in
             ("unplaced", "groups", "census", "offered_for", "_state_names", "ask_categorize")}
    mint.unplaced = lambda _cc: []
    mint.groups = lambda _rows: list(gs)
    mint.census = lambda _cc: []
    mint.offered_for = lambda _cc, _g, _a: (offered(), None)
    mint._state_names = lambda _o: ["Alvania"]
    mint.ask_categorize = ask
    quiet = lambda _line: None
    try:
        first = mint.categorize("zz", log=quiet)
        expect(len(calls) == 1 and first["asked"] == 1 and first["usage"]["input_tokens"] == 10,
               "the first run asks once per chunk and sums the usage")
        rows = conn.execute("SELECT ref, status, holders FROM office_candidate").fetchall()
        expect(rows == [("mayor-of-velmora@", "categorized", 2)],
               "the candidate is upserted by ref, categorized, with its distinct holders")
        expect(conn.execute("SELECT count(*) FROM office_attestation").fetchone()[0] == 2
               and conn.execute("SELECT group_key, reason FROM office_unassigned").fetchall()
               == [(gs[2].key, "party membership")],
               "attestations link the member rows, and the unassigned group keeps its reason")
        second = mint.categorize("zz", log=quiet)
        expect(len(calls) == 1 and second["asked"] == 0 and second["recorded"] == 1,
               "a rerun over the same groups makes zero calls")
        expect(conn.execute("SELECT count(*) FROM office_candidate").fetchone()[0] == 1,
               "a rerun updates the candidate it made rather than adding one")
        dry = mint.categorize("zz", dry_run=True, log=quiet)
        expect(len(calls) == 1 and dry["recorded"] == 1, "a dry run calls nothing")
        # A prompt edit is a new key: simulate it by a new model name.
        answers["n"] = 1
        conn.execute("UPDATE office_candidate SET status = 'created' WHERE ref = 'mayor-of-velmora@'")
        mint.categorize("zz", log=quiet, model="other-model")
        statuses = dict(conn.execute("SELECT ref, status FROM office_candidate").fetchall())
        expect(statuses == {"mayor-of-velmora@": "created", "mayor-of-velmora-town@": "categorized"},
               "a created candidate the answers no longer produce is left alone")
        conn.execute("UPDATE office_candidate SET status = 'categorized' WHERE ref = 'mayor-of-velmora@'")
        answers["n"] = 0
        mint.categorize("zz", log=quiet, model="third-model")
        statuses = dict(conn.execute("SELECT ref, status FROM office_candidate").fetchall())
        expect(statuses == {"mayor-of-velmora@": "categorized", "mayor-of-velmora-town@": "superseded"},
               "a candidate the newest answers no longer produce is superseded")
        expect(conn.execute("SELECT count(DISTINCT candidate_id) FROM office_attestation")
               .fetchone()[0] == 1, "a superseded candidate's attestations are removed")
    finally:
        for name, value in saved.items():
            setattr(mint, name, value)
        for table in TABLES:
            conn.execute(f"DROP TABLE IF EXISTS pg_temp.{table}")
        for table in ("mint_call", "office_candidate"):
            conn.execute(f"DROP SEQUENCE IF EXISTS pg_temp.{table}_seq")


def check_state_positions(expect: Any) -> None:
    """An office scoped to the state only by `P1001` is in the index categorize sees."""
    try:
        conn = db.conn()
    except psycopg.OperationalError as exc:
        print(f"  skip no database ({exc.__class__.__name__})")
        return
    conn.execute("CREATE TEMP TABLE position (LIKE public.position INCLUDING DEFAULTS)")
    try:
        for qid, country, jurisdiction in (("Q1", "Q90", None), ("Q2", None, "Q90"),
                                           ("Q3", "Q91", "Q91")):
            conn.execute("INSERT INTO pg_temp.position (qid, label, country_qid, jurisdiction_qid)"
                         " VALUES (%s, %s, %s, %s)", (qid, qid, country, jurisdiction))
        got = [row.qid for row in mint.state_positions("Q90")]
        expect(got == ["Q1", "Q2"], f"by P17 or by P1001 alone, and no other state's: {got}")
    finally:
        conn.execute("DROP TABLE IF EXISTS pg_temp.position")


def main() -> int:
    """Run every pin and report."""
    failures: list[str] = []

    def expect(condition: bool, message: str) -> None:
        print(("  ok   " if condition else "  FAIL ") + message)
        if not condition:
            failures.append(message)

    for name, check in (
        ("order", check_order),
        ("settle", check_settle),
        ("floor", check_floor),
        ("census_exclude", check_census_exclude),
        ("prompt", check_prompt),
        ("worth_asking", check_worth_asking),
        ("ledger", check_ledger),
        ("state_positions", check_state_positions),
    ):
        print(f"{name}:")
        check(expect)
    print(f"{len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
