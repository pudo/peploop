#!/usr/bin/env python
"""Propose P39 statements for Iraq, federal and subnational.

    python scripts/iq_offices.py --office justice cabinet governor_nineveh

The country parameters for `wd/campaign.py`; the method is
`recipes/country_sweep.md` and `plans/iraq_sweep.md` records what the survey
measured. Iraq is the first country this workbench has swept that is both badly
covered *and* richly sourced, and five things about it shaped everything below.

* **Its rosters existed all along and were not being read.** 106 position items
  carry `P17 = Q796` between 781 holder links, but `ar.wikipedia` tabulates far
  more than that — and almost every table dated its rows in Levantine month
  names (`12 حزيران 1948`) and separated them with the word `إلى` rather than a
  dash, neither of which `wd/roster.py` knew. The defence ministry's four era
  tables parsed 38 ministers with **zero dates and no error**. The parser change
  that fixed it is pinned by `scripts/check_dates.py` and was measured to change
  nothing in any of the nine campaigns that came before.

* **The era question is answered per *item*, never per country.** Justice's
  Kingdom-era bench is not `Q106964104` — none of its seven dated statements
  predates 1958, and Iraq's whole 1921–58 justice bench sits on the cross-country
  generic `Q17763739` — so that era is declared distinct and files as a creation
  byproduct. Defence's Kingdom-era ministers *are* `Q22690703`, which records
  nine of them. Two portfolios in one country, opposite answers, both measured.
  Hence `continuous_eras = ()`: naming the Kingdom there would route all 77
  Kingdom rows through `early.unsupported` and skip the ones the items support.

* **The cabinet lane is the only channel ~22 portfolios have.** Five of Iraq's
  27 ministry articles carry a dated roster; the rest carry none. What covers
  them is 82 `ar:وزارة <PM>` / `حكومة <PM>` articles, each dating itself in its
  own infobox and listing its ministers — 74 of them as bullets, which is why
  `RosterSource.bullet_offices` exists. These dates are the **government's**
  span, not the tenure's, and the backtest says so; 222 of 1,372 rows carry a
  note that the source itself says is not a full-government tenure.

* **Three cabinets are deliberately absent.** `حكومة علي فالح الزيدي` is the
  sitting one (§7 #35). `حكومة محمد شياع السوداني` dates its own rows and so
  never receives `term`'s end, which would ship 24 ministers of a *closed*
  government as open-ended. `حكومة حيدر العبادي` stacks two holders inside one
  name cell with their own `(2014-2016)` spans, so the survivor would take the
  whole government's span — a date the source disproves, which is worse than a
  coarse one.

* **A type filter would have rejected the head of state.** `Q889817` President of
  Iraq carries `P31 = Q248577` and nothing under the `Q4164871` closure, and
  `Q61905369` member of the Kurdistan Parliament carries the *trans-national*
  Kurdistan in `P1001`. Both are invisible to the obvious census. §2 of the
  recipe says to use the census to find items and never to reject them, and Iraq
  is where that earns its place twice in one run.

Lane E — the sixteen monarchy-era Chamber of Deputies rolls, the Senate, and the
1924 constituent assembly — is not here: all five of its offices need items that
do not exist, so it is a creation lane first and `scripts/iq_legislature.py`
after. What it would contribute today is 1,129 redlinks and 389 spells with
nowhere to put them.
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.campaign import Campaign, Office, RosterSource, run
from wd.http import REPO_ROOT, make_session

OUT_DIR = REPO_ROOT / "data" / "iraq"

#: Truthy, unlike `r""`, which `office_rows` silently replaces with
#: `DEFAULT_HEADINGS` — and none of Iraq's Arabic headings match that.
ANY_TABLE = r".*"

#: The bucket lane's second channel. `ar` carries 201 members against `en`'s
#: nine, which is the recipe's "expect the home-language wiki to be the primary
#: channel" in one line.
MINISTER_CATEGORIES = (("ar", "وزراء عراقيون"),
                       ("en", "Government ministers of Iraq"))

#: The 2003–2004 section both en spine pages carry, and the only place in Lane A
#: where the roster's own sectioning does not map onto one item. On the PM list
#: it is the Iraqi Governing Council's rotating monthly presidency (Q75611179,
#: whose P571 is that section's first row to the day); on the president list it
#: is the occupying authority — Garner and Bremer, who held no Iraqi office and
#: are routed to no item at all.
CPA_IGC = r"coalition provisional authority|iraqi governing council"

#: The Kurdistan Region's executive labels, spelled once. `en.wikipedia` and the
#: items disagree about "Kurdistan Region" against "Iraqi Kurdistan"; these
#: follow the items' own English labels where they have one.
KRG_PRESIDENT = "President of the Kurdistan Region"
KRG_PM = "Prime Minister of the Kurdistan Region"
KRG_DPM = "Deputy Prime Minister of the Kurdistan Region"
KRG_VP = "Vice President of the Kurdistan Region"
KRG_SPEAKER = "Speaker of the Kurdistan Parliament"


PORTFOLIOS = (
    # A. a portfolio cell that also names the deputy premiership: the portfolio wins.
    (r"الخارجيةالنائب|النائب الأول لرئيس", "Q6895071"),
    (r"النفطالنائب|نائب رئيس مجلس الوزراء - وزير النفط", "Q55691802"),
    (r"التخطيطالنائب", "Q55691776"),
    # B. the deputy premiership, before the premiership it contains.
    (r"نائب.{0,4}رئيس.{0,4}(الوزراء|مجلس الوزراء)|نواب رئيس الوزراء", "Q20423494"),
    # C. offices other lanes own. Matched, and sent nowhere.
    (r"رئيس.{0,4}(الوزراء|مجلس الوزراء|للوزراء)|رئيس وزراء|رئيس المجلس الوزراء", ""),
    (r"رئيس الجمهوري[هة]", ""),
    (r"رئيس مجلس النواب", ""),
    (r"رئيس مجلس القضاء", ""),
    (r"البنك المركزي", ""),
    # D. ministers of state, anchored on دول[هة], before the bare one.
    (r"دول[هة].{0,10}الاوقاف", "Q64153902"),
    (r"دول[هة].{0,10}(الوحد[هة]|شوون الوحد)", "Q56697322"),
    (r"دول[هة].{0,14}(اعمار الشمال|اعمار شمالي)", "Q64859730"),
    (r"دول[هة].{0,10}المرا[هة]|دول[هة].{0,10}المرأ", "Q65232506"),
    (r"دول[هة].{0,10}مجلس النواب", "Q110634586"),
    (r"دول[هة].{0,12}العسكري", "Q66385462"),
    (r"دول[هة].{0,10}الكردي", "Q66395654"),
    (r"دول[هة].{0,12}الخارجي", ""),
    (r"دول[هة].{0,10}(المحافظات|الاهوار|المصالح[هة]|القانوني|رياس[هة] الجمهوري)", ""),
    (r"الناطق الرسمي", ""),
    (r"دول[هة].{0,6}(لشوون|للشوون|شوون)", ""),
    (r"وكيل وزير", ""),
    (r"وزير .{2,20} ووزير ", ""),
    # E. portfolios, by bare stem — specific before general.
    (r"الاعمار والاسكان والبلديات", "Q96119237"),
    (r"البلديات والاشغال", "Q56650429"),
    # `Q61958669` is the *Ministry* of Municipal and Rural Affairs — `P31 =
    # Q192350`, a body — and routing a portfolio there writes the very defect
    # `scripts/iq_removals.py` exists to clean. It did: run 1 added two P39
    # statements to it before the removals lane's own census caught them.
    # `Q56650429` "Minister of Municipalities and Public Works" is `P31 =
    # Q294414`, an actual office, and is where the other municipal cells already
    # route.
    (r"الشوون البلدي", "Q56650429"),
    (r"البلديات", "Q12251008"),
    (r"الاعمار والاسكان|الاسكان والاعمار", "Q55691705"),
    (r"الاسكان والتعمير", "Q56885008"),
    (r"اعمار الشمال|شوون الشمال", "Q64153946"),
    (r"الاعمار", "Q55691727"),
    (r"الاشغال والاسكان|الاشغال العام[هة] والاسكان|والاشغال والاسكان", "Q56650446"),
    (r"الاشغال والمواصلات|الاشغال والنقل|الاشغال والموصلات", "Q57270337"),
    (r"المواصلات والاشغال", "Q55755041"),
    (r"النافع[هة]", "Q57270337"),
    (r"الاسكان", ""),
    (r"الاشغال", ""),
    (r"الاقتصاد والمواصلات", "Q57401232"),
    (r"النقل والمواصلات", "Q56884070"),
    (r"المواصلات", "Q12339722"),
    (r"النقل", "Q66360580"),
    (r"الخارجي", "Q6895071"),
    (r"الداخلي[هة] والعدلي|الداخلي", ""),      # lane B: interior
    (r"العدلي[هة]|العدل\b|للعدل", ""),        # lane B: justice
    (r"المالي", "Q28104676"),
    (r"الدفاع", ""),                          # lane B: defence
    (r"المعارف", "Q55714273"),
    (r"التعليم العالي", "Q55691077"),
    (r"التربي", "Q110633948"),
    (r"الاقتصاد", "Q20470741"),
    (r"العمل والشوون الاجتماعي", "Q56697253"),
    (r"الشوون الاجتماعي", "Q22690704"),
    (r"الصح[هة]", "Q6866166"),
    (r"البيئ", ""),
    (r"الزراع[هة] والاصلاح|الاصلاح الزراعي والزراع", "Q64748068"),
    (r"الاصلاح الزراعي", "Q58195518"),
    (r"الزراع[هة] والري|الري والزراع[هة]", "Q57270285"),
    (r"الزراع", "Q110634580"),
    (r"الموارد المائي", "Q110634545"),
    (r"الري\b", "Q56256826"),
    (r"النفط والمعادن", "Q66167561"),
    (r"النفط", "Q55691802"),
    (r"الكهرباء", ""),                        # lane B: electricity
    (r"التخطيط", "Q55691776"),
    (r"الصناع[هة] والتصنيع|التصنيع العسكري", "Q56867915"),
    (r"الصناع[هة] والمعادن|الصناع", "Q110634125"),
    (r"التجار[هة] الخارجي", "Q66828325"),
    (r"التجار[هة] الداخلي", "Q66828321"),
    (r"التجار", "Q55693859"),
    (r"الثقاف[هة] والارشاد", "Q56697377"),
    (r"الثقاف[هة] والاعلام", ""),             # lane B: information (pre-2001)
    (r"الثقاف", "Q110634577"),
    (r"السياح[هة]|الاثار", "Q110634577"),
    (r"الارشاد", "Q64153401"),
    (r"الانباء|الاعلام", ""),                 # lane B: information
    (r"الاوقاف والشوون الديني", "Q67209439"),
    (r"الاوقاف", ""),                         # lane B: awqaf
    (r"الشباب|رعاي[هة] الشباب", "Q65095623"),
    (r"التموين", "Q57516271"),
    (r"الوحد", "Q64160785"),
    (r"الهجر[هة]", "Q56196437"),
    (r"حقوق الانسان", "Q114315435"),
    (r"حقوق المرا[هة]|شوون المرا[هة]", "Q65232506"),
    (r"العلوم", "Q56241386"),
    (r"الاتصالات", "Q110634118"),
    (r"الحكم المحلي", "Q64912939"),
    # F. the bare minister of state and the portfolio-less minister, last.
    (r"بلا وزار[هة]|بدون وزار[هة]|من دون حقيب", "Q1937160"),
    (r"وزير.{0,4}دول[هة]|وزار[هة] دول[هة]|وزراء دول[هة]", ""),
    (r".", ""),
    (r"", ""),
)


#: The 82 cabinet articles listed by `قالب:حكومات العراق`, oldest first, as
#: (article, start, end). Every one of them dates itself in its own rendered
#: infobox — monarchy `التكوين`/`النهاية`, republic `تاريخ البدء`/`تاريخ
#: الانتهاء` — and 53 of the starts are the government item's own `P571`, pulled
#: into the box from Wikidata rather than typed on the page.
#:
#: `حكومة علي فالح الزيدي` (formed 2026-05-14) is deliberately absent: it is the
#: sitting cabinet, it states no end, its start parses to month precision from a
#: slash-dual calendar, and two of its ministers are also in Sudani's account —
#: one continuous tenure told twice, which `collapsing_groups` refuses (§7 #35).
#:
#: Sudani's start is 2022-10-27, the confidence vote, not the 2022-10-13 his
#: infobox gives: 13 October is his designation, his own table rows all say
#: 27 October, and so does his predecessor's end.
CABINETS = (
    ("حكومة عبد الرحمن الكيلاني النقيب", "1920-11-11", "1922-11-16"),
    ("وزارة عبد المحسن السعدون الأولى", "1922-11-16", "1923-11-22"),
    ("وزارة جعفر العسكري الأولى", "1923-11-22", "1924-08-02"),
    ("وزارة ياسين الهاشمي الأولى", "1924-08-02", "1925-06-26"),
    ("وزارة عبد المحسن السعدون الثانية", "1925-06-26", "1926-11-21"),
    ("وزارة جعفر العسكري الثانية", "1926-11-21", "1928-01-11"),
    ("وزارة عبد المحسن السعدون الثالثة", "1928-01-14", "1929-01-20"),
    ("وزارة توفيق السويدي الأولى", "1929-04-28", "1929-08-25"),
    ("وزارة عبد المحسن السعدون الرابعة", "1929-09-19", "1929-11-13"),
    ("وزارة ناجي السويدي", "1929-11-13", "1930-03-23"),
    ("وزارة نوري السعيد الأولى", "1930-03-23", "1931-10-19"),
    ("وزارة نوري السعيد الثانية", "1931-10-19", "1932-11-03"),
    ("وزارة ناجي شوكت", "1932-11-03", "1933-03-20"),
    ("وزارة رشيد عالي الكيلاني الأولى", "1933-03-20", "1933-09-08"),
    ("وزارة رشيد عالي الكيلاني الثانية", "1933-09-08", "1933-11-09"),
    ("وزارة جميل المدفعي الأولى", "1933-11-09", "1934-02-21"),
    ("وزارة جميل المدفعي الثانية", "1934-02-21", "1934-08-27"),
    ("وزارة علي جودت الأيوبي الأولى", "1934-08-27", "1935-03-04"),
    ("وزارة جميل المدفعي الثالثة", "1935-03-04", "1935-03-16"),
    ("وزارة ياسين الهاشمي الثانية", "1935-03-17", "1936-10-29"),
    ("وزارة حكمت سليمان", "1936-10-29", "1937-08-16"),
    ("وزارة جميل المدفعي الرابعة", "1937-08-17", "1938-12-25"),
    ("وزارة نوري السعيد الثالثة", "1938-12-25", "1939-04-06"),
    ("وزارة نوري السعيد الرابعة", "1939-04-06", "1940-02-21"),
    ("وزارة نوري السعيد الخامسة", "1940-02-22", "1940-03-31"),
    ("وزارة رشيد عالي الكيلاني الثالثة", "1940-03-31", "1941-01-30"),
    ("وزارة طه الهاشمي", "1941-02-01", "1941-04-01"),
    ("حكومة الدفاع الوطني (العراق)", "1941-04-03", "1941-04-10"),
    ("وزارة رشيد عالي الكيلاني الرابعة", "1941-04-12", "1941-05-29"),
    ("وزارة جميل المدفعي الخامسة", "1941-06-02", "1941-10-07"),
    ("وزارة نوري السعيد السادسة", "1941-09-21", "1942-10-08"),
    ("وزارة نوري السعيد السابعة", "1942-10-08", "1943-12-25"),
    ("وزارة نوري السعيد الثامنة", "1943-12-25", "1944-06-04"),
    ("وزارة حمدي الباجه جي الأولى", "1944-06-04", "1944-08-29"),
    ("وزارة حمدي الباجه جي الثانية", "1944-08-29", "1946-02-23"),
    ("وزارة توفيق السويدي الثانية", "1946-02-23", "1946-06-01"),
    ("وزارة أرشد العمري الأولى", "1946-06-01", "1946-11-14"),
    ("وزارة نوري السعيد التاسعة", "1946-11-21", "1947-03-11"),
    ("وزارة صالح جبر", "1947-03-29", "1948-01-29"),
    ("وزارة محمد الصدر", "1948-01-29", "1948-06-26"),
    ("وزارة مزاحم الباجه جي", "1948-06-26", "1949-01-06"),
    ("وزارة نوري السعيد العاشرة", "1949-01-06", "1949-12-10"),
    ("وزارة علي جودت الأيوبي الثانية", "1949-12-10", "1950-02-05"),
    ("وزارة توفيق السويدي الثالثة", "1950-02-05", "1950-09-15"),
    ("وزارة نوري السعيد الحادية عشر", "1950-09-15", "1952-07-12"),
    ("وزارة مصطفى محمود العمري", "1952-07-12", "1952-11-21"),
    ("وزارة نور الدين محمود", "1952-11-23", "1953-01-29"),
    ("وزارة جميل المدفعي السادسة", "1953-01-29", "1953-05-07"),
    ("وزارة جميل المدفعي السابعة", "1953-05-07", "1953-09-17"),
    ("وزارة محمد فاضل الجمالي الأولى", "1953-09-17", "1954-03-08"),
    ("وزارة محمد فاضل الجمالي الثانية", "1954-03-08", "1954-04-29"),
    ("وزارة أرشد العمري الثانية", "1954-04-29", "1954-09-03"),
    ("وزارة نوري السعيد الثانية عشر", "1954-09-03", "1955-12-17"),
    ("وزارة نوري السعيد الثالثة عشر", "1955-12-17", "1957-06-20"),
    ("وزارة علي جودت الأيوبي الثالثة", "1957-06-20", "1957-12-16"),
    ("وزارة عبد الوهاب مرجان", "1957-12-16", "1958-03-03"),
    ("وزارة نوري السعيد الرابعة عشر", "1958-03-03", "1958-05-19"),
    ("حكومة الاتحاد العربي", "1958-05-19", "1958-07-14"),
    ("وزارة أحمد مختار بابان", "1958-05-19", "1958-07-14"),
    ("حكومة عبد الكريم قاسم", "1958-07-14", "1963-02-08"),
    ("وزارة أحمد حسن البكر الأولى", "1963-02-08", "1963-05-11"),
    ("وزارة أحمد حسن البكر الثانية", "1963-05-11", "1963-11-18"),
    ("وزارة طاهر يحيى الأولى", "1963-11-18", "1964-06-18"),
    ("وزارة طاهر يحيى الثانية", "1964-06-18", "1964-11-10"),
    ("وزارة طاهر يحيى الثالثة", "1964-11-10", "1965-09-06"),
    ("وزارة عارف عبد الرزاق", "1965-09-06", "1965-09-24"),
    ("وزارة عبد الرحمن البزاز الأولى", "1965-09-24", "1966-04-18"),
    ("وزارة عبد الرحمن البزاز الثانية", "1966-04-18", "1966-08-06"),
    ("وزارة ناجي طالب", "1966-08-06", "1967-05-10"),
    ("وزارة عبد الرحمن عارف (1967)", "1967-03-10", "1967-07-10"),
    ("وزارة طاهر يحيى الرابعة", "1967-07-10", "1968-07-17"),
    ("حكومة عبد الرزاق النايف", "1968-07-17", "1968-07-30"),
    ("حكومة سعدون حمادي", "1991-03-23", "1991-09-13"),
    ("حكومة محمد حمزة الزبيدي", "1991-09-13", "1993-09-05"),
    ("حكومة أحمد حسين خضير", "1993-09-05", "1994-05-29"),
    ("حكومة نوري المالكي الأولى", "2006-05-20", "2010-12-22"),
    ("حكومة نوري المالكي الثانية", "2010-12-22", "2014-09-08"),
    # `حكومة حيدر العبادي` belongs here by date and is deferred on correctness.
    # Its table stacks successive holders inside one name cell with their own
    # spans — "خالد العبيدي (2014-2016)<br/>عرفان الحيالي (2016-2018)" — so the
    # second holder is dropped and the first inherits `term`, the whole
    # 2014-09-08 – 2018-10-25 government. Twenty-eight of its rows carry such a
    # parenthesised span and nine stack two people. That is not a coarse date but
    # one the source itself disproves, which no downstream check would catch.
    ("حكومة عادل عبد المهدي", "2018-10-24", "2020-05-07"),
    ("حكومة مصطفى الكاظمي", "2020-05-06", "2022-10-27"),
    # …and `حكومة محمد شياع السوداني` is deferred for the opposite reason: its
    # rows carry a start of their own ("27 تشرين الأول 2022") and no end, and
    # `term` is applied only where `not row.start`, so it never supplies the end.
    # Twenty-four ministers of a government that fell in May 2026 would ship as
    # open-ended statements. It comes back when `office_rows` learns to apply a
    # source's `term` *end* to a row that has a start and no end.

)

#: Only the primary roster block of each article. Dropping the reshuffle
#: sections costs the ~30 ministers who appear in no other block; keeping them
#: costs 111 duplicate person-portfolio rows that `merge_terms` cannot chain
#: because they share an identical `term` rather than abutting it. Prefer the
#: row-level dedup in `office_rows` and widen this to ANY_TABLE; §2.
PRIMARY = (r"قائم[ةه] الوزراء|التشكيل[ةه] الوزاري|تشكيل[ةه] الوزار[ةه]"
           r"|الوزار[ةه] النقيبي")

#: The ten governorates with no governor item. Shape measured in
#: data/iraq/survey/lane_f.md §1: P31 Q4164871, P279 Q132050, P17 Q796,
#: P1001 = the governorate. `provincial_governor` is reused for its description
#: template only — its parent is the Saudi Q98786082, so P279 is overridden.
#: P571 is suppressed: no Iraqi governor item carries one, and the roster's
#: earliest row is a *mutasarrif of a liwa*, which is a different office (§3b).
GOVERNOR_CLAIMS = (("P279", "Q132050"), ("P571", None))

MISSING_GOVERNORS = (
    # key, governorate QID, en label, ar label, (lang, category)…
    ("governor_karbala",      "Q214104",   "Governor of Karbala",       "محافظ كربلاء",
     (("ar", "محافظو كربلاء"), ("en", "Governors of Karbala Governorate"))),
    ("governor_muthanna",     "Q212761",   "Governor of Muthanna",      "محافظ المثنى",
     (("ar", "محافظو المثنى"), ("en", "Governors of Muthanna Governorate"))),
    ("governor_qadisiyyah",   "Q62987",    "Governor of Al-Qadisiyyah", "محافظ القادسية",
     (("ar", "محافظو القادسية"),)),
    ("governor_diyala",       "Q217075",   "Governor of Diyala",        "محافظ ديالى",
     (("ar", "محافظو ديالى"),)),
    ("governor_duhok",        "Q189541",   "Governor of Duhok",         "محافظ دهوك",
     (("ar", "محافظو دهوك"),)),
    ("governor_sulaymaniyah", "Q213182",   "Governor of Sulaymaniyah",  "محافظ السليمانية",
     (("ar", "محافظو السليمانية"), ("en", "Governors of Sulaymaniyah Governorate"))),
    # --- below the floor; declared so the run reports them, not to be minted ---
    ("governor_babylon",      "Q59202",    "Governor of Babylon",       "محافظ بابل",
     (("ar", "محافظو بابل"),)),
    ("governor_wasit",        "Q189747",   "Governor of Wasit",         "محافظ واسط",
     (("ar", "محافظو واسط"),)),
    ("governor_halabja",      "Q15631321", "Governor of Halabja",       "محافظ حلبجة",
     (("en", "Governors of Halabja Governorate"),)),
    ("governor_dhiqar",       "Q215649",   "Governor of Dhi Qar",       "محافظ ذي قار",
     ()),
)

GOVERNOR_HONORIFIC = re.compile(
    r"^\s*(?:"
    r"وكيل\s+المتصرف\s+القائمقام|وكيل\s+المتصرف\s+آمر\s+الفرقة|"
    r"وكيل\s+المحافظ|وكيل\s+المتصرف|وكيل\s+متصرف|"
    r"معاون\s+المتصرف|معاون\s+متصرف|"
    r"المحافظ|المتصرف|القائمقام"
    r")\s+"
)

REGIMES = (
    (r"PUK-controlled|PUK-run", "puk_administration"),
    (r"KDP-controlled|KDP-run", "kdp_administration"),
)

#: ckb membership-roll headers. `("ناوچە","notes")` MUST come first: "ناو" is a
#: 3-character prefix of "ناوچەی ھەڵبژاردن" and prefix matching applies at
#: length >= 3, so the naive single key reads the constituency as a name column.
CKB_ROLL = (
    ("ناوچە", "notes"), ("ژمارە", "ordinal"), ("لیست", "notes"),
    ("حیزب", "party"), ("فراکسیۆن", "notes"), ("لیژنە", "notes"),
    ("ناو", "name"),
)

CKB_ROLL_5 = (
    ("ناوچە", "notes"), ("ژمارە", "ordinal"), ("حیزب", "party"), ("ناو", "name"),
)

KRG_PORTFOLIOS = (
    # The head and deputy head are covered by their own offices above; routing
    # them to "" is what keeps two sources off one tenure.
    (r"سەرۆکوەزیرانی حکوومەتی ھەرێم", ""),
    (r"جێگری سەرۆکوەزیرانی حکوومەتی ھەرێم", ""),
    (r"وەزیری داد", ""),                              # justice
    (r"وەزیری ناوخۆ", ""),                            # interior
    (r"وەزیری پێشمەرگە", ""),                         # peshmerga affairs
    (r"وەزیری دارایی و ئابووری", ""),                 # finance and economy
    (r"وەزیری تەندروستی", ""),                        # health
    (r"وەزیری پەروەردە", ""),                         # education
    (r"وەزیری ئاوەدانکردنەوە و نیشتەجێ کردن", ""),    # reconstruction and housing
    (r"وەزیری سامانە سروشتییەکان", ""),               # natural resources
    (r"وەزیری شارەوانی و گەشت و گوزار", ""),          # municipalities and tourism
    (r"وەزیری خوێندنی باڵا", ""),                     # higher education
    (r"وەزیری پلاندان", ""),                          # planning
    (r"وەزیری کاروباری کۆمەڵایەتی", ""),              # labour and social affairs
    (r"وەزیری ڕۆشەنبیری و لاوان", ""),                # culture and youth
    (r"وەزیری شەھیدان و ئەنفالکراوان", ""),           # martyrs and Anfal affairs
    (r"وەزیری کشتوکاڵ و سەرچاوەکانی ئاو", ""),        # agriculture and water
    (r"وەزیری پیشەسازی", ""),                         # trade and industry
    (r"وەزیری گواستنەوە و گەیاندن", ""),              # transport and communications
    (r"وەزیری ئەوقاف و کاروباری ئایینی", ""),         # endowments and religious affairs
    (r"وەزیری کارەبا", ""),                           # electricity
    (r"وەزیری ھەرێم", ""),                            # minister of region (3 holders)
    (r"", ""),                                        # §7: the catch-all, not r"."
)

OFFICES = (
    # --- lane D: the central bank and the general staff --------------------
    # `ar:البنك المركزي العراقي` tabulates 25 governors as "المحافظ | الفترة",
    # every row dated in Levantine months and joined by "إلى". Before the parser
    # work this page gave 25 rows with no names and no end dates; `Q110490288`
    # records four holders. The heading pattern is doing real work: the same
    # article carries two currency-auction tables whose "name" column holds
    # dollar amounts, and `محافظو البنك المركزي` is what excludes them (§7 #2).
    #
    # Ten further people hold `Q25167655` — the *category* item — for this
    # office. That is lane H's business; this office proposes against the real
    # item and the removals script accounts for the other ten.
    Office(
        "central_bank", "Governor of the Central Bank of Iraq", "Q110490288",
        rosters=(RosterSource("ar", "البنك المركزي العراقي",
                              headings=r"محافظو البنك المركزي"),),
        categories=(("ar", "محافظو البنك المركزي العراقي"),),
    ),
    # `قائمة رؤساء أركان الجيش العراقي`, `قائمة رؤساء أركان القوات المسلحة
    # (العراق)` and `رؤساء أركان الجيش العراقي` are one page — revid 75937930 —
    # so §7 #1's redirect trap is live here and declaring two offices would
    # double-propose all 36 rows.
    #
    # "المدة" is the only date column on it, holding "من: 6 كانون الثاني/يناير
    # 1921 حتى: …". The shared table types that key `days`, because on the
    # Kuwaiti and Saudi lists it is a tenure length and reading it as the term
    # cost every date on those pages. One string, two meanings, no lexical
    # difference to lean on — so the page declares its own reading.
    Office(
        "chief_of_staff", "Chief of the Iraqi General Staff", "Q110517194",
        rosters=(RosterSource("ar", "رؤساء أركان الجيش العراقي",
                              headings=r"روساء اركان الجيش",
                              column_roles=(("المدة", "period"),)),),
        categories=(("ar", "رؤساء أركان الجيش العراقي"),),
    ),
    # The modern speakership. Its list opens the term with "تسلم منصبه" — a
    # *fourth* Iraqi spelling of taking office, after "تولى", "استلام" and
    # "تاريخ تعيينهم" — against a "ترك منصبه" the existing key already reached,
    # so the page read 14 ends and no starts at all.
    #
    # The monarchy-era speakership is a different article
    # (`رؤساء مجلس النواب العراقي في العهد الملكي`, 38 rows) and has no item.
    # It waits on the creation lane with the rest of lane E.
    Office(
        "speaker", "Speaker of Council of Representatives of Iraq", "Q20404109",
        rosters=(RosterSource("ar", "رؤساء مجلس النواب العراقي",
                              headings=ANY_TABLE),),
        categories=(("ar", "رؤساء مجلس النواب العراقي"),),
    ),

    # --- head of government ------------------------------------------------
    # `en:List of prime ministers of Iraq` is the cleanest source this workbench
    # has read: 81 rows, 81 dated to the day, 81 identified by their own
    # wikilink, one table. `ar:قائمة رؤساء وزراء العراق` is NOT added beside it.
    # It reads 83/83 rows and dates all 83 — to the *year*, because the page
    # writes Levantine month names — and it disagrees with en on four
    # premierships (it splits Nuri al-Said's first and al-Maliki's, drops one of
    # Rashid Ali al-Gaylani's, and ends Abdul-Mahdi in 2019 rather than 2020).
    # §7: two rosters for one office is two sources dating one tenure. The
    # category is the second channel, and it dates nothing.
    #
    # No `date_targets`: Q1476165's own P571 is 1920-11-11 and 46 of its 81
    # dated statements start before 1932, so the Kingdom-era premiership is on
    # this item by the item's own record, and no rival item exists.
    Office(
            "prime_minister", "Prime Minister of Iraq", "Q1476165",
            rosters=(RosterSource("en", "List of prime ministers of Iraq",
                                  headings=r"^list of officeholders"),),
            categories=(("en", "Prime ministers of Iraq"),
                        ("ar", "رؤساء وزراء العراق")),
            section_targets=((CPA_IGC, "Q75611179"), (r"", "Q1476165")),
        ),

    # --- head of state -----------------------------------------------------
    # Q889817 carries P31 = Q248577 and nothing under the Q4164871 closure, so a
    # type-gated census cannot see the head of state of the country (plan §1a).
    # Eleven of the roster's fourteen rows are already recorded; the add is the
    # sitting president, Nizar Amidi (Q115579547, from 2026-04-12).
    Office(
            "president", "President of Iraq", "Q889817",
            rosters=(RosterSource("en", "List of presidents of Iraq",
                                  headings=r"^list of officeholders"),),
            categories=(("en", "Presidents of Iraq"), ("ar", "رؤساء العراق")),
            section_targets=((CPA_IGC, ""), (r"", "Q889817")),
        ),

    # The throne. The heading pattern is the whole of the row filter: the page's
    # first table is headed "King-designate of Iraq (1920)" and holds one row —
    # Abdullah I of *Jordan*, who was offered the Iraqi throne in 1920 and never
    # reigned. `^kings of iraq` accepts the second table and refuses the first.
    #
    # Expect zero statements. All three kings already carry Q3254084 with no
    # dates at all, so the person-level `already holds P39` check skips them and
    # the roster's three day-precision reigns cannot be written. That is the
    # `unrecorded spells` ceiling the recipe describes, and the honest report is
    # three rows, three identified, zero adds — not a relaxed gate.
    Office(
            "king", "King of Iraq", "Q3254084",
            rosters=(RosterSource("en", "King of Iraq",
                                  headings=r"^kings of iraq"),),
            categories=(("en", "Kings of Iraq"), ("ar", "ملوك العراق")),
        ),

    # --- deputy head of state ----------------------------------------------
    # Two era tables on the office article, and the office is genuinely
    # multi-seat: Iraq ran three simultaneous vice presidents in 2004–5, 2005–6,
    # 2014–15 and 2016–18, and two in 1970. Nine of the nineteen rows overlap
    # another; the overlap warnings are data, not defects.
    #
    # `ar:نائب رئيس جمهورية العراق` has four rows to en's nineteen, disagrees on
    # Tariq al-Hashimi's end by fifteen months, and loses the day on its one
    # Levantine-dated cell. Not added.
    Office(
            "vice_president", "Vice President of Iraq", "Q4117119",
            rosters=(RosterSource(
                "en", "Vice President of Iraq",
                headings=r"^(?:under iraqi republic|republic of iraq since 2004)"),),
            categories=(("en", "Vice presidents of Iraq"),
                        ("ar", "نواب رئيس جمهورية العراق")),
        ),

    # 'Abd al-Ilah was regent for the whole of Faisal II's minority, 1939–1953,
    # and is head of state for fourteen of the Kingdom's years — the one gap in
    # the spine that the King and PM lists do not cover. `en:Regent of Iraq`
    # tabulates it: three rows, all wikilinked, all day-precision once
    # "Regency start"/"Regency end" are in the vocabulary. Q16968459 exists and
    # is *bare* — no P31, no P17, no holders, only a Freebase ID — so nothing
    # competes for the era and nothing supports a precedent either; the rows
    # pass on `modern_from` and the ordinary two-channel bar.
    #
    # There is NO regent category on either wiki, so this is the one Lane A
    # office running on a single channel: the roster's own wikilinks. It is
    # reported small rather than widened.
    #
    # 'Abd al-Ilah holds two regencies either side of the 1941 Golden Square
    # coup's regent, so this office alone puts Lane A in the claims half of the
    # batch — QuickStatements would merge his two spells into one P39 with two
    # starts and two ends.
    Office(
            "regent", "Regent of Iraq", "Q16968459",
            rosters=(RosterSource("en", "Regent of Iraq",
                                  headings=r"^reign of faisal ii$"),),
        ),

    # `ar:قائمة وزراء العدل (العراق)` is the richest roster in the country: 86 rows
    # across two era tables, 85 of them dated, 81 identified by wikilink.
    #
    # The Kingdom's justice ministry is NOT this item, and the item says so: all
    # seven of Q106964104's dated statements start 1958 or later. Iraq's entire
    # 1921-58 justice bench sits on the cross-country generic Q17763739 (107
    # statements among these 81 people, against 8 here), which is a class-3
    # generic in the removals lane and a `generic_targets` entry here — not a
    # target. So the Kingdom section is declared a distinct era and its 58 rows
    # become an item-creation byproduct. Contrast `awqaf` below, whose Kingdom
    # rows DO belong on its item: the answer is per item, never per country.
    Office(
        "justice", "Minister of Justice of Iraq", "Q106964104",
        rosters=(RosterSource("ar", "قائمة وزراء العدل (العراق)",
                              headings=r"العدليه|وزراء العدل"),),
        categories=(("ar", "وزراء عدل عراقيون"),      # 46 members
                    ("ar", "وزراء عدل العراق"),       # 11
                    ("en", "Justice ministers of Iraq")),  # 20
        regime_sections=((r"العهد الملكي", "Kingdom of Iraq"),),
    ),

    # Four era tables on one ministry article, and one item under all of them:
    # Q22690703 carries 9 Kingdom-era statements out of 28 dated, including the
    # roster's own 1932 and 1933 rows. No era is declared, so its 1921-58 rows are
    # ordinary `modern` rows. The single pre-1921 row (Jafar al-Askari,
    # 23 October 1920, on a table headed 1921-1958) is `historical` and fails
    # `precedent_allows` on the item's own record — 0 statements before 1921 —
    # which is the right answer and should be reported, not worked around.
    Office(
        "defence", "Minister of Defence of Iraq", "Q22690703",
        rosters=(RosterSource("ar", "وزارة الدفاع (العراق)",
                              headings=r"وزراء الدفاع"),),
        categories=(("ar", "وزراء دفاع عراقيون"),          # 48
                    ("en", "Ministers of defence of Iraq")),  # 27
    ),

    # 2003- only, and all eleven rows are already on Q25463377 with dates. This
    # office is worth running for the backtest, not for the batch: it is the
    # lane's calibration set, and reporting it as zero statements is the point.
    Office(
        "interior", "Minister of the Interior of Iraq", "Q25463377",
        rosters=(RosterSource("ar", "وزارة الداخلية (العراق)",
                              headings=r"وزراء الداخليه"),),
        categories=(("ar", "وزراء داخلية عراقيون"),        # 50
                    ("en", "Interior ministers of Iraq")),  # 31
    ),

    # Four items for one portfolio, and the `ملاحظات` column is what distinguishes
    # them in prose ("وزير الأوقاف", "وكيل وزير الأوقاف", "وزير الدولة لشؤون
    # الأوقاف", "وزير الأوقاف والشؤون الدينية") — but `ملاحظات` is globally typed
    # `notes`, so `section_targets` cannot read it and the routing is by date.
    #
    # The 1968-1980 window routes to "" on purpose: Q66438318 and Q64153902 are
    # two items for the same office in the same year, differing by one definite
    # article and neither carrying P571. Two items competing for one era is a
    # merge decision, not a campaign, so those rows file as a byproduct instead of
    # picking a winner. Q56043357's own 1993-2003 statement overlapping
    # Q67209439's declared span is a second conflict — but it costs no proposals,
    # because the one row in that window is already recorded.
    Office(
        "awqaf", "Minister of Awqaf of Iraq", "Q56043357",
        rosters=(RosterSource("ar", "وزارة الأوقاف والشؤون الدينية (العراق)",
                              headings=r"وزراء الاوقاف|وزراء العهد الجمهوري"),),
        categories=(("ar", "وزراء أوقاف عراقيون"),),   # 13
        date_targets=((None, 1968, "Q56043357"),
                      (1968, 1980, ""),
                      (1980, None, "Q67209439")),
    ),

    # Q116687952 has zero holders, so it is invisible to any census built from
    # holders and was found by label search alone. It also breaks the country's own
    # shape: `P1001 = Q796` with NO `P17`, where every other Lane-B item carries
    # both. Zero holders means zero precedent, so this lane rests entirely on
    # `modern_from` — which is safe, because the ministry was created in 2003.
    #
    # The heading pattern keeps two of the article's three rosters. The third,
    # "وزراء الصحة والبيئة", is the merged 2016-2022 Health-and-Environment
    # ministry: no item exists for it in either wiki, and the community files those
    # six people on Q6866166 (Minister of Health). They are lane C's health rows,
    # not this office's, and the pattern excludes them by construction — "وزراء
    # البييه" cannot match "وزراء الصحه والبييه".
    Office(
        "environment", "Minister of Environment of Iraq", "Q116687952",
        rosters=(RosterSource("ar", "وزارة البيئة (العراق)",
                              headings=r"وزراء البييه"),),
        categories=(("ar", "وزراء بيئة العراق"),           # 5
                    ("ar", "وزراء بيئة عراقيون"),          # 1
                    ("en", "Environment ministers of Iraq")),  # 4
    ),

    # The ministry dates from 2003; the roster's first two rows are the director of
    # the `هيئة الكهرباء` "with the rank of minister", numbered "–" rather than 1
    # and 2, and the first of them names nobody at all ("؟"). That is a different
    # body, so the pre-2003 window routes to "" — an item-creation byproduct rather
    # than two commission directors filed as ministers.
    Office(
        "electricity", "Minister of Electricity of Iraq", "Q57363560",
        rosters=(RosterSource("ar", "وزارة الكهرباء (العراق)",
                              headings=r"وزراء الكهرباء"),),
        categories=(("ar", "وزراء كهرباء عراقيون"),        # 9
                    ("ar", "وزراء كهرباء في العراق"),      # 3
                    ("en", "Electricity ministers of Iraq")),  # 3
        date_targets=((None, 2003, ""), (2003, None, "Q57363560")),
    ),

    # The one table on this page carries no heading at all, and an empty-string
    # pattern is falsy — `source.headings or DEFAULT_HEADINGS` would swap in the
    # default and the office would lose all six rows. Hence a pattern that is
    # truthy AND matches "".
    #
    # A succession proved from the roster's own people rather than from the labels:
    # Q55684412 ("Minister of culture and information") runs 1967-1998 and
    # Q114315423 ("Minister of Information") starts 2001, with no year claimed by
    # both. Latif Nusayyif Jasim sits on the first for 1979-07-16..1991-03-23 — the
    # roster's row 1 to the day — and al-Sahhaf on the second for 2001-04-24.
    #
    # NOT added beside this: `ar:قائمة وزراء الإعلام العراقيين`, which is a REDIRECT
    # to the same page (identical revid). Two sources for one office is two sources
    # dating one tenure, and here it would be the same source twice over.
    Office(
        "information", "Minister of Information of Iraq", "Q114315423",
        rosters=(RosterSource("ar", "قائمة وزراء الإعلام (العراق)",
                              headings=r"^$|وزراء الاعلام"),),
        categories=(("ar", "وزراء إعلام العراق"),          # 5
                    ("ar", "وزراء إعلام عراقيون"),         # 7
                    ("en", "Information ministers of Iraq")),  # 8
        date_targets=((None, 2001, "Q55684412"), (2001, None, "Q114315423")),
    ),

    # Lane C — the cabinet bucket. One office, 80 sources, routed by the office
    # cell. The target is the fallback only: `PORTFOLIOS` routes every one of the
    # 190 distinct cells this corpus uses and its catch-alls send an unmapped one
    # to "" — but it still has to be a real item, or `run()` reads the office as
    # awaiting creation and proposes nothing at all.
    Office(
        "cabinet", "Government of Iraq", "Q1937160",
        rosters=tuple(
            RosterSource("ar", page, headings=PRIMARY, term=(start, end))
            for page, start, end in CABINETS
        ) + tuple(
            # 74 of the 79 tabulate nothing: their ministers are bulleted under
            # `التشكيلة الوزارية` as "وزير المالية: [[رستم حيدر]]", and the
            # article dates the government rather than the row. Both halves of
            # that need `bullet_offices` — the office ahead of the colon is what
            # `PORTFOLIOS` routes on, and without it every row on a page shares
            # one haystack and a bucket lane cannot tell a foreign minister from
            # a finance minister.
            RosterSource("ar", page, kind="bullets", headings=PRIMARY,
                         term=(start, end), bullet_offices=True)
            for page, start, end in CABINETS
        ),
        section_targets=PORTFOLIOS,
        categories=MINISTER_CATEGORIES,
    ),

    #: Lane F. `en:List of governors of Erbil` rather than its Arabic or Sorani
    #: siblings: all three are sitelinks of one item (Q22935594) and they disagree
    #: by months on the modern tenures, so this is one source, chosen for being the
    #: only one with separate start and end columns. Its third table is the
    #: Kurdistan Region era — see the lane G note.
    Office("governor_erbil", "Governor of Erbil Governorate", "Q139375353",
           rosters=(RosterSource("en", "List of governors of Erbil",
                                 headings=r"^governors between"),),
           categories=(("ar", "محافظو أربيل"),
                       ("en", "Governors of Erbil Governorate"))),

    #: The 88 rows are start-dated only and no end is inferred; see §3c. Everything
    #: before 1970 is a *mutasarrif of Liwa al-Mawsil* — the same administrative
    #: post under its pre-1969 name, whose item does not exist — so it routes to ""
    #: and files as a creation byproduct rather than under the modern governorship.
    Office("governor_nineveh", "Governor of Nineveh", "Q127628062",
           rosters=(RosterSource("ar", "قائمة محافظي نينوى",
                                 headings=r"^المحافظون$"),),
           date_targets=((None, 1970, ""),),
           categories=(("ar", "محافظو نينوى"),
                       ("en", "Governors of Nineveh Governorate"))),

    #: The roster is a section of the *governorate* article, not a list page, and its
    #: header row is marked up as `td` — see the four vocabulary keys below.
    Office("governor_saladin", "Governor of Saladin", "Q116679878",
           rosters=(RosterSource("ar", "محافظة صلاح الدين",
                                 headings=r"محافظو محافظه صلاح الدين"),),
           date_targets=((None, 1970, ""),),
           categories=(("ar", "محافظو محافظة صلاح الدين"),
                       ("en", "Governors of Saladin Governorate"))),

    #: Five rows, three of them a bare year, and Q114664017 already records one of
    #: them. Run it for the measurement, not the volume.
    Office("governor_maysan", "Governor of Maysan Governorate", "Q114664017",
           rosters=(RosterSource("en", "Maysan Governorate",
                                 headings=r"^list of governors$"),),
           categories=(("en", "Governors of Maysan Governorate"),)),

    # --- creation-first, then run -------------------------------------------------
    #: No item; 11 rows across two era tables, 9 dated. `أول متصرف للواء ديالى` on
    #: its own first row is why the pre-1970 rows route to "".
    Office("governor_diyala", "Governor of Diyala", "Q141062942",
           rosters=(RosterSource("ar", "قائمة محافظي ديالى",
                                 headings=r"العهد الملكي|بعد عام 2003"),),
           date_targets=((None, 1970, ""),),
           archetype="provincial_governor", jurisdiction="Q217075",
           create_labels=(("en", "Governor of Diyala"), ("ar", "محافظ ديالى")),
           create_claims=GOVERNOR_CLAIMS,
           categories=(("ar", "محافظو ديالى"),)),

    #: No item; 14 rows, all dated, from 1969 — the year the governorate was created.
    Office("governor_duhok", "Governor of Duhok", "Q141062944",
           rosters=(RosterSource("en", "List of governors of Duhok",
                                 headings=ANY_TABLE),),
           archetype="provincial_governor", jurisdiction="Q189541",
           create_labels=(("en", "Governor of Duhok"), ("ar", "محافظ دهوك")),
           create_claims=GOVERNOR_CLAIMS,
           categories=(("ar", "محافظو دهوك"),
                       ("en", "Governors of Duhok Governorate"))),

    # ---- G1  the Kurdistan Region executive ------------------------------
    Office("kr_president", "President of the Kurdistan Region", "Q7241271",
               rosters=(RosterSource(
                   "en", KRG_PRESIDENT,
                   headings=r"^president of the (?:puk-run|kdp-run|kurdistan region$)"),),
               # Pre-unification eras have no item; "" files the row as a creation
               # byproduct *before* the person-level `already holds` check, which is
               # the only way the KDP-run gap becomes visible at all (§1b).
               date_targets=((None, 2005, ""), (2005, None, "Q7241271")),
               regime_sections=REGIMES,
               categories=(("en", "Presidents of Kurdistan"),)),

    Office("kr_prime_minister", "Prime Minister of the Kurdistan Region", "Q16967730",
               rosters=(RosterSource(
                   "en", KRG_PM, headings=r"^(?:puk-controlled|kdp-controlled|2006)"),),
               date_targets=((None, 2006, ""), (2006, None, "Q16967730")),
               regime_sections=REGIMES,
               categories=(("en", "Prime Ministers of Kurdistan Region"),)),

    Office("kr_deputy_pm", "Deputy Prime Minister of the Kurdistan Region",
               "Q132799487",
               rosters=(RosterSource(
                   "en", KRG_DPM, headings=r"^(?:puk-controlled|kdp-controlled|2006)"),),
               date_targets=((None, 2006, ""), (2006, None, "Q132799487")),
               regime_sections=REGIMES),

    # No era split: the office was created at unification and the item says so
    # (`Q48860808` P571 = 2005-06-14). Two vice presidents sit concurrently
    # from 2019-09-08 — real, so expect an overlap warning, not a parse defect.
    Office("kr_vice_president", "Vice President of the Kurdistan Region", "Q48860808",
               rosters=(RosterSource("en", KRG_VP,
                                     headings=r"^list of vice presidents"),)),

    # ---- G2  the Kurdistan Parliament ------------------------------------
    # The office article, NOT `en:Kurdistan Region Parliament`: 11 dated rows
    # against 9, and it ends the sitting speaker where the other calls her
    # incumbent. `("term","notes")` disarms the parliamentary-term ordinal
    # column, which under the global `("term","period")` key joins itself into
    # the range and costs 8 of 11 rows every date (§4c).
    Office("kr_speaker", "Speaker of the Kurdistan Parliament", "Q132799885",
               rosters=(RosterSource("en", KRG_SPEAKER, headings=r"^list of speakers",
                                     column_roles=(("term", "notes"),)),),
               date_targets=((None, 2005, ""), (2005, None, "Q132799885"))),

    # One membership item, one Office, one RosterSource per term. Two sources
    # for the 4th term is safe *because* `term=` makes their dates identical by
    # construction — the §7 two-roster hazard is two sources *parsing* dates.
    Office("kr_mp", "member of the Kurdistan Parliament", "Q61905369",
               rosters=(
                   # 1st term — pre-unification; `date_targets` sends it to "".
                   RosterSource("ckb", "پێڕستی ئەندامانی خولی یەکەمی پەرلەمانی کوردستان-عێراق",
                                headings=ANY_TABLE, term=("1992", "1994"),
                                column_roles=CKB_ROLL),
                   RosterSource("ckb", "پێڕستی ئەندامانی خولی دووەمی پەرلەمانی کوردستان-عێراق",
                                headings=ANY_TABLE, term=("2005", "2009"),
                                column_roles=CKB_ROLL),
                   RosterSource("en", "List of members of the Kurdistan Region Parliament (2009–2013)",
                                headings=ANY_TABLE, term=("2009", "2013"),
                                column_roles=(("member", "name"),)),
                   RosterSource("en", "List of members of the Kurdistan Region Parliament (2013–2019)",
                                headings=ANY_TABLE, term=("2013", "2018")),
                   RosterSource("ar", "قائمة أعضاء برلمان إقليم كردستان (2013–2019)",
                                headings=ANY_TABLE, term=("2013", "2018")),
                   RosterSource("ckb", "پێڕستی ئەندامانی خولی پێنجەمی پەرلەمانی کوردستان-عێراق",
                                headings=ANY_TABLE, term=("2018", "2024"),
                                column_roles=CKB_ROLL_5),
               ),
               date_targets=((None, 2005, ""), (2005, None, "Q61905369"))),

    # ---- G3  the KRG ministries — creation-first -------------------------
    # Every portfolio routes to "" today: 22 of 22 have no position item. The
    # audit's byproduct column becomes the creation list, with each row's
    # holder QID attached. Run 2 replaces the "" values with the minted items.
    Office("krg_cabinet", "Council of Ministers of the Kurdistan Region", "",
               rosters=(RosterSource(
                   "ckb", "کابینەی نۆیەمی حکوومەتی ھەرێمی کوردستان",
                   headings=r"کابینەی نۆیەم", term=("2019-07-10", None),
                   column_roles=(("پلە", "office"), ("حیزب", "party"), ("ناو", "name"))),),
               section_targets=KRG_PORTFOLIOS),
)


CAMPAIGN = Campaign(
    name="iraq",
    country_qid="Q796",
    # The state's founding. `modern_from` only selects which rows the census is
    # asked about — whether an early term is ordinary is answered by the target
    # item's own record through `early.precedent_ok` / `early.unsupported`, which
    # is how defence's 1925 rows land and justice's 1921 rows do not.
    modern_from=1921,
    offices=OFFICES,
    label_langs=("en", "ar"),
    # `ckb` for the Kurdistan lanes, where Sorani carries the parliament's term
    # calendar and three membership rolls that neither `en` nor `ar` has.
    sibling_wikis=("ar", "en", "ckb"),
    evidence_verb="lists them as holding the office",
    # Deliberately empty, and the reason is measured rather than assumed. The
    # `_early` predicate is `historical | historical_roster_only |
    # in_era("continuous")`, so naming the Kingdom of Iraq here would pull every
    # ordinary 1921–58 row into the precedent test — and no lane-B item clears
    # `MIN_EARLIER = 3` before 1921. It would skip all 77 Kingdom rows, including
    # the ten defence and nine awqaf ministers those items already record.
    continuous_eras=(),
    # Iraqi premiers routinely hold Defence or Interior in their own person, and
    # Kurdish leaders hold federal office while holding regional office, so
    # without these `interim_of` stamps `P2868 = acting` on real appointments.
    # Measured on the people's own records: Nouri al-Maliki holds the premiership
    # 2007-05..2014-09 *and* Interior twice *and* Defence 2010-12..2011-08;
    # Abd al-Karim Qasim was premier and defence minister for the whole of
    # 1958–1963; Barham Salih, Fuad Masum and Fuad Hussein each crossed between
    # Erbil and Baghdad.
    concurrency_ignore=(
        # --- federal Iraq
        "Q1476165",    # Prime Minister of Iraq
        "Q889817",     # President of Iraq
        "Q4117119",    # Vice President of Iraq
        "Q20423494",   # Deputy Prime Minister of Iraq
        "Q22690703",   # Minister of Defence
        "Q25463377",   # Minister of the Interior
        "Q6895071",    # Minister of Foreign Affairs
        "Q28104676",   # Minister of Finance
        "Q20404109",   # Speaker of the Council of Representatives
        "Q21328603",   # member of the Council of Representatives — the seat kept
        "Q42314957",   # member of the Transitional National Assembly
        "Q75611179",   # President of the Governing Council — a 30-day rotation
        # --- the Kurdistan Region, whose offices overlap each other by design
        "Q7241271",    # President of Iraqi Kurdistan
        "Q16967730",   # Prime Minister of Iraqi Kurdistan
        "Q132799487",  # Deputy Prime Minister of the Kurdistan Region
        "Q48860808",   # Vice President of Iraqi Kurdistan
        "Q132799885",  # Speaker of the Kurdistan Parliament
        "Q105512852",  # President of the Kurdistan National Council
        "Q113470571",  # Foreign Minister of the Kurdistan Region
        "Q61905369",   # member of the Kurdistan Parliament
        "Q27832358",   # UNHCR — open-ended, and would swallow any short spell
        # …and one entry that is here because of a defect rather than a real
        # concurrency. `Q25167655` is a *category* item — "Category:Governors of
        # the Central Bank of Iraq" — that ten people hold as `P39`, several of
        # them open-ended. `interim_of` read those spans as a concurrent office
        # and stamped three genuine central-bank appointments `P2868 = acting`.
        # The statements themselves are lane H's class 1 removals; ignoring the
        # item here is what stops a known defect qualifying real tenures while
        # it waits for the human gate.
        "Q25167655",   # Category:Governors of the Central Bank of Iraq
        # The same misfire from the other end of the item layer. A *generic* role
        # item accumulates spells from every country that uses it, so a person's
        # "justice minister" statement can span decades and any real appointment
        # falling inside it reads as cover for it. Fourteen rows were qualified
        # `P2868 = acting` on that basis in the first run. These are the same
        # QIDs as `generic_targets` below — that stops the sweep proposing
        # *beside* them, this stops them qualifying anything — plus the body
        # items, which are lane H class 2.
        "Q17763739",   # justice minister (generic)
        "Q10540834",   # agriculture minister (generic)
        "Q4018482",    # education minister (generic)
        "Q11812509",   # industry minister (generic)
        "Q2632935",    # minister of state (generic)
        "Q83307",      # minister (generic)
        "Q1937160",    # minister without portfolio (generic)
        "Q7614320",    # finance minister (generic)
        "Q6867009",    # Ministry of Foreign Affairs — a body, not an office
        "Q61958669",   # Ministry of Municipal and Rural Affairs — a body
        "Q1973075",    # Council of Representatives of Iraq — a body
        "Q56043357",   # Minister of Awqaf — overlaps Q67209439 by 1993–2003,
                       #   a recorded conflict this run refuses to arbitrate
        "Q66438318",   # …and its 1968 rival, the other half of that merge
    ),
    # The cross-country role items Iraqi ministers are actually recorded on, none
    # of which carries `P17`. They are not targets and they are not removals
    # either — a generic with a qualifier is a position the community has taken
    # and this run does not overturn it. Naming them here stops the sweep
    # proposing a redundant statement beside one, and `scripts/iq_removals.py`
    # reports them as a replacement *proposal* behind an explicit flag.
    generic_targets=(
        "Q17763739",  # justice minister — 405 holders; 107 statements among the
                      #   justice roster's own 81 people, against 8 on Q106964104
        "Q2518691",   # defence minister — 324
        "Q17578116",  # interior minister — 254
        "Q1449973",   # environment minister — 45
        "Q3273722",   # health minister — 165
        "Q13424386",  # minister of information — 30
        "Q10540834",  # agriculture minister — 32 Iraqis
        "Q12339722",  # transport minister
        "Q11812509",  # industry minister
        "Q4018482",   # education minister
        "Q7614320",   # finance minister — 243
        "Q2632935",   # minister of state — 138
        "Q83307",     # minister — 9,551
        "Q486839",    # member of parliament — 18 Iraqis
        "Q1937160",   # minister without portfolio — the cabinet lane's fallback
    ),
    # Every non-applying rule maps to `skip`, so each case is applied or skipped
    # with a reason and `edit_plan.md` is an account rather than a backlog.
    dispositions={
        "namesake": "skip",
        "predecessor_body": "skip",
        "category_only": "skip",
        "no_dates": "skip",
        "believed.held": "skip",
        "uncertain": "skip",
    },
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--office", nargs="*", default=None,
                        help="Office keys to run (default: all)")
    args = parser.parse_args()
    run(make_session(), CAMPAIGN, OUT_DIR, keys=args.office)


if __name__ == "__main__":
    main()
