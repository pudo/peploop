# Recipe: the enrichment loop

**One person per request, scoped to one PETScan query, and done when the query
can be deleted.**

Reach for this instead of a country sweep when the goal is coverage rather than
one institution. A campaign is office-first — a human declares an `Office`, so
every institution nobody declared is invisible, which is why
`coverage/README.md` reads *judiciary 0 of 11, SOE 0 of 11, mayors 0 of 11*.
This inverts the unit: the person is the unit, their article is the evidence, and
the offices they turn out to have held are discovered rather than configured.

The frame is `wd_categories.yml` in the `opensanctions` repo — a few hundred
PETScan queries that mass-include people as PEPs **because** their Wikidata items
lack the statements that would find them properly, and around 240 of those paper
over it with a synthetic position that has no Wikidata identity at all. (It was
594 and 284 when this was written; the count falls as queries retire, which is
the point. `scripts/spec_report.py` is the live answer.) A run enriches one
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

**Qualifier values come from closed sets too.** `for_qualifier` builds them per
country for `P768` electoral district and `P4100` parliamentary group, and the
model names a value in prose exactly as it names a country. Two things about
them are easy to get wrong:

- **Render the aliases, not just the label.** A Polish constituency is
  *labelled* by number ("Sejm Constituency no. 11") and *named* by place in its
  aliases ("Sieradz electoral district"), while the evidence says "okręgu
  sieradzkim". With labels alone the model named one district in 130 proposals,
  because bridging that gap would mean knowing a place-to-number mapping it has
  no way to have. With aliases: 56 in 117.
- **An empty set is an answer.** Guatemala has no electoral-district and no
  parliamentary-group items at all, so the block is omitted rather than offered
  and the qualifier simply cannot be asserted there. That is the `∅ measured`
  disposition from `coverage/README.md`, not a gap to close.

An unmatched qualifier is dropped and never fails the tenure: the tenure is the
claim, the constituency is a detail, and losing a detail must not cost a P39.

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

**"Already recorded" is five states, not two**, and `_tenure_state` answers
which. Collapsing them is where every write-path bug in this loop has come from,
because each wrong answer is a plausible-looking statement:

| state | what it means | what to do |
|---|---|---|
| `recorded` | same office, same span | nothing |
| `undated` | the office is recorded with **no dates at all** | date it — a QS merge |
| `closes` | recorded open-ended, the evidence ends it | close it — a QS merge |
| `conflicts` | both dated and disagreeing | a human decides which is wrong |
| `new` | no statement for this office | create it |

Two of those are counter-intuitive and both cost real duplicates before they
existed. **`undated` is not a duplicate** — `zavod` refuses an Occupancy when
nothing is dated, so the statement produces no PEP at all, and 31 of 42 recorded
Sejm seats are in that state. **`closes` is not a new tenure** — live
`2021-03-16–None` against evidence `2021-03-16–2023` is the same spell better
recorded. The shared failure is that "do all the dates present on both sides
agree" is trivially true when one side has none.

### 5a. Place the offices the gazetteer never offered

A single-target gazetteer makes **every other office a person held** read as
unresolved by construction, so `office_unresolved` is not a creation list until
`resolve_offices` has run `wd/positions.py:lookup_position` over the names. Its
own gate is two-signal — a label variant must match *and* the item's own
`P17`/`P1001` must resolve to the country — which is why a match there is
allowed to become a statement rather than a review row. The driver widens the
gazetteer with what it places, so the invariant that every applied QID came from
the gazetteer still holds.

Two things the first pass got wrong, both worth knowing before trusting a match:

- **A model writing for a reader disambiguates**, and a label search takes the
  string literally: "Minister of Education and Science (Poland)", "Deputy Voivode
  of Łódź Voivodeship (wicewojewoda łódzki)". Try the stripped form *and* the
  parenthetical — the parenthetical is often the better query, because Wikidata
  labels a Polish office in Polish. That went from 2 matches to 9. A parenthetical
  that is merely a country is dropped, or "(Poland)" is searched as the country.
- **`lookup_position`'s country gate accepts a bare `P17`, which lets a generic
  office class through.** "Mayor (wójt) of Świlcza" matched `Q98637505 wójt`, the
  Polish administrative rank, `P17=Poland` and no `P1001` at all. Writing a
  specific village mayoralty onto that is the generic-occupation trap, and
  `recipes/position_items.md` calls an office scoped to no polity a defect — so a
  match must name the polity it governs.

What is left after that *is* the creation list, and unlike the ~150 offices nine
campaigns listed and never minted, each row arrives with an attested holder,
dates and a quote. Poland: 6 names placed onto 4 items, 4 ambiguous, 3 rejected
for no polity, and **51 genuinely item-less** — municipal councillors, sejmik
members, deputy voivodes, government plenipotentiaries.

## 6. Policy, records, batch

`wd/policy.py:ENRICH_RULES`, then `wd/enrich.py:records`, then
`scripts/render_edit_plan.py` unchanged.

The rule order is load-bearing the same way `DEFAULT_RULES`' is: a proposal can
be `acting` and unverifiable at once, so everything that says *this is not
usable* precedes everything that says *what kind of statement it is*. The
terminal rule is `skip` with a reason, not `review` — conservatism belongs in the
rules, and there is no queue.

### Merge or create — the distinction the whole write path turns on

Every P39 record is one of two things, and confusing them writes duplicates:

- a **merge** edits a statement already on the item. QuickStatements matches an
  incoming line on subject, property and *value* and folds its qualifiers into
  the statement it finds, which is exactly the wanted behaviour. `MERGE_FLAGS`
  names them: `undated_statement`, `closes_existing_statement`,
  `qualifies_existing_statement`.
- a **creation** adds a statement. Only the API does that, because QS would fold
  it into the existing one instead.

**The API creates and never merges.** So routing a merge there writes a second
statement rather than improving the first — which is how a *correct*
`qualifies_existing_statement` produced five duplicate claims in a rendered
payload. `render_edit_plan.py` now refuses outright if a merge rule reaches the
API path, rather than trusting the producer.

Then three combinations neither path can carry out, all byproducts:

- **several merges onto one office** — QS folds them all into the same statement,
  leaving it with every start and every end and nothing pairing them up. That is
  the `Q1368615` shape, already live from the Ecuador batch.
  (`undated_needs_removal`)
- **a merge and a creation onto one office** — through QS the lines fold
  together; split across paths, QS afterwards faces two statements and folds into
  whichever it finds. There is no safe order. (`mixed_write_paths`)
- **a recorded span the evidence contradicts** — one of them is wrong and this
  engine cannot know which. (`contradicts_recorded`)

Everything else: **several tenures, none of them a merge → the claims path**,
which `render_edit_plan.py` already partitions into `edit_plan_claims.json`.

**Pre-flight before applying claims.** The API de-duplicates nothing and
`claims_written.json` only protects a *re-run*, not a first run against state
that moved. Read each payload against live claims (`max_age=0`) before
`--apply`; that check is what caught the five duplicates.

`byproduct` had never been emitted by any producer before this loop, so
`render_edit_plan.py` had no bucket for it and dropped 87 of 117 records
silently. It has one now; if you add a disposition, check the renderer knows
about it.

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

Say this out loud rather than discovering it later. As of 2026-08-24:

- **Position association still has not been exercised.** Every run so far was a
  single-office spec whose gazetteer held one item, so there was nothing to
  choose between. The 24 `bucket` specs are where that question lives and none
  has been run — `es:Alcaldes_de_Guatemala` is the obvious first.
- **`undated_needs_removal` has nowhere to go.** 49 Polish records need a live
  statement removed before their terms can be written, and nothing renders that
  into a removal list — `wd/write.py:remove_claim` and
  `scripts/apply_removals.py` both exist and are unwired.
- **No `regression/` baseline** is committed for a run, which the repo's own
  convention asks for and which matters more here than usual: see §10.
- **The `P768` set is noisy.** It carries Senate constituencies, historical
  2001–2011 ones and at least one outright settlement, because the `P279`
  closure under `Q192611` reaches further than intended. Nothing wrong has been
  proposed from it, but narrow it before trusting it elsewhere.
- Every statement so far cites only a Wikipedia permalink (`S4656`, no `S854`),
  and roughly half are year-precision.

Since resolved, and left here because the reasoning still governs: office names
outside the gazetteer *are* now placed by `wd/positions.py:lookup_position`
(§5a), and statements *have* reached Wikidata — 128 for Polish MPs, 4 for
Guatemalan deputies — all 102 P39 holders predicted to emit as PEPs.

## 10. How this code fails

Worth its own section, because it has been consistent enough to plan around.
**Thirteen defects were found in this loop and its dependencies; not one was
caught by a test.** Every one came from reading real output or pre-flighting a
payload, and two were in `wd/` modules that had been running for weeks.

The failure mode is always the same: **the code looks right and produces
plausible output.** A quote gate that rejects truthful citations looks like the
model hallucinating. A loop variable named `prop` renames the statement it hangs
on and still renders valid QuickStatements. An undated statement read as a
duplicate silently suppresses the loop's largest class of fix. A `13/72` score
looks like a bad model.

So the discipline is:

1. **Dump the artifact and read it.** One dossier, one rendered `.qs` line, one
   claims payload. `--dossiers` exists for this.
2. **Audit a matcher's full output with resolved labels**, never a sample.
   `Mayor (wójt) of Świlcza` matching the generic `wójt` rank, and 56 of 56
   districts being right, both came out of that.
3. **Pre-flight anything that writes**, against live state.
4. **Pin it afterwards**, in `scripts/check_enrich.py`, from the bug that
   shipped rather than from imagination. It is offline and tokenless, so there is
   no excuse not to run it.
