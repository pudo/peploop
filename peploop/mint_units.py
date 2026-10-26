"""Mint the offices every unit of a local level has, from each unit's own article.

The person lane mints an office only when a seeded person's article names it,
so the mayoralties and council seats of places whose mayor has no article stay
missing. A census entry with `per: units` names a level (the class its units
are instances of, such as a country's local government areas) and the office
each unit has; this module turns every current unit that lacks the office into
a candidate, when the unit's own article names a current holder. The candidate
then goes through `mint.verify` like any other: the named holder is its one
attestation, so the floor, the guard, the model and `mint --submit` all apply
unchanged.

A level whose units mostly have the office already is completed on the
units' articles alone. One where fewer than half do is started only where the
entry gives a `source` for that subdivision: a law or official list saying
every unit has the office.

A level may also be one of the EU AMLR unit levels (`of: amlr:municipal`):
its units are `amlr.units` at that level, whatever their classes, and a unit
already has the office when some `amlr.HEADS` office is scoped to it. Their
holder is read first from the unit's own current `P6`, then from the infobox
of the unit's article in the level's language (`HEAD_TITLES`), and the office
is labelled from the entry's templates in each language.

An entry may instead list its bodies one by one (`per: bodies`): the Union's
agencies and the international organisations seated in it, whose heads
nobody seeded. Each body names its head's title, the statement on it that
names its head, and its office's labels; the holder is that statement's,
else the line of its infobox under the title, and an office already scoped
to the body under that title means it has one. An organisation's office
governs the organisation itself (`Body.polity`).
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable, Sequence
from urllib.parse import unquote

from psycopg.types.json import Jsonb

from peploop import amlr, countries, db, offices, positions, typegraph, wikidata, wikipedia
from peploop.mint import CURRENT_WINDOW_YEARS, PROTECTED_STATUSES
from peploop.text import fold

#: A unit typed as a former administrative entity, however recorded, is history.
FORMER = "Q19953632"

#: The share of a subdivision's units that must have the office already for
#: the set to be completed on the units' articles alone.
COMPLETE_AT = 0.5

#: The infobox titles a municipality's head is given. Whatever the title, the
#: seat subclasses mayor, as 171 of one state's 185 existing mayoralties do.
SHIRE_PRESIDENT = ("president", "shire president")
HEAD_LINE = re.compile(r"^[•·\s]*(?P<title>(?:lord )?mayor|(?:shire )?president)\s*:\s*(?P<name>.+)$", re.I)
#: What an infobox puts where nobody holds the office.
VACANT = re.compile(r"\b(vacant|administrator|none|tba|suspended|dismissed)\b", re.I)

#: Per language, the infobox titles a unit's head is given: the title as an
#: office label writes it, and the pattern its masculine and feminine forms
#: match. Longer titles first, so "sindaco metropolitano" is not "sindaco".
HEAD_TITLES: dict[str, tuple[tuple[str, str], ...]] = {
    "de": (("Oberbürgermeister", r"oberbürgermeister(?:in)?"), ("Bürgermeister", r"bürgermeister(?:in)?"),
           ("Landrat", r"landr(?:at|ätin)")),
    "fr": (("maire", r"maire"), ("président", r"présidente?")),
    "it": (("sindaco metropolitano", r"sindac[oa] metropolitan[oa]"), ("sindaco", r"sindac[oa]"),
           ("presidente", r"presidente(?:ssa)?")),
    # The pl infobox writes "Prezydent" for the city's prezydent miasta.
    "pl": (("prezydent miasta", r"prezydent(?: miasta)?"), ("burmistrz", r"burmistrz"), ("starosta", r"starosta")),
    "el": (("δήμαρχος", r"δήμαρχος"),),
    "pt": (("presidente da câmara municipal", r"presidente da câmara(?: municipal)?"),),
    "cs": (("primátor", r"primátor(?:ka)?"), ("starosta", r"starost(?:a|ka)")),
    "hu": (("polgármester", r"polgármester"),),
    "fi": (("kaupunginjohtaja", r"kaupunginjohtaja"), ("pormestari", r"pormestari")),
    "sk": (("primátor", r"primátor(?:ka)?"),),
    "hr": (("gradonačelnik", r"gradonačelni(?:k|ca)"),),
    "lv": (("domes priekšsēdētājs", r"(?:domes )?priekšsēdētāj[sa]"),),
    "sl": (("župan", r"župan(?:ja)?"),),
    "es": (("alcalde", r"alcaldesa|alcalde"), ("presidente", r"president[ea]")),
}
#: An infobox head line in any of those languages: the title, perhaps a
#: bracketed term ("Domes priekšsēdētājs (2026-)"), one or two colons, the name.
HEAD_LINE_OF = {
    lang: re.compile(r"^[•·–\-\s]*(?P<title>" + "|".join(f"(?:{pattern})" for _, pattern in titles)
                     + r")(?:\s*\([^)]*\))?\s*::?\s*(?P<name>.+)$", re.I)
    for lang, titles in HEAD_TITLES.items()
}
#: An acting, interim or appointed holder, or nobody, in those languages: the
#: floor never counts an acting tenure as current.
NOT_HELD = re.compile(
    r"(?:\bp\.\s?[fo]\.|\bf\.\s?f\.|\bpełni[a-ząćęłńóśźż]*\s+(?:funkcj|obowiązk)|\bkomisarz|\bkommissarisch|"
    r"\bcommissari[oa]|\bcommissione|\bcommissaire|\binterim|\bvakant|\bvacante?\b|\bneobsazen|\buprázdn|\bnieobsadz|"
    r"\bbetöltetlen|\bκεν[όή]\b|\bvacant)",
    re.I)
#: The years a head line names: "(01-09-2019) - (31-12-2023)" is a term that is over.
YEAR = re.compile(r"\b(?:19|20)\d\d\b")
#: The headings an article's section on its council goes under.
COUNCIL_HEADING = re.compile(r"^##\s*((?:elected |current |the )?council|councillors|"
                             r"(?:current )?composition|governance|government|local government|politics)\b",
                             re.I)
#: The type words a unit's label wraps its place name in: "City of X", "X Shire Council".
UNIT_WORDS = re.compile(
    r"^(?:the\s+)?(?:(?:aboriginal\s+)?shire|city|rural city|town|municipality|borough|region|"
    r"municipal district|district council|regional council|council)\s+of\s+(?:the\s+)?"
    r"|\s+(?:(?:city|regional|shire|municipal|town|district|aboriginal shire|rural city)\s+)?"
    r"(?:council|shire|region|municipality)$",
    re.I,
)


@dataclass
class Body:
    """One body of a `per: bodies` entry, whose head's office the entry names.

    An EU body's head office is the Union's (`P1001` the scope's state); an
    international organisation's is its own, so `polity` names the
    organisation and the office carries no `P17`.
    """

    qid: str
    #: The head's title as the body's infobox writes it ("Executive Director").
    title: str
    #: The office's label per language, curated: English and the scope's languages.
    labels: dict[str, str] = field(default_factory=dict)
    #: The body's statement naming its head now (`P1037`, `P488` …), where it has one.
    holder: str | None = None
    #: The polity the office governs where it is not the scope's state: an organisation's own.
    polity: str | None = None
    #: The office's `P279`, by the title word, where the entry's parent is not it.
    parent: str | None = None
    #: An infobox spelling of the title the default pattern misses ("General Secretary").
    infobox: str | None = None


@dataclass
class Level:
    """One `per: units` census entry: the office every unit of a level has."""

    key: str
    archetype: str
    institution_class: str
    #: The class the level's units are instances of, directly or by a subclass;
    #: or `P150`, the units the state's subdivisions list, where no class
    #: types them all.
    of: str
    #: Per subdivision QID, a source saying every unit of it has the office;
    #: `*` for a national law or page that says it of every subdivision.
    sources: dict[str, str] = field(default_factory=dict)
    #: The wiki the units' articles are read in.
    lang: str = "en"
    #: Per language, the office's label as a template over `{title}` (the
    #: head's title, `HEAD_TITLES`), `{name}` (the unit's label in that
    #: language), `{council}` (its council's) and `{genitive}` (the unit's
    #: name in the genitive, as its article writes it: `genitive`). A key `lang/title` words one
    #: title apart: Finland's kaupunginjohtaja is a city manager, its pormestari
    #: a mayor. Empty for the English lane's own wording.
    labels: dict[str, str] = field(default_factory=dict)
    #: Per language, rewrites of the names before they fill a template:
    #: "Δήμος Καλαμάτας" is the unit, "Δήμαρχος Καλαμάτας" its head. In the
    #: level's own language a name none of them rewrites gives no label, since
    #: the template's grammar expects the form.
    forms: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    #: The head's title when only the unit's `P6` names the holder.
    title: str | None = None
    #: The office's `P279`, measured over the state's existing head offices of
    #: the level: per title or per subdivision where those differ, else one.
    parent: str | None = None
    parents: dict[str, str] = field(default_factory=dict)
    #: For `per: bodies`, the bodies listed one by one in place of a class of units.
    bodies: list[Body] = field(default_factory=list)

    @property
    def by_body(self) -> bool:
        """Whether the entry lists its bodies one by one (`per: bodies`) rather than a level of units."""
        return self.of == "bodies"

    @property
    def amlr_level(self) -> str | None:
        """The AMLR level the entry names (`of: amlr:<level>`), or None for a class."""
        return self.of.removeprefix("amlr:") if self.of.startswith("amlr:") else None

    def source_for(self, subdivision: str | None) -> str | None:
        """The source saying every unit of the subdivision has the office, if the entry gives one."""
        return self.sources.get(subdivision or "") or self.sources.get("*")

    def parent_for(self, title: str | None, subdivision: str | None) -> str | None:
        """The measured parent for a unit's office: by its title, its subdivision, or the level's."""
        return self.parents.get(title or "") or self.parents.get(subdivision or "") or self.parent


@dataclass
class Head:
    """The holder a unit's own `P6` names now."""

    qid: str
    label: str
    start: str | None = None
    #: The statement's reference URL, where it has one.
    reference: str | None = None


@dataclass
class Unit:
    qid: str
    label: str
    #: The unit's article in the level's language; None where it has none.
    title: str | None
    subdivision: str | None
    council: str | None
    council_label: str | None
    #: Offices of this archetype already scoped to the unit.
    has_office: bool = False
    #: The unit's and its council's labels per language, for the templates.
    names: dict[str, str] = field(default_factory=dict)
    council_names: dict[str, str] = field(default_factory=dict)
    head: Head | None = None
    #: Why the unit's `P6` names no head, when it has statements: `p6/several`, `p6/stale` ...
    head_problem: str | None = None


def levels(cc: str, path: Path | None = None) -> list[Level]:
    """The country's `per: units` census entries."""
    out = []
    for entry in countries.section(cc, "census", path) or []:
        if entry.get("per") not in ("units", "bodies"):
            continue
        bodies = [Body(qid=str(b["qid"]), title=str(b["title"]), labels=dict(b.get("labels") or {}),
                       holder=b.get("holder"), polity=b.get("polity"), parent=b.get("parent"),
                       infobox=b.get("infobox"))
                  for b in entry.get("bodies") or []]
        out.append(Level(key=entry["key"], archetype=entry["archetype"],
                         institution_class=entry["class"], of=entry["of"] if entry["per"] == "units" else "bodies", bodies=bodies,
                         sources=dict(entry.get("sources") or {}), lang=entry.get("lang", "en"),
                         labels=dict(entry.get("labels") or {}),
                         forms={lang: [tuple(f) for f in fs] for lang, fs in (entry.get("forms") or {}).items()},
                         title=entry.get("title"), parent=entry.get("parent"),
                         parents=dict(entry.get("parents") or {})))
    return out


UNITS_SQL = """SELECT DISTINCT ?u ?uLabel ?article ?sub ?council ?councilLabel WHERE {{
  {unit}
  FILTER NOT EXISTS {{ ?u wdt:P576 [] }}
  FILTER NOT EXISTS {{ ?u wdt:P31/wdt:P279?/wdt:P279? wd:{former} }}
  ?article schema:about ?u ; schema:isPartOf <https://en.wikipedia.org/> .
  OPTIONAL {{ ?u wdt:P131 ?sub . VALUES ?sub {{ {subs} }} }}
  OPTIONAL {{ ?u wdt:P194 ?council }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}"""

#: Units that already have an office of the archetype's parent: scoped to them
#: under `P1001`, or named as their head of government.
HELD_SQL = """SELECT DISTINCT ?u WHERE {{
  {unit}
  {{ ?o wdt:P1001 ?u ; wdt:P279/wdt:P279* wd:{parent} . }} {head}
}}"""


def unit_pattern(level: Level, state: str) -> str:
    """The SPARQL pattern binding `?u` to the level's units."""
    if level.of == "P150":
        return f"wd:{state} wdt:P150 ?sub . ?sub wdt:P150 ?u ."
    return f"?u wdt:P31/wdt:P279* wd:{level.of} ; wdt:P17 wd:{state} ."


def units(level: Level, state: str, subdivisions: Sequence[str], parent: str) -> list[Unit]:
    """Every current unit of the level with an English article, read live."""
    subs = " ".join(f"wd:{q}" for q in subdivisions) or "wd:Q0"
    unit = unit_pattern(level, state)
    rows = wikidata.sparql(UNITS_SQL.format(unit=unit, subs=subs, former=FORMER))
    head = "UNION { ?u wdt:P1313 [] }" if parent == "Q30185" else ""
    held = {r["u"] for r in wikidata.sparql(HELD_SQL.format(unit=unit, parent=parent, head=head))}
    out: dict[str, Unit] = {}
    for r in rows:
        qid = r["u"]
        title = r["article"].rsplit("/wiki/", 1)[-1].replace("_", " ")
        unit = out.setdefault(qid, Unit(qid, r.get("uLabel") or qid, unquote(title), None, None, None,
                                        has_office=qid in held))
        unit.subdivision = unit.subdivision or r.get("sub")
        if r.get("council") and unit.council is None:
            unit.council, unit.council_label = r["council"], r.get("councilLabel")
    return sorted(out.values(), key=lambda u: u.qid)


SUBDIVISION_SQL = """SELECT DISTINCT ?u ?sub WHERE {{
  VALUES ?u {{ {values} }} VALUES ?sub {{ {subs} }} ?u wdt:P131+ ?sub .
}}"""


def subdivision_of(qids: Sequence[str], subdivisions: Sequence[str]) -> dict[str, str]:
    """Each unit's first-level subdivision, through its `P131` chain; units in two are left out."""
    if not qids or not subdivisions:
        return {}
    subs = wikidata.values_block(subdivisions)
    rows = wikidata.bisect(lambda chunk: wikidata.sparql(
        SUBDIVISION_SQL.format(values=wikidata.values_block(chunk), subs=subs)), list(qids), size=60)
    found: dict[str, set[str]] = {}
    for r in rows:
        found.setdefault(r["u"], set()).add(r["sub"])
    return {u: next(iter(subs_)) for u, subs_ in found.items() if len(subs_) == 1}


def _year(text: str | None) -> int | None:
    found = re.match(r"^[+-]?(\d{4})", text or "")
    return int(found.group(1)) if found else None


def current_head(entity: dict[str, Any], holders: dict[str, dict[str, Any]], langs: Sequence[str],
                 this_year: int | None = None, prop: str = "P6") -> tuple[Head | None, str | None]:
    """The one living human the unit's `P6` (or a body's `prop`) names now, or None with why.

    Current means no end and not deprecated; the preferred statements stand
    alone where there are any. Several current statements are a list nobody
    ended, and one begun before the current window an office long since
    passed on, as the mint floor reads any tenure.
    """
    this_year = this_year or date.today().year
    tag = prop.lower()
    claims = [c for c in entity.get("claims", {}).get(prop, [])
              if c.get("rank") != "deprecated" and not c.get("qualifiers", {}).get("P582")]
    if not claims:
        return None, None
    claims = [c for c in claims if c.get("rank") == "preferred"] or claims
    if len(claims) > 1:
        return None, f"{tag}/several"
    claim = claims[0]
    qid = (claim.get("mainsnak", {}).get("datavalue", {}).get("value") or {}).get("id")
    holder = holders.get(qid or "") or {}
    if "Q5" not in wikidata.claim_qids(holder, "P31", include_deprecated=False):
        return None, f"{tag}/not-human"
    if wikidata.claim_time(holder, "P570", include_deprecated=False):
        return None, f"{tag}/dead"
    starts = [q.get("datavalue", {}).get("value", {}).get("time") for q in claim.get("qualifiers", {}).get("P580", [])]
    start = next((t for t in starts if t), None)
    if start and (_year(start) or this_year) < this_year - CURRENT_WINDOW_YEARS:
        return None, f"{tag}/stale"
    refs = [snak.get("datavalue", {}).get("value") for ref in claim.get("references", [])
            for prop in ("P854", "P4656") for snak in ref.get("snaks", {}).get(prop, [])]
    label = wikidata.best_label(holder, (*langs, "en", "mul")) or qid
    return Head(qid, label, start.lstrip("+")[:10] if start else None,
                next((r for r in refs if isinstance(r, str)), None)), None


def _names(entity: dict[str, Any]) -> dict[str, str]:
    return {lang: term["value"] for lang, term in (entity.get("labels") or {}).items()}


def amlr_units(level: Level, cc: str, subdivisions: Sequence[str]) -> list[Unit]:
    """The country's AMLR units of the level, each with its article, council and current `P6` head."""
    qids = sorted(q for q, (lv, _pop) in amlr.units(cc).items() if lv == level.amlr_level)
    ents = wikidata.fetch_items(qids, props="labels|claims|sitelinks") if qids else {}
    held = amlr.scoped_heads(qids) if qids else set()
    held |= {q for q, e in ents.items() if offices._unended(e, "P1313")}
    subs = subdivision_of(qids, subdivisions)
    councils = {q: c[0] for q, e in ents.items() if len(c := offices._unended(e, "P194")) == 1}
    heads = sorted({(c.get("mainsnak", {}).get("datavalue", {}).get("value") or {}).get("id")
                    for e in ents.values() for c in e.get("claims", {}).get("P6", [])} - {None})
    holders = wikidata.fetch_items(heads, props="labels|claims") if heads else {}
    council_ents = wikidata.fetch_items(sorted(set(councils.values())), props="labels") if councils else {}
    langs = list(dict.fromkeys([level.lang, *level.labels]))
    out = []
    for qid in qids:
        ent = ents.get(qid)
        if not ent:
            continue
        names = _names(ent)
        council = councils.get(qid)
        council_names = _names(council_ents.get(council or "", {}))
        title = (ent.get("sitelinks") or {}).get(f"{level.lang}wiki", {}).get("title")
        head, problem = current_head(ent, holders, langs)
        council_label = wikidata.best_label(council_ents.get(council or "", {}), ("en", level.lang, "mul"))
        out.append(Unit(qid, wikidata.best_label(ent, (level.lang, "en", "mul")) or qid, title, subs.get(qid),
                        council, council_label if council else None,
                        has_office=qid in held, names=names, council_names=council_names,
                        head=head, head_problem=problem))
    return out


def place_name(label: str) -> str:
    """The place a unit's label names, without its type words: "City of X" is X."""
    return UNIT_WORDS.sub("", label.strip()).strip() or label.strip()


def head_of(text: str, lang: str = "en") -> tuple[str, str] | None:
    """The head's title and name from an article's infobox lines, or None when vacant.

    In another language than English the title comes back as `HEAD_TITLES`
    writes it, and a line naming an acting holder, or a term whose years are
    all past ("(01-09-2019) - (31-12-2023)"), names nobody: a stale infobox is
    not a current holder.
    """
    pattern = HEAD_LINE if lang == "en" else HEAD_LINE_OF.get(lang)
    if pattern is None:
        return None
    for line in text.splitlines():
        found = pattern.match(line.strip())
        if not found:
            continue
        raw = found["name"]
        name = re.sub(r"\[\d+\]|\(.*?\)|^(?:Cr|Clr|Councillor)\.?\s+", "", raw).strip(" ,;")
        if lang != "en":
            # "Riccardo Righi dal 10-6-2024", "Name - Deputy", "Name Toimialajohtajat: …": the
            # name ends at a date, a dash or the next infobox field.
            name = re.split(r"\s+(?:dal|dall'|dalla|desde|depuis|seit|od|since)(?:\b|\s)|\s+[-–]\s+|\d|\s+\S+:",
                            name)[0].strip(" ,;")
            years = [int(y) for y in YEAR.findall(raw)]
            if NOT_HELD.search(raw) or (len(years) >= 2 and max(years) < date.today().year):
                return None
            if "," in name:
                # Several names: a commission running the unit, no one head.
                return None
        if not name or VACANT.search(name):
            return None
        return (found["title"].strip().lower() if lang == "en" else canonical_title(lang, found["title"])), name
    return None


def canonical_title(lang: str, written: str) -> str:
    """The title as `HEAD_TITLES` writes it, for the infobox's spelling of it."""
    for title, pattern in HEAD_TITLES.get(lang, ()):
        if re.fullmatch(pattern, written.strip(), re.I):
            return title
    return written.strip()


def same_person(a: str, b: str) -> bool:
    """Whether two renderings of a name share a surname-length word, whatever their order."""
    words = lambda text: {w for w in re.findall(r"\w+", fold(text)) if len(w) >= 4}  # noqa: E731
    return bool(words(a) & words(b))


#: Per language, words after which a name stands in the genitive: the head's
#: titles, and prepositions that govern no other case ("do Zgierza", "od Piły").
GENITIVE_CUES: dict[str, tuple[str, ...]] = {
    "pl": (r"prezydent\w*", r"burmistrz\w*", r"starost\w*", "do", "od", "dla", "koło", "obok", "spod", "wokół",
           "bez", "naprzeciw", "wzdłuż", "u"),
}


def genitive(text: str, lang: str, name: str | None) -> str | None:
    """The unit's name in the genitive, in the form its article writes most often.

    A Polish city's head is "prezydent Zgierza", which no rule of the
    language spells reliably; the article's own prose does ("prezydentem
    Zgierza", "do Gorzowa Wielkopolskiego"). A form counts when it follows a
    word of `GENITIVE_CUES`, has the name's words and hyphens, shares its stem
    and is not the name itself ("do Jastrzębia" is short for Jastrzębie-Zdrój). None when the article never writes one.
    """
    cues = GENITIVE_CUES.get(lang)
    if not cues or not name or not text:
        return None
    words = name.split()
    first = fold(words[0])
    stem = first[:max(3, min(len(first) - 2, 5))]
    found = re.compile(r"(?<!\w)(?i:" + "|".join(cues) + r")\s+(?:miasta\s+)?"
                       + r"\s+".join([r"([A-ZĄĆĘŁŃÓŚŹŻ][\w-]*)"] * len(words)) + r"(?!\w)")
    forms: Counter[str] = Counter()
    for match in found.finditer(text):
        form = " ".join(match.groups())
        if fold(form).startswith(stem) and form != name and form.count("-") == name.count("-"):
            forms[form] += 1
    return forms.most_common(1)[0][0] if forms else None


def office_labels(level: Level, unit: Unit, title: str, text: str = "") -> dict[str, str]:
    """The office's label in each language the level templates, from the unit's names.

    A language whose template names something the unit has no label for is left out.
    """
    out = {}
    for lang in dict.fromkeys(k.split("/")[0] for k in level.labels):
        template = level.labels.get(f"{lang}/{title}") or level.labels.get(lang)
        if not template:
            continue
        slots = {"title": title, "name": unit.names.get(lang), "council": unit.council_names.get(lang),
                 "genitive": genitive(text, lang, unit.names.get(lang)) if lang == level.lang else None}
        wanted = {n for n in ("name", "council", "genitive") if "{" + n + "}" in template}
        if any(not slots[n] for n in wanted):
            continue
        forms = level.forms.get(lang, ())
        for n in wanted:
            rewritten = False
            for pattern, repl in forms:
                slots[n], count = re.subn(pattern, repl, slots[n])
                rewritten |= bool(count)
            if forms and lang == level.lang and not rewritten:
                break
        else:
            out[lang] = template.format(**slots).strip()
    return out


def council_quote(text: str, limit: int = 380) -> str | None:
    """The first prose under the article's sections on its council, or None."""
    active = False
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("##"):
            active = bool(COUNCIL_HEADING.match(line))
            continue
        if active and len(line) > 25:
            return line[:limit]
    return None


#: A lead that puts the unit in the past: abolished, though nothing on its item says so.
PAST = re.compile(r"\b(?:was|were)\s+(?:an?|the)\s+[^.]{0,60}?\b(?:local government area|shire|city|town|"
                  r"municipality|borough|council|division)\b", re.I)


def lead(text: str) -> str:
    """The article's first sentence of prose, past the infobox lines."""
    for line in text.splitlines():
        if len(line) > 80 and not line.startswith("##") and ":" not in line[:40]:
            return line
    return ""


def draft_for(level: Level, unit: Unit, text: str, url: str) -> tuple[dict[str, Any] | None, str]:
    """The candidate's draft for one unit, or None with the reason it has none."""
    if level.labels:
        return labelled_draft(level, unit, text, url)
    if PAST.search(lead(text)[:250]):
        return None, "unit/former"
    head = head_of(text)
    if head is None:
        return None, "unit/no-named-holder"
    title, name = head
    place = place_name(unit.label)
    source = level.source_for(unit.subdivision)
    evidence = {"qid": unit.qid, "label": unit.label, "url": url, "holder": name, "source": source}
    if level.archetype == "mayor":
        parent = "Q30185"
        word = "Shire President" if title in SHIRE_PRESIDENT else title.title()
        label = f"{word} {of_unit(unit.label)}"
        evidence["quote"] = f"{title.title()}: {name}"
        single = True
    elif level.archetype == "councillor":
        quote = council_quote(text)
        if quote is None:
            return None, "unit/no-council-section"
        parent = "Q708492"
        council = unit.council_label or council_name(text, place)
        if not council:
            return None, "unit/no-council-name"
        label = f"member of {council}"
        evidence["quote"] = f"{quote} … {title.title()}: {name} (a member of the council)"
        single = False
    else:
        raise ValueError(f"{level.key}: no unit lane for archetype {level.archetype!r}")
    return {
        "decision": "office", "archetype": level.archetype, "labels": {"en": label},
        "institution_class": level.institution_class, "single_seat": single,
        "parent_qid": parent, "body_qid": unit.council, "jurisdiction_qid": unit.qid,
        "jurisdiction_name": unit.label, "evidence": evidence["quote"],
        "reason": f"every unit of the level has the office; {unit.label}'s article names its holder",
        "unit": evidence,
    }, "unit/drafted"


def labelled_draft(level: Level, unit: Unit, text: str, url: str) -> tuple[dict[str, Any] | None, str]:
    """The draft of a level labelled from templates: the holder from `P6`, else the infobox.

    The unit's own `P6` is its own statement of who heads it, so it comes
    first, with the article's infobox line beside it. An undated P6 is often
    the mayor before last: where the infobox names someone else, the article
    is the fresher source and its holder is the attestation.
    """
    line = head_of(text, level.lang) if text else None
    head = unit.head
    if head and line and not same_person(head.label, line[1]):
        head = None
    if not head and not line:
        return None, "unit/no-named-holder"
    title = line[0] if line else (level.title or "")
    labels = office_labels(level, unit, title, text)
    if not labels:
        return None, "unit/no-label"
    quotes = []
    if head:
        since = f", since {re.sub(r'(?:-00)+$', '', head.start)}" if head.start else ""
        ref = f" (reference: {head.reference})" if head.reference else ""
        quotes.append(f"{unit.label}, head of government (P6) on Wikidata: {head.label} ({head.qid}){since}{ref}")
    if line:
        quotes.append(f"{title}: {line[1]} (infobox of {url})")
    evidence = {"qid": unit.qid, "label": unit.label, "url": url, "lang": level.lang,
                "holder": head.label if head else line[1], "holder_qid": head.qid if head else None,
                "quote": quotes[0], "quotes": quotes, "source": level.source_for(unit.subdivision),
                "parent": level.parent_for(title, unit.subdivision)}
    shape = offices.ARCHETYPES[level.archetype]
    return {
        "decision": "office", "archetype": level.archetype, "labels": labels,
        "institution_class": level.institution_class, "single_seat": shape.single_seat,
        "parent_qid": evidence["parent"] or shape.parent, "body_qid": unit.council,
        "jurisdiction_qid": unit.qid, "jurisdiction_name": unit.label, "evidence": quotes[0],
        "reason": f"every unit of the level has the office; {'its P6' if head else 'its article'} names its holder",
        "unit": evidence,
    }, "unit/drafted"


#: The offices scoped to a body, or held by its head (`P2388`), with their English labels.
BODY_SCOPED_SQL = """SELECT DISTINCT ?b ?o ?l WHERE {{ VALUES ?b {{ {values} }}
  {{ ?o wdt:P2389 ?b }} UNION {{ ?o wdt:P1001 ?b }} UNION {{ ?o wdt:P642 ?b }} UNION {{ ?b wdt:P2388 ?o }}
  ?o rdfs:label ?l . FILTER(lang(?l) = "en") }}"""
#: A head the infobox calls acting or interim holds the office for nobody.
ACTING = re.compile(r"\b(?:acting|interim|ad interim|a\.i\.)\b", re.I)


def title_pattern(body: Body) -> re.Pattern[str]:
    """The body's head title as an infobox may write it: any case, a space or hyphen between its words."""
    if body.infobox:
        return re.compile(body.infobox, re.I)
    words = [re.escape(w) for w in re.split(r"[\s\-]+", body.title.strip()) if w]
    return re.compile(r"[\s\-]+".join(words), re.I)


def has_head_office(body: Body, labels: Sequence[str], p2388: bool = False) -> bool:
    """Whether an office scoped to the body is its head's: named by the head's title, or the body's `P2388`."""
    pattern = title_pattern(body)
    return p2388 or any(pattern.match(label.strip()) for label in labels)


def body_head(text: str, body: Body) -> str | None:
    """The head the body's infobox names under its title; "" when it names nobody current, None when no line.

    Infoboxes write the head three ways: "Executive Director: Emer Cooke",
    "Agency executives: Emer Cooke, Executive Director Christa …, Chairperson"
    and "Head: Director Sherri Aldis". An acting or interim head, or a term
    whose years are all past, is no holder, and outranks the body's own
    statement as any infobox line does: that statement names the head before.
    """
    pattern = title_pattern(body).pattern
    for line in text.splitlines()[:120]:
        line = line.strip().lstrip("•·– ").strip()
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        name = None
        if re.fullmatch(rf"(?:current\s+)?{pattern}", key, re.I):
            name = re.split(r"\s*[(,;]|\s+since\b", value)[0]
        elif re.fullmatch(r"(?:head|leader)", key, re.I) and re.match(rf"(?:acting\s+)?{pattern}\s+\S", value, re.I):
            name = re.sub(rf"^(?:acting\s+)?{pattern}\s+", "", value, flags=re.I)
            name = re.split(r"\s*[(,;]|\s+since\b", name)[0]
        elif (found := re.search(rf",\s*((?:acting|interim)\s+)?{pattern}\b", value, re.I)):
            chunk = value[:found.start()]
            # The name follows the previous seat's title, which ends the run before it.
            chunk = re.split(r"\b(?:director|chair\w*|president|secretary|head|member|board)\b\s+", chunk,
                             flags=re.I)[-1]
            name = chunk.split(",")[-1]
            if found.group(1):
                return ""
        else:
            continue
        name = re.sub(r"\[\d+\]|\(.*?\)", "", name or "")
        name = re.sub(r"^[\d\s\-–]+", "", name).strip(" ,;")
        years = [int(y) for y in YEAR.findall(value)]
        if not name or ACTING.search(line) or NOT_HELD.search(line) or VACANT.search(name):
            return ""
        if len(years) >= 2 and max(years) < date.today().year and "present" not in value.lower():
            return ""
        return name
    return None


def body_units(level: Level, state: str) -> list[tuple[Body, Unit]]:
    """Each listed body with its article, its head office if any, and the head its own statement names."""
    qids = [b.qid for b in level.bodies]
    ents = wikidata.fetch_items(qids, props="labels|claims|sitelinks") if qids else {}
    rows = wikidata.bisect(lambda chunk: wikidata.sparql(BODY_SCOPED_SQL.format(
        values=wikidata.values_block(chunk))), qids, size=40) if qids else []
    labels: dict[str, list[str]] = {}
    for r in rows:
        labels.setdefault(r["b"], []).append(r["l"])
    heads = sorted({(c.get("mainsnak", {}).get("datavalue", {}).get("value") or {}).get("id")
                    for b in level.bodies if b.holder
                    for c in (ents.get(b.qid) or {}).get("claims", {}).get(b.holder, [])} - {None})
    holders = wikidata.fetch_items(heads, props="labels|claims") if heads else {}
    out = []
    for body in level.bodies:
        ent = ents.get(body.qid)
        if not ent:
            continue
        head, problem = current_head(ent, holders, (level.lang,), prop=body.holder) if body.holder else (None, None)
        title = (ent.get("sitelinks") or {}).get(f"{level.lang}wiki", {}).get("title")
        out.append((body, Unit(body.qid, wikidata.best_label(ent, (level.lang, "en", "mul")) or body.qid, title,
                               None, None, None,
                               has_office=has_head_office(body, labels.get(body.qid, []),
                                                          bool(offices._unended(ent, "P2388"))),
                               names=_names(ent), head=head, head_problem=problem)))
    return out


def body_draft(level: Level, body: Body, unit: Unit, text: str, url: str,
               state: str) -> tuple[dict[str, Any] | None, str]:
    """The draft of a body's head office: the holder from its own statement, else its infobox.

    As for a unit, the infobox outranks a statement naming someone else: a
    body's head statement is often its last head but one.
    """
    line = body_head(text, body) if text else None
    if line == "":
        return None, "unit/not-held"
    head = unit.head
    if head and line and not same_person(head.label, line):
        head = None
    if not head and not line:
        return None, "unit/no-named-holder"
    labels = {lang: text_ for lang, text_ in body.labels.items() if text_}
    if not labels.get("en"):
        return None, "unit/no-label"
    quotes = []
    if head:
        since = f", since {re.sub(r'(?:-00)+$', '', head.start)}" if head.start else ""
        ref = f" (reference: {head.reference})" if head.reference else ""
        quotes.append(f"{unit.label}, {body.holder} on Wikidata: {head.label} ({head.qid}){since}{ref}")
    if line:
        quotes.append(f"{body.title}: {line} (infobox of {url})")
    polity = body.polity or state
    evidence = {"qid": unit.qid, "label": unit.label, "url": url, "lang": level.lang,
                "holder": head.label if head else line, "holder_qid": head.qid if head else None,
                "quote": quotes[0], "quotes": quotes, "source": None,
                "parent": body.parent or level.parent, "body": body.qid,
                "polity": body.polity if body.polity and body.polity != state else None}
    shape = offices.ARCHETYPES[level.archetype]
    return {
        "decision": "office", "archetype": level.archetype, "labels": labels,
        "institution_class": level.institution_class, "single_seat": shape.single_seat,
        "parent_qid": evidence["parent"] or shape.parent, "body_qid": body.qid,
        "jurisdiction_qid": polity, "jurisdiction_name": unit.label if body.polity else None,
        "evidence": quotes[0],
        "reason": f"the census lists {unit.label}'s head; {'its statement' if head else 'its article'} names the holder",
        "unit": evidence,
    }, "unit/drafted"


def of_unit(label: str) -> str:
    """"of" and the unit's full name, as the existing items word it: "of the Shire of X", "of X Shire"."""
    return f"of the {label}" if re.match(r"^(?:the\s+)?\w[\w ]*? of ", label, re.I) and not label.lower().startswith("the ") \
        else f"of {label}"


COUNCIL_NAME = re.compile(r"\b((?:[A-Z][\w'’-]*\s){1,5}Council)\b")


def council_name(text: str, place: str) -> str | None:
    """The council's name as the article writes it ("Clarence City Council"), or None."""
    for found in COUNCIL_NAME.finditer(text):
        name = re.sub(r"^(?:The|A|An)\s+", "", found.group(1).strip())
        if name.lower() != "council" and place.split()[0].lower() in name.lower():
            return name
    return None


def started(units_: Sequence[Unit]) -> dict[str | None, float]:
    """Per subdivision, the share of its units that already have the office."""
    total, held = Counter(), Counter()
    for u in units_:
        total[u.subdivision] += 1
        held[u.subdivision] += u.has_office
    return {sub: held[sub] / total[sub] for sub in total}


#: The statuses of a mention candidate an item exists or is being made for;
#: one the coming verify guards makes the unit's yield there (`mint.UNIT_YIELDS`).
LIVE_STATUSES = PROTECTED_STATUSES


def mention_seats(cc: str, ctx: "mint.Context | None" = None) -> set[tuple[str, str]]:
    """(archetype, town) of every local seat the run's mention candidates name."""
    from peploop import mint
    ctx = ctx or mint.Context(cc)
    rows = db.conn().execute(
        "SELECT archetype, draft, spec FROM office_candidate WHERE country = %s"
        " AND NOT ('unit' = ANY(origin)) AND status = ANY(%s) AND archetype = ANY(%s)",
        (cc, list(LIVE_STATUSES), [a for a, s in offices.ARCHETYPES.items() if s.level == "municipality"]),
    ).fetchall()
    out = set()
    for archetype, draft, spec in rows:
        draft = draft or {}
        place = (spec or {}).get("jurisdiction_qid") or draft.get("jurisdiction_qid")
        if not place or place in ctx.levels:
            found = ctx.local_place(draft.get("jurisdiction_name"))
            place = found[0] if found else None
        if place:
            out.add((archetype, place))
    return out


def supersede(cc: str, ref: str) -> None:
    """Take a unit's candidate out of the run, unless an item was made from it."""
    db.conn().execute(
        "UPDATE office_candidate SET status = 'superseded', updated_at = now()"
        " WHERE country = %s AND ref = %s AND status <> ALL(%s) AND decided_by IS NULL",
        (cc, ref, list(PROTECTED_STATUSES)))


UPSERT_SQL = (
    "INSERT INTO office_candidate (country, ref, origin, institution_class, archetype, single_seat,"
    " draft, holders, current_holders, source_url, status, problems)"
    " VALUES (%s, %s, '{unit}', %s, %s, %s, %s, 1, 1, %s, 'categorized', '{}')"
    " ON CONFLICT (country, ref) DO UPDATE SET draft = EXCLUDED.draft,"
    " single_seat = EXCLUDED.single_seat, source_url = EXCLUDED.source_url,"
    " status = 'categorized', rule = NULL, updated_at = now()"
    " WHERE office_candidate.status <> ALL(%s) AND office_candidate.decided_by IS NULL"
    " AND (office_candidate.draft IS DISTINCT FROM EXCLUDED.draft OR office_candidate.status = 'superseded')"
)


def heads_reached(level: Level) -> list[str]:
    """The parents a level names that reach no `amlr.HEADS` class, read live.

    An office the report and the back-link would not see as a head office
    would leave its unit in the mint queue, to be minted again.
    """
    parents = sorted({q for q in (level.parent, *level.parents.values()) if q})
    closure = typegraph.of_items(parents) if parents else {}
    return [q for q in parents if q not in amlr.HEADS and not closure.get(q, set()) & amlr.HEADS]


def build(cc: str, log: Callable[[str], None] = print,
          read: Callable[[str, str], tuple[str, str]] | None = None,
          keys: Sequence[str] | None = None) -> Counter[str]:
    """Write a candidate for every unit of every `per: units` level that lacks its office.

    `keys` narrows the run to those levels.
    """
    def _read(lang: str, title: str) -> tuple[str, str]:
        art = wikipedia.fetch_article(lang, title)
        return wikipedia.html_to_text(art["html"]), art["url"]

    read = read or _read
    state = positions.country_qid(cc)
    claimed = mention_seats(cc)
    subs = [q for q, _labels in offices.subdivisions(state)]
    stats: Counter[str] = Counter()
    for level in levels(cc):
        if keys is not None and level.key not in keys:
            continue
        if level.by_body:
            stats.update(build_bodies(cc, level, state, read, log))
            continue
        if level.amlr_level:
            if stray := heads_reached(level):
                log(f"{level.key}: parents {' '.join(stray)} reach no head class; level skipped")
                stats[f"{level.key}:parent-not-a-head"] += 1
                continue
            found = amlr_units(level, cc, subs)
        else:
            found = units(level, state, subs, offices.ARCHETYPES[level.archetype].parent)
        shares = started(found)
        log(f"{level.key}: {len(found)} units, " + ", ".join(
            f"{sub or '?'} {share:.0%}" for sub, share in sorted(shares.items(), key=lambda kv: str(kv[0]))))
        drafted: list[tuple[Unit, dict[str, Any], str]] = []
        for unit in found:
            if unit.has_office:
                stats[f"{level.key}:has-office"] += 1
                continue
            if (level.archetype, unit.qid) in claimed:
                # The run's holders name this seat: their candidate makes it, and feeds them.
                stats[f"{level.key}:mention-has-it"] += 1
                supersede(cc, f"unit/{level.key}/{unit.qid}")
                continue
            if shares[unit.subdivision] < COMPLETE_AT and not level.source_for(unit.subdivision):
                stats[f"{level.key}:set-not-started"] += 1
                continue
            text, url = "", f"https://www.wikidata.org/wiki/{unit.qid}"
            if unit.title:
                try:
                    text, url = read(level.lang, unit.title)
                except Exception as exc:  # noqa: BLE001 -- one unreadable article is one skip
                    log(f"{unit.qid} {unit.title}: unreadable: {exc}")
                    stats[f"{level.key}:unreadable"] += 1
                    continue
            elif not unit.head:
                stats[f"{level.key}:unit/no-article"] += 1
                continue
            draft, why = draft_for(level, unit, text, url)
            if draft is None:
                stats[f"{level.key}:{why}"] += 1
                # A unit drafted by an earlier run, whose article no longer qualifies.
                supersede(cc, f"unit/{level.key}/{unit.qid}")
                continue
            drafted.append((unit, draft, url))
        clash = homonyms([d for _u, d, _url in drafted])
        for unit, draft, url in drafted:
            ref = f"unit/{level.key}/{unit.qid}"
            if unit.qid in clash:
                stats[f"{level.key}:unit/homonym-label"] += 1
                supersede(cc, ref)
                continue
            stats[f"{level.key}:unit/drafted"] += 1
            db.conn().execute(UPSERT_SQL, (
                cc, ref, level.institution_class, level.archetype,
                draft["single_seat"], Jsonb(draft), url, list(PROTECTED_STATUSES)))
    return stats


def build_bodies(cc: str, level: Level, state: str, read: Callable[[str, str], tuple[str, str]],
                 log: Callable[[str], None] = print) -> Counter[str]:
    """Write a candidate for every listed body whose head has no office yet.

    Each body is listed by hand with its head's title, so no share of a level
    must be started first: the census is the source that the office exists.
    """
    stats: Counter[str] = Counter()
    found = body_units(level, state)
    log(f"{level.key}: {len(found)} bodies, {sum(u.has_office for _b, u in found)} with a head office")
    for body, unit in found:
        ref = f"unit/{level.key}/{unit.qid}"
        if unit.has_office:
            stats[f"{level.key}:has-office"] += 1
            supersede(cc, ref)
            continue
        text, url = "", f"https://www.wikidata.org/wiki/{unit.qid}"
        if unit.title:
            try:
                text, url = read(level.lang, unit.title)
            except Exception as exc:  # noqa: BLE001 -- one unreadable article is one skip
                log(f"{unit.qid} {unit.title}: unreadable: {exc}")
                stats[f"{level.key}:unreadable"] += 1
                continue
        elif not unit.head:
            stats[f"{level.key}:unit/no-article"] += 1
            continue
        draft, why = body_draft(level, body, unit, text, url, state)
        stats[f"{level.key}:{why}"] += 1
        if draft is None:
            supersede(cc, ref)
            continue
        db.conn().execute(UPSERT_SQL, (
            cc, ref, level.institution_class, level.archetype,
            draft["single_seat"], Jsonb(draft), url, list(PROTECTED_STATUSES)))
    return stats


def homonyms(drafts: Sequence[dict[str, Any]]) -> set[str]:
    """The units whose office would share a label with another unit's of the level.

    Two powiats are both "powiat bielski", so both heads would be "starosta
    bielski": a label nobody could tell apart from its twin, and the guard
    would let the first through and refuse the second. Neither is drafted.
    """
    seen: dict[tuple[str, str], set[str]] = {}
    for draft in drafts:
        for lang, text in draft["labels"].items():
            seen.setdefault((lang, fold(text)), set()).add(draft["jurisdiction_qid"])
    return {qid for units_ in seen.values() if len(units_) > 1 for qid in units_}
