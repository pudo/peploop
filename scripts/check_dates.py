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

from wd.infobox import birth_year_category
from wd.kinship import _cut_gloss, parse_genealogy
from wd.officebox import parse_officebox
from wd.create import duplicate_of
from wd.positions import Candidate, Lookup
from wd.validate import conflicting_tenures
from wd.roster import (
    RosterRow,
    _roles,
    merge_terms,
    parse_bullet_rosters,
    parse_date,
    parse_period,
)

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
    # --- Qatar -----------------------------------------------------------
    (["التسلسل", "الأمير", "صورة", "العلاقة مع سلفه", "بداية الفترة",
      "نهاية الفترة", "طول الفترة", "مُلاحظات"],
     {4: "start", 5: "end", 6: "days"},
     "ar:قائمة أمراء قطر. 'طول الفترة' is the duration decoy a third time, in "
     "a third spelling; the bare 'فترة' key cannot reach it because it differs "
     "at the first letter. The page dated correctly without it only because "
     "both real columns happened to be recognised"),
    (["No.", "Portrait", "Name(Birth–Death)", "Took office", "Left office",
      "Time in office", "Cabinet", "Ref."],
     {2: "name", 3: "start", 4: "end", 5: "days"},
     "en:Prime Minister of Qatar — the same decoy in English, and the wide "
     "'Term of office' header subdivided by a second header row"),
    (["Constituency", "Elected member"],
     {0: "notes", 1: "name"},
     "en:2021 Qatari general election. 'Constituency' already had `notes`, so "
     "unnamed the members landed there too: the table parsed with no name "
     "column and its wikilinks were never collected"),
    (["الأعضاء"],
     {0: "name"},
     "both Shura Council rolls on ar:قائمة أعضاء مجلس الشوري القطري (2021). "
     "The plural inserts an alif-hamza after the article, so neither 'العضو' "
     "nor 'عضو' reaches it"),
    (["الاسم", "صورة", "مدة عضوية", "حزب سياسي", "رئيس الوزراء"],
     {2: "period", 4: "appointer"},
     "every ar:وزارة <portfolio> (العراق) article. 'مدة عضوية' colspans the "
     "start and end cells, and it reaches the bare 'مدة' days-decoy by prefix "
     "— so as a decoy it threw both dates away: 38 defence ministers parsed "
     "with no dates and no error"),
    (["الاسم", "صورة", "مدة العضوية", "حزب سياسي", "رئيس الوزراء"],
     {2: "period"},
     "the same header with the definite article, which three of the defence "
     "ministry's four era tables use"),
    (["#", "المحافظ أو المتصرف", "تاريخ المباشرة", "وصف", "صورة"],
     {1: "name", 2: "start", 3: "notes"},
     "ar:قائمة محافظي نينوى. Unrecognised, its 88 governors had neither a name "
     "column nor a date"),
    (["المحافظة", "مولده", "تاريخ تعيينهم", "انتهاؤه"],
     {0: "name", 1: "notes", 2: "start", 3: "end"},
     "ar:محافظة صلاح الدين. 'المحافظة' reads as 'the governorate' and holds the "
     "*holder*, so it must resolve to `name` — which it does by prefix from the "
     "'المحافظ' key, and naming it `notes` to be safe cost all 21 rows their "
     "name column. None of the other three is reachable from an existing key: "
     "'تاريخ التعيين', 'انتهت' and the lifespan keys each differ inside the word"),
    (["المنصب", "الاسم", "استلام المنصب", "مغادرة المنصب"],
     {2: "start", 3: "end"},
     "ar:رؤساء مجلس النواب العراقي. 'غادر' does not reach 'مغادرة' — the Jordan "
     "end-key bug in a new spelling — so 43 speakers and Senate presidents "
     "parsed a start with no end, which reads as still in office"),
    (["الوزارات والدوائر", "وزير"],
     {0: "office", 1: "name"},
     "ar:حكومة إقليم كردستان heads its two columns in a `td` row. Only 'وزير' "
     "was recognised, one of the two `_reads_as_header` needs, so all 32 rows "
     "were dropped"),
]

#: (header cells, per-source overrides, {index: role}, what it is)
#:
#: The one case the ordered table cannot express: a header string that means two
#: different things on two pages. A page declares its own reading through
#: `RosterSource.column_roles`, and the override has to win.
HEADER_OVERRIDES = [
    (["ترتيب", "الاسم", "الصورة", "الرتبة", "المدة", "ملاحظات"],
     (("المدة", "period"),),
     {1: "name", 4: "period"},
     "ar:رؤساء أركان الجيش العراقي, where 'المدة' is the only date column there "
     "is. Globally it is a `days` decoy, because on the Kuwaiti and Saudi lists "
     "it is a tenure length and reading it as the term cost every date on the "
     "page — so the fix belongs on the page, not in the table"),
    (["ترتيب", "الاسم", "الصورة", "الرتبة", "المدة", "ملاحظات"],
     (),
     {4: "days"},
     "…and with no override the global decoy reading still stands, which is "
     "what protects Kuwait and Saudi Arabia"),
]

#: (cell text, expected ISO prefix or None, what it is / what it broke)
DATES = [
    # --- Solar Hijri (Jalali), fa.wikipedia ------------------------------
    # The opposite ruling from the lunar Hijri block below, and the difference
    # is load-bearing. A lunar AH year falls outside the Gregorian range the
    # bare-year rule accepts, and a lunar day conversion is ambiguous, so that
    # calendar is left unconverted. Solar Hijri is a *solar* calendar: the
    # conversion is exact, its years land squarely inside the Gregorian range,
    # and fa.wikipedia dates every roster this way — so declining to convert
    # would mean no Iranian lane yields a single date.
    ("۱۳ مرداد ۱۳۹۲", "2013-08-04", "day precision — Rouhani's first inauguration"),
    ("13 مرداد 1392", "2013-08-04", "the same cell in ASCII digits"),
    ("١۵ مرداد ١۴٠٢", "2023-08-06",
     "Arabic-Indic and Persian-Indic digits MIXED inside one number, live on "
     "fa:دادستان کل کشور beside the all-Persian spelling of the same date. A "
     "two-step digit conversion has an order to get wrong; one table does not"),
    ("۲۲ بهمن ۱۳۵۷", "1979-02-11", "the revolution's victory day"),
    ("۸ مهر۱۳۵۸", "1979-09-30",
     "the commonest fa shape: no space between month and year"),
    ("۴ آذر ۱۳۰۴ه‍. ش", "1925-11-25", "an explicit solar marker, built with ZWJ"),
    ("۱۴۰۰/۸/۱۲", "2021-11-03", "slash form, year first"),
    # Dey is the one month that begins in one Gregorian year and ends in the
    # next, so it survives at day precision and cannot survive at month.
    ("۱۹ دی ۱۳۶۱", "1983-01-09", "Dey at DAY precision converts exactly"),
    ("دی ۱۳۶۱", None, "Dey at MONTH precision spans two Gregorian years"),
    ("مرداد ۱۳۹۲", "2013", "month 1–9 reduces to the Gregorian year, +621"),
    ("بهمن ۱۳۹۲", "2014", "month 11–12 reduces to the Gregorian year, +622"),
    ("۱۳۹۲", None,
     "a bare Solar Hijri year straddles two Gregorian years — 286 days of "
     "2013 and 79 of 2014 — so no year-precision rendering of it is correct"),
    ("۵۷/۱۲/۱۵", "1979-03-06",
     "a two-digit Solar Hijri year, year-first — the whole Markazi governors "
     "page. Read as 13xx: the abbreviation belongs to a century that ended at "
     "SH 1399, so 1400+ is unreachable this way. It cannot collide with the "
     "ASCII `d/m/YYYY` branch, which requires its four-digit year last"),
    ("۱۳۵۹–۶۰", None,
     "an abbreviated end year outside the slash shape is still refused — "
     "nothing there says which century it means"),
    # Solar and lunar years OVERLAP, which is why the calendar is read from the
    # marker and never inferred from the range. Astan Quds carries these.
    ("۹۰۶ه‍.ق", None, "a lunar year, marked"),
    ("۱۳۴۴ه‍. ق", None,
     "a LUNAR year sitting inside the solar range in use — the case a "
     "range-based guard would convert and be wrong by six centuries"),
    # The two branches that took a year from a shape rather than from a range.
    ("1392-05-13", None,
     "an ISO-shaped Solar Hijri cell. Before the guard this returned "
     "'1392-05-13' verbatim — a 4th-century P39 start date"),
    ("13/05/1392", None, "the same defect on the d/m/Y branch"),
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
    # --- the source declining to state a date ----------------------------
    ("? - 1983", None,
     "en:Qatar Central Bank dates its first governor '? - 1983' in the *took "
     "office* column and 'January 1990' in *left office*. The 1983 belongs to "
     "the other bound; read as a start it invents a fact the article refuses "
     "to state"),
    ("1983 ?", None, "the same doubt written after the year"),
    ("1983", "1983", "…and the bare year beside it still parses"),
    ("¿1983?", "1983",
     "an inverted question mark is Spanish punctuation, not a doubt marker: "
     "only a free-standing '?' suppresses the date"),
    # --- the Levantine month names ---------------------------------------
    # Iraqi pages date almost everything this way. Two of the twelve are *two
    # words*, which the single-token month group cannot capture at all, so these
    # are rewritten to the Gulf name before it runs. Untreated, every one of
    # them fell through to the bare-year rule and landed on the item as a year
    # beside its day-precision neighbours — which is the shape §7 calls a cell
    # that failed to parse, not a coarse source.
    ("12 حزيران 1948", "1948-06-12", "the Iraqi central bank's first governor"),
    ("14 شباط 1949", "1949-02-14", "February"),
    ("23 آذار 1949", "1949-03-23", "March, with the madda alef"),
    ("21 نيسان 1924", "1924-04-21", "April"),
    ("29 أيار 1928", "1928-05-29", "May, with the hamza alef"),
    ("24 تموز 1921", "1921-07-24", "July"),
    ("23 آب 1921", "1921-08-23", "August — matched only in the madda spelling"),
    ("1 أيلول 1936", "1936-09-01", "September"),
    ("11 تشرين الثاني 1920", "1920-11-11",
     "two words: Iraq's first prime minister took office on this date"),
    ("18 تشرين الأول 1930", "1930-10-18", "two words, October"),
    ("6 كانون الثاني 1921", "1921-01-06", "two words, January"),
    ("23 كانون الأول 1929", "1929-12-23", "two words, December"),
    ("1 الاول تشرين 1930", "1930", "the two words the wrong way round are not "
                                   "a month name and must not become one"),
    # --- dual-named cells, and what must not be rewritten ----------------
    ("14 تموز يوليو 1958", "1958-07-14",
     "both naming systems in one cell. The rewrite names July twice, which "
     "leaves the year no longer adjacent to the month and costs the day, so the "
     "repeat has to collapse"),
    ("6 كانون الثاني/يناير 1921", "1921-01-06", "the same, slash-separated"),
    ("23 كانون الأول/ديسمبر 1929", "1929-12-23", "the same, two-word month"),
    ("7 حزيران/ يونيو 2020", "2020-06-07", "the same, space after the slash"),
    ("2 أبريل/نيسان 1980", "1980-04-02",
     "Gulf name first, and spelled with the hamza the rewrite's output lacks — "
     "which is why the repeat is collapsed per month rather than by "
     "backreference"),
    ("توفي والده اب عن العائلة سنة 1948", "1948",
     "'اب' is the word for father, and the bare-alef spelling of August. Only "
     "the madda form is a month, or this fires on prose"),
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
    # --- an Arabic table writes the range in words, not with a dash -------
    ("12 حزيران 1948 إلى 14 شباط 1949", ("1948-06-12", "1949-02-14"),
     "ar:البنك المركزي العراقي states all 25 governors' terms this way. The "
     "dash split cannot see a word, so every one parsed with a start and no "
     "end — which reads as a sitting governor, not as a lost bound"),
    ("من: 6 كانون الثاني/يناير 1921 حتى: 3 تشرين الثاني/نوفمبر 1923",
     ("1921-01-06", "1923-11-03"),
     "ar:رؤساء أركان الجيش العراقي, with the opener and the separator both "
     "colon-suffixed, and both months dual-named"),
    ("14 شباط 1949 الى 23 آذار 1949", ("1949-02-14", "1949-03-23"),
     "'الى' without the hamza, which is how the same page spells it elsewhere"),
    ("9 أيلول 2014-الى 14 أيلول 2020", ("2014-09-09", "2020-09-14"),
     "the same cell writing the dash *and* the word — the Iraqi central bank's "
     "sitting governor, whose first term ran to 2020. Left as it was, the "
     "substitution put a second dash beside the glued one, the split read the "
     "pair as one separator and the end was lost"),
    ("من تاريخ 2017/1/2 لغاية تاريخ 2017/4/9", ("2017", "2017"),
     "'لغاية' is a third spelling of the separator. The numeric dates here are "
     "y/m/d, which the d/m/y rule cannot read, so both fall to the bare year — "
     "and that is honest for a cell this workbench does not need"),
]

#: (cell text, still in office, what it is)
#:
#: Split out from `PERIODS` because the incumbency flag is decided *before* the
#: range is split, and that ordering is the whole point: "حتى الآن" — "until
#: now" — is both the separator word and the incumbency marker. Cutting the
#: range first turns a sitting minister into an unbounded one, and this was the
#: only row in 48 prior roster sources that the Arabic separator change touched
#: until the order was fixed.
INCUMBENCY = [
    ("2022 حتى الآن", True, "ar:وزارة الصحة (الكويت)'s sitting minister"),
    ("من: 7 حزيران/ يونيو 2020 حتى الآن", True,
     "the Iraqi chief of staff, whose cell carries the opener, a dual-named "
     "Levantine month and the incumbency phrase at once"),
    ("12 حزيران 1948 إلى 14 شباط 1949", False,
     "a closed term is not incumbent merely for carrying a separator word"),
    ("23 de julio de 1834 (fallecido en el cargo)", False,
     "died in office is not still in office"),
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
    ("<div class='mw-parser-output'><div class='treelist'>"
     "<ul><li><a href='/wiki/Jassim'>Jassim bin Mohammed</a>"
     "<ul><li><a href='/wiki/Mohammed_bin_Jassim'>Mohammed bin Jassim</a>"
     "<ul><li>Sheikh ??? bin Mohammed Al Thani</li>"
     "<li><a href='/wiki/Fahad'>Fahad bin Jassim</a></li></ul>"
     "</li></ul></li></ul></div></div>",
     [("Jassim bin Mohammed", 1, None, None, False),
      ("Mohammed bin Jassim", 2, "Jassim bin Mohammed", None, False),
      ("Fahad bin Jassim", 3, "Mohammed bin Jassim", None, False)],
     "`{{Tree list}}` wraps its list in a `div.treelist` to draw the connecting "
     "rules, so the whole genealogy sat one level below where the walker looked "
     "— `en:House of Thani` read as 15 depth-1 entries from an unrelated list. "
     "The '???' bullet is dropped: it asserts a son exists without naming him, "
     "and left in it reads as a redlink to mint an item for"),
    ("<div class='mw-parser-output'>"
     "<div class='navbox'><div class='treelist'><ul>"
     "<li><a href='/wiki/Jordan'>Jordan (1921–present)</a></li></ul></div></div>"
     "</div>",
     [],
     "…and only at the top level. `en:Hashemites` renders a treelist inside a "
     "navbox whose items are *territories*; a `.//div` search would emit "
     "'Jordan (1921–present)' as a Hashemite"),
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

#: (wikitext, lang, [(office, start, end)], what it is / what it broke)
#:
#: `wd.officebox` reads the person's own infobox, which is the only channel a
#: country publishing no rosters has. Its failure mode is quiet: a mispaired
#: group dates the wrong office, and nothing downstream can tell.
OFFICEBOXES = [
    ("{{Infobox officeholder\n"
     "| office = [[Ministry of Commerce and Industry (Qatar)|"
     "Minister of Commerce and Industry]]\n"
     "| term_start = 12 November 2024\n"
     "| monarch = [[Tamim bin Hamad Al Thani]]\n}}",
     "en", [("Minister of Commerce and Industry", "2024-11-12", None)],
     "the piped link prints the office and targets the *ministry*; splitting "
     "on every pipe would name the office 'Ministry of Commerce and Industry "
     "(Qatar)' — the organisation, not the position"),
    ("{{Infobox officeholder\n"
     "| office = [[List of ambassadors of Qatar to the United States|"
     "Ambassador of Qatar to the United States]]\n"
     "| term_start = December 2016\n"
     "| term_end = | birth_date = \n}}",
     "en", [("Ambassador of Qatar to the United States", "2016-12", None)],
     "real markup on Q107379868: an empty `term_end` runs straight into the "
     "next parameter, and a line-based reader took 'birth_date' as the end"),
    ("{{Infobox officeholder\n"
     "| office = [[Attorney General]]\n| term_start = 17 June 2021\n"
     "| office1 = [[Ministry of Justice (Qatar)|Minister of Justice]]\n"
     "| term_start1 = 2018\n| term_end1 = 17 June 2021\n}}",
     "en", [("Attorney General", "2021-06-17", None),
            ("Minister of Justice", "2018", "2021-06-17")],
     "numbered groups: `office1` pairs with `term_start1`, never with the "
     "unsuffixed `term_start` above it"),
    ("{{معلومات صاحب منصب\n"
     "|المنصب = سفير قطر لدى بلجيكا\n|بداية الفترة = 13 يناير 2017\n"
     "|نهاية الفترة = \n"
     "|المنصب1= سفير قطر لدى ألمانيا\n|بداية الفترة1= 2009\n"
     "|نهاية الفترة1= 2016\n}}",
     "ar", [("سفير قطر لدى بلجيكا", "2017-01-13", None),
            ("سفير قطر لدى ألمانيا", "2009", "2016")],
     "the Arabic vocabulary, which is where this channel actually lives: 141 "
     "of Qatar's 227 dated tenures are ar.wikipedia's. The bare stems 'منصب' "
     "and 'بداية' look like these fields and match a sixth as many articles"),
    ("{{Infobox officeholder\n| office = {{#property:P39}}\n"
     "| term_start = 2019\n}}",
     "en", [],
     "an infobox filled from Wikidata restates what Wikidata already holds; "
     "read back it would manufacture agreement between a claim and itself"),
    ("{{Infobox person\n| title = Poet laureate\n| term_start = 1990\n}}",
     "en", [],
     "a person box has no office grammar — reading its `title` as an office "
     "turns a job description into a position claim"),
]


#: (list HTML, bullet_offices, [(name, office, start)], what it is)
#:
#: The bucket-over-bullets shape and the two rosters it broke on the way in. Both
#: negatives are the *default* path, which is what protects every campaign that
#: does not ask for this.
BULLETS = [
    ("<h2>التشكيلة الوزارية</h2><ul>"
     "<li>وزير المالية: <a href='/wiki/رستم حيدر' title='رستم حيدر'>رستم حيدر</a></li>"
     "<li>وزير الخارجية: <a href='/wiki/نوري السعيد' title='نوري السعيد'>نوري السعيد</a></li>"
     "</ul>",
     True,
     [("رستم حيدر", "وزير المالية", None), ("نوري السعيد", "وزير الخارجية", None)],
     "68 of Iraq's 74 bullet cabinets. The office ahead of the colon is the "
     "routing key and the licence to carry no date — the article dates the "
     "government, never the row. Without the Arabic headings the list is skipped "
     "outright; without the office cell all 821 rows share one haystack"),
    ("<h2>التشكيلة الوزارية</h2><ol>"
     "<li>رئيس مجلس الوزراء: <a href='/wiki/ناجي شوكت' title='ناجي شوكت'>ناجي شوكت</a></li>"
     "<li>وزير المالية: <a href='/wiki/نصرت الفارسي' title='نصرت الفارسي'>نصرت الفارسي</a></li>"
     "</ol>",
     True,
     [("ناجي شوكت", "رئيس مجلس الوزراء", None),
      ("نصرت الفارسي", "وزير المالية", None)],
     "ar:وزارة ناجي شوكت numbers its ministers with `#`, so the walk has to "
     "descend into `ol` as well as `ul`"),
    ("<h2>Руководство</h2><ul>"
     "<li>Первый заместитель министра: должность вакантна</li>"
     "<li>Заместители министра: <a href='/wiki/Иванов Иван' title='Иванов Иван'>Иванов Иван</a></li>"
     "</ul>",
     False,
     [],
     "three Belarusian ministry articles list current leadership this way. The "
     "deputy marker sits in the *office* half, so stripping it off the name is "
     "precisely what would hide it from DEPUTY_ROW — nine spurious rows entered "
     "a shipped campaign this way before the flag was made opt-in"),
    ("<h2>List of ministers</h2><ul>"
     "<li>1989–1990: <a href='/wiki/A B' title='A B'>A B</a></li>"
     "<li>1990–1992: <a href='/wiki/C D' title='C D'>C D</a></li>"
     "</ul>",
     True,
     [("A B", None, "1989"), ("C D", None, "1990")],
     "en:Ministry of Foreign Affairs (Qatar) puts the *dates* before the colon. "
     "A date is not an office, and captured as one it feeds the routing haystack "
     "a date range"),
]


#: (lines as (subject, [(prop, iso)]), flagged, what it is)
#:
#: `conflicting_tenures` is a veto — it refuses to render a batch — so both what
#: it catches and what it lets past are worth pinning. It caught the UAE's twelve
#: real cases and, until narrowed, also refused two Iraqi governors whose page
#: says in words that they were appointed twice.
TENURES = [
    ([("Q1", [("P580", "1993-09-17")]), ("Q1", [("P580", "2001-05-08")])], False,
     "ar:قائمة محافظي نينوى on Abdul-Wahid Shannan — 'عُيّن محافظاً مرتين', "
     "appointed governor twice, and the page gives no end for either. Two bare "
     "starts have nothing to pair, so this is a faithful record and not one "
     "tenure dated twice"),
    ([("Q2", [("P582", "1993-09-17")]), ("Q2", [("P582", "2001-05-08")])], False,
     "the same shape from the other side"),
    ([("Q9", [("P580", "2021-08-26"), ("P582", "2021-11-28")]),
      ("Q9", [("P580", "2024-08-21")])], False,
     "Alireza Kazemi: caretaker Minister of Education for three months in 2021, "
     "and the office again from 2024 — the roster's second row ends `متصدی`, "
     "incumbent. The later line's start is after the earlier line's end, so "
     "there is nothing to pair and these are two tenures. Until this was "
     "narrowed it refused the whole Iran batch"),
    ([("Q10", [("P580", "2021-08-26"), ("P582", "2024-11-28")]),
      ("Q10", [("P580", "2024-08-21")])], True,
     "the same shape but OVERLAPPING — the open line begins before the dated "
     "one ends, so it may well be that spell told twice. Still a defect"),
    ([("Q3", [("P580", "1977-12-20")]), ("Q3", [("P582", "1989-10-11")])], True,
     "Hamdan bin Zayed in the UAE batch: a lone start beside a lone end is one "
     "spell told in two halves, and QuickStatements piled the ends onto one "
     "statement. Still a defect"),
    ([("Q4", [("P580", "1977-12-20"), ("P582", "1979-07-01")]),
      ("Q4", [("P580", "1977-12-20"), ("P582", "1989-10-11")])], True,
     "Hamdan bin Mohammed Al Nahyan: two rosters dating one tenure, sharing a "
     "start and disagreeing by ten years"),
    ([("Q5", [("P580", "2014-09-09")]),
      ("Q5", [("P580", "2023-01-23"), ("P582", "2026-06-18")])], True,
     "a half-dated line beside a complete one — the Iraqi central bank governor "
     "before the dash-glued separator was fixed. Something could complete it, so "
     "it stays a defect"),
    ([("Q11", [("P580", "1990-10-28")]),
      ("Q11", [("P580", "2013-11-20"), ("P582", "2017-10-11")])], True,
     "Ghorbanali Saadat, governor of West Azarbaijan — tuple for tuple the Q5 "
     "shape above, and the opposite truth. Without the source signal the "
     "validator cannot tell them apart, so it vetoes, which is correct"),
    ([("Q12", [("P580", "1990-10-28")]),
      ("Q12", [("P580", "2013-11-20"), ("P582", "2017-10-11")])], False,
     "the same lines once the parser says the roster offered an end column for "
     "the 1990 row and left it blank: a spell whose end is unknown, not a "
     "fragment of the 2013 one",
     {("Q12", "P39", "Q_office", "+1990-10-28T00:00:00Z/11")}),
    ([("Q6", [("P580", "1990-01-01"), ("P582", "1992-01-01")]),
      ("Q6", [("P580", "2000-01-01"), ("P582", "2002-01-01")])], False,
     "two fully dated spells a decade apart — the ordinary multi-tenure case the "
     "claims file exists for"),
]


#: `parse_bullet_rosters`'s `headings` override. The allowlist recognises a
#: section by the word in its heading; a roll sectioned alphabetically has
#: letters, and hid every member of the first eight Majlis terms.
_ALPHA_ROLL = (
    "<h2>\u0622\u060c \u0627\u060c \u0628</h2><ul>"
    "<li><a href='/wiki/a' title='\u0645\u0647\u062f\u06cc \u0628\u0627\u0632\u0631\u06af\u0627\u0646'>"
    "\u0645\u0647\u062f\u06cc \u0628\u0627\u0632\u0631\u06af\u0627\u0646</a></li>"
    "<li><a href='/wiki/b' title='\u062d\u0633\u0646 \u062d\u0628\u06cc\u0628\u06cc'>"
    "\u062d\u0633\u0646 \u062d\u0628\u06cc\u0628\u06cc</a></li></ul>"
)
_REFS = (
    "<h2>\u0645\u0631\u0627\u062c\u0639</h2><ul>"
    "<li><a href='/wiki/a' title='\u0645\u0647\u062f\u06cc \u0628\u0627\u0632\u0631\u06af\u0627\u0646'>"
    "\u0645\u0647\u062f\u06cc \u0628\u0627\u0632\u0631\u06af\u0627\u0646</a></li>"
    "<li><a href='/wiki/b' title='\u062d\u0633\u0646 \u062d\u0628\u06cc\u0628\u06cc'>"
    "\u062d\u0633\u0646 \u062d\u0628\u06cc\u0628\u06cc</a></li></ul>"
)
BULLET_OVERRIDES = [
    (_ALPHA_ROLL, None, 0,
     "a letter heading matches no keyword, so the default allowlist drops it"),
    (_ALPHA_ROLL, r".", 2,
     "the caller has read the page and says every list on it is a roster"),
    (_REFS, r".", 0,
     "an override says the page is a roster, not that its references are — "
     "BULLET_NOT_HEADINGS still applies"),
]


def _cand(qid, label_match=True, country_match=True, is_list=False,
          countries=("Q794",), types=("Q4164871",)):
    return Candidate(
        qid=qid, label="", description=None, types=list(types),
        country_qids=list(countries), label_match=label_match,
        country_match=country_match, is_list=is_list,
    )


#: The creation duplicate guard. Every one of these is a case `_existing`'s old
#: `status == "matched"` test got wrong or right for the wrong reason: the
#: status only says whether the *search* was decisive, and creation needs to
#: know whether an item that would be duplicated is sitting in the candidates.
GUARDS = [
    (Lookup(status="matched", resolved_qid="Q1", candidates=[_cand("Q1")]),
     "Q1", "one strong candidate — the case the status test already caught"),
    (Lookup(status="ambiguous", candidates=[_cand("Q1"), _cand("Q2")]),
     "Q1", "two items match label and country; the status test minted a third"),
    (Lookup(status="label-only", resolved_qid="Q1",
            candidates=[_cand("Q1", country_match=False, countries=())]),
     "Q1", "unique label match on an item asserting no country at all"),
    (Lookup(status="ambiguous",
            candidates=[_cand("Q1", country_match=False, countries=("Q843",))]),
     None, "same label, a different country — a different office, not a duplicate"),
    (Lookup(status="ambiguous", candidates=[_cand("Q1", is_list=True,
                                                  types=["Q13406463"])]),
     None, "a pure list article is not a position item"),
    (Lookup(status="label-only", resolved_qid="Q1",
            candidates=[_cand("Q1", country_match=False, countries=(),
                              types=["Q5"])]),
     None, "Q64759749: a human carrying the office as an alias. No P17, so "
           "they arrive through the same branch `label-only` needs"),
    (Lookup(status="ambiguous",
            candidates=[_cand("Q1", country_match=False, countries=(),
                              types=["Q17633526"])]),
     None, "Q19793882: a Wikinews headline beginning with the office's name"),
    (Lookup(status="ambiguous",
            candidates=[_cand("Q1", is_list=True,
                              types=["Q13406463", "Q4164871"])]),
     "Q1", "typed as both a list and a position — block, because a false "
           "duplicate costs a check and a missed one mints an item"),
    (Lookup(status="ambiguous",
            candidates=[_cand("Q1", label_match=False), _cand("Q2", label_match=False)]),
     None, "label-mismatched noise is why `ambiguous` cannot be trusted wholesale"),
    (Lookup(status="unmatched"), None, "no candidates"),
    (Lookup(status="ambiguous",
            candidates=[_cand("Q1", is_list=True, types=["Q13406463"]),
                        _cand("Q2")]),
     "Q2", "the list article is skipped, the real item behind it is not"),
]


def header_roles(cells, overrides=()):
    """The roles `_roles` assigns to a header row written as plain text."""
    row = "".join(f"<th>{cell}</th>" for cell in cells)
    table = lxml_html.fromstring(f"<table><tr>{row}</tr></table>")
    return _roles(
        [(cell, False) for cell in table.xpath("//th")], len(cells), overrides
    )


#: (category name, year or None, what it is)
#:
#: The birth-year category is the *second* channel behind every P569 this
#: workbench proposes, and it was English-only — silently, because a wiki with
#: no matching category yields `no-cross-check` forever rather than an error.
#: Five of these were wrong on the first pass and only real articles said so:
#: Hungarian has vowel harmony, Latvian puts the year first, Czech and French
#: spell more than the year, and Lithuanian could not be verified at all.
BIRTH_CATEGORIES_CASES = [
    ("1962 births", "1962", "en, the only one that used to work"),
    ("Urodzeni w 1985", "1985", "pl"),
    ("Geboren 1958", "1958", "de"),
    ("Родившиеся в 1952 году", "1952", "ru"),
    ("Народились 1978", "1978", "uk"),
    ("Nacidos en 1972", "1972", "es"),
    ("Naissance en décembre 1977", "1977",
     "fr writes the month in as well, so the year is not the whole tail"),
    ("Narození v roce 1964", "1964", "cs — not the bare 'Narození 1964' guessed first"),
    ("Nati nel 1977", "1977", "it"),
    ("1963-ban született személyek", "1963",
     "hu vowel harmony: '-ban' here, '-ben' after a front-vowel year"),
    ("1973. gadā dzimušie", "1973", "lv puts the year first, not last"),
    ("مواليد 1985", "1985", "ar"),
    ("Narození 1. září", None,
     "a day-and-month category carries no year and must not be read as one"),
    ("1985 deaths", None, "the death category is the near-miss that matters most"),
    ("Ludzie urodzeni w Bolesławcu", None,
     "born-in-a-place reads like born-in-a-year in Polish, and is not"),
    ("Year of birth missing", None, "the doubt sibling carries no year"),
]


def main() -> None:
    bad = 0
    for name, want, why in BIRTH_CATEGORIES_CASES:
        got = birth_year_category(name)
        if got != want:
            bad += 1
            print(f"FAIL birth_year_category({name!r})\n  want {want!r}, "
                  f"got {got!r}\n  ({why})")
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
    for cells, overrides, want, why in HEADER_OVERRIDES:
        got = header_roles(cells, overrides)
        wrong = {i: (role, got[i]) for i, role in want.items() if got[i] != role}
        if wrong:
            bad += 1
            detail = ", ".join(
                f"{cells[i]!r} want {role!r}, got {actual!r}"
                for i, (role, actual) in sorted(wrong.items())
            )
            print(f"FAIL _roles({cells!r}, overrides={overrides!r})\n  {detail}"
                  f"\n  ({why})")
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
    for text, want, why in INCUMBENCY:
        _start, _end, incumbent = parse_period(text)
        if incumbent != want:
            bad += 1
            print(f"FAIL parse_period({text!r}) incumbent\n  want {want!r}, "
                  f"got {incumbent!r}\n  ({why})")
    for html, bullet_offices, want, why in BULLETS:
        got = [
            (row.name, row.cells.get("office"), row.start)
            for roster in parse_bullet_rosters(html, bullet_offices)
            for row in roster.rows
        ]
        if got != want:
            bad += 1
            print(f"FAIL parse_bullet_rosters(..., {bullet_offices!r})\n  "
                  f"want {want!r}\n  got  {got!r}\n  ({why})")
    for html, override, want, why in BULLET_OVERRIDES:
        got = sum(
            len(roster.rows)
            for roster in parse_bullet_rosters(html, dateless=True, headings=override)
        )
        if got != want:
            bad += 1
            print(f"FAIL parse_bullet_rosters(..., headings={override!r})\n  "
                  f"want {want} rows, got {got}\n  ({why})")
    for case in TENURES:
        lines, want, why = case[:3]
        withheld = case[3] if len(case) > 3 else frozenset()
        rendered = [
            "\t".join(["Q_subject", "P39", "Q_office"]
                       + [x for prop, iso in quals
                          for x in (prop, f"+{iso}T00:00:00Z/11")])
            .replace("Q_subject", subject)
            for subject, quals in lines
        ]
        got = bool(conflicting_tenures(rendered, withheld))
        if got != want:
            bad += 1
            print(f"FAIL conflicting_tenures({lines!r})\n  want flagged="
                  f"{want!r}, got {got!r}\n  ({why})")
    for found, want, why in GUARDS:
        got = duplicate_of(found)
        if got != want:
            bad += 1
            print(f"FAIL duplicate_of({found.status!r}, "
                  f"{len(found.candidates)} candidates)\n  want {want!r}, "
                  f"got {got!r}\n  ({why})")
    for wikitext, lang, want, why in OFFICEBOXES:
        got = [(t.office, t.start, t.end) for t in parse_officebox(wikitext, lang)]
        if got != want:
            bad += 1
            print(f"FAIL parse_officebox(..., {lang!r})\n  want {want!r}\n  "
                  f"got  {got!r}\n  ({why})")
    total = (len(BIRTH_CATEGORIES_CASES)
             + len(DATES) + len(PERIODS) + len(INCUMBENCY) + len(MERGES) + len(BULLETS) + len(TENURES)
             + len(HEADERS) + len(HEADER_OVERRIDES) + len(GENEALOGY)
             + len(GLOSSES) + len(OFFICEBOXES) + len(GUARDS)
             + len(BULLET_OVERRIDES))
    if bad:
        raise SystemExit(f"\n{bad} of {total} cases failed")
    print(f"{total} header, date, term-merge, genealogy, infobox and creation-guard cases pass")


if __name__ == "__main__":
    main()
