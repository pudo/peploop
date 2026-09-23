# Positions: resolving a free-text office to a QID

Round one extracts an office as the article names it — a title, sometimes a
jurisdiction string, dates, quotes. This is the half that turns that into a
Wikidata QID or refuses to. It is built and measured on three countries, and
the second turn has been run and measured on the pilot.

Two rules govern everything here. **Retrieval ranks, a model decides.** And
**nothing is filtered out of the table**: an abolished office is the right
answer for a tenure that ended before it, an item mistyped as an occupation is
worth offering *labelled* as one, and whether an office confers political
exposure is a question for a consumer. Every signal re-orders and is shown to
the model as a tag; none of them removes a row.

The numbers behind every claim here are in `research/peploop_positions.md`.
Things measured and rejected are in `positions_discarded.md` — read it before
proposing a change, because most of the obvious ideas have been tried.

## Tables

```
position       one row per Wikidata item a title may resolve to
position_name  (qid, lang, text, alias) — one row per name per language
type_edge      cached P31/P279 edges, so the class hierarchy is walked once
```

`position` carries the item (`label`, `description`, `country_qid` from `P17`,
`jurisdiction_qid` from `P1001`, `jurisdiction_text`, `body_qid` from `P361` or
`P2389`, `kinds`, `inception`, `abolished`, `replaces`, `replaced_by`,
`redirected_from`, `sources`, `loaded_at`), the ranking signals (`holders`,
`holders_at`, `holders_by_country`, `instance_count`, `subclass_count`,
`held_subclasses`, `not_office`, `diplomatic`, `scope_qualifier`), and the
search document (`search_text`, plus `tsv` generated from it and GIN indexed).

Every signal is nullable and filled by its own step, so one too expensive for a
large country is left null there rather than blocking the load. **Null means
uncounted and never zero** — the distinction is load-bearing in the ranking.

`position_name` is not indexed for search. It is the per-language source the
document is built from, and the answer to *which* name matched, looked up by
QID after the shortlist is cut.

A `candidate` table in a database seeded before this work is residue; nothing
reads or writes it.

## Discovery

Three lanes per country, each tagged in `sources`, run by
`load-positions --country <cc>`. `rigour` resolves the code to a QID.

- **`descent`** — `?pos p:P31/ps:P31/wdt:P279* wd:Q4164871` with a
  `P17`/`P1001` union. `p:P31/ps:P31` and not `wdt:`, because one preferred
  value hides the normal-rank ones and a live office then reads as not a
  position.
- **`usage`** — offices scoped to the state that someone is recorded in, or
  that name their own holder via `P1308`. This catches what the ontology
  mistyped: a country-generic mayoralty whose only `P31` is "type of position"
  is invisible to the descent and can still have a thousand holders.
- **`citizen`** — offices held by citizens of the state whose `P106` is
  politician, diplomat or judge. The only route to an office the state's own
  people hold that is scoped to no polity of theirs: a posting abroad, a seat
  in an international body, an item with no jurisdiction claim at all.

None is sufficient and the union is not redundant: **12% of the loaded table is
reached by the citizen lane alone.**

Two shapes matter and are not interchangeable. Discovery **pages** at
`DISCOVERY_PAGE = 2000` with a total ordering, because a large country's
response cannot otherwise be read to the end. And the citizen lane is **two
phases** — list the people with a cheap two-triple query, then ask for their
`P39` in `VALUES` chunks of 120 — because the single-query form is one join
large enough that no amount of paging rescues it.

## The document

One `search_text` per position: a de-duplicated bag of content tokens, not
prose. Into it go every label and alias in **every** language, plus every name
in every language of the `P1001`, `P17`, `P361`/`P2389`, `P1365` and `P1366`
targets, plus the **best label only** of each `P279` parent.

That last asymmetry is deliberate. The jurisdiction, the state, the body and
the office this one replaced are words an article genuinely uses for *this*
office. A class is not: a generic parent carries dozens of aliases across 300
languages, and pasting them onto every child makes the class outmatch the
office it is the class of.

Each token is stored twice, as itself and as its 6-character prefix
(`PREFIX = 6`). That is how inflection is handled — Postgres ships no Czech
stemmer, and `simple` is the only honest configuration for an index holding
302 languages.

## Search

`search(title, jurisdiction, country_qid, limit=15, pool=CANDIDATE_POOL)`.

The query is the title and the jurisdiction string concatenated, put through
the *same* `token_bag` as the document, OR-ed into a `to_tsquery`, and ranked
by `ts_rank(tsv, q, 0)` over the GIN index. With a de-duplicated bag every
lexeme has frequency 1, so that rank is exactly the count of matched query
terms — plain coverage, and no weighting scheme improves on it.

SQL returns `CANDIDATE_POOL = 400` rows; Python applies the signals and cuts to
15. **The cut must happen after the ranking**, not in the `LIMIT`: the text
score ties heavily, so a SQL-side cut prunes by exactly the criterion the
signals exist to overrule. Where the plateau falls is a property of the table,
not of the search — it was 200 on one country and is 400 on three, and it is
re-derived by running the curve.

`country_qid` scopes nothing. It is passed because the ranking needs to know
who is asking, and it is **not a filter** — see `positions_discarded.md`.

## Ranking

`SIGNALS = ("not_office", "holders", "class", "dates", "diplomatic")`, applied
as an additive adjustment to a base score normalised to 1.0:

```
holders             +0.30 × log10(1+n) / log10(1+1000)
unheld              -0.15
not_office          -0.50
abstract            -0.35
date_fit             0.00   ← measured destructive; the tag is still emitted
date_conflict       -0.30
inbound_diplomatic  -0.25
```

**A holder count is counted where the search is.** `holders_by_country` maps a
state QID to how many of that state's citizens hold the office, and the scope
rule is `local`: a missing key is *silence*, never the global count. A global
count scored as a local one is how a foreign lower-house seat with thousands of
holders reaches rank 1 in another country's queries.

Ten tags, each derived from a filled column and each shown to the model:

| tag | rule |
|---|---|
| `not-office` | a declared type in `NOT_AN_OFFICE`, and no position metaclass |
| `unheld` | nobody in the asking state holds it |
| `abstract` | class-like, and below `CONVENTION_FLOOR = 50` local holders |
| `generic-by-convention` | class-like, and at or above the floor |
| `abolished` | `abolished` is set |
| `date-fit` / `date-conflict` | the tenure's dates against the office's span |
| `diplomatic` / `inbound-diplomatic` | a mission, and whether it is scoped *to* the asking state |
| `foreign-scoped` | another state's office, reached only by the citizen lane |

Class-likeness is `instance_count > 0` or `held_subclasses >= 3`. The same
shape reads two ways and only a count of the state's own holders tells them
apart: an abstraction a handful of people were misfiled under, or the item the
community uses on purpose because it mints no item per place.

## The second turn

`reconcile.resolve_mention` runs it for one office mention: search, render,
ask, settle, record. One request per mention, never a batch, and never a
continuation of the extraction conversation — several decisions in one context
is how a pass standardises on whoever answered first.

The model sees the mention as extraction wrote it (title, jurisdiction string,
dates, quotes), **the whole article the quotes came from** when it is under
`ARTICLE_CAP = 20,000` characters (a line says so when it is not; the median
article is under 3,000), and a shortlist of 15 rendered one per line —
`QID | label | description | kind | part of | exists | holders | tags | used
with | matched` — under a frozen, hashed prompt (`prompts/reconcile.md`). The
prompt explains the body/seat distinction, every tag, and two conventions the
tags alone did not carry: a country-wide office with no subclasses is not a
class and shows `used with:` once the state's holders clear the convention
floor, and an officer of a named organisation is recorded on the generic
officer item with the organisation as a qualifier. Bodies are named, not
printed as QIDs.

It answers with a closed set: `same-office`, `renamed`, `generic-class`,
`body-not-seat`, `wrong-office`, `none`. Only the first two are matches.
`settle()` refuses a pick that was not on the shortlist. **The answer schema is
one fixed shape for every request**; it used to close `qid` over the offered
QIDs per request, which put the shortlist inside the cached prefix and made
every request write the prompt to cache and read nothing. An uncounted holder
count prints `uncounted`, never `0`.

Every verdict is a row in `resolution`, keyed by (extraction, mention index,
prompt hash, `RENDER_VERSION`). A mention answered under that key is never
asked again; a prompt edit or a rendering change re-asks. A row with a null
`qid` is the creation queue.

`python -m peploop.check_propose` pins the lane above -- both directions of the
endpoint aggregation, the two-language fold, the acting filter -- with no
network, no key and no database.

`python -m peploop.check_reconcile` pins the rendering (including the article
section and the cap), the fixed schema, `settle` on every verdict kind, and that
every tag the ranking can produce is explained in the prompt — so a new tag
cannot ship unexplained. It needs no network, no key and no tokens.
`scripts/reconcile_bench.py` measures the turn against the silver set, scoring
against `fixtures/cz_positions_verified.jsonl` where a disagreement has been
hand-read; the numbers are in `research/peploop_positions.md` §9.

## The test set

`scripts/position_fixture.py` pairs an extracted title to one of the person's
`P39` statements by date agreement, and writes
`peploop/fixtures/cz_positions.jsonl`. One pairing rule is in force: **two
titles in one language with the same dates are two offices, not one tenure
named twice.** Two further rules were implemented and measured harmful; they
survive as `--both-endpoints` and `--one-to-one` only so the ablation is
re-runnable.

`scripts/position_bench.py --country cz` reports four slices. The primary one
is **`vocab_overlap`** — rows whose title shares a token with its answer. Use
it for MRR and top-1 when comparing two orderings; do **not** quote its recall,
which is flattered by sharing a token-overlap assumption with the retriever.
`--signals none` is the text order alone.

`fixtures/cz_positions_verified.jsonl` holds hand-read truth for rows where a
verdict and the silver label disagreed; `reconcile_bench.py` scores against it
where present. Of 50 read so far the silver label was wrong in 35, so **silver
agreement is a floor**: the 150-row run reads 58.7% against silver and 77.3%
against truth, with no confirmed wrong match (`research/peploop_positions.md`
§9).

**About 22% of gold rows are mispaired and dates cannot fix it.** Correlated
offices start on the same day — a deputy elected in October also becomes deputy
chair of their parliamentary club that October — so the club post inherits the
chamber seat as its label. Strict date agreement makes this *worse*, not
better, because a real tenure often disagrees at the end (an article dates it
by the day the holder left, Wikidata by the day the successor was sworn in)
while an artefact agrees perfectly. What remains mispaired is mostly an office
with no `P39` anywhere on the person, which no re-pairing rule can reach.

## Running it

```
python -m peploop.cli load-positions --country cz     # discovery, fetch, upsert
python -m peploop.cli position-signals --country cz   # the ranking columns
python -m peploop.cli position-signals --country cz --local-holders   # just that state's count
python -m peploop.cli position-stats                  # what the table holds
python -m peploop.cli reconcile --country cz          # the second turn, over a run
python scripts/position_fixture.py                    # rebuild the silver set
python scripts/position_bench.py --country cz --signals all
python -m peploop.check_neutral                       # no country token in peploop/*.py
python -m peploop.check_reconcile                     # the second turn, offline
python -m peploop.check_propose                       # the P39 lane, offline
python scripts/reconcile_bench.py --country cz --limit 150   # the second turn, live
```

`--local-holders` is the one to reach for on an *n*th country. `fill_counts`
re-asks all five signals over the whole table -- 268 chunks of query service
per signal -- and four of them are whole-corpus counts a new country does not
change the answer to. The fifth, `holders_by_country`, is keyed by the state
that ran it, so a new country has no key anywhere and every row reads
`uncounted` until this fills it.

`VACUUM (ANALYZE) position` after a signal fill: five whole-table updates
triple the heap and grow the GIN index by a third with no new documents.

## From a verdict to a proposal

`propose` reads the verdicts back (`propose.placements`) and writes a `P39` for
each mention whose `qid` is set -- which is exactly the set `settle()` already
passed, so nothing is judged twice. The statement carries `P580`/`P582` from the
tenure, the quote and the article, and `proposal.resolution_id` pointing back at
the verdict, which is what the review screen reads to show the office as the
article named it and the shortlist the model was offered.

Four rules decide the rest:

- **A tenure the item already records for the same office is set aside.** Two
  spells of one office that overlap are one appointment written down twice,
  dated a few days apart: Wikidata ends a ministry on 2022-06-01 and the
  article on 2022-04-20, a convocation opens on 2018-06-03 and the member was
  sworn in on the 22nd. Such a proposal is `overlapping`, which is inert -- in
  neither `review.REVIEWABLE` nor `render.WRITABLE` -- and carries the spell it
  clashed with in `qualifiers._reason`. Nothing is forfeited by it: `apply`
  sees the office value already on the item, returns `exists` and drops the
  dates (see *What is not done* below), so the only `P39` that can reach
  Wikidata at all is one for an office the item holds no statement for.
  Downstream the cost is worse than nothing -- OpenSanctions keys an Occupancy
  on `(person, position, start, end)` and merges only on an *identical* start,
  so a near-miss is a permanent duplicate. Measured on 1,253 Slovenian `P39`
  rows: 231 set aside, reviewable rows 1,206 -> 999, people to review 830 ->
  734. Two things the rule deliberately does not do. It judges *only* the same
  office QID -- a spell overlapping a *different* office is a minister keeping
  their parliamentary seat, and 106 of these rows are exactly that. And a
  recorded statement carrying **no dates at all** blocks nothing, because it is
  the thing the proposal exists to sharpen; those 65 rows stay `refine`. The
  order is load-bearing: the clash is asked first, because whether the tenure
  is already recorded decides whether it belongs on the item at all, and only
  what survives it is asked what kind of tenure it was.
- **The same spell in two languages is one row.** A person's `sl` and `pl`
  articles both name the tenure and reconciliation places both on one item;
  `tenure_key` folds them into one proposal with two sources, because a
  reviewer asked the same question twice is a reviewer being wasted.
- **A spell no recorded statement covers is `new`, whatever else the item
  records for that office.** An earlier term beside a recorded later one is
  coverage, not a dispute. It used to read `conflict` -- `tenure_status`
  returned `new` only when the item held no statement for the office at all --
  and 20 Slovenian rows were being shown as contradictions on that basis.
  `exists` and `conflict` have left the `P39` lane entirely; both only ever
  meant a statement the item already carries.
- **An acting tenure is `filtered`.** Wikidata says "acting" with a qualifier
  this pipeline does not write, and a `P39` that omits it asserts more than the
  article did. Its `_reason` is `acting`, so its volume stays countable
  alongside every other rule that decided something.

`render` refuses `P39` outright, whatever its status. QuickStatements matches a
line on subject, property and *value* and folds the qualifiers into whatever
statement it finds, so two terms of one office arrive as one statement carrying
both starts and both ends. Positions go out through `apply`, which creates and
never merges.

## What is not done

- **`apply` cannot write a `refine`.** A P39 the item already records, wanting
  the end date the article supplies, is a *merge* into an existing statement,
  and `apply` creates and never merges: its router sees the office value
  already there, returns `exists`, and the date is dropped. Measured on
  `Q101002571`, whose National Assembly statement has a start and no end --
  `apply --qid Q101002571` reports "nothing to write". A `new` tenure is
  unaffected. Writing the merge is write-path work and the wrong shape gets
  duplicates, so the proposals stand and `apply` skips them for now. This gap
  is also what makes `overlapping` free: a proposal that could never be written
  costs a reviewer's attention and buys nothing. Closing the gap is what would
  make those rows worth showing again.
- **The creation queue is a count, not a queue.** A verdict with a null `qid`
  is an office that was named, evidenced and could not be placed; nothing yet
  collects those with their evidence for minting. On a country whose offices
  Wikidata mostly lacks this is the larger half of the output.
- **A large country's ranking signals are null on purpose.** Filling them is
  600 query-service requests and 6–11 hours, and a null foreign count scores
  *better* than a filled one, so this is not a cost compromise.
- **The open question.** Loading a third, much larger country cost 1.5 points
  of aggregate recall and 4.8 of top-1. Only 0.3 of the recall was the pool
  cut, now spent by raising the pool. The rest is a foreign office genuinely
  outranking the answer *inside* the fifteen, identical at every pool size, and
  the signal that would settle it is null on exactly those rows. The next
  measurement is whether a cheap country-match signal that needs no holder
  count recovers it — not a bigger pool, and not the filter already rejected.
