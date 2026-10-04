"""Drive the peploop pipeline from the command line.

Run as `python -m peploop.cli <command>` from the repository root. Every command
is idempotent: seeding twice queues nothing new, fetching twice re-uses the
item and article rows that are still inside their age tolerance.
"""

import contextlib
import json
import time
from collections import Counter
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import click

from peploop import apply as applying
from peploop import db, policy, positions, scope, titles, verify as verifying, wikidata, wikipedia
from peploop import extract as extraction
from peploop import mint_write as minting
from peploop import propose as proposals
from peploop import reconcile as reconciling
from peploop import render as rendering
from peploop import review as reviewing

DUMP_DIR = Path("data/extract")
ITEM_MAX_AGE = "7 days"
ARTICLE_MAX_AGE = "30 days"


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
    qid: Sequence[str], statuses: tuple[str, ...], limit: int, country: str | None = None
) -> list[str]:
    """Pick the people a command works on: the named ones, or the next batch."""
    if qid:
        return list(qid)
    rows = db.conn().execute(
        "SELECT qid FROM person WHERE status = ANY(%s)"
        " AND (%s::text IS NULL OR country = %s) ORDER BY qid LIMIT %s",
        (list(statuses), country, country, limit),
    )
    return [row[0] for row in rows]


@cli.command()
@click.option(
    "--file",
    "path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Seed file of categories, e.g. peploop/seeds/cz.yml.",
)
@click.option("--country", default=None, help="Stamp the people queued with this ISO code.")
def seed(path: Path, country: str | None) -> None:
    """Queue the members of every Wikipedia category in a seed file.

    The country is what every later command's `--country` selects on. Someone
    two runs both find keeps the first one's stamp, so re-seeding a country
    never moves people out of another.
    """
    entries = wikipedia.load_seeds(path)
    members_total, new_total, failed = 0, 0, 0
    for entry in entries:
        head = f"{entry.lang}:{entry.category} depth {entry.depth}"
        try:
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
@click.option("--limit", default=100, show_default=True)
@click.option("--threads", default=8, show_default=True)
@click.option("--qid", multiple=True, help="Process these people, ignoring the item age.")
@country_option
def fetch(limit: int, threads: int, qid: Sequence[str], country: str | None) -> None:
    """Fetch the item and every Wikipedia article of queued people."""
    qids = _select(qid, ("queued",), limit, country)
    if not qids:
        click.echo("nothing queued")
        return
    force = bool(qid)
    with ThreadPoolExecutor(max_workers=threads) as pool:
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


@cli.command()
@click.option("--qid", multiple=True, help="Check these items instead of all known ones.")
@click.option("--articles", is_flag=True, help="Also re-fetch article text.")
def refresh(qid: Sequence[str], articles: bool) -> None:
    """Re-fetch the items whose revision moved, and optionally their articles."""
    if qid:
        qids = list(qid)
    else:
        qids = [row[0] for row in db.conn().execute("SELECT qid FROM item ORDER BY qid")]
    if not qids:
        click.echo("no items known")
        return
    stored = {
        row[0]: row[1]
        for row in db.conn().execute(
            "SELECT qid, lastrevid FROM item WHERE qid = ANY(%s)", (qids,)
        )
    }
    live = wikidata.lastrevids(qids)
    moved = [q for q in qids if q in live and stored.get(q) != live[q]]
    entities = _fetch_items(moved, force=True) if moved else {}
    click.echo(f"{len(qids)} items checked, {len(moved)} moved, {len(entities)} re-fetched")
    if articles:
        known = _stored_items(qids)
        requeued = 0
        for person_qid in qids:
            entity = entities.get(person_qid) or known.get(person_qid)
            if entity is None:
                continue
            if _fetch_articles(person_qid, entity, force=True):
                db.set_person_status(person_qid, "queued")
                requeued += 1
        click.echo(f"{requeued} people re-queued after re-reading their articles")


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
    person lived. A person set aside here is never reconciled or proposed,
    which on the pilot's second country was every mayor of the 1500s.
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
@click.option("--limit", default=10, show_default=True)
@click.option("--threads", default=4, show_default=True)
@click.option("--qid", multiple=True, help="Extract these people instead of a batch.")
@country_option
def extract(limit: int, threads: int, qid: Sequence[str], country: str | None) -> None:
    """Ask the model about fetched people and store the structured answer.

    Selection is stable, so the same `--limit` picks the same people twice: a
    person already extracted under this prompt and these article revisions is
    skipped without a request, and re-running costs nothing.
    """
    qids = _select(qid, ("fetched", "extracted"), limit, country)
    if not qids:
        click.echo("nothing fetched")
        return
    with ThreadPoolExecutor(max_workers=threads) as pool:
        for _, line in pool.map(_extract_one, qids):
            click.echo(line)


@cli.command()
@click.option("--limit", default=100, show_default=True)
@click.option("--qid", multiple=True, help="Propose for these people instead of a batch.")
@country_option
def propose(limit: int, qid: Sequence[str], country: str | None) -> None:
    """Turn each extracted person's answer into proposals, and status them."""
    qids = _select(qid, ("extracted", "proposed"), limit, country)
    if not qids:
        click.echo("nothing extracted")
        return
    for person_qid in qids:
        click.echo(_propose_one(person_qid)[1])
    _echo_property_counts(country)


def _echo_property_counts(country: str | None = None) -> None:
    """Print how many proposals of each property carry each status."""
    click.echo("proposals by property and status:")
    for prop, status, count in db.conn().execute(
        "SELECT p.property, p.status, count(*) FROM proposal p"
        " JOIN person pe ON pe.qid = p.person_qid"
        " WHERE (%s::text IS NULL OR pe.country = %s)"
        " GROUP BY p.property, p.status ORDER BY p.property, p.status",
        (country, country),
    ):
        click.echo(f"  {prop:12s} {status:11s} {count}")


def _run_one(qid: str, entity: dict[str, Any], force: bool) -> tuple[str, str]:
    """Carry one person from item through articles, extraction and proposals."""
    _, status = _process(qid, entity, force)
    if status != "fetched":
        return status, f"{qid} {status}"
    status, line = _extract_one(qid)
    if status != "extracted":
        return status, line
    proposed, tail = _propose_one(qid)
    return proposed, f"{line}\n{tail}"


@cli.command()
@click.option("--limit", default=50, show_default=True)
@click.option("--threads", default=4, show_default=True)
@click.option("--qid", multiple=True, help="Run these people, ignoring the item age.")
@country_option
def run(limit: int, threads: int, qid: Sequence[str], country: str | None) -> None:
    """Fetch, extract and propose in one pass per person."""
    qids = _select(qid, ("queued",), limit, country)
    if not qids:
        click.echo("nothing queued")
        return
    force = bool(qid)
    counts: Counter[str] = Counter()
    with ThreadPoolExecutor(max_workers=threads) as pool:
        chunks = [qids[i : i + 50] for i in range(0, len(qids), 50)]
        entities: dict[str, dict[str, Any]] = {}
        for result in pool.map(lambda c: _fetch_items(c, force), chunks):
            entities.update(result)
        entities.update({k: v for k, v in _stored_items(qids).items() if k not in entities})
        for absent in [q for q in qids if q not in entities]:
            db.set_person_status(absent, "failed", "item missing or deleted")
            counts["failed"] += 1
            click.echo(f"{absent} failed: item missing or deleted")
        work = [(q, entities[q]) for q in qids if q in entities]
        for status, line in pool.map(lambda i: _run_one(i[0], i[1], force), work):
            counts[status] += 1
            click.echo(line)
    click.echo(f"{len(qids)} people: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    _echo_property_counts(country)


@cli.command()
@click.option("--status", default="new,refine", show_default=True)
@click.option("--property", "properties", multiple=True, help="Render only these properties.")
@country_option
def render(status: str, properties: Sequence[str], country: str | None) -> None:
    """Print the selected proposals as QuickStatements v1 lines.

    Nothing is written to Wikidata: the output is a batch a human pastes into
    the QuickStatements importer after reading it.
    """
    statuses = [part.strip() for part in status.split(",") if part.strip()]
    try:
        lines, problems = rendering.render(statuses, list(properties), country)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    if problems:
        for problem in problems[:10]:
            click.echo(problem, err=True)
        raise click.ClickException(f"{len(problems)} problems; nothing rendered")
    for line in lines:
        click.echo(line)
    click.echo(f"{len(lines)} lines", err=True)


@cli.command()
@click.option("--limit", default=20, show_default=True)
@click.option("--qid", multiple=True, help="Review these people instead of a random draw.")
@country_option
def review(limit: int, qid: Sequence[str], country: str | None) -> None:
    """Review people's `new`, `refine` and `conflict` proposals, recording a verdict.

    One person per screen, drawn at random from those with something left to
    review; each person's decisions are written in one transaction when the
    screen is submitted. An accepted conflict is a note that the item is wrong,
    not an edit: `apply` never writes a value contradicting what is recorded.
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


def _apply_pass(
    qids: Sequence[str], token: str | None, write: bool, follow: bool
) -> tuple[int, int, bool]:
    """Write one pass over `qids`: proposals applied, failures, and whether lag stopped it.

    In follow mode a person with nothing left to write prints nothing, because
    a row the router keeps skipping would otherwise be re-announced every pass.
    """
    applied, failed = 0, 0
    for index, person_qid in enumerate(qids):
        if write and index:
            time.sleep(applying.THROTTLE)
        try:
            plan, note = applying.apply_person(person_qid, token, defer_lag=follow)
        except applying.ApiError as exc:
            # The site is lagged, not this person: the next pass comes back.
            if follow and exc.code == "maxlag":
                return applied, failed, True
            failed += 1
            click.echo(f"{person_qid} failed: {type(exc).__name__}: {exc}")
            continue
        except Exception as exc:  # noqa: BLE001 — a refused edit is a row, not a dead run
            failed += 1
            click.echo(f"{person_qid} failed: {type(exc).__name__}: {exc}")
            continue
        if follow and not plan.data:
            continue
        routes = " ".join(f"{route}={n}" for route, n in sorted(plan.routes.items()))
        head = f"{person_qid} [{routes}]{note}"
        click.echo(f"{head}: {plan.summary}" if plan.data else f"{head}: nothing to write")
        for proposal_id, reason in plan.skipped:
            click.echo(f"  skipped proposal {proposal_id}: {reason}")
        if not plan.data:
            continue
        applied += plan.covered
        if not write:
            click.echo(json.dumps(plan.data, indent=2, ensure_ascii=False))
    return applied, failed, False


@cli.command("apply")
@click.option("--limit", default=10, show_default=True)
@click.option("--qid", multiple=True, help="Write these people instead of a batch.")
@click.option("--write", is_flag=True, help="Send the edits; without it nothing leaves here.")
@click.option("--follow", is_flag=True, help="Keep draining what review accepts, until Ctrl-C.")
@country_option
def apply_(
    limit: int, qid: Sequence[str], write: bool, follow: bool, country: str | None
) -> None:
    """Write each person's accepted proposals to Wikidata as one edit.

    A dry run by default: it does the same pre-flight against the live item and
    prints the payload it would send. `--write` logs in and sends, one person
    every ten seconds, and records what came back on each proposal.

    `--follow` turns it into a drainer that selects again every minute instead
    of exiting, so it can run detached beside `review` — `nohup` it the way
    `run` is run — and Ctrl-C ends it with the session's totals. A person the
    lag budget ran out on is left alone and retried next pass.
    """
    if follow and not write:
        raise click.UsageError("--follow writes: pass --write too")
    token = None
    lock = contextlib.nullcontext()
    if write:
        # One drain per country: a second picks the same people, and the API
        # writes their statements twice.
        lock = minting.writer_lock(country or "qids:" + ",".join(sorted(qid)), "apply")
        lock.__enter__()
        click.echo(f"logged in as {applying.login()}")
        token = applying.csrf_token()
    applied, failed, seen, state = 0, 0, 0, ""
    try:
        while True:
            qids = applying.people(list(qid), limit, country)
            if not qids:
                if not follow:
                    click.echo("nothing accepted")
                    return
                state = _note_state(state, "idle", "nothing accepted: waiting")
            else:
                seen += len(qids)
                count, fails, lagged = _apply_pass(qids, token, write, follow)
                applied += count
                failed += fails
                if not follow:
                    break
                if lagged:
                    state = _note_state(state, "lagged", "wikidata is lagged: waiting")
                elif count:
                    state = "writing"
            time.sleep(applying.FOLLOW_IDLE)
    except KeyboardInterrupt:
        click.echo("")
    finally:
        lock.__exit__(None, None, None)
    verb = "applied" if write else "would apply"
    click.echo(f"{seen} people: {verb} {applied} proposals, {failed} failed")


def _note_state(state: str, now: str, message: str) -> str:
    """Print a follow-mode heartbeat only when the state it reports has changed."""
    if state != now:
        click.echo(message)
    return now


@cli.command()
@click.option("--limit", default=10, show_default=True)
@click.option("--qid", multiple=True, help="Dump these people instead of a batch.")
@country_option
def dump(limit: int, qid: Sequence[str], country: str | None) -> None:
    """Write each person's request and parsed answer to data/extract/<qid>.md."""
    DUMP_DIR.mkdir(parents=True, exist_ok=True)
    rows = db.conn().execute(
        "SELECT DISTINCT ON (e.qid) e.qid, e.request_json, e.response_json, e.bad_quotes"
        " FROM extraction e JOIN person p ON p.qid = e.qid"
        " WHERE (%s OR e.qid = ANY(%s)) AND (%s::text IS NULL OR p.country = %s)"
        " ORDER BY e.qid, e.id DESC LIMIT %s",
        (not qid, list(qid), country, country, limit),
    )
    count = 0
    for person_qid, request, response, bad_quotes in rows:
        body = request["messages"][0]["content"]
        answer = dict(response)
        bad = answer.pop("_bad_quotes", [])
        parts = [f"# {person_qid}", "", body, "", "# Parsed response", "", "```json"]
        parts.append(json.dumps(answer, indent=2, ensure_ascii=False))
        parts.append("```")
        parts.append("")
        parts.append(f"# Bad quotes ({bad_quotes})")
        parts.append("")
        parts.extend(f"- {quote!r}" for quote in bad)
        path = DUMP_DIR / f"{person_qid}.md"
        path.write_text("\n".join(parts) + "\n")
        count += 1
        click.echo(f"{path} ({len(body)} chars sent, {bad_quotes} bad quotes)")
    click.echo(f"{count} dumps written")


@cli.command("policy")
@click.option("--limit", default=100000, show_default=True)
@click.option("--qid", multiple=True, help="Decide these people instead of a run's.")
@click.option("--dry-run", is_flag=True, help="Report what the rules would decide; write nothing.")
@country_option
def policy_(limit: int, qid: Sequence[str], dry_run: bool, country: str | None) -> None:
    """Decide every proposal by rule: accepted, skipped, or pending the verifier.

    Reads each person's `new` and `refine` rows -- and whatever the policy
    itself decided last time, so a rule change is one re-run -- and never a
    row a human ruled on or `apply` has written. The report is the funnel:
    per property, how many rows entered and which rule took each of them.
    """
    people = _select(qid, ("proposed",), limit, country)
    if not people:
        click.echo("nobody proposed")
        return
    funnel = policy.run(people, write=not dry_run)
    labels = policy.office_labels(list(funnel.offices))
    for line in policy.report_lines(funnel, labels):
        click.echo(line)
    click.echo(f"{len(people)} people, {'reported' if dry_run else 'decided'}")


def _pending_people(qid: Sequence[str], limit: int, country: str | None) -> list[str]:
    """The people with a proposal the policy has held for the verifier."""
    if qid:
        return list(qid)
    rows = db.conn().execute(
        "SELECT DISTINCT p.person_qid FROM proposal p JOIN person pe ON pe.qid = p.person_qid"
        " WHERE p.status = 'pending' AND (%s::text IS NULL OR pe.country = %s)"
        " ORDER BY p.person_qid LIMIT %s",
        (country, country, limit),
    )
    return [row[0] for row in rows]


@cli.command("verify")
@click.option("--limit", default=50, show_default=True, help="How many people to verify.")
@click.option("--threads", default=4, show_default=True)
@click.option("--qid", multiple=True, help="Verify these people instead of a batch.")
@click.option("--dry-run", is_flag=True, help="Print what the model would be shown; send nothing.")
@country_option
def verify_(
    limit: int, threads: int, qid: Sequence[str], dry_run: bool, country: str | None
) -> None:
    """Ask a second model about every proposal the policy holds as `pending`.

    One request per proposal against the frozen `prompts/verify.md`, shown the
    edit as it would land beside the article and the item's own claims. A
    verdict is stored by the content it was about, so a re-run asks only what
    is new; once a person's rows are answered the policy is run over them
    again, and each row leaves as `accepted` or `skipped`.
    """
    people = _pending_people(qid, limit, country)
    if not people:
        click.echo("nothing pending")
        return
    if dry_run:
        for person_qid in people:
            for row in verifying.pending_rows(person_qid):
                click.echo(f"===== proposal {row['id']} =====")
                click.echo(verifying.render_edit(verifying.edit_for(row)))
        return

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
    with ThreadPoolExecutor(max_workers=threads) as pool:
        for lines, counts in pool.map(one, people):
            for line in lines:
                click.echo(line)
            totals.update(counts)
    click.echo(f"{len(people)} people: " + ", ".join(f"{k}={v}" for k, v in sorted(totals.items())))


def _mentions_for(country: str | None, limit: int) -> list[tuple[int, int, Any]]:
    """List the office mentions still unanswered under the current prompt.

    One row per (extraction, mention index). The extraction chosen per person
    is the newest, because an older one was answered about articles that have
    since been re-read. The ledger, not this query, is what makes the pass
    resumable -- `resolve_mention` returns a recorded verdict without asking --
    but skipping the answered ones here keeps `--limit` meaning new work.
    """
    _text, prompt_hash = reconciling.system_prompt()
    rows = db.conn().execute(
        "SELECT e.id, e.response_json->'positions' FROM ("
        "  SELECT DISTINCT ON (qid) id, qid, response_json FROM extraction"
        "  WHERE response_json IS NOT NULL ORDER BY qid, id DESC"
        ") e JOIN person pe ON pe.qid = e.qid"
        " WHERE (%s::text IS NULL OR pe.country = %s)"
        " AND pe.status <> 'out_of_scope' ORDER BY e.id",
        (country, country),
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
            if len(work) >= limit:
                return work
    return work


@cli.command()
@click.option("--limit", default=100, show_default=True)
@click.option("--threads", default=4, show_default=True)
@country_option
def reconcile(limit: int, threads: int, country: str | None) -> None:
    """Resolve each extracted office mention to a position item, or refuse.

    One request per mention against the frozen `prompts/reconcile.md`, never a
    batch: several offices in one context is how a pass standardises on
    whatever it answered first. The country names whose holder counts rank the
    shortlist; it is not a filter, and an office of another state stays
    reachable and is tagged as one.

    A mention already answered under this prompt and rendering is skipped
    without a request, so a re-run costs only what is new.
    """
    state_qid = positions.country_qid(country) if country else None
    work = _mentions_for(country, limit)
    if not work:
        click.echo("nothing to reconcile")
        return
    def one(item: tuple[int, int, Any]) -> tuple[str, tuple[str, ...]]:
        """Resolve one mention, returning its line and what it counts towards.

        The tally is returned rather than incremented: `counts[k] += 1` from a
        pool is a read-modify-write on shared state, and a lost count in a
        summary is the kind of wrong number nothing later contradicts.

        A mention the model fails on is a line of output, not the end of the
        run. Measured once: a response that repeated `0.0}` until it hit
        `max_tokens` came back as truncated JSON, the structured-output parser
        raised, and one bad answer out of 440 took the pool down with it. The
        verdict is simply not recorded, so the next pass asks again.
        """
        extraction_id, index, mention = item
        try:
            verdict, sent = reconciling.resolve_mention(extraction_id, index, mention, state_qid)
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
    with ThreadPoolExecutor(max_workers=threads) as pool:
        for line, tally in pool.map(one, work):
            counts.update(tally)
            click.echo(line)
    click.echo(
        f"{len(work)} mentions: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    )


@cli.command("titles")
@click.option("--country", required=True, help="ISO code of the run whose titles to translate.")
@click.option("--dry-run", is_flag=True, help="Count what would be asked; ask nothing.")
def titles_(country: str, dry_run: bool) -> None:
    """Cache an English office name for every extracted title, and for unlabelled offices.

    The second search channel `reconcile` reads. Resumable from the table: a
    title cached under the current prompt and model is never asked again, so
    a re-run pays only for new titles. Offices with no `en`/`mul` label get the
    same pass's name as a local search aid, never written to Wikidata.
    """
    state_qid = positions.country_qid(country)
    since = db.conn().execute("SELECT now()").fetchone()[0]
    mentions = titles.mention_titles(state_qid, country)
    click.echo(f"mentions: {len(mentions)}")
    stats = titles.translate(mentions, dry_run=dry_run, log=click.echo)
    click.echo("mentions: " + ", ".join(f"{k}={v}" for k, v in stats.items()))
    items = titles.item_titles(state_qid=state_qid)
    stats = titles.refresh_items(items, dry_run=dry_run, log=click.echo)
    click.echo("offices: " + ", ".join(f"{k}={v}" for k, v in stats.items()))
    if not dry_run:
        spent = titles.cost(since=since)
        click.echo(
            f"spent: {spent['requests']} requests, {spent['titles']} titles,"
            f" {spent['input_tokens']} input + {spent['output_tokens']} output tokens"
        )


@cli.command("load-positions")
@click.option("--country", required=True, help="ISO code of the country to load.")
@click.option(
    "--source",
    "sources",
    multiple=True,
    type=click.Choice(positions.SOURCES),
    help="Run only these discovery lanes instead of all of them.",
)
def load_positions(country: str, sources: Sequence[str]) -> None:
    """Load one country's position items into the reconciliation table."""
    started = time.monotonic()
    counts = positions.load_country(
        country, sources or positions.SOURCES, log=click.echo
    )
    click.echo(
        f"loaded {counts['loaded']} positions, {counts['names']} names"
        f" in {time.monotonic() - started:.0f}s"
    )


@cli.command("position-signals")
@click.option("--country", required=True, help="ISO code of the country to count.")
@click.option("--skip-counts", is_flag=True, help="Only the two local signals.")
@click.option(
    "--local-holders",
    is_flag=True,
    help="Only count this country's citizens among every position's holders,"
         " for the rows that have no count for it yet.",
)
@click.option(
    "--recount",
    is_flag=True,
    help="With --local-holders, re-ask for rows that already have a count.",
)
def position_signals(
    country: str, skip_counts: bool, local_holders: bool, recount: bool
) -> None:
    """Fill the ranking signals for one country's positions.

    Separate from the load because the counts are grouped query-service
    queries that take minutes and are worth re-running on their own, and
    because a signal too expensive for a large country has to be skippable
    without blocking the rows from existing.
    """
    qid = positions.country_qid(country)
    if local_holders:
        # The one signal that is a statement about the country asking, and
        # the only one worth re-running when a *different* country's load
        # added rows: the other four are whole-corpus counts that a new
        # country does not change the answer to.
        positions.fill_local_holders(qid, only_missing=not recount, log=click.echo)
        return
    if not skip_counts:
        timings = positions.fill_counts(qid, log=click.echo)
        click.echo(f"counts in {sum(timings.values()):.0f}s total")
    positions.fill_scope_qualifiers(log=click.echo)
    positions.fill_diplomatic(log=click.echo)


@cli.command("position-stats")
@click.option("--country", help="Report on one country instead of the whole table.")
def position_stats(country: str | None) -> None:
    """Report what the position table holds, per discovery source."""
    where, params = "", []
    if country:
        where = " WHERE country_qid = %s"
        params = [positions.country_qid(country)]
    total = db.conn().execute(
        f"SELECT count(*) FROM position{where}", params
    ).fetchone()[0]
    click.echo(f"positions:        {total}")
    click.echo(
        "names:            "
        + str(db.conn().execute("SELECT count(*) FROM position_name").fetchone()[0])
    )
    click.echo(
        "type edges cached: "
        + str(db.conn().execute("SELECT count(*) FROM type_edge").fetchone()[0])
    )
    click.echo("\nby source set:")
    rows = db.conn().execute(
        f"SELECT array_to_string(sources, '+'), count(*) FROM position{where}"
        " GROUP BY 1 ORDER BY 2 DESC",
        params,
    )
    for label, count in rows:
        click.echo(f"  {label or '(none)':<24} {count}")
    click.echo("\nflags:")
    rows = db.conn().execute(
        f"SELECT count(*) FILTER (WHERE not_office),"
        f" count(*) FILTER (WHERE abolished IS NOT NULL),"
        f" count(*) FILTER (WHERE jurisdiction_qid IS NOT NULL),"
        f" count(*) FILTER (WHERE holders IS NOT NULL) FROM position{where}",
        params,
    ).fetchone()
    for name, count in zip(
        ("not_office", "abolished", "has jurisdiction", "holders counted"), rows
    ):
        click.echo(f"  {name:<24} {count}")


@cli.command()
@country_option
def stats(country: str | None) -> None:
    """Print row counts per person status, per article language and per table.

    With `--country` every count that hangs off a person is scoped to that
    run; `http_cache` is not, because a cache entry belongs to no one.
    """
    conn = db.conn()
    # One predicate, spliced into each person-shaped query. The table alias in
    # front of `qid` differs per query, so the caller supplies it.
    scope = " AND (%s::text IS NULL OR {alias}qid IN (SELECT qid FROM person WHERE country = %s))"
    args = (country, country)
    click.echo("person by status:")
    for status, count in conn.execute(
        "SELECT status, count(*) FROM person WHERE (%s::text IS NULL OR country = %s)"
        " GROUP BY status ORDER BY count(*) DESC",
        args,
    ):
        click.echo(f"  {status:12s} {count}")
    for table in ("membership", "item", "article"):
        count = conn.execute(
            f"SELECT count(*) FROM {table} WHERE true" + scope.format(alias=""), args
        ).fetchone()[0]
        click.echo(f"{table:12s} {count}")
    count = conn.execute("SELECT count(*) FROM http_cache").fetchone()[0]
    click.echo(f"{'http_cache':12s} {count}")
    click.echo("seed categories by members (top 10):")
    for lang, category, count in conn.execute(
        "SELECT lang, category, count(*) FROM membership WHERE true"
        + scope.format(alias="")
        + " GROUP BY lang, category ORDER BY count(*) DESC LIMIT 10",
        args,
    ):
        click.echo(f"  {count:6d}  {lang}:{category}")
    extracted, tokens = conn.execute(
        "SELECT count(DISTINCT qid), coalesce(sum((usage_json->>'input_tokens')::bigint"
        " + (usage_json->>'cache_creation_input_tokens')::bigint"
        " + (usage_json->>'cache_read_input_tokens')::bigint"
        " + (usage_json->>'output_tokens')::bigint), 0) FROM extraction WHERE true"
        + scope.format(alias=""),
        args,
    ).fetchone()
    click.echo(f"extracted    {extracted} people, {tokens} tokens")
    click.echo("articles by language (top 15):")
    for lang, count in conn.execute(
        "SELECT lang, count(*) FROM article WHERE true"
        + scope.format(alias="")
        + " GROUP BY lang ORDER BY count(*) DESC LIMIT 15",
        args,
    ):
        click.echo(f"  {lang:8s} {count}")
    proposed, rows = conn.execute(
        "SELECT count(DISTINCT person_qid), count(*) FROM proposal WHERE true"
        + scope.format(alias="person_"),
        args,
    ).fetchone()
    click.echo(f"proposal     {rows} rows for {proposed} people")
    _echo_property_counts(country)
    for line in reviewing.summary_lines(country):
        click.echo(line)
    click.echo("mint candidates by status:")
    for status, count in conn.execute(
        "SELECT status, count(*) FROM office_candidate WHERE (%s::text IS NULL OR country = %s)"
        " GROUP BY status ORDER BY count(*) DESC, status",
        args,
    ):
        click.echo(f"  {status:12s} {count}")


# --- mint --------------------------------------------------------------------
#
# The stage between `reconcile` and `propose` that creates the offices nobody's
# P39 had anywhere to go. `mint` is imported inside each command: the verify half
# is still growing, and a command that does not touch it should not depend on it.


def _mint_module() -> Any:
    from peploop import mint

    return mint


@cli.command("mint-categorize")
@click.option("--country", required=True, help="ISO code of the country to categorize.")
@click.option("--dry-run", is_flag=True, help="Print the first request; ask and write nothing.")
def mint_categorize(country: str, dry_run: bool) -> None:
    """Cluster a country's unplaced offices into candidates, and draft each one."""
    stats = _mint_module().categorize(country, dry_run=dry_run, log=click.echo)
    stats.pop("clusters", None)
    stats.pop("truncated", None)
    click.echo(json.dumps(stats, sort_keys=True))


@cli.command("mint-verify")
@click.option("--country", required=True, help="ISO code of the country to verify.")
@click.option("--limit", default=None, type=int, help="Verify at most this many candidates.")
@click.option("--threads", default=4, show_default=True)
@click.option("--dry-run", is_flag=True, help="Print what the model would be shown; send nothing.")
def mint_verify(country: str, limit: int | None, threads: int, dry_run: bool) -> None:
    """Ask the second model about each categorized office, and decide each by rule."""
    verify = getattr(_mint_module(), "verify", None)
    if verify is None:
        raise click.ClickException("mint.verify is not implemented yet")
    stats = verify(country, limit=limit, threads=threads, dry_run=dry_run, log=click.echo)
    if not isinstance(stats, dict):
        return
    for (status, rule), n in sorted((stats.get("funnel") or {}).items(), key=lambda kv: -kv[1]):
        click.echo(f"{n:5d}  {status:10s} {rule}")
    click.echo(json.dumps({k: v for k, v in stats.items() if k not in ("funnel", "decided") and _jsonable(v)},
                          sort_keys=True, default=str))


def _jsonable(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool, list, dict, type(None)))


@cli.command("mint")
@click.option("--country", required=True, help="ISO code of the country to mint for.")
@click.option("--limit", default=None, type=int, help="Create at most this many items.")
@click.option("--id", "ids", multiple=True, type=int, help="Only these candidates.")
@click.option("--write", is_flag=True, help="Create the items; without it nothing leaves here.")
def mint_(country: str, limit: int | None, ids: Sequence[int], write: bool) -> None:
    """Create each guarded office as a Wikidata item, then feed it back into the run.

    A dry run by default: it prints each guarded payload with the labels of
    every item it names, and writes nothing anywhere. `--write` logs in, takes
    the country's writer lock, resolves any creation a crash left behind, and
    then creates one item every ten seconds, re-checking each live first and
    feeding it into the position table and the mentions it was attested by.
    """
    if not write:
        rows = minting.guarded(country, ids, limit)
        for cand in rows:
            names = minting.labels_of(cand)
            click.echo(f"===== #{cand['id']} {cand['ref']} ({cand['holders']} holders,"
                       f" {cand['current_holders']} current) =====")
            for qid, label in sorted(names.items()):
                click.echo(f"  {qid} = {label}")
            click.echo(json.dumps(cand["data"], indent=2, ensure_ascii=False))
        click.echo(f"{len(rows)} guarded; would create {len(rows)} items (dry run)")
        return
    click.echo(f"logged in as {applying.login()}")
    token = applying.csrf_token()
    recheck = minting.default_recheck()
    if recheck is minting.fallback_recheck:
        click.echo("mint.reguard not found: re-checking by live duplicate search only")
    counts: Counter[str] = Counter()
    with minting.writer_lock(country):
        for cid, outcome, qid in minting.recover(country, log=click.echo):
            counts[f"recovered:{outcome}"] += 1
        rows = minting.guarded(country, ids, limit)
        for index, cand in enumerate(rows):
            if index:
                time.sleep(applying.THROTTLE)
            head = f"#{cand['id']} {cand['ref']}"
            try:
                qid = minting.mint_one(cand["id"], token, recheck=recheck)
            except Exception as exc:  # noqa: BLE001 — stop: recover resolves the row next run
                counts["failed"] += 1
                click.echo(f"{head} failed, left for recover: {type(exc).__name__}: {exc}")
                break
            after = db.conn().execute(
                "SELECT status, rule FROM office_candidate WHERE id = %s", (cand["id"],)
            ).fetchone()
            counts[after[0]] += 1
            click.echo(f"{head} -> {qid or '-'} {after[0]} {after[1] or ''}".rstrip())
            if after[0] in minting.FEEDABLE:
                click.echo("  " + minting.feed(country, [cand["id"]], log=click.echo).line())
    click.echo(f"{country}: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))


@cli.command("mint-feed")
@click.option("--country", required=True, help="ISO code of the country to feed.")
@click.option("--id", "ids", multiple=True, type=int, help="Only these candidates.")
def mint_feed(country: str, ids: Sequence[int]) -> None:
    """Load every created or found item and re-ask the mentions it was attested by."""
    click.echo(minting.feed(country, list(ids) or None, log=click.echo).line())


@cli.command("mint-report")
@click.option("--country", required=True, help="ISO code of the country to report on.")
@click.option("--out", "out", default=None, type=click.Path(dir_okay=False, path_type=Path),
              help="Write the markdown here instead of printing it.")
def mint_report(country: str, out: Path | None) -> None:
    """Report the funnel by rule, what was created and found, the skips, and the cost."""
    text = minting.report(country)
    if out is None:
        click.echo(text, nl=False)
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    click.echo(f"{out} written")


@cli.command("mint-audit")
@click.option("--id", "cand_id", required=True, type=int, help="The candidate audited.")
@click.option("--skip", is_flag=True, required=True, help="Skip it; the only ruling there is.")
@click.option("--reason", required=True, help="Why, as the export list will show it.")
@click.option("--by", required=True, help="Who audited it; the rule becomes audit:<by>.")
def mint_audit(cand_id: int, skip: bool, reason: str, by: str) -> None:
    """Skip a candidate after the fact. There is no approve: nothing waits on a human."""
    if not skip:
        raise click.UsageError("an audit can only skip: pass --skip")
    try:
        cand = minting.audit_skip(cand_id, reason, by)
    except (LookupError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"#{cand_id} {cand['ref']}: {cand['status']} -> skipped (audit:{by})")


if __name__ == "__main__":
    cli()
