---
description: What was tried on the way to peploop and peptree as they are, what failed and why, and one line per country run. Read before re-measuring something or re-proposing an idea.
date: 2026-10-11
tags: [history, lessons, peploop, peptree, quickstatements, retrieval]
---

# History and lessons

The specs (`peploop/design.md`, `peploop/positions.md`, `peploop/tree/design.md`)
say how things work now. This file says what was tried first and what was
learned, so the same ideas are not re-proposed without new evidence. An entry
is a measurement, not a law: a better measurement can overturn it, an argument
cannot.

## The write path

- **QuickStatements V1 (QS2) merges by value.** A line is matched on item,
  property and value and its qualifiers are folded into the statement found,
  so two tenures of one office became one statement carrying both starts and
  both ends (Kuwait: 50 people; Ecuador: one ministry statement whose starts
  were fourteen years apart). That is why a `wbeditentity` API writer was
  built for anything with several spells.
- **The API writer was slow and fragile.** One person per edit, ten seconds
  apart, waiting out maxlag (an edit once sat 27 s lagged for four minutes);
  `--limit` defaults cut drains short; two drains run side by side wrote 24
  statements twice (Trinidad), because the API de-duplicates nothing.
- **QS2 automation failed on OAuth**, so peptree pasted 300-command chunks into
  the importer by hand (64 chunks), and peploop's Malaysia run split 1,499
  statements to pasted chunks and 410 to the API.
- **QuickStatements 3.0** (`qs-dev`, API token) replaced both. Measured on the
  sandbox item: a `+` line always creates (and duplicates on a re-run, so the
  ledger is load-bearing); a plain line merges into the *first* statement with
  an exactly equal value; references join in one line with `!S`; `R+` sets
  preferred rank; `SWITCH_VALUE` changes a value in place by exact match and
  keeps the GUID (a year stored as `+1939-01-01T00:00:00Z/9` matches when sent
  verbatim); `-Q|P|value` removes only the first match, so removal is by
  `-STATEMENT|GUID` only; a failed command reports no reason and the report CSV
  refuses a token; `combine_commands` folds an item's consecutive lines into one
  edit, and for five Japanese members with three or more new P39s that edit
  failed whole (19 lines, batch 59098) while the same lines one edit each all
  landed (59101) — so peploop's additions go out uncombined.
  Creations failed the same way, with nothing invalid in them: Congo's five
  offices combined failed whole twice (59301, 59323), and the same items sent
  one edit per line landed (59322, 59339) — so creations go out uncombined too.
- **A strike that lived only in prose went live.** Batch 59046 sent a line a
  reviewer had struck in a `sweep.md` note; it had to be removed by GUID. Strikes
  and removals became ledger rows the sender honours.
- **QS3 cannot aim a merge.** A refinement whose value sits on several
  statements cannot be sent; it closes as `ambiguous-statement`. Japan: 2.2% of
  rows, all House of Representatives members recorded once per Diet term —
  accepted as a skip over remove-and-recreate. Congo: 4.5% (5 of 111), each a
  legislator holding one bare and one termed (`P2937`) statement for the seat.

## Operating peploop

- An operator typed 20–26 invocations per country; every manual link failed at
  least once. The answer was to merge the commands that always run together
  (`reconcile` ⊃ signals, `propose` ⊃ policy, one `mint`, one `send`), not a
  single `run` driver.
- A human review gate produced 158 verdicts and 5 applied edits over two
  countries; it was replaced by the policy and a second-model verifier. The
  review TUI stays as a sampler; its accept never writes.
- Audits done as raw `UPDATE`s were wiped by the next `propose` (Colombia's 14
  `audit:pudo` rows, the Dominican Republic's five). An audit is now a verdict
  plus a strike, which a re-propose keeps.
- Every command start ran the schema's `ALTER`s under exclusive locks and two
  concurrent starts deadlocked; the schema is now applied once per change of
  its hash, under an advisory lock.
- A check once wrote to live rows; database checks shadow their tables.
- The label/alias lane produced a fifth of all proposal rows and the policy
  threw every one away; it was removed.
- LLM spend to 2026-10-04 was about $640: extraction $182, reconcile $285,
  verify $103, mint $69, titles $2. Ledger keys hash the rendered request, so a
  refactor that changes rendering by a byte re-asks everything.

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
  - **a country filter** on candidates: hides 41% of the table, −23.7 macro recall;
    the country is a ranking input;
  - **IDF / term weighting**: +0.02 MRR, −0.4 recall; plain coverage (`ts_rank`
    flag 0) is equivalent;
  - **`pg_trgm`** over the document: 23–76% recall at 137–225 ms against 82.7% at
    1.8 ms for `ts_rank`;
  - **`ts_rank` length normalisation**: flags 1/16 cost 8.6 points of top-1, 2/8
    are catastrophic;
  - **a shortlist longer than 15**: k=200 recovers 44 gold rows, none defensible;
  - **cutting the pool in SQL**: −2.8 recall; depth is worth nothing without the
    re-ranker;
  - **descriptions in the document**: −1.5 macro (they stay on the line the model
    reads);
  - **sitelink titles, monolingual name properties, every item-valued
    statement target, every alias of a `P279` parent, `P1889`**: zero gain or a
    loss;
  - **a date-fit boost** for old offices: −0.08 MRR, −16 top-1 (the conflict
    penalty half is kept);
  - **a global holder count**: wrong once two countries are loaded; counted
    locally it is worth +0.099 MRR;
  - **embeddings** (e5-base): about 3 points on top of the title channel, needs
    torch and a re-embed per load, no pgvector on the server;
  - **a forced "of <state>" qualifier, an era prior, a learned alias table**:
    flat or negative; `first_held_year` is not a start date (10% conflicts);
  - **a per-request schema closing `qid` over the shortlist**: it sat inside the
    cached prefix and killed caching; `settle` refuses an off-list QID anyway;
  - **quotes without the article**: the model refused offices settled elsewhere
    in the text; the whole article under a 20,000-character cap is used.
- The test set: strict agreement on both tenure endpoints is evidence *against*
  a pair (articles date a tenure by the day the holder left, Wikidata by the
  successor's swearing-in); a tolerance picked from a grid is tuning to the
  metric; a silver set filtered by token overlap cannot measure a token
  retriever.
- A production `wd_peps` extract carried no signal (`is_pep` true on all
  189,089 rows). peploop carries no PEP classification: that is a consumer's
  question.

## Minting

- Unsupervised by design: a disagreement between categorize, verify and the
  guard is a skip with its rule, never a review row. The bar is at least two
  distinct holders and one current, or one current holder for a census office.
- Siblings dissolved or last held 30 years ago no longer set a new item's shape
  (Cuba's colonial governor did).
- A crash between intent and result is resolved from the record of the write,
  never by retrying: first `usercontribs` on the intent tag, now QS3's
  `response_id` per `CREATE`.
- Not minted, by rule: bilateral ambassadorships, subnational cabinet seats
  (Malaysia: 418 groups as `archetype/none`), deputy ministers without an
  archetype.

## peptree

- The type hierarchy is polluted: mayor is 98% of head of government's subtree,
  honorary titles 14% of Belarus's load. A `P279*` walk means nothing alone.
- On 54 repair slots Opus made 0 errors and Sonnet 3; answers are candidate
  indices, never free QIDs. Model-written search terms found ~7 new items from
  438 terms.
- Eras: only a form the state replaced moves the state's start — the British
  Empire's 1997 end had dated Kenya and Tanzania wrongly.
- `P17` holds only a state; a dependent territory goes in `P1001` alone.
- Denmark: rigour gives `dk` the Kingdom (Q756617), but Danish offices put
  Denmark (Q35) in `P17` 578 times against 45. The Netherlands will need the
  same treatment.
- A permanent representative is the state's post abroad, not an inbound one.
- Class typing ("has subclasses, no direct holders") was built and switched off:
  it caught real offices and missed the real class.
- Brazil's 4,300 type/class-swapped mayoralties (bot-made) would be 8,500 edits
  for no gain downstream; left to a bot operator.
- A two-letter code read as a word ("to" → Tonga) put a wrong `P17` live;
  `send --propose-reverts` exists for such cases.
- zavod's position filter follows `P31` on superclasses, so class-level `P31`s
  exclude 193 of 24,546 held offices, all seven UAE Rulers included
  (opensanctions#5854).
- peptree before peploop (Malaysia): of 93 repaired items 80 were loadable
  anyway; the repair is felt in the attributes, not in which offices load.
- The non-OECD sweep: 209 of 210 places, 3,916 statements, about $370.
- Three `P17 = Sweden` statements were reverted by the items' creator
  (2026-10-12): "school commander", "squadron commander", "air group
  commander", generic military roles made for Swedish officers. The only
  channel was holders, 100% Swedish because Swedish editors documented them.
  Requiring the model's quote to name the state would have refused a fifth of
  Sweden's correct P17s ("svensk" is not "Sverige"); an explicit scope answer
  separates the roles (all `generic` or `unclear` on a probe) from Swedish-only
  titles (kammarrättspresident, hovrättsassessor: `office`).
  Re-asked over all 876 landed `P17`s whose label names no state: 823
  `office`, 4 `unclear`, 19 `generic`; 17 listed (14 plus the three reverted),
  14 `P17`s removed (QS3 59521).
- No measured generic class carries a `P17`; the eight with a `P1001` all name
  a class of polity (mayor's municipality, bishop's diocese). A `P1001` value
  with a `P279` of its own and no `P17` is such a class: 2 of 400 sampled
  `P1001` values had a `P279`, "state" and a county whose `P17` keeps it a
  polity.
- Counting subclasses does not find generic roles: "≥3 subclasses" is 9%
  precise, the Swedish roles have 0–2, and the most-used "mayor of a place in
  X" classes have under ten. What one-country classes of local office share
  is many subclasses with distinct `P1001`; the old `class_type` rule also
  failed because people put the class itself in `P39`.
- Reconcile's `generic-class` is not "generic": its 253 items are mostly
  national classes picked against a named seat ("member of the Australian
  House of Representatives"), so it does not feed the generic list.
- peptree began as a separate package with its own copy of the type closure
  and edge table. The two tables disagreed on 381 of the 4,896 classes both
  held: 282 because peploop's closure followed deprecated claims, most of the
  rest because peploop's edges never expired. Merged under nomenklatura's rule
  (deprecated skipped, ended skipped except historical country); across jp's
  2,977 offices no position, diplomatic, worship or organisation verdict
  moved.

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
| Australia | 10-12 – 10-14 | 2,188 statements (2,115 rows applied), 43 open tenures taken back; 579 offices minted, 498 of them local | QS3 59669, 59594 59621 (mint); peptree 59250 |

Findings from runs that became rules: `tenure_ended` and the current-era seed
(Colombia), `future_date` and `termed` (Colombia's audit), `recorded_elsewhere`
(Cuba), `contested/twin` (Burundi), `open_superseded` reading an office's and
its body's `P576` (Haiti, Trinidad). Malaysia's audit found about 9% of open
tenures wrong — 17 Malacca seats left open after a dissolution — and the rules
that would catch them are open work (`plans/peploop_next.md`).

Somaliland and Somalia (one session, Somaliland seeded first because en
nests its tree inside Somalia's) added two of those rules. `open_superseded/
government`: an open minister's seat that began before the state's current
`P1313` holder took office -- stale "incumbent" infoboxes of Bihi's cabinet
after the December 2024 change, 19 Somali ministers from before the 2022
government. `minor_wiki_only/open`: an open tenure only wikis outside the home
languages and English keep open -- among them an it.wikipedia "disputed"
presidency of Somalia from May 2026. Its first cut read the home languages off
the person's `P27` alone and took six ar-only rows: the run state's languages
count too. Somaliland's `P27` was measured, not assumed: holders of its offices
carry Somaliland 37 times to Somalia's 15. Somalia minted nothing: its federal
ministries all have items, and what was left were member-state cabinet seats
(no archetype) and offices attested in English only where its offices carry ar
labels. Four open rows were audited out by hand: two senators from the 2016-17
term (the chamber rule needs a cohort of starters on record, and the 2022 term
has one) and two ambassadorships an article had ended or left a decade stale.

Australia went down to local government, with mint creating every office it
lacked. A state minister is now a `minister` scoped to its state, a council
seat a `councillor`, and a mayor's town is resolved live from the name
categorize gives. A `per: units` census entry mints a level's office for
every unit whose own article names a holder (`mint_units`): mayoralties of
local government areas went from 2-66% per state to 35-99%. The checks missed
four things, each found in a dry run or after a send and each now a rule:
federation homonyms (45 state offices first fed to another state's or the
Commonwealth's item of the same title: `other_polity` in the guard, `exists`
and the policy), the two lanes drafting one seat twice (units yield to the
mention candidate verify guards, and are decided last), the unit's infobox
line becoming the created item's alias (488 items; removed with wikibase-cli,
the only write outside QS3), and open tenures begun long ago that no quote
calls current (`open_unattested`: of 132 open tenures from 2022 or earlier,
45 had no such quote and about half were over). Categorize re-asks every
chunk after a submit, since the state's office list it shows has changed:
about $20 a pass.

