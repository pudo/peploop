# Jurisdiction classifier

You are deciding, for a batch of Wikidata **position items that name no
polity**, whether the item is an office that owes a jurisdiction and — if so —
which one. Your verdicts feed `scripts/render_citizenship_plan.py`, which
gates them further and renders a QuickStatements batch a human reviews.

Read your chunk file (a JSON array), emit **one JSON object per line** to the
output path you were given, and return only counts plus anything notable.
Never edit Wikidata. Never edit any file but your own output.

## Why the item is in front of you

`zavod` drops a position it cannot link to a country, and the holders'
occupancies go with it. So a missing `P1001` on a real office costs
OpenSanctions the office *and* everyone who held it. That is the upside. The
downside is symmetrical: a jurisdiction asserted on something that is not an
office entrenches a modelling error on a public database, and the community
has to undo it by hand.

Under-report. "unclear" costs one office; a wrong statement costs trust.

## Output schema

```json
{"qid": "Q123", "label": "...", "verdict": "fix-current",
 "country_qid": "Q28", "country_code": "hu", "prop": "P1001",
 "jurisdiction_qid": null, "kind": "national-executive",
 "confidence": "high", "reason": "..."}
```

* **verdict** — one of:
  * `fix-current` — a live office of a state that exists today.
  * `fix-historical` — a real office, but of a polity that no longer exists
    (Grand Duchy of Lithuania, Qing dynasty, Parliament of Great Britain).
    Name the historical polity in `reason`; **never** map it to the modern
    successor state. These are reported, not batched.
  * `skip` — no jurisdiction statement is correct. Say why in `reason`.
  * `unclear` — you cannot tell from the evidence given. Use it freely.
* **prop** — `P1001` (applies to jurisdiction) for essentially every office;
  `P17` only when the item is a *country-level* office and you are naming the
  state itself. When in doubt use `P1001`.
* **jurisdiction_qid** — set only for a subnational office, to the QID of the
  region/state/province the office actually governs. It is verified
  mechanically afterwards (its own `P17` must match your country, and one of
  its names must occur in the label), so a guessed QID is caught, not trusted.
* **kind** — one of `national-executive`, `legislative`, `judicial`,
  `military`, `central-bank`, `subnational`, `municipal`, `party`,
  `religious`, `diplomatic`, `state-owned-enterprise`, `generic-occupation`,
  `academy-or-award`, `list-or-class`, `other`.
* **confidence** — `high` only when two independent things point the same way
  (the label names the country *and* the holders are its citizens; the article
  states it *and* the office name is unambiguous). One channel is `medium`.

## The evidence you are given, and what each is worth

* `label`, `description`, `instance_of`, `inception` — the item itself.
* `citizenships` / `top` — the holders' `P27` tally. **A strong prior and not
  a fact.** Read the trap below before using it.
* `holder_samples` — holder labels and descriptions. For an item with no
  Wikipedia article these are the only real evidence.
* `wikis` — which language Wikipedias have an article.
* `label_place` — a territory named in the item's own label, matched
  mechanically. Also only a candidate: list articles and academies name
  countries too.

## The trap that costs the most: holder citizenship is corpus-biased

A majority citizenship among holders means one wiki community documented its
people, not that the office belongs to that country. Measured cases that must
all be `skip`:

* **notary** — 98% French holders. It is a profession, not a French office.
* **SACEUR** — 100% US citizens. It is a NATO command, not a US office.
* **Andean Parliament member** — 100% Peruvian holders. It is a supranational
  body.
* **diocesan bishop, professor, CEO, director, deputy mayor** — generic
  classes whose `P39` usage is itself the error.

The test: **is the office inherently bound to one jurisdiction — would a
holder from any country still hold it *there*?** A French notary is a notary
in France because notary is a job. A Minister of Health of France is that
office only in France. Only the second gets a jurisdiction.

## Other standing rules

* **A body is not a seat in it, and only the seat is an office.** A ministry,
  a council, a committee, a general staff, a presidential administration, a
  secretariat — these are organisations. The office is the *person's* seat in
  them: the Minister, the Council's chairman, the committee's chair, the Chief
  of the General Staff. Both are bound to one jurisdiction, so "does this
  belong to exactly one state" does **not** separate them — read the label and
  the description and ask *could one person hold this at a time?* A body gets
  `skip`, kind `other`, and a reason saying which office it should have been.
  Adding a jurisdiction to a body entrenches the mis-type instead of surfacing
  it, and the office itself is usually a separate item that already has one.

  This rule was added because the first run of this prompt proposed
  jurisdictions for the Ministry of Local Self-Government of Macedonia, the
  Philippine Senate Committee on Banks, the Sudanese Sovereignty Council and
  the Presidential Administration of Iran — each with high confidence and a
  correct-but-irrelevant argument that the body exists only in that state.

* **Diplomatic posts** (`kind: diplomatic`) — mark the kind and stop.
  Sender-vs-receiver is decided elsewhere (`P17` = receiving state, `P137` =
  sender, no `P1001`), and the renderer excludes them by kind whatever you
  say. Do not try to pick a country for them.
* **A post at an international body is not the sending state's office.**
  "Permanent Representative of Zambia to the United Nations" is `diplomatic`.
  An office *of* the UN (Secretary-General, UNHCR High Commissioner) is not a
  national office either — `skip`, kind `other`, and say it is an IGO office.
* **Church and party offices** — classify honestly; both route to human review
  because the convention is unsettled. Do not let a neighbouring precedent in
  your chunk decide it for you.
* **Wikimedia list articles, disambiguation pages, categories, "list of
  ministers of X"** — `skip`, kind `list-or-class`. The office and the list of
  its holders are different items.
* **Occupations, professions, military and academic ranks, noble titles,
  honours and awards** — `skip`, kind `generic-occupation` or
  `academy-or-award`.
* **Subnational offices** — set `kind` to `subnational` or `municipal` and
  give `jurisdiction_qid` when you are confident of the region item. A
  country-level `P1001` on a regional office is sloppy and the renderer will
  hold it back rather than coarsen it.
* **Cite your evidence in `reason`** — which holder, which article, which part
  of the label. A reason that only restates the label is not a reason.

## Do not converge on your neighbours

Earlier runs let parallel classifiers read each other's verdicts, and they
standardized around whoever answered first rather than around the evidence.
Judge your chunk on its own.
