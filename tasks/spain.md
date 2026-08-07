# Task: Spain — category members → real P39 statements

Fourth country run of `recipes/category_check.md`, over the 13 Spanish specs in
`wd_categories.yml` (7 carrying a synthetic `position:` block). Spain is the
largest block this workbench has measured, and it is the first where the
question is not *whether* a term is missing but **which item it belongs on**.

## What the survey found (2026-08-06)

**Spain: 13,284 position items carrying 50,523 P39 holder statements** — against
Czechia's 192/14,124, Belarus's 628/2,016, Ecuador's 79 items. The volume is
parliamentary and municipal, and it goes back two centuries: member of the
Congress of Deputies (3,790 holders), procurador en Cortes 1943–1977 (2,495),
senator (1,693), member of the Congress 1876–1923 (1,145), member of the
Parliament of Catalonia (1,074).

The category-to-target join (en.wikipedia categories, depth 1, `P31=Q5`
enforced):

| spec | members | humans | hold the target | hold *no* Spanish position |
|---|---|---|---|---|
| `Members_of_the_Congress_of_Deputies_(Spain)` | 573 | 551 | 248 | 36 |
| `Members_of_the_Senate_of_Spain` | 311 | 299 | 164 | 37 |
| `Presidents_of_the_Congress_of_Deputies` | 70 | 70 | 28 | 1 |
| `Presidents_of_the_Senate_of_Spain` | 39 | 39 | 35 | 0 |
| `Prime_ministers_of_Spain` | 124 | 123 | 15 | 10 |
| `Deputy_Prime_Ministers_of_Spain` | **0** | 0 | 0 | — |
| `Government_ministers_of_Spain` | 700 | 661 | 0 (bucket) | 22 |
| `Judiciary_of_Spain` | 38 | 33 | — | 5 |
| `Presidents_of_the_autonomous_communities` | 178 | 157 | — (no id) | 2 |
| `Ministers_of_Spanish_autonomous_communities` | 235 | 190 | — | 39 |
| `Mayors_of_places_in_Spain` | 494 | 441 | **1** | 67 |
| `Political_office-holders_in_Spain` | 478 | 373 | — | 23 |
| `21st-century_Spanish_politicians` | 1501 | 1455 | — | 238 |

Read the "hold the target" column as a warning, not a gap: 15 of 123 prime
ministers hold Q844587 because the other 108 held **Q16020745 Presidente del
Consejo de Ministros**, and 1 of 441 mayors holds Q5663900 because mayors hold
a per-municipality item. Spain models offices at the level of the *ministry
configuration*, so a portfolio is a succession of items.

### The structural fact: one office, several items

Measured per portfolio by tallying the P39s of each es.wikipedia portfolio
category's members, split at 1977:

* **Foreign affairs**: Ministro de Estado (Q32969013, 132 dated terms, all
  pre-1945) → Asuntos Exteriores (Q25672112, declares itself abolished 2004) →
  …y de Cooperación (Q26262159, 2004–2018) → …, Unión Europea y Cooperación
  (Q54877757, 3 terms, all after 2018). A clean succession, and the join is by
  date.
* **Justice**: Gracia y Justicia (Q32978760, 126 terms in 1834–1931, one after)
  → Justicia (Q24279063, 39 pre-1977 and 19 modern). The Second Republic's 1931
  rename is the boundary.
* **Congress presidency**: Q17014422 (15 terms pre-1834, 32 in 1834–1876, **0**
  in 1876–1923, every modern one) and Q45213921 (31 terms in 1876–1923,
  inception 1876) — plus Q43118787 for the Cortes republicanas and Q43138757 for
  the Cortes franquistas. Four items, one office, and only one of them says so
  in its label.
* **Labour** and **education** are the unhappy case: Q44487637 "Minister of
  Labour" (inception 1920, 18 dated terms across every era) competes with
  Q87001438 "minister of Labor, Migration and Social Security" (a 2018–2020
  ministry name carrying 17 terms from 1919 onward). Both are used as the
  generic item by different editors. No office was declared for either — see
  "not covered".

`Office.date_targets` was added for this, and it is what makes the run possible.

### Rosters

es.wikipedia keeps `Anexo:` list articles, but their quality varies more than in
Ecuador. Usable (full dates, wikilinked names, per-row BOE citations):

| page | rows |
|---|---|
| `Anexo:Ministros de Asuntos Exteriores de España` | 198 |
| `Anexo:Ministros de Justicia de España` | 253 |
| `Anexo:Presidentes del Senado de España` | 112 |
| `Anexo:Presidentes del Tribunal Supremo de España` | 50 |
| `Anexo:Presidentes del Gobierno de España` | 22 |
| `Anexo:Presidentes de comunidades autónomas españolas` | 136 |
| `en:List of presidents of the Congress of Deputies` | 273 |

Unusable, and worth knowing why: **Fomento, Hacienda, Economía, Interior** each
have an `Anexo:` page that is a *portrait grid* — three to five cells per era,
no date column at all (the new date-column guard drops them). **Industria** and
`Anexo:Presidentes del Consejo de Ministros de España` are tables with no
`wikitable`/`sortable` class and one row per *cabinet* with an events column.
**Defensa** parses (76 rows) but names the row's own office inside the name cell
("Ministro de la Guerra", "Ministro del Ejército") because three service
ministries ran in parallel from 1939 to 1977 — routing that needs per-row office
reading, which the engine has no channel for yet.

## Result: 93 records, 111 statements

`data/spain/{edit_plan.md,edit_plan.qs,roster_audit.md}` — 7 offices, 1,044
roster rows, **789 of them already hold their P39**.

* **89 P39 statements** on 12 target items: 23 Ministro de Estado (Q32969013),
  18 President of the Congress (Q17014422, 3 of them acting with
  `P2868 = Q4676846`), 17 Gracia y Justicia (Q32978760), 9 Justicia (Q24279063),
  6 President of the Senate (Q1335465), 4 Asuntos Exteriores (Q25672112), 1 its
  2004–2018 successor (Q26262159), 10 presidents of autonomous communities
  (Canarias 5, Murcia 3, Castilla y León 1, Ceuta 1), 1 prime minister.
* **22 P102 statements** — party memberships the roster's party column proves for
  people carrying no P102 at all.
* `wd/validate.py` passes with no defects: every date is day-precision, none
  ends before it starts, no line is repeated. One warning — Q6006897's party
  membership appears on two lines with two different roster permalinks, so the
  batch writes **110 statements from 111 lines**.
* **Sourcing is weak: 7 of 111 statements carry a real citation** (BOE decrees,
  senado.es), the other 104 cite the roster permalink as S4656. The Spanish
  tables footnote rows generously, but rarely the rows that were still missing.

Held back by rule:

| rule | n | what it is |
|---|---|---|
| `category_only → review` | 131 | in the category, named by no roster row — **100 of them are prime ministers**, i.e. the 19th-century Presidentes del Consejo de Ministros whose item is Q16020745 and whose roster is unparseable |
| `duplicate_office_item → skip` | 44 | the term is already on record under another item *of the same office* (22 on Q45213921, 13 on Q24279063, 8 on the foreign-affairs successors) |
| `interim_concurrent_office → review` | 20 | see the ruling below |
| `early.unsupported → skip` | 9 | the Antiguo Régimen secretaries of Gracia y Justicia, 1714–1834; Q32978760 declares inception 1851 |
| no identity | 92 | 82 of them Cortes de Cádiz presidents (1810–1814) with no Wikidata item |

### The one ruling this run made

**`interim_concurrent_office` is routed to `review` for Spain**
(`Campaign.dispositions`). The rule reads a spell shorter than 90 days that
falls inside a dated term the person holds elsewhere as *cover*, and adds
`P2868 = Q4676846`. In Spain that inference does not hold: 19th-century
ministries and Cortes presidencies routinely lasted weeks (the Cortes de Cádiz
elected a president **monthly**), and the "other office" the rule matched was as
often a lifetime post — senator for life, the bishopric of Majorca, the embassy
to the Russian Empire — or an item for the *ministry* rather than the minister.
Nine of the eighteen it first caught were premiers who held the Estado portfolio
substantively, which is the opposite of acting. It still flags them; the flag now
asks a human instead of writing a qualifier.

### The two statements to look at first

`roster_audit.md` prints exactly two date overlaps, and both are real history
rather than a parse error: **1936–1939 had two governments**. The Republic's
minister of state (Álvarez del Vayo) overlaps Franco's Junta Técnica foreign
secretary (Serrat y Bonastre, then Muguiro "secretario interino"), and the same
for justice (Cortés López against Irujo). Three statements in the batch are
Junta Técnica officials filed on the Republican-era items, because es.wikipedia
lists them as the office's holders and no date window can separate two parallel
governments:

* Q5867468 Serrat y Bonastre → Q32969013, 1936-10-05 – 1937-04-22
* Q11692722 Muguiro → Q32969013, 1937-04-22 – 1938-01-31
* Q5939073 Cortés López → Q24279063, 1936-10-03 – 1938-01-30

Also worth a look: **Q29179 Franco → Q844587** (1938-01-31 – 1973-06-09). True —
he was Presidente del Gobierno for those 35 years — and Q844587 already carries
nine pre-1977 terms, but the roster row's name cell reads "Vinculación a la
jefatura del Estado" rather than a name, so the identity came from a wikilink
inside a note.

## Nothing was created, and that is the finding

Every office this run touched already has its item, including the two era items
for the Congress presidency that nobody had noticed (Q43118787, Q43138757) and
all **nineteen** autonomous-community president items. One office genuinely has
no item — the **President of the Asamblea Nacional Consultiva** (the corporate
chamber of 1927–1929, on the Congress roster) — and it has exactly one attested
holder, José de Yanguas Messía, which is below `wd.create.guard`'s floor of two.
Its row is recorded as `skip: no item exists for this era` rather than filed
under the nearest item that exists, which is what the empty `date_targets`
window is for.

Deliberately *not* created, because creating them would contradict a measured
convention rather than fill a gap:

* **Presidente del Estamento de Próceres** (1834–1836, 4 holders on the Senate
  roster). Q1335465 declares inception 1834 and carries 21 terms from
  1834–1876, so the community already treats the Estamento as the Senate.
* **Ministro de Trabajo** / **Ministro de Educación** as long-running items —
  both already exist twice over (above). This needs a merge or a rank decision,
  not a third item.

## Byproducts

* **82 Cortes de Cádiz presidents (1810–1814) with no Wikidata item** —
  `data/spain/roster_audit.md`, the `no identity` column of the Congress
  section. The en.wikipedia list names them all with dates and constituencies;
  they are the single largest people-creation list this workbench has produced.
* **100 Presidentes del Consejo de Ministros** in `Prime_ministers_of_Spain`
  with no roster to date them. Their item (Q16020745, 79 holders / 142 dated
  terms) is well populated, so the gap is per-person, not structural.
* **Mayors**: 441 humans in `Mayors_of_places_in_Spain`, one of whom holds
  Q5663900. Per-municipality mayor items exist for the large cities (Barcelona
  92 holders, Reus 131, Terrassa 90); the spec's `wikidata_id` is pointing at a
  generic class instead.
* **`Deputy_Prime_Ministers_of_Spain` does not exist as an en.wikipedia
  category** — 0 members at depth 0, 1 and 4 — while Q3113035 has 15 holders.

## `wd_categories.yml` proposals

* `Presidents_of_the_autonomous_communities_of_Spain` carries a `position:`
  block with **no `wikidata_id`**, and it cannot have one: it is nineteen
  offices. Split it into the 19 per-community specs, resolutions in
  `scripts/es_offices.py:COMMUNITIES` (Q2748453 Andalucía, Q3133842 Aragón,
  Q3320056 Asturias, Q13710953 Baleares, Q967418 Canarias, Q47358 Cantabria,
  Q3272746 Castilla-La Mancha, Q4892213 Castilla y León, Q16933549 Cataluña,
  Q6745827 Ceuta, Q15971570 Comunitat Valenciana, Q3049413 Extremadura,
  Q3409188 Galicia, Q3049394 La Rioja, Q3133837 Madrid, Q30727487 Melilla,
  Q5199072 Murcia, Q3753803 Navarra, Q1124265 País Vasco).
* `Presidents_of_the_Congress_of_Deputies_(Spain)` should not be one
  `wikidata_id`: the office has four era items. Either point it at Q17014422 and
  accept that 1876–1923 holders are on Q45213921, or split by era.
* `Prime_ministers_of_Spain` → the category is 1834-onwards while Q844587 is the
  1938-onwards office. Add a second spec for Q16020745.
* `Mayors_of_places_in_Spain` → Q5663900 is the *class* "alcalde", not a
  position anyone holds; 1 of 441 members holds it. Drop the `position:` block
  or split per municipality.
* `Deputy_Prime_Ministers_of_Spain` → the category is empty; drop it or find the
  real name.
* `Judiciary_of_Spain` (33 humans) resolves to two real items —
  Q29934477 president of the Supreme Court (51 holders) and Q73179241 magistrate
  of the Supreme Court (84) — and could be split accordingly.

## What this run added to the tooling

* **`Office.date_targets`** — (from, to, item) windows, so one roster can span a
  succession of renamed items. An empty item means "no item exists for this
  era", and the row becomes a creation byproduct instead of a wrong statement.
* **`already_under_sibling` + the `duplicate_office_item` rule** — one office
  with several items is normal in Spain, and 44 rows were already on record
  under a sibling item. Before the rule, 21 of them were being *added* to the
  other item and, because the spell sits inside the sibling's span, the interim
  rule was attaching a `P2868` to them as well.
* **`section_targets` now matches the row's `office` cell**, not just its
  section heading — which is how one national table of nineteen autonomous
  communities becomes nineteen targets.
* **A table with no date column is not a roster** (`office_rows`): es.wikipedia
  heads each era with an "Espectro político" colour key, and those were
  contributing an unidentifiable row per era.
* Parser work in `wd/roster.py`, all of it generic and all of it re-verified
  against Ecuador, Belarus and Czechia (`scripts/diff_verdicts.py`: no semantic
  change in any of the three):
  * Spanish abbreviated months (`jul.`, `sept.`) and English month names, plus
    the month-first date form ("September 24, 1810") and the dot that can follow
    either the day *or* the month.
  * `Duración` is a tenure length, not a period — under the `period` role it
    shadowed the start and end cells beside it and **every date on four pages
    was lost**.
  * Hidden `{{dts}}` sort keys (`<span style="display:none">01812-06-12 </span>`)
    are dropped — *and their tail text kept*, since lxml's `remove()` takes the
    visible date with it.
  * `<hr>` divides a cell like `<br>`: the Senate list stacks a president's four
    sessions that way, and read as one line the four dates concatenate into a
    year.
  * A cell colspanning start *and* end is a range, not a start repeated as its
    own end.
  * "(fallecido en el cargo)" is not "en el cargo" — four chief justices died at
    their desks and every one was being recorded as incumbent.
  * English column vocabulary, so an en.wikipedia list parses at all.
  * A `td` header row is a header when it names two known columns; a full-width
    `td` is a section when it reads like a label rather than a note.
  * `Cargo suprimido entre 1814 y 1820` and friends are vacancies, not people.

## Follow-up: what the backtest says (2026-08-07)

The run was re-measured with `wd/backtest.py`, which scores each office against
the rows it skipped as already-held. Spain's decisions did not change — the diff
against `regression/spain/` is empty — but three things are now visible that were
not:

| office | on record | target agreement | date conflicts | unrecorded spells |
|---|---|---|---|---|
| Prime Minister | 22 | 100% | 2 | 1 |
| President of the Congress | 183 | 90% | 7 | 42 |
| President of the Senate | 110 | 100% | 4 | 9 |
| President of the Supreme Court | 49 | 100% | 4 | 0 |
| Foreign Affairs | 187 | 95% | 11 | 44 |
| Justice | 224 | 93% | 12 | 33 |
| President of an autonomous community | 125 | 100% | 10 | 2 |

* **The era routing is what earns the Congress presidency its 90%.** Deleting
  `date_targets` from that office drops it to **58%**, and the cohort then derives
  Q45213921 on its own and suppresses 87 rows that would otherwise have been
  added to the wrong item. That is the near-miss of this campaign, reproduced as
  an automatic check.
* **131 roster spells are recorded nowhere**, though the person holds the item for
  a different spell — dropped today by the person-level `already holds` test, not
  decided. Alejandro Groizard's two Senate presidencies are the shape of it.
  Promoting them to proposals is a deliberate next step, not a side effect.
* **The acting qualifier has next to no precedent.** 47 spells the Congress roster
  marks acting are recorded without `P2868`, and the precedent census finds **2
  acting-qualified statements across the 88 target items of all four campaigns** —
  both Spanish (Q844587 and Q13710953, one each). The three acting statements in
  this batch, and the 17 in the three earlier campaigns' batches (Ecuador 12,
  Czechia 4, Belarus 1), follow a convention the measured items do not use. This
  needs a ruling; nothing was changed.

## Status

- [x] survey: 13 specs, 13,284 target items / 50,523 holder statements, per-spec
  gap join, per-portfolio item succession measured, roster inventory (2026-08-06)
- [x] engine: `date_targets`, `already_under_sibling`, office-cell section
  routing, date-column guard; ten parser fixes in `wd/roster.py`
- [x] Ecuador, Belarus and Czechia re-run and diffed — no semantic change
- [x] run: 7 offices, 1,044 rows → 93 records / 111 statements,
  `data/spain/edit_plan.qs`; baseline in `regression/spain/`
- [x] backtest added and read: target agreement 90–100%, 50 date conflicts,
  131 unrecorded spells, 2 acting-qualified statements on 88 targets (2026-08-07)
- [ ] human review → run `data/spain/edit_plan.qs` (110 statements on 111 lines)
- [ ] rule on `P2868`: no target item in any campaign uses it
- [ ] rule on the 3 Junta Técnica statements and on Franco → Q844587
- [ ] rule on the 20 `interim_concurrent_office` rows (P2868 or plain?)
- [ ] labour and education: two competing items each — merge, or pick one
- [ ] `wd_categories.yml`: the 19-way autonomy split, the Congress era items, the
  second prime-minister spec, the mayor and deputy-PM specs
- [ ] byproducts: 82 Cortes de Cádiz presidents; 100 undated Consejo de
  Ministros premiers
- [ ] the four portrait-grid ministry pages (Fomento, Hacienda, Economía,
  Interior) need a different source; Defensa needs per-row office routing
