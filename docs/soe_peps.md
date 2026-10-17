# State-owned enterprise PEPs

A memo on how to model the people who run state-owned enterprises, on
Wikidata and in OpenSanctions. It is open. Decided so far: follow the EU AMLR;
OpenSanctions reads SOE roles through a separate discovery path in wd_peps,
which may go wide; on Wikidata an SOE carries both an ownership chain and a
type marker. The existing paths (peploop's `soe_head` archetype,
OpenSanctions' `se_soe` crawler) are experiments that carry the simplest path
forward, not the model.

## Shape of the work

- **A wd_peps discovery path.** Next to the per-territory and IGO paths in
  OpenSanctions' `datasets/_wikidata/peps/crawler.py`: find enterprises by the
  marker and the ownership chain, read their leadership statements, and emit
  a position per enterprise and role. Position classification is the final
  filter, so the path can take everything plausibly state-owned.
- **pepcorp, a third sweep lane next to peploop and peptree, for enterprise
  profiles** (`peploop/corp/`, spec `peploop/corp/design.md`). Its unit is the
  enterprise: it finds candidates (typed, owned through a `P127` chain, an
  official holdings list, legal forms, parent links), decides each once,
  and writes `P127` or `P749` links, the `P31 Q270791` marker on
  enterprises, and the board seats on
  the body: `P169`/`P1037` for the head, `P5052` for the supervisory body
  (its chair with the role), `P488` for a one-tier board's chair, `P3320`
  role-qualified for the rest; every link is checked against its quote
  before it is written. State institutions
  (museums, broadcasters, research centres, hospitals, agencies) are written
  too, without the marker. Germany is the prototype: federal and Land holdings,
  Landesbanken in, Sparkassen and municipal enterprises later.
- **peploop's part.** When a person's article names them head or board member
  of an enterprise, the statement would go on the enterprise rather than in a
  minted `soe_head` office (open question 1).

## What the rules ask for

- **FATF** (Glossary, Recommendation 12): PEPs include "senior executives of
  state owned corporations", and the definition "is not intended to cover
  middle ranking or more junior individuals". It defines neither "state owned"
  nor "senior executive".
- **EU AMLR** (Regulation 2024/1624, Art. 2(1)(34)(a)(vii)): members of the
  *administrative, management or supervisory bodies* of undertakings
  controlled by the state; also of undertakings controlled by regional or
  local authorities when they are medium or large under Directive 2013/34/EU.
  Control is meant in that directive's Art. 22 sense (parent and subsidiary),
  so a state-controlled group's subsidiaries are in scope. Art. 2(2) repeats
  the middle-ranking exclusion. The UK MLR 2017 reg. 35(14)(g) has the same
  board-level wording without the local branch.

We follow the AMLR. FATF anchors on senior executives; the AMLR makes it
concrete as whole boards (board of directors, executive board, supervisory
board), reaches regional and municipal enterprises above a size threshold, and
covers subsidiaries of a controlled group. Both stop above management below
board level.

## The company problem

In the rest of the OpenSanctions database a `Company` is a legal entity: a
register row with a jurisdiction, a registration number and an address.
Wikidata's company item is a social construct: "Gazprom" is a brand, a group
of about a thousand legal entities and the listed parent PJSC all at once.
Emitting Wikidata's item as an OpenSanctions `Company` tagged `gov.soe` would
put a group where the database expects a legal entity, and it would match and
merge badly against register data (`ru_egrul` has the actual entities).

For PEP purposes the group view is fine: the board members Wikidata lists
under Gazprom are, in practice, those of the parent, which is exactly the
board the rules mean. The mismatch is only in emitting the company itself.

**Option: position without an organization.** OpenSanctions mints a
`Position` named for the role and the enterprise ("Member of the board of
directors, Gazprom"), with country and `gov.soe`, and no `organization`
entity. That is how every other Wikidata position is already emitted: a
Position plus Occupancy, no body entity. The position's id derives from the
company QID and the role, so it is stable across runs. The cost is that the
link to the company exists only in the position's name.

## What Wikidata has (measured 2026-10-17)

**How people are linked to companies.** Over items typed as business,
company, enterprise, public company or state-owned enterprise:

| Link | Statements |
|---|---|
| `P169` CEO, on the company | 28,240 on 5,364 companies |
| `P3320` board member, on the company | 19,952 on 1,432 companies |
| `P1037` director/manager, on the company | 14,154 |
| `P488` chairperson, on the company | 12,252 |
| generic `P39` (board member, CEO, chair…) + `P108`/`P2389` qualifier naming the company | ~3,700 |
| dedicated position items (`P2389` → company) | 86 positions, 814 holders |

`P3320` carries the seat's role in `P2868` (chairperson, deputy chairperson,
treasurer, managing director…). So the convention for company roles is
statements on the company; a position item per company per role goes against
it. The exception is statutory bodies whose seats are public appointments
(central bank boards, regulators, sovereign-fund boards), where position items
are conventional and peploop's `central_bank_governor` and `state_body_member`
archetypes already apply.

**Which companies are state-owned.**

- `Q270791` (state-owned enterprise) types 1,251 items directly and about
  1,000 more through subclasses. It misses flagships: Petrobras, Saudi
  Aramco, Sonatrach, Eskom, Petronas, ZESCO and Ethiopian Airlines lack it;
  Gazprom, Rosneft, Pemex, PDVSA, Codelco and Deutsche Bahn have it.
- The subclass tree is polluted: GDR combines and VEBs, health trusts,
  pedagogic documentation centres. 142 of the directly typed items are
  dissolved (`P576`).
- `P127` (owned by) is the stronger signal: 15 of 18 flagships have one. Its
  values are heterogeneous: the country (Deutsche Bahn → Germany, ZESCO →
  Zambia), a government (Rosneft, PDVSA, Pemex), a ministry or state-property
  agency, a sovereign fund (Aramco → PIF, Sberbank → National Wealth Fund),
  SASAC (CNPC), or another state company (Gazprom → Rosneftegaz). Deciding
  "state-controlled" means walking `P127` to a set of state actors. The share
  qualifier `P1107` is inconsistent (Aramco has both 98.18 and 0.9827), and
  some values are junk (Sonatrach's owner is the class `Q270791`). Petrobras,
  Eskom and Codelco have no `P127`.
- `P127` on sovereign states is mostly not companies: roads, stations,
  paintings and castles outnumber businesses tenfold.

**Leadership data is thin.** Of the 1,251 directly typed SOEs, 42 carry
`P488`, 36 `P169` and 9 `P3320`. Gazprom has three chairs and two CEOs; Eskom,
Codelco, Pemex and Petronas have none. `P108` at SOEs is more common (about
1,350 people at directly typed ones), but its role qualifiers are mostly
researchers and engineers, the trap `institutions.md` describes for
`economic.soe_leadership`.

## Intended pattern

Both a chain of links and a type: `P127` (owner) or `P749` (parent) is the
evidence, and `P31` is a derived marker so an enterprise can
be found with one triple. wd_peps discovery may go wide: position
classification is the final filter, so the marker serves recall and ease of
querying, not precision.

**Type candidates** (measured 2026-10-17):

- `Q270791` state-owned enterprise, "legal entity controlled by a government
  to undertake commercial activities": the national marker. It sits under
  `Q122898840` publicly owned company ("company owned by any public body")
  and `Q17990971` public enterprise.
- `Q1780371` municipal company, a sibling under `Q122898840`: the marker for
  the EU's regional and local branch.
- National subclasses under `Q270791` already exist for some states (China
  `Q124343324`, Indonesia `Q137925492`, Philippines `Q5589413`, Morocco
  `Q121742110`, New Zealand `Q130420294`, Russia `Q4481739`, US `Q48851989`)
  and many national legal forms (French EPIC, Czech státní podnik). An
  instance of one is found through `P279*` like `Q270791` itself.
- `Q270791` is also typed a legal form, and 616 items state it as `P1454`
  (legal form) rather than `P31`; national legal forms under it are used the
  same way (261 VEBs, 84 Norwegian, 83 Czech státní podnik). Discovery reads
  `P31` and `P1454` both.
- `P31 Q270791` is almost never dated (1,253 normal-rank statements, 2
  deprecated, 2 preferred), so privatisation is not recorded on the marker
  today.

The tree's pollution (combines, VEBs, health trusts, central banks under
publicly owned company) is a filter's job, not discovery's.

## Edge cases against the AMLR

Decided: heuristics, not arithmetic. Shares, sizes and control are badly
sourced on Wikidata and a weak place to store them, so no rule computes on
them: there is no size test for the regional tier, and control is the
article's own statement of who owns or runs the body. State institutions stay
in scope (edge cases 1, 3, 6, 7), beside the AMLR's undertakings. Research on
regulator and vendor practice for each case: `docs/research/soe_peps_practice.md`.

AMLR Art. 2(1)(34)(a)(vii) names members of the administrative, management or
supervisory bodies of *undertakings* controlled by the state in an Art. 22
Directive 2013/34/EU relationship, or by regional or local authorities when
the undertaking or group is medium or large (Art. 3(3), (4), (6), (7)); Art.
2(2) excludes middle-ranking officials. The German run of 2026-10-17 writes
on 155 bodies: 52 national and 48 regional enterprises, 20 national and 35
regional institutions; 39 have more than one public owner, and on 9 every
named owner holds under 50 %.

**What counts as an undertaking**
1. State institutions (museums, theatres, research centres, broadcasters,
   hospitals, agencies, foundations) are in OpenSanctions' scope by the
   user's ruling, but not undertakings under (vii).
2. Public-law bodies that trade (Landesbanken, KfW, Bayerische Staatsforsten,
   Anstalten des öffentlichen Rechts): undertakings, with control by statute
   rather than shares.
3. Public broadcasters (ARD broadcasters, ZDF, Deutsche Welle): public-law
   and constitutionally independent of the state.
4. Non-profit companies in state hands (Helmholtz centres: GmbH, 90 % Bund).
5. Foundations: no owner, control through founding statute and board
   appointment.
6. Units of the administration (Landesbetriebe), with no legal personality.
7. Heads of agencies (a federal office, BImA): not in (vii), and near the
   middle-ranking line.

**The control test**
8. Joint control by several public owners, none with a majority (FBB
   37/37/26, Meyer Werft 40/40, Fraport Land 31 % plus city 20 %).
9. A minority stake with dominant influence: blocking minorities, special
   rights, the largest shareholder (Deutsche Telekom ~30 % Bund and KfW,
   Salzgitter 26.5 % Niedersachsen).
10. Indirect control through chains (state holding companies, KfW, Land
    investment companies), and a minority link breaking it.
11. Mixed state and municipal control, and which tier it falls into
    (Komm.ONE: Land 12 %, municipal association 88 %).
12. Temporary state ownership: rescues (Hypo Real Estate, Uniper 99 % since
    2022, SEFE) and privatisation; when PEP status begins and ends.

**Size for the regional and local tiers**
13. Regional enterprises are written with no size check; (vii) requires
    medium or large (Directive 2013/34 thresholds, raised in 2023), at
    entity or group level.
14. The municipal tier, deferred, is the largest by number.

**Bodies and seats**
15. Which bodies are "administrative, management or supervisory": a
    broadcasting council of delegates, a foundation council, an advisory
    board (Beirat), a public-law Verwaltungsrat.
16. Employee representatives on co-determined supervisory boards (half the
    seats in large German companies).
17. Where management ends: Generalbevollmächtigte, division heads,
    Prokuristen, an extended management board.
18. Boards of subsidiaries inside a state group (DB Fernverkehr), and
    group-level versus entity-level seats.
19. Rotating and ex officio chairs (KfW's alternating ministers).

**Time and entity**
20. How long a former board member stays relevant, against the 20-year
    window the run writes.
21. A group on Wikidata against the legal entity whose board the rule means.
22. Foreign SOEs (third-country PEPs), and a state group's foreign
    subsidiaries (DB Arriva).

## Open questions

1. **peploop's `soe_head`.** pepcorp writes seats on the enterprise; peploop
   still mints `soe_head` offices from a person's article. Does it stop, and
   hand the enterprise to pepcorp instead?
2. **Bodies without an owner.** Settled: a subordinate body is linked by
   `P749` to its ministry or government, not `P127`, and found by its
   country's state-only legal forms (the spec's `forms`) or by that parent
   link. OpenSanctions' discovery needs the same two lanes (#5936, second
   amendment pending).
3. **Employee representatives** on co-determined supervisory boards are
   written as plain members. Tag them (a `P2868` role item), later.
4. **OpenSanctions emission.** Position without an organization (above), or
   is there a legal-entity link worth keeping, such as matching the group's
   parent to a register entity instead of emitting Wikidata's item?
5. **Review unit.** Is an enterprise reviewed once ("ZESCO is an in-scope
   SOE") so all its roles follow, rather than each position on its own?
6. **Marker granularity and privatisation.** Write `Q270791` itself, or the
   national subclass where one exists? And when an enterprise is privatised,
   does its marker get an end date (`P582`), unused today, or go?
