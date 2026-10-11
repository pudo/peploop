"""The edit record every producer writes and every renderer reads.

Reach for this instead of inventing a per-campaign dict. The workbench grew two
incompatible verdict dialects — a P39 one keyed on `era`, and a classifier one
keyed on `kind`/`confidence` — which is why birth dates and citizenship could
not share a renderer with positions, and why the acting-qualifier path stayed
half-built for months (`render_edit_plan.py` read a `qualifiers` field that no
producer ever wrote).

Three properties make this schema worth the ceremony:

* **Qualifiers and references hang off the statement, not the record.** P569
  wants `S143` + `S4656` while P39 wants `S854` + `S813`; a single per-record
  source pair cannot express both.
* **The decision is explicit and always present.** A record says what will
  happen and which rule decided it, so the review document is an audit of
  decisions taken rather than a queue of questions.
* **`flags` is a list.** The tier it replaces was assigned by an if/elif chain,
  so a row that was acting *and* pre-cutoff *and* roster-only kept only whichever
  label the chain reached first, and any policy keyed on that string silently
  inherited the loss.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

SCHEMA = 2

#: What will be done with a record. `hold` is transitional: it marks a statement
#: the engine believes but that the era gate keeps out of the batch, and it
#: disappears once the policy layer decides those cases outright.
ACTIONS = ("apply", "hold", "review", "skip", "defect", "byproduct")


@dataclass(frozen=True)
class Value:
    """A snak value, in the few shapes this workbench emits."""

    type: str
    id: Optional[str] = None
    iso: Optional[str] = None
    precision: Optional[int] = None
    text: Optional[str] = None

    @staticmethod
    def item(qid: str) -> "Value":
        return Value("item", id=qid)

    @staticmethod
    def time(iso: str) -> "Value":
        """A partial ISO date, with the precision its length implies."""
        return Value("time", iso=iso, precision={1: 9, 2: 10, 3: 11}[min(len(iso.split("-")), 3)])

    @staticmethod
    def url(text: str) -> "Value":
        return Value("url", text=text)

    @staticmethod
    def string(text: str) -> "Value":
        return Value("string", text=text)

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass(frozen=True)
class Snak:
    property: str
    value: Value

    def to_dict(self) -> Dict[str, Any]:
        return {"property": self.property, "value": self.value.to_dict()}


@dataclass
class Statement:
    property: str
    value: Value
    qualifiers: List[Snak] = field(default_factory=list)
    references: List[Snak] = field(default_factory=list)
    #: True when the item already carries this statement — the diff-against-item
    #: discipline made explicit rather than hidden in a skip.
    existing: bool = False
    #: The roster gave this term a start and left its end column blank, rather
    #: than not offering one. Carried through to `wd.validate.check`, which
    #: otherwise reads a start-only line beside a dated one as one tenure two
    #: sources date differently — see `RosterRow.end_withheld`.
    end_withheld: bool = False

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "property": self.property,
            "value": self.value.to_dict(),
        }
        if self.qualifiers:
            out["qualifiers"] = [q.to_dict() for q in self.qualifiers]
        if self.references:
            out["references"] = [r.to_dict() for r in self.references]
        if self.existing:
            out["existing"] = True
        if self.end_withheld:
            out["end_withheld"] = True
        return out


@dataclass
class Subject:
    """Who the statements are about — an existing item, or one to be created.

    A `create` subject carries a stable `ref` instead of a QID so the creation
    ledger can recognise it on a later run and reuse the item it already made.
    """

    kind: str = "item"
    qid: Optional[str] = None
    ref: Optional[str] = None
    label: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v}


@dataclass
class Decision:
    action: str
    #: The rule that fired. This is the audit key: the review document groups by
    #: it, so a human reviews a dozen rules with counts rather than 300 rows.
    rule: str
    source: str = "default"
    #: Which single-concern .qs file this belongs in.
    concern: str = "p39"
    rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v}


@dataclass
class Signal:
    """One channel's contribution to a decision.

    Replaces the free-text evidence sentence, which was built by f-string in
    three places with three different wordings. The prose is generated from
    these, so it stays consistent and the channels stay countable.
    """

    channel: str
    supports: str
    detail: str
    source_url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v}


@dataclass
class Record:
    campaign: str
    subject: Subject
    statements: List[Statement]
    decision: Decision
    office: Optional[str] = None
    identity: Dict[str, Any] = field(default_factory=dict)
    flags: List[str] = field(default_factory=list)
    signals: List[Signal] = field(default_factory=list)
    notes: str = ""
    byproduct: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "schema": SCHEMA,
            "campaign": self.campaign,
            "subject": self.subject.to_dict(),
            "statements": [s.to_dict() for s in self.statements],
            "decision": self.decision.to_dict(),
        }
        if self.office:
            out["office"] = self.office
        if self.identity:
            out["identity"] = self.identity
        if self.flags:
            out["flags"] = sorted(self.flags)
        if self.signals:
            out["signals"] = [s.to_dict() for s in self.signals]
        if self.notes:
            out["notes"] = self.notes
        if self.byproduct:
            out["byproduct"] = self.byproduct
        return out


def sort_key(record: Record) -> tuple:
    """Stable emission order.

    Ordering has to be deterministic or the regression diff drowns in noise;
    today's order is only accidentally stable, coming from dict insertion.
    """
    statement = record.statements[0] if record.statements else None
    return (
        record.office or "",
        statement.value.id or "" if statement else "",
        statement.property if statement else "",
        record.subject.qid or record.subject.ref or "",
        record.decision.rule,
    )


def dumps(records: List[Record]) -> str:
    """JSONL, sorted and with stable key order, ready to diff."""
    return "".join(
        json.dumps(r.to_dict(), ensure_ascii=False, sort_keys=True) + "\n"
        for r in sorted(records, key=sort_key)
    )
