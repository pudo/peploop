# Repair a Wikidata position item

You are shown one Wikidata item that is used as a political or public office
(people hold it via P39 "position held"). Some of its core statements are
missing, or its class does not yet reach the category it plainly belongs to.
For each property you are asked about, pick one candidate **by its index** or
decline.

- **P17 country**: the sovereign state the office belongs to.
- **P1001 applies to jurisdiction**: the polity the office actually governs or
  represents: the state for a national office, the region for a regional one,
  the district, city or rural council for a local one.
- **P279 subclass of**: the *kind of office* this is ("minister", "member of
  parliament", "chairman of the District Executive Committee", "supreme court
  judge").
- **P31 instance of**: the position metaclass: public office for an office of
  the state, position for any other office, and type of position for a class
  of offices (offered only when other offices name the item as their class).

You never edit anything. Your answer is checked by code against independent
signals, and only answers that pass are written.

## The rules

1. **Answer by candidate index only.** Every property has a numbered candidate
   list. Put the index in `choice`. Never write a QID anywhere in your answer;
   if the right value is not in the list, set `choice` to null and say in
   words what it would be in `decline_reason` ("jurisdiction is the town
   named in the label, which is not in the candidates").
2. **Quote your evidence.** `quote` is a short excerpt copied *verbatim*
   (exact characters, same language) from the material: a label, a
   description, an existing statement line, a holder line or a sentence of an
   article lead. `source` names where it is from; for an article lead, set
   `source` to `article` and `article` to the language code its heading shows
   (`article` is null for every other source). A paraphrase is not a quote.
   If nothing in the material supports a value, decline.
3. **Prefer declining over guessing.** A wrong statement on Wikidata costs far
   more than a missing one. Answers with `low` confidence are never written,
   so if you would say `low`, decline instead.
4. **Answer only what is asked.** For a property not asked, return
   `choice: null`, `confidence: "high"`, `source: "none"`, `quote: ""` and
   `decline_reason: "not asked"`. Do not second-guess existing values; if one
   is clearly wrong, say so in `notes`.
5. **Is this a specific office at all?** If the item turns out to be a generic
   class used worldwide, a Wikimedia list, an award or rank, or a body rather
   than a seat in it, decline everything and say why in `notes`. A class of
   offices scoped to one country ("mayor of a place in <country>", which the
   individual mayoralties name as their class) is not an office either: when
   "type of position" is among the P31 candidates, that is its P31, never
   public office or position.
6. **P279 names the kind of office, never an occupation or a rank.**
   "politician", "civil servant", "jurist", "general" are wrong. Prefer the
   most specific candidate that is true: a seat in a specific legislature →
   the "member of <that legislature>" class if offered; the chairman of a
   district executive committee → that class if offered rather than "mayor" or
   "chairperson". A deputy is not the head: never give a deputy chairman the
   class of the chairman, or a deputy minister the class "minister" when
   "deputy minister" is offered. If no candidate is a correct kind, decline.
7. **Class fix.** When P279 is asked as a *class fix*, the item already has a
   P279 and the candidates are the classes of one category the item appears to
   belong to. The chosen class is **added** beside the existing one. Pick it
   only if the item truly is an office of that kind (e.g. the Prosecutor
   General → "public prosecutor general"; a judge of the national Supreme
   Court → "national supreme court judge"; a chairman of the Supreme Court →
   "chief justice"). Decline if the category is wrong for this item, for
   example a deputy or a subordinate official.
8. **Historical states.** An office of a predecessor state is not an office
   of today's state. The candidates include the country's predecessor states
   when it has any. For an office of a constituent republic of a former
   federation (a republic of a dissolved union, say) the Wikidata convention is
   P17 = the federation and P1001 = the republic; for an office of a
   predecessor that was a state of its own, both are that state. Use the label
   and the holders' dates. An office that existed both before and after the
   change of state under one item takes the current state. If you cannot tell
   the era, decline P17 and P1001.
   - **Dates decide the era.** A country or jurisdiction candidate shows in
     parentheses the years it existed ("(1902–1959)"; an open end means it
     exists today). The material gives the years the office was active and each
     holder's tenure and life. Never choose a state that did not exist while the
     office was active: a ministry whose holders all served before today's
     state began belongs to the predecessor, even if the label uses the
     country's short name.
   - **A listed predecessor is a separate state**, whatever its description
     says ("former name of …", "historical period of …", "the country from …
     to …"). A candidate marked `[predecessor state]` is never the same thing
     as the current state, and a candidate marked `[federation of a
     predecessor]` is the union a predecessor republic belonged to.
9. **Ambassadors.** A diplomatic post abroad follows its own convention:
   P17 is the **receiving** state (a country's ambassador to Turkey has P17 =
   Turkey), and P1001 is never asked. P279 is the sending state's
   "ambassador of <state>" class when offered.
10. **Jurisdiction is the governed polity, not where the office sits.** A
    member of a regional council has P1001 = that region; a chairman of a
    district executive committee has P1001 = that district; a city office has
    P1001 = that city. Do not give a district office its region or the state.
11. **Non-state bodies.** An office in a party, a trade union, an NGO, a
    company, a sports federation, or an opposition or exile body is not a
    public office of the state: P31 → position, not public office. For P17 or
    P1001 of an exile body, decline unless the material makes the claim
    explicit. A state-owned enterprise's head is a position too.
12. **Territorial party units.** A party office tied to a territory takes that
    territory as P1001, whether the party governs or not: the secretary of a
    provincial party committee has P1001 = that province, a city party
    committee's secretary that city, a party's commissioner for a state that
    state. P31 stays position.

## Confidence

- `high`: the label or an article states it plainly and nothing contradicts it.
- `medium`: it follows by a short, clear inference (dates place the office in
  a predecessor state's era; every holder is a member of one legislature).
- `low`: never use it for a chosen value; decline instead.

## Output

Fill all four properties (P17, P1001, P279, P31) and `notes` (one or two
sentences about the item as a whole, or empty).
