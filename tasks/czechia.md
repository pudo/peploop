# Task: Czechia — category members → real P39 statements

Third country run of `recipes/category_check.md`, over the 13 Czech specs in
`wd_categories.yml` (8 carrying a synthetic `position:` block). Czechia is the
extreme of the Belarus case: Wikidata's coverage is close to complete, so the
deliverable is the documented review tiers and the byproduct lists, not the
batch.

## What the survey found (2026-08-05)

**Czechia is the best-covered country this workbench has measured.** 192
position items carry P17/P1001 = Q213, with **14,124 P39 holder statements** —
against Belarus's 628 items / 2,016 statements and Ecuador's 79 items. The
volume is municipal and parliamentary: member of a Czech municipal council
(1,774 holders), Chamber of Deputies (1,217), district representative (553),
Senate (345).

The category-to-target join says how little is left to win:

| spec (depth) | members | humans | hold the target | gap |
|---|---|---|---|---|
| `Poslanci Parlamentu ČR` (1) | 1227 | 1223 | 1222 | **1** |
| `Poslanci Parlamentu ČR (2021–2025)` (0) | 212 | 212 | 212 | **0** |
| `Senátoři Parlamentu ČR` (1) | 359 | 356 | 345 | **11** |
| `Senát Parlamentu ČR` (1) | 291 | 287 | 276 | 11 (same people) |
| `Prezidenti ČR` (0) | 6 | 4 | 4 | **0 — complete** |
| `Soudci Ústavního soudu ČR` (0) | 46 | 46 | 45 | **1** |
| `Soudci Nejvyššího soudu ČR` (0) | 25 | 25 | 0 | **no item exists** |
| `Soudci Nejvyššího správního soudu ČR` (0) | 20 | 20 | 0 | **no item exists** |
| `Ministři vlád ČR` (1) | 360 | 335 | — (bucket) | 39 hold no Czech position |
| `Political office-holders in the CR` (1) | 112 | 79 | — | 4 |
| `Members of the Parliament of the CR` (1) | 57 | 51 | — | 21 |
| `Čeští politici` (0) | 393 | 378 | — | 277 (municipal catch-all) |

Three structural differences drove the run:

* **Every portfolio has a dedicated list article.** cs.wikipedia keeps 22
  `Seznam ministrů <portfolio> České republiky` pages, all from one template:
  a dated table per era with the appointing cabinet, the party and per-row
  footnotes. This is the Ecuador `Anexo:` shape at full coverage — no bullet
  lists, no ministry-article scraping, no interwiki sibling hunt (the cs
  categories are already the comprehensive ones).
* **Two eras share every office name *and every item*.** The tables separate
  "V rámci československé federace" (the Czech Socialist Republic, then the
  Czech Republic as a federal unit, 1969–1992) from "V rámci samostatné
  republiky" (1993 on). See the ruling below — this is the one decision that
  matters.
* **The categories carry Protectorate and Czechoslovak officials.** The
  Protectorate of Bohemia and Moravia (1939–1945) and federal Czechoslovakia
  had ministers of the same portfolios, and cs.wikipedia files several of them
  in the Czech Republic categories.

## Result: 6 statements, and a much stricter matcher

`data/czechia/{edit_plan.md,edit_plan.qs,roster_audit.md}` — 21 offices, 486
roster rows:

**6 batched adds** (two-channel, post-1993): Alexandr Vondra (European
Affairs 2007–2009), Igor Červený (Environment, incumbent from 2026-02-23),
Michal Bartoň (Constitutional Court, from 2025-12-18), and three
without-portfolio ministers — Pavel Bratinka, Jaroslav Bašta, Petr Mlsna.
**446 roster rows already held their P39.**

Held back, grouped by era in `edit_plan.md`:

| era | n | what it is |
|---|---|---|
| `federal_cr` | 32 | 1969–1992 ministers of the Czech Republic *within the federation* |
| `category_only` | 12 | in the category, named by no roster row |
| `roster_only` | 8 | named by the roster, in no category (all without-portfolio) |
| `protectorate` | 4 | the 1939–1945 Protectorate premiers |
| `interim_concurrent_office` | 4 | a short spell covering a second portfolio |

**Sourcing is weak, as in Belarus**: 1 of 6 statements carries a real citation
(Bratinka's own biography page); the other 5 cite the roster permalink as
S4656. The cs tables do footnote rows, but rarely the ones that were still
missing.

## Decisions the user needs to make

1. **The federal era (32 rows) — the big one.** Do 1969–1992 ministers of the
   Czech Republic belong on the items labelled for the Czech Republic? The
   measured convention says the community already thinks so: Agriculture
   carries 10 pre-1993 terms of 27, Education 9 of 31, Culture 7 of 25, Justice
   6 of 27, all reaching back to 8 January 1969, and two items
   (Q110408550 Minister of Industry, Q110409158 Minister of Commerce and
   Travel) exist *only* for abolished federal portfolios. It is nonetheless a
   continuity judgment about communist-era ministers of a federal unit, so
   nothing was batched. Promoting them is one line: drop the `federac` branch
   from `REGIMES` in `scripts/cz_ministers.py` and re-render.
2. **The 4 interim spells.** Vladimír Špidla is the roster's 8th and 10th
   minister of justice (41 and 50 days) — both inside his own premiership — and
   its 6th minister of health (61 days) while he was labour minister; Zdeněk
   Škromach is its 11th minister of health (23 days) while deputy premier. The
   convention is `P39` + `P2868 = Q4676846`; say the word and they go in with
   that qualifier.
3. **The Protectorate premiers** (Beran, Eliáš, Krejčí, Bienert) need their own
   item; they are on the `Seznam premiérů Česka` page but in no Czech category.

## Surgical edits (wikibase-cli, not the batch)

* **Q12043172 Otakar Fischer holds Q20058795** (Minister of the Interior of the
  Czech Republic) with 1939-03-01 → 1939-04-01 — a Protectorate interior
  minister on the modern item. Remove, and create the Protectorate item.
* **Q12028974 Kateřina Šimáčková**'s Constitutional Court statement is *normal*
  rank while her ECtHR one is *preferred*. Nothing is wrong with the data, but
  it is why `wdt:P39` under-reports coverage (see the gotcha added to
  `CLAUDE.md`).

## Byproducts: items that need creating

Four portfolios have a cs.wikipedia roster but **no Wikidata position item**:

| portfolio | holders on the roster |
|---|---|
| Minister of Informatics (2003–2007) | Vladimír Mlynář, Dana Bérová, Ivan Langer (all dated) |
| Minister for Science, Research and Innovation | Langšádlová, Ženíšek (+ Mareš, Bělobrádek as deputy PMs) |
| Minister for Sport, Prevention and Health (2025–) | Boris Šťastný |
| Minister for Legislation | 10 holders, month precision; distinct from Q59773536 (chair of the Legislative Council) |

And two courts, which are the largest single gap in the block:

* **Judge of the Supreme Court of the Czech Republic** — 25 category members,
  19 with no Czech position at all. Only the generic Q117826617 "supreme court
  judge" exists.
* **Judge of the Supreme Administrative Court of the Czech Republic** — 20
  members, 12 with nothing. Q135399028 "soudce nejvyššího správního soudu"
  exists as a generic label with 0 holders.

Several members of both categories currently carry only their *Constitutional*
Court P39, because judges move between the courts.

## What this run added to the tooling

* **`wd/roster.py` speaks Czech**: month names in the genitive, ordinal day
  numbers ("2. července 1992"), Czech diacritic folding, and the column
  vocabulary (`Ministr`/`Premiér`/`Soudce`/`Jméno`, `Funkční období`, `Nástup do
  úřadu`, `Strana`, `Vláda`, `úřadující` as the incumbent marker).
* **`_subroles()`** — a second header row refines a wide one. cs.wikipedia heads
  three columns "Funkční období" and labels them "Nástup do úřadu", "Opuštění
  úřadu", **"Dny v úřadu"**; without this the day count is a candidate end date,
  and a 1,939-day tenure reads as the year 1939.
* **Fixed a bug that had disabled `_is_date_phrase` entirely.** Its separator
  class was `[\s.,()/-–—‒―]+`, in which the unescaped `-` after `/` forms the
  range U+002F–U+2013 — every digit and letter — so the function always
  returned `False`. This is the cause of the Belarus telecom page parsing 0
  rows (recorded as open in `tasks/belarus.md`).
* **Rowspan continuation rows are dropped** when they restate both the person
  and the term (a spell straddling two cabinets), and `merge_terms` dedupes
  identical spans.
* **Vacancy rows are not people**: `VACANT` drops "Funkce neobsazena" / "Funkce
  nevyužívána", which were 11 of 11 entries in the audit's `no identity` column.
* **`interim_of()` + `Campaign.concurrency_ignore`** — a spell shorter than 90
  days that falls inside a dated term the person already holds for another
  office is cover, not a term. Both channels are required: Petr Krčál really
  was labour minister for 21 days. Parliamentary and council seats are ignored,
  since a minister holds those throughout.
* **`short_spells()`** warns in the audit about brief tenures that the
  concurrency rule did *not* catch.

Ecuador and Belarus re-run and diffed (recipe step: "when the engine changes,
re-run the previous country"): **Ecuador byte-identical** (423 verdicts, 97
batchable). **Belarus batchable unchanged at 10**, with 7 `lifespan_not_term`
records replaced by 6 correct `historical_roster_only` adds — the health
bullets' leading dates are now read as the term instead of the trailing
lifespan — plus Postoialko and Ostapenko correctly recognised as already
covered.

## Not covered

* **Parliament**, where the volume is, is already done: 1,222 of 1,223 deputies
  and 345 of 356 senators hold the item. The 12 remaining are a targeted
  lookup, not a campaign; the per-term list articles
  (`Seznam členů Poslanecké sněmovny … (2021–2025)`, 10 of them, plus 16 Senate
  ones) exist if per-term qualifiers are ever wanted.
* **`Čeští politici`** (378 people, 277 with no Czech position) and
  `Political office-holders in the Czech Republic` are municipal/regional
  catch-alls — the deferred lane, and where the next real yield is.
* **Deputy Prime Minister** (Q61882567, 42 holders) and the **five abolished
  federal portfolios** with categories but no roster page and no item
  (kontroly, plánování, stavebnictví, lesního a vodního hospodářství, výstavby
  a techniky — 3–7 members each).
* **PETScan noise, quantified**: `Political office-holders` 112 members → 79
  humans; `Ministři vlád ČR` 360 → 335. Enforcing `P31=Q5` is not optional.

## `wd_categories.yml` proposals

* `Lists_of_members_of_the_Chamber_of_Deputies_of_the_Czech_Republic` has **0
  members at depth 0, 1 and 4** — it is a container of list articles. Drop it.
* `wikidata_id` can replace the `position:` block on five specs, all verified:
  `Poslanci Parlamentu ČR` and `Poslanci … (2021–2025)` → Q19803234,
  `Senátoři Parlamentu ČR` → Q18941264, `Prezidenti ČR` → Q1819381,
  `Soudci Ústavního soudu ČR` → Q59773473.
* `Ministři_vlád_České_republiky` is a bucket that should be **split into its 22
  portfolio subcategories**, each with its own `wikidata_id` — the resolutions
  are in `scripts/cz_ministers.py`.
* The two supreme-court specs must wait on item creation.
* `Senát_Parlamentu_České_republiky` is a topic category (1 member at depth 0);
  its people arrive only at depth 1, via the `Senátoři` subcategory the block
  already lists separately.

## Status

- [x] survey: 13 specs, 192 target items / 14,124 holder statements, per-spec
  gap join, roster inventory (2026-08-05)
- [x] Czech support + three parser bug fixes in `wd/roster.py`; `interim_of` and
  `short_spells` in `wd/campaign.py`; Ecuador and Belarus re-verified by diff
- [x] run: 21 offices, 486 rows → 6 batched adds, 60 review rows,
  `data/czechia/edit_plan.{md,qs}`
- [ ] human review → apply the 6
- [ ] rule on the federal era (32), the 4 interim spells, the 4 Protectorate
  premiers
- [ ] surgical: remove Otakar Fischer's 1939 term from Q20058795
- [ ] create items: 4 portfolios + the two supreme courts (45 members waiting)
- [ ] `wd_categories.yml`: the five `wikidata_id` swaps, the bucket split, and
  drop the empty `Lists_of_members_…` spec
