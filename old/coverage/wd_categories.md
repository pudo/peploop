# `wd_categories.yml` — the position targets OpenSanctions names by QID

The ledger for the 209 QIDs `datasets/_wikidata/categories/wd_categories.yml`
carries in its `position:` blocks. Committed here because `data/` is gitignored,
so the run's own output cannot be the record.

Those blocks are a **workaround**: each one hand-asserts a name, a country and a
topic set beside a QID, and `crawler.py:174` builds the position from the yml
without consulting `categorise()` at all. The question this ledger answers is
whether the *items* could carry that weight instead — i.e. whether a spec's
`position:` block could be deleted and `wd_peps` left to emit the office.

**Headline: no, and not for reasons enrichment can fix.** Of the 209 targets,
**80 are positions `wd_peps` would emit today**. The other 129 are held back by
**OpenSanctions' own position policy in 127 cases** and by a Wikidata modelling problem in
**2**. Enriching Wikidata cannot retire these queries; changing
`SUB_TYPES` could.

Measured 2026-08-23 by `scripts/audit_os_positions.py`, replaying
`zavod/shed/wikidata/position.py`'s gates in their own order. **Rank-correct**:
the closure skips deprecated claims because nomenklatura's `Item.claims` does
(`model.py:152-160`), which `wd/shape.py` does not — see the caveat at the end.

| what `wd_peps` does | items | whose policy |
|---|---:|---|
| emits the position | 80 | — |
| enters the review UI undecided (IGO registry, `is_pep=None`) | 23 | OpenSanctions |
| dropped: closure confers no `role.pep` | 104 | OpenSanctions |
| dropped: closure hits `EXCLUDE_TYPES` | 2 | Wikidata |

## The 104 blocked on `SUB_TYPES`

Each names its kind of office correctly; the class simply confers no `role.pep`.
Not a defect and never a retype — the classes responsible:

| class | items | in `SUB_TYPES`? |
|---|---:|---|
| `Q4175034` | 79 | confers gov.legislative |
| `Q5230427` | 12 | **absent** |
| `Q42178` | 5 | **absent** |
| `Q1758037` | 3 | **absent** |
| `Q486839` | 1 | confers gov.legislative, role.pep |
| `Q8191099` | 1 | **absent** |
| `Q994779` | 1 | **absent** |
| `Q11488158` | 1 | **absent** |

`Q4175034` legislator alone is 79 of them: every Russian regional duma seat.

## The 2 blocked on Wikidata — and it is one inherited claim each

`position.py:159-164` drops an item whose closure hits `EXCLUDE_TYPES` with
nothing in `ALLOW_TYPES` to rescue it. That check runs **before** the country
gate and **before** the IGO registry, so neither a `P17` nor a `P2389` can save
these; no statement on the item itself is wrong.

| item | path to the excluded class |
|---|---|
| `Q1296423` White House Counsel | → `Q2994387` adviser → `Q15978655` consultant → `Q3320743` title of honor |
| `Q7250572` Prosecutor of the ICC | → `Q600751` prosecutor → `Q112684029` government attorney → `Q40348` lawyer → `Q189533` academic degree → `Q618779` award |

Two wrong claims on shared ontology nodes, both at normal rank:

- `Q15978655` **consultant** `P31 = Q3320743` title of honor. A consultant is a
  profession — the item also declares `Q28640` profession and `Q4164871` position.
- `Q40348` **lawyer** `P31 = Q189533` academic degree. A lawyer is a profession; a
  Juris Doctor is a degree.

`Q189533` academic degree `P279 = Q618779` award is *defensible* and should stay,
which is why removing the consultant claim alone fixes only the White House
Counsel — verified by simulation, not assumed.

`Q216353` title `P279 = Q618779` award is **deprecated**, so zavod never
traverses it. It is the edge that makes this look like a title-of-honor problem
and it is not one.

### The structural half, which is the one worth fixing

`EXCLUDE_TYPES` is tested against the whole 6-hop closure. `wd/shape.py`'s
mirror-image test refuses to do that, in its own words: *"the closure cannot
answer it: within six hops `Q28640` profession reaches `Q4164871` position"* — so
`NOT_AN_OFFICE` reads **declared** types only. `EXCLUDE_TYPES` has the same flaw
and no such guard. **36,142 in-use position items** sit under adviser/consultant
with no `ALLOW_TYPES` rescue, one wrong upstream claim from vanishing silently.
Fixing the two claims above does not change that; testing declared types would.

## Caveats on these numbers

- **The positions DB is not readable from here.** `db_is_pep` overrides every
  gate (`position.py:150-157`), so any target a reviewer has vetted emits
  regardless of the table above. A count taken with DB access will be higher than
  80; the user's own reading was 86 emitting against 120 on OS policy, and the
  difference is most likely exactly those vetted rows plus where one counts the
  23 IGO-undecided items. The partition by *cause* is the durable part.
- **`wd/shape.py` disagrees with itself here and both ways are bugs.** Its
  `type_targets` keeps deprecated claims where nomenklatura drops them, which
  over-reports exclusions (19 items, not 2); and `CLOSURE_CACHE` is lossy — one
  item's closure is 123 nodes read from `closure.json` and 140 read fresh, and
  the cached one misses `Q618779` outright, which under-reports (3). The two
  cancelled, which is how 3 came to look like a plausible answer. Neither is
  fixed yet; anything read out of `wd/shape.py`'s `excluded_by` is unreliable
  until they are.

## Retirement (2026-08-23)

The counts above are measured over the **209** QIDs the config named before any
retirement. `scripts/retire_specs.py` has since commented out **43** specs whose
targets `wd_peps` emits and whose members already hold the office
(`coverage/petscan_retirable.md`), leaving 551 specs, 241 with a `position:`
block and **174** distinct QIDs. 2,913 people now arrive from their own `P39`
statements; 213 leave OpenSanctions, all of them born before 1920 or long dead,
whom `wd_peps` declines by design.

One row of the checklist was held back rather than applied, and it is the reason
to replay the gates before writing rather than trust the checklist: see
`retire_specs.py:HOLD_BACK`.

## Statements written

`scripts/render_os_positions_plan.py` → 116 statements over 97 items, of which
**115 uploaded 2026-08-23 19:02** and verified live (`--verify`: 188 of 189).
One line outstanding: `Q7241113` `P279` `Q965043`. The 86-item generic-`P31`
lane and the surgical items are in `tasks/followups.md`.
