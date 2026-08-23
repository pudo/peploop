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
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from rigour.territories import lookup_territory

from wd.api import claim_qids, fetch_entities
from wd.dossier import Dossier
from wd.gazetteer import Gazetteer
from wd.positions import lookup_position
from wd.policy import ENRICH_RULES, Candidate, Facts, decide
from wd.record import Decision, Record, Signal, Snak, Statement, Subject, Value

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
        #: Named, never a QID — matched against the qualifier sets afterwards.
        "district": NULLABLE,
        "group": NULLABLE,
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "quote": {"type": "string"},
        "source": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": ["property", "position_qid", "office_name", "value", "start",
                 "end", "acting", "district", "group", "confidence", "quote",
                 "source", "reason"],
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
    #: Extra P39 qualifiers whose named value matched a closed set.
    qualifiers: Dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.failures

    def as_dict(self) -> Dict[str, Any]:
        return {
            "qid": self.qid, "flags": sorted(self.flags),
            "failures": sorted(self.failures), "resolved": self.resolved,
            "qualifiers": dict(self.qualifiers),
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


def _tenure_state(
    proposal: Dict[str, Any], recorded: Sequence[Dict[str, Any]]
) -> str:
    """How this proposal stands against what the item records for the office.

    Three outcomes, and the middle one is the whole point of the loop:

    * `recorded` — the same office over the same span, compared at the precision
      the two share. Nothing to do.
    * `undated` — the office is on the item with **no dates at all**, and the
      proposal has some. Not a duplicate: it is the statement that exists and
      cannot produce an Occupancy, because `zavod` refuses one when nothing is
      dated. 31 of 42 recorded Sejm seats are in this state, and treating them as
      already-recorded suppressed every single fix.
    * `new` — no statement for this office.

    Reading `undated` as `recorded` is the easy bug, because "does every date
    that exists on both sides agree" is trivially true when one side has none.
    """
    dated_proposal = bool(proposal.get("start") or proposal.get("end"))
    undated_match = False
    for tenure in recorded:
        if tenure.get("position") != proposal.get("position_qid"):
            continue
        if not (tenure.get("start") or tenure.get("end")):
            if not dated_proposal:
                return "recorded"    # undated both sides: nothing to add
            undated_match = True
            continue
        for key in ("start", "end"):
            new, old = proposal.get(key), tenure.get(key)
            if new and old:
                span = min(len(new), len(old))
                if new[:span] != old[:span]:
                    break
            elif new or old:
                # One side dates this bound and the other does not. Not the same
                # span; a coarser record is handled by the shared-precision
                # comparison above, an absent bound is a different tenure.
                break
        else:
            return "recorded"
    return "undated" if undated_match else "new"


def check(
    verdict: Dict[str, Any],
    dossier: Dossier,
    gazetteer: Gazetteer,
    *,
    recorded: Optional[Sequence[Dict[str, Any]]] = None,
    resolved: Optional[Dict[str, str]] = None,
    qualifiers: Optional[Dict[str, Gazetteer]] = None,
) -> List[Checked]:
    """Run every mechanical check over one person's proposals.

    `recorded` defaults to the tenures the dossier discloses. Pass the unhidden
    list in backtest mode, where the dossier deliberately withholds them.

    `resolved` maps an office *name* the model reported to the QID
    `wd/positions.py:lookup_position` found for it. A single-target gazetteer
    makes every other office the person held read as unresolved by construction
    — "Senator of the Republic of Poland" plainly has an item — so a second
    mechanical pass places them. `lookup_position` is itself two-signal (a label
    variant must match *and* the item's own P17/P1001 must resolve to the
    country), which is why a match here is allowed to become a statement rather
    than a review row.
    """
    resolved = resolved or {}
    # Label -> QID per qualifier property, folded so a case or spacing
    # difference does not silently drop a correct value.
    qualifier_index: Dict[str, Dict[str, str]] = {}
    for prop, qualifier_set in (qualifiers or {}).items():
        index: Dict[str, str] = {}
        for entry in qualifier_set.entries:
            for text in [entry.label, *entry.aliases]:
                if text:
                    index.setdefault(" ".join(text.split()).casefold(), entry.qid)
        qualifier_index[prop] = index
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
                named = (proposal.get("office_name") or "").strip()
                if named in resolved:
                    target = resolved[named]
                    flags.append("office_resolved")
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
            for field, prop in (("district", "P768"), ("group", "P4100")):
                named = " ".join((proposal.get(field) or "").split()).casefold()
                if not named:
                    continue
                found = qualifier_index.get(prop, {}).get(named)
                if found:
                    result.qualifiers[prop] = found
                    flags.append(f"{field}_resolved")
                else:
                    flags.append(f"{field}_unmatched")
            failures.extend(_dates_ok(proposal, flags))
            state = _tenure_state(proposal, recorded) if target else "new"
            if state == "recorded":
                # Already there is not the end of it: the statement may say
                # nothing about the constituency or the caucus, and QuickStatements
                # merges a qualifier into the statement it finds. Only safe when
                # there is exactly one statement for the office — with two, QS has
                # no way to know which one the qualifier belongs to.
                on_target = [t for t in recorded
                             if t.get("position") == proposal.get("position_qid")]
                have = set(on_target[0].get("qualifiers") or []) if on_target else set()
                adding = set(result.qualifiers) - have
                if adding and len(on_target) == 1:
                    flags.append("qualifies_existing_statement")
                elif adding:
                    flags.append("ambiguous_merge_target")
                    failures.append("already_recorded")
                else:
                    flags.append("already_recorded")
                    failures.append("already_recorded")
            elif state == "undated":
                # QuickStatements matches on subject, property and value, so a
                # dated line merges its qualifiers into the statement already
                # there — which is exactly right for *one* undated statement and
                # exactly wrong for several, hence `several_terms` below.
                flags.append("undated_statement")
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
            # The two-channel gate, with the channels this pipeline actually
            # has. `scripts/harvest_dob.py` pairs the infobox microformat with
            # the article's births category — but outside enwiki the infobox
            # channel is simply absent: `worth_rendering` is False for pl, de,
            # fr and cs because those wikis state the date in prose instead, so
            # that pair can never both exist and the lane was English-only.
            #
            # Here channel one is the model reading that prose, under a verbatim
            # quote, which is the case `tasks/birthdates.md` lists as left on the
            # table. Channel two stays the births category, maintained by
            # different editors and now localised for eleven wikis. The infobox
            # is a third channel when it exists, and a contradiction from it
            # still stops the proposal.
            evidence = dossier.birth_evidence
            years = set(evidence.categories) if evidence else set()
            if evidence is not None and evidence.category_uncertain:
                failures.append("dob_category_flagged_uncertain")
            if result.resolved and years:
                if result.resolved[:4] in years:
                    flags.append("dob_two_channel")
                    if evidence and evidence.value:
                        span = min(len(evidence.value), len(result.resolved))
                        if evidence.value[:span] == result.resolved[:span]:
                            flags.append("dob_infobox_agrees")
                        else:
                            failures.append("dob_disagrees_with_infobox")
                else:
                    failures.append("dob_disagrees_with_category")
            else:
                failures.append("dob_no_cross_check")
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

    # One undated statement cannot absorb several dated terms: QuickStatements
    # would merge them all into it, leaving one statement carrying every start
    # and every end with nothing pairing them up — the Q1368615 shape. Adding
    # them through the API instead leaves the undated statement in place beside
    # the new ones, so the undated one has to be removed, and removal is a human
    # gate. Mark the class rather than guessing.
    per_office: Dict[str, int] = {}
    for c in out:
        if "undated_statement" in c.flags:
            key = c.proposal.get("position_qid") or ""
            per_office[key] = per_office.get(key, 0) + 1
    for c in out:
        if ("undated_statement" in c.flags
                and per_office.get(c.proposal.get("position_qid") or "", 0) > 1):
            c.flags.append("several_terms")
    return out


#: Which `.qs` concern a property belongs to. `render_edit_plan.py` groups the
#: review document by it; the batch itself is one file.
CONCERNS = {"P39": "p39", "P569": "dob", "P27": "citizenship", "P21": "gender"}

#: A Wikipedia permalink is an *import*, not a source. `S4656` (Wikimedia import
#: URL) is where it goes; `S854` reference URL is for a real citation, and a
#: linter rightly rejects a wiki URL there.
IMPORT_URL = "S4656"


def _statement(checked: Checked, url: Optional[str]) -> Optional[Statement]:
    """One proposal as a statement, with its own qualifiers and references."""
    proposal = checked.proposal
    prop = proposal.get("property")
    if prop == "P39":
        # No QID means there is nothing to assert. An office named in prose is a
        # byproduct, and a statement whose value is absent would render as
        # `{"type": "item"}` — malformed, and only visible once it reached a
        # batch.
        if not proposal.get("position_qid"):
            return None
        value = Value.item(proposal["position_qid"])
    elif prop == "P569":
        if not checked.resolved:
            return None
        value = Value.time(checked.resolved)
    elif prop in ("P27", "P21"):
        if not checked.resolved:
            return None
        value = Value.item(checked.resolved)
    else:
        return None

    qualifiers: List[Snak] = []
    if prop == "P39":
        if proposal.get("start"):
            qualifiers.append(Snak("P580", Value.time(proposal["start"])))
        if proposal.get("end"):
            qualifiers.append(Snak("P582", Value.time(proposal["end"])))
        # Not `prop`: that is the statement's own property, and rebinding it
        # here rendered a P39 line whose property column said P768.
        for qual_prop, qual_qid in sorted(checked.qualifiers.items()):
            qualifiers.append(Snak(qual_prop, Value.item(qual_qid)))
    references = [Snak(IMPORT_URL, Value.url(url))] if url else []
    return Statement(prop, value, qualifiers=qualifiers, references=references,
                     # The source named a start and no end, rather than not
                     # offering one — `wd/validate.py` reads the difference.
                     end_withheld=bool(proposal.get("start")
                                       and not proposal.get("end")))


def records(
    spec_key: str,
    dossier: Dossier,
    checks: Sequence[Checked],
    *,
    campaign: str,
) -> List[Record]:
    """Turn one person's checked proposals into edit records.

    One record per proposal, so every one carries the rule that decided it and
    the review document is an account rather than a queue. A person's several
    tenures in one office therefore arrive as several records — which is exactly
    the shape `render_edit_plan.py` partitions into `edit_plan_claims.json`,
    because QuickStatements would merge them into one statement carrying every
    start and every end with nothing pairing them up.
    """
    urls = {f.source: f.url for f in dossier.fragments}
    out: List[Record] = []
    for checked in checks:
        proposal = checked.proposal
        flags = list(checked.flags) + [f"fail_{f}" for f in checked.failures]
        ruling = decide(
            Candidate(
                qid=checked.qid,
                target=proposal.get("position_qid") or "",
                flags=tuple(flags),
                identity="quote",
                office=spec_key,
            ),
            Facts(),
            rules=ENRICH_RULES,
        )
        statement = _statement(checked, urls.get(proposal.get("source") or ""))
        if statement is not None:
            for prop, qid in ruling.qualifiers.items():
                statement.qualifiers.append(Snak(prop, Value.item(qid)))
        byproduct = None
        if ruling.disposition == "byproduct":
            byproduct = {
                "office_name": proposal.get("office_name"),
                "holder": checked.qid,
                "start": proposal.get("start"),
                "end": proposal.get("end"),
                "quote": proposal.get("quote"),
            }
        out.append(Record(
            campaign=campaign,
            subject=Subject(qid=checked.qid, label=dossier.label or checked.qid),
            statements=[statement] if statement is not None else [],
            decision=Decision(
                action=ruling.disposition,
                rule=ruling.rule,
                source=ruling.source,
                concern=CONCERNS.get(proposal.get("property") or "", "other"),
                rationale=ruling.rationale,
            ),
            office=spec_key,
            identity={"channel": "quote", "source": proposal.get("source")},
            flags=flags,
            signals=[Signal(
                channel=proposal.get("source") or "dossier",
                supports=proposal.get("property") or "",
                detail=(proposal.get("quote") or "")[:300],
                source_url=urls.get(proposal.get("source") or ""),
            )],
            notes=proposal.get("reason") or "",
            byproduct=byproduct,
        ))
    return out


def name_variants(name: str) -> Tuple[str, Tuple[str, ...]]:
    """Split an office name into a primary query and its alternatives.

    A model writing for a reader disambiguates, and the disambiguation is what
    breaks a label search: it reports "Minister of Education and Science
    (Poland)" and "Deputy Voivode of Łódź Voivodeship (wicewojewoda łódzki)".
    Sixty-one of Poland's sixty-four names went unmatched, and the parenthetical
    is the first reason.

    The parenthetical is also frequently the *native* name, which is often the
    better query: Wikidata labels a Polish office in Polish and carries the
    English only as an alias, if at all. So both halves are tried, the stripped
    form first.
    """
    inner = tuple(
        m.strip() for m in re.findall(r"\(([^)]+)\)", name)
        # A parenthetical that is just a country is a disambiguator, not a name:
        # "(Poland)" would be searched as the country itself.
        if m.strip() and lookup_territory(m.strip(), fuzzy=True) is None
    )
    stripped = re.sub(r"\s*\([^)]*\)", "", name).strip()
    primary = stripped or name
    extras = tuple(dict.fromkeys(x for x in (name, *inner) if x and x != primary))
    return primary, extras


def resolve_offices(
    session: Any,
    names: Sequence[str],
    country: Optional[str],
    *,
    log: Callable[[str], None] = lambda _m: None,
) -> Dict[str, Dict[str, Any]]:
    """Place the office names a run could not offer an item for.

    Returns one entry per distinct name: its `lookup_position` status, the QID
    when it resolved, and the candidates when it did not. Only `matched`
    entries become statements — `label-only` and `ambiguous` are the cases the
    two-signal gate declined, and forcing them would be exactly the padding this
    workbench refuses. `unmatched` is the genuine creation list.

    Deduplicated by name because a category's members hold the same handful of
    other offices: Poland's 106 people named 67 offices between them, and the
    Senate seat alone accounts for several.
    """
    out: Dict[str, Dict[str, Any]] = {}
    for name in sorted({n.strip() for n in names if n and n.strip()}):
        primary, extras = name_variants(name)
        try:
            lookup = lookup_position(session, primary, country, extra_names=extras)
        except Exception as exc:      # one bad name must not end the pass
            log(f"  lookup failed for {name!r}: {exc}")
            continue
        status, qid = lookup.status, lookup.resolved_qid
        if status == "matched" and qid:
            # `lookup_position`'s country gate accepts a `P17` alone, which lets a
            # *generic* office class through: "Mayor (wójt) of Świlcza" matched
            # `Q98637505 wójt`, the Polish administrative rank, P17=Poland and no
            # P1001 at all. Writing a specific village mayoralty onto that is the
            # generic-occupation trap, and `recipes/position_items.md` calls an
            # office scoped to no polity a defect — so a match has to name the
            # polity it governs before it may become a statement.
            entity = fetch_entities(session, [qid], props="claims").get(qid) or {}
            if not claim_qids(entity, "P1001"):
                status, qid = "no-polity", None
        out[name] = {
            "status": status,
            "qid": qid,
            "candidates": [
                {"qid": c.qid, "label": c.label, "label_match": c.label_match,
                 "country_match": c.country_match}
                for c in lookup.candidates[:4]
            ],
        }
        log(f"  {status:11} {name[:56]:58} {qid or ''}")
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
    "Checked", "CONCERNS", "GENDERS", "PROPERTIES", "PROPOSAL_SCHEMA",
    "VERDICT_SCHEMA", "check", "flag_summary", "records", "unresolved_offices",
]
