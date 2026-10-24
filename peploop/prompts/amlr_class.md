You read one row of an EU member state's list of prominent public functions
that names a class rather than one office or one body ("mayors of
municipalities over 50,000 inhabitants", "county presidents", "members of
the boards of state-owned enterprises"). The list was published under the EU
anti-money-laundering rules (Commission notice C/2023/724). You say which
rule over Wikidata items the row stands for, if any. You are told which
levels of governed local unit the state has, and what each level's units
are.

Answer `target` with one of:

- `level`: the row names the head of the executive of every local unit of
  one of the state's levels: the mayor of a municipality or city, the
  president or head of a county, district, province or grouping of
  municipalities, the head of a metropolitan authority. Give `level` as the
  level whose units the row's function heads. Only the head counts: a deputy
  mayor, a member of a council, a council's chair who is not its executive,
  a municipal secretary or director is not the head, and answers `none`. A
  head of a first-level region (a land, a voivodeship, an autonomous
  community, a région) is not a level here: answer `none`.
- `tier`: the row names the boards, management or heads of a class of state
  bodies: enterprises the state (national), a region (regional) or a
  municipality (municipal) owns or controls, or national agencies and public
  institutions. Give `tier` (`national`, `regional`, `municipal`) and
  `bodies` (`enterprise` for businesses, `institution` for agencies,
  regulators and public institutions).
- `none`: anything else: party bodies, courts, international
  organisations, several distinct offices of the state ("ministers", "state
  secretaries"), regional governments, councils, or a row too vague to say.

Also answer what the row names, independently of the target:

- `kind`: `position` (one office), `body` (one named body whose seats are
  the function), `body_class` (a class of bodies or of their offices:
  "mayors", "boards of state-owned enterprises", "directors of state
  agencies", several distinct offices such as "ministers" or "deputy
  ministers" of every portfolio), or `unusable` (a rank, a role with no
  body, an empty or garbled row).
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

Give `confidence` as `high`, `medium` or `low`; `low` means another careful
reader could well answer differently, and a `low` answer expands nothing.
Give `reason` in one sentence.
