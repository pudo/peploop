#!/usr/bin/env python
"""Comment out the PETScan specs `retirable.py` found removable.

    python scripts/retire_specs.py            # dry run, prints the blocks
    python scripts/retire_specs.py --write

Part two of the `wd_categories.yml` PR: part one adds the position classes to
`zavod`, this removes the queries those classes made redundant. A spec is
removable when its target is a position `wd_peps` emits *and* every member either
already holds that position or is someone no PEP dataset would emit anyway —
`coverage/petscan_retirable.md` is the checklist and states the cost per row.

**Commented out, not deleted.** The block stays in the file behind `#` with the
date and the reason on it, because the claim being made is "these people arrive
from their own P39 statements now" and that claim can stop being true: a
retirement is the thing most likely to need reverting, and a diff that deletes 44
blocks gives a reviewer nothing to check against. Restoring one is uncommenting
it.

Text-level editing, and the block finder is imported from
`patch_categories_yml.py` rather than rewritten: the file is hand-curated, with
section comments and rationale notes a YAML round-trip would destroy.
"""

import argparse
import difflib
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from patch_categories_yml import SPEC_RE, YML, block_key, spec_blocks  # noqa: E402

RETIRABLE = REPO_ROOT / "coverage" / "petscan_retirable.json"

#: Specs the checklist calls removable that are **not**, with the reason. Held
#: back here rather than edited out of the JSON, so the next `retirable.py` run
#: does not silently re-propose them and so the reason travels with the PR.
#:
#: Verified per row by replaying `position.py`'s gates — the type gate, the
#: country gate, the IGO registry and the topic default — against the constants
#: in the *working tree's* `position.py`. `retirable.py` establishes that the
#: target emits by a cheaper route, and this is the row where the two disagree.
HOLD_BACK: Dict[str, str] = {
    "ru:Председатели Совета Федерации России":
        "Q4376672 Chairman of the Federation Council does NOT emit: its "
        "`P279 = Q4516946` (member of the Federation Council) is **deprecated**, "
        "so rank-correctly it reaches only `Q1758037` speaker, which confers no "
        "`role.pep`. Retiring this would drop the chair of Russia's upper house. "
        "Fixed by either un-deprecating that P279 on Wikidata (the claim is "
        "true), or by giving `Q1758037` a SUB_TYPES entry — already an open "
        "issue in tasks/followups.md.",
}


def block_extent(lines: List[str], start: int, limit: int) -> int:
    """One past the last line that really belongs to this spec.

    `spec_blocks` ends a block where the *next* one starts, which sweeps up
    whatever sits between them — and in this file that is often a section comment
    belonging to the next spec (`# United Nations system:`) or a blank line.
    Commenting those out would move a heading onto the wrong side of the edit, so
    the tail is trimmed back to the last line that is neither blank nor a
    standalone comment.

    A comment *inside* a block survives, because the walk only stops at a line
    that is non-blank, non-comment and indented no deeper than the `- ` itself.
    """
    dash = len(SPEC_RE.match(lines[start]).group(1))  # type: ignore[union-attr]
    end = start + 1
    while end < limit:
        stripped = lines[end].strip()
        if stripped and not stripped.startswith("#"):
            indent = len(lines[end]) - len(lines[end].lstrip())
            if indent <= dash:
                break
        end += 1
    while end - 1 > start:
        stripped = lines[end - 1].strip()
        if stripped and not stripped.startswith("#"):
            break
        end -= 1
    return end


def reason(row: Dict) -> str:
    """The one line that goes above the commented block."""
    drops = row.get("drops_from_dataset") or 0
    held, members = row.get("held", 0), row.get("members", 0)
    parts = [f"retired {row.get('last_confirmed')}"]
    parts.append(f"{held}/{members} already hold {row['target']}")
    if drops:
        kinds = ", ".join(sorted(row.get("dropped") or {}))
        parts.append(f"{drops} leave the dataset ({kinds})")
    return "; ".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--yml", type=Path, default=YML)
    parser.add_argument("--json", type=Path, default=RETIRABLE)
    args = parser.parse_args()

    rows = {
        r["key"]: r for r in json.loads(args.json.read_text()) if r.get("removable")
        and r["key"] not in HOLD_BACK
    }
    original = args.yml.read_text()
    lines = original.split("\n")

    found: List[Tuple[int, int, str]] = []
    for start, limit in spec_blocks(lines):
        key = block_key(lines, start, limit)
        if key in rows:
            found.append((start, block_extent(lines, start, limit), key))

    missing = sorted(set(rows) - {k for _, _, k in found})
    # Comment from the bottom up so earlier indices stay valid.
    for start, end, key in sorted(found, reverse=True):
        row = rows[key]
        pad = SPEC_RE.match(lines[start]).group(1)  # type: ignore[union-attr]
        body = [
            f"{pad}# {lines[i][len(pad):]}" if lines[i].startswith(pad) else
            f"{pad}# {lines[i].lstrip()}"
            for i in range(start, end)
        ]
        lines[start:end] = [f"{pad}# {reason(row)}"] + body

    patched = "\n".join(lines)
    people = sum(rows[k]["held"] for _, _, k in found)
    drops = sum(rows[k]["drops_from_dataset"] for _, _, k in found)
    print(f"{len(found)} of {len(rows)} removable specs located and commented out")
    print(f"  {people} people already covered by real P39 statements")
    print(f"  {drops} leave the dataset (born before 1920 / not emittable)")
    for key in missing:
        print(f"  NOT FOUND: {key} — already retired, or renamed upstream")
    for key, why in HOLD_BACK.items():
        print(f"  HELD BACK: {key}\n    {why}")

    if args.write:
        args.yml.write_text(patched)
        print(f"wrote {args.yml}")
    else:
        diff = difflib.unified_diff(
            original.split("\n"), patched.split("\n"),
            fromfile=str(args.yml), tofile=str(args.yml) + " (retired)", lineterm="",
        )
        for line in list(diff)[:60]:
            print(line)
        print("... (dry run — pass --write to apply)")


if __name__ == "__main__":
    main()
