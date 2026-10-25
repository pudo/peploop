"""Fail when a country spec does not parse or names a malformed value.

    .venv/bin/python -m peploop.corp.check_country
"""

import re
import sys

from peploop.corp import country
from peploop.checks import expect

QID = re.compile(r"^Q[1-9]\d*$")
PID = re.compile(r"^P[1-9]\d*$")
KINDS = {"enterprise", "institution"}
TIERS = {"national", "regional", "municipal", "international"}


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
        expect(all(QID.match(q) and k in ("state", "government") for q, k in spec.actors.items()),
               f"{cc}: extra actors are QIDs of kind state or government")
        expect(all(PID.match(p) and (q is None or QID.match(q)) for p, q in spec.roles.values()),
               f"{cc}: extra seats map to a property and an optional QID")
        expect(all(QID.match(q) for q in spec.parties), f"{cc}: extra parties are QIDs")
        expect(all(QID.match(q) for q in spec.party_branch_classes), f"{cc}: party branch classes are QIDs")
        expect(all(QID.match(q) for q in spec.municipal_classes), f"{cc}: municipal classes are QIDs")
        expect(all(lang and title and depth >= 0 for lang, title, depth in spec.categories),
               f"{cc}: municipal categories name a wiki and a title")
        expect(all(QID.match(str(e.get("unit") or "")) for e in spec.holdings if e.get("level") == "municipal"),
               f"{cc}: a municipal holding names its unit")
        expect(all(e.get("level") in (None, "municipal") for e in spec.holdings), f"{cc}: holdings levels are known")
        expect(set(spec.tiers) <= TIERS, f"{cc}: tiers are known")
        expect(not spec.international or spec.tiers == ("international",),
               f"{cc}: the international tier stands alone: no state tier beside it")
        expect(all(QID.match(q) for q in spec.body_classes + spec.organisation_classes),
               f"{cc}: international classes are QIDs")
        expect(spec.international == bool(spec.wikis), f"{cc}: an international spec, and only one, names its wikis")
        expect(spec.state is None or bool(QID.match(spec.state)), f"{cc}: the state override is a QID")
    return 0


if __name__ == "__main__":
    sys.exit(main())
