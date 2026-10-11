"""Fail when the code or the prompt knows which country is being run.

peptree is meant to run on any state, and everything it knows about one comes
from data (`country.config`): the languages from rigour, the predecessors
from rigour and Wikidata, every word a label is read for from a class's
labels. A rule written around one country's language, territory or wiki is a
rule the next country silently breaks. This greps the tokens of every country
already run or queued out of `peploop/tree/*.py` and `peploop/tree/prompts/*.md`, the
checks included (their fixtures use an invented country). The list grows as
countries are added and the hit count stays at zero.

One exception, marked rather than inferred. A prompt teaches by example, and an
example list that names several unrelated states is the opposite of a
country-specific rule; such a line says so by ending with its marker comment.

Run it as `python -m peploop.tree.check_neutral` from the repository root.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# Tokens of the countries peptree has run or is about to. Case is folded
# before the comparison, so each entry is written however it reads best.
TOKENS = (
    # Belarus, the pilot, and its Soviet predecessors
    "belarus", "беларус", "белорус", "białoru", "bielorus", "byelorussia", "bssr", "бсср",
    "soviet", "ussr", "ссср", "minsk", "мінск", "минск", "brest", "брэст", "baranavich", "be.wikipedia",
    "be-tarask", "be_x_old", "выканкам", "исполком", "сельсав", "сельсов", "аблвыканкам",
    # Kazakhstan, Cuba, Iran: queued
    "kazak", "казах", "қазақ", "astana", "cuba", "куба", "havana", "habana", "iran", "иран", "ایران",
    "persia", "pahlavi", "tehran",
)
# Country, predecessor and place-type QIDs, matched as whole words.
QIDS = (
    "Q184", "Q15180", "Q2895", "Q15071808", "Q2043199", "Q209325",
    "Q232", "Q168811", "Q241", "Q14905932", "Q794", "Q107258515", "Q83311",
)
QID_RE = re.compile(r"\b(" + "|".join(QIDS) + r")\b")
# What a line ends with to declare itself a multi-country example list.
MARKERS = {".md": "<!-- examples -->", ".py": "# examples"}
# This file names every token by definition; nothing else may.
SELF = Path(__file__).name


def files() -> list[Path]:
    """List the code and prompt files the rule covers, in a stable order."""
    found = [path for path in sorted(ROOT.glob("*.py")) if path.name != SELF]
    return found + sorted((ROOT / "prompts").glob("*.md"))


def hits(path: Path) -> list[tuple[int, str, str]]:
    """Report every (line number, token, line) a file names a country token on."""
    marker = MARKERS[path.suffix]
    found = []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if line.rstrip().endswith(marker):
            continue
        folded = line.casefold()
        found.extend((number, token, line.strip()) for token in TOKENS if token.casefold() in folded)
        found.extend((number, m.group(1), line.strip()) for m in QID_RE.finditer(line))
    return found


def main() -> int:
    """Print what names a country, and fail if anything does."""
    checked = files()
    total = 0
    for path in checked:
        for number, token, line in hits(path):
            total += 1
            print(f"{path.relative_to(ROOT.parent)}:{number}: {token!r} in: {line}")
    print(f"{len(checked)} files, {len(TOKENS) + len(QIDS)} tokens, {total} hits")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
