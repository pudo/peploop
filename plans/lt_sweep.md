---
description: Plan for Lithuania's three-lane sweep — a first peploop run, a second peptree run and a pepcorp re-run, seeded broad at national level with the AMLR's ten 50,000+ municipalities' mayors as the local tier; measurements of 2026-11-25, the seed and census in countries/lt.yml, stage order, budgets and the decisions for the user.
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
- **Local tier = the AMLR's mayors**: the ten municipalities of 50,000 or more
  (`amlr.units("lt")`): Vilnius city and district, Kaunas city and district,
  Klaipėda city and district, Šiauliai, Panevėžys, Marijampolė, Mažeikiai.
  Read as: not a mayors-only sweep, and of the mayors only these ten. The other
  50 mayors, the vice-mayors and the councillors are out (+836 people); a
  wider local tier is a seed edit away (the counts are in the seed comment).
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
the ten mayor categories +52, **1,527 in all**. Left out, with marginals: the
other mayors +287, vice-mayors +28, municipal politicians +521, Court of Appeal
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

**The ten mayors.** Every office has an open holder. Reached by the seeds:
all but Panevėžys's Loreta Masiliūnienė (`Q133295247`, lt article, open from
2025-04-14) and Marijampolė's Valdas Tumelis (`Q16475279`, no article:
residue). Open statements to watch, none of them ours: Panevėžys has two open
(Luomanas 2024-11, Masiliūnienė 2025-04), Klaipėda District two (Dačkauskas
2015, Markauskas 2019), Kaunas has Matijošaitis open twice (2015, 2023),
Vilnius an open 1812 statement on `Q98107569`.

**AMLR.** `lt.amlr.yml`'s expansions predate the mayor items: 58 of the 60
mayor rows have no expansion though their items exist. That is the AMLR lane's
`amlr expand`, outside this sweep; listed in the closing report.

## Cost and budgets

Slovenia's 1,248 people cost $33 for extract and reconcile; Lithuania is one
wiki plus en, so about **$45–60** in all. `--live`, budgets:

| stage | budget |
|---|---|
| extract | $20 |
| reconcile | $25 |
| mint | $8 |
| verify | $8 |
| corp | $6 |

## Stages

§7's order, from `tree place lt` through `report applied`, plus
`seed --country lt --qid Q133295247` after `seed`. What to check:

- **load-positions**: `Q18507240` and the 60 mayor items load as Lithuania's.
- **reconcile**: "ekonomikos ir inovacijų ministras" lands on `Q107735812`,
  not the twin; "švietimo, mokslo ir sporto ministras" on `Q30313091`, the
  pre-2019 title on `Q140638601`; "viceministras" mentions go to the creation
  queue by ministry, never onto the minister.
- **propose**: Seimas seats of the 2024 term start at the first sitting
  (2024-11-14), not the election; the ten mayors' 2023 tenures are their own
  statements beside the 2015/2019 ones.
- **mint (dry)**: the three apex judges, vice-ministers per ministry (from
  the mentions), the four service commanders. Ambassadorships come back
  `diplomatic/deferred`.
- **corp run lt**: read `data/pepcorp/lt/lt-<date>.md` against 2026-10-24's.

## Sends, each on the user's go

1. `tree send --batch 45 --submit`, if `tree place lt` finds anything.
2. `mint --country lt --submit`, then `verify` and a fresh `send` dry run.
3. `send --country lt --submit`: one tranche (well under 1,500 people).
4. `corp send lt --submit`.

Then §6: Lithuania's tokens in `check_neutral.TOKENS` (the name stem, `Q37`,
`lt.wikipedia`, Vilnius), the `history.md` line, the push proposal.

## Decisions for the user

1. **Local tier.** The ten AMLR mayors only, as read above. Adding the other
   50 mayors (+287) or the councillors (+521) is one seed line each.
2. **The Economy and Innovation twin.** Merging `Q140592938` into
   `Q107735812` is a merge outside the lanes, not part of this run.
3. **Ambassadors.** Left out (+108), as for Kazakhstan and Kyrgyzstan, until
   mint makes ambassadorships.
4. **The governance.lt list** as an OpenSanctions source: a crawler in
   `opensanctions/datasets`, outside this repository.
