# Measured: enriching one person at a time

The evidence behind `recipes/enrichment_loop.md`. That file says what to do;
this says what was counted, what it cost, and which of the counts are one run
wide and should not be generalised.

**Measured 2026-08-23/24.** Three kinds of evidence, kept apart because they age
differently:

- **Population counts** over `wd_categories.yml` and Wikidata, re-runnable with
  `scripts/spec_report.py` and `scripts/retirable.py`.
- **Run results** — two specs, one of them n=3. Read the caveats in §6.
- **Bugs found by reading output**, each with the number that made it visible.
  These are the durable part: every one was silent, and most were in code the
  workbench had been running for weeks.

## 1. The population

`wd_categories.yml` had **594** PETScan specs when this was measured. **284**
attached a synthetic position (`h.make_position`, `wd-cat` hash id, no Wikidata
identity) and **239** of those carried a resolved `wikidata_id` — **209** unique
target QIDs, holding **63,353** P39 statements between them.

**These numbers go down as the project works, which is the point.** By
2026-08-24 the same file read 551 / 241 / 196, because `scripts/retire_specs.py`
had commented out 43 specs the ledger found removable. So a figure here is a
measurement with a date on it and not a constant: re-run `scripts/spec_report.py`
and `scripts/retirable.py` rather than quoting this section, and expect the
denominator to shrink. `data/enrich/specs.json` is the live answer; it is
gitignored, so the committed ledgers `coverage/petscan_specs.md` and
`coverage/petscan_retirable.md` are the record.

Distribution of those targets by how many holders they have:

| holders | targets |
|---|---:|
| 0 | 2 |
| 1–9 | 30 |
| 10–49 | 55 |
| 50–499 | 97 |
| 500+ | 25 |

The two with no holders at all are `Q104881755` Mayor of Managua and
`Q68081922` Minister of the Czech Republic.

### What deleting a query actually requires

`crawler.py` applies a spec's `topic:` to its members **independently of the
`position:` block** (`crawl_category` pops them separately; `crawl_persons`
adds topics and then decides `external=` on whether any exist). So removing a
whole spec removes the PEP topic, the country and the synthetic occupancy
together, and the replacement has to be `wd_peps` emitting those people from
their own statements. That is a stronger condition than every member holding the
target, and it is why the report audits the target item as well as the members.

Note the categories crawler passes `strict=True`, so it is the stricter of the
two readers — `deceased` and `too_young` apply to it and not to `wd_peps`.

### Dispositions, 284 specs

| disposition | specs | people in the pre-gate gap |
|---|---:|---:|
| `retirable` | 22 | 0 |
| `enrich` | 72 | 1,970 |
| `fix-item` | 4 | 7 |
| `os-policy` | 110 | 2,292 |
| `bucket` | 24 | — |
| `unresolved` | 28 | 2,405 |
| `broken-query` | 24 | — |

**`os-policy` is the ceiling, and it is not made of Wikidata problems.** Those
110 specs name targets that are correctly modelled and that `wd_peps` still
declines — the class confers no `role.pep` in `zavod`'s `SUB_TYPES`, or the type
closure reaches an award with nothing to rescue it. No amount of P39 writing
retires them. Only the first two rows are reachable by enrichment.

`broken-query` is the 24 specs whose category matches no page at all, which
`scripts/category_langcheck.py` had already found: a wrong wiki, or a title whose
case is wrong after the first letter. A spec contributing nobody is not
retirable, it is broken, and the fix is upstream.

**Two independent audits of the same 209 targets disagreed, and the more careful
one is right.** This session read `wd/shape.py` and got 86 emittable;
`scripts/audit_os_positions.py` replays `zavod/shed/wikidata/position.py`'s gates
in their own order and got 80. The difference is documented in
`coverage/wd_categories.md`: `wd/shape.py`'s `type_targets` keeps deprecated
claims where nomenklatura's `Item.claims` drops them, and its `CLOSURE_CACHE` is
lossy — two errors that partly cancel. **Anything read out of `wd/shape.py`'s
`excluded_by` is unreliable until both are fixed**, so `spec_report.py` takes the
emit call from the audit and not from `shape`.

### The gate moves the answer

`spec_report.py`'s `gap` is counted **before** the cohort relevance gate and
overstates the queue, sometimes entirely:

| spec | pre-gate gap | post-gate work |
|---|---:|---:|
| `Prime_ministers_of_Spain` | 101 | **0** |
| `Presidents_of_the_Senate_of_Spain` | 3 | **0** |
| `Members_of_the_Senate_of_Spain` | 69 | 10 |
| `Posłowie_na_Sejm…X_kadencji` | 106 | 106 |

Measured across the 94 specs whose target emits: **44 removable, 50 carrying
work** — against the 22 the pre-gate count found. `scripts/retirable.py` keeps
that list, and every removable row states how many people leave the dataset when
its `topic:` goes (the long-dead and the pre-1920, whom `wd_peps` declines
anyway).

## 2. How much evidence exists

The binding constraint is not judgement, it is whether there is anything to read.
`tasks/birthdates.md` measured that 84% of the P569 gap has no enwiki article and
64% has none in any language, which is why a sitelink is a hard cohort gate.

Humans with `P27 = <country>`, an enwiki article, and **zero** P39 statements,
against those with one:

| country | article, no P39 | article, has P39 |
|---|---:|---:|
| Iran (Q794) | **6,643** | 1,079 |
| Lesotho (Q1013) | **135** | 74 |

The campaigns worked the right-hand column. Most of those 6,643 are footballers
and poets, which is what the category generator is for.

## 3. Can a gazetteer be cached

Position items with `P17`/`P1001` pointing at one state, via
`p:P31/ps:P31/wdt:P279*` → `Q4164871`:

| country | position items | measured |
|---|---:|---|
| Guatemala | 51 | 2026-08-24 |
| Lesotho | 62 | 2026-08-05 |
| Czechia | 194 | 2026-08-05 |
| Iran | 200 | 2026-08-05 |
| Poland | 322 | 2026-08-24 |
| **Russia** | **2,348** | 2026-08-24 |
| United States | 5,005 | 2026-08-05 |
| **Spain** | **13,198** | 2026-08-24 |

**The first answer — "yes, and the US is the outlier rather than the shape" —
was wrong, and wrong in the direction that matters.** It rested on three
countries, and both of the ones later proposed as the first bucket run break it.

Spain is the shape at the far end. A 40-item random sample is almost entirely
per-municipality mayoralties (`mayor of Alfambra`, `alcalde de Valle de
Bardají`), and the `P279` tally adds 210 Catholic bishoprics across three
classes (Latin 75, suffragan 71, diocesan 64) and 118 nobility titles (62
`marqués`, 56 `conde`). Everything descends from `Q4164871`, so nothing here is
mis-modelled — the set is simply not a menu anyone could choose from. Filtering
to items with at least one recorded holder still leaves **4,818**.

So a whole-country gazetteer is a *small-country* technique. Czechia at 194 and
Poland at 322 fit a cached prefix; Spain cannot be one however it is filtered,
and the alternative is to retrieve per person — see §11.

Use `p:P31/ps:P31`, never `wdt:P31`: `wdt:` reports `Q12251224` "Crown Prince of
Saudi Arabia" — a live spec target — as not a position, because its `Q4164871`
sits behind a preferred value.

## 4. Cost

One Opus 5 request per person at `effort=high`, two cached system blocks
(instructions ~2,121 tokens; gazetteer), dossier in the user turn.

| | ICC prosecutors | Poland, Sejm X |
|---|---|---|
| dossier size | ~13k chars (~3.2k tokens) | ~4k chars (~1k tokens) |
| people | 3 | 40 backtest / 106 gap |
| cost | $0.34 total | **$4.57 for 106 = $0.043 each** |

Guatemala's two Congress specs: 23 people, **$0.84**. So the working figure is
**4¢ per person**, and the `enrich` class as a whole (72 specs, ~1,970 people
pre-gate) is roughly **$85**, or ~$42 on the Batch API.

Caching behaves as designed and is visible in the run log: 3,298 tokens written
once on the first request and read on every one after it. The serialised first
request in `wd/verdicts.py` is what makes that true — a fan-out that starts every
worker at once has each of them write the prefix instead.

Dossier size is the cost driver and it varies by an order of magnitude between
specs, which is why `batch_size=1` and a renderer exist: JSON-escaping a 40 KB
article wastes tokens, and one large item in a batch of ten inflates the context
of the other nine.

## 5. Run results

### ICC prosecutors (n=3, en)

Target QID hidden from the dossier. **3 of 3 tenures rediscovered at day
precision**, `same_term` on all three, 0 missed, 6 of 6 quotes verified.

The result that mattered more than the count: Bensouda's *Deputy* Prosecutorship
(2004–2012) was reported as a separate unresolved office rather than merged into
her Prosecutorship, with the reason saying so. Moreno-Ocampo's notes declined a
German-only claim the English article did not corroborate.

### Poland, Sejm X kadencja (n=40 backtest, pl+en)

391 recorded holders, 106 post-gate work, 0 dropped by the gate.

| | |
|---|---:|
| proposals | 117 |
| quotes verified | **117 / 117** |
| recall: recorded tenures re-found | 41 / 42 |
| dates agree where a date existed | **13 / 13** |
| recorded tenures that are **undated** | **31 / 42** |
| proposals with no matching record | 59 |
| proposals for offices outside the gazetteer | 45 |

Three mid-term replacement dates were read out of Polish prose at day precision
and matched the record exactly (`2020-11-27`, `2021-05-04`, `2021-03-16`). One
proposal came back `coarser` than the record — the model was *more* conservative
than Wikidata, which is the right direction.

**Recall is measured by cardinality, not identity** (`min(len(proposals),
len(on_target))`), so 41/42 means one person had fewer proposals than recorded
tenures. It is a floor, and a crude one.

### Guatemala (n=23 gap, en + es)

A deliberately different second target: 8 specs over 5 offices, the same office
reached from two wikis (`Presidentes_de_Guatemala` es and
`Presidents_of_Guatemala` en both → `Q6085537`), a bucket spec, and two
`os-policy` ones. **25 statements over 23 people for $0.84.**

Its value was structural rather than numerical. Three of its five `enrich` specs
were retired mid-session by `scripts/retire_specs.py` for the reasons
`retirable.py` had computed (`48/50 already hold Q6085537; 2 leave the dataset`),
which closed that pipeline end to end. And **its empty qualifier sets exposed a
shadowing bug** that Poland would have hidden: see §9.

### What reached Wikidata

| | proposed | live and verified |
|---|---:|---:|
| Poland `P39` `Q19269361` | 102 | **102** |
| Poland `P27` `Q36` | 22 | **22** |
| Poland `P569` | 4 | **4** |
| Guatemala `P39` `Q18277108` (API path) | 4 | **4** |

The Polish batch went through QuickStatements; the Guatemalan four through
`scripts/apply_claims.py --apply`, which was the first exercise of the claims
path — two people with several tenures in one office, written atomically. A
second run of it is a clean no-op, which matters because the API de-duplicates
nothing and the ledger is the only guard.

**All 102 Polish `P39` holders are predicted to emit as PEPs**, with zero
remaining gaps (`wd/human.py:verify_all` against the office's own topics). That is
the premise of the whole project and it had not been checked before. A live
`yente` confirmation is still outstanding: OpenSanctions takes days to pick
changes up.

### The re-run, and what a cohort read means

Poland's cohort `held` climbed 391 → 416 → 493 across three runs in ninety
minutes. This looked like WDQS instability and was not: **the batch had been
applied**, and `members_holding` reading at `max_age=0` saw its own effect. The
`already_recorded` gate then correctly declined to re-propose. That is
`STATE_MAX_AGE = 0` doing exactly the job the UAE incident created it for, and it
is the reason a cohort count is not a stable number to plan against.

## 6. What not to generalise

- **Three specs, all single-office.** Every gazetteer so far held one item, so
  **position association has still not been tested**: there was nothing to choose
  between. The 24 `bucket` specs are where that question lives and none has been
  run.
- **Legislature membership is the easy case.** One item, no succession, and every
  member's term shares the same boundaries, so target and date agreement are
  close to free. A good Poland score is necessary, not sufficient. Every run here
  is a legislature or a small executive office.
- **Every statement cites only a Wikipedia permalink** (`S4656`, no `S854`).
  `wd/validate.py` warns, correctly, and roughly half are year-precision.
- **The applied statements are not yet confirmed downstream.** They are
  *predicted* to emit — 102 of 102, by replaying the crawl's gates — but
  OpenSanctions takes days to pick changes up, so a live `yente` check is
  outstanding.
- **A cohort count is not stable.** Poland's `held` moved 391 → 416 → 493 in
  ninety minutes because the batch was being applied underneath it. Size a run
  from a fresh read, not from a number written down earlier.
- **`undated_needs_removal` is unrouted.** 49 Polish records need a live
  statement removed first and nothing renders that list.

## 7. The birth-date lane

Two channels are required and, outside English, **neither of
`scripts/harvest_dob.py`'s two exists**:

- The births category was matched by `^(\d{3,4}) births$` — English only. On any
  other wiki nothing matched, so the verdict was `no-cross-check` forever and
  every date was held back for want of a channel that could not exist. Now
  localised for eleven wikis.
- `worth_rendering` is **False** for pl, de, fr and cs: those wikis state the
  birth date in prose rather than an infobox field. So the infobox channel is
  absent there regardless of the category fix.

The enrichment loop has a channel that campaign does not — the model reading the
prose under a verbatim quote, which `tasks/birthdates.md` lists as left on the
table. The gate is therefore prose against the births category, with the infobox
as a third channel that still vetoes on contradiction.

**The category is the ceiling, and it swings by an order of magnitude:**

| spec | missing `P569` | reachable (has a births category) |
|---|---:|---:|
| Poland, Sejm X | 4 | **4 (100%)** |
| Supreme People's Assembly | 39 | 6 (15%) |
| Ecuador, Asambleístas | 13 | 1 (7%) |

Same shape as `tasks/birthdates.md`'s per-country swing. **DOB is a per-spec
decision, not a lane.**

**Exercised, and the sizing held.** Poland's gap run produced six two-channel
birth dates, of which four were new and applied — against the ceiling of 4-of-4
measured before spending anything. The quotes are Polish prose (`ur. 7 września
1983 w Lublinie`, `ur. 28 grudnia 1973 w Krzeszowicach`), which is the channel
`harvest_dob.py` structurally cannot reach and `tasks/birthdates.md` lists as
left on the table.

Five of the eleven category patterns were wrong on the first pass and only real
articles said so: Hungarian vowel harmony (`-ban` / `-ben`), Latvian word order
(`1973. gadā dzimušie`), Czech `Narození v roce`, French writing the month in,
and Lithuanian which could not be verified at all and is marked unverified.

## 8. The roster channel

A category and its list article are two views of one roster. The link between
them is the **eponymous-list convention**: `Posłowie na Sejm Rzeczypospolitej
Polskiej X kadencji` the category sits beside an article of exactly that name,
129 KB of tables.

**`P301` main topic does not work**, which matters because it is the obvious
structured signal to reach for. It resolves to the *body* or an occupation —
"International Criminal Court", "Prosecutor" — not to a list.

Measured on the Polish page: `parse_rosters` finds **70 rows, 69 linked to an
item**, from four tables (the presidium, club affiliation, and the 39 whose
mandate expired). The **main 460-member list is in 849 `<li>` elements and is not
reachable**: `parse_bullet_rosters` returns nothing under the default heading
allowlist, and the `headings="."` override that fixed Iran's Majlis pages
returns 247 rows of which most are statistics — "Płeć: kobiety – 135", "Wiek:
poniżej 30 lat – 3". **A permissive heading override is not safe**, and this page
needs a real heading list or nothing.

Several PEP categories have no list article at all — the Supreme People's
Assembly is one — so the channel is a fallback rather than a guarantee.

## 9. P39 qualifiers

Closed sets per country, same principle as the position gazetteer:

| country | `P768` districts | `P4100` groups |
|---|---:|---:|
| Poland | 139 | 25 |
| Guatemala | **0** | **0** |

Guatemala has no items of either kind, so the qualifier cannot be asserted there
at all and the block is omitted rather than offered.

**Rendering decides whether the channel works.** A Polish constituency is
*labelled* by number and *named* by place in its aliases, while the evidence says
"okręgu legnickim":

| what the model was shown | proposals naming a district or group |
|---|---:|
| label + description | **1 / 130** |
| label + **aliases** + description | **56 / 117** |

A 28× difference, entirely in the prompt's prefix. All 56 were audited against
the article that proposed them: **56 correct**, including Warsaw II picked over
Warsaw I from a category reading "okręgu Warszawa II". The two the audit itself
flagged were its own crudeness — a five-character stem drops "Łódź", and the
first alias word is "Warsaw" where Polish says "warszawskim".

The set is **noisy** and was left so: it carries Senate constituencies,
historical 2001–2011 ones, and one outright settlement ("Imionki PKP"), because
the `P279` closure under `Q192611` reaches further than intended.

## 10. Bugs found by reading output

Every one silent, and the number that made each visible.

| bug | what it cost | how it surfaced |
|---|---|---|
| lxml `remove()` takes the element's tail | ~35% of every article's prose, mid-sentence: "added in July.indictment on four charges" (en body 9,321 → 14,277 chars) | reading one dossier |
| `endswith("wiki")` reads `commonswiki` as language "commons" | three copies, one feeding the live jurisdiction classifier a wiki community that does not exist | `langs=('en', 'commons')` in a log line |
| an **undated** recorded statement matched any dated proposal | every dated term a person was owed skipped as `already_recorded`; 31 of 42 Sejm seats are undated, so this was the loop's largest class of fix | 2 applies where 59 were expected |
| `byproduct` rendered as nothing | 87 of 117 records vanished, including every creation candidate and every surgical removal | counting the records that reached `edit_plan.md` |
| `Comparison.target_agrees` is False when the record is undated | a clean run read as **13/72** | the rows all said `recorded None None–None` |
| `accepted=` hid the person's existing tenures | the dossier said "do not propose anything already here" and listed nothing | `"tenures": [], "out_of_scope": 2` |
| `topics` is a `Dict[str, Set[str]]`, not a set | would have crashed on the first person with an accepted tenure | reading the same dossier |
| the retirable test used the pre-gate gap | 22 removable reported against 44 | building a real cohort |
| `contains` searched `fragments`, not the rendered dossier | a 2% false-negative rate — four *correct* proposals rejected for citing the officebox section this code prints itself | reading the four "hallucinations" |
| `for prop, gazetteer in qualifiers.items()` shadowed the parameter | Guatemala rejected its own target 12 times; Poland would have checked positions against 139 electoral districts | a second spec with empty qualifier sets |
| `for prop, qid in checked.qualifiers.items()` shadowed the statement's property | a committed `.qs` line reading `Q103056893 P768 Q19269361` — valid syntax, wrong statement | reading the rendered line |
| the qualifier block printed labels and not aliases | 1 district named in 130 proposals instead of 56 in 117 | comparing the block to the evidence wording |
| a merge routed to the API creates instead of merging | five duplicate claims in a rendered payload | pre-flighting against live claims |
| closing an open-ended statement read as a new tenure | four Polish seats would have doubled | the same pre-flight |
| a contradicted span read as an addition | one Polish seat, `2007–2015` against `2007–2011` + `2011–2015` | the same pre-flight |

The pattern is worth stating plainly: **thirteen defects, and not one was caught
by a test.** Every one came from reading real output or pre-flighting a payload,
and two were in `wd/` modules the workbench had been running for weeks.

They fail the same way: **the code looks right and the output looks plausible.**
A quote gate rejecting truthful citations looks like hallucination. A rebound
loop variable still renders valid QuickStatements. A `13/72` score looks like a
bad model. `recipes/enrichment_loop.md` §10 turns this into a working
discipline; `scripts/check_enrich.py` is where each one is pinned afterwards, 27
checks and offline.


## 11. The office index, and what retrieval can and cannot decide

*Measured 2026-08-24.* `wd/positions.py:index_for_country` — one SPARQL over
`rdfs:label`/`skos:altLabel` for every position item scoped to a state:

| country | name rows | items | size | time |
|---|---:|---:|---:|---:|
| Poland | 4,331 | 322 | 115 KB | 19 s |
| Spain | 115,551 | 13,197 | 2.8 MB | 29 s |

~13 names per item in every language, against the one English label
`wbsearchentities` ranks on. It builds at Spain scale in half a minute, which
is what makes the per-person path affordable.

### What the old matcher was missing

Two of the 79 offices `coverage/offices_named.md` queued for creation already
had items:

| queued as `create` | the item | why it was missed |
|---|---|---|
| Marshal of Warmian–Masurian Voivodeship | `Q140428371` | an en-dash. `wbsearchentities` returns the item for `Warmian-Masurian` and nothing at all for `Warmian–Masurian` |
| Minister of Family, Labour and Social Policy | `Q25919989`, aliased **"Polish Minister of Family, Labour and Social Policy"** | the name is a registered alias character-for-character; an English prefix search capped at 30 hits never surfaced it |

`wd/positions.py:norm_label` compounded it by stripping non-ASCII rather than
transliterating, so `Łódź Voivodeship` normalised to `d voivodeship`. It now
folds through `normality.ascii_text`.

### The whole Polish queue, scored

All 71 Polish `create` rows through the index — the full output read, not a
sample:

* **2 retrieve a covering match**, and they are exactly the two above.
* **0 retrieve nothing at all.**

That second number is the finding. Every one of the other 69 rows has a
plausible-looking top hit, so **a mechanical top-1 would be wrong 69 times out
of 71**:

| queued office | top hit | what it actually is |
|---|---|---|
| Mayor of Chełm | `Q177529` mayor, 0.50 | the occupation class |
| Chief Labour Inspector | `Q11788787` Chief Inspector, 0.50 | a different, generic office |
| Undersecretary of State in the MFA | `Q25598671` Minister for Foreign Affairs, 0.43 | the principal, not the deputy |
| Vice-Marshal of Podlaskie Voivodeship | `Q1558362` voivodeship marshal, 0.50 | generic *and* not the deputy |
| member of the Warsaw City Council | `Q111008336` chair of the city council of Warsaw, 0.60 | the chair, not a member |
| member of the Łódź Voivodeship Sejmik | `Q130582164` member of the voivodeship sejmik, 0.75 | the class, not the seat |

### The direction rule

Token *containment* fires on the generic cases because `{mayor} ⊆ {mayor,
chelm}`. So containment is scored in one direction only: **the candidate must
cover the query, never the reverse.** Under that rule all six rows above score
as non-covering and both real items score as covering. It is the rule most
likely to be relaxed later to raise the match count, and
`scripts/check_enrich.py` pins all six as negatives.

But the direction rule only separates *generic* from *specific*. It cannot
separate a **rename** from a **near neighbour** — `Q25919989` and
`Q107919654` both look like "fewer words, same subject", and one is the same
chair while the other is a sibling item. That judgement needs the item's
description, kind, polity, span and holder count, which is why retrieval ranks
and `prompts/office_rerank.md` decides.

## 11a. What a country gazetteer must not offer

*Measured 2026-08-24 on Czechia.* The raw `for_country` set is not a menu.
Of 194 entries, **50 were not choices at all**:

| dropped | why |
|---:|---|
| 34 | **ambassadorships.** The `P1001` arm of `COUNTRY_OFFICES` pulls in the *inbound* missions — `Q56761205` "ambassador of the United Kingdom to the Czech Republic" is a British office whose jurisdiction is Czechia. 29 foreign embassies accredited to Prague, offered to Czech ministers as though holdable. |
| 16 | **unheld non-positions** — `General of the Army`, `Národní umělec`, `General Staff of the Army of the Czech Republic`, and thirteen more ranks and bodies that `wd/shape.py` had *already* flagged `not_a_position`. |

194 → 144 entries, 12,748 → 9,265 prompt tokens.

Two things this cost to get right:

* **The obvious structural test for an inbound mission does not work.** "`P17`
  names a country other than the scope country" catches 16 Czech items and only
  one is an embassy — it also catches `Mayor of Brno`, `Roman Catholic Bishop of
  Olomouc` and `ministr hospodářství České republiky`, because those carry a
  `P17` inherited from a predecessor state. That is the documented "P17 on
  positions with historical states is a judgment call" gotcha, arriving as a
  wrong filter. Dropping *all* ambassadorships sidesteps it; a diplomatic lane
  passes `diplomatic=True` and scopes itself.
* **`FILTER NOT EXISTS { ?pos wdt:P279* wd:Q121998 }` times the query service
  out** (504, then a connection reset). The exclusion runs through
  `wd/shape.py:type_closure` instead, which is disk-cached and reads
  `p:P31/ps:P31` rather than truthy values.

The `not_a_position` rule needs a second signal: the shape check keeps
deprecated `P31` claims and so over-reports. `wd/gazetteer.py:is_offerable`
requires the item to *also* have no recorded holders — an item shape doubts
that people are nonetheless recorded in is an item shape is wrong about. That
spared `Q81514903` Czech primate.

## 12. The Czech ministers bucket

*Measured 2026-08-24.* `Ministři_vlád_České_republiky`, the first bucket spec
prepared for a run. Three defects had to be cleared before it could produce a
cohort at all, and none of them announced itself:

* **The spec declares `language: en` and names a cs.wikipedia category.**
  PETScan returns 0 members, and a spec with 0 members reads as an empty
  category rather than a broken query. **Six specs are affected**, all Czech,
  and all currently sweep in nobody:

  | category | en | cs |
  |---|---:|---:|
  | `Ministři_vlád_České_republiky` | 0 | 35 |
  | `Poslanci_Parlamentu_České_republiky` | 0 | 16 |
  | `Senátoři_Parlamentu_České_republiky` | 0 | **294** |
  | `Prezidenti_České_republiky` | 0 | 9 |
  | `Soudci_Nejvyššího_soudu_České_republiky` | 0 | 26 |
  | `Soudci_Ústavního_soudu_České_republiky` | 0 | 48 |

  **Fixed upstream the same day** (opensanctions `29a6c5dbb`), which moved
  those spec keys from `en:` to `cs:`. The two other
  non-ASCII `language: en` specs (`Members_of_the_Polish_Sejm_2023–2027`,
  the Slovak National Council one) are false positives — an en-dash in a year
  range — and resolve fine on en.

* **`depth: 0` on a category that is a shelf of subcategories.** The Czech
  ministers category holds 7 articles and 28 per-portfolio subcategories
  (`Ministři dopravy`, `Ministři financí`, `Ministři kultury`…). At depth 0 the
  cohort is 5 people; at depth 1 it is **335 members, 298 held, 11 todo**.

* **The dossier was reading the wrong wikis, and not only for Czechia.**
  `wd/dossier.py:pick_langs` falls back to a globally size-ordered
  `WIKI_PRIORITY` where `cs` sits 14th, behind `pl` and `uk`, and
  `scripts/enrich.py` never passed `prefer`. Three of the first five Czech
  ministers were about to be judged on their Polish, German and Ukrainian
  articles with the Czech one unread — the wiki whose category swept them in,
  so it exists by construction.

  The general fix is `wd/dossier.py:territory_langs`, which asks `rigour` what
  a country's languages actually are (`get_territory(cc).langs`, ISO 639-3,
  converted by `rigour.langs.iso_639_alpha2`; codes with no two-letter form
  are dropped rather than guessed at, and the survivors are ordered by
  `WIKI_PRIORITY` so `en` still wins South Africa's twelve). `scripts/enrich.py`
  now prefers `(spec.language, *territory_langs(country), "en")`.

  **This changes the second wiki for 19 of the 36 (spec-language, country)
  combinations in the yml**, and Czechia was the least of it. Every `en:` spec
  outside the anglophone world was reading **German** second, because `de` is
  second on a global size list:

  | spec | was | now |
  |---|---|---|
  | Crown princes of Saudi Arabia | en, **de** | en, **ar** |
  | Members of the Supreme People's Assembly (kp) | en, **de** | en, **ko** |
  | State Administration Council (mm) | en, **de** | en, **my** |
  | Greece, Yemen, Singapore, Belarus | en, **de** | en, **el / ar / zh / ru** |
  | Colombia, Ecuador, Guatemala, Nicaragua, Venezuela, Spain | en, **de** | en, **es** |
  | `ru:` specs for Crimea | ru, **en** | ru, **uk** |

  A German article on a North Korean legislator is not a second channel; it is
  a stub translated from the first. The specs that do not move are the ones
  where the old default happened to be right — `us`, `au`, `de`, `eu`, and
  every spec already written in the country's own language.

`--language` and `--depth` overrides exist on `scripts/enrich.py` so a spec can
be tested before the yml fix is filed.

### Why this is the right calibration country

298 held members is a labelled test set for the question no run has asked: with
194 offices in the gazetteer, does the loop name the one the record uses? Five
dossiers checked by hand hide 14 in-scope tenures between them — Transport,
Human Rights, Foreign Affairs, Justice, Agriculture, two regional assemblies, a
governorship, both chambers — with **0 leaking back into the evidence**.

And at 194 items Czechia can run *both* paths over the same people: the
whole-country cached prefix, and retrieve-and-rerank. Spain can only run the
second, and there is nothing there to compare it against.

**The numbers themselves are not measured yet** — the run needs an API key that
was not available in the session that built this. `scripts/enrich.py --backtest`
prints them: reachability, choice accuracy, and how often the loop named
nothing.

## 13. A gap that was a superclass — US Supreme Court justices

*Measured 2026-08-24.* `en:Justices_of_the_Supreme_Court_of_the_United_States`,
the first US spec run, and it produced **no enrichment work at all** — for a
reason no disposition in `coverage/petscan_specs.md` names.

The spec targets **`Q20706330` United States Supreme Court justice**, and the
target passes every check the toolkit applies to a target: `verify_all` reports
`defects=[]` and `os_notes=[]`, `topics=[gov.judicial, gov.national, role.pep]`,
`P1001=Q30`, `P361=Q11201` Supreme Court of the United States. It is emittable,
correctly scoped, and attached to the right body. It is also **not the office**:

| item | `P31` | `P279` | holders |
|---|---|---|---:|
| `Q20706330` US Supreme Court justice | `Q16533` judge, `Q4164871` position | `Q55736868` national supreme court judge | **2** |
| `Q11144` Associate Justice of the SCOTUS | `Q294414` public office | `Q20706330` | **104** |
| `Q11147` Chief Justice of the United States | `Q294414`, `Q12737077` | `Q20706330`, `Q3188089` | **19** |

`Q20706330` is the **parent class of the two seats**, which is why it has two
holders and its children have 123. So the cohort split against it reads

    members 101, held 1, todo 12, dropped 88 (85 born-before-1920, 3 long-dead)

and every one of those 12 already holds `Q11144`, dated, nine of them already
emitting as PEPs. Re-run with `target=Q11144` and `targets=[Q11144, Q11147]`:

    members 101, held 100, todo 0, dropped 1

**The 12-person gap was entirely an artefact of the target naming a class rather
than a seat.** Had the run trusted it, the loop would have proposed a superclass
P39 to twelve people who already hold the child — the `duplicate_office_item`
failure with the parent standing in for the sibling.

Three things worth carrying forward:

* **A phantom gap looks exactly like a real one, and the target audit cannot
  see it.** Every property `wd/shape.py` reads is right on `Q20706330`. What
  gives it away is *arithmetic between items*: a target whose `P279` children
  are themselves positions carrying two orders of magnitude more holders is not
  the office its members hold. Nothing measures that today, and it generalises
  past this spec — a class-as-target produces a gap on every member.
* **The holder count is the cheap tell.** 1 of 101 members already holding a
  well-documented office is not a coverage gap in the world's most heavily
  edited judiciary; it is a wrong item. Read `held` before scoping, not after.
* **The spec's own sibling already had it right.** `Chief_justices_of_the_United_States`
  targets `Q11147` and is on the retirable list at 17/17. One category of the
  same court, two targets, one of them a class.

The category also contains two non-humans (`Q1780882` the list article,
`Q6994955` a category page) — the PETScan `P4224` leak, caught by the cohort's
own `P31=Q5` re-check, as designed.

### What the run found that is worth an edit

One member, and it is the source of `Q20706330`'s two holders:
**`Q956007` James Iredell** (associate justice 1790–1799) carries
`P39 = Q20706330` — the class — where his 100 colleagues carry `Q11144`. The
other holder, `Q437855` Robert H. Harrison, was confirmed to the Court and
declined the seat, so his statement is a different question and not this run's.

Fixing Iredell is a **value change, not an addition**, so it is a stop-and-ask
under the workbench's rules rather than anything a batch carries. He is also
pre-1920 and `zavod` declines him regardless: this is a Wikidata correction with
no PEP consequence, which is the ordinary case for a category like this one and
not a reason to skip it.
