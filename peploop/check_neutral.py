"""Fail when the code or the prompt knows which country is being run.

The pilot is the first of many and will end up a small fraction of what this
tool processes, so a rule written around one country's language, territory or
wiki is a rule the next country silently breaks. This greps the tokens of every
country already run out of `peploop/*.py` and `peploop/prompts/*.md`: the list
grows as countries are added and the hit count stays at zero.

One exception, marked rather than inferred. A prompt teaches by example, and an
example list that names several unrelated languages is the opposite of a
country-specific rule; such a line says so by ending with its marker comment.

Run it as `python -m peploop.check_neutral` from the repository root.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# Tokens of the countries this workbench has run. Case is folded before the
# comparison, so each entry is written however it reads best.
TOKENS = (
    "czech", "česk", "Q213", "Q33946", "Q191168", "cs.wikipedia", "Úřaduj", "Brno", "Praha",
    "sloven", "Q215", "sl.wikipedia", "državn", "Ljubljana", "Maribor",
    "colomb", "Q739", "es.wikipedia", "Bogotá", "Petro",
    "malaysia", "ms.wikipedia", "Kuala Lumpur", "Dewan",  # Q833 is a prefix of Q83307 minister
    "ja.wikipedia", "日本", "Tokyo", "東京", "衆議院",  # Q17 prefixes thousands of QIDs
)
# What a line ends with to declare itself a multi-language example list.
MARKERS = {".md": "<!-- examples -->", ".py": "# examples"}
# This file names every token by definition; nothing else may.
SELF = Path(__file__).name


def files() -> list[Path]:
    """List the code and prompt files the rule covers, in a stable order."""
    found = [path for path in sorted(ROOT.glob("*.py")) if path.name != SELF]
    return found + sorted((ROOT / "prompts").glob("*.md"))


def hits(path: Path) -> list[tuple[int, str, str]]:
    """Report every (line number, token, line) a file names a pilot token on."""
    marker = MARKERS[path.suffix]
    found = []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if line.rstrip().endswith(marker):
            continue
        folded = line.casefold()
        found.extend(
            (number, token, line.strip()) for token in TOKENS if token.casefold() in folded
        )
    return found


def main() -> int:
    """Print what names the pilot, and fail if anything does."""
    checked = files()
    total = 0
    for path in checked:
        for number, token, line in hits(path):
            total += 1
            print(f"{path.relative_to(ROOT.parent)}:{number}: {token!r} in: {line}")
    print(f"{len(checked)} files, {len(TOKENS)} tokens, {total} hits")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
