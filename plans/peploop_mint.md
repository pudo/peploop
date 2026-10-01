---
description: Unsupervised position-minting stage for peploop — aggregate missing offices per country, categorize + verify with two LLM passes, create via the API, feed back into reconcile. First target Cuba.
date: 2026-10-01
tags: [peploop, positions, minting, cuba, wikidata-write]
---

# peploop: minting missing position items

## Context

Cuba was scoped (`peploop/countries.md:246-264`, `seeds/cu.yml`) but not run. The
scoping found that much of the coverage gap is offices with no Wikidata item:
- the Council of State, Central Committee and Politburo memberships;
- the Second Secretary;
- 14 of 15 provincial governorships;
- the apex court president;
- the chief of the general staff;
- the heads of state enterprises.

peploop records unplaced offices only as `resolution` rows with `qid IS NULL`
(`positions.md:319` says "a count, not a queue"). Nothing turns those rows into
items. This adds a stage between `reconcile` and `propose` that does five things:
1. collects candidate offices from two sources, the reconcile misses and a
   per-country census;
2. categorizes them and drafts each item's shape (LLM pass 1);
3. verifies that each office is real, current, missing and correctly shaped
   (LLM pass 2);
4. creates the items that pass, through the action API;
5. reopens the affected mentions, so their P39s get proposed.

**Fixed decisions (user):**
- Candidates come from the reconcile misses and a census against
  `recipes/institutions.md`, merged. A census-only office still needs
  attested holders.
- Evidence bar: at least 2 *distinct people* and at least 1 current holder. A
  one-seat-at-a-time office passes with 1 current holder plus a checked
  official source.
- **Unsupervised, like the rest of peploop.** An item is created when
  categorize, verify and the mechanical guard all agree. A disagreement is a
  **skip with a recorded rule**, never a review row. The flagged rows become
  an export list (`mint-report`), the same way `conflict` rows do. A
  disagreement class that recurs becomes a new rule in `disposition()`. A
  human may audit after the fact and skip (`audit:<by>`, as on Colombia), but
  nothing waits on a human. The runtime has no gate. The only stops are
  development checkpoints, while the stage is being built and first run.
- The ruling party's national organs are in scope: organ seats and party
  offices. Party *membership* stays P102.
- **peploop imports nothing from `wd/`** (`design.md:9`). `wd/` is R&D and
  peploop is heading to daily production. Knowledge from `wd/create.py`,
  `wd/shape.py` and past mints is *ported, trimmed* into peploop, and the
  mechanics are left behind:
  - no `wb create-entity`;
  - no JSON ledgers;
  - no "paste `target=` back into the script".
- Code is shared with the person loop by reusing peploop's own modules. No
  generic "pass" framework.

## Design

### Reuse (existing peploop, unchanged)

| Module | Reused |
|---|---|
| `db` | `conn`, `init_schema` |
| `http` | `get_json(max_age=0)`, `post` |
| `wikidata` | `fetch_items`, `best_label`, `claim_qids`, `claim_time` |
| `positions` | `country_qid`, `type_closure`, `POSITION_METACLASSES`, `NOT_AN_OFFICE`, `fold`, `tokens`, `search`, `fill_diplomatic` |
| `reconcile` | `client`, `Strict`, `Candidate`, `candidates_for`, `render_shortlist`, `mention_from`. LLM calls keep the same pattern: prompt file + sha + `RENDER_VERSION` + pydantic `messages.parse` + a Postgres ledger keyed on what was shown. |
| `apply` | `login`, `csrf_token`, `_api`, `maxlag_wait`, `editgroup`, `log_write`, `_snak`, `THROTTLE` |
| `propose` | `propose_person` |
| `cli` | `country_option`, the threadpool and line-per-row output |

### Small changes to existing modules
- **`positions.py`:** split `load_country` into `discover` + `load_items`. Add
  `load_qids(qids, source="minted")`. `upsert_position` unions `sources`
  instead of overwriting them.
- **`reconcile.py`:** add `reopened_for` (column plus a new unique index that
  replaces the old 4-column key). Add `reopen(...)` and `retrievable(...)`.
  `RENDER_VERSION` and `reconcile.md` stay untouched, so nothing else is
  re-asked.
- **`apply.py`:** factor the current `send` body into `_send`. Add
  `create_item(data, summary, token)` (`wbeditentity new=item`, `assert=user`,
  maxlag, editgroup in the summary). Add `find_created(tag, since)`, which
  reads `usercontribs` and is authoritative immediately.
- **`cli.py`:** new commands (below). `stats` gains a mint section.

### New modules
- **`peploop/offices.py`:** the ported knowledge, mostly pure.
  - `ARCHETYPES`: minister, legislator, judge, supreme_judge, governor, mayor,
    agency_head, central_bank_governor, prosecutor_general, plus new ones:
    party_organ_member, state_body_member, party_secretary,
    military_chief_of_staff, court_president, soe_head. Parents for the new
    ones come from step S0.
  - `Spec`, `entity_data` (no references on structural claims), and
    `describe` (resolved labels only; a QID in text is refused).
  - `siblings(state_qid)` → `metaclass_for` / `parent_for`. Shape follows the
    country's own offices. The fallback is `Q294414`, the modal metaclass.
  - `live_lookup` (`wbsearchentities` + CirrusSearch `haswbstatement`, all at
    `max_age=0`) → `duplicate_of`.
  - `shape_defects` and `guard(...)`, which checks:
    - labels and the distinct-holder floor;
    - currency;
    - a live duplicate search per label and alias, plus duplicates within
      the run;
    - the body: it resolves, is not a position, shares a word with the
      office label, and has the right P17;
    - that P1001 is in the state;
    - that the office is not the body itself;
    - shape;
    - that it is not a bilateral post.
- **`peploop/mint.py`:**
  - The queue: `unplaced`, `is_current`, `group_key` and `groups`; `census(cc)`
    from `peploop/census/<cc>.yml`, with `per: subdivisions` expanded over a
    live P150 read; and `floor()` before any tokens are spent.
  - **Categorize** (Sonnet, `prompts/mint_categorize.md`):
    - clusters the groups into offices and assigns an institution class and
      archetype;
    - drafts labels in the country's languages plus en, the P279, the body,
      P1001 and P1365;
    - may only use QIDs from the lists it is shown;
    - gives every group exactly one disposition.
  - **Verify** (Opus, a different model on purpose; `prompts/mint_verify.md`):
    one office per request. It is shown the attestations in full, the live
    duplicates, the whole country index and the sibling tallies, and answers
    `mint|exists|not-an-office|not-current|not-distinct|generic-convention|unclear`
    plus shape corrections.
  - `disposition()`: ordered rules in the style of `policy.py`:
    1. census office with no attestation → skip
    2. bilateral post → skip (`diplomatic/deferred`)
    3. below the evidence bar → skip; neither model can override this
    4. categorize refused it → skip
    5. live duplicate or `verify:exists` → `found`
    6. all three agree → `guarded`
    7. otherwise → `skipped` with `rule=disagree/<first problem>` and
       `problems[]` kept. This is the conservative default; nothing is
       relaxed to raise the count.
  - `mint_one` (crash-safe):
    1. lock the row and re-run the guard live;
    2. write `status=creating` + `intent_tag` and commit;
    3. call `create_item` with the tag in the summary;
    4. record the QID.

    `recover()` resolves rows left in `creating` through `find_created`.
  - `feed()`: for each created or found item:
    1. `load_qids`;
    2. `fill_diplomatic`, leaving `holders_by_country` null so the item is
       not tagged `unheld`;
    3. `retrievable` per attestation;
    4. `reopen` only the mentions the item was clustered from;
    5. `propose_person` for the affected people.
- **Schema** (`schema.sql`, idempotent):
  - `mint_call`: the LLM ledger, keyed by pass, content, prompt hash, render
    version and model;
  - `office_candidate`: ref, origin, class, archetype, draft, corrections,
    spec, data, distinct and current holder counts, source, status, rule,
    problems, qid, intent fields;
  - `office_attestation`: candidate ↔ resolution/person, plus current,
    retrieved, reopened_id;
  - `office_unassigned`;
  - the `resolution.reopened_for` column and index swap.
- **`peploop/census/cu.yml`:** institution anchors with body QIDs and official
  sources, written *after* S0 so they come from measurement, not memory.
- **`peploop/check_mint.py`** + `fixtures/mint_cases.jsonl`: one pinned case
  per gate, rule and state transition. `check_reconcile` and `check_apply`
  gain cases too.

### CLI (slots into `countries.md` §3 between `reconcile` and `propose`)
```
mint-categorize --country cc [--census …] [--dry-run]
mint-verify     --country cc [--limit N] [--threads 4] [--dry-run]
mint            --country cc [--limit N] [--id …] [--write]      # dry by default
mint-feed       --country cc [--id …]                             # idempotent
mint-report     --country cc [--out data/mint/cc.md]              # funnel by rule, the skip export list, cost by stage
mint-audit      --id N --skip --reason … --by NAME                # after-the-fact skip only (audit:<by>); no approve path
```
In steady state, `mint-categorize → mint-verify → mint --write → mint-feed`
run back to back as one runbook step, and the funnel number is shown first.
During the first runs (Cuba, then a second country), development checkpoints
stop after `mint-verify` and after `mint --write --limit 1`. An observer
agent reads the skips and the guarded rows. Each class it finds wrong becomes
a rule, never a per-row decision.

## Implementation steps (one subagent each; stop and report after each checkpoint)

- **Step 0.** Copy this plan to `plans/peploop_mint.md` in the repo, keeping
  the frontmatter.
- **S0. Measure. No code.**
  - P279 and P31 tallies, and exemplars read in full, for: Politburo, Central
    Committee and Council of State member; second secretary; chief of general
    staff; court president; SOE director.
  - Cuba's sibling shapes, about 50 own offices.
  - Results go to `research/position_items.md`.
  - **Checkpoint:** show the parent choices.
- **S1. `offices.py`, pure half**, with `check_mint` cases:
  - rows vs people;
  - the one-seat source exception;
  - a QID in a description;
  - the body word check;
  - bilateral refusal;
  - payload shape;
  - metaclass fallback.
- **S2–S5, in parallel:**
  - **S2.** Live lookups and siblings, checked against Q1370482 and with no
    `http_cache` writes.
  - **S3.** The `positions` split and `load_qids`, checked by a rerun of
    `si` that gives the same counts.
  - **S4.** Reconcile `reopened_for`, `reopen` and `retrievable`, checked by
    `check_reconcile`/`check_propose`.
  - **S5.** `apply.create_item` and `find_created`, checked by `check_apply`
    payload pins and a `usercontribs` fixture.
  - **Checkpoint** after these.
- **S6.** The queue, census loader, floor and schema tables. Check by reading
  `unplaced` on `co` and eyeballing the groups.
- **S7.** The categorize pass: prompt, settle, ledger, supersede. Check with
  `check_mint`, then `--dry-run` on `co`.
- **S8.** The verify pass and the disposition rules: one fixture per rule,
  including "a disagreement is skipped, never queued".
  **Checkpoint.**
- **S9.** `mint_one`, `recover`, `feed` and the CLI. Check with crash
  simulation in `check_mint`, then a dry `mint` on `co`.
- **S10.** Docs:
  - `countries.md` §3/§4 (stages and checkpoint);
  - `positions.md` (replace "a count, not a queue");
  - `design.md` (file list);
  - `institutions.md` `political.parties` (membership is P102, organ seats
    are offices).

  Run every `check_*.py`, including `check_neutral`.

## Verification (Cuba, dry first)
1. Seed and run CU through `reconcile`. Checkpoint the creation queue by title.
2. Write `census/cu.yml` from S0. Bodies and sources pass the guard live.
3. `mint-categorize --dry-run`. Read the request, run it, then dump every
   cluster with resolved labels. Watch for:
   - Q18060652 (colonial governor) offered for the 2020 governorships;
   - Q89188209 (twin of the presidency);
   - "member of the PCC" (party membership, not an office).
4. `mint-verify` and `mint-report`. An observer agent audits the skips and
   the guarded rows. This is a development checkpoint: show the funnel, and
   turn any wrong class into a rule.
5. Dry `mint`. Read each `data` blob against its siblings.
6. On the go-ahead, `mint --write --limit 1`, then:
   - `wbgetentities` shows the item;
   - `mint-feed` shows a `position` row, every attestation `retrieved`, and
     reopened verdicts that are `same-office`;
   - `propose` makes P39s on the new QID.
7. The rest of `mint --write`. A rerun creates nothing, and a killed write is
   recovered.
8. `policy --dry-run`: no minted QID under `office/unindexed` or
   `office/unheld`. Then `verify`/`apply` on the user's go.
9. `scripts/position_metadata.py --country cu` as an outside check: zero
   defects on the minted items. Record the mint numbers and cost in
   `countries.md`.

## Open risks
- **Large countries:** categorize chunking (150 groups per request) is one
  shared context. Measure on `si` before relying on it.
- **Conservatism costs coverage:** skipping every disagreement may mint few
  items on the first run. Measure the funnel on Cuba. Split
  `disagree/<problem>` classes into rules (for example, "verify corrected
  P279 to a measured sibling parent" → accept the correction and re-guard)
  only where an observer audit shows the class is sound.
- **Outbound ambassadorships** (about 48 Cuban categories) are deferred: they
  need the bilateral two-parent shape plus P137. Report the count for now.
