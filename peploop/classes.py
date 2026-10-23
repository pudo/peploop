"""Name the Wikidata classes that say what sort of thing an item is.

Reach for these instead of writing a QID into a rule. Every lane asks the
same questions: is this item an office, a body, a place, an honour? A lane
that keeps its own copy of the answer drifts from the others.

Where two lanes test different sets, both are here under names that say
what each holds. Merging them changes what both lanes filter, so a merge
waits for a measurement.
"""

#: Metaclasses that say "this is an office" and nothing about which kind.
#: `Q4164871` is not the modal one: of the items that are the target of some
#: `P39`, 17,788 are typed `Q294414` public office, and among ministers that
#: is 85% of them. A check demanding a literal `P31 = Q4164871` misses them.
POSITION_METACLASSES = {
    "Q4164871",  # position
    "Q294414",  # public office
    "Q17279032",  # elective office
    "Q114962596",  # historical position
    "Q83856136",  # legal position
    "Q136649946",  # type of position
    "Q355567",  # noble title
    "Q42045197",  # position of authority
}
#: The three of them an item declares when it is plainly typed a seat: what
#: peptree reads as "typed a position" when nothing else says so.
POSITION_CORE = {"Q4164871", "Q294414", "Q17279032"}
#: A class of office ("mayor of a place in X"), not an office someone holds.
TYPE_OF_POSITION = "Q136649946"
#: Wikimedia list article and list of persons: a list, not what it lists.
LIST_ARTICLES = {"Q13406463", "Q19692233"}

#: Wikidata's own answer to what a position is not, read off `Q4164871`'s
#: `P1889 different from`, plus the rank, honour and body classes measurement
#: turned up. Tested against *declared* types only: within six hops
#: `Q28640` profession reaches `Q4164871`, so a closure test reads a naval
#: rank and a wood-carving trade as offices. peploop's ranking reads it.
NOT_AN_OFFICE = {
    "Q480319",  # title of authority
    "Q12737077",  # occupation
    "Q28640",  # profession
    "Q11348",  # function
    "Q192581",  # job activity
    "Q4189293",  # rank
    "Q56019",  # military rank
    "Q4226220",  # naval officer rank
    "Q43229",  # organization
    "Q495430",  # general staff — a body, not a seat in one
    "Q6813432",  # military staff — also a body
    "Q3320743",  # title of honor
    "Q13424289",  # honorary title
    "Q618779",  # award
    "Q4192699",  # badge of distinction
    "Q486983",  # academic rank
    "Q4121104",  # sports title
}
#: Declared types that say the item is an honour, a rank, an award, a list or
#: a person. peptree's load filter reads it. It shares 9 classes with
#: `NOT_AN_OFFICE`: occupations and bodies are judged by other rules there.
HONOURS_AND_RANKS = {
    "Q5",  # human: "oldest living person in Finland" is a subclass of people, not a seat
    "Q3320743",  # title of honor
    "Q13424289",  # honorary title
    "Q618779",  # award
    "Q4192699",  # badge of distinction
    "Q1499804",  # grade of an order
    "Q38593919",  # medal of an order
    "Q799000",  # breast badge
    "Q4189293",  # rank
    "Q56019",  # military rank
    "Q4226220",  # naval officer rank
    "Q19476593",  # police rank
    "Q303618",  # diplomatic rank
    "Q486983",  # academic rank
    "Q3529618",  # academic title
    "Q4121104",  # sports title
    "Q55956975",  # honorary sporting title
    "Q414528",  # academician
    "Q2625729",  # corresponding member
    *LIST_ARTICLES,
}

#: What a body reaches through `P31`/`P279`: organization.
ORGANISATION = "Q43229"
#: "ambassador of a country": the class layer with one subclass per *sending*
#: state ("ambassador of <state>"), whose own `P17` is that sender in 205 of
#: 207 items. Its sibling layer, "ambassador to a country", has one subclass
#: per receiver and says nothing about who sends.
SENDER_CLASS = "Q29645880"
#: A `P1001` value of one of these kinds is a territory: anything else (a
#: ministry, a corps, a party) says nothing about the office's level.
TERRITORY = {"Q56061", "Q486972", "Q515", "Q7275", "Q6256", "Q3024240", "Q82794", "Q1048835"}
CITY = "Q515"
