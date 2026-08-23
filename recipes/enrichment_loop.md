# Recipe: the enrichment loop

**One person per request, scoped to one PETScan query, and done when the query
can be deleted.**

Reach for this instead of a country sweep when the goal is coverage rather than
one institution. A campaign is office-first — a human declares an `Office`, so
every institution nobody declared is invisible, which is why
`coverage/README.md` reads *judiciary 0 of 11, SOE 0 of 11, mayors 0 of 11*.
This inverts the unit: the person is the unit, their article is the evidence, and
the offices they turn out to have held are discovered rather than configured.

The frame is `wd_categories.yml` in the `opensanctions` repo — 594 PETScan
queries that mass-include people as PEPs **because** their Wikidata items lack
the statements that would find them properly, 284 of which paper over that with a
synthetic position that has no Wikidata identity at all. A run enriches one
query's members. It closes when that query is deletable, which is a definition of
done a campaign never had, and which is measured rather than declared.

Read `research/enrichment_loop.md` for the counts this rests on. Do not
re-measure what is in there; add to it when a run measures something new.

## 0. Pick a spec, and know which of four things blocks it

```
python scripts/audit_os_positions.py --json data/os_positions/audit.json
python scripts/spec_report.py        # -> coverage/petscan_specs.md
python scripts/retirable.py          # -> coverage/petscan_retirable.md
```

`spec_report.py` reads the audit and gives every spec a disposition. Only two of
them are yours:

| disposition | what to do |
|---|---|
| `retirable` | delete the query — it is on `coverage/petscan_retirable.md` |
| `enrich` | **this recipe** |
| `fix-item` | the target has a Wikidata defect; `recipes/position_items.md` first |
| `os-policy` | **keep the query.** Enrichment cannot retire it — see below |
| `bucket` | names a class of offices; needs the country gazetteer path |
| `unresolved` | no `wikidata_id` yet; `tasks/category_positions.md` |
| `broken-query` | the category matches no page; upstream title fix |

**`os-policy` is the ceiling and it is not made of Wikidata problems.** 110 of
284 specs name targets that are correctly modelled and that `wd_peps` still
declines, because the class confers no `role.pep` in `zavod`'s `SUB_TYPES`. No
P39 you write changes that. Do not scope a run against one, and do not record it
as a defect — file it upstream and move on.

**Take the emit/no-emit call from `scripts/audit_os_positions.py`, never from
`wd/shape.py`.** That module's `excluded_by` is unreliable in two ways that
partly cancel (`coverage/wd_categories.md`), so a number read out of it looks
plausible and is a coin toss.

**`spec_report.py`'s `gap` is measured before the cohort gate and overstates the
queue** — sometimes to zero. `Prime_ministers_of_Spain` shows 101 and has none.
`retirable.py` is the one that builds a real cohort; believe that one.

## 1. Cohort — and never drop the undated

`wd/cohort.py:build` is PETScan members ∩ `P31=Q5` − current holders − a
relevance gate, and it keeps the holders as the **backtest set**.

Re-check `P31=Q5` yourself: PETScan's own filter passes `Category:` items through
`P4224`.

The gate drops three kinds of person, and the shape of it is the point:

- a **known** `P569` before 1920,
- a **known** `P570` more than five years ago,
- no sitelink in a readable language — there is nothing to buy.

**A missing date is never a reason to drop anyone.** Undated people are the
highest-yield population, not the lowest: `research/person_items.md` measured ten
Lesotho holders whom one `P569` would make emittable. Every drop is counted and
reported; a filter that silently shrinks a cohort is the same failure as a
campaign that silently skips an institution.

## 2. Gazetteer — the closed set, in a cached block

`wd/gazetteer.py` builds the **only** QIDs the model may name. For an
`office`/`membership` spec that is the target plus its succession siblings
(`P1365`/`P1366`); for a `bucket` spec it is every position item scoped to the
country, which fits (62 Lesotho, 194 Czechia, 200 Iran).

Each entry carries the `P279` *kind* and the `P361` body, because a ministry, a
council, a committee or a general staff is a **body** and the office is the seat
in it — the closure `wd/shape.py` already encodes, which an LLM tier re-derives
as a bug if the prompt does not say it (`recipes/position_items.md`).

`p:P31/ps:P31`, never `wdt:`. A live spec target is invisible to `wdt:P31`.

## 3. Dossier — fetch shared evidence once

`wd/dossier.py:build` assembles one person's packet out of existing primitives:
`wd/human.py`'s reading of the item, the officebox tenures, the categories, the
rendered article prose, the birth-date evidence, and the roster rows naming them.

Two rules hold the cost down and both have been paid for:

**Shared evidence is fetched once, not per person.** `build_roster_index` reads a
spec's list articles and hands each person the rows that name them. The link from
category to list is the **eponymous-list convention** — a category called
`Posłowie na Sejm…X kadencji` sits beside an article of exactly that name.
`P301` main topic is the obvious signal and it is wrong: it gives the body.

**Every fragment is quotable**, because the model must cite a verbatim span and
`Dossier.contains` checks it afterwards.

Read one dossier end to end before spending anything (`--dossiers`). Every
mechanical matcher this workbench has built was too loose on its first pass, and
§9 of the research file is what reading dossiers found.

## 4. One request per person

`wd/verdicts.py:classify` with `batch_size=1`, `extra_system=[gazetteer]` and a
renderer. Two cached breakpoints: the instructions (stable across every run of
this kind) and the gazetteer (stable within one run). Marking only the last block
would make each run re-bill the prompt every run shares.

`prompts/person_enrichment.md` is the committed prompt. Its two hard rules exist
because they are mechanically checkable afterwards:

- **every proposal carries a verbatim quote** — a paraphrase fails;
- **never invent an identifier.** A country is named in prose and
  `rigour.territories.lookup_territory` resolves it; a position QID must come
  from the gazetteer, and an office that is not in it is reported by name.

## 5. The mechanical channel

`wd/enrich.py:check` is the second of the two independent signals this workbench
runs on. In order: the quote occurs in the evidence; the QID is in the
gazetteer; the dates are well-formed, ordered, and not before the office existed;
the statement is not already recorded; a birth date agrees with the article's
own births category.

**The quote check is the cheapest and strongest guard available.** It turns "the
model asserted a date" into "the model pointed at a date in a document we
fetched", at no marginal cost, and it catches what a JSON schema structurally
cannot — `output_config.format` constrains every field's shape and no field's
value.

**Distinguish three states, not two.** A recorded statement that is *undated* is
not a duplicate: `zavod` refuses an Occupancy when nothing is dated, so it
produces no PEP at all, and dating it is the largest single class of fix the loop
finds (31 of 42 recorded Sejm seats). Reading it as already-recorded is the easy
bug — "do all the dates present on both sides agree" is trivially true when one
side has none.

## 6. Policy, records, batch

`wd/policy.py:ENRICH_RULES`, then `wd/enrich.py:records`, then
`scripts/render_edit_plan.py` unchanged.

The rule order is load-bearing the same way `DEFAULT_RULES`' is: a proposal can
be `acting` and unverifiable at once, so everything that says *this is not
usable* precedes everything that says *what kind of statement it is*. The
terminal rule is `skip` with a reason, not `review` — conservatism belongs in the
rules, and there is no queue.

Which write path a statement takes is decided by the evidence, not by taste:

- **one undated statement, one dated proposal → QuickStatements.** QS matches on
  subject, property and value and merges the qualifiers into the statement it
  finds, which is exactly what is wanted.
- **several dated terms against one undated statement → neither.** QS would fold
  them all into it (the `Q1368615` shape) and the API would leave it standing
  beside them. The undated statement has to be removed first, and removal is the
  human gate — so this is `undated_needs_removal`, a byproduct list.
- **several tenures, no undated statement → the claims path.**
  `render_edit_plan.py` partitions those into `edit_plan_claims.json` already.

`byproduct` had never been emitted by any producer before this loop, so
`render_edit_plan.py` had no bucket for it and dropped them silently. It has one
now; if you add a disposition, check the renderer knows about it.

## 7. Backtest before proposing

The members who **already** hold the office are a labelled test set that costs
nothing to label. Run them with `--backtest`, which **withholds those tenures
from the dossier** — a backtest that shows the model the answer measures its
ability to copy a list.

Report three numbers, never one:

- **recall** — recorded tenures the loop re-found;
- **date agreement**, over the recorded tenures that *have* dates;
- **new dated terms**, which the record cannot score.

Do not use `Comparison.target_agrees` as the headline. It is False whenever the
recorded statement is undated, because `ExistingTerm.covers` needs two dates to
overlap anything — which made a clean Poland run read as 13/72.

If the numbers disappoint, stop and report them. That is the measurement the
whole design rests on.

## 8. Close the spec

A run closes when `retirable.py` moves the spec to the removable list, or when
every remaining member is documented — a verified P39, or a false positive that
becomes a `negcats` suggestion back to the yml. The PR is
`coverage/petscan_retirable.md`, and every row states how many people leave the
dataset when the query goes, because deleting a spec removes its `topic:` too.

## 9. What has not been tested

Say this out loud rather than discovering it later. As of 2026-08-23:

- **Position association has never actually been exercised.** Both runs were
  single-office specs whose gazetteer held one item, so there was nothing to
  choose between. The 24 `bucket` specs are where that question lives.
- **`office_unresolved` is not a creation list.** For a single-target gazetteer
  every other office is unresolved by construction. Run
  `wd/positions.py:lookup_position` over those names first.
- **Nothing has been written to Wikidata**, so no post-write verification exists,
  and no `regression/` baseline is committed for a run.
- Every statement so far cites only a Wikipedia permalink (`S4656`, no `S854`).
