---
description: Work programme before the next paid pepcorp re-run of EU + CH — what the prompt-fixes plan left, the precision classes a fresh 60-line sample and whole-run sizing found, the tenure rules pepcorp should take from peploop, and the alignment of the three lanes that should happen around the re-run.
date: 2026-10-22
tags: [pepcorp, peploop, peptree, precision, tenure, rerun, alignment, eu]
---

# pepcorp: before the next Europe re-run

Inputs: `plans/pepcorp_prompt_fixes.md`, which is implemented in 5da37f4
(narrow class, link and person checks; the decide prompt's date and artistic
lines; newest answer per body; `reask`; `corp eval`), and peploop's tenure
work (be9816f, 6b47976). Also the 2026-10-20 run reports and the freeze. The
decisions behind them have not been re-planned under 5da37f4. Beside those,
a fresh random sample of 60 applied lines (seed 0.731), and whole-run counts
over the 4,034 applied seat rows.

## What the sample says

There are 60 lines. 47 are clean. 4 are wrong:
- Two seats or links sit on position items: Drug Commissioner `Q1259952`
  (typed `Q4164871`) and Generalny Konserwator Zabytków.
- One chair is stale (Sächsische Aufbaubank). The en infobox names one
  chair and the de article another, and the model flagged it in `notes`.
- One `P127` rests on a legal form (cz NKÚ, "organizační složka státu").
  The freeze already holds it.

The other 9 are doubtful:
- Two acting heads (pl GDDKiA "p.o." 2018–24, Tauron).
- An end taken from "the ministry proposed his dismissal" (cz DI).
- A marker on a body the article puts in the past tense (Abellio
  Deutschland).
- A board member whose quote names another body (Kulturstiftung Sachsen).
- Two seats whose dates are not in their quote (CIEMAT, Business France).
- Two undated "current" seats from infoboxes.

That is the same 85–90% as the earlier samples, but the classes are
different. They are now about **tenure precision** more than control.

Sized over the whole run (applied seats, 4,034):

| class | rows | note |
|---|---|---|
| undated seat (no start, no end) | 704 | the freeze's open question |
| start not in the seat's quote | 211 | some come from a second passage. Some are altered: bg `Q12279300` quote "22 юли 2026", written `2025-07-22` |
| end not in the seat's quote | 216 | mostly the successor's start, uncited |
| quote names acting/interim/p.o./kommissarisch | ~100 | rough regex; peploop writes none of these |
| item typed as a position | 24 | belong to peploop as `P39` |
| two current holders of one head/chair seat | 13 bodies | two of them are legitimate co-chairs (de-pl foundation) |
| `superseded` skips | 126 | peploop would close these at the successor's start |
| bodies whose notes say earlier holders were left out "for brevity" | 136 | lost recall inside the 20-year window |

## Work, in order

### 1. Rules: free, no re-ask

1. **Position items are not bodies.** At load time, gate items whose `P31`
   reaches a position class (`positions.POSITION_METACLASSES`). They are
   residue for peploop. Add a fixture.
2. **Contested current seat.** When two people hold one head or chair seat
   as current and neither is dated, write neither (`contested`). This is
   peploop's sibling rule applied to a body. A co-chair role is the
   exception.
3. **Dates must stand in a quote.** If a seat's start or end year is not in
   its quote, drop that date and judge the seat again by the date rules.
   This is the verbatim gate peploop has. It stays until §2.2 gives each
   date its own quote.
4. **Close at the successor.** For an open, not-current head followed by a
   later head of the same seat, end it at the successor's start. Cite the
   successor's quote for `P582`, as `propose.close_at_next` does. This
   replaces `superseded` and turns 126 skips into dated statements.
5. **Acting heads are written** (user, 2026-10-22). pepcorp does not follow
   peploop's `acting` exclusion. An acting seat is a seat, dated like any
   other. The flag in §2.1 is kept so the report can count acting seats.
6. **Undated is fine when current** (user, 2026-10-22). An undated seat is
   written when it is current. Current is read from peploop's present-tense
   or infobox markers (`policy` CURRENT/INFOBOX/NOT_NOW) in the quote, not
   from the model's `current` flag alone. An undated seat that is not
   current stays `undated_former`.

Each rule gets a fixture in `check_rules` and a case in
`eval/eu_2026_10.yml`. Then re-plan all 28 countries with `--no-ask`, and
diff each against the freeze.

### 2. Decide prompt: the one re-ask

These go into a single prompt change:

1. **`acting: bool`** on a seat, worded as in peploop's
   `prompts/extract.md`. It is counted in the report and does not gate.
2. **`start_quote` and `end_quote`** where the dates come from a passage
   other than the seat quote, such as a successor's line or an infobox.
   The date gate in §1.3 then reads them, and close-at-next has its
   evidence from the model.
3. **No omission for brevity.** List every holder whose tenure ended within
   the last 25 years. The rules cut by date, not the model.
4. **Past tense ends control.** "was a subsidiary of" sets `active` or
   `control.ended` rather than marking the body.
5. **An end is a tenure ending.** A proposed dismissal, a nomination or an
   announcement is not one. This extends the arrest line.

Ask only affected bodies (`reask`). Add these classes:
- a date not in its quote;
- "brevity", "omitted" or "left out" in the notes;
- two current holders;
- `superseded`.

Also the existing three classes. Estimate the cost from the selection
before asking. Expect most of the 2,179 bodies whose notes mention omitted
holders to fall out, because their omissions are older than 25 years.

### 3. A seat check

pepcorp verifies links, markers and classes, but not seats. peploop
verifies every `P39`. Add `verify_seat`: one narrow call per written seat
that asks whether the quote names this person in this role at these dates.
It uses peploop's vocabulary (`supported`, `contradicted`, `imprecise`,
`wrong-person`, with confidence), and the gate is "supported, not low". At
about 4,000 seats it is the cheapest broad precision lever. It re-keys only
its own calls.

### 4. Test, then spend

1. Extend the eval set with the cases above: this sample's 4 wrong and 9
   doubtful lines, the bg altered date, and 5 acting cases (expected:
   written) and 5 superseded cases.
2. Run `corp eval`, then a pilot re-ask of two countries (de and pl, which
   have the most undated rows).
3. Sample 60 lines from the pilot.
4. Only then re-ask the selection for all 28 countries, and write the
   history.md line.

## Aligning the three lanes

Moved to `plans/lane_alignment.md`.

## For the user

- **The freeze.** After §1, does the freeze still go out as it is, or does
  the re-planned run replace it?
