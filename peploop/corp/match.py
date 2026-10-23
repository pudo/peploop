"""Resolve a seat whose person the body's article names but does not link.

A body's article names far more board members than it links. When a seat
would be written but for the link, the name is searched among human items
(`persons.candidates`), and each candidate with a Wikipedia page is shown,
page and item facts beside the seat's passage, to a narrow model check that
asks one thing: does this person's own page place them at this body, or in
its field? A seat resolves only to the one candidate the check accepts:

- the page names or links the body (`institution`): accepted;
- the page shows a career in the body's field, nothing contradicts, no
  other candidate is accepted and the namesakes are few (`domain`): accepted;
- an item with no page whose own statements name the body (an employer, a
  position or membership of it, or its name in the description; `item`):
  accepted, like the institution tier, without a call;
- anything else is not.

A seat the article does link goes through the same check when nothing ties
its person to the body -- no statement or description of their item names
it, and their page neither links nor names it: an article's link can point
to a namesake (`confirm`).

Answers are kept in `pcorp_call` by content, like the decisions, so a re-run
pays only for seats or pages that changed.
"""

import concurrent.futures as cf
import os
from datetime import date
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict

from peploop import llm, memo
from peploop.corp import decide, persons, wd

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "match_person.md"
MODEL = os.environ.get("PEPCORP_MATCH_MODEL", "claude-sonnet-5-5")
#: The tiers of evidence a person's page can give for a seat, strongest first.
TIERS = ("institution", "domain", "none", "conflict")
#: An item's statements that tie a person to a body when their value, or a
#: qualifier's, is the body: employer, position held, member of, affiliation.
TIE_PROPS = ("P108", "P39", "P463", "P1416")
#: A body's name shorter than this is too ambiguous to find in a description.
NAME_MIN = 5
#: Seat roles as the check reads them.
ROLES = {"head": "head of the executive", "chair": "chair", "deputy_chair": "deputy chair", "member": "member",
         "managing_director": "managing director", "party_secretary": "party secretary"}
#: Paged namesakes up to which a domain-tier match may resolve a seat.
DOMAIN_MAX = 3
BODIES = {"executive": "executive body", "supervisory": "supervisory board or council", "board": "board"}


class Verdict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence: Literal["institution", "domain", "none", "conflict"]
    same_person: bool
    reason: str


def year(claims: list[dict[str, Any]]) -> int | None:
    for c in claims:
        t = (c.get("mainsnak", {}).get("datavalue") or {}).get("value", {})
        if isinstance(t, dict) and "time" in t:
            return int(t["time"][1:5]) if t["time"][0] == "+" else -int(t["time"][1:5])
    return None


def lifespan(entity: dict[str, Any]) -> tuple[int | None, int | None]:
    claims = entity.get("claims", {})
    return year(claims.get("P569", [])), year(claims.get("P570", []))


def dates_fit(entity: dict[str, Any], start: int | None, end: int | None, current: bool, today: int) -> bool:
    """Whether a person's life can hold the seat: of age when it began, alive while it ran."""
    born, died = lifespan(entity)
    begin = start or end or (today if current else None)
    if born is not None and begin is not None and begin - born < 21:
        return False
    if born is not None and current and today - born > 95:
        return False
    if died is not None and begin is not None and died < begin:
        return False
    return True


def excerpt(text: str, names: list[str], chars: int = persons.PAGE_CHARS) -> str:
    """A page's opening, plus the paragraphs further on that name the body."""
    head = text[:chars]
    if len(text) <= chars:
        return head
    folded = [" ".join(persons.fold(n)) for n in names if len(persons.fold(n)) >= 1 and len(n) >= 4]
    more = []
    for para in text[chars:].split("\n"):
        p = " ".join(persons.fold(para))
        if para.strip() and any(f and f in p for f in folded):
            more.append(para.strip())
    tail = "\n".join(more)[:chars // 2]
    return head + ("\n[…]\n" + tail if tail else "\n[…]")


def body_names(entity: dict[str, Any], langs: list[str]) -> list[str]:
    """The body's labels and aliases in the country's languages and English: how a page may name it."""
    out = [entity.get("labels", {}).get(lg, {}).get("value") for lg in langs]
    out += [a["value"] for lg in langs for a in entity.get("aliases", {}).get(lg, [])]
    return list(dict.fromkeys(n for n in out if n))


def item_ties(entity: dict[str, Any], body: str, names: list[str]) -> str | None:
    """How an item's own data names the body, or None: a statement (or its qualifier) or the description."""
    for prop in TIE_PROPS:
        for claim in entity.get("claims", {}).get(prop, []):
            values = [claim.get("mainsnak", {}).get("datavalue", {}).get("value")]
            values += [q.get("datavalue", {}).get("value") for qs in claim.get("qualifiers", {}).values() for q in qs]
            if any(isinstance(v, dict) and v.get("id") == body for v in values):
                return f"{prop} names the body"
    folded = [" ".join(persons.fold(n)) for n in names if len(n) >= NAME_MIN]
    for desc in entity.get("descriptions", {}).values():
        text = f" {' '.join(persons.fold(desc.get('value', '')))} "
        for name in folded:
            if name and f" {name} " in text:
                return f"its description names the body: {desc.get('value', '')!r}"
    return None


def facts(entity: dict[str, Any], labels: dict[str, str]) -> list[str]:
    """An item's identifying statements, one line each, by label."""
    born, died = lifespan(entity)
    lines = [f"- born: {born or 'unknown'}" + (f"; died: {died}" if died else "")]
    for prop, what in (("P27", "citizenship"), ("P106", "occupation"), ("P108", "employer"), ("P39", "position held"),
                       ("P463", "member of"), ("P69", "educated at")):
        vals = [labels.get(q, q) for q in wd.values(entity, prop)]
        if vals:
            lines.append(f"- {what}: " + "; ".join(vals[:12]))
    return lines


def message(seat: dict[str, Any], body: dict[str, Any], cand: dict[str, Any], page: dict[str, Any],
            labels: dict[str, str]) -> str:
    """One candidate for one seat, as the check reads it."""
    e = cand["entity"]
    desc = (e.get("descriptions", {}).get(page["lang"]) or e.get("descriptions", {}).get("en") or {}).get("value", "")
    when = ", ".join(x for x in (f"from {seat['start']}" if seat["start"] else "",
                                 f"until {seat['end']}" if seat["end"] else "",
                                 "held now" if seat["current"] else "") if x) or "undated"
    return "\n".join([
        "# The seat",
        f"Body: {body['qid']} {' / '.join(body['names'][:4])}" + (f" — {body['description']}" if body["description"] else ""),
        f"Kind: {body['kind']}",
        f"Seat: {ROLES.get(seat['role'], seat['role'])} of the {BODIES.get(seat['body'], seat['body'])} ({when})",
        f"Name in the body's article: {seat['name']}",
        f"Passage ({seat['article']}): {seat['quote']}",
        "",
        "# The candidate",
        f"Item: {cand['qid']} {wd_label(e, page['lang'])}" + (f" — {desc}" if desc else ""),
        *facts(e, labels),
        f"Their page links to the body's item: {'yes' if page['links_body'] else 'no'}",
        "",
        f"```page lang={page['lang']} title={page['title']!r}",
        page["text"],
        "```",
    ])


def wd_label(entity: dict[str, Any], lang: str) -> str:
    labels = entity.get("labels", {})
    for lg in (lang, "en", "mul"):
        if lg in labels:
            return labels[lg]["value"]
    return next(iter(labels.values()), {}).get("value", "")


def ask(text: str) -> tuple[Verdict, dict[str, int]]:
    system, _ = llm.system_prompt(PROMPT_PATH)
    response = llm.send(
        model=MODEL, max_tokens=1000, output_config={"effort": "low"},
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": text}], output_format=Verdict)
    if response.parsed_output is None:
        raise RuntimeError(f"no parsed output ({response.stop_reason})")
    return response.parsed_output, llm.usage(response)


def choose(verdicts: dict[str, dict[str, Any]]) -> tuple[str | None, str]:
    """The one candidate a seat resolves to, and why: (QID or None, outcome).

    A candidate counts when the check calls them the same person on the
    institution or the domain tier. One institution-tier candidate wins over
    domain-tier ones; two at the same best tier are namesakes the pages
    cannot tell apart. Among more than `DOMAIN_MAX` namesakes, a field alone
    is too weak: only the institution tier resolves; so it is for a citizen
    of other countries only (`foreign`), where a field is shared by every
    country's namesakes.
    """
    passed = {q: v["evidence"] for q, v in verdicts.items()
              if v.get("same_person") and v.get("evidence") in ("institution", "item", "domain")
              and not (v["evidence"] == "domain" and v.get("foreign"))}
    if not passed:
        return None, "rejected" if verdicts else "no_candidate"
    # A page or an item that names the body is the same strength of evidence.
    for tiers in (("institution", "item"), ("domain",)):
        at = sorted(q for q, t in passed.items() if t in tiers)
        if len(at) > 1:
            return None, "ambiguous"
        if len(at) == 1 and (tiers[0] == "institution" or len(verdicts) <= DOMAIN_MAX):
            return at[0], passed[at[0]]
    return None, "crowded_domain"


def resolve(cc: str, seats: list[dict[str, Any]], wikis: list[str], log: Callable[[str], None] = print,
            today: int | None = None, citizens: frozenset[str] = frozenset(),
            ) -> dict[tuple[str, str], dict[str, Any]]:
    """Match each seat to a person: {(body QID, name): {"qid", "outcome", "verdicts"}}.

    `seats` are the unlinked seats the rules would otherwise write, each
    with its body (`qid`), `kind` and the answer's seat (`seat`); `citizens`
    the country's QIDs, the citizenship a domain-tier match must not lack
    where the item states one. Only seats with a candidate that has a page
    cost a call.
    """
    today = today or date.today().year
    bodies = wd.fetch_items(sorted({s["qid"] for s in seats}), props="labels|aliases|descriptions")

    def gather(s: dict[str, Any]) -> list[dict[str, Any]]:
        seat = s["seat"]
        start = int(seat["start"][:4]) if seat["start"] and seat["start"][:4].isdigit() else None
        end = int(seat["end"][:4]) if seat["end"] and seat["end"][:4].isdigit() else None
        return [c for c in persons.candidates(seat["name"], wikis, s["qid"])
                if dates_fit(c["entity"], start, end, seat["current"], today)]

    jobs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    outcome: dict[tuple[str, str], dict[str, Any]] = {}
    def foreign(entity: dict[str, Any]) -> bool:
        held = set(wd.values(entity, "P27"))
        return bool(citizens and held and not held & citizens)

    with cf.ThreadPoolExecutor(decide.WORKERS) as ex:
        futures = {ex.submit(gather, s): s for s in seats}
        found_by: dict[int, list[dict[str, Any]]] = {}
        for fut in cf.as_completed(futures):
            s = futures[fut]
            try:
                found_by[id(s)] = fut.result()
            except Exception as exc:  # one failed search leaves its seat unresolved, not the run
                log(f"  {s['qid']} {s['seat']['name']}: search failed ({exc.__class__.__name__})")
                found_by[id(s)] = []
    # An item with no page is judged by its own data, without a call: it
    # counts when its statements or description name the body.
    tied: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    for s in seats:
        names = body_names(bodies.get(s["qid"], {}), wikis)
        for c in found_by[id(s)]:
            why = None if c["pages"] else item_ties(c["entity"], s["qid"], names)
            if why:
                tied.setdefault((s["qid"], s["seat"]["name"]), {})[c["qid"]] = {
                    "evidence": "item", "same_person": True, "reason": why, "foreign": False}
        found_by[id(s)] = [c for c in found_by[id(s)] if c["pages"]]
    for s in seats:
        found = found_by[id(s)]
        key = (s["qid"], s["seat"]["name"])
        if key in tied and not found:
            qid, why = choose(tied[key])
            outcome[key] = {"qid": qid, "outcome": why, "verdicts": tied[key]}
        elif not found:
            outcome[key] = {"qid": None, "outcome": "no_candidate", "verdicts": {}}
        elif len(found) > persons.MAX_CANDIDATES:
            # Too many paged namesakes to check; an item tied to the body still counts.
            qid, why = choose(tied[key]) if key in tied else (None, "crowd")
            outcome[key] = {"qid": qid, "outcome": why, "verdicts": tied.get(key, {})}
        else:
            for c in found:
                jobs.append((s, c))
    refs = sorted({q for _, c in jobs for p in ("P27", "P106", "P108", "P39", "P463", "P69")
                   for q in wd.values(c["entity"], p)})
    labels = {q: decide.memo_name(i) for q, i in memo.labels_of(refs, ("en", "mul")).items()}

    def page(s: dict[str, Any], c: dict[str, Any]) -> dict[str, Any]:
        lang = s["seat"]["article"] if s["seat"]["article"] in c["pages"] else c["pages"][0]
        title = c["entity"]["sitelinks"][f"{lang}wiki"]["title"]
        body = bodies.get(s["qid"], {})
        text = excerpt(persons.page_text(lang, title), body_names(body, wikis))
        return {"lang": lang, "title": title, "text": text, "links_body": s["qid"] in persons.page_links(lang, title)}

    def one(s: dict[str, Any], c: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        text = message(s["seat"], body_info(s, bodies.get(s["qid"], {}), wikis), c, page(s, c), labels)
        return c["qid"], {**checked(cc, s, c["qid"], text), "foreign": foreign(c["entity"])}

    verdicts: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    failed: set[tuple[str, str]] = set()
    with cf.ThreadPoolExecutor(decide.WORKERS) as ex:
        futures2 = {ex.submit(one, s, c): (s, c) for s, c in jobs}
        for i, fut in enumerate(cf.as_completed(futures2), 1):
            s, c = futures2[fut]
            key = (s["qid"], s["seat"]["name"])
            try:
                qid, v = fut.result()
            except Exception as exc:  # one failed check leaves its candidate out, not the run
                log(f"  {s['qid']} {s['seat']['name']} {c['qid']}: check failed ({exc.__class__.__name__}: {exc})")
                failed.add(key)
                continue
            verdicts.setdefault(key, {})[qid] = v
            if i % 50 == 0:
                log(f"  checked {i}/{len(jobs)} candidates")
    for s, _ in jobs:
        key = (s["qid"], s["seat"]["name"])
        if key in outcome:
            continue
        vs = {**verdicts.get(key, {}), **tied.get(key, {})}
        # A namesake left unchecked might have passed too: the seat waits for the next run.
        qid, why = (None, "check_failed") if key in failed else choose(vs)
        outcome[key] = {"qid": qid, "outcome": why, "verdicts": vs}
    counts: dict[str, int] = {}
    for o in outcome.values():
        counts[o["outcome"]] = counts.get(o["outcome"], 0) + 1
    log(f"{len(seats)} unlinked seats matched by name: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    return outcome


def body_info(s: dict[str, Any], body: dict[str, Any], wikis: list[str]) -> dict[str, Any]:
    """The body of a seat as the check reads it: its names, kind and description."""
    return {"qid": s["qid"], "kind": s["kind"], "names": body_names(body, wikis) or [s["qid"]],
            "description": (body.get("descriptions", {}).get(s["seat"]["article"])
                            or body.get("descriptions", {}).get("en") or {}).get("value", "")}


def checked(cc: str, s: dict[str, Any], candidate: str, text: str) -> dict[str, Any]:
    """The check's verdict on one candidate for one seat, from the ledger or asked once."""
    _, prompt_hash = llm.system_prompt(PROMPT_PATH)
    key = decide.content_key(MODEL, prompt_hash, text)
    verdict = decide.recorded(key)
    if verdict is None:
        answer, usage = ask(text)
        verdict = answer.model_dump()
        decide.LEDGER.store(key, cc, s["qid"], MODEL, prompt_hash,
                            {"message": text, "seat": s["seat"]["name"], "candidate": candidate}, verdict, usage)
    return verdict


def confirm(cc: str, seats: list[dict[str, Any]], wikis: list[str],
            log: Callable[[str], None] = print) -> set[tuple[str, str]]:
    """The linked seats whose person's own page does not bear them out: {(body QID, name)}.

    `seats` are the seats the rules would write for a person the article
    links (`linked`). One whose item names the body, or whose page links or
    names it, stands without a call; the rest are checked like a matched
    candidate, and stand when the check calls them the same person.
    """
    bodies = wd.fetch_items(sorted({s["qid"] for s in seats}), props="labels|aliases|descriptions")
    people = wd.fetch_items(sorted({s["person"] for s in seats}),
                            props="labels|aliases|descriptions|claims|sitelinks")
    jobs: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []

    def tie(s: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]] | None:
        """None when the person is tied to the body; else the candidate and page to check."""
        entity = people.get(s["person"]) or {}
        names = body_names(bodies.get(s["qid"], {}), wikis)
        if item_ties(entity, s["qid"], names):
            return None
        langs = [s["seat"]["article"], *wikis]
        lang = next((lg for lg in langs if f"{lg}wiki" in entity.get("sitelinks", {})), None)
        if lang is None:
            return None  # no page to read: the article's link stands
        title = entity["sitelinks"][f"{lang}wiki"]["title"]
        links_body = s["qid"] in persons.page_links(lang, title)
        text = persons.page_text(lang, title)
        folded = " ".join(persons.fold(text))
        if links_body or any(f" {' '.join(persons.fold(n))} " in f" {folded} " for n in names if len(n) >= NAME_MIN):
            return None
        return ({"qid": s["person"], "entity": entity, "pages": [lang]},
                {"lang": lang, "title": title, "text": excerpt(text, names), "links_body": False})

    with cf.ThreadPoolExecutor(decide.WORKERS) as ex:
        futures = {ex.submit(tie, s): s for s in seats}
        for fut in cf.as_completed(futures):
            s = futures[fut]
            try:
                found = fut.result()
            except Exception as exc:  # a failed read leaves the seat as the article links it
                log(f"  {s['qid']} {s['seat']['name']}: page not read ({exc.__class__.__name__})")
                continue
            if found:
                jobs.append((s, *found))
    refs = sorted({q for _, c, _ in jobs for p in ("P27", "P106", "P108", "P39", "P463", "P69")
                   for q in wd.values(c["entity"], p)})
    labels = {q: decide.memo_name(i) for q, i in memo.labels_of(refs, ("en", "mul")).items()}
    out: set[tuple[str, str]] = set()

    def one(s: dict[str, Any], c: dict[str, Any], page: dict[str, Any]) -> bool:
        text = message(s["seat"], body_info(s, bodies.get(s["qid"], {}), wikis), c, page, labels)
        v = checked(cc, s, c["qid"], text)
        return bool(v.get("same_person") and v.get("evidence") in ("institution", "domain"))

    with cf.ThreadPoolExecutor(decide.WORKERS) as ex:
        futures2 = {ex.submit(one, *job): job[0] for job in jobs}
        for fut in cf.as_completed(futures2):
            s = futures2[fut]
            try:
                if not fut.result():
                    out.add((s["qid"], s["seat"]["name"]))
            except Exception as exc:  # a failed check leaves the seat as the article links it
                log(f"  {s['qid']} {s['seat']['name']}: check failed ({exc.__class__.__name__}: {exc})")
    log(f"{len(seats)} linked seats; {len(jobs)} without a tie to the body checked; {len(out)} not borne out")
    return out


def linked(decisions: list[dict[str, Any]], answered: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The seats the rules would write for a person the article links, with their body's kind, the answer's seat and the person."""
    reqs = {r["qid"]: r for r in answered}
    out, seen = [], set()
    for d in decisions:
        if (d["disposition"] != "apply" or d["detail"].get("via") not in ("link", "anchor")
                or d["qid"] not in reqs or not d["value"]):
            continue
        name = d["detail"].get("name")
        seat = next((s for s in reqs[d["qid"]]["answer"]["seats"] if s["name"] == name), None)
        if seat is None or (d["qid"], name) in seen:
            continue
        seen.add((d["qid"], name))
        out.append({"qid": d["qid"], "kind": reqs[d["qid"]]["answer"]["kind"], "seat": seat, "person": d["value"]})
    return out


def unlinked(decisions: list[dict[str, Any]], answered: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The seats the rules left for want of a linked person, with their body's kind and the answer's seat."""
    reqs = {r["qid"]: r for r in answered}
    out, seen = [], set()
    for d in decisions:
        if d["rule"] != "person_unlinked" or d["qid"] not in reqs:
            continue
        name = d["detail"].get("name")
        req = reqs[d["qid"]]
        seat = next((s for s in req["answer"]["seats"] if s["name"] == name), None)
        if seat is None or (d["qid"], name) in seen:
            continue
        seen.add((d["qid"], name))
        out.append({"qid": d["qid"], "kind": req["answer"]["kind"], "seat": seat})
    return out

