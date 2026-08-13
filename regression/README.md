# Regression baseline

Verdict files and QuickStatements output from a known-good run of each campaign,
kept **outside `data/`** because `data/` is gitignored — these are the only
record of how the engine behaved before a change, and
`recipes/country_sweep.md` requires diffing against them whenever the engine is
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
The UAE baseline was added 2026-08-12 from that campaign's first (and so far
only) run — the run that removed the per-concern `.qs` split, so its
`edit_plan.qs` also carries `P53` lines.

That exception is worth knowing before diffing a `.qs` by hand: the retrieved date
comes from `--retrieved` and changes on every re-render, so compare with
`sed 's/+20..-..-..T00:00:00Z\\/11$//'` or the whole file reads as changed.

| campaign | records | `apply` records | `.qs` lines | API claims |
|---|---|---|---|---|
| ecuador | 327 | 163 | 177 | — |
| belarus | 95 | 16 | 16 | — |
| czechia | 72 | 18 | 18 | — |
| spain | 297 | 93 | 111 | — |
| uae | 136 | 86 | 94 | — |
| saudi | 283 | 44 | 43 | — |
| kuwait | 1,299 | 358 | 253 | 117 |

**The baselines above the Kuwait row predate the two-file split** (§8 of the
recipe), so their `.qs` still holds the multi-tenure lines that
`render_edit_plan.py` now routes to `edit_plan_claims.json`. That is deliberate:
they are the record of what *was applied*, and `scripts/repair_merged.py` reads
exactly those lines to recover which start belonged to which end. Do not
regenerate them to match today's renderer — the pairing would be lost, and it is
the only copy.

Their diffs are also expected to be noisy for a reason that is not the engine:
**Ecuador, Czechia, the UAE, courts and positions have since been applied**, so
re-running those campaigns drops every record whose statement now exists
(`already holds P39`). Ecuador went 327 → 232 that way. Read a shrinking
`apply` count as "the community has this now", and confirm it by checking one
vanished record against Wikidata before suspecting a regression.

The middle column counts every record the policy decided to apply, not just the
ones the `modern` rule released — an earlier version of this table said 97 for
Ecuador and 6 for Czechia, which is `apply/modern` alone and roughly half of what
those `.qs` files actually contain. A `.qs` line is a statement, except where one
claim is restated with a second reference (`wd/validate.py` reports that: Spain's
111 lines write 110 statements).

Spain's snapshot was taken after the ten `wd/roster.py` parser fixes and the
`Office.date_targets` / `already_under_sibling` additions that run required —
all three earlier campaigns were re-run against it and diffed clean, which is
the only reason those additions are in.

Kuwait was added 2026-08-13, after its batch was applied, and its baseline is the
first to carry an `edit_plan_claims.json` beside the `.qs` — the two together are
the batch, so a snapshot with only the `.qs` would understate it by 117
statements. It went in alongside four `wd/roster.py` additions (the Arabic Kuwaiti
column vocabulary, the duration decoys, and the `_subroles` fix that refines
continuation positions); all six earlier campaigns were re-run and diffed, and
the three that showed changes were traced statement-by-statement to their batches
having been applied upstream, not to the engine.

Saudi Arabia was added 2026-08-12, and its baseline is the first that spans two
scripts: `sa_offices.py` writes a verdict file per office and `sa_family.py`
writes `saudi_family.jsonl`, which the campaign owns through
`Campaign.extra_verdicts`. Re-running the campaign means running **both** before
diffing, or the kinship file reads as a wholesale delete. It went in alongside
seven `wd/roster.py` additions (the Arabic Saudi column vocabulary, the
`_first_month` scan, the dateless-stack drop) and the `wd/backtest.py` precision
fix; all five earlier campaigns were re-run and diffed clean across every one of
them, which is the only reason they are in. The backtest fix changed no record
anywhere — it only stopped three Belarusian offices and one Saudi one being
reported as parse defects they never were.

`data/positions/` (the earlier Lithuania/Bahrain run, 133 records) is not
baselined: it predates `wd/campaign.py` and is not reproducible by any current
script.

Ecuador's snapshot excludes `minister_gobierno.jsonl`, a stale file from a run
before that office key was renamed to `interior`. Because the renderer globbed
the directory, its 96 records — 91 absent from the current run — had been
rendering into `edit_plan.md`. `wd/campaign.py` now writes a `manifest.json` of
the files a campaign owns and `scripts/render_edit_plan.py` honours it, so a
renamed key can no longer strand output.
