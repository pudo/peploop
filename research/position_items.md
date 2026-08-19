# Measured: how Wikidata models political position items

The evidence behind `recipes/position_items.md`. The recipe says what to do; this
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

## 9. What failed, and what to distrust

Recorded rather than estimated:

- `SELECT ?t (COUNT(DISTINCT ?pos)) WHERE { ?h wdt:P39 ?pos . ?pos p:P31/ps:P31 ?t }
  GROUP BY ?t` — never returned (>15 min, 4 attempts). The §2 "reality check"
  figures come from four single-type counts instead, which did run.
- `SELECT (COUNT(DISTINCT ?i)) WHERE { ?i p:P279/ps:P279 wd:Q83307 . FILTER NOT
  EXISTS { ?i p:P31/ps:P31 wd:Q4164871 } }` — repeated 503s. Derived by
  subtraction (5,211 − 739).

Two standing cautions:

- **WDQS will not take a label regex over all positions.** `FILTER(CONTAINS(
  LCASE(?l), …))` across `Q4164871` answers with a 504. Use CirrusSearch
  (`haswbstatement:P31=Q4164871 <term>`), and search **words** — `lithuan` is not a
  word and matches nothing, which silently cost an audit its four highest-value
  items on one run.
- **Holder-derived priors are corpus-biased** (`country_sweep.md` §10 rule 5).
  Nothing above rests on them, deliberately.
