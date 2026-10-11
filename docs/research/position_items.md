# Measured: how Wikidata models political position items

The evidence behind `old/recipes/position_items.md`. The recipe says what to do; this
says what was counted, over what sample, and what could not be counted. Kept
separate so the recipe stays readable and so any figure in it can be re-checked
rather than trusted.

**Measured 2026-08-19** against live WDQS and `wbgetentities`, through
`wd.http.make_session` + `wd.api.sparql` / `fetch_entities`. Type tests use
`p:P31/ps:P31` (statement nodes) where the question is "does this hold anywhere
among the values"; presence tests use `p:<prop> ?st`, so normal and deprecated
ranks count. Re-running any of it means re-running those helpers — the queries
below are described precisely enough to rebuild.

## 0. Read this first: the corpus is not what you think

**145,212 items carry `wdt:P31 = Q4164871`** (145,271 at statement level — 59
items hide the claim behind a non-preferred or deprecated rank). Roughly 90,000 of
them are bulk municipal imports:

| `P279` value | items |
|---|---:|
| `Q15113603` municipal councillor (France) | 40,268 |
| `Q382617` mayor of a place in France | 40,133 |
| `Q99762605` Romanian mayor | 3,148 |
| `Q17175157` German mayor | 1,646 |
| `Q55400987` French community councillor | 1,263 |
| `Q131101457` Philippine mayor | 1,180 |
| `Q19961107` / `Q19961106` Japanese city / town mayor | 791 / 746 |
| `Q83307` minister | **736** |
| `Q30185` mayor | **645** |

So **any percentage taken over "all position items" is a statement about French
communes.** Every cluster figure below is measured over `?i wdt:P279 <class>`,
which is what `country_sweep.md` §10 means by a well-curated cluster.

## 1. Property frequency

### Over the whole corpus (n = 145,212) — for reference only, see §0

| property | items | share |
|---|---:|---:|
| `P279` subclass of | 119,804 | 82.5% |
| `P1001` applies to jurisdiction | 110,985 | 76.4% |
| `P17` country | 90,428 | 62.3% |
| `P17` **and** `P1001` | 66,176 | 45.6% |
| `P1001` only | 44,809 | 30.9% |
| `P17` only | 24,252 | 16.7% |
| neither | 9,975 | 6.9% |
| `P2389` organization directed | 25,714 | 17.7% |
| `P361` part of | 16,797 | 11.6% |
| `P576` abolished | 12,623 | 8.7% |
| `P571` inception | 9,038 | 6.2% |
| `P1308` position holder | 7,257 | 5.0% |
| `P137` operator | 4,481 | 3.1% |
| `P1366` replaced by | 856 | 0.59% |
| `P1365` replaces | 846 | 0.58% |
| `P2388` office held by head of org | 29 | 0.02% |
| `P3831` object has role | **0** | **0.00%** |
| `en` label | 91,604 | 63.1% |
| `mul` label | 568 | 0.39% |
| `en` description | 39,340 | 27.1% |

The `P1001 > P17` inversion is entirely §0: French municipal items name a commune
in `P1001` and no country in `P17`.

**`P3831` is a non-property here.** Zero of 145,212 carry it as a main statement;
only 73 items site-wide do. Its real use is as a *qualifier* on `P1308` (50 items),
e.g. `Q107703906` marking an acting holder with `P3831 = Q4676846`, alongside
`P1545` series ordinal, `P5054` member of cabinet, `P580`/`P582`.

**`P2388` belongs on the organisation, not the office** — 29 of 145,212.

### Over curated archetype clusters — the numbers worth imitating

| cluster (`P279 =`) | n | `P17` | `P1001` | `P361` | `P2389` | `P571` | `P576` | `P1308` | `P1365`/`P1366` | `en` label | `en` desc |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `Q83307` minister | 5,211 | 81.6% | 94.4% | 92.6% | 32.9% | 8.5% | 4.7% | 6.8% | 2.4% / 2.9% | 97.3% | 93.0% |
| `Q48352` head of state | 346 | 86.4% | 82.1% | 16.5% | 22.8% | 44.5% | 16.8% | 47.1% | 13.3% / 11.3% | 96.2% | 77.2% |
| `Q2285706` head of government | 343 | 91.3% | 88.0% | 40.5% | 23.9% | 53.1% | 8.7% | 49.6% | 8.5% / 5.0% | 92.7% | 85.7% |
| `Q486839` member of parliament | 565 | 85.7% | 86.0% | 89.9% | 0.4% | 5.7% | 3.2% | – | 3.0% / 2.8% | 92.2% | 47.8% |
| `Q132050` governor | 589 | 65.7% | 84.4% | 13.4% | 4.6% | 15.1% | 3.9% | 13.2% | 1.5% / 2.0% | 91.8% | 52.8% |
| `Q30185` mayor | 1,193 | 97.4% | 92.9% | 48.2% | 4.4% | 21.1% | 6.6% | 18.1% | 3.0% / 3.8% | 95.5% | 56.4% |
| `Q117826617` supreme court judge | 59 | 83.1% | 89.8% | 55.9% | 8.5% | 6.8% | 0 | 5.1% | 1.7% / 0 | 100% | 76.3% |
| `Q29645880` ambassador of a country | 207 | 99.0% | 3.4% | 0.5% | 1.4% | 3.9% | 0 | 0 | 12.1% / 0 | 100% | 11.6% |
| `Q29645886` ambassador to a country | 264 | 99.2% | 16.7% | 0 | 20.5% | 9.8% | 0.4% | 12.1% | 6.4% / 0.4% | 99.6% | 7.2% |
| bilateral posts (`P279` to both an "…of X" and a "…to Y" class) | 5,206 | 93.0% | 29.6% | 1.2% | 74.9% | 7.1% | 0.06% | 19.1% | 1.9% / 0.1% | – | – |

`P279` is 100% by construction in every row. `mul` labels are effectively unused:
24 of 5,211 ministers, 10 of 4,452 public-office subclasses, 3 of 346 head-of-state
classes.

**`Q4164871`'s own `P1963` "properties for this type"** — the community's answer to
which properties belong on a position item — is `P1308`, `P2098`, `P2389`, `P571`,
`P17`.

## 2. `P31` is a metaclass, and `Q4164871` is not the modal one

| specific class C | items `P31 → C` | of those also `P31 = Q4164871` | items `P279 → C` **and** `P31 = Q4164871` |
|---|---:|---:|---:|
| `Q83307` minister | 178 | 8 | 739 |
| `Q30185` mayor | **4,279** | 11 | 645 |
| `Q48352` head of state | 32 | 5 | 148 |
| `Q2285706` head of government | 48 | 23 | 126 |
| `Q486839` member of parliament | 18 | 5 | 458 |
| `Q132050` governor | 50 | 13 | 270 |
| `Q16533` judge | 23 | 9 | 200 |
| `Q117826617` supreme court judge | 1 | 0 | 47 |
| `Q294414` public office | **25,917** | 660 | 80 |

**The load-bearing measurement.** Of the 5,211 items with `P279 = Q83307`, the
`P31` breakdown is `Q294414` public office **4,428 (85.0%)**, `Q4164871` position
738 (14.2%), no `P31` at all 74 (1.4%), other 22 plus a long tail. Across the seven
political archetypes, `P31 = Q294414` beats `P31 = Q4164871` **5,509 : 2,409**.

Metaclasses in live use as a position item's `P31`: `Q294414` public office,
`Q4164871` position, `Q17279032` elective office (what `Q11696` POTUS uses),
`Q114962596` historical position, `Q83856136` legal position, `Q136649946` type of
position, `Q355567` noble title, `Q42045197`.

`P31` straight to the specific class happens at scale in exactly one place: the
4,279 items with `P31 = Q30185` (Brazilian mayoralties — `P279` = public office +
elective office, `P1001` = the municipality). **Only 74 of those 4,279 have any P39
holder**: minted and never populated.

**Reality check against consumers.** 147,584 distinct items are the target of some
`wdt:P39`. Of them 110,613 (74.9%) carry truthy `P31 = Q4164871`; **17,788 (12.1%)
carry `Q294414` instead**; 780 `Q17279032`; 74 `Q30185`. A closure demanding a
literal `P31 = Q4164871` therefore misses ~17,800 offices people actually hold.

## 3. The boundary: position vs occupation vs profession vs rank

Wikidata declares this at the class layer rather than leaving it implicit:

- **`Q4164871` position** — `P279 = Q214339` role; `P361 = job activity`;
  **`P1889 different from` → `Q480319` title of authority, `Q12737077` occupation,
  `Q28640` profession, `Q11348` function, `Q192581` job activity**.
- **`Q12737077` occupation** — `P279 = Q1807498` social position; `P1889 different
  from Q4164871`; and tagged `P1552 = Q122754124` ambiguous Wikidata item.
- **`Q28640` profession** — `P31 = metaclass`; `P279 = Q12737077`. So profession ⊂
  occupation, and occupation is disjoint-by-declaration from position.
- **`Q4189293` rank** — `P279 = Q4120621` rank, **`Q4164871` position**, `Q82799`
  name. **`Q56019` military rank** — `P279 = Q4189293`; `P1889 different from
  Q16631188` military position; `P1963 = P1611` NATO code, `P241`, `P8766` insignia,
  `P3729`/`P3730`. **`Q16631188` military position** — `P279 = Q4164871 +
  Q12737077`.

Counts: `P31 = Q12737077` 6,353 items; `Q28640` 10,117; `Q56019` 1,861; `Q4189293`
138. Overlap with `P31 = Q4164871`: occupation 486, profession 780, **military rank
142 (7.6% of ranks)**, military position 25.

**Because `Q4189293` rank lists `Q4164871` among its `P279`, ranks reach "position"
in any closure walk.** The discriminator is not the closure — it is the absence of
jurisdictional and holder furniture, and the presence of rank-specific properties.

### Exemplars of the boundary

| item | `P31` | `P279` |
|---|---|---|
| `Q16533` judge | legal profession (`Q15987302`); legal position (`Q83856136`); ISCO-08 group; embede | jurist (`Q185351`) |
| `Q82955` politician | profession (`Q28640`) | professional (`Q702269`) |
| `Q40348` lawyer | legal profession; ISCO-08 group; academic degree | jurist; legal profession |
| `Q189290` military officer | military profession (`Q6857706`) | military personnel; officer |
| `Q83460` general | **military rank (`Q56019`)** | military officer; four-star rank |
| `Q565077` flotilla admiral | **naval officer rank (`Q4226220`)** | flag officer (`Q977459`) |
| `Q23011774` flotilla admiral (Belgian Navy) | **military rank (`Q56019`)** | Général (`Q582170`) |
| `Q843020` justice of the Supreme Court of Canada | legal position + **occupation** | supreme court judge; national supreme court judge |
| `Q11147` Chief Justice of the United States | **public office + occupation** | chief justice (`Q3188089`); US Supreme Court justice |

Two rules fall out:

- **A rank is not an office.** `Q565077` carries `P1611` NATO OF-6,
  `P3729`/`P3730`, `P8766` insignia, no `P1308`/`P2389`/`P1001` — and **eight `P17`
  values** (FI, BE, BG, SE, DE, DK, LV, LT), because `P17` on a rank means "used by
  these countries". Never read `P17` uniformly.
- **"Judge" in the abstract is an occupation; a named judgeship on a named court is
  a position.** `Q16533` carries ISCO/SOC/ESCO/ANZSCO codes and gendered labels;
  `Q843020` carries `P17`, `P1001`, `P361`, `P571`. The community is comfortable
  double-typing an apex judgeship as position *and* occupation.

## 4. Jurisdiction: `P17` vs `P1001`

Measured as "is `P1001` the same item as `P17`?" over items carrying both:

| cluster | `P1001` = `P17` | `P1001` ≠ `P17` |
|---|---:|---:|
| `Q83307` minister | **3,760 (91.8%)** | 338 |
| `Q486839` member of parliament | 274 (60.8%) | 177 |
| `Q48352` head of state | 176 (64.9%) | 95 |
| `Q2285706` head of government | 116 (39.9%) | 175 |
| `Q117826617` supreme court judge | 16 (35.6%) | 29 |
| **`Q30185` mayor** | 31 (2.8%) | **1,070 (97.2%)** |
| **`Q132050` governor** | 23 (6.9%) | **312 (93.1%)** |
| subclasses of `Q294414` (mostly BR mayoralties) | 24 (0.6%) | 4,299 (99.4%) |

What the `P1001` target *is*: mayors — subnational 1,079 vs a country 31 (97.2%);
governors — 480 vs 18 (96.4%).

- **National office: both, both naming the country.** 91.8% of ministerial items
  carrying both duplicate it.
- **Sub-national: `P17` = the state, `P1001` = the polity governed.** 93–97%.
- The head-of-government and apex-judgeship clusters split because they contain
  sub-national and supranational offices (state premiers, US state supreme courts).

## 5. Diplomatic posts

Measured over **5,206 actual bilateral post items**, comparing each item's own
claims against the receiver of its "ambassador to Y" parent and the sender of its
"ambassador of X" parent:

| | present | resolvable | finding |
|---|---:|---:|---|
| `P17` | 4,844 (93.0%) | 4,958 | **receiver 4,286 (86.4%)**, sender 615 (12.4%), other 57 |
| `P137` | 4,078 (78.3%) | 4,053 | **sender 3,884 (95.8%)**, receiver 3, other 166 |
| `P1001` | 1,539 (29.6%) | — | receiver 1,371 (86.5%), sender 131 (8.3%) |
| `P2389` = the embassy | 3,901 (74.9%) | — | |
| `P461` opposite of = the reciprocal post | 437 (8.4%) | — | |

So `P17` receiver, `P137` sender, `P2389` embassy, and **do not assert `P1001`** —
sender-in-`P1001` is a 2.5% minority.

**The trap that inverts the answer.** The two class layers behave oppositely: among
the 207 `Q29645880` "ambassador of a country" subclasses (one per sender) `P17` is
the **sender** (205/207); among the 264 `Q29645886` "ambassador to a country"
subclasses (one per receiver) it is the **receiver** (262/264). A quoted "262/264"
is about the receiver layer only.

## 6. Succession and renamed offices

Practice is **one item per name or era, chained with `P1365`/`P1366` and bounded
with `P571`/`P576`** — not one item with dated qualifiers. The chain properties are
rare globally (0.58% / 0.59%) but concentrated where renames happen: ministers
2.4% / 2.9%, heads of state 13.3% / 11.3%.

Model chain — the Azerbaijani education portfolio. Every item: `P31 = Q294414`,
`P279 = Q83307`, `P17 = Q227`, `P361 = Q13410372` Cabinet of Azerbaijan,
`P2354 = Q4294936` (the same roster article for all five), its own `P571`/`P576`,
`P748` appointed by = President of Azerbaijan, and `P1308` holders with `P1545`
ordinals and `P5054` member-of-cabinet:

```
Q115518883  Minister of People's Education of the Azerbaijan SSR
  └P1366→ Q115518392  …of the Republic of Azerbaijan   P571 1991-02-05  P576 1993-04-28
            ├P1366→ Q115518180  Minister of Enlightenment              P571 1993-04-28  P576 1993-09-02
            └P1366→ Q115517960  Minister of Higher and Secondary Ed.   P571 1993-04-28  P576 1993-09-02
                      both └P1366→ Q107703906  Minister of Education   P571 1993-09-02  P576 2022-07-28
                                     (P1365 lists BOTH predecessors)
                                     └P1366→ Q115100960  Minister of Science and Education  P571 2022-07-28 (open)
```

What makes it read as one office over time: `P571`/`P576` exact and adjacent — one
item's `P576` is the next one's `P571`; splits and merges as multi-valued
`P1365`/`P1366`; a shared `P2354`.

**Minority idiom:** one item with dated `P1448` official names — `Q6865764`
"Minister for Communications" (Ireland) carries three dated `P1448` values across
1922–1991 *as well as* `P1365`/`P1366` and `P571`/`P576`. Useful for label
matching; it does not replace the chain, and the same names also exist as items.

## 7. Parent conventions for specific office classes

Measured in-session over CirrusSearch clusters (`haswbstatement:P31=Q4164871
<term>`), reading `P279` off each hit. Cheap and reliable where a WDQS label scan
504s.

| office class | items | typed | convention |
|---|---:|---:|---|
| parliamentary speakership | 150 | 96 | **`Q1758037` speaker — 84 (87.5%)**; `Q140686` chairperson 3 |
| "chief justice" | 111 | 96 | **`Q3188089` chief justice — 88 (91.7%)**; `Q55736868` 3 |
| "President of the Supreme Court" | 19 | 12 | **split — `Q117826617` 4, `Q13554447` chief judge 4, `Q16474031` court president 3** |

Candidate parents, counted as `?p wdt:P31 wd:Q4164871 ; wdt:P279 <class>` — all in
live use, so all are real conventions rather than inventions:

| parent | position items using it |
|---|---:|
| `Q83307` minister | 736 |
| `Q132050` governor | 269 |
| `Q16533` judge | 199 |
| `Q486839` member of parliament | 454 |
| `Q1553195` party leader | 146 |
| `Q117826617` supreme court judge | 43 |
| `Q108290289` senior government official | 41 |
| `Q107363151` central bank governor | 33 |
| `Q707492` chief of staff | 24 |
| `Q3368517` public prosecutor general | 22 |
| `Q55736868` national supreme court judge | 7 |
| `Q109607046` deputy prosecutor general | 1 |

## 8. Exemplars worth reading in full

**`Q21503673` Minister of Foreign Affairs of Romania** — the shape a roster
campaign should aim at. Everything jurisdictional in six statements, the roster
linked by `P2354`, and the whole succession as **125 dated `P1308` values** back to
1862:

```
P31 = position (Q4164871) · P279 = foreign minister (Q7330070)
P17 = Romania · P1001 = Romania · P361 = Government of Romania
P2389 = Ministry of Foreign Affairs of Romania
P2354 = list of Ministers of Foreign Affairs of Romania
P910 = Category:… · P373 Commons · P2521 female form of label
P1308 × 125, each {start time; end time}
```

**`Q11696` President of the United States** — the maximal head-of-state shape.
`P31 = Q17279032` elective office (not `Q4164871`); four `P279` parents (head of
state, head of government, commander-in-chief, president); `P2098` deputy = VP;
`P2097` term length 4 with a dated `{maximum 2, from 1951-02-27, subject of 22nd
Amendment}` override beside a historical value; `P748` appointed by = Electoral
College; `P263` official residence with three dated historical ones; `P2715`
elected in; `P3618` base salary; 82 external-id statements.

**`Q843020` justice of the Supreme Court of Canada** — an apex judgeship, and
legitimate position/occupation double-typing: `P31 = Q83856136` legal position +
`Q12737077` occupation; `P279 = Q117826617 + Q55736868`; `P17`, `P1001`,
`P361 = Supreme Court of Canada`, `P571 = 1875-09-30`, `P1754` category related to
list. Compare `Q11144` Associate Justice SCOTUS (`P2097 = novalue {subject of =
life tenure}`) and `Q11147` Chief Justice (`P1269 facet of`, `P937` work location).
**None of the three uses `P31 = Q4164871`.**

**`Q326552` United States Ambassador to Germany** — the bilateral shape:
`P31 = Q4164871`; `P279 = Q15726790` ambassador of the US **and** `Q28796675`
ambassador to Germany; `P17 = Germany` (receiver); `P137 = United States` (sender);
`P2389 = Embassy of the United States, Berlin`; no `P1001`.

## 8b. The consumer-named cohort (measured 2026-08-23)

The 209 position items `opensanctions`' `wd_categories.yml` names by QID, scored
with `wd/shape.py` by `old/scripts/audit_os_positions.py`. A different sample from
everything above — it is a *consumer's* list, so it is worldwide, skewed towards
the offices somebody needed and away from the ones Wikidata happens to document
well. 194 of 209 are well modelled; 79 are complete.

**Sub-national legislator seats and `P17`.** `P279 = Q4175034` legislator, grouped
by the country of the polity the seat's `P1001` names:

| polity's country | seats | carrying `P17` |
|---|---:|---:|
| Russia | 66 | **2** |
| Nigeria | 36 | 36 |
| Italy | 13 | 13 |
| Malaysia | 12 | 12 |
| United States | 12 | 10 |
| Argentina | 8 | 8 |
| United Kingdom | 7 | 6 |
| all others in the top 15 | 26 | 21 |

103 of 114 (90%) outside Russia, against 2 of 66 inside it. Over the whole
`Q4175034` cluster the figure is a misleading 182 of 306 (59%), because Russia's
bulk-created `Q1332683xx` series is a fifth of it. **The lesson is the one
`wd/precedent.py` exists for**: the same office class answers differently per
country, and a corpus-wide percentage here is a statement about one bulk import —
the same trap as §0's French communes, one property along.

**Parent classes for an office that names no kind.** `P279` tallies over the
sibling cluster named in each row; CirrusSearch `haswbstatement:P31=Q4164871
inlabel:"<phrase>"`, capped at 200 hits, relevance-ranked:

| cluster | winner | count |
|---|---|---|
| `"secretary general"` (186) | `Q6501749` general secretary | 60 |
| `"chairperson of the"` (84) | `Q140686` chairperson | 32 |
| `"mayor of"` (200) | `Q30185` mayor | 64 (behind `Q382617` at 92 — corpus bias) |
| `"chief of staff"` (200) | *none* | 8 / 5 / 4 across three rivals |
| `"president of the court"` (11) | *none* | 1 / 1 / 1 / 1 |

**A court presidency is measured structurally, and the sibling channel overrules
the tally.** `P279` over offices whose `P2389`/`P361` names a court (`Q41487`
closure) leads with `Q58412318` US district judge 88, `Q3188089` chief justice 73,
`Q16533` judge 64, `Q16474031` court president 29 — none of which is the answer.
The two *international* court presidencies that carry any `P279` both subclass
**their own court's judgeship**: `Q19926443` President of the ICJ takes
`Q30771010` Judge of the ICJ, `Q94692068` President of the ECtHR takes `Q64682634`
Judge of the ECtHR. So does the ICC's, on `Q965043`. A label tally would have
picked `Q3188089`, which is a national supreme-court role and not this.

A "president of an organisation" cluster cannot be measured by label at all —
`inlabel:"president of the"` is dominated by state presidencies (`Q248577` 21,
`Q48352` 12) and speakerships (`Q1758037` 35). The structural cluster answers it:
positions whose `P2389` names an item that is a `Q484652` international
organization, tallied on `P279` —

| `P279` | positions |
|---|---:|
| `Q6501749` general secretary | 19 |
| `Q140686` chairperson | 12 |
| `Q1255921` president (leader of an organization) | 10 |
| `Q1501800` director general | 8 |

which is not one winner but **one winner per title word**, and that is the
convention: the class follows what the office is called.

**zavod's IGO registry is not the gap it looked like.** All 24 of the cohort's
international posts already carry a `P2389`/`P361` into an `INTL_ORGS` org, so
none of them is dropped for want of a link. What stops 101 of the 209 is instead
`SUB_TYPES`: `Q4175034` legislator confers `gov.legislative` and no `role.pep` (79
items), and `Q5230427` member of a legislative assembly (12) and `Q42178` vice
president (5) are absent from it. That is a consumer's topic table, not a
modelling defect, and it is recorded here so no future run reads those 101 items
as broken.

## 9. What failed, and what to distrust

Recorded rather than estimated:

- `SELECT ?t (COUNT(DISTINCT ?pos)) WHERE { ?h wdt:P39 ?pos . ?pos p:P31/ps:P31 ?t }
  GROUP BY ?t` — never returned (>15 min, 4 attempts). The §2 "reality check"
  figures come from four single-type counts instead, which did run.
- `SELECT (COUNT(DISTINCT ?i)) WHERE { ?i p:P279/ps:P279 wd:Q83307 . FILTER NOT
  EXISTS { ?i p:P31/ps:P31 wd:Q4164871 } }` — repeated 503s. Derived by
  subtraction (5,211 − 739).

Added 2026-08-23, from the `wd_categories.yml` cohort (§8b):

- `?org wdt:P31/wdt:P279* wd:Q1156854` for "an international court" and
  `wd:Q7188` for "a presidential administration" both returned confidently and
  **wrongly** — the first answered with ambassadorships and Arabic letters, the
  second with 1,654 Dutch municipal councillors. Neither QID means what the query
  assumed. A structural cluster is only worth more than a label tally once the
  anchor class has been read; an implausible result is the cheap tell, and a
  *plausible* wrong one would not have been caught.
- The `P31` shape of the minister cluster, which no gap measures: 4,430 of 5,215
  carry `Q294414` public office, 740 carry `Q4164871`, and **only 78 carry both**.
  The community swaps the metaclass rather than stacking it, which is what makes
  `Q4164871 → Q294414` a removal and not an addition.

Two standing cautions:

- **WDQS will not take a label regex over all positions.** `FILTER(CONTAINS(
  LCASE(?l), …))` across `Q4164871` answers with a 504. Use CirrusSearch
  (`haswbstatement:P31=Q4164871 <term>`), and search **words** — `lithuan` is not a
  word and matches nothing, which silently cost an audit its four highest-value
  items on one run.
- **Holder-derived priors are corpus-biased** (`country_sweep.md` §10 rule 5).
  Nothing above rests on them, deliberately.

## 10. Party organs, collegial state organs and other mint archetypes (measured 2026-10-01)

Measured for the peploop mint stage (Cuba first). The question each cluster
answers is "what `P31`, `P279` and body property does an item of this kind carry
today", so that a minted item has a sibling and not an invention. Live reads
(`max_age=0` for everything Cuban); clusters are CirrusSearch
`haswbstatement:P31=<mc> inlabel:"<phrase>"` over the six metaclasses in §2
(`Q4164871`, `Q294414`, `Q17279032`, `Q114962596`, `Q83856136`, `Q136649946`), in
several languages, then hand-filtered to the kind. `P31`/`P279` are read off
claims (all ranks), not `wdt:`. **Samples are small.** Most of these kinds are
barely modelled, and an n of 5 is a hint, not a convention.

### 10a. Party organ seats

| cluster | n | `P31` | `P279` | body |
|---|---:|---|---|---|
| member of a Politburo (CPSU, CPSU candidate, CCP, CCP PSC, WPK, WPK Presidium) | 6 | `Q4164871` 5, `Q114962596` 1 | `Q115136557` Politburo member 3; `Q115168134` member of the CC of the CPSU 2; `Q20046316`, `Q618536`, `Q120800191`, `Q46403368`, `Q30945753` 1 each | `P361` organ 3/6 |
| member of a Central Committee (RO, RO alternate, HU, CPSU, CCP, CCP alternate, Fatah, PCF, MES, CP Byelorussia) | 10 | `Q4164871` 9, `Q114962596` 1 | **none 7**; `Q8191099` member 2; `Q115252544` CPSU member 1 | `P361` the CC 8/10 |

No Politburo-membership item exists for Vietnam, Laos or Cuba. `Q61127295`
"Permanent Member of the Secretariat" (Vietnam) exists with **no claims at all**.

**The modelling is itself split: P39 on a membership seat vs P463 on the body.**
Counted with `p:P39/ps:P39` and `p:P463/ps:P463`, distinct holders:

| organ | P463 → body | P39 → body | P39 → membership seat |
|---|---:|---:|---:|
| Politburo of the CPSU `Q842008` | 106 | 0 | 89 (`Q108495011`) |
| Central Committee of the CPSU `Q1971373` | **933** | 0 | **2** (`Q115168134`) |
| Politburo of the CCP `Q1076970` | 4 | 0 | 75 (`Q20046316`) |
| PSC of the CCP `Q197542` | 5 | 0 | 62 (`Q42327067`) |
| Central Committee of the CCP `Q50963` | 0 | 0 | 12 (`Q60988843`) |
| Politburo of the CPV `Q7210126` | 0 | 0 | — |

The Soviet Central Committee is a P463 convention; the Chinese Politburo is a P39
one. Vietnamese leaders (`Q10831196` Tô Lâm, `Q318458`, `Q10806940`) carry
neither. One Cuban (`Q44008911` Roberto Morales Ojeda) holds `P39 = Q1516390`
Council of State of Cuba, which is the body itself.

### 10b. Collegial state organ seats

Executive or standing collegial organs only. Legislative "Council of State"
chambers (Oman, Sudan, Libya, the Russian republics' State Councils) are
`Q486839`/`Q4175034` seats and are excluded, as is the Swiss Federal Council
(`Q83307`).

| n | `P31` | `P279` | body |
|---:|---|---|---|
| 13 | `Q4164871` 10, `Q294414` 2, `Q114962596` 1 | `Q16862850` Member of State Council **4** (LU, NL, GDR, Russian Empire); `Q41961533` member of the Presidium of the Supreme Soviet 2; none 2 (ES `Q106223649`, MZ `Q111893540`); one each of `Q41961562`, `Q8191099`, `Q120800191`, `Q17279032`, and three defects | `P361` the organ 8/13; `P2389` 0 |

The three defects are worth naming because each one is a trap a minting run
could copy: `Q94994178` (Monaco) subclasses `Q1216422` "State councillor", which
is a **disambiguation page**. `Q84704434` (NK SAC) subclasses `Q25263528` State
Affairs Commission, and `Q98796960` subclasses `Q11515680` Standing Committee of
the SPA. Both of those parents are the **bodies**.

### 10c. Party secretaries (national level)

| cluster | n | `P279` | body |
|---|---:|---|---|
| leader: first/general secretary of a national ruling communist party | 17 | `Q6501749` general secretary 8, `Q1553195` party leader 7, `Q48352` head of state 6, none 5, `Q62003554` 2 | `P2389` the party 10/17; `P361` 3/17 |
| deputy/secretariat seat: Second Sec. CP Azerbaijan `Q136228845`, Secretary CPSU `Q115147301`, Secretary CC CP Az. `Q124313750`, Secretary CCP Secretariat `Q46404263`, CPV Permanent Member `Q61127295` | 5 | `Q836971` party secretary 3 of 4 typed; `Q138784034` 1 (stacked); `Q46403368` 1 | `P361` the Secretariat/CC 3/5 |

`inlabel:"Second Secretary"` returns parliamentary bureau seats and diplomatic
ranks. The only national party second secretaryship on Wikidata is
`Q136228845` (Azerbaijan SSR), which stacks `Q836971` **and** `Q138784034`.

### 10d. Armed-forces chief of staff

The national armed-forces chief only. Service chiefs (army, navy, air), logistics,
intelligence, procurement, presidential military staffs and commanders-in-chief
are excluded.

| n | `P31` | `P279` | body |
|---:|---|---|---|
| 93 | `Q4164871` 92, `Q294414` 2, `Q56019` 2 | **`Q5097014` chief of defence 28 of 40 typed (70%)**; `Q707492` Chief of Staff 7; `Q189290` 2; one each of `Q2257775`, `Q380782`, `Q83460`, `Q11247470`; none 53 | `P2389` 27/93, naming the general staff (RU, BY, UA, PT, HU, IR, AL) or the armed forces (IL); `P361` 8/93 |

`Q5097014` is itself `P279 Q707492`, so the two answers agree. `P17` 53/93, and
`P1001` 42/93.

### 10e. Apex court president

National supreme, cassation and constitutional courts. Sub-national, electoral,
audit and colonial courts are excluded.

| cluster | n | `P31` | `P279` | body |
|---|---:|---|---|---|
| all apex presidencies | 46 | `Q4164871` 31, `Q294414` 21 (both on 6) | `Q3188089` chief justice 15, none 10, `Q13554447` 6, `Q16474031` court president 5, `Q117826617` 4, `Q16533` 3, `Q1255921` 2 | **`P2389` the court 40/46**; `P361` 13/46 |
| supreme / cassation only | 32 | `Q4164871` 21, `Q294414` 14 | **`Q3188089` 13 of 26 typed (50%)**; `Q13554447` 5; `Q117826617` 3; `Q16533` 3; `Q16474031` 2 | |

This is wider than §7's English-label cluster of 12, and it moves the answer from
"split three ways" to "plurality `Q3188089`". The Latin American presidencies all
take it: CL `Q6634829`, PE `Q6024100`, MX `Q6085566`, HN `Q116908996` and GT
`Q6085575`. `Q3188089` is `P279 Q16474031` court president, so it subsumes the
rival label. Six items stack a second parent, **their own court's judgeship** (US,
SE, GT, SV, FI, KR), which is §8b's international-court pattern again. Two
cautions:
- `Q13554447` "chief judge" is described "highest-ranking judge of a court in US"
  and carries `P17 = Q30`. The five non-US items using it (RU, FI, UK, SA, CZ)
  have picked a US-scoped class.
- Constitutional-court presidencies lean `Q16474031` (IT, ES, TN).

### 10f. Head of a state-owned enterprise

Structural: positions whose `P2389` names an item typed `Q270791` / `Q4481739` /
`Q10876322` / `Q48851989` / `Q15811601` / `Q4830453` / `Q783794` / `Q6881511` /
`Q891723` / `Q1589009` / `Q167037` / `Q219577`. That gives 103 positions, 13 of
them central-bank governors, leaving **90**.

| `P31` (n=103) | `P279` (n=90, ex-central-bank) |
|---|---|
| `Q4164871` 84, `Q294414` 20 | none 35; `Q140686` chairperson 10; `Q484876` CEO 9; `Q1501800` director general 8; `Q2534525` chairperson of the executive board 7; `Q428322` PDG 3; `Q1255921` president (of an org) 2; **`Q30461` president 2**; `Q2660648` sōsai 2; `Q1162163` director 1 |

`P361` 13/103. There is no winner, and the class follows the title word, as §8b
found for IGO heads: "CEO" → `Q484876`, "director general" → `Q1501800`,
"chair(man)" / "styrelseordförande" → `Q140686` / `Q2534525`. **`Q30461` is
"leader of a country or part of a country" (`P279 Q48352` head of state)**, and
`Q138139721` President of SOCAR and `Q139927564` Presidente de ANTEL both took it.
An SOE "presidente" is `Q1255921`, "leader of an organization".

### 10g. Governor of a first-level subdivision

Labels "Gobernador de/del", "Governor of … province/region/state", "Provincial
Governor". Vice, lieutenant, colonial and central-bank governors are excluded.
n = **661**.

- `P31`: `Q294414` 355, `Q4164871` 268, `Q17279032` 113, `Q114962596` 28.
- `P279`: **`Q132050` 218** direct. The next largest are national governor
  classes that themselves subclass `Q132050`: PH 50, NG 38, MX 32, BR 25, AR 23,
  AO 13, KR 12. Then `Q2285706` 95 and `Q48352` 61, which are stacked parents.
- `P1001` 605/661, `P17` 590/661, `P361` 185/661 (28%).

`Q132050` is confirmed. It is `P279 Q1097498` ruler, `P31` public office +
position, and its `P1889` separates it from `Q889821` (US state governor).

### 10h. Parents, read in full

| QID | en label | en description | read |
|---|---|---|---|
| `Q115136557` | Politburo member | — | `P31 Q4164871`, `P279 Q8191099`, `P361 Q309118` politburo; 0 sitelinks, 3 subclasses |
| `Q8191099` | member | individual or organization with membership in a group; constitutive components of a corporate body | 155 subclasses, mostly academies and honours (Freemason, EMBO); generic |
| `Q16862850` | Member of State Council | — | `P31 Q4164871`, `P279 Q294414`; 0 sitelinks, 4 subclasses |
| `Q41961562` | member of the supreme collegiate body of executive power | — | `P279 Q1097498` ruler, `P361 Q22950320` collective head of state |
| `Q836971` | party secretary | senior official within a political party with responsibility for the organizational and daily political work | `P279` politician, party official, secretary; `P1889 Q140716837` regional party secretary |
| `Q138784034` | second secretary | — | `P279` four secretary/undersecretary classes; its 13 subclasses are mostly embassy ranks and parliamentary bureau seats |
| `Q62003554` | First Secretary | In communist party, head of a territorial committee (local or regional) | the description says sub-national, and two national items use it anyway |
| `Q5097014` | chief of defence | highest ranked commissioned officer of a nation's armed forces | `P31 Q16631188` military position, `P279 Q707492` |
| `Q3188089` | chief justice | presiding member of a supreme court | `P279 Q55736868`, `Q16474031`, `Q25713832`; `P361 Q190752` |
| `Q16474031` | court president | chief of a court of justice | `P279` leader of org, judge, chairperson |
| `Q13554447` | chief judge | highest-ranking judge of a court in US | `P17`/`P1001 = Q30`; **US-scoped** |
| `Q1255921` | president | leader of an organization | `P1889 Q30461` |
| `Q30461` | president | leader of a country or part of a country, usually in republics | `P279 Q48352`; **not for an SOE** |
| `Q484876` | chief executive officer | highest-ranking officer of an organization | corporate title |
| `Q1501800` | director general | title given to the highest executive officer in some organizations | |
| `Q132050` | governor | high ranked governing official in a state | `P279 Q1097498` |
| `Q46403368` / `Q30945753` | deputy / chief at the national level | civil service rank in China | ranks, not parents for any other state |
| `Q115252544` | CPSU member | — | party **membership** (`P279 Q11388835`); `Q115168134` CC member inherits it, which conflates the seat with membership |
| `Q1216422` | State councillor | Wikimedia disambiguation page | not a class |

### 10i. Cuba's own offices (Q241)

Population: positions with `P17` or `P1001` = `Q241` at statement level (89
items), plus positions whose `P1001` is a Cuban place. Inbound ambassadorships, the
nuncio and bishoprics are removed. **n = 53**, of which 10 are pre-1959
`secretario de …` cabinet secretaries (`P279 Q135496778`).

| property | tally |
|---|---|
| `P31` | **`Q294414` 30**, `Q4164871` 23 |
| `P279` | `Q83307` minister 23; `Q135496778` cabinet secretary 10; none 3 (`Q5453781` UJC first secretary, `Q89188209`, `Q132672793`); `Q132050` 2; `Q30185` 2; one each of `Q7330070`, `Q248577`, `Q1758037`, `Q486839`, `Q11812509`, `Q42178`, `Q4018482`, `Q1553195`, `Q48352`, `Q14212`, `Q2518691`, `Q1255921`, `Q107363151`, `Q203184` |
| `P361` | **`Q834304` Council of Ministers 32**; none 16; `Q1516390` Council of State 3; one each NA, CC of the PCC, Ayuntamiento, Provincial Assembly |
| `P17` | **none 31**, `Q241` 22. The `Q114433xxx` ministry batch carries `P1001` only |
| `P1001` | `Q241` 45, Havana 3, `Q12588` 1, none 4 |

The modern state (the `Q114433xxx`/`Q114436xxx` series, ~30 items) is uniformly
`Q294414` + `Q83307` + `P1001 Q241` + `P361 Q834304` + `P2389` its ministry. The
older, high-traffic items (President, PM, MINREX, the assembly seat, First
Secretary) are `Q4164871`. A sibling-derived metaclass for Cuba is `Q294414`.

Exemplars, read in full:
- **`Q113662078` Governor of La Habana Province**: `P31 Q294414`, `P279 Q132050`,
  `P1001 Q12588`, `P1365 Q132672896`. No `P17`, `P361`, holders or sitelinks.
  `Q12588` "Havana Province" is the current province: it is in `Q241`'s `P150`,
  with no `P576`. Its predecessor `Q132672896` (Provincial Assembly president,
  1959–2020-01) is `P279 Q30185` mayor, `P1366 Q113662078`.
- **`Q1370482` President of Cuba**: `P31 Q4164871`, `P279 Q248577`, `P17`/`P1001
  Q241`, `P361 Q1516390` + `Q834304`, `P2389 Q834304`, `P748 Q720753`, `P2098
  Q21071159`, `P263`, 8 `P1308`. The aliases carry "Presidente del Consejo de
  Estado", which is the origin of the `Q89188209` twin (ruwiki only, `Q294414`,
  `P361 Q1516390`, no `P279`).
- **`Q6502015` Prime Minister**: `Q4164871`, `P279 Q14212`, `P17`/`P1001`,
  `P361 Q834304`, `P748 Q720753`, `P2354`, 4 `P1308`.
- **`Q21272829` diputado de la ANPP**: no `en` label. `Q4164871`, `P279 Q486839`,
  `P17`/`P1001`, `P361 Q720753`. Holds 46 Cuban P39s, the most of any item.
- **`Q7644899` People's Supreme Court**: the **body**, `P31 Q190752` supreme
  court, `P17`/`P1001`. No presidency item exists.
- **`Q114436623` President of the Central Bank**: `Q294414`, `P279 Q107363151`,
  `P17`, `P2389 Q2607787`, `P361 Q834304`. No `P1001`.

Body items:

| body | QID | state |
|---|---|---|
| Communist Party of Cuba | `Q371402` | `P31 Q233591` |
| Politburo of the PCC (standing) | **missing** | only per-term items: `Q106764104` 1st … `Q106808574` 8th (2021), each `P17` alone |
| Central Committee | `Q30914590` | `P31 Q43229`, `P361 Q371402`; per-term `Q61129184` 1st … `Q106649332` 8th |
| Secretariat of the CC | `Q29075190` | **no claims**; per-term `Q106839095` 1st … `Q106808350` 8th |
| Council of State | `Q1516390` | `P31 Q11204` legislature, `P749 Q720753`, `P527` President + VP; `Q56063251` 8th Council of State has no claims |
| Council of Ministers | `Q834304` | `P31 Q35798`, `P279 Q640506` |
| People's Supreme Court | `Q7644899` | `P31 Q190752` |
| Revolutionary Armed Forces (FAR) | `Q663472` | `P31 Q772547` |
| Ministry of the FAR | `Q56274945` | ministry of Cuba |
| FAR General Staff (EMG) | **missing** | |
| MININT | `Q3858481` | ministry of Cuba |
| Fiscalía General de la República | **missing** | |
| Contraloría General | `Q25408126` | no `P31` |
| Central Bank | `Q2607787` | |
| GAESA | `Q113204847` | `P31 Q17326725`, `P361 Q663472`; `P1037` still the late López-Calleja |
| CIMEX | `Q113134286` | company |
| Gaviota | `Q18624414` | **no claims** |
| Cubana de Aviación | `Q849910` | airline |
| CUPET | `Q3007579` | SOE |
| ETECSA | `Q490323` | SOE |
| BioCubaFarma | `Q107363258` | government organization |
| Unión Eléctrica | `Q116178079` | "Crown corporation" |
| Habanos S.A. | **only `Q1142914` trademark** | no company item |

### 10j. Cuban items of the new kinds that already exist

Searched in en and es: "Buró Político", "miembro del Buró Político", "Segundo
Secretario" + Cuba, "Comité Central" + miembro, "Consejo de Estado" / "Council of
State" + Cuba, "Gobernador/Governor of <each of the 15 P150 provinces>", "Tribunal
Supremo Popular", "Estado Mayor General", "Jefe del Estado Mayor", GAESA,
"Fiscal General", "Contralor". The P39 values held by `P102 = Q371402` or Cuban
politicians were also tallied (126 targets).

- **None exist** for Politburo, Central Committee or Secretariat membership,
  Council of State membership, Second Secretary, chief of the general staff,
  president of the People's Supreme Court, or any SOE head.
- **Governor: 1 of 15**. `Q113662078` La Habana is the only one, so the 14 are
  missing as scoped. Isla de la Juventud is a special municipality, not a
  province.
- Near misses that a categorize pass will be offered:
  - `Q18060652` "Governor of Cuba" is a **colonial** administrator: `P279
    Q132050`, `P1308` Diego de Mazariegos. Not the 2020 office.
  - `Q89188209` is the presidency's twin.
  - `Q24953065` "Secretario general del Partido Comunista de Cuba" is an **empty**
    item (eswiki sitelink, no claims). It is a probable duplicate of `Q5453787`,
    not a second secretaryship.
  - `Q1516390` is used as a P39 value once.

### 10k. What failed, and what to distrust (this run)

- `haswbstatement:P279` (any value) as a "position" filter is useless. With
  `inlabel:"Political Bureau"` / `inlabel:Politikai` it returned 140 political
  science concepts and genres. Filter on the metaclass instead.
- Anchoring on the body class undercounts. `?b wdt:P31 wd:Q309118` politburo finds
  13 bodies, and only 1 of them has a linked position, because bodies are typed
  `P279 Q309118` about as often as `P31`. The CCP Politburo is `P31` political
  organization, `P279` politburo.
- The SOE anchor on `Q270791` and its national subclasses yields only 23
  positions, because enterprises are typed "company" or "business". Widening to
  company classes brings in central banks, which have to be removed by hand.
- The Cuba SPARQL on `P17`/`P1001 = Q241` misses offices scoped only to a province
  (`Q113662078` has no `P17`) and the Republic-era offices whose `P17` is
  `Q14905932`. The second query, on `P1001` → a place with `P17 Q241`, is needed.
- `inlabel:"Chief of Staff"` (544) is dominated by civilian chiefs of staff.
  `inlabel:"Second Secretary"` returns legislative and diplomatic seats. Use
  military and party phrases.
- WDQS answered every query in this run. Nothing timed out, because all were
  subquery-first or Q241-bounded.

### 10l. Belarus's own offices (Q184, measured 2026-10-02)

Population: the runbook's descent query (`p:P31/ps:P31/wdt:P279* Q4164871`,
`P17`/`P1001`/`P1001→P17 = Q184`) returns **641 items**, of which 304 hold any
`P39`. Most of the 337 unheld are honorary titles and ranks ("Заслужаны …",
orders, militsiya ranks, academy memberships) that the descent reaches; 32 are
ambassadorships, a handful church offices. Tallied over the 264 held items left
once ambassadorships, church, trade-union and opposition-cabinet offices are
removed:

| property | tally |
|---|---|
| `P31` | **`Q4164871` 252**, `Q294414` 8, `Q114962596` 2 |
| `P279` | `Q21814449` district-committee chair **119**; none 55; `Q140686` chairperson 9; `Q15623433` (convocation seats) 7; `Q486839` 6; `Q98556185` regional-committee chair 6; `Q104226809` presidential aide 6; `Q83307` 3 |
| `P361` | none 227; **`Q997640` Council of Ministers 28** |
| `P17` | `Q184` 256 |
| `P1001` | a subdivision or town 168, `Q184` 63, none 33 |

Unlike Cuba, a sibling-derived metaclass for Belarus is `Q4164871`. Ministries
are uniformly `P361 Q997640` with `P279` mostly absent (9 of 24) or `Q83307`.
The executive vertical is fully itemised: six oblast chairs (`P279 Q98556185`,
`P1001` the oblast, `P2389` the oblast executive committee), Minsk City
`Q4462174` (`P31` chairperson + position + mayor, `P1001 Q2280`), and ~120
district chairs under `Q21814449`, each `P2389` its committee. `Q184`'s `P150`
is the six oblasts plus Minsk.

Body items:

| body | QID | state |
|---|---|---|
| National Assembly | `Q1798607` | `P31 Q189445` |
| House of Representatives | `Q1649622` | `P361 Q1798607`; per-convocation items `Q28381376` 5th … `Q83463673` 7th are the *Assembly's* convocations (`Q15238777`), not seats |
| Council of the Republic | `Q1512428` | `P361 Q1798607` |
| Council of Ministers | `Q997640` | `P31 Q35798`, `P279 Q640506` |
| Presidential Administration | `Q3918977` | `P31 Q327333` |
| Security Council | `Q16326568` | `P31 Q43229` only, no `P17` |
| KGB | `Q1329608` | `P31 Q939616` |
| National Bank | `Q431491` | central bank |
| Prosecutor General's Office | `Q6482716` | |
| Constitutional Court | `Q252742` | `P31 Q32766` |
| Supreme Court | `Q3001108` | `P31 Q190752` |
| Central Election Commission | `Q2576708` | `P749 Q4127275` |
| All-Belarusian People's Assembly | `Q4127275` | `P31 Q625994`, `Q43229`; `Q125662609` the 7th (2024) |
| General Staff | `Q19772403` | `P31 Q495430`, `P749` the Ministry of Defence `Q2576529`; typed so that the descent counts it as a position |
| SOEs | Belaruskali `Q815266`, Belneftekhim `Q3917821`, Belorusneft `Q4082693`, Naftan `Q3919275`, Mozyr refinery `Q2459960`, Grodno Azot `Q4150056`, Belarusian Potash Co. `Q4082705`, Belavia `Q815314`, Belarusian Railway `Q76987`, Beltelecom `Q4082979`, Belarusbank `Q1997334`, MAZ `Q1251215` | no head-of item exists for any |

Missing outright (CirrusSearch `haswbstatement:P17=Q184 haswbstatement:P31=Q4164871`
with "старшыня"/"председатель"/"Суда", 285 hits read, plus label searches in be
and ru): the Chairman of the House of Representatives, the chairmen of the
Constitutional and Supreme Courts, the State Secretary of the Security Council,
the Chairman of the Central Election Commission, the Chairman of the
All-Belarusian People's Assembly, and every SOE head.

Traps:
- **Membership of the Council of the Republic is two conventions at once**: the
  generic `Q15623433` (110 statements) and per-convocation seats `Q99181114` 1st
  … `Q77927043` 7th, `Q131301762` 8th (3 statements, be label only), each `P279
  Q15623433`. The House has only the generic `Q14335901` (717). `Q105570788`
  (5th convocation) has no holder.
- `Q122831383` judge of the Constitutional Court carries **no `P31`**, so the
  descent does not reach it; `Q122920176` (Supreme Court judge) is typed.
- `Q4436588` KGB chair has `P1001 = Q9291994`, a **person** (Lavitsky).
- `Q14825897` is labelled as the Minsk City Council (en, ru) and as a deputy of it
  (be), and is used as a seat 12 times.
- Renamed offices: `Q13410734` First Deputy Chairman and `Q13410737` Deputy Chairman
  of the Council of Ministers are the pre-1994 titles of `Q18690166` / `Q18690228`;
  `Q100707485` Chairman of the Supreme Council and `Q14324101` its members are the
  pre-1996 legislature.
- `Q98556185` generic "chairman of the Regional Executive Committee" (`P1001
  Q209325` region of Belarus, 0 holders) and `Q21814449` for districts are
  classes, not offices.

### 10m. The Dominican Republic's own offices (Q786, measured 2026-10-03)

Population: the runbook's descent query returns **66 items**; less 34
inbound ambassadorships, church offices and oddments (`Q3643406` Braceros,
`Q5267880` alférez, the first lady), 31 are the state's own, plus the body
`Q30909878` typed as a position. Tallied over those 31:

| property | tally |
|---|---|
| `P31` | **`Q294414` 26**, `Q4164871` 5 |
| `P279` | `Q83307` minister 23; `Q1758037` 2 (both chamber presidencies); `Q1501926` 2; one each of `Q30461`, `Q2285706`, `Q48352`, `Q7330070`, `Q15686806`, `Q486839` |
| `P361` | **`Q3112605` Cabinet 26**; none 3; the chamber 2 |
| `P1001` | `Q786` 29; `Q2119267` the Senate 1 (the Senate presidency, a defect) |
| `P2389` | none 16; the ministry or chamber on the rest |

The modern cabinet is one batch (`Q113992401`..`Q113992471`), uniformly
`Q294414` + `Q83307` + `P361 Q3112605`, so a sibling-derived metaclass is
`Q294414`, as for Cuba. Nothing below the cabinet is itemised: no apex-court
presidency or judgeship, no electoral-body chair, no central-bank governor, no
police or armed-forces head typed as a position, no provincial governorship
(0 of 31), no mayoralty, no state-enterprise head. Holders on Wikidata are
thin too: the presidency 74 statements, the Senate seat 25, the Chamber seat
22, every minister 1-3.

Body items (read in full):

| body | QID | state |
|---|---|---|
| Congress | `Q595411` | `P31 Q189445` |
| Senate | `Q2119267` | `P31 Q2570643`, `P361 Q595411`, `P2388 Q113992525` |
| Chamber of Deputies | `Q320280` | `P31 Q320289`, `P2388 Q23007339` |
| Cabinet | `Q3112605` | `P279 Q640506`, no `P31` |
| Supreme Court of Justice | `Q6136068` | `P31 Q190752` |
| Constitutional Tribunal | `Q9089790` | **no claims but `P571` 2010**, es label only |
| Superior Electoral Court | `Q123166271` | `P17` only, no `P31` |
| Junta Central Electoral | `Q5956447` | `P31 Q935741` |
| Procuraduría General | `Q30909878` | `P31` ministry **and** position, `P279 Q1501926`; the office is `Q113992411`, whose es label is the body's name |
| Contraloría General | `Q5785178` | `P17` only |
| Cámara de Cuentas | **missing** | |
| Consejo Nacional de la Magistratura | `Q5783921` | no claims |
| Central Bank | `Q1800406` | `P31 Q66344` |
| Armed Forces | `Q436714` | `P31 Q772547` |
| Ministry of Defence | `Q17347140` / `Q116731341` | two ministry items; the second's en label reads "Fuerzas Armadas" |
| Army / Navy / Air Force | `Q5290731` / `Q3124137` / `Q2669881` | `P361 Q436714`; the Army's commander `Q119848570` exists with no `P31` |
| National Police | `Q3394185` | `P31 Q732717` |
| Banreservas | `Q5717780` | bank + state enterprise |
| Edesur / Edenorte / Edeeste | `Q5817651` / `Q138348776` / `Q138478738` | Edesur has no `P31` |
| Ayuntamiento del Distrito Nacional | `Q136913293` | no claims |

Traps:
- **Two items for the Minister of Public Health**, `Q113992409` and
  `Q113992469`, with identical claims; only the first is held.
- `Q113992448` is "Ministro Administrativo de la Presidencia" in es and
  "Minister of the Presidency" in en, beside `Q113992686` "Administrative
  Minister of the Presidency": two offices, one mislabelled.
- `Q30909878` (the Procuraduría, a body) is typed `Q4164871`, so it is loaded
  as a position next to the office it is the body of.
- `Q786`'s `P150` is the 31 provinces and the Distrito Nacional, which has no
  governor. Five es province labels carry "Provincia" or a parenthetical, so a
  label template filled from them reads badly.

### 10n. Party leaders, chairs and secretaries; agency heads (measured 2026-10-03)

For the mint's `party_leader` and `party_secretary` archetypes, and a re-check
of `agency_head` and `soe_head`. Live reads. Two populations, because each is
biased in a different way.

**Structural:** every position whose `P2389` or `P361` names an item typed
(`P31`/`P279?`) `Q7278` political party: 289 items. Hand-split by label into
national leaders, chairs/presidents and secretaries (deputies, youth wings,
whips and parliamentary posts dropped; regional branches kept, and named
below):

| cluster | n | states | `P31` | `P279` | body | `P1001` |
|---|---:|---:|---|---|---|---|
| leader | 61 | 16 | `Q4164871` 61 | **`Q1553195` party leader 43**; none 10; one or two each of `Q82955`, `Q319544`, `Q140686` | `P2389` 50, `P361` 34 (both on 23) | absent 39; the state 11; a subdivision 9 (Australian and Canadian branches) |
| chair / president | 86 | 30 | `Q4164871` 83, `Q294414` 3 | **`Q1553195` 37**; `Q140686` chairperson 17; none 17; `Q1255921` 7; `Q2746259` party chair 3; `Q2054321` Parteiobmann 2 | `P2389` 73, `P361` 25 | absent 41; the state 18; Cyprus 10 (one batch, no `P17`); a subdivision 10 |
| general secretary / secretary-general | 47 | 25 | `Q4164871` 44, `Q114962596` 3 | **`Q6501749` general secretary 29**; `Q1553195` 12 (stacked, where the post leads the party); none 8; `Q48352` 5 | `P2389` 38, `P361` 15 | absent 25; the state 13; a subdivision 6 |

**By class:** every item with `P279 = Q1553195` (160): `P2389` 113 (83 of
them a party), `P361` 37, no body 37, `P1001` 67, `P17` 102. Every item with
`P279 = Q6501749` (251) is mostly not a party's: only 27 name a party under
`P2389`, the rest are secretaries-general of IGOs, ministries and
presidencies. `Q836971` party secretary has 15 subclasses, none of them
naming a party.

Exemplars read in full: `Q3615378` Leader of the Labour Party (UK) —
`P31 Q4164871`, `P279 Q1553195`, `P2389` and `P361` the party, `P17 Q145`,
**`P1001` novalue**; `Q29576752` chairman of the SPD — the same, with `P2389`
the party and its executive board, `P1001 Q183`; `Q33195772` Secretary
General of the PSOE — `P279 Q6501749`, `P2389`/`P361` the party, no `P17`, no
`P1001`; `Q52413578` President of the PRI — `P279 Q1553195`, `P2389` the party,
`P17 Q96`; `Q6310828` Chairperson of the DPP — `P279 Q1553195`, `P2389`/`P361`
the party, `P1001 Q865`. The parents: `Q1553195` "leading official of a
political party" (`P31` position and occupation, `P279 Q1251441` leader,
`Q82955` politician; itself `P2389`/`P361 Q7278`); `Q6501749` "leader or chief
officer of an organisation" (`P279 Q140686`); `Q2746259` party chair (5
subclasses); `Q836971` "senior official within a political party with
responsibility for the organizational and daily political work".

So leaders and chairs are one shape and secretaries another only in `P279`:
`party_leader` takes `Q1553195`, `party_secretary` `Q6501749` (or `Q836971`
for a secretariat seat, §10c), both name the party under `P2389`, both carry
no `P1001` — absent from the majority of every cluster, and a party governs no
polity — and both are `Q4164871`, not the public office a state's ministries
declare.

**Agency heads:** positions whose `P2389`/`P361` names an item typed
`Q327333` government agency, filtered to head titles (director, chief, head,
president, chair, administrator, commissioner, general): 3,190 across 169
states. `P31` `Q4164871` 2,827, `Q294414` 355. `P279` none 2,589; past the
central-bank governors (122) and ministers, `Q1501800` director general 79,
`Q1162163` director 29, `Q61861399` 18, `Q140686` chairperson 15. Body
**`P2389` 2,088 against `P361` 1,265**; `P1001` 1,557. The archetype named
its agency under `P361` until now; it takes `P2389`, and the title word picks
director, director general or chairperson, as for an enterprise.

**Enterprise heads** (§10f's 90, re-read): `P31` `Q4164871` 79, `Q294414` 10;
`P1001` absent 68, present 22 (17 of them the state). `scoped=False` and
`P2389` stand; the metaclass is `Q4164871`.

### 10o. Bodies as a discovery lane (measured 2026-10-04)

The question: does reading a state's *bodies* (central bank, audit office, armed
forces, apex courts, electoral bodies, intelligence, police, prosecution, state
enterprises) find offices peploop's descent, usage, citizen and outbound lanes
miss? There are two hooks. Hook 1 is the body's own `P2388` (office held by
head), with `P1037` director and `P488` chairperson for the current head. Hook 2
is any item naming the body under `P2389` or `P361`. The run covered eight
countries: cu, co, by, bi, do, ht, jm and tt. Everything was read live, and the
peploop DB was read-only.

**Finding the bodies.** There were three sources. (a) Type: `p:P31/ps:P31` to a
class, or one `P279` hop below it, with `P17`, `P1001` or `P131` naming the
state. (b) Every `body:` in `peploop/census/*.yml`, typed by its census class.
Colombia has no census. (c) The `body_qid` of every loaded `position` row of the
state, typed by its `P31`. That gives 675 bodies in all, and **134 of them fall
in a FATF class** (127 not dissolved). The rest are cabinets, ministries,
chambers and parties.

**Which classes the community uses.** Measured globally, by reading the
`P2389`/`P361` body of every position that subclasses the kind's head class, so
the body sample is chosen by its office and not by its own type:

| kind | head class | bodies | `P31` of the body |
|---|---|---:|---|
| central bank | `Q107363151` | 142 | **`Q66344` central bank 127 (89%)**; business 12, bank 6 |
| armed forces | `Q5097014` | 36 | `Q772547` armed forces 18; `Q495430` general staff 8; `Q327333` agency 5; `Q1788820` defence ministry 3 |
| apex court | `Q3188089`, `Q16474031` | 124 | `Q190752` supreme court 46; national or sub-national subclasses 37 (ES, US, CA); `Q41487` court 9; `Q32766` constitutional court 8; untyped 7 |
| police | `Q2855502`, `Q2101758` | 117 | `Q10387680` organisation unit 83, which are sub-national forces; `Q732717` 10, `Q35535` 6, `Q7410456` 4 |
| prosecution | `Q3368517`, `Q1501926`, `Q16353016` | 74 | **untyped 25**; `Q327333` agency 18; two competing classes, `Q11775750` 7 and `Q1092499` 6 |
| intelligence | `Q105695126` | 8 | `Q327333` 4, `Q47913` 3. Belarus's KGB is `Q939616` secret service, which subclasses only "government agency" |
| audit (SAI) | none generic | — | `Q43306178` supreme audit institution is on **11 items worldwide**. Among 89 label hits ("Contraloría General", "Cour des comptes", "Court of Audit", "Rechnungshof"…), `Q10983451` Court of Audit 20 and `Q327333` 3; most are untyped or typed by the national agency class |
| electoral | — | 296 | `Q935741` election commission is used directly (296 items) |
| general staff | — | 56 | `Q495430` 56 |

Only two kinds are typed reliably: **central banks** (`Q66344`) and
**election commissions** (`Q935741`). General staffs are reliable where they
exist (56 items worldwide). Armed forces split between `Q772547` and `Q8473`.
Prosecution and audit bodies cannot be found by type at all.

**Per class and country.** Each cell reads bodies / with `P2388` / with an
unended `P1037` or `P488` / office items reached by either hook / of those, not
in `position` today:

| class | cu | co | by | bi | do | ht | jm | tt | total |
|---|---|---|---|---|---|---|---|---|---|
| central bank | 1/1/0/1/0 | 2/1/1/1/0 | 1/1/1/1/0 | 1/0/1/0/0 | 1/0/1/0/0 | 2/0/0/0/0 | 1/1/1/1/0 | 1/1/0/1/0 | 10/5/5/5/0 |
| audit (SAI) | 1/0/0/0/0 | 1/0/1/1/0 | 0 | 0 | 1/0/0/0/0 | 1/0/0/0/0 | 0 | 0 | 4/0/1/1/0 |
| defence | 6/0/0/0/0 | 4/1/0/2/0 | 4/3/1/3/0 | 1/0/0/0/0 | 2/0/0/2/1 | 5/1/0/1/0 | 2/1/0/1/0 | 2/0/0/0/0 | 26/6/1/9/1 |
| apex court | 1/0/0/0/0 | 2/0/0/2/0 | 2/0/0/2/0 | 2/0/0/0/0 | 2/0/0/2/0 | 1/0/0/0/0 | 1/0/0/0/0 | 1/0/0/0/0 | 12/0/0/6/0 |
| electoral | 1/0/0/0/0 | 1/0/0/0/0 | 1/0/1/1/0 | 1/0/0/0/0 | 2/0/0/0/0 | 1/0/0/0/0 | 0 | 0 | 7/0/1/1/0 |
| intelligence | 2/0/0/0/0 | 3/1/0/1/0 | 2/0/0/1/1 | 2/0/1/0/0 | 0 | 1/0/1/0/0 | 0 | 0 | 10/1/2/2/1 |
| police | 2/0/0/0/0 | 3/0/0/1/1 | 5/0/0/0/0 | 1/0/0/0/0 | 2/0/0/1/0 | 2/0/0/0/0 | 5/0/0/0/0 | 1/0/0/0/0 | 21/0/0/2/1 |
| prosecution | 0 | 1/0/0/0/0 | 2/1/0/1/0 | 0 | 0 | 1/0/0/0/0 | 1/0/0/0/0 | 0 | 5/1/0/1/0 |
| SOE | 4/0/1/0/0 | 7/0/0/0/0 | 22/0/1/0/0 | 0 | 4/0/0/0/0 | 0 | 1/0/0/0/0 | 1/0/0/0/0 | 39/0/2/0/0 |
| **total** | | | | | | | | | **134/13/12/27/3** |

The type search misses prominent bodies that exist. Belarus's KGB `Q1329608`
(`Q939616`), its State Control Committee `Q6497506` (`Q948571` organ of state)
and its interior ministry `Q2427674` are all missed, though each has a `P2388`
whose target is already loaded. Ecopetrol `Q1282130` (typed business/public
company) is missed. So is the Dominican DNI `Q10884568`, which has no `P31`.
Several bodies have no item at all: the audit offices of jm, tt, bi, do and ht;
Cuba's Fiscalía; Burundi's parquet général; and Jamaica's Court of Appeal and
Supreme Court.

**Hook 1, `P2388`.** Of the 134 FATF-class bodies, 13 carry it: central banks 5,
defence 6, intelligence 1, prosecution 1. Of all 675 bodies, 421 carry it,
nearly all of them ministries and chambers. **Every one of the 421 targets is
already in `position`.** The reason is that the bodies careful enough to state
`P2388` point at offices careful enough to state `P17`/`P1001`, which the
descent finds anyway. Hook 1 adds no office in any of the eight countries.

**`P1037` / `P488` are not current-head evidence.** 12 bodies carry an unended
value (13 people), and at least 7 of the 13 are wrong:
- GAESA's `Q108037988` died in 2022;
- Banco de la República's `P488` names the manager whose term ended in 2021;
- the Bank of Jamaica's names the governor who left in 2019;
- Belarus's MoD `P1037` names the minister to 2020, and the NBRB's names a
  chairman whose own `P39` ends in 2025;
- Burundi's central bank names a governor who is now an MP;
- Haiti's Service d'Intelligence National names **`Q37230` the CIA** as its
  director.

A property with no end date reads as "current" but is usually just never
closed.

**Hook 2, reverse `P2389`/`P361`.** Together with hook 1's targets it reaches
83 items. 25 declare a position metaclass, and 24 of those are already loaded.
2 are untyped. 56 are not offices: military units and service branches that
name their armed forces under `P361` (by 21, co 13, cu 7), plus a library and
an art collection under Colombia's central bank. Two of the 56 are already in
`position`: the Dominican Army `Q5290731` and Belarus's General Staff
`Q19772403`. Only 3 items are new to `position`, and 2 of those are real
offices:
- **`Q135659026`** head of Belarus's Presidential Security Service: `P31`
  position and `P2389` the service, but no `P17`/`P1001`;
- **`Q119848570`** the Dominican Army's general commander: `P2389` the army and
  no other claim.

The third, `Q5280641`, is an untyped Colombian police directorate, a body. No
rank or honour was reached by either hook (nothing hit `NOT_AN_OFFICE`). But
the units would load **unflagged**, because `not_office` tests declared types
only and a unit declares `Q176799` military unit, not `Q43229`. The 6-hop type
closure is no filter either. It puts Belarus's General Staff `Q19772403`,
Colombia's Luis Ángel Arango Library `Q531927` and two Belarusian service arms
under `Q4164871`. Only a declared position metaclass separates the offices.

**People.** The hooks reach 48 current heads: live `P39` holders of the
reached offices plus `P1037`/`P488`. 37 of them are among the run's people.
Every one reached through an office already holds a `P39` on a loaded item.
The only stranded run people (no `P39` at all) are 3 reached through
`P1037`/`P488`, and none of them has an office item to place:
- `Q108037988` GAESA, who is dead;
- `Q20013830` Colombia's Contraloría;
- `Q11976472` the Dominican central bank.

For context, the run has 1,084 people with no `P39` across the eight countries
(cached item JSON).

**What blocks the rest.** Of the 127 live FATF bodies, 93 reach no office
through either hook. The known gaps sort three ways.

1. *An office item exists but carries nothing a lane reads.* These are real
   offices that are invisible or unanchored for want of `P31`, `P17`/`P1001` or
   a body link. 15 of the run's people name one of them in a mention that
   failed to place, and 8 of those 15 have no `P39` at all. Among the 8 are
   Tobago's current Chief Secretary (`Q126725819`) and current Presiding
   Officer (`Q111372484`).

   | item | office | lacks | unplaced run people (no `P39`) |
   |---|---|---|---:|
   | `Q106040759` | Chief of Defence Staff (TT) | `P17`, `P1001`, `P279`, `P2389` (only `P31`) | 1 (0) |
   | `Q85751924` | Chief Secretary of Tobago | every claim | 2 (1) |
   | `Q85794414` | Presiding Officer, Tobago House of Assembly | every claim | 4 (4) |
   | `Q123054908` | Governor, Banque de la République d'Haïti | every claim | 1 (0) |
   | `Q132736192` | member seat, Haiti's CPT | every claim (loaded via the citizen lane) | 2 (2) |
   | `Q119848570` | General Commander, Dominican Army | `P31`, `P17`, `P1001` | 2 (1) |
   | `Q135659026` | Head, Belarus Presidential Security Service | `P17`, `P1001` | 3 (0) |
   | `Q85751928` | Chief of Defence Staff (JM) | `P1001` only (already loaded via `P17`) | 0 |

   `old/scripts/body_fixes.sh` adds the missing statements: 28 additive
   `wb add-claim` lines, each written against the revision it was read at.
2. *The body is known, but it has no `P2388` and no office item exists.* These
   are mint candidates with a body to name under `P2389`:
   - **Colombia's Supreme Court of Justice president.** No item, under any
     es/en label searched. 2 run people name it unplaced, and 3 more name the
     magistracy.
   - Colombia's Contralor General: the body `Q8042106` has `P488` but there is
     no office.
   - The Dominican central bank governor (`Q1800406`, with a current `P488`).
   - GAESA's head.
   - The police heads of jm (`Q3160777`), tt (`Q7842422`) and ht (`Q3394179`).
   - Burundi's apex courts, central bank, armed forces, SNR and police.
   - Belarus's thirteen census SOEs.

   The census already lists most of these. A body lane adds only the bodies
   the census has not named, chiefly the type-found SOEs and units, which are
   noise.
3. *The body itself is missing.* The audit offices of jm, tt, bi, do and ht;
   Cuba's Fiscalía; Burundi's parquet; Jamaica's Court of Appeal.

**Ambiguous, and kept out of the script:**
- `Q125542684` "Inspector General of Colombia" (es "Procurador general de
  Colombia", no claims) against `Q16622285` "Attorney General of Colombia" (es
  label also "Procurador General de Colombia", `P279` public prosecutor general,
  loaded). The enwiki article of the second is about the Fiscalía. That is a
  label and merge question, not a missing statement.
- `Q6448961` "Intendente Jefe de la Policía Nacional de Colombia" (`P17`
  only) is a police **rank**. Typing it would make a rank an office.
- `Q30909878` "Office of the Attorney General" (DO) is typed both `Q192350`
  ministry and `Q4164871` position, with `P279` attorney general: a body
  modelled as an office (a `wd/shape.py` defect).
- Haiti's SIN `P1037 = Q37230` (the CIA) is wrong, but the fix is a removal.
- The Chief Secretary of Tobago's `P279`: the measured analogues split
  (`Q5096847` "chief minister" 30 of 53 "Chief Minister of …" items, all of
  them Indian; `Q2285706` head of government 5). It is left without one.
- Bodies with no `P31`: Trinidad and Tobago Police Service `Q7842422`,
  Tribunal Constitucional (DO) `Q9089790` (no `P17` either), TSE (DO)
  `Q123166271`, Contraloría (DO) `Q5785178`, Edesur `Q5817651` and DNI (DO)
  `Q10884568`. Typing them helps a type-based body search, not discovery of
  any office.

#### Proposal: a body lane, if any

**A generic body lane is not worth it.** Over eight countries, hook 1 (`P2388`)
reaches nothing new, and hook 2 reaches 2 real offices among 83 items, 56 of
which are military units that would load as unflagged rows. The offices the
runs actually lost are invisible *to every hook*: an item with no claims has no
`P2389`, and its body has no `P2388` to it. A discovery lane cannot read a
link that was never written. These cases get fixed in the data, as
`old/scripts/body_fixes.sh` does, or by the mint.

If one is wanted anyway, the narrow version that pays is **reverse `P2389`
only, from bodies of the two reliably typed classes plus the census bodies,
admitting only items that declare a position metaclass or declare nothing**:
- Drop `P361`, which is the unit channel.
- Drop `P2388`, which is redundant with the descent.

It slots into `positions.py` as a fifth default source, `"body"`, beside
`"outbound"` and in the same shape: two phases, no new CLI flag. Phase one
asks for the state's bodies: `P31` central bank, election commission or general
staff, scoped `P17`/`P1001`, plus the census bodies passed in by the run.
Phase two asks `?pos p:P2389/ps:P2389 ?body`, chunked by `values_chunks`, and
keeps an answer only if it declares a position metaclass or declares nothing.
That is a post-query filter, as `_discover_outbound` keeps only
`DIPLOMATIC_CLASS`, never a `P279*` in the query. Measured here, it would have
found `Q135659026` and `Q119848570`, and after the script nothing that descent
does not.

**The census covers the rest.** Its `body:` QIDs are the hand-checked version
of phase one, and they already feed the mint, which is where class 2 belongs.
What the census does not do, and should, is record the office item when one
exists unconnected (`exists: Q85751924, claimless` is a comment in `tt.yml`
today). That item belongs in the fix list, not the mint queue. Otherwise the
mint's duplicate guard is the only thing standing between a claimless office
and a second item for it.

### 10p. Deputy, vice and junior ministers (measured 2026-10-04)

For the mint's `deputy_minister` and `minister_of_state` archetypes. Live
reads. Clusters are CirrusSearch `inlabel:"<phrase>@<lang>"` over the six
metaclasses of §10, kept only where the label in that language *begins* with
the phrase: "Deputy Minister of/for", "First Deputy Minister", "Vice(-)Minister
of", "Viceministro/a de", "Заместитель министра", "Первый заместитель
министра", "Заступник міністра" (the **deputy** cluster, 488 items, 51 states);
"Minister of State in/at/for" (**minister of state**, 377 items, 41 states);
"secrétaire d'État", "Secretario de Estado de", "Secretário de Estado"
(**secretary of state**, 281); "Junior Minister" (4) and "Parliamentary
Secretary" (25). `P31`/`P279`/bodies are read off claims, every rank but
deprecated. The bodies were classified by their labels (a cabinet, a council
of ministers, a government vs a ministry or department), because their types
do not separate the two: a cabinet and a ministry both reach `Q327333`.

| cluster | n | `P31` | `P279` | body | `P1001` |
|---|---:|---|---|---|---|
| deputy | 488 | `Q294414` 370, `Q4164871` 130 | `Q83307` minister 170 (15 states); **`Q26204040` deputy minister 107** (27 states, with its national subclasses: Bulgaria 8); `Q15735113` assistant secretary via the Greek, Cypriot and Israeli national classes 39; `Q118286354` Minister of Mozambique 28; none 92 (14 states) | `P361` 341, `P2389` 20, none 135. **The government or cabinet 284**, a ministry ~69 (Indonesia 38 of them) | 414; the state itself 302 |
| minister of state | 377 | `Q294414` 293, `Q4164871` 89 | **`Q83307` minister 165 (35 states)**; `Q3315100` (UK) 91, `Q2325081` (Ireland) 28 and `Q2632935` itself 16, all `Q2632935` minister of state (13 states); `Q245696` (Japan) 37; none 32 | `P361` 267, `P2389` 28. **The cabinet 235**, a ministry or department ~33 | 343; the state 337 |
| secretary of state | 281 | `Q4164871` 167, `Q294414` 134 | national classes: Portugal `Q115209702` 45, UK cabinet `Q14214` 37, Spain `Q3477289` 22; `Q83307` 34; `Q736559` 30 | cabinet/government 163, ministry ~66 | 240 |

`Q26204040` **deputy minister** ("person who assists minister in management
of ministerial financial and human resources and can act on behalf of the
minister"): `P31 Q4164871`, `P279 Q3250324` deputy, labelled in en, es
(viceministro), fr (vice-ministre), ru (заместитель министра), de; 7
sitelinks. It does **not** subclass `Q83307` minister, and it reaches
`Q4164871` only through its own `P31` -- which is the walk the consumer uses.
`Q90132546` "deputy minister" (political function, 2 subclasses, both
Belarusian) is a stray duplicate. `Q2632935` **minister of state** ("minister
assigned to assist a specific cabinet minister"): `P31 Q294414`, `P279
Q83307` minister. `Q1307214`, suggested as a candidate, is "form of
government" and unrelated. `Q21814496` "first deputy" subclasses deputy, and
two Belarusian first-deputy items use `Q26204040` instead.

**One seat or many.** Of the 148 deputy items with a holder whose `P39`
started in 2016 or later and records no end, 33 have two or more such holders
at once (Russia's deputy defence minister 6, Thailand's interior 4, Georgia's
interior 4): a deputy ministership is a seat several people hold together.
A first deputy is a seat of its own, minted as its own item -- 20 "First
Deputy Minister" items, none merged with the plain deputyship of the same
ministry. Ministers of state are mostly one per ministry, but Ireland and
Jamaica each carry ministries with two current.

**Per-ministry items, not a generic item with a qualifier.** 316 people hold
`P39 = Q26204040` itself (193 of them with a qualifier naming the ministry),
concentrated in Hungary 106, Georgia 37, Czechia 29 and Canada 27; 139 hold
`Q2632935` itself (Iraq 34). Against them, the 488 per-ministry deputy items
carry 2,809 holder-item pairs, and none of the eight run countries' people
uses the generic item. So the generic convention is a handful of states'
practice, and a deputy ministership is minted as its own item.

**The run countries' own items.**

| state | items | shape |
|---|---|---|
| Belarus | 7 deputies, 3 of them first deputies (`Q90133244`, `Q90132622`, `Q106400254`, `Q137842286`, `Q63928477`; first `Q19849020`, `Q106400307`, `Q116947355`) | `P279 Q26204040` on 5 (two stack the stray `Q90132546`, one `Q15735113`); `P31 Q4164871` 4, `Q294414` 1, none 2; **no body**; `P1001` the state. Labels "Deputy Minister of X of the Republic of Belarus", ru "заместитель Министра …", be "намеснік Міністра …" |
| Jamaica | 10 ministers of state (`Q112109646`…`Q115278562`) | `P31 Q294414`, `P279 Q83307`, **`P361 Q5015520` Cabinet of Jamaica**, `P1001` the state; every label "Minister of State **at** the Ministry of X" (or "at the Office of the Prime Minister"); description "cabinet position in Jamaica" |
| Colombia | 1 (`Q140800142` Vice Minister of Defense) | `P31 Q4164871`, no `P279`, `P361` the ministry `Q3062492` |
| cu, do, ht, bi, tt | none | Trinidad and Tobago's ministers of state and parliamentary secretaries have no items at all |

So the two kinds differ in `P279` and in nothing else. **`deputy_minister`**
takes `Q26204040`; **`minister_of_state`** takes `Q2632935`, keeping a drafted
`Q83307` where the state's own ministers of state use it (Jamaica). Both name
the government or cabinet under `P361` -- the body the state's ministers sit
in, not the ministry, by about four to one in both clusters -- are scoped to
the state, take their metaclass from the state's siblings, and are not one
seat. The sibling label wins over the drafted one: an article's "Minister of
State in the Ministry of X" is minted as Jamaica's "… at the Ministry of X".
Parliamentary secretaries (Jamaica, Trinidad and Tobago) are a third kind
with 25 items worldwide and no class of their own; they get no archetype.
