"""Read birth dates out of Wikipedia infoboxes, with a built-in cross-check.

Reach for this when Wikidata is missing `P569` on people whose Wikipedia
article states a birth date anyway — the article's infobox is a structured
field, so the date can be lifted without an LLM reading prose.

Two independent channels are extracted per article and compared, because
roughly one enwiki infobox birth date in twenty disagrees with the value
Wikidata already holds:

* the infobox date itself, taken from the `bday` microformat that
  `{{birth date}}` and friends emit — already normalised to ISO;
* the article's `Category:1965 births`, which editors maintain separately
  from the infobox.

Only agreement on the year is treated as safe to batch; everything else is a
review case. See `Evidence.verdict`.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional

# `{{birth date and age|1954|7|17}}` renders a hCard microformat span. Reading
# the rendered form means never enumerating template spellings.
BDAY = re.compile(r'class="bday[^"]*"[^>]*>\s*([0-9-]+)\s*<')
ISO_DAY = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
ISO_YEAR = re.compile(r"^(\d{4})$")

# Year-precision templates render a bare year with no microformat, so they need
# a wikitext pass. `{{birth year and age|1977}}`, `{{by|1977}}`.
YEAR_TPL = re.compile(
    r"\{\{\s*(?:birth[ _-]?year(?:[ _-]and[ _-]age)?|by)\s*\|\s*"
    r"(?:df\s*=\s*\w+\s*\|\s*)?(1[2-9]\d\d|20[0-4]\d)\s*[|}]",
    re.IGNORECASE,
)

# An infobox that pulls the date from Wikidata cannot tell us anything Wikidata
# does not already have — the field is empty precisely because P569 is missing.
WD_DRIVEN = re.compile(
    r"\{\{\s*#(?:statements|property)\s*:\s*P569|\{\{\s*wikidata\s*\|",
    re.IGNORECASE,
)

HAS_INFOBOX = re.compile(r"\{\{\s*infobox", re.IGNORECASE)
BIRTH_PARAM = re.compile(r"\|\s*birth[ _-]?date\s*=\s*([^|\n]*)", re.IGNORECASE)
#: The birth-year category, per wiki. This is the *second* channel — editors
#: maintain it separately from the infobox, which is what makes agreement
#: between them worth anything.
#:
#: It was English-only, and that failed silently rather than loudly: on any
#: other wiki no category matches, so `Evidence.verdict` is `no-cross-check`
#: forever and every birth date is held back for want of a channel that
#: structurally could not exist. A Polish MP with only a plwiki article could
#: never be dated, and nothing said so.
BIRTH_CATEGORIES = (
    re.compile(r"^(\d{3,4}) births$"),                       # en
    re.compile(r"^Urodzeni w (\d{3,4})$"),                   # pl
    re.compile(r"^Geboren (\d{3,4})$"),                      # de
    re.compile(r"^Родившиеся в (\d{3,4}) году$"),             # ru
    re.compile(r"^Народились\s+(?:у\s+)?(\d{3,4})$"),         # uk
    re.compile(r"^Нарадзіліся ў (\d{3,4})$"),                 # be
    re.compile(r"^Nacidos en (\d{3,4})$"),                   # es
    # fr writes the month in too: "Naissance en décembre 1977".
    re.compile(r"^Naissance en (?:\S+ )?(\d{3,4})$"),         # fr
    re.compile(r"^Narození v roce (\d{3,4})$"),               # cs
    re.compile(r"^Narodenia v roku (\d{3,4})$"),              # sk
    re.compile(r"^Nati nel (\d{3,4})$"),                     # it
    re.compile(r"^Nascidos em (\d{3,4})$"),                  # pt
    # hu vowel harmony: "-ban" or "-ben" depending on the year.
    re.compile(r"^(\d{3,4})-b[ae]n született személyek$"),     # hu
    re.compile(r"^(\d{3,4})\. gadā dzimušie$"),               # lv
    # lt: not verified against a real article — Nausėda carries no
    # birth-year category at all, so this pattern is a guess and is
    # marked as one rather than counted as coverage.
    re.compile(r"^(\d{3,4}) m\. gimę žmonės$"),                # lt (unverified)
    re.compile(r"^مواليد (\d{3,4})$"),                        # ar
    re.compile(r"^زادگان (\d{3,4}) \(میلادی\)$"),             # fa
)

#: "1965 births" has an "unknown"/"missing" sibling that must not be read as a
#: year. Every pattern above requires a year, so an unlocalised sibling cannot
#: be misread as one — this only has to catch the case where an article carries
#: both a year category and a doubt category.
CATEGORY_UNCERTAIN = re.compile(
    r"(births?.*(unknown|missing|uncertain)|year of birth"
    r"|rok urodzenia|Geburtsjahr unbekannt|год рождения неизвестен"
    r"|año de nacimiento desconocido|Date de naissance non renseignée)",
    re.IGNORECASE,
)


def birth_year_category(name: str) -> Optional[str]:
    """The year a births category names, or None. Localised per wiki."""
    for pattern in BIRTH_CATEGORIES:
        match = pattern.match(name)
        if match:
            # `lt` spells the year "1985 m."; keep only the digits.
            return re.sub(r"[^0-9]", "", match.group(1))
    return None


@dataclass
class Evidence:
    """What one article says about its subject's birth date."""

    qid: str
    title: str
    revid: Optional[int] = None
    #: Distinct ISO dates from the infobox microformat.
    bdays: List[str] = field(default_factory=list)
    #: Distinct years from year-precision templates.
    years: List[str] = field(default_factory=list)
    #: Distinct years from `Category:NNNN births`.
    categories: List[str] = field(default_factory=list)
    has_infobox: bool = False
    wikidata_driven: bool = False
    category_uncertain: bool = False
    #: Other QIDs whose article resolved to this same page — duplicate items.
    shares_article_with: List[str] = field(default_factory=list)

    @property
    def value(self) -> Optional[str]:
        """The date to propose, ISO, day precision where available."""
        if self.bdays:
            return self.bdays[0]
        if self.years:
            return self.years[0]
        return None

    @property
    def precision(self) -> Optional[int]:
        """Wikidata time precision: 11 = day, 9 = year."""
        if self.bdays:
            return 11 if ISO_DAY.match(self.bdays[0]) else 9
        return 9 if self.years else None

    @property
    def verdict(self) -> str:
        """Routing decision: `batch` is safe to emit, everything else reviews.

        `conflict` is the valuable one — the infobox and the birth-year
        category disagree, which usually means one of them is wrong on
        Wikipedia too and the article needs a human.

        January 1st is held back separately: it shows up in these infoboxes at
        far above its 1-in-365 share, so a day-precision `-01-01` is more
        likely a placeholder for a year-only date than a real birthday.
        """
        if self.value is None:
            return "nothing-found"
        if self.shares_article_with:
            return "duplicate-item"
        if len(self.bdays) > 1 or len(self.years) > 1:
            return "ambiguous-source"
        if self.category_uncertain:
            return "flagged-uncertain"
        if not self.categories:
            return "no-cross-check"
        if len(self.categories) > 1:
            return "ambiguous-source"
        if self.categories[0] != self.value[:4]:
            return "conflict"
        if self.precision == 11 and self.value[5:] == "01-01":
            return "suspicious-precision"
        return "batch"

    @property
    def reason(self) -> str:
        cats = ",".join(self.categories) or "none"
        return f"infobox={self.value or 'none'} category={cats}"


def parse_wikitext(evidence: Evidence, wikitext: str) -> None:
    """Fill in the signals that only the source form carries."""
    evidence.has_infobox = bool(HAS_INFOBOX.search(wikitext))
    evidence.wikidata_driven = bool(WD_DRIVEN.search(wikitext))
    evidence.years = sorted(set(YEAR_TPL.findall(wikitext)))


def parse_categories(evidence: Evidence, categories: List[str]) -> None:
    for name in categories:
        year = birth_year_category(name)
        if year:
            evidence.categories.append(year)
        elif CATEGORY_UNCERTAIN.search(name):
            evidence.category_uncertain = True
    evidence.categories = sorted(set(evidence.categories))


def parse_lead_html(evidence: Evidence, html: str) -> None:
    found = []
    for raw in BDAY.findall(html):
        if ISO_DAY.match(raw) or ISO_YEAR.match(raw):
            found.append(raw)
    evidence.bdays = sorted(set(found))


def worth_rendering(wikitext: str) -> bool:
    """Whether section 0 is worth a render request.

    Triage step: a filled `birth_date` parameter is the precondition for a
    microformat date, and rendering is one request per article, so skip the
    ~85% of articles that cannot produce one.
    """
    if WD_DRIVEN.search(wikitext):
        return False
    for value in BIRTH_PARAM.findall(wikitext):
        value = value.strip()
        if value and not value.startswith("<!--"):
            return True
    return False
