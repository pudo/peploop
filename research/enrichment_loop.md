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

| country | position items |
|---|---:|
| Lesotho | 62 |
| Czechia | 194 |
| Iran | 200 |
| United States | 5,005 |

So yes for a sweep target, and the US is the outlier rather than the shape.
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
