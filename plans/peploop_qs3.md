---
description: Move peploop's writes (apply, mint, QS export) onto QuickStatements 3.0 through a send mechanism and ledger shared with peptree, and merge peploop's commands from 19 to 14
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
  - The old value matches by exact equality. A year stored as `+1939-01-01T00:00:00Z/9`, the form most imported years have, matches when sent verbatim (QS3 59094/59096, 2026-10-11). A plain line after it with the new value merges our reference into the switched statement: one statement, two references.
- **`ambiguous-statement` is accepted (2026-10-11).** Japan's dry run closed 8 of 367 rows (2.2%) this way, all House of Representatives members with one statement per Diet term. The user chose the skip over remove-and-recreate.
- **Removal:** `-STATEMENT|GUID` is exact. `-Q|P|value` removes only the first of several statements that share the value, so never use it.
- **Errors:** a failed command reports status −1 and its raw line, never the reason. The report CSV returns 403 to a token.
- **The API:**
  - It has no preview step and no maxlag handling.
  - `combine_commands` defaults to false; pass true.
  - Leave out the `wikibase` field.
- **Not tested yet:** `CREATE` + `LAST` (for mint) and the `response_id` that carries the new QID.

## peploop: one send path for both tools, and a smaller surface (approved 2026-10-11)
### Why

peptree writes only through QS3 (commit 319ee0d): `peptree/outbox.py` + `peptree/removals.py`
on `peptree/ledger.py` (`ptree_batch` / `ptree_edit` / `ptree_strike` / `ptree_removal`).
peploop still has three write channels: QS2 chunks pasted by hand (`export`, uncommitted
`peploop/qs.py`), a throttled `wbeditentity` drain (`apply`), and API item creation
(`mint --write`). Its CLI has 19 commands, grown stage by stage.

Goal: QS3 is the only way anything reaches Wikidata, through **one joint send
mechanism with neutral names inside `peploop/`**, used by both tools. Use the
switch to merge the commands that always run together, keeping what a basic
country run needs. QS3 semantics are the measured ones in `plans/peploop_qs3.md`.

Decisions (2026-10-11):
- Joint ledger + sender, neutral names, in `peploop/`.
- peploop adopts **strikes and removals**.
- Date sharpening → **`SWITCH_VALUE`** when the value is unique.
- **Mint stays an ad-hoc peploop function** on the shared send mechanism (`CREATE`, QIDs from `response_id`).
- **One `send` verb in both tools**: additions, then approved removals, as separate QS3 batches.
- **Merge a few commands**, not a single `run` driver. `review`, `prompt` and `audit` stay.
- peptree's side verbs go.
- **No migration of existing peploop runs** (Malaysia `exported`, Japan `accepted`). The one
  data change is renaming peptree's `ptree_*` ledger tables into the joint ones, because a
  sent or struck line must never go out again.

### Command surface after

**peploop: 19 → 14**
| command | change |
|---|---|
| `seed`, `load-positions`, `fetch`, `extract` | unchanged |
| `reconcile` | **absorbs `position-signals`**, which it runs first: signals only fill uncounted rows, so it's idempotent and cheap on re-run |
| `propose` | **absorbs `policy`**: always ends with `policy.run` and the funnel. Re-deciding after a rule change is a re-run of `propose`, which is local |
| `verify` | unchanged (it already re-runs the policy per person) |
| `mint` | **absorbs `mint-categorize`, `mint-verify`, `mint-feed`, `mint --write`**. Dry run: categorize, verify, feed the `found` rows, print the guarded queue. `--submit` sends the `CREATE` batch, binds QIDs, feeds them |
| `send` | **replaces `apply` and `export`**. Dry run: reconcile the ledger, live pre-flight, write `pending.qs`, print routes and skips. `--submit`: one additions batch, then one approved-removals batch. `--status`: the batch table |
| `audit proposal\|candidate` | same verb, but a proposal audit now writes a **strike** on (person, P39, office). It still holds on a re-propose, and on a row that already landed it queues the removal (ours → approved) |
| `removals [approve\|reject <guid…>]` | new, shared with peptree |
| `report`, `review`, `prompt` | unchanged |

**peptree: 13 → 7.** The verbs are `sweep plan|table|run`, `place <cc>`, `audit <n>`, `send [--batch n] [--submit] [--status]`, `strike`, and `removals [approve|reject]`.
- **`place <cc>`** merges `country`, `load`, `repair` and `report`. It is the per-place unit that `sweep run` shells out to, and how one place is re-run after a fix.
- `outbox` becomes `send`.
- `removals submit` folds into `send --submit`.
- `status <id>` folds into `send --status`.
- `migrate_ledger.py` is deleted after the rename.

### Shape

### `peploop/ledger.py` (new; absorbs `peptree/ledger.py`)
- Tables `wd_batch`, `wd_edit`, `wd_strike`, `wd_removal`. These are the `ptree_*` columns plus `tool` ('peploop' | 'peptree'). A batch's op is add, remove or create, and a batch never mixes them.
- `wd_edit.refs integer[]` holds the proposal or candidate ids behind an edit, so peploop can project status back onto its rows.
- The functions move unchanged, each with a `tool` filter: `open_batch`, `bind_qs3`, `close_batch`, `record_edits`, `set_status`, `edits`, `strikes`, `struck`, `strike`, `ours_urls`, `candidates`, `propose_removal`, `decide`, `removals`.
- Schema goes in `peploop/schema.sql`. One `ALTER TABLE ptree_* RENAME TO wd_*` plus `ADD COLUMN tool … DEFAULT 'peptree'`, run once.

### `peploop/send.py` (new; absorbs `outbox.send/recover/reconcile`, `removals.preflight/submit`, the writer lock)
- `send(tool, op, name, rows, log)`: open the batch, record, `qs3.submit`, bind, wait, mark `failed`, reconcile.
- `recover(tool)` finds a lost batch by its unique name. `status(tool)` prints the batch table.
- `reconcile(tool, is_live)`: `is_live` is the tool's own check.
  - peptree: the value is present.
  - peploop: the value **and** the line's qualifiers are present (`qs._carries`), so a `+` spell lands only when that spell is live.
  - create: a QID came back in `response_id`.
- `submit_removals(tool)`: live pre-flight (`send` / `gone` / `moved`), then one remove batch.
- One advisory writer lock per `send` (from `mint_write.writer_lock`), not per country, because a peptree batch spans countries.

### `peploop/qs.py` (rewrite of the uncommitted file): V1 lines, tool-neutral
- **One line per statement**, its references joined with `!S`.
- Routes come from `plan.plan_person`:
  | plan | line |
  |---|---|
  | new / spells-together / value-on-item | a `+` line with its qualifiers and references |
  | preferred | `+…` with `R+` |
  | refine, exactly one live statement holds the value | a plain merge line with only `addable_qualifiers` and the new references |
  | date sharpening, value unique | `SWITCH_VALUE\|Q\|P\|old\|new` |
  | refine, several statements hold the value | policy skip `ambiguous-statement` |
  | Julian or unrenderable value | policy skip `unrenderable` |
- `validate` keeps today's checks and adds three:
  - no `+` line shares (item, prop, value) with a plain line;
  - one `SWITCH_VALUE` per statement;
  - removals only in remove batches.
- `key`, `removal_line`, `validate_removals` and `SUMMARY_RE` move here from peptree.
- `create_lines(candidate)` renders `CREATE` + `LAST|…` from what `offices.entity_data` builds today.
- `qs3.py` gains `commands(batch)` → `(raw, status, response_id)`.
- Deleted: `CAP`, `commands`, `parse`, QS2 `API`, the chunk functions, `record`, `landed`, the `api:` routes.

### `peploop/plan.py`: the planning half of `apply.py`, moved
- Moves: `_snak`, `reference`/`row_sources`/`references`, `same_value`, `addable_qualifiers`, `plan_claim`, `plan_tenure`, `plan_person`, `_qualifier_fingerprint`, `_statement_key`, `_find_guid`, `accepted_rows`, `people`, `preflight`.
- Callers move to `plan`: `propose.py:613`, `offices.py:291`, `qs.py`.
- **`apply.py` is deleted**: the login and credentials code, `maxlag_wait`, `write_payload`, `send`, `create_item`, `find_created`, `log_write`, `record`, `retire`, `apply_person`.
- `retire`'s `apply:<route>` closures become policy skips decided before `send`.

### Policy and statuses (`policy.py`, `propose.py`)
- New skip rules: `ambiguous-statement`, `unrenderable`, and `strike:<by>` (a row whose (person, P39, office) is struck).
- `proposal.status`: `accepted` → `sent` → `applied` | `failed`, written from `wd_edit.refs`.
- `KEPT_STATUSES`, `UNAUDITABLE` and `LIVE_SPELL_STATUSES` gain `sent`. `exported` and `applied` stay as kept, so old rows are left alone.

### Mint (`mint_write.py` shrinks to rows → `CREATE` lines, recover, feed, audit)
`mint --submit` → `send(tool='peploop', op='create', …)` → bind QIDs from `response_id` → `feed`. The holders go out on a later `send`, after `propose`/`verify` sees the new item.

### Docs
- `peploop/countries.md` §3–§5: the stage list with the merges, and `send` in place of `apply`/`export`.
- `peptree/sweep.md` header, and the `peptree/cli.py` docstring.

### Steps (commit locally after each, STOP after each, no push)

1. **Joint ledger and sender; peptree onto them.** Covers `peploop/ledger.py`, `peploop/send.py`, the table rename, peptree's `send`/`place`, and deleting peptree `status`, `ledger.py`, `removals.py` (minus its CLI) and `migrate_ledger.py`.
   - Check: `peptree.check_ledger` and `check_outbox` pass, repointed.
   - Check: a dry `peptree send` writes the same pending lines as `outbox` did before the change (diff the files).
2. **peploop command merges.** `reconcile` ⊃ signals, `propose` ⊃ policy, `mint` ⊃ the four mint commands (still the old write path inside, for now).
   - Check: `check_reconcile`, `check_policy`, `check_propose`, `check_mint*` pass.
3. **peploop rendering and routing, dry.** The `plan.py` split, the `qs.py` rewrite, the policy rules, `send` without `--submit`.
   - Check: a rewritten `check_qs.py` pins every route row and the collision rule.
   - Check: `check_plan.py` (the planning half of `check_apply.py`) passes.
   - Check: a small new country's dry `send` routes everything to QS3, and skips stay under 2% (stop with the counts if not).
4. **Mint `CREATE`.** `create_lines`, `qs3.commands`, recovery by `response_id`.
   - Check: `check_mint_write.py` is rewritten around a fake QS3 (lost answer → `find`; a resend is refused).
   - Then **one real mint**, on your explicit go.
5. **First real peploop `send --submit`**, one small country, on your explicit go.
   - Check: every row is `applied` after reconcile at `max_age=0`.
   - Check: zero duplicate P39s.
   - Check: the EditGroups edit count matches.
6. **Delete legacy and rewrite the runbook.** `apply.py`, the write half of `check_apply.py`, the chunk code, `qs.parse`, the API path in `mint_write`, and the removed CLI commands.

### Verification
- In both packages, every `check_*.py` passes under `/home/pudo/.venv/wrangle/bin/python -m …`, with nothing installed.
- `grep -rn "wbeditentity\|api.php\|wikibase-cli\|csrf" peploop peptree` finds only read paths.
- Live checks are steps 4 and 5. `send --status` should show landed = sent for each batch.

## Loose ends (peptree)

- Australia (sweep batch 65) is `blocked: crash in country`. The query service returned 504s on the `P131` subdivision query in `country.py`; retry it before treating it as a bug.
- `data/peptree/byproducts/held_non_position_p31.md` (63 items) could be imported as `proposed` removals and approved one by one. There is no `import-byproduct` command yet.
- `outbox --propose-reverts` hasn't been run; it would queue the Tonga-bug revert candidates as proposals.
- The auto-mode classifier refuses `outbox --submit` unless you ask for the submit explicitly in that turn.
