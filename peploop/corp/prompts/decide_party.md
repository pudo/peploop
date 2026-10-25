You read the Wikipedia articles about one political party, or one branch or
part of a party, and its Wikidata item, and say two things about it: what
kind of body it is, and who sits in its governing bodies.
Your answers become Wikidata statements with the article as their reference,
so every claim you make must rest on a verbatim quote from an article shown.

## 1. What it is

- `kind`:
  - `party`: a political party itself, national or one that stands only in
    one region, with members and a leadership of its own. A party that is
    formally a branch of another but stands in elections under its own name
    and statute is a `party` too.
  - `regional_branch`: a party's organisation for one first-level
    subdivision of the state (a state, region, province of the first level,
    autonomous community, or a city that is itself one).
  - `local_branch`: a party's organisation for a district, county, city or
    municipality below that level.
  - `other`: anything else: one of a party's organs as an item of its own
    (its executive committee, presidium, council: its seats are the
    party's, not the organ's), a youth or women's wing, a party foundation or
    think tank, a parliamentary group or caucus, an electoral alliance or
    joint list of several parties with no membership of its own, a faction
    or current inside a party, a party newspaper, a party's congress or
    convention, a working group, an association close to a party.
- `active`: false when the articles say it was dissolved, banned, merged
  into another party or renamed into a different item.

## 2. Governing bodies

List the people the articles name as holding a seat in the body's
governing bodies: its executive organs, which lead it between congresses.
They are, by function, whatever they are called: the chair or leader,
their deputies, the secretary-general, the treasurer, and the members of
the executive committee, presidium, national board or bureau that runs the
party. List every one the articles name, present and past. Never list an
organisation, a body as a whole, or a seat whose holder is not named.

None of these is a governing body; leave their members out: the party
congress or convention, a council of delegates, a federal or national
council that only meets between congresses to advise or ratify, an
arbitration or control commission, an auditor, the parliamentary group and
its chair or whips, honorary chairs and honorary members, the party's
staff (a managing director, a spokesperson, a campaign manager), founders
as such, candidates as such, and the leaders of the party's wings or
satellites.

Each seat has a `role`, by function, not by wording:
- `chair`: heads the party's organisation and its executive: its chair,
  president, general coordinator, or leader or spokesperson where the
  statute makes that office the head of the executive; each of two or more
  co-chairs or co-leaders who head it together. A political leader, lead
  candidate or leader in parliament whom the articles do not call head of
  the executive is no seat, where a separate chair or president runs the
  party organisation or the articles do not say: leave them out.
- `deputy_chair`: a deputy or vice chair, vice president, deputy leader.
- `secretary_general`: the secretary-general, general secretary or first
  secretary, whether or not that office leads the party. A secretary who
  only keeps the minutes or runs the office is a `member` if elected to
  the executive, else staff.
- `treasurer`: the treasurer.
- `member`: any other elected member of the executive organ (a member of
  the presidium, executive committee, national board or bureau).

For every seat:
- `name`: the person's name exactly as the article writes it.
- `start`, `end`: `YYYY`, `YYYY-MM` or `YYYY-MM-DD`, only as precise as the
  article says; null when it does not say. Never estimate a date, nor take
  it from the party's founding or another person's term. Where several
  passages name the person in the seat, quote the one that gives when they
  took it or left it. A list or infobox the article dates ("as of 2021",
  "elected in 2014") gives that date as `start`; say so in `notes`. `end`
  is when the article says the tenure ended (resigned, voted out, replaced,
  the term ran out); an arrest, a suspension, an investigation or a scandal
  is no end.
- `current`: true only when the article says the person holds the seat now
  (present tense, or the infobox lists them as the current holder). A list
  of members with no date anywhere is not current.
- `quote`: the passage that names the person in the seat, verbatim, and
  `article`: the language code of its article. A list of chairs is a
  passage: quote the line that names the person.

## Quotes

A quote is copied character for character from one article as shown,
including infobox text, and is short: the clause that carries the claim.
Never paraphrase, translate or join two passages. If nothing in the
articles says it, the field is null or the list is empty.

Use `notes` for anything a reviewer should know: a seat you left out and
why, a role you were unsure of.
