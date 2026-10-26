---
description: Open peploop work as of 2026-10-12 — the audit rules Malaysia showed are missing, mint lanes not yet covered, a country tag on the shortlist, the consolidation still worth doing, and one office loader for both lanes.
date: 2026-10-11
tags: [peploop, backlog, mint, policy, reconcile, consolidation]
---

# peploop: what is next

The tool as it is: `peploop/design.md`. What was tried: `docs/history.md`.
Only §5 is started: `llm.py` holds the first part of the LLM-pass kernel.

## 1. The first live `mint --submit` — done

Congo (2026-10-12) created four offices through QS3 (59322, 59339, 59348), each
checked live, rows `created`, edits `landed`, mentions fed. Combined creation
batches failed whole, so creations now go out uncombined.

## 2. Rules for wrong open tenures

Malaysia's audit found about 9% of open `P39`s wrong and none among closed
ones. Three rules for `policy.py`, each with a case in `check_policy.py`:

- an open seat on a body dissolved after the article's revision (17 Malacca
  seats after the 2026-09-23 dissolution);
- ~~an open tenure read only from a wiki outside the country's languages and
  English~~ -- done, `minor_wiki_only/open` (Somalia, 2026-10-12);
- an open chamber seat whose new term is on record with too few starters to
  make the cohort (Somalia's Upper House: one 2022 senator against 2016-17
  seats);
- an open ambassadorship the same person's later posting ends, when the later
  post has no item to propose it on;
- an open tenure on a term item that has a successor.

Found by the Cypriot audits (2026-10-14), not yet rules:

- a closed legislative seat whose span crosses a general election, written
  as one statement where the chamber has one per term (a Cypriot MP's
  "May 2001 – 29 February 2008" spans the 2006 election);
- an infobox "MP until" equal to the day the person became a minister, read
  as the seat's end where ministers keep their seats (Northern Cyprus);
- a seed person that is a duplicate of another item already holding the
  tenures (same name and birth date, one item per wiki): skip, and report
  the pair for a merge.

Found by Malta's audit (2026-10-15), not yet rules:

- a tenure on a term item (its term behind `P2937`) must fall inside the
  term: a 2013-2017 seat went onto the 13th House (2017-2022);
- a scheduled end the article states ("set to retire in February 2026")
  that is already past closes the tenure: a Chief Justice was written open;
- `open_superseded/chamber` reads a year-precision start as its year's last
  day, so 2022 seats pass where day-precise ones of the same election skip;
  and a closed spell goes out while its continuation on the same chamber is
  skipped (a district move written as the seat's end);
- a post read from one article loses to another article's narrower title
  (fi "ambassador" against en/fr/et "Deputy High Commissioner").

Found by Zambia's audit (2026-10-16), not yet a rule:

- a cabinet seat open from before the head of state's latest re-election,
  where ministers vacate office when the President assumes it: the
  September 2026 cabinet re-formed every seat, but Hichilema's `P39` is one
  statement from 2021, so `open_superseded/government` cannot see the new
  term (four 2024 appointees taken back by hand). Needs the term's start
  from somewhere other than the head's `P39`, such as the election item.
- an open chamber seat taken up mid-term (a by-election or list
  replacement) escapes `open_superseded/chamber`, whose test is a measured
  term after the start: Namibia's 2022 and 2024 entrants to the 7th
  Assembly stayed open after the 8th's March 2025 cohort (two taken back by
  hand). A new term's cohort after the start should be enough.

## 3. Mint lanes not yet covered

- **Empty offices, "if well-justified"** (requirements, 2026-10-12). The user
  defined it on 2026-10-15: a source says every unit of the level has the
  office, and at least one sibling of the level has an attested holder. Build
  it as a rule in `mint.RULES` with its case in `check_mint`; Malta's six
  regional presidencies are the first test, and design.md's evidence bar
  changes with it.

- **Bilateral ambassadorships** are refused (`offices.bilateral`); every
  country has dozens of unplaced "ambassador of X to Y" mentions.
- **Deputy ministers** without a national class to shape them.
- **Subnational cabinet seats** are minted since Australia; Malaysia's 418
  `archetype/none` groups were never re-run.
- **`open_unattested` reads English only.** Other languages need their
  present-tense markers, measured, before it applies to them.

Each needs an archetype in `offices.py` with its shape measured first
(`docs/research/position_items.md` is the template), and a case in
`check_mint.py`.

## 3a. The Union's bodies and the organisations seated in it (`eu`)

Built 2026-10-25, dry run only: `census/eu.yml` lists 86 bodies' heads
(`per: bodies`), 56 guarded, nothing created. Left:

1. **Creation, with the user.** Two tranches by `mint --country eu --submit
   --id …`: the 35 Union bodies' heads, then the 21 organisations' (no
   `P17`, `P1001` the organisation). The holders' `P39` follow only once
   the person lane runs: no mention attests these offices.
2. **The three found but unscoped** (EU Military Committee chair, the
   Francophonie's and the CPLP's secretaries general): a peptree `P1001`
   or `P2389` repair, not a creation.
3. **Deputies and the person lane.** A seed file for `eu` (the Union's
   office-holder categories, the agencies' directors) would attest the
   deputies and feed the 56. Union offices fit the scope as it is; an
   organisation's offices do not: `load-positions` discovers by `P17`/
   `P1001` of the scope, and categorize cannot give a mention candidate an
   organisation as its polity. Either is a change to the discovery lanes
   and categorize's offered polities, to be decided before seeding.
4. **Residue:** 9 skipped for a French or German label their body lacks;
   3 for a title the verifier would shape as director; 13 bodies whose
   infobox names nobody current (acting heads at Europol, ECCC; none at
   EIT, CTBTO, EUMETSAT). The AMLR asset's Union rows (`amlr/eu.yml`) are
   not expanded to these bodies yet.
5. **Interim calls:** labels are written by hand from the body's own
   French and German names, never invented where it has none; the
   Commission's directorates-general and services, the Council's
   committees and rotating chairs are left out; an organisation is one
   whose `P159` lies in a member state, less four whose seat is plainly
   elsewhere (IOM, the Pacific Community, Intelsat, UNFICYP).

## 3b. Holders of the minted unit and body offices

`seed --holders` is built (2026-10-25); per tranche: `mint --submit` →
`tree backlink --eu` → `seed --holders` → `load-positions` once → the
stages → send with the user. A ~360-person tranche (the 777 offices whose
holder resolves) costs about $50 live, half batched. Before the first
tranche:

1. **A state is its current QIDs** in the person lane (done 2026-10-26).
   Still on the main QID: the mint lane (`mint.state_positions`,
   `Context.index`, `subdivisions`, `offices.found_from`/`live_lookup`,
   `siblings`, the scope checks) -- for nl, mint would miss existing `Q55`
   offices and take the Kingdom's constituent countries for its units --
   and reconcile's `_governs` (a render change, so it re-keys answers).
   rigour's bad alternates (Southern Netherlands and Crown Colony of Malta
   kept as current, Mecca, Bali, Navajo, Ichkeria, Santo Domingo) are for
   upstream and `eras.historical`.
2. **Generic `P39`s** no longer hide the specific office (done). Residue:
   propose attaches the first mention's verdict to a spell (Wiśniewski's
   medium English one over the high Polish one); rector-style classes
   scoped to a class (`P1001` "educational institution") still count as
   seats.
3. **Stale `P6`.** An undated `P6` often names a former mayor; mint's
   draft already prefers a differing infobox name. Count how many seeded
   holders' accepted tenures are closed after the first tranche.
4. **Holders already in another run** keep their old extraction; the
   office they now hold is reached only if it was mentioned and refused
   (the re-ask). Re-extracting them is a choice for the user.
5. **Unlinked names** (412 units, 37 bodies) are residue; IO heads need no
   discovery change once their office is created and loaded.

## 4. The candidate's country on the shortlist line

Homonym offices of other states (a Spanish "mayor of Chía" offered for
Colombia) reach the shortlist with nothing on the line saying whose they are.
Add the state to `Candidate.line` and bump `RENDER_VERSION` to 3. That re-keys
every reconcile answer, so re-ask only refusals and `wrong-office` verdicts,
not the whole ledger (a full re-ask is about $140 over eight countries).

## 5. Consolidation still worth doing

Do these when the files are open anyway; none changes behaviour.

- **The rest of the LLM-pass kernel.** `llm.py` holds the client, the prompt
  hash, the usage counts and the prices; each of the seven passes (six here, one in
  `tree/repair.py`) still carries its own request, parse and record, `Strict`
  is defined five times and `USAGE_KEYS` twice. An `llm_usage` view over the
  ledgers would let `report` show every pass's cost.
- **A check fixture and runner.** Five copies of the shadow-table helper, and
  peptree's eight checks carry their own `expect` beside peploop's seventeen;
  one `checks.py` fixture and a `check` command that runs every `check_*` of
  both lanes.
- **Pin every prompt's request hash.** Ledger keys hash the rendered request;
  only reconcile's is pinned, so a refactor that changes rendering by a byte
  silently re-asks a pass.

Not to do: one ledger table for every pass, keying by message hash (re-keys
about $390 of answers), a single `run` driver.

## 6. One office loader for both lanes

peploop (`positions.discover` → `position`) and peptree (`tree/load.py` →
`ptree_item`) each find a country's offices with their own queries, holder
counts and not-an-office lists, and they disagree. Of peploop's `position` rows
for a state, peptree's filter drops jp 410 of 2,977 (173 not an office, 81
occupation, 79 inbound ambassador, 62 body), my 290 of 710, by 110 of 646, and
about half for the small Caribbean runs. So reconcile can resolve a mention to
an item peptree has ruled out, an inbound ambassadorship among them.

One loader and one filter would fix that, with peptree's lanes as the richer
half: it knows predecessor states, realms and eras, which peploop's
`country_qid` does not. Share the country model (`tree/country.py`) with it, so
reconcile and `mint` see predecessors too. This changes which offices peploop
resolves against: measure the shortlist and proposal diff on two finished
countries before switching.

The two lanes also fold names differently: `positions.fold` transliterates to
ASCII, `tree/country.fold` strips diacritics (NFKD), and each has its own
`tokens`, so the same Cyrillic or Greek title compares differently in each.
Pick one with the loader, measured on the same diff, since it moves matches in
whichever lane changes.
