# Talking to the Wikidata community

How we describe this work on Wikidata: the mass-editing proposal, WikiProject
notices, `User:Pudox/PEP`, talk-page replies and edit summaries. The governing
policy is `Wikidata:Mass-editing policy` (adopted 9 October 2026); our edits
fall in its scope and its "possibly controversial" branch (quality, quantity,
modelling), so they go through `Wikidata:Mass editing proposals` with a week
for objections.

## Vocabulary

Our tool names mean nothing outside this repository. Say what the edits do:

| our word | on Wikidata |
|---|---|
| peploop | adding positions held (`P39`) and basic biographical facts to politicians, from their Wikipedia articles |
| peptree | classifying position items (`P31`/`P279`) and stating their country and jurisdiction (`P17`/`P1001`) |
| mint | creating items for offices that Wikipedia articles name and Wikidata lacks |
| pepcorp | linking state-owned enterprises and public institutions to the state that owns them (`P127`/`P749`) |
| sweep | working through one country |
| ledger, strike | our record of every edit we sent, and of edits we will never send again |
| PEP | rarely needed; "politicians and senior public officials" is clearer |

## Tone

Write like a bot request (`Requests for permissions/Bot`, e.g. OKA bot 3,
EZBIDsBot): what the edits do, then bold-labelled mechanics (source,
matching, references, existing statements, corrections), with counts. The
purpose gets one sentence. No adjectives about the data or ourselves, no
"gaps" or "patchy", no answering objections nobody raised. A model's role is
stated as mechanism: what it reads, what it proposes, what checks it.

The FtM docs styleguide (`followthemoney/docs/styleguide.md`) applies,
minus its FtM terminology table (on Wikidata: item, statement, property,
country). In short: open with the point, not "this page explains"; present
tense; condition before action; no marketing words, "simply"/"just", em-dash
asides, rule-of-three lists or restated conclusions; bold only for field
labels. "Please" stays where we ask volunteers for something.

## What we say

- **Specific properties, not broad edits.** A fixed list of properties on a
  defined set of items (people holding public office, their offices, state
  bodies), worked through one country at a time.
- **Rooted in Wikipedia.** Every statement about a person is read from that
  person's own Wikipedia article(s) and cited with `P143`, `P4656` (the
  article revision) and `P813`. No other sources, no scraped lists.
- **Inference is used, and we say so.** A language model reads the article and
  proposes values; it does not write to Wikidata. Statements the model infers
  rather than reads (classifying an office) carry no reference, so they are
  distinguishable.
- **Verified in layers.** Separate model calls for extraction, matching to
  existing items and verification; matching against existing items and their
  types before any value is used; code rules that reject classes of mistake
  (dates outside an office's or a country's existence, generic offices, people
  out of scope); and re-checking against the live item right before sending.
- **Existing data comes first.** We add to what is there: a date already
  present is merged, not duplicated; we do not change ranks, merge items or
  remove statements other editors made.
- **We create few items, mostly offices.** Never people. An office is created
  only when no existing item matches, after a duplicate search; the body or
  place an office needs is created where it has no item (16 Chinese municipal
  party committees, 6 Cypriot municipalities so far).
- **Modelling follows the community.** We measured how well-curated items
  already model positions and follow that, including country-specific
  conventions, rather than imposing a scheme. Areas a WikiProject actively
  curates are left to it.
- **Everything is reversible.** Each run is a named, edit-grouped
  QuickStatements batch, and a database records every statement we sent and
  the analysis behind it. When a rule turns out wrong or a constraint was
  missing, we re-run the analysis under the fixed rule and know exactly which
  of our statements to withdraw, across all batches; a withdrawn statement is
  never sent again. Lead with this capability; a specific incident is cited
  only as evidence that it works, if someone asks.
- **We are reachable.** Questions on `User talk:Pudox` stop the affected work
  until answered.

## Why, said plainly

The goal is public transparency: who holds what political office, where, and
who manages state funds from the positions that control state enterprises and
institutions. Lead with this; every lane serves one of those two questions.

- **Who holds what office, where.** Wikidata's coverage of officeholders is
  uneven, and many office items lack the classification and jurisdiction that
  let anyone ask "all ministers of this province" or "every head of a state
  agency in this country". People need the office; the office needs its place.
- **Who runs state enterprises and public institutions.** State enterprises and public institutions are
  rarely linked to the state that owns them, so their boards and directors are
  invisible as public power. The ownership link and the board seat make them
  queryable.

The answers serve journalists, researchers, civil society and anyone checking
public accountability. OpenSanctions is one reuser: it reads this data back
to identify politically exposed persons for anti-money-laundering screening,
and is a company that uses it commercially. Say that once, plainly, after the
public-interest purpose, so nobody discovers it.

## Living people

Edits about living people state only facts their articles state: offices held,
dates, birthplace, citizenship, gender. We never label anyone a "politically
exposed person" on Wikidata; that judgement stays downstream.

## Before posting the proposal

- A sampled precision figure per kind of edit (persons, office
  classification, new offices, ownership links), with what the errors were.
  The proposal asks for "an evaluation of the quality"; per-country audit
  notes in `history.md` are not that number.
- Volumes so far and expected per country, from the ledger.
- 50-100 test edits per kind, as edit-group links.
- Acknowledge the roughly 50,000 edits made before the policy existed, and
  offer them for review.
- Ping Ainali from the proposal. They raised edit summaries (fixed: summaries
  now link `User:Pudox/PEP`) and redundant `P31 Q294414` statements (410
  withdrawn), and asked on 15 October for the policy's Step 3; the proposal is
  the answer, and the ping goes out only once it is posted.
- Confirm we check constraint violations after a batch (the policy's Step 4).
