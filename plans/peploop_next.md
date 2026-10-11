---
description: Open peploop work as of 2026-10-11 — the first live mint, the audit rules Malaysia showed are missing, mint lanes not yet covered, a country tag on the shortlist, and the core consolidation that is still worth doing.
date: 2026-10-11
tags: [peploop, backlog, mint, policy, reconcile, consolidation]
---

# peploop: what is next

The tool as it is: `peploop/design.md`. What was tried: `docs/history.md`.
Nothing here is started.

## 1. The first live `mint --submit`

The QS3 creation path (one batch of `CREATE` + `LAST` lines, each QID read from
its command's `response_id`) is checked offline only. No country has a
`guarded` office now; the next country run that leaves one creates it with
`mint --submit --limit 1` on the user's go, then checks: the item exists with
its labels and claims, the row is `created` with that QID, the send ledger's
`create` edit is `landed`, and the feed reopened its mentions.

## 2. Rules for wrong open tenures

Malaysia's audit found about 9% of open `P39`s wrong and none among closed
ones. Three rules for `policy.py`, each with a case in `check_policy.py`:

- an open seat on a body dissolved after the article's revision (17 Malacca
  seats after the 2026-09-23 dissolution);
- an open tenure read only from a wiki outside the country's languages and
  English (four from id, th, ta or zh were long over or the wrong office);
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

- **One LLM-pass kernel.** Extract, reconcile, verify, titles, mint categorize
  and mint verify each carry their own copy of request, parse, record and
  usage accounting (a seventh in `peptree/repair.py`; `Strict` defined five
  times, `USAGE_KEYS` twice). One `llm.py` plus an `llm_usage` view lets
  `report` show every pass's cost.
- **A check fixture and runner.** Five copies of the shadow-table helper; one
  `checks.py` fixture and a `check` command that runs every `check_*`.
- **Pin every prompt's request hash.** Ledger keys hash the rendered request;
  only reconcile's is pinned, so a refactor that changes rendering by a byte
  silently re-asks a pass.

Not to do: one ledger table for every pass, keying by message hash (re-keys
about $390 of answers), a single `run` driver.
