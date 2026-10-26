# Wikidata PEP workbench

A human-guided system for improving Wikidata's coverage of people in public
office, which anti-money-laundering rules call politically exposed persons
(PEPs). It reads mostly from Wikipedia: a person's own articles for their
offices and personal facts, a body's article for who owns and runs it.

Language models do the reading. Every answer quotes the article verbatim
and picks from candidates the code offers. Rules and a second model check
each answer before anything is planned, and the operator reviews each batch
before it is sent.

## Why

[OpenSanctions](https://www.opensanctions.org) needs this data, and building
it out on Wikidata is one of the ways being explored. It is not a corporate
push: the edits come from a personal account, [User:Pudox](https://www.wikidata.org/wiki/User:Pudox)
(and a bot account once approved), as an individual member of the community.
If contributing the data becomes a burden or nuisance to the community, the
work stops and the data is built elsewhere.

What OpenSanctions reads is secondary to modelling Wikidata correctly: a
tenure stated with dates and a reference, and an office that says whose it
is, serve every reuser.

## Three lanes

The work splits along the structures the rules care about. Each lane runs
country by country, because offices, institutions and state ownership differ
from one country to the next.

- **People** (`peploop`): a country's office holders, from their own
  articles to `P39` (position held, with dates) and `P569 P570 P21 P27 P19`.
  It creates office items that articles show are missing (offices only,
  never people or places). Spec: `peploop/design.md`, `peploop/positions.md`.
- **Offices** (`peptree`): a country's position items, given the type
  (`P31`), class (`P279`), country (`P17`) and jurisdiction (`P1001`) they
  lack. Spec: `peploop/tree/design.md`.
- **State bodies** (`pepcorp`): state-owned enterprises and public
  institutions, linked to their owner (`P127`/`P749`), typed, and with their
  board seats on the body. Spec: `peploop/corp/design.md`.

Scope follows the FATF and EU AMLR definitions of prominent public
functions; `docs/institutions.md` lists the institution classes a country is
checked against.

## How edits are made

- **Evidence.** A statement read from an article carries one reference to
  that article (`P143` and the page). An inference carries none. A model
  answers by quoting the article and by choosing a candidate's index; it
  never writes an item ID of its own, and a quote not found in the article
  drops the answer.
- **Checks.** Each class of error found in an audit or reported by an
  editor becomes a rule with an offline check, not a review queue. Before a
  batch goes out, a hand sample is checked for precision.
- **Additive.** The tools write the form most of Wikidata already uses, read
  every form, and add beside other editors' modelling rather than replacing
  it. A statement is removed only when it is provably the tools' own.
- **Sending.** All writes go through QuickStatements 3.0, one edit per line,
  in batches named for their purpose. Each summary names the property and
  the source wikis and links [User:Pudox/PEP](https://www.wikidata.org/wiki/User:Pudox/PEP).
  Every batch is recorded before it is sent, so a lost answer is never sent
  twice, and can be reverted whole through EditGroups. Large runs go out in
  daily tranches.

## Feedback

Please raise problems on [User talk:Pudox](https://www.wikidata.org/wiki/User_talk:Pudox).
A reported mistake is treated as a class: the rule that lets it through is
fixed and the tools' own statements of that class are taken back.
`docs/history.md` records what editors have pointed out and what changed.

## What this is not

This is a working tool for one project, published for transparency. It is
not a reusable library, not a template for Wikidata enrichment, and comes
with no licence, support or stability promise. It depends on the
OpenSanctions libraries (`rigour`, `nomenklatura`), a Postgres database and
model API keys.

## Documents

- `docs/requirements.md`: the direction the project follows, as principles.
- `peploop/methods.md`: the vocabulary and rule families the lanes share.
- `peploop/countries.md`: how a country is run, start to finish.
- `docs/history.md`: what was tried, measured and changed, and every batch
  sent.
- `docs/soe_peps.md`, `docs/research/`: background studies.
- `plans/`: working notes for changes in progress.
- `old/`: the retired first toolkit, kept as prior art.
