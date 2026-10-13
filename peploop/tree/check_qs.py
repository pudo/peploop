"""Pin the QuickStatements rendering and the local validation, offline.

    .venv/bin/python -m peploop.tree.check_qs
"""

from peploop.tree import qs
from peploop.tree.check_filter import expect


def main() -> None:
    retrieved = "+2026-10-04T00:00:00Z/11"
    note = " /* [[User:Pudox/PEP|PEP coverage]]: classify a political position and its jurisdiction */"
    art = {"qid": "Q1", "prop": "P17", "value": "Q900001", "source": "article_xa",
           "articles": {"xa": "https://xa.wikipedia.org/wiki/X"}, "disposition": "apply"}
    expect(qs.line(art, retrieved) == 'Q1\tP17\tQ900001\tS854\t"https://xa.wikipedia.org/wiki/X"\tS813\t'
           '+2026-10-04T00:00:00Z/11' + note, "an article-derived value carries S854 + S813 at /11")
    struct = {**art, "source": "label"}
    expect(qs.line(struct, retrieved) == "Q1\tP17\tQ900001" + note,
           "a structural inference carries no reference, and the summary rides on the last column and names the objective, not the run")
    expect(qs.line({**art, "articles": {}}, retrieved) == "Q1\tP17\tQ900001" + note,
           "an article source with no article URL degrades to no reference")
    lines = qs.render([art, art, {**art, "disposition": "skip", "qid": "Q2"}])
    expect(len(lines) == 1, "skips are not rendered and duplicates collapse")
    errs = qs.validate(["Q1\tP17\tQ900001 /* peptree repair xx 2026-10-04 */", "Q1\tP17\tQ900003 /* peptree repair xx 2026-10-04 */"])
    expect(len(errs) == 1 and "second P17" in errs[0], "two values for one single-valued property are refused")
    expect(qs.validate(["Q1\tP279\tQ5 /* peptree repair xx 2026-10-04 */", "Q1\tP279\tQ6 /* peptree repair xx 2026-10-04 */"]) == [],
           "two P279 additions on one item are allowed")
    expect(qs.validate(["Q1\tP17"]) != [], "a malformed line is refused")
    expect(qs.validate(["-Q1\tP17\tQ900001"]) != [], "a removal is refused")


if __name__ == "__main__":
    main()
