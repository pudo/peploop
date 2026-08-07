#!/usr/bin/env python
"""Propose P39 statements for the Spanish offices in wd_categories.yml.

    python scripts/es_offices.py --office pm senate_pres

The country parameters for `wd/campaign.py`; the method is
`recipes/category_check.md`. Spain is the largest block this workbench has run
against — 13,284 position items carrying 50,523 holder statements — and the
shape of the problem is not coverage but **which item a term belongs on**.

Spanish ministries are renamed with almost every cabinet, and Wikidata models
each name as its own position item. So a portfolio is not one target but a
succession of them, and the join is by *date*: foreign affairs runs Ministro de
Estado (to 1938) → Asuntos Exteriores (to 2004) → Asuntos Exteriores y
Cooperación (to 2018) → Asuntos Exteriores, Unión Europea y Cooperación, each
with its own item and its own era's holders. `Office.date_targets` exists for
that. Where two items compete for the *same* era — labour and education both
have a plausible long-running item and a specific one carrying holders it has
no business carrying — no office is declared here at all; `tasks/spain.md`
records them.

The offices that made it in are the ones where the succession is measurable:
one item per era, each item's own record agreeing with the era it is given.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.campaign import Campaign, Office, RosterSource, run
from wd.http import REPO_ROOT, make_session

OUT_DIR = REPO_ROOT / "data" / "spain"

#: es.wikipedia heads each era's table by reign or regime ("Isabel II",
#: "Restauración borbónica", "Dictadura de Francisco Franco"), and no two pages
#: agree on the wording. Accepting every table is safe here because a table with
#: no date column — the "Espectro político" colour key each era carries — is
#: dropped by `campaign.office_rows` before it can contribute a row.
ANY_TABLE = r".*"

#: Autonomía cell → that community's own president item. The national list
#: tabulates all nineteen in one table, naming the community in a rowspanned
#: first column, so this is `section_targets` doing exactly what it was written
#: for: one roster, one target per row.
COMMUNITIES = (
    (r"andalucia", "Q2748453"),
    (r"aragon", "Q3133842"),
    (r"asturias", "Q3320056"),
    (r"baleares", "Q13710953"),
    (r"canarias", "Q967418"),
    (r"cantabria", "Q47358"),
    (r"castilla-la mancha", "Q3272746"),
    (r"castilla y leon", "Q4892213"),
    (r"cataluna", "Q16933549"),
    (r"ceuta", "Q6745827"),
    (r"comunidad valenciana", "Q15971570"),
    (r"extremadura", "Q3049413"),
    (r"galicia", "Q3409188"),
    (r"la rioja", "Q3049394"),
    (r"comunidad de madrid", "Q3133837"),
    (r"melilla", "Q30727487"),
    (r"murcia", "Q5199072"),
    (r"navarra", "Q3753803"),
    (r"pais vasco", "Q1124265"),
)

AUTONOMY_CATEGORIES = tuple(
    ("es", name)
    for name in (
        "Presidentes de la Junta de Andalucía",
        "Presidentes de la Diputación General de Aragón",
        "Presidentes del Principado de Asturias",
        "Presidentes de las Islas Baleares",
        "Presidentes del Gobierno de Canarias",
        "Presidentes de Cantabria",
        "Presidentes de la Junta de Castilla y León",
        "Presidentes de la Junta de Comunidades de Castilla-La Mancha",
        "Presidentes de la Generalidad de Cataluña",
        "Presidentes de Ceuta",
        "Presidentes de la Junta de Extremadura",
        "Presidentes de la Junta de Galicia",
        "Presidentes de la Comunidad de Madrid",
        "Presidentes de Melilla",
        "Presidentes de la Región de Murcia",
        "Presidentes del Gobierno de Navarra",
        "Presidentes del Gobierno Vasco",
        "Presidentes de La Rioja",
        "Presidentes de la Generalidad Valenciana",
    )
)

OFFICES = [
    # The office is "Presidente del Gobierno" from 1938; the 19th-century
    # premiership is Q16020745 (Presidente del Consejo de Ministros), whose own
    # list article tabulates one row per *cabinet* with an events column and is
    # not readable as a roster — see tasks/spain.md.
    Office(
        "pm", "Prime Minister", "Q844587",
        rosters=(RosterSource("es", "Anexo:Presidentes del Gobierno de España",
                              headings=ANY_TABLE),),
        categories=(("en", "Prime ministers of Spain"),),
    ),
    # Both chambers' presiding officers sit on one long-running item each, and
    # the community already files every era there: Q17014422 carries 15 terms
    # from before 1834, Q1335465 forty-six from before 1931.
    # The Congress presidency has two items, and they partition by era in the
    # data even though only one says so: Q45213921 carries 31 terms from
    # 1876–1923 and declares that inception, Q17014422 none from that window and
    # every modern one. Before 1876 both are in use (32 terms against 24), which
    # is what `already_under_sibling` is for — the roster's 19th-century rows are
    # mostly on record under whichever item an editor reached for.
    Office(
        "congress_pres", "President of the Congress of Deputies", "Q17014422",
        date_targets=(
            (None, 1876, "Q17014422"),
            (1876, 1924, "Q45213921"),   # …until the Primo de Rivera coup
            # The Asamblea Nacional Consultiva (1927–1929) was a corporate
            # chamber that replaced the Cortes, and its president is on this
            # roster. Wikidata has an item for its *members* (Q24044772) and
            # none for its president, so there is nothing to propose: the row
            # becomes an item-creation byproduct instead of a wrong statement.
            (1924, 1931, ""),
            (1931, 1939, "Q43118787"),   # Cortes republicanas
            (1939, 1977, "Q43138757"),   # Cortes franquistas
            (1977, None, "Q17014422"),
        ),
        rosters=(RosterSource("en", "List of presidents of the Congress of Deputies",
                              headings=ANY_TABLE),),
        categories=(("en", "Presidents of the Congress of Deputies (Spain)"),),
    ),
    Office(
        "senate_pres", "President of the Senate", "Q1335465",
        rosters=(RosterSource("es", "Anexo:Presidentes del Senado de España",
                              headings=ANY_TABLE),),
        categories=(("es", "Presidentes del Senado de España"),
                    ("en", "Presidents of the Senate of Spain")),
    ),
    Office(
        "supreme_court_pres", "President of the Supreme Court", "Q29934477",
        rosters=(RosterSource("es", "Anexo:Presidentes del Tribunal Supremo de España",
                              headings=ANY_TABLE),),
        categories=(("es", "Presidentes del Tribunal Supremo de España"),),
    ),
    # Foreign affairs, the clearest case of the renaming succession. Each window
    # is the ministry's name in that period and each item's record agrees:
    # Q32969013 (Estado) holds 125 terms from 1834–1931 and none after 1945,
    # Q26262159 declares itself 2004–2018.
    Office(
        "exteriores", "Foreign Affairs", "Q32969013",
        date_targets=(
            (None, 1938, "Q32969013"),   # Ministro de Estado
            (1938, 2004, "Q25672112"),   # Ministro de Asuntos Exteriores
            (2004, 2018, "Q26262159"),   # …y de Cooperación
            (2018, None, "Q54877757"),   # …, Unión Europea y Cooperación
        ),
        rosters=(RosterSource("es", "Anexo:Ministros de Asuntos Exteriores de España",
                              headings=ANY_TABLE),),
        categories=(("en", "Foreign ministers of Spain"),
                    ("es", "Ministros de Asuntos Exteriores de España")),
    ),
    # Justice was "Gracia y Justicia" until the Second Republic renamed it in
    # 1931, and the two items split there: Q32978760 carries 126 terms from
    # 1834–1931 and one after, Q24279063 thirteen from the Republic on.
    Office(
        "justicia", "Justice", "Q32978760",
        date_targets=(
            (None, 1931, "Q32978760"),   # Ministro de Gracia y Justicia
            (1931, None, "Q24279063"),   # Ministro de Justicia
        ),
        rosters=(RosterSource("es", "Anexo:Ministros de Justicia de España",
                              headings=ANY_TABLE),),
        categories=(("en", "Justice ministers of Spain"),
                    ("es", "Ministros de Justicia de España")),
    ),
    Office(
        "autonomy_pres", "President of an autonomous community", "Q2748453",
        section_targets=COMMUNITIES,
        rosters=(RosterSource(
            "es", "Anexo:Presidentes de comunidades autónomas españolas",
            # The page's first table lists only the incumbents, with election
            # years where a term belongs; the historical one is the roster.
            headings=r"^historico",
        ),),
        categories=AUTONOMY_CATEGORIES,
    ),
]

CAMPAIGN = Campaign(
    name="spain",
    country_qid="Q29",
    # The first democratic Cortes since the Republic. The Constitution follows
    # in December 1978, but the offices are continuous from the 1977 election
    # and every roster's last era heading starts at the transition.
    modern_from=1977,
    offices=OFFICES,
    label_langs=("es", "en"),
    sibling_wikis=("es", "en", "ca", "gl", "eu"),
    evidence_verb="lists them in the office",
    # Shortness carries no signal in Spain. Nineteenth-century ministries and
    # Congress presidencies routinely lasted weeks, and the "other office" the
    # concurrency test matches is as often a lifetime post — senator for life, a
    # bishopric, an embassy — or an item for the *ministry* rather than the
    # minister. Nine of the eighteen spells it caught were premiers who held the
    # Estado portfolio substantively, which is the opposite of acting. So the
    # rule keeps flagging them and the flag routes to review instead of adding a
    # P2868 nobody measured.
    dispositions={"interim_concurrent_office": "review"},
    # Every Spanish minister and chamber president also sits in the Cortes, in
    # whichever form that chamber took, so an overlap with one of these says
    # nothing about whether a short ministerial spell was cover.
    concurrency_ignore=(
        "Q18171345",  # Member of the Congress of Deputies
        "Q19323171",  # member of the Senate of Spain
        "Q6087309",   # procurador en Cortes (1943–1977)
        "Q32963246",  # member of the Congress of Deputies (1876–1923)
        "Q39399258",  # Senator of the Kingdom (1876–1923)
        "Q64877910",  # member of the Cortes under Isabel II
        "Q64876399",  # member of the Congress, Sexenio Democrático
        "Q32979666",  # member of the Cortes republicanas
        "Q24044772",  # member of the Consultative National Assembly
        "Q18714088",  # Member of the Parliament of Catalonia
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
