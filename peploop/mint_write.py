"""Create the office items the mint stage guarded, and feed them back into the run.

The other half of `mint`: that module decides which offices may be created and
leaves each one `guarded` with the exact `wbeditentity` payload, `found` with
the item that already exists, or `skipped` under a rule. This one sends the
guarded payloads, resolves a creation a crash interrupted, and then makes every
created or found item reachable: loaded into the position table, its attested
mentions re-asked, and their people proposed again.

A creation is the one write peploop cannot take back by editing, so it is made
crash-safe by recording the intent before the call: a row left in `creating` is
resolved by the tag its edit summary carries, never simply retried.
"""

import datetime
import hashlib
import json
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field, fields
from typing import Any, Callable, Iterator, Sequence

from psycopg.rows import dict_row

from peploop import apply, db, offices, positions, propose, reconcile, wikidata

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

#: `find_created` is read from a little before the intent, so clock skew between
#: the database and Wikidata cannot put the edit before the window opens.
INTENT_SLACK = datetime.timedelta(minutes=5)

#: List prices per million tokens: input, output, cache read, cache write. A
#: model not listed is reported in tokens only, never priced by a guess.
PRICES: dict[str, tuple[float, float, float, float]] = {
    "claude-sonnet-5": (2.0, 10.0, 0.20, 2.50),
    "claude-sonnet-5-5": (2.0, 10.0, 0.20, 2.50),
    "claude-opus-5": (5.0, 25.0, 0.50, 6.25),
    "claude-opus-5-5": (4.0, 20.0, 0.20, 5.00),
}
USAGE_KEYS = ("input_tokens", "output_tokens", "cache_read_input_tokens",
              "cache_creation_input_tokens")


def _row(cand_id: int, lock: bool = False) -> dict[str, Any] | None:
    sql = "SELECT * FROM office_candidate WHERE id = %s" + (" FOR UPDATE" if lock else "")
    with db.conn().cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, (cand_id,)).fetchone()


def intent_tag(cand: dict[str, Any]) -> str:
    """The marker a creation's summary carries, unique to this row and payload."""
    blob = json.dumps(cand["data"], sort_keys=True, ensure_ascii=False)
    sha = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:8]
    return f"peploop-mint:{cand['country']}:{cand['ref']}:{sha}"


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


def fallback_recheck(cand: dict[str, Any]) -> list[str]:
    """The live re-check when `mint.reguard` is not there: the duplicate search alone."""
    dup = live_duplicate(cand)
    return [f"duplicate/{dup}"] if dup else []


def default_recheck() -> Recheck:
    """`mint.reguard` if the verify half exposes it, else the duplicate search."""
    from peploop import mint

    return getattr(mint, "reguard", None) or fallback_recheck


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


def mint_one(cand_id: int, token: str, *, recheck: Recheck) -> str | None:
    """Create one guarded office and return its QID, or None if nothing was sent.

    The row is locked and re-checked live, then marked `creating` with its
    intent tag and committed *before* the API call, so a crash at any later
    point leaves a row `recover` can resolve by the tag. A row not `guarded`,
    or one that already has a QID, is left alone, which is what makes a second
    call a no-op. A label conflict is the duplicate the search missed, and is
    recorded as `found`; any other API error leaves the row `creating` and
    propagates.
    """
    conn = db.conn()
    with conn.transaction():
        cand = _row(cand_id, lock=True)
        if cand is None or cand["status"] != "guarded" or cand["qid"] is not None:
            return None
        reasons = recheck(cand)
        if reasons:
            return _settle_refusal(cand_id, reasons)
        tag = intent_tag(cand)
        conn.execute(
            "UPDATE office_candidate SET status = 'creating', intent_at = now(),"
            " intent_tag = %s, batch = %s, updated_at = now() WHERE id = %s",
            (tag, apply.BATCH_ID, cand_id))
    summary = f"Create office: {_label(cand)} [{tag}]"
    try:
        qid, rev = apply.create_item(cand["data"], summary, token)
    except apply.LabelConflict as exc:
        conn.execute(
            "UPDATE office_candidate SET status = 'found', qid = %s, rule = 'api:label-conflict',"
            " updated_at = now() WHERE id = %s AND status = 'creating'", (exc.qid, cand_id))
        return exc.qid
    conn.execute(
        "UPDATE office_candidate SET status = 'created', qid = %s, created_rev = %s,"
        " rule = %s, updated_at = now() WHERE id = %s AND status = 'creating'",
        (qid, rev, CREATED, cand_id))
    return qid


@contextmanager
def writer_lock(country: str) -> Iterator[None]:
    """Hold the one-writer-per-country lock for the length of a write run.

    `recover` treats every `creating` row as interrupted, which is only true
    when no other process is in the middle of a creation: a second writer would
    otherwise reset a row whose edit is still in flight and send it twice.
    """
    conn = db.conn()
    key = f"peploop-mint:{country}"
    got = conn.execute("SELECT pg_try_advisory_lock(hashtext(%s))", (key,)).fetchone()[0]
    if not got:
        raise RuntimeError(f"another mint writer holds the lock for {country}")
    try:
        yield
    finally:
        conn.execute("SELECT pg_advisory_unlock(hashtext(%s))", (key,))


def recover(
    country: str,
    *,
    find: Callable[[str, datetime.datetime], str | None] | None = None,
    lookup: Lookup = live_duplicate,
    log: Callable[[str], None] = lambda _m: None,
) -> list[tuple[int, str, str | None]]:
    """Resolve every row a crash left in `creating`; returns (id, outcome, qid).

    The edit log is asked first, because it is authoritative the moment an edit
    lands: a creation carrying the row's tag is recorded as created. Only when
    it shows none is the row put back: a live search that finds the office
    makes it `found`, and a clean one returns it to `guarded`, from where the
    next `mint_one` sends it once. Run it under `writer_lock`.
    """
    find = find or (lambda tag, since: apply.find_created(tag, since))
    with db.conn().cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            "SELECT * FROM office_candidate WHERE country = %s AND status = 'creating'"
            " ORDER BY id", (country,)).fetchall()
    out: list[tuple[int, str, str | None]] = []
    for cand in rows:
        since = (cand["intent_at"] or datetime.datetime.now(datetime.timezone.utc)) - INTENT_SLACK
        qid = find(cand["intent_tag"], since) if cand["intent_tag"] else None
        if qid:
            db.conn().execute(
                "UPDATE office_candidate SET status = 'created', qid = %s, rule = %s,"
                " updated_at = now() WHERE id = %s AND status = 'creating'",
                (qid, RECOVERED, cand["id"]))
            out.append((cand["id"], "created", qid))
            log(f"#{cand['id']} {cand['ref']}: recovered {qid} from the edit log")
            continue
        dup = lookup(cand)
        if dup:
            db.conn().execute(
                "UPDATE office_candidate SET status = 'found', qid = %s, rule = 'guard:duplicate',"
                " updated_at = now() WHERE id = %s AND status = 'creating'", (dup, cand["id"]))
            out.append((cand["id"], "found", dup))
            log(f"#{cand['id']} {cand['ref']}: not created; {dup} exists")
            continue
        db.conn().execute(
            "UPDATE office_candidate SET status = 'guarded', intent_at = NULL, intent_tag = NULL,"
            " batch = NULL, updated_at = now() WHERE id = %s AND status = 'creating'", (cand["id"],))
        out.append((cand["id"], "guarded", None))
        log(f"#{cand['id']} {cand['ref']}: not created; back to guarded")
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


def audit_skip(cand_id: int, reason: str, by: str) -> dict[str, Any]:
    """Skip a candidate after the fact, as a human auditing a run.

    There is no approve: an audit can only take a row out. A row an item was
    made from is refused, because skipping it would hide a creation rather
    than undo it; that takes a deletion or a merge on Wikidata.
    """
    if not by.strip() or not reason.strip():
        raise ValueError("an audit names who skipped it and why")
    conn = db.conn()
    with conn.transaction():
        cand = _row(cand_id, lock=True)
        if cand is None:
            raise LookupError(f"no candidate #{cand_id}")
        if cand["status"] in UNSKIPPABLE:
            raise ValueError(f"#{cand_id} is {cand['status']}: an item exists or is being made")
        conn.execute(
            "UPDATE office_candidate SET status = 'skipped', rule = %s,"
            " problems = array_append(problems, %s), decided_by = %s, decided_at = now(),"
            " updated_at = now() WHERE id = %s",
            (f"audit:{by}", f"audit: {reason}", by, cand_id))
    return cand


# --- report ------------------------------------------------------------------


def cost(model: str, usage: dict[str, int]) -> float | None:
    """Dollars for one usage tally at list price, or None for an unpriced model."""
    price = PRICES.get(model)
    if price is None:
        return None
    p_in, p_out, p_read, p_write = price
    return (usage.get("input_tokens", 0) * p_in + usage.get("output_tokens", 0) * p_out
            + usage.get("cache_read_input_tokens", 0) * p_read
            + usage.get("cache_creation_input_tokens", 0) * p_write) / 1e6


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
            price = cost(model, use)
            dollars += price or 0.0
            out.append(f"| {pass_} | {model} | {calls[(pass_, model)]} | {use['input_tokens']}"
                       f" | {use['output_tokens']} | {use['cache_read_input_tokens']}"
                       f" | {use['cache_creation_input_tokens']}"
                       f" | {'-' if price is None else f'{price:.2f}'} |")
        out.append(f"| **total** | | {sum(calls.values())} | | | | | {dollars:.2f} |")
    else:
        out.append("(no calls)")
    return "\n".join(out) + "\n"


def guarded(country: str, ids: Sequence[int] = (), limit: int | None = None) -> list[dict[str, Any]]:
    """The rows `mint` would send, oldest first."""
    with db.conn().cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "SELECT * FROM office_candidate WHERE country = %s AND status = 'guarded'"
            " AND qid IS NULL AND (%s::bigint[] IS NULL OR id = ANY(%s)) ORDER BY id LIMIT %s",
            (country, list(ids) or None, list(ids) or None, limit)).fetchall()


def labels_of(cand: dict[str, Any]) -> dict[str, str]:
    """Resolved labels for every QID a payload names, for the dry-run display."""
    qids = [c["mainsnak"]["datavalue"]["value"]["id"]
            for c in (cand.get("data") or {}).get("claims", [])
            if c.get("mainsnak", {}).get("datavalue")]
    found = wikidata.fetch_items(sorted(set(qids)), props="labels") if qids else {}
    return {q: wikidata.best_label(e) or "?" for q, e in found.items()}
