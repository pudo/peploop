---
description: Kuwait PEP sweep — the ministerial items exist and are nearly empty; ar.wikipedia carries every roster and the National Assembly rolls
date: 2026-08-13
tags: [campaign, kuwait, al-sabah, p39, p53, arabic, national-assembly]
---

# Kuwait: full item layer, almost no holders

Method is `recipes/country_sweep.md`; this holds what the survey measured and
the decisions that follow. Kuwait is the **Ecuador profile** — the position
items nearly all exist and carry a handful of holders each — which the recipe's
calibration table says is the highest-yield shape.

## Coverage

| measurement | value |
|---|---|
| people with `P27 = Q817` | 2,003 |
| …carrying any `P39` | 288 |
| items scoped to Q817 with ≥1 holder | 63 |
| holder statements across them | 507 |

Of the 63, **24 are foreign embassies' ambassadors to Kuwait** — other
countries' offices that happen to be scoped here, and not this sweep's lane.
The Kuwaiti offices proper hold ~350 statements, and the largest single item
(`Q21295986` Member of the National Assembly, 228 statements) is **undated in
196 of them**.

## §2a — is each office one item or several?

Checked, and the answer is reassuringly boring: the three offices that looked
duplicated are a position item beside a correctly-typed *list article*.

| office | position item (holders) | list article |
|---|---|---|
| emir | Q100877419 (17) | Q246932 `P31 = Q19692233` |
| prime minister | Q30100649 (11) | Q2035020 `P31 = Q13406463` |
| speaker | Q110532419 (4) | Q6597898 `P31 = Q13406463` |

`en:Emir of Kuwait` and `en:Prime Minister of Kuwait` **sitelink to the list
items**, so resolving either office by article title lands on the wrong one —
the same trap Saudi Arabia's Second Deputy Prime Ministership set. Targets are
taken from the census, never from the sitelink.

Genuine defects, all surgical (never in a batch):

* **Q139413655 "Monarch of Kuwait"** — 1 holder, no `P31`, `P279 = Q116`. A
  stray third item for the throne.
* **Q128977192 "Kuwaiti Minister of Public Works"** (1) beside **Q110526419
  "Minister of Public Works"** (4).
* **Q120913227 "list of deputy speakers of Kuwait National Assembly"** is typed
  `P31 = Q4164871` — a list article mistyped as a position, so the deputy
  speakership has no usable item.
* **Q110532468 Governor of the Central Bank** carries `P31 = Q294414` (cabinet
  position) for a central-bank governorship.
* **Q124394695 "Governor of Kuwait"** is scoped to no country at all.

## PETScan — ar.wikipedia is the channel, again

The UAE and Saudi finding repeats, harder. en.wikipedia has **no category at
all** for the emirs, the crown princes, the House of Sabah, the Assembly's
members or its speakers.

| category | depth 0 | depth 1 | subcats |
|---|---|---|---|
| `ar:أعضاء مجلس الأمة الكويتي` | 86 | **437** | 22, one per term 1962–2024 |
| `en:Members of the National Assembly of Kuwait` | — | — | does not exist |
| `ar:وزراء كويتيون` | 83 | **305** | 44 portfolios |
| `en:Government ministers of Kuwait` | 11 | 80 | 27 portfolios |
| `ar:سياسيون كويتيون` | 200 | 601 | 12 |
| `ar:آل صباح` | 126 | 135 | 1 |
| `en:House of Sabah` | 0 | 0 | 0 |

The per-term member subcategories are the useful shape: `ar:أعضاء مجلس الأمة
الكويتي 1985` is ar.wikipedia asserting membership *in that term*. They exist
for all 22 terms; only four terms have a roster table to pair them with, so the
other eighteen are `category_only` and skip. That is the honest ceiling, not an
underperforming lane.

## Rosters

25 offices have a source. ar.wikipedia keeps a dated table in the *ministry*
article for most portfolios; en.wikipedia's equivalents are shorter or undated.

**The lanes with real yield** (roster rows vs statements already recorded):

| office | target | rows | recorded | source |
|---|---|---|---|---|
| electricity & water | Q110526402 | 39 | 5 | `ar:وزارة الكهرباء والماء والطاقة المتجددة` |
| health | Q110526428 | 31 | 5 | `ar:وزارة الصحة (الكويت)` |
| finance | Q110525649 | 29 | 10 | `ar:وزارة المالية (الكويت)` |
| information | Q110526654 | 29 | 5 | `ar:وزارة الإعلام (الكويت)` |
| oil | Q108599663 | 25 | 7 | `ar:وزارة النفط (الكويت)` |
| deputy prime minister | Q110526533 | 44 | 10 | `ar:مجلس الوزراء الكويتي` |
| speaker | Q110532419 | 22 | 4 | `en:List of speakers of Kuwait National Assembly` |
| justice | Q110526408 | 19 | 6 | `en:Ministry of Justice (Kuwait)` (bullets) |
| crown prince | **Q22690742** | 8 | **0** | `ar:قائمة ولاة عهد الكويت` |
| six ministers of state | various | 101 | ~10 | `ar:قائمة وزراء الدولة لشؤون …` |
| Assembly members | Q21295986 | 202 | 228 (196 undated) | four `ar:مجلس الأمة الكويتي <year>` rolls |

**Already complete, so they are the backtest's test set:** emir (17 of 17
recorded, dated to the day), prime minister (11 of 11), interior (19 recorded
against 18 rows).

## Four parser gaps, all Arabic vocabulary

Each one silently cost every date on its page — §7's "when a page returns rows
but no dates, dump the header row folded" case, four times over.

1. `ar:وزارة المالية` dates under a bare **`التاريخ`**, which is deliberately
   unreachable: the Saudi province articles split it into `التاريخ الهجري` /
   `التاريخ الميلادي` and neither may be caught by a bare prefix key. Ordering
   solves it — the two specific keys already precede, so a bare key added
   *after* them cannot shadow either.
2. `ar:وزارة الإعلام` heads its pair **`تاريخ التعيين`** / **`تاريخ انتهاء
   الخدمة`** (appointment / end of service). Neither starts with `التاريخ`.
3. `ar:رئاسة الأركان العامة` is §7's subdivided-header trap in Arabic: three
   columns headed `مدة الرئاسة`, sub-headed **`بدأ فترته`** / **`انتهت فترته`**
   / **`الفترة الزمنية`**. The third is a *duration* and reached `period`
   through the existing `الفترة` key, shadowing the two real date cells — the
   Czech "Dny v úřadu" bug exactly. Its holder column is headed `رئيس الأركان`,
   so the only column reading as a name was **`وزير الدفاع`** — the appointing
   defence minister — through the generic `وزير` key.
4. `en:Ministry of Interior (Kuwait)` heads the ministers' table **`interior
   tenure from`**, which no `tenure` prefix can catch. The Arabic article
   tabulates the same 18 ministers with dates, so this one is answered by
   choosing the better source rather than by a key.

## Decisions

* **No kinship lane.** Both `en:House of Sabah` and `ar:آل صباح` render their
  genealogy as `{{Tree chart}}` — parent-child edges encoded in box-drawing
  characters — not as the heading-per-generation article `wd/kinship.py` reads,
  where the heading *is* the assertion. P25/P22 would have to come from a new
  parser and is deferred. **P53 = Q291639** still ships, through
  `Office.family` on the hereditary offices, exactly as the UAE's did.
* **The Assembly rolls are dated from the election dates, not from the pages.**
  The four rolls (2016, 2020, 2023, 2024) carry 50 wikilinked members each and
  no date column, so `RosterSource.term` supplies it, as the Saudi Shura rolls
  did. The boundaries are Wikidata's own `P585` on the election items, at day
  precision, each term ending where the next election falls:

  | roll | start | end | source |
  |---|---|---|---|
  | 2016 | 2016-11-26 | 2020-12-05 | Q27921330 → Q39088670 |
  | 2020 | 2020-12-05 | 2022-09-29 | Q39088670 → Q112957772 |
  | 2023 | 2023-06-06 | 2024-04-04 | Q104032248 → Q124707230 |
  | 2024 | 2024-04-04 | 2024-05-10 | Q124707230 → dissolution |

  The 2020 boundary **understates deliberately**. That Assembly was dissolved
  in August 2022, its successor's election annulled by the constitutional court
  in March 2023, and the 2020 members reinstated until May 2023. Recording
  "elected 2020, served to the 2022 election" is the attested, continuous half
  of that; asserting the reinstatement as one unbroken span would be wrong for
  the eight months the 2022 Assembly actually sat. The 2024 end is the Emir's
  10 May 2024 dissolution, when parliament was suspended.

* **No `P2937` (parliamentary term) qualifier.** It is the interesting
  convention here — term items exist for every election year — but it is used
  on only **19 of the 228** existing seat statements. Recipe §10.3: a minority
  practice is not mass-asserted. Dates only.

* `modern_from = 1962`, the year of the constitution and the first cabinet
  (17 January 1962). Pre-1962 rows are department heads of the pre-independence
  administration — `ar:وزارة المالية` opens with "رئيس دائرة المالية
  والاقتصاد", 1937 — and are judged against each target item's own record by
  `precedent`, never by a country constant.

* `concurrency_ignore` must name the whole hereditary and federal spine.
  Kuwaiti practice is that one man holds several of these permanently and
  legitimately: the Crown Prince is routinely Prime Minister, and the interior
  and defence ministers are simultaneously Deputy Prime Minister — the ministry
  articles head their own tables "ministers of interior **and deputy prime
  ministers**". Left out, `interim_of` would read each overlap as cover and
  qualify a real appointment `P2868 = Q4676846`.

## What the run produced, and what blocks it

370 statements from 620 roster rows across 25 offices — the largest batch this
workbench has built, and the backtest is the cleanest: **target agreement 100%
on all 21 offices with comparable rows**, so no office here is a family of items
in disguise. All 19 date conflicts were read; none is a parse defect. Two
systematic source disagreements account for almost all of them:

* the ar ministry tables **close each term at the successor's amiri decree**
  while Wikidata records the handover — Nawaf Al-Ahmad's interior term reads
  1978-03-19–1988-01-26 against a recorded 1978-03-19–1986-07-12, and the
  roster's end is exactly the next holder's start;
* the roster dates the **appointment** where Wikidata dates the **swearing-in**
  — two weeks apart on the 2024 premiership.

The three lanes the parser fixes unlocked yielded what the survey predicted:
electricity and water 39 rows, health 31, information 29, oil 25, and the
chief-of-staff list its first 13 dates ever.

**It cannot be uploaded as it stands.** QuickStatements folds two lines with the
same subject, property and *value* into one statement and merges their
qualifiers, so a person with two spells in one office gets a single P39 carrying
two `P580`s and two `P582`s. Kuwait has **50** such groups — the most of any
batch — because its rosters are long enough to catch re-appointments. This was
measured on Wikidata against batches already applied, and the damage is live:
`Q1368615` carries one Ecuadorian ministry statement whose two starts are
fourteen years apart. `tasks/followups.md` holds the finding and the options.

## Byproducts expected

* the deputy speakership (17 rows on `ar:مجلس الأمة الكويتي`) has no position
  item — Q120913227 is a mistyped list article — so it is creation-first;
* the National Guard's deputy commandership (4 rows) likewise;
* the six governorates: only two have items (Q127163995 Al-Jahra,
  Q127164105 Capital, one holder each) and no article tabulates governors, so
  there is nothing to read even for those two;
* the Central Bank governorship has an item and no roster in either language.
