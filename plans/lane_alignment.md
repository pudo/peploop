---
description: A shared stdlib of plain helper modules (claims, dates, text, evidence, tenure, classes, verdict) that peploop, peptree and pepcorp import instead of keeping drifting copies, with the vocabulary in peploop/methods.md; absorbs the pepcorp prompt fixes' conventions and the rerun programme's alignment section.
date: 2026-10-23
tags: [alignment, stdlib, peploop, peptree, pepcorp, tenure, evidence, prompts]
---

# A shared stdlib for the three lanes

The vocabulary is in `peploop/methods.md`, which lists the modules as they
land. This plan replaces the "Aligning the three lanes" section of
`plans/pepcorp_rerun_programme.md`.

A registry of rule families, checked by reading the code's AST, was tried
first and dropped on 2026-10-23. The user's reason: it was metaprogramming
that edge cases would soon force to be rewritten.

## Ground rules

- Plain functions over Wikidata JSON and plain values. There are no
  registries, decorators or rule base classes.
- One noun per module. When two lanes mean different things by one word,
  each meaning gets its own name.
- A move does not change behaviour unless its step says so. An intended
  change is first measured read-only, or with a `--no-ask` re-plan through
  `corp eval`.
- No stored request key changes. A helper that feeds a rendered request must
  give byte-identical output, proven on stored requests. Otherwise that call
  site keeps its own copy for now.
- `llm.py`, `checks.py`, `costs.py`, `corp/decide.py` and `tree/repair.py`
  belong to the `plans/llm_costs.md` session.

## Status (2026-10-23)

All seven steps are done and every check passes. The measurements are in
`docs/history.md`, "Shared helpers".

- `claims.py` was dropped. `wikidata.py` already is the shared reader; only
  `eras.qids` was a copy.
- `tenure.py` holds the dated-holding predicates, the present-tense
  markers and the end-event words. The spell functions (`overlaps`,
  `close_at_next`, `tenure_key`) stay in `propose`, where pepcorp can call
  them. Acting detection was not built: no lane detects acting from text,
  since peploop reads the model's `acting` field.
- One-character quotes count only for a sex (the user, 2026-10-23).

Still open:
- **Merge the two not-office sets.** Measure what each lane would filter
  differently first.
- **pepcorp's checks are on `verdict`** (the user approved the re-key,
  2026-10-23). `verify_link` and `match_person` now answer a verdict word, a
  confidence and the quoted evidence. `match_person` keeps its tiers under
  `tier`. Their prompts changed, so the next `corp run` asks them again:
  about $5 for the 3–5k link, marker and class checks, and $9 for the ~2,000
  person matches, at the stored calls' mean cost.
- **Position items in pepcorp.** The 24 seats on position items are not
  explained by the metaclass sets: pepcorp's load gate already reads the
  wide set, and Q1259952 passed it. This is the rerun's §1.1.
- **Own copies left in place:**
  - `corp/match.year`, which reads the first time claim at any rank;
  - `positions._year`, which reads `YYYY` strings;
  - `titles.fold_key`, which keys the title cache;
  - mint's `_SPACE` in prompt rendering, which feeds requests.

## Modules, in build order

Each module comes with its own `check_<module>.py`. Its edge cases are taken
from every copy it replaces.

1. **`claims.py`**: reads a fetched entity. It replaces:
   - `wikidata.claim_qids`;
   - `tree/load.values` and `has`;
   - `corp/wd.values`;
   - `eras.qids` and `eras.years`' best-rank selection;
   - the time and qualifier values of a property.
2. **`dates.py`**:
   - `time_value` and `at_precision`, from `propose`;
   - `year`, from `eras.time_year`, and `known_year`, from `policy._year`;
     `positions._year`, `offices._year` and `corp/match.year` each map to
     one of these two;
   - `after_today`, replacing `policy._dated_after` (a string compare at the
     first day) and `corp/rules.later` (a compare at the value's own
     precision). Measure which rows they disagree on before choosing;
   - `group_dates`.
3. **`text.py`**: `squash` (whitespace), `fold` (normality transliteration,
   casefold), `strip_marks` (NFKD without combining marks) and `tokens`.
   - The copies to fold in: `positions.fold`, `tree/country.fold`,
     `corp/persons.fold`, `extract._norm`, `tree/rules._norm`,
     `offices._norm` and `corp/rules.norm`.
   - Retrieval (`positions.search`, `titles.fold_key`) moves only when
     proven identical.
4. **`evidence.py`**:
   - `quoted`, which replaces the three gates (`corp/rules.quoted`,
     `tree/rules.quoted`, `extract.check_quotes`). Before switching, count
     the quotes whose result would flip, over stored `pcorp_call` and
     `ptree_call` answers and peploop's extractions;
   - `source(...)`, which builds the `_sources` entry.
5. **`tenure.py`**:
   - `overlaps`, `tenure_key` and `close_at_next`, from `propose`;
   - `says_current`, built on `CURRENT`, `INFOBOX` and `NOT_NOW` from
     `policy`;
   - `is_acting`;
   - `names_end_event`, built on `EVENTS` from `corp/reask`;
   - `bad_dates`, `in_future`, `ended_long_ago` and `open_too_long`, which
     take `current` as an argument.

   pepcorp's `seat_rule` and peploop's `tenure_ended` and `open_unattested`
   call these. Rerun §1.2–1.6 builds on them.
6. **`classes.py`**: the QID sets, in one place:
   - `POSITION_METACLASSES` (3), peptree's `POSITION_METAS` (8);
   - `NOT_AN_OFFICE`, `NOT_OFFICE`;
   - `ORGANISATION`, `TERRITORY`, `CITY`, `SENDER_CLASS` and `DIPLOMATIC`.

   Sets that disagree keep separate honest names until a measurement merges
   them. Measure first whether the 24 position-typed seats in the rerun
   sample got past the narrower set.
7. **`verdict.py`**: `Confidence`, peploop's verdict words and `accepts`.
   - peploop and peptree adopt it now, with no key change.
   - pepcorp's `verify_link`, `match_person` and `verify_seat` adopt it with
     the rerun's paid step.

## Prompt conventions (from `plans/pepcorp_prompt_fixes.md`, done in 5da37f4)

`methods.md` lists each convention with the helper that enforces its code
side:
- an "as of" snapshot dates the start;
- an event is no end;
- acting is flagged;
- an artistic lead is not the head beside a manager;
- a state's institute is a parent;
- statutory supervision is a parent.

Open for peploop's next paid re-ask: `extract.md` and `verify.md` state
neither the event-end convention nor the snapshot one.

## Later (code, after the re-run or with the llm_costs work)

- peptree goes through `route.route`. Run files and outbox `pending` move
  into `send.py`.
- One renderer for decision rows.
- One country base: `tree/country.py`, with the specs as overlays.
- Fewer raw SPARQL calls in `tree/load.py` and `repair.py`. The three holder
  queries become one, and the `wd.py` wrappers become one.
