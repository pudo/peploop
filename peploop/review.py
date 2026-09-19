"""Review one person's proposals at a time and record a verdict for each.

The unit of review is the person, shown beside what Wikidata already records
about them: whether a proposed value is right is usually decided by looking at
the item as a whole, not at an isolated row. So both go in one table, grouped
by property with the item's own claims dimmed above the proposals — the
comparison is then a glance down one column instead of a jump between a text
dump and a grid. Accept is the resting state, so the common person is a glance
and one `Enter`, and a digit rejects a single row with one reason from the
closed set the `verdict` table allows.

Nothing here writes to Wikidata. A submitted person's decisions land in one
transaction, and a row marked skipped stays reviewable later.
"""

import os
import webbrowser
from dataclasses import dataclass, field
from typing import Any, ClassVar

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.markup import escape
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Input, Static

from peploop import db, prompt, wikidata

REVIEWABLE = ("new", "refine")
# The order is the keypad: digit 1 is the first of these. It must stay a subset
# of the `verdict.reason` check constraint in schema.sql.
REASONS = (
    "wrong_value", "wrong_precision", "quote_unsupported", "wrong_person",
    "already_recorded", "rule_missing", "source_wrong", "other",
)
# One word per reason, for the legend and the verdict cell: what the database
# stores is too long to read across a row eight times.
REASON_WORDS = {
    "wrong_value": "value", "wrong_precision": "precision",
    "quote_unsupported": "quote", "wrong_person": "person",
    "already_recorded": "recorded", "rule_missing": "rule",
    "source_wrong": "source", "other": "other",
}
WRONG_PERSON = REASONS.index("wrong_person") + 1

# The words a reviewer reads instead of a P-code, and the order the groups are
# drawn in. `labels` is not a property: it is the one summary row standing for
# every language the item has a label in.
PROPERTY_NAMES = {
    "P31": "human",
    "labels": "labels",
    "P21": "gender",
    "P569": "birth date",
    "P570": "death date",
    "P19": "birth place",
    "P27": "citizenship",
    "P39": "position",
}
ITEM_GROUPS = ("P31", "P21", "P19", "P27")
TIME_GROUPS = ("P569", "P570")
# How many languages the `labels` row names before it falls back to a count.
LABEL_LANGS = 5
QUOTE_PREVIEW = 60
VALUE_WIDTH = 46
SPAN_QUALIFIERS = (("P580", "from"), ("P582", "to"))
ACCEPT, REJECT, SKIP = "accept", "reject", "skip"
MARKS = {ACCEPT: "✓", REJECT: "✗", SKIP: "–"}
# The digits are the only keys with no footer entry, so they are spelled out.
# One line: at 118 characters it is the widest thing on screen that must not
# wrap, which is what the single spaces between the reasons buy.
LEGEND = (
    f"{MARKS[REJECT]} "
    + " ".join(f"[b]{n}[/b] {REASON_WORDS[r]}" for n, r in enumerate(REASONS, 1))
    + "  [b]A[/b] accept all  [b]R[/b]# reject all  [b]W[/b] wrong person"
)


def property_name(prop: str) -> str:
    """Name a property the way a reviewer reads it, P-codes left out.

    `label:cs` and `alias:cs` are peploop's pseudo-properties for Wikidata
    terms, which are not statements and have no property of their own.
    """
    for prefix in ("label", "alias"):
        if prop.startswith(f"{prefix}:"):
            return f"{prefix} ({prop.split(':', 1)[1]})"
    return PROPERTY_NAMES.get(prop, prop)


def date_text(value: dict[str, Any]) -> str:
    """Render a time datavalue for a table cell, at the precision it claims."""
    return prompt.format_time(value["time"], value.get("precision", 11), name_day=False)


def item_cell(qid: str, labels: dict[str, str | None]) -> Text:
    """Render an item value as its label with the QID dimmed behind it."""
    cell = Text(prompt.named(qid, labels, label_first=True))
    cell.stylize("dim", len(cell) - len(qid))
    return cell


def value_cell(
    value: dict[str, Any], qualifiers: dict[str, Any] | None, labels: dict[str, str | None]
) -> Text:
    """Render a proposed datavalue and its date qualifiers as one cell."""
    if "time" in value:
        cell = Text(date_text(value))
    elif "id" in value:
        cell = item_cell(value["id"], labels)
    elif "text" in value:
        cell = Text(value["text"])
    else:
        cell = Text(str(value))
    spans = [
        f"{name} {date_text((qualifiers or {})[prop])}"
        for prop, name in SPAN_QUALIFIERS
        if (qualifiers or {}).get(prop)
    ]
    if spans:
        cell.append(f"  [{', '.join(spans)}]", style="dim")
    return cell


def span_text(claim: dict[str, Any]) -> str:
    """Render a statement's start and end qualifiers as one `when` cell."""
    start = prompt.qualifier_time(claim, "P580")
    end = prompt.qualifier_time(claim, "P582")
    if start is None and end is None:
        return ""
    return f"{date_text(start) if start else '?'} → {date_text(end) if end else '?'}"


def label_summary(entity: dict[str, Any], prefer: list[str]) -> Text:
    """Name the languages the item has a label in, capped at a readable few.

    One row for all of them: the labels are here so a reviewer can see the item
    is the right person and that a proposed term is not already recorded, and
    thirty language codes answer neither question better than five do.
    """
    have = list(entity.get("labels", {}))
    order = [lang for lang in dict.fromkeys([*prefer, *have]) if lang in have]
    rest = len(order) - LABEL_LANGS
    shown = ", ".join(order[:LABEL_LANGS]) or "—"
    return Text(f"{shown} + {rest} more" if rest > 0 else shown)


def existing_values(
    entity: dict[str, Any], group: str, labels: dict[str, str | None], prefer: list[str]
) -> list[tuple[Text, str]]:
    """List (value, when) pairs for what the item already records in a group."""
    if group == "labels":
        return [(label_summary(entity, prefer), "")]
    if group in TIME_GROUPS:
        return [
            (Text(prompt.format_time(time, precision, name_day=False)), "")
            for time, precision in wikidata.claim_time(entity, group)
        ]
    if group == "P39":
        held = []
        for claim in entity.get("claims", {}).get("P39", []):
            value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
            if isinstance(value, dict) and "id" in value:
                held.append((item_cell(value["id"], labels), span_text(claim)))
        return held
    if group in ITEM_GROUPS:
        return [(item_cell(qid, labels), "") for qid in wikidata.claim_qids(entity, group)]
    kind, _, lang = group.partition(":")
    if kind == "label":
        term = entity.get("labels", {}).get(lang)
        return [(Text(term["value"]), "")] if term else []
    return [(Text(term["value"]), "") for term in entity.get("aliases", {}).get(lang, [])]


@dataclass
class Row:
    """One reviewable proposal and the decision standing against it."""

    id: int
    property: str
    value: dict[str, Any]
    qualifiers: dict[str, Any] | None
    quote: str | None
    lang: str | None
    url: str | None
    status: str
    decision: str = ACCEPT
    reason: str | None = None
    note: str | None = None

    def mark(self) -> str:
        """Render the decision as the table's first cell."""
        text = MARKS[self.decision]
        if self.reason:
            text = f"{text} {REASON_WORDS.get(self.reason, self.reason)}"
        return f"{text} +note" if self.note else text


@dataclass
class Line:
    """One line of the table: a claim the item holds, or a proposal on it."""

    key: str
    cells: list[Text]
    row: Row | None = None


@dataclass
class Person:
    """Everything one review screen shows about one person."""

    qid: str
    label: str
    entity: dict[str, Any]
    labels: dict[str, str | None] = field(default_factory=dict)
    articles: list[tuple[str, str]] = field(default_factory=list)
    seed_url: str | None = None
    rows: list[Row] = field(default_factory=list)


def dim(cells: list[Text]) -> list[Text]:
    """Dim a whole line, which is what marks it as the item's own record."""
    for cell in cells:
        cell.stylize("dim")
    return cells


def build_lines(person: Person) -> list[Line]:
    """Lay out one person as table lines, grouped by property.

    A group is drawn when the item records something in it or a proposal wants
    to, existing values first so a proposal reads as an addition to what is
    above it. Term groups come last and only where something is proposed: the
    item's other thirty labels are the one `labels` row.
    """
    proposals: dict[str, list[Row]] = {}
    for row in person.rows:
        proposals.setdefault(row.property, []).append(row)
    terms = sorted(
        (group for group in proposals if ":" in group),
        key=lambda group: (group.split(":")[1], 0 if group.startswith("label") else 1),
    )
    prefer = ["en", "mul", *(lang for lang, _ in person.articles)]
    lines: list[Line] = []
    for group in [*PROPERTY_NAMES, *terms]:
        rows = proposals.get(group, [])
        existing = existing_values(person.entity, group, person.labels, prefer)
        if not rows and not existing:
            continue
        name = property_name(group)
        for number, (value, when) in enumerate(existing):
            cells = [Text(""), Text(name), value, Text(when), Text("")]
            lines.append(Line(f"{group}#{number}", dim(cells)))
        for row in rows:
            lines.append(Line(str(row.id), proposal_cells(row, person.labels), row))
    for line in lines:
        # The value column is fixed, so a long office name is cut here rather
        # than by the viewport, which would give no sign that it was cut.
        line.cells[2].truncate(VALUE_WIDTH, overflow="ellipsis")
    return lines


def proposal_cells(row: Row, labels: dict[str, str | None]) -> list[Text]:
    """Render one proposal as the five cells of its line."""
    quote = " ".join((row.quote or "").split())
    if len(quote) > QUOTE_PREVIEW:
        quote = quote[:QUOTE_PREVIEW] + "…"
    return [
        Text(row.mark()),
        Text(property_name(row.property)),
        value_cell(row.value, row.qualifiers, labels),
        Text(row.lang or ""),
        Text(quote) if quote else Text("—", style="dim"),
    ]


def select_people(qids: list[str], limit: int) -> list[str]:
    """Pick people to review: the named ones, or a random draw of proposed ones.

    Random order, because reviewing in insertion order measures whoever was
    seeded first rather than the pipeline.
    """
    if qids:
        return qids
    rows = db.conn().execute(
        "SELECT p.person_qid FROM proposal p JOIN person pe ON pe.qid = p.person_qid"
        " WHERE pe.status = 'proposed' AND p.status = ANY(%s)"
        " AND NOT EXISTS (SELECT 1 FROM verdict v WHERE v.proposal_id = p.id)"
        " GROUP BY p.person_qid ORDER BY random() LIMIT %s",
        (list(REVIEWABLE), limit),
    )
    return [row[0] for row in rows]


def load_person(qid: str) -> Person | None:
    """Assemble one review screen's worth of state, or nothing if the item is gone."""
    conn = db.conn()
    item = conn.execute("SELECT json FROM item WHERE qid = %s", (qid,)).fetchone()
    if item is None:
        return None
    entity = item[0]
    rows = [
        Row(*record)
        for record in conn.execute(
            "SELECT id, property, value, qualifiers, quote, source_lang, source_url, status"
            " FROM proposal WHERE person_qid = %s AND status = ANY(%s)"
            " AND NOT EXISTS (SELECT 1 FROM verdict v WHERE v.proposal_id = proposal.id)"
            " ORDER BY property, id",
            (qid, list(REVIEWABLE)),
        )
    ]
    # The articles the latest extraction actually read, in the order it read them.
    read = conn.execute(
        "SELECT article_langs FROM extraction WHERE qid = %s ORDER BY id DESC LIMIT 1", (qid,)
    ).fetchone()
    urls = dict(conn.execute("SELECT lang, url FROM article WHERE qid = %s", (qid,)))
    seed = conn.execute(
        "SELECT lang FROM membership WHERE qid = %s ORDER BY seen_at LIMIT 1", (qid,)
    ).fetchone()
    articles = [(lang, urls[lang]) for lang in (read[0] if read else []) if lang in urls]
    seed_lang = seed[0] if seed else None
    person = Person(
        qid=qid,
        label=wikidata.best_label(entity) or qid,
        entity=entity,
        articles=articles,
        seed_url=urls.get(seed_lang or "") or (articles[0][1] if articles else None),
        rows=rows,
    )
    wanted = prompt.state_qids(entity)
    wanted.extend(r.value["id"] for r in rows if "id" in r.value)
    person.labels = {
        found: wikidata.best_label(entity)
        for found, entity in wikidata.fetch_items(wanted, props="labels").items()
    }
    return person


def write_verdicts(rows: list[Row], reviewer: str) -> tuple[int, int]:
    """Record one person's decisions in a single transaction.

    Rows marked skipped are left alone, and so is a row someone has ruled on
    since the screen was drawn: a verdict is the one thing in the table a
    re-run cannot reproduce.
    """
    conn = db.conn()
    written, taken = 0, 0
    with conn.transaction():
        for row in rows:
            if row.decision == SKIP:
                continue
            already = conn.execute(
                "SELECT 1 FROM verdict WHERE proposal_id = %s", (row.id,)
            ).fetchone()
            if already is not None:
                taken += 1
                continue
            conn.execute(
                "INSERT INTO verdict (proposal_id, decision, reason, note)"
                " VALUES (%s, %s, %s, %s)",
                (row.id, row.decision, row.reason, row.note or None),
            )
            conn.execute(
                "UPDATE proposal SET status = %s, decided_by = %s, decided_at = now()"
                " WHERE id = %s",
                ("accepted" if row.decision == ACCEPT else "rejected", reviewer, row.id),
            )
            written += 1
    return written, taken


def summary_lines() -> list[str]:
    """Report acceptance per property and rejections per reason over every verdict."""
    conn = db.conn()
    total = conn.execute("SELECT count(*) FROM verdict").fetchone()[0]
    if not total:
        return []
    lines = [f"verdicts: {total}", "acceptance by property:"]
    for prop, accepted, seen in conn.execute(
        "SELECT p.property, count(*) FILTER (WHERE v.decision = 'accept'), count(*)"
        " FROM verdict v JOIN proposal p ON p.id = v.proposal_id"
        " GROUP BY p.property ORDER BY p.property"
    ):
        lines.append(f"  {property_name(prop):20s} {accepted:4d}/{seen:<4d} {accepted / seen:.0%}")
    lines.append("rejections by reason:")
    for reason, count in conn.execute(
        "SELECT coalesce(reason, '(none)'), count(*) FROM verdict WHERE decision = 'reject'"
        " GROUP BY reason ORDER BY count(*) DESC"
    ):
        lines.append(f"  {reason:20s} {count}")
    return lines


class NoteScreen(ModalScreen[str | None]):
    """Ask for the one-line note that stays on a row whatever its decision."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "cancel", "cancel")]

    def __init__(self, label: str, note: str) -> None:
        super().__init__()
        self.label = label
        self.note = note

    def compose(self) -> ComposeResult:
        with Vertical(id="note-box"):
            yield Static(f"note on {escape(self.label)}")
            yield Input(value=self.note, placeholder="one line, Enter to keep", id="note")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip())

    def action_cancel(self) -> None:
        self.dismiss(None)


class ProposalTable(DataTable):
    """The one table. `Enter` submits the person, and the arrows skip the dim rows."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("enter", "app.submit", "submit", show=False),
        Binding("up", "app.cursor(-1)", "up", show=False),
        Binding("down", "app.cursor(1)", "down", show=False),
    ]


class ReviewApp(App[None]):
    """Walk a list of people, one screen each, recording verdicts on submit."""

    CSS = """
    #person { height: 1; padding: 0 1; background: $panel; }
    #legend { height: 1; color: $text-muted; }
    /* The quote column takes whatever is left and is clipped rather than
       scrolled: the evidence panel below holds the quote in full. */
    ProposalTable { height: auto; max-height: 70%; overflow-x: hidden; }
    #evidence { height: auto; max-height: 10; padding: 0 1; border-top: solid $primary; }
    #note-box { width: 70%; height: auto; padding: 1 2; background: $panel; border: thick $primary; }
    NoteScreen { align: center middle; }
    """
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("j", "cursor(1)", "down", show=False),
        Binding("k", "cursor(-1)", "up", show=False),
        Binding("a", "accept", "accept"),
        Binding("s", "skip_row", "skip row"),
        Binding("n", "note", "note"),
        Binding("A", "accept_all", "accept all", show=False),
        Binding("R", "arm_bulk", "reject all", show=False),
        Binding("W", "wrong_person", "wrong person", show=False),
        Binding("x", "skip_person", "skip person"),
        Binding("o", "open_item", "wikidata"),
        Binding("w", "open_article", "article"),
        Binding("escape", "disarm", "cancel", show=False),
        Binding("q", "quit", "quit"),
        *[Binding(str(n), f"reject({n})", REASONS[n - 1], show=False) for n in range(1, 9)],
    ]
    COLUMNS = (
        ("verdict", "verdict"),
        ("property", "property"),
        ("value", "value"),
        ("when", "when/lang"),
        ("source", "source"),
    )

    def __init__(self, qids: list[str], reviewer: str | None = None) -> None:
        super().__init__()
        self.qids = qids
        self.reviewer = reviewer or os.environ.get("USER") or "review"
        self.index = -1
        self.person: Person | None = None
        self.lines: list[Line] = []
        # Table indices the cursor may rest on: the proposals, in table order.
        self.stops: list[int] = []
        self.written = 0
        self.skipped = 0
        self.bulk = False

    def compose(self) -> ComposeResult:
        yield Static(id="person")
        yield Static(LEGEND, id="legend")
        yield ProposalTable(cursor_type="row")
        yield Static(id="evidence")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(ProposalTable)
        for key, label in self.COLUMNS:
            width = VALUE_WIDTH if key == "value" else None
            table.add_column(label, key=key, width=width)
        self.advance()

    @property
    def table(self) -> ProposalTable:
        """Return the proposal table, which is the only focusable widget here."""
        return self.query_one(ProposalTable)

    def advance(self) -> None:
        """Move to the next person with something to review, or leave."""
        while True:
            self.index += 1
            if self.index >= len(self.qids):
                self.exit()
                return
            person = load_person(self.qids[self.index])
            if person is not None and person.rows:
                self.person = person
                self.show_person()
                return

    def show_person(self) -> None:
        """Draw the current person: header, one table, evidence."""
        person = self.person
        assert person is not None
        links = " · ".join(f"[link='{url}']{lang}[/link]" for lang, url in person.articles)
        name = escape(person.label)
        if person.seed_url:
            name = f"[link='{person.seed_url}']{name}[/link]"
        self.query_one("#person", Static).update(
            f"[b]{name}[/b]  "
            f"[link='https://www.wikidata.org/wiki/{person.qid}']{person.qid}[/link]  {links}"
            f"   [dim]{self.index + 1}/{len(self.qids)}[/dim]"
        )
        self.lines = build_lines(person)
        self.stops = [n for n, line in enumerate(self.lines) if line.row is not None]
        table = self.table
        table.clear()
        for line in self.lines:
            table.add_row(*line.cells, key=line.key)
        table.focus()
        if self.stops:
            table.move_cursor(row=self.stops[0])
        self.show_evidence()

    def rows(self) -> list[Row]:
        """List the current person's rows, or nothing before one is loaded."""
        return self.person.rows if self.person is not None else []

    def current(self) -> Row | None:
        """Return the proposal under the cursor, if the cursor is on one."""
        index = self.table.cursor_row
        if index is None or not 0 <= index < len(self.lines):
            return None
        return self.lines[index].row

    def show_evidence(self) -> None:
        """Show the selected row's quote in full, with the article it came from."""
        row = self.current()
        if row is None:
            self.query_one("#evidence", Static).update("")
            return
        parts = [escape(row.quote or "(no quote)")]
        source = f"{row.status} · {row.lang or '?'} · {row.url or 'no source'}"
        parts.append(f"[dim]{escape(source)}[/dim]")
        if row.note:
            parts.append(f"[i]note: {escape(row.note)}[/i]")
        self.query_one("#evidence", Static).update("\n".join(parts))

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Keep the cursor on a proposal; a mouse click can land it on a dim row."""
        if self.stops and event.cursor_row not in self.stops:
            self.table.move_cursor(row=min(self.stops, key=lambda n: abs(n - event.cursor_row)))
            return
        self.show_evidence()

    def action_cursor(self, delta: int) -> None:
        """Move to the next or previous proposal, stepping over the dim rows."""
        if not self.stops:
            return
        here = self.table.cursor_row
        position = self.stops.index(here) + delta if here in self.stops else 0
        self.table.move_cursor(row=self.stops[min(max(position, 0), len(self.stops) - 1)])

    def _decide(self, rows: list[Row | None], decision: str, reason: str | None) -> None:
        """Set a decision on some rows and redraw them; a note survives it."""
        for row in rows:
            if row is not None:
                row.decision, row.reason = decision, reason
                self.table.update_cell(str(row.id), "verdict", Text(row.mark()))
        self.show_evidence()

    def action_accept(self) -> None:
        """Put the current row back to the resting state."""
        self._decide([self.current()], ACCEPT, None)

    def action_skip_row(self) -> None:
        """Leave the current row undecided, so it stays reviewable later."""
        self._decide([self.current()], SKIP, None)

    def action_accept_all(self) -> None:
        """Put every row back to the resting state."""
        self._decide(list(self.rows()), ACCEPT, None)

    def action_reject(self, digit: int) -> None:
        """Reject with the digit's reason: the current row, or every row after `R`."""
        rows = list(self.rows()) if self.bulk else [self.current()]
        self.bulk = False
        self._decide(rows, REJECT, REASONS[digit - 1])

    def action_arm_bulk(self) -> None:
        """Wait for the digit that rejects every row with one reason."""
        self.bulk = True
        self.notify("reject every row: press a digit 1-8")

    def action_disarm(self) -> None:
        self.bulk = False

    def action_wrong_person(self) -> None:
        """Reject the whole person as a mismatch and submit in one stroke."""
        self._decide(list(self.rows()), REJECT, REASONS[WRONG_PERSON - 1])
        self.action_submit()

    def action_note(self) -> None:
        """Attach a one-line note to the current row, whatever its decision."""
        row = self.current()
        if row is None:
            return

        def keep(note: str | None) -> None:
            if note is None:
                return
            row.note = note or None
            self._decide([row], row.decision, row.reason)

        self.push_screen(NoteScreen(property_name(row.property), row.note or ""), keep)

    def action_submit(self) -> None:
        """Write this person's decisions and move on."""
        if self.person is None:
            return
        written, taken = write_verdicts(self.person.rows, self.reviewer)
        self.written += written
        if taken:
            self.notify(f"{taken} rows were already decided elsewhere and were left alone")
        self.advance()

    def action_skip_person(self) -> None:
        """Move on without writing anything about this person."""
        self.skipped += 1
        self.advance()

    def action_open_item(self) -> None:
        if self.person is not None:
            webbrowser.open(f"https://www.wikidata.org/wiki/{self.person.qid}")

    def action_open_article(self) -> None:
        if self.person is not None and self.person.seed_url:
            webbrowser.open(self.person.seed_url)
