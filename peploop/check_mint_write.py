"""Pin the write half of minting: crash safety, recovery, feeding, and the audit.

A creation cannot be undone by an edit, so every transition around it is pinned
here offline: one batch for every guarded office, each QID read back from its
`CREATE` command, a crash before the request and one after it, a creation QS3
reports failed, a re-check that refuses, a second call on a done row, a feed
run twice, and an audit that tries to skip a created row. Every case runs
against temporary tables shadowing the real ones -- the send ledger among them
-- and QuickStatements is a fake that fails the check if anything else reaches
it, so nothing is read from or written to Wikidata.

Run it as `python -m peploop.check_mint_write` from the repository root.
"""

import sys
from typing import Any, Callable

import psycopg
from click.testing import CliRunner
from psycopg.types.json import Jsonb

from peploop import cli, db, mint, mint_write, positions, propose, qs3, reconcile, send

TABLES = ("office_candidate", "office_attestation", "mint_call", "office_unassigned",
          "resolution", "extraction", "wd_batch", "wd_edit", "wd_strike", "wd_removal")
SEQUENCES = ("office_candidate", "mint_call", "resolution", "extraction", "wd_batch")
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


def check_lock(expect: Any, conn: psycopg.Connection) -> None:
    """One sender at a time, whichever tool or country: a lost batch is only lost with one sender."""
    def try_lock(key: str) -> bool:
        other = psycopg.connect(db.DATABASE_URL, autocommit=True)
        try:
            return other.execute("SELECT pg_try_advisory_lock(hashtext(%s))", (key,)).fetchone()[0]
        finally:
            other.close()

    with send.writer_lock("peploop mint zz"):
        taken = try_lock(send.LOCK)
    expect(not taken, "a second sender is refused the send lock while a mint holds it")
    expect(try_lock(send.LOCK), "and gets it once the mint is done")


class FakeQS3:
    """QuickStatements 3.0 as far as minting uses it: batches by id, a QID per CREATE.

    `fail` names refs whose CREATE fails; `crash` is "before" (the request
    never arrives), "after" (it arrives, the answer is lost) or None.
    """

    def __init__(self) -> None:
        self.batches: dict[int, tuple[str, list[str]]] = {}
        self.next_qid = 7001
        self.fail: set[str] = set()
        self.crash: str | None = None
        self.combined: dict[int, bool] = {}

    def submit(self, lines: list[str], name: str, combine: bool = True) -> int:
        if self.crash == "before":
            raise Crash()
        qs_id = 90000 + len(self.batches)
        self.batches[qs_id] = (name, list(lines))
        self.combined[qs_id] = combine
        if self.crash == "after":
            raise Crash()
        return qs_id

    def wait(self, batch: int, log: Any = None, every: float = 0) -> dict[str, Any]:
        return {"status": {"code": qs3.DONE, "display": "Done"}}

    def commands(self, batch: int) -> list[dict[str, Any]]:
        out, current = [], None
        for i, line in enumerate(self.batches[batch][1]):
            if line.startswith("CREATE"):
                failed = any(f in line for f in self.fail)
                current = None if failed else f"Q{self.next_qid}"
                if current:
                    self.next_qid += 1
                out.append({"index": i, "status": qs3.ERROR if failed else qs3.COMMAND_DONE,
                            "response_id": current})
            else:
                out.append({"index": i, "status": qs3.COMMAND_DONE if current else qs3.ERROR,
                            "response_id": current})
        return out

    def find(self, name: str, username: str, pages: int = 3) -> int | None:
        return next((i for i, (n, _) in self.batches.items() if n == name), None)


FAKE = FakeQS3()


def check_create(expect: Any, conn: psycopg.Connection) -> None:
    """Every guarded office goes out in one batch, and each QID is read off its own CREATE."""
    first, second = candidate(conn, "create-one"), candidate(conn, "create-two")
    out = mint_write.create(COUNTRY, recheck=clean, lookup=lambda _c: None)
    expect(len(FAKE.batches) == 1, "one QS3 batch for every guarded office")
    lines = next(iter(FAKE.batches.values()))[1]
    expect(not any(FAKE.combined.values()), "creations go out uncombined")
    expect(lines[0].startswith("CREATE /* Create office: Mayor of Velmora [peploop-mint:zz:create-one:")
           and lines[1].startswith('LAST\tLen\t"Mayor of Velmora"'),
           "an item is CREATE and its LAST lines, the intent tag in the summary")
    expect(sorted(out) == [(first, "created", "Q7001"), (second, "created", "Q7002")]
           and state(conn, first) == ("created", "Q7001", "mint:created"),
           "each row takes the QID its own CREATE returned")
    batch = conn.execute("SELECT batch FROM office_candidate WHERE id = %s", (first,)).fetchone()[0]
    edits = conn.execute("SELECT status, refs FROM wd_edit WHERE op = 'create' ORDER BY refs[1]").fetchall()
    expect(batch.startswith("peploop mint zz") and edits == [("landed", [first]), ("landed", [second])],
           "the batch is named on the row and both creations are landed in the send ledger")
    expect(mint_write.create(COUNTRY, recheck=clean) == [] and len(FAKE.batches) == 1,
           "a second create sends nothing: no row is guarded")


def check_submit(expect: Any, conn: psycopg.Connection) -> None:
    """Submit creates what the dry run guarded and decides nothing: no categorize, no verify."""
    def no_model(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("submit decided again")

    saved = mint.categorize, mint.verify, mint.reguard
    mint.categorize, mint.verify, mint.reguard = no_model, no_model, clean
    positions.load_qids = lambda qids, source="minted", log=None: {}
    positions.fill_diplomatic = lambda qids=None, log=None: 0
    try:
        guarded = candidate(conn, "submit-guarded")
        skipped = candidate(conn, "submit-skipped", status="skipped", rule="verify:unclear")
        sent = len(FAKE.batches)
        res = CliRunner().invoke(cli.mint_, ["--country", COUNTRY, "--submit"])
        expect(res.exit_code == 0 and len(FAKE.batches) == sent + 1
               and state(conn, guarded)[0] == "loaded" and state(conn, skipped)[0] == "skipped",
               f"--submit creates the guarded row only, without deciding ({res.output.strip()[-200:]})")
        counts, _fed = mint_write.submit(COUNTRY, recheck=clean, lookup=lambda _c: None)
        expect(not counts and len(FAKE.batches) == sent + 1, "a second submit creates nothing")
    finally:
        mint.categorize, mint.verify, mint.reguard = saved


def check_crash(expect: Any, conn: psycopg.Connection) -> None:
    """A lost answer is found by the batch's name and its creations read back, not resent."""
    cid = candidate(conn, "crash-after-submit")
    FAKE.crash = "after"
    try:
        mint_write.create(COUNTRY, recheck=clean)
    except Crash:
        pass
    FAKE.crash = None
    status, qid, _rule = state(conn, cid)
    tag = conn.execute("SELECT intent_tag FROM office_candidate WHERE id = %s", (cid,)).fetchone()[0]
    expect(status == "creating" and qid is None and tag.startswith(f"peploop-mint:{COUNTRY}:crash-after-submit:"),
           "a crash after the request leaves the row creating, tagged, without a QID")
    sent = len(FAKE.batches)
    send.recover(mint_write.TOOL, "someone", lambda _m: None)
    out = mint_write.recover(COUNTRY, lookup=lambda _c: None)
    expect(len(out) == 1 and out[0][1] == "created" and state(conn, cid)[2] == "mint:recovered"
           and len(FAKE.batches) == sent,
           "recover binds the batch by name and reads the QID back; nothing is sent again")


def check_resend(expect: Any, conn: psycopg.Connection) -> None:
    """A creation that never reached QS3 goes back to guarded and is sent exactly once."""
    cid = candidate(conn, "crash-before-submit")
    FAKE.crash = "before"
    try:
        mint_write.create(COUNTRY, recheck=clean)
    except Crash:
        pass
    FAKE.crash = None
    send.recover(mint_write.TOOL, "someone", lambda _m: None)
    out = mint_write.recover(COUNTRY, lookup=lambda _c: None)
    expect(out == [(cid, "guarded", None)] and state(conn, cid)[0] == "guarded",
           "no batch at QS3 and a clean live lookup put the row back to guarded")
    sent = len(FAKE.batches)
    again = mint_write.create(COUNTRY, recheck=clean)
    expect(len(again) == 1 and again[0][1] == "created" and len(FAKE.batches) == sent + 1,
           "the next create sends it once, under a fresh intent tag")
    other = candidate(conn, "crash-dup")
    conn.execute("UPDATE office_candidate SET status = 'creating', intent_tag = 't', intent_at = now()"
                 " WHERE id = %s", (other,))
    mint_write.recover(COUNTRY, lookup=lambda _c: "Q7003")
    expect(state(conn, other) == ("found", "Q7003", "guard:duplicate"),
           "no batch and a live duplicate make the interrupted row found")


def check_refusals(expect: Any, conn: psycopg.Connection) -> None:
    """A failed CREATE is found or closed; a refusing re-check skips; nothing else is sent."""
    failing = candidate(conn, "fails-at-qs3")
    FAKE.fail = {"fails-at-qs3"}
    out = mint_write.create(COUNTRY, recheck=clean, lookup=lambda _c: None)
    expect(out == [(failing, "skipped", None)] and state(conn, failing)[2] == mint_write.CREATE_FAILED,
           "a CREATE QS3 reports failed, with nothing found live, is closed rather than resent")
    found = candidate(conn, "fails-but-exists")
    FAKE.fail = {"fails-but-exists"}
    mint_write.create(COUNTRY, recheck=clean, lookup=lambda _c: "Q7010")
    expect(state(conn, found) == ("found", "Q7010", "guard:duplicate"),
           "a failed CREATE whose office a live search finds is recorded as found")
    FAKE.fail = set()
    sent = len(FAKE.batches)
    refused = candidate(conn, "refused")
    mint_write.create(COUNTRY, recheck=lambda _c: ["body-word/Q5", "holders/1"])
    expect(state(conn, refused) == ("skipped", None, "guard:body-word/Q5") and len(FAKE.batches) == sent,
           "a re-check that refuses skips under guard:<reason> and sends nothing")
    dup = candidate(conn, "refused-dup")
    mint_write.create(COUNTRY, recheck=lambda _c: ["duplicate/Q7011"])
    expect(state(conn, dup) == ("found", "Q7011", "guard:duplicate") and len(FAKE.batches) == sent,
           "a re-check that finds a duplicate records it as found")
    quoted = candidate(conn, "quoted", data=Jsonb({**DATA, "labels": {"en": {"language": "en", "value": 'A "b"'}}}))
    mint_write.create(COUNTRY, recheck=clean)
    expect(state(conn, quoted)[0] == "skipped" and len(FAKE.batches) == sent,
           "an item QS lines cannot carry is skipped, not sent")
    skipped = candidate(conn, "not-guarded", status="skipped", rule="disagree/x")
    mint_write.create(COUNTRY, recheck=clean)
    expect(state(conn, skipped)[0] == "skipped" and len(FAKE.batches) == sent, "a row not guarded is never sent")


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
    open_ = candidate(conn, "audit-guarded")
    args = ["--country", COUNTRY, "--reason", "a party post", "--by", "fl"]
    res = runner.invoke(cli.audit_, ["candidate", str(made), str(open_), *args])
    expect(res.exit_code != 0 and state(conn, made)[0] == "created"
           and state(conn, open_)[0] == "guarded",
           f"audit refuses a created row, and the guarded one beside it ({res.output.strip()})")
    res = runner.invoke(cli.audit_, ["candidate", str(open_), "--country", "zy",
                                     "--reason", "x", "--by", "fl"])
    expect(res.exit_code != 0 and state(conn, open_)[0] == "guarded",
           "audit refuses a row of another country's run")
    res = runner.invoke(cli.audit_, ["candidate", "--ids", "-", *args], input=f"{open_}  # why\n")
    problems = conn.execute("SELECT problems, decided_by FROM office_candidate WHERE id = %s",
                            (open_,)).fetchone()
    expect(res.exit_code == 0 and state(conn, open_) == ("skipped", None, "audit:fl")
           and problems == (["audit: a party post"], "fl"),
           f"audit skips a guarded row from an id file under audit:<by> ({res.output.strip()})")
    expect(not any(p.name in ("approve", "accept") for p in cli.audit_.params),
           "audit has no approve path")


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

    saved = {
        (qs3, "submit"): qs3.submit, (qs3, "wait"): qs3.wait, (qs3, "commands"): qs3.commands,
        (qs3, "find"): qs3.find, (qs3, "_get"): qs3._get,
        (positions, "load_qids"): positions.load_qids,
        (positions, "fill_diplomatic"): positions.fill_diplomatic,
        (reconcile, "retrievable"): reconcile.retrievable, (reconcile, "reopen"): reconcile.reopen,
        (propose, "propose_person"): propose.propose_person,
    }
    def no_http(*_a: Any, **_k: Any) -> Any:
        failures.append("QS3 was reached")
        raise AssertionError("QS3 reached in an offline check")

    qs3.submit, qs3.wait, qs3.commands, qs3.find = FAKE.submit, FAKE.wait, FAKE.commands, FAKE.find
    qs3._get = no_http
    shadow(conn)
    try:
        for name, check in (
            ("create", check_create), ("submit", check_submit), ("crash", check_crash), ("lock", check_lock), ("resend", check_resend),
            ("refusals", check_refusals),
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
