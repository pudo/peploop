"""What the model may propose about a person, and what has to hold before it counts.

The judgement pass is one channel. This module is the other one, and it is
entirely mechanical: every proposal is checked against the evidence it claims to
rest on before it can become a `wd/record.py` Record.

The cheapest and strongest check is the **verbatim quote**. The schema below
requires each proposal to carry a span copied out of the dossier, and
`Dossier.contains` asserts it really occurs there. That converts "the model
asserted a date" into "the model pointed at a date in a document we fetched", at
no marginal cost — and it catches the failure a JSON schema structurally cannot,
because `output_config.format` constrains every field's shape and no field's
value.

Two things the model is never allowed to produce:

* **a country QID** — it names the country in prose and
  `rigour.territories.lookup_territory` resolves it. That library already knows
  that "Islamic Republic of Iran" is Q794 and "Zaire" is Q6500954; a model
  guessing QIDs is a class of error with no upside.
* **a position QID outside the gazetteer** — anything else is `unresolved`, and
  becomes an item-creation candidate rather than a bad statement.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from rigour.territories import lookup_territory

from wd.dossier import Dossier
from wd.gazetteer import Gazetteer

#: Properties a proposal may target. `P21` is here because Wikidata wants it,
#: not because it moves anything downstream: `zavod` reads `P21` nowhere at all
#: (`research/person_items.md` §2), so a gender lane must be sized and reported
#: as a Wikidata-quality lane.
PROPERTIES = ["P39", "P569", "P27", "P21"]

GENDERS = {
    "male": "Q6581097",
    "female": "Q6581072",
    "non-binary": "Q48270",
    "trans woman": "Q1052281",
    "trans man": "Q2449503",
}

#: Partial ISO. Year precision is acceptable — most rosters give no more, and a
#: year is what rescues an undated tenure just as well as a day.
ISO_DATE = re.compile(r"^\d{3,4}(-\d{2}(-\d{2})?)?$")

NULLABLE = {"anyOf": [{"type": "string"}, {"type": "null"}]}

#: `anyOf` rather than a nullable type, and every field `required`: structured
#: outputs express absence as an explicit null, never as an omitted key.
PROPOSAL_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "property": {"type": "string", "enum": PROPERTIES},
        "position_qid": NULLABLE,
        "office_name": NULLABLE,
        "value": NULLABLE,
        "start": NULLABLE,
        "end": NULLABLE,
        "acting": {"type": "boolean"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "quote": {"type": "string"},
        "source": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": ["property", "position_qid", "office_name", "value", "start",
                 "end", "acting", "confidence", "quote", "source", "reason"],
    "additionalProperties": False,
}

VERDICT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "qid": {"type": "string"},
        "label": {"type": "string"},
        "proposals": {"type": "array", "items": PROPOSAL_SCHEMA},
        "notes": {"type": "string"},
    },
    "required": ["qid", "label", "proposals", "notes"],
    "additionalProperties": False,
}


@dataclass
class Checked:
    """One proposal, and what the mechanical channel made of it."""

    qid: str
    proposal: Dict[str, Any]
    #: Everything true about this proposal, for `wd/policy.py` to rule on.
    flags: List[str] = field(default_factory=list)
    #: Why it cannot be applied, if it cannot. Empty means every check passed.
    failures: List[str] = field(default_factory=list)
    #: The resolved value: a QID for P27/P21, a normalised date for P569.
    resolved: Optional[str] = None

    @property
    def ok(self) -> bool:
        return not self.failures

    def as_dict(self) -> Dict[str, Any]:
        return {
            "qid": self.qid, "flags": sorted(self.flags),
            "failures": sorted(self.failures), "resolved": self.resolved,
            **self.proposal,
        }


def _dates_ok(proposal: Dict[str, Any], flags: List[str]) -> List[str]:
    bad = []
    start, end = proposal.get("start"), proposal.get("end")
    for name, value in (("start", start), ("end", end)):
        if value and not ISO_DATE.match(value):
            bad.append(f"malformed_{name}")
    if start and end and ISO_DATE.match(start) and ISO_DATE.match(end):
        # Compare at the precision they share: a year-precision end must not be
        # read as January 1st and lose to a day-precision start in its own year.
        span = min(len(start), len(end))
        if start[:span] > end[:span]:
            bad.append("start_after_end")
    if not start and not end:
        flags.append("undated")
    return bad


def _tenure_recorded(
    proposal: Dict[str, Any], recorded: Sequence[Dict[str, Any]]
) -> bool:
    """Is this tenure already on the item? Compared at shared precision."""
    for tenure in recorded:
        if tenure.get("position") != proposal.get("position_qid"):
            continue
        for key in ("start", "end"):
            new, old = proposal.get(key), tenure.get(key)
            if new and old:
                span = min(len(new), len(old))
                if new[:span] != old[:span]:
                    break
        else:
            return True
    return False


def check(
    verdict: Dict[str, Any],
    dossier: Dossier,
    gazetteer: Gazetteer,
    *,
    recorded: Optional[Sequence[Dict[str, Any]]] = None,
) -> List[Checked]:
    """Run every mechanical check over one person's proposals.

    `recorded` defaults to the tenures the dossier discloses. Pass the unhidden
    list in backtest mode, where the dossier deliberately withholds them.
    """
    qid = verdict.get("qid", "")
    if recorded is None:
        recorded = dossier.item.get("tenures") or []
    out: List[Checked] = []
    for proposal in verdict.get("proposals") or []:
        result = Checked(qid=qid, proposal=proposal)
        flags, failures = result.flags, result.failures

        # 1. The quote. Cheapest, strongest, and first: a proposal whose
        #    evidence is not in the evidence has nothing else worth checking.
        if dossier.contains(proposal.get("quote") or ""):
            flags.append("quote_verified")
        else:
            failures.append("quote_not_in_evidence")

        prop = proposal.get("property")
        if prop == "P39":
            target = proposal.get("position_qid")
            if not target:
                # Not a failure: an office with no item is the creation queue,
                # which is the point of asking rather than letting it guess.
                flags.append("office_unresolved")
                if not (proposal.get("office_name") or "").strip():
                    failures.append("unresolved_without_a_name")
            elif target in gazetteer:
                flags.append("gazetteer_hit")
            else:
                failures.append("position_not_in_gazetteer")
            failures.extend(_dates_ok(proposal, flags))
            if target and _tenure_recorded(proposal, recorded):
                flags.append("already_recorded")
                failures.append("already_recorded")
            if proposal.get("acting"):
                flags.append("acting")
            entry = next((e for e in gazetteer.entries if e.qid == target), None)
            if entry and proposal.get("start") and entry.inception:
                if proposal["start"][:4] < entry.inception:
                    # `wd/precedent.py` decides whether an early term belongs
                    # from the item's own record; this only catches a term before
                    # the office existed at all.
                    failures.append("starts_before_inception")

        elif prop == "P569":
            value = proposal.get("value") or ""
            if not ISO_DATE.match(value):
                failures.append("malformed_date")
            elif value.endswith("-01-01"):
                # `value.py:65`: bots write Jan 1 for year-precision imports, so
                # a day-precise January 1st is read back as a year anyway.
                failures.append("january_first_placeholder")
            else:
                result.resolved = value
            evidence = dossier.birth_evidence
            # The measured two-channel gate: the infobox microformat against the
            # article's own births category, maintained by different editors.
            if evidence is not None and evidence.verdict == "batch":
                flags.append("dob_two_channel")
                if evidence.value and result.resolved:
                    span = min(len(evidence.value), len(result.resolved))
                    if evidence.value[:span] != result.resolved[:span]:
                        failures.append("dob_disagrees_with_infobox")
            else:
                failures.append("dob_one_channel")
            if dossier.item.get("birth_date"):
                failures.append("already_recorded")

        elif prop == "P27":
            named = (proposal.get("value") or "").strip()
            territory = lookup_territory(named, fuzzy=True) if named else None
            if territory is None or not territory.qid:
                failures.append("country_unresolved")
            else:
                result.resolved = territory.qid
                flags.append("country_resolved")
                if result.resolved in (dossier.item.get("citizenship") or []):
                    failures.append("already_recorded")

        elif prop == "P21":
            key = (proposal.get("value") or "").strip().casefold()
            if key in GENDERS:
                result.resolved = GENDERS[key]
                # Recorded for honesty, not as a defect: nothing in `zavod`
                # reads P21, so this can only ever be a Wikidata-quality gain.
                flags.append("wikidata_only")
            else:
                failures.append("gender_unrecognised")
            if dossier.item.get("gender"):
                failures.append("already_recorded")

        if proposal.get("confidence") == "low":
            flags.append("low_confidence")
        out.append(result)
    return out


def unresolved_offices(checks: Sequence[Checked]) -> List[Dict[str, Any]]:
    """The offices the evidence named and the gazetteer did not hold.

    This is the second pass's input, and the reason a missing office produces a
    creation candidate rather than a guessed QID. Unlike the ~150 offices nine
    campaigns listed for creation and never minted, each of these arrives with
    an attested holder, a date and a quote.
    """
    return [
        {
            "office_name": c.proposal.get("office_name"),
            "holder": c.qid,
            "start": c.proposal.get("start"),
            "end": c.proposal.get("end"),
            "quote": c.proposal.get("quote"),
            "source": c.proposal.get("source"),
        }
        for c in checks
        if "office_unresolved" in c.flags and c.ok
    ]


def flag_summary(checks: Sequence[Checked]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for c in checks:
        for name in c.flags + [f"FAIL:{f}" for f in c.failures]:
            counts[name] = counts.get(name, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


__all__ = [
    "Checked", "GENDERS", "PROPERTIES", "PROPOSAL_SCHEMA", "VERDICT_SCHEMA",
    "check", "flag_summary", "unresolved_offices",
]
