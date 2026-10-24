"""Expand each member state's listed functions into the Wikidata items they stand for.

The AMLR asset (`amlr.py`) holds every row of the states' Art. 43 lists as
the notice gives it. A lane can only act on items, so each usable row grows
an `expansion`: the position item a row names, the body whose seats it names,
the level whose unit heads it names, or the pepcorp tier whose bodies it
names. Reach for this when a country's list should say which items it means:
peploop and peptree read the positions and levels, pepcorp the bodies and
tiers, and `amlr_report` reads them all back as coverage.

A row names its item in text, and a name search alone was right for barely
half of a sample of bodies, so nothing is matched by name:

- `position` and `body` rows search Wikidata and the state's Wikipedia by
  the row's local name, then its English one. Candidates must be the right
  sort of thing (`admit`): an office for a position, an organisation that is
  neither an office, a person, a building nor a place for a body; of the
  state, unless the row is an international organisation's; neither
  abolished nor dissolved. A model shown the row and the candidates picks
  the one that is exactly what the row names, or none (`prompts/amlr_match.md`),
  and the pick still has to pass `settle`: no namesake shown beside it, no
  ministry for a row that names its enterprise.
- `body_class` rows are read by a model that knows the state's unit levels
  (`prompts/amlr_class.md`): the head of every unit of a level becomes
  `{level, office: head}`, a class of state bodies `{tier, bodies}`.

The model also reads each row's `kind` and `amlr`; where it is sure the
keyword classifier was wrong on an unreviewed row, the row is corrected and
marked `checked`, and is tried again under its new kind. Answers are kept in
`pcorp_call` by content, so a re-run pays only for rows whose candidates
changed. Rows already expanded are left as they are: a re-run tries the rest,
so the asset grows and hand edits survive. Each run writes what it saw and
decided per row to `data/amlr/<cc>-expand-<date>.jsonl`.
"""

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict
from rigour.langs import iso_639_alpha2
from rigour.territories import get_territory

from peploop import amlr, db, eras, http, llm, memo, offices, positions, typegraph, verdict, wikidata
from peploop.classes import LIST_ARTICLES, ORGANISATION, POSITION_METACLASSES, SENDER_CLASS, TERRITORY, TYPE_OF_POSITION
from peploop.text import fold
from peploop.verdict import LINK_VERDICTS, Confidence

PROMPTS = Path(__file__).resolve().parent / "prompts"
MATCH_PROMPT = PROMPTS / "amlr_match.md"
CLASS_PROMPT = PROMPTS / "amlr_class.md"
MODEL = os.environ.get("PEPLOOP_AMLR_MODEL", "claude-sonnet-5-5")
#: pepcorp's answer ledger, under `amlr:<cc>`: the bodies are pepcorp's anyway.
LEDGER = llm.Ledger("pcorp_call")
PASS = "corp:amlr"
OUT = Path(__file__).resolve().parents[1] / "data" / "amlr"
#: Candidates the model reads, best named first.
SHOWN = 8
#: Hits read per search; past this a name is a crowd anyway.
SEARCH_LIMIT = 10
#: Content words a full-text query keeps: every word must match, so a long
#: title written out in full ("... of the Republic of Lithuania") finds nothing.
QUERY_WORDS = 6
#: What a ministry is; a ministry picked for a row that names no ministry is
#: the parent of the body the row names (seen: ROMTEHNICA -> its ministry).
MINISTRY = "Q192350"
#: The word stems a row names a ministry by, folded: Greek folds to "ypourg".
MINISTRY_WORDS = ("minis", "ypourg", "departement")
HUMAN = "Q5"
#: What a class of offices is typed: "type of position", "class of ambassadors
#: of a country" ("ambassador of Belgium" is every Belgian embassy's head, not one office).
OFFICE_CLASSES = frozenset({TYPE_OF_POSITION, "Q29918328"})
WORKERS = 6

STOPWORDS = frozenset("""of the and for in at to on a an de la le les du des der die das und von für zu el los las
y del da do dos di della e et""".split())


# --- the rows' names and the searches ---------------------------------------------

PAREN = re.compile(r"\(([^()]*)\)")
QUOTED = re.compile(r"[‘'“\"„«]([^’'”\"“»]{3,})[’'”\"“»]")
ACRONYM = re.compile(r"^[A-ZĂÂÎȘȚŞŢ.\- ]{2,8}$")
TRAIL = " ,;:.-–"
ROMANIAN = str.maketrans("şţŞŢ", "șțȘȚ")


def _clean(text: str | None) -> str:
    return " ".join((text or "").split()).strip(TRAIL)


def row_names(row: dict[str, Any]) -> list[tuple[str, bool]]:
    """The names a row gives its item, each with whether it is in the state's language; local first.

    A body row names the body (`organisation`, or the function text when
    it has none); a position row names the office. A parenthesis or a quote
    inside a name is usually the local name or the body's own short name; a
    bare acronym in one is as often a ministry's, and is left out.
    """
    local: list[str] = [_clean(row.get("local"))]
    english: list[str] = []
    texts = ([row.get("organisation") or row.get("position")] if row["kind"] == "body"
             else [row.get("position")])
    for text in texts:
        text = _clean(text)
        if row["kind"] == "body" and not row.get("organisation"):
            # "members of the Board of Directors of the Central Bank": the body comes last.
            tail = re.split(r"\bof the\b|,", PAREN.sub(" ", text))[-1]
            if _clean(tail) and _clean(tail) != _clean(PAREN.sub(" ", text)):
                english.append(_clean(tail))
        for inner in PAREN.findall(text) + QUOTED.findall(text):
            inner = _clean(inner)
            if inner and not ACRONYM.match(inner) and len(inner) > 3:
                local.append(inner)
        english.append(_clean(PAREN.sub(" ", text)))
    if row.get("lang") == "RUM":
        # The sheet writes Romanian with cedillas; Wikidata's labels with commas.
        local = [n.translate(ROMANIAN) for n in local]
    out: dict[str, bool] = {}
    for name in local:
        if name:
            out.setdefault(name, True)
    for name in english:
        if name and len(name) > 3:
            out.setdefault(name, False)
    return list(out.items())[:3]


def query_words(name: str, drop: frozenset[str] = frozenset()) -> str:
    """A name's content words, longest first, as an all-words query; `drop` is what the scope already says."""
    words = [w for w in re.findall(r"\w+", name) if len(w) > 2 and w.lower() not in STOPWORDS | drop]
    return " ".join(sorted(words, key=len, reverse=True)[:QUERY_WORDS])


def search_entities(name: str, lang: str) -> list[str]:
    """Items whose label or alias begins with the name."""
    data = http.get_json(wikidata.WD_API, params={
        "action": "wbsearchentities", "format": "json", "type": "item", "search": name[:250],
        "language": lang, "uselang": lang, "strictlanguage": "false", "limit": SEARCH_LIMIT})
    return [h["id"] for h in data.get("search", []) if "id" in h]


def cirrus(query: str) -> list[str]:
    """Items Wikidata's full-text search finds for a query (`haswbstatement` and all)."""
    data = http.get_json(wikidata.WD_API, params={
        "action": "query", "format": "json", "list": "search", "srnamespace": 0, "srsearch": query,
        "srlimit": SEARCH_LIMIT, "srprop": ""})
    return [h["title"] for h in data.get("query", {}).get("search", []) if amlr.QID.match(h.get("title", ""))]


def search_pages(name: str, lang: str) -> list[str]:
    """The items of the pages a Wikipedia's own search ranks first for the name."""
    data = http.get_json(f"https://{lang}.wikipedia.org/w/api.php", params={
        "action": "query", "format": "json", "generator": "search", "gsrsearch": name[:250], "gsrlimit": 3,
        "gsrnamespace": 0, "prop": "pageprops", "ppprop": "wikibase_item", "redirects": 1})
    pages = sorted(data.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
    return [p["pageprops"]["wikibase_item"] for p in pages if p.get("pageprops", {}).get("wikibase_item")]


def io_row(row: dict[str, Any]) -> bool:
    """A row of an international organisation or the Union: its item has no state to match."""
    return row["amlr"] in ("ix_io", "eu")


#: Full-text filters: an office's metaclasses, and anything but a person (a
#: search for a title otherwise returns its holders first).
OFFICE_TYPES = "haswbstatement:P31=Q4164871|P31=Q294414|P31=Q17279032"
NOT_HUMAN = "-haswbstatement:P31=Q5"


def found(row: dict[str, Any], state: str | None, country: str, langs: list[str]) -> list[str]:
    """The items any search finds for a row, in the order found.

    Each name by label prefix; an office's English name with the state's name
    after it, the way its label is usually written; full text among the
    state's items (or an office's among offices); and a body's name in the
    state's Wikipedia.
    """
    names = row_names(row)
    if not names:
        return []
    own = langs[0] if langs else "en"
    local = not io_row(row) and state is not None
    scope = f"haswbstatement:P17={state}|P1001={state} " if local else ""
    # Within the state's items its name is said already, and a label may not repeat it.
    drop = frozenset({"republic", *country.lower().split()}) if local else frozenset()
    out: list[str] = []
    for name, is_local in names:
        out += search_entities(name, own if is_local else "en")
    if row["kind"] == "position":
        english = next((n for n, is_local in names if not is_local), names[0][0])
        if local:
            out += search_entities(f"{english} of {country}", "en")
        words = query_words(english, drop)
        if words:
            out += cirrus(f"{scope}{OFFICE_TYPES} {words}")
            out += cirrus(f"{scope}{NOT_HUMAN} {words}")
    else:
        name, is_local = names[0]
        words = query_words(name, drop)
        if words:
            out += cirrus(f"{scope}{NOT_HUMAN} {words}")
        out += search_pages(name, own if is_local else "en")
    return list(dict.fromkeys(out))


# --- what a candidate must be ------------------------------------------------------


def _values(entity: dict[str, Any], prop: str) -> list[str]:
    return wikidata.claim_qids(entity, prop, include_deprecated=False)


def admit(kind: str, entity: dict[str, Any], closure: set[str], current: set[str],
          scope_states: dict[str, list[str]], io: bool, state_names: list[str]) -> str | None:
    """Why a found item cannot be what a row of this kind names, or None to show it.

    `closure` is the item's type closure, `current` the state's QIDs,
    `scope_states` each `P1001` target's own `P17` (an office of one of the
    state's units is the state's), `io` whether the row is an international
    organisation's (no state to match), `state_names` the state's names (a
    position stating no country must name it).
    """
    types = set(_values(entity, "P31"))
    if HUMAN in types:
        return "person"
    if types & LIST_ARTICLES:
        return "list"
    if kind == "position":
        if not closure & POSITION_METACLASSES:
            return "not_position"
        if types & OFFICE_CLASSES or SENDER_CLASS in _values(entity, "P279"):
            return "class_of_offices"
        if positions.is_generic(entity.get("id")):
            return "generic"
        if offices.dissolved(entity) or wikidata.claim_time(entity, "P582", include_deprecated=False):
            return "abolished"
    else:
        if ORGANISATION not in closure:
            return "not_organisation"
        if types & POSITION_METACLASSES:
            return "office"
        if closure & TERRITORY:
            return "place"
        if offices.dissolved(entity):
            return "dissolved"
    if io:
        return None
    p17 = set(_values(entity, "P17"))
    p1001 = _values(entity, "P1001")
    now = set(offices._unended(entity, "P17"))
    if kind == "position" and now & current and now - current:
        # One item for the supreme-court judges of four Nordic states is none of theirs;
        # a predecessor state's ended P17 is history, not a second state.
        return "several_states"
    if placed(entity, current, scope_states):
        return None
    if p17 or any(scope_states.get(q) for q in p1001):
        return "other_country"
    if kind == "position" and not any(offices.names_state(n, state_names) for n in _names(entity)):
        return "stateless"
    return None


def placed(entity: dict[str, Any], current: set[str], scope_states: dict[str, list[str]]) -> bool:
    """Whether an item states the state as its country or jurisdiction, or a unit of it."""
    p1001 = _values(entity, "P1001")
    return bool((set(_values(entity, "P17")) | set(p1001)) & current
                or any(set(scope_states.get(q, ())) & current for q in p1001))


def _names(entity: dict[str, Any]) -> list[str]:
    names = [v["value"] for v in entity.get("labels", {}).values()]
    return names + [a["value"] for al in entity.get("aliases", {}).values() for a in al]


def name_score(row_texts: list[str], entity: dict[str, Any]) -> float:
    """How closely an item's names meet the row's: 3 for an equal name, 2 for one inside the other, else word overlap."""
    best = 0.0
    mine = [k for k in (offices.label_key(t) for t in row_texts) if k]
    for name in _names(entity):
        theirs = offices.label_key(name)
        if not theirs:
            continue
        for key in mine:
            if key == theirs:
                return 3.0
            if f" {theirs} " in f" {key} " or f" {key} " in f" {theirs} ":
                best = max(best, 2.0)
            a, b = set(key.split()), set(theirs.split())
            best = max(best, len(a & b) / max(len(a | b), 1))
    return best


# --- the model's answers ------------------------------------------------------------


class Match(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal[amlr.KINDS]
    amlr: Literal[amlr.CATEGORIES]
    pick: int | None
    verdict: Literal[LINK_VERDICTS]
    confidence: Confidence
    reason: str


class ClassAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal[amlr.KINDS]
    amlr: Literal[amlr.CATEGORIES]
    target: Literal["level", "tier", "none"]
    level: Literal[amlr.LEVELS] | None
    tier: Literal[amlr.TIERS] | None
    bodies: Literal[amlr.BODY_KINDS] | None
    confidence: Confidence
    reason: str


@dataclass
class Candidate:
    """One admitted item as the model reads it and `settle` judges it."""

    qid: str
    label: str
    lines: list[str]
    #: The item is a ministry, the parent a body row must not be matched to.
    ministry: bool = False
    #: The words of the item's English and multilingual names, folded.
    words: frozenset[str] = frozenset()
    #: The item states the row's state (or is an international organisation's):
    #: a namesake that states none, a class most often, does not make it ambiguous.
    placed: bool = True


def row_text(row: dict[str, Any]) -> str:
    return " ".join(_clean(row.get(k)) for k in ("position", "local", "organisation", "notes"))


def io_title(row: dict[str, Any]) -> list[str]:
    """An international organisation's row's title: its words before the organisation's name.

    "Head of office of the UNHCR, ..." or "Secretary for Ibero-American
    Cooperation, SGI": a state lists the functions seated in it, often a local
    office's or a lesser secretary's, which a model reads up to the head.
    """
    title = re.split(r",| - | – ", PAREN.sub(" ", _clean(row.get("position"))))[0]
    return offices.label_key(title).split()


def names_ministry(text: str) -> bool:
    folded = fold(text)
    return any(w in folded for w in MINISTRY_WORDS)


def settle(row: dict[str, Any], shown: list[Candidate], answer: Match) -> tuple[dict[str, Any] | None, str]:
    """The expansion entry an answer gives a row, or None; and the outcome's name.

    The model's pick stands only when it is supported above low confidence,
    on the row's own kind (a reviewed row's kind stands whatever the model
    reads), on the list, alone under its name among the items placed in the
    state, and not the ministry above a body the row names. An international
    organisation's office must carry every word of the row's title.
    """
    if answer.kind != row["kind"] and not row.get("checked"):
        return None, "kind_differs"
    if answer.pick is None or not verdict.accepts(answer.verdict, answer.confidence):
        return None, "no_match"
    if not 0 <= answer.pick < len(shown):
        return None, "off_list"
    pick = shown[answer.pick]
    key = offices.label_key(pick.label)
    if key and any(offices.label_key(c.label) == key and (c.placed or not pick.placed)
                   for c in shown if c.qid != pick.qid):
        return None, "homonym"
    if row["kind"] == "body" and pick.ministry and not names_ministry(row_text(row)):
        return None, "parent_ministry"
    if row["kind"] == "position" and io_row(row) and not set(io_title(row)) <= pick.words:
        return None, "io_title"
    return {row["kind"]: pick.qid, "by": "model"}, "matched"


def class_entry(row: dict[str, Any], levels: set[str], answer: ClassAnswer) -> tuple[dict[str, Any] | None, str]:
    """The rule a body-class row stands for, or None; and the outcome's name.

    A level rule needs a level the state's file lists units for; a tier rule
    a tier and a kind of body.
    """
    if answer.kind != "body_class" and not row.get("checked"):
        return None, "kind_differs"
    if answer.confidence == verdict.LOW:
        return None, "low_confidence"
    if answer.target == "level":
        if answer.level not in levels:
            return None, "no_such_level"
        return {"level": answer.level, "office": "head", "by": "model"}, "level"
    if answer.target == "tier" and answer.tier and answer.bodies:
        return {"tier": answer.tier, "bodies": answer.bodies, "by": "model"}, "tier"
    return None, "no_rule"


def fixes(row: dict[str, Any], kind: str, category: str, confidence: str) -> dict[str, Any]:
    """The corrections a sure reading makes to an unreviewed row's `kind` and `amlr`."""
    if row.get("checked") or confidence != "high":
        return {}
    out = {}
    if kind != row["kind"]:
        out["kind"] = kind
    if category != row["amlr"]:
        out["amlr"] = category
    return out


# --- rendering -----------------------------------------------------------------------


def _label(info: dict[str, Any] | None) -> str:
    labels = (info or {}).get("labels", {})
    for lang in ("en", "mul"):
        if lang in labels:
            return labels[lang]
    return next(iter(sorted(labels.values())), "")


def candidate(entity: dict[str, Any], closure: set[str], langs: list[str], labels: dict[str, Any],
              placed: bool = True) -> Candidate:
    """An admitted item, as lines the model reads."""
    qid = entity.get("id", "")
    names = entity.get("labels", {})
    fallback: dict[str, str] = next(iter(names.values()), {})
    label = next((names[lg]["value"] for lg in ("en", "mul", *langs) if lg in names), fallback.get("value", qid))
    shown = [f"{lg} \"{names[lg]['value']}\"" for lg in dict.fromkeys(["en", "mul", *langs]) if lg in names]
    aliases = [a["value"] for lg in ("en", *langs) for a in entity.get("aliases", {}).get(lg, [])][:4]
    descs = entity.get("descriptions", {})
    desc = next((descs[lg]["value"] for lg in ("en", *langs) if lg in descs), None)
    lines = [f"{qid}: " + "; ".join(shown) + (f" (also: {'; '.join(aliases)})" if aliases else "")]
    if desc:
        lines.append(f"description: {desc}")
    for prop, what in (("P31", "instance of"), ("P279", "subclass of"), ("P17", "country"), ("P1001", "jurisdiction"),
                       ("P361", "part of"), ("P2389", "office of"), ("P749", "parent organisation"),
                       ("P127", "owned by")):
        vals = [_label(labels.get(q)) or q for q in _values(entity, prop)][:5]
        if vals:
            lines.append(f"{what}: " + "; ".join(vals))
    ended = wikidata.claim_time(entity, "P576", include_deprecated=False)
    if ended:
        lines.append(f"dissolved or abolished: {ended}")
    words = frozenset(w for lg in ("en", "mul") for n in [names.get(lg, {}).get("value", "")]
                      + [a["value"] for a in entity.get("aliases", {}).get(lg, [])]
                      for w in offices.label_key(n).split())
    return Candidate(qid=qid, label=label, lines=lines, ministry=MINISTRY in closure, words=words, placed=placed)


def match_message(row: dict[str, Any], country: str, shown: list[Candidate]) -> str:
    want = "a position item (the office)" if row["kind"] == "position" else "a body item (the organisation)"
    p = ["# The row", f"Country: {country}", f"Function: {_clean(row.get('position')) or '(empty)'}"]
    for key, what in (("local", "In the state's language"), ("organisation", "Body"), ("identifier", "State's code"),
                      ("notes", "Note"), ("category", "Filed under")):
        if row.get(key):
            p.append(f"{what}: {_clean(row[key])}")
    p += [f"Looking for: {want}", "", "# Candidates"]
    for i, c in enumerate(shown):
        p.append(f"[{i}] " + "\n    ".join(c.lines))
    if not shown:
        p.append("(none found)")
    return "\n".join(p)


def class_message(row: dict[str, Any], country: str, levels: dict[str, list[str]]) -> str:
    p = ["# The row", f"Country: {country}", f"Function: {_clean(row.get('position')) or '(empty)'}"]
    for key, what in (("local", "In the state's language"), ("organisation", "Body"), ("notes", "Note"),
                      ("category", "Filed under")):
        if row.get(key):
            p.append(f"{what}: {_clean(row[key])}")
    p += ["", "# The state's levels of governed local unit"]
    for level in amlr.LEVELS:
        if levels.get(level):
            p.append(f"{level}: " + "; ".join(levels[level]))
    if not any(levels.values()):
        p.append("(none)")
    return "\n".join(p)


def params(prompt: Path, message: str) -> dict[str, Any]:
    system, _ = llm.system_prompt(prompt)
    return {"model": MODEL, "max_tokens": 1000, "output_config": {"effort": "low"},
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": message}]}


# --- the run --------------------------------------------------------------------------


@dataclass
class Work:
    """One row being expanded: its raw entry, what it was asked and what came back."""

    cc: str
    row: dict[str, Any]
    prompt: Path
    message: str
    shown: list[Candidate] = field(default_factory=list)
    refused: dict[str, str] = field(default_factory=dict)
    answer: dict[str, Any] | None = None

    @property
    def key(self) -> str:
        return LEDGER.key(MODEL, llm.system_prompt(self.prompt)[1], self.message)


def langs_of(cc: str) -> list[str]:
    """The state's Wikipedia languages, its main one first; the Union reads English."""
    territory = get_territory(cc) if cc != "eu" else None
    own = [iso_639_alpha2(lang) for lang in (territory.langs if territory else [])]
    return list(dict.fromkeys(lang for lang in own if lang))


def todo(data: dict[str, Any]) -> list[dict[str, Any]]:
    """The rows a run tries: usable and not yet expanded."""
    return [r for r in data.get("functions") or []
            if not r.get("expansion") and r["kind"] in ("position", "body", "body_class")]


def prepare(cc: str, data: dict[str, Any], log: Callable[[str], None]) -> list[Work]:
    """Search, admit and render every row a country's run tries; no model calls."""
    rows = todo(data)
    langs = langs_of(cc)
    territory = get_territory(cc) if cc != "eu" else None
    country = territory.name if territory else "European Union"
    levels = {lv: [c["name"] for c in (data.get("units") or {}).get(lv) or []] for lv in amlr.LEVELS}
    work = [Work(cc, r, CLASS_PROMPT, class_message(r, country, levels)) for r in rows if r["kind"] == "body_class"]
    matched = [r for r in rows if r["kind"] != "body_class"]
    if not matched:
        return work
    state = positions.country_qid(cc) if cc != "eu" else None
    current = set(eras.current_qids(cc)) if cc != "eu" else set()
    state_names = memo.names_of([state]).get(state, []) if state else []

    def gather(r: dict[str, Any]) -> list[str]:
        try:
            return found(r, state, country, langs)
        except Exception as exc:  # noqa: BLE001 -- one failed search leaves its row for the next run
            log(f"  {cc} row {r['row']}: search failed ({type(exc).__name__})")
            return []

    with ThreadPoolExecutor(WORKERS) as pool:
        hits = dict(zip((r["row"] for r in matched), pool.map(gather, matched)))
    qids = sorted({q for qs in hits.values() for q in qs})
    ents = wikidata.fetch_items(qids, props="labels|aliases|descriptions|claims")
    ents = {q: e for q, e in ents.items() if e.get("id", q) == q}  # a redirect is found again by its target
    closure = typegraph.close({q: typegraph.targets(e) for q, e in ents.items()})
    scopes = sorted({s for e in ents.values() for s in _values(e, "P1001")} - set(ents))
    scope_ents = {**wikidata.fetch_items(scopes, props="claims"), **ents} if scopes else ents
    scope_states = {q: _values(e, "P17") for q, e in scope_ents.items()}
    refs = {q for e in ents.values() for p in ("P31", "P279", "P17", "P1001", "P361", "P2389", "P749", "P127")
            for q in _values(e, p)}
    labels = memo.labels_of(refs, ("en", "mul"))
    for r in matched:
        w = Work(cc, r, MATCH_PROMPT, "")
        texts = [n for n, _ in row_names(r)]
        ranked: list[tuple[float, int, str]] = []
        for q in hits.get(r["row"], []):
            if q not in ents:
                continue
            why = admit(r["kind"], ents[q], closure.get(q, set()), current, scope_states, io_row(r), state_names)
            if why:
                w.refused[q] = why
            else:
                ranked.append((-name_score(texts, ents[q]), len(ranked), q))
        w.shown = [candidate(ents[q], closure.get(q, set()), langs, labels,
                             placed=io_row(r) or placed(ents[q], current, scope_states))
                   for _, _, q in sorted(ranked)[:SHOWN]]
        w.message = match_message(r, country, w.shown)
        work.append(w)
    return work


def ask(work: list[Work], log: Callable[[str], None]) -> None:
    """Answer every row with candidates (or a class row) from the ledger, or by asking."""
    jobs = []
    for w in work:
        if w.prompt == MATCH_PROMPT and not w.shown:
            continue
        w.answer = LEDGER.recorded(w.key)
        if w.answer is not None:
            continue
        schema = ClassAnswer if w.prompt == CLASS_PROMPT else Match

        def done(answer: BaseModel, tally: dict[str, int], w: Work = w) -> None:
            w.answer = answer.model_dump()
            LEDGER.store(w.key, f"amlr:{w.cc}", str(w.row["row"]), MODEL, llm.system_prompt(w.prompt)[1],
                         {"amlr": w.row["row"], "message": w.message}, w.answer, tally)

        jobs.append(llm.Job(params(w.prompt, w.message), schema, done))
    log(f"{len(work)} rows; {sum(w.answer is not None for w in work)} answered before, {len(jobs)} to ask")
    llm.run(PASS, jobs, log=log)


def apply(w: Work, levels: set[str]) -> str:
    """Write a row's answer into its raw entry; return the outcome."""
    if w.answer is None:
        return "no_candidates" if w.prompt == MATCH_PROMPT and not w.shown else "unasked"
    a: ClassAnswer | Match
    if w.prompt == CLASS_PROMPT:
        a = ClassAnswer(**w.answer)
        entry, outcome = class_entry(w.row, levels, a)
    else:
        a = Match(**w.answer)
        entry, outcome = settle(w.row, w.shown, a)
    fix = fixes(w.row, a.kind, a.amlr, a.confidence)
    if fix:
        w.row.update(fix)
        w.row["checked"] = True
    if entry and "kind" not in fix:
        w.row["expansion"] = [entry]
    return outcome


def expand(codes: list[str], log: Callable[[str], None] = print, rounds: int = 2) -> dict[str, dict[str, int]]:
    """Expand the rows of these countries' files and write them back; return outcomes per country.

    A second round tries the rows the first corrected to another kind.
    """
    db.init_schema()
    from peploop.corp import wd as corp_wd  # the ledger table is pepcorp's
    corp_wd.init()
    OUT.mkdir(parents=True, exist_ok=True)
    tally: dict[str, dict[str, int]] = {}
    for n in range(rounds):
        files = {cc: amlr.read_raw(cc) for cc in codes}
        work: dict[str, list[Work]] = {}
        for cc, (_, data) in files.items():
            if todo(data):
                work[cc] = prepare(cc, data, log)
                log(f"{cc}: {len(work[cc])} rows to try")
        ask([w for ws in work.values() for w in ws], log)
        retry = False
        for cc, ws in work.items():
            header, data = files[cc]
            levels = {lv for lv in amlr.LEVELS if (data.get("units") or {}).get(lv)}
            kinds_before = {id(w): w.row["kind"] for w in ws}
            outcomes = {}
            path = OUT / f"{cc}-expand-{date.today().isoformat()}.jsonl"
            with path.open("a" if n else "w") as fh:
                for w in ws:
                    outcome = apply(w, levels)
                    outcomes[w.row["row"]] = outcome
                    t = tally.setdefault(cc, {})
                    t[outcome] = t.get(outcome, 0) + 1
                    if w.row["kind"] != kinds_before[id(w)]:
                        retry = True
                    fh.write(json.dumps({"row": w.row["row"], "kind": w.row["kind"], "position": w.row.get("position"),
                                         "organisation": w.row.get("organisation"), "outcome": outcome,
                                         "expansion": w.row.get("expansion"), "answer": w.answer,
                                         "shown": [c.qid + " " + c.label for c in w.shown],
                                         "refused": w.refused}, ensure_ascii=False) + "\n")
            amlr.save(cc, header, data)
        if not retry:
            break
    return tally
