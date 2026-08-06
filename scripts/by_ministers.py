#!/usr/bin/env python
"""Propose P39 statements for the Belarusian ministries in wd_categories.yml.

    python scripts/by_ministers.py --office foreign defence justice

The country parameters for `wd/campaign.py`; the method is
`recipes/category_check.md`. Belarus differs from the Ecuador run in three
ways, all encoded below:

* **The English categories are nearly empty** (2–35 members) while their
  Belarusian and Russian siblings hold 10× that, so every office harvests its
  interwiki siblings via `sibling_category`.
* **Rosters live on the office or ministry article**, not on dedicated list
  pages: `Министр иностранных дел Республики Беларусь` tabulates its holders,
  while most ministries list them as bullets under "Министры"/"Руководство".
* **Three regimes share one office name.** The 1918 Belarusian People's
  Republic, the Byelorussian SSR and the Republic of Belarus all had a
  "minister of X", and the modern Wikidata items are for the last of them.
  Roster sections and the wikis' own БНР/БССР categories mark which is which;
  anything not the modern republic is held for review.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.campaign import Campaign, Office, RosterSource, run
from wd.http import REPO_ROOT, make_session

OUT_DIR = REPO_ROOT / "data" / "belarus"

#: Sections and headings naming an office of an earlier polity.
REGIMES = (
    (r"БССР|Беларускай ССР|Белорусской ССР|BSSR|Соveт|Совет народных комиссаров"
     r"|нарком|Народны камісар|Народный комиссар", "byelorussian_ssr"),
    (r"БНР|Беларускай Народнай Рэспублікі|Белорусской Народной Республики", "bnr"),
    (r"Літбел|Литбел", "litbel"),
)

OFFICES = [
    Office("pm", "Prime Minister", "Q12379704",
           rosters=(RosterSource("be", "Прэм’ер-міністр Рэспублікі Беларусь"),),
           sibling_category="Prime_ministers_of_Belarus",
           regime_sections=REGIMES),
    # No roster page names the deputy premiers, and the category mixes the rank
    # with First Deputy Prime Minister (Q18690166), so nothing here is batched.
    Office("deputy_pm", "Deputy Prime Minister", "Q18690228",
           sibling_category="Deputy_prime_ministers_of_Belarus",
           regime_sections=REGIMES,
           hold="no_roster_rank_unclear"),
    Office("foreign", "Foreign Affairs", "Q2045068",
           rosters=(RosterSource("ru", "Министр иностранных дел Республики Беларусь"),),
           sibling_category="Foreign_ministers_of_Belarus",
           regime_sections=REGIMES),
    Office("defence", "Defence", "Q44035369",
           rosters=(RosterSource("be", "Міністр абароны Рэспублікі Беларусь"),),
           sibling_category="Defence_ministers_of_Belarus",
           regime_sections=REGIMES),
    Office("finance", "Finance", "Q106510813",
           rosters=(RosterSource("ru", "Министерство финансов Республики Беларусь",
                                 kind="bullets"),),
           sibling_category="Finance_ministers_of_Belarus",
           regime_sections=REGIMES),
    Office("interior", "Internal Affairs", "Q100699741",
           rosters=(RosterSource("ru", "Министерство внутренних дел Республики Беларусь",
                                 kind="bullets"),),
           sibling_category="Interior_ministers_of_Belarus",
           regime_sections=REGIMES),
    Office("justice", "Justice", "Q106510814",
           rosters=(RosterSource("be", "Міністры юстыцыі Рэспублікі Беларусь"),),
           sibling_category="Justice_ministers_of_Belarus",
           regime_sections=REGIMES),
    Office("health", "Health Care", "Q89775465",
           rosters=(RosterSource("ru", "Министерство здравоохранения Республики Беларусь",
                                 kind="bullets"),),
           sibling_category="Health_ministers_of_Belarus",
           regime_sections=REGIMES),
    Office("transport", "Transport and Communications", "Q60676745",
           rosters=(RosterSource("ru",
                                 "Министерство транспорта и коммуникаций Республики Беларусь",
                                 kind="bullets"),),
           sibling_category="Transport_ministers_of_Belarus",
           regime_sections=REGIMES),
    Office("telecom", "Communications and Informatisation", "Q28598480",
           rosters=(RosterSource("ru",
                                 "Министерство связи и информатизации Республики Беларусь",
                                 kind="bullets"),),
           sibling_category="Communications_ministers_of_Belarus",
           regime_sections=REGIMES),
    Office("industry", "Industry", "Q106508605",
           rosters=(RosterSource("ru", "Министерство промышленности Республики Беларусь",
                                 kind="bullets"),),
           sibling_category="Industry_ministers_of_Belarus",
           regime_sections=REGIMES),
    Office("information", "Information", "Q106399613",
           rosters=(RosterSource("ru", "Министерство информации Республики Беларусь",
                                 kind="bullets"),),
           sibling_category="Information_ministers_of_Belarus",
           regime_sections=REGIMES),
]

CAMPAIGN = Campaign(
    name="belarus",
    country_qid="Q184",
    # Independence: the ministry items are the Republic's, not the BSSR's.
    modern_from=1991,
    offices=OFFICES,
    label_langs=("ru", "be", "en"),
    sibling_wikis=("ru", "be", "be_x_old", "uk"),
    evidence_verb="lists them as minister",
    regime_categories=(
        ("be", "Міністры_БССР", "byelorussian_ssr"),
        ("ru", "Народные_комиссары_и_министры_Белорусской_ССР", "byelorussian_ssr"),
        ("en", "People's_commissars_and_ministers_of_the_Byelorussian_Soviet_Socialist_Republic",
         "byelorussian_ssr"),
        ("be", "Міністры_БНР", "bnr"),
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
