"""Drive the review app headlessly against shadowed tables and pin what it may write.

Textual can be driven without a terminal, so the two things the sampler must
get right are checkable offline: the keys write the verdicts they say they do,
and a verdict is all they write -- no proposal status changes, so nothing
reaches Wikidata except through the policy, which reads a rejection and skips
the row. `proposal` and `verdict` are shadowed by temporary copies for the
length of the run, so a real person's screen is drawn and nothing live is
touched: an earlier version wrote to the live rows and "restored" them by
clearing `decided_by`, which erased the policy's provenance on every row.

Run it as `python -m peploop.check_review` from the repository root.
"""

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from textual.widgets import Static

from peploop import db, policy, review

SHOT_PATH = Path("data/review.svg")
NARROW_SHOT_PATH = Path("data/review_narrow.svg")
SHOT_PEOPLE = 3
# Either side of `review.SIDEBAR_MIN_COLUMNS`: the sidebar is the layout at the
# first size and must be gone at the second, with the legend back in its place.
WIDE_SIZE = (160, 40)
NARROW_SIZE = (100, 40)


@dataclass
class Layout:
    """What one terminal size made of the reason help, and who was drawn in it."""

    sidebar: bool
    legend: bool
    sidebar_text: str
    headers: list[str]


def _reviewable(minimum: int) -> list[tuple[str, int]]:
    """List people with at least `minimum` proposals left to review, all of them decidable.

    A conflict is reviewable but no policy rule reads it, so a person whose
    rows include one could not show what the policy makes of a rejection.
    """
    rows = db.conn().execute(
        "SELECT p.person_qid, count(*) FROM proposal p JOIN person pe ON pe.qid = p.person_qid"
        " WHERE pe.status = 'proposed' AND p.status = ANY(%s)"
        " AND NOT EXISTS (SELECT 1 FROM verdict v WHERE v.proposal_id = p.id)"
        " AND (p.decided_by IS NULL OR p.decided_by LIKE %s)"
        " GROUP BY p.person_qid HAVING count(*) >= %s"
        " AND count(*) FILTER (WHERE NOT p.status = ANY(%s)) = 0"
        " ORDER BY count(*), p.person_qid",
        (list(review.REVIEWABLE), policy.DECIDER + "%", minimum, list(policy.DECIDABLE)),
    )
    return [(qid, count) for qid, count in rows]


def _shot_person() -> str | None:
    """Pick the person whose screen shows the most: held offices and proposals.

    The point of the screenshot is the layout, and the layout is about existing
    claims sitting dimmed above the proposals, so a person with no `P39` on
    their item would picture half of it.
    """
    row = db.conn().execute(
        "SELECT p.person_qid FROM proposal p JOIN person pe ON pe.qid = p.person_qid"
        " JOIN item i ON i.qid = p.person_qid"
        " WHERE pe.status = 'proposed' AND p.status = ANY(%s)"
        " AND NOT EXISTS (SELECT 1 FROM verdict v WHERE v.proposal_id = p.id)"
        " GROUP BY p.person_qid, i.json"
        " HAVING count(*) >= 2"
        " ORDER BY jsonb_array_length(coalesce(i.json->'claims'->'P39', '[]'::jsonb)) > 0 DESC,"
        " count(DISTINCT p.property) DESC, count(*) DESC, p.person_qid",
        (list(review.REVIEWABLE),),
    ).fetchone()
    return None if row is None else row[0]


async def _drive(qid: str) -> tuple[review.ReviewApp, list[review.Row], list[int]]:
    """Accept the first row, reject the second, skip the rest, and submit.

    The cursor positions are returned with the app, because the table now
    holds the item's own claims too and the one thing keys can get wrong is
    landing on one of them.
    """
    app = review.ReviewApp([qid], reviewer="check_review")
    moves: list[int] = []
    async with app.run_test() as pilot:
        await pilot.pause()
        rows = list(app.person.rows) if app.person else []
        moves.append(app.table.cursor_row)
        await pilot.press("down")
        moves.append(app.table.cursor_row)
        await pilot.press("up")
        moves.append(app.table.cursor_row)
        await pilot.press("j", "2")
        for _ in rows[2:]:
            await pilot.press("j", "s")
        await pilot.press("enter")
        if app.is_running:
            await pilot.press("q")
    return app, rows, moves


async def _layout(qids: list[str], size: tuple[int, int], path: Path) -> Layout:
    """Draw every person at one terminal size and report what the reasons look like.

    Drawing all of them and not just the screenshotted one is the cheap half of
    the check: a person whose table the layout cannot fit throws on render.
    """
    app = review.ReviewApp(qids, reviewer="check_review")
    headers = []
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        path.parent.mkdir(parents=True, exist_ok=True)
        app.save_screenshot(str(path))
        sidebar = app.query_one("#sidebar", Static)
        seen = (sidebar.display, app.query_one("#legend", Static).display, str(sidebar.content))
        for _ in qids:
            if not app.is_running:
                break
            headers.append(str(app.query_one("#person", Static).content))
            await pilot.press("x")
        if app.is_running:
            await pilot.press("q")
    return Layout(*seen, headers)


#: The tables the sampler writes, shadowed by full temporary copies.
SHADOWED = ("proposal", "verdict")


def shadow(conn: Any) -> None:
    """Put a temporary copy of each written table in front of the real one."""
    for table in SHADOWED:
        conn.execute(f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING DEFAULTS"
                     " INCLUDING INDEXES INCLUDING CONSTRAINTS)")
        conn.execute(f"INSERT INTO pg_temp.{table} SELECT * FROM public.{table}")
        top = conn.execute(f"SELECT coalesce(max(id), 0) + 1 FROM pg_temp.{table}").fetchone()[0]
        conn.execute(f"CREATE TEMP SEQUENCE {table}_seq START {top}")
        conn.execute(f"ALTER TABLE pg_temp.{table} ALTER COLUMN id SET DEFAULT"
                     f" nextval('pg_temp.{table}_seq')")


def unshadow(conn: Any) -> None:
    for table in SHADOWED:
        conn.execute(f"DROP TABLE IF EXISTS pg_temp.{table}")
        conn.execute(f"DROP SEQUENCE IF EXISTS pg_temp.{table}_seq")


def main() -> int:
    """Run the check against the shadowed tables and report what it found."""
    conn = db.conn()
    live = conn.execute("SELECT count(*), max(id) FROM public.verdict").fetchone()
    shadow(conn)
    try:
        people = _reviewable(2)
        if not people:
            print("no person has two reviewable proposals; nothing to check")
            return 1
        qid, count = people[0]
        print(f"reviewing {qid} with {count} reviewable proposals")
        return _check(conn, qid)
    finally:
        unshadow(conn)
        after = conn.execute("SELECT count(*), max(id) FROM public.verdict").fetchone()
        print(f"live verdict table untouched: {after == live}")


def _check(conn: Any, qid: str) -> int:
    """Review the person headlessly and report what each assertion found."""
    before = dict(conn.execute("SELECT id, status FROM proposal WHERE person_qid = %s", (qid,)))
    app, rows, moves = asyncio.run(_drive(qid))
    # Drawn order, not load order. The table groups by property and puts the
    # term pseudo-properties last, so a person with a `label:` or `alias:`
    # proposal has `person.rows` in a different order from the rows the keys
    # act on -- and the assertions below are about which row a key reached.
    ids = [line.row.id for line in app.lines if line.row is not None]
    stops = app.stops
    verdicts = {
        row[0]: (row[1], row[2])
        for row in conn.execute(
            "SELECT proposal_id, decision, reason FROM verdict WHERE proposal_id = ANY(%s)",
            (ids,),
        )
    }
    statuses = {
        row[0]: row[1]
        for row in conn.execute(
            "SELECT id, status FROM proposal WHERE id = ANY(%s)", (ids,)
        )
    }
    failures: list[str] = []

    def expect(condition: bool, message: str) -> None:
        print(("  ok   " if condition else "  FAIL ") + message)
        if not condition:
            failures.append(message)

    expect(
        len(app.lines) > len(rows),
        f"{len(app.lines) - len(rows)} dimmed rows drawn beside {len(rows)} proposals",
    )
    expect(
        moves == [stops[0], stops[1], stops[0]],
        f"the cursor stepped over the dimmed rows: {moves} within {stops}",
    )
    expect(app.written == 2, f"two verdicts written (got {app.written})")
    expect(verdicts.get(ids[0]) == ("accept", None), f"{ids[0]} accepted with no reason")
    expect(
        verdicts.get(ids[1]) == ("reject", "wrong_precision"),
        f"{ids[1]} rejected as wrong_precision",
    )
    expect(
        all(statuses.get(ident) == before[ident] for ident in ids),
        "no proposal status changed: the sampler records verdicts and gates nothing",
    )
    decided = {pid: policy.decide(case) for pid, case in policy.person_cases(qid)}
    expect(
        decided.get(ids[1]) == policy.Disposition(policy.SKIPPED, "review_rejected"),
        f"the policy skips {ids[1]} on the sampler's rejection",
    )
    expect(
        ids[0] not in decided or decided[ids[0]].rule != "review_rejected",
        f"an accept in the sampler decides nothing: {ids[0]} goes on to the rules",
    )
    expect(
        all(ident not in verdicts for ident in ids[2:]),
        f"{len(ids[2:])} skipped rows kept no verdict",
    )

    shot = _shot_person()
    draw = [q for q in review.select_people([], SHOT_PEOPLE) if q != shot]
    qids = ([shot] if shot else []) + draw
    wide = asyncio.run(_layout(qids, WIDE_SIZE, SHOT_PATH))
    unnamed = [name for name in review.REASON_NAMES.values() if name not in wide.sidebar_text]
    expect(
        wide.sidebar and not wide.legend,
        f"at {WIDE_SIZE[0]} columns the sidebar replaces the one-line legend",
    )
    # A tenure has to be readable where the item's own tenures are read, which
    # is the `when` column. Appending it to the value cell instead put it
    # behind a `VALUE_WIDTH` truncation, where a long office name ate it.
    spanned = [
        review.span_cell({"P580": {"time": "+2020-10-15T00:00:00Z", "precision": 11}}),
        review.span_cell({"P582": {"time": "+2022-06-01T00:00:00Z", "precision": 11}}),
        review.span_cell({"P585": {"time": "+2020-10-15T00:00:00Z", "precision": 11}}),
        review.span_cell(None),
    ]
    expect(
        [str(cell) if cell is not None else None for cell in spanned]
        == ["2020-10-15 → ?", "? → 2022-06-01", None, None],
        f"a tenure renders into the when column, one endpoint or two (got {spanned})",
    )
    expect(
        not unnamed,
        f"the sidebar spells out all {len(review.REASONS)} reasons (missing {unnamed})",
    )
    for header in wide.headers:
        print(f"  rendered {header}")
    narrow = asyncio.run(_layout(qids[:1], NARROW_SIZE, NARROW_SHOT_PATH))
    expect(
        narrow.legend and not narrow.sidebar,
        f"at {NARROW_SIZE[0]} columns the sidebar is hidden and the legend is back",
    )
    print(f"screenshots at {SHOT_PATH} and {NARROW_SHOT_PATH}")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
