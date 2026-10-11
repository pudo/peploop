"""Pin the audit: a proposal taken out by hand stays out across a re-propose.

The hazard this exists for: an audit used to be a raw `UPDATE proposal SET
status = 'skipped'`, and `propose` re-derives every row that is neither
`applied` nor carrying a verdict, so the next re-propose of that person wiped
it and the policy decided the row again from scratch -- one country's fourteen
`audit:pudo` rows went that way. So the cases are: an audit leaves a verdict
and `audit:<by>` provenance, a re-propose keeps the row and does not insert
its twin, the policy no longer selects it, and an audit refuses a row already
written, a row of another country's run, and an unknown id, all or nothing,
through the function and through `cli audit`.
Every case runs against temporary tables shadowing the real ones.

Run it as `python -m peploop.check_audit` from the repository root.
"""

import sys
from typing import Any

import psycopg
from click.testing import CliRunner
from psycopg.types.json import Jsonb

from peploop import cli, db, policy, propose

#: The send ledger is shadowed too: an audit strikes what it takes out.
TABLES = ("proposal", "verdict", "person", "item", "article", "wd_strike", "wd_removal", "wd_edit", "wd_batch")
SEQUENCES = ("proposal", "verdict")
COUNTRY = "zz"
PERSON = "Q9000001"
STRANGER = "Q9000002"


def shadow(conn: psycopg.Connection) -> None:
    for table in TABLES:
        conn.execute(f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING DEFAULTS"
                     " INCLUDING INDEXES INCLUDING CONSTRAINTS)")
    for table in SEQUENCES:
        conn.execute(f"CREATE TEMP SEQUENCE {table}_seq")
        conn.execute(f"ALTER TABLE pg_temp.{table} ALTER COLUMN id SET DEFAULT"
                     f" nextval('pg_temp.{table}_seq')")


def unshadow(conn: psycopg.Connection) -> None:
    for table in TABLES:
        conn.execute(f"DROP TABLE IF EXISTS pg_temp.{table}")
    for table in SEQUENCES:
        conn.execute(f"DROP SEQUENCE IF EXISTS pg_temp.{table}_seq")


def office(qid: str) -> dict[str, Any]:
    return {"entity-type": "item", "id": qid}


def row(conn: psycopg.Connection, person: str, qid: str, status: str,
        decided_by: str | None = None) -> int:
    return conn.execute(
        "INSERT INTO proposal (person_qid, property, value, quote, status, decided_by)"
        " VALUES (%s, 'P39', %s, 'a quote', %s, %s) RETURNING id",
        (person, Jsonb(office(qid)), status, decided_by),
    ).fetchone()[0]


def state(conn: psycopg.Connection, ident: int) -> tuple[Any, ...] | None:
    return conn.execute("SELECT status, decided_by FROM proposal WHERE id = %s",
                        (ident,)).fetchone()


def main() -> int:
    """Run every pin and report."""
    failures: list[str] = []

    def expect(condition: bool, message: str) -> None:
        print(("  ok   " if condition else "  FAIL ") + message)
        if not condition:
            failures.append(message)

    try:
        conn = db.conn()
    except psycopg.OperationalError as exc:
        print(f"skip: no database ({exc.__class__.__name__})")
        return 0
    shadow(conn)
    try:
        conn.execute("INSERT INTO person (qid, country, status) VALUES (%s, %s, 'proposed'),"
                     " (%s, 'zy', 'proposed')", (PERSON, COUNTRY, STRANGER))
        conn.execute("INSERT INTO item (qid, json) VALUES (%s, %s)",
                     (PERSON, Jsonb({"claims": {}})))
        doubted = row(conn, PERSON, "Q100", "accepted", "policy:supported")
        other = row(conn, PERSON, "Q101", "accepted", "policy:supported")
        written = row(conn, PERSON, "Q102", "applied", "policy:supported")
        foreign = row(conn, STRANGER, "Q100", "accepted", "policy:supported")
        inflight = row(conn, PERSON, "Q105", "sent", "policy:supported")

        print("refusals:")
        for ids, why in (
            ([doubted, inflight], "a row whose edit is in flight"),
            ([doubted, foreign], "a row of another country's run"),
            ([doubted, 999999], "an unknown id"),
        ):
            try:
                policy.audit(ids, "doubted", "fl", COUNTRY)
                refused = False
            except ValueError:
                refused = True
            expect(refused and state(conn, doubted) == ("accepted", "policy:supported"),
                   f"refuses {why}, and leaves the good id in the same call alone")
        try:
            policy.audit([doubted], " ", "fl", COUNTRY)
            refused = False
        except ValueError:
            refused = True
        expect(refused, "an audit with no reason is refused")

        print("audit:")
        policy.audit([doubted], "a career span written as one tenure", "fl", COUNTRY)
        expect(state(conn, doubted) == ("skipped", "audit:fl"),
               "the row is skipped under audit:<by>")
        verdict = conn.execute("SELECT decision, reason, note, decided_by FROM verdict"
                               " WHERE proposal_id = %s", (doubted,)).fetchall()
        expect(verdict == [("reject", "other", "a career span written as one tenure", "audit:fl")],
               "and carries a reject verdict with the reason and who decided")

        struck = conn.execute("SELECT qid, prop, value, origin FROM wd_strike").fetchall()
        expect(struck == [(PERSON, "P39", "Q100", "audit:fl")],
               "and the statement is struck, so no later row sends it either")

        print("re-propose:")
        again = [propose.Proposal("P39", office(q), "new", quote="a quote", lang="en")
                 for q in ("Q100", "Q101", "Q103")]
        counts, kept = propose._store(PERSON, again, extraction_id=1, item_rev=None)
        expect(state(conn, doubted) == ("skipped", "audit:fl"),
               "a re-propose keeps the audited row, status and provenance")
        twins = conn.execute("SELECT count(*) FROM proposal WHERE person_qid = %s"
                             " AND value->>'id' = 'Q100'", (PERSON,)).fetchone()[0]
        expect(twins == 1, "and does not insert its twin beside it")
        expect(state(conn, other) is None and kept == 3,
               "while an unaudited row is re-derived as before (the applied and sent ones are kept too)")
        cases = [pid for pid, _case in policy.person_cases(PERSON)]
        expect(doubted not in cases and cases,
               "the policy no longer selects the audited row")

        print("re-propose, a row apply closed:")
        born = {"time": "+1960-03-01T00:00:00Z", "precision": 11, "timezone": 0, "before": 0,
                "after": 0, "calendarmodel": "http://www.wikidata.org/entity/Q1985727"}
        other_birth = {**born, "time": "+1961-07-04T00:00:00Z"}
        closed = conn.execute(
            "INSERT INTO proposal (person_qid, property, value, quote, status, decided_by)"
            " VALUES (%s, 'P569', %s, 'a quote', 'skipped', 'apply:conflict') RETURNING id",
            (PERSON, Jsonb(born)),
        ).fetchone()[0]
        recorded = {"claims": {"P569": [{"rank": "normal", "mainsnak": {
            "property": "P569", "snaktype": "value", "datatype": "time",
            "datavalue": {"type": "time", "value": other_birth}}}]}}
        again.append(propose.Proposal("P569", born, "conflict", quote="a quote", lang="en"))
        propose._store(PERSON, again, extraction_id=1, item_rev=None, entity=recorded)
        expect(state(conn, closed) == ("skipped", "apply:conflict"),
               "keeps it, and its provenance, while the item still closes it")
        propose._store(PERSON, again, extraction_id=1, item_rev=None, entity={"claims": {}})
        expect(state(conn, closed) is None,
               "and re-derives it once the item no longer does")

        print("an applied row:")
        guid = f"{PERSON}$0000-2222"
        conn.execute("UPDATE proposal SET claim_guid = %s WHERE id = %s", (guid, written))
        policy.audit([written], "not this office", "fl", COUNTRY)
        expect(state(conn, written) == ("applied", "policy:supported"),
               "stays applied: it is on Wikidata until it is taken off")
        removal = conn.execute("SELECT guid, status, ours FROM wd_removal").fetchall()
        expect(removal == [(guid, "proposed", False)],
               "and its statement's removal is proposed: a statement sent before the ledger is not provably ours")

        print("command:")
        runner = CliRunner()
        fresh = row(conn, PERSON, "Q104", "accepted", "policy:supported")
        args = ["--country", COUNTRY, "--reason", "stale infobox", "--by", "fl"]
        res = runner.invoke(cli.audit_, ["proposal", str(inflight), str(fresh), *args])
        expect(res.exit_code != 0 and state(conn, fresh) == ("accepted", "policy:supported"),
               f"`audit proposal` refuses a row in flight and the call with it ({res.output.strip()})")
        res = runner.invoke(cli.audit_, ["proposal", "--ids", "-", *args], input=f"{fresh}\n")
        expect(res.exit_code == 0 and state(conn, fresh) == ("skipped", "audit:fl"),
               f"`audit proposal --ids -` skips the listed row ({res.output.strip()})")
        expect(not any(p.name in ("approve", "accept") for p in cli.audit_.params),
               "the command has no approve path")
    finally:
        unshadow(conn)
    print(f"{len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
