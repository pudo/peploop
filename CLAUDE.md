# Wikidata PEP workbench

One package, `peploop/`, that improves Wikidata's coverage of politically
exposed persons so OpenSanctions can read them back. Two lanes:

- **peploop** (`peploop.cli <command>`): people one at a time, from their
  Wikipedia articles to `P39` and biography statements; `mint` creates
  missing office items. Spec `peploop/design.md`, runbook `peploop/countries.md`.
- **peptree** (`peploop.cli tree <verb>`): a country's position items, filling
  `P31`/`P279`/`P17`/`P1001`; it creates nothing, so whatever must exist is
  peploop's `mint`. Spec `peploop/tree/design.md`, sweep `peploop/tree/sweep.md`.

Open work: `plans/peploop_next.md`, `plans/peptree_next.md`; what was learned:
`docs/history.md` (read it before re-measuring). `old/` is retired prior art:
never import, run or follow it.

## Sweeps run unattended

A country sweep runs end to end without checking in -- every stage and
`--submit`, undoing our own edits, model spend, rule fixes, local commits --
replacing the global pacing rules here. Ask only before a git push, merging
items or changing ranks, or removing a statement that is not provably ours.

## Requirements

`docs/requirements.md` is the user's statement of intent. When the user
directly states a requirement (not an answer to a question you asked), append
it dated, in their words, in that turn. Never add, expand, reword or remove an
entry yourself.

## Running things

- `set -a && source .envrc && set +a`, then `.venv/bin/python -m peploop.cli
  <command>` from the repository root. Never install into an environment.
- State is one Postgres database (`peploop`); peptree's tables are `ptree_*`.
  Other sessions share it, the ledger and the tree: scope sends to your country
  or batch, commit only your files, and read what went out from the ledger.
- Checks are offline scripts (`peploop.check_<name>`,
  `peploop.tree.check_<name>`): the ones next to what you touch, and all of
  them before a commit. A check that touches the database shadows its tables
  with temporary ones.
- All HTTP goes through `peploop/http.py`. Ad-hoc curl passes
  `-A "opensanctions-workbench/0.1 (friedrich@opensanctions.org)"`.

## Writing to Wikidata

- QuickStatements 3.0 through the send ledger (`peploop/ledger.py`,
  `send.py`) is the only write path; every batch is recorded before the
  request, so a lost answer is recovered, never sent twice. Our own labels or
  aliases, which QS3 cannot remove, are undone with `wb` (`--maxlag 5`).
- A new statement is a `+` line; a merge is a plain line, planned only when
  exactly one statement holds the value. Removals go by statement id.
- Statements read from an article carry a reference; inferences don't.

## Judgment

- Model Wikidata correctly first; what OpenSanctions emits is secondary.
- An office is its title and its polity: the same title in another state,
  province or council is another office.
- Measure the convention, don't declare it: tally de-facto practice over
  well-curated items before choosing a property.
- Holder-derived priors are corpus-biased: a 90–100% one-country share often
  means one wiki documented its people, not that the office is bound there.
- A class of case that should not be written becomes a rule with its check,
  never a review queue.

## Wikidata gotchas

- `wdt:` is best-rank only: ask "does this hold anywhere" with `p:P31/ps:P31`.
- Never read Wikidata's state through a cache; state reads use `max_age=0`.
- WDQS: statement-node scans time out; unbounded `wdt:P279*` inside `FILTER
  NOT EXISTS` 504s; ~150+ `VALUES` items 414; a 200 with truncated JSON is a
  deterministic timeout: bisect, never retry whole, never cache.
