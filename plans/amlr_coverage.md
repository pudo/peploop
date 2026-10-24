---
description: The tool expansions that bring EU AMLR-scope PEPs (from July 2027) into Wikidata across pepcorp, peptree and peploop — the shared ≥50k unit set, local heads, municipal enterprises, party leadership, IO and EU offices, the national function lists as input, family details — each sized by a measurement, with a build order.
date: 2026-10-23
tags: [amlr, pepcorp, peptree, peploop, subnational, municipal, parties, family, scope]
---

# AMLR scope: what to add to the three lanes

The AMLR (Reg. 2024/1624, Art. 2(1)(34)–(35)) applies from 2027-07-10. Beyond
4AMLD it adds:
- heads of local authorities, groupings of municipalities and metro regions
  with ≥50k inhabitants (viii);
- party governing bodies, including regional and local ones for ≥50k
  constituencies (iii);
- boards and management of medium or large enterprises controlled by regional
  or local authorities (vii);
- siblings of tier (i).

Each section below names an expansion, the measurement that sizes it, and the
changes by file. Scripts and outputs are in the session scratchpad
(`units/`, `eupub/`, `conventions/`, `family/`); the numbers are from QLever's
dump as of 2026-10-23.

User calls so far:
- pepcorp takes municipal and inter-municipal SOEs, parties, IOs and EU bodies,
  and the function list as input; the work spans all three lanes.
- Size proxy for regional and local enterprises: controlling unit ≥50k and the
  body has its own article.

## 0. Shared: the AMLR unit set

**Finding.** A generic `P279* Q56061` walk over items with `P1082` ≥ 50,000
returns 6,067 "units" in the EU-27. Most are not governed: French cantons (320)
and arrondissements (289), German Bundestag constituencies (298), Spanish
judicial districts (227), Czech electoral units, hundreds of Catholic dioceses,
Swedish parishes. The type tree is no guide here, as everywhere.

Rooted at municipality (`Q15284`), the governed set is **1,212 municipalities
≥50k** (fr 134, de 197, es 152, it 139, nl 92, pl 85, gr 74, pt 59, se 52,
ro 41, dk 39, be 30, fi 21, bg 20, hu 19, cz 18, at 9, sk 9, hr 8, cy 4, lt 4,
si 4, ie 1, lu 1). This misses ee, lv and the Irish councils, whose classes sit
outside `Q15284`. Groupings come to another **954**: 293 German Landkreise,
271 French EPCI à fiscalité propre, 235 Polish powiats, 140 Spanish comarcas
(mostly not governed), 12 Italian città metropolitane, 3 Irish councils.

**Change.**
- A per-country `units:` block in data, listing for each level (municipal,
  grouping, metro) the classes whose instances are governed units. This is a
  short list per country, measured once, like pepcorp's `forms`.
- One reader, `amlr_units(cc) -> {qid: (level, population)}`: best-rank
  `P1082` ≥ `AMLR_POPULATION` (50,000; a member state's lower notified
  threshold overrides it in the same block), not `P576`, not former, run over
  `country.current_qids`.
- It lives in `peploop/amlr.py`, which all three lanes read. The `units:`
  block goes into `peploop/amlr/<cc>.yml` (§6a), the one per-country file the
  lanes share; pepcorp's spec and the census then refer to levels by name.
- `country.current_qids` is pepcorp's today; the reader may need it moved
  somewhere shared, or a copy of its rule.

## 1. peptree + peploop: heads of ≥50k units (viii)

**Finding.** For the 1,212 municipalities and 954 groupings:

| | municipalities | groupings |
|---|---|---|
| head office linked by `P1313` | 606 (50 %) | 38 |
| any office scoped `P1001` to the unit | 790 | 605 (mostly council seats) |
| current head on the unit (`P6`, no end) | 838 (69 %) | 379 |
| current `P6` head also holds the `P1313` office by `P39` | 461 of 525 pairs (88 %) | |

So where the office exists, peploop has done its job; **the gap is offices that
do not exist** and units that name no head.
- Countries nearly complete: fr, es, nl, ro, be, se.
- Countries with heads but no offices: de (185 heads, 16 offices), dk (39 / 0),
  bg (20 / 0), cz (17 / 1), hu (18 / 2), gr (18 / 4), at (9 / 2), pl (34 / 7).
- Italy has offices (110) but few heads (37).
- Groupings are almost bare: Landrat (de), président d'EPCI (fr) and starosta
  (pl) offices exist for 2 + 2 + 0 units, while 242 + 128 + 1 units name a
  head.

The ceiling is about 2,000 heads (Spanish comarcas mostly ungoverned), of whom
~1,200 are named on the units today.

**Changes.**
- **peptree (the back-link, §4 Lane A, scoped to the AMLR set).**
  - A unit with exactly one head office scoped to it by `P1001` and no
    `P1313` gets the back-link.
  - Offices of ≥50k units missing `P17`/`P279` get them under the jurisdiction
    and era rules. peptree creates nothing; a unit with no office goes to
    peploop's mint queue.
- **peploop `mint_units`, made EU-capable.**
  1. A census entry `per: units` may name a level of the AMLR set
     (`of: amlr:municipal`) instead of one class, so a country's ≥50k units
     are the candidates whatever their classes.
  2. The attested holder comes first from the unit's own current `P6`, a
     statement on the unit and so the unit's own evidence, read with its
     reference. Only where there is none does it come from the infobox.
  3. `HEAD_LINE` (English titles only) becomes a per-language table of head
     titles (Bürgermeister/Oberbürgermeister, Landrat, maire, président,
     sindaco, alcalde, burmistrz/prezydent miasta, starosta, borgmester,
     polgármester, primar, starosta, presidente da câmara …), or the infobox
     line is read by the model that drafts the office anyway.
  4. EU census files gain the entries: `municipal_head` and, where groupings
     are governed, `grouping_head`. The archetype is `mayor`, with a new
     `grouping_head` archetype if the measured parents differ (Landrat
     `Q875765`-style items).
- **Current holders.** Once an office exists, the `P6` head and the unit
  article's head are seeded into peploop's person queue, so `P39` and the
  details follow the normal path.

Order: de, dk, pl, gr, it, cz, hu, bg, at, then the grouping levels de, fr, pl.

## 2. pepcorp: municipal enterprises (vii, local)

**Finding.** pepcorp's Wikidata lanes reach few municipal enterprises.
- **Linked**: 5,031 bodies link to a ≥50k unit by `P127`/`P749` (≤2 hops),
  and 2,796 of them have an article. **Only 588 are organisations**: de 281,
  cz 117 (many schools), se 43, fi 37, it 18, nl 6. The rest are what a city
  owns: stations, stadiums, paintings, buildings. A municipality as owner is
  property, not control, far more often than a state is.
- **Typed**: `Q1780371` on a body located in a ≥50k unit: 26 in the EU.
- **Sector in unit**: an organisation located (`P131`/`P159`) in a ≥50k unit,
  typed with a municipal-sector class (transport company, energy company,
  public utility, municipal company, housing association, SEM/SPL,
  intercommunale, public enterprise), with an article. This adds 757: de 435
  (370 transport companies), pl 86, es 47, it 36, at 25, nl 25, be 19, cz 18.
- **Seats**: about 130 of these ~1,300 bodies carry any seat statement today.
  Whatever the tier yields comes from the articles.
- Wikidata links no category to municipal company, so the category lane cannot
  find these bodies by topic.

The candidate pool is about 1,300 bodies, two-thirds of them German. That is
small beside §1. The binding constraint is the people: boards of a Stadtwerk
are rarely linked people with items. The heads (Geschäftsführer, directeur
général) and chairs, often the mayor ex officio and already a PEP, are the
likely yield. Expect low hundreds of new seats EU-wide, to be confirmed on a
pilot.

**Changes.**
- `actors.py`: `amlr_units(cc)` adds actors of kind `municipal`, and chains to
  them resolve to level `municipal`. The type exclusion (`Q56061` in
  `NOT_GOVERNMENT`) stays for the type walk; these units come in by name.
- `load.py`:
  - Open the `Q1780371` typed lane.
  - A new lane `sector`: organisations located in an AMLR unit whose `P31` is
    one of the spec's `municipal_classes` (global defaults: transport company,
    energy company, public utility, municipal company, housing association;
    per country: SEM/SPL, intercommunale, Kommunalunternehmen, azienda
    speciale, empresa municipal, allmännyttigt bostadsbolag …).
  - A located body is only a candidate: decide must find the municipal
    control quote, as for any lane.
- `country.py`: new spec keys:
  - `municipal_classes`;
  - `categories` (Wikipedia category titles naming municipal enterprises,
    walked by the existing `wikipedia.walk_category`; for example
    de:Kategorie:Kommunales Unternehmen);
  - `holdings` entries with `level: municipal` (city Beteiligungsberichte,
    starting with the largest cities).
- `rules.gate`: `municipal` passes when the controlling unit (the chain's end,
  or the unit the decide answer names, resolved to an AMLR unit) is ≥50k and
  the body has an article. The marker is `Q1780371`. The correction rule
  (`rules.correction`) stops proposing removals where the municipal tier is
  written.
- `countries/*.yml`: add `municipal` to `tiers` country by country, de first,
  then pl, es, it, at, nl, be, cz.
- Decide prompt: an inter-municipal owner (Zweckverband, intercommunale,
  EPCI) is municipal control; several municipalities jointly holding a
  majority count as control, the AMLR's "groupings of municipalities".

Pilot: de, the 100 largest-unit candidates, to measure seats per body and
person-item hits before the rest.

## 3. pepcorp: regional tier, size proxy and holdings (vii, regional)

The regional tier is written today with no size check. Under the user's proxy a
first-level subdivision always clears 50k, so the rule changes nothing at the
regional tier except requiring the body's own article, which load already
requires (no article: dropped). What the regional tier lacks is **input**:
- Länder holdings lists (the de spec says "not yet"), and the regional
  registers of fr régions, it regioni, es comunidades and pl województwa.
- Spec `holdings` entries with `level: regional` and their source.

## 4. Party governing bodies (iii)

**Finding (convention).** Of 251 EU parties with ≥5 current seat-holders:
- **212 carry `P488` chair on the party item (84 %)** and 42 carry `P3975`
  secretary-general.
- 49 have a dedicated leader position item with holders (23 of them Spanish).
- 104 use a generic `P39` (party leader, chair) qualified with the party.
- Board, executive and supervisory statements (`P3320`, `P5052`) are
  essentially unused.

Regional branches:
- German Landesverbände exist as items (194, 152 typed `Q18744396`) and 106
  carry `P488`.
- Spain is mixed: 128 branches, 65 using statements, 58 positions.
- French fédérations, Italian regional secretariats and Polish structures are
  essentially not modelled.

**So the convention is statements on the party: pepcorp's lane.** peploop
does not mint party-leader offices beyond those it already has; Spain's
positions are kept and filled as they are.

**Changes (pepcorp).**
- **Load lane `party`**: parties with current seat-holders. These are parties
  that are `P102` of a human holding a current `P39` that is
  `P279*` legislator (`Q4175034`) or a head office of a governed unit,
  national, regional or ≥50k local. Their branches come in by `P749`/`P361`
  to such a party.
- **Decide**: a new kind `party` (and `party branch`), with no control
  question. Seats are the party's executive organs, translated by function:
  - chair (`P488`), co-chairs (`P488` ×2);
  - deputy chairs (`P3320` + `Q1127270`);
  - secretary-general (`P3975`, already used on 42);
  - treasurer (`P3320` + treasurer role);
  - members of the executive committee or presidium (`P3320` +
    `Q141755781`, or a party-board role item if the tally shows one in use).
  - A congress, a council of delegates or a parliamentary group is not a
    governing body.
- **Gate**: a party admits on its seat-holders, not on control, so `rules.gate`
  takes a kind-specific branch. Marker: none.
- **Spec**: `parties: [extra party QIDs]` for parties the lane misses, and
  `party_branch_classes` per country (de `Q18744396`).
- **Measure first** (rule of the repo): which role items party-board members
  carry today, before the seat table is fixed.

## 5. International organisations and EU bodies (user, 2026-10-24: in scope)

**Finding (convention).** Coverage is thin either way: 42 of 88 EU bodies and
71 of 122 IOs seated in the EU have no leadership data at all. Counting people,
**position items dominate** (EU: 167 people via positions against ~100 via
statements; IOs: 553 against ~150): President of the Commission, President of
the ECB, DG of UNESCO, DG of the IAEA, Secretary General of OPEC. Statements on
the body (`P488`, `P1037`) usually hold only the current head, and board
membership is absent.

**So the top offices are peploop's** (positions + `P39`), and pepcorp writes
only boards where no position convention exists.
- **peploop**: a census for the Union and for EU-seated IOs, a `cc: eu` scope.
  It lists each EU body's head and deputies (from C/2023/611) and each IO's
  head, deputies and board, with the existing archetypes (`agency_head`,
  `state_body_member`) and IO jurisdiction. The person lane seeds from the
  bodies' articles.
- **pepcorp**: an `international` spec (`countries/eu.yml`) with holdings from
  C/2023/611 and IOs `P159` in the EU. The kind `international`, no control
  gate, writes only the supervisory and management boards (EIB Board of
  Directors, ESM Board of Governors, agency management boards) as `P5052`,
  never the head where an office exists. `NOT_GOVERNMENT`'s IGO exclusion
  stays: these bodies are holdings, not state actors.

## 6. The national function lists as input (Art. 43, C/2023/724)

**Finding.** The curated sheet (2,759 rows, no QID column) splits as:
- 1,584 position rows: ~900 national and local offices, 454 IO offices, 220
  party offices;
- **907 named-body rows (638 distinct bodies)**: 272 enterprises, 336
  agencies or institutions, 30 central banks;
- 209 body-class rows;
- 59 unusable rows.

Named bodies are concentrated in mt 110, ro 109, dk 98, lt 90, pl 78, ee 37,
sk 37 and cz 25, exactly the thin countries whose pepcorp specs rest on
holdings from knowledge. A name search resolves 64 % of a 50-body sample
correctly, and only ~54 % on exact label + country without review.

**Changes.**
- **pepcorp**: each named body becomes a spec `holdings` entry with
  `listed: true` and `source` the OJ notice, resolved by a model call
  (name + local name + country → QID, checked against the item's country and
  type), never by bare label. A `listed` body passes the gate as in PEP scope
  by the member state's own list. That admits its seats. It gives no owner
  link, which still needs a quote or an official holdings list.
- **pepcorp**: body-class rows ("members of supervisory boards of state firms",
  "public institutes", "state agencies") are read once per country into its
  spec as confirmation of `forms` and tiers, not as a new mechanism.
- **peptree/peploop**: the concrete position rows are a per-country benchmark
  for the sweep report ("listed functions: N, office found: M"). They are
  matched with peploop's office matcher, not by text search.
- The AMLR single list (expected around July 2027) re-enters the same path.

## 6a. The function list as a living asset (user, 2026-10-24)

The curated sheet becomes a repo asset, one YAML per country under
`peploop/amlr/<cc>.yml` (plus `eu.yml` for Union and IO functions). It holds:
- the original rows, verbatim with their sheet row and the OJ source;
- the AMLR category of each row;
- a **growing expansion** of each row into concrete Wikidata items: positions,
  bodies, or a rule over units ("mayors of municipalities >50k" → the
  municipal level of the unit set × head office).

The same file carries the country's `units:` (§0), since the units are what
expand the generic rows. Every lane reads what concerns it:
- peptree and peploop: positions and unit levels;
- pepcorp: named bodies and body classes.

A coverage report reads the file back per country: rows, rows expanded, items
found, holders known.

## Workstreams (coordinated, sequential subagents)

1. `peploop/amlr.py` and the per-country files: format, `units:` for EU-27,
   the original rows imported (§0, §6a).
2. Expansion of rows into items, and the coverage report (§6, §6a).
3. Heads of ≥50k units: peptree back-links, `mint_units` EU-capable (§1).
4. pepcorp listed lane, from the asset's named bodies (§6).
5. pepcorp parties (§4).
6. pepcorp municipal tier (§2, §3).
7. IOs and EU bodies: peploop `eu` census, pepcorp boards (§5).

Each stops at a dry run: nothing goes to Wikidata without the user. A
workstream that needs an architectural expansion beyond its section stops and
reports instead.

## 7. peploop: family of tier (i) — skipped for now (user, 2026-10-24)

**Finding (partial: 15 of 27 states, open tier-(i) `P39`s).** Of 1,903 holders
(inflated by stale open terms: cy 117, of whom 12 started since 2018), 11 %
carry any family statement:

| sibling `P3373` | spouse `P26` | child `P40` | father `P22` | mother `P25` |
|---|---|---|---|---|
| 2.6 % | 4.3 % | 3.4 % | 6.0 % | 2.0 % |

Where these statements exist:
- every value is an item, almost all humans;
- the statements are symmetric (`P3373` 67/67, `P26` 81/81, parent and child
  236/237);
- they are mostly unreferenced (`P3373` 27 %, `P40` 18 %).

Coverage is best in ie, fr and ee and near zero in hu, it and cy. How many
relatives the holders' articles link to people with items is **not yet
measured**; that is the lane's ceiling, as no people are created.

**Changes (peploop).**
- A `family` detail beside `P569 P570 P21 P27 P19`, for current tier-(i)
  holders only (heads of state and government, ministers, deputy and assistant
  ministers, state secretaries). Siblings are required only for this tier; for
  the other relations it may run on every holder later.
- Evidence: a relative the holder's article names *and links* to a human item,
  with the relation stated in the same sentence or infobox field. No people
  are created.
- Each statement is written with the article as reference, and the inverse on
  the relative (`P3373`↔`P3373`, `P26`↔`P26`, `P40`↔`P22`/`P25` by the
  parent's sex), as Wikidata's own symmetry shows.
- Rules with checks:
  - no relative who is the holder themself;
  - no `P22`/`P25` whose birth is after the holder's;
  - no spouse whose life does not overlap;
  - an existing statement is merged, never duplicated.

First step: run the prepared 30-article sample (de, fr, it, pl, es, se), re-based
on holders who started in 2018 or later, to size the lane before building it.

## 8. Already covered, checked only

Courts of auditors, central bank boards (pepcorp's statutory lane plus the
`central_bank_governor` and `state_body_member` archetypes), ambassadors and
senior military are national tiers the sweeps already take. The function list's
position rows (§6) are the check on them.
