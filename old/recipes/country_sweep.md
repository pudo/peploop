# Recipe: sweeping one country's PEP landscape into verified Wikidata statements

How to take a country and turn what its wikis record about the people who run
it into P39 (and P53, P102, …) statements Wikidata can carry — autonomously,
end to end, with **two** files as the deliverable (§8). Derived from seven runs,
counted as the statements they actually write:

| run | scope | rows → statements | what it proved |
|---|---|---|---|
| Ecuador | 17 specs, ministries | ~1,900 → 177 | items existed but were nearly empty; roster-first works |
| Belarus | 15 specs | → 16 | already covered; the real channel was a wiki the config didn't name |
| Czechia | 13 specs, 21 offices | 486 → 18 | essentially finished; yield was parser bugs and creation lists |
| Spain | 7 offices | 1,044 → 111 | one office is many items; routing is by *date* |
| UAE | 13 offices, incl. 7 rulerships | 573 → 94 | hereditary power; ar.wiki as the primary channel; P53 as a concern |
| Saudi Arabia | 13 offices + a kinship lane | 623 → 40 | the dynasty *is* the lane, and it is not an office; Hijri dating caps what a roster can yield |
| Kuwait | 25 offices, incl. 4 legislative term rolls | 620 → 370 | the largest yield so far, and the run that found QuickStatements cannot write a person's *second* tenure at all (§8) |
| Jordan | 7 offices + a kinship lane, 98 per-cabinet sources | → 220 + 161 | a whole institution dated by its cabinet articles rather than by a roster |
| Qatar | 44 offices + a kinship lane, 21 items minted | 222 → 69 | **a country that publishes no rosters.** Two of its 32 ministry articles date a minister; the channel that reached the rest was the *holders'* own infoboxes (`wd/officebox.py`), and the diplomatic lane had to mint its items before it could write anything |

The engine is `wd/campaign.py`; a country script is only parameters
(`scripts/ec_ministers.py` is the simplest shape, `scripts/es_offices.py` the
richest succession routing, `scripts/ae_offices.py` the broadest lane mix).
**Expect the target census in §2 to tell you how much there is to win** —
where the items already carry thousands of holder statements, the yield is
small and the useful output is byproduct lists and parser hardening, not the
batch.

Follow this instead of re-deriving per country. Each step says what to run,
what the output is for, and what went wrong the first time.

## The contract

**A campaign is finished when every institution has a disposition, not when a
batch is validated.** Scope against `recipes/institutions.md`, record the answers
in `coverage/<country>.md`, and close only when no row reads `deferred` and every
`blocked:` points at a named issue. The `.qs` is an output, not the finish line.

This is the same discipline `wd/policy.py` already applies to rows, moved up one
level. Until it was, eleven campaigns each produced a validated batch and closed
while whole FATF categories went untouched — judiciary in 0 of 11, SOE and
sovereign wealth in 0 of 11, party officials in 0 of 11, mayors nowhere at all.
`coverage/README.md` has the matrix; the point of it is that none of that was
visible from inside a campaign that was, on its own terms, complete.

Two corollaries worth stating, because both were violated in practice:

* **A byproduct list does not close an institution.** Roughly 150 office items
  have been listed for creation across nine campaigns and 23 minted. A row
  reading `⊘ creation-first` is unfinished work, not a disposition.
* **An institution nobody looked at cannot be reported as absent.** `no-source`
  requires a measurement. "Not attempted" is not an available answer.

A sweep is **99% autonomous**. It runs survey → rosters → policy → backtest →
render without a human checkpoint, and the human sees exactly one thing: the
finished batch, reviewed whole in the QuickStatements importer before upload.
Concretely:

* **One `.qs` per campaign, plus one claims file.**
  `data/<country>/edit_plan.qs`, validated by `wd/validate.py` at render time, is
  the deliverable; `edit_plan_claims.json` carries the statements
  QuickStatements *cannot* write (§8) and is reviewed with it as one batch. The
  renderer no longer shards by concern — the file the reviewer approves must be
  the file they read end to end — and the second file is not a shard: it is a
  property of the write path, not of the evidence. `decision.concern` stays on
  the record and groups `edit_plan.md`.
* **Every case gets a disposition.** `wd/policy.py` decides each candidate by
  an ordered rule table; the campaign's `dispositions` maps any rule that
  would default to `hold`/`review` onto `skip`, so `edit_plan.md` is an
  account of what was decided and why — never a queue. If you want a tier a
  human can rule on later, write the rule instead. The corollary is that
  conservatism lives in the rules: nothing is relaxed to raise the count, and
  a lane with one weak channel is reported small rather than padded.
* **The audit and the backtest are the run checking itself**, not documents a
  human is expected to work through. A human *may* spot-check them; the run
  must be correct without that.
* The human gates that remain: running the `.qs`, running
  `apply_claims.py --apply` and `create_offices.py --apply`, and anything
  destructive (merges, deletions, statement removal, rank changes) — those are
  wikibase-cli lists in `tasks/followups.md`, never lines in the batch.
* **Never trust a checkbox about whether a batch was applied.** Three of them
  were wrong at once — the UAE, courts and positions were all live while
  `followups` called them pending, and the UAE's whole batch had gone in a month
  earlier. Diffing a `.qs` against Wikidata is cheap: for each line ask whether a
  statement with that subject, property, value *and dates* exists. The revision
  history settles it beyond doubt (`#quickstatements` in the comment, the
  timestamp identical across every subject in the batch).

## Scope: the FATF landscape, not the ministry list

The target is the country's **politically exposed persons** under FATF
guidance, which is wider than the cabinet: heads of state and government;
ministers and their deputies; legislators; apex-court judges; central bank
governors; senior military leaders; **royal and ruling families**;
ambassadors; senior executives of state-owned enterprises; senior party
officials. Survey all of it; run what has a channel.

Where the power actually sits varies by country and the sweep should follow
it, not the org chart western defaults assume. In the UAE the ministries were
the *least* interesting lane: the emirate rulerships, deputy rulers and crown
princes — hereditary offices whose categories were empty — held the value,
and ruling-house membership (P53) shipped 36 of the 94 statements. A
`wd_categories.yml` country block, where one exists, is one input among
several; the UAE's two catch-all specs contributed almost nothing.

**SOE and sovereign-wealth leadership needs its own census before you commit
a lane to it.** Wikidata's dominant convention for executives is a generic
role item + `P108 <org>` (~17k statements), which OpenSanctions cannot see —
its PEP build reads only P39 and drops positions with no country. Dedicated
"Chairman of X" items are the only path that works and they are rare (~20 on
all of Wikidata, none in the UAE). That makes SWFs a *creation-first* lane —
the office items, sometimes the org items, must exist before a sweep can
propose anything — and until then the census's findings are followups, not
statements.

## 1. Survey the landscape

Start from **`recipes/institutions.md`** — the checklist of institution classes —
and walk every one of them, asking: which offices exist, which have Wikidata
items, which have categories, which have rosters. Write the answers into
`coverage/<country>.md` as you go, **including the classes the country does not
have and the ones with no obvious source**; those rows are the deliverable for
those institutions.

Do not scope from the campaign's own name outward. The three narrowest campaigns
in the repo are the three called `*_ministers.py`, and Ecuador's nineteen offices
are nineteen cabinet portfolios with no president, no legislature and no courts. Then measure the categories at **depth 0, 1 and 4**:

    /Users/pudo/.python/wrangle/bin/python scripts/petscan.py --lang es "Ministros_de_Ecuador" --depth 1

* **depth 0** for head-of-state/government categories. Deeper pulls in
  eponymous subcategories and relatives — `es:Presidentes_de_Ecuador` goes
  84 → 363 at depth 4, adding *children of presidents* and colonial governors.
* **depth 1** where the subcategories are *terms* or *portfolios* (§3).
* enforce `P31=Q5` yourself: PETScan's "uses Q5" filter passes `Category:`
  items via P4224 (37 of 764 hits in Ecuador).

Join the member universe against existing P39s for the honest gap: how many
hold no position scoped to this country at all (UAE: 1,876 nationals, 120
with any P39).

**Follow the interwiki siblings, and expect the home-language wiki to be the
primary channel, not a supplement.** `en:Government_ministers_of_Belarus` has
35 members, its Belarusian sibling 243; arwiki holds 1,311 UAE sitelinks
against enwiki's 870, and ruler categories for four emirates where en has
none. Resolve the category page to its Wikidata item and harvest every
sitelinked sibling (`campaign.sibling_categories`). It also imports that
wiki's own noise: `uk:Прем'єр-міністри_Білорусі` files every Byelorussian SSR
council chairman as a prime minister of Belarus.

## 2. Inventory the targets — and fix the item layer first

Run `scripts/position_metadata.py --country <cc>` first and read
`recipes/position_items.md` beside it: the census below finds which offices have
items, and that one says whether the items are *modelled right*. The two questions
are not the same. Iran's audit found **54 of 323 items that say "position" and
never say what kind** — under-modelling no holder count reveals.

One SPARQL census of every position item the country owns, with holder counts:

```sparql
SELECT ?pos (COUNT(DISTINCT ?h) AS ?holders) WHERE {
  { ?pos wdt:P17 wd:Q736 } UNION { ?pos wdt:P1001 wd:Q736 }
  ?pos wdt:P31/wdt:P279* wd:Q4164871 .
  OPTIONAL { ?h p:P39/ps:P39 ?pos }
} GROUP BY ?pos
```

**Count with `p:P39/ps:P39`, never `wdt:P39`.** The truthy predicate returns
only preferred-rank values, so one preferred statement hides every other
position the person holds. Measuring Czechia the wrong way reported 7,554
holder statements against a real 14,124, and offered an add for a statement
that already existed. `campaign.holders()` gets this right.

**Type filters are unsafe as gates.** The UAE's seven Ruler items split
across two `P31` conventions (one emirate carries `Q4164871`, six carry
`Q294414`, one both) and four government *bodies* carry no `P31` at all — a
`P31`-closure would silently drop most of the country. Use the census to
*find* items, never to reject them.

Read the result before planning anything. It tells you which offices already
have items, which are **list articles mistyped as positions**, which are
**generic items doing duty for a country office** (Q83307 "minister", one
item literally meaning "incumbent"), and which offices are missing entirely.
Missing items are a creation lane (`archetype` + `body` +
`scripts/create_offices.py`), not a blocker. Expect real gaps in surprising
places: 19 of the UAE's 35 emirate-office cells (ruler / deputy ruler / crown
prince / executive council / ruler's representative, per emirate) had no
item, including offices with living, sitting holders. Measure the existing
items' *shape* while you are here (`wd/precedent.py` on exemplars) — labels,
P279 parent, P361 body, P1001 — because anything the campaign creates must
match the convention the country already uses, and because bulk-created items
often carry nothing at all: none of the UAE's 34 ministerial items has an
inception date, so a succession there can only be derived from holders'
`P580`s, not from the items.

### 2a. Then ask whether the office is one item or several

**Do this before writing a single `target=`.** In Spain it is normal for one
office to be a *succession* of items, and a target chosen without checking is
wrong for most of the roster:

* ministries are renamed with almost every cabinet and Wikidata models each
  name (Ministro de Estado → Asuntos Exteriores → …y de Cooperación → …,
  Unión Europea y Cooperación), so the target is a function of the *date*:
  `Office.date_targets`;
* the same office can have era items nobody labelled as such — Q45213921
  "President of the Congress of Deputies" *is* described as 1876–1923, but
  Q43118787 (Cortes republicanas) and Q43138757 (Cortes franquistas) are not
  described at all, and were found only by looking;
* two items can compete for the *same* era, which is a merge decision and not
  a campaign: Spanish labour has both a long-running "Minister of Labour" and
  a 2018–2020 ministry name carrying holders from 1919. Declare no office at
  all; the merge goes on the followups list.

The measurement that answers it: for each portfolio category, tally its
members' P39 values split at the modern cutoff, then take the era profile of
every candidate item (`wd.precedent.census`, `starts` bucketed by era). An
item whose terms *stop* where another's *start* is a succession; two items
covering the same years are a conflict. A rename chain can also be proved
from one person: Noura Al Kaabi holds two of the UAE's three culture items
with non-overlapping starts.

**Never map an unproven rename.** The UAE cabinet page carries 89 distinct
office-cell values; 40 route to an item and 49 route to `""`, becoming
creation byproducts. "Minister of Energy" is *not* filed under "Minister of
Energy and Infrastructure" — a plausible rename, but unproven, and the run
does not guess.

**Where the same office really has two items in parallel use, expect the
roster rows to be on record under the other one.** `already_under_sibling`
flags that as `duplicate_office_item` and skips it — 44 Spanish rows, 21 of
which the engine was otherwise about to add a second time *and* qualify as
acting, because a spell sitting inside the sibling item's span also trips
`interim_of`.

## 3. Lane the offices

**The census in `recipes/institutions.md` is the spine; this table is not.** What
follows is how you *run* an institution once the ledger says it exists — a
mechanic, not a taxonomy of a country. Laning by shape is what let an institution
with an awkward shape stop being mentioned: it never appeared in a lane table, so
it never appeared as uncovered either.

Every lane below is an attribute of a `coverage/<country>.md` row, and every row
needs one — including the rows whose shape is "no channel found", which is a
measurement to record rather than a lane to skip.

| lane | shape | how to run it |
|---|---|---|
| single office | "President of X", one item | roster + category, §4 |
| succession | one office, several era items | same, routed by `date_targets` (§2a) |
| body membership | "Member of the X Assembly" | same, plus era routing when a predecessor chamber exists |
| **bucket** | "Minister of X" = any portfolio | check whether the wikis subdivide by portfolio — if so it is mechanical, not per-person |
| hereditary | rulers, crown princes, royal houses | the roster *is* the succession; add `family` for the P53 backfill — office and surname are two independent assertions and both must agree |
| **dynasty** | a royal house of hundreds, most of whom hold nothing | not an office at all: `wd/kinship.py` over a genealogy article, §4a |
| creation-first | offices/bodies with no item (SWFs, new courts) | `archetype` + `body`, `create_offices.py`, then run like any other |
| catch-all | "Politicians of X", "Political office-holders" | a generator, never a lane: resolve its members onto real offices, and record what is left as the item-creation byproduct it is |

The bucket lane is where ministerial volume is, and the trick is that both
wikis usually subdivide the minister category by portfolio
(`Ministros_de_Salud_Pública_de_Ecuador`). List subcategories with
`list=categorymembers&cmtype=subcat`. Portfolio subcategory + portfolio item
= a target per person, with no per-person office guessing.

## 3a. Triage the blockers before you run a single lane

**Half of everything ever deferred was blocked on one thing in `wd/` or
`scripts/` that a single change would have unblocked** — 21 deferrals on item
creation and 14 on a shared parser gap, against 11 that were genuine scope
decisions. A blocker is not a property of the lane that happened to hit it; it is
a toolkit gap whose cost is paid by every lane it gates, and it should be fixed
before any of them run.

**The promotion rule: a workaround appearing in a second campaign is a toolkit
gap.** Not a clever fix to copy — evidence that something is missing. Three of
these are on record:

* `wd/create.py` has no non-ruler *deputy* archetype and no *governor* archetype.
  Kuwait dropped three offices over the first; Iran's 27 governorships and Iraq's
  workaround (`iq_offices.py` reusing `provincial_governor` "for its description
  template only") are the second, and neither campaign promoted it.
* The `{{Tree chart}}` genealogy shape defeated `wd/kinship.py` in **Kuwait and
  Jordan**, and Jordan's plan cites Kuwait's deferral as precedent rather than
  resolving it: *"if the tree-chart reader is ever built it unlocks both at
  once."* It was not built.
* RTL-reversed date ranges were deferred by Kuwait, then by Jordan citing Kuwait.

The sizing case is Iran. `parse_bullet_rosters` was blind to Persian in three
independent ways and gated **~3,300 statements across three institutions**. It was
documented in the plan *before* execution, recorded as "a bounded change this run
does not make", and the first batch shipped at 224 statements. Making the change
took the same run to 688. **The gap was known, sized and skipped**, which is
exactly what this section exists to stop.

Iraq is the counter-example that shows the ordering works: its Levantine month
names and column vocabulary were scheduled as a serial parser phase *before* the
lanes, and its ministry pages went from "38 rows, 0 dated" to "38 named, 38
dated" before anyone tried to harvest them.

Run it as one serial change with one owner, graded by `scripts/check_dates.py`.
`wd/roster.py` is shared state; parallel agents must not touch it.

## 3b. Mint the items first, not last

Choose the archetype against `recipes/position_items.md`'s `P279` table before
minting, not after — the parent is what says *which kind* of office this is, and an
item minted without one looks done while telling nobody anything. Pick the parent
that describes the office and nothing else: typing an ordinary judgeship as
`Q117826617` supreme court judge to make a consumer emit it corrupts the data and
the corrupted item then looks correct everywhere. Where no archetype fits, §10
says measure before minting.

**A creation-first institution has zero coverage by definition**, and creation is
the only step that cannot be hurried because it needs a human. Scheduling it last
is why it is always the thing left undone:

* ~150 office items listed for creation across nine campaigns; **23 minted.**
* `create_offices.py`'s `SCRIPTS` dict is missing `jo`, `kw` and `ir` — **the
  three campaigns with the largest creation lists.** Each plan instructed the
  wiring; none of them did it.
* Iran's governor lane has **778 of 903 rows** behind the gate.
* Qatar was the first campaign ever to run `--apply`, and doing so immediately
  exposed a description-template bug that would have written "diplomatic post of
  Q846" into every item — meaning every earlier campaign's creation list was
  written against a path that produced garbage and nobody knew.

Mint, verify the shape against existing siblings with `wd/precedent.py`, then
harvest. An institution whose items were minted but never populated is still
unfinished.

## 4. Find the rosters (this is the leverage)

Many wikis keep a dated table per office — `Anexo:Ministros de Trabajo de
Ecuador`; eswiki puts them in namespace 104 (`Anexo:`), most wikis in ns 0:

    action=query&list=allpages&apnamespace=104&apprefix=Ministros de

A roster gives, in one fetch: every holder, exact dates, the appointer, a
**per-row citation**, and a colour legend marking acting officials. That is
strictly more than N biographies restating the same table, so **verify
roster-first, not person-first**.

Rosters hide in three places, in descending order of quality:

1. **a dedicated list article** per office (`Anexo:Ministros de …`,
   `List of rulers of …`);
2. **the office article** (`Министр иностранных дел Республики Беларусь`,
   `ar:نائب حاكم دبي`), which often tabulates each regime's holders in its
   own section — and for some offices (UAE deputy rulers, crown princes) is
   the *only* source in any language;
3. **the ministry article**, holders bulleted under "Министры"/"Руководство"
   (`parse_bullet_rosters`). Weakest: bullets rarely footnote their rows, so
   those statements source to the roster permalink rather than a citation —
   0 of 10 in Belarus against 81 of 97 in Ecuador. The audit records the
   ratio; it is a real quality difference (UAE: 2 of 94 statements cite
   anything outside Wikimedia, because its two spine pages carry zero refs).

Probe candidates by parsing them and counting rows that carry a *date*: a
page yielding undated rows is usually a navbox or a link farm. `office_rows`
drops a table with no date *column* for the same reason. Watch for
**redirects** — `Anexo:Ministros del Interior` → `…de Gobierno`, and the UAE
rulers page is the target of six — two offices pointing at one page will
double-propose it unless each reads it behind its own `headings` filter. One
page can also legitimately serve many offices: the UAE's eleven ruler tables
live on a single list article, one office per `headings` pattern, because an
office needs its own entry to carry its own `family`.

`wd/roster.py` parses rendered HTML (`wd.wikipedia.fetch_html`), because
`rowspan` is load-bearing. It returns `Roster(heading, columns, rows,
legend)` with `RosterRow(name, link, start, end, incumbent, acting, section,
appointer, ref_urls, covering)`, plus `merge_terms()` and `names_match()`.

**The two-channel gate**: a statement is batched only when two independent
signals agree — category + roster row, or a roster row whose identity is
asserted by a wikilink / corroborated by its own citation (§6). Single-weak-
channel candidates are skipped with a reason.

### 4b. When there is no roster at all

Some countries do not publish one. Qatar dates a minister on **two of its
thirty-two ministry articles**, across both wikis — the roster channel reaches
the throne and the central bank and stops. Before concluding that such a country
is simply undocumented, look at it from the other side: instead of an office
naming its holders, a holder names their offices, and
`{{Infobox officeholder}}` has an `office`/`term_start`/`term_end` grammar that
says the same thing one person at a time. Qatar's holders' own infoboxes carry
**227 dated tenures**, 141 of them on ar.wikipedia.

`wd/officebox.py` reads them and returns `RosterRow`s, so identity resolution,
`target_for` routing, the backtest and the policy table apply unchanged; an
office opts in with `Office.officebox = ("ar", "en")`. Four things decide
whether it is safe:

1. **It is one channel and never two.** An infobox is written by whoever wrote
   the article and corrected by nobody in particular. `officebox.two_channel`
   applies only where the office's *own* category names the person too, and
   `officebox.one_channel` skips the rest — which is why this is one `Office`
   per portfolio and not one cabinet bucket: in a bucket, "in some ministerial
   category" would satisfy the gate for a portfolio the category never
   mentioned.
2. **Route the office string, never default it.** One person's box lists every
   office they held, so each portfolio's `section_targets` claims its own and
   ends with the catch-all `r""` → `""`, meaning *no item*. Left out, every
   other office in the box lands on this one.
3. **Read the field names the template actually uses.** Arabic officeholder
   boxes use `المنصب` / `بداية الفترة` / `نهاية الفترة`; the bare stems `منصب`
   and `بداية` look like the same fields and match a sixth as many articles.
   Measure both before believing a low count — this one was under-read
   six-fold at survey time and the whole lane was nearly scoped out on it.
4. **Cite the article, not the office.** Each row's source is the revision of
   the *person's* page, so unlike a roster lane there is no single permalink;
   without threading it through, these statements render unreferenced.

Deliberately not read: `{{Infobox person}}`, whose `title` is a job description
rather than an office, and any box populated from Wikidata — reading that back
manufactures agreement between a claim and itself.

## 4a. When the family is the lane, not the office

Where power is dynastic, the office lane reaches only the fraction of the house
that held office — 81 of the 411 people carrying `P53 = Q31711`. The rest are
documented, densely, in one place: a **genealogy article**. `wd/kinship.py`
reads one (`en:Descendants of Ibn Saud`) and `scripts/sa_family.py` supplies the
parameters; the records go into the campaign's own batch through
`Campaign.extra_verdicts`, because one campaign still means one batch.

What makes it mechanical is that **the heading is the assertion**. A section
headed with a wife's name says "these are her children"; one headed
"Patrilineal grandsons" says "each of these has a father who is a son of the
ancestor", which closes the candidate set for a patronymic to a few dozen people
instead of to Wikidata. Three properties, three shapes of second channel:

* **P25** — the section names the mother, and her *item* is confirmed from
  somewhere else: a `{{main}}` hatnote, or two or more of the section's own
  children already recording her. Gated further on the child already recording
  the father, so the statement joins a parentage instead of asserting one.
* **P22** — the patronymic resolves to exactly one member of the generation the
  heading names, who could have fathered them (`FATHER_MIN_AGE`, death year).
* **P53** — the article lists them as a descendant *and* their own name or
  recorded parentage says the same.

Four things this cost, all of which would have shipped silently:

* **Take the chain from the item, not from the printed name.** The article prints
  "Abdul Aziz bin Fahd"; the item is "Abdulaziz bin Fahd bin **Turki II** bin
  Abdulaziz Al Saud". On the short form that resolves to King Fahd; on the long
  one to a different man a generation down. `child_chain` unions every spelling
  and takes the longest, and refuses where two spellings disagree.
* **A shorter spelling of the *father's* name must not satisfy a grandfather
  check.** The alias "Khalid Al Faisal" chains to one element, the length test
  short-circuited, and "Sattam bin Khalid bin Nasser" was filed under Khalid bin
  Faisal — the right generation, the wrong man.
* **A lifespan inside the name part poisons the chain.** "(born 1973)" precedes
  the description separator, so the father's name parsed as "fahd born 1973" and
  matched nobody.
* **One link in two generations is a wiki error, not a fact.** Detect it
  (`contradictory_links`) and skip both entries: the heading is what closes the
  candidate set, so a person under the wrong one is resolved against the wrong
  generation entirely.

A second article shape, from `en:Hashemites`, where descent is stated by
**indentation** rather than by heading — a wife's bullet, her children nested
under it, theirs under that. Three things it added:

* **The enclosing bullet is the assertion, exactly as a heading is.** Nested
  lists render *inside* their parent's `<li>`, so a flat `./li` walk returns the
  four wives and loses the seventy people the article exists to place. Carry the
  nesting down (`Listed.depth`, `parent`, `parent_link`) and `mother_records`
  takes a bullet-rooted group with no change at all.

* **The gloss beside a name describes a different relation from the nesting.**
  Hamzah is nested under Queen Noor — she is his mother — and annotated "(The
  King's half-brother)", which is his relation to the *reigning* king. A parser
  reading the parenthetical emits sibling edges where the article asserts parent
  edges. Read structure; cut the gloss off the name (`glosses=True`), including
  the ones the description separator has already truncated mid-bracket, and keep
  a regnal marker, which is the one parenthetical that *is* part of a name.

* **One bullet can name a couple, and the second half married in.** Split
  "[[Hamzah]] and [[Princess Basmah]]" into two entries pointing at each other,
  and mark the second `married_in`: they are *listed* under the bullet above
  without descending from it. Left unmarked they cost one wrong statement and
  eleven wasted skips — a wife's married name ("Princess Ghazi of Jordan") read
  as evidence of her own descent, and every in-law resolved against the wrong
  parent. Detect the couple from the links joined by nothing but "and", never
  from the word alone: "two links in one bullet" also matches
  "[[Muhammad bin Fahd]] … governor of the [[Eastern Province]]", which entered
  a province as a person and married it to a prince.

`P26` is emitted from such a pairing only where the article also nests children
under it — the pairing alone is one channel — and in one direction, because it
is bot-reciprocated like P40.

And one ceiling worth measuring before promising anything: **10 of Ibn Saud's
~22 wives have no Wikidata item**, and they hold 20 of the missing mothers. A
parent with no item cannot be the value of anyone's `P25`, so that half of the
lane is *creation-first*, exactly like the UAE's sovereign wealth funds. Report
it as a byproduct list with the children named, not as a lane that underperformed.

Deliberately not emitted, and worth deciding once rather than per country:
**P40** (the bot-maintained reciprocal of P22), **P3373** (combinatorial, and
redundant once both parents are recorded — the Sudairi Seven alone would be 42
statements), and **P26** where the evidence is prose about cousin marriages.

## 5. Resolve identity, then gate it

Ladder, strongest first:

1. the roster row's own **wikilink** → title → QID (`pageprops`, redirects
   followed). Wikipedia asserted this identity; take it.
2. the bare name as an **exact article title**.
3. **truncated titles**: rosters print all four Spanish name parts while the
   article sits at two or three.

Rungs 2–3 are nobody's assertion, so they must survive three gates — each of
which caught a real false positive:

* **citizenship**: no contradicting P27 (killed "Carlos Pérez García", a
  Spanish footballer, proposed as energy minister)
* **lifetime**: born ≤ term start − 18, died ≥ term start (killed Ángel
  Polibio Chaves, 1855–1930, proposed as 1998 labour minister)
* **political marker**: any P39/P102, a political P106, or a description that
  reads political (killed es.wiki's "Ernesto Albán", a comedian)

Name comparison is token-based, accent- and hamza-folded, never substring —
and **ordered, with matching regnal numbers, wherever a patronymic connector
appears**: "Rashid bin Humaid Al Nuaimi" and "Humaid bin Rashid Al Nuaimi"
are a real father and son, both Rulers of Ajman, and token *sets* match them.
Rejected identities stay visible in the audit as `no identity`; they are the
item-creation byproduct, not waste.

## 6. Policy: every row decided, by rule

Every candidate becomes an edit record (`wd/record.py`) carrying its
statements, the **flags** describing it (a set — a row can be acting *and*
pre-cutoff *and* roster-only), and a **decision** naming the rule that made
it. `wd/policy.py` holds the ordered rule table; first match wins; every
disposition is traceable to one line. **Nothing is escalated per case.**

**Rule order is load-bearing.** Rules answering "does this claim belong on
this item at all" (`era.distinct`, `duplicate_office_item`,
`early.unsupported`) precede rules answering "what kind of tenure was it"
(`acting`, `interim`), and the general `modern.two_channel` rule comes last
of the applying rules or it swallows the specific tiers and drops their
qualifiers. Both mistakes were made within an hour of each other; the table
in `wd/policy.py` is grouped and commented by the question each group answers.

The defaults that used to be open questions, now decided and measured:

* **Acting spells apply, qualified `P2868 = Q4676846`** — the documented
  convention is the office plus the qualifier, not a separate item. Worth
  knowing: the measured items barely use it (2 acting-qualified statements
  across the 88 targets of the first four campaigns), so the rule follows the
  convention rather than the tally; a country whose exemplars contradict it
  overrides once in `dispositions`. Read the acting marker only from a legend
  or a page that declares its convention (§7: italics are emphasis except
  where the page says otherwise).
* **`interim_concurrent_office` applies with the same qualifier**: a short
  spell falling entirely inside a dated term the person holds elsewhere is
  cover, and is recorded as acting. Two channels are required — the spell is
  short *and* concurrent — and `concurrency_ignore` must name the offices
  whose overlap means nothing, or the rule misfires: parliamentary seats
  everywhere, and in the UAE the rulerships and federal executive offices,
  because Mohammed bin Rashid is Ruler of Dubai *and* Vice President *and*
  Prime Minister, permanently and legitimately.
* **Roster-only rows apply when someone other than this engine asserted
  them** (`roster_only.attested`: identity by wikilink, or the row carries a
  non-Wikimedia citation — a *better* second channel than any category), and
  skip on a bare name match.
* **Early terms are answered by the target's own record, never by a country
  constant** (`early.precedent_ok` / `early.unsupported`): Czech Agriculture
  carries ten pre-1993 terms, Czech Defence's item only exists from 1993, so
  no per-country rule can be right for both. `modern_from` selects which rows
  the census is asked about; it does not decide them. The UAE refinement: the
  rulership items pass on their own evidence (4–15 mostly pre-1971 holders
  each) while the ministerial items fail, all under one `modern_from = 1971`.
* **A different polity's office is skipped** (`era.distinct`) — it needs its
  own item, which no rule can invent. `continuous_eras` names the polities
  that are the *same institution* under an earlier constitution (the Czech
  Republic inside the federation — not the Protectorate). Route by the
  *row's* section, never by the person: someone who served the Byelorussian
  SSR and then the Republic holds both offices.
* **`category_only` and `no_dates` land on `skip` via the campaign's
  `dispositions`** — in a category but named by no roster row, or agreed but
  undated, is not enough to write a statement, and it is not a queue either.
* **Offices created for a deputy-ruler shape use `P279 = Q3250324`** — the
  two pre-existing items disagree (Q42178 "vice president" vs Q3250324
  "deputy") and neither is the counterpart of Amir; Q3250324 is the less
  wrong and `wd/create.py` encodes it.

A country whose history genuinely contradicts a default says so **once**, in
`dispositions` or `continuous_eras` — never per person.

## 6a. Read the backtest before reading anything else

Most of a roster is people whose spell is already recorded — 789 of Spain's
1,052 rows, 213 of the UAE's 573 — and those rows are a **labelled test
set**: the roster says what the engine believes, the item says what the
community recorded. `wd/backtest.py` compares them for every such row at no
network cost and writes a `## Backtest` section at the head of the audit,
plus `data/<campaign>/backtest.jsonl`. Three numbers per office:

* **target agreement** — did `target_for` pick the item the community uses?
  Below ~90% the office is a family of items and the routing is guessing.
  Spain's Congress presidency scores 58% without its era routing and 90% with
  it; that drop is the whole of §2a, measured.
* **date agreement** — the share of comparable rows that do not *contradict*
  the record. Read the bolded `conflict` column, not the percentage: a
  recorded year-precision date is agreement written differently. A parse
  defect shows up as conflicts confined to one page — this is how the
  `"5 de julio del 2022"` bug was found in Ecuador, months after shipping.
  A healthy run's conflicts are source disagreements, not parse defects (the
  UAE run had exactly two, both genuine).

  **Either side can be the coarser one, and for a long time only one was
  handled.** `_same_span` and `_shares_boundary` took their precision from the
  *record*, so a roster dating by year against an item dating by day could only
  ever score `conflict`: the Saudi province articles date governors "1952 - 1955"
  where the items carry "1952-12-20" – "1955-04-18", and all five comparable
  Riyadh rows read as contradictions on a page with nothing wrong with it. The
  fix — compare at the precision both sides claim, as `wd/validate.py` has since
  Spain — also retroactively cleared three Belarusian offices that had been
  reported at 0% and 33% for months. If a whole office scores 0%, suspect the
  comparison before the parser.
* **acting agreement** — where the roster says acting, does the record carry
  `P2868`?

`unrecorded spells` counts roster terms the item does not record at all
though it records another spell in the same office; those are dropped today
by the person-level `already holds` check, and the count (140 in Spain) is
what promoting them to proposals would cost — a candidate extension, not yet
a rule.

The same comparisons derive the office's **item family** — any item two
people use for a spell this roster describes, agreeing on a boundary, and
passing `verify_family`. That is what lets a country nobody hand-analysed
get `duplicate_office_item` protection, and it is deliberately conservative:
it needs two people agreeing on a boundary, so a single cross-filed row (the
UAE's Sharjah/Ras al-Khaimah dynasty overlap) can still ship — the audit
flags it instead.

## 7. The audit is the run checking itself

Non-negotiable: dump **every** roster row with its resolved identity, how it
was resolved, and its fate (`data/<country>/roster_audit.md`) and read it
before rendering — every matcher this workbench has built was too loose on
the first pass. Each of these was wrong once and would have shipped silently:

* **a roster page that is a redirect** — two portfolios parsed one page and
  double-proposed it.
* **sibling ministries in the same article** — heading patterns on "cartera"
  swept in "Cartera de Minería". Accept only the office's own table and *log
  the tables you skipped*.
* **a `Período` header colspanning two cells** — every end date silently
  dropped on four rosters. A role can occupy several columns; keep all values.
* **a wide header subdivided by a second header row** — read the top row
  alone and a "Dny v úřadu" *day count* becomes an end date: a 1,939-day
  tenure ends in the year 1939. `_subroles` refines from the sub-header; give
  decoy columns their own role (`days`) so they cannot fall back into
  `period`. Same trap in Arabic: `المدة` (duration) is typed `days`.
* **the name in the wrong column** — one page fills the *portrait* cell with
  the name; reject candidates that are a pure date or ordinal.
* **rowspan continuation rows** — drop a row only when *both* name and dates
  are continuations, or a second genuine term under one merged name cell is
  lost.
* **rows that are gaps, not people** — "Funkce neobsazena", "Vacante" were
  11 of 11 entries in Czechia's `no identity` column.
* **date overlaps**: a roster is sequential, so two people overlapping means
  a misparsed cell. Print the warnings; expect only coarse pre-modern ones.
* **acting flags in `bgcolor=` rather than `style=`**; some wikis skip colour
  and write "(в. а.)" / "и. о." in the cell. **Italics mark acting only on a
  page that declares the convention** (`en:President of the UAE` does, in
  prose) — elsewhere italics are emphasis and ship names.
* **bracketed years that are a lifespan, not a term** — "Боркусевич
  (1892—1930)". The giveaway is a term starting in the birth year; where a
  bullet has both leading dates and trailing brackets, the leading pair is
  the term.
* **a wiki's own vocabulary**: month names, column headers, and the folding
  that makes them matchable (і/ў/ё; Arabic hamza/ya: one page heads the same
  column `الاسم` and `الإسم`). Write heading patterns against
  `wd.roster.fold` and test them against the *folded* text — an Arabic
  pattern copied off the page never matched because "رؤساء" folds to "روساء".
  An era marker can defeat a regex boundary outright: `\b` cannot fire
  between "1" and "م", so the AD marker needed its own pattern.
* **optional particles must be word-bounded.** `(?:del?\s*)?` matched the
  "De" of "December", leaving "cember" for the month lookup — the match
  *succeeded*, so the regex never backtracked, and every English December
  silently lost its day. `parse_date('2 December 1971')` returned `1971-12`,
  in the country founded on 2 December 1971. Require `\s+` after a particle.
* consecutive rows for one person (new appointer, ministry rename) are
  **one** term: merge on `previous.end == row.start`, never across a change
  in acting status.
* **a duration column parsed as the term** — "Duración" / "Tiempo en el
  cargo" shadow the real date cells under the `period` role and every date on
  the page is lost.
* **hidden sort keys.** `{{dts}}` renders `<span style="display:none">…</span>`
  whose own hyphens split the cell first; strip the span but keep its **tail**
  text, because lxml's `remove()` takes the visible date with it.
* **`<hr>` divides a cell like `<br>`** — four stacked sessions read as one
  line concatenate into "18 de nov. de 18375 de nov. de 1838". Pair
  equal-length start and end stacks into one row per term.
* **abbreviated months, with the dot on either side** ("2. července",
  "17 de jul. de 1834"), and English month-first dates, each need their own
  pattern.
* **"died in office" is not "in office"** — "(fallecido en el cargo)"
  contains the incumbency phrase.
* **a full-width `td` can be a heading or a note** — word count separates a
  reign announcement (a section) from a thirty-word gap explanation (also a
  section, but one that displaced the era heading the regime routing reads).
* **a header row marked up as `td`** — no roles were assigned and all 84 rows
  dropped for want of a name column. Treat the first row as a header when it
  names two known columns.
* **class-less tables are real tables.** Requiring `class="wikitable"`
  silently skipped a five-ruler table; refuse page furniture by class name
  instead. And guard *both* span attributes — `colspan="100%"` crashed a
  parse.
* **"Incumbent" in a date column is data, not a defect** — later UAE cabinet
  tables date only the changes. A run must be able to say "247 of 432 rows
  carry a date, and that is the source".
* **an empty-string headings pattern is falsy** — `source.headings or
  DEFAULT_HEADINGS` swapped in the default and an office lost all its rows.
* **a `td` header row plus an unknown vocabulary is a silent total loss.** The
  two conditions compound: `_reads_as_header` needs *two* recognised column
  names to treat a `td` row as a header, so a page whose headers are all
  unfamiliar gets no roles at all and every row is dropped for want of a name
  column. The Saudi ministerial lists head their dates "من الفترة" / "حتى
  الفترة" — a bare "من" key cannot cover the first (two-letter keys match whole)
  and there was no key for "حتى" — so one column of seven was recognised, and
  eleven interior ministers and twenty-one health ministers parsed with **zero
  dates and no error**. When a page returns rows but no dates, dump the header
  row folded before suspecting anything else.
* **a table dated twice over, once per calendar.** The Saudi province articles
  tabulate governors under "التاريخ الهجري" (Hijri) beside "التاريخ الميلادي"
  (Gregorian). Name the one you cannot use as a decoy — the same treatment a
  "Duración" day count gets — and make sure neither is reachable through a bare
  "التاريخ" prefix key.
* **Hijri dates need no conversion, and that is worth a test rather than
  code.** An AH year falls outside the Gregorian range the year rule accepts
  (AH 1500 is AD 2076, so nothing in use collides), so `1370 هـ` yields nothing
  and `1331هـ/1913م.` correctly keeps `1913`. `scripts/check_dates.py` pins it,
  because the behaviour is invisible, load-bearing, and one "fix" to the year
  range away from stamping a whole country's dates a year or two wrong. What it
  costs is honest and uneven: two of eleven interior ministers and none of
  twenty-one health ministers carry a datable term, because those pages print
  the Gregorian date beside the Hijri one and the others do not. **Report the
  lane at what it yields.**
* **a parenthetical stacked under a date becomes a phantom row.**
  `en:King of Saudi Arabia` writes "23 September 1932" over "(aged 57)" and
  "9 November 1953" over "(death by natural causes)", and the equal-length
  stack pairing read them as a second, dateless term per king — 6 of the page's
  13 rows. Harmless per person (the dated span wins) but it doubles the audit
  and the backtest denominator. Drop a paired term with no date on either side.
* **a pattern that matches but fails its lookup never backtracks.**
  `parse_date` searched for the *first* day-month-year shape and gave up when
  the word turned out not to be a month, so "1 رجب 1441 هـ 25 فبراير 2020 م"
  fell through to the bare-year rule and returned "2020" beside its
  day-precision neighbours. Scan to the first match whose month actually
  resolves (`_first_month`), not to the first match.
* **a sub-header that spans two columns names both of them.** `_subroles` used
  to refine only the spanning cell's own position, so `ar:قائمة ولاة عهد الكويت`
  — which sub-heads its start *and* end cells with one "فترة تولي المنصب" beside
  a duration column — left the end column unnamed and every crown prince
  open-ended. Continuation positions are refined too now, exactly as `_roles`
  reads them.
* **one page per cabinet, dated only where it changes.** `en:List of cabinets of
  the UAE` gives a section per cabinet, so a minister serving three of them
  appears three times: with a start, with nothing, and with an end. Read as three
  rows that is one spell arriving as *fragments* — a lone `P580` and a lone
  `P582` — and QuickStatements' merge had been silently reassembling them, so
  nobody saw it for a month. `wd/validate.py:conflicting_tenures` now refuses
  it. Where an office is fed by both a dedicated succession list and a
  per-cabinet page, merge the person's consecutive rows before proposing.
* **a table whose date ranges run backwards.** `ar:وزارة المالية (الكويت)`
  writes eight of its 29 ranges "1965-1959", "1981-1967" — an RTL authoring
  artifact, and the rows chain correctly read the other way round. Left as a
  deferred lane rather than fixed with a global "swap if reversed" in
  `parse_period`, which would touch every campaign and could mask a real parse
  defect. `wd/validate.py` refuses a `start > end` batch, so this fails loudly.
* **a membership roll dates no row on purpose.** A legislature publishes one
  page per term with the term in the *title* — the Saudi Consultative Assembly's
  three rolls are 150 members each with no date column at all. `RosterSource.term`
  supplies it, and it has to bypass the "no date column ⇒ navbox" guard or the
  table is thrown away before the term is applied. Give each term an **end** as
  well: the end of term N is the start of term N+1, as attested as the start,
  and it lets `merge_terms` fold a re-appointed member's three open-ended
  statements into the one continuous membership they describe.

* **a whole *institution* dates no row, and the article per government is the
  term.** Jordan keeps one article per cabinet — 108 of them — and only the two
  most recent date their rows; the other 106 print a bare
  `الاسم ¦ المهام الوزارية` and nothing else. What dates them is each article's
  own infobox (`التكوين`/`النهاية`), so the lane is 98 `RosterSource`s each
  carrying its government's span. Two consequences worth knowing before
  reaching for this shape. The dates it writes are *cabinet*-precision, not
  tenure-precision — a minister replaced mid-government is overstated, and the
  backtest says so (Jordan's cabinet lane scores 75% on dates against 100% on
  every office with a real date column). And a minister who served four
  consecutive governments arrives as four rows, so `merge_terms` does the real
  work and the API half of the batch gets large: 59 of Jordan's 275 applying
  records are people with several tenures in one office.

* **the sitting cabinet dates from the *original* appointment, not from this
  government.** Jordan's current cabinet article gives a minister
  2023-09-26 – 2025-08-06 where the predecessor's gives her
  2023-09-26 – 2024-09-15: one continuous tenure told twice, sharing a start,
  which `validate.collapsing_groups` refuses and no rule can settle without
  picking a source. Defer the sitting cabinet, as Kuwait's was.

* **two rosters for one office is two sources dating one tenure.** Running
  `ar:رئيس وزراء الأردن` and `en:List of prime ministers of Jordan` together
  looked like the two-channel gate working and was not: they agree on every
  premiership and disagree by a day or two on seven end dates, which arrives as
  one P39 with two ends. One source per office; the *category* is the second
  channel, and it dates nothing.

  …and **the same is true of one person's infobox in two languages**, which is
  how the rule arrives when the source is the holder rather than the office.
  Qatar's ICT ministership ends 2016-01-27 on one wiki and 2016-01-26 on the
  other; `wd/campaign.py:officebox_rows` therefore reads the second wiki only
  for people the first does not cover — the reach of both, nothing dated twice.

* **a genealogy may list one person twice, legitimately.** `en:House of Thani`
  names Ahmed bin Muhammed as a son in one branch and as the head of another,
  and the founder twice with the gloss capitalised differently. `P53` says
  nothing about *where* someone was listed, so the second bullet restates the
  first and `validate` refuses the batch for a duplicate line;
  `kinship.house_records` emits one record per person. For `P22` the same shape
  means the opposite — two bullets under two different fathers is the article
  contradicting itself, and both skip.

* **an honorific is sometimes linked, and it leads.** `[[Sheikha]] [[Najla bint
  Khalifa Al Thani]]` — the style is the first link in the bullet, so it was
  read as the person: 22 entries resolved to the article about the title, and
  every child nested under them inherited "Sheikh" as their father's link and
  lost the patronymic gate. `kinship.HONORIFIC_ARTICLES` drops them, matched
  whole; no person's article is titled with one of these alone.

* **a bullet can name nobody.** Twenty-five of `en:House of Thani`'s entries are
  "Sheikh ??? bin Nasir Al Thani" — a real assertion that a son existed, naming
  him nowhere. They resolve to no item, so nothing acts on them, but left in
  they read as redlinks and enter the item-creation list as an instruction to
  mint an item for "???".

* **a catch-all written `.` does not match an empty cell.** `section_targets`
  builds its haystack from the row's section and office cell, so a row with
  neither has an empty string to match against — `re.search(".", "")` is false,
  the catch-all never fires, and the row falls through to `Office.target`. In
  Jordan that filed 57 blank cells as ministers of state, 39 of them prime
  ministers and 18 of them the King, and it showed up only as a backtest target
  agreement of 68%. Write the catch-all `r""`.

* **a definite article fused to a preposition defeats a pattern carrying it.**
  Arabic cabinet lists write the portfolio in the accusative — "وزيرا للعدل",
  where `للعدل` is لِ + العدل — so a pattern written `العدل` matches none of
  them. Jordan uses 630 distinct spellings of about fifty portfolios across a
  century, and patterns written from the *titles* left 433 rows unrouted. Match
  the bare stem, and dump the whole distinct-value tally with what each routes
  to before running anything.

The mechanical half of this is no longer yours to type: `wd/validate.py` runs
at render time and **refuses to render** a batch with a duplicate line, a
`start > end` (compared at the coarser of the two precisions — "25 January
1972 – 1972" is an ordinary cell, not a defect), or a malformed value. It
warns, without vetoing, about the citation-versus-permalink split, a P39
with no start date, one claim restated on two lines with different
references, and a year-precision date beside day-precision ones on the same
item — which means a cell failed to parse, not that the source was coarse.

## 8. Emit

    /Users/pudo/.python/wrangle/bin/python scripts/render_edit_plan.py --retrieved <today> --campaign <country>

* `edit_plan.qs` — **the deliverable**: one additive QuickStatements batch
  per campaign, all concerns, validated. Additive-only means the whole batch
  is mass-revertable; single-file means what was approved is what was read.
* `edit_plan_claims.json` — **the other half of the same deliverable**, and
  only ever this one thing: people with **several tenures in one office**.
  QuickStatements matches a line on subject, property and value alone and
  merges its qualifiers into whatever statement it finds, so two spells arrive
  as one P39 carrying both starts and both ends. Kuwait had 50 such people of
  358, Spain 13, the UAE 14, Ecuador 14 — every campaign has them, and until
  this split they were shipped silently. `scripts/apply_claims.py` writes them
  through `wb edit-entity`, one atomic payload per person, `--dry` by default
  and guarded by `claims_written.json` — the API creates every claim it is
  given, so a second run without the ledger doubles all of them. Review the
  two files together.
* `edit_plan.md` — the account: every verdict with its evidence, source and
  the rule that decided it, applied and skipped alike, grouped by concern.
* **Offices with no item**: declare `archetype` + `body` instead of `target`,
  then `python scripts/create_offices.py --country xx` (dry by default,
  `--apply` to write; guarded by a ledger, a duplicate search, a holder
  floor and a body-label check). QuickStatements cannot do this: `LAST` is
  subject-only, so a freshly created office cannot be the value of its
  holders' P39 in the same batch — creation runs first, then the sweep.
* Sourcing: prefer the roster row's own citation as `S854` + `S813`; when the
  row has none, cite the roster **permalink** as `S4656` — never a Wikipedia
  URL in S854.
* Qualifiers beyond dates go in `qualifiers` (P2868 acting, P768 electoral
  district, P2937 term); check the country's de-facto practice with a
  qualifier tally over the position's existing P39s before choosing.
* Surgical work (merges, rank changes, statement removal, label fixes) never
  goes in the `.qs` — it is a wikibase-cli list in `tasks/followups.md`, and
  it stops and asks.

## 9. Close the loop

**Reconcile before you close.** Fill in the `shipped` column of
`coverage/<country>.md` against the `expected` column written at survey time, and
give any institution shipping under half its estimate a written reason. This is
the check the method has never had: Iran sized its Majlis lane at 2,349
statements and shipped 388, sized its ambassador lane at ~640 and shipped 29, and
neither ratio was computed anywhere. Qatar is the only campaign in eleven that
ever produced a planned-versus-built table, and it is worth copying — it caught
two estimates wrong in opposite directions and explained both.

A campaign may not close while a ledger row reads `deferred`, and a `blocked:`
row must name an issue with an owner. **Update the country's column in
`coverage/README.md`** from the ledger.

Note what the reconciliation cannot see today: the `already holds P39` gate
`continue`s before `emit()`, so those rows never become verdicts at all. Iran
tallied 1,932 of 3,060 rows that way — 63% of the run, invisible in
`edit_plan.md`. That contradicts "every case gets a disposition" and is a toolkit
issue, not a per-campaign one.

* Byproducts land in `tasks/followups.md` if actionable (items to create,
  merges, `wd_categories.yml` write-backs) and stay measured in the audit
  otherwise (rows with no Wikidata item are the item-creation / OS PEP
  coverage list).
* Retirement metric per spec (`members_total / p39_have / p39_planned /
  p39_gap`) → which `position:` blocks can be dropped from
  `wd_categories.yml`, and which specs should be **split** rather than given
  one `wikidata_id` (a two-era category needs two; a 19-community category
  needs nineteen).
* **Baseline the run**: copy the verdict files, `manifest.json` and
  `edit_plan.qs` to `regression/<country>/` (see `regression/README.md`).
  When the engine changes, **re-run every previous country and
  `diff_verdicts.py`** — the differ compares what records mean, so a schema
  change diffs empty. The Belarus name-matching change moved three Ecuadorian
  people from `category_only` to dated adds; that was visible only because
  the old verdicts were on disk.

## 10. Researching a convention empirically

When a modelling question has no documented answer — and Wikidata's guidance
is often deliberately broad (P1001 legitimately reads as sender *or* receiver
on a diplomatic post) — measure the de-facto convention instead of declaring
one. The method, from the diplomatic-posts run:

1. Find the **well-curated cluster** for the shape in question (for bilateral
   diplomatic posts: the 264 subclasses of Q29645886, flagship-maintained)
   and tally property usage across it with SPARQL — that produced "P17 = the
   receiving state, 262/264" as a measured fact.
2. Read two or three **exemplar items in full** before choosing properties;
   a curated exemplar shows the whole shape at once (P17/P137/P2389/P461).
3. Distinguish **majority practice from split practice**: doubled-P1001 at
   35/264 is a minority; mass-asserting it would take a side the community
   has not. Emit only what the convention clearly supports.
4. A **predictable systematic bias** in one channel can be modelled and
   overridden explicitly rather than routed to review — the diplomatic
   classifier reliably latched onto the sender, so where the label named a
   receiver the label won, as a recorded rule
   (`render_diplomatic_plan.py`).
5. Beware **corpus bias in holder-derived priors**: majority properties of a
   position's holders make a strong shortlist, but generic occupations show
   90–100% one-country shares merely because one wiki community documented
   its people ("notary" = 98% French). The test: is the office inherently
   bound to ONE jurisdiction?

## Per-country parameters

Everything else is generic; these are the inputs a new country needs, as a
campaign script (copy `scripts/ec_ministers.py` for the simple shape,
`es_offices.py` for successions, `ae_offices.py` for hereditary lanes and
Arabic sources):

* per office: key, label, `target` QID, roster page(s) (`RosterSource`, with
  `kind="bullets"` where the list is not a table, `headings=` where one page
  serves several offices, `term=(start, end)` where the page *is* one term and
  dates no row), and either explicit `categories` or a `sibling_category` to
  expand through interwiki links
* `section_targets` when one roster spans several named offices — matched
  against the row's section heading *and* its office cell
* `date_targets` when the office's *item* changes on a date (§2a); an empty
  QID means "no item exists for this era" and files the row as a creation
  byproduct instead of under the nearest item that happens to exist
* `family` on a hereditary office, for the P53 backfill
* `archetype` / `body` / `create_labels` for offices that need minting first,
  plus `jurisdiction` where the country scopes the office narrower than itself —
  the eight Saudi provincial governorships that exist all carry
  `P1001 = <province>`, so minting the missing five nationally would make them a
  different shape from their siblings
* `extra_verdicts` where a lane is not an office at all (§4a), so the manifest
  owns its file and the campaign still renders one batch
* `regime_sections` / `regime_categories` where several polities shared the
  office name; `continuous_eras` for the ones that are the same institution
* `modern_from`, the institutional cutoff year
* `concurrency_ignore` — every seat whose overlap with another office means
  nothing (legislature and council seats everywhere; rulerships and
  permanent federal offices where one person properly holds several)
* `dispositions` — rule id → disposition; under the one-batch model this
  maps `hold`/`review` defaults (`category_only`, `no_dates`,
  `predecessor_body`, `believed.held`, `uncertain`) to `skip`
* `generic_targets` — vague items ("minister without portfolio") whose
  proposals are redundant beside a specific office's
* `label_langs` and `sibling_wikis` — which language names people in the
  audit, and which wikis to follow
* `review_sections` — words marking a pre-ministerial body in a section
  header

Then add the country to `SCRIPTS` in `scripts/create_offices.py` if it has a
creation lane, and to `regression/` once the run is accepted.
