# Iran — institution coverage

Campaign `scripts/ir_offices.py`; plan `plans/iran_sweep.md` (first run) and
`plans/iran_rerun.md` (this one); baseline `regression/iran/`.

* **Run 1**, 2026-08-18/19 — 66 offices, 1,054 statements applied.
* **Run 2**, 2026-08-19 — 100 offices, **1,538 statements** rendered (1,125
  QuickStatements + 413 via the API for 186 people), 0 to review, 476 skipped
  with a reason. 27 position items minted. **Applied 2026-08-19** — the API half
  verified live at exactly the expected count (0 short, 0 doubled).

Run 2 was scoped from this ledger rather than from the campaign script, which is
the whole point of the file: run 1 reported itself finished with eleven
institutions never looked at, three of which needed only a config line.

| id | offices | items | rows | expected | shipped | status | evidence |
|---|---:|---:|---:|---:|---:|---|---|
| `executive.head_of_state` | 2 | 2 | 17 | 17 | ~4 | `shipped` | leader + president; ~100% dated already, the calibration set |
| `executive.head_of_government` | 1 | 1 | 78 | 78 | ~20 | `shipped` | PM, abolished 1989 |
| `executive.deputy_leadership` | 1 | 13 | 8 | 8 | 8 | `◐ partial` | first VP only; 11 portfolio vice-presidencies never configured. `Q2660216`, the generic VP, holds 43 |
| `executive.cabinet` | 24 | 24 | 921 | 921 | ~301 | `shipped` | 24 of 26 ministry rosters; 2 lack items |
| `executive.deputy_ministers` | 0 | 0 | 10 | ? | 0 | `blocked:deputy-ministers` | ten deputies sit on the interior page, heading-filtered out. `Q116214167` exists with 3 holders |
| `executive.leader_office` | 0 | 1 | 0 | 0 | 0 | `no-source` | `Q110126773`, 1 holder. Measured run 2: `fa:دفتر رهبری` is about the Hosseiniyeh, `بیت رهبری` yields no roster, no category, no infobox chain |
| `legislature.lower_membership` | 1 | 1 | **3067** | 2349 | **1078** | `shipped` | **terms 1–12.** Run 1 had 4 terms and 388; terms 1–8 are alphabetical bullet rolls (1,871 rows, 99% wikilinked) that the heading allowlist hid entirely. Backtest 1,665 on record, target 100%, date 98% |
| `legislature.upper_membership` | — | — | — | — | — | `absent` | no upper house since 1979 |
| `legislature.leadership` | 1 | 3 | 22 | ~10 | 0 | `covered` | Speaker `Q6597965` configured run 2; all 7 holders already recorded, so the lane proposes nothing. Measured, not assumed |
| `legislature.leadership.deputy` | 0 | 1 | 56 | 56 | 0 | `blocked:wide-roster` | `Q118321724`. `fa:نایب‌رئیس مجلس شورای اسلامی` is **two holders per row** (first and second deputy), keyed by term ordinal, and dates nothing |
| `legislature.historic_chambers` | 0 | 2 | ~1400 | — | 0 | `blocked:historic-chambers` | NCA `Q134563198` holds 85; 7 Senate rolls / 173 people; `era.distinct`, needs own items |
| `oversight.constitutional_body` | 2 | 2 | 16 | 11 | 11 | `shipped` | Guardian Council member + secretary |
| `oversight.state_councils` | 4 | 5 | 437 | 260 | ~190 | `shipped` | AoE rolls 428 rows → 179 records; Expediency |
| `oversight.state_councils.snsc` | 1 | 1 | 8 | 0 | 0 | `absent` | membership is **ex officio** — measured, no member item should exist |
| `oversight.audit_anticorruption` | 0 | 0 | 7 | ? | 0 | `⊘ creation-first` | General Inspection Office, 7 rows, no item. `fa:سازمان بازرسی کل کشور` is prose bullets, not a roster |
| `oversight.electoral_commission` | 0 | 0 | 0 | 0 | 0 | `no-source` | measured run 2: `fa:ستاد انتخابات کشور` exists and lists no holders; oversight is the Guardian Council's, already covered |
| `judiciary.apex` | 1 | 1 | 8 | 8 | ~1 | `shipped` | 8/8 dated, parsed with no code change |
| `judiciary.prosecution` | 1 | 1 | 14 | 14 | ~10 | `shipped` | fa strictly better than en here |
| `judiciary.specialised` | 1 | 1 | 40 | ~40 | ~4 | `⊘ creation-first` | **5 of 9 judicial offices have no item**; 17 named judges deliberately not minted |
| `economic.central_bank` | 1 | 1 | 25 | 25 | **11** | `shipped` | `Q20110284` had 3 holders and no office. **en** roster, 25 rows / 25 dated; fa's tabulates 24 and dates none |
| `economic.sovereign_wealth` | 0 | 0 | 0 | 0 | 0 | `⊘ creation-first` | measured twice: 0 P39, 0 P108, `pq:P642` unused. `fa:صندوق توسعه ملی` is statute clauses, not a roster |
| `economic.soe_leadership` | 0 | 0 | 0 | 0 | 0 | `⊘ creation-first` | same census; `fa:شرکت ملی نفت ایران`'s 581 bullets are subsidiary companies |
| `economic.regulators` | 0 | 0 | 0 | 0 | 0 | `no-source` | measured run 2: SEO and Bimeh Markazi articles list statutory duties and subsidiaries; no holder roster in either |
| `security.defence_command` | 3 | 3 | ~20 | ~20 | ~8 | `shipped` | general staff, Artesh C-in-C, navy |
| `security.paramilitary` | 8 | 8 | ~90 | ~90 | ~35 | `shipped` | IRGC: 291 of 420 catalogued people held no P39 |
| `security.intelligence` | 1 | 1 | 9 | 9 | ~1 | `shipped` | MOIS |
| `security.police` | 1 | 1 | 9 | 9 | **9** | `shipped` | `Q114457755` had **0** holders. No roster in either wiki — the Qatar path: en chief-commanders category + the holders' own infoboxes |
| `subnational.executive` | **31** | **31** | 902 | 640 | **408** | `created+shipped` | **27 items minted 2026-08-19.** Run 1 shipped 0 of 903. 128 rows skipped `pahlavi`, 246 pre-1979 |
| `subnational.municipal` | 0 | 3 | ~130 | 0 | 0 | `blocked:muni-countries` | Tehran 75 rows/75 dated. **Measured 2026-08-19**: `Q6627742` (47 holders), Isfahan and Qom are correctly shaped and dropped at gate 5 — `ir` ∉ `MUNI_COUNTRIES`. Minting more emits nothing |
| `subnational.assemblies` | 0 | 6 | 21 | 0 | 0 | `no-source` | Tehran council 21 rows, undated, 9% linked — measured |
| `diplomatic.outbound` | 15 | 78 | 765 | 244 | 28 | `◐ partial` | 15 of 32 parseable rosters; only 244 of 765 rows datable; Oman deferred (RTL) |
| `diplomatic.multilateral` | 1 | 2 | 21 | 21 | **3** | `shipped` | `Q7169241` had 9 holders and no office. The en table names its columns "Permanent Representative"/"Years served", which match no role key — it produced *no roster at all* until declared |
| `hybrid.ruling_family` | — | — | — | — | — | `absent` | no hereditary office since 1979 |
| `hybrid.religious_hierarchy` | 0 | 4 | ~120 | ? | 0 | `⊘ creation-first` | Friday prayers = leader's representatives, one office; ~31 provinces, 4 items |
| `hybrid.parastatal_foundations` | 0 | 1 | 109 | ~3 | 0 | `⊘ creation-first` | 6 bonyad headships ruled *positions*; Astan Quds mostly lunar-dated |
| `hybrid.state_media` | 0 | 0 | 18 | 18 | 0 | `⊘ creation-first` | **found run 2**: `fa:رئیس سازمان صدا و سیمای جمهوری اسلامی ایران`, 18 rows / 17 dated / 14 linked. No position item exists — `lookup_position` unmatched on three spellings |
| `political.parties` | 0 | 2 | 99 | 3 | 0 | `no-source` | measured: 10 tables, 99 leaders, **zero dates**; convention is `P488` on the party |

## Item-layer audit (`recipes/position_items.md`, 2026-08-19)

`scripts/position_metadata.py --country ir` over **323** position items scoped to
Iran, then calibrated against live `yente-cli fetch` for all 279 that have a
holder. The port and OpenSanctions agree on 190 of 279; the recipe's reading
order — no holders, then the review layer, then a port bug — accounts for the
rest, and **no port bug was needed to explain any of it**.

| | |
|---|---:|
| items scoped | 323 |
| pass all five gates | 193 |
| … and have a holder | **186** |
| … capable but unheld | 7 |
| fail ≥1 gate | 130 |
| … and have a holder | 93 |

**The 27 governorships minted this run pass all five gates** — `P279 = Q132050`
confers `role.pep` + `gov.executive`. They are absent from OpenSanctions only on
rebuild cadence, which the recipe warns cannot verify its own fixes.

### Two structural drops, confirmed live

* **Mayoralties are invisible in Iran, whatever the item says.** `Q6627742`
  Mayor of Tehran (**47 holders**), `Q28169496` Isfahan and `Q109901180` Qom are
  each correctly `P279 = Q30185` with no `P576`, and each fails gate 5 alone:
  `ir` is not in `MUNI_COUNTRIES`. All three confirmed absent from
  OpenSanctions. **This cancels the ~10-mayor creation round** in `To close` —
  minting them would produce items that look done and emit nothing, which is the
  recipe's own anti-pattern. Upstream issue, not an item fix.
* **`Q13561063` Prime Minister of Iran (70 holders)** fails twice: `P279` is
  `Q14212` "prime minister", which confers `gov.head` and `gov.executive` and no
  `role.pep`, and `P576 = 1989-08-03` falls four months before the
  `1990-12-26` abolition cutoff. The parent is fixable on Wikidata (pair it with
  `Q2285706`); the cutoff is not, so living former premiers stay invisible.

### The port is stricter than OpenSanctions, in a knowable way

37 items the port failed are carried by OpenSanctions anyway — the review layer
rescuing them — including the second-largest lane in this campaign,
`Q98458420` Member of the Assembly of Experts (198 holders, `P279` = elective
office). Reporting those 113 `no_pep_topic` items as broken would have invented
defects; the recipe says so, and the calibration set is what proved it.

### 22 pass every gate, hold statements, and are absent on their own merits

Two explained groups, neither an item defect:

* **13 ambassadorships.** `P17` on an outbound post is the *receiving* state, so
  these belong to the receiver's country and not to Iran's — the standing
  `P137` gap, opensanctions/opensanctions#5475.
* **The rest are historical or abolished offices** — the National Consultative
  Assembly (85 holders), Atabeg, Minister of Information and Tourism — plus
  `Q19718069` Anglican Bishop in Iran, which is the review layer's call to make.

### Scope note

The label channel admits non-Iranian items — Brunei's and Kedah's legislatures,
a Malaysian religious council, `Q708492` "council member" with 3,050 holders
worldwide. That is the channel working as designed (it exists to admit items
with no country path) and not a finding about Iran.

## Close status: **NOT CLOSED**

| | run 1 | run 2 |
|---|---:|---:|
| `shipped` / `created+shipped` / `◐ partial` / `covered` | 14 | **19** |
| `⊘ creation-first` — unfinished by definition | 7 | 7 |
| `blocked:` — named, with a followup | 0 | **3** |
| `absent` / `no-source` — closed with a measurement | 5 | **8** |
| `not-attempted` — not a permitted disposition | **11** | **0** |

**No row reads `not-attempted`.** That was run 2's first goal and it is met: the
six never-examined classes were measured, and four of them close as `no-source`
on the measurement rather than on a shrug.

What run 2 changed, in one line each:

* **The Majlis lane tripled** — 388 → 1,078 — because `parse_bullet_rosters`
  gained the `headings` override its table counterpart always had.
* **The governor lane exists** — 0 → 408 — because 27 items were minted.
* **Three offices whose item was already there** shipped 23 statements between
  them for the cost of a config line each, exactly as this ledger predicted.

## To close

Seven `⊘` rows and three `blocked:` ones. `⊘` is not a resting state:

1. **One more creation round** — IRIB headship (18 rows, measured and ready),
   the General Inspection Office, 5 judicial, ~31 clerical, 6 bonyad. **Not the
   mayors**: the item-layer audit below confirms every Iranian mayoralty is
   dropped at gate 5, so `subnational.municipal` closes as
   `blocked:muni-countries` rather than by minting ten items that emit nothing.
   Watch the parent on each: `Q1162163` director, `Q16533` judge and `Q121998`
   ambassador all pass the type gate and confer no `role.pep`.
2. **The remaining 17 ambassador rosters** and Oman's RTL-reversed ranges.
3. **The 11 portfolio vice-presidencies**, and the deputy-minister rows the
   interior page's heading filter drops.
4. **`legislature.leadership.deputy`** needs a two-holders-per-row reader, or a
   decision to take the first-deputy column only and say so.
5. **The historic chambers** (NCA, Senate) need their own items.

## The gate that is not a gap

`legislature.leadership` reads `covered` with **0 shipped**, and that is the
right answer: all 7 speakers already hold the statement. The same gate — held
per (person, target), not per term — is why the Majlis lane's 1,078 is not
higher: a member re-elected in a term the engine already recorded is invisible
to it. Recovering those needs a per-term gate, and per-term membership cannot go
through QuickStatements at all, so it is a write-path change and not a rule
change. Named here rather than folded into a number.
