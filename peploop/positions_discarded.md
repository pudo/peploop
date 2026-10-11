# Positions: ideas measured and rejected

Read this before changing the resolver. Most of the obvious improvements have
been tried and cost something; each entry is the rule that stands, the number
that decided it, and nothing about how it was found. The design is in
`positions.md`, the full measurements in `docs/research/peploop_positions.md`.

An entry here is not a law. It is a measurement, and a measurement can be
overturned by a better one — but by that, and not by an argument.

## Retrieval

**A country filter.** Scoping candidates to the run's country hides 41% of the
loaded table — every globally abstract office the community records with a
scoping qualifier, and every ministry of a predecessor state whose name the
articles still use. Costs **23.7 points of macro recall**. The country is a
ranking input, never a filter.

**IDF or any term weighting.** Worth **+0.02 MRR** over plain coverage, and it
*loses* 0.4 points of aggregate recall. `ts_rank(tsv, q, 0)` over a
de-duplicated token bag is exactly coverage, and reproduces a hand-rolled
IDF-weighted index to the fourth decimal. There is no search engine to build
here.

**`pg_trgm` over the document.** `similarity()` scores **23.3%** aggregate
recall at 137 ms per query; `word_similarity()` 75.6% at 225 ms. Against 82.7%
at 1.8 ms for `ts_rank`. Trigram is the wrong tool for a long document; it was
the right one when the unit was a single name, and that is why the indexes were
dropped rather than kept "just in case".

**`ts_rank` length normalization.** Flags 1 and 16 trade +1.2 macro for
**−8.6 points of top-1**; flags 2 and 8 are catastrophic (aggregate 65%);
1|8 together drop top-1 to 0.4%. Only flags 0, 4 and 32 are equivalent, and 0
is used.

**A shortlist longer than 15.** Going from k=15 to k=200 recovers 44 gold rows
and **not one of them has a defensible label** — every row whose title shares
distinctive vocabulary with its answer is already inside the top 15. A longer
list costs prompt tokens and hands the model more plausible neighbours.

**Cutting the pool in SQL.** The `LIMIT` must not do the ranking's job: the
text score ties heavily, so a SQL-side cut prunes by the criterion the signals
exist to overrule. Costs 2.8 points of aggregate recall. Note the corollary —
depth is worth **nothing at all** without a re-ranker downstream: `--signals
none` is identical to four decimals at every pool size from 15 to 2,000.

## What goes in the document

**Descriptions, in any language.** English and `mul` are neutral; all languages
cost **1.5 macro points and 1.7 of top-1**. "Czech politician" is in hundreds
of documents and matches nearly any Czech query. Descriptions still belong on
the *candidate line the model reads* — they disambiguate for a reader without
helping retrieval.

**Wikipedia sitelink titles.** Only 297 of 2,292 are not already a label or
alias, and adding them changes the bench by **exactly zero** on every slice.

**Monolingual name properties** (`P1448`, `P1813`, `P2561`, `P1705`). 28
statements across 343 items. Not worth the fetch.

**Every item-valued statement target.** All 78 properties, 1,377 referenced
items, 30 s of extra fetches for one small country: macro flat, **MRR −0.03**,
document 2.4× larger. Only `P1365` appeared to help, and all 120 of its
improved rows were a single office that is 47% of the gold set. The six
properties in `REFERENCED_PROPS` are the ones that pay.

**`P1889` "different from", ever.** It names precisely the items this one is
confusable with. Indexing it is wrong on principle whatever it measures.

**Every alias of a `P279` parent.** A generic class carries dozens per language;
pasting them onto each child costs **3.9 macro points** and makes the index a
fifth larger. A kind contributes its one best label.

## Ranking

**The date-fit boost.** The design said an abolished office should be *boosted*
for a tenure that ended before it. An inception preceding a tenure is true of
nearly every old office, so it is an "is old" bonus handed to wrong candidates
as freely as right ones: **−0.08 MRR and −16 points of top-1.** Ships at
`date_fit: 0.0`, with the tag still emitted because the model is owed the
observation. The *conflict penalty* half is kept.

**A global holder count.** Correct only while one country is loaded, because
then the biggest counts are that country's. With two, a foreign lower-house
seat with 4,694 holders and no local ones reaches rank 1 on 74 of 746 queries.
Counted locally it is worth **+0.099 MRR and 13 points of top-1**.

**Filling holder counts for a large country.** 600 query-service requests,
6–11 hours. And a null foreign count *scores better* than a filled one, so
this is a correctness argument and not a budget one.

## The second turn

**A per-request schema closing `qid` over the shortlist.** The structured-output
schema sits inside the cached prefix, so a `Literal` over the offered QIDs made
every request write ~3.5k tokens of cache and read **0**; one fixed shape reads
them back from the second request on. `settle` refuses an off-list QID either
way, so the schema was enforcing nothing the gate did not.

**Quotes without the article.** With only the copied sentences in view the model
refused offices whose settling sentence was elsewhere in the article. The whole
article under a 20,000-character cap is under ten lines of code; a quote window
around each hit is not, and `check_quotes` shows some quotes are not verbatim.

## The test set

**Requiring both tenure endpoints to agree.** Strict date agreement is
*evidence against* a pair being right: 64.6% of both-endpoint pairs share
vocabulary with their answer against 74.0% of pairs with only one endpoint to
compare. An article dates a tenure by the day the holder left and Wikidata by
the day the successor was sworn in.

**One statement, one tenure.** Costs 5–8 points of vocabulary agreement and
halves the set. Both rules survive behind `--both-endpoints` and `--one-to-one`
so the ablation re-runs; neither is on.

**A date tolerance chosen from a grid.** The one-year variant is the only
configuration that beats the shipped set on both readings. It stays unadopted:
picking a tolerance from {0,1,2} by which value raises the acceptance metric is
tuning toward the number.

**Cleaning the fixture with text overlap.** A silver set selected by token
overlap cannot measure a token-based retriever — recall goes to ~100% by
construction and measures nothing. Vocabulary agreement is recorded per row as
a diagnostic and never used to accept or reject a pair.

## Structure

**Source D, the production `wd_peps` extract.** `is_pep` is `TRUE` on all
189,089 rows, 34,951 are soft-deleted, and one small country has 234 rows of
English-normalised captions. No signal. More broadly: peploop carries no
`is_pep`, no topics, no 1990 abolition cutoff and no municipal-country list —
it maps narrative to positions of any kind, and PEP classification is a
consumer's question.

**A generalised `lookup_item` table with a `kind` column.** Places have a
parent chain rather than a jurisdiction and people have neither; a shared table
becomes nullable columns meaning different things per kind and a ranker with
nothing in common. Birthplace gets its own table when it arrives.

**Single-query citizen discovery.** One join over "positions held by citizens
with a political occupation" failed four times on a large country, including
at page 1, where the wrapper's ordering makes the first page more work than the
unpaged query. Two bounded phases never failed once across ~700 requests.

**A dump pipeline.** Not rejected on measurement — SPARQL reaches ~16,000 items
with paging and a two-phase citizen lane, so it has not been needed. Revisit if
a country's load stops fitting in a night, not before.
