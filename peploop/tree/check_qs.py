"""Pin the QuickStatements rendering and the local validation, offline.

    .venv/bin/python -m peploop.tree.check_qs
"""

from peploop import plan, wikipedia
from peploop.tree import qs
from peploop.checks import expect

wikipedia.edition_items = lambda: {"xa": "Q0000101"}


def main() -> None:
    retrieved = plan.today()["time"] + "/11"
    note = " /* [[User:Pudox/PEP|PEP coverage]]: classify a political position and its jurisdiction */"
    rev_url = "https://xa.wikipedia.org/w/index.php?title=X&oldid=7"
    art = {"qid": "Q1", "prop": "P17", "value": "Q900001", "source": "article_xa",
           "articles": {"xa": rev_url}, "disposition": "apply"}
    expect(qs.line(art) == f'Q1\tP17\tQ900001\tS143\tQ0000101\tS4656\t"{rev_url}"\tS813\t{retrieved}' + note,
           "an article-derived value cites as peploop does: the wiki, the revision read, retrieved at /11")
    page = {**art, "articles": {"xa": "https://xa.wikipedia.org/wiki/X"}}
    expect('\tS4656\t"https://xa.wikipedia.org/wiki/X"\t' in qs.line(page),
           "a request stored before revisions were kept cites the page")
    struct = {**art, "source": "label"}
    expect(qs.line(struct) == "Q1\tP17\tQ900001" + note,
           "a structural inference carries no reference, and the summary rides on the last column and names the objective, not the run")
    expect(qs.line({**art, "articles": {}}) == "Q1\tP17\tQ900001" + note,
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
