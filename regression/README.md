# Regression baseline

Verdict files and QuickStatements output from a known-good run of each campaign,
kept **outside `data/`** because `data/` is gitignored — these are the only
record of how the engine behaved before a change, and
`recipes/category_check.md` requires diffing against them whenever the engine is
touched.

Compare with:

    python scripts/diff_verdicts.py --campaign czechia

`--update` refuses to overwrite a baseline whose diff is not empty unless you
also pass `--force`; it used to overwrite unconditionally, which turns a
regression net into a copy of the last run. It now also refreshes
`edit_plan.qs` and `manifest.json`, which previously drifted.

The differ compares what records *mean* — which (person, position) pairs exist
and what was decided about each — so a change to the record schema shows up as
an empty diff rather than as every record having changed. Pass
`--rename old_=new_` when an office key changes, or the moved file reads as a
wholesale delete plus add. `--update` refreshes the baseline once a diff has
been read and understood.

## What this snapshot is

Captured 2026-08-06; Spain refreshed 2026-08-07 after `wd/backtest.py`,
`wd/validate.py` and the `del`-date fix in `wd/roster.py`. All four campaigns'
verdicts came out semantically identical across that change and every `.qs` line
was unchanged **except its `S813` retrieved date**, which is what let it land.

That exception is worth knowing before diffing a `.qs` by hand: the retrieved date
comes from `--retrieved` and changes on every re-render, so compare with
`sed 's/+20..-..-..T00:00:00Z\\/11$//'` or the whole file reads as changed.

| campaign | records | `apply` records | `.qs` lines |
|---|---|---|---|
| ecuador | 327 | 163 | 177 |
| belarus | 95 | 16 | 16 |
| czechia | 72 | 18 | 18 |
| spain | 297 | 93 | 111 |

The middle column counts every record the policy decided to apply, not just the
ones the `modern` rule released — an earlier version of this table said 97 for
Ecuador and 6 for Czechia, which is `apply/modern` alone and roughly half of what
those `.qs` files actually contain. A `.qs` line is a statement, except where one
claim is restated with a second reference (`wd/validate.py` reports that: Spain's
111 lines write 110 statements).

Spain's snapshot is from the run described in `tasks/spain.md`, taken after the
ten parser fixes and the `date_targets` / `already_under_sibling` additions that
run required — all three earlier campaigns were re-run against it and diffed
clean, which is the only reason those additions are in.

`data/positions/` (the earlier Lithuania/Bahrain run, 133 records) is not
baselined: it predates `wd/campaign.py` and is not reproducible by any current
script.

Ecuador's snapshot excludes `minister_gobierno.jsonl`, a stale file from a run
before that office key was renamed to `interior`. Because the renderer globbed
the directory, its 96 records — 91 absent from the current run — had been
rendering into `edit_plan.md`. `wd/campaign.py` now writes a `manifest.json` of
the files a campaign owns and `scripts/render_edit_plan.py` honours it, so a
renamed key can no longer strand output.
