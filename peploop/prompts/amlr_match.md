You match one row of an EU member state's list of prominent public functions
to the Wikidata item it names. The list was published under the EU
anti-money-laundering rules (Commission notice C/2023/724); each row names a
function, sometimes the body it sits in, in English and sometimes in the
state's language. A search by name found a few candidate items, each shown
with its labels, description, types, country, jurisdiction and parent. Names
alone prove little: many bodies and offices share a name across countries,
and a search returns namesakes, parents and branches.

The row says what it is looking for:

- `position`: the row names one office, and the item is that office: a
  position item ("Minister of Finance of Lithuania", "judge of the
  Constitutional Court of Slovakia", "Secretary General of OPEC"). A plural
  row naming the holders of one office ("Judges at the Constitutional
  Court") names that one office. A row naming several distinct offices
  ("Federal ministers", "State secretaries" of every ministry) names no one
  office: answer no candidate.
- `body`: the row names a body whose governing seats are the function (a
  state enterprise, an agency, a central bank, an institution), and the
  item is that body: an organisation, never the office, a building, a
  person, a place or a brand.

Answer `pick` with the index of the one candidate that is exactly what the
row names, or null. Pick only when it is clear:

- The same thing, not a relative of it. A ministry is not the enterprise it
  owns, nor the agency under it; a parent company is not its subsidiary or
  branch; a group is not one of its companies; a court is not one chamber of
  it; the office of chair is not the board; an organisation's regional
  office is not the organisation. A row naming a subsidiary ("Gunpowder
  Factory, branch of ROMARM") is matched only by the subsidiary's own item.
- For an international organisation, the organisation-wide office the row
  names, word for word. A state lists the functions seated on its
  territory: the head of an office, representation, delegation or regional
  centre, a function "based in" a city, a lesser secretary or director, is
  not the organisation's head and has no candidate unless that very post
  has an item.
- The same polity. An office or body of the right name in another state, a
  region or a city is another one: "Minister of Health" of another country,
  a municipal enterprise for a national one.
- A current or recent item. An abolished office or a dissolved body that a
  successor replaced is not the row's, unless the row names it by that old
  name and nothing replaced it.
- One candidate. When two candidates would fit equally (two items for one
  body, or the row too vague to tell them apart), answer null.
- A generic class of office ("minister", "mayor", "member of parliament",
  "ambassador") without the state is not the state's office.

Answer `verdict` with one of:

- `supported`: the picked candidate is what the row names.
- `wrong-item`: no candidate is; the nearest is a parent, a namesake, a
  relative or a class.
- `unsupported`: the row or the candidates leave it open.

Give `confidence` as `high`, `medium` or `low`. `low` means another careful
reader could well answer differently; a `supported` answer at `low` matches
nothing.

Also read the row itself, independently of the candidates, and answer what
it names:

- `kind`: `position` (one office), `body` (one named body whose seats are
  the function), `body_class` (a class of bodies or of their offices:
  "mayors", "boards of state-owned enterprises", "directors of state
  agencies", several distinct offices), or `unusable` (a rank, a role with
  no body, an empty or garbled row).
- `amlr`: the clause of the AMLR (Reg. 2024/1624, Art. 2(34)) the function
  falls under:
  - `i_executive`: heads of state and government, ministers, deputy and
    assistant ministers, state secretaries;
  - `ii_legislature`: members of parliament and similar national
    legislative bodies;
  - `iii_party`: governing bodies of political parties;
  - `iv_courts`: supreme, constitutional and other high courts, and
    prosecutors general;
  - `v_audit_cb`: courts of auditors, boards of central banks;
  - `vi_diplomat_military`: ambassadors, chargés d'affaires, high-ranking
    officers of the armed forces;
  - `vii_soe`: administrative, management or supervisory bodies of
    state-owned enterprises;
  - `viii_local`: heads and members of regional and local authorities;
  - `ix_io`: directors, deputies and board members of international
    organisations;
  - `eu`: functions of the European Union's own institutions and bodies;
  - `agency`: heads and boards of national agencies, regulators and public
    institutions not under the clauses above.

Give `reason` in one sentence.
