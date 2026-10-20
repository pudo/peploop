# peploop: Wikipedia → Wikidata enrichment loop

Wikidata is the closest thing there is to a public, structured record of who
holds political office, and it is thin below the head-of-state tier:
legislators without birth dates, ministers without a `P39`, judges and central
bankers with an article in one language and no office item at all. Wikipedia,
across its languages, holds most of the missing facts as prose and infoboxes.

peploop reads a politician's Wikipedia articles, asks a model one structured
question about them, checks each answer against what Wikidata already says,
decides it by rule (and by a second model where the rule is unsure), and
writes what passes. It creates the office items nobody has made yet. It is
built for Wikidata being right; OpenSanctions reads the result through its own
crawlers, and whether it emits an item is never a reason to shape a claim.

Its one dependency from the OpenSanctions stack is `rigour`, for everything
about countries: name lookup, QID lookup, and the languages of a territory.

## Principles

- **One person, one request.** The unit of work is a Wikidata item. Everything
  needed to process it is fetched, prompted, and stored per item. No campaign,
  no country-wide lane, no verdict ledger spanning runs.
- **Deterministic code frames the question; the model answers it.** Scripts
  fetch, trim, and format. The model reads and extracts. Code never guesses at
  fuzzy content, and the model never fetches or writes.
- **Frozen system prompt, injected material.** The system prompt describes the
  whole game once: what a proposal is, which properties exist, date and name
  conventions, how to cite, when to say nothing. It carries `cache_control` and
  is never interpolated. Per-person material (existing Wikidata state, article
  texts) goes in the user message, after the cached prefix.
- **Postgres is the only state.** HTTP cache, seed queue, article texts,
  extraction results, proposals. One database, one schema, `psql` is the
  inspection tool. No `data/` directory of JSONL ledgers.
- **Every proposal carries its evidence.** A verbatim quote, the article URL
  and the revision it came from, the language. A proposal without a quote is
  discarded before it is stored.
- **Add-only, never overwrite.** A proposal that matches an existing Wikidata
  claim is stored as `status=exists` and goes no further. A proposal that
  contradicts one is stored as `status=conflict` for a human, never as an edit.
- **Rules decide; review measures.** Every proposal is decided by the policy
  and the verifier. A human samples proposals in `review` and records why one
  is wrong; a class of wrong rows becomes a rule. A human veto after the fact
  is `audit`, and it is durable. No stage waits for a human.
- **Extract the whole shape, propose what can be placed.** Positions and
  birthplaces are extracted as free text and proposed only once
  reconciliation gives them a QID. Positions are; birthplace is not started.

## The loop

```
seed ─► fetch ─► extract ─► reconcile ─► mint ─► propose (+ policy) ─► verify ─► send
```

`mint` is the one stage whose unit is not a person: it works a country's
offices, and feeds what it creates back into the per-person stages around it.

Each stage is a function over one QID; a driver runs them under a thread pool
with a per-host rate limiter. Stages are idempotent: re-running a QID re-reads
the cache and upserts its proposals.

### 1. Seed

Input: a YAML file of categories for one country, `peploop/seeds/<cc>.yml`, each
entry `category`, `lang`, and an optional `depth` (default 1). Entries are taken from
OpenSanctions' `wd_categories.yml`, whose dozens of categories per country
transfer by keeping `category`, renaming `language` to `lang` and dropping
`country`, `topic` and `position`. Many narrow categories at shallow depth are
preferred to one wide category at depth 3: each PetScan request stays small,
and the category that admitted a person is recorded, so a wrong inclusion can
be traced to its category and that category removed. PetScan resolves the category
tree to (page title, QID) pairs; we drop anything without a QID and enforce
`P31=Q5` ourselves after the fetch step, because PetScan's Q5 filter lets
category items through. PetScan reports failure as HTTP 200 with valid JSON
(`{"error": "Pool::get_conn timed out…"}`), so a body carrying an `error` key
or no `*` key has its cache row dropped and raises, rather than standing in for
the category for a week. Its rows also include namespace-14 category pages (27 of
the en category's 114, 104 of the 6,397 for `Čeští politici`): the seed keeps
`namespace == 0` and the fetch step still enforces `P31=Q5`.

Output: one row per person in `person` (`qid`, `status=queued`) and one row per
(person, category) in `membership`. `person` is unique on QID, and extraction is
keyed on QID, prompt hash and article set, so a person found through six
categories is fetched once and prompted once. Adding categories to the file
never costs a re-extraction of anyone already seen.

The seed is deliberately the only country-shaped thing in peploop. The
country is metadata on the run, not a scope the pipeline reasons about.

### 2. Fetch

For one QID:

- **Wikidata item** via `wbgetentities` (labels, aliases, descriptions,
  sitelinks, claims), stored in its own `item` table with `lastrevid`, not in
  the generic HTTP cache. It is state, and state is invalidated by revision,
  not by age. See *Caching and invalidation* below.
- **Wikipedia articles**: every sitelink, fetched as Parsoid HTML from the
  REST API (`/page/html/{title}`), which is stable markup with the infobox and
  section structure intact. The endpoint follows redirects, so a sitelink
  that has become one comes back as another page; when that page belongs to
  another item it is dropped (a politician's title measured redirecting to
  his wife's biography), and when it is the same person under a moved title
  it is kept. Reduced to plain text by a small function that
  keeps the infobox as `key: value` lines, keeps headings, drops navboxes,
  references, tables of succession, and hatnotes. Cached in `article` with the
  revision id, which comes from the response's `etag`
  (`W/"<rev>/<uuid>/view/html"`) and falls back to `/revision/(\d+)` in the root
  element's `about` attribute, a URI through a localized special page;
  `mw:pageId` is the page id and `dc:replaces` the *previous* revision, so
  neither is usable. Infobox cells are text-node joined with spaces, and only
  inside the infobox, where the parts stack in nested spans with no whitespace
  between them; navbox and hatnote classes are per-wiki (`navileiste`,
  `klappleiste`, `succession-box`), so the drop list matches class fragments.
- **Ordering and budget**: articles are ordered English first where it exists,
  then the country's languages (the seed language of the category that found
  the person, then the languages of their `P27` countries from `rigour`'s
  territory data), then the rest by length descending. The English article and
  the first country-language article are always sent, whatever they cost: they
  are the two the extraction is worth doing on at all. The rest are taken
  strictly in that order and packing stops at the first article that does not
  fit in the budget, rather than skipping ahead to a shorter one. The budget is
  60k tokens, measured by a character heuristic of two characters per token
  (Czech and Slovak run about that), exact via `count_tokens` when tuning. An
  article that is not sent is dropped whole, never truncated, and the drop is
  recorded on the `extraction` row.

#### Caching and invalidation

Three kinds of fetched data, three rules:

| data | table | valid while | refreshed by |
|---|---|---|---|
| Wikidata item | `item` | `fetched_at` under 7 days | `fetch --qid`, and always by `send`'s pre-flight |
| Wikipedia article | `article` | `fetched_at` under 30 days | `fetch --qid` |
| everything else (PetScan, SPARQL, search) | `http_cache` | 7 days | age only |

The item rule is the one that matters. `wbgetentities` is what we compare
proposals against, and it is also what our own eventual writes change, so an
age-based cache there would let a statement we just wrote be proposed again.
So nothing that writes trusts it: `send` re-reads every item it is about to
edit, live.

Two consequences:

- Every `proposal` row records `item_rev`, the revision its status was computed
  against. The stored status is a snapshot for `report`; it is not trusted by
  anything that writes.
- The pre-flight belongs to `send`: it re-reads every item it is about
  to write with `fetch_items`, which never consults a cache, and decides each
  accepted row against what came back rather than against the stored status.
  An item whose `lastrevid` has left the row's `item_rev` behind is re-proposed
  first, so a value our own earlier edit already added is recognised as
  `exists` and dropped.

`fetch --qid Q…` bypasses the item TTL for the named items, so re-processing one
person after fixing something always reads live. Extraction is keyed on the
article set (languages and revision ids), so a refreshed article re-extracts
its person and an unchanged one does not.

Rate limits: one `requests.Session` per thread, a token bucket per host --
every Wikipedia and Wikidata's API share one (~4/s), because Wikimedia limits
an IP across all its wikis; the query service has its own -- `Retry-After`
honoured, descriptive User-Agent. Reads are cheap; the limiter exists so a 16-thread run does not get
the IP throttled.

### 3. Prompt

Two parts, rendered by code:

**System prompt** (`peploop/prompts/extract.md`, one file, versioned in git,
hashed into the `extraction` row). It explains: the task, the output schema field by
field, the meaning of each Wikidata property we cover, the date precision
convention (`YYYY`, `YYYY-MM`, `YYYY-MM-DD`, never a guess at a day), gender
values allowed, how citizenship differs from nationality-by-birth, that name
forms are the article title and infobox names per language (not transliterations
the model invents), the quote requirement (verbatim, from the provided text,
enough context to stand alone), and that an empty answer is correct when the
articles are silent. It is long on purpose: it must exceed the 1024-token cache
minimum for Sonnet 5 and it is the only place the rules live. It is sent with
`cache_control: {type: "ephemeral"}`.

**User message**, in this order:

1. The Wikidata state we already hold, as a compact block: QID, labels by
   language, existing `P31/P21/P27/P19/P569/P570` values with their precision,
   and the offices under `P39` with their `P580`/`P582` qualifiers. The model
   is told these are for recognition, not to be echoed as new proposals.
2. Each article as a fenced block headed by language, title, revision, URL, in
   the order *Fetch* packed them: English first where it exists, then the
   country's languages, then the rest longest first.

Nothing else. No per-request date, no run id, nothing that varies but need not.

### 4. Extract

One `client.messages.parse()` call, model `claude-sonnet-5`, adaptive thinking,
effort `low`, output schema enforced by the API:

```
Extraction
  is_human: bool
  is_human_quote: str | None
  birth_date: list[Dated]           # value, quotes[], lang; one per distinct value
  death_date: list[Dated]
  gender: "male"|"female"|"other"|None, with gender_quotes[] and gender_lang
  citizenships: list[Citizenship]   # name as written, basis, start, end, quotes[], lang
  names: list[NameForm]             # lang, label, aliases[]
  positions: list[Position]         # title, jurisdiction, start, end, acting, quotes[], lang
  birth_places: list[Placed]        # name as written, quotes[], lang
  notes: str | None                 # anything the model wants a human to know
```

`positions` and `birth_places` are free text in the articles' own languages —
the office as the article names it, the place with whatever parent chain the
article gives. They are stored and read until reconciliation places them:
`positions` become `P39` once it does, `birth_places` still wait.

The raw response, token usage, model id, prompt hash and article set are stored
in `extraction`. A person is extracted once per (prompt hash, article set);
changing the prompt re-extracts everyone on the next run, which is the point.

### 5. Reconcile

Citizenship country names are resolved to QIDs by `rigour`, not by us. The model returns the country name as the
article writes it, in whatever language; `rigour.territories.lookup_territory`
resolves it (strong names, weak names and multilingual forms, with a bounded
fuzzy fallback) to a `Territory` whose `qid` is the P27 value. Historical
states stay distinct where Wikidata keeps them distinct: "Czechoslovakia" is
`Q33946`, not `Q213`, and "Soviet Union" is `Q15180`. Where `rigour` folds a
predecessor into its successor ("West Germany" → `de`, with `Q713750` in
`other_qids`), the proposal is `Q183`. No country table of our own, no LLM call. A name `rigour` cannot place becomes a
`status=unresolved` proposal so the gaps are visible.

The same module answers the two other country questions the loop has: which
languages a person's articles are read in after English (`Territory.langs` from
their existing P27), and whether an existing P27 claim already covers a proposed one
(`get_territory_by_qid`, compared over `Territory.qids` so `Q713750` on the item
makes a proposed `Q183` read as `exists` rather than `new`).

Positions are the main reconciliation. `positions.md` is the design and
`docs/research/peploop_positions.md` the numbers; the shape in brief:

- A `position` table, one row per Wikidata item a free-text office title may
  resolve to, with `position_name` holding one row per (qid, lang) name and
  `type_edge` caching the class hierarchy. Places have a parent chain rather
  than a jurisdiction and people have neither, so there is no generalised
  `candidate (kind, …)` table: birthplace gets its own when it arrives.
- Discovery is three per-country lanes — a class descent, offices someone is
  recorded in, and offices the state's own citizens hold — unioned and tagged
  by which lane found each item. None is sufficient alone.
- **The search is one index.** `position.search_text` is a de-duplicated bag
  of the content tokens of every name the item carries and every name of the
  items it points at, each token stored beside its six-character prefix in
  place of a stemmer; a generated `to_tsvector('simple', …)` column over it
  carries the only GIN index. A query is the title *and* the jurisdiction
  string through the identical transformation, OR-ed into one `to_tsquery`
  and ordered by `ts_rank(tsv, q, 0)`, which over a bag counts how much of
  the query the item accounts for. `country_qid` is not a filter.
- **Generic classes are never a target.** `positions.generic_labels()` is the
  one list both tools read: the classes of office that name no jurisdiction.
  `generic_positions.csv` is its measured seed, the classes held across many
  states (mayor, minister, bishop, head of state; the evidence is
  `docs/research/generic_positions.md`). The `generic_position` table adds the
  roles peptree's repair answer judged generic on quoted evidence: "squadron
  commander", which one wiki recorded for its own officers alone, looks
  national in its holders and is not. `peploop.cli generic strike` takes back
  a wrong one. Reconcile reads the list and never writes to it: its
  `generic-class` verdict means "less specific than this mention", which
  holds for national classes that are right `P39` values. A `P39` onto a
  listed item says nothing about where the office was held. After the list
  changes, run `reconcile` once, which syncs `position.generic`
  (`positions.mark_generic`). It blocks four uses and nothing else:
  the search leaves flagged rows out of every shortlist, the policy skips a `P39`
  onto one as `office/generic`, and mint never takes one as a duplicate or a
  found office. It is never read against a `P279` parent. Fourteen of
  `offices.ARCHETYPES`' parents are on the list, and a minted mayoralty's
  `P279 = Q30185` is exactly right.
- Retrieval returns a deep pool and Python re-ranks it to fifteen on signals
  — how many of the asking state's citizens hold the office, whether it is
  class-like, whether its dates can span the tenure — each shown to the model
  as a tag rather than applied silently.
- Reconciliation is one request per office mention, under its own frozen
  prompt (`prompts/reconcile.md`), not a second turn of the extraction
  conversation: shortlists differ per office, and several decisions in one
  context is how a judgement pass standardises on whoever answered first.
  The request carries the mention as extraction wrote it (title, the
  `jurisdiction` string the first turn's schema has next to the title, dates,
  quotes), the whole article the quotes came from when it is under
  `ARTICLE_CAP`, and the fifteen candidates rendered as whole items. The
  model answers from a closed verdict set and `settle` refuses any QID not on
  the list; the answer schema is one fixed shape, because a per-request
  schema sits in the cached prefix and defeats the prompt cache. Every verdict
  lands in `resolution`, keyed by extraction, mention, prompt hash and
  rendering version, which is what a re-run resumes from.

### 5a. Mint

A reconciler refusal is often right: the office has no item, and its holder's
`P39` has nowhere to land. On a country Wikidata models thinly -- a one-party
state's organs, the provincial governorships, the apex court's presidency --
those refusals outweigh the statements, and a loop that only fills existing
offices never reaches the people they make politically exposed. The mint stage
creates the missing items, and is built as the most conservative stage in the
loop, because a creation is the one write that cannot be taken back by
editing: undoing it needs a deletion or a merge. `positions.md` (the creation
queue) has the mechanics; the decisions are these.

- **The evidence bar is one current holder.** An office is minted on one
  distinct attested person who holds it now, whatever the seat. An earlier bar
  asked for two people, or one plus a census entry or an official source, and
  it worked as a noise filter that also removed the offices PEP screening
  needs most: a party's leadership, a state company's head, an agency's
  director, whose predecessors nobody seeded. Whether the office is real and
  missing is what the verifier and the guard decide; the floor only says that
  somebody holds it now. A census entry is a prompt for offices nobody's
  article names, not evidence: one no mention attests is skipped. The floor
  is applied in code before a model is asked, and neither model can lower it.
- **A level's offices come from its units' own articles.** A census entry
  with `per: units` names a level (a country's local government areas) and
  the office each unit has. `mint_units` makes a candidate for every current
  unit that lacks it, attested by the head its own article names, so the
  mayoralties of towns whose mayor has no article are not left out. A level
  where fewer than half the units have the office is started only on a source
  saying every unit has it. Verify and the guard decide these as any other.
- **The shape is fixed, not drafted.** Each kind of office is an archetype in
  `offices.py` -- its `P279` parent, how it names its body, whether it is
  scoped, whether it is one seat -- with the parents measured across other
  states' items (`docs/research/position_items.md` §10), and the metaclass and
  parent taken from the state's own offices where they agree. A model drafts
  labels and picks a body; it does not invent a data model per item.
- **Unsupervised up to the send, like the rest of the loop.** Categorize
  clusters and drafts, a verifier of another model family reads each office against its evidence
  and the live duplicates, and `offices.guard` vetoes mechanically. An item is
  created when all three agree; anything else is `skipped` under the rule that
  says which stage disagreed, or `found` when the item turns out to exist. No
  status means "waiting for a human": a recurring disagreement becomes a rule,
  and `audit candidate` can only skip, after the fact.
- **Submit creates what the dry run showed.** The dry run decides and prints
  every guarded office; `--submit` runs neither categorize nor verify, so it
  creates those rows and no others. A dry run's own feed changes the misses a
  re-run would categorize, and a decision made inside the submit would create
  an office nobody was shown.
- **Crash-safe by intent, not by retry.** Before the request every row is
  re-guarded live, marked `creating` with an intent tag unique to the row, its
  payload and the attempt, and committed; the tag keys the creation in the
  send ledger. All of a run's offices go out as
  one QS3 batch of `CREATE` + `LAST` lines, and each office's QID is the
  `response_id` of its own `CREATE` command, found by line index. A row a
  crash leaves in `creating` is resolved from QS3's record of that batch --
  found by name if its answer was lost -- and only a creation that never
  reached QS3 goes back to `guarded`, or to `found` when a live search sees the
  office. A creation QS3 reports failed is `found` likewise, or else closed as
  `qs3:create-failed`. The one send lock keeps a second sender from reading
  another's in-flight batch as lost.
- **Fed back, narrowly.** A created or found item is loaded into `position`,
  and only the mentions it was clustered from are re-asked -- and only those
  the new item would reach on their shortlist -- so `propose` writes their
  `P39`s through the ordinary policy, verify and send.

### 6. Propose

`propose` skips `birth_places`, which stay in `extraction.response_json` until
a reconciler of their own exists. A `positions` entry becomes a `P39` once
reconciliation has placed it, carrying `P580`/`P582` and a `resolution_id` back
to the verdict that placed it -- `positions.md` has the three rules that decide
the rest. Every other
extracted value becomes a row in `proposal`:

```
proposal
  id, person_qid, property (P21/P27/P569/...), value (JSON in Wikidata
  datavalue shape), qualifiers (JSON), quote, source_lang, source_url,
  source_rev, extraction_id, item_rev, status, decided_by, decided_at
```

Labels and aliases are not proposed.

`status` is set by a small deterministic comparison against the Wikidata claims
already fetched, deprecated ranks ignored:

| existing claim            | proposal    | status      |
|---------------------------|-------------|-------------|
| none                      | any         | `new`       |
| same value, same/finer precision | any  | `exists`    |
| same value, coarser precision   | finer | `refine`   |
| different value, single-valued property (P569, P570, P21, P19) | any | `conflict` |
| different value, multi-valued property (P27) | any | `new` |
| name `rigour` cannot place | citizenship | `unresolved`|
| all quotes failed the verbatim gate | any | `unquoted` |
| a mechanical rule excluded it | any | `filtered` |
| a spell of the same office overlapping it | tenure | `overlapping` |

A citizenship of a predecessor state beside a recorded successor is an
addition, not a contradiction, and the same holds for every successor state;
`conflict` is reserved for properties that can only be true once.

A tenure is compared against the item's statements for *that office alone*, and
overlap decides it rather than matching endpoints: an office has one holder at
a time, so a proposal overlapping a recorded spell of it is that appointment
written down twice, dated a few days apart. Those are `overlapping` and inert.
A spell no recorded statement covers is a further term and is `new`; a recorded
statement carrying no dates at all blocks nothing and yields `refine`, because
that is the statement the proposal exists to sharpen. `exists` and `conflict`
do not occur on a tenure -- both only ever meant a statement the item already
carries, and `send` could write neither. Overlap is judged against the same
office only: a spell overlapping a *different* office is a minister keeping
their parliamentary seat. `peploop/positions.md` has the measured counts.

`filtered` and `overlapping` are what a rule decided so a human does not have
to, with the rule's name in `qualifiers._reason`. Neither is ever rendered,
reviewed or applied, and `report` counts both so each rule's volume stays
visible. The reasons:

| reason | what it excludes |
|---|---|
| `undated_predecessor` | a citizenship of a dissolved state that no article dates. Wikidata models a citizenship that ended with `P582`, so the dated case is a real addition and stays. |
| `acting` | a tenure the article called acting. Wikidata says so with a qualifier this pipeline does not write, and a `P39` omitting it asserts more than the article did. |
| `overlaps <start>..<end>` | the recorded spell of the same office a proposed tenure is a second writing-down of, an open side left blank. This one sets `overlapping` rather than `filtered`. |

A value is proposed once per *value*, not once per article: the citizenship
three wikis attest, or the birth date two of them give at different precisions,
is one row whose `qualifiers._sources` lists every `{lang, url, rev, quote}`
behind it. The list is the evidence; the writer cites one of its sources on
the statement (below), and `_basis` carries the strongest grounds any of them
gave.

`unquoted` comes last and overrides whatever the comparison found: a value
whose every quote `extract` could not find in the article text has no evidence
behind it, so it is not a candidate edit however well it agrees with Wikidata.

Only `new` and `refine` are candidates for writing; the policy decides each
(§6a). A `conflict` can be sampled in `review` -- an article disputing the
item is exactly what a human should see -- but that records that Wikidata
looks wrong, which is a to-do about the item and not an edit: `send` writes
nothing for it. A written proposal moves to `sent` and then `applied`, its
`applied_batch` naming the QS3 batch. The kind of evidence behind a proposal
(an infobox line, prose, a demonym) is not a column: the extraction JSON keeps `basis` and the quotes, so
it is derivable by query when the verdicts make it worth measuring.

### 6a. Policy

The policy runs at the end of every `propose` and `verify`. It reads every
`new` and `refine` row and decides each by an ordered list of rules in `policy.py` --
first match wins, the rule's name lands in `proposal.decided_by` as
`policy:<rule>`, and the status becomes `accepted` (what `send` writes),
`skipped` (a decision with a reason, never a queue) or `pending` (the verifier
has not been asked yet). The deterministic rules come first, so nothing a rule
would skip anyway is ever sent to a model; the verifier's answer is the last
rule, and only `supported` at better than low confidence passes it.

What the rules say, in order: a row a human rejected in the `review` sampler
is skipped (an accept there decides nothing); the dates the *extraction* found set a
person aside the item's own dates could not; a value nobody quoted has nothing
to verify; a date after today is a schedule, not a record (a term's planned
end, a nominee's start). A birth or death date attested by one wiki outside the person's own
languages is skipped, and so is a refinement over a statement somebody other
than a Wikipedia import referenced. A citizenship of a state the person's life
never reached is skipped (`citizenship_before_state`: the earliest birth and
latest death any source gives, against the state's best-rank `P571`/`P576`
from `eras.py`, the span both lanes read). A citizenship from a demonym passes only
when it names the run's own state. A `P39` passes only on a `same-office`
verdict at `high` confidence, with a start at year precision or finer, on a
tenure that ended within a generation (`P39_MAX_ENDED_YEARS`; the loop records
who holds office now), on an office the ranking tags neither
`not-office`, `abstract`, `inbound-diplomatic`, `date-conflict` nor
`foreign-scoped` (an outbound `diplomatic` posting excepted), and not on a
generic item its community uses *with* a scoping qualifier this pipeline does
not yet write. Every threshold is a constant at the top of `policy.py`, and
`check_policy` fabricates one case per rule.

Before any of them, a person's spells of one office are folded where the
office's community keeps one statement per holder rather than one per term.
`load-positions` (and the policy, for an office never counted) records how
many of the office's holders Wikidata has and how many of them carry two or
more statements for it (`position.statement_holders`, `repeat_holders`);
under a tenth (`PER_TERM_SHARE`), with at least `PER_HOLDER_MIN_HOLDERS`
holders, the office is per-holder -- the National People's Congress and the
CPPCC at about 0.1%, against the Bundestag's 65%. There, the spells every
rule but the still-held ones (`tenure_ended`, `open_unattested`,
`open_superseded`) lets through are joined into one span from the earliest
start to the latest end, open when the newest spell is, on the earliest
spell's row, carrying every member's sources; the others are skipped as
`folded`. Spells join only while each continues the one before -- starting
by the year after it ended, or within `FOLD_GAP_YEARS` of an open one's
start -- and two closed readings of one term in dispute join nothing. The
still-held rules judge a span by its newest spell's start, so a deputy of the
13th and 14th congresses is one statement from 2018 that passes on the 2023
election; a span they refuse loses its newest spell until it passes or is a
single spell again. The span is verified as the edit it now is, and the plan
treats it like any other tenure.

Four rules read a proposal against its *siblings*, which no single reading
can: a single-valued value another wiki disagrees with is `contested`; among a
person's several spells of one office, one another spell covers (the open
reading of a closed term) is a `sibling_spell`, and two that overlap without
merely touching -- consecutive terms share a boundary year and are not in
dispute -- are `contested`, the open one alone where one is open. The same
judgement runs across two *items* of one office family (`contested/twin`):
two of a state's offices sharing a kind no more than two of its offices
declare, past the metaclasses and the archetype-level classes, or an item
typed only `minister` whose name less the state's *is* an alias of the
other's kind ("Minister of Internal Affairs of Ruritania", "interior
minister"). Ambassadorships never form one, since an envoy accredited to
several states at once is the ordinary case. And two
stand in for an inception the office item lacks: a tenure that ended before
the polity the office governs existed (`tenure_before_polity`, `P571` of the
`P1001` or `P17` target) or a generation before the office's earliest
recorded holder (`tenure_before_record`). Both years are filled lazily, once
per office, the first time the policy meets it; they are the one thing in the
policy that reaches the network. A last one reads the person's record against
the office's: a spell aimed at an office nobody in the state holds, when the
record already has another `P39` starting the same day, is
`office/recorded-elsewhere` -- the unused twin of a seat the community records
on its other item. A minted office is uncounted rather than unheld, so it is
never caught.

A row a human ruled on is theirs and the policy never reads it; everything else
is re-decided from scratch on every run, so a rule change is one `propose`.
`proposed_status` keeps the `new`/`refine` a row started as. The funnel --
per property, what entered and which rule took each row -- ends every
`propose` and `verify`, `report <cc> funnel` reprints it, and it is the first
thing to read after any change to the rules.

### 6b. Verify

`verify` is the second reading, and the policy's last rule. A proposal the
deterministic gates hold as `pending` is rendered as the edit it would make --
property, value with its label, qualifiers with their precision spelled out,
for a position the office re-rendered as the reconciler showed it and the
office as the article wrote it -- beside the item's current claims for that
property, the quotes, and the whole article when it is under the cap. A second
model, from a different family than the extractor's (`PEPLOOP_VERIFY_MODEL`),
is asked under the frozen `prompts/verify.md` to find the reason the edit is
wrong, and answers from a closed set: `supported`, `unsupported`,
`contradicted`, `imprecise`, `already-recorded`, `wrong-item`, `wrong-person`.
It never sees the extractor's JSON, its notes or the reconciler's reason,
because a second opinion is worth only its uncorrelated error. One proposal per
request, never a batch.

The ledger, `verification`, is keyed on *content*: a hash of the person, the
property, the value, the qualifiers that reach Wikidata and the (language,
revision) of every source. A re-propose replaces the row and finds its verdict
again; a re-fetched article is a new question; a prompt edit or a rendering
change re-asks. `policy` looks the verdict up by that key and passes only
`supported` at better than low confidence. Everything else is `skipped` under
`verify/<verdict>`, with the model's reason in the ledger for the report.

### 7. Send

`send` is the one way peploop edits Wikidata, shared with peptree: a
QuickStatements 3.0 batch submitted over its API under the user's own
account, recorded in the joint send ledger (`ledger.py`: `wd_batch`,
`wd_edit`, `wd_strike`, `wd_removal`) *before* the request, so an answer lost
in flight is found again by the batch's name rather than sent twice. It is a
**dry run by default**: it pre-flights and plans every person with accepted
rows and writes the lines to `data/peploop/send/<cc>.qs`, counted by route;
`--submit` sends them, then the approved removals as a batch of their own,
waits, and settles each row `applied` or `failed` from what is live. Every
decision before it is unsupervised; the send itself, of every lane, goes out
in coordination with the user.

Nobody on Wikidata knows these tools, so an edit says what it is for and
never how it was made. Its batch is named by objective (`Politically exposed
persons: person profiles (81)`; peptree's is `positions hierarchy`, mint's
`missing positions`), made unique by its ledger id. The summary of each line
links the explainer page `User:Pudox/PEP` (maintained on Wikidata) and names
the property and the source wikis (`qs.describe`). A line is stamped as it goes out, so one queued under older
wording goes out under the current one. A removal carries its reason, which is
therefore written for the public.

Nothing trusts a stored status. Each accepted row is re-decided against the
live claims (`plan.py`), and routed. A dated spell of an office is matched to
the statements it *overlaps*, never to the office value alone -- keyed on the
value, a legislator's every later term read as already recorded and was never
written. A spell overlapping nothing is a further term and a new statement; one
overlapping a statement that lacks an endpoint the article gives, and agrees on
the endpoint they share, has that endpoint merged in; a near miss on a shared
endpoint touches nothing; and a statement with no dates at all takes the
article's whole. For everything else:

| live state | what is written |
|---|---|
| no statement with this value | a new statement: a `+` line |
| the value, at the same or a finer precision | nothing |
| the value more coarsely, referenced only by `P143`/`P4656`/`P813` or not at all | `SWITCH_VALUE` on that statement, then a plain line adding our reference if it has none |
| the value more coarsely, referenced to anything else | a `+` line with `R+`, the old one left alone |
| a differing value on a `SINGLE_VALUED` property | nothing; it is a conflict |

QuickStatements cannot be aimed at a statement: a plain line merges into the
*first* statement holding its value and a `+` line always creates one. So a
merge or a switch is planned only where that value sits on one statement
alone; otherwise the row closes as `ambiguous-statement`. A `+` line for a value
a plain line of the same person names waits for the next send, since in one
batch the merge could land on the statement it makes. A value no line can
carry (a Julian date, a string with a quote) closes as `unrenderable`. Every
row closed without a line is `skipped` under `plan:<route>`, which a
re-propose keeps for as long as the route still holds.

Contradiction is ruled out over *every* statement before anything else, not
over the one that happens to match: a person recorded with both a coarse 1950
and a day-precision 1 March 1950 is not someone our 1 February 1950 refines,
though it agrees with the coarse value at the precision they share. A
`somevalue` snak records that nobody knows and contradicts nothing.

The rows are grouped by the statement they land on before anything is
rendered, because a `+` line de-duplicates nothing: the same citizenship
attested in two languages is one statement, not two identical claims.

A statement cites **one** article, however many attest it: `P143` imported
from the item of the source wiki, `P4656` the permanent URL of the revision
that was read, `P813` today. The article is the first of the statement's
sources (every folded row's) in `prompt.wiki_order` with `home_first`: the
country's own languages (the seed category's, then those of each `P27`), then
English, then the rest longest article first; two revisions of one wiki go to
the first. The other sources stay in `_sources`. A merge or a switch into a
live statement adds our reference only when that statement has none at all;
one already referenced, by anyone, gets a plain line carrying just the
qualifiers, or none after a switch when there are none to add. peptree and
pepcorp cite in this one shape.

Additions go out **uncombined**, one edit per line: a combined edit fails
whole when one of its commands does, with no reason given. A row moves `accepted` → `sent` when its line is
recorded and → `applied` once every line it rode on is live, or `failed` when
QS3 reports a line failed; `send --submit --retry` sends a run's failed lines
again. A row taken out after it landed is struck by `audit proposal`, which
queues the statement's removal by id; removals go out only when approved, or
when the statement is provably only ours.

## Tables

`schema.sql` is the reference; what each table is for:

```
http_cache         cached HTTP bodies (PetScan, SPARQL, search), by URL and params
person             one row per seeded person: status, error, country
membership         which seed category found which person
item               Wikidata items as last fetched, with lastrevid
article            Wikipedia article text and revision, per person and language
extraction         the model's answer per person, prompt hash and article set
proposal           one statement to consider: value, qualifiers, sources, status,
                   decided_by, proposed_status, resolution_id, applied_batch
verdict            a human's ruling on a proposal (review sample or audit)
position           one row per office item a title may resolve to, with its signals
position_name      every name of a position, per language
type_edge          the P31/P279 ancestry cache, shared with peptree (`typegraph.py`)
memo               slow-moving reads kept under a key, shared with peptree (`memo.py`)
resolution         the reconciler's verdict per office mention, keyed on content
title_en, title_en_call   the cached English name of an office title
verification       the verifier's verdict per proposal, keyed on content
mint_call          categorize and verify requests of the mint stage
office_candidate   one office the mint stage considered, its disposition and QID
office_attestation the mentions behind a candidate, and what the feed reopened
office_unassigned  mint groups no office took, with the reason
wd_batch, wd_edit, wd_strike, wd_removal   the send ledger shared with peptree
schema_version     the hash of schema.sql as last applied
```

`verdict.reason` is one of `wrong_value`, `wrong_precision`,
`quote_unsupported`, `wrong_person`, `already_recorded`, `rule_missing`,
`source_wrong`, `wrong_office`, `other`. `wrong_office` says the office was
placed on the wrong item, which is the one thing a `P39` row can be wrong about
that no other reason names. The prompt hash that produced a proposal is reachable
through `extraction`, so acceptance per prompt version is a join, not a column.

`office_candidate.status` is the disposition (`skipped`, `found`, `guarded`,
then `creating`, `created`, `loaded`) and `rule` the rule that set it;
`office_attestation` is what the floor counted and what `feed` may reopen, and
nothing else. Migrations are a single idempotent `schema.sql`; no Alembic.
It is applied only when its hash differs from the one in `schema_version`,
under an advisory lock, since its `ALTER`s take exclusive locks.

A `verdict` row is a human's: a `review` sample (`decided_by` `review:<user>`)
or an `audit` (`audit:<name>`). `propose` keeps every proposal that has one,
which is what makes an audit survive a re-run.

`person.error` carries the exception text of a failed fetch, so one bad person
is a row rather than a dead run. `person.country` is stamped by `seed` from its
own flag and is the only thing in the schema that knows a run has a country; a
person two runs both find keeps the first one's stamp.
`proposal.resolution_id` points a `P39` back at the verdict that placed it, and
is null on everything else. `position.search_text` is the loader's token
bag — every name of the item and of the items it points at, folded, stopped,
de-duplicated, each token beside its six-character prefix — and `position.tsv`
is generated from it, since `to_tsvector(regconfig, text)` is IMMUTABLE. That
GIN index is the only one the search reads; `position_name` is indexed on
`qid` alone, because its job is to say which name matched, not to be searched.

## Commands

Run from the repository root as `python -m peploop.cli <command>`;
`countries.md` §3 is the order they run in.

```
seed             --country cc
load-positions   --country cc
fetch            --country cc | --qid Q...
extract          --country cc | --qid Q...
reconcile        --country cc
mint             --country cc [--submit] [--limit N]
propose          --country cc | --qid Q...
verify           --country cc | --qid Q...
send             --country cc [--qid Q...] [--submit [--retry]] | --status
removals         [approve|reject GUID...] [--tool peploop|peptree]
tree             place|sweep|audit|send|strike   peptree, see tree/design.md

report           --country cc [people|positions|proposals|funnel|mint]
audit            proposal|candidate [ID...] [--ids FILE] --country cc --reason TEXT --by NAME
prompt           extract|verify|mint-categorize|mint-verify [--qid Q...] [--country cc]
review           [--country cc] [--qid Q...] [--limit N]
```

Every stage works through everything its selection returns, at a fixed
concurrency per stage, and needs `--country` or `--qid`: without one it would
take every country's people. `--country` is a filter over `person.country`
and never reaches a stage -- the unit of work stays one person -- and `--qid`
overrides it, because naming someone is the answer to "this one" rather than
to "the whole run". `mint` and `reconcile` take the country as
their unit, since the queue and the shortlist's ranking are a country's.

Two commands write to Wikidata, `mint` and `send`, both as QS3 batches through
the joint send ledger, and both are dry runs unless `--submit`; both take the
one send lock, which `tree send` takes too. §7 has the routing. `removals`
approves or rejects a queued removal of either lane; the approved ones go out
with that lane's next `send --submit`.
`mint` categorizes, verifies, writes `data/mint/<cc>.md` and feeds the
`found` rows on every run, then feeds each item it creates; the feed is
idempotent.

`reconcile` first fills the ranking signals for rows that have none (the
counts only for rows no pass has counted, and the local signals), then caches
an English name for every mention title of the run
(`titles.py`, the second search channel), then resolves each mention to a
position item or refuses, one request per mention against
`prompts/reconcile.md`; `positions.md` has the whole of it. The country's
holder counts rank the shortlist -- not a filter, and another state's office
stays reachable and tagged as one. A mention already answered under this
prompt and rendering is skipped without a request, so a re-run costs only
what is new. Last, it re-asks each refusal whose shortlist now offers an item
the stored one did not, under `reopened_for = 'retrieval:2'`: a retrieval
change alters no key the ledger reads, so without this a better search would
never reach a mention already refused. Each mention is re-asked once per tag
(`PEPLOOP_REASK_SCOPE=stranded` limits it to people with no `P39` and nothing
placed). `load-positions` runs every discovery lane and gives a
label-less office its English name.

`propose` ends by deciding every row and printing the funnel; `verify` asks
about the `pending` rows and ends with the policy and its funnel, so the policy
never runs by hand. `report` prints
any checkpoint's numbers and writes nothing; `funnel` is what the rules would
decide now. `audit` is the only way to take a row out by hand -- a proposal
audit is a verdict, a skip and a strike, which a re-propose keeps, and on a
row already written it queues the statement's removal -- and there is no
approve. `prompt` prints the request a model stage would send and
sends nothing, which is how a prompt change is judged before it is run over a
country.

`review` is a Textual TUI whose unit is a person, not a proposal: it shows the
item's existing claims and links to the articles beside that person's
proposals on their way to Wikidata, drawn at random, and writes all of one
person's verdicts in one transaction on submit. It is a sampler, not a gate:
no status changes, the policy skips a row it rejected, and an accept decides
nothing. Accept is the resting state, a digit rejects a row with one of the
`verdict.reason` values, and a row marked skipped stays reviewable later.

`fetch` takes `queued` people, reads the item and every sitelinked article, and
marks each one `fetched`, `not_human` where the `P31=Q5` gate rejects it,
`out_of_scope` where the item's own dates say nobody is politically exposed any
more, or `failed` with the exception text. Both item gates run before the first
article is fetched, which is where a person's cost begins: `scope.py` discards
whoever is alive and over ninety or dead more than five years, and keeps
everyone whose dates are missing, contradictory or too coarse to place -- the
reason it discarded on lands in `person.error`. `extract` stores the model's
answer for each `fetched` person; a person already answered under this prompt
hash and these article revisions is skipped without a request.

## What is deliberately not here

- No bot account: `send` writes what the policy accepted, and the edits
  appear under the user's own name. The plan groups the same (person,
  property, value) attested from two languages by statement and sends one
  statement citing one of them; the day two attestations carry different
  qualifiers, that grouping is what has to notice.
- No roster pages, no Wikipedia lists, no non-Wikimedia sources. The prompt
  material is one person's own articles.
- No per-country policy, dispositions, backtests, or coverage ledgers.
- No Meilisearch or other search service; Postgres indexes cover the candidate
  set we have (tens of thousands of positions, not millions of places). If
  birthplace needs all human settlements, that is the moment to reconsider,
  not before.
- No page archiving. The article text and revision id in `article` is the
  provenance we keep.

## Layout

```
peploop/
  design.md
  countries.md             how a country is run
  positions.md             the position resolver, as built
  schema.sql
  generic_positions.csv    the measured generic office classes both tools never target
  fixtures/                the silver test set the bench scores against
  bench/                   the retrieval and second-turn benches over that set
  seeds/<cc>.yml           the categories a country's run is seeded from
  census/<cc>.yml          the offices a state has whether or not anyone named them
  prompts/extract.md
  prompts/reconcile.md
  prompts/verify.md
  prompts/mint_categorize.md   cluster unplaced offices, draft each item
  prompts/mint_verify.md       is this office real, current, missing, rightly shaped
  prompts/title_en.md          an English name for an office title, a search aid
  __init__.py
  db.py          connection, cache get/put, upserts
  http.py        session, rate limiter, User-Agent, disk cache
  wikidata.py    fetch item, best_label, claim readers, SPARQL
  wikipedia.py   PetScan seed, REST HTML fetch, HTML → text
  scope.py       the dates that say a person is no longer worth an extraction
  prompt.py      render system + user message
  extract.py     schema, parse call
  propose.py     compare against existing claims, write proposals
  policy.py      decide every proposal by rule: accepted, skipped or pending
  verify.py      the second reading: render the edit, ask, keep the answer by content
  review.py      Textual TUI: one person per screen, verdicts on submit
  plan.py        plan one person's accepted rows against their live item
  qs.py          the QS3 codec both lanes share: values, references, CREATE, read a line back
  route.py       aim a plan's statements as QS3 lines; check a batch
  outbox.py      what one country sends: pre-flight, route, submit, settle the rows
  ledger.py      the send ledger shared with peptree: batches, edits, strikes, removals
  send.py        submit to QS3 through the ledger: recover, reconcile, dispatch, retry, removals
  typegraph.py   the P31/P279 closure over `type_edge`, by nomenklatura's rule
  memo.py        slow-moving reads (class labels, gazetteers, leads) kept in `memo`
  llm.py         the model client, a prompt's hash, a response's token counts
  qs3.py         the QuickStatements 3.0 API client
  cli.py         the commands; every stage's selection and its concurrency
  positions.py   load a country's offices, search and rank them
  reconcile.py   resolve one office mention to an item, or refuse
  titles.py      the English name of an office title, cached per title
  offices.py     mint: the archetypes, the payload, the guard, the live duplicate reads
  mint.py        mint: the queue, the floor, categorize, verify, the disposition rules
  mint_write.py  mint: create crash-safely, recover, feed back, report, audit
  mint_units.py  mint: a level's offices, one candidate per unit, from the unit's article
  check_neutral.py    fails when the code names a country it has run
  check_review.py     drives the review TUI headlessly over shadowed tables
  check_audit.py      an audited proposal survives a re-propose
  check_propose.py    the position lane's three silent failures, offline
  check_scope.py      the relevance gate's date arithmetic, offline
  check_seed.py       the category walk seeding falls back to when PetScan is down, offline
  check_policy.py     one fabricated case per rule of the policy, offline
  check_verify.py     the verifier's rendering, key, schema and prompt coverage, offline
  check_reconcile.py  pins the second turn offline: no network, no key
  check_plan.py       what an accepted row plans to, against a live item, offline
  check_qs.py         the line each route becomes, and what a batch refuses, offline
  tree/               peptree: position-item repair, see tree/design.md
  check_mint.py       every reason not to mint, on the payload itself
  check_mint_queue.py the queue: what counts as current evidence, how mentions pool
  check_mint_categorize.py  the categorize rendering, gate and ledger, offline
  check_mint_verify.py the mint verifier's rendering, rules and ledger, offline
  check_mint_write.py one CREATE batch, crash, recovery, feed, the send lock and audit, offline
  check_titles.py     the title cache's key, batching and search channel, offline
```
