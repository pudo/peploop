# Task: real P39s for the synthetic PETScan positions

`wd_categories.yml` (opensanctions repo) assigns members of ~273 Wikipedia
categories a **synthetic position** (`h.make_position(name, country)`,
`wd-cat` hash id — no Wikidata identity). That was the right call for bulk
PEP coverage, but each of those assignments is really an unverified claim
"this person held X" — and X often exists on Wikidata as a proper item.
Goal: turn the config into candidates for a P39 verification process, so
the occupancies become real Wikidata statements (and OS can eventually read
them from wd_peps instead of the category heuristic).

Source: `/Users/pudo/Code/opensanctions/datasets/_wikidata/categories/wd_categories.yml`
(579 category specs, 273 with a `position:` block; 17 already carry a
`wikidata_id`; 154 non-English category languages, mostly ru).

**The goal is NOT to map every category member to the position.** Category
membership is a candidate generator; each member is verified individually
and only true holders get a P39 proposed. Rejects are equally valuable
output: they document the category's noise (LT pilot: 16% false positives)
and feed `negcats` suggestions back to the yml. Retirement of a
pseudo-position requires every member accounted for — verified P39 or
documented false positive.

## Granularity is the crux

The bulk crawler's assignment may be much coarser than the office a person
actually held; linking must target the *specific* office:

* **office** — the name denotes one seat ("Mayor of Bogotá", "Minister of
  Finance" + spec country by): resolve name→QID once, then run the
  country-sweep pipeline (PETScan members → roster/article verification →
  P39 batch, `recipes/country_sweep.md`).
* **membership** — one named body ("Deputy of the Kursk Oblast Duma",
  "Member of the Supreme People's Assembly"): same as office. (The Russian
  oblast dumas are the Q133268xxx items just backfilled in
  tasks/jurisdictions.md.)
* **bucket** — a class ("Minister of the Russian Federation", "Governor of
  a Russian Region", "Mayor of a Municipality in Guatemala"): no single
  target item. Per-person narrowing: read the member's item/article, name
  the actual office (portfolio, region, municipality), find *that* item,
  propose the P39 there. Positions resulting are much narrower than the
  crawler's assignment.

## Interim format

`scripts/category_positions.py` reads the yml and writes
`data/categories/positions.json`, one record per position-bearing spec:

    key, category, language, depth, os_topic, os_country,
    position_name, position_country, position_topics,
    declared_qid,          # wikidata_id from the yml, if any
    granularity,           # office | membership | bucket (mechanical)
    wd_candidates,         # entity-search hits: qid, label, desc, types,
                           #   country QIDs, label/country agreement flags
    status                 # declared | matched | ambiguous | unmatched | bucket

plus `data/categories/positions.md` for review. `matched` requires the two
usual signals: near-exact label match AND the candidate's own P17/P1001
resolving to the spec's country. Everything else stays for review/LLM.

Downstream (separate steps): the country-sweep pipeline
(`recipes/country_sweep.md`: rosters, identity gates, policy, one batch);
bucket categories get their own narrowing pass.

## End state: retiring pseudo-positions from the yml

The payoff metric. A category spec can lose its `position:` block once its
members are covered by real P39s (wd_peps then emits proper occupancies and
the synthetic wd-cat position is redundant). Per spec, extend the interim
record with a retirement readiness measure, computed mechanically:

    members_total,        # PETScan members with P31=Q5
    p39_have,             # members already holding P39 → resolved_qid
    p39_planned,          # members in a pending verification .qs
    p39_gap,              # the rest (verification rejected / not yet run)
    retirable             # resolved + position country-resolvable + gap == 0

Requirements per spec: verified `resolved_qid`; the item resolves a country
for zavod (some label-only rows wait on citizenship_plan.qs); every member
verified. The report ranks specs by closeness to retirement so yml cleanup
PRs can start with the cheap ones (small categories, item already good).

## Status

- [x] extractor + mechanical resolution (2026-08-05,
  `scripts/category_positions.py` → `data/categories/positions.{json,md}`):
  **273 specs → 122 matched + 30 label-only + 17 declared = 169 resolved**,
  22 ambiguous, 60 unmatched, 22 buckets. What it took: synonym expansion
  (OS says "Deputy of the X Duma"/"Senator of", Wikidata says "member of
  the..."), country-name suffixing for bare portfolio names ("Minister of
  Finance" + by), and transitive country agreement (candidate P1001 is
  often a subdivision — Kursk Oblast, not Russia; one P17 hop resolves it).
  Note: ~30 label-only rows have no country data on the item — several are
  exactly the positions `citizenship_plan.qs` will fix once applied.
- [x] verify the 169 resolved QIDs (agent pass: item is a real position, not a
  list article — Q6085548 is dual-typed! — and the office actually corresponds
  to the category's scope) — **done, and the result is the next entry.**
- [x] LLM tail for the 22 ambiguous + 60 unmatched (unmatched splits into
  naming variants the search missed vs. genuinely item-less offices — the latter
  feed a position-item creation list) — **done by the 2026-08-06 tail pass
  below**, and the creation list it wanted now exists with evidence attached:
  `coverage/offices_named.md`.
- [x] resolution verification (2026-08-05, 4 Opus agents over the 169
  resolved rows): **162 confirm / 6 replace / 1 reject / 0 unclear**,
  merged back into positions.json → **168 verified QIDs**, 66 scope notes
  (chamber granularity, predecessor boundaries, term qualifiers). Replaces
  were label-only Belarus ministries resolved to generic concepts; reject
  was ru Security Council members (item means *permanent* member; no
  correct item exists). Side finds: Q133268347/Q101483020 Volgograd
  duplicate (merge candidate), 7 label-only duma items lacking P1001 and
  not covered by citizenship_plan.qs, OAS SG item mislabeled.
- [x] pilot on 4 categories (2026-08-05): Crown_princes_of_Saudi_Arabia,
  ru:Мэры Москвы, Presidents_of_Interpol, ru:Депутаты Курской областной
  думы → 25 category members, 14 P39-gap candidates → **12 adds (21 dated
  statements, official-source refs), 2 rejects** →
  `data/positions/edit_plan.{md,qs}` ready for review. Both planted traps
  caught: Nebe = predecessor ICPC office (negcat candidate for the Interpol
  category), Resin = acting mayor only (ru Мэры Москвы sweeps in
  acting/deputies). Kursk agent cross-checked official convocation rosters
  (web.archive.org) and found ru.wiki errors (Chetverikov's convocations)
  and the declined-list-mandate trap. Review note: Ivanov's early-term
  rows cite the 5th-convocation roster URL as source — check before apply.
- [x] **bucket-category narrowing has a design** (2026-08-24):
  `recipes/enrichment_loop.md`. The narrowing *is* the enrichment loop with the
  country gazetteer instead of a single target — `wd/gazetteer.py:for_country`,
  measured at 62 items for Lesotho, 194 Czechia, 200 Iran, so it fits a cached
  prefix. **Unrun**, and it is the one part of that design with no evidence
  behind it: every run so far was a single-office spec whose gazetteer held one
  item, so the model never actually had to *choose*. 24 bucket specs — mayors in
  Guatemala, Nicaragua, Venezuela and Spain, Australian local councillors across
  seven states, Russian regional and district heads, party leaders, senior
  military leadership. Those are the rows reading 0 of 11 in
  `coverage/README.md`. Start with a national one (`Government_ministers_of_Spain`,
  `Министры Российской Федерации`) rather than a municipal one: Poland's run
  suggests municipal offices mostly have no item at all, so a mayoral bucket
  would test creation rather than choosing.
- [x] Middle East run (2026-08-05): Presidents_of_Yemen (2 rejects — Houthi
  SPC chairmen, disputed claim lives on the SPC item; Wikidata's Q878256
  holder line is the recognized succession), Sultans_of_Oman (1 historical
  add, 890 CE — item practice covers pre-Busaidi rulers),
  Members_of_the_Palestinian_Legislative_Council depth=1 (38 candidates →
  **36 adds / 2 unclear**, every one checked against CEC primary rosters;
  headline: **Abbas's PLC-1996 seat may be an encyclopedia myth** — absent
  from the CEC's 88-name roster, parked unclear), and the first **bucket
  narrowing** pass, Government_ministers_of_Bahrain depth=1 (49 people →
  **22 adds across 16 resolved Bahraini offices, 14 offices need item
  creation** — all the "Minister of State for X" junior posts are missing
  from Wikidata; 3 true rejects/negcats; 2 wrong existing P39s flagged for
  surgical fix: Q6983237→Q108884463, Q16730783→Q115344290; dup P39s on
  Q16190522/Q16115995/Q20418017). GPC Yemen closed mechanically:
  **no-p39-target** — the GPC (Q1460677) is a party, membership is P102;
  the yml position block models party membership as a position.
  Combined plan now: **84 modern statements** in edit_plan.qs, lint-clean.
  Tooling: lookup_position default search depth raised (generic labels
  like "Minister of Health" bury the right country's item deep in the
  ranking); yml depth=0 on PLC/Bahrain specs means the direct specs catch
  almost nobody — members arrive via the depth-7 sweeps.
- [x] **retirement report built** (2026-08-24). `scripts/spec_report.py` gives
  every spec one of seven dispositions and writes `coverage/petscan_specs.md`;
  `scripts/retirable.py` builds the real cohort and writes
  `coverage/petscan_retirable.md`, the PR checklist, accumulating so a spec keeps
  the date it was first found removable. Two findings the plan above could not
  have known: the pre-gate gap **overstates the queue**, sometimes to zero
  (`Prime_ministers_of_Spain` reads 101 and has none — all born before 1920), so
  44 specs are removable against the 22 a pre-gate count finds; and the ceiling
  is **not** made of Wikidata problems — of 209 targets only ~80 are positions
  `wd_peps` emits, and 127 are blocked on OpenSanctions' own `SUB_TYPES` policy
  (`coverage/wd_categories.md`). Those queries cannot be retired by enriching
  anything.
- [x] **tail resolved + `wikidata_id`s written back (2026-08-06).** Two
  wording-independent signals closed most of what name search couldn't
  (`scripts/category_tail.py`): the Wikipedia **category item's P301**
  main topic, and a **P39 tally over the category's members**. Then 8 Opus
  agents adjudicated all 104 tail+bucket rows (`verdicts/tail_*.jsonl`):
  47 replace / 22 no-p39-target / 19 create / 16 confirm.
  **284 specs → 238 resolved, 23 create, 23 no-p39-target**, rendered by
  `render_category_qids.py` into `resolved.json` + `qid_plan.md` +
  `create_positions.qs` (22 CREATEs) and written into the yml by
  `patch_categories_yml.py` (215 insertions, additive, idempotent).
  What it took:
  * `normalize=1` on wbgetentities — every wiki localizes the category
    namespace ("Категория:", "Kategorie:"), so `Category:` misses without it.
  * Tightening the score: `country_match` + tally lead are **not**
    independent for a big country, because regional deputies later hold the
    national seat — that pair alone matched "member of the State Duma" to
    four regional dumas. Now the name or the P301 must be one of the two.
  * Reading the spec list from the yml, not the cached positions.json: 11
    Lithuanian specs had been added upstream since the snapshot and were
    never resolved at all (4 of them need new items).
  * Deduping creates by label — the en and es Ecuador specs name one office.
- [x] byproduct: `scripts/category_langcheck.py` — **38 of 594 specs match
  no category page at all** (`langcheck.md`). The crawler hands `language`
  to PETScan, which defaults to `en`, and titles are case-sensitive after
  the first letter: 8 Czech specs query enwiki for cswiki titles, 10 Russian
  oblast specs die on `Думы` vs `думы`, plus `White_House_Counsels`,
  `OSCE_Secretaries_General`, `Under-Secretaries-General…`. Silent: no
  members, no error. Separate PR.
- [ ] user decisions pending (see `qid_plan.md`): the 22 CREATEs; the
  Security Council row (yml declares Q38715670 "**permanent** member",
  a strict subset — create a generic member item, or drop the id?); whether
  bucket rows should take a generic QID at all; Ecuador's
  create-vs-stretch-Q6085548 call; the Australian local-councillor rows
  (Wikidata models per council, ~200 items).
- [x] **4 duplicate position items merged (2026-08-06, wikibase-cli)**, all
  from the bulk-created Q1332683xx series: Q133268398→Q115242140 (Dagestan),
  Q133268337→Q96324124 (Moscow City), Q133268358→Q124755389 (KhMAO),
  Q133268347→Q101483020 (Volgograd). Gate before merging: identical P361
  body + P1001 jurisdiction, no sitelinks on either side, and **every stub
  holder already held the keeper** (overlap = full stub count, 0 unique) —
  the duplicated P39 statements were the evidence, not a consequence.
  Verified after: redirects live, P31/P279 unioned (nothing dropped).
  Note `wb merge-entity <from> <to>` merges the *first* into the second; a
  `--dry` run caught that zsh doesn't word-split, so a `$pair` variable
  arrived as one argument.
- [ ] follow-up to those merges: **270 people still carry a P39 pointing at
  a redirect** plus an identical one on the keeper, so the seat shows twice
  and WDQS counts don't include the redirect side. Checked safe to strip:
  comparing actual qualifier property/value sets (not just counts — equal
  counts can hide different convocation terms), all 270 redirect-side
  statements are fully covered by an identical keeper-side statement, 0
  would lose a distinct tenure. Needs wikibase-cli (QS cannot remove).
- [x] **the item layer behind the resolved QIDs, audited (2026-08-23).** The
  QIDs are written into the yml; this asks whether the *items* carry enough to be
  read. `scripts/audit_os_positions.py` scores all **209 distinct QIDs** with
  `wd/shape.py` plus zavod's `INTL_ORGS` registry (loaded off `igo.py`, not
  transcribed), and reports the one gate that stops each item rather than every
  gate it fails: **80 discoverable today, 101 upstream, 13 IGO-undecided by
  design, 11 untyped, 3 surgical, 1 country-less.** Then
  `scripts/render_os_positions_plan.py` → **116 statements over 97 items**
  (`data/os_positions/`), gates pinned by `scripts/check_os_positions.py`.
  **115 uploaded 2026-08-23 19:02 and verified against live Wikidata** with
  `render_os_positions_plan.py --verify`, which suppresses the diff so the tables
  emit everything they would ever propose and reports what is not there: 188 of
  189. The one outstanding line is `Q7241113` `P279` `Q965043`, decided after the
  upload. The 86-item generic-`P31` lane is surgical and is in
  `tasks/followups.md`; `wd/shape.py` was left alone deliberately.
  Measurements in `research/position_items.md` §8b; the committed ledger is
  `coverage/wd_categories.md` (`data/` is gitignored, so the run's own output
  cannot be the record). Its headline: **80 of 209 targets are positions
  `wd_peps` would emit**, 127 are blocked on OpenSanctions' own position policy
  and 2 on Wikidata — so these specs cannot be retired by enrichment. What it
  took:
  * The lane I expected to be largest was already closed — **24 of 24** IGO posts
    carry a registry org link.
  * The biggest blocker is not Wikidata: `Q4175034` legislator confers no
    `role.pep` (79 seats), `Q5230427` and `Q42178` are absent from `SUB_TYPES`.
    Left alone deliberately — retyping 79 correctly-modelled seats to trip a
    consumer's sentinel is what the recipe forbids.
  * `Q104881755` Mayor of Managua is the **only** item of the 209 that resolves
    no country, so zavod drops it and every holder with it. Its `P1001` was first
    written as `Q3070` — San José, Costa Rica — reproducing the QID-from-memory
    failure `GAP_TARGETS_BY_COUNTRY` documents, within the hour. `verify_body`
    now refuses it, and `check_os_positions.py --online` pins that.
  * Two of three `P2389` rows were already on their items: `wd/shape.py`'s gaps
    answer "does the item carry this property", which is the wrong question for a
    decided target. The renderer now diffs the exact claim.
  * The ICC presidency looked unmeasurable by label (1-1-1-1 over eleven items)
    and was decided structurally instead: both the ICJ and ECtHR presidencies
    subclass **their own court's judgeship**, so `Q7241113` takes `Q965043` — an
    item in this same cohort. A label tally would have said `Q3188089` chief
    justice, which is a national supreme-court role.
  * Three gate bugs, each costing a correct statement: a U+200E left-to-right
    mark inside `Q4467481`'s label; "Volgograd *Regional* Duma" against its body's
    "Volgograd *Oblast* Duma"; and demanding `P17 == [Q159]` when
    `Q4146671` carries Russia *and* the Soviet Union and `Q4070652` carries no
    `P17` at all.
- [x] **43 specs retired** (2026-08-24) by `scripts/retire_specs.py`, which
  comments the block out with the date and the reason on it rather than deleting
  it, because a retirement is the thing most likely to need reverting. The yml
  went 594 → 551 specs and 284 → 241 with a `position:` block. The remaining
  removable ones are in `coverage/petscan_retirable.md`.
- [x] **the creation queue has evidence attached** (2026-08-24).
  `scripts/office_ledger.py` → `coverage/offices_named.md`: 79 offices an
  enrichment run named and could not place, each with the holder attested to have
  held it, the dates, and the sentence saying so. That is what the "unmatched →
  position-item creation list" line above asked for, and what nine campaigns'
  creation lists never had — `wd/create.py:guard`'s holder floor is already met.
  Also 6 ambiguous and 4 refused for naming no polity they govern.
