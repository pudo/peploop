---
description: Interim policy decisions made during the autonomous pepcorp EU + Switzerland dry run (nothing sent), each with examples, lines withheld and the alternative, to be synthesised into calls for the user before one big re-run.
date: 2026-10-17
tags: [pepcorp, policy, eu, switzerland, dry-run]
---

# pepcorp EU + CH: interim policy log

Dry run, nothing sent (`data/pepcorp/HOLD`). Every call below is interim and
moderately conservative: when in doubt, the class is not written. Countries:
A fr it es pt gr cy mt; B at ch be lu ie dk se fi; C pl cz sk hu ro bg hr si
ee lv lt.

Format per entry: question; countries and examples; interim call and where
it lives (spec / rule / prompt); lines withheld; the alternative.

## Calls for the user, ranked (synthesis, 2026-10-18)

Result of the dry run: 3,938 lines on 26 countries, ~$185, samples 18–20/20.
What each call decides, by how much it moves.

**A. What counts as evidence of state control (largest visible gaps)**

1. *Statutory bodies with no owner* (29, 39, 45): public broadcasters (ORF,
   SRG SSR, Czech TV/Radio, DR, SVT/SR, MRT), news agencies, independent
   authorities (CNIL, Arcep, AGCOM, MFSA …), central banks. Today nothing
   is written. Proposal: a body set up by statute whose leadership a state
   organ appoints is state at its level, no owner link; its council is its
   supervisory body. ~100–150 bodies, the most visible ones.
   **User, 2026-10-18: "should be typed appropriately".** Measured on 30 of
   them: public broadcaster `Q1126006` on 6 of 10 broadcasters (SRG SSR
   only "broadcaster", MRT "company", TG4 "business"); central bank
   `Q66344` on all 3; regulators split across national classes (Italian
   `Q3630770` ×4, French `Q2872764`/`Q18558685`, Spanish `Q104601620`,
   regulatory agency `Q1639780`, financial regulatory agency `Q105062392`)
   or untyped beyond organization / government agency / quango (CRE,
   HATVP, CNIL, Arcep, Fiskalrat, ComCom, ERA).
2. *An official list or a state-only legal form as proof* (33, 46): bodies
   on a holdings register (Luxembourg's 26, the Swiss EFV list, ÖBAG) or
   carrying a spec state-only form (Italian autonomous museums) whose
   articles never say who owns them. Proposal: the list (cited by `P854`)
   or the form proves control for public establishments; minority stakes
   still not. ~50–100 bodies.
3. *Unlinked people with an item* (16): ~4,900 seats skipped. Proposal: a
   unique human label match, verified by a cheap call against the item
   (employer, positions, dates), as in pepcorp_next §2. The biggest recall
   lever (est. +20–30 % seats).

**B. Modelling idioms**

4. *Owner = the state-as-legal-person item or the country?* (19): Skarb
   Państwa, État français, Greek State, Belgische Staat. Convention is
   mixed (fr 17:9 for the legal person, be 11:10, gr 22:13). Follow each
   country's majority, or always the polity.
5. *One-tier boards* (13): chair `P488`, members `P3320` (as the design
   says) or `P5052` as now, when the board oversees a separate CEO (ie, se,
   dk, fi, fr conseil d'administration). 30–100+ lines.
6. *Privatised enterprises* (25): remove the marker (as now, needs your
   approval) or keep it with `P582`.

**C. Scope edges (small; interim calls in brackets)**

7. Ministry units, police, armed forces, prisons, state schools, archives
   [excluded; armed forces now global] (6, 7, 28).
8. Public-university rectors [in], learned academies [in], commemorative
   committees [in], internal units [in] (50, 48, 32, 51).
9. Ex-officio chairs [in, undated], seats from before state control [in],
   undated infobox seats [in; need a refresh cadence] (18, 17, 27).
10. A minister (office) named as owner → its ministry as `P749` [not
    written] (26).
11. Greenland and Faroe [out of dk; own gl/fo specs later] (43).

**D. Fixes for the re-run that need no call** (prompt or rules, done before
re-asking): members of a collegial body filed as executive (24); a
government's own department or head's office is kind `government` (47); a
building's owner is not the body's owner (52); ownership by a state company
or an infobox parent-company field is ownership in words (37); a marker
whose only quote is a share sentence is refused (41). Settle each country's
spec `actors` before asking (49).

## Decisions

1. **Council institutions** (from the Dutch sample). A body that is itself a
   council (electoral council, council of state, regulatory commission):
   only its chair is written, as head; members left out. Prompt
   (`decide.md`). Alternative: members as `P3320`/collegial-body positions
   via peploop.
2. **Intergovernmental organisations as state actors.** Geneva IOs carry
   `P17` CH and became government actors. Interim: `Q245065` in spec
   `not_government` (ch), then moved to the global `NOT_GOVERNMENT` in
   `actors.py` (an IGO is never one state's). Rule change, no re-ask.
3. **Agencies via a legal form** (se: 332 bodies via "Swedish government
   agency"). Interim: in scope as institutions (`P1037`, `P749` to the
   ministry), consistent with the earlier user call that pepcorp writes
   `P1037` for agencies. Lines: most of Sweden's.
4. **Broadcast channels/stations** (be, ch, dk). Interim: individual radio and
   TV channels excluded in specs; the broadcaster kept. Alternative: none
   expected (channels have no leadership of their own).
5. **Holdings from official lists** (ch EFV list of 22 federal units; lu, be,
   se, dk, fi to come). Interim: allowed, spec-only, verified QIDs; the
   major SOEs missing from all lanes (CFL, Luxair, SES, skeyes, SFPI, LKAB,
   SVT, SJ, Senaatti) show that holdings lists are needed wherever Wikidata
   lacks links.
6. **Ministry units, police, armed forces** (it dipartimenti/DG, es DG /
   secretarías de estado / subsecretarías, fr divisions and joint military
   services, cy/pt police). Interim: excluded in specs; their heads are
   peploop's positions (as de's Abteilung). Alternative: institutions with
   `P1037` heads. Costs: es ~210 bodies, it ~40. AESIA (es) lost because it
   is typed secretaría general.
7. **Prisons, state schools, archives, nature parks** (cz, hu, ro, ee, bg,
   lv, pt). Interim: excluded; not essential institutions whose leadership
   is PEP. Alternative: keep prisons (heads are senior civil servants).
8. **State stand-ins** (pl Skarb Państwa, hu Hungarian State, ro SGG with a
   wrong `P1001`). Interim: new spec key `actors` (state / government).
   Rule-side; alternative is fixing the items on Wikidata (SGG's `P1001`).
9. **Broadcasters typed as stations** (fr Arte France, es EiTB, Telemadrid,
   TVG; pl TVP, bg BNR). Interim: station classes not excluded there; the
   prompt's kind:other drops channels. Alternative: per-item exclusions.
10. **Municipalities as first-level subdivisions** (si, lv, lt). Interim:
    their companies count as municipal and are not written (consistent
    with national + regional). Alternative: a country tier override.
12. **Commission with its own secretariat** (ch Federal Gaming Board; ElCom,
    ComCom, WEKO likely). The model wrote members as `P5052` because the
    commission oversees a secretariat. Interim: council rule (chair only, as
    head), prompt wording tightened. Alternative: members as supervisory
    seats when a separate executive exists. ~10–20 bodies per country.
13. **One-tier boards with a separate CEO** (ie Irish National Stud, IDA,
    RTÉ; se Akademiska Hus). Classified supervisory: chair `P5052` +
    `Q15818143`, members `P5052`. The design's table says a one-tier chair
    is `P488` and members `P3320`. Interim: as is (consistent, a PEP seat
    either way). Alternative: prompt line making any board of directors in a
    one-tier company law `board`; affects every ie/se/dk/fi/lu (and likely
    fr conseil d'administration) chair and member, 30–60+ lines.
14. **Future-dated seats** (be RTBF head from 2026-11-01). Rule fix, not a
    policy call: start or end after today, at the date's precision, is held.
15. **Holder title vs infobox field** (lu FNR, Fonds culturel national: a
    board president under "Generaldirekter"). Prompt: the person's own title
    decides the role. Not a policy call.
16. **Unlinked people with an item** (all countries; it 20 vs 7 written, es
    32 vs 6, gr and mt 0 seats written). Interim: not resolved (pepcorp
    writes only linked people). Alternative: a unique-label fallback
    verified against the item (employer, position, country), as in
    pepcorp_next §2. The biggest recall lever for the re-run.
17. **Seats from before state control** (fr Bull, state-owned since
    2026-03-31: Breton and Barnabé written from the Atos era). Interim:
    accept (true on Wikidata). Alternative: a control start date in the
    answer, and seats ended before it skipped.
18. **Ex-officio chairs** (es: ministers and secretaries general chairing
    agency boards, undated). Interim: accept (true; PEPs anyway).
    Alternative: skip seats held by virtue of another office, or require a
    start date for them.
19. **State-as-legal-person items as `P127` target** (gr Greek State
    Q56692361: 22 items vs 13 using Q41; pl Skarb Państwa ~72 items; be
    Belgische Staat: 7 lines vs 1 to Q31, live items 11 vs 10, no clear
    convention; fr État français: 17 vs 9 organisations, 21 lines vs 7;
    se Svenska staten). Interim: follow the local convention. Alternative: rewrite
    every `P127` to a spec state actor into the polity, as for a national
    government (34). A modelling call for the user.
20. **Holdings compiled from knowledge** (mt, cy: from the model's knowledge
    and an enwiki category; QIDs checked, not the official pages).
    Interim: accepted; the control gate still needs an article quote.
21. **Municipal correction where municipalities are subdivisions** (si, lv,
    lt: Latvian municipal hospitals). The correction is skipped when the
    resolved owner is a subdivision (meant for city-states), so whether a
    municipal company is corrected depends on whether its owner resolved.
    Interim: accept (either a correct correction or none). Alternative:
    limit the guard to city-states.
22. **Stakes reported without control wording** (si: 16 of 30 unclear; SDH
    stakes in Telekom, Triglav). Interim: unwritten, per "words, not
    shares". Alternative: a holdings list from SDH's own portfolio as the
    proof of control.
23. **Fixed terms running past today** (lt FNTT head 2022–2027). Rule fix:
    written as held, start only, no future end.
24. **Collegial bodies filed as executive** (at Volksanwaltschaft: 5
    members as `P3320` + executive board member). The council rule's
    wording speaks of supervisory seats, so members filed under
    `executive` slip through. Interim: accepted for the dry run (the
    members are PEPs either way; the role is wrong). Re-run: prompt "members
    of a collegial body that is the institution are left out, whatever body
    they would be filed in".
25. **Privatised enterprises: remove the marker or end it?** (pl Mikrostyk,
    Biazet, TOPSIL: one item covers the former state enterprise and today's
    private company). Interim: removal proposed, as designed (waits for
    approval anyway). Alternative: keep `Q270791` with `P582` at the
    privatisation date, which keeps the history and is how OpenSanctions
    could drop it as past.
26. **Owner named as the competent minister** (pl "minister właściwy do
    spraw X": 19 of 66 no_controller). Interim: unwritten (an office, not
    linked). Alternative: map the minister's portfolio to its ministry as
    `P749`, a prompt and resolution change.
27. **Undated infobox seats** (pl: all 10 `P5052`, 10 heads undated).
    Interim: written when the article says current (existing user call).
    Noted because they go stale; a refresh cadence is the remedy.
28. **Armed forces as a body** (ch Swiss Armed Forces: `P1037` for each
    chief; pl, cy, hu excluded them already). Interim: excluded in every
    spec where it appears (`Q772547`), heads being peploop's positions.
    Alternative: keep (true data, adds the seat on the body); or make it a
    global exclusion beside military unit.
29. **Statutory public-law bodies with no owner** (cz Czech TV, Czech
    Radio, ČTK: control unclear/none, nothing written; likely sk STVR, si
    RTV, hr HRT, lt LRT, and agencies set up by statute). The user named
    broadcasters' leadership as PEP. Interim: unwritten. Re-run proposal
    (prompt): a body established by statute whose leadership or
    supervisory body a state organ (parliament, government) appoints is
    `state` at its level with no owner; seats written, no links; its
    council is its supervisory body. Few bodies, but the most visible.
    HIGH PRIORITY for the re-run.
30. **Councils as their own items** (cz broadcasting councils, government
    advisory councils: members written as `P5052` on the council item, an
    advisory council's chair as head). Interim: excluded in the cz spec
    (media council, government council, advisory board classes).
    Alternative: attach a broadcaster's council to the broadcaster (with
    29).
31. **Thin countries without agency links** (sk: 39 kept, agencies carry no
    `P749`, no category or form; only holdings reach them). Interim: as is.
    Alternative: an official list of central state bodies per thin country
    as holdings, or a peptree-style pass adding `P749` to agencies.
32. **Minor statutory committees** (hu National Memorial and Piety
    Committee, typed government agency: its chairs written as head, per the
    council rule). Interim: written. Question: is a commemorative or
    honorary committee's chair a PEP? Alternative: a prompt line leaving
    out committees without executive or regulatory powers.
33. **Official holdings lists as control evidence** (lu: 26 bodies
    unclear, most on the Trésorerie's participations register while their
    articles don't say who owns them — Théâtre National, Université,
    Luxinnovation, CHEM, Creos, Mudam; also ch EFV list, at ÖBAG, sk). The
    articles are today the only evidence. Interim: unwritten. Alternative:
    a holdings entry counts as proof of control for the link to its holder
    (reference: the list's URL, `P854`), at least for public
    establishments; minority stakes listed there (SES, Bourse) still not.
    HIGH PRIORITY with 29: the two together decide the visible gaps.
34. **"Owner: Government of X"** (ie EirGrid, An Post fell to no_state_owner).
    Rule fix: a national government as owner is written as the state
    polity; a regional government counts as state control without a link.
35. **Rigour alternates that are not the state** (ie: Irish Republic
    1919–22, now dropped via "historical unrecognized state"; the island of
    Ireland Q22890 stays a current QID, 0 lines). Upstream: rigour.
36. **Hospitals managed by a non-state group** (ie Saolta-managed
    hospitals: no_state_owner). Interim: unwritten. Alternative: HSE or the
    hospital group as a state body via spec `actors`.
37. **Ownership by a state company is ownership in words** (ee Enefit
    Power: "all shares belong to Eesti Energia" came back unclear; hu MAVIR:
    "Anyavállalata: MVM Zrt." came back unclear; ro, sk subsidiaries
    similar). Re-run prompt: an infobox parent-company or owner field names
    the owner in words, as a sentence would. Recall, not a policy call.
38. **Institutions under an office or the polity** (fr: CNIL, CNRS,
    CNOUS, France Travail, SGG named under "the Prime Minister" / "the
    Minister of X"; ARCEP, FranceAgriMer under France). Rule fix: the
    no_state_owner gate applies to enterprises only; such institutions keep
    their seats, no link. Re-run question: map a minister (office) to the
    ministry as `P749` (with 26).
39. **French independent authorities** (CNIL, Arcep, CRE, HAS, HATVP, CADA,
    AFLD, ANJ, CNCTR, CGLPL …; académies; CNAF/UNCAM): no owner by design.
    Part of 29.
40. **Stale removal proposals** (lv: pilot proposals the full run no longer
    made stayed queued). Fix: a run withdraws its country's undecided
    pepcorp correction proposals it no longer produces.
41. **Share figure read as control despite the prompt** (lv Conexus Baltic
    Grid: marker from "largest shareholders … AST (68,46 %)"). One case;
    a check that refuses a marker whose only quote is a share sentence is a
    possible rule for the re-run.
42. **Ministry-held shares refused by the link check** (it CDP, Invitalia,
    Consap, Difesa Servizi: the rules write the state, the quote names the
    ministry). Fix: the check is told the named ministry; a ministry's
    holding is the state's. Not a policy call.
43. **Greenland and Faroe** (dk: Air Greenland, Royal Greenland, KNI,
    Tusass … "100 % owned by Grønlands Selvstyre"). Interim: out of
    Denmark; OpenSanctions treats GL and FO as their own territories, so
    they belong to future gl/fo specs.
44. **Ministries modelled only via `P279` or deprecated `P31`** (dk: ~30
    styrelser lost their `P749`). Interim: dk spec `actors` lists 11
    ministries. Alternative: fix the ministry items on Wikidata (a peptree
    job).
45. **Swedish broadcasters under a foundation** (SVT, SR, UR owned by
    Förvaltningsstiftelsen, not in any lane). Interim: added as holdings;
    part of 29.
46. **A state-only legal form as control evidence** (it: Brera,
    Capodimonte, MANN, Gallerie Estensi typed "istituto museale ad autonomia
    speciale" come back unclear: their articles never say "owned by the
    ministry"; likely fr EPA/EPIC, es). Interim: unwritten. Alternative: a
    body whose own `P31`/`P1454` is one of the spec's state-only forms is
    state at the national tier; seats written, the parent link still needs
    a quote. Pairs with 33 (lists as evidence): both put Wikidata's or an
    official list's classification in place of article wording.
47. **A head of government's office as a body** (it Presidency of the
    Council of Ministers: its secretary written as head; de's Staatskanzlei
    excluded by class; pt Madeira's Secretarias Regionais, typed only
    government agency: their regional ministers written as heads, 2 errors
    in the sample). Interim: written. Re-run: the decide prompt asks
    whether the body is a (regional) government's ministry or department,
    or its head's office, and if so returns kind `government`. Not a
    policy call, a recall/precision fix.
48. **Learned academies** (fr Académie des inscriptions: its rotating
    annual president written as head; "personne morale de droit public").
    Interim: written. Alternative: academies are not state control
    (kind other), or only their permanent secretary.
49. **Cost note: actor changes re-key every request.** Adding a state actor
    changes the candidate list shown in each message, so every body of the
    country is asked again (fr: $40.59 for the re-run on top of $17.63).
    For the re-run, settle spec `actors` before asking.
50. **Public universities** (es Universitat de les Illes Balears: rector
    as head; fr leaves universities out of its forms). Interim: accept
    (one case). Question: are rectors of public universities in scope?
    Alternative: exclude university (`Q3918`) globally.
51. **Internal units of a state body** (es Observatorio de Igualdad de RTVE;
    Instituto Hidrográfico under the Navy staff). Interim: accept (true,
    low value). Alternative: kind `other` for units without legal
    personality.
52. **Owner in the infobox vs the body that runs it** (es Dalí
    Theatre-Museum: "Propietario: Gobierno de España", run by the Dalí
    Foundation; Trubia arms factory, probably operated privately since
    2001). Interim: as written (2 errors). Alternative: prompt line — a
    building's owner is not the owner of the body housed in it.
11. **Anchor-text name resolution** (C's inflected-language finding: 7 of
    10 unresolved controllers in the Polish pilot). Implemented, not a
    policy call; noted because it also lifts person linking everywhere.
