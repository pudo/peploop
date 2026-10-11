# Recipe: modelling a person item

The sibling of `position_items.md`, and the half a roster lane actually writes
to. That file asks whether an office can be found; this one asks whether the
human named in a P39 statement is a well-formed person — and, separately,
whether anything downstream can read them.

Reach for it at **phase A of a sweep**, beside `institutions.md`, and again
after a roster lane lands. A campaign that harvests 200 tenures onto items that
carry no name, no date and no citizenship has done data entry, not curation.

Three questions, answered separately by `wd/human.py` and never mixed into one
score:

| | what it means | who it is for |
|---|---|---|
| **defects** | Wikidata modelling errors | fix them; they are wrong |
| **gaps** | recommended properties absent | the lane a campaign can run |
| **os_notes** | what the PEP build makes of the item | report, never "fix" |

A person can be flawlessly modelled and correctly absent from OpenSanctions —
someone born in 1880, or dead since 1990. Mixing the columns sends a campaign to
repair records that were never broken, which is the failure this split exists to
prevent.

## Required — an item missing these is defective

- **`P31 = Q5`**, as a best-rank, un-ended claim. The type closure over
  `P31`/`P279` is what `zavod` reads, but the query that *finds* holders is
  `?person wdt:P39 ?pos . ?person wdt:P31 wd:Q5` — truthy, direct, exact. A
  person typed human only through a subclass, or whose `Q5` sits behind a
  preferred value or is deprecated, is never fetched at all. `q5_not_best_rank`
  is the defect; `unreachable` is the note it causes.
- **A name.** Any label or alias, in any language: `LangText.pick` takes the
  preferred languages first, then whatever exists, then aliases, and
  `rigour.names.is_name` asks only for one letter in any script. `no_name`
  therefore means the item has no label and no alias anywhere, which is rare and
  is never recoverable downstream — the Person is emitted nameless and matches
  nothing.
- **Not also a position.** `Q5` and `Q4164871` on one item conflates an office
  with whoever holds it. `human.py:21` drops such an item silently, so every P39
  statement written onto it is written onto the wrong kind of thing. Untangling
  one is a split: stop and ask, never a batch line.
- **Dates that are possible.** A death date before the birth date, or a birth
  date in the future, is a defect regardless of what any consumer does with it.

`Q95074` fictional character is *not* a defect — a fictional person is correctly
modelled as one. It is a note, because `human.py:23` drops them.

## Recommended — the gaps a campaign can close

- **`P569` date of birth.** See *the birth-date hinge* below; this is not the
  soft nice-to-have it looks like.
- **`P27` citizenship.** Gates nothing at all — unlike a position, a person
  needs no country to be emitted, and `wikidata_occupancy` copies the *office's*
  country onto the holder for non-diplomatic posts anyway. It is still what lets
  a matcher place the person, and `human.py:71` reads
  `P1001`, `P17`, `P19`, `P945`, `P495`, `P937` in that order only when `P27`
  yields nothing — and files the result as `country`, never `citizenship`.
- **`P21` sex or gender.** **`zavod` never reads it.** The property appears
  nowhere in the crawl path; the only code that touches it is
  `nomenklatura/wikidata/propose.py`, which pushes OpenSanctions' gender *to*
  Wikidata. A gender lane is a Wikidata-quality lane and should be scoped and
  reported as one — running it will not move a single OpenSanctions record.

## The birth-date hinge

The one place a gap and a note line up, and the sharpest finding in this file.

`wd_peps` calls `make_occupancy(no_end_implies_current=False)`
(`position.py:375`), and `positions.py:204-214` refuses an Occupancy when there
is **no date anywhere** — no `P580`/`P582` on the statement, no `P569`/`P570` on
the person. No Occupancy means no emitted person (`crawler.py:216` emits the
person only alongside one) and no emitted position either, for want of a holder.

So on an undated tenure — which is most of what a roster harvest leaves behind
when the source gave no dates — **a birth date is the difference between a PEP
and nothing at all**. A `P580` on the statement does the same job, and a roster
that named a term usually has one: reach for whichever channel the evidence
actually supports, and note that the tenure date fixes one statement while the
birth date fixes every undated tenure the person has. `Verdict.dob_would_rescue` counts the people one `P569`
short, and `dob_carries` counts the ones already standing on that single
property, which is what a lane must not regress.

Two traps come with it:

- **A date coarser than a year is not a date.** `value.py:52` discards a
  decade- or century-precision `P569` entirely: it is not read as a birth date
  and does not count as a date signal. The item looks dated to anyone reading
  it and is not, so `coarse_birth_date` is its own gap.
- **A day-precise January 1st is read back as a year** (`value.py:65`), because
  bots write Jan 1 for year-precision imports. Don't propose one.

## What the PEP build does with a person — the notes, in order

Read a disagreement in the order the crawl applies them.

**Reached** — `position.py:322`, a truthy `wdt:P31 wd:Q5` plus a truthy
`wdt:P39` to an accepted position, or the position's own `P1308`. One preferred
P39 hides every normal-rank one, so a holder found only through a
non-best-rank statement is reached only if some *other* office reaches them.

**Built** — `wikidata_basic_human`:

| note | rule | source |
|---|---|---|
| `blocked` | `Q1045488`, the one hand-blocked QID | `human.py:10` |
| `not_human` | `Q5` missing from the `P31`/`P279` closure | `human.py:19` |
| `also_position` | `Q4164871` in the closure | `human.py:21` |
| `fictional` | `Q95074` in the closure | `human.py:23` |
| `born_pre_1900` | `P569` below `1900-01-01` (`registry.date.RELEVANCE_MIN`) | `human.py:41` |
| `implausibly_old` | `P569` more than 110 years ago | `human.py:45` |
| `too_young` | under 18 — **`strict` only**, so not `wd_peps` | `human.py:42` |
| `deceased` | any death date — **`strict` only** | `human.py:55` |

`strict=True` is the `_wikidata/categories` crawler. `wd_peps`, the dataset
every campaign here writes into, passes `strict=False`; `wd/human.py` models
both and defaults to the latter.

**Emitted** — one Occupancy must survive `positions.py:occupancy_status`:

| tenure dropped | rule |
|---|---|
| `no_dates` | nothing dated on person or statement — see the hinge |
| `long_dead` | died more than 5 years ago |
| `implausibly_old` | born more than 110 years ago |
| `after_office` | ended beyond the office's after-office window |
| `max_office` | open-ended and started more than 40 years ago |
| `position_dissolved` | the office ended beyond that same window |

Two more notes describe the *audit's* scope rather than the person:
`no_tenures` (no P39 claim at all) and `no_accepted_tenures` (every P39 pointed
at a position this run did not accept). The second is the expected
disagreement class — see below.

The after-office window is **the position's**, not the person's:
`gov.national` + `gov.head` never expires, `gov.national` / `gov.igo` /
`role.diplo` get 20 years, everything else 5. Judging a tenure without the
office's topics reads every ex-minister as dropped — pass `topics` from
`wd/shape.py` or the answer is wrong in one direction only.

## Anti-patterns

- **Do not add a `P569` to make someone emittable.** The hinge says a birth date
  rescues an undated tenure; it does not say invent one. A harvested date needs
  the same two independent channels as anything else — `scripts/harvest_dob.py`
  cross-checks the infobox against the article's births category, and that is
  the bar.
- **Do not run a gender lane for OpenSanctions.** Nothing downstream reads
  `P21`. Run it because Wikidata wants it, size it as a Wikidata lane, and say
  so in the ledger row.
- **Do not read a person's dates through the seven-day cache.** People are the
  state a campaign's own batches change; `wd/human.py:verify_all` fetches with
  `max_age=0` for the same reason `campaign.STATE_MAX_AGE` exists.
- **Do not treat `also_position` as a retype.** It is a split, and splits are
  destructive-adjacent: they stop and ask.
- **Do not conclude "not in OpenSanctions" from a person's own record.** The
  usual cause is the position layer: the person is fine and every office they
  hold failed a gate in `wd/shape.py`. Check that before suspecting this port.

## Verifying

```
/Users/pudo/.python/wrangle/bin/python scripts/person_metadata.py --country Q794
/Users/pudo/.python/wrangle/bin/python scripts/person_metadata.py --qids Q42,Q76 --calibrate
```

The candidate query is deliberately **wider** than the gates it measures — it
reads `p:P39/ps:P39` and imposes no type constraint — because a scope built from
the crawler's own query would hide exactly the people that query misses.

`--calibrate` checks each verdict against a live `yente-cli fetch`, and
`--check-spec` asserts this file still enumerates every gate class and threshold
`wd/human.py` applies. The full measurement record, including the Lesotho funnel
and the source lines behind every gate, is in `research/person_items.md`.

Measured on a 40-person subset of Lesotho's 138 holders: **38 agree,
0 pass-but-absent, 2 fail-but-present** — and both of the two are the review layer. The Speaker of
the National Assembly and the Commander of the Defence Force both hang off a
`P279` that leaves the PEP default off, so the type layer refuses them and a
reviewer rescued them upstream in a database this repo cannot read. Read a
disagreement in that order: **the position layer first** (`wd/shape.py`), then
the review layer, then a port bug — the last is yours to fix and the least
likely. A `passes, absent` count above zero is the one that should worry you;
it means this reader is over-claiming.
