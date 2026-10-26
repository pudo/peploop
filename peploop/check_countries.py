"""Fail when a country file has an unknown key or names a malformed state, realm or predecessor.

    .venv/bin/python -m peploop.check_countries
"""

import re
import sys

from peploop import countries
from peploop.checks import expect

QID = re.compile(r"^Q[1-9]\d*$")


def main() -> int:
    codes = sorted(p.stem for p in countries.DIR.glob("*.yml") if not p.name.endswith(".amlr.yml"))
    expect(bool(codes), f"{len(codes)} country files found")
    for cc in codes:
        countries.section(cc, "seeds")  # raises on an unknown top-level key
        state, realm = countries.state(cc), countries.realm(cc)
        expect(state is None or bool(QID.match(state)), f"{cc}: the state is a QID")
        expect(realm is None or (bool(QID.match(realm)) and state is not None and realm != state),
               f"{cc}: a realm is a QID around a state the file names")
        expect(all(QID.match(q) for q in countries.not_predecessors(cc)), f"{cc}: every left-out predecessor is a QID")
    return 0


if __name__ == "__main__":
    sys.exit(main())
