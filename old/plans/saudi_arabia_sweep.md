---
description: Saudi Arabia PEP sweep — offices (P39) plus a new kinship lane (P25/P22/P53) for the House of Saud
date: 2026-08-12
tags: [campaign, saudi-arabia, house-of-saud, p39, p25, kinship, arabic, hijri]
---

# Saudi Arabia: offices, and the House of Saud's kinship graph

Method is `recipes/country_sweep.md`; this document holds only what the survey
measured and the decisions that follow from it. Two lanes, because the country's
power sits in a dynasty and the engine as it stands can only assert P39/P102/P53.

## What the survey found

**The person layer is empty in the usual way.** 6,213 people carry
`P27 = Q851`; **551** carry any `P39` (8.9%). Comparable to the UAE (1,876 /
120) at three times the scale.

**The dynasty is half-recorded, and the gap is not where you would guess.**
Of the 411 people carrying `P53 = Q31711` (House of Saud):

| property | recorded | gap |
|---|---|---|
| P22 father | 346 | 65 |
| P569 birth | 311 | 100 |
| P27 citizenship | 290 | 121 |
| P3373 sibling | 133 | — (out of scope, below) |
| P40 child | 120 | — (reciprocal, below) |
| **P39 position** | **81** | **330** |
| **P25 mother** | **72** | **339** |

So P22 is largely done; **P25 and P39 are the lanes**. Ibn Saud himself
(Q151509) records 50 children and 10 spouses. 273 patrilineal descendants of
Ibn Saud are on record, 262 of them with P53.

**The item layer exists and is nearly empty.** 125 of the items scoped to Q851
carry at least one holder statement. The shape of it:

* the ministerial items were bulk-created and hold 1–2 holders each (Minister
  of Interior Q114452638: **1**; Minister of Foreign Affairs Q22689140: 6;
  Minister of Defence Q25556795: 8). Minister of Health Q98934272 (21) and
  Minister of Information and Media Q104127725 (13) are the exceptions.
* **Member of the Consultative Assembly Q21328601 holds 283** — the one
  well-populated item in the country.
* provincial governors: **8 of 13 items exist** (Riyadh Q57334761 has 7
  holders, the rest 1–2). Najran, Northern Borders, Jazan, Al-Bahah and
  Al-Jouf have no item — a creation lane.
* the usual defects, for `tasks/followups.md`: `Q20388005 "list of rulers of
  Saudi Arabia"` carries 2 holders (a list article mistyped as a position);
  `Q6867237 "Ministry of Interior"`, `Q12250935 "Ministry of Energy"` and
  `Q12250983` carry P39 holders (bodies, not offices); "Minister of Interior"
  and "Minister of Energy" each have a competing item.

**The categories are well subdivided, and arwiki is the primary channel** —
again. `en:House of Saud` d1 = 193 members, `ar:آل سعود` d1 = **392**.
`en:Government ministers of Saudi Arabia` has **41 portfolio subcategories**,
`ar:وزراء سعوديون` has **49**; `en:Governors of provinces of Saudi Arabia` has
12. `en:Sons of Ibn Saud` = 31. That is a mechanical bucket lane, not
per-person work.

## Lane A — P39, through `wd/campaign.py` unchanged

Every source below was fetched and parsed; the counts are rows the parser
actually returned, not estimates.

| office | source | rows / dated | target |
|---|---|---|---|
| King | `en:King of Saudi Arabia` | 13 / 7 (6 phantom, below) | Q850168 (9) |
| Crown Prince | `en:Crown Prince of Saudi Arabia` | 12 / 12 | Q12251224 (18) |
| Deputy Crown Prince | same page, own table | 3 / 3 | Q19810880 (2) |
| Second Deputy PM | same page, own table | 4 / 4 | none — creation |
| Prime Minister | `ar:قائمة رؤساء وزراء السعودية` | 11 / 11 + legend | Q1153839 (8) |
| Shura chairman | `ar:قائمة رؤساء مجلس الشورى السعودي` | 3 / 3 | needs resolving |
| **Shura members** | `ar:قائمة أعضاء مجلس الشورى السعودي` ×4 terms | **150 each / 0** | Q21328601 (283) |
| ministers (bucket) | `ar:قائمة وزراء X (السعودية)` per portfolio | 7 / 11 / 21 / 26 measured | ~40 items exist |
| sitting cabinet | `en:Council of Ministers of Saudi Arabia` | 37 / 37 | via portfolio map |
| historical rulers | `ar:قائمة حكام آل سعود` | 29 / 27 | mostly missing |

Three of these need a decision rather than a parameter:

* **The Shura member lists are the volume and they carry no dates.** Each page
  is one four-year term and the term is *in the page title*, in Hijri
  (1434–1438 هـ = 2013–2016, 1438–1442 = 2016–2020, 1442–1446 = 2020–2024,
  1446–1450 = 2024–2028). `RosterSource` has nowhere to put "every row on this
  page has these dates", so this needs one new field on `RosterSource`
  (`term=(start, end)`), applied when a row parses no date of its own. 600 rows
  against an item that already holds 283 — the backtest will be unusually
  informative here.
* **The first and second Saudi states are different polities.** 22 of the 29
  rulers on `قائمة حكام آل سعود` ruled Diriyah or the Emirate of Nejd, and
  `era.distinct` skips them for want of their own item — correctly. Their items
  are a creation byproduct, not a batch line.
* **Governors have items but no roster yet found.** `ar:قائمة أمراء محافظة
  الأحساء` (6 rows) is a *governorate*, not one of the 13 provinces. This lane
  is a source probe before it is a lane; if no per-province roster exists the
  12 en subcategories are a one-channel generator and it reports small.

## Lane B — the kinship graph (new: `wd/kinship.py`)

`wd/campaign.py:family_records` asserts P53 only, from a hereditary office. The
House of Saud needs something else, and `en:Descendants of Ibn Saud` (72k of
wikitext) is the source: **sectioned by wife**, each section listing that
wife's children with wikilinks.

    ===Hussa Al Sudairi===
    {{main|Hussa bint Ahmed Al Sudairi}}
    # '''[[Fahd of Saudi Arabia|Fahd]]''' (1921 – 2005); King (1982–2005)
    # [[Sultan bin Abdulaziz|Sultan]] (1928–2011); Crown Prince (2005–2011)
    …

### B1. P25, the mother

Two channels, neither sufficient alone:

1. the article files this child under this wife's section, identity asserted by
   a **wikilink**;
2. the wife's item is independently confirmed — by the section's `{{main}}`
   link (**only 2 of 21 sections have one**), *or* by ≥2 of the section's other
   children already recording the same P25, *or* by an item that records
   `P26 = Q151509` under that name.

Gated further on the child already recording `P22 = Q151509`: we add the mother
only where the community already agrees on the father.

Measured with a crude wikitext parser: 51 children found, 35 resolve to items,
19 of those record no P25, **18 of the 19 already record P22 = Ibn Saud**. The
real number is higher — the first seven wife sections use `{{Children}}`
templates that render as a table and the crude parser saw none of their rows,
so the implementation reads rendered HTML and handles both shapes.

### B2. P53, House of Saud

The `ar:آل سعود` tree (392 at depth 1) and the article's grandson /
great-grandson lists against the 411 already carrying P53. Same two-channel
bar as the UAE: the name must carry the dynasty *and* a source must place the
person in it. Neither alone.

### B3. P22 from the patronymic

Arabic names encode paternity, and the article's own section headings close the
candidate set: everyone under "Patrilineal grandsons" has a father who is a son
of Ibn Saud. So "Khalid bin Faisal" resolves against the 45 sons, and
"Mohammed bin Salman bin Abdulaziz" resolves on the **whole chain**, which is
far stronger than a first-name match. Gates: exactly one candidate father
(there were two Turkis and two Badrs — genuine ambiguity, skipped with a
reason), and the father born ≥16 years before the child.

### Deliberately out of scope, decided once

* **P40 (child)** — the reciprocal of P22, maintained by bot. Emitting both
  directions doubles the batch and invites a constraint conflict.
* **P3373 (sibling)** — combinatorial (the Sudairi Seven alone would be 42
  statements) and redundant where both parents are recorded, which is the whole
  point of B1.
* **P26 (spouse)** and the royal-marriage graph — the article's prose describes
  cousin marriages in sentences, not rows. Not a mechanical channel.

## Parser work this run needs (`wd/roster.py`)

Found by running the parser on the real pages, in the §7 tradition:

* **Arabic column keys the Saudi pages use and the Emirates pages did not**:
  `مسلسل` / `الترتيب` / `ترتيب` → ordinal; `حتى` → end (only `الى` and
  `نهاية` exist today, so `حتى الفترة` matched nothing); `العضو` and
  `وزير <portfolio>` → name; **`في عهد` → appointer** (the reigning king — a
  free second signal); `الميلاد` / `الوفاة` → notes (a lifespan column beside
  the dates, exactly the trap the recipe names); `سبقه` / `تبعه` → notes;
  `مراجع` → ref. Without these the header row — marked up as `td` on these
  pages — fails `_reads_as_header`'s two-known-columns test and **every row
  loses its dates**: Interior 11 rows and Health 21 rows both parsed with zero.
* **Hijri dates are already safe, and that is worth a test rather than code.**
  `1370 هـ` → `None`, `28/6/1350هـ` → `None`, and `1331هـ/1913م.` → `1913`:
  the Gregorian year range guard rejects AH years and keeps the AD half of a
  dual-dated cell. Locking this in matters because most of these pages date
  in Hijri and a conversion would be silently wrong by a year.
* **the `(aged 57)` phantom row.** `en:King of Saudi Arabia` writes
  "23 September 1932(aged 57)" over two lines and "9 November 1953(death by
  natural causes)" likewise, so the equal-length stack pairing emits a **second
  dateless row per king** — 6 of the page's 13 rows. Harmless today (they land
  on `no_dates` and the dated span wins) but they double the audit and the
  backtest denominator. Drop a paired term where neither side parses a date.
* **a mismatched stack loses precision.** Where the start cell stacks Hijri
  over Gregorian and the end cell has one line, the whole start cell is parsed
  at once and `'1 رجب 1441 هـ 25 فبراير 2020 م'` yields `2020` instead of
  `2020-02-25` — a year-precision date beside day-precision ones, which
  `wd/validate.py` already warns about. Prefer a full day-month-year match
  anywhere in the string over the bare-year fallback.

## Order of work

1. parser hardening + the Hijri regression test; re-run `diff_verdicts.py`
   across all five committed countries before anything else — the Arabic keys
   touch the UAE.
2. Lane A, `scripts/sa_offices.py`: kings, crown princes, PM, Shura chairman,
   Shura members (the `term=` field), the portfolio bucket, the cabinet page.
3. Lane B, `wd/kinship.py` + `scripts/sa_family.py`: P25, then P53, then P22.
4. render one `data/saudi/edit_plan.qs`, byproducts to `tasks/followups.md`,
   baseline into `regression/saudi/`.

Checkpoint after 1, after 2 and after 3.

## What it came to

**626 roster rows and 274 listed descendants → 43 lines / 42 statements**: 29
P39, 9 P53, 3 P25, 2 P22. 283 records, so 239 rows were decided against with a
reason on the record. Backtest: **target agreement 97–100% on every office,
date agreement 100% on ten of thirteen** and 78–86% on the three whose conflicts
are genuine source disagreements (King Faisal's premiership is dated from 1962 on
the roster and from his accession on the item; the ar foreign-ministers page
runs his tenure to October 1975, seven months after he was assassinated).

The yield is small for the same reason the UAE's was, and the reason is worth
stating plainly rather than treating as a disappointment:

* **the throne is finished.** 29 of the 33 rows across King, Crown Prince,
  Deputy Crown Prince and Prime Minister were already on record.
* **Hijri dating caps three ministerial lanes.** Health yields 0 datable terms
  from 21 rows, Interior 2 from 11. Nothing is wrong with the parse; the sources
  simply do not give a Gregorian date, and converting would be guessing.
* **P22 was already 84% done** (346 of 411), so the patronymic lane had almost
  nothing left to find — and what it found first were two false positives it
  took two rounds of reading the output to kill.
* **the mother lane is blocked on item creation, not on inference.** 10 of Ibn
  Saud's ~22 wives have no item, and they hold 20 of the missing mothers.

One correction the creation dry run forced, worth keeping in mind for the next
country: **a census that prints only items with a holder will hide the empty
items the sweep exists to fill.** The Shura chairmanship (Q22688060) was declared
for creation and found by `create_offices.py`'s own duplicate search, because it
has `P17 = Q851` and zero holders. The dry run is a second census, and reading it
is not optional.

Three engine changes came out of it, all of which earned their place by being
caught before shipping or by fixing something already shipped:

* `RosterSource.term` — a membership roll that dates no row, for the Shura's
  three 150-member terms. General; any appointed legislature will need it.
* `wd/backtest.py` compared at the record's precision, never the roster's, so a
  year-precision roster could only score `conflict`. Fixing it took Riyadh from
  0% to 100% **and retroactively cleared three Belarusian offices** that had been
  reported as parse defects for months. No record anywhere changed.
* `wd/kinship.py` — the dynasty lane, now written up as §4a of the recipe.
* seven `wd/roster.py` additions and `scripts/check_dates.py`, which pins the
  Hijri behaviour that was previously accidental and invisible.
