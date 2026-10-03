"""Pin the write half of minting: crash safety, recovery, feeding, and the audit.

A creation cannot be undone by an edit, so every transition around it is pinned
here offline: a crash between the intent and the recorded QID, a recovery that
finds the edit and one that does not, a label conflict, a re-check that
refuses, a second call on a done row, a feed run twice, and an audit that tries
to skip a created row. Every case runs against temporary tables shadowing the
real ones, and apply's HTTP is replaced by a function that fails the check if
anything reaches it, so nothing is read from or written to Wikidata.

Run it as `python -m peploop.check_mint_write` from the repository root.
"""

import sys
from typing import Any, Callable

import psycopg
from click.testing import CliRunner
from psycopg.types.json import Jsonb

from peploop import apply, cli, db, mint_write, positions, propose, reconcile

TABLES = ("office_candidate", "office_attestation", "mint_call", "office_unassigned",
          "resolution", "extraction")
SEQUENCES = ("office_candidate", "mint_call", "resolution", "extraction")
COUNTRY = "zz"
DATA = {"labels": {"en": {"language": "en", "value": "Mayor of Velmora"}},
        "descriptions": {}, "aliases": {}, "claims": []}
SPEC = {"ref": "mayor-of-velmora@", "archetype": "mayor", "state_qid": "Q900",
        "labels": {"en": "Mayor of Velmora"}}


class Crash(BaseException):
    """A process dying mid-write: not an `Exception`, so nothing catches it."""


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


def candidate(conn: psycopg.Connection, ref: str, status: str = "guarded", **kw: Any) -> int:
    cols = {"country": COUNTRY, "ref": ref, "status": status, "data": Jsonb(DATA),
            "spec": Jsonb(SPEC), "holders": 2, "current_holders": 1}
    cols.update(kw)
    names = ", ".join(cols)
    marks = ", ".join(["%s"] * len(cols))
    return conn.execute(f"INSERT INTO office_candidate ({names}) VALUES ({marks}) RETURNING id",
                        list(cols.values())).fetchone()[0]


def state(conn: psycopg.Connection, cid: int) -> tuple[Any, ...]:
    return conn.execute("SELECT status, qid, rule FROM office_candidate WHERE id = %s",
                        (cid,)).fetchone()


clean: Callable[[dict[str, Any]], list[str]] = lambda _c: []  # noqa: E731


def check_crash(expect: Any, conn: psycopg.Connection) -> None:
    """A crash after the intent commit is recovered from the edit log, not resent."""
    cid = candidate(conn, "crash-after-create")
    wikidata_log: dict[str, str] = {}

    def create(data: dict[str, Any], summary: str, token: str) -> tuple[str, int]:
        tag = summary.split("[", 1)[1].split("]", 1)[0]
        wikidata_log[tag] = "Q7001"  # the item exists on Wikidata ...
        raise Crash()  # ... and the process dies before the row records it

    apply.create_item = create
    try:
        mint_write.mint_one(cid, "token", recheck=clean)
    except Crash:
        pass
    status, qid, _rule = state(conn, cid)
    tag, intent_at = conn.execute("SELECT intent_tag, intent_at FROM office_candidate WHERE id = %s",
                                  (cid,)).fetchone()
    expect(status == "creating" and qid is None and intent_at is not None
           and tag.startswith(f"peploop-mint:{COUNTRY}:crash-after-create:"),
           "a crash after the intent commit leaves the row creating, tagged, without a QID")
    out = mint_write.recover(COUNTRY, find=lambda t, _since: wikidata_log.get(t),
                             lookup=lambda _c: None)
    expect(out == [(cid, "created", "Q7001")] and state(conn, cid) == ("created", "Q7001", "mint:recovered"),
           "recover finds the item by its tag and records it as created")


def check_lock(expect: Any, conn: psycopg.Connection) -> None:
    """Two writers for one country cannot both run recover."""
    with mint_write.writer_lock(COUNTRY):
        other = psycopg.connect(db.DATABASE_URL, autocommit=True)
        try:
            taken = other.execute("SELECT pg_try_advisory_lock(hashtext(%s))",
                                  (f"peploop-mint:{COUNTRY}",)).fetchone()[0]
        finally:
            other.close()
    expect(not taken, "a second writer is refused the country's lock")
    with mint_write.writer_lock(COUNTRY, "apply"):
        other = psycopg.connect(db.DATABASE_URL, autocommit=True)
        try:
            taken = other.execute("SELECT pg_try_advisory_lock(hashtext(%s))",
                                  (f"peploop-apply:{COUNTRY}",)).fetchone()[0]
            mint_free = other.execute("SELECT pg_try_advisory_lock(hashtext(%s))",
                                      (f"peploop-mint:{COUNTRY}",)).fetchone()[0]
        finally:
            other.close()
    expect(not taken, "a second drain of one country is refused: the API writes twice")
    expect(mint_free, "and the apply lock is its own, so a mint writer is not held up by it")


def check_resend(expect: Any, conn: psycopg.Connection) -> None:
    """A crash before the edit landed is put back to guarded and sent exactly once."""
    cid = candidate(conn, "crash-before-create")
    sent: list[str] = []

    def die(data: dict[str, Any], summary: str, token: str) -> tuple[str, int]:
        raise Crash()

    apply.create_item = die
    try:
        mint_write.mint_one(cid, "token", recheck=clean)
    except Crash:
        pass
    out = mint_write.recover(COUNTRY, find=lambda _t, _s: None, lookup=lambda _c: None)
    expect(out == [(cid, "guarded", None)] and state(conn, cid)[0] == "guarded",
           "no edit and a clean live lookup put the row back to guarded")

    def create(data: dict[str, Any], summary: str, token: str) -> tuple[str, int]:
        sent.append(summary)
        return "Q7002", 42

    apply.create_item = create
    first = mint_write.mint_one(cid, "token", recheck=clean)
    second = mint_write.mint_one(cid, "token", recheck=clean)
    rev, batch = conn.execute("SELECT created_rev, batch FROM office_candidate WHERE id = %s",
                              (cid,)).fetchone()
    expect(first == "Q7002" and len(sent) == 1 and state(conn, cid) == ("created", "Q7002", "mint:created")
           and rev == 42 and batch == apply.BATCH_ID,
           "the next mint_one resends exactly once and records qid, revision and batch")
    expect(second is None and len(sent) == 1, "a second mint_one on a created row does nothing")
    expect("peploop-mint:" in sent[0], "the summary carries the intent tag")

    other = candidate(conn, "crash-dup")
    conn.execute("UPDATE office_candidate SET status = 'creating', intent_tag = 't', intent_at = now()"
                 " WHERE id = %s", (other,))
    mint_write.recover(COUNTRY, find=lambda _t, _s: None, lookup=lambda _c: "Q7003")
    expect(state(conn, other) == ("found", "Q7003", "guard:duplicate"),
           "no edit and a live duplicate make the interrupted row found")


def check_refusals(expect: Any, conn: psycopg.Connection) -> None:
    """A label conflict is found; a refusing re-check skips; another error stays creating."""
    sent: list[str] = []

    def conflict(data: dict[str, Any], summary: str, token: str) -> tuple[str, int]:
        sent.append(summary)
        raise apply.LabelConflict("modification-failed", "already has label", "Q7010")

    apply.create_item = conflict
    cid = candidate(conn, "label-conflict")
    expect(mint_write.mint_one(cid, "token", recheck=clean) == "Q7010"
           and state(conn, cid) == ("found", "Q7010", "api:label-conflict"),
           "a label conflict records the named item as found")

    refused = candidate(conn, "refused")
    mint_write.mint_one(refused, "token", recheck=lambda _c: ["body-word/Q5", "holders/1"])
    expect(state(conn, refused) == ("skipped", None, "guard:body-word/Q5") and len(sent) == 1,
           "a re-check that refuses skips under guard:<reason> and sends nothing")
    dup = candidate(conn, "refused-dup")
    mint_write.mint_one(dup, "token", recheck=lambda _c: ["duplicate/Q7011"])
    expect(state(conn, dup) == ("found", "Q7011", "guard:duplicate") and len(sent) == 1,
           "a re-check that finds a duplicate records it as found")

    def refused_api(data: dict[str, Any], summary: str, token: str) -> tuple[str, int]:
        raise apply.ApiError("failed-save", "something else")

    apply.create_item = refused_api
    err = candidate(conn, "api-error")
    try:
        mint_write.mint_one(err, "token", recheck=clean)
        raised = False
    except apply.ApiError:
        raised = True
    expect(raised and state(conn, err)[0] == "creating",
           "any other API error raises and leaves the row creating for recover")
    conn.execute("DELETE FROM office_candidate WHERE id = %s", (err,))

    skipped = candidate(conn, "not-guarded", status="skipped", rule="disagree/x")
    apply.create_item = lambda *_a: (_ for _ in ()).throw(AssertionError("sent"))
    expect(mint_write.mint_one(skipped, "token", recheck=clean) is None
           and state(conn, skipped)[0] == "skipped", "a row not guarded is never sent")


def check_feed(expect: Any, conn: psycopg.Connection) -> None:
    """Feed reopens only attested, retrievable mentions, and a rerun does nothing new."""
    entries = [{"title": f"Mayor of Velmora {i}", "quotes": ["q"], "lang": "en"} for i in range(3)]
    eid = conn.execute("INSERT INTO extraction (qid, prompt_hash, model, response_json) VALUES"
                       " ('Q8001', 'h', 'm', %s) RETURNING id", (Jsonb({"positions": entries}),)
                       ).fetchone()[0]
    cid = candidate(conn, "fed", status="created", qid="Q7100", rule="mint:created")
    for idx in (0, 1):
        conn.execute("INSERT INTO office_attestation (candidate_id, extraction_id, mention_idx,"
                     " person_qid, current) VALUES (%s, %s, %s, 'Q8001', true)", (cid, eid, idx))
    loaded: list[tuple[list[str], str]] = []
    reopened: list[int] = []
    proposed: list[str] = []
    positions.load_qids = lambda qids, source="minted", log=None: loaded.append((list(qids), source)) or {}
    positions.fill_diplomatic = lambda qids=None, log=None: 0
    reconcile.retrievable = lambda mention, _s, _q: mention.title.endswith("0")

    def reopen(e: int, i: int, mention: Any, s: Any, qid: str, model: str = "") -> tuple[Any, bool]:
        reopened.append(i)
        conn.execute("INSERT INTO resolution (extraction_id, mention_idx, title, prompt_hash,"
                     " render_version, model, kind, confidence, reopened_for, qid)"
                     " VALUES (%s, %s, %s, 'h', 2, 'm', 'same-office', 'high', %s, %s)",
                     (e, i, mention.title, qid, qid))
        return reconcile.Verdict(title=mention.title, qid=qid, kind="same-office"), True

    reconcile.reopen = reopen
    propose.propose_person = lambda qid: proposed.append(qid)
    first = mint_write.feed(COUNTRY, [cid])
    rows = conn.execute("SELECT mention_idx, retrieved, reopened_id IS NOT NULL FROM office_attestation"
                        " WHERE candidate_id = %s ORDER BY mention_idx", (cid,)).fetchall()
    expect(loaded == [(["Q7100"], "minted")], "a created item is loaded with source minted")
    expect(reopened == [0] and rows == [(0, True, True), (1, False, False)],
           "only the attested mention the search would surface is reopened; idx 2 is never touched")
    expect(first.loaded == 1 and first.retrieved == {True: 1, False: 1}
           and first.reopened == {"same-office": 1} and proposed == ["Q8001"],
           "the counts say what was loaded, retrieved, reopened and proposed")
    expect(state(conn, cid)[0] == "loaded", "the candidate is loaded")
    second = mint_write.feed(COUNTRY, [cid])
    expect(second.loaded == 0 and reopened == [0] and proposed == ["Q8001"],
           "a second feed does nothing new")
    found = candidate(conn, "fed-found", status="found", qid="Q7101", rule="guard:duplicate")
    mint_write.feed(COUNTRY, [found])
    expect(loaded[-1] == (["Q7101"], "found"), "a found item is loaded with source found")


def check_audit(expect: Any, conn: psycopg.Connection) -> None:
    """The audit skips a guarded row and refuses a created one; there is no approve."""
    runner = CliRunner()
    made = candidate(conn, "audit-created", status="created", qid="Q7200", rule="mint:created")
    res = runner.invoke(cli.mint_audit, ["--id", str(made), "--skip", "--reason", "wrong", "--by", "fl"])
    expect(res.exit_code != 0 and state(conn, made)[0] == "created",
           f"mint-audit refuses a created row ({res.output.strip()})")
    open_ = candidate(conn, "audit-guarded")
    res = runner.invoke(cli.mint_audit, ["--id", str(open_), "--skip", "--reason", "a party post",
                                          "--by", "fl"])
    problems = conn.execute("SELECT problems, decided_by FROM office_candidate WHERE id = %s",
                            (open_,)).fetchone()
    expect(res.exit_code == 0 and state(conn, open_) == ("skipped", None, "audit:fl")
           and problems == (["audit: a party post"], "fl"),
           "mint-audit skips a guarded row under audit:<by>, keeping the reason")
    res = runner.invoke(cli.mint_audit, ["--id", str(open_), "--reason", "x", "--by", "fl"])
    expect(res.exit_code != 0, "without --skip there is nothing an audit can do")
    expect(not any(p.name in ("approve", "accept") for p in cli.mint_audit.params),
           "mint-audit has no approve path")


def check_report(expect: Any, conn: psycopg.Connection) -> None:
    conn.execute("INSERT INTO mint_call (pass, country, content_key, prompt_hash, render_version,"
                 " model, usage_json) VALUES ('categorize', %s, 'k', 'h', 1, 'claude-sonnet-5', %s)",
                 (COUNTRY, Jsonb({"input_tokens": 1_000_000, "output_tokens": 100_000})))
    text = mint_write.report(COUNTRY)
    expect("## Funnel" in text and "| categorize | claude-sonnet-5 | 1 | 1000000 | 100000 | 0 | 0 | 3.00 |"
           in text, "the report prices a pass from its usage")
    expect("audit:fl" in text and "## Skip export" in text, "the skip export lists the audited row")


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

    def no_http(*_a: Any, **_k: Any) -> Any:
        failures.append("apply HTTP was reached")
        raise AssertionError("apply HTTP reached in an offline check")

    saved = {
        (apply, "_api"): apply._api, (apply, "create_item"): apply.create_item,
        (positions, "load_qids"): positions.load_qids,
        (positions, "fill_diplomatic"): positions.fill_diplomatic,
        (reconcile, "retrievable"): reconcile.retrievable, (reconcile, "reopen"): reconcile.reopen,
        (propose, "propose_person"): propose.propose_person,
    }
    apply._api = no_http
    shadow(conn)
    try:
        for name, check in (
            ("crash", check_crash), ("lock", check_lock), ("resend", check_resend), ("refusals", check_refusals),
            ("feed", check_feed), ("audit", check_audit), ("report", check_report),
        ):
            print(f"{name}:")
            check(expect, conn)
    finally:
        for (module, name), value in saved.items():
            setattr(module, name, value)
        unshadow(conn)
    print(f"{len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
