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
two or three, which inflates a chamber's count several times over. The list
also contains what the descent reaches and the run does not want: every
*inbound* ambassadorship, church offices, the odd order of merit. Read past
them.

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
`docs/institutions.md`; the shape is `seeds/si.yml`'s: a comment block
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
interpreter `.venv/bin/python -m peploop.cli`.

```
seed --country <cc>                  # the categories of seeds/<cc>.yml
load-positions --country <cc>        # every discovery lane; network only, beside fetch
fetch --country <cc>                 # items, the scope gate, then every sitelinked article
extract --country <cc>               # one request per person, Sonnet
reconcile --country <cc>             # ranking signals, English titles, one request per office mention, then the refusals whose list gained
mint --country <cc>                  # categorize (Sonnet), verify (Opus), data/mint/<cc>.md, feed `found`; dry: every guarded payload
mint --country <cc> --submit         # creates what the dry run printed, decides nothing; feeds each item made
propose --country <cc>               # P39 rows appear only now; ends by deciding every row and printing the funnel
verify --country <cc>                # one request per pending row, Opus; ends with the policy's funnel
send --country <cc>                  # dry: pre-flight, plan, data/peploop/send/<cc>.qs with its routes
send --country <cc> --submit         # on the user's go: one QS3 batch, then approved removals; rows settle
send --country <cc> --submit --retry # the lines QS3 failed, again, one edit each
```

Beside them: `report --country <cc> [people|positions|proposals|funnel|mint]`
prints any checkpoint's numbers and writes nothing; `audit proposal|candidate
<ids> --country <cc> --reason … --by <name>` takes rows out (§5); `prompt
extract|verify --qid Q` and `prompt mint-categorize|mint-verify --country
<cc>` print what a model stage would be shown, sending nothing; `review
--country <cc>` samples proposals in a terminal UI and records verdicts the
policy reads (a rejection skips the row; nothing is accepted by it).

Every stage works through its whole selection at a fixed concurrency, and
takes `--qid` to run named people instead. `fetch` and `load-positions` are
network only and run side by side. `reconcile` first counts holders,
instances and subclasses for rows no pass has counted, so a country pays only
for its own new rows. A `reconcile` with failed mentions is simply run again:
the ledger asks only the failures.

The mint stage sits between `reconcile` and `propose` because its input is the
reconciler's refusals and its output is items those refusals can now land on.
Write `census/<cc>.yml` before `mint`: the offices the country has
whether or not a seeded article named them, by institution class of
`docs/institutions.md`, each with its body QID and, optionally, an
official source. An entry is a prompt for the offices nobody's article names
-- it puts the anchor and its body in front of categorize -- and not a second
channel of evidence: every office passes on one current holder, census or
not. Its bodies come from measurement (`docs/research/position_items.md` §10 is
the template), never from memory. A census
entry nobody's article attests is skipped, so the file says what must exist
and the seeds still decide what gets made. `mint --submit` creates the rows
the last dry run guarded and nothing it did not print, and feeds each item as
soon as it is created; every `mint` run, dry or not, feeds the rows verify
decided `found` -- an item that already existed -- and repairs a feed a crash
or a propose failure cut short. The feed is idempotent.
`audit candidate <id> --country <cc> --reason … --by <name>` skips a row
after the fact; there is no approve.

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
| `extract` | `report people`: people per status (how many the scope gate discarded), token total | go on |
| `reconcile` | verdicts by kind; the creation queue (`resolution` rows with a null `qid`) by office title; where the incumbents' offices landed | go on |
| `mint` (dry) | candidates per institution class and the groups no office took (`office_unassigned`); `data/mint/<cc>.md` (`report mint`): the funnel by rule, then every `guarded` row with the lines that would create it and every `found` row with the item it names | **stop and show it** |
| `mint --submit` | created, found at the re-check, failed; the feed line (attestations `retrieved`, reopened verdicts by kind); a re-run creates nothing | **only on the user's go**, then `propose` |
| `propose` | the funnel it ends with, per property, rule by rule (`report funnel` reprints it) | **stop and show it**: `verify` is the next spend |
| `verify` | verdicts by kind and the funnel it ends with; every refusal class read by the observer; doubtful `supported` rows listed | go on to `send` |
| `send` (dry) | routes (create, merge, switch, and what closes without a line: `exists`, `termed`, `ambiguous-statement`, …), lines, rows deferred; above 2% `ambiguous-statement`, stop and report | **stop and show it** |
| `send --submit` | the QS3 batch id and EditGroups link, rows applied and failed (`send --status`); failed lines go again with `--retry` | **only on the user's go**, then the audit |

Nothing is written to Wikidata and nothing is pushed to git without the user
asking. The funnel is the one place to stop unasked: a rule that fires on a
class the country's shape explains is fine, and a rule firing on a class
nobody predicted is a finding to report before any request is spent.

Creating an item is the one write peploop cannot take back by editing, so the
dry `mint` is a stop: an observer reads the skips and the guarded rows, and
each class it finds wrong becomes a rule in `mint.RULES` with a case in
`check_mint` -- never a ruling on a row. What is shown first is the funnel
number (offices created and found against candidates), then the report.

The funnel's usual shape: about 60% of `P39` rows reach the verifier; the rest
fall to a medium-confidence placement, a missing start, a tenure too old, a
sibling spell, a generic item that wanted a scoping qualifier. A class that falls for a reason the rules do not name becomes a
rule in `policy.py` with a case in `check_policy.py` before `verify` runs --
never a row to hand-check, never a "review later".

## 5. The audit

The audit is an observer agent over `psql` and the edits; what it doubts it
takes out with `audit proposal --ids <file> --country <cc> --reason … --by
<name>`, never with a raw `UPDATE` -- a skip without its verdict is wiped by
the next `propose`. It reads `verification` joined to `proposal` for the country's
applied rows and the batch's edits on EditGroups
(`https://editgroups.toolforge.org/b/QSv3/<qs3 id>/`, ids from `send --status`)
for a stratified sample (per property, per policy rule, per office), and
reports the `supported` verdicts it doubts, with the verifier's evidence and
its own reading of the article. Where to focus, always: the **incumbents** --
an open tenure on the right current item, with no end date invented -- and
the multi-term legislators, whose several spells must be several statements.
Then whatever §1 flagged for this country: the duplicate office pairs, the
tiers with no item, the renamed offices.

What a doubtful class becomes: a rule, with its case, and a re-run of the
policy. A row already written is taken back by the same `audit proposal`: it
strikes the statement, and the strike queues its removal by statement id --
approved at once when the statement is provably only ours, `proposed` for
`removals approve` otherwise -- which the next `send --submit` sends. A large
class can still be reverted whole on EditGroups. peploop never removes
anything nobody approved.

## 6. Closing a country

- `check_neutral.TOKENS` gains the country's tokens (its name stem, the state
  QID, `<lang>.wikipedia`, its capital) and the check passes -- which is what
  finds anything of the country that crept into a rule or a prompt during the
  run.
- The country's entry in §7 is finished with its numbers.
- The memory file gets one line.

## 7. Countries run

One line per country run, with its batches, is in `docs/history.md`; the
findings that became rules are there too. Add the new country's line there
when it closes.
