# Requirements

- 2026-10-12: The key goal of this package is to run autonomous country
  sweeps, not to prompt the user every five minutes. No prompting the user
  for sends, removals and the like.
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
