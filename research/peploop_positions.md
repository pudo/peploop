# Measured: resolving a free-text office to a Wikidata QID

The evidence behind `peploop/positions.md`. That file says what the resolver
is; this says what was counted, what it cost, and which figures are one run
wide and should not be generalised. Ideas that were measured and rejected are
in `peploop/positions_discarded.md`.

**Measured 2026-09-20/21** against live WDQS and `wbgetentities` through
`peploop.wikidata.sparql` / `fetch_items`, and a local Postgres 18.6. Type
tests use `p:P31/ps:P31` where the question is "does this hold anywhere among
the values". Bench figures come from `scripts/position_bench.py --country cz`
against `peploop/fixtures/cz_positions.jsonl`; every one is re-runnable.

**The query service is the dominant variance in everything below.** The same
query has taken 51 s and 578 s on the same night, and a single grouped count
swung 66 s → 352 s. Treat one timing as an order of magnitude, not a number.

## 1. Discovery, per country

| lane | Czechia (Q213) | Poland (Q36) | Spain (Q29) | Slovenia (Q215) |
|---|---|---|---|---|
| descent | 203 / 58 s | 344 / 124 s | 13,301 / 155–611 s | 75 / 23 s |
| usage | 169 / 92 s | 270 / 209 s | 5,074 / 73–188 s | 68 / 4 s |
| citizen | 236 / 21 s | 547 / 41 s | 5,922 / 2,922–5,076 s | 92 / 176 s |
| union | 343 | 767 | 15,018 | **135** |

Czech overlaps: descent ∩ usage 161, descent-only 42, usage-only 8, union 211;
the citizen lane adds a further 132 items in neither.

Spain's citizen lane in two phases: 40,309 politicians (25 s), 1,647 diplomats
(8 s), 515 judges (8 s) → **41,899 people deduplicated in 41 s**, then 350
chunks of 120. Phase-2 cost is query-service latency and nothing about the
chunk: one chunk returned 2 offices in 82 s, another 114 in under a second.

The loaded table, 15,986 rows by source set:

| sources | rows |
|---|---|
| descent only | 8,565 |
| citizen + descent + usage | 4,534 |
| **citizen only** | **1,914** |
| descent + usage | 737 |
| citizen + usage | 125 |
| usage only | 110 |
| citizen + descent | 1 |

12% of the table is reachable by the citizen lane alone. 93 of Spain's rows
were already present from the other two countries.

**Slovenia is thin, and that is the measurement, not a bug (2026-09-22).** 135
offices against Czechia's 343, for a state with a fifth of the population but
the same institutional shape -- a National Assembly, a National Council, twenty
ministries, two apex courts, 212 municipalities. 75 of the 135 are scoped to
Q215 at all; the rest are generic classes and inbound embassies the citizen
lane reached. The whole load took 221 s and the citizen lane found 1,652
Slovenian politicians, diplomats and judges holding, between them, 92 distinct
offices. What is missing is not the famous items -- `Q21296001` member of the
National Assembly, `Q20522401` its speaker, `Q109070159` Governor of the Bank of
Slovenia and every ministry are all there, reached by all three lanes -- but
the tiers below them are barely modelled. The table holds a mayoralty for two
of 212 municipalities (Ljubljana and Trbovlje), no item scoped to Slovenia for
a constitutional or supreme court judge, and for the whole state-secretary tier
one generic `Q37494512 state secretary` carrying two Slovenian holders and no
`P1001` -- against the 307 people the seed's state-secretary categories
returned.

**An absence has to be checked against the table, not against
`wbsearchentities`.** Searching "State Secretary Slovenia" in English returns
nothing, and the item is labelled `state secretary`; searching "judge of the
Constitutional Court of Slovenia" returns nothing either, and there the absence
is real. The prefix search agreed with the table once out of twice, which is
what `CLAUDE.md` says about it.
So a Slovenian run's refusals are mostly real absences, and its creation queue
is the interesting half of its output.

## 2. What a load costs, per step

| step | Poland (767) | Spain (15,018) |
|---|---|---|
| discovery, all three lanes | 374 s | 3,150 s |
| entity fetch | 16 s | 230 s |
| type closure | 29 s | 192 s |
| referenced items | 33 s (1,239) | 310 s (20,670) |
| upsert | 5 s | 100 s |
| **total** | **457 s** | **3,983 s** |
| peak RSS | 230 MB | ~600 MB |

**Discovery is 79–82% of a load, and the citizen lane is most of that.** The
entity fetch is not the bottleneck and never was: ~1 s per 50-QID request,
linear from Poland to Spain.

## 3. The ranking signals do not scale

Five grouped queries, chunked at 120 QIDs:

| query | 343 rows (3 chunks) | 1,061 rows (9 chunks) |
|---|---|---|
| holders | 56 s | 583 s |
| holders by country | 352 s | 251 s |
| instance_count | 159 s | 390 s |
| subclass_count | 268 s | 120 s |
| held_subclasses | 149 s | 363 s |
| **total** | **984 s** | **1,706 s** |
| per request | 65.6 s | 37.9 s |

Per-request cost is flat regardless of chunk contents, so cost is
`chunks × 5 × ~1 min`. **A 15,000-row country projects to 600 requests and
6.3–10.9 hours**, which is why a large country's signals are left null — and
per §5 a null foreign count also *scores better* than a filled one.

## 4. The bench

Current, 15,986 rows, `CANDIDATE_POOL = 400`:

| slice | n | `--signals all` | `--signals none` |
|---|---|---|---|
| aggregate | 746 | 83.0% / 0.674 / 61.3% | 78.6% / 0.434 / 30.8% |
| per tenure | 688 | 83.7% / 0.682 / 61.9% | 80.1% / 0.444 / 31.5% |
| `vocab_overlap` | 578 | 94.3% / 0.782 / 72.0% | 90.3% / 0.497 / 35.6% |
| macro over 78 answers | 78 | 72.9% / 0.556 | 69.8% / 0.468 |

Ranking is worth **0.24 MRR and 30 points of top-1** over the text order.

**Per-signal deltas** (measured at 343 rows, `vocab_overlap` slice, cumulative):

| added | MRR | top-1 |
|---|---|---|
| baseline | 0.601 | 37.7% |
| + `not_office` | 0.602 | 37.7% |
| + `holders` | **0.780** | **69.2%** |
| + `class` | 0.790 | 70.4% |
| + `dates` | 0.791 | 70.4% |
| + `diplomatic` | 0.792 | 70.6% |

Each alone: `holders` 0.780/69.2%, `class` 0.616/38.1%, `dates` 0.611/39.1%,
`not_office` 0.602/37.7%, `diplomatic` 0.600/37.5%. **The holder count is the
whole of it**; the other four together are worth 0.012 MRR and 1.4 points, and
are kept for the named case each fixes and for what they tag.

**Holder scope** (1,061 rows, only the scope moving):

| scope | aggregate | overlap MRR / top-1 |
|---|---|---|
| global | 82.17% / 0.6160 / 53.08% | 0.7127 / 61.94% |
| local | **84.18% / 0.7150 / 66.09%** | **0.8337 / 78.37%** |

`local`, `local_or_global` and `local_or_zero` are **indistinguishable** once
every row has a key, so the repair is the backfill and not the rule. `local`
is adopted on principle: it is the only one that asserts no number nobody took.

**Pool curve.** At 1,061 rows the plateau completes at 200 (aggregate 82.17%,
overlap 93.94%; 400 and 2,000 identical). At 15,986 rows it completes at 400
(aggregate 82.71% → 82.98%, overlap 93.94% → 94.29%; 2,000 identical). MRR and
top-1 do not move with pool size at all. **Where the plateau falls is a
property of the table**, so re-run the curve after loading a country.

**The two constants.** `CONVENTION_FLOOR = 50`: the grid degrades above it
(0.7922 at 50, 0.7871 at 100, 0.7781 at 250) and the decisive case needs a
floor above 46; 25 and 50 differ by 0.0002, so the plateau does not choose and
the decisive case does. `HELD_SUBCLASS_FLOOR = 3`: N ∈ {2,3,5,10} are identical
to four decimals while re-tagging 10–24 items, so the threshold **cannot be
measured** beyond N ≥ 2; both endpoints are measured (N=1 is 0.7895, dropping
the clause 0.7898, so the clause is earned).

## 5. The case the aggregate metric cannot see

`Q486839` member of parliament (bare abstract, the failure to prevent) against
`Q108899569` member of a Czech municipal council (generic **by convention** —
Czechia mints no item per municipality, so the place goes in a `P1001`
qualifier):

| | holders | citizens of the state | instance | subclass | held_subclasses |
|---|---|---|---|---|---|
| Q486839 | 7,026 | 46 | 18 | 567 | 497 |
| Q108899569 | 1,799 | **1,260** | 0 | 4 | 4 |

The raw holder count is **blind** here — both saturate the bonus and the
abstract item still outranks the generic one in 202 of 223 shortlists. Only
*holders who are citizens of the state* separates them, at a floor above 46:
202/223 falls to 2/223.

**At a floor of 25 — two ten-thousandths of MRR from the optimum, well inside
the bench's plateau — the rule fires on nothing and the failure returns in
full.** A plateau is not evidence that two configurations are equivalent.

**Crowders demoted** (343 rows, mean rank and top-3 appearances, before → after):

| item | lists | mean rank | top-3 |
|---|---|---|---|
| Q110408550 Minister of Industry (8 holders) | 374 | 6.7 → 9.4 | 133 → 43 |
| Q110409158 Commerce and Travel (8) | 383 | 7.2 → 10.1 | 104 → 43 |
| Q110414308 Economic Policy (1) | 386 | 6.6 → 12.3 | 104 → 9 |
| Q110420088 ministr hospodářství (2) | 393 | 6.4 → 10.5 | 86 → 42 |
| Q101241090 inbound embassy (1) | 128 | 8.7 → 11.0 | 16 → **0** |

And under local holder scoring, `Q15964890` member of the House of Commons of
Canada — 4,694 holders, zero of them Czech, imported by Poland's citizen lane —
went from rank 1 on **74 of 746** Czech gold queries to **zero**.

## 6. Latency, the planner, table sizes

| rows | end to end (mean / median / p95) | ranking query |
|---|---|---|
| 343 | 5.79 / 4.75 / 12.8 ms | 1.66 / 0.87 / 5.06 ms |
| 1,061 | 8.31 / 6.19 / 21.5 ms | 3.05 / 1.38 / 11.8 ms |
| 15,986 | 16.99 / 11.15 / 40.24 ms | 4.23 / 2.05 / 13.76 ms |

**A 15× table costs 1.67× the search.** Pool size is nearly free: at 15,986
rows, pool 200 measured 18.75 ms mean against pool 400 at 16.12 ms — the larger
pool nominally faster, i.e. noise. The plan evaluates `ts_rank` for every
matching row whatever the `LIMIT`, so the pool decides what is *kept*, not what
is read.

**The planner does use `position_tsv_idx`** — 32 of 40 fixture queries at 1,061
rows, 33 of 40 at 15,986; table size changed nothing. The 7 that scan
sequentially are correct to: `search` ORs every content lexeme, so
`radní kraje` matches 13,712 of 15,986 rows. That tail is why p95 is four times
the median.

| state | rows | names | heap | tsv index | mean `search_text` |
|---|---|---|---|---|---|
| CZ | 343 | 11,552 | 608 kB | 6,824 kB | 3,935 chars / 509 tokens |
| +PL | 1,061 | 26,664 | 1,064 kB | 8,744 kB | 3,527 / 462 |
| +PL, signals filled | 1,061 | 26,664 | **3,792 kB** | **12 MB** | unchanged |
| +ES | 15,986 | 167,170 | 16 MB + 196 MB TOAST | 34 MB | — |

Whole database 318 MB. Note row three: five whole-table updates with no vacuum
tripled the heap and grew the GIN index 37% **with no new documents** — vacuum
after a signal fill.

Dropping the three indexes nothing read freed 13.1 MB and cut a full rewrite of
`position_name` from 221 ms to 66 ms.

## 7. The silver test set, and its error rate

723 people, 2,234 titles → **746 gold rows over 688 gold tenures**, 1,456 weak
labels, 32 with no label. 77.6% of gold rows share a token with their answer.

Pairing ablation, same 723 people, **re-measured 2026-09-21 against the
15,986-row table**, reproducible with `scripts/position_fixture.py --dry` plus
the named flags. Each row is relative to the shipped rule, since rule 1 is now
the default:

| configuration | flags | gold rows | any token | distinctive |
|---|---|---|---|---|
| **rule 1 only (shipped)** | — | **746** | **77.6%** | **77.5%** |
| no rules at all | `--no-collision` | 764 | 77.2% | 77.0% |
| rules 1+2 | `--both-endpoints` | 291 | 72.5% | 72.2% |
| rules 1+3 | `--one-to-one` | 499 | 72.5% | 72.3% |
| rules 1+2+3 | both flags | 270 | 72.6% | 72.2% |

**Read the "distinctive" column with care: it is relative to the table.** A
token counts as distinctive when it appears in under 5% of position documents,
so the threshold moves as countries are loaded. At 1,061 rows the shipped
configuration scored 66.8% here; at 15,986 it scores 77.5%, and the column has
converged with "any token" to within 0.1 points. **On a table this size the
test no longer discriminates** — it was a useful diagnostic on one country and
is close to vacuous on three. The *ordering* of the configurations is stable
across both table sizes, which is all the ablation is for.

**Strict date agreement is evidence a pair is *wrong*.** Over every candidate
pair with at least one agreeing endpoint, those agreeing on **both** share
vocabulary 64.6% of the time (n=158), against 74.0% where there is no second
endpoint to compare (n=204). An article dates a tenure by the day the holder
left and Wikidata by the day the successor was sworn in, so a real pair often
disagrees at the end; a committee post inherits its parliamentary term verbatim
from the seat it rides on and agrees perfectly.

About **22% of gold rows are mispaired** and the residue is mostly an office
with no `P39` anywhere on the person, which no re-pairing rule can reach.

## 8. Gotchas worth the line

- **One degenerate answer takes a whole pass down.** At mention 440 of a
  Slovenian run the model emitted `{"qid":null,"kind":"none...` and then
  repeated `0.0}` until it hit `MAX_TOKENS = 4000`; the structured-output
  parser raised `ValidationError: Invalid JSON: EOF while parsing a string`,
  `pool.map` propagated it, and the run stopped. Nothing was lost -- a verdict
  is stored as it is made and the ledger resumed the rest -- but a pass that
  dies at 440 of 6,000 has to be noticed and restarted by hand. One bad answer
  in 440 is the rate to plan for, so `cli.reconcile` catches per mention and
  records nothing for it, which makes the next pass ask again.
- **A BCE date crashes the load.** `-013-01` into a `DATE` column aborted a
  load at 99% of its upserts, after two hours of discovery. Neither a 343-item
  nor a 767-item country contains one: this class of bug is not testable below
  ~15,000 items. `load_country` upserts row by row under autocommit, so that
  crash left 14,834 rows committed and the rest absent — **neither a load nor a
  rollback.** Still true; not fixed.
- **`ChunkedEncodingError` on an HTTP 200 tracks query *duration*, not response
  size.** A 13,755-row answer arrives in one piece when the query is fast (4 s).
  So paging helps at offset > 0 and **never at offset 0**, where the wrapper's
  total ordering makes page 1 more work than the unpaged query.
- **A truncated body is not always deterministic**, contrary to the rule in the
  repo's `CLAUDE.md`: one query failed at page 3 and read the same three pages
  cleanly on a re-run with nothing changed.
- **`P463` does occur** in this corpus, on four items including `Q8191099`
  member.
- **An inbound mission is identified by `P17`, not `P1001`.** Only 9 of 64
  ambassadorships carry a jurisdiction at all; `coalesce(P1001, P17)` separates
  34 inbound from 30 outbound, matching the hand count in `wd/gazetteer.py`.
- **`P1365 replaces` is the modal `P39` qualifier for 50 positions.** Without a
  deny list, `scope_qualifier` reads "replaces" as the qualifier to write.

## 9. The second turn, measured (2026-09-21)

`scripts/reconcile_bench.py --country cz`, model `claude-sonnet-5`, one request per
mention, sampled round-robin over distinct gold answers. Verdicts are in the
`resolution` table; disagreements were hand-read against the person's live `P39`
and recorded in `fixtures/cz_positions_verified.jsonl`.

**The 20-row probe, first prompt, quotes only.** 13/20 agreed with silver. All
four disagreeing matches were silver mispairings (Deputy PM paired to Finance
Minister on identical dates, a Senate seat paired to a council post, ...); the
model was right in each. Three refusals with gold shown, one of them a
rendering gap: `Q30103103` (56 local holders, `P1001`, no subclasses) is not
class-like, earned no tag, and the model refused it "with no qualifier shown".

**The cache never hit.** 3,519 cache-write tokens and 0 read on every one of
the 20 requests, against 7.96M read over the extraction pass's 1,156. Six
diagnostic requests: a fixed schema reads 3,355 from cache on the second call;
a per-request `Literal` over the offered QIDs writes 3,409 every time, and two
requests with the *same* literal read it back. The structured-output schema is
in the cached prefix.

**After the fixes** (fixed schema, `used with:` at the convention floor, whole
article under 20,000 chars, bodies named, `RENDER_VERSION`): the same 20 rows
re-asked cost 183 written / 3,482 read / 3,058 input / 218 output per request.
`Q30103103` resolved at high confidence. One row flipped to a wrong refusal —
`chairperson` + `P2389` for a hunting-union chair, which the person's item
records exactly so — and two other `P2389`-scoped officers were read
inconsistently, so the prompt gained the "officer of a named organisation"
section before the 150.

**150 rows, prompt `5ea5f9f2`, render 2.** 15 minutes sequential, ~6 s per
request; per request 26 written / 3,883 read / 3,305 input / 232 output.

| | against silver | against hand-read truth |
|---|---|---|
| agreement | 88 / 150 (58.7%) | **116 / 150 (77.3%)** |
| agreement, answer on the shortlist | 76.5% | 88.2% |
| matches | 114 (76.0%) | 114 |
| matches that are wrong | 26 | **0** confirmed, 2 unknown |
| refusals | 36 | 36 |

The 36 refusals: **4 right** (silver was a bare `minister`/`member`, or a
Wikidata error — an ICTY judge recorded as ICC), **7 wrong with the answer on
the shortlist**, **11 where the right item was never retrieved**, 14 unknown.
Verdicts: `same-office` 114 (97 high, 17 medium), `none` 30, `generic-class` 6.

Of 50 hand-read disagreements the silver label was wrong in 35: the silver set's
documented ~22% mispairing is what the "false matches" were made of. Read the
silver agreement as a floor, and the verified figure as the measurement.

**Where the wrong refusals come from.** Three are cross-language
inconsistencies: "Mayor of Letohrad" (en) and "Menteri Pengembangan Regional"
(id) refused while the cs and en mentions of the same tenures matched at high
confidence; "stellvertretender Ministerpräsident" (de) refused as a world
generic where cs and fr picked the Czech Deputy PM. Two are `generic-class`
misfires on a right item (`deputy minister`, `parliamentary group leader`). The
11 not-retrieved refusals are mostly the officer-of-organisation convention —
`vice president`, `rector`, `director` + `P2389` — whose generic item the search
did not bring into the fifteen. That is a retrieval question, not a verdict one.

Refusal rate by article language: cs 22/107, all others 14/43. Small numbers;
the three cross-language cases above are the signal.
