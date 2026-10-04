---
description: Shrink peploop's operator surface from 23 commands and ~50 flags to five verbs (run, write, report, audit, check) plus a small dev group. Covers the inventory, measured use across the last 8 country runs, the hazards found along the way, the target runbook, and a migration in small checked steps. Accounts for the in-flight title_en and outbound-lane work.
date: 2026-10-04
tags: [peploop, cli, runbook, simplification, operator-experience, locks, audit]
---

# Simplify the peploop operator surface

## Why

On `main` the CLI has **23 commands** (24 once the `titles` worktree lands) and
about **50 options**. An operator types **20–26 invocations per country**, plus
retries and raw SQL. For the Dominican Republic that was 20 logged stage runs in
`data/do_*.log`, 4 apply runs in the scratchpad, and one `audit_do.sql`. The
runbook (`countries.md` §3) lists 17 lines, and then needs a paragraph of
caveats for what the lines leave out.

None of the stages is wrong. The problem is that the *chaining* is manual, and
every manual link has failed at least once:

- `--limit` was used as "unlimited". Across all transcripts the values passed
  were 1,000–100,000 on fetch, extract, reconcile, propose, verify and policy.
  The only small limit that mattered was `apply --limit 3`.
- `apply` cut off a drain twice at its default of 10 people. Every recent
  drain took 4–5 invocations (`jm_apply1..5`, `by_apply_drain1..4`,
  `apply_do..4`), so one run became several EditGroups batches, because
  `BATCH_ID` is per process.
- Two `apply` processes drained Trinidad and Tobago at once and wrote 24
  statements twice (`efb35a9`, `3b4f8cb`).
- A run on one country deadlocked on `AccessExclusiveLock` when another
  country's command started at the same moment (see Hazards).
- Audit skips were done with raw `UPDATE proposal …` statements, and the next
  `propose` re-run silently wiped them (see Hazards).

The goal is a few verbs that encode the runbook's order, with stops before
every write. It is not a rewrite: every stage function stays as it is.

## How the last 8 runs were actually driven

The 8 runs were co, cu, bi, by, do, ht, jm and tt, between 2026-09-30 and
2026-10-03. The sequence below comes from `data/<cc>_*.log`, the scratchpad
apply logs, and a tally of every `peploop.cli` call in the session transcripts
(main sessions and subagents).

```
seed → load-positions ∥ fetch → extract
→ position-signals --skip-counts → position-signals --local-holders
→ reconcile → reconcile (again: the failed rows)
→ mint-categorize → mint-verify (1–5×) → mint (dry) → mint-report --out data/mint/<cc>.md → mint-feed
→ propose → policy --dry-run → policy → verify → policy (again) → verify (again)
→ apply --write --limit 3 → psql UPDATE … audit:coordinator → apply --write --limit 1000 (×3–5)
```

Patterns in that sequence:

- **Always run back to back:**
  - the two `position-signals` calls;
  - `policy --dry-run` and then `policy`;
  - `verify` and then `policy` (verify already re-runs the policy per person, so
    the second `policy` only reprints the funnel: `jm_policy_dry` and
    `jm_policy2` differ only in `pending → accepted/skipped`);
  - `mint-verify`, `mint`, `mint-report`;
  - `mint --write` and `mint-feed`;
  - `reconcile` twice, the second pass picking up the 1–9 failed requests
    (`*_reconcile2.log`).
- **Same value every time:** `--threads` was 8 for fetch, 4 for extract, 8 for
  reconcile and 4 for verify. `mint-report --out` always pointed at
  `data/mint/<cc>.md`.
- **Never used** in any transcript: `refresh`, `--recount`, `mint --id`,
  `mint-feed --id`, `extract --qid`, `fetch --qid`.
- **Used only in the Slovenia era:** `run` (3 calls), `render` (5), `review`
  (1), `dump` (1).

## Inventory: commands

Each row gives the call count across all transcripts (from the tally) and
whether the runbook (`countries.md` §3) lists the command.

| command | purpose | runbook | used in last 8 runs | verdict |
|---|---|---|---|---|
| `seed --file --country` | queue the members of a seed file's categories | yes | yes (24) | **internal**: `run` stage `seed`, path derived from `<cc>` |
| `load-positions --country [--source]` | load a country's office items | yes | yes (30); `--source` 1× | **internal**: stage `positions`; `--source` goes |
| `fetch --limit --threads --qid` | items, scope gate, articles | yes | yes (12) | **internal**: stage `fetch` |
| `refresh --qid --articles` | re-fetch moved items | no | no (0) | **delete**: apply's pre-flight already reads live state |
| `extract --limit --threads --qid` | one LLM read per person | yes | yes (19) | **internal**: stage `extract` |
| `position-signals [--skip-counts] [--local-holders] [--recount]` | ranking signals | yes, as 2 lines | yes (33), always as the pair | **fold** into stage `positions`/`reconcile` (see below); all 3 flags go |
| `position-stats` | position table counts | no | 11×, mostly the pilot | **fold** into `report` (section `positions`) |
| `reconcile --limit --threads` | one LLM verdict per office mention | yes | yes (34), then a retry pass | **internal**: stage `reconcile`, retries failures once |
| `mint-categorize [--dry-run]` | cluster misses into candidates | yes | yes (21) | **internal**: stage `mint` |
| `mint-verify [--limit] [--threads] [--dry-run]` | Opus decides each candidate | yes | yes (35) | **internal**: stage `mint` |
| `mint [--write] [--limit] [--id]` | create guarded items (dry by default) | yes | yes (44) | dry half → output of the `mint` stage; write half → **`write`** |
| `mint-feed [--id]` | feed created/found items back | yes | yes (17) | **internal**: `found` is fed in stage `mint` (no Wikidata write needed); `created` is fed in `write` |
| `mint-report [--out]` | mint funnel, skips, cost | yes | yes (28) | **fold** into `report` (section `mint`) |
| `mint-audit --id --skip --reason --by` | skip a candidate afterwards | yes | 9× | **fold** into `audit` |
| `propose --limit --qid` | extraction → proposals | yes | yes (22) | **internal**: stage `propose` |
| `policy [--dry-run] [--limit] [--qid]` | decide each proposal by rule | yes, as 2 lines | yes (59) | **internal**: stage `policy`; the dry funnel → `report funnel` |
| `verify [--dry-run] [--limit] [--threads] [--qid]` | Opus checks each pending row | yes | yes (37) | **internal**: stage `verify` (already re-runs the policy) |
| `apply [--write] [--limit] [--follow] [--qid]` | write accepted rows | yes | yes (67) | **fold** into **`write`**; `--follow` goes |
| `stats` | people, articles, proposals, tokens | as a checkpoint | yes (47) | **fold** into `report` (sections `people`, `proposals`) |
| `run` | old fetch+extract+propose in one pass | as a warning | no (3, Slovenia only) | **delete**; the name goes to the new driver |
| `render` | QuickStatements output | no | no (5, Slovenia only) | **delete** (already planned as step 3 of the unsupervised plan) |
| `dump` | write an extract request and answer to `data/extract/` | no | no (1) | **fold** into `dev prompt extract --qid` |
| `review` | Textual TUI sampler | no | no (1) | **move** to `dev sample` (see open decision 1) |
| `titles --country [--dry-run]` *(worktree)* | cache English office titles | n/a | n/a | **internal**: stage `reconcile` runs it before shortlisting; no command |
| `load-positions` lane `mission` *(worktree)* | outbound ambassador discovery | n/a | n/a | **internal**: a default member of `positions.SOURCES`; no flag |
| `reconcile --reask retrieval:2` *(planned in `peploop_recon.md` step 3)* | re-ask refusals whose shortlist changed | n/a | n/a | **internal**: the `reconcile` stage always does it; no flag |

### Flags that go away

- `--limit` on every stage. Small defaults truncated silently, and operators
  passed the country's size anyway. A stage works on everything its
  selection returns. `--limit` survives only on `write`, for the "first N"
  gate.
- `--threads` on every stage: fixed per stage at the values every run used.
- `--country` as an option: it becomes the positional `<cc>`.
- `--file` on seed: becomes `peploop/seeds/<cc>.yml`.
- `--dry-run` on `policy`, `verify`, `mint-categorize` and `mint-verify`:
  - local state is re-derivable, so it needs no dry run;
  - LLM spend is braked by `--until`;
  - "show me the request" becomes `dev prompt <stage>`.
- `--write`, `--follow` and the drain loop on `apply`: replaced by `write`,
  which drains to empty and exits.
- `--skip-counts`, `--local-holders`, `--recount` and `--source`.
- `--id` on `mint` and `mint-feed`, and `--out` on `mint-report`.
- `--qid` stays, on `run` and `write` only: it carries the named people
  through every stage. That replaces the 16 `apply --qid` and 5
  `propose/verify --qid` uses.

## Inventory: modules, tables, checks

**Dead or near-dead code**

- `render.py` (162 lines) and the `render` command: no use since Slovenia, and
  their deletion was already planned.
- `reconcile.as_jsonl` has no caller.
- **Mint scaffolding** from when the two halves were built in parallel:
  - `cli._mint_module` (a lazy import);
  - `getattr(mint, "verify")` with the error "not implemented yet";
  - `mint_write.fallback_recheck` and `default_recheck`, which are
    `getattr(mint, "reguard")` with a fallback. `mint.reguard` exists, so the
    fallback branch and its "mint.reguard not found" message never run.
- **The label/alias lane.** `propose` still emits `label:`/`alias:` rows, and
  the policy throws them all away under `lane_removed`: 5,318 of 24,378
  proposal rows in the DB, 135 of Jamaica's 569. Removing the lane touches
  `propose.py` (emission), `policy.lane_removed`, `apply.TERM_PREFIXES`, and
  the label/alias handling in `review.py`/`render.py`.
- `design.md` §Layout lists a `run.py` ("driver, thread pool") that does not
  exist. The `Commands` section and the "Every command here exists" paragraph
  describe the Slovenia-era surface.

**Tables**

- Every table has a reader.
- `verdict` holds 158 rows from the TUI era. Its only readers are `review.py`,
  `check_review`, `check_regress`, and `propose._store`, which keeps any row
  with a verdict. That last reader is what makes it the right home for
  audits (below), so keep it.

**Checks.** 13 checks are offline and pass in about 9 s together. Measured
today:

| check | seconds | result |
|---|---|---|
| `check_apply` | 1.0 | pass |
| `check_mint` | 0.7 | pass |
| `check_mint_categorize` | 0.8 | pass |
| `check_mint_queue` | 0.8 | pass |
| `check_mint_verify` | 1.2 | pass |
| `check_mint_write` | 0.9 | pass |
| `check_neutral` | 0.1 | pass |
| `check_policy` | 0.7 | pass |
| `check_propose` | 0.2 | pass |
| `check_reconcile` | 0.7 | pass |
| `check_scope` | 0.2 | pass |
| `check_seed` | 0.2 | pass |
| `check_verify` | 0.7 | pass |

- There is no runner, so each check is invoked by name. The transcripts show
  `check_neutral` run 92 times, but `check_seed` only twice.
- **The DB checks repeat one helper.** Five of them
  (`check_mint_categorize`, `_queue`, `_verify`, `_write` and
  `check_reconcile`) each re-implement the same "shadow the live table with a
  `TEMP` table" helper.
- **`check_regress` is not a check.** It re-extracts every judged person with
  real model calls, and it reported 45 "regressions" that nobody acts on.
  The 2×2 rewrite planned in the unsupervised plan never happened. Verdict:
  **delete**.
- **`check_review` writes to live rows.** It drives the TUI against live
  proposals and "restores" them with `UPDATE proposal SET status = %s,
  decided_by = NULL, decided_at = NULL`. That erases the `policy:`/`apply:`
  provenance of every row it touched, and the next policy run then re-decides
  those rows. Verdict: **delete** with the TUI's demotion. If the sampler
  stays, rewrite it on the shadow-table helper.

**Per-country files**

- `seeds/<cc>.yml` and `census/<cc>.yml` are both long, well-commented,
  measured files with different lifecycles: seeds are written before the run,
  the census before `mint`. Merging them buys little. Keep both and find them
  by convention. The census stays optional, since Colombia ran without one.
- `countries.md` §7 has no entries for bi, by, do, ht, jm and tt. Recording
  them is part of closing those runs, not of this plan.

## Hazards found while taking the inventory

These are bugs, not surface. Fix them first, whatever happens to the CLI.

1. **Audit skips do not survive a re-run.**
   - `propose._store` deletes and re-derives every proposal row except
     `applied` rows and rows with a `verdict` (`KEPT_STATUSES`, propose.py
     ~750). A raw `UPDATE … decided_by='audit:pudo'` has neither, so the next
     `propose` wipes it and the policy re-decides the row from scratch.
   - Colombia's 14 `audit:pudo` rows (ids 29503…35772) no longer exist. Their
     re-derived rows were later skipped by the verifier, so nothing leaked, but
     only by luck.
   - The 5 surviving `audit:coordinator` rows for `do` will go the same way on
     the next `propose` for those people.
   - Candidate audits *are* durable: `write_candidates` skips rows where
     `decided_by IS NOT NULL`.
   - **Fix:** an audit writes a `verdict` row (decision `reject`, reason, note)
     as well as `status='skipped', decided_by='audit:<by>'`. `propose` already
     keeps rows that have a verdict, so the audit becomes durable with no
     schema change.
2. **Every CLI start runs DDL that can deadlock.**
   - `cli()` calls `db.init_schema()`, which executes all of `schema.sql` on
     every invocation. That includes `ALTER TABLE verdict DROP/ADD CONSTRAINT`,
     `ALTER TABLE resolution DROP CONSTRAINT …` and 22 more `ALTER`s, each
     taking `AccessExclusiveLock`.
   - Two commands that start together deadlock. That is the "DeadlockDetected
     at categorize start" and the failed reconcile call in the Haiti run.
   - **Fix:** take `pg_advisory_lock(hashtext('peploop-schema'))` around it.
     Better still, skip the file when its hash matches one stored in a
     one-row `schema_version` table.
3. **The country lock keys differ.**
   - `apply` locks `peploop-apply:<cc>` and `mint` locks `peploop-mint:<cc>`,
     so a mint and an apply can run on one country at once.
   - Two concurrent LLM runs on one country (two `reconcile`s) are also
     unlocked. The ledgers make that wasteful rather than wrong.
   - **Fix:** one lock per country, `peploop:<cc>`, held by both `run` and
     `write`. Different countries still run in parallel.
4. **`--skip-counts` left every run country without whole-corpus counts.**
   - Only Czechia's 201 rows (and other pilot-era loads) carry
     `holders`/`instance_count`/`held_subclasses`. Colombia, Cuba, Slovenia
     and all six recent countries have at most 3 counted rows each, 1,061 of
     17,641 rows overall.
   - `holders_by_country` is filled, so the local holder signal works. The
     ranker's `class` signal, though, is silent on every run country's own
     offices.
   - The runbook's reason for skipping ("whole-corpus numbers a new country
     does not change") holds for *other* countries' rows, not for the newly
     loaded ones.
   - **Fix:** the `positions` stage counts the rows that have no counts yet
     (`fill_counts(qids=<uncounted>)`). The impact on ranking is unmeasured;
     note it, and don't re-run old countries for it.
5. **One `apply` process is one EditGroups batch.**
   - `BATCH_ID` is chosen per process, so the 3–5 invocations a drain took
     became 3–5 batches. The user's decision was "one EditGroups batch per
     run".
   - **Fix:** `write` drains to empty in one process. It waits out maxlag
     internally, as `--follow` did, and exits when nothing it can write is
     left.

## Target surface

```
peploop run    <cc> [--until STAGE] [--from STAGE] [--qid Q…]
peploop write  <cc> [--yes] [--limit N] [--qid Q…]
peploop report <cc> [SECTION…] [--out PATH]
peploop audit  <cc> (--proposal ID… | --candidate ID… | --ids FILE) --reason TEXT --by NAME
peploop check  [NAME…]
peploop dev    prompt <stage> (--qid Q | --country cc)   # print the first request, send nothing
peploop dev    sample <cc>                               # the review TUI, if kept
peploop dev    counts [--all]                            # whole-corpus fill_counts, for a re-measure
```

Five verbs and a `dev` group of three. The split that carries the safety
story: **`run` never writes to Wikidata, and `write` is the only thing that
does.**

### `run <cc>`: reads, thinks, decides

An ordered list of idempotent stages. Each stage is the existing function,
called with no limit. The driver:

- takes the country lock, so a second `run` or `write` on the same country
  exits at once and names the holder;
- logs every stage to `data/runs/<cc>.log` (append-only, a header line per
  stage, the summary line last);
- ends by writing `data/runs/<cc>.md` (the `report`).

| stage | what it calls | notes |
|---|---|---|
| `seed` | `wikipedia.load_seeds` + `seed_category` over `seeds/<cc>.yml` | skipped when the country already has people, unless `--from seed` |
| `positions` | `positions.load_country` (all lanes, `mission` included), then `fill_counts` on uncounted rows | runs beside `fetch` (both are network-only); skipped when this state's rows were loaded within 7 days, unless `--from positions` |
| `fetch` | the current `fetch` body over all `queued` people | |
| `extract` | the current `extract` body over all `fetched` people | ledgered; a re-run costs nothing |
| `reconcile` | `fill_scope_qualifiers`, `fill_diplomatic`, `fill_local_holders(only_missing)`, then `titles.translate` (when it lands), then every unanswered mention, then one retry of the failures, then a re-ask of refusals whose shortlist gained a QID | the signals need the item table, which is why they sit here rather than in `positions` |
| `mint` | `categorize` → `verify` → `feed` of `found` rows; prints the guarded queue (what `mint` dry printed) | feeding `found` writes nothing to Wikidata, so it needs no write gate |
| `propose` | `propose_person` over every extracted person | |
| `policy` | `policy.run(write=True)`, then the funnel | **default stop** (`--until` defaults to `policy`): the one place the runbook stops unasked, before verify spends |
| `verify` | the current `verify` body (it re-runs the policy per person) | |

`--until STAGE` stops after a stage. `--from STAGE` starts at one, for when
the earlier ones are known done. `--qid` restricts every person-shaped stage
to the named people, so one person runs the whole pipeline. The driver
prints the pending work per LLM stage *before* it starts the stage: new
extractions, unanswered mentions, candidates to verify, pending rows. A
prompt edit that re-keys a whole country is therefore visible up front, not
on the bill.

### `write <cc>`: the one writer

`write` takes the same country lock and does four things:

1. **create**: recovers interrupted creations, then creates every `guarded`
   candidate (`mint_one`) and feeds each one. Feeding reloads the item,
   re-asks the mentions attested to it, and re-proposes.
2. **catch-up**: runs `policy` and `verify` over the people the feed touched,
   so new office items reach the gate their statements need. This is the
   only LLM spend in `write`; it is bounded by the number of fed people and
   printed first.
3. **apply**: drains `accepted` rows to empty, one EditGroups batch per
   invocation, waiting out maxlag.
4. Prints what was written and appends to `data/runs/<cc>.log`.

The other options:

- `--limit N` caps both the items created and the people written, which is
  the "first three diffs" gate.
- Without `--yes`, `write` is a dry run. It prints the guarded payloads and
  the per-person apply payloads, runs the pre-flight, and writes nothing to
  Wikidata or the DB; the catch-up step is skipped. This keeps today's
  "nothing leaves without an explicit flag" under one flag name for both
  writers, where today `mint` and `apply` each take their own `--write`.

### `report <cc>`: every checkpoint's numbers in one place

One function per section. Plain `report <cc>` prints them all. Each section
comes from code that already exists or from the ad-hoc SQL in the
scratchpad:

- `people`: today's `stats`, scoped to the country.
- `positions`: today's `position-stats`, plus the twin pairs §1 of the
  runbook asks for.
- `reconcile`: verdicts by kind, the creation queue by title, where the
  incumbents landed (`r.sql`, `latest.sql`).
- `mint`: `mint_write.report`.
- `funnel`: `policy.run(write=False)` and `report_lines`, which replaces
  `policy --dry-run`.
- `verify`: verdicts by kind and the refusal classes.
- `writes`: statements per property, batch ids, `apply:` skips.

`--out` defaults to `data/runs/<cc>.md`.

### `audit <cc>`: the only way to take a row out

- `--proposal` writes, in one transaction, `status='skipped'`,
  `decided_by='audit:<by>'` and a `verdict` row (`reject`, reason `other`,
  note = `--reason`). That fixes hazard 1.
- `--candidate` calls `mint_write.audit_skip`.
- Both refuse rows that are `applied`, `created` or `creating`, as
  `audit_skip` already does for candidates.
- `--ids FILE` (or `-` for stdin) takes the id list an observer's SQL
  produced. The SQL selects, and the command records who decided and why.
- There is still no approve.

### `check`: the offline checks, one entry point

`peploop/check.py` imports each `check_*` module, runs its `main()`, and
prints one line per check plus a total. `check <name>` runs one. A shared
`checks_db.shadow(conn, tables)` replaces the five copies of the temp-table
helper. The list is the files on disk, so a new `check_titles.py` is picked
up without registration.

## What the runbook becomes

§3 of `countries.md` shrinks to this. The measurements in §1 and the seed and
census authoring in §2 are unchanged.

```
python -m peploop.cli run <cc> --until reconcile   # seed, positions ∥ fetch, extract, reconcile
python -m peploop.cli report <cc> reconcile        # checkpoint: verdicts, creation queue, incumbents
# write census/<cc>.yml if the country needs one (see §3)
python -m peploop.cli run <cc>                     # mint, propose, policy → stops at the funnel
python -m peploop.cli report <cc> mint funnel      # checkpoint: STOP AND SHOW
python -m peploop.cli run <cc> --from verify --until verify
python -m peploop.cli write <cc>                   # dry: the payloads, nothing sent
python -m peploop.cli write <cc> --yes --limit 3   # on the user's go: three items/people
python -m peploop.cli audit <cc> --ids doubts.txt --reason "…" --by <name>   # if the observer doubts rows
python -m peploop.cli write <cc> --yes             # the drain: one batch
python -m peploop.cli report <cc> writes
python -m peploop.cli check                        # closing: check_neutral among them
```

That is 7 invocations of real work plus the dry `write` and the reports, down from 20–26. Re-running
any line is safe. The checkpoint table in §4 keeps its rows. Each row's
"show" column becomes a `report` section.

## The in-flight work

- **`title_en` (worktree `agent-af8b…`)** adds `titles.py`, a prompt, two
  tables and a `titles` command.
  - Keep the module, the prompt, the tables and `check_titles.py`.
  - Drop the command. The `reconcile` stage calls
    `titles.translate(mention_titles(...))` and `refresh_items` before
    shortlisting; both are cached and resumable.
  - Its `--dry-run` count becomes a line in the `reconcile` stage's
    "pending work" preamble, and its `cost()` becomes part of
    `report reconcile`.
  - If it merges before step 6 below, the command lives for a few days and
    goes in step 8.
- **Outbound lane (worktree `agent-a18b…`, no diff yet).**
  - Add `mission` to `positions.SOURCES`, so every load runs it.
  - Do not add a `--source` choice or a separate command.
  - The recon plan's follow-up (`load-positions --country by` then
    `position-signals --local-holders`) becomes
    `run by --from positions --until reconcile`.
- **`reconcile --reask retrieval:2`** (recon plan step 3): implement it as
  the `reconcile` stage's last step, with no flag. The tag stays as the
  `reopened_for` value. Its first run per country spends ($13–59 across the 8
  countries per the recon plan), and the pending-work preamble shows that
  before the requests go out.

## Migration: small steps, each with its check

Stop and report after each step.

0. **Fix the hazards, no surface change.**
   - Schema-init lock or version hash. *Check:* start four `stats` processes
     at once, 10 times, with no deadlock.
   - Audits as verdicts, `mint-audit` unchanged for now. *Check:* a
     `check_propose` case: audit a row, re-propose the person, and the row is
     still `skipped` with `audit:` provenance.
   - Delete `check_review`. *Check:* none needed, nothing imports it.
1. **Delete the dead code.**
   - `render.py` and `render`, `refresh`, old `run`, `check_regress`,
     `as_jsonl`, the three mint shims, `--recount`.
   - The label/alias lane in `propose`, with `policy.lane_removed` kept one
     release for old rows.
   - *Check:* all offline checks pass, `grep` finds no reference,
     `check_neutral` passes, and `design.md` §Layout and §Commands are
     updated.
2. **Add the `check` runner and the shadow-table helper.** *Check:* `check`
   reports 12 passes (after the deletions) in under 15 s, and each migrated
   check still fails when its assertion is inverted. Spot-check one.
3. **Move the stage bodies out of `cli.py` into `peploop/stages.py`.**
   - Each stage becomes a function `(country, qids=None) -> summary`. This is
     a pure move; the commands keep calling them.
   - *Check:* on `bi`, which is finished, every stage sends zero model
     requests (the ledgers hold) and `report` output is byte-identical
     before and after.
4. **Add `report`.**
   - It folds `stats`, `position-stats`, `mint-report` and the policy funnel.
   - *Check:* `report do funnel` equals `data/do_policy_dry.log`'s funnel up
     to the decisions since made. `report do mint` equals `data/mint/do.md`.
5. **Add `audit`**, and make `mint-audit` an alias of it. *Check:*
   `check_mint_write`'s audit case passes through the new path, and a
   proposal audit survives re-propose (step 0's case).
6. **Add the `run` driver.**
   - One lock per country, `positions` with uncounted `fill_counts`, the
     signals inside `reconcile`, one failure retry, the pending-work
     preamble, and `--until`/`--from`/`--qid`.
   - *Check:* `run jm` on a finished country makes zero model requests and
     changes no `proposal.status` (snapshot before and after). Then
     `run <next country> --until policy` from empty, observed.
7. **Add `write`.**
   - create → feed → catch-up policy/verify → apply drain, one process, one
     batch, `--limit`, dry unless `--yes`.
   - *Check:* `write <finished country>` lists nothing. On the next country,
     `write --yes --limit 3` gives three diffs and one batch id, and the
     drain gives one more batch id.
8. **Retire the per-stage commands from the CLI.** Keep the functions; drop
   the commands (and `titles`, if it merged). Rewrite `countries.md` §3–4 and
   `design.md` §Commands. *Check:* the runbook's commands all run on the
   next country, and `check` passes.
9. **Optional, only if the next mint change spans sections: split `mint.py`
   (2,520 lines).** It splits along its own `# ---` markers into `mint.py`
   (queue, floor, census, disposition rules), `mint_categorize.py` and
   `mint_verify.py`. That matches the check files, which are already split
   that way. Pure moves. *Check:* the four `check_mint*` pass unchanged.
   Don't do it for its own sake.

## Risks

- **The driver can hide spend.** One `run` reaches every LLM stage, and a
  prompt edit re-keys a country: Colombia's extract was about $35. The
  pending-work preamble and the default stop at `policy` are the brakes. If
  they prove too soft, add a request ceiling per stage, not a flag per stage.
- **`write` spends on its catch-up verify.** It is small (the people the feed
  touched: 10–45 per country so far) and printed first. The alternative is
  a `run` after the create and before the apply, which brings back a manual
  link.
- **Losing the per-stage escape hatch.** `--from X --until X` runs one stage,
  and `--qid` runs one person. Prompt development that relied on
  `extract --limit 20` uses `--qid` with a sample list instead, or
  `dev prompt`.
- **Merge conflicts with the two worktrees in `cli.py`.** Steps 0–2 do not
  touch `cli.py`'s commands. Start step 3 after both worktrees have merged.
- **Behaviour drift in step 3.** "Pure move" is the claim the byte-identical
  `report` check exists to test. If it differs, stop.
- **One lock per country serialises `run` and `write`.** That is intended.
  It would also block the "fetch beside load-positions" parallelism if those
  were separate processes, which is why the driver runs them as threads.
- **`audit` with an id file is only as good as the SQL that made the file.**
  The command records who and why but cannot check what. That is the same as
  today, minus the raw `UPDATE`.

## Open decisions for the user

1. **The review TUI.** It "stays as an optional sampler", but an accept in it
   sets `status='accepted'`, and `apply` writes that row with no policy and no
   verify. That is the 31 hand-accepted Slovenia rows. Options:
   - (a) delete `review.py` (827 lines) and its Textual dependency;
   - (b) keep it as `dev sample`, recording verdicts without changing status,
     so it samples and never gates or writes.

   Recommendation: (b) if anyone still samples with it, otherwise (a).
2. **The consent flag on `write`.** Proposed: dry unless `--yes`. The
   alternative is that the verb itself is the consent, which saves one flag
   but breaks the habit that nothing leaves without a flag. Either way,
   `--limit 3` remains the first-run gate.
3. **Whether `run`'s default stop stays at `policy`** once a few more
   countries have gone through clean, or moves to the end, with `--until
   policy` used only for new kinds of country.

## Not proposed

- A `measure` verb for the runbook's §1 (category tree, office descent,
  PetScan counts). Those are read-only research snippets, and a command
  would freeze a procedure that still changes per country.
- Merging `seeds/` and `census/`.
- A stage-state table for resumption. Idempotent stages plus `--from` already
  resume, and a second record of "done" would drift from the ledgers that
  actually decide it.
