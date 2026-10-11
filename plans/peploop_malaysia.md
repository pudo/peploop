---
description: Run a peploop country sweep on Malaysia using the position items peptree just repaired
date: 2026-10-06
tags: [peploop, peptree, malaysia, country-sweep]
---

# peploop sweep of Malaysia, using peptree's repaired positions

## Context

peptree repairs position items (P17/P1001/P279/P31). Its global sweep produced
108 lines on 93 items for Malaysia (`data/peptree/my/my-2026-10-05.qs`, outbox
chunk 011): P1001 68, P17 20, P279 20. The user has confirmed that chunk has
been pasted.

peploop builds its office set **live from Wikidata**
(`peploop/positions.py:load_country` → `discover`): the `descent` lane needs
`P31/P279* Q4164871` together with `P17` or `P1001` equal to the state. So peptree's
repairs flow into peploop with no code bridge at all. Any item that gained P17,
P1001 or an office-typed P279 becomes loadable, and the reconciler can then
place mentions on it instead of queuing them for minting.

The experiment is to run the standard runbook (`peploop/countries.md` §1–§6) on
Malaysia, and to measure how much of the result depends on peptree's
repairs. The answer tells us whether "peptree first, then peploop" should
become the default order for a country.

Malaysia was chosen because English Wikipedia covers it, and it is close in
shape to the Commonwealth runs already closed (JM, TT). Its matrix also shows a large
subnational tier: 197 subnational offices are kept (Menteri Besar, state EXCO
members, state assemblies, mayors).

On approval, this plan is copied to `plans/peploop_malaysia.md` per the
CLAUDE.md convention.

## Steps (each ends at a checkpoint)

### 1. Confirm the repairs landed (read-only)
- Read the live claims (`max_age=0`) of the 93 subjects in
  `data/peptree/my/my-2026-10-05.qs` and count how many of the 108 lines are
  present. Use a scratch script over `peploop/wikidata.fetch_items`; this does
  not run `peptree outbox --status`, which writes to the ledger.
- WDQS lag: the SPARQL discovery sees an edit only once the query service has
  caught up. Check a few touched items with an ASK query, and wait if they are
  missing.

### 2. Baseline vs. fresh position set
- Run `peploop.cli load-positions --country my`. This reads live data and only
  ever adds rows.
- Partition peptree's 93 touched items as follows:
  - (a) in `position` and reachable by `descent`/`usage`
  - (b) reachable only because of a peptree line (it gained P17 or P1001 where it had neither, or
    gained a P279 that completes the Q4164871 path)
  - (c) still not loadable
- Also list peptree's 123 `skip:one_channel` items (e.g. Mayor of Ipoh,
  Menteri Besar of Terengganu P279). Items still unscoped go into
  `census/my.yml` with their QIDs, as the TT census does, so that
  mint-verify finds them instead of minting duplicates.
- **Checkpoint:** report the partition sizes.

### 3. Runbook §1 measurements → `peploop/seeds/my.yml`
- Measure the category trees on en.wikipedia and ms.wikipedia, starting
  from OpenSanctions' `wd_categories.yml` Malaysia entries. Cover the tiers in
  `recipes/institutions.md`: federal cabinet, both houses of the federal parliament, the 13 state
  assemblies and their EXCOs, Menteri Besar and Chief Ministers, the rulers and Yang
  di-Pertuan Agong (royal family is its own lane: leave a note, don't
  seed genealogy), the Federal Court, Bank Negara, the armed forces, ambassadors, and
  SOE/GLC heads (Khazanah, Petronas).
- Seed the current era only (Malaysia since 1963), with each entry's
  measured size and marginal count in comments, following the `tt.yml` style.
- Write `census/my.yml` from the step 2 measurement.
- **Checkpoint:** the seed size and estimated cost, before `seed`.

### 4. Stages up to the policy funnel
`seed` → `fetch` → `extract` → `position-signals` → `reconcile`. Then run
`mint-categorize` → `mint-verify`, then `propose` → `policy`. The command form is
`.venv/bin/python -m peploop.cli <stage> --country my`, with `.envrc` sourced.
- Attribution measurement: count the `resolution` rows whose chosen `qid` is
  in partition (b). These are the placements peptree's repairs made possible.
  Also count the mint candidates that matched a peptree-touched item.
- **Checkpoint (runbook §4):** the funnel after `policy`, before `verify`
  spends. Also a checkpoint after `mint-verify`, before any `mint --write`.

### 5. Verify, then write (only on the user's go)
`verify`, then a dry run of `apply`, then `apply --write --limit 3`. Each
sample diff is shown to the user, and the drain runs only on an explicit go.
The writer lock is per country, so only one drain runs at a time.

### 6. Close the country (runbook §6)
- Add Malaysia's tokens to `check_neutral.TOKENS`.
- Add a §7 entry in `peploop/countries.md`, including the peptree attribution
  numbers.
- Add one memory line about whether peptree-before-peploop paid off.
- If the effect was material, add a sentence to the runbook §1 saying to run
  peptree for the country first.

## Files touched
- New: `peploop/seeds/my.yml`, `peploop/census/my.yml`,
  `plans/peploop_malaysia.md`
- Edited (closing only): `peploop/countries.md` §7, the `check_neutral` tokens
- No peptree code changes. If a peploop code defect turns up, it is a stop
  and a report, not a fix in flight.

## Verification
- Step 1 confirms in the live record that peptree's lines have landed.
- `report --country my funnel`, `report --country my mint`
- The backtest, i.e. the policy's skipped "already recorded" rows, agrees with
  the routing.
- `apply` dry-run payloads are pre-flighted against the live state.
- Sample diffs from `--limit 3` are read before the drain.
- Nothing is written to Wikidata, and no git push happens, without the
  user's explicit instruction.
