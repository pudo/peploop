# Requirements

The direction the project's owner has set for the tools. **Principles** are
reviewed and grouped; each carries the date(s) it was stated. **Log** is what
the owner said, verbatim and dated, awaiting review. On review an entry
becomes or joins a principle and leaves the Log; its verbatim text stays in
git history. Instructions for a single task go into that task's plan.

## Principles

### PEP scope

- A country sweep, national and subnational, covers all FATF positions, a
  broad set of holders, and rich personal details on Wikidata. (2026-10-14)
- State-owned enterprises follow the EU AMLR, and all three lanes move toward
  the regulation's functions, producing data that helps OpenSanctions meet its
  requirements. (2026-10-17, 2026-10-23)
- The leadership of state museums, theatres, research centres, broadcasters
  and state enterprises run as part of the administration (Landesbetriebe) is
  PEP: these are essential institutions. (2026-10-17)
- The Union's bodies and international organisations are in scope. Relatives
  and close associates are not, for now. (2026-10-24)
- Reading may go wide: position classification downstream is the final
  filter. (2026-10-17)
- The EU's list of prominent public functions is a living asset in the repo:
  the original list, per country, expanded over time from its categories into
  concrete items. (2026-10-24)

### Modelling on Wikidata

- Mint an office when it is well justified, even with no current holder.
  (2026-10-12)
- Completeness justifies minting: "if we have 3 out of 9 governors, let's make
  the other 6". (2026-10-23)
- Whether a position is abstract or generic rather than one state's office is
  part of each lane's main evaluation, and the list of generic positions is
  kept clean. (2026-10-13)
- An office with jurisdiction X does not also need country X: `P17` is added
  only where the jurisdiction is narrower than the country. (2026-10-16)
- Era rule: a country-related statement, and a position's own country, must
  fall within the time the country existed. (2026-10-15)
- Ownership and control are judged by heuristics, "not math on fake numbers":
  shares, sizes and percentages are neither sourced from nor stored on
  Wikidata. (2026-10-17)
- Statutory bodies with no owner (public broadcasters, independent
  regulators, central banks) are typed appropriately. (2026-10-18)

### Contributing to Wikidata

- The tools take part as an individual member of the community, not as a
  corporate account. If contributing becomes a burden or nuisance to the
  community, the work stops and the data is built elsewhere. (2026-10-25)
- Intake is broad and writes are precise and mainstream (Postel's law). The
  tools' conventions come from majority usage on Wikidata and are never
  enforced across it: they add beside other editors' modelling and never
  swap or remove it. Where a minority form is very small, double-tagging can
  be considered. (2026-10-25)
- Edit summaries make sense to an outside editor: they say what an edit is
  for, not which internal tool or schedule made it. (2026-10-13)
- Minted offices carry no description, except a generic title that names no
  polity; labels only in English and the territory's own languages; no
  country in the label, since `P17`/`P1001` carry it. (2026-10-24)
- Every write to Wikidata goes out in coordination with the owner, also
  when a sweep runs unsupervised. (2026-10-20)

### Data quality and working method

- A seat whose holder the article does not link may be matched by a fuzzy
  name search, but the candidate's own Wikipedia page must name at least the
  industry or domain, ideally the institution. (2026-10-18)
- A gap study ends in the tool changes that close the gap; measurement only
  sizes it. (2026-10-23)
- Country sweeps run autonomously to their dry run rather than prompting the
  owner every few minutes. (2026-10-12)
- Changes to the repo's instructions simplify them overall. (2026-10-12)
- Requirements are logged verbatim and worked into principles on review.
  (2026-10-25)

## Log

- 2026-10-25: On the purpose: "OpenSanctions needs this data, and one of the
  ways we're exploring to build it out is via Wikidata. However this is not a
  corporate push: I've chosen to use the Pudox over the OpenSanctions account
  to be a member of the community as an individual. If contributing the data
  to Wikidata becomes a burden or nuisance to the community, we'll stop and
  build elsewhere"
- 2026-10-25: "for the requirements, we can keep logging verbatim and then
  work them into principles upon review"
