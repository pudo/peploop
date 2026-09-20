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
| A | Rebuild the silver fixture | done, acceptance test **failed** | 532 gold rows to 270; vocabulary agreement 77.3% to 72.2%. The rules are anti-correlated with correctness. |
| B | Increment 4: ranking signals | pending | |
| C | Increment 5: the second turn | pending | |
| D | Increment 6: Poland, then Spain | pending | |
| E | Increment 7: wire into propose | pending | |

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

Where this leaves stage B: the rebuilt fixture is committed so code and data
agree, and it is a *worse* test set than the one it replaced. Before stage B
runs, pick one — revert the fixture to `fd8f36d`'s and keep the new fields
off, adopt the tolerant variant on its own merits, or accept that this set
cannot be cleaned by dates and reach for a different label source.

### B. Increment 4: ranking signals

Scored on **top-1 and MRR only** — recall cannot move. Targets named by the
failure analysis: minted-but-barely-held ministries crowd correct answers
hardest, and inbound ambassadorships are pure noise.

### C. Increment 5: the second turn

The model picks from the shortlist or declines. Costs real tokens; budget and
report it.

### D. Increment 6: Poland, then Spain

Spain is ~13,200 positions against the pilot's 343. The questions are load
time, index size, and whether Czech retrieval degrades with Spain in the same
table.

### E. Increment 7: wire into propose

`P39` with the scoping qualifier the community uses, and a creation queue row
for anything unmatched.
