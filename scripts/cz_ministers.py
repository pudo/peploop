#!/usr/bin/env python
"""Propose P39 statements for the Czech offices in wd_categories.yml.

    python scripts/cz_ministers.py --office foreign interior justice

The country parameters for `wd/campaign.py`; the method is
`recipes/category_check.md`. Despite the name this also carries the three
non-ministerial offices the Czech yml block names (president, prime minister,
Constitutional Court), because they are parameterised identically.

Czechia is the best-cased country this engine has run against, and the awkward
part is not the parsing:

* **Every portfolio has a dedicated list article.** cs.wikipedia keeps 22
  `Seznam ministrů <portfolio> České republiky` pages, all built from one
  template — a dated table per era with the appointing cabinet and the party.
  No bullet lists, no ministry-article scraping.
* **Two eras share every office name and every item.** The tables separate
  "V rámci československé federace" (the Czech Socialist Republic, then the
  Czech Republic as a federal unit, 1969–1992) from "V rámci samostatné
  republiky" (1993 on). The Wikidata items are labelled for the Czech
  Republic, and the community *already* files federal-era holders on them —
  Agriculture carries 10 pre-1993 terms of 27, Education 9 of 31, both back to
  1969. That makes the era a settled-looking convention rather than an obvious
  one, so `REGIMES` routes those rows to review instead of the batch and the
  brief carries the tally; promoting them is a one-line change here.
* **Three list articles carry a sibling office's table**, which is why
  `section_targets` exists: the abolished federal ministries of industry and of
  trade have their own items, and the minister of economy sits on the regional
  development page.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.campaign import Campaign, Office, RosterSource, run
from wd.http import REPO_ROOT, make_session

OUT_DIR = REPO_ROOT / "data" / "czechia"

#: Table headings naming an era whose holders are a continuity judgment. The
#: Protectorate cabinets sit on the prime-minister page and are a different
#: state altogether; the federal-era Czech governments are the same institution
#: under a different constitution, which is exactly why they need a ruling.
REGIMES = (
    (r"Protektorát", "protectorate"),
    (r"federac|socialistická republika", "federal_cr"),
)


def minister(
    key: str, label: str, target: str, portfolio: str,
    headings: str = None, **kwargs
) -> Office:
    """An office whose list article and category follow the cs.wikipedia mould.

    `portfolio` is the shared part of both names — "vnitra" yields the page
    "Seznam ministrů vnitra České republiky" and the category "Ministři vnitra
    České republiky".
    """
    return Office(
        key,
        label,
        target,
        rosters=(
            RosterSource(
                "cs", f"Seznam ministrů {portfolio} České republiky",
                headings=headings,
            ),
        ),
        categories=(("cs", f"Ministři {portfolio} České republiky"),),
        regime_sections=REGIMES,
        **kwargs,
    )


OFFICES = [
    minister("foreign", "Foreign Affairs", "Q2501396", "zahraničních věcí"),
    minister("interior", "Internal Affairs", "Q20058795", "vnitra"),
    minister("finance", "Finance", "Q2207925", "financí"),
    # A Czech defence ministry only exists from 1993 — defence was federal
    # before that — so this page has a single unheaded table, which the default
    # heading pattern has nothing to match against.
    minister("defence", "Defence", "Q25040919", "obrany", headings=r".*"),
    minister("justice", "Justice", "Q26197353", "spravedlnosti"),
    minister("health", "Health", "Q45750372", "zdravotnictví"),
    minister("education", "Education, Youth and Sports", "Q30312984",
             "školství, mládeže a tělovýchovy"),
    minister("agriculture", "Agriculture", "Q28808262", "zemědělství"),
    minister("culture", "Culture", "Q45843918", "kultury"),
    minister("transport", "Transport", "Q45754140", "dopravy"),
    minister("labour", "Labour and Social Affairs", "Q27479703",
             "práce a sociálních věcí"),
    minister("environment", "Environment", "Q33702144", "životního prostředí"),
    minister("europe", "European Affairs", "Q12052800", "pro evropské záležitosti"),
    minister("human_rights", "Human Rights", "Q47519610", "pro lidská práva"),
    # The federal ministries of industry and of trade & tourism were merged in
    # 1992; both survive as their own items, and both tables sit on the merged
    # office's page.
    minister("industry", "Industry and Trade", "Q25507811", "průmyslu a obchodu",
             section_targets=(
                 (r"průmyslu v rámci federace", "Q110408550"),
                 (r"obchodu a cestovního ruchu", "Q110409158"),
             )),
    # Ditto the minister of economy (1990–1996), whose portfolio became
    # regional development.
    minister("regional", "Regional Development", "Q25515749", "pro místní rozvoj",
             section_targets=((r"hospodářství", "Q110420088"),)),
    # The list article's own title is the exception to the naming mould.
    Office("no_portfolio", "Without Portfolio", "Q59773497",
           rosters=(RosterSource("cs", "Seznam ministrů České republiky bez portfeje"),),
           categories=(("cs", "Ministři bez portfeje České republiky"),),
           regime_sections=REGIMES),
    Office("president", "President", "Q1819381",
           rosters=(RosterSource("cs", "Seznam prezidentů České republiky"),),
           categories=(("cs", "Prezidenti České republiky"),),
           regime_sections=REGIMES),
    # This page heads its tables by state rather than by office: "Protektorát
    # Čechy a Morava", "Česká socialistická republika …", "Česká republika (od
    # 1993)". REGIMES then routes the first two out of the batch.
    Office("pm", "Prime Minister", "Q3409229",
           rosters=(RosterSource("cs", "Seznam premiérů Česka",
                                 headings=r"protektorat|ceska"),),
           categories=(("cs", "Premiéři Česka"),),
           regime_sections=REGIMES),
    Office("constitutional_court", "Constitutional Court judge", "Q59773473",
           rosters=(RosterSource("cs", "Seznam soudců Ústavního soudu České republiky"),),
           categories=(("cs", "Soudci Ústavního soudu České republiky"),),
           regime_sections=REGIMES),
    # Wikidata has no item for either supreme court's judges, so 45 category
    # members have nowhere to put a statement. Both categories are the yml
    # block's own, and both courts are real and current; the items are simply
    # missing. `scripts/create_offices.py` mints them.
    Office("supreme_court", "Supreme Court judge", "",
           archetype="supreme_judge",
           body="Q7645005",  # Supreme Court of the Czech Republic
           create_labels=(
               ("en", "judge of the Supreme Court of the Czech Republic"),
               ("cs", "soudce Nejvyššího soudu České republiky"),
           ),
           rosters=(RosterSource("cs", "Nejvyšší soud České republiky"),),
           categories=(("cs", "Soudci Nejvyššího soudu České republiky"),)),
    Office("supreme_admin_court", "Supreme Administrative Court judge", "",
           archetype="supreme_judge",
           body="Q7644797",  # Supreme Administrative Court of the Czech Republic
           create_labels=(
               ("en", "judge of the Supreme Administrative Court of the Czech Republic"),
               ("cs", "soudce Nejvyššího správního soudu České republiky"),
           ),
           rosters=(RosterSource("cs", "Nejvyšší správní soud České republiky"),),
           categories=(("cs", "Soudci Nejvyššího správního soudu České republiky"),)),
    # The list is of *ministers for legislation*; the only item Wikidata has is
    # the chair of the Government Legislative Council, which the same people
    # held but which is not the same office. Nothing here is batched.
    Office("legislation", "Legislation / Legislative Council", "Q59773536",
           rosters=(RosterSource("cs", "Seznam ministrů pro legislativu České republiky"),),
           categories=(("cs", "Předsedové Legislativní rady vlády České republiky"),),
           regime_sections=REGIMES,
           hold="minister_vs_council_chair"),
]

CAMPAIGN = Campaign(
    name="czechia",
    country_qid="Q213",
    # Independence, and where cs.wikipedia splits every roster table. A handful
    # of rows start in July 1992 — the Klaus I cabinet, which carried on across
    # the split — and land in `historical` for the same ruling.
    modern_from=1993,
    offices=OFFICES,
    label_langs=("cs", "en"),
    sibling_wikis=("cs", "sk", "en"),
    evidence_verb="lists them in the office",
    # The Czech Republic of 1969–1992 is the same state as today's under an
    # earlier constitution — the ministries were never abolished and refounded
    # — so its rows are judged on each target item's own record. The
    # Protectorate is not, and stays out.
    continuous_eras=("federal_cr",),
    # Nearly every Czech minister sits in parliament or on a council at the same
    # time, so those overlaps say nothing about whether a short spell was cover.
    concurrency_ignore=(
        "Q19803234",   # Member of the Chamber of Deputies
        "Q18941264",   # Member of the Senate
        "Q25265211",   # member of the Czech National Council
        "Q108899569",  # member of a Czech municipal council
        "Q27830380",   # Prague City Assembly member
        "Q27830328",   # regional council member
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
