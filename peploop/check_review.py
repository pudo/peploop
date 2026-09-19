"""Drive the review app headlessly against the real database and undo the run.

Textual can be driven without a terminal, so the one thing a review command
must get right — the keys write the verdicts they say they do — is checkable
offline. The script picks a real person, reviews them, asserts what landed, and
then deletes its own verdicts and restores the proposal statuses, so running it
costs the database nothing.

Run it as `python -m peploop.check_review` from the repository root.
"""

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from textual.widgets import Static

from peploop import db, review

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
    """List people with at least `minimum` proposals left to review."""
    rows = db.conn().execute(
        "SELECT p.person_qid, count(*) FROM proposal p JOIN person pe ON pe.qid = p.person_qid"
        " WHERE pe.status = 'proposed' AND p.status = ANY(%s)"
        " AND NOT EXISTS (SELECT 1 FROM verdict v WHERE v.proposal_id = p.id)"
        " GROUP BY p.person_qid HAVING count(*) >= %s ORDER BY count(*), p.person_qid",
        (list(review.REVIEWABLE), minimum),
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


def main() -> int:
    """Run the check and report what it did, restoring the database afterwards."""
    conn = db.conn()
    people = _reviewable(2)
    if not people:
        print("no person has two reviewable proposals; nothing to check")
        return 1
    qid, count = people[0]
    before = {
        row[0]: row[1]
        for row in conn.execute(
            "SELECT id, status FROM proposal WHERE person_qid = %s", (qid,)
        )
    }
    print(f"reviewing {qid} with {count} reviewable proposals")
    try:
        return _check(conn, qid)
    finally:
        _restore(conn, before)


def _check(conn: Any, qid: str) -> int:
    """Review the person headlessly and report what each assertion found."""
    app, rows, moves = asyncio.run(_drive(qid))
    ids = [row.id for row in rows]
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
    expect(statuses.get(ids[0]) == "accepted", f"{ids[0]} status is accepted")
    expect(statuses.get(ids[1]) == "rejected", f"{ids[1]} status is rejected")
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
    expect(not unnamed, f"the sidebar spells out all eight reasons (missing {unnamed})")
    for header in wide.headers:
        print(f"  rendered {header}")
    narrow = asyncio.run(_layout(qids[:1], NARROW_SIZE, NARROW_SHOT_PATH))
    expect(
        narrow.legend and not narrow.sidebar,
        f"at {NARROW_SIZE[0]} columns the sidebar is hidden and the legend is back",
    )
    print(f"screenshots at {SHOT_PATH} and {NARROW_SHOT_PATH}")

    return 1 if failures else 0


def _restore(conn: Any, before: dict[int, str]) -> None:
    """Undo the run: drop its verdicts and put every status back as it was."""
    ids = list(before)
    with conn.transaction():
        conn.execute("DELETE FROM verdict WHERE proposal_id = ANY(%s)", (ids,))
        for ident, status in before.items():
            conn.execute(
                "UPDATE proposal SET status = %s, decided_by = NULL, decided_at = NULL"
                " WHERE id = %s",
                (status, ident),
            )
    left = conn.execute(
        "SELECT count(*) FROM verdict WHERE proposal_id = ANY(%s)", (ids,)
    ).fetchone()[0]
    print(f"restored: {len(before)} proposal statuses, {left} verdict rows left behind")


if __name__ == "__main__":
    sys.exit(main())
