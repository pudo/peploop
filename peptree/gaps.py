"""Say what each kept item is missing, and score the country as a matrix.

A gap is a missing `P17`, `P1001`, `P279` or position metaclass, or a
*class fix*: a well-formed office that plainly belongs to a FATF category (by
its name or its body) but whose class chain does not reach that category's
class. The fix adds the category class as one more `P279`; nothing is removed.

The matrix is category × state over the country's current national offices.
A category is reached through its class handles (minus `exclude`) or, for an
unsettled category, only through names and bodies.
"""

from pathlib import Path
from typing import Any

import yaml

from peptree import country as countries
from peptree import wd
from peptree.load import POSITION_METAS, has, values

CATEGORIES_PATH = Path(__file__).resolve().parent / "categories.yml"


def categories() -> list[dict[str, Any]]:
    cats = yaml.safe_load(CATEGORIES_PATH.read_text())
    for cat in cats:
        cat["class_qids"] = [c["qid"] for c in cat.get("classes") or []]
        cat["exclude_qids"] = [c["qid"] for c in cat.get("exclude") or []]
        cat["body_qids"] = [c["qid"] for c in cat.get("body_classes") or []]
    return cats


#: A deputy is in the minister and legislator categories but never heads an
#: apex office, so the head categories refuse a deputy's label.
BODY_ROUTE = {"apex_judge"}
HEAD_CATEGORIES = {"head_of_state", "head_of_government", "prosecutor_general", "central_bank",
                   "supreme_audit", "military_chief", "security_chief", "party_leader"}


def class_names(c: countries.Country, cats: list[dict[str, Any]]) -> dict[str, list[list[str]]]:
    """Per category, the stem sequences of its classes' names in the country's languages."""
    qids = sorted({q for cat in cats for q in cat["class_qids"]})
    names = wd.names_of(qids, c.langs)
    out: dict[str, list[list[str]]] = {}
    for cat in cats:
        seqs = {tuple(countries.seq(n)) for q in cat["class_qids"] for n in names.get(q, [])}
        out[cat["key"]] = [list(x) for x in sorted(seqs) if x]
    return out


def is_deputy(c: countries.Country, text: str) -> bool:
    return countries.says(c.words.get("deputy", []), text)


def name_categories(c: countries.Country, names: dict[str, list[list[str]]], entity: dict[str, Any]) -> set[str]:
    """The categories an item's labels name it into: the name route of the class fix.

    A label names a category when it leads with the name of one of the
    category's classes, in any of the country's languages ("Міністр
    культуры ..." leads with "міністр"). A head category asks more: no deputy,
    and nothing after the class name but the state's own name ("President of
    the Republic of X", never "President of the Supreme Court").
    """
    deputy_stems = {s for p in c.words.get("deputy", []) for s in countries.stems(p)}
    # "deputy" names a legislator in English and an assistant too: a class name
    # made only of deputy words says nothing.
    names = {k: [n for n in seqs if not all(s in deputy_stems for s in n)] for k, seqs in names.items()}
    own = {s for q in c.home for n in c.names.get(q, []) for s in countries.stems(n)}
    out = set()
    for lg in ("en", *c.langs):
        text = entity.get("labels", {}).get(lg, {}).get("value", "")
        if not text:
            continue
        toks = countries.seq(text)
        bare = list(toks)
        while bare and any(bare[0].startswith(d) or d.startswith(bare[0]) for d in deputy_stems):
            bare = bare[1:]
        for key, seqs in names.items():
            head = key in HEAD_CATEGORIES
            for need in seqs:
                for cand in ((toks,) if head else (toks, bare)):
                    if len(cand) < len(need) or not all(t.startswith(n) for t, n in zip(cand, need)):
                        continue
                    if head and (is_deputy(c, text) or not all(
                            any(t.startswith(o) or o.startswith(t) for o in own) for t in cand[len(need):])):
                        continue
                    out.add(key)
    return out


def reaches(cat: dict[str, Any], types: set[str]) -> bool:
    return bool(types & set(cat["class_qids"])) and not types & set(cat["exclude_qids"])


class Context:
    """Everything the gap and matrix steps read once per country."""

    def __init__(self, cc: str, items: list[dict[str, Any]]) -> None:
        self.cc = cc
        self.country = countries.get(cc)
        self.cats = categories()
        self.by_key = {c["key"]: c for c in self.cats}
        self.names = class_names(self.country, self.cats)
        self.items = items
        self.types = wd.closure({it["qid"]: values(it["entity"], "P31") + values(it["entity"], "P279")
                                 for it in items})
        bodies = sorted({b for it in items for b in values(it["entity"], "P361") + values(it["entity"], "P2389")})
        body_seeds = {}
        for qid, ent in wd.fetch_items(bodies, props="claims|labels").items():
            body_seeds[qid] = values(ent, "P31")
        self.body_types = wd.closure(body_seeds) if body_seeds else {}

    def body_categories(self, entity: dict[str, Any]) -> set[str]:
        out = set()
        for body in values(entity, "P361") + values(entity, "P2389"):
            for cat in self.cats:
                if set(cat["body_qids"]) & self.body_types.get(body, set()):
                    out.add(cat["key"])
        return out

    def detected(self, item: dict[str, Any]) -> set[str]:
        """Categories an item belongs to by name or body (not by class)."""
        if item["kind"] == "ambassador":
            return {"ambassador"}
        if item["kind"] not in ("national", "predecessor"):
            return set()
        # The body route only where every seat in the body is of the category:
        # every seat on an apex court is a judge's, but a central bank's board
        # or a ministry also seats deputies who are not its head.
        return name_categories(self.country, self.names, item["entity"]) | (self.body_categories(item["entity"]) & BODY_ROUTE)

    def gaps(self, item: dict[str, Any], types: set[str] | None = None) -> list[tuple[str, str, str | None]]:
        """(prop, gap, category) for one kept item."""
        ent = item["entity"]
        types = self.types[item["qid"]] if types is None else types
        out: list[tuple[str, str, str | None]] = []
        detected = self.detected(item)
        if not has(ent, "P17"):
            out.append(("P17", "missing", None))
        if not has(ent, "P1001") and item["kind"] != "ambassador":
            out.append(("P1001", "missing", None))
        if not has(ent, "P279"):
            cat = next(iter(sorted(detected)), None) if len(detected) == 1 else None
            out.append(("P279", "missing", cat))
        else:
            for key in sorted(detected):
                cat = self.by_key[key]
                if cat["class_qids"] and not reaches(cat, types):
                    out.append(("P279", "classfix", key))
                    break
        if not set(values(ent, "P31")) & POSITION_METAS:
            out.append(("P31", "missing", None))
        return out


def store_gaps(cc: str, ctx: Context) -> int:
    rows = [(cc, it["qid"], prop, gap, cat) for it in ctx.items for prop, gap, cat in ctx.gaps(it)]
    con = wd.conn()
    with con.transaction():
        con.execute("DELETE FROM ptree_gap WHERE country = %s", (cc,))
        with con.cursor() as cur:
            cur.executemany("INSERT INTO ptree_gap (country, qid, prop, gap, category) VALUES (%s,%s,%s,%s,%s)", rows)
    return len(rows)


# --- the matrix -----------------------------------------------------------------

def well_formed(item: dict[str, Any], ent: dict[str, Any]) -> bool:
    return (has(ent, "P17") and (has(ent, "P1001") or item["kind"] == "ambassador") and has(ent, "P279")
            and bool(set(values(ent, "P31")) & POSITION_METAS) and item["holders"] > 0)


def matrix(ctx: Context, added: dict[str, dict[str, list[str]]] | None = None) -> dict[str, dict[str, Any]]:
    """Per category: state (ok / repair / absent) and the items behind it.

    `added` maps qid → prop → values a batch would add; the matrix is then the
    one after the batch. Only current offices count: national, or the state's
    own posts abroad for the ambassador category.
    """
    added = added or {}
    new_classes = {v for props in added.values() for v in props.get("P279", [])}
    up = wd.class_closure(new_classes) if new_classes else {}
    out = {}
    for cat in ctx.cats:
        members, ok = [], []
        for it in ctx.items:
            if it["kind"] not in ("national", "ambassador"):
                continue
            if (cat["key"] == "ambassador") != (it["kind"] == "ambassador"):
                continue
            ent = _with(it["entity"], added.get(it["qid"], {}))
            types = set(ctx.types[it["qid"]])
            for v in added.get(it["qid"], {}).get("P279", []):
                types |= up.get(v, {v})
            in_class = reaches(cat, types)
            if cat["key"] in HEAD_CATEGORIES and is_deputy(ctx.country, wd.label(ent)):
                continue  # a deputy prosecutor reaching the class is not the office
            if not in_class and cat["key"] not in ctx.detected({**it, "entity": ent}):
                continue
            members.append(it["qid"])
            # Unsettled categories have no class: well-formed is all they can ask.
            if (in_class or not cat["class_qids"]) and well_formed(it, ent):
                ok.append(it["qid"])
        state = "ok" if ok else ("repair" if members else "absent")
        out[cat["key"]] = {"state": state, "members": len(members), "ok": len(ok),
                           "ok_items": ok[:5], "unsettled": bool(cat.get("unsettled"))}
    return out


def _with(entity: dict[str, Any], props: dict[str, list[str]]) -> dict[str, Any]:
    """A copy of an entity with item-valued statements added (for the after-matrix)."""
    if not props:
        return entity
    claims = dict(entity.get("claims", {}))
    for prop, vals in props.items():
        claims[prop] = list(claims.get(prop, [])) + [
            {"rank": "normal", "mainsnak": {"datavalue": {"value": {"id": v}}}} for v in vals]
    return {**entity, "claims": claims}
