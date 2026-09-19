"""Score a prompt or rule change against the verdicts a human already gave.

The reviewed rows are the only ground truth this pipeline has, and they are
worth more as a test set than as a backlog: every accepted value the new prompt
still yields is a rule that did not break, and every rejected one it no longer
yields — or that a mechanical rule now throws out — is review the human never
has to do again. So this re-extracts the judged people under the current prompt
and re-derives their proposals in memory, without storing anything: `propose`
keeps a judged row and declines to insert its duplicate, which would hide
exactly the change being measured.

Re-extraction costs one model call per judged person, and `extract` skips a
person it has already read under this prompt and these article revisions, so a
second run inside one prompt version is free.

Run it as `python -m peploop.check_regress` from the repository root.
"""

import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from peploop import db, extract, prompt, propose

THREADS = 4
LISTED = 40


@dataclass
class Judged:
    """One proposal a human ruled on, and what the current rules make of it."""

    qid: str
    property: str
    value: dict[str, Any]
    decision: str
    reason: str | None
    status: str = "absent"
    filtered_by: str | None = None

    @property
    def reproduced(self) -> bool:
        """Say whether the value is still proposed for a human to see."""
        return self.status not in ("absent", propose.FILTERED)

    def line(self) -> str:
        """Render the row for one of the report's lists."""
        value = self.value
        shown = value.get("text") or value.get("id") or value.get("time") or value
        detail = f" [{self.filtered_by}]" if self.filtered_by else ""
        return (
            f"  {self.qid:12s} {self.property:12s} {str(shown)[:36]:38s}"
            f" {self.reason or '-':16s} → {self.status}{detail}"
        )


def judged_rows() -> list[Judged]:
    """Read every proposal a human has ruled on, oldest first."""
    rows = db.conn().execute(
        "SELECT p.person_qid, p.property, p.value, v.decision, v.reason"
        " FROM proposal p JOIN verdict v ON v.proposal_id = p.id"
        " ORDER BY v.decision, p.person_qid, p.property"
    )
    return [Judged(*row) for row in rows]


def reextract(qids: list[str]) -> Counter[str]:
    """Re-extract every judged person under the current prompt, reporting outcomes."""
    counts: Counter[str] = Counter()

    def one(qid: str) -> str:
        try:
            row = extract.extract_person(qid)
        except Exception as exc:  # noqa: BLE001 — a failed person is a count, not a dead run
            print(f"  {qid} failed: {type(exc).__name__}: {exc}")
            return "failed"
        return "skipped" if row.skipped else "extracted"

    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        for outcome in pool.map(one, qids):
            counts[outcome] += 1
    return counts


def current(qid: str) -> dict[str, propose.Proposal]:
    """Derive one person's proposals from their latest extraction, storing nothing."""
    conn = db.conn()
    row = conn.execute(
        "SELECT response_json FROM extraction WHERE qid = %s ORDER BY id DESC LIMIT 1", (qid,)
    ).fetchone()
    item = conn.execute("SELECT json FROM item WHERE qid = %s", (qid,)).fetchone()
    if row is None or item is None:
        return {}
    built = propose.build(item[0], row[0], propose.article_texts(qid))
    return {propose.value_key(p.property, p.value): p for p in built}


def score(rows: list[Judged]) -> None:
    """Fill in what the current prompt and rules make of each judged row."""
    for qid in sorted({row.qid for row in rows}):
        proposals = current(qid)
        for row in [r for r in rows if r.qid == qid]:
            found = proposals.get(propose.value_key(row.property, row.value))
            if found is None:
                continue
            row.status = found.status
            row.filtered_by = (found.qualifiers or {}).get("_reason")


def report(rows: list[Judged]) -> None:
    """Print the three numbers and the rows behind two of them."""
    accepted = [row for row in rows if row.decision == "accept"]
    rejected = [row for row in rows if row.decision == "reject"]
    kept = [row for row in accepted if row.reproduced]
    lost = [row for row in accepted if not row.reproduced]
    survived = [row for row in rejected if row.reproduced]
    caught = [row for row in rejected if row.status == propose.FILTERED]
    print(f"accepted reproduced   {len(kept)}/{len(accepted)}")
    print(f"rejected reproduced   {len(survived)}/{len(rejected)}")
    print(f"rejected now filtered {len(caught)}/{len(rejected)}")
    for title, group in (
        ("accepted values no longer proposed (regressions)", lost),
        ("rejected values still proposed", survived),
        ("rejected values a rule now filters", caught),
    ):
        print(f"\n{title}: {len(group)}")
        for row in group[:LISTED]:
            print(row.line())


def main() -> int:
    """Re-extract the judged people, re-derive their proposals and score them."""
    rows = judged_rows()
    if not rows:
        print("no verdicts recorded; nothing to score against")
        return 1
    qids = sorted({row.qid for row in rows})
    print(f"{len(rows)} verdicts over {len(qids)} people, prompt {prompt.system_prompt()[1][:12]}")
    counts = reextract(qids)
    print("extraction: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    score(rows)
    report(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
