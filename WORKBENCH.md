# WORKBENCH — LLM-assisted Wikidata debugging & editing

Working notes for a loose toolchain of scripts that let an LLM (Claude, in this
repo) inspect Wikidata items — humans and the positions they hold — and make
targeted, reviewed edits. Not an app; a workbench.

## Goal & non-goals

* **Goal:** small Python scripts to fetch item + Wikipedia data in an
  LLM-friendly form; a standardized, etiquette-compliant HTTP layer; a write
  path for targeted edits (probably an existing CLI or the Wikibase REST API).
* **Non-goal:** depending on `nomenklatura`/`zavod`. Those are studied as prior
  art only (see below). No FtM entities here — we work directly on the Wikidata
  data model.
* **Non-goal:** unreviewed editing. The *decisions* are automated — the
  toolkit decides every case under declared rules and records which rule
  decided it — but statements reach Wikidata only when the user runs the
  batch, and destructive edits (merges, deletions, statement removal, rank
  changes) still stop and ask. Position items are the one thing written
  directly, because QuickStatements cannot express them (see the write path).

## Task briefs

Where a kind of campaign recurs, the method is written up once in
`recipes/*.md` and the brief keeps only what is country-specific:
`recipes/category_check.md` covers taking a `wd_categories` country block to a
reviewed P39 batch.

* `tasks/genders.md` — resolve conflicting P21 values on ~170 PEP items.
* `tasks/positions.md` — PETScan category members → verified missing P39s.
* `tasks/jurisdictions.md` — backfill P1001/P17 on country-less position
  items (currently invisible to OS crawlers).
* `tasks/diplomatic.md` — P1001/P17 conventions for diplomatic posts.
* `tasks/birthdates.md` — backfill P569 from Wikipedia infoboxes, per country.
* `tasks/category_positions.md` — the synthetic `wd_categories` positions,
  resolved to real position items.
* `tasks/ecuador.md`, `tasks/belarus.md` — country runs of
  `recipes/category_check.md`.

## Motivating tasks

1. **Link people to positions.** Read a person's Wikipedia article, find
   positions they held that are missing/incomplete on the Wikidata item, and
   assert `P39` (position held) with `P580`/`P582` date qualifiers, sourced.
2. **Fix gender statements.** Edit `P21` (sex or gender), including marking an
   existing value as **deprecated rank** (with `P2241` reason for deprecated
   rank) rather than deleting it. Note: rank editing rules out
   QuickStatements as the sole write path — QS cannot change statement ranks.

## Prior art studied (read-only reference)

### `nomenklatura/nomenklatura/wikidata/`

Read layer + QuickStatements write layer, built for OS↔WD reconciliation.
Things worth stealing:

* **`util.py:make_session()`** — the canonical session setup: descriptive
  User-Agent (default requests UA gets 403'd by Wikimedia), urllib3 `Retry`
  honoring `Retry-After` on 429/503, 90s timeout. We want the same shape, with
  our own UA string.
* **`client.py`** — `wbgetentities` with
  `props=info|sitelinks/urls|aliases|labels|descriptions|claims|datatype`.
  Two hard-won lessons:
  * Wikidata returns **transient errors inside HTTP 200 bodies** (DB lag, rate
    limits). Status-code retries can't see them; check for a populated
    `entities` key and retry in-band errors with backoff. `no-such-entity` is
    permanent and cacheable.
  * **Merged/redirected items**: the returned entity's `id` may differ from the
    requested QID → re-fetch under the new QID.
* **`model.py`** — clean object model: `Item` → `Claim` (mainsnak + qualifiers
  + references + rank) → `Snak`. Claims with `rank == "deprecated"` are
  segregated on parse. `Claim.is_ended()` handles the P582 subtleties:
  `novalue` end = asserted current; `somevalue` = ended at unknown date;
  imprecise end dates only count once their whole span elapsed.
  `Item.types` walks the P31/P279 closure (depth-capped at 6).
* **`wikipedia.py`** — Wikimedia asks bots to use the CDN-cached REST endpoints
  for page content, not the action API:
  `https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}` (lead
  paragraph, plaintext). For our use we'll want **full articles**, see below.
* **`value.py:snak_value_to_string()`** — time-value parsing: signed years,
  precision integers (9=year, 10=month, 11=day), the bot-artifact `-01-01`
  day-precision-that-isn't pattern.
* **`write/`** — typed QuickStatements V1 command model (`CREATE`, `Lxx`/`Axx`,
  statements with qualifier and `S854`/`S813` reference columns) + serializer.
  The `propose.py` diff-against-item approach (build a `_Known` summary of what
  WD already holds, emit only what's missing) is the right editing discipline
  even if we swap out the command format.

### `zavod/zavod/shed/wikidata/`

Domain logic on top of the client — how OS decides what a person/position is:

* **`human.py`** — filters: must have Q5 in type closure, exclude Q4164871
  (position) and Q95074 (fictional character); plausibility windows on P569/P570;
  citizenship from P27 with fallback chain P1001/P17/P19/P945/P495/P937.
* **`position.py`** — the position ontology: type closure matched against
  `POSITION_BASICS` (Q4164871 position, ambassador classes, …), a big
  `SUB_TYPES` map (mayor Q30185, MP Q486839, minister Q83307, head of state
  Q48352, judge Q16533, …), `EXCLUDE_TYPES` (awards, honorary/religious
  titles). `position_holders()` combines a SPARQL inverse lookup on
  `wdt:P39` with the item's own P1308 (officeholder) claims — people show up
  on either side.
* **`country.py`** — country resolution by traversing P17/P27, then
  P1001/P1376/P361/P749/P159/P2389, with a `SKIP_PLACES` blocklist for
  cultural/supranational regions.

## wikibase-cli field notes (v20.3.1, tested 2026-08-04)

Installed globally via npm; config at `~/.config/wikibase-cli/config.json`
(instance, `lang: en`, credentials for user `Pudox` already set up).

* Reads work: `wb data Q42 --props labels`, `wb desc Q42 -l en`,
  `wb claims Q42 P21` (→ `Q6581097`), `wb summary Q42` (includes the Wikipedia
  intro!), `wb search --type item "Federal Minister of Finance"` (→ Q22575092).
* **`mul` label gotcha:** Wikidata is migrating language-independent labels to
  the `mul` language code — Q42 now has **no `en` label at all**, only
  `mul: "Douglas Adams"` (plus 74 language-specific ones). Consequences:
  * `wb label Q42 -l en` → "no result found"; `wb label Q42` falls back to
    some arbitrary language (Arabic). The CLI doesn't do `en → mul` fallback.
  * **Our read layer must always try `en` then `mul`** (nomenklatura's
    `PREFERRED_WD_LANGS` already inserts `mul` right after English — same fix).
  * Any "does this item have an English label?" check is wrong without it.
* `wb search` matches labels/aliases fairly literally — "Minister of Finance
  of Germany" found nothing, "Federal Minister of Finance" hit. Position
  resolution needs alias-tolerant search (or SPARQL) rather than one query.
* Writes not yet tested. Next: try a claim edit on test.wikidata.org
  (`wb config instance https://test.wikidata.org` or `--instance`).

## Wikidata data model cheat sheet (humans & positions)

### Person item

| Prop | Meaning | Notes |
|---|---|---|
| P31 | instance of | Q5 = human |
| P21 | sex or gender | Q6581097 male, Q6581072 female, Q1052281 trans woman, Q2449503 trans man, Q48270 non-binary |
| P569 / P570 | birth / death date | precision int: 9=year 10=month 11=day |
| P27 | country of citizenship | |
| P39 | **position held** | the workhorse; one statement per tenure |
| P106 | occupation | weaker than P39; often where "politician" hides |

### P39 qualifiers

| Qual | Meaning |
|---|---|
| P580 / P582 | start / end time |
| P1365 / P1366 | replaces / replaced by |
| P768 | electoral district |
| P2715 | elected in (the election item) |
| P4100 | parliamentary group |
| P642 (deprecated) / P8810 | "of" — often needs cleanup |

### Position item

P31/P279 into the position class tree (Q4164871 "public office" etc.), P1001
jurisdiction, P17 country, P571 inception, P576 abolished, P1308 officeholder
(inverse of P39), P2388 office held by head of the organization.

### Statement anatomy (what edits manipulate)

* Every statement has a **GUID** (`Q42$D8404CDA-...`) — rank edits and
  removals target this.
* **Rank:** preferred / normal / deprecated. Deprecating a wrong gender value
  keeps the history visible; add qualifier **P2241** (reason for deprecated
  rank), e.g. Q41755623 "incorrect value". If one of several values is the
  right one, it should get **preferred** rank instead (with P7452 reason for
  preferred rank if warranted).
* **References:** P854 reference URL + P813 retrieved (web sources), or P248
  stated in. `P143 imported from Wikimedia project` is what bot-imports carry —
  a weak reference we'll often be upgrading.

## Read path (to build)

* One small module, e.g. `wd/http.py`: a `requests.Session` per
  `make_session()` above, with a UA like
  `opensanctions-workbench/0.1 (https://opensanctions.org; friedrich@opensanctions.org) python-requests/x.y`
  per the [Wikimedia User-Agent policy]. Simple on-disk cache (JSON files
  keyed by URL hash?) — enough for iterative debugging, no SQL cache needed.
* `wd/items.py`: fetch via `wbgetentities` (in-band error retry + redirect
  handling as above). Keep the raw JSON around; give the LLM a **condensed
  rendering** (labels, description, claims with resolved labels, qualifiers,
  ranks, references, sitelinks) rather than raw snaks.
* `wd/wikipedia.py`: full-article fetch for LLM reading. Options:
  * `https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}` — lead only.
  * Action API `prop=extracts&explaintext=1` — full plaintext, CDN-unfriendly
    but fine at our volume.
  * REST `page/html/{title}` — full Parsoid HTML; convert to markdown/text
    ourselves. Infoboxes and succession boxes carry a lot of the position
    signal, so plaintext extracts (which drop tables) may lose exactly what we
    want — worth testing both.
* SPARQL (`https://query.wikidata.org/sparql`) for inverse lookups (e.g. all
  holders of a position, candidate positions by name) — same session, results
  JSON.
* `wd/positions.py` (built 2026-08-05): `lookup_position(session, name,
  country)` — office name + ISO code → Wikidata position item, two-signal
  gated (label/alias variant match AND the item's P17/P1001 resolving to
  the country, directly or one P17 hop up for regional bodies). Returns
  matched / label-only / ambiguous / unmatched plus scored candidates;
  pure list-articles never match, dual-typed ones are flagged. Grown from
  the wd_categories.yml normalization (tasks/category_positions.md); reuse
  it for per-person office narrowing and item-creation checks.

* `wd/roster.py` (built 2026-08-05): `parse_rosters(html)` and
  `parse_bullet_rosters(html)` — an officeholder list, tabulated or bulleted,
  → dated rows with the appointing president, per-row citation URLs, and the
  flag marking acting officials (a colour legend, or "(в. а.)" in the text).
  Rendered HTML rather than wikitext, because `rowspan` decides which rows a
  shared reference belongs to. Knows Spanish, Russian, Belarusian and
  Ukrainian dates and column headers. Reach for it whenever an office's
  holders are listed somewhere: one fetch replaces N biography reads and
  carries better dates than any of them.
* `wd/campaign.py` (built 2026-08-05): the country-independent engine behind
  `recipes/category_check.md` — category harvest (including interwiki sibling
  categories), roster-row identity resolution with namesake gates, tiering
  into batch/held verdicts, and the audit document. A country script is only
  parameters; see `scripts/ec_ministers.py` and `scripts/by_ministers.py`.

## Write path (to decide)

Candidates, given "mark a value deprecated" is a requirement:

1. **Wikibase REST API** (`/w/rest.php/wikibase/v1/`) — modern, per-statement
   endpoints: `PATCH /entities/items/{qid}/statements/{guid}` (JSON Patch — can
   set `rank`), `POST .../statements`, `DELETE`. Auth via OAuth or bot
   password. Nice fit for surgical single edits from Python; every request
   carries an edit summary + our UA.
2. **`wikibase-cli` / `wikibase-edit`** (maxlath, Node) — `wd add-claim`,
   `wd update-claim-rank <guid> deprecated`, `wd add-qualifier`, edit-group
   support (batches show up on the EditGroups tool and are mass-revertable).
   Mature, battle-tested; the "existing wikidata cli" option. Downside: Node
   dependency, creds in its own config.
3. **QuickStatements** — great for reviewable bulk adds (and the nomenklatura
   serializer already exists as reference), but **cannot edit ranks or remove
   specific statements reliably** → at most a secondary path for additive
   batches.
4. **pywikibot** — heavyweight, its own config universe; skip unless we hit a
   wall.

Decision (2026-08-04): **wikibase-cli does not parse QS files**, so the two
tools split by edit shape:
* **Additive batches** (new statements with qualifiers + references) →
  QuickStatements V1 files, run in the web UI: built-in dedup, batch IDs,
  mass-revert, EditGroups tracking.
* **Surgical edits** (ranks, removals, merges, updates) → wikibase-cli:
  `wb edit-entity '{"id":…,"claims":{…qualifiers/references…}}'` (verified
  with --dry), `wb update-claim-rank`, `wb merge-entity`, all with
  `--summary` and `--maxlag`. An `apply_edits.py` wrapper only if/when the
  browser step gets annoying.

Amended (2026-08-06): **item creation joins the surgical side**, in
`wd/write.py`. QuickStatements V1 `LAST` is valid only as a statement's
*subject* and there is no way to name a created item, so an office minted in a
batch cannot be the value of its holders' P39 in that same batch — the 45
Czech supreme-court judges would need a second batch after a human read back
the QID. `wb create-entity` also takes one atomic JSON payload, where a
`CREATE` plus a dozen `LAST` lines can half-fail into a malformed item, and it
returns the QID immediately.

Creation is the least reversible thing here — undoing it needs a deletion or a
merge, both on the human-only list — so `wd/create.py:guard` requires all of:
a duplicate search through `positions.lookup_position`, a floor on attested
holders, a body whose label shares a word with the office's own name (the
first two body QIDs written by hand were a Spanish construction brand and a
character from the Nibelungenlied), and `--dry` unless `--apply` is passed.
Every write is appended to `data/<campaign>/applied.jsonl` and the created QID
recorded in `created.json`, because nothing de-duplicates a `CREATE`.

Etiquette for whichever path: descriptive UA, `maxlag=5` on writes, edit
summaries that link back to a rationale, test against **test.wikidata.org**
first, no mass edits without a bot flag.

## Proposed toolchain shape

```
wd/                  # tiny shared lib: session, cache, item fetch+render, wikipedia fetch
scripts/
  fetch_item.py      # QID -> condensed item dump (for LLM context)
  fetch_wiki.py      # QID or title -> article text (lead / full / infobox)
  find_position.py   # name/country -> candidate position QIDs (search + SPARQL)
  propose_edits.py   # (task-specific) emit edit plan for review
  apply_edits.py     # reviewed plan -> wikibase-cli / REST calls
plans/               # design docs if anything grows beyond a script
WORKBENCH.md         # this file
```

Working loop: fetch → LLM reads item + article → LLM drafts edit plan →
human reviews → apply → verify by re-fetching.

## Open questions

* Write auth: bot password on the main account vs. dedicated account? Edit
  volume is small and reviewed, so main account with good edit summaries is
  probably fine to start.
* Article rendering for the LLM: plaintext extract vs. HTML→markdown (keeps
  infoboxes/succession boxes). Test on a few politicians.
* Position matching: when the article names a position ("Minister of Finance
  of Ruritania"), resolve to QID via `wbsearchentities` + type-closure check
  (is it a Q4164871 descendant?) — reuse the closure-walk idea from
  `model.py:Item.types`.
* Sourcing edits: P39 from a Wikipedia article — cite the specific reference
  the article uses (better) or the article itself (P143, weak)? Probably:
  have the LLM pull the underlying citation URL out of the article when one
  exists.

[Wikimedia User-Agent policy]: https://meta.wikimedia.org/wiki/User-Agent_policy
