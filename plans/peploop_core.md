---
description: Whether peploop's core (not its CLI) can be consolidated without a rewrite. Maps the duplicated machinery (six copies of the LLM-pass kernel, five ledgers, two rule engines, two audits, seven label lookups, ten shadow-table helpers), costs each ledger's re-key from the DB, and ranks six consolidation moves. Answers whether consolidation should come before the `run` driver.
date: 2026-10-04
tags: [peploop, consolidation, refactor, llm-ledger, rules, checks, architecture]
---

# Consolidate peploop's core

Read with `plans/peploop_simplify.md`. That plan fixed the operator surface. This
one asks whether the code under it carries more concepts than the job needs.

## Short answer

**Partly.** Three moves are worth doing before the `run` driver: delete what the
simplification left behind, add a shared check fixture, and extract one
LLM-pass kernel. Together they take about 300 lines out of 19,500. They remove
the one concept that is genuinely copied six times, and they re-key no ledger.
The driver's planned "pending work" preamble and its cost line both want that
kernel to exist first.

Everything else is hygiene, to do when a change is in the file anyway. The big
modules are big because of domain rules (policy has 23 rules, mint has 12,
positions has its ranking signals), not because machinery is duplicated. The
duplicated machinery comes to about 700–900 lines, roughly 5–6% of the
production code. A consolidation that tried to remove the domain size would be
a rewrite.

## State of the core

Production code is 14,400 lines in 20 modules. The 16 checks add 5,100 lines
and schema.sql adds 518. The DB has 20 tables, 72 classes and 6 prompts.

| module | LOC | what it is | classes | notes |
|---|---:|---|---:|---|
| mint.py | 2,520 | queue, census, floor, categorize, verify, 12 disposition rules | 24 | 4 `# ---` sections: queue 1–406, categorize 407–1273, verify 1274–2120, disposition 2121–2520 |
| positions.py | 1,864 | load (lanes), signals, search/rerank | 1 | ~240 lines (1128–1370) are policy-only lazy fills |
| policy.py | 1,418 | 23 proposal rules, case building, funnel, audit | 4 | ~550 lines are P39 spell/family logic |
| offices.py | 1,063 | archetypes, spec, payload, guard, live duplicate search | 5 | |
| cli.py | 1,060 | stage bodies, pools, reports | 0 | stage bodies move out in simplify step 3 |
| apply.py | 966 | session, payload planning, router, send, record | 3 | also hosts `create_item`/`find_created` for mint |
| reconcile.py | 835 | shortlist, render, ask, ledger, re-ask | 5 | |
| review.py | 828 | Textual sampler | 7 | now verdict-only (simplify decision 1b) |
| propose.py | 722 | compare, status, store | 3 | |
| mint_write.py | 519 | create, recover, feed, audit, report, cost, **writer_lock** | 1 | |
| titles.py | 474 | English title cache | 4 | |
| verify.py | 463 | second reading of proposals | 4 | |
| wikipedia / extract / wikidata / prompt / db / scope / http | 360 / 257 / 250 / 216 / 207 / 182 / 155 | | | |

**Concepts a reader has to hold.** There are four person-level decisions:
`extraction`, `resolution`, `proposal`→policy, and `verification`. Mint adds
three more: `office_candidate`→disposition, `mint_call`, and
`office_attestation`. There are two writers (`apply_person`, `mint_one`), and the
English-title cache is one more ledger (`title_en`).

Several names mean different things in different modules:

- `Candidate` is a shortlist row in reconcile and an office candidate in mint.
- `Case` is the policy's input in one module and mint's in another.
- `verify` is both a module and `mint.verify`.
- `Verdict`, `Verification` and `MintVerdict` are three different things.
- `Answer` and `VerifyAnswer` are two different things.

**LLM spend per ledger,** read from the DB on 2026-10-04 at `mint_write.PRICES`
(Haiku at $1/$5, which `PRICES` does not list). This table is what a re-key
costs, as an upper bound, if every country were re-run:

| ledger | rows | model | spend | per row | keyed on |
|---|---:|---|---:|---:|---|
| `extraction` | 7,303 | sonnet-5 | $182 | $0.025 | qid, prompt_hash, article_revs |
| `resolution` | 32,678 | sonnet-5 | $285 | $0.009 | extraction, mention, prompt_hash, render_version, reopened_for |
| `verification` | 5,491 | opus-5 | $103 | $0.019 | content key, prompt_hash, render_version, model |
| `mint_call` categorize | 180 | sonnet-5 | $41 | $0.23 | sha(message), prompt_hash, render_version, model |
| `mint_call` verify | 422 | opus-5 | $28 | $0.066 | sha(message), prompt_hash, render_version, model |
| `title_en` (+`_call`) | 12,184 (499 calls) | haiku-4-5 | $2 | — | state, lang, folded title/jurisdiction, prompt_hash, model |
| **total** | | | **≈ $640** | | |

No key includes request parameters such as `max_tokens`, `effort`, `thinking` or
the model in the request body. A key changes only when the prompt text or the
rendered user message changes, or when `RENDER_VERSION`/the model is bumped. That
makes the kernel move below safe by construction, as long as rendering stays
byte-identical.

Reconcile is the largest spend ($285), and no report prints it. Neither does
verify's. `report` prints extraction tokens (`cli._report_people`), mint dollars
(`mint_write.cost`) and title tokens (`titles.cost`), each with its own SQL.

## Duplication map

### 1. The LLM-pass kernel: six copies in peploop, a seventh in peptree

Every pass repeats the same eight parts.

| part | extract | reconcile | verify | titles | mint categorize | mint verify | prompt.py |
|---|---|---|---|---|---|---|---|
| prompt file + sha256 | via `prompt.system_prompt` | `system_prompt` (lru) | `system_prompt` (lru) | `system_prompt` (lru) | `categorize_prompt` (no cache) | `verify_prompt` (no cache) | `system_prompt` |
| client singleton + lock | `client` | `client` | `client` | `client` | reuses `reconcile.client` | reuses `reconcile.client` | |
| `Strict` base | yes | yes | yes | yes | imports `reconcile.Strict` | same | |
| request dict | inline in `extract_person` (built twice: sent, then stored) | `request_for` | `request_for` | `request_for` (no cache_control, no thinking) | inline in `ask_categorize` (streamed) | inline in `ask_verify` | |
| usage dict | inline | inline in `reconcile` | inline in `verify` | inline in `ask` (2 keys) | `_usage` | `_usage` | |
| ledger read | inline SELECT | `recorded` | `recorded_many` | `cached_many` | `recorded_call` | `recorded_verify` | |
| ledger write | `db.insert_extraction` | `store` | `store` | `_store` | `store_call` | `store_verify` | |
| pool + per-item failure | `cli.extract`/`_extract_one` | `cli._resolve_all` | `cli._verify_people` | `translate.one` + 3 retries | serial loop | `ThreadPoolExecutor` or `mint._Inline` | |

The per-pass schemas, renderings and `settle*` functions are domain code and
stay where they are. The rows above are not domain code. They come to about 190
lines, plus about 45 more in mint's two near-identical `recorded_*`/`store_*`
pairs. `peptree/repair.py` copies the same `Strict`/`system_prompt`/`client`.

Two inconsistencies come with the copies:

- Prompt hashing is cached (`lru_cache`) in three modules and re-read on every
  call in mint.
- `USAGE_KEYS` is defined twice (`mint.py:1185`, `mint_write.py:53`), in
  different orders.

Threading has two workarounds for one cause. Temp-table shadows exist only on
the caller's connection, and `db.conn()` is per thread. So `mint._Done`/`_Inline`
(~30 lines) and the `threads > 1` branch in `titles.translate` both exist so
that a check can run a pool inline.

### 2. Ledger tables

There are five tables of one family: `extraction`, `resolution`,
`verification`, `mint_call` and `title_en`/`title_en_call`. They share
`prompt_hash`, `model`, `usage_json` and `created_at`, and four of them have
`render_version`. They differ in what they are about. `resolution`'s columns
(`qid`, `kind`, `shortlist`) are read as domain data by six modules:
`propose.placements`, `mint.unplaced`, `policy`, `mint_write.feed_one`,
`cli._mentions_for` and `reconcile.refusals`. Two foreign keys point at it:
`proposal.resolution_id` and `office_attestation`.

The ledgers do not need merging. What is missing is one place to read spend
across all of them.

### 3. Fold, stem, token and label helpers

- **Whitespace-collapsed fold, twice:**
  - `mint._fold` = `_SPACE.sub(" ", positions.fold(t)).strip()`;
  - `offices._norm` = `" ".join(fold(t).split())`.

  Both compute the same thing.
- **Stems, twice:**
  - `offices._stems(texts)` drops `ROLE_STEMS`;
  - `mint._stems(text, drop)` takes the drop set as an argument.

  The body is the same: `tokens` → `[:PREFIX]` → `len > 2`.
- **Phrase folding:** `offices._phrase` / `label_key` / `without_state` /
  `names_state` are a fourth variant, built on `fold` and `re.findall`.
- **`titles.fold_key`** is deliberately different (NFC with no
  transliteration). Keep it.
- **Labels for a set of QIDs,** seven variants:
  - `reconcile._body_labels` and `mint._labels` are byte-identical: the
    position label first, then `fetch_items` + `best_label`;
  - `verify._labels` adds descriptions;
  - `policy.office_labels` reads the position table only;
  - `mint._labels_of` returns every language;
  - `mint_write.labels_of` and `_label` read a payload's QIDs;
  - `titles._country_names` asks rigour first;
  - `mint.Context.labels_for` memoises over `_labels_of`.
- **A state's languages as alpha-2 codes,** four copies:
  - `prompt.country_langs` (drops unmapped codes);
  - `mint.offered_for` and `mint.country_langs` (keep unmapped codes with
    `or lang`);
  - `titles.unlabelled` (keeps a `None`).

  These differ in a way that can reach a rendered request.
  `mint.offered_for`'s list is in the categorize message, so its content key
  depends on it.

### 4. Live-read helpers and their local variants

`wikidata.fetch_items`, `claim_qids`, `claim_time` and `best_label` are shared
and used by 8–13 modules each. The local variants are these:

- **"Item values, unended, not deprecated":**
  - `offices._unended`;
  - `positions._unended_qid` (first value, with an ended fallback);
  - `positions.type_targets` (P31+P279, with an exception for `ALWAYS_KEPT`).
- **`offices._values`** is a one-line wrapper around
  `claim_qids(..., include_deprecated=False)`.
- **Class walks:**
  - `positions.type_closure` walks P31+P279 and is cached in `type_edge`;
  - `offices._Subclasses` walks P279 only, memoised per object, deliberately;
  - `peptree/wd.py` holds a copy of `type_closure`.
- **`offices.resolve`** is `fetch_items(props="labels|aliases|claims")` with a
  sort. `offices.live_lookup` and `mint.Context` (135 lines) are the live
  context of the mint guard. Neither is duplicated elsewhere.
- **`wikidata.lastrevids`** has no caller.

### 5. Locking

- `db.init_schema` takes `pg_advisory_xact_lock(hashtext('peploop-schema'))`.
- `mint_write.writer_lock` takes the session lock
  `pg_try_advisory_lock(hashtext('peploop:<cc>'))`.
- `cli.apply_` imports the writer lock from `mint_write`, so the apply writer
  depends on the mint module for its lock.

Two lock helpers in two modules do one job. The `run` driver will need a third
caller.

### 6. Reports and funnels

- **`policy.Funnel` + `report_lines`:** keyed `(property group, rule)`.
- **`mint.verify`'s `stats["funnel"]`:** a `Counter((status, rule))`, printed by
  `cli.mint_verify` and again by `mint_write.report`.
- **`cli._report_people`:** token sums by hand-written SQL.
- **`cli._report_proposals` → `_echo_property_counts`:** also printed by
  `cli.propose`.
- **`review.summary_lines`.**
- **`mint_write.report`:** 86 lines of markdown, with its own `cost`.
- **`titles.cost`.**

The two funnels are the same idea (rows per rule that decided them) in two
shapes.

## Concepts that could merge, and which should not

| pair | merge? | why |
|---|---|---|
| Policy `Disposition` + `decide` vs mint `Decision` tuple + `_first` | **yes, the plumbing** | Both are "first matching rule in an ordered tuple, the rule's name recorded, every case decided". About 20 lines of machinery each. The rules themselves stay where they are: the status vocabularies (`accepted/skipped/pending` and `skipped/found/guarded`) are different lifecycles. |
| `policy.audit` vs `mint_write.audit` | **yes, the skeleton** | The skeleton is the same: validate `by`/`reason`, lock `FOR UPDATE`, refuse unknown/foreign/unauditable all-or-nothing, update. The encoding has drifted: a proposal records `decided_by='audit:<by>'`, while a candidate records `decided_by='<by>'`, `rule='audit:<by>'` (10 live rows of each shape). |
| `mint.census_unattested` vs `mint.floor`'s `census/unattested` | **yes, delete one** | The rule and the floor both return the same string. The only production caller of `floor` is `below_floor`, which runs after `census_unattested`, so the floor's branch never runs in production. Only `check_mint_queue.check_floor` reaches it. |
| `mint.Row` (queue) vs `mint.Attestation` (verify) | **yes** | Both describe one mention behind an office. `Candidate.rows` exists only to alias `attestations`, so that `floor` can read both, through an `Attested` Protocol. One shape removes the Protocol and the alias. |
| `office_candidate` vs `proposal` | **no** | Both are "a decision with an ordered rule, an audit trail and a write". But the write targets differ (a new item vs a statement), recovery differs (intent tag + usercontribs vs baserevid + re-propose), and readers differ. One table would make every reader branch on kind. |
| mint-verify's dispositions vs policy's `RULES` | **no** (beyond the plumbing above) | Different inputs (a candidate with a guard and a live duplicate vs a proposal with siblings and spells). One rule list would be a union type with half the fields empty. |
| `offices.guard` vs policy's office rules (`office_rejected`, `generic_needs_scope`, `recorded_elsewhere`) | **no** | Different questions. The guard asks "may this new item exist with this shape?". The policy rules ask "is this existing item a right target for this person's P39?". They share inputs (types, P17/P1001) but no logic. |
| `mint_one` vs `apply_person` | **no**; move the lock | Both writers already share apply's session, `create_item`, `find_created`, `BATCH_ID` and `THROTTLE`. What is left is per-kind crash semantics. The *loop* that drives both (cli `apply_` and `mint_`) merges in simplify step 7 (`write`). The lock should move to `db` before that. |
| `mint_call` keying (sha of the message) vs `verification` keying (semantic key + `RENDER_VERSION`) | **no** | Hashing the message makes `render_version` redundant for `mint_call`. But a person-verify message carries the item's live claims, so a message-hash key would re-ask on every unrelated item edit. The two keyings are right for their two passes. |
| Position-row loaders (`policy._position_rows`, `reconcile.candidates_for`/`replay_shortlist`, `mint.state_positions`, `mint.Context.index`) | **partly** | `mint.state_positions` and `Context.index` run the same SELECT, the second with subdivisions added; merge those two. The rest select different columns for different renderings, and the column lists are what keeps `RENDER_VERSION` honest. Leave them. |

## Size hotspots and seams

- **`mint.py`:** the seams are its own markers:
  - queue + census + floor (~400);
  - categorize (~870);
  - verify + Context + evidence (~850);
  - disposition (~400).

  The checks already split that way (`check_mint_queue`,
  `check_mint_categorize`, `check_mint_verify`). A split **moves**, it removes
  nothing. The concept win sits beside it: merge `Row`/`Attestation`, delete
  `_Inline`, and give mint's `Candidate`/`Case` names that do not collide with
  reconcile's and policy's (`OfficeCandidate`, `MintCase`). Not now: the
  deputy-minister work is in flight in `mint.py`.
- **`positions.py`:**
  - load + lanes (1–847);
  - ranking signals (848–1127);
  - policy-only lazy fills (1128–1370: `fill_first_held`, `holder_spells`,
    `dissolutions`, `fill_polity_inception`, `unfilled_*`, `fill_kinds`,
    `kind_use`, `organisations`, `item_names`, `names_by_qid`);
  - search/rerank (1404–1864).

  The policy-only block is the natural seam: it is "office facts the policy
  reads", and only `policy` calls it. Moving it to `policy` (or to an
  `office_facts.py`) would make `positions` purely load + rank. That is a move,
  not a removal. Do it only if policy is open anyway.
- **`policy.py`:** the rules are the content. The spell/family block (440–988)
  could be its own module, but it reads `Case` throughout. Leave it.
- **`cli.py`:** simplify step 3 (`stages.py`) already owns this file.
  Consolidation should not touch it ahead of the driver.

## Dead or near-dead code

| what | where | status |
|---|---|---|
| `lastrevids` | `wikidata.py:127` (24 lines) | no caller |
| `item_titles`, `refresh_items` | `titles.py:392–463` (~70 lines) | Called only by `check_titles.check_shortlist`. The backfill they did now happens on every load (`positions.load_items` → `titles.item_title`/`translate`). The check case is the only pin on "an unlabelled item is reachable by its English name", so port the case to the load path before deleting. |
| the floor's census branch | `mint.py:398` | unreachable in production (see above) |
| `mint._Done`, `mint._Inline`; `titles.translate`'s single-thread branch | `mint.py:2385–2410`, `titles.py:325` | Exist only for temp-table checks. They go once the kernel has an inline-at-one-thread runner. |
| `lane_removed` rule, `apply`'s `lane_removed` route, `TERM_PREFIXES`, `propose`'s route | policy/apply/propose | **Still live.** 3,752 label/alias rows remain (22 `accepted`, 14 `new`, 9 `applied`). One `DELETE` of the non-applied rows would let all four go. That is a DB change: **ask first.** |
| `cli.policy_` | `cli.py:486` | **Broken since `a66ed14`:** `_funnel(run, write=True)` names `run`, which is only bound in `verify_`. `python -m peploop.cli policy --country cc` raises `NameError`. The one-line fix is `run = _select(qid, ("proposed",), country)`. Every check passes, because none drives the CLI. |
| `from __future__ import annotations` | `policy.py:20` | harmless, unused by the rough check; ignore |

## Test structure

- There are 16 `check_*.py` files and no runner yet (simplify step 2 is not done).
- **The shadow-table helper exists 10 times in 8 files:**
  - `check_audit.shadow`;
  - `check_mint_write.shadow`;
  - `check_mint_verify`, inline;
  - `check_mint_categorize`, two inline variants;
  - `check_mint_queue`, inline;
  - `check_reconcile`, two inline variants;
  - `check_titles.shadow`;
  - `check_review`, a copy-in variant.

  The variants differ only in the table list, whether sequences are re-pointed,
  `INCLUDING GENERATED`, and whether live rows are copied in.
- Every check hand-rolls `failures += 0 if ok else 1` or an `expect` closure,
  and its own `main()`.
- Model stubs are passed in three ways:
  - an `asker=` parameter (titles);
  - module attribute swaps restored in `finally` (`mint.ask_verify = saved`,
    `setattr(mint, …)`);
  - and no stub at all, because the call is never reached (reconcile renders
    only).
- **Only reconcile's prompt hash and render version are pinned**
  (`check_titles.RECONCILE_PROMPT_SHA256`). Extract, verify, categorize,
  mint-verify and title_en have no pin, so a refactor could re-key them
  without failing a check.

A single `peploop/checks.py` would simplify this:

- `shadow(conn, tables, *, sequences=(), copy=False)` as a context manager;
- `Expect` (collects failures, prints, returns the exit code);
- `stub(module, **attrs)` as a context manager for model stubs.

It would take about 120 lines out of the checks and add about 50. It would also
make a new "ledger keys" pin cheap.

## Moves, ranked

Score = (concepts removed + LOC removed/50) / (risk + churn), where risk and
churn are 1 (low) to 3 (high). The LOC figures are estimates from the spans
above.

| # | move | concepts removed | net LOC | risk | churn | score | re-keys |
|---|---|---:|---:|---:|---:|---:|---|
| 1 | Dead code and the `policy_` fix | 3 | −120 prod, −30 checks | 1 | 1 | 2.9 | none |
| 2 | `checks.py` fixture + runner + ledger-key pin | 2 | −70 checks (+ a new pin) | 1 | 2 | 1.1 | none; adds the pin that guards #3 |
| 3 | `llm.py` kernel + `llm_usage` view | 4 | −120 prod | 2 | 2 | 1.6 | none if the pin holds |
| 4 | One decision plumbing: `Disposition`/`first`/`Funnel`/`audit_rows` | 3 | −60 | 1 | 2 | 1.4 | none |
| 5 | Shared lookups: labels, fold/stems, territory langs, unended values, advisory lock | 4 | −90 | 2 | 3 | 1.1 | **rendering-sensitive**; none if byte-identical |
| 6 | Split `mint.py`; merge `Row`/`Attestation`; rename the colliding classes | 2 | −40 | 2 | 3 | 0.5 | none |

By score the order would be 1, 3, 4, 2, 5, 6. The recommended order is
**1 → 2 → 3 → 4 → 5 → 6**. Move 2 goes before 3 because it adds the pin that
makes 3 safe.

### Move 1: delete what the simplification left (≈ half a day)

- **Fix `cli.policy_`:** bind `run` from `_select`.
- **Delete:**
  - `wikidata.lastrevids`;
  - the floor's census branch (`mint.py:398`). Keep the rule
    `census_unattested`: the funnel reports `census/unattested` under it.
    Move `check_floor`'s census case to a disposition case.
- **Port and delete:** move `check_titles`'s unlabelled-item case onto
  `positions.load_items(translate=…)` with a stubbed `fetch_items`. Then delete
  `titles.item_titles` and `refresh_items`.
- **Optional, with consent:**
  - `DELETE FROM proposal WHERE (property LIKE 'label:%' OR property LIKE 'alias:%') AND status <> 'applied'`;
  - then delete `lane_removed`, `TERM_PREFIXES`, apply's route and propose's
    route.
- **Verify:**
  - every check passes;
  - `grep` finds no reference to the deleted names;
  - `report <cc> funnel` on `bi` is identical before and after, except for the
    `lane_removed` line if the delete ran;
  - `python -m peploop.cli policy --country bi` runs.
- **Hashes:** none touched.

### Move 2: one check fixture, a runner, and a ledger-key pin (≈ half a day)

- **Add:**
  - `peploop/checks.py` with `shadow`, `Expect` and `stub`;
  - `peploop/check.py`, which imports every `check_*`, runs `main()` and prints
    one line each, as simplify step 2 planned.
- **Migrate the 8 files.**
- **New `check_keys.py`:**
  - pins `(prompt_hash, RENDER_VERSION)` for all six passes;
  - pins the sha256 of one rendered fixture message per pass:
    - an `extract` user message from a fixture entity and articles;
    - `reconcile.render_mention` over fixture candidates;
    - `verify.render_edit`;
    - `titles.render_batch`;
    - `mint.render_categorize`;
    - mint's `evidence().message()`.
  - Moves 3 and 5 must leave all of them unchanged. A deliberate prompt edit
    updates the pin in the same commit, which makes the re-key visible in the
    diff.
- **Verify:**
  - `check` reports every check passing in under 15 s;
  - inverting one assertion per migrated file fails it (spot-check two).
- **Hashes:** none touched; this move adds the guard.

### Move 3: one LLM-pass kernel (≈ 1 day)

- **`peploop/llm.py`, about 90 lines:**
  - `Prompt(path)`: text and sha256, cached;
  - `client()`;
  - `Strict`;
  - `usage(response)` with one `USAGE_KEYS`;
  - `request(prompt, message, *, model, max_tokens, effort=None, thinking=True, cache=True)`;
  - `parse(request, schema)` and `stream_json(request, schema)`, each returning
    `(answer, usage)` and raising on no parse. A truncated stream carries its
    usage, as `mint.Truncated` does today.
  - `PRICES` and `cost(model, usage)`, moved from `mint_write`;
  - `pool(threads)`: a `ThreadPoolExecutor`, or an inline runner at one
    thread. It replaces `mint._Inline` and `titles`' branch.
- **Callers:**
  - extract, reconcile, verify, titles and mint keep their own schemas,
    renderers, `settle*` and ledger SQL;
  - they lose `client`/`_client_lock`, `Strict`, `system_prompt`'s body, the
    usage dicts and the request dicts;
  - mint's two `recorded_*`/`store_*` pairs become one pair with a `pass_`
    argument (they differ only in the pass string and the render-version
    constant).
- **`llm_usage` view in schema.sql:**
  - columns: (pass, country, model, usage, created_at);
  - a `UNION ALL` over the five ledgers: country through
    `person.country`, `resolution.state_qid` and `mint_call.country`;
  - `title_en_call` has no country, so it is reported globally;
  - `report <cc> cost` prints dollars per pass from it, which covers reconcile
    and verify for the first time;
  - `mint_write.cost`'s per-report table and `titles.cost` read the view.
- **What it removes:**
  - six client singletons;
  - five `Strict` bases;
  - six prompt-hash readers;
  - five usage dicts;
  - two `USAGE_KEYS`;
  - three cost paths;
  - the inline-pool hack.

  peptree can import the kernel instead of copying it.
- **Risk:**
  - the request shape: `titles` sends `system` as a plain string with no
    thinking, and `ask_categorize` streams with `output_config.format`, so the
    builder takes flags rather than imposing one shape;
  - a hash read that is no longer cached is harmless.
- **Verify:**
  - `check_keys` unchanged;
  - `check_reconcile`/`check_verify`/`check_mint_categorize`/`check_titles`
    pass;
  - `dev prompt mint-categorize --country bi` and `mint-verify` print "0 to
    ask";
  - re-running `reconcile bi` and `verify bi` sends zero requests;
  - `report bi cost` matches the hand-computed $ for bi from this plan's SQL.
- **Hashes:** none, *if* every prompt is read as the same bytes and every
  rendered message is byte-identical. The pin is what proves it. **No ledger is
  re-keyed.** If a pin moves, stop. A careless move here could re-key up to
  $640 of answers, and $285 of that is reconcile alone.

### Move 4: one decision plumbing (≈ half a day)

- **A small `decide.py`** (or a section at the top of `policy.py`):
  - `Disposition(status, rule)`;
  - `first(rules, case) -> Disposition | None`;
  - `Funnel` keyed `(group, rule)` with `report_lines`;
  - `audit_rows(cur, rows, *, ids, country, unauditable)` → problems.
- **`mint`:**
  - `Decision` tuples become `Disposition`;
  - `_first` → `first`;
  - `stats["funnel"]` becomes a `Funnel`.
- **Both audits** call `audit_rows` and keep their own UPDATE (a proposal also
  writes a `verdict`).
- **Audit encoding:** standardise on `decided_by='audit:<by>'` for candidates
  too. The 10 existing `coordinator` candidate rows need a one-line `UPDATE`
  (**ask first**). Alternatively, readers accept both encodings for a release.
- **What it removes:**
  - one of two rule mechanisms;
  - one of two funnel shapes;
  - one of two audit skeletons;
  - the `decided_by` drift.
- **Risk:** low. The rule names and order are untouched, so the funnel strings
  stay identical.
- **Verify:**
  - `check_policy`, `check_mint_verify`, `check_audit` and `check_mint_write`
    pass;
  - `report bi funnel mint` is byte-identical before and after (except the audit
    rows, if migrated).
- **Hashes:** none.

### Move 5: shared lookups (≈ 1 day; can be done one helper at a time)

- **`wikidata.labels(qids, *, descriptions=False, langs=False)`:** reads the
  position table first, then live. It replaces `reconcile._body_labels`,
  `mint._labels`, `verify._labels`, `mint._labels_of` and
  `mint.Context.labels_for`'s fetch. `policy.office_labels` stays
  position-only for the report.
- **`positions.fold_words`** replaces `mint._fold` and `offices._norm`.
  **`positions.stems(texts, drop)`** replaces `mint._stems` and
  `offices._stems`.
- **`territory_langs(cc_or_qid, keep_unmapped)`:**
  - `keep_unmapped` preserves the two existing behaviours **exactly**;
  - `mint.offered_for`'s list is inside the categorize message, so a change
    there re-keys `mint_call` categorize (~$41 across countries).
- **`wikidata.claim_qids(..., unended=True)`** replaces `offices._unended`.
  `positions._unended_qid` and `type_targets` keep their special cases.
- **`db.advisory_lock(key, *, wait=False, xact=False)`:**
  - replaces `mint_write.writer_lock`'s body and `init_schema`'s lock;
  - `writer_lock` stays as the named wrapper, moved to `db`, so that
    `apply` stops depending on `mint_write`.
- **Merge `mint.state_positions` and `mint.Context.index`.**
- **Risk:** the label helpers feed reconcile's candidate rendering
  (`RENDER_VERSION`) and mint's messages (content keys). `check_keys` catches
  any drift. Do it one helper per commit.
- **Verify:** as in move 3, plus `check_mint`/`check_mint_queue`.
- **Hashes:** none if byte-identical. Any helper whose output differs is
  dropped from the move, not shipped with a bumped version.

### Move 6: split `mint.py`, and merge its mention shapes (≈ 1 day, after the deputy-minister work merges)

- **The split:**
  - `mint.py`: queue, census, floor, rules and disposition;
  - `mint_categorize.py`;
  - `mint_verify.py`: Context, evidence, ask, the verify driver.

  This is simplify step 9.
- **With it:**
  - merge `Row` and `Attestation`;
  - drop the `Attested` Protocol and `Candidate.rows`;
  - rename `mint.Candidate` → `OfficeCandidate` and `mint.Case` → `MintCase`.
- **Risk:** churn in the 4 `check_mint*` files (≈ 60 import edits). Pure moves
  apart from the merge.
- **Verify:**
  - the four mint checks pass unchanged in assertions;
  - `check_keys` is unchanged;
  - `report bi mint` is byte-identical.
- **Hashes:** none; `Attestation` feeds `render_attestations`, so the pin
  matters.

**Totals for moves 1–6:**

- about −430 production lines and −100 check lines, roughly 3% of the code;
- about 18 duplicated concepts brought to one;
- no ledger re-keyed, under the pin.

## Is consolidation an angle before the `run` driver?

**Moves 1–3: yes. Moves 4–6: no.**

**For moves 1–3:**

- The driver's first job is the per-stage "pending work" preamble (simplify,
  `run`). It also needs a cost line, because one `run` reaches every paid stage.
- Today the preamble has to be hand-built six ways, from six ledger readers.
  The cost line would come from three report paths that do not cover the two
  biggest spenders ($285 reconcile, $103 verify out of $640).
- With the kernel and `llm_usage`, both become one query each.
- Move 1 fixes a broken command the driver would call (`policy`).
- Move 2 is simplify step 2 anyway, plus the pin that every later move needs.
- Together: ≈ 2 days and −300 lines, with zero re-keyed dollars.

**Against making the rest an angle:**

- Consolidation's ceiling is small. The total removable duplication is about
  530 lines of 19,500, under 3%.
- The large modules are large for reasons a merge does not touch:
  - 23 + 12 ordered rules;
  - ranking signals;
  - the archetype table;
  - their documentation.
- Moves 4–6 cut concepts a reader trips on, but not ones the driver depends on.
  They are better done when their files are open for other reasons.
- Move 6 must wait for the deputy-minister work regardless.

## What not to do

- **One ledger table.** `resolution` is domain data for six readers and the
  target of two foreign keys. Folding it into a generic `llm_call` JSON table
  would turn every reader into JSON paths. A row-preserving migration re-keys
  nothing but churns ~15 SQL sites. A careless one re-asks up to $640. Unify
  *reads* through the `llm_usage` view instead.
- **One decision table or one rule list** for proposals and candidates. Share
  the plumbing (move 4), not the domain.
- **Merging `mint_one` and `apply_person` into one writer class.** Their crash
  semantics differ on purpose. The shared parts (session, `create_item`,
  `find_created`, batch, throttle) are already shared, and the loop merges in
  simplify step 7.
- **Keying every pass on a hash of its message** to drop `RENDER_VERSION`. It
  would make person-verify re-ask on unrelated item edits, and re-key all of
  `verification` and `resolution` (~$390).
- **Moving policy's lazy office facts into the position load** to remove the
  `fill_*`/`unfilled_*` pairs. They are lazy because only offices the policy
  meets are worth the network reads. This is a behaviour change, not a
  consolidation.
- **Re-rendering anything "while we're in there".** Any change to a candidate
  line, an attestation line or a language list re-keys a ledger. Each such
  change is its own commit with its own cost line, never a side effect of a
  refactor.
- **Splitting `positions.py` or `policy.py` for size alone.** It moves code
  without removing a concept. Do it only alongside a change that has to span
  sections.
- **Touching `cli.py`'s stage bodies** ahead of simplify step 3. They move
  wholesale there, and doing it twice doubles the merge conflicts.

## Coordination

- The deputy-minister work edits `offices.py`, `mint.py` and
  `prompts/mint_categorize.md`. That re-keys `mint_call` categorize by
  design: the prompt hash changes.
- Moves 1–4 touch `offices.py` only in move 5 (the `_norm`/`_stems`/`_unended`
  helpers), and `mint.py` only in moves 3, 4 and 6.
- Run moves 1–2 now. Run 3–4 after the deputy-minister branch merges. Update
  `check_keys`' categorize pin to the branch's new hash in that merge.
- `peptree/` is uncommitted and copies `Strict`/`client`/`system_prompt`
  (`repair.py`) and `type_closure` (`wd.py`). Once move 3 lands it can import
  `peploop.llm`. Don't change peptree from this plan.
