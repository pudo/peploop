---
description: peptree one level down. Score every country's governed subnational units (usually first-level, sometimes second) × {head of government, head of state, deputy, legislature member}, find the offices load cannot see, link units to their offices with P1313/P1906, and turn the empty cells into a mint queue. Measured over 210 sweep countries and 3,084 first-level units before any code.
date: 2026-10-05
tags: [peptree, subnational, governors, p150, p1313, matrix, minting, fatf]
---

# peptree: one level down

## Goal

FATF counts state and province governors as PEPs, and so does OpenSanctions
(`Q132050` governor → `role.pep`, `zavod/shed/wikidata/position.py`). peptree
scores only national offices today. The 7,739 subnational offices it keeps are
repaired but never scored (`gaps.matrix` skips every `kind` except national
and ambassador). This adds a second matrix. Its rows are a country's governed
units and its columns are four slots. Every cell ends in a state, and an empty
cell becomes a mint candidate.

The scheme was written as "P150 first-level units × {head, deputy,
legislature}". The data says that is the right shape with three corrections:
- the level has to be chosen per country;
- "head" is two slots;
- discovery has to start from the units, not the country.

Probes: `scratchpad/sub/{a..i}_*.py` (session scratch, read-only, cached in
`http_cache`). Phase 0 ports them into `peptree/subnational.py`.

## What the data says (2026-10-05)

### The units

- 210 sweep countries; 175 have current `P150` units; **3,084 first-level
  units**.
- What the units themselves carry:
  - `P36` capital 2,455
  - `P1313` head-of-government office **694**
  - `P6` head of government (a person) 630
  - `P194` legislature 431
  - `P35` head of state (a person) 48
  - `P1906` head-of-state office 33
- Per country, the share of units linking a head office (`P1313`/`P1906`):
  - ≥90%: **21** countries
  - partial: **30**
  - none: **124**
  - no units: 35

  The 124 "none" countries hold 2,085 units.
- **`P150` is not one grain.** The first level includes:
  - French communes (82, in gp/mq/yt), Polynesian and Caledonian communes
    (77), Macedonian municipalities (80) and Puerto Rican municipios (77);
  - islands (37), atolls (36), reef islands (40) and villages (23);
  - electoral units (39, across 12 countries);
  - Uganda's 135 districts and Azerbaijan's 59 districts.

  A first-level unit can therefore be a mayoralty, a constituency or nothing
  governed at all.
- **Sometimes the governed level is the second one.** Philippine regions link a
  head on 1 of 18; provinces (level 2) link one on **116 of 119**. Elsewhere
  the second level is municipal: Romania's 3,186 communes all link a mayor,
  Indonesia's 513 regencies link a *bupati*, Nigeria's 190 linked LGAs a
  chairman.
- **Unit *types* carry nothing.** 3 of 349 type items ("state of Nigeria", …)
  have a `P1313`. So the type can't serve as the grain test or the archetype.

### The offices units link to

- 637 linked offices. **628 are per-unit** (one unit each). 9 are shared, and
  they are generic classes:
  - `Q132050` governor on 64 units (af, am, az, bg, …)
  - `Q371909` prefect on 21 Ecuadorian provinces
  - mayor, chairperson, president

  **90 units** name a generic class in `P1313`, and 34 of them also have a
  per-unit head office that nothing links.
- Of the 628 per-unit offices:
  - 609 have `P1001` = their unit, 596 have a `P279`, 593 are held;
  - **only 378 have the country in `P17`**, which is what peptree's load needs
    to find them. Most of the rest are French overseas communes (`P17` France,
    out of scope), but **63 have no `P17` at all**.
- The `P279` a per-unit head uses:
  - bare `Q132050` 140;
  - a national class otherwise, for example `Q56284759` "governor of a Nigerian
    state" 36, `Q1540324` Russia 34, Brazil 25, Argentina 23, Angola 18,
    Mozambique 10, South Africa 9;
  - `Q2285706` 33 and chief minister 28.

  This matches `research/position_items.md` §10g. The archetype is a
  sibling convention, per country.

### Every office scoped to a unit

- **5,505 positions** have `P1001` = a first-level unit (out of 33,974 items with
  such a `P1001`). **648 lack the country in `P17`** and are invisible to load,
  103 of them unit heads.
- By a first-cut classifier (closure + label words):

  | slot | offices | note |
  |---|---|---|
  | head | 622 | well-formed: all have `P279`, 565 held |
  | head? | 676 | label says governor/prefect/chairman/commissioner; mixes real heads (Governor of Kamphaeng Phet, chairman of the Minsk Regional Executive Committee, Commissioner for the Mwanza Region) with agency heads (Head of the State Courier Service Department, Commissioner for Children's Rights) |
  | legislator | 800 | |
  | deputy | 194 | |
  | mayor | 209 | |
  | other | 2,967 | ru 1,291 (regional ministers), br 547, th 382 (provincial officers), my 212 (state honours) |

  **A label regex can't decide the head slot.** That needs the unit's link,
  the sibling convention, or a model.
- **The unit × slot matrix today, first level:**
  - a head office exists for **1,037 of 3,084 units (34%)**, and the unit links
    it for 606;
  - 431 units name a legislature and 374 have a member office;
  - 159 have a deputy.
- **Back-link repair is mechanical:** 168 units have exactly one head office and
  link none. ir 28, bg 27, pe 25, sv 13, pg 12, cn 9, sa 7, iq 6, ru 6, …
- **Head is two slots.** 51 units have two head offices, and nearly all are a
  head of state plus a head of government:
  - Governor vs Chief Minister of Tamil Nadu (in 27);
  - Sultan vs Menteri Besar (my 7);
  - Governor vs Chief Minister of Sindh (pk 4).

  Real duplicates are rare: "gouverneur de Jujuy" beside "Governor of Jujuy
  Province", and Udmurt's renamed head.

### Evidence channels, measured

- **`P6`/`P35` person on a unit with no linked office** (275 units, 339 people):
  - 106 hold an office scoped to that unit that the unit doesn't link (that's
    the back-link lane again);
  - 131 hold only other offices;
  - 117 have no `P39` at all, 42 of them Azerbaijani district heads.

  This is a mint signal: a named current head with no office.
- **A class `P39` qualified by a unit** (6,079 statements): 5,638 are `P768`
  constituencies. The rest are almost all national legislators delegated by
  province (Argentine senators, 1,140), which is legitimate modelling. Head
  evidence here is small: Thailand's "Province Governor" class with a unit
  qualifier (26 statements, 12 provinces), and governor + unit in ar and ve
  (about 10 each).
- **Claimless items.** Ghana's regional ministers exist for 6 of 16 regions.
  Two carry only a Google KG id (`Q96372445` Ashanti, `Q96379890` Greater
  Accra), and at most one person holds any of them. No SPARQL lane can find
  them; only a label search can.
- **enwiki rosters are thin where the gaps are:**
  - "Regional ministers of Ghana": 19 articles, 13 of the people with any `P39`;
  - Dominican Republic governors: 10;
  - Honduras: 10;
  - Ethiopia's region governors: 3;
  - Laos, Guatemala: subcategories only.

  The peploop mint bar (≥2 distinct holders, ≥1 current) will rarely be met
  from Wikidata alone.
- **Others are minting this layer right now.**
  - Thailand: per-province governor, vice governor, PAO president and
    provincial officers, all with 0 holders (Gabut555, 2026-04).
  - Russia: regional ministers (Oravrattas, 2025-10).
  - Bulgaria: oblast governors (Dimitar999, 2026-02).

  A mint needs a duplicate search made at mint time, and an unheld office is a
  `P39` job for peploop, not a gap for peptree.

### peptree's own load

- **The load misses offices scoped only to a province.** Load finds offices by
  `P17`/`P1001` = the country, or orphans held by citizens. So an office scoped
  only to its province is never loaded (the 648 above).
- **Of the 7,739 kept subnational offices, 5,697 are Brazil's.** The rest point
  their `P1001` at:
  - level 1: 529
  - level 2: 410
  - another place: 239
  - nothing: 348
  - no config: 518
- **The `kind` is noisy.** Hong Kong's offices sit under cn, and Argentina's
  "Deputy Chief of the Army General Staff" is classed subnational.

### The gap countries

These have governed first-level units and no head office at all. They are the
real mint queue (units in brackets):
- dz Algeria (58), vn Vietnam (34), do Dominican Republic (32), tn Tunisia (24),
  gt Guatemala (22), mn Mongolia (22), td Chad (21);
- ml Mali (20), bt Bhutan (20), hn Honduras (18), la Laos (17),
  ni Nicaragua (17), gh Ghana (16), et Ethiopia (14);
- sn Senegal (14), bf Burkina Faso (13), jo Jordan (12), al Albania (12),
  kp North Korea (12), bj Benin (12), plus the Libyan, Cape Verdean and
  Liberian rows.

At roughly 20 units each, that is **about 40 countries and 700–900 head
offices**. Island states and municipal first levels (bs, mh, kn, tt, nr, sc,
mk, xk, me, pr) are *n/a*, not gaps.

## Design

### 1. Choose the level, per country, from data

A unit counts as **governed** when any of these hold:
- it has `P1313`/`P1906`/`P6`/`P35`/`P194`;
- an office's `P1001` names it and that office lands in a head slot.

Per country, take the levels 1 and 2 (`country.config` already has `l1`/`l2`):
1. **Choose the level:** the highest level where at least half the units are
   governed. That picks level 2 for the Philippines and level 1 for Nigeria.
2. **Exclude municipal levels** (type closure reaches municipality/commune,
   `Q15284`/`Q484170`) and non-levels (island, atoll, village, electoral unit;
   `country.NOT_A_LEVEL` plus these). Municipal offices stay out of this
   workstream, as `recipes/institutions.md` already says (`P36`, not `P150`).
3. **When no level is governed but level 1 is an admin type**, the country goes
   to a one-call census: "do the first-level units of X have an executive head,
   and what is the office called?". The answer has to quote an article. The
   answer either marks the level governed (and gives the archetype's label) or
   marks it *n/a*.

The choice is recorded per country (`ptree_level`), so the report can say why.

### 2. Discovery from the units

There are three new lanes, all writing into `ptree_item` with `kind =
subnational`:
- **`unit_scope`:** every position with `P1001` = a chosen-level unit, using the
  same closure and filter as today. This fixes the 648 offices load can't see.
- **`unit_link`:** the targets of the units' `P1313`/`P1906`, minus generic
  classes (which already drop as `generic_class`).
- **`unit_search`:** for each empty head cell, a label search for the
  archetype's label in the unit's name (`wbsearchentities` plus full-text, in
  the country's languages). This finds claimless items (Ghana). A hit goes to
  the model, never straight to a cell.

### 3. Slots

| slot | how an office earns it |
|---|---|
| `head_gov` | the unit's `P1313`; else the country's sibling convention (the modal `P279` of linked heads); else a model pick among the unit's `head?` offices |
| `head_state` | the unit's `P1906`, or the second of a pair where the country's linked heads form pairs (in, my, pk) |
| `deputy` | label opens with the country's `deputy` words and the rest names the head office |
| `legislator` | `P361`/`P2389` = the unit's `P194`, or a legislator class |

The model step uses the repair prompt's pattern: candidates are indices, the
answer must quote, and the result is cached by content. It runs only on cells
where no mechanical channel decides. Regional ministers, provincial officers
and honours fall in no slot. Ministers are counted in a report-only `cabinet`
column.

### 4. Cell states

| state | meaning |
|---|---|
| `ok` | linked from the unit, well-formed (`gaps.well_formed`), held |
| `unlinked` | the office exists and is scoped, but the unit doesn't link it |
| `repair` | the office exists but has a gap (`P17`/`P279`/`P31`, as today) |
| `unheld` | well-formed and linked, no holder: a peploop job, not peptree's |
| `claimless` | found only by search |
| `missing` | nothing found: a mint candidate |
| `n/a` | slot doesn't exist for this unit (no deputy office in the country, no legislature) |

### 5. Lanes that write

- **A. Unit back-link (new, mechanical).** Add `P1313`/`P1906` on the *unit*
  item. Two channels are required:
  - the office's `P1001` = the unit;
  - the slot evidence: the sibling convention or the class closure.

  168 candidates today, more after discovery. This is the first lane that
  writes to place items, so `qs.validate` and the outbox need to accept a
  place subject. Where a unit's `P1313` is a generic class, the specific office
  is *added* (34 today). Removing the generic value is destructive, so it goes
  on a list for the user, never into a batch.
- **B. Office repair.** The existing repair lane, now reaching unit offices too.
  `P279` takes the country's head archetype, which gives the class fix a
  subnational target. `P17` follows `p17_not_a_state`, as today.
- **C. Claimless resolution.** A search hit the model confirms gets the
  archetype's `P31`/`P279`/`P1001`/`P17` through lane B.
- **D. Mint.** A `missing` head cell gets an item:
  - `P31` = the country's metaclass convention;
  - `P279` = the archetype;
  - `P1001` = the unit;
  - `P17` = the country;
  - label from the archetype template in the country's languages plus en.

  It goes through QS `CREATE` with the `ptree_create` ledger already designed in
  `plans/peptree.md` ("Finding created QIDs on a re-run"). The unit's
  `P1313` = new item can't go in the same batch (`LAST` is subject-only), so the
  next run's lane A writes it. That's the intended order, not a workaround. The
  duplicate search runs at `max_age=0` right before rendering, because others
  are minting this layer.
- **Deputy and legislator cells** are reported, and minted only when the country
  already has the slot for at least half its units (completing a set, never
  starting one).

### 6. Report

The country report gets a `## Subnational` section:
- the chosen level and why;
- unit × slot counts by state;
- the mint queue with each cell's evidence;
- the generic-`P1313` removal list.

`sweep.md` gets a column. The national matrix is unchanged.

## Phases (each ends in a checkpoint)

0. **Read-only report.** Port the probes into `peptree/subnational.py`: level
   choice, discovery, slots by mechanical channels only, cells. Run over the
   reviewed sweep countries and look at the level choice and the matrix for
   about 10 profiles: ng, ph, gh, th, ir, in, ug, az, dz, pf. *Checkpoint:
   level choices and the `head?` residue, eyeballed in full.*
1. **Discovery lanes in load, and the model slot step.** *Checkpoint: the full
   matched list with resolved labels, per `CLAUDE.md`'s matcher rule.*
2. **Lane A (back-link) to the outbox.** *Checkpoint: the first chunk, read
   line by line.*
3. **Lanes B and C on unit offices.**
4. **Mint queue as a report**, then minting once the evidence rule below is
   decided.

## Decisions for the user

1. **The evidence bar for a mint.** The peploop bar (≥2 holders, ≥1 current)
   would mint almost nothing in the gap countries. My recommendation has three
   parts:
   - *Completing a set* (the country already has the office for ≥50% of the
     level's units): mint the rest with the unit's own article quoting the
     office. No holder needed, because the office is structural and its
     siblings prove the shape.
   - *Starting a set* (a gap country): one quoted source that establishes the
     office for every unit of the level, plus at least one named current holder
     somewhere in the country.
   - *Never*: an office with no source, or an archetype that no sibling and no
     national class supports.
2. **Deputies and legislature members: in FATF scope?** OpenSanctions types
   `Q486839` member of parliament as PEP but `Q4175034` legislator as not, and
   most provincial-assembly seats are the latter. My recommendation: report
   both, mint neither until asked.
3. **Should level 2 ever be scored alongside level 1?** Nigerian LGA chairs,
   Indonesian *bupati* and Romanian mayors are all linked and well-formed. My
   recommendation: no. One governed level per country; municipal levels belong
   to the mayor workstream.
4. **Writes to place items** (lane A): this is a new kind of subject for
   peptree's batches. It's additive, but it is a new place to make mistakes, so
   it gets its own first-chunk review.

## Not in scope

- Mayors and municipal levels, including Brazil's mayoralty repairs.
- Regional cabinets (`cabinet` is report-only).
- Holders: an `unheld` office is peploop's.
- Removing generic `P1313` values (destructive; listed only).

## Consumer note

zavod reads `P1001` = a unit as `subnationalArea` and finds the country through
the unit (`item_countries`). So a governor with `P1001` and a `P279` reaching
`Q132050` is emitted as a PEP without a `P17`. That is a reason the model is
legible, not a reason to choose it: lane B still adds `P17` because the
country's siblings carry it.
