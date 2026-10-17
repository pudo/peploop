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
seats beyond the global table, the tiers written, and where rigour's main
QID is a realm around the state, the polity whose subdivisions are the
regional tier. A new country is a new spec, not a code change.

A country is all its current QIDs: rigour's main one and its alternates,
less the predecessor states (typed historical and ended before 1990-12-26,
the policy OpenSanctions' crawlers use). Every query placing a body in the
country runs once per QID, and each counts as the state when a link points
to it.

## The pattern it writes

pepcorp writes on two kinds of state body: **enterprises** (businesses,
whatever their legal form) and **institutions** (museums, theatres, research
centres, broadcasters, hospitals, agencies, administrative units run like a
business). Ministries, legislatures and courts are peploop's, as positions.

- A link to each public body the article presents as owning, carrying or
  running it: `P127` owned by, for the holder (the state or a subdivision
  itself, a state holding or fund, another enterprise); `P749` parent
  organization, for a ministry, government or agency it is part of or
  subordinate to. A co-owner with a mere stake gets no link: consumers read
  these links as control. The split follows usage: `P749` points to a
  government body, `P127` to the polity. A chain of these links to the state, a first-level subdivision or a
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
  | member of the executive body | `P3320` + `P2868 Q141755781` | same |
  | a managing director, not the chair | `P3320` + `P2868 Q19940089` | same |
  | a party committee secretary | only where the country's spec maps it | |

  A head is written once: not as `P169` where the same person is already
  `P1037` on the item, nor the other way round. "Executive board member"
  (`Q141755781`) is a role item created for pepcorp, because "board member" (`Q2824523`) means a
  one-tier board in some languages and an executive board in others.

  A supervisory body is whatever oversees the executive: a supervisory board,
  an administrative council, a board of trustees, a broadcasting council; all
  its named members are written. The model translates a country's titles
  into these roles by function, so the table is global and the prompt names
  no country.

- **Corrections.** A body whose article shows it municipal, while the
  municipal tier is not written, gains the municipal marker `Q1780371`; a
  body shown private gains nothing. Either way, its contradicted `Q270791`
  (or `Q1780371`) statements are proposed for removal and wait for
  `removals approve`, being other editors'.

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
   country's languages or English; never sports clubs, military units,
   diplomatic missions, courts or places, nor the spec's `exclude`.
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
