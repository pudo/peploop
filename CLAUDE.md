# Wikidata workbench

Scripts for LLM-assisted Wikidata cleanup: filling in each country's
**national PEP landscape** — everyone politically exposed under FATF guidance
(heads of state and government, ministers, legislators, apex-court judges,
central bankers, military leaders, royal and ruling families, ambassadors,
SOE executives, party officials), not just the cabinet. Outputs land in
`data/` (gitignored).

Where things live:

- `recipes/country_sweep.md` — **the method.** One country at a time, run
  99% autonomously: survey → target census → rosters → identity gates →
  policy → backtest → one validated `.qs` the human reviews in the
  QuickStatements importer. Read it before starting a run rather than
  re-deriving the method; its calibration table says what countries of each
  coverage profile yield, and §7 catalogues the roster failure modes.
- `tasks/followups.md` — actionable leftovers from closed campaigns
  (unapplied batches, item-creation lists, the surgical wikibase-cli list).
- `tasks/*.md` (the rest) — briefs only for campaigns that are a genuinely
  different kind of work (genders, birthdates, jurisdictions, categories).
- `regression/<country>/` — the committed record of every accepted run.
- `WORKBENCH.md` — design notes and write-path decisions.

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

- **Decide, then let the user write.** The toolkit decides every case and
  records the rule that decided it; nothing reaches Wikidata until the user
  runs the batch. Those are different gates, and conflating them is what
  produced a backlog of 438 unanswered rulings and zero applied edits.
- **Every case gets a disposition.** `wd/policy.py` holds an ordered list of
  `predicate → disposition` rules; a case with no evidence is `skip` with a
  recorded reason, and a class of case needing data entry becomes a byproduct
  list. Neither is ever a question about a row. If you find yourself wanting
  to add a tier so a human can rule on it later, write the rule instead.
- **Escalate policies, not cases.** A country whose history contradicts the
  default says so once, in `dispositions` or `continuous_eras` — never per
  person.
- **The rows you skip are the test set.** Most of a roster is people whose spell
  is already recorded, and `wd/backtest.py` scores the engine against them
  before anything is proposed — did the routing pick the item the community
  uses, do the parsed dates contradict the recorded ones, does the record use
  the qualifier a rule is about to add. Read the `## Backtest` section of the
  audit first. It also derives the office's item family, which is how a country
  nobody has hand-analysed gets the `duplicate_office_item` protection.
- **A batch is checked before it renders.** `wd/validate.py` refuses to write a
  `.qs` containing a duplicate line, a `start > end`, or a malformed value, and
  warns about coarse dates beside day-precision ones on the same item. Don't
  re-type those checks per campaign; that is what it is for.
- **Measure the convention, don't declare it.** Whether a term belongs on an
  office item is answered by `wd/precedent.py` from that item's own record,
  because the answer differs per item inside one country: Czech Agriculture
  carries ten pre-1993 terms, Czech Defence's item only exists from 1993.
- **One office is often several items.** Before choosing a `target`, check
  whether the office is a *succession* — Spanish ministries are renamed each
  cabinet and Wikidata models each name, so foreign affairs is four items and the
  Congress presidency four more (only one of which says so in its label). Route
  by date (`Office.date_targets`), and expect the roster's rows to be on record
  under a sibling item (`already_under_sibling` → `duplicate_office_item`). Two
  items competing for the *same* era is a merge decision, not a campaign.
- Keep batches **additive-only**, and **one `.qs` per campaign**. QS
  de-duplicates and additive batches are mass-revertable, so the batch is safe
  as one unit. The renderer used to shard by `decision.concern`; it no longer
  does, because the review that decides anything happens in the QuickStatements
  importer and a split meant the file approved was never the file read end to
  end. `concern` stays on the record as metadata and groups `edit_plan.md`.
- **There is no review queue.** A campaign's `dispositions` maps every
  non-applying rule to `skip`, so each case is applied or skipped with a reason
  and `edit_plan.md` is an account rather than a backlog. The corollary is that
  conservatism lives in the rules: nothing is relaxed to raise the count, and a
  lane with one weak channel is reported small rather than padded.
- **Statements go out as QuickStatements; position items are created through
  the API** (`wd/write.py` → `wb create-entity`). QS `LAST` is only valid as a
  statement's subject, so an item created in a batch cannot be the value of
  the holders' P39 in that same batch. Creation is guarded by a ledger, a
  duplicate search, a holder floor, a body-label check, and `--dry` by default.
- **Destructive edits still stop and ask** — merges, deletions, statement
  removal, rank changes. They are the one human gate left.
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
- **Two axes, not one.** A tier answers "did this claim hold?"; it says
  nothing about "is this the right person?". Every policy rule is a
  conjunction over both — `roster_only` applies on a wikilink or a real
  citation and skips on a bare name match. Not all channels are equal
  either: a roster row with a non-Wikimedia citation is a *better* second
  channel than the category whose absence used to hold it.
- **Rule order is load-bearing.** Flags are a set, so a row can be acting
  *and* pre-cutoff *and* roster-only. Rules answering "does this belong on
  this item at all" must precede rules answering "what kind of tenure was
  it", and the general rule must come last of the applying ones or it
  swallows the specific tiers and drops their qualifiers. Both mistakes were
  made in one afternoon; the table is grouped and commented accordingly.
- **Research conventions empirically.** Wikidata's documented guidance is
  often ambiguous (P1001!). Measure de-facto practice with SPARQL tallies
  over well-curated item clusters and read exemplar items in full before
  choosing properties (`recipes/country_sweep.md` §10 is the template).
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
- **`wdt:` returns only best-rank values — for every property, not just
  P39.** One preferred statement hides all the normal-rank ones and a
  deprecated statement vanishes entirely. On P39 that undercounts coverage
  (Czechia read as 7,554 holder statements against a real 14,124, and a
  statement that already existed was offered as an add). On **P31 it
  misclassifies items**: `wdt:P31` says Q12251224 "Crown Prince of Saudi
  Arabia" is only a crown prince (its `Q4164871` sits behind a preferred
  value) and says Q68081922 has no type at all (deprecated), so a
  "is this a position?" closure built on `wdt:P31` rejects real positions.
  Use `p:P39/ps:P39`, `p:P31/ps:P31` etc. whenever the question is "does
  this hold *anywhere* among the values", and keep `wdt:` for "what is the
  one current/best value".
- WDQS: statement-node scans (`p:`/`pq:`) time out easily; prefer `wdt:`
  and subquery-first shapes, retry patiently, and never cache non-JSON
  bodies (a 200 "upstream request timeout" poisons the cache —
  `wd/api.py:sparql` guards this).
- WDQS via GET: ~150+ `VALUES` items overflow the URI (HTTP 414). A 200
  body that is *truncated* JSON means the query timed out mid-serialization
  — that failure is deterministic, so retrying whole is useless: bisect the
  chunk (`citizenship_candidates.py:group_fetch`).
- Roster tables lie in small ways, and each one silently costs every date on a
  page: a "Duración" column read as the term, a hidden `{{dts}}` sort key whose
  hyphens split the cell first (and whose *tail* holds the visible date, which
  lxml's `remove()` discards), `<hr>` instead of `<br>` between a person's
  several terms, an abbreviated month with the dot on the far side ("17 de jul.
  de 1834"), "(fallecido en el cargo)" reading as still-in-office, and a header
  row marked up as `td`. The full list, with what each one broke, is in
  `recipes/country_sweep.md` §7.
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
