---
description: Improve peploop's position retrieval — an LLM-written English title as a second search channel, an outbound-ambassador discovery lane, and a re-ask of refusals whose shortlist changed. Measured on 8 countries, including forced title qualifiers and an era prior (both rejected).
date: 2026-10-03
tags: [peploop, positions, reconcile, retrieval, multilingual, embeddings, discovery]
---

# peploop: placing office mentions that retrieval cannot reach

Related: `plans/peploop_mint.md` (the creation queue whose `found` items this
plan makes retrievable), `plans/slovenia_sweep.md` (where the index and the
reconcile ledger were introduced).

## The question

On cu, co, by, bi, do, ht, jm, tt, 557 in-scope people with no `P39` had every
office mention unplaced; 537 of them carry 1,903 mentions whose newest verdict
is `none`. Is that retrieval (the item exists and the shortlist did not offer
it), discovery (the item exists and is not in `position`), or genuinely missing
items (the mint queue's job)? And what is the cheapest change that moves it?

All prototypes, sets and rankings are in the session scratchpad
(`scratchpad/eval/`, scripts `build_sets.py`, `baseline.py`, `canon.py`,
`alias.py`, `embed.py`, `emb_rank.py`, `fuse.py`, `exact.py`, `score.py`).
Nothing in `peploop/` was changed and nothing was written to Wikidata or to the
peploop database.

## Evaluation sets

| set | n | what it is | gold |
|---|---|---|---|
| **pos** | 2,177 | newest `same-office`/high verdicts, stratified ≤110 per (country, language bucket) | the verdict's QID |
| **hard** | 548 | every attestation of a mint candidate in status `loaded` (found or created), read from the original refusal | the candidate's QID (3 golds dropped: a college, a commission and a city council that `guard:duplicate` had accepted as "the office") |
| **labA** | 19 | the (a) rows of the hand-labelled sample | hand-found QID |
| **stranded** | 1,903 | the `none` mentions of the 537 people above | none (used for churn and cost) |

**pos is biased toward the current retriever by construction** — every row was
answered from a lexical shortlist, so lexical recall@15 is ~100% there. It is a
non-regression check (does a change push known answers out?) and an @1 signal,
never evidence of a gain. Gains are read off **hard** and **labA**.

## Measured baseline

recall@1/5/15/50 of `reconcile.shortlist_hits` (SHORTLIST = 15):

| set | ALL | en | es | fr | be | ru | other |
|---|---|---|---|---|---|---|---|
| pos | 81/94/100/100 | 87/97/100 | 87/96/100 | 85/95/100 | 79/93/100 | 80/94/100 | 68/88/99 |
| hard | **45/60/62/79** | 58/88/90 | 55/63/63 | 12/18/18 | 71/80/88 | 50/50/50 | **8/12/15** |
| labA | 3/19 on the shortlist | | | | | | |

By country, hard @15: tt 92, jm 91, co 67, by 59, cu 55, bi 49, do 44, **ht 8**.
Haiti and the Dominican Republic are the en-only cabinet case: of the country's
non-office-excluded positions, 54% (tt), 31% (jm), 23% (bi), 19% (ht), 17%
(do) carry an English label and nothing else, and the gold sits at rank 40–60
behind every other "Minister of … of the Dominican Republic" because the title
`Ministro de la Juventud` shares only the `minist` prefix with
`Minister of Youth of the Dominican Republic`.

Already in the document, contrary to the brief: `search_text` holds every label
and alias in every language, every name of the `P1001`/`P17`/`P361`/`P2389`/
`P1365`/`P1366` targets, and each `P279` parent's best label. So "add the body
and the jurisdiction" (option c) and "the body's Spanish label" (option d) are
*already implemented*. They do not help here because the en-only ministers'
body is `Q3112605`/`Q18379707` — the government, not the ministry — whose
Spanish name contributes "gobierno república dominicana", not "juventud".

## The hand-labelled split of `none` (150 random stranded mentions)

| label | n | share | ≈ of 1,903 |
|---|---|---|---|
| (a) item exists | 19 | 12.7% | ~240 |
| (b) no item, PEP office | 81 | 54.0% | ~1,030 |
| (c) not a PEP office / out of scope | 50 | 33.3% | ~630 |

Labelled by reading the title, dates and the country's `position` rows, then
searching Wikidata (prefix and full-text) and checking known holders' `P39`.
(b) is therefore an upper bound on "missing": an item with an unusual label can
hide from both searches. Party leaders and party bodies, regional KGB chiefs,
deputy ministers, Colombian city mayors (no per-city item; Wikidata has the
Spanish homonyms only), Tobago House of Assembly, PARLACEN, CSTO are all (b).
(c) is UN staff, municipal councillors, lower courts, opposition councils,
academy officers, embassy staff below ambassador, a gang leader.

**The (a) rows split three ways**, and only one of them is retrieval:

| | n | example |
|---|---|---|
| on the shortlist, model refused (a rename the model would not assert) | 3 | `Міністар гандлю` → *Minister of Antimonopoly Regulation and Trade* |
| loaded, not retrieved | 5 | `Ambasador … w Królestwie Tajlandii` → *ambassador of Belarus to Thailand*; `congressman` → *Member of the Chamber of Deputies of the DR* |
| **not in `position` at all** | **11** | nine outbound ambassadorships (Belarus to Bulgaria ×3, Ecuador, Estonia, Italy, Romania, Vietnam, Belgium; Cuba to Guinea), *Vice President of Haiti*, *President of the Supreme Court of Justice* (Colombia; an item with no claims) |

The discovery gap is structural. An outbound mission is scoped `P17` = the
*receiving* state (`Q133822129`: `P17 Q219` Bulgaria), so `descent` never reaches
it; nobody holds most of them yet, so `usage` and `citizen` don't either.
Wikidata has 84 items `P279 Q21814438` "ambassador of Belarus"; **27 are not
loaded**. 313 of the 1,903 stranded mentions (16%; 164 in Belarus) are
ambassadorial.

So **for the stranded people, discovery matters more than retrieval**, and
more than half of the bucket is the mint queue's (b). Retrieval is what
decides the hard set — the items mint already found or created — where it is
the whole story.

## What each option bought

All rows are recall@1/5/15/50; "fill" means the first channel's top-N
followed by the second channel's ranks, deduplicated, cut at 15.

### (a) LLM canonicalisation — the title in English Wikidata-label form

`claude-haiku-4-5`, 25 titles per request, the country and jurisdiction given,
answers `{id: English name}`. "ambassador of Belarus to Bulgaria",
"member of the Chamber of Deputies of the Dominican Republic", "Minister of
Defence of the Dominican Republic". The canonical title goes through the
*existing* `positions.search` (with the article's jurisdiction string), so the
signals and the pool are unchanged.

| variant | pos | hard | hard es | hard fr | hard other | labA |
|---|---|---|---|---|---|---|
| lexical (baseline) | 81/94/100/100 | 45/60/62/79 | 56/64/64 | 12/18/18 | 8/12/15 | 3 |
| canonical only | 89/96/98/99 | 77/87/91/95 | 70/76/88 | 94/94/94 | 62/87/88 | 5 |
| RRF(lex, canon) | 85/97/99/100 | 54/66/81/94 | | | | 3 |
| lex top-10, canon fill | 81/94/100/100 | 45/60/93/97 | 56/64/92 | 12/18/94 | 8/12/89 | 6 |
| **canon top-10 (exact-name first), lex fill** | **92/97/100/100** | **82/90/93/96** | 80/86/94 | 94/94/94 | 70/89/91 | 6 |

- **Exact-name promotion** moves a candidate up when one of its names has
  exactly the canonical title's content tokens. It is worth +5 @1 on hard and
  +3 on pos and nothing @15; applied to the *raw* title it costs 5 points @1 on
  pos (generic names match exactly), so it belongs to the canonical channel
  only. Example it fixes: "Minister of Defence of the Dominican Republic" is
  the gold's label verbatim and still ranked 18th by coverage, because every
  sibling ministry ties and the freshly loaded gold has no holder count.
- **Canon-first with a lexical fill strictly dominates** the baseline: no pos
  answer leaves the fifteen, and hard @15 goes 62 → 93.
- **Cost**: 3,819 unique titles = 149,937 input + 65,785 output tokens =
  **$0.48, i.e. $0.13 per 1,000 titles** ($0.06 under the Batches API); 83 s
  wall clock at 6 threads.
- **Not deterministic**: a second run over hard's 414 titles agreed exactly on
  66% and case-insensitively on 72% ("House" vs "Chamber of Representatives",
  adding "of Colombia"), with identical recall (91 vs 91 @15). So the
  translation has to be *cached*, keyed like every other model output, or a
  shortlist cannot be reproduced.
- Its residual misses are offices whose Wikidata name differs in kind, not
  language: "Mayor of Minsk" vs *chairman of the Minsk City Executive
  Committee*, "Secretary of State for Labour" vs *Minister of Labour* (the
  prompt says not to modernise, on purpose), and Belarusian local-council
  seats modelled per convocation in Russian only.

### (b) Multilingual embeddings

Fresh venv, CPU torch 2.14, sentence-transformers 6.1. Every distinct name of
every one of the 17,622 loaded positions (137,522 names, capped at 40 per item)
plus one context line per item (label | description | kind | part of |
jurisdiction | country) = 155,144 vectors; an item scores the max over its
vectors; `+β` for an item of the asking state (`country_qid` or a local holder
count), β = 0.05 (0.1 was flat or slightly worse for e5; the prior matters
because "Minister of Health" otherwise ranks every state's minister equally).
Query = title + " — " + jurisdiction (raw) or the canonical title (canon).

| model | dim | encode 155k names, 4 CPU | peak RSS | raw | canon | lex top-10 + raw fill |
|---|---|---|---|---|---|---|
| paraphrase-multilingual-MiniLM-L12-v2 | 384 | 615 s (252/s) | 2.1 GB | hard 42/52/62/73 | 81/86/91/95 | 45/60/80/87 |
| multilingual-e5-small | 384 | 698 s (222/s) | 2.1 GB | hard 41/60/82/96 | 45/91/96/98 | 45/60/86/96 |
| multilingual-e5-base | 768 | 2,452 s (63/s) | 3.5 GB | hard 43/69/91/97 | 58/89/94/97 | **45/60/90/97** |
| LaBSE | 768 | 2,102 s (74/s) | 3.4 GB | hard 44/56/61/68 | 60/93/94/96 | 45/60/86/91 |

(MiniLM raw at β = 0.1, the rest at 0.05. Encoding rates were taken with other
jobs sharing the 4 CPUs, so they are upper bounds on time. Queries encode at
47–192 per second batched.)

Scoring is brute-force numpy: 1.1–1.4 ms per query over all 155k vectors;
the matrix is 119 MB (384-d) or 238 MB (768-d) as float16. pos for every
embedding-filled hybrid stays at 100 @15.

- **Without an LLM**, e5-base is the only channel that comes close to
  canonicalisation: lex top-10 + e5-base fill = **90 @15** on hard against 93
  for the canonical fill. MiniLM is not good enough raw (80).
- **On top of canonicalisation** any of them adds the same small amount:
  canon-first + lex + 2 embedding rows = **96–97 @15** on hard (from 93;
  LaBSE 97/97, e5-base 96/99, e5-small 96/99). e5-small does it as well as
  the base models. LaBSE is the weakest raw channel.
- Embedding @1 is poor (24% on hard's English rows): name-level cosine ties
  across every country's identically-labelled office. They are a *recall*
  channel, never an ordering.

### (c) Index enrichment without models

- *All languages in `position_name`*: already so.
- *P279, body and jurisdiction labels in the document*: already so (see the
  baseline section).
- *A learned alias table* — every newest `same-office`/high verdict's title as
  an alias of its QID, scored by token Jaccard, leave-one-person-out: 7,982
  aliases on 771 items. Alone 51/62/68/76 on hard; lex top-10 + alias fill
  71 @15. It adds nothing once the canonical channel is in (93 → 92), and it is
  empty for every new country, which is exactly where retrieval is weakest.
  Not recommended; the ledger already *is* this table if it is ever needed.
- *MP and constituency forms*: `search_title` already handles "MP" and
  "Member of … for <constituency>". The remaining forms ("Abgeordnete für St
  Catherine Central", "Deputy for the National District", "diputado",
  "Sénateur du Centre") are what the canonical channel fixes, in every
  language at once.

### (d) Cross-lingual through the body's label

Already in the document, and empty where it matters: the en-only DR, Haiti,
Burundi and T&T ministers' `P2389` points at the *government*, not the
ministry. Making it useful would mean repointing items on Wikidata, which is
model-the-item-first work and not a retrieval change.

### (e) Discovery: outbound missions

Not a retrieval experiment, but the largest single (a) cause. An extra
discovery lane — items `P279` a class that is itself `P279*` `Q121998`
(ambassador) and scoped to the state (`P17`/`P1001`/`P642` = state), i.e. the
children of "ambassador of Belarus" — would have loaded 27 more Belarusian
items, and Haiku's canonical titles for the nine stranded Belarus/Cuba
ambassador rows match those items' English labels **verbatim**. With the
lane and the canonical channel, labA goes from 3/19 to ~17/19 on the
shortlist.

### Other things the data showed

- **Homonym placements already happen.** `Q26702560` *mayor of Chía* (Spain,
  "political position in Spain") was placed 4× for Colombian Chía and
  `Q26698687` *mayor of Bello* once; the policy skipped them, nothing was
  applied. The candidate line shows label and description but never the
  item's country or jurisdiction. Higher recall will offer more such
  homonyms ("Alcalde de Pereira" already pulls *mayor of Ferreira* and *mayor of
  Pereiro de Aguiar*, both Spanish, to ranks 1 and 3).
- **Mint's `guard:duplicate` accepted non-offices** as the found item: a
  Jesuit college for "Alcalde de Montería" (6 attestations), a
  constitutional commission, a city council. Worth its own fix in `mint.py`;
  out of scope here.
- **62 hard attestations are already retrievable today** (the MP fix landed
  after their feed) and were never reopened.

## Title expansion and era prior (measured)

A second run on the same sets and the same live table, re-running every
channel fresh (scratchpad `r2/`: `qualify.py`, `resolve_jur.py`,
`run_search.py`, `compare.py`, `era.py`, `final.py`, `ordered.py`). Nothing in
`peploop/`, the DB or Wikidata was written; candidate spans were read live
(`P571/P576/P580/P582`, `P279`, `P1365/P1366` for all 17,641 positions, cached in
`r2/claims.json`), holder spells from the people in `item` (8,395 dated `P39`
spells), the mention's own person excluded.

Succession slices: **do/jm/cu** by country; **P1365/6** = the gold carries a
replaces/replaced-by; **sibling** = the gold shares a `P279` parent with
2–10 other positions of the same state (a broader parent is a class, not a
succession).

recall@1/5/15:

| variant | pos | hard | hard en | hard es | hard fr | hard be | hard ru | hard other | hard do/jm/cu | hard P1365/6 | hard sibling | labA @15 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| lexical (today) | 81/94/99 | 45/60/62 | 58/88/91 | 56/64/64 | 12/18/18 | 66/77/86 | 50/50/50 | 8/12/15 | 43/70/72 | 58/89/89 | 46/56/58 | 3 |
| **(a) canon top-10 exact-first, lex fill** | **92/97/100** | **82/90/93** | 91/95/96 | 80/86/94 | 94/94/94 | 60/71/80 | 79/92/100 | 70/89/91 | 93/97/98 | 68/89/95 | 77/81/88 | 6 |
| (b) + forced " of <state>" when the canonical names no place; qualified 10, canonical, lex | 92/97/100 | 82/90/93 | 91/95/96 | 80/86/94 | 94/94/94 | 60/71/80 | 79/92/100 | 69/88/90 | 93/97/98 | 68/89/95 | 77/81/88 | 6 |
| (b-sub) + forced " of <subdivision/municipality>" whenever the jurisdiction resolves to one | 92/97/100 | 81/90/93 | 89/95/96 | 80/86/95 | 94/94/94 | 60/71/80 | 79/92/100 | 69/88/90 | 91/97/98 | 68/89/100 | 77/81/89 | 6 |
| raw `search_title` + forced qualifier, no model (exact-first 10, lex fill) | 84/95/99 | 53/63/68 | 82/90/93 | 53/64/67 | 21/41/44 | 66/77/86 | 46/50/58 | 9/16/24 | 65/72/77 | 63/89/89 | 46/57/60 | 4 |
| (c) (a) + era prior, best setting on the tuning half | 92/97/100 | 82/90/93 | 91/95/96 | 80/86/94 | 94/94/94 | 60/71/80 | 79/92/100 | 69/89/91 | 93/97/98 | 68/89/95 | 77/81/88 | 6 |
| (d) (a) top-13 + e5-small (raw query) fill | 92/97/100 | 82/90/**96** | 91/95/100 | 80/86/95 | 94/94/94 | 60/71/86 | 79/92/100 | 70/89/92 | 93/97/100 | 68/89/100 | 77/81/89 | 5 |

(a) reproduces the first run exactly (92/97/100, 82/90/93, 6/19).

**(b) buys nothing, because Haiku already writes the state.** 529 of 548 hard
and 2,070 of 2,177 pos canonical titles already name a place under a
deterministic gazetteer test (the state's names in six languages, its `P150`
subdivisions, every sovereign state, the resolved jurisdiction). The 107 pos /
19 hard titles it leaves bare are mostly *not the state's own office* — the
East African Legislative Assembly, the Supreme Soviet of the USSR, a university
rector, a US state assembly — and there the qualifier is wrong: on those rows
(a) is already worse than lexical at @1 (75 vs 82 on pos) and (b) worsens it to
71 ("member of the East African Court of Justice **of Burundi**", "rector of
EAFIT **of Colombia**", "…Supreme Soviet of the Soviet Union **of Belarus**").
The omission is a signal, not a gap. Vs (a): pos −6/+2 @1, 0 @15; hard −1 @1 and
−1 @15 (*Slonim District Executive Committee **of Belarus*** pushed the gold
from 1 to 72 — the appended state outweighed the district).

**Forcing the subnational place over-qualifies**: (b-sub) loses 19 pos and 6
hard @1 and wins 4 and 0. The cases are exactly the feared ones —
"Senator for the province of San Pedro de Macorís" → *Senator of the Dominican
Republic of San Pedro de Macorís* ranks the *Roman Catholic Bishop of San Pedro
de Macorís* first and the Senate seat third; "Member of the Council of the
Republic" with a Mahilyow/Vitebsk jurisdiction ranks the regional council
chairman over the national seat. No row moved onto the fifteen. Jurisdiction
resolution was also fragile: of 556 distinct (state, jurisdiction) strings,
`wbsearchentities` + `P150`/settlement closure resolved 110 first-level and 50
municipalities; inflected forms ("Мінскай вобласці", "Republiki Białorusi"),
constituencies and bodies stay unresolved.

**English titles still want the model.** The deterministic qualifier on the
raw English title is the cheapest English gain on offer — hard en @1 58 → 82,
Jamaica @1 53 → 89, pos en 87 → 91 — but (a) takes the same rows to 91/95/96
(pos en 95/99/100). The canonical pass covered en mentions in the first run as
well; nothing to re-run. As an addition to (a) (`a` top-13, raw-qualified fill)
it adds 2 hard rows @15 and nothing else.

**(b′) was not run.** It only pays if (b) beats (a), and (b) is flat. Its cost
would be a `title_en.md` prompt change — a new prompt hash, so every cached
title re-translates: ~12,300 titles ≈ $1.60 at Haiku rates for the 8
countries — to move at most the 3–5% of titles Haiku leaves stateless, which
are the rows where a state hurts.

**(c) The era prior has nothing to work on.** Of the 44 hard and 98 pos
mentions whose gold sits at rank 2–5 under (a), **36 and 84 have no declared
date on either the rank-1 item or the gold**; the misses are portfolio and rank
(deputy vs chairman, *Minister of Labour* vs *Health and Social Protection*),
homonyms (*mayor of Madrid*, Spain, over *Alcalde de Madrid Cundinamarca*) and
direction (*ambassador of Germany to Burundi* over *Burundian Ambassador to
Germany*). Declared spans are thin: of the 1,942 / 978 distinct items on the pos
/ hard shortlists, 370 / 176 have a declared start and 92 / 42 an end; 20 / 548
hard golds have a declared start. Measured, split by person (tune on 266 hard /
1,160 pos, report on 282 / 1,017):
- conflict-only demotion, shortlist level: W=1 is a no-op, W≥2 costs
  1 point @1 on hard (*Prime Minister of Burundi* demoted below *Minister of
  Finance*: the gold's own declared dates contradict the tenure, 4 hard golds
  do); in-search penalties of 0.3/0.6/1.0 cost 2/7/12 points @1.
- any *support* bonus (span covers the tenure; another holder's spell overlaps
  it; closest declared start) loses 10–70 points @1, because the fresh,
  undated gold loses to its dated, held sibling or parent class.
- **`first_held_year` and holder spells are not start dates.** Read as the
  office's start, they put 218 of 2,177 pos golds (10%) and 82 hard golds into
  conflict: *Minister of Justice of Burundi* "first held 2005" against a 1975
  tenure, because the community only recorded recent holders. Only
  `P571`/`P580` (`inception`) and `P576`/`P582` (`abolished`) may demote.
  This matches the existing `WEIGHTS` reasoning: `date_fit` stays 0,
  `date_conflict` stays as it is, on declared dates only.

**(d) e5-small still adds recall, not order**: hard @15 93 → 96 (17 won, 5
lost: four "Concejal de Pereira" rows whose gold is the mis-guarded *councillor
of Barranquilla*), 0 @1, pos −3 rows @15 (3 rows to rank 16–17), labA 6 → 5 (the
Haitian *Secrétaire d'État de l'Intérieur* falls off at 14). The canonical
query embedding is no better as the fill than the raw one. Same verdict as
before: real but small, and not worth torch and a re-embed per load yet.

**Two smaller findings from the regressions.**
- Exact-name promotion compares token *sets*, so *ambassador of Germany to
  Burundi* exactly matches "ambassador of Burundi to Germany". Comparing the
  ordered content-token sequence instead: pos @1 +12/−8 (the Burundi embassy
  rows won; eight Belarusian "Deputy Head of the Presidential Administration"
  rows lost, because the gold's names put the words in another order — "Deputy
  Head of the Administration of the President" — so only the set match promoted
  it, and *First Deputy Head* took rank 1 on text), hard and labA unchanged.
  Net +4 rows on pos. The Burundi gold (*Burundian Ambassador to Germany*)
  has no exact name under either test; the set match promoted the
  wrong-direction item past it, and the ordered match simply promotes nothing.
  So "ordered first, set second" reproduces (a) exactly (0 rows moved on any
  set): the gain comes only from dropping the set match. Too small to change
  step 2's spec; the bench in step 2 can carry it as a flag.
- A foreign-state demotion inside the fifteen (candidate's `P17`/country is
  another state, not diplomatic) wins 5 hard @1 (Madrid) and loses 10 pos @1
  (US state legislators, the USSR Supreme Soviet), net zero. The homonym case
  is the model's to refuse once it can see the country — step 5 — not the
  ranking's.

**Determinism and cost of each step.** (a) is the only model step: $0.13 per
1,000 titles ($0.06 batched), 66% exact agreement between two runs, so it must
be cached (step 1 already says so). (b), (b-sub), (c), (d) and ordered exact
promotion are deterministic given the table; (b) additionally needs a
jurisdiction resolver (live search, ~1,400 API calls for 697 strings here,
throttled at 6 threads), and (c) a live span fetch (353 `wbgetentities` calls,
6 minutes) refreshed on every load.

**Recommendation: keep (a) unchanged.** No qualifier composition anywhere —
neither in `titles.py` nor in `shortlist_hits` — and no era prior in either
`positions.search` or `shortlist_hits`. Step 2 stays as specified; the
order-sensitive exact match is a +4-row option for its bench, not a
requirement.

## Estimated end-to-end gain

Using canon-first + lex fill (recommended), with and without the
outbound-mission lane. Placement is conditional on the model accepting a
shortlisted gold; the observed rate on mint reopens is 170 match / 289
reopened = 59% (61 went `generic-class`), used below as the conversion.

| | gold on shortlist | expected placements |
|---|---|---|
| **stranded `none` (1,903)**, today | 3/19 of (a) ≈ 30 | already refused |
| retrieval only | 6/19 ≈ 75 (+45) | +25 |
| retrieval + ambassador lane | ~17/19 ≈ 215 (+185) | **+110** |
| **mint attestations not retrievable at feed (268)** | 62 → 235 (+173) | **+100**, ~196 people (32 of them stranded) |

People: the 19 (a) rows belong to 17 of the 124 people in the sample (14%),
so ≈ 75 of the 537 stranded people have at least one placeable mention; at
the reopen conversion ≈ **45 people gain their first P39**, plus the 32
stranded people reached through the mint items. The 95% interval on a 19/150
proportion is 8–19%, so read these as ±50%.

The other ~85% of the stranded bucket does not move with any retrieval
change: (b) is the mint queue's, (c) should stay unplaced.

**Risk of wrong placements.** Recall here is bought by re-ordering the fifteen (canon-first displaces
three of the 280 answers that were retrievable at feed time, and none on pos), so the model reads the same length of list, but with
plausible cross-language neighbours instead of lexical noise. What keeps that
safe is unchanged: the generic-class and body-not-seat rules, `settle`'s
closed set, and the prompt's "two equally good → none". What it adds is the
homonym case above, which the model can only refuse if it can see the
candidate's country — hence step 4.

## Recommended design

1. **A canonical English title per mention, as a second search channel.**
   - New module `peploop/titles.py` and prompt `peploop/prompts/title_en.md`
     (frozen, hashed, like every other prompt). `english_titles(mentions,
     state_qid)` batches 25 titles per request to `claude-haiku-4-5` and
     stores each answer.
   - Postgres cache table `title_en (state_qid, title, jurisdiction,
     prompt_hash, model, english, created_at)`, unique on the first four. The
     search reads the table and never calls the model, so `shortlist_hits`
     stays deterministic and offline-testable; a missing row means the
     lexical channel alone, logged, never an error.
   - `reconcile.shortlist_hits` becomes: canonical search (same
     `positions.search`, same signals, same pool), exact-name promotion,
     top-10; then the lexical ranking fills to 15. `retrievable` follows
     automatically, so mint's `feed` uses the same retrieval.
   - The model is **not** shown the English title. It reads the title as
     written, as today; the translation is a retrieval aid only, like
     `search_title`. So the reconcile prompt hash does not change.
2. **No embeddings now.** The best model-free channel (e5-base) reaches 90 @15
   to the canonical channel's 93, and on top of it any embedding adds 3 points
   at @15. The price is torch (a 1.4 GB venv), a 0.5–1.1 GB model (e5-small /
   e5-base; models pulled 3.8 GB into `~/.cache/huggingface` during this
   test), 10–41 minutes and 2–3.5 GB of RAM to embed the current table on 4 CPUs, and an index
   that has to be re-embedded on every `load-positions`. `pgvector` is not
   available on this server (`pg_available_extensions` has no `vector`), so
   the vectors would be a `bytea`/`real[]` column scanned in numpy — fine at
   1.3 ms per query, but another moving part. Revisit if a country appears
   where the canonical channel is weak (a script Haiku romanises badly) or if
   the per-mention LLM call becomes the bottleneck; e5-small is the one to
   try, since it matched e5-base as a fill.
3. **An outbound-mission discovery lane** in `positions.discover`: the state's
   own "ambassador of <state>" class(es) and their `P279` children. Tagged
   `diplomatic` by the existing `fill_diplomatic`; the `inbound-diplomatic`
   logic is untouched because these are scoped to the receiving state.
4. **Show the candidate's state on its line** (`country: …` from
   `country_qid`, or the jurisdiction's label), and one prompt sentence: a
   candidate of a different state is right only for a posting abroad or an
   international seat. This is a rendering *and* prompt change, so it re-asks
   on its own schedule (below).

**Ledger keying.** A verdict is keyed by (extraction, mention, prompt hash,
`RENDER_VERSION`, `reopened_for`); the shortlist is not in the key. Steps 1–3
change neither the prompt nor the rendering, so a plain `reconcile` would read
every old verdict back and re-ask nothing. Do **not** bump `RENDER_VERSION`
for a retrieval change — that re-asks every placed mention too. Instead
re-ask exactly the refusals whose shortlist gained a QID, under
`reopened_for = 'retrieval:2'` — the mechanism `feed` already uses, which
`propose.placements` reads as the newest row. Record the retrieval that built
a shortlist on the row (`resolution.retrieval TEXT`, e.g.
`canon10+lex:<title_en prompt hash[:8]>`), outside the key, so an audit can
tell the two apart. Step 4 does bump `RENDER_VERSION` and the prompt hash, and
is costed separately.

What the "Title expansion and era prior" measurements change here: nothing in
the keys. `title_en.md` stays as written (no "always name the state or place"
instruction), so its hash — and every cached translation — is not invalidated;
no qualifier is composed after the model, so `title_en` holds the model's
answer and nothing derived from it; no era signal is added, so the
`positions.WEIGHTS`/`TAGS` the reconcile prompt explains are unchanged and the
reconcile prompt hash and `RENDER_VERSION = 2` stay. Had a qualifier been
adopted, the place would have been the search side (`shortlist_hits`, like
`search_title`), never `title_en`'s stored value, and the era prior would have
been a `positions.WEIGHTS` term with a `TAGS` entry — a reconcile prompt-hash
change. Neither is needed.

## Implementation steps

Each is a checkpoint: stop and report after it.

1. **`title_en` cache and the translation pass.** `peploop/titles.py`, the
   prompt, the table in `schema.sql`, `cli title-en --country cc` (batched,
   resumable from the table). *Check:* a `check_titles.py` offline check pins
   the batching, the JSON parse (an answer missing an id is re-asked, an extra
   id ignored) and the cache key; a live run on Haiti reports tokens and cost
   and agrees with this plan's $0.13/1k titles within 2×.
2. **Retrieval.** `shortlist_hits` = canonical top-10 with exact-name
   promotion, lexical fill to 15; exact-name promotion as a function in
   `positions.py` beside `search`. No title qualifier and no era term: both
   were measured flat or negative (see "Title expansion and era prior").
   *Check:* `check_reconcile` still passes; a
   `scripts/` bench (port of `baseline.py`/`score.py`) reproduces pos ≥
   99 @15, hard ≥ 92 @15 and lexical-only behaviour when `title_en` is empty;
   `check_neutral` passes (no country token in the prompt or module).
3. **Re-ask refusals whose shortlist changed.** `cli reconcile --reask
   retrieval:2 --country cc`: for each mention whose newest verdict is not a
   match, rebuild the shortlist; if it offers a QID the stored shortlist did
   not, `resolve_mention(..., reopened_for='retrieval:2')`. Add
   `resolution.retrieval`. *Check:* dry-run counts per country (expect ~76%
   of `none` mentions to gain a candidate; 1,452 of the 1,903 stranded did); then a
   live run on one small country (bi or ht) and a hand-read of 50 new matches
   — target zero wrong placements, any homonym placement stops the rollout
   until step 5.
4. **Re-feed mint.** `mint-feed` re-asks `retrievable` for every attestation
   with `retrieved = false`. *Check:* the number newly retrievable matches this
   plan's 173 (of 268) within 10%.
5. **Candidate country on the line.** `Candidate.line` gains `country:`; the
   prompt gains one sentence and the `check_reconcile` pin for it;
   `RENDER_VERSION = 3`. *Check:* `check_reconcile`; the four Chía/Bello
   verdicts re-asked come back `wrong-office`.
6. **Outbound-mission discovery lane.** `positions.discover` lane `mission`;
   `load-positions --country by` then `position-signals --local-holders`.
   *Check:* the 27 missing Belarusian items load; the nine labA ambassador rows
   are on their shortlists; then step 3's re-ask for by.

## Rollout and cost

- **Translation**: 15,904 newest mentions across the 8 countries, 12,285
  unique (title, jurisdiction, state) ≈ **$1.60** at Haiku rates.
- **Re-ask after steps 2–3** (retrieval only, refusals whose shortlist
  changed): 8,771 newest refusals (8,381 of them `none`) across the 8
  countries, ~76% gaining a candidate ≈ 6,700 requests × $0.0088 (Sonnet 5 averages on this ledger:
  3,158 input, 4,130 cache-read, 171 output tokens) ≈ **$59**. Stranded people
  only: 1,452 × $0.0088 ≈ **$13**.
- **Mint re-feed**: ~170 reopens ≈ $1.50.
- **Step 5** re-asks every mention of a country when it next runs: 15,904 ≈
  **$140** for all 8. Run it per country as each is next touched rather than
  as a sweep, or only over placed mentions whose item's state differs from the
  asking state (hundreds, a few dollars) if the full re-ask is not wanted.
- Then `propose` → `policy` → `verify` → `apply` per country, as in
  `peploop/countries.md`.

## Open questions

- Whether to fold the English title into round one's extraction instead
  (`positions[].title_en`): free per mention, but an extraction prompt change
  re-extracts every person. Worth doing at the next extraction-prompt bump,
  after which `title_en` becomes the fallback for old extractions.
- Belarus's per-convocation local-council seats exist only in Russian
  ("депутат районного Совета депутатов 28 созыва"); no channel here finds
  them from a Belarusian title naming the district. A census/shape question
  for mint, not retrieval.
- (b) at 54% is the larger lever by far, and the mint queue's `skipped`
  status (3,344 candidates) is where it sits.
