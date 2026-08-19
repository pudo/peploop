# Institution coverage across campaigns

What each country sweep actually covered, by institution class. Scoped against
`recipes/institutions.md`; the per-country detail lives in `coverage/<country>.md`.

This file exists because the gaps below were invisible for eleven campaigns.
Each run produced a validated batch and closed; nothing anywhere named an
institution and marked it uncovered, so the same categories went missing
country after country without anyone being able to see it.

**Legend:** ✅ covered · ◐ partial · ✗ not attempted (a channel exists, or none
was looked for) · ⊘ creation-first, no items exist · **∅ measured: no channel
exists** · — not applicable

`∅` and `✗` look alike and are opposites. `✗` is an admission that nobody
looked; `∅` is a finding, and needs the measurement written in the country's
ledger. A campaign may close on `∅` and may not close on `✗`.

| | EC | BY | CZ | ES | AE | SA | KW | JO | QA | IQ | IR |
|---|---|---|---|---|---|---|---|---|---|---|---|
| head of state | ✗ | ✗ | ✅ | ✗ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| head of government | ✗ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| cabinet | ✅ | ◐ | ✅ | ◐ | ◐ | ◐ | ◐ | ✅ | ✅ | ✅ | ✅ |
| legislature membership | ✗ | ✗ | ✗ | ◐ | ✗ | ✅ | ✅ | ◐ | ⊘ | ◐ | ✅ |
| judiciary | ✗ | ✗ | ◐ | ◐ | ⊘ | ✗ | ✗ | ✗ | ✗ | ✗ | ◐ |
| central bank | ✗ | ✗ | ✗ | ✗ | ⊘ | ✗ | ✗ | ✗ | ✅ | ✅ | ✅ |
| military / security | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✅ | ✗ | ✗ | ◐ | ✅ |
| sub-national | ✗ | ✗ | ✗ | ✅ | ◐ | ◐ | ✗ | ✗ | ✗ | ◐ | ◐ |
| ambassadors (outbound) | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✅ | ✗ | ◐ |
| SOE / sovereign wealth | ✗ | ✗ | ✗ | ✗ | ⊘ | ✗ | ✗ | ✗ | ✗ | ⊘ | ⊘ |
| party officials | ✗ | ✗ | ✗ | ✗ | — | — | — | ✗ | — | ✗ | ∅ |
| royal / ruling family | — | — | — | ✗ | ◐ | ✅ | ◐ | ✅ | ✅ | — | — |

| campaign | script | offices | plan | baseline |
|---|---|---|---|---|
| ecuador | `ec_ministers.py` | 19 | — | `regression/ecuador/` |
| belarus | `by_ministers.py` | 12 | — | `regression/belarus/` |
| czechia | `cz_ministers.py` | 23 | — | `regression/czechia/` |
| spain | `es_offices.py` | 7 (+19 routed) | — | `regression/spain/` |
| uae | `ae_offices.py` | 13 | — | `regression/uae/` |
| saudi | `sa_offices.py` + `sa_family.py` | 20 | ✓ | `regression/saudi/` |
| kuwait | `kw_offices.py` | 25 | ✓ | `regression/kuwait/` |
| jordan | `jo_offices.py` + `jo_family.py` | 6 | ✓ | `regression/jordan/` |
| qatar | `qa_offices.py` + `qa_family.py` | 44 | ✓ | `regression/qatar/` |
| iraq | `iq_offices.py` | 29 | ✓ | **none** |
| iran | `ir_offices.py` | 100 | ✓ | `regression/iran/` |

## What the columns say

**Whole FATF categories are empty across every campaign.**

* **Judiciary — 0 of 11 done properly.** The best case is Iran at three of nine
  offices. Apex-court judges are the *second item* on the FATF list the recipe
  opens with.
* **SOE and sovereign wealth — 0 of 11.** Every occurrence in the repo is a
  deferral. Saudi Arabia, the UAE, Kuwait, Qatar and Iraq were all swept without
  it, simultaneously — the five countries where it matters most.
* **Party officials — 0 of 11.** Only Iran even measured it. Belarus, Czechia and
  Ecuador are where it would matter and none looked.
* **Mayors — 0 of 11, anywhere.**
* **Central bank — 3 of 11**, and Kuwait and Jordan each have an *item with no
  roster* recorded as a deferral rather than as a coverage gap. Iran's was the
  third kind: an item with 3 holders, a perfectly good roster on **en**, and no
  office configured against it. The ledger found it; nine campaigns had not.
* **Ambassadors (outbound) — 1½ of 11.** Several campaigns correctly dismissed
  *inbound* envoys as another country's PEPs, then never ran their own.

**The head of state is missing from three campaigns** — Ecuador, Belarus, Spain.
The cheapest and highest-value office in each.

## The tell

Institutional breadth tracks two things almost perfectly, and neither is the
country:

1. **The file name.** The three narrowest campaigns are the three named
   `*_ministers.py`. A campaign scoped as a ministers sweep from the filename
   outward never asks about courts, and Ecuador's 19 offices are 19 cabinet
   portfolios and nothing else — no president, no legislature, no courts.
2. **Whether a plan file exists.** The broadest campaigns all have one. The UAE
   is the sole `*_offices.py` campaign with **no plan**, and its scope decisions
   survive only as four docstring paragraphs and scattered `followups.md`
   bullets.

## Maintaining this file

* A campaign updates its column at close, from its own `coverage/<country>.md`.
* **A ✗ is a claim and needs evidence.** If nobody looked, the ledger row says so
  — `no-source` requires a measurement, and "not attempted" is not a disposition
  a campaign may close on.
* `⊘` is not a resting state. It means items must be minted; the campaign is not
  finished while a row reads `⊘`.

## What the second Iran run showed

Iran is the first campaign re-run from its ledger rather than from its script,
and the ledger's own predictions held:

* **Three offices needed a config line and nothing else** — central bank, Majlis
  speakership, police command — and had been invisible for a whole campaign
  because nothing named them. They shipped 23 statements between them, and the
  speakership shipped 0 *because it was already complete*, which is a result the
  old method had no way to record.
* **The biggest lane was gated by one shared toolkit gap, not by its own
  difficulty.** `parse_bullet_rosters` could not be told "this page is a roster"
  the way a table source always could, so 1,871 wikilinked Majlis members read
  as eight empty pages. Fixing the gate tripled the lane.
* **`⊘` really is not a resting state.** The governor lane went 0 → 408
  statements the moment its 27 items existed. Nothing else about it changed.

The three rows still worth watching across every country: **SOE / sovereign
wealth (0 of 11)**, **mayors (0 of 11)** and **party officials (0 of 11)**.
Iran now has the `mayor` archetype and a fixed duplicate guard, so the mayoral
row is one creation round from being the first.
