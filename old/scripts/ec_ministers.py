#!/usr/bin/env python
"""Propose P39 statements for the Ecuadorian ministries in wd_categories.yml.

    python scripts/ec_ministers.py --office trabajo turismo exteriores

The country parameters for `wd/campaign.py`; the method is
`recipes/country_sweep.md`. Ecuador is the country the engine was first built
for, and the case where the win is largest: its ministry items existed but sat
at one to four holders each, while es.wikipedia keeps a dated, footnoted
`Anexo:Ministros de …` table per portfolio going back to 1830.

Two things are specific enough to spell out:

* **The roster articles carry sibling ministries and predecessor agencies in
  the same page.** Matching a table heading on "cartera" swept in "Cartera de
  Minería" and "Cartera de planificación económica"; `MINISTERIAL_HEADING`
  accepts only the office's own table, and the audit logs the ones skipped.
* **Gobierno / Interior is one roster spanning a ministry renamed four times**
  (Gobierno → Interior → Gobierno → Interior) between 1830 and now. The section
  heading picks which item a row belongs to, but the item history is unsettled,
  so `hold` keeps every row out of the batch pending a ruling.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.campaign import Campaign, Office, RosterSource, run
from wd.http import REPO_ROOT, make_session

OUT_DIR = REPO_ROOT / "data" / "ecuador"

#: Headings of the tables that ARE the office: "Titulares", "Ministros de la
#: cartera de Turismo". The same article also tabulates predecessor agencies
#: (DITURIS, SENADER) and — the trap — sibling ministries carved out of the
#: same sector. Deliberately tighter than `campaign.DEFAULT_HEADINGS`, whose
#: bare `ministr` prefix would also accept "Ministerio de …" section headers.
MINISTERIAL_HEADING = r"^(?:titulares|ministr[oa]s?)\b"


def portfolio(
    key: str, label: str, target: str, roster: str,
    es_cat: str = None, en_cat: str = None, **kwargs
) -> Office:
    """An office with one `Anexo:` roster and up to two category generators."""
    categories = tuple(
        (lang, cat) for lang, cat in (("es", es_cat), ("en", en_cat)) if cat
    )
    return Office(
        key, label, target,
        rosters=(RosterSource("es", roster, headings=MINISTERIAL_HEADING),),
        categories=categories,
        **kwargs,
    )


OFFICES = [
    portfolio("trabajo", "Trabajo", "Q114289910",
              "Anexo:Ministros de Trabajo de Ecuador",
              "Ministros_de_Trabajo_de_Ecuador", "Labour_ministers_of_Ecuador"),
    portfolio("turismo", "Turismo", "Q114289956",
              "Anexo:Ministros de Turismo de Ecuador",
              "Ministros_de_Turismo_de_Ecuador", "Tourism_ministers_of_Ecuador"),
    portfolio("deporte", "Deporte", "Q114290016",
              "Anexo:Ministros de Deportes de Ecuador",
              "Ministros_de_Deporte_de_Ecuador", "Sports_ministers_of_Ecuador"),
    portfolio("exteriores", "Relaciones Exteriores", "Q24293533",
              "Anexo:Ministros de Relaciones Exteriores de Ecuador",
              "Ministros_de_Relaciones_Exteriores_de_Ecuador",
              "Ministers_of_foreign_affairs_of_Ecuador"),
    portfolio("finanzas", "Economía y Finanzas", "Q19845330",
              "Anexo:Ministros de Economía de Ecuador",
              "Ministros_de_Economía_y_Finanzas_de_Ecuador",
              "Ministers_of_finance_of_Ecuador"),
    portfolio("defensa", "Defensa", "Q27921459",
              "Anexo:Ministros de Defensa de Ecuador",
              "Ministros_de_Defensa_de_Ecuador", "Defence_ministers_of_Ecuador"),
    # One roster covers both names (the Interior page redirects to it) and spans
    # 1830 to now. The section header picks the item; nothing is batched until
    # that rename history is ruled on.
    portfolio("interior", "Gobierno / Interior", "Q114260168",
              "Anexo:Ministros de Gobierno de Ecuador",
              "Ministros_del_Interior_de_Ecuador", "Interior_ministers_of_Ecuador",
              section_targets=((r"\bgobierno\b", "Q114290115"),),
              hold="rename_history"),
    portfolio("agricultura", "Agricultura y Ganadería", "Q114289753",
              "Anexo:Ministros de Agricultura de Ecuador",
              "Ministros_de_Agricultura_y_Ganadería_de_Ecuador",
              "Agriculture_ministers_of_Ecuador"),
    portfolio("cultura", "Cultura y Patrimonio", "Q100594801",
              "Anexo:Ministros de Cultura y Patrimonio de Ecuador",
              "Ministros_de_Cultura_y_Patrimonio_de_Ecuador",
              "Culture_ministers_of_Ecuador"),
    portfolio("educacion", "Educación", "Q114289770",
              "Anexo:Ministros de Educación de Ecuador",
              "Ministros_de_Educación_de_Ecuador", "Education_ministers_of_Ecuador"),
    portfolio("energia", "Energía", "Q114289772",
              "Anexo:Ministros de Energía de Ecuador",
              "Ministros_de_Energía_y_Recursos_Naturales_no_Renovables_de_Ecuador",
              "Energy_ministers_of_Ecuador"),
    portfolio("ambiente", "Ambiente", "Q114289994",
              "Anexo:Ministros de Ambiente de Ecuador",
              "Ministros_de_Ambiente_de_Ecuador", "Environment_ministers_of_Ecuador"),
    portfolio("salud", "Salud Pública", "Q90885218",
              "Anexo:Ministros de Salud de Ecuador",
              "Ministros_de_Salud_Pública_de_Ecuador",
              "Ministers_of_health_of_Eduador"),
    portfolio("justicia", "Justicia", "Q114289620",
              "Anexo:Ministros de Justicia de Ecuador",
              "Ministros_de_Justicia_de_Ecuador", "Justice_ministers_of_Ecuador"),
    portfolio("inclusion", "Inclusión Económica y Social", "Q114289831",
              "Anexo:Ministros de Inclusión Económica y Social de Ecuador",
              "Ministros_de_Inclusión_Económica_y_Social_de_Ecuador"),
    portfolio("obras", "Transporte y Obras Públicas", "Q114289931",
              "Anexo:Ministros de Obras Públicas de Ecuador",
              "Ministros_de_Transporte_y_Obras_Públicas_de_Ecuador"),
    portfolio("vivienda", "Desarrollo Urbano y Vivienda", "Q114290143",
              "Anexo:Ministros de Desarrollo Urbano y Vivienda de Ecuador",
              "Ministros_de_Desarrollo_Urbano_y_Vivienda_de_Ecuador"),
    portfolio("industrias", "Industrias y Productividad", "Q114289842",
              "Anexo:Ministros de Industrias y Productividad de Ecuador",
              "Ministros_de_Industrias_y_Productividad_de_Ecuador"),
    portfolio("telecom", "Telecomunicaciones", "Q114290138",
              "Anexo:Ministros de Telecomunicaciones de Ecuador"),
]

CAMPAIGN = Campaign(
    name="ecuador",
    country_qid="Q736",
    # The present ministry structure dates from the 1979 return to democracy,
    # and these items were created for the modern ministries. Anything earlier
    # is a continuity judgment — is an 1861 "Ministro del Interior y Relaciones
    # Exteriores" a holder of the 2010 item? — so it is held, not batched.
    modern_from=1979,
    offices=OFFICES,
    label_langs=("es",),
    sibling_wikis=("es",),
    evidence_verb="lists them as minister",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--office", nargs="*", default=None,
                        help="Office keys to run (default: all)")
    args = parser.parse_args()
    run(make_session(), CAMPAIGN, OUT_DIR, keys=args.office)


if __name__ == "__main__":
    main()
