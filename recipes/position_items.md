# Recipe: modelling a political position item

A campaign's job is to model political power correctly in Wikidata. That is the
whole of the primary goal, and it is worth doing whether or not any consumer
notices. A secondary goal is that OpenSanctions can read the result, and it gets
one section, at the end, where it belongs.

The ordering is not decoration. It decides what you do when the two disagree:

- **The convention wins on Wikidata.** Measure it (`country_sweep.md` §10) and
  emit what it supports. Never mass-assert a shape to satisfy a consumer.
- **The gap becomes an upstream issue**, filed against `opensanctions` and named
  in the country's ledger row with an owner. It is not a licence to write wrong
  statements, and it is not a reason to leave the ledger row blank.

Reach for this at phase A of a sweep, before any roster, and again before minting
anything with `wd/create.py`. `wd/shape.py` is the checker;
`scripts/position_metadata.py --country <cc>` runs it.

## Measure over a curated cluster, never over the corpus

145,212 items carry `wdt:P31 = Q4164871`, and roughly 90,000 of them are bulk
municipal imports: 40,268 French municipal councillors, 40,133 French mayors,
3,148 Romanian mayors, 1,646 German ones. `Q83307` minister has 736. So any
percentage taken over "all position items" is a statement about French communes.

Every figure below is measured over the **archetype cluster** for the shape in
question — the items with `P279 = <the class>` — which is what §10 means by a
well-curated cluster. Sample sizes are given so you can weigh them.

## The shape

Wikidata answers this itself: `Q4164871`'s `P1963` "properties for this type"
names **`P1308`, `P2098`, `P2389`, `P571`, `P17`**. In practice, measured over the
5,211-item minister cluster (`P279 = Q83307`):

| property | share | reading |
|---|---:|---|
| `P279` subclass of | 100% | the kind of office — always present, and load-bearing |
| `P1001` applies to jurisdiction | 94.4% | the polity governed |
| `P361` part of | 92.6% | the body the seat sits in |
| `P17` country | 81.6% | the sovereign state |
| `P2389` organization directed | 32.9% | the ministry or agency the office runs |
| `P571` inception | 8.5% | |
| `P576` abolished | 4.7% | |
| `P1308` position holder | 6.8% | 47–50% on head-of-state and head-of-government items |
| `P1365`/`P1366` replaces / replaced by | 2.4% / 2.9% | concentrated where offices are renamed |
| `en` label / `en` description | 97.3% / 93.0% | |

Two properties to leave alone. **`P3831` "object has role" is a non-property
here** — 0 of 145,212 position items carry it as a main statement; its real use is
as a qualifier on `P1308` marking an acting holder. **`P2388` belongs on the
organisation, not the office** — 29 of 145,212. `mul` labels are effectively
unused: 24 of the 5,211 ministers.

### `P31` is a metaclass, and `Q4164871` is not the modal one

Of the 5,211 items with `P279 = Q83307` minister, the `P31` breakdown is
**`Q294414` public office 4,428 (85%)**, `Q4164871` position 738 (14.2%), none 74.
`Q11696` President of the United States uses `Q17279032` elective office. Across
the seven political archetypes `Q294414` beats `Q4164871` 5,509 : 2,409.

All of them reach `Q4164871` through `P279`, so the requirement is *"a `P31` to a
position metaclass whose closure reaches `Q4164871`"* — not the literal QID. A
check demanding `P31 = Q4164871` misses about **17,800 offices people actually
hold**. `wd/shape.py:POSITION_METACLASSES` lists the six in live use.

For minting, `wd/create.py` writes `P31 = Q4164871` + `P279 = <archetype>` +
`P17` + `P1001`. That matches the best-curated items and the second-largest
cluster: defensible, just not modal. Do not "fix" existing `Q294414` items toward it.

## What a position is not

Wikidata states the boundary on `Q4164871` itself, as `P1889 different from`:
**`Q480319` title of authority, `Q12737077` occupation, `Q28640` profession,
`Q11348` function, `Q192581` job activity.** Add ranks (`Q4189293`, `Q56019`,
`Q4226220`) and organisations (`Q43229`, and bodies like `Q495430` general staff).

**The closure cannot answer this question.** Within six hops both `Q28640`
profession and `Q4189293` rank reach `Q4164871`, so a wood-carving trade
(`Q258874` dievdirbys) and a naval rank (`Q565077` flotilla admiral) both read as
positions. `wd/shape.py` tests the item's **declared** `P31`/`P279` against the
list above, and fires only on positive evidence that the item is something else —
`Q138024519` "Roman Catholic episcopal title" declares no metaclass and no known
kind, yet its own `P279` reaches `Q4164871`, and flagging Lithuania's bishoprics
off that was a false positive. Under-reporting beats proposing a wrong retype.

The working distinctions:

- **A rank is not an office.** `Q565077` flotilla admiral carries `P1611` NATO
  code, `P3729`/`P3730` next lower/higher rank, `P8766` insignia — and **eight
  `P17` values** (FI, BE, BG, SE, DE, DK, LV, LT), because `P17` on a rank means
  "used by these countries". Another reason never to read `P17` uniformly.
- **"Judge" in the abstract is an occupation; a named judgeship on a named court
  is a position.** `Q16533` judge carries ISCO/SOC/ESCO codes; `Q843020` justice of
  the Supreme Court of Canada carries `P17`, `P1001`, `P361` and `P571`. The
  community is comfortable double-typing an apex judgeship as position *and*
  occupation — both `Q843020` and `Q11147` do.
- **A body is not a seat in it.** `Q12663357` "Defence Staff (Lithuania)" is
  `P31 = Q495430` general staff. The office is `Chief of the Defence Staff`.
- **An office and the list of its holders are different items.** A position typed
  `Q13406463` Wikimedia list article is two things at once and every consumer has
  to guess. `Q12663218` Speaker of the Seimas is one today.

## Under-modelling: "position" and nothing else

The commonest real defect. An item declaring only a metaclass asserts that it is
an office and never says which kind — so it cannot be grouped, queried by kind or
inherited from, and everything downstream guesses. Measured:

- **Iran: 54 of 323 scoped items**, on offices at the centre of the state —
  `Q2660216` Vice President of Iran (43 holders), `Q20987826` Interior Minister
  (15), `Q107041759` Member of the Guardian Council (13).
- **Lithuania: 5 of 221**, including `Q106624287` Chief of the Defence Staff.

Across both, 212 of 221 and 257 of 323 items are otherwise soundly modelled — the
defect is concentrated, not endemic.

The fix is a `P279` from the table below. It is additive and it is cheap.

## Choosing the `P279`

`wd/create.py:ARCHETYPES` is the authority — each parent was measured off a real
cluster, and `scripts/position_metadata.py --check-spec` fails if this table and
that dict drift apart.

| archetype | `P279` parent | notes |
|---|---|---|
| `minister` | `Q83307` minister | 5,211-item cluster; the reference shape |
| `head_of_state` | `Q48352` head of state | 346 items; `P1308` on 47% |
| `head_of_government` | `Q2285706` head of government | 343 items |
| `legislator` | `Q4175034` legislator | see also `Q486839` member of parliament, 565 items |
| `judge` | `Q16533` judge | an ordinary judgeship |
| `supreme_judge` | `Q117826617` supreme court judge | 59-item cluster; `Q55736868` for a national apex court |
| `governor` | `Q132050` governor | 589 items; 93% scope `P1001` narrower than `P17` |
| `provincial_governor` | `Q98786082` emir of province | the Gulf shape; an Amir, not a director |
| `mayor` | `Q30185` mayor | 1,193 items; 97% scope `P1001` to the municipality |
| `ambassador` | `Q121998` ambassador | generic; prefer the bilateral pair below |
| `bilateral_ambassador` | `Q121998` ambassador | in practice **two** parents — see *Diplomatic posts* |
| `agency_head` | `Q1162163` director | |
| `ruler` | `Q166382` emir | measured off the fourteen emirate items |
| `heir_apparent` | `Q207293` crown prince | names no body: the heir belongs to the emirate |
| `deputy_ruler` | `Q3250324` deputy | the two existing items disagree; this is the less wrong |

Pick the parent that **describes the office**. Where no archetype fits, §10 says
measure before minting: a cheap CirrusSearch sweep of `haswbstatement:P31=Q4164871
<office name>` plus a `P279` tally answers most cases in one pass. Measured that
way: parliamentary speakerships are `Q1758037` speaker (84 of 96 typed), chief
justiceships `Q3188089` chief justice (88 of 96), and "President of the Supreme
Court" is **split** — `Q117826617` 4, `Q13554447` chief judge 4, `Q16474031` court
president 3 — which per §10 rule 3 means do not mass-assert a side.

## Jurisdiction

- **National office: `P17` and `P1001`, both naming the country.** 91.8% of
  ministerial items carrying both duplicate it. Redundant-looking, and it is the
  convention.
- **Sub-national office: `P17` = the sovereign state, `P1001` = the polity
  governed.** 97.2% for mayors, 93.1% for governors; and the `P1001` target is the
  municipality or region rather than a country in 96–97% of those.
- **An office scoped only to a historical polity resolves to no country, and that
  is correct.** The Grand Duchy of Lithuania, the Polish–Lithuanian Commonwealth
  and the Lithuanian SSR are complete answers. Never backfill the modern republic
  onto one; that is a wrong statement in the lane that looks safest.

### Diplomatic posts

Measured over **5,206 actual bilateral post items** — not the class layer:

| | share |
|---|---:|
| `P17` = the **receiving** state | 86.4% of 4,958 resolvable |
| `P137` = the **sending** state | 95.8% of 4,053 resolvable |
| `P2389` = the embassy | 74.9% |
| `P1001` present at all | 29.6%, and it copies the *receiver* 86.5% of the time |

So: `P17` receiver, `P137` sender, `P2389` embassy, and **do not assert `P1001`** —
sender-in-`P1001` is a 2.5% minority. `P279` carries two parents, one per end:
`Q29645880` "ambassador of a country" for the sender class and `Q29645886`
"ambassador to a country" for the receiver class.

Two class layers are easy to confuse, and the confusion inverts the answer: among
the 207 `Q29645880` subclasses `P17` is the **sender** (205/207); among the 264
`Q29645886` subclasses it is the **receiver** (262/264). A quoted "262/264" is
about the receiver layer only.

## One office or several

Practice is **one item per name or era, chained**, not one item with dated
qualifiers. The Azerbaijani education portfolio is the model chain: each item
carries `P31 = Q294414`, `P279 = Q83307`, `P17`, `P361` the cabinet, a shared
`P2354` pointing at the same roster article, its own `P571`/`P576` — and one
item's `P576` is exactly the next one's `P571`. Splits and merges are modelled as
multi-valued `P1365`/`P1366`, so `Q107703906` lists both its predecessors.

`P748` appointed by belongs on the era items. A minority idiom adds dated
`P1448` official names on a single item (`Q6865764`, Ireland) — useful for label
matching, and it does not replace the chain.

**Two items competing for the same era is a merge, not a backfill.** Adding
metadata to the empty twin entrenches the duplicate; put the merge on the surgical
list, where a human decides.

## Reading types correctly

Consumer-independent facts about Wikidata that will bite any checker:

- **`wdt:` returns best-rank values only** — for every property. One preferred
  `P31` hides all the normal-rank ones and a deprecated one vanishes entirely.
  `Q12251224` reads as only a crown prince because its `Q4164871` sits behind a
  preferred value; `Q68081922` reads as untyped because its `P31` is deprecated.
  Use `p:P31/ps:P31`, or read claims — `wd.api.claim_qids` does.
- **Read `P31` and `P279` together, at every level.**
  `nomenklatura/wikidata/model.py:_type_props` follows both, treats the item's own
  QID as one of its types, skips ended claims and caps the path at 6. A closure
  seeded from `P31` alone reports correctly-shaped positions as untyped — that
  mistake produced two confident false findings in one afternoon: that Lithuania's
  60 mayoralties were mis-typed, and that Qatar's 28 ambassadorships had been
  minted with a bad parent. Both were wrong.
- **Never read an item's own types through the HTTP cache.** They are state this
  engine's batches change, exactly as `wd/campaign.py:STATE_MAX_AGE = 0` exists
  for. `wd/shape.py:type_closure` fetches audited items with `max_age=0` and caches
  only the stable ancestor classes; before that split, a run after its own batch
  read `Q131824331` as untyped and re-proposed a `P279` the item already carried.

## Exemplars worth reading in full

- **`Q21503673` Minister of Foreign Affairs of Romania** — the shape a roster
  campaign should aim at: everything jurisdictional in six statements, the roster
  linked by `P2354`, and the whole succession as 125 dated `P1308` values.
- **`Q11696` President of the United States** — the maximal head-of-state shape:
  `P2098` deputy, `P2097` term length with a dated override, `P748` appointed by,
  `P263` official residence, `P2715` elected in.
- **`Q843020` justice of the Supreme Court of Canada** — an apex judgeship, and an
  example of legitimate position/occupation double-typing.
- **`Q326552` United States Ambassador to Germany** — the bilateral shape, both
  `P279` parents, `P17` receiver and `P137` sender.

## Making it legible to OpenSanctions

Secondary, and never a reason to change the model. `zavod/zavod/shed/wikidata/`
skips a position when it cannot resolve a country; when the `P31`/`P279` closure
misses `POSITION_BASICS` — `Q4164871`, `Q29645880`, `Q29645886`, `Q707492`; when
the closure hits `EXCLUDE_TYPES` without also hitting an allowed class
(`Q114962596` historical position, `Q193622` order, `Q60754876` grade of an order,
`Q618779` award, `Q13424289` honorary title, `Q4240305` cross, `Q120560` minor
basilica, `Q2977` cathedral, `Q3320743` title of honor, `Q42603` priest,
`Q11773926` ecclesiastical occupation, `Q63187345` religious occupation); or when
a `P576` predates `1990-12-26`. Allowed classes include the explicit rescues
`Q45722` cardinal, `Q1729113` cardinal-bishop, `Q2033341` cardinal priest,
`Q2361374` cardinal-deacon, `Q19808790` Episcopal Co-Prince.

Country resolution walks `P17`/`P27` **first** and, if either yields anything,
never reads `P1001`/`P1376`/`P361`/`P749`/`P159`/`P2389` — so adding `P1001`
beside a correct `P17` changes nothing. Claims pointing at a historical polity
contribute nothing (`Q3024240` historical country, `Q19953632` former
administrative territorial entity, `Q839954` archeological site), and neither do
places spanning many states (`Q234` Flanders, `Q210718` Asia, `Q4412` West Africa,
`Q52062` Nordic countries, `Q7785` Commonwealth of Nations, `Q4264` Mercosur,
`Q18348382` Colony of New South Wales, `Q2334526` Province of North Carolina,
`Q1070529` Colony of Virginia).

Three things worth knowing and not acting on:

- **`role.pep` is an internal sentinel.** It is read once to seed a default and
  discarded before any entity is emitted; nothing carries it. **Never write it, and
  never choose a `P279` in order to trip it** — that is how you corrupt data while
  appearing to improve it. Several parents leave the default off while being the
  honest choice: `Q16533` judge, `Q4175034` legislator, `Q121998` ambassador,
  `Q1162163` director, `Q14212` prime minister, `Q109862464` lord mayor,
  `Q836971` party secretary, `Q116182667` diplomat, `Q303618` diplomatic rank.
  Each is a gap to file upstream.
- **A position with no holder is never emitted.** The reader reaches positions
  through people's `P39`, so metadata makes an item findable and a roster lane
  makes it found. 83 of Lithuania's 221 items have no holder.
- **Some distinctions no property can express.** Archbishops and nuncios are
  religious PEPs and ordinary bishops are not; both reach `Q17279032` identically,
  and a review database decides. Close such rows `absent` by policy.

**`MUNI_COUNTRIES` is irrelevant here.** It gates municipal positions on a country
allowlist that is a staged rollout heading for every country, so a mayoralty
outside it is complete and correct with nothing to fix and nothing to file.
