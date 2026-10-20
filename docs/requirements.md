# Requirements

- 2026-10-12: The key goal of this package is to run autonomous country
  sweeps, not to prompt the user every five minutes.
- 2026-10-12: Keep this file with only the requirements the user states
  directly, not answers to questions. Every time the user states one, note it
  down. It is a statement of intent: the LLM is not authorized to expand the
  set of requirements, but is required to record them.
- 2026-10-12: Changes to the repo's instructions simplify them overall
  instead of expanding them.
- 2026-10-12: Also mint empty positions if well-justified.
- 2026-10-13: Make it part of the primary design of peptree/peploop to
  consider if a position is abstract/non-national in their main evaluation.
- 2026-10-13: Worst case we could even build a generic/abstract detection
  stage of the pipeline as a separate model call. Making that list clean is
  immensely valuable, and recording every generic position to it goes out of
  reconciliation.
- 2026-10-13: Improve the readability of the QS edit comments in peploop and
  peptree. They talk about themselves but nobody knows what peploop and
  peptree are (this repo is private). We probably shouldn't mention stuff like
  "send so <date>", it's internal.
- 2026-10-14: For a country sweep on the national and subnational levels: "We
  want all FATF positions, broad holders, and rich Wikidata personal details."
- 2026-10-15: "let's design an era rule for country-related statements"
- 2026-10-15: The era rule "is also for positions: if the position was created or
  dissolved outside the country's existence, etc."
- 2026-10-16: "if a position has jurisdiction X, we don't also need to put
  country X. country X only makes sense if the stated jurisdiction is more
  specific (eg. region Y of country X)."
- 2026-10-17: For state-owned enterprises: "follow EU AMLR".
- 2026-10-17: "it's ok for wd_peps to go too wide, because position
  classification can serve as a final filter"
- 2026-10-17: On state museums, theatres, research centres, broadcasters and
  Landesbetriebe: "these are essential institutions and their leadership is
  PEP."
- 2026-10-17: "in general I feel we shouldn't get too deep into percentages,
  sizes and control because WD is a weird place to source and store that.
  [...] We want heuristics, not math on fake numbers."
- 2026-10-18: On statutory bodies with no owner (public broadcasters,
  independent regulators, central banks): "should be typed appropriately"
- 2026-10-18: On person matching for seats the article does not link: "my
  ambition would be that we check by name in a fuzzy manner but then set
  pretty strict standards for the resulting wikipedia pages. They need to
  mention at least the industry or domain, ideally the institution"
- 2026-10-20: "sending should be done in coordination with the user, even in
  cases where an autonomous/unsupervised sweep is being conducted."
