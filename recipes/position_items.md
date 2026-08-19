# Recipe: what a position item needs to be found

A position item that the OpenSanctions PEP build cannot see is not a small
problem to fix later. Every P39 statement a campaign writes onto it produces
nothing, the coverage ledger reports the institution as covered, and the defect
is invisible from inside the campaign that caused it. Reach for this file at
**phase A of a sweep**, beside `institutions.md`, and again before minting
anything with `wd/create.py`.

The measured case: of 230 position items scoped to Lithuania, **136 carry enough
metadata to stand on their own and 87 fail at least one gate** — yet only **65 are
in OpenSanctions today**. The gap between 136 and 65 is the finding in the next
section: metadata is necessary and not sufficient. Nobody had looked, because a
sweep scoped from a roster outward never asks.

## A position with no holder is never seen

Measured over the same 230 items: **every position in OpenSanctions has at least
one P39 holder. There are no exceptions** — the zero-holder column is empty on
both sides of the ledger. `wd_peps` reaches positions *through people*, so a
perfectly-shaped item nobody holds is never emitted at all. 68 of the 78
Lithuanian items that pass every gate and are still absent have no holders.

This is the reason a sweep has two halves and neither works alone. Fixing an
item's metadata makes it *capable* of being found; a roster lane is what makes it
found. Report them as one number per institution or the ledger lies in whichever
direction the campaign happened to work.

A holder also has to survive `human.py`'s own gates — `Q5` in the closure and
plausibility windows on `P569`/`P570` — which is why `Deputy to the Sejm of the
Polish–Lithuanian Commonwealth` is absent despite 3,940 of them.

## Every root class, enumerated

`wd/discover.py` is the authority and carries the source line for each set; this
is the same content in a form you can check an item against by eye. Counts as of
2026-08-19: **34** subtypes, of which **27** set the PEP
default and **7** only contribute topics.

**`POSITION_BASICS`** — one of these must be in the closure or the item is never
a candidate (4):
`Q4164871` position · `Q29645880` ambassador of a country · `Q29645886`
ambassador to a country · `Q707492` military chief of staff.

**Subtypes that contribute topics but leave the default at not-PEP** (7) —
each is a trap, because the item looks typed and still drops:
`Q16533` judge · `Q4175034` legislator · `Q109862464` lord mayor · `Q14212` prime
minister · `Q836971` party secretary · `Q116182667` diplomat · `Q303618`
diplomatic rank.

`Q14212` "prime minister" is the sharpest of these: it contributes `gov.head` and
`gov.executive` but does not set the default, so a premiership typed only that way
defaults to non-PEP. Pair it with `Q2285706` head of government, which does — and
report the asymmetry rather than treating `Q14212` as the wrong parent.

**`EXCLUDE_TYPES`** — silent exclusion, unless `ALLOW_TYPES` also matches
(12):
`Q114962596` historical position · `Q193622` order · `Q60754876` grade of an
order · `Q618779` award · `Q13424289` honorary title · `Q4240305` cross ·
`Q120560` minor basilica · `Q2977` cathedral · `Q3320743` title of honor ·
`Q42603` priest · `Q11773926` ecclesiastical occupation · `Q63187345` religious
occupation.

**`ALLOW_TYPES` beyond the subtypes** — the explicit rescues (5):
`Q45722` cardinal · `Q1729113` cardinal-bishop · `Q2033341` cardinal priest ·
`Q2361374` cardinal-deacon · `Q19808790` Episcopal Co-Prince. Every `SUB_TYPES`
key is also allowed, which is what lifts an elected bishopric out of exclusion.

None of these sets should ever be written onto an item as a topic. They are read.

**Historical-polity types** — a country claim pointing at one of these
contributes nothing (3): `Q3024240` historical country ·
`Q19953632` former administrative territorial entity · `Q839954` archeological
site. `rigour.territories` answers first where it knows the QID.

**`SKIP_PLACES`** — places whose `P17` names every state they span, so they
resolve to no country at all (8): `Q234` Flanders · `Q210718`
Asia · `Q4412` West Africa · `Q52062` Nordic countries · `Q7785` Commonwealth of
Nations · `Q4264` Mercosur · `Q18348382` Colony of New South Wales · `Q2334526`
Province of North Carolina · `Q1070529` Colony of Virginia.

**`MUNI_COUNTRIES`** — the only countries where a `gov.muni` position survives
(28): `au` · `be` · `br` · `by` · `ca` · `co` · `cz` · `es` · `fr` · `gb` · `gt` · `hu` · `id` · `is` · `it` · `ke` · `kr` · `mx` · `ni` · `nl` · `pl` · `ro` · `ru` · `sk` · `ua` · `us` · `ve` · `za`.
Everywhere else a correctly-typed mayoralty is dropped, and the fix is an issue
against `opensanctions`, not a change to the item.

**`POSITION_ABOLISHED_CUTOFF`** — `1990-12-26`. A `P576` before it drops the
position; living former holders of an office abolished after it stay PEPs.

## Two audiences, and which one wins

A position item answers to Wikidata's conventions and to `zavod`'s reader, and
they are not the same thing. Where they conflict:

- **The convention wins on Wikidata.** Measure it (`country_sweep.md` §10) and
  emit what it supports. Never mass-assert a shape to satisfy a consumer.
- **The gap becomes an upstream issue**, filed against `opensanctions`, named in
  the country's ledger row with an owner. It is not a licence to write wrong
  statements, and it is not a reason to leave the ledger row blank.

The canonical instance is the outbound ambassadorship — see *Anti-patterns*.

## The five gates

Ported in `wd/discover.py`, which is a reading of someone else's code and will
drift, so every constant there carries its source line. Verified against
`zavod/zavod/shed/wikidata/` and calibrated against 230 live lookups.

| # | gate | source | effect when it fails |
|---|---|---|---|
| 1 | `P31`/`P279` closure intersects `POSITION_BASICS` — `Q4164871` position, `Q29645880` ambassador of a country, `Q29645886` ambassador to a country, `Q707492` military chief of staff | `position.py:20`, tested `:161-166` | never becomes a candidate |
| 2 | a country resolves | `country.py:_crawl_item_countries`, gate `position.py:227` | `return None` — the item does not exist downstream |
| 3 | the closure sets the **PEP default** (see below) | `position.py:26-80`, read `:278` | built, then dropped as non-PEP unless a reviewer rescues it |
| 4 | no `EXCLUDE_TYPES` ancestor, and no `P576` before `1990-12-26` | `position.py:88-104`, `:84`, gate `:234` | silently excluded |
| 5 | a `gov.muni` position's country is in `MUNI_COUNTRIES` | `position.py:116`, gate `:304` | `return None` |

**`ALLOW_TYPES` beats `EXCLUDE_TYPES`** (`position.py:107-114`), and every
`SUB_TYPES` key is in it — so one pep-conferring ancestor lifts an item out of
exclusion. This is why the Lithuanian bishoprics pass the type gates: a bishop is
elected, so the closure reaches `Q17279032`.

### Gate 2 short-circuits, and that is the subtle one

`_crawl_item_countries` reads `P17`/`P27` first and, **if either yields any
country, never consults** `P1001`, `P1376`, `P361`, `P749`, `P159`, `P2389`. So
adding `P1001` beside a correct `P17` changes nothing at all. It also recurses:
`P1001 = Q216` (Vilnius) resolves to `lt` through the city's own `P17`, which is
why mayoralties pass gate 2 without naming a country directly.

Claims pointing at a **historical polity** contribute nothing
(`country.py:is_historical_country`), so an office scoped only to the Soviet
Union, the Grand Duchy or the Polish–Lithuanian Commonwealth correctly resolves
to no country. That is an `absent` ledger row, not a backfill.

### `role.pep` is a sentinel, and you never write it

It looks like a topic in `SUB_TYPES` and it is not one. `position.py:278` reads it
once to compute `default_is_pep`, then **discards it at `:284`, before
`position.add("topics", …)`, and again at `:301`.** No Position entity carries it;
the topics that survive are the `gov.*`, `pol.*` and `role.diplo` ones. Lithuania's
Minister of Finance comes back `['gov.executive', 'gov.national']`, its President
`['gov.national', 'gov.head']`, the Archbishop of Vilnius `['gov.religion']`.

So "does this parent confer `role.pep`" is the wrong question asked in the wrong
vocabulary. The right one is **which side of the PEP default does this office
start on**, because a reviewer decides the rest. `wd/discover.py` calls it
`Verdict.pep_default`, keeps the marker in `PEP_SENTINEL`, and strips it from its
own output so it cannot be copied onto an item by accident.

**Never choose a `P279` in order to trip the sentinel.** Pick the parent that
describes the office; the default follows from it. Typing a district judgeship as
`Q117826617` supreme court judge would flip the default and corrupt the data to do
it — and the corrupted item then looks correct to everything downstream. Where the
honest parent does not set the default, that is a gap to report against
`opensanctions`, not something to route around in the data.

### Gate 3 makes `P279` load-bearing, not decorative

`P31 = Q4164871` is the same on every position item; **the archetype narrows it
with `P279`**, and that choice decides whether the item confers PEP status:

| you want | `P279` | topics, and the PEP default |
|---|---|---|
| apex-court judge | `Q117826617` supreme court judge | `role.pep`, `gov.judicial` |
| any other judge | `Q16533` judge | `gov.judicial` — **default is not PEP** |
| legislator | `Q486839` member of parliament | `role.pep`, `gov.legislative` |
| legislator, generic | `Q4175034` legislator | `gov.legislative` — **default is not PEP** |
| council member | `Q708492` council member | `role.pep` (via `Q17279032`) |
| mayor | `Q30185` mayor | `role.pep`, `gov.executive`, `gov.muni` — then gate 5 kills it |
| outbound ambassador | `Q29645880` ambassador of a country | `role.pep`, `role.diplo` |
| inbound ambassador | `Q29645886` ambassador to a country | `role.pep`, `role.diplo` |
| ambassador, generic | `Q121998` ambassador | `role.diplo` only — **default is not PEP** |
| minister | `Q83307` minister | `role.pep`, `gov.executive` |
| deputy minister | `Q15966511` / `Q26204040` | `role.pep`, `gov.executive` |
| prosecutor general | `Q3368517` | `role.pep`, `gov.judicial` |
| deputy prosecutor general | `Q109607046` | `role.pep`, `gov.judicial` |
| central bank governor | `Q107363151` | `role.pep`, `gov.financial` |
| head of state / government | `Q48352` / `Q2285706` | `role.pep`, `gov.head` |
| party leader | `Q1553195` | `role.pep`, `pol.party` |
| military chief of staff | `Q707492` | `role.pep`, `gov.national`, `gov.security` |
| agency head | `Q1162163` director | **nothing** — needs a second parent to set the default |

Four rows of that table are traps that pass every other gate: `Q16533`,
`Q4175034`, `Q121998` and `Q1162163` all look like the obvious parent and leave the
default at not-PEP. `Q294414` "public office" is a fifth — it reaches `Q4164871`,
so gate 1 passes, and it contributes nothing *on its own*. In each case the parent
may still be the honest one; the answer is an upstream issue, not a different
parent.

**Read the closure over `P31` and `P279` together, or you will invent defects
that are not there.** `nomenklatura/wikidata/model.py:_type_props` follows both
properties at every level, treats the item's own QID as one of its types, skips
ended claims, and caps the path at 6. A closure seeded from `P31` alone reports
every correctly-shaped position as untyped — which is how a first draft of
`wd/discover.py` concluded that Lithuania's 60 mayoralties were mis-typed
`Q294414` and that Qatar's 28 ambassadorships had been minted with a
non-conferring parent. Both were wrong: the mayoralties reach `Q30185` through
their `P279` and fail only gate 5, and `Q38717123` "ambassador of Qatar" is
correctly attached to `Q29645880`, as are 207 other sender classes.

## Required, recommended, optional

**Required** — an item missing any of these is not discoverable:

- `P31 = Q4164871` (or a class reaching it).
- a `P279` from the table above that confers `role.pep`.
- a country path: `P17` for a national office; for a sub-national one, `P1001`
  naming the jurisdiction is enough, because gate 2 recurses.

**Recommended** — improves the record, not required by the gates:

- `P1001` where the office is scoped narrower than the country. `zavod` also
  reads it as `subnationalArea` when the target is not a country
  (`position.py:198-202`).
- `P361` the body the office belongs to; `P2389` where it *directs* one. Both are
  gate-2 fallbacks and both are how a multilateral post picks up its registry
  pseudo-country (`position.py:180`).
- an `en` label, or a `mul` one. `zavod` translates the next-best language rather
  than failing, but a machine translation is what then names the position.

**Optional** — `P571` inception, `P576` abolition. `zavod` falls back to holders'
`P580`/`P582` (`position.py:210-217`), so absence costs little. 219 of
Lithuania's 230 items have no `P571` and it harms nothing.

**`P576` is a kill-switch, not metadata.** A date before `1990-12-26` drops the
position outright. Add one only when the office genuinely ended.

## What no property can express

Some distinctions live in the review database (`zavod.stateful.positions
.categorise`), which no item can reach and which this repo cannot read. Do not
try to fix these with a `P279`:

- **Archbishops and nuncios are religious PEPs; ordinary bishops are not.** Both
  reach `Q17279032` identically, so the type layer cannot separate them. Measured
  in Lithuania: the Archbishops of Vilnius and Kaunas carry `gov.religion`, the
  Apostolic Nuncio `role.diplo`, and the Bishops of Telšiai, Panevėžys and the
  Military Ordinariate are absent — correctly. Close such rows `absent` by
  policy, not as a defect.
- A reviewer may mark any position PEP-conferring or not. When `wd/discover.py`
  says self-sufficient and OpenSanctions disagrees, suspect the review layer
  before suspecting the port — then check.

## Anti-patterns

- **Do not repair an outbound ambassadorship toward the sender.** `P17` on one is
  the **receiving** state (262/264 of the curated cluster; 74/77 in Iran), the
  sender sits in `P137`, and `zavod` does not read `P137`
  (opensanctions/opensanctions#5475). Because gate 2 short-circuits, such a post
  resolves to the *receiver* and `P1001 = <sender>` beside it is inert. Adding
  the sender's `P17` is a large batch of wrong statements in the lane that looks
  safest. Leave it, and carry the gap as the upstream issue.
- **Do not test types with `wdt:P31`.** One preferred value hides the normal-rank
  ones and a deprecated one vanishes. `Q12251224` reads as only a crown prince
  because its `Q4164871` sits behind a preferred value; `Q68081922` reads as
  untyped because its `P31` is deprecated. A "is this a position?" closure built
  on truthy values rejects real positions. Use `p:P31/ps:P31`, or read claims —
  `wd.api.claim_qids` does.
- **Do not assume a `P31` that reaches `Q4164871` is enough.** `Q294414` does,
  and confers nothing. Gate 1 passing says very little.
- **Do not treat a byproduct list as a fix.** An item minted with a
  non-conferring parent is worse than no item: it looks done.

## Verifying

```
/Users/pudo/.python/wrangle/bin/python scripts/position_metadata.py --country lt
```

`wd/discover.py:verify_all` scores a whole country in one pass and answers
locally, which matters because the live API answers on the dataset's rebuild
cadence and so cannot verify its own fixes.

Calibrate rather than trust: `scripts/position_metadata.py --calibrate` checks
each verdict against a live `yente-cli fetch`. Keep the calibration set beside the
campaign's verdicts; it is the only regression net this reader has, and it is what
caught the `P31`-only closure bug above — the signature was a large, suspiciously
uniform group of items the port called broken and OpenSanctions carried anyway.

Read a disagreement in this order: **no holders** (68 of Lithuania's 78), then the
**review layer** (the three bishops), then a **port bug**. Only the third is
yours to fix, and it is the least likely.
