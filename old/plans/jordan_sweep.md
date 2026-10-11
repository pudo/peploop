---
description: Jordan country sweep — Hashemite kinship lane, throne, cabinet ministers via 109 per-cabinet Arabic articles, and the parliamentary presiding offices
date: 2026-08-13
tags: [wikidata, country-sweep, jordan, kinship, arabic-rosters]
---

# Jordan sweep

Method lives in `recipes/country_sweep.md`; this document holds what the survey
measured for Jordan and the decisions that followed.

**Run 2026-08-13. Outcome: 275 applying records — 210 statements via
QuickStatements and 159 via the API for 59 people with several tenures in one
office.** Baselined in `regression/jordan/`; byproducts and defects in
`tasks/followups.md`. What the survey got wrong is recorded under
"What the run changed" at the foot of this document.

## Context

Jordan is the seventh country sweep and the repo's first Jordanian material of any
kind — a clean greenfield (no `tasks/`, `recipes/`, `plans/`, `data/` or cache hit
for "jordan"/"hashemite"/"Q810"). It is requested with a priority order: **family,
senior PEPs, royals, then parliamentary positions.**

The survey below broadly supports that order but relocates the *volume*: the family
and throne lanes are real and small, while the ministerial lane turns out to be the
highest-yield thing in the country — 40 near-empty ministry items against ~109
per-cabinet Arabic articles that tabulate office, holder and dated start/end. That
is the "Ecuador profile" (items exist, nearly empty) with a genuine dated channel,
the highest-yield shape in the calibration table. The user has confirmed taking the
full cabinet lane.

Deliverable, as always: one `data/jordan/edit_plan.qs` plus its
`edit_plan_claims.json` half, reviewed together.

## What the survey measured

All figures from live SPARQL / MediaWiki API on 2026-08-13.

### Coverage

| measure | Jordan | comparator |
|---|---|---|
| people with `P27 = Q810` | 2,622 | UAE 1,876 |
| of those carrying any P39 | 372 | UAE 120 |
| position items scoped `P17 = Q810` | 91 | |
| holder statements across them | 494 | Czechia 14,124 |
| …of which other states' ambassadors *to* Jordan | 25 items / 96 statements | not the lane |
| …of which university / church offices | 8 items / 18 statements | not the lane |
| **the actual national-PEP lane** | **~58 items / ~380 statements** | |

Counted with `p:P39/ps:P39`, never `wdt:P39`.

Date-qualifier coverage on the offices that matter — this is what a sweep adds:

| item | office | stmts | with P580 | with P582 |
|---|---|---|---|---|
| Q17524418 | Member of the House of Representatives | 84 | 13 | 13 |
| Q20081407 | Senator | 83 | 20 | 18 |
| Q7243300 | Prime Minister | 42 | 38 | 37 |
| Q20716373 | Minister of Foreign Affairs | 37 | 24 | 23 |
| Q110065338 | Minister of the Interior | 8 | 8 | 7 |
| Q115345222 | Consort of Jordan | 6 | 3 | 2 |
| Q105531070 | Speaker of the House | 5 | 5 | 4 |
| Q14625123 | King of Jordan | 4 | 4 | 3 |
| Q113330973 | Deputy Prime Minister | 4 | 4 | 1 |
| Q6594880 | President of the Senate | 3 | 3 | 2 |
| Q25463341 | Chairman of the Joint Chiefs | 2 | 2 | 1 |
| Q110068356 | Governor of the Central Bank | 2 | 2 | 1 |
| Q130265327 | Director of General Intelligence | 2 | 2 | 2 |
| Q54900644 | Crown Prince | 1 | 1 | 1 |

The ~40 ministry items in the `Q110065338`–`Q110068001` range were bulk-created and
carry **1–8 holders each**. That block is the campaign's centre of gravity.

### Channel: Arabic vs English (category members, depth 0)

| lane | en | ar |
|---|---|---|
| Kings | 5 pages + 1 subcat | 7 pages + 1 subcat |
| Royalty | 2 pages + **6 subcats** | *missing* |
| Prime ministers | 45 | 45 |
| Government ministers | 1 page + **46 subcats** | **190 pages** + 41 subcats |
| House of Representatives members | 58 + 1 | **114** + 1 |
| Senate members | ***no category at all*** | **156** + 1 |

**The channel splits by lane, which is unusual.** Arabic is decisive for the
legislature (the Senate has no English category whatsoever — the Kuwait pattern)
and for ministers; English is the only channel for the royal family (`ar` has no
royal-family category, and the genealogy article is `en:Hashemites`). Both wikis
subdivide ministers by portfolio (46 en / 41 ar), so the bucket lane is mechanical.

Jordan has **no per-term legislature subcategories** — unlike Kuwait's 22, which
produced 936 `category_only` rows. Each legislature category has exactly one
subcat, the presiding officers.

### Rosters found, and whether they parse *today*

Roles below are the real output of `wd.roster._roles` run on each page's actual
header row — not inspection. This is §7 #24 discipline applied up front.

| page | rows | header → role | verdict |
|---|---|---|---|
| `ar:رئيس وزراء الأردن` t3 | **78** | name / start / end / portrait | **parses clean** |
| `ar:حكومة <PM>` × ~109 | 85 (Khasawneh) | office / name / start / **`غادر المنصب` → no role** | **every row open-ended** |
| `ar:وزارة الداخلية (الأردن)` t1 | 13 | portrait / name / period / party / – / notes | parses |
| `ar:قائمة رؤساء مجلس النواب الأردني` t1 | **34** | – / name / start / end / – | **parses clean** |
| `ar:مجلس الأعيان الأردني` t2 | **28** | – / **`الرئيس` → no role** / period / period / – / – | **all 28 rows dropped** |
| `ar:قائمة أعضاء مجلس الأعيان … السابع والعشرين` t3 | **69** | **`عضو` → no role** / – / **oath date → no role** | **total loss** |
| `en:List of prime ministers of Jordan` t0 | 82 | ordinal / portrait / name / – / period / – / – | parses (corroborating) |
| `en:Cabinet of Jordan` t1 | 30 | Portrait / Office / Incumbent | **no date column** — portfolio discovery only |
| `ar:مجلس النواب الأردني <term>` | 16 | election results (votes, list, district) | **not a member roster** |

Two of these are §7 #24 silent total losses and one loses every end date. They are
the parser work, and they are small and precisely identified.

Notably absent: **there is no dedicated per-portfolio roster list-article in either
language** (no `قائمة وزراء الخارجية الأردنيين`, no `List of ministers of foreign
affairs of Jordan`). The cabinet articles are the ministerial channel; there is no
tier-1 source to fall back on.

## §2a — is each office one item or several?

- **Crown Prince is two items competing for the same era**: Q54900644 "Crown Prince
  of Jordan" (1 holder, en label) and Q60061190 "ولي العهد (الأردن)" (0 holders).
  Per the recipe that is a **merge decision, not a campaign** — declare no office,
  put it on `tasks/followups.md` as surgical. Do not route holders to either until
  it is resolved.
- **King of Jordan** (Q14625123) carries no `P17`, so it is invisible to the P17
  census — found by search. Same for the Emirate of Transjordan era, which has no
  distinct item; pre-1946 rows route to `""` via `date_targets` and become creation
  byproducts rather than being filed under the Kingdom's throne.
- The ministry items are a **rename chain, not a succession to route by date** in
  most cases — but several pairs are clearly duplicates rather than eras
  (`Q110066504` "Minister of Labour" vs `Q133851928` "Minister of Labor";
  `Q110065394` "Minister of Water and Irrigation" vs `Q137704254` "وزير المياه
  والري"; `Q110257013`/`Q110067675` ICT vs Digital Economy). Let
  `wd.backtest.observed_family` derive the family from the cohort and let
  `already_under_sibling` → `duplicate_office_item` protect the batch; send the
  confirmed duplicate pairs to followups as merges.
- Jordan's cabinets rename portfolios constantly, so expect a large share of the
  ~50 distinct `المنصب` values to route to `""`. That is correct behaviour and
  becomes the creation byproduct list — **never map an unproven rename.**

## Item-layer defects (surgical → `tasks/followups.md`, never batch lines)

- Q54900644 / Q60061190 — duplicate Crown Prince items, merge.
- Q110066504 / Q133851928 — duplicate Labour ministry items.
- Q110065394 / Q137704254 — duplicate Water & Irrigation items.
- Q6597909 "list of speakers of the House of Representatives of Jordan" — a **list
  article carrying 2 P39 holders**, the Q20388005 shape from Saudi.
- Q136223044 `وزير شؤون الأرض المحتلة` and Q136650633 `عضو في مجلس النواب الأردني`
  — Arabic-only labels duplicating English-labelled items (Q17524418 for the
  latter); check and merge.
- Q14625123 "King of Jordan" has no `P17` — add `P17 = Q810`.

## Lanes

Ordered as requested. Yields below are **estimates from row counts against recorded
coverage**, not promises; the calibration table's warning applies — where items are
already dense the useful output is byproduct lists and parser hardening.

### Lane A — the Hashemite family (kinship, `extra_verdicts`)

The lane the user put first, and it is viable — which was not obvious. `en:Hashemites`
uses **93 `{{tree chart}}` templates**, the markup that forced Kuwait to abandon its
House of Sabah lane. But those are confined to the *Ancestry* and *Main branch*
sections (the medieval Sharifian lineage, which the lane does not need). The three
sections that matter are **nested `*` lists**, the shape `wd/kinship.py` already reads:

| section | list lines | wikilinked | couple-lines | max depth |
|---|---|---|---|---|
| Descendants of King Hussein of Jordan | 34 | 17 | 3 | 3 |
| Descendants of King Talal of Jordan | 19 | 9 | 4 | 3 |
| Descendants of King Abdullah I of Jordan | 18 | 5 | 1 | 3 |
| Main branch | 6 | 6 | 2 | 3 |

**37 of 77 lines carry a wikilink.** The other 40 — mostly unlinked grandchildren
("Princess Haya (The King's half-niece)") — are a bare name match, which the
two-axes rule forbids as a lone channel. They become the item-creation byproduct
list, not a padded lane.

Ancestor/house: `Q1774915` Hashemites (P53 value). Second channel for P53 comes
from the en royalty subcategories: *Princes of Jordan*, *Jordanian princesses*,
*Jordanian royal consorts*, *Kings of Jordan*, *Mothers of Jordanian monarchs*.
**Exclude `Recipients of Jordanian royal pardons`** — it is in the royalty tree and
names people who are not royals at all.

Two shapes `wd/kinship.py` does not read today (user approved extending it):

1. **The mother is a level-1 bullet, not a section heading.** Saudi's article heads
   a section per wife; Jordan lists `*Queen Noor (King Hussein's fourth wife and
   widow)` with her children at `**`. The bullet closes the candidate set exactly
   the way a heading does — that is the assertion — so `mother_records` needs to
   accept a bullet-rooted group alongside a heading-rooted one.
2. **A line names a couple**: `**[[Hamzah bin Al Hussein|Hamzah]] and [[Princess
   Basmah Hamzah|Princess Basmah]] (…)`. Their children sit at `***`. Split the
   pair: `P26` between them, and children take `P22` from the male and `P25` from
   the female by `P21`. The blood descendant is listed first (the parenthetical
   marks the other as an in-law), but resolve father/mother by `P21`, not by order.

One new failure mode to record in §4a, because it would ship silently:

> **The parenthetical describes a different relation from the nesting.** Under
> "Descendants of King Hussein", Hamzah is nested beneath Queen Noor — she is his
> mother — but is annotated "(The King's half-brother)", relative to the *reigning*
> king, Abdullah II. A parser trusting the parenthetical emits sibling edges where
> the article asserts parent edges. **The nesting is the assertion; the
> parenthetical is a distractor.** Read structure, never the gloss.

`P40`, `P3373` and prose-derived `P26` stay unemitted per the standing decision —
except the couple-line `P26`, which is structural rather than prose, and should be
gated on both halves resolving to items.

### Lane B — the throne and royal offices

Small and largely finished; run it for completeness and for the backtest signal.

- King of Jordan `Q14625123` — `en:List of kings of Jordan` (7.5 KB). 4 statements,
  all dated. Expect ~0–4 adds.
- Consort of Jordan `Q115345222` — 6 statements, 3 dated.
- Crown Prince — **no office declared** (see §2a); blocked on the merge.
- Pre-1946 Emirate of Transjordan → `date_targets = ((None, 1946, ""),)`.

### Lane C — the government (senior PEPs, the volume)

**C1 — Prime Minister** `Q7243300`. Source is `ar:رئيس وزراء الأردن` t3 (78 rows,
parses clean today), with `en:List of prime ministers of Jordan` t0 (82 rows) as the
corroborating second channel. 42 statements recorded, 38 dated, so the yield is
modest — but Jordanian PMs are re-appointed heavily (Wasfi Tal, Zaid al-Rifai, Ibrahim
Hashem all serve several separated terms), so expect a **large `edit_plan_claims.json`
half**, Kuwait-scale or larger. On the en page beware `King(Reign)` and `Election`,
both date-bearing decoy columns — currently inert (no role), and they must stay so.

**C2 — the cabinet lane, ~109 articles.** `Category:حكومات الأردن` holds 111 members
(~109 cabinet articles plus a template and a category). Each tabulates
`المنصب ¦ شاغل المنصب ¦ تولى المنصب ¦ غادر المنصب` — office, holder, dated start,
dated end. Khasawneh's alone is 85 rows.

- One `Office` with ~109 `RosterSource`s, routed by a `PORTFOLIOS` `section_targets`
  map against the `المنصب` cell — the Saudi `sa_offices.py` shape, ~50 entries,
  specific before general, `""` for unproven renames, `(r".", "")` catch-all last.
- Build the map by first harvesting the distinct `المنصب` values across all 109
  pages and tallying them; do not hand-write it from `en:Cabinet of Jordan` (30 rows,
  undated, current cabinet only — it is portfolio *discovery*, not a roster).
- `الحزب` on the ministry tables → `P102`, as in Czechia phase 7b.
- Expect heavy attrition: no-item portfolios, people with no item, `category_only`.
  This is nonetheless the largest lane by a wide margin.

**C3 — ministry articles** (e.g. `ar:وزارة الداخلية (الأردن)`, 13 rows, parses).
A second, independent channel per portfolio for the ~40 ministries that have one.
Weakest tier (§4), so treat as corroboration for C2 rather than a primary source.

### Lane D — parliamentary positions

The presiding offices are the win here; the seats are not.

- **President of the Senate** `Q6594880` — 3 statements recorded against **28 rows**
  on `ar:مجلس الأعيان الأردني` t2. Blocked today (no name column). Best
  statements-per-row ratio in the campaign.
- **Speaker of the House** `Q105531070` — 5 recorded against **34 rows** on
  `ar:قائمة رؤساء مجلس النواب الأردني`. Parses clean today.
- **Senate members** `Q20081407` — 83 statements, only 20 dated. The 27th Senate roll
  (`قائمة أعضاء مجلس الأعيان الأردني السابع والعشرين`, 69 rows) carries an oath date
  per member **and** a party column → P39 + P102. Blocked today (no name column, no
  date role). Only one term of ~27 has such a roll; the ar category's 156 members are
  otherwise `category_only` → skip, and become a byproduct list.
- **House members** `Q17524418` — 84 statements, 13 dated. The per-term articles are
  **election-result tables** (candidate votes, list votes, `الدائرة الإنتخابية`,
  governorate), not member rosters, and only 3 of 20 terms have one. **Declare no
  member office**; the ar category's 114 members are a `category_only` byproduct.
  Report this lane small — it is the honest finding, and padding it is what the
  conservatism rule forbids. (`الدائرة الإنتخابية` would be `P768` if a real roster
  ever appears.)

### Lane E — security, central bank, intelligence (survey only)

`Q25463341` Chairman of the Joint Chiefs (2), `Q130265327` Director of General
Intelligence (2), `Q110068356` Governor of the Central Bank (2). No roster located
in this survey. Probe for one; if none, record as a deferred lane in followups
rather than declaring an office that yields nothing.

## Parser work

### `wd/roster.py` — four keys and one refinement

Measured, not guessed. Each is currently a silent loss:

| add | role | unblocks |
|---|---|---|
| `غادر` (`غادر المنصب`, "left office") | `end` | **the entire cabinet lane's end dates** — ~109 pages currently parse open-ended |
| `الرئيس` (folds to `الرييس`) | `name` | the 28-row Senate presidents table, all rows currently dropped |
| `عضو` ("member"; `العضو` exists, `عضو` does not whole-match) | `name` | the 69-row 27th Senate roll |
| `تاريخ اليمين` ("oath date") | `start` | the same roll's dates |

Plus: `ar:مجلس الأعيان الأردني` heads its two date cells `فترة الاستلام: من` and
`فترة الاستلام: إلى`, and **both currently resolve to `period`**. Verify whether two
adjacent `period` columns already split into start/end (§7 #3 says a role may occupy
several columns and all values are kept); if not, refine via `_subroles` the way
Kuwait's `فترة تولي المنصب` sub-header was handled.

Confirm inert-and-should-stay-inert: `عدد الأعضاء`, `الدورات`, `الحكومة`,
`King(Reign)`, `Election`. None currently takes a date role; a careless prefix key
could pull them in.

Watch `الاسم (مواليد–وفاة)` on the ministry tables and `Name(Birth–Death)` on the en
PM list — lifespan inside the name cell, §7 #10.

### `wd/kinship.py` — two shapes

Bullet-as-mother and couple-line splitting, per Lane A. This is a shared module, so
the change must be pinned in `scripts/check_dates.py` and the other campaigns
re-checked (see Verification).

## Files

**New**
- `scripts/jo_offices.py` — the campaign profile (offices, `PORTFOLIOS`,
  `dispositions`, `concurrency_ignore`, `Campaign`). Copy `scripts/sa_offices.py`
  for the `section_targets` shape and `kw_offices.py` for the Arabic-source shape.
- `scripts/jo_family.py` — the kinship lane, on `scripts/sa_family.py`. Writes
  `verdicts/jordan_family.jsonl`, owned via `Campaign.extra_verdicts`.
- `plans/jordan_sweep.md` — this document.
- `regression/jordan/` — the baseline, once the run is accepted.

**Modified**
- `wd/roster.py` — the four column keys + the `فترة الاستلام` refinement.
- `wd/kinship.py` — bullet-as-mother, couple-lines.
- `scripts/check_dates.py` — pins for every new key and both kinship shapes.
- `scripts/create_offices.py` — add `"jo"` to `SCRIPTS` if a creation lane is declared.
- `recipes/country_sweep.md` — §4a gains the parenthetical-vs-nesting failure mode;
  §7 gains the `غادر المنصب` and `الرئيس`/`عضو` cases.
- `tasks/followups.md` — item-layer defects, merges, byproduct lists.

Reuse, do not re-implement: `wd.campaign.run`, `wd.policy.decide`,
`wd.backtest.{compare,score,observed_family,report}`, `wd.validate.{check,
collapsing_groups}`, `wd.precedent.census`, `wd.roster.{parse_rosters,merge_terms,
names_match,fold}`, `wd.write.{edit_entity,Ledger}`.

## Order of work

Checkpoint and report after each numbered step; do not thread them together.

1. **Parser hardening.** Add the four `roster.py` keys, resolve the two-`period`
   question, extend `kinship.py`. Pin everything new in `scripts/check_dates.py`,
   then run it. **Stop and report.**
2. **Re-check the other campaigns** against the changed engine — see Verification.
   **Stop and report** before writing any Jordan profile.
3. **Harvest the `المنصب` vocabulary** across the ~109 cabinet articles and tally it;
   write `PORTFOLIOS` from the tally. **Stop and report** the mapped/unmapped split.
4. **Lane A + B** — `jo_family.py` and the throne offices. Read
   `data/jordan/kinship_audit.md` in full before proceeding.
5. **Lanes C + D** — `jo_offices.py`. Read the `## Backtest` section of
   `data/jordan/roster_audit.md` first, then the audit itself end to end.
6. **Creation lane**, if declared — `create_offices.py --country jo` dry, then
   `--apply` (human gate). Creation runs *before* the sweep that references the items.
7. **Render** — `render_edit_plan.py --retrieved <today> --campaign jordan`.
8. **Baseline** — copy verdicts, `manifest.json`, `edit_plan.qs` and
   `edit_plan_claims.json` to `regression/jordan/`; add the row to
   `regression/README.md`.

The batch itself, `apply_claims.py --apply`, `create_offices.py --apply`, and every
merge on the defects list remain human gates.

## Verification

Run with `/Users/pudo/.python/wrangle/bin/python` — never `uv run`, never install.

- **`scripts/check_dates.py`** is the primary net. Per `regression/README.md`, all
  nine batches are now live, so *"diffs clean" has stopped being available as a
  signal* — every baseline diffs large because a re-run correctly drops records
  whose statements now exist. `check_dates.py` pins parsing and merging directly and
  does not depend on live state; every new column key and both kinship shapes get a
  case there.
- **`scripts/diff_verdicts.py --campaign <c>`** for all seven prior campaigns anyway
  — but read the diffs the slow way the README prescribes: check by hand that each
  vanished record's statement is genuinely on Wikidata, rather than treating a
  non-empty diff as a regression. Saudi needs **both** `sa_offices.py` and
  `sa_family.py` re-run or `saudi_family.jsonl` reads as a wholesale delete.
- **The backtest is the campaign's self-check.** Read `## Backtest` before anything
  else. Target agreement below ~90% on an office means the routing is guessing and
  the office is a family of items — expect this on the ministry duplicates. A whole
  office at 0% date agreement is a comparison bug before it is a parser bug.
- **`wd/validate.py` gates the render** — it refuses duplicates, `start > end`, and
  any surviving collapsing group. If it refuses, the fix is the profile or the
  parser, never a relaxed check.
- **Spot-check the two blocked tables after the parser change**: `ar:مجلس الأعيان
  الأردني` must yield 28 named rows (currently 0) and the 27th Senate roll 69
  (currently 0). Those two numbers are the parser work's pass/fail.
- **Read `roster_audit.md` end to end** before rendering, per §7. Every matcher this
  workbench has built was too loose on the first pass.

## Explicitly out of scope

- House of Representatives **seats** — no member roster exists; byproduct list only.
- The Crown Prince office — blocked on a merge, which is a human gate.
- Ambassadors *to* Jordan (25 items) and university/church offices (8) — not the
  national PEP lane.
- The medieval Sharifian lineage in `en:Hashemites` (`{{tree chart}}`) — out of
  reach, as with Kuwait's House of Sabah. If the tree-chart reader is ever built it
  unlocks both at once; that is its own task, not this campaign's.


## What the run changed

Three of the survey's load-bearing claims did not survive contact.

**The cabinet lane is real but far thinner than the survey implied, and dated
differently.** The survey generalised from `ar:حكومة بشر الخصاونة` — 85 rows with
`المنصب ¦ شاغل المنصب ¦ تولى المنصب ¦ غادر المنصب`. That shape covers **2 of 108
cabinets**. The other 106 print a bare `الاسم ¦ المهام الوزارية` and date nothing;
`المهام` took no column role at all, so 76 of them parsed as names attached to
nothing. What rescued the lane was each article's own infobox (`التكوين` /
`النهاية`), making it the §7 "the page *is* one term" shape: 98 cabinets with a
span, 1,824 rows. The cost is honest and worth restating — **the dates are
cabinet-precision, not tenure-precision**, and the backtest scores that lane 75%
on dates against 100% on every office that has a real date column.

**The portfolio map could not be written from titles.** The cells are accusative
with the definite article fused to a preposition (`وزيرا للعدل`, where `للعدل` is
لِ + العدل), in 630 distinct spellings of about fifty portfolios across a century.
Patterns carrying the article left 433 rows unrouted. Two further order bugs came
out of eyeballing the full tally, which is the only reason they were caught: the
deputy premiership had to precede the premiership (`نائبا لرئيس الوزراء` contains
`رئيس الوزراء`, and 66 deputies were reading as prime ministers), and each
minister-of-state pattern had to be anchored on `دولة` so that
`وزيرا للمالية والشؤون الاقتصادية` stayed with finance.

**The family lane was smaller than its row count suggested, and needed a guard
the survey did not anticipate.** 87 people are listed in the descendant sections
and 47 carry a wikilink, but most already record what the article proves: the
lane yields **5 statements** (4 P53, 1 P26). The guard: the second half of a
couple bullet married *in*, and treating them as children of the bullet above
cost one wrong statement — a wife's married name, "Princess Ghazi of Jordan",
read as evidence of her own descent — and eleven wasted skips.

Two survey claims held exactly. The Senate is Arabic-only (156 members, no
English category), and the presiding offices were the best statements-per-row in
the country: 28 rows against 3 recorded for the Senate presidency, 34 against 5
for the speakership, both previously yielding nothing because `الرئيس` was not a
name column.
