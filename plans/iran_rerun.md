---
description: Systematic re-run of the Iran sweep, driven by coverage/iran.md — close the 11 not-attempted and 7 creation-first institutions the first run never reached
date: 2026-08-19
tags: [wikidata, iran, country-sweep, coverage, creation-gate]
---

# Iran re-run — closing the ledger

The first Iran run shipped 1,054 statements and reported itself complete.
`coverage/iran.md` — written after it, under the method it prompted — reads
**NOT CLOSED**: 11 institutions `not-attempted`, 7 `⊘ creation-first`, and the
largest single lane (903 provincial-governor rows) untouched. This run closes
that ledger. The first run is not re-litigated; its statements are live and the
`already holds P39` gate skips them.

Run order is `recipes/country_sweep.md`'s: **triage the shared blockers first,
run the creation gate second, harvest last** — the inverse of what produced the
gaps.

## Phase C — triage (serial, one owner, before any lane)

Four blockers. Three of them gate more than one institution, which is the
promotion rule; the fourth is one line.

| # | blocker | institutions gated | evidence it is shared |
|---|---|---|---|
| C1 | no `governor` archetype in `wd/create.py` | `subnational.executive` (778 rows) | **Iraq already worked around it** — `iq_offices.py:329` reuses `provincial_governor` "for its description template only". Two countries overriding one field is a missing archetype |
| C2 | `create_offices._existing` returns a duplicate only on `status == "matched"` | **7** — every `⊘` row in the ledger | `lookup_position` returns `ambiguous` whenever no *unique* strong candidate exists, so two matching items mint a third. `label-only` slips through with a `resolved_qid` in hand |
| C3 | no `mayor` archetype | `subnational.municipal` (~10 capitals) | one institution, but it shares C2's single human gate — batching it costs nothing and splitting it costs a second gate |
| C4 | `"ir"` absent from `create_offices.SCRIPTS` | all of the above | one line; nothing Iranian can be minted without it |

**Deliberately not triaged this run:** the `already holds P39` gate is per
`(person, target)`, not per term, so it hides every row of a re-elected member's
later terms. It gates `legislature.lower` and `oversight.state_councils`, so by
the rule it *is* a promotion — but the fix changes what a duplicate means for
every campaign, and per-term membership cannot go through QuickStatements at
all (§ the collapsing-groups rule). It gets a probe and a written disposition,
not a patch smuggled into a country run.

Each change is pinned in `scripts/check_dates.py` before the next one starts.
128 cases at HEAD; C1–C3 add a `GUARDS` block.

## Phase D — creation gate  [HUMAN]

One gate, one review, every institution's items at once. `--dry` output is a
reviewed proposal; `--apply` is the user's call.

| institution | items | shape |
|---|---:|---|
| `subnational.executive` | 27 | `governor`, `P1001` = province, `P2354` = list article, `P571` suppressed |
| `judiciary.specialised` | 5 | `judge` / `agency_head` |
| `diplomatic.outbound` | 7 | `bilateral_ambassador` — `P17` is the **receiving** state |
| `subnational.municipal` | ~10 | `mayor` |
| `oversight.audit_anticorruption` | 1 | General Inspection Office head |
| `hybrid.parastatal_foundations` | 6 | bonyad headships, already ruled *positions* |
| `hybrid.religious_hierarchy` | ~31 | Friday-prayer leaders — census first, may collapse to one office |

## Phase E — harvest

**E1, no creation needed — six items that exist and were never configured.**
Measured live this run, `max_age=0`:

| item | holders now | institution |
|---|---:|---|
| `Q7169241` Permanent Rep to the UN | 9 | `diplomatic.multilateral` |
| `Q6597965` Speaker of the Majlis | 7 | `legislature.leadership` |
| `Q20110284` Governor of the Central Bank | 3 | `economic.central_bank` |
| `Q118321724` Deputy Speaker | 2 | `legislature.leadership` |
| `Q110126773` Head of the Leader's Office | 1 | `executive.leader_office` |
| `Q114457755` FARAJA commander | **0** | `security.police` |

**E2** — the 27 governor offices, once minted.
**E3** — the remaining creation-first lanes, once minted.
**E4** — measured dispositions for the six never-examined classes
(`oversight.electoral_commission`, `economic.regulators`, `hybrid.state_media`,
`executive.deputy_ministers`, `executive.deputy_leadership` (11 portfolio VPs),
`legislature.historic_chambers`). A `no-source` needs a measurement, not a
shrug.

## Phase F — reconcile

Expected vs actual per institution in `coverage/iran.md`. Anything under half
its estimate carries a written reason. The Majlis row (388 of 2,349) already
has one and keeps it.

## Phase G — close

No row reads `not-attempted`, `deferred` or a bare `⊘`. Every `blocked:` names
an entry in `tasks/followups.md`.

## Invariants

* `scripts/check_dates.py` before and after every toolkit change.
* `wd/roster.py` is finished — a defect there is reported, not patched.
* `STATE_MAX_AGE = 0` for anything reading what Wikidata already records.
* One batch: one `.qs` plus `edit_plan_claims.json`, reviewed together.
* Creation never runs without `--dry` first, and `--apply` is the human's.
