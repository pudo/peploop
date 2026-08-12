#!/usr/bin/env python
"""Propose P39 and P53 statements for the United Arab Emirates.

    python scripts/ae_offices.py --office ajman fujairah cabinet

The country parameters for `wd/campaign.py`; the method is
`recipes/country_sweep.md`. The UAE is the emptiest country this workbench has
measured — 1,876 people carry `P27 = Q878` and 120 of them carry any `P39` at
all — and the emptiness is not in the ministries. Four things are specific
enough to spell out.

* **The emirate rulers are the point, and their categories are empty.** Six of
  the seven `Rulers of X` categories on en.wikipedia have no members, so the
  roster carries the office channel alone and ar.wikipedia's `حكام …`
  categories supply the second. One en page holds all seven successions in
  eleven tables, which is why every ruler office reads the same page behind its
  own `headings` filter rather than being routed by `section_targets`: an office
  needs its own entry to carry its own `family`.

* **`List of rulers of individual Emirates` also tabulates four pre-union
  polities** — Dibba, Al Hamriyah, Al Heera, Kalba — that have no position item
  and are not emirates. The `headings` filter excludes them by construction;
  creating their ruler items is a byproduct recorded in `tasks/followups.md`.

* **The cabinet is one page with 89 distinct office-cell values.** Only the
  portfolios that have an item are mapped; everything else routes to `""`,
  which files the row as an item-creation byproduct instead of under the
  nearest item that happens to exist. The mapping is ordered specific-first
  because `target_for` takes the first match, and "Minister of State for
  Foreign Affairs" contains "Foreign Affairs".

* **No review tier.** `dispositions` sends every non-applying rule to `skip`, so
  the campaign decides each row and `edit_plan.md` is an account rather than a
  queue. The batch is reviewed once, whole, in the QuickStatements importer.
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.campaign import Campaign, Office, RosterSource, run
from wd.http import REPO_ROOT, make_session

OUT_DIR = REPO_ROOT / "data" / "uae"

#: The one page carrying all seven ruler successions.
RULERS = "List of rulers of individual Emirates of the United Arab Emirates"
#: The cabinet history, 1971 to 2024, in fifteen tables.
CABINETS = "List of cabinets of the United Arab Emirates"
#: A table whose heading names nothing this parser recognises. `List of deputy
#: prime ministers…` has no section heading at all, so this has to match the
#: empty string — and it has to be *truthy*, because `office_rows` reads
#: `source.headings or DEFAULT_HEADINGS` and an empty pattern is silently
#: replaced by the default. Written `r""` first, which cost the Prime Minister
#: office all four of its rows. Same value as `es_offices.ANY_TABLE`.
ANY_TABLE = r".*"


def ruler(
    emirate: str, target: str, family: str, names: tuple, ar_category: str,
    en_category: str = "",
) -> Office:
    """One emirate's rulership, read off its own section of the shared page.

    The section heading is derived from the emirate rather than from the office
    key, so the key stays a slug: it becomes a verdict filename and a `--office`
    argument, and "abu dhabi" made both awkward.
    """
    categories = tuple(
        (lang, cat) for lang, cat in (("ar", ar_category), ("en", en_category)) if cat
    )
    return Office(
        emirate.casefold().replace(" ", "_"), f"Ruler of {emirate}", target,
        rosters=(RosterSource(
            "en", RULERS,
            headings=rf"^emirate of {re.escape(emirate.casefold())}$",
        ),),
        categories=categories,
        family=family,
        family_names=names,
    )


#: Portfolio phrase → position item, first match wins. Ordered so that a
#: "Minister of State for X" cannot be claimed by the pattern for "Minister of
#: X"; the negative lookaheads keep a renamed portfolio from being filed under
#: the item for its successor.
PORTFOLIOS: tuple = (
    # Heads of government first: their cells read "Prime Minister Minister of
    # Defence", and the defence pattern below would otherwise claim the row.
    #
    # Deputy before principal, and by ordering rather than by a lookahead. The
    # first attempt wrote `prime minister(?!.*deputy)`, which looks *forward*
    # from the match while the word "Deputy" sits behind it — so all fifteen
    # "Deputy Prime Minister" rows routed to the Prime Minister item.
    (r"\bdeputy prime minister\b", "Q106181156"),
    (r"\bprime minister\b", "Q30101519"),
    # "Minister of State for …" — all of these precede their bare counterparts.
    (r"state for federal national council affairs", "Q110975280"),
    (r"state for foreign affairs", "Q112645669"),
    (r"state for financial affairs(?! and industry)", "Q113380158"),
    (r"state for defence affairs", "Q113380173"),
    (r"state for public education", "Q113380576"),
    (r"state for international cooperation", "Q113380073"),
    (r"state for government development", "Q113380066"),
    (r"state for advanced technology", "Q113380127"),
    (r"state for artificial intelligence", "Q113380176"),
    (r"state for food and water security", "Q113380525"),
    (r"state for youth", "Q113380129"),
    # Bare portfolios.
    (r"foreign affairs and international cooperation", "Q110964346"),
    (r"minister of foreign affairs", "Q110964346"),
    (r"minister of justice(?!, islamic)", "Q113379893"),
    (r"minister of health", "Q110964361"),
    (r"minister of education(?! and youth)", "Q112116923"),
    (r"minister of interior", "Q110964305"),
    (r"minister of defen[cs]e", "Q110964264"),
    (r"minister of presidential affairs", "Q110964337"),
    (r"climate change and environment", "Q113379896"),
    (r"minister of community development", "Q113379911"),
    (r"minister of culture and youth", "Q110975282"),
    (r"culture and knowledge development", "Q110975281"),
    (r"minister of information and culture", "Q110964354"),
    (r"minister of economy(?! and trade)", "Q113379885"),
    (r"minister of finance(?!,| and)", "Q106181285"),
    (r"energy and infrastructure", "Q113379905"),
    (r"industry and advanced technology", "Q113379907"),
    (r"human resources and emirati[sz]ation", "Q113380142"),
    (r"tolerance and coexistence", "Q113379902"),
    (r"federal supreme council affairs", "Q113380135"),
    (r"minister of cabinet affairs(?! and)", "Q113379897"),
    # Bare "Minister of State" last of the state offices: 41 rows carry it with
    # no portfolio named, and it is a real item rather than a placeholder.
    (r"minister of state(?! for)", "Q113380185"),
    # Anything else is a portfolio with no item. Routing it to "" files the row
    # as a creation byproduct; without this it would land on `target`.
    (r".", ""),
)

OFFICES = [
    # ---- Lane B: the emirate executive -------------------------------------
    ruler("Abu Dhabi", "Q28471402", "Q2615540",
          ("nahyan", "النهيان", "نهيان"),
          "حكام إمارة أبو ظبي", "Sheikhs of Abu Dhabi"),
    ruler("Dubai", "Q110964267", "Q2422081",
          ("maktoum", "المكتوم", "مكتوم"),
          "حكام دبي", "Rulers of Dubai"),
    ruler("Sharjah", "Q110964697", "Q286668",
          ("qasimi", "qassimi", "القاسمي", "قاسمي"),
          "حكام الشارقة"),
    ruler("Ras Al Khaimah", "Q110964704", "Q286668",
          ("qasimi", "qassimi", "القاسمي", "قاسمي"),
          "حكام رأس الخيمة", "Sheikhs of the Emirate of Ras Al Khaimah"),
    ruler("Ajman", "Q110964698", "Q59773372",
          ("nuaimi", "naimi", "النعيمي", "نعيمي"),
          "حكام عجمان"),
    ruler("Fujairah", "Q110964700", "Q60544836",
          ("sharqi", "الشرقي", "شرقي"),
          "حكام الفجيرة"),
    ruler("Umm Al Quwain", "Q110964702", "Q4063314",
          ("mualla", "moalla", "المعلا", "معلا"),
          "حكام أم القيوين"),

    # ---- Lane A: the federal executive ------------------------------------
    Office("president", "President", "Q955006",
           rosters=(RosterSource("en", "President of the United Arab Emirates",
                                 headings=r"list of officeholders"),),
           categories=(("en", "Presidents of the United Arab Emirates"),
                       ("ar", "رؤساء دولة الإمارات العربية المتحدة"))),
    Office("vice_president", "Vice President", "Q48774199",
           rosters=(RosterSource("en", "Vice President of the United Arab Emirates",
                                 headings=r"list of officeholders"),),
           categories=(("en", "Vice presidents of the United Arab Emirates"),
                       ("ar", "نواب رؤساء الإمارات العربية المتحدة"))),
    Office("prime_minister", "Prime Minister", "Q30101519",
           rosters=(RosterSource(
               "en", "List of prime ministers of the United Arab Emirates",
               headings=ANY_TABLE),),
           categories=(("en", "Prime ministers of the United Arab Emirates"),
                       ("ar", "رؤساء وزراء الإمارات العربية المتحدة"))),
    Office("deputy_pm", "Deputy Prime Minister", "Q106181156",
           rosters=(RosterSource(
               "en", "List of deputy prime ministers of the United Arab Emirates",
               headings=ANY_TABLE),),
           categories=(("en", "Deputy prime ministers of the United Arab Emirates"),
                       ("ar", "نواب رؤساء وزراء الإمارات العربية المتحدة"))),
    # The whole cabinet history, routed by the row's own Office cell. `target`
    # is unreachable: the catch-all in PORTFOLIOS fires for any row that names
    # an office at all, and every row on this page does.
    Office("cabinet", "Council of Ministers", "Q113380185",
           rosters=(RosterSource("en", CABINETS, headings=r"cabinet$"),),
           section_targets=PORTFOLIOS,
           categories=(
               ("en", "Government ministers of the United Arab Emirates"),
               ("en", "Foreign ministers of the United Arab Emirates"),
               ("en", "Finance ministers of the United Arab Emirates"),
               ("en", "Interior ministers of the United Arab Emirates"),
               ("en", "Defense ministers of the United Arab Emirates"),
               ("en", "Education ministers of the United Arab Emirates"),
               ("en", "Health ministers of the United Arab Emirates"),
               ("en", "Economy ministers of the United Arab Emirates"),
               ("en", "Energy ministers of the United Arab Emirates"),
               ("en", "Environment ministers of the United Arab Emirates"),
               ("en", "Culture ministers of the United Arab Emirates"),
               ("en", "Information ministers of the United Arab Emirates"),
               ("en", "Labour ministers of the United Arab Emirates"),
               ("en", "Social affairs ministers of the United Arab Emirates"),
               ("en", "Transport ministers of the United Arab Emirates"),
               ("en", "Public works ministers of the United Arab Emirates"),
               ("en", "State ministers of the United Arab Emirates"),
               ("en", "Cabinet affairs ministers of the United Arab Emirates"),
               ("en", "Community development ministers of the United Arab Emirates"),
               ("en", "Higher education ministers of the United Arab Emirates"),
               ("en", "Industry ministers of the United Arab Emirates"),
               ("en", "Tourism ministers of the United Arab Emirates"),
               ("en", "Trade ministers of the United Arab Emirates"),
               ("en", "Communication ministers of the United Arab Emirates"),
               ("en", "Tolerance and Coexistence ministers of the United Arab Emirates"),
               ("en", "Women government ministers of the United Arab Emirates"),
               ("ar", "وزراء حكومة الإمارات العربية المتحدة"),
           )),

    # ---- Lane C: federal bodies -------------------------------------------
    # ar carries the same ten speakers at day precision where en gives bare
    # years, and footnotes every row.
    # The heading pattern is written FOLDED — "رؤساء" reduces to "روساء", since
    # `office_rows` matches against `fold(heading)` and the fold maps ؤ to و.
    # Copied straight off the page it matched nothing and the office lost all
    # ten speakers.
    Office("fnc_speaker", "President of the Federal National Council", "Q115766982",
           rosters=(RosterSource("ar", "المجلس الوطني الاتحادي",
                                 headings=r"روساء المجلس"),),
           categories=(("en", "Speakers of the Federal National Council"),
                       ("ar", "رؤساء المجلس الوطني الاتحادي"))),
]

CAMPAIGN = Campaign(
    name="uae",
    country_qid="Q878",
    # Federation. Ruler terms run to 1761 and are decided against each item's
    # own record by `precedent`, which the ruler items pass and the ministerial
    # items — created for the modern state — do not.
    modern_from=1971,
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
    # In the UAE one person holds several of these permanently and at once:
    # Mohammed bin Rashid is Ruler of Dubai *and* Vice President *and* Prime
    # Minister, and Mohammed bin Zayed is Ruler of Abu Dhabi *and* President.
    # Left out, `interim_of` reads every such overlap as a covering spell and
    # qualifies a genuine appointment `P2868 = Q4676846`.
    concurrency_ignore=(
        "Q28471402",   # Ruler of Abu Dhabi
        "Q110964267",  # Ruler of Dubai
        "Q110964697",  # Ruler of Sharjah
        "Q110964698",  # Ruler of Ajman
        "Q110964700",  # Ruler of Fujairah
        "Q110964702",  # Ruler of Umm al-Quwain
        "Q110964704",  # Ruler of Ras al-Khaimah
        "Q955006",     # President of the UAE
        "Q48774199",   # Vice President of the UAE
        "Q30101519",   # Prime Minister of the UAE
        "Q106181156",  # Deputy Prime Minister of the UAE
        "Q21328608",   # member of the Federal National Council
    ),
    # 41 cabinet rows name no portfolio beyond "Minister of State", so a spell
    # already recorded under a specific portfolio must not be restated here.
    generic_targets=("Q113380185",),
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--office", nargs="*", default=None,
                        help="Office keys to run (default: all)")
    args = parser.parse_args()
    run(make_session(), CAMPAIGN, OUT_DIR, keys=args.office)


if __name__ == "__main__":
    main()
