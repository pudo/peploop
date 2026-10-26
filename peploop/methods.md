# Methods: the shared vocabulary and its helpers

The three lanes all write associations:
- peploop ties a person to an office (`P39`) and to the person's own facts;
- peptree ties an office to its class, state and polity
  (`P31 P279 P17 P1001`);
- pepcorp ties a body to its owner or parent (`P127 P749`), to its marker and
  class (`P31`), and its leaders to their seats on it.

All three read Wikidata JSON, compare dates, fold text, check quotes and
judge tenures. This file names those parts. It also lists the plain modules
that do each part once. A lane reaches for the module rather than writing its
own copy, so that a fix there reaches every lane. A lane's policy stays in
the lane's own rules. Those rules call the helpers.

## Terms

- **Claim**: a subject, a property and an object, with dates and sources. A
  rule decides about a claim.
- **Source**: the passage a claim rests on: `{lang, url, rev, quote, dates?}`.
  `dates: "P582"` marks a passage that dates only the end. A statement cites
  one article, home wiki first (`plan.reference`).
- **Quote**: text copied verbatim from the material the model was shown. A
  claim whose quote is not in that material is not written.
- **Time value**: Wikidata's `{time, precision}`. Two dates are compared at
  the precision they share.
- **Span**: a pair of years, start and end, either one open. Used for states,
  offices and values (`eras`).
- **Spell**: one continuous holding of one office or seat. A **tenure** is
  the statement that records one or more spells.
- **Current**: the source says the holding continues now, in the present
  tense or in an infobox. **Acting**: the holder stands in for the office.
  **Snapshot**: a list or infobox dated "as of" some day.
- **Candidate**: an object the code offers by index. A model answers with an
  index, never with a QID. A free name resolves only when exactly one item
  matches.
- **Verdict**: what a narrow check returns: a verdict word, a confidence and
  the evidence it quotes.
- **Channel**: one independent signal for a claim. Examples are a label,
  holders, siblings, a body, a category, an official list and a legal form.
  The model counts as one channel.

## Families of rules

Rules are described by the question they answer. There are eleven
questions, listed in the order a claim meets them:
- **scope**: is the subject ours?
- **evidence**: is the claim in the text that was shown?
- **resolution**: which item is the object?
- **object-kind**: is the object the right sort of thing for the property?
- **judgment**: does a narrow check agree?
- **corroboration**: does a channel independent of the model agree?
- **time**: is the holding dated, ended or current?
- **era**: did the subject and the object exist at the same time?
- **conflict**: does the claim contradict a sibling or another holder?
- **subsumption**: does an existing statement already say this, or imply it?
- **plan**: can the claim be written as a line?

These names are for docs and reviews, such as "every `time` rule in the three
lanes". No code reads them.

## The shared modules

- `wikidata`: reads a fetched entity (`claim_qids`, `claim_time`,
  `best_label`). The lanes' `values` helpers are thin calls into it.
- `dates`: time values.
  - `time_value` builds one; `at_precision` compares at a shared precision.
  - `year` reads the year at any precision; `known_year` returns None below
    year precision.
  - `after_today` compares at the value's own precision; `group_dates`
    merges two articles' readings of one date.
- `text`: normalises text before a comparison.
  - `squash` collapses whitespace and control characters.
  - `fold` transliterates to casefolded ASCII, for names across languages.
  - `strip_marks` drops diacritics but keeps the script, for words within
    one country's languages.
- `evidence`: the quote gate.
  - `quoted` and `missing` forgive whitespace, case, JSON escapes and
    wrapping marks, and nothing else.
  - A quote must be `MIN_QUOTE` (4) characters long, or `MIN_QUOTE_DENSE` (2)
    in a logographic or syllabic script (rigour's `is_dense_script`). Only a
    sex may be quoted as one character (男), so peploop's extraction passes
    `min_length=1` for its gender quotes alone.
- `tenure`: whether a holding's dates make it worth writing.
  - `bad_dates`, `ended_long_ago` (`MAX_ENDED_YEARS`, 20) and
    `open_too_long` (`OPEN_TERM_YEARS`, 4).
  - `says_current` reads a quote's present-tense or infobox markers per
    language (`CURRENT`, `INFOBOX`, `NOT_NOW`).
  - `names_end_event` catches an end dated by an arrest or an investigation.
  - The lane decides how it knows a holding is current: peploop from its
    quotes, pepcorp from the model's flag.
- `propose`: one person's spells of an office: `overlaps`, `close_at_next`,
  `tenure_key`.
- `classes`: the QIDs that say what sort of thing an item is: position
  metaclasses, not-an-office classes, organisation, territory, the sender
  class of ambassadors.
- `verdict`: what a check of one claim answers, and the one gate `accepts`:
  supported, not at low confidence.
  - `VERDICTS` is the full set, used by peploop's verifier.
  - `LINK_VERDICTS` and `PERSON_VERDICTS` are the subsets pepcorp's link and
    person checks answer from.
  - `Confidence` is the type every lane's prompts answer in.
- `eras`: spans of states, offices and values (`span_of`, `state_start`,
  `overlaps`).
- `typegraph`: subclass closures. Use it for every "is this a kind of X" test.
  The type tree mixes offices with classes of office and with unrelated
  subtrees, so never walk `P279*` bare.
- `plan.reference`: the one reference shape (`P143` + `P4656` + `P813`).
- `route.route`: plans a claim against the live item: a new statement, a
  merge into one that is there, or a skip.
- `checks`: `expect` and `ent`, for every offline check.

## Deliberate differences between lanes

- **Acting holders.** pepcorp writes acting heads as seats. peploop leaves
  acting tenures out.
- **Corroboration.** peptree applies a value only when a channel besides the
  model agrees. peploop and pepcorp need a quote and a narrow check.
- **What is not an office.** peploop's ranking reads `NOT_AN_OFFICE` and
  peptree's load filter `HONOURS_AND_RANKS`. They share 9 classes. Merging
  them changes both lanes' filters and waits for a measurement.
