# Task: positions at international organisations (FIFA → ICC → Interpol)

OpenSanctions loses most positions at international bodies. Confirmed
2026-08-05, two layers deep in zavod (see the approved plan in
`~/.claude/plans/i-want-to-think-nested-blanket.md`):

1. **Discovery** (`datasets/_wikidata/peps/crawler.py`) sweeps positions per
   rigour territory (P1001|P17) plus per-country occupation queries — IGO
   positions are invisible to both unless a holder happens to be a
   politician/diplomat/judge with P27.
2. **The country gate** (`zavod/shed/wikidata/position.py:207`) drops
   whatever does get discovered; even a reviewed `is_pep=True` DB row can't
   rescue a country-less position.

Live probes: UN Secretary-General (Q81066), NATO SG (Q167662) and Interpol
SG (Q111170012) are absent from `wd_peps`; FIFA president (Q22955080) is in
with `country=['ch','zz']` — the `ch` is P17 headquarters pollution, the
`zz` comes from the hand-maintained block in `wd_categories.yml:477-670`.

## Approach (decided with user, 2026-08-05)

Hybrid: a **curated org-QID registry in zavod** (`zavod/shed/wikidata/igo.py`,
org QID → country code + topics; positions linking to a registry org via
P2389/P361 bypass the gate with `country=zz`/`eu`/`un` only and enroll as
needs-review) **plus a Wikidata campaign adding the missing P2389/P361
org links** to position items. No new Wikidata class: membership would be
derivable (P2389 → org → org's P31), and OS coverage shouldn't depend on
our own tags surviving. Scope includes non-governmental international
bodies (FIFA, IOC, …) with per-org topic defaults.

## On-Wikidata modeling (what the census keys on)

Positions link to their body via **P2389** "organization directed by the
office" (FIFA pres, UN SG, NATO SG, World Bank pres) and/or **P361**
"part of". P17 on these items is junk where present (FIFA → Switzerland,
NATO SG → NATO-as-country). Some have no org link at all (Interpol SG:
bare `P31=position`) — the enrichment target.

Org-class closures for the census sweep (verified QIDs):
Q245065 intergovernmental organization, Q1262438 international court,
Q15925165 UN specialized agency, Q11422536 international sport governing
body, Q484652 international organization (broad + noisy: catches GAA,
Achaean League, trade unions, College of Cardinals — census tags which
class matched; the per-org human review is the filter).

## Method

1. `scripts/igo_positions.py` census, two channels:
   * **org-link channel** (WDQS): P39-used positions with P2389/P361 into
     the class closures above, holder counts, org + position metadata.
   * **label channel** (over `data/jurisdictions/bare_positions.json`):
     positions with *no* org link whose label tail names a known org —
     candidates for P2389 additions.
2. Render `data/igo/igo_plan.md`: registry seed table (org, classes,
   positions, holders, proposed country code + topics) sorted by impact,
   plus P2389-addition candidates split auto (label + description/enwiki
   agree) vs review. `.qs` is additive-only P2389 statements.
3. User reviews registry seed + runs `.qs`; zavod changes land separately
   (registry module, gate override, discovery sweep — see plan file).

## Status

- [x] problem verified in code + live data (probes above)
- [x] approach decided (hybrid; registry + enrichment; zz-only country;
      needs-review PEP default)
- [x] census run (2026-08-05, `scripts/igo_positions.py`): 142 active orgs /
      213 linked positions in the registry seed; 4-statement auto `.qs`
      (all "Secretary General of X" → org); 7 rows to review; matcher
      tightened after audit (state leak via "member state of the UN"
      classes, list items, " to " accreditation posts, deputy/assistant
      roles, first-vs-last " of " tail split)
- [x] registry seed reviewed by user (2026-08-05: IMF/World Bank → zz,
      WHO/UNESCO → un; strikes applied: friendship groups, College of
      Cardinals, trade unions, religious NGOs, EU delegations/COREPER,
      EP political groups, ancient leagues)
- [x] P2389 enrichment batch run in QuickStatements (2026-08-05, 4
      statements — confirmed live on Q111170012)
- [x] zavod (2026-08-05): `zavod/shed/wikidata/igo.py` (86-org registry),
      registry override + db_is_pep gate bypass + review-default in
      `position.py`, occupancy country-inference carve-out
      (gov.igo / zz / un), `query_igo_positions()` sweep in the wd_peps
      crawler; 4 new tests in `zavod/tests/shed/test_wikidata_position.py`,
      mypy --strict + ruff clean
- [x] local verification (wd_item_debug.py + live WDQS): UN SG → country
      `un` gov.igo; NATO SG → `zz` (no Belgium/NATO junk); FIFA / World
      Bank / Interpol SG enroll as undecided with correct zz/poi values;
      discovery sweep returns 144 candidates incl. all probes and PACE
- [x] PR opened: https://github.com/opensanctions/opensanctions/pull/5313
      (branch `pudo/wd-igo-positions`; includes review-round fixes:
      territory.is_country for occupancy inference, explicit
      `is_pep is False`, historical/ended claims soften to `continue`)
- [x] second-pass link hunt (2026-08-05, `scripts/igo_link_candidates.py`):
      hunts the full item universe (CirrusSearch `inlabel:` per registry-org
      name + P1001/P17-pointing-at-org + holder-employer corroboration +
      sub-org sweep), keyed on the igo.py registry read from the PR branch.
      458 in-use candidates → 4 auto rows (`igo_links2_p2389.qs` /
      `igo_links2_p361.qs`, one property per batch), 121 review rows in
      `igo_links2_plan.md` (mostly accreditation posts, correctly flagged
      DIPLOMATIC), sub-org registry leads (College of Commissioners: 42
      positions; NATO commands; Committee of Ministers of the CoE) and
      unregistered-org leads (Council of the EU Q8896 — has no P361→EU and
      isn't in the registry, so its presidency rows were demoted to review).
      Matcher tightened after audit: employer-only rows need ≥3 staff and
      ≥50% of holders (kills "full professor"/"director" corpus noise, 333
      rows); nested label tails keep only the most specific org; a longer
      unregistered org name in the label blocks auto.
- [x] all 121 review rows decided (2026-08-05): 4 parallel verification
      agents (opus, one chunk each, verdicts in `data/igo/verdicts2/`),
      merged by `scripts/render_igo_verdicts.py` → `igo_links2_decided.md`.
      Verdicts: 19 link, 10 registry leads, 67 diplomatic (sending-state
      posts, no org link), 24 reject, 1 unclear (FIFA referee). Notable:
      envoy/SRSG posts are UN offices despite mandate-area P17 (Yemen,
      Syria, Kosovo); Arab League's own outgoing ambassador is the org's
      post (reverse of the diplomatic pattern); generic "UN Special
      Rapporteur" → Q1065 while specific rapporteurships → HRC Q205650.
- [ ] user: run `igo_links2_p2389.qs` (2) + `igo_links2_p361.qs` (21) in
      QuickStatements (auto + verified rows, additive-only)
- [x] registry expanded (2026-08-05, PR #5313 merged that morning; expansion
      PR https://github.com/opensanctions/opensanctions/pull/5318, branch
      `pudo/wd-igo-expand`, 95 → 113 orgs): Council of the EU, College of
      Commissioners, EP Secretariat, EESC, EU delegations (`eu`); NATO
      organs incl. SHAPE/ACO (SACEUR, 21 holders); OSCE, AU Commission,
      EALA, CoE Committee of Ministers (`zz`); UN DESA + WFP (`un` — WFP
      has no position items on Wikidata yet, future-proofing); IOC Ethics
      Commission (poi). Left out: Peace Implementation Council (High Rep
      BiH already resolves via P1001 → `ba`). All lead QIDs verified
      against live items first — the WFP guess Q848633 turned out to be
      the International Chamber of Commerce; correct QID is Q204344.
- [ ] user: run the QS batches — `igo_links2_p2389.qs` (2) +
      `igo_links2_p361.qs` (21), and after PR #5318 review the third
      batch enabled by the expansion: `igo_links3_p2389.qs` (5) +
      `igo_links3_p361.qs` (4), see `igo_links3_plan.md`
- [ ] production re-crawl: review newly enrolled positions in the UI,
      confirm probes ship via wd_peps with no HQ countries
