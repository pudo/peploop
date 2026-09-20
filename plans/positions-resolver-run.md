---
description: Overnight build of the round-2 position resolver, increments 4-7 of peploop/positions.md, with the Poland and Spain scale experiments
date: 2026-09-20
tags: [peploop, positions, reconciliation, wikidata, overnight]
---

# Position resolver: overnight run ledger

One subagent at a time. This file is the state: each stage records what it
measured and what it decided, so a later stage never re-derives it and a
session that loses context can resume from here.

## The goal

A free-text office title from a Wikipedia article resolves to a Wikidata QID,
or is recorded as unresolvable with its evidence. Measured end to end on the
Czech pilot, then shown to survive Poland and Spain.

## Standing rules for every stage

- **A measurement is the deliverable.** Report the number; never tune toward
  one. A disappointing result stops the stage and is written down here.
- **Simplify on error.** Two failed attempts at the same thing means the
  approach is wrong, not that it needs a third. Step back, write down what
  broke, take the smaller path.
- **Nothing is filtered, only ordered.** An abolished office, an occupation
  mistyped as an office, a foreign-scoped post: all stay in the table, tagged.
- **No PEP policy anywhere.** No `is_pep`, no topics, no 1990 cutoff, no
  municipal-country list. peploop maps narrative to positions of any kind.
- `peploop/check_neutral.py` must stay at zero hits: no country token in
  `peploop/*.py` or `peploop/prompts/*.md`.
- Commit per stage, push when a stage is green.

## Where things stand

Increments 0, 2 and 3 are done, pushed through `fd8f36d`.

Retrieval on the pilot, flat `search_text` document per position ranked by
`ts_rank`:

| measure | value |
|---|---|
| aggregate recall@15 (532 gold rows) | 82.5% |
| macro recall@15 (72 gold answers) | 81.1% |
| recall@15 over the 400 answerable rows | 95.5% |
| MRR (macro) | 0.553 |
| top-1 | 40.6% |
| titles retrieving nothing | 0.0% |
| search latency | ~6 ms end to end, 1.8 ms for the ranking query |

**Retrieval is finished.** At k=15 every gold row whose title shares
distinctive vocabulary with its answer is already retrieved; raising k to 200
adds 44 rows and not one of them has a defensible label. What remains is
ordering inside the fifteen, and the quality of the test set.

## Stages

| # | stage | state | outcome |
|---|---|---|---|
| A | Rebuild the silver fixture | done, **resolved** | Two of three rules measured harmful and were dropped. Rule 1 alone: 746 gold rows at 77.5% / 66.8% agreement, beating the superseded set on both readings with 40% more rows. |
| B | Increment 4: ranking signals | done, **resolved** | One signal carries the stage: a holder count is worth 0.18 MRR and 32 points of top-1 on the primary slice, the other four together 0.012 and 1.4. The date *boost* is measured destructive and ships at zero weight. `Q486839` and `Q108899569` are separated mechanically, by a floor above 46 in-country holders. |
| C | Increment 5: the second turn | **built, not run** | Still no `ANTHROPIC_API_KEY` on this host. Everything up to the call exists — frozen prompt, closed verdict set, per-request schema closing the pick over the offered QIDs, `settle`, the assembled request — and `python -m peploop.check_reconcile` pins it at 0 failures with no network and no tokens. No agreement number exists, because nothing was asked. |
| D | Increment 6: Poland, then Spain | done, **resolved with a defect** | Poland loads in 457 s, 82% of it discovery. Spain does not: its 13,300-row response cannot be read to the end (three attempts, `ChunkedEncodingError`), though the query itself finishes. Czech recall falls 81.6% to 79.4% on Poland's rows alone, and filling those rows' holder counts costs a further 0.08 MRR and 11 points of top-1. Signals project to 6.3–10.9 h for a Spain-sized table. |
| E | Repair what scale found | done, **2 of 3 resolved** | Depth: a 200-row pool re-ranked to 15 buys 2.8 points of aggregate recall and nothing at all without a re-ranker. Local holder scoring: **+0.099 MRR and 13 points of top-1**, the largest move since the holder count itself, and the repair is the backfill rather than the rule. Spain: paging fixes the query three attempts could not receive (13,301 items, twice) and `usage` too, but `citizen` fails at offset 0, where a page is *larger* work than the unpaged query. Spain is not loaded and the bench is unchanged. |
| F | Increment 7: wire into propose | pending | |

### A. Rebuild the silver fixture

The pairing heuristic mislabels about a quarter of the gold set, which now
bounds what anything downstream can be shown to do. 132 of 532 gold rows share
no token at all with their own answer, and a stricter reading puts it at 197.
The mechanism is not date precision (89.5% of pairs are day-precision) but
correlated offices: a deputy elected on a given day also becomes deputy chair
of their parliamentary club that day, and the club post inherits the chamber
seat as its label.

Constraint that shapes the design: **a silver set selected by text overlap
cannot measure text retrieval.** Pairing stays date- and structure-driven;
vocabulary agreement is recorded as a diagnostic, never used to select.

#### Outcome (2026-09-20): built as specified, and it made the set worse

All four rules are in `scripts/position_fixture.py` and every row now carries
`tenure_id`, `evidence`, `vocab_overlap` and `vocab_distinctive`. The rebuild
runs, the bench reports per tenure, `check_neutral` is at zero. The
measurement says the premise is wrong.

| fixture | gold rows | gold tenures | shares any token | shares a distinctive token |
|---|---|---|---|---|
| shipped before (`fd8f36d`) | 532 | 357 | 77.3% | 65.4% |
| rebuilt, rules 1+2+3 | 270 | 244 | 72.2% | 58.1% |

The acceptance test was that agreement should rise well above 63%. It fell,
on both readings, while the set halved. Ablated one rule at a time over the
same 723 people (the diagnostic is the same code that writes the row):

| configuration | gold rows | any token | distinctive |
|---|---|---|---|
| the shipped heuristic (superseded code) | 532 | 77.3% | 65.4% |
| every rule off | 764 | 77.1% | 66.1% |
| rule 1 alone, language collision | 746 | 77.5% | 66.8% |
| rule 2 alone, both endpoints | 305 | 71.8% | 57.0% |
| rule 3 alone, one-to-one per tenure | 517 | 72.0% | 58.2% |
| rules 1+3 | 499 | 72.3% | 58.9% |
| rules 1+2+3, as specified | 270 | 72.2% | 58.1% |
| rules 1+2+3, endpoints tolerant to 1 year | 452 | 78.5% | 65.5% |

Reproduce any row with `scripts/position_fixture.py --dry` plus
`--no-collision` / `--loose-endpoints` / `--no-one-to-one` / `--tolerance`.

**The rules select against the right answers.** Of the 411 old gold rows that
share vocabulary with their answer, 44.3% survive; of the 121 that do not,
57.0% survive. Two measurements say why:

- Over every (tenure, P39) pair with at least one agreeing endpoint, the ones
  where **both** endpoints agree share vocabulary 64.6% of the time (n=158),
  against 70.6% where the second endpoint disagrees (n=677) and 74.0% where
  there is no second endpoint to compare (n=204). Strict date agreement is
  *evidence against* the pair being right on this corpus.
- The mechanism is the reverse of the one assumed. An article dates a real
  tenure by the day the person left; Wikidata dates it by the day the
  successor was sworn in. `Q10819807` "Prime Minister of the Czech Republic"
  runs 2017-12-06..2021-11-28 in the article and 2017-12-06..2021-12-17 on
  `Q3409229` — exact to the day at the start, nineteen days out at the end,
  and rule 2 throws it away. Meanwhile the *artefact* pairs agree perfectly,
  because a committee post inherits the parliamentary term verbatim from the
  seat it rides on: `Q12023211`'s "předseda Výboru pro obranu" 2006..2010 sits
  exactly on the `Q19803234` statement 2006-06-03..2010-06-03, both endpoints,
  and no date rule can tell it from a real one.

Rule 1 is the only one that pays, and only just: it is the case the evidence
named, but it fires on 14 rows because correlated offices usually differ in
their *end* date and so never land in one group. Against the permissive
baseline it costs 18 rows and buys 0.4 and 0.7 points.

The tolerant variant is recorded because it was measured, **not adopted**:
choosing a tolerance from {0, 1, 2} by which one raises the acceptance metric
is tuning toward the number, which this file forbids. It is the user's call.

#### Resolution: keep the rule that pays, drop the two that do not

Rule 1 alone is now the default; rules 2 and 3 survive as `--both-endpoints`
and `--one-to-one` so the ablation stays reproducible. It is not a tuned
choice — it is the only configuration that beats the superseded set on
*both* readings, and it does so with 40% more rows:

| fixture | gold rows | any token | distinctive |
|---|---|---|---|
| superseded | 532 | 77.3% | 65.4% |
| rules 1+2+3 as specified | 270 | 72.2% | 58.1% |
| **rule 1 alone, adopted** | **746** | **77.5%** | **66.8%** |

The tolerant variant stays unadopted for the reason stage A gave: picking a
tolerance by which value raises the acceptance metric is tuning.

**Dates are exhausted as a labelling channel, and that is the finding.** The
residual mispairs are mostly cases where the right answer is absent from the
person's record entirely — a committee post with no `P39` of its own — so no
re-pairing rule can reach them. Two consequences carried into stage B:

- The honest primary for a *ranking* change is MRR and top-1 over the
  `vocab_distinctive` slice. Circularity poisons a recall measurement made
  that way, but not a comparison between two orderings of the same candidate
  set, which is all stage B does.
- Per-tenure is reported beside per-title, because "tenures reconciled" is
  what the loop is actually for.

#### Baseline for stage B (2026-09-20, rule-1-only fixture)

| slice | n | recall@15 | MRR | top-1 |
|---|---|---|---|---|
| aggregate | 746 | 81.6% | 0.528 | 33.8% |
| deduplicated by tenure | 688 | 82.1% | 0.534 | 34.2% |
| macro over 78 answers | 78 | 74.9% | 0.512 | — |
| `vocab_overlap` true | 578 | 93.4% | 0.601 | 37.7% |

Not comparable to anything measured against the superseded set.

### B. Increment 4: ranking signals

Scored on **top-1 and MRR only** — recall cannot move. Targets named by the
failure analysis: minted-but-barely-held ministries crowd correct answers
hardest, and inbound ambassadorships are pure noise.

#### Outcome (2026-09-20)

Five nullable columns filled from five grouped query-service queries plus two
free local ones, and the ordering moved in Python over the same candidate set
the text index returned — so recall@15 is **identical in every configuration
below**, 93.4% on the primary slice, and nothing here is a recall result.

| config | aggregate (746) | per tenure (688) | macro (78) | `vocab_overlap` (578) |
|---|---|---|---|---|
| baseline `b4ff356` | 0.528 / 33.8% | 0.534 / 34.2% | 0.512 | 0.601 / 37.7% |
| + `not_office` | 0.528 / 33.8% | 0.535 / 34.2% | 0.515 | 0.602 / 37.7% |
| + `holders` | 0.670 / 58.8% | 0.682 / 60.2% | 0.539 | 0.780 / 69.2% |
| + `class` | 0.679 / 59.8% | 0.690 / 61.0% | 0.545 | 0.790 / 70.4% |
| + `dates` | 0.680 / 59.8% | 0.691 / 61.0% | 0.547 | 0.791 / 70.4% |
| + `diplomatic` | **0.681 / 59.9%** | **0.692 / 61.2%** | **0.558** | **0.792 / 70.6%** |

**A holder count is the stage.** It is worth 0.18 of MRR and 32 points of
top-1 on the primary slice; everything else together is worth 0.012 and 1.4.
The four small signals stay for the case each one fixes and for what they tag,
not for their share of a mean.

**One signal was measured harmful and half of it was dropped.** The design's
date-fit *boost* — an abolished office boosted for a tenure that ended before
it — costs 0.08 MRR and 16 points of top-1, because an inception preceding a
tenure is true of nearly every old office and the bonus reaches the wrong
candidates as freely as the right one. The conflict penalty pays about a
thousandth and ships; the boost ships at zero weight with its tag intact.

**The two constants.** The convention floor is **50 citizens of the state**,
determined by two constraints meeting: the grid degrades above 100, and the
decisive case needs a floor above 46. `held_subclasses ≥ N` **cannot be
measured** beyond `N ≥ 2` — 2, 3, 5 and 10 score identically to four decimals
while the rule re-tags between 24 and 10 items, so those items never come near
the top of a scored shortlist. N=1 and dropping the clause are both worse than
the plateau, so the clause is earned and its threshold is not; the declared 3
stays because it is inside the plateau.

**The decisive test resolves, and the aggregate metric could not see it.**
`Q486839` member of parliament outranks `Q108899569` member of a Czech
municipal council in 202 of the 223 shortlists that hold both, on the text
order and still after the holder signal — both saturate its bonus. With the
floor at 50 it is 2 of 223. With the floor at 25, where the bench's MRR is two
ten-thousandths lower, it is 202 of 223 again. The measurement that decided
this is a two-item rank comparison, not the bench.

Carried into stage C: the shortlist a model reads now arrives with tags
(`not-office`, `unheld`, `abstract`, `generic-by-convention`, `abolished`,
`date-conflict`, `inbound-diplomatic`, `diplomatic`, `foreign-scoped`) and a
`scope_qualifier` saying which property makes a generic office concrete. The
full account, with the query timings and three corrections to earlier notes,
is the 2026-09-20 ranking-signals section of `peploop/positions.md`.

### C. Increment 5: the second turn — blocked on a missing credential

`positions.md`'s VPS-move table lists `ANTHROPIC_API_KEY` as a thing that had
to come across from `.envrc`. It did not: there is no `.envrc`, no `.env`, and
nothing in any shell profile on this host. `~/.config/wikibase-cli/config.json`
*is* present, so the write path would work; the read path that asks a model
anything does not.

Rather than stall the night on it, the order changes: **D runs first**, and C
is then built to the point of being runnable — the prompt file, the candidate
rendering, the schema, the plumbing, all testable offline — with the API calls
left for whenever a key exists. Nothing about D depends on C.

#### Outcome (2026-09-20): built to the call, and the offline half is most of it

Three artefacts and a check, with the full account in the increment-5 section
of `peploop/positions.md`:

- `peploop/prompts/reconcile.md`, frozen and hashed, carrying the body/seat
  rule that `wd/gazetteer.py:Gazetteer.render` had and the earlier passes'
  prompts did not, a glossary of all ten tags the ranking derives, and the
  closed verdict set.
- `peploop/reconcile.py`: the candidate line
  (`QID | label | description | kind | part of | exists | holders | tags | matched`),
  the per-office message, `verdict_schema(qids)` closing `qid` over the
  offered QIDs with a per-request `Literal`, `settle` mirroring
  `wd/rerank.py:settle` as a pure function, and `request_for` assembling the
  whole request without sending it.
- `peploop/check_reconcile.py`, run as `python -m peploop.check_reconcile`:
  **0 failures**, no network, no key, no tokens. It pins five candidate lines
  byte for byte, the whole user message, `settle` on each of the six kinds,
  off-shortlist refusal on both channels, the prompt's sha256, and — the pin
  worth having — that the set of tags `positions.tags_for` can derive *equals*
  the set the prompt explains, so a signal cannot move a row unexplained.

Two things this does **not** produce, and neither is a cost compromise: there
is no agreement-with-gold number and no verdict distribution, because nothing
was asked of a model. `propose` still skips positions.

### D. Increment 6: Poland, then Spain

Spain is ~13,200 positions against the pilot's 343. The questions are load
time, index size, and whether Czech retrieval degrades with Spain in the same
table.

#### Outcome (2026-09-20): the third question is the stage

Full account, with every table, is the 2026-09-20 scale section of
`peploop/positions.md`. The five things a later stage needs from here:

**Poland loads; the cost is discovery and nothing else.** 767 items, 21,235
names, 457 s end to end, 230 MB peak. 374 of those seconds are the three
discovery queries; the entity fetch — named in advance as the likely
bottleneck for a large country — took 16 s for 767 items, about a second per
50-QID request, and projects to under five minutes for Spain.

**Spain does not load, and the reason is the transfer rather than the query.**
Three attempts, each dying with `ChunkedEncodingError: Response ended
prematurely` while reading the body of an HTTP 200. The descent query
*completed* twice — once in 188 s, once served from the query service's own
cache in under a second — so the item count is confirmed at **13,300** and the
query is affordable. The failure is in body iteration, past where the retry
policy reaches. Nothing was weakened and no fourth attempt was made. The fix
is the repo's standing rule for this failure, bisect the chunk: page discovery
with `LIMIT`/`OFFSET`. That is the next increment's first task.

**Czech recall moved, which the brief said would be the most important
result.** 81.6% to 79.4% aggregate, 93.4% to 91.3% on the primary slice, from
767 Polish rows alone. Attributable: removing them restores 81.9%, and 78 of
the 80 newly-displaced answers have a new row above them. It is not a foreign
item being genuinely better — it is that `search` cuts to `LIMIT 15` in SQL on
a score with massive ties, before any signal runs, so a row the cut drops is
unrecoverable. The answer is within the text top 200 for 90.1% of gold rows,
and re-ranking a top-200 candidate set down to fifteen scores **83.2% recall /
0.699 MRR**, better than this table managed with one country in it. Retrieval
depth is a parameter the design never had to choose before.

**Filling a foreign country's holder counts is worse than leaving them null.**
With Poland's signals null the Czech ordering *improves* (0.808 MRR on the
primary slice against 0.792); filled, it falls to 0.707 and loses eleven
points of top-1. One item does most of it: `Q15964890` member of the House of
Commons of Canada, 4,694 holders, imported by *Poland's* citizen lane, is now
rank 1 for 74 of 746 Czech gold queries. The holder count is a global quantity
being scored as a local one, and increment 4 could not see it because on one
country the largest holder counts were that country's own. `holders_by_country`
is the intended repair; it measured at only +0.006 MRR here, but only because
`fill_counts` writes that map under the state it was run with, so the 718 rows
Poland created carry no Czech key and the fallback fires on exactly the
offending rows. Re-measuring it needs one query over the table, which the
query service refused with repeated 504s at the end of the night. **Untested,
not disproven.**

**The signals cost six to eleven hours for a Spain-sized table.** Per-request
cost is flat at 38–66 s regardless of chunk contents, so the bill is chunks ×
five queries × a minute: 600 requests for ~14,400 rows. Poland's own fill took
1,706 s for 1,061 rows. Combined with the finding above, leaving a large
country's signals null is not a cost compromise — it is the better of the two
configurations measured.

Housekeeping done: the three indexes nothing reads are dropped (13.1 MB, and a
full rewrite of `position_name` went 221 ms to 66 ms). `load_country` and
`discover` now log a timing per step, which is how the table above exists.

### E. Repair what scale found

Stage D diagnosed three defects and fixed none of them; this stage is the
repair, in three steps with the bench re-run between each so the deltas are
attributable. Nothing here is new functionality.

#### E1. Retrieval depth (2026-09-20): done

`search` cut to `LIMIT 15` in SQL, on a text score that is a count of
matched lexemes and therefore ties by the dozen, with `qid` breaking the tie
alphabetically. The ranking signals never saw the rows the cut removed. Now
SQL returns `CANDIDATE_POOL` rows (200), the signals order all of them in
Python, and the cut happens last; display names are looked up after the cut,
so their cost stays proportional to the shortlist.

| slice | before (pool 15) | after (pool 200) |
|---|---|---|
| aggregate, 746 rows | 79.4% / 0.611 / 52.8% | **82.2% / 0.616 / 53.1%** |
| per tenure, 688 | 80.5% / 0.625 / 54.4% | 82.7% / 0.630 / 54.7% |
| macro over 78 answers | 70.7% / 0.519 | 71.3% / 0.522 |
| `vocab_overlap`, 578 | 91.3% / 0.707 / 61.6% | **93.9% / 0.713 / 61.9%** |
| `--signals none`, aggregate | 79.4% / 0.464 / 31.4% | 79.4% / 0.464 / 31.4% |

Three things the curve settled, in `positions.md`'s retrieval-depth section:

- **The plateau begins at 100 and is complete at 200.** 400, 800 and a pool
  larger than any query's match set score identically to four decimals, so
  200 is not a tuned number; it is the smallest pool at the ceiling.
- **Depth is worth nothing without a re-ranker.** `--signals none` is
  identical at every pool size to every decimal, because a deeper pool cut
  back to the same fifteen in the same order is the same fifteen. Depth pays
  only because something re-orders the pool, and the old code was pruning
  the candidate set by the criterion the signals exist to improve on.
- **It is cheap.** A thirteenfold pool costs 14% of the search: 8.06 ms to
  9.19 ms mean over 300 queries at 1,061 rows.

Stage D's projection of "83.2% recall / 0.699 MRR" for a top-200 pool does
**not** reproduce; the measured pair is 82.2% / 0.616, and no pool size
gives 0.699 on any slice. The projection came from a probe, not the bench.

#### E2. The holder count, counted where the search is (2026-09-20): done

Two changes, and the code is the smaller one. `holder_count()` reads
`holders_by_country[state]` for the bonus and `unheld`, with **silence** for
a row nobody has counted there — not the global count, which is what
increment 4 scored and what put a foreign lower-house seat with 4,694
holders at rank 1 for 74 of 746 Czech queries. `fill_local_holders`
(`position-signals --local-holders`) then fills the key for the rows another
country's load created: 718 rows, 12 chunks of 60, **1,005 s**, per chunk
7 s to 427 s with no relation to its contents.

| scope | aggregate | `vocab_overlap` |
|---|---|---|
| `global` (increment 4) | 82.2% / 0.616 / 53.1% | 93.9% / 0.713 / 61.9% |
| **`local`, adopted** | **84.2% / 0.715 / 66.1%** | **95.0% / 0.834 / 78.4%** |
| `--signals none` | 79.4% / 0.464 / 31.4% | 91.3% / 0.534 / 36.3% |

The `global` row is bit-identical before and after the backfill, so the
whole delta is the scope of one count and nothing else moved.

Three things to carry forward:

- **`local`, `local_or_global` and `local_or_zero` score identically** to
  every decimal, because after the backfill no row has a missing count for
  them to disagree about. The repair is the data. Stage D's +0.006 for
  `local_or_global` was measuring a fallback firing on exactly the rows that
  caused the damage; `local` is adopted on the principle that it is the only
  rule that asserts no number nobody took, not on a measured margin.
- **The decisive case of increment 4 survives.** The generic parliament item
  leads the local council item in 2 of 341 orderings holding both, against 3
  before; the convention floor of 50 is untouched (46 local holders against
  1,260).
- **The pool curve is flatter than it looked.** Under `local`, 400 finds
  three more rows than 200 and 2,000 gives one back, with MRR and top-1
  static past 100. Non-monotone in its own parameter is noise; 200 stays.

#### E3. Paged discovery (2026-09-20): two thirds, and the third needs a
different query

`discover` wraps each query as a subselect under `ORDER BY ?pos LIMIT n
OFFSET m`, 2,000 a page, stopping on the first short page. Validated
against a 13,755-row answer: unpaged 4 s, paged 128 s over seven pages,
**identical sets**.

| query | pages | items | time |
|---|---|---|---|
| descent | 7 | 13,301 | 474 s |
| usage | 3 | 5,073 | 533 s |
| citizen | 0 | — | `ChunkedEncodingError` at offset 0 |

**The descent is solved** — it is the query three unpaged attempts could not
receive, and it arrived twice, confirming the count at 13,299/13,301. Peak
RSS 121 MB. The `usage` truncation seen in the first paged run did not
recur, so it was transient.

`citizen` is the finding. It fails on its *first* page, which is where
paging cannot help by construction: at offset 0 the wrapper adds a total
ordering over the whole result set to the most expensive of the three
queries, so the page is more work than the unpaged query, not less.
Bisecting it changes nothing. A halving handler was written for the
truncated-body case, never fired, and was removed rather than shipped
untested.

`load_country` writes nothing until all three queries answer, so **Spain is
not in the table**, it stands at 1,061 rows, and the question stage D asked
— does a small country's retrieval survive a large one — is still open. The
next attempt is a different shape of `citizen` query, which is a decision
rather than a retry.

### F. Increment 7: wire into propose

`P39` with the scoping qualifier the community uses, and a creation queue row
for anything unmatched.
