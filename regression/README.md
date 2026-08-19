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
| jordan | 495 | 221 | 220 | 161 (applied) |
| qatar | 158 | 71 | 71 | — |
| iran | 1,155 | 203 | 717 | 337 |

**The baselines above the Kuwait row predate the two-file split** (§8 of the
recipe), so their `.qs` still holds the multi-tenure lines that
`render_edit_plan.py` now routes to `edit_plan_claims.json`. That is deliberate:
they are the record of what *was applied*, and `scripts/repair_merged.py` reads
exactly those lines to recover which start belonged to which end. Do not
regenerate them to match today's renderer — the pairing would be lost, and it is
the only copy.

Qatar was added 2026-08-13 and its batch applied 2026-08-14, so it has now
joined every row above it in no longer reproducing — a re-run correctly drops
each of the 69 statements as `already holds P39`. The snapshot is the record of
what was proposed, not something a later run can reproduce. It went in alongside four
`wd/roster.py` additions (`طول الفترة` as a third spelling of the duration
decoy, `الأعضاء` and `Elected member` as name columns, and a free-standing `?`
in a date cell yielding no date), two `wd/kinship.py` ones (`{{Tree list}}`
genealogies, which render as a `div.treelist` the walker never descended into,
and linked honorifics — `[[Sheikha]] [[Najla bint Khalifa Al Thani]]` read the
*style* as the person), and `wd/officebox.py`, a new evidence channel.

The way it was verified is the point. `regression/` could not be the net — see
below — so every campaign was first re-run on unmodified code and snapshotted to
`data/_prechange/<campaign>/verdicts`, and each change diffed against *that*.
All eight came back "no semantic change" except one Saudi pair, traced to a
`house_records` fix that stops a person listed twice in one genealogy producing
two identical `P53` records; the `.qs` never carried the duplicate, so no batch
changed. Anyone touching the engine next should take the same snapshot first —
it costs one run of each campaign and is the only working net there is.

## This net no longer catches much, and that needs solving

**Every baseline here now diffs large, and not because the engine changed.** All
nine batches have been applied in whole or in part, so a re-run correctly drops
every record whose statement exists (`already holds P39`) — Kuwait went 1,299 →
996 differing pairs, Ecuador 327 → 232 records, Saudi Arabia from 43 statements
to 14. A baseline captured before its batch was applied cannot be reproduced
after, so "diffs clean" has stopped being available as a signal.

That was survivable while one campaign at a time was live. It is not now, and it
means the *next* engine change has no net under it. The fix is to stop letting
the net depend on live state: freeze each campaign's inputs beside its verdicts —
the cached roster HTML it parsed, and a snapshot of the holder sets and person
claims as they were — and diff against a run pinned to those. Until that exists,
verify an engine change the slow way: read `scripts/check_dates.py` (which pins
the parsing and merging directly), and check by hand that every vanished record's
statement is genuinely on Wikidata, as was done on 2026-08-13 for Ecuador,
Belarus and Czechia.

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

Jordan was added 2026-08-13 and **refreshed the same day**, after its API half
(161 statements for 60 people) had been applied and after the `already_under_sibling`
fix below. The snapshot in the table is the post-application one, so it is the
number the `.qs` in this directory actually carries.

Its API half was unusually large for the size of the campaign — 60 of 275
applying records were people with several tenures in one office — because a
minister who served four consecutive governments is four rows on four cabinet
articles and one continuous tenure once `merge_terms` is done with them.

The refresh was not cosmetic. `already_under_sibling` took its sibling set from
*all* of an office's targets, which is right for an office spread across era
items (Spain files one presidency of the Congress across four) and wrong for a
bucket lane: Jordan's cabinet is one `Office` routing forty ministries, so every
portfolio read as a sibling of every other and a minister holding two at once —
Ahmad al-Tarawneh was Justice and Education across the same span — had one
skipped as a duplicate of the other. Thirteen true statements were being
suppressed, and the cabinet lane's backtest read 88% on targets and 75% on dates
because of it; with era siblings kept and portfolio siblings dropped it reads
99% and 89%. Spain, the UAE, Saudi Arabia and Kuwait were all re-run against the
change and none gained a record; Saudi Arabia's single cross-portfolio false
duplicate correctly stopped being one.

It went in alongside five `wd/roster.py` column keys (the Jordanian Arabic
vocabulary: `غادر`, `الرئيس`, `عضو`, `تاريخ اليمين`, `المهام`), the
`wd/kinship.py` nesting and couple-line work, and `wd.campaign._title_chunks`.
Kuwait — the only other campaign whose baseline post-dates its batch — was
re-run against all of it and showed no new records and no changed decisions.

`data/positions/` (the earlier Lithuania/Bahrain run, 133 records) is not
baselined: it predates `wd/campaign.py` and is not reproducible by any current
script.

Ecuador's snapshot excludes `minister_gobierno.jsonl`, a stale file from a run
before that office key was renamed to `interior`. Because the renderer globbed
the directory, its 96 records — 91 absent from the current run — had been
rendering into `edit_plan.md`. `wd/campaign.py` now writes a `manifest.json` of
the files a campaign owns and `scripts/render_edit_plan.py` honours it, so a
renamed key can no longer strand output.
