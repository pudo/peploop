#!/usr/bin/env python
"""P39 for Jordan's ministers, prime ministers and presiding officers.

    python scripts/jo_offices.py
    python scripts/jo_offices.py --office cabinet senate_president

The office half of the Jordan campaign; the Hashemite kinship lane is
`scripts/jo_family.py` and the method is `recipes/country_sweep.md`. The survey
this was written from is `plans/jordan_sweep.md`.

Five things about this country are specific enough to spell out.

* **The cabinet lane is 98 articles, not one roster.** Jordan keeps an article
  per government — `Category:حكومات الأردن`, 108 of them — and no per-portfolio
  list article exists in either language. Each cabinet's article tabulates its
  own ministers, so the lane is one `Office` with 98 sources routed by the
  portfolio cell.

* **Only two of those 108 date their rows.** The two most recent use
  `تولى المنصب`/`غادر المنصب`; the other 106 print a bare
  `الاسم ¦ المهام الوزارية` and date nothing. What dates them is the article's
  own infobox — `التكوين` and `النهاية` — which is the §7 #29 shape: the page
  *is* one term. `CABINETS` below carries those 98 spans, and `RosterSource.term`
  applies each only to rows that parsed no date of their own, so the two dated
  articles keep what they say. `merge_terms` then folds a minister who served
  four consecutive governments into one continuous tenure rather than four.

* **The portfolio cell is written in the accusative.** "وزيرا للزراعة", not
  "وزير الزراعة", and across a century of articles it appears in 630 distinct
  spellings of about fifty portfolios. `PORTFOLIOS` therefore matches on the
  portfolio's *stem* rather than on a title, and `section_targets` puts both the
  raw and the folded cell in the haystack, so a natural spelling matches.

* **The defence portfolio has no item and usually has no minister.** The
  commonest single cell in the whole corpus is "رئيسا للوزراء ووزيرا للدفاع" —
  the prime minister holding defence himself, 22 times. It routes to the
  premiership, which is why that pattern precedes the defence one.

* **Two portfolios have two items each.** Labour is Q110066504 and Q133851928,
  water Q110065394 and Q137704254; each pair competes for the same era rather
  than succeeding one another, so this routes to the better-attested of each and
  the merge goes to `tasks/followups.md`. It is a merge decision, not a campaign.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.campaign import Campaign, Office, RosterSource, run
from wd.http import REPO_ROOT, make_session

OUT_DIR = REPO_ROOT / "data" / "jordan"
#: `office_rows` reads `source.headings or DEFAULT_HEADINGS`, so an empty string
#: would silently swap the default back in (§7 #23).
ANY_TABLE = r".*"

#: Every government with a formation date in its infobox, oldest first, as
#: (article, start, end). Ten of the 108 articles state no formation date and
#: are left out: with no term and no dated rows there is nothing to record.
#: The four 1920 "local governments" predate the Emirate and are kept because
#: `modern_from` and the targets' own precedent decide them, not this list.
CABINETS = (
    ("حكومة الرمثا المحلية", "1920-09-02", "1921-04-11"),
    ("حكومة السلط المحلية", "1920-09-15", "1921-04-11"),
    ("حكومة الكرك المحلية", "1920-09-15", "1921-04-11"),
    ("حكومة الكورة المحلية", "1920-09-15", "1921-04-11"),
    ("حكومة رشيد طليع الأولى", "1921-04-11", "1921-06-23"),
    ("حكومة رشيد طليع (الثانية)", "1921-07-05", "1921-08-05"),
    ("حكومة مظهر رسلان الأولى", "1921-08-15", "1922-03-10"),
    ("حكومة علي رضا الركابي الأولى", "1922-03-10", "1923-01-28"),
    ("حكومة مظهر رسلان الثانية", "1923-02-01", "1923-09-01"),
    ("حكومة حسن خالد أبو الهدى الأولى", "1923-09-05", "1924-05-07"),
    ("حكومة علي رضا الركابي الثانية", "1924-05-03", "1926-06-23"),
    ("حكومة حسن خالد أبو الهدى الثانية", "1926-06-26", "1929-10-17"),
    ("حكومة حسن خالد أبو الهدى الثالثة", "1929-10-17", "1931-02-21"),
    ("حكومة عبد الله سراج", "1931-02-22", "1933-10-18"),
    ("حكومة إبراهيم هاشم الأولى", "1933-10-18", "1938-09-27"),
    ("حكومة توفيق أبو الهدى الأولى", "1938-09-28", "1939-08-06"),
    ("حكومة توفيق أبو الهدى الثانية", "1939-08-06", "1940-09-24"),
    ("حكومة توفيق أبو الهدى الثالثة", "1940-09-25", "1941-07-27"),
    ("حكومة توفيق أبو الهدى الرابعة", "1941-07-29", "1943-05-18"),
    ("حكومة توفيق أبو الهدى الخامسة", "1943-05-19", "1944-10-14"),
    ("حكومة سمير الرفاعي الأولى", "1944-10-15", "1945-05-18"),
    ("حكومة إبراهيم هاشم الثانية", "1945-05-19", "1947-02-01"),
    ("حكومة سمير الرفاعي الثانية", "1947-02-04", "1947-12-27"),
    ("حكومة توفيق أبو الهدى السادسة", "1947-12-28", "1949-05-03"),
    ("حكومة توفيق أبو الهدى السابعة", "1949-05-07", "1950-04-12"),
    ("حكومة سعيد المفتي الأولى", "1950-04-12", "1950-10-11"),
    ("حكومة سعيد المفتي الثانية", "1950-10-14", "1950-12-04"),
    ("حكومة سمير الرفاعي الثالثة", "1950-12-04", "1951-07-25"),
    ("حكومة توفيق أبو الهدى الثامنة", "1951-07-25", "1951-09-07"),
    ("حكومة توفيق أبو الهدى التاسعة", "1951-09-08", "1952-09-27"),
    ("حكومة توفيق أبو الهدى العاشرة", "1952-09-07", "1953-05-05"),
    ("حكومة فوزي الملقي", "1953-05-05", "1954-05-02"),
    ("حكومة توفيق أبو الهدى الحادية عشرة", "1954-05-04", "1954-10-21"),
    ("حكومة توفيق أبو الهدى الثانية عشرة", "1954-10-24", "1955-05-28"),
    ("حكومة سعيد المفتي الثالثة", "1955-05-30", "1955-12-15"),
    ("حكومة هزاع المجالي الأولى", "1955-12-15", "1955-12-20"),
    ("حكومة إبراهيم هاشم الثالثة", "1955-12-21", "1956-01-07"),
    ("حكومة سمير الرفاعي الرابعة", "1956-01-09", "1956-05-20"),
    ("حكومة سعيد المفتي الرابعة", "1956-05-22", "1956-06-26"),
    ("حكومة إبراهيم هاشم الرابعة", "1956-07-01", "1956-10-27"),
    ("حكومة حسين الخالدي", "1957-04-15", "1957-04-24"),
    ("حكومة إبراهيم هاشم الخامسة", "1957-04-24", "1958-05-18"),
    ("حكومة سمير الرفاعي الخامسة", "1958-05-18", "1959-05-05"),
    ("حكومة هزاع المجالي الثانية", "1959-05-06", "1960-08-28"),
    ("حكومة بهجت التلهوني الأولى", "1960-08-29", "1961-06-28"),
    ("حكومة بهجت التلهوني الثانية", "1961-06-28", "1962-01-27"),
    ("حكومة وصفي التل الأولى", "1962-01-28", "1962-12-02"),
    ("حكومة وصفي التل الثانية", "1962-12-02", "1963-03-07"),
    ("حكومة سمير الرفاعي السادسة", "1963-03-27", "1963-04-21"),
    ("حكومة حسين بن ناصر الأولى", "1963-04-21", "1963-07-09"),
    ("حكومة حسين بن ناصر الثانية", "1963-07-09", "1964-07-06"),
    ("حكومة بهجت التلهوني الثالثة", "1964-07-06", "1965-02-14"),
    ("حكومة وصفي التل الثالثة", "1965-02-13", "1965-12-22"),
    ("حكومة وصفي التل الرابعة", "1966-12-22", "1967-03-04"),
    ("حكومة حسين بن ناصر الثالثة", "1967-03-04", "1967-04-23"),
    ("حكومة سعد جمعة الأولى", "1967-04-23", "1967-08-01"),
    ("حكومة سعد جمعة الثانية", "1967-08-02", "1967-10-07"),
    ("حكومة بهجت التلهوني الرابعة", "1967-10-07", "1969-03-24"),
    ("حكومة عبد المنعم الرفاعي الأولى", "1969-03-24", "1969-08-13"),
    ("حكومة بهجت التلهوني الخامسة", "1969-08-13", "1970-04-19"),
    ("حكومة بهجت التلهوني السادسة", "1970-04-19", "1970-06-27"),
    ("حكومة عبد المنعم الرفاعي الثانية", "1970-06-27", "1970-09-16"),
    ("حكومة محمد داوود", "1970-09-16", "1970-09-24"),
    ("حكومة أحمد طوقان", "1970-09-26", "1970-10-28"),
    ("حكومة وصفي التل الخامسة", "1970-10-28", "1971-11-28"),
    ("حكومة أحمد اللوزي الأولى", "1971-11-29", "1972-08-21"),
    ("حكومة أحمد اللوزي الثانية", "1972-08-21", "1973-05-26"),
    ("حكومة زيد الرفاعي الأولى", "1973-05-26", "1974-11-23"),
    ("حكومة زيد الرفاعي الثانية", "1974-11-23", "1976-02-08"),
    ("حكومة زيد الرفاعي الثالثة", "1976-02-08", "1976-07-13"),
    ("حكومة مضر بدران الأولى", "1976-07-13", "1976-11-27"),
    ("حكومة مضر بدران الثانية", "1976-11-27", "1979-12-19"),
    ("حكومة عبد الحميد شرف", "1979-12-19", "1980-07-03"),
    ("حكومة قاسم الريماوي", "1980-07-03", "1980-08-28"),
    ("حكومة مضر بدران الثالثة", "1980-08-28", "1984-01-10"),
    ("حكومة أحمد عبيدات", "1984-01-10", "1985-04-04"),
    ("حكومة عبد الكريم الكباريتي", "1996-02-04", "1997-03-19"),
    ("حكومة عبد السلام المجالي الثانية", "1997-03-19", "1998-08-20"),
    ("حكومة عبد الرؤوف الروابدة", "1999-03-04", "2000-06-18"),
    ("حكومة علي أبو الراغب الأولى", "2000-06-19", "2002-01-14"),
    ("حكومة علي أبو الراغب الثانية", "2002-01-14", "2003-07-20"),
    ("حكومة علي أبو الراغب الثالثة", "2003-07-21", "2003-10-22"),
    ("حكومة فيصل الفايز", "2003-10-25", "2005-04-05"),
    # Its own infobox states no end. The successor's formation is the end, as
    # attested as the start — and left open it made every minister who served
    # here look like one unbroken tenure running into their next portfolio,
    # which `validate.collapsing_groups` refuses outright.
    ("حكومة عدنان بدران", "2005-04-07", "2005-11-27"),
    ("حكومة معروف البخيت الأولى", "2005-11-27", "2007-11-22"),
    ("حكومة نادر الذهبي", "2007-11-25", "2009-12-09"),
    ("حكومة سمير زيد الرفاعي الأولى", "2009-12-14", "2010-11-22"),
    ("حكومة سمير زيد الرفاعي الثانية", "2010-11-24", "2011-02-01"),
    ("حكومة معروف البخيت الثانية", "2011-02-09", "2011-10-17"),
    ("حكومة عون الخصاونة", "2011-10-24", "2012-04-26"),
    ("حكومة فايز الطراونة الثانية", "2012-05-02", "2012-10-10"),
    ("حكومة عبد الله النسور الأولى", "2012-10-11", "2013-03-30"),
    ("حكومة عبد الله النسور الثانية", "2013-03-30", "2016-05-29"),
    ("حكومة هاني الملقي الأولى", "2016-06-01", "2016-09-25"),
    ("حكومة هاني الملقي الثانية", "2016-09-28", "2018-06-14"),
    ("حكومة عمر الرزاز", "2018-06-04", "2020-10-12"),
    ("حكومة بشر الخصاونة", "2020-10-12", "2024-09-15"),
    # The sitting cabinet is deliberately absent, as Kuwait's was. Its article
    # is the one that dates a minister from their *original* appointment rather
    # than from this government's formation — Wesam Al Tahtamouni appears here
    # as 2023-09-26 – 2025-08-06 and in Khasawneh's as 2023-09-26 – 2024-09-15,
    # one continuous tenure told twice, which `collapsing_groups` refuses and no
    # rule can resolve without picking a source. It is a deferred lane in
    # `tasks/followups.md`, not a row anyone decided.
    #   ("حكومة جعفر حسان", "2024-09-18", None),
)

#: Portfolio cell → position item, first match wins, so the specific precede the
#: general. Written on bare stems rather than on titles: the cells are accusative
#: with the definite article fused to a preposition — "وزيرا للعدل" contains
#: "للعدل" and never "العدل" — and a pattern carrying the article matched none of
#: the 630 spellings this corpus uses. That mistake left 433 rows unrouted.
#:
#: Rule order is load-bearing twice over. The deputy premiership precedes the
#: premiership because "نائبا لرئيس الوزراء" contains "رئيس الوزراء" and 66
#: deputies were reading as prime ministers; and each minister *of state* pattern
#: is anchored on "دولة" so that "وزيرا للمالية والشؤون الاقتصادية" stays with
#: finance instead of being claimed by the economic-affairs portfolio.
#:
#: An empty QID means no item exists for this portfolio: those rows become the
#: item-creation byproduct rather than being filed under whichever ministry
#: happens to be nearest (§2a — never map an unproven rename). The combined
#: municipal/rural/environment ministry is deliberately one of them.
PORTFOLIOS = (
    # The premiership first: its commonest cell also names the defence
    # portfolio, and the prime minister is who held it.
    (r"نائب.{0,3}رئيس|نائبا لرئيس|نائب.{0,3}الرئيس", "Q113330973"),
    # The premiership is deliberately *not* routed here. The `prime_minister`
    # office owns it from `ar:رئيس وزراء الأردن`, which dates the premiership
    # directly; a cabinet's infobox dates the government, and the two differ by
    # a day often enough that both lanes emitting produced one tenure with two
    # ends — which no write path can reconcile. Matching it and sending it
    # nowhere is what keeps it out of the other portfolios' patterns.
    (r"رئيس.{0,3}الوزراء|رئيس.{0,3}للوزراء|رئيسا للوزراء|رئيس.{0,3}النظار", ""),
    # Ministers of state, before the bare "وزير دولة" that would swallow them.
    (r"رئاسة ?الوزراء|رئاسةوزراء|شؤون رئاسة", "Q110067963"),
    
    (r"دولة .{0,3}شؤون الإعلام|دولة .{0,3}شؤون الاعلام", "Q55498292"),
    (r"دولة .{0,8}المرأة", "Q116765650"),
    (r"دولة .{0,8}الشؤون الاقتصادية", "Q113330970"),
    (r"تطوير القطاع العام|القطاع العام|الأداء المؤسسي", "Q110257014"),
    (r"متابعة أداء|المتابعة والتنسيق|مراقبة الاداء|مراقبة الأداء", "Q110067973"),
    # Portfolios, by stem. Written without the definite article because the
    # cells fuse it to a preposition — "وزيرا للعدل" has "للعدل", never "العدل".
    (r"خارجي", "Q20716373"),
    (r"داخلي", "Q110065338"),
    (r"عدل|عدلي", "Q110067612"),
    (r"قانوني", "Q110068001"),
    (r"مالي", "Q110067022"),
    (r"تعليم العال|التعليم العال", "Q110065430"),
    (r"تربي", "Q54810595"),
    (r"صح[ةه]|صحي", "Q110067245"),
    (r"زراع", "Q106785048"),
    (r"اشغال|أشغال", "Q105620514"),
    (r"ثقاف", "Q58488702"),
    (r"مياه|ري[ّ]?\b", "Q110065394"),
    (r"تنمية اجتماعية|تنمي[ةه] الاجتماعي", "Q58335451"),
    (r"عمل\b|لعمل", "Q110066504"),
    (r"شؤون البلدية|الشؤون البلدي", ""),
    (r"بيئ|بيي", "Q110066643"),
    (r"سياح|آثار|اثار", "Q110066878"),
    (r"صناع", "Q25058330"),
    (r"طاق", "Q110066267"),
    (r"اوقاف|أوقاف", "Q110066975"),
    (r"شباب والرياض", "Q55679943"),
    (r"شباب", "Q110067108"),
    (r"اقتصاد رقمي|الاقتصاد الرقمي", "Q110067675"),
    (r"تكنولوجيا المعلومات|اتصالات وتكنولوجيا", "Q110257013"),
    (r"اتصال الحكومي|الاتصال الحكومي", "Q115075491"),
    (r"إدارة محلية|ادارة محلية|الادارة المحلية|الإدارة المحلية", "Q110066853"),
    (r"استثمار", "Q110066808"),
    (r"سياسية والبرلمانية|السياسية والبرلمانية", "Q110066895"),
    (r"برلماني", "Q119150174"),
    (r"أرض المحتلة|ارض المحتلة|الأرض المحتلة", "Q136223044"),
    (r"نقل", "Q110065361"),
    (r"إعلام|اعلام", "Q108307110"),
    # The bare minister of state, last of the ones that resolve.
    (r"وزير.{0,3}دول[ةه]|وزيرا للدول[ةه]", "Q113330996"),
    (r".", ""),
    # Empty, not ".": a row whose office cell is blank has an empty haystack,
    # which "." does not match, and it fell through to `Office.target` — so 57
    # blank cells were filed as ministers of state, 39 of them prime ministers
    # and 18 of them the King. An empty pattern matches the empty string too.
    (r"", ""),
)

MINISTER_CATEGORIES = (
    ("ar", "وزراء أردنيون"),
    ("ar", "وزراء خارجية أردنيون"), ("ar", "وزراء داخلية أردنيون"),
    ("ar", "وزراء مالية أردنيون"), ("ar", "وزراء عدل أردنيون"),
    ("ar", "وزراء صحة أردنيون"), ("ar", "وزراء زراعة أردنيون"),
    ("ar", "وزراء تربية وتعليم أردنيون"), ("ar", "وزراء ثقافة أردنيون"),
    ("ar", "وزراء عمل أردنيون"), ("ar", "وزراء إعلام أردنيون"),
    ("ar", "وزراء أشغال عامة أردنيون"), ("ar", "وزراء نقل ومواصلات أردنيون"),
    ("ar", "وزراء طاقة أردنيون"), ("ar", "وزراء بيئة أردنيون"),
    ("ar", "وزراء سياحة أردنيون"), ("ar", "وزراء تخطيط أردنيون"),
    ("ar", "وزراء دولة أردنيون"), ("ar", "وزراء أوقاف أردنيون"),
    ("ar", "وزراء تنمية اجتماعية أردنيون"), ("ar", "وزراء مياه أردنيون"),
    ("ar", "وزراء شباب أردنيون"), ("ar", "وزراء اقتصاد أردنيون"),
    ("ar", "وزراء استثمار أردنيون"), ("ar", "وزراء اتصالات أردنيون"),
    ("ar", "وزراء تعليم عالي أردنيون"), ("ar", "وزراء صناعة وتجارة أردنيون"),
    ("ar", "وزيرات أردنيات"),
    ("en", "Government ministers of Jordan"),
)

OFFICES = (
    # Lane A — the throne.
    Office("king", "King of Jordan", "Q14625123",
           rosters=(RosterSource("en", "List of kings of Jordan",
                                 headings=ANY_TABLE),),
           categories=(("en", "Kings of Jordan"), ("ar", "ملوك الأردن"))),

    # Lane B — the government.
    Office("prime_minister", "Prime Minister of Jordan", "Q7243300",
           # The Arabic office article only. `en:List of prime ministers of
           # Jordan` tabulates the same 78 premierships and disagrees with it by
           # a day or two on seven end dates — two sources dating one tenure,
           # which arrives as two statements that no write path can reconcile
           # (`validate.collapsing_groups` refused the batch over it). The
           # second channel is the category, which does not date anything.
           rosters=(RosterSource("ar", "رئيس وزراء الأردن", headings=ANY_TABLE),),
           categories=(("ar", "رؤساء وزراء الأردن"),
                       ("en", "Prime ministers of Jordan"))),
    # The target is the fallback only: `PORTFOLIOS` routes every row, and its
    # catch-all sends an unmapped portfolio to "" rather than here. It has to be
    # a real item all the same, or `run()` reads the office as one awaiting
    # creation and proposes nothing at all.
    Office("cabinet", "Government of Jordan", "Q113330996",
           rosters=tuple(
               RosterSource("ar", page, headings=ANY_TABLE, term=(start, end))
               for page, start, end in CABINETS
           ),
           section_targets=PORTFOLIOS,
           categories=MINISTER_CATEGORIES),

    # Lane C — the parliamentary presiding offices, which are where the
    # legislature's yield is: the seats themselves have no roster (see the
    # module docstring of `plans/jordan_sweep.md`).
    Office("speaker", "Speaker of the House of Representatives", "Q105531070",
           rosters=(RosterSource("ar", "قائمة رؤساء مجلس النواب الأردني",
                                 headings=ANY_TABLE),),
           categories=(("ar", "رؤساء مجلس النواب الأردني"),)),
    Office("senate_president", "President of the Senate of Jordan", "Q6594880",
           rosters=(RosterSource("ar", "مجلس الأعيان الأردني",
                                 headings=ANY_TABLE),),
           categories=(("ar", "رؤساء مجلس الأعيان الأردني"),)),
    Office("senator", "Senator of Jordan", "Q20081407",
           rosters=(RosterSource(
               "ar", "قائمة أعضاء مجلس الأعيان الأردني السابع والعشرين",
               headings=ANY_TABLE, term=("2020-10-27", "2024-09-15")),),
           categories=(("ar", "أعضاء مجلس الأعيان الأردني"),)),
)

CAMPAIGN = Campaign(
    name="jordan",
    country_qid="Q810",
    #: Independence and the Kingdom. The Emirate of Transjordan (1921) and the
    #: 1920 local governments are earlier polities; no rule here decides them,
    #: each target's own record does (`early.precedent_ok` / `early.unsupported`).
    modern_from=1946,
    offices=OFFICES,
    label_langs=("en", "ar"),
    sibling_wikis=("ar", "en"),
    evidence_verb="lists them in the office",
    dispositions={
        "namesake": "skip", "predecessor_body": "skip", "category_only": "skip",
        "no_dates": "skip", "believed.held": "skip", "uncertain": "skip",
    },
    #: A seat and a portfolio overlap legitimately, and a Jordanian prime
    #: minister routinely holds defence or foreign affairs at the same time.
    concurrency_ignore=(
        "Q7243300", "Q113330973", "Q20081407", "Q17524418",
        "Q14625123", "Q105531070", "Q6594880", "Q113330996",
    ),
    #: The bare "Minister of State", whose proposals are redundant beside a
    #: specific portfolio's.
    generic_targets=("Q113330996",),
    extra_verdicts=("jordan_family.jsonl",),
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--office", nargs="*", default=None,
                        help="Office keys to run (default: all)")
    args = parser.parse_args()
    run(make_session(), CAMPAIGN, OUT_DIR, keys=args.office)


if __name__ == "__main__":
    main()
