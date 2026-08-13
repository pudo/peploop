# Follow-ups

Actionable leftovers from closed campaigns — the human gates and byproducts,
one line each. Method lives in `recipes/country_sweep.md`; campaign records in
`regression/`. Strike lines as they are done.

## The QuickStatements merge — fixed, and repaired 2026-08-13

**19 of 21 merged statements split back into one statement per tenure**
(`scripts/repair_merged.py`): ecuador 4, czechia 1, courts 2, positions 10 —
including `Q4196259` and `Q109487160`, which each carried *four* starts and four
ends on one statement — plus 2 of the UAE's 4. Verified afterwards: no statement
in any repaired batch still carries more than one date, and qualifiers like
`P2868` and the references survived the split.

The API halves of **kuwait (117 statements / 50 people)**, **ecuador (28 / 14)**
and **spain (32 / 13)** are applied and verified: 177 tenures, all as separate
statements, none date-merged.

- [ ] **The UAE batch is now refused by `wd/validate.py` — 12 defects — and
      should not be uploaded.** The same mechanism cuts both ways, which is the
      thing worth remembering. For a person with two genuine spells, the QS merge
      *destroys* the pairing. But 10 of the UAE's 12 groups are one tenure the
      run emitted as **fragments** — one line carrying only `P582`, another only
      `P580`, describing the same spell — and there the merge silently
      *repaired* it: `Q215477`, `Q107596718` and `Q12178848` all hold one
      correct, complete statement on Wikidata today. So QS's merge was masking a
      parser defect, `conflicting_tenures` now catches it, and routing those to
      the API would have written two half-dated statements where one good one
      exists. Find out why the UAE rosters fragment a spell across two records
      before re-rendering; the other 2 (`Q1573260`, `Q22687591`) are genuinely
      two sources disagreeing about an end date and need reading.
- [ ] the 2 UAE statements the repair refused, for the same reason — its
      verification would not touch a statement whose live dates are not what the
      batch sent, which is what stopped it breaking the 10 correct ones

### How it was fixed

QS matches a line on subject + property + **value** alone and folds the line's
qualifiers into the statement it finds, so a person with two spells in one
office got a single P39 carrying two `P580`s and two `P582`s, unpairable. `wd/validate.py:collapsing_groups` detects them (and `check` now
*refuses* to render one into a `.qs`), `render_edit_plan.py` partitions them into
`edit_plan_claims.json`, and `scripts/apply_claims.py` writes them through
`wb edit-entity`, `--dry` by default and guarded by `claims_written.json`.
Every campaign has been re-rendered through the split.

- [x] **[#1](https://github.com/opensanctions/wd-vibes-workbench/issues/1)** —
      done for 19 of 21. `scripts/repair_merged.py` adds the split-off tenures
      *before* stripping the surplus qualifiers, so an interruption leaves a
      visible duplicate rather than a lost date — which is exactly what saved it
      when the first run failed on a bad `P813` reference value: every add was
      rejected, no removal ran, and nothing on Wikidata changed.
- [x] `data/courts/edit_plan.qs` (2) and `data/positions/edit_plan.qs` (10)
      **had been applied** after all, and are repaired. They still cannot be
      re-rendered — their verdicts use an older schema (`statements: null`) that
      `render_edit_plan.py` cannot read — so the repair took its pairings
      straight from the `.qs`, which is the only record of them.

## Batches awaiting QuickStatements review/upload

Each campaign is now **two files reviewed together** — `edit_plan.qs` in the
QuickStatements importer, and `edit_plan_claims.json` via
`scripts/apply_claims.py --campaign <name>` (dry first). The counts below are
`.qs statements + API statements`.

- [x] **kuwait, API half — 117 statements for 50 people, applied 2026-08-13.**
      Verified on Wikidata afterwards: all 117 tenures exist as *separate* P39
      statements and none carries more than one `P580`/`P582` — the behaviour QS
      could not produce. Ledger: `data/kuwait/claims_written.json`; edit log:
      `data/kuwait/applied.jsonl`. A re-run is a no-op.
- [ ] **kuwait, QuickStatements half — 253 statements**, still to upload. This
      one has to go through the importer rather than the API, so that the batch
      stays a single mass-revertable EditGroups entry.
- [ ] ~~kuwait — 253 + 117~~ (370 statements: 368 P39, 2 P53). Backtest is clean:
      target agreement 100% on all 21 offices with comparable rows, and all 19
      date conflicts were read and are source disagreements rather than parse
      defects — the ar ministry tables close each term at the successor's amiri
      decree where Wikidata records the handover, and the roster dates the
      appointment where Wikidata dates the swearing-in. The API half is unusually
      large (50 of 358 people) because the four Assembly rolls give one member up
      to four consecutive terms in the same seat
- [ ] **spain — 79 to upload**; its API half (32 / 13 people) is applied
- [ ] **uae — blocked, do not upload.** `wd/validate.py` refuses it: 12 groups
      are one tenure emitted as fragments or dated twice (see the top of this
      file). Also still open: one row the backtest contradicts —
      Q1380993 Saqr bin Mohammad al-Qassimi → Q110964697 Ruler of Sharjah
      (1972), a spell the community records on Q110964704 Ras Al Khaimah;
      the two thrones are one dynasty and holders are filed under either
- [ ] **saudi — 43 + 0** (29 P39, 9 P53, 3 P25, 2 P22) — the P22s are the two to
      read first, being the only statements in the batch derived from a name
      rather than from a table
- [ ] **belarus — 6 + 0** — check the industry-ministers date overlap first
- [ ] **ecuador — 50 to upload**; its API half (28 / 14 people) is applied, and
      its 4 merged statements are repaired. Ecuador's own batch was applied some
      time before 2026-08-13, so 50 is what the community has *not* since
      recorded independently
- [x] **czechia** — applied earlier, its one merged statement repaired, and a
      re-render now yields nothing at all
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
- [ ] `--country sa`: 5 offices dry-run clean and awaiting minting — Second
      Deputy Prime Minister (enwiki *redirects* its article to the Crown Prince,
      so resolving it by title silently lands on Q12251224) and the
      governorships of Najran, Northern Borders, Al-Bahah and Al-Jouf. They take
      `P279 = Q98786082` "emir of province" and `P1001 = <province>`, measured
      off the eight that exist — the `agency_head` shape would have made them
      "directors". **Jazan is blocked by the holder floor** (enwiki has no
      `Governors of Jazan Province` category and no roster names them), which is
      the guard working, not a bug.
      The Shura chairmanship needed no creation after all: Q22688060 exists with
      `P17 = Q851` and **zero holders**, which is why a census printing only
      items with a holder missed it. It now carries 3 statements in the batch.
- [ ] Saudi Arabia: Minister of Human Resources and Social Development — the
      *ministry* is Q12250983 and the minister has no item, so the sitting
      holder routes to `""` rather than assert the 2019 rename of Q59507344
- [ ] Saudi Arabia: the rulership of the first and second Saudi states. 19 of
      the 22 rulers on `ar:قائمة حكام آل سعود` have a person item and no office
      to hold — the Imamate of Diriyah and the Emirate of Nejd are not the
      Kingdom's throne (`data/saudi/roster_audit.md`, `earlier_states`)

- [ ] Kuwait: the deputy speakership of the National Assembly — **Q120913227 is a
      list article typed `P31 = Q4164871`**, so the office has no usable item and
      17 dated rows on `ar:مجلس الأمة الكويتي` are waiting on one
- [ ] Kuwait: First Deputy Prime Minister (9 dated rows on `ar:مجلس الوزراء
      الكويتي`) and Deputy Commander of the National Guard (4 rows on
      `ar:الحرس الوطني (الكويت)`) have no item either. All three are deputy
      shapes and `wd/create.py` has no archetype for one that is not a deputy
      *ruler* — measure the convention before minting rather than reusing it
- [ ] Kuwait: the Deputy Rulership of Kuwait (1921–1961), 2 rows routed to `""`
      by `kw_offices.crown_prince` — a distinct office from the crown princedom
      that succeeded it

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
- [ ] Saudi item-layer defects found by the position census:
      Q20388005 "list of rulers of Saudi Arabia" is a **list article carrying 2
      P39 holders**; Q6867237 (Ministry of Interior), Q12250935 (Ministry of
      Energy) and Q12250983 carry P39 holders though they are *bodies*;
      Q12251224 Crown Prince has a stray `P31 = Q13406463` (Wikimedia list
      article) among its five types; "Minister of Interior" and "Minister of
      Energy" each have a competing item (Q114452638 / Q6867237 and
      Q110983168 / Q12250935) — merge-or-rank decisions
- [ ] Kuwait item-layer defects found by the position census:
      **Q139413655 "Monarch of Kuwait"** carries 1 holder, no `P31` and
      `P279 = Q116` — a stray third item for a throne already held by
      Q100877419 (17 holders) beside the correctly-typed list Q246932;
      **Q128977192 "Kuwaiti Minister of Public Works"** (1 holder) duplicates
      Q110526419 (4); **Q110532468** Governor of the Central Bank is typed
      `P31 = Q294414` "cabinet position"; **Q124394695 "Governor of Kuwait"** is
      scoped to no country at all — merge-or-rank decisions
- [ ] Wikipedia fix, not Wikidata: `ar:وزارة المالية (الكويت)` writes eight of
      its 29 date ranges **backwards** ("1965-1959", "1981-1967"), an RTL
      authoring artifact — the rows chain correctly read the other way round.
      The lane is deferred rather than fixed with a global "swap if reversed" in
      `parse_period`, which would touch every campaign and could mask a real
      parse defect
- [ ] Wikipedia fix, not Wikidata: `ar:قائمة أعضاء مجلس الشورى السعودي
      (1438-1442هـ)` states in its lead that it lists the **1434–1438** term.
      The table is the later council (a different vice-chairman), so the prose
      is a copy-paste error — the title was believed over it
- [ ] Wikipedia fix: `en:Descendants of Ibn Saud` lists
      `Sara bint Mashour Al Saud` in two generations at once, and
      `Abdulaziz bin Fahd bin Turki II bin Abdulaziz Al Saud` among the
      *grandsons* though his own name makes him a great-grandson. Both are
      skipped as `father.generation_contradicted` / `father.unresolved`

## `wd_categories.yml` write-backs (PR against opensanctions)

- [ ] Belarus: `wikidata_id` for all 12 specs (resolutions verified)
- [ ] Czechia: five `wikidata_id` swaps, the bucket split, drop the empty `Lists_of_members_…` spec
- [ ] Spain: 19-way autonomy split (QIDs in `scripts/es_offices.py:COMMUNITIES`),
      Congress era items, second prime-minister spec (Q16020745), mayor and
      deputy-PM spec fixes
- [ ] UAE: `depth` + `language: ar` siblings on the two `ae` specs; `position:`
      blocks for the seven rulerships, the federal offices and ~40 ministerial items
- [ ] Kuwait: `language: ar` siblings throughout — en.wikipedia has **no
      category at all** for the emirs, the crown princes, the House of Sabah, the
      Assembly's members or its speakers, while `ar:أعضاء مجلس الأمة الكويتي` has
      437 members at depth 1 and `ar:وزراء كويتيون` 305 against en's 80; plus a
      `position:` block per portfolio item and the Assembly seat (Q21295986)
- [ ] Saudi Arabia: `language: ar` siblings throughout (`ar:آل سعود` has 392
      members at depth 1 against enwiki's 193, and `ar:وزراء سعوديون` has 49
      portfolio subcategories against enwiki's 41); a `position:` block per
      province governorship; the Consultative Assembly seat (Q21328601)
- [ ] the retirement report over all resolved specs

## External

- [ ] `rigour`: `ae-sh` → Q289693 and `ae-fu` → Q4045 are *cities*; the
      emirates are Q188810 and Q4091
- [ ] OpenSanctions PR #5318 (IGO second pass) review; production re-crawl
      once merged
- [ ] Lithuania: Q140592938 "Minister of Economy and Innovation" looks like a
      duplicate — merge candidate

## Item-creation rosters (people, not offices — OS PEP coverage)

- **10 wives of Ibn Saud have no Wikidata item, and they hold the remaining
  P25 gap** — 20 of his children are waiting on them, listed per wife in
  `data/saudi/kinship_audit.md`. Only 11 of his ~22 wives have an item at all,
  which is the ceiling on the mother lane: a wife with no item cannot be the
  value of anyone's P25. This is the single highest-leverage creation list in
  the Saudi campaign.
- 31 Kuwaiti roster rows with no item (`data/kuwait/roster_audit.md`), 15 of
  them the whole of `en:Ministry of Justice (Kuwait)`'s bullet list of ministers
- **936 Kuwaiti Assembly members are `category_only`** — in one of
  `ar:أعضاء مجلس الأمة الكويتي`'s 22 per-term subcategories but named by no
  roster, because only four of the 24 per-term pages tabulate their members.
  The per-term category *is* ar.wikipedia asserting membership in that term, so
  this is the highest-volume seat-coverage list the workbench has measured; it
  needs a source that dates the other eighteen terms, not a relaxed rule
- 324 Consultative Assembly members with no Wikidata item, from three term
  rolls of 150 (`data/saudi/roster_audit.md`, `shura_member`)
- ~1,100 Ecuadorian ministers with no Wikidata item (`data/ecuador/roster_audit.md`)
- 132 UAE roster rows with no item (`data/uae/roster_audit.md`)
- 82 Cortes de Cádiz presidents, 1810–1814 (`data/spain/roster_audit.md`, Congress `no identity` column)
- 100 undated Presidentes del Consejo de Ministros (per-person gap on Q16020745)

## Deferred lanes

- UAE lane E (sovereign wealth funds) — creation-first; see the recipe's SOE note
- Spain: the four portrait-grid ministry pages (Fomento, Hacienda, Economía,
  Interior) need a different source; Defensa needs per-row office routing
- Belarus: the 14 portfolios outside the yml, and the parliament seats
- Kuwait: the finance ministry (29 rows, reversed ranges — see the surgical
  list); the sitting cabinet on `en:Cabinet of Kuwait` / `ar:مجلس الوزراء
  الكويتي`, whose 22 rows carry offices but date only under a "since" /
  "التشكيل الحكومي الحالي" heading; the six governorates (only Q127163995 and
  Q127164105 exist, one holder each, and no article tabulates governors); the
  Central Bank governorship (Q110532468 has an item and no roster in either
  language); `ar:قائمة وزراء الدولة لشؤون الإتصالات (الكويت)`, which carries no
  table; P25/P22 for the House of Sabah — both `en:House of Sabah` and
  `ar:آل صباح` render their genealogy as `{{Tree chart}}`, parent-child edges in
  box-drawing characters, not the heading-per-generation article `wd/kinship.py`
  reads
- Saudi Arabia: the 12 provinces whose article tabulates no governors (only
  `ar:منطقة الرياض` does); `ar:قائمة أعضاء مجلس الشورى السعودي (1446-1450هـ)`,
  the current term, which has neither a table nor a list to read; the health
  and interior ministries' rosters, which date **only** in Hijri (21 and 9 of
  their rows respectively yield no term at all — see the Hijri note in
  `scripts/sa_offices.py`)
- Ecuador: lanes A / C / C2 (presidential line, legislature seats,
  predecessor-chamber presidencies)
