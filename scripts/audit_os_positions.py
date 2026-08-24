#!/usr/bin/env python
"""Audit the position items OpenSanctions names by hand, against how Wikidata models offices.

Reach for this when a consumer's config *asserts* a position — a name, a country,
a topic set — beside a QID. Those assertions are the tell: a crawler that has to
name the office itself is working around an item it cannot read. This script
reads one such config, `datasets/_wikidata/categories/wd_categories.yml`, whose
`position:` blocks carry 209 distinct QIDs, and scores each item with `wd.shape`.

    python scripts/audit_os_positions.py
    python scripts/audit_os_positions.py --json data/discover/os_positions.json

The report keeps three answers apart, the same split as `wd/shape.py`:
Wikidata modelling defects, unasserted conventions (gaps), and what the consumer
currently makes of the item. It adds a fourth that only exists because the config
is hand-written: where the config's asserted country or topics **disagree** with
what the item yields, one of the two is wrong, and the disagreement is the
strongest single signal in the audit for which items need work.
"""

import argparse
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from wd.api import best_label, best_description, claim_qids, fetch_entities  # noqa: E402
from wd.http import make_session  # noqa: E402
from wd.shape import PEP_SENTINEL, SUB_TYPES, verify_all  # noqa: E402
from wd.specs import load_specs  # noqa: E402

OS_ROOT = Path("/Users/pudo/Code/opensanctions")
CATEGORIES_YML = OS_ROOT / "datasets/_wikidata/categories/wd_categories.yml"
IGO_REGISTRY = OS_ROOT / "zavod/zavod/shed/wikidata/igo.py"

#: `position.py:170-176`. An office whose `P2389` or `P361` reaches a registered
#: international body takes that body's country and topics and skips the country
#: gate entirely — the only route by which an office with no national
#: jurisdiction is discoverable at all. `wd/shape.py` does not model it, because
#: a country audit never meets one; this audit is two thirds IGO posts.
IGO_LINK_PROPS = ("P2389", "P361")


def intl_orgs() -> Dict[str, Any]:
    """zavod's registry of international bodies, loaded from its own source.

    Imported off the file rather than copied, because the registry is a list of
    113 QIDs that grows — a transcribed copy would be wrong within a release and
    would be wrong silently. The module imports nothing but `dataclasses`, so it
    loads outside zavod's environment.
    """
    spec = importlib.util.spec_from_file_location("zavod_igo", IGO_REGISTRY)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load the IGO registry at {IGO_REGISTRY}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return dict(module.INTL_ORGS)


def config_positions(path: Path = CATEGORIES_YML) -> Dict[str, Dict[str, Any]]:
    """The QIDs the config names, with everything it asserts about each.

    Reads through `wd.specs.load_specs` rather than the yml directly. A second
    parser for one config is the duplication `CLAUDE.md` calls a signal that
    something is missing from the toolkit — and `load_specs` knows three things a
    fresh parser has to relearn: the `categories` list is not at a fixed path in
    the document, a `position:` block with no country of its own inherits the
    category's, and `Spec.granularity` says whether the name denotes one seat or a
    class of offices. The last is the one this audit could not have derived: five
    of the 209 QIDs sit on a `bucket` spec, meaning the config stretched a generic
    class item to stand for a whole family of offices.

    One QID can appear under several specs (22 do), and the assertions can differ
    between them, so countries and topics accumulate into sets rather than being
    overwritten by whichever spec was read last.
    """
    out: Dict[str, Dict[str, Any]] = {}
    for spec in load_specs(path):
        if not spec.target:
            continue
        row = out.setdefault(
            spec.target,
            {"names": set(), "countries": set(), "topics": set(),
             "categories": [], "granularity": set()},
        )
        row["categories"].append(spec.category)
        row["granularity"].add(spec.granularity)
        if spec.position_name:
            row["names"].add(spec.position_name)
        if spec.position_country:
            row["countries"].add(spec.position_country)
        row["topics"].update(spec.position_topics or [])
    return out


def audit(path: Path = CATEGORIES_YML) -> List[Dict[str, Any]]:
    declared = config_positions(path)
    qids = sorted(declared)
    session = make_session()
    orgs = intl_orgs()
    entities = fetch_entities(session, qids, max_age=0)
    labels = {qid: best_label(e) or "" for qid, e in entities.items()}
    verdicts = {v.qid: v for v in verify_all(session, qids, labels=labels)}

    rows: List[Dict[str, Any]] = []
    for qid in qids:
        row: Dict[str, Any] = {"qid": qid}
        row.update(
            {
                "config_name": sorted(declared[qid]["names"]),
                "config_countries": sorted(declared[qid]["countries"]),
                "config_topics": sorted(declared[qid]["topics"]),
                "categories": declared[qid]["categories"],
                # `bucket` means the config's own name is a class of offices
                # rather than a seat. Carried through so a renderer can *flag*
                # such a row — not hold it back: `Q68081922` "minister of the
                # government of the Czech Republic" is a generic class and a
                # `P279 = Q83307` on it is exactly right. What the flag is for is
                # the other direction, a jurisdiction: `Q19810880` took a `P1001`
                # to Saudi Arabia because it was a generic "deputy crown prince",
                # and that is the mistake this field makes visible.
                "granularity": sorted(declared[qid]["granularity"]),
            }
        )
        entity = entities.get(qid)
        if entity is None:
            row["status"] = "missing"
            rows.append(row)
            continue
        # A merged item comes back under its redirect target, so the config's
        # QID and the entity's own id disagree — which means the consumer is
        # keying a position on an item that no longer exists under that id.
        if entity.get("id") != qid:
            row["redirects_to"] = entity.get("id")
        row["label"] = labels.get(qid)
        row["description"] = best_description(entity)
        verdict = verdicts.get(qid)
        if verdict is None:
            row["status"] = "unverified"
            rows.append(row)
            continue
        row.update(verdict.as_dict())
        row["status"] = "ok"
        row["disagreements"] = disagreements(row, verdict)
        row["igo_link"] = igo_link(entity, orgs)
        row["cohort"] = cohort(row)
        row["lever"] = lever(row)
        # The item's own claims for the four properties a fix lane reads, so a
        # renderer works off the audit rather than refetching 209 items — and so
        # the record of what the item carried when it was judged is committed.
        for prop in ("P17", "P1001", "P361", "P2389", "P31", "P279"):
            row[prop.lower()] = claim_qids(entity, prop)
        rows.append(row)
    return rows


def igo_link(entity: Dict[str, Any], orgs: Dict[str, Any]) -> Optional[str]:
    """The registered international body this office directs or sits in, if any."""
    for prop in IGO_LINK_PROPS:
        for qid in claim_qids(entity, prop):
            if qid in orgs:
                return qid
    return None


#: What the config asserts when the office has no national jurisdiction: `zz` for
#: a global body, `un` for a UN organ, `eu` for the Union. A Wikidata item cannot
#: be expected to carry any of them as a country, so they select the cohort rather
#: than being read as a country claim.
PSEUDO_COUNTRIES = {"zz", "eu", "un"}


def cohort(row: Dict[str, Any]) -> str:
    """`igo` or `national` — which gate in `wikidata_position` the item must pass.

    Taken from what the config asserts, not from the item: the config's `zz` *is*
    the human judgement that this office has no national jurisdiction, and it is
    the only channel that separates the OSCE Secretary General (an IGO post whose
    `P17` would be wrong) from the Chief Justice of Russia (a national office
    whose `P17` is merely missing).
    """
    if set(row["config_countries"]) & PSEUDO_COUNTRIES:
        return "igo"
    if "gov.igo" in row["config_topics"]:
        return "igo"
    return "national"


def lever(row: Dict[str, Any]) -> str:
    """The one thing that would make this item discoverable, or "" if nothing must.

    Ordered by which gate `wikidata_position` reaches first, so each item names
    the gate that actually stops it rather than every gate it would fail:

    * `surgical` — the item is two things at once or is not an office. A retype or
      a merge, never a batch.
    * `no_polity` — nothing resolves a country and the office owes one.
    * `igo_link` — an IGO post with no `P2389`/`P361` into a registered body. The
      highest-value additive lane here, because the property is the community's
      own recommendation for the office of an organisation and the item usually
      carries no country claim that could ever substitute.
    * `untyped` — declares a metaclass and never says what kind of office.
    * `upstream` — modelled correctly and named a kind of office; the reason it
      confers nothing is that the class is absent from (or non-conferring in)
      zavod's `SUB_TYPES`. Not a Wikidata defect and never an edit: it is an
      issue to file, and retyping the office to trip the sentinel is the exact
      corruption `recipes/position_items.md` forbids.
    """
    if "also_a_list_article" in row["defects"] or "not_a_position" in row["defects"]:
        return "surgical"
    if "no_polity" in row["defects"]:
        return "no_polity"
    if row["cohort"] == "igo" and row["igo_link"] is None:
        return "igo_link"
    if "untyped" in row["defects"]:
        return "untyped"
    if "pep_default_off" in row["os_notes"]:
        # An IGO post that reached a registered body is *not* blocked: the
        # registry sets `is_pep = None` (`position.py:280-286`), so the office
        # enters the review UI undecided instead of being dropped. Registry
        # membership vouches for the org and a human vouches for the seat, which
        # is the design and not a gap to close on Wikidata.
        if row["cohort"] == "igo" and row["igo_link"]:
            return "review"
        return "upstream"
    return ""


def upstream_classes(rows: List[Dict[str, Any]]) -> Counter:
    """Classes that leave a well-modelled office conferring no PEP status.

    Two kinds, and the tally does not distinguish them because the fix is the
    same issue either way: a class absent from `SUB_TYPES` altogether
    (`Q42178` vice president), and a class present but conferring only a `gov.*`
    topic (`Q4175034` legislator, `Q16533` judge — both of which name an office
    every FATF reading treats as exposed).
    """
    counter: Counter = Counter()
    for row in rows:
        if row.get("lever") != "upstream":
            continue
        for qid in row["declared"]:
            if qid in POSITION_NOISE:
                continue
            counter[qid] += 1
    return counter


#: Metaclasses that say "office" and nothing more. Excluded from the upstream
#: tally because they are what every position item carries and naming them there
#: would bury the classes that actually decide the verdict.
POSITION_NOISE = {"Q4164871", "Q294414", "Q17279032", "Q13406463"}


def disagreements(row: Dict[str, Any], verdict: Any) -> List[str]:
    """Where the config's assertions and the item's own claims contradict.

    Only contradictions, never absences: the item yielding *nothing* is already
    reported as a defect, and re-reporting it here would drown the cases where
    two channels both answered and answered differently.
    """
    out: List[str] = []
    config_countries = set(row["config_countries"]) - PSEUDO_COUNTRIES
    item_countries = set(verdict.countries)
    if config_countries and item_countries and not (config_countries & item_countries):
        out.append(
            "country: config %s / item %s"
            % (",".join(sorted(config_countries)), ",".join(sorted(item_countries)))
        )
    config_topics = set(row["config_topics"])
    item_topics = set(verdict.topics) - {PEP_SENTINEL}
    if config_topics and item_topics and not (config_topics & item_topics):
        out.append(
            "topics: config %s / item %s"
            % (",".join(sorted(config_topics)), ",".join(sorted(item_topics)))
        )
    return out


def report(rows: List[Dict[str, Any]]) -> None:
    total = len(rows)
    ok = [r for r in rows if r["status"] == "ok"]
    print(f"# {total} position QIDs named by wd_categories.yml\n")

    missing = [r for r in rows if r["status"] != "ok"]
    if missing:
        print(f"## {len(missing)} not verifiable")
        for row in missing:
            print(f"- {row['qid']} {row['status']}: {row['config_name']}")
        print()

    redirects = [r for r in ok if r.get("redirects_to")]
    if redirects:
        print(f"## {len(redirects)} merged away (config keys a dead QID)")
        for row in redirects:
            print(f"- {row['qid']} -> {row['redirects_to']} {row.get('label')}")
        print()

    def tally(key: str) -> Counter:
        counter: Counter = Counter()
        for row in ok:
            for value in row.get(key, []):
                counter[value] += 1
        return counter

    print("## Modelling defects")
    print(f"well modelled: {sum(1 for r in ok if r['well_modelled'])} / {len(ok)}")
    for name, count in tally("defects").most_common():
        print(f"  {name}: {count}")
    print()
    print("## Gaps (unasserted conventions)")
    print(f"complete: {sum(1 for r in ok if r['complete'])} / {len(ok)}")
    for name, count in tally("gaps").most_common():
        print(f"  {name}: {count}")
    print()
    print("## What the OpenSanctions build makes of them")
    for name, count in tally("os_notes").most_common():
        print(f"  {name}: {count}")
    no_country = [r for r in ok if not r["countries"]]
    print(f"  no country resolves: {len(no_country)}")
    print()
    print("## Config disagrees with the item")
    for row in ok:
        for line in row.get("disagreements", []):
            print(f"- {row['qid']} {row.get('label')}: {line}")
    print()

    print("## Cohort")
    for name, count in Counter(r["cohort"] for r in ok).most_common():
        print(f"  {name}: {count}")
    igo = [r for r in ok if r["cohort"] == "igo"]
    linked = [r for r in igo if r["igo_link"]]
    print(f"  igo posts linked to a registered body: {len(linked)} / {len(igo)}")
    print()

    print("## Lever — the gate that stops each item")
    for name, count in Counter(r["lever"] or "none" for r in ok).most_common():
        print(f"  {name}: {count}")
    print()

    for name in ("surgical", "no_polity", "igo_link", "untyped"):
        lane = [r for r in ok if r["lever"] == name]
        if not lane:
            continue
        print(f"### {name} ({len(lane)})")
        for row in lane:
            print(
                f"- {row['qid']:12} {(row.get('label') or '')[:56]:58} "
                f"declared={','.join(row['declared']) or 'NONE'}"
            )
        print()

    review = [r for r in ok if r["lever"] == "review"]
    if review:
        print(f"### review — IGO posts that enter the review UI undecided ({len(review)})")
        for row in review:
            print(f"- {row['qid']:12} {(row.get('label') or '')[:56]:58} "
                  f"body={row['igo_link']}")
        print()

    print("### upstream — correctly modelled, class confers no PEP default")
    upstream = [r for r in ok if r["lever"] == "upstream"]
    print(f"{len(upstream)} items. The classes responsible:")
    for qid, count in upstream_classes(ok).most_common():
        conferred = SUB_TYPES.get(qid)
        note = (
            "absent from SUB_TYPES"
            if conferred is None
            else "confers " + ",".join(sorted(conferred))
        )
        print(f"  {qid}: {count} items — {note}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yml", type=Path, default=CATEGORIES_YML)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()
    rows = audit(args.yml)
    report(rows)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(rows, indent=1, ensure_ascii=False))
        print(f"wrote {args.json}")


if __name__ == "__main__":
    main()
