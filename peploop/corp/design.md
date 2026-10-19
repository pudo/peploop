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
  government body, `P127` to the polity; a ministry is never an owner, a
  polity never a parent. A chain of these links to the state, a first-level
  subdivision or a government body of either is the evidence of control.
  No shares, sizes or control arithmetic: control is what the article says
  in words, never read from share figures, which go stale.
- `P31 Q270791` state-owned enterprise, on an enterprise only: the marker,
  unless the item already reaches `Q270791` or `Q1780371` through `P31` or
  `P1454`. An institution's links are what find it.
- Leadership on the body, never as position items:

  | seat | enterprise | institution |
  |---|---|---|
  | head of the executive body | `P169` | `P1037` |
  | chair of the supervisory body | `P5052` + `P2868 Q15818143` | `P5052` + `P2868 Q140686` |
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

  A supervisory body is whatever oversees or appoints the executive: a
  supervisory board, an administrative council, a board of trustees, a
  broadcasting council; all its named members are written, its chair as a
  member with the role (the idiom on Wikidata; `P488` is a one-tier
  board's chair). A council that only advises is no supervisory body. The model translates a country's titles
  into these roles by function, so the table is global and the prompt names
  no country.

- **Corrections.** A body whose article shows it municipal, while the
  municipal tier is not written, gains the municipal marker `Q1780371`; a
  body shown private gains nothing. Either way, a contradicted `Q270791`
  (or `Q1780371`) statement is proposed for removal and waits for
  `removals approve`, being another editor's. Only the marker itself is
  proposed, never a subclass someone chose; a city-state's company is
  regional, never corrected to municipal.

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
   article's links), or one the run finds state-controlled; it is skipped
   when it would shortcut a chain the item already has (`chain_existing`),
   point a parent at a polity (`parent_polity`) or an owner at a ministry
   (`owner_ministry`). Every link left is then checked once more against its
   quote alone (`verify.py`, `prompts/verify_link.md`): funding, a working
   level or supervision is no control, and a refused link is skipped
   (`link_unverified`). A seat needs a human's item (pepcorp creates no
   people): the one the article links under the name, or else one found by
   name (`persons.py`, `match.py`, `prompts/match_person.md`). The name is
   searched fuzzily (accents, script, order, titles, middle names) among
   human items whose life can hold the seat, and each candidate's own page
   is checked against the seat: a page that names or links the body and
   ties them to it is a match, and so is an item without a page whose own
   data names the body (employer, position held or membership of it, or
   its name in the description); one that only places them
   in the body's own field, or confirms a detail the passage gives (party,
   former office), is a match only for the sole such candidate among at
   most three namesakes, and never for a citizen of other countries only;
   a career elsewhere or anything contradicting is none, and an item
   without a page whose data does not name the body is never matched. Only seats the dates
   would let through are searched. No open seat is written for a person who
   has died (`holder_dead`).
   What survives is planned against the live item by peploop's planner
   (`route.route`), which merges dates, role and reference into a statement
   that is there and writes a `+` line only for a new one.
4. **qs + report** (`qs.py`, `report.py`): `data/pepcorp/<cc>/<cc>-<date>.qs`
   and `.md`, with the funnel, the seats by how their person was found
   (link, anchor text, match), and the residue: holdings without an item,
   seats whose person is neither linked nor matched, control the articles
   leave unclear.
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
  verify.py    the link check against its quote
  prompts/verify_link.md
  persons.py   name folding and fitting, candidate search, a person's page
  match.py     the unlinked seat's person, checked against their own page
  prompts/match_person.md
  check_rules.py, check_persons.py, check_neutral.py, check_country.py
```

Shared with peploop: `plan.py` and `route.py` (planning and lines),
`send.py` and `ledger.py` (the write path), `wikipedia.py` and the `article`
table, `positions.organisations`, `policy` (tenure ages).

    .venv/bin/python -m peploop.cli corp run <cc> [--no-ask] [--no-reload] [--qid Q…] [--limit N]
    .venv/bin/python -m peploop.cli corp send <cc> [--qid Q…] [--submit]
