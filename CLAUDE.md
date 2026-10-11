# Wikidata PEP workbench

Two tools that improve Wikidata's coverage of politically exposed persons, so
OpenSanctions can read them back:

- **peploop** (`peploop/`) — one person at a time: read their Wikipedia
  articles, extract the offices they held and their birth date, citizenship
  and death, resolve each office to a position item, decide every proposed
  statement by rule (and a second model where the rule is unsure), and write
  what passes. It also creates office items nobody has made yet (`mint`).
  Spec: `peploop/design.md`; how a country is run: `peploop/countries.md`.
- **peptree** (`peptree/`) — one country's position items at a time: give each
  office the type (`P31`), kind (`P279`), state (`P17`) and jurisdiction
  (`P1001`) it lacks. The sweep over every country is `peptree/sweep.md`.

Open work for each is `plans/peploop_next.md` and `plans/peptree_next.md`.
What was tried and learned along the way, including approaches that failed,
is `docs/history.md` — read it before re-measuring something.
`docs/research/` holds the measurements the code cites, `docs/institutions.md`
the institution classes `mint` works through.

`old/` is the retired campaign toolkit (`wd/`, its scripts, recipes, coverage
ledgers). It is prior art: never import it, run it, or follow its rules.

## Running things

- Python: `.venv/bin/python -m peploop.cli <command>` and
  `.venv/bin/python -m peptree.cli <verb>` from the repository root, with
  `set -a && source .envrc && set +a` first (database URL, Anthropic key,
  QuickStatements token and username). Never install into an environment.
- State is one Postgres database (`peploop`); peptree's tables are `ptree_*`.
- Checks are offline scripts: `.venv/bin/python -m peploop.check_<name>` and
  `peptree.check_<name>`. Run the ones next to what you touch, and all of them
  before a commit. Checks that touch the database shadow its tables with
  temporary ones; a new check must too.
- All HTTP goes through `peploop/http.py` (descriptive User-Agent, per-host
  pacing, disk cache). For an ad-hoc curl pass
  `-A "opensanctions-workbench/0.1 (friedrich@opensanctions.org)"`.

## Writing to Wikidata

- **QuickStatements 3.0 is the only write path**, for both tools, through one
  send ledger (`peploop/ledger.py`, `peploop/send.py`; tables `wd_batch`,
  `wd_edit`, `wd_strike`, `wd_removal`). Every batch is recorded before the
  request, so a lost answer is recovered by name, never sent twice.
- Every write command is a dry run by default; `--submit` sends. **Submit only
  when the user has asked for it in that turn.**
- A new statement is a `+` line (QS3 creates, never merges); a merge into an
  existing statement is a plain line and is only planned when exactly one
  statement holds the value. Removals go by statement id only, and only once
  approved (`removals approve`) — except undoing our own edit after a strike.
- Destructive edits — removals, rank changes, merges of items — always stop
  and ask.
- Statements read from an article carry a reference (peploop: `P143` the
  wiki, `P4656` the revision, `P813` retrieved; peptree: `S854` + `S813`);
  structural inferences go unreferenced.

## How decisions are made

- **Model Wikidata correctly first; what OpenSanctions emits is secondary.**
  When they disagree, the measured Wikidata convention wins.
- **Every case gets a disposition by rule.** No review queue, no "later"
  tier: a class of case that should not be written becomes a rule with its
  check. A human vetoes after the fact (`audit` in peploop, `strike` in
  peptree), and that veto is durable.
- **Mechanical first, a model for the tail, a mechanical gate vetoes.**
  Retrieval ranks, a model decides from a shortlist shown in full, and a rule
  can still refuse the pick.
- **Rule order is load-bearing.** "Does this belong on this item at all"
  precedes "what kind of tenure is it", and the general rule comes last.
- **A model pass is code with a committed prompt** (`peploop/prompts/`,
  `peptree/prompts/`), ledgered on content so a re-run asks only what is new.
  Instruct it to cite evidence and prefer "unclear" over guessing.
- **Measure the convention, don't declare it.** Wikidata's guidance is often
  ambiguous; tally de-facto practice over well-curated items and read
  exemplars before choosing a property.
- **Holder-derived priors are corpus-biased.** A generic occupation shows a
  90–100% one-country share because one wiki documented its people; ask
  whether the office is bound to one jurisdiction.

## Wikidata gotchas

- Many items have no `en` label: fall back `en` → `mul` (`wikidata.best_label`).
- `wbgetentities` hides transient errors in HTTP-200 bodies and answers a
  merged item under the target's id; `peploop/wikidata.py:fetch_items` handles
  both.
- Time precision below 9 (century, millennium) renders as a misleading year.
  Compare two dates at the precision they share; a whole office at 0% date
  agreement is a comparison bug before it is a parser bug.
- Hijri dates are not converted; a lane dated only in AH yields no term.
- `wdt:` returns best-rank values only, for every property: one preferred
  statement hides the normal ones and a deprecated one vanishes. Ask "does
  this hold anywhere" with `p:P31/ps:P31`, and keep `wdt:` for "the current
  value".
- Never read Wikidata's state through a cache: our own writes change it. State
  reads use `max_age=0`.
- QS3 backs off only on HTTP 429 and does not wait out maxlag, and a failed
  command reports no reason: re-send a run's failed lines with `send --retry`.
- WDQS: statement-node scans time out; an unbounded `wdt:P279*` inside
  `FILTER NOT EXISTS` 504s; ~150+ `VALUES` items overflow a GET (414); a 200
  with truncated JSON is a deterministic timeout — bisect the chunk, never
  retry it whole, never cache it.
- A country's position set contains other countries' offices: an inbound
  ambassadorship is scoped to the receiving state. Don't separate inbound
  from outbound by `P17` (predecessor states break it).
- PetScan's "uses Q5" passes category items; check `P31=Q5` yourself.
  Category membership is a candidate, never a fact.
- References extracted from wikitext arrive HTML-escaped (`&amp;`).
