"""The mechanical channels a model's answer must agree with.

Each channel looks at one item and a proposed value and says whether it, on
its own evidence, supports that value:

- `label`: the item's labels name the value (country, predecessor, a place of
  the type the label's words name, receiving state);
- `holders`: most holders are citizens of the proposed country;
- `body`: the body the office sits in (`P361`/`P2389`) carries that value;
- `siblings`: offices whose labels differ from this one only in a place name
  agree on the value (the per-district chairmen all share one `P279`);
- `category`: the value reaches the class of a category the item's name or
  body puts it in;
- `state_office`: the metaclass matches whether the office is the state's.

Pure functions over data passed in, so `check_rules.py` can pin each one.
"""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from peptree import country as countries
from peptree.load import POSITION_METAS, values

TOKEN = re.compile(r"\w+", re.U)
PUBLIC_OFFICE, POSITION = "Q294414", "Q4164871"


SUBNATIONAL = {"region", "district", "local"}


class Places:
    """The gazetteer, indexed for stem lookups."""

    def __init__(self, places: list[dict[str, Any]]) -> None:
        self.places = {p["qid"]: p for p in places}
        self.stem_index: set[str] = set()
        for p in places:
            if set(p["levels"]) & (SUBNATIONAL | {"country", "predecessor"}):
                for need in p["stems"]:
                    self.stem_index |= set(need)

    def is_place_token(self, tok: str) -> bool:
        return any(tok[:k] in self.stem_index for k in range(4, len(tok) + 1))

    def mentioned(self, text: str, levels: set[str]) -> list[str]:
        return [q for q, p in self.places.items() if set(p["levels"]) & levels and countries.mentions(p, text)]

    def of_type(self, text: str, types: set[str]) -> list[str]:
        """Subnational places the text names that are of one of `types` (closure included)."""
        return [q for q in self.mentioned(text, SUBNATIONAL) if set(self.places[q].get("classes", [])) & types]


def labels_text(entity: dict[str, Any]) -> list[str]:
    """Every label, in every language: an item labelled only in Polish still names its state."""
    return [o["value"] for o in entity.get("labels", {}).values()]


def shape(text: str, places: Places) -> str:
    """A label with its place names and numbers masked: siblings share one."""
    out = []
    for tok in TOKEN.findall(text.lower()):
        out.append("#" if tok.isdigit() or (len(tok) >= 4 and places.is_place_token(tok)) else tok)
    return " ".join(out)


@dataclass
class Siblings:
    """Per label shape, how the other offices of that shape are typed."""

    p279: dict[str, Counter[str]] = field(default_factory=lambda: defaultdict(Counter))
    meta: dict[str, Counter[str]] = field(default_factory=lambda: defaultdict(Counter))
    p17: dict[str, Counter[str]] = field(default_factory=lambda: defaultdict(Counter))
    members: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    shapes: dict[str, set[str]] = field(default_factory=dict)


def siblings(items: list[dict[str, Any]], places: Places, langs: tuple[str, ...]) -> Siblings:
    """Group items by label shape, in English and the country's official languages."""
    out = Siblings()
    for it in items:
        ent = it["entity"]
        shapes = {f"{lg}:{shape(ent['labels'][lg]['value'], places)}"
                  for lg in dict.fromkeys(("en", *langs)) if lg in ent.get("labels", {})}
        shapes = {s for s in shapes if "#" in s}  # only labels that name a place
        out.shapes[it["qid"]] = shapes
        for s in shapes:
            out.members[s].add(it["qid"])
            out.p279[s].update(set(values(ent, "P279")))
            out.meta[s].update(set(values(ent, "P31")) & POSITION_METAS)
            out.p17[s].update(set(values(ent, "P17")))
    return out


def convention(sib: Siblings, qid: str, table: str, min_agree: int = 2, share: float = 2 / 3) -> str | None:
    """The value this item's siblings agree on, by the strictest shape that has one."""
    best = None
    for s in sib.shapes.get(qid, ()):
        if len(sib.members[s]) < 2:
            continue
        tally = getattr(sib, table)[s]
        total = sum(tally.values())
        top = tally.most_common(1)
        if top and top[0][1] >= min_agree and top[0][1] / total >= share:
            if best is not None and best != top[0][0]:
                return None  # two shapes disagree: no convention
            best = top[0][0]
    return best


@dataclass
class Facts:
    """What the channels read about one item, gathered by the caller."""

    item: dict[str, Any]
    country: countries.Country
    places: Places
    sib: Siblings
    detected: set[str] = field(default_factory=set)
    #: Body qid → its P17/P1001/P131 values.
    bodies: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    #: Category key → class qids, and the closure of each candidate value.
    cat_classes: dict[str, set[str]] = field(default_factory=dict)
    value_types: dict[str, set[str]] = field(default_factory=dict)
    sender_class: str | None = None


def expected_label(prop: str, f: Facts) -> set[str] | None:
    """The values the labels name for P17/P1001, or None when they name none."""
    texts = labels_text(f.item["entity"])
    joined = " | ".join(texts)
    c = f.country
    if f.item["kind"] == "ambassador":
        if prop != "P17":
            return None
        found = set(f.places.mentioned(joined, {"country"})) - c.home
        return found or None
    pred = countries.named_predecessor(c, joined) if f.item["kind"] == "predecessor" else None
    if prop == "P17":
        if pred:
            return {c.predecessors[pred]}
        if countries.names_country(c, joined) or f.places.mentioned(joined, SUBNATIONAL):
            return {c.qid}
        return None
    types: set[str] = set()
    for t in texts:
        types |= countries.level_types(c, t)
    if types:
        found = set(f.places.of_type(joined, types))
        return found or None
    if pred:
        return {pred}
    if countries.names_country(c, joined):
        return {c.qid}
    return None


def channels(prop: str, value: str, f: Facts) -> list[str]:
    """The names of the mechanical channels that support `value` for `prop`."""
    out = []
    ent = f.item["entity"]
    qid = f.item["qid"]
    if prop in ("P17", "P1001"):
        exp = expected_label(prop, f)
        if exp and value in exp:
            out.append("label")
        if prop == "P17":
            by, n = f.item.get("holder_countries") or {}, f.item.get("holders") or 0
            if value in f.country.p17_values and n >= 2 and by.get(value, 0) / n >= 2 / 3:
                out.append("holders")
            if convention(f.sib, qid, "p17") == value:
                out.append("siblings")
        body_props = ("P17",) if prop == "P17" else ("P1001", "P131")
        if any(value in f.bodies.get(b, {}).get(p, []) for b in values(ent, "P361") + values(ent, "P2389")
               for p in body_props):
            out.append("body")
    elif prop == "P279":
        if convention(f.sib, qid, "p279") == value:
            out.append("siblings")
        types = f.value_types.get(value, {value})
        if any(types & f.cat_classes.get(key, set()) for key in f.detected):
            out.append("category")
        if f.item["kind"] == "ambassador" and value == f.sender_class:
            out.append("category")
    elif prop == "P31":
        if convention(f.sib, qid, "meta") == value:
            out.append("siblings")
        joined = " | ".join(labels_text(ent))
        state = f.item["kind"] in ("national", "subnational", "predecessor", "ambassador") \
            and not countries.says(f.country.words.get("non_state", []), joined)
        if value == (PUBLIC_OFFICE if state else POSITION):
            out.append("state_office")
    return list(dict.fromkeys(out))


def conflict(prop: str, value: str, f: Facts) -> bool:
    """The labels name a value for P17/P1001, and it is not this one."""
    if prop not in ("P17", "P1001"):
        return False
    exp = expected_label(prop, f)
    return bool(exp) and value not in exp
