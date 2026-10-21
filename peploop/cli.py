"""Drive the peploop pipeline from the command line.

Run as `python -m peploop.cli <command>` from the repository root. Every command
is idempotent: seeding twice queues nothing new, fetching twice re-uses the
item and article rows that are still inside their age tolerance.
"""

import json
import os
import time
from collections import Counter
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import click

from peploop import db, ledger, mint, policy, positions, scope, titles, verify as verifying, wikidata, wikipedia
from peploop import extract as extraction
from peploop import mint_write as minting
from peploop import mint_units
from peploop import outbox
from peploop.corp import outbox as corp_outbox
from peploop.corp import regress as corp_regress
from peploop.corp import run as corp_run
from peploop.corp import wd as corp_wd
from peploop.tree import audit as tree_audit
from peploop.tree import outbox as tree_outbox
from peploop.tree import place as tree_place
from peploop.tree import qs as tree_qs
from peploop.tree import sweep as tree_sweep
from peploop.tree import wd as tree_wd
from peploop import qs
from peploop import plan as planning
from peploop import send as sending
from peploop import propose as proposals
from peploop import reconcile as reconciling
from peploop import review as reviewing

ITEM_MAX_AGE = "7 days"
ARTICLE_MAX_AGE = "30 days"
SEED_DIR = Path(__file__).resolve().parent / "seeds"
MINT_REPORT_DIR = Path(__file__).resolve().parent.parent / "data" / "mint"
# How many requests each stage keeps in flight: what every country run has
# passed, now fixed. Each one stage's own, because what bounds it differs --
# Wikimedia's rate limiter for a fetch, the model's latency for the rest.
FETCH_THREADS = 8
EXTRACT_THREADS = 4
RECONCILE_THREADS = 8
VERIFY_THREADS = 4

#: Whose refusals `reconcile`'s retrieval re-ask covers: `all`, or `stranded`
#: -- people with no `P39` on the item and every mention unplaced, whom a
#: placement helps most. An environment switch rather than a flag, because it
#: exists to stage the first, costed run and every later run wants `all`.
REASK_SCOPE = os.environ.get("PEPLOOP_REASK_SCOPE", "all")


def _fetch_items(qids: Sequence[str], force: bool) -> dict[str, dict[str, Any]]:
    """Fetch the items that are missing or past their age tolerance."""
    if not force:
        fresh = {
            row[0]
            for row in db.conn().execute(
                "SELECT qid FROM item WHERE qid = ANY(%s)"
                f" AND fetched_at > now() - interval '{ITEM_MAX_AGE}'",
                (list(qids),),
            )
        }
        qids = [qid for qid in qids if qid not in fresh]
    entities = wikidata.fetch_items(qids)
    for qid, entity in entities.items():
        db.upsert_item(qid, entity.get("lastrevid"), entity)
    return entities


def _stored_items(qids: Sequence[str]) -> dict[str, dict[str, Any]]:
    rows = db.conn().execute("SELECT qid, json FROM item WHERE qid = ANY(%s)", (list(qids),))
    return {qid: entity for qid, entity in rows}


def _fetch_articles(qid: str, entity: dict[str, Any], force: bool) -> int:
    """Fetch every Wikipedia article of one person, returning how many were read."""
    fresh = set()
    if not force:
        fresh = {
            row[0]
            for row in db.conn().execute(
                "SELECT lang FROM article WHERE qid = %s"
                f" AND fetched_at > now() - interval '{ARTICLE_MAX_AGE}'",
                (qid,),
            )
        }
    count = 0
    for lang, title in wikidata.sitelink_articles(entity):
        if lang in fresh:
            continue
        article = wikipedia.fetch_article(lang, title)
        landed = article["redirect"]
        if landed and wikipedia.page_item(lang, landed) != qid:
            click.echo(f"{qid} {lang}:{title} redirects to {landed}, another item; dropped")
            continue
        text = wikipedia.html_to_text(article["html"])
        db.upsert_article(qid, lang, title, article["rev_id"], article["url"], text)
        count += 1
    return count


def _process(qid: str, entity: dict[str, Any], force: bool) -> tuple[str, str]:
    """Enforce the item gates and read the person's articles, returning their status."""
    try:
        if "Q5" not in wikidata.claim_qids(entity, "P31"):
            db.set_person_status(qid, "not_human")
            return qid, "not_human"
        reason = scope.out_of_scope(entity)
        if reason is not None:
            db.set_person_status(qid, "out_of_scope", reason)
            return qid, "out_of_scope"
        _fetch_articles(qid, entity, force)
        db.set_person_status(qid, "fetched")
        return qid, "fetched"
    except Exception as exc:  # noqa: BLE001 — a failed person is a row, not a dead run
        db.set_person_status(qid, "failed", f"{type(exc).__name__}: {exc}")
        return qid, "failed"


@click.group()
def cli() -> None:
    """Fetch Wikidata items and Wikipedia articles for political office-holders."""
    db.init_schema()


# The country a run is scoped to. It reaches the database as `person.country`,
# stamped by `seed`, and scopes a command's *selection* only -- every stage
# still works one person at a time and knows nothing about where they are from.
# Naming people with `--qid` overrides it, because a named person is the answer
# to "this one", not to "the next batch of these".
country_option = click.option(
    "--country", default=None, help="Only people seeded by this ISO code's run."
)


def _select(
    qid: Sequence[str], statuses: tuple[str, ...], country: str | None
) -> list[str]:
    """Pick the people a command works on: the named ones, or all of a run's.

    A stage works through everything its selection returns, so one of the two
    is required: without them a stage would take every country's people.
    """
    if qid:
        return list(qid)
    if not country:
        raise click.UsageError("name the run with --country, or the people with --qid")
    rows = db.conn().execute(
        "SELECT qid FROM person WHERE status = ANY(%s) AND country = %s ORDER BY qid",
        (list(statuses), country),
    )
    return [row[0] for row in rows]


@cli.command()
@click.option("--country", required=True, help="Seed peploop/seeds/<country>.yml under this code.")
def seed(country: str) -> None:
    """Queue the members of every Wikipedia category in the country's seed file.

    The country is what every later command's `--country` selects on. Someone
    two runs both find keeps the first one's stamp, so re-seeding a country
    never moves people out of another.
    """
    path = SEED_DIR / f"{country}.yml"
    if not path.exists():
        raise click.UsageError(f"no seed file at {path}")
    entries = wikipedia.load_seeds(path)
    members_total, new_total, failed = 0, 0, 0
    for entry in entries:
        head = f"{entry.lang}:{entry.category} " + ("links" if entry.article else f"depth {entry.depth}")
        try:
            if entry.article:
                members = wikipedia.seed_article(entry.category, entry.lang)
            else:
                members = wikipedia.seed_category(entry.category, entry.lang, entry.depth)
        except RuntimeError as exc:
            # One category PetScan cannot serve is a line of output, not the
            # end of the file: the rest of the seed is independent of it.
            failed += 1
            click.echo(f"{head}: {exc}", err=True)
            continue
        added = 0
        for _, qid in members:
            added += db.upsert_person(qid, country)
            db.upsert_membership(qid, entry.category, entry.lang)
        members_total += len(members)
        new_total += added
        click.echo(f"{head}: {len(members)} members with a QID, {added} new people")
    click.echo(
        f"{len(entries)} categories ({failed} failed): "
        f"{members_total} memberships, {new_total} new people"
    )


@cli.command()
@click.option("--qid", multiple=True, help="Process these people, ignoring the item age.")
@country_option
def fetch(qid: Sequence[str], country: str | None) -> None:
    """Fetch the item and every Wikipedia article of queued people."""
    qids = _select(qid, ("queued",), country)
    if not qids:
        click.echo("nothing queued")
        return
    force = bool(qid)
    with ThreadPoolExecutor(max_workers=FETCH_THREADS) as pool:
        chunks = [qids[i : i + 50] for i in range(0, len(qids), 50)]
        entities: dict[str, dict[str, Any]] = {}
        for result in pool.map(lambda c: _fetch_items(c, force), chunks):
            entities.update(result)
        entities.update({k: v for k, v in _stored_items(qids).items() if k not in entities})
        missing = [q for q in qids if q not in entities]
        for absent in missing:
            db.set_person_status(absent, "failed", "item missing or deleted")
        counts: dict[str, int] = {"failed": len(missing)} if missing else {}
        work = [(q, entities[q]) for q in qids if q in entities]
        for _, status in pool.map(lambda item: _process(item[0], item[1], force), work):
            counts[status] = counts.get(status, 0) + 1
    click.echo(f"{len(qids)} people: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))


def _extract_one(qid: str) -> tuple[str, str]:
    """Extract one person, reporting the new status and a printable line."""
    try:
        row = extraction.extract_person(qid)
    except Exception as exc:  # noqa: BLE001 — a failed person is a row, not a dead run
        db.set_person_status(qid, "failed", f"{type(exc).__name__}: {exc}")
        return "failed", f"{qid} failed: {type(exc).__name__}: {exc}"
    head = f"{row.qid} {(row.label or '?')[:28]:28s} arts={row.articles}"
    reason = _extracted_out_of_scope(qid)
    if reason is not None:
        db.set_person_status(qid, "out_of_scope", reason)
        return "out_of_scope", f"{head} out of scope: {reason}"
    db.set_person_status(qid, "extracted")
    if row.skipped:
        return "extracted", f"{head} skipped (already extracted from these revisions)"
    dropped = ",".join(row.dropped) or "-"
    return "extracted", (
        f"{head} dropped={dropped} in={row.input_tokens} cache_w={row.cache_creation}"
        f" cache_r={row.cache_read} out={row.output_tokens} bad_quotes={row.bad_quotes}"
        f" positions={row.positions} {row.seconds:.1f}s"
    )


def _extracted_out_of_scope(qid: str) -> str | None:
    """Apply the relevance gate a second time, to the dates the articles gave.

    The item gate ran before any article was read and kept everyone whose item
    carries no date; the extraction is the first thing that says when such a
    person lived. A person set aside here is never reconciled or proposed.
    """
    row = db.conn().execute(
        "SELECT response_json FROM extraction WHERE qid = %s ORDER BY id DESC LIMIT 1", (qid,)
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return scope.out_of_scope_extracted(row[0])


def _propose_one(qid: str) -> tuple[str, str]:
    """Propose one person's extraction, reporting the new status and a line."""
    try:
        summary = proposals.propose_person(qid)
    except Exception as exc:  # noqa: BLE001 — a failed person is a row, not a dead run
        db.set_person_status(qid, "failed", f"{type(exc).__name__}: {exc}")
        return "failed", f"{qid} failed: {type(exc).__name__}: {exc}"
    counts = " ".join(
        f"{prop}:{status}={n}" for (prop, status), n in sorted(summary.counts.items())
    )
    return summary.person_status, (
        f"{summary.qid} {(summary.label or '?')[:28]:28s} {summary.person_status}"
        f" {summary.written} proposals kept={summary.kept}"
        f" positions={summary.positions} places={summary.birth_places} {counts}"
    )


@cli.command()
@click.option("--qid", multiple=True, help="Extract these people instead of the whole run.")
@country_option
def extract(qid: Sequence[str], country: str | None) -> None:
    """Ask the model about fetched people and store the structured answer.

    A person already extracted under this prompt and these article revisions
    is skipped without a request, so re-running costs only what is new.
    """
    qids = _select(qid, ("fetched", "extracted"), country)
    if not qids:
        click.echo("nothing fetched")
        return
    with ThreadPoolExecutor(max_workers=EXTRACT_THREADS) as pool:
        for _, line in pool.map(_extract_one, qids):
            click.echo(line)


@cli.command()
@click.option("--qid", multiple=True, help="Propose for these people instead of the whole run.")
@country_option
def propose(qid: Sequence[str], country: str | None) -> None:
    """Turn each extracted person's answer into proposals, then decide every one by rule.

    The decision is the policy: accepted, skipped, or pending the verifier. It
    reads each person's `new` and `refine` rows -- and whatever it decided last
    time, so a rule change is one re-run -- and never a row a human ruled on or
    that went out. It is local and re-derived on every run, so it is part of
    proposing rather than a stage of its own; the report ends with the funnel,
    per property, of which rule took each row. `report --country <cc> funnel`
    shows the same without writing.
    """
    qids = _select(qid, ("extracted", "proposed"), country)
    if not qids:
        click.echo("nothing extracted")
        return
    for person_qid in qids:
        click.echo(_propose_one(person_qid)[1])
    if country:
        _echo_property_counts(country)
    for line in _funnel(_select(qid, ("proposed",), country), write=True):
        click.echo(line)


def _echo_property_counts(country: str) -> None:
    """Print how many proposals of each property carry each status, terms folded."""
    click.echo("proposals by property and status:")
    counts: Counter[tuple[str, str]] = Counter()
    for prop, status, count in db.conn().execute(
        "SELECT p.property, p.status, count(*) FROM proposal p"
        " JOIN person pe ON pe.qid = p.person_qid WHERE pe.country = %s"
        " GROUP BY p.property, p.status",
        (country,),
    ):
        counts[(prop, status)] += count
    for (prop, status), count in sorted(counts.items()):
        click.echo(f"  {prop:12s} {status:11s} {count}")


@cli.command()
@click.option("--limit", default=20, show_default=True, help="How many people to draw.")
@click.option("--qid", multiple=True, help="Review these people instead of a random draw.")
@country_option
def review(limit: int, qid: Sequence[str], country: str | None) -> None:
    """Sample people's proposals in a terminal UI, recording a verdict on each.

    A sampler, not a gate: the verdicts measure the pipeline and change no
    status. The policy's next run skips a row rejected here; an accept decides
    nothing. One person per screen, drawn at random from those with something
    left to review; each person's decisions are written in one transaction
    when the screen is submitted.
    """
    qids = reviewing.select_people(list(qid), limit, country)
    if not qids:
        click.echo("nothing to review")
        return
    app = reviewing.ReviewApp(qids)
    app.run()
    click.echo(
        f"{app.written} verdicts written over {len(qids)} people"
        f" ({app.skipped} skipped)"
    )
    for line in reviewing.summary_lines():
        click.echo(line)


@cli.command("send")
@click.option("--country", help="The run to send.")
@click.option("--qid", multiple=True, help="Send these people only.")
@click.option("--submit", is_flag=True, help="Send it as a QuickStatements 3.0 batch; without it nothing leaves here.")
@click.option("--status", "show_status", is_flag=True, help="Print the send ledger: batches, failures, strikes, removals.")
@click.option("--retry", is_flag=True, help="With --submit: send the run's failed lines again, one edit each.")
def send_(country: str | None, qid: Sequence[str], submit: bool, show_status: bool, retry: bool) -> None:
    """Send a run's accepted proposals to Wikidata, then its approved removals, and settle every row.

    A dry run by default: it settles what went out before, pre-flights and
    plans every person with accepted rows against their live item, and writes
    the lines to `data/peploop/send/<cc>.qs` with the routes counted. `--submit`
    closes the rows the plan writes nothing for, sends the lines as one QS3
    batch and the approved removals as another, waits, and records each row
    `applied` or `failed`. With `mint --submit`, one of the two commands that
    edit Wikidata.
    """
    if show_status:
        click.echo(sending.status(outbox.TOOL))
        return
    if not country:
        raise click.UsageError("name the run with --country")
    if retry:
        if not submit:
            raise click.UsageError("--retry sends; pass --submit with it")
        found = outbox.retry(country, click.echo)
        click.echo(f"QS3 batch {found}" if found else "nothing sent")
        return
    sent = outbox.run(country, click.echo, submit=submit, qids=list(qid), threads=FETCH_THREADS)
    click.echo(f"QS3 batches {' '.join(map(str, sent))}" if sent else "nothing sent")


@cli.command("removals")
@click.argument("action", type=click.Choice(["list", "approve", "reject"]), default="list")
@click.argument("guids", nargs=-1)
@click.option("--tool", type=click.Choice([outbox.TOOL, tree_outbox.TOOL, corp_outbox.TOOL]),
              help="List one tool's removals only.")
def removals_(action: str, guids: Sequence[str], tool: str | None) -> None:
    """List statements to take back off Wikidata, or approve/reject them: `removals [approve|reject GUID…]`.

    One queue for both tools. An audit of an applied peploop row, or a peptree
    strike of a landed line, queues its removal: approved when the statement is
    provably only ours, proposed for a human otherwise. Approved ones go out
    with that tool's next `send --submit`.
    """
    if action == "list":
        click.echo(sending.removals_listing(tool))
        return
    if not guids:
        raise click.UsageError(f"{action} needs statement GUIDs")
    n = ledger.decide(guids, "approved" if action == "approve" else "rejected")
    click.echo(f"{n} of {len(guids)} {action}d (only proposed removals change)")


@cli.command("generic")
@click.argument("action", type=click.Choice(["list", "strike"]), default="list")
@click.argument("qid", required=False)
@click.option("--reason", help="Why the struck item is not generic after all.")
def generic_(action: str, qid: str | None, reason: str | None) -> None:
    """List the roles a model judged generic, or strike one it got wrong: `generic [strike QID --reason …]`.

    A listed role is no `P39` target, no shortlist row and gets no country from
    peptree, so a false one silently costs statements; striking it restores it
    and keeps any later run from listing it again.
    """
    con = db.conn()
    if action == "list":
        for row in con.execute("SELECT qid, label, country, source, evidence, struck FROM generic_position"
                               " ORDER BY struck IS NOT NULL, country, qid").fetchall():
            q, label, cc, source, evidence, struck = row
            click.echo(f"{q}\t{label or ''}\t{cc or ''}\t{source or ''}: {evidence or ''}"
                       + (f"\tSTRUCK: {struck}" if struck else ""))
        return
    if not qid or not reason:
        raise click.UsageError("strike needs a QID and --reason")
    n = con.execute("UPDATE generic_position SET struck = %s WHERE qid = %s", (reason, qid)).rowcount
    if not n:
        raise click.UsageError(f"{qid} is not a model-judged generic role (the measured CSV is edited by hand)")
    positions.generic_labels.cache_clear()
    positions.mark_generic(log=click.echo)
    click.echo(f"struck {qid}")


#: The model stages `prompt` can show a request for.
PROMPT_STAGES = ("extract", "verify", "mint-categorize", "mint-verify")


@cli.command("prompt")
@click.argument("stage", type=click.Choice(PROMPT_STAGES))
@click.option("--qid", multiple=True, help="The person to show (extract, verify).")
@country_option
def prompt_(stage: str, qid: Sequence[str], country: str | None) -> None:
    """Print what a model stage would be shown, and send nothing.

    How a prompt or rendering change is judged before it is run over a
    country: `extract` and `verify` take people, the mint passes a country
    and print their first request with the count still to ask.
    """
    if stage in ("extract", "verify") and not qid:
        raise click.UsageError(f"{stage} shows people: pass --qid")
    if stage.startswith("mint-") and not country:
        raise click.UsageError(f"{stage} works a country: pass --country")
    if stage == "extract":
        for person_qid in qid:
            entity, articles, dropped = extraction.stored_articles(person_qid)
            click.echo(f"===== {person_qid} ({len(articles)} articles,"
                       f" dropped {','.join(dropped) or '-'}) =====")
            click.echo(extraction.user_message(entity, articles))
    elif stage == "verify":
        for person_qid in qid:
            for row in verifying.pending_rows(person_qid):
                click.echo(f"===== proposal {row['id']} =====")
                click.echo(verifying.render_edit(verifying.edit_for(row)))
    elif stage == "mint-categorize":
        mint.categorize(country, dry_run=True, log=click.echo)
    else:
        mint.verify(country, dry_run=True, log=click.echo)


def _funnel(people: Sequence[str], write: bool) -> list[str]:
    """Run the policy over these people and return its funnel as report lines."""
    if not people:
        return ["nobody proposed"]
    funnel = policy.run(people, write=write)
    labels = policy.office_labels(list(funnel.offices))
    verb = "decided" if write else "as the rules would decide them now"
    return policy.report_lines(funnel, labels) + [f"{len(people)} people, {verb}"]


def _pending_people(qid: Sequence[str], country: str | None) -> list[str]:
    """The people with a proposal the policy has held for the verifier."""
    if qid:
        return list(qid)
    if not country:
        raise click.UsageError("name the run with --country, or the people with --qid")
    rows = db.conn().execute(
        "SELECT DISTINCT p.person_qid FROM proposal p JOIN person pe ON pe.qid = p.person_qid"
        " WHERE p.status = 'pending' AND pe.country = %s ORDER BY p.person_qid",
        (country,),
    )
    return [row[0] for row in rows]


@cli.command("verify")
@click.option("--qid", multiple=True, help="Verify these people instead of the whole run.")
@country_option
def verify_(qid: Sequence[str], country: str | None) -> None:
    """Ask a second model about every proposal the policy holds as `pending`, then decide.

    One request per proposal against the frozen `prompts/verify.md`, shown the
    edit as it would land beside the article and the item's own claims. A
    verdict is stored by the content it was about, so a re-run asks only what
    is new; once a person's rows are answered the policy is run over them
    again, and each row leaves as `accepted` or `skipped`. It starts with the
    policy, so rows `propose` just made are decided and only those that need the
    model are asked, and it ends with the policy over the whole run and its
    funnel.
    """
    run = _select(qid, ("proposed",), country)
    policy.run(run, write=True)
    people = _pending_people(qid, country)
    if people:
        _verify_people(people)
    else:
        click.echo("nothing pending")
    for line in _funnel(run, write=True):
        click.echo(line)


def _verify_people(people: Sequence[str]) -> None:
    """Verify every pending row of these people, re-deciding each person after."""

    def one(person_qid: str) -> tuple[list[str], Counter[str]]:
        """Verify one person's pending rows, then re-decide them.

        A row the model fails on is a line of output and stays `pending`, so
        the next pass asks again; the person's other rows are still decided.
        """
        lines: list[str] = []
        counts: Counter[str] = Counter()
        for row in verifying.pending_rows(person_qid):
            head = f"{person_qid} #{row['id']} {row['property']}"
            try:
                verification, sent = verifying.verify_proposal(row)
            except Exception as exc:  # noqa: BLE001 — one bad answer is a line, not a dead run
                lines.append(f"{head} failed: {type(exc).__name__}: {str(exc)[:90]}")
                counts["failed"] += 1
                continue
            counts["sent" if sent else "cached"] += 1
            counts[verification.verdict] += 1
            lines.append(
                f"{head} -> {verification.verdict}/{verification.confidence}"
                f" {'(sent)' if sent else '(cached)'} {verification.reason[:80]}"
            )
        funnel = policy.run([person_qid], write=True)
        for (_group, rule), n in funnel.decided.items():
            counts[f"policy:{rule}"] += n
        return lines, counts

    totals: Counter[str] = Counter()
    with ThreadPoolExecutor(max_workers=VERIFY_THREADS) as pool:
        for lines, counts in pool.map(one, people):
            for line in lines:
                click.echo(line)
            totals.update(counts)
    click.echo(f"{len(people)} people: " + ", ".join(f"{k}={v}" for k, v in sorted(totals.items())))


def _mentions_for(country: str) -> list[tuple[int, int, Any]]:
    """List the office mentions still unanswered under the current prompt.

    One row per (extraction, mention index). The extraction chosen per person
    is the newest, because an older one was answered about articles that have
    since been re-read. The ledger, not this query, is what makes the pass
    resumable -- `resolve_mention` returns a recorded verdict without asking --
    but skipping the answered ones here makes the count printed the new work.
    """
    _text, prompt_hash = reconciling.system_prompt()
    rows = db.conn().execute(
        "SELECT e.id, e.response_json->'positions' FROM ("
        "  SELECT DISTINCT ON (qid) id, qid, response_json FROM extraction"
        "  WHERE response_json IS NOT NULL ORDER BY qid, id DESC"
        ") e JOIN person pe ON pe.qid = e.qid"
        " WHERE pe.country = %s AND pe.status <> 'out_of_scope' ORDER BY e.id",
        (country,),
    )
    answered = {
        (row[0], row[1])
        for row in db.conn().execute(
            "SELECT extraction_id, mention_idx FROM resolution"
            " WHERE prompt_hash = %s AND render_version = %s",
            (prompt_hash, reconciling.RENDER_VERSION),
        )
    }
    work: list[tuple[int, int, Any]] = []
    for extraction_id, mentions in rows:
        for index, entry in enumerate(mentions or []):
            if (extraction_id, index) in answered:
                continue
            work.append((extraction_id, index, reconciling.mention_from(entry)))
    return work


@cli.command()
@click.option("--country", required=True, help="The run whose mentions to resolve.")
def reconcile(country: str) -> None:
    """Resolve each extracted office mention to a position item, or refuse.

    One request per mention against the frozen `prompts/reconcile.md`, never a
    batch: several offices in one context is how a pass standardises on
    whatever it answered first. The country names whose holder counts rank the
    shortlist; it is not a filter, and an office of another state stays
    reachable and is tagged as one.

    A mention already answered under this prompt and rendering is skipped
    without a request, so a re-run costs only what is new. First every
    mention's title gets its cached English name, the second search channel
    the shortlist reads; a title already cached is never asked again. Last,
    every refusal whose shortlist now offers an item it did not is asked once
    more, because a retrieval change alters no key the ledger reads.

    Before any of it, the positions' ranking signals are filled (`_signals`):
    they read the item table, which only `fetch` fills, and they count only
    what has no count yet, so on a re-run they cost nothing.
    """
    state_qid = positions.country_qid(country)
    _signals(state_qid)
    _translate_titles(state_qid, country)
    work = _mentions_for(country)
    if work:
        _resolve_all(work, state_qid)
    else:
        click.echo("nothing new to reconcile")
    _reask_gained(country, state_qid)


def _resolve_all(
    work: Sequence[tuple[int, int, Any]], state_qid: str, reopened_for: str = ""
) -> None:
    """Resolve each mention at the stage's concurrency, printing a line and a tally."""
    def one(item: tuple[int, int, Any]) -> tuple[str, tuple[str, ...]]:
        """Resolve one mention, returning its line and what it counts towards.

        The tally is returned rather than incremented: `counts[k] += 1` from a
        pool is a read-modify-write on shared state, and a lost count in a
        summary is the kind of wrong number nothing later contradicts.

        A mention the model fails on is a line of output, not the end of the
        run: a response that degenerates until `max_tokens` comes back as
        truncated JSON and the structured-output parser raises. The verdict is
        simply not recorded, so the next pass asks again.
        """
        extraction_id, index, mention = item
        try:
            verdict, sent = reconciling.resolve_mention(
                extraction_id, index, mention, state_qid, reopened_for=reopened_for
            )
        except Exception as exc:  # noqa: BLE001 — see above
            return (
                f"{extraction_id}#{index} {mention.title[:44]!r} failed:"
                f" {type(exc).__name__}: {str(exc).splitlines()[0][:90]}",
                ("failed",),
            )
        target = verdict.qid or verdict.chosen or "-"
        line = (
            f"{extraction_id}#{index} {mention.title[:44]!r} -> {target}"
            f" {verdict.kind}/{verdict.confidence}"
            + (f" veto={verdict.veto}" if verdict.veto else "")
        )
        return line, (
            verdict.kind,
            "matched" if verdict.resolved else "unmatched",
            "asked" if sent else "recorded",
        )

    counts: Counter[str] = Counter()
    with ThreadPoolExecutor(max_workers=RECONCILE_THREADS) as pool:
        for line, tally in pool.map(one, work):
            counts.update(tally)
            click.echo(line)
    click.echo(
        f"{len(work)} mentions: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    )


def _reask_gained(country: str, state_qid: str) -> None:
    """Ask each refusal again whose shortlist now offers an item it did not offer.

    Stored under `reconcile.RETRIEVAL_REASK`, so the new verdict sits beside the
    refusal and, being newer, is the one `propose` reads; a mention is re-asked
    once per tag, and one whose list did not change is never sent. The count
    is printed before any request goes out.
    """
    rows = db.conn().execute(
        "SELECT e.id, e.response_json->'positions' FROM ("
        "  SELECT DISTINCT ON (qid) id, qid, response_json FROM extraction"
        "  WHERE response_json IS NOT NULL ORDER BY qid, id DESC"
        ") e JOIN person pe ON pe.qid = e.qid JOIN item i ON i.qid = pe.qid"
        " WHERE pe.country = %s AND pe.status <> 'out_of_scope'"
        + (
            " AND pe.status = 'proposed' AND NOT (i.json->'claims' ? 'P39')"
            " AND NOT EXISTS (SELECT 1 FROM ("
            "  SELECT DISTINCT ON (mention_idx) qid FROM resolution r"
            "  WHERE r.extraction_id = e.id ORDER BY mention_idx, id DESC"
            " ) newest WHERE newest.qid IS NOT NULL)"
            if REASK_SCOPE == "stranded" else ""
        ),
        (country,),
    ).fetchall()
    mentions = {
        (eid, idx): reconciling.mention_from(entry)
        for eid, entries in rows for idx, entry in enumerate(entries or [])
    }
    refused, work = reconciling.reask_work(mentions, state_qid, threads=RECONCILE_THREADS)
    click.echo(
        f"retrieval re-ask ({REASK_SCOPE}): {refused} refusals,"
        f" {len(work)} with a shortlist that gained an item"
    )
    if work:
        _resolve_all(work, state_qid, reopened_for=reconciling.RETRIEVAL_REASK)


def _translate_titles(state_qid: str, country: str) -> None:
    """Cache an English name for every mention title of the run, before it is searched.

    A search aid, so a failed pass is a line of output and the run goes on:
    an uncached title is searched by its own words alone.
    """
    since = db.conn().execute("SELECT now()").fetchone()[0]
    try:
        stats = titles.translate(titles.mention_titles(state_qid, country), log=click.echo)
    except Exception as exc:  # noqa: BLE001 — see above
        click.echo(f"english titles skipped: {type(exc).__name__}: {str(exc)[:120]}")
        return
    if stats["todo"]:
        spent = titles.cost(since=since)
        click.echo(f"english titles: {stats['answered']} of {stats['todo']} answered in"
                   f" {spent['requests']} requests, {spent['input_tokens']} input +"
                   f" {spent['output_tokens']} output tokens")


@cli.command("load-positions")
@click.option("--country", required=True, help="ISO code of the country to load.")
def load_positions(country: str) -> None:
    """Load one country's position items into the reconciliation table, every lane.

    Additive, so it is also the way to add a lane to a country already
    loaded: what the other lanes found is updated in place, not duplicated.
    """
    started = time.monotonic()
    counts = positions.load_country(country, log=click.echo)
    click.echo(
        f"loaded {counts['loaded']} positions, {counts['names']} names"
        f" in {time.monotonic() - started:.0f}s"
    )


def _signals(state_qid: str) -> None:
    """Fill the ranking signals the shortlist reads, for rows that have none yet.

    The whole-corpus counts for rows no load has counted (a newly loaded
    country's own, a minted item), and this state's citizens among the holders
    of rows that have no number for it. A recount of rows already counted is
    `positions.fill_counts` with no `qids`, called by hand.
    """
    uncounted = positions.uncounted()
    if uncounted:
        timings = positions.fill_counts(state_qid, uncounted, log=click.echo)
        click.echo(f"counts for {len(uncounted)} uncounted rows in {sum(timings.values()):.0f}s")
    positions.fill_local_holders(state_qid, only_missing=True, log=click.echo)
    positions.fill_scope_qualifiers(log=click.echo)
    positions.fill_diplomatic(log=click.echo)
    positions.mark_generic(log=click.echo)


# --- report ------------------------------------------------------------------
#
# Every checkpoint's numbers, one section each, all scoped to one run. Reading
# only: `funnel` runs the policy without writing, which still reads offices'
# holders live, the way the policy's own run does.


def _report_people(country: str) -> None:
    """People per status, the seed categories, articles and the extraction's tokens."""
    conn = db.conn()
    scope = " WHERE qid IN (SELECT qid FROM person WHERE country = %s)"
    click.echo("person by status:")
    for status, count in conn.execute(
        "SELECT status, count(*) FROM person WHERE country = %s"
        " GROUP BY status ORDER BY count(*) DESC",
        (country,),
    ):
        click.echo(f"  {status:12s} {count}")
    for table in ("membership", "item", "article"):
        count = conn.execute(f"SELECT count(*) FROM {table}" + scope, (country,)).fetchone()[0]
        click.echo(f"{table:12s} {count}")
    click.echo("seed categories by members (top 10):")
    for lang, category, count in conn.execute(
        "SELECT lang, category, count(*) FROM membership" + scope
        + " GROUP BY lang, category ORDER BY count(*) DESC LIMIT 10",
        (country,),
    ):
        click.echo(f"  {count:6d}  {lang}:{category}")
    extracted, tokens = conn.execute(
        "SELECT count(DISTINCT qid), coalesce(sum((usage_json->>'input_tokens')::bigint"
        " + (usage_json->>'cache_creation_input_tokens')::bigint"
        " + (usage_json->>'cache_read_input_tokens')::bigint"
        " + (usage_json->>'output_tokens')::bigint), 0) FROM extraction" + scope,
        (country,),
    ).fetchone()
    click.echo(f"extracted    {extracted} people, {tokens} tokens")
    click.echo("articles by language (top 15):")
    for lang, count in conn.execute(
        "SELECT lang, count(*) FROM article" + scope
        + " GROUP BY lang ORDER BY count(*) DESC LIMIT 15",
        (country,),
    ):
        click.echo(f"  {lang:8s} {count}")


def _report_positions(country: str) -> None:
    """What the position table holds for the state, per discovery source."""
    where, params = " WHERE country_qid = %s", [positions.country_qid(country)]
    total = db.conn().execute(f"SELECT count(*) FROM position{where}", params).fetchone()[0]
    click.echo(f"positions:        {total}")
    click.echo("by source set:")
    for label, count in db.conn().execute(
        f"SELECT array_to_string(sources, '+'), count(*) FROM position{where}"
        " GROUP BY 1 ORDER BY 2 DESC",
        params,
    ):
        click.echo(f"  {label or '(none)':<24} {count}")
    click.echo("flags:")
    rows = db.conn().execute(
        f"SELECT count(*) FILTER (WHERE not_office),"
        f" count(*) FILTER (WHERE abolished IS NOT NULL),"
        f" count(*) FILTER (WHERE jurisdiction_qid IS NOT NULL),"
        f" count(*) FILTER (WHERE holders_at IS NOT NULL),"
        f" count(*) FILTER (WHERE title_en IS NOT NULL) FROM position{where}",
        params,
    ).fetchone()
    names = ("not_office", "abolished", "has jurisdiction", "holders counted", "english name")
    for name, count in zip(names, rows):
        click.echo(f"  {name:<24} {count}")


def _report_proposals(country: str) -> None:
    """Proposals per property and status, the sampler's verdicts, mint candidates."""
    conn = db.conn()
    proposed, rows = conn.execute(
        "SELECT count(DISTINCT person_qid), count(*) FROM proposal"
        " WHERE person_qid IN (SELECT qid FROM person WHERE country = %s)",
        (country,),
    ).fetchone()
    click.echo(f"proposal     {rows} rows for {proposed} people")
    _echo_property_counts(country)
    for line in reviewing.summary_lines(country):
        click.echo(line)
    click.echo("mint candidates by status:")
    for status, count in conn.execute(
        "SELECT status, count(*) FROM office_candidate WHERE country = %s"
        " GROUP BY status ORDER BY count(*) DESC, status",
        (country,),
    ):
        click.echo(f"  {status:12s} {count}")


def _report_funnel(country: str) -> None:
    """What the rules would decide now, per property and rule, writing nothing."""
    for line in _funnel(_select((), ("proposed",), country), write=False):
        click.echo(line)


def _report_mint(country: str) -> None:
    """The mint funnel by rule, what was created and found, the skips, and the cost."""
    click.echo(minting.report(country), nl=False)


REPORT_SECTIONS = {
    "people": _report_people,
    "positions": _report_positions,
    "proposals": _report_proposals,
    "funnel": _report_funnel,
    "mint": _report_mint,
}


@cli.command("report")
@click.argument("sections", nargs=-1, type=click.Choice(list(REPORT_SECTIONS)))
@click.option("--country", required=True, help="The run to report on.")
def report(sections: Sequence[str], country: str) -> None:
    """Print a run's numbers, every section or the named ones; writes nothing.

    One command for every checkpoint of the runbook: people and tokens after
    extract, positions after the load, proposals and the policy's funnel
    before verify spends, the mint funnel after its verify.
    """
    for name in sections or REPORT_SECTIONS:
        click.echo(f"## {name}")
        REPORT_SECTIONS[name](country)
        click.echo("")


# --- mint --------------------------------------------------------------------
#
# The stage between `reconcile` and `propose` that creates the offices nobody's
# P39 had anywhere to go.


@cli.command("mint")
@click.option("--country", required=True, help="ISO code of the country to mint for.")
@click.option("--limit", default=None, type=int, help="Create at most this many items.")
@click.option("--id", "ids", type=int, multiple=True, help="With --submit, create only these guarded rows.")
@click.option("--submit", is_flag=True, help="Create the items as a QS3 batch; without it nothing leaves here.")
def mint_(country: str, limit: int | None, ids: tuple[int, ...], submit: bool) -> None:
    """Find the offices a country's P39s had nowhere to go, decide each, and create the guarded ones.

    Runs when the reconciler's refusals name offices Wikidata lacks; a run
    with none skips it. Categorize clusters the misses and the census into
    candidate offices, verify asks a second model about each and decides it by
    rule, then the report is written to `data/mint/<cc>.md` and every item the
    decision found already existing is fed into the run. Both model passes are
    ledgered, so a re-run asks only what is new.

    A dry run by default: it ends by printing each guarded office as the QS
    lines that would create it, with the labels of every item it names.
    `--submit` decides nothing: it creates the offices the last dry run
    guarded and printed, each re-checked live, as one QS3 batch, then feeds
    every item made into the position table and the mentions it was attested
    by; `--id` narrows it to named rows, for a sample shown to reviewers first. The holders' P39s go out with the next `send`, after `propose` and
    `verify` have seen the new items.
    """
    if submit:
        if not minting.guarded(country, limit, ids):
            click.echo(f"{country}: 0 guarded: run the dry mint first")
        counts, fed = minting.submit(country, limit, ids=ids or None, recheck=mint.reguard,
                                     username=os.environ.get("QS_USERNAME", ""), log=click.echo)
        click.echo("  " + fed.line())
        click.echo(f"{country}: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
        return
    stats = mint.categorize(country, log=click.echo)
    click.echo("categorize: " + json.dumps({k: v for k, v in stats.items() if k not in ("clusters", "truncated")},
                                           sort_keys=True))
    units = mint_units.build(country, log=click.echo)
    if units:
        click.echo("units: " + json.dumps(dict(sorted(units.items()))))
    stats = mint.verify(country, threads=VERIFY_THREADS, log=click.echo)
    for (status, rule), n in sorted((stats.get("funnel") or {}).items(), key=lambda kv: -kv[1]):
        click.echo(f"{n:5d}  {status:10s} {rule}")
    out = MINT_REPORT_DIR / f"{country}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(minting.report(country))
    click.echo(f"{out} written")
    click.echo(minting.feed(country, log=click.echo).line())
    rows = minting.guarded(country, limit)
    for cand in rows:
        names = minting.labels_of(cand)
        click.echo(f"===== #{cand['id']} {cand['ref']} ({cand['holders']} holders,"
                   f" {cand['current_holders']} current) =====")
        for qid, label in sorted(names.items()):
            click.echo(f"  {qid} = {label}")
        for line in qs.create_lines(cand["data"], "") or ["(cannot be written as QS lines)"]:
            click.echo("  " + line.removesuffix(" /*  */"))
    click.echo(f"{len(rows)} guarded; would create {len(rows)} items (dry run)")


def _read_ids(handle: Any) -> list[int]:
    """The integers in an id file: one or more per line, `#` starting a comment."""
    out = []
    for line in handle:
        for token in line.split("#", 1)[0].replace(",", " ").split():
            try:
                out.append(int(token))
            except ValueError as exc:
                raise click.BadParameter(f"not an id: {token!r}", param_hint="--ids") from exc
    return out


@cli.command("audit")
@click.argument("kind", type=click.Choice(["proposal", "candidate"]))
@click.argument("ids", nargs=-1, type=int)
@click.option("--ids", "ids_file", type=click.File("r"),
              help="Read the ids from this file ('-' for stdin), e.g. an observer's SQL output.")
@click.option("--country", required=True, help="The run the rows belong to; others are refused.")
@click.option("--reason", required=True, help="Why, as the report and the skip export show it.")
@click.option("--by", required=True, help="Who audited; the rows are decided by audit:<by>.")
def audit_(
    kind: str, ids: Sequence[int], ids_file: Any, country: str, reason: str, by: str
) -> None:
    """Take proposals or mint candidates out after the fact. There is no approve.

    The one way to overrule the pipeline by hand, so that no audit is raw SQL
    again: a proposal audit is a `reject` verdict as well as a skip, which a
    re-propose keeps, and a strike, which no later send overrides; on a
    proposal already applied the strike queues the statement's removal. A
    candidate audit is a skip `write_candidates` keeps. All or nothing: a
    proposal in flight, a created item, a row of another country's run or an
    unknown id refuses the call.
    """
    wanted = list(ids) + (_read_ids(ids_file) if ids_file else [])
    if not wanted:
        raise click.UsageError("name the rows: ids as arguments, or --ids FILE")
    wanted = list(dict.fromkeys(wanted))
    auditor = policy.audit if kind == "proposal" else minting.audit
    try:
        rows = auditor(wanted, reason, by, country)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    for row in rows:
        name = row.get("ref") or f"{row.get('person_qid')} {row.get('property')}"
        if row["status"] in policy.LANDED:
            click.echo(f"#{row['id']} {name}: applied, struck; its removal is queued (`removals`)")
        else:
            click.echo(f"#{row['id']} {name}: {row['status']} -> skipped (audit:{by})")
    click.echo(f"{len(rows)} {kind}s skipped")


# --- peptree: repair position items, one place at a time ---------------------------


@cli.group("tree")
def tree() -> None:
    """Give each country's position items the P31, P279, P17 and P1001 they lack."""
    tree_wd.init()


@tree.command("place")
@click.argument("cc")
@click.option("--no-ask", is_flag=True, help="Re-decide from the ledger; no model calls.")
@click.option("--limit", type=int, default=None, help="Ask about the first N items only.")
def tree_place_(cc: str, no_ask: bool, limit: int | None) -> None:
    """Derive a place's country, load its offices, decide their gaps, and write its run file and report."""
    tree_place.run(cc, limit, no_ask)


@tree.command("sweep")
@click.argument("step", type=click.Choice(["plan", "table", "run"]))
@click.argument("batch", type=int, required=False)
def tree_sweep_(step: str, batch: int | None) -> None:
    """Rebuild the sweep's batches (`plan`), refresh its ledger (`table`), or run one batch (`run N`)."""
    if step == "plan":
        click.echo(tree_sweep.plan())
    elif step == "table":
        click.echo(tree_sweep.table())
    else:
        if batch is None:
            raise click.UsageError("sweep run needs a batch number")
        done = tree_sweep.run(batch, log=lambda m: click.echo(m, err=True))
        lines = sum(len(p.read_text().splitlines()) for cc in done if (p := tree_qs.latest(cc)))
        click.echo(f"batch {batch}: ran {' '.join(done) or 'nothing'}, {lines} lines proposed;"
                   " send with `tree send --submit`")


@tree.command("audit")
@click.argument("batch", type=int)
def tree_audit_(batch: int) -> None:
    """Print every line of sweep batch N with labels, and what to look at."""
    text, path = tree_audit.write(batch)
    click.echo(text)
    click.echo(f"\n{path}", err=True)


@tree.command("send")
@click.option("--submit", is_flag=True, help="Send it as a QuickStatements 3.0 batch; without it nothing leaves here.")
@click.option("--batch", type=int, default=None, help="Only the places of this reviewed sweep batch.")
@click.option("--status", "show_status", is_flag=True, help="Print the send ledger: batches, failures, strikes, removals.")
@click.option("--propose-reverts", is_flag=True, help="Queue removals for what landed on items the load now drops.")
def tree_send_(submit: bool, batch: int | None, show_status: bool, propose_reverts: bool) -> None:
    """Send what every reviewed place proposes and has not gone out yet, then the approved removals."""
    log = lambda m: click.echo(m, err=True)  # noqa: E731
    if show_status:
        click.echo(sending.status(tree_outbox.TOOL))
        return
    if propose_reverts:
        tree_outbox.propose_reverts(log)
        return
    sent = tree_outbox.run(log, batch, submit=submit)
    click.echo(f"QS3 batches {' '.join(map(str, sent))}" if sent else f"nothing sent; review {tree_outbox.PENDING}")


@tree.command("strike")
@click.argument("qid")
@click.argument("prop")
@click.argument("value", required=False, default=ledger.ANY)
@click.option("--reason", required=True, help="Why it must never be sent.")
@click.option("--country", default=None, help="The place it belongs to; read from the ledger when omitted.")
def tree_strike_(qid: str, prop: str, value: str, reason: str, country: str | None) -> None:
    """Never send this statement; undo it if it already landed."""
    try:
        click.echo(tree_outbox.strike(qid, prop, value, reason, country, log=lambda m: click.echo(m, err=True)))
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc


# --- pepcorp: state enterprise profiles, one country at a time ----------------------


@cli.group("corp")
def corp() -> None:
    """Give each country's state enterprises their owner, type marker and leadership."""
    corp_wd.init()


@corp.command("run")
@click.argument("cc")
@click.option("--no-ask", is_flag=True, help="Re-decide from the ledger; no model calls, no reload.")
@click.option("--no-reload", is_flag=True, help="Ask about the enterprises the last load kept.")
@click.option("--limit", type=int, default=None, help="Ask about the first N enterprises only.")
@click.option("--qid", "qids", multiple=True, help="Ask about these enterprises only.")
def corp_run_(cc: str, no_ask: bool, no_reload: bool, limit: int | None, qids: Sequence[str]) -> None:
    """Load a country's enterprises, decide them, and write its run file and report."""
    path = corp_run.run(cc, limit, no_ask, reload=not no_reload, only=set(qids) or None,
                        log=lambda m: click.echo(m, err=True))
    click.echo(path)


@corp.command("eval")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def corp_eval_(path: Path) -> None:
    """Ask and check a regression set's bodies and print expected against got; writes no run file."""
    click.echo(corp_regress.table(corp_regress.evaluate(path, log=lambda m: click.echo(m, err=True))))


@corp.command("send")
@click.argument("cc", required=False)
@click.option("--submit", is_flag=True, help="Send it as a QuickStatements 3.0 batch; without it nothing leaves here.")
@click.option("--status", "show_status", is_flag=True, help="Print the send ledger: batches, failures, strikes, removals.")
@click.option("--qid", "qids", multiple=True, help="Only these enterprises' lines.")
def corp_send_(cc: str | None, submit: bool, show_status: bool, qids: Sequence[str]) -> None:
    """Send what a country's latest run proposes and has not gone out yet, then the approved removals."""
    if show_status:
        click.echo(sending.status(corp_outbox.TOOL))
        return
    if cc is None:
        raise click.UsageError("send needs a country")
    sent = corp_outbox.run(cc, lambda m: click.echo(m, err=True), submit=submit, qids=set(qids) or None)
    click.echo(f"QS3 batches {' '.join(map(str, sent))}" if sent else f"nothing sent; review {corp_outbox.PENDING}")


if __name__ == "__main__":
    cli()
