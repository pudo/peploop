# Institution classes

The institutions a state's politically exposed people sit in, as ~35 classes:
what a country is made of, beyond its cabinet. Two things read them.
The `census` section of `peploop/countries/<cc>.yml` lists a country's offices by these classes, so the mint stage
can propose the offices nobody's article named; and mint categorize assigns
every candidate office one of them (`mint.INSTITUTION_CLASSES` is pinned to
the headings below by `check_mint_queue`).

Each class says what it covers, where its holders are usually listed, the
shape its office item takes, and the failure mode that usually hides it — so
a country run asks about courts, central banks and state companies, not only
ministries.

---

## executive

### `executive.head_of_state`
President, monarch, supreme leader. Usually one item, well covered, near-100%
dated. **Roster:** a dedicated list article, both wikis. **Shape:** one item, or a
succession where the polity changed. **Failure mode:** not yield — this is the
backtest's calibration set, and its value is telling you whether your date parser
works before you trust it anywhere else. Score it separately, never as part of a
lane average (Iran's spine was 100% on four items and 26% on a fifth).

### `executive.head_of_government`
Prime minister, chief minister. Often abolished or dormant — Iran's PM ended in
1989 — which makes it a *historic* office with a live item. **Failure mode:**
`modern_from` set after the office ended silently sends every row through the
precedent test.

### `executive.deputy_leadership`
Vice presidents, deputy PMs, first deputies. **Failure mode:** the generic
vice-presidency item and the *first* vice-presidency share an English label and
are different items — Iran's `Q2660216` and `Q40097798` differ only in the fa
label (`معاون اول`). Never choose a target by English label here.

### `executive.cabinet`
The portfolio ministries. Usually the largest executive lane and often a **bucket**
— one office routed by an office-cell stem. **Roster:** a per-ministry list
article where the wiki has them (Iran: 26 of 27), otherwise the per-cabinet
articles (Jordan's 98, Iraq's 82). **Failure mode:** a fused article-preposition
defeats a pattern written from titles (Jordan used 630 spellings of ~50
portfolios); dump the whole distinct office-cell tally with what each stem routes
to *before* running anything.

### `executive.deputy_ministers`
Rarely has items. **Failure mode:** deputies sit in a table on the minister's own
page and parse as ministers — Iran's interior page leads with ten of them.
Heading-filter the page rather than trusting its first table.

### `executive.leader_office`
Chief of staff, head of the presidential/leader's office, presidential advisors.
**Failure mode:** advisor posts are a large undifferentiated bucket that overlaps
the parastatal family; route them explicitly or they swallow the cabinet lane.

## legislature

### `legislature.lower_membership`
**The highest-volume shape there is.** Kuwait's four term rolls were the largest
contributor to the biggest run this workbench has done; Iran's Majlis shipped 388
statements at 99% date agreement. **Roster:** one roll per term, dated in the
*page title* rather than per row — the `RosterSource.term` case. **Shape:** one
membership item, or per-convocation items reached through `P2937`.
**Failure modes, three of them, all expensive:**
* The `already holds P39` gate is per (person, target), **not per term**. A member
  who served twice is dropped from their second term silently. Iran: 423 people.
* Membership may be modelled `P2937` + `P768` rather than with dates. Measure the
  convention before emitting; then emit dates *as well*, because
  `zavod/shed/wikidata/position.py` reads P580/P582/P768 and never P2937.
* `P768` needs the *constituency* item, not the city. Gate on the linked item's
  `P31`, never on the column heading.

### `legislature.upper_membership`
Senate, consultative council, federal council. Often appointed rather than
elected, which makes it a PEP lane of its own.

### `legislature.leadership`
Speaker, deputy speakers, committee chairs. Small, clean, usually well dated.

### `legislature.historic_chambers`
A pre-constitutional or pre-revolutionary chamber is a **different institution**,
not an early term of the current one. **Failure mode:** routing its rows onto the
modern item. It needs its own item, which no rule can invent — `era.distinct`
skips the rows and the ledger records a creation list.

## oversight

### `oversight.constitutional_body`
Guardian Council, constitutional court, council of state.

### `oversight.state_councils`
Expediency councils, assemblies of experts, supreme security councils.
**Failure mode:** membership may be **ex officio** — the seat *is* another office,
and its dates are that office's dates. Iran's SNSC heads the column literally
"Ex officio member". There is no member item and there should not be one; close
the class `absent` with the evidence, do not invent a lane.

### `oversight.audit_anticorruption`
Audit court, inspection organisation, ombudsman. Usually item-less.

### `oversight.electoral_commission`
Almost never has items. Expect `no-source` or a creation list.

## judiciary

### `judiciary.apex`
Chief justice, supreme court president. Usually exists and is well dated.

### `judiciary.prosecution`
Prosecutor-general, attorney-general.

### `judiciary.specialised`
Revolutionary, clerical, administrative and military courts; the courts of
appeal. **Failure mode:** the tempting one. A category of named judges will pass
every mechanical guard test and still be wrong to mint — Iran's
17 Revolutionary Court judges cleared the duplicate search, the holder floor and
the body-label check, but **no source dates any appointment** and the only
attested shape is a *branch* presidency, not a generic judgeship. A guard
returning CLEAR is not a reason to create.

## economic

### `economic.central_bank`
Governor, deputy governors. Small, clean, always worth doing.

### `economic.sovereign_wealth`
**Creation-first by definition: the offices rarely exist yet.**
Wikidata's dominant convention is a generic role item plus `P108 <org>`, which the
OpenSanctions PEP build cannot see — it reads P39 and drops positions with no
country. Dedicated "Chairman of X" items are the only path that works and there
are ~20 on all of Wikidata. **Census it before committing a lane:** count P39,
P108, P463 and `pq:P642` on the org items. If the answer is zeros, the class is
creation-first and its ledger row cannot close on a byproduct list.

### `economic.soe_leadership`
National oil, airline, ports, telecom, rail. Same shape and same trap as SWFs.
**Failure mode:** the "employees" a P108 census turns up may be presenters and
engineers rather than executives — Iran's IRIB returned sports commentators.
Draw the boundary at *apex headship* and say so.

### `economic.regulators`
Securities, competition, financial intelligence unit.

## security

### `security.defence_command`
Chief of the general staff, service commanders. **Failure mode:** the rank is
often a *wikilink* leading the name cell, and the first-anchor rule then resolves
six different commanders to "major general". Decide anchor selection per page.

### `security.paramilitary`
Revolutionary guards, national guard, gendarmerie, basij. Frequently the real
military power and frequently better documented than the regular army.
**Failure mode:** commanders hold several of these at once by design — Iran's
Shamkhani commanded two navies simultaneously — so `concurrency_ignore` must be
measured, not assumed, or `interim_of` stamps `P2868` on real appointments.

### `security.intelligence`
Ministry or agency of intelligence, counter-intelligence, protection
organisations.

### `security.police`
Law-enforcement command, interior security forces.

## sub-national

### `subnational.executive`
Governors, walis, prefects. **Usually the largest creation-first lane in the
country**, and the one most often deferred: Iran had 903 dated roster rows against
**four** position items. **Generator:** the country's `P150` (first-level only).
**Shape:** measure `P1001` before minting — the Iranian convention is to scope to
the polity governed, and worldwide 172 of 185 `P279=Q132050` items with a `P1001`
do the same. **Failure mode:** minting to a neighbouring country's archetype makes
the new items siblings of nothing; if two countries both need the same archetype
field overridden, that is a missing archetype in `offices.py`, not two workarounds.

### `subnational.municipal`
Mayors of the capital and provincial capitals. **Generator:** `P36`, not `P150` —
`P150` is the wrong granularity for municipal offices.

### `subnational.assemblies`
Provincial and city councils. **Failure mode:** frequently undated and
weakly linked; close it `no-source` with the measurement rather than shipping a
lane of `no_dates` skips.

## diplomatic

### `diplomatic.outbound`
The country's ambassadors abroad. **Shape, and this one is counter-intuitive:**
`P17` on an outbound ambassadorship is the **receiving** state — measured 74/77 in
Iran and 262/264 in Qatar — and the sender sits in `P137`, which `zavod` does not
read (opensanctions/opensanctions#5475). **Do not "repair" these items toward the
sending country.** They are already visible, filed under the receiver, and adding
the sender's `P17` is a large batch of wrong statements in the lane that looks
safest. **Failure mode:** the rosters are bullets, rarely dated (Iran: 244 of 765
rows) and rarely cited (11%), so identity rests on the wikilink alone.

### `diplomatic.multilateral`
Permanent representatives to the UN, OPEC, regional bodies. Leave the receiver
bare where it is an organisation rather than a state.

## hybrid power

### `hybrid.ruling_family`
Where power is dynastic the office lane reaches only the fraction that held
office — 81 of 411 for the House of Saud. **Shape:** `P22`/`P25`/`P40` from a genealogy
article, plus `P53` from a hereditary office; peploop has no kinship lane.
**Failure mode:** take a patronymic chain from the *item's* full name, never from
the article's printed short form.

### `hybrid.religious_hierarchy`
Where clerical office is state power: Friday prayer leaders, the leader's
provincial representatives, endowment authorities. **Failure mode:** two lanes
that look distinct may be one office — Iran's Friday-prayer lists *redirect* to
the representative lists. Check redirects before scoping two rows.

### `hybrid.parastatal_foundations`
Bonyads, awqaf, relief committees, veterans' foundations. **The classifier test
does not settle these** — "is it bound to one jurisdiction" answers yes for all of
them. The axis that cuts is *does an appointment instrument from a state authority
fill it*: a constitutional article, a presidential warrant, a decree.
**Failure mode:** dating in **lunar** Hijri where the rest of the country uses
solar (Astan Quds), which no range test can detect — read the calendar marker.

### `hybrid.state_media`
State broadcaster and news agency headships. Often a genuine constitutional
appointment.

## political

### `political.parties`
Party and front leaderships. **Failure mode:** usually not a P39 lane at all —
the convention is `P488` (chairperson) on the *party* item. Iran had 99 leaders
across 10 tables with zero dates anywhere and exactly two leadership position
items. Close it with the measurement and route the byproduct to `P488`.

Where the party rules, its national organs are state power and three different
things, which take three different shapes:

* **Party membership** is `P102` on the person. Never an office.
* **Membership of a large organ** — a central committee, its alternates — is
  `P463` on the *body*, by a wide margin: the Soviet Central Committee has 933
  distinct holders recorded that way against 2 on a membership-seat item, and
  seven of ten central-committee "member" items carry no `P279` at all
  (`docs/research/position_items.md` §10a). Don't mint a seat for it.
* **A seat in a standing politburo or presidium, a secretariat seat, and the
  national party offices** (general, first and second secretary) are offices:
  `P39` onto an item. The Chinese Politburo and its Standing Committee hold
  75 and 62 holders on seat items against 4 and 5 by `P463`; the Soviet
  Politburo is split, 89 on the seat against 106 on the body. Their parents are
  measured in §10a and §10c (`Q115136557` politburo member, `Q836971` party
  secretary). **Failure mode:** these organs are barely modelled — no
  politburo-seat item exists for Vietnam, Laos or Cuba, and the one national
  second secretaryship on Wikidata is a Soviet republic's — so this class is
  creation-first, and the first sibling found is as likely a defect as a
  convention.

---

## Using this file

* **A census names every class the country has**, including the awkward ones;
  a class the country lacks is simply absent from it.
* **Add what a run teaches here**: when a class hides in a new way, write the
  failure mode down so the next country inherits it.
* **The item shape is measured, not declared**: `docs/research/position_items.md`
  says which `P279` names a class's kind and how `P17` and `P1001` divide
  between the state and the polity governed.
