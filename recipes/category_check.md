# Recipe: checking a `wd_categories` country block into real P39 statements

How to work down the synthetic PETScan positions one country at a time —
verifying who actually held what, and retiring the pseudo-positions behind
them. Derived from four runs, counted as the lines their `.qs` files actually
carry:

* Ecuador (`tasks/ecuador.md`, 17 specs → 177 statements) — a country whose
  position items existed but were nearly empty;
* Belarus (`tasks/belarus.md`, 15 specs → 16) — already well covered, and
  documented mainly on a wiki the config did not name;
* Czechia (`tasks/czechia.md`, 13 specs → 18) — essentially finished, where the
  yield was the review tiers, the item-creation lists and three parser bugs;
* Spain (`tasks/spain.md`, 7 offices → 111) — the largest block measured, and the
  one that shows what to do when a country models an office as a *succession of
  items*.

The Lithuanian (`tasks/positions.md`) and Bahraini
(`tasks/category_positions.md`) runs are earlier, more manual versions.

The engine is `wd/campaign.py`; a country script is only parameters
(`scripts/ec_ministers.py`, `scripts/by_ministers.py`). **Expect the target
census in step 2 to tell you how much there is to win** — where the items
already carry thousands of holder statements, the yield is small and the
useful output is the documented review tiers, not the batch.

Follow this instead of re-deriving per country. Each step says what to run,
what the output is for, and what went wrong the first time.

## 0. What you need before starting

* the country's block in
  `/Users/pudo/Code/opensanctions/datasets/_wikidata/categories/wd_categories.yml`
* `data/categories/positions.json` (from `scripts/category_positions.py`) —
  already resolves most `position:` blocks to QIDs, with verification verdicts
* a campaign brief at `tasks/<country>.md`, ending in a status checklist

## 1. Inventory the categories

Enumerate every spec whose `country:` is the target (also grep the country
name — a few specs carry only `language:`), then measure each category at
**depth 0, 1 and 4**:

    /Users/pudo/.python/wrangle/bin/python scripts/petscan.py --lang es "Ministros_de_Ecuador" --depth 1

Record the counts in the brief as a table. Depth is a decision per category,
not a global setting:

* **depth 0** for head-of-state/government categories. Deeper pulls in
  eponymous subcategories and relatives — `es:Presidentes_de_Ecuador` goes
  84 → 363 at depth 4, adding *children of presidents* and colonial governors.
* **depth 1** where the subcategories are *terms* or *portfolios* (see step 3)
  — there the subcategory names are the useful signal.
* enforce `P31=Q5` yourself: PETScan's "uses Q5" filter passes `Category:`
  items via P4224 (37 of 764 hits in Ecuador).

Then join the member universe against existing P39s to get the honest gap:
how many hold no position item scoped to this country at all.

**Follow the interwiki siblings.** The config's category is often the thinnest
one: `en:Government_ministers_of_Belarus` has 35 members, its Belarusian
sibling 243. Resolve the category page to its Wikidata item and harvest every
sitelinked sibling (`campaign.sibling_categories`) — for countries documented
mainly on another wiki this is the difference between a token run and a real
one. It also imports that wiki's own noise: `uk:Прем'єр-міністри_Білорусі`
files every Byelorussian SSR council chairman as a prime minister of Belarus.

## 2. Inventory the targets

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
position the person holds — Kateřina Šimáčková's Constitutional Court seat is
invisible to `wdt:` because her later ECtHR seat is ranked preferred. Measuring
Czechia the wrong way reported 7,554 holder statements against a real 14,124,
and offered an add for a statement that already existed. `campaign.holders()`
gets this right; ad-hoc census queries are where it goes wrong.

Read the result before planning anything. It tells you which offices already
have items (Ecuador had a complete, near-empty ministry block: 17 items at
1–4 holders each), which are **list articles mistyped as positions**, which
are **generic items doing duty for a country office** (Q83307 "minister",
Q3273722 "health minister", and one item literally meaning "incumbent"), and
which offices are missing entirely. Missing items are a creation subtask, not
a blocker to the rest.

### 2a. Then ask whether the office is one item or several

**Do this before writing a single `target=`.** In Spain it is normal for one
office to be several items, and a target chosen without checking is wrong for
most of the roster:

* ministries are renamed with almost every cabinet and Wikidata models each name
  (Ministro de Estado → Asuntos Exteriores → …y de Cooperación → …, Unión Europea
  y Cooperación), so the target is a function of the *date*: `Office.date_targets`;
* the same office can have era items nobody labelled as such — Q45213921
  "President of the Congress of Deputies" *is* described as 1876–1923, but
  Q43118787 (Cortes republicanas) and Q43138757 (Cortes franquistas) are not
  described at all, and were found only by looking;
* two items can compete for the *same* era, which is a merge decision and not a
  campaign: Spanish labour has both a long-running "Minister of Labour" and a
  2018–2020 ministry name carrying holders from 1919. Declare no office at all
  and say so in the brief.

The measurement that answers it: for each portfolio category, tally its members'
P39 values split at the modern cutoff, then take the era profile of every
candidate item (`wd.precedent.census`, `starts` bucketed by era). An item whose
terms *stop* where another's *start* is a succession; two items covering the same
years are a conflict.

**Where the same office really has two items in parallel use, expect the roster
rows to be on record under the other one.** `already_under_sibling` flags that as
`duplicate_office_item` and skips it — 44 Spanish rows, 21 of which the engine
was otherwise about to add a second time *and* qualify as acting, because a spell
sitting inside the sibling item's span also trips `interim_of`.

## 3. Lane the categories

| lane | shape | how to run it |
|---|---|---|
| single office | "President of X", one item | roster + category, step 4 |
| body membership | "Member of the X Assembly" | same, plus era routing when a predecessor chamber exists |
| **bucket** | "Minister of X" = any portfolio | check whether the wikis subdivide it by portfolio — if so it is mechanical, not per-person |
| catch-all | "Politicians of X", "Political office-holders" | defer; these are municipal/provincial grab-bags |

The bucket lane is where the volume is, and the trick is that both wikis
usually subdivide the minister category by portfolio
(`Ministros_de_Salud_Pública_de_Ecuador`, `Defence_ministers_of_Ecuador`).
List subcategories with `list=categorymembers&cmtype=subcat`. Portfolio
subcategory + portfolio position item = a target per person, with no
per-person office guessing.

## 4. Find the rosters (this is the leverage)

Spanish-language wikis keep a dated table per office — `Anexo:Ministros de
Trabajo de Ecuador`. Enumerate them in one query (namespace 104 is `Anexo:` on
eswiki; other wikis put lists in ns 0):

    action=query&list=allpages&apnamespace=104&apprefix=Ministros de

A roster gives, in one fetch: every holder, exact start/end dates, the
appointing president, a **per-row citation** (Registro Oficial decrees, press
archives) and a colour legend marking acting officials. That is strictly more
than N biographies restating the same table, so **verify roster-first, not
person-first**.

Rosters hide in three places, in descending order of quality:

1. **a dedicated list article** per office (`Anexo:Ministros de …`);
2. **the office article** (`Министр иностранных дел Республики Беларусь`),
   which often tabulates each regime's holders in its own section — the
   cleanest regime signal you will get;
3. **the ministry article**, where holders are a bulleted list under
   "Министры"/"Руководство" (`parse_bullet_rosters`). Weakest: bullets rarely
   footnote their rows, so those statements end up sourced to the roster
   permalink rather than a citation — 0 of 10 in Belarus against 81 of 97 in
   Ecuador. Say so in the brief; it is a real quality difference.

Probe candidates by parsing them and counting rows that carry a *date*: a page
that yields rows without dates is usually a navbox or a link farm, not a
roster. `office_rows` now drops a table with no date *column* for the same
reason — es.wikipedia heads each era with a party-colour key table, and four of
its ministry lists are portrait grids with no dates at all, which is the
difference between "this office has no roster" and "this roster has 5 rows". Watch for redirects — `Анexo:Ministros del Interior` and
`Список министров иностранных дел` both redirect elsewhere, and two offices
pointing at one page will double-propose it.

`wd/roster.py` parses them from rendered HTML (`wd.wikipedia.fetch_html`),
because `rowspan` is load-bearing — a reference or appointer cell shared by
three rows belongs to all three. It returns `Roster(heading, columns, rows,
legend)` with `RosterRow(name, link, start, end, incumbent, acting, section,
appointer, ref_urls, covering)`, plus `merge_terms()` and `names_match()`.

**The two-channel gate**: a statement is batched only when the category *and*
a roster row agree. Category-only and roster-only candidates are real but
single-channel — hold them (step 6).

## 5. Resolve identity, then gate it

Ladder, strongest first:

1. the roster row's own **wikilink** → title → QID (`pageprops`, redirects
   followed). Wikipedia asserted this identity; take it.
2. the bare name as an **exact article title**.
3. **truncated titles**: rosters print all four Spanish name parts
   ("Carlos Marx Carrasco Vicuña") while the article sits at two or three.

Steps 2–3 are not assertions by anyone, so they must survive three gates —
each of which caught a real false positive in the Ecuador run:

* **citizenship**: no contradicting P27 (killed "Carlos Pérez García", a
  Spanish footballer, proposed as energy minister)
* **lifetime**: born ≤ term start − 18, died ≥ term start (killed Ángel
  Polibio Chaves, 1855–1930, proposed as 1998 labour minister)
* **political marker**: any P39/P102, a political P106, or a description that
  reads political (killed es.wiki's "Ernesto Albán", a comedian)

Name comparison is token-prefix, minimum two tokens, accent-free, stopwords
dropped — never substring. Rejected identities stay visible in the audit as
`no identity`; they are the item-creation byproduct, not waste.

## 6. Tier the output; batch only the safe tier

Every candidate becomes an edit record (`wd/record.py`) carrying its
statements, the **flags** describing it, and a **decision** naming the rule
that made it. Flags are a set, not one label: a row can be acting *and*
pre-cutoff *and* roster-only, and the old single `era` string kept only
whichever an if/elif chain reached first.

`wd/policy.py` assigns the disposition — `apply`, `apply` with qualifiers,
`skip` with a reason, `hold`, `review`. **Nothing is escalated per case.** A
row with no evidence is skipped and says why; a class of rows needing a QID
becomes a byproduct list. If you want to add a tier so a human can rule on it
later, write the rule instead.

Two things decide most of it:

* **The census, not a country default** (§2). `early.precedent_ok` asks the
  target item whether it already carries terms this early. This matters more
  than it sounds: nineteen of Ecuador's twenty ministry items carry *zero*
  pre-1979 terms, so importing 19th-century holders would invent a convention
  rather than follow one — while its foreign-affairs item carries 21 of 43 and
  takes them happily.
* **Identity rung, alongside tier.** `identify` returns five strengths; a rule
  that applies on Wikipedia's own wikilink must not apply on this engine's
  token-subset guess. In the three campaigns 30 of 32 roster-only rows were
  wikilinked, so the gate costs almost nothing and excludes precisely the
  guesses.

The flags a row can carry:

| era | meaning |
|---|---|
| `modern` | both channels, inside the modern institutional era → batched |
| `roster_only` | roster names them, no category does |
| `historical` / `historical_roster_only` | term starts before the modern cutoff |
| `acting` | legend marks the spell `encargado` |
| `category_only` | in the category, absent from the roster (rosters often start at a democratic transition) |
| `predecessor_body` | filed under a pre-ministerial agency |
| `rename_history` | the office's item history is unsettled (`hold=` on the portfolio) |
| `lifetime_mismatch` | probable namesake |
| `lifespan_not_term` | the bracketed years were the person's dates, not a term |
| `interim_concurrent_office` | a short spell inside a term they hold elsewhere |
| `no_dates` | two channels agree on the office, but nothing dates it |
| a regime name (`byelorussian_ssr`, `bnr`) | an earlier polity's version of the office |

**Rule order is load-bearing, and easy to get wrong in both directions.**
Rules answering "does this claim belong on this item at all" (`era.distinct`,
`early.unsupported`) must precede rules answering "what kind of tenure was it"
(`acting`, `interim`) — ordered the other way, a 19th-century acting spell is
applied to an item whose own record starts in 1979. And the general
`modern.two_channel` rule must come *last* of the applying rules, or it
swallows the specific tiers and silently drops their `P2868`. Both mistakes
were made within an hour of each other; the table is grouped and commented by
the question each group answers.

Pick the **modern cutoff** from the country's institutional history (Ecuador:
1979, the return to democracy; Belarus: 1991, independence) and say so in the
brief. It selects which rows the census is asked about; it does not decide
them. Where several polities shared an office name, add explicit **regime
routing** on top of the date: roster section headings name the polity
("Министры иностранных дел БССР"), and the wikis keep dedicated БНР/БССР
categories. Route by the *row's* section, never by the person — someone who
served the Byelorussian SSR and then the Republic holds both offices, and a
person-level gate silently drops their modern term. Pre-cutoff holders are
a continuity judgment — is an 1861 "Ministro del Interior y Relaciones
Exteriores" a holder of an item created for the 2010 ministry? — and that is
the user's call, not the script's.

Acting spells: the de-facto convention is `P39 <office>` + `P2868 = Q4676846`
(acting), not a separate item. Keep them held until the user rules, then
re-render.

**Where no legend marks acting officials, the roster will not tell you.**
cs.wikipedia numbers Vladimír Špidla as the 8th minister of justice for 41 days
with nothing to distinguish the row — he was prime minister at the time and
covering the portfolio. `campaign.interim_of` catches these by requiring two
channels: the spell is under `SHORT_SPELL_DAYS`, *and* it falls inside a dated
P39 term the person already holds for another office. Both are needed — Petr
Krčál genuinely was labour minister for 21 days. Set
`Campaign.concurrency_ignore` to the legislature and council seats, or every
minister trips the rule via their parliamentary seat. Brief spells that the
concurrency test clears still get a `short_spells()` warning in the audit.

## 6a. Read the backtest before reading anything else

Most of a roster is people whose spell is already recorded — 789 of Spain's 1,052
rows already hold the target, and 900 have something on record to compare against
— and those rows are a **labelled test set**: the roster says
what the engine believes, the item says what the community recorded. `wd/backtest.py`
compares them for every such row at no network cost and writes a `## Backtest`
section at the head of the audit, plus `data/<campaign>/backtest.jsonl`.

Three numbers per office, and each answers a question that used to be answered
by a human noticing something:

* **target agreement** — did `target_for` pick the item the community uses? Below
  ~90% the office is a family of items and the routing is guessing. Spain's
  Congress presidency scores 58% without its era routing and 90% with it; that
  drop is the whole of §2a, measured.
* **date agreement** — the share of comparable rows that do not *contradict* the
  record. Read the bolded `conflict` column, not the percentage: a recorded
  year-precision date, or an item recording one tenure where the roster counts
  legislatures, are agreement written differently. A parse defect shows up as
  conflicts confined to one page — this is how the `"5 de julio del 2022"` bug
  was found in Ecuador, months after that campaign shipped.
* **acting agreement** — where the roster says acting, does the record carry
  `P2868`? Across all four campaigns the answer is essentially no: **2
  acting-qualified statements on 88 target items**, both of them Spanish, against
  20 the batches propose. That is an open question about the rule that adds the
  qualifier rather than a fact about any one country.

`unrecorded spells` counts roster terms the item does not record at all though it
records another spell in the same office. Those are dropped today by the
person-level `already holds` check; the number is what promoting them to
proposals would cost, and it is large (140 in Spain).

The same comparisons derive the office's **item family** — any item two people
use for a spell this roster describes, agreeing on a boundary, and passing
`verify_family` (this country's office by P17/P1001, and a label naming the same
office rather than the same *kind* of office). That is what let the Spanish
Congress presidency find Q45213921 with no human input in the acceptance test.
Candidates that fail the gates are printed as "declare them in the profile if any
is the same office" — take that as a to-do list for `date_targets`.

## 7. Audit the matcher before shipping

Non-negotiable: dump **every** roster row with its resolved identity, how it
was resolved, and its fate (`data/<country>/…_audit.md`), and read it. Each of
these was wrong on the first pass and would have shipped silently:

* **a roster page that is a redirect** — `Anexo:Ministros del Interior` →
  `…de Gobierno`, so two portfolios parsed one page and double-proposed it.
* **sibling ministries in the same article** — matching table headings on
  "cartera" swept in "Cartera de Minería", "Cartera de planificación
  económica". Accept only the office's own table (`^(titulares|ministros…)`)
  and *log the tables you skipped*.
* **a `Período` header colspanning two cells** — every end date silently
  dropped on four rosters. A role can occupy several columns; keep all values.
* **a wide header subdivided by a second header row.** cs.wikipedia heads three
  columns "Funkční období" and labels them "Nástup do úřadu", "Opuštění úřadu",
  "Dny v úřadu" — read the top row alone and the *day count* becomes a candidate
  end date, so a 1,939-day tenure ends in the year 1939. `_subroles` refines
  from the sub-header; give the decoy column its own role (`days`) so it cannot
  fall back into `period`.
* **the name in the wrong column.** One page fills the *portrait* cell with the
  name and leaves the name cell empty, so the scan walks onto the date. Reject
  candidates that are a pure date or ordinal rather than taking the first
  non-empty cell.
* **rowspan continuation rows.** A spell straddling two cabinets gets one row
  per cabinet with the name and dates rowspanned; the later rows restate a term
  already recorded and would double the statement. Drop a row only when *both*
  the name and the dates are continuations — otherwise a second genuine term
  under one merged name cell is lost.
* **rows that are gaps, not people** — "Funkce neobsazena", "Funkce
  nevyužívána", "Vacante" are numbered among the holders and were 11 of 11
  entries in Czechia's `no identity` column, which is meant to be the
  item-creation list.
* **date overlaps**: a roster is sequential, so two people overlapping means a
  misparsed cell. Print the warnings; expect only coarse pre-modern ones.
* **acting flags in `bgcolor=` rather than `style=`** — a style-only reader
  loses every acting marker on the page. Some wikis skip colour entirely and
  write "(в. а.)" or "и. о." in the cell.
* **bracketed years that are a lifespan, not a term** — "Боркусевич (1892—1930)"
  is a birth-and-death pair, and "(р. 1966)" a birth year. The giveaway is a
  term starting in the person's birth year; where a bullet has *both* leading
  dates and trailing brackets, the leading pair is the term.
* **a wiki's own vocabulary**: month names, column headers and the diacritics
  that vary between spellings (і/ў/ё, "Тэрмін"/"Тэрмiн"). `wd.roster` folds
  both sides — write your own heading patterns against `wd.roster.fold`, or
  "Міністры" will not match a pattern spelled "министр".
* consecutive rows for one person (new appointer, ministry rename) are **one**
  term: merge on `previous.end == row.start`, and never merge across a change
  in acting status.
* **a duration column parsed as the term.** "Duración" / "Tiempo en el cargo" /
  "Dny v úřadu" sit beside the dates and hold "1 año y 143 días"; under the
  `period` role they shadow the start and end cells, and every date on the page
  is silently lost. Four Spanish pages, three Czech ones.
* **hidden sort keys.** `{{dts}}` renders a date cell as `<span
  style="display:none">01812-06-12 </span>12 de junio de 1812`, and the key's own
  hyphens split the cell before the real dash does. Strip such spans — but keep
  their **tail** text, because lxml's `remove()` takes the visible date with it.
* **`<hr>` divides a cell like `<br>`.** The Spanish Senate list stacks a
  president's four sessions in one pair of cells that way; read as single lines
  the four dates concatenate into "18 de nov. de 18375 de nov. de 1838", which
  parses as a year if it parses at all. Pair equal-length start and end stacks
  into one row per term.
* **abbreviated months, and the dot on either side of them.** Czech abbreviates
  the day ("2. července"), Spanish the month ("17 de jul. de 1834"); a pattern
  that allows only the first reads the second as a bare year. English puts the
  month first ("September 24, 1810") and needs its own pattern.
* **"died in office" is not "in office".** "(fallecido en el cargo)" contains
  the incumbency phrase, and four Spanish chief justices lost their end date to
  it.
* **a full-width `td` can be a heading or a note.** es.wikipedia announces each
  reign in a plain `td` (take it as the section, or it becomes a person);
  cs.wikipedia explains a two-year gap in thirty words in the same shape (take
  *that* as the section and the era heading the regime routing reads is gone).
  Word count separates them.
* **a header row marked up as `td`.** es.wikipedia's defence list styles its
  header with column classes and no `th` anywhere, so no roles were assigned and
  all 84 rows were dropped for want of a name column. Treat the first row as a
  header when it names two known columns.

The mechanical half of this is no longer yours to type: `wd/validate.py` runs at
render time and **refuses to render** a batch with a duplicate line, a
`start > end`, a value that is not an item or a date that is not a date. It
warns, without vetoing, about the citation-versus-permalink split, a P39 with no
start date, one claim restated on two lines with different references (so 111
lines can be 110 statements), and a year-precision date sitting beside
day-precision ones on the same item — which means a cell failed to parse, not
that the source was coarse.

## 8. Emit and route

    /Users/pudo/.python/wrangle/bin/python scripts/render_edit_plan.py --retrieved <today> --campaign <country>

* `edit_plan_<concern>.qs` — additive QuickStatements, one file per concern
  (`p39`, `p102`, …), run by the user in the web UI. `edit_plan.qs` is the
  combined file.
* **Offices with no item**: declare `archetype` and `body` instead of
  `target`, then `python scripts/create_offices.py --country xx` (dry by
  default, `--apply` to write). It mints the item through `wb create-entity`,
  records it in `created.json`, and prints the `target=` line to paste back —
  after which the office runs like any other. QuickStatements cannot do this:
  `LAST` is subject-only, so a freshly created office cannot be the value of
  its holders' P39 in the same batch.
* `edit_plan.md` — the review document: every verdict with its evidence
  sentence, source and notes, held-back tiers grouped by era.
* Sourcing: prefer the roster row's own citation as `S854` + `S813`. When the
  row has none, cite the roster **permalink** as `S4656` (Wikimedia import
  URL) — never a Wikipedia URL in S854.
* Qualifiers beyond dates go in `qualifiers` (P2868 acting, P768 electoral
  district, P2937 parliamentary term, P2715 elected in); check the country's
  de-facto practice with a qualifier tally over the position's existing P39s
  before choosing.
* Surgical work (rank changes, replacing a generic P39 with the country item,
  merges) never goes in the `.qs` — it is a wikibase-cli list in the brief.

## 9. Close the loop

* Byproducts to record in the brief, not discard: roster rows with **no
  Wikidata item** (item creation / OS PEP coverage), offices with no item,
  generic-position statements to replace, mislabelled or conflated items.
* Retirement metric per spec (`members_total / p39_have / p39_planned /
  p39_gap`) → which `position:` blocks can be dropped from
  `wd_categories.yml`, and which specs should be **split** instead of given
  one `wikidata_id` (a two-era category like
  `Asambleístas_y_diputados_de_Ecuador` needs two).

## Per-country parameters

Everything else is generic; these are the inputs a new country needs. Ecuador's
live in `scripts/ec_ministers.py` (`PORTFOLIOS`) — copy the shape:

* per office: key, label, target QID, its roster page(s) (`RosterSource`, with
  `kind="bullets"` where the list is not a table), and either explicit
  `categories` or a `sibling_category` to expand through interwiki links
* `section_targets` when one roster spans two named ministries — matched against
  the row's section heading *and* its office cell, which is how one national
  table of nineteen autonomous communities becomes nineteen targets
* `date_targets` when the office's *item* changes on a date rather than by
  section (§2a). An empty QID means "no item exists for this era": the row is
  recorded as an item-creation byproduct instead of being filed under the
  nearest item that happens to exist
* `regime_sections` / `regime_categories` where several polities shared the
  office name
* `hold=` for any office whose item history is unsettled, or that has no
  roster at all (Belarus's deputy premiers)
* `modern_from`, the institutional cutoff year
* `concurrency_ignore`, the seats whose overlap with a ministry means nothing
  (parliament, senate, municipal and regional councils)
* `label_langs` and `sibling_wikis` — which language names people in review
  output, and which wikis to follow
* `review_sections` — words that mark a pre-ministerial body in a section
  header ("Dirección", "Corporación", "Secretaría Nacional", "Subsecretaría")

When the engine changes, **re-run the previous country and diff the verdict
files**. The Belarus work loosened name matching from token-prefix to token
subset (Slavic rosters flip name order and add patronymics); re-running Ecuador
moved three people from "category only" to dated adds — an improvement, but
only visible because the old verdicts were still on disk to diff against.
