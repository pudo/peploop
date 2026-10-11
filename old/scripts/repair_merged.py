#!/usr/bin/env python
"""Split a statement QuickStatements merged back into one statement per tenure.

    python scripts/repair_merged.py --campaign ecuador           # dry
    python scripts/repair_merged.py --campaign ecuador --apply

QuickStatements matches an incoming line on subject, property and value alone,
so an additive batch carrying two spells of one office wrote **one** statement
holding every start and every end at once — `Q1368615` ended up claiming a single
Ecuadorian ministry with starts in 1991 *and* 2005 and ends in 1992 *and* 2010.
`wd/validate.py` now refuses to render such a batch and `scripts/apply_claims.py`
writes those tenures through the API instead; this repairs what shipped before
either existed.

The pairing is the whole difficulty: nothing in the merged statement says which
start belongs to which end, and the dates alone cannot say — an official's two
spells can interleave with a colleague's. So the pairing is taken from **the
batch's own lines**, which is why this reads a `.qs` rather than Wikidata, and
why a batch nobody kept cannot be repaired this way.

Two safety properties, because this is the one operation here that removes data:

* **It verifies before it touches.** The statement's own dates must be exactly
  the set the batch sent. Anything else — a human has split it, another batch
  merged into it, a date was corrected — is skipped and reported, never guessed
  at.
* **It adds before it removes.** Interrupted after the add, Wikidata holds a
  visible duplicate of one tenure, which is recoverable by looking. Interrupted
  after a removal-first, a date would simply be gone. So the new statements are
  written first and the surplus qualifiers stripped second.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.api import fetch_entities
from wd.http import REPO_ROOT, make_session
from wd.validate import DISTINGUISHING_QUALIFIERS, _parse
from wd.write import MAXLAG, Ledger, WriteError, _run, edit_entity, log

DATA_DIR = REPO_ROOT / "data"

#: Where each batch as *applied* lives. The regression baseline is the applied
#: artefact for the roster campaigns; `courts` and `positions` have no baseline
#: (and verdict files in a schema `render_edit_plan.py` cannot read), so their
#: `data/` copy is all there is.
BATCHES = {
    "ecuador": REPO_ROOT / "regression/ecuador/edit_plan.qs",
    "czechia": REPO_ROOT / "regression/czechia/edit_plan.qs",
    "uae": REPO_ROOT / "regression/uae/edit_plan.qs",
    "courts": DATA_DIR / "courts/edit_plan.qs",
    "positions": DATA_DIR / "positions/edit_plan.qs",
}


def iso_and_precision(token: str):
    """A QuickStatements time token as (ISO prefix, precision)."""
    body, precision = token.rsplit("/", 1)
    date = body.lstrip("+-").split("T")[0]
    keep = {"9": 4, "10": 7, "11": 10}[precision]
    return date[:keep], int(precision)


def api_time(token: str) -> dict:
    iso, precision = iso_and_precision(token)
    return {"time": iso, "precision": precision}


def api_reference(token: str):
    """A QuickStatements reference argument in wikibase-edit form.

    A reference's value can be a time as easily as a URL — `S813` (retrieved) is
    on every line this workbench writes — and handing `wikibase-edit` the raw
    QuickStatements token gets "invalid time value { property: 'P813', value:
    '+2026-08-06T00:00:00Z/11' }", which is what it should say.
    """
    if token.startswith(("+", "-")) and "T" in token and "/" in token:
        return api_time(token)
    return token.strip('"')


def claim_times(claim: dict, prop: str):
    """(ISO prefix, precision) for each qualifier value, plus its hash."""
    out = []
    for snak in claim.get("qualifiers", {}).get(prop, []):
        value = (snak.get("datavalue") or {}).get("value")
        if not value:
            continue
        keep = {9: 4, 10: 7, 11: 10}.get(value.get("precision"), 10)
        out.append((value["time"].lstrip("+-").split("T")[0][:keep],
                    value.get("precision"), snak.get("hash")))
    return out


def tenures(lines):
    """(subject, prop, value) → the tenures the batch meant, in file order."""
    groups = {}
    for line in lines:
        subject, prop, value, qualifiers, references = _parse(line)
        key = (subject, prop, value)
        signature = tuple((k, qualifiers[k]) for k in DISTINGUISHING_QUALIFIERS
                          if k in qualifiers)
        entry = groups.setdefault(key, [])
        if signature not in [s for s, _ in entry]:
            entry.append((signature, references))
    return {key: entry for key, entry in groups.items() if len(entry) > 1}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", required=True, choices=sorted(BATCHES))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    path = BATCHES[args.campaign]
    if not path.exists():
        raise SystemExit(f"No batch at {path}")
    session = make_session()
    groups = tenures([l for l in path.read_text().splitlines() if l.strip()])
    ents = fetch_entities(session, sorted({k[0] for k in groups}), max_age=0)

    out_dir = DATA_DIR / args.campaign
    ledger = Ledger.load(out_dir / "repaired.json")
    summary = f"split a QuickStatements-merged {args.campaign} statement into one per tenure"

    repaired = skipped = 0
    for (subject, prop, value), entry in sorted(groups.items()):
        label = subject
        entity = ents.get(subject)
        if not entity:
            print(f"· {subject}: item not found — skipped")
            skipped += 1
            continue
        matching = [c for c in entity.get("claims", {}).get(prop, [])
                    if (c["mainsnak"].get("datavalue") or {}).get("value", {}).get("id") == value]
        merged = [c for c in matching
                  if len(c.get("qualifiers", {}).get("P580", [])) > 1
                  or len(c.get("qualifiers", {}).get("P582", [])) > 1]
        if not merged:
            continue
        if len(merged) > 1:
            print(f"· {subject} {prop} {value}: {len(merged)} merged statements — "
                  "too tangled to split mechanically, skipped")
            skipped += 1
            continue
        claim = merged[0]

        # What the batch meant, and what the statement actually holds.
        wanted = {"P580": [], "P582": []}
        for signature, _refs in entry:
            bounds = dict(signature)
            for bound in ("P580", "P582"):
                if bound in bounds:
                    wanted[bound].append(iso_and_precision(bounds[bound]))
        live = {bound: claim_times(claim, bound) for bound in ("P580", "P582")}

        mismatch = [
            bound for bound in ("P580", "P582")
            if sorted(wanted[bound]) != sorted((d, p) for d, p, _h in live[bound])
        ]
        if mismatch:
            print(f"· {subject} {prop} {value}: {'/'.join(mismatch)} on Wikidata is not "
                  f"what the batch sent — skipped, needs reading")
            for bound in mismatch:
                print(f"    batch {bound}: {[d for d, _ in wanted[bound]]}")
                print(f"    live  {bound}: {[d for d, _p, _h in live[bound]]}")
            skipped += 1
            continue

        keep, *rest = entry
        # Two ledger keys, not one: the add and the removal are separate edits,
        # and a run interrupted between them must resume at the removal rather
        # than add a second copy of every split-off tenure.
        key = f"{subject}|{prop}|{value}"
        if ledger.qid(f"{key}|done"):
            continue

        keep_bounds = dict(keep[0])
        keep_dates = {b: iso_and_precision(keep_bounds[b]) for b in ("P580", "P582")
                      if b in keep_bounds}
        # Qualifier snaks to strip: everything that is not the kept tenure's own.
        # One hash per surplus value, matched by (date, precision) so a repeated
        # date cannot take the wrong snak with it.
        strip = []
        for bound in ("P580", "P582"):
            target = keep_dates.get(bound)
            seen_keep = False
            for date, precision, hash_ in live[bound]:
                if target and (date, precision) == target and not seen_keep:
                    seen_keep = True
                    continue
                strip.append(hash_)

        add_claims = []
        for signature, references in rest:
            bounds = dict(signature)
            claim_body = {"value": value}
            quals = {}
            for bound in ("P580", "P582"):
                if bound in bounds:
                    quals[bound] = api_time(bounds[bound])
            for other, token in bounds.items():
                if other not in ("P580", "P582"):
                    quals[other] = token
            if quals:
                claim_body["qualifiers"] = quals
            refs = {f"P{k[1:]}": api_reference(v) for k, v in references.items()}
            if refs:
                claim_body["references"] = [refs]
            add_claims.append(claim_body)

        plan = (f"{label} {prop} {value} [{claim['id'].split('$')[1][:8]}]: keep "
                f"{keep_dates.get('P580', ('?',))[0]}–{keep_dates.get('P582', ('',))[0]}, "
                f"split off {len(add_claims)}, strip {len(strip)} qualifier(s)")
        if not args.apply:
            print(f"· {plan}")
            continue

        # Add first, then remove: see the module docstring.
        payload = {"id": subject, "claims": {prop: add_claims}}
        try:
            edit_entity(payload, summary, ledger, f"{key}|add", apply=True)
            _run(["wb", "remove-qualifier", claim["id"], "|".join(strip),
                  "--summary", summary, "--maxlag", str(MAXLAG)])
        except WriteError as exc:
            print(f"✗ {plan}\n    {exc}")
            skipped += 1
            continue
        ledger.record(f"{key}|done", subject,
                      {"added": add_claims, "stripped": strip, "guid": claim["id"]})
        log(out_dir / "applied.jsonl",
            {"qid": subject, "repair": {"guid": claim["id"], "added": add_claims,
                                        "stripped": strip}})
        print(f"✓ {plan}")
        repaired += 1

    verb = "repaired" if args.apply else "would repair"
    print(f"\n{verb} {repaired}, skipped {skipped}")
    if not args.apply:
        print("Dry run — pass --apply to write.")


if __name__ == "__main__":
    main()
