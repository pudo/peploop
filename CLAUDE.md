# Wikidata workbench

Scripts for LLM-assisted Wikidata cleanup (humans and the positions they
hold). Design notes and write-path decisions live in `WORKBENCH.md`; one
brief per campaign in `tasks/*.md` (each ends with a status checklist —
update it as work progresses). Outputs land in `data/` (gitignored).

## Running things

- Python: `/Users/pudo/.python/wrangle/bin/python scripts/<script>.py` —
  never `uv run`, never install into the env. Scripts self-insert the repo
  root into `sys.path` to import `wd/`.
- All HTTP goes through `wd/http.py`: descriptive User-Agent (Wikimedia
  403s the default one) + disk cache in `data/cache/`. Don't hand-roll
  requests in scripts; for ad-hoc curl, pass
  `-A "opensanctions-workbench/0.1 (friedrich@opensanctions.org)"`.
- `wb` (wikibase-cli) is installed and logged in — reads are free to use;
  its config (with credentials) is at `~/.config/wikibase-cli/config.json`.

## Editing rules

- **Nothing is applied without the user's review.** Scripts produce a
  human-readable `.md` plan (sorted by impact, e.g. holder counts) plus a
  machine `.qs` file. The user runs QS batches in the QuickStatements web
  UI themselves; surgical edits (ranks, merges, removals) go through
  wikibase-cli on request.
- Keep batches **additive-only** and single-concern (one `.qs` per concern);
  QS de-duplicates, and additive batches are mass-revertable.
- Anything ambiguous, low-confidence, or convention-unsettled goes into the
  `.md` review sections, never silently into the `.qs`.
- Statements derived from an article/source get references (`S854` + `S813`);
  structural inferences (e.g. P1001 from the item's own label) follow
  community practice and go unreferenced.

## Methodology (what has worked)

- **Mechanical first, LLM for the tail.** Regex/label parsing and SPARQL
  handle the bulk auditable-y; LLM agents judge only what mechanics can't.
- **Two independent signals per auto-edit.** An edit enters a batch only
  when two channels agree (e.g. label-derived country vs classifier verdict;
  city-item P17 vs classifier). Disagreement → review. A predictable
  systematic bias in one channel can be modeled and overridden explicitly
  (see the chose-sender override in `render_diplomatic_plan.py`).
- **Research conventions empirically.** Wikidata's documented guidance is
  often ambiguous (P1001!). Measure de-facto practice with SPARQL tallies
  over well-curated item clusters and read exemplar items in full before
  choosing properties (`tasks/diplomatic.md` is the template).
- **Verification agents:** fan out in parallel, one input file each; they
  write JSONL verdicts to `data/.../verdicts/` and return only counts +
  notable calls. Use `model: "opus"` for judgment-heavy passes. Always
  instruct: cite evidence, prefer "unclear" over guessing, never edit.
- Wikipedia category membership, name heuristics, and OS-merged values are
  *candidate generators*, not facts — every candidate is verified against
  the item and/or article before an edit is proposed.
- **Holder-derived priors are corpus-biased.** Majority properties of a
  position's holders (P27 citizenship, sitelink languages) make a strong
  shortlist signal, but generic occupations show 90–100% one-country shares
  merely because one wiki community documented its people ("notary" = 98%
  French). The classifier test: is the office inherently bound to ONE
  jurisdiction — would a holder from any country still hold it *there*?
- **Agents converge via the verdicts directory.** Parallel classifiers that
  read earlier `verdicts/*.jsonl` adopt each other's precedents (bishoprics,
  party posts, titular sees). Helpful — but it standardizes *around whoever
  answered first*, so cross-check convention calls across chunks in the
  renderer and route splits (church, party offices) to review.
- **Audit mechanical matchers on real output before shipping.** Every
  matcher this workbench has built was too loose on the first pass; always
  dump the full matched list with resolved labels and eyeball it.

## Gotchas (hard-won)

- Labels: many items have no `en` label anymore — always fall back
  `en → mul` (`wd/api.py:best_label`). wikibase-cli's `wb label` doesn't.
- wbgetentities hides transient errors in HTTP-200 bodies and redirects
  merged items to a different QID than requested — `wd/api.py` handles both;
  don't bypass it.
- Time values: precision < 9 (e.g. 7 = century) renders as a misleading
  year ("+2000/7" is the 20th century). Check `precision` before reading.
- WDQS: statement-node scans (`p:`/`pq:`) time out easily; prefer `wdt:`
  and subquery-first shapes, retry patiently, and never cache non-JSON
  bodies (a 200 "upstream request timeout" poisons the cache —
  `wd/api.py:sparql` guards this).
- WDQS via GET: ~150+ `VALUES` items overflow the URI (HTTP 414). A 200
  body that is *truncated* JSON means the query timed out mid-serialization
  — that failure is deterministic, so retrying whole is useless: bisect the
  chunk (`citizenship_candidates.py:group_fetch`).
- Matching entity names into position labels: substring is too loose (alias
  "Loire" fires inside "Indre-et-Loire"; "the North" hits the North Riding
  → Northern Ireland). Require the label's after-preposition *tail* to
  equal a name exactly, and reject bare-eponym aliases of suffixed
  subdivisions ("Gombe" for "Gombe State" names the city/emirate, not the
  state). Country P150 lists are first-level only — right granularity for
  regional offices, never for municipal ones.
- PETScan's "uses Q5" filter passes `Category:` items (via P4224); enforce
  `P31=Q5` yourself. Category membership ≠ held the position (acting
  officials, predecessors under earlier polities, plain miscategorization).
- URLs extracted from wikitext `<ref>`s arrive HTML-escaped (`&amp;`) —
  unescape before emitting.
- City→country resolution via search hits same-named US towns (Melbourne FL,
  Palestine TX) and historical P17 values (London → Kingdom of England);
  use preferred/un-ended P17 and require an agreement gate.
- P17 on positions with historical states (Zaire vs DRC) is a judgment
  call — route to review.
