# Task: Belarus — category members → real P39 statements

Second country run of `recipes/category_check.md`, over the 15 Belarus specs in
`wd_categories.yml` (12 carrying a synthetic `position:` block, all English
categories at depth 0). Belarus is the opposite case to Ecuador: Wikidata's
coverage is already good, so the value here is less in the batch than in what
the run proves and documents.

## What the survey found (2026-08-05)

**Wikidata already covers Belarus well.** 628 position items carry
P17/P1001 = Belarus, with **2,016 P39 holder statements** — including seat
items with real depth (member of the House of Representatives, 481 holders;
Supreme Soviet, 177; Council of the Republic, 110 plus per-convocation items)
and a ministry item for every portfolio. Ecuador, by contrast, had 79 position
items and a ministry block sitting at 1–4 holders each.

Three structural differences drove the run:

* **The English categories are nearly empty.** 2–35 members each, against
  10× that in their Belarusian and Russian siblings (`en:Government_ministers_of_Belarus`
  35 → `be:Міністры_Беларусі` 243 at depth 1). Every office therefore harvests
  its interwiki siblings, resolved through the category item's sitelinks.
* **Rosters live on the office or ministry article.** Exactly one dedicated
  list article exists (`Список министров иностранных дел Белоруссии`, itself a
  redirect to the position article). Otherwise holders are tabulated on
  `Министр X Республики Беларусь` (11 such pages on ru, 14 on be) or — more
  often — listed as **bullets** under "Министры"/"Руководство" in the ministry
  article.
* **Three regimes share every office name.** The 1918 Belarusian People's
  Republic, the Byelorussian SSR and the Republic of Belarus each had a
  "minister of X", and the modern items are the Republic's. Both wikis keep
  separate БНР/БССР categories, and roster tables separate the regimes by
  section heading, so the routing is mechanical — but `uk:Прем'єр-міністри_Білорусі`
  files every BSSR council chairman as a "prime minister of Belarus", which is
  exactly the category noise this campaign exists to document.

## Result: 10 statements, and a much better parser

`data/belarus/{edit_plan.md,edit_plan.qs,roster_audit.md}`:
**10 batched adds** (two-channel, post-1991) — 5 industry ministers, 4 justice
ministers, and Piotr Kraučanka, the first foreign minister of independent
Belarus. 58 roster rows already held their P39. Held back: 42 category-only
(overwhelmingly BSSR/BNR officeholders swept in by the uk and en categories),
22 Byelorussian SSR, 7 BNR, 5 roster-only (information ministers, absent from
every category), 1 undated, 1 pre-1991 (Uladzimir Jahoraŭ, interior minister
from July 1990 across independence — a genuine continuity call).

**Sourcing is weaker than Ecuador's**: 0 of 10 statements carry a real
citation, because the bullet lists rarely footnote their rows, so all 10 cite
the roster permalink as S4656. Ecuador's ratio was 81 of 97.

Flagged in the audit: the ru industry list gives **overlapping terms**
(Q13132825 1996–2006 vs Q19918364 from 2003) — one of the two is wrong at the
source, and both are in the batch, so this needs a human eye before applying.

## What this run added to the tooling

The Ecuador engine only worked on Spanish tables. Now generic:

* `wd/campaign.py` — the country-independent engine (harvest, identify, gate,
  tier, audit); `scripts/by_ministers.py` is 130 lines of parameters.
* `wd/roster.py` grew Russian/Belarusian/Ukrainian month names and column
  vocabulary, folded-key header matching (і/ў/ё), acting markers written in
  the row text ("(в. а.)", "и. о.") rather than by legend colour, and
  `parse_bullet_rosters()` for `* [[Name]] (dates)` lists — including the
  dates-first shape and the trap where the bracketed years are a **lifespan**,
  not a term.
* Ecuador re-run on the new matcher: **94 → 97 adds** (Ordoñez Moscoso,
  Pesántez, Andramuño moved from "category only" to dated adds, Andramuño with
  a separate acting spell). Verified by diffing the verdict files.

## Not covered

* **The other 14 portfolios.** The wikis carry 26–28 minister subcategories
  (culture, education, energy, agriculture, forestry, taxes, housing, sport,
  antimonopoly/trade, natural resources, economy, architecture, emergencies,
  CIS affairs) and Wikidata has an item for each. Only the 12 in the yml were
  run; extending is a copy of the `Office` block per portfolio.
* **Deputy Prime Minister** (58 category members, 20 holders) is held whole:
  no roster names the deputy premiers, and the category mixes the rank with
  First Deputy Prime Minister (Q18690166).
* **Parliament seats**, where Belarus's real volume is (481 + 177 + 110
  holders). No yml spec covers them; the per-convocation Council of the
  Republic items suggest the community's convention is already settled, so a
  gap analysis there is the highest-value follow-up.
* ~~`Министерство связи и информатизации` parsed 0 rows after the date-phrase
  guard was tightened~~ — **fixed during the Czechia run (2026-08-05)**. The
  pattern was fine; `_is_date_phrase` was returning `False` for everything
  because its separator character class read `/-–` as a range covering every
  digit and letter. The page now parses, and the health bullets' leading dates
  are read as the term instead of the trailing lifespan: 7 `lifespan_not_term`
  records became 6 correct `historical_roster_only` adds (Сурта 1933, Киселёв
  1937, Инсаров 1948, Савченко 1966, Улащик 1987, Грицук 1980–1994), with
  Постоялко and Остапенко recognised as already covered. The 10 batched adds
  are unchanged.

## Status

- [x] survey: 15 specs, 628 target items / 2,016 holder statements, interwiki
  sibling harvest, roster inventory (2026-08-05)
- [x] engine extracted to `wd/campaign.py`; Cyrillic + bullet-list support in
  `wd/roster.py`; Ecuador re-verified (94 → 97 adds, all three new ones sound)
- [x] run: 10 batched adds, 79 review rows, `data/belarus/edit_plan.{md,qs}`
- [ ] human review → apply; check the industry date overlap first
- [ ] decide the held tiers: BSSR/BNR officeholders (do they belong on the
  modern items at all?), roster-only information ministers, Deputy PM rank
- [ ] extend to the 14 portfolios outside the yml, and to the parliament seats
- [ ] `wd_categories.yml`: propose `wikidata_id` for all 12 specs (the
  resolutions are verified) and drop the `position:` blocks that are now
  covered
