"""Pin the English-title channel: the cache, the batching, and what the shortlist does with it.

No key and no request: the model is replaced by a function answering from a
dict. The cache and the search run against temporary tables that shadow
`title_en`, `title_en_call`, `position` and `position_name` on this
connection, so nothing stored is read or written.

What is pinned, and why each would go wrong silently:

* **the key and the batching** -- a title that folds to a cached key is not
  asked again, a batch is at most `BATCH` titles, an id the answer leaves out
  is asked again and an id it invents is dropped;
* **the shortlist** -- a cached English title puts its item first, a cache
  miss is exactly today's lexical search, an item with no English label is
  reached through its English search name, and exact-name promotion reads
  the words in order (an ambassador *of* a state is not the ambassador *to*
  it);
* **what the reconcile model sees does not change** -- the channel is a
  retrieval aid, so the reconcile prompt's hash and `RENDER_VERSION` stay as
  they were and the English title never enters the request. A change to
  either re-asks every recorded verdict.

Run it as `python -m peploop.check_titles` from the repository root.
"""

import hashlib
import sys
from typing import Any, Sequence

import psycopg

from peploop import db, positions, reconcile, titles

#: The reconcile prompt and rendering this channel shipped under. A retrieval
#: change must not move either: the ledger is keyed by them, and moving one
#: re-asks every placed mention.
RECONCILE_PROMPT_SHA256 = "0c8e514fe693abac432180896eb8dd01e6d322d5762017961741a033a37e7490"
RECONCILE_RENDER_VERSION = 2

STATE = "Q1"

SHADOWED = ("title_en", "title_en_call", "position", "position_name")


def shadow(conn: psycopg.Connection) -> None:
    """Create the temporary tables that shadow the real ones on this connection."""
    for table in SHADOWED:
        conn.execute(f"CREATE TEMP TABLE {table} (LIKE public.{table}"
                     " INCLUDING DEFAULTS INCLUDING GENERATED INCLUDING INDEXES)")


def unshadow(conn: psycopg.Connection) -> None:
    for table in SHADOWED:
        conn.execute(f"DROP TABLE IF EXISTS pg_temp.{table}")


def fake_asker(answers: dict[str, str], calls: list[list[str]], drop: Sequence[str] = ()):
    """A model that answers from `answers` by title, leaves out `drop` once, invents id 99."""
    dropped: set[str] = set()

    def ask(batch: Sequence[titles.Title], _model: str) -> tuple[dict[int, str], dict[str, int]]:
        calls.append([item.title for item in batch])
        out = {99: "an id nobody sent"}
        for index, item in enumerate(batch):
            if item.title in drop and item.title not in dropped:
                dropped.add(item.title)
                continue
            out[index] = answers.get(item.title, item.title)
        return out, {"input_tokens": 10, "output_tokens": 5}

    return ask


def add_position(qid: str, names: dict[str, str], aliases: Sequence[tuple[str, str]] = ()) -> None:
    """Insert one synthetic position with its search document built the loader's way."""
    texts = list(names.values()) + [text for _lang, text in aliases]
    label = names.get("en") or names.get("mul") or next(iter(names.values()))
    db.conn().execute(
        "INSERT INTO position (qid, label, country_qid, search_text) VALUES (%s, %s, %s, %s)",
        (qid, label, STATE, " ".join(positions.token_bag(texts))),
    )
    for lang, text in names.items():
        db.conn().execute("INSERT INTO position_name (qid, lang, text) VALUES (%s, %s, %s)",
                          (qid, lang, text))
    for lang, text in aliases:
        db.conn().execute(
            "INSERT INTO position_name (qid, lang, text, alias) VALUES (%s, %s, %s, true)",
            (qid, lang, text))


def check_key(expect: Any) -> None:
    """Pin the cache key and the prompt hash, offline."""
    a = titles.Title("Ministro  de la JUVENTUD ", "Zenda", "es", STATE)
    b = titles.Title("ministro de la juventud", "zenda", "es", STATE)
    expect(a.key == b.key, f"case and spacing fold into one key: {a.key}")
    expect(titles.Title("ministro de la juventud", "Zenda", "pt", STATE).key != a.key,
           "the language is part of the key")
    expect(titles.Title("ministro de la juventud", "Zenda", "es", "Q2").key != a.key,
           "the state is part of the key")
    expect(titles.Title("ministro de la juventud", None, "es", STATE).key != a.key,
           "the jurisdiction is part of the key")
    expect(titles.fold_key("Міністр") != titles.fold_key("Министр"),
           "folding does not transliterate: two scripts stay two keys")
    text, digest = titles.system_prompt()
    expect(digest == hashlib.sha256(titles.PROMPT_PATH.read_bytes()).hexdigest(),
           f"the title prompt hash is the sha256 of the file: {digest[:12]}")
    expect("ambassador of <sending state> to <receiving state>" in text,
           "the prompt keeps the ambassador direction rule")
    rendered = titles.render_batch([titles.Title("Minister\tof X", "Y\nZ", "en", "Q183")])
    expect(rendered == "id\tcountry\ttitle\tjurisdiction\n0\tGermany\tMinister of X\tY Z",
           f"a batch renders as tab-separated rows with the state's name: {rendered!r}")
    answer = titles.TitleAnswer(titles=[
        titles.Entry(id=0, english="Minister of X"), titles.Entry(id=0, english="again"),
        titles.Entry(id=1, english="  "), titles.Entry(id=7, english="invented"),
    ])
    expect(titles.parse_answer(answer, 2) == {0: "Minister of X"},
           "a parsed answer keeps the first name per id, drops empty and out-of-batch ids")


def check_reconcile_unchanged(expect: Any) -> None:
    """Pin that the reconcile model is shown exactly what it was before the channel."""
    _text, digest = reconcile.system_prompt()
    expect(digest == RECONCILE_PROMPT_SHA256,
           f"the reconcile prompt hash is unchanged: {digest[:12]}")
    expect(reconcile.RENDER_VERSION == RECONCILE_RENDER_VERSION,
           f"RENDER_VERSION is unchanged: {reconcile.RENDER_VERSION}")
    mention = reconcile.Mention(title="Ministro de la Juventud", lang="es")
    request = reconcile.request_for(mention, [])
    content = request["messages"][0]["content"]
    expect("Ministro de la Juventud" in content and "Minister of Youth" not in content,
           "the model reads the title as written, never its English search name")


def check_translate(expect: Any) -> None:
    """Pin batching, resumption and re-asking against the shadowed cache."""
    items = [titles.Title(f"Office {n}", None, "es", STATE) for n in range(60)]
    items.append(titles.Title("office 3", None, "es", STATE))  # folds onto "Office 3"
    calls: list[list[str]] = []
    asker = fake_asker({}, calls, drop=("Office 7",))
    stats = titles.translate(items, threads=1, asker=asker)
    sizes = [len(call) for call in calls]
    expect(stats["titles"] == 60, f"titles are de-duplicated by key: {stats['titles']}")
    expect(sizes == [25, 25, 10, 1],
           f"batches of {titles.BATCH}, then the left-out title alone: {sizes}")
    expect(calls[-1] == ["Office 7"], "the id the answer left out is asked again")
    expect(stats["answered"] == 60 and stats["missing"] == 0,
           f"every title is answered by the end: {stats}")
    stored = db.conn().execute("SELECT count(*) FROM title_en").fetchone()[0]
    expect(stored == 60, f"an invented id stores nothing: {stored} rows")
    expect(titles.cached(titles.Title("OFFICE 12", None, "es", STATE)) == "Office 12",
           "a cached title is read back under its folded key")
    calls.clear()
    again = titles.translate(items, threads=1, asker=asker)
    expect(not calls and again["cached"] == 60,
           "a re-run asks nothing: translations are cached once")
    calls_row = db.conn().execute(
        "SELECT count(*), sum(titles), sum((usage_json->>'input_tokens')::int)"
        " FROM title_en_call").fetchone()
    expect(tuple(calls_row) == (4, 61, 40), f"every request's usage is recorded: {calls_row}")


def check_shortlist(expect: Any) -> None:
    """Pin the two-channel shortlist against a synthetic shadowed table."""
    # Twenty sibling ministries the title as written reaches only through the
    # "minist" prefix, and which sort before the gold on the text index's tie.
    portfolios = ("Defence", "Finance", "Health", "Labour", "Justice", "Trade",
                  "Culture", "Energy", "Tourism", "Transport", "Housing", "Agriculture",
                  "Education", "Environment", "Interior", "Planning", "Sport",
                  "Fisheries", "Mines", "Water")
    for n, portfolio in enumerate(portfolios):
        add_position(f"Q1{n:02d}", {"en": f"Minister of {portfolio} of Ruritania"})
    gold = "Q900"
    add_position(gold, {"en": "Minister of Youth of Ruritania"})
    mention = reconcile.Mention(title="Ministro de la Juventud", jurisdiction="Ruritania",
                                lang="es")
    lexical = [h.qid for h in positions.search(
        reconcile.search_title(mention.title), mention.jurisdiction, STATE,
        limit=reconcile.SHORTLIST)]
    miss = [h.qid for h in reconcile.shortlist_hits(mention, STATE)]
    expect(gold not in lexical, "the gold is off the lexical fifteen")
    expect(miss == lexical, "a cache miss is exactly the lexical shortlist")
    titles.translate([titles.Title(mention.title, mention.jurisdiction, "es", STATE)],
                     threads=1,
                     asker=fake_asker({mention.title: "Minister of Youth of Ruritania"}, []))
    hit = [h.qid for h in reconcile.shortlist_hits(mention, STATE)]
    expect(hit[:1] == [gold], f"a cached English title puts the gold first: {hit[:3]}")
    expect(len(hit) == reconcile.SHORTLIST and set(lexical) - set(hit) <= set(lexical[-5:]),
           "the lexical channel fills the rest, keeping its own order")

    # An office labelled only in the state's language: no English title reaches it.
    unlabelled = "Q950"
    add_position(unlabelled, {"xx": "Ylimmäinen kaupunginjohtaja Zendalinna"})
    english = "chairman of the Zenda City Executive Committee"
    other = reconcile.Mention(title="Chairman of the Zenda City Executive Committee", lang="en")
    titles.translate([titles.Title(other.title, None, "en", STATE)], threads=1,
                     asker=fake_asker({other.title: english}, []))
    before = [h.qid for h in reconcile.shortlist_hits(other, STATE)]
    found = titles.item_titles(state_qid=STATE)
    titles.refresh_items(found, threads=1,
                         asker=fake_asker({"Ylimmäinen kaupunginjohtaja Zendalinna": english}, []))
    after = [h.qid for h in reconcile.shortlist_hits(other, STATE)]
    expect(list(found) == [unlabelled], f"only the item with no en/mul label is translated: {list(found)}")
    expect(unlabelled not in before and after[:1] == [unlabelled],
           f"an unlabelled item is reached through its English search name: {after[:3]}")
    shown = db.conn().execute(
        "SELECT count(*) FROM position_name WHERE qid = %s", (unlabelled,)).fetchone()[0]
    expect(shown == 1, "the English search name is not a name the item carries")

    # Direction: the sending state comes first, and a set match would ignore it.
    wrong, right, named = "Q960", "Q961", "Q962"
    add_position(wrong, {"en": "ambassador of Zembla to Ruritania"})
    add_position(right, {"en": "Ruritanian Ambassador to Zembla"})
    add_position(named, {"en": "ambassador of Ruritania to Zembla"})
    hits = [positions.Hit(qid=q, name="", lang="", score=0.0) for q in (right, wrong)]
    promoted = [h.qid for h in positions.promote_exact(hits, "ambassador of Ruritania to Zembla")]
    expect(promoted == [right, wrong],
           "the reverse-direction ambassador is not promoted as an exact name")
    hits.append(positions.Hit(qid=named, name="", lang="", score=0.0))
    promoted = [h.qid for h in positions.promote_exact(hits, "Ambassador of Ruritania to Zembla")]
    expect(promoted[0] == named, "the same words in the same order are promoted")


def main() -> int:
    """Run every pin and report."""
    failures: list[str] = []

    def expect(condition: bool, message: str) -> None:
        print(("  ok   " if condition else "  FAIL ") + message)
        if not condition:
            failures.append(message)

    print("key:")
    check_key(expect)
    print("reconcile unchanged:")
    check_reconcile_unchanged(expect)
    try:
        conn = db.conn()
    except psycopg.OperationalError as exc:
        print(f"  skip no database ({exc.__class__.__name__})")
    else:
        for name, check in (("translate", check_translate), ("shortlist", check_shortlist)):
            print(f"{name}:")
            shadow(conn)
            try:
                check(expect)
            finally:
                unshadow(conn)
    print(f"{len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
