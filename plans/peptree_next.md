---
description: Open peptree work as of 2026-10-11 — the OECD tail of the sweep, loose ends from sent batches, the never-built fill lane, and the subnational workstream (governed units, their head offices, back-links and a mint queue), all on the QS3 send path.
date: 2026-10-11
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
units to their offices, and turn empty cells into a mint queue.

**What the data says** (measured 2026-10-05):
- 3,084 first-level units in 175 countries. Only 694 carry `P1313`
  (head-of-government office); 124 countries link no head office at all.
- `P150` is not one grain: communes, atolls, villages and electoral units all
  appear at level 1. Sometimes the governed level is the second (Philippine
  provinces link a head on 116 of 119; regions on 1 of 18). Unit types carry
  nothing (3 of 349).
- 5,505 positions are scoped `P1001` to a first-level unit; 648 lack `P17` and
  are invisible to load (103 of them unit heads).
- 168 units have exactly one head office and link none: a mechanical back-link.
- "Head" is two slots where a governor and a chief minister coexist (India,
  Malaysia, Pakistan).
- About 40 countries (Algeria, Vietnam, Dominican Republic, Tunisia, Ghana,
  Ethiopia, …) have governed units and no head office: 700–900 offices to mint.
- Others are minting this layer now (Thailand, Russia, Bulgaria), so a mint
  needs a fresh duplicate search.

**Design.**
1. Choose the level per country from data: the highest level where at least
   half the units are governed, municipal and non-levels excluded; a country
   with none gets a one-call census that must quote.
2. Discovery lanes into `ptree_item` (`kind = subnational`): offices scoped to a
   chosen-level unit, the units' `P1313`/`P1906` targets, and a label search for
   empty head cells (claimless items, e.g. Ghana's regional ministers).
3. Slots: `head_gov` from the unit's `P1313`, else the country's sibling
   convention, else a model pick by index with a quote; `head_state` from
   `P1906` or the second of a pair; `deputy` and `legislator` by label and body.
4. Cell states: `ok`, `unlinked`, `repair`, `unheld` (a peploop job), `claimless`,
   `missing`, `n/a`.
5. Lanes that write, all through `send`:
   - **A** back-link `P1313`/`P1906` on the unit item, on two channels (the
     office's `P1001` = unit, plus the slot evidence). The first lane whose
     subject is a place; `tree/qs.validate` must accept it. A generic class in a
     unit's `P1313` is not removed by the lane — that is a proposed removal.
   - **B** the existing repair lane, reaching unit offices.
   - **C** a search hit the model confirms, repaired through B.
   - **D** mint a `missing` head through peploop's `mint` (as in the fill
     lane); the unit's `P1313` to the new item goes in the next run's lane A.
6. A `## Subnational` section in the country report, and a column in `sweep.md`.

**Phases**, each ending at a checkpoint: (0) a read-only report over ~10
profiles (ng, ph, gh, th, ir, in, ug, az, dz, pf), level choices and the
`head?` residue read in full; (1) discovery lanes and the model slot step, the
matched list read in full; (2) lane A, the first batch read line by line;
(3) lanes B and C; (4) the mint queue as a report, then minting.

**Decisions for the user** (open):
1. The evidence bar for a mint: completing a set (≥50% of the level's units
   have the office) needs only the unit's article quoting it; starting a set
   needs one quoted source for the whole level plus one named current holder.
2. Deputies and legislature members: OpenSanctions types `Q486839` member of
   parliament as PEP but not `Q4175034` legislator, which most provincial seats
   are. Recommended: report both, mint neither until asked.
3. Never score level 2 beside level 1: one governed level per country;
   municipal levels belong to a mayor workstream.
4. Writes to place items (lane A) are a new kind of subject: first batch
   reviewed line by line.
