---
description: Plan for Lithuania's three-lane sweep — a first peploop run, a second peptree run and a pepcorp re-run, seeded broad at national level with every municipality's mayor, as the AMLR list names them, as the local tier; measurements of 2026-11-25, the seed and census in countries/lt.yml, stage order, budgets and the decisions for the user.
date: 2026-11-25
tags: [sweep, lt, peploop, peptree, pepcorp, seeds, census, mayors, amlr]
---

# Lithuania sweep

Run as `peploop/countries.md` §7, on the Kyrgyz pattern (`plans/kg_sweep.md`).
peploop has never run Lithuania: a **first run**, seeds and census drafted in
`peploop/countries/lt.yml` (they pass `check_countries`; the census loads 14
anchors). peptree ran it once (batch 45, reviewed 2026-10-08, 184 kept, 5
lines, chunk 044). pepcorp ran it 2026-10-17 to 10-24 (78 enterprises written
on). The state is `Q37`.

## Scope, as the user set it (2026-11-25)

- **Broad at national level**: every tier `docs/institutions.md` names that
  lt.wikipedia files.
- **Local tier = the mayors the AMLR list names**: all 60 municipalities
  (`lt.amlr.yml` rows 1205–1324), by `Lietuvos_merai` at depth 1. First
  narrowed to the ten units of 50,000 or more, then widened to the list the
  same day. Vice-mayors and councillors are out (+549); the list's municipal
  administration directors are left to the mentions.
- **SOE holdings stay as they are.** The Governance Coordination Centre's
  list (`https://governance.lt/apie-imones/vvi-sarasas/`, spreadsheet
  `https://governance.lt/wp-content/uploads/2026/07/Imoniu_sarasas_su_pokyciu_registru_2026.xlsx`:
  32 VVĮ and their subsidiaries, with company code, share and holding
  ministry) goes into OpenSanctions as a source directly, not through
  Wikidata. Measured in passing: 34 of the list's top-level and large
  first-level entries resolve to items by `P10772`; `corp run lt` re-runs on the
  existing `corp` section.

## The era

- Seimas elected October 2024; the government changed in 2025. The propose
  checkpoint confirms the incumbents rather than assuming them.
- Municipal councils and directly elected mayors: March 2023, next election
  **March 2027**. A run now writes the 2023–2027 term; after April 2027
  the mayors want a re-run.

## Measurements (2026-11-25)

**Category tree.** lt.wikipedia is regular: `Lietuvos_ministrai` (26 portfolio
subcategories), `Lietuvos_viceministrai` (15), `Seimo_nariai` (677 pages +
signatories, speakers, deputy speakers), one category per apex court, the
prosecutors general and deputies, `Lietuvos_merai` (60 per-municipality
subcategories), `Lietuvos_savivaldybių_politikai` (60). en adds
`Political_office-holders_in_Lithuania`.

**PetScan, chosen entries** (marginals in `lt.yml`): national 1,475 distinct,
`Lietuvos_merai` +277, **1,752 in all**. Left out, with marginals: vice-mayors +28, municipal politicians +521, Court of Appeal
+11, prosecutors +17, generals +41, county governors +13, ambassadors +108, en
politicians by place +72, `Lietuvos_politikai` +247.

**Wikidata's office set**: 250 items in the descent, about 120 of them offices
of the republic. Mayors (`Q1317377xx`) and council seats (`Q1317550xx`) exist
for all 60 municipalities; the 14 ministers; the court presidents; some 30
agency directors (`Q141…`/`Q142…`, made 2026 by another editor). **No item**:
apex-court judges, vice-ministers, ministry chancellors, deputy prosecutors
general, outbound ambassadors (only the UN and EU permanent representatives).
**Twin**: Minister of Economy and Innovation `Q107735812` (24 holders) /
`Q140592938` (2). **Renamed**: Education and Science `Q140638601` (12; its lt
label says "švietimo ir sporto") / Education, Science and Sport `Q30313091` (5).

**The mayors.** 58 of the 60 offices have an open holder. Not reached by the
seeds: Panevėžys's Loreta Masiliūnienė `Q133295247`, Panevėžys District's
Antanas Pocius `Q12648740` and Vilkaviškis's Algirdas Neiberka `Q16443376`
(all with lt articles: queued by `--qid`); Jonava's Valdas Majauskas,
Marijampolė's Valdas Tumelis and Druskininkai's Violeta Grigorienė (2026
by-elections, no article: residue). Open statements to watch, none of them
ours: Panevėžys has two open (Luomanas 2024-11, Masiliūnienė 2025-04),
Klaipėda District two (Dačkauskas 2015, Markauskas 2019), Kazlų Rūda two,
Kaunas has Matijošaitis open twice (2015, 2023), Vilnius an open 1812
statement on `Q98107569`.

**AMLR.** `lt.amlr.yml`'s expansions predate the mayor items: 58 of the 60
mayor rows have no expansion though their items exist. That is the AMLR lane's
`amlr expand`, outside this sweep; listed in the closing report.

## Cost and budgets

Slovenia's 1,248 people cost $33 for extract and reconcile; Lithuania's 1,752
are one wiki plus en, so about **$55–70** in all. `--live`, budgets:

| stage | budget |
|---|---|
| extract | $20 |
| reconcile | $25 |
| mint | $8 |
| verify | $8 |
| corp | $6 |

## Stages

§7's order, from `tree place lt` through `report applied`, plus
`seed --country lt --qid Q133295247 Q12648740 Q16443376` after `seed`. What to check:

- **load-positions**: `Q18507240` and the 60 mayor items load as Lithuania's.
- **reconcile**: "ekonomikos ir inovacijų ministras" lands on `Q107735812`,
  not the twin; "švietimo, mokslo ir sporto ministras" on `Q30313091`, the
  pre-2019 title on `Q140638601`; "viceministras" mentions go to the creation
  queue by ministry, never onto the minister.
- **propose**: Seimas seats of the 2024 term start at the first sitting
  (2024-11-14), not the election; the mayors' 2023 tenures are their own
  statements beside the 2015/2019 ones.
- **mint (dry)**: the three apex judges, vice-ministers per ministry (from
  the mentions), the four service commanders. Ambassadorships come back
  `diplomatic/deferred`.
- **corp run lt**: read `data/pepcorp/lt/lt-<date>.md` against 2026-10-24's.

## Sends, each on the user's go

1. `tree send --batch 45 --submit`, if `tree place lt` finds anything.
2. `mint --country lt --submit`, then `verify` and a fresh `send` dry run.
3. `send --country lt --submit`: one tranche if the rows' people stay under
   1,500, else current holders first.
4. `corp send lt --submit`.

Then §6: Lithuania's tokens in `check_neutral.TOKENS` (the name stem, `Q37`,
`lt.wikipedia`, Vilnius), the `history.md` line, the push proposal.

## Decisions for the user

1. **Local tier.** All 60 mayors, as the AMLR list names them; the
   councillors (+521) or vice-mayors (+28) are one seed line each.
2. **The Economy and Innovation twin.** Merging `Q140592938` into
   `Q107735812` is a merge outside the lanes, not part of this run.
3. **Ambassadors.** Left out (+108), as for Kazakhstan and Kyrgyzstan, until
   mint makes ambassadorships.
4. **The governance.lt list** as an OpenSanctions source: a crawler in
   `opensanctions/datasets`, outside this repository.

## The run (2026-11-25), to the dry runs

**Spend: $137.58**, twice the estimate: extract $40.37 ($0.032 a head, 1,266
people), resolve $58.84 (7,270 mentions), mint $23.81 (categorize ran twice:
the census changed), verify $10.50, peptree $1.09, pepcorp $2.13.

**peptree** (batch 45): 8 lines, 2 struck. `Q1362218` P1001 (the item
conflates the Police Commissioner General, ltwiki, with a German police rank,
dewiki) and `Q30064875` P31 (a diplomatic rank class). Left: P1001 on three
agency heads and the border guard commander, P17 on three dioceses' bishops.
The sweep table row still shows the 2026-10-08 run; `tree sweep table` was not
re-run because `tree/sweep.md` carries uncommitted edits.

**peploop**: 1,750 seeded, 1,266 in scope. 1,755 P39 rows: 697 ended, 123
open and unattested, 108 contested, 451 supported. Send dry run: **588 lines
for 427 people**: 450 P39 (28 open: 11 Seimas seats of the 14th Seimas, 5
deputy speakers, court and judicial-council presidents, council seats), 78
P27, 28 birth dates (14 refine a year to a day), 3 death dates, 12 genders;
11 merges, 1 row closed as `ambiguous-statement`. No mayor line is open: the
sitting mayors already hold their P39.
Fixes in the run: lt present-tense markers (`tenure.CURRENT`); the
vice-ministers by ministry and no bank board, land force or police in the
census. Audited out: the twin-bound Economy and Innovation row (#302907) and
a Seimas seat dated from the election (#302132).

**mint**: 5 to create: judges of the Supreme, Supreme Administrative and
Constitutional Courts, the environment vice-minister, the Freedom Party
chair. 13 vice-ministers came back not current or unclear; party chairs mostly
medium. `Q141306379` (Land Force commander) exists untyped.

**pepcorp**: 111 lines on 65 bodies (41 P1037, 28 P3320 party board seats,
12 P127, 12 P169, 9 P31, 5 P488, 3 P749, 1 P5052). Fixed in the run: the
city-state rule wrote Kaunas's and Klaipėda's municipal companies as
state-owned (`municipal_subdivisions`).

## Send proposal

In this order, each on the user's go:

1. `tree send --batch 45 --submit`: 6 lines.
2. `mint --country lt --submit`: 5 items; then `verify` and a `send` dry run
   for the lines their feed adds.
3. `send --country lt --submit`: one tranche, 577 lines (after the full audit below).
4. `corp send lt --submit`: 111 lines.

Open: the Economy and Innovation twin merge; the conflated `Q1362218`; the
13 vice-ministries; `check_neutral` still flags the AMLR lane's
`amlr_expand.py:67` and `prompts/amlr_match.md:13` (Lithuania as an example)
beside the older Kazakh example in `prompts/extract.md`.

## The full audit (every line)

All 583 accepted peploop rows were read against every source quote, and all
111 pepcorp lines against their report entries. Taken out with `audit
proposal` (10 rows; 588 → 577 lines): an end date no source gives (#301313,
#302641), a quote about another office (#302769), a 1990–2007 council seat on
today's council item (#303585), an end inferred from a later election
(#302387), a bare death date with no "died" (#302463), and four citizenships
read from ethnicity ("Tautybė: lietuvis", "lietuvių"), a birthplace, or
against a stated Russian citizenship (#301744 #301822 #301703 #302711): an
open class, since lt "tautybė" names ethnicity where the extract prompt reads
an infobox `Nationality:` as citizenship. Kept after reading all sources: six
rows whose first quote lacked a date another language gives, and title-only
mayor quotes whose infobox the verifier read. The pepcorp lines held.

`check_neutral`: the AMLR lane's two Lithuania hits are neutralised (an
example marker on `amlr_match.md:13`, which re-keys that pass's ledger, and a
reworded comment); the Kazakh example in `extract.md:250` remains, as it did
at Kazakhstan's close, since changing it re-keys every country's extraction.
The peptree sweep row is updated by hand (`tree/sweep.md`, beside the user's
uncommitted edits there).
