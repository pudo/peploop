---
description: Modelling decisions collected after the non-OECD peptree sweep, to be combined into one round of code changes and edit batches.
date: 2026-10-06
tags: [peptree, modelling, backlog, decisions]
---

# peptree modelling backlog: decisions (2026-10-06)

Collected after the sweep finished: 209 of 210 non-OECD places done, with Russia
left to WikiProject EP. Each item is a decision. "Change" says what to build.

## Wikidata edits (class level)

1. **Nuncio counts as ambassador.** Q157037 is `P279` "ambassador of a country",
   but it is also under papal legate (Q740369), which the ambassador category
   excludes. *Change:* `categories.yml`/`gaps.reaches` treats an item that
   reaches a class handle through a path not via the excluded subtree as in the
   category. Concretely: an exclusion only applies when the item does not *also*
   reach a handle directly (nuncio → ambassador of a country). Re-render va.
   No Wikidata edit.
2. **Cypriot deputy minister: replace the class.** On Q66126505, add `P279`
   Q26204040 (deputy minister) and **remove** `P279` Q15735113 (Assistant
   Secretary). The removal is destructive: a one-item wikibase-cli edit, applied
   by hand after review. The nine member lines become unnecessary; withdraw any
   that were not pasted.
3. **Classes of office get `P31` type of position.** An item that is another
   item's `P279` (a class: "mayor of a place in Peru") and has no `P31`
   Q136649946 gets one, additively. Wrong `P31`s (Romania's class typed
   "public office") stay in place, listed as a byproduct for human removal.
   *Change:* a class lane in repair (the `p31_on_a_class` veto already finds
   them).
4. **Brazil: the additive half only.** For the ~4,300 type/class-swapped
   mayoralties and the ~680 with `P31` mayor and no `P279`: add `P31` public
   office and `P279` mayor (or the "mayor of a municipality in <state>" class
   their siblings use). Leave the wrong claims for others to remove. *Change:*
   lift the inverted skip for `P31`/`P279` *additions* on items of this shape.
   This is mass-asserting a measured convention, so first measure the sibling
   class per state and dry-run one state.

## peptree rules

5. **Party offices carry `P1001`** for the territory of every territorial
   party unit, ruling party or not. *Change:* nothing blocks this today. Write
   it into the repair prompt and the plan so the model stops declining it.
6. **`P31` position type:** apply when the item's `P31` is empty, **or** none of
   its existing `P31` values reaches the position hierarchy (Q4164871 closure).
   A "military rank" type gets one; a "mayor" type, which is under position,
   does not. *Change:* `p31_weak_channel` becomes a rule on that predicate.
   Re-decide the 1,394 skipped slots from the ledger (`--no-ask`) and measure
   how many apply.
7. **De facto states:** model what Wikidata types. Artsakh, Abkhazia,
   Somaliland and the Sahrawi Republic take `P17` when typed a state. No change.
8. **Off-country items:** drop from the load an item whose own `P17`/`P1001`
   is another state with no link to the country being run (Mayor of Peshawar
   under India, a British regimental colonelcy). Unscoped items still load by
   citizenship. *Change:* a `classify` drop reason, `scoped_elsewhere`, with a
   check.

## Left as is

9. **Indonesia's ~9,795 unheld civil-service posts:** leave them. The focus
   rule keeps them out; the ledger notes it.
10. **Vietnam's Kingdom of Kampuchea predecessor:** leave it. It produced no
    lines; revisit if it does.

## Generic-class marker

11. **Draft the community note and extend `generic_positions.csv`.** Add the
    generic classes the sweep met: "ambassador of a country" (Q29645880),
    "ambassador to a country" (Q29645886), "deputy minister" (Q26204040),
    "chief justice" (Q3188089), "governor" (Q132050)… measured, not declared,
    using the same columns and holder spread the file already uses. Draft the
    Project chat note proposing the "abstract position" `P31` marker. Nothing is
    tagged on Wikidata yet.

## Outcome (2026-10-06)

- 1 nuncio: built (`soft: true` exclusions); only the 186 Holy See nunciatures moved in.
- 2 Cyprus: applied on Wikidata (P279 deputy minister added, Assistant Secretary removed).
- 3 class typing: built, then switched off. "Has subclasses, no direct holders"
  caught real offices and missed Peru's class. The vetoes stay.
- 4 Brazil: skipped after review. The swapped mayoralties already read as
  positions with P17/P1001, so the additive half would add 8,500 edits for no
  consumer gain. Belongs to a bot operator.
- 5 party P1001: prompt rule. The prompt hash changed, so any future *asking*
  run re-asks every request; re-render with `--no-ask`.
- 6 P31: built; the re-decision yielded 161 public-office lines (chunk-035).
- 8 off-country drop: built, catches 0 on current data. It surfaced the
  two-letter-code bug ("to" named Tonga), fixed separately for states and
  gazetteer places.
- 11 generic classes: chief minister added; note drafted in
  `plans/generic_positions_note.md`; nothing posted.
