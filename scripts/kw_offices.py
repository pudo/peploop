#!/usr/bin/env python
"""Propose P39 (and P53) statements for Kuwait.

    python scripts/kw_offices.py --office crown_prince oil assembly_2024

The country parameters for `wd/campaign.py`; the method is
`recipes/country_sweep.md` and `plans/kuwait_sweep.md` records what the survey
measured. Kuwait is the **Ecuador profile** — the position items nearly all
exist and carry a handful of holders each (2,003 people hold `P27 = Q817`, 288
of them any `P39`) — and six things about it are specific enough to spell out.

* **ar.wikipedia is the channel, not a supplement.** en.wikipedia has no
  category at all for the emirs, the crown princes, the House of Sabah, the
  Assembly's members or its speakers, and every portfolio's dated succession
  lives in the *ministry* article on ar.wikipedia. `ar:أعضاء مجلس الأمة
  الكويتي` alone has 437 members across 22 per-term subcategories.

* **Two offices sitelink to a list article, not to themselves.** `en:Emir of
  Kuwait` resolves to Q246932 and `en:Prime Minister of Kuwait` to Q2035020,
  both correctly typed as Wikimedia lists. Every `target` here comes from the
  holder census, never from an article title — the trap Saudi Arabia's Second
  Deputy Prime Ministership set from the other direction.

* **The Assembly rolls date no row, and the term comes from the election.**
  Four of the 24 per-term pages tabulate their members (2016, 2020, 2023,
  2024): 50-odd wikilinked names each, no date column. `RosterSource.term`
  supplies the span from Wikidata's own `P585` on the election items — see
  `ASSEMBLY` below, where the 2020 roll's end is deliberately the *earlier* of
  two defensible readings.

* **No `P2937`.** Term items exist for every election year and would be the
  interesting qualifier, but only 19 of the 228 existing seat statements carry
  one. Recipe §10.3: a minority practice is not mass-asserted.

* **The crown-prince list is two offices in one table.** Its first section is
  `نائب حاكم الكويت (1921–1961)` — Deputy Ruler, a distinct office with no
  item — so `section_targets` routes those rows to `""` and they become
  creation byproducts instead of landing on the heir apparent's item.

* **The finance ministry's own table writes half its ranges backwards.**
  `ar:وزارة المالية (الكويت)` dates eight of its 29 rows "1965-1959",
  "1981-1967" — an RTL authoring artifact, and the rows chain correctly when
  read the other way round. The lane is left out rather than fixed by a global
  "swap if reversed" in `parse_period`, which would touch every campaign and
  could mask a real parse defect. It is a followup with its diagnosis, not a
  padded lane.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.campaign import Campaign, Office, RosterSource, run
from wd.http import REPO_ROOT, make_session

OUT_DIR = REPO_ROOT / "data" / "kuwait"

#: A table whose heading names nothing the parser recognises, or none at all.
#: Must be truthy — `office_rows` reads `source.headings or DEFAULT_HEADINGS`
#: and an empty pattern is silently replaced by the default. Same value as
#: `ae_offices.ANY_TABLE`.
ANY_TABLE = r".*"

#: The cabinet's own article, which carries four successions in four tables:
#: prime ministers, first deputy prime ministers, deputy prime ministers and
#: the ministries themselves. Each office reads it behind its own `headings`
#: pattern — two offices sharing one page double-propose it otherwise (§7) —
#: and the fifth table, `التشكيلات الوزاريه`, lists *cabinets* rather than
#: people and is matched by none of them.
CABINET = "مجلس الوزراء الكويتي"

#: Assembly membership rolls: (page suffix, start, end).
#:
#: The pages carry 50-odd wikilinked members and no date column at all, so the
#: term is declared here rather than parsed, at **day precision**, from
#: Wikidata's `P585` on the election items — the same shape as Saudi Arabia's
#: Shura rolls, which had to declare theirs in Hijri years.
#:
#: Each term ends where the next election falls, which is as attested as the
#: start and keeps a member re-elected twice from carrying two open-ended
#: statements for one seat.
#:
#: **The 2020 boundary understates on purpose.** That Assembly was dissolved in
#: August 2022; the constitutional court annulled its successor's election in
#: March 2023 and reinstated the 2020 members until May 2023. "Elected 2020,
#: served to the 2022 election" is the continuous, attested half of that story;
#: one unbroken span to 2023 would be wrong for the eight months the 2022
#: Assembly actually sat. The 2024 end is not an election but the Emir's
#: dissolution of 10 May 2024, when parliament was suspended.
#:
#: The other twenty pages carry no member table — 2013 tabulates committee
#: elections and 2022 five names — so eighteen terms are reachable only through
#: their category, land on `category_only`, and skip. That is the ceiling, not
#: an underperforming lane.
ASSEMBLY = (
    ("2016", "2016-11-26", "2020-12-05"),  # Q27921330 → Q39088670
    ("2020", "2020-12-05", "2022-09-29"),  # Q39088670 → Q112957772
    ("2023", "2023-06-06", "2024-04-04"),  # Q104032248 → Q124707230
    ("2024", "2024-04-04", "2024-05-10"),  # Q124707230 → dissolution
)

#: Every per-term subcategory of `ar:أعضاء مجلس الأمة الكويتي`, listed rather
#: than expanded because `build_people` harvests at depth 0 and all 1,077
#: memberships sit one level down. Candidate generators only: the roster row
#: decides, and a term with no roster is `category_only`.
ASSEMBLY_CATEGORIES = tuple(
    ("ar", f"أعضاء مجلس الأمة الكويتي {term}")
    for term in ("1962", "1963", "1967", "1971", "1975", "1981", "1985", "1992",
                 "1996", "1999", "2003", "2006", "2008", "2009", "فبراير 2012",
                 "ديسمبر 2012", "2013", "2016", "2020", "2022", "2023", "2024")
) + (("ar", "أعضاء مجلس الأمة الكويتي"),)

#: The two categories that put a Kuwaiti soldier forward. Neither is a claim to
#: any particular command; the roster decides which.
MILITARY = (("ar", "عسكريون كويتيون"),)

OFFICES = [
    # ---- Lane A: the throne -------------------------------------------------
    # 17 of 17 rulers are already recorded, to the day, so this office is here
    # for the backtest and for the P53 backfill rather than for statements.
    # The page's other table — twelve Emirs of Bani Khalid, 1669–1796 — is a
    # different polity's office with no item, and is excluded by `headings`
    # rather than routed: it has no `date_targets` window that would not also
    # claim the Sabah emirs, whose own succession starts in 1752.
    Office("emir", "Emir of Kuwait", "Q100877419",
           rosters=(RosterSource("en", "Emir of Kuwait",
                                 headings=r"^emirs of kuwait"),),
           categories=(("ar", "حكام الكويت"),),
           family="Q291639",
           family_names=("Sabah", "Al Sabah", "الصباح", "آل صباح")),
    # Q22690742 has **zero** holders and eight rows waiting, which is the
    # single emptiest office this campaign found. Its category does not exist in
    # either language, so the roster is the only channel — and every row is
    # wikilinked, which is what `roster_only.attested` asks for.
    Office("crown_prince", "Crown Prince of Kuwait", "Q22690742",
           rosters=(RosterSource("ar", "قائمة ولاة عهد الكويت",
                                 headings=ANY_TABLE),),
           # The 1921–1961 section is the Deputy Rulership, a distinct office
           # with no item; its two rows become creation byproducts.
           section_targets=((r"نايب حاكم", ""),),
           family="Q291639",
           family_names=("Sabah", "Al Sabah", "الصباح", "آل صباح")),

    # ---- Lane B: the government --------------------------------------------
    Office("prime_minister", "Prime Minister", "Q30100649",
           rosters=(RosterSource("ar", "قائمة رؤساء وزراء الكويت",
                                 headings=ANY_TABLE),),
           categories=(("ar", "رؤساء مجلس الوزراء الكويتي"),
                       ("en", "Prime ministers of Kuwait")),
           family="Q291639",
           family_names=("Sabah", "Al Sabah", "الصباح", "آل صباح")),
    # 44 rows, all wikilinked and dated to the day. The table's own `office`
    # column names each holder's concurrent portfolio, which is *not* routed:
    # the deputy premiership is the statement, and the portfolio is already the
    # subject of its own office below.
    Office("deputy_pm", "Deputy Prime Minister", "Q110526533",
           rosters=(RosterSource("ar", CABINET,
                                 headings=r"نواب رييس مجلس الوزراء"),),
           categories=(("ar", "نواب رؤساء وزراء الكويت"),
                       ("en", "Deputy prime ministers of Kuwait"))),

    # ---- Lane C: the portfolios, from the ministry articles -----------------
    Office("foreign_affairs", "Minister of Foreign Affairs", "Q110525652",
           rosters=(RosterSource("ar", "وزارة الخارجية (الكويت)",
                                 headings=r"قايمه وزراء الخارجيه"),),
           categories=(("ar", "وزراء خارجية كويتيون"),
                       ("en", "Foreign ministers of Kuwait"))),
    # The heading says "ministers of interior **and deputy prime ministers**",
    # which is why `concurrency_ignore` names both items: the two offices are
    # held together as a matter of course here.
    Office("interior", "Minister of Interior", "Q110526608",
           rosters=(RosterSource("ar", "وزارة الداخلية (الكويت)",
                                 headings=r"وزراء الداخليه"),),
           categories=(("ar", "وزراء داخلية كويتيون"),
                       ("en", "Interior ministers of Kuwait"))),
    # Two tables, split at the ministry's founding; only the later one is this
    # item's. "قبل التاسيس" (before the founding) is the pre-1962 defence
    # department and is left to `precedent` nowhere — it is simply not read.
    Office("defence", "Minister of Defense", "Q104382486",
           rosters=(RosterSource("ar", "وزارة الدفاع (الكويت)",
                                 headings=r"^بعد التاسيس$"),),
           categories=(("ar", "وزراء دفاع كويتيون"),
                       ("en", "Defence ministers of Kuwait"))),
    Office("oil", "Minister of Oil", "Q108599663",
           rosters=(RosterSource("ar", "وزارة النفط (الكويت)",
                                 headings=r"وزراء النفط"),),
           categories=(("ar", "وزراء نفط كويتيون"),
                       ("en", "Oil ministers of Kuwait"))),
    Office("health", "Minister of Health", "Q110526428",
           rosters=(RosterSource("ar", "وزارة الصحة (الكويت)",
                                 headings=r"وزراء الصحه"),),
           categories=(("ar", "وزراء صحة كويتيون"), ("ar", "وزراء صحة الكويت"),
                       ("en", "Health ministers of Kuwait"))),
    # 39 rows against five recorded — the widest single gap in the country.
    Office("electricity_water", "Minister of Electricity and Water",
           "Q110526402",
           rosters=(RosterSource("ar", "وزارة الكهرباء والماء والطاقة المتجددة (الكويت)",
                                 headings=r"سجل الوزراء"),),
           categories=(("ar", "وزراء كهرباء وماء كويتيون"),
                       ("ar", "وزراء مياه وكهرباء في الكويت"),
                       ("en", "Electricity and water ministers of Kuwait"))),
    Office("information", "Minister of Information", "Q110526654",
           rosters=(RosterSource("ar", "وزارة الإعلام (الكويت)",
                                 headings=r"الوزراء الحاليون والسابقون"),),
           categories=(("ar", "وزراء إعلام كويتيون"),
                       ("en", "Information ministers of Kuwait"))),
    Office("awqaf", "Minister of Awqaf and Islamic Affairs", "Q110525626",
           rosters=(RosterSource("ar", "وزارة الأوقاف والشؤون الإسلامية (الكويت)",
                                 headings=r"^الوزراء$"),),
           categories=(("ar", "وزراء أوقاف كويتيون"),
                       ("en", "Endowments and Islamic affairs ministers of Kuwait"))),
    # The only lane whose source is an en bullet list rather than a table, and
    # the weaker sourcing shows: bullets rarely footnote their rows, so these
    # statements cite the roster permalink rather than a citation (§4).
    Office("justice", "Minister of Justice", "Q110526408",
           rosters=(RosterSource("en", "Ministry of Justice (Kuwait)",
                                 kind="bullets", headings=ANY_TABLE),),
           categories=(("ar", "وزراء عدل كويتيون"), ("ar", "وزراء عدل الكويت"),
                       ("en", "Justice ministers of Kuwait"))),

    # ---- Lane D: the ministers of state ------------------------------------
    # Five dedicated ar list articles, one per portfolio. The sixth,
    # `قائمة وزراء الدولة لشؤون الإتصالات`, carries no table at all.
    Office("mos_cabinet_affairs", "Minister of State for Cabinet Affairs",
           "Q109244175",
           rosters=(RosterSource("ar", "قائمة وزراء الدولة لشؤون مجلس الوزراء (الكويت)",
                                 headings=ANY_TABLE),),
           categories=(("ar", "وزراء شؤون مجلس الوزراء كويتيون"),
                       ("en", "Cabinet affairs ministers of Kuwait"))),
    Office("mos_assembly_affairs",
           "Minister of State for National Assembly Affairs", "Q110529897",
           rosters=(RosterSource("ar", "قائمة وزراء الدولة لشؤون مجلس الأمة (الكويت)",
                                 headings=ANY_TABLE),),
           categories=(("ar", "وزراء شؤون مجلس الأمة كويتيون"),
                       ("ar", "وزراء دولة لشؤون مجلس الأمة كويتيون"))),
    Office("mos_municipal", "Minister of State for Municipal Affairs",
           "Q110529873",
           rosters=(RosterSource("ar", "قائمة وزراء الدولة لشؤون البلدية (الكويت)",
                                 headings=ANY_TABLE),),
           categories=(("ar", "وزراء بلدية كويتيون"),)),
    Office("mos_housing", "Minister of State for Housing Affairs", "Q112161663",
           rosters=(RosterSource("ar", "قائمة وزراء الدولة لشؤون الإسكان (الكويت)",
                                 headings=ANY_TABLE),),
           categories=(("ar", "وزراء إسكان كويتيون"), ("ar", "وزراء إسكان الكويت"),
                       ("en", "Housing ministers of Kuwait"))),
    Office("mos_economic", "Minister of State for Economic Affairs",
           "Q112161634",
           rosters=(RosterSource("ar", "قائمة وزراء الدولة للشؤون الاقتصادية (الكويت)",
                                 headings=ANY_TABLE),),
           categories=(("ar", "وزراء اقتصاد الكويت"),
                       ("en", "Economy ministers of Kuwait"))),

    # ---- Lane E: the legislature -------------------------------------------
    Office("speaker", "Speaker of the National Assembly", "Q110532419",
           rosters=(RosterSource("en", "List of speakers of Kuwait National Assembly",
                                 headings=ANY_TABLE),),
           categories=(("ar", "رؤساء مجلس الأمة الكويتي"),)),
] + [
    # One office per roll rather than one office with four sources: `term`
    # belongs to the source, and giving each roll its own key makes the audit
    # and the backtest report per term, which is the unit a wrong boundary
    # would be wrong in.
    Office(f"assembly_{year}", f"Member of the National Assembly ({year})",
           "Q21295986",
           rosters=(RosterSource("ar", f"مجلس الأمة الكويتي {year}",
                                 headings=ANY_TABLE, term=(start, end)),),
           categories=ASSEMBLY_CATEGORIES)
    for year, start, end in ASSEMBLY
] + [
    # ---- Lane F: the security services -------------------------------------
    # Its holder column is headed with the office ("رئيس الأركان") and the
    # appointing defence minister sits in a column of its own; both needed a
    # `wd/roster.py` key before this page yielded a single date.
    Office("chief_of_staff", "Chief of the General Staff", "Q19903817",
           rosters=(RosterSource("ar", "رئاسة الأركان العامة للجيش الكويتي",
                                 headings=r"روساء الاركان العامه"),),
           categories=MILITARY),
    Office("national_guard", "Commander of the Kuwait National Guard",
           "Q128977631",
           rosters=(RosterSource("ar", "الحرس الوطني (الكويت)",
                                 headings=r"^روساء الحرس الوطني$"),),
           categories=MILITARY,
           family="Q291639",
           family_names=("Sabah", "Al Sabah", "الصباح", "آل صباح")),
]

CAMPAIGN = Campaign(
    name="kuwait",
    country_qid="Q817",
    # The constitution was promulgated in November 1962 and the first cabinet
    # took office on 17 January 1962. Earlier rows are department heads of the
    # pre-independence administration and are judged against each target item's
    # own record by `precedent`, never by this constant.
    modern_from=1962,
    offices=OFFICES,
    label_langs=("en", "ar"),
    sibling_wikis=("ar", "en"),
    evidence_verb="lists them in the office",
    # There is no review queue: every rule that does not apply, skips, with its
    # reason recorded. See `recipes/country_sweep.md`.
    dispositions={
        "namesake": "skip",
        "predecessor_body": "skip",
        "category_only": "skip",
        "no_dates": "skip",
        "believed.held": "skip",
        "uncertain": "skip",
    },
    # Kuwaiti practice is that one man holds several of these at once,
    # permanently and legitimately. The Crown Prince is routinely Prime
    # Minister; the interior and defence ministries are held *ex officio* with
    # the deputy premiership, which is why both ministry articles head their
    # tables "ministers of X and deputy prime ministers". Left out, `interim_of`
    # reads each overlap as a covering spell and qualifies a real appointment
    # `P2868 = Q4676846`.
    concurrency_ignore=(
        "Q100877419",  # emir of Kuwait
        "Q22690742",   # Crown Prince
        "Q30100649",   # Prime Minister
        "Q110526533",  # Deputy Prime Minister
        "Q21295986",   # Member of the National Assembly
        "Q110526608",  # Minister of Interior
        "Q104382486",  # Minister of Defense
        "Q110525652",  # Minister of Foreign Affairs
    ),
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--office", nargs="*", default=None,
                        help="Office keys to run (default: all)")
    args = parser.parse_args()
    run(make_session(), CAMPAIGN, OUT_DIR, keys=args.office)


if __name__ == "__main__":
    main()
