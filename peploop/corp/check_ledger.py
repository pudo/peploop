"""Pin the answer ledger: a re-plan takes each body's newest answer, under whichever decide prompt asked it.

Runs against temporary tables shadowing `pcorp_call` and `pcorp_item`.

    .venv/bin/python -m peploop.corp.check_ledger
"""

from psycopg.types.json import Jsonb

from peploop.corp import decide, wd
from peploop.corp.check_rules import answer
from peploop.checks import expect

TABLES = ("pcorp_call", "pcorp_item")
CC = "zz"


def call(key: str, qid: str, prompt: str, ans: dict, when: str, request: dict | None = None) -> None:
    wd.conn().execute(
        "INSERT INTO pcorp_call (key, country, qid, model, prompt_hash, request, answer, usage, created_at)"
        " VALUES (%s,%s,%s,'m',%s,%s,%s,'{}',%s)",
        (key, CC, qid, prompt, Jsonb(request or {"message": key, "offered": [], "links": {}, "articles": []}),
         Jsonb(ans), when))


def main() -> None:
    conn = wd.conn()
    for table in TABLES:
        conn.execute(f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING DEFAULTS INCLUDING CONSTRAINTS)")
    try:
        for qid in ("Q900001", "Q900002", "Q900003"):
            conn.execute("INSERT INTO pcorp_item (country, qid, lanes, entity) VALUES (%s,%s,'{}','{}')", (CC, qid))
        new = {**answer(), "statutory": None}
        new["control"]["ended"] = None
        call("a-old", "Q900001", "p1", new, "2026-10-01")
        call("a-new", "Q900001", "p2", new, "2026-10-02")
        call("b-old", "Q900002", "p1", new, "2026-10-01")
        call("b-check", "Q900002", "v1", {"supports": True}, "2026-10-03", {"message": "x", "link": []})
        call("c-stale", "Q900003", "p0", answer(), "2026-10-03")
        call("d-dropped", "Q900004", "p2", new, "2026-10-02")
        got = {r["qid"]: r["key"] for r in decide.from_ledger(CC)}
        expect(got.get("Q900001") == "a-new", "a body asked under a new prompt takes that answer")
        expect(got.get("Q900002") == "b-old", "a body not asked again keeps its older prompt's answer, not a check's row")
        expect("Q900003" not in got, "an answer the current schema cannot read is passed over")
        expect("Q900004" not in got, "a body the last load dropped has no answer")
    finally:
        for table in TABLES:
            conn.execute(f"DROP TABLE IF EXISTS pg_temp.{table}")


if __name__ == "__main__":
    main()
