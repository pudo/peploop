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
| `subnational.municipal` | 0 | 3 | ~130 | ? | 0 | `⊘ creation-first` | Tehran 75 rows/75 dated; ~10 capitals need items. `mayor` archetype exists and `Q30185` is the honest parent — the existing three are modelled correctly |
| `subnational.assemblies` | 0 | 6 | 21 | 0 | 0 | `no-source` | Tehran council 21 rows, undated, 9% linked — measured |
| `diplomatic.outbound` | 15 | 78 | 765 | 244 | 28 | `◐ partial` | 15 of 32 parseable rosters; only 244 of 765 rows datable; Oman deferred (RTL) |
| `diplomatic.multilateral` | 1 | 2 | 21 | 21 | **3** | `shipped` | `Q7169241` had 9 holders and no office. The en table names its columns "Permanent Representative"/"Years served", which match no role key — it produced *no roster at all* until declared |
| `hybrid.ruling_family` | — | — | — | — | — | `absent` | no hereditary office since 1979 |
| `hybrid.religious_hierarchy` | 0 | 4 | ~120 | ? | 0 | `⊘ creation-first` | Friday prayers = leader's representatives, one office; ~31 provinces, 4 items |
| `hybrid.parastatal_foundations` | 0 | 1 | 109 | ~3 | 0 | `⊘ creation-first` | 6 bonyad headships ruled *positions*; Astan Quds mostly lunar-dated |
| `hybrid.state_media` | 0 | 0 | 18 | 18 | 0 | `⊘ creation-first` | **found run 2**: `fa:رئیس سازمان صدا و سیمای جمهوری اسلامی ایران`, 18 rows / 17 dated / 14 linked. No position item exists — `lookup_position` unmatched on three spellings |
| `political.parties` | 0 | 2 | 99 | 3 | 0 | `no-source` | measured: 10 tables, 99 leaders, **zero dates**; convention is `P488` on the party |

## Item-layer audit (`recipes/position_items.md`, 2026-08-19)

`scripts/position_metadata.py --country ir`, 323 items scoped. The question is
whether Iran's offices are *modelled correctly as Wikidata items*; what a
downstream reader currently makes of them is recorded separately and is never a
defect.

| | |
|---|---:|
| items scoped | 323 |
| well modelled | 257 |
| `untyped` — `P31` says position, nothing says what kind | **54** |
| `no_polity` | 8 |
| `not_a_position` | 8 |
| `also_a_list_article` | 1 |

**The fix bundle: `data/iran/iran_item_layer.qs`, 14 statements, additive.**
Every parent was chosen by tallying `P279` across all position items whose
English label names the same class, and only classes with a clear winner are in
it — vice president 76 of 81, interior minister 25 of 31, speaker of a chamber
62 of 69, commander-in-chief 9 of 12, general secretary 46 of 58, director
general 27 of 38, consort 34 of 50. Council seats and secretaryships, deputy
speakerships, unit commands and spokesmanships were measured too and came back
**split**, so they stay untyped with the tally as the recorded reason rather
than take a parent this run invented.

`Q13561063` Prime Minister of Iran is in the bundle for a different reason: it
is not untyped, it carries `P279 = Q14212` alone, and the office was Iran's head
of government until 1989 — `Q2285706` is the class that says so.

Three of the untyped are offices **this campaign configured in run 2**,
the Majlis speakership among them, so the sweep wrote statements onto items that
did not say what they were.

### 11 items are surgical, and never a batch line

Retypes and merges, listed in `tasks/followups.md`: three IRGC military *ranks*
and two Wikimedia *categories* typed as positions, a social class (Bazaari), an
occupation (Bakshy), a naval rank (Daryabegi), a duplicate First Vice Chief
Justice, and a probable duplicate deputy speakership where the two items name
different bodies in `P361`.

`Q6597965` Speaker of the Majlis is on **both** lists — it is untyped *and*
dual-typed as a Wikimedia list article. Adding the `P279` is additive and is in
the batch; dropping the stray `P31` is not.

### Secondary: what a reader currently makes of them

Recorded so the ledger does not claim coverage a consumer cannot use, and **not**
a reason to model anything differently.

* `pep_default_off` on 113 items, `excluded_type` on 10, `abolished_before_cutoff`
  on 4.
* Iranian mayoralties are dropped because `ir` is absent from `zavod`'s
  `MUNI_COUNTRIES`. `Q6627742` Mayor of Tehran (47 holders) is modelled correctly
  with `P279 = Q30185`; nothing about the item changes and the mayoral lane
  proceeds.
* `Q13561063` is additionally dropped by a `P576` of 1989-08-03, four months
  before the reader's cutoff — 70 holders, some living.
* Outbound ambassadorships resolve to the receiving state, the standing `P137`
  gap (opensanctions/opensanctions#5475). **Their missing `P17` must not be
  backfilled with Iran**: on an outbound post `P17` is the receiver, so
  `Q124541201` and `Q65262055` are `no_polity` and stay that way.
* Calibrating against live `yente-cli` was worth it once: 37 items the reader
  was expected to drop are carried anyway, Assembly of Experts membership among
  them at 198 holders. Read as item defects those were fabricated problems.

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
   the General Inspection Office, 5 judicial, ~10 mayoral, ~31 clerical, 6
   bonyad. Choose each `P279` to describe the office and measure it against the
   class's convention; `Q1162163` "director" in particular says very little
   about a ministry or a command.
2. **`data/iran/iran_item_layer.qs`** — 14 additive statements, ready to run.
   Then the 40-odd untyped items whose class came back split, which need a
   convention measured per office rather than per class.
3. **The remaining 17 ambassador rosters** and Oman's RTL-reversed ranges.
4. **The 11 portfolio vice-presidencies**, and the deputy-minister rows the
   interior page's heading filter drops.
5. **`legislature.leadership.deputy`** needs a two-holders-per-row reader, or a
   decision to take the first-deputy column only and say so.
6. **The historic chambers** (NCA, Senate) need their own items.

## The gate that is not a gap

`legislature.leadership` reads `covered` with **0 shipped**, and that is the
right answer: all 7 speakers already hold the statement. The same gate — held
per (person, target), not per term — is why the Majlis lane's 1,078 is not
higher: a member re-elected in a term the engine already recorded is invisible
to it. Recovering those needs a per-term gate, and per-term membership cannot go
through QuickStatements at all, so it is a write-path change and not a rule
change. Named here rather than folded into a number.
