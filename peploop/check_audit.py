"""Pin the audit: a proposal taken out by hand stays out across a re-propose.

The hazard this exists for: an audit used to be a raw `UPDATE proposal SET
status = 'skipped'`, and `propose` re-derives every row that is neither
`applied` nor carrying a verdict, so the next re-propose of that person wiped
it and the policy decided the row again from scratch -- one country's fourteen
`audit:pudo` rows went that way. So the cases are: an audit leaves a verdict
and `audit:<by>` provenance, a re-propose keeps the row and does not insert
its twin, the policy no longer selects it, and an audit refuses a row already
written, a row of another country's run, and an unknown id, all or nothing.
Every case runs against temporary tables shadowing the real ones.

Run it as `python -m peploop.check_audit` from the repository root.
"""

import sys
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from peploop import db, policy, propose

TABLES = ("proposal", "verdict", "person", "item", "article")
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

        print("refusals:")
        for ids, why in (
            ([doubted, written], "a row already on Wikidata"),
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

        print("re-propose:")
        again = [propose.Proposal("P39", office(q), "new", quote="a quote", lang="en")
                 for q in ("Q100", "Q101", "Q103")]
        counts, kept = propose._store(PERSON, again, extraction_id=1, item_rev=None)
        expect(state(conn, doubted) == ("skipped", "audit:fl"),
               "a re-propose keeps the audited row, status and provenance")
        twins = conn.execute("SELECT count(*) FROM proposal WHERE person_qid = %s"
                             " AND value->>'id' = 'Q100'", (PERSON,)).fetchone()[0]
        expect(twins == 1, "and does not insert its twin beside it")
        expect(state(conn, other) is None and kept == 2,
               "while an unaudited row is re-derived as before (the applied one is kept too)")
        cases = [pid for pid, _case in policy.person_cases(PERSON)]
        expect(doubted not in cases and cases,
               "the policy no longer selects the audited row")
    finally:
        unshadow(conn)
    print(f"{len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
