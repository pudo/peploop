# Research note: how Wikidata models diplomatic posts

Context: 386 diplomatic position items (1,866 P39 holders) from the
jurisdiction backfill (tasks/jurisdictions.md) were held back pending a
sender-vs-receiver convention decision. This note documents the existing
conventions, measured empirically on 2026-08-04.

## Documented guidance

* **P1001 "applies to jurisdiction"** is deliberately broad: *"the item …
  belongs to or has power over or applies to the value"*. For a bilateral
  post both the sender ("belongs to") and receiver ("applies to") readings
  are legitimate — which is exactly why usage is split.
* No WikiProject documents diplomat modeling. WikiProject every politician
  covers legislatures/cabinets only. The convention is emergent, readable
  from the well-curated clusters below.

## De-facto conventions (measured)

**Bilateral posts** — subclasses of Q29645886 "ambassador to a country"
(264 items, the Hungarian foreign-service cluster is the flagship):

| Property | Usage | Meaning |
|---|---|---|
| P17 country | **262/264** | the **receiving** state |
| P1001 jurisdiction | 44/264 (35 doubled sender+receiver, 9 receiver only) | both jurisdictions |
| P137 operator | curated items | the **sending** state |
| P2389 organization directed | curated items | the embassy/mission item |
| P279 | all | → Q29645886, often also "ambassador of X" and "ambassador to Y" classes |
| P461 opposite | curated items | the reverse post |

Exemplar (Q63024073 ambassador of Hungary to United Kingdom):
P17=UK, P1001=Hungary+UK, P137=Hungary, P2389=Embassy of Hungary in London.

**Sender-named classes** — subclasses of Q29645880 "ambassador of a country"
("ambassador of Finland", …): **P17 = the sending state**, no P1001. So P17
means "the state in the item's name", not consistently sender or receiver —
but on bilateral posts it is always the receiver.

**Apostolic nuncios** (curated exemplar Q28530618 Apostolic Nuncio to
Poland): **P1001 = Q159583 Holy See (sender)**, no P17; the receiving side
is encoded via P279 → "ambassador to Poland" (the per-receiver class layer);
P2389 → the nunciature item.

## Decision for the 386 held-back items

1. **P17 = receiving state** on every receiver-named post (nuncios "to X",
   "ambassador of X to Y", consuls-general "in <city>"). This is the 99%
   convention, and it is what OpenSanctions needs: zavod reads P17 directly,
   and OS convention for `role.diplo` positions is that the position's
   country names the receiving state (see wikidata_occupancy).
2. **P137 operator = sending state** where the sender is unambiguous from
   the label (nuncios → Holy See; "Consul General of France in X" → France;
   "ambassador of X to Y" → X). Encodes the sender without leaning on the
   ambiguous P1001; matches the curated exemplars.
3. **Do not mass-assert P1001** on these: doubled-P1001 is minority practice
   (35/264) and single-value P1001 would take a side the community hasn't.
4. Consular posts named by city need a city→country resolution for the
   receiving state (e.g. Kyoto → Japan); the classifier verdicts already
   attempted this — normalize and spot-check rather than trust blindly.

Normalization plan: re-derive sender/receiver mechanically from the label
("of X" → sender, "to Y"/"in Y" → receiver side), reconcile against the
per-chunk verdicts, route disagreements and city-only receivers to review,
then emit `P17` (+ `P137`) QuickStatements.

## Status

- [x] conventions researched (this note)
- [x] normalization (2026-08-04, `scripts/render_diplomatic_plan.py`):
  * **278 auto rows → 572 QS statements** (P17 receiver + P137 sender where
    parseable), covering 1,600 holders. Includes 7 sender-convention
    overrides (classifier had picked the sender; label receiver wins) and
    city-resolved consulates (city item's preferred/un-ended P17, gated on
    classifier agreement or classifier-chose-sender).
  * **33 org representatives** (UN, NATO, EU, OECD, IAEA…): P137 sender
    only, no P17 — in the .qs, listed separately in the .md.
  * Held for review: 2 disagreements (Melbourne city-resolver trap caught by
    the gate; Zaire Q971 vs DRC Q974), 16 unresolved receivers (incl. the
    genuinely stateless Consul General of France in Jerusalem), 57 unparsed
    labels (non-English, attachés, oddities) — LLM tail pass possible.
  * Plan: `data/jurisdictions/diplomatic_plan.md` / `.qs`.
- [x] Opus tail pass over the 73 leftovers (2026-08-04): 70 fix / 3 skip /
  0 unclear → `diplomatic_tail.qs` (**96 statements** from the 60
  high-confidence rows); 13 medium-confidence rows appended to the .md for
  review. Highlights: caught a non-position (Q12759558 Serbia consulate
  *organisation*, sole holder 1907), corrected two sender-latched hints
  (Seoul→KR, Dubrovnik→HR), sender-only for org-accredited posts and PRC's
  Hong Kong commissioner (SAR ≠ receiving state), receiver-only for AIT
  Kaohsiung (operator is a nonprofit, not the US state).
- [ ] review diplomatic_plan.md → apply diplomatic_plan.qs + diplomatic_tail.qs
