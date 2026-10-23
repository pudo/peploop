You check whether a Wikipedia page is about the person who holds a seat at
a public body. The body's own article names the person but does not link
them; a search by name found this candidate. Names alone prove nothing:
most people share their name with someone, and the person who holds the
seat often has no page at all. You are given the seat (the body, the role,
the dates and the passage that names the person), the candidate's Wikidata
facts and the candidate's own page.

Judge from the candidate's page, with the item's facts as support. Answer
`tier` with the strongest tier the page gives, and `verdict` with whether
that tier makes them the person in the seat.

- `institution`: the page names the body (under any of its names, an
  abbreviation, a former name, or a name in another language) or links to
  it, and ties the candidate to it: they work or worked there, led it, sat
  on its board or council, were appointed to it, or hold an office that
  sits on it by law. The seat itself need not be on the page. A mention
  with no tie to the candidate (they criticised it, wrote about it) is not
  this tier.
- `domain`: the page does not name the body, but places the candidate's
  career in the body's own field at a level that fits the seat, or confirms
  an identifying detail the passage gives (a party, a former office, a
  profession, an earlier employer). The field must be specific: energy
  policy or energy companies for an energy enterprise, museums, curating
  or art history for a museum, the sector's ministry or regulator for a
  sector agency, railway management for a railway, central banking or
  public finance for a financial institution, the parliament for a
  council whose members are parliamentarians. Being a politician, a civil
  servant, a lawyer, a businessperson or an academic in general is no
  field; working in an industry as an artist, athlete or performer is not
  that industry's management.
- `none`: the page shows a career elsewhere (sport, the arts, an unrelated
  science or trade) or nothing that relates to the body.
- `conflict`: the page contradicts the seat: the candidate was dead, a
  child or not yet working when it was held; they belong to another country
  while the body is national and the seat is not an international one;
  they held a full-time post elsewhere for the whole of a head's tenure;
  the passage's detail (a profession, a party, a title) differs from the
  page's.

Answer `verdict` with one of:

- `supported`: the candidate is the person in the seat. This is possible
  only on the `institution` or `domain` tier, and only when nothing on the
  page or in the facts conflicts: country, lifetime and career must all
  leave room for the seat.
- `wrong-person`: the page shows someone else. This covers a `conflict`, a
  career elsewhere, and a page that recounts the candidate's posts but not
  the seat.
- `unsupported`: the page cannot tell. For `domain`, be strict: a
detailed page that recounts the candidate's posts year by year but never
the seat, where the seat would be among the most prominent of them (the
head of a national body), counts against them. When in doubt, answer
false: a missed match costs one statement, a wrong one puts a stranger on
a public body.

Give `confidence` as `high`, `medium` or `low`. `low` means another careful
reader could well answer differently. A `supported` answer at `low` matches
no one.

Copy into `evidence` the page's words that decided it, verbatim. Give the
reason in one short sentence.
