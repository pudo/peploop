---
description: Plan for Kazakhstan's three-lane sweep — a first peploop and pepcorp run and a second peptree run, seeded for the era of the July 2026 constitution (the unicameral Kurultai), with the measurements taken 2026-11-05, the seed and census drafts, the stage order and budgets, and the decisions that belong to the user.
date: 2026-11-05
tags: [sweep, kz, peploop, peptree, pepcorp, seeds, census, kurultai]
---

# Kazakhstan sweep

Run as `peploop/countries.md` §7. For peploop and pepcorp this is a **first run**:
there is no `countries/kz.yml` yet, so §1–2 (seed file and census) come
first. peptree already ran Kazakhstan: batch 0, 102 items, 3 lines `P31`,
submitted 2026-10-06. State `Q232`.

## The era: the 2026 constitution

The new constitution was approved in a referendum on 2026-03-15 and took
effect on **2026-07-01**. It dissolved the bicameral Parliament (the Mäjilis
and the Senate) and created the **Kurultai**: unicameral, 145 seats, its 1st
convocation elected on 2026-08-23. So the current era began four months ago,
and that shapes the whole run:

- **The Kurultai is the chamber now.** Wikidata has `Q141159337` member
  (1 holder), `Q140473689` chairman and `Q141159567` deputy chairman (0
  holders each). Those items exist, so they are in the load. Expect the
  1st-convocation seats to be the run's largest block of new `P39`s.
- **The old chambers have just closed.** Their members held office within the
  last few months, so they are still PEPs, and the seed takes the last
  convocation. On Wikidata, 140 of the 146 Senate statements (`Q21295141`) and
  77 of the 94 Mäjilis statements (`Q21328574`) have no end date, and almost
  none of them are ours. peploop adds an end only where the person's article
  gives one (the "ends added" route). Articles that haven't been updated since
  July will leave those tenures open; that is residue to report, not
  something to fix by hand.
- **No item marks the dissolution.** Neither chamber's member item has a
  `P576`, so `open_superseded` cannot fire on an open Senate or Mäjilis
  seat. Whether to add one is decision 1 below.
- `Q7925052` Vice President has one open holder. The run needs to check
  whether the 2026 text revived the office before it trusts that seat.

## Measurements (2026-11-05)

**Category trees.** ru.wikipedia is the regular wiki. It has a category per
portfolio, per Mäjilis convocation (I–VIII), per oblast and city akimate, and
per ambassadorial post (~118), plus the apex courts, the agencies, the
Accounts Committee, the CEC and the Presidential Administration. kk.wikipedia
is flatter but adds the vice-ministers (`Қазақстан вице-министрлері`, 50 pages).
en adds almost nothing: `Political_office-holders_in_Kazakhstan` at depth 2
contributes +6, which is the only `country: kz` entry in OpenSanctions'
`wd_categories.yml`. Two traps to avoid: `Министры_Казахстана` at depth 1
pulls in the Kazakh SSR commissars (150; the scope gate sets aside the dead),
and `Президенты_Казахстана` at depth 1 is the two presidencies' eponymous
trees, so it gets `depth: 0`.

**Wikidata's office set.** The descent reaches 144 items, so Kazakhstan is
Czechia-sized. The holder-ranked list:

- Well covered: the Senate (146), the Mäjilis (94), about 30 ministry items
  (`Q1077525xx`, `Q1277887xx`), PM, DPM, Presidential Administration,
  National Bank, KNB, Security Council, Prosecutor General.
- **Tiers with no item:** judges of the Supreme Court and of the
  Constitutional Court; outbound ambassadors (2 items against ~118
  categories); vice-ministers; the CEC; the Accounts Committee (now the
  Supreme Audit Chamber); the ombudsman; the agency chairs (Anti-Corruption,
  Financial Monitoring, the regulator ARDFM); most city akims. These are
  `census` entries, and the mentions behind them feed mint's creation queue.
- **Duplicate pair:** Kyzylorda Region akim, `Q115693303` (2 holders) vs
  `Q115603335` (1). The run uses the more-held one and checks afterwards that
  nothing landed on its twin. `Q126198202` "Mayor of Abai Region" is the Abai
  akim under an English label.
- **Not offices:** honorary titles and orders (People's Artist, Order of the
  Leopard), `Q97662173` "junior researcher", the Writers' Union chair
  (21 holders), every inbound ambassadorship. Read past them.

**PetScan, with each entry's marginal gain:**

| entry | lang, depth | members | marginal |
|---|---|---|---|
| Президенты / Вице-президенты / Премьер-министры | ru 0 | 2 / 2 / 19 | +22 |
| Заместители премьер-министра | ru 0 | 56 | +51 |
| Министры Казахстана | ru 1 | 393 | +333 |
| Заместители министров + Қазақстан вице-министрлері | ru 1, kk 0 | 23 + 50 | +51 |
| Аппарат Правительства, Администрация президента, советники, Іс басқарушылары | ru/kk | 8–39 each | +31 |
| Агентства, Счётный комитет, ЦИК, омбудсмены, генпрокуроры | ru 0–1 | 3–14 each | +22 |
| Судьи Верховного / Конституционного суда | ru 1 | 31 / 15 | +29 |
| Начальники Генштаба | ru 0 | 11 | +7 |
| Депутаты Курултая I созыва + en/kk Kurultai | ru 0, en 1, kk 1 | 56 + 23 + 25 | +63 |
| Мажилис VIII созыва | ru 0 | 102 | +72 |
| Депутаты Сената (all convocations, one bag) | ru 1 | 193 | +158 |
| Председатели палат | ru 1 | 15 | +3 |
| Акимы областей | ru 1 | 139 | +59 |
| Акимы городов | ru 1 | 270 | +197 |
| Послы Казахстана | ru 1 | 196 | +122 |
| Председатели партий | ru 0 | 22 | +9 |
| en ministers, en office-holders | en 1–2 | 192 / 229 | +11 |
| **total** | | | **~1,240** |

Left out: Mäjilis VII (+67, ended in 2023), district akims (+22),
`Государственные деятели` (+52) and `Политики Казахстана` (+142), which are
mostly history, and the generals' rank categories, which are ranks, not
offices.

**Cost.** About 1,240 people sits between Slovenia's 1,248 ($16.57 extract,
$16.73 reconcile) and Malta's 272, so roughly **$35 for extract and
reconcile**, plus a few dollars for the other stages. Budgets: extract $25,
reconcile $25, verify $10, mint $5, corp $10.

## Before the stages

1. **`countries/kz.yml` `seeds`**: the table above, shaped like `by.yml`
   (a comment block with sources and left-outs, entries by tier, each
   commented with its size).
2. **`census`**, with body QIDs measured live:
   - the oblast akims as a `per: subdivisions` entry over the 17 regions and
     the 3 cities of republican significance; some have items (Aktobe,
     Astana, Almaty, Kyzylorda, …), and those get loaded, not minted;
   - judges of the Supreme Court and of the Constitutional Court;
   - the outbound ambassadors, one office per host state;
   - vice-ministers, per ministry;
   - the agency chairs, the CEC chair, the Supreme Audit Chamber chair and
     the Commissioner for Human Rights;
   - the Kurultai chair and deputy chairs, if load does not reach them.

   Per the coverage-gain rule, mint only offices that add new PEPs. That
   counts vice-ministers, judges and ambassadors. It does not count a
   chamber's committee chairs.
3. **Present-tense markers for Russian and Kazakh.** `tenure.CURRENT` has
   neither, so every open ru/kk tenure falls to `open_unattested`. They need
   to be measured on the run's own open quotes at the `propose` checkpoint,
   with `check_tenure` cases (the Maltese pattern). Expect this to be the
   rule work with the most impact.
4. **Kazakh labels put the head noun last** (`plans/peptree_next.md`), which
   matters for the label channel and for mint's kk terms. Read kk labels in
   the mint dry run line by line.

## Stages

In the order of §7 (`tree place kz` through `report applied`), `--live` with
the budgets above. `report applied` has nothing to say yet. Points specific to
Kazakhstan, for each checkpoint:

- **load-positions:** confirm which Kyzylorda twin is used, and that the
  Kurultai items load as national.
- **reconcile:** an article written before July names "депутат Мажилиса" for a
  current Kurultai member. Those are two offices, and the mention must land on
  the Mäjilis with its end, never on the Kurultai.
- **propose:** check old-chamber seats with no end date, which only an
  article can close. Check that each Kurultai seat starts on or after
  2026-08 or the first sitting, not on the election date when the article
  gives the sitting.
- **mint (dry):** expect most guarded rows to be ambassadors and judges. Check
  that the akim offices and the duplicate pair come back `found`, not
  guarded.
- **corp run kz:** the `corp` section needs (a) `holdings`: Samruk-Kazyna and
  its main subsidiaries (KazMunayGas, Kazatomprom, KTZ, KEGOC, Kazakhtelecom,
  Kazpost, Air Astana, Samruk-Energy, QazaqGaz), the Baiterek holding and its
  development institutions, all with QIDs resolved live from their
  articles; (b) `forms`: measure whether the state-only forms РГП/ГКП
  (republican and municipal state enterprise) are typed on Wikidata;
  (c) `tiers: [national, regional]`. The National Bank and the regulators are
  statutory bodies, not enterprises (the Malta rule).

## Sends, each on the user's go

1. `tree send --batch 0 --submit`, if `tree place kz` finds anything new.
2. `mint --country kz --submit`, then `verify` and a fresh `send` dry run.
3. `send --country kz --submit`. One tranche if the dry run stays under
   ~1,500 people, which it should.
4. `corp send kz --submit`.

Then §6: add the `check_neutral.TOKENS` (Kazakhstan, `Q232`, `ru`/`kk`
wikipedia, Astana), write the `history.md` line, and propose the push.

## Decisions for the user

1. **Mark the old parliament dissolved?** Adding `P576` 2026-07-01 to the
   Parliament of Kazakhstan's item, plus `P1366` Kurultai, would let
   `open_superseded` hold back the ~200 open Senate and Mäjilis seats. That is
   a write outside all three lanes, though: a one-off `wb` edit with the
   user's say-so. Without it, those seats are listed as residue.
2. **City akims at full width** (+197 people, mostly regional-centre and
   industrial towns)? The default is to seed them. The alternative keeps only
   the 3 republican cities and the oblast centres, at about half the people.
3. **Mäjilis VIII and the Senate**, seeded as recently ended (the default), or
   Kurultai only? Leaving them out saves about 230 people and a fifth of the
   spend, but leaves current PEPs out.

(OpenSanctions' `kz_mazhilis` crawler reads a chamber that no longer exists.
That is outside this repository; it's noted here only so the closing report
can flag it.)

## Closing report (2026-11-06): dry runs done, sends proposed

Nothing has been sent. Spend: $160.76 (extract $41.63, resolve $65.94, mint
$36.84, verify $12.87, the rest small). The plan's $35 assumed Malta's
per-person rate; Kazakh articles carry three or four language versions, and
each spelling of each office is its own resolve.

**Sends, in order, each on the user's go:**

1. peptree: nothing (0 lines).
2. `mint --country kz --submit`: 9 items: akims of Almaty Region, Shymkent,
   Pavlodar, Ulytau, Zhetisu and North Kazakhstan; the chairs of the CEC
   (`P279` chairperson, pinned in the census), the Agency for Strategic
   Planning and Reforms, and the Commission on Human Rights under the
   President. No ordinal aliases are left. Then `verify` and a fresh `send`
   dry run for the seats these feed.
3. `send --country kz --submit`: 833 lines for 609 people, under the
   1,500-person tranche, so one batch. Creates: 288 `P39`, 477 `P27` (474
   Kazakhstan; Russia ×2, Switzerland, Kyrgyzstan), 17 `P569`, 1 `P570`, 4 `P21`.
   Merges: 23 `P39` (ends, mostly the Mäjilis at 2026-07-01 or 2023-01-19,
   and two US ambassadorships dated). 19 `P569` refinements (year to day).
   A 25-row sample read against its quotes found no error; the incumbents are
   the current akims, ministers, 20 Kurultai members and its chair and
   deputy chair.
4. `corp send kz --submit`: 81 lines (`P31` marker 14, `P127` 17, heads and
   chairs).

**Doubtful but left in, for the user's read:** `Q1377512` `P27` Switzerland
since 2008 (the kk infobox says so; asylum is not citizenship); Shahar Media
Group `P127` Kazakhstan, from a stub whose "now" dates from ~2008.

**Decisions for the user:**

- `Q110557338` and `Q137287653` are one person (Alibek Kuantyrov); merge?
  Rows on the first were taken out.
- `Q141159567` (Deputy Chairman of the Kurultai) is `P31` the member seat; the
  reader now copes, so leave it, or tell its creator.
- The old parliament's `P576`: no longer needed for this run (the dissolution
  is read and the Mäjilis seats end at it); still unrecorded on Wikidata.
- `prompts/extract.md:250` names Almaty and the Kazakh SSR outside an
  examples marker, so `check_neutral` now fails. Fixing it changes the
  extract prompt hash and re-keys every extraction.
- The Kurultai's 32 `resolution/medium` mentions need a re-ask path to be
  written.
