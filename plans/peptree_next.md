---
description: Open peptree work as of 2026-10-11 — the OECD tail of the sweep, loose ends from sent batches, the never-built fill lane, and the subnational workstream (governed units, their head offices, back-links and a mint queue), all on the QS3 send path.
date: 2026-10-14
tags: [peptree, backlog, sweep, subnational, mint]
---

# peptree: what is next

The tool as it is: `peploop/tree/design.md`; the sweep ledger:
`peploop/tree/sweep.md`. Commands are `python -m peploop.cli tree <verb>`.
What was tried: `docs/history.md`.

## 1. The OECD tail

Pending: ca, us, de, se, gb, it, es, fr, nl. Blocked: au (`crash in country`:
query-service 504s on the `P131` subdivision query — retry before treating it
as a bug). These are the largest position sets (Spain 13,198 items, mostly
per-municipality mayoralties, plus bishoprics and nobility titles); the repair
asks only about held or categorised offices. Overseas territories follow the
territory rule (`P1001` only, no `P17`). The Netherlands has Denmark's
problem: rigour's code names the Kingdom; check which state its offices put in
`P17` before running.

## 2. Loose ends

- **Revert candidates.** `send --propose-reverts` has never been run; it
  queues every landed line on an item the load now drops as a proposed removal
  for `removals approve`.
- **63 held offices with a wrong `P31`** (a family name, human, a title) are
  listed in `data/peptree/byproducts/held_non_position_p31.md`. Import them as
  proposed removals (an `import <file>` action on peploop's shared `removals`),
  then approve one by one.
- **Kazakh labels** put the head noun last; the label channel misses them.
- **The filter is half of one office loader.** peploop's `position` set and
  peptree's kept items disagree (jp: peptree drops 410 of 2,977); the shared
  loader is `plans/peploop_next.md` §6, and changes to `load.py`'s filter feed
  into it.

## 2b. Generic roles: what the first pass left open

The repair's `scope` answer and the `generic_position` table are in; the
2026-10-13 pass over landed `P17`s listed 17 roles and took back 14 `P17`s
(QS3 59521). Open:

- **No real run has exercised the writer.** `record_generic` is pinned by
  checks only. The prompt change re-keys the cache, so each country's next run
  re-asks every item; `tree place --no-ask` on old answers skips every
  `P17`/`P1001` (no scope answer).
- **`P1001` never audited.** Only landed `P17`s were re-asked.
- **Our own `P17` hides an item from the load.** An orphan we gave a country
  leaves the orphan lane and no other lane takes it; the five Swedish roles
  were missing from the reload and needed `tree strike`. The load should also
  take items whose only `P17` is ours.
- **Kept as offices, worth a second look:** Q110299985 kommunalordförande,
  Q3742121 slottsfogde, Q10658478 räntmästare, Q131323581 Rainha de Bateria,
  Q139303992 (ng) Commissioner for Women Affairs and Poverty Alleviation.
- **Q11870945 Fältprost** keeps our `P31 Q294414` (public office); a generic
  chaplain role is arguably no office of the state.
- **Classes of local office** ("mayor of a place in X"): own `P17`, ≥10 direct
  subclasses with distinct `P1001` making up half its subclasses, holders
  ignored: about 224 candidates at ~90% precision (QLever, 2026-10-13). A
  feeder for "type of position" typing and for the scope question, not for
  the generic list. False positives are "member of <legislature>" with a
  subclass per constituency.
- **P39s filed on such a class:** 22,905 holders on 146 one-country classes;
  about 1,400 `P1001`-qualified statements have a matching subclass to move
  to (Landrat 356 of 467). Czech, Hungarian and Swiss mayors use the
  qualifier by convention and stay.

## 3. The fill lane

peptree repairs offices it finds; it creates none. For a FATF category a
country has no office for (central bank governor, supreme court judge, auditor
general), find the office or create it. Creating it is peploop's `mint` with a
different queue: the archetype shapes and `guard` (`offices.py`), the live
duplicate search, and the crash-safe `CREATE` batch with its feed back
(`mint_write.py`) all apply as they are. What is new is the queue builder --
empty category cells from the matrix, each with at least one named holder --
and any archetype a category lacks. Not designed further than that.

## 4. Subnational: one level down

Score every country's governed subnational units × {head of government, head
of state, deputy, legislature member}, find the offices load cannot see, link
units to their offices, and mint the empty cells.

**What the data says** (measured 2026-10-05):
- 3,084 first-level units in 175 countries. Only 694 carry `P1313`
  (head-of-government office); 124 countries link no head office at all.
- `P150` is not one grain: communes, atolls, villages and electoral units all
  appear at level 1. Sometimes the governed level is the second (Philippine
  provinces link a head on 116 of 119; regions on 1 of 18).
- 5,505 positions are scoped `P1001` to a first-level unit; 648 lack `P17` and
  are invisible to load (103 of them unit heads).
- 168 units have exactly one head office and link none: a mechanical back-link.
- "Head" is two slots where a governor and a chief minister coexist.

**What a run down to local government established** (Australia, 2026-10):
- **Places, not people, reach the local level.** Person articles minted about
  15 local offices; the units' own articles 498 (`mint_units`, a `per: units`
  census entry). Start from the units; the person lane feeds holders onto
  what exists.
- **One office item per unit and role:** `P1001` the unit, `P361` its council
  (the unit's `P194`), and the unit's `P1313` naming the head office. A
  provincial seat sits in its own province's cabinet. Titles repeat across
  polities, so sibling measures and duplicate checks are per polity.
- **Coverage is regional:** one subdivision near complete, the next empty.
  Completing or starting a set is decided per subdivision.
- **Unit lists carry the dead.** Units come from a class (`P150` stops at the
  first level), and many defunct ones have no `P576`; the unit's article is
  the check.
- **Local currency is weak evidence.** Infoboxes are undated, so the office
  rests on a level-wide source; local open tenures go stale fast.

**Settled:** the mint evidence bar is a named current holder in the unit's own
article, plus a source for the whole level where fewer than half the
subdivision's units have the office. Municipal levels are minted through
`per: units`, not a separate workstream.

**Open:**
- **Lane A, the back-link,** is built for the EU's ≥50k units
  (`tree backlink`). Open: extending it beyond the AMLR unit set, the units
  whose `P1313` names a generic class or a shared office (proposed removals,
  not the lane's), and the 871 units with no head office, which a re-run
  links once `mint_units` has made their offices.
- **The governed level per country**, from data: the highest level where at
  least half the units are governed, municipal and non-levels excluded.
- **Discovery lanes** into `ptree_item` (`kind = subnational`): offices scoped
  to a chosen-level unit, the units' `P1313`/`P1906` targets, and claimless
  head items found by label.
- **Deputies and legislature members:** OpenSanctions types `Q486839` member
  of parliament as PEP, not `Q4175034` legislator, which most provincial seats
  are. Report both, mint neither until asked.
- A `## Subnational` section in the country report and a column in `sweep.md`.
