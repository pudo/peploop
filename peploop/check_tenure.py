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
    expect(not tenure.says_current("Incumbent", "xx") and not tenure.reads_current("xx"),
           "a language without markers says nothing")
    expect(tenure.names_end_event("Er wurde 2023 verhaftet."), "an arrest is an event, not an end")
    expect(not tenure.names_end_event("Er trat 2023 zurück."), "a resignation is an end")


if __name__ == "__main__":
    main()
