---
description: Move peploop's writes (apply, mint, QS export) onto QuickStatements 3.0, after peptree went first
date: 2026-10-11
tags: [peploop, peptree, quickstatements, qs3, write-path]
---

# QS3 as the single write path

## Where this stands (2026-10-11)

**peptree has moved to QS3:**
- `peploop/qs3.py` is the client:
  - `submit`, `info`, `wait`, `failed` (the raw lines of failed commands), `find` (a batch by name), `link`;
  - the token comes from `QS3_TOKEN` in `.envrc`.
- `peptree/ledger.py` holds the ledger:
  - `ptree_batch` is written before each request, and its name carries the local id so `outbox.recover` can find a lost batch;
  - `ptree_edit` covers op add and op remove;
  - `ptree_strike` holds a reviewer's veto;
  - `ptree_removal` removes by GUID, and stays `proposed` until approved, unless it is the undo of our own edit.
- `peptree/outbox.py` and `peptree/removals.py` are the only two write commands.
- **Live so far:**
  - QS3 59044 (ch, 25 adds) and 59046 (be/dk/no/pt, 174 adds): every line landed and none duplicated. QS3 combined each item's lines into one edit, so 25 lines took 21 edits.
  - QS3 59083: the first removal by GUID (Q50810280 P279), struck in review after the automated submit had sent it.
- `ptree_emitted_old` is the pre-migration table. Drop it once nobody needs it.

**peploop is unchanged.**
- `apply` and `mint` still write through `wbeditentity`.
- `export` (the uncommitted `peploop/qs.py`) still writes QS2 chunks for pasting by hand.

## QS3 semantics: measured on Q4115189, 2026-10-08/09

- **A plain line** merges into the *first* statement with an equal value.
  - It doesn't duplicate a qualifier that's already there, and it de-duplicates an identical reference.
  - Submitting it again makes no revision at all.
  - `/9` dates match `/9` dates exactly.
- **A `+` line** always creates a statement, so two spells of one office stay two. Re-submitting it **duplicates** the statement.
- **References:** several reference blocks go on one line, joined by `!S`. A `+` statement must never be one line per reference: each line would create its own statement.
- **Rank:** `R+` creates a preferred statement.
- **`SWITCH_VALUE|Q|P|old|new`** changes the value in place and keeps the GUID.
- **Removal:** `-STATEMENT|GUID` is exact. `-Q|P|value` removes only the first of several statements that share the value, so never use it.
- **Errors:** a failed command reports status −1 and its raw line, never the reason. The report CSV returns 403 to a token.
- **The API:**
  - It has no preview step and no maxlag handling.
  - `combine_commands` defaults to false; pass true.
  - Leave out the `wikibase` field.
- **Not tested yet:** `CREATE` + `LAST` (for mint) and the `response_id` that carries the new QID.

## peploop: the next session

The goal is to make QS3 the only write path, so `wbeditentity` and hand-pasting go away.

**1. Routing** (`peploop/qs.py:route` / `lines_for`, reusing `apply.plan_person`):

| Today's route | Becomes | Condition |
|---|---|---|
| new statement | `+` line | |
| spells-together | `+` line | |
| value-on-item | `+` line | |
| `api:preferred` | `+…R+` line | |
| refine | plain merge line carrying only `addable_qualifiers` and the new references | exactly one live statement holds the value |
| date sharpening | `SWITCH_VALUE` | the value is unique |

- A refine where several statements hold the value can't be expressed in QS3. It becomes a `skip` rule in `policy.py`, named `ambiguous-statement`, not an API fallback. These skips must stay **under 2% of rows**; above that, stop and discuss.
- `validate` gets a new rule: within one batch, no `+` line may share (item, property, value) with a plain line.

**2. Ledger.** Mirror peptree: open a batch row, record the edits, submit, bind, wait, then reconcile live.
- `+` lines make the ledger load-bearing: a row that has been sent must never go again.
- The decision is whether to reuse `ptree_batch` / `ptree_edit` or keep peploop's `proposal.status` / `applied_batch`.

**3. Mint.** Mint becomes a `CREATE` batch, and `recover()` reads the new QIDs from `response_id`. Test this on one real mint first.

**4. Delete** once one small country's batch is clean, meaning everything landed and there are zero duplicate P39s:
- in `apply.py`: `login`, `_send`, `write_payload`, `create_payload` and the throttled drain;
- `mint_write`'s API call;
- the QS2 `api.php` constants;
- the paste chunk files.

## Loose ends (peptree)

- Australia (sweep batch 65) is `blocked: crash in country`. The query service returned 504s on the `P131` subdivision query in `country.py`; retry it before treating it as a bug.
- `data/peptree/byproducts/held_non_position_p31.md` (63 items) could be imported as `proposed` removals and approved one by one. There is no `import-byproduct` command yet.
- `outbox --propose-reverts` hasn't been run; it would queue the Tonga-bug revert candidates as proposals.
- The auto-mode classifier refuses `outbox --submit` unless you ask for the submit explicitly in that turn.
