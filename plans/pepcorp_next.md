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
   Verkehrsbetrieb Potsdam, Bremer Straßenbahn, OOWV) were withdrawn by
   the de run of 2026-10-25: Germany now writes the municipal tier, where
   the correction rule does not fire, and these bodies keep `Q270791`. The
   user decides whether a written tier should still swap `Q270791` for
   `Q1780371`; the rows are saved in the session scratchpad.
2. Council institutions: where the institution is itself a council
   (Kiesraad, Raad voor het Openbaar Bestuur), its members and chair are
   written as supervisory board members; they are the body, peploop's
   collegial-body positions. A prompt rule for the next round.
3. The rest of Germany (~970 lines) and the Netherlands (179), sent
   uncombined; reload Germany first for the state-chancellery exclusion.

Accepted with the review: undated `P169`/`P488` seats are written when the
article says they are held now, against the constraint asking for a start
date; `P749` raises its inverse-constraint (`P355`) warning on ministries.

## 2. Person matching: the biggest recall lever

A seat is written only when the article links the person (`rules.linked`).
Since 2026-10-18 a name resolves through a link's title or its anchor text,
with titles and degrees after the name dropped ("JUDr. … , Ph.D.").
What is left is people the article does not link at all: about 4,900 seats
in the EU + Switzerland dry run (fr 650, es 489, pl 418, it 314, at 297, ch
296, se 288, ro 271, fi 225, be 202 …) beside ~1,500 written, and 1,385 in
the last German pass. Greek and Maltese boards are almost never linked.

A German sample of 60 unlinked names: 40 % have no human item (residue:
pepcorp creates no people), 30 % match exactly one human item by name, 30 %
several (homonyms). Agent samples in the EU run found the same: people with
items the article leaves as plain text or red links (Simone Quilici, Rui
Santos Ivo, Michela Spagnuolo, Almut Wieland-Karimi).

The step: **verified unique names.** For a seat whose name the article does
not link:

1. Search human items (`P31 Q5`) by exact label or alias in the article's
   language and `mul`, after `rules.norm`; keep the name only when one
   item matches.
2. One cheap model call shows that item (labels, description, birth and
   death, occupations, employers `P108`, positions `P39`, citizenship) beside
   the article passage that names the seat; accepted only on a clear match,
   as peploop's `verify` checks an edit against its article.
3. Homonyms (several items) stay out, unless the same call picks one with
   confidence from the item details; a living-person check (`holder_dead`)
   and the date rules apply as for linked people.

Each accept and refuse class gets a fixture in `check_rules`; the report
counts seats by how their person was resolved (link, anchor, matched). The
statement keeps the article as its reference; the match itself is an
inference and carries none. Ceiling, by the sample: about a third of the
unlinked seats, ~1,500 in the EU run, ~400 in Germany.

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

- EU-25 and Switzerland: dry run done 2026-10-17/18, nothing sent. 3,938
  lines in `data/pepcorp/<cc>/<cc>-2026-10-18.qs`, 10 marker removals proposed.
  The interim policy calls and the ranked calls for the user are in
  `plans/pepcorp_eu_policy.md`; their answers drive one re-run of all 26
  (prompt and rules changed once, then re-ask), then sends country by
  country, with the user.
- Thin countries (sk, si, cy, mt) rest on holdings lists; mt/cy/it/pt
  holdings came from knowledge and an enwiki category, QIDs checked, not
  against the official pages.
- The AMLR listed lane (2026-10-24): built and dry-run on mt, ro, dk, lt,
  pl, ee, sk and cz. The list alone admits 42 bodies and adds 19 seats
  (ro 3, dk 9, lt 7), nothing sent. Left:
  1. Send those 19 seats with the user, as one tranche limited with
     `corp send <cc> --qid` to the bodies the list alone admits.
  2. The residue is the list itself: 362 named-body rows in these eight
     countries resolve to no item (ro 103, mt 93, lt 59, dk 48), many of
     them Romanian and Maltese bodies with no item or article. Another
     `amlr expand` pass, or hand entries in the asset, comes before pepcorp
     can use them. 26 listed bodies have no article and stay out by the
     article gate.
  3. Open interim calls: a body its articles call private is not admitted
     by the list; a body the list alone admits gets no statutory class;
     the other 19 countries are run only when their next re-run comes.
  4. Body-class cross-check: Portugal lists municipal enterprises, a tier
     its spec does not write (the municipal workstream); the Netherlands
     says it has no state enterprises under the definition, while its spec
     writes them under the AMLR default.
- Party governing bodies (2026-10-25): the `party` and `party_branch`
  lanes, built and dry-run on de, es and nl, nothing sent: 701 party seat
  lines (de 480, es 192, nl 29). Left:
  1. Send with the user, as tranches limited with `corp send <cc> --qid`
     to the party bodies: per country, `P488` and `P3975` first (the
     convention's own idioms, mostly current), then the `P3320` deputies,
     treasurers and members.
  2. The other EU countries: each needs its `party_branch_classes`
     measured (fr, it, pl branches are hardly modelled, so the national
     parties alone), and a run limited to party bodies.
  3. Open interim calls: a local branch is not written until the AMLR's
     local tier (2027) has a unit population check; a party's organ as an
     item of its own (its presidium) gets nothing, its seats go on the
     party; youth wings, foundations and alliances with no membership are
     out; a member's seat counts as held when open and started within
     twelve years; a party is read in English only where it has no
     own-language article.
  4. OpenSanctions does not read parties yet: `wd_soe` reads state
     bodies only. A party lane reading `P488`, `P3975` and `P3320` on the
     country's parties is the crawler side of this.
- The municipal tier (2026-10-25): built and dry-run on de, nothing sent:
  249 municipal bodies passed, 300 lines on 193 bodies (117 `Q1780371`,
  101 `P127`, 78 seats). Left:
  1. Send with the user, as two tranches limited with `corp send de
     --qid`: the 57 bodies with seats (116 lines), then the 134 with only
     a marker and links (180 lines). Re-plan de first once QLever answers:
     the last fix (a region beside a leading city) is not in the run file.
  2. A city's departments (Kulturreferat) pass as institutions; the
     prompt's government kind should name a municipality's departments.
  3. The other countries: pl, es, it, at, nl, be, cz, pt each need their
     `municipal_classes` and categories measured, and a run limited to the
     new bodies (`reask` picks the old answers the prompt change affects).
  4. Open interim calls: Sparkassen and hospitals stay out; joint
     ownership by several municipalities passes the gate but its links
     still need the verify check, which reads joint carriers as owning
     none; an owner named unlinked resolves to a unit by its label or
     its label after one word; a unit is found through a named
     controller's jurisdiction or owners up to two steps.
- Zambia needs a holdings list (the IDC portfolio): its Wikidata has almost
  no state links and its category three members.
- Norway beyond the 30-body trial; Greenland and Faroe as their own specs.
- Some of rigour's alternate QIDs are not the country (Navajo Nation for us,
  Mecca for sa, Bali for id, Nigerian states, the island of Ireland for ie):
  a fix upstream in rigour.

## 5. Parked

- Sparkassen in the municipal tier (152 in German ≥50k units).
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
