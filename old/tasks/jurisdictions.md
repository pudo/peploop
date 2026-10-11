# Task: jurisdiction backfill for country-less position items

Position items with no resolvable country are **silently invisible to
OpenSanctions** — confirmed in code, 2026-08-04. Backfilling `P1001`
(applies to jurisdiction) / `P17` (country) on legitimate government
position items directly grows OS PEP coverage without touching any OS code.

Naming the polity is one of several things a position item owes.
`recipes/position_items.md` has the rest and `wd/shape.py` checks them locally: an
office that gains a `P17` while still saying only "position" is half-modelled, and
an office scoped to a *historical* polity legitimately resolves to no country and
must never be backfilled to a modern state.

## The skip, verified

`zavod/shed/wikidata/position.py:207`:

    # Skip all positions that cannot be linked to a country.
    if not position.has("country"):
        return None

Both `wd_peps` and `wd_categories` route every position through
`wikidata_position()`; in `wd_categories` a `None` position also drops the
person's occupancy. Country resolution tries, in order: the position item's
own P1001/P17/P27 claims, then a recursive traversal
(`country.py:item_countries`) over P17/P27 and then
P1001/P1376/P361/P749/P159/P2389, refusing historical countries. An item
where all of that comes up empty → position skipped, occupancies dropped.

Live proof: the Prosecutor General of Lithuania item (Q132068652) had *no*
P17/P1001 until the Lithuania campaign's side edits added them — the office
was structurally invisible to wd_peps no matter how many P39s pointed at it.

## Scale (WDQS, 2026-08-04)

* 147,310 distinct items are used as P39 targets; **12,941 (8.8%) have
  neither P17 nor P1001.** Some are rescued by the traversal props; the rest
  are skipped.
* Composition of the ≥50-holder, no-traversal-props-at-all tier (sampled):
  1. **Generic occupational classes** — director, professor, CEO, notary,
     judge, deputy mayor, "local politician". Country-less by nature; the
     P39 usage itself is sloppy (belongs in P106, or a country-specific
     subclass). OS skipping these is *correct* — no fix wanted on the
     position; arguably the holders' claims deserve refinement.
  2. **Historical offices** — Qing dynasty ranks, Geheimrat, members of the
     Parliaments of Great Britain (1707–1800). Skipping is correct too.
  3. **Ambiguous but possibly live** — e.g. Q5354399 "county magistrate"
     (4,253 holders; Taiwanese 縣長 usage may include current officials).
  4. **The target class: legitimate national offices with missing metadata**
     (the Q132068652 pattern) — typically young, thinly-edited items in the
     1–30 holder range. These are pure win: one P1001 statement makes the
     whole office and all its holders visible to OS.

## Approach

1. `scripts/bare_positions.py` — build the full candidate list. WDQS times
   out on the one-shot query (learned the hard way: statement-node scans
   with `pq:P580` filters, and even the grouped census under load), so
   paginate: fetch distinct P39 targets + holder counts in slices (by holder
   floor, or paged `LIMIT/OFFSET` over `ORDER BY ?pos`), cache each page,
   filter for missing P17/P1001 client-side from batched `wbgetentities`
   (which also yields P31 ancestry, labels, sitelinks in one go).
2. Classify each candidate (LLM pass): generic class / historical /
   fixable national office / unclear. Signals: P31/P279 ancestry, label
   pattern ("Minister of X", "member of the Nth Y"), holders' recency
   (per-position SPARQL for max P580 is cheap), holders' citizenships
   (majority country ≈ the missing jurisdiction), linked Wikipedia article.
3. For "fixable": propose `P1001` (and `P17` where clear) with the inferred
   country, evidence noted, human-reviewed → QuickStatements batch.
4. Re-run the OS-side check: positions previously skipped that now resolve.
   (Optionally: report the generic-class P39 usages upstream as a Wikidata
   data-quality project — out of scope here.)

## Status

- [x] skip behaviour confirmed in code; scale quantified (12.9k/147k bare)
- [x] bare_positions.py run (2026-08-04): 12,893 bare positions →
  `data/jurisdictions/bare_positions.json`. 8,491 have no traversal props at
  all (definitely skipped by zavod); 4,402 might still resolve via traversal.
  The single grouped WDQS query went through on the first try this time; the
  paged fallback wasn't needed.
- [x] label-country slice: 988 bare positions name exactly ONE country in
  their label (`label_country_candidates.json`, 5,822 P39 holders covered;
  461 of them definitely-skipped; 963 not marked abolished). Jurisdiction is
  inferable from the label alone. Notable modern finds in the head: Speaker
  of the House of Representatives of Egypt (34 holders), Member of the
  General National Congress of Libya (34). Substantial historical/religious
  noise remains (Constable of France, High Priest of Israel, nuncios) —
  classification still required before edits.
- [x] classification pass over the 988 (2026-08-04, 8 parallel LLM
  classifiers → `verdicts/chunk_*.jsonl`, plan via
  render_jurisdiction_plan.py): **663 fix-current / 92 fix-historical /
  220 skip / 13 unclear.** Products:
  * `fix_plan.qs` — **225 high-confidence non-diplomatic statements**
    (P1001, one P17) covering 1,548 P39 holders: 84 national-exec, 76
    legislative, 31 military, 24 judicial, 6 central-bank. Ready for review.
  * **386 diplomatic posts (1,866 holders) held back**: classifiers were
    inconsistent on sender vs receiver for sender-named posts ("Consul
    General of France in X") — convention since researched and decided
    (P17 = receiver, P137 = sender, no P1001; measured convention and
    rationale in `scripts/render_diplomatic_plan.py`'s docstring, method in
    `recipes/country_sweep.md` §10).
  * Medium/low-confidence fix-current (~50), fix-historical (92), unclear
    (13) listed in `fix_plan.md` only.
  * Classifiers also caught label-matcher false positives (Jersey/New
    Jersey, Samoa/American Samoa, Order of Malta...) as skips, and fixed
    two China/Taiwan mixups from the label matcher.
- [x] the harder remainder (11,905 with no country in the label), 2026-08-05:
  * `scripts/holder_citizenship.py` — holders' P27 tallies for all 11.9k via
    budget-chunked SPARQL. 10,150 have signal; strong-majority tiers (≥3
    holders at ≥80%, or 2-of-2 unanimous; top country modern, not abolished)
    → 2,499 candidates.
  * `scripts/citizenship_candidates.py` — enrichment: holder samples
    (label+desc; the only evidence for the 1,504 article-less items),
    sitelink langs; 20 chunks.
  * 20 parallel Opus classifiers → `verdicts/citizen_*.jsonl` (2,499
    verdicts: 1,185 fix-current / 959 skip / 303 fix-historical / 52
    unclear). Corpus-bias traps held: notary/98%-fr, SACEUR/100%-us,
    Andean Parliament/100%-pe all skipped.
  * `scripts/render_citizenship_plan.py` → `citizenship_plan.md` + `.qs`:
    **572 statements (564 P1001, 8 P17) covering ~9.5k P39 holders.** Gates:
    high confidence only; kind excluded for diplomatic/generic/award/list;
    church + party offices to review (convention unsettled, chunks split);
    country must match the citizenship prior; subnational entity QIDs
    accepted only after mechanical verification (P17 + name-in-label), or
    via strict label-tail equality against the country's own P150 list
    (substring matching was too loose: alias "Loire" fired inside
    Indre-et-Loire, "the North" hit the North Riding — caught in audit).
  * Review backlog in the .md: 149 subnational without a safe entity, 183
    church/party convention rows, 163 medium/low confidence, 10 prior
    disagreements (incl. Greenland vs Denmark), 52 unclear (incl. Crimea /
    Sevastopol — deliberately not batched), 303 historical.
- [x] **applied** — verified live 2026-08-19, not from a run log: of the lines
  touching the positions-DB export, `citizenship_plan.qs` is 178/178 present on
  Wikidata and `fix_plan.qs` 44/45. The box sat unchecked for two weeks after
  the edits went in, which is how a re-run nearly re-proposed them.
  `diplomatic_plan.qs` + `diplomatic_tail.qs` are applied too — all **668**
  statements over 367 subjects verified present 2026-08-19. An earlier check
  here read 17/38 and was wrong: it compared the batch's `P137` sender lines
  against a snapshot holding only `P17`/`P1001`, so every sender statement
  counted as missing. Check a statement against the property it actually
  names.
- [x] **positions-DB run, 2026-08-19** — driven off an export of zavod's
  positions table (rows with an empty `countries` array) rather than a SPARQL
  census, because that export *is* the coverage OS tried and failed to emit.
  `scripts/db_positions.py` partitions it with `wd.shape.verify`:
  * 3,083 QIDs → **1,861 fixable** (no polity), 501 that resolve today and want
    a re-crawl not an edit, 404 that are not positions, 244 scoped to a dead
    polity, 45 bilateral, 28 deleted.
  * `wd/shape.py:_scoped_to_history` returns `bool(named)` over
    `COUNTRY_PROPS + FALLBACK_PROPS` and never tests historical-ness, so an item
    whose `P361` points at a country-less body reads as "scoped to history" and
    its `no_polity` defect is suppressed — **232 of 493 items landed in the wrong
    bucket**. Corrected locally in `db_positions.py:scoped_to_dead_polity`
    (`P17`/`P1001` only); `wd/shape.py` is untouched and 11 campaigns still read
    the wide test. Fix upstream or not, but know which one is running.
  * 1,861 → **472 candidates**: strong citizenship majority (387), label-named
    country (3), both (82). The 1,389 dropped carry 111k P39 holders and that is
    the gate working — `president`, `minister`, `director`, `member of
    parliament`, `ambassador`, `professor`, at 5–74% majority shares.
  * classified through `scripts/classify_jurisdictions.py` (Anthropic SDK, one
    committed prompt, schema-enforced verdicts, resumable ledger): 472 verdicts,
    46 requests, **$5.38**. Then 144 `fix-current` re-judged for $1.93 after the
    audit below. Ledger: `verdicts/db.jsonl`, pre-fix copy in `db_pass1.jsonl`.
  * **`db_plan.qs` — 19 statements over 517 P39 holders**, all verified absent
    live. Review backlog in `db_plan.md`: 48 medium/low confidence, 26
    subnational without a safe entity, 102 historical, 35 unclear.
- [x] the audit that the 19 survived and 26 did not — read it before trusting a
  future pass. Two failures, both real, both now closed:
  * three party offices shipped **despite the classifier marking them "routed to
    human review"**, because `render_citizenship_plan.py` gated on `PARTY_RE` —
    a regex for the *word* party — and a party is usually named ("SPD", "Québec
    solidaire"). `party` is now in `REVIEW_KINDS`; route on the structured field.
  * four **bodies** were handed a `P1001` at high confidence — the Ministry of
    Local Self-Government of Macedonia, the Philippine Senate Committee on
    Banks, the Sudanese Sovereignty Council, the Presidential Administration of
    Iran. `wd/shape.py:NOT_AN_OFFICE` has encoded "a military staff is a body,
    not a seat in it" for months; the prompt had never been told, so the LLM
    tier re-derived the bug with a correct-but-irrelevant argument ("the body
    exists only in that state"). Rule and all four cases are now in
    `prompts/jurisdiction_classifier.md`; on re-judge all four flipped to skip,
    each naming the office that should carry the statement instead.
- [ ] review db_plan.md → apply db_plan.qs
- [ ] the 1,389 census items below the candidate gate: single-holder offices
  (565 items, 744 holders) need a second signal; the ~645 below an 80% majority
  are mostly the generic classes and want a `P39`-usage cleanup upstream, not a
  jurisdiction
- [ ] follow-ups parked: party offices campaign-wide (LDP sec-gen, CCP
  provincial secretaries — PEP-relevant, convention undecided); religious
  sees P17 batch (measured practice: 965/1443 carry P17=country); tier C
  (3,779 single-holder positions) needs a second signal
- [ ] re-run bare_positions.py after applies → measure OS coverage gain
