# pepcorp

pepcorp gives a country's state enterprises and institutions the Wikidata
profile OpenSanctions reads their politically exposed people from: what links
them to the state, a type marker that finds an enterprise in one triple, and
who leads them and sits on their boards. It gives its political parties the
same profile's last part: who sits in their governing bodies. Its unit is the
body, an item neither peploop (people) nor peptree (positions) edits. Why the shape is what
it is, and the measurements behind it, are in `docs/soe_peps.md`.

The logic is global. What differs by country lives in its spec,
`countries/<cc>.yml` (`country.py`): official holdings lists, the state-only
legal forms that mark a body, classes the type tree misfiles as government,
seats beyond the global table, the tiers written, where rigour's main
QID is a realm around the state, the polity whose subdivisions are the
regional tier, parties the party lane misses, the classes of its parties'
regional branches, and for the municipal tier its sector classes and
categories. A new country is a new spec, not a code change.

A country is all its current QIDs: rigour's main one and its alternates,
less the predecessor states (typed historical and ended before 1990-12-26,
the policy OpenSanctions' crawlers use). Every query placing a body in the
country runs once per QID, and each counts as the state when a link points
to it.

The parts of a rule that the three lanes share are named in
`peploop/methods.md`.

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
  polity never a parent. A legal person standing for the state (a state
  treasury, "the State") named as owner is written as the polity too; an
  item that already names it keeps it. A central bank, an agency or another
  body the run itself writes as an enterprise or institution owns in its own
  right and is linked as itself. A province named beside a national holder
  that leads is a co-owner and gets no link (`co_owner`); nor is the polity
  added beside a state holder the item already names (`holder_existing`). A chain of these links to the state, a first-level
  subdivision or a government body of either is the evidence of control;
  where the municipal tier is written, so is one to a governed unit of
  50,000 or more (`amlr.units`), whose own links follow the same split: a
  city or a district owns, it is never a parent organization.
  No shares, sizes or control arithmetic: control is what the article says
  in words, never read from share figures, which go stale. Where the
  articles say nothing about who owns a body, the spec's official holdings
  list (cited by `P854`, unless the entry is a minority stake; a wiki page
  or a query is no official list) or a
  state-only legal form of the body's own kind proves it the state's at the national tier: an
  enterprise is then owned by the polity, an institution gets its seats and
  no link.
- A body the member state's own list of prominent public functions names
  (AMLR Art. 43, `peploop/amlr/<cc>.yml`, resolved to its item in a row's
  expansion) is in PEP scope by that list: where only the control gate
  stops it -- control unclear, unstated or unquoted, another tier, an
  enterprise with no state owner named -- its seats are written all the
  same, and nothing else (`listed_scope`). The list proves scope, never
  ownership: its marker, links and class are written only where the
  article proves them, as for any body. It does not widen what a body is:
  a listed ministry, court or legislature stays peploop's, a listed
  agency or central bank is an institution like any other; nor does it
  admit a body inactive or called private in its articles, since the list
  may lag a privatisation. Such a body counts as no state owner of others.
- A statutory body with no owner -- a public broadcaster, a central bank, a
  regulator, set up by law with its leadership appointed by a state organ
  -- is the state's by statute, whatever its legal form (an association
  holding a licence, a bank with private shareholders), unless its articles
  call it private: its seats are written, and its class
  (`Q1126006`, `Q66344`, `Q1639780`) when the item has none and no
  state-only form of the spec, cited to the article whose control quote
  carries it (none, no class).
- `P31 Q270791` state-owned enterprise, on an enterprise only: the marker,
  unless the item already reaches `Q270791` or `Q1780371` through `P31` or
  `P1454`, and only when the control quote says so in words (a share figure
  does not). An institution's links are what find it. A municipal
  enterprise's marker is `P31 Q1780371` municipal company, under the same
  rule.
- **The municipal tier.** A body a municipality, a district, a public body
  of several of them (an inter-municipal association, a metropolitan
  authority), or several municipalities together, controls in the article's
  words. The AMLR takes such enterprises when medium or large; pepcorp reads
  that by proxy, never from company figures: the controlling unit is a
  governed unit of 50,000 or more and the body has an article. The unit is
  a controller the answer names; else the unit behind a controller that is
  itself a municipal body the run passes (an inter-municipal association, a
  city's holding company); else the end of the item's chain on Wikidata;
  else, when the answer names no controller with an item, the unit the body
  is located in. A body under a smaller unit, or none the run can place,
  gets nothing (`municipal_unit`) and is residue. A city-state's company is
  regional. A city's or district's official list of its holdings
  (`level: municipal`, naming its `unit`) proves the tier where the
  articles say nothing, as a state's list does: the enterprise is marked
  and owned by the unit, cited to the list.
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
  broadcasting council, a board of directors over a separate chief
  executive (a one-tier board is one that itself runs the body); all its named members are written, its chair as a
  member with the role (the idiom on Wikidata; `P488` is a one-tier
  board's chair). A council that only advises is no supervisory body. The model translates a country's titles
  into these roles by function, so the table is global and the prompt names
  no country.

- **Parties.** The members of a political party's governing bodies are PEPs
  (AMLR Art. 2(1)(34)(iii)), and Wikidata records them as statements on the
  party, not as offices; peploop mints no party offices. A party, or a party's branch for a first-level
  subdivision, is admitted by its members' seats, not by control: it gets
  no marker, no link and no class, only its seats, under every seat rule
  below (person, dates, a dead holder, a superseded chair). Its seats are
  its executive organs, translated by function:

  | seat | statement |
  |---|---|
  | chair, leader; each co-chair | `P488` |
  | deputy chair | `P3320` + `P2868 Q1127270` |
  | secretary-general | `P3975` |
  | treasurer | `P3320` + `P2868 Q388338` |
  | member of the executive committee, presidium or board | `P3320` |

  A congress, a council of delegates, a council that only ratifies, an
  arbitration commission, the parliamentary group, honorary chairs and the
  party's staff are no governing body. Youth wings, foundations, caucuses,
  alliances with no membership and a party's local branches are not
  written on; the local branches wait for the AMLR's local tier.

- **Corrections.** A body whose article shows it municipal, in a country
  that does not write the municipal tier, gains the municipal marker
  `Q1780371`, and its contradicted `Q270791` statement is proposed for
  removal and waits for `removals approve`, being another editor's. Where
  the tier is written, such a body is written on like any municipal body
  and keeps the marker it has. Only the marker itself is
  proposed, never a subclass someone chose; a city-state's company is
  regional, never corrected to municipal. A body shown privatised keeps its
  marker, ended with `P582` at the date the article gives; without a date
  nothing is written.

The rule is the EU AMLR: every member of the administrative, management and
supervisory bodies of an enterprise the state controls; regional and
municipal enterprises when medium or large. The national and regional tiers
are written by default; a spec names its own, `municipal` among them.

## The run, per country

1. **load** (`load.py`, `actors.py`): eight lanes for state bodies, wide on purpose -- typed
   (`P31`/`P1454` in the `Q270791` tree), formed (`P31`/`P1454` exactly one
   of the spec's forms), statutory (`P31` exactly a public broadcaster,
   central bank or regulatory agency), owned (a chain of `P127`/`P749` links of up to three
   steps to a state actor, read from QLever, from the country's items and
   into them), parented (`P749` to a state actor), category (the country's
   state-enterprise and agency categories), seed (the spec's holdings),
   listed (the bodies the AMLR asset resolves for the country; the asset is
   the one source, never copied into the spec). Two for parties: party (a
   party of the country with a living member who holds a current seat that
   started within twelve years: a legislator's, read as `P279*` of
   `Q4175034`, or a head office of the state, a first-level subdivision or a
   governed unit of 50,000 or more, `amlr.HEADS` over `amlr.units`; plus the
   spec's `parties`), party branch (a part of such a party or its subsidiary
   by `P361`/`P749` that is typed a party or one of the spec's
   `party_branch_classes`: most parts are working groups, currents and
   organs), both read from QLever. Three for the municipal tier, read only
   where the spec writes it, beside the owned lane's chains to its units:
   municipal typed (`P31`/`P1454` in the `Q1780371` tree), sector (an item
   located by `P131`/`P159` in a governed unit of 50,000 or more whose
   `P31` is exactly a municipal-sector class: transport, energy and
   utility companies, housing companies and associations, public
   enterprises, plus the spec's `municipal_classes`; read from QLever) and
   municipal category (the spec's `categories`). A city owns stations,
   venues and paintings far more often than a state does: the sector and
   category lanes pass the organisation test, and being located in a city
   is no control. Dropped: dissolved, not an organisation, no article in the
   country's languages or English; never sports clubs, military units,
   diplomatic missions, courts or places, youth wings, parliamentary groups
   or electoral lists, nor the spec's `exclude`.
2. **decide** (`decide.py`, `prompts/decide.md`): one request per body with
   its statements, chain, candidate controllers and articles. The answer:
   what it is, whether a state controls it and the bodies over it (chosen or
   named), every named seat with dates. Kept in `pcorp_call` by content; a
   plan reads each body's newest answer under whichever decide prompt asked
   it (one the current schema reads), so a prompt change is applied by
   asking again only the bodies it affects (`reask.py` picks them). The
   unanswered bodies go out through `llm.run`, as Message Batches when there
   are many, against the run's `--budget`. A party is asked with its own
   prompt (`prompts/decide_party.md`, a `PartyAnswer`): what it is (party,
   regional or local branch, other) and its seats, no control; it is read
   in the country's own languages, in English only where it has no other
   article. The two prompts never share a key, so a change to one re-asks
   none of the other's bodies.
3. **rules** (`rules.py`): the gates (an enterprise or institution, active,
   state-controlled by a quote, at a tier the spec writes; a listed body
   passes the last two by the list, for its seats only; a party or its
   regional branch passes when active, for its seats only; a municipal body
   needs its unit), then the marker,
   the links and the seats, each with its rule. A link needs a state body:
   a state actor, a government body (a named one resolved through the
   article's links), or one the run finds state-controlled; it is skipped
   when it would shortcut a chain the item already has (`chain_existing`),
   point a parent at a polity (`parent_polity`) or an owner at a ministry
   (`owner_ministry`). Every link left is then checked once more against its
   quote alone (`verify.py`, `prompts/verify_link.md`), told which property
   it is: founding, funding, a working level or an independent body's
   supervision is no control, being one of a state's institutes or units
   makes a parent and never an owner, and a minister's statutory
   supervision of a state legal person is subordination. Both checks answer
   in the shared verdict words (`peploop/verdict.py`), and a claim passes only
   when it is `supported` at better than low confidence. A refused link is
   skipped (`link_unverified`). So is the marker, against the control quote
   (`marker_unverified`), and a statutory class, against the control quote
   and the article's opening (`class_unverified`: a regulator sets rules for
   a sector, licenses it or supervises its firms; a registry, patent office
   or watchdog is none). A seat needs a human's item (pepcorp creates no
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
   would let through are searched. A seat whose person the article links
   goes through the same page check when nothing ties that person to the
   body (their item does not name it, their page neither links nor names
   it), and is skipped when the check does not call them the same person
   (`person_unconfirmed`: the article linked a namesake). No open seat is written for a person who
   has died (`holder_dead`), nor for a head the article does not call current
   who started before another head it names (`superseded`: an interim, a
   predecessor).
   What survives is planned against the live item by peploop's planner
   (`route.route`), which merges dates, role and reference into a statement
   that is there and writes a `+` line only for a new one.
4. **qs + report** (`qs.py`, `report.py`): `data/pepcorp/<cc>/<cc>-<date>.qs`
   and `.md`, with the funnel, the seats by how their person was found
   (link, anchor text, match), the listed bodies' own funnel (loaded,
   passed, of them by the list alone, seats written), the parties' (each
   lane loaded, what the answers call them, passed, seats by statement),
   the municipal tier's (each lane loaded, decided municipal, passed,
   marker, seats; seats a body and how many persons were found), and the
   residue:
   holdings without an item, seats whose person is neither linked nor
   matched, control the articles leave unclear, the list's named-body rows
   without an item, municipal bodies under no unit of 50,000 or more.
5. **send** (`outbox.py`): the latest run file through the joint send ledger,
   once per line; `--qid` limits a batch to chosen bodies. `--submit` goes
   out with the user, like every send.

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
  prompts/decide_party.md
  countries/<cc>.yml
  verify.py    the link check against its quote
  prompts/verify_link.md
  persons.py   name folding and fitting, candidate search, a person's page
  match.py     the unlinked seat's person, and the linked one without a tie, checked against their own page
  prompts/match_person.md
  reask.py     the bodies a decide prompt change affects, to ask again
  regress.py   a regression set asked and checked, expected against got
  eval/*.yml   regression sets
  check_rules.py, check_persons.py, check_verify.py, check_ledger.py, check_neutral.py, check_country.py
```

Shared with peploop: `plan.py` and `route.py` (planning and lines),
`send.py` and `ledger.py` (the write path), `wikipedia.py` and the `article`
table, `positions.organisations`, `policy` (tenure ages), `llm.py` (the
answer ledger's key, batches and the budget).

    .venv/bin/python -m peploop.cli corp run <cc> [--no-ask] [--no-reload] [--qid Q…] [--limit N]
    .venv/bin/python -m peploop.cli corp send <cc> [--qid Q…] [--submit]
    .venv/bin/python -m peploop.cli corp eval peploop/corp/eval/<set>.yml
    .venv/bin/python -m peploop.corp.reask [cc …]
