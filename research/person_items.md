# Measured: how a person item reaches a PEP dataset

The evidence behind `recipes/person_items.md`, the person half of
`research/position_items.md`. The recipe says what to do; this says what was
counted and what was read out of code.

**Measured 2026-08-19.** Two kinds of evidence, kept apart because they age
differently:

- **Country measurements**, re-runnable with
  `scripts/person_metadata.py --country <cc>`.
- **Readings of `zavod`/`nomenklatura` source**, each with its file and line.
  Independently verified for this report rather than transcribed — where a
  reading turned out stronger than the recipe stated, it is noted.

## 1. Lesotho, the only country audited so far

`scripts/person_metadata.py --country ls` — 138 people, every holder of an
accepted Lesotho position.

| | count |
|---|---:|
| people audited | 138 |
| **modelling defects** | **0** |
| emitted as PEPs | 76 |

**Zero defects across 138 people**, which is the finding: Lesotho's person items
are all well-formed, and the entire opportunity is *gaps*, not repairs. That is
the opposite shape from the position side, where Iran carries 54 items that say
"position" and never say which kind. A person-side campaign is a completion lane;
a position-side one is often a correction lane.

| gap | people |
|---|---:|
| `no_birth_date` | 57 |
| `no_citizenship` | 49 |
| `no_gender` | 16 |

| why not emitted | people |
|---|---:|
| `no_occupancy` | 60 |
| `implausibly_old` | 5 |
| `born_pre_1900` | 5 |
| `no_accepted_tenures` | 2 |

The tenure funnel — **175 P39 statements become 94 occupancies**:

| tenure dropped | count |
|---|---:|
| `long_dead` (died more than 5 years ago) | 36 |
| `after_office` (past the office's window) | 35 |
| `no_dates` | 10 |

And the hinge, which is why `P569` is not a soft nice-to-have:

- **9 people are emitted *only* because a `P569` is present.** A lane that
  regresses those regresses real PEPs.
- **10 people are absent, and a `P569` alone would fix it.**

## 2. What the crawl reads — and what it does not

**`P21` sex or gender appears nowhere in `zavod`.** Verified as
`grep -rn '"P21"' zavod/zavod/` → no matches at all, which is stronger than "the
crawl path does not read it". The only code touching `P21` is
`nomenklatura/wikidata/props.py:35` and `propose.py:65,166`, which push
OpenSanctions' gender **to** Wikidata — the opposite direction.

So a gender lane moves zero OpenSanctions records. Run it because Wikidata wants
it, and size it in the ledger as a Wikidata-quality lane.

**Citizenship is not a gate either.** Unlike a position, a person needs no country
to be emitted. `zavod/shed/wikidata/human.py` reads `P27` first and falls back
through `P1001`, `P17`, `P19`, `P945`, `P495`, `P937`, filing the result as
`country` rather than `citizenship`.

**Holders are found truthily.** `position.py` queries
`?person wdt:P39 ?pos . ?person wdt:P31 wd:Q5`, plus the position's own `P1308`.
Both legs are `wdt:`, so one preferred `P39` hides every normal-rank one and a
`Q5` behind a preferred value or a deprecated rank is never fetched at all.

## 3. The birth-date hinge, verbatim

`zavod/zavod/stateful/positions.py` refuses an Occupancy when nothing is dated:

```python
if not (
    death_date
    or birth_date
    or end_date
    or period_end
    or effective_start_date
    or no_end_implies_current
):
    # If we don't have any dates to work with, nor a really well-maintained
    # source, don't consider them a PEP.
    return None
```

`wd_peps` passes `no_end_implies_current=False`, so on an undated tenure the
person's own dates are the only remaining channel. No Occupancy means no emitted
person — and no emitted position either, for want of a holder.

Note **a death date does the same job as a birth date** in that condition. The
audit's `dob_would_rescue` counts `P569` only, so it is a floor on the rescuable
population, not a ceiling.

## 4. The gates, with source lines

`zavod/zavod/shed/wikidata/human.py`:

| gate | rule | line |
|---|---|---|
| `blocked` | `BLOCKED_PERSONS = {"Q1045488"}` — one hand-blocked QID | `:10` |
| `not_human` | `"Q5" not in types` (the `P31`/`P279` closure) | `:19` |
| `also_position` | `"Q4164871" in types` — an office and its holder conflated | `:21` |
| `fictional` | `"Q95074" in types` | `:23` |
| `too_young` | under 18 — **`strict` only** | `:34` |
| `born_pre_1900` | `date.text < registry.date.RELEVANCE_MIN` | `:40` |

`strict=True` is the `_wikidata/categories` crawler; `wd_peps` — the dataset every
campaign here writes into — passes `strict=False`, so `too_young` and `deceased`
do not apply to it. `wd/human.py` models both and defaults to the latter.

## 5. The after-office window belongs to the office

`zavod/zavod/stateful/positions.py:147-153`, over the **position's** topics:

| topics | window |
|---|---|
| `gov.national` + `gov.head` | never expires |
| `gov.national` | 20 years (`EXTENDED_AFTER_OFFICE`) |
| `gov.igo` or `role.diplo` | 20 years |
| everything else | 5 years (`DEFAULT_AFTER_OFFICE`) |

`YEAR_DAYS = 365`, so these are day counts rather than calendar years. This is why
`scripts/person_metadata.py` passes `topics` from `wd/shape.py`: judging a tenure
without the office's topics puts every ex-minister on the 5-year default and
reports them dropped. The error is one-directional, so it looks like a finding.

## 6. Date precision traps

`nomenklatura/wikidata/value.py`:

- **A date coarser than a year is discarded entirely** — a decade- or
  century-precision `P569` is not read as a birth date and does not count as a
  date signal for §3. The item looks dated to a human reading it and is not.
- **A day-precise January 1st is read back as a year**, because bots write Jan 1
  for year-precision imports. So never propose one.

## 7. Calibration

`--calibrate` checks each verdict against a live `yente-cli fetch`. On a 40-person
subset of Lesotho: **38 agree, 0 pass-but-absent, 2 fail-but-present** — and both
of the two are the review layer. The Speaker of the National Assembly and the
Commander of the Defence Force each hang off a `P279` that leaves the PEP default
off, so the type layer refuses them and a reviewer rescued them upstream in a
database this repo cannot read.

Read a disagreement in this order: **the position layer first**
(`wd/shape.py` — the usual cause), then the review layer, then a port bug. The
last is yours and the least likely. **A `pass-but-absent` count above zero is the
one to worry about**: it means this reader is over-claiming.

## 8. Not measured, and what to distrust

- **One country.** Every figure in §1 is Lesotho, n=138, and Lesotho has zero
  defects — so this report says nothing yet about how common person-side defects
  are. Do not generalise the 0 until a second country is audited.
- The candidate query is deliberately **wider** than the gates it measures — it
  reads `p:P39/ps:P39` with no type constraint — because a scope built from the
  crawler's own truthy query would hide exactly the people that query misses.
- `no_accepted_tenures` is the expected disagreement class, not a defect: it means
  every office the person holds was one this run did not accept.
