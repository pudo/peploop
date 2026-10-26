# Measured: generic position classes used as `P39` values

This is the evidence for marking classes like `Q83307` minister, `Q30185` mayor and
`Q486839` member of parliament as **generic type of position**. That is a proposed
subclass of `Q136649946`, added as an extra `P31`. These items are used as the
*value* of `P39` but name no jurisdiction, so a holder statement pointing at one
says nothing about where the office was held. The list itself is
`peploop/generic_positions.csv`. Consumers can read that file until the Wikidata
marker exists.

**Measured 2026-10-04** against live WDQS and `wbgetentities`. Usage counts use
`p:P39/ps:P39` (every rank). Types are read from the item's own non-deprecated
`P31` claims. Holder spread is `wdt:P27` of holders.

## 1. Headline

| | items | `P39` statements | share of all `P39` |
|---|---:|---:|---:|
| all `P39` | — | 1,999,176 | 100% |
| values used ≥ 20 times (the measured set) | 9,073 | 1,496,761 | 74.9% |
| **generic (rule §2)** | **232** | **154,814** | **7.74%** |
| batch 1 (top 100 by use) | 100 | 147,041 | 7.36% |
| batch 2 | 132 | 7,773 | 0.39% |

Batch 1 holds 95.0% of all generic usage. By domain it is 39 public office, 25
organisational/corporate, 17 religious, 12 royal/court and 7 academic. The domain
was assigned by hand and is not used by the rule.

Top ten:

| item | `P39` uses | holder countries | largest country share |
|---|---:|---:|---:|
| `Q30185` mayor | 15,676 | 271 | 40% |
| `Q1255921` president | 11,551 | 263 | 37% |
| `Q140686` chairperson | 10,149 | 317 | 19% |
| `Q1162163` director | 9,662 | 207 | 45% |
| `Q83307` minister | 9,560 | 289 | 5% |
| `Q29182` bishop | 7,742 | 235 | 16% |
| `Q486839` member of parliament | 7,078 | 239 | 30% |
| `Q30461` president | 7,006 | 176 | 73% |
| `Q589298` editor-in-chief | 3,940 | 149 | 17% |
| `Q121998` ambassador | 3,851 | 305 | 11% |

Where the rest of the measured set went:

| disposition | items | `P39` statements |
|---|---:|---:|
| has a jurisdiction | 7,739 | 1,150,617 |
| not typed as a position (occupations, church ranks) | 543 | 132,406 |
| no jurisdiction, single country (≥ 80% one `P27`) | 249 | 33,062 |
| no jurisdiction, too few jurisdictions (fails the spread test) | 268 | 19,611 |
| hand veto | 28 | 5,871 |
| body veto (§2, test 5) | 14 | 380 |
| **generic** | **232** | **154,814** |

## 2. The rule

An item is generic when all four tests hold.

1. **It is typed as a position.** Its own `P31` includes `Q4164871`, `Q294414`
   or `Q136649946`. Without this test the list would pull in occupations
   (`Q1144278` diocesan bishop, 19,479 uses, `P31` ecclesiastical occupation).
2. **It has no jurisdiction.** It has no `P17` and no `P1001`, **or** every such
   value is itself a class. "Is a class" means the value has `P279`, or its own
   `P31` is a metaclass (`Q19478619`, `Q24017414`, `Q23958852`, `Q24017465`,
   `Q136649946`, `Q16889133`), and it is not an instance of a territory type
   (`P31/P279*` into `Q56061`, `Q1048835`, `Q6256`, `Q3024240`, `Q7275`,
   `Q15642541`, `Q82794`). One concrete value anywhere makes the item scoped.
3. **Holders are spread across jurisdictions.** The largest single `P27` covers
   less than 80% of holders that have one, **and** either at least 3 direct
   subclasses carry distinct `P1001`, or holders come from at least 15 countries
   with none above 50%.
4. **It survives the veto** in `veto.json`. Two kinds of item are removed by hand:
   - `specific_body`, 15 items: the office of one named body (`Q30771010` ICJ
     judge, `Q128212331` IOC member, `Q1161813` UNGA president, the UNICEF/UNESCO
     goodwill ambassadors, FIFA/FIBA referee, Diet of Galicia, Filiki Eteria);
   - `occupation_or_status`, 14 items: positions that are really occupations
     (founder, teacher, physician, journalist, emeritus, partner, fellow).
5. **Its body is not one specific organisation.** If every `P361`/`P2389` value
   is an instance rather than a class (it has no `P279`), the item is the office of
   that one body, however international its holders are. This test was added at
   review after the hand veto missed 13 such offices: the African Union, ECOWAS
   and OAU chairs, the ICJ president and vice-president, the presidents of
   Interpol, the CERN Council, PACE, IFLA and the Universal Esperanto
   Association, the TEJO board, and the Ukrainian Free University rectors. Several
   are intergovernmental PEP offices, so blocking or tagging them would be wrong.
   `Q2092585` ambassador of the European Union went too: one sender, like
   "ambassador of Belarus". Two flagged items stay: `Q212238` civil servant (its
   body is the concept officialdom) and `Q7888495` UN permanent representative
   (generic across sending states).

The territory exclusion in test 2 matters. With `P279` alone as the class test,
65 of the 3,414 jurisdiction values read as classes. That included `Q1747689`
Ancient Rome, `Q12544` Byzantine Empire and 15 other states that carry `P279`
alongside their state type. With the exclusion, 48 values remain, and they are
genuinely class-like: `Q15284` municipality, `Q484170` commune of France,
`Q665487` diocese, `Q2385804` educational institution, `Q173843` regency.

The class-valued rule added **8 items and 31,243 statements**: mayor 15,676, bishop
7,742, council member 3,658, cardinal 2,933, regent 587, consul 423, alderman 150
and count 74. Without it the list was 238 items and 123,951 statements, and the
most generic office of all, mayor with holders from 271 countries, was out because
its `P1001` names the *kind* of place. The other class-valued items fell to the
remaining tests:
- not typed as a position: `Q212071` rector 8,416, `Q189854` metropolitan 1,042;
- single-country: `Q30103103`, 90%.

## 3. Borderline cases

- **Historical states fragment `P27`.** "Member of the 18th Parliament of Great
  Britain" (`Q94911433`, 764 uses) has holders from 9 "countries": Kingdom of GB,
  UK of GB&I, UK, England and others. Its top share is 0.53, so citizenship alone
  calls it multi-jurisdiction. It has no subclasses and fewer than 15 countries,
  so test 3 rejects it. It needs a `P17`, not this marker; the same holds for the
  other GB Parliament term items. The Diet of Galicia (`Q24257953`, 20
  countries, top share 0.24) does pass the numbers, and it is in the veto for that
  reason.
- **A single dominant country with many subclasses.** `Q189010` notary has 286
  subclasses but 97.5% French holders: excluded. These are French notary offices
  with a missing `P17`. `Q30461` president is 73% French with 128
  jurisdiction-scoped subclasses: included.
- **Country-scoped metaclasses are not generic.** `Q382617` mayor of a place in
  France (2,075 uses, 40,193 subclasses), `Q13423499` the Dutch equivalent and
  `Q3044918` member of the French National Assembly (18,905) all carry a concrete
  `P17`/`P1001`. These are the "legitimate intermediates": a class whose instances
  are the eras or seats of one office in one state.
- **Odd class-like values.** `Q1140115` Government of Russia, `Q597526` Latin
  Church and `Q589856` Catholic Church in Chile carry `P279`, so they count as
  classes. None of the items using them passes test 3, but the test is only as
  good as the `P279` it reads.
- **Church offices split on test 1.** `Q29182` bishop and `Q45722` cardinal are
  typed as positions and qualify. `Q1144278` diocesan bishop, the item the
  community pairs with a `P708` diocese qualifier, is typed as an occupation and
  does not. Whether qualifier-scoped conventions should be exempted explicitly is
  an open question in the community note.

## 4. `Q136649946` (type of position)

- 93 items carry it at statement level. The class was created on **2025-10-26**.
- Edit summaries since 2025-09 name the first addition for 88 of the 93:
  - by editor: one editor 55, a second 12, a third 3, and 13 others with 1–2
    each;
  - by month: 2025-10 56, 2025-11 3, then a trickle, with 13 in 2026-09.
- **It replaced rather than added.** The sampled diffs on `Q486839`, `Q140686` and
  `Q581817` are `wbsetclaim-update` edits that turned `P31 Q4164871` into
  `P31 Q136649946`. Today 85 of 93 have no direct `P31` `Q4164871`/`Q294414`.
  For 14 of them, `P279+` does not reach `Q4164871` either: `Q248577`, `Q599151`,
  `Q1540324`, `Q28806166`, `Q62075809`, `Q113712126`, `Q116033480`, `Q131340825`,
  `Q136974651`, `Q136975581`, `Q136975737`, `Q138479408`, `Q139929993` and
  `Q140796532`. Their direct subclasses that have no position-type `P31` of their
  own number 335. A consumer whose closure starts from direct `p:P31` loses them.
- **What it marks.** About 40 of the 93 are "mayor of a place in <country/state>"
  classes, which carry a `P17`. So it means "a class of positions", not "has no
  jurisdiction".
- **Overlap.**
  - 37,451 `P39` statements point at its items, and 32,488 of those go to the 11
    that are also generic: chairperson, minister, MP, ambassador, deputy
    chairperson, deputy mayor, prime minister, official, head of state, head of
    mission, head of government.
  - Of the 93, 11 are generic, 5 have a jurisdiction, and 77 have fewer than 20
    `P39` uses.
  - Of the 232 generic items, 11 carry it.

## 5. Routes compared

| route | where the marker lives | covers today | cost for 232 | consumer read |
|---|---|---|---|---|
| **subclass of `Q136649946`, additive `P31`** (chosen) | item | 0 | 1 create + 232 additive lines | direct `P31` on the item |
| `Q136649946` alone | item | 11 | — | can't tell scoped from generic |
| `P39` none-of constraint (`P2302 = Q52558054`) | property | 4 (`Q83307`, `Q486839`, `Q1055894`, `Q765778`) | grouped statements; property-talk consensus for every addition | parse `P2305` qualifiers on `P39` |
| `P5008` focus list | item | 0 | 1 create + project page + 232 lines | `wdt:P5008` |

Notes on the existing tools:
- **The none-of constraint is inconsistent.** `P39` has 14 none-of statements.
  `Q83307` and `Q1055894` are mandatory (no `P2316`). `Q486839`, `Q16886136`,
  `Q55400987`, `Q703534` and the 49 US-mayor classes are suggestion
  (`Q62026391`).
- **What `P5008` would look like.** A focus-list item looks like `Q140249898`:
  `P31 Q51539995`, `P973` project page, `P921` subject, 3,423 uses. The
  every-politician project item `Q5492483` has 52 `P5008` uses, and
  `Q15884641` WikiProject Politicians has none. A focus list means "a project is
  working on this", which is the wrong meaning for a permanent marker.

## 6. Consumer rule

Read **only the item's own non-deprecated `P31`**. Never use the transitive
closure. `Item.types` in nomenklatura walks `P31` and `P279` at every level, so a
specific office ("Minister of Finance of Brazil", `P279 Q83307`) would inherit the
marker from its parent and be dropped.

```sparql
SELECT ?item WHERE {
  ?item p:P31 ?st . ?st ps:P31 wd:Q_NEW .
  MINUS { ?st wikibase:rank wikibase:DeprecatedRank }
}
```

The list is about 250 items, small enough to load once per run as a set. Until
`Q_NEW` exists, `peploop/generic_positions.csv` is that set.

Where it plugs in:
- **zavod, `wikidata_position`.** Return early on a direct hit. Leave
  `SUB_TYPES` alone: generic items stay useful there as superclasses for topic
  assignment.
- **The politician discovery query** can add
  `FILTER NOT EXISTS { ?position p:P31/ps:P31 wd:Q_NEW }`.
- **nomenklatura, `Item`.** Add a direct-only `P31` accessor next to `types`.

## 7. Queries

Every query goes through WDQS POST. `VALUES` chunks hold 3–100 items, and a
timeout or truncated JSON bisects the chunk.

```sparql
# usage per P39 value, all ranks (~60 s)
SELECT ?pos (COUNT(*) AS ?n) WHERE { ?s p:P39 ?st . ?st ps:P39 ?pos }
GROUP BY ?pos HAVING(COUNT(*) >= 20)

# subclass profile (chunks of 100)
SELECT ?i (COUNT(DISTINCT ?x) AS ?subs) (COUNT(DISTINCT ?j) AS ?subjur)
WHERE { VALUES ?i { … } ?x wdt:P279 ?i . OPTIONAL { ?x wdt:P1001 ?j } } GROUP BY ?i

# holder citizenship spread (chunks of 20; 10 for the big ones)
SELECT ?i ?c (COUNT(DISTINCT ?s) AS ?n)
WHERE { VALUES ?i { … } ?s p:P39/ps:P39 ?i . OPTIONAL { ?s wdt:P27 ?c } } GROUP BY ?i ?c

# territory test for jurisdiction values (chunks of 60)
SELECT DISTINCT ?v WHERE { VALUES ?v { … } ?v wdt:P31/wdt:P279* ?root .
  VALUES ?root { wd:Q56061 wd:Q1048835 wd:Q6256 wd:Q3024240 wd:Q7275 wd:Q15642541 wd:Q82794 } }

# example offices: subclasses with a country and holders (depth 1, then depth 2 for misses)
SELECT ?i ?x (COUNT(*) AS ?n) WHERE { VALUES ?i { … } ?x wdt:P279 ?i .
  ?x wdt:P17 [] . ?h wdt:P39 ?x } GROUP BY ?i ?x

# Q136649946 adoption
SELECT ?i (COUNT(*) AS ?n) WHERE { ?i p:P31/ps:P31 wd:Q136649946 . ?s p:P39/ps:P39 ?i } GROUP BY ?i
```

`Q136649946` history comes from `prop=revisions&rvstart=2025-09-01`, matching
`Q136649946` in edit summaries.

## 8. What failed, and what to distrust

- **The example query with a join inside.** Joining `?c wdt:P31 wd:Q3624078` inside
  the example query did not finish on minister (5,230 subclasses). The sovereign
  states were fetched separately and filtered in Python. A depth-2 example query
  (`wdt:P279/wdt:P279?`) over all 246 candidates at once made about one chunk per three
  minutes; splitting by depth fixed it.
- **`(wdt:P31|wdt:P279)+` path tests time out** on the Q136649946 items. `wdt:P279+`
  alone ran.
- **Example offices.** A pick ranked by sitelinks or by holder count is wrong often
  enough to need reading:
  - by sitelinks: chairperson → President of Vietnam, monarch → Pope, ambassador →
    goodwill ambassador;
  - by holders, the top hit is usually a country-level class, not an office: mayor →
    mayor of a place in the Netherlands.

  Examples in `generic_positions.csv` marked `hand` were read: each is a specific
  office within two `P279` steps of the generic item, with `P17` set and `P39`
  holders. `auto` means only the mechanical part was checked. For 13 of batch 1
  there is no such subclass (e.g. court painter, cardinal priest, rosh yeshiva),
  and 6 offered only class-like candidates and were left blank (associate professor, professor, docent, lecturer, municipal executive, military commander).
- **Only values with at least 20 uses were measured.** Generic classes with less
  use are not on the list.
