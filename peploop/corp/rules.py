"""Turn each answer into statements, and decide each one apply or skip.

A body passes its gates first -- it is an enterprise or a state institution,
it is active, the article says a state controls it, at a tier the country's
spec writes -- or nothing is written on it. Then three kinds of statement:

- on an enterprise, the marker `P31 Q270791`, or `P31 Q1780371` for a
  municipal one, unless the item already reaches either through any subclass;
- a link to each public body the answer names over it: `P127` for an owner,
  `P749` for a parent it is part of or subordinate to, unless the loaded
  chain already reaches that body through another. The body must be a state
  actor, a government body, or one this run finds state-controlled; a body
  whose named owners and parents are all something else is not written on;
- one leadership statement per seat (`SEATS`, by kind, body and role, plus
  the spec's `roles`), for a person the article links to an item of a human,
  or one found by name whose own page places them at the body (`match.py`).

A body the member state's own AMLR list names (the `listed` lane) is in PEP
scope by that list: where the control gate alone stops it, its seats are
written all the same, and nothing else (`listed_scope`). The list proves
scope, never ownership: its marker and links still need the article.

A body at the municipal tier passes only where a governed unit of 50,000
or more (`amlr.units`) controls it and it has an article: the AMLR's
"medium or large" read by the size of its owner, never by the company's
figures (`municipal_unit`). A city-state's company is regional.

A party or a regional branch of one (the party lanes) is admitted by its
seat-holders, not by control: it passes when active, and gets its seats
only -- no marker, no link, no class -- by the party rows of `SEATS`, under
every seat rule a body's seats have.

An EU body or an international organisation (the `international` lane) is
admitted by being one, not by control, and gets its board seats only, as
`P5052` with the chair's role (`INTERNATIONAL_SEATS`). Its head is never
written: where the person holds an office of the body, or the seat is the
head's and the body has a head office, the office and its `P39` are
peploop's (`position_office`, `head_office`).

No shares, sizes or control arithmetic: the links and the article's word
are the evidence.

What survives is planned against the live item by peploop's own planner
(`route.route`), which merges into a statement that is there rather than
writing a second, and patches dates, role and reference by adding only.
Every row ends in `pcorp_decision` with the rule that decided it.
"""

import re
import unicodedata
from datetime import date
from typing import Any

from psycopg.types.json import Jsonb

from peploop import dates, evidence, ledger, route, tenure, typegraph
from peploop.corp import actors as actormod
from peploop.corp import country as countries
from peploop.corp import wd

#: The state-owned enterprise class: the marker written for the national and regional tiers.
MARKER = "Q270791"
#: The municipal company class: the municipal tier's marker.
MUNICIPAL = "Q1780371"
#: Markers that already make an item findable as a public enterprise, through any subclass.
MARKED = frozenset({MARKER, MUNICIPAL})
#: The tool name the send ledger records pepcorp's edits and removals under.
TOOL = "pepcorp"
#: The link property for each relation an answer names.
RELATIONS = {"owner": "P127", "parent": "P749"}
#: What a statutory body is, as the answer says, → the class written when its item lacks one.
STATUTORY = {
    "broadcaster": "Q1126006",  # public broadcaster
    "central_bank": "Q66344",  # central bank
    "regulator": "Q1639780",  # regulatory agency
}
#: Classes that already type a statutory body, through any subclass. A
#: country's own class for its regulators is one of its spec's `forms`.
STATUTORY_TYPED = frozenset(STATUTORY.values())
#: The kinds of body that are written on: a state's businesses, and the
#: institutions it runs (museums, broadcasters, research centres, agencies).
WRITTEN = ("enterprise", "institution")
#: The kinds of party body whose governing bodies are written: the party and
#: its branch for a first-level subdivision. A local branch waits for the
#: AMLR's local tier, which needs its unit's population.
PARTY = ("party", "regional_branch")
#: The kinds of international body whose boards are written: no control is asked.
INTERNATIONAL = ("eu_body", "international_organisation")
#: An international body's board seats: a supervisory board's idiom, its chair
#: and deputy as role qualifiers, as for an institution's supervisory body.
INTERNATIONAL_SEATS: dict[str, tuple[str, str | None]] = {
    "chair": ("P5052", "Q140686"),  # chairperson
    "deputy_chair": ("P5052", "Q1127270"),  # deputy chairperson
    "member": ("P5052", None),
}
#: (kind, body, role) → (property, role qualifier `P2868` or None). A "*" fits any.
SEATS: dict[tuple[str, str, str], tuple[str, str | None]] = {
    ("enterprise", "*", "head"): ("P169", None),
    ("enterprise", "executive", "chair"): ("P169", None),  # the chair of the executive body is its head
    ("institution", "*", "head"): ("P1037", None),  # director / manager
    ("institution", "executive", "chair"): ("P1037", None),
    # The chair of a supervisory body is one of its members, with the role:
    # `P5052` qualified, the idiom Wikidata uses (`P488` is a one-tier chair).
    ("enterprise", "supervisory", "chair"): ("P5052", "Q15818143"),  # chairman of the supervisory board
    ("institution", "supervisory", "chair"): ("P5052", "Q140686"),  # chairperson
    ("*", "board", "chair"): ("P488", None),
    ("*", "supervisory", "member"): ("P5052", None),  # supervisory board member
    ("*", "supervisory", "deputy_chair"): ("P5052", "Q1127270"),  # deputy chairperson
    ("*", "*", "deputy_chair"): ("P3320", "Q1127270"),
    ("*", "executive", "member"): ("P3320", "Q141755781"),  # executive board member (pepcorp's own role item)
    ("*", "board", "member"): ("P3320", None),
    ("*", "*", "managing_director"): ("P3320", "Q19940089"),  # managing director
    # A party's executive organs, by the idioms party items carry: plural
    # `P488` for co-chairs, `P3975` for the secretary-general, and `P3320`
    # unqualified for an executive member (75 of 75 on EU parties).
    ("party", "*", "chair"): ("P488", None),
    ("party", "*", "deputy_chair"): ("P3320", "Q1127270"),  # deputy chairperson
    ("party", "*", "secretary_general"): ("P3975", None),
    ("party", "*", "treasurer"): ("P3320", "Q388338"),  # treasurer
    ("party", "*", "member"): ("P3320", None),
}
#: Short tokens with a full stop that are titles, not names: "Dr.", "Prof.".
HONORIFIC = re.compile(r"^\w{1,5}\.$")
#: Degrees written after a name ("Ing. Jan Novák, Ph.D.", "Petra Horvát MBA"), compared without dots.
POSTNOMINAL = frozenset({"phd", "csc", "drsc", "mba", "llm", "msc", "bsc", "dis", "mpa", "dba", "artd", "thd"})


def seat_statement(kind: str, body: str, role: str,
                   extra: dict[str, tuple[str, str | None]] | None = None) -> tuple[str, str | None] | None:
    """The statement a seat becomes: the country's own row for its role, else the most specific of `SEATS`."""
    if kind in PARTY:
        # A party's rows stand alone: no body's row fits a party's seat.
        return SEATS.get(("party", "*", role))
    if kind in INTERNATIONAL:
        # A board seat is the one seat written on an international body.
        return INTERNATIONAL_SEATS.get(role)
    if extra and role in extra:
        return extra[role]
    for key in ((kind, body, role), (kind, "*", role), ("*", body, role), ("*", "*", role)):
        if key in SEATS:
            return SEATS[key]
    return None


def norm(text: str) -> str:
    """A name or page title reduced to what both write the same: no disambiguator, no title, no case."""
    text = unicodedata.normalize("NFKC", text).casefold()
    text = re.sub(r"\(.*?\)", " ", text)
    head, _, tail = text.partition(",")
    if tail and all(re.sub(r"[^\w]", "", t) in POSTNOMINAL | {"ma"} or HONORIFIC.match(t) for t in tail.split()):
        text = head
    tokens = [t for t in text.split() if not HONORIFIC.match(t)]
    while tokens and re.sub(r"[^\w]", "", tokens[-1]) in POSTNOMINAL:
        tokens.pop()
    return " ".join(re.sub(r"[^\w-]", "", t) for t in tokens if re.sub(r"[^\w-]", "", t))


def linked(name: str, lang: str, links: dict[str, dict[str, str]]) -> list[str]:
    """The items an article links under this name: its own language's first, else any language's."""
    want = norm(name)
    def hits(ls: dict[str, str]) -> list[str]:
        return sorted({q for title, q in ls.items() if norm(title) == want})
    own = hits(links.get(lang, {}))
    if own:
        return own
    return sorted({q for ls in links.values() for q in hits(ls)})


def item(qid: str) -> dict[str, str]:
    return {"entity-type": "item", "id": qid, "numeric-id": int(qid[1:])}


def gate(answer: dict[str, Any], message: str, tiers: tuple[str, ...] = countries.DEFAULT_TIERS,
         proof: str | None = None, unit: str | None = None) -> str | None:
    """Why nothing is written on this body, or None when it passes.

    `proof` is what shows the body the state's when its articles say nothing
    about who owns it (`proven`): an official holdings list or a state-only
    legal form. It never overrides an article that names a stake or a
    private owner. `unit` is the governed unit of 50,000 or more whose
    control puts the body in the municipal tier (`municipal_unit`); a
    municipal body without one is controlled by a smaller unit, or by one
    the run cannot place.
    """
    if answer["kind"] in PARTY or answer["kind"] in INTERNATIONAL:
        # A party is admitted by its seat-holders, an international body by
        # being one: no control to show.
        return None if answer["active"] else "inactive"
    if answer["kind"] not in WRITTEN:
        return f"kind:{answer['kind']}"
    if not answer["active"]:
        return "inactive"
    control = answer["control"]
    if control["verdict"] == "unstated" and proof:
        # A city's list of its holdings proves the municipal tier, with the unit it names.
        tier = "municipal" if proof == MUNICIPAL_LIST else "national"
        if tier in tiers and (tier != "municipal" or unit):
            return None
    if answer.get("statutory") in STATUTORY and control["verdict"] in ("unclear", "unstated"):
        # A public broadcaster, central bank or regulator is the state's by
        # statute, whatever its legal form (an association with a licence, a
        # bank with private shareholders): at its level, else national.
        level = control["level"] if control["level"] in ("national", "regional") else "national"
        return None if level in tiers else f"level:{level}"
    if control["verdict"] != "state":
        return f"control:{control['verdict']}"
    if control["level"] not in tiers:
        return f"level:{control['level']}"
    if control["level"] == "municipal" and unit is None:
        return "municipal_unit"
    if not evidence.quoted(control["quote"], message):
        return "control_unquoted"
    return None


#: The gates the member state's own list overrides: whatever the articles
#: leave unsaid or unclear about who owns or runs a listed body, or at which
#: tier, and an enterprise whose named owners are no state body. A body that
#: is no enterprise or institution (a ministry, a court: peploop's), is
#: inactive, or that its articles call private is not admitted: the list
#: names functions, and may lag a privatisation.
LISTED_OVERRIDES = ("control:unclear", "control:unstated", "control_unquoted", "enterprise_unowned", "no_state_owner")


def listed_scope(why: str | None, listed: bool) -> bool:
    """Whether a body stopped for `why` is written on all the same, its seats only, because the state lists it."""
    return listed and why is not None and (why in LISTED_OVERRIDES or why.startswith("level:"))


#: What `proven` returns for a city's or district's official list of its holdings.
MUNICIPAL_LIST = "municipal_list"


def proven(item: dict[str, Any] | None, spec: countries.Spec, kind: str | None = None) -> str | None:
    """What proves a body the state's apart from its articles: `list`, `municipal_list` or `form`, else None.

    An official holdings list proves it unless the entry is marked a minority
    stake; a wiki page or query is no official list, however it was seeded.
    An entry of a city's list (`level: municipal`) proves the municipal tier. A
    state-only legal form (the spec's `forms`, the item's own `P31` or
    `P1454`, exactly) proves a body of its own kind by itself: an authority's
    form proves no enterprise.
    """
    if not item:
        return None
    seed = item.get("seed")
    if seed and not seed.get("minority") and official(seed.get("source")):
        return MUNICIPAL_LIST if seed.get("level") == "municipal" else "list"
    entity = item.get("entity") or {}
    if any(spec.forms.get(v) in ((kind,) if kind else ("enterprise", "institution"))
           for p in ("P31", "P1454") for v in wd.values(entity, p)):
        return "form"
    return None


def official(url: str | None) -> bool:
    """Whether a holdings entry's source is a list someone answers for: a URL, not a wiki's."""
    m = re.match(r"https?://([^/\s]+)", url or "")
    return bool(m) and not re.search(r"(^|\.)(wikipedia|wikidata)\.org$", m.group(1))


def list_source(seed: dict[str, Any]) -> list[dict[str, Any]]:
    """A holdings list as a statement's source: its URL, cited with `P854`."""
    return [{"reference_url": seed["source"]}] if seed.get("source") else []


def source(req: dict[str, Any], lang: str | None) -> list[dict[str, Any]]:
    """The article a value was read in, as peploop's planner takes it."""
    art = next((a for a in req["articles"] if a["lang"] == lang), None)
    return [art] if art else []


def control_rows(req: dict[str, Any], entity: dict[str, Any], chain: list[str] | None,
                 state: set[str], closure: dict[str, set[str]],
                 named: dict[str, str] | None = None, polities: frozenset[str] = frozenset(),
                 refused: set[tuple[str, str, str]] | frozenset = frozenset(),
                 reached: set[str] | frozenset = frozenset(),
                 government: set[str] | frozenset = frozenset(),
                 country: str | None = None, standins: frozenset[str] = frozenset(),
                 proof: str | None = None, seed: dict[str, Any] | None = None,
                 admins: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """The type and link rows of a body that passed its gates.

    The marker goes on an enterprise only: a museum or a broadcaster is no
    state-owned enterprise, and its links are what find it. A statutory body
    (a public broadcaster, a central bank, a regulator) gets its class when
    its item has none. One `P127` or `P749` per public body the answer names
    over it, each with its quote. `state` is every body that counts as the
    state's; `named` resolves a controller the answer named rather than
    chose (name → QID); `standins` are the legal persons standing for the
    state (a state treasury), whose ownership is written as the polity's;
    `admins` the city administrations named, each → its unit, whose
    ownership is written as the unit's.
    A body proven the state's by a list or a form alone (`proof`) is an
    enterprise owned by the polity, cited to the list, or an institution
    with no link.
    """
    answer = req["answer"]
    control = answer["control"]
    rows = []
    marks = {t for p in ("P31", "P1454") for v in wd.values(entity, p) for t in closure.get(v, {v})}
    by_proof = control["verdict"] == "unstated" and proof is not None
    proof_sources = list_source(seed or {}) if proof in ("list", MUNICIPAL_LIST) else []
    municipal = proof == MUNICIPAL_LIST if by_proof else control["level"] == "municipal"
    if answer["kind"] == "enterprise":
        marker = MUNICIPAL if municipal else MARKER
        rule = "marked" if marks & MARKED else None
        if rule is None and (req.get("qid", ""), "P31", marker) in refused:
            # The control quote does not say the state controls it (a share figure).
            rule = "marker_unverified"
        rows.append({"property": "P31", "value": item(marker),
                     "qualifiers": {"_sources": proof_sources if by_proof else source(req, control["article"])},
                     "_rule": rule})
    statutory = STATUTORY.get(answer.get("statutory") or "")
    if statutory:
        # The class is read in the article: with no control quote, nothing cites it.
        cited = source(req, control["article"])
        rows.append({"property": "P31", "value": item(statutory), "qualifiers": {"_sources": cited},
                     "_rule": "typed" if marks & STATUTORY_TYPED or proof == "form"
                     else "statutory_unsourced" if not cited
                     # The narrow check found the article does not make it one (a registry called a regulator).
                     else "class_unverified" if (req.get("qid", ""), "P31", statutory) in refused
                     else None})
    if by_proof:
        if answer["kind"] == "enterprise" and municipal:
            unit = (seed or {}).get("unit")
            rows.append({"property": "P127", "value": item(unit) if unit else None,
                         "qualifiers": {"_sources": proof_sources},
                         "_rule": None if unit else "no_controller"})
        elif answer["kind"] == "enterprise" and country:
            rows.append({"property": "P127", "value": item(country), "qualifiers": {"_sources": proof_sources},
                         "_rule": "standin_existing" if set(wd.values(entity, "P127")) & (standins | {country})
                         else "holder_existing" if set(wd.values(entity, "P127")) & state else None})
        return rows
    offered = req["offered"]
    if not control["owners"]:
        rows.append({"property": "P127", "value": None, "qualifiers": {}, "_rule": "no_controller"})
    for owner in control["owners"]:
        prop = RELATIONS[owner["relation"]]
        idx = owner["controller"]
        qid = offered[idx] if idx is not None and 0 <= idx < len(offered) else (named or {}).get(owner["name"] or "")
        if qid is None:
            rows.append({"property": prop, "value": None, "qualifiers": {}, "_rule": "no_controller"})
            continue
        standin = qid in standins
        if prop == "P127" and qid in (admins or {}):
            # "Owner: the city administration": the owner is the city itself.
            if qid in wd.values(entity, "P127"):
                rows.append({"property": prop, "value": item(qid), "qualifiers": {}, "_rule": "standin_existing"})
                continue
            qid = (admins or {})[qid]
        if prop == "P127" and (qid in government or standin) and country and control["level"] == "national":
            # "Owner: Government of X", "owner: the State Treasury": the owner
            # is the state itself, the polity, never the body acting for it.
            qid, standin = country, True
        rule = None
        if not evidence.quoted(owner["quote"], req["message"]):
            rule = "owner_unquoted"
        elif qid not in state:
            # Being on the loaded chain is not enough: a chain can run
            # through a minority stake, and the body must itself be a state
            # actor, a government body or one this run finds state-controlled.
            rule = "controller_not_state"
        elif (prop == "P127" and control["level"] == "national" and qid in polities and qid != country
              and country is not None):
            # A province beside the national holder that leads: a co-owner, whose stake is no control.
            rule = "co_owner"
        elif chain and qid in chain[2:]:
            rule = "chain_reaches"
        elif prop == "P127" and qid in government:
            # A ministry or agency is a parent, never an owner: the owner is
            # the state it belongs to.
            rule = "owner_ministry"
        elif qid in reached:
            # One of the item's own links already leads there one step on.
            rule = "chain_existing"
        elif standin and set(wd.values(entity, "P127")) & standins:
            # The item already names the state's stand-in as owner: that is
            # the state, and a second owner statement would read as two.
            rule = "standin_existing"
        elif prop == "P127" and qid == country and set(wd.values(entity, "P127")) & (state - {country} - standins):
            # The item already names a state holder (a state company, a
            # transport authority): the polity beside it reads as a second owner.
            rule = "holder_existing"
        elif (req.get("qid", ""), prop, qid) in refused:
            # The narrow check (`verify.py`) found the quote does not state it.
            rule = "link_unverified"
        elif prop == "P749" and qid in polities:
            # A parent organization is a ministry or government body; a state
            # or a province as parent is all but unused on Wikidata.
            rule = "parent_polity"
        rows.append({"property": prop, "value": item(qid),
                     "qualifiers": {"_sources": source(req, owner["article"])}, "_rule": rule})
    # One row per link: a government rewritten to its state may meet the state named too.
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    out = []
    for row in rows:
        if row["value"] is None or row["property"] not in RELATIONS.values():
            out.append(row)
            continue
        k = (row["property"], row["value"]["id"])
        if k in seen:
            if seen[k]["_rule"] is not None and row["_rule"] is None:
                out[out.index(seen[k])] = row
                seen[k] = row
            continue
        seen[k] = row
        out.append(row)
    return out


#: Why a marker is proposed for removal, as the edit summary says it.
REMOVAL_REASONS = {
    "municipal": "a municipal company, not a state-owned enterprise (its Wikipedia article)",
}


def correction(req: dict[str, Any], entity: dict[str, Any], closure: dict[str, set[str]],
               tiers: tuple[str, ...], subdivisions: frozenset[str] = frozenset(),
               ) -> tuple[str | None, list[dict[str, Any]], list[dict[str, Any]]]:
    """A marker the answer contradicts: (kind of correction, rows to add, statements to propose removing).

    A body the article shows to be municipal, while the tier is not written,
    keeps no state-enterprise marker and gains the municipal one. A body it
    shows to be private, and dates when the state gave it up, keeps its
    marker with that end (`P582`): the item records its state past too.
    Nothing else is written on either.
    """
    answer = req["answer"]
    control = answer["control"]
    if answer["kind"] not in WRITTEN or not answer["active"] or not evidence.quoted(control["quote"], req["message"]):
        return None, [], []
    offered = req.get("offered") or []
    owners = {offered[o["controller"]] for o in control["owners"]
              if o["controller"] is not None and 0 <= o["controller"] < len(offered)}
    if owners & subdivisions:
        # A city that is also a first-level subdivision (a city-state)
        # controls at the regional tier: nothing to correct.
        return None, [], []
    def marked(claim: dict[str, Any], roots: frozenset[str]) -> bool:
        v = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        return isinstance(v, dict) and bool(closure.get(v.get("id"), {v.get("id")}) & roots)
    def exactly(claim: dict[str, Any], values: frozenset[str]) -> bool:
        # Only the marker itself is ever proposed for removal: a subclass
        # someone chose (a mixed public company) may well be right.
        v = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        return isinstance(v, dict) and v.get("id") in values
    claims = [c for c in entity.get("claims", {}).get("P31", []) if c.get("rank") != "deprecated"]
    if control["verdict"] == "state" and control["level"] == "municipal" and "municipal" not in tiers:
        wrong = [c for c in claims if exactly(c, frozenset({MARKER}))]
        if not wrong:
            return None, [], []
        add = [] if any(marked(c, frozenset({MUNICIPAL})) for c in claims) else [
            {"property": "P31", "value": item(MUNICIPAL), "qualifiers": {"_sources": source(req, control["article"])},
             "_rule": None}]
        return "municipal", add, wrong
    if control["verdict"] == "private" and answer["kind"] == "enterprise":
        ended = control.get("ended")
        values = {c["mainsnak"]["datavalue"]["value"]["id"] for c in claims if exactly(c, MARKED)}
        if not ended or not values:
            return None, [], []
        return "private", [{"property": "P31", "value": item(v),
                            "qualifiers": {"_sources": source(req, control["article"]),
                                           "P582": dates.time_value(ended)},
                            "_rule": None} for v in sorted(values)], []
    return None, [], []


def municipal_unit(req: dict[str, Any], entity: dict[str, Any], chain: list[str] | None,
                   units: frozenset[str] | set[str], named: dict[str, str] | None = None,
                   through: dict[str, str] | None = None) -> str | None:
    """The governed unit of 50,000 or more whose control puts a body in the municipal tier, or None.

    Reach for this to apply the AMLR's size test for local enterprises by
    proxy: the controlling unit is large enough and the body has an article.
    The unit is a controller the answer names; else the unit behind a
    controller that is itself a municipal body (`through`: an inter-municipal
    association, a city's holding); else the end of the item's chain on
    Wikidata; else, when the answer names no controller with an item at all,
    the unit the body is located in (`P131`, `P159`).
    """
    if not req.get("articles"):
        return None
    found = sorted(controllers(req, named))
    for qid in found:
        if qid in units:
            return qid
    for qid in found:
        if qid in (through or {}):
            return (through or {})[qid]
    if chain and chain[-1] in units:
        return chain[-1]
    if not found:
        return next((q for p in ("P131", "P159") for q in wd.values(entity, p) if q in units), None)
    return None


#: How many owner steps a named controller is followed to the unit behind it.
UNIT_HOPS = 2


def controller_units(qids: set[str], entities: dict[str, dict[str, Any]], units: frozenset[str] | set[str],
                     hops: int = UNIT_HOPS) -> dict[str, str]:
    """The governed unit behind each named controller that is no unit itself, where one is.

    Answers name a city's administration (an item whose jurisdiction,
    `P1001`, is the city) or a city's holding company as often as the city:
    a controller's unit is its jurisdiction, or that of an owner or parent
    it has on Wikidata, up to `hops` steps. `entities` holds every item the
    walk reads.
    """
    def walk(qid: str, left: int) -> str | None:
        if qid in units:
            return qid
        entity = entities.get(qid) or {}
        here = next((u for u in wd.values(entity, "P1001") if u in units), None)
        if here or left == 0:
            return here
        return next((u for p in ("P127", "P749") for o in wd.values(entity, p) if (u := walk(o, left - 1))), None)
    return {q: u for q in qids if q not in units and (u := walk(q, hops))}


def unit_names(entities: dict[str, dict[str, Any]]) -> dict[str, str | None]:
    """Each unit's labels and aliases, folded (`norm`) → the unit; None where two units share one.

    A label wins over another unit's alias: a district named after its town
    often carries the town's name as an alias.
    """
    def terms(kind: str) -> dict[str, str | None]:
        out: dict[str, str | None] = {}
        for qid, entity in sorted(entities.items()):
            values = ([v["value"] for v in entity.get("labels", {}).values()] if kind == "labels"
                      else [a["value"] for al in entity.get("aliases", {}).values() for a in al])
            for term in {norm(t) for t in values if t}:
                out[term] = qid if out.get(term, qid) == qid else None
        return out
    return terms("aliases") | terms("labels")


def name_unit(name: str, names: dict[str, str | None]) -> str | None:
    """The unit an owner's name the article does not link stands for: its label, or its label after one word.

    Articles write the owner as "the town of X" in one word or two ("Stadt
    Mannheim") where they link nothing; the link it becomes is checked
    against its quote like any other.
    """
    tokens = norm(name).split()
    for n in (len(tokens), len(tokens) - 1):
        if n > 0 and (hit := names.get(" ".join(tokens[-n:]))):
            return hit
    return None


def city_state(req: dict[str, Any], named: dict[str, str] | None, subdivisions: frozenset[str],
               municipal: frozenset[str] | set[str] = frozenset()) -> dict[str, Any]:
    """The request with a city-state's company at the regional tier, where the answer calls it municipal.

    A city that is also a first-level subdivision (a city-state) controls
    its companies as a region does: they are no municipal tier's. A region
    beside a city that leads (`municipal`: the units and the bodies standing
    for one) is a co-owner, and the company stays the city's.
    """
    control = req["answer"].get("control")
    found = controllers(req, named) if control else set()
    if not control or control["level"] != "municipal" or not found & subdivisions or found & set(municipal):
        return req
    return {**req, "answer": {**req["answer"], "control": {**control, "level": "regional"}}}


def seat_rule(seat: dict[str, Any], start: dict[str, Any] | None, end: dict[str, Any] | None,
              today: date) -> str | None:
    """Why a seat is not written, from its dates and currency alone."""
    if tenure.bad_dates(start, end):
        return "bad_dates"
    if start and dates.after_today(start, today):
        # A tenure that starts after today is not a fact yet.
        return "future"
    if seat["current"] and end:
        return "current_ended"
    if not start and not end and not seat["current"]:
        return "undated_former"
    if tenure.ended_long_ago(start, end, today):
        return "tenure_ended"
    if not end and not seat["current"] and tenure.open_too_long(start, today):
        return "open_unattested"
    return None


#: The two properties a body's head is written with; a person holds one of them, never both.
HEADS = ("P169", "P1037")


def seat_rows(req: dict[str, Any], humans: set[str], today: date,
              extra: dict[str, tuple[str, str | None]] | None = None,
              entity: dict[str, Any] | None = None, dead: set[str] | frozenset = frozenset(),
              matched: dict[tuple[str, str], str] | None = None,
              titles: dict[str, set[str]] | None = None,
              unconfirmed: set[tuple[str, str]] | frozenset = frozenset()) -> list[dict[str, Any]]:
    """One leadership row per seat the answer lists.

    A person is the item the article links under the seat's name; failing
    that, the one `match.py` found by name and checked against their own
    page (`matched`, by body and name). Each row says how (`_via`): `link`
    when the name is the linked page's title (`titles`, QID → its page
    titles), `anchor` when only the link's text, `matched`. A linked person
    whose own page does not bear out the seat (`unconfirmed`, by body and
    name) is a namesake the article links by mistake.
    """
    heads = {p: set(wd.values(entity or {}, p)) for p in HEADS}
    kind = req["answer"]["kind"]
    # The latest start among the answer's heads (a party's chairs): an
    # earlier one left open (an interim, a predecessor) was followed by that one.
    lead = "chair" if kind in PARTY else "head"
    starts = [s["start"] for s in req["answer"]["seats"] if s["role"] == lead and s["start"]]
    last_head = max(starts, key=lambda t: t.ljust(10, "0")) if starts else None
    rows = []
    for seat in req["answer"]["seats"]:
        statement = seat_statement(kind, seat.get("body", "*"), seat["role"], extra)
        if statement is None:
            rows.append({"property": "seat", "value": None, "qualifiers": {}, "_rule": f"role_unmapped:{seat['role']}",
                         "_name": seat["name"]})
            continue
        prop, role = statement
        start = dates.time_value(seat["start"]) if seat["start"] else None
        end = dates.time_value(seat["end"]) if seat["end"] else None
        if end and dates.after_today(end, today) and not (start and dates.after_today(start, today)):
            # A fixed term that runs past today is held now: its end is not a fact yet.
            end, seat = None, {**seat, "current": True}
        found = linked(seat["name"], seat["article"], req["links"])
        via = None
        if found:
            via = "link" if any(norm(t) == norm(seat["name"]) for q in found for t in (titles or {}).get(q, ())) else "anchor"
        elif (req.get("qid", ""), seat["name"]) in (matched or {}):
            found, via = [(matched or {})[(req.get("qid", ""), seat["name"])]], "matched"
        rule = None
        if not evidence.quoted(seat["quote"], req["message"]):
            rule = "seat_unquoted"
        elif not found:
            # A seat its dates rule out is no work for the matcher: only
            # the ones that would be written wait for a person.
            rule = seat_rule(seat, start, end, today) or "person_unlinked"
        elif len(found) > 1:
            rule = "person_ambiguous"
        elif found[0] not in humans:
            rule = "not_human"
        elif (req.get("qid", ""), seat["name"]) in unconfirmed:
            rule = "person_unconfirmed"
        elif not end and found[0] in dead:
            # A seat with no end, held by someone who has died, ended then.
            rule = "holder_dead"
        elif (seat["role"] == lead and not seat["current"] and not end and last_head
              and (seat["start"] or "").ljust(10, "0") < last_head.ljust(10, "0")):
            rule = "superseded"
        elif prop in HEADS and any(found[0] in heads[p] for p in HEADS if p != prop):
            # The head already recorded under the other head property: a
            # second statement would read as a second seat.
            rule = "head_other"
        else:
            rule = seat_rule(seat, start, end, today)
        quals: dict[str, Any] = {"_sources": source(req, seat["article"])}
        if start:
            quals["P580"] = start
        if end:
            quals["P582"] = end
        if role:
            quals["P2868"] = item(role)
        rows.append({"property": prop, "value": item(found[0]) if len(found) == 1 else None,
                     "qualifiers": quals, "_rule": rule, "_name": seat["name"], "_via": via})
    return rows


#: A head's title that makes the head the board's chair: an authority's chair, a council's president.
CHAIR_TITLE = re.compile(r"\b(?:chair\w*|president)\b", re.I)


def head_excluded(rows: list[dict[str, Any]], seats: list[dict[str, Any]], offices: set[str],
                  held: dict[str, set[str]], head_title: str | None = None) -> list[dict[str, Any]]:
    """An international body's seat rows, less those that are a position office's.

    `offices` are the body's own offices (scoped to it, or its head's `P2388`),
    `held` each person's `P39` values, `head_title` the title peploop's
    census gives the body's head, whose office it mints. A person who holds
    one of the offices sits there by it; the head who chairs the board is
    the head's office wherever the body has or is getting one, and so is
    every chair of a board whose head the census titles its chair: both are
    peploop's, and a second statement on the body would record the office twice.
    """
    out = []
    for row, seat in zip(rows, seats):
        person = (row.get("value") or {}).get("id")
        headed = bool(offices or head_title)
        if row["_rule"] is None and person and held.get(person, set()) & offices:
            row = {**row, "_rule": "position_office"}
        elif row["_rule"] is None and ((seat.get("heads_body") and headed) or (
                seat["role"] == "chair" and head_title and CHAIR_TITLE.search(head_title))):
            row = {**row, "_rule": "head_office"}
        out.append(row)
    return out


def census_heads(cc: str) -> dict[str, str]:
    """Body → its head's title, for the bodies whose head office peploop's census lists (`per: bodies`)."""
    from peploop import mint_units
    return {b.qid: b.title for level in mint_units.levels(cc) for b in level.bodies}


#: The offices of an international body: scoped to it, or held by its head (`P2388`).
BODY_OFFICES = """SELECT DISTINCT ?b ?o WHERE { VALUES ?b { %s }
  { ?o wdt:P2389 ?b } UNION { ?o wdt:P1001 ?b } UNION { ?o wdt:P642 ?b } UNION { ?b wdt:P2388 ?o } }"""


def body_offices(qids: list[str]) -> dict[str, set[str]]:
    """Each body's offices, read live: what a board seat must not repeat."""
    rows = wd.bisect(lambda chunk: wd.sparql(BODY_OFFICES % wd.values_block(chunk)), qids, size=40) if qids else []
    out: dict[str, set[str]] = {}
    for r in rows:
        out.setdefault(r["b"], set()).add(r["o"])
    return out


def settle(r: dict[str, Any], entity: dict[str, Any], rows: list[dict[str, Any]],
           decisions: list[dict[str, Any]]) -> list[str]:
    """Plan a body's surviving rows against its live item, record every row's decision, return the lines."""
    for n, row in enumerate(rows):
        row["id"] = n
    planned = [row for row in rows if row["_rule"] is None]
    routed = route.route(r["qid"], entity, planned) if planned else route.Routed(qid=r["qid"])
    skipped = dict(routed.skipped)
    written = {i for _, ids in routed.edits for i in ids}
    for row in rows:
        n = row["id"]
        if row["_rule"] is not None:
            disposition, rule = "skip", row["_rule"]
        elif n in written:
            disposition, rule = "apply", "write"
        elif n in routed.deferred:
            disposition, rule = "skip", "deferred"
        else:
            disposition, rule = "skip", f"plan:{skipped.get(n, 'unrouted')}"
        value = (row["value"] or {}).get("id")
        detail = {k: v for k, v in row["qualifiers"].items() if not k.startswith("_")}
        if row.get("_name"):
            detail["name"] = row["_name"]
        if row.get("_via"):
            detail["via"] = row["_via"]
        if row.get("_scope"):
            detail["scope"] = row["_scope"]
        decisions.append({"qid": r["qid"], "prop": row["property"], "value": value, "detail": detail,
                          "disposition": disposition, "rule": rule, "call_key": r.get("key")})
    return routed.lines


def decide(cc: str, answered: list[dict[str, Any]], items: dict[str, dict[str, Any]],
           actors: actormod.Actors, spec: countries.Spec | None = None, today: date | None = None,
           refused: set[tuple[str, str, str]] | frozenset = frozenset(),
           matched: dict[tuple[str, str], str] | None = None,
           unconfirmed: set[tuple[str, str]] | frozenset = frozenset(),
           ) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    """Plan every answered body against its live item: (lines, decision rows, proposed removals).

    `refused` are the links, markers and classes the quote check refused
    (`verify.py`), `matched` the unlinked seats' people found by name and
    `unconfirmed` the linked seats their person's page does not bear out
    (`match.py`).
    """
    today = today or date.today()
    spec = spec or countries.get(cc)
    subdivisions = frozenset(q for q, k in actors.kinds.items() if k == "subdivision")
    units = actors.units()
    # Controllers the answers named rather than chose, resolved through the
    # article's links, count when they are a government body of the country.
    # An owner the article does not link may still name a unit ("the town of X").
    names = unit_names(live(sorted(units), "labels|aliases")) if units else {}
    named: dict[str, dict[str, str]] = {}
    for r in answered:
        for o in r["answer"].get("control", {}).get("owners", []):
            if o["controller"] is None and o["name"]:
                found = linked(o["name"], o["article"], r["links"])
                if not found and (unit := name_unit(o["name"], names)):
                    found = [unit]
                if len(found) == 1:
                    named.setdefault(r["qid"], {})[o["name"]] = found[0]
    # The unit behind each controller named, and the city administrations
    # among them, which count as public bodies of their unit.
    behind: dict[str, str] = {}
    admins: dict[str, str] = {}
    if units:
        named_now = {q for r in answered for q in controllers(r, named.get(r["qid"]))} - units - set(actors.kinds)
        reads = live(sorted(named_now))
        for _ in range(UNIT_HOPS):
            reads.update(live(sorted({o for e in reads.values() for p in ("P127", "P749") for o in wd.values(e, p)})))
        behind = controller_units(named_now, reads, units)
        admins = {q: u for q in named_now for u in wd.values(reads.get(q) or {}, "P1001") if u in units}
    answered = [city_state(r, named.get(r["qid"]), subdivisions, units | set(behind)) for r in answered]
    proofs = {r["qid"]: proven(items.get(r["qid"]), spec, r["answer"]["kind"]) for r in answered}
    # The unit each municipal body's control resolves to; an inter-municipal
    # association or a city's holding this run passes lends its own unit to
    # the bodies it owns, so the walk repeats while it finds more.
    seeds = {qid: (it.get("seed") or {}).get("unit") for qid, it in items.items()}
    unit_of: dict[str, str | None] = {}
    by_qid = {r["qid"]: r for r in answered}
    for _ in range(3):
        through = behind | {q: u for q, u in unit_of.items() if u and by_qid[q]["answer"]["control"]["level"] == "municipal"
                            and gate(by_qid[q]["answer"], by_qid[q]["message"], spec.tiers, proofs[q], u) is None}
        unit_of = {r["qid"]: (seeds.get(r["qid"]) if proofs[r["qid"]] == MUNICIPAL_LIST else municipal_unit(
            r, (items.get(r["qid"]) or {}).get("entity") or {}, (items.get(r["qid"]) or {}).get("chain"), units,
            named.get(r["qid"]), {q: u for q, u in through.items() if q != r["qid"]}))
            for r in answered if "control" in r["answer"]}
    why = {r["qid"]: gate(r["answer"], r["message"], spec.tiers, proofs[r["qid"]], unit_of.get(r["qid"]))
           for r in answered}
    passed = {r["qid"]: r for r in answered if why[r["qid"]] is None}
    # Bodies the state's own list names: in scope by the list where the control gate alone stops them.
    listed = {qid for qid, it in items.items() if "listed" in (it.get("lanes") or ())}
    scoped = {r["qid"] for r in answered if r["qid"] not in passed and r["qid"] in listed
              and listed_scope(why[r["qid"]], True)}
    # Bodies the answer gates out but whose existing marker it contradicts.
    marked_now = {qid for qid, it in items.items()
                  if wd.values(it.get("entity") or {}, "P31") or wd.values(it.get("entity") or {}, "P1454")}
    contradicted = {r["qid"] for r in answered if r["qid"] not in passed and r["qid"] in marked_now
                    and "control" in r["answer"] and (r["answer"]["control"]["level"] == "municipal" or r["answer"]["control"]["verdict"] == "private")}
    entities = wd.fetch_items(sorted(set(passed) | contradicted | scoped)) if passed or contradicted or scoped else {}
    marks = {v for e in entities.values() for p in ("P31", "P1454") for v in wd.values(e, p)}
    closure = typegraph.of_classes(marks)
    seated = [r for r in answered if r["qid"] in passed or r["qid"] in scoped]
    names = sorted({q for r in seated for s in r["answer"]["seats"]
                    for q in linked(s["name"], s["article"], r["links"])} | set((matched or {}).values()))
    people = wd.fetch_items(names, props="claims|sitelinks") if names else {}
    titles = {q: {s["title"] for s in e.get("sitelinks", {}).values()} for q, e in people.items()}
    humans = {q for q, e in people.items() if "Q5" in wd.values(e, "P31")}
    dead = {q for q, e in people.items() if e.get("claims", {}).get("P570")}
    # A party owns nothing here and is no state body: only the bodies' answers name controllers.
    parties = {qid for qid, r in passed.items() if r["answer"]["kind"] in PARTY}
    # An international body is no state body either; its head's office is peploop's.
    international = {qid for qid, r in passed.items() if r["answer"]["kind"] in INTERNATIONAL}
    own_offices = body_offices(sorted(international)) if international else {}
    heads = census_heads(cc) if international else {}
    held = {q: set(wd.values(e, "P39")) for q, e in people.items()}
    government = actors.is_government({q for qid, m in named.items() if qid in passed for q in m.values()})
    # A body this run finds state-controlled is a state owner in its own right:
    # a state bank's subsidiary is held through the bank.
    state = (set(passed) - parties - international) | set(actors.kinds) | government | set(admins)
    # A municipal unit is a polity too: an owner, never a parent organization.
    polities = frozenset(q for q, k in actors.kinds.items() if k in ("state", "subdivision")) | units
    # A government body this run writes as an enterprise or institution (a
    # central bank, an agency holding shares) owns in its own right; only a
    # ministry or a government is written as the state it acts for.
    bodies = (frozenset(q for q, k in actors.kinds.items() if k == "government") | government) - set(passed)
    standins = frozenset(q for q, k in actors.kinds.items() if k == "state" and q != actors.state)
    # What each item's existing owners and parents link to in turn: a link to
    # one of those would only shortcut a chain already on Wikidata.
    linked_now = {qid: {v for p in ("P127", "P749") for v in wd.values(e, p)} for qid, e in entities.items()}
    hop = wd.fetch_items(sorted(set().union(*linked_now.values())), props="claims") if linked_now else {}
    reached = {qid: {v for t in targets for p in ("P127", "P749") for v in wd.values(hop.get(t) or {}, p)} - targets
               for qid, targets in linked_now.items()}
    # So would a link to what this run's own answers put over its other
    # controllers: a transport company owned by a state holding that the
    # same run puts under the state gets the holding, not the state too.
    planned = {qid: controllers(r, named.get(qid)) for qid, r in passed.items()
               if qid not in parties and qid not in international}
    for qid, via in through_planned(planned, linked_now).items():
        reached[qid] = reached.get(qid, set()) | via
    lines: list[str] = []
    decisions: list[dict[str, Any]] = []
    removals: list[dict[str, Any]] = []
    for r in answered:
        if why[r["qid"]] is not None:
            kind, add, wrong = (correction(r, entities[r["qid"]], closure, spec.tiers, subdivisions)
                                if r["qid"] in contradicted and r["qid"] in entities else (None, [], []))
            decisions.append({"qid": r["qid"], "prop": "-", "value": None,
                              "detail": {"scope": "listed"} if r["qid"] in scoped else {},
                              "disposition": "skip", "rule": why[r["qid"]], "call_key": r.get("key")})
            seats = (listed_seats(r, humans, today, spec.roles, entities[r["qid"]], dead, matched, titles, unconfirmed)
                     if r["qid"] in scoped and r["qid"] in entities else [])
            if kind or seats:
                lines += settle(r, entities[r["qid"]], add + seats, decisions)
                for claim in wrong:
                    value = claim["mainsnak"]["datavalue"]["value"]["id"]
                    removals.append({"guid": claim["id"], "qid": r["qid"], "prop": "P31", "value": value,
                                     "reason": REMOVAL_REASONS[kind]})
                    decisions.append({"qid": r["qid"], "prop": "P31", "value": value, "detail": {"guid": claim["id"]},
                                      "disposition": "remove", "rule": f"correction:{kind}", "call_key": r.get("key")})
            continue
        entity = entities.get(r["qid"])
        if entity is None:
            decisions.append({"qid": r["qid"], "prop": "-", "value": None, "detail": {},
                              "disposition": "skip", "rule": "missing", "call_key": r.get("key")})
            continue
        if r["qid"] in parties:
            lines += settle(r, entity, seat_rows(r, humans, today, spec.roles, entity, dead, matched, titles,
                                                 unconfirmed), decisions)
            continue
        if r["qid"] in international:
            rows = seat_rows(r, humans, today, spec.roles, entity, dead, matched, titles, unconfirmed)
            lines += settle(r, entity, head_excluded(rows, r["answer"]["seats"], own_offices.get(r["qid"], set()),
                                                     held, heads.get(r["qid"])), decisions)
            continue
        chain = items.get(r["qid"], {}).get("chain")
        rows = control_rows(r, entity, chain, state, closure, named.get(r["qid"]), polities, refused,
                            reached.get(r["qid"], set()), bodies, actors.state, standins,
                            proofs[r["qid"]], items.get(r["qid"], {}).get("seed"), admins)
        links = [row for row in rows if row["property"] in RELATIONS.values() and row["value"] is not None]
        if r["answer"]["kind"] == "enterprise" and not links:
            # An enterprise whose article names no public owner stands on
            # wording alone ("partly state-owned"): no marker, no seats. An
            # owner already on the item proves nothing: it may record a
            # minority holder.
            decisions.append({"qid": r["qid"], "prop": "-", "value": None,
                              "detail": {"scope": "listed"} if r["qid"] in listed else {},
                              "disposition": "skip", "rule": "enterprise_unowned", "call_key": r.get("key")})
            if listed_scope("enterprise_unowned", r["qid"] in listed):
                lines += settle(r, entity, listed_seats(r, humans, today, spec.roles, entity, dead, matched, titles,
                                                        unconfirmed), decisions)
            continue
        if (r["answer"]["kind"] == "enterprise" and links
                and not any(row["_rule"] in (None, "chain_reaches", "chain_existing", "owner_ministry", "standin_existing")
                            for row in links)):
            # Every body the answer names over it is no state body: the
            # control it claims runs through someone else's company. An
            # institution named under an office ("the Prime Minister") or
            # the polity itself keeps its seats: it would keep them had the
            # answer named no parent at all.
            decisions.append({"qid": r["qid"], "prop": "-", "value": None,
                              "detail": {"scope": "listed"} if r["qid"] in listed else {},
                              "disposition": "skip", "rule": "no_state_owner", "call_key": r.get("key")})
            if listed_scope("no_state_owner", r["qid"] in listed):
                lines += settle(r, entity, listed_seats(r, humans, today, spec.roles, entity, dead, matched, titles,
                                                        unconfirmed), decisions)
            continue
        rows += seat_rows(r, humans, today, spec.roles, entity, dead, matched, titles, unconfirmed)
        lines += settle(r, entity, rows, decisions)
    return lines, decisions, removals


#: The items read live for the municipal tier, kept for the process: a run plans its country several times.
LIVE: dict[tuple[str, str], dict[str, Any]] = {}


def live(qids: list[str], props: str = "claims") -> dict[str, dict[str, Any]]:
    """These items as Wikidata has them now, each read once per process."""
    missing = [q for q in qids if (q, props) not in LIVE]
    if missing:
        found = wd.fetch_items(missing, props=props)
        LIVE.update({(q, props): found.get(q) or {} for q in missing})
    return {q: LIVE[(q, props)] for q in qids}


def listed_seats(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
    """A listed body's seat rows when the list alone admits it, each marked so (`scope`)."""
    rows = seat_rows(*args, **kwargs)
    for row in rows:
        row["_scope"] = "listed"
    return rows


def through_planned(planned: dict[str, set[str]], linked_now: dict[str, set[str]]) -> dict[str, set[str]]:
    """Per body, the controllers this run puts over its other controllers, old or planned."""
    out = {}
    for qid, mine in planned.items():
        via = {v for t in mine | linked_now.get(qid, set()) for v in planned.get(t, set())} - {qid}
        # Two controllers each over the other is a loop, not a chain: neither goes.
        out[qid] = via - {v for v in via if planned.get(v, set()) & mine}
    return out


def controllers(req: dict[str, Any], named: dict[str, str] | None) -> set[str]:
    """The bodies an answer names over its body, chosen or resolved by name."""
    offered = req["offered"]
    out = set()
    for o in (req["answer"].get("control") or {}).get("owners", []):
        idx = o["controller"]
        qid = offered[idx] if idx is not None and 0 <= idx < len(offered) else (named or {}).get(o["name"] or "")
        if qid:
            out.add(qid)
    return out


def queue_removals(cc: str, removals: list[dict[str, Any]]) -> int:
    """Queue each contradicted marker for removal: it waits for `removals approve`, being another editor's.

    A proposal an earlier run made and this one no longer makes is withdrawn
    while still undecided: the answer behind it has changed.
    """
    wd.conn().execute(
        "DELETE FROM wd_removal WHERE tool = %s AND country = %s AND origin = 'correction'"
        " AND status = 'proposed' AND NOT (guid = ANY(%s))", (TOOL, cc, [x["guid"] for x in removals]))
    for x in removals:
        ledger.propose_removal(TOOL, x["guid"], x["qid"], x["prop"], x["value"], cc, x["reason"],
                               "correction", False)
    return len(removals)


def store(cc: str, decisions: list[dict[str, Any]]) -> None:
    """Replace a country's decision rows."""
    conn = wd.conn()
    with conn.transaction():
        conn.execute("DELETE FROM pcorp_decision WHERE country = %s", (cc,))
        counter: dict[str, int] = {}
        for d in decisions:
            n = counter[d["qid"]] = counter.get(d["qid"], -1) + 1
            conn.execute(
                "INSERT INTO pcorp_decision (country, qid, n, prop, value, detail, disposition, rule, call_key)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (cc, d["qid"], n, d["prop"], d["value"], Jsonb(d["detail"]), d["disposition"], d["rule"],
                 d["call_key"]))
