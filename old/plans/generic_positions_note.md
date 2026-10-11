---
description: Draft Project chat / WikiProject Politicians proposal for an "abstract position" P31 marker on generic classes of office, so they stop being used as P39 targets. Not posted.
date: 2026-10-06
tags: [wikidata, community, p39, generic-positions, draft]
---

# Draft: marking generic classes of office ("abstract position")

*For Wikidata:Project chat, cross-posted to WikiProject Politicians. Not posted yet.*

## The problem

Many `P39` (position held) statements point at a **class** of office rather
than at a specific office: "minister", "mayor", "member of parliament",
"ambassador". A statement like *X position held: minister* doesn't say which
country or which ministry, so readers, reusers and bots can't tell what office
was held.

We measured it in October 2026, counting every rank:

- 1,999,176 `P39` statements in total.
- 233 classes of office have **no jurisdiction** of their own and are held in
  many states. Between them they are the value of **154,814** `P39` statements,
  7.7% of all `P39`.
- The ten largest account for most of it: mayor (15,676), president (Q1255921,
  11,551), chairperson (10,149), director (9,662), minister (9,560), bishop
  (7,742), member of parliament (7,078), president (Q30461, 7,006),
  editor-in-chief (3,940) and ambassador (3,851).

The method and the full list are public. An item counts as generic when it is
typed as a position, has no concrete `P17`/`P1001`, and its holders come from
many countries, with no single country holding a majority.

## What already exists, and why it isn't enough

- **`Q136649946` (type of position)** is used on 93 items. About 40 of those are
  "mayor of a place in <country>", which *are* tied to a jurisdiction. So it
  means "a class of positions", not "a class with no jurisdiction". Only 11 of
  the 233 carry it.
- **The `P39` none-of constraint (`Q52558054`)** lists four of these classes,
  with mixed statuses: minister and deputy are mandatory, MP is a suggestion.
  Each addition needs property-talk consensus, and reusers have to parse
  qualifiers.

## Proposal

1. Create one item, **"abstract position"**: a subclass of `Q136649946` (type of
   position), meaning *a type of position not tied to any jurisdiction*.
2. Add it as an **additional** `P31` on each generic class. Their existing
   `P31 Q4164871` (position) stays, so nothing that works today breaks. It's
   purely additive.
3. Leave country-scoped classes alone. "mayor of a place in France" or "member of
   the French National Assembly" are legitimate intermediate classes and don't
   get the marker.

The first round would be about 233 items. Ten examples: mayor (`Q30185`),
president (`Q1255921`), chairperson (`Q140686`), director (`Q1162163`), minister
(`Q83307`), bishop (`Q29182`), member of parliament (`Q486839`), ambassador
(`Q121998`), prime minister (`Q14212`), head of state (`Q48352`).

## How reusers would read it

Read only the item's **own** non-deprecated `P31`, at any rank. Don't walk
`P279`: a specific office ("Minister of Finance of Brazil", `P279` minister)
must not inherit the marker.

```sparql
SELECT ?item WHERE {
  ?item p:P31 ?st . ?st ps:P31 wd:Q_NEW .
  MINUS { ?st wikibase:rank wikibase:DeprecatedRank }
}
```

Constraint and bot authors could then flag new `P39` statements onto a marked
class and suggest a specific office instead.

## Alternatives we considered

- **A `P5008` focus list:** a WikiProject focus-list item that every generic
  class carries. It works mechanically, but "on a project's focus list" means
  "someone is working on this", which is the wrong meaning for a permanent
  property of the class.
- **Extending the `P39` none-of constraint** (`Q52558054`, with `P6607`
  explaining each entry). That keeps the list on the property, but grows a
  single statement to hundreds of qualifiers, and each needs property-talk
  agreement.

## Questions for the community

- Is "abstract position" the right name? Would "generic position" or "position
  type without jurisdiction" be clearer?
- Should qualifier-scoped conventions be exempt? For example, "diocesan bishop"
  used with a `P708` diocese qualifier.
- Who maintains the list as new classes appear? We'd publish the measurement
  query so it can be re-run.
