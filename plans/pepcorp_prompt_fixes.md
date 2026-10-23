---
description: Fix the error classes the EU + CH re-run's precision samples found, mostly in the narrow checks rather than the decide prompt, so the 6,189 planned lines are corrected without re-asking every body.
date: 2026-10-20
tags: [pepcorp, prompt, precision, verify, eu]
---

# pepcorp: prompt fixes without a re-ask

The re-run's samples (542 lines; `plans/pepcorp_eu_policy.md`, "Re-run
2026-10-19/20") left error classes that rules cannot see. Changing
`prompts/decide.md` changes its hash, and every body's request is keyed by it.
After that change, `--no-ask` finds no answers, and a full re-ask costs
~$170. So each fix goes where it is cheapest:

1. **Narrow checks** (`verify.py` and similar). One short call per line the
   rules would write, keyed by its own prompt. Changing them re-keys only
   those calls (~3–5k lines, a few dollars), and `corp run --no-ask`
   re-runs them. Most classes fit here: they are about whether one quote
   carries one claim.
2. **Decide prompt.** Only for what the decide call alone sees: dates and
   which person sits in which seat. These need a re-ask, done for the
   affected bodies only (§3).

## 1. Narrow checks (no decide re-ask)

| Class | Example | Fix |
|---|---|---|
| Founding or "a state institute" read as owner | it FS → its foundation; lu CNA "one of the state's cultural institutes" | `verify_link.md`: drop "founded it" from the supporting list. Being one of a state's institutes supports `P749` to a named body, never `P127` to the polity. The check is told which property it checks; today it is told only owner or parent. |
| A minister's statutory supervision refused as parent | pl NFOŚiGW, ZUS | `verify_link.md`: a state legal person under its minister's supervision by statute is subordinate (parent), unlike an independent regulator's oversight. |
| "Regulator" stretched to watchdogs, registries, patent offices, an anti-doping agency | hu Fiscal Council, pt INPI, mt registry, at NADA | New check `verify_class`: the statutory class goes to the same narrow call as the marker, with the control quote and the body's first paragraph. A regulator must set rules for a sector or market, license it, or supervise its firms. A refused class gets `class_unverified`. Broadcaster and central bank are checked too (cheap). |
| A namesake through the article's own link | fi Ruokavirasto head, mt exchange | Linked seats go through `match.py`'s page check when the person's item neither names the body (employer, position, description) nor has a page that mentions it. Today only unlinked seats are checked. Cost scales with linked seats lacking a tie, likely a few hundred. |

Order:
1. Make the four changes, with fixtures (`check_rules`, plus
   `check_verify` for the prompts' plumbing).
2. Test on a regression set (§4).
3. Re-plan all 28 countries with `--no-ask`.

Only checks are paid for.

## 2. Decide prompt (re-ask needed)

Leadership, dates section:
- **Snapshot lists.** A list or infobox "as of" a date gives that date as
  the start, marked as such. With no date anywhere, the seat is current
  only when the text says so in the present tense. An undated list of
  members is not current.
- **Ends from events.** An end date is when the article says the tenure
  ended (resigned, replaced, term ended). An arrest, an investigation or a
  scandal is no end.
- **Artistic leads.** A chief conductor, artistic director, curator or
  editor-in-chief is `head` only when the article names no general,
  administrative or managing director. When it does, that person is
  `head`, and the artistic lead is left out.

## 3. Asking only the affected bodies

Change `decide.from_ledger` to take each body's newest answer under any
decide prompt hash, not only the current one. Then a new prompt applies body
by body, and a re-plan still sees every country's answers. Each answer's own
hash is kept in `pcorp_call` and stays queryable.

Select the bodies to re-ask from the stored answers with SQL:
- any seat with neither start nor end;
- any seat whose end quote names an arrest, charge or investigation, by a
  word list per language;
- institutions whose `head` title matches conductor, artistic, curator or
  editor in the answer's quotes.

Estimate: 15–25% of bodies, ~$30–45. Re-ask them with
`corp run <cc> --qid …`, already the pilot's path, then re-plan with
`--no-ask`.

## 4. Testing without touching the run files

`corp run --qid` writes the country's run file, and `corp send` sends the
latest one. The regression run must not overwrite the 6,189-line files.

Add a `corp eval <file>` verb:
- **Input:** a YAML of QIDs, each with the outcome expected (rule fired,
  line written or not).
- **Run:** it asks and checks those bodies through the same functions,
  then compares each with its expectation.
- **Output:** a table. No run file and no report.

The set:
- every wrong and doubtful line from the three samples (~45);
- the pilot's 24 cases;
- 20 lines judged correct, to catch regressions.

## Not in scope

- **mt one-tier plc chair as supervisory:** the user decided on
  2026-10-19 that a board over a CEO is supervisory.
- **Duplicate head/chair seats across properties (fr):** a rule extension
  of `head_other` to chairs; a rule, not a prompt fix.
- **An undated head contradicting the item's closed tenure:** a rule. Skip
  when the item already ends that person's statement or names a later
  holder.
