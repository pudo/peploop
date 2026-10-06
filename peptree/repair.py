"""Ask the model for each gap, one item per request, answers kept by content.

The request shows the item, its holders, its article leads and an indexed
candidate list per asked property; the model answers by index. The ledger
(`ptree_call`) is keyed by a hash of model, prompt and message, so a re-run
pays only for items whose material changed.
"""

import concurrent.futures as cf
import hashlib
import os
import threading
from collections import Counter
from pathlib import Path
from typing import Any, Literal, Optional

import anthropic
import requests
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict

from peptree import country as countries
from peptree import gaps as gapmod
from peptree import signals, wd
from peptree.load import GENERIC_META, LIST_ARTICLES, POSITION_METAS, items as load_items, place_refs, values

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "repair.md"
MODEL = os.environ.get("PEPTREE_MODEL", "claude-opus-5")
MAX_TOKENS = 16000
WORKERS = int(os.environ.get("PEPTREE_WORKERS", "6"))
PROPS = ("P17", "P1001", "P279", "P31")

#: Office kinds offered for any missing P279, on top of the country's own
#: conventions and every category class. Grown from the dry run's misses:
#: civil chief of staff, president (of a body), chief of defence.
BASE_P279 = """Q83307 Q26204040 Q877955 Q14212 Q2285706 Q121998 Q19356884 Q486839 Q4175034 Q708492 Q30185
Q132050 Q16533 Q117826617 Q55736868 Q3188089 Q135398920 Q3368517 Q107363151 Q5097014 Q707492 Q112119463
Q484876 Q1501800 Q140686 Q1255921 Q5089507 Q1758037 Q1553195 Q6501749 Q2632935""".split()
META_CANDIDATES = ["Q294414", "Q4164871"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Slot(Strict):
    choice: Optional[int]
    confidence: Literal["high", "medium", "low"]
    source: Literal["label", "description", "statements", "holders", "article", "none"]
    #: The language code of the article quoted, as its heading shows it; null unless source is "article".
    article: Optional[str]
    quote: str
    decline_reason: Optional[str]


class Answer(Strict):
    P17: Slot
    P1001: Slot
    P279: Slot
    P31: Slot
    notes: str


def system_prompt() -> tuple[str, str]:
    text = PROMPT_PATH.read_text()
    return text, hashlib.sha256(text.encode()).hexdigest()


_client = None
_lock = threading.Lock()


def client() -> anthropic.Anthropic:
    global _client
    with _lock:
        if _client is None:
            _client = anthropic.Anthropic()
        return _client


# --- context ----------------------------------------------------------------------

class Run:
    """What candidates and channels read once per country."""

    def __init__(self, cc: str) -> None:
        wd.init()
        self.cc = cc
        self.country = countries.get(cc)
        self.items = load_items(cc)
        self.by_qid = {it["qid"]: it for it in self.items}
        self.ctx = gapmod.Context(cc, self.items)
        self.places = signals.Places(countries.gazetteer(self.country, place_refs(self.items)))
        countries.learn_level_words(self.country, self.items, list(self.places.places.values()))
        self.sib = signals.siblings(self.items, self.places, self.country.official)
        rows = wd.conn().execute("SELECT qid, prop, gap, category FROM ptree_gap WHERE country = %s", (cc,)).fetchall()
        self.gaps: dict[str, dict[str, tuple[str, str | None]]] = {}
        for qid, prop, gap, cat in rows:
            self.gaps.setdefault(qid, {})[prop] = (gap, cat)
        sender = wd.sparql(f"SELECT ?cls WHERE {{ ?cls wdt:P279 wd:Q29645880 ; wdt:P17 wd:{self.country.qid} }}")
        self.sender_class = sender[0]["cls"] if sender else None
        # The country's own P279 conventions: values two or more kept items use.
        used = Counter(v for it in self.items for v in set(values(it["entity"], "P279")))
        self.country_p279 = [q for q, n in used.most_common() if n >= 2]
        self.cat_classes = {c["key"]: set(c["class_qids"]) for c in self.ctx.cats}
        all_classes = [q for c in self.ctx.cats for q in c["class_qids"]]
        pool = BASE_P279 + all_classes + self.country_p279 + ([self.sender_class] if self.sender_class else [])
        self.info = wd.labels_of(pool + META_CANDIDATES + sorted(self.country.home))
        self.value_types = wd.class_closure(pool)
        # Classes that must never be offered: lists and the metaclasses.
        self.p279_pool = [q for q in dict.fromkeys(pool)
                          if q not in POSITION_METAS and q not in LIST_ARTICLES and q != GENERIC_META]
        bodies = sorted({b for it in self.items for b in values(it["entity"], "P361") + values(it["entity"], "P2389")})
        found = wd.fetch_items(bodies, props="claims")
        self.bodies = {b: {p: values(e, p) for p in ("P17", "P1001")} for b, e in found.items()}
        heads = [q for c in self.ctx.cats if c["key"] in ("head_of_state", "head_of_government") for q in c["class_qids"]]
        # Every language's name, for a label in any language; a one-stem name
        # must be a real word ("cap d'Estat" leaves only "esta").
        seqs = {tuple(countries.seq(n)) for ns in wd.names_of(heads).values() for n in ns}
        self.head_seqs = sorted(x for x in seqs if len(x) > 1 or (x and len(x[0]) >= 6))
        self.value_spans: dict[str, list[int | None]] = {}
        self.non_states: set[str] = set()
        self.classes: set[str] = set()
        self._typed: set[str] = set()

    def spans_for(self, qids: list[str]) -> None:
        """Read (and cache a month) when each candidate value existed."""
        wanted = sorted(set(qids) - set(self.value_spans) - set(self.country.spans))
        for chunk in wd.values_chunks(wanted, 50):
            self.value_spans.update(wd.cached("spans:" + "|".join(chunk), lambda chunk=chunk: {
                q: countries.entity_span(e) for q, e in wd.fetch_items(chunk, props="claims").items()}))
        unread = sorted(set(qids) - self._typed)
        for chunk in wd.values_chunks(unread, 50):
            self.non_states.update(wd.cached("non_states:" + "|".join(chunk), lambda chunk=chunk: sorted(
                q for q, e in wd.fetch_items(chunk, props="claims").items() if not countries.is_state(e))))
        self._typed |= set(unread)

    def classes_for(self, qids: list[str]) -> None:
        """Note which items are some other item's `P279` (cached a day): a class, not an office.

        `FILTER EXISTS`, not a join: WDQS answers `VALUES ?c {…} ?x wdt:P279 ?c` with nothing.
        """
        for chunk in wd.values_chunks(sorted(set(qids)), 100):
            found = wd.cached("subclassed:" + "|".join(chunk), lambda chunk=chunk: sorted({
                r["c"] for r in wd.sparql(f"SELECT ?c WHERE {{ VALUES ?c {{ {wd.values_block(chunk)} }} FILTER EXISTS {{ ?x wdt:P279 ?c }} }}")}),
                max_age=wd.DAY)
            self.classes.update(found)

    def facts(self, item: dict[str, Any]) -> signals.Facts:
        return signals.Facts(item=item, country=self.country, places=self.places, sib=self.sib,
                             detected=self.ctx.detected(item), bodies=self.bodies,
                             cat_classes=self.cat_classes, value_types=self.value_types,
                             sender_class=self.sender_class, value_spans=self.value_spans,
                             non_states=self.non_states, classes=self.classes,
                             head_seqs=[list(x) for x in self.head_seqs])

    def candidates(self, item: dict[str, Any]) -> dict[str, list[str]]:
        """Indexed candidate QIDs per asked property."""
        asked = self.gaps.get(item["qid"], {})
        c = self.country
        text = " | ".join(signals.labels_text(item["entity"]))
        out: dict[str, list[str]] = {}
        if "P17" in asked:
            if item["kind"] == "ambassador":
                out["P17"] = [q for q in self.places.mentioned(text, {"country"}) if q not in c.home]
            else:
                out["P17"] = c.p17_values
        if "P1001" in asked:
            regions = [q for q, p in sorted(self.places.places.items()) if "region" in p["levels"]]
            local = self.places.mentioned(text, {"district", "local"})[:25]
            out["P1001"] = list(dict.fromkeys(c.p1001_values + regions + local))
        if "P279" in asked:
            gap, cat = asked["P279"]
            if gap == "classfix":
                pool = list(self.ctx.by_key[cat]["class_qids"])  # the file's order: a set's varies by process
                if cat == "ambassador" and self.sender_class:
                    pool = [self.sender_class] + pool
            else:
                conv = signals.convention(self.sib, item["qid"], "p279")
                first = ([conv] if conv else []) + (list(self.ctx.by_key[cat]["class_qids"]) if cat else [])
                pool = first + self.p279_pool
            out["P279"] = [q for q in dict.fromkeys(pool) if q != item["qid"]]
        if "P31" in asked:
            out["P31"] = list(META_CANDIDATES)
        return {k: v for k, v in out.items() if v}


# --- rendering -------------------------------------------------------------------

SHOWN_PROPS = ("P31", "P279", "P361", "P2389", "P17", "P1001", "P131", "P137", "P571", "P576", "P1365", "P1366")


def holders(qids: list[str]) -> dict[str, list[dict[str, str]]]:
    """Up to ten holders per office, with dates and citizenships, read live."""
    q = """SELECT ?pos ?h ?hLabel ?s ?e (GROUP_CONCAT(DISTINCT ?cl; separator=", ") AS ?cit) WHERE {
      VALUES ?pos { %s } ?h p:P39 ?st . ?st ps:P39 ?pos . ?h wdt:P31 wd:Q5 .
      OPTIONAL { ?st pq:P580 ?s } OPTIONAL { ?st pq:P582 ?e }
      OPTIONAL { ?h wdt:P27 ?c . ?c rdfs:label ?cl FILTER(LANG(?cl) = "en") }
      SERVICE wikibase:label { bd:serviceParam wikibase:language "%s". } }
      GROUP BY ?pos ?h ?hLabel ?s ?e"""
    out: dict[str, list[dict[str, str]]] = {}
    for chunk in wd.values_chunks(qids, 40):
        for r in wd.sparql(q % (wd.values_block(chunk), ",".join(wd.LANGS))):
            # GROUP_CONCAT order is arbitrary; sorted, so the content key is stable.
            cit = ", ".join(sorted(x for x in r.get("cit", "").split(", ") if x))
            out.setdefault(r["pos"], []).append({"qid": r["h"], "name": r.get("hLabel", ""),
                                                 "start": r.get("s", "")[:10], "end": r.get("e", "")[:10],
                                                 "cit": cit})
    for pos, rows in out.items():
        rows.sort(key=lambda r: (r["start"] or "9999", r["qid"]), reverse=True)
        seen, keep = set(), []
        for r in rows:
            if r["qid"] not in seen:
                seen.add(r["qid"])
                keep.append(r)
        out[pos] = keep[:10]
    return out


def leads(entity: dict[str, Any], langs: tuple[str, ...]) -> list[tuple[str, str, str]]:
    """(lang, url, lead) for the articles in the country's languages and English that exist.

    One per language, its own wiki first, then a script variant's
    (`<lang>_...wiki`); the URL is the one Wikidata gives for the sitelink.
    """
    out = []
    links = entity.get("sitelinks", {})
    for lang in dict.fromkeys((*langs, "en")):
        sites = [f"{lang}wiki"] + sorted(k for k in links if k.startswith(f"{lang}_") and k.endswith("wiki"))
        for site in sites:
            if site in links:
                title = links[site]["title"]
                url = links[site].get("url") or f"https://{lang}.wikipedia.org/wiki/{title.replace(' ', '_')}"
                host = url.split("/")[2].split(".")[0]
                out.append((lang, url, wd.lead(host, title)))
                break
    return out


def years_text(span: list[int | None] | tuple[int | None, int | None] | None) -> str:
    """"1902–1959", "1959–", "–1925"; empty when nothing is known."""
    if not span or (span[0] is None and span[1] is None):
        return ""
    return f"{'' if span[0] is None else span[0]}–{'' if span[1] is None else span[1]}"


def render(run: Run, item: dict[str, Any], cands: dict[str, list[str]], held: list[dict[str, str]],
           articles: list[tuple[str, str, str]]) -> str:
    ent = item["entity"]
    run.spans_for([q for prop in ("P17", "P1001") for q in cands.get(prop, [])])
    refs = {v for p in SHOWN_PROPS for v in values(ent, p)} | {v for vs in cands.values() for v in vs}
    info = {**wd.labels_of(refs), **run.info}
    label_langs = (*[lg for lg in run.country.langs if lg not in ("en", "mul")], "en", "mul")
    labels = {lg: ent["labels"][lg]["value"] for lg in label_langs if lg in ent.get("labels", {})}
    if not labels:
        labels = {lg: o["value"] for lg, o in list(ent.get("labels", {}).items())[:3]}
    p = [f"# Item {item['qid']}", "", "## Labels"] + [f"- {lg}: {v}" for lg, v in labels.items()]
    descs = {lg: ent["descriptions"][lg]["value"] for lg in ("en", *run.country.official) if lg in ent.get("descriptions", {})}
    if descs:
        p += ["", "## Descriptions"] + [f"- {lg}: {v}" for lg, v in descs.items()]
    aliases = {lg: [a["value"] for a in ent["aliases"][lg]][:5] for lg in ("en", *run.country.official) if lg in ent.get("aliases", {})}
    if aliases:
        p += ["", "## Aliases"] + [f"- {lg}: {'; '.join(v)}" for lg, v in aliases.items()]
    p += ["", "## Existing statements"]
    for prop in SHOWN_PROPS:
        for claim in ent.get("claims", {}).get(prop, []):
            v = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
            if isinstance(v, dict) and "id" in v:
                text = f"{v['id']} ({wd.name(info.get(v['id']))})"
            elif isinstance(v, dict) and "time" in v:
                text = v["time"][:11].lstrip("+") + f" (precision {v.get('precision')})"
            else:
                continue
            rank = "" if claim.get("rank") == "normal" else f" [{claim.get('rank')}]"
            p.append(f"- {prop}: {text}{rank}")
    asked = run.gaps.get(item["qid"], {})
    p += ["", "## Asked"]
    for prop in PROPS:
        if prop not in cands:
            continue
        gap, cat = asked[prop]
        if gap == "classfix":
            label = run.ctx.by_key[cat]["label"]
            p.append(f"- {prop}: class fix. The item's P279 chain does not reach the category "
                     f"\"{label}\". If the item is an office of that kind, choose the class to ADD.")
        else:
            p.append(f"- {prop}: missing")
    p.append("For every property not listed here, answer \"not asked\".")
    p += ["", f"## Holders ({item['holders']} in total; up to 10 shown, latest first)"]
    active = years_text(signals.office_span(item))
    if active:
        p.append(f"Office active (from its inception/abolition, else its holders' dates): {active}")
    if not held:
        p.append("(none)")
    life = {r["h"]: r for r in item.get("holder_rows") or []}
    for h in held:
        r = life.get(h["qid"], {})
        lived = f"; lived {r.get('b') or '?'}–{r.get('d') or ''}" if r.get("b") or r.get("d") else ""
        p.append(f"- {h['name']} ({h['qid']}) {h['start'] or '?'} – {h['end'] or '?'}{lived}; citizenship: {h['cit'] or '?'}")
    for lang, url, text in articles:
        p += ["", f"## Article lead ({lang}: {url})", text or "(empty)"]
    if not articles:
        p += ["", "## Article: none"]
    p += ["", "## Candidates"]
    for prop in PROPS:
        if prop not in cands:
            continue
        p.append(f"### {prop}")
        for i, q in enumerate(cands[prop]):
            d = (info.get(q) or {}).get("description")
            when = ""
            if prop in ("P17", "P1001"):
                span = run.country.spans.get(q) or run.value_spans.get(q)
                when = f" ({years_text(span)})" if years_text(span) else ""
                if q in run.country.predecessors or q in run.country.unions:
                    when += " [predecessor state]" if q in run.country.predecessors else " [federation of a predecessor]"
            p.append(f"[{i}] {q} {wd.name(info.get(q))}{when}" + (f" — {d}" if d else ""))
    return "\n".join(p)


# --- the ledger ------------------------------------------------------------------

def content_key(model: str, prompt_hash: str, message: str) -> str:
    return hashlib.sha256(f"{model}\n{prompt_hash}\n{message}".encode()).hexdigest()


def recorded(key: str) -> dict[str, Any] | None:
    row = wd.conn().execute("SELECT answer FROM ptree_call WHERE key = %s", (key,)).fetchone()
    return None if row is None else row[0]


def ask(message: str, model: str = MODEL) -> tuple[Answer, dict[str, int]]:
    text, _ = system_prompt()
    response = client().messages.parse(
        model=model, max_tokens=MAX_TOKENS, thinking={"type": "adaptive"}, output_config={"effort": "high"},
        system=[{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": message}], output_format=Answer)
    if response.parsed_output is None:
        raise RuntimeError(f"no parsed output ({response.stop_reason})")
    u = response.usage
    return response.parsed_output, {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
                                    "cache_read_input_tokens": u.cache_read_input_tokens or 0,
                                    "cache_creation_input_tokens": u.cache_creation_input_tokens or 0}


#: Items with a gap above which only held offices and offices in a FATF category are
#: asked about. Indonesia's 13,828 were mostly an imported civil-service org chart
#: ("Kepala Seksi …", district chiefs), 11,460 of them held by no one.
LARGE = 300


def focus(run: Run, todo: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """In a large place, the items worth a model call: held by someone, or in a category."""
    if len(todo) <= LARGE:
        return todo
    return [it for it in todo if it.get("holders") or run.ctx.detected(it)]


def prepare(run: Run, log: Any = print) -> list[dict[str, Any]]:
    """Build every request for the country's gaps (no model calls)."""
    todo = [run.by_qid[q] for q in sorted(run.gaps) if q in run.by_qid]
    kept = focus(run, todo)
    if len(kept) < len(todo):
        log(f"large place: asking about {len(kept)} held or categorised items, not {len(todo) - len(kept)} others")
    todo = kept
    held = holders([it["qid"] for it in todo])
    reqs, failed = [], 0
    for it in todo:
        try:
            cands = run.candidates(it)
            if not cands:
                continue
            articles = leads(it["entity"], run.country.official)
            message = render(run, it, cands, held.get(it["qid"], []), articles)
        except requests.RequestException as exc:  # one timed-out read must not lose hours of others
            failed += 1
            log(f"  {it['qid']}: not prepared ({exc.__class__.__name__}); the next run asks it")
            continue
        reqs.append({"qid": it["qid"], "candidates": cands, "message": message,
                     "articles": [(lg, url) for lg, url, _ in articles]})
    if failed:
        log(f"{failed} items not prepared after read errors")
    return reqs


def repair(cc: str, model: str = MODEL, limit: int | None = None, log: Any = print) -> list[dict[str, Any]]:
    """Ask the model about every gap of a country; return (request, answer, key) records."""
    run = Run(cc)
    reqs = prepare(run, log)
    if limit:
        reqs = reqs[:limit]
    _, prompt_hash = system_prompt()
    for r in reqs:
        r["key"] = content_key(model, prompt_hash, r["message"])
    todo = [r for r in reqs if recorded(r["key"]) is None]
    log(f"{len(reqs)} requests; {len(reqs) - len(todo)} answered before, {len(todo)} to ask")

    def one(r: dict[str, Any]) -> None:
        answer, usage = ask(r["message"], model)
        wd.conn().execute(
            "INSERT INTO ptree_call (key, country, qid, model, prompt_hash, request, answer, usage)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (key) DO NOTHING",
            (r["key"], cc, r["qid"], model, prompt_hash,
             Jsonb({"message": r["message"], "candidates": r["candidates"], "articles": r["articles"]}),
             Jsonb(answer.model_dump()), Jsonb(usage)))

    with cf.ThreadPoolExecutor(WORKERS) as ex:
        futures = {ex.submit(one, r): r["qid"] for r in todo}
        for i, fut in enumerate(cf.as_completed(futures), 1):
            try:
                fut.result()
            except Exception as exc:  # one failed item must not lose the others
                log(f"  {futures[fut]}: {exc}")
            if i % 25 == 0:
                log(f"  asked {i}/{len(todo)}")
    for r in reqs:
        r["answer"] = recorded(r["key"])
    return reqs


def from_ledger(cc: str) -> list[dict[str, Any]]:
    """The latest answered request per item, for re-deciding without asking again."""
    rows = wd.conn().execute(
        "SELECT DISTINCT ON (qid) qid, key, request, answer FROM ptree_call WHERE country = %s"
        " ORDER BY qid, created_at DESC", (cc,)).fetchall()
    return [{"qid": q, "key": k, "message": req["message"], "candidates": req["candidates"],
             "articles": req["articles"], "answer": ans} for q, k, req, ans in rows]


#: USD per million tokens: input, output, cache read, cache write.
PRICES = {"claude-opus-5": (5.0, 25.0, 0.50, 6.25), "claude-sonnet-5": (2.0, 10.0, 0.20, 2.50)}


def cost(cc: str) -> tuple[float, int]:
    """Total spend on this country's ledger rows, and the number of calls."""
    rows = wd.conn().execute("SELECT model, usage FROM ptree_call WHERE country = %s", (cc,)).fetchall()
    total = 0.0
    for model, u in rows:
        pi, po, pr, pw = PRICES.get(model, PRICES["claude-opus-5"])
        total += (u["input_tokens"] * pi + u["output_tokens"] * po + u["cache_read_input_tokens"] * pr
                  + u["cache_creation_input_tokens"] * pw) / 1e6
    return total, len(rows)
