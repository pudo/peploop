"""Create the office items the mint stage guarded, and feed them back into the run.

The other half of `mint`: that module decides which offices may be created and
leaves each one `guarded` with the exact item it would create, `found` with
the item that already exists, or `skipped` under a rule. This one creates the
guarded ones as a QuickStatements 3.0 batch (`send.create`), resolves a
creation a crash interrupted, and then makes every created or found item
reachable: loaded into the position table, its attested mentions re-asked, and
their people proposed again.

A creation is the one write peploop cannot take back by editing, so it is made
crash-safe by recording the intent before the request: a row left in
`creating` is resolved from the send ledger and QS3's own record of the batch,
never simply retried.
"""

import datetime
import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field, fields
from typing import Any, Callable, Sequence

from psycopg.rows import dict_row

from peploop import db, llm, offices, positions, propose, qs, reconcile, send, wikidata

#: What a recheck returns: every reason not to create, empty when clean.
Recheck = Callable[[dict[str, Any]], list[str]]
#: What a lookup returns: the item the office would duplicate, or None.
Lookup = Callable[[dict[str, Any]], str | None]

#: Statuses `feed` reads: an item exists for the candidate.
FEEDABLE = ("created", "found")
#: Statuses an audit may not skip: an item was, or is being, made from the row.
UNSKIPPABLE = ("created", "creating", "loaded")

#: The rule a created row carries, so a `loaded` row still says it was made here.
CREATED = "mint:created"
RECOVERED = "mint:recovered"

#: The send ledger's tool name for creations.
TOOL = "peploop"
#: A creation QS3 reports failed, and no live search finds: QS3 gives no reason,
#: so the row is closed rather than sent again on every run.
CREATE_FAILED = "qs3:create-failed"

USAGE_KEYS = ("input_tokens", "output_tokens", "cache_read_input_tokens",
              "cache_creation_input_tokens")


def _row(cand_id: int, lock: bool = False) -> dict[str, Any] | None:
    sql = "SELECT * FROM office_candidate WHERE id = %s" + (" FOR UPDATE" if lock else "")
    with db.conn().cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, (cand_id,)).fetchone()


def intent_tag(cand: dict[str, Any], at: datetime.datetime | None = None) -> str:
    """The creation's key in the send ledger, unique to this row, payload and attempt.

    The attempt is in it because a row put back to `guarded` after a crash is a
    new creation.
    """
    blob = json.dumps(cand["data"], sort_keys=True, ensure_ascii=False)
    sha = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:8]
    stamp = (at or datetime.datetime.now(datetime.timezone.utc)).strftime("%Y%m%d%H%M%S%f")
    return f"peploop-mint:{cand['country']}:{cand['ref']}:{sha}:{stamp}"


def _label(cand: dict[str, Any]) -> str:
    labels = ((cand.get("data") or {}).get("labels") or {})
    if "en" in labels:
        return labels["en"]["value"]
    for term in labels.values():
        return term["value"]
    spec_label = (cand.get("spec") or {}).get("labels", {}).get("en")
    if spec_label:
        return spec_label
    if cand.get("qid"):
        # A found row was never drafted into a spec: name the item it found.
        row = db.conn().execute("SELECT label FROM position WHERE qid = %s", (cand["qid"],)).fetchone()
        if row and row[0]:
            return row[0]
    return cand["ref"]


def _spec(cand: dict[str, Any]) -> offices.Spec | None:
    raw = cand.get("spec") or {}
    known = {f.name for f in fields(offices.Spec)}
    try:
        return offices.Spec(**{k: v for k, v in raw.items() if k in known})
    except TypeError:
        return None


def live_duplicate(cand: dict[str, Any]) -> str | None:
    """Search Wikidata live, per label and alias, for the item this office would be."""
    spec = _spec(cand)
    if spec is None:
        return None
    texts = [(lang, text) for lang, text in spec.labels.items()]
    texts += [(lang, text) for lang, many in spec.aliases.items() for text in many]
    for lang, text in texts:
        dup = offices.duplicate_of(offices.live_lookup(text, lang, spec.state_qid))
        if dup:
            return dup
    return None


def _settle_refusal(cand_id: int, reasons: Sequence[str]) -> str | None:
    """Close a row the live re-check refused: `found` on a duplicate, else `skipped`."""
    dup = next((r.split("/", 1)[1] for r in reasons if r.startswith("duplicate/")), None)
    if dup:
        db.conn().execute(
            "UPDATE office_candidate SET status = 'found', qid = %s, rule = 'guard:duplicate',"
            " problems = %s, updated_at = now() WHERE id = %s", (dup, list(reasons), cand_id))
        return dup
    db.conn().execute(
        "UPDATE office_candidate SET status = 'skipped', rule = %s, problems = %s,"
        " updated_at = now() WHERE id = %s", (f"guard:{reasons[0]}", list(reasons), cand_id))
    return None


def prepare(cand_id: int, *, recheck: Recheck) -> dict[str, Any] | None:
    """Lock and re-check one guarded office, and record the intent to create it.

    Returns the row, now `creating` with its intent tag and committed, or None
    if nothing is to be sent: a row not `guarded`, one that already has a QID
    (which is what makes a second call a no-op), or one the live re-check
    refuses -- `found` on a duplicate, `skipped` otherwise.
    """
    conn = db.conn()
    with conn.transaction():
        cand = _row(cand_id, lock=True)
        if cand is None or cand["status"] != "guarded" or cand["qid"] is not None:
            return None
        reasons = recheck(cand)
        if reasons:
            _settle_refusal(cand_id, reasons)
            return None
        tag = intent_tag(cand)
        conn.execute(
            "UPDATE office_candidate SET status = 'creating', intent_at = now(),"
            " intent_tag = %s, updated_at = now() WHERE id = %s", (tag, cand_id))
    return {**cand, "intent_tag": tag}


def _created(cand_id: int, qid: str, rule: str) -> None:
    db.conn().execute(
        "UPDATE office_candidate SET status = 'created', qid = %s, rule = %s, updated_at = now()"
        " WHERE id = %s AND status = 'creating'", (qid, rule, cand_id))


def _not_created(cand: dict[str, Any], lookup: Lookup, failed: bool) -> tuple[str, str | None]:
    """Settle a creation that made no item: `found` if a live search finds it, else back or closed.

    A creation that never went out is put back to `guarded`, from where the
    next run sends it once; one QS3 tried and failed is `skipped`.
    """
    dup = lookup(cand)
    if dup:
        db.conn().execute(
            "UPDATE office_candidate SET status = 'found', qid = %s, rule = 'guard:duplicate',"
            " updated_at = now() WHERE id = %s AND status = 'creating'", (dup, cand["id"]))
        return "found", dup
    if failed:
        db.conn().execute(
            "UPDATE office_candidate SET status = 'skipped', rule = %s, updated_at = now()"
            " WHERE id = %s AND status = 'creating'", (CREATE_FAILED, cand["id"]))
        return "skipped", None
    db.conn().execute(
        "UPDATE office_candidate SET status = 'guarded', intent_at = NULL, intent_tag = NULL,"
        " batch = NULL, updated_at = now() WHERE id = %s AND status = 'creating'", (cand["id"],))
    return "guarded", None


def create(
    country: str,
    limit: int | None = None,
    *,
    recheck: Recheck,
    lookup: Lookup = live_duplicate,
    log: Callable[[str], None] = lambda _m: None,
) -> list[tuple[int, str, str | None]]:
    """Create every guarded office of a run as one QS3 batch; returns (id, outcome, qid).

    Run it under `send.writer_lock`, after `recover`. Each row is re-checked
    live and marked `creating` before anything is sent; a row whose item cannot
    be written as QS lines is `skipped` as unrenderable.
    """
    rows: list[tuple[str, str, list[str], int]] = []
    cands: dict[str, dict[str, Any]] = {}
    for cand in guarded(country, limit):
        if qs.create_lines(cand["data"], "") is None:
            _settle_refusal(cand["id"], [qs.UNRENDERABLE])
            continue
        ready = prepare(cand["id"], recheck=recheck)
        if ready is None:
            continue
        lines = qs.create_lines(ready["data"], qs.describe(TOOL, ["CREATE"]))
        rows.append((country, ready["intent_tag"], lines or [], ready["id"]))
        cands[ready["intent_tag"]] = ready
    if not rows:
        return []

    def mark(name: str) -> None:
        db.conn().execute("UPDATE office_candidate SET batch = %s WHERE id = ANY(%s)",
                          (name, [ref for *_, ref in rows]))

    made = send.create(TOOL, rows, log, on_recorded=mark)
    return [_settle(cands[tag], qid, lookup) for tag, qid in made.items()]


def submit(
    country: str,
    limit: int | None = None,
    *,
    recheck: Recheck,
    lookup: Lookup = live_duplicate,
    username: str = "",
    log: Callable[[str], None] = lambda _m: None,
) -> tuple[Counter[str], "FeedStats"]:
    """Create exactly the offices the last dry run guarded, then feed what was made.

    What `mint --submit` runs. It decides nothing: categorize and verify are
    the dry run's, and a re-run of them here could guard an office nobody was
    shown. Each guarded row is still re-checked live before it is sent.
    Returns the outcomes counted and the feed's stats.
    """
    counts: Counter[str] = Counter()
    with send.writer_lock(f"peploop mint {country}"):
        send.recover(TOOL, username, log)
        for _cid, outcome, _qid in recover(country, lookup=lookup, log=log):
            counts[f"recovered:{outcome}"] += 1
        for cid, outcome, qid in create(country, limit, recheck=recheck, lookup=lookup, log=log):
            counts[outcome] += 1
            log(f"#{cid} -> {qid or '-'} {outcome}")
    return counts, feed(country, log=log)


def _settle(cand: dict[str, Any], qid: str | None, lookup: Lookup, rule: str = CREATED) -> tuple[int, str, str | None]:
    if qid:
        _created(cand["id"], qid, rule)
        return cand["id"], "created", qid
    outcome, found = _not_created(cand, lookup, failed=True)
    return cand["id"], outcome, found


def recover(
    country: str,
    *,
    lookup: Lookup = live_duplicate,
    log: Callable[[str], None] = lambda _m: None,
) -> list[tuple[int, str, str | None]]:
    """Resolve every row a crash left in `creating`; returns (id, outcome, qid).

    QS3's record of the batch is asked first, because it is authoritative: a
    `CREATE` that returned a QID is recorded as created, one that failed is
    settled like any failed creation. A row whose batch never reached QS3 --
    `send.recover` binds one whose answer was lost, so run that first -- is
    put back: a live search that finds the office makes it `found`, and a clean
    one returns it to `guarded`, from where the next `create` sends it once.
    Run it under `send.writer_lock`.
    """
    with db.conn().cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            "SELECT * FROM office_candidate WHERE country = %s AND status = 'creating'"
            " ORDER BY id", (country,)).fetchall()
    out: list[tuple[int, str, str | None]] = []
    for cand in rows:
        where = send.created_in(cand["intent_tag"]) if cand["intent_tag"] else None
        if where is not None and where[1] is not None:
            qid = send.creations(where[0]).get(cand["intent_tag"])
            result = _settle(cand, qid, lookup, RECOVERED)
        else:
            outcome, found = _not_created(cand, lookup, failed=False)
            result = (cand["id"], outcome, found)
        out.append(result)
        log(f"#{cand['id']} {cand['ref']}: {result[1]} {result[2] or ''}".rstrip())
    return out


# --- feed --------------------------------------------------------------------


@dataclass
class FeedStats:
    """What one `feed` did, for the run's closing line."""

    loaded: int = 0
    retrieved: Counter[bool] = field(default_factory=Counter)
    reopened: Counter[str] = field(default_factory=Counter)
    proposed: int = 0
    failed: list[str] = field(default_factory=list)

    def line(self) -> str:
        kinds = " ".join(f"{k}={n}" for k, n in sorted(self.reopened.items())) or "-"
        return (f"{self.loaded} candidates loaded; retrieved true={self.retrieved[True]}"
                f" false={self.retrieved[False]}; reopened {kinds};"
                f" {self.proposed} people proposed"
                + (f"; {len(self.failed)} failed" if self.failed else ""))


def _mention(extraction_id: int, mention_idx: int) -> reconcile.Mention | None:
    row = db.conn().execute(
        "SELECT response_json -> 'positions' -> %s FROM extraction WHERE id = %s",
        (mention_idx, extraction_id)).fetchone()
    if row is None or not row[0]:
        return None
    return reconcile.mention_from(row[0])


def _reopened_id(extraction_id: int, mention_idx: int, qid: str) -> int | None:
    row = db.conn().execute(
        "SELECT id FROM resolution WHERE extraction_id = %s AND mention_idx = %s"
        " AND reopened_for = %s ORDER BY id DESC LIMIT 1",
        (extraction_id, mention_idx, qid)).fetchone()
    return row[0] if row else None


def feed_one(cand: dict[str, Any], stats: FeedStats, log: Callable[[str], None]) -> None:
    """Make one created or found item reachable, and re-ask the mentions it is for.

    Only the mentions the candidate was clustered from are reopened, and only
    those whose shortlist would now offer the item: one the search cannot
    surface would buy the same refusal again. An attestation keeps what was
    decided (`retrieved`, `reopened_id`), so a rerun skips what is done.
    """
    qid, cid = cand["qid"], cand["id"]
    state = positions.country_qid(cand["country"])
    source = positions.MINTED if (cand["rule"] or "").startswith("mint:") else "found"
    positions.load_qids([qid], source=source)
    # Holder counts are left null, so the fresh item reads uncounted, not unheld.
    positions.fill_diplomatic([qid])
    with db.conn().cursor(row_factory=dict_row) as cur:
        atts = cur.execute(
            "SELECT * FROM office_attestation WHERE candidate_id = %s"
            " ORDER BY extraction_id, mention_idx", (cid,)).fetchall()
    people: list[str] = []
    for att in atts:
        eid, idx = att["extraction_id"], att["mention_idx"]
        mention = _mention(eid, idx)
        if mention is None:
            continue
        retrieved = att["retrieved"]
        if retrieved is None:
            retrieved = reconcile.retrievable(mention, state, qid)
            db.conn().execute(
                "UPDATE office_attestation SET retrieved = %s WHERE candidate_id = %s"
                " AND extraction_id = %s AND mention_idx = %s", (retrieved, cid, eid, idx))
        stats.retrieved[bool(retrieved)] += 1
        if not retrieved or att["reopened_id"] is not None:
            continue
        verdict, _sent = reconcile.reopen(eid, idx, mention, state, qid)
        stats.reopened[verdict.kind] += 1
        db.conn().execute(
            "UPDATE office_attestation SET reopened_id = %s WHERE candidate_id = %s"
            " AND extraction_id = %s AND mention_idx = %s",
            (_reopened_id(eid, idx, qid), cid, eid, idx))
        if att["person_qid"] not in people:
            people.append(att["person_qid"])
    for person in people:
        try:
            propose.propose_person(person)
            stats.proposed += 1
        except Exception as exc:  # noqa: BLE001 — one person is a line, not a dead feed
            db.set_person_status(person, "failed", f"{type(exc).__name__}: {exc}")
            stats.failed.append(f"{person}: {type(exc).__name__}: {exc}")
            log(f"  {person} propose failed: {type(exc).__name__}: {exc}")
    db.conn().execute(
        "UPDATE office_candidate SET status = 'loaded', updated_at = now()"
        " WHERE id = %s AND status = ANY(%s)", (cid, list(FEEDABLE)))
    stats.loaded += 1
    log(f"#{cid} {cand['ref']} -> {qid}: {len(atts)} attestations, {len(people)} people re-proposed")


def feed(
    country: str,
    cand_ids: Sequence[int] | None = None,
    log: Callable[[str], None] = lambda _m: None,
) -> FeedStats:
    """Feed every created or found candidate not yet loaded, or just the named ones.

    Idempotent: a fed candidate is `loaded` and is not selected again, and a
    feed interrupted halfway resumes from what its attestations recorded.
    """
    with db.conn().cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            "SELECT * FROM office_candidate WHERE country = %s AND status = ANY(%s)"
            " AND qid IS NOT NULL AND (%s::bigint[] IS NULL OR id = ANY(%s)) ORDER BY id",
            (country, list(FEEDABLE), list(cand_ids) if cand_ids else None,
             list(cand_ids) if cand_ids else None)).fetchall()
    stats = FeedStats()
    for cand in rows:
        feed_one(cand, stats, log)
    return stats


# --- audit -------------------------------------------------------------------


def audit(ids: Sequence[int], reason: str, by: str, country: str) -> list[dict[str, Any]]:
    """Skip candidates after the fact, as a human auditing a run.

    There is no approve: an audit can only take a row out. A row an item was
    made from is refused, because skipping it would hide a creation rather
    than undo it; that takes a deletion or a merge on Wikidata. All or
    nothing, like the proposal audit: an unknown id, another country's row or
    an unskippable one refuses the whole call.
    """
    if not by.strip() or not reason.strip():
        raise ValueError("an audit names who skipped it and why")
    conn = db.conn()
    with conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            "SELECT * FROM office_candidate WHERE id = ANY(%s) ORDER BY id FOR UPDATE",
            (list(ids),)).fetchall()
        found = {row["id"] for row in rows}
        problems = [f"#{ident}: no such candidate" for ident in ids if ident not in found]
        problems += [f"#{row['id']}: of {row['country']}'s run, not {country}'s"
                     for row in rows if row["country"] != country]
        problems += [f"#{row['id']} is {row['status']}: an item exists or is being made"
                     for row in rows if row["status"] in UNSKIPPABLE]
        if problems:
            raise ValueError("; ".join(problems))
        for row in rows:
            cur.execute(
                "UPDATE office_candidate SET status = 'skipped', rule = %s,"
                " problems = array_append(problems, %s), decided_by = %s, decided_at = now(),"
                " updated_at = now() WHERE id = %s",
                (f"audit:{by}", f"audit: {reason}", by, row["id"]))
    return rows


# --- report ------------------------------------------------------------------


def _labels_text(cand: dict[str, Any]) -> str:
    labels = ((cand.get("spec") or {}).get("labels")
              or (cand.get("draft") or {}).get("labels") or {})
    return "; ".join(f"{lang}: {text}" for lang, text in sorted(labels.items())) or "-"


def _cell(text: Any) -> str:
    return str(text if text is not None else "-").replace("|", "\\|").replace("\n", " ")


def report(country: str) -> str:
    """The mint stage's state for one country, as markdown.

    The funnel first, because it is the number the run is judged by; then what
    exists or will, the skip export list a human audits from, the groups no
    office took, and what each pass cost.
    """
    conn = db.conn()
    with conn.cursor(row_factory=dict_row) as cur:
        cands = cur.execute(
            "SELECT * FROM office_candidate WHERE country = %s ORDER BY id", (country,)).fetchall()
    out = [f"# Mint report: {country}", ""]
    out += ["## Funnel", "", "| status | rule | n |", "|---|---|---|"]
    funnel = Counter((c["status"], c["rule"] or "") for c in cands)
    for (status, rule), n in sorted(funnel.items(), key=lambda kv: (kv[0][0], -kv[1], kv[0][1])):
        out.append(f"| {status} | {_cell(rule or '-')} | {n} |")
    out.append(f"| **total** | | {len(cands)} |")

    def section(title: str, rows: list[dict[str, Any]], qid: bool = True) -> None:
        out.extend(["", f"## {title} ({len(rows)})", ""])
        if not rows:
            out.append("(none)")
            return
        out.extend(["| id | ref | qid | label | rule |", "|---|---|---|---|---|"])
        for c in rows:
            out.append(f"| {c['id']} | {_cell(c['ref'])} | {_cell(c['qid'] if qid else '')}"
                       f" | {_cell(_label(c))} | {_cell(c['rule'])} |")

    made = lambda c: (c["rule"] or "").startswith("mint:")  # noqa: E731
    section("Guarded", [c for c in cands if c["status"] in ("guarded", "creating")], qid=False)
    section("Created", [c for c in cands if c["status"] == "created"
                        or (c["status"] == "loaded" and made(c))])
    section("Found", [c for c in cands if c["status"] == "found"
                      or (c["status"] == "loaded" and not made(c))])

    skips = [c for c in cands if c["status"] == "skipped"]
    out.extend(["", f"## Skip export ({len(skips)})", ""])
    if skips:
        out.extend(["| id | ref | rule | holders | current | labels |", "|---|---|---|---|---|---|"])
        for c in sorted(skips, key=lambda c: (c["rule"] or "", c["ref"])):
            out.append(f"| {c['id']} | {_cell(c['ref'])} | {_cell(c['rule'])} | {_cell(c['holders'])}"
                       f" | {_cell(c['current_holders'])} | {_cell(_labels_text(c))} |")
    else:
        out.append("(none)")

    unassigned = conn.execute(
        "SELECT coalesce(reason, '-'), count(*) FROM office_unassigned WHERE country = %s"
        " GROUP BY 1 ORDER BY 2 DESC, 1", (country,)).fetchall()
    total = sum(n for _r, n in unassigned)
    out.extend(["", f"## Unassigned groups ({total})", ""])
    if unassigned:
        out.extend(["| reason | n |", "|---|---|"])
        out.extend(f"| {_cell(reason)} | {n} |" for reason, n in unassigned)
    else:
        out.append("(none)")

    usage_rows = conn.execute(
        "SELECT pass, model, usage_json FROM mint_call WHERE country = %s ORDER BY id",
        (country,)).fetchall()
    qids = [c["qid"] for c in cands if c["qid"]]
    if qids:
        usage_rows += [("reopen", m, u) for m, u in conn.execute(
            "SELECT model, usage_json FROM resolution WHERE reopened_for = ANY(%s)", (qids,))]
    tally: dict[tuple[str, str], Counter[str]] = {}
    calls: Counter[tuple[str, str]] = Counter()
    for pass_, model, usage in usage_rows:
        key = (pass_, model)
        calls[key] += 1
        tally.setdefault(key, Counter()).update(
            {k: int((usage or {}).get(k) or 0) for k in USAGE_KEYS})
    out.extend(["", "## Cost", ""])
    if tally:
        out.extend(["| pass | model | calls | input | output | cache read | cache write | $ |",
                    "|---|---|---|---|---|---|---|---|"])
        dollars = 0.0
        for (pass_, model), use in sorted(tally.items()):
            price = llm.cost(model, use)
            dollars += price or 0.0
            out.append(f"| {pass_} | {model} | {calls[(pass_, model)]} | {use['input_tokens']}"
                       f" | {use['output_tokens']} | {use['cache_read_input_tokens']}"
                       f" | {use['cache_creation_input_tokens']}"
                       f" | {'-' if price is None else f'{price:.2f}'} |")
        out.append(f"| **total** | | {sum(calls.values())} | | | | | {dollars:.2f} |")
    else:
        out.append("(no calls)")
    return "\n".join(out) + "\n"


def guarded(country: str, limit: int | None = None) -> list[dict[str, Any]]:
    """The rows `mint` would send, oldest first."""
    with db.conn().cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "SELECT * FROM office_candidate WHERE country = %s AND status = 'guarded'"
            " AND qid IS NULL ORDER BY id LIMIT %s",
            (country, limit)).fetchall()


def labels_of(cand: dict[str, Any]) -> dict[str, str]:
    """Resolved labels for every QID a payload names, for the dry-run display."""
    qids = [c["mainsnak"]["datavalue"]["value"]["id"]
            for c in (cand.get("data") or {}).get("claims", [])
            if c.get("mainsnak", {}).get("datavalue")]
    found = wikidata.fetch_items(sorted(set(qids)), props="labels") if qids else {}
    return {q: wikidata.best_label(e) or "?" for q, e in found.items()}
