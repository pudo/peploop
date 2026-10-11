#!/usr/bin/env python
"""Propose P39 (and P53) statements for Qatar.

    python scripts/qa_offices.py --office emir crown_prince justice

The country parameters for `wd/campaign.py`; the method is
`recipes/country_sweep.md` and `plans/qatar_sweep.md` records what the survey
measured. Qatar looks like the Ecuador profile from its coverage numbers — 31
domestic position items carrying about 35 `P39` statements between them, one
holder each — but it is not, and five things about it are worth spelling out.

* **`modern_from` is 1850, and that is what makes the throne lane exist.**
  `precedent_allows` needs three dated holder statements earlier than the
  cutoff; the Emir item has three holders in total, starting 1972, 1995 and
  2013. At any cutoff after 1972 every pre-modern emir is skipped
  `early.unsupported`, which is twelve of the roughly thirty statements a
  roster sweep can produce here. Qatar has one continuous polity since the Al
  Thani established themselves at Doha — no predecessor state whose offices
  need items of their own — so the rows are `modern` and clear the ordinary
  two-channel bar instead. `Precedent.covers()` still refuses a term earlier
  than an item's own declared inception, which Q25711499 sets to 1851.

* **Qatar publishes almost no ministerial rosters.** Two of the thirty-two
  ministry articles across both wikis carry a dated list of ministers; the
  other thirty carry none. The portfolios below are therefore the whole of what
  a roster can reach, and every other ministry waits on the infobox channel.

* **None of Qatar's headings match `DEFAULT_HEADINGS`.** "List of rulers",
  "Governors", "Deputy Prime Ministers" and "List of ministers" are all invisible
  to it, so every source here names its own. An office whose heading pattern
  misses does not fail — it silently parses zero rows (§7 #24).

* **The Crown Prince roster is Arabic-only and has no category.** `en:Crown
  Prince of Qatar` does not exist and neither wiki keeps a crown-prince
  category, so this is the one lane running on a single channel: the roster
  alone. Its rows still have to clear `modern.two_channel`, which they do on
  the wikilink identity, but there is no category behind them and the lane is
  reported small rather than widened to compensate.

* **The spine is concurrent by design.** The sitting prime minister is
  simultaneously foreign minister; Khalid bin Mohammad Al Attiyah held foreign
  affairs, the deputy premiership and defence together; Khalid bin Khalifa took
  the interior ministry and the premiership on the same day. Nine such pairs are
  on record. Left out of `concurrency_ignore`, `interim_of` reads each overlap
  as a covering spell and stamps `P2868 = Q4676846` on a real appointment.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.campaign import Campaign, Office, RosterSource, run
from wd.http import REPO_ROOT, make_session

OUT_DIR = REPO_ROOT / "data" / "qatar"

#: The ruling house, for the `P53` backfill the throne lanes carry. Matched
#: against name *tokens*, never as a substring.
THANI = "Q2502270"
THANI_NAMES = ("thani", "ثاني")


def portfolio(
    key: str, label: str, target: str, en_category: str, ar_category: str,
    pattern: str,
) -> Office:
    """A ministry with no roster anywhere: its holders come from their own boxes.

    The catch-all is written `r""` — an empty pattern, which `re.search` matches
    against anything and which routes to the empty string, meaning *no item*.
    That is the point: one person's infobox lists every office they ever held,
    and only the one this portfolio names belongs on this item. Written `r"."`
    it would fail to match an empty cell; left out entirely, every other office
    in the box would default to `target` and land here.
    """
    categories = tuple(
        (lang, category)
        for lang, category in (("en", en_category), ("ar", ar_category))
        if category
    )
    return Office(
        key, label, target,
        categories=categories,
        officebox=("ar", "en"),
        section_targets=((pattern, target), (r"", "")),
    )

OFFICES = [
    # --- the throne ------------------------------------------------------
    # `en:Emir of Qatar` renders its succession through
    # `{{Succession table monarch}}`, which is a real table once rendered even
    # though the wikitext holds no `{|`. It lists ten rulers to the Arabic
    # list's eight and dates them all.
    #
    # `ar:قائمة أمراء قطر` is deliberately NOT added beside it. The two sources
    # disagree — the Arabic table dates Abdullah bin Jassim from 1913-07-17 and
    # the English from 1914, and omits two rulers — and §7 is explicit that two
    # rosters for one office is two sources dating one tenure. The category is
    # the second channel, and it dates nothing.
    Office(
        "emir", "Emir of the State of Qatar", "Q25711499",
        rosters=(RosterSource("en", "Emir of Qatar",
                              headings=r"^list of rulers$"),),
        categories=(("en", "Emirs of Qatar"), ("ar", "أمراء قطر")),
        family=THANI, family_names=THANI_NAMES,
    ),
    # Heading patterns are matched against `wd.roster.fold`ed text, so this one
    # is written folded: "قائمة ولاة العهد" folds to "قايمه ولاه العهد", and
    # written unfolded it matches nothing and the lane parses zero rows.
    Office(
        "crown_prince", "Crown Prince of Qatar", "Q54965863",
        rosters=(RosterSource("ar", "ولاية العهد في قطر",
                              headings=r"ولاه العهد"),),
        family=THANI, family_names=THANI_NAMES,
    ),
    # --- the government --------------------------------------------------
    # The officeholders table carries a "Time in office" column: a tenure
    # *length*, already claimed by the `days` role. Through `period` it would
    # shadow the two date columns beside it and the page would date nothing —
    # the Czech "Dny v úřadu" bug in English.
    Office(
        "prime_minister", "Prime Minister of Qatar", "Q30100647",
        rosters=(RosterSource("en", "Prime Minister of Qatar",
                              headings=r"^list of officeholders"),),
        categories=(("en", "Prime ministers of Qatar"),
                    ("ar", "رؤساء وزراء قطريون")),
        family=THANI, family_names=THANI_NAMES,
    ),
    Office(
        "deputy_pm", "Deputy Prime Minister of Qatar", "Q108861084",
        rosters=(RosterSource("en", "Deputy Prime Minister of Qatar",
                              headings=r"^deputy prime ministers$"),),
        categories=(("en", "Deputy prime ministers of Qatar"),
                    ("ar", "نواب رؤساء وزراء قطر")),
    ),
    # --- the two portfolios that publish a list --------------------------
    # Both are bullet lists, not tables. Foreign Affairs dates its rows as bare
    # appointment years with no end — a start-only term, which is what the
    # source says and not a defect to repair.
    #
    # en.wikipedia splits the foreign-affairs holders across two categories
    # ("Foreign ministers of Qatar", 4; "Foreign affairs ministers of Qatar",
    # 2) and so does ar. All four are named: a category the office does not
    # claim is a second channel silently missing.
    Office(
        "foreign_affairs", "Minister of Foreign Affairs of Qatar", "Q108861056",
        rosters=(RosterSource("en", "Ministry of Foreign Affairs (Qatar)",
                              kind="bullets", headings=r"^list of ministers"),),
        categories=(("en", "Foreign ministers of Qatar"),
                    ("en", "Foreign affairs ministers of Qatar"),
                    ("ar", "وزراء خارجية قطر"),
                    ("ar", "وزراء خارجية قطريون")),
    ),
    # Q110182394 has no holders at all and no rival: the people this roster
    # resolves hold no ministerial item between them, so nothing competes for
    # the era. It is also why the lane rests entirely on `modern_from` — an
    # item with zero holders supports no precedent whatever.
    Office(
        "justice", "Minister of Justice of Qatar", "Q110182394",
        rosters=(RosterSource("en", "Ministry of Justice (Qatar)",
                              kind="bullets", headings=r"^list of ministers"),),
        categories=(("en", "Justice ministers of Qatar"),
                    ("ar", "وزراء عدل قطر")),
    ),
    # --- the portfolios no roster lists (the infobox channel) -------------
    #
    # Twenty-eight of Qatar's thirty-two ministry articles carry no dated list
    # of ministers on either wiki, so there is no roster to read. The same facts
    # are written down one person at a time: 83 dated ministerial tenures sit in
    # the infoboxes of the holders' own articles, 141 of the 227 dated tenures
    # found there being ar.wikipedia's.
    #
    # Each of these offices reads only *its own* category's members, and its
    # `section_targets` claim only its own office string. Everything else an
    # infobox lists — a football federation presidency, another portfolio, an
    # ambassadorship — falls through to the catch-all and is routed to no item
    # at all, which records it as a byproduct instead of filing it here. That
    # is the whole reason this is one office per portfolio rather than one
    # cabinet bucket: in a bucket, "in some ministerial category" would satisfy
    # the two-channel gate for a portfolio the category never mentioned.
    portfolio("interior", "Minister of the Interior", "Q110182528",
              "Interior ministers of Qatar", "وزراء داخلية قطر",
              r"minister of (?:the )?interior|وزير الداخلي"),
    portfolio("defence", "Minister of Defence of Qatar", "Q110182640",
              "Defense ministers of Qatar", "وزراء دفاع قطر",
              r"minister of (?:state for )?defen[cs]e|وزير الدفاع|وزير الدوله لشوون الدفاع"),
    portfolio("finance", "Minister of Finance of Qatar", "Q110182380",
              "Finance ministers of Qatar", "وزراء مالية قطر",
              r"minister of finance|وزير الماليه"),
    portfolio("health", "Minister of Public Health", "Q110183282",
              "Health ministers of Qatar", "وزراء صحة قطر",
              r"minister of (?:public )?health|وزير[ه]? الصحه"),
    portfolio("education", "Minister of Education and Higher Education",
              "Q110183226", "Education ministers of Qatar",
              "وزراء تربية وتعليم قطريون",
              r"minister of education|وزير التربيه|وزير التعليم"),
    portfolio("labour", "Minister of Labour", "Q110183234",
              "Labour ministers of Qatar", "وزراء عمل قطر",
              r"minister of (?:labour|labor)|وزير العمل"),
    portfolio("municipality", "Minister of Municipality", "Q110183210",
              "Municipal affairs ministers of Qatar", "",
              r"minister of municipal|وزير البلدي"),
    portfolio("transport", "Minister of Transport", "Q110183197",
              "Transport ministers of Qatar", "وزراء نقل قطر",
              r"minister of transport|وزير المواصلات|وزير النقل"),
    portfolio("sports", "Minister of Sports and Youth", "Q110183206",
              "Sports and youth ministers of Qatar", "وزراء رياضة وشباب قطريون",
              r"minister of sports|وزير الرياضه|وزير الشباب"),
    portfolio("social", "Minister of Social Development and Family",
              "Q110183240", "Social development and family ministers of Qatar",
              "", r"minister of social development|وزير التنميه الاجتماعيه"),
    portfolio("awqaf", "Minister of Awqaf and Islamic Affairs", "Q110182358",
              "Endowments and Islamic affairs ministers of Qatar",
              "وزراء أوقاف وشؤون إسلامية قطريون",
              r"minister of (?:endowments|awqaf)|وزير الاوقاف|وزير الشوون الاسلاميه"),
    portfolio("culture", "Minister of Culture, Arts and Heritage", "Q110182482",
              "Culture ministers of Qatar", "وزراء ثقافة في قطر",
              r"minister of culture|وزير الثقافه"),
    portfolio("environment", "Minister of the Environment of Qatar",
              "Q110182471", "Environment and climate change ministers of Qatar",
              "وزراء بيئة وتغير المناخ قطر",
              r"minister of (?:the )?environment|وزير البيه"),
    portfolio("ict", "Minister of Information and Communications Technology",
              "Q110182490",
              "Communications and information technology ministers of Qatar",
              "", r"minister of (?:information and )?communications|وزير الاتصالات"),
    portfolio("energy", "Minister of Energy", "Q110182815",
              "Energy ministers of Qatar", "وزراء طاقة قطر",
              r"minister of (?:state for )?energy|وزير الطاقه(?! والصناعه)"
              r"|وزير الدوله لشوون الطاقه"),
    portfolio("commerce", "Minister of Commerce and Industry", "Q106762274",
              "Commerce ministers of Qatar", "وزراء تجارة وصناعة قطريون",
              r"minister of commerce|وزير التجاره"),
    # --- central bank ----------------------------------------------------
    # Four governors, two of them linked. The first row's start cell reads
    # "? - 1983": the source declining to state a start, not a start of 1983.
    Office(
        "central_bank", "Governor of the Qatar Central Bank", "Q110183389",
        rosters=(RosterSource("en", "Qatar Central Bank",
                              headings=r"^governors$"),),
    ),
]


#: Qatar's own ambassador class, the parent every outbound post shares.
QATAR_ENVOY = "Q38717123"


def envoy(
    key: str, receiver_en: str, receiver_ar: str, receiver_qid: str,
    receiving_class: str, holders: int, target: str = "",
) -> Office:
    """One bilateral ambassadorship, awaiting its item.

    The shape is measured, not chosen — ten existing "ambassador of Qatar to X"
    items agree on it, and it inverts what `wd.create.payload` writes by
    default: `P17` is the **receiving** state (8 of 8 that carry it), `P279`
    names both Qatar's own ambassador class and the receiving state's, and
    `P1001` is asserted by two of the ten and so is left off entirely rather
    than mass-asserted (recipe §10.3).

    `target` is deliberately absent: `run()` prints these as awaiting creation
    and skips them, and `scripts/create_offices.py --country qa` mints them
    under a human gate. Only then does `target` get filled in and the holders
    become writable — QuickStatements' `LAST` is valid as a statement's subject
    and nowhere else, so an item minted in a batch cannot be the value of a P39
    in that same batch.

    `holders` is carried in the docstring of the declaration rather than passed
    to the guard: `wd.create.guard` counts the category itself, and its floor of
    two is what keeps the 24 single-envoy categories unminted.
    """
    return Office(
        key, f"ambassador of Qatar to {receiver_en}", target,
        categories=(("ar", f"سفراء قطر لدى {receiver_ar}"),),
        archetype="bilateral_ambassador",
        jurisdiction=receiver_qid,
        create_labels=(
            ("en", f"ambassador of Qatar to {receiver_en}"),
            ("ar", f"سفير قطر لدى {receiver_ar}"),
        ),
        create_claims=(
            ("P17", receiver_qid),
            ("P279", [QATAR_ENVOY, receiving_class]),
            ("P1001", None),
        ),
        officebox=("ar", "en"),
        section_targets=((rf"سفير (?:دوله )?قطر لدى {receiver_ar}"
                          rf"|ambassador of qatar to {receiver_en.lower()}", target),
                         (r"", "")),
    )


#: Lane E — the diplomatic corps. 102 of the 227 dated tenures the infobox
#: channel finds are ambassadorships, and none can be written until these items
#: exist. The 21 below are every bilateral posting with at least two documented
#: envoys whose item is missing; the six that already exist are excluded by
#: matching on the *receiving class*, because `Q112756747` files the
#: Netherlands under `Q29999` where the category resolves to `Q55` and a
#: country-keyed check would have minted a duplicate.
AMBASSADORS = [
    envoy("amb_france", "France", "فرنسا",
          "Q142", "Q19359050", 8, "Q141060919"),
    envoy("amb_egypt", "Egypt", "مصر",
          "Q79", "Q30056302", 6, "Q141060920"),
    envoy("amb_mexico", "Mexico", "المكسيك",
          "Q96", "Q29511856", 5, "Q141060922"),
    envoy("amb_turkey", "Turkey", "تركيا",
          "Q43", "Q28038722", 4, "Q141060923"),
    envoy("amb_russian_federation", "the Russian Federation", "روسيا",
          "Q159", "Q29511967", 4, "Q141060924"),
    envoy("amb_united_kingdom", "the United Kingdom", "المملكة المتحدة",
          "Q145", "Q456692", 4, "Q141060925"),
    envoy("amb_india", "India", "الهند",
          "Q668", "Q30056023", 4, "Q141060926"),
    envoy("amb_belgium", "Belgium", "بلجيكا",
          "Q31", "Q29511906", 3, "Q141060927"),
    envoy("amb_tunisia", "Tunisia", "تونس",
          "Q948", "Q29970486", 3, "Q141060928"),
    envoy("amb_saudi_arabia", "Saudi Arabia", "السعودية",
          "Q851", "Q30057165", 3, "Q141060934"),
    envoy("amb_kuwait", "Kuwait", "الكويت",
          "Q817", "Q30057130", 3, "Q141060940"),
    envoy("amb_lebanon", "Lebanon", "لبنان",
          "Q822", "Q30057181", 3, "Q141060946"),
    envoy("amb_united_arab_emirates", "the United Arab Emirates", "الإمارات العربية المتحدة",
          "Q878", "Q30057151", 2, "Q141060953"),
    envoy("amb_pakistan", "Pakistan", "باكستان",
          "Q843", "Q30056349", 2, "Q141060959"),
    envoy("amb_italy", "Italy", "إيطاليا",
          "Q38", "Q21814442", 2, "Q141060966"),
    envoy("amb_sao_tome_and_principe", "São Tomé and Príncipe", "ساو تومي وبرينسيبي",
          "Q1039", "Q106457780", 2, "Q141060972"),
    envoy("amb_venezuela", "Venezuela", "فنزويلا",
          "Q717", "Q30057166", 2, "Q141060981"),
    envoy("amb_nigeria", "Nigeria", "نيجيريا",
          "Q1033", "Q30249268", 2, "Q141060987"),
    envoy("amb_libya", "Libya", "ليبيا",
          "Q1016", "Q30056069", 2, "Q141060990"),
    envoy("amb_morocco", "Morocco", "المغرب",
          "Q1028", "Q29898040", 2, "Q141060991"),
    envoy("amb_greece", "Greece", "اليونان",
          "Q41", "Q29898588", 2, "Q141060992"),
]

OFFICES = OFFICES + AMBASSADORS

CAMPAIGN = Campaign(
    name="qatar",
    country_qid="Q846",
    # Not the 1970 Council of Ministers, and not 1971. See the module docstring:
    # the emirate is one continuous polity from the Al Thani establishment at
    # Doha, and a later cutoff empties the throne lane rather than protecting
    # anything. Each row is still judged against its own target's record by
    # `precedent`, never by this constant alone.
    modern_from=1850,
    offices=OFFICES,
    label_langs=("en", "ar"),
    # ar carries the people — 181 politicians and 126 diplomats against
    # en's 105 and 60 — while en carries the better rosters.
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
    # The House of Thani lane is not an office and produces no roster, but it is
    # this campaign's and belongs in its batch: `scripts/qa_family.py` writes
    # the file and the manifest owns it from here.
    extra_verdicts=("qatar_family.jsonl",),
    concurrency_ignore=(
        "Q25711499",   # Emir of the State of Qatar
        "Q54965863",   # Crown Prince
        "Q30100647",   # Prime Minister
        "Q108861084",  # Deputy Prime Minister
        "Q108861056",  # Minister of Foreign Affairs
        "Q110182528",  # Minister of the Interior
        "Q110182640",  # Minister of Defence
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
