---
description: Deep peploop run on Japan — national, prefectural and every municipal mayor — after a peptree pass on Japan's office items; pilot slice before the full spend
date: 2026-10-08
tags: [peploop, peptree, japan, country-sweep, mayors, subnational]
---

# peploop: a deep run on Japan

## Context

Japan is the first peploop country where Wikidata already holds most of the
office set. Measured on 2026-10-08, read-only:

- **Office items:** 6,124 reached by descent through `P17`/`P1001` = Q17.
  1,763 of them are mayoralties, 101 governorships and 81 ambassadorships.
  4,759 have no holder. The trap tail is the predecessor era: daimyo,
  shogun, House of Peers, Meiji foreign advisers and Nagasaki bugyō.
- **What is already recorded:** 24,146 P39 statements. Every prefectural
  governor has an item (`Q51198747`…), and so does every prefectural
  assembly (the `Q1045259xx` series).
- **Most existing P39s are undated.** Of 7,624 House of Representatives
  statements, 6,002 carry no qualifier at all. 1,165 carry `P2937` and 783
  carry `P768`. The House of Councillors has 1,319 of 1,967 undated, and
  Aomori's governor item has 52 of 53. So the main yield here is **dates on
  tenures Wikidata already holds**, through `apply.plan_tenure`'s `refine`
  route. That is a different shape from every earlier country, where the
  yield was new statements. It is also why the run is worth doing deep.
- **Category trees:** ja.wikipedia is the regular tree. It has per-era Diet
  categories (`令和時代の衆議院議員` 828, `令和時代の参議院議員` 406,
  `平成時代の…` 1,715 / 921), portfolios under `日本の国務大臣`, governors by
  prefecture (`都道府県知事`, ~45–55 each), mayors by prefecture and then by
  municipality (`日本の市町村長`, 47 containers, plus
  `廃止自治体の市町村長` with 253 subcats), and prefectural assembly members
  (`日本の都道府県議会議員`, 48 subcats). en.wikipedia is thin.
  OpenSanctions' `wd_categories.yml` has one Japan entry
  (`Political_office-holders_in_Japan`).

Decisions from the user (2026-10-08):
- Go to full depth, including **every municipal mayor**.
- Run **peptree on Japan first**, then peploop. This follows
  `plans/peploop_malaysia.md`.

Malaysia is mid-run (1,915 people extracted, nothing proposed). This plan
does not touch it. The writer lock is per country.

On approval, this plan is copied to `plans/peploop_japan.md`.

## Steps (each ends at a checkpoint)

### 0. peptree on Japan (sweep batch 73)
- Run `sweep run 73` → `audit 73`. Use the loop in `plans/peptree.md`, "Non-OECD
  sweep: outcome and handover". Expect the `LARGE` gate to trip on 6k items and
  the run to go through `focus`. Taxonomy fixes count as normal execution
  (memory `peptree-sweep-pacing`). Stop on anything that needs a revert or
  touches code outside `peptree/`.
- Mark `reviewed`, then run `outbox --batch 73`. **The user pastes the chunk.**
  Then `outbox --status`.
- Wait until WDQS has caught up: an ASK over a sample of touched items must
  succeed before load.
- **Checkpoint:** peptree lines by property, the chunk id, and confirmation
  that the lines are live.

### 1. Load and partition (read-only plus `load-positions`)
- Run `load-positions --country jp`. Report items per lane.
- List the duplicate pairs (two items for one era) among the national
  offices, renamed ministries and chamber presidencies, and record which twin
  holds the holders.
- Do the peptree attribution partition as in Malaysia's step 2: items that
  became loadable only because of a peptree line.
- **Homonymous municipalities:** list mayoralty items whose municipality
  label repeats across prefectures (伊達市 in Hokkaido and Fukushima, 府中市 in
  Tokyo and Hiroshima, and so on). These are the reconciler's known trap for
  this country, and step 4 checks them by name.
- **Checkpoint:** lane counts, the duplicate pairs, and the homonym list.

### 2. Seeds and census (runbook §1–§2)
- Write `peploop/seeds/jp.yml` in the `si.yml`/`my.yml` shape: every entry
  commented with its measured size and its marginal over the entries above
  it. Use `wikipedia.seed_category` for the counts. The tiers:
  - **Diet:** the Reiwa categories of both houses whole. The Heisei
    categories too: living ex-members are in scope, and the 20-year rule
    skips the 1990s. Speakers and vice-speakers. Showa out.
  - **Executive:** `日本の国務大臣` without its `(廃止)` and 戦前 children.
    Also 副大臣 and 大臣政務官 if their categories exist, plus the
    Chief Cabinet Secretary tier and the deputy prime ministers.
  - **Imperial family:** the current-imperial-family category only, at depth
    0. The genealogy is a kinship lane and is not seeded.
  - **Courts and oversight:** Supreme Court justices, the
    Prosecutor-General, the Board of Audit, the Cabinet Legislation Bureau.
  - **Central bank and SOEs:** BoJ governors and executives; Japan Post and
    the Japan Post Bank, the Development Bank of Japan, JBIC, GPIF, and NHK.
    Each one only if a category exists.
  - **Security:** the SDF chiefs of staff (統合/陸上/海上/航空幕僚長) and the
    National Police Agency commissioners.
  - **Diplomats:** `駐…日本大使` containers.
  - **Party officers:** LDP secretaries-general and policy chiefs, and the
    leaders of the opposition parties.
  - **Prefectures:** `都道府県知事`, excluding `廃止された府県の知事`. The
    prefectural assemblies through `日本の都道府県議会議員`.
  - **Municipal:** the 47 `…の市町村長` containers at depth 2, and
    `東京都の特別区長`.
  - **Left out:** `廃止自治体の市町村長` (mayors of municipalities abolished in
    the merger wave, almost all ended more than 20 years ago), municipal and
    ward council members (not PEP grade), the wards of designated cities
    (appointed officials), `日本の政治家秘書`, and the by-topic and eponymous
    trees.
- Write `peploop/census/jp.yml` from the step 1 gaps (tiers with no item, the
  apex judiciary's seat versus the court, SOE heads). Bodies come from live
  measurement, not memory.
- **Measure two Japan conventions before anything is proposed. Both are
  findings only, with no code change:**
  - Does `P2937` on Diet statements follow a rule a new spell should copy? Run
    a tally by term and by era, and read three exemplars.
  - How do ja articles print dates? A sample of 20 articles counted for
    `1962年（昭和37年）` dual forms against era-only forms. The extract prompt
    says "Gregorian as printed", so an era-only date should yield nothing.
- **Checkpoint:** the seed total, the distinct people, and a cost estimate
  scaled from Colombia and Malaysia per person. Expect on the order of 10–14k
  seeded and 5–8k extracted, so a few hundred dollars across all stages.
  Report the two convention findings too.

### 3. Seed, fetch, then a pilot slice
- `seed` → `fetch` (network only, side by side with nothing else). Report
  people by status after the scope gate.
- **Pilot:** about 200 people stratified across the tiers (Reiwa Diet,
  ministers, governors, prefectural assembly, mayors, including a homonymous
  town's mayor). Run `extract` → `position-signals` → `reconcile` →
  `propose` → `policy` with `--qid` on them.
- **Checkpoint: stop and show the pilot funnel.** Look for:
  - how many accepted rows route `refine` (dating an undated statement)
    against `new` and `termed`;
  - whether era dates were mis-converted;
  - whether mayors landed on the right municipality's item;
  - whether any rule fires on a class nobody predicted.

  A class that falls for an unnamed reason becomes a stop and a report. It
  is not fixed in flight.

### 4. Full run up to the policy funnel
- Run `extract`, `reconcile`, `mint-categorize` → `mint-verify`, and
  `propose` → `policy` on the whole country, detached, each with an observer
  (log tail, failures, tokens).
- Mint expectations: mostly `found`. Mayoralties are not minted, because
  there is no municipality resolver yet, and the 1,763 existing items should
  catch most mentions.
- **Checkpoints (runbook §4):**
  - after `reconcile`: verdicts by kind, the creation queue, where the
    incumbents landed, and the homonym list checked by name;
  - after `mint-verify`: `report mint`, before any `mint --write`;
  - after `policy`: the funnel, before `verify` spends.

### 5. Verify and write (only on the user's go)
- `verify`, then `apply` dry, then `apply --write --limit 3`. Show the three
  diffs, and include at least one `refine` onto an undated statement.
- Drain only on an explicit go. It is one process under the writer lock.
- The audit (runbook §5) focuses on:
  - the incumbents;
  - multi-term Diet members, whose spells must land as several statements;
  - `refine` rows that dated a bare statement belonging to a different term;
  - the homonymous mayoralties.

### 6. Close (runbook §6)
- Add Japan's tokens to `check_neutral.TOKENS` and run the check.
- Write the `countries.md` §7 entry. Include the share of the yield that was
  `refine` and the peptree attribution.
- Add one memory line.

## Files
- New: `peploop/seeds/jp.yml`, `peploop/census/jp.yml`,
  `plans/peploop_japan.md`.
- Edited at close only: `peploop/countries.md` §7 and
  `peploop/check_neutral.py` tokens.
- peptree fixes from step 0 go under its own rules, with a check each.
- A peploop code defect found during the run is a stop and a report.

## Verification
- Step 0: the outbox status shows the chunk live, and an ASK on sampled
  items succeeds.
- `report --country jp people|positions|funnel|mint` at each checkpoint.
- The pilot funnel is read before the full extract.
- `apply` pre-flights against live state (`max_age=0`), and the three
  `--limit 3` diffs are read before the drain.
- After the drain: nothing landed on an unused twin, and no written statement
  absorbed two spells.
- Nothing is written to Wikidata and nothing is pushed without the user's
  explicit instruction.
