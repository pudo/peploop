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

**All 21 are now clean**, the last two by source judgement rather than mechanically:

- `Q22687591` Hamdan bin Mohammed Al Nahyan held the deputy premiership
  `1977-12-20 – 1989-10-11`; he **died in office** on that date, and his article
  records serving *alongside* Maktoum bin Rashid "(1979–1989)". The competing
  `1979-07-01` was only the end of the *third cabinet*.
- `Q1573260` Hamdan bin Zayed: three sources gave three ends — `2009-05-10`
  (the deputy-PM list), `2009-05-12` (the cabinet list) and `2009-03-04` (his own
  infobox). Kept **2009-05-12**, the day the ninth cabinet took office, which is
  when an eighth-cabinet deputy premiership necessarily ends. Worth knowing that
  the cabinet page applies that date to every member of the cabinet, so it is
  structural rather than an attestation about him.

- [x] **The 12 UAE defects are fixed** (`merge_terms`), and were a parser defect
      rather than the merge. 10 of the 12 were one tenure emitted as
      **fragments** — a line carrying only `P582` and another only `P580` for the
      same spell — because the deputy premiership is fed by *two* pages: the
      dedicated succession list and `List of cabinets of the UAE`, which prints
      one section per cabinet and dates only the changes. QuickStatements
      reassembled each pair, so `Q215477`, `Q107596718` and `Q12178848` are
      *correct* on Wikidata: the merge had been quietly covering for it. A row
      with no start of its own now continues the term the earlier section opened,
      and `scripts/check_dates.py` pins all seven shapes.

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
`scripts/apply_claims.py --campaign <name>` (dry first).

**Checked against live Wikidata on 2026-08-13, line by line — because four of
these checkboxes were wrong.** Two questions, and they are not the same one:
whether the batch that was *rendered* went in, and what a re-render proposes
*now* — the latter can be non-zero on a fully applied campaign, because the
rosters have moved on and because the engine has since learned to read rows it
used to drop.

| batch | its own lines, on Wikidata | a re-render today proposes |
|---|---|---|
| kuwait | 370 of 370 | 0 |
| uae | 94 of 94 | 0 |
| czechia | 18 of 18 | 0 |
| courts | 106 of 106 | (schema too old to re-render) |
| positions | 84 of 84 | (ditto) |
| saudi | 43 of 43 | **14** |
| ecuador | 177 of 177, + 28 API | **50** |
| spain | 32 — the API half only | **79** |
| belarus | 10 of 16 | **6** |
| **jordan** | **161 API statements for 60 people, applied 2026-08-13** | **220 `.qs`, not yet uploaded** |

Now that the state reads are fresh (`campaign.STATE_MAX_AGE`), the right-hand
column is simply what `render_edit_plan.py` prints. **Trust that, not this
list** — every count here was wrong at some point today, and it is the one thing
in this file that cannot go stale.

- [x] **kuwait, API half — 117 statements for 50 people, applied 2026-08-13.**
      Verified on Wikidata afterwards: all 117 tenures exist as *separate* P39
      statements and none carries more than one `P580`/`P582` — the behaviour QS
      could not produce. Ledger: `data/kuwait/claims_written.json`; edit log:
      `data/kuwait/applied.jsonl`. A re-run is a no-op.
- [x] **kuwait, QuickStatements half — 253 statements, applied 2026-08-13.**
- [x] ~~kuwait — 253 + 117~~ (370 statements: 368 P39, 2 P53). Backtest was clean:
      target agreement 100% on all 21 offices with comparable rows, and all 19
      date conflicts were read and are source disagreements rather than parse
      defects — the ar ministry tables close each term at the successor's amiri
      decree where Wikidata records the handover, and the roster dates the
      appointment where Wikidata dates the swearing-in. The API half is unusually
      large (50 of 358 people) because the four Assembly rolls give one member up
      to four consecutive terms in the same seat
- [ ] **spain — 79 to upload**; its API half (32 / 13 people) is applied
- [x] **uae — applied 2026-08-12 07:33** via QuickStatements, all 94 lines.
      Verified twice over: every line is present with its own dates (58 dated,
      36 undated P53), and the revision history shows
      `Pudox … #quickstatements` on each subject at that minute. This entry said
      "awaiting upload" for a day; **four batches turned out to be applied
      already** (courts, positions, uae, saudi), so trust a re-render or a diff
      against live Wikidata, never a checkbox here.
      Still open: one row the backtest contradicts — Q1380993 Saqr bin Mohammad
      al-Qassimi → Q110964697 Ruler of Sharjah (1972), a spell the community
      records on Q110964704 Ras Al Khaimah; the two thrones are one dynasty and
      holders are filed under either
- [x] **saudi — applied**, all 43 lines (29 P39, 9 P53, 3 P25, 2 P22), including
      the two P22s that were flagged for reading first as the only statements
      derived from a name rather than a table. Worth a look after the fact
- [ ] **belarus — 6 left of 16**; the other 10 are on Wikidata. Check the
      industry-ministers date overlap first
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

## Jordan (added 2026-08-13)

**Two duplicate P39 statements to remove — surgical, stop and ask.**
`Q100258645` Nayef Al-Fayez carries `P39 = Q110066643` twice over for each of two
spells. Cause: the first `apply_claims` run for this person reported `1 failed`
after `wikibase-edit` retried thirteen times against query-service lag — but the
edit had already succeeded server-side, so the ledger recorded nothing and the
retry wrote it again. The API de-duplicates nothing; the ledger is the only guard
and it cannot see a write that succeeded after the client gave up. Remove one of
each pair:

    wb remove-claim Q100258645$4C14170D-86BF-4688-BB99-95C707F1839B
    wb remove-claim Q100258645$FA71F397-61F4-487B-A9BA-98A1B216F3FF

Keep `$20832BE6…` (2012-10-11–2013-03-30) and `$D7ED51B7…` (2018-06-04–2020-10-12).
All 58 other people written through the API were checked and are clean. Worth a
guard in `wd/write.py`: on a timeout or maxlag failure, re-read the item before
reporting failure, because "failed" and "succeeded slowly" are indistinguishable
from the client side.

**Item-layer defects — surgical, stop and ask.**
* Q54900644 "Crown Prince of Jordan" (1 holder, en label) and Q60061190
  "ولي العهد (الأردن)" (0 holders) are **two items for one throne**. No office was
  declared for the crown princedom because of it; merge, then the lane is a
  five-row roster away.
* Q98231908 "وزير الأوقاف والشؤون والمقدسات" (2 holders, **no P17**) duplicates
  Q110066975 (1 holder, P17=Q810). The campaign routes to the P17-scoped one and
  the backtest reports the five rows the community filed on the other.
* Q110066504 "Minister of Labour" / Q133851928 "Minister of Labor", and
  Q110065394 "Minister of Water and Irrigation" / Q137704254 "وزير المياه والري"
  — one pair each, competing for the same era rather than succeeding it.
* Q6597909 "list of speakers of the House of Representatives of Jordan" is a
  **list article carrying 2 P39 holders** — the Q20388005 shape again.
* Q136650633 "عضو في مجلس النواب الأردني" (1 holder) duplicates Q17524418 (82).
* Q14625123 "King of Jordan" carries **no P17**, which is why the P17 census
  misses it entirely; add `P17 = Q810`.

**Byproducts (people with no item — OS PEP coverage).**
* **958 cabinet roster rows resolve to no Wikidata item**, out of 1,824. This is
  the largest single item-creation list this workbench has measured for a country
  whose ministries already have items.
* **232 `category_only`** — in `ar:وزراء أردنيون` or a Senate category but named
  by no roster row this campaign read.
* 40 of the 87 people listed in the Hashemite descendant sections have no
  article, listed per parent in `data/jordan/kinship_audit.md`.

**Portfolios with no item (creation-first, ~319 rows).** Planning
(`وزيرا للتخطيط`, 21 rows), Communications/`مواصلات` (21), Supply/`تموين` (10),
Municipal & Rural Affairs (8), Posts & Telecommunications (6), National Economy
(7), Political Development (6), and the historical `المعارف` education ministry
(11). Defence has no item and usually no minister — the prime minister held it
himself 22 times. None is mapped: an unproven rename is a byproduct, not a guess.

**Source defects on ar.wikipedia (fix the wiki, not the parser).** Four pairs of
consecutive cabinets carry infobox spans that overlap by 1–20 days, so a minister
who served both gets two tenures that overlap by the same amount:
`توفيق أبو الهدى التاسعة` ends 1952-09-27 but `العاشرة` starts 1952-09-07;
`حسن خالد أبو الهدى الأولى` ends 1924-05-07 against `علي رضا الركابي الثانية`
starting 1924-05-03; `بهجت التلهوني الثالثة` / `وصفي التل الثالثة` by a day; and
`هاني الملقي الثانية` / `عمر الرزاز` by ten. Not patched here, for the reason the
Kuwaiti reversed ranges were not: a global "swap or clamp if overlapping" would
touch every campaign and could mask a real defect. (The three 1920 *local*
governments — Ramtha, Salt, Karak, Kura — also overlap and are meant to: they ran
in parallel in different towns.)

**Deferred.**
* **The sitting cabinet** (`ar:حكومة جعفر حسان`) — its article dates ministers
  from their original appointment rather than from this government, which
  collides with the predecessor's dating of the same tenure. Kuwait's sitting
  cabinet is deferred for a sibling reason.
* **39 of 108 cabinet articles yield no rows at all** — they carry only
  `خرج من الفريق الحكومي` / `إنضم إلى الفريق الحكومي` reshuffle tables, which name
  who joined and left without dating either, or no minister table at all.
* **10 cabinets state no formation date** in their infobox and are left out of
  `CABINETS`: with no term and no dated rows there is nothing to record.
* **House of Representatives seats.** `ar:أعضاء مجلس النواب الأردني` has 114
  members and Q17524418 carries 82 statements with 13 dated, but the per-term
  articles are **election-result tables** (candidate votes, list votes,
  `الدائرة الإنتخابية`, governorate), not member rosters, and only 3 of 20 terms
  have one. No member office was declared. A source dating the other seventeen
  terms is what this needs, not a relaxed rule.
* **Senate seats before the 27th term.** `ar:أعضاء مجلس الأعيان الأردني` has 156
  members; only the 27th roll tabulates them, and that one carries a party column
  (`حزب`) which would be `P102` if the lane is ever extended.
* **Security and central bank.** Chairman of the Joint Chiefs (Q25463341, 2
  holders), Director of General Intelligence (Q130265327, 2) and Governor of the
  Central Bank (Q110068356, 2) have items and no roster in either language.

**`wd_categories.yml`.** Jordan needs `language: ar` throughout: the Senate has
**no English category at all** against 156 members in Arabic, and ministers are
190 pages + 41 portfolio subcategories in Arabic against 1 page in English. The
royal lane inverts it — Arabic has no royal-family category and the genealogy
article is `en:Hashemites`.

## Qatar (added 2026-08-13)

All five lanes ran. **71 `.qs` lines writing 69 statements** (55 `P39`, 9
`P53`, 7 `P22`), no API half — QuickStatements merged the two `P53` claims that
appear twice with different references, exactly as `wd/validate.py` predicted.
**Applied 2026-08-14 and verified: all 69 claims read back live from Wikidata,
none missing.** Baselined in `regression/qatar/`; the brief is
`plans/qatar_sweep.md`.

**Lane E — the ambassadors — is applied.** 21 bilateral ambassadorship items
were created 2026-08-14 (`data/qatar/created.json`, `applied.jsonl`), all 21
clearing `wd.create.guard`, and the sweep then wrote 14 `P39` statements onto
them. `Q141060919`–`Q141060992`; the office keys and targets are in
`scripts/qa_offices.py`.

The item shape is measured off ten existing "ambassador of Qatar to X" items and
inverts what `payload()` writes by default, which is why `CreateSpec` gained
`claims_override`: `P17` is the **receiving** state (8 of 8 that carry it),
`P279` names both `Q38717123` "ambassador of Qatar" and the receiving state's
own "ambassador to X" class, and `P1001` — used by two of the ten — is not
asserted. What was created, per item:

    {"labels": {"en": "ambassador of Qatar to France",
                "ar": "سفير قطر لدى فرنسا"},
     "descriptions": {"en": "diplomatic post of Qatar in France"},
     "claims": {"P31": "Q4164871",
                "P279": ["Q38717123", "Q19359050"],
                "P17": "Q142"}}

**Still open in this lane**, and deliberately: the 24 single-envoy categories are
below `guard`'s floor of two attested holders and were not minted; the permanent
representations (UN, UNESCO, OAS — the UN mission alone has six documented
holders) are a different archetype and need their own decision.

**A bug this lane found in the creation path — fixed, and it never shipped.**
`scripts/create_offices.py` passed none of `country_label`, `jurisdiction_label`
or `body_label`, and `payload()` falls back to the raw QID when a label is
missing. Every archetype's description template interpolates one of the three,
so the first Qatari payload read "diplomatic post of Q846" and a `judge` or
`agency_head` office would have said "judge of Q213". All three are now
resolved through the `_label` helper already in that script — `guard` was
fetching the body's label anyway to check it shares a word with the office name.

**Nothing was ever written with a leaked QID**, checked three ways:

* `data/qatar/created.json` is the **only** creation ledger in the repo; every
  other campaign's `applied.jsonl` holds claim-edits and not one creation, so
  `--apply` had never been run on this path before 2026-08-14.
* All 21 Qatari items were minted *after* the fix and read back clean —
  "diplomatic post of Qatar in France", not a QID.
* A SPARQL sweep of `P31 = Q4164871` items whose English description matches
  `\bQ[0-9]{2,}\b` returns four hits, all of them deliberate cross-references
  ("for property consultant use Q124728671"). None is a template leak.

The Czech judge items the campaign's creation lane would have minted
(`Q140913203`, `Q140913206`) already exist and were made by hand — their
descriptions read "position at the Supreme Court…", which is not the archetype
template, and `Q140913206` carries a `P279` the archetype does not use.

Floor is two attested holders, which `wd.create.guard` already imposes; the 24
single-envoy categories are below it and are not to be minted.

| holders | label (en) | label (ar) | `P17` receiving | `P279` receiving class |
|---|---|---|---|---|
| 8 | ambassador of Qatar to France | سفير قطر لدى فرنسا | `Q142` | `Q19359050` |
| 6 | ambassador of Qatar to Egypt | سفير قطر لدى مصر | `Q79` | `Q30056302` |
| 5 | ambassador of Qatar to Mexico | سفير قطر لدى المكسيك | `Q96` | `Q29511856` |
| 4 | ambassador of Qatar to Turkey | سفير قطر لدى تركيا | `Q43` | `Q28038722` |
| 4 | ambassador of Qatar to the Russian Federation | سفير قطر لدى روسيا | `Q159` | `Q29511967` |
| 4 | ambassador of Qatar to the United Kingdom | سفير قطر لدى المملكة المتحدة | `Q145` | `Q456692` |
| 4 | ambassador of Qatar to India | سفير قطر لدى الهند | `Q668` | `Q30056023` |
| 3 | ambassador of Qatar to Belgium | سفير قطر لدى بلجيكا | `Q31` | `Q29511906` |
| 3 | ambassador of Qatar to Tunisia | سفير قطر لدى تونس | `Q948` | `Q29970486` |
| 3 | ambassador of Qatar to Saudi Arabia | سفير قطر لدى السعودية | `Q851` | `Q30057165` |
| 3 | ambassador of Qatar to Kuwait | سفير قطر لدى الكويت | `Q817` | `Q30057130` |
| 3 | ambassador of Qatar to Lebanon | سفير قطر لدى لبنان | `Q822` | `Q30057181` |
| 2 | ambassador of Qatar to the United Arab Emirates | سفير قطر لدى الإمارات العربية المتحدة | `Q878` | `Q30057151` |
| 2 | ambassador of Qatar to Pakistan | سفير قطر لدى باكستان | `Q843` | `Q30056349` |
| 2 | ambassador of Qatar to Italy | سفير قطر لدى إيطاليا | `Q38` | `Q21814442` |
| 2 | ambassador of Qatar to São Tomé and Príncipe | سفير قطر لدى ساو تومي وبرينسيبي | `Q1039` | `Q106457780` |
| 2 | ambassador of Qatar to Venezuela | سفير قطر لدى فنزويلا | `Q717` | `Q30057166` |
| 2 | ambassador of Qatar to Nigeria | سفير قطر لدى نيجيريا | `Q1033` | `Q30249268` |
| 2 | ambassador of Qatar to Libya | سفير قطر لدى ليبيا | `Q1016` | `Q30056069` |
| 2 | ambassador of Qatar to Morocco | سفير قطر لدى المغرب | `Q1028` | `Q29898040` |
| 2 | ambassador of Qatar to Greece | سفير قطر لدى اليونان | `Q41` | `Q29898588` |

Also deferred with it: the permanent representations (UN, UNESCO, OAS — the UN
mission alone has six documented holders) are a different archetype from a
bilateral post and need their own decision, and 42 of the dated tenures are
sub-ministerial or non-PEP (department directors, a football federation
presidency, a Red Crescent secretary-generalship) and route to no item at all.

**Item-creation rosters (people, not offices).**
* 87 of the 179 anchors in `en:House of Thani`'s three branch lists are
  redlinks — half the house has no article and so no item. They are named in
  `data/qatar/kinship_audit.md` under "Listed with no article".
* 44 of the 45 members of the 2021 Shura Council have no item. `Q21328600` has
  one holder against a 45-seat chamber. `en:2021 Qatari general election`
  names the 30 elected; `ar:قائمة أعضاء مجلس الشوري القطري (2021)` names all 45
  as unlinked plain text.

**Item-layer defects — surgical, stop and ask.**
* `Q54965863` Crown Prince, `Q21328600` Shura member, `Q108861084` Deputy PM
  and `Q110183427` Chief of Armed Forces carry no `P571`, so
  `Precedent.covers()` has nothing to enforce.
* The four economic-portfolio items — `Q106762274` Commerce and Industry,
  `Q108861091` Industry and Energy, `Q110182815` Energy, `Q110182502` Business
  and Trade — are a renaming succession that no statement declares: none has
  `P571`, `P576`, `P1365` or `P1366`.
* `Q108718564` "ambassador of Qatar to Hungary" puts both parents on `P31`
  where every sibling uses `P279`.
* `Q23020336` Mohammed bin Abdulrahman Al Thani: `en:Deputy Prime Minister of
  Qatar` dates him from November 2017, the item records 2016-01-27. The
  backtest's only date conflict; needs the sources read, not a parser change.
* Nine roster spells are not recorded although the person already holds the
  target for a *different* spell (Khalifa bin Hamad as crown prince and prime
  minister, Hamad bin Khalifa likewise, three more on the deputy premiership).
  The person-level `already holds P39` gate drops them before they reach the
  batch, which is coarser than the statement it protects.

**Engine followup, not Qatar's.** `scripts/sa_family.py` and
`scripts/jo_family.py` read item state through the seven-day cache rather than
`STATE_MAX_AGE`, which is the one thing `CLAUDE.md` says never to do: a Saudi
re-run still offers a `P53` that has been live on `Q99162142` for days.
`scripts/qa_family.py` uses `STATE_MAX_AGE`; the other two want the same change
and a re-baseline with it.

## Iran (added 2026-08-18)

Run 2026-08-18. Campaign `scripts/ir_offices.py`, plan `plans/iran_sweep.md`.
The Solar Hijri date path (`wd/roster.py`, graded by `scripts/check_dates.py`
against a 151-case fixture) is what made any of it reachable.

### Still to apply

* **`scripts/apply_claims.py --campaign iran --apply`** — the API half, which
  QuickStatements cannot express at all (a person's several tenures in one
  office). Written, validated, and spot-checked live: three sampled people hold
  zero statements on their targets, so nothing duplicates. Blocked in the run
  by the session's permission classifier, not by any finding. **The ledger is
  load-bearing here in a way it is not for QS — the API de-duplicates nothing,
  so a re-run without `claims_written.json` doubles every tenure.**

### Lanes measured but not run

* **The 903 provincial-governor rows.** All 31 provinces publish
  `فهرست استانداران …`; 879 rows carry a raw date and 72% are wikilinked,
  against **4** position items and 10 statements. Blocked on 27 item creations
  *and* a missing archetype — `wd/create.py`'s `provincial_governor` is the
  Saudi `P279=Q98786082` "emir of province" shape and would make 27 items
  siblings of nothing. Needs a `governor` archetype (`parent="Q132050"`).
* **Majlis terms 1–8.** Terms 9–12 shipped. The earlier rolls exist under page
  titles the `فهرست نمایندگان دوره {ordinal} مجلس شورای اسلامی` pattern does not
  reach; find them before assuming they are bullets.
* **The Majlis gate.** `holders()` gates per (person, target), and 423 people
  already hold `Q17525449` for a *different* term, so their remaining terms are
  silently dropped. That under-yields rather than writing anything wrong, but a
  per-term gate would recover them.
* **17 undated ambassador rosters.** They parse now (765 rows across 32 pages)
  but only 244 rows anywhere are datable; the other 17 pages would skip as
  `no_dates` to a row. Not padded into the batch.

### Destructive — stop-and-ask, never a batch line

* **The corpus contains botched Jalali conversions, and the backtest proves it.**
  Four for four on the IRGC commander-in-chief: `۲۰ شهریور ۱۳۶۰` is 1981-09-11
  and Wikidata records 1981-09-**20**; `۲ خرداد ۱۳۵۹` is 1980-05-23 and Wikidata
  records 1980-06-**02**. Someone kept the Solar Hijri **day number** and mapped
  the month *name* to the nearest Gregorian month — a defect invisible to any
  year-based check, because the year is right. Full measurement in
  `data/iran/survey/defects_jalali.md`. Corrections are value changes, so they
  are a `--dry`-by-default script behind this gate, and they go in **after** the
  additive batch.
* Merge `Q60149120` into `Q107040507` (Chairman of the Assembly of Experts).
  Lanes A and D ruled independently: the two items' holders **interleave into one
  unbroken succession** — `Q60149120` holds exactly the 2014–2016 segment sitting
  inside `Q107040507`'s gap — so this is fragmentation, not two offices.
* Merge `Q106960625` into `Q107391283` (First Vice Chief Justice). Raisi
  2004-07-27 → 2014-08-23 and Mohseni-Ejei 2014-08-23 → 2021-07-01: consecutive
  occupants handing over on the identical day, with no era, jurisdiction, body or
  sitelink distinguishing the items.
  **Blocker:** `create_offices._existing` treats only `status=="matched"` as a
  duplicate and this label returns `ambiguous`, so `guard` would mint a **third**
  item. Fix that before any creation runs.
* `Q7844710` is a `Category:` item carrying 9 P39 statements — the Iraqi
  `Q25167655` case exactly. Removal.
* `Q917663` (the Assembly of Experts **body**) is used as a P39 value by 2 people.
  Removal.
* `Q5662557` (Chief Justice) carries `P576 = 2022-10-01`, which ends the
  incumbent's tenure. Value removal.
* **Do NOT merge the three Khatam al-Anbiya items** — measured as construction HQ,
  Central military HQ and air-defence university, three different bodies.

### Item creation (dry first)

* **27 provincial governorships.** All 31 provinces have a `فهرست استانداران …`
  roster totalling 903 rows, 879 raw-dated, 72% wikilinked, against **4** items
  and 10 statements. The `P1001 = <province>` convention was measured across 123
  Iranian position items and is clear enough to mint to.
  **Blocker:** `wd/create.py` has no archetype for this — the existing
  `provincial_governor` is the Saudi `P279=Q98786082` "emir of province" shape and
  would make 27 items siblings of nothing. Needs a `governor` archetype
  (`parent="Q132050"`).
* **5 judicial offices with no item**: heads of the Supreme Court (7 rows), the
  Court of Administrative Justice (14), the General Inspection Office (7), the
  Tehran Prosecutor-General (4) and the Tehran Revolutionary Courts (8).
  `Q31068012` and `Q5960362` are bare *article* items — usable as `P2354`, never
  as a `target`. `ir-tehran-prosecutor` renders its description as "head of Iran"
  and needs an override.
* **7 ambassadorships with a fa roster and no item** (Romania 31 rows, Bulgaria
  23, Denmark 20, Philippines 17, Senegal 14, Uzbekistan, Slovenia). Mint with the
  `qa_offices.envoy` shape — **not** `wd.create.payload`'s default, which writes
  the *sender* into `P17`.
* 10 provincial-capital mayoralties (6 with a real identity channel). `P36`, not
  `P150`, is the right generator for these.
* Pre-1979 War minister and `وزیر علوم و آموزش عالی` — both have a roster and no
  position item (`Q20110822` is a Wikimedia *list article*).

### Not created, deliberately

* **The 17 named Revolutionary Court judges.** `wd/create.py:guard` returns CLEAR
  on them — duplicate search unmatched, 17 well over the holder floor, body-label
  check fine — and they should still not be minted: one channel only (a category
  is a candidate generator, never a fact), **no source dates any judge's
  appointment**, and the only attested shape is a *branch* presidency rather than
  a generic judgeship. Salavati, the canonical case, has no officeholder infobox.
* **Supreme National Security Council membership.** Ex officio — the en page heads
  the column literally "Ex officio member" and fa fills it with offices, not
  people. The membership dates are the *other* office's dates. No member item
  exists and none should.
* **City councils.** Tehran's is 21 rows and undated, 9% wikilinked. No item, no
  lane.

### External

* opensanctions/opensanctions#5475 — diplomatic positions carry only the
  receiving country. Iran's 77 outbound ambassadorships record the sender in
  `P137` (74/77) and `zavod` does not read it. Wide blast radius: every country's
  ambassadors.

## Iran run 2 (added 2026-08-19)

Scoped from `coverage/iran.md` rather than from the campaign script. Batch
rendered and **not yet applied**: `data/iran/edit_plan.qs` (1,125 statements)
plus `data/iran/edit_plan_claims.json` (413 statements for 186 people) — the two
halves of one batch, reviewed together.

### Done this run

* 27 provincial governorship items minted (`data/iran/created.json`), verified
  live as well-formed. `subnational.executive` went 0 → 408 statements.
* Majlis terms 1–8 configured — 1,871 rows, 1,851 wikilinked. Lane 388 → 1,078.
* Central bank `Q20110284`, Majlis speakership `Q6597965`, UN permanent
  representation `Q7169241` and FARAJA `Q114457755` configured against items
  that already existed.
* `regression/iran/` and `regression/qatar/` baselines **un-broken** — both had
  their verdicts in a `verdicts/` subdirectory that `diff_verdicts.py` never
  looked in, so both reported "baseline 0 records" and compared against nothing
  from the day they were committed. Layout flattened to match every other
  campaign; the differ now refuses an empty baseline instead of printing one.

### Next creation round (dry first, then the human gate)

One round covers all of it; the archetypes and the fixed duplicate guard exist.

* **IRIB headship** — measured and ready: `fa:رئیس سازمان صدا و سیمای جمهوری
  اسلامی ایران`, 18 rows, 17 dated, 14 linked. `lookup_position` unmatched on
  three spellings, so no item exists. `agency_head`.
* **General Inspection Office** head — 7 rows.
* **5 judicial offices**, **~10 provincial-capital mayors** (`mayor` archetype
  now exists), **~31 Friday-prayer leaderships**, **6 bonyad headships**
  (already ruled *positions*).

### Blocked, each named in the ledger

* `blocked:wide-roster` — Deputy Speakership `Q118321724`. Its roster is **two
  holders per row** (first and second deputy) keyed by term ordinal, and dates
  nothing. Needs a two-holders-per-row reader, or a decision to take the
  first-deputy column only and record that it under-covers.
* `blocked:deputy-ministers` — ten deputy ministers sit on the interior page and
  the heading filter drops them. `Q116214167` exists with 3 holders.
* `blocked:historic-chambers` — National Consultative Assembly (`Q134563198`,
  85 holders) and 7 Senate rolls / 173 people. `era.distinct`; need own items.

### Item repairs (surgical, stop-and-ask — never in a batch)

* `Q106975489` "Governor of Khorasan Province": `P1001 = Q794` should be
  `Q587090`. Measured as the **only** item in the 242-strong worldwide
  `P279 = Q132050` cluster whose jurisdiction is its own country.
* `Q106963302` Ardabil: add `P1001 = Q134228`, add an `fa` label.
* `Q126003139` East Azarbaijan: `P279` is `Q382844`, should be `Q132050`.
* `P2354` (has list) missing on all four pre-existing governor items.
* Mohammad-Sadeq Moatamedian's four governorships are recorded against the
  **list articles** rather than the offices — add the four correct P39s, then
  remove the four list-article ones (destructive half, human gate).
* `P31 = Q13406463` missing on `Q109550030`, `Q28712909`, `Q56360216`,
  `Q28713751`.

### Known and named, not a defect

`legislature.leadership` ships 0 because all 7 speakers already hold the
statement — `covered`, measured. The same gate (held per person+target, not per
term) caps the Majlis lane: a member re-elected in a term already recorded is
invisible. A per-term gate is a **write-path** change, since per-term membership
cannot go through QuickStatements at all.

## Toolkit gaps that block lanes in more than one campaign

Promoted here because a workaround appearing in a *second* campaign is the signal
that something is missing, not a pattern to copy (`recipes/country_sweep.md` §3a).
Each one blocks work that is otherwise ready.

* **`wd/kinship.py` cannot read `{{Tree chart}}`.** Blocks the House of Sabah
  (Kuwait) and the medieval Sharifian lineage (Jordan). Jordan's plan cites
  Kuwait's deferral as precedent — *"if the tree-chart reader is ever built it
  unlocks both at once"* — and it was not built. **Two lanes, one reader.**
* **`wd/create.py` archetypes.** No non-ruler *deputy* archetype (Kuwait dropped
  three offices); no *governor* archetype (Iran's 27 governorships; Iraq worked
  around it by reusing `provincial_governor` "for its description template
  only"). Two campaigns overriding the same field.
* **`create_offices._existing` treats only `status=="matched"` as a duplicate.**
  An `ambiguous` result passes, so `guard` would mint a third item beside two
  existing ones. Note the naive fix is wrong: `ambiguous` is the default for any
  search returning candidates, so it must judge the *candidates* — label-match ∧
  not-pure-list ∧ (country-match ∨ no country property).
* **`SCRIPTS` in `create_offices.py` is missing `jo`, `kw`, `ir`** — the three
  campaigns with the largest creation lists. Every plan instructed the wiring.
* **RTL-reversed date ranges.** Deferred by Kuwait, then by Jordan citing Kuwait,
  then by Iran (the Oman ambassador roster). Three campaigns, one unmade
  decision. The standing rule is to defer the page rather than add a global swap
  — but three deferrals is a request for a per-source `reversed=True` flag.
* **The `already holds P39` gate is per (person, target), not per term** — and
  worse, it `continue`s before `emit()`, so the rows never become verdicts.
  Iran tallied **1,932 of 3,060 rows** (63%) invisible in `edit_plan.md`, which
  contradicts the contract's "every case gets a disposition". It drops 423 Iran
  Majlis members, 9 Qatari Al Thani second spells, 3 Iraqi reigns and ~100
  undated Spanish premierships. The data needed for a per-term gate is already
  on `person.p39_claims`.
* **The duration-column collision** (`المدة` / `مدت تصدی` / `Duración` /
  `Dny v úřadu` / `طول الفترة`) has now appeared in five campaigns. Iran settled
  the principle — *`days` is inert, `period` shadows* — but there is still no
  shared fixture, so each campaign rediscovers it.

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
