---
description: Iraq national PEP landscape sweep — federal, subnational (Kurdistan, governorates), legislature, and the item-layer repairs
date: 2026-08-14
tags: [wikidata, country-sweep, iraq, kurdistan, pep]
---

# Iraq sweep

> **First execution step:** copy this file to `/Users/pudo/Code/wikidata/plans/iraq_sweep.md`
> (repo-root `plans/` is where planning docs belong per the global convention) and
> work from there.

## Context

Iraq's PEP coverage on Wikidata is minuscule and its item layer is visibly
broken. Every prior campaign (Ecuador → Qatar) has been a country whose items
existed and were empty, or whose rosters were absent. Iraq is the first that is
**both** badly covered *and* richly sourced: an Arabic roster layer that is
substantial and almost entirely unread today, because the column vocabulary and
the Iraqi/Levantine month names are not in `wd/roster.py`.

Measured live on 2026-08-14, before any code:

- **106** position items carry `P17 = Q796`, holding **781** distinct
  holder-links between them. The largest is the *Transitional* National Assembly
  (77) — a body that existed for one year in 2005.
- The **Council of Representatives** records **35** members ever, against
  329 seats × 6 parliaments since 2005, plus a 16-term monarchy-era chamber.
- **Kurdistan**: President 2 holders, Prime Minister 3, Deputy PM 1, Speaker of
  Parliament **0**, and no membership item for its 111-seat parliament at all.
- **Governorates**: 18 via `P150`; only 7 have a governor item carrying `P1001`.
- The **Central Bank** records 4 governors on the real item (`Q110490288`) and
  **10 on a `Category:` item** (`Q25167655`).

The intended outcome is one campaign — `scripts/iq_offices.py` plus its sibling
lanes — producing one additive `.qs`, its `edit_plan_claims.json` half, a
justified statement-removal script for the invalid P39s, and byproduct lists
for the item creation the country needs.

### Decisions taken before planning

| question | answer |
|---|---|
| Lane scope | **Everything**: executive spine, portfolio ministries, the 82-cabinet lane, legislature (monarchy + modern + Kurdistan), governorates, Kurdistan executive |
| `parse_date` change | **Full prescribed procedure** — pre-change capture of all 12 prior campaign runs, then diff every one |
| Kurdistan 1990s PUK/KDP rival administrations | **`era.distinct`** — distinct polities; their rows skip and become an item-creation byproduct |
| Invalid P39 statements | **A removals script**, each removal carrying its justification, `--dry` by default |

---

## 1. What the survey measured

### 1a. The item layer is a gate that would have rejected real positions

`President of Iraq` (`Q889817`) carries `P17 = Q796` but `P31 = Q248577`
(head of state), which is **not** under the `Q4164871` closure. A census gated on
`P31/P279* Q4164871` does not see the head of state of the country. This is
`recipes/country_sweep.md` §2's "type filters are unsafe as gates" reproducing
exactly — **use the census to find items, never to reject them.** The Iraq census
must union `P17`, `P1001`, and label-match, and must not filter on type.

### 1b. Channels that work today

| channel | rows / dated |
|---|---|
| `en:List of prime ministers of Iraq` | 81 / 81, clean `name` role |
| `en:List of presidents of Iraq` | 14 / 14 |
| `ar:قائمة وزراء العدل (العراق)` | **86 / 85**, split monarchy (58) + republic (28) |
| `en:Prime Minister of the Kurdistan Region` | 10 / 10 across 3 era tables |
| `en:President of the Kurdistan Region` | 4 / 4 across 3 era tables |
| `en`/`ar` kings of Iraq | 3–4 |
| `ar:قائمة وزراء الإعلام (العراق)` | 6 / 6 |

### 1c. Channels recovered by column vocabulary *alone*

Verified by patching `roster.COLUMN_ROLES` in memory and re-parsing — no other
change:

| page | before | after |
|---|---|---|
| `ar:وزارة الدفاع (العراق)` | 38 rows, **0 dated** | 38 named + 38 dated, 4 era tables |
| `ar:وزارة الداخلية (العراق)` | 11 rows, 0 dated | 11 + 11 |
| `ar:وزارة الأوقاف والشؤون الدينية` | — | 20 + 20 |
| `ar:وزارة البيئة` / `وزارة الكهرباء` | — | 14 + 14 each |
| `ar:البنك المركزي العراقي` | 25 rows, no **name** | 25 named |
| `ar:قائمة محافظي نينوى` | 88 rows, 0 dated | 88 named + 88 dated |
| `ar:قائمة رؤساء وزراء العراق` | 83 dated, no name | 83 named |

The cause is §7 #8/#11 verbatim: **`مدة العضوية` is a header colspanning two
cells** that holds start and end, and it folds to contain `مدة`, which the table
types `days` — a decoy. Both date columns were being discarded silently.

### 1d. Two parser gaps, precisely bounded

**Gap 1 — column vocabulary.** Additive entries to `COLUMN_ROLES`. Keys must be
ordered so the specific beats the generic (`مدة العضوية` → `period` must win over
`مدة` → `days`); `COLUMN_ROLES` is an ordered **list** of pairs, so prepend.

```
مدة العضوية / مدة عضوية / مدة الوزارة → period   (NOT days — this is the bug)
المحافظ أو المتصرف, المحافظ           → name
رئيس الوزراء                          → name
تاريخ المباشرة, استلام الرئاسة         → start
ترك الرئاسة                            → end
ولادة-وفاة, الحياة, الرتبة, وصف        → notes    (§7 #21: a lifespan is not a term)
الوزارات والدوائر                      → office
حزب سياسي                              → party
```

**Gap 2 — Iraqi/Levantine month names.** Unknown to `parse_date`, so the most
important lanes fall to the bare-year rule:

```
parse_date('12 حزيران 1948')        → 1948      (want 1948-06-12)
parse_date('11 تشرين الثاني 1920')  → 1920      (want 1920-11-11)
parse_date('1 كانون الأول 1958')    → 1958
parse_date('14 تموز يوليو 1958')    → 1958-07   (day lost to the dual name)
```

Two structural consequences, not just a table addition:

1. Several names are **two tokens** (`كانون الثاني`, `تشرين الأول`,
   `تشرين الثاني`, `كانون الأول`), so the day–month–year pattern must admit a
   multi-token month.
2. Pages write **both calendars adjacent** — `14 تموز يوليو 1958`. `_first_month`
   scans to the first month that resolves, finds `يوليو`, and the day is no
   longer adjacent to it. The Levantine name must resolve *first* so the day
   binds. This is §7 #26's lesson applied to a new shape.

Month set: `كانون الثاني` Jan, `شباط` Feb, `آذار` Mar, `نيسان` Apr, `أيار` May,
`حزيران` Jun, `تموز` Jul, `آب` Aug, `أيلول` Sep, `تشرين الأول` Oct,
`تشرين الثاني` Nov, `كانون الأول` Dec. Note `آب` is two letters — match whole.
Write every pattern against `wd.roster.fold` and test against folded text.

**One genuine collision to resolve, not guess.** `المدة` means *duration* on the
Kuwaiti and Saudi pages already in the table (typed `days`) and *period* on
`ar:قائمة رؤساء أركان الجيش العراقي`, where it is the only date column — 36
chiefs of staff, 0 dated. Do not flip the global mapping. Inspect the column's
content and decide between a content-sensitive refinement and a per-source
override; record which, and why, in the audit.

### 1e. Channels with no roster at all

- `ar:وزارة الخارجية (العراق)` — **0 tables.** Foreign affairs, the most
  PEP-relevant portfolio, has no roster on its ministry article.
- `ar:المحكمة الاتحادية العليا (العراق)` — 0 tables. The apex court has **no
  roster channel**; judges are officebox-or-nothing.
- Only **5 of 27** ministry articles carry a dated roster. The other ~22
  portfolios have no dedicated channel, which makes the cabinet lane not a
  bonus but the **only** path to them.

### 1f. The cabinet lane — 82 articles, the Jordan shape

`قالب:حكومات العراق` lists **82** cabinets: monarchy-era `وزارة <PM> <ordinal>`
(~67) and republic-era `حكومة <PM>` (~15). Every one sampled dates itself in its
own infobox — monarchy `التكوين`/`النهاية`, republic `تاريخ البدء`/`تاريخ الانتهاء`
— so the lane is 82 `RosterSource`s each carrying its government's span, exactly
as Jordan's 98 were.

Three shapes inside it, and the last two are new work:

1. **Republic-era tables** — `الوزارة | الوزير | الملاحظات`, or with a real
   `الفترة` column (Sudani, 25 rows). Existing vocabulary already covers these.
2. **Monarchy-era bullets** — `وزير الخارجية: نوري السعيد حتى 18 تشرين الأول
   1930، ثم شغل المنصب عبد الله الدملوجي`. `parse_bullet_rosters` territory, with
   *two* holders and an inline Levantine date in one bullet.
3. **Stacked holders inside one name cell** — Abadi's article writes
   `خالد العبيدي (2014-2016)عرفان…`: successive holders with parenthesised year
   ranges *inside* the cell. Related to §7 #17 but not the same; needs its own
   handling and its own `check_dates.py` case.

Two known costs, both already characterised by Jordan: dates are
**cabinet-precision, not tenure-precision** (the backtest will say so, and it
should), and a minister across four cabinets arrives as four rows, so
`merge_terms` does the real work and **the API half of the batch gets large**.
One new risk: `حكومة عبد الكريم قاسم` carries **six reshuffle tables**
(`التعديل الوزاري الأول…السادس`) that largely repeat the same ministers —
dedup before proposing or the same tenure ships six times.

Per §7 #38, the highest-leverage pre-flight here: **dump the whole distinct
`الوزارة`-cell tally with what each routes to, before running anything.** Match
bare stems; Arabic cabinet lists fuse the article to the preposition. End the
`section_targets` table with `(r".", "")` **and** `(r"", "")`.

Per §7 #35, **defer the sitting cabinet** (`حكومة محمد شياع السوداني`) as
Kuwait's and Jordan's were: it dates from the original appointment and collides
with its predecessor's account of the same tenure.

### 1g. Legislature

- **16 monarchy-era Chamber of Deputies rolls** (`الدورة الأولى` …
  `السادسة عشر`), tables `التسلسل | الاسم | الملاحظات` sectioned per governorate,
  **no date column** — the term is in the title, so this is the `RosterSource.term`
  lane (§7 #32), and each term's end is the next term's start. Names are mostly
  **unlinked** (2–12 wikilinks per ~30-row table), so most rows resolve to no
  item: expect a large **item-creation byproduct list and few statements**, and
  report it that way rather than relaxing the identity gate.
- **Modern CoR**: `قائمة أعضاء مجلس النواب العراقي (2005-2010)` is bullet lists
  per bloc (~130 wikilinked names reachable), and `…العراقي 2018` is a 74-row
  election-results table with an `إسم النائب` column. Terms 2010, 2014, 2021 and
  2025 have no roll — a real gap to report, not to paper over.
- Also present and unmodelled: `المجلس التأسيسي للمملكة العراقية` (1924),
  `مجلس الأمة العراقي`, and `مجلس الأعيان العراقي` — **a Senate**.
- **Kurdistan**: `قائمة أعضاء برلمان إقليم كردستان (2013–2019)`, 112 rows,
  `party | name`, no dates → `term=` lane. No membership item exists.

The Kingdom's chamber is **not** the post-2003 Council of Representatives
(`Q21328603`, whose `P361` is `Q1973075`). It needs its own item; `era.distinct`
handles the rows that are not it, and no rule can invent the item.

### 1h. Subnational

`P150` gives 18 governorates (Halabja, created 2014, is missing from it — check
separately). Seven have a governor item with `P1001`; Basra and Najaf have items
**without** `P1001`. So Iraq's own convention is inconsistent, unlike Saudi's
uniform provincial `P1001`. **Measure it with `wd/precedent.py` before minting
the ~11 missing items** — minting to the wrong shape makes them siblings of
nothing.

`ar:قائمة محافظي نينوى` yields 88 governors with start dates only, and the name
cell carries the honorific inline (`المحافظ عبد القادر الدخيل`, and `المتصرف`
for the Ottoman-era holders — an `era.distinct` marker, not a name part). Strip
the honorific; do not let it into `names_match`.

---

## 2. Lanes

| lane | shape | expectation |
|---|---|---|
| **A** Executive spine | PM, President, King, VP, Deputy PM | ~110 rows, clean; the backtest's calibration set |
| **B** Portfolio rosters | justice (86), defence (38), awqaf (20), environment (14), electricity (14), interior (11), information (6) | ~190 rows once vocabulary lands; era-sectioned |
| **C** Cabinet lane | 82 `RosterSource`s, bucket routing over `الوزارة` stems | the volume, and the only channel for ~22 portfolios; large API half |
| **D** Central bank + military | CBI 25, chief of staff 36 | CBI needs the month fix; chief of staff needs the `المدة` call |
| **E** Legislature | 16 monarchy rolls, 2 modern rolls, Senate, constituent assembly, Kurdistan parliament | creation-first; byproduct-heavy, few statements |
| **F** Governorates | 18 governorates, 7 items, Nineveh roster of 88 | creation-first after measuring the `P1001` convention |
| **G** Kurdistan executive | President, PM, Deputy PM, Speaker, KRG ministries | 14 clean rows + `era.distinct` for the 1990s split |
| **H** Repairs | invalid P39 statements | a justified removals script, not batch lines |

**Explicitly out of scope for run 1:** ambassadors (a large existing lane with
its own archetype — Iraq is the *receiver* in most existing items, so it is a
separate campaign), SOE and sovereign-wealth leadership (creation-first per the
recipe, and Iraq has no dedicated items), tribal and clerical offices
(`بابا شيخ`, `Sheikh Mashayekh Anizah`), and armed-group leadership items
(`Emir of Al-Qaeda in Iraq`) which are not PEP positions.

There is **no dynastic lane**. Iraq's monarchy ended in 1958 and the Hashemite
genealogy already ran under Jordan (`scripts/jo_family.py`, `en:Hashemites`);
`wd/kinship.py` is not needed here. Confirm no Iraqi-branch gap remains before
closing the lane.

---

## 3. Sub-agent fan-out

The lanes are independent and each owns its own verdict file
(`data/iraq/verdicts/iraq_<key>.jsonl`, governed by `manifest.json`), so
**research and configuration parallelise cleanly**. Two things do not, and
getting the barriers right is the whole design:

- **`wd/roster.py` is shared state.** The vocabulary and month work is *one*
  change with *one* owner. Parallel agents editing it would conflict, and the
  pre-change capture only means something if a single controlled change sits
  between capture and diff. **Serial, one owner, no exceptions.**
- **The render is a single serial step.** One campaign is one batch; the `.qs`
  and `edit_plan_claims.json` are two halves of one review.

```
Phase 0  SERIAL   pre-change capture: run all 12 prior campaign scripts,
                  snapshot data/<campaign>/verdicts → data/_prechange/<campaign>/verdicts
                  (saudi and jordan need BOTH offices and family scripts)
                     │
Phase 1  FAN OUT  7 read-only survey agents, one per lane A–G, each returning
                  a measured lane report + a proposed Office/RosterSource block
                  + the vocabulary keys and date shapes it needs
                     │
Phase 2  SERIAL   the parser change (one owner): COLUMN_ROLES + Levantine months
                  + the المدة call + the stacked-name-cell shape;
                  extend scripts/check_dates.py with every new case;
                  diff_verdicts.py against the Phase-0 capture, per campaign
                     │  ← any diff is stop-and-report, not fix-and-continue
Phase 3  SERIAL   write scripts/iq_offices.py from the Phase-1 reports;
                  add "iq" to SCRIPTS in scripts/create_offices.py;
                  create_offices.py --country iq (dry) → --apply  [HUMAN GATE]
                     │
Phase 4  SERIAL   run the sweep; read data/iraq/roster_audit.md — ## Backtest first
                     │
Phase 5  FAN OUT  per-office backtest triage: agents read the audit and report
                  whether a low target-agreement office is a family of items
                  (§2a) or a routing bug — one office each, read-only
                     │
Phase 6  SERIAL   render_edit_plan.py; validate; the two batch halves  [HUMAN GATE]
                     │
Phase 7  SERIAL   removals script + justifications  [HUMAN GATE, after the adds]
```

Phase-1 agent contract, per the recipe's verification-agent convention: **one
lane each, read-only, cite evidence, prefer "unclear" over guessing, never
edit**, write findings to a file and return only counts plus notable calls. Use
`model: "opus"` for the judgment-heavy lanes (C's routing table, E's era
questions, F's convention measurement).

One caution from the recipe: **parallel agents converge on whoever answered
first.** Lanes B, C and F will each form an opinion about era boundaries and
about which portfolio item a stem routes to. Cross-check those calls across lane
reports in Phase 3 rather than trusting the first one written.

---

## 4. Campaign parameters

New file `scripts/iq_offices.py`, closest precedents `scripts/jo_offices.py`
(the cabinet bucket lane and its ~60-entry stem table) and `scripts/qa_offices.py`
(Arabic-first, sparse rosters, creation lane).

- `name="iraq"`, `country_qid="Q796"`, `label_langs=("en","ar")`,
  `sibling_wikis=("ar","en","ckb")` — `ckb` (Sorani) for the Kurdistan lanes.
- `modern_from=1921` (the state's founding). Its only job is selecting which rows
  the census is asked about; **early terms are decided by each target's own
  record** via `early.precedent_ok` / `early.unsupported`. Expect monarchy-era
  rows to fail on most ministry items and pass on the throne.
- `regime_sections` per office for the four polities the rosters themselves
  separate: Kingdom 1921–58, Republic 1958–68, Ba'athist Republic 1968–2003,
  post-2003 Republic. `ar:قائمة وزراء العدل` names them in its own headings
  (`وزارة العدلية في العهد الملكي` / `وزراء العدل خلال العهد الجمهوري`).
  **Route by the row's section, never by the person** — Iraqi careers cross
  regimes routinely.
- `continuous_eras` — deliberately **narrow**. The post-2003 Republic and the
  1968–2003 Republic are arguably one institution; the **Kingdom is not**, and
  neither is the CPA/interim period. Whatever is chosen is declared **once**,
  here, and never per person.
- `date_targets` where a portfolio's item changes across eras (§2a); an empty QID
  means "no item exists for this era" and files the row as a creation byproduct
  rather than under the nearest item that happens to exist.
- `section_targets` for the cabinet bucket — bare Arabic stems, ending
  `(r".", "")` and `(r"", "")`.
- `concurrency_ignore` naming every seat whose overlap means nothing: CoR and
  Kurdistan Parliament membership, and the genuinely concurrent Iraqi pattern of
  a PM holding Defence or Interior in his own person (Qasim was PM **and**
  Defence Minister; Sudani's deputies hold portfolios). Without this,
  `interim_of` stamps `P2868` on real appointments.
- `jurisdiction` per governorate office (`P1001 = <governorate>`) — **only if**
  Phase 1F measures that as Iraq's convention.
- `generic_targets` naming the generic items so the sweep does not propose a
  redundant statement beside one (`Q17763739` justice minister, `Q2632935`
  minister of state, `Q83307` minister, `Q486839` member of parliament, …).
- `dispositions` mapping every non-applying rule to `skip`:
  `namesake`, `predecessor_body`, `category_only`, `no_dates`, `believed.held`,
  `uncertain`. `edit_plan.md` is an account, not a queue.

---

## 5. The removals lane (H)

New: `scripts/iq_removals.py` → `data/iraq/removals.md` + `removals.json`, and
`scripts/apply_removals.py --campaign iraq`, `--dry` by default, shelling
`wb remove-claim <guid>` one GUID at a time behind a `removals_written.json`
ledger and relaying stderr. Statement removal is destructive, so this **stops and
asks** — the script decides and justifies; the human runs it.

**Ordering is load-bearing: the additive batch goes in first.** Removing the
wrong statement before the right one exists leaves the person with no P39 at all.

Classify, and do not lump — this is the difference between a defect and a
community disagreement:

- **Class 1 — structurally invalid, a `Category:` item as a position.**
  `Q25167655` "Category:Governors of the Central Bank of Iraq", `P31 = Q4167836`,
  held by **10** people. A category is not a position. Unambiguous.
- **Class 2 — structurally invalid, a *body* as a position.** `Q1973075` Council
  of Representatives (`P31 = Q37002670`, a legislature) ×5; `Q6867009` Ministry
  of Foreign Affairs ×3; `Q61958669` Ministry of Municipal and Rural Affairs ×5.
  An organisation is not a position.
- **Class 3 — contested, and NOT to be removed by default.** Generic role items:
  `Q17763739` justice minister ×36, `Q2632935` minister of state ×34,
  `Q10540834` agriculture minister ×32, `Q7614320` finance minister ×24,
  `Q486839` member of parliament ×18, `Q83307` minister ×11. These are used
  across all of Wikidata as fallbacks and often carry qualifiers that make them
  meaningful. Removing ~150 of them is a position the community has not taken.
  Emit them as a **separate, clearly-labelled proposal section** behind an
  explicit flag, with the specific item that should replace each — and let
  `generic_targets` stop the sweep proposing beside them meanwhile.

Every row in `removals.md` carries: subject QID + label, the statement's GUID,
the offending value + its `P31`, the reason it is invalid, and — for classes 1
and 2 — the correct statement that now exists in its place.

Get the GUIDs from `wd/api.py:fetch_entities` with `max_age=0`, never through the
seven-day cache: this reads Wikidata's *state*, which is exactly what the
campaign's own writes change.

---

## 6. Files

| path | change |
|---|---|
| `plans/iraq_sweep.md` | this document, moved into the repo |
| `wd/roster.py` | `COLUMN_ROLES` prepends; Levantine month names in `parse_date`; multi-token months; the dual-calendar day-binding fix; the `المدة` call; the stacked-name-cell shape |
| `scripts/check_dates.py` | a case for every new date shape above, plus the ones that must **keep** their current answer |
| `scripts/iq_offices.py` | new — lanes A, B, C, D, F, G |
| `scripts/iq_legislature.py` | new — lane E's term rolls, joining via `extra_verdicts` |
| `scripts/iq_removals.py`, `scripts/apply_removals.py` | new — lane H |
| `scripts/create_offices.py` | add `"iq": "iq_offices"` to `SCRIPTS` |
| `tasks/followups.md` | byproducts: item-creation lists, the class-3 proposal, deferred lanes |
| `regression/iraq/` | after acceptance: `verdicts/`, `manifest.json`, both batch halves, a `README.md` row |

Reuse, do not rewrite: `wd/campaign.py:run`, `office_rows`, `identify`,
`target_for`, `holders` (with `STATE_MAX_AGE`), `wd/policy.py:decide`,
`wd/backtest.py:score`/`report`, `wd/precedent.py:census`,
`wd/validate.py:check`/`collapsing_groups`, `wd/write.py:Ledger`/`edit_entity`,
`scripts/render_edit_plan.py`, `scripts/apply_claims.py`,
`scripts/diff_verdicts.py`.

---

## 7. Verification

1. **`scripts/check_dates.py` passes** before and after every `parse_date` touch,
   with the new Iraqi cases *and* every pre-existing case unchanged — especially
   the Hijri ones, which must keep yielding nothing.
2. **`diff_verdicts.py --campaign <each>` against the Phase-0 capture is empty**
   for all 12 prior campaigns. Any diff stops the session and gets reported, not
   fixed in passing.
3. **Read `## Backtest` at the head of `data/iraq/roster_audit.md` first.** Target
   agreement below ~90% on an office means it is a family of items and the
   routing is guessing (§2a) — not a reason to ship. Read the bolded `conflict`
   column, not the percentage: a coarse recorded date is agreement written
   differently. **A whole office at 0% date agreement is a comparison bug before
   it is a parser bug.**
4. **Read `roster_audit.md` end to end**, including every skipped table and every
   `no identity` row. Every matcher this workbench has built was too loose on the
   first pass.
5. **`render_edit_plan.py` refuses to render on a defect** — a duplicate line, a
   `start > end` (expect RTL-reversed ranges in Arabic tables, §7 #29; defer the
   lane rather than adding a global swap), a malformed value. Read its warnings
   too: a year-precision date beside day-precision ones on the same item means a
   cell failed to parse.
6. **Spot-check the two batch halves against Wikidata live** before the human
   gate: for a sample of lines, does a statement with that subject, property,
   value *and dates* already exist? Read with `max_age=0`.
7. **`apply_claims.py --campaign iraq` dry first**, and confirm
   `claims_written.json` is in place — the API de-duplicates nothing, so a second
   run without the ledger doubles every tenure.
8. **`apply_removals.py` dry first**, and only after the additive batch is in.

## 8. What this run should be judged on

Given the calibration table, Iraq is an **empty-item, rich-roster** country and
should land in the Kuwait band rather than the Czechia one. But three lanes are
honestly creation-first (legislature, governorates, Kurdistan parliament) and
one has no channel at all (the Federal Supreme Court), so the deliverable is
deliberately two-sided: a substantial batch **and** a substantial byproduct list.
Per the standing rule, a lane with one weak channel gets **reported small rather
than padded** — the monarchy-era legislative rolls in particular will yield far
more redlinks than statements, and that is the correct outcome, not a failure.
