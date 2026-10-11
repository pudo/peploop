---
description: Qatar country sweep — thin rosters, a dynasty-shaped state; adds a person-infobox tenure channel, a creation-first ambassador lane, and Tree list genealogy support
date: 2026-08-13
tags: [wikidata, country-sweep, qatar, al-thani, kinship, infobox, arabic-rosters, creation-first]
---

# Qatar sweep

Method lives in `recipes/country_sweep.md`; this document holds what the survey
measured for Qatar and the decisions that follow.

## Context

Qatar has never been swept. Nothing in the repo mentions it: no `data/qatar/`,
no `regression/qatar/`, no `scripts/qa_offices.py`.

Wikidata records the Qatari state almost not at all. Thirty-one domestic
position items exist — a block minted around 2021 — and between them they carry
roughly thirty-five `P39` statements: one holder each, the sitting minister.
Of 236 documented Qatari public figures, **51 have any `P39` at all**.

Qatar is not, however, the Ecuador profile the calibration table would predict
from those numbers, because the roster channel that makes that profile
high-yield is absent: **two of thirty-two ministry articles carry a dated
minister list**, on either wiki. The country's power is also unusually
concentrated in one family — 91 of the 236 are Al Thani.

So this campaign cannot be run with the engine as it stands. It adds three
capabilities, each of which outlives Qatar:

1. a **person-infobox tenure channel**, which is how a country whose ministries
   publish no succession tables can be swept at all;
2. a **creation-first ambassador lane**, extending `scripts/create_offices.py`
   to the diplomatic archetype;
3. a small extension to the kinship reader for `{{Tree list}}` genealogies —
   which turned out to be a one-clause change, not the `{{Tree chart}}` parser
   the scope question anticipated. See Lane F.

The intended outcome is one reviewable batch — a `.qs` plus its claims file —
covering the formal government and the House of Thani, plus byproduct creation
lists for what the batch cannot reach.

## What the survey measured

All numbers below were measured with the repo's own code
(`wd/petscan.py`, `wd/roster.py`, `wd/api.py`) on 2026-08-13, not estimated.

### Coverage

| measurement | value |
|---|---|
| people with `P27 = Q846` | 1,271 |
| …carrying any `P39` | 54 |
| category-tree members (en+ar union, PetScan) | 297 |
| …that are actually `P31 = Q5` | 236 |
| …that are **not** human (the `Q5` gate earns its keep) | 61 |
| humans carrying any `P39` | 51 |
| humans with **no** `P39` | 185 |
| domestic position items (ambassadors excluded) | 31 |
| `P39` statements across all of them | ~35 |
| items with **zero** holders | 3 |

The 61 non-humans are 20.5% of the PetScan result — the recipe's warning that
PetScan's "uses Q5" filter passes `Category:` items via P4224, at a rate higher
than Ecuador's 37-in-764.

### Channel: Arabic is primary, but English is not a supplement

PetScan member counts, as run:

| category | lang | depth | members |
|---|---|---|---|
| سياسيون قطريون | ar | 3 | 181 |
| دبلوماسيون قطريون | ar | 2 | 126 |
| آل ثاني | ar | 2 | 89 |
| وزراء قطريون | ar | 2 | 75 |
| Qatari politicians | en | 3 | 105 |
| House of Thani | en | 2 | 76 |
| Government ministers of Qatar | en | 2 | 67 |
| Qatari diplomats | en | 2 | 60 |

Arabic carries more people; English carries the better *rosters* and the only
readable genealogy. Both wikis maintain a full per-portfolio ministerial
category tree (en 32 subcategories, ar 33), which is the second channel for
every ministerial claim. `sibling_wikis=("ar", "en")`, `label_langs=("en","ar")`.

### Rosters found, and whether they parse *today*

Run through `wd.roster.parse_rosters` / `parse_bullet_rosters` against live
rendered HTML. "gap" is roster rows resolving to an item that the target does
not already record as a holder.

| source | rows | dated | linked | gap |
|---|---|---|---|---|
| `en:Emir of Qatar` (`{{Succession table monarch}}`) | 10 | 10 | 10 | **7** |
| `ar:قائمة أمراء قطر` | 8 | 8 | 8 | 5 (subset of above) |
| `ar:ولاية العهد في قطر` § ولاة العهد | 6 | 6 | 6 | **5** |
| `en:Prime Minister of Qatar` | 7 | 7 | 7 | **2** |
| `ar:قائمة رؤساء وزراء قطر` | 7 | 7 | 7 | subset |
| `en:Deputy Prime Minister of Qatar` | 9 | 9 | 8 | **4** |
| `en:Qatar Central Bank` § Governors | 4 | 4 | 2 | **2** |
| `en:Ministry of Foreign Affairs (Qatar)` (bullets) | 8 | 8 | 6 | **3** |
| `en:Ministry of Justice (Qatar)` (bullets) | 8 | 8 | 7 | **~7** |
| `en:Cabinet of Qatar` | 19 | **0** | 19 | — |
| `en:2021 Qatari general election` | 30 | 0 | 1 | — |
| `ar:قائمة أعضاء مجلس الشوري القطري (2021)` | 45 | 0 | ~2 | — |
| the other 30 ministry articles (en + ar) | — | **none** | — | — |

Three findings decide the campaign's shape:

- **The clean office lanes total roughly 30 new statements.** That is the whole
  of what a roster-driven sweep can produce in Qatar. The Emir lane is the
  largest and the cleanest: the first seven emirs carry **no `P39` at all**, so
  there is no sibling-item ambiguity to route around. The Crown Prince roster
  is Arabic-only and was found only by searching ar for the office by name —
  `en:Crown Prince of Qatar` does not exist.
- **`en:Cabinet of Qatar` is the sitting cabinet and dates nothing.** §7's
  "defer it" applies, and it is nearly worthless anyway: the sitting minister is
  the one holder each position item already has.
- **The Shura Council is a creation list, not a statement lane.** Of the 28
  elected 2021 members named on en.wikipedia, **one has a Wikidata item**. The
  ar list article names all 45 (15 appointed + 30 elected) as unlinked plain
  text in a single `الأعضاء` column with no date column — weak identity on the
  §5 ladder, so it would skip even if the item existed.

### Where the 185 people without `P39` actually are

Tallied from their `P106` and their ar.wikipedia categories:

| signal | count | lane |
|---|---|---|
| `تصنيف:آل ثاني` | 71 | family lane (P53), throne offices |
| `تصنيف:دبلوماسيون قطريون` | 56 | ambassador lane |
| `تصنيف:سفراء قطر` (54 per-country subcats) | 35 | ambassador lane |
| `تصنيف:وزراء قطريون` | 22 | infobox lane — no roster dates them |
| `تصنيف:أمراء قطر` | 9 | throne |
| `تصنيف:أعضاء مجلس الشورى القطري` | 6 | creation byproduct |
| P106 = politician / diplomat / civil servant | 51 / 33 / 12 | — |

The infobox measurement that follows from this: of the 185, **25 have
`{{Infobox officeholder}}` on en.wikipedia carrying `office=` and
`term_start=`**, and 8 more on ar. 47 en articles carry an office field without
dates.

### The House of Thani

| measurement | value |
|---|---|
| items labelled "… Al Thani" in the census | 91 |
| carrying `P53 = Q2502270` | 52 |
| carrying some other `P53` value | 2 |
| carrying **no** `P53` | **37** |
| lacking `P22` | **59** |
| lacking `P25` | **90** |

`en:House of Thani` publishes the genealogy as **15 `{{Tree chart}}` template
calls** under three branch headings — one template call per grid *row*, cells
being either a box key, an edge glyph (`!`, `,`, `-`, `^`, `.`), or empty, so
parent-child edges live in the column geometry of consecutive rows. This is the
shape `plans/kuwait_sweep.md` deferred. `ar:آل ثاني` has no family tree — but
`ar:قالب:شجرة أمراء قطر` does, as 15 `{{شجرة نسب}}` calls using **the same edge
glyphs** (`!`, `,|-|^|-|.`) with Arabic box keys (`أ`, `ب`). So the reader must
be written against the glyph vocabulary rather than the template name, and
Qatar then has *two independent trees* for the ruling line — a genuine second
channel for the edges they share.

### The backtest, run live before any code was written

`wd.backtest` was pointed at the seven roster lanes against the statements
Wikidata already holds — the rows the sweep would *skip* are its test set:

| office | on record | target agreement | date agreement |
|---|---|---|---|
| emir | 3 | 100% (3/3) | 100% |
| crown_prince | 3 | 100% (1/1) | 100% |
| prime_minister | 7 | 100% (5/5) | 100% |
| deputy_pm | 7 | 100% (4/4) | **75%** (3/4) |
| foreign_affairs | 4 | — | 100% (3 coarser) |
| central_bank / justice | 0 / 1 | — | — |

Two things follow.

**Routing is not in doubt.** Target agreement is 100% wherever it can be
measured, so none of these lanes is secretly several items and the
`duplicate_office_item` protection has nothing to catch. Foreign Affairs scoring
"coarser" on all three is the roster's bare appointment years meeting
day-precision records — agreement at the precision they share, which is the
comparison the backtest is supposed to make.

**The one conflict is a source disagreement, not a parser defect.**
Q23020336 Mohammed bin Abdulrahman Al Thani: `en:Deputy Prime Minister of Qatar`
dates him from November 2017, Wikidata records 2016-01-27. It needs reading, and
it is the kind of thing §7 says to report rather than repair.

**Qatar needs the two-file batch.** The backtest found **9 roster spells that
are not recorded at all although the person already holds the target for some
other spell** — Khalifa bin Hamad Al Thani as crown prince *and* prime minister,
Hamad bin Khalifa likewise, three more on the deputy premiership. This is the
Kuwait multi-tenure shape exactly: QuickStatements matches on subject, property
and value alone and would fold the two spells into one statement carrying both
starts. They belong in `edit_plan_claims.json` via
`wd.validate.collapsing_groups`, and `scripts/apply_claims.py` writes them. The
`.qs` and the claims file are two halves of one batch.

## §2a — is each office one item or several?

The renamed economic portfolios are a **succession Wikidata models but does not
declare**: Q106762274 Commerce and Industry, Q108861091 Industry and Energy,
Q110182815 Energy, Q110182502 Business and Trade. None carries `P571`, `P576`,
`P1365` or `P1366`, so nothing on the items says which era each name owned.
Route by date with `Office.date_targets`, and expect
`already_under_sibling → duplicate_office_item` to fire.

Three items have **zero holders** — Q110182394 Justice, Q110182502 Business and
Trade, Q110182437 Development Planning and Statistics — which is the case the
Saudi run warned about: a census printed from holders alone hides exactly the
items a sweep exists to fill.

## `modern_from` decides whether the throne lane exists at all

This is the finding that most changes the campaign, and it was measured by
running `wd.policy.decide` against the live `wd.precedent.census`:

| `modern_from` | Emir, 1878 row | Crown Prince, 1935 row | ministerial rows |
|---|---|---|---|
| 1970 (first Council of Ministers) | `early.unsupported` → **skip** | `early.unsupported` → **skip** | `modern.two_channel` → apply |
| 1850 | `modern.two_channel` → **apply** | `modern.two_channel` → **apply** | apply |

`precedent_allows` needs `supports_before(modern_from)`, which needs at least
three *dated* holder statements earlier than the cutoff. The Emir item has three
holders in total, starting 1972, 1995 and 2013. So at any cutoff after 1972 the
entire throne lane — the largest and cleanest gap in the country, 12 of roughly
30 roster statements — is skipped, and no amount of item-layer repair changes
that.

**Decision: `modern_from = 1850`.** This is not a relaxation. Qatar has one
continuous polity since the Al Thani established themselves at Doha; there is no
predecessor state of the Spanish or Ecuadorian kind whose offices need items of
their own, and the protectorate period changed the state's international status,
not the office. Rows still have to clear `modern.two_channel` — a roster row
plus a category or a citation — and `Precedent.covers()` still refuses any term
that predates an item's own declared inception, which Q25711499 sets to 1851.
The alternative considered and rejected was `modern_from = 1970` with
`continuous_eras` naming the emirate: `in_era("continuous")` feeds `_early`, so
it routes the rows *into* the rule that skips them.

## Item-layer defects — surgical, never batch lines

Per §2, these are `wikibase-cli` edits recorded in `tasks/followups.md`, made
before the sweep, not lines in the batch:

- Q54965863 Crown Prince, Q21328600 Shura member, Q108861084 Deputy PM and
  Q110183427 Chief of Armed Forces carry no `P571`, so `Precedent.covers()` has
  nothing to enforce.
- The four economic-portfolio items need `P1365`/`P1366` and inception/abolition
  to make the succession legible.
- The 2021-minted ministerial block carries English labels only, several without
  the "of Qatar" suffix ("Minister of Agriculture", "Minister of Labour"), and
  no `ar` label at all — a byproduct list, since `wd/api.py:best_label` falls
  back `en → mul` but the Arabic roster channel matches on labels.

## Decisions taken before planning

Three scope questions were put to the user and answered at maximum scope:

- **Family lane** → build the `{{Tree chart}}` reader, for `P22`/`P25`, rather
  than shipping `P53` alone on the Kuwait precedent. **The premise was wrong and
  the answer is better than asked for**: the tree charts are only the ruler
  succession line, and the real genealogy is a `{{Tree list}}` of nested bullets
  the workbench already knows how to read. The lane ships `P22` and `P53` for a
  one-clause change; `P25` is not in the source at all. See Lane F.
- **Infobox lane** → build the person-infobox tenure channel rather than
  reporting Qatar's ministerial history as undocumented.
- **Ambassadors** → include as a creation-first lane rather than deferring to
  the existing diplomatic campaign.

## Lanes

Written as `Office` declarations in `scripts/qa_offices.py`, plus one kinship
script. `ANY_TABLE = r".*"` — truthy, per the UAE bug.

### Lane A — the throne (roster, clean, the biggest gap)

| office key | target | source | rows | new |
|---|---|---|---|---|
| `emir` | Q25711499 | `en:Emir of Qatar` § List of rulers | 10 | 7 |
| `crown_prince` | Q54965863 | `ar:ولاية العهد في قطر` § قائمة ولاة العهد | 6 | 5 |

One source per office, per §7 — `ar:قائمة أمراء قطر` is **not** added beside the
English emir list. The two disagree (en dates Abdullah bin Jassim from 1914, ar
from 1913-07-17; the ar table also omits two rulers), and two rosters for one
office is two sources dating one tenure. English is the fuller list and wins;
the `أمراء قطر` category is the second channel and dates nothing.

Expect one genuine overlap the parser will not have misread: Ahmed bin Muhammed
1898–1905 sits inside Jassim's 1878–1913 reign. §7 says overlapping dates mean a
misparsed cell; here it is a contested succession the article states as such.
The audit must say so rather than "fixing" it.

`family = Q2502270`, `family_names = ("thani", "ثاني")` on both, so the P53
backfill rides the throne lane as the UAE's did.

### Lane B — the government (roster where one exists)

| office key | target | source | rows | new |
|---|---|---|---|---|
| `prime_minister` | Q30100647 | `en:Prime Minister of Qatar` | 7 | 2 |
| `deputy_pm` | Q108861084 | `en:Deputy Prime Minister of Qatar` | 9 | 4 |
| `foreign_affairs` | Q108861056 | `en:Ministry of Foreign Affairs (Qatar)` (bullets) | 8 | 3 |
| `justice` | Q110182394 | `en:Ministry of Justice (Qatar)` (bullets) | 8 | ~7 |

The PM table carries a `Time in office` column — the duration decoy that cost
Czechia (`Dny v úřadu`) and Kuwait (`الفترة الزمنية`) every date on their pages.
`wd.roster` already reads it as the `days` role; the check-dates suite should
pin the English spelling too.

Both ministry sources are `kind="bullets"`. Foreign Affairs dates rows as bare
appointment years with no end — a start-only term, which is correct, not a
defect.

The remaining **28 ministry articles carry no dated list at all**, so every other
portfolio reaches the batch only through Lane D.

Q110182394 Justice has no holders and no rival: the six people its roster
resolves hold no ministerial item at all between them, so there is no sibling
competing for the era and nothing for `duplicate_office_item` to catch. It is
also why the lane depends entirely on the `modern_from` decision — an item with
zero holders supports no precedent whatever.

### Lane C — central bank and security

| office key | target | source | rows | new |
|---|---|---|---|---|
| `central_bank` | Q110183389 | `en:Qatar Central Bank` § Governors | 4 | 2 |
| `chief_of_staff` | Q110183427 | Lane D only — no roster exists | — | — |

The central-bank table's first row reads `? - 1983 – January 1990`, which
`parse_period` currently resolves to `1983..1990-01`. The "?" is the source
saying it does not know the start; taking 1983 as a start is a parse defect and
that row must be dropped, not dated. This is a §7 case to add.

### Lane D — the infobox channel (the portfolios no roster reaches)

25 en + 8 ar person-articles carry `{{Infobox officeholder}}` with `office=` and
`term_start=` for people holding no `P39` at all; 47 more carry an office field
without dates and are a `no_dates` skip.

**Shape.** A new `wd/officebox.py` reading *wikitext*, not rendered HTML — the
numbered groups (`office`/`office1`/`office2` pairing with
`term_start1`/`term_end1`) are explicit in the source and collapse into
indistinguishable `<th>Assumed office</th>` rows once rendered. It emits
`RosterRow` objects, so `identify()`, the backtest, the policy table and the
render path are reused unchanged; the channel is a *source of rows*, not a new
kind of record.

**Field pairing.** Group by the numeric suffix; an unsuffixed `office` pairs with
unsuffixed `term_start`/`term_end`. Two traps observed in real Qatari data:
`|term_end = | birth_date =` on Q107379868, where an empty field runs into the
next and a naive line reader takes `birth_date` as the end value; and
`term_start = 17 December 2005<ref>{{Cite web|url=…}}</ref>` on Q118174084,
where the reference must be stripped before `parse_date` and its URL kept as
`ref_urls`.

**Routing.** `office=` is free text and its wikilink usually points at the
*ministry* (an organisation item), not the position item — Q115735972's
`office` links `Ministry of Commerce and Industry (Qatar)`. Route with the
`Office.section_targets` idiom (ordered pattern → QID, catch-all written `r""`),
matched against the link target first and the printed text second. Never
substring-match into position labels: CLAUDE.md's rule that the after-preposition
tail must match exactly applies here too.

**Second channel.** The per-portfolio Wikipedia category — en has 32, ar 33, and
they are maintained independently of the infoboxes. `officebox.two_channel`
applies where the infobox names an office *and* the person sits in that
portfolio's category; `officebox.one_channel` skips. A `{{Infobox officeholder}}`
populated from Wikidata tells us nothing new and must be refused outright, the
way `wd/infobox.py` already reasons about `bday`.

**Measured before trusted.** Infobox rows for people who *already* hold the
target enter the backtest like any other row. The channel ships only if its
target and date agreement are in the same range as the roster lanes; if it is
not, that is the report.

Non-PEP offices come through this channel too — Q100408297's first `office` is
president of the Qatar Football Association, Q118174084's is a football club
presidency. The routing table simply has no target for them, which is the
correct outcome, not a gap.

### Lane E — the ambassadors (creation-first)

54 ar per-country categories holding **125 member pages**, against ~10 existing
position items.

**The convention is already settled, and mechanically.** Ten exemplars read in
full (`Q108718564`, `Q112756747`, `Q40338387`, `Q110628980`, `Q65262135`,
`Q121629243`, `Q30593814`, `Q30636822`, plus the inbound `Q56761183`,
`Q107185088`):

| property | practice | decision |
|---|---|---|
| label (en) | `ambassador of Qatar to X` — 8 of 10 | use it; `Qatari Ambassador to X` is the older outlier |
| label (ar) | `سفير قطر لدى X` — 10 of 10 | mechanical |
| `P31` | `Q4164871` position — 9 of 10 | assert |
| `P279` | `Q38717123` *ambassador of Qatar* **and** the receiving state's *ambassador to X* class item — 10 of 10 | assert both; look the second up per country |
| `P17` | the **receiving** state, never Qatar — 8 of 8 that have it | assert |
| `P1001` | 2 of 10 | **do not assert** — a minority practice is not mass-asserted |
| description | 0 of 10 | none |

Q108718564 puts both parents on `P31` instead of `P279` — one item-layer defect
for the surgical list, not a reason to copy it.

**How many to mint.** `wd/create.py:guard` already imposes `min_holders=2`, which
lands exactly where the evidence does: **30 of the 54 categories have two or more
members, covering 101 of the 125 people**. The 24 single-member categories are
reported, not minted — one documented envoy is not evidence of an office worth an
item. Permanent representatives (UN, UNESCO, OAS) are a different archetype from
a bilateral ambassadorship and are excluded from this pass; `مندوبو قطر
الدائمون لدى الأمم المتحدة` alone has six members and deserves its own decision.

**Routing and dates.** The routing signal is unusually clean: one ar category per
receiving state *is* the office. The second channel is the person's own infobox
`office=` naming the same receiving state — which is Lane D's output, so this
lane depends on Lane D and must be built after it. Dates come from Lane D too;
where the infobox gives no term, the row is a `no_dates` skip, and the lane is
reported small rather than padded with undated statements.

One warning from the Jordan refresh applies directly: this is a **bucket lane** —
one `Office` routing forty-odd ambassadorships — and that is the exact shape
where `already_under_sibling` misfired, reading every portfolio as a sibling of
every other and suppressing thirteen true Jordanian statements. The fix landed on
2026-08-13 (era siblings kept, portfolio siblings dropped); this lane is its
first new user, so the backtest for it deserves reading twice.

### Lane F — the House of Thani

All three properties join the batch through
`Campaign.extra_verdicts = ("qatar_family.jsonl",)`.

**No `{{Tree chart}}` reader is needed. This was my error, and it makes the lane
much smaller than the scope question implied.** The 15 `{{Tree chart}}` calls at
the top of the section are only the ten-ruler succession line — decorative here.
The genealogy proper is in three branch subsections built with `{{Tree list}}`,
which renders as **`<div class="treelist">` wrapping nested `<ul>`**: 197 list
items at nesting depths 1–7. That is the Hashemite bullet-nesting shape
`wd/kinship.py` already reads for `en:Hashemites`, where the enclosing bullet is
the assertion (`Listed.depth`, `parent`, `parent_link`).

`parse_genealogy` misses it today for one narrow reason: it iterates the *direct
children* of `mw-parser-output` and handles `ul` nodes, and a `div.treelist` is
neither. The change is one clause — descend into `div.treelist` and parse its
`<ul>` with the existing nesting logic. Verified by hand: run against the page as
it stands, `parse_genealogy` returns 15 entries, all depth 1, from the unrelated
"Rulers" list.

**Measured yield.** The planning estimate here was 26 `P22` + 17 `P53`; the
built lane returns **7 + 7**. The estimate was wrong, and in a way this
workbench has a rule about: it came from a hand-written DOM walk that fell back
to `.//a` when a bullet had no direct anchor, so a child's link counted as its
parent's and 56 distinct titles inflated to 139. The shipped parser is the
strict one. Every matcher this workbench has built was too loose on the first
pass — this time it was the estimate rather than the code.

| measurement | estimate | measured |
|---|---|---|
| entries in the three branch lists | — | 170 |
| …carrying a real (blue) link | 179 | **64** |
| distinct person titles | 139 | 56 |
| …resolving to a human item | 59 | **49** |
| redlinks, i.e. an item-creation byproduct | 80 | 87 anchors |
| children under a linked parent | 78 | 48 |
| …already recording `P22` | — | **39** |
| open `P22` cases | 26 | **9** |
| `P22` the patronymic resolves | — | **7** (3 skip) |
| `P53` proposed | 17 | **7** |

So Lane F is **14 statements**, not 43. The lane is small by arithmetic rather
than by conservatism: half the house has no article, and of what remains four
fifths already records its father. Two things it is not:

- **`P25` is unavailable.** Nothing in the tree names a mother; the lists are
  purely patrilineal and carry no marriage join. Report it, do not fake it.
- **The 37 `P53` gaps are not all reachable.** Only 59 of the 91 Al Thani census
  items appear in the tree, and `house_records`' `house.listed_and_named` rule
  needs the person listed *and* named. The residue is reported, not padded in
  from the category alone — a name without a second channel is a namesake. Note
  also that `wd/campaign.py:family_records` iterates `per_person`, so
  `Office.family` on the throne lanes reaches only the sixteen people in those
  rosters; it is not an alternative route to the rest.

**Three failure modes this article has, all of which must be handled:**

- **25 placeholder entries** of the form `Sheikh ??? bin Nasir Al Thani` — real
  bullets naming nobody. They must be dropped, not resolved; this is a new §7
  mode.
- **14 titles appear at more than one depth in the tree**, e.g. `Abdullah bin
  Jassim Al Thani` at both the second and fourth generation. §4a's rule stands:
  one link in two generations is a wiki error, so `contradictory_links` skips
  both.
- **A piped link whose printed name contradicts its target** — `[[Hamad bin
  Abdullah Al Thani|Hamad Bin Jassim Al Thani]]`. §4a: take the chain from the
  *item's* full name, never the printed short form (`child_chain`).

The patronymic remains the second channel, as in Saudi Arabia: an edge the tree
asserts and the item's own name chain confirms is applyable
(`father.listed_and_named`); an edge only one channel asserts skips
(`father.one_channel`). Qatari naming makes this unusually strong — "Tamim bin
Hamad bin Khalifa Al Thani" states father and grandfather — but Saudi Arabia's
first patronymic pass still produced two false positives, so the audit gets read
in full before anything renders.

`ar:قالب:شجرة أمراء قطر` is a second tree over the ruling line only (11 boxes),
using the same edge glyphs with Arabic keys. It is **not** wired in: it adds
nothing the en branch lists do not already assert, and a second source dating the
same edges is the §7 trap, not a bonus.

### Not a lane — the Consultative Assembly

`Q21328600` has one holder and the 2021 roster names 45 people, of whom **one
has a Wikidata item**. The lane is reported as an item-creation byproduct list in
`tasks/followups.md`, not padded into the batch. The ar article's history section
records the council's shape changes (formed 1972, ten members added 1975), which
is what a future creation run needs.

## Campaign parameters

```python
CAMPAIGN = Campaign(
    name="qatar",
    country_qid="Q846",
    modern_from=1850,               # see the section above; 1970 empties Lane A
    offices=OFFICES,
    label_langs=("en", "ar"),
    sibling_wikis=("ar", "en"),     # ar carries the people, en the rosters
    evidence_verb="lists them in the office",
    concurrency_ignore=(            # measured: 9 concurrent pairs on 5 people
        "Q25711499",   # Emir
        "Q54965863",   # Crown Prince
        "Q30100647",   # Prime Minister
        "Q108861084",  # Deputy Prime Minister
        "Q108861056",  # Minister of Foreign Affairs
        "Q110182528",  # Minister of the Interior
        "Q110182640",  # Minister of Defence
    ),
    dispositions={                  # no review queue
        "namesake": "skip",
        "predecessor_body": "skip",
        "category_only": "skip",
        "no_dates": "skip",
        "believed.held": "skip",
        "uncertain": "skip",
    },
    extra_verdicts=("qatar_family.jsonl",),
)
```

`concurrency_ignore` is not optional here. Measured on live data: the sitting
prime minister is simultaneously foreign minister, Khalid bin Mohammad Al Attiyah
held foreign affairs, the deputy premiership and defence together, and Khalid bin
Khalifa held the interior ministry and the premiership from the same day. Left
out, `interim_of` reads each overlap as cover and stamps `P2868 = Q4676846` on
nine real appointments.

## Byproducts, and where each one lands in `tasks/followups.md`

| byproduct | existing heading |
|---|---|
| the 44 Shura members with no item (2021 council, 15 appointed + 30 elected minus the one that exists) | *Item-creation rosters (people, not offices)* |
| the ~45 `ambassador of Qatar to X` position items | *Position/body items to create* |
| missing `P571` on Crown Prince, Shura member, Deputy PM, Chief of Armed Forces; the economic-portfolio `P1365`/`P1366` succession; the label-only ministerial block | *Surgical (wikibase-cli, stop-and-ask)* |
| the 80 redlinked Al Thani in the genealogy | *Item-creation rosters (people, not offices)* |
| `P25` for the House of Thani — no source states a mother | *Deferred lanes* |
| the 24 single-envoy ambassadorships below the holder floor, and the UN/UNESCO/OAS permanent representations | *Deferred lanes* |
| Q108718564, which puts both parents on `P31` instead of `P279` | *Surgical* |
| the Q23020336 deputy-premiership date conflict | *Surgical*, after reading the sources |

## What the run produced

Run 2026-08-13/14, all five lanes. **71 `.qs` lines writing 69 statements**, no
API half — 55 `P39`, 9 `P53`, 7 `P22` — against 87 recorded skips. The 21
ambassador position items were minted first (`created.json`), which is what
unblocked Lane E's 14 statements.

**Applied 2026-08-14.** All 69 claims verified live on Wikidata afterwards, none
missing; QuickStatements merged the two `P53` lines that carry different
references into one statement each, which is why 71 lines make 69 statements.

| lane | planned | built |
|---|---|---|
| A throne (emir, crown prince) | 12 | 12 |
| B government (PM, deputy PM, foreign affairs, justice) | 16 | 16 |
| C central bank | 2 | 1 |
| D infobox tenures | ≤33 | **13** (27 officebox applies in total, 14 of them Lane E's) |
| F House of Thani — `P22` | 26 | **7** |
| F House of Thani — `P53` | 17 | **7** |
| F House of Thani — `P25` | 0 | 0 — no mother edges exist |
| E ambassadors | ≤101 | **21 items minted; 14 statements** |

Two estimates were wrong in opposite directions and both are worth recording.

**Lane F's was too high**, and the reason is the rule this workbench already has
about matchers: the planning figure came from a DOM walk that fell back to
`.//a`, so a child's link counted as its parent's. The shipped parser is strict;
half the house is redlinked and four fifths of the rest already record a father.

**Lane E needed items before it could yield anything.** 21 bilateral
ambassadorships were minted through `scripts/create_offices.py --country qa
--apply`, all 21 clearing the guard, and the lane then wrote 14 `P39`s — every
one dated from an ar.wikipedia infobox and sourced to that article's revision.
The shape needed `wd.create.CreateSpec.claims_override`, because an outbound
posting inverts the default: `P17` is the *receiving* state, `P279` carries two
parents, and `P1001` is not asserted. It also exposed a bug in every campaign's
creation path — `create_offices.py` never passed `country_label`, so the
description template rendered a raw QID ("diplomatic post of Q846").

**Lane D's was too low, by a factor of six.** The plan counted Arabic infobox
fields under the bare stems `منصب` and `بداية`, which match 16 of 222 Qatari
ar.wikipedia articles. The definite forms the template actually uses — `المنصب`,
`بداية الفترة`, `نهاية الفترة` — match 101, and carry **213 dated tenures for
people with no `P39` at all**. That the lane still yields 13 is the two-channel
gate working as designed: 102 of the 227 dated tenures are ambassadorships
waiting on Lane E's items, 42 are sub-ministerial or non-PEP and route to no
item, and the rest are already recorded.

The multi-tenure claims file is **empty**, though the backtest predicted nine
such spells. They are all second spells by people who already hold the target
for a different one, so the person-level `already holds P39` gate drops them
before they reach the batch. That gate is coarser than the statement it
protects, and those nine spells remain unwritten — a followup, not a defect
this run introduced.

This is a five-checkpoint job, not one sitting. Stop and report at each:

1. `wd/roster.py` keys + `check_dates` + a clean diff against the step-0 capture;
2. the `div.treelist` clause in `wd/kinship.py` and the family lane, with its
   false-positive rate against the patronymic channel;
3. the infobox channel, with its backtest scores beside the roster lanes';
4. ambassador item creation, dry run read in full before `--apply`;
5. the sweep, the audit read, and the rendered batch.

If a checkpoint's numbers disappoint — the treelist clause recovers fewer edges
than the 53 counted here, the infobox channel backtests below the roster lanes —
that is the report, not the cue to loosen a rule. Nothing here is relaxed to
raise the count, and a lane with one weak channel is reported small rather than
padded.

## Parser work in `wd/roster.py`

Small, and each case goes into `scripts/check_dates.py`:

- **`? - 1983 – January 1990`** (`en:Qatar Central Bank`) resolves to
  `1983..1990-01`. The `?` is the source declining to state a start; taking the
  next number is the §7 "a pattern that matches but fails its lookup" family.
  A cell whose start is explicitly unknown must yield no start.
- **`طول الفترة`** ("length of the period", `ar:قائمة أمراء قطر`) is a duration
  column and currently falls through to `col6`. It broke nothing here only
  because the two real date columns were recognised, which is precisely how the
  Czech `Dny v úřadu` and Kuwaiti `الفترة الزمنية` bugs stayed invisible until
  they weren't. Add it beside them as a `days` decoy.
- **`Constituency` / `Elected member`** (`en:2021 Qatari general election`):
  neither maps to `name`, so the members land in `notes` and their links are
  never collected. Needed only if the Shura lane is ever revived after item
  creation, but the keys are free.
- **`الأعضاء`** ("the members", the ar Shura list) — same, plus that table has no
  date column at all and needs `RosterSource.term` to be read.
- **`Sheikh ??? bin Nasir Al Thani`** — 25 bullets in `en:House of Thani` name
  nobody. A placeholder is not a person and must be dropped before resolution;
  new §7 mode, pinned in `wd/kinship.py`'s cases.
- **`{{Succession table monarch}}`** concatenates the ruler's name with a gloss
  in one cell ("Sheikh Mohammed bin ThaniHakim of Qatar Peninsula…"). Identity
  survives because it comes from the wikilink, but an unlinked row would fail
  `names_match`. Record the shape; do not paper over it.

## Files

| path | what |
|---|---|
| `scripts/qa_offices.py` | the office lanes and `CAMPAIGN` |
| `scripts/qa_family.py` | the House of Thani lane |
| `wd/officebox.py` (new) | person-infobox tenure channel, emitting `RosterRow`s |
| `wd/roster.py` | the column keys and the `?`-start fix above |
| `wd/kinship.py` | the `div.treelist` clause, placeholder and repeated-link handling |
| `wd/campaign.py` | additive hook so an `Office` can take infobox rows as a source |
| `scripts/create_offices.py` | `"qa"` in `SCRIPTS`, for the ambassador lane |
| `scripts/check_dates.py` | a pinned case per parser change |
| `recipes/country_sweep.md` | the new §7 modes and a calibration-table row |
| `tasks/followups.md` | Shura creation list, item-layer defects, byproducts |
| `regression/qatar/` | verdicts, manifest, `.qs`, claims — after acceptance |

## Order of work

The ordering constraints are not stylistic. Creation must precede the sweep
because QuickStatements' `LAST` is valid only as a statement's *subject*, so an
item minted in a batch cannot be the value of a `P39` in that same batch. The
parser suite must precede the profile because seven other campaigns share the
engine.

0. **Capture the net before changing anything.** Run all eight prior campaigns
   on today's unmodified code and keep their verdicts — `saudi` and `jordan` need
   both their offices *and* family scripts. This is the baseline every later diff
   is against, because `regression/` no longer reproduces (see Verification).
1. **Parser first.** `wd/roster.py` keys and the `?`-start fix, then
   `scripts/check_dates.py` to pin them.
2. **Diff against the step-0 capture**, not against `regression/`. Any diff is a
   stop-and-report, not a fix-and-continue.
3. **Item-layer repairs**, surgically via `wb`: the missing `P571` values and the
   economic-portfolio succession. Recorded in `tasks/followups.md`.
4. **The two new channels**, each with its own pinned cases and its own clean
   diff — they are additive and must leave the eight existing campaigns
   bit-identical. `wd/kinship.py`'s treelist clause must be diffed against Saudi
   Arabia and Jordan specifically, since they are its existing users.
5. **The family lane** — `scripts/qa_family.py`, then read
   `data/qatar/kinship_audit.md` in full before anything else.
6. **Ambassador item creation** — after Lane D exists, since the holder floor is
   evidenced from it. `scripts/create_offices.py --country qa` dry, read the
   output, then `--apply`. **Human gate.**
7. **The sweep** — `scripts/qa_offices.py`, then read the `## Backtest` section
   of `data/qatar/roster_audit.md` first and the audit end to end after.
8. **Render** — `scripts/render_edit_plan.py --retrieved <today> --campaign qatar`.
   `wd/validate.py` refuses on a defect.
9. **Human gates** — the `.qs` in the QuickStatements importer, then
   `scripts/apply_claims.py --campaign qatar` dry, then `--apply`.
10. **Baseline** — copy verdicts, manifest, `.qs` and claims into
    `regression/qatar/` and add the row to `regression/README.md`.

## Verification

- `scripts/check_dates.py` passes before and after every `wd/roster.py` or
  `wd/kinship.py` change.
- **The regression net does not currently work, and this campaign changes the
  engine more than any before it.** `regression/README.md` is explicit: all nine
  batches have been applied upstream, so a re-run correctly drops every record
  whose statement now exists and every baseline diffs large for reasons that have
  nothing to do with the engine. "Diffs clean" is not available as a signal.

  The interim procedure the README prescribes is the one to follow, and it is
  slow on purpose: capture a **pre-change run of every campaign before touching
  anything** (step 0, added below), diff each post-change run against *that*
  rather than against `regression/`, lean on `scripts/check_dates.py` which pins
  parsing and merging directly, and hand-check that any record which vanished
  did so because its statement is genuinely on Wikidata.

  If the pre-change capture turns out to be more work than it looks, that is a
  stop-and-report — it is the difference between an additive change and an
  unverifiable one, not a step to skip.
- The backtest numbers above are the pre-registered expectation: target
  agreement 100% on emir, crown_prince, prime_minister and deputy_pm; date
  agreement 100% except the one deputy-PM conflict. A drop means the change
  broke something, and a whole office at 0% is a comparison bug before it is a
  parser bug.
- Every new channel is measured by the backtest *before* it is trusted: rows it
  proposes for people already on record must agree with what the community
  wrote. A channel that cannot be backtested does not ship.
- `wd/validate.py` must render without defects, and `collapsing_groups` must
  find the multi-tenure people the backtest already predicted.
- Spot-read the full `data/qatar/roster_audit.md` — every matcher this workbench
  has built was too loose on the first pass.

## Explicitly out of scope

- **The Consultative Assembly as a statement lane.** One of 45 members has an
  item; it is a creation list.
- **`en:Cabinet of Qatar` as a dated source.** It is the sitting cabinet, dates
  nothing, and the sitting minister is the one holder each item already has.
- **Inbound ambassadors** (other countries' envoys *to* Qatar) — 19 UK, 9
  Spanish, 7 French and so on. Scoped to Qatar but not this sweep's lane, per
  the Kuwait precedent.
- **`ar:آل ثاني` as a genealogy source.** It has no family tree.
- **`ar:قالب:شجرة أمراء قطر` as a second genealogy.** It covers only the ruling
  line the English branch lists already assert; two sources for one edge is the
  §7 trap.
- **`P25` and `P26` for the House of Thani.** No source states a mother or a
  marriage. This is the one thing the approved scope asked for that the data
  cannot supply.
- **Hijri conversion.** Qatari rosters date in Gregorian, so the Saudi problem
  does not arise here; the no-conversion behaviour stays pinned regardless.
- **Merges and any destructive edit.** If two items compete for one era, that is
  a merge decision and a human gate, not a campaign.
