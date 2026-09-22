---
description: Slovenia sweep through peploop — country scoping on the person table, the si position index, a wide sl.wikipedia seed, reconcile as a command, P39 proposals, and the match shortlist in the review TUI
date: 2026-09-22
tags: [peploop, slovenia, positions, p39, reconcile, tui, review]
---

# Slovenia: the first peploop country after the pilot

The deliverable is a review session: `peploop review --country si` showing
Slovenian people with their proposals, **including P39 matches with the
candidate shortlist the resolver saw**. Nothing is written to Wikidata.

## What stands between here and that

Round 1 runs end to end on Czechia. Round 2's resolver is built and measured —
`research/peploop_positions.md` §9: 150 Czech mentions, 77.3% against hand-read
truth, 0 confirmed wrong matches — but three things are missing, the first of
which `positions.md:240-254` names itself:

1. `propose` skips positions; they sit in `extraction.response_json`.
2. `reconcile` has no CLI command — `resolve_mention` is driven only by
   `scripts/reconcile_bench.py` over a fixture.
3. The TUI draws `P39` (`PROPERTY_NAMES`, `existing_values`, `SPAN_QUALIFIERS`)
   but cannot show the mention, the verdict or the shortlist, so a wrong office
   is unjudgeable.

Slovenia itself is greenfield: no seed, no rows in `position`, no mention in the
repo.

## Decisions

- **Wide seed.** `Slovenski politiki` (1,778 pages, 61 subcats) plus the ten
  `Poslanci N. državnega zbora` convocations, ministers, courts, mayors,
  diplomats. Accepts the non-PEP tail cz.yml deliberately excluded.
- **P39 rows plus a shortlist pane**, not a second TUI. The unit of review stays
  the person; a key on a P39 row opens the mention, the verdict and the
  candidates in rank order with the pick marked.
- **A `country` column on `person`**, stamped at seed time and threaded through
  every command as `--country`. The alternative — a database per country —
  would rebuild the shared `position`, `type_edge` and `http_cache` tables for
  each one.

## Phases

0. This document.
1. **Country scoping.** `person.country`, `seed --country`, a `--country` filter
   in the selection helpers (`cli.py:_select`, `review.select_people`) rather
   than in each command. Slovenian tokens into `check_neutral.TOKENS`.
2. **The si position index.** `load-positions` → `position-signals` →
   `VACUUM (ANALYZE) position` → `position-stats`. `rigour` resolves `si → Q215`
   with no code change. Czech/Poland scale expected.
3. **`seeds/si.yml` and the sweep.** Categories listed from sl.wikipedia's own
   API; five `dump` files read by hand before the full `run`, because the
   extraction prompt has only ever been judged on Czech.
4. **`reconcile` as a command.** Selects that country's unresolved mentions and
   calls `resolve_mention`, which is already resumable on
   (prompt hash, `RENDER_VERSION`).
5. **`propose` emits P39.** Exactly the `resolution.qid IS NOT NULL` rows —
   `settle()` already guarantees those are `same-office`/`renamed` and on the
   shortlist, so no new judgement enters here.
6. **The TUI pane** and one new reject reason, `wrong_office`.
7. **Review.**

## Two things that will bite if forgotten

- **`render` must skip P39.** QuickStatements matches a line on subject,
  property and *value*, folding qualifiers into the statement it finds, so two
  tenures of one office collapse into one P39 carrying both starts. The API path
  (`apply.py`, `wbeditentity`) creates and never merges; it is the only safe
  route for positions.
- **Slovenia is the fourth country in one shared index.** `positions.md:248-254`
  records that the third cost 1.5 points of aggregate recall and 4.8 of top-1,
  and the open question there is unresolved. Measure it in phase 4 against a
  Slovenian silver set rather than assuming it transfers.

## Not in scope

Writing to Wikidata; minting the creation queue's office items; birthplace
reconciliation; the `wd/` campaign engine and its `coverage/`, `regression/`
artifacts.
