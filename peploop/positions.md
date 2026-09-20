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

- The table is Postgres, `pg_trgm` on label and jurisdiction text, a
  `simple`-configuration `tsvector` over `search_text`. No search service until
  birthplace forces the question (`design.md`, *Not in round 1*).
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

The `candidate` row already has label, aliases (all languages), description,
`country_qid`, `jurisdiction_qid`, `jurisdiction_text`, `search_text`. What
the search must survive:

- **Cross-language queries.** The article says "primátor Brna"; the item's
  labels include `cs` "primátor Brna" and `en` "Mayor of Brno". Aliases in all
  languages in `search_text` covers this when the term exists in the article's
  language; when it does not, the jurisdiction string is the bridge ("Brno" is
  the same in every language). That is why `jurisdiction_text` is indexed
  separately and why turn one asks for a jurisdiction next to the title.
- **Inflection and word order.** `simple` tsvector does no stemming, so
  "ministr obrany" and "ministra obrany" are different tokens. Trigram
  similarity covers this; the FTS covers exact-token queries. Both are needed,
  and the score should combine them.
- **The parent trap.** `{mayor} ⊆ {mayor, brno}`: the class label is a subset
  of the query, and a naive containment or IDF score prefers it. The rule from
  `wd/rerank.py` applies: containment is scored one way, the candidate must
  cover the query, never the reverse.
- **Not-a-position rows.** If a row typed as a position is really an
  occupation or a rank, it should still be *in* the table (the article may
  well name it, and telling the model "this is an occupation, not an office"
  prevents a wrong P39), but flagged.

Storage questions still open are whether labels should be one row per
(qid, lang) so search can prefer the article's language, and whether
`description` should enter `search_text` (it disambiguates, but it also adds
noise: every Czech mayor's description says "Czech politician").

## 3. Ranking: which candidates go first, and which last

The shortlist is drawn by search score; the ranking below re-orders it before
the model sees it, and each signal that moved a row is *shown* to the model as
a tag, not applied silently.

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
  Already in the design as "filter to the run's country first, global
  fallback"; a filter is the strongest possible ranking and probably too
  strong at the borders (a Czechoslovak minister for a Czech person).
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
  table with 200 Czech offices, and whether `country_qid` as a first-pass
  filter is enough to keep it flat. Increment 6.

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
  loaded_at         TIMESTAMPTZ

position_name
  qid   TEXT REFERENCES position, lang TEXT, text TEXT, alias BOOLEAN
  PRIMARY KEY (qid, lang, text)
  GIN (text gin_trgm_ops); GIN to_tsvector('simple', text)
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

`peploop/positions.py:search(title, jurisdiction, lang, country_qid, k=15)`:
trigram similarity over `position_name.text` and over `jurisdiction_text`,
plus `simple` full-text on the title's tokens, combined into one score;
`covers` computed as in `wd/positions.py:Hit` and used as the first sort key;
the run's country first, global fallback. `scripts/position_bench.py` runs
every fixture row and reports **recall@15 and MRR on gold rows**, recall@15
on weak rows (any of the person's P39 in the top 15), and the share of rows
with no hit at all, broken down by `lang` and by whether a jurisdiction string
was present. This is the number the rest of the plan moves; it is measured
first with no ranking signal at all so that every later signal has a delta.

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
