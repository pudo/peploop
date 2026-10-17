---
description: Open pepcorp work as of 2026-10-17 — the scope freeze up to the first German batch, person resolution as the biggest recall lever, the EU country specs, parked tiers and seats, and the OpenSanctions crawlers that read pepcorp's output.
date: 2026-10-17
tags: [pepcorp, backlog, soe, institutions, countries, person-resolution]
---

# pepcorp: what is next

The tool as it is: `peploop/corp/design.md`; why it has this shape:
`docs/soe_peps.md`. What was tried: `docs/history.md`. Commands are
`python -m peploop.cli corp <verb>`.

## 1. In flight: the scope freeze

Nothing new until the first German batch has landed and been read back.

Done (2026-10-17): the pre-run cleanup (ministries, governments, branch
offices, the organisation check on category members and its fix for the
polluted type tree); Germany and the Netherlands re-decided; the link check
against each quote (`verify.py`); the pre-send review's fixes (supervisory
chair as `P5052` + role, advisory councils out, control from the article's
words never from share figures, bodies not sites, city-states regional, no
open seat for a dead person, no shortcut links, no ministry as owner, no
polity as parent, corrections removing only `Q270791` itself); three wrong
removal proposals rejected (Deutsche Oper am Rhein, SAGA, Elbe-Werkstätten);
the role item `Q141755781` linked as different from `Q2824523` and part of
`Q897395`.

Left:

1. Recount the run files against the review (no `P488` with `Q15818143`, no
   `P127` to a ministry, no open seat for a dead holder, Deutsche Telekom
   and ABN AMRO without the marker).
2. Precision sample of 20 per country.
3. The four municipal removals awaiting approval (Hallesche Verkehrs-AG,
   Verkehrsbetrieb Potsdam, Bremer Straßenbahn, OOWV): `removals --tool
   pepcorp`.
4. First batch: `corp send de --qid …` for ~10 reviewed bodies (DB, KfW,
   Autobahn GmbH, FBB, dena, Rothaus, Staatliche Kunstsammlungen Dresden,
   Charité, Meyer Werft, Hypo Real Estate); reconcile; read the items live.
   Then the rest of Germany and the Netherlands.
5. The history.md line.

Accepted with the review: undated `P169`/`P488` seats are written when the
article says they are held now, against the constraint asking for a start
date; `P749` raises its inverse-constraint (`P355`) warning on ministries.

## 2. Person resolution: the biggest recall lever

A seat is written only when the article links the person under the exact
name it writes (`rules.linked`: link titles, normalised). The last German
pass left 1,385 seats unlinked against about 1,000 written. A sample of 60
unlinked names:

- 40 % have no human item at all: true residue, as pepcorp creates no people;
- 30 % match exactly one human item by name (Almut Wieland-Karimi,
  `Q2649808`, is named in the ZIF article without a resolvable link), but
  only 1 of 18 such items already mentions the body;
- 30 % match several (homonyms).

Two steps, in order:

1. **Anchor text.** Read the article's links from its Parsoid HTML with their
   anchor text, and match the written name against anchors as well as
   titles. Safe and cheap; catches people linked under another form of their
   name.
2. **Verified unique names.** For a name with no link and exactly one human
   item, one cheap model call showing the item (labels, description, birth
   and death, occupations, employers, positions) beside the article passage;
   only a clear match is accepted, the way peploop's `verify` checks an edit
   against its article. Homonyms stay out unless the same call picks one
   with confidence.

Ceiling: about 400 more German seats. Each accept and refuse class gets a
fixture in `check_rules`; the report counts seats by how their person was
resolved.

## 3. More data back to Wikidata

Where the German funnel loses statements, besides unlinked people (§2):

- **Dissolution dates.** 287 German bodies were found inactive (dissolved,
  merged) and carry no `P576`; the answer already holds the verdict and the
  quote. Cheap, real data, uncontroversial.
- **Official sources.** The federal Beteiligungsbericht and the Länder
  reports name every supervisory board member of each holding; as a second
  source (`P854`) they reach seats Wikipedia never mentions (still bounded by
  person items).
- **History.** 625 German seats ended more than 20 years ago and are left out
  by the PEP cutoff; for Wikidata they are correct facts. A policy question.
- **People without items.** About 40 % of unlinked seats have no human item.
  Creating them is ruled out today; Wikidata's structural-need notability
  might cover board members of notable bodies, a question for the community
  first.

## 4. Countries

- 26 EU specs (`countries/<cc>.yml`) were written by measurement. Holdings
  with QIDs: at ee es fi fr gr hu ie lv; no state-only legal form yet: hr ie
  mt si sk. None has been run.
- Zambia needs a holdings list (the IDC portfolio): its Wikidata has almost
  no state links and its category three members.
- Norway beyond the 30-body trial.
- Some of rigour's alternate QIDs are not the country (Navajo Nation for us,
  Mecca for sa, Bali for id, Nigerian states): a fix upstream in rigour.

## 5. Parked

- The municipal tier, Sparkassen included, with the `Q1780371` marker.
- Employee representatives on co-determined supervisory boards, tagged on
  their `P5052` seat (memo open question 3).
- peploop's `soe_head` minting: hand the enterprise to pepcorp instead of
  minting a head office (memo open question 1).
- Seats written without dates: most `P5052` (68 of 73) and `P488` (80 of
  132) in the last pass. The report counts them; the prompt already prefers
  passages that give the tenure.

## 6. OpenSanctions side

- `wd_soe` (opensanctions#5937) reads lane A (the `Q270791` tree) and lane B
  (`P127`/`P749` to a territory, or to a government body of one, with a
  jurisdiction rule), which matches pepcorp's `P749` → ministry and `P127` →
  polity. Its seat table should carry `Q141755781` (executive board member)
  beside `Q63858690`.
- `wd_peps` (opensanctions#5939) sweeps a territory's current alternate
  QIDs and skips predecessor states; pepcorp follows the same policy
  (`country.current_qids`).
