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

1. Pre-run cleanup, no prompt change: exclude ministries (`Q192350`) and
   governments (`Q7188`) globally (about 120 German ministries come in
   through the agencies category and are always `government`); apply the
   organisation check to category members (17 built structures); in the de
   spec, exclude Landesvertretung bei Bund, Wasserstraßen- und
   Schifffahrtsamt, Dienststelle, Abteilung and Ärztekammer.
2. Commit everything since the push.
3. Re-decide Germany under the final prompt (~$33; the last pass decided
   2,124 bodies at about $0.016 each).
4. Diff against `data/pepcorp/de/baseline-*` on the 20 reviewed bodies:
   authorities linked only by `P749` to a named ministry, local offices
   gone, owners as polity `P127`, no stake-only links, head written once.
5. Precision sample of 40 applied statements; list every proposed marker
   removal for the user (`removals --tool pepcorp`).
6. First batch: `corp send de --qid …` for ~10 reviewed bodies (DB, KfW,
   Autobahn GmbH, FBB, dena, Rothaus, Staatliche Kunstsammlungen Dresden,
   Charité, Meyer Werft, Hypo Real Estate); reconcile; read the items live.
   Then the rest of Germany.
7. The history.md line.

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

## 3. Countries

- 26 EU specs (`countries/<cc>.yml`) were written by measurement. Holdings
  with QIDs: at ee es fi fr gr hu ie lv; no state-only legal form yet: hr ie
  mt si sk. None has been run.
- fr, es and pt list municipal administrations under `not_government`; the
  global jurisdiction rule (a government body governs where its `P1001`
  says) now covers them, so those entries can go.
- Zambia needs a holdings list (the IDC portfolio): its Wikidata has almost
  no state links and its category three members.
- Norway beyond the 30-body trial.
- Some of rigour's alternate QIDs are not the country (Navajo Nation for us,
  Mecca for sa, Bali for id, Nigerian states): a fix upstream in rigour.

## 4. Parked

- The municipal tier, Sparkassen included, with the `Q1780371` marker.
- Employee representatives on co-determined supervisory boards, tagged on
  their `P5052` seat (memo open question 3).
- peploop's `soe_head` minting: hand the enterprise to pepcorp instead of
  minting a head office (memo open question 1).
- Seats written without dates: most `P5052` (68 of 73) and `P488` (80 of
  132) in the last pass. The report counts them; the prompt already prefers
  passages that give the tenure.

## 5. OpenSanctions side

- `wd_soe` (opensanctions#5937) reads lane A (the `Q270791` tree) and lane B
  (`P127`/`P749` to a territory, or to a government body of one, with a
  jurisdiction rule), which matches pepcorp's `P749` → ministry and `P127` →
  polity. Its seat table should carry `Q141755781` (executive board member)
  beside `Q63858690`.
- `wd_peps` (opensanctions#5939) sweeps a territory's current alternate
  QIDs and skips predecessor states; pepcorp follows the same policy
  (`country.current_qids`).
