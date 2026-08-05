# Task: backfill P569 (date of birth) from Wikipedia infoboxes

Many people who hold a position on Wikidata have no birth date there, while
their Wikipedia article states one in the infobox. The infobox field is
structured, so the date can be lifted mechanically — no LLM reading prose —
and cross-checked against a second, independently maintained signal before
anything is written.

Run it **one country at a time**: the fraction of the gap that is reachable
swings from 90% (Bangladesh) to under 1% (Russia, Indonesia), so country choice
decides whether a run is worth doing at all.

## Feasibility (measured 2026-08-04/05)

| | |
|---|---|
| humans (P31=Q5) with P39, no P569 | **197,992** |
| …of those, with an enwiki article (random n=2,484) | **16.4%** → ~32,000 |
| …of those, with an extractable infobox date (n=407) | **9.8%** |
| global expected harvest, enwiki only | **~3,200** statements |
| agreement with existing P569 where Wikidata has one (n=66) | **95.5%** |

The 4.5% disagreement rate is *not* an extraction bug — spot-checked
mismatches are genuine enwiki-vs-Wikidata conflicts (e.g. Q84434578 infobox
`1985-07-03` vs Wikidata `1985-03-07`, a day/month transposition somewhere).
That number is the reason for the cross-check below rather than a straight
harvest.

So: a real but modest campaign. ~3k statements is worth doing, and it is not
the 100k-scale win the 198k headline suggests. The binding constraint is that
**84% of the gap has no English Wikipedia article at all**, and a further 64%
of the gap has no Wikipedia article in any language.

## Method: rendered microformat + category gate

**Extraction.** Do not parse `{{birth date}}` spellings. Fetch the *rendered*
section 0 and read the hCard microformat the templates emit:

```
{{birth date and age|1954|7|17|df=y}}   →   <span class="bday">1954-07-17</span>
{{Birth date and age|df=yes|1953|06|15}} →  <span class="bday">1953-06-15</span>
```

Argument order, `df=` flags and capitalisation stop mattering, and the value
arrives pre-normalised to ISO. It also **fails safe**: Kim Jong-un's
`8 January {{circa|1982–1984}}` emits no `bday` at all, so uncertain dates
self-exclude instead of needing a blocklist.

`{{birth year and age|1977}}` renders a bare year with *no* microformat, so
year-precision dates need a separate wikitext pass — that is the only template
parsing in the pipeline (`wd/infobox.py:YEAR_TPL`).

**The second signal.** enwiki maintains `Category:1965 births` separately from
the infobox, by different editors. Requiring the infobox year to equal the
category year is the two-independent-channels gate this repo runs on
everything else. Measured on 40 hits: 33 agree, 2 disagree, 5 have no
category. The 5% disagreement rate matches the independent 4.5% measured
against Wikidata's own values — the two channels are catching the same
underlying unreliability, which is what makes the gate worth having.

**Routing.** Only `batch` reaches a `.qs`:

| verdict | meaning | destination |
|---|---|---|
| `batch` | infobox year == category year | `day.qs` / `year.qs` |
| `conflict` | the two disagree | review — usually Wikipedia is wrong somewhere |
| `suspicious-precision` | day-precision `-01-01` | review; the year is likely fine |
| `duplicate-item` | several QIDs resolve to one article | review as merge candidates |
| `ambiguous-source` | >1 candidate date in the article | review |
| `flagged-uncertain` | article carries a "year of birth missing/unknown" category | review |
| `no-cross-check` | no birth-year category to confirm the infobox | review |
| `nothing-found` | no usable date | dropped, counted by shape |

Day- and year-precision go to **separate** `.qs` files: different concerns,
and precision-9 statements are a weaker claim worth approving separately.

## Where the reachable work is

`scripts/dob_country_sizing.py` output (2026-08-05). `enwiki` is the only
column that matters — and it does **not** track `gap`:

| country | QID | gap | enwiki | % | est. harvest |
|---|---|---:|---:|---:|---:|
| United States | Q30 | 15,155 | 8,358 | 55% | ~836 |
| India | Q668 | 4,755 | 3,384 | 71% | ~338 |
| Pakistan | Q843 | 2,449 | 619 | 25% | ~62 |
| Nigeria | Q1033 | 2,254 | 531 | 24% | ~53 |
| United Kingdom | Q145 | 2,300 | 424 | 18% | ~42 |
| Bangladesh | Q902 | 244 | 219 | 90% | ~22 |
| Malaysia | Q833 | 561 | 192 | 34% | ~19 |
| Philippines | Q928 | 449 | 160 | 36% | ~16 |
| France | Q142 | 9,038 | 110 | 1% | ~11 |
| Indonesia | Q252 | 4,425 | 20 | 0% | ~2 |
| Russia | Q159 | 5,104 | 2 | 0% | ~0 |

(Iran, Poland, Brazil, Turkey, Germany, Japan, Ukraine all land under 25
reachable items; full table in `data/birthdates/sizing.md`.)

**France, Russia and Indonesia are traps** — a combined 18,567 missing birth
dates and 132 reachable items between them. Those gaps come from bulk-imported
national registries and local-wiki articles, not from anything enwiki can fix.
The US and India together hold 83% of the reachable work in this table
(11,742 of 14,111); Bangladesh is tiny but the densest at 90%.

Note these 18 countries hold only ~51k of the 198k global gap — the rest have
no `P27` at all or sit outside this list, so the country table under-counts the
true total. The global ~3.2k estimate comes from the unbiased random sample,
not from summing this column.

## Recipe for one country

```bash
python scripts/dob_country_sizing.py                          # pick a target
python scripts/harvest_dob.py --country Q1033 --name nigeria  # harvest
```

Then read `data/birthdates/<name>/plan.md`, and run `day.qs` / `year.qs` in the
QuickStatements web UI yourself. Outputs per run:

* `plan.md` — every candidate grouped by verdict, with permalinks
* `day.qs`, `year.qs` — the batch rows only
* `evidence.json` — raw signals per article, for a verification agent
* `sizing.md` — the country table

**Request cost.** Wikitext + categories batch 50 titles per call; only the
~17% of articles with a filled `birth_date` parameter get an individual render
request (`wd/infobox.py:worth_rendering`). Nigeria: 531 people → ~11 batch
calls + 90 renders.

**Referencing.** `S143 Q328` (imported from English Wikipedia) plus `S4656`
with the revision permalink. `P143=Q328` is the dominant convention on P569 in
practice — 36 of 102 referenced statements in a 300-item sample, the most
common single reference value — and the permalink makes each value auditable
back to the exact revision it was read from.

## Proven run

**Nigeria (Q1033)** — 531 addressable → 47 statements (40 day, 7 year), with
3 conflicts, 2 Jan-1st placeholders, 2 duplicate items and 4 without a
cross-check held back for review. Spot-verified 6 batch rows against wikitext:
all correct. Files in `data/birthdates/nigeria/`.

## Gotchas

* **Never sample the gap population with a bare `LIMIT`.** WDQS returns the
  planner's cheapest rows, which are mythological and *fictional* — Namor,
  Grimlock and Selina Meyer all hold P39. Use CirrusSearch `srsort=random`,
  and enforce `P31=Q5` regardless (it excludes fictional characters, which
  `P39` alone does not).
* **`COUNT` over the gap join times out on WDQS**; CirrusSearch
  `haswbstatement:` + `srinfo=totalhits` answers the same question instantly.
  `-haswbstatement:P569` is the negation. Per-country enumeration *does* work
  on WDQS (India 17s, US 225s).
* Use `p:P569` not `wdt:P569` in the `FILTER NOT EXISTS` — a `somevalue` or
  deprecated-only birth date is present, and re-asserting over it is wrong.
* `SELECT DISTINCT` — a person with three P39 statements otherwise appears
  three times.
* **Infoboxes that read from Wikidata** (`{{#statements:P569}}`) are circular:
  the field is blank *because* P569 is missing. Excluded at triage.
* **Redirects collapse two items into one article** (Q13140890 "Wahab
  Dosunmu" / Q14479598 "Wahab Dosumu"). Batching both writes the same date
  twice and hides a merge; the harvest surfaces these for free.
* `Category:Year of birth missing` and `Category:1965 births` both match a
  naive "births" pattern — the former must not be read as a year.
* **January 1st is a placeholder**, not a birthday, at roughly 20× its
  1-in-365 share (2 of 42 day-precision hits in Nigeria, both written by hand
  as `{{Birth date and age|1960|01|01}}`). WORKBENCH.md flags the same
  artifact on Wikidata's own values. The year is usually right, so these are
  worth re-asserting at precision 9 after review rather than discarding.
* Non-English wikis are mostly *not* additional yield: many use
  Wikidata-driven infoboxes, so their birth-date field is empty for exactly
  the items in the gap. Locally-authored infoboxes (de, fr, ru, pl, ja) are
  worth testing before assuming otherwise; `--lang` accepts them but only
  en/de/fr/es have a `WIKI_ITEM` mapping for `S143`.

## Not done / open

* Only P39 holders are in scope. The same method over all humans (5.6M lack
  P569) would be far larger but is not PEP-relevant and would need a bot flag.
* Prose-only birth dates ("born 8 March 1956" with no infobox) are left on the
  table: 1 of 52 no-bday enwiki articles had one. An LLM pass could get these,
  but the volume does not justify it before the infobox tail is done.
* `{{Birth based on age as of date|52|2007|6|10}}` yields a year ±1 and is
  currently ignored.
* Non-enwiki languages unmeasured (see gotcha above).

## Status

- [x] Feasibility measured (yield, accuracy, per-country sizing)
- [x] `wd/infobox.py` extraction + gate; `wd/wikipedia.py` batch fetch
- [x] `scripts/harvest_dob.py`, `scripts/dob_country_sizing.py`
- [x] Nigeria run, spot-verified — 49 statements pending review
- [ ] User review of `data/birthdates/nigeria/plan.md`
- [ ] Nigeria `day.qs` / `year.qs` run in QuickStatements
- [x] US sized: 8,358 addressable — the largest target (needed patient retry)
- [ ] US (8,358) and India (3,384): 83% of the reachable work
- [ ] Then Pakistan (619), UK (424), Bangladesh (219, densest at 90%)
- [ ] Decide whether `conflict` rows are worth an LLM verification pass
