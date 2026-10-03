# peploop: Wikipedia → Wikidata enrichment loop

A small, deterministic pipeline that reads a politician's Wikipedia articles,
asks an LLM one structured question about them, and records the answers as
*proposals* in Postgres. Nothing here writes to Wikidata: a review command
records a human's verdict on each proposal, and a later round adds the writer
that applies what those verdicts have shown can be trusted.

The parent repo (`wd/`, `scripts/`) is treated as prior art to read, never as a
dependency. `peploop/` imports nothing from it. Its one dependency from the
OpenSanctions stack is `rigour`, for everything about countries: name lookup,
QID lookup, and the languages spoken in a territory.

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
- **Review measures; it does not gate.** A human reviews a sample of proposals
  and records a reason for each rejection. Those verdicts are what later
  sessions read to tune the prompt, and what decides which properties the
  writer may apply unreviewed. No stage waits for every proposal to be seen.
- **Round 1 extracts the whole shape and proposes the flat fields.** Positions
  and birthplace are extracted as free text from the first run, stored raw, and
  not proposed until reconciliation gives them QIDs. This stresses the
  single-call extraction on its real load early and yields the query corpus the
  candidate search is designed against. Positions have since crossed that line;
  birthplace has not.

## The loop

```
seed ─► fetch ─► prompt ─► extract ─► reconcile (round 2) ─► mint ─► propose
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
| Wikidata item | `item` | `fetched_at` under 7 days **and** `lastrevid` unchanged | `refresh`, and always before `render` |
| Wikipedia article | `article` | `fetched_at` under 30 days | `refresh --articles` |
| everything else (PetScan, SPARQL, search) | `http_cache` | 7 days | age only |

The item rule is the one that matters. `wbgetentities` is what we compare
proposals against, and it is also what our own eventual writes change, so an
age-based cache there would let a statement we just wrote be proposed again
(the parent repo did exactly this: a `holders()` list cached before its batch
went in re-admitted twenty existing statements). The check is cheap:
`action=query&prop=info&titles=Q1|Q2|...` returns `lastrevid` for 50 items per
call, so `refresh` over 1,500 people is 30 requests, and only items whose
revision moved are re-fetched in full.

Two consequences:

- Every `proposal` row records `item_rev`, the revision its status was computed
  against. The stored status is a snapshot for `stats`; it is not trusted by
  anything that writes.
- `render` prints stored `new` and `refine` proposals and nothing else; the
  QuickStatements importer the user pastes them into is the check on that
  batch. The pre-flight belongs to `apply`: it re-reads every item it is about
  to write with `fetch_items`, which never consults a cache, and decides each
  accepted row against what came back rather than against the stored status.
  An item whose `lastrevid` has left the row's `item_rev` behind is re-proposed
  first, so a value our own earlier edit already added is recognised as
  `exists` and dropped. The revision the pre-flight read is the edit's
  `baserevid`, which is what makes a concurrent change an `editconflict`
  instead of a silent overwrite.

`run --qid Q…` bypasses the item TTL for the named items, so re-processing one
person after fixing something always reads live. Extraction is keyed on the
article set (languages and revision ids), so a refreshed article re-extracts
its person and an unchanged one does not.

Rate limits: one `requests.Session` per thread, a shared token bucket per host
(Wikidata API ~ 4/s, Wikipedia REST ~ 8/s), `Retry-After` honoured, descriptive
User-Agent. Reads are cheap; the limiter exists so a 16-thread run does not get
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
effort `low` to start, output schema enforced by the API. The Pydantic schema
for round 1:

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

### 5. Reconcile (round 1: countries only)

Round 1 has one soft reconciliation: citizenship country names to QIDs, and
it is `rigour`'s job, not ours. The model returns the country name as the
article writes it, in whatever language; `rigour.territories.lookup_territory`
resolves it (strong names, weak names and multilingual forms, with a bounded
fuzzy fallback) to a `Territory` whose `qid` is the P27 value. Historical
states stay distinct where Wikidata keeps them distinct: "Czechoslovakia" is
`Q33946`, not `Q213`, and "Soviet Union" is `Q15180`. Where `rigour` folds a
predecessor into its successor ("West Germany" → `de`, with `Q713750` in
`other_qids`), the proposal is `Q183` and the pilot hand check watches for it.
No country table of our own, no LLM call. A name `rigour` cannot place becomes a
`status=unresolved` proposal so the gaps are visible.

The same module answers the two other country questions the loop has: which
languages a person's articles are read in after English (`Territory.langs` from
their existing P27), and whether an existing P27 claim already covers a proposed one
(`get_territory_by_qid`, compared over `Territory.qids` so `Q713750` on the item
makes a proposed `Q183` read as `exists` rather than `new`).

Round 2 adds positions and birthplace. Positions are built, measured and
proposed; birthplace is not started. `positions.md` is the design and
`research/peploop_positions.md` the numbers; the shape in one paragraph:

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

- **The evidence bar is people, not rows.** An office is minted only on two
  distinct attested holders, at least one of them current; an office held by
  one person at a time passes on one current holder plus a second channel
  saying the office exists -- its census entry (`census/<cc>.yml`, curated
  from measurement before any article is read), or an official source that
  answers when read. Asking a one-seat office for two people measures whether
  its predecessor was seeded, not whether it exists. A census entry never
  stands in for the holder itself, and a seat of many always needs two. The
  floor is applied in code before a model is asked, and neither model can
  lower it.
- **The shape is fixed, not drafted.** Each kind of office is an archetype in
  `offices.py` -- its `P279` parent, how it names its body, whether it is
  scoped, whether it is one seat -- with the parents measured across other
  states' items (`research/position_items.md` §10), and the metaclass and
  parent taken from the state's own offices where they agree. A model drafts
  labels and picks a body; it does not invent a data model per item.
- **Unsupervised, like the rest of the loop.** Categorize clusters and drafts,
  a verifier of another model family reads each office against its evidence
  and the live duplicates, and `offices.guard` vetoes mechanically. An item is
  created when all three agree; anything else is `skipped` under the rule that
  says which stage disagreed, or `found` when the item turns out to exist. No
  status means "waiting for a human": a recurring disagreement becomes a rule,
  and `mint-audit` can only skip, after the fact.
- **Crash-safe by intent, not by retry.** Before the API call the row is
  re-guarded live, marked `creating` with an intent tag unique to the row and
  its payload, and committed; the tag rides in the edit summary. A row a crash
  leaves in `creating` is resolved by `usercontribs`, which -- unlike search or
  the query service -- is authoritative the moment an edit lands: a creation
  carrying the tag is recorded, and only when there is none does a live
  duplicate search return the row to `found` or to `guarded`. One advisory
  lock per country keeps a second writer from reading another's in-flight row
  as a crash. The create goes through `apply`'s session (`wbeditentity
  new=item`, `assert=user`, `maxlag`, the EditGroups tag), under the user's
  account like every other write.
- **Fed back, narrowly.** A created or found item is loaded into `position`,
  and only the mentions it was clustered from are re-asked -- and only those
  the new item would reach on their shortlist -- so `propose` writes their
  `P39`s through the ordinary policy, verify and apply.

The knowledge is ported from `wd/create.py` and `wd/shape.py` and trimmed;
the mechanics (`wb create-entity`, JSON ledgers, a target pasted back into a
script) are left behind, and nothing is imported.

### 6. Propose

`propose` skips `birth_places`, which stay in `extraction.response_json` until
a reconciler of their own exists. A `positions` entry becomes a `P39` once
reconciliation has placed it, carrying `P580`/`P582` and a `resolution_id` back
to the verdict that placed it -- `positions.md` has the three rules that decide
the rest, and the reason `render` refuses to emit a `P39` at all. Every other
extracted value becomes a row in `proposal`:

```
proposal
  id, person_qid, property (P21/P27/P569/...), value (JSON in Wikidata
  datavalue shape), qualifiers (JSON), quote, source_lang, source_url,
  source_rev, extraction_id, item_rev, status, decided_by, decided_at
```

Labels and aliases are proposals too, under the pseudo-properties
`label:<lang>` and `alias:<lang>`: a Wikidata term is not a statement and has
no property of its own, so the language code carries the slot instead. Their
`value` is `{"language": …, "text": …}`, and a name the model could not place
in a language arrives under `und` and is `unresolved`.

`status` is set by a small deterministic comparison against the Wikidata claims
already fetched, deprecated ranks ignored:

| existing claim            | proposal    | status      |
|---------------------------|-------------|-------------|
| none                      | any         | `new`       |
| same value, same/finer precision | any  | `exists`    |
| same value, coarser precision   | finer | `refine`   |
| different value, single-valued property (P569, P570, P21, P19) | any | `conflict` |
| different value, multi-valued property (P27, labels, aliases) | any | `new` |
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
carries, and `apply` could write neither. Overlap is judged against the same
office only: a spell overlapping a *different* office is a minister keeping
their parliamentary seat. `peploop/positions.md` has the measured counts.

`filtered` and `overlapping` are what a rule decided so a human does not have
to, with the rule's name in `qualifiers._reason`. Neither is ever rendered,
reviewed or applied, and `stats` counts both so each rule's volume stays
visible. The reasons:

| reason | what it excludes |
|---|---|
| `undated_predecessor` | a citizenship of a dissolved state that no article dates. Wikidata models a citizenship that ended with `P582`, so the dated case is a real addition and stays. |
| `fragment` | an alias whose tokens are a proper subset of the item's label in that language (`mul`, then `en`, when it has none there): a surname or a given name on its own. |
| `script:<scripts>` | a name in a script the language is not written in. The expected scripts are derived per language from the item's own terms in it, or failing those from the opening of the article in it; nothing to derive from is no check. |
| `acting` | a tenure the article called acting. Wikidata says so with a qualifier this pipeline does not write, and a `P39` omitting it asserts more than the article did. |
| `overlaps <start>..<end>` | the recorded spell of the same office a proposed tenure is a second writing-down of, an open side left blank. This one sets `overlapping` rather than `filtered`. |

A value is proposed once per *value*, not once per article: the citizenship
three wikis attest, or the birth date two of them give at different precisions,
is one row whose `qualifiers._sources` lists every `{lang, url, rev, quote}`
behind it. Both write paths read that list — QuickStatements gets one line per
source and merges them, the API writer one reference per source on one
statement — and `_basis` carries the strongest grounds any of them gave. A
literal the item already holds in *any* language, `mul` included, is `exists`
and not a second language's to add.

`unquoted` comes last and overrides whatever the comparison found: a value
whose every quote `extract` could not find in the article text has no evidence
behind it, so it is not a candidate edit however well it agrees with Wikidata.
Name forms carry no quotes and are never `unquoted`.

Only `new` and `refine` are candidates for writing. A `conflict` is reviewed
too — an article disputing the item is exactly what a human should see — but
accepting one records that Wikidata looks wrong, which is a to-do about the
item and not an edit: `apply` writes nothing for it. A reviewed proposal moves to `accepted` or `rejected`; a written one to
`applied`, carrying `applied_rev` (the revision the edit produced) and, for a
statement, `claim_guid` (the statement it created or sharpened; a label or an
alias is not a statement and leaves it null). The kind of evidence behind a proposal (an infobox line, prose, a
demonym) is not a column: the extraction JSON keeps `basis` and the quotes, so
it is derivable by query when the verdicts make it worth measuring.

Name forms are proposals too: a label in a language where the item has none is
`new`; an alias not present is `new`; anything already there is `exists`.

### 6a. Policy

`policy` is the gate that replaced the human one. It reads every `new` and
`refine` row and decides each by an ordered list of rules in `policy.py` --
first match wins, the rule's name lands in `proposal.decided_by` as
`policy:<rule>`, and the status becomes `accepted` (what `apply` writes),
`skipped` (a decision with a reason, never a queue) or `pending` (the verifier
has not been asked yet). The deterministic rules come first, so nothing a rule
would skip anyway is ever sent to a model; the verifier's answer is the last
rule, and only `supported` at better than low confidence passes it.

What the rules say, in order: labels and aliases are never written (13 of the
19 reviewed were titles or fragments); the dates the *extraction* found set a
person aside the item's own dates could not; a value nobody quoted has nothing
to verify; a date after today is a schedule, not a record (a term's planned
end, a nominee's start), and the verifier passed two of those before the rule
existed. A birth or death date attested by one wiki outside the person's own
languages is skipped, and so is a refinement over a statement somebody other
than a Wikipedia import referenced. A citizenship from a demonym passes only
when it names the run's own state. A `P39` passes only on a `same-office`
verdict at `high` confidence, with a start at year precision or finer, on a
tenure that ended within a generation (`P39_MAX_ENDED_YEARS`; the loop records
who holds office now), on an office the ranking tags neither
`not-office`, `abstract`, `inbound-diplomatic`, `date-conflict` nor
`foreign-scoped` (an outbound `diplomatic` posting excepted), and not on a
generic item its community uses *with* a scoping qualifier this pipeline does
not yet write. Every threshold is a constant at the top of `policy.py`, and
`check_policy` fabricates one case per rule.

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
is re-decided from scratch on every run, so a rule change is one command.
`proposed_status` keeps the `new`/`refine` a row started as. `policy --dry-run`
prints the funnel -- per property, what entered and which rule took each row --
and that funnel is the first thing to read after any change to the rules.
Measured on the pilot's second country before any verifier existed: of 960
`P39` rows 600 reached the verifier, 153 fell to medium confidence, 69 to a
missing start, 69 to a tenure that ended before anyone alive was born, and the
mayors of a city from the 1500s went with them.

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

Measured on the first twelve requests: nine supported, one `already-recorded`
(a mayoralty the item held), one `contradicted` (an ethnic descriptor read as
a citizenship, with Austria-Hungary already on the item), one `unsupported`
(the same, on another person) -- three refusals a reviewer would have made,
at about $0.02 a request. The same run showed the one thing a single reading
cannot see, two wikis dating a death two days apart, so `policy` now skips a
single-valued value as `contested` when a sibling proposal disagrees.

### 7. Apply

`apply` writes one person per `wbeditentity` call: every proposal accepted for
them lands atomically, under the user's own account through the action API,
with the pre-flight revision as `baserevid`, `maxlag=5` and no bot flag. The
credentials are the ones wikibase-cli is configured with, and `action=login`
takes the bot password it stores.

It is a **dry run by default**. Without `--write` it does the same pre-flight
and prints the payload it would send; `--write` logs in, fetches a CSRF token
and sends, one person every ten seconds, single-threaded.

Nothing trusts a stored status. Each accepted row is re-decided against the
live claims, and routed. A dated spell of an office is matched to the statements
it *overlaps*, never to the office value alone -- keyed on the value, a
legislator's every later term read as already recorded and was never written.
A spell overlapping nothing is a further term and a new statement; one
overlapping a statement that lacks an endpoint the article gives, and agrees on
the endpoint they share, has that endpoint merged in; a near miss on a shared
endpoint touches nothing; and a statement with no dates at all takes the
article's whole. For everything else:

| live state | what is written |
|---|---|
| no statement with this value | a new statement, normal rank |
| the value, at the same or a finer precision | nothing |
| the value more coarsely, referenced only by `P143`/`P4656`/`P813` | that same statement, `id` and all, with our value and our reference appended |
| the value more coarsely, referenced to anything else | a second statement at `rank: preferred`, the old one left alone |
| a differing value on a `SINGLE_VALUED` property | nothing; it is a conflict |

An accepted `conflict` is therefore inert here by construction: every property
a proposal can conflict on is `SINGLE_VALUED`, and that row is ruled out before
anything else. Nothing reaches Wikidata through it, and with `--write` the row
is closed as `skipped` under `apply:conflict` -- as is every accepted row the
edit could not carry -- so a drainer does not select it again every minute.

A pre-flight that finds the item moved re-proposes the person and then runs
the policy over them again, because a re-propose re-derives every row the
policy decided; a verdict the verifier already gave is found by its content.
Each written row records `base_rev` and `applied_batch` beside `applied_rev`,
which is the diff link an audit reads and the batch a bad run is reverted by.

Contradiction is ruled out over *every* statement before anything else, not
over the one that happens to match: a person recorded with both a coarse 1950
and a day-precision 1 March 1950 is not someone our 1 February 1950 refines,
though it agrees with the coarse value at the precision they share. A
`somevalue` snak records that nobody knows and contradicts nothing.

Labels and aliases ride in the same payload — a label only where the item has
none in that language, an alias as `{language, value, add: ""}` so the ones
already there survive.

The rows are grouped by the statement they land on before the payload is built,
because the API de-duplicates nothing: the same citizenship attested in two
languages is one statement carrying two references, not two identical claims,
and both rows are recorded against the one guid it produced. `propose` now
groups the same value across articles into one row as well, so that row carries
its `_sources` list and contributes one reference per language on its own.

Every statement gets the same reference as the QuickStatements path: `P143`
imported from the item of the source wiki (resolved once by SPARQL over
`wdt:P31 wd:Q10876391; wdt:P424 ?code` and cached), `P4656` the permanent URL
of the revision that was read, `P813` today. A `maxlag` refusal is slept off
with `Retry-After`, doubling to a single wait of two minutes and to ten minutes
in total for one person's write; an `editconflict` re-reads the item,
re-proposes and retries once, and then the person gets an `error` and their
proposals stay `accepted`.

`apply --write --follow` is the drainer: it selects again every minute instead
of exiting, so it can run detached beside `review` and write each person up
within a minute of their being accepted. A lag episode outlasting the ten
minutes is not that person's fault, so in follow mode it leaves them untouched
and the next pass retries them silently, while any other API error still marks
them `failed` — a payload the site refuses must not be offered forever.

## Tables

```
http_cache   (url, params_hash) → body, fetched_at
person       qid, status, error, updated_at
membership   qid, category, lang, seen_at        (unique on all three)
item         qid, lastrevid, json, fetched_at
article      qid, lang, title, rev_id, url, text, fetched_at
extraction   id, qid, prompt_hash, model, article_langs[], request_json,
             response_json, usage_json, created_at
proposal     (as above, plus applied_rev, claim_guid, proposed_status)
verdict      proposal_id, decision (accept|reject), reason, note, created_at
position     qid, label, description, country_qid, jurisdiction_qid,
             jurisdiction_text, body_qid, kinds[], sources[], not_office,
             inception, abolished, replaces[], replaced_by[], holders,
             first_held_year, polity_inception_year (each with an _at stamp),
             search_text, tsv (generated from search_text), loaded_at
position_name qid, lang, text, alias                 (unique on qid+lang+text)
type_edge    qid, targets[], fetched_at              (the P31/P279 ancestry cache)
verification proposal_key, proposal_id, person_qid, property, prompt_hash,
             render_version, model, verdict, confidence, evidence, reason,
             usage_json, created_at   (unique on key, prompt, rendering, model)
mint_call    pass (categorize|verify), country, content_key, prompt_hash,
             render_version, model, request_json, response_json, usage_json
             (unique on pass, content, prompt, rendering, model)
office_candidate country, ref, origin[], institution_class, archetype,
             single_seat, draft, corrections, spec, data, holders,
             current_holders, source_url, status, rule, problems[], qid,
             created_rev, batch, intent_at, intent_tag   (unique on country+ref)
office_attestation candidate_id, extraction_id, mention_idx, person_qid,
             current, retrieved, reopened_id
office_unassigned country, group_key, reason, categorize_call
```

`verdict.reason` is one of `wrong_value`, `wrong_precision`,
`quote_unsupported`, `wrong_person`, `already_recorded`, `rule_missing`,
`source_wrong`, `wrong_office`, `other`. `wrong_office` says the office was
placed on the wrong item, which is the one thing a `P39` row can be wrong about
that no other reason names. The prompt hash that produced a proposal is reachable
through `extraction`, so acceptance per prompt version is a join, not a column.
The table exists from round 1 so nothing later has to back-fill it.

Eight tables plus three for round 2, and four for the mint stage:
`office_candidate.status` is the disposition (`skipped`, `found`, `guarded`,
then `creating`, `created`, `loaded`) and `rule` the rule that set it;
`office_attestation` is what the floor counted and what `feed` may reopen, and
nothing else. Migrations are a single `schema.sql`
applied with `CREATE TABLE IF NOT EXISTS`; no Alembic.

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

Run from the repository root as `python -m peploop.cli <command>`.

```
seed    --file peploop/seeds/cz.yml [--country cc]
fetch   [--limit N] [--threads 8] [--qid Q...]
refresh [--qid Q...] [--articles]
extract [--limit N] [--threads 4] [--qid Q...]
reconcile [--limit N] [--threads 4]
propose [--limit N] [--qid Q...]
dump    [--limit N] [--qid Q...]
stats
run     [--limit N] [--threads 4] [--qid Q...]
render  [--status new,refine] [--property P...] > out.qs
policy  [--limit N] [--qid Q...] [--dry-run]
verify  [--limit N] [--threads 4] [--qid Q...] [--dry-run]
review  [--qid Q...] [--limit N]
apply   [--limit N] [--qid Q...] [--write] [--follow]

load-positions   --country cc [--source descent|usage|citizen]
position-signals --country cc [--local-holders] [--recount]
position-stats   [--country cc]

mint-categorize  --country cc [--dry-run]
mint-verify      --country cc [--limit N] [--threads 4] [--dry-run]
mint             --country cc [--limit N] [--id N...] [--write]
mint-feed        --country cc [--id N...]
mint-report      --country cc [--out data/mint/cc.md]
mint-audit       --id N --skip --reason TEXT --by NAME
```

The `mint*` commands take `--country` as the unit of work, since the queue is
a country's. `mint` is a dry run unless `--write`, and feeds each item it
creates; `mint-feed` re-runs the feed and is idempotent.

Every command but the three `position*` ones and `refresh` also takes
`--country`, which selects the people a run seeded under that code and nothing
else. It is a filter over `person.country` and never reaches a stage: the unit
of work stays one person, and `--qid` overrides it, because naming someone is
the answer to "this one" rather than to "the next batch of these".

Every command here exists. The three `position*` commands build and measure
the round-2 lookup table and are documented in `positions.md`; the rest are
the round-1 loop. `review` is a Textual TUI whose unit is a
person, not a proposal: it shows the item's existing claims and links to the
articles beside that person's `new` and `refine` proposals, drawn at random
from those with something left to review, and writes all of one person's
decisions in one transaction on submit. Accept is the resting state, a digit
rejects a row with one of the eight `verdict.reason` values, and a row marked
skipped stays reviewable later.
`apply` writes `accepted` proposals, throttled, under the user's account, and
prints what it would send unless `--write` is given; §7 has the routing. With
`--write --follow` it stays up and drains whatever `review` accepts next. Once
verdicts exist, `stats` adds acceptance per property and a tally per reason,
and counts `applied` beside the other statuses.

`reconcile` resolves each extracted office mention to a position item or
refuses, one request per mention against `prompts/reconcile.md`; `positions.md`
has the whole of it. `--country` names the state whose holder counts rank the
shortlist -- it is not a filter, and another state's office stays reachable and
tagged as one. A mention already answered under this prompt and rendering is
skipped without a request, so a re-run costs only what is new.

`extract` reads the model's answer for each `fetched` person and stores it;
its selection is stable, and a person already answered under this prompt hash
and these article revisions is skipped without a request. `dump` writes the
request and the parsed answer of one person to `data/extract/<qid>.md`, which
is how a prompt change is judged before it is run over a country.

`fetch` takes `queued` people, reads the item and every sitelinked article, and
marks each one `fetched`, `not_human` where the `P31=Q5` gate rejects it,
`out_of_scope` where the item's own dates say nobody is politically exposed any
more, or `failed` with the exception text. Both item gates run before the first
article is fetched, which is where a person's cost begins: `scope.py` discards
whoever is alive and over ninety or dead more than five years, and keeps
everyone whose dates are missing, contradictory or too coarse to place -- the
reason it discarded on lands in `person.error`. `run` carries the same people on through
extract and propose in one pass each and marks them `proposed`. `refresh` checks `lastrevid` for
every known item (or the named ones) and re-fetches the ones that moved; with
`--articles` it re-fetches article text as well, which re-queues the affected
people. `stats` prints counts per person status, per article language and per
table, and per proposal property once there are proposals. `render` is the
first consumer of proposals and exists so the loop can be judged end to end on
the pilot.

## Pilot

Czechia via `seeds/cz.yml`, whose twelve categories queue 1,576 people; the
wide `Čeští_politici` is commented out, because its ~6,300 members are mostly
not politically exposed and the prompt should be judged on the narrower set
first. Success for round 1 means: the loop runs on those people without manual
intervention, `stats` shows a proposal distribution that reads sensibly, a
review of 50 `new` proposals finds the quote supports the value in at least 48,
and 20 people's `positions` lists read beside their infoboxes are complete and
undated only where the article is. Measured on the first 60 people at Sonnet 5
rates: $0.025 per person, output tokens being over half of it; a person with a
long article costs $0.15 to $0.18. The pilot's 1,839 people are therefore
$50 to $80 depending on the mix. If the review fails, the fix is in the prompt
file, and re-running is one command.

PetScan does not cap its JSON output at 500: the thirteen categories of
`seeds/cz.yml` returned between 0 and 6,397 rows in one response each, with no
parameter asking for more. The exactly-500 result the en category once gave at
depth 3 is unexplained, and depth 4 still times out; the seed avoids both by
staying shallow across many categories.

## What is deliberately not here

- No graduation rule, no sampling policy, no bot account: `apply` writes what a
  human has accepted, one property switch at a time is a later round, and the
  edits appear under the user's own name. `render` still does not collapse the
  same (person, property, value) attested from two languages into one line:
  QuickStatements merges them into one statement with two references, which is
  right while their qualifiers agree and wrong the day they differ. `apply`
  groups by statement and sends one claim with both references; the day two
  attestations carry different qualifiers, that grouping is what has to notice.
- No roster pages, no Wikipedia lists, no non-Wikimedia sources. The prompt
  material is one person's own articles. Widening the material is round 3.
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
  countries.md             how a country is run, and the ones that have been
  bigpicture.md
  positions.md             round 2: the position resolver, as built
  positions_discarded.md   round 2: measured and rejected, read before changing
  schema.sql
  fixtures/                the silver test set the bench scores against, and API pins
  census/<cc>.yml          the offices a state has whether or not anyone named them
  prompts/extract.md
  prompts/reconcile.md
  prompts/verify.md
  prompts/mint_categorize.md   cluster unplaced offices, draft each item
  prompts/mint_verify.md       is this office real, current, missing, rightly shaped
  __init__.py
  db.py          connection, cache get/put, upserts
  http.py        session, rate limiter, User-Agent (copied and trimmed from wd/http.py)
  wikidata.py    fetch item, best_label, claim readers, SPARQL
  wikipedia.py   PetScan seed, REST HTML fetch, HTML → text
  scope.py       the dates that say a person is no longer worth an extraction
  prompt.py      render system + user message
  extract.py     schema, parse call
  propose.py     compare against existing claims, write proposals
  policy.py      decide every proposal by rule: accepted, skipped or pending
  verify.py      the second reading: render the edit, ask, keep the answer by content
  render.py      proposals → QuickStatements lines
  review.py      Textual TUI: one person per screen, verdicts on submit
  apply.py       log in, plan one wbeditentity per person, write and record
  run.py         driver, thread pool
  cli.py
  positions.py   round 2: load a country's offices, search and rank them
  reconcile.py   round 2: the second turn, assembled but never sent
  offices.py     mint: the archetypes, the payload, the guard, the live duplicate reads
  mint.py        mint: the queue, the floor, categorize, verify, the disposition rules
  mint_write.py  mint: create crash-safely, recover, feed back, report, audit
  check_neutral.py    fails when the code names a country it has run
  check_regress.py    re-scores a prompt change against recorded verdicts
  check_review.py     drives the review TUI headlessly and undoes itself
  check_propose.py    the position lane's three silent failures, offline
  check_scope.py      the relevance gate's date arithmetic, offline
  check_seed.py       the category walk seeding falls back to when PetScan is down, offline
  check_policy.py     one fabricated case per rule of the policy, offline
  check_verify.py     the verifier's rendering, key, schema and prompt coverage, offline
  check_reconcile.py  pins the second turn offline: no network, no key
  check_apply.py      the write payloads and the router, offline
  check_mint.py       every reason not to mint, on the payload itself
  check_mint_queue.py the queue: what counts as current evidence, how mentions pool
  check_mint_categorize.py  the categorize rendering, gate and ledger, offline
  check_mint_write.py crash, recovery, feed and audit transitions, offline
```

Round 1 is roughly 800 lines and anything larger is a sign the increment is
wrong. Round 2 adds about as much again, most of it in `positions.py`; the
measurements that justify each part are in `research/peploop_positions.md`.

## Open questions for later rounds

- Whether `refine` proposals (adding a day to a year-precision date) are safe
  to render without review, given how often infoboxes disagree across languages.
- How the two-turn reconciliation behaves when an article names ten offices;
  batching all titles into one second turn versus one turn per title.
- Whether a country-match signal that needs no holder count recovers what a
  large country's arrival costs a small one's retrieval. `positions.md` closes
  on this; a dump-based candidate set is *not* the answer, since SPARQL
  reaches ~16,000 items per country with paging.
