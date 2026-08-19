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
#: Terms 1–8 are `bullets`: the pages are alphabetical rolls of wikilinked
#: names under letter-group headings ("آ، ا، ب، پ، ت، ث"), not tables. The
#: letter heading matches no word in `BULLET_HEADINGS`, which is why the first
#: eight terms read as empty pages and the lane looked like it began in 2012;
#: `bullet_headings` overrides the allowlist for exactly this. 1,871 rows, 1,851
#: of them wikilinked.
MAJLIS_TERMS = (
    ("نخست",     ("1980-05-28", "1984-05-27"), "bullets"),
    ("دوم",      ("1984-05-28", "1988-05-26"), "bullets"),
    ("سوم",      ("1988-05-28", "1992-05-27"), "bullets"),
    ("چهارم",    ("1992-05-28", "1996-05-26"), "bullets"),
    ("پنجم",     ("1996-06-01", "2000-05-24"), "bullets"),
    ("ششم",      ("2000-05-27", "2004-05-26"), "bullets"),
    ("هفتم",     ("2004-05-27", "2008-05-25"), "bullets"),
    ("هشتم",     ("2008-05-27", "2012-05-23"), "bullets"),
    ("نهم",      ("2012-05-27", "2016-05-24"), "table"),   # Q5957961
    ("دهم",      ("2016-05-28", "2020-05-26"), "table"),   # Q25424055
    ("یازدهم",   ("2020-05-27", "2024-05-26"), "table"),   # Q95215862
    ("دوازدهم",  ("2024-05-27", None),         "table"),   # Q124744493, sitting
)

LEGISLATURE = (
    Office("majlis", "Member of the Islamic Consultative Assembly", "Q17525449",
           rosters=tuple(
               RosterSource("fa", f"فهرست نمایندگان دوره {ordinal} مجلس شورای اسلامی",
                            headings=ANY_TABLE, term=term, kind=kind,
                            # The roll links the electoral district *after* the
                            # member, so the last anchor is a place (§ lane F).
                            person_first=(kind == "bullets"),
                            dateless_bullets=(kind == "bullets"),
                            bullet_headings=r"." if kind == "bullets" else None)
               for ordinal, term, kind in MAJLIS_TERMS
           )),
)

# --- lane L: the items that existed all along ------------------------------
#: Six position items were already on Wikidata when the first Iran run closed,
#: each with a handful of holders and no office configured against it — the
#: cheapest coverage in the country, and `coverage/iran.md`'s first row of
#: unfinished business. Two of the six have no channel at all and are not here:
#: the Deputy Speakership `Q118321724` (its roster is two holders per row and
#: dates nothing) and the Head of the Leader's Office `Q110126773` (measured:
#: no roster, no category, no infobox chain). Both are recorded in the ledger.
INHERITED = (
    # en is strictly better here: fa's `فهرست رؤسای کل بانک مرکزی ایران`
    # tabulates 24 governors and dates none of them.
    Office("central_bank", "Governor of the Central Bank of Iran", "Q20110284",
           rosters=(RosterSource("en", "Governor of the Central Bank of Iran",
                                 headings=ANY_TABLE),)),
    Office("majlis_speaker", "Speaker of the Islamic Consultative Assembly",
           "Q6597965",
           rosters=(RosterSource("fa", "رئیس مجلس شورای اسلامی",
                                 headings=ANY_TABLE),)),
    # "Permanent Representative" and "Years served" are the page's own column
    # names and match no role key, so the table read as having neither a person
    # nor a date and produced no roster at all.
    Office("un_rep", "Permanent Representative of Iran to the United Nations",
           "Q7169241",
           rosters=(RosterSource(
               "en", "Permanent Representative of Iran to the United Nations",
               headings=ANY_TABLE,
               column_roles=(("Permanent Representative", "name"),
                             ("Years served", "period"))),)),
    # No roster exists in either wiki — the fa article's only table lists
    # subordinate units. This is the Qatar shape: the category names the
    # holders and their own infoboxes date them. The *chief* commanders'
    # category, not `فرماندهان نیروی انتظامی` (43 members, every sub-command).
    Office("faraja", "Commander-in-Chief of FARAJA", "Q114457755",
           categories=(("en", "Chief commanders of the Police Command of the "
                              "Islamic Republic of Iran"),),
           officebox=("fa", "en")),
)

# --- lane G: the provincial governors -------------------------------------
#: The largest single lane in the country: 902 rows across 31 provinces, ~90% of
#: them dated. Four provinces already have a position item; the other 27 are
#: minted through `create_offices.py --country ir`, which is why this lane could
#: not run at all in the first sweep — 778 of its rows sat behind an item that
#: did not exist.
#:
#: Shape measured, not chosen (`recipes/country_sweep.md` §10). Of the 242
#: worldwide items with `P279 = Q132050` and `P31 = Q4164871`, 185 carry `P1001`
#: and **172 of those scope strictly narrower than their own `P17`** — the
#: convention is not "province vs country" but *scope to the polity governed*.
#: So `P1001` is the province and `P17` stays `Q794`. `P571` is suppressed on
#: all 27: no Iranian governor item carries one, and the earliest row on most of
#: these pages belongs to a predecessor office rather than to this one.
#:
#: `PREDECESSORS` are those predecessor offices, routed to `""` so their rows
#: are dropped rather than filed under a governorship that did not yet exist —
#: the numbered *ostans* of 1937–60 (`استان یکم`, `استان سوم`), the Qajar
#: `حکمران`/`والی` of Gilan and Kerman, the undivided Azerbaijan province, and
#: the 1945–46 separatist Azerbaijan People's Government.
PREDECESSORS = (
    (r"استاندار(?:ان)? استان (?:یکم|سوم)", ""),
    (r"والیان ایالت کرمان", ""),
    (r"حکمران گیلان", ""),
    (r"حکومت خودمختار آذربایجان", ""),
    (r"استانداران استان آذربایجان$", ""),
)
#: Only the *other* regime. `regime_sections` names states this office did not
#: belong to — Belarus lists the BSSR and the BNR and never the Republic of
#: Belarus — and naming `جمهوری اسلامی` here made the campaign's own polity
#: foreign to itself: 431 current-regime governor rows skipped as "a different
#: polity's office". The Pahlavi sections are genuinely the Imperial State.
PROVINCE_REGIMES = ((r"پهلوی", "pahlavi"),)

#: The four governorships that already have an item. `Q106975489` is labelled
#: "Governor of Khorasan Province" and carries `P1001 = Q794` — the only item in
#: the worldwide cluster whose jurisdiction is its own country rather than the
#: polity it governs, which is a repair and not a routing problem.
#: `Q126003139` is labelled "Governor-general of East Azerbaijan", but its only
#: holder is Malek Rahmati (2024) and its `P910` is the generic modern category,
#: so the community uses it as the *modern* governorship under a legacy label:
#: all 50 East Azarbaijan rows route there and no 28th item is minted.
GOVERNOR_ITEMS = {
    "Q1367759": "Q106975471",  # Isfahan Province
    "Q587090": "Q106975489",  # Razavi Khorasan Province
    "Q134228": "Q106963302",  # Ardabil Province
    "Q176081": "Q126003139",  # East Azarbaijan Province
    # Minted 2026-08-19 by `create_offices.py --country ir --apply`;
    # the ledger is `data/iran/created.json`.
    "Q392522": "Q141125483",  # Alborz Province
    "Q132945": "Q141125419",  # Bushehr Province
    "Q171702": "Q141125425",  # Chaharmahal and Bakhtiari Province
    "Q1004666": "Q141125405",  # Fars Province
    "Q928828": "Q141125404",  # Gilan Province
    "Q170041": "Q141125473",  # Golestan Province
    "Q187373": "Q141125458",  # Hamadan Province
    "Q633659": "Q141125441",  # Hormozgan Province
    "Q170570": "Q141125428",  # Ilam Province
    "Q165352": "Q141125403",  # Kerman Province
    "Q174010": "Q141125407",  # Kermanshah Province
    "Q241119": "Q141125413",  # Khuzestan Province
    "Q180068": "Q141125445",  # Kohgiluyeh and Boyer-Ahmad Province
    "Q134386": "Q141125451",  # Kurdistan Province
    "Q1131727": "Q141125437",  # Lorestan Province
    "Q134417": "Q141125431",  # Markazi Province
    "Q308864": "Q141125410",  # Mazandaran Province
    "Q180075": "Q141125467",  # North Khorasan Province
    "Q1105893": "Q141125476",  # Qazvin Province
    "Q131664": "Q141125464",  # Qom Province
    "Q168949": "Q141125448",  # Semnan Province
    "Q939575": "Q141125422",  # Sistan and Baluchestan Province
    "Q171551": "Q141125479",  # South Khorasan Province
    "Q590866": "Q141125434",  # Tehran Province
    "Q134411": "Q141125416",  # West Azarbaijan Province
    "Q170568": "Q141125461",  # Yazd Province
    "Q146726": "Q141125455",  # Zanjan Province
}

#: (key, province item, en label, fa short name, list-article item, roster rows).
#: The fa short name is the province label without `استان `, which is both the
#: roster page's title and the label convention the existing items use
#: (`Q106975471` is `استاندار اصفهان`, not `استاندار استان اصفهان`).
PROVINCES = (
    ("kerman", "Q165352", "Kerman Province", "کرمان", "Q16045843", 67),
    ("gilan", "Q928828", "Gilan Province", "گیلان", "Q5809662", 56),
    ("fars", "Q1004666", "Fars Province", "فارس", "Q16045783", 55),
    ("kermanshah", "Q174010", "Kermanshah Province", "کرمانشاه", "Q16074234", 55),
    ("east_azarbaijan", "Q176081", "East Azarbaijan Province", "آذربایجان شرقی", "Q16074289", 50),
    ("isfahan", "Q1367759", "Isfahan Province", "اصفهان", "Q140191194", 49),
    ("mazandaran", "Q308864", "Mazandaran Province", "مازندران", "Q16045808", 45),
    ("khuzestan", "Q241119", "Khuzestan Province", "خوزستان", "Q16074354", 40),
    ("west_azarbaijan", "Q134411", "West Azarbaijan Province", "آذربایجان غربی", "Q16074306", 39),
    ("bushehr", "Q132945", "Bushehr Province", "بوشهر", "Q16074058", 35),
    ("sistan_baluchestan", "Q939575", "Sistan and Baluchestan Province", "سیستان و بلوچستان", "Q16045775", 28),
    ("chaharmahal_bakhtiari", "Q171702", "Chaharmahal and Bakhtiari Province", "چهارمحال و بختیاری", "Q16045833", 27),
    ("ilam", "Q170570", "Ilam Province", "ایلام", "Q16074395", 26),
    ("markazi", "Q134417", "Markazi Province", "مرکزی", "Q16045813", 25),
    ("tehran", "Q590866", "Tehran Province", "تهران", "Q16074088", 25),
    ("lorestan", "Q1131727", "Lorestan Province", "لرستان", "Q16045800", 24),
    ("hormozgan", "Q633659", "Hormozgan Province", "هرمزگان", "Q16045819", 23),
    ("kohgiluyeh_boyer_ahmad", "Q180068", "Kohgiluyeh and Boyer-Ahmad Province", "کهگیلویه و بویراحمد", "Q16045852", 23),
    ("semnan", "Q168949", "Semnan Province", "سمنان", "Q16074202", 23),
    ("kurdistan", "Q134386", "Kurdistan Province", "کردستان", "Q16074207", 22),
    ("zanjan", "Q146726", "Zanjan Province", "زنجان", "Q16074174", 21),
    ("hamadan", "Q187373", "Hamadan Province", "همدان", "Q16045827", 20),
    ("yazd", "Q170568", "Yazd Province", "یزد", "Q28712909", 18),
    ("qom", "Q131664", "Qom Province", "قم", "Q16045795", 16),
    ("north_khorasan", "Q180075", "North Khorasan Province", "خراسان شمالی", "Q28713751", 15),
    ("golestan", "Q170041", "Golestan Province", "گلستان", "Q56360216", 14),
    ("qazvin", "Q1105893", "Qazvin Province", "قزوین", "Q16045790", 14),
    ("razavi_khorasan", "Q587090", "Razavi Khorasan Province", "خراسان رضوی", "Q109550030", 13),
    ("south_khorasan", "Q171551", "South Khorasan Province", "خراسان جنوبی", "Q17992164", 13),
    ("ardabil", "Q134228", "Ardabil Province", "اردبیل", "Q16074314", 12),
    ("alborz", "Q392522", "Alborz Province", "البرز", "Q16073997", 9),
)

SUBNATIONAL = tuple(
    Office(
        f"gov_{k}", f"Governor of {en}", GOVERNOR_ITEMS.get(prov),
        rosters=(RosterSource("fa", f"فهرست استانداران {short}",
                              headings=ANY_TABLE),),
        section_targets=PREDECESSORS,
        regime_sections=PROVINCE_REGIMES,
        archetype=None if prov in GOVERNOR_ITEMS else "governor",
        jurisdiction=prov,
        create_labels=(("en", f"Governor of {en}"), ("fa", f"استاندار {short}")),
        # `P2354` is the roster article this lane actually read, which 74 of the
        # 242 worldwide governor items carry. `P571` suppressed, per above.
        create_claims=(("P2354", list_item), ("P571", None)),
    )
    for k, prov, en, short, list_item, _rows in PROVINCES
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
           + INHERITED + SUBNATIONAL
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
