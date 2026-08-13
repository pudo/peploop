#!/usr/bin/env python
"""Assert `wd.roster` column naming, date parsing and term merging, and
`wd.kinship` descent parsing, against what broke them.

    python scripts/check_dates.py

Reach for this before and after touching either function. Every case below is a
real cell from a real roster that this workbench parsed wrongly at some point,
and `recipes/country_sweep.md` §7 records what each one cost — a silent
month-precision downgrade on the UAE's founding date, a 1,939-day tenure read as
the year 1939. The regression net in `regression/` catches a *decision* that
changed; this catches the parse underneath it, which is cheaper to read.

The Hijri block is the reason this file exists. Most Saudi rosters date in AH,
and no conversion happens: an AH year is simply outside the Gregorian range the
year rule accepts (AH 1500 falls in AD 2076, so nothing in use collides), and a
dual-dated cell keeps its AD half. That behaviour is load-bearing and invisible
— worth pinning before someone "fixes" the year range.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lxml import html as lxml_html

from wd.kinship import _cut_gloss, parse_genealogy
from wd.roster import RosterRow, _roles, merge_terms, parse_date, parse_period

#: (header cells, {column index: required role}, what it is / what it broke)
#:
#: A header this module does not recognise costs every row on the page and says
#: nothing while doing it (§7 #24), so the roles are worth asserting directly.
#: Only the columns that matter are named; the rest may fall through to `colN`,
#: which is the point of the decoy cases — an unnamed column is inert, a
#: *wrongly* named one shadows the cells beside it.
HEADERS = [
    (["المنصب", "شاغل المنصب", "تولى المنصب", "غادر المنصب"],
     {0: "office", 1: "name", 2: "start", 3: "end"},
     "the ~109 `ar:حكومة <رئيس الوزراء>` cabinet articles, Jordan's only dated "
     "source for ministers. 'تولى' was already a start key and 'غادر' was not, "
     "so every row parsed with a start and no end — a lost cell that reads as a "
     "sitting minister"),
    (["رقم المجلس", "الرئيس", "فترة الاستلام: من", "فترة الاستلام: إلى",
      "عدد الأعضاء", "ملاحظة"],
     {1: "name", 2: "period", 3: "period"},
     "ar:مجلس الأعيان الأردني. Without 'الرئيس' the table had no name column "
     "and all 28 rows were dropped for want of one. The two date cells are one "
     "header row, not a colspan with sub-headers, so they take `period` twice "
     "and are joined into a range — no `_subroles` refinement needed"),
    (["عضو", "حزب، حفلة", "تاريخ اليمين الدستورية"],
     {0: "name", 2: "start"},
     "the 27th Senate roll. 'العضو' cannot reach 'عضو' — the key differs at its "
     "first letter, not its third — and the oath date does not begin with "
     "'التاريخ', so neither the names nor the dates were read"),
    (["المجلس", "الاسم", "تولى المنصب", "ترك المنصب", "الدورات"],
     {1: "name", 2: "start", 3: "end"},
     "ar:قائمة رؤساء مجلس النواب الأردني, which already parsed: pinned so the "
     "keys it leans on are not repurposed"),
    (["الصورة", "الاسم (مواليد–وفاة)", "فترة شغل المنصب", "الحزب", "الحكومة"],
     {1: "name", 2: "period", 3: "party"},
     "the Arabic ministry articles. 'الحكومة' naming which cabinet a row "
     "belongs to must stay inert rather than read as an appointer"),
    # --- decoys the Jordanian keys must not have reopened -----------------
    (["الاسم", "المدة", "التاريخ الهجري", "التاريخ الميلادي"],
     {0: "name", 1: "days", 2: "notes", 3: "period"},
     "a tenure length and a table dated twice over, once per calendar: the AH "
     "column is a decoy and neither may be reachable through a bare 'التاريخ'"),
    (["No.", "Portrait", "Name(Birth–Death)", "Election", "Term of office",
      "Political party", "King(Reign)"],
     {2: "name", 4: "period"},
     "en:List of prime ministers of Jordan. 'Election' and 'King(Reign)' both "
     "carry years and both must stay inert, or they shadow the term"),
]

#: (cell text, expected ISO prefix or None, what it is / what it broke)
DATES = [
    # --- Hijri, and dual-dated cells -------------------------------------
    ("1370 هـ", None, "AH year alone: no Gregorian date to be had"),
    ("28/6/1350هـ", None, "AH day/month/year, numeric"),
    ("20 رمضان 1395 هـ", None, "AH with an AH month name"),
    ("1331هـ/1913م.", "1913", "dual-dated: the AD half wins"),
    ("1 رجب 1441 هـ 25 فبراير 2020 م", "2020-02-25",
     "AH stacked over AD in one cell — returned the bare year 1441→2020 "
     "before `_first_month` kept scanning past the AH month"),
    ("مارس 1963 م", "1963-03", "AD month precision, Arabic"),
    ("5 مارس 2023", "2023-03-05", "AD day precision, Arabic, no era marker"),
    ("2 ديسمبر 1971", "1971-12-02", "the UAE's founding date"),
    ("1761م", "1761", "the era marker glued to the year"),
    # --- the particle and abbreviation traps -----------------------------
    ("2 December 1971", "1971-12-02",
     "`(?:del?\\s*)?` matched the 'De' of December and lost the day"),
    ("17 de jul. de 1834", "1834-07-17", "es abbreviated month, dot after"),
    ("2. července 1992", "1992-07-02", "cs day ordinal, dot after the day"),
    ("5 de julio del 2022", "2022-07-05", "'del' before a four-digit year"),
    ("September 24, 1810", "1810-09-24", "en month-first"),
    ("16 июля 1990", "1990-07-16", "ru genitive month"),
    # --- what must NOT parse ---------------------------------------------
    ("حتى الآن", None, "'to date' is not a date"),
    ("Incumbent", None, "still in office"),
    ("Funkce neobsazena", None, "a gap in the succession"),
    ("1939", "1939", "a day count that is also a plausible year — the reason "
                     "decoy columns get the `days` role rather than a guard here"),
]

#: (cell text, (start, end), what it is)
PERIODS = [
    ("1331هـ/1913م. – 1354هـ/1935م.", ("1913", "1935"), "dual-dated range"),
    ("1370 هـ – 1373 هـ", (None, None), "AH range: nothing to record"),
    ("28/6/1350هـ – 9/3/1353هـ", (None, None), "AH numeric range"),
    ("23 September 1932 – 9 November 1953", ("1932-09-23", "1953-11-09"),
     "an ordinary en reign"),
    ("September 24, 1810 –October 23, 1810", ("1810-09-24", "1810-10-23"),
     "no space on the right of the dash"),
    ("25 January 1972 – 1972", ("1972-01-25", "1972"),
     "coarse end beside a day-precision start — an ordinary cell, not a defect"),
    ("октябрь — декабрь 1995", ("1995-10", "1995-12"),
     "the year stated once, at the end, and meant of both months"),
    ("23 de julio de 1834 (fallecido en el cargo)", ("1834-07-23", None),
     "'died in office' contains the incumbency phrase; the end date survives "
     "as the start of nothing — the term simply ends"),
]


#: (rows as (start, end), expected terms, what it is). `merge_terms` decides how
#: many P39 statements a person gets out of one office's rows, so a mistake here
#: is a spurious statement rather than a wrong date — which makes it exactly as
#: worth pinning, and nothing tested it until nine UAE ministers shipped with half
#: a date each.
MERGES = [
    ((("1971-12-09", None), (None, "1990-11-20")), [("1971-12-09", "1990-11-20")],
     "one section per cabinet, dated only where it changes: a start with no end "
     "and an end with no start are one spell, not two half-dated ones"),
    ((("1997-03-25", None), (None, None), (None, "2009-05-12")),
     [("1997-03-25", "2009-05-12")],
     "…and a middle cabinet that dates nothing at all does not break the pair"),
    ((("1979-04-30", None), ("1979-04-30", "1990-10-07"), (None, "1990-10-07")),
     [("1979-04-30", "1990-10-07")],
     "fragments beside the complete term they belong to are absorbed, not "
     "emitted alongside it"),
    ((("1977-12-20", "1979-07-01"), ("1977-12-20", "1989-10-11")),
     [("1977-12-20", "1979-07-01"), ("1977-12-20", "1989-10-11")],
     "two *complete* terms sharing a start are a source conflict, not a "
     "fragment: both survive so `validate` can refuse the batch and a human "
     "reads the sources"),
    ((("1962-01-17", "1963-01-26"), ("1963-01-26", "1965-11-30")),
     [("1962-01-17", "1965-11-30")],
     "the original case: consecutive rows split by a cabinet change are one term"),
    ((("2016-11-26", "2020-12-05"), ("2023-06-06", "2024-04-04")),
     [("2016-11-26", "2020-12-05"), ("2023-06-06", "2024-04-04")],
     "two genuinely separate spells with a gap stay separate — the Kuwaiti "
     "legislator re-elected after sitting out a term"),
    ((("2014-07-05", None),), [("2014-07-05", None)],
     "a lone open term is an incumbent, and must not be dropped as a fragment"),
]


#: (list HTML, [(name, depth, parent, partner, married_in)], what it broke)
#:
#: `wd.kinship.parse_genealogy` reads descent off indentation, and every one of
#: these was wrong once in a way the gates downstream then had to absorb.
GENEALOGY = [
    ("<div class='mw-parser-output'>"
     "<ul><li><a href='/wiki/Queen_Noor'>Queen Noor</a> (fourth wife)"
     "<ul><li><a href='/wiki/Hamzah'>Hamzah</a> and "
     "<a href='/wiki/Basmah'>Princess Basmah</a> (half-brother)"
     "<ul><li>Princess Haya (half-niece)</li></ul></li></ul></li></ul></div>",
     [("Queen Noor", 1, None, None, False),
      ("Hamzah", 2, "Queen Noor", "Princess Basmah", False),
      ("Princess Basmah", 2, None, "Hamzah", True),
      ("Princess Haya", 3, "Hamzah", None, False)],
     "the whole shape at once: a wife's bullet is her children's parent, a "
     "couple splits, the in-law is *not* a child of the bullet above, and the "
     "grandchild hangs off the blood descendant rather than the spouse"),
    ("<div class='mw-parser-output'>"
     "<ul><li><a href='/wiki/Muhammad_bin_Fahd'>Muhammad bin Fahd</a> "
     "(1950–2025) Former governor of the "
     "<a href='/wiki/Eastern_Province'>Eastern Province</a></li></ul></div>",
     [("Muhammad bin Fahd (1950–2025) Former governor of the Eastern Province",
       1, None, None, False)],
     "two links in one bullet are not a couple. Taking 'more than one link' as "
     "the test entered a province as a person and married it to a prince; the "
     "links must be joined by nothing but the word 'and'"),
]

#: (printed name, expected after the gloss cut, what it is)
GLOSSES = [
    ("Princess Iman (The King's half-sister)", "Princess Iman",
     "the gloss describes the relation to the reigning king, not to the bullet "
     "above, and is never part of the name"),
    ("Princess Muna (King Hussein's second wife", "Princess Muna",
     "the description separator cuts the gloss off mid-way, so an unclosed "
     "bracket has to be cut too or half a sentence reads as ancestry"),
    ("Sa'ad (I)", "Sa'ad (I)",
     "a regnal marker is the opposite of noise — it is what tells two "
     "same-named relatives apart"),
]


def header_roles(cells):
    """The roles `_roles` assigns to a header row written as plain text."""
    row = "".join(f"<th>{cell}</th>" for cell in cells)
    table = lxml_html.fromstring(f"<table><tr>{row}</tr></table>")
    return _roles([(cell, False) for cell in table.xpath("//th")], len(cells))


def main() -> None:
    bad = 0
    for cells, want, why in HEADERS:
        got = header_roles(cells)
        wrong = {i: (role, got[i]) for i, role in want.items() if got[i] != role}
        if wrong:
            bad += 1
            detail = ", ".join(
                f"{cells[i]!r} want {role!r}, got {actual!r}"
                for i, (role, actual) in sorted(wrong.items())
            )
            print(f"FAIL _roles({cells!r})\n  {detail}\n  ({why})")
    for html, want, why in GENEALOGY:
        got = [(e.name, e.depth, e.parent, e.partner, e.married_in)
               for e in parse_genealogy(html, glosses=True)]
        if got != want:
            bad += 1
            print(f"FAIL parse_genealogy(...)\n  want {want!r}\n  got  {got!r}"
                  f"\n  ({why})")
    for printed, want, why in GLOSSES:
        got = _cut_gloss(printed)
        if got != want:
            bad += 1
            print(f"FAIL _cut_gloss({printed!r})\n  want {want!r}, got {got!r}"
                  f"\n  ({why})")
    for rows, want, why in MERGES:
        got = merge_terms([
            RosterRow(ordinal=i, section=None, name="x", link=None, start=s, end=e)
            for i, (s, e) in enumerate(rows)
        ])
        if got != want:
            bad += 1
            print(f"FAIL merge_terms({list(rows)!r})\n  want {want!r}, "
                  f"got {got!r}\n  ({why})")
    for text, want, why in DATES:
        got = parse_date(text)
        if got != want:
            bad += 1
            print(f"FAIL parse_date({text!r})\n  want {want!r}, got {got!r}\n  ({why})")
    for text, want, why in PERIODS:
        start, end, _incumbent = parse_period(text)
        if (start, end) != want:
            bad += 1
            print(f"FAIL parse_period({text!r})\n  want {want!r}, "
                  f"got {(start, end)!r}\n  ({why})")
    total = (len(DATES) + len(PERIODS) + len(MERGES) + len(HEADERS)
             + len(GENEALOGY) + len(GLOSSES))
    if bad:
        raise SystemExit(f"\n{bad} of {total} cases failed")
    print(f"{total} header, date, term-merge and genealogy cases pass")


if __name__ == "__main__":
    main()
