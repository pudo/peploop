#!/usr/bin/env python
"""Propose P39 statements for Saudi Arabia.

    python scripts/sa_offices.py --office king crown_prince shura_member

The country parameters for `wd/campaign.py`; the method is
`recipes/country_sweep.md`, and `plans/saudi_arabia_sweep.md` records what the
survey measured. Saudi Arabia is the third-emptiest country this workbench has
measured — 6,213 people carry `P27 = Q851` and 551 of them carry any `P39` — and
five things about it are specific enough to spell out.

* **Most of these rosters date in Hijri, and nothing converts them.** An AH year
  simply falls outside the Gregorian range `parse_date` accepts (AH 1500 is AD
  2076, so nothing in use collides), and a cell dated in both keeps its AD half.
  `scripts/check_dates.py` pins that. The consequence is honest and uneven: the
  health ministers' roster has 21 rows and **no** datable term, the interior
  ministers' 11 rows yield 2, and the information ministers' 26 rows yield 14 —
  those pages print the Gregorian date beside the Hijri one and the others do
  not. The lanes are reported at what they yield rather than padded.

* **The Consultative Assembly rolls are one term per page and date no row.**
  150 members per page, no date column at all: the term is in the page title, in
  Hijri. `RosterSource.term` carries it, and the value is declared here at *year
  precision* because that is what the sources support — see `SHURA` below, where
  each year is anchored to a Gregorian date one of the pages actually prints.

* **The Second Deputy Prime Ministership has no item, and enwiki redirects its
  article to the Crown Prince.** So resolving the office by title lands on
  Q12251224 and would file four holders of a distinct office under the heir
  apparent's. It is declared for creation instead, and until the item exists the
  engine reports it pending and proposes nothing.

* **The first and second Saudi states are different polities.** 22 of the 29
  rulers on `قائمة حكام آل سعود` were Imams or Emirs of Diriyah and Nejd, whose
  office has no item; `date_targets` routes every pre-1932 row to `""`, which
  files it as an item-creation byproduct rather than under the Kingdom's throne.

* **No review tier.** `dispositions` sends every non-applying rule to `skip`, so
  the campaign decides each row and `edit_plan.md` is an account rather than a
  queue. The batch is reviewed once, whole, in the QuickStatements importer.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.campaign import Campaign, Office, RosterSource, run
from wd.http import REPO_ROOT, make_session

OUT_DIR = REPO_ROOT / "data" / "saudi"

#: A table whose heading names nothing the parser recognises, or none at all.
#: Must be truthy — `office_rows` reads `source.headings or DEFAULT_HEADINGS`
#: and an empty pattern is silently replaced by the default. Same value as
#: `ae_offices.ANY_TABLE`.
ANY_TABLE = r".*"

#: The page carrying the Crown Prince, Deputy Crown Prince and Second Deputy
#: Prime Minister successions in three tables.
HEIRS = "Crown Prince of Saudi Arabia"

#: Consultative Assembly terms: (page suffix, start year, end year).
#:
#: The rolls are undated and titled in Hijri, so the term is declared here
#: rather than parsed — at **year precision**, because that is the most these
#: sources support and a wrong boundary would be stamped on 150 people at once.
#: Two of the pages print a Gregorian anchor that fixes the mapping beyond
#: doubt: the 1434 roll's own prose gives "11 يناير 2013 (29 صفر 1434)", and
#: the 1438 roll gives "3 ربيع الأول 1438" = 2 December 2016. 1442 AH begins
#: 20 August 2020, and 1446 — when the next council was seated, and the reason
#: its own page exists — in 2024.
#:
#: **Each term's end is the next term's start**, which is exactly as attested as
#: the start and matters more than it looks: a member serving all three terms
#: would otherwise get three open-ended statements for one seat, which no reader
#: can tell apart. Closed and consecutive, `merge_terms` folds them into the one
#: continuous membership they describe.
#:
#: The 1446–1450 page is listed on the disambiguation page but carries neither a
#: table nor a list, so there is nothing to read; it is a followup, not a lane.
SHURA = (
    ("1434-1438هـ", "2013", "2016"),
    ("1438-1442هـ", "2016", "2020"),
    ("1442-1446هـ", "2020", "2024"),
)

#: Portfolio phrase → position item, first match wins, specific first.
#:
#: Read off the census of items scoped to Q851 (125 carry a holder), not
#: guessed. Two rows route to `""` on purpose:
#:
#: * **Human Resources and Social Development** is the 2019 renaming of Labour
#:   and Social Development, and Wikidata has an item for the *ministry*
#:   (Q12250983) but none for the minister. Filing the holder under
#:   Q59507344 "Minister of Labor and Social Development" would assert a rename
#:   nobody has recorded — the trap `recipes/country_sweep.md` §2a names.
#: * anything else unmapped, by the catch-all, so a portfolio with no item
#:   becomes a creation byproduct instead of landing on `target`.
PORTFOLIOS: tuple = (
    # Head of government first: the Crown Prince's cell reads "Prime Minister".
    (r"\bprime minister\b", "Q1153839"),
    # "Minister of State for …" ahead of the bare "Minister of State".
    (r"state for foreign affairs", "Q114453160"),
    (r"state for gulf affairs", "Q114453161"),
    (r"state for shura affairs", "Q114453163"),
    # Bare portfolios.
    (r"minister of defen[cs]e", "Q25556795"),
    (r"minister of national guard", "Q56660969"),
    (r"minister of interior", "Q114452638"),
    (r"minister of foreign affairs", "Q22689140"),
    (r"minister of islamic affairs", "Q114452780"),
    (r"minister of education", "Q79588209"),
    (r"minister of justice", "Q110983007"),
    (r"minister of energy", "Q110983168"),
    (r"industry and mineral resources", "Q114452778"),
    (r"minister of transport", "Q60149886"),
    (r"minister of commerce", "Q114452755"),
    (r"minister of investment", "Q112917802"),
    (r"economy and planning", "Q114452759"),
    (r"minister of health", "Q98934272"),
    (r"minister of (?:media|information)", "Q104127725"),
    (r"minister of finance", "Q60197575"),
    (r"minister of culture", "Q114452757"),
    (r"environment, water and agriculture", "Q114452766"),
    (r"hajj and umrah", "Q105911981"),
    (r"communications and information technology", "Q114452756"),
    (r"municipalities and housing", "Q114452786"),
    (r"minister of sport", "Q112917804"),
    (r"minister of tourism", "Q114452805"),
    # An unproven rename: the ministry item exists, the minister item does not.
    (r"human resources and social development", ""),
    (r"minister of state(?! for)", "Q105045827"),
    # Anything else is a portfolio with no item.
    (r".", ""),
)

#: The five provinces whose governorship has no item: (key, province QID,
#: en label, ar label, en category). The eight that do exist all carry
#: `P279 = Q98786082` and `P1001 = <province>`, which is why `jurisdiction` is
#: set — see `Office.jurisdiction`.
MISSING_GOVERNORS = (
    ("governor_jazan", "Q269973", "Governor of Jazan Region",
     "أمير منطقة جازان", "Governors of Jazan Province"),
    ("governor_najran", "Q464718", "Governor of Najran Region",
     "أمير منطقة نجران", "Governors of Najran Province"),
    ("governor_northern", "Q201781", "Governor of the Northern Borders Region",
     "أمير منطقة الحدود الشمالية", "Governors of Northern Borders Province"),
    ("governor_bahah", "Q852774", "Governor of Al-Bahah Region",
     "أمير منطقة الباحة", "Governors of al-Baha Province"),
    ("governor_jouf", "Q1471266", "Governor of Al-Jouf Region",
     "أمير منطقة الجوف", "Governors of al-Jouf Province"),
)

#: Every en portfolio subcategory of `Government ministers of Saudi Arabia`.
#: Listed rather than expanded because `build_people` harvests at depth 0 — the
#: parent category has almost no direct members and all the volume is one level
#: down. These are candidate generators only; the roster row decides.
MINISTER_CATEGORIES = tuple(
    ("en", f"{portfolio} ministers of Saudi Arabia")
    for portfolio in (
        "Agriculture", "Aviation", "Civil service", "Commerce", "Communication",
        "Culture", "Defense", "Economy", "Education", "Electricity", "Energy",
        "Environment", "Finance", "Foreign", "Hajj", "Health",
        "Higher education", "Housing", "Industry", "Information", "Interior",
        "Investment", "Islamic affairs", "Justice", "Labour",
        "Municipal affairs", "National guard",
        "Petroleum and mineral resources", "Planning", "Public works",
        "Social affairs", "Sports", "State", "Tourism", "Trade", "Transport",
        "Water", "Youth",
    )
) + (
    ("en", "Government ministers of Saudi Arabia"),
    ("en", "Women government ministers of Saudi Arabia"),
    ("ar", "وزراء سعوديون"),
)

OFFICES = [
    # ---- Lane A: the throne -------------------------------------------------
    Office("king", "King of Saudi Arabia", "Q850168",
           rosters=(RosterSource("en", "King of Saudi Arabia",
                                 headings=r"^kings of saudi arabia"),),
           categories=(("en", "Kings of Saudi Arabia"),
                       ("ar", "ملوك السعودية"))),
    Office("crown_prince", "Crown Prince of Saudi Arabia", "Q12251224",
           rosters=(RosterSource("en", HEIRS, headings=r"^crown princes"),),
           categories=(("en", "Saudi heirs apparent who never acceded"),
                       ("ar", "أولياء عهد السعودية"))),
    # Q19810880's label is the bare lowercase "deputy crown prince", but it is
    # this country's office: `P1001 = Q851`, `P31 = Q4164871`, two holders of
    # the three the page lists.
    Office("deputy_crown_prince", "Deputy Crown Prince", "Q19810880",
           rosters=(RosterSource("en", HEIRS, headings=r"^deputy crown princes"),)),
    # No item, and the article redirects to the Crown Prince — see the module
    # docstring. Declared for `scripts/create_offices.py`; proposes nothing yet.
    Office("second_deputy_pm", "Second Deputy Prime Minister", "",
           rosters=(RosterSource("en", HEIRS,
                                 headings=r"^second deputy prime ministers"),),
           archetype="head_of_government", body="Q14654732",
           create_labels=(("en", "Second Deputy Prime Minister of Saudi Arabia"),
                          ("ar", "النائب الثاني لرئيس مجلس الوزراء السعودي"))),

    # ---- Lane B: the government --------------------------------------------
    Office("prime_minister", "Prime Minister", "Q1153839",
           rosters=(RosterSource("ar", "قائمة رؤساء وزراء السعودية",
                                 headings=ANY_TABLE),),
           categories=(("en", "Prime ministers of Saudi Arabia"),
                       ("ar", "رؤساء وزراء سعوديون"))),
    # The sitting cabinet, routed by the row's own Office cell. `target` is
    # unreachable: the catch-all in PORTFOLIOS fires for any row that names an
    # office, and every row on this page does.
    Office("cabinet", "Council of Ministers", "Q105045827",
           rosters=(RosterSource("en", "Council of Ministers of Saudi Arabia",
                                 headings=r"^membership$"),),
           section_targets=PORTFOLIOS,
           categories=MINISTER_CATEGORIES),
    # The per-portfolio Arabic lists, which carry the history the cabinet page
    # does not. Their heading is "القائمة" — folded "القايمه", since `fold`
    # maps ئ to ي — or absent, hence ANY_TABLE where it is.
    Office("foreign_affairs", "Minister of Foreign Affairs", "Q22689140",
           rosters=(RosterSource("ar", "قائمة وزراء الخارجية (السعودية)",
                                 headings=r"^القايمه$"),),
           categories=(("en", "Foreign ministers of Saudi Arabia"),
                       ("ar", "وزراء خارجية السعودية"))),
    Office("defence", "Minister of Defence", "Q25556795",
           rosters=(RosterSource("ar", "قائمة وزراء دفاع السعودية",
                                 headings=r"قايمه الوزراء"),),
           categories=(("en", "Defense ministers of Saudi Arabia"),
                       ("ar", "وزراء دفاع سعوديون"))),
    Office("information", "Minister of Information and Media", "Q104127725",
           rosters=(RosterSource("ar", "قائمة وزراء الإعلام (السعودية)",
                                 headings=r"^القايمه$"),),
           categories=(("en", "Information ministers of Saudi Arabia"),
                       ("ar", "وزراء إعلام سعوديون"))),
    # Only two of eleven rows carry a Gregorian date; the rest are Hijri-only
    # and land on `no_dates`. The second table on the page is a one-row stub
    # box with no date column, which `office_rows` drops of its own accord.
    Office("interior", "Minister of Interior", "Q114452638",
           rosters=(RosterSource("ar", "قائمة وزراء الداخلية (السعودية)",
                                 headings=ANY_TABLE),),
           categories=(("en", "Interior ministers of Saudi Arabia"),
                       ("ar", "وزراء داخلية السعودية"))),
    # Twenty-one rows, none of them datable — the whole page is in Hijri. Run
    # anyway: the audit's job is to say so, and the twenty-one identified
    # ministers are an item-coverage measurement even when no term can be cited.
    Office("health", "Minister of Health", "Q98934272",
           rosters=(RosterSource("ar", "قائمة وزراء الصحة (السعودية)",
                                 headings=ANY_TABLE),),
           categories=(("en", "Health ministers of Saudi Arabia"),
                       ("ar", "وزراء صحة سعوديون"))),

    # ---- Lane C: the legislature -------------------------------------------
    # 150 members per term, no date column: see SHURA. Three pages, one office,
    # because they are three terms of the same seat.
    Office("shura_member", "Member of the Consultative Assembly", "Q21328601",
           rosters=tuple(
               RosterSource("ar", f"قائمة أعضاء مجلس الشورى السعودي ({suffix})",
                            headings=ANY_TABLE, term=(start, end))
               for suffix, start, end in SHURA
           ),
           categories=(
               ("en", "Members of the Consultative Assembly of Saudi Arabia"),
               ("ar", "أعضاء مجلس الشورى السعودي"),
           )),
    # Q22688060 "President of the Shura Council of Saudi Arabia" exists, carries
    # `P17 = Q851`, and had **no holders at all** — which is why the census that
    # printed only items with a holder did not show it, and why the creation
    # dry run found it by label before anything was minted. Read that as the
    # census's limit rather than the item's: an office with zero holders is
    # exactly the kind this workbench is for.
    Office("shura_chairman", "President of the Consultative Assembly", "Q22688060",
           rosters=(RosterSource("ar", "قائمة رؤساء مجلس الشورى السعودي",
                                 headings=ANY_TABLE),),
           categories=(("ar", "رؤساء مجلس الشورى السعودي"),)),

    # ---- Lane D: the provinces ---------------------------------------------
    # Riyadh is the only one of the thirteen provinces whose article tabulates
    # its governors. The table is dated twice over, "التاريخ الهجري" beside
    # "التاريخ الميلادي", and only the second is read.
    Office("governor_riyadh", "Governor of Riyadh Region", "Q57334761",
           rosters=(RosterSource("ar", "منطقة الرياض",
                                 headings=r"امراء منطقه الرياض"),),
           categories=(("en", "Governors of Riyadh Province"),
                       ("ar", "أمراء منطقة الرياض"))),

    # ---- Lane E: the earlier Saudi states ----------------------------------
    # Every row here routes to "" and becomes an item-creation byproduct: the
    # Imamate of the first Saudi state and the Emirate of Nejd are not the
    # Kingdom's throne, and no rule can invent their items. The modern kings'
    # table on this same page is excluded by `headings` rather than deduplicated,
    # so the `king` office keeps sole ownership of Q850168.
    Office("earlier_states", "Ruler of the earlier Saudi states", "Q850168",
           rosters=(RosterSource("ar", "قائمة حكام آل سعود",
                                 headings=r"تاسيس السلاله|^الدوله السعوديه$"),),
           date_targets=((None, 1932, ""),),
           categories=(("ar", "حكام الدولة السعودية الأولى"),
                       ("ar", "حكام الدولة السعودية الثانية"))),
] + [
    Office(key, en_label, "",
           categories=(("en", category),),
           archetype="provincial_governor",
           jurisdiction=province,
           create_labels=(("en", en_label), ("ar", ar_label)))
    for key, province, en_label, ar_label, category in MISSING_GOVERNORS
]

CAMPAIGN = Campaign(
    name="saudi",
    country_qid="Q851",
    # The Kingdom was proclaimed on 23 September 1932. Terms starting earlier
    # are judged against the target item's own record by `precedent`, and the
    # `earlier_states` office has no item to be judged against at all.
    modern_from=1932,
    offices=OFFICES,
    label_langs=("en", "ar"),
    sibling_wikis=("ar", "en"),
    evidence_verb="lists them in the office",
    # There is no review queue: every rule that does not apply, skips, with its
    # reason recorded. See the module docstring.
    dispositions={
        "namesake": "skip",
        "predecessor_body": "skip",
        "category_only": "skip",
        "no_dates": "skip",
        "believed.held": "skip",
        "uncertain": "skip",
    },
    # One person properly holds several of these at once, permanently. Mohammed
    # bin Salman is Crown Prince *and* Prime Minister; Salman was Crown Prince,
    # Deputy Prime Minister and Minister of Defence together; every king was his
    # own Prime Minister until 2022. Left out, `interim_of` reads each overlap
    # as a covering spell and qualifies a real appointment `P2868 = Q4676846`.
    concurrency_ignore=(
        "Q850168",     # King of Saudi Arabia
        "Q12251224",   # Crown Prince
        "Q19810880",   # deputy crown prince
        "Q1153839",    # Prime Minister
        "Q2375533",    # Custodian of the Two Holy Mosques
        "Q21328601",   # Member of the Consultative Assembly
        "Q105045827",  # Minister of State
    ),
    # Eleven of the sitting cabinet's rows name no portfolio beyond "Minister of
    # State", so a spell already recorded under a specific portfolio must not be
    # restated here.
    generic_targets=("Q105045827",),
    # The kinship lane is not an office: `scripts/sa_family.py` reads a
    # genealogy article rather than a roster, and its P25/P22/P53 records belong
    # in this campaign's one batch.
    extra_verdicts=("saudi_family.jsonl",),
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--office", nargs="*", default=None,
                        help="Office keys to run (default: all)")
    args = parser.parse_args()
    run(make_session(), CAMPAIGN, OUT_DIR, keys=args.office)


if __name__ == "__main__":
    main()
