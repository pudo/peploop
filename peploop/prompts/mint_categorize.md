# Categorizing the offices nobody could place

You are given a list of **groups**. Each group is the office mentions in one
country's Wikipedia articles that were written in the same words — a title and
the jurisdiction the article named — and that no existing Wikidata item could
be matched to. Your job is to say which **distinct offices** these groups name,
what kind of thing each one is, and how its item would be labelled, so that the
offices that really are missing can be created.

Your answer is not written to Wikidata. A later pass re-reads every office you
propose against the full evidence, a mechanical guard checks the holder counts,
the shape and live duplicates, and only an office every stage agrees on is
created. Anything you mark `unclear` is skipped with that reason recorded. So a
refusal is a complete answer and a wrong `office` is not. **Prefer `unclear` to
guessing.**

## What you are given

**The state.** Its name, the QID its offices are scoped by, and the languages
its offices are labelled in.

**Items you may cite.** Every QID you write must come from these lists; a QID
from anywhere else is removed mechanically after the fact. They are:

- **the state** and **its first-level subdivisions**, which are the values a
  `jurisdiction_qid` may take. One marked "(dissolved)" no longer exists: an
  office of it is still scoped to it, never to the state, because the
  evidence is about that place;
- **census bodies**: courts, chambers, councils and organs a country survey
  named;
- **parties**: the political parties the country's seeded people belong to,
  most members first. They are what a party office names as its `body_qid`;
- **kinds of office**: the generic class items an archetype is a kind of;
- **items the reconciler considered**: what the matcher looked at for these
  groups and refused, with its verdict counts on each group's line;
- **the state's existing offices**, one per line as `QID | label | kind`, where
  `kind` is the label of the item's own `P279` parents. A row marked
  `(not an office)` is a body, an occupation or a rank: citable as a
  `body_qid`, never as an existing office.

**Kind tallies.** How often each `kind` occurs among the state's existing
offices. It tells you what this country's community usually makes an office a
kind of.

**Census anchors.** Offices a survey of the country's institutions says exist,
each with a key. A group that names one of them is assigned to it by giving its
`census_key`. An anchor no group names needs nothing from you.

**The groups**, one block each:

```
g12 | Title as written [| other spellings] | jur: … | 5 mentions, 4 people, 1 current | lang es
  reconciler: none 3, body-not-seat 2 → Q123 (label)
  > "a short quote from the article"
```

- `people` counts distinct persons, and `current` how many of them the
  extraction dated as holding the office now. They are evidence of how real and
  how live an office is, not a reason to merge or split.
- `reconciler` is what the matcher answered for these mentions. `body-not-seat`
  with a body QID means it found the court or chamber and not the seat in it;
  `generic-class` means it found only the class; `wrong-office` means the
  closest item was a different office. These are the most useful lines on the
  page: they name the body or the parent the missing seat belongs to.

## Clustering: one office, one item

Many groups are pieces of one office. Put them in one office when they name the
same seat in different words:

- gendered forms of one title (a male and a female form of mayor, magistrate,
  president);
- the same office in two languages, when the jurisdiction or body agrees;
- the title with and without its jurisdiction, or with the jurisdiction written
  differently, when nothing in the evidence suggests two seats;
- abbreviations and spelling variants.

Keep them apart when they are different seats, even when the words are close:

- **A body is not a seat.** The court, the council, the ministry is an
  organisation; the office is the seat in it. A group that names only the body
  ("the Constitutional Court") is `body`, not the judge's seat.
- **A deputy is not the principal.** Vice-, deputy, adjunct, under-, acting
  and second offices are their own offices, never folded into the one above.
- **A member is not the chair.** The president of a court or council and a
  judge or member of it are two offices; the chair is the single seat.
- **Different places are different offices.** The mayor of one town and the
  mayor of another are two items, as are the governors of two subdivisions.
- **A renamed office is a new item per name.** When the evidence shows a
  portfolio or a body was renamed, each name and era is its own office, linked
  by `replaces_qid` when the predecessor is on the lists.

Every group is assigned **exactly once**: to one office's `groups`, or to
`unassigned` with a reason. A group you cannot place is `unassigned`, never
left out.

## The decision

Each office gets one `decision`:

- **`office`** — a real public office of this state, held by one person at a
  time or by each member of a body, that has no item among the existing
  offices. This is the only decision that can lead to an item being created.
- **`exists`** — the office already has an item among the state's existing
  offices or the items the reconciler considered, and the reconciler missed
  it. Give the QID in `exists_qid`. Use it only when that row *is* this seat:
  the same place, the same body, the same level, not merely the same kind.
- **`party-membership`** — being a member of a party, a party list, a
  coalition. Membership is recorded as a party affiliation, not an office.
- **`body`** — the group names an organisation (a court, a ministry, a
  council, a chamber, a party organ) and no seat in it.
- **`occupation`** — a profession or activity: lawyer, journalist, economist,
  activist, councillor-in-general with no body named.
- **`rank`** — a military, police, diplomatic or academic rank or grade: a
  general, a colonel, a commissioner rank, a professor.
- **`honorific`** — a title of honour, an order or a decoration, a courtesy
  title, an emeritus status.
- **`historical-only`** — an office of a predecessor state or regime, or one
  abolished before anyone now living could hold it, so nobody holds it today.
- **`foreign`** — an office of another state or of an international
  organisation, held by a citizen of this one.
- **`not-state`** — a post outside the state: a company that is not
  state-owned, a university, a club, an NGO, a business association, a church
  post, a local party post, a parliamentary caucus spokesperson, the rotating
  chair of an international organisation.
- **`unclear`** — the evidence does not settle what the office is, or which
  seat. Use it freely; say what is missing in `reason`.

**Parties.** Party *membership* is `party-membership`. So is membership of a
large party organ — a central committee, a national council, a party congress:
Wikidata records it as membership of the organ (`member of`), not as a seat,
by hundreds to one, and such an office is never created. Say so in `reason`.
The seats that are offices are a national party's leader, chair or president
(archetype `party_leader`), its general secretary or secretary-general and a
seat in its secretariat (`party_secretary`), and a seat in its political
bureau (`politburo_member`). The title word decides between the first two: a
general secretary is `party_secretary` even where the post leads the party, a
first secretary or chair is `party_leader`. Every one of them names its party
as `body_qid`, from the parties list or the census bodies; draft one whose
party is on neither with a null body, and it will be skipped for that. Local
and regional party posts and a party's spokesperson in a chamber are
`not-state`. Minor and opposition parties are parties like any other.

**Diplomacy.** An ambassadorship or a permanent representation abroad is
`office` with archetype `ambassador`. It will not be created in this round, but
it is an office and must be recorded as one.

## The shape of an office

For every office, whatever its decision:

- **`institution_class`** — one of the classes below, or null when none fits:

  `executive.head_of_state`, `executive.head_of_government`,
  `executive.deputy_leadership`, `executive.cabinet`,
  `executive.deputy_ministers`, `executive.leader_office`,
  `legislature.lower_membership`, `legislature.upper_membership`,
  `legislature.leadership`, `legislature.historic_chambers`,
  `oversight.constitutional_body`, `oversight.state_councils`,
  `oversight.audit_anticorruption`, `oversight.electoral_commission`,
  `judiciary.apex`, `judiciary.prosecution`, `judiciary.specialised`,
  `economic.central_bank`, `economic.sovereign_wealth`,
  `economic.soe_leadership`, `economic.regulators`,
  `security.defence_command`, `security.paramilitary`,
  `security.intelligence`, `security.police`, `subnational.executive`,
  `subnational.municipal`, `subnational.assemblies`, `diplomatic.outbound`,
  `diplomatic.multilateral`, `hybrid.ruling_family`,
  `hybrid.religious_hierarchy`, `hybrid.parastatal_foundations`,
  `hybrid.state_media`, `political.parties`.

- **`archetype`** — the kind of seat, one of the names below, or null when
  none fits. Null is a complete answer; a wrong archetype gives the item the
  wrong parent.

  | archetype | the seat |
  |---|---|
  | `minister` | a minister of the national government |
  | `legislator` | a member of a chamber or assembly |
  | `judge` | a judge or magistrate of a court that is not the apex |
  | `supreme_judge` | a judge or magistrate of an apex court |
  | `court_president` | the president of a court |
  | `speaker` | the president or speaker of a legislative chamber |
  | `governor` | the executive head of a subdivision |
  | `mayor` | the executive head of a municipality |
  | `agency_head` | the head of a state agency, directorate, office, regulator or oversight body |
  | `central_bank_governor` | the governor of the central bank |
  | `prosecutor_general` | the head of the national prosecution service |
  | `military_chief_of_staff` | the commander or chief of staff of the armed forces or a branch |
  | `soe_head` | the head of a state-owned enterprise |
  | `state_body_member` | a member of a collegial state body that is not a chamber or a court: an electoral council, a board, a commission |
  | `politburo_member` | a seat in a party's political bureau |
  | `party_leader` | the leader, chair or president of a national party |
  | `party_secretary` | the general secretary or secretary-general of a national party, or a seat in its secretariat |
  | `ambassador` | an ambassadorship or a permanent representation abroad |

  The head of a police force or an intelligence service is `agency_head`. A
  deputy of any of these is the same archetype as the principal only when it
  is a seat of its own; a vice-minister is not `minister`, it is null. A
  vice-president or deputy speaker of a chamber is not `speaker`, it is null.

- **`single_seat`** — true when one person holds the office at a time (a
  minister, a mayor, a court's president), false when each member of a body
  holds it (a legislator, a judge of a bench, a council member).

- **`labels`** — the office's name as a Wikidata label, in each of the state's
  languages and in English (`en`), one entry per language. A label is the name
  of the office, not of the person and not of the body: "Mayor of X", "Member
  of the Y", "President of the Z Court". Use the most official form the
  evidence shows, the jurisdiction or body spelled out, no abbreviations, no
  dates, no party.

  **Capitalisation.** Wikidata has no single rule and the measured practice
  differs by office, so follow the state's own existing offices of the same
  kind on the list in front of you. Where there is none: in English, capitalise
  a named office's title word ("Minister of Finance", "Governor of X",
  "President of the Y Court") and lowercase a membership seat ("member of the
  Senate of X"), which is how most such items are labelled; in a language whose
  orthography writes titles in lower case (Spanish, French, Portuguese,
  Italian), lowercase the title word ("alcalde de X", "ministre de …"); in German
  capitalise nouns as German does. Never write a label in all capitals.

- **`description_en`** — a short English description in Wikidata style,
  lowercase, no final full stop, naming the state: "public office in …",
  "member of the … of …".

- **`parent_qid`** — the item this office is a kind of (its `P279`), from the
  kinds of office or the state's existing offices: when the state's existing
  offices of this kind are all a kind of one country-specific class ("mayor of
  a place in …"), that class is the parent. The head of a state-owned
  enterprise takes the class its title word names: director general,
  chairperson or president, all among the kinds of office; so does the head of
  an agency (director, director general or chairperson). A party's general
  secretary takes general secretary, a seat in its secretariat party
  secretary. Null when unsure; the archetype supplies a default.

- **`body_qid`** — the court, chamber, ministry, council, organ, company or
  party the seat is in. Null when the office is not a seat in a body, or the
  body is not on the lists.

- **`jurisdiction_qid`** — the polity the office governs, when it is the state
  or one of the listed subdivisions. **`jurisdiction_name`** — the polity's
  name as written, always when the office governs a place, and especially when
  the place is not on the lists (a municipality usually is not).

- **`replaces_qid`** — the existing office this one is the renamed successor
  of. Null unless the evidence says so.

- **`census_key`** — the key of the census anchor this office is, if any.

- **`evidence`** — the words that settle the decision, quoted from a group's
  title or quote. Quote, never paraphrase.

- **`reason`** — one sentence saying why this decision, this archetype and
  these groups.

## Standing rules

- **Assign every group exactly once.** A group missing from your answer, or
  in two offices, is recorded as a defect of the answer.
- **Cite only what is listed.** Every QID must appear in the lists in front of
  you. A QID recalled from memory is removed and recorded as a problem, so it
  buys nothing.
- **One office per seat, one item per name.** Two groups for one seat in two
  languages are one office with labels in both. Two seats with the same words
  are two offices.
- **Evidence is what the groups show.** A single mention by one person is
  still a group and still gets an office or `unassigned`; whether there is
  enough evidence to create it is decided later, by counting people, not by
  you.
- **You never edit anything.** There is no tool to call and no item to change.
- Background knowledge may inform a judgement — that a ministry was renamed,
  that a body is an organ of a party — but `evidence` must quote the input.
- **Keep the answer short.** For any decision other than `office`, give only
  `groups`, `decision`, `exists_qid` (for `exists`), `evidence` and `reason`:
  `labels` is an empty list and every other field is null or false. Group
  several groups that share one non-office decision ("occupation",
  "not-state") into one entry rather than one entry each. `evidence` is a few
  words, `reason` one short sentence.
