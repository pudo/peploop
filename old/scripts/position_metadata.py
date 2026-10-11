"""Audit how a country's position items are modelled, and propose the fixes.

Run this at phase A of a sweep, before scoping a roster lane. It reports Wikidata
modelling defects — an occupation typed as an office, an office scoped to no
polity, an office that says "position" and never says what kind — each worth
fixing on its own terms. `recipes/position_items.md` is the method.

Whether a downstream reader currently emits an item is reported separately as
notes, never as a defect.

    python scripts/position_metadata.py --country lt
    python scripts/position_metadata.py --country lt --calibrate

`--calibrate` checks each verdict against a live `yente-cli fetch`, which is the
only regression net this reader has. Read a disagreement as no-holders first, the
review layer second, a port bug third.
"""

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from wd.api import best_label, claim_qids, fetch_entities, sparql  # noqa: E402
from wd.shape import (  # noqa: E402
    COUNTRY_PROPS, FALLBACK_PROPS, _country_of as country_of, type_closure,
    verify_all,
)
from wd.positions import holder_counts  # noqa: E402
from wd.validate import check  # noqa: E402
from wd.http import get_text, make_session  # noqa: E402
from wd.record import (  # noqa: E402
    Decision, Record, Signal, Statement, Subject, Value, dumps,
)

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
POSITION_CLASS = "Q4164871"

#: Countries this script knows how to scope. Each names the country item and the
#: label fragments that admit an item with no country path at all — which is the
#: ordering problem at the centre of the audit: "has no country" cannot also be
#: the membership test, so the label channel is what lets such an item in.
COUNTRIES: Dict[str, Dict[str, object]] = {
    "lt": {
        "qid": "Q37",
        "name": "Lithuania",
        "campaign": "lithuania",
        # CirrusSearch terms, not regex stems: "lithuan" is not a word and
        # matches nothing, which silently cost this audit the four apex-court
        # presidencies — the highest-value items in it — on the first run.
        "search_terms": ("Lithuania", "Lithuanian", "Lietuvos", "Seimas"),
    },
    # Persian hints as well as English: many Iranian position items carry an
    # `fa` label and no `en` one, and the label channel exists for exactly the
    # items the country channels miss.
    "ir": {
        "qid": "Q794",
        "name": "Iran",
        "campaign": "iran",
        "search_terms": ("Iran", "Iranian", "Persia", "Majlis", "ایران", "استاندار"),
    },
    # The Gulf trio. Each names its emirates as well as the state, because a
    # ruler item is scoped to the emirate and reaches the federal country
    # channel only through `P17` — and a sub-national office that never got one
    # is exactly what this audit is for. Arabic hints for the same reason as
    # Iran's: the item with no `en` label is the item the country channels miss.
    "ae": {
        "qid": "Q878",
        "name": "United Arab Emirates",
        "campaign": "uae",
        "search_terms": (
            "United Arab Emirates", "Emirati", "Abu Dhabi", "Dubai",
            "Sharjah", "Ajman", "Fujairah", "Khaimah", "Quwain",
            "الإمارات", "أبوظبي",
        ),
    },
    "qa": {
        "qid": "Q846",
        "name": "Qatar",
        "campaign": "qatar",
        "search_terms": ("Qatar", "Qatari", "Shura Council", "قطر"),
    },
    "iq": {
        "qid": "Q796",
        "name": "Iraq",
        "campaign": "iraq",
        "search_terms": ("Iraq", "Iraqi", "Baghdad", "Kurdistan Region",
                         "العراق"),
    },
    # Czechoslovakia and the Protectorate are the point of including their names:
    # an office of a dissolved federation resolves to no modern country, which is
    # correct, and the label channel is the only way an audit scoped to Czechia
    # ever sees one. Expect `absent` rows, not backfills.
    "cz": {
        "qid": "Q213",
        "name": "Czechia",
        "campaign": "czechia",
        "search_terms": ("Czech", "Czechia", "Czechoslovakia", "Bohemia",
                         "Moravia", "Prague"),
    },
    # `Byelorussian` for the SSR-era items, same reason.
    "by": {
        "qid": "Q184",
        "name": "Belarus",
        "campaign": "belarus",
        "search_terms": ("Belarus", "Belarusian", "Byelorussian", "Minsk",
                         "Беларусі"),
    },
    # `Hejaz` and `Nejd` reach the pre-1932 kingdoms, which are their own polities
    # and must not acquire a modern `P17`.
    "sa": {
        "qid": "Q851",
        "name": "Saudi Arabia",
        "campaign": "saudi",
        "search_terms": ("Saudi", "Saudi Arabia", "Riyadh", "Hejaz", "Nejd",
                         "السعودية"),
    },
    # No campaign has ever run on Bahrain — `coverage/README.md` has no BH
    # column. This entry makes the phase-A census runnable, and `campaign` names
    # the directory a future sweep would use.
  "bh": {
        "qid": "Q398",
        "name": "Bahrain",
        "campaign": "bahrain",
        "search_terms": ("Bahrain", "Bahraini", "البحرين"),
    },
}

#: Decided per office against the measured convention: every parent below is in
#: live use as a `P279` on real position items (counts taken 2026-08-19).
#:
#: Chosen because it *describes the office*, never to trip `wd.shape`'s PEP
#: sentinel. That ordering matters: typing a district judgeship as a supreme
#: court judge would flip the sentinel and corrupt the data to do it. Where the
#: honest parent does not set the default — `Q16533` judge, `Q14212` prime
#: minister — the gap is reported upstream and the parent stays honest.
PARENTS_BY_COUNTRY: Dict[str, Dict[str, Tuple[str, str]]] = {
  "lt": {
    "Q131824331": ("Q117826617", "apex court presidency — supreme court judge"),
    "Q133090275": ("Q117826617", "apex court presidency — supreme court judge"),
    "Q131824524": ("Q117826617", "final-instance court presidency"),
    "Q131807424": ("Q117826617", "constitutional court presidency"),
    "Q132891425": ("Q108290289", "judicial governance body, not a court"),
    "Q133190264": ("Q108290289", "parliamentary leadership"),
    # WITHDRAWN 2026-08-19. The item already carried `P279 = Q1758037` speaker,
    # which is the convention at 84 of 96 typed speakerships. `Q108290289` was
    # added because it sets the reader's PEP default and for no other reason —
    # the thing `recipes/position_items.md` forbids. Removal is on the surgical
    # list; `Q1758037` not conferring is an upstream issue, not a parent to swap.
    # "Q12663218": ("Q108290289", "parliamentary leadership"),
    "Q140916310": ("Q108290289", "agency headship"),
    "Q132068652": ("Q3368517", "public prosecutor general"),
    "Q55607326": ("Q707492", "military chief of staff"),
    "Q5177800": ("Q132050", "governor"),
  },
  # Iran, measured 2026-08-19 by tallying `P279` over every position item whose
  # en label matches the office's class. Each share is that tally; only classes
  # with a clear winner are here. Council seats and secretaryships, deputy
  # speakerships, unit commands and spokesmanships were measured and came back
  # split — they stay untyped in the ledger with the tally as the reason, rather
  # than take a parent this run invented.
  "ir": {
    "Q2660216": ("Q42178", "vice president — 76 of 81"),
    "Q20987826": ("Q17578116", "interior minister — 25 of 31"),
    "Q115625149": ("Q83307", "minister; the general class, 380 in use"),
    "Q6597965": ("Q1758037", "speaker of a chamber — 62 of 69"),
    "Q5719341": ("Q380782", "commander-in-chief — 9 of 12"),
    "Q113337481": ("Q5784340", "consort — 34 of 50"),
    "Q107001741": ("Q6501749", "general secretary of a party — 46 of 58"),
    "Q124609039": ("Q1501800", "director general — 27 of 38"),
    "Q137004668": ("Q1501800", "director general — 27 of 38"),
    "Q137005532": ("Q1501800", "director general — 27 of 38"),
    "Q115625244": ("Q26204040", "deputy minister; the generic class, 10 in use"),
    # Not untyped — `Q14212` "prime minister" is already there. The office was
    # Iran's head of government until 1989 and the class that says so is absent.
    "Q13561063": ("Q2285706", "head of government, beside its existing Q14212"),
  },
  # Qatar, the UAE and Bahrain, measured 2026-08-19. The tally is a CirrusSearch
  # sweep of `haswbstatement:P31=Q4164871 <office name>` with `P279` counted off
  # the fetched entities, per `recipes/country_sweep.md` §10 — a WDQS statement-node
  # scan over every position item answers 504, which is the documented gotcha and
  # not a query worth retrying.
  "qa": {
    "Q108861091": ("Q83307", "minister; the general class, 380 in use"),
  },
  "ae": {
    # Split 1:1 between `Q42178` vice president and `Q3250324` deputy across the
    # only two "Deputy Ruler of …" items that exist. `recipes/position_items.md`
    # already ruled on this exact tie for `deputy_ruler` and picked the deputy.
    "Q125497761": ("Q3250324", "deputy ruler; the two items disagree 1:1 and the "
                               "recipe's deputy_ruler already broke the tie"),
    # The three consular posts left untyped are Malaysia's, France's and
    # Indonesia's, not the UAE's to model. They are reported, never written.
  },
  "bh": {
    # 71 of 149 "King of …" items, against `Q116` monarch 20 and `Q48352` head of
    # state 6. The recipe's `head_of_state` archetype is for *minting*; this item
    # exists, and the convention on an existing kingship is the narrower class.
    "Q726872": ("Q12097", "king — 71 of 149, the clear winner"),
    # 11 of the 36 "Commander-in-Chief of …" items that carry any P279, matching
    # Iran's independently-measured 9 of 12. Twenty carry none at all.
    "Q130535612": ("Q380782", "commander-in-chief — 11 of 36, and 9 of 12 in Iran"),
    # `Q16533` judge on 6 of 7, and deliberately the generic judgeship rather than
    # `Q117826617` supreme court judge: Bahrain's apex is the Court of Cassation,
    # so a sharia court of appeal is high but not the national apex, and §10 rule 3
    # says under-claim on a thin sample rather than pick a side.
    "Q127876951": ("Q16533", "judgeship — 6 of 7 apex appellate items"),
    "Q125693554": ("Q207293", "crown prince; the class every Gulf heir item uses"),
  },
}

#: Items typed as positions that are not offices at all, or that duplicate one.
#: These never enter a batch: retyping and merging are destructive-adjacent and
#: belong on the wikibase-cli list in `tasks/followups.md`.
SURGICAL_BY_COUNTRY: Dict[str, Dict[str, str]] = {
  "lt": {
    "Q114059276": "occupation ('lithuanist'), not a position — retype",
    "Q101540148": "occupation ('Lithuanian teacher'), not a position — retype",
    "Q258874": "folk-craft occupation ('dievdirbys'), not a position — retype",
    "Q565077": "military rank ('flotilla admiral'), not a position — retype",
    "Q12663357": "a body (P31=Q495430), not a position — retype",
    "Q139379876": "basketball league presidency, not a public office — retype",
    "Q63994897": "no en label, duplicates Grand Duke of Lithuania — merge",
    "Q132476998": "duplicates Q12661306 Minister of National Defence — merge",
    "Q132861229": "duplicates Q107735740 Minister of Transport — merge",
  },
  "ir": {
    "Q80934037": "military rank ('second brigadier general of IRGC') — retype",
    "Q80930817": "military rank ('brigadier general of IRGC') — retype",
    "Q80930670": "military rank ('second brigadier general') — retype",
    "Q49920382": "a Wikimedia category, not a position — retype",
    "Q49920381": "a Wikimedia category, not a position — retype",
    "Q4875094": "social class ('Bazaari'), not a position — retype",
    "Q2671576": "occupation ('Bakshy', a musician), not a position — retype",
    "Q113641745": "military rank ('Daryabegi'), not a position — retype",
    "Q106960625": "duplicates Q107391283 First Vice Chief Justice — merge",
    # Dual-typed. Adding its `P279` is additive and is in the batch; removing
    # the list-article `P31` is not, and is why it appears in both places.
    "Q6597965": "also typed Q13406463 Wikimedia list article — drop that P31",
    "Q107288100": "probably duplicates Q118321724 Deputy Speaker, which holds "
                  "the fawiki sitelink — the two name different bodies in P361, "
                  "so a human decides",
    # Both added 2026-08-19, both found by eyeballing the batch rather than by a
    # check, and both keep a statement *out* of it.
    #
    # A mediaeval Seljuk title, `P31` naming noble title / khan / sultan and
    # `P1001` already naming two polities (Iran and Georgia). The gap tier offered
    # it a single `P17 = Iran`, which is the `flotilla admiral` error — on a title
    # `P17` means "used by these countries", so collapsing two to one is a wrong
    # statement, not a missing one.
    "Q174506": "mediaeval title used across several polities (P1001 already names "
               "Iran and Georgia) — never a single P17; needs retyping",
    # `P31 = Q4164871` and nothing else, and its own description says it is the
    # Presidential Administration — a body and its staff, not a seat. Same shape
    # as Q5942489, which `NOT_AN_OFFICE` now catches by class; this one declares
    # only the metaclass, so no class test can reach it.
    "Q16074706": "the Presidential Administration, a body rather than a seat in "
                 "one — retype; not an office to give jurisdiction to",
  },
  "ae": {
    # Same office, same era, same P1001, same P279. A merge, not a backfill:
    # adding metadata to the empty twin entrenches the duplicate.
    "Q30635458": "duplicates Q125497760 Crown Prince of Dubai, which holds the "
                 "only holder — merge, and the surviving item keeps the P31 "
                 "Q355567 noble title question for the same human",
  },
  # Added 2026-08-19 from eyeballing the four batches. Each one is an item whose
  # only country evidence is a jurisdiction claim that is itself wrong, so no rule
  # reading the item can tell: the label names no country, and the wrong claim is
  # the thing a rule would trust. Removing a claim is destructive, hence here.
  "sa": {
    "Q19810880": "the generic class 'deputy crown prince', wrongly scoped by a "
                 "P1001 to Saudi Arabia — the class is used by several monarchies, "
                 "so the fix is removing that P1001, not adding a matching P17",
    "Q17005012": "Afghanistan's Attorney General's Office — a body, another "
                 "country's, and carrying a P1001 to Saudi Arabia that is simply "
                 "wrong; it reached this audit through that claim",
  },
  "cz": {
    "Q19602879": "the generic class 'zastupitel' (councillor), wrongly scoped by a "
                 "P1001 to Czechia — same shape as Q19810880",
  },
  "iq": {
    "Q139552348": "'Territory of the Islamic State of Iraq' is a territory, not an "
                  "office — retype",
    "Q106695366": "leadership of a proscribed armed group, not an office of the "
                  "Iraqi state; its P17 already says Iraq and a P1001 would assert "
                  "the state's jurisdiction over it — a human decides",
  },
  "bh": {
    # A 7th-century Rashidun/Umayyad governorship: its holders are Abu Hurairah
    # and Marwan I, dated 634-662, and its P17 is `Q4165357` Eastern Arabia.
    #
    # On the surgical list specifically to keep it *out* of the batch. It is
    # untyped and its label ends "of Bahrain", so the national-office rule offered
    # it `P1001 = Kingdom of Bahrain` — a modern state asserted onto a mediaeval
    # office, which is the wrong statement the recipe says hides in the safest-
    # looking lane. `wd.shape`'s historical suppression cannot catch it either:
    # Eastern Arabia spans seven modern states and is absent from `SKIP_PLACES`,
    # so the item resolves to a country and never looks historical.
    "Q98433836": "7th-century governorship of Eastern Arabia, not an office of "
                 "the modern kingdom — needs P31 Q114962596 historical position "
                 "and a P576, and must never take a modern P1001",
  },
}


#: Gap closers that cannot be derived from the item, named by a **sibling that
#: already carries the value** rather than by the target's QID.
#:
#: `"like:Q110964267"` reads "whatever `P361` the Ruler of Dubai carries". Written
#: with literal QIDs first, and three of the four were wrong: `Q1129582` is the
#: Cook Islands Cup, `Q1136236` is Umkhonto We Sizwe, `Q100135` is an Italian
#: comune. They validated, rendered, and would have gone to Wikidata as the
#: Cabinet of Qatar and the Federal Supreme Council. A QID typed from memory has
#: no second channel at all; a sibling has one by construction, and it is the same
#: evidence the note claims — "six of seven rulers already carry this" becomes the
#: thing the code reads rather than a comment beside a magic number.
#:
#: `P361` names the body a seat sits in and `P2389` the organisation an office
#: runs; neither is inferable from the office item, which is why they are here at
#: all. `P1001` appears only for a *sub-national* office, where the polity governed
#: is not the country — the national case comes off the label instead.
GAP_TARGETS_BY_COUNTRY: Dict[str, Dict[str, Dict[str, str]]] = {
    "qa": {
        # Q110182815 Minister of Energy carries the cabinet; 23 Qatari position
        # items name the same body, which is the convention for a portfolio.
        "Q108861091": {"P361": "like:Q110182815"},
        # Q110183427 Chief of Armed Forces was here with the cabinet as its body
        # and is deliberately not: a service chief is part of the armed forces,
        # not of the council of ministers. The guard passed it — Cabinet of Qatar
        # does resolve to Qatar — which is the reminder that a country-agreement
        # check catches a wrong *item*, never a wrong *claim*. Its P361 stays open.
        # The chamber, not the cabinet: read off the membership item for the same
        # body rather than off a ministry.
        "Q110183297": {"P361": "like:Q21328600"},
    },
    "ae": {
        # Six of the seven emirate rulers already carry the Federal Supreme
        # Council; Abu Dhabi is the one that does not, and six agreeing siblings
        # is the second channel.
        "Q28471402": {"P361": "like:Q110964267"},
        # Q955006 President of the UAE was here with the same body and is
        # deliberately not: the presidency is *elected by* the Federal Supreme
        # Council, not a seat in it. The rulers are members; the president is
        # their office-holder. Its P361 stays open.
        # Deputy Ruler of Abu Dhabi, `نائب حاكم أبو ظبي`: sub-national, so the
        # polity governed is the emirate. Taken from the Crown Prince of Abu
        # Dhabi, the other office scoped to the same emirate.
        "Q125497761": {"P1001": "like:Q125497756"},
    },
    "bh": {},
}

#: A decided target must resolve to the audit's country, or it is not that
#: country's body. The check that catches a mistyped QID, and it cannot be a bare
#: `P17` read: `Q5015550` Cabinet of Qatar carries no `P17` at all and reaches
#: Qatar through `P1001`, exactly as `wd.shape`'s walk does.
def _resolve_sibling(
    session, spec: str, prop: str, entities: Dict[str, Dict]
) -> Optional[str]:
    """The value a sibling item carries for `prop`, or None if it carries no one.

    Refuses a sibling with several values: "the body Ruler of Dubai belongs to" is
    only a second channel while there is exactly one answer.
    """
    if not spec.startswith("like:"):
        return spec
    sibling = spec[len("like:"):]
    entity = entities.get(sibling)
    if entity is None:
        entity = fetch_entities(session, [sibling], max_age=0).get(sibling, {})
    values = claim_qids(entity, prop)
    return values[0] if len(values) == 1 else None


def _country_of_item(session, qid: str) -> Set[str]:
    """FtM country codes an item resolves to, by `wd.shape`'s own walk.

    Reused rather than reimplemented so the guard agrees with the checker: a body
    reaching its country through `P1001` counts, which a bare `P17` read would
    reject — and `Q5015550` Cabinet of Qatar is exactly that item.
    """
    entity = fetch_entities(session, [qid]).get(qid, {})
    got: Set[str] = set()
    for prop in COUNTRY_PROPS + FALLBACK_PROPS:
        for value in claim_qids(entity, prop):
            got |= country_of(session, value, (qid,))
        if got:
            return got
    return got


def _country_names(session, qid: str) -> Set[str]:
    """Every name the country item answers to, for the label channel.

    Aliases matter more than the label here: "United Arab Emirates" is the label
    and "UAE" the alias, and an office item's tail uses either.
    """
    entity = fetch_entities(session, [qid]).get(qid, {})
    names = {
        term["value"].lower()
        for section in ("labels", "aliases")
        for term in _terms(entity.get(section, {}))
    }
    return {n for n in names if n}


def _terms(section: Dict[str, object]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for value in section.values():
        if isinstance(value, list):
            out.extend(v for v in value if isinstance(v, dict))
        elif isinstance(value, dict):
            out.append(value)  # type: ignore[arg-type]
    return out


#: Country names to QIDs, for "does this label name a country other than the one
#: being audited". Built once from `rigour.territories` rather than by search: a
#: CirrusSearch lookup per label would be hundreds of requests, and the question is
#: only ever asked of a tail that already looks like a country name.
_TERRITORY_NAMES: Optional[Dict[str, str]] = None


def _named_country(label: str, session) -> Optional[str]:
    """The QID of a country this label's tail names, if it names one at all."""
    global _TERRITORY_NAMES
    if _TERRITORY_NAMES is None:
        from rigour.territories import get_territories
        _TERRITORY_NAMES = {}
        for territory in get_territories():
            if territory.qid is None or territory.is_historical:
                continue
            for name in (territory.name, territory.full_name):
                if name:
                    _TERRITORY_NAMES.setdefault(name.lower(), territory.qid)
    lowered = label.lower().strip()
    for sep in (" of the ", " of ", " to the ", " to ", " in the ", " in "):
        if sep in lowered:
            tail = lowered.rsplit(sep, 1)[1].strip(" ,.()")
            got = _TERRITORY_NAMES.get(tail) or _TERRITORY_NAMES.get(f"the {tail}")
            if got:
                return got
    return None


def _is_national(label: str, names: Set[str]) -> bool:
    """Does this office's label say it governs the whole country?

    The tail after the last preposition must *equal* a country name — substring
    would fire "Minister of the Interior of the Emirate of Dubai" as national, and
    the whole point of the test is to keep `P1001 = the country` off a
    sub-national office, where the correct target is the emirate.
    """
    lowered = label.lower().strip()
    for sep in (" of the ", " of ", " to the ", " to "):
        if sep in lowered:
            tail = lowered.rsplit(sep, 1)[1].strip(" ,.")
            if tail in names or f"the {tail}" in names:
                return True
    return False


def _end_of(session, entity: Dict[str, object], layer: str) -> Optional[str]:
    """The state at one end of a bilateral posting, read off its own class.

    The recipe measures `P17` on the class layers rather than on the post: among
    `Q29645880`'s 207 subclasses it names the sender 205 times, among
    `Q29645886`'s 264 it names the receiver 262 times. So "ambassador of Qatar to
    France" carries both classes, and each one's `P17` answers for its own end —
    which is a second channel sitting on the item, not an inference from the
    country the audit happens to be scoped to.

    Returns `None` for a post with no class at that end, which is how
    `Q117021447` Permanent Representative to the UN correctly declines to be
    given a receiver: it is a multilateral post and has no receiving state.
    """
    parents = claim_qids(entity, "P279")
    if not parents:
        return None
    closure = type_closure(session, parents)
    classes = fetch_entities(session, parents)
    for parent in parents:
        if layer not in closure.get(parent, set()):
            continue
        values = claim_qids(classes.get(parent, {}), "P17")
        if len(values) == 1:
            return values[0]
    return None


def gap_closers(
    session, code: str, country: Dict[str, object], verdicts,
    entities: Dict[str, Dict],
) -> Dict[str, Dict[str, str]]:
    """Per item, the value that would close each of its gaps.

    Mechanical where the item itself supplies a second channel, decided where it
    cannot. Nothing lands here on the strength of the audit's scope alone: a gap
    with no derivable target and no table entry stays open and is reported, which
    is what keeps a batch from being padded with plausible guesses.
    """
    qid = str(country["qid"])
    decided = GAP_TARGETS_BY_COUNTRY.get(code, {})
    names = _country_names(session, qid)
    out: Dict[str, Dict[str, str]] = {}
    for verdict in verdicts:
        entity = entities.get(verdict.qid, {})
        closers: Dict[str, str] = {}
        for prop, spec in decided.get(verdict.qid, {}).items():
            target = _resolve_sibling(session, spec, prop, entities)
            if target is None:
                print(f"  !! {verdict.qid} {prop}: {spec} names no single value")
                continue
            reached = _country_of_item(session, target)
            if reached and code not in reached:
                # The guard that would have caught the Cook Islands Cup. It tests
                # for a target belonging to *another* country, which is what each
                # of the three mistyped QIDs actually was: Cook Islands, South
                # Africa, Italy. None of them resolved to nothing.
                print(f"  !! {verdict.qid} {prop}: target {target} resolves to "
                      f"{sorted(reached)}, not {code} — refusing it")
                continue
            if not reached:
                # Accepted, and worth saying. `Q5440456` Federal Supreme Council
                # is the UAE's — enwiki sitelink, uaecabinet.ae, a description
                # that names the country — and carries no country claim of any
                # kind. The body has the same gap the offices do, one level up,
                # and refusing it here would have blocked a correct statement to
                # complain about a different item.
                print(f"  ·  {verdict.qid} {prop}: target {target} resolves to no "
                      f"country — accepted on the sibling channel; the body has a "
                      f"jurisdiction gap of its own")
            closers[prop] = target
        for gap in verdict.gaps:
            if gap in closers:
                continue
            if verdict.bilateral:
                if gap == "no_P17":
                    got = _end_of(session, entity, "Q29645886")
                    if got:
                        closers["P17"] = got
                elif gap == "no_sender":
                    got = _end_of(session, entity, "Q29645880")
                    # The agreement gate: a sender that is not this country's
                    # state means the item is another country's outbound post,
                    # swept in by the receiver channel, and not this run's to fix.
                    if got == qid:
                        closers["P137"] = got
            elif gap == "no_P17" and code in verdict.countries:
                # Two channels: the item already resolves to this country through
                # some other property, and the audit is scoped to it.
                #
                # The second channel is weaker than it looks, because the first can
                # be a *wrong* claim and this rule then states it twice.
                # `Q17005012` "Attorney General's Office of Afghanistan" carries
                # `P1001 = Saudi Arabia`, so it resolved to `sa` and was handed
                # `P17 = Saudi Arabia` as well. So: refuse when the label names some
                # *other* country. It stays silent for a label naming no country at
                # all — "Minister of Interior" is a real Saudi portfolio and ten of
                # them look like that — which is why the residue below is surgical
                # rather than rule-driven.
                named = _named_country(verdict.label or "", session)
                if named and named != qid:
                    print(f"  !! {verdict.qid} P17: label names "
                          f"{named}, not {qid} — refusing it")
                else:
                    closers["P17"] = qid
            elif gap == "no_P1001" and _is_national(verdict.label or "", names):
                closers["P1001"] = qid
        if closers:
            out[verdict.qid] = closers
    return out


def candidates(session, country: Dict[str, object]) -> Dict[str, str]:
    """Position items the country owns, by qid -> label.

    Three channels, because the audit's own membership test cannot be "resolves
    to this country": that is the defect it looks for. `P17`/`P1001` find the
    well-formed ones and a text search finds the rest — an item with no country
    claim at all is reachable only by what its label says.
    """
    qid = country["qid"]
    found: Dict[str, str] = {}
    queries = [
        f"SELECT ?p WHERE {{ ?p wdt:P17 wd:{qid} ; wdt:P31/wdt:P279* wd:Q4164871 }}",
        f"SELECT ?p WHERE {{ ?p wdt:P1001 wd:{qid} ; wdt:P31/wdt:P279* wd:Q4164871 }}",
    ]
    for query in queries:
        for row in sparql(session, query, max_age=0):
            found.setdefault(row["p"], "")
    for term in country["search_terms"]:  # type: ignore[union-attr]
        for item in _search_labels(session, str(term)):
            found.setdefault(item, "")
    entities = fetch_entities(session, sorted(found), max_age=0)
    return {q: (best_label(entities.get(q, {})) or "") for q in sorted(found)}


def _search_labels(session, term: str) -> List[str]:
    """Position items whose text mentions `term`, via CirrusSearch.

    The label channel cannot be a SPARQL scan: `FILTER(CONTAINS(LCASE(?l), …))`
    over every position on Wikidata answers with a 504, and this channel exists
    precisely to admit items with no country path, so it cannot be narrowed by
    country either. CirrusSearch answers the same question in one request.

    Only reaches items carrying `P31 = Q4164871` outright, so an item typed
    solely as a subclass (`Q294414` public office) arrives through the country
    channels above instead.
    """
    found: List[str] = []
    offset = 0
    while True:
        raw = get_text(session, WIKIDATA_API, params={
            "action": "query", "format": "json", "list": "search",
            "srnamespace": "0", "srlimit": "50", "sroffset": str(offset),
            "srsearch": f"haswbstatement:P31={POSITION_CLASS} {term}",
        }, max_age=0)
        payload = json.loads(raw)
        hits = payload.get("query", {}).get("search", [])
        found.extend(hit["title"] for hit in hits)
        offset += len(hits)
        if len(hits) < 50 or offset >= 500:
            break
    return found


def _item(qid: str) -> Value:
    return Value(type="item", id=qid, iso=None, precision=None, text=None)


def records_for(
    campaign: str, verdict, entity: Dict[str, object], holders: int,
    parents: Dict[str, Tuple[str, str]], surgical: Dict[str, str],
    country_qid: str, closers: Dict[str, str],
) -> Optional[Record]:
    """One record per item: the statements that would model it correctly.

    Every case gets a disposition, including the ones with nothing to add — an
    item that already passes is recorded as a skip with its evidence, so the
    audit is an account of the country rather than a list of grievances.

    Two tiers of statement, and the difference decides what may be automated. A
    **defect** fix asserts something the item cannot do without and is written
    only for an item on the decided list. A **gap** fix asserts a measured
    convention and is written wherever `gap_closers` found a target with a second
    channel — which is most of them, and is why this run proposes ~50 statements
    where the defect tier alone proposed none.

    Gaps are written whether or not anyone holds the office. Gating them on
    holders was the first policy here and it was backwards: a holder count is a
    statement about what a *reader* can reach, and `P137` on an ambassadorship is
    correct or incorrect regardless. Eleven of the twenty-one posts this workbench
    minted for Qatar have no holder — `tasks/followups.md` records the batch as
    applied and only fourteen `P39`s found — and leaving its own creations
    half-shaped because no roster filled them is exactly the consumer-first
    ordering `recipes/position_items.md` opens by forbidding.

    An item on the surgical list still gets nothing: it returns above, because
    adding metadata to a duplicate or a mis-typed item entrenches it.
    """
    qid = verdict.qid
    label = verdict.label or qid
    subject = Subject(kind="position", qid=qid, ref=None, label=label)
    signals = [
        Signal(channel="modelling",
               supports="yes" if verdict.well_modelled else "no",
               detail=f"defects={verdict.defects or ['none']}; "
                      f"declared={verdict.declared or ['none']}; "
                      f"polity={verdict.countries or ['none']}"
                      f" via {verdict.country_via or 'nothing'}",
               source_url=None),
        Signal(channel="os_legibility",
               supports="yes" if not verdict.os_notes else "no",
               detail=f"notes={verdict.os_notes or ['none']}; "
                      f"topics={sorted(verdict.topics - {'role.pep'}) or ['none']}",
               source_url=None),
        Signal(channel="holders", supports="yes" if holders else "no",
               detail=f"{holders} holder(s) with a P39 to this item", source_url=None),
        Signal(channel="convention",
               supports="yes" if not verdict.gaps else "no",
               detail=f"gaps={verdict.gaps or ['none']}; "
                      f"closable={sorted(closers) or ['none']}; "
                      f"{'bilateral post' if verdict.bilateral else 'ordinary office'}",
               source_url=None),
    ]
    flags = list(verdict.defects) + list(verdict.gaps) + list(verdict.os_notes) + (
        [] if holders else ["no_holders"])

    # An item can need both. `Q6597965` Speaker of the Majlis is untyped *and*
    # dual-typed as a list article: the `P279` is additive and belongs in the
    # batch, dropping the stray `P31` is not and belongs on the surgical list.
    # Returning early here would have silently dropped the additive half.
    if qid in surgical and qid not in parents:
        return Record(
            campaign=campaign, subject=subject, statements=[],
            decision=Decision(action="defect", rule="item_layer.surgical",
                              source="default", concern="item_layer",
                              rationale=surgical[qid]),
            office="metadata", identity={"method": "qid"}, flags=flags,
            signals=signals, notes="stop-and-ask: never a batch line",
            byproduct={"kind": "surgical", "detail": surgical[qid]},
        )

    statements: List[Statement] = []
    # Only items on the decided list get a country. An office scoped to the Grand
    # Duchy or the Lithuanian SSR resolves to no country *correctly*, and naming
    # the modern republic on one would be a wrong statement in the lane that
    # looks safest — those close `absent` in the ledger instead.
    if qid in parents and "no_polity" in verdict.defects:
        for prop in ("P17", "P1001"):
            if country_qid not in set(claim_qids(entity, prop)):
                statements.append(Statement(
                    property=prop, value=_item(country_qid),
                    qualifiers=[], references=[], existing=False,
                    end_withheld=False))
    parent = parents.get(qid)
    if parent and parent[0] not in set(claim_qids(entity, "P279")):
        statements.append(Statement(
            property="P279", value=_item(parent[0]),
            qualifiers=[], references=[], existing=False, end_withheld=False))

    # The gap tier. Never a property the item already carries: `closers` is keyed
    # on a gap that fired against a live read, so the two can only disagree if
    # state moved underneath the run — which is the case this guard is for.
    gap_props: List[str] = []
    for prop in ("P17", "P1001", "P361", "P137", "P2389"):
        target = closers.get(prop)
        if target and target not in set(claim_qids(entity, prop)):
            statements.append(Statement(
                property=prop, value=_item(target),
                qualifiers=[], references=[], existing=False,
                end_withheld=False))
            gap_props.append(prop)

    if not statements:
        rule = ("modelling.sound" if verdict.complete
                else "modelling.no_rule")
        rationale = (
            "already names its polity, says what kind of office it is, and "
            "expresses every convention measured for its kind"
            if verdict.complete else
            f"defects {verdict.defects or 'none'} / gaps "
            f"{verdict.gaps or 'none'} and no target has a second channel — "
            "see the ledger row"
        )
        return Record(
            campaign=campaign, subject=subject, statements=[],
            decision=Decision(action="skip", rule=rule, source="default",
                              concern="item_layer", rationale=rationale),
            office="metadata", identity={"method": "qid"}, flags=flags,
            signals=signals, notes="", byproduct=None,
        )

    if parent:
        detail = parent[1]
    elif gap_props:
        detail = "closes " + "/".join(gap_props) + " against the measured convention"
    else:
        detail = "country backfill"
    if gap_props and parent:
        detail += f"; also closes {'/'.join(gap_props)}"
    if qid in surgical:
        return Record(
            campaign=campaign, subject=subject, statements=statements,
            decision=Decision(action="apply", rule="metadata.two_channel",
                              source="default", concern="item_layer",
                              rationale=f"{detail}; parent measured in live use. "
                                        "Carries a separate surgical note"),
            office="metadata", identity={"method": "qid"}, flags=flags,
            signals=signals, notes="stop-and-ask, separately: " + surgical[qid],
            byproduct={"kind": "surgical", "detail": surgical[qid]},
        )
    return Record(
        campaign=campaign, subject=subject, statements=statements,
        decision=Decision(action="apply", rule="metadata.two_channel",
                          source="default", concern="item_layer",
                          rationale=f"{detail}; parent measured in live use, and "
                                    "the label names the country"),
        office="metadata", identity={"method": "qid"}, flags=flags,
        signals=signals, notes="", byproduct=None,
    )


def calibrate(verdicts, holders: Dict[str, int]) -> None:
    """Check each verdict against the live API, and say which way it disagreed."""
    table: Counter = Counter()
    disagree: List[str] = []
    for verdict in verdicts:
        proc = subprocess.run(["yente-cli", "fetch", verdict.qid, "-f", "json"],
                              capture_output=True, text=True)
        present = False
        if proc.returncode == 0 and proc.stdout.strip():
            try:
                present = json.loads(proc.stdout).get("schema") == "Position"
            except json.JSONDecodeError:
                present = False
        table[(verdict.well_modelled, present)] += 1
        if verdict.well_modelled != present:
            why = ("no holders" if not holders.get(verdict.qid) else
                   "review layer, or a port bug")
            disagree.append(
                f"  {verdict.qid:12} well_modelled={verdict.well_modelled} "
                f"in_os={present}  ({why})  {verdict.label}")
    print("\n## Calibration")
    print(f"  agree            : {table[(True, True)] + table[(False, False)]}")
    print(f"  passes, absent   : {table[(True, False)]}")
    print(f"  fails, present   : {table[(False, True)]}")
    for line in disagree[:40]:
        print(line)
    if len(disagree) > 40:
        print(f"  … and {len(disagree) - 40} more")


def check_spec() -> int:
    """Fail if the recipe has drifted from the two things it must stay true to.

    The recipe names conventions that live in code, which is the kind of
    duplication that rots quietly. Two authorities, in priority order:

    `wd/create.py:ARCHETYPES` is the Wikidata authority — it holds the measured
    `P279` for each kind of office, and the recipe's table is a restatement of it.
    An archetype added there without the recipe naming it leaves the documented
    convention incomplete, and the next campaign mints against the gap.

    `wd/shape.py`'s ported constants are the secondary, OpenSanctions authority.
    Only the classes a reader would *silently* drop need naming, because those are
    the ones somebody has to look up when a well-modelled item does not appear.
    """
    from wd import create, shape

    recipe = (REPO_ROOT / "recipes" / "position_items.md").read_text()
    missing: List[str] = []

    absent = sorted(
        f"{key} ({arch.parent})"
        for key, arch in create.ARCHETYPES.items()
        if key not in recipe or arch.parent not in recipe
    )
    if absent:
        missing.append(f"  ARCHETYPES not named in the recipe: {absent}")

    # The gap tier is the recipe's newest claim and the easiest to add to in code
    # without saying so: a gap nobody documented is a statement a campaign emits
    # for a reason no reader can look up. Both the gap name and the property it
    # writes have to appear.
    for label, table in (("OFFICE_GAPS", shape.OFFICE_GAPS),
                         ("BILATERAL_GAPS", shape.BILATERAL_GAPS)):
        unnamed = sorted(
            f"{gap} ({prop})" for gap, (prop, _s) in table.items()
            if gap not in recipe or prop not in recipe
        )
        if unnamed:
            missing.append(f"  {label} not named in the recipe: {unnamed}")

    ported = {
        "POSITION_BASICS": shape.POSITION_BASICS,
        "EXCLUDE_TYPES": shape.EXCLUDE_TYPES,
        "SKIP_PLACES": shape.SKIP_PLACES,
        "HISTORICAL_TYPES": shape.HISTORICAL_TYPES,
    }
    for name, qids in ported.items():
        gone = sorted(q for q in qids if q not in recipe)
        if gone:
            missing.append(f"  {name}: {gone}")
    # The subtypes that contribute topics but leave the PEP default off: the
    # traps, and the only members worth enumerating one by one.
    quiet = sorted(
        q for q, topics in shape.SUB_TYPES.items()
        if shape.PEP_SENTINEL not in topics and q not in recipe
    )
    if quiet:
        missing.append(f"  SUB_TYPES leaving the default off: {quiet}")

    if missing:
        print("recipes/position_items.md has drifted:")
        print("\n".join(missing))
        return 1
    print("recipes/position_items.md matches wd/create.py:ARCHETYPES, names "
          "every gap and its property, and names every quietly-dropped class.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country", required=True, choices=sorted(COUNTRIES))
    parser.add_argument("--calibrate", action="store_true",
                        help="check every verdict against a live yente-cli fetch")
    parser.add_argument("--check-spec", action="store_true",
                        help="assert recipes/position_items.md enumerates every gate class")
    args = parser.parse_args()

    if args.check_spec:
        raise SystemExit(check_spec())

    country = COUNTRIES[args.country]
    campaign = str(country["campaign"])
    session = make_session()
    labels = candidates(session, country)
    print(f"## {country['name']}: {len(labels)} position items")

    parents = PARENTS_BY_COUNTRY.get(args.country, {})
    surgical = SURGICAL_BY_COUNTRY.get(args.country, {})

    verdicts = verify_all(session, sorted(labels), labels=labels)
    holders = holder_counts(session, sorted(labels))
    entities = fetch_entities(session, sorted(labels), max_age=0)
    closers = gap_closers(session, args.country, country, verdicts, entities)

    records = [
        record for record in (
            records_for(campaign, verdict, entities.get(verdict.qid, {}),
                        holders.get(verdict.qid, 0), parents, surgical,
                        str(country["qid"]), closers.get(verdict.qid, {}))
            for verdict in verdicts
        ) if record is not None
    ]

    out_dir = REPO_ROOT / "data" / campaign / "verdicts"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{campaign}_metadata.jsonl").write_text(dumps(records))

    gates = Counter(f for v in verdicts for f in v.defects)
    notes = Counter(n for v in verdicts for n in v.os_notes)
    actions = Counter(r.decision.action for r in records)
    # Gaps counted over *held* items, because that is the population the batch
    # can act on; an unheld office with three gaps is not three lines of work.
    held = {v.qid for v in verdicts if holders.get(v.qid)}
    conv = Counter(g for v in verdicts for g in v.gaps)
    #: Per gap, not per item: a gap is a unit of work and an item can have one
    #: closable and one not. Counting items instead reported 15 open gaps for
    #: Qatar when 15 were the *closable* senders.
    gap_prop = {"no_P17": "P17", "no_P1001": "P1001", "no_P361": "P361",
                "no_sender": "P137", "no_embassy": "P2389", "no_P279": "P279"}
    open_gaps = Counter(
        g for v in verdicts for g in v.gaps
        if gap_prop.get(g) not in closers.get(v.qid, {})
        and not (g == "no_P279" and v.qid in parents)
    )
    print(f"  well modelled   : {sum(1 for v in verdicts if v.well_modelled)}")
    print(f"  complete        : {sum(1 for v in verdicts if v.complete)}")
    print(f"  no holders      : {sum(1 for q in labels if not holders.get(q))}")
    print("  defects         : " + (", ".join(f"{k}={n}" for k, n in gates.most_common()) or "none"))
    print(f"  gaps ({len(held)} of {len(labels)} items held) : "
          + (", ".join(f"{k}={n}" for k, n in conv.most_common()) or "none"))
    print(f"  gaps still open ({sum(open_gaps.values())}) : "
          + (", ".join(f"{k}={n}" for k, n in open_gaps.most_common()) or "none"))
    print("  os notes        : " + (", ".join(f"{k}={n}" for k, n in notes.most_common()) or "none"))
    print("  dispositions    : " + ", ".join(f"{k}={n}" for k, n in actions.most_common()))
    print(f"  wrote {out_dir / f'{campaign}_metadata.jsonl'}")

    # A decided item that the candidate set never reached would vanish without
    # a trace, which is the one thing an audit may not do.
    reached = {v.qid for v in verdicts}
    for name, decided in (("PARENTS", set(parents)), ("SURGICAL", set(surgical))):
        unreached = sorted(decided - reached)
        if unreached:
            print(f"  !! {name} not reached by any channel: {unreached}")

    batch = [
        "\t".join([r.subject.qid, s.property, s.value.to_dict()["id"]])
        for r in records if r.decision.action == "apply" for s in r.statements
    ]
    if batch:
        result = check(batch)
        qs_path = out_dir.parent / f"{campaign}_item_layer.qs"
        if not result.ok:
            for defect in result.defects:
                print(f"  \u2717 {defect}")
            print(f"  {len(result.defects)} defect(s) — batch not written")
        else:
            qs_path.write_text("\n".join(batch) + "\n")
            print(f"  wrote {qs_path} ({len(batch)} statements)")
        for warning in result.warnings:
            print(f"  \u26a0 {warning}")

    surgical_rows = [r for r in records if r.byproduct]
    if surgical_rows:
        print(f"  surgical (stop-and-ask, never a batch line): {len(surgical_rows)}")
        for r in surgical_rows:
            print(f"     {r.subject.qid:12} {r.byproduct['detail']}")

    if args.calibrate:
        calibrate(verdicts, holders)


if __name__ == "__main__":
    main()
