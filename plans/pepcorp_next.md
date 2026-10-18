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

First batch landed 2026-10-17: 51 statements on 10 German bodies (QS3
60510, 60511 retry uncombined). Precision samples before it: Germany 20/20,
Netherlands 17/20.

Left:

1. The four municipal removals awaiting approval (Hallesche Verkehrs-AG,
   Verkehrsbetrieb Potsdam, Bremer Straßenbahn, OOWV): `removals --tool
   pepcorp`.
2. Council institutions: where the institution is itself a council
   (Kiesraad, Raad voor het Openbaar Bestuur), its members and chair are
   written as supervisory board members; they are the body, peploop's
   collegial-body positions. A prompt rule for the next round.
3. The rest of Germany (~970 lines) and the Netherlands (179), sent
   uncombined; reload Germany first for the state-chancellery exclusion.

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

- EU-25 and Switzerland: dry run done 2026-10-17/18, nothing sent
  (`data/pepcorp/HOLD` holds every pepcorp send until removed). 3,938 lines
  in `data/pepcorp/<cc>/<cc>-2026-10-18.qs`, 10 marker removals proposed.
  The interim policy calls and the ranked calls for the user are in
  `plans/pepcorp_eu_policy.md`; their answers drive one re-run of all 26
  (prompt and rules changed once, then re-ask), then sends country by
  country.
- Thin countries (sk, si, cy, mt) rest on holdings lists; mt/cy/it/pt
  holdings came from knowledge and an enwiki category, QIDs checked, not
  against the official pages.
- Zambia needs a holdings list (the IDC portfolio): its Wikidata has almost
  no state links and its category three members.
- Norway beyond the 30-body trial; Greenland and Faroe as their own specs.
- Some of rigour's alternate QIDs are not the country (Navajo Nation for us,
  Mecca for sa, Bali for id, Nigerian states, the island of Ireland for ie):
  a fix upstream in rigour.

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
