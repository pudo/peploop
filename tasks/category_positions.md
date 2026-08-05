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
  positions-campaign pipeline (PETScan members → article verification →
  P39 batch, `tasks/positions.md`).
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

Downstream (separate steps): PETScan member fetch per resolved category →
P39 gap via `position_gap.py` → per-person verification agents → QS batch;
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
- [ ] verify the 169 resolved QIDs (agent pass: item is a real position,
  not a list article — Q6085548 is dual-typed! — and the office actually
  corresponds to the category's scope)
- [ ] LLM tail for the 22 ambiguous + 60 unmatched (unmatched splits into
  naming variants the search missed vs. genuinely item-less offices —
  the latter feed a position-item creation list, cf. tasks/positions.md)
- [ ] pick pilot categories → PETScan members → `position_gap.py` →
  verification agents → .qs
- [ ] bucket-category narrowing design (22 specs: "Minister of the Russian
  Federation", "Governor of a Russian Region", Australian local
  councillors...) — per-person office identification from articles
- [ ] retirement report: per-spec P39 coverage (members_total / p39_have /
  p39_planned / p39_gap) → ranked list of yml sections whose
  pseudo-positions can be dropped
- [ ] eventually: propose `wikidata_id`s back into wd_categories.yml so the
  crawler emits real positions instead of wd-cat hashes; drop `position:`
  blocks flagged retirable
