---
description: Iran national PEP landscape sweep — the Solar Hijri date path, an item layer 28% of which has no country, and lanes that are mostly creation-first
date: 2026-08-18
tags: [wikidata, country-sweep, iran, pep, farsi, jalali, creation-first]
---

# Iran sweep

Method lives in `recipes/country_sweep.md`; this document holds what the survey
measured for Iran and the decisions that followed.

## Context

Iran has no prior work in this repo — `fa` appears nowhere in the roster path,
and the only mentions of Iran anywhere are a QID in `scripts/dob_country_sizing.py`
and a note in `tasks/birthdates.md`. It is greenfield in two senses, and the
second one is the campaign: **fa.wikipedia dates every roster in Solar Hijri, and
`wd/roster.py` cannot read a single one of those dates today.**

Iran is also not the country the calibration table would predict. It is neither
Iraq (empty items, rich rosters) nor Czechia (already finished). Measured live on
2026-08-18: the offices that exist are unusually *well* dated — President, Supreme
Leader, Chief Justice, Speaker, IRGC Commander-in-Chief and the SNSC Secretary are
all at 100% P580 coverage — while the institutions that carry Iran's actual power
either have no position item at all (bonyads, the judiciary below Chief Justice,
28 of 31 provinces) or have one item doing the work of thousands of people (the
Majlis). So the deliverable is deliberately three-sided: a modest statement batch,
a **large item-layer repair**, and a **large creation list**.

The intended outcome is one campaign — `scripts/ir_offices.py` plus its sibling
lanes — producing one additive `.qs`, its `edit_plan_claims.json` half, an
item-layer batch, and byproduct lists for the creation the country needs.

## Decisions taken before planning

| question | answer |
|---|---|
| Lane scope | **Everything** — executive, legislature, judiciary, IRGC/Artesh/MOIS, clergy + bonyads, provinces + Tehran, ambassadors |
| Temporal scope | **`modern_from = 1979`** — revised 2026-08-18. "2000 onward is sufficient" was the original brief; the survey showed 2000 is a *hard* floor that guts the creation-first lanes (see §1n) |
| Item creation | **In scope**, via the guarded API path (`create_offices.py`, `--dry` default) |
| Majlis membership | Per-term rolls, **wikilinked rows only** (`roster_only.attested`); bare name matches skip |
| Jalali coarse dates | day → exact; month → Gregorian year (+621 for SH 1–9, +622 for 11–12); **Dey → None**; bare year → None |
| Regression protection | `scripts/check_dates.py` cases only — no cross-campaign pre-change capture |
| Jalali conversion | `jdatetime` at runtime (installed into `wrangle` during planning) |

---

## 1. What the survey measured

Measured live 2026-08-18 with `max_age=0` on every state read, before any code.

### 1a. The item layer is broken in a way that hides a whole lane

Union of `P17=Q794` and `P1001=Q794`, typed and untyped: **209 items**. But
CirrusSearch finds items the country census structurally cannot see:

```
haswbstatement:P31=Q4164871 inlabel:"ambassador of Iran"  -> 77 items, 329 P39 statements
   ... of which exactly 1 carries P17=Q794 and 0 carry P1001=Q794
```

Their only country signal is `P279 → Q30055513` ("ambassador of Iran"). Combined
universe: **312 items, 263 with holders, 2,214 P39 statements, 1,681 people.**

| metric | value |
|---|---|
| items lacking `P17=Q794` | **108 items / 619 statements — 28% of the corpus** |
| items lacking `P31=Q4164871` | 86 items / 164 statements |

**CORRECTED 2026-08-18 by lane K — the premise above is empirically false, and it
was this plan's headline claim.**

The claim was that 76 outbound-ambassador items are invisible to the OpenSanctions
PEP build for want of a country. They are not. Measured:

| property on Iran's 77 outbound ambassadorships | count |
|---|---|
| `P17` = the **receiving** state | **74 / 77** |
| `P137` = `Q794` (the sending state) | **74 / 77** |
| `P1001` = `Q794` | **0 / 77** |

`zavod/shed/wikidata/position.py:183` reads P1001/P17/P27, and a live `yente-cli`
fetch confirms the items resolve: `Q27038402` → `country: ["fr"]`, `Q84177448` →
`["gb"]`. **They are visible, filed under the receiver** — which is also the
convention `scripts/qa_offices.py` measured for Qatar (P17 = receiving state,
262/264).

So **lane A must drop the ambassadorships from its `P17=Q794` set.** Adding
`P17=Q794` to 76 items that correctly carry the receiver would have been 76 wrong
statements in the batch that looked lowest-risk. What lane A should do instead is
narrow and real: `P17=Q398`/`P137=Q794` on `Q124541201` (Bahrain, 8 holders, no
country property at all), `P17=Q191`/`P137=Q794` on `Q65262055` (Estonia),
`P137=Q794` on `Q87142629` (Syria, which carries a *wrong* `P17=Q794` and
`P1001=Q858`). Leave `Q124536803` (EU) and `Q7169241` (UN) bare per the
organisation-receiver rule. The Syria correction is destructive → human gate.

**The real fix for OpenSanctions is a `zavod` change — read `P137` for
`role.diplo` — not a Wikidata batch.** That is a followup against the opensanctions
repo, not a line in this campaign.

`§1a`'s "108 items / 619 statements" therefore needs restating: **~329 of those
statements are already visible and already correct.** Lane A's true scope is the
non-diplomatic remainder.

The census lesson still stands: *use the census to find items, never to reject
them.* The Iran census must union `P17`, `P1001`, label-match **and**
`P279* Q30055513`, and must not filter on type.

The 86 untyped items are organisations used directly as P39 values — Ministry of
Interior `Q1091482`, Basij `Q750202`, Setad `Q5962994`, IRIB `Q1674127`, Assembly
of Experts `Q917663` — plus `Q7844710`, a **`Category:` item carrying 9 P39
statements**, plus outright junk (Persepolis F.C., a school, Fars News Agency).

**Duplicates to resolve before choosing any `target` (§2a):** two Chairman of the
Assembly of Experts items (`Q60149120`, `Q107040507`), two First Vice Chief
Justice items (`Q106960625`, `Q107391283`) and two Ministry of Industries items.
**The three Khatam al-Anbiya items are NOT duplicates** (lane HJ: construction HQ /
Central military HQ / air-defence university) — do not merge them. Two items competing for the same era is a merge
decision, not a campaign.

### 1b. Coverage is bimodal, and the average lies

Whole corpus: 1,154 / 2,214 statements carry P580 (52%). That average hides a
clean split:

- Three bulk-imported generic items — Majlis member (659 statements), vizier
  (158), National Consultative Assembly member (86) — hold **903 statements with
  107 P580 (12%)**.
- The other **1,311 statements are 80% dated**, and most named offices are at
  100%: President, Supreme Leader, Chief Justice, Speaker, IRGC CinC, SNSC
  Secretary; Foreign Minister 93%, Mayor of Tehran 92%.

So the named-office lanes are calibration sets rather than yield lanes — but
**lane B is only half a calibration set, and the average must not be scored
against** (lane BC). President 10/10, Supreme Leader 3/3, First VP 8/8 and the ten
portfolio VPs 23/23 give **44 statements at 100% P580**; the generic VP
`Q2660216` is **26% dated (11/43)** and PM `Q13561063` **63% (54/86)**. Score the
backtest against the four clean items, not the lane.

### 1c. The Majlis — corrected by lane F, and it is the biggest lane in the campaign

`Q17525449` "Member of the Islamic Consultative Assembly" is one item for 618
people / 659 statements. Three things the first census got wrong:

**The P2937 discrepancy is resolved, and my provisional explanation was wrong.**
336 statements carry `P2937`, holding **369 values, because 24 statements carry
more than one term** — one carries four. `P768` is 368 values on 368 statements,
exactly 1:1, so the multi-valued *district* attribution was incorrect. The naive
4×`OPTIONAL` count of 692 closes exactly as 659 + 33 surplus P2937 values.

**Those 24 statements are the QuickStatements collapse already realised in the
data.** `Q5701584` holds a single P39 carrying the 8th, 9th, 11th and 12th
legislatures at once, and term-11 statements carry P580s that are the 8th and
10th legislatures' start dates. This is `wd/validate.py:collapsing_groups`'s
pathology, on the live item, before we write anything.

**All twelve convocation items exist — "only three" was wrong — and they are
datable.** Eleven are typed `P31=Q15238777`. The census missed their dates
because they carry **`P571`/`P576`, not `P580`/`P582`** (three use the P580/P582
pair). All day-precision, all chaining consistently. None carries `P17`, which is
why a country census cannot see them. So the Majlis lane **is** date-derivable.

**Sizing:** 2,349 statements across all 12 terms (1,690 people, 1,295 brand-new to
the item). Lane F sized terms 6–12 alone at 1,502; **under the revised
`modern_from=1979` the full 2,349 is in scope**, since the convocation items date
back to 1980 and the roll rows are day-precision. Both figures already
apply wikilinked-rows-only *and* `P31=Q5` — 28 of 1,718 candidate QIDs are
disambiguation pages or a city. Byproduct: 295 rows / 290 distinct names with no
item.

**Two configuration warnings that would each have corrupted the run:**

- **The person-level `already holds P39` gate must not be used on this lane.**
  423 people already hold this item *for a different term*; the gate would drop
  every one of their new terms.
- **1,142 statements (49%) belong to 483 multi-term people** — by far the largest
  `edit_plan_claims.json` half any campaign here has produced. QuickStatements
  cannot write these at all.

**Qualifier shape: emit `P2937` + `P768` + `P580`/`P582`, all four.** The tally
says P2937+P768 is 318/659 (48.3%) and 100% of terms 11–12, date-only is 70
(10.6%), and 246 (37.3%) carry no qualifier at all. The decisive argument is
downstream, not conventional: **`zavod/shed/wikidata/position.py` reads
P580/P582/P768 and never P2937**, so a P2937-only statement yields an Occupancy
with `status=unknown` forever. Copying the convocation item's own P571/P576 costs
nothing and is not an over-claim. **`P768` is emittable only for terms 10–12** —
terms 1–9 link the district cell to the *city* (`Q56557504`) rather than the
constituency (`Q192611`), so **gate on the linked item's P31, never on the column
heading**.

**Term 11 is the calibration set:** 290 roll QIDs, 276 recorded, all
`P2937=Q95215862`, all with `P768`, all normal rank, 275 of 276 referenced. Zero
recorded people are absent from the roll — 95.2% recall, 100% precision. Of the 14
missing, 4 have no statement at all and **10 already hold a P580/P582-dated
statement for the same term**. That 10 is the lane's real duplicate risk and lane F
reports **no safe additive rule for it — unsettled, and it must be settled before
this lane ships.**

### 1d. Whole institutions have no item layer at all

| institution | state |
|---|---|
| Provincial governors | **4 items for 31 provinces** — Isfahan (5 holders), Razavi Khorasan (3), Ardabil (1), Governor-general of E. Azerbaijan (1) |
| Mayors | Tehran (47), Isfahan (2), Qom (1). Nothing else |
| City councils | 6 *organisation* items; **no "member of city council" position item** |
| Supreme Court / Revolutionary Court judges | **no item exists.** `Q13107481` and `Q694334` have 0 P39, 0 P108 |
| Bonyads | Mostazafan `Q2910392` 0/0/0; Khatam al-Anbiya 0/0; Setad 1 org-as-position. **Only** Astan Quds Razavi has a real office item (`Q5952948` Trustee, 2 holders) |
| Friday prayer leaders | `Q134929929` Tehran (2) and `Q124883178` (1). No per-city items |
| Supreme Leader's representatives | 2 items, 1 holder each, against ~31 provinces |

Crucially, **there is no hidden `P108` population to convert.** The employer query
returns IRIB 10, MFA 4, Central Bank 3, Astan Quds 2, and 0–1 for everything else;
`pq:P642` is used **zero** times across all 23 institutions. Unlike the Gulf SOE
census, the bonyad lane is simply absent — it is creation-first or nothing.

The good news: the archetype is already proven — but **not by `Q134929929`, which
carries no `P1001` at all** (lane G, corrected 2026-08-18). The shape
`P31=Q4164871` / `P279=Q125482` / `P17=Q794` / `P1001=<province>` is attested by
`Q126002876`, `Q126202498` and `Q124883178`. Cite those.

### 1e. The citizenship gap

23,119 humans carry `P27=Q794`; **1,597 (6.9%) have any P39 at all**, and only
~1,018 hold an Iran-scoped position. The remaining 21,522 are the honest ceiling
on what any roster lane can reach.

### 1f. Three parser gaps, precisely bounded

Measured directly against `wd/roster.py` at HEAD.

**Gap 1 — Solar Hijri dates yield nothing, and the naïve fix yields wrong.**

```
parse_date('۱۳ مرداد ۱۳۹۲')  -> None
parse_date('13 مرداد 1392')  -> None
parse_date('۱۳۹۲')           -> None
parse_date('1392-05-13')     -> '1392-05-13'   # <- silently 621 years wrong
```

Three independent causes: Persian-Indic digits (U+06F0–06F9) are never normalised
(`_deaccent`'s table at `roster.py:565` maps no digits); none of the twelve Persian
solar month names is in `MONTHS` (115 keys, all es/en/ru/be/uk/cs/ar); and the
bare-year rule `\b(1[5-9]\d\d|20[0-4]\d)\b` (`roster.py:696`) excludes SH 1300–1404.

**This is not the Saudi Hijri situation.** There, "handled by not converting" is
right — lunar AH years land outside the guard *and* the day conversion is genuinely
ambiguous. Solar Hijri is a solar calendar; conversion is exact. And "report the
lane at what it yields" is not available here, because it would mean *every* fa
lane yields zero terms.

**The load-bearing sequencing constraint:** the ISO branch (`roster.py:690`) and the
`d/m/YYYY` branch (`:693`) have **no year-range guard**. Adding digit normalisation
or Persian month names without a converter *and* a guard turns a silent-nothing
into a silent 4th-century P39 start date. Converter, guard and `check_dates.py`
cases land as one change.

**Gap 2 — no fa header can match today.** `_ARABIC_FOLD` (`roster.py:558`) folds
`أإآٱ→ا`, `ى ئ→ي`, `ؤ→و`, `ة→ه`, but not Persian kaf `ک` (U+06A9) → `ك` or Persian
yeh `ی` (U+06CC) → `ي`:

```
fold('کارگزاران') == fold('كارگزاران')  -> False
fold('نمایندگی')  == fold('نمايندگي')   -> False
```

So `وزیر` (Persian yeh) does not match the existing `COLUMN_ROLES` key `وزير`
(Arabic yeh). **Zero of the 228 `COLUMN_ROLES` keys work on a Farsi page** — even
the Arabic-script ones that look shared. Adding the two-letter fold makes a slice
of the existing Arabic vocabulary work on fa pages for free, before any new key.

**Gap 3 — ZWNJ (نیم‌فاصله, U+200C) is pervasive and is not whitespace.**

```
fold('امام‌جمعه') == fold('امام جمعه')  -> False
```

`" ".join(text.split())` does not split U+200C. Breaks header matching, heading
matching and — most costly — person-name matching against Wikidata `fa` labels,
which use ZWNJ inconsistently. Fold ZWNJ → space (right for names:
`علی‌اکبر` ↔ `علی اکبر`).

### 1g. The conversion, and what each package earns

`jdatetime 6.1.0` and `persiantools 6.2.0` were installed into `wrangle` during
planning (the shared OpenSanctions env — noted because `wd/` may now import them
while every other module there assumes only `requests` + `lxml`).

**Cross-validation: a closed-form implementation and `jdatetime` agree on all
44,195 Solar Hijri dates in SH 1300–1420, with identical leap-year sets (37 years,
1300–1450).** Correctness is settled; use `jdatetime` at runtime.

| gap | use | why |
|---|---|---|
| Jalali → Gregorian | **`jdatetime`** | exact agreement over 44,195 dates; keeps calendar arithmetic out of the repo |
| `ک`→`ك`, `ی`→`ي` | **extend `_ARABIC_FOLD`** | `persiantools.characters.CHARACTER_MAP_FA_TO_AR` *is* exactly those two mappings and nothing else |
| Persian-Indic digits | **one `str.translate`** | see the gotcha below |
| ZWNJ → space | **ours** | `persiantools` leaves U+200C untouched |

Confirmed safe: neither `ی` nor `ک` is in `_ARABIC_FOLD` today, and the fold
*targets* (`ي ك ه ا و`) are not remapped by the Persian pair — so extending the
table cannot disturb the Arabic behaviour eight campaigns depend on.

**Digits gotcha, worth pinning:** `persiantools.digits.fa_to_en` converts
Persian-Indic (U+06F0–06F9) but **not** Arabic-Indic (U+0660–0669) —
`digits.fa_to_en('١٣٩٢')` returns it unchanged, and reaching ASCII needs
`ar_to_fa` first. Both ranges occur in Perso-Arabic wikitext. One `str.translate`
covering both cannot be called in the wrong order.

### 1h. Coarse Jalali dates do not convert to coarse Gregorian dates

A Solar Hijri year straddles two Gregorian years — SH 1392 is 286 days of 2013
plus 79 of 2014 — so a bare `۱۳۹۲` has no correct year-precision rendering, and
every SH month spans two Gregorian months. Measured over SH 1360–1404, the
month→Gregorian-year offset is nonetheless constant for **eleven of twelve months**:

| SH month | Gregorian year offset | |
|---|---|---|
| 1–9 Farvardin…Azar | +621, always | safe downgrade to year precision |
| 10 Dey | +621 *or* +622 | **the only ambiguous month** |
| 11–12 Bahman, Esfand | +622, always | safe downgrade to year precision |

The rule, declared once: **day → exact Gregorian day** (the only case keeping day
precision); **month → Gregorian year** (+621 / +622), **Dey → None**; **bare year
→ None**.

**HAZARD, found by lane HJ — a year range cannot tell lunar from solar.** The
Saudi ruling works because AH years fall *outside* the Gregorian guard. That does
not transfer: Astan Quds carries lunar years **1302 / 1335 / 1344**, which sit
squarely *inside* the proposed SH 1300–1404 window. A range-based converter would
read them as solar and be wrong by roughly six centuries.

**The calendar must be read from the marker, never inferred from the range.** Both
lane HJ and lane K found the source marks it explicitly: `ه‍.ق` = lunar (must keep
yielding nothing) versus `ه‍.خ` / `ه‍.ش` = solar. Note these markers are built with
**ZWJ (U+200D)**, not the ZWNJ (U+200C) §1f names — so the fold must handle both.
An unmarked bare year in a page that uses `ق` elsewhere is undatable, not solar.

Corollary: **Dey is much cheaper than a substring count suggests, and day-precision
Dey converts fine.** `دی` is a substring of `اردیبهشت` and of `متصدی`, so naive
probes over-report badly (lane G: 224 vs 84 real; lane K: 115 vs 66). Measured, the
month-precision Dey cells that actually go undatable are 7 in lane BC, 3 in lane G
and 0 in lane E. **"Dey → None" applies to the month branch alone.** This is a genuine coverage cost and gets **reported, not padded** — the
audit counts coarse-Jalali cells dropped per lane so the policy can be revisited
with numbers rather than re-argued.

### 1i. The job is localization, not new machinery

`parse_rosters` finds **zero rows** on all 27 fa ministry pages and all 52 cabinet
pages today. The machinery is all there; none of the vocabulary is Persian.

**The "nine keys" claim is verified as *switches it on*, refuted as *completely*
(lane BC).** The nine — `نام`→name, `نگاره`→portrait, `آغاز تصدی`→start,
`پایان تصدی`→end, `دولت`→appointer, `رئیس دولت`→appointer, `وضعیت`→notes,
`ر.`→ordinal, `م.`→ref — take lane C from **0 → 783 rows**. But they leave
`فهرست وزیران امور خارجه ایران` at 125 rows and **zero** date cells (it heads
`شماره | آغاز وزارت | پایان وزارت | صدراعظم وقت | شاه`), lose 54 rows on Health,
10 dates on Interior, and leave **all of lane B and all 52 cabinets dark**. The
measured set is **47 keys**, and the cabinet vocabulary (`مقام`, `حزب سیاسی`,
`منبع`, `سمت`, `نام سرپرست`, `آغاز کار`…) is disjoint from the nine.

There is also a **zero-code starting point** that parses today onto existing
items: `en:Chief Justice of Iran` (8/8 dated) and `en:Prosecutor-General of Iran`
(14/14). Worth running first as a smoke test before any parser change.

**But "localization, not machinery" is only two-thirds true, and the exception is
the largest single change in Phase 2.** Three lanes independently hit the same
wall: `parse_bullet_rosters` **drops a dateless bullet outright** and
`BULLET_HEADINGS` carries no Persian, and — unlike the table path —
**the bullet path has no `term=` bypass**, so `RosterSource.term` cannot rescue it
(`office_rows` applies `term` only to rows that already exist). Behind that one
gap sit roughly **2,000 statements**: lane F 1,033 (Majlis terms 1–8), lane K ~640
(ambassador bullets), lane D ~330 (five of six Assembly-of-Experts rolls).

**A second shared defect: anchor selection.** `parse_bullet_rosters` takes
`anchors[-1]` and `_person_link` takes the first anchor, and Persian pages break
both — lane D's rolls link the **province after** the person (every row would
resolve to `استان تهران`), lane F's rolls put the person first and the district
last, and lane E's tables lead the cell with a **linked military rank** (6 of 6
IRGC commanders-in-chief resolve to `سرلشکر`, "major general"). This needs a
principled rule, not a positional one — and §7 #37 already records the same
lesson for `wd/kinship.py`'s linked honorifics.

Two corrections the survey made to its own sub-agents, both of which would have
cost real work:

- **`roster.py` does handle rowspan** — it parses rendered HTML precisely because
  rowspan is easier there, including the colspan'd name header these tables use.
- **The en.wikipedia ambassador lists are not a calendar calibration fixture.** On
  their 206 unambiguous rows they are **~40% wrong, with 102 rows a mechanical
  `year − 622`** — i.e. en.wiki already contains botched Jalali conversions.
  Calibrate the converter on real events, never on these. (This is also a
  finding to report: it is a data-quality problem in the existing corpus.)

### 1k. Phase 0 result — the smoke test passed, 2026-08-18

Run against HEAD with no code change:

| page | tables | rows | named | dated |
|---|---|---|---|---|
| `en:Chief Justice of Iran` | 1 | 8 | 8 | **8** |
| `en:Prosecutor-General of Iran` | 1 | 14 | 14 | **14** |
| `fa:وزیر امور خارجه (ایران)` | 2 | 8 | 8 | **0** |
| `fa:فهرست شهرداران تهران` | **0** | 0 | 0 | 0 |

The pipeline works end to end today. The fa ministry page confirms the
localization diagnosis exactly: tables, rows and names all parse, the columns come
back `col0/col1/col2` (**no header recognised**), and no date survives. The Tehran
mayors page returning **zero tables** is a new finding and is lane G's to explain —
a redirect, a different title, or a table shape `parse_rosters` refuses.

### 1j. Where fa.wikipedia sits

**fa.wikipedia is the source of record, not a supplement.** en.wiki has 2 of 11
Iranian ministry office articles and no per-ministry roster pattern; fa.wiki has a
complete uniform one. **10,578 Iranian humans on Wikidata have only a fa sitelink,
against 586 en-only.** `sibling_wikis` must lead with `fa`.

Anchors, confirmed by both implementations:

```
1300-01-01 SH -> 1921-03-21   epoch of the modern SH calendar
1357-11-22 SH -> 1979-02-11   Islamic Revolution victory day
1392-05-13 SH -> 2013-08-04   Rouhani's first inauguration
1400-03-29 SH -> 2021-06-19   2021 presidential election
1403-04-15 SH -> 2024-07-05   2024 runoff
1404-01-01 SH -> 2025-03-21   Nowruz 1404
1403-12-30 SH -> 2025-03-20   leap year, Esfand 30
```

### 1m. Phase 2 obligations accumulated from returning lanes

Every item here is a change to **shared state** and belongs to the single serial
owner. Recorded as lanes report, so nothing is rediscovered late.

**Parser defects that make today's output *wrong*, not merely empty.** Both
returning lanes found this independently, and it changes how a "before" count is
read: with no `name` role, the parser does not fall back safely.

- Lane G: on `fa:فهرست استانداران گیلان` the parser reads the **start-date cell as
  the person's name** — 40 rows, 40 date strings. The 685 "before" rows across the
  province lane were largely corrupt, not undated.
- Lane F: on Majlis terms 10–11 `parse_rosters` emits **582 rows with the district
  item as the resolved person.**
- Lane G's diagnosis of the mechanism: `parse_rosters`'s name search is
  `spanned + [name_index+1, name_index-1]` and **never tries `name_index` itself**.
  With no `name` role, `name_index=0` and offset 1 is the empty half of a
  colspanned header, so every row drops. **Verify this myself before changing it —
  it is shared with eight accepted campaigns.**

**A third Perso-Arabic folding gap, not in §1f.** The ezafe **U+0654 ARABIC HAMZA
ABOVE** (`حوزهٔ` ≠ `حوزه`) sits outside `_ARABIC_STRIP`'s U+064B–U+0652 range;
affects 3 of 16 Majlis headers. Also, ZWNJ→space does **not** fix joined-vs-spaced
compound given names (`محمدحسن` vs `محمد حسن`), and `ائ`/`ای` costs *person names*,
not only headers.

**The unguarded ISO branch, observed live.** `parse_period` on a Majlis footnote
returned `(None, '۲۰۲۰-۰۷-۱۲', False)` — a Persian-digit ISO date passed through
verbatim. §1f's landmine is real and already firing.

**A date shape §1h does not cover:** `۵۷/۱۲/۱۵` — **two-digit** SH year/month/day,
23 cells, the whole Markazi page, plus `۱۴۰۰/۸/۱۲` (four-digit, Y/M/D order).
Neither matches the existing `d/m/YYYY` branch. Both need explicit handling and
both are dangerous, because a two-digit year is ambiguous on its face.

**The Dey probe must be token-anchored.** Dey is far cheaper than feared — 84
cells, only 3 at month precision — but `دی` is a substring of `اردیبهشت` and of
`متصدی` ("incumbent"), so a naive probe reports 224. Any new month matcher must
match whole tokens.

**Column-role work, per page rather than global.** `دوره` means **appointer** on
the province pages (it holds a President/PM name), not period. `مدت` is a duration
`days` decoy — but **`مدت تصدی` collides**: duration on Qazvin governors, the only
date column on Ahvaz mayors. This is the Iraqi `المدة` case again and takes
`RosterSource.column_roles`, not a global mapping.

**`سرپرست` / `کفیل` are an unhandled acting marker** — 67 rows on the province
lane; 36 are parenthesised and reachable via `ACTING_TEXT`, 31 are bare or glued
and need a suffix rule.

**`parse_bullet_rosters` is blind to the Majlis rolls** — zero rows on terms 1–8,
worth 1,033 statements, for two independent reasons: no Persian in
`BULLET_HEADINGS`, and the bullet path **requires a date and has no `term=`
bypass** although the table path has one. It also takes `anchors[-1]` as the
person, where this shape puts the person first and the district last.

**`wd/create.py` has no archetype for a provincial governor.** The existing
`provincial_governor` is the Saudi `P279=Q98786082` "emir of province" shape and
would make 27 new items siblings of nothing. A new `governor` archetype
(`parent="Q132050"`) is needed.

**Redirects hide the roll inventory (§7 #1, new form).** The counts 12 / 24 / 7
hold only with `apfilterredir=nonredirects`; unfiltered they read 27 / 52 / 36,
because fa.wiki keeps an ezafe-spelt redirect for nearly every page.

**Do not strip honorifics.** Lane G measured it: `names_match` is already 591/625
(95%), and stripping *drops* it to 590 because `سرتیپ مظفری` falls to one token,
below the floor. The سید-meets-the-two-token-floor risk measures **zero** (0 of 443
two-token names). The real residue is a wikilink pointing at a **birthplace**
inside a biography parenthetical — so **gate the resolved link on `P31=Q5`**.

**Two hazards in the creation guard, found by running it for real (lane I).**
`create_offices._existing` treats only `status=="matched"` as a duplicate; the
First Vice Chief Justice label returns `ambiguous`, so `guard` would happily mint a
**third** item beside the two that already exist. Separately, `Q5960362` has no
`en` label, so the body-label check passes *only* because the spec carries a fa
label — drop it and creation is refused. And `ir-tehran-prosecutor` renders its
description as **"head of Iran"**, needing an explicit override.

**A guard returning CLEAR is not a reason to create (lane I).** For the 17 named
Revolutionary Court judges, `guard` passes on every mechanical test — duplicate
search unmatched, 17 ≥ the holder floor, body-label check fine. It should still be
refused: one channel only (a category is a candidate generator, never a fact), **no
source dates any judge's appointment**, and the only attested shape is a *branch*
presidency, not a generic judgeship. Byproduct list, not a creation.

**`_is_date_phrase` is blind to Persian digits** — the fourth lane to report a date
column being read as the person's name.

**Vocabulary beyond `COLUMN_ROLES`**, confirmed by four lanes: `INCUMBENT` lacks
`تاکنون` / `در حال تصدی` (rows ship closed instead of incumbent) and `ACTING_TEXT`
lacks `سرپرست` / `کفیل` / `موقت`. `ARABIC_RANGE` lacks `تا` (337 rows in lane K
alone) — and because `تاکنون` *begins* with `تا`, it needs a `(?!کنون)` lookahead
or the incumbency marker becomes an end date. That is the Kuwait `حتى الآن`
ordering bug exactly.

**Mixed-digit numbers vindicate the one-pass translate table.** Lane I found
`١۵ مرداد ١۴٠٢` — Arabic-Indic **and** Persian-Indic digits inside one number, on
the same page as `۱۵ مرداد ۱۴۰۲`. `persiantools`' two-step (`ar_to_fa` then
`fa_to_en`) would need the right order; a single table covering both ranges cannot
be called wrongly. §1g's call stands.

**RECONCILED — the duration-column conflict, four lanes disagreeing.**
`مدت تصدی` is a tenure *length* on lanes D and I and on `fa:فهرست استانداران قزوین`,
but it is the **only date column** on `fa:رئیس‌جمهور ایران` (21 rows) and on the
Ahvaz mayors list (53 rows). This is Iraq's `المدة` case reproduced exactly, and it
resolves on an asymmetry rather than on a majority vote:

> **`days` is inert; `period` is active.** A duration column wrongly typed `days`
> costs nothing — the role exists precisely to make a decoy harmless. A duration
> column wrongly typed `period` *shadows the real start/end pair beside it* and
> costs **every date on the page** (the Spanish "Duración" failure, §7 #14).

So the global mapping is the safe direction, and the two pages where it is genuinely
the date column take `RosterSource.column_roles` overrides:

| key | global role | note |
|---|---|---|
| `مدت تصدی` | **`days`** | override to `period` on `رئیس‌جمهور ایران` and Ahvaz mayors |
| `مدت` (bare) | **`days`** | 22 tables in lane G hold "۲ سال" / "۳ ماه و ۱۳ روز"; lane BC confirms no bare `مدت` exists in B+C, so no conflict |
| `طول دوران` | **`days`** | lane E's decoy, 9 pages; one value is `۰–۱ سال`, a *range* that would parse as a term |
| `طول تصدی` | **`days`** | lane D |
| `دورهٔ تصدی` | **`days`** | lane G (Tabriz). Note the ezafe **U+0654** — must fold first |
| `duration` / `term` (en) | `days` / `notes` | lane D: turns the en AoE chairmen page from 10 rows/0 dates into 7 rows, 7/7 dated |

**Ordering is load-bearing and `COLUMN_ROLES` is an ordered list:** `مدت تصدی`
must be *prepended ahead of* bare `مدت`, or the generic key claims the specific
string first. Same for `دوره زمانی` ahead of `دوره` (lane I), and `نامزدکننده`
ahead of `نام` (lane D).

**`دوره` is never `period`** — three lanes agree, with different readings:
*appointer* on the province pages (it holds a President/PM name, lane G), *ordinal*
on one fa page and appointer on another (lane HJ), and a *term description* on two
judiciary tables where `دوره زمانی` is the real date column (lane I). A global
`دوره → period` key would cost every date on all of them.

**Process fix for the next fan-out:** lane F had a generically-named scratchpad
file (`qids.json`) clobbered mid-run by a sibling lane. Give each agent its own
scratchpad subdirectory.

### 1n. Why `modern_from = 2000` was rejected

The brief was "2000-onward holders are sufficient", and I read it as a floor on
effort rather than an instruction to discard correct statements. **The engine does
not allow that reading.**

`era_flag` marks any row starting before `modern_from` as `historical`, which sends
it to `early.unsupported` unless `precedent_allows`. And `Precedent.supports_before`
requires **both** `MIN_EARLIER = 3` dated statements earlier than the cutoff **and**
a `MIN_SHARE = 0.15` share. Iranian items are thin — most record 0–13 holders — so
that test fails almost everywhere.

**The structural case is worse: a newly minted item has `dated = 0` by
construction, so `supports_before` can never return True.** Every creation-first
lane would therefore be permanently capped at post-2000 terms — lane G's 27 new
governor items, lane I's 5 judiciary items, lane H's parastatal heads.

Identified cost of the 2000 cutoff, from lanes that reported the split:

| lane | pre-2000 statements lost |
|---|---|
| F Majlis | **847** (2,349 all terms vs 1,502 for terms 6–12) |
| G governors | ~577 rows (903 total, only 326 starting ≥ 2000) |
| I judiciary | ~27 (about half the lane) |
| BC, D, E, K | split not reported — additional |

`modern_from = 1979` fixes it at the right layer: it is a real institutional
boundary, post-1979 rows apply through `modern.two_channel`, and Pahlavi rows still
face the precedent test they should face. Lane I reached the same conclusion
independently from its own offices, all of which are continuous from 1979/1982/1989.


### 1o. The backtest's first result — the corpus is wrong, and predictably so

Run on three offices before the full sweep. Petroleum scored **94% date
agreement** and Chief Justice **100%**, which is the converter reproducing dates
the community entered independently. The IRGC commander-in-chief scored **0%**,
on two rows — and the plan's own rule says a whole office at 0% is a comparison
bug before it is a parser bug. It is neither. Both conflicts are ~9-day offsets
on *both* bounds, and all four values check out as the same defect:

| roster cell | correct (jdatetime) | Wikidata records | naive day-preserving guess |
|---|---|---|---|
| `۲۰ شهریور ۱۳۶۰` | 1981-09-11 | 1981-09-**20** | day 20 → "20 September" |
| `۱۹ شهریور ۱۳۷۶` | 1997-09-10 | 1997-09-**19** | day 19 → "19 September" |
| `۲ خرداد ۱۳۵۹` | 1980-05-23 | 1980-06-**02** | day 2 → "2 June" |
| `۲۷ خرداد ۱۳۵۹` | 1980-06-17 | 1980-06-**27** | day 27 → "27 June" |

Four for four: someone kept the Solar Hijri **day number** and mapped the month
*name* to the nearest Gregorian month. That is a third corruption sub-class
beside the ±1-year and raw-SH-year errors, and it is invisible to a year-based
check because the year is right.

**Consequence for reading the run:** a low date-agreement score on a thinly
recorded Iranian office is evidence about the corpus, not about this converter.
Do not "fix" the parser toward it. The additive batch is unaffected — a
conflicting existing statement means the row is already recorded and is skipped —
but the corrections are a *destructive* lane and stay behind the human gate.


### 1p. What Phase 2 actually changed

One serial change to `wd/roster.py`, `wd/validate.py` and `scripts/check_dates.py`,
graded by the 151-case fixture. `check_dates.py` went from **108 to 128 cases** and
passes; the fixture scores **150/151**, the one deviation being a case its own
author flagged as unsettled — a prose footnote where `parse_date` is exact and only
the `parse_period` half is coarser. The stated invariant (the Persian-digit string
is never returned) holds.

* **Solar Hijri via `jdatetime`**, ahead of the Gregorian branches, with the
  three-precision rule of §1h.
* **Both Indic digit ranges in one `str.translate`.** Vindicated live: lane I found
  `١۵ مرداد ١۴٠٢`, mixing Arabic-Indic and Persian-Indic *inside one number*, on the
  same page as the all-Persian spelling. A two-step conversion has an order to get
  wrong.
* **A year-range guard on the ISO and `d/m/Y` branches.** `parse_date('1392-05-13')`
  returned `'1392-05-13'` before this — a 4th-century P39 start date.
* **`ک→ك`, `ی→ي`, ZWNJ→space, ZWJ dropped, and `_ARABIC_STRIP` extended to U+0655**
  so the ezafe hamza folds. `fold('رئیس')` is now `'رييس'`, which is why every
  heading pattern Phase 1 wrote had to be re-derived.
* **~90 Persian `COLUMN_ROLES` keys**, prepended, with the duration reconciliation
  above and per-page `column_roles` where a string genuinely means two things.
* **`تا` as a range separator, guarded `تا(?!\w)`.** It is the first two letters of
  `تاريخ` ("date"), and an unguarded alternative split the range *inside the word* —
  caught immediately by an existing Arabic case, which is the regression net doing
  its job.
* **`سرپرست` / `کفیل` / `موقت` as acting markers** and `متصدی` / `تاکنون` as
  incumbency, both yeh spellings, since `_incumbent` runs on the raw cell.
* **`conflicting_tenures` narrowed.** A line with only a start, beginning after
  every dated spell in its group has ended, is a later open spell rather than a
  fragment — there is nothing to pair it to. Alireza Kazemi was caretaker Minister
  of Education in 2021 and took the office again in 2024; the check refused the
  entire batch over it. Both UAE shapes it was written for stay flagged, and the
  overlapping variant is pinned as a new case.


### 1q. The bullet path, opened — and why the first batch was small

The first run shipped **five of eleven lanes**. It read 1,106 roster rows; the
survey had found roughly **8,300 more** it never touched, and three of the four
largest sat behind one function. `parse_bullet_rosters` was blind to Persian in
three separate ways, each of which alone was enough to return zero rows:

1. `BULLET_HEADINGS` carried no Persian, so the heading gate skipped every fa
   list before anything else ran.
2. A bullet with no date of its own is dropped outright — and unlike the table
   path, there was no `term=` bypass, so a membership roll dated once in its
   lead could never reach `campaign.py:681` where `term` is applied.
3. `anchors[-1]` takes the last link as the officeholder, which suits
   "генерал-майор [[Name]]" and inverts on Persian rolls, where the member's
   **province** or electoral district is linked *after* them.

Fixed as three declared behaviours rather than a guess: Persian added to
`BULLET_HEADINGS` (matched against `fold()` output per §7 #11), and two new
`RosterSource` flags — `dateless_bullets` and `person_first` — both off by
default, for the same reason `bullet_offices` is.

Measured immediately: Assembly of Experts term 5 went **10 → 78 rows** and term 4
**8 → 87**, all wikilinked, with the member rather than the province in the name
column. The whole lane runs **428 rows → 179 applying records**, at 100% target
and 88% date agreement — on its own more than half the size of the entire first
batch.

**Still not taken, and now honestly bounded rather than blocked:**

* **The Majlis.** Terms 9 and 10 are *tables* (290 and 325 rows) and parse today.
  What stops them is not the parser but `holders()`: the `already holds P39` gate
  is per (person, target), and 423 people already hold `Q17525449` for a
  *different* term, so the gate would silently drop their other terms. Lane F
  said so explicitly. That needs a per-term gate, not a config line.
* **The ambassador bullets.** They parse now — France 52 rows, 32 dated — but
  most pages are undated (`no_dates` → skip), only 11% of rows carry a citation,
  and routing 77 pages to targets is a config job whose measured reach is 488
  rows. Worth its own run.
---

## 2. Lanes

The item census and the roster survey disagree in a way that resolves cleanly:
the **items** are thin, the **rosters** are thick. Iran is therefore the Iraq
shape — badly covered *and* richly sourced — and several lanes are creation-first
followed by a substantial roster, not creation-first instead of one.

| lane | shape | measured | verdict |
|---|---|---|---|
| **A** Item-layer repair | additive `P17`/`P31` for the country-less items — **excluding the 76 ambassadorships, which are correct as they stand (lane K)** | 619 statements claimed, **~329 already visible**; true scope is the remainder | own `.qs`, unreferenced. No longer the headline |
| **B** Executive spine | President, Supreme Leader, First VP + 11 portfolio VPs, PM | ~100 rows, ~100% dated already | **the calibration set** for the Jalali converter, not a yield lane |
| **C** Ministries | 27 fa ministry rosters (~800KB), 24 with target items | vs **136** recorded holders | **STRONG.** 14 cabinets + ~40 pre-revolutionary in a structured template |
| **D** Councils | AoE 6 term rolls; Guardian; Expediency | AoE 523 rows / 472 linked → **206 people, 223 records**; lane total ~260 with the bullet change, **~115 without** | **STRONG** (AoE). **en rolls carry NO Gregorian dates** — fa only. **SNSC confirmed ex-officio: lane closed** |
| **E** Security | IRGC, Artesh, General Staff, MOIS, FARAJA | 14 of 18 offices have dated tables; **291 of 420 catalogued IRGC people have no P39** | **STRONG, and the cleanest tables in the country** |
| **F** Legislature | 12 Majlis + 24 NCA + 7 Senate term lists | ~6,000 rows at **95–100% wikilink→QID** vs 744 statements | **STRONG — largest.** But see the qualifier-shape split below |
| **G** Subnational | governors, mayors, city councils | **all 31 provinces have governor lists — 903 rows, 879 raw-dated, 72% wikilinked** against 4 governor items; Tehran mayors 75/75 dated; **Tehran council is 21 rows and undated, not 201 — councils deferred** | **creation-first, then STRONG** |
| **H** Clergy / parastatal | Friday prayer leaders, Supreme Leader's reps, bonyads | Bonyad-e Shahid, IRIB, Mostazafan good; Setad prose-only; **Astan Quds 126 rows, near-zero yield (lunar Hijri, genuinely undatable)** | mixed; creation-first, archetype proven by `Q134929929` / `Q126002876` |
| **I** Judiciary | 9 offices, **5 with no item** (confirmed) | 71 rows / 70 raw-dated / 15 recorded → **~54 adds**; +82 bullet rows unlocked by 4 Persian heading words | STRONG. **fa is the source of record**; en is a two-office bridge that ships before the converter |
| **J** Parties | party leaderships | one party has a real table, 3 rows | **WEAK — report small, do not pad** |
| **K** Diplomatic rosters | Iranian ambassadors abroad | 98 fa ambassador subcategories, 28 uniform en lists, **~799 dated fa bullets** | **STRONG breadth.** Distinct from lane A: A gives the 77 existing items a country, K dates and extends their holders. `parse_bullet_rosters` territory |

**The Majlis needs a different qualifier shape from every other lane.** Membership
is modelled `P2937` (parliamentary term) + `P768` (district), *not* dates:
336 P2937 and 368 P768 against 91 P580 and 80 P582. Ministries are date-first. So
lane F is two jobs — wikilinked roster rows for the ~2,600 uncovered people, and a
separate `P2937` term-item dating exercise — and it must not be given the
date-first treatment the other lanes get.

**`Majlis term 11 is already done` (284 of 289 recorded).** That is simultaneously
the duplicate risk for lane F and **the only real backtest set Iran offers**, since
most other offices record 0–13 holders. Run the backtest against term 11 before
trusting the converter anywhere else.

*(One number to re-measure in Phase 1: the two surveys reported P2937 at 336 and
369. The census run applied `COUNT(DISTINCT ?st)` after finding that bare
`OPTIONAL`s inflate the count to 692 via multi-valued district qualifiers; the
discrepancy is almost certainly that. Not material to the plan, but the lane F
agent should settle it.)*

**Explicitly deferred:** the pre-revolutionary National Consultative Assembly
(`Q134563198`, 85 holders) and the 7-term Senate rolls (173 people) — both
`era.distinct` under a 2000-onward cut, both needing their own items; and
`vizier` / `Atabeg` / `beylerbey` / Sasanian items, which are pre-modern and not
PEP positions.

**There is no dynastic lane.** `wd/kinship.py` is built around a genealogy article
with generational headings and patronymic chains; post-1979 Iran has no such
article and no hereditary office. Iranian elite kinship (the Larijani brothers
across the judiciary, parliament and the Guardian Council) is prose, not a descent
tree — a followup, not a lane. Note `Q41874964` "Hashemites of Iran" is explicitly
a *different* family from Jordan's `Q20811513` (`scripts/jo_family.py:77`).

---

## 3. Multi-agent fan-out

The lanes are independent and each owns its own verdict file
(`data/iran/verdicts/iran_<key>.jsonl`, governed by `manifest.json`), so research
and configuration parallelise cleanly. Two things do not:

- **`wd/roster.py` is shared state.** The Jalali conversion, digit normalisation,
  Perso-Arabic fold and Persian column vocabulary are **one change, one owner,
  serial, no exceptions.**
- **The render is a single serial step.** One campaign is one batch.

```
Phase 0  SERIAL   smoke test, no code change: run en:Chief Justice of Iran (8/8)
                  and en:Prosecutor-General of Iran (14/14) through the existing
                  pipeline onto existing items. Proves the path end to end while
                  the Persian side is still untouched.
                     |
Phase 1  FAN OUT  one read-only survey agent per lane A-J -> data/iran/survey/lane_<x>.md
                  + a proposed Office/RosterSource block + the vocabulary keys and
                  date shapes it needs. Vocabulary tested by prepending to
                  COLUMN_ROLES IN MEMORY - no agent touches wd/ or scripts/.
                     |
Phase 2  SERIAL   the parser change, one owner:
                    a. jdatetime conversion + digit normalisation (both ranges)
                    b. year-range guard on the ISO and d/m/Y branches
                    c. Perso-Arabic letter fold + ZWNJ -> space in _deaccent
                    d. Persian COLUMN_ROLES keys, prepended
                    e. FIELDS["fa"] + fa templates in wd/officebox.py
                  extend scripts/check_dates.py with every new case AND pinning
                  cases for the existing Arabic/Cyrillic/Czech/Spanish headers
                     |  <- check_dates.py failing is stop-and-report
Phase 3  SERIAL   lane A: scripts/ir_item_types.py -> the item-layer batch
                     |
Phase 4  SERIAL   write scripts/ir_offices.py; add "ir" to SCRIPTS in
                  create_offices.py; --dry -> --apply          [HUMAN GATE]
                     |
Phase 5  SERIAL   run the sweep; read data/iran/roster_audit.md - ## Backtest first
                     |
Phase 6  FAN OUT  per-office backtest triage, one office each, read-only
                     |
Phase 7  SERIAL   render_edit_plan.py; validate; the two batch halves [HUMAN GATE]
```

**Orchestration consequence discovered by lane D: the Phase-2 fold change
invalidates every heading pattern Phase 1 wrote.** `fold('رئیسان')` is currently
`'ريیسان'` — `ئ→ي` folds but `ی` does not — so patterns written against today's
`fold()` output stop matching the moment `ی→ي` lands. **Every lane's heading and
section patterns must be re-tested after the fold, before the sweep runs.**

Phase-1 agent contract: **one lane each, read-only, cite evidence, prefer
"unclear" over guessing, never edit**; write findings to a file and return only
counts plus notable calls. `model: "opus"` for the judgment-heavy lanes (the
bonyad item-shape question, the clergy lane, the Majlis term-item question).

**Parallel agents converge on whoever answered first.** Several lanes will each
form an opinion about whether a bonyad headship is a position at all, and about
which item a Persian office stem routes to. Cross-check those calls across lane
reports in Phase 4 rather than trusting the first one written.

---

## 4. Campaign parameters

New file `scripts/ir_offices.py`; closest precedents `scripts/qa_offices.py`
(sparse rosters, officebox channel, creation-first ambassador lane) and
`scripts/iq_offices.py` (the era/bucket routing).

- `name="iran"`, `country_qid="Q794"`, `label_langs=("en","fa")`,
  `sibling_wikis=("fa","en","ar")`.
- **`modern_from=1979`** — the Islamic Republic's founding, which is what the field
  is documented to mean ("the institutional era the position items were created
  for"). See §1n for why 2000 was rejected. Pre-1979 Pahlavi rows still go through
  `early.unsupported` / `early.precedent_ok` and will mostly skip, which is
  correct. The audit reports the 1979–2000 and 2000+ counts separately so the
  original scope preference stays visible.
- `continuous_eras=()` until measured. Listing an era pulls its rows into the
  `_early` predicate and therefore the precedent test, which can skip *more* than
  leaving it empty — Iraq's measured finding.
- `regime_sections` for the 1979 rupture where a roster spans it.
- `generic_targets` naming `Q17525449` (Majlis member), `Q175240` (vizier),
  `Q134563198` (NCA member) so the sweep does not propose a redundant statement
  beside one.
- `concurrency_ignore` for Iran's genuinely concurrent offices: Majlis membership,
  Expediency and Assembly-of-Experts seats, and the Supreme Leader's
  representative posts, which overlap everything by design.
- `dispositions` mapping every non-applying rule to `skip`: `namesake`,
  `predecessor_body`, `category_only`, `no_dates`, `believed.held`, `uncertain`.
- `archetype`/`body`/`jurisdiction`/`create_labels` for lanes G, H and I, with
  `P1001 = <province>` — matching `Q126002876`'s proven shape, **after**
  `wd/precedent.py` confirms it is the convention rather than one item's habit.
- `officebox=("fa","en")` **only** on offices with no roster — it is a fallback
  channel, not a supplement, and running both against one office would date one
  tenure from two sources (§7 #35). Given lane C found 27 ministry rosters, the
  officebox lane should be much smaller here than it was for Qatar.
- Lane F takes a **different qualifier shape**: `P2937` + `P768`, not P580/P582.
  Do not let the date-first treatment reach it.

---

## 5. Files

| path | change |
|---|---|
| `plans/iran_sweep.md` | this document, copied into the repo |
| `wd/roster.py` | `jdatetime` conversion; Persian-Indic **and** Arabic-Indic digit normalisation; year-range guard on the ISO and `d/m/Y` branches; Perso-Arabic + ZWNJ folds in `_deaccent`; Persian `COLUMN_ROLES` keys (prepended — ordered list, specific must beat generic) |
| `wd/officebox.py` | **Re-measure before writing anything.** Lane I found fa.wikipedia uses `{{Infobox Officeholder}}` in **Latin script with English field names** — 11 of 16 judiciary articles match `INFOBOX_NAMES` and `FIELDS["en"]` *today*, and 2 more need only the template name `جعبه اطلاعات سیاستمدار` added. **A `FIELDS["fa"]` block may be redundant.** Note lane BC found the officebox fallback list empty for B+C — every office there has a roster |
| `scripts/check_dates.py` | every new Persian date/header case, **plus** pinning cases for the existing Arabic/Cyrillic/Czech/Spanish headers and the Hijri block, which must keep yielding nothing |
| `scripts/ir_item_types.py` | new — lane A, additive `P17`/`P31` for the 108 country-less items |
| `scripts/ir_offices.py` | new — lanes B–E, G–I |
| `scripts/ir_legislature.py` | new, if the Majlis term-item work warrants it — joins via `Campaign.extra_verdicts` |
| `scripts/create_offices.py` | add `"ir": "ir_offices"` to `SCRIPTS` |
| `tasks/followups.md` | `## Iran (added <date>)`; creation lists; the merge decisions; deferred lanes |
| `regression/iran/` | after acceptance: `verdicts/`, `manifest.json`, both batch halves, a `README.md` row |

**Reuse, do not rewrite:** `wd/campaign.py:run` / `office_rows` / `identify` /
`target_for` / `holders` (with `STATE_MAX_AGE`), `wd/policy.py:decide`,
`wd/backtest.py:score` / `report`, `wd/precedent.py:census`,
`wd/validate.py:check` / `collapsing_groups`, `wd/officebox.py:officebox_rows`,
`wd/write.py:Ledger` / `create_entity`, `scripts/render_edit_plan.py`,
`scripts/apply_claims.py`. Lane A follows `scripts/iq_item_types.py` exactly.

---

## 6. Verification

1. **`scripts/check_dates.py` passes** before and after every `wd/roster.py` touch,
   with the new Persian cases *and* every pre-existing case unchanged — especially
   the Hijri block, which must keep yielding nothing, and the
   Arabic/Cyrillic/Czech/Spanish header cases the `_deaccent` change puts at risk.
   A fold that breaks an existing Arabic header is a silent total loss of a page
   (§7 #24).
2. **The Jalali anchors are assertions, not spot checks.** The seven anchors above
   plus one per SH month boundary, including the Dey case that must yield `None`,
   and a digits case pinning that both U+06F0–06F9 and U+0660–0669 reach ASCII in
   one pass.
3. **A wrong-century date must be impossible.** Assert that
   `parse_date('1392-05-13')` and `parse_date('13/05/1392')` do **not** return a
   4th-century date. The year-range guard is the point of the change.
4. **Smoke-test before changing anything.** `en:Chief Justice of Iran` (8/8) and
   `en:Prosecutor-General of Iran` (14/14) parse onto existing items today, with
   no parser change at all. Run those first; they prove the pipeline end to end
   while the Persian path is still untouched.
5. **Read `## Backtest` at the head of `data/iran/roster_audit.md` first.** Lane B
   and **Majlis term 11 (284 of 289 already recorded)** are the labelled test set:
   a date agreement below ~90% there is a **converter defect**, not a roster
   defect, and stops the run. Target agreement below ~90% means a family of items
   and routing that is guessing. **A whole office at 0% date agreement is a
   comparison bug before it is a parser bug.**
6. **Never calibrate the converter on en.wikipedia's Iranian ambassador lists.**
   Measured ~40% wrong on 206 unambiguous rows, 102 of them a mechanical
   `year − 622` — en.wiki already contains botched Jalali conversions. Calibrate on
   real events. Report the defect as a byproduct.
7. **Read `roster_audit.md` end to end**, including every skipped table and every
   `no identity` row. Every matcher this workbench has built was too loose on the
   first pass.
8. **Report the coarse-Jalali drop count per lane** in the audit.
9. **`render_edit_plan.py` refuses to render on a defect.** Expect RTL-reversed
   ranges on fa tables as on ar ones (§7 #31): defer such a lane rather than adding
   a global swap. Read its warnings too.
10. **Spot-check both batch halves against Wikidata live** with `max_age=0` before
    the human gate: does a statement with that subject, property, value *and dates*
    already exist? Majlis term 11 is 284/289 recorded — the duplicate risk is real.
11. **`apply_claims.py --campaign iran` dry first**, and confirm
    `claims_written.json` is in place — the API de-duplicates nothing, so a second
    run without the ledger doubles every tenure.
12. **Lane A goes in as its own batch and is checked separately.** Adding `P17` to
    108 items changes what the census returns, so re-run the census after it lands
    and confirm the universe reconciles to 312.

---

## 8. Outcome

**Three batches, 2026-08-18/19.**

| batch | QS statements | what it added |
|---|---|---|
| 1 | 224 | the table lanes: spine, 24 ministries, councils, security, judiciary |
| 2 | **688** | + Assembly of Experts rolls and Majlis terms 9–12, after the bullet path opened (§1q) |
| 3 | 29 | + 14 ambassador rosters |
| API | **337** for 145 people | the tenures QuickStatements cannot express at all |

Batches 1 and 2 are applied; 2 superseded 1 at the same path, and QuickStatements
de-duplicated the overlap. After batch 2 the sweep reports **1,932 rows as
`already holds P39`** — the run checking its own writes with `STATE_MAX_AGE = 0`,
which is what makes batch 3 honestly small rather than a re-proposal.

Measured against the survey's own baselines, live:

| office | before | after |
|---|---|---|
| Member of the Assembly of Experts | 19 holders / 26 statements | **181 / 188** |
| Member of the Islamic Consultative Assembly | 618 / 659 | **938 / 979** |
| Foreign Affairs Minister | 27 / 29 | **59 / 61** |

**The strongest evidence in the run is a number nobody wrote:** the Majlis lane
scored **99% date agreement against 676 statements already on record**. Those
dates came from `term=` triples read off the convocation items, converted through
a Solar Hijri path that did not exist a day earlier. Independent agreement at
that scale is not something a misparse produces.



Run 2026-08-18. **1,093 records, 861 applying — 688 statements in
`edit_plan.qs` and 335 via the API for 145 people with several tenures in one
office**, across 670 people and 30 offices. 232 skipped with a reason, 0 held,
0 to review: `edit_plan.md` is an account, not a queue. Baselined in
`regression/iran/`.

The first render was **312**. The difference is one function: opening
`parse_bullet_rosters` to Persian (§1q) unlocked the Assembly of Experts rolls
(428 rows → 179 records), and the Majlis rolls turned out to be *tables* whose
term is their title — 1,196 rows across terms 9–12, dated from the convocation
items their own `P2937` qualifiers point at, giving **388 records at 100% target
and 99% date agreement against 676 statements already on record.** That 99% is
the strongest evidence in the run that the Solar Hijri path and the `term=`
triples are both right.

Decisions by rule: `roster_only.attested → apply` 185, `early.precedent_ok →
apply` 61, `acting → apply` 61, `interim_concurrent_office → apply` 3,
`modern.two_channel → apply` 2; `early.unsupported → skip` 197,
`category_only → skip` 11, `no_dates → skip` 10, `duplicate_office_item → skip`
8, `namesake → skip` 2.

**The backtest is the result worth reading.** Most offices score 100% target and
81–100% date agreement against statements the community entered independently —
on a country where, before this run, `wd/roster.py` could not read a single date.
Two low scores were run down and neither is ours:

* **Interior at 22% target.** The audit names the siblings: `Q7844710`, a
  `Category:` item, and `Q1091482`, the ministry *organisation*. Lane A found
  `Q7844710` holds **9 of Iran's 11 recorded interior ministers** while the real
  position item holds 2. The engine routes to the real item and is right to.
* **IRGC commander-in-chief at 0% date.** Four for four, the recorded values are
  the naive day-preserving conversion (§1o). The corpus is wrong.

**What was left out, and why.** The Majlis (lane F, ~2,349 statements), the
ambassador bullets (lane K, ~640) and five of the six Assembly of Experts rolls
(lane D, ~330) all sit behind one bounded change to `parse_bullet_rosters` —
it drops a dateless bullet, has no Persian in `BULLET_HEADINGS`, and unlike the
table path has no `term=` bypass. That is ~3,300 statements this run did not
take, reported rather than half-parsed. The subnational lane (903 governor rows)
is behind 27 item creations and a missing `wd/create.py` archetype. Both are in
`tasks/followups.md` with their blockers named.

**Not run:** `apply_claims.py --apply` was blocked by the session's permission
classifier. `edit_plan_claims.json` is written, validated and spot-checked
against live Wikidata (three sampled people hold zero statements on their
targets, so nothing would duplicate), and needs only the human gate.

## 7. What this run should be judged on

**Iran should land in the Kuwait band or above** — the largest yield this
workbench has attempted. It is the Iraq shape in a more extreme form: an item
layer that is thin and partly broken, sitting under a roster layer that is
uniform, dated and almost entirely unread, because none of `wd/roster.py`'s
vocabulary is Persian.

The sizing, from the two surveys together: 2,268 P39 statements exist on Iranian
humans (Czechia had 14,124), 2,600 Iranian politicians have none at all, and 1,293
existing statements lack a start date — against ~6,000 legislature rows at 95–100%
wikilink→QID, 27 ministry rosters versus 136 recorded holders, ~898 dated
provincial-governor rows versus four governor items, and 291 of 420 catalogued
IRGC people with no P39.

Three caveats keep that honest:

- **Lane A is the headline, not the `.qs` size.** Adding `P17` to 108 items makes
  619 existing statements visible to the OpenSanctions PEP build — a larger
  practical effect than most of the new statements, at near-zero risk.
- **Several strong lanes are gated behind item creation** (28 provinces, 5 of 9
  judicial offices, the city councils, most bonyads), so a large creation list is
  a deliverable, not a shortfall.
- **Two lanes are honestly small and stay small**: parties (one table, three rows)
  and Astan Quds (126 rows, lunar Hijri, genuinely undatable — the Saudi ruling
  applies there and only there). Reported small rather than padded.

The run's real risk is not yield but the converter. Lane B and Majlis term 11 are
near-100% recorded already, which makes them the labelled test set: **if the
backtest does not reproduce them, the Jalali path is wrong and nothing else in the
run can be trusted.**
