"""Pin how the holders of minted unit and body offices enter the person lane.

The holder of an office `mint_units` made reaches the lane by its item: the
unit's own head statement, or the link an infobox puts on the holder's name.
What this file guards is that a link is followed only to a living human with
an article in the unit's wiki -- an unlinked name is never searched for --
that only offices which exist have their holders seeded, and that seeding is
the ordinary upsert, so someone already in the lane keeps their status.

No network: the article, the page's item and the item are fabricated. The
person, membership and candidate tables are shadowed by temporary ones. Run
it as `python -m peploop.check_holders` from the repository root.
"""

import sys
from typing import Any

import psycopg
from click.testing import CliRunner
from psycopg.types.json import Jsonb

from peploop import cli, db, holders, wikipedia

TABLES = ("person", "membership", "office_candidate")
COUNTRY = "zz"
URL = "https://xx.wikipedia.org/wiki/Lindo"
ARTICLE = """<html><body>
<table class="infobox"><tbody>
<tr><th>Bürgermeister</th><td><a rel="mw:WikiLink" href="./Ann_Smith_(Politikerin)" title="Ann Smith">Ann Smith</a>
 (<a rel="mw:WikiLink" href="./Partei" title="Partei">Partei</a>)<sup class="mw-ref reference"><a href="#cite">[1]</a></sup></td></tr>
<tr><th>Landrat</th><td><a rel="mw:WikiLink" href="./Bob_Red?action=edit&amp;redlink=1" class="new">Bob Red</a></td></tr>
<tr><th>Vorsitz</th><td><a rel="mw:WikiLink" href="./Cara_Doe" title="Cara Doe">Cara Doe</a> and
 <a rel="mw:WikiLink" href="./Cara_Doe_junior" title="Cara Doe junior">Cara Doe</a></td></tr>
<tr><th>Kämmerer</th><td>Dan Plain</td></tr>
</tbody></table>
<p>Ann Smith is mentioned in <a rel="mw:WikiLink" href="./Other_Ann_Smith">Ann Smith</a> prose too.</p>
</body></html>"""
PAGES = {"Ann Smith (Politikerin)": "Q1", "Cara Doe": "Q3", "Eve Dead": "Q4", "Fayette Catt": "Q5", "Gustav Farley": "Q6"}


def human(lang: str = "xx", dead: bool = False, kind: str = "Q5") -> dict[str, Any]:
    claims: dict[str, Any] = {"P31": [{"rank": "normal", "mainsnak": {"datavalue": {"value": {"id": kind}}}}]}
    if dead:
        claims["P570"] = [{"rank": "normal", "mainsnak": {"datavalue": {"value": {"time": "+2020-01-01T00:00:00Z"}}}}]
    return {"claims": claims, "sitelinks": {f"{lang}wiki": {"title": "x"}}}


ITEMS = {"Q1": human(), "Q3": human(), "Q4": human(dead=True), "Q5": human(kind="Q146"), "Q6": human(lang="yy")}


def lookup(html: str = ARTICLE) -> holders.Lookup:
    return holders.Lookup(html=lambda _lang, _title: html, page_item=lambda _lang, t: PAGES.get(t),
                          items=lambda qids: {q: ITEMS[q] for q in qids if q in ITEMS})


def one_link(name: str, target: str) -> str:
    return (f'<table class="infobox"><tr><th>Mayor</th><td><a rel="mw:WikiLink" href="./{target.replace(" ", "_")}">'
            f"{name}</a></td></tr></table>")


def main() -> int:
    failures: list[str] = []

    def expect(got: Any, want: Any, message: str) -> None:
        ok = got == want
        print(("  ok   " if ok else "  FAIL ") + message + ("" if ok else f" (got {got!r})"))
        if not ok:
            failures.append(message)

    print("the infobox's links:")
    lines = wikipedia.infobox_links(ARTICLE)
    expect(lines[0], ("Bürgermeister: Ann Smith (Partei)",
                      [("Ann Smith", "Ann Smith (Politikerin)"), ("Partei", "Partei")]),
           "each line as the text writes it, footnote dropped, with the pages its links target")
    expect(lines[1][1], [], "a red link names no page")
    expect(len(lines), 4, "prose links are not infobox lines")

    print("resolving a named holder:")
    expect(holders.resolve("Ann Smith", "xx", URL, lookup()), ("Q1", "holder/link"),
           "the link on the name is followed to a living human with an article in the unit's wiki")
    expect(holders.resolve("Bob Red", "xx", URL, lookup()), (None, "holder/unlinked"), "a red link is residue")
    expect(holders.resolve("Dan Plain", "xx", URL, lookup()), (None, "holder/unlinked"),
           "and so is a name with no link: it is never searched for")
    expect(holders.resolve("Cara Doe", "xx", URL, lookup()), (None, "holder/several-links"),
           "a line linking the name to two pages is not guessed between")
    expect(holders.resolve("Hal Gone", "xx", URL, lookup(one_link("Hal Gone", "Hal Gone"))),
           (None, "holder/no-item"), "a page with no item is residue")
    for name, why, message in (("Eve Dead", "holder/dead", "a dead holder"),
                               ("Fayette Catt", "holder/not-human", "an item that is no human"),
                               ("Gustav Farley", "holder/other-wiki", "an item whose article is in another wiki")):
        expect(holders.resolve(name, "xx", URL, lookup(one_link(name, name))), (None, why), f"{message} is refused")
    expect(holders.resolve("Ann Smith", "xx", "https://www.wikidata.org/wiki/Q20", lookup()),
           (None, "holder/no-article"), "a unit with no article has no infobox to read")

    try:
        conn = db.conn()
    except psycopg.OperationalError as exc:
        print(f"skip the seeding cases: no database ({exc.__class__.__name__})")
        return 1 if failures else 0
    for table in TABLES:
        conn.execute(f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING DEFAULTS"
                     " INCLUDING INDEXES INCLUDING CONSTRAINTS)")
    conn.execute("CREATE TEMP SEQUENCE office_candidate_seq")
    conn.execute("ALTER TABLE pg_temp.office_candidate ALTER COLUMN id SET DEFAULT nextval('pg_temp.office_candidate_seq')")
    try:
        def candidate(ref: str, status: str, unit: dict[str, Any], qid: str | None = "Q900",
                      origin: str = "{unit}") -> None:
            conn.execute("INSERT INTO office_candidate (country, ref, origin, status, qid, draft)"
                         " VALUES (%s, %s, %s, %s, %s, %s)",
                         (COUNTRY, ref, origin, status, qid, Jsonb({"unit": unit})))

        candidate("unit/a/Q20", "created", {"holder": "Ida P6", "holder_qid": "Q7", "url": URL, "lang": "xx"})
        candidate("unit/a/Q21", "found", {"holder": "Ann Smith", "holder_qid": None, "url": URL, "lang": "xx"},
                  qid="Q901")
        candidate("unit/a/Q22", "loaded", {"holder": "Dan Plain", "url": URL})
        candidate("unit/a/Q23", "guarded", {"holder": "Joe Waiting", "holder_qid": "Q8", "url": URL, "lang": "xx"},
                  qid=None)
        candidate("unit/a/Q24", "creating", {"holder": "Kim Flight", "holder_qid": "Q9", "url": URL, "lang": "xx"},
                  qid=None)
        candidate("mention/x", "created", {"holder_qid": "Q10"}, origin="{reconcile}")
        conn.execute("INSERT INTO person (qid, country, status) VALUES ('Q7', 'yy', 'proposed')")

        print("which offices' holders are seeded:")
        found = holders.holders(COUNTRY, lookup=lookup())
        expect([(h.ref, h.qid, h.how) for h in found],
               [("unit/a/Q20", "Q7", "holder/statement"), ("unit/a/Q21", "Q1", "holder/link"),
                ("unit/a/Q22", None, "holder/unlinked")],
               "created, found and loaded offices only: not one guarded or in flight, nor a mention's office")
        expect(found[2].lang, "xx", "a draft without a language takes its article's wiki")

        counts = holders.seed(COUNTRY, found)
        expect(counts["new"], 1, "only the holder new to the lane is counted new")
        expect(conn.execute("SELECT qid, country, status FROM person ORDER BY qid").fetchall(),
               [("Q1", COUNTRY, "queued"), ("Q7", "yy", "proposed")],
               "a holder is queued under the run's country; one already in the lane keeps status and stamp")
        expect(conn.execute("SELECT qid, category, lang FROM membership ORDER BY qid").fetchall(),
               [("Q1", "holder:Q901", "xx"), ("Q7", "holder:Q900", "xx")],
               "each membership names the office, in the unit's wiki")

        print("the command:")
        runner = CliRunner()
        result = runner.invoke(cli.cli, ["seed", "--country", COUNTRY, "--qid", "Q11", "--qid", "Q1", "--lang", "xx"])
        expect((result.exit_code, result.output.strip().splitlines()[-1:]), (0, ["2 people named, 1 new"]),
               "`seed --qid` queues named people, new ones counted")
        expect(conn.execute("SELECT country, status FROM person WHERE qid = 'Q11'").fetchone(),
               (COUNTRY, "queued"), "under the run's country")
        result = runner.invoke(cli.cli, ["seed", "--country", COUNTRY, "--qid", "Q12"])
        expect(result.exit_code != 0 and "--lang" in result.output, True, "and needs the wiki they are read in")
    finally:
        for table in TABLES:
            conn.execute(f"DROP TABLE IF EXISTS pg_temp.{table}")
        conn.execute("DROP SEQUENCE IF EXISTS pg_temp.office_candidate_seq")

    print(f"{len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
