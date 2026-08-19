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
    # Spanish abbreviated, which is how es.wikipedia's date templates render a
    # sortable cell: "17 de jul. de 1834".
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7,
    "ago": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dic": 12,
    # English, for the en.wikipedia list articles a country's own wiki lacks.
    "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12, "jan": 1, "apr": 4, "aug": 8, "dec": 12,
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
    # Russian nominative. A date cell always uses the genitive ("16 июля"),
    # but a *month range* with no day does not: "октябрь — декабрь 1995".
    "январь": 1, "февраль": 2, "март": 3, "апрель": 4, "май": 5, "июнь": 6,
    "июль": 7, "август": 8, "сентябрь": 9, "октябрь": 10, "ноябрь": 11,
    "декабрь": 12,
    # Arabic, in the Gulf/Egyptian naming system, which is what ar.wikipedia
    # uses for the Emirates: "2 ديسمبر 1971". Keys are already hamza-folded
    # (أبريل → ابريل) because `parse_date` looks the deaccented word up first.
    # The Levantine names are absent *here* for two reasons that still hold:
    # the four that matter most ("كانون الثاني", "تشرين الأول") are *two words*,
    # which the single-token month group cannot capture, and the single-word ones
    # include "آب" — which folds to "اب", also the word for "father", and would
    # fire on prose. They are handled instead by `LEVANTINE_MONTHS`, which
    # rewrites them to the Gulf name before the month group ever runs.
    "يناير": 1, "فبراير": 2, "مارس": 3, "ابريل": 4, "مايو": 5, "يونيو": 6,
    "يوليو": 7, "اغسطس": 8, "سبتمبر": 9, "اكتوبر": 10, "نوفمبر": 11,
    "ديسمبر": 12,
    # …and the -ه spellings of the two that take one, which fold to the same
    # form only if the page writes them with ة.
    "يونيه": 6, "يوليه": 7,
}

#: "1761م" — the ميلادي (AD) era marker glued to a year. It defeats the
#: year-of-last-resort pattern outright, because a `\b` cannot fire between "1"
#: and "م": both are word characters. Six of the seven emirate ruler tables on
#: ar.wikipedia write every date this way.
ARABIC_ERA = re.compile(r"(?<=\d)\s*م(?!\w)")

#: The Levantine (Syriac-derived) month names, rewritten to the Gulf name in
#: `MONTHS` before the month group runs. Iraqi pages date almost everything this
#: way — "12 حزيران 1948" for the central bank's first governor, "11 تشرين
#: الثاني 1920" for its first prime minister — and without this every one of
#: them fell through to the bare-year rule and landed on the item as a year
#: beside its day-precision neighbours.
#:
#: Two of the twelve are *two words*, which is why this is a rewrite and not
#: twelve more `MONTHS` keys: the day-month-year group captures a single token.
#: The alef is spelled أ, آ and ا across pages, hence the character classes —
#: except for August, which is matched only in its madda spelling "آب", because
#: the bare-alef form "اب" is also the word for "father" and would fire on
#: prose. Ordered longest-first, and every pattern is word-bounded.
#: The Gulf name each one becomes, written the way `MONTHS` keys it — already
#: hamza-folded, so the lookup finds it — beside the spellings a page may use
#: for the same month, which is what the repeat collapse below has to match.
_GULF_MONTHS = (
    ("يناير", r"يناير"),
    ("فبراير", r"فبراير"),
    ("مارس", r"مارس"),
    ("ابريل", r"[أاآإ]بريل"),
    ("مايو", r"مايو"),
    ("يونيو", r"يونيو|يونيه"),
    ("يوليو", r"يوليو|يوليه"),
    ("اغسطس", r"[أاآإ]غسطس"),
    ("سبتمبر", r"سبتمبر"),
    ("اكتوبر", r"[أاآإ]كتوبر"),
    ("نوفمبر", r"نوفمبر"),
    ("ديسمبر", r"ديسمبر"),
)
LEVANTINE_MONTHS = tuple(
    (re.compile(rf"(?<!\w){pattern}(?!\w)"), gulf)
    for pattern, gulf in (
        (r"كانون\s+ال[أاآإ]ول", "ديسمبر"),
        (r"كانون\s+الثاني", "يناير"),
        (r"تشرين\s+ال[أاآإ]ول", "اكتوبر"),
        (r"تشرين\s+الثاني", "نوفمبر"),
        (r"حزيران", "يونيو"),
        (r"[أاآإ]يلول", "سبتمبر"),
        (r"شباط", "فبراير"),
        (r"[أاآإ]ذار", "مارس"),
        (r"نيسان", "ابريل"),
        (r"[أاآإ]يار", "مايو"),
        (r"تموز", "يوليو"),
        (r"آب", "اغسطس"),
    )
)
#: A cell dated in both naming systems at once — "14 تموز يوليو 1958", "6 كانون
#: الثاني/يناير 1921" — names one month twice over once the rewrite above has
#: run, and the year is then no longer adjacent to the month, which costs the
#: day. Collapsing the repeat binds them back together. Each month is collapsed
#: on its own rather than with a backreference, because the two halves need not
#: be spelled alike: the page's own "أبريل" meets the rewrite's "ابريل".
_REPEATED_MONTHS = tuple(
    (re.compile(rf"(?<!\w)(?:{spellings})\s*[/،\-–]?\s*(?:{spellings})(?!\w)"), gulf)
    for gulf, spellings in _GULF_MONTHS
)


def _levantine(text: str) -> str:
    """Rewrite Levantine month names to the Gulf names `MONTHS` knows."""
    for pattern, gulf in LEVANTINE_MONTHS:
        text = pattern.sub(gulf, text)
    for pattern, gulf in _REPEATED_MONTHS:
        text = pattern.sub(gulf, text)
    return text


#: Header text → column role. Matched on a normalised, accent-free prefix, so
#: one entry covers a family of spellings. Ordered: the first match wins, which
#: matters where one language's word for "start" prefixes another's for "term".
COLUMN_ROLES = [
    # Persian (fa.wikipedia). First in the list because these are the most
    # specific keys here and the table is scanned in order — a bare stem below
    # would otherwise claim a two-word Persian header first.
    #
    # None of the existing Arabic vocabulary reached fa.wikipedia before the
    # Perso-Arabic fold landed: `وزیر` and `وزير` differ in one code point, so
    # every one of these pages parsed with no column named at all. That is not
    # a silent nothing — with no `name` role the parser reads the *start-date*
    # cell as the person, so 31 province pages returned rows of date strings
    # and the Majlis rolls returned the electoral district as the officeholder.
    #
    # Ordering constraints measured on real pages: `مدت تصدی` before `مدت`,
    # `تاریخ آغاز`/`تاریخ پایان` before `آغاز`/`پایان`, `نام سرپرست` before
    # `نام`, `نامزدکننده` before `نام`, `دوره زمانی` before `دوره`,
    # `رئیس دولت` before any bare `رئیس`.
    ("نام سرپرست", "name"), ("نامزدکننده", "appointer"),
    ("نام و نام خانوادگی", "name"), ("نام شهردار", "name"),
    ("نام", "name"), ("متصدی", "name"), ("وزیر", "name"),
    ("استاندار", "name"), ("شهردار", "name"), ("رئیس دولت", "appointer"),
    # `رئیس‌جمهور` is the appointing president on every ministry roster and the
    # *holder* on `فهرست رئیس‌جمهورهای ایران`; that page declares
    # `column_roles=(("رئیس‌جمهور", "name"),)` rather than flipping this.
    ("رئیس‌جمهور", "appointer"), ("رئیس جمهور", "appointer"),
    ("نگاره", "portrait"), ("تصویر", "portrait"),
    ("تاریخ آغاز", "start"), ("تاریخ شروع", "start"),
    ("تاریخ انتصاب", "start"), ("تاریخ تعیین", "start"),
    ("دریافت سمت", "start"), ("آغاز به کار", "start"), ("آغاز", "start"),
    ("شروع", "start"), ("پذیرش پست", "start"), ("از تاریخ", "start"),
    ("از سال", "start"),
    ("تاریخ پایان", "end"), ("پایان", "end"), ("ترک پست", "end"),
    ("تا تاریخ", "end"), ("تا سال", "end"),
    # `دوران تصدی` and `دوره زمانی` are ranges; `مدت تصدی`, `مدت`,
    # `طول دوران` and `طول تصدی` are tenure *lengths*. The asymmetry decides
    # the global mapping: a duration wrongly typed `days` is inert, while one
    # wrongly typed `period` shadows the start/end pair beside it and costs
    # every date on the page. The two pages where `مدت تصدی` really is the only
    # date column say so with `RosterSource.column_roles`.
    ("دوران تصدی", "period"), ("دوران نخست‌وزیری", "period"),
    ("دوره زمانی", "period"), ("زمان خدمت", "period"),
    ("مدت تصدی", "days"), ("طول دوران", "days"), ("طول تصدی", "days"),
    ("دورهٔ تصدی", "days"), ("مدت", "days"),
    # `دوره` is never a period: it holds a President or PM name on all 18
    # province pages that use it, and an ordinal elsewhere. Typed `period` it
    # would cost every date on every one of them.
    ("دوره نخست‌وزیری یا ریاست‌جمهوری", "appointer"),
    ("دوره ریاست جمهوری یا نخست‌وزیری", "appointer"),
    ("دوره", "appointer"), ("گمارنده", "appointer"), ("دولت", "appointer"),
    ("هیئت دولت", "appointer"), ("صدراعظم وقت", "appointer"),
    ("نخست‌وزیر", "appointer"), ("رهبر", "appointer"), ("شاه", "appointer"),
    ("مقام", "office"), ("سمت", "office"),
    ("وزارت‌خانه", "office"), ("وزارتخانه", "office"),
    ("حزب", "party"), ("جناح", "party"),
    ("ردیف", "ordinal"), ("شماره", "ordinal"), ("ر.", "ordinal"),
    ("م.", "ref"), ("منبع", "ref"), ("مراجع", "ref"),
    # Lifespans, ages and birthplaces are not terms (§7 #10): named so the
    # date parser cannot reach a birth year and read it as a start.
    ("وضعیت", "notes"), ("تولد–مرگ", "notes"), ("تاریخ تولد", "notes"),
    ("سال تولد", "notes"), ("محل تولد", "notes"), ("زاده", "notes"),
    ("سن", "notes"), ("امضا", "notes"), ("مجلس", "notes"),
    ("توضیحات", "notes"), ("توضیح", "notes"), ("ائتلاف", "notes"),
    ("مدرک تحصیلی", "notes"), ("جایگاه", "notes"),
    # English keys the Iranian en.wikipedia pages need. `Duration` beside
    # `Term` both landed on `period` and shadowed the real cells.
    ("duration", "days"),
    # Spanish
    ("nombre", "name"), ("ministro", "name"), ("titular", "name"),
    ("presidente", "name"), ("funcionario", "name"),
    ("inicio", "start"), ("desde", "start"), ("asuncion", "start"),
    ("nombramiento", "start"),
    ("finalizacion", "end"), ("fin", "end"), ("hasta", "end"), ("cese", "end"),
    ("periodo", "period"), ("mandato", "period"),
    # "Duración" is a *tenure length* ("1 año y 143 días"), not a term. Under
    # the `period` role it shadowed the start and end cells beside it and every
    # date on the table was lost; as `days` it cannot.
    ("duracion", "days"), ("tiempo en el cargo", "days"),
    ("designante", "appointer"), ("designado", "appointer"),
    ("nombrado", "appointer"), ("gobierno", "appointer"),
    ("partido", "party"), ("ref", "ref"), ("observacion", "notes"),
    ("cartera", "office"), ("cargo", "office"), ("institucion", "office"),
    # Which polity's office a row belongs to, where one table serves several:
    # es.wikipedia tabulates all nineteen autonomous communities' presidents in
    # one list, naming the community in a rowspanned first column.
    ("autonomia", "office"), ("comunidad", "office"),
    # English, for list articles the country's own wiki does not keep.
    ("name", "name"), ("portrait", "portrait"), ("image", "portrait"),
    ("imagen", "portrait"), ("foto", "portrait"),
    ("took office", "start"), ("assumed office", "start"),
    ("left office", "end"), ("term of service", "period"),
    ("term of office", "period"), ("tenure", "period"), ("term", "period"),
    ("time in office", "days"), ("party", "party"), ("notes", "notes"),
    ("monarch", "appointer"), ("government", "appointer"),
    ("constituency", "notes"), ("no", "ordinal"), ("#", "ordinal"),
    # `en:Regent of Iraq` dates the regency for Faisal II's whole minority under
    # its own pair of headers, which no other key reaches; unrecognised, its
    # three rows carried no dates and the fourteen years the King and prime
    # minister lists do not cover were unrecordable.
    ("regency start", "start"), ("regency end", "end"),
    # `en:List of governors of Erbil` and `…of Duhok` head their holder column
    # "Person" and Duhok's term "Time as governor" — which must be `period` and
    # cannot be reached from "time in office", the day-count decoy. Both keys are
    # needed together: without the first the pages have no name column, without
    # the second Duhok has no date column and is dropped as a navbox. 56 rows.
    # `en:Maysan Governorate` heads its term "Assumed role", also a `period`
    # rather than a start — its first row reads "1992-1994".
    ("person", "name"), ("time as governor", "period"),
    ("assumed role", "period"),
    # "Office holder" must precede "Office": matching is header-startswith-key,
    # so a bare "office" key would claim the holder column and the table would
    # lose its names. The UAE cabinet list heads exactly these two side by side.
    ("office holder", "name"), ("officeholder", "name"), ("incumbent", "name"),
    # "Elected member" heads the winners' column of every constituency table on
    # an election article. "Constituency" beside it already has the `notes`
    # role, so unnamed the members landed in `notes` too: the table parsed with
    # no name column and its wikilinks were never collected.
    ("elected member", "name"), ("governor", "name"), ("office", "office"),
    # Monarchical rosters date the *reign*, not the "term". Without "Ruled" the
    # seven-emirate ruler list parses with no date column at all and is dropped
    # whole. "Reign start"/"Reign end" precede the bare "Reign" for the same
    # prefix reason as above.
    ("ruled", "period"), ("reign start", "start"), ("reign end", "end"),
    ("years of reign", "period"), ("reign", "period"),
    # A lifespan is not a tenure. These columns sit beside the dates on the
    # dynastic lists and naming them keeps `parse_date` away from a death year.
    ("lifespan", "notes"), ("birth", "notes"), ("death", "notes"),
    ("family", "notes"), ("house", "notes"), ("emirate", "notes"),
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
    # Arabic. Keys are written in natural spelling because `_role_keys` folds
    # them exactly as it folds a header, so "الإسم" and "الاسم" — which head the
    # same column on different Emirates pages — reduce to one entry.
    #
    # Ordered longest-first within each role, since matching is
    # header-startswith-key: "المدة" (a tenure *length*) must not be reachable
    # through "مدة", and vice versa, or a day count shadows the date cells
    # exactly as "Duración" did on the Spanish lists.
    ("الاسم", "name"), ("اسم الحاكم", "name"), ("اسم", "name"),
    ("شاغل المنصب", "name"), ("الحاكم", "name"), ("الوزير", "name"),
    # Kuwait's chief-of-staff list heads its holder column with the office, and
    # names the appointing *defence minister* in a column of its own. So
    # "وزير الدفاع" has to be claimed as the appointer before the generic
    # "وزير" below can read it as a name: it was the only column reading as a
    # name on that page, and the thirteen chiefs of staff parsed as thirteen
    # ministers.
    ("رئيس الأركان", "name"), ("وزير الدفاع", "appointer"),
    # The Saudi ministerial lists head the holder column with the office itself
    # — "وزير الداخلية", "وزير الصحة" — and the Shura membership lists with
    # "العضو". Both precede nothing they could shadow: "وزارة" (the ministry,
    # an `office` column) differs from "وزير" at its third letter.
    #
    # "الأعضاء" (the members, plural) is the sole column of both Shura Council
    # rolls on `ar:قائمة أعضاء مجلس الشوري القطري (2021)`. Neither "العضو" nor
    # "عضو" reaches it — the plural inserts an alif-hamza after the article —
    # so without its own key those tables have no name column at all.
    ("وزير", "name"), ("العضو", "name"), ("الأعضاء", "name"),
    # Jordan heads its holder column with the office in the definite article
    # where Saudi Arabia and Kuwait use the bare noun. "الرئيس" is the Senate
    # list's *president* — the person, not a body — and without it that table
    # had no name column at all and all 28 rows were dropped for want of one;
    # "عضو" (undefined) heads the 27th Senate roll, which "العضو" cannot reach
    # because the key differs at its first letter, not its third.
    ("الرئيس", "name"), ("عضو", "name"),
    # "المحافظة" is deliberately *not* a key of its own, and the reason is worth
    # recording because the natural guess is wrong. It folds to "المحافظه", which
    # the "المحافظ" key below reaches by prefix — and on the page that has the
    # column (`ar:محافظة صلاح الدين`) that is the right answer: the header reads
    # "the governorate" and the cells hold the *holder*, so `name` is what its 21
    # rows need. Naming it `notes` to be safe cost them their name column.
    #
    # A list serving several governorates would head the *place* column the same
    # way, where the role is `office` — the "office holder" before "office" trap
    # with no lexical difference to lean on. No page in use has that shape; when
    # one turns up it declares itself through `RosterSource.column_roles` rather
    # than flipping this for everyone.
    #
    # `ar:قائمة محافظي نينوى` heads its holder column "المحافظ أو المتصرف" —
    # governor *or* mutasarrif — and the central bank article heads its 25
    # governors with a bare "المحافظ". Neither was recognised, so both tables
    # parsed with no name column at all: the bank's governors had dates and no
    # people, and Nineveh's 88 had neither.
    #
    # "المتصرف" is not an Ottoman title, which is the natural guess and is wrong:
    # measured over that page, mutasarrif rows run 1921-02-20 to 1969-09-17 and
    # muhafiz rows 1970-09-03 onwards. It is the *same* Iraqi office under the
    # name the 1969 governorates law replaced when liwa became muhafazah. The
    # Ottoman governors are a different article (`ar:قائمة ولاة الموصل`), in
    # prose, and pre-1918.
    ("المحافظ أو المتصرف", "name"), ("المحافظ", "name"),
    ("الصورة", "portrait"), ("صورة", "portrait"),
    # "من الفترة" / "حتى الفترة" are the Saudi lists' start and end. A bare
    # "من" cannot cover the first: two-letter keys match whole (see `_roles`),
    # and there was no key for "حتى" at all — so the header row, marked up as
    # `td` on these pages, recognised one column of seven, failed
    # `_reads_as_header`'s two-column test, and every date on the page was lost:
    # eleven interior ministers and twenty-one health ministers, all undated.
    ("من الفترة", "start"), ("تولى", "start"), ("بداية", "start"),
    # Kuwait dates its holders three further ways. "تاريخ التعيين" (date of
    # appointment) and "تاريخ انتهاء الخدمة" (date service ended) head the
    # information ministry's pair, and neither begins with "التاريخ" — the
    # article is absent — so the bare key below cannot reach them. "بدأ فترته"
    # / "انتهت فترته" are the *sub*-headers under the chief-of-staff list's
    # three-wide "مدة الرئاسة"; `_subroles` reads them, and without them the
    # duration cell beside them was the only one that parsed.
    ("تاريخ التعيين", "start"), ("تاريخ انتهاء", "end"),
    # "تاريخ اليمين الدستورية" — the date a member swore the constitutional
    # oath — is how a Jordanian membership roll dates its rows, and like the
    # two above it does not begin with "التاريخ".
    ("تاريخ اليمين", "start"),
    # Iraq dates a governor by "تاريخ المباشرة" (the date he took up the post)
    # and a president by "استلام الرئاسة" against "ترك الرئاسة" — the latter
    # already reachable through the "ترك" key, the former two not through any.
    ("تاريخ المباشرة", "start"), ("استلام", "start"),
    # `ar:محافظة صلاح الدين` dates its 21 governors "تاريخ تعيينهم" (the date of
    # their appointment) against "انتهاؤه", and `ar:رؤساء مجلس النواب العراقي`
    # closes a speakership with "مغادرة المنصب". None is reachable by prefix from
    # the keys above — "تاريخ التعيين", "انتهت" and "غادر" each differ inside the
    # word — so all three tables parsed starts with no ends, which reads as 43
    # sitting officials rather than as a lost column. The Jordan "غادر" bug in
    # three new spellings.
    ("تاريخ تعيينهم", "start"), ("انتهاؤه", "end"), ("مغادرة", "end"),
    # The modern speakership list opens with "تسلم منصبه" against a "ترك منصبه"
    # the "ترك" key already reaches — so the page read 14 ends and no starts at
    # all. Iraq spells the same act four ways across two articles about one
    # office: "تولى", "استلام", "تسلم", and "تاريخ تعيينهم" one lane over.
    ("تسلم", "start"),
    ("بدأ", "start"), ("انتهت", "end"),
    ("من", "start"),
    # "غادر المنصب" (left the post) closes what "تولى المنصب" opens on every
    # one of the ~109 `ar:حكومة <رئيس الوزراء>` cabinet articles, which are the
    # only dated source for Jordan's ministers. "تولى" was already a start key,
    # so the pair looked half-recognised: every cabinet row parsed with a start
    # and no end, which reads as a sitting minister rather than as a lost cell.
    ("غادر", "end"),
    ("حتى", "end"), ("ترك", "end"), ("نهاية", "end"), ("الى", "end"),
    # "الفترة الزمنية" is a tenure *length* ("3 سنوات و7 أشهر و28 يومًا") and
    # must be claimed before the bare "الفترة": through that key it took the
    # `period` role, shadowed the start and end cells either side of it, and
    # every date on the chief-of-staff list was lost. The Czech "Dny v úřadu"
    # bug in Arabic.
    # …and "فترة بقائه بالمنصب" (how long he stayed in the post) is the same
    # decoy one word further in, sub-heading a third column beside the two that
    # hold the real dates. Every value of a repeated role is joined with " – "
    # before parsing, so leaving it as a `period` appended a tenure length to
    # the range and the crown princes' end dates all parsed as nothing.
    # …and "طول الفترة" (the length of the period) is the same decoy a third
    # time, heading the seventh column of `ar:قائمة أمراء قطر` beside the two
    # that hold the real dates. It cost nothing there only because "بداية
    # الفترة" and "نهاية الفترة" were both recognised — which is exactly how
    # the Czech and Kuwaiti spellings stayed invisible until a page turned up
    # without that luck. It cannot be reached through the bare "فترة" key
    # (it differs at its first letter), so it needs naming of its own.
    ("الفترة الزمنية", "days"), ("فترة بقائه", "days"), ("طول الفترة", "days"),
    # "فترة الحكم", "فترة تولي المنصب" and a bare "الفترة" are all one span in
    # two cells or one; the period role handles either.
    ("فترة", "period"), ("الفترة", "period"),
    # A table dated twice over, once per calendar: the Saudi province articles
    # tabulate their governors under "التاريخ الهجري" (AH) beside "التاريخ
    # الميلادي" (AD). Only the second is a term this workbench can record — no
    # conversion happens anywhere (`scripts/check_dates.py`) — so the AH column
    # is named a decoy, exactly as a "Duración" day count is, and *neither* may
    # be reachable through a bare "التاريخ" prefix key. A bare key added *after*
    # both of them is safe and is what the Kuwaiti finance ministry's single
    # undivided "التاريخ" column needs: first match wins, so the two specific
    # keys still claim their own columns.
    ("التاريخ الميلادي", "period"), ("التاريخ الهجري", "notes"),
    ("التاريخ", "period"),
    # Iraq. "مدة العضوية" (the membership period) heads a *pair* of cells on
    # every `ar:وزارة <portfolio> (العراق)` article — start on one, end on the
    # other — and it reaches the bare "مدة" decoy key below by prefix, so both
    # date columns were being read as a tenure length and thrown away. The
    # defence ministry's four era tables parsed 38 ministers with zero dates and
    # no error; interior, awqaf, environment and electricity the same. It has to
    # be claimed as a `period` *before* "مدة", and in both spellings, because
    # the first table of the pair drops the article ("مدة عضوية").
    ("مدة العضوية", "period"), ("مدة عضوية", "period"),
    ("المدة الزمنية", "days"), ("المدة", "days"), ("مدة", "days"),
    ("المنصب", "office"), ("الوزارة", "office"), ("المسمى", "office"),
    # "المهام الوزارية" — the ministerial duties — is how 76 of Jordan's 108
    # cabinet articles head the portfolio column, against two that use
    # "المنصب". Unnamed, the office cell was invisible and every one of those
    # pages parsed as a list of names attached to nothing.
    ("المهام", "office"),
    # "في عهد" — "in the reign of" — names the king who appointed the holder,
    # which is the same channel a Spanish list's "Designante" column carries.
    ("في عهد", "appointer"),
    # Iraq's ministry tables close with the prime minister or the president who
    # appointed the holder — the same channel again. Note "رئيس الوزراء" heads
    # the *holder* column on `ar:قائمة رؤساء وزراء العراق`, where it means the
    # name and not the appointer: one string, two roles, exactly as "المدة"
    # means duration in Kuwait and a period in Iraq. No key can tell them
    # apart, so the default is the commoner reading and a page that disagrees
    # says so through `RosterSource.column_roles`.
    ("رئيس الوزراء", "appointer"), ("رئيس الدولة", "appointer"),
    # The KRG cabinet page heads its portfolio column "الوزارات والدوائر" (the
    # ministries and departments) in a header row marked up as `td`. Only
    # "وزير" beside it was recognised, one column of two, so the row failed
    # `_reads_as_header`'s two-column test and all 32 rows were dropped.
    ("الوزارات والدوائر", "office"),
    ("حزب سياسي", "party"),
    ("الملاحظات", "notes"), ("ملاحظات", "notes"), ("الامارة", "notes"),
    ("العائلة", "notes"), ("العمر", "notes"),
    # A lifespan beside the tenure, and the neighbours a succession list prints
    # either side of the holder ("سبقه" preceded by, "تبعه" followed by). Named
    # so they cannot be read as the term, and so the `td` header row above them
    # is recognised as a header at all.
    ("الميلاد", "notes"), ("الوفاة", "notes"),
    # The same lifespan under two more headings: `ar:قائمة رؤساء العراق` prints
    # it as "الحياة" and `ar:قائمة رؤساء وزراء العراق` as "ولادة-وفاة". Named so
    # a birth and death year cannot be read as the term — the bracketed-lifespan
    # trap with a column heading of its own. "الرتبة" is the military rank on
    # the chief-of-staff list, "وصف" the note column on Nineveh's governors.
    ("الحياة", "notes"), ("ولادة-وفاة", "notes"),
    ("الولادة والوفاة", "notes"), ("مولده", "notes"), ("الملك", "notes"),
    ("الرتبة", "notes"), ("وصف", "notes"),
    ("سبقه", "notes"), ("تبعه", "notes"), ("أبرز المناصب", "notes"),
    ("الحزب", "party"), ("المرجع", "ref"), ("مصدر", "ref"), ("مراجع", "ref"),
    ("التسلسل", "ordinal"), ("الرقم", "ordinal"),
    ("مسلسل", "ordinal"), ("الترتيب", "ordinal"), ("ترتيب", "ordinal"),
    # The Shura lists number their rows under a bare "م". One letter, so it can
    # only ever match a header that is exactly that.
    ("م", "ordinal"),
]

# Wikipedia writes date ranges with every dash there is, plus a few words for
# "still in office".
DASHES = "-–—‒―"
#: …and an Arabic table often writes the range in words instead: "إلى" / "حتى"
#: ("to", "until"), optionally with a colon. Rewritten to a dash so the split in
#: `parse_period` can see it. The lookahead is what keeps "حتى الآن" — "until
#: now", the incumbency marker itself — from being cut into a missing end date.
#: The optional dash is for the cell that writes *both* — "9 أيلول 2014-الى 14
#: أيلول 2020", where the dash is glued to the year and the word follows it. Left
#: in place, the substitution puts a second dash beside the first and the split
#: takes the pair for one separator, losing the end: that cell is the Iraqi
#: central bank's sitting governor and his first term ran to 2020-09-14.
ARABIC_RANGE = re.compile(
    # `تا` must be a whole word. It is the first two letters of `تاريخ`
    # ("date"), which an Arabic cell writes as `من تاريخ … لغاية تاريخ …`, so an
    # unguarded alternative splits the range inside the word and loses the
    # first bound entirely. It is also the first two letters of `تاكنون`
    # ("until now") — the incumbency marker, exactly the `حتى الآن` trap — and
    # the same guard covers both.
    r"\s*[-–—]?\s*(?:[إا]ل[يى]|حت[يى]|لغاي[ةه]|تا(?!\w))\s*:?\s*"
    r"(?!ال[آأا]ن|الان|اليوم|الوقت|الحالي)"
)
INCUMBENT = re.compile(
    r"actualidad|presente|present\b|incumbent|en\s+(?:el\s+)?(?:cargo|funciones)|actual|titular$"
    r"|настоящее\s+врем|по\s+сей\s+день|н\.\s*в\.|дагэтуль|цяпер|зараз"
    r"|дзеючы|теперішній|нині"
    r"|úřadující|současnost|dosud"
    # Persian. `متصدی` ("incumbent") ends the sitting holder's row on the
    # ministry rosters, and `تاکنون` ("until now") is the ambassador bullets'
    # form — the latter also *begins* with the range word `تا`, which is why
    # `ARABIC_RANGE` guards it with a lookahead rather than splitting on it.
    # Both yeh spellings, because `_incumbent` runs on the raw cell rather than
    # on `fold()` output: fa.wikipedia writes Persian yeh (U+06CC) and the
    # Arabic pages Arabic yeh (U+064A), and only the folded path unifies them.
    r"|متصد[يی]|تاكنون|تاکنون|در\s*حال\s*تصد[يی]"
    # Arabic. All four forms occur on the Emirates pages, and the alef of
    # "الآن" is spelled آ, أ and ا across them, hence the character class —
    # this pattern is matched against raw cell text, not the folded form.
    r"|حت[يى]\s*ال[آأا]ن|لحد\s*ال[آأا]ن|الوقت\s*الحاضر|الحالي|اليوم"
    # …and "الآن" standing alone after the range dash, with no "حتى" in front of
    # it, which is how Iraq's sitting cabinet writes every one of its rows:
    # "14 مايو/آيار 2026 – الآن". Without it 24 ministers of the government in
    # office ship as open-ended statements rather than as incumbents.
    r"|[-–—]\s*ال[آأا]ن",
    re.I,
)
#: "…–23 de julio de 1834 (fallecido en el cargo)" ends a term; it does not
#: continue one. Without this the "en el cargo" inside it reads as "still in
#: office" and the end date is thrown away — four Spanish chief justices died
#: at their desks and every one of them was recorded as incumbent.
DIED_IN_OFFICE = re.compile(
    r"fallecid|falleci[oó]|muri[oó]|muerto|asesinad|died|deceased"
    # Arabic: ar:حاكم دبي ends terms with "(الوفاة لأسباب طبيعية)" and
    # "(الموت بنوبة قلبية)". Both contain "اليوم"-free death words, but the cell
    # also often says "الحالي" nearby, so this has to out-rank INCUMBENT — which
    # it does, because `is_incumbent` requires this pattern *not* to match.
    r"|الوفا[هة]|الموت|تو[في]ي|اغتيل|قتل\b",
    re.I,
)
#: A table that holds data rather than page furniture, by class.
TABLE_CLASSES = re.compile(r"wikitable|sortable", re.I)
#: Classes that mark page chrome. Needed because the selector now accepts a
#: class-less table: without this, dropping the `wikitable` requirement would
#: start reading infoboxes and navboxes as rosters.
CHROME_CLASSES = re.compile(
    r"infobox|navbox|metadata|ambox|sidebar|mbox|navigation-only|noprint", re.I
)
BACKGROUND = re.compile(r"background(?:-color)?\s*:\s*(#[0-9A-Fa-f]{3,8})")
#: Some wikis mark an acting officeholder in the cell text instead of by
#: colour: "(в. а.)" on be.wikipedia, "и. о." on ru.wikipedia.
ACTING_TEXT = re.compile(
    r"\(\s*(?:в\.?\s*а\.?|в\.?\s*і\.?\s*а\.?|и\.?\s*о\.?|в\.?\s*и\.?\s*о\.?"
    r"|acting|interim|encargad\w*"
    # Arabic: "بالإنابة" / "بالوكالة" are the standard formulas. No Emirates page
    # uses them today — the ar president table simply omits its one-day acting
    # holder — but the en cabinet list writes "(Acting)", which the English
    # branch above already catches.
    # …and Iraq drops the preposition and marks the *office* cell instead:
    # "وزارة الصحة (وكالة)", "وزير المالية (وكالة)".
    r"|بال[إأا]ناب[هة]|بالوكال[هة]|وكال[هة])\s*\)"
    r"|выконва\w*\s+абавязк|исполняющ\w*\s+обязанност",
    re.I,
)
#: An acting marker leading the *period* rather than the name: ru.wikipedia
#: writes "(и. о., октябрь — декабрь 1995)". `ACTING_TEXT` cannot see it — that
#: pattern wants the marker alone in its brackets — so the spell reads as an
#: ordinary term whose dates then fail to parse, and the row lands in a
#: convention queue as `no_dates` when it is really an acting spell.
ACTING_PREFIX = re.compile(
    r"^\s*(?:в\.?\s*а\.?|и\.?\s*о\.?|в\.?\s*и\.?\s*о\.?|acting|interim"
    r"|encargad\w*)\s*[,;]\s*",
    re.I,
)
#: A page that declares its own italic convention. en:President of the United
#: Arab Emirates says "Acting presidents are in italics" and marks the one-day
#: 2004 incumbent that way — with no background colour at all, so `_flags` saw
#: nothing. Only a page carrying such a sentence has its italics read as a flag:
#: elsewhere italics are emphasis, foreign words and ship names.
ITALIC_ACTING = re.compile(
    r"(?:acting|interim)[^.]{0,60}\bitalic|\bitalic[^.]{0,60}(?:acting|interim)",
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
    r"|vacante|vacant|vakansiya|вакансия|вакантна"
    # es.wikipedia numbers the gaps among the holders too: "Cargo suprimido
    # entre 1814 y 1820", "Supresión del Senado como órgano constitucional".
    r"|cargo\s+(?:suprimido|vacante|sin)|supresion|puesto\s+suprimido"
    r"|sin\s+titular|interregno|abolished|office\s+(?:abolished|vacant))\b",
    re.I,
)


#: Arabic letters that spell the same word two ways. ar.wikipedia mixes them
#: freely *within one page* — "الاسم"/"الإسم" head the same column, "حتى الآن"
#: and "حتى الأن" both mean "to date", and "أبوظبي"/"أبو ظبي" are the same
#: emirate — so a header or month name only matches once the hamza and ya
#: variants are folded to their bare forms.
_ARABIC_FOLD = {"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
                "ى": "ي", "ئ": "ي", "ؤ": "و", "ة": "ه",
                # Persian writes kaf and yeh at different code points from
                # Arabic, so `وزیر` never reaches the `وزير` key already in
                # COLUMN_ROLES and `کارگزاران` never matches `كارگزاران`.
                # Folding them is what makes the existing Arabic vocabulary
                # work on fa.wikipedia at all.
                "ک": "ك", "ی": "ي",
                # The zero-width non-joiner is Persian's intra-word space
                # (`نیم‌فاصله`). It is not whitespace, so `" ".join(split())`
                # leaves it in place and `امام‌جمعه` never matches `امام جمعه`.
                # A space is the right target: the same compound is written
                # both ways, and personal names divide on it (`علی‌اکبر`).
                "\u200c": " "}
#: Vowel marks and the kashida stretch character carry no meaning for matching
#: and appear only decoratively. The range runs to U+0655 so it also covers the
#: ezafe hamza that Persian writes above a final he (`حوزهٔ` vs `حوزه`) — outside
#: the U+064B–U+0652 harakat block, and on 3 of 16 Majlis headers. The
#: zero-width *joiner* is dropped outright: it carries no meaning and Persian
#: builds its calendar-era markers with it (`ه‍.ق`).
_ARABIC_STRIP = "ـٰ\u200d" + "".join(chr(c) for c in range(0x064B, 0x0656))


def _deaccent(text: str) -> str:
    """Fold the diacritics that vary between spellings of the same header.

    Cyrillic і/ў/ё are folded too: be-tarask and be spell the same column
    header differently ("Тэрмін" / "Тэрмiн"), and ru "ё" is routinely typed
    as "е". Arabic hamza and ya variants fold the same way, and its vowel marks
    are dropped outright.
    """
    trans = str.maketrans(
        "áéíóúüñÁÉÍÓÚÜÑіїўёІЇЎЁ" "áčďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ"
        + "".join(_ARABIC_FOLD),
        "aeiouunAEIOUUNиiуеИIУЕ" "acdeeinorstuuyzACDEEINORSTUUYZ"
        + "".join(_ARABIC_FOLD.values()),
        _ARABIC_STRIP,
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


def _role_keys_with(overrides: Tuple[Tuple[str, str], ...]) -> List[Tuple[str, str]]:
    """`_role_keys` with a page's own readings taking precedence.

    Reach for this when one header string means two different things on two
    pages and no key can tell them apart, which is the one case the ordered
    table cannot express. "المدة" is a tenure *length* on the Kuwaiti and Saudi
    lists — it is in the table as a `days` decoy for exactly that reason — and
    on `ar:رؤساء أركان الجيش العراقي` it is the only date column there is,
    holding "من: 6 كانون الثاني/يناير 1921 حتى: …" for all 36 chiefs of staff.
    A page says which it means; a global rule would have to guess, and guessing
    the other way is what silently cost every date on the Czech and Kuwaiti
    pages the decoy keys were added for.
    """
    return [(_norm(key), role) for key, role in overrides] + _role_keys()


def _incumbent(text: str) -> bool:
    """Does this cell say the term is still running?"""
    return bool(INCUMBENT.search(text)) and not DIED_IN_OFFICE.search(text)


#: Persian-Indic (U+06F0–06F9) and Arabic-Indic (U+0660–0669) digits, folded to
#: ASCII in one pass. Both ranges occur in Perso-Arabic wikitext and they occur
#: *mixed inside a single number* — `١۵ مرداد ١۴٠٢` sits on the same page as
#: `۱۵ مرداد ۱۴۰۲` — so a two-step conversion has an order to get wrong and this
#: does not.
_ASCII_DIGITS = str.maketrans(
    {**{0x06F0 + n: str(n) for n in range(10)},
     **{0x0660 + n: str(n) for n in range(10)}}
)

#: The twelve Solar Hijri months. Keys are stored both raw and `_deaccent`ed,
#: the way `parse_date` looks a month word up.
_JALALI_RAW = {
    "فروردین": 1, "اردیبهشت": 2, "خرداد": 3, "تیر": 4, "مرداد": 5,
    # `امرداد` is the archaic spelling of Mordad and is still in use on
    # fa.wikipedia's older roster tables.
    "امرداد": 5,
    "شهریور": 6, "مهر": 7, "آبان": 8, "آذر": 9, "دی": 10, "بهمن": 11,
    "اسفند": 12,
}

#: A cell that names the *lunar* calendar. Solar Hijri and lunar Hijri years
#: overlap — Astan Quds carries lunar 1302/1335/1344, squarely inside the solar
#: range in use — so the calendar can only be read from this marker, never
#: inferred from the year. Written against `_deaccent` output, where the
#: zero-width joiner in `ه‍.ق` is already gone.
_LUNAR_MARKER = re.compile(r"ه\s*\.?\s*ق(?!\w)")

#: What the Gregorian branches of `parse_date` will accept as a year. The bare
#: year rule has always carried this range; the ISO and `d/m/Y` branches never
#: did, which is why `parse_date('1392-05-13')` returned a 4th-century date.
_GREGORIAN_YEAR = re.compile(r"^(?:1[5-9]\d\d|20[0-4]\d)$")


def _jalali_months() -> Dict[str, int]:
    """`_JALALI_RAW` with a `_deaccent`ed key beside every raw one."""
    out: Dict[str, int] = {}
    for word, number in _JALALI_RAW.items():
        out[word] = number
        out[_deaccent(word)] = number
    return out


JALALI_MONTHS = _jalali_months()


def _jalali_iso(year: int, month: int, day: int) -> Optional[str]:
    """One Solar Hijri date as a Gregorian ISO day, or None if it is not one."""
    try:
        import jdatetime
        return jdatetime.date(year, month, day).togregorian().isoformat()
    except (ValueError, ImportError):
        return None


def _jalali_date(text: str) -> Optional[str]:
    """A Solar Hijri cell as a partial ISO Gregorian string, or None.

    Reach for this before the Gregorian patterns, because fa.wikipedia dates
    everything this way and the Gregorian rules would either miss the cell or —
    on an ISO-shaped or slash-shaped one — read the Solar Hijri year as an AD
    year and be wrong by six centuries.

    Three precisions, and only one of them survives intact:

    * **day** → the exact Gregorian day. Solar Hijri is a solar calendar, so
      this conversion is exact, unlike the lunar Hijri one `parse_date`
      deliberately declines to make.
    * **month** → a Gregorian *year*. A Solar Hijri month spans two Gregorian
      months, so month precision cannot survive; but measured over SH
      1360–1404 the year offset is constant for eleven of the twelve —
      +621 for months 1–9, +622 for 11–12 — so the year is safe to keep.
      **Dey (month 10) crosses and yields nothing.**
    * **bare year** → nothing. A Solar Hijri year straddles two Gregorian years
      (SH 1392 is 286 days of 2013 and 79 of 2014), so no year-precision
      rendering of it is correct.
    """
    if _LUNAR_MARKER.search(text):
        return None
    month_word = _first_month_in(text, JALALI_MONTHS)
    if month_word is None:
        return _jalali_numeric(text)
    month, hit = month_word
    day = hit.group(1)
    year = int(hit.group(3))
    if not 1200 <= year <= 1499:
        return None
    if day:
        return _jalali_iso(year, month, int(day))
    # Month precision. Dey is the one month that starts in one Gregorian year
    # and ends in the next, so it cannot be reduced to a year at all.
    if month == 10:
        return None
    return str(year + (621 if month <= 9 else 622))


def _first_month_in(text: str, table: Dict[str, int]):
    """The first `[day] month year` match whose word is really a month.

    Same discipline as `_first_month`: a pattern that matches but fails its
    lookup must not stop the scan, or a cell that leads with something
    date-shaped throws away the real date behind it.
    """
    for hit in re.finditer(
        r"(?:(?<!\d)(\d{1,2})(?!\d)\s*)?([^\W\d_]+)\s*(?:سال\s*)?(\d{3,4})", text
    ):
        word = hit.group(2)
        month = table.get(_deaccent(word), table.get(word))
        if month:
            return month, hit
    return None


def _jalali_numeric(text: str) -> Optional[str]:
    """`۱۴۰۰/۸/۱۲` — a Solar Hijri date written year-first with slashes.

    A two-digit year is read as 13xx (`۵۷/۱۲/۱۵` is SH 1357), which is the
    whole Markazi governors page. The abbreviation belongs to a century that
    ended at SH 1399, so 1400+ is deliberately unreachable this way — and a
    bare abbreviated year outside this slash shape (`۱۳۵۹–۶۰`) is still
    refused, because nothing there says which century it means.

    Note the order is year-first, which is the Persian convention and the
    reason this cannot collide with `parse_date`'s existing `d/m/YYYY` branch:
    that one requires its four-digit year *last*.
    """
    hit = re.search(r"(?<!\d)(\d{2}|\d{4})\s*/\s*(\d{1,2})\s*/\s*(\d{1,2})(?!\d)", text)
    if not hit:
        return None
    year, month, day = (int(part) for part in hit.groups())
    if year < 100:
        year += 1300
    if not 1200 <= year <= 1499 or not 1 <= month <= 12:
        return None
    return _jalali_iso(year, month, day)


def _first_month(pattern: str, text: str, group: int):
    """The first match of `pattern` whose `group` names a month, and the month.

    A month-name group is the one part of a date pattern that can match and
    still be wrong, so every caller wants "keep looking" rather than "give up".
    """
    for hit in re.finditer(pattern, text):
        word = hit.group(group)
        month = MONTHS.get(_deaccent(word), MONTHS.get(word))
        if month:
            return month, hit
    return None


def parse_date(text: str) -> Optional[str]:
    """A Spanish date as a partial ISO string: `1979-08-10`, `1979-08`, `1979`.

    Returns None when the cell holds no year at all, so callers can tell
    "no date given" from "date given but coarse".
    """
    low = _levantine(ARABIC_ERA.sub("", " ".join(text.split()).casefold()))
    # Both Indic digit ranges reduce to ASCII before anything reads a number.
    # Until this ran, every date on fa.wikipedia was invisible: not misparsed,
    # simply never matched.
    low = low.translate(_ASCII_DIGITS)
    # Solar Hijri first, because the Gregorian branches below would read its
    # year as an AD year. This is the opposite of the lunar Hijri ruling — that
    # calendar is left unconverted because an AH year falls outside the
    # Gregorian range and the day conversion is ambiguous; a Solar Hijri year
    # does *not* fall outside it, and its conversion is exact.
    jalali = _jalali_date(_deaccent(low))
    if jalali:
        return jalali
    # A question mark standing on its own is the source saying it does not know
    # this date, and the number beside it belongs to the *other* bound: the
    # Qatar Central Bank's first governor is dated "? - 1983" in a "Took office"
    # column and "January 1990" in "Left office", so reading 1983 as his start
    # invents a fact the article declines to state. Only a free-standing "?"
    # counts — one inside a word or attached to a number is something else.
    if re.search(r"(?:^|\s)\?(?:\s|$)", low):
        return None
    # "10 de agosto de 1979" (es), "16 июля 1990" (ru/be/uk) and "2. července
    # 1992" (cs) all reduce to day, month word, year — the Czech day is an
    # ordinal, so the dot after it has to be allowed for or the day is lost.
    # The dot can follow either part: Czech abbreviates the day ordinal ("2.
    # července 1992"), Spanish the month name ("17 de jul. de 1834"). Missing the
    # second is the difference between a day-precision term and a bare year.
    # The particle must be a *word*, hence `\s+` and not `\s*`: written `\s*` it
    # also matches the "De" of "December", leaving "cember" as the month name.
    # The match still succeeds, so the regex never backtracks and only the MONTHS
    # lookup fails — silently downgrading every English December to month
    # precision. "2 December 1971" is the UAE's founding date.
    # Every pattern below is scanned to its *first match whose word is actually
    # a month*, not to its first match. A cell can lead with something
    # date-shaped that is not a date, and giving up on it throws away the real
    # date behind it: ar.wikipedia's Saudi lists stack a Hijri date over the
    # Gregorian one, so "1 رجب 1441 هـ 25 فبراير 2020 م" matched at "1 رجب
    # 1441", failed the month lookup, fell through to the bare-year rule and
    # returned "2020" — day precision lost beside its day-precision neighbours.
    day_month = _first_month(
        r"\b(\d{1,2})\s*\.?\s*(?:del?\s+)?([^\W\d_]+)\s*\.?\s*(?:del?\s+)?(\d{4})",
        low, 2,
    )
    if day_month:
        month, hit = day_month
        return f"{hit.group(3)}-{month:02d}-{int(hit.group(1)):02d}"
    # "September 24, 1810" — English writes the month first, and the
    # day-month-year pattern above cannot see the day at all.
    month_day = _first_month(
        r"\b([^\W\d_]+)\s*\.?\s*(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*(\d{4})", low, 1
    )
    if month_day:
        month, hit = month_day
        return f"{hit.group(3)}-{month:02d}-{int(hit.group(2)):02d}"
    month_year = _first_month(r"\b([^\W\d_]+)\s*(?:del?\s*)?(\d{4})", low, 1)
    if month_year:
        month, hit = month_year
        return f"{hit.group(2)}-{month:02d}"
    # Both branches below take a year from a *shape* rather than from a range,
    # which is how a Solar Hijri cell used to leave here as a 4th-century AD
    # date. `1392-05-13` is a real cell on fa.wikipedia and it is 2013.
    iso = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", low)
    if iso and _GREGORIAN_YEAR.match(iso.group(1)):
        return iso.group(0)
    numeric = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", low)
    if numeric and _GREGORIAN_YEAR.match(numeric.group(3)):
        return f"{numeric.group(3)}-{int(numeric.group(2)):02d}-{int(numeric.group(1)):02d}"
    year = re.search(r"\b(1[5-9]\d\d|20[0-4]\d)\b", low)
    return year.group(1) if year else None


def _month_in(text: str) -> Optional[int]:
    """The month a bare month-name fragment names, if it names one."""
    for word in re.findall(r"[^\W\d_]+", text.casefold()):
        month = MONTHS.get(_deaccent(word), MONTHS.get(word))
        if month:
            return month
    return None


def parse_period(text: str) -> Tuple[Optional[str], Optional[str], bool]:
    """Split a "start – end" cell. Returns (start, end, still_in_office)."""
    cleaned = " ".join(text.split())
    incumbent = _incumbent(cleaned)
    # An Arabic table often writes the range in words rather than with a dash —
    # "12 حزيران 1948 إلى 14 شباط 1949" on the Iraqi central bank's governors,
    # "من: 6 كانون الثاني/يناير 1921 حتى: 3 تشرين الثاني/نوفمبر 1923" on the
    # chief-of-staff list — and the dash split below cannot see a word. Every
    # such cell parsed with a start and no end, which reads as a sitting holder
    # rather than as a lost bound: 25 central bank governors and 36 chiefs of
    # staff, all open-ended.
    # This runs *after* `_incumbent`, and skips the phrase it depends on,
    # because "حتى الآن" ("until now") is itself the incumbency marker — cutting
    # it first turns a sitting minister into an unbounded one. Kuwait's health
    # ministry has exactly that cell, and it was the only row in 48 prior roster
    # sources this change touched until the order was fixed.
    cleaned = ARABIC_RANGE.sub(" – ", cleaned)
    # Split on a dash that separates two dates, not the one inside "1979-08-10"
    # or a hyphenated name. A space on *either* side is enough: en.wikipedia
    # renders "September 24, 1810 –October 23, 1810" with none on the right, and
    # requiring both dropped every end date on the page.
    parts = re.split(
        rf"\s+[{DASHES}]+\s*|\s*[{DASHES}]+\s+|\s*[{DASHES}]{{2,}}\s*", cleaned
    )
    if len(parts) == 1 and re.search(rf"\d\s*[{DASHES}]\s*\d", cleaned):
        parts = re.split(rf"(?<=\d)\s*[{DASHES}]\s*(?=\d)", cleaned, maxsplit=1)
    start = parse_date(parts[0]) if parts else None
    end = parse_date(parts[1]) if len(parts) > 1 else None
    # "октябрь — декабрь 1995" states the year once, at the end, and means it
    # of both months. Without this the range loses its start entirely.
    if start is None and end and len(parts) > 1:
        month = _month_in(parts[0])
        if month:
            start = f"{end[:4]}-{month:02d}"
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
    #: Column role → the article titles that column links to. The party cell
    #: prints an abbreviation ("ODS") but links the full name ("Občanská
    #: demokratická strana"), so the link is what makes P102 resolvable
    #: without a per-country lexicon of party initials.
    links: Dict[str, List[str]] = field(default_factory=dict)

    @property
    def acting(self) -> bool:
        return any(
            re.search(
                # `سرپرست` ("caretaker") and `کفیل` ("acting") are Iran's
                # markers and are the commonest tier in the country: 67 rows on
                # the province lists, 96 on the ministry rosters, and the ones
                # that decide whether Alireza Kazemi's 2021 spell as Minister of
                # Education is the same tenure as his 2024 one. Written folded,
                # because that is what a flag carries.
                r"encargad|interin|subrogante|acting|в\.\s*а|и\.\s*о"
                r"|سرپرست|كفيل|کفیل|موقت",
                f, re.I,
            )
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
            rowspan = _span(cell, "rowspan")
            colspan = _span(cell, "colspan")
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


def _roles(
    header: List[Tuple[object, bool]],
    width: int,
    overrides: Tuple[Tuple[str, str], ...] = (),
) -> List[str]:
    roles: List[str] = []
    keys = _role_keys_with(overrides) if overrides else _role_keys()
    for index, (cell, _) in enumerate(header):
        text = _norm(cell.text_content()) if cell is not None else ""
        role = f"col{index}"
        for prefix, candidate in keys:
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


def _reads_as_header(
    row_cells: List[Tuple[object, bool]],
    width: int,
    overrides: Tuple[Tuple[str, str], ...] = (),
) -> bool:
    """Does this row name its columns rather than fill them?

    Some tables mark their header row up as plain `td` — es.wikipedia's
    defence-minister list does, and with no `th` anywhere the parser assigned no
    roles at all and dropped all 84 rows for want of a name column. Requiring
    two recognised column names keeps a genuine first data row from being eaten.
    """
    roles = _roles(row_cells, width, overrides)
    return sum(1 for role in roles if not role.startswith("col")) >= 2


def _subroles(
    roles: List[str],
    header: List[Tuple[object, bool]],
    overrides: Tuple[Tuple[str, str], ...] = (),
) -> List[str]:
    """Refine column roles from a second header row that subdivides the first.

    Reach for this wherever a wide header has its own sub-labels: cs.wikipedia
    heads three columns "Funkční období" and labels them "Nástup do úřadu",
    "Opuštění úřadu", "Dny v úřadu". Reading only the top row leaves the day
    count indistinguishable from the dates, and a plausible tenure of 1939 days
    then parses as the year 1939.

    A sub-label can itself span several columns, and it names every one of them
    — `ar:قائمة ولاة عهد الكويت` sub-heads its start *and* end cells with one
    "فترة تولي المنصب" beside a duration column. Refining only the spanning
    cell's own position left the end column unnamed and every crown prince
    open-ended, so continuation positions are refined too, exactly as `_roles`
    reads them. Re-applying a role a rowspanned cell already set is harmless.
    """
    out = list(roles)
    keys = _role_keys_with(overrides) if overrides else _role_keys()
    for index, (cell, _) in enumerate(header):
        if cell is None or index >= len(out):
            continue
        text = _norm(cell.text_content())
        for prefix, role in keys:
            if text == prefix or (len(prefix) >= 3 and text.startswith(prefix)):
                out[index] = role
                break
    return out


def _drop(element) -> None:
    """Remove an element but keep the text that follows it.

    lxml's `remove()` takes the element's tail with it, and the tail is where
    the visible value lives once a hidden sort key is dropped: `<span
    style="display:none">01812-06-12 </span>12 de junio de 1812` is one span
    whose *tail* is the date a reader sees.
    """
    parent = element.getparent()
    tail = element.tail or ""
    if tail:
        previous = element.getprevious()
        if previous is not None:
            previous.tail = (previous.tail or "") + tail
        else:
            parent.text = (parent.text or "") + tail
    parent.remove(element)


def _cell_text(cell, keep_breaks: bool = False) -> str:
    if cell is None:
        return ""
    clone = lxml_html.fromstring(lxml_html.tostring(cell))
    # Hidden sort keys are the trap here: `{{dts}}` renders a date cell as
    # `<span style="display:none">01812-06-12 </span>12 de junio de 1812`, and
    # the key's own hyphens then split the cell before its real dash does — the
    # term reads as starting in the year "01812" and ending on its own start.
    for junk in clone.xpath(
        ".//sup[contains(@class, 'reference')]|.//style|.//span[@typeof]"
        "|.//*[contains(translate(@style, ' ', ''), 'display:none')]"
    ):
        _drop(junk)
    if keep_breaks:
        # `<hr>` divides a cell as often as `<br>` does: the Spanish Senate's
        # list stacks a president's four sessions in one cell that way, and read
        # as a single line the four dates concatenate into "18 de nov. de
        # 18375 de nov. de 1838" — a term with year precision at best.
        for br in clone.xpath(".//br|.//hr"):
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


def _span(cell, attribute: str) -> int:
    """A cell's `rowspan`/`colspan` as a usable count.

    Hand-written wikitext puts things in these attributes that HTML does not
    allow: `ar:حاكم دبي` writes `colspan="100%"`, which read naively raises and
    took the whole page's parse down with it. Anything unreadable means one.
    """
    try:
        return max(1, int(cell.get(attribute, 1)))
    except (TypeError, ValueError):
        return 1


def _mostly_italic(cell) -> bool:
    """Is this cell's text italicised, rather than merely containing italics?

    A name followed by an italic parenthetical is not an italic name, so this
    asks what share of the cell the italic runs cover.
    """
    if cell is None:
        return False
    whole = " ".join((cell.text_content() or "").split())
    if not whole:
        return False
    italic = "".join(
        " ".join((element.text_content() or "").split())
        for element in cell.xpath(".//i|.//em")
    )
    return len(italic) >= 0.6 * len(whole)


def _lines(roles: List[str], row_cells: List[Tuple[object, bool]], role: str):
    """The first cell of this role and its text, split on line breaks."""
    for candidate, (cell, _) in zip(roles, row_cells):
        if candidate != role or cell is None:
            continue
        text = _cell_text(cell, keep_breaks=True)
        if text:
            return cell, [line for line in text.split("\n") if line]
    return None, []


def _spans(
    roles: List[str], row_cells: List[Tuple[object, bool]]
) -> List[Tuple[Optional[str], Optional[str], bool, str]]:
    """Every term a row's separate start and end cells describe.

    Usually one. But a roster listing a president's several non-consecutive
    terms writes them as stacked dates in the same two cells — the Spanish
    Senate's 19th-century presidents were elected afresh each session, so one
    row carries four start dates and four end dates. Read as single cells they
    concatenate into a number that is not a date at all; paired up they are four
    terms, which is what Wikidata records.
    """
    start_cell, starts = _lines(roles, row_cells, "start")
    end_cell, ends = _lines(roles, row_cells, "end")
    # One cell colspanning both columns holds a *range*, not a start repeated as
    # its own end — es.wikipedia writes Adolfo Suárez's royal designation that
    # way, and read as two cells it becomes a term that begins and ends on the
    # same day.
    if start_cell is not None and start_cell is end_cell:
        start, end, incumbent = parse_period(" ".join(starts))
        return [(start, end, incumbent, " ".join(starts))]
    if len(starts) > 1 and len(starts) == len(ends):
        stacked = [
            (
                parse_date(start),
                None if _incumbent(end) else parse_date(end),
                _incumbent(end),
                f"{start} – {end}",
            )
            for start, end in zip(starts, ends)
        ]
        # A pair that carries no date on either side is not a term. The stacking
        # here is meant for a holder with several separate spells, but the same
        # two cells also stack a *parenthetical* under the date:
        # `en:King of Saudi Arabia` writes "23 September 1932" over "(aged 57)"
        # and "9 November 1953" over "(death by natural causes)", so the second
        # lines pair up into a dateless phantom term — six of that page's
        # thirteen rows, one per king. They were harmless (the dated span wins
        # per person) but they doubled the audit and the backtest's denominator.
        dated = [term for term in stacked if term[0] or term[1] or term[2]]
        if dated:
            return dated
    start_text = " ".join(starts)
    end_text = " ".join(ends)
    incumbent = _incumbent(end_text)
    return [(
        parse_date(start_text) if start_text else None,
        None if incumbent or not end_text else parse_date(end_text),
        incumbent,
        f"{start_text} – {end_text}".strip(" –"),
    )]


def parse_rosters(
    page_html: str, column_roles: Tuple[Tuple[str, str], ...] = ()
) -> List[Roster]:
    """Every wikitable in a rendered list article, as roster rows.

    `column_roles` lets one page override the shared header vocabulary, for the
    case where a header string means two different things on two pages and no
    ordering of `COLUMN_ROLES` can separate them — see `_role_keys_with`.
    """
    doc = lxml_html.fromstring(page_html)
    legend = _legend(doc)
    notes = _footnotes(doc)
    # Read once for the whole page, not per row: the declaration is prose above
    # the table, and it licenses reading italics as an acting marker below it.
    declaration = ITALIC_ACTING.search(" ".join(doc.text_content().split()))
    italic_convention = declaration.group(0).strip() if declaration else None
    headings: Dict[object, Optional[str]] = {}
    current: Optional[str] = None
    for element in doc.iter("h1", "h2", "h3", "h4", "table"):
        if element.tag == "table":
            headings[element] = current
        else:
            text = " ".join(element.text_content().split())
            current = re.sub(r"\[\s*editar[^]]*\]", "", text).strip() or current
    rosters: List[Roster] = []
    # `sortable` alone occurs too: es.wikipedia's defence-minister list styles
    # its table with column classes and never names it a wikitable. And a real
    # roster may carry *no* class at all — ar:حاكم دبي tabulates five rulers of
    # Dubai in a bare `<table>` — so requiring `wikitable` skipped it silently.
    # The furniture is therefore refused by name rather than data being required
    # to announce itself; a table with no date column is dropped downstream, and
    # `office_rows` matches the section heading besides.
    for table in doc.xpath("//table"):
        classes = table.get("class") or ""
        if CHROME_CLASSES.search(classes):
            continue
        if classes.strip() and not TABLE_CLASSES.search(classes):
            continue
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
            is_header = all(cell.tag == "th" for cell, _ in origins) or (
                not roles and _reads_as_header(row_cells, width, column_roles)
            )
            spans_row = len(origins) == 1 and _span(origins[0][0], "colspan") >= width
            # A single cell spanning the whole table is a heading whether or not
            # it is marked up as one: es.wikipedia announces each reign and each
            # suppression of an office in a plain `td` ("Reinado de Juan Carlos
            # I", "Supresión del Senado como órgano constitucional"), and those
            # were being offered up as people. An unmarked full-width row can
            # also be an explanatory *note*, though — cs.wikipedia's labour list
            # explains a two-year gap in thirty words — and taking that for the
            # section overwrote the era heading the regime routing reads. A
            # heading is a label, so the word count is what separates them.
            if spans_row and (is_header or len(_cell_text(origins[0][0]).split()) <= 15):
                section = _cell_text(origins[0][0]) or section
                continue
            if is_header:
                roles = (
                    _subroles(roles, row_cells, column_roles)
                    if roles
                    else _roles(row_cells, width, column_roles)
                )
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
            links: Dict[str, List[str]] = {}
            for role, (cell, _) in zip(roles, row_cells):
                if cell is None:
                    continue
                for anchor in cell.xpath(".//a[@href]"):
                    title = anchor.get("title") or ""
                    if (
                        (anchor.get("href") or "").startswith("/wiki/")
                        and ":" not in title
                        and "mw-file" not in (anchor.get("class") or "")
                        and title not in links.setdefault(role, [])
                    ):
                        links[role].append(title)
            name_index = roles.index("name") if "name" in roles else 0
            # Every column the name header covers, then its neighbours: a
            # "Nombre" header can colspan a colour swatch, a portrait *and* the
            # name — searching only the first of them loses the linked cell, and
            # with it Wikipedia's own assertion of who this is. cs.wikipedia's
            # education list fills the *portrait* cell instead and leaves the
            # name cell empty, hence the neighbours. A date or a bare ordinal is
            # never a name, so such a candidate is skipped rather than taken —
            # otherwise the row is filed under "3. července 1992".
            name_cell = None
            name_is_new = False
            spanned = [i for i, role in enumerate(roles) if role == "name"]
            for offset in spanned + [name_index + 1, name_index - 1]:
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
            # The marker sits wherever the page puts it: beside the name, in the
            # notes, or — on the Iraqi cabinet tables — in the office cell, as
            # "وزارة الصحة (وكالة)". It says the same thing in all three.
            acting_text = (
                ACTING_TEXT.search(name)
                or ACTING_TEXT.search(cells.get("notes", ""))
                or ACTING_TEXT.search(cells.get("office", ""))
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
                incumbent = _incumbent(periods[1])
                if incumbent:
                    end = None
                spans = [(start, end, incumbent, " – ".join(periods[:2]))]
            elif periods:
                start, end, incumbent = parse_period(periods[0])
                spans = [(start, end, incumbent, periods[0])]
            else:
                spans = _spans(roles, row_cells)
            tr = trs[index] if index < len(trs) else None
            for start, end, incumbent, period_raw in spans:
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
                           if acting_text else [])
                        + ([
                            "acting, per the page's italic convention: "
                            + str(italic_convention)
                        ] if italic_convention and _mostly_italic(name_cell)
                           else []),
                        ref_urls=ref_urls,
                        cells=cells,
                        links=links,
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
    r"holders|list of"
    # Arabic. 74 of Iraq's 82 cabinet articles list their ministers as bullets
    # rather than tabulating them, under "التشكيلة الوزارية" (68), "تشكيلة
    # الوزارة" (21) or "التعديلات الوزارية" (4). With no Arabic here the
    # allowlist missed every one of them and the whole bullet half of the lane —
    # 1028 of 1372 rows — was skipped before anything else could go wrong.
    r"|تشكيل|وزراء|تعديلات"
    # Persian. Three lanes reported the same wall independently: with no Persian
    # here the heading gate skipped every fa bullet list before anything else
    # could go wrong — the twelve Majlis rolls, the 47 ambassador pages and five
    # of the six Assembly of Experts rolls. Written folded (`ی`→`ي`, `ک`→`ك`),
    # because the caller folds the heading before matching.
    r"|نمايندگان|سفيران|فهرست|اعضا|وزيران|فرماندهان|رييسان|روساي"
    r"|استانداران|مديران|نمايندگي"
    # The ambassador pages head their sections by *era* rather than by role.
    r"|جمهوري اسلامي|پهلوي|قاجاريه|مشروطه",
    re.I,
)
BULLET_NOT_HEADINGS = re.compile(
    r"заместител|намесн|заступник|ссылк|литератур|источник|примечан|"
    r"сноск|калегі|коллеги|deputy|see also|referen"
    # …and the Arabic sections that are apparatus rather than a roster, since a
    # cabinet article ends with several of them.
    r"|انظر\s+أيضا|مراجع|مصادر|وصلات\s+خارجية|بوابة",
    re.I,
)
#: "وزير المالية: [[رستم حيدر]]" — the office named before a colon, the holder
#: after it. 68 of the 74 Iraqi bullet cabinets write every row this way, and it
#: is what makes a *dateless* bullet identifiable as a roster row: the article
#: dates the whole government in its infobox (`RosterSource.term`), never the
#: row. Requiring a date, as every other bullet wiki's rows carry one, dropped
#: 920 rows that state an office and a person perfectly clearly.
#:
#: Capturing the office is the load-bearing half. `target_for` builds its
#: haystack from the row's section and its `office` cell, and a bullet has no
#: cells — so without this every row on a page shares one haystack (the page
#: heading) and a bucket lane cannot tell a foreign minister from a finance
#: minister.
#:
#: Opt-in per source (`RosterSource.bullet_offices`), because measured against
#: every prior bullet roster it is not safe by default. It admitted nine rows
#: from three Belarusian ministry articles whose "current leadership" bullets are
#: `Первый заместитель министра: [[Name]]` and `должность вакантна` — the deputy
#: marker sits in the *office* half, so stripping it off the name is exactly what
#: stops `DEPUTY_ROW` from seeing it — and on `en:Ministry of Foreign Affairs
#: (Qatar)`, whose bullets read `1989–1990: Ahmed bin Saif Al Thani`, it captured
#: the *date range* as the office and fed it to the routing haystack.
BULLET_OFFICE = re.compile(r"^\s*([^:：\[\]]{3,60}?)\s*[:：]\s*(?=\S)")
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
        # An abbreviated month is a month: es.wikipedia writes "17 de jul. de
        # 1834", and the stem rule below needs four characters to fire.
        if _deaccent(token) in MONTHS:
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


def parse_bullet_rosters(
    page_html: str, bullet_offices: bool = False, dateless: bool = False,
    person_first: bool = False, headings: Optional[str] = None,
) -> List[Roster]:
    """Officeholders listed as bullets rather than tabulated.

    Wikis outside the table-making habit write the same information as a list —
    ru.wikipedia's ministry articles run `* rank [[Name]] (16 июля 1990 —
    25 января 1994)<ref>` — and the ministry article is then the only roster
    an office has. Rows carry the same fields as table rows, so callers can
    treat both alike; `columns` is `["bullet"]` to mark the provenance.

    `bullet_offices` reads an office named ahead of a colon into the row's
    `office` cell, and lets a row with one carry no date. Both are what a bucket
    lane over bullets needs and neither is safe by default — see `BULLET_OFFICE`.

    `headings` replaces `BULLET_HEADINGS` for this page, and is the bullet
    counterpart of the `headings` a table source already carries: a caller who
    has read the page and knows every list on it is a roster can say so. Needed
    because the allowlist recognises a section by the *word* in its heading, and
    a roll sectioned alphabetically has letters — `fa:فهرست نمایندگان دوره نخست
    مجلس شورای اسلامی` heads its groups "آ، ا، ب، پ، ت، ث" and hid all 1,871
    members of the first eight Majlis terms. Extending the allowlist a fourth
    time (after Russian, Arabic and Persian) would fix this page and not the
    next one. `BULLET_NOT_HEADINGS` still applies: an override says the page is
    a roster, not that its references section is.
    """
    doc = lxml_html.fromstring(page_html)
    notes = _footnotes(doc)
    heading: Optional[str] = None
    rosters: List[Roster] = []
    # `ol` because `ar:وزارة ناجي شوكت` numbers its seven ministers with `#`
    # instead of bulleting them, which is the same list to a reader.
    for element in doc.iter("h1", "h2", "h3", "h4", "ul", "ol"):
        if element.tag not in ("ul", "ol"):
            text = " ".join(element.text_content().split())
            heading = re.sub(r"\[\s*(?:editar|edit|править|правіць)[^]]*\]", "", text).strip() or heading
            continue
        if element.getparent() is not None and element.getparent().tag in ("li", "table", "td"):
            continue  # nested list, or a navbox
        # Folded, per §7 #11: a pattern typed in the source spelling matches
        # nothing once Persian yeh and kaf fold to their Arabic code points.
        folded_heading = fold(heading) if heading else ""
        allowed = re.compile(headings, re.I) if headings else BULLET_HEADINGS
        if heading and (
            not allowed.search(folded_heading)
            or BULLET_NOT_HEADINGS.search(folded_heading)
        ):
            continue
        rows: List[RosterRow] = []
        for item in element.xpath("./li"):
            text = _cell_text(item)
            # The office named ahead of a colon, which is both this row's routing
            # key and its licence to carry no date of its own. A *date* ahead of
            # the colon is not an office — Qatar's foreign ministry bullets read
            # "1989–1990: Ahmed bin Saif Al Thani" — and a deputy's title there
            # must still disqualify the row, which is why `DEPUTY_ROW` is asked
            # about the office half as well as the name: stripping the marker off
            # the name is what would otherwise hide it.
            office_cell = None
            titled = BULLET_OFFICE.match(text) if bullet_offices else None
            if titled is not None and not _is_date_phrase(titled.group(1)):
                office_cell = " ".join(titled.group(1).split())
                if DEPUTY_ROW.match(office_cell):
                    continue
            else:
                titled = None
            # Leading dates win over trailing parentheses: a line that has both
            # ("1921 — Боркусевич (1892—1930)") states the term first and the
            # person's *lifespan* in the brackets.
            leading = BULLET_PERIOD_FIRST.match(text)
            if leading is not None and _is_date_phrase(leading.group(1)):
                period_text, name_text = leading.group(1), leading.group(2)
            else:
                period = BULLET_PERIOD.search(text)
                if period is None:
                    if office_cell is None and not dateless:
                        continue
                    period_text = ""
                    name_text = text[titled.end():] if titled is not None else text
                else:
                    period_text, name_text = period.group(1), text[: period.start()]
                    if office_cell is not None:
                        name_text = name_text[titled.end():]
            name_text = re.sub(r"\([^()]*\)\s*[;.,]*\s*$", " ", name_text)
            # A note can share the parentheses with the dates ("1963—1984;
            # министр автомобильного транспорта"); the term comes first.
            period_text = period_text.split(";")[0]
            acting_period = bool(ACTING_PREFIX.match(period_text))
            if acting_period:
                period_text = ACTING_PREFIX.sub("", period_text)
            anchors = [
                a for a in item.xpath(".//a[@href]")
                if (a.get("href") or "").startswith("/wiki/")
                and ":" not in (a.get("title") or "x")
                and not _is_date_link(a.get("title") or "")
            ]
            # Ranks and offices are linked ahead of the person ("генерал-майор
            # [[Name]]"), so the last link before the dates is the officeholder.
            # Persian rolls invert it: the Assembly of Experts rolls link the
            # *province* after the member and the Majlis rolls link the
            # electoral district, so `anchors[-1]` resolved every row on those
            # pages to a place. A page says which shape it is; guessing per row
            # is what put `استان تهران` in the officeholder column.
            link = None
            if anchors:
                link = (anchors[0] if person_first else anchors[-1]).get("title")
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
                    else (["acting, per the period cell"] if acting_period else []),
                    ref_urls=ref_urls,
                    cells=(
                        {"bullet": text, "office": office_cell}
                        if office_cell
                        else {"bullet": text}
                    ),
                )
            )
        if len(rows) >= 2:
            rosters.append(Roster(columns=["bullet"], rows=rows, heading=heading))
    return rosters


def _absorb_fragments(
    terms: List[Tuple[Optional[str], Optional[str]]]
) -> List[Tuple[Optional[str], Optional[str]]]:
    """Drop half-dated terms that a fully dated one already describes.

    A page that dates only its changes leaves a spell stated twice over: once as
    a start with no end, once as an end with no start. Where a complete term
    shares either bound, the fragment is that same term seen through a different
    section and adds nothing; emitted, it becomes a second P39 with half a date
    on it.
    """
    complete = [(s, e) for s, e in terms if s and e]
    dated = [(s, e) for s, e in terms if s or e]
    out = []
    for start, end in terms:
        if not start and not end:
            # A row that dates nothing is the middle cabinet of a spell whose
            # ends the sections either side of it carry. It is dropped only when
            # something dated survives, so an office whose every row is undated
            # still reaches the `no_dates` disposition instead of vanishing.
            if dated:
                continue
            out.append((start, end))
            continue
        if start and end:
            out.append((start, end))
            continue
        if start and any(s == start for s, _e in complete):
            continue
        if end and any(e == end for _s, e in complete):
            continue
        # A term with an end and no start of its own cannot begin a spell, so
        # beside any complete term for the same office it is a fragment of one.
        if end and not start and complete:
            continue
        out.append((start, end))
    return out


def merge_terms(rows: List[RosterRow]) -> List[Tuple[Optional[str], Optional[str]]]:
    """Collapse a person's consecutive roster rows into continuous terms.

    Rosters split a single uninterrupted spell into several rows whenever
    something *else* changes — a new appointing president, a ministry rename —
    and each split would otherwise become a spurious extra P39 statement.

    The hard case is a page that prints **one section per cabinet and dates only
    the changes**, which `en:List of cabinets of the United Arab Emirates` does.
    A minister serving three cabinets appears three times: with a start, with
    nothing, and with an end. Read as three rows that is one spell arriving in
    *fragments* — and a fragment is worse than a duplicate, because a lone `P580`
    and a lone `P582` are two statements neither of which is true. Nine UAE
    ministers shipped that way; QuickStatements' habit of merging by
    subject/property/value quietly reassembled them, which is the only reason it
    went unnoticed for a month (`wd/validate.py:conflicting_tenures`).

    So a row with no start of its own does not begin a term here: it continues
    the one the earlier section opened, and its end closes it.
    """
    terms: List[Tuple[Optional[str], Optional[str]]] = []
    previous: Optional[RosterRow] = None
    seen: set = set()
    # Ordered by whichever bound the row actually has. Keyed on `start` alone, a
    # row carrying only an end sorted to the very front — before the row whose
    # start it closes — and the two could never be paired up.
    for row in sorted(rows, key=lambda r: (r.start or r.end or "", r.ordinal)):
        if (row.start, row.end, row.acting) in seen:
            continue  # two rows describing one term, e.g. a rowspan restatement
        seen.add((row.start, row.end, row.acting))
        open_term = bool(terms) and terms[-1][0] is not None and terms[-1][1] is None
        continuous = (
            previous is not None
            and previous.acting == row.acting
            and previous.end is not None
            and previous.end == row.start
        )
        continues_open = (
            open_term
            and row.start is None
            and previous is not None
            and previous.acting == row.acting
        )
        if (continuous or continues_open) and terms:
            terms[-1] = (terms[-1][0], row.end or terms[-1][1])
        else:
            terms.append((row.start, row.end))
        previous = row
    return _absorb_fragments(terms)


def name_tokens(name: str) -> List[str]:
    """Comparable name tokens: accent-free, lowercased, no parenthetical."""
    cleaned = re.sub(r"\(.*?\)", " ", name)
    cleaned = re.sub(r"[^\w\s]", " ", _deaccent(cleaned))
    #: Honorifics and nobiliary particles carry no identity. The Gulf ones are
    #: load-bearing rather than cosmetic: every one of the 93 name cells on the
    #: emirate ruler list is prefixed "Sheikh", so left in they are a token every
    #: ruler shares, and the two-token floor that stops "every Juan matching
    #: every other" would be met by the honorific plus one given name.
    stop = {"de", "del", "la", "las", "los", "y", "e", "da", "dos", "san",
            "sheikh", "shaikh", "sheik", "sheikha", "shaikha", "hh", "hrh",
            "الشيخ", "الشيخه", "شيخ", "بن", "بنت", "ال", "آل", "بين"}
    return [t for t in cleaned.casefold().split() if t and t not in stop]


#: Arabic patronymic connectors. Their presence flips name matching from
#: order-blind to order-sensitive, because in a patronymic the order *is* the
#: identity — see `names_match`.
PATRONYMIC = re.compile(r"\b(?:bin|ibn|bint|binti)\b|بن\b|بنت\b", re.I)
#: A regnal ordinal, which is the only thing distinguishing three Rulers of
#: Ajman who otherwise share every token.
REGNAL = re.compile(r"^(?:i{1,3}|iv|vi{0,3}|ix|xi{0,2})$", re.I)


def names_match(left: str, right: str) -> bool:
    """True when two spellings of a person's name can be the same person.

    Spellings differ in ways that are systematic per language and would each
    need their own rule: Spanish rosters carry more surnames than the article
    title ("Sandra Vela" vs "Sandra Vela Dávila"), Russian ones flip the order
    and add a patronymic ("Киселёв, Кузьма Венедиктович" vs "Кузьма Киселёв").
    Token subset covers all of them; the floor of two shared tokens is what
    stops every "Juan" matching every other.

    **A patronymic name is compared in order, and its regnal number must
    agree.** An Arabic patronymic reverses under inheritance, so as token
    *sets* a man and his father are indistinguishable: "Rashid bin Humaid Al
    Nuaimi" and "Humaid bin Rashid Al Nuaimi" are two different Rulers of
    Ajman, and Ajman also had a Rashid bin Humaid I, II and III. Both extra
    conditions are gated on the connector being present, so a Spanish or
    Slavic roster — which needs the order-blind comparison to work at all —
    reaches exactly the same verdict as before.
    """
    left_tokens, right_tokens = name_tokens(left), name_tokens(right)
    a, b = set(left_tokens), set(right_tokens)
    if len(a) < 2 or len(b) < 2:
        return False
    if PATRONYMIC.search(left) or PATRONYMIC.search(right):
        if {t for t in left_tokens if REGNAL.match(t)} != {
            t for t in right_tokens if REGNAL.match(t)
        }:
            return False
        shorter, longer = sorted((left_tokens, right_tokens), key=len)
        return longer[: len(shorter)] == shorter
    return a <= b or b <= a
