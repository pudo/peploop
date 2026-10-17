"""Fail when a country spec does not parse or names a malformed value.

    .venv/bin/python -m peploop.corp.check_country
"""

import re
import sys

from peploop.corp import country
from peploop.tree.check_filter import expect

QID = re.compile(r"^Q[1-9]\d*$")
PID = re.compile(r"^P[1-9]\d*$")
KINDS = {"enterprise", "institution"}
TIERS = {"national", "regional", "municipal"}


def main() -> int:
    specs = sorted(p.stem for p in country.DIR.glob("*.yml"))
    expect(bool(specs), f"{len(specs)} country specs found")
    for cc in specs:
        spec = country.get(cc)
        expect(all(QID.match(q) for q in spec.seeded()), f"{cc}: every holding's QID is well-formed")
        expect(all(e.get("name") for e in spec.holdings), f"{cc}: every holding has a name")
        expect(all(QID.match(q) and k in KINDS for q, k in spec.forms.items()), f"{cc}: forms are QIDs with a kind")
        expect(all(QID.match(q) for q in spec.not_government), f"{cc}: misfiled classes are QIDs")
        expect(all(QID.match(q) for q in spec.exclude), f"{cc}: excluded classes are QIDs")
        expect(all(PID.match(p) and (q is None or QID.match(q)) for p, q in spec.roles.values()),
               f"{cc}: extra seats map to a property and an optional QID")
        expect(set(spec.tiers) <= TIERS, f"{cc}: tiers are known")
    return 0


if __name__ == "__main__":
    sys.exit(main())
