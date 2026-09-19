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
  not proposed until round 2 gives them QIDs. This stresses the single-call
  extraction on its real load early and yields the query corpus the candidate
  search is designed against.

## The loop

```
seed ─► fetch ─► prompt ─► extract ─► reconcile (round 2) ─► propose
```

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
  section structure intact. Reduced to plain text by a small function that
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
article gives. They are stored and read, not proposed, until round 2.

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

Round 2 adds positions and birthplace. The free-text titles already in
`extraction` are the test queries for the index; measure retrieval on them
before the second LLM turn exists. The design is fixed now so the tables do
not change:

- `candidate` table: one row per Wikidata item that may be the target of a
  reconciliation, with `kind` (`position`, `place`), `qid`, `label`, `aliases`
  (all languages), `description`, `country_qid` (P17), `jurisdiction_qid`
  (P1001), and `jurisdiction_text`: the labels and aliases of the P1001 item in
  all languages, fetched from Wikidata when the candidate is loaded. `rigour`
  is no help here. P1001 is a country only for national offices; for everything
  else it is a region ("Jihomoravský kraj"), a municipality ("Brno"), or a body
  ("Senát Parlamentu České republiky"), and those names are not in any
  territory table. So jurisdiction is a string the search matches, exactly like
  the label: an article that says "primátor Brna" has to find `Mayor of Brno`
  through the jurisdiction text when the position label is in another language.
  `country_qid` is the one column `rigour` normalises, and it is used only as a
  filter to try the run's country first. Indexed with `pg_trgm` on `label` and
  `jurisdiction_text`, and a `simple`-configuration `tsvector` over
  `search_text` (see *Tables*), since the text is multilingual.
- Position candidates are the union of: items reachable by `P279*` from
  `Q4164871` position and `Q294414` public office that carry a `P17` or
  `P1001`; items held by a human via `P39` with `P17`/`P1001` set (zavod's
  usage-based discovery); and the positions OpenSanctions tracks in its
  `wd_peps` stateful table. Loaded per country on demand, cached in the table
  with a `loaded_at`.
- Extraction becomes two turns in one conversation: turn one returns free-text
  position titles with dates and quotes; code searches `candidate` for each
  title *and* whatever jurisdiction the model names beside it (trigram +
  full-text over label, aliases and jurisdiction text, filtered to the run's
  country first, global fallback, top 15); turn two shows the candidates in
  full, jurisdiction label included, and asks the model to pick one or `none`.
  The first turn's schema therefore has a `jurisdiction: str | None` field next
  to the title, so "minister of finance" arrives with "Czechoslovakia" or
  "Czech Republic" attached where the article says which. The pick is constrained to the offered QIDs by the schema.
  The conversation shares the cached system prefix.

### 6. Propose

In round 1 `propose` skips `positions` and `birth_places`: they stay in
`extraction.response_json` until reconciliation can give them QIDs. Every other
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

A citizenship of a predecessor state beside a recorded successor is an
addition, not a contradiction, and the same holds for every successor state;
`conflict` is reserved for properties that can only be true once.

`filtered` is what a rule decided so a human does not have to, with the rule's
name in `qualifiers._reason`. It is never rendered, reviewed or applied, and
`stats` counts it so each rule's volume stays visible. The reasons:

| reason | what it excludes |
|---|---|
| `undated_predecessor` | a citizenship of a dissolved state that no article dates. Wikidata models a citizenship that ended with `P582`, so the dated case is a real addition and stays. |
| `fragment` | an alias whose tokens are a proper subset of the item's label in that language (`mul`, then `en`, when it has none there): a surname or a given name on its own. |
| `script:<scripts>` | a name in a script the language is not written in. The expected scripts are derived per language from the item's own terms in it, or failing those from the opening of the article in it; nothing to derive from is no check. |

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
live claims, and routed:

| live state | what is written |
|---|---|
| no statement with this value | a new statement, normal rank |
| the value, at the same or a finer precision | nothing |
| the value more coarsely, referenced only by `P143`/`P4656`/`P813` | that same statement, `id` and all, with our value and our reference appended |
| the value more coarsely, referenced to anything else | a second statement at `rank: preferred`, the old one left alone |
| a differing value on a `SINGLE_VALUED` property | nothing; it is a conflict |

An accepted `conflict` is therefore inert here by construction: every property
a proposal can conflict on is `SINGLE_VALUED`, and that row is ruled out before
anything else. The acceptance stands as a human's note that the item needs
looking at, and nothing reaches Wikidata through it.

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
with `Retry-After`, doubling to about two minutes; an `editconflict` re-reads
the item, re-proposes and retries once, and then the person gets an `error`
and their proposals stay `accepted`.

## Tables

```
http_cache   (url, params_hash) → body, fetched_at
person       qid, status, error, updated_at
membership   qid, category, lang, seen_at        (unique on all three)
item         qid, lastrevid, json, fetched_at
article      qid, lang, title, rev_id, url, text, fetched_at
extraction   id, qid, prompt_hash, model, article_langs[], request_json,
             response_json, usage_json, created_at
proposal     (as above, plus applied_rev, claim_guid)
verdict      proposal_id, decision (accept|reject), reason, note, created_at
candidate    (as above; empty in round 1)
```

`verdict.reason` is one of `wrong_value`, `wrong_precision`,
`quote_unsupported`, `wrong_person`, `already_recorded`, `rule_missing`,
`source_wrong`, `other`. The prompt hash that produced a proposal is reachable
through `extraction`, so acceptance per prompt version is a join, not a column.
The table exists from round 1 so nothing later has to back-fill it.

Eight tables plus one for round 2. Migrations are a single `schema.sql` applied
with `CREATE TABLE IF NOT EXISTS`; no Alembic.

`person.error` carries the exception text of a failed fetch, so one bad person
is a row rather than a dead run. `candidate.search_text` is label, aliases and
jurisdiction text joined by the loader, because Postgres refuses a `to_tsvector`
expression index over `array_to_string` (it is not IMMUTABLE); the full-text
index sits on that column and the trigram indexes stay on `label` and
`jurisdiction_text`.

## Commands

Run from the repository root as `python -m peploop.cli <command>`.

```
seed    --file peploop/seeds/cz.yml
fetch   [--limit N] [--threads 8] [--qid Q...]
refresh [--qid Q...] [--articles]
extract [--limit N] [--threads 4] [--qid Q...]
propose [--limit N] [--qid Q...]
dump    [--limit N] [--qid Q...]
stats
run     [--limit N] [--threads 4] [--qid Q...]
render  [--status new,refine] [--property P...] > out.qs
review  [--qid Q...] [--limit N]
apply   [--limit N] [--qid Q...] [--write]
```

Every command here exists. `review` is a Textual TUI whose unit is a
person, not a proposal: it shows the item's existing claims and links to the
articles beside that person's `new` and `refine` proposals, drawn at random
from those with something left to review, and writes all of one person's
decisions in one transaction on submit. Accept is the resting state, a digit
rejects a row with one of the eight `verdict.reason` values, and a row marked
skipped stays reviewable later.
`apply` writes `accepted` proposals, throttled, under the user's account, and
prints what it would send unless `--write` is given; §7 has the routing. Once
verdicts exist, `stats` adds acceptance per property and a tally per reason,
and counts `applied` beside the other statuses.

`extract` reads the model's answer for each `fetched` person and stores it;
its selection is stable, and a person already answered under this prompt hash
and these article revisions is skipped without a request. `dump` writes the
request and the parsed answer of one person to `data/extract/<qid>.md`, which
is how a prompt change is judged before it is run over a country.

`fetch` takes `queued` people, reads the item and every sitelinked article, and
marks each one `fetched`, `not_human` where the `P31=Q5` gate rejects it, or
`failed` with the exception text. `run` carries the same people on through
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
  bigpicture.md
  schema.sql
  prompts/extract.md
  __init__.py
  db.py          connection, cache get/put, upserts
  http.py        session, rate limiter, User-Agent (copied and trimmed from wd/http.py)
  wikidata.py    fetch item, best_label, claim readers
  wikipedia.py   PetScan seed, REST HTML fetch, HTML → text
  prompt.py      render system + user message
  extract.py     schema, parse call
  propose.py     compare against existing claims, write proposals
  render.py      proposals → QuickStatements lines
  review.py      Textual TUI: one person per screen, verdicts on submit
  apply.py       log in, plan one wbeditentity per person, write and record
  run.py         driver, thread pool
  cli.py
```

Roughly 800 lines. Anything that wants to be larger than that in round 1 is a
sign the increment is wrong.

## Open questions for later rounds

- Whether the position candidate set should be built from a Wikidata dump
  rather than SPARQL once it covers more than a handful of countries.
- Whether `refine` proposals (adding a day to a year-precision date) are safe
  to render without review, given how often infoboxes disagree across languages.
- How the two-turn reconciliation behaves when an article names ten offices;
  batching all titles into one second turn versus one turn per title.
