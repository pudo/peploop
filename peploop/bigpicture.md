# peploop: the system we are building toward

This page is the reference for the *end state*. It exists so each increment can
be judged against a target, and so the target does not get re-derived from
whatever was built last. It is not a build plan. `design.md` says what the
current round builds; this says why, and what comes after.

## Purpose

Wikidata is the closest thing there is to a public, global, structured record of
who holds political office. It is also mostly empty below the head-of-state
tier: legislators without birth dates, ministers without a `P39`, judges and
central bankers with an article in one language and no item at all. Wikipedia,
across its languages, already contains most of the missing facts as prose and
infoboxes.

The system reads a person's Wikipedia articles, extracts the facts Wikidata
models, checks them against what Wikidata already says, and writes what it has
learned to trust. A human reviews a sample and records why anything was wrong;
those recorded reasons are how the prompt and the pipeline get tuned, and how
the set of things the tool may write on its own grows. OpenSanctions consumes
the result through its existing Wikidata crawlers; nothing here is built for a
downstream reader, only for Wikidata being right.

## The finished system

```
 seeds ──► fetch ──► extract ──► reconcile ──► propose ──► write
   ▲                                  │             │
   │                                  ▼             ▼
   └───────────── lookup index        └──── verdicts (sampled review)
```

**Seeds.** A queue of Wikidata items worth reading. Sources, in the order they
are added: Wikipedia category trees; the holders of positions OpenSanctions
tracks; people named on position rosters and succession boxes; items with a
sitelink but no `P569`/`P39`, found by SPARQL. A seed is a QID and a reason.

**Fetch.** Every sitelinked article as plain text with its revision id, and the
Wikidata item at a known revision. Later: the roster or list pages that mention
the person, as additional material in the same prompt.

**Extract.** One LLM conversation per person, under a frozen system prompt that
describes the whole game, with the person's material injected. It yields the
flat facts (human, birth and death date, gender, citizenship, name forms) and
the free-text facts that need a QID (offices held with dates, birthplace, and
eventually family relations for dynastic polities). Every value carries a
verbatim quote and the article it came from.

**Reconcile.** Free-text offices and places become QIDs by searching a local
index and letting the model pick from what the search returns, or decline. The
index is a Postgres table loaded per country from Wikidata, holding one
searchable document per item: its names in every language, and the names of
the jurisdiction, state, body and predecessor it points at. Retrieval ranks
and the model decides; nothing is filtered out of the table, and every signal
that moved a row is shown to the model as a tag. An office the index does not
hold is not matched; it is recorded, with its evidence, in a creation queue.
Positions are built (`positions.md`); places are not started.

**Propose.** A table of evidenced claims, each compared against the live item
and marked `new`, `exists`, `refine` or `conflict`. This table is the system's
real output and the thing every later stage reads.

**Verdicts.** A reviewer sees one person at a time, their proposals listed
together with the quotes behind them and the item's current state, and accepts
each or rejects it with one reason from a short closed set and a note. The reviewer sees a sample
the human chose, never everything. The verdicts are the dataset: acceptance
per property, per kind of evidence and per prompt version are queries over
them, and the rejection reasons are what a coding session reads before it
edits the prompt. How verdicts turn into prompt changes is left to those
sessions on purpose.

**Write.** Proposals reach Wikidata through the API with references (`P143` the
wiki they were imported from, `P4656` the permanent URL of the revision read,
`P813` retrieved) and an edit summary naming the tool, under the user's own
account with a throttle. Accepted proposals are
written; so are unreviewed ones for the properties the human has switched on
after reading the verdict numbers. Making that switch automatic is a later
round, once the numbers say what the rule should be. Writes are additive. A
person's several tenures in one office land in one edit. Merges, deletions and
rank changes never happen here.

## The rounds

1. **Flat fields, Czechia.** Seed from one category. The loop runs unattended,
   proposals land in Postgres, a dumb QuickStatements renderer proves the table
   is usable. *Current: `design.md`.*
2. **Positions and birthplace.** The lookup index, the two-turn
   reconciliation, the creation queue. *Positions are built and measured on
   three countries; the second turn is assembled but has never been sent, and
   the creation queue and birthplace are not started.*
3. **Wider material.** Roster and list pages found from the person's articles
   join the prompt. The seed queue gains SPARQL-found gaps.
4. **Verdicts.** The review command and the verdict table; review the
   pilot's proposals; read acceptance per property.
5. **Write.** The throttled writer, references, the atomic multi-tenure edit;
   the first per-property switches.
6. **Scale.** More countries in one run; scheduled re-runs against
   `lastrevid`. A dump-based index is the fallback, not the plan: SPARQL
   reaches ~16,000 items per country with paged discovery.

Each round is done when its stage works on the pilot country end to end and
the previous rounds still do. A round does not start early because a later one
looks easy.

## Not in the picture

- Modelling debates. Whether an office should be a `Q294414` or a `Q4164871`,
  whether a term belongs on the office item: the system proposes what the
  article evidences, in the shape the item already uses, and leaves ontology to
  the community.
- Consumer legibility. Whether OpenSanctions emits an item is never a reason to
  propose or shape a claim.
- A web service, accounts, or a public review queue. If review needs to be
  shared, PoliLoom already exists for that, and the `proposal` table is the
  natural export toward it.
- Review of every proposal. Review is a sample that measures; a tool that has
  to be approved value by value never earns the right to write on its own.
- Country-specific policy code. A country's quirks belong in the prompt
  material and the lookup index, not in a rules table.

## Relationship to what came before

The parent repo (`wd/`, `scripts/`, `recipes/`) is the record of what was tried:
campaigns scoped per office, verdict ledgers, policy tables, backtests, roster
parsers. Its measurements (`research/`) and its gotchas (`CLAUDE.md`) are worth
reading and are cited where a round relies on one. Its code is not imported.

PoliLoom is the same idea built as a hosted service with a web UI and a dump
pipeline. peploop is the small local version of the same loop, on Postgres and
one prompt file, and may converge with it later. It does not adopt it first.
