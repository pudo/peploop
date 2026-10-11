#!/usr/bin/env python
"""Write resolved `wikidata_id`s back into wd_categories.yml.

    python scripts/patch_categories_yml.py            # dry run, prints diff
    python scripts/patch_categories_yml.py --write

Text-level editing rather than a YAML round-trip: the file is hand-curated,
with section comments and rationale notes that a dump would destroy. Each
spec block is located by its `- category:` line, and `wikidata_id:` is
inserted directly under the position's `name:` — where the specs that
already declare one put it.

Input: data/categories/resolved.json (from render_category_qids.py).
"""

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.http import REPO_ROOT

YML = Path(
    "/Users/pudo/Code/opensanctions/datasets/_wikidata/categories/wd_categories.yml"
)
RESOLVED = REPO_ROOT / "data" / "categories" / "resolved.json"

SPEC_RE = re.compile(r"^(\s*)- category:\s*(.+?)\s*$")
KEY_RE = re.compile(r"^(\s*)([A-Za-z_]+):\s*(.*)$")
# Many of the Russian specs carry a trailing translation comment
# ("- category: Министры Российской Федерации # Ministers of the ...").
COMMENT_RE = re.compile(r"\s+#.*$")


def scalar(text: str) -> str:
    return COMMENT_RE.sub("", text).strip().strip("\"'")


def spec_blocks(lines: List[str]) -> List[Tuple[int, int]]:
    """(start, end) line indices for each `- category:` block."""
    starts = [i for i, line in enumerate(lines) if SPEC_RE.match(line)]
    return [
        (s, starts[i + 1] if i + 1 < len(starts) else len(lines))
        for i, s in enumerate(starts)
    ]


def block_key(lines: List[str], start: int, end: int) -> Optional[str]:
    match = SPEC_RE.match(lines[start])
    if match is None:
        return None
    category = scalar(match.group(2))
    language = "en"
    for line in lines[start:end]:
        m = KEY_RE.match(line)
        if m and m.group(2) == "language":
            language = scalar(m.group(3))
            break
    return f"{language}:{category}"


def position_name_line(lines: List[str], start: int, end: int) -> Optional[int]:
    """Index of the `name:` line inside the block's `position:` mapping —
    None if there is no position block, or it already declares a
    `wikidata_id` (the whole block is scanned first, since `name:` is
    written above `wikidata_id:` in the specs that have one)."""
    in_position = False
    indent = None
    name_at = None
    for i in range(start, end):
        m = KEY_RE.match(lines[i])
        if m is None:
            continue
        pad, key = len(m.group(1)), m.group(2)
        if key == "position":
            in_position, indent = True, pad
            continue
        if in_position:
            if pad <= (indent or 0):
                break  # left the position block
            if key == "wikidata_id":
                return None  # already declared
            if key == "name" and name_at is None:
                name_at = i
    return name_at


def main(argv: List[str]) -> None:
    write = "--write" in argv
    resolved: Dict[str, dict] = {
        r["key"]: r for r in json.load(RESOLVED.open())
    }
    lines = YML.read_text().split("\n")

    edits: List[Tuple[int, str, str]] = []  # (line index, text, key)
    skipped: List[str] = []
    for start, end in spec_blocks(lines):
        key = block_key(lines, start, end)
        row = resolved.get(key or "")
        if row is None or not row.get("qid"):
            continue
        name_at = position_name_line(lines, start, end)
        if name_at is None:
            skipped.append(f"{key} (already declared, or no position name)")
            continue
        pad = KEY_RE.match(lines[name_at]).group(1)  # type: ignore
        edits.append((name_at, f"{pad}wikidata_id: {row['qid']}", key or ""))

    for name_at, text, key in reversed(edits):
        lines.insert(name_at + 1, text)

    print(f"{len(edits)} wikidata_id insertions; {len(skipped)} skipped")
    for note in skipped:
        print(f"  skip: {note}")
    if write:
        YML.write_text("\n".join(lines))
        print(f"wrote {YML}")
    else:
        for name_at, text, key in edits[:15]:
            print(f"  + {text.strip()}   ({key})")
        print("(dry run — pass --write to apply)")


if __name__ == "__main__":
    main(sys.argv[1:])
