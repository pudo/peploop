"""Turn each answer into statements, and decide each one apply or skip.

A body passes its gates first -- it is an enterprise or a state institution,
it is active, the article says a state controls it, at a tier the country's
spec writes -- or nothing is written on it. Then three kinds of statement:

- on an enterprise, the marker `P31 Q270791`, unless the item is already
  typed or given that legal form through any subclass;
- a link to each public body the answer names over it: `P127` for an owner,
  `P749` for a parent it is part of or subordinate to, unless the loaded
  chain already reaches that body through another. The body must be a state
  actor, a government body, or one this run finds state-controlled; a body
  whose named owners and parents are all something else is not written on;
- one leadership statement per seat (`SEATS`, by kind, body and role, plus
  the spec's `roles`), for a person the article links to an item of a human.

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

from peploop import ledger, policy, propose, route, typegraph
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
#: The kinds of body that are written on: a state's businesses, and the
#: institutions it runs (museums, broadcasters, research centres, agencies).
WRITTEN = ("enterprise", "institution")
#: (kind, body, role) → (property, role qualifier `P2868` or None). A "*" fits any.
SEATS: dict[tuple[str, str, str], tuple[str, str | None]] = {
    ("enterprise", "*", "head"): ("P169", None),
    ("enterprise", "executive", "chair"): ("P169", None),  # the chair of the executive body is its head
    ("institution", "*", "head"): ("P1037", None),  # director / manager
    ("institution", "executive", "chair"): ("P1037", None),
    ("enterprise", "supervisory", "chair"): ("P488", "Q15818143"),  # chairman of the supervisory board
    ("institution", "supervisory", "chair"): ("P488", None),
    ("*", "board", "chair"): ("P488", None),
    ("*", "supervisory", "member"): ("P5052", None),  # supervisory board member
    ("*", "supervisory", "deputy_chair"): ("P5052", "Q1127270"),  # deputy chairperson
    ("*", "*", "deputy_chair"): ("P3320", "Q1127270"),
    ("*", "executive", "member"): ("P3320", "Q141755781"),  # executive board member (pepcorp's own role item)
    ("*", "board", "member"): ("P3320", None),
    ("*", "*", "managing_director"): ("P3320", "Q19940089"),  # managing director
}
#: Short tokens with a full stop that are titles, not names: "Dr.", "Prof.".
HONORIFIC = re.compile(r"^\w{1,5}\.$")


def seat_statement(kind: str, body: str, role: str,
                   extra: dict[str, tuple[str, str | None]] | None = None) -> tuple[str, str | None] | None:
    """The statement a seat becomes: the country's own row for its role, else the most specific of `SEATS`."""
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
    tokens = [t for t in text.split() if not HONORIFIC.match(t)]
    return " ".join(re.sub(r"[^\w-]", "", t) for t in tokens if re.sub(r"[^\w-]", "", t))


def quoted(quote: str | None, message: str) -> bool:
    """Whether a quote is in the text the model was shown, whitespace and case normalised."""
    if not quote:
        return False
    return " ".join(quote.split()).casefold() in " ".join(message.split()).casefold()


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


def gate(answer: dict[str, Any], message: str, tiers: tuple[str, ...] = countries.DEFAULT_TIERS) -> str | None:
    """Why nothing is written on this body, or None when it passes."""
    control = answer["control"]
    if answer["kind"] not in WRITTEN:
        return f"kind:{answer['kind']}"
    if not answer["active"]:
        return "inactive"
    if control["verdict"] != "state":
        return f"control:{control['verdict']}"
    if control["level"] not in tiers:
        return f"level:{control['level']}"
    if not quoted(control["quote"], message):
        return "control_unquoted"
    return None


def source(req: dict[str, Any], lang: str | None) -> list[dict[str, Any]]:
    """The article a value was read in, as peploop's planner takes it."""
    art = next((a for a in req["articles"] if a["lang"] == lang), None)
    return [art] if art else []


def control_rows(req: dict[str, Any], entity: dict[str, Any], chain: list[str] | None,
                 state: set[str], closure: dict[str, set[str]],
                 named: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """The marker and link rows of a body that passed its gates.

    The marker goes on an enterprise only: a museum or a broadcaster is no
    state-owned enterprise, and its links are what find it. One `P127` or
    `P749` per public body the answer names over it, each with its quote.
    `state` is every body that counts as the state's; `named` resolves a
    controller the answer named rather than chose (name → QID).
    """
    answer = req["answer"]
    control = answer["control"]
    rows = []
    if answer["kind"] == "enterprise":
        marks = {t for p in ("P31", "P1454") for v in wd.values(entity, p) for t in closure.get(v, {v})}
        rows.append({"property": "P31", "value": item(MARKER),
                     "qualifiers": {"_sources": source(req, control["article"])},
                     "_rule": "marked" if marks & MARKED else None})
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
        rule = None
        if not quoted(owner["quote"], req["message"]):
            rule = "owner_unquoted"
        elif qid not in state:
            # Being on the loaded chain is not enough: a chain can run
            # through a minority stake, and the body must itself be a state
            # actor, a government body or one this run finds state-controlled.
            rule = "controller_not_state"
        elif chain and qid in chain[2:]:
            rule = "chain_reaches"
        rows.append({"property": prop, "value": item(qid),
                     "qualifiers": {"_sources": source(req, owner["article"])}, "_rule": rule})
    return rows


#: Why a marker is proposed for removal, as the edit summary says it.
REMOVAL_REASONS = {
    "municipal": "a municipal company, not a state-owned enterprise (its Wikipedia article)",
    "private": "not state-controlled: its Wikipedia article says it is privately owned",
}


def correction(req: dict[str, Any], entity: dict[str, Any], closure: dict[str, set[str]],
               tiers: tuple[str, ...]) -> tuple[str | None, list[dict[str, Any]], list[dict[str, Any]]]:
    """A marker the answer contradicts: (kind of correction, rows to add, statements to propose removing).

    A body the article shows to be municipal, while the tier is not written,
    keeps no state-enterprise marker and gains the municipal one; a body it
    shows to be private keeps neither. Nothing else is written on either.
    """
    answer = req["answer"]
    control = answer["control"]
    if answer["kind"] not in WRITTEN or not answer["active"] or not quoted(control["quote"], req["message"]):
        return None, [], []
    def marked(claim: dict[str, Any], roots: frozenset[str]) -> bool:
        v = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        return isinstance(v, dict) and bool(closure.get(v.get("id"), {v.get("id")}) & roots)
    claims = [c for c in entity.get("claims", {}).get("P31", []) if c.get("rank") != "deprecated"]
    if control["verdict"] == "state" and control["level"] == "municipal" and "municipal" not in tiers:
        wrong = [c for c in claims if marked(c, frozenset({MARKER})) and not marked(c, frozenset({MUNICIPAL}))]
        if not wrong:
            return None, [], []
        add = [] if any(marked(c, frozenset({MUNICIPAL})) for c in claims) else [
            {"property": "P31", "value": item(MUNICIPAL), "qualifiers": {"_sources": source(req, control["article"])},
             "_rule": None}]
        return "municipal", add, wrong
    if control["verdict"] == "private" and answer["kind"] == "enterprise":
        wrong = [c for c in claims if marked(c, MARKED)]
        return ("private", [], wrong) if wrong else (None, [], [])
    return None, [], []


def seat_rule(seat: dict[str, Any], start: dict[str, Any] | None, end: dict[str, Any] | None,
              today: date) -> str | None:
    """Why a seat is not written, from its dates and currency alone."""
    year = lambda t: int(t["time"][1:5]) if t else None  # noqa: E731
    if start and end and end["time"] < start["time"]:
        return "bad_dates"
    if start and year(start) > today.year:
        return "future"
    if seat["current"] and end:
        return "current_ended"
    if not start and not end and not seat["current"]:
        return "undated_former"
    latest = year(end) or year(start)
    if latest is not None and latest < today.year - policy.P39_MAX_ENDED_YEARS:
        return "tenure_ended"
    if not end and not seat["current"] and start and year(start) <= today.year - policy.OPEN_TERM_YEARS:
        return "open_unattested"
    return None


#: The two properties a body's head is written with; a person holds one of them, never both.
HEADS = ("P169", "P1037")


def seat_rows(req: dict[str, Any], humans: set[str], today: date,
              extra: dict[str, tuple[str, str | None]] | None = None,
              entity: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """One leadership row per seat the answer lists."""
    heads = {p: set(wd.values(entity or {}, p)) for p in HEADS}
    rows = []
    for seat in req["answer"]["seats"]:
        statement = seat_statement(req["answer"]["kind"], seat["body"], seat["role"], extra)
        if statement is None:
            rows.append({"property": "seat", "value": None, "qualifiers": {}, "_rule": f"role_unmapped:{seat['role']}",
                         "_name": seat["name"]})
            continue
        prop, role = statement
        start = propose.time_value(seat["start"]) if seat["start"] else None
        end = propose.time_value(seat["end"]) if seat["end"] else None
        found = linked(seat["name"], seat["article"], req["links"])
        rule = None
        if not quoted(seat["quote"], req["message"]):
            rule = "seat_unquoted"
        elif not found:
            rule = "person_unlinked"
        elif len(found) > 1:
            rule = "person_ambiguous"
        elif found[0] not in humans:
            rule = "not_human"
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
                     "qualifiers": quals, "_rule": rule, "_name": seat["name"]})
    return rows


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
        decisions.append({"qid": r["qid"], "prop": row["property"], "value": value, "detail": detail,
                          "disposition": disposition, "rule": rule, "call_key": r.get("key")})
    return routed.lines


def decide(cc: str, answered: list[dict[str, Any]], items: dict[str, dict[str, Any]],
           actors: actormod.Actors, spec: countries.Spec | None = None, today: date | None = None,
           ) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    """Plan every answered body against its live item: (lines, decision rows, proposed removals)."""
    today = today or date.today()
    spec = spec or countries.get(cc)
    passed = {r["qid"]: r for r in answered if gate(r["answer"], r["message"], spec.tiers) is None}
    # Bodies the answer gates out but whose existing marker it contradicts.
    marked_now = {qid for qid, it in items.items()
                  if wd.values(it.get("entity") or {}, "P31") or wd.values(it.get("entity") or {}, "P1454")}
    contradicted = {r["qid"] for r in answered if r["qid"] not in passed and r["qid"] in marked_now
                    and (r["answer"]["control"]["level"] == "municipal" or r["answer"]["control"]["verdict"] == "private")}
    entities = wd.fetch_items(sorted(set(passed) | contradicted)) if passed or contradicted else {}
    marks = {v for e in entities.values() for p in ("P31", "P1454") for v in wd.values(e, p)}
    closure = typegraph.of_classes(marks)
    names = sorted({q for r in passed.values() for s in r["answer"]["seats"]
                    for q in linked(s["name"], s["article"], r["links"])})
    people = wd.fetch_items(names, props="claims") if names else {}
    humans = {q for q, e in people.items() if "Q5" in wd.values(e, "P31")}
    # Controllers the answers named rather than chose, resolved through the
    # article's links, count when they are a government body of the country.
    named: dict[str, dict[str, str]] = {}
    for r in passed.values():
        for o in r["answer"]["control"]["owners"]:
            if o["controller"] is None and o["name"]:
                found = linked(o["name"], o["article"], r["links"])
                if len(found) == 1:
                    named.setdefault(r["qid"], {})[o["name"]] = found[0]
    government = actors.is_government({q for m in named.values() for q in m.values()})
    # A body this run finds state-controlled is a state owner in its own right:
    # a state bank's subsidiary is held through the bank.
    state = set(passed) | set(actors.kinds) | government
    lines: list[str] = []
    decisions: list[dict[str, Any]] = []
    removals: list[dict[str, Any]] = []
    for r in answered:
        why = gate(r["answer"], r["message"], spec.tiers)
        if why is not None:
            kind, add, wrong = (correction(r, entities[r["qid"]], closure, spec.tiers)
                                if r["qid"] in contradicted and r["qid"] in entities else (None, [], []))
            decisions.append({"qid": r["qid"], "prop": "-", "value": None, "detail": {},
                              "disposition": "skip", "rule": why, "call_key": r.get("key")})
            if kind:
                lines += settle(r, entities[r["qid"]], add, decisions)
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
        chain = items.get(r["qid"], {}).get("chain")
        rows = control_rows(r, entity, chain, state, closure, named.get(r["qid"]))
        links = [row for row in rows if row["property"] in RELATIONS.values() and row["value"] is not None]
        if links and not any(row["_rule"] in (None, "chain_reaches") for row in links):
            # Every body the answer names over it is no state body: the
            # control it claims runs through someone else's company.
            decisions.append({"qid": r["qid"], "prop": "-", "value": None, "detail": {},
                              "disposition": "skip", "rule": "no_state_owner", "call_key": r.get("key")})
            continue
        rows += seat_rows(r, humans, today, spec.roles, entity)
        lines += settle(r, entity, rows, decisions)
    return lines, decisions, removals


def queue_removals(cc: str, removals: list[dict[str, Any]]) -> int:
    """Queue each contradicted marker for removal: it waits for `removals approve`, being another editor's."""
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
