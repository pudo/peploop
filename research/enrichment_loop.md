# Measured: enriching one person at a time

The evidence behind `recipes/enrichment_loop.md`. That file says what to do;
this says what was counted, what it cost, and which of the counts are one run
wide and should not be generalised.

**Measured 2026-08-23.** Three kinds of evidence, kept apart because they age
differently:

- **Population counts** over `wd_categories.yml` and Wikidata, re-runnable with
  `scripts/spec_report.py` and `scripts/retirable.py`.
- **Run results** — two specs, one of them n=3. Read the caveats in §6.
- **Bugs found by reading output**, each with the number that made it visible.
  These are the durable part: every one was silent, and most were in code the
  workbench had been running for weeks.

## 1. The population

`wd_categories.yml` has **594** PETScan specs. **284** attach a synthetic
position (`h.make_position`, `wd-cat` hash id, no Wikidata identity) and **239**
of those carry a resolved `wikidata_id` — **209** unique target QIDs, holding
**63,353** P39 statements between them.

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
| cost | $0.34 total | ~$0.04 per person |

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

## 6. What not to generalise

- **Two specs, one language family each.** Both are single-office specs where the
  gazetteer holds one item, so **position association was never actually
  tested**: there was nothing to choose between. The 24 `bucket` specs are where
  that question lives and none has been run.
- **Legislature membership is the easy case.** One item, no succession, and every
  member's term shares the same boundaries, so target and date agreement are
  close to free. A good Poland score is necessary, not sufficient.
- **`45 proposals for other offices` is not a creation list.** For a
  single-target gazetteer every other office is unresolved by construction, and
  "Senator of the Republic of Poland" plainly has an item.
  `wd/positions.py:lookup_position` has to run over those names before any of
  them is called a creation candidate.
- **Every statement cites only a Wikipedia permalink** (`S4656`, no `S854`).
  `wd/validate.py` warns, correctly. Poland's batch is 18 of 19 at year
  precision.
- **Nothing has been applied to Wikidata**, so no post-write verification exists.

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

## 9. Bugs found by reading output

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

The pattern is worth stating plainly: **not one of these was caught by a test,
and every one was caught by looking at real output.** Two were in `wd/` modules
the workbench had been running for weeks.
