# Task: Ecuador — category members → real P39 statements

Country run over every Ecuador-related spec in `wd_categories.yml` (17
categories, 11 of them carrying a synthetic `position:` block). Ecuador is a
good end-to-end pilot for the retirement metric in
`tasks/category_positions.md`: the whole country fits in one campaign, its
position items mostly exist, and es.wikipedia carries dated per-office
rosters that make verification cheap.

Survey below is measured (2026-08-05), not estimated.

## The category inventory

PETScan member counts (items with a Wikidata link; `people` = after the
`P31=Q5` filter, which dropped 37 of 764 hits). "d0/d1/d4" = subcategory
depth; the yml runs these at depth 0 in the spec but the crawler's own
depth-4 sweeps reach them anyway.

| spec (lang:category) | position block | d0 | d1 | d4 |
|---|---|---:|---:|---:|
| en:Presidents_of_Ecuador | President of Ecuador | 83 | 86 | 95 |
| es:Presidentes_de_Ecuador | President of Ecuador | 84 | 98 | **363** |
| en:Vice_presidents_of_Ecuador | Vice President | 39 | 39 | 39 |
| es:Vicepresidentes_de_Ecuador | Vice President | 51 | 51 | 51 |
| en:Members_of_the_National_Assembly_(Ecuador) | Member of the NA | 104 | 156 | 156 |
| es:Asambleístas_y_diputados_de_Ecuador | Member of the NA | 299 | 309 | 446 |
| en:Members_of_the_National_Congress_(Ecuador) | Member of the NC | 76 | 105 | 105 |
| en:Presidents_of_the_National_Assembly_(Ecuador) | President of the NA | 10 | 10 | 10 |
| en:Presidents_of_the_National_Congress_(Ecuador) | President of the NC | 8 | 8 | 8 |
| es:Presidentes_del_Congreso_Nacional_de_Ecuador | President of the NC | 30 | 30 | 30 |
| en:Presidents_of_the_Senate_of_Ecuador | President of the Senate | 17 | 17 | 17 |
| en:Government_ministers_of_Ecuador | — | 64 | 139 | 139 |
| en:Women_government_ministers_of_Ecuador | — | 38 | 38 | 38 |
| es:Ministros_de_Ecuador | — | 51 | 258 | 264 |
| es:Ministras_de_Ecuador | — | 33 | 33 | 33 |
| en:Political_office-holders_in_Ecuador | — | 7 | 339 | 431 |
| es:Políticas_de_Ecuador | — | 156 | 166 | 166 |

**Universe (union at depth ≤1): 727 people.** 429 already hold at least one
P39 pointing at an Ecuador-scoped position, 46 hold P39s but none Ecuadorian,
**252 hold no P39 at all**. Every one of the 727 has an es or en article — so
article-level verification is always possible.

Depth discipline: `es:Presidentes_de_Ecuador` at depth ≥1 pulls in
`Hijos de Presidentes de Ecuador` (children!), `Gobernantes coloniales de
Quito` and per-president eponymous subcats — hence 363 at d4. Run the
president/VP categories at **depth 0 only**; the assembly and minister trees
are safe at depth 1 because their subcategories are *terms* and *portfolios*
(see below).

## The target inventory

79 position items carry P17/P1001 = Ecuador (929 P39 holder statements).
Shape of it:

* seats: **Q22230757** National Congress Deputy (288 holders, the 1979–2007
  and earlier Congress seat), **Q21295982** Member of the National Assembly
  (51, post-2009).
* national: Q732562 President (44), Q4261569 Vice President (19),
  Q6085548 President of the National Assembly (6, dual-typed as a list
  article).
* **a complete modern ministry block**: Q24293533 foreign affairs (59),
  Q19845330 finance (34), Q27921459 defence (19), then ~17 items in the
  Q1142896xx–Q1142901xx range (interior, agriculture, education, energy,
  environment, health, justice, labour, sport, tourism, transport, housing,
  telecoms, production, social inclusion, culture, government) with **1–4
  holders each**. The items exist; they are simply empty.
* municipal/provincial: Q6797798 Mayor of Quito (19), Q5663928 Guayaquil
  (11), Q63041550 Cuenca, six `Prefecto de <province>` items, and
  **Q110164227 "Alcalde" with 149 holders** — a generic mayor item with
  P17=Ecuador used as the catch-all for every Ecuadorian mayor. Out of scope
  here, flagged as a data-quality item below.
* ~25 inbound-ambassador items (`ambassador of X to Ecuador`) — those belong
  to `tasks/diplomatic.md`, not this campaign.

## Four lanes

### Lane A — the presidential line (94 members, 50 gaps) — convention-heavy

Not the easy win it looks like. Q732562 holds the 44 *constitutional*
presidents; the gap list is dominated by interim and de-facto rule:
"Acting President of Ecuador (1911)", jefes supremos, junta chairmen
(Q734584 Poveda = Supreme Council of Government), a president-elect
(Q24960275 Bonifaz, never inaugurated), and a handful of people whose only
Ecuadorian tie in the category is that they were *vice* president.

De-facto Wikidata practice is established and narrow: Q878497 (Fabián
Alarcón) carries `P39 Q732562` + **`P2868 = Q4676846` (acting)**. Adopt it —
skipping acting holders the way `tasks/positions.md` does would throw away
most of Ecuador's 19th/20th-century head-of-state history. Junta and
collegial bodies (Consejo Supremo de Gobierno, Junta Militar, Provisional
Government) are *not* the presidency: route to review, not into the batch.
Same treatment for the 51-member VP category (32 gaps).

Source: `Anexo:Presidentes del Ecuador` distinguishes titulares from
interinos and cites each.

### Lane B — ministers (272 members, 170 portfolio gaps) — the volume win

This is the bucket-narrowing case from `tasks/category_positions.md`, and
Ecuador makes it **mechanical**: both wikis subdivide the minister category
by portfolio, and each portfolio has a Wikidata item.

| portfolio subcategory | es | en | union | holders | gap | target |
|---|---:|---:|---:|---:|---:|---|
| Ministros del Interior | 48 | 7 | 48 | 3 | **46** | Q114260168 |
| Relaciones Exteriores | 47 | 20 | 48 | 59 | 18 | Q24293533 |
| Economía y Finanzas | 19 | 28 | 36 | 34 | 17 | Q19845330 |
| Educación | 16 | 3 | 16 | 1 | 16 | Q114289770 |
| Salud Pública | 14 | 8 | 16 | 2 | 15 | Q90885218 |
| Trabajo | 12 | 1 | 13 | 1 | 12 | Q114289910 |
| Industrias y Productividad | 12 | 0 | 12 | 1 | 11 | Q114289842 |
| Defensa | 20 | 6 | 21 | 19 | 10 | Q27921459 |
| Agricultura y Ganadería | 12 | 1 | 12 | 3 | 9 | Q114289753 |
| Inclusión Económica y Social | 10 | 0 | 10 | 3 | 9 | Q114289831 |
| Transporte y Obras Públicas | 9 | 0 | 9 | 2 | 8 | Q114289931 |
| Energía y Rec. Naturales | 7 | 3 | 8 | 3 | 8 | Q114289772 |
| Turismo | 8 | 2 | 8 | 1 | 7 | Q114289956 |
| Justicia | 3 | 5 | 5 | 1 | 4 | Q114289620 |
| Cultura y Patrimonio | 6 | 1 | 6 | 4 | 4 | Q100594801 |
| Ambiente | 4 | 3 | 4 | 1 | 3 | Q114289994 |
| Deporte | 2 | 2 | 3 | 2 | 2 | Q114290016 |
| Desarrollo Urbano y Vivienda | 2 | 0 | 2 | 2 | 2 | Q114290143 |

**170 unique people**, each with a named target — no per-person office
guessing needed, only per-person confirmation + dates.

Two renaming traps to settle before batching:
* **Gobierno vs Interior.** The es category `Ministros del Interior` spans
  the whole line back to the 19th-century *Ministerio de Gobierno*, but
  Wikidata has both Q114260168 (Interior) and Q114290115 (Government). The
  roster page is literally `Anexo:Ministros de Gobierno de Ecuador` (3336
  words). Pre-2010 holders almost certainly belong on Q114290115. Split by
  date, route the boundary years to review.
* **Industrias y Productividad** (es) vs Q114289842 "Minister of Production,
  Foreign Trade, Investment and Fisheries" — same trap, later merger.

The remaining ~100 minister-category members not in any portfolio
subcategory need per-person narrowing from the article (secretariats,
`Ministro de Bienestar Social`, pre-1979 portfolios with no item). Expect an
item-creation list, as in the Bahrain pass.

### Lane C — legislature seats (~300 gaps) — era split, then qualifiers

The `es:Asambleístas_y_diputados_de_Ecuador` spec is a **two-era category**
(the verification pass already flagged this): 299 members, of which 294 lack
Q21295982 (asambleísta, post-2009) and 85 lack Q22230757 (National Congress
deputy). Members must be routed by era, not by category:

* **post-2009 → Q21295982.** en category alone has 88 gaps at depth 0 (130 at
  depth 1). Term subcategories exist on both wikis
  (`Asambleístas de Ecuador 2009-2013 … 2025-2029`, `Members of the first…
  fifth National Assembly`) *and* per-term roster anexos with district and
  party columns. De-facto qualifier practice on Q21295982: P580 (39), P582
  (31), **P768 electoral district (20)**, **P2937 term (19)**, P2715 elected
  in (12). Term items exist for periods 1–3 (Q16621914, Q16629825,
  Q30911706); **periods 4 and 5 have only list-article items** (Q112285757,
  Q137370095) — either create term items or omit P2937 for those.
* **1979–2007 (and the pre-1979 unicameral Congress) → Q22230757.** 41 gaps
  from the en category, 85 from the es one.
* **pre-1979 bicameral era.** Bodies exist (Q56612905 Senate 1835–1970,
  Q51107050 Chamber of Representatives 1979–84, Q1680117 Congress) but there
  is **no seat item for senator or diputado of the old Chamber**. Creation
  candidates.

### Lane C2 — presiding officers of predecessor chambers (47 members, 0 covered)

`Presidents of the Senate of Ecuador` (17), `Presidents of the National
Congress` (8 en / 30 es), `Presidents of the Chamber of Deputies` (14, not
even in the yml) — **none of these has a position item.** The only hit,
Q5693719 "Presidente del Congreso Nacional del Ecuador", is a Wikimedia list
article (`Anexo:Presidentes de la Función Legislativa del Ecuador`), not an
office.

Decision needed: create three predecessor-presidency items, or treat
Q6085548 (President of the National Assembly) as the continuous
presiding-officer office. Q6085548's own P361/P2389 already reach back to
the Congress, Chamber and Senate, and its earliest holders (Olmedo!) long
predate the National Assembly — so Wikidata is *already* leaning continuous,
sloppily. **Recommendation: create the three items** (bodies exist to hang
P361 on, and eswiki keeps separate categories per chamber), then link
Q6085548 to them with P1365/P1366. Until that is decided, this lane's 47
members produce zero statements — so do it early; it is 47 people for three
item creations.

### Lane D — the residual catch-alls (deferred)

`en:Political_office-holders_in_Ecuador` (339 at d1) and
`es:Políticas_de_Ecuador` (166) are grab-bags whose subcategories are mayors,
councillors (`Concejalas`), governors, provincial prefects and
vice-mayors — municipal/provincial offices where `Q110164227 "Alcalde"`
(149 holders) already shows the community taking a shortcut. **131 people
with no Ecuadorian P39 are reachable only through these two categories.**
Defer: settle the generic-Alcalde question first (per-city items vs the
generic office + P642/P1001 qualifier), and note that provincial prefect
items exist for only 6 of 24 provinces. Municipal work also hits the
CLAUDE.md gotcha about P150 granularity.

Uncovered categories found in the tree that the yml never models —
candidates for new specs *and* for this campaign's later passes:
`Provincial_Prefects_of_Ecuador` (12/15), `Mayors_of_places_in_Ecuador`
(21/31), `Governors_of_Ecuador` (10 at d1),
`Members_of_the_Ecuadorian_Constituent_Assembly_(2007–2008)` (8),
`Presidents_of_the_Chamber_of_Deputies_of_Ecuador` (14).

## Method: roster-first, not person-first

The big change from previous campaigns. es.wikipedia has an `Anexo:` roster
per office — `Anexo:Ministros de Gobierno de Ecuador`, `…de Trabajo de
Ecuador`, `…de Salud de Ecuador`, `Anexo:Presidentes del Ecuador`,
`Anexo:Asambleístas del <n> período legislativo …` — and they are dated
wikitables with **per-row `<ref>` citations** (Registro Oficial decrees,
ministry memoirs, archived ministry pages) and a colour legend marking
`funcionario encargado` (acting). One fetch per office yields every holder,
exact start/end dates, the citation to use as S854, and the acting flag —
instead of N per-person article reads that each restate the same table.

So per office: parse the roster → match rows to the category members' QIDs →
propose. Person articles are then only needed for (a) roster rows whose name
doesn't match a member QID, (b) members absent from the roster, (c) any
conflict. That is the two-signal gate: **category membership + roster row**,
with the person's article as tie-breaker.

Refs: prefer the roster row's own citation URL (S854 + S813); fall back to
the roster page permalink; never the bare category.

## Scripts to build

1. `scripts/ec_campaign.py` — the survey that produced the tables above,
   generalised to one country code: yml specs → PETScan at per-spec depth →
   `P31=Q5` filter → existing-P39 join → per-target gap sets, output
   `data/ecuador/universe.json` + a review `.md`. Supersedes running
   `position_gap.py` once per position (12+ invocations, no shared member
   cache).
2. `scripts/roster_parse.py` — `Anexo:` wikitable → rows of
   `{name, wikilink, start, end, acting, ref_url, designante}`. Built on
   `wd/wikipedia.py`; Spanish date parsing ("10 de agosto de 1979") and the
   `{{leyenda}}` acting legend are the only real work. Reusable for every
   Latin American country.
3. `scripts/portfolio_map.py` — portfolio subcategory → ministry item, the
   Lane B mapping table, with the rename split (Gobierno/Interior,
   Industrias/Producción) expressed as date ranges rather than one QID.
4. Extend `scripts/render_edit_plan.py`: the verdict schema needs a
   `qualifiers` dict, because Ecuador needs **P2868 (acting)**, P768
   (electoral district), P2937 (term) and P2715 (elected in) — today only
   P580/P582 are emitted. One `.qs` per lane, additive-only.
5. `scripts/ec_missing_items.py` — the creation list: three chamber
   presidencies, old-Chamber/Senate seats, assembly terms 4–5, unmapped
   pre-1979 portfolios. Output a table for hand-creation, not an automated
   write.

## Sequencing

1. **Lane B pilot, 3 portfolios** (Trabajo 12, Turismo 8, Deporte 3 — small
   rosters, no rename trap): prove `roster_parse.py` + the qualifier
   extension end to end, ~20 statements. Audit the matcher output in full
   before trusting it, per CLAUDE.md.
2. **Lane B in full** — 18 portfolios, 170 candidates, in portfolio-sized
   batches. Gobierno/Interior last, after the date split is agreed.
3. **Lane C2 item creation** (3 items) → then its 47 members.
4. **Lane A** presidents + VPs with the acting convention (82 candidates).
5. **Lane C** legislature seats: era routing first (mechanical, by
   term/period subcategory and roster), then the qualifier-rich batches;
   biggest volume, most likely to need a second pass.
6. **Retirement report** for the 11 position-bearing Ecuador specs, and a
   `wikidata_id` proposal PR against `wd_categories.yml` (`Member of the
   National Congress` → Q22230757 closes one of the ambiguous rows; the
   `Asambleístas_y_diputados` spec should be **split in two** rather than
   given one id).
7. Lane D only after the generic-Alcalde convention question is answered.

## Open decisions (need a call before the affected lane runs)

* Acting/interim holders: adopt `P2868 = Q4676846` (recommended, matches the
  Alarcón precedent) or keep the "skip acting" rule from `tasks/positions.md`
  — with the consequence that Lane A shrinks to ~20 statements.
* Three predecessor presidencies as new items (recommended) vs. stretching
  Q6085548 across chambers.
* Gobierno→Interior cutover date, and whether pre-1979 minister holders go
  on the modern portfolio item at all.
* Assembly terms 4–5: create term items, or emit those P39s without P2937.
* Lane D: generic Q110164227 "Alcalde" + qualifier vs per-municipality items
  (blocks ~131 people).

## Side findings (not P39 work)

* **Generic office items used where a country item exists.** 12 people in the
  Lane B batch already carry a generic P39: Q83307 "minister" (6), Q3273722
  "health minister" (3, incl. Alfredo Palacio and Carina Vance), Q4018482
  "education minister", Q7614320 "finance minister", Q42178 "vice president",
  and Q42841 **"incumbent"** — which is not an office at all. The additive
  batch leaves these in place; replacing them with the Ecuadorian items is a
  surgical wikibase-cli pass.
* Q2322197 (José Francisco Cevallos, footballer and Minister of Sport
  2011–14) has en label "José Rodrigo Cevallos" and a description saying
  "born 1991" while P569 is 1971 — the item conflates him with his son.

* Q22984534 "Ministry of Public Health" is an *organisation* carrying
  P1001=Ecuador and showing up in the position census — check whether
  anything uses it as a P39 target.
* Q384769 "First Ladies and Gentlemen of Ecuador" (list article) is used as a
  P39 target by 11 people; Q23921870 "Governors of Guayas" (6) and
  Q5677156 "Barcelona Sporting Club presidents" (1) likewise. List articles
  as positions — a cleanup batch of its own.
* Q19845330's label is the bare "Minister of Finance" with no country in it —
  add the qualifier-free label fix ("… of Ecuador") when touching it.
* Q6085548 is dual-typed position + list article (already noted in
  `tasks/category_positions.md`).

## Status

- [x] survey of all 17 Ecuador specs: member counts at depth 0/1/4,
  727-person universe, 298 without any Ecuadorian P39 (2026-08-05)
- [x] target inventory: 79 Ecuador-scoped position items, incl. the empty
  modern ministry block; per-portfolio gap table (170 candidates)
- [x] convention research: acting = P2868/Q4676846 precedent, seat qualifier
  practice (P768/P2937/P2715), `Anexo:` roster pages as the source of record
- [x] roster tooling (2026-08-05): `wd/roster.py` (rendered-HTML wikitable →
  dated rows with acting flags, per-row citations, section headers),
  `wd/wikipedia.fetch_html`, and `render_edit_plan.py` gained `--campaign`,
  arbitrary qualifiers, and `source_prop` (S4656 for wiki permalinks, so a
  Wikipedia URL never lands in S854).
- [x] **Lane B run, all 20 portfolios** (2026-08-05, `scripts/ec_ministers.py`
  → `data/ecuador/{edit_plan.md,edit_plan.qs,ministers_audit.md}`): ~1,900
  roster rows → **94 people / 98 statements batched**, 87 rows already held
  the P39, and 328 rows held back by tier: 98 roster-only (identity solid via
  the roster's wikilink, but no category corroborates the office), 98 pre-1979
  (continuity judgment against items created for the modern ministries),
  78 Gobierno/Interior (`hold`), 27 acting, 20 category-only (the rosters
  start in 1979, so earlier category members land here), 6 pre-ministerial
  sections, 1 lifetime mismatch. ~1,100 rows name people with **no Wikidata
  item at all** — a byproduct list for item creation / OS PEP coverage.
  What the audit pass caught before shipping (all fixed):
  * `Anexo:Ministros del Interior` is a *redirect* to `…de Gobierno` — the two
    portfolios were parsing one page and double-proposing it.
  * matching table headings on "cartera" swept in **sibling ministries**
    ("Cartera de Minería", "Cartera de planificación económica"), which is
    what made 11 roster date-overlap warnings; now only the office's own
    table counts and 3 overlaps remain, all in pre-1979 held-back rows.
  * a single `Período` header colspanning two cells meant every end date was
    silently dropped on 4 rosters (Salud, Cultura, Obras, Industrias).
  * namesake gates on non-wikilink identities: a lifetime check (3 catches,
    e.g. Ángel Polibio Chaves 1855–1930 proposed as 1998 labour minister) and
    a political-occupation marker (2 catches: es.wiki's "Ernesto Albán" is a
    comedian, its "Carlos Pérez García" a Spanish footballer).
- [ ] human review of `data/ecuador/edit_plan.md` → apply the 98 statements
- [ ] rule on the held-back tiers (roster-only, pre-1979, Gobierno/Interior,
  acting) — each is a `--campaign ecuador` re-render away once decided
- [ ] Lane C2 items · Lane A · Lane C
- [ ] retirement report + `wd_categories.yml` PR (incl. splitting the
  `Asambleístas_y_diputados` spec)
