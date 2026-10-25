# Wikidata PEP workbench

One package, `peploop/`, that improves Wikidata's coverage of politically
exposed persons so OpenSanctions can read them back. Three lanes:

- **peploop** (`peploop.cli <command>`): people one at a time, from their
  Wikipedia articles to `P39` and `P569 P570 P21 P27 P19`; `mint` creates
  offices, never places or people. Spec `peploop/design.md`, runbook
  `peploop/countries.md`.
- **peptree** (`peploop.cli tree <verb>`): a country's position items, filling
  `P31`/`P279`/`P17`/`P1001`; it creates nothing, so whatever must exist is
  peploop's `mint`. Spec `peploop/tree/design.md`, sweep `peploop/tree/sweep.md`.
- **pepcorp** (`peploop.cli corp <verb>`): a country's state enterprises and
  institutions, to `P127`/`P749` links, the `P31 Q270791` marker and board
  seats on the body; creates nothing. Global logic, country data in
  `peploop/corp/countries/<cc>.yml`. Spec `peploop/corp/design.md`,
  background `docs/soe_peps.md`.

What the lanes' rules share, by family: `peploop/methods.md`.

Open work: `plans/peploop_next.md`, `plans/peptree_next.md`,
`plans/pepcorp_next.md`; what was learned:
`docs/history.md` (read before re-measuring). `old/` is retired: never use it.

## Sweeps run unattended; sends go with the user

A country sweep runs every stage to its dry run without checking in -- model
spend, audits, rule fixes, local commits -- replacing the global pacing rules
here. Every write to Wikidata (`--submit`, `removals approve`, `wb`) is sent
in coordination with the user, even inside an unattended sweep: the sweep
ends with its audited dry-run lines and a send proposal (lines by property,
flags, tranches), and they go out as the user agrees. A git push, merging
items, changing ranks, or removing a statement not provably ours joins that
closing report. A sweep is done when every stage has run, its sends are
proposed or sent and audited, and its history.md line is written; people
without an article, offices no article attests and units without an item are
residue listed there, not asked.

## Requirements

`docs/requirements.md` is the user's statement of intent. A requirement the
user states directly (not an answer to your question) is appended that turn,
dated, in their words; never add, expand, reword or remove an entry yourself.

## Running things

- `set -a && source .envrc && set +a`, then `.venv/bin/python -m peploop.cli
  <command>` from the repository root. Never install into an environment.
- State is one Postgres database (`peploop`); peptree's tables are `ptree_*`.
  Other sessions share it, the ledger and the tree: scope sends to your country
  or batch, commit only your files, and read what went out from the ledger.
- Checks are offline scripts (`peploop.check_<name>`, `peploop.tree.check_<name>`):
  the ones next to what you touch, all of them before a commit; one that
  touches the database shadows its tables with temporary ones.
- All HTTP goes through `peploop/http.py`. Ad-hoc curl passes
  `-A "opensanctions-workbench/0.1 (friedrich@opensanctions.org)"`.

## Writing to Wikidata

- QuickStatements 3.0 through the send ledger (`peploop/ledger.py`,
  `send.py`) is the only write path; every batch is recorded before the
  request, so a lost answer is recovered, never sent twice. A minted item's
  terms go out in its `CREATE`; fixing our own items' terms afterwards is
  `wb` (`--maxlag 5`).
- A new statement is a `+` line; a merge is a plain line, planned only when
  exactly one statement holds the value. Removals go by statement id.
- Statements read from an article carry a reference; inferences don't.

## Judgment

- Model Wikidata correctly first; what OpenSanctions emits is secondary.
- An office is its title and its polity: the same title in another state,
  province or council is another office.
- Measure the convention, don't declare it: tally de-facto practice over
  well-curated items before choosing a property. Write the mainstream form
  and read every form: never remove or swap another editor's modelling to
  enforce ours; add beside it.
- Holder-derived priors are corpus-biased: a 90–100% one-country share often
  means one wiki documented its people, not that the office is bound there.
- A class of case that should not be written becomes a rule with its check,
  never a review queue.

## Wikidata gotchas

- `wdt:` is best-rank only: ask "does this hold anywhere" with `p:P31/ps:P31`.
- WDQS: unbounded `wdt:P279*` inside `FILTER NOT EXISTS` 504s; ~150+ `VALUES`
  items 414; truncated JSON in a 200 is a timeout: bisect, never retry whole.
