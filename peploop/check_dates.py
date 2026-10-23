"""Pin how every lane reads and compares a Wikidata date.

Each case is a reading one lane relied on before the helpers were shared, so a
change here is a change in all three lanes at once.

Run it as `python -m peploop.check_dates` from the repository root.
"""

from datetime import date

from peploop.checks import expect
from peploop.dates import after_today, at_precision, group_dates, known_year, time_value, year

TODAY = date(2026, 10, 23)


def t(text: str, precision: int) -> dict:
    return {"time": text, "precision": precision}


def check_values() -> None:
    expect(time_value("1962") == {**time_value("1962"), "time": "+1962-00-00T00:00:00Z", "precision": 9},
           "a year pads month and day with 00, at precision 9")
    expect(time_value("1962-02")["precision"] == 10 and time_value("1962-02-06")["precision"] == 11,
           "a month is precision 10, a day 11")
    expect(time_value("62") is None and time_value("1962-2-6") is None, "anything else is no date")
    expect(at_precision("+1962-02-06T00:00:00Z", 10) == "+1962-02", "a day read to the month")
    expect(at_precision("+1962-02-06T00:00:00Z", 8) == "1960", "a day read to the decade")


def check_years() -> None:
    expect(year("+1909-01-01T00:00:00Z") == 1909, "a Wikidata time string")
    expect(year("-0550-01-01T00:00:00Z") == -550, "a year before the common era")
    expect(year("1990-12-26T00:00:00Z") == 1990, "a WDQS dateTime, with no sign")
    expect(year(t("+1900-00-00T00:00:00Z", 7)) == 1900, "year reads a century's first year")
    expect(year(None) is None and year("") is None and year({}) is None, "nothing is no year")
    expect(known_year(t("+1900-00-00T00:00:00Z", 7)) is None, "known_year refuses a century")
    expect(known_year(t("+1962-02-06T00:00:00Z", 11)) == 1962, "known_year reads a day's year")
    expect(known_year(None) is None, "known_year of nothing")


def check_future() -> None:
    expect(not after_today(t("+2026-00-00T00:00:00Z", 9), TODAY), "the current year is not in the future")
    expect(after_today(t("+2027-00-00T00:00:00Z", 9), TODAY), "next year is")
    expect(not after_today(t("+2026-10-00T00:00:00Z", 10), TODAY), "the current month is not")
    expect(after_today(t("+2026-11-00T00:00:00Z", 10), TODAY), "next month is")
    expect(not after_today(t("+2026-10-30T00:00:00Z", 10), TODAY),
           "a month-precision value with a stray day compares as its month")
    expect(after_today(t("+2026-10-24T00:00:00Z", 11), TODAY), "tomorrow is")
    expect(not after_today(t("+2026-10-23T00:00:00Z", 11), TODAY), "today is not")
    expect(not after_today(t("+2030-00-00T00:00:00Z", 8), date(2031, 1, 1)), "a decade compares as its year")
    expect(not after_today(None, TODAY) and not after_today({"time": None}, TODAY), "nothing is not in the future")


def check_groups() -> None:
    groups = group_dates([{"value": "1962"}, {"value": "1962-02-06"}, {"value": "1963"}])
    expect([[e["value"] for e in g] for g in groups] == [["1962-02-06", "1962"], ["1963"]],
           "a year and a day of that year are one date, finest first")


def main() -> None:
    check_values()
    check_years()
    check_future()
    check_groups()


if __name__ == "__main__":
    main()
