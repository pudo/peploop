#!/usr/bin/env python
"""Normalize the held-back diplomatic verdicts into a P17/P137 edit plan.

    python scripts/render_diplomatic_plan.py

Implements the diplomatic-post convention, measured empirically on the
curated bilateral-post cluster (the method is `recipes/country_sweep.md` §10):
  P17  = receiving state   (262/264 on subclasses of Q29645886)
  P137 = sending state     (operator, as on the curated exemplars)
  P1001 is not asserted    (doubled-P1001 is minority practice, 35/264, and a
                            single value would take a side the community
                            hasn't — its "applies to jurisdiction" reading is
                            legitimately sender *or* receiver).

Sender and receiver are re-derived *mechanically* from the label; the
classifier verdicts serve only as a cross-check. Rows where the mechanical
receiver and the classifier's country agree go into the .qs batch; city-named
consulates, org representatives ("to the United Nations"), disagreements and
unparseable labels go to review sections in the .md.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rigour.territories import get_territories

from wd.http import REPO_ROOT, make_session

BASE = REPO_ROOT / "data" / "jurisdictions"
HOLY_SEE = "Q159583"

PATTERNS = [
    # (regex, sender_group, receiver_group, fixed_sender)
    # Nuncio labels come with typos (Nunco, auncio), plurals and to/in variants:
    (re.compile(r"^apostolic (?:pro-)?(?:nuncios?|nunco|auncio) (?:to|in) (?:the )?(.+)$", re.I), None, 1, HOLY_SEE),
    (re.compile(r"^ambassador (?:of|from) (?:the )?(.+?) (?:to|in) (?:the )?(.+)$", re.I), 1, 2, None),
    (re.compile(r"^high commissioner of (?:the )?(.+?) to (?:the )?(.+)$", re.I), 1, 2, None),
    (re.compile(r"^(.+?) ambassador to (?:the )?(.+)$", re.I), 1, 2, None),
    (re.compile(r"^consul(?:ate)?[- ]general of (?:the )?(.+?) (?:in|at) (?:the )?(.+)$", re.I), 1, 2, None),
    (re.compile(r"^consul général de (?:la )?(.+?) à (.+)$", re.I), 1, 2, None),
    (re.compile(r"^consul of (?:the )?(.+?) (?:in|at) (?:the )?(.+)$", re.I), 1, 2, None),
    (re.compile(r"^permanent representative of (?:the )?(.+?) to (?:the )?(.+)$", re.I), 1, 2, None),
]

# Receivers that are organizations, not states: never assert P17; the sender
# (P137) is still safe. Kept for a dedicated review section.
ORG_RECEIVERS = {
    "united nations", "nato", "european union", "african union", "osce",
    "unesco", "council of europe", "organization of american states", "un",
    "oecd", "organisation for economic co-operation and development",
    "international atomic energy agency", "asian development bank",
    "african development bank", "world trade organization", "arab league",
    "organization of the petroleum exporting countries", "caricom",
}

# The Holy See (Q159583) and Vatican City (Q237) are distinct items but the
# same jurisdiction for agreement purposes; normalize to the Holy See.
HOLY_SEE_ALIASES = {"Q159583", "Q237"}


def territory_index() -> dict[str, tuple[str, str]]:
    index: dict[str, tuple[str, str]] = {}
    for t in get_territories():
        if not t.is_country or t.is_historical or t.qid is None:
            continue
        for name in {t.name, t.full_name}:
            if name:
                index[name.casefold()] = (t.code, t.qid)
    index["holy see"] = ("va", HOLY_SEE)
    # Names that appear in diplomatic labels but aren't rigour's primary names;
    # without these the city-resolver finds e.g. Palestine, Texas.
    index.setdefault("palestine", ("ps", "Q219060"))
    return index


def resolve(name: str | None, index: dict) -> tuple[str, str] | None:
    if not name:
        return None
    key = name.strip().rstrip(".").casefold()
    # Trailing parentheticals: "China (PRC)" etc.
    key = re.sub(r"\s*\(.*\)$", "", key)
    return index.get(key)


def resolve_city_country(session, city: str) -> str | None:
    """Country QID of a city, via the top Wikidata search hit's P17.

    Cities carry historical P17 values (London → Kingdom of England, ...), so
    prefer preferred-rank statements, then statements without an end-time
    qualifier; only an unambiguous survivor is returned.
    """
    from wd.api import fetch_entities
    from wd.http import get_text

    raw = get_text(
        session,
        "https://www.wikidata.org/w/api.php",
        params={
            "action": "wbsearchentities", "format": "json", "type": "item",
            "language": "en", "limit": "1", "search": city,
        },
    )
    results = json.loads(raw).get("search", [])
    if not results:
        return None
    entities = fetch_entities(session, [results[0]["id"]], props="claims")
    for entity in entities.values():
        claims = [
            c for c in entity.get("claims", {}).get("P17", [])
            if c.get("rank") != "deprecated"
            and "id" in c.get("mainsnak", {}).get("datavalue", {}).get("value", {})
        ]
        preferred = [c for c in claims if c.get("rank") == "preferred"]
        current = [c for c in claims if "P582" not in c.get("qualifiers", {})]
        for pool in (preferred, current, claims):
            values = {c["mainsnak"]["datavalue"]["value"]["id"] for c in pool}
            if len(values) == 1:
                return values.pop()
    return None


def main() -> None:
    index = territory_index()
    candidates = {
        p["qid"]: p
        for p in json.loads((BASE / "label_country_candidates.json").read_text())
    }
    rows = []
    for path in sorted(BASE.glob("verdicts/chunk_*.jsonl")):
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            v = json.loads(line)
            if v.get("kind") == "diplomatic" and v["verdict"] == "fix-current":
                v["holders"] = candidates.get(v["qid"], {}).get("holders", 0)
                rows.append(v)

    session = make_session()
    auto, disagree, org_rows, unresolved, unparsed = [], [], [], [], []
    qs = []
    for v in rows:
        # Strip direction marks and zero-width chars that sneak into labels:
        label = re.sub(r"[​‎‏]", "", v["label"]).strip()
        parsed = None
        for regex, sg, rg, fixed_sender in PATTERNS:
            m = regex.match(label)
            if m:
                sender = ("va", HOLY_SEE) if fixed_sender else None
                if sender is None and sg is not None:
                    sender = resolve(m.group(sg), index)
                receiver = resolve(m.group(rg), index)
                parsed = (sender, receiver, m.group(rg))
                break
        if parsed is None:
            unparsed.append(v)
            continue
        sender_hit, receiver, receiver_text = parsed
        sender_code, sender_qid = sender_hit if sender_hit else (None, None)
        receiver_qid = receiver[1] if receiver else None

        if receiver_qid is None:
            key = receiver_text.strip().rstrip(".").casefold().removeprefix("the ")
            if key in ORG_RECEIVERS:
                # Org representative: no P17; the sender operator is still true.
                v["derived"] = {"sender": sender_qid, "receiver": None}
                org_rows.append(v)
                if sender_qid:
                    qs.append(f"{v['qid']}\tP137\t{sender_qid}")
                continue
            # Probably a city: resolve via the city item's own P17, and only
            # trust it when it agrees with the classifier's suggestion.
            receiver_qid = resolve_city_country(session, receiver_text)
            v["receiver_text"] = receiver_text
            if receiver_qid is None:
                unresolved.append(v)
                continue

        v["derived"] = {"sender": sender_qid, "receiver": receiver_qid}
        classifier_qid = v.get("country_qid")
        holy_match = (
            receiver_qid in HOLY_SEE_ALIASES and classifier_qid in HOLY_SEE_ALIASES
        )
        # Some classifier chunks used the sender as the jurisdiction (the
        # inconsistency that parked this batch). When the classifier's pick
        # is the parsed sender, it carries no receiver information — the
        # label-derived receiver stands. Codes compared as well as QIDs so
        # country-item variants (Netherlands vs Kingdom of the Netherlands)
        # still register as "chose the sender".
        chose_sender = sender_qid is not None and (
            classifier_qid == sender_qid or v.get("country_code") == sender_code
        )
        if classifier_qid == receiver_qid or holy_match or chose_sender:
            if holy_match:
                v["derived"]["receiver"] = receiver_qid = HOLY_SEE
            v["override"] = chose_sender and classifier_qid != receiver_qid
            auto.append(v)
            qs.append(f"{v['qid']}\tP17\t{receiver_qid}")
            if sender_qid:
                qs.append(f"{v['qid']}\tP137\t{sender_qid}")
        else:
            disagree.append(v)

    md = [
        "# Diplomatic P17/P137 edit plan",
        "",
        f"{len(rows)} diplomatic fix-current verdicts: "
        f"{len(auto)} auto (label & classifier agree), {len(disagree)} disagreements, "
        f"{len(org_rows)} org representatives (P137 only), "
        f"{len(unresolved)} unresolved receivers, {len(unparsed)} unparsed labels",
        "",
        "## auto (in .qs)",
    ]
    for v in sorted(auto, key=lambda v: -v["holders"]):
        d = v["derived"]
        md.append(
            f"* {v['qid']} **{v['label']}** — P17 {d['receiver']}"
            + (f", P137 {d['sender']}" if d["sender"] else "")
            + f" ({v['holders']} holders)"
            + ("  ⟵ label receiver over classifier's sender pick" if v.get("override") else "")
        )
    md.append("\n## disagreements (label-derived vs classifier — review)")
    for v in sorted(disagree, key=lambda v: -v["holders"]):
        md.append(
            f"* {v['qid']} {v['label']} — label→{v['derived']['receiver']} "
            f"vs classifier→{v.get('country_qid')} ({v['holders']} holders): {v.get('reason')}"
        )
    md.append("\n## org representatives (P137 sender in .qs, no P17)")
    for v in sorted(org_rows, key=lambda v: -v["holders"]):
        md.append(
            f"* {v['qid']} {v['label']} — P137 {v['derived']['sender'] or '-'} "
            f"({v['holders']} holders)"
        )
    md.append("\n## unresolved receivers (review)")
    for v in sorted(unresolved, key=lambda v: -v["holders"]):
        md.append(
            f"* {v['qid']} {v['label']} — receiver text {v['receiver_text']!r}, "
            f"classifier suggested {v.get('country_qid')} ({v['holders']} holders)"
        )
    md.append("\n## unparsed labels (review)")
    for v in sorted(unparsed, key=lambda v: -v["holders"]):
        md.append(f"* {v['qid']} {v['label']} — classifier suggested {v.get('country_qid')} ({v['holders']} holders)")

    (BASE / "diplomatic_plan.md").write_text("\n".join(md) + "\n")
    (BASE / "diplomatic_plan.qs").write_text("\n".join(qs) + "\n")
    # The tail the mechanics couldn't handle, as input for an LLM pass:
    (BASE / "diplomatic_unparsed.json").write_text(
        json.dumps(unparsed + unresolved, indent=1, ensure_ascii=False)
    )
    print(
        f"{len(rows)} diplomatic verdicts → auto {len(auto)} ({len(qs)} QS lines), "
        f"disagree {len(disagree)}, city/org {len(unresolved)}, unparsed {len(unparsed)}"
    )
    print(f"holders covered by auto rows: {sum(v['holders'] for v in auto)}")
    print(f"Wrote {BASE / 'diplomatic_plan.md'} and {BASE / 'diplomatic_plan.qs'}")


if __name__ == "__main__":
    main()
