"""Pin how every lane judges a holding's dates and whether it is held now.

Run it as `python -m peploop.check_tenure` from the repository root.
"""

from datetime import date

from peploop import tenure
from peploop.checks import expect
from peploop.dates import time_value as t

TODAY = date(2026, 10, 23)


def main() -> None:
    expect(tenure.bad_dates(t("2015"), t("2014")), "an end before the start")
    expect(not tenure.bad_dates(t("2014-03-26"), t("2014")), "an end known to the year is not before a day of it")
    expect(not tenure.bad_dates(t("2014"), None), "an open tenure has no bad dates")
    expect(tenure.ended_long_ago(t("1990"), t("2005"), TODAY), "ended 21 years ago")
    expect(not tenure.ended_long_ago(t("1990"), t("2006"), TODAY), "ended 20 years ago")
    expect(tenure.ended_long_ago(t("2000"), None, TODAY), "open, but begun 26 years ago")
    expect(tenure.open_too_long(t("2022"), TODAY) and not tenure.open_too_long(t("2023"), TODAY),
           "an open tenure outlives a term after four years")
    expect(not tenure.open_too_long(None, TODAY), "no start is not too long")
    expect(tenure.says_current("Incumbent. Assumed office 2019", "en"), "an infobox says held now")
    expect(not tenure.says_current("beating incumbent Brett Svendsen", "en"), "a rival's incumbency is not now")
    expect(tenure.says_current("he currently serves as councillor", "en"), "prose in the present")
    expect(not tenure.says_current("he currently serves as councillor", "en", infobox_only=True),
           "prose is not an infobox")
    expect(tenure.says_current("现任省长", "zh", infobox_only=True), "a Chinese infobox's 现任")
    expect(tenure.says_current("Trenutni nosilec naziva Začetek delovanja 10. april 2026", "sl", infobox_only=True),
           "an sl infobox's incumbent")
    expect(tenure.says_current("Od leta 2007 je član sveta.", "sl")
           and tenure.says_current("Od 2. septembra 2011 je minister", "sl"), "sl prose: since … is")
    expect(tenure.says_current("Predsednik uprave je mag. Boris Kupec.", "sl")
           and tenure.says_current("medtem ko je predsednik nadzornega sveta Milan Perović", "sl")
           and tenure.says_current("Agencijo vodi direktorica Duška Godina.", "sl"), "an sl body's officers in the present")
    expect(not tenure.says_current("Predsednik: Jernej Vrtovec", "sl"), "an sl infobox field line says nothing of now")
    expect(not tenure.says_current("Leta 1992 je bil izvoljen v 1. zbor", "sl"),
           "an sl election in the past is not now")
    expect(tenure.says_current("Durata mandato: 27 giugno 2014 – in carica", "it", infobox_only=True)
           and tenure.says_current("è attualmente consigliere", "it"), "Italian: in carica, attualmente")
    expect(not tenure.says_current("nel 2013 viene eletto consigliere regionale", "it"),
           "an Italian election in the past is not now")
    expect(tenure.says_current("Attwalment huwa Imħallef", "mt")
           and not tenure.says_current("Nhar is-16 ta' Lulju 2014, huwa nħatar Imħallef", "mt"),
           "mt: attwalment is now, an appointment is not")
    expect(not tenure.says_current("Incumbent", "xx") and not tenure.reads_current("xx"),
           "a language without markers says nothing")
    expect(tenure.names_end_event("Er wurde 2023 verhaftet."), "an arrest is an event, not an end")
    expect(not tenure.names_end_event("Er trat 2023 zurück."), "a resignation is an end")


if __name__ == "__main__":
    main()
