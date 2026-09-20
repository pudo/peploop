# Positions: the reconciliation table for round 2

Context notes for the design of the position lookup that round 2 of the loop
needs. `design.md` §5 fixed the *shape* of the `candidate` table so round 1
would not have to change it; this document is about *filling* it, and about
the two questions the shape left open: which items belong in it, and in what
order the search should offer them. It was written before the research and
extended by it; §6 records what the research answered and §7 is the plan.

## What the table is for

Turn one of extraction returns an office as the article names it: a free-text
title in the article's language, a jurisdiction string where the article gives
one, dates, an `acting` flag, quotes. Turn two shows the model a shortlist of
Wikidata items and asks it to pick one or decline. The table is what the
shortlist is drawn from. It has to be good at three things:

1. **Recall.** If the community's item for the office exists, it is in the
   shortlist. An office the table lacks is not matched and lands in the
   creation queue with its evidence; that is acceptable, a wrong match is not.
2. **Legibility.** The model must be able to tell the candidates apart from
   what the row shows: label, aliases, description, the jurisdiction's name,
   and the reasons the ranking put it where it did (abolished, abstract, how
   many holders).
3. **Order.** The shortlist is short (top 15 in the current design). The right
   item must be near the top for common queries, and the *wrong-but-plausible*
   parents must not crowd it out: "minister of defence" has to surface
   `Minister of Defence of Czechia` above `defence minister` (the class).

## Constraints already fixed

- The table is Postgres and a `simple`-configuration `tsvector` over
  `search_text`; the `pg_trgm` channels this originally also named were
  measured and removed (§2). No search service until birthplace forces the
  question (`design.md`, *Not in round 1*).
- Retrieval ranks, a model decides, a mechanical gate vetoes (repo rule). The
  table does not pick; it orders. So ranking heuristics may be soft and
  approximate as long as the true item is *present* and *visible*.
- Non-PEP positions belong in the table. A resolution to `Q4164871`-typed
  item that OpenSanctions does not track is still a correct P39, still
  disambiguates ("chairman of the Czech Chess Federation" is not a ministry),
  and still says something about the person. Whether it is PEP is downstream's
  judgement, not the table's.
- Everything HTTP goes through `peploop/http.py`; state reads bypass the cache.

## Corpus facts to design against

Measured elsewhere in this repo (`research/position_items.md`) and from the
production extract at `/Users/pudo/tmp/pep_wd_positions.csv`:

| measure                                                      | value    |
|--------------------------------------------------------------|----------|
| position items in Wikidata (P31/P279* into the position tree) | ~145,000 |
| live `is_pep=True` rows in the prod `wd_peps` table           | 154,138  |
| of which French                                               | 80,793   |
| Czechia position items (gazetteer)                            | 194      |
| Poland                                                        | 322      |
| Russia                                                        | 2,348    |
| Spain                                                         | 13,198   |

Two things follow. **The corpus is dominated by per-municipality mayoralties**
(French communes alone are more than half the PEP table), so any measure taken
over the whole corpus is a statement about France, and any per-country load
for FR, ES, IT, DE will be four orders of magnitude larger than for CZ.
**Whole-country loading is a small-country technique**; the loader has to be
sized and paced for Spain, not Czechia.

The prod table also carries `topics` (`gov.national`, `gov.muni`,
`gov.judicial`, `role.diplo`…) and `subnational_areas` for ~70% of rows. Those
are consumer-side classifications, but they are free signal for the table
(see *Ranking*), and the `wd_peps` *dataset* itself is one of the three
discovery sources `design.md` already names.

## 1. Discovery: how items get into the table

`design.md` names three sources; the note below says what each one actually
reaches and what it misses, so the union can be measured rather than assumed.

**a. Class descent.** Everything reachable by `P31/P279*` from `Q4164871`
position and `Q294414` public office (and the other metaclasses
`recipes/position_items.md` measured: `Q4164871` is *not* the modal one).
Necessary, not sufficient: many real offices are typed only as a subclass of
something that is not in the position tree (a `Q30185` mayor subclass that
never reaches `Q4164871`, a legislative seat typed as `Q4175034` legislative
term, a bishopric, a `Q3186962` occupation used as an office). Also over-
inclusive: it pulls in occupations, ranks and honours that are typed as
positions by mistake — the shape defects `wd/shape.py` reports. The descent
must read `p:P31/ps:P31`, never `wdt:` (best-rank hides real types), and the
unbounded `P279*` belongs in a cached closure, not in a live `FILTER`.

**b. Usage.** Every item that is the *value* of a human's `P39`. This is
zavod's `shed.wikidata.position` discovery route and is the one that catches
offices the ontology mistyped. It finds what people already hold, which is a
strong prior for what our articles will name; it misses offices with zero
recorded holders, which are exactly the offices a first roster lane creates.
Full-corpus `P39` values is a big query; per-country it is bounded by holders,
not by items, and Spain is the stress case again.

**c. The tracked set.** The prod `wd_peps` position rows (the CSV extract).
This is the set OpenSanctions has already judged; it is authoritative on
`is_pep`, `topics` and `countries` and carries nothing else. Loading it gives
the table 154k rows on day one, most of them French mayors.

**d. Not yet named in `design.md`, worth considering:** items with a `P1001`
or `P17` and a `P279` into a *body* (`P361` chain), and items that are the
value of `P1308` officeholder / `P39` on a *position's own* item. Both are
cheap once a country's set is loaded and they catch the "seat in a body"
offices whose only typing is the body.

The union should be built **per country, on demand, incrementally**: a run for
`cz` loads CZ; a later run for `pl` adds PL without touching CZ rows; a re-load
refreshes `loaded_at` and updates rows in place. A full load of one country
should be minutes for CZ and an hour or two for FR, never a day. Which
discovery source found an item is worth recording (a `sources TEXT[]` or a
join table), because *the item found by class descent alone and never held by
anyone* is a ranking signal in its own right.

## 2. Storage and indexing: how a row becomes findable

Settled by the ablation below, and the shape is much plainer than this
section originally proposed. **One document per position, not one row per
name.** `position.search_text` is a de-duplicated, sorted bag of content
tokens drawn from every name the item carries and every name of the items it
points at; `position.tsv` is a generated `to_tsvector('simple', search_text)`
over it with a GIN index. That index is the whole search. The three trigram
and per-name full-text indexes this section used to specify are gone, and
`position_name` stays as the per-language source the document is built from
and as the answer to *which* name matched.

What each part of that is, and what it is worth:

- **The blob beats the per-name channels by 16.9 aggregate points** — 64.1%
  to 81.0% as shipped, 17.7 in the ablation harness. Scoring each name
  separately and keeping the best asks "is there one string here that looks
  like the query", which is the wrong question: an article writes the
  office and the place in one breath, and no single label on the item has
  both. Pooling every name of the item and of its jurisdiction, country,
  body, kinds and succession into one document asks "how much of what the
  article said does this item account for", which is the right one.
- **`simple`, and a six-character prefix in place of a stemmer.** The names
  are in every language the item has one in; Postgres ships a configuration
  for a minority of them and none at all for the pilot's, so `simple` is the
  only honest choice. Each token is therefore stored twice, whole and
  clipped, and the clipped copy is what makes "ministr" reach "ministra" and
  "Liberecký" reach "Libereckého". Worth about three points.
- **Trigram is the wrong tool over a blob.** Measured on the same document:
  `similarity()` 23.3% aggregate at 137 ms a query, `word_similarity()` 75.6%
  at 225 ms, `ts_rank` 81.8% at 1.6 ms. Trigram earned its place when the
  unit was one short name; over a document of a few thousand characters it
  mostly measures length.
- **The jurisdiction is query text, not a channel.** Concatenating it onto
  the title before tokenising is worth 7.7 aggregate points over the title
  alone. Scored as a separate trigram channel over `jurisdiction_text`, as
  the original design had it, it contributed exactly 0.0 — the place names
  are already in the document, and a second reading of them adds nothing.
  `jurisdiction_text` survives as a display column and is no longer indexed.
- **Cross-language queries** are still answered, and by the same fact as
  before: an article naming an office in one language and an item labelled in
  another still agree on the polity. What changed is that the bridge is a
  *part of the document* rather than a column beside it.
- **The parent trap is handled by the scoring itself.** `{mayor} ⊆ {mayor,
  brno}`: the class covers one of the query's two content words and the
  named mayoralty covers both, so the named one ranks higher without a rule.
  The boolean `covers` that used to be the first sort key is gone — with
  coverage scoring, covering the whole query *is* the top score.
- **Not-a-position rows** are unchanged: still in the table, still flagged,
  because telling the model "this is an occupation, not an office" prevents a
  wrong P39 that dropping the row would only hide.

The two storage questions this section left open are answered. Names are one
row per (qid, lang) — kept, but for display and provenance, since the search
no longer reads them. Descriptions are **out** of the document: measured,
`en`/`mul` descriptions are neutral and all-language descriptions cost 1.5
macro points, because "Czech politician" is in hundreds of documents at once.

## 3. Ranking: which candidates go first, and which last

The base ranking is settled and is one line of SQL:
`ORDER BY ts_rank(tsv, q, 0) DESC, qid`, where `q` is the query's lexemes
OR-ed together. Because the document is a bag in which every lexeme appears
exactly once, `ts_rank` with normalisation flag 0 over an OR-query sums to
*the number of query terms the document matched* — it is uniform coverage,
numerically identically so, and the fancier options were measured and are
not worth their code:

- **IDF** — weighting a rare lexeme above a common one — is worth +0.02 MRR
  and −0.4 aggregate points against uniform coverage.
- **Normalisation flags** 0, 4 and 32 are identical. Flags 1 and 16 (divide
  by document length) trade +1.2 macro for −8.6 top-1, which is the wrong
  trade for a shortlist a model reads from the top. Flags 2 and 8 are
  catastrophic: 65% aggregate.
- **Filtering by the run's country** costs 23.7 macro points and is gone.
  `country_qid` stays in the signature unused, for the ranking signal below.

Everything after this point is increment 4 and is *not* measured yet. Each
signal re-orders the shortlist before the model sees it, and each one that
moved a row is *shown* to the model as a tag rather than applied silently.

**Discourage, never exclude:**

- **Abolished / dissolved.** `P576` dissolved, `P582` end time on the item,
  `P1366` replaced-by, `P31` including `Q114962596` historical position, or a
  description saying "former". An abolished office is still the right answer
  for a 1960 tenure, so this is a signal *conditional on the tenure's dates*:
  a row ended in 1992 is boosted, not penalised, for a 1980 start.
- **Abstract / class-like.** "member of parliament", "defence minister",
  "mayor of a place in France". The heuristics that identify one, in order of
  cost:
  1. it has many `P279` children (subclass count): a real office has zero or
     a handful (renamings), a class has hundreds;
  2. it has `P279` children *that are themselves in the table with a
     `P1001`*, and it has no `P1001` of its own, or its `P1001` is a country
     while its children's are municipalities;
  3. it is the `P31` of other position items (a metaclass);
  4. it has *no* `P1001` and *no* `P17` at all;
  5. its label is a bare noun phrase without a proper noun ("minister of
     finance" vs "Minister of Finance of Czechia") — cheap but language-
     dependent, last resort.
  Signals 1–3 come from the same descent that discovered the item, so they
  are free at load time. The threshold is measured, not declared (as
  `research/position_items.md` did for the shape conventions).
- **Occupation, rank, honour typed as a position.** From `wd/shape.py`'s
  checks; tag as `not_office` and rank below every real office.

**Encourage:**

- **Holder count.** How many humans carry a `P39` to it. The best single
  signal for "is this the item the community uses", and the one the user
  flagged as possibly too expensive. Options, cheapest first: (i) a count
  over the prod `wd_peps`-side occupancy table if one is available; (ii) a
  count over our own `item` table's fetched persons (biased to what we have
  read but free); (iii) a per-country SPARQL `COUNT` grouped by position, one
  query per country, which is bounded and was affordable for Czechia's 14k
  statements; (iv) a dump pass, done once, for everything. Store as a nullable
  integer with a `counted_at`; treat null as unknown, not zero.
- **Country match.** Row's `country_qid`/`jurisdiction_qid` equals the run's
  country or the jurisdiction turn one named (via `rigour` for countries).
  The design's original "filter to the run's country first, global fallback"
  is dead: measured, the filter costs 23.7 macro points, because what it
  hides is every globally abstract office recorded with a scoping qualifier
  and every office of the predecessor state. As a *boost* it is untested and
  is the first thing increment 4 tries.
- **Tracked by OpenSanctions.** `is_pep` from the prod extract. A weak
  positive: it says the item was judged a real office, not that it is *this*
  one. Non-PEP rows must not be pushed below the abstract ones by it.
- **Date fit.** The item's `P571` inception / `P576` dissolution against the
  tenure's start/end, when both are known. The strongest disambiguator inside
  a renaming succession (`Office.date_targets` in the country-sweep toolkit
  does this by hand today).

A last-resort pick (abstract, or `not_office`) should still be *offered* when
nothing better matches, because "member of the Chamber of Deputies of the Czech
Republic" is better modelled on the class than dropped, and the model can say
so in a note. Whether such a pick becomes a proposal or a `creation queue` row
is a policy question for `propose`, not for the table.

## 4. Testing the search before building the whole table

`design.md` already says it: the free-text titles in `extraction.response_json`
from round 1 are the test queries, and they exist today for the Czech pilot.
The proposed order of work is:

1. Pull every extracted `(title, jurisdiction, lang, start, end)` from the
   Czech extractions into a fixture (one file, committed under
   `peploop/fixtures/` or `regression/`).
2. Hand-label a sample of them with the right QID — or, cheaper, take the
   holders' *existing* `P39` claims as silver labels: a person whose article
   names "ministr financí" and whose item already carries `P39 Q…` gives a
   query–answer pair for free. This is the country-sweep backtest idea
   ("the rows you skip are the test set") applied to reconciliation.
3. Load *only Czechia* by each discovery source separately, and measure per
   source: recall of the silver QIDs, table size, load time.
4. Run the search, measure recall@15 and MRR of the true item before any
   ranking heuristic, then with each heuristic added; the abstract-item
   heuristics are validated by whether the true item's rank *improves*.
5. Only then load a large country (Spain or France) to measure load time and
   whether the search degrades when the table has 80k mayors in it.

Step 4 is a script with a committed fixture, run offline, and is the thing
that makes later changes to the ranking safe.

## 5. Generalise to a `lookup_item` table?

The question raised: should this be an abstract `lookup_item (kind, qid, …)`
table so the same search serves birthplaces later and, if a family-link lane is
built, people? The `candidate` table *already* has `kind` in its key for this
reason. The costs of generalising further now: places do not have a
jurisdiction, they have a parent chain (`P131*`), and people have neither but
have dates and a citizenship; a shared table ends up with nullable columns
that mean different things per kind, and a shared ranker that has nothing in
common across kinds except "the label matched". The gain is one loader
skeleton and one search function. Recommendation carried into the questions
below: keep `kind` (it is free), keep the label/alias/search-text core shared,
and put position-specific ranking columns (holder count, abstractness,
abolished, is_pep) in a `position` side table keyed by qid. That is the
smallest thing that is not wrong for places later.

## Decisions taken (2026-09-20)

- **Load path: per country, via SPARQL and the API.** No dump. Incremental
  loads, small for CZ and PL, stress-tested on ES and FR before it is called
  done. Research has to bound the big-country queries.
- **Holder counts come from Wikidata or not at all.** There is no
  OpenSanctions-side occupancy source to read. Per-country grouped `COUNT`
  queries and a nullable column; measure whether the signal is worth its cost
  before making it load-bearing.
- **Position-only table, no `kind`.** The generalisation to places and people
  is dropped rather than deferred: the table is `position`, and birthplace gets
  its own table when it arrives. The `candidate` table in `schema.sql` is
  superseded by this decision.
- **Test set: silver labels from existing P39.** The Czech round-1 extraction
  titles are the queries; the holders' recorded P39 values are the answers.
  Disagreements are hand-checked, nothing else is hand-labelled.

## Measured on the Czech pilot (2026-09-20)

What round 1 left in the `peploop` Postgres database, read before any table
was built. It is the test set, and it already changes the ranking concept.

| measure                                                       | value |
|---------------------------------------------------------------|-------|
| people extracted                                              | 873   |
| extracted position titles                                     | 3,047 |
| distinct titles (case-folded)                                 | 1,526 |
| titles with a jurisdiction string                             | 2,276 |
| titles with a start date                                      | 2,858 |
| titles flagged acting                                         | 50    |
| titles in `cs` / `en` / `de` / `pl` / `fr`                    | 2,556 / 156 / 76 / 73 / 68 |
| people with at least one P39 on their item                    | 852   |
| P39 statements on those items (silver labels)                 | 2,793 |
| distinct position items among them                            | 139   |

The seed was a category of Czech legislators, so the silver set is dominated by
one item (`Q19803234` member of the Chamber of Deputies, 998 statements) and
its answers are biased toward what is already recorded. Even so, three things
in the top thirty items decide how the table has to think about abstractness:

**1. The Czech convention for local office is a country-scoped generic item
plus a `P1001` qualifier.** `Q108899569` "member of a Czech municipal council"
(302 statements, every one carrying `P1001` = the municipality), `Q99356295`
"mayor of a place in the Czech Republic" (131, all with `P1001`),
`Q108899565` deputy mayor, `Q108899428` mayor of a city district,
`Q97482814` district representative. Czechia does *not* mint an item per
municipality; France mints 80,000. So "a class with many children and no
`P1001` is a pick of last resort" is wrong for Czechia at the municipal tier:
the generic item is the community's answer and the municipality goes in the
qualifier. **Abstractness is relative to the country's convention**, and the
only way to learn the convention is to count holders per item per country,
which makes holder counts *more* load-bearing than the notes above assumed,
not less. It also means the table must record, per item, which qualifier the
community uses to scope it (`P1001` here), so that `propose` can emit it.

**2. Globally abstract items are used on purpose, with a scoping qualifier.**
`Q1127270` deputy chairperson (128 uses, every one with `P2389` organisation
directed), `Q140686` chairperson (43, all `P2389`), `Q8191099` member (13,
twelve with `P463`). These are party and committee posts, and this is how the
community records them. A pick of `chairperson` is not wrong; a pick of
`chairperson` *without* `P2389` is. Whether the loop should propose these at
all is a `propose` policy question; the table's job is to offer them tagged
`abstract` and to say which qualifier makes them concrete.

**3. The bare abstract pick exists and is the failure to prevent.**
`Q486839` member of parliament appears 20 times, with only dates as
qualifiers. Twenty Czech legislators recorded on the world-level class instead
of on `Q19803234`. That is the case the ranking must push to the bottom when a
concrete national item exists.

Two competing generic items for the same tier also show up: `Q64421048` "mayor
in the Czech Republic" (17 uses) beside `Q99356295` "mayor of a place in the
Czech Republic" (131). The table can rank the majority item first, but which
one is right is a merge question for the community, not for the loop.

A random sample of extracted titles shows what the queries look like: a third
are municipal and regional councillors ("Zastupitel města Tachov", "Zastupitel
Olomouckého kraje"), a large share are party and parliamentary-club posts
("místopředseda poslaneckého klubu ODS"), committee memberships
("rozpočtový výbor"), deputy-minister and ministry posts, and only a minority
are offices with an item of their own. Recall against the silver set will
therefore be measured on a subset, and the honest headline number is the
share of titles that reconcile *anywhere* (concrete, generic + qualifier,
abstract + qualifier, or none) with the reason.

Two mechanical notes for the loader: `Q30103103` has no `en` label at all
(`cs` only, "náměstek krajského hejtmana"), so labels must be read from every
language, and every P39 count above is over the pilot's own 873 items, not
Wikidata — a per-country count from WDQS is the next measurement.

## WDQS cost of the ranking signals, timed on Czechia (2026-09-20)

Three grouped queries over items with `P17` or `P1001` = `Q213`, run once
each against the live service (`max_age=0`):

| query                                              | rows | time  |
|----------------------------------------------------|------|-------|
| holders per position, `wdt:P39` (best rank)        | 168  | 32 s  |
| holders per position, `p:P39/ps:P39` (all ranks)   | 168  | 97 s  |
| `P279` children per item                           | 163  | 55 s  |

Best-rank and all-rank differ by 29 holder pairs out of 8,938, so the cheap
shape is good enough for a *ranking* signal (it would not be for a coverage
claim). Per-country holder counts are therefore affordable for a small country
in one query; Spain and France will need the same query chunked by position
`VALUES` (the 414 limit is ~150 QIDs per GET) or split by tier. The subclass
query as written also caught non-positions (`Q188` German language has
`P17` = Czechia and 51 subclasses), so every count query must be intersected
with the position closure, not scoped by `P17` alone.

The top Czech items by live holder count confirm the pilot's reading:
`Q108899569` municipal councillor 1,800, `Q99356295` mayor 1,238, `Q19803234`
Chamber of Deputies 1,217, `Q97482814` district representative 556. The
country's convention is visible from one query.

## The ranking signals, measured on the Czech pilot (2026-09-20)

Increment 4, against the rule-1-only fixture at `b4ff356`. **Scored on MRR
and top-1 and on nothing else.** The candidate set is whatever the text index
returned and the signals only re-order inside it, so recall@15 is identical
in every row of every table below — 93.4% on the `vocab_overlap` slice, from
the baseline to the shipped configuration. A recall number from this stage
would be a tautology, not a result.

The `vocab_overlap`-true slice is the primary, for the reason the fixture
rebuild gave: the pairing still mislabels 22.5% of gold rows and no date rule
can reach them, but circularity poisons a *recall* measurement, not a
comparison between two orderings of one candidate set.

### What was filled, and what the query service charged for it

Five grouped queries over the whole table in chunks of 120 QIDs, `max_age=0`,
run once against the live service on an evening when it was erratic — the
same shapes had taken half as long two hours earlier, and one of them 48 s
against 352 s.

| query | rows | first run (205 items) | second run (343 items) |
|---|---|---|---|
| holders, `wdt:P39` with `OPTIONAL` | 343 | 48 s | 56 s |
| holders who are citizens of the state | 343 | 66 s | 352 s |
| `instance_count`, `wdt:P31` inbound | 343 | 24 s | 159 s |
| `subclass_count`, `wdt:P279` inbound | 343 | 3 s | 268 s |
| `held_subclasses`, children somebody holds | 80 | 19 s | 149 s |

Two things the timings say. The service's variance is larger than the
difference between any two of these query shapes, so timing one of them once
measures the evening and not the query. And the first run counted only the
201 rows the state scopes, which is the wrong set: the search offers the
whole table, and the rows that most need discouraging — a world-level class,
another state's embassy — are exactly the ones a `P17` scope leaves
uncounted. `fill_counts` counts every row.

`scope_qualifier` and the ambassadorship flag cost nothing: the first is a
tally over the `item` table already fetched, the second is `type_closure`
served out of `type_edge`.

### The delta table

Cumulatively, each signal added to the ones above it:

| config | aggregate (746) | per tenure (688) | macro (78) | `vocab_overlap` (578) |
|---|---|---|---|---|
| baseline, text order | 0.528 / 33.8% | 0.534 / 34.2% | 0.512 | 0.601 / 37.7% |
| + `not_office` | 0.528 / 33.8% | 0.535 / 34.2% | 0.515 | 0.602 / 37.7% |
| + `holders` | 0.670 / 58.8% | 0.682 / 60.2% | 0.539 | 0.780 / 69.2% |
| + `class` | 0.679 / 59.8% | 0.690 / 61.0% | 0.545 | 0.790 / 70.4% |
| + `dates` | 0.680 / 59.8% | 0.691 / 61.0% | 0.547 | 0.791 / 70.4% |
| + `diplomatic` (shipped) | **0.681 / 59.9%** | **0.692 / 61.2%** | **0.558** | **0.792 / 70.6%** |

Each alone, against the same baseline:

| signal alone | aggregate | per tenure | macro | `vocab_overlap` |
|---|---|---|---|---|
| none | 0.528 / 33.8% | 0.534 / 34.2% | 0.512 | 0.601 / 37.7% |
| `not_office` | 0.528 / 33.8% | 0.535 / 34.2% | 0.515 | 0.602 / 37.7% |
| `holders` | 0.670 / 58.8% | 0.682 / 60.2% | 0.539 | 0.780 / 69.2% |
| `class` | 0.539 / 34.0% | 0.546 / 34.4% | 0.512 | 0.616 / 38.1% |
| `dates` | 0.537 / 35.3% | 0.538 / 34.7% | 0.530 | 0.611 / 39.1% |
| `diplomatic` | 0.527 / 33.6% | 0.535 / 34.2% | 0.513 | 0.600 / 37.5% |

**One signal is the whole result.** A holder count is worth 0.18 of MRR and
32 points of top-1 on the primary slice; the other four together are worth
0.012 and 1.4. That is not a disappointment — it is the answer to the
question the pilot's reading posed, that the only way to learn a country's
convention is to count who is recorded where — but it does mean the four
small signals are kept for what they *tag*, and for one named failure each,
rather than for their contribution to a mean.

Why the base ranking leaves so much on the table: the document is a bag and
`ts_rank` counts matched lexemes, so a query of four content words puts
dozens of candidates on exactly the same score, and the tie is broken by
QID. Most of what a signal buys here is breaking those ties on something.

### The two constants

`held_subclasses >= N`, at a convention floor of 50:

| N | `vocab_overlap` MRR | top-1 | items it tags that `instance_count` misses |
|---|---|---|---|
| 1 | 0.7895 | 70.24% | 29 |
| 2 | 0.7922 | 70.59% | 24 |
| 3 | 0.7922 | 70.59% | 20 |
| 5 | 0.7922 | 70.59% | 14 |
| 10 | 0.7922 | 70.59% | 10 |
| ∞ (`instance_count` alone) | 0.7898 | 70.42% | 0 |

**N cannot be measured on this fixture, beyond `N ≥ 2`.** Two through ten
score identically to four decimal places while the rule changes the tag on
between 24 and 10 items, which says those items are never near the top of a
shortlist any gold row is scored on. Both endpoints *are* measured: N=1 is
worse than the plateau, and dropping the clause entirely is worse than the
plateau, so the clause earns its place and its threshold does not. The
declared 3 sits inside the plateau and stays for that reason and no other.

The convention floor, holders who are citizens of the state, at N=3:

| floor | `vocab_overlap` MRR | top-1 | aggregate MRR |
|---|---|---|---|
| 0 | 0.7822 | 69.38% | 0.6719 |
| 10 | 0.7902 | 70.24% | 0.6787 |
| 25 | 0.7920 | 70.42% | 0.6802 |
| 50 | **0.7922** | **70.59%** | **0.6807** |
| 100 | 0.7871 | 70.07% | 0.6767 |
| 250 | 0.7781 | 69.20% | 0.6703 |
| 500 | 0.7781 | 69.20% | 0.6703 |

An interior optimum, and a shallow one: 25 and 50 differ by 0.0002. **The
bench does not choose between them and the decisive test does**, which is the
useful half of this measurement and is the next section.

### `Q486839` against `Q108899569`: a mechanical rule separates them

The two items have the same class-like *shape* and opposite meanings.
`Q486839` member of parliament is the bare abstract pick, 20 Czech
legislators filed on a world-level class. `Q108899569` member of a Czech
municipal council is the community's own answer, because Czechia mints no
item per municipality and puts the place in a `P1001` qualifier.

What the filled columns say about them:

| | holders | citizens of the state | `instance_count` | `subclass_count` | `held_subclasses` |
|---|---|---|---|---|---|
| `Q486839` | 7,026 | 46 | 18 | 567 | 497 |
| `Q108899569` | 1,799 | 1,260 | 0 | 4 | 4 |

Measured over every shortlist the 2,234 fixture titles produce, counting the
223 in which both appear:

| ordering | `Q486839` mean rank | its top-1s | `Q108899569` mean rank | its top-1s | abstract above generic |
|---|---|---|---|---|---|
| text only | 8.4 | 2 | 8.4 | 39 | 202 of 223 |
| + `holders` | 6.0 | 7 | 6.0 | 53 | 202 of 223 |
| + `class`, floor 25 | 5.6 | 9 | 5.4 | 62 | 202 of 223 |
| + `class`, floor 50 | 10.8 | 1 | 5.1 | 63 | **2 of 223** |
| shipped | 10.1 | 1 | 4.9 | 65 | **2 of 223** |

**Yes, and the rule is holders who are citizens of the state, floored above
46.** Three things in that table are worth keeping.

The holder count, which is otherwise the whole result, does **nothing** here:
both items saturate the log-scaled bonus, and the bad pick keeps its lead
over all 223 shortlists. A signal that carries a stage can be blind to the
case the stage exists for.

The floor is genuinely determined rather than picked. Ordered by citizens of
the state, the class-like items run … `Q4657217` municipal executive 54,
`Q486839` member of parliament 46, `Q212071` rector 44 …, so the rule needs a
floor above 46; the grid says it degrades above 100. The two constraints
intersect on 50, and the grid's own plateau would have been equally happy
with 25 — where the rule fires on nothing and the bad pick outranks the good
one in 202 shortlists out of 223, at an MRR two ten-thousandths lower.
**The aggregate metric is blind to the failure this increment was built to
prevent**, which is the third time in this loop that a defect was not found
by a test.

### The dates signal: half of it pays and half of it is destructive

The design said an abolished office should be boosted for a tenure that
ended before it and penalised for one that started after. Measured as two
halves, over the whole `holders + class` configuration:

| date signal | aggregate | `vocab_overlap` |
|---|---|---|
| off | 0.679 / 59.8% | 0.790 / 70.4% |
| conflict penalty only | 0.680 / 59.8% | 0.791 / 70.4% |
| fit boost only | 0.614 / 46.8% | 0.708 / 54.0% |
| both, as designed | 0.614 / 46.8% | 0.709 / 54.0% |

The boost costs 0.08 of MRR and **16 points of top-1**. The mechanism is
plain once it is stated: an inception that precedes a tenure is true of
almost every office that has existed for a while, so "boost a compatible
office" is an *is-old* bonus, handed to the twenty wrong old candidates as
freely as to the right one. The conflict penalty is specific — it fires only
where the office demonstrably did not exist — and is worth about a
thousandth.

Shipped as the penalty alone, with `WEIGHTS["date_fit"] = 0.0` and the
`date-fit` tag still emitted, because the observation is worth showing a
model even when it is worth nothing to an ordering. This is the stage A
resolution again: keep the half that pays, keep the measurement of the half
that does not.

### The named crowders, verified rather than assumed

The failure analysis named six items that most often push a correct answer
down. Mean rank across the shortlists each appears in, and how often each
reaches the top three:

| item | shortlists | mean rank before | after | top-3 before | after |
|---|---|---|---|---|---|
| `Q110408550` Minister of Industry | 374 | 6.7 | 9.4 | 133 | 43 |
| `Q110409158` Minister of Commerce and Travel | 383 | 7.2 | 10.1 | 104 | 43 |
| `Q110414308` Minister for Economic Policy and Development | 386 | 6.6 | 12.3 | 104 | 9 |
| `Q110420088` ministr hospodářství ČR | 393 | 6.4 | 10.5 | 86 | 42 |
| `Q101241090` ambassador of Saudi Arabia to Czechia | 128 | 8.7 | 11.0 | 16 | **0** |
| `Q486839` member of parliament | 445 | 8.4 | 10.1 | 10 | 5 |

All six are demoted and none is filtered; every one is still offered, tagged.
The four ministries carry 8, 8, 1 and 2 holders, so the holder count alone
answers them, exactly as predicted.

### Three things that contradict what was written before

**An inbound mission is identified by `P17`, not by `P1001`.** Of the 64
ambassadorships in the table only 9 carry a jurisdiction at all, and it is
the country claim that holds the receiving state: "ambassador of Poland to
the Czech Republic" is `P17` = the receiving state, "ambassador of the Czech
Republic to the United Kingdom" is `P17` = the United Kingdom. Reading the
jurisdiction with the country as its fallback splits 34 inbound missions from
30 outbound ones, which is the order of magnitude `wd/gazetteer.py` measured
by hand (29 of 194). One item is caught wrongly by it and is a known wart: a
permanent representation to a supranational body carries its *sending*
state's `P17`.

**`P463 member of` does occur in this corpus.** Four items take it as their
modal scoping qualifier, `Q8191099` member among them, which is what the
pilot's reading of the top thirty items said. A later note claiming it does
not occur is wrong.

**The modal qualifier is not a scoping qualifier without a deny list.** Taken
over everything but the dates, the modal qualifier of fifty positions is
`P1365 replaces` — a fact about whom the holder took over from, not about
which office this is. `NON_SCOPING_QUALIFIERS` therefore excludes the
succession, end-cause, term-length and appointed-by properties as well as the
dates, and the column then reads as its name promises: `P2389` organisation
directed on 14 items, `P1001` jurisdiction on 13, `P5054` member of cabinet
on 12, `P463` on 4, `P2937` parliamentary term on the Chamber seat. A column
that answered `P1365` would have been emitted by increment 7 as the qualifier
to write, and it would have written something untrue.

### The tag census over the 343 rows

`not_office` 25, `unheld` 43, `abolished` 13, class-like 71 — of which
`generic-by-convention` 10 and `abstract` 61 — `inbound-diplomatic` 34,
`diplomatic` 30, `foreign-scoped` 41. Nothing is filtered by any of them.

## What poliloom does (read 2026-09-20)

`~/Code/poliloom` is the OpenSanctions community tool with the same two-stage
shape (free text, then an LLM pick from a candidate list). What it settled on
and what it abandoned, from its code and migration history:

- **Discovery is dump-only.** A recursive `P279` CTE from four roots
  (`Q4164871` position, `Q29645880` ambassador of a country, `Q29645886`
  ambassador to a country, `Q707492` military chief of staff) minus the closure
  of an incident-driven ignore list (`Q114962596` historical position,
  `Q12737077` occupation, `Q618779` award, `Q193622` order, `Q63187345`
  religious occupation, `Q2977` cathedral, …). Membership is one hop: an
  item is a position if *any* direct `P31` or `P279` target is in the class
  set, and any single edge into the ignore closure drops it. The whole
  pipeline re-reads the 100 GB dump nightly under a three-day timeout.
- **Retrieval flip-flopped four times with no evaluation harness**:
  `pg_trgm` → pgvector embeddings → Meilisearch hybrid → Meilisearch
  keyword-only over labels, top 100 to the model, default ranking rules, no
  thresholds. No gold set, no recall number anywhere in the repo. The only
  ranking guidance is prose in the prompt: "strongly prefer country-specific
  positions over generic", which our Czech measurement says is wrong at the
  municipal tier.
- **Labels lose their language and aliases are not imported at all.** Their
  workaround is to have the extraction LLM append "(Myanmar)" to the query
  string. Jurisdiction is not a column; it is a prose string rebuilt from the
  relation graph at request time.
- **Abolished offices are excluded wholesale** via the historical-position
  root in the ignore list. There is no holder count, subclass count, or any
  popularity signal.

Worth taking: the roots + ignore-closure pattern as an auditable pair of QID
lists (their ignore list is production knowledge); truthy-rank filtering of
`P31`/`P279` before building the closure; a separate `label (qid, lang, text)`
table with a unique key and a trigram index, rather than a `TEXT[]`; and their
two-dump rule for deletions (never delete on absence alone). Worth avoiding:
dropping language and aliases, jurisdiction as prose, any-parent-poisons
exclusion, excluding historical offices, and changing the retrieval stack
without a measured test set. (`Q114962596` is confirmed as "historical
position"; `Q19832712` is "historical administrative division" and does not
belong in this design.)

## What zavod does (read 2026-09-20)

`zavod/shed/wikidata/position.py` and `datasets/_wikidata/peps/crawler.py` in
the opensanctions repo. The two designs read so far are mirror images:
poliloom descends from class roots over a dump; zavod **discovers by evidence
of use and classifies upward**.

- **Discovery is three flat SPARQL sweeps**, no transitive closure at query
  time. Per territory QID (one query per QID, never a `VALUES` block, because
  the six QIDs of `gb` together exceed the 60 s budget while each alone is
  inside it): positions with `P1001|P17` = the territory that either have a
  human holder via `P39` or name one via `P1308`. Per country: positions held
  by anyone with `P27` = the country and `P106` in {politician, diplomat,
  judge}, which catches offices with no jurisdiction of their own (postings
  abroad, IGO seats). Globally: positions with `P2389|P361` into a curated
  registry of ~110 international organisations. Measured: `Q145` 30 s / 2,102
  rows, `Q30` 53 s / 3,319 rows, `Q148` 37 s / 364 rows; Germany hit the
  client's 60 s read timeout and the HTTP timeout was raised to 90 s. The
  rewrite that produced this cut discovery from ~58k queries, many of them
  `(wdt:P31|wdt:P279)*` closures, to 814 flat ones, and deleted a 500-line
  hand-maintained subclass triage table on the way.
- **Classification is an upward P31/P279 closure per item**, depth-capped at
  six hops (`nomenklatura.wikidata.model.Item.types`), tested against three QID
  lists: `POSITION_BASICS` (`Q4164871`, the two ambassador classes, `Q707492`
  chief of staff) as the "is a position at all" gate; `EXCLUDE_TYPES`
  (historical position `Q114962596`, orders, awards, honorary titles,
  cathedrals, priests, religious occupations) as a silent veto; `ALLOW_TYPES`
  (cardinals, prosecutors, magistrates, the Co-Prince of Andorra) overriding
  both. A ~40-entry `SUB_TYPES` map (mayor, minister, head of government,
  judge, central bank governor, party leader, …) grants topics. The bar for
  `EXCLUDE_TYPES` is stated in a comment: only classes unambiguously
  non-PEP-conferring, everything doubtful goes to review.
- **Abolished offices are cut at a date, not excluded.** `P576|P582` best-rank
  value before `1990-12-26` drops the position at discovery and at
  classification; later abolition keeps it, because living former holders are
  still PEPs. Ended `P17`/`P1001` claims and historical countries contribute no
  country but do not kill the item.
- **A position with no country is dropped** unless a reviewer marked it PEP.
  Country comes from `P1001`, `P17`, `P27`, then a recursive fallback over
  `P1376`, `P361`, `P749`, `P159`, `P2389`.
- **The stateful `position` table** is keyed by `entity_id` with no unique
  constraint, tri-state `is_pep` (`None` = awaiting review, used on purpose for
  IGO seats), `topics` human-owned after insert, `dataset` = whichever crawler
  enrolled it first, and `caption`/`countries`/`subnational_areas` refreshed on
  drift. Nothing anywhere computes a holder count; the only holder signal is an
  in-run set gating whether a position is emitted at all.
- **Redirects are a first-class case**: the crawler compares the fetched
  `item.id` with the requested QID and keeps an alias map, because merged
  position items are common.

What this means for the lookup table:

1. **Take the usage sweep as discovery source (b) verbatim**, one query per
   territory QID, with the same 90 s timeout. It is measured to fit every
   country inside WDQS's budget at ~3k rows, and it returns exactly the items a
   P39 can point at. Poliloom's class descent becomes source (a), run from
   the same four `POSITION_BASICS` roots minus the same `EXCLUDE_TYPES`
   closure, and the two sets are compared per country rather than unioned
   blindly: an item in (a) and not (b) has zero recorded holders, an item in
   (b) and not (a) is mistyped, and both facts are ranking signals.
2. **Do not copy the country gate or the 1990 cutoff.** Both are PEP policy,
   correct for a screening product and wrong for a reconciliation table: a
   Czech article naming a 1970s Czechoslovak ministry needs the abolished item
   to *match*, and the loop's job is a correct P39, not a PEP verdict.
   `abolished_at` is a column, `is_pep` from the prod extract is a column, and
   neither is a filter.
3. **Take the redirect handling.** The loader must store the canonical QID it
   was redirected to and remember the alias, or the same office enters twice
   under a merged and a surviving ID.
4. **The topics map is a free classifier.** `SUB_TYPES` keyed on the upward
   closure gives every row a coarse kind (legislative, executive, judicial,
   municipal, diplomatic, party) at load time, which is what turn two needs to
   show the model beside the label and what `propose` needs to decide whether
   a party post is in scope.

## What this repo already has (inventoried 2026-09-20)

The `wd/` toolkit and `research/position_items.md` answer several of the
questions in §6 before any new measurement, and they change two of the
assumptions above.

**Class descent from `Q4164871` alone misses offices people hold.** Of the
147,584 distinct items that are the target of some `P39`, 110,613 carry
`P31 = Q4164871` and **17,788 carry `Q294414` public office instead**; among
ministers, `Q294414` is the modal type (4,428 of 5,211, 85%). The metaclasses
in live use are eight (`Q294414`, `Q4164871`, `Q17279032` elective office,
`Q114962596` historical position, `Q83856136` legal position, `Q136649946`
type of position, `Q355567` noble title, `Q42045197`); `wd/shape.py`
`POSITION_METACLASSES` carries six of them. `Q114962596` is deliberately
*both* a metaclass and an `EXCLUDE_TYPES` member, so "historical position" as
a negative signal has to be read as "abolished", not "not a position". The
in-repo per-country queries (`wd/gazetteer.py:COUNTRY_OFFICES`,
`wd/positions.py:COUNTRY_NAMES`) root at `Q4164871` with a hybrid predicate,
`p:P31/ps:P31/wdt:P279*` (rank-safe instance hop, truthy subclass walk), and
reach `Q294414` through `P279*`; they are measured at **Spain: 13,197 items,
115,551 label and alias rows, 29 s** in one query with no language filter,
which is the load path for discovery source (a) and for labels together.

**Holder counts have a proven shape and a known cost.** `wd/positions.py:
holder_counts` groups `p:P39/ps:P39` by `VALUES` chunks of 120 (the 414
limit); the country-wide census in `recipes/country_sweep.md` is the same as
the query timed above. `wdt:P39` reads half the truth (Czechia 7,554 against
14,124), but the ranking signal can afford it. `wd/positions.py:subclass_held`
is the exact **class-versus-seat detector** this design wants: it counts a
cohort's P39 by `P279` child of a target, and it is how `Q20706330` "US
Supreme Court justice" (a defect-free item nobody holds) was separated from
`Q11144` (the seat people hold). The same file's `Hit.covers` rule, the
`STOPWORDS` list and the six pinned negatives in `scripts/check_enrich.py` are
the retrieval-direction rule and its regression test, ready to reuse.

**Class-likeness has a measured prior.** Items minted and never populated are
common: `Q30185` mayor has 4,279 direct `P31` instances (Brazilian
mayoralties), of which only 74 have any holder. `Q294414` has 25,917 direct
instances. So "many `P31` instances" marks a metaclass, "many `P279`
children with holders of their own" marks a class whose seats are elsewhere,
and "zero holders" alone marks nothing (it is the normal state of a freshly
minted office).

**`P1001` versus `P17` is a per-tier convention, already measured.** National
offices carry both naming the country (ministers 91.8%); sub-national offices
carry `P17` the state and `P1001` the polity governed (mayors 97.2%, governors
93.1%); bilateral diplomatic posts invert (`P17` = receiving state 86.4%,
`P137` = sending state 95.8%, and inbound missions land in a country's set
through `P1001`, 29 of Czechia's 194). Renamed offices are one item per era
chained with `P1365`/`P1366` and bounded by `P571`/`P576`;
`wd/gazetteer.py:for_target` walks that chain one hop in each direction,
deliberately not transitively. `wd/shape.py:NOT_AN_OFFICE` holds Wikidata's
own boundary (`P1889` on `Q4164871`: title of authority, occupation,
profession, function, job) plus ranks, bodies and honours; the closure cannot
answer "is this an office" because profession and rank both reach
`Q4164871` within six hops, so the `not_office` tag must come from *declared*
types, as `verify()` does.

**The LLM-facing row format exists.** `wd/gazetteer.py:Entry.line()` renders
`QID | label | description | kind | part of | exists: start–end | topics |
N recorded holders | item defects`, with a header that tells the model a
ministry or council is a body and the office is the seat in it. That is the
turn-two candidate line, and `wd/rerank.py`'s verdict kinds (`same-office`,
`renamed`, `generic-class`, `body-not-seat`, `wrong-office`, `none`) are the
closed set a pick should return.

**What peploop lacks and must add**: a SPARQL helper (port `wd/api.py:sparql`
onto `peploop.http`, add `query.wikidata.org` to `HOST_RATES`); a
jurisdiction-text fetch (labels and aliases of each `P1001` target in all
languages, which nothing in `wd/` does); any abolished-office query (the repo
reads `P576` off fetched entities only); and a per-country size table beyond
the six countries measured so far. The `candidate` table in `schema.sql` is
unpopulated scaffolding that nothing reads or writes, so replacing it with a
`position` table costs nothing. `peploop.http.get_text(max_age=0)` skips the
cache both ways, unlike `wd/http.py`, which still writes.

## The three discovery sources, measured on Czechia (2026-09-20)

Each source run once as one live query, scoped to `Q213`:

| source                                                            | items | time |
|-------------------------------------------------------------------|-------|------|
| A. class descent, `p:P31/ps:P31/wdt:P279* Q4164871` + `P17|P1001` | 203   | 58 s |
| B. usage, zavod's sweep (`P39` holder or `P1308`) + `P17|P1001`   | 169   | 92 s |
| C. usage by citizen-occupation (`P27` = CZ, `P106` ∈ {politician, diplomat, judge}) | 236 | 21 s |

| overlap                                     | items |
|---------------------------------------------|-------|
| A ∩ B                                       | 161   |
| A − B: typed as a position, nobody holds it | 42    |
| B − A: held, not reached by the descent     | 8     |
| C − (A ∪ B): held by Czech politicians, scoped to no Czech polity | 132 |

**B − A contains `Q99356295` "mayor of a place in the Czech Republic"**, the
item with 1,238 holders. Its `P31` is `Q136649946` type of position and its
`P279` is `Q30185` mayor; the descent walks `P31` then `P279*` upward from the
*type*, never from the item's own `P279`, so a country-generic class that is a
subclass of mayor and an instance of "type of position" is invisible to it.
The remaining seven are two cathedral chapters, an orchestra, an award, a
chaplaincy and two inbound ambassadorships: the junk the usage sweep admits.
So neither source is sufficient and the union is small: **A ∪ B = 211 for
Czechia.**

**C is a different population.** 132 of its 236 items are outside both: global
abstract items in live use by Czech holders (`Q1127270` deputy chairperson,
`Q1162163` director, `Q110242307` councillor, `Q1055894` deputy, `Q1068947`
chief physician), Czech offices abroad (ambassadors of the Czech Republic to
the UK, Switzerland, Poland, Sweden; a European Commissioner; a UN General
Assembly presidency), and Czech items with no polity claim at all
(`Q109979872` director general of the fire service, `Q108397872` chair of a
council of elders). All of these are things a Czech article will name and turn
one will extract, so the table needs them, tagged by the source that found
them: **an item reached only through C is either abstract or foreign-scoped,
and both are ranking facts.** C also confirms that the outbound diplomatic
lane cannot be found by `P17|P1001` = CZ at all, only by who holds it.

Two loader consequences. The descent query at 58 s for a country of 200
items sits at the WDQS budget, because `wdt:P279*` from every position type is
the expensive part, not the country filter; Spain's 29 s in the notes above
was measured on a different day, and the variance is the point. The usage
sweep was run with zavod's `P1308` arm and `Q5` guard unchanged; whether either
matters for the set was not tested.

## The flat document, ablated on the Czech pilot (2026-09-20)

Increment 3 built the search §2 and §3 originally specified — a `pg_trgm`
channel and a `simple` full-text channel per *name*, a second trigram channel
over `jurisdiction_text`, a Jaccard token score and a boolean `covers` first
sort key — measured it, and then measured what else the same table could
support. It lost to something with a quarter of the code.

| design                                             | macro R@15 | aggregate R@15 | MRR (macro) | top-1 |
|----------------------------------------------------|-----------:|---------------:|------------:|------:|
| per-name trigram + FTS, jurisdiction channel, Jaccard | 70.2%   | 64.1%          | 0.493       | 17.5% |
| one token-bag document per position, `ts_rank`     | 77.2%      | 81.0%          | 0.560       | 40.0% |

The lesson is not about Postgres. Scoring each name separately asks *is there
one string here that looks like the query*, and no single label on the item
carries both the office and the place that an article writes in one breath.
Pooling the names into one document asks *how much of what the article said
does this item account for*, which is the question retrieval was being asked.

### What earns a place in the document

Measured by removing it and re-running. All of these stay:

| in the bag                              | why it pays |
|-----------------------------------------|-------------|
| the item's own labels and aliases, every language | the core; the name the article used is the one that has to match |
| names of `P1001` jurisdiction, every language     | the cross-language bridge — a place name travels between languages largely unchanged |
| names of `P17` country                            | offices the article names with the state rather than the polity |
| names of `P361` / `P2389` body                    | an article often names the chamber and not the seat |
| names of `P279` kinds                             | the generic word for the office when the item's own label is a proper name. The ablation's note reads *labels*; the loader writes every name, and the divergence below is about that |
| `P1365` / `P1366` succession, one hop each way    | **reachability, not score** — see the caveat below |
| each token's six-character prefix                 | ~3 points; the inflection handling, with no stemmer available |
| the jurisdiction string concatenated onto the title | +7.7 aggregate over the title alone |

### What does not, and was removed

| left out                                    | measurement |
|---------------------------------------------|-------------|
| descriptions, any language                  | `en`/`mul` neutral; all languages −1.5 macro, −1.7 top-1. "Czech politician" is in hundreds of documents at once |
| Wikipedia sitelink titles                   | only 297 of 2,292 carry a token the labels do not; effect exactly zero |
| `P1448`/`P1813`/`P2561`/`P1705` monolingual names | 28 statements across 343 items. Nothing to index |
| the other ~74 item-valued statement properties | 1,377 targets over 78 properties, 30 s of extra fetching for one small country; macro flat, MRR −0.03, and the bag 2.4× bigger |
| `P1889 different from`                      | **never.** It is an anti-relation: it names exactly the items this one is confusable with, so indexing it teaches the search the wrong answer |
| the jurisdiction as a trigram channel of its own | contributed exactly 0.0. The place names are already in the document |
| `country_qid` as a candidate filter         | −23.7 macro. Removed before this ablation and not reinstated |

### Scoring

`ts_rank(tsv, q, 0)` over an OR-query, and nothing else. Because the document
is a *bag* — every lexeme de-duplicated, so every frequency is 1 — `ts_rank`
with flag 0 sums to the number of query terms the document matched. It is
uniform coverage, numerically identically so, which is why there is no
scoring code in Python at all.

| scoring variant                       | against uniform coverage |
|---------------------------------------|--------------------------|
| IDF weighting                         | +0.02 MRR, −0.4 aggregate. Not worth the statistics it needs |
| normalisation flags 0, 4, 32          | identical to each other. Flag 0 is used |
| flags 1, 16 (divide by document length) | +1.2 macro, −8.6 top-1 — the wrong trade for a list read from the top |
| flags 2, 8 (divide by unique-word count) | catastrophic: 65% aggregate |
| `similarity()` over the same document | 23.3% aggregate, 137 ms a query |
| `word_similarity()` over it           | 75.6% aggregate, 225 ms a query |
| `ts_rank` over it                     | 81.0% aggregate, 1.8 ms a query |

Trigram earned its place when the unit being compared was one short name.
Over a document of a few thousand characters it mostly measures length.

### The succession caveat, recorded so nobody quotes the number

Adding `P1365 replaces` alone reads as **+15.4 top-1**, which is not a
finding about succession. All 120 rows it improved are the single office
`Q19803234`, which is 248 of the 532 gold rows by itself and whose `P1365`
is `Q25265211` Czech National Council; macro recall is completely flat.
Succession is in the document because a renamed office has to be reachable
by the name it used to have, and for no other reason. One hop, both
directions, non-transitive, as `wd/gazetteer.py:for_target` does — a
transitive walk names the whole ministry lineage and dissolves the
distinction it is there to preserve.

### What the shipped version measures, and where it differs from the ablation

Re-measured after the design was written back into `positions.py` and
Czechia reloaded (343 positions, 11,567 names, 550 referenced items, 83 s):

| measure                                   | before | after |
|-------------------------------------------|-------:|------:|
| macro recall@15 over 72 gold answers      | 70.2%  | 77.2% |
| aggregate recall@15 over 532 gold rows    | 64.1%  | 81.0% |
| macro MRR                                 | 0.493  | 0.560 |
| top-1                                     | 17.5%  | 40.0% |
| recall@15 over the 400 answerable rows    | 84.0%  | 94.0% |
| weak rows, recall@15                      | 42.3%  | 53.2% |
| titles retrieving nothing at all          | 1.1%   | 0.0%  |
| a search, end to end                      | 58 ms  | 6.2 ms |
| the ranking query alone                   | —      | 1.8 ms |

Two of those numbers are not what the ablation predicted, and both are worth
keeping rather than smoothing over.

**Top-1 is 40.0% against a predicted 28.0%.** The arithmetic says why: the
ablation's flat-design figure was taken *before* succession was added, and
`P1365` alone was separately measured at +15.4 top-1. Which is exactly the
artefact the section above warns about — this is `Q19803234` being 47% of
the gold set, not a twelve-point improvement in anything.

**Macro is 77.2% against a predicted 81.1%**, while aggregate landed on
target. The shipped loader puts *every name in every language* of each
referenced item into the document, where the ablation's note reads "`P279`
kind labels"; the difference is thousands of alias tokens on generic
parents, and a generic parent that matches more queries is precisely what
costs a rare office its rank. The mean document is 645 lexemes and the
largest is 2,967 — a military rank whose own aliases, its kind's aliases and
its state's names are all in it. Unresolved, and the first thing to try
before increment 4 adds a signal.

**The gap at k=15 is now ranking, not retrieval — which inverts increment
3's own conclusion.** At k=200 the same search reaches 91.4% aggregate,
89.2% macro, and **100.0% of the 400 answerable gold rows**. Every row a
correct fixture pairing could ask for is in the pool; what is left is the
order, which is what increment 4 is for. The old search's recall did not
move between k=15 and k=200 at all.

**The GIN index is used, and the planner is right not to always use it.**
On a 343-row table a six-lexeme OR-query matches 270 rows, so the planner
ignores `position_tsv_idx` and takes a sequential scan (5.4 ms); on a
selective query it takes a bitmap index scan on that index unprompted, and
forcing the index on the broad query is faster still (1.8 ms). The index is what makes this
survive Spain, not what makes Czechia fast.

## 6. Questions the research answered, and the ones left

Answered above:

- **Which classes to descend from.** The eight live metaclasses, with
  `Q294414` the modal one for real offices, and the measured fact that the
  descent still misses country-generic classes typed `Q136649946` (the Czech
  mayor item). Descent is one source of three, not the definition.
- **What zavod and poliloom compute.** Neither counts holders or subclasses;
  zavod's usage sweep and its three QID lists are reusable, poliloom's
  ignore-closure and labels-table shape are reusable, and both exclude things
  a reconciliation table must keep.
- **Holder counts without WDQS.** No such source exists. WDQS grouped counts
  are affordable per country and returned the country's convention directly.
- **Czech source sizes and overlap.** A 203, B 169, C 236; A ∪ B 211; C adds
  132 items outside both.

Still open, and each is the first measurement of the increment that needs it:

- Which abstractness heuristic separates `Q486839` member of parliament (bare
  abstract, 20 pilot uses) from `Q108899569` municipal councillor (generic by
  convention, 302 uses) *mechanically*, without a hand list. The candidate
  answer is "holders in this country" over "holders elsewhere", tested in
  increment 4.
- Whether the scoping qualifier a generic item is used with (`P1001` for the
  Czech councillor, `P2389` for chairperson, `P463` for member) can be read
  cheaply enough to store; the pilot's own 873 items say yes for Czechia, and a
  statement-node query for it has not been tried.
- How search quality degrades when 80,000 French mayoralties share the
  table with 200 Czech offices. Increment 6 — but *not* with `country_qid` as
  a first-pass filter, which increment 3 measured and removed: it costs 23.7
  macro points on one country alone, and whatever keeps a large table flat
  has to be a ranking signal instead.

## 7. The plan

Seven increments, each with the measurement that closes it. The first four
run on Czechia alone and answer "does the search work" before any large
country is loaded, which is what the user asked for. Everything is
additive to `peploop/`; the `candidate` table is dropped from `schema.sql`.

### Tables

```
position
  qid               TEXT PRIMARY KEY        -- canonical after redirect
  label             TEXT                    -- best label (en → mul → any)
  description       TEXT
  country_qid       TEXT                    -- P17, first un-ended value
  jurisdiction_qid  TEXT                    -- P1001, first un-ended value
  jurisdiction_text TEXT                    -- labels+aliases of the P1001 item, all langs
  body_qid          TEXT                    -- P361 / P2389, for "part of" in the row
  kinds             TEXT[]                  -- SUB_TYPES hits on the 6-hop upward closure
  sources           TEXT[]                  -- {descent, usage, citizen, tracked}
  not_office        BOOLEAN                 -- NOT_AN_OFFICE on declared types, no metaclass
  inception         DATE, abolished DATE    -- P571/P576, P580/P582 fallback, precision ≥ 9
  replaces          TEXT[], replaced_by TEXT[]   -- P1365 / P1366, one hop
  holders           INTEGER, holders_at TIMESTAMPTZ      -- NULL = not counted
  instance_count    INTEGER                 -- items with P31 = this
  subclass_count    INTEGER                 -- items with P279 = this
  held_subclasses   INTEGER                 -- of those, with ≥1 holder (the seat-elsewhere test)
  is_pep            BOOLEAN                 -- from the prod extract; NULL = untracked
  topics            TEXT[]                  -- from the prod extract
  redirected_from   TEXT[]
  search_text       TEXT                    -- the token bag, whole tokens + 6-char prefixes
  tsv               tsvector GENERATED      -- to_tsvector('simple', search_text), GIN
  loaded_at         TIMESTAMPTZ

position_name
  qid   TEXT REFERENCES position, lang TEXT, text TEXT, alias BOOLEAN
  PRIMARY KEY (qid, lang, text)
  INDEX (qid) -- the source of search_text and the display name; not searched
```

Names keep their language (poliloom lost it and had to ask the LLM to
disambiguate), aliases are loaded (poliloom skipped them), and every ranking
signal is a nullable column filled by its own step, so a signal that proves
too expensive for a large country is simply left null there.

### Increment 0: a SPARQL client in peploop

Port `wd/api.py:sparql` onto `peploop.http.get_text` and `peploop.db`'s cache:
whitespace-normalised query as cache key, bare QIDs in bindings, `cache_drop`
on a non-JSON 200 body. Add `query.wikidata.org` to `HOST_RATES` at 1/s.
`VALUES` chunks of 120, statement-node chunks of 40, both from `wd/`.
Closes when the three Czech source queries above run through it.

### Increment 1: the silver test set

`scripts/position_fixture.py` reads every extracted title from
`extraction.response_json -> 'positions'` for the Czech run beside the
person's P39 claims from `item`, and writes `peploop/fixtures/cz_positions.jsonl`
with one row per title: `title, jurisdiction, lang, start, end, person_qid,
p39: [{qid, start, end}]`. Where a title's start date equals a P39's `P580` at
shared precision, the row also gets `gold_qid`; the rest carry only the
person's P39 set as a weak label. Report: titles, rows with a gold pair, rows
with a weak label only, rows with neither. Expected from the profile above:
about 2,800 titles have a start, ~2,000 P39 statements have `P580`, so several
hundred gold pairs and a long tail of party and committee posts with nothing.
Nothing is hand-labelled; the human reads disagreements later.

Built 2026-09-20 from the latest extraction per person (the 3,047 titles
counted earlier were over every extraction, including superseded prompt
versions):

| measure                                   | value |
|-------------------------------------------|-------|
| people with at least one extracted title  | 723   |
| titles                                    | 2,234 |
| titles with a gold pair                   | 532   |
| titles with a weak label only             | 1,670 |
| titles whose person has no P39 at all     | 32    |

Gold pairs are dominated by `Q19803234` (248 of 532), so the bench must
report macro-averaged recall over gold QIDs beside the aggregate, or it will
mostly measure one office. The first row of the file is the design's central
case: "Starosta obce Kravaře" pairs by date to `Q99356295`, the generic mayor
item, with the village in the qualifier.

Those numbers are **against the superseded set**. Everything above this line
was measured before the rebuild below and is kept as the record of what the
first heuristic produced.

#### Rebuilding the pairing, and what it measured (2026-09-20)

The first heuristic took the first non-null of a title's start and end,
looked for exactly one P39 agreeing on it, and never checked the other
endpoint. It is wrong about a quarter of the time, and the failure is not
date precision (89.5% of pairs rest on day-precision dates) but correlated
offices: a member elected on a given day also becomes deputy chair of a
committee that day, and the committee post inherits the chamber seat as its
label. `Q10853442` has one P39 serving as gold for six different titles.

The rebuild's constraint is that **a silver set selected by vocabulary
overlap cannot measure a token-based retriever** -- recall goes to 100% by
construction. So pairing stays date- and structure-driven, and vocabulary
agreement is written onto the row as `vocab_overlap` and never read by the
selection. Four rules:

1. A person's titles group into tenures by `(start, end, acting)`. Extraction
   reads one article per language, so a language occurring twice inside one
   date group proves the group holds two offices sharing dates, and the group
   is awarded nothing.
2. Every endpoint both sides carry must agree, not just the first one found.
3. One-to-one at the *tenure* level: a statement is gold for at most one
   tenure and a tenure for at most one statement, ties dropped rather than
   broken. At tenure level, so that one ministry named in six wikis stays six
   titles with one shared answer.
4. Tightness orders the competition: both endpoints beats one, day beats
   month beats year.

Each row now also carries `tenure_id`, `evidence`
(`both-endpoints` | `start` | `end`), `vocab_overlap`, `vocab_distinctive`
(the same test over tokens carried by under 5% of position documents) and the
`reason` a tenure was awarded nothing. The bench reports deduplicated by
tenure beside deduplicated by title.

**It made the set worse, and that is the finding.**

| fixture                     | gold rows | gold tenures | any token | distinctive |
|-----------------------------|-----------|--------------|-----------|-------------|
| first heuristic (superseded)| 532       | 357          | 77.3%     | 65.4%       |
| rules 1+2+3                 | 270       | 244          | 72.2%     | 58.1%       |

Ablated one rule at a time over the same 723 people:

| configuration                          | gold | any token | distinctive |
|----------------------------------------|------|-----------|-------------|
| the first heuristic (superseded code)  | 532  | 77.3%     | 65.4%       |
| every rule off                         | 764  | 77.1%     | 66.1%       |
| rule 1 alone, language collision       | 746  | 77.5%     | 66.8%       |
| rule 2 alone, both endpoints           | 305  | 71.8%     | 57.0%       |
| rule 3 alone, one-to-one per tenure    | 517  | 72.0%     | 58.2%       |
| rules 1+3                              | 499  | 72.3%     | 58.9%       |
| rules 1+2+3, as shipped                | 270  | 72.2%     | 58.1%       |
| rules 1+2+3, endpoints tolerant to 1y  | 452  | 78.5%     | 65.5%       |

Every row but the first is `scripts/position_fixture.py --dry` with
`--no-collision`, `--loose-endpoints`, `--no-one-to-one` and `--tolerance`
in the combination that names it; the switches exist so the table can be
re-run rather than quoted.

The rules keep the suspect rows in preference to the sound ones: of the 411
old gold rows sharing vocabulary with their answer 44.3% survive, of the 121
sharing none 57.0% survive. The reason is measurable. Over every
(tenure, P39) pair with at least one agreeing endpoint, the pairs where
*both* endpoints agree share vocabulary 64.6% of the time (n=158), against
70.6% where the second endpoint disagrees (n=677) and 74.0% where there is no
second endpoint (n=204). **Agreeing on both dates is evidence against a pair
being right**, because an article dates a tenure by the day the holder left
and Wikidata by the day the successor arrived, while a committee post copies
its parliamentary term verbatim and therefore matches perfectly.
`Q3409229` on `Q10819807` runs 2017-12-06..2021-12-17 against an article's
2017-12-06..2021-11-28: exact at the start, nineteen days out at the end,
discarded. `Q12023211`'s "predseda Vyboru pro obranu" 2006..2010 lands
exactly on a `Q19803234` statement, and is kept.

Rule 1 is the one rule that pays, and it fires on 14 rows: correlated offices
usually differ in their end date, so they rarely land in one date group at
all. Against the permissive baseline it costs 18 rows and buys 0.4 and 0.7
points. The tolerant variant in the last row was measured and **not adopted** --
picking a tolerance because it raises the acceptance metric is tuning toward
the number.

Retrieval re-baselined on the rebuilt set, not comparable to the numbers in
the section below because the label set changed:

| measure                          | superseded set | rebuilt set |
|----------------------------------|----------------|-------------|
| gold rows                        | 532            | 270         |
| aggregate recall@15              | 82.5%          | 78.5%       |
| deduplicated by tenure, recall@15| 82.9%          | 79.9%       |
| macro recall@15                  | 81.1% (72)     | 74.4% (56)  |
| macro MRR                        | 0.553          | 0.457       |
| aggregate MRR / top-1            | 0.563 / 40.6%  | 0.482 / 31.9% |
| rows with `vocab_overlap` true   | 95.5% recall   | 92.8% recall |
| weak rows recall@15              | 54.0% (1,670)  | 58.9% (1,932) |

Every one of those is a statement about the test set and not about the index:
the search did not change between the two columns.

### Increment 2: the Czech loader

`peploop/positions.py:load_country(cc)`:

1. Sources A, B, C as measured, each tagging `sources`. D (the prod extract)
   is loaded once, globally, as `is_pep`/`topics` onto rows that exist and as
   rows of its own tagged `tracked` where they do not.
2. Redirect-safe entity fetch (`peploop.wikidata.fetch_items`, `max_age=0`)
   for every QID in the union: labels and aliases in all languages into
   `position_name`, description, `P17`, `P1001`, `P361`/`P2389`, `P571`/`P576`,
   `P1365`/`P1366`, declared types.
3. Upward closure over `P31`/`P279`, six hops, batched level by level as
   `wd/shape.py:type_closure` does, into a `type_edge` cache table; `kinds`
   from `SUB_TYPES`, `not_office` from `NOT_AN_OFFICE` on declared types.
4. Jurisdiction text: one entity fetch for the distinct `P1001` targets.
5. `loaded_at` per row; re-running a country updates in place and never
   deletes (a QID absent from this run's union keeps its row; deletion is a
   later decision, poliloom's two-run rule is the template).

Closes when Czechia loads in under ten minutes and every QID in the fixture's
P39 sets is either in the table or listed as missing with its label.

### Increment 3: the search, measured before any ranking

`peploop/positions.py:search(title, jurisdiction, country_qid, limit=15)`.
`scripts/position_bench.py` runs every fixture row and reports **recall@15
and MRR on gold rows**, recall@15 on weak rows (any of the person's P39 in
the top 15), and the share of rows with no hit at all, broken down by `lang`
and by whether a jurisdiction string was present. This is the number the rest
of the plan moves; it is measured with no ranking signal at all so that every
later signal has a delta.

The search this increment specified — trigram over `position_name.text` and
over `jurisdiction_text`, `simple` full text beside it, a Jaccard score, a
`covers` first sort key, the run's country first — was built, measured, and
replaced. What it is now: one `to_tsquery('simple', …)` of the title's and
the jurisdiction's lexemes against one `tsv` per position, ordered by
`ts_rank(tsv, q, 0)`. Two queries per search, the second of them only to
name what matched. The ablation that decided every part of it is below.

### Increment 4: the ranking signals, one at a time

Fill the nullable columns for Czechia and re-run the bench after each:

1. `holders` from the grouped `wdt:P39` query, chunked by 120 QIDs.
2. `instance_count`, `subclass_count`, `held_subclasses` from three grouped
   queries over the same chunks (`wd/positions.py:subclass_held` is the third).
3. `abolished`/`inception` already loaded; the bench passes each row's
   `start`/`end` so the date-fit signal can be scored.

Then the tags the model will see, derived, never hand-listed:

| tag                     | rule                                                        | rank effect |
|-------------------------|-------------------------------------------------------------|-------------|
| `not_office`            | declared type in `NOT_AN_OFFICE`, no metaclass              | last        |
| `abstract`              | `instance_count > 0` or `held_subclasses ≥ 3`, and holders in this country < some measured floor | below every concrete hit |
| `generic-by-convention` | same shape, but holders in this country ≥ the floor         | ranked with concrete items, shown with its scoping qualifier |
| `unheld`                | `holders = 0`, source is descent only                       | below held items |
| `abolished`             | `abolished` set                                             | boosted when the tenure ends before it, penalised when the tenure starts after |
| `foreign-scoped`        | source is citizen only, `country_qid ≠ run country`         | shown, not boosted |

The floor and the "≥ 3" are the two constants this increment exists to
measure: the bench says whether `Q486839` drops and `Q108899569` stays. If a
mechanical rule cannot separate them on Czechia, that is the finding, and the
scoping-qualifier tally from the pilot's own items is the next signal to try.

**Done, and the measurement section above supersedes this table in three
places**: the abolished row's boost is measured destructive and ships at zero
weight, `not_office` is a signal of its own rather than an always-on penalty,
and an inbound mission is recognised by `P17` with `P1001` preferred where it
exists rather than by `P1001` alone.

### Increment 5: the second turn

`prompts/reconcile.md`: the shortlist rendered as `wd/gazetteer.py:Entry.line()`
does (`QID | label | description | kind | part of | exists | holders | tags`),
the header that explains a body is not its seat, the office as written with
its jurisdiction, dates and quotes, and a closed verdict set (`same-office`,
`renamed`, `generic-class`, `body-not-seat`, `wrong-office`, `none`) with the
pick constrained to the offered QIDs by the schema. Run on the gold rows and
report agreement with the gold QID and the distribution of verdict kinds; a
`generic-class` verdict on a `generic-by-convention` candidate is the case to
read by hand, because it is where the prompt and the country's convention
disagree. No proposal is written; `propose` still skips positions.

### Increment 6: scale

Load Poland, then Spain, with timings per step. Re-run the Czech bench with
Spain in the table to see whether the country-first filter keeps recall and
MRR where they were. Decide from the numbers whether holder counts are filled
for a 13,000-item country or left null above a size, and whether France
(80,000 rows) is loaded row-complete or as `tracked` rows only until a French
run needs it.

### Increment 7: wire it in

Extraction becomes the two-turn conversation `design.md` §5 describes;
`propose` emits `P39` with the scoping qualifier the row says the community
uses, and an unmatched title goes to the creation queue with its evidence.
This increment is the only one that changes a table other than the two new
ones, and it is scoped separately when increments 3 and 4 have a number.

### Deliberately left out

Deleting rows a re-run no longer finds; a `place` table or any shared lookup
machinery; a label-regex or CirrusSearch channel (the fixture will say whether
recall needs it); any filter on `is_pep`, on the 1990 cutoff, or on municipal
countries — those are PEP policy and belong downstream of a correct P39.

## Moving development to a VPS (2026-09-20)

What the position work needs from the laptop, and where each piece went:

| resource                              | disposition |
|---------------------------------------|-------------|
| Czech silver test set                 | `peploop/fixtures/cz_positions.jsonl`, built by `scripts/position_fixture.py` from the local database; committed |
| the peploop Postgres database (33 MB) | `pg_dump -Fc` to `~/tmp/peploop.dump`; copy out of band, restore with `pg_restore -d peploop ~/tmp/peploop.dump` after `createdb peploop` |
| dependency manifest                   | `peploop/requirements.txt`, pinned to the versions in the working env, Python 3.13 |
| prod positions extract (source D)     | still `/Users/pudo/tmp/pep_wd_positions.csv`; not in the repo, decision pending |
| zavod and poliloom findings           | digested above; the QID lists live in `wd/shape.py` |
| `data/cache/` (5 GB), `data/discover/` | not moved; re-derivable |
| secrets                               | `ANTHROPIC_API_KEY` from `.envrc`; Wikidata credentials are read by `peploop/apply.py` from `~/.config/wikibase-cli/config.json`, so that file must exist on the VPS too; `PEPLOOP_DATABASE_URL` if the DSN is not `postgresql:///peploop` |

Postgres on the VPS needs the `pg_trgm` extension available; `schema.sql`
creates it. The `wb` CLI is used only by `wd/write.py` and is optional there.
