"""Read officeholder rosters out of Wikipedia list articles.

Spanish-language wikis keep a dated table per office — `Anexo:Ministros de
Trabajo de Ecuador`, `Anexo:Presidentes del Ecuador` — listing every holder
with start/end dates, the appointing president, a per-row citation and a
colour legend marking acting officials. One roster answers for a whole
office, so reach for this instead of reading N biographies that each restate
the same table: the roster supplies the dates, the reference to cite, and the
acting flag that would otherwise have to be inferred.

The rendered HTML is parsed rather than the wikitext, because `rowspan` is
load-bearing here — a shared reference or appointer cell belongs to every row
it spans, and only the rendered grid says which those are.
"""

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

from lxml import html as lxml_html

#: Month names as they appear in date cells, per wiki language. Slavic dates
#: are written in the genitive ("16 июля 1990"), which is the only form that
#: occurs in a date cell, so only that form is listed.
MONTHS = {
    # Spanish
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
    # Russian
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11,
    "декабря": 12,
    # Belarusian
    "студзеня": 1, "лютага": 2, "сакавіка": 3, "красавіка": 4, "траўня": 5,
    "чэрвеня": 6, "ліпеня": 7, "жніўня": 8, "верасня": 9, "кастрычніка": 10,
    "лістапада": 11, "снежня": 12,
    # Ukrainian
    "січня": 1, "лютого": 2, "березня": 3, "квітня": 4, "травня": 5,
    "червня": 6, "липня": 7, "серпня": 8, "вересня": 9, "жовтня": 10,
    "листопада": 11, "грудня": 12,
    # Czech
    "ledna": 1, "února": 2, "března": 3, "dubna": 4, "května": 5, "června": 6,
    "července": 7, "srpna": 8, "září": 9, "října": 10, "listopadu": 11,
    "prosince": 12,
}

#: Header text → column role. Matched on a normalised, accent-free prefix, so
#: one entry covers a family of spellings. Ordered: the first match wins, which
#: matters where one language's word for "start" prefixes another's for "term".
COLUMN_ROLES = [
    # Spanish
    ("nombre", "name"), ("ministro", "name"), ("titular", "name"),
    ("presidente", "name"), ("funcionario", "name"),
    ("inicio", "start"), ("desde", "start"), ("asuncion", "start"),
    ("finalizacion", "end"), ("fin", "end"), ("hasta", "end"), ("cese", "end"),
    ("periodo", "period"), ("mandato", "period"), ("duracion", "period"),
    ("designante", "appointer"), ("designado", "appointer"),
    ("nombrado", "appointer"), ("gobierno", "appointer"),
    ("partido", "party"), ("ref", "ref"), ("observacion", "notes"),
    ("cartera", "office"), ("cargo", "office"), ("institucion", "office"),
    # Russian / Belarusian / Ukrainian
    ("имя", "name"), ("імя", "name"), ("ім'я", "name"), ("ф.и.о", "name"),
    ("фио", "name"), ("фамилия", "name"), ("прозвішча", "name"),
    ("министр", "name"), ("міністр", "name"),
    ("портрет", "portrait"), ("партрэт", "portrait"), ("фото", "portrait"),
    ("здымак", "portrait"),
    ("начало", "start"), ("вступил", "start"), ("пачатак", "start"),
    ("з", "start"),
    ("окончание", "end"), ("покинул", "end"), ("конец", "end"),
    ("заканчэнне", "end"), ("па", "end"),
    ("срок", "period"), ("полномочия", "period"), ("тэрмін", "period"),
    ("термін", "period"), ("период", "period"), ("каденция", "period"),
    ("час", "period"), ("гады", "period"), ("роки", "period"),
    ("глава правительства", "appointer"), ("премьер", "appointer"),
    ("прэзідэнт", "appointer"), ("кіраўнік урада", "appointer"),
    ("президент", "appointer"),
    ("партия", "party"), ("партыя", "party"),
    ("примечания", "notes"), ("заўвагі", "notes"), ("каментар", "notes"),
    ("источник", "ref"),
    # Czech. Two-word keys come first: "Předseda vlády" names the appointing
    # premier, while a bare "Předseda" heads a list of the office's own holders.
    ("předseda vlády", "appointer"), ("vláda", "appointer"),
    ("nominant", "appointer"), ("prezident", "appointer"),
    ("pořadí", "ordinal"),
    ("jméno", "name"), ("ministr", "name"), ("premiér", "name"),
    ("soudce", "name"), ("předseda", "name"),
    ("portrét", "portrait"), ("fotografie", "portrait"), ("obrázek", "portrait"),
    ("funkční období", "period"), ("působení v úřadu", "period"),
    ("začátek a konec", "period"), ("období", "period"),
    ("nástup", "start"), ("začátek", "start"),
    ("opuštění", "end"), ("odchod", "end"), ("konec", "end"),
    # The day count sits under the same "Funkční období" header as the dates,
    # and a plausible tenure length ("1939") parses as a year if left unnamed.
    ("dny", "days"), ("délka", "days"),
    ("strana", "party"), ("subjekt", "party"),
    ("gesce", "office"),
    ("poznámky", "notes"), ("podrobnosti", "notes"),
]

# Wikipedia writes date ranges with every dash there is, plus a few words for
# "still in office".
DASHES = "-–—‒―"
INCUMBENT = re.compile(
    r"actualidad|presente|en\s+(?:el\s+)?(?:cargo|funciones)|actual|titular$"
    r"|настоящее\s+врем|по\s+сей\s+день|н\.\s*в\.|дагэтуль|цяпер|зараз"
    r"|дзеючы|теперішній|нині"
    r"|úřadující|současnost|dosud",
    re.I,
)
BACKGROUND = re.compile(r"background(?:-color)?\s*:\s*(#[0-9A-Fa-f]{3,8})")
#: Some wikis mark an acting officeholder in the cell text instead of by
#: colour: "(в. а.)" on be.wikipedia, "и. о." on ru.wikipedia.
ACTING_TEXT = re.compile(
    r"\(\s*(?:в\.?\s*а\.?|в\.?\s*і\.?\s*а\.?|и\.?\s*о\.?|в\.?\s*и\.?\s*о\.?"
    r"|acting|interim|encargad\w*)\s*\)|выконва\w*\s+абавязк|исполняющ\w*\s+обязанност",
    re.I,
)
FOOTNOTE_ID = re.compile(r"#(cite_note[-_][\w.%-]+)")
#: Rows recording a gap in the succession rather than a person. cs.wikipedia
#: numbers "Funkce neobsazena" (post unfilled) and "Funkce nevyužívána" (post
#: not in use) among the holders, and they would otherwise be offered up for
#: identification and clutter the audit's item-creation column. Matched against
#: the FOLDED name, so the pattern itself is accent-free.
VACANT = re.compile(
    r"^(?:funkce\s+(?:neobsazena|nevyuzivana)|neobsazeno|urad\s+neobsazen"
    r"|vacante|vacant|vakansiya|вакансия|вакантна)\b",
    re.I,
)


def _deaccent(text: str) -> str:
    """Fold the diacritics that vary between spellings of the same header.

    Cyrillic і/ў/ё are folded too: be-tarask and be spell the same column
    header differently ("Тэрмін" / "Тэрмiн"), and ru "ё" is routinely typed
    as "е".
    """
    trans = str.maketrans(
        "áéíóúüñÁÉÍÓÚÜÑіїўёІЇЎЁ" "áčďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ",
        "aeiouunAEIOUUNиiуеИIУЕ" "acdeeinorstuuyzACDEEINORSTUUYZ",
    )
    return text.translate(trans)


def _norm(text: str) -> str:
    return _deaccent(" ".join(text.split())).casefold().strip(" .:")


def fold(text: str) -> str:
    """Compare wiki text the way this module does: whitespace-collapsed,
    diacritic-folded (і→и, ñ→n), lowercased.

    Callers matching their own patterns against headings or cell text should
    fold both sides, or "Міністры" will not match a pattern written "министр".
    """
    return _norm(text)


@lru_cache(maxsize=1)
def _role_keys() -> List[Tuple[str, str]]:
    """`COLUMN_ROLES` with keys folded exactly the way headers are."""
    return [(_norm(key), role) for key, role in COLUMN_ROLES]


def parse_date(text: str) -> Optional[str]:
    """A Spanish date as a partial ISO string: `1979-08-10`, `1979-08`, `1979`.

    Returns None when the cell holds no year at all, so callers can tell
    "no date given" from "date given but coarse".
    """
    low = " ".join(text.split()).casefold()
    # "10 de agosto de 1979" (es), "16 июля 1990" (ru/be/uk) and "2. července
    # 1992" (cs) all reduce to day, month word, year — the Czech day is an
    # ordinal, so the dot after it has to be allowed for or the day is lost.
    day_month = re.search(
        r"\b(\d{1,2})\s*\.?\s*(?:de\s*)?([^\W\d_]+)\s*(?:de\s*)?(\d{4})", low
    )
    if day_month:
        month = MONTHS.get(_deaccent(day_month.group(2)), MONTHS.get(day_month.group(2)))
        if month:
            return f"{day_month.group(3)}-{month:02d}-{int(day_month.group(1)):02d}"
    month_year = re.search(r"\b([^\W\d_]+)\s*(?:de\s*)?(\d{4})", low)
    if month_year:
        month = MONTHS.get(_deaccent(month_year.group(1)), MONTHS.get(month_year.group(1)))
        if month:
            return f"{month_year.group(2)}-{month:02d}"
    iso = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", low)
    if iso:
        return iso.group(0)
    numeric = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", low)
    if numeric:
        return f"{numeric.group(3)}-{int(numeric.group(2)):02d}-{int(numeric.group(1)):02d}"
    year = re.search(r"\b(1[5-9]\d\d|20[0-4]\d)\b", low)
    return year.group(1) if year else None


def parse_period(text: str) -> Tuple[Optional[str], Optional[str], bool]:
    """Split a "start – end" cell. Returns (start, end, still_in_office)."""
    cleaned = " ".join(text.split())
    incumbent = bool(INCUMBENT.search(cleaned))
    # Split on a dash that separates two dates, not the one inside "1979-08-10"
    # or a hyphenated name.
    parts = re.split(rf"\s+[{DASHES}]+\s+|\s*[{DASHES}]{{2,}}\s*", cleaned)
    if len(parts) == 1 and re.search(rf"\d\s*[{DASHES}]\s*\d", cleaned):
        parts = re.split(rf"(?<=\d)\s*[{DASHES}]\s*(?=\d)", cleaned, maxsplit=1)
    start = parse_date(parts[0]) if parts else None
    end = parse_date(parts[1]) if len(parts) > 1 else None
    if incumbent:
        end = None
    return start, end, incumbent


@dataclass
class RosterRow:
    #: 1-based position in the table, for citing a row in review output.
    ordinal: int
    #: The full-width header row above this one — usually the institution's
    #: name at the time ("Ministerio de Información y Turismo"), which is how
    #: renamed and predecessor bodies announce themselves.
    section: Optional[str]
    name: str
    #: Wikipedia article title, when the name is linked.
    link: Optional[str]
    #: For a spell covered by another office's holder, the office they came
    #: from ("Subsecretario de Turismo"). The name is then that person's.
    covering: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None
    incumbent: bool = False
    period_raw: str = ""
    appointer: Optional[str] = None
    #: Legend texts for the row's background colours — "Funcionario encargado
    #: de las funciones sin titularidad" is how acting officials are marked.
    flags: List[str] = field(default_factory=list)
    ref_urls: List[str] = field(default_factory=list)
    cells: Dict[str, str] = field(default_factory=dict)

    @property
    def acting(self) -> bool:
        return any(
            re.search(r"encargad|interin|subrogante|acting|в\.\s*а|и\.\s*о", f, re.I)
            for f in self.flags
        )


@dataclass
class Roster:
    """One wikitable from a list article."""

    #: Column roles in table order, e.g. ["name", "start", "end", "ref"].
    columns: List[str]
    rows: List[RosterRow]
    #: Colour → legend text, as declared by `{{leyenda}}` above the table.
    legend: Dict[str, str] = field(default_factory=dict)
    #: Article section heading above the table. List articles routinely put
    #: the office's own holders in one table and its predecessor agencies'
    #: directors in the next, distinguished only by this heading.
    heading: Optional[str] = None


def _legend(doc) -> Dict[str, str]:
    """Colour swatch → its explanation, from the `{{leyenda}}` spans."""
    legend: Dict[str, str] = {}
    for span in doc.xpath("//span[contains(@style, 'background')]"):
        colour = BACKGROUND.search(span.get("style", "") or "")
        if colour is None:
            continue
        text = " ".join((span.getparent().text_content() or "").split())
        # The swatch span is empty; its meaning sits in the parent's text.
        text = re.sub(r"^\s*color\s*#[0-9A-Fa-f]+\s*", "", text).strip()
        if text:
            legend.setdefault(colour.group(1).upper(), text)
    return legend


def _footnotes(doc) -> Dict[str, List[str]]:
    """Footnote id → the external URLs cited in it."""
    notes: Dict[str, List[str]] = {}
    for item in doc.xpath("//li[starts-with(@id, 'cite_note')]"):
        urls = [
            a.get("href")
            for a in item.xpath(".//a[@href]")
            if (a.get("href") or "").startswith("http")
        ]
        if urls:
            notes[item.get("id")] = urls
    return notes


def _grid(table) -> List[List[Tuple[object, bool]]]:
    """Expand a table into a rectangular grid of (cell, is_origin) pairs.

    `is_origin` is False for the positions a `rowspan`/`colspan` cell was
    stretched into, which is how a reference shared by three rows still
    reaches all three.
    """
    grid: List[List[Optional[Tuple[object, bool]]]] = []
    for r, tr in enumerate(table.xpath(".//tr")):
        while len(grid) <= r:
            grid.append([])
        col = 0
        for cell in tr.xpath("./td|./th"):
            row = grid[r]
            while col < len(row) and row[col] is not None:
                col += 1
            try:
                rowspan = max(1, int(cell.get("rowspan", 1)))
                colspan = max(1, int(cell.get("colspan", 1)))
            except ValueError:
                rowspan = colspan = 1
            for dr in range(rowspan):
                while len(grid) <= r + dr:
                    grid.append([])
                target = grid[r + dr]
                for dc in range(colspan):
                    while len(target) <= col + dc:
                        target.append(None)
                    if target[col + dc] is None:
                        target[col + dc] = (cell, dr == 0 and dc == 0)
            col += colspan
    width = max((len(row) for row in grid), default=0)
    out: List[List[Tuple[object, bool]]] = []
    for row in grid:
        row = row + [None] * (width - len(row))
        out.append([c if c is not None else (None, False) for c in row])
    return out


def _roles(header: List[Tuple[object, bool]], width: int) -> List[str]:
    roles: List[str] = []
    for index, (cell, _) in enumerate(header):
        text = _norm(cell.text_content()) if cell is not None else ""
        role = f"col{index}"
        for prefix, candidate in _role_keys():
            # Prefix matching is what lets one entry cover "Начало" and "Начало
            # полномочий", but a two-letter key ("па" = until) would swallow any
            # header starting with it ("Партрэт"), so those must match whole.
            if text == prefix or (len(prefix) >= 3 and text.startswith(prefix)):
                role = candidate
                break
        roles.append(role)
    # A name column spanning image + name yields two positions with the same
    # role; the image one carries no text and is harmless.
    return roles + [f"col{i}" for i in range(len(roles), width)]


def _subroles(
    roles: List[str], header: List[Tuple[object, bool]]
) -> List[str]:
    """Refine column roles from a second header row that subdivides the first.

    Reach for this wherever a wide header has its own sub-labels: cs.wikipedia
    heads three columns "Funkční období" and labels them "Nástup do úřadu",
    "Opuštění úřadu", "Dny v úřadu". Reading only the top row leaves the day
    count indistinguishable from the dates, and a plausible tenure of 1939 days
    then parses as the year 1939.
    """
    out = list(roles)
    for index, (cell, is_origin) in enumerate(header):
        if cell is None or not is_origin or index >= len(out):
            continue
        text = _norm(cell.text_content())
        for prefix, role in _role_keys():
            if text == prefix or (len(prefix) >= 3 and text.startswith(prefix)):
                out[index] = role
                break
    return out


def _cell_text(cell, keep_breaks: bool = False) -> str:
    if cell is None:
        return ""
    clone = lxml_html.fromstring(lxml_html.tostring(cell))
    for junk in clone.xpath(".//sup[contains(@class, 'reference')]|.//style|.//span[@typeof]"):
        junk.getparent().remove(junk)
    if keep_breaks:
        for br in clone.xpath(".//br"):
            br.tail = "\n" + (br.tail or "")
        lines = (" ".join(part.split()) for part in clone.text_content().split("\n"))
        return "\n".join(line for line in lines if line)
    return " ".join(clone.text_content().split())


#: "Subsecretario de Turismo (Bolívar Cevallos Machuca)", or the same thing
#: written across a line break — an interim spell filled by whoever held
#: another office, written office-first.
COVERING = re.compile(
    r"^\s*((?:vice|sub)?(?:presidenta?|ministr[oa]|secretari[oa]|director[a]?|encargad[oa])"
    r"\w*[^()]*?)\s*\(([^)]+)\)\s*$",
    re.I,
)
OFFICE_LINE = re.compile(
    r"^(?:vice|sub)?(?:presidenta?|ministr[oa]|secretari[oa]|subsecretari[oa]|"
    r"director[a]?|encargad[oa]|gobernador[a]?)\b",
    re.I,
)


def _split_covering(name: str) -> Tuple[str, Optional[str]]:
    """Separate "who" from "in what other capacity", if the cell says both."""
    lines = [line for line in name.split("\n") if line]
    if len(lines) > 1 and OFFICE_LINE.match(lines[0]):
        return lines[-1], lines[0]
    name = " ".join(" ".join(lines).split())
    match = COVERING.match(name)
    if match is None:
        return name, None
    return " ".join(match.group(2).split()), " ".join(match.group(1).split())


def _person_link(cell) -> Optional[str]:
    if cell is None:
        return None
    for anchor in cell.xpath(".//a[@href]"):
        href = anchor.get("href") or ""
        if not href.startswith("/wiki/"):
            continue
        title = anchor.get("title") or ""
        if ":" in title or "mw-file" in (anchor.get("class") or ""):
            continue  # File:/Category: links, i.e. the portrait
        return title
    return None


def _colours(element) -> List[str]:
    """Background colours an element declares, via CSS or the legacy attribute.

    Both spellings occur in the same table — `{{leyenda}}` rows are usually
    `bgcolor="#B6FFC0"`, which a style-only reader would silently miss and
    thereby lose every acting-official marker on the page.
    """
    if element is None:
        return []
    colours = BACKGROUND.findall(element.get("style") or "")
    legacy = (element.get("bgcolor") or "").strip()
    if legacy:
        colours.append(legacy if legacy.startswith("#") else f"#{legacy}")
    return colours


def _flags(row_cells: List[Tuple[object, bool]], tr, legend: Dict[str, str]) -> List[str]:
    elements = [tr] + [cell for cell, _ in row_cells]
    flags: List[str] = []
    for element in elements:
        for colour in _colours(element):
            text = legend.get(colour.upper())
            if text and text not in flags:
                flags.append(text)
    return flags


def parse_rosters(page_html: str) -> List[Roster]:
    """Every wikitable in a rendered list article, as roster rows."""
    doc = lxml_html.fromstring(page_html)
    legend = _legend(doc)
    notes = _footnotes(doc)
    headings: Dict[object, Optional[str]] = {}
    current: Optional[str] = None
    for element in doc.iter("h1", "h2", "h3", "h4", "table"):
        if element.tag == "table":
            headings[element] = current
        else:
            text = " ".join(element.text_content().split())
            current = re.sub(r"\[\s*editar[^]]*\]", "", text).strip() or current
    rosters: List[Roster] = []
    for table in doc.xpath("//table[contains(@class, 'wikitable')]"):
        grid = _grid(table)
        if not grid:
            continue
        trs = table.xpath(".//tr")
        width = len(grid[0])
        roles: List[str] = []
        section: Optional[str] = None
        rows: List[RosterRow] = []
        for index, row_cells in enumerate(grid):
            origins = [(cell, new) for cell, new in row_cells if cell is not None and new]
            if not origins:
                continue
            is_header = all(cell.tag == "th" for cell, _ in origins)
            spans_row = len(origins) == 1 and int(origins[0][0].get("colspan", 1)) >= width
            if is_header and spans_row:
                section = _cell_text(origins[0][0]) or section
                continue
            if is_header:
                roles = _subroles(roles, row_cells) if roles else _roles(row_cells, width)
                continue
            if not roles:
                roles = [f"col{i}" for i in range(width)]
            # A role can span several columns: "Nombre" over portrait+name, or
            # — load-bearing — a single "Período" header colspanning the start
            # and end cells. Keep every value in column order.
            values: Dict[str, List[str]] = {}
            for role, (cell, _) in zip(roles, row_cells):
                text = _cell_text(cell)
                if text and text not in values.setdefault(role, []):
                    values[role].append(text)
            cells: Dict[str, str] = {
                role: " – ".join(texts) for role, texts in values.items() if texts
            }
            name_index = roles.index("name") if "name" in roles else 0
            # The declared column first, then its neighbours: a "Nombre" header
            # can span portrait + name, and cs.wikipedia's education list fills
            # the *portrait* cell with the name and leaves the name cell empty.
            # A date or a bare ordinal is never a name, so such a candidate is
            # skipped rather than taken — otherwise the row is filed under
            # "3. července 1992".
            name_cell = None
            name_is_new = False
            for offset in (name_index, name_index + 1, name_index - 1):
                if not 0 <= offset < width:
                    continue
                cell, is_origin = row_cells[offset]
                text = _cell_text(cell) if cell is not None else ""
                if not text or _is_date_phrase(text):
                    continue
                name_cell, name_is_new = cell, is_origin
                break
            name = _cell_text(name_cell, keep_breaks=True) if name_cell is not None else ""
            name = name or cells.get("name", "")
            if not name:
                continue
            # A person whose spell straddles two cabinets gets one row per
            # cabinet, with the name and dates rowspanned across them. Only the
            # party and cabinet cells are new, so the later rows restate a term
            # already recorded — keeping them would double the statement.
            dates_are_new = any(
                is_origin
                for role, (cell, is_origin) in zip(roles, row_cells)
                if role in ("period", "start", "end") and cell is not None
                and _cell_text(cell)
            )
            if not name_is_new and not dates_are_new:
                continue
            name, covering = _split_covering(name)
            if VACANT.match(fold(name)):
                continue
            acting_text = ACTING_TEXT.search(name) or ACTING_TEXT.search(
                cells.get("notes", "")
            )
            if acting_text:
                name = " ".join(ACTING_TEXT.sub(" ", name).split())
            ref_urls: List[str] = []
            for cell, _ in row_cells:
                if cell is None:
                    continue
                for anchor in cell.xpath(".//sup[contains(@class, 'reference')]//a[@href]"):
                    match = FOOTNOTE_ID.search(anchor.get("href") or "")
                    if match:
                        for url in notes.get(match.group(1), []):
                            if url not in ref_urls:
                                ref_urls.append(url)
            periods = values.get("period", [])
            if len(periods) > 1:
                # Two cells under one "Período" header: start, then end.
                start, end = parse_date(periods[0]), parse_date(periods[1])
                incumbent = bool(INCUMBENT.search(periods[1]))
                if incumbent:
                    end = None
                period_raw = " – ".join(periods[:2])
            elif periods:
                start, end, incumbent = parse_period(periods[0])
                period_raw = periods[0]
            else:
                start = parse_date(cells.get("start", "")) if cells.get("start") else None
                end = parse_date(cells.get("end", "")) if cells.get("end") else None
                incumbent = bool(INCUMBENT.search(cells.get("end", "")))
                if incumbent:
                    end = None
                period_raw = f"{cells.get('start', '')} – {cells.get('end', '')}".strip(" –")
            tr = trs[index] if index < len(trs) else None
            rows.append(
                RosterRow(
                    ordinal=len(rows) + 1,
                    section=section,
                    name=name,
                    link=_person_link(name_cell),
                    covering=covering,
                    start=start,
                    end=end,
                    incumbent=incumbent,
                    period_raw=period_raw,
                    appointer=cells.get("appointer"),
                    flags=_flags(row_cells, tr, legend)
                    + ([f"acting, per the row text: {acting_text.group(0).strip()}"]
                       if acting_text else []),
                    ref_urls=ref_urls,
                    cells=cells,
                )
            )
        if rows:
            rosters.append(
                Roster(
                    columns=roles,
                    rows=rows,
                    legend=legend,
                    heading=headings.get(table),
                )
            )
    return rosters


#: Where a bullet keeps its term. Three shapes occur, all in ru.wikipedia
#: ministry articles alone: the dates parenthesised at the end (optionally
#: followed by "." or ";"), the dates leading the line before an em dash, and
#: a parenthesised term trailed by a note ("(1963—1984; министр
#: автомобильного транспорта)").
BULLET_PERIOD = re.compile(r"\(([^()]*\d{3,4}[^()]*)\)\s*[;.,]*\s*$")
BULLET_PERIOD_FIRST = re.compile(
    r"^\s*([^—–]*\d{4}[^—–]*(?:[—–][^—–]*\d{4}[^—–]*)?)\s*[—–]\s*(\S.*)$"
)
#: "(р. 1966)", "(нар. 1973)" — a birth year, not a term. Kept as a row (the
#: person may still be a genuine holder) but with no dates attached.
BIRTH_ONLY = re.compile(r"^\s*(?:р|нар|род|нар\.|b|born)\b\.?\s*\d{4}\s*$", re.I)
#: Sections that list the holders of the office the page is about. Ministry
#: articles also carry deputies, boards and a link farm, so both an allowlist
#: and a denylist are needed — "Первые заместители министра" contains
#: "министр".
BULLET_HEADINGS = re.compile(
    r"минист|мініст|ministr|руковод|кіраўн|кираун|глав|очільник|спіс|список|"
    r"holders|list of",
    re.I,
)
BULLET_NOT_HEADINGS = re.compile(
    r"заместител|намесн|заступник|ссылк|литератур|источник|примечан|"
    r"сноск|калегі|коллеги|deputy|see also|referen",
    re.I,
)
#: Military and courtesy ranks printed ahead of the name, and the
#: interlanguage-link markers ("[бел.]") that render inside it.
DEPUTY_ROW = re.compile(
    r"^\s*(?:первый\s+)?(?:заместител|намесн|заступник|deputy|vice)", re.I
)
NAME_NOISE = re.compile(
    r"^\s*(?:генерал[\w-]*|палкоўнік|подполковник|падпалкоўнік|полковник|"
    r"маёр|майор|адмирал|адмірал|маршал|капитан|камандзір|тав\.)\s+|"
    r"\[[^\]]{1,12}\]",
    re.I,
)


def _is_date_phrase(text: str) -> bool:
    """Is this text nothing but a date or date range?

    Guards the dates-first bullet shape: "Корбут, Николай Петрович (1997" also
    ends in a year, and reading it as the term would drop the real end date
    sitting after the dash.
    """
    stop = {"с", "по", "до", "год", "года", "г", "гг", "з", "да", "у", "de"}
    # `DASHES` must be escaped inside the class: unescaped, its leading "-"
    # follows "/" and forms the range U+002F–U+2013, which swallows every digit
    # and letter, leaving no tokens and making this function always False.
    separators = re.escape(" \t.,()/" + DASHES)
    tokens = [t for t in re.split(rf"[\s{separators}]+", _deaccent(_norm(text))) if t]
    if not tokens:
        return False
    for token in tokens:
        if token.isdigit() or token in stop:
            continue
        stem = token[:5]
        if len(stem) >= 4 and any(_deaccent(m).startswith(stem) for m in MONTHS):
            continue
        return False
    return True


def _is_date_link(title: str) -> bool:
    """Bullets link their dates ("[[16 июля]] [[1990]]", "[[Декабрь]]").

    Month names are matched by stem, because a link uses the nominative
    ("Декабрь") where a date cell uses the genitive ("декабря").
    """
    text = _deaccent(_norm(title))
    if re.fullmatch(r"\d{1,2}\s+[^\W\d_]+|\d{3,4}(?:\s*год)?", text):
        return True
    stem = text[:5]
    return len(stem) >= 4 and any(
        _deaccent(month).startswith(stem) for month in MONTHS
    )


def parse_bullet_rosters(page_html: str) -> List[Roster]:
    """Officeholders listed as bullets rather than tabulated.

    Wikis outside the table-making habit write the same information as a list —
    ru.wikipedia's ministry articles run `* rank [[Name]] (16 июля 1990 —
    25 января 1994)<ref>` — and the ministry article is then the only roster
    an office has. Rows carry the same fields as table rows, so callers can
    treat both alike; `columns` is `["bullet"]` to mark the provenance.
    """
    doc = lxml_html.fromstring(page_html)
    notes = _footnotes(doc)
    heading: Optional[str] = None
    rosters: List[Roster] = []
    for element in doc.iter("h1", "h2", "h3", "h4", "ul"):
        if element.tag != "ul":
            text = " ".join(element.text_content().split())
            heading = re.sub(r"\[\s*(?:editar|edit|править|правіць)[^]]*\]", "", text).strip() or heading
            continue
        if element.getparent() is not None and element.getparent().tag in ("li", "table", "td"):
            continue  # nested list, or a navbox
        if heading and (
            not BULLET_HEADINGS.search(heading) or BULLET_NOT_HEADINGS.search(heading)
        ):
            continue
        rows: List[RosterRow] = []
        for item in element.xpath("./li"):
            text = _cell_text(item)
            # Leading dates win over trailing parentheses: a line that has both
            # ("1921 — Боркусевич (1892—1930)") states the term first and the
            # person's *lifespan* in the brackets.
            leading = BULLET_PERIOD_FIRST.match(text)
            if leading is not None and _is_date_phrase(leading.group(1)):
                period_text, name_text = leading.group(1), leading.group(2)
            else:
                period = BULLET_PERIOD.search(text)
                if period is None:
                    continue
                period_text, name_text = period.group(1), text[: period.start()]
            name_text = re.sub(r"\([^()]*\)\s*[;.,]*\s*$", " ", name_text)
            # A note can share the parentheses with the dates ("1963—1984;
            # министр автомобильного транспорта"); the term comes first.
            period_text = period_text.split(";")[0]
            anchors = [
                a for a in item.xpath(".//a[@href]")
                if (a.get("href") or "").startswith("/wiki/")
                and ":" not in (a.get("title") or "x")
                and not _is_date_link(a.get("title") or "")
            ]
            # Ranks and offices are linked ahead of the person ("генерал-майор
            # [[Name]]"), so the last link before the dates is the officeholder.
            link = anchors[-1].get("title") if anchors else None
            name = " ".join(name_text.split())
            if DEPUTY_ROW.match(name):
                continue
            while NAME_NOISE.search(name):
                name = " ".join(NAME_NOISE.sub(" ", name).split())
            name, covering = _split_covering(name)
            if VACANT.match(fold(name)):
                continue
            acting_text = ACTING_TEXT.search(text)
            if acting_text:
                name = " ".join(ACTING_TEXT.sub(" ", name).split())
            if link and len(name_tokens(link)) >= 2:
                name = link.split(" (")[0]
            if len(name_tokens(name)) < 2:
                continue
            if BIRTH_ONLY.match(period_text):
                start, end, incumbent = None, None, False
            else:
                start, end, incumbent = parse_period(period_text)
            ref_urls: List[str] = []
            for anchor in item.xpath(".//sup[contains(@class, 'reference')]//a[@href]"):
                match = FOOTNOTE_ID.search(anchor.get("href") or "")
                if match:
                    for url in notes.get(match.group(1), []):
                        if url not in ref_urls:
                            ref_urls.append(url)
            rows.append(
                RosterRow(
                    ordinal=len(rows) + 1,
                    section=None,
                    name=name,
                    link=link,
                    covering=covering,
                    start=start,
                    end=end,
                    incumbent=incumbent,
                    period_raw=period_text,
                    flags=[f"acting, per the row text: {acting_text.group(0).strip()}"]
                    if acting_text
                    else [],
                    ref_urls=ref_urls,
                    cells={"bullet": text},
                )
            )
        if len(rows) >= 2:
            rosters.append(Roster(columns=["bullet"], rows=rows, heading=heading))
    return rosters


def merge_terms(rows: List[RosterRow]) -> List[Tuple[Optional[str], Optional[str]]]:
    """Collapse a person's consecutive roster rows into continuous terms.

    Rosters split a single uninterrupted spell into several rows whenever
    something *else* changes — a new appointing president, a ministry rename —
    and each split would otherwise become a spurious extra P39 statement.
    """
    terms: List[Tuple[Optional[str], Optional[str]]] = []
    previous: Optional[RosterRow] = None
    seen: set = set()
    for row in sorted(rows, key=lambda r: (r.start or "", r.ordinal)):
        if (row.start, row.end, row.acting) in seen:
            continue  # two rows describing one term, e.g. a rowspan restatement
        seen.add((row.start, row.end, row.acting))
        continuous = (
            previous is not None
            and previous.acting == row.acting
            and previous.end is not None
            and previous.end == row.start
        )
        if continuous and terms:
            terms[-1] = (terms[-1][0], row.end)
        else:
            terms.append((row.start, row.end))
        previous = row
    return terms


def name_tokens(name: str) -> List[str]:
    """Comparable name tokens: accent-free, lowercased, no parenthetical."""
    cleaned = re.sub(r"\(.*?\)", " ", name)
    cleaned = re.sub(r"[^\w\s]", " ", _deaccent(cleaned))
    stop = {"de", "del", "la", "las", "los", "y", "e", "da", "dos", "san"}
    return [t for t in cleaned.casefold().split() if t and t not in stop]


def names_match(left: str, right: str) -> bool:
    """True when two spellings of a person's name can be the same person.

    Spellings differ in ways that are systematic per language and would each
    need their own rule: Spanish rosters carry more surnames than the article
    title ("Sandra Vela" vs "Sandra Vela Dávila"), Russian ones flip the order
    and add a patronymic ("Киселёв, Кузьма Венедиктович" vs "Кузьма Киселёв").
    Token subset covers all of them; the floor of two shared tokens is what
    stops every "Juan" matching every other.
    """
    a, b = set(name_tokens(left)), set(name_tokens(right))
    if len(a) < 2 or len(b) < 2:
        return False
    return a <= b or b <= a
