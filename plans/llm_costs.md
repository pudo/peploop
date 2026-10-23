---
description: Keep inference spend visible and bounded across peploop, pepcorp and peptree, then cut it — cost report, pre-flight estimate and run budget, one shared ask/ledger layer, the Batch API for bulk passes, resolve's article cache and settled titles, and measured trials of thinking, effort and model.
date: 2026-10-22
tags: [costs, llm, batch, caching, peploop, pepcorp, peptree, alignment]
---

# Inference costs across the toolchain

## Context

At list price the seven model ledgers hold about $5.2k of spend. None of it
went through the Batch API. Spend concentrates in a few passes:

| pass | $ | heavy because |
|---|---|---|
| resolve | 1,423 | 166k calls, one per mention, each re-sending the whole article uncached |
| tree repair | 911 | Opus 5 at high effort |
| extract | 727 | output ~3× its answer (thinking) |
| mint verify | 701 | Opus 5 high, output ~5× its answer |
| mint categorize | 506 | $0.24 a call: 27k in, 18.7k out |
| corp decide | 472 | 2.8 asks per body, from re-keying |
| title_en | shows $0 | `claude-haiku-4-5` missing from `llm.PRICES` |

The system-prompt cache already works: reads run 3–7k tokens a call and
writes are close to zero. The waste is elsewhere:
- unattended work at full price;
- re-asks after prompt, actor or render changes;
- thinking that outweighs the answer;
- Opus 5 where Opus 5.5 is cheaper;
- per-mention article repeats.

Spend is also invisible until after a run: extract, resolve and verify print
no dollars.

The aim is to see spend per pass before and after every run, to cap it, and
to roughly halve it, without changing what any stored answer is keyed by.
Stage 0 and corp decide's batching (part of stage 2) come before the Europe
pepcorp re-run (`plans/pepcorp_rerun_programme.md`).

## Stage 0: see it (before the Europe re-run)

1. **Prices.** Add `claude-haiku-4-5` ($1 in, $5 out, $0.10 cache read,
   $1.25 cache write) to `llm.PRICES` (`peploop/llm.py:48`). Reports name
   any unpriced model instead of summing it as $0.
2. **`peploop.cli cost`.** One query over all seven ledgers:
   - `extraction`
   - `resolution.usage_json`
   - `verification.usage_json`
   - `mint_call.usage_json`
   - `title_en_call.usage_json`
   - `pcorp_call.usage`
   - `ptree_call.usage`
   
   Flags `--since` and `--by pass|model|country|week`. pepcorp's sub-pass
   (decide, verify, match) is read from the request shape. Start from the
   session's scratch `costs.py` and move it into `peploop/costs.py`, using
   `llm.cost`.
3. **Dollars in every run's output.** extract (`cli.py:247`), resolve
   (`_resolve_all`), verify (`_verify_people`) and titles
   (`titles.cost`, `cli.py:745`) print $ beside their tokens, as
   `corp/report.py:22`, `tree/report.py:50` and `mint_write.py:520` already
   do. Each history.md run row gets a $ column.

## Stage 1: one ask layer

This is the alignment item, and it puts the estimate, the budget and batching
in one place.

- **`llm.Ledger(table)`** replaces the identical `content_key`, `recorded`,
  `ask` and `cost` in `corp/decide.py:270-380` and `tree/repair.py:342-455`.
  `corp/verify.py` and `corp/match.py` use it through decide today and will
  use it directly. **Keys stay byte-identical** (`sha256(model\nprompt_hash\nmessage)`).
- **`llm.send(request, pass_)`** is the one function that talks to the API:
  `messages.parse`, or `messages.stream` for categorize. It wraps the copied
  `ask` bodies:
  - `extract.py:198`
  - `verify.py:259`
  - `reconcile.py:471`
  - `titles.py:197`
  - `mint.py:963`, `mint.py:2448`
  - `corp/decide.py:279`, `corp/match.py:175`, `corp/verify.py:92`
  - `tree/repair.py:351`
  
  peploop's own tables and key functions stay as they are. Only the send
  moves.
- **Estimate.** `llm.estimate(pass_, model, n)` multiplies n by the pass's
  mean $/call for that model in its ledger (a mean, since the run's spend is a
  sum). With no history it falls back to another model's mean, scaled by price. Every paid verb prints
  "N to ask, ~$X" before sending. The counts already exist in:
  - `corp/decide.py:322`
  - `tree/repair.py:413`
  - mint's `dry_run` (`mint.py:1237`, `:2913`)
  - `titles.translate(dry_run=True)`
  - `_mentions_for`
  - extract's selection less the ledgered people
  - verify's selection less the ledgered proposals
  
  A `--dry-run` on each verb stops there.
- **Budget.** `llm.send` keeps a per-process running total. Past `--budget`
  (default `PEPLOOP_RUN_BUDGET`) it raises `BudgetSpent`. The driver stops
  asking, keeps what is answered (it is ledgered) and says so. A re-run
  continues. This is a cap, not a prompt, so unattended sweeps still run.
  `cost`/`check` read the same price table.
- **Shared check helpers on the way.** `expect` moves out of
  `tree/check_filter.py` into `peploop/checks.py`.

## Stage 2: the Batch API, at 50% off

- **`llm.batch(pass_, requests)`** submits `[(custom_id, params)]`. Before
  submitting, it records the batch id and its custom_ids in a new
  `llm_batch` table, the way the send ledger records a QS3 batch first. It
  polls until the batch ends, then hands each result to the pass's own
  store. An interrupted run finds its open batch and collects it instead of
  submitting again.
  - Errored or expired results go back to the live path.
  - Results arrive in any order, so they are matched by custom_id.
  - Caching inside a batch is best-effort: keep the system breakpoint and
    don't count on the hits.
- **Which passes, in this order:**
  1. corp decide (`prepare` builds every message first).
  2. tree repair (same).
  3. mint categorize. It is sent one at a time today. A batch needs no
     streaming; set `max_tokens` 64k.
  4. extract and mint verify: build their messages before the send loop
     (both are independent per person or candidate).
  5. resolve: split `resolve_mention` into retrieve+shortlist (a pool, no
     model) and ask (batched). `_reask_gained` stays a second round.
  
  Iterative rounds stay live: corp verify's fallback-quote rounds, match,
  and title rounds. They are small.
- **When.** Batch by default when a pass has more than ~50 requests to ask.
  Below that, and for `--qid` work, send live. `--live` forces live.

## Stage 3: resolve, the biggest pass

- **Article cache.** `render_mention` (`reconcile.py:258`) puts the article
  in its own content block ahead of the mention, quotes and candidates,
  with a second `cache_control`. Bump `RENDER_VERSION`. Order work so a
  person's first mention is asked before the rest of that person's
  mentions, which today race across 8 threads. In batch mode the cache is
  best-effort and keeps the 5-minute TTL; a 1h TTL doubles the write and
  stays unmeasured. The expected
  saving is ~30% of resolve's input.
- **Settled titles.** When (normalised title, jurisdiction, state) has five
  or more high-confidence resolutions to one QID and no dissent, give the
  next mention that QID without a call. Record it as a resolution with
  `model = 'memo'` and its usage empty. peploop's verify still judges the
  `P39` downstream. That covers 19.8k past calls (12%).

## Stage 4: measured trials, each at a run boundary

The model, the prompt and the render are all in the key, so each change is
made between runs, never in the middle of a country. Each trial replays a
fixed sample from the ledger and compares the answers to the stored ones.
It is capped at ~$10 by the budget.

- **mint categorize:** thinking disabled (Sonnet 5 accepts it), and a terser
  answer schema with ids, not echoed labels. Measure the agreement of
  decisions on ~20 chunks across cn, au and by. The target is half the
  output tokens.
- **tree repair, peploop verify and mint verify:** Opus 5 → Opus 5.5 ($4/$20,
  reads $0.20), and effort high → medium. Measure verdict agreement on 300
  stored answers each.
- **extract:** check output tokens against answer size at low effort. Try
  the leaner schema only if thinking is still most of the output.
- **corp decide:** strip reference and bibliography sections from articles
  before `ARTICLE_CHARS`. The 95th percentile is 17.6k tokens and the
  largest 71k. **Measured, dropped (2026-10-22):** the HTML reducer already
  removes footnotes, and the remaining link and literature sections are
  3.2% of message text (2.7% on the largest). That is not worth re-keying
  every body.

## Status (2026-10-22)

Stages 0–3 are built and checked. The real batch path was tested on a
three-request pilot. Stage 4's trials ran (~$25), and the results are in
`docs/history.md` under "Model spending". Every setting can be switched by
environment variable:
- `PEPTREE_MODEL`/`PEPTREE_EFFORT`
- `PEPLOOP_VERIFY_MODEL`/`PEPLOOP_VERIFY_EFFORT`
- `PEPLOOP_MINT_VERIFY_MODEL`/`PEPLOOP_MINT_VERIFY_EFFORT`
- `PEPLOOP_EXTRACT_THINKING`

Adopted by the user (2026-10-22): Opus 5.5, at medium effort for peptree and
peploop verify and at high for mint verify.

Open:
- extract without thinking (no loss seen, but a weak measure);
- a batch pilot on a real pass (corp decide on a small country) at the next
  run.

## Files

- `peploop/llm.py`: prices, `Ledger`, `send`, `estimate`, budget, `batch`
- new `peploop/costs.py` and a `cost` verb in `peploop/cli.py`
- `llm_batch` table: wherever peploop's schema lives (`peploop/schema.sql`)
- the pass modules listed in stage 1, and `reconcile.py` for stage 3
- new `peploop/checks.py`, `peploop/check_llm.py`

## Verification

- **`check_llm` (offline):**
  - a fabricated usage gives the expected cost for each model;
  - the estimate is computed from a fake ledger;
  - the budget stops after the n-th fake send;
  - a fake batch client is interrupted after submission, and the rerun
    collects the batch and does not resubmit.
- **Key stability.** A check over stored `pcorp_call`/`ptree_call` rows
  recomputes every key through `llm.Ledger` and expects zero changes. Run
  `corp run <cc> --no-ask` and `tree place <cc> --no-ask` before and after
  stage 1: the plans are identical and $0 is spent.
- **`cost` verb.** Its totals reproduce the per-pass table above (~$5.2k).
- **Batch pilot.** A small country's `tree place` and `corp run` under batch:
  compare the answers' shapes and the funnel against live, and the $ against
  the estimate.
- **Every lane's checks** (`check_*`, `corp.check_*`, `tree.check_*`)
  before each commit.


