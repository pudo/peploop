> **Retired.** This folder is the `wd/` campaign toolkit that came before
> peploop and peptree, kept as prior art. Nothing in it is imported, run, or
> followed by the current tools; its rules (wikibase-cli writes, claims files,
> coverage ledgers, campaign dispositions) do not apply to them. Lessons worth
> keeping are in `docs/history.md`. What follows is the toolkit's own
> instructions file, unchanged.

# Wikidata workbench

Scripts for LLM-assisted Wikidata cleanup: filling in each country's
**national PEP landscape** — everyone politically exposed under FATF guidance
(heads of state and government, ministers, legislators, apex-court judges,
central bankers, military leaders, royal and ruling families, ambassadors,
SOE executives, party officials), not just the cabinet. Outputs land in
`data/` (gitignored).

Where things live:

- `recipes/institutions.md` — **what a country is made of.** The checklist of
  ~35 institution classes a sweep is scoped against and measured complete
  against, each with where its roster usually lives, what item shape it needs,
  and the failure mode that usually kills it. Start here, not at the campaign
  script: the three narrowest campaigns in this repo are the three named
  `*_ministers.py`, because a sweep scoped from its own filename outward never
  asks about courts.
- `recipes/position_items.md` — **how to model a political office.** The measured
  Wikidata conventions for a position item: `P31` to a position metaclass (and
  `Q294414` public office is the modal one, not `Q4164871`), `P279` naming the
  *kind* of office, `P17` the state with `P1001` the polity actually governed,
  `P361` the body, `P1365`/`P1366` for a renamed office. Its checker is
  `wd/shape.py`, run by `scripts/position_metadata.py --country <cc>`; the defects
  it reports are Wikidata's own — an occupation or a rank typed as an office, an
  office scoped to no polity, an office that says "position" and never says which
  kind (54 of Iran's 323 items). Read it before scoping a roster lane and before
  minting. Whether OpenSanctions currently emits an item is a secondary matter
  kept in one closing section: `role.pep` is an internal sentinel, never written
  and never a reason to pick a parent, and `MUNI_COUNTRIES` is irrelevant here.
- `recipes/person_items.md` — **how to model the holder.** The sibling of the
  above, for the people a roster lane writes P39 onto, checked by `wd/human.py`
  and run by `scripts/person_metadata.py --country <QID>`. It keeps three answers
  apart: Wikidata modelling *defects* (`P31 = Q5` as a best-rank claim, a name in
  some language, not also typed `Q4164871`), *gaps* a campaign can close (`P569`,
  `P27`, `P21`), and what OpenSanctions makes of the item, which is again a
  closing section and never a defect. Two findings invert the obvious priorities:
  nothing downstream reads `P21` at all, so a gender lane is a Wikidata lane; and
  a **birth date is what rescues an undated tenure** — with no date on either the
  person or the P39 statement no occupancy is produced, and the person and the
  position both vanish. Measured on Lesotho: of 138 holders, **zero** carry a modelling defect
  while 57 want a birth date — 9 are emitted only because they have one and 10
  more would be. `research/person_items.md` has the funnel.
- `research/<topic>.md` — **the measurements a recipe rests on.** Property
  tallies, cluster sizes, exemplars read in full, and the queries that failed.
  `research/position_items.md` is the first: 145,212 position items, eleven curated
  clusters, and the reason a percentage over the whole corpus is a statement about
  French communes. A recipe cites; this is what it cites. Re-check here before
  re-measuring, and add a report when a run measures something worth inheriting.
- `recipes/country_sweep.md` — **the method.** One country at a time, run
  99% autonomously: census → blocker triage → item creation → rosters →
  identity gates → policy → backtest → one validated `.qs` the human reviews
  in the QuickStatements importer. Read it before starting a run rather than
  re-deriving the method; its calibration table says what countries of each
  coverage profile yield, and §7 catalogues the roster failure modes.
- `recipes/enrichment_loop.md` — **the other method, and the one to reach for
  when the goal is coverage rather than one institution.** One *person* per
  request, scoped to one `wd_categories.yml` PETScan query, done when that query
  can be deleted. A campaign is office-first, so every institution nobody
  declared stays invisible; this discovers the offices instead. Its measurements
  are `research/enrichment_loop.md`, its ledgers are `coverage/petscan_specs.md`
  (what blocks each spec) and `coverage/petscan_retirable.md` (the PR that
  deletes them — the spec count falls as they retire, so measure, don't quote).
  §10 of the recipe is the one to read first: thirteen defects were found in this
  loop and **not one of them by a test**.
- `coverage/offices_named.md` — **the creation queue, with evidence.** Every
  office an enrichment run named and could not place, each with the person
  attested to have held it, the dates, and the sentence that says so. Built by
  `scripts/office_ledger.py` from artifacts that are otherwise gitignored, which
  is the point: a queue that lives only in `data/` gets re-derived instead of
  worked. `create` is the list to mint from — `wd/create.py:guard`'s holder floor
  is already met, which is what ~150 offices listed across nine campaigns never
  had.
- `coverage/<country>.md` — **the ledger, and the definition of done.** One row
  per institution class with a disposition. A campaign closes when no row reads
  `deferred` and every `blocked:` names an issue — *not* when a batch validates.
  `coverage/README.md` is the cross-country matrix, and it is the artifact that
  made visible what eleven campaigns could not see from inside: judiciary
  covered in 0 of 11, SOE and sovereign wealth 0 of 11, mayors nowhere at all.
- `tasks/followups.md` — actionable leftovers from closed campaigns
  (unapplied batches, item-creation lists, the surgical wikibase-cli list).
- `tasks/*.md` (the rest) — briefs only for campaigns that are a genuinely
  different kind of work (genders, birthdates, jurisdictions, categories).
- `prompts/<pass>.md` — **what an LLM tier was actually asked.** The
  instructions for a judgement pass, versioned beside the code that sends them
  (`wd/verdicts.py`, `scripts/classify_jurisdictions.py`). A prompt that lives
  only in a session transcript cannot be audited when its verdicts look wrong,
  and four passes were run that way. When a run surfaces a rule the prompt was
  missing, write the rule *and* the case that exposed it.
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

- **Model Wikidata correctly first; consumer legibility is secondary.** Both
  recipes are ordered that way, and it decides what to do when they disagree: the
  measured convention wins, and the gap becomes an issue filed against
  `opensanctions` with an owner named in the ledger row. Never mass-assert a shape
  to satisfy a reader, and never record "a consumer does not emit this yet" as a
  defect.
- **A campaign is done when every institution has a disposition**, not when a
  `.qs` validates. This is `wd/policy.py`'s rule — every case gets a disposition,
  and "review later" is not one — applied one level up, to institutions. A
  byproduct list does not close an institution: ~150 office items have been
  listed for creation across nine campaigns and 23 minted.
- **Fix a shared blocker before the lanes, not after.** Half of everything ever
  deferred was blocked on one thing in `wd/` that a single change would unblock.
  A workaround appearing in a *second* campaign is not a pattern to copy, it is
  the signal that something is missing from the toolkit — Kuwait and Jordan both
  dropped a kinship lane to `{{Tree chart}}`, the second citing the first.
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
- **Retrieval ranks; a model decides; a mechanical gate vetoes.** Matching an
  office name to its item is not a string comparison: "Minister of Family,
  Labour and Social Policy" *is* `Q25919989` under a later name, while "Mayor of
  Chełm" is *not* `Q177529 mayor`, and on tokens alone both read as "the
  candidate has fewer words". `wd/positions.py:index_for_country` retrieves from
  the country's own labels and aliases (13 per item, every language, where
  `wbsearchentities` is an English prefix search capped at 30);
  `wd/rerank.py` shows the top candidates *in full* and asks. Measured over
  Poland's 71 queued offices, a mechanical top-1 would have been wrong 69 times.
  Two rules: **containment is scored one way — the candidate must cover the
  query**, or `{mayor} ⊆ {mayor, chelm}` writes a named mayoralty onto the
  occupation class; and a pick must clear the `P1001` gate before it is applied.
- **Which wiki to read is a property of the country, not of a global ranking.**
  `wd/dossier.py:pick_langs` falls back to `WIKI_PRIORITY`, a size ordering, so
  the second article read for a Saudi crown prince, a North Korean legislator
  and a Myanmar general was **German** — `de` is second on that list. Pass
  `prefer=(spec.language, *territory_langs(cc), "en")`;
  `wd/dossier.py:territory_langs` asks `rigour` (`get_territory(cc).langs`, ISO
  639-3, converted by `rigour.langs.iso_639_alpha2`). It moved the second wiki
  for 19 of 36 spec/country combinations.
- **A whole-country gazetteer is a small-country technique.** Czechia is 194
  position items and Poland 322, but Russia is 2,348 and Spain **13,198** —
  mostly per-municipality mayoralties, plus bishoprics and nobility titles that
  are all legitimately under `Q4164871`. Measure before scoping a bucket run.
- **Measure the convention, don't declare it.** Whether a term belongs on an
  office item is answered by `wd/precedent.py` from that item's own record,
  because the answer differs per item inside one country: Czech Agriculture
  carries ten pre-1993 terms, Czech Defence's item only exists from 1993.
- **Where power is dynastic, the family is a lane of its own.** `wd/kinship.py`
  reads a genealogy article (`en:Descendants of Ibn Saud`) for P25/P22/P53,
  because the office lane reaches only the fifth of a royal house that held
  office. The heading is the assertion — a wife's name means "these are her
  children", "Patrilineal grandsons" closes the candidate set for a patronymic
  — and the chain must come from the *item's* full name, not the article's
  printed short form. `recipes/country_sweep.md` §4a has the four ways that
  went wrong. Such a lane joins the campaign's own batch through
  `Campaign.extra_verdicts`.
- **One office is often several items.** Before choosing a `target`, check
  whether the office is a *succession* — Spanish ministries are renamed each
  cabinet and Wikidata models each name, so foreign affairs is four items and the
  Congress presidency four more (only one of which says so in its label). Route
  by date (`Office.date_targets`), and expect the roster's rows to be on record
  under a sibling item (`already_under_sibling` → `duplicate_office_item`). Two
  items competing for the *same* era is a merge decision, not a campaign.
- Keep batches **additive-only**, and **one batch per campaign** — one `.qs`
  plus the claims file below, reviewed together. QS de-duplicates and additive
  batches are mass-revertable, so the batch is safe as one unit. The renderer
  used to shard by `decision.concern`; it no longer does, because the review that
  decides anything happens in the QuickStatements importer and a split meant the
  file approved was never the file read end to end. `concern` stays on the record
  as metadata and groups `edit_plan.md`.
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
- **A person's several tenures in one office cannot go through QuickStatements
  at all.** QS matches an incoming line on subject, property and *value* alone
  and merges the line's qualifiers into the statement it finds, so two spells
  become one P39 carrying both starts and both ends with nothing pairing them
  up — Q1368615 holds an Ecuadorian ministry statement whose starts are
  fourteen years apart, which anything reading P39 with dates takes for
  nineteen unbroken years. `wd/validate.py:collapsing_groups` finds these,
  `render_edit_plan.py` partitions them into `edit_plan_claims.json` (one
  wikibase-edit payload per person, so their tenures land atomically) and
  `scripts/apply_claims.py` writes them, `--dry` by default. The `.qs` and the
  claims file are **two halves of one campaign's batch** — review them
  together; the split is a property of the write path, not of the evidence.
  The trade is that the API de-duplicates *nothing*, so re-running without
  `claims_written.json` would double every tenure: the ledger is load-bearing
  here in a way it is not for QS.
- **Know whether an edit merges or creates.** QuickStatements matches a line on
  subject, property and *value* and folds its qualifiers into the statement it
  finds; the API creates and never merges. So a statement that already exists and
  wants a date, an end or a qualifier is a **QS merge**, and routing it to the
  API writes a duplicate instead — which is how five duplicate claims reached a
  rendered payload from a rule that was individually correct. Three combinations
  are safe on neither path and are byproducts: several merges onto one office,
  a merge plus a creation onto one office, and a recorded span the evidence
  contradicts. `wd/enrich.py:MERGE_FLAGS` names them and
  `scripts/render_edit_plan.py` refuses to API-route one.
- **Pre-flight any API write against live state.** `claims_written.json` protects
  a re-run, not a first run against state that moved, and the API de-duplicates
  nothing. Read the payload against `max_age=0` claims before `--apply`.
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
- **A judgement pass is a script with a committed prompt**, not a fleet of
  chat agents. `wd/verdicts.py` batches candidates through the Anthropic SDK
  under a schema the API enforces, and `scripts/classify_jurisdictions.py` is
  the worked example; the instructions live in `prompts/`. Four passes ran the
  other way and every one of their prompts died with its session, which is why
  nothing could be re-run, audited, or improved. The ledger is the resume
  point: verdicts append to one JSONL, answered items are skipped, so a
  widened candidate set costs only what is new. `scripts/check_verdicts.py`
  pins that arithmetic offline. Always instruct: cite evidence, prefer
  "unclear" over guessing, never edit.
- Wikipedia category membership, name heuristics, and OS-merged values are
  *candidate generators*, not facts — every candidate is verified against
  the item and/or article before an edit is proposed.
- **Holder-derived priors are corpus-biased.** Majority properties of a
  position's holders (P27 citizenship, sitelink languages) make a strong
  shortlist signal, but generic occupations show 90–100% one-country shares
  merely because one wiki community documented its people ("notary" = 98%
  French). The classifier test: is the office inherently bound to ONE
  jurisdiction — would a holder from any country still hold it *there*?
- **Classifiers converge on whatever shares their context.** When passes read
  each other's `verdicts/*.jsonl` they adopt each other's precedents
  (bishoprics, party posts, titular sees) and standardize around whoever
  answered first; the SDK path removes that channel, because batches are
  independent requests against one frozen prompt. The failure survives one
  level down — a batch of ten items is still one context — so keep batches
  small, and keep routing the unsettled conventions (church, party offices) to
  review in the renderer rather than trusting a run to be consistent.
- **The classifier's `kind` is the routing signal; a label regex is its
  fallback.** Party offices shipped in a batch the classifier had itself
  marked "routed to human review", because the renderer gated on a regex for
  the *word* party and a party is usually named ("SPD", "Québec solidaire").
  Route on the structured field, and treat the regex as cover for a mis-kinded
  row.
- **Tell the classifier what `wd/shape.py` already knows.** A ministry, a
  council, a committee, a general staff is a *body*; the office is the seat in
  it. Both are bound to one jurisdiction, so the "is this bound to one state"
  test cannot separate them — four bodies were handed a `P1001` at high
  confidence before the prompt said so. Any closure the toolkit encodes in
  code belongs in the prompt too, or the LLM tier re-derives the bug.
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
- **Hijri dates are handled by *not* converting them.** An AH year falls
  outside the Gregorian range `parse_date` accepts, so `1370 هـ` yields
  nothing and a dual-dated `1331هـ/1913م.` keeps `1913`. Most Saudi rosters
  date in AH, so whole lanes legitimately yield no term — report that rather
  than converting. `scripts/check_dates.py` pins this and every other §7 date
  case; run it before and after touching `parse_date`/`parse_period`.
- **Comparing two dates means comparing at the precision they share.** Both
  `wd/validate.py` and `wd/backtest.py` do; the latter did not for months, and
  reported four correctly-parsed offices as parse defects because the roster
  was coarser than the record. A whole office at 0% date agreement is a
  comparison bug before it is a parser bug.
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
- **Never read Wikidata's *state* through the seven-day cache.** `wd/http.py`
  caches for a week, which is right for roster HTML and category membership and
  wrong for anything answering "what does Wikidata already record" — because
  that is precisely what this engine's own writes change. A UAE re-run read a
  `holders()` list cached before its batch went in (5 holders against 10 live),
  so the `already holds P39` gate let twenty already-existing statements back
  into the batch. `campaign.STATE_MAX_AGE = 0` covers `holders()` and the people
  fetch; any new state read must use it, and a pre-flight before writing should
  pass `max_age=0` of its own.
- **A write's `maxlag` covers the query-service updaters, not just database
  replication.** `action=query&siprop=dbrepllag` can report 0.9s while
  `wbeditentity` is refused because `wdqs1013` is 27s behind, and
  `wikibase-edit` answers a refusal by *retrying with backoff* rather than
  failing — so a write legitimately takes minutes and a 120s timeout reads as a
  hang. `wd/write.py` allows `WRITE_TIMEOUT` and keeps `MAXLAG = 5`, because the
  fix for a lagged site is to wait, not to declare a willingness to add load.
- **Never capture a subprocess's stderr without relaying it.** `wikibase-edit`
  printed "maxlag: Waiting for wdqs1013 … retrying" on every attempt, and
  `wd/write.py` captured and discarded it — turning a diagnosis that was sitting
  right there into three rounds of guessing at credentials, DNS and POST
  reachability. `_run` now relays stderr and reports the last output on timeout,
  which is the case that most needs it.
- WDQS: statement-node scans (`p:`/`pq:`) time out easily; prefer `wdt:`
  and subquery-first shapes, retry patiently, and never cache non-JSON
  bodies (a 200 "upstream request timeout" poisons the cache —
  `wd/api.py:sparql` guards this). **An unbounded `wdt:P279*` in a `FILTER NOT
  EXISTS` is the same trap** — it 504s and then resets the connection. Apply a
  type exclusion through `wd/shape.py:type_closure`, which is disk-cached and
  reads `p:P31/ps:P31` rather than truthy values.
- **A country's position set contains offices of *other* countries.** `P1001`
  is the jurisdiction, so an inbound ambassadorship ("ambassador of the United
  Kingdom to the Czech Republic") is scoped to the receiving state: 29 of
  Czechia's 194 offices were foreign embassies accredited to Prague. Do not try
  to separate inbound from outbound by `P17` — `Mayor of Brno` and the Czech
  Minister of Economy both carry a non-Czech `P17` from a predecessor state, so
  that test catches them and misses the embassies. `wd/gazetteer.py:for_country`
  drops all ambassadorships by default and logs the count.
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
