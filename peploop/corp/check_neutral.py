"""Fail when pepcorp's code or prompt knows which country is being run.

Everything pepcorp knows about one country comes from data: its state and
subdivisions from Wikidata, its languages from rigour, its holdings lists,
legal forms, misfiled classes and extra seats from `countries/<cc>.yml`. The
board vocabulary is translated by the model into a fixed set of roles, so no
country's titles belong in the code. This greps the tokens of every country
run so far, and every QID a country spec names as a form or a misfiled
class, out of `peploop/corp/*.py` and `peploop/corp/prompts/*.md`; the checks
use invented QIDs.

Run it as `python -m peploop.corp.check_neutral` from the repository root.
"""

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
TOKENS = (
    # Germany, the prototype
    "german", "deutsch", "bundes", "länder", "aufsichtsrat", "vorstand", "geschäftsführ", "gmbh", "berlin",
    "de.wikipedia", "landesbank",
)
QIDS = ("Q183",)
#: Every form, misfiled class, party branch class, municipal class and scope's body class a country spec
#: names: spec data, never code. Classes of organisations of states are no one scope's: the global
#: `actors.NOT_GOVERNMENT` names one.
SPEC_QIDS = tuple(sorted({q for path in (Path(__file__).resolve().parent / "countries").glob("*.yml")
                          for key in ("forms", "not_government", "exclude", "party_branch_classes", "municipal_classes",
                                      "body_classes")
                          for q in [str(e["qid"]) for e in (yaml.safe_load(path.read_text()) or {}).get(key) or []]}))
QID_RE = re.compile(r"\b(" + "|".join(QIDS + SPEC_QIDS) + r")\b")
SELF = Path(__file__).name


def files() -> list[Path]:
    found = [path for path in sorted(ROOT.glob("*.py")) if path.name != SELF]
    return found + sorted((ROOT / "prompts").glob("*.md"))


def hits(path: Path) -> list[tuple[int, str, str]]:
    found = []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        folded = line.casefold()
        found.extend((number, token, line.strip()) for token in TOKENS if token in folded)
        found.extend((number, m.group(1), line.strip()) for m in QID_RE.finditer(line))
    return found


def main() -> int:
    checked = files()
    total = 0
    for path in checked:
        for number, token, line in hits(path):
            total += 1
            print(f"{path.relative_to(ROOT.parent)}:{number}: {token!r} in: {line}")
    print(f"{len(checked)} files, {len(TOKENS) + len(QIDS) + len(SPEC_QIDS)} tokens, {total} hits")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
