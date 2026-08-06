# Regression baseline

Verdict files and QuickStatements output from a known-good run of each campaign,
kept **outside `data/`** because `data/` is gitignored — these are the only
record of how the engine behaved before a change, and
`recipes/category_check.md` requires diffing against them whenever the engine is
touched.

Compare with:

    python scripts/diff_verdicts.py --campaign czechia

The differ compares what records *mean* — which (person, position) pairs exist
and what was decided about each — so a change to the record schema shows up as
an empty diff rather than as every record having changed. Pass
`--rename old_=new_` when an office key changes, or the moved file reads as a
wholesale delete plus add. `--update` refreshes the baseline once a diff has
been read and understood.

## What this snapshot is

Captured 2026-08-06, from the engine as of the Czechia run (`tasks/czechia.md`).

| campaign | records | batched | `.qs` statements |
|---|---|---|---|
| ecuador | 327 | 97 | 101 |
| belarus | 95 | 10 | 10 |
| czechia | 66 | 6 | 6 |

`data/positions/` (the earlier Lithuania/Bahrain run, 133 records) is not
baselined: it predates `wd/campaign.py` and is not reproducible by any current
script.

Ecuador's snapshot excludes `minister_gobierno.jsonl`, a stale file from a run
before that office key was renamed to `interior`. Because the renderer globbed
the directory, its 96 records — 91 absent from the current run — had been
rendering into `edit_plan.md`. `wd/campaign.py` now writes a `manifest.json` of
the files a campaign owns and `scripts/render_edit_plan.py` honours it, so a
renamed key can no longer strand output.
