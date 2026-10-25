"""Ask the model about each kept enterprise, one request each, answers kept by content.

A request shows the item's statements, its ownership chain, the indexed
candidate controllers and the enterprise's articles in the country's languages
and English. The answer says what the enterprise is, who controls it and who
sits in its leading bodies, each with a verbatim quote. The ledger
(`pcorp_call`) is keyed by a hash of model, prompt and message, so a re-run pays
only for enterprises whose material changed.

A party (the `party` and `party_branch` lanes) is asked with its own prompt,
`prompts/decide_party.md`: what it is and who sits in its executive organs,
and no control question. Its answer is a `PartyAnswer`; the two prompts
never share a key, so neither's change re-asks the other's bodies.
"""

import os
from pathlib import Path
from typing import Any, Callable, Literal, Optional
from urllib.parse import quote, unquote

import requests
from lxml import html as lxml_html
from pydantic import BaseModel, ConfigDict

from peploop import db, http, llm, memo, positions, wikidata, wikipedia
from peploop.corp import actors as actormod
from peploop.corp import country as countries
from peploop.corp import load as loadmod
from peploop.corp import wd

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "decide.md"
PARTY_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "decide_party.md"
MODEL = os.environ.get("PEPCORP_MODEL", "claude-sonnet-5-5")
MAX_TOKENS = 16000
WORKERS = int(os.environ.get("PEPCORP_WORKERS", "6"))
ARTICLE_MAX_AGE = "30 days"
#: Characters of one article shown; a long history section is cut, not the lead and infobox.
ARTICLE_CHARS = 60_000
SHOWN_PROPS = ("P31", "P1454", "P127", "P749", "P17", "P571", "P576", "P169", "P488", "P3320", "P1037")
#: A party's statements shown: what it is part of, and its leadership as recorded.
PARTY_PROPS = ("P31", "P17", "P571", "P576", "P361", "P749", "P488", "P3975", "P3320")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Owner(Strict):
    relation: Literal["owner", "parent"]
    controller: Optional[int]
    name: Optional[str]
    quote: str
    article: str


class Control(Strict):
    verdict: Literal["state", "private", "unclear", "unstated"]
    level: Literal["national", "regional", "municipal", "foreign", "none"]
    quote: Optional[str]
    article: Optional[str]
    ended: Optional[str]
    owners: list[Owner]


class Seat(Strict):
    name: str
    body: Literal["executive", "supervisory", "board"]
    role: Literal["head", "chair", "deputy_chair", "member", "managing_director", "party_secretary"]
    start: Optional[str]
    end: Optional[str]
    current: bool
    quote: str
    article: str


class Answer(Strict):
    kind: Literal["enterprise", "institution", "government", "other"]
    statutory: Optional[Literal["broadcaster", "central_bank", "regulator"]]
    active: bool
    control: Control
    seats: list[Seat]
    notes: str


class PartySeat(Strict):
    name: str
    role: Literal["chair", "deputy_chair", "secretary_general", "treasurer", "member"]
    start: Optional[str]
    end: Optional[str]
    current: bool
    quote: str
    article: str


class PartyAnswer(Strict):
    kind: Literal["party", "regional_branch", "local_branch", "other"]
    active: bool
    seats: list[PartySeat]
    notes: str


def system_prompt(path: Path = PROMPT_PATH) -> tuple[str, str]:
    return llm.system_prompt(path)


def is_party(item: dict[str, Any]) -> bool:
    """Whether a loaded body is asked as a party: it came in by a party lane."""
    return bool(set(item.get("lanes") or ()) & set(loadmod.PARTY_LANES))


def party_wikis(entity: dict[str, Any], wikis: list[str]) -> list[str]:
    """The wikis a party is read in: the country's own languages, English only where none has an article.

    A party's English article mostly retells its own-language one, at twice
    the cost of a request.
    """
    own = [w for w in wikis if w != "en" and f"{w}wiki" in entity.get("sitelinks", {})]
    return own or ["en"]


# --- articles ---------------------------------------------------------------------

def fetch_articles(qid: str, entity: dict[str, Any], wikis: list[str]) -> list[dict[str, Any]]:
    """The enterprise's articles in these languages, read again when older than a month."""
    links = entity.get("sitelinks", {})
    fresh = {r[0] for r in db.conn().execute(
        f"SELECT lang FROM article WHERE qid = %s AND fetched_at > now() - interval '{ARTICLE_MAX_AGE}'", (qid,))}
    html: dict[str, str] = {}
    for lang in wikis:
        site = links.get(f"{lang}wiki")
        if site is None or lang in fresh:
            continue
        article = wikipedia.fetch_article(lang, site["title"])
        landed = article["redirect"]
        if landed and wikipedia.page_item(lang, landed) != qid:
            continue
        db.upsert_article(qid, lang, site["title"], article["rev_id"], article["url"],
                          wikipedia.html_to_text(article["html"]))
        html[lang] = article["html"]
    rows = db.conn().execute("SELECT lang, title, rev_id, url, text FROM article WHERE qid = %s", (qid,)).fetchall()
    # The page just read is kept for its links, so they cost no second fetch.
    found = {r[0]: {"lang": r[0], "title": r[1], "rev": r[2], "url": r[3], "text": r[4], "html": html.get(r[0])}
             for r in rows}
    return [found[lang] for lang in wikis if lang in found and f"{lang}wiki" in links]


def article_links(articles: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    """lang → {name: QID}: how a seat's or an owner's name is resolved to an item.

    A name is a linked page's title or the text the article links it under,
    so a name the article writes inflected ("Ministerstwu Infrastruktury",
    "Janem Kowalskim") resolves through its link as well as one in the title's
    form. An anchor text the article links to two different items is left out.
    """
    return {a["lang"]: names_linked(a["lang"], a["title"], a.get("html")) for a in articles}


def names_linked(lang: str, title: str, html: str | None = None) -> dict[str, str]:
    html = html or wikipedia.fetch_article(lang, title)["html"]
    return link_names(html, lambda titles: page_items(lang, titles))


def link_names(html: str, resolve: Callable[[list[str]], dict[str, str]]) -> dict[str, str]:
    """{title or anchor text: QID} of a Parsoid page's article links, titles resolved by `resolve`."""
    root = lxml_html.fromstring(html)
    anchors: list[tuple[str, str]] = []
    for a in root.iter("a"):
        href = a.get("href") or ""
        if ("mw:WikiLink" not in (a.get("rel") or "") or not href.startswith("./")
                or "redlink=1" in href or "new" in (a.get("class") or "").split()):
            continue  # a red link names no item
        target = unquote(href[2:].split("#")[0].split("?")[0]).replace("_", " ")
        if target:
            anchors.append((target, " ".join(a.text_content().split())))
    items = resolve(sorted({t for t, _ in anchors}))
    out = dict(items)
    by_text: dict[str, set[str]] = {}
    for target, text in anchors:
        if target in items and text:
            by_text.setdefault(text, set()).add(items[target])
    for text, qids in by_text.items():
        if len(qids) == 1:
            out.setdefault(text, next(iter(qids)))
    return out


def title_chunks(titles: list[str], most: int = 50, length: int = 6000) -> list[list[str]]:
    """Titles in batches the API takes: at most `most`, and short enough once percent-encoded (Cyrillic or Greek take six bytes a letter)."""
    chunks: list[list[str]] = [[]]
    size = 0
    for title in titles:
        n = len(quote(title)) + 3
        if chunks[-1] and (len(chunks[-1]) >= most or size + n > length):
            chunks.append([])
            size = 0
        chunks[-1].append(title)
        size += n
    return [c for c in chunks if c]


def page_items(lang: str, titles: list[str]) -> dict[str, str]:
    """Article title → QID for these titles, a redirect's title included; other namespaces left out."""
    api = f"https://{lang}.wikipedia.org/w/api.php"
    out: dict[str, str] = {}
    for chunk in title_chunks(titles):
        data = http.get_json(api, params={"action": "query", "titles": "|".join(chunk), "prop": "pageprops",
                                          "ppprop": "wikibase_item", "redirects": 1, "format": "json"})
        query = data.get("query", {})
        found = {p["title"]: p["pageprops"]["wikibase_item"] for p in query.get("pages", {}).values()
                 if p.get("ns") == 0 and p.get("pageprops", {}).get("wikibase_item")}
        out.update(found)
        # A link's title may be normalised, then redirected: follow both hops.
        hops = {h["from"]: h["to"] for step in ("normalized", "redirects") for h in query.get(step, [])}
        for start in hops:
            to = start
            for _ in range(3):
                to = hops.get(to, to)
            if to in found:
                out.setdefault(start, found[to])
    return out


# --- rendering --------------------------------------------------------------------

def claim_text(claim: dict[str, Any], info: dict[str, dict[str, Any]]) -> str | None:
    """One statement as a line: its value, then its dates, role and share."""
    def show(v: Any) -> str | None:
        if isinstance(v, dict) and "id" in v:
            return f"{v['id']} ({memo_name(info.get(v['id']))})"
        if isinstance(v, dict) and "time" in v:
            return v["time"][:11].lstrip("+")
        if isinstance(v, dict) and "amount" in v:
            return v["amount"].lstrip("+")
        return None
    main = show(claim.get("mainsnak", {}).get("datavalue", {}).get("value"))
    if main is None:
        return None
    quals = []
    for qprop in ("P580", "P582", "P2868", "P1107"):
        for snak in (claim.get("qualifiers") or {}).get(qprop, []):
            v = show(snak.get("datavalue", {}).get("value"))
            if v:
                quals.append(f"{qprop} {v}")
    rank = "" if claim.get("rank") == "normal" else f" [{claim.get('rank')}]"
    return main + (f" ({'; '.join(quals)})" if quals else "") + rank


#: The label languages of the request being rendered, best first. A label
#: is picked by this order, never by the order the cache returns: `jsonb`
#: re-sorts keys, and a name that changes between runs changes the request
#: and makes the ledger pay for it again.
LABEL_ORDER: tuple[str, ...] = ("en", "mul")


def memo_name(info: dict[str, Any] | None) -> str:
    labels = (info or {}).get("labels", {})
    for lang in LABEL_ORDER:
        if lang in labels:
            return labels[lang]
    return next(iter(sorted(labels.items())), ("", ""))[1]


def render(item: dict[str, Any], offered: list[str], kinds: dict[str, str], articles: list[dict[str, Any]],
           wikis: list[str]) -> str:
    ent = item["entity"]
    refs = {v for p in SHOWN_PROPS for v in wikidata.claim_qids(ent, p)} | set(offered) | set(item["chain"] or [])
    for claims in ent.get("claims", {}).values():
        for c in claims:
            for snak in (c.get("qualifiers") or {}).get("P2868", []):
                v = snak.get("datavalue", {}).get("value")
                if isinstance(v, dict) and "id" in v:
                    refs.add(v["id"])
    global LABEL_ORDER
    LABEL_ORDER = loadmod.label_langs(wikis)
    info = memo.labels_of(sorted(refs), LABEL_ORDER)
    p = [f"# Item {item['qid']}", "", "## Labels"]
    p += [f"- {lg}: {ent['labels'][lg]['value']}" for lg in loadmod.label_langs(wikis) if lg in ent.get("labels", {})]
    descs = [f"- {lg}: {ent['descriptions'][lg]['value']}" for lg in loadmod.label_langs(wikis) if lg in ent.get("descriptions", {})]
    if descs:
        p += ["", "## Descriptions", *descs]
    p += ["", "## Existing statements"]
    for prop in SHOWN_PROPS:
        for claim in ent.get("claims", {}).get(prop, []):
            text = claim_text(claim, info)
            if text:
                p.append(f"- {prop}: {text}")
    if item["chain"]:
        p += ["", "## Ownership chain found on Wikidata",
              " → owned by → ".join(f"{q} ({memo_name(info.get(q))})" for q in item["chain"])]
    if item["seed"]:
        s = item["seed"]
        p += ["", "## Official list of state holdings",
              f"Listed as \"{s.get('name')}\", held by {s.get('holder')} ({s.get('source')})."]
    p += ["", "## Candidate controllers"]
    for i, q in enumerate(offered):
        d = (info.get(q) or {}).get("description")
        p.append(f"[{i}] {q} {memo_name(info.get(q))} ({kinds.get(q, 'owner on the item')})" + (f" — {d}" if d else ""))
    for a in articles:
        p += ["", f"```article lang={a['lang']} title={a['title']!r} url={a['url']}", a["text"][:ARTICLE_CHARS], "```"]
    if not articles:
        p += ["", "## Articles: none"]
    return "\n".join(p)


def render_party(item: dict[str, Any], articles: list[dict[str, Any]], wikis: list[str]) -> str:
    """A party's request: its labels, its statements and its articles; no controllers to choose from."""
    ent = item["entity"]
    refs = {v for p in PARTY_PROPS for v in wikidata.claim_qids(ent, p)}
    global LABEL_ORDER
    LABEL_ORDER = loadmod.label_langs(wikis)
    info = memo.labels_of(sorted(refs), LABEL_ORDER)
    p = [f"# Item {item['qid']}", "", "## Labels"]
    p += [f"- {lg}: {ent['labels'][lg]['value']}" for lg in LABEL_ORDER if lg in ent.get("labels", {})]
    descs = [f"- {lg}: {ent['descriptions'][lg]['value']}" for lg in LABEL_ORDER if lg in ent.get("descriptions", {})]
    if descs:
        p += ["", "## Descriptions", *descs]
    p += ["", "## Existing statements"]
    for prop in PARTY_PROPS:
        for claim in ent.get("claims", {}).get(prop, []):
            text = claim_text(claim, info)
            if text:
                p.append(f"- {prop}: {text}")
    for a in articles:
        p += ["", f"```article lang={a['lang']} title={a['title']!r} url={a['url']}", a["text"][:ARTICLE_CHARS], "```"]
    if not articles:
        p += ["", "## Articles: none"]
    return "\n".join(p)


# --- the ledger ------------------------------------------------------------------

#: Every pepcorp answer -- decide's, the link check's, the person match's -- in one table.
LEDGER = llm.Ledger("pcorp_call")


def content_key(model: str, prompt_hash: str, message: str) -> str:
    return LEDGER.key(model, prompt_hash, message)


def recorded(key: str) -> dict[str, Any] | None:
    return LEDGER.recorded(key)


def params(message: str, model: str = MODEL, prompt: Path = PROMPT_PATH) -> dict[str, Any]:
    """The decide request for one message, without its output format."""
    text, _ = system_prompt(prompt)
    return {"model": model, "max_tokens": MAX_TOKENS, "thinking": {"type": "adaptive"},
            "output_config": {"effort": "medium"},
            "system": [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": message}]}


def ask(message: str, model: str = MODEL) -> tuple[Answer, dict[str, int]]:
    response = llm.send(output_format=Answer, **params(message, model))
    if response.parsed_output is None:
        raise RuntimeError(f"no parsed output ({response.stop_reason})")
    return response.parsed_output, llm.usage(response)


def prepare(cc: str, log: Callable[[str], None], only: set[str] | None = None,
            limit: int | None = None) -> list[dict[str, Any]]:
    """Build every request for a country's kept bodies, or these, or the first `limit` (no model calls)."""
    state = countries.state_qid(cc)
    actors = actormod.read(cc)
    wikis = loadmod.langs(state)
    reqs, failed = [], 0
    todo = [it for it in loadmod.items(cc) if not only or it["qid"] in only]
    for item in todo[:limit] if limit else todo:
        party = is_party(item)
        try:
            if party:
                articles = fetch_articles(item["qid"], item["entity"], party_wikis(item["entity"], wikis))
                offered: list[str] = []
                message = render_party(item, articles, wikis)
            else:
                articles = fetch_articles(item["qid"], item["entity"], wikis)
                offered = actormod.offered(actors, item["entity"], item["chain"])
                message = render(item, offered, actors.kinds, articles, wikis)
            links = article_links(articles)
        except requests.RequestException as exc:  # one timed-out read must not lose the others
            failed += 1
            log(f"  {item['qid']}: not prepared ({exc.__class__.__name__}); the next run asks it")
            continue
        reqs.append({"qid": item["qid"], "party": party, "message": message, "offered": offered, "links": links,
                     "articles": [{k: a[k] for k in ("lang", "url", "rev")} for a in articles]})
    if failed:
        log(f"{failed} enterprises not prepared after read errors")
    return reqs


def decide(cc: str, model: str = MODEL, limit: int | None = None, log: Callable[[str], None] = print,
           only: set[str] | None = None) -> list[dict[str, Any]]:
    """Ask the model about every kept enterprise of a country; return the answered requests."""
    reqs = prepare(cc, log, only, limit)
    hashes = {path: system_prompt(path)[1] for path in (PROMPT_PATH, PARTY_PROMPT_PATH)}
    for r in reqs:
        r["prompt"] = PARTY_PROMPT_PATH if r["party"] else PROMPT_PATH
        r["key"] = content_key(model, hashes[r["prompt"]], r["message"])
    todo = [r for r in reqs if recorded(r["key"]) is None]
    log(f"{len(reqs)} requests; {len(reqs) - len(todo)} answered before, {len(todo)} to ask")

    def done(r: dict[str, Any]) -> Callable[[BaseModel, dict[str, int]], None]:
        return lambda answer, usage: LEDGER.store(
            r["key"], cc, r["qid"], model, hashes[r["prompt"]],
            {k: r[k] for k in ("message", "offered", "links", "articles")}, answer.model_dump(), usage)

    jobs = [llm.Job(params(r["message"], model, r["prompt"]), PartyAnswer if r["party"] else Answer, done(r))
            for r in todo]
    llm.run("corp:decide", jobs, log, WORKERS)
    for r in reqs:
        r["answer"] = recorded(r["key"])
    return [r for r in reqs if r["answer"] is not None]


def from_ledger(cc: str) -> list[dict[str, Any]]:
    """Each kept body's newest answer, under whichever decide prompt asked it, for re-deciding without asking again.

    A prompt change then applies body by body: the bodies asked again carry
    the new prompt's answer, the rest keep theirs. An answer the current
    schema cannot read (an older prompt's) is passed over; the ledger rows
    of the narrow checks are no answers (they carry no candidates).
    """
    rows = wd.conn().execute(
        "SELECT qid, key, answer FROM pcorp_call WHERE country = %s AND request ? 'offered'"
        " ORDER BY qid, created_at DESC", (cc,)).fetchall()
    kept = {it["qid"] for it in loadmod.items(cc)}
    newest: dict[str, tuple[str, dict[str, Any]]] = {}
    for q, k, ans in rows:
        if q in kept and q not in newest and readable(ans):
            newest[q] = (k, ans)
    requests = dict(wd.conn().execute("SELECT key, request FROM pcorp_call WHERE key = ANY(%s)",
                                      ([k for k, _ in newest.values()],)).fetchall())
    return [{"qid": q, "key": k, **requests[k], "answer": ans} for q, (k, ans) in newest.items()]


def readable(answer: dict[str, Any]) -> bool:
    """Whether the current schema reads an answer: a body's, or a party's."""
    for schema in (Answer, PartyAnswer):
        try:
            schema.model_validate(answer)
        except ValueError:
            continue
        return True
    return False


def cost(cc: str) -> tuple[float, int]:
    """Total spend on this country's ledger rows at list price, and the number of calls."""
    return LEDGER.cost(cc)
