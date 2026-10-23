"""Judge a holding's dates the same way in every lane: dated, ended, current.

Reach for this when a rule decides whether a person's tenure of an office or a
seat is worth writing. The lanes record who holds office now. A tenure that
ended a generation ago is a biography. An open tenure older than a term needs
a source that says it is held now, because an article gives the day someone
took office far more often than the day they left.

These predicates answer questions about dates and quotes. How a lane knows a
holding is current (an extracted quote, a model's flag) and what it does with
the answer remain the lane's own rules.
"""

import re
from datetime import date
from typing import Any

from peploop import dates

#: How many years ago a tenure may have ended and still be written. A start
#: that long ago with no end is more often an end the article did not give
#: than a career still running.
MAX_ENDED_YEARS = 20
#: An open tenure that began this many years ago or more has outlived a
#: typical term: it must be quoted as held now.
OPEN_TERM_YEARS = 4

#: What an English quote says when the office is held now: an infobox's
#: "Incumbent" and "Assumed office", or prose in the present.
CURRENT_EN = re.compile(r"\bincumbent\b|\bassumed office\b|\bpresent\b|\bcurrent(?:ly)?\b|\bsince\b|"
                        r"\b(?:is|serves|sits) (?:as )?(?:the|a|an)\b|\bserving\b", re.I)
#: Marker words that tell of the start, not of now: the rival a person beat
#: ("beating incumbent Brett Svendsen") and the day they began ("commenced
#: serving as the Division 2 councillor").
NOT_NOW = re.compile(r"\b(?:beat|defeat|unseat|oust)\w*\s+(?:the\s+)?(?:sitting\s+)?incumbent\b"
                     r"|\bagainst\s+(?:the\s+)?(?:sitting\s+)?incumbent\b"
                     r"|\b(?:commenced|began|begun|started)\s+serving\b", re.I)
#: What only an infobox says: an office it lists as held now. An ambassador
#: rotates within a term, and a stub's "since 2016 he is" is never revised.
INFOBOX = {
    "en": re.compile(r"\bincumbent\b|\bassumed office\b", re.I),
    "el": re.compile(r"εν ενεργεία", re.I),
    "tr": re.compile(r"görevde|makama geliş", re.I),
    "pt": re.compile(r"\bem exercício\b|\ba[c]?tualidade\b|(?:[–-]|\d{4})\s*presente\b", re.I),
    "zh": re.compile(r"[现現]任|就任日期"),
}
#: The same, per language whose articles were measured: Greek infoboxes
#: write "Εν ενεργεία", Turkish ones "Görevde" and "Makama geliş" (assumed
#: office), Portuguese ones "Período: 2022 a atualidade" or "– presente";
#: prose says "σήμερα" / "halen", "günümüz" / "atualmente", "é o atual"
#: (today, still, the current one). Chinese infoboxes write "现任" over
#: "就任日期" (incumbent, assumed office: 549 of 7,847 Chinese articles, every
#: one with both), prose "现任" and "至今" (to this day).
CURRENT = {
    "en": CURRENT_EN,
    "el": re.compile(r"εν ενεργεία|σήμερα|διατελεί|υπηρετεί", re.I),
    "tr": re.compile(r"görevde|makama geliş|halen|hâlâ|günümüz|devam ediyor|sürdürüyor", re.I),
    "pt": re.compile(r"\bem exercício\b|\ba[c]?tualidade\b|(?:[–-]|\d{4})\s*presente\b|"
                     r"\ba[c]?tualmente\b|\bé (?:o|a) a[c]?tual\b|\bdesde\b|\bem funções\b|"
                     r"\bocupa o (?:cargo|posto)\b", re.I),
    "zh": re.compile(r"[现現]任|就任日期|至今|迄今"),
}
#: An end read from an event rather than from the tenure ending, by language (stems):
#: an arrest, a charge or an investigation ends nothing by itself.
END_EVENTS = re.compile(
    r"arrest|charged|indict|investigat|suspend|detain|"
    r"verhaftet|festgenommen|ermittl|angeklagt|suspendiert|"
    r"arrêté|interpellé|mis en examen|enquête|suspendu|"
    r"detenid|arrestad|investigaci|imputad|arrestat|indagat|indagine|sospes|detid|investigaç|"
    r"zatrzyman|aresztowan|śledztw|zarzut|zawieszon|zatčen|obviněn|vyšetřov|obvinen|zadržan|"
    r"letartóztat|őrizetbe|nyomozás|vádat|felfüggeszt|reținut|anchet|inculpat|suspendat|"
    r"арестуван|задържан|разследван|обвин|отстранен|συνελήφθη|δίωξη|έρευνα|"
    r"uhićen|pritvoren|istrag|optužen|aretiran|preiskav|vahistati|kahtlustus|aizturēt|apcietināt|"
    r"izmeklēšan|apsūdz|sulaikyt|suimt|ikiteisminį|pidätet|tutkinta|syyte|"
    r"anhållen|häktad|anholdt|sigtet|gearresteerd|aangehouden|geschorst", re.IGNORECASE)


def bad_dates(start: dict[str, Any] | None, end: dict[str, Any] | None) -> bool:
    """Whether a tenure ends before it starts, compared at the precision both share.

    An end known only to the year is not before a start known to the day of
    that year: 2014-03-26 to 2014 is a tenure within 2014.
    """
    if not start or not end:
        return False
    shared = min(start.get("precision", 11), end.get("precision", 11))
    return (dates.at_precision(end["time"], shared) or "") < (dates.at_precision(start["time"], shared) or "")


def ended_long_ago(start: dict[str, Any] | None, end: dict[str, Any] | None, today: date) -> bool:
    """Whether a tenure's latest known year is more than `MAX_ENDED_YEARS` ago."""
    latest = dates.known_year(end) or dates.known_year(start)
    return latest is not None and latest < today.year - MAX_ENDED_YEARS


def open_too_long(start: dict[str, Any] | None, today: date) -> bool:
    """Whether an open tenure began a term or more ago, so its being held now needs saying."""
    year = dates.known_year(start)
    return year is not None and year <= today.year - OPEN_TERM_YEARS


def reads_current(lang: str | None) -> bool:
    """Whether this language's present-tense markers are listed, so `says_current` can answer for it."""
    return (lang or "en") in CURRENT


def says_current(quote: str | None, lang: str | None, infobox_only: bool = False) -> bool:
    """Whether a quote says the office is held now, in its language's markers.

    `infobox_only` reads only an infobox's markers: an ambassador rotates
    within a term, and "where he currently serves" outlives a council seat.
    """
    markers = (INFOBOX if infobox_only else CURRENT).get(lang or "en")
    return bool(markers and quote and markers.search(NOT_NOW.sub("", quote)))


def names_end_event(quote: str | None) -> bool:
    """Whether a quote dates an end by an event (an arrest, a charge, an investigation) rather than a tenure ending."""
    return bool(quote and END_EVENTS.search(quote))
