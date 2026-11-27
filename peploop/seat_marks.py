"""Words by which an office title names another seat than the office it resembles.

The acting holder, the deputy and the first or second deputy each hold a seat
of their own, though their titles carry the whole name of the seat above.
Reach for these where a title is laid against an office's names: mint, to keep
such a title out of an item's aliases, and the policy, to keep its holder off
the seat above. Matched on folded text, so the East Slavic forms ("исполняющий
обязанности", "временный", "врио", "и. о.", "заместитель", "намеснік",
"заступник", "первый") are matched transliterated.
"""

import re

ACTING = re.compile(
    r"\b(acting|interim|interino|interina|encargad[oa]|ad hoc|provisional|en funciones"
    r"|kommissarisch\w*|geschaftsfuhrend\w*|facente funzion\w*|penjabat|pemangku|plt"
    r"|ispolna\w*|obazannost\w*|vrio|vykonva\w*|abavazk\w*|vremenn\w*|timcasov\w*|tymczasow\w*)\b"
    r"|\bi\. ?o\."
)
#: A deputy's word. English "deputy" is also a legislator ("deputy in the
#: National Assembly", "National Assembly Deputy"), so it counts only where a
#: title follows it.
DEPUTY = re.compile(
    r"\b(substitute|suplente|alternate|co[- ]?judge|conjuez|conjueza|deputy(?! (?:to|in|of|for|from)\b)(?!$)"
    r"|vice|vice-?\w+|assist\w*|stellvertret\w*|vize\w*|adjoint\w*|wakil(?! rakyat)|timbalan|naib"
    r"|adjunt[oa]|zamestitel\w*|namesnik\w*|zastupnik\w*|zastep\w*|yardimci\w*|vekil\w*)\b"
)
#: The number of a deputy: a first or second deputy is another seat than the
#: deputies of the same body. Read only beside a `DEPUTY` word, where "second"
#: is not a preposition; "primer ministro" is a prime minister, not a first.
ORDINAL = re.compile(
    r"\b(first|(?:primer[oa]?|premier|premiere)(?! minist)|pervyj|pervaa|persy|persaa|erst\w*|prv\w*|pierwsz\w*"
    r"|second|segund[oa]|second[oa]|deuxieme|vtoroj|vtoraa|zweit\w*|drug[iao]|druh[aeyi]"
    r"|third|tercer[oa]?|terz[oa]|troisieme|tretij|tret'a|dritt\w*|trec[iaoe])\b"
)
#: The same marks in Han script, read on the title as written: a deputy (副),
#: a numbered one (第一副). Transliterated, they are syllables that occur
#: everywhere.
DEPUTY_HAN = re.compile(r"副")
ORDINAL_HAN = re.compile(r"第[一二三四五]副")
CJK = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff\uac00-\ud7af]")
