---
description: peptree prototype. A sibling of peploop that improves Wikidata position items by filling in the jurisdiction and class on existing offices, and minting the missing ones. It is scored as a country × FATF-category matrix and writes through QuickStatements.
date: 2026-10-04
tags: [peptree, positions, fatf, jurisdiction, quickstatements, prototype]
---

# peptree: prototype

## Goal

This is a small tool that takes one country and makes its PEP positions usable.
There are two cases:

1. **Repair.** Existing position items that lack a country (`P17`), a
   jurisdiction (`P1001`), a class (`P279`) or a position metaclass (`P31`) get
   those statements added.
2. **Fill.** For FATF categories the country has no office for (e.g. central bank
   governor, supreme court judge, auditor general), find the office or create it.

Progress is measured as a matrix: rows are FATF categories, columns are states
(ok / repaired / created / absent / skipped). This is a prototype. The repo's
recipes and research are background reading, not a spec; we take what's useful
and learn the rest by running it.

**The type hierarchy is polluted and will stay polluted.** Mayor makes up 98% of
head of government's subtree, community councillors outnumber national MPs, and
honorary titles and ranks reach `Q4164871` through their `P31` closure (14% of
Belarus's load). No step may assume that a `P279*` walk means anything on its own.
The tool absorbs the noise and improves the hierarchy gradually:
- a category is a set of class handles plus known polluting subtrees (`exclude`)
  plus the bodies its offices sit in;
- the level comes from the jurisdiction (the office's own, or its body's), never
  from the class;
- a load-time filter drops non-offices and generic classes before anything is
  counted. An item with `P31 = Q136649946` (type of position) set directly, at any
  rank, is a class: never a repair or mint target. A country-scoped one, e.g.
  "member of the parliament of Sweden", may still fill its matrix cell when people
  hold it directly;
- every run that meets a new polluting subtree records it in `categories.yml`;
- the repair lane's class fix (pointing a well-formed office at its category
  class) is how the hierarchy gets better, one item at a time.

## Shape

```
load <cc> ─► gaps + matrix ─► LLM: propose & verify ─► rules ─► .qs ─► upload
```

- **`peptree/categories.yml`** lists 13 FATF categories, measured by T1. Each
  entry gives:
  - its class handles (e.g. central bank governor `Q107363151`, prime minister
    `Q14212`, chief of defence `Q5097014`), with counts
  - `exclude` subtrees
  - body classes (e.g. central bank `Q66344`, supreme court `Q190752`)

  Four categories are `unsettled`: supreme audit, SOE executive, security chief and
  central bank board. Their offices are found from the bodies. The file is edited
  as runs teach us.
- **load**: peploop's position discovery and closure, plus one SPARQL lane for
  positions with no country whose holders are citizens of the country.
- **gaps + matrix**: plain code. For each item, list the missing statements;
  for each category, say whether an office exists in the closure.
- **LLM step**: one frozen prompt per job, with schema-enforced output and answers
  cached by content hash (peploop's pattern):
  - *repair*: the model sees the item, its holders and the article lead, and gives a
    value for each missing statement with a quote, or declines.
  - *fill*: the model sees the matrix cell, the country's matching bodies (from
    SPARQL) and candidate items (from search). It answers with one of: an existing
    QID, a new office to create (label, `P279`, body, source quote), "absent", or
    "unclear".
- **rules**: a short ordered rule list in which every case ends applied or
  skipped with a reason, and nothing is queued for review. To start: the model
  must cite a quote. A created office needs a duplicate search that comes back
  empty and at least one named holder. Edits are add-only.
- **write**: render one `.qs` per run, then upload it as one named batch through
  the QuickStatements API under the user's account. New offices use `CREATE`/`LAST`.
  The batch ID and result go in Postgres.

## Write path: the outbox

- **One export path.** `outbox` (`peptree/outbox.py`) reads every place's latest
  run file, subtracts what Wikidata holds now (live, any rank) and what was already
  emitted, and writes the rest into `data/peptree/outbox/chunk-NNN.qs`, at most 300
  QS commands each (a referenced line is two). The user pastes chunks into the QS
  importer by hand. Run files, batches and days are never pasted themselves, so a
  fix that re-renders twenty countries costs only its new statements.
- **Ledger** `ptree_emitted`: one row per emitted statement, keyed on the line
  without its summary and retrieval date. `emitted → landed` when live,
  `→ withdrawn` when neither proposed nor live. An unpasted chunk (nothing landed)
  with a withdrawn line is retired and its other lines re-emitted in a new chunk.
  Landed lines on items the load now drops are listed as revert candidates; a
  wrong class on a kept item is not caught (a landed line closes its own gap).
- **Checks before writing a chunk**: `qs.validate` and the QS parse API (no auth),
  both with 0 errors and ≤300 commands. `status <id>` reads a pasted batch back.
- **Encoding**: give every time value an explicit precision, and pad year and month
  dates with `-00` (`+1990-00-00T00:00:00Z/9`). One reference per line, with
  `!S` to start another. Use TAB and LF separators.
- **EditGroups** tracks each pasted chunk (one summary per chunk), and that is the
  revert path.
- **API submit was removed.** The classic `api.php` submit refused with "Problem
  generating OAuth signature" on every try; QS3 (`qs-dev`) is the one untried
  route if pasting ever becomes the bottleneck.

## Finding created QIDs on a re-run

A compressed `CREATE` is one atomic `wbeditentity`, so no command result holds the
new QID. Discovery of new QIDs is therefore a stage of its own. It runs at the start
of every run, so a run a few hours later picks up what the last one created.

- **Ledger**: every planned office gets a `ptree_create` row before submission,
  with:
  - an **intent key**, a hash of the normalised label, `P279`, `P1001` and the body
  - a short **intent tag**, which goes into the `CREATE` line's edit summary
    (`/* peptree:<tag> */`)
  - the batch ID
  - status `planned → submitted → resolved(qid) | failed`
- **Resolve** (each run, for `submitted` rows):
  1. Read `list=usercontribs&ucshow=new` for the user since the batch was
     submitted, and match the intent tag in the summary. If the summary doesn't
     survive compression, match on label + `P1001` instead.
  2. Otherwise, a live `wbsearchentities` / `haswbstatement` lookup on label + `P1001`.
  3. Otherwise, if the batch is `DONE` with this command in error, mark the row `failed`.
     If the batch is still running, leave the row `submitted`.
- **Cache invalidation**: every read that answers "what does Wikidata hold now"
  uses `max_age=0`. That covers the resolve step, the pre-flight before rendering,
  and the duplicate search before minting. When a batch is `DONE`, cached
  SPARQL, search and entity responses for the batch's subjects and its country's
  discovery queries are evicted. WDQS lags the live site by minutes, so resolve
  never relies on SPARQL.
- **Gate**: a matrix cell whose office is `submitted` but not yet resolved is
  never minted again. A cell resolved to a new QID behaves like any existing item,
  so the repair lane can add to it in the same run.

## Code

- `peptree/` sits next to `peploop/`, with its own CLI, Postgres tables prefixed
  `ptree_`, and no imports from `wd/`.
- It imports peploop's `http`, `db`, `wikidata` and `positions` (discovery and
  closure) directly. If that becomes awkward, we split them out later.
- It does not use peploop's API writer (`apply.py`); writes go through QS.
- Planned modules: `categories.yml`, `load.py`, `matrix.py`, `llm.py`, `rules.py`,
  `qs.py` and `cli.py`. The pilot is Belarus: labels in a non-Latin script, a more
  complex state, and BSSR-era offices to tell apart from current ones.

## First subagent tasks (read-only, nothing written to Wikidata)

These run in parallel. Each one reports its results and stops.

- **T1: draft `categories.yml`.** For about 12 FATF categories, find the class
  QID that is actually used, by counting via SPARQL how many position items reach
  it and across how many countries, and the matching body class. Mark categories
  that have no good class (SOE executive, supreme audit) instead of solving them.
  Output: the draft YAML, with one count per entry.
- **T2: Belarus baseline.** Using peploop's discovery code read-only, plus SPARQL:
  list Belarus's position items, their gaps, and the category × state matrix as it
  stands today. This gives the "before" picture and the size of each lane.
- **T3: QuickStatements upload spike.** Find out how to submit a batch
  programmatically: the classic `api.php` import with username and token, or QS3.
  Cover how to poll status, how `CREATE`/`LAST` and references are encoded, and
  rate limits. No upload. Output: notes plus a sketch of `qs.py`.
- **T4: repair prompt dry-run.** Draft the repair prompt. Run it with the
  Anthropic SDK on about 20 Belarusian items that lack a country or class,
  writing results to scratch only. This tells us whether the LLM step can carry
  the repair lane before we build around it.

The checkpoint after these tasks is to look at the numbers and choose the prototype's
first lane (repair or fill) before writing the tool.
- **T5: LLM search terms.** Make one Sonnet call per country for an institutional
  map: for each FATF category, the office title and body name in the official
  languages and English, plus variants and predecessor names, and whether the
  institution exists. Run every term through Wikidata full-text search and compare
  the hits with T2's SPARQL baseline. Measure the positions the terms find that
  SPARQL missed (especially ones with no country), the positions they miss, and the
  false hits. The terms only generate candidates; nothing the model lists is
  written.
- **T6: Generic P39 targets.** Rank the generic classes that `P39` statements
  point at (minister, member of parliament, mayor…) by statement count and by how
  many countries their holders come from. Separate them from legitimate
  intermediate classes. Draft a Property talk:P39 proposal that adds the top ~100
  to `P39`'s existing none-of constraint (`Q52558054`, suggestion status,
  `P6607` clarifications), and sketch how zavod/nomenklatura would read that
  list. Wikidata has no item-level "generic position" property, so the constraint
  is the existing community home for this list; `Q136649946` "type of position"
  is the matching `P31` metaclass. The user wants the marker on the generic
  item itself, so T6 also drafts a `P5008` ("on focus list of Wikimedia project")
  route: a WikiProject focus-list item that every generic class carries.

  **Preferred route (user decision):** a new "abstract position" item, a
  subclass of `Q136649946` meaning "type of position not tied to any jurisdiction".
  Generic classes gain it as an *additional* `P31`; their `P31 Q4164871` stays, so
  the edit is additive and OpenSanctions' closure is untouched. Country-scoped
  classes (member of the parliament of Sweden) don't get it. Consumers read it
  directly (`p:P31/ps:P31`, any rank). `P5008` and the `P39` constraint are
  fallbacks. Post a community note before tagging at scale.

## Findings so far (2026-10-04)

- **Belarus is mostly repair work.** 849 items loaded; 272 need a country,
  jurisdiction, class or position type; about 7 offices are genuinely missing.
  Several well-formed apex offices don't reach their category class, so the
  class fix is a lane of its own.
- **The repair LLM step works.** On 54 slots Opus made 0 errors (Sonnet 3). The
  misses came from missing candidates. Answers must be candidate indices, not
  free QIDs.
- **The LLM search terms don't help discovery** (about 7 new items from 438 terms).
  Load adds a Soviet-scope lane instead (`P17` = USSR/BSSR). The institution map
  feeds the fill step, which works from bodies.
- **Write path:** classic QS API, parse-before-submit, QIDs recovered on re-run.

## Implementation state (2026-10-04)

- **Belarus written.** Batch 289589 has 297 commands: 189 `P1001`, 72 `P17` and 29
  `P279` statements on 232 items, with 0 errors. It was pasted into the QS UI by
  hand, because the classic API refused with "Problem generating OAuth
  signature" even right after a fresh background batch had run.
- **Writes are pasted by hand**, as outbox chunks (see the write path above).
- **Country config comes from data** (`country.py`). Languages come from rigour.
  Predecessor states come from rigour and `P1365`/`P155`, and their federations
  from `P17`. The gazetteer holds the `P150` units plus second-level units. Level
  words are learned from the country's own offices. `check_neutral.py` forbids
  country QIDs and word lists in code.
- **P31 is held back** unless a sibling or category channel agrees
  (`p31_weak_channel`).
- **The load filter** drops non-offices, bodies, inbound ambassadors,
  occupations, places, legal cases, estates and `generic_positions.csv`.
- **Output**: each run writes `data/peptree/<cc>/<cc>-<date>.qs` (what the place
  would add now) with an `.md` report beside it; only `outbox` turns those into
  paste files.

- **Eras** (fixed after kz/cu/ir): every office has an active span (P571/P576, else
  holder tenures). A country candidate spans from its P571 or its predecessors'
  P576. `era_mismatch` vetoes values that don't overlap, holders count only when
  contemporary, and the model sees the dates. Predecessors are found by walking
  P1365/P155 both ways (Qajar Iran, the US protectorate of Cuba).
- **Label matching** uses whole words with bounded suffixes, aliases, and cities of
  100k+. A name shared with a predecessor is ambiguous and counts as neither
  channel nor conflict.
- **Batches after the fix pass (2026-10-04):** kz 30 lines, cu 36, ir 17, all
  audited live line by line; the only flag is one redundant cu line. Belarus
  replays 270 of 289589's 290 lines with none contradicted.
- **P17 holds only a state** (after the Caribbean runs). A dependent territory
  (Puerto Rico, Cayman, Guadeloupe) is not typed a state, so its own offices get the
  territory in `P1001` and no `P17` at all: the sovereign is not where an overseas
  territory is, and the community is split between the two (Cayman, BVI and
  Montserrat put the territory, Turks and Caicos and Puerto Rico the sovereign).
  Predecessor offices still take `P17` (Netherlands Antilles → the Kingdom).
  `p17_not_a_state` vetoes any non-state value (British Empire). "A state" is a
  direct `P31` in `STATE_CLASSES`, not "its own `P17` is itself": Denmark's and the
  Netherlands' own `P17` name the Realm and the Kingdom.
- **Open:**
  - Kazakh head-last labels never name a category.
  - The P279 candidate pool is generic (no Guardian Council class).
  - P31 is still held back.
  - Should party and trade-union heads carry P1001?
  - Automated QS submission (the OAuth error).
