"""Pin the minting queue: which misses count as evidence, and how they pool.

Every figure the floor reads is computed here, and each one fails in the
generous direction without raising: an acting tenure counted as current, a
dead holder still "in office", a term that opened twenty years ago read as
running, a census entry expanded over a stale subdivision. All of it is pure
except `unplaced`, which runs against temporary tables shadowing the real
ones, so nothing stored is read or written.

Run it as `python -m peploop.check_mint_queue` from the repository root.
"""

import re
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from peploop import db, mint
from peploop.mint import Group, Row

TODAY = date(2026, 10, 1)
RECIPE = Path(__file__).resolve().parent.parent / "recipes" / "institutions.md"


def row(person: str = "Q1", **fields: Any) -> Row:
    """An unplaced mention with just the fields a case is about."""
    base = dict(resolution_id=1, extraction_id=1, mention_idx=0, person=person,
                title="Minister of Works")
    base.update(fields)
    out = Row(**base)
    out.current = mint.is_current(out, TODAY)
    return out


def check_current(expect: Any) -> None:
    cases = (
        ("an open tenure inside the window", dict(start="2020"), True),
        ("an open tenure at the window's edge", dict(start="2014-10-02"), True),
        ("an open tenure older than the window", dict(start="2010"), False),
        ("an undated tenure", dict(), False),
        ("an end still to come", dict(start="1990", end="2028"), True),
        ("an end already past", dict(start="2022", end="2024-05"), False),
        ("an end this year, at year precision", dict(start="2022", end="2026"), False),
        ("an end later this month", dict(start="2022", end="2026-10-20"), True),
        ("an unparseable end", dict(start="2024", end="soon"), False),
        ("an acting tenure", dict(start="2025", acting=True), False),
        ("a dead holder", dict(start="2025", death="+2025-06-01T00:00:00Z"), False),
    )
    for name, fields, want in cases:
        expect(row(**fields).current is want, f"{name} is {'' if want else 'not '}current")


def check_group_key(expect: Any) -> None:
    expect(mint.group_key(row(title="Ministro de  Educación ", jurisdiction=None))
           == "ministro de educacion|", "titles fold diacritics, case and spacing")
    expect(mint.group_key(row(title="MINISTRO DE EDUCACION", jurisdiction="Ålvik"))
           == "ministro de educacion|alvik", "jurisdictions fold the same way")
    rows = [row("Q1", title="Mayor of Alvik", start="2024"),
            row("Q2", title="mayor of alvik", start="2001"),
            row("Q2", title="Mayor of Alvik", start="2001", mention_idx=1),
            row("Q3", title="Governor of Bray")]
    pooled = mint.groups(rows)
    expect([g.key for g in pooled] == ["mayor of alvik|", "governor of bray|"],
           "groups pool by key, the best-attested first")
    first = pooled[0]
    expect((first.mentions, first.people, first.current) == (3, 2, 1),
           "a group counts mentions, distinct people and distinct current people")
    expect(first.title == "Mayor of Alvik", "a group is titled by its commonest spelling")


def check_floor(expect: Any) -> None:
    def group(rows: list[Row], **kw: Any) -> Group:
        return Group("k", rows, **kw)

    two = [row("Q1", start="2024"), row("Q2", start="1990", end="1994")]
    expect(mint.floor(group(two)) is None, "two people, one current, pass")
    expect(mint.floor(group([row("Q1", start="2024"), row("Q1", start="2024", mention_idx=1)]))
           == "holders/1", "two rows of one person are one holder")
    expect(mint.floor(group([row("Q1", start="2024")], single_seat=True,
                            source_url="https://example.org/officials")) is None,
           "a single seat with a source passes on one current holder")
    expect(mint.floor(group([row("Q1", start="2024")], single_seat=True)) == "holders/1",
           "a single seat with no source still needs two people")
    expect(mint.floor(group([row("Q1", start="2024")], single_seat=True,
                            origin=("reconcile", "census"))) is None,
           "a census-anchored single seat passes on one current holder")
    expect(mint.floor(group([row("Q1", start="2024")], origin=("reconcile", "census")))
           == "holders/1", "but a census-anchored seat of many still needs two people")
    expect(mint.floor(group([row("Q1", start="1990", end="1994")], single_seat=True,
                            origin=("reconcile", "census"))) == "not-current",
           "and a census-anchored single seat still needs its holder to be current")
    expect(mint.floor(group([row("Q1", start="1990", end="1994"),
                             row("Q2", start="1995", end="1999")])) == "not-current",
           "two past holders and nobody now is not current")
    expect(mint.floor(group([], origin=("census",))) == "census/unattested",
           "a census office nobody's article names is refused under its own rule")
    expect(mint.floor(group([])) == "holders/0", "an empty reconcile group has no holders")


CENSUS = """
- key: court
  class: judiciary.apex
  archetype: court_president
  labels: {en: President of the High Court, xx: Presidente de la Corte}
  source: https://example.org/court
- key: governor
  class: subnational.executive
  archetype: governor
  labels: {en: "Governor of {name}", xx: "Gobernador de {name}"}
  per: subdivisions
"""


def check_census(expect: Any) -> None:
    labels = {"Q11": {"en": "Bray", "xx": "Brai"}, "Q12": {"mul": "Ostra"}, "Q13": {}}
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "zz.yml"
        path.write_text(CENSUS)
        anchors = mint.census("fr", path=path, subdivisions=lambda _s: ["Q11", "Q12", "Q13"],
                              labels_of=lambda qids: {q: labels[q] for q in qids})
        by_key = {a.key: a for a in anchors}
        expect(set(by_key) == {"court", "governor/Q11", "governor/Q12"},
               "a subdivision entry expands once per P150, and an unnamed one is dropped")
        expect(by_key["governor/Q11"].labels == {"en": "Governor of Bray", "xx": "Gobernador de Brai"},
               "each label is filled from the subdivision's label in that language")
        expect(by_key["governor/Q12"].labels == {"en": "Governor of Ostra", "xx": "Gobernador de Ostra"},
               "a missing language falls back to en, then mul")
        expect(by_key["governor/Q11"].jurisdiction == "Q11" and by_key["court"].jurisdiction is None,
               "an expanded anchor is scoped to its subdivision")
        for bad, message in (("judiciary.apex", "unknown archetype"), ("judiciary.top", "unknown class")):
            path.write_text(f"- {{key: x, class: {bad}, archetype: "
                            f"{'nonesuch' if 'archetype' in message else 'governor'}, labels: {{en: X}}}}")
            try:
                mint.census("fr", path=path)
                expect(False, f"an {message} is refused")
            except ValueError:
                expect(True, f"an {message} is refused")
        expect(mint.census("fr", path=Path(tmp) / "absent.yml") == [], "no file is an empty census")


def check_classes(expect: Any) -> None:
    expect(len(set(mint.INSTITUTION_CLASSES)) == len(mint.INSTITUTION_CLASSES),
           "institution classes are unique")
    if not RECIPE.exists():
        print("  skip no recipes/institutions.md")
        return
    headings = re.findall(r"^### `([a-z_]+\.[a-z_]+)`", RECIPE.read_text(), re.M)
    expect(tuple(headings) == mint.INSTITUTION_CLASSES,
           "INSTITUTION_CLASSES matches the recipe's headings, in order")


def check_unplaced(expect: Any) -> None:
    """Pin `unplaced` against temporary tables shadowing the real ones."""
    try:
        conn = db.conn()
    except psycopg.OperationalError as exc:
        print(f"  skip no database ({exc.__class__.__name__})")
        return
    tables = ("person", "item", "extraction", "resolution")
    for table in tables:
        conn.execute(f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING DEFAULTS)")
    try:
        for qid, status in (("Q1", "proposed"), ("Q2", "out_of_scope"), ("Q3", "proposed")):
            conn.execute("INSERT INTO pg_temp.person (qid, status, country) VALUES (%s, %s, 'zz')",
                         (qid, status))
        dead = {"claims": {"P570": [{"rank": "normal", "mainsnak": {"datavalue": {
            "value": {"time": "+2025-01-01T00:00:00Z", "precision": 11}}}}]}}
        conn.execute("INSERT INTO pg_temp.item (qid, json) VALUES ('Q3', %s)", (Jsonb(dead),))
        positions = [{"title": f"Office {i}", "start": "2024", "acting": i == 2,
                      "quotes": [f"quote {i}"]} for i in range(4)]
        for eid, qid in ((1, "Q1"), (2, "Q2"), (3, "Q3"), (4, "Q1"), (5, "Q1")):
            conn.execute("INSERT INTO pg_temp.extraction (id, qid, prompt_hash, model, response_json)"
                         " VALUES (%s, %s, 'h', 'm', %s)", (eid, qid, Jsonb({"positions": positions})))
        rid = 0

        def resolve(eid: int, idx: int, qid: str | None) -> None:
            nonlocal rid
            rid += 1
            conn.execute(
                "INSERT INTO pg_temp.resolution (id, extraction_id, mention_idx, title, start_text,"
                " prompt_hash, render_version, model, qid, kind, confidence)"
                " VALUES (%s, %s, %s, %s, '2024', 'h', 1, 'm', %s, 'none', 'low')",
                (rid, eid, idx, f"Office {idx}", qid))

        resolve(1, 0, None)          # an older extraction of Q1: not read
        resolve(5, 0, None)          # refused, then placed by a re-ask
        resolve(5, 0, "Q99")
        resolve(5, 1, "Q98")         # placed, then refused by a later prompt
        resolve(5, 1, None)
        resolve(5, 2, None)          # acting
        resolve(2, 0, None)          # out of scope
        resolve(3, 3, None)          # a dead holder
        got = {(r.extraction_id, r.mention_idx): r for r in mint.unplaced("zz", TODAY)}
        expect(set(got) == {(5, 1), (5, 2), (3, 3)},
               "the newest verdict decides, on the newest extraction, out-of-scope people excluded")
        expect(got[(5, 2)].acting and not got[(5, 2)].current, "acting is read off the extraction")
        expect(got[(3, 3)].death == "+2025-01-01T00:00:00Z" and not got[(3, 3)].current,
               "a P570 on the item makes the holder not current")
        expect(got[(5, 1)].current and got[(5, 1)].quote == "quote 1",
               "a live open tenure is current, and carries its quote")
    finally:
        for table in tables:
            conn.execute(f"DROP TABLE IF EXISTS pg_temp.{table}")


def main() -> int:
    """Run every pin and report."""
    failures: list[str] = []

    def expect(condition: bool, message: str) -> None:
        print(("  ok   " if condition else "  FAIL ") + message)
        if not condition:
            failures.append(message)

    for name, check in (
        ("current", check_current),
        ("group_key", check_group_key),
        ("floor", check_floor),
        ("census", check_census),
        ("classes", check_classes),
        ("unplaced", check_unplaced),
    ):
        print(f"{name}:")
        check(expect)
    print(f"{len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
