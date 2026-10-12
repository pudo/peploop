---
description: Open peploop work as of 2026-10-12 — the audit rules Malaysia showed are missing, mint lanes not yet covered, a country tag on the shortlist, the consolidation still worth doing, and one office loader for both lanes.
date: 2026-10-11
tags: [peploop, backlog, mint, policy, reconcile, consolidation]
---

# peploop: what is next

The tool as it is: `peploop/design.md`. What was tried: `docs/history.md`.
Only §5 is started: `llm.py` holds the first part of the LLM-pass kernel.

## 1. The first live `mint --submit` — done

Congo (2026-10-12) created four offices through QS3 (59322, 59339, 59348), each
checked live, rows `created`, edits `landed`, mentions fed. Combined creation
batches failed whole, so creations now go out uncombined.

## 2. Rules for wrong open tenures

Malaysia's audit found about 9% of open `P39`s wrong and none among closed
ones. Three rules for `policy.py`, each with a case in `check_policy.py`:

- an open seat on a body dissolved after the article's revision (17 Malacca
  seats after the 2026-09-23 dissolution);
- ~~an open tenure read only from a wiki outside the country's languages and
  English~~ -- done, `minor_wiki_only/open` (Somalia, 2026-10-12);
- an open chamber seat whose new term is on record with too few starters to
  make the cohort (Somalia's Upper House: one 2022 senator against 2016-17
  seats);
- an open ambassadorship the same person's later posting ends, when the later
  post has no item to propose it on;
- an open tenure on a term item that has a successor.

## 3. Mint lanes not yet covered

- **Bilateral ambassadorships** are refused (`offices.bilateral`); every
  country has dozens of unplaced "ambassador of X to Y" mentions.
- **Subnational cabinet seats** have no archetype (Malaysia: 418 groups,
  `archetype/none`).
- **Deputy ministers** without a national class to shape them.

Each needs an archetype in `offices.py` with its shape measured first
(`docs/research/position_items.md` is the template), and a case in
`check_mint.py`.

## 4. The candidate's country on the shortlist line

Homonym offices of other states (a Spanish "mayor of Chía" offered for
Colombia) reach the shortlist with nothing on the line saying whose they are.
Add the state to `Candidate.line` and bump `RENDER_VERSION` to 3. That re-keys
every reconcile answer, so re-ask only refusals and `wrong-office` verdicts,
not the whole ledger (a full re-ask is about $140 over eight countries).

## 5. Consolidation still worth doing

Do these when the files are open anyway; none changes behaviour.

- **The rest of the LLM-pass kernel.** `llm.py` holds the client, the prompt
  hash, the usage counts and the prices; each of the seven passes (six here, one in
  `tree/repair.py`) still carries its own request, parse and record, `Strict`
  is defined five times and `USAGE_KEYS` twice. An `llm_usage` view over the
  ledgers would let `report` show every pass's cost.
- **A check fixture and runner.** Five copies of the shadow-table helper, and
  peptree's eight checks carry their own `expect` beside peploop's seventeen;
  one `checks.py` fixture and a `check` command that runs every `check_*` of
  both lanes.
- **Pin every prompt's request hash.** Ledger keys hash the rendered request;
  only reconcile's is pinned, so a refactor that changes rendering by a byte
  silently re-asks a pass.

Not to do: one ledger table for every pass, keying by message hash (re-keys
about $390 of answers), a single `run` driver.

## 6. One office loader for both lanes

peploop (`positions.discover` → `position`) and peptree (`tree/load.py` →
`ptree_item`) each find a country's offices with their own queries, holder
counts and not-an-office lists, and they disagree. Of peploop's `position` rows
for a state, peptree's filter drops jp 410 of 2,977 (173 not an office, 81
occupation, 79 inbound ambassador, 62 body), my 290 of 710, by 110 of 646, and
about half for the small Caribbean runs. So reconcile can resolve a mention to
an item peptree has ruled out, an inbound ambassadorship among them.

One loader and one filter would fix that, with peptree's lanes as the richer
half: it knows predecessor states, realms and eras, which peploop's
`country_qid` does not. Share the country model (`tree/country.py`) with it, so
reconcile and `mint` see predecessors too. This changes which offices peploop
resolves against: measure the shortlist and proposal diff on two finished
countries before switching.

The two lanes also fold names differently: `positions.fold` transliterates to
ASCII, `tree/country.fold` strips diacritics (NFKD), and each has its own
`tokens`, so the same Cyrillic or Greek title compares differently in each.
Pick one with the loader, measured on the same diff, since it moves matches in
whichever lane changes.
