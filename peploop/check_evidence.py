"""Pin what counts as a quote in every lane's gate.

Each case is either something one lane's own gate accepted before the gates
were shared, or something the measurement over stored answers showed matters.

Run it as `python -m peploop.check_evidence` from the repository root.
"""

from peploop.checks import expect
from peploop.evidence import floor, missing, quoted

SHOWN = "Die  ZDF-Holding ist\nim Besitz des Landes.\n原任某市市长，现任省长。 EUROFIMA’s shareholders include railways."


def main() -> None:
    expect(quoted("die zdf-holding ist im besitz", SHOWN), "case and whitespace are forgiven")
    expect(quoted("„im Besitz des Landes.“", SHOWN), "the marks a model wraps a quote in are dropped")
    expect(quoted("EUROFIMA\\u2019s shareholders", SHOWN), "a JSON escape written out literally is decoded")
    expect(quoted("现任省长", SHOWN) and quoted("现任", SHOWN), "two characters of a dense script are a quote")
    expect(floor("现任") == 2 and floor("한국") == 2 and floor("ZDF") == 4, "the floor follows the script")
    expect(quoted("男", "性别：男", min_length=1) and not quoted("男", "性别：男"),
           "one character is a quote only where the lane lowers the floor (a sex)")
    expect(not quoted("ZDF", SHOWN), "three letters are found in any article, so they prove nothing")
    expect(not quoted("im Eigentum des Landes", SHOWN), "a paraphrase is not a quote")
    expect(not quoted(None, SHOWN) and not quoted("", SHOWN), "no quote is no evidence")
    expect(missing(["im Besitz des Landes", "Bundesbesitz", ""], SHOWN) == ["Bundesbesitz", ""],
           "missing lists the quotes the gate refuses, in order")


if __name__ == "__main__":
    main()
