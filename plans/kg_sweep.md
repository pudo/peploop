---
description: Plan for Kyrgyzstan's three-lane sweep — a first peploop and pepcorp run and a second peptree run, seeded for the 2021 constitution and the Jogorku Kenesh's 8th convocation (elected 2025-11-30), with the measurements taken 2026-11-10, the seed and census in countries/kg.yml, stage order and budgets, and the decisions that belong to the user.
date: 2026-11-10
tags: [sweep, kg, peploop, peptree, pepcorp, seeds, census, jogorku-kenesh]
---

# Kyrgyzstan sweep

Run as `peploop/countries.md` §7, on the Kazakhstan pattern (`plans/kz_sweep.md`).
peploop and pepcorp have never run Kyrgyzstan, so this is a **first run**. The
seed file and census are drafted in `peploop/countries/kg.yml` and pass
`check_countries`. peptree has run Kyrgyzstan once: batch 18, reviewed
2026-10-07, 58 items kept, 0 lines. The state item is `Q813`.

## The era

- **The constitution.** The 2021 constitution is presidential. The Chairman of
  the Cabinet of Ministers is also head of the Presidential Administration.
  On Wikidata that office is `Q2333371` "Prime Minister of Kyrgyzstan", whose ru
  label is already the chairman's. Expect both titles to land on it.
- **The parliament.** The Jogorku Kenesh has one chamber of 90 seats. Its 7th
  convocation dissolved itself in 2025, and the 8th was elected on
  **2025-11-30**. Wikidata has a single seat item, `Q21091853`, with 37
  statements, 31 of them open. Some of those open seats belong to 7th-convocation
  members who were not re-elected. peploop closes them only where the person's
  article gives an end date. The rest are residue.
- **The president.** Japarov's term runs to January 2027. The propose
  checkpoint should confirm the incumbents rather than assume them.

## Measurements (2026-11-10)

**Category trees.** ru.wikipedia is the regular wiki, but its categories are
named `…_Кыргызстана`; the `…_Киргизии` names are empty. It has:

- a category per portfolio and for the vice-premiers;
- one bag of deputies for all convocations (177 pages and 3 subcategories), plus
  list articles for the V–VIII convocations;
- the Supreme Court chairs (17);
- Bishkek's mayors;
- 37 ambassador-per-host-state categories.

ky.wikipedia has the deputies by convocation (IV–VII) and almost nothing else.
en has a ministers tree and a legislators tree. There is no category on any wiki
for the regional governors (the President's plenipotentiary representatives) or
for the GKNB, the CEC or the Accounts Chamber.

**Wikidata's office set.** The descent reaches 82 items, about half of them
not offices: honorary titles, orders, inbound ambassadors, and "general".

- **Held:** PM (46), the deputy seat (37), Justice (19), President (15),
  Foreign Affairs (15), the Speaker (14), the Deputy PM (14), and about 20
  ministries with 1–7 holders each. National Bank, GKNB, Prosecutor General,
  the Chief of the General Staff, the State Secretary and the Vice President
  have 1–3 holders each.
- **Tiers with no item:** the regional governors, judges of either apex court,
  outbound ambassadors, the CEC, the Accounts Chamber, the ombudsman, and the
  Presidential Administration's head. These are the census entries.
- **Bare items:** `Q65149880` "Губернатор Ошской области" has no `P31`, `P17` or
  `P1001`. The load can't reach it, so mint's dry run has to *find* it (see the
  checkpoints). `Q134436561` "Mayor of Osh" is typed, with 0 holders.
- **Subdivisions.** `_subdivisions(Q813)` returns 10 units: the 7 regions,
  Bishkek, Osh, and `Q33225425` "Osh City", a cebwiki duplicate of Osh. The
  census excludes the two cities (which have mayors) and the duplicate.
- **No twins** for one era were found.

**PetScan, with each entry's marginal gain:**

| entry | lang, depth | members | marginal |
|---|---|---|---|
| Президенты / Вице-президенты / Премьер-министры / Вице-премьеры | ru 0 | 7 / 3 / 31 / 12 | +42 |
| Министры Кыргызстана | ru 1 | 160 | +137 |
| Government ministers of Kyrgyzstan | en 1 | 84 | +17 |
| Депутаты Жогорку Кенеша | ru 1 | 192 | +153 |
| VIII convocation list article | ru | 42 links | +6 |
| ky deputies + Kyrgyzstani legislators | ky 1, en 1 | 24 + 52 | +19 |
| Supreme Court chairs, Constitutional Court judges, prosecutors, ombudsmen, National Bank, General Staff | ru 0–1 | 2–17 each | +23 |
| Мэры городов + Mayors of places | ru 1, en 2 | 16 + 14 | +7 |
| Political office-holders in Kyrgyzstan | en 2 | 138 | +7 |
| **total** | | | **~440** |

Left out:

| entry | marginal | why |
|---|---|---|
| Послы Кыргызстана | +21 | no outbound item exists, and mint defers ambassadorships (as for KZ) |
| Политики Кыргызстана, depth 1 | +33 | Kirghiz SSR people, candidates |
| Генералы | +2 | ranks, not offices |
| local kenesh deputies | | |
| VI/VII convocation lists | +8 | ended |

**Cost.** Kazakhstan cost $171 for ~1,120 people, about $0.15 a head. Most of
that was resolve, because every language spelling of an office is its own
question. Kyrgyz articles are mostly ru and en, with ky on a few, so expect
less fan-out than Kazakhstan's ru/kk/en/uk. Estimate **$50–70** in all.
Budgets, `--live`:

| stage | budget |
|---|---|
| extract | $20 |
| reconcile | $30 |
| mint | $10 |
| verify | $8 |
| corp | $8 |

## Before the stages

1. **`countries/kg.yml`** is written: the seeds as above, the census
   (16 anchors) and a minimal `corp` section.
2. **Census anchors:**
   - 7 regional governors, with English labels only. Russian needs the
     prepositional case, so mint writes the ru term from the article's own
     title.
   - The judge and chair of the Supreme Court (`Q106498794`) and of the
     Constitutional Court (`Q5164291`).
   - The CEC, Accounts Chamber and ombudsman heads, which have no body item.
   - The heads of Kyrgyzaltyn (`Q25579369`) and Kyrgyz Railways (`Q247851`).
3. **Present-tense markers.** `tenure.CURRENT` has ru but no ky. Only 24 ky
   pages are seeded, so measure ky at propose and add it only if open ky
   quotes fall to `open_unattested` in numbers.
4. **pepcorp `holdings` is empty.** The design wants an official holdings
   list cited by `P854`; a wiki page or a query doesn't count. Before
   `corp run`, look for the State Property Management Fund's list of state
   enterprises and joint-stock companies (spf.gov.kg). If there is one, add
   the entries that have items; if not, the corp run relies on articles and
   categories. Measure the state-only forms ГП/МП (state and municipal
   enterprise) for `forms`.

## Stages

These run in the order of §7, from `tree place kg` through `report applied`.
At each checkpoint, check the following:

- **tree place kg:** see whether the second pass now picks up `Q65149880`
  (Osh Region governor) or the Osh mayor. If peptree can type the governor
  item, the governor tier gains a found office instead of a mint.
- **load-positions:** the PM item `Q2333371` and the deputy seat `Q21091853`
  load as national.
- **reconcile:**
  - "Председатель Кабинета министров" lands on `Q2333371`.
  - "Руководитель Администрации Президента" goes to the creation queue; it
    must not land on the PM item. Since 2021 the two are one person but two
    titles.
  - A "полпред"/"губернатор" mention resolves to its region's office, never
    to the Russian Federation's plenipotentiary items (`Q4370363`,
    `Q4370371`), which share the label.
- **propose:**
  - 8th-convocation seats start on or after the first sitting (December
    2025), not on the election date.
  - 7th-convocation seats with no end date stay open only where the
    article says nothing.
- **mint (dry):**
  - The Osh Region governor comes back `found` as `Q65149880`, not as a new
    item.
  - The Osh and Bishkek mayors come back found.
  - Expect most guarded rows to be judges and vice-ministers.
- **corp run kg:** read `data/pepcorp/kg/kg-<date>.md`. The National Bank is
  statutory, not an enterprise.

## Sends, each on the user's go

1. `tree send --batch 18 --submit`, if `tree place kg` finds anything.
2. `mint --country kg --submit`, then `verify` and a fresh `send` dry run.
3. `send --country kg --submit`. This is one tranche, since the run is well
   under 1,500 people.
4. `corp send kg --submit`.

Then §6:

- Add Kyrgyzstan's tokens to `check_neutral.TOKENS`: the name stem, `Q813`,
  `ky.wikipedia`, Bishkek.
- Write the `history.md` line.
- Propose the push.

## Decisions taken (2026-11-11)

1. **Ambassadors:** left out.
2. **`Q65149880`, the Osh Region governor**, was fixed before the run:
   `P31` position, `P279` governor `Q132050`, `P17` `Q813`, `P1001` Osh Region,
   and `P1313` on Osh Region pointing back to it. All cite the ru article
   (QS3 67002, peptree ledger). Its en label is still missing: the add path
   writes no terms on an item that isn't ours.
3. **7th-convocation exits are closed.** The 7th convocation kept its powers
   until the 8th was sworn in on **2025-12-17**, not on the 2025-09-24/25
   self-dissolution vote. Of the 7 open seats on `Q21091853` from that
   convocation, 4 holders sit in the 8th: Джумабеков, Сурабалдиева, Алимжанова
   and Рысбаев (who is in the VIII list but unlinked). The other 3 got `P582`
   2025-12-17, cited to economist.kg's report of the swearing-in (QS3 67004,
   peploop ledger): Маткеримов, Акаев and Айдарова. Акаев is Mayor of Osh
   from 2026-02-18 (`Q134436561`), which the run should pick up. The other
   open seats are older convocations (V, VI, undated) and are residue.

## Run (2026-11-11): every stage to its dry run

Model spend about **$41**, against an estimate of $50–70:

| stage | spend |
|---|---|
| tree | $0.76 |
| extract | $13.33 |
| reconcile | $17.35 |
| mint | $4.22 |
| verify | $5.26 |
| corp | $0.33 |

Logs are `data/logs/kg-*.log`.

| stage | result |
|---|---|
| tree place kg | 1 line pending, 1 struck (`P1001` on the General Staff, a body) |
| seed / load / fetch | 410 people, 130 positions, 289 fetched (116 out of scope, 8 not human) |
| extract | 289 people, nothing left unasked |
| reconcile | 2,128 mentions, 899 matched (876 same-office, 23 renamed) |
| mint (dry) | 1 item to create; 19 found; 194 not current; 141 with no archetype |
| propose / verify | 286 people decided; 339 asked |
| send (dry) | 239 lines, 171 people |
| corp run kg | 9 lines on 4 bodies |
| report applied | nothing sent yet |

### Checkpoints

- **reconcile**
  - "Председатель Кабинета министров" and its translations land on `Q2333371`.
  - The deputy chairmen go to `Q29561881`, and the first deputy to `Q112762996`.
  - Every mention of the Presidential Administration's head or deputy head
    resolves to `none`, never to the PM.
  - No polpred or governor mention lands on a Russian item. The Osh governor
    resolves to `Q65149880`; the other regions resolve to `none`.
- **mint**
  - All seven polpred entries are `not-current`: no current governor has an
    article. That leaves them as residue.
  - The other census anchors (both court presidents, Constitutional Court
    judge, Accounts Chamber, ombudsman, Kyrgyzaltyn, Kyrgyz Railways) are also
    `not-current`, and the CEC is unattested.
  - Only the Supreme Court judge is minted: 3 holders, 1 current.
- **propose**
  - All 8th-convocation open seats start on **2025-12-17**, except two at
    year precision, "2025".
  - Салымбеков's seat, open since 2024-09, is his VII-and-VIII continuation,
    the same way the four re-elected seats were kept open.
  - Акаев takes the Osh mayoralty from 2026-02-18, and Токторбаев's mayoralty
    closes the same day.
  - Speaker: Маматалиев from 2026-02-12, and Шакиев closes on that date. That
    settles the speaker question from the plan.
  - The 51 VII-convocation open seats fall to `open_unattested`: right, since
    that convocation ended on 2025-12-17. None of them is from a ky article,
    so `tenure.CURRENT` needs no ky.
- **Rule fix, `79bd5f0`.** Two Ministers of Education were open:
  - Иманалиев, whose ky infobox gives "2023" and no end;
  - Кендирбаева, from 2023-10-06.

  News shows Иманалиев held the post 2023-03-06 to 2023-09-07. The new rule
  `open_superseded/unordered` skips a year-wide open start on a one-holder
  seat when another holder's dated open start falls inside it. It fired once.

## Send proposal

1. **`tree send --batch 18 --submit`: 1 line.**
   - `Q110751928` "Ambassador of Kyrgyzstan to Bulgaria" gets `P31` `Q294414`.
   - **Flag:** this is an ambassador item. It types an existing post and
     creates nothing, but you left ambassadors out. Strike it, or send it.
2. **`mint --country kg --submit`: 1 item, "Judge of the Supreme Court of
   Kyrgyzstan".**
   - Terms: en, ky, ru.
   - Statements: `P31` `Q294414`, `P279` `Q117826617`, `P1001` `Q813`,
     `P361` `Q106498794`.
   - Then run `verify` and a fresh `send` dry run.
3. **`send --country kg --submit`: 239 lines for 171 people, in one tranche.**

   | kind | property | lines |
   |---|---|---|
   | new statement | `P39` | 119 (24 open) |
   | new statement | `P27` | 96 (95 Kyrgyzstan; 1 Belarus, Usenov's ky article) |
   | new statement | `P569` | 6 |
   | new statement | `P21` | 2 |
   | merge | `P39` | 10 (7 are inferred `P582` with no reference) |
   | merge | `P569` | 2 |
   | switch | `P569` | 4 (year to day) |

   **Flag:** 4 lines go on existing ambassador posts, to Russia (`Q105139129`)
   and Tajikistan (`Q105159245`), for people in scope for other offices. I
   propose sending them, since they create nothing. The alternative is to
   strike them, in keeping with "leave out ambassadors".
4. **`corp send kg --submit`: 9 lines.**
   - `P127` `Q813` on the National Bank, Kyrgyz Post and KTRK.
   - `P31` public broadcaster on KTRK.
   - `P1037` for 3 former National Bank chairs and 1 former KTRK head.
   - `P488` with `P582` 2014 for Babanov at Respublika.
   - No official holdings list was found, so `holdings` stays empty.

## Not proposed: for your decision

- **`renamed` resolutions are never written** (`policy.P39_KINDS`, a global
  rule). In Kyrgyzstan this loses three closures on items that are the same
  seat:
  - Akylbek Japarov's PM end, 2024-12-16. His statement is still open, which
    also stops the cabinet rule from working here (two open PMs).
  - The current National Bank chair, Baketaev, from 2026-03.
  - Turgunbaev's National Bank end.

  Widening the rule changes every country, so it waits for you.
- **VII-convocation deputies who did not return (about 45)** could get a
  closed seat, with the convocation's end as `P582`. That needs a rule
  closing a chamber's tenures at a known convocation end. It is an expansion
  candidate, not done.
- **Residue:**
  - the polpred tier and the other census anchors with no current holder in
    an article;
  - the VII-and-older open seats with no end date;
  - 13 corp seats whose person has no item.
- **`check_neutral`:** 2 hits in `peploop/prompts/extract.md:250` ("Almaty,
  Kazakh SSR"). That line predates both sweeps, and the Kazakh tokens now
  catch it.

## After the sends (§6)

- Add Kyrgyzstan's tokens to `check_neutral.TOKENS`.
- Write the `docs/history.md` line.
- Push `0e1cd16`, `503d741`, `79bd5f0` and this report.

## Sent (2026-11-11)

| send | QS3 batch | result |
|---|---|---|
| peptree, batch 18 | 67085 | 1/1 |
| mint | 67086 | `Q142115524`, 8/8 |
| peploop | 67157 | 241/241: 239 rows applied, including 2 judge tenures on the new item |
| pepcorp | 67158 | 9/9 |

Nothing was refused, and no removals were pending. The tokens and the
history line are written. Next: the `renamed` rule.

## `renamed` re-ask (2026-11-11)

- **Prompt:** changed in `4e227d2`.
- **Re-ask:** all 894 newest `renamed` mentions, for $9.81. The script is in
  the scratchpad (`reask_renamed.py`).
- **Kyrgyzstan:** 3 new lines, dry run:
  - Baketaev, current National Bank chair, from 2026-03-18;
  - Turgunbaev, Minister of Natural Resources, 2023–24;
  - Isabekov, agriculture, 2006-05 to 2007-01.
- **Still out:**
  - Turgunbaev's National Bank tenure: the first mention stays
    renamed/medium.
  - Japarov's PM end: now wrong-office/medium.
- **Sent:** QS3 67165, 3/3.
- **Other 23 countries:** not re-proposed. Those runs may belong to other
  sessions, and their sends need the user.
