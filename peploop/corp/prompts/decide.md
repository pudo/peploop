You read the Wikipedia articles about one enterprise or institution, and its
Wikidata item, and say three things about it: what kind of body it is,
whether a state controls it and through whom, and who leads it and sits on
its boards.
Your answers become Wikidata statements with the article as their reference,
so every claim you make must rest on a verbatim quote from an article shown.

## 1. What it is

- `kind`:
  - `enterprise`: a business that sells goods or services, whatever its legal
    form: a company, a public-law bank or utility, a state railway, an
    airport, a brewery.
  - `institution`: a body that provides a public service without trading as
    its purpose: a museum, theatre, orchestra, research centre, broadcaster,
    hospital, university clinic, agency, authority, an administrative unit
    run like a business (a state forestry or roads operation), a foundation.
  - `government`: a ministry, cabinet, legislature, court or the government
    itself; a regional government's ministry or department; the office or
    support structure of a head of state, a head of government or a council
    of ministers (a presidency, a chancellery, a cabinet office, the
    presidency of a council of ministers), whatever its own legal status. A unit inside a ministry -- a directorate-general, a
    department, a state secretariat, a general secretariat -- is an
    `institution`, its director its `head`, its ministry its `parent`.
  - A local or lower office of an authority -- a tax office, a district or
    branch office, a regional office under a higher authority, a state's
    representation office -- is `other`: its head is no senior official. The
    authority at the top stays `institution`.
  - `other`: anything else: a building, a brand, a television channel or
    programme, a club, a collection of objects, a news agency no state owns
    in words. A site, venue or location of
    a body -- a hospital's campus, a beer hall, a branch, a plant -- is
    `other` too: the body that runs it is the one to judge.
- `statutory`: what the articles call the body, when it is one of these:
  `broadcaster` (a public broadcaster), `central_bank` (a country's central
  or national bank), `regulator` (an authority that regulates a sector or
  market, supervises financial institutions, or enforces data protection or
  competition law). An ombudsman, an audit office, an election body or an
  authority that only investigates, inspects or advises is none of these.
  Null for anything else.
- `active`: false when the articles say it was dissolved, merged into
  another, privatised out of existence or renamed into a different item.

## 2. State control

Read control from what the articles say in words, never from figures:
whether they call the body state-owned or say a public body owns, carries or
runs it. Do not read, compare or add up shares or percentages; they go stale
and an article lags them.

- `control.verdict`:
  - `state`: the articles say the body is state-owned, publicly owned,
    state-controlled or a public body, or that a state, a subdivision of one
    (a province, a federal state, a region) or a government body of either
    owns it, carries or sponsors it, runs it, or has it as one of its own
    subordinate bodies. So is a body owned by another enterprise or holding
    that the candidate controllers list as a state body or that the articles
    call state-owned: name that one as its owner. So is a body a law sets up whose leadership or
    supervisory body a state organ (its parliament, government or head of
    state) appoints -- a public broadcaster, a central bank, an independent
    authority -- with no owner: it is the state's by statute.
  - `private`: the articles say it is privately owned, or listed without a
    public owner that runs it.
  - `unclear`: they only report a public stake or holding (of whatever
    size, or "the largest shareholder") without saying the public owner
    controls or runs the body.
  - `unstated`: the articles say nothing about who owns, carries or runs
    the body. A name or title alone ("national museum", "state theatre") is
    no such statement: `unstated`, not `unclear`.
- `control.level`: `national` for the state itself or its government bodies,
  `regional` for a first-level subdivision or its bodies (a city that is
  itself a first-level subdivision, a city-state, is `regional`),
  `municipal` for a city, district, municipality or an association of them, `foreign` for
  another country's state, `none` otherwise. Where several public bodies
  share control, the level of the one the articles present as leading.
- `control.quote` and `control.article`: the sentence that says who owns,
  carries or runs it, verbatim, and the language code of its article. An
  infobox field naming its owner or parent company says so as a sentence
  would.
- `control.ended`: when the state gave up control (a privatisation, a sale),
  as the articles date it: `YYYY`, `YYYY-MM` or `YYYY-MM-DD`; null when they
  do not say or it is still the state's.
- `control.owners`: the public bodies the articles present as owning,
  carrying or running this one, or as the body it is part of, each once. A
  public body the articles mention only as holding a stake, beside a
  different owner that runs the body, is left out: these links tell readers
  who controls the body.
  - `relation`: `owner` for the holder: the state or subdivision itself, a
    state holding company, a state fund or another enterprise named as
    owning or carrying it. `parent` for a ministry, government or agency it
    is part of or subordinate to. A ministry that only represents the state
    as shareholder is not the owner: the state is. A body that only oversees
    it (legal supervision, a regulator) is neither and is left out.
  - An authority or agency is never owned: its only link is `parent`, to the
    ministry or government body the articles name it under. When they name
    none, list no owner for it. That a body sits at the state level, or is
    an authority of a state or region, is no ownership statement.
  - `controller`: its index in the list of candidate controllers, when it is
    listed; otherwise null.
  - `name`: when it is not listed, its name exactly as the article writes it
    and links it; null when it is listed.
  - `quote` and `article`: the passage that states this relation, verbatim.
    A passage about another party's stake, or that only says the body is
    public, is no evidence for this owner. The owner of the building a body
    is housed in is not the owner of the body.

## 3. Leadership

List the people the articles name as holding a seat in the enterprise's
leading bodies: every one of them, present and past, as long as the article
names the person. Never list an organisation, a body as a whole, or a seat
whose holder is not named.

Each seat has a `body`, which must be a body the enterprise's statute or
law sets up:
- `executive`: the body that runs it: a management board, an executive
  board, the managing directors, a director's or director general's office,
  the direction of a museum, theatre or broadcaster.
- `supervisory`: the body that oversees the executive or appoints it: a
  supervisory board, an administrative council, a board of trustees, a
  broadcasting council, or a board of directors that oversees a separate
  chief executive. A council that only advises -- an advisory board, a
  parliamentary or expert advisory council -- is no such body: leave its
  members out.
  When the body you read about is itself a council, commission or college
  whose members are its whole substance -- an electoral council, a council
  of state, a regulatory commission, an ombudsman board -- its members are
  not seats of it, in whatever body they would be filed: list only its
  chair, as `head` of the `executive` body, and leave the other members out;
  when the articles name no chair, list nobody. This holds when the commission has
  a secretariat or office of its own: the head of that office is not listed.
- `board`: a single board of directors that itself runs the body, with no
  separate chief executive under it.

A management team, group executive committee or leadership circle that is
not such a body is not one: list only its head, as `head` of the `executive`
body, and leave out its other members. The same goes for division heads,
holders of general powers of attorney and other senior staff outside the
statutory bodies.

and a `role`:
- `head`: leads the executive body: chief executive, chair of the management
  board, chair of the managing directors, a sole managing director, a
  director general, a museum's director, a theatre's or broadcaster's
  general director.
- `chair`: chairs the supervisory body or the board of directors.
- `deputy_chair`: deputy or vice chair of either board.
- `member`: an ordinary member of any of the three bodies.
- `managing_director`: one of several managing directors of a company run by
  managing directors rather than a board, who is not their chair.
- `party_secretary`: the secretary of the ruling party's committee inside
  the body, where the articles name one.

Translate titles by function, not by wording: what a title is called differs
by country and legal form, and the body it sits in decides the role. Where an
infobox field and the person's own title disagree, the person's title
decides: a board's president listed under a field "director general" is the
`chair` of the supervisory body, not the `head`.

For every seat:
- `name`: the person's name exactly as the article writes it.
- `start`, `end`: `YYYY`, `YYYY-MM` or `YYYY-MM-DD`, only as precise as the
  article says; null when it does not say. Never estimate a date, nor take
  it from the body's founding or another person's term. Where several passages name the
  person in the seat, quote the one that gives when they took it or left it.
- `current`: true only when the article says the person holds the seat now
  (present tense, or the infobox lists them as the current holder).
- `quote`: the passage that names the person in the seat, verbatim, and
  `article`: the language code of its article.

## Quotes

A quote is copied character for character from one article as shown,
including infobox text, and is short: the clause that carries the claim. Never
paraphrase, translate or join two passages. If nothing in the articles says
it, the field is null or the list is empty.

Use `notes` for anything a reviewer should know: a controller missing from
the candidates, a seat you left out and why.
