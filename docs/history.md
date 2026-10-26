---
description: What was tried on the way to peploop, peptree and pepcorp as they are, what failed and why, what editors pointed out, and every batch sent. Read before re-measuring something or re-proposing an idea.
date: 2026-10-11
tags: [history, lessons, peploop, peptree, pepcorp, quickstatements, retrieval]
---

# History and lessons

The specs (`peploop/design.md`, `peploop/positions.md`, `peploop/tree/design.md`,
`peploop/corp/design.md`) say how things work now. This file says what was
tried first and what was learned, so the same ideas are not re-proposed
without new evidence. An entry is a measurement, not a law: a better
measurement can overturn it, an argument cannot. Where an editor pointed out
a problem, the entry says what they found, what was taken back and the rule
that followed.

## The write path

- **QuickStatements V1 (QS2) merges by value.** A line is matched on item,
  property and value and its qualifiers folded into the statement found, so
  two tenures of one office became one statement carrying both starts and
  both ends (Kuwait: 50 people). A `wbeditentity` API writer was built for
  anything with several spells.
- **The API writer was slow and fragile**: one person per edit, ten seconds
  apart, waiting out maxlag; two drains run side by side wrote 24 statements
  twice (Trinidad), because the API de-duplicates nothing. QS2 automation
  failed on OAuth, so batches were pasted into the importer by hand.
- **QuickStatements 3.0** replaced both. Measured on the sandbox item: a `+`
  line always creates (and duplicates on a re-run, so the ledger is
  load-bearing); a plain line merges into the *first* statement with an
  exactly equal value; `R+` sets preferred rank; `SWITCH_VALUE` changes a value
  in place and keeps the GUID; `-Q|P|value` removes only the first match, so
  removal is by `-STATEMENT|GUID` only; a failed command reports no reason.
  `combine_commands` folds an item's lines into one edit, and such edits
  failed whole with nothing invalid in them (five Japanese members, batch
  59098, the same lines one edit each all landed in 59101; Congo's offices,
  59301 and 59323, landed uncombined as 59322 and 59339). Every lane sends
  uncombined.
- **A strike that lived only in prose went live.** Batch 59046 sent a line a
  reviewer had struck in a note; it was removed by GUID. Strikes and removals
  became ledger rows the sender honours.
- **QS3 cannot aim a merge.** A refinement whose value sits on several
  statements closes as `ambiguous-statement` (Japan 2.2% of rows, Congo
  4.5%), accepted as a skip over remove-and-recreate.
- **One reference per statement** (2026-10-19). A Wikidata admin pointed out
  that statements carried a `P143` reference for every wiki that agreed (one
  diff had eight): 470 of 4,585 referenced statements had two or more. A
  statement now cites one article, home wiki first, and none is added to a
  statement already referenced. peptree moved from the page URL (`P854`) to
  the same reference; its 1,433 earlier `P854` references stay.

## Operating peploop

- An operator typed 20–26 invocations per country and every manual link
  failed at least once; the commands that always run together were merged
  (`reconcile` ⊃ signals, `propose` ⊃ policy, one `mint`, one `send`).
- A human review gate produced 158 verdicts and 5 applied edits over two
  countries; it was replaced by the policy and a second-model verifier. The
  review TUI stays as a sampler; its accept never writes.
- Audits done as raw `UPDATE`s were wiped by the next `propose`. An audit is
  now a verdict plus a strike, which a re-propose keeps.
- Concurrent starts deadlocked on the schema's `ALTER`s; the schema is applied
  once per change of its hash, under an advisory lock. A check once wrote to
  live rows; database checks shadow their tables.
- The label/alias lane produced a fifth of all proposal rows and the policy
  threw every one away; it was removed.
- Ledger keys hash the rendered request, so a refactor that changes rendering
  by a byte re-asks everything.

## Retrieval (resolving an office mention to an item)

- Of 150 unplaced mentions read by hand: 13% the item existed, 54% a missing
  PEP office, 33% not a PEP office. Discovery mattered more than retrieval.
- Outbound missions are scoped `P17` = the receiving state, so descent never
  finds them: 27 of 84 "ambassador of Belarus" items were unloaded until the
  outbound lane.
- A cached English title from a small model took the hard set from 62 to 93
  recall@15 and 45 to 82 recall@1 at $0.13 per 1k titles. Two runs agreed
  exactly on only 66% of titles, so answers are cached and read back.
- Measured and rejected:
  - **a country filter** on candidates: hides 41% of the table, −23.7 macro
    recall; the country is a ranking input;
  - **IDF / term weighting**: +0.02 MRR, −0.4 recall;
  - **`pg_trgm`** over the document: 23–76% recall at 137–225 ms against 82.7%
    at 1.8 ms for `ts_rank`;
  - **`ts_rank` length normalisation**: flags 1/16 cost 8.6 points of top-1,
    2/8 are catastrophic;
  - **a shortlist longer than 15**: k=200 recovers 44 gold rows, none
    defensible;
  - **cutting the pool in SQL**: −2.8 recall;
  - **descriptions in the document**: −1.5 macro (they stay on the line the
    model reads);
  - **sitelink titles, monolingual name properties, every item-valued
    statement target, every alias of a `P279` parent, `P1889`**: zero gain or
    a loss;
  - **a date-fit boost** for old offices: −0.08 MRR, −16 top-1;
  - **a global holder count**: wrong once two countries are loaded; counted
    locally it is worth +0.099 MRR;
  - **embeddings** (e5-base): about 3 points on top of the title channel,
    needs torch and a re-embed per load;
  - **a forced "of <state>" qualifier, an era prior, a learned alias table**:
    flat or negative; `first_held_year` is not a start date (10% conflicts);
  - **a per-request schema closing `qid` over the shortlist**: it sat inside
    the cached prefix and killed caching; `settle` refuses an off-list QID;
  - **quotes without the article**: the model refused offices settled
    elsewhere in the text; the whole article under a 20,000-character cap is
    used.
- The test set: strict agreement on both tenure endpoints is evidence
  *against* a pair (articles date a tenure by the day the holder left,
  Wikidata by the successor's swearing-in); a tolerance picked from a grid is
  tuning to the metric; a silver set filtered by token overlap cannot measure
  a token retriever.
- A production `wd_peps` extract carried no signal (`is_pep` true on all
  189,089 rows). peploop carries no PEP classification: that is a consumer's
  question.
- **A state is all its current QIDs** (2026-10-26). rigour's `nl` is the
  Kingdom (`Q29999`) while Dutch offices carry the Netherlands (`Q55`), so
  their holders read as foreign-scoped. Discovery, holder counts, the
  `office/foreign-scoped` tag and the policy now read every current QID of
  the state; of the finished runs only nl's proposals moved. A `VALUES` of
  states inside an `OPTIONAL` hung for over ten minutes per chunk;
  `FILTER(?c IN …)` answers in a second. Mint and reconcile's `_governs`
  still read the main QID.
- **A generic `P39` covers no seat** (2026-10-26). A person holding "city
  president" or "chief executive officer" was read as already recorded, so the
  mayoralty the article names was never proposed. Such offices are marked
  `(generic office)` for extraction and no longer make `recorded_elsewhere`.
  A bare class test also caught national chambers whose terms are
  subclasses, so a generic office is listed or class-shaped with no `P1001`.

## Minting

- Unsupervised by design: a disagreement between categorize, verify and the
  guard is a skip with its rule, never a review row. The bar is at least two
  distinct holders and one current, or one current holder for a census office.
- Siblings dissolved or last held 30 years ago no longer set a new item's
  shape (Cuba's colonial governor did).
- A crash between intent and result is resolved from the record of the write,
  never by retrying: first `usercontribs` on the intent tag, now QS3's
  `response_id` per `CREATE`.
- Not minted, by rule: bilateral ambassadorships (the archetype puts the
  receiver in `P17` and the sender in `P137`, which no stage handles),
  subnational cabinet seats (Malaysia: 418 groups as `archetype/none`),
  deputy ministers without an archetype.
- **Unit heads for the AMLR** (2026-10-24, dry run). `mint_units` over 871
  governed units of 50,000 or more with no head office: 756 of 822 drafts
  guarded; a hand check of 35 found every office real and missing. Each
  failure became a rule:
  - an undated `P6` is often the mayor before last: where the infobox names
    someone else, the infobox holds;
  - infoboxes name commissions, acting heads and terms already over: none is
    a holder;
  - unit names repeat (two Polish "powiat bielski"): an office whose label
    would twin another's is not drafted;
  - a label takes the genitive the unit's own article writes ("prezydent
    Gdańska"), as the existing offices do.
- **Terms reworked** (2026-10-25). An outside editor found the English
  descriptions only rephrased the label, and aliases came in any language an
  article was written in (60 of China's 112 drafts carried a German,
  Vietnamese or Russian one). Minted items now carry no description, except a
  generic title naming no polity, and labels and aliases only in English and
  the territory's languages. Re-deciding the drafts reused their verdicts: a
  request that only drops terms keeps its answer.
- **The Union's bodies** (2026-10-25, dry run). 39 of 210 Union bodies and
  organisations seated in a member state had a head office; the 124 existing
  head items mostly carry no `P17` and scope by `P2389` or `P1001`, which the
  new ones follow. The body's own statement or its English infobox gave a
  holder for 73 of 86 bodies; 56 guarded, and a hand check of 25 found every
  office real and missing. An acting head in the infobox outranks a body's
  stale statement and drafts nothing; a body's head is attested by person,
  since "unit:Q… Name" read as the body holding its own office.
- **Holder seeding** (2026-10-25, piloted on existing offices). A unit's head
  office has no mention behind it, so its holder is seeded into the person
  lane once the office exists. The holder's item comes from the unit's `P6`
  (205 of 777) or the infobox link on the name (157 more); 412 names have no
  link and stay residue, never a search. On 32 holders of existing offices
  lacking the `P39`, 21 were accepted after the two rules above (state QIDs,
  generic offices), none wrong in a hand check. The rest: closed tenures where
  the unit's `P6` was an earlier mayor, acting mayors (rightly filtered),
  disputed or unsupported claims, and re-extractions that dropped the office.

## peptree

- The type hierarchy cannot be trusted alone: mayor is 98% of head of
  government's subtree, honorary titles 14% of Belarus's load. A `P279*` walk
  means nothing alone.
- On 54 repair slots Opus made 0 errors and Sonnet 3; answers are candidate
  indices, never free QIDs. Model-written search terms found ~7 new items from
  438 terms.
- Eras: only a form the state replaced moves the state's start (the British
  Empire's 1997 end had dated Kenya and Tanzania wrongly). `P17` holds only a
  state; a dependent territory goes in `P1001` alone. A permanent
  representative is the state's post abroad, not an inbound one.
- Denmark: rigour gives `dk` the Kingdom (Q756617), but Danish offices put
  Denmark (Q35) in `P17` 578 times against 45.
- Class typing ("has subclasses, no direct holders") was built and switched
  off: it caught real offices and missed the real class. Counting subclasses
  does not find generic roles either ("≥3 subclasses" is 9% precise).
- Brazil's 4,300 type/class-swapped mayoralties would be 8,500 edits for no
  gain downstream; left to the bot operator who made them.
- A two-letter code read as a word ("to" → Tonga) put a wrong `P17` live;
  `send --propose-reverts` exists for such cases.
- zavod's position filter follows `P31` on superclasses, so class-level `P31`s
  exclude 193 of 24,546 held offices, all seven UAE Rulers included
  (opensanctions#5854).
- peptree before peploop (Malaysia): of 93 repaired items 80 were loadable
  anyway; the repair is felt in the attributes, not in which offices load.
  The non-OECD sweep: 209 of 210 places, 3,916 statements.
- **Generic roles got a country** (2026-10-12). The creator of three Swedish
  military roles ("school commander", "squadron commander", "air group
  commander") reverted the `P17 = Sweden` we had added: the only channel was
  holders, 100% Swedish because Swedish editors documented them. An explicit
  scope answer now separates generic roles from Swedish-only titles. Re-asked
  over all 876 landed `P17`s whose label names no state: 823 `office`, 4
  `unclear`, 19 `generic`; 14 more `P17`s were removed (QS3 59521).
- **Redundant `P31 public office`** (2026-10-13). An editor asked us to
  revert QS3 59250: `P31 public office` on Swedish municipal speakers already
  typed by a class that is itself a public office. One channel had been exempt
  from `p31_typed_elsewhere`; 410 of 900 landed `P31`s were redundant this way
  and all were removed (QS3 59949). The rule now holds for every channel.
- **Citizenship before the state** (2026-10-15). An editor reverted two
  `P27 = Czech Republic` ("no Czech Republic in 1961"): a lead's "český
  politik" on people who died before 1993. 9 of 723 `P27`s sent were such; the
  7 still live were removed (QS3 60037), and `citizenship_before_state` now
  skips them, with one era source (`peploop/eras.py`) for both lanes. States'
  `P571` misleads either way (Russia prefers 1263, Germany 1949), so only a
  home state's configured chain moves a start, and `tenure_before_polity`
  keeps reading the first `P571` in claim order.
- Reconcile's `generic-class` is not "generic": its items are mostly
  national classes picked against a named seat, so it does not feed the
  generic list.
- peptree's own copy of the type closure disagreed with peploop's on 381 of
  4,896 classes (deprecated claims followed, edges never expired). Merged under
  nomenklatura's rule; across Japan's 2,977 offices no verdict moved.
- **The AMLR back-link** (2026-10-24). Of 2,282 EU units of 50,000 or more,
  881 already carried a `P1313`, 528 got one planned and 871 had no head
  office. Groupings' heads (Landrat, président d'EPCI) reach neither mayor nor
  head of government and had to be named classes. Neither a council-seat class
  nor the body's type separates a council's chair from the executive's head;
  the two wrong lines a label scan found went through "city president" or a
  bare "Bürgermeister" item.

## pepcorp

First built and run 2026-10-17 on Germany, the Netherlands, Norway and
Zambia; then a dry run of the other EU states and Switzerland.

- **The type tree takes "business" up to "position"**, so a closure test
  dropped railway and grid operators as offices. pepcorp tests the item's own
  `P31` against the position classes.
- **Municipal administrations read as government**: in France 34,961 items
  fall under executive branch. A government body is a state actor only where
  its own `P1001`, when it has one, is the state or a first-level subdivision.
- **A country's QIDs.** Organisations name Denmark `Q35` and the Netherlands
  `Q55` as `P17`; pepcorp sweeps all current QIDs, as `wd_peps` does.
- **Categories lack their class.** The Dutch "Government-owned companies" and
  "Government agencies" categories carried only the country in `P971`; the
  class was added (QS3 60476) and 856 members came in.
- **Existing owners prove nothing** (Deutsche Telekom carries `P127` Germany,
  a minority holder): an enterprise is written on only when its article names
  a public owner. Share figures are never read: they go stale.
- **Idioms measured, not assumed.** `P488` + chairman of the supervisory board
  has 0 uses; the supervisory chair is `P5052` + `P2868`. "Board member"
  `Q2824523` reads differently by language, hence the role item `Q141755781`
  (QS3 60487).
- **Funding is not ownership.** The decision call took grants and supervision
  for control; a narrow check on each link's quote (`verify.py`) refuses about
  a quarter of links, mostly rightly.
- **Labels from `jsonb` come back re-sorted**, which changed requests and made
  the content-keyed ledger pay again; labels are picked by language order.
- **QS3 fails whole items when combining many lines**: uncombined, all 34
  landed (QS3 60510, 60511).
- **Inflected languages hide links** ("Ministerstwa Zdrowia"): matching link
  titles lost 7 of 10 named owners in the Polish pilot. Names resolve through
  a link's anchor text too.
- **Wikimedia's limit is the IP's.** Five runs pacing 4/s each stalled on 429s
  for an hour; the pacer is shared across processes.
- **A state stands behind other items.** Owners named as Skarb Państwa, État
  français or a ministry typed only by a deprecated `P31` were no state actor;
  a spec's `actors` names them. Adding one re-asks the whole country.
- **The rules lost bodies the articles plainly put under the state**
  ("Owner: Government of Ireland" refused as a ministry). Re-planning from
  cached answers took Austria's `no_state_owner` from 33 to 4, Belgium's from
  41 to 2.
- **Unlinked people, matched by their own page.** Of ~3,900 seats left for
  want of a linked person, a name search plus a check of the candidate's own
  page against the seat (`match.py`) resolved 199. Names fit loosely, so the
  page carries the proof: 41 hand-judged cases agreed with the check; the one
  error found in ~110 was a namesake in the same field abroad, so a field-only
  match now needs the country's citizenship where the item states one.
- **Silence, a stake and a list are three things.** `unclear` (a stake named
  without control) is split from `unstated` (nothing said): only silence lets
  an official holdings list or a state-only form prove a body the state's.
  Lists seeded from Wikipedia or Wikidata are no proof, and a public-law form
  churches share (Anstalt des öffentlichen Rechts) is no state-only form.
- **Statutory bodies** (broadcasters, central banks, regulators) pass
  whatever their legal form; the model stretches "regulator" to watchdogs and
  registries, the residue samples found most often.
- **The polity is not every owner.** A body the run writes as an enterprise
  owns as itself; a province beside a national holder is a co-owner.
- **An infobox head may be an interim's**: 126 heads left open while the
  article names a later one are skipped.
- **The AMLR list adds scope, not bodies** (2026-10-24). Of the listed bodies
  in eight countries all but 69 were already loaded by another lane; the list
  alone admitted 42 and gained 19 seats. Where the list falls short is the
  articles: 26 listed bodies have no article in the country's languages or
  English, and 362 named rows resolve to no item.
- **Party governing bodies are statements on the party** (2026-10-25).
  Measured over EU parties: `P488` 3,124 statements, `P3975` 590, `P3320` 75,
  `P5052` none; roles live on people's `P39` qualified with the party. So seats
  are `P488` (each co-chair), `P3320` with a role item, and `P3975`. A party's
  parts are mostly working groups and organs: a part is a branch only when
  typed a party or a spec's branch class. A Dutch "partijleider" (political
  leader, not the party's chair) was written as `P488` in the first sample; a
  leader the articles do not call head of the executive is now left out.
- **The municipal tier is property-heavy and people-light** (2026-10-25,
  Germany). Of 664 new bodies, 249 passed, giving 0.31 seats per passed body:
  a person was found for 16% of seats, the rest unlinked. Answers name a city's
  administration item or holding as often as the city; resolving those to the
  unit nearly doubled the passes.
- **Corrections became additive** (2026-10-25). The correction rule had
  proposed removing `Q270791` from bodies the article shows municipal. The
  tool writes the mainstream form and reads every form, and never overwrites
  another editor's modelling (Postel's law): `Q1780371` now goes beside a
  `Q270791` someone chose, and the nine pending removals were rejected.
- **International boards are thin in the articles** (2026-10-25). Over 193
  Union bodies and organisations, 106 seats were named and 9 board lines
  survived the rules. Where a body's head is titled its chair, the board's
  chair is that head and its seat is left to the office. An honorary president
  and an executive board member are not board members.

| country | when | written | batches |
|---|---|---|---|
| Germany | 10-17 | first batch: 51 statements on 10 bodies | QS3 60510, 60511 (retry); 60476, 60487 (categories, role item) |
| EU-27 + Switzerland | 10-17 – 10-20 | dry runs, nothing sent: 6,189 lines after the policy re-run; samples 84–90% correct, 2–4% wrong | — |

## Model spending

- **Where it went (2026-10-22).** $5,240 at list price over the seven ledgers,
  none of it batched: resolve $1,423 (the person's article re-sent uncached
  with each mention), peptree $911, extract $727, mint verify $701, mint
  categorize $506, pepcorp decide $472, peploop verify $468.
- **Settled titles.** 12% of resolve calls went to titles already answered
  five or more times to one item with no dissent; hence `reconcile.settled`.
- **Trimming pepcorp's articles is not worth a re-key**: link and see-also
  sections are 3.2% of the text.
- **Trials (2026-10-22, `trial`).** A replayed sample against the stored
  answers. Opus 5.5 medium kept 92% of peptree items and 95% of peploop
  verdicts in agreement, 30–40% cheaper, and was adopted for both. Mint verify
  needed Opus 5.5 high (83% against a 93% floor, strictly one-sided: fewer
  offices). Categorize and extract without thinking fell apart or could not
  be measured, and keep their settings.

## Shared helpers across the lanes

- **One quote gate** (2026-10-23). The three lanes had three gates (case,
  JSON escapes, a 4-character floor). The shared `evidence.quoted`, replayed
  over 394k stored quotes, gained about 150 and lost 5. A bare floor of 4 cost
  Chinese tenure markers (现任); a one-character quote is a failed answer
  except for a sex.
- **One tenure judgment.** pepcorp compared dates as strings, so an end known
  only to the year read as before a start in that year (`bad_dates`). The
  shared test compares at the precision both dates share.
- **Two not-office sets**, peploop's 17 classes and peptree's 21, share 9.
  Both are in `classes` under their own names; not merged.
- **The AMLR unit set** (2026-10-24). A country's governed levels are
  measured by the direct `P31` classes of its items of 50,000 or more, not a
  walk under municipality, which missed Estonian, Latvian and Lithuanian city
  municipalities and the Irish councils. EU-27: 1,239 municipal, 1,025
  grouping and 18 metro units. Ungoverned levels (most Spanish comarcas,
  French cantons, Austrian and Czech districts) and sub-municipal districts
  are left out.
- **The AMLR rows expanded into items** (2026-10-24). 767 of 2,696 usable rows
  expanded to bodies, positions, tiers and unit levels; hand checks 40/40,
  10/10, 36/40 and 19/20. Each position failure became a rule: `io_title`
  (a function seated at an organisation is not its head), `class_of_offices`
  ("ambassador of Belgium" is a class), `several_states` (a Nordic title
  shared by four supreme courts). About 1,400 rows have no candidate at all.

## The campaign toolkit (`old/`)

Before peploop, `wd/` ran one hand-built campaign per country. What it learned
that still applies:

- Solar Hijri: a day converts to a day; a month to a Gregorian year (+621, +622
  for Bahman/Esfand), except Dey, which is ambiguous; a bare year to nothing.
  Read the calendar from its marker (`ه‍.ق` lunar, `ه‍.ش` solar), never from the
  year's range. Existing Iranian dates on Wikidata carry a day-preserving
  conversion error (about 9 days off); don't tune toward it.
- Compare dates at the precision both sides share (the Riyadh backtest went
  from 0% to 100% agreement).
- A census that prints only held items hides the empty items a sweep exists to
  fill; use a census to find, never to reject (Iraq's president is typed head of
  state, outside the position closure).
- Cabinet articles date a tenure to the cabinet, not the person (Jordan: 75%
  agreement); order portfolio patterns most-specific first (66 deputies read as
  prime ministers).
- Adding `P17` to 108 Iranian office items made 619 existing statements
  visible downstream.
- A run "complete" with 11 institutions never examined is why a country is
  judged against a list of institution classes (`docs/institutions.md`).

## Country runs (peploop)

| country | when | written | batches |
|---|---|---|---|
| Czechia | 2026-09 | nothing (pilot) | — |
| Slovenia | 09-22 – 09-29 | 554 statements, 488 items | API `930b9c352c` `4a18bf5e03` `f61844d6d0` |
| Colombia | 09-30, mint 10-02 | 1,454 + 44 statements; 2 offices minted | API `8bce22eb29` `0de728e012` `4e234c5722` `c1a4c231ae` `080763000f` `97f567b202` |
| Cuba | 10-01 | 84 statements; 4 governorships minted | API `3016bd0155` `a1b09a190b` |
| Belarus | 10-02 – 10-03 | 867 statements; 7 offices minted | API `24c59100d5` … `ca2f4ad4e0` (7) |
| Burundi | 10-02 – 10-03 | 71 statements; 2 minted | API `27feca64da` `18bd97946d` `9d666e8810` |
| Dominican Republic | 10-03 | 212 statements; 11 minted | API, 7 batches |
| Haiti | 10-03 | 123 statements | API `bb7092c2d9` `1a0b411261` `4a701a2fa7` |
| Jamaica | 10-03 | 251 statements; 1 minted | API, 7 batches (`a69492583f` largest) |
| Trinidad and Tobago | 10-03 | 247 statements; 2 minted | API, 5 batches |
| Malaysia | 10-06 – 10-08 | 1,909 statements; 28 minted | QS2 chunks `qs-001`–`033`, API `a53c072841` `aed5ba0d5d` `4e87482554`, fixes `38d1f550f6` |
| Japan | 10-08 – 10-11 | 5,697 rows applied | API `2417c74c8b` `0216ceab44` `6c47bfe35d`, QS3 59098 59101 |
| Republic of the Congo | 10-12 | 110 statements (98 rows applied); 4 minted; Brazzaville mayor repaired | QS3 59371, 59246 59247 (repair), 59322 59339 59348 (mint; 59301 59323 failed combined) |
| Somaliland | 10-12 | 99 statements (96 rows applied); 6 minted | QS3 59387, 59385 (mint) |
| Somalia | 10-12 | 237 statements (229 rows applied); nothing minted | QS3 59411 59412 |
| Australia | 10-12 – 10-14 | 2,196 statements (2,123 rows applied), 43 open tenures taken back; 579 offices minted, 498 of them local | QS3 59669 59690, 59691 (removals), 59594 59621 (mint); peptree 59250 |
| Northern Cyprus | 10-14 – 10-15 | 121 statements (112 rows applied), 1 taken back; 11 offices minted | QS3 59848 59871, 59850 (removals), 59843 59847 (mint) |
| Cyprus | 10-14 – 10-15 | 76 statements (72 rows applied), 3 taken back; 4 offices and 6 municipalities created, a duplicate MP merged | QS3 59849 59869 59951, 59850 (removals), 59846 59950 (mint), 59945 59946 59952 (places) |
| Malta | 10-14 – 10-15 | 268 statements (247 rows applied), 3 taken back; 63 offices minted, 59 of them local council mayoralties | QS3 59858 59868, 59863 (removals), 59856 (mint) |
| South Sudan | 10-15 | 148 statements (141 rows applied), 4 taken back before the send; 3 offices minted | QS3 60017, 59989 60008 (mint) |
| Sudan | 10-15 | 128 statements (117 rows applied), 1 taken back before the send; 6 offices minted, 3 of them the RSF's | QS3 60018, 59990 60010 (mint) |
| Australia (second) | 10-15 – 10-16 | 226 statements (196 P39 for 171 people, 98 of them new to the ledger); 18 offices minted; 10 of our statements taken back | QS3 60256, 60250 (mint), 60258 60266 (removals); peptree 60285 |
| Zambia | 10-16 – 10-17 | 282 statements (261 rows applied: 131 P39), 4 taken back before the send; 6 offices minted; the Supreme Court's country corrected | QS3 60336 60350, 60334 (mint), 60418 (court) |
| Angola | 10-16 – 10-17 | 110 statements (100 rows applied: 55 P39), 0 taken back; 4 offices minted | QS3 60342, 60341 (mint) |
| Namibia | 10-16 – 10-17 | 353 statements (330 rows applied: 204 P39), 3 taken back before the send; 15 offices minted | QS3 60349 60351, 60347 (mint) |
| China (zh sample) | 10-23 | 121 edits for 117 rows on 52 people, a review sample for the Mass-editing proposal; 10 offices minted | QS3 61360, 61352 (mint; 135 never reached QS3) |

### Rules each run added

Each audit took rows back by hand; the class behind them became a rule.

- **Colombia:** `tenure_ended` and the current-era seed; `future_date` and
  `termed` from its audit.
- **Cuba:** `recorded_elsewhere`. **Burundi:** `contested/twin`. **Haiti,
  Trinidad:** `open_superseded`, reading an office's and its body's `P576`.
- **Malaysia:** about 9% of open tenures were wrong (Malacca seats left open
  after a dissolution); the rules that would catch them are open work.
- **Somaliland, Somalia:** `open_superseded/government` (an open minister's
  seat that began before the state's current head of government took office);
  `minor_wiki_only/open` (an open tenure only wikis outside the home languages
  and English keep open). Somaliland's `P27` was measured, not assumed: its
  office holders carry Somaliland 37 times to Somalia's 15.
- **Australia:** `other_polity` (45 state offices first fed to another
  state's item of the same title); units yield to the mention lane when both
  draft one seat; a unit's infobox line is no alias (488 aliases removed with
  wikibase-cli); `open_unattested` (of 132 open tenures from 2022 or earlier,
  45 had no quote calling them current, about half of them over). `per: units`
  census entries took local mayoralties from 2–66% per state to 35–99%.
- **Northern Cyprus, Cyprus, Malta:** a rival state's offices (either side of
  a `P1336` claim) are off the shortlist; community names resolve to no state;
  a `per: units` level may name a state's `P150`; `open_unattested` reads
  Greek and Turkish; a same-year spell two articles date differently is held
  back; an open ambassadorship older than a term needs an infobox's word; a
  citizenship only a minor wiki gives is skipped; a seed may name a list
  article. Six 2024 Cypriot municipalities had no item and were created by
  hand; a duplicate MP was merged.
- **South Sudan, Sudan:** the `subdivision` lane (governorships carrying only
  `P1001`); a state's units are its `P150` and the items typed its first-level
  subdivision; archetypes `head_of_government` and `council_chair` for the
  RSF's rival government; a census anchor answered `exists` with no item is
  the anchor's office; an infobox's "Incumbent" counts as current; a
  speakership names its chamber. The Justice ministry's twin items were
  merged.
- **Australia (second):** judged by people gained, not offices: the
  parliamentary leadership and assistant ministers already held a `P39`, so
  neither was minted for its own sake. A portfolio-named junior seat takes the
  parent of the state's seats of the same title; a census entry may name the
  subdivision its office governs; `overlaps_holder` refuses a closed spell a
  successor took up inside it. `mint --submit` sends the payload its dry run
  printed, so five offices guarded before the `P17`-beside-`P1001` rule went
  out with both, and their `P17`s were removed. Re-deciding the first run
  flagged 48 open tenures; 32 were over or wrong, 28 already removed.
- **Zambia, Angola, Namibia:** seeds widened to each country's whole
  office-holding tree (measured against every living citizen with an article,
  the remainder is mostly sport); `open_unattested` reads Portuguese
  (held back 30 Angolan open tenures); a title opening on a verb or dating its
  holder is no alias. The Supreme Court of Zambia's item carried `P17` India;
  its value was switched to Zambia in place (QS3 60418).
