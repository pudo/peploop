# Iran — institution coverage

Campaign `scripts/ir_offices.py`; plan `plans/iran_sweep.md`; baseline
`regression/iran/`. Run 2026-08-18/19, three QuickStatements batches (717
statements) plus 337 via the API.

**Retrofitted after the fact**, which is why so many rows read `not-attempted` —
a status the method no longer permits at close. This ledger is the honest picture
of a run that reported itself finished.

| id | offices | items | rows | expected | shipped | status | evidence |
|---|---:|---:|---:|---:|---:|---|---|
| `executive.head_of_state` | 2 | 2 | 17 | 17 | ~4 | `shipped` | leader + president; ~100% dated already, the calibration set |
| `executive.head_of_government` | 1 | 1 | 78 | 78 | ~20 | `shipped` | PM, abolished 1989 |
| `executive.deputy_leadership` | 1 | 13 | 8 | 8 | 8 | `◐ partial` | first VP only; 11 portfolio vice-presidencies never configured |
| `executive.cabinet` | 24 | 24 | 921 | 921 | ~300 | `shipped` | 24 of 26 ministry rosters; 2 lack items |
| `executive.deputy_ministers` | 0 | 0 | 10 | ? | 0 | `not-attempted` | ten deputies sit on the interior page, heading-filtered out |
| `executive.leader_office` | 0 | 1 | 0 | ? | 0 | `not-attempted` | `Q110126773` exists, 1 holder |
| `legislature.lower_membership` | 1 | 1 | 1196 | 2349 | 388 | `◐ partial` | **16% of estimate.** Terms 9–12 only; 1–8 titles not found; per-term gate drops 423 people |
| `legislature.upper_membership` | — | — | — | — | — | `absent` | no upper house since 1979 |
| `legislature.leadership` | 0 | 3 | 0 | ~10 | 0 | `not-attempted` | Speaker `Q6597965`, deputy `Q118321724` — items exist, never configured |
| `legislature.historic_chambers` | 0 | 2 | ~1400 | — | 0 | `not-attempted` | NCA 85 holders, 7 Senate rolls / 173 people; `era.distinct`, needs own items |
| `oversight.constitutional_body` | 2 | 2 | 16 | 11 | 11 | `shipped` | Guardian Council member + secretary |
| `oversight.state_councils` | 4 | 5 | 437 | 260 | ~190 | `shipped` | AoE rolls 428 rows → 179 records; Expediency |
| `oversight.state_councils.snsc` | 1 | 1 | 8 | 0 | 0 | `absent` | membership is **ex officio** — measured, no member item should exist |
| `oversight.audit_anticorruption` | 0 | 0 | 7 | ? | 0 | `⊘ creation-first` | General Inspection Office, 7 rows, no item |
| `oversight.electoral_commission` | 0 | 0 | 0 | 0 | 0 | `not-attempted` | never looked |
| `judiciary.apex` | 1 | 1 | 8 | 8 | ~1 | `shipped` | 8/8 dated, parsed with no code change |
| `judiciary.prosecution` | 1 | 1 | 14 | 14 | ~10 | `shipped` | fa strictly better than en here |
| `judiciary.specialised` | 1 | 1 | 40 | ~40 | ~4 | `⊘ creation-first` | **5 of 9 judicial offices have no item**; 17 named judges deliberately not minted |
| `economic.central_bank` | 0 | 1 | 0 | ? | 0 | `not-attempted` | `Q20110284`, 3 holders — item exists, never configured |
| `economic.sovereign_wealth` | 0 | 0 | 0 | 0 | 0 | `⊘ creation-first` | measured: 0 P39, 0 P108, `pq:P642` used zero times |
| `economic.soe_leadership` | 0 | 0 | 0 | 0 | 0 | `⊘ creation-first` | same census; IRIB's "employees" are presenters |
| `economic.regulators` | 0 | 0 | 0 | 0 | 0 | `not-attempted` | never looked |
| `security.defence_command` | 3 | 3 | ~20 | ~20 | ~8 | `shipped` | general staff, Artesh C-in-C, navy |
| `security.paramilitary` | 8 | 8 | ~90 | ~90 | ~35 | `shipped` | IRGC: 291 of 420 catalogued people held no P39 |
| `security.intelligence` | 1 | 1 | 9 | 9 | ~1 | `shipped` | MOIS |
| `security.police` | 0 | 1 | 0 | ? | 0 | `not-attempted` | FARAJA `Q114457755` found by lane E, never configured |
| `subnational.executive` | 0 | 4 | 903 | 640 | 0 | `⊘ creation-first` | **778 of 903 rows behind 27 item creations + a missing `governor` archetype** |
| `subnational.municipal` | 0 | 3 | ~130 | ? | 0 | `not-attempted` | Tehran 75 rows/75 dated; 10 capitals need items |
| `subnational.assemblies` | 0 | 6 | 21 | 0 | 0 | `no-source` | Tehran council 21 rows, undated, 9% linked — measured |
| `diplomatic.outbound` | 15 | 78 | 765 | 244 | 29 | `◐ partial` | 15 of 32 parseable rosters; only 244 of 765 rows datable; Oman deferred (RTL) |
| `diplomatic.multilateral` | 0 | 2 | 0 | ? | 0 | `not-attempted` | UN permanent rep `Q7169241`, 9 holders |
| `hybrid.ruling_family` | — | — | — | — | — | `absent` | no hereditary office since 1979 |
| `hybrid.religious_hierarchy` | 0 | 4 | ~120 | ? | 0 | `⊘ creation-first` | Friday prayers = leader's representatives, one office; ~31 provinces, 4 items |
| `hybrid.parastatal_foundations` | 0 | 1 | 109 | ~3 | 0 | `⊘ creation-first` | 6 bonyad headships ruled *positions*; Astan Quds mostly lunar-dated |
| `hybrid.state_media` | 0 | 0 | 0 | ? | 0 | `not-attempted` | IRIB headship is a constitutional appointment |
| `political.parties` | 0 | 2 | 99 | 3 | 0 | `no-source` | measured: 10 tables, 99 leaders, **zero dates**; convention is `P488` on the party |

## Close status: **NOT CLOSED**

| | count |
|---|---|
| `shipped` / `◐ partial` | 14 |
| `⊘ creation-first` — unfinished by definition | 7 |
| `not-attempted` — not a permitted disposition | 11 |
| `absent` / `no-source` — properly closed with a measurement | 5 |

**Eleven institutions were never looked at**, including three whose position item
already exists and needed only a config line: the central bank, the Majlis
speakership and the police command. Seven more are creation-first and unminted.

The run shipped 1,054 statements and reported itself complete. Against this
ledger it is **at most a third of the country**, and the largest single gap —
903 provincial-governor rows — is one archetype and one human gate away.

## To close

1. Configure the three offices that already have items (central bank, Majlis
   speakership, FARAJA) — hours, not days.
2. Mint the governor archetype and 27 items; harvest the 903 rows.
3. Mint the 5 judicial, 7 ambassadorial, 10 mayoral and ~31 clerical items.
4. Census the SOE/parastatal layer properly and decide what a `⊘` closes as.
5. Find the Majlis term 1–8 page titles; build the per-term gate.
6. Look at the six never-examined classes and give each a measured disposition.
