#!/usr/bin/env python
"""Fold the verification-agent verdicts into the second-pass IGO link plan.

    python scripts/render_igo_verdicts.py

Reads data/igo/igo_link_candidates.json (mechanical candidates; auto rows
carry two agreeing signals) and data/igo/verdicts2/chunk_*_verdicts.jsonl
(one LLM verdict per review row: link / registry / diplomatic / reject /
unclear, with evidence). Writes the decided plan and REGENERATES the two
QuickStatements batches so they hold auto + verified-link rows — one
property per batch, additive-only. Rerunning igo_link_candidates.py
overwrites the .qs with auto-only rows again; rerun this script after.
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.http import REPO_ROOT

OUT_DIR = REPO_ROOT / "data" / "igo"
VDIR = OUT_DIR / "verdicts2"

# Proposed zavod igo.py country codes for the registry-expansion leads.
LEAD_CODES = {
    "Q8896": "eu",  # Council of the European Union
    "Q331024": "eu",  # European Economic and Social Committee
    "Q2362881": "zz",  # African Union Commission
    "Q81299": "zz",  # OSCE
    "Q2671637": "un",  # UN DESA
    "Q7157377": "zz",  # Peace Implementation Council
    "Q5327657": "zz",  # East African Legislative Assembly
    "Q47472719": "zz",  # IOC Ethics Commission (poi topics)
}


def main() -> None:
    data = json.loads((OUT_DIR / "igo_link_candidates.json").read_text())
    candidates = {c["qid"]: c for c in data["candidates"]}
    auto = [c for c in data["candidates"] if c["auto"]]
    registry = json.loads((VDIR / "registry.json").read_text())

    verdicts: dict[str, dict] = {}
    for path in sorted(VDIR.glob("chunk_*_verdicts.jsonl")):
        for line in path.read_text().splitlines():
            if line.strip():
                v = json.loads(line)
                verdicts[v["qid"]] = v

    review_qids = {c["qid"] for c in data["candidates"] if not c["auto"]}
    if review_qids != set(verdicts):
        raise SystemExit(
            f"verdict coverage mismatch: missing={sorted(review_qids - set(verdicts))} "
            f"extra={sorted(set(verdicts) - review_qids)}"
        )
    for v in verdicts.values():
        if v["verdict"] == "link":
            assert v["org"] in registry, f"{v['qid']} links non-registry org {v['org']}"
            assert v["property"] in ("P2389", "P361"), v

    def holders(qid: str) -> int:
        return candidates.get(qid, {}).get("holders", 0)

    by = {k: [] for k in ("link", "registry", "diplomatic", "reject", "unclear")}
    for v in verdicts.values():
        by[v["verdict"]].append(v)
    for rows in by.values():
        rows.sort(key=lambda v: -holders(v["qid"]))

    lines = [
        "# IGO org-link plan, second pass — decided",
        "",
        "Mechanical candidates from `scripts/igo_link_candidates.py`; every",
        "review row judged by a verification agent against the item's real",
        "claims (verdicts in `data/igo/verdicts2/`). The `.qs` batches hold",
        "the auto rows plus the verified links; everything else is recorded",
        "below. Counts: "
        + ", ".join(f"{k} {len(rows)}" for k, rows in by.items())
        + f", auto {len(auto)}.",
        "",
        f"## Batch: auto rows ({len(auto)}; two agreeing mechanical signals)",
        "",
    ]
    for c in auto:
        lines.append(
            f"* {c['qid']} “{c['label']}” ({c['holders']} holders) → "
            f"{c['property']} {c['signals']['tail'][0]}"
        )

    lines += ["", f"## Batch: verified links ({len(by['link'])}; mechanical signal + agent verdict)", ""]
    for v in by["link"]:
        lines.append(
            f"* {v['qid']} “{v['label']}” ({holders(v['qid'])} holders) → "
            f"{v['property']} {v['org']} {registry[v['org']]} — {v['evidence']}"
        )

    lines += [
        "",
        "## Registry expansion leads (real international offices; org not in igo.py)",
        "",
        "Adding the org to zavod's registry is the first step; the follow-up",
        "P2389/P361 statements below are NOT in the `.qs` batches (they'd",
        "point at orgs zavod doesn't know yet).",
        "",
    ]
    for v in by["registry"]:
        code = LEAD_CODES.get(v.get("org", ""), "??")
        lines.append(
            f"* {v['qid']} “{v['label']}” ({holders(v['qid'])} holders) → org "
            f"{v.get('org')} (proposed code `{code}`) — {v.get('note') or v['evidence']}"
        )
    lines += [
        "",
        "Also from the sub-org sweep (already linked on Wikidata, so they",
        "enroll as soon as the org joins the registry): Q2983826 College of",
        "Commissioners (42 positions, `eu`), NATO organs Q944947 / Q1432908 /",
        "Q1959817 / Q2001035 / Q55858714 (`zz`), Q2735723 Committee of",
        "Ministers of the CoE (`zz`), Q4398720 Secretariat of the European",
        "Parliament (`eu`), Q130417640 EU Delegation (`eu`).",
        "",
        f"## Diplomatic accreditation posts ({len(by['diplomatic'])}; no org link — sending-state positions)",
        "",
    ]
    for v in by["diplomatic"]:
        lines.append(f"* {v['qid']} “{v['label']}” ({holders(v['qid'])} holders)")

    lines += ["", f"## Rejected ({len(by['reject'])})", ""]
    for v in by["reject"]:
        lines.append(
            f"* {v['qid']} “{v['label']}” — {v.get('note') or v['evidence']}"
        )

    lines += ["", f"## Unclear ({len(by['unclear'])})", ""]
    for v in by["unclear"]:
        lines.append(f"* {v['qid']} “{v['label']}” — {v.get('note') or v['evidence']}")

    plan_path = OUT_DIR / "igo_links2_decided.md"
    plan_path.write_text("\n".join(lines) + "\n")
    print(f"Wrote {plan_path}", file=sys.stderr)

    statements: dict[str, list[tuple[str, str]]] = {"P2389": [], "P361": []}
    for c in auto:
        statements[c["property"]].append((c["qid"], c["signals"]["tail"][0]))
    for v in by["link"]:
        statements[v["property"]].append((v["qid"], v["org"]))
    for prop, rows in statements.items():
        qs_path = OUT_DIR / f"igo_links2_{prop.lower()}.qs"
        qs_path.write_text("\n".join(f"{q}|{prop}|{org}" for q, org in rows) + "\n")
        print(f"Wrote {qs_path} ({len(rows)} statements)", file=sys.stderr)

    print(Counter(v["verdict"] for v in verdicts.values()), file=sys.stderr)


if __name__ == "__main__":
    main()
