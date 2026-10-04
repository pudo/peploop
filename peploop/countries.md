# Running a country

The loop records who holds office **now**. Every choice below follows from
that: the categories seeded are the current era's, not the country's whole
political past; a tenure that ended a generation ago is skipped by rule
(`policy.P39_MAX_ENDED_YEARS`) rather than reconciled with care; when an office
has been renamed, the item under its current name is the one that matters, and
the tenures under the old names are mostly history the run should not chase.
The scope gate at fetch (`scope.py`) makes the tail cheap -- a dead
19th-century president costs one item read and no article, no extraction --
so a category may be seeded wide, but nothing is gained by seeding wide *into
the past*.

This is the procedure, with the measurements that come before it and the
checkpoints inside it. `design.md` says what each stage is; `positions.md` says
how the office resolver works. A session starting a country reads this and
`seeds/<cc>.yml` of the last country run, and nothing else.

## 1. Before seeding: three measurements

All read-only, all from `peploop`'s own modules so the HTTP cache is shared.

**The wiki's category tree.** Find the country's politician root on its own
wiki (`Políticos de Colombia`, `Slovenski politiki`) *and* on en.wikipedia --
which of the two is the regular one is a property of the country, not a rule:
Slovenia's and Colombia's own wikis carry the tiers, Cuba's carries one flat
bag of 1902-1959 secretaries, Spanish Cortes deputies and dissidents while the
English tree has the portfolios and the 2020 governors. List each root's
subcategories with sizes, then the parents of each tier: heads of state and government, the
cabinet, each legislative chamber, the apex courts and control bodies, the
central bank, governors and mayors, ambassadors, the military and police
leadership, party leaders. `prop=categoryinfo` gives pages and subcategory
counts; `list=categorymembers&cmtype=subcat` walks a level. What to look for:
which parents are *pure containers* (one page, twenty subcategories) and need
`depth: 2`; which subcategories are **per period** (`Senadores de Colombia
2022-2026`) or **per century**, because those are how the current era is
chosen; which are a trap (`Militares de Colombia` is mostly conquistadors;
`Presidentes de X` at depth 4 grows fourfold with family members); and which
carry an **eponymous child** -- a `Fidel Castro` or `Álvaro Uribe` category of
family, films and places one level under the presidents, the party or the
legislature -- which is what `depth: 0` is for.

```python
from peploop import http; import json
API = "https://es.wikipedia.org/w/api.php"
r = json.loads(http.get_text(API, params={"action": "query", "generator": "categorymembers",
    "gcmtitle": "Categoría:Ministros_de_Colombia", "gcmtype": "subcat", "gcmlimit": 200,
    "prop": "categoryinfo", "format": "json"}, max_age=3600, timeout=60))
for p in r["query"]["pages"].values():
    print(p["title"], p.get("categoryinfo", {}).get("pages"), p.get("categoryinfo", {}).get("subcats"))
```

**Wikidata's office set.** The descent count (`?pos p:P31/ps:P31/wdt:P279*
wd:Q4164871` with the `P17`/`P1001` union on the state) says whether this is a
Czechia-sized country (194) or a Spain-sized one (13,000, mostly
municipalities); the holder-ranked list of those items, read whole, says two
things the run needs to know before it starts: **which tiers have no item at
all** (Colombia: no magistrate of any apex court, four outbound
ambassadorships against 72 categories -- those mentions will end in the
creation queue the mint stage works, which is not a failure, and a tier with
no item is also a `census/<cc>.yml` entry), and **which offices have two
items competing for one era** (Colombia: the presidency of each chamber, one
ministry). Two items for one era is a merge decision and a human gate; the
run does not write onto the unused twin, and the holder signal is what keeps
the reconciler off it. Check after the run that nothing landed there.

```python
from peploop import wikidata
rows = wikidata.sparql("""SELECT ?pos ?posLabel (COUNT(DISTINCT ?st) AS ?n) WHERE {
  ?pos p:P31/ps:P31/wdt:P279* wd:Q4164871 .
  { ?pos wdt:P17 wd:Q739 } UNION { ?pos wdt:P1001 wd:Q739 } UNION { ?pos wdt:P1001/wdt:P17 wd:Q739 }
  OPTIONAL { ?h p:P39 ?st . ?st ps:P39 ?pos }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,es". }
} GROUP BY ?pos ?posLabel ORDER BY DESC(?n)""")
```

Count *distinct statements*, as above. A `COUNT(?h)` over that `UNION` counts a
holder once per branch that matches, and a state that is its own `P17` matches
two or three, so the first version of this query read Colombia's Senate as 903
holders for 382 statements. The list also contains what the descent reaches
and the run does not want: every *inbound* ambassadorship (35 of Cuba's 98
items), church offices, the odd order of merit. Read past them.

**PetScan counts per candidate entry**, with the running distinct total:
`wikipedia.seed_category(category, lang, depth)` returns `(title, qid)` pairs.
The total is the cost estimate (below) and the marginal count of each entry
says whether it earns its place: `Políticos_de_Colombia` at depth 3 added 294
people to 2,600 already reached by tier, nearly all history, and was left out.

## 2. The seed file

`seeds/<cc>.yml`, one PetScan query per entry: `category`, `lang`, optional
`depth` (default 1). OpenSanctions' `wd_categories.yml` (`country: <cc>`
entries) is the starting list and never the whole of it: it names the tiers
OpenSanctions has a spec for, and its retirements are OpenSanctions' reasons
(a category whose members are born before 1920 is retired *there*; here the
scope gate handles that at fetch). The tiers to cover are the ones in
`recipes/institutions.md`; the shape is `seeds/si.yml`'s: a comment block
saying where the entries came from and what was left out, then the entries by
tier, **every one commented with its measured size**, depth 1 except pure
containers, `depth: 0` where the only subcategory is an eponymous one. Where
the wiki has per-period or per-century subcategories, seed the current era's;
where it has a `carteras desaparecidas` tier, leave it out. Seed the English
tree at whatever depth *its* shape earns: one level where the country's own
wiki carries the tiers, the portfolio and governor containers where it is the
only wiki that has them.

## 3. The stages, in order

From the repository root, key sourced (`set -a && source .envrc && set +a`),
interpreter `.venv/bin/python -m peploop.cli`, `--country <cc>` on every
command that takes it.

```
seed --file peploop/seeds/<cc>.yml --country <cc>
load-positions --country <cc>                  # descent, usage and citizen lanes; additive
fetch --country <cc> --limit N --threads 8     # items, the scope gate, then every sitelinked article
extract --country <cc> --limit N --threads 4   # one request per person, Sonnet
position-signals --country <cc> --skip-counts  # scope qualifiers read the item table: after fetch
position-signals --country <cc> --local-holders    # this state's holder count per office
reconcile --country <cc> --limit N --threads 8 # one request per office mention
mint-categorize --country <cc>                 # cluster the misses and the census into offices, Sonnet
mint-verify --country <cc>                     # one request per office that clears the floor, Opus; decides each
mint --country <cc> [--write]                  # dry by default; --write creates and feeds each item
mint-feed --country <cc>                       # the re-run: load, re-ask the attested mentions, re-propose
mint-report --country <cc> --out data/mint/<cc>.md   # funnel by rule, the skip list, cost
propose --country <cc> --limit N               # P39 rows appear only now
policy --country <cc> --dry-run                # the funnel
verify --country <cc> --limit N --threads 4    # one request per pending row, Opus; re-runs the policy
policy --country <cc>
apply --country <cc> --write --limit 3         # on the user's go
apply --country <cc> --write --follow          # the drain
```

Three things the command list does not say. `run` is fetch, extract and
propose in one pass and nothing else: it yields no `P39` until `reconcile` has
run, and it never runs the policy. `fetch` and `load-positions` are network
only and run side by side. `--limit` defaults are small on most commands (the
`propose`, `reconcile` and `verify` defaults are 100, 100 and 50 *people*);
pass the country's size. `position-signals` without `--local-holders` runs
`fill_counts` over the whole table unless `--skip-counts` is given, and those
four counts are whole-corpus numbers a new country does not change.

The mint stage sits between `reconcile` and `propose` because its input is the
reconciler's refusals and its output is items those refusals can now land on.
Write `census/<cc>.yml` before `mint-categorize`: the offices the country has
whether or not a seeded article named them, by institution class of
`recipes/institutions.md`, each with its body QID and, optionally, an
official source. An entry is a prompt for the offices nobody's article names
-- it puts the anchor and its body in front of categorize -- and not a second
channel of evidence: every office passes on one current holder, census or
not. Its bodies come from measurement (`research/position_items.md` §10 is
the template), never from memory; `census/cu.yml` is the first. A census
entry nobody's article attests is skipped, so the file says what must exist
and the seeds still decide what gets made. `mint --write` feeds each item as soon as it is created, so
`mint-feed` is not a step of the normal run: it is the re-run and the repair,
for a feed a crash or a propose failure cut short, and for the rows
`mint-verify` decided `found` -- an item that already existed -- which `mint`
does not select. Both are idempotent.
`audit candidate N --country <cc> --reason … --by <name>` skips a row after
the fact; there is no approve.

Every LLM stage is ledgered on content (prompt hash, article revisions,
rendering version), so re-running one after a prompt edit costs only what is
new, and re-running one that was interrupted costs nothing. Run the long ones
detached (`fetch`, `extract`, `reconcile`, `verify`) with an observer that
reports the tail of the log, the failure count and the token total; a
connection error or a `maxlag` wait is a retry, not a bug.

## 4. The checkpoints, and what to show at each

| after | show | then |
|---|---|---|
| `seed` | people per category, the distinct total | go on |
| `load-positions` | items loaded per lane; the duplicate pairs from §1 and which twin is used | go on |
| `extract` | `stats --country <cc>`: people per status (how many the scope gate discarded), token total | go on |
| `reconcile` | verdicts by kind; the creation queue (`resolution` rows with a null `qid`) by office title; where the incumbents' offices landed | go on |
| `mint-categorize` | candidates per institution class; the groups no office took (`office_unassigned`) and why | go on |
| `mint-verify` | `mint-report`: the funnel by rule, then every `guarded` row with its payload's labels and every `found` row with the item it names | first runs: **stop and show it** |
| `mint --write --limit 1` | the item on Wikidata; the feed line (attestations `retrieved`, reopened verdicts by kind); the `P39` rows `propose` made on it | first runs: **only on the user's go** |
| `mint --write` | created, found at the re-check, failed; a re-run creates nothing | go on to `propose` |
| `policy --dry-run` | the funnel, per property, rule by rule | **stop and show it** |
| `verify` | verdicts by kind; every refusal class read by the observer; doubtful `supported` rows listed | go on to `policy` |
| `apply --write --limit 3` | the three diffs | **only on the user's go** |
| the drain | batch ids, statements per property, people written | the audit |

Nothing is written to Wikidata and nothing is pushed to git without the user
asking. The funnel is the one place to stop unasked: a rule that fires on a
class the country's shape explains is fine, and a rule firing on a class
nobody predicted is a finding to report before any request is spent.

The two mint stops are development checkpoints, held while the stage is new
(Cuba, then one more country), not gates in the runtime: nothing in `mint`
waits on a human. Creating an item is the one write peploop cannot take back
by editing, so for those runs an observer reads the skips and the guarded rows
after `mint-verify`, and each class it finds wrong becomes a rule in
`mint.RULES` with a case in `check_mint` -- never a ruling on a row. Once the
stage has run clean on two countries, `mint-categorize`, `mint-verify` and
`mint --write` run back to back as one step, and what is shown is the funnel
number first (offices created and found against candidates), then the report.

The funnel's usual shape (Slovenia, 960 `P39` rows in): about 60% reach the
verifier; the rest fall to a medium-confidence placement, a missing start, a
tenure too old, a sibling spell, a generic item that wanted a scoping
qualifier. A class that falls for a reason the rules do not name becomes a
rule in `policy.py` with a case in `check_policy.py` before `verify` runs --
never a row to hand-check, never a "review later".

## 5. The audit

The audit is an observer agent over `psql` and the diffs; what it doubts it
takes out with `audit proposal --ids <file> --country <cc> --reason … --by
<name>`, never with a raw `UPDATE` -- a skip without its verdict is wiped by
the next `propose`. It reads `verification` joined to `proposal` for the country's
applied rows, opens
`https://www.wikidata.org/w/index.php?title=<qid>&diff=<applied_rev>&oldid=<base_rev>`
for a stratified sample (per property, per policy rule, per office), and
reports the `supported` verdicts it doubts, with the verifier's evidence and
its own reading of the article. Where to focus, always: the **incumbents** --
an open tenure on the right current item, with no end date invented -- and
the multi-term legislators, whose several spells must be several statements.
Then whatever §1 flagged for this country: the duplicate office pairs, the
tiers with no item, the renamed offices.

What a doubtful class becomes: a rule, with its case, and a re-run of the
policy; the rows already written are reverted by EditGroups batch if the class
is large and by hand if it is a few. peploop never reverts on its own.

## 6. Closing a country

- `check_neutral.TOKENS` gains the country's tokens (its name stem, the state
  QID, `<lang>.wikipedia`, its capital) and the check passes -- which is what
  finds anything of the country that crept into a rule or a prompt during the
  run.
- The country's entry in §7 is finished with its numbers.
- The memory file gets one line.

## 7. Countries run

**Czechia** (`seeds/cz.yml`, 2026-09). The pilot. 12 categories, 1,839 people
queued, 872 extracted and proposed; reconcile was never run as a country pass,
nothing was written. The wide `Čeští_politici` (6,397 members) stayed
commented out.

**Slovenia** (`seeds/si.yml`, 2026-09-22 to 09-29). 40 categories, 2,115
people, wide on purpose (state secretaries, both chambers, 101 mayoralties,
ambassadors, the catch-all). The first country written unsupervised: 960 `P39`
rows into the policy, 569 verified (516 `supported`, 21 `already-recorded`,
14 `wrong-item`, 9 `contradicted`, 7 `unsupported`, 2 `imprecise`), 554
statements on 488 items in EditGroups batches `930b9c352c`, `4a18bf5e03`,
`f61844d6d0`. Every refusal the observer read was sound. Soft spots: a
renamed ministry routed to the later-named item; pre-1994 municipal "mayors"
who were assembly presidents; 31 rows the user had accepted by hand in the
TUI, which the policy never re-judges.

**Colombia** (`seeds/co.yml`, 2026-09-30). The first country seeded for the
current era by rule. 50 categories, 2,400 people, 6,234 memberships; the scope
gate set 1,057 aside at fetch and 7 were not human, so 1,336 were extracted
(≈ $35) and 5,572 office mentions reconciled (≈ $25): 2,869 `same-office`,
2,519 `none` -- vice-ministers, magistrates, small-town mayors and councillors,
outbound ambassadors, the tiers Wikidata has no item for. Offices: 338 loaded,
206 Colombia's own; the used twin of each duplicate pair (`Q57541164`,
`Q110567947`, `Q110567641`) was the one the holder count chose, and the three
rows the reconciler still put on `Q29583126` the verifier refused as
already-recorded. The funnel: 1,945 `P39` in, 1,036 to the verifier; the new
`tenure_ended` rule took 569 (ends in the 1990s and 2000s), `contested` 103
(one spell dated two ways by two wikis, a day apart), `undated_tenure` 101.
Gender: every in-scope item already had `P21`, zero writes. Birth dates: 325
to the verifier, 161 `conflict` rows where the item disagrees with the article
(an export, not an edit). Verified 1,527 rows at ≈ $30: 1,480 passed, every
refusal read and sound. The audit of 75 passes plus every row dated on the
change of government found 9 doubts in four classes -- scheduled end dates on
ambassadors' infoboxes, stale "Incumbent" boxes, career spans written as one
tenure, the English announcement day taken over the Spanish swearing-in day
-- and three rules came out of it: `future_date` in the policy (3 rows), the
`termed` route in `apply` (9 rows), and three verifier rules for the prose
cases, shelved until the drain was done because a prompt edit re-keys every
verdict. The 14 doubted rows were skipped by hand under `audit:pudo`. Written on
2026-09-30: **1,454 statements on 850 items** -- 973 `P39` (139 of them open
tenures; Senate 292, Chamber 247, councillors of Bogotá 45, the governors and
ministers a handful each), 320 `P569`, 154 `P27`, 7 `P570` -- in EditGroups
batches `8bce22eb29` (the first three people), `0de728e012` (the drain, 843
people), `4e234c5722` (four people retried after a query-service lag). Eleven
accepted rows closed at the pre-flight: 8 `apply:termed`, 3 `apply:conflict`.
No written statement absorbed two spells. Cost, all stages: about $90.

Colombia was the second country through the mint stage (2026-10-02), without
a census: 2,169 unplaced groups, 440 with no current holder near them, 990
candidates from 22 Sonnet requests. Two created -- Justice of the
Constitutional Court `Q141621249` and its President `Q141621254`, the seats
the reconciler had refused as `body-not-seat` against the court -- and 23
found already on Wikidata, which put 10 more mentions on an office. Skipped
mostly for no archetype (350: vice-ministers, directors), one holder (266:
no census, so a one-seat office needs two) and ambassadorships (93). Three
mayoralties had been guarded scoped to the state or the department their
town sits in, because categorize is offered no municipalities; an archetype
now names the level it governs and the guard checks it, so mayors wait for a
municipality resolver. Aliases no longer take an acting holder's or a
co-judge's title. Mint cost $8.44. The rerun of the person stages wrote
**44 statements** (43 `P39`, 35 of them on the two court items, and 1 `P569`)
in EditGroups batches `c1a4c231ae`, `080763000f` and `97f567b202`; verify
passed 45 of 134, refusing 46 as already on the record.

**Cuba** (`seeds/cu.yml`, `census/cu.yml`, measured 2026-09-30, written
2026-10-01). The first country run with the mint stage, because most of what
it needs has no item. Also the first
country whose own wiki is the irregular one: es `Políticos de Cuba` is a flat bag of
1902-1959 secretaries, Spanish Cortes deputies, colonial governors and 76
dissidents, and the tiers are on en.wikipedia (twenty ministerial portfolios,
the 2020 provincial governors, 48 ambassadorships). Seeded for the 2019
constitution onward: 521 people, of whom about 128 are living and in scope,
so fetch through verify is about $10. Wikidata before any run: 98 items by
descent, about 50 Cuba's own (35 are inbound embassies, 4 church offices); no
item for Council of State or Central Committee membership, the Politburo, the
Second Secretary, 14 of the 15 provincial governorships, the apex court's
president, the chief of the general staff, or any state enterprise head, so
the creation queue will outweigh the statements. Traps: `Q18060652` "Governor
of Cuba" (36 colonial holders) beside the one 2020 governorship item
`Q113662078`; `Q89188209`, an unlabelled unused twin of the presidency
(`Q1370482`) for 1976-2019; `Q6502015` holding prime ministers under three
constitutional names; an assembly item (`Q21272829`) with 54 statements, six
dated, no term qualifier. The party offices are the lane this country adds:
a Politburo seat and the Second Secretary are offices and are in the census;
Central Committee membership is politically exposed too, but Wikidata records
it as `P463` on the body rather than as a seat, so it is not minted, and
peploop does not write `P463` yet.

The run: 518 people seeded, 156 extracted (the rest out of scope), 697
office mentions reconciled, 428 left unplaced in 409 groups. **Mint**: 149
groups had no current holder near them and cost nothing; categorize (4 Sonnet
requests) made 159 candidates, verify asked Opus about 7. Four created --
the governorships of Villa Clara `Q141612240`, Cienfuegos `Q141612505`,
Granma `Q141612511` and Pinar del Río `Q141612637`, each shaped on
`Q113662078` -- and 9 found already on Wikidata; 145 skipped by rule, chiefly
one holder (40), no archetype for a deputy minister (35), ambassadorships
deferred (31) and census offices no seeded article named (15). Two rules
came out of it: a one-seat census office passes on one current holder (the
census is the second channel; asking for two people measures whether the
predecessor was seeded), and siblings that are dissolved or last held 30
years ago do not set a minted item's shape (the colonial governor did).
Artemisa and the Politburo seat stopped at verify's medium confidence. One
`creating` row survived a maxlag refusal and was recovered on the next run.
Mint cost $1.34. **Statements**: 115 `P39` proposed, 38 written; verify
passed 86 of 97 rows. One rule came out of the funnel: `recorded_elsewhere`
skips a spell already on the record under another office when the target
has no holder (2 rows: the presidency twin `Q89188209`, and the Havana
provincial assembly presidency recorded as "mayor of Havana"). Written:
**84 statements on 60 items** -- 38 `P39` (19 open, the five governors'
holders among them), 30 `P27`, 15 `P569`, 1 `P570` -- in EditGroups batches
`3016bd0155` (the first three people) and `a1b09a190b` (the drain).

