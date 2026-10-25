---
description: Closing report of the AMLR workstreams (2026-10-23/25) — every dry-run send and creation proposal awaiting the user, in order, with the open policy calls each workstream left.
date: 2026-10-25
tags: [amlr, sends, mint, peptree, pepcorp, closing-report]
---

# AMLR workstreams: what waits for the user

Nothing below has gone to Wikidata. Each item is a dry run with its file or
command; creations are irreversible.

## Creations (`mint --submit`)

| # | what | count | tranches | where |
|---|---|---|---|---|
| C1 | heads of ≥50k units (WS3b, re-drafted under the term rules) | 777 | hu cz sk at hr lv si fi pt it gr 137 → de 142 → pl 266 (cities first) → fr 232 (after a post-2026-election holder spot check) | `mint --country <cc> --submit` |
| C2 | heads of EU bodies and EU-seated IOs (WS7) | 56 | Union 35 → IOs 21 | `mint --country eu --submit --id …` |

Not to submit: China's 112 guarded drafts predate the term rules (old
descriptions, aliases in foreign languages); a `mint --country cn` dry run first.

After C1/C2: `tree backlink --eu` again (new offices get the units' `P1313`),
and the holders' `P39` (see open calls).

## Statements

| # | what | lines | tranches | where |
|---|---|---|---|---|
| S1 | unit → head office back-links (WS3a) | 544 (505 `P1313`, 36 `P1001`, 3 `P17`) | de 321 → it dk pt bg 185 → 13 others 38; fr 40 held to its review | `pending-backlink.qs`, `tree send --lane backlink` |
| S2 | seats on bodies only the AMLR list admits (WS4) | 19 (14 `P169`, 5 `P5052`) | one | `corp send ro\|dk\|lt --qid …` |
| S3 | party governing bodies (WS5) | 701 | per country: `P488`+`P3975` (de 224, es 160, nl 15) → `P3320` roles (de 256, es 32, nl 14) | `corp send <cc> --qid` from `scratchpad/ws5/<cc>_qids.txt` |
| S4 | municipal companies, de (WS6) | ~296 | seats 57 bodies ~116 → marker+links 134 bodies ~180 | re-run `corp run de --no-ask` first (QLever outage hid the last fix); `scratchpad/ws6/send_t{1,2}_*.txt` |
| S5 | EU / IO boards (WS7) | 9 `P5052` | one, after C2 | `corp send eu` |

Run files from WS4–WS6 re-plan whole countries: every send is limited by
`--qid` to the workstream's bodies.

## Open calls for the user

1. Pending marker removals: with the municipal tier written, de's four
   `Q270791` removal proposals were withdrawn. Swap `Q270791` → `Q1780371`
   on municipal companies anyway (others' statements, per-removal approval)?
2. Settled 2026-10-25: the city-state rule (a city-state's company is
   regional) applies in every country.
3. Holders' `P39` after creation: no CLI seeds a person by QID (203 unit heads
   have one from `P6`); IO offices have no person lane (discovery and
   categorize would need the organisation set).
4. Settled 2026-10-25: EU scope labels en+fr+de, all three required.
5. Smaller: Q841760's vandalised English label; 161 units whose `P1313` names a
   generic class (removal proposals); Tipperary North/South lack `P576`;
   Munich's Kulturreferat (city departments are government: prompt + re-ask);
   362 unresolved named-body rows (ro, mt) for another `amlr expand` pass;
   3 unscoped IO offices for peptree (EUMC Chair, OIF, CPLP); OpenSanctions'
   crawlers need party and international lanes.

## Spend

WS2 $2.35, WS3b $24.48, terms $1.53, WS4 $3.74, WS5 $11.36, WS6 $7.43, WS7
$7.05: ~$58 at list price.
