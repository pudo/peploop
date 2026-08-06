# Recipe: checking a `wd_categories` country block into real P39 statements

How to work down the synthetic PETScan positions one country at a time —
verifying who actually held what, and retiring the pseudo-positions behind
them. Derived from three runs: Ecuador (`tasks/ecuador.md`, 17 specs → 101
statements, a country whose position items were nearly empty), Belarus
(`tasks/belarus.md`, 15 specs → 10 statements, a country already well covered)
and Czechia (`tasks/czechia.md`, 13 specs → 6 statements, a country essentially
finished — where the yield was the review tiers, the item-creation lists and
three parser bugs).
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
roster. Watch for redirects — `Анexo:Ministros del Interior` and
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

Every candidate becomes a verdict record (the `render_edit_plan.py` schema:
`qid, label, position, verdict, era, terms[{start,end}], evidence,
source_url, source_prop, notes, qualifiers`). Only `verdict: add` with
`era: modern` reaches the `.qs`; every other era is grouped in the review
document under its name, waiting for a ruling. Tiers that earned their own
name in Ecuador:

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

Pick the **modern cutoff** from the country's institutional history (Ecuador:
1979, the return to democracy; Belarus: 1991, independence) and say so in the
brief. Where several polities shared an office name, add explicit **regime
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

Also verify mechanically before you eyeball: no duplicate (person, position)
pairs, no `start > end`, dates at the precision you expect, and the count of
statements sourced to a real citation versus to a wiki permalink.

## 8. Emit and route

    /Users/pudo/.python/wrangle/bin/python scripts/render_edit_plan.py --retrieved <today> --campaign <country>

* `edit_plan.qs` — additive QuickStatements, one concern per batch, run by the
  user in the web UI.
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
* `section_targets` when one roster spans two named ministries
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
