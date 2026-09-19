"""Drive the peploop pipeline from the command line.

Run as `python -m peploop.cli <command>` from the repository root. Every command
is idempotent: seeding twice queues nothing new, fetching twice re-uses the
item and article rows that are still inside their age tolerance.
"""

import json
import time
from collections import Counter
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import click

from peploop import apply as applying
from peploop import db, wikidata, wikipedia
from peploop import extract as extraction
from peploop import propose as proposals
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
        text = wikipedia.html_to_text(article["html"])
        db.upsert_article(qid, lang, title, article["rev_id"], article["url"], text)
        count += 1
    return count


def _process(qid: str, entity: dict[str, Any], force: bool) -> tuple[str, str]:
    """Enforce P31=Q5 and read the person's articles, returning their status."""
    try:
        if "Q5" not in wikidata.claim_qids(entity, "P31"):
            db.set_person_status(qid, "not_human")
            return qid, "not_human"
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


@cli.command()
@click.option(
    "--file",
    "path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Seed file of categories, e.g. peploop/seeds/cz.yml.",
)
def seed(path: Path) -> None:
    """Queue the members of every Wikipedia category in a seed file."""
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
            added += db.upsert_person(qid)
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
def fetch(limit: int, threads: int, qid: Sequence[str]) -> None:
    """Fetch the item and every Wikipedia article of queued people."""
    if qid:
        qids: list[str] = list(qid)
    else:
        rows = db.conn().execute(
            "SELECT qid FROM person WHERE status = 'queued' ORDER BY qid LIMIT %s",
            (limit,),
        )
        qids = [row[0] for row in rows]
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
    db.set_person_status(qid, "extracted")
    head = f"{row.qid} {(row.label or '?')[:28]:28s} arts={row.articles}"
    if row.skipped:
        return "extracted", f"{head} skipped (already extracted from these revisions)"
    dropped = ",".join(row.dropped) or "-"
    return "extracted", (
        f"{head} dropped={dropped} in={row.input_tokens} cache_w={row.cache_creation}"
        f" cache_r={row.cache_read} out={row.output_tokens} bad_quotes={row.bad_quotes}"
        f" positions={row.positions} {row.seconds:.1f}s"
    )


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
def extract(limit: int, threads: int, qid: Sequence[str]) -> None:
    """Ask the model about fetched people and store the structured answer.

    Selection is stable, so the same `--limit` picks the same people twice: a
    person already extracted under this prompt and these article revisions is
    skipped without a request, and re-running costs nothing.
    """
    if qid:
        qids: list[str] = list(qid)
    else:
        rows = db.conn().execute(
            "SELECT qid FROM person WHERE status IN ('fetched', 'extracted')"
            " ORDER BY qid LIMIT %s",
            (limit,),
        )
        qids = [row[0] for row in rows]
    if not qids:
        click.echo("nothing fetched")
        return
    with ThreadPoolExecutor(max_workers=threads) as pool:
        for _, line in pool.map(_extract_one, qids):
            click.echo(line)


def _select(qid: Sequence[str], statuses: tuple[str, ...], limit: int) -> list[str]:
    """Pick the people a command works on: the named ones, or the next batch."""
    if qid:
        return list(qid)
    rows = db.conn().execute(
        "SELECT qid FROM person WHERE status = ANY(%s) ORDER BY qid LIMIT %s",
        (list(statuses), limit),
    )
    return [row[0] for row in rows]


@cli.command()
@click.option("--limit", default=100, show_default=True)
@click.option("--qid", multiple=True, help="Propose for these people instead of a batch.")
def propose(limit: int, qid: Sequence[str]) -> None:
    """Turn each extracted person's answer into proposals, and status them."""
    qids = _select(qid, ("extracted", "proposed"), limit)
    if not qids:
        click.echo("nothing extracted")
        return
    for person_qid in qids:
        click.echo(_propose_one(person_qid)[1])
    _echo_property_counts()


def _echo_property_counts() -> None:
    """Print how many proposals of each property carry each status."""
    click.echo("proposals by property and status:")
    for prop, status, count in db.conn().execute(
        "SELECT property, status, count(*) FROM proposal GROUP BY property, status"
        " ORDER BY property, status"
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
def run(limit: int, threads: int, qid: Sequence[str]) -> None:
    """Fetch, extract and propose in one pass per person."""
    qids = _select(qid, ("queued",), limit)
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
    _echo_property_counts()


@cli.command()
@click.option("--status", default="new,refine", show_default=True)
@click.option("--property", "properties", multiple=True, help="Render only these properties.")
def render(status: str, properties: Sequence[str]) -> None:
    """Print the selected proposals as QuickStatements v1 lines.

    Nothing is written to Wikidata: the output is a batch a human pastes into
    the QuickStatements importer after reading it.
    """
    statuses = [part.strip() for part in status.split(",") if part.strip()]
    try:
        lines, problems = rendering.render(statuses, list(properties))
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
def review(limit: int, qid: Sequence[str]) -> None:
    """Review people's `new`, `refine` and `conflict` proposals, recording a verdict.

    One person per screen, drawn at random from those with something left to
    review; each person's decisions are written in one transaction when the
    screen is submitted. An accepted conflict is a note that the item is wrong,
    not an edit: `apply` never writes a value contradicting what is recorded.
    """
    qids = reviewing.select_people(list(qid), limit)
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


@cli.command("apply")
@click.option("--limit", default=10, show_default=True)
@click.option("--qid", multiple=True, help="Write these people instead of a batch.")
@click.option("--write", is_flag=True, help="Send the edits; without it nothing leaves here.")
def apply_(limit: int, qid: Sequence[str], write: bool) -> None:
    """Write each person's accepted proposals to Wikidata as one edit.

    A dry run by default: it does the same pre-flight against the live item and
    prints the payload it would send. `--write` logs in and sends, one person
    every ten seconds, and records what came back on each proposal.
    """
    qids = applying.people(list(qid), limit)
    if not qids:
        click.echo("nothing accepted")
        return
    token = None
    if write:
        click.echo(f"logged in as {applying.login()}")
        token = applying.csrf_token()
    applied, failed = 0, 0
    for index, person_qid in enumerate(qids):
        if write and index:
            time.sleep(applying.THROTTLE)
        try:
            plan, note = applying.apply_person(person_qid, token)
        except Exception as exc:  # noqa: BLE001 — a refused edit is a row, not a dead run
            failed += 1
            click.echo(f"{person_qid} failed: {type(exc).__name__}: {exc}")
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
    verb = "applied" if write else "would apply"
    click.echo(f"{len(qids)} people: {verb} {applied} proposals, {failed} failed")


@cli.command()
@click.option("--limit", default=10, show_default=True)
@click.option("--qid", multiple=True, help="Dump these people instead of a batch.")
def dump(limit: int, qid: Sequence[str]) -> None:
    """Write each person's request and parsed answer to data/extract/<qid>.md."""
    DUMP_DIR.mkdir(parents=True, exist_ok=True)
    rows = db.conn().execute(
        "SELECT DISTINCT ON (qid) qid, request_json, response_json, bad_quotes"
        " FROM extraction WHERE (%s OR qid = ANY(%s)) ORDER BY qid, id DESC LIMIT %s",
        (not qid, list(qid), limit),
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


@cli.command()
def stats() -> None:
    """Print row counts per person status, per article language and per table."""
    conn = db.conn()
    click.echo("person by status:")
    for status, count in conn.execute(
        "SELECT status, count(*) FROM person GROUP BY status ORDER BY count(*) DESC"
    ):
        click.echo(f"  {status:12s} {count}")
    for table in ("membership", "item", "article", "http_cache"):
        count = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        click.echo(f"{table:12s} {count}")
    click.echo("seed categories by members (top 10):")
    for lang, category, count in conn.execute(
        "SELECT lang, category, count(*) FROM membership GROUP BY lang, category"
        " ORDER BY count(*) DESC LIMIT 10"
    ):
        click.echo(f"  {count:6d}  {lang}:{category}")
    extracted, tokens = conn.execute(
        "SELECT count(DISTINCT qid), coalesce(sum((usage_json->>'input_tokens')::bigint"
        " + (usage_json->>'cache_creation_input_tokens')::bigint"
        " + (usage_json->>'cache_read_input_tokens')::bigint"
        " + (usage_json->>'output_tokens')::bigint), 0) FROM extraction"
    ).fetchone()
    click.echo(f"extracted    {extracted} people, {tokens} tokens")
    click.echo("articles by language (top 15):")
    for lang, count in conn.execute(
        "SELECT lang, count(*) FROM article GROUP BY lang ORDER BY count(*) DESC LIMIT 15"
    ):
        click.echo(f"  {lang:8s} {count}")
    proposed, rows = conn.execute(
        "SELECT count(DISTINCT person_qid), count(*) FROM proposal"
    ).fetchone()
    click.echo(f"proposal     {rows} rows for {proposed} people")
    _echo_property_counts()
    for line in reviewing.summary_lines():
        click.echo(line)


if __name__ == "__main__":
    cli()
