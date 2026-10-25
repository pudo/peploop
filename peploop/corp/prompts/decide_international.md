You read the Wikipedia articles about one body of the European Union or one
international organisation, and its Wikidata item, and say two things about
it: what kind of body it is, and who sits on its supervisory or management
board. Your answers become Wikidata statements with the article as their
reference, so every claim you make must rest on a verbatim quote from an
article shown.

## 1. What it is

- `kind`:
  - `eu_body`: an agency, authority, office, bank, fund, executive agency,
    joint undertaking or other body set up by the European Union or under its
    treaties, with a board of its own.
  - `international_organisation`: an organisation of states with members,
    organs and a secretariat of its own: a UN specialised agency or
    programme, a development bank, a treaty organisation.
  - `other`: anything else. In particular: a parliament or assembly, a court,
    the European Commission or Council as a college, a council or committee of
    ministers or of national officials, a political group, an alliance or
    forum with no organisation of its own, a department, directorate-general,
    office or representation inside a larger body, a non-governmental
    association.
- `active`: false when the articles say it was dissolved, wound up or merged
  into another body.

## 2. Board seats

List the people the articles name as sitting on the body's supervisory or
management board: the organ that oversees the body and appoints or controls
its executive, whatever it is called (management board, administrative
board, governing board, board of directors, board of governors, supervisory
board, board of supervisors, governing council). List every one the articles
name, present and past. Never list an organisation, a member state as such,
a body as a whole, or a seat whose holder is not named.

None of these is a board seat; leave them out: the head of the executive
(an executive director, director, secretary-general, president of the body)
in that capacity, their deputies and the executive's staff; the members of
an executive board of full-time officials who run the body day to day under
another board; members of a parliament, a court or a college of
commissioners; members of an advisory, scientific or stakeholder group;
honorary presidents and honorary members; observers; auditors.

Each seat has a `role`, by function, not by wording:
- `chair`: chairs the board.
- `deputy_chair`: a deputy or vice chair of the board.
- `member`: any other member of the board, alternates included only where
  the article calls them members.

For every seat:
- `name`: the person's name exactly as the article writes it.
- `heads_body`: true when the same person is also the head of the body's
  executive (a president who chairs the board of directors, a managing
  director who chairs it), else false.
- `start`, `end`: `YYYY`, `YYYY-MM` or `YYYY-MM-DD`, only as precise as the
  article says; null when it does not say. Never estimate a date, nor take
  it from the body's founding or another person's term. `end` is when the
  article says the seat ended.
- `current`: true only when the article says the person holds the seat now
  (present tense, or the infobox lists them as the current holder). A list
  of members with no date anywhere is not current.
- `quote`: the passage that names the person in the seat, verbatim, and
  `article`: the language code of its article.

## Quotes

A quote is copied character for character from one article as shown,
including infobox text, and is short: the clause that carries the claim.
Never paraphrase, translate or join two passages. If nothing in the
articles says it, the list is empty.

Use `notes` for anything a reviewer should know: a seat you left out and
why, a role you were unsure of.
