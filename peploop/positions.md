# Positions: resolving a free-text office to a QID

Extraction gives an office as the article names it — a title, sometimes a
jurisdiction string, dates, quotes. This is the half that turns that into a
Wikidata QID or refuses to.

Two rules govern everything here. **Retrieval ranks, a model decides.** And
**nothing is filtered out of the table**: an abolished office is the right
answer for a tenure that ended before it, an item mistyped as an occupation is
worth offering *labelled* as one, and whether an office confers political
exposure is a question for a consumer. Every signal re-orders and is shown to
the model as a tag; none of them removes a row.

The numbers behind every claim here are in `docs/research/peploop_positions.md`.
Things measured and rejected are in `docs/history.md` (Retrieval) — read it before
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

Five lanes per country, each tagged in `sources`, run by
`load-positions --country <cc>`. `rigour` resolves the code to a QID.

- **`descent`** — `?pos p:P31/ps:P31/wdt:P279* wd:Q4164871` with a
  `P17`/`P1001` union. `p:P31/ps:P31` and not `wdt:`, because one preferred
  value hides the normal-rank ones and a live office then reads as not a
  position.
- **`usage`** — offices scoped to the state that someone is recorded in, or
  that name their own holder via `P1308`. This catches what the ontology
  mistyped: a country-generic mayoralty whose only `P31` is "type of position"
  is invisible to the descent and can still have a thousand holders.
- **`subdivision`** — offices whose `P1001` is one of the state's
  first-level units (its unended `P150`, and the items typed a first-level
  subdivision with the state as `P17`: each list alone misses some). A
  governorship or provincial cabinet seat often carries no `P17`, so the two
  lanes above, keyed on the state, never reach it. Types are closed after
  the query, since a `P279*` joined to a large province's `P1001` times out.
- **`citizen`** — offices held by citizens of the state whose `P106` is
  politician, diplomat or judge. The only route to an office the state's own
  people hold that is scoped to no polity of theirs: a posting abroad, a seat
  in an international body, an item with no jurisdiction claim at all.
- **`outbound`** — the state's own missions abroad, asked by *sender*: the
  members of its "ambassador of <state>" class (`P279 Q29645880`, `P17` =
  the state), plus the items it operates (`P137`) whose type closure reaches
  `Q121998` ambassador. A bilateral post is scoped `P17` = the *receiver*, so
  descent and usage never reach it, and most are unheld, so citizen doesn't
  either: 27 of Belarus's 84 were in no lane. The operator channel is
  filtered after the query because `P137` also names the state as operator
  of its helicopters.

None is sufficient and the union is not redundant: **12% of the loaded table is
reached by the citizen lane alone.**

**A mission's direction is its sender, not its scope.** `P17` names the
receiver on 86% of bilateral posts and the *sender* on 12%, so "scoped to the
asking state" calls one post in eight an inbound embassy when it is the state's
own. Every diplomatic row carries `sender_qid` — its "ambassador of <state>"
class's `P17`, else its own `P137`, never its `P17` — and `tags_for` calls a
row whose sender is the asking state `diplomatic`, never `inbound-diplomatic`
or `foreign-scoped`. `country_qid` stays the item's `P17`: the inbound test
for the *receiving* state and every per-state listing read it as the scope.

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
who is asking, and it is **not a filter** — see `docs/history.md` (Retrieval).

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
one fixed shape for every request**: a per-request schema would sit inside the
cached prefix and defeat the prompt cache. An uncounted holder
count prints `uncounted`, never `0`.

Every verdict is a row in `resolution`, keyed by (extraction, mention index,
prompt hash, `RENDER_VERSION`, `reopened_for`). A mention answered under that
key is never asked again; a prompt edit or a rendering change re-asks. A row
with a null `qid` is the raw input of the creation queue (below);
`reopened_for` is empty except on a verdict re-asked because the item it was
missing has since been minted, which sits beside the original and, being
newer, is the one `propose` reads.

`python -m peploop.check_propose` pins the lane above -- both directions of the
endpoint aggregation, the two-language fold, the acting filter -- with no
network, no key and no database.

`python -m peploop.check_reconcile` pins the rendering (including the article
section and the cap), the fixed schema, `settle` on every verdict kind, and that
every tag the ranking can produce is explained in the prompt — so a new tag
cannot ship unexplained. It needs no network, no key and no tokens.
`peploop/bench/reconcile_bench.py` measures the turn against the silver set, scoring
against `fixtures/cz_positions_verified.jsonl` where a disagreement has been
hand-read; the numbers are in `docs/research/peploop_positions.md` §9.

## The test set

`peploop/bench/position_fixture.py` pairs an extracted title to one of the person's
`P39` statements by date agreement, and writes
`peploop/fixtures/cz_positions.jsonl`. One pairing rule is in force: **two
titles in one language with the same dates are two offices, not one tenure
named twice.** Two further rules were implemented and measured harmful; they
survive as `--both-endpoints` and `--one-to-one` only so the ablation is
re-runnable.

`peploop/bench/position_bench.py --country cz` reports four slices. The primary one
is **`vocab_overlap`** — rows whose title shares a token with its answer. Use
it for MRR and top-1 when comparing two orderings; do **not** quote its recall,
which is flattered by sharing a token-overlap assumption with the retriever.
`--signals none` is the text order alone.

`fixtures/cz_positions_verified.jsonl` holds hand-read truth for rows where a
verdict and the silver label disagreed; `reconcile_bench.py` scores against it
where present. Of 50 read so far the silver label was wrong in 35, so **silver
agreement is a floor**: the 150-row run reads 58.7% against silver and 77.3%
against truth, with no confirmed wrong match (`docs/research/peploop_positions.md`
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
python -m peploop.cli report --country cz positions  # what the table holds
python -m peploop.cli reconcile --country cz          # the ranking columns, then the second turn, over a run
python peploop/bench/position_fixture.py                    # rebuild the silver set
python peploop/bench/position_bench.py --country cz --signals all
python -m peploop.check_neutral                       # no country token in peploop/*.py
python -m peploop.check_reconcile                     # the second turn, offline
python -m peploop.check_propose                       # the P39 lane, offline
python peploop/bench/reconcile_bench.py --country cz --limit 150   # the second turn, live
```

`reconcile` fills the signals only for rows that have none, and the state's
own holder count (`holders_by_country`, keyed by the state that ran it) for
rows without one; a recount of rows already counted is `positions.fill_counts`
with no `qids`, called by hand -- 268 query-service chunks per signal.

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
  no status the policy decides -- and carries the spell it
  clashed with in `qualifiers._reason`. Writing it would cost worse than
  nothing downstream: OpenSanctions keys an Occupancy on
  `(person, position, start, end)` and merges only on an *identical* start,
  so a near-miss is a permanent duplicate. Two things the rule deliberately
  does not do. It judges *only* the same office QID -- a spell overlapping a
  *different* office is a minister keeping their parliamentary seat. And a
  recorded statement carrying **no dates at all** blocks nothing, because it is
  the thing the proposal exists to sharpen; such rows stay `refine`, and the
  plan merges the dates into that statement. The order is load-bearing: the clash is asked first, because whether the tenure
  is already recorded decides whether it belongs on the item at all, and only
  what survives it is asked what kind of tenure it was.
- **The same spell in two languages is one row.** A person's `sl` and `pl`
  articles both name the tenure and reconciliation places both on one item;
  `tenure_key` folds them into one proposal with two sources, because a
  reviewer asked the same question twice is a reviewer being wasted.
- **A spell no recorded statement covers is `new`, whatever else the item
  records for that office.** An earlier term beside a recorded later one is
  coverage, not a dispute. `exists` and `conflict` do not occur in the `P39`
  lane; both only ever mean a statement the item already carries.
- **An acting tenure is `filtered`.** Wikidata says "acting" with a qualifier
  this pipeline does not write, and a `P39` that omits it asserts more than the
  article did. Its `_reason` is `acting`, so its volume stays countable
  alongside every other rule that decided something.

A further term goes out as a `+` line, which QuickStatements always creates
as a statement of its own; dates for the one undated statement of an office go
out as a plain line merged into it (`design.md` §7).

## The creation queue

A verdict with a null `qid` is an office that was named, evidenced and could
not be placed. On a country whose offices Wikidata mostly lacks this is the
larger half of the output, and the mint stage (`mint.py`, `mint_write.py`,
the shape rules in `offices.py`) turns it into items, so those holders' `P39`s
have somewhere to go.

- **Two sources, one queue.** `mint.unplaced` reads every miss of the
  country's people (not those the scope gate discarded) and pools them by
  folded title and jurisdiction; `census/<cc>.yml` adds the offices the state
  has whether or not anyone's article named them, expanded per subdivision
  over a live `P150` read where an office exists in each. A census office is
  a prompt for the offices nobody's article names, not a second channel of
  evidence: one no mention attests is skipped as `census/unattested`, so the
  funnel says how much of the census the seeds reached. A `per: units` entry
  is a third source (`mint_units`): one candidate per unit of a level that
  lacks the office, attested by the head the unit's own `P6` or article
  names, and for the EU's ≥50k units read from `amlr.units`.
- **Current is read conservatively.** An acting tenure or a dead holder never
  counts, an end counts only while its earliest reading is still ahead, an
  open tenure only if it began within twelve years, an undated one never.
- **What cannot become current costs nothing.** A group with no current holder
  that shares no place or subject stem with one that has is dropped before the
  first request. Most of a queue is single historical mentions, and asking
  about them is what pushed a request past its output budget.
- **The floor runs after clustering.** One office is many spellings -- a
  gendered form, the same title in two languages, with and without its place
  -- so categorize sees every surviving group, single-person ones included, and
  the floor reads the pieces it merged together: one distinct person attested,
  and a current holder among them, for every office. A floor of two people
  would remove the party, state-company and agency heads screening needs most;
  verify and the guard are the gate on whether an office is real. Neither
  model can override the floor.
- **Two models and a veto.** Categorize (`prompts/mint_categorize.md`, the
  reconciler's model) clusters the groups into offices in chunks ordered so
  the pieces of one office share a request, gives each an institution class
  and an archetype, and drafts labels, body, jurisdiction and predecessor from
  the QIDs it was shown -- an off-list QID is removed after the fact, and every
  group gets exactly one answer, the ones no office took landing in
  `office_unassigned` with a reason. Verify (`prompts/mint_verify.md`, the
  person verifier's model, a different family on purpose) reads one office per
  request: the attestations in full, the live duplicate hits, the state's
  index and its sibling tallies, the draft with every QID labelled. It answers
  from a closed set (`mint`, `exists`, `not-an-office`, `not-current`,
  `not-distinct`, `generic-convention`, `unclear`) and agrees with the shape or
  corrects it. Then `offices.guard` vetoes mechanically: labels in the state's
  languages, no QID in any text, a current holder, a live duplicate search per
  label and alias and against the run's own candidates, a body that resolves,
  is not a position and shares a content word with the office, a jurisdiction
  inside the state, the shape, no bilateral post. The shape itself is fixed per
  archetype and follows the state's own siblings, falling back to `Q294414`.
  Siblings are the state's offices and those of its current subdivisions,
  less any that is dissolved (`P576`), typed historical, or last held more
  than 30 years ago, so a colonial predecessor does not set a new office's
  type. A body two or more siblings already use is
  measured rather than drafted, so it skips the shared-word check ("Council
  of Ministers" shares no content word with "Minister of X").
- **A disagreement is a skip, never a review row.** `mint.RULES` is ordered
  like `policy.py`'s and writes one of three statuses: `found` (a live
  duplicate, or the item a pass named -- which counts only when it is an
  office of the state or one of its subdivisions, not a class and not a
  posting; ambassadorships are skipped before it is read), `guarded` (categorize, verify at high
  confidence and the guard all agree), or `skipped` under the rule that
  decided it -- `verify:not-current`, `disagree/shape:parent_qid`,
  `guard:body-word/…`. The corrections a verifier proposed are kept on the
  row, so a disagreement class an audit shows to be sound can become a rule
  that accepts it; nothing is relaxed per row. The mint report's skip export
  (`report <cc> mint`) is the list for a human, the way `conflict` rows are
  for the person loop.
- **Feed reopens only what was attested.** Once an item is created or found,
  `feed` loads it into `position` with its holder counts left null, so it
  reads `uncounted` rather than unheld; then, for each mention the candidate
  was clustered from, asks `retrievable` whether the shortlist would now offer
  it -- a mention the search cannot surface would buy the same refusal again --
  and `reopen`s only those, under the same prompt and rendering, before
  re-proposing their people. A mention that merely looks like the office is
  never re-asked on the strength of the new item.

## What is not done

- **A large country's ranking signals are null on purpose.** Filling them is
  600 query-service requests and 6–11 hours, and a null foreign count scores
  *better* than a filled one, so this is not a cost compromise.
- **The open question.** Adding a much larger country to the table cost a
  small one 1.5 points of aggregate recall and 4.8 of top-1. Only 0.3 of the recall was the pool
  cut, now spent by raising the pool. The rest is a foreign office genuinely
  outranking the answer *inside* the fifteen, identical at every pool size, and
  the signal that would settle it is null on exactly those rows. The next
  measurement is whether a cheap country-match signal that needs no holder
  count recovers it — not a bigger pool, and not the filter already rejected.
