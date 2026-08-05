# Task: category-driven P39 (position held) completion

Use Wikipedia category membership as a *candidate generator* for missing
`P39` (position held) statements on Wikidata: run PETScan for a category that
maps to a specific position QID, diff members against the position's actual
holders on Wikidata, verify each gap against the person's Wikipedia article,
and prepare sourced P39 edits with date qualifiers.

## Background: how OS does it today (and why to invert it)

`datasets/_wikidata/categories/` (opensanctions repo) drives the
`wd_categories` dataset: PETScan (`petscan.wmcloud.org`, depth=4, members
with a Q5 wikidata item) enumerates category members; category specs in
`wd_categories.yml` optionally carry a hardcoded `position:` block
(name + `wikidata_id`), and **every member gets that occupancy
unconditionally** — no dates, no verification of actually having held the
office. PR opensanctions/opensanctions#5300 adds ~20 Lithuanian categories
in exactly this style.

Inverting it — verifying per person and writing the P39 *into Wikidata* —
is better because:

* the fix lands at the source; OS's `wd_peps` then picks the position up
  natively, with start/end dates, and the `position:` blocks in the YAML
  become redundant over time;
* it catches the false positives that blanket assignment can't: categories
  contain acting officeholders, predecessors-of-the-office under earlier
  polities, and depth-N subcategory drift;
* everyone else consuming Wikidata benefits, not just OS.

## Spot check (2026-08-04)

`Lietuvos_prezidentai` (depth 2): 12 members, all with a Q5 item. The
category includes Artūras Paulauskas (acting president only) and Justas
Paleckis (Soviet-era chairman) — live proof that membership ≠ held the
office. Diff against `?p wdt:P39 wd:Q878222` (13 holders): **zero gaps** —
every member already carries the P39. Expectation: head-of-state-level
items are fully curated; the yield is in vice-ministers, final-instance
judges, ambassadors, central bankers — precisely the PR 5300 tail.

## Mechanics

* **PETScan is a plain GET** (params cribbed from `crawler.py`):
  `https://petscan.wmcloud.org/?language=lt&project=wikipedia&categories=<cat>`
  `&depth=<n>&format=json&doit=&wikidata_item=with&wikidata_prop_item_use=Q5`.
  JSON gives `.["*"][0].a["*"][]` rows with `.metadata.wikidata` (QID) and
  `.title`. CSV also available (`format=csv`, column `Wikidata`).
* **Holder set**: SPARQL `?p wdt:P39 wd:<position>` plus the position item's
  own `P1308` (officeholder) claims — same union `position_holders()` uses in
  zavod.
* **Candidates** = category members − holders. For each: fetch item + the
  category-language Wikipedia article; the LLM verifies the person actually
  held *that specific office* (not deputy/acting/related office) and extracts
  start/end dates and, where possible, the citation the article uses.
* **Edit**: `P39 = <position QID>` + `P580`/`P582` qualifiers + reference
  (article's underlying citation as P854+P813 preferred; the article itself
  is weak sourcing). Acting officeholders: skip — modelling "acting" is its
  own rabbit hole; log them instead.
* Depth matters: PR 5300 uses depth 4 for recall in OS, but for *edit
  candidates* start with depth 0–1 per specific category — subcategory drift
  is the main false-positive engine.

## Input: category → position mappings

Take the `position:`-bearing categories from PR 5300 as the pilot set
(Lithuania: president, PM, Seimas members + speaker, constitutional /
supreme / supreme-administrative court judges, prosecutor general, Bank of
Lithuania board, chief of defence, ambassadors-by-receiving-country, ...).
The YAML in the PR is the machine-readable source — parse it rather than
copying it here.

## Pipeline / scripts

1. `scripts/petscan.py` — category + language + depth → list of (QID, title).
2. `scripts/position_gap.py` — position QID + category spec → candidate list
   (members − holders), with per-person item snapshot (existing P39s help the
   review: "has P39 deputy minister" explains a minister-category hit).
3. `scripts/fetch_article.py` — shared with tasks/genders.md.
4. LLM verification pass → verdicts + proposed edits (JSONL).
5. Edit plan render → human review → apply via wikibase-cli → re-fetch,
   verify, and report which YAML `position:` blocks are now redundant.

## Open questions

* Sourcing bar: is "the lt.wikipedia article says so" acceptable as P143-ish
  sourcing when the article cites nothing? Probably: prefer the article's
  own citation; fall back to the article URL as P854; skip if neither.
* Date precision/conflicts: articles often give years only; P39 with
  year-precision qualifiers is fine.
* Where a candidate turns out to be a false category member (acting, wrong
  era), optionally propose the *category* cleanup on Wikipedia too? Out of
  scope for now; log them.

## Status

- [x] PETScan-from-script proven; president pilot shows zero gaps (expected)
- [x] petscan.py + position_gap.py built (2026-08-04). First results:
  * Speaker of the Seimas (Q12663218): 2 candidates — Čmilytė-Nielsen and
    Skvernelis, both genuinely missing the speaker P39. Real, easy wins.
  * Member of the Seimas (Q18507240): 669 members, 25 candidates.
  * PM (Q845439): 1 candidate — Sakalauskas, *Soviet-era* head of government,
    i.e. a category false positive the verification step must reject.
  * Gotcha fixed: PETScan's "uses Q5" filter passes Category: items too
    (they reference Q5 via P4224); position_gap enforces P31=Q5 itself.
- [x] sweep of PR 5300's mapped categories (2026-08-04), depth 0, snapshots
  in `data/positions/<qid>.json`:

  | Position | Category | members | WD holders | candidates |
  |---|---|---:|---:|---:|
  | Q878222 President | Lietuvos_prezidentai | 12 | 13 | 0 |
  | Q845439 Prime Minister | Lietuvos_ministrai_pirmininkai | 19 | 25 | 1 |
  | Q18507240 Member of the Seimas | Seimo_nariai | 669 | 815 | 25 |
  | Q12663218 Speaker of the Seimas | LR_Seimo_pirmininkai | 16 | 16 | 2 |
  | Q132068652 Prosecutor General | Lietuvos_generaliniai_prokurorai | 8 | 1 | 7 |
  | Q109496871 Bank of Lithuania governor | Lietuvos_banko_vadovai | 10 | 3 | 7 |
  | Q55607326 Chief of Defence | Lietuvos_kariuomenės_vadai | 16 | 3 | 13 |

  **55 candidates total.** Observations:
  * Yield concentrates where the position item is young/thin: the Prosecutor
    General item (Q132068652) has ONE P39 holder on all of Wikidata; the
    category alone names 7 more, incl. Paulauskas (PG 1990–95). Chief of
    Defence and Bank governor similar — mostly interwar + 1990s officeholders.
    Q47891929 Vaikšnoras (current Chief of Defence since 2024!) lacks the P39.
  * Known false positives to be caught in verification: Soviet-era officials
    riding in republican categories (Sakalauskas for PM; likely Drobnys for
    bank governor, Vitkauskas for chief of defence). Interwar officeholders
    need a per-position judgment: same office resumed (bank governor,
    kariuomenės vadas?) vs. different polity.
  * The four `position:` blocks without `wikidata_id` (3 final-instance-court
    judgeships, deputy PG) have **no Wikidata position item at all** (checked
    by search + a jurisdiction=LT position census) — sweeping those categories
    requires creating the position items first. Separate, well-defined subtask.
  * Bonus findings from the LT position census: Q140592938 "Minister of
    Economy and Innovation of Lithuania" (2 holders) looks like a duplicate of
    Q107735812 (20 holders) — merge candidate. Q132068652 and Q55607326 lack
    `P1001: Lithuania` (they don't appear in the jurisdiction query) — small
    metadata edits worth adding to the batch.
- [x] verification pass (2026-08-04): 6 parallel LLM reviewers read all 55
  lt.wikipedia articles → `data/positions/verdicts/*.jsonl`. Outcome:
  **35 modern adds** (edit-ready), **10 interwar adds** (held back pending a
  policy call on interwar continuity), **9 rejected** (Soviet analogues,
  acting-only, Supreme Council 1990–92 ≠ Seimas, and two outright category
  errors on lt.wiki), **1 unclear**. Raw-category false-positive rate ~16%
  on the Seimas set — the verification step earns its keep.
- [x] edit plan rendered: `data/positions/edit_plan.md` (review doc) +
  `data/positions/edit_plan.qs` (35 sourced, dated P39 QuickStatements).
  Items needing a human eye before applying are flagged in the .md:
  Kižienė (no dates in article), Kraucevičius/Stanaitis ("ėjo pareigas" —
  possibly de facto), the Žukauskas/Žukas 1920–21 overlap, Kopustinskas 1941.
  Acting-PG term for Petrauskas and acting-PM week for Sakalauskas are
  recorded in the verdicts if ever wanted.
- [x] side edits verified against live items → `data/positions/side_edits.qs`:
  * Q132068652 (Prosecutor General) has neither P1001 nor P17 → add both = Q37.
  * Q55607326 (Chief of Defence) lacks P1001 → add Q37.
  * Q2529445 Nikitinas P569 is `+2000/precision 7` — i.e. *20th century*, not
    the year 2000 (my snapshot misread it; `year_of` now skips sub-year
    precision). Add P569 = 1941 sourced to the LRT obituary the article cites.
    Whether to then remove/deprecate the century-precision claim is a manual
    call (QS removal needs an exact value match; wb-cli is safer).
  * Q140592938 = confirmed duplicate of Q107735812 (Minister of Economy and
    Innovation; identical P31 + description, no distinguishing claims, 2 vs 20
    holders) → **merge**, manual or `wb merge-entity`, not QS.
- [ ] human review of edit_plan.md → apply → re-run position_gap to verify
- [ ] position-item creation subtask for the court judgeships / deputy PG
