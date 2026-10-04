# Mark generic position classes on Wikidata

Mark the 232 classes in `peptree/generic_positions.csv` (minister, mayor, member of
parliament…) with a new metaclass, "generic type of position" (a subclass of
`Q136649946`), so that a reader can tell from the item itself that it is not a
usable value of `P39`. `research/generic_positions.md` has the evidence and the
alternatives that were rejected.

Order, each step by hand:

1. Post `proposal.wiki` to WikiProject Ontology and WikiProject Politicians, which
   pings the creator of `Q136649946`. Wait a few days for objections.
2. Create the item: paste `new_item.qs` into QuickStatements. Note the new QID.
3. Replace `Q_NEW` with that QID in both tag files.
4. Run `tag_batch1.qs`, which holds the top 100 by `P39` use (147k statements).
5. A week later, if nobody has objected, run `tag_batch2.qs` (the remaining 132).

Every tag line adds a `P31` and removes nothing, so each batch can be reverted as a
whole from EditGroups. Both files parse cleanly in QuickStatements with a
placeholder QID.

Consumers must read the marker from the item's own non-deprecated `P31` only,
never through the `P31`/`P279` closure. Otherwise every specific office inherits it
from its generic parent.
