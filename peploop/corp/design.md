# pepcorp

pepcorp gives a country's state enterprises and institutions the Wikidata
profile OpenSanctions reads their politically exposed people from: what links
them to the state, a type marker that finds an enterprise in one triple, and
who leads them and sits on their boards. Its unit is the body, an item
neither peploop (people) nor peptree (positions) edits. Why the shape is what
it is, and the measurements behind it, are in `docs/soe_peps.md`.

The logic is global. What differs by country lives in its spec,
`countries/<cc>.yml` (`country.py`): official holdings lists, the state-only
legal forms that mark a body, classes the type tree misfiles as government,
seats beyond the global table, and the tiers written. A new country is a new
spec, not a code change.

## The pattern it writes

pepcorp writes on two kinds of state body: **enterprises** (businesses,
whatever their legal form) and **institutions** (museums, theatres, research
centres, broadcasters, hospitals, agencies, administrative units run like a
business). Ministries, legislatures and courts are peploop's, as positions.

- A link to each public body over it that the article names: `P127` owned
  by, for an owner (a shareholder, founder or carrier); `P749` parent
  organization, for a ministry or government it is part of or subordinate
  to. A chain of these links to the state, a first-level subdivision or a
  government body of either is the evidence of control. No shares, sizes or
  control arithmetic: the links and the article's word are the evidence.
- `P31 Q270791` state-owned enterprise, on an enterprise only: the marker,
  unless the item already reaches `Q270791` or `Q1780371` through `P31` or
  `P1454`. An institution's links are what find it.
- Leadership on the body, never as position items:

  | seat | enterprise | institution |
  |---|---|---|
  | head of the executive body | `P169` | `P1037` |
  | chair of the supervisory body | `P488` + `P2868 Q15818143` | `P488` |
  | member of the supervisory body | `P5052` | `P5052` |
  | deputy chair of the supervisory body | `P5052` + `P2868 Q1127270` | same |
  | chair / deputy / member of a one-tier board | `P488` / `P3320` + `P2868 Q1127270` / `P3320` | same |
  | member of the executive body | `P3320` + `P2868 Q2824523` | same |
  | a managing director, not the chair | `P3320` + `P2868 Q19940089` | same |
  | a party committee secretary | only where the country's spec maps it | |

  A supervisory body is whatever oversees the executive: a supervisory board,
  an administrative council, a board of trustees, a broadcasting council; all
  its named members are written. The model translates a country's titles
  into these roles by function, so the table is global and the prompt names
  no country.

The rule is the EU AMLR: every member of the administrative, management and
supervisory bodies of an enterprise the state controls; regional and
municipal enterprises when medium or large. The national and regional tiers
are written by default; a spec names its own.

## The run, per country

1. **load** (`load.py`, `actors.py`): five lanes, wide on purpose -- typed
   (`P31`/`P1454` in the `Q270791` tree), formed (`P31`/`P1454` exactly one
   of the spec's forms), owned (a chain of `P127`/`P749` links of up to three
   steps to a state actor, read from QLever, from the country's items and
   into them), parented (`P749` to a state actor), seed (the spec's
   holdings). Dropped: dissolved, not an organisation, no article in the
   country's languages or English.
2. **decide** (`decide.py`, `prompts/decide.md`): one request per body with
   its statements, chain, candidate controllers and articles. The answer:
   what it is, whether a state controls it and the bodies over it (chosen or
   named), every named seat with dates. Kept in `pcorp_call` by content.
3. **rules** (`rules.py`): the gates (an enterprise or institution, active,
   state-controlled by a quote, at a tier the spec writes), then the marker,
   the links and the seats, each with its rule. A link needs a state body:
   a state actor, a government body (a named one resolved through the
   article's links), or one the run finds state-controlled. A seat needs a
   person the article links to a human's item: pepcorp creates no people.
   What survives is planned against the live item by peploop's planner
   (`route.route`), which merges dates, role and reference into a statement
   that is there and writes a `+` line only for a new one.
4. **qs + report** (`qs.py`, `report.py`): `data/pepcorp/<cc>/<cc>-<date>.qs`
   and `.md`, with the funnel and the residue: holdings without an item,
   seats whose person has no linked item, control the articles leave unclear.
5. **send** (`outbox.py`): the latest run file through the joint send ledger,
   once per line; `--qid` limits a batch to chosen bodies.

## Layout

```
peploop/corp/
  country.py   the country spec
  load.py      lanes, filter, pcorp_item
  actors.py    state actors and the chains of links they reach
  decide.py    articles, request, answer ledger
  rules.py     gates, seat table, name resolution, planning
  qs.py        run file
  report.py    run report
  outbox.py    sending
  run.py       one country end to end
  wd.py        shared readers, init
  schema.sql   pcorp_item, pcorp_call, pcorp_decision
  prompts/decide.md
  countries/<cc>.yml
  check_rules.py, check_neutral.py, check_country.py
```

Shared with peploop: `plan.py` and `route.py` (planning and lines),
`send.py` and `ledger.py` (the write path), `wikipedia.py` and the `article`
table, `positions.organisations`, `policy` (tenure ages).

    .venv/bin/python -m peploop.cli corp run <cc> [--no-ask] [--no-reload] [--qid Q…] [--limit N]
    .venv/bin/python -m peploop.cli corp send <cc> [--qid Q…] [--submit]
