# peptree

Make one country's position items usable: give each office the type (`P31`),
kind (`P279`), state (`P17`) and jurisdiction (`P1001`) it lacks, so that
OpenSanctions — and peploop, which places people on these items — can read
what the office is and whose it is. The sweep over every country and
territory is `peploop/tree/sweep.md`; open work is `plans/peptree_next.md`; what was
tried is `docs/history.md`.

The parts of a rule that the three lanes share are named in
`peploop/methods.md`.

## Principles

- **The type hierarchy is polluted and stays polluted.** Mayor is 98% of head
  of government's subtree; honorary titles and ranks reach the position
  metaclass. No step trusts a `P279*` walk on its own. A FATF category
  (`categories.yml`) is a set of class handles, the subtrees known to pollute
  them (`exclude`), and the bodies its offices sit in. The level (national or
  subnational) comes from the jurisdiction, never from the class.
- **Nothing names a country.** A country's languages, predecessor states,
  gazetteer and level words come from data (`country.py`); a country whose
  data is thin gets fewer matches, never another country's rule.
- **Every slot ends applied or skipped by rule.** No review tier: the review
  is of a whole batch, after the run, before anything is sent.
- **Two channels or nothing.** The model's answer applies only when a
  mechanical channel (`signals.py`: the label names it, the holders are its
  citizens, the body carries it, the office is the state's own) agrees.
- **No country for a generic role.** The repair answers `scope` before any
  property: one polity's office, or a role many states have. Holders never
  settle it, because one wiki's editors record their own people. `P17` and
  `P1001` apply only to an office (`generic_role`), and a role judged generic
  joins the generic list (`positions.generic_labels()`), so the next load
  drops it and peploop never targets it.

## The run, per place

`python -m peploop.cli tree place <cc>` runs four steps; `tree sweep run <n>`
runs it for every pending place of a batch, each in its own process with its
log.

1. **country** (`country.py`): derive the config from data — languages,
   predecessor states and their eras, first- and second-level places, the
   words that name a level of government, a deputy, an ambassador, a party.
2. **load** (`load.py`): five discovery lanes, unioned — descent (typed into
   the position tree, scoped to the state), usage (scoped and held), orphan
   (held by a citizen, scoped to nothing), outbound (the state's posts
   abroad), predecessor (scoped to a predecessor state). A filter drops what
   is not an office (an item typed as a class, an occupation, a place, a
   generic class from the generic list), each with its reason.
   A lane the query service cuts off (the UK's descent, France's orphans) is
   asked of QLever, whose dump lags by days; every item is then read live.
3. **gaps** (`gaps.py`): per kept item, the missing `P17`, `P1001`, `P279` or
   metaclass, and the *class fix* — a well-formed office plainly of a FATF
   category whose chain does not reach that category's class gets the class as
   one more `P279`. The category × state matrix scores the country.
4. **repair** (`repair.py`, `rules.py`, `qs.py`, `report.py`): one model request
   per item with its holders, article leads and an indexed candidate list per
   asked property (`prompts/repair.md`); the answer is an index and a quote,
   cached by content in `ptree_call`. The ordered rule table in `rules.py`
   decides each slot — the refusals first (item gone or moved, declined,
   unquoted, low confidence, a generic role given a country, outside the state's era, a non-state or the realm
   in `P17`, a label that contradicts it, a class or list article given `P31`),
   then `two_channels` applies and `one_channel` skips. Applied slots render to
   `data/peptree/<cc>/<cc>-<date>.qs` (an article-derived value cites its
   article as peploop does: `P143` the wiki, `P4656` the revision read, `P813`), with the report beside it.

The repair asks only about items someone holds or that a FATF category
names (`repair.held_or_categorised`), and never about a mayoralty: an office
nobody holds matters least to OpenSanctions and is most often org-chart
clutter, and a country's thousands of mayoralties rarely clear two channels. Changing
`prompts/repair.md` re-keys the cache: re-decide earlier places with
`tree place <cc> --no-ask`, which reads the ledger and asks nothing.

## Modelling rules the code holds

- `P17` holds only a state. A dependent territory's office takes `P1001` alone.
- `P17` goes only beside a jurisdiction narrower than the state: an office
  whose `P1001` is the state itself is not asked `P17`, and a `P17` answer
  repeating `P1001` is skipped (`p17_same_as_jurisdiction`). peploop's `mint`
  follows the same rule.
- A state's era runs from its first recorded form; only a form the state
  replaced moves its start (an empire's end does not date its colonies).
  Only the home state's configured chain moves a start; any other value
  spans its own best-rank `P571`/`P576` (`peploop/eras.py`, shared with
  peploop's citizenship rule).
- A country's state is the one its offices use: Denmark is Q35, not the
  Kingdom (Q756617); the Kingdom is a realm lane.
- A permanent representative to an organisation is the state's post abroad.
- An office another state shares gets no `P1001` of ours.
- A type/class-swapped set made by a bot (Brazil's mayoralties) is skipped as
  `inverted`, left to a bot operator.

## Review and sending

The sweep ledger (`sweep.md`) is the review gate: a place goes
`pending → run → reviewed → submitted`. `tree audit <n>` prints every line of a
batch with labels and flags the shapes that have hidden a defect before. The
sweeping agent turns each flag that proves real into a rule in `rules.py` with
a case in `check_rules.py`, or a strike, then marks the batch `reviewed`;
`tree sweep table` rewrites the other columns.

Only reviewed places go out, and only with the user. `tree send` (`outbox.py`)
reconciles the joint send ledger, takes every reviewed place's latest run file, drops what went out
before, what a reviewer struck and what is already live, and writes the rest
to `data/peptree/send/pending.qs`; `tree send --submit` sends it as one QS3 batch,
then the approved removals as another. A line is plain (no `+`): it merges
into a statement that already holds its value, so an addition sent twice
changes nothing.

`tree strike <qid> <prop> [value] --reason …` vetoes a statement for good; if one
of ours already landed, its removal is queued, with the reason as its public
edit summary (approved when the statement is
provably only ours). `removals approve|reject` (peploop's top-level command,
one queue for both lanes) decides the rest. `tree send --propose-reverts` queues removals for landed lines on items the load
now drops.

## Layout

peptree is the `tree` subpackage of peploop and the `tree` command group of
`peploop/cli.py`. It shares peploop's database, HTTP layer and Wikidata reader,
the type closure (`peploop/typegraph.py`), the slow-read cache
(`peploop/memo.py`), the QuickStatements codec (`peploop/qs.py`), the send
ledger and skeleton (`peploop/ledger.py`, `peploop/send.py`) and the model
layer (`peploop/llm.py`: the answer ledger's key, batches, the budget).

```
peploop/tree/
  design.md       this file
  sweep.md        the sweep ledger: one row per place, its batch, status, notes
  categories.yml  FATF categories: class handles, excludes, bodies
  prompts/repair.md
  place.py        one place: country → load → gaps → repair → run file and report
  country.py      a country's config from data
  load.py         discovery lanes and the not-an-office filter
  gaps.py         missing statements, class fixes, the matrix
  signals.py      the mechanical channels a model answer must agree with
  repair.py       the model request per item, ledgered on content
  rules.py        the ordered disposition table
  qs.py           render and check a run file
  report.py       the funnel, matrix and skips beside the run file
  audit.py        one batch, every line labelled, for review
  sweep.py        the universe, batches and the ledger table
  outbox.py       send and strike: peptree's side of peploop/send.py
  wd.py           the run's label languages, and the readers the modules share
  check_*.py      offline checks
```

Tables are `ptree_*` in peploop's database; sends, strikes and removals are in
the joint `wd_*` tables (`peploop/ledger.py`).
