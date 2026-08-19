#!/usr/bin/env python
"""Iran's PEP landscape: the executive spine, the ministries, the councils,
the security services and the judiciary.

    python scripts/ir_offices.py [--office KEY ...]

Five measured facts shaped this configuration; `plans/iran_sweep.md` holds the
survey they come from.

* **fa.wikipedia is the source of record, not a supplement.** en.wikipedia has
  two of eleven Iranian ministry office articles and no per-ministry roster
  pattern, while fa has a complete uniform one; 10,578 Iranian humans on
  Wikidata carry only a fa sitelink against 586 en-only. Every office here takes
  its fa roster unless fa has none.

* **Until the Solar Hijri path landed, none of this was reachable** — and it was
  not merely unread. With no `name` role the parser reads the *start-date* cell
  as the person, so the province lists returned rows of date strings and the
  Majlis rolls returned the electoral district as the officeholder. A "before"
  count on a Persian page was corruption, not silence.

* **`modern_from = 1979`, not 2000.** The brief was "2000-onward is sufficient",
  but `Precedent.supports_before` needs three dated statements earlier than the
  cutoff *and* a 15% share, and Iranian items are thin. Worse, a newly minted
  item has `dated = 0` by construction, so every creation-first lane would be
  permanently capped at post-2000 terms. 1979 is the real institutional
  boundary and the engine reasons correctly from it.

* **Two strings mean two things, and neither can be settled globally.**
  `رئیس‌جمهور` is the appointing president on every ministry roster and the
  *holder* on `فهرست رئیس‌جمهورهای ایران`; `مدت تصدی` is a tenure length on the
  judiciary and Expediency tables and the only date column on the president
  list. Both are declared per page with `RosterSource.column_roles`, which is
  what that field is for.

* **Heading patterns are written folded.** `fold('رئیسان')` is `'رييسان'` —
  Persian yeh folds to Arabic yeh now, so a pattern typed in the source spelling
  silently matches nothing.
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from wd.campaign import Campaign, Office, RosterSource, run
from wd.http import make_session

OUT_DIR = REPO_ROOT / "data" / "iran"

#: Truthy, unlike `r""`, which `office_rows` silently replaces with
#: `DEFAULT_HEADINGS` — none of which are Persian.
ANY_TABLE = r".*"

# --- lane B: the executive spine ------------------------------------------
# Already ~100% dated, so this lane is the backtest's labelled set rather than a
# yield lane — but only in part: President 10/10, Supreme Leader 3/3 and First
# VP 8/8 are clean, while the generic VP item is 26% dated and the PM item 63%.
SPINE = (
    Office("president", "President of Iran", "Q838380",
           rosters=(RosterSource("fa", "فهرست رئیس‌جمهورهای ایران",
                                 headings=ANY_TABLE,
                                 column_roles=(("رئیس‌جمهور", "name"),
                                               ("مدت تصدی", "period"))),)),
    Office("supreme_leader", "Supreme Leader of Iran", "Q332486",
           rosters=(RosterSource("fa", "رهبر ایران", headings=ANY_TABLE),)),
    Office("first_vp", "First Vice President of Iran", "Q40097798",
           rosters=(RosterSource("fa", "معاون اول رئیس‌جمهور ایران",
                                 headings=ANY_TABLE),)),
    # The third table on the PM page is `انتصاب‌های لغو شده` — *cancelled*
    # appointments. Reading it would propose tenures that never began.
    Office("prime_minister", "Prime Minister of Iran", "Q13561063",
           rosters=(RosterSource("fa", "فهرست نخست‌وزیران ایران",
                                 headings=r"پادشاهي مشروطه|جمهوري اسلامي"),)),
)

# --- lane C: the ministries ------------------------------------------------
#: (key, label, fa roster page, target). 24 of the 26 real ministry rosters;
#: `وزیر جنگ (ایران)` is a stub with no table and `وزیر علوم و آموزش عالی` has
#: no position item — both are creation/byproduct, not offices.
#: `فهرست وزیران دفاع ایران` is a *redirect* to the defence page and is
#: deliberately not listed, or defence would be proposed twice (§7 #1).
MINISTRIES = (
    ("education", "Minister of Education", "وزیر آموزش و پرورش", "Q97204911"),
    ("ict", "Minister of ICT", "وزیر ارتباطات و فناوری اطلاعات", "Q110038716"),
    ("intelligence", "Minister of Intelligence", "وزیر اطلاعات", "Q106582349"),
    ("info_tourism", "Minister of Information and Tourism",
     "وزیر اطلاعات و جهانگردی", "Q109924436"),
    ("economy", "Minister of Economic Affairs and Finance",
     "وزیر امور اقتصادی و دارایی", "Q108852880"),
    ("commerce", "Minister of Commerce", "وزیر بازرگانی (ایران)", "Q108046090"),
    ("labour_welfare", "Minister of Cooperatives, Labour and Social Welfare",
     "وزیر تعاون، کار و رفاه اجتماعی", "Q110042498"),
    ("agriculture", "Minister of Agriculture Jihad", "وزیر جهاد کشاورزی",
     "Q110042480"),
    ("justice_min", "Minister of Justice", "وزیر دادگستری (ایران)", "Q85952209"),
    ("defence", "Minister of Defence and Armed Forces Logistics",
     "وزیر دفاع و پشتیبانی نیروهای مسلح", "Q110039042"),
    ("roads", "Minister of Roads and Urban Development", "وزیر راه و شهرسازی",
     "Q108752025"),
    ("industries_mines", "Minister of Industries and Mines",
     "وزیر صنایع و معادن", "Q119930622"),
    ("industry_trade", "Minister of Industry, Mine and Trade",
     "وزیر صنعت، معدن و تجارت", "Q110042550"),
    ("science", "Minister of Science, Research and Technology",
     "وزیر علوم، تحقیقات و فناوری", "Q5952049"),
    ("culture", "Minister of Culture and Islamic Guidance",
     "وزیر فرهنگ و ارشاد اسلامی", "Q109669247"),
    ("labour_social", "Minister of Labour and Social Affairs",
     "وزیر کار و امور اجتماعی (ایران)", "Q59506325"),
    ("housing", "Minister of Housing and Urban Development",
     "وزیر مسکن و شهرسازی", "Q115624978"),
    ("mines_metals", "Minister of Mines and Metals", "وزیر معادن و فلزات",
     "Q115625149"),
    ("heritage", "Minister of Cultural Heritage and Tourism",
     "وزیر میراث فرهنگی، گردشگری و صنایع دستی", "Q110038961"),
    ("petroleum", "Minister of Petroleum", "وزیر نفت (ایران)", "Q16074360"),
    ("energy", "Minister of Energy", "وزیر نیرو (ایران)", "Q110039096"),
    ("sport", "Minister of Sport and Youth", "وزیر ورزش و جوانان", "Q16047280"),
)

PORTFOLIOS = tuple(
    Office(key, label, target,
           rosters=(RosterSource("fa", page, headings=ANY_TABLE),))
    for key, label, page, target in MINISTRIES
) + (
    # Two ministries need a heading filter rather than the whole page.
    # `معاونان` on the interior page is ten DEPUTY ministers; without this they
    # parse as ministers.
    Office("interior", "Interior Minister of Iran", "Q20987826",
           rosters=(RosterSource("fa", "وزیر کشور (ایران)",
                                 headings=r"فهرست"),)),
    # Health's three predecessor bodies are separate institutions with no item
    # of their own; routed to "" so they file as a creation byproduct instead of
    # landing on the modern ministry.
    Office("health", "Minister of Health and Medical Education", "Q17991514",
           rosters=(RosterSource("fa", "وزیر بهداشت، درمان و آموزش پزشکی",
                                 headings=ANY_TABLE),),
           section_targets=((r"وزير بهداري و بهزيستي", ""),
                            (r"وزير بهداري", ""),
                            (r"وزير صحيه", ""),
                            (r"", "Q17991514"))),
    # The one lane-C item already at scale (29 statements). `Q63185643` is the
    # *list article's* item, not the position.
    Office("foreign", "Foreign Affairs Minister of Iran", "Q127710",
           rosters=(RosterSource("fa", "فهرست وزیران امور خارجه ایران",
                                 headings=ANY_TABLE),),
           regime_sections=((r"پيش از انقلاب مشروطه", "qajar"),)),
)

# --- lane D: the councils --------------------------------------------------
#: The six Assembly of Experts terms and the day each began, from the rolls'
#: own leads. Each term's end is the next term's start (§7 #32), so a member
#: re-elected across terms merges into one continuous spell instead of six.
AOE_TERMS = (
    ("اول",   ("1983-08-15", "1991-02-21")),
    ("دوم",   ("1991-02-21", "1999-02-20")),
    ("سوم",   ("1999-02-20", "2007-02-20")),
    ("چهارم", ("2007-02-20", "2016-05-24")),
    ("پنجم",  ("2016-05-24", "2024-05-21")),
    ("ششم",   ("2024-05-21", None)),
)

COUNCILS = (
    # The rolls date no row: the term is stated once in the page's lead, which
    # is `RosterSource.term`'s case. Five of the six are bullet lists, and they
    # need `dateless_bullets` to survive `parse_bullet_rosters` at all — a
    # dateless bullet is dropped there before `term` is ever applied to it.
    # `person_first` because these rolls link the member's **province** after
    # them; on the default last-link rule every row resolved to `استان تهران`.
    Office("aoe_member", "Member of the Assembly of Experts", "Q98458420",
           rosters=tuple(
               RosterSource("fa", f"فهرست نمایندگان دوره {ordinal} مجلس خبرگان رهبری",
                            kind="bullets", headings=ANY_TABLE, term=term,
                            dateless_bullets=True, person_first=True)
               for ordinal, term in AOE_TERMS
           ) + tuple(
               RosterSource("fa", f"فهرست نمایندگان دوره {ordinal} مجلس خبرگان رهبری",
                            headings=ANY_TABLE, term=term)
               for ordinal, term in AOE_TERMS
           ),
           categories=(("fa", "اعضای مجلس خبرگان رهبری"),)),
    Office("aoe_chairman", "Chairman of the Assembly of Experts", "Q107040507",
           rosters=(RosterSource("en", "List of chairmen of the Assembly of Experts",
                                 headings=ANY_TABLE,
                                 column_roles=(("duration", "days"),
                                               ("term", "notes"))),)),
    Office("guardian_member", "Member of the Guardian Council", "Q107041759",
           rosters=(RosterSource("fa", "شورای نگهبان", headings=r"^اعضا"),),
           categories=(("fa", "اعضای شورای نگهبان"),)),
    Office("guardian_secretary", "Secretary of the Guardian Council", "Q107086881",
           rosters=(RosterSource("fa", "دبیر شورای نگهبان", headings=r"فهرست"),),
           categories=(("fa", "دبیران شورای نگهبان"),)),
    Office("expediency_chairman", "Chairman of the Expediency Discernment Council",
           "Q60149180",
           rosters=(RosterSource("fa", "مجمع تشخیص مصلحت نظام",
                                 headings=r"^رييسان"),)),
    Office("expediency_secretary", "Secretary of the Expediency Discernment Council",
           "Q108267905",
           rosters=(RosterSource("fa", "دبیرخانه مجمع تشخیص مصلحت نظام",
                                 headings=ANY_TABLE),)),
    # Membership of the SNSC is ex officio — the en page heads the column
    # literally "Ex officio member" and the fa page fills it with offices, not
    # people. There is no member item and there should not be one; only the
    # secretaryship is an office.
    Office("snsc_secretary", "Secretary of the Supreme National Security Council",
           "Q101117334",
           rosters=(RosterSource("en", "Supreme National Security Council",
                                 headings=r"secretaries"),)),
)

# --- lane E: the security services ----------------------------------------
SECURITY = (
    Office("irgc_cinc", "Commander-in-Chief of the IRGC", "Q56360403",
           rosters=(RosterSource("fa", "فرمانده کل سپاه پاسداران انقلاب اسلامی",
                                 headings=r"^فرماندهان"),)),
    Office("irgc_deputy", "Deputy Commander of the IRGC", "Q138527486",
           rosters=(RosterSource("fa", "فرمانده کل سپاه پاسداران انقلاب اسلامی",
                                 headings=r"^فهرست جانشينان"),)),
    Office("irgc_aerospace", "Commander of the IRGC Aerospace Force", "Q125258861",
           rosters=(RosterSource("fa", "نیروی هوافضای سپاه پاسداران انقلاب اسلامی",
                                 headings=r"^فرماندهان"),)),
    # `یگان‌ها` on the ground-force page is 64 *unit* rows, not commanders.
    Office("irgc_ground", "Commander of the IRGC Ground Force", "Q125258846",
           rosters=(RosterSource("fa", "نیروی زمینی سپاه پاسداران انقلاب اسلامی",
                                 headings=r"^فرماندهان"),)),
    Office("irgc_navy", "Commander of the IRGC Navy", "Q138527120",
           rosters=(RosterSource("fa", "نیروی دریایی سپاه پاسداران انقلاب اسلامی",
                                 headings=r"^فرماندهان"),)),
    Office("quds", "Commander of the Quds Force", "Q80822829",
           rosters=(RosterSource("fa", "نیروی قدس سپاه پاسداران انقلاب اسلامی",
                                 headings=r"^فرماندهان"),)),
    Office("irgc_chief_of_staff", "Chief of the General Staff of the IRGC",
           "Q136522730",
           rosters=(RosterSource("fa", "ستاد مشترک سپاه پاسداران انقلاب اسلامی",
                                 headings=r"^رييسان"),)),
    Office("irgc_minister", "Minister of Revolutionary Guards", "Q138529815",
           rosters=(RosterSource("fa", "وزارت سپاه پاسداران انقلاب اسلامی",
                                 headings=r"^وزيران"),)),
    Office("artesh_cinc", "Commander-in-Chief of the Army", "Q5719341",
           rosters=(RosterSource("fa", "فرمانده کل ارتش جمهوری اسلامی ایران",
                                 headings=r"^فهرست"),)),
    Office("artesh_navy", "Commander of the Iranian Navy", "Q96375335",
           rosters=(RosterSource("fa",
                                 "فرمانده نیروی دریایی ارتش جمهوری اسلامی ایران",
                                 headings=r"^فرماندهان"),)),
    Office("general_staff", "Chief of the General Staff of the Armed Forces",
           "Q107327562",
           rosters=(RosterSource("fa", "رئیس ستاد کل نیروهای مسلح",
                                 headings=ANY_TABLE),)),
)

# --- lane I: the judiciary -------------------------------------------------
# Five of the nine judicial offices have no position item at all, including the
# heads of the Supreme Court, the Court of Administrative Justice and the
# General Inspection Office. They are a creation list, not offices here.
#
# The two en pages parse today with no code change and were the campaign's
# Phase-0 smoke test; the fa Prosecutor-General page is strictly better than its
# en counterpart (13 of 14 rows at day precision with 13 references, against
# nine bare-year ranges and no citations), so it wins under §7 #35.
JUDICIARY = (
    Office("chief_justice", "Chief Justice of Iran", "Q5662557",
           rosters=(RosterSource("en", "Chief Justice of Iran",
                                 headings=ANY_TABLE),)),
    Office("prosecutor_general", "Prosecutor-General of Iran", "Q5729613",
           rosters=(RosterSource("fa", "دادستان کل کشور (ایران)",
                                 headings=ANY_TABLE),)),
    Office("judiciary_spokesman", "Spokesman for the Judiciary of Iran",
           "Q107391310",
           rosters=(RosterSource("fa", "شورای عالی قوه‌قضائیه",
                                 headings=ANY_TABLE),)),
)

# --- lane F: the legislature ----------------------------------------------
#: `Q17525449` is one item for 618 people, and its rolls date no row — the term
#: is the page's title. Dates come from the convocation items the statements'
#: own `P2937` qualifiers point at, read live rather than assumed; the 12th has
#: no `P576` because it is sitting, and its start is the 11th's end plus a day
#: (§7 #32).
#:
#: **Known and accepted cost.** `holders()` gates per (person, target), not per
#: term, and 423 people already hold this item for a *different* term — so their
#: remaining terms are dropped. That under-yields; it does not write anything
#: wrong, and the alternative is a per-term gate this run does not build. Term 11
#: is 276 of 290 already recorded and is the lane's calibration set rather than
#: its yield.
MAJLIS_TERMS = (
    ("نهم",      ("2012-05-27", "2016-05-24")),   # Q5957961
    ("دهم",      ("2016-05-28", "2020-05-26")),   # Q25424055
    ("یازدهم",   ("2020-05-27", "2024-05-26")),   # Q95215862
    ("دوازدهم",  ("2024-05-27", None)),           # Q124744493, sitting
)

LEGISLATURE = (
    Office("majlis", "Member of the Islamic Consultative Assembly", "Q17525449",
           rosters=tuple(
               RosterSource("fa", f"فهرست نمایندگان دوره {ordinal} مجلس شورای اسلامی",
                            headings=ANY_TABLE, term=term)
               for ordinal, term in MAJLIS_TERMS
           )),
)

# --- lane K: the diplomatic rosters ---------------------------------------
#: Iran's outbound ambassadorships, with the fa roster page derived from the
#: *receiving* state's Persian label — which is what `P17` holds on these items
#: (74 of 77), and the reason lane A must **not** add `P17=Q794` to them. They
#: are already visible to the OpenSanctions build, filed under the receiver;
#: the sender sits in `P137`, which `zavod` does not read
#: (opensanctions/opensanctions#5475).
#:
#: Only the 15 pages carrying at least one date are listed. The other 17 that
#: parse are undated bullets — they would every one of them skip as `no_dates`,
#: so listing them buys nothing but 17 more fetches. 765 rows exist across all
#: 32; 244 of them are datable, and that gap is the honest size of this lane.
AMBASSADORS_SRC = (
    ("Q27038402", "ambassador of Iran to France", "فرانسه", "bullets"),
    ("Q88634479", "Ambassador of Iran to Egypt", "مصر", "bullets"),
    ("Q124540500", "ambassador of Iran to the Russian Federation", "روسیه", "bullets"),
    ("Q87982622", "ambassador of Iran to Malaysia", "مالزی", "bullets"),
    ("Q124608724", "ambassador of Iran to Qatar", "قطر", "bullets"),
    ("Q107253232", "ambassador of Iran to Belgium", "بلژیک", "bullets"),
    ("Q124536760", "ambassador of Iran to Saudi Arabia", "عربستان سعودی", "table"),
    ("Q115764181", "ambassador of Iran to Afghanistan", "افغانستان", "table"),
    ("Q124570608", "ambassador of Iran to Norway", "نروژ", "bullets"),
    # Oman is deliberately absent: five of its rows run backwards
    # (`starts +2011-01-01 but ends +2009-01-01`), the RTL authoring
    # artifact of §7 #31. `wd/validate.py` refuses them, and the recipe's
    # answer is to defer the lane rather than add a global swap that would
    # silently reorder a legitimately odd range somewhere else.
    ("Q124612964", "ambassador of Iran to Turkmenistan", "ترکمنستان", "bullets"),
    ("Q124614360", "ambassador of Iran to Thailand", "تایلند", "bullets"),
    ("Q107249825", "ambassador of Iran to Ireland", "ایرلند", "table"),
    ("Q124540979", "ambassador of Iran to Austria", "اتریش", "table"),
    ("Q124540443", "ambassador of Iran to Bosnia and Herzegovina", "بوسنی و هرزگوین", "bullets"),
)

DIPLOMATIC = tuple(
    Office(f"amb_{pos.lower()}", label, pos,
           rosters=(RosterSource(
               "fa", f"فهرست سفیران ایران در {fa}", headings=ANY_TABLE,
               kind="bullets" if kind == "bullets" else "table",
               person_first=(kind == "bullets"),
           ),))
    for pos, label, fa, kind in AMBASSADORS_SRC
)

OFFICES = (SPINE + PORTFOLIOS + COUNCILS + SECURITY + JUDICIARY + LEGISLATURE
           + DIPLOMATIC)

CAMPAIGN = Campaign(
    name="iran",
    country_qid="Q794",
    modern_from=1979,
    offices=OFFICES,
    label_langs=("en", "fa"),
    sibling_wikis=("fa", "en", "ar"),
    evidence_verb="lists them in the office",
    #: Items naming an office only vaguely. A statement proposed against one of
    #: these is redundant beside a specific office, and the Majlis item in
    #: particular is one item doing the work of 618 people.
    generic_targets=(
        "Q175240",     # vizier, 157
        "Q134563198",  # member of the National Consultative Assembly, 85
        "Q83307",      # minister
        # Found by lane A, and the first two matter most: a governor or MP
        # statement proposed beside one of these is redundant, and Iran uses
        # them at scale.
        "Q486839",     # member of parliament, 231 Iranian holders
        "Q132050",     # governor, 25
        "Q17575128",   # grand ayatollah, 107
        "Q2660216",    # the generic vice-presidency, 37
        "Q11247470",   # commanding officer, 10
        "Q30185",      # mayor, 9
    ),
    #: Offices whose overlap with another carries no meaning. Measured, not
    #: assumed: 32 overlapping P39 pairs in the security lane alone — Shamkhani
    #: commanded the IRGC Navy and the Artesh Navy at the same time and held the
    #: Ministry of Revolutionary Guards while Deputy Commander. `Q27628370` is
    #: ex officio the Supreme Leader on 15 of 15 rows. Without this,
    #: `interim_of` stamps P2868 on real appointments.
    concurrency_ignore=(
        "Q17525449",   # a Majlis seat overlaps everything by design
        "Q332486",     # Supreme Leader
        "Q27628370",   # Commander-in-Chief of the Armed Forces, ex officio
        "Q86969202",   # Expediency Council seat
        "Q98458420",   # Assembly of Experts seat
        "Q107041759",  # Guardian Council seat
        "Q2660216",    # the generic vice-presidency
        "Q138527486", "Q125258846", "Q138529815",
    ),
    #: Every rule that does not apply maps to `skip`, so `edit_plan.md` is an
    #: account of what was decided rather than a queue nobody works through.
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
    parser.add_argument("--office", action="append", help="run only these keys")
    args = parser.parse_args()
    run(make_session(), CAMPAIGN, OUT_DIR, keys=args.office)


if __name__ == "__main__":
    main()
