# Follow-ups

Actionable leftovers from closed campaigns — the human gates and byproducts,
one line each. Method lives in `recipes/country_sweep.md`; campaign records in
`regression/`. Strike lines as they are done.

## Batches awaiting QuickStatements review/upload

- [ ] `data/ecuador/edit_plan.qs` (98 statements)
- [ ] `data/belarus/edit_plan.qs` (10) — check the industry-ministers date overlap first
- [ ] `data/czechia/edit_plan.qs` (6)
- [ ] `data/spain/edit_plan.qs` (111 lines / 110 statements)
- [ ] `data/uae/edit_plan.qs` (94) — one row the backtest contradicts:
      Q1380993 Saqr bin Mohammad al-Qassimi → Q110964697 Ruler of Sharjah
      (1972), a spell the community records on Q110964704 Ras Al Khaimah;
      the two thrones are one dynasty and holders are filed under either
- [ ] `data/jurisdictions/diplomatic_plan.qs` + `diplomatic_tail.qs` (572 + 96)
- [ ] IGO link batches `data/igo/igo_links2_p2389.qs` / `igo_links2_p361.qs`

## Position/body items to create (`scripts/create_offices.py`, dry first)

- [ ] `--country ae`: the 19 missing emirate cells (deputy rulers, crown
      princes, executive-council chairs, ruler's representatives) + member of
      the Federal Supreme Council, judge of the Federal Supreme Court, Central
      Bank governor. Six executive-council *bodies* must exist first.
- [ ] Czechia: 4 portfolio items + the two supreme courts (45 members waiting)
- [ ] Lithuania: 3 final-instance judgeships + deputy prosecutor general
- [ ] UAE: the ~49 unmapped cabinet portfolios (best-attested: Planning,
      Public Works, Labour and Social Affairs, Supreme Council Affairs,
      Economy and Trade); the 4 pre-union polity rulerships (Dibba,
      Al Hamriyah, Al Heera, Kalba)

## Surgical (wikibase-cli, stop-and-ask — never in a batch)

- [ ] remove Otakar Fischer's 1939 term from Q20058795
- [ ] merge Crown Prince of Dubai: keep Q30635458, fold in Q125497760
- [ ] merge Ruler of Dubai: Q114315948 (empty, holds the sitelinks) into Q110964267 (all structure, no sitelink)
- [ ] merge the two empty UAE happiness ministers: Q39086062 (wrong P31) + Q22674768
- [ ] Q125497761 (Deputy Ruler of Abu Dhabi): add `en` label + description
- [ ] Q110964267 Ruler of Dubai: mis-filed `P31 = Q294414` / "cabinet position" description
- [ ] Spain labour + education: two items competing per office (Q44487637 vs
      Q87001438 for labour) — merge or rank decision
- [ ] SWF org defects flagged by the UAE census: ADIA Q334956 `P169` (wrong
      property, wrong person, undated); ADQ Q115774776 / Q124328392 duplicate;
      ADNOC Q166729 `P3320` points at a body; Etihad Q212304 stale `P169`

## `wd_categories.yml` write-backs (PR against opensanctions)

- [ ] Belarus: `wikidata_id` for all 12 specs (resolutions verified)
- [ ] Czechia: five `wikidata_id` swaps, the bucket split, drop the empty `Lists_of_members_…` spec
- [ ] Spain: 19-way autonomy split (QIDs in `scripts/es_offices.py:COMMUNITIES`),
      Congress era items, second prime-minister spec (Q16020745), mayor and
      deputy-PM spec fixes
- [ ] UAE: `depth` + `language: ar` siblings on the two `ae` specs; `position:`
      blocks for the seven rulerships, the federal offices and ~40 ministerial items
- [ ] the retirement report over all resolved specs

## External

- [ ] `rigour`: `ae-sh` → Q289693 and `ae-fu` → Q4045 are *cities*; the
      emirates are Q188810 and Q4091
- [ ] OpenSanctions PR #5318 (IGO second pass) review; production re-crawl
      once merged
- [ ] Lithuania: Q140592938 "Minister of Economy and Innovation" looks like a
      duplicate — merge candidate

## Item-creation rosters (people, not offices — OS PEP coverage)

- ~1,100 Ecuadorian ministers with no Wikidata item (`data/ecuador/roster_audit.md`)
- 132 UAE roster rows with no item (`data/uae/roster_audit.md`)
- 82 Cortes de Cádiz presidents, 1810–1814 (`data/spain/roster_audit.md`, Congress `no identity` column)
- 100 undated Presidentes del Consejo de Ministros (per-person gap on Q16020745)

## Deferred lanes

- UAE lane E (sovereign wealth funds) — creation-first; see the recipe's SOE note
- Spain: the four portrait-grid ministry pages (Fomento, Hacienda, Economía,
  Interior) need a different source; Defensa needs per-row office routing
- Belarus: the 14 portfolios outside the yml, and the parliament seats
- Ecuador: lanes A / C / C2 (presidential line, legislature seats,
  predecessor-chamber presidencies)
