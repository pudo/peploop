"""The mechanical channels a model's answer must agree with.

Each channel looks at one item and a proposed value and says whether it, on
its own evidence, supports that value:

- `label`: the item's labels name the value (country, predecessor, a place of
  the type the label's words name, receiving state). A name the state shares
  with a predecessor names whichever of them the office's era allows, and
  neither when both fit;
- `holders`: most holders are citizens of the proposed country, counting only
  those whose tenure lies inside that country's span;
- `body`: the body the office sits in (`P361`/`P2389`) carries that value in
  `P17` or `P1001` (never `P131`: where a body sits is not what it governs);
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
CITY = "Q515"


SUBNATIONAL = {"region", "district", "local"}


class Places:
    """The gazetteer, indexed for whole-word lookups."""

    def __init__(self, places: list[dict[str, Any]]) -> None:
        self.places = {p["qid"]: p for p in places}
        #: A place word, and the same word less its last two letters (for an inflected ending).
        self.word_index: dict[str, set[str]] = defaultdict(set)
        for p in places:
            if set(p["levels"]) & (SUBNATIONAL | {"country", "predecessor"}):
                for need in p["words"]:
                    for w in need:
                        self.word_index[w].add(w)
                        if len(w) >= countries.ENDING_FROM:
                            self.word_index[w[:-2]].add(w)

    def is_place_token(self, tok: str) -> bool:
        cands = set().union(*(self.word_index.get(tok[:k], set()) for k in range(1, len(tok) + 1)))
        return any(countries.word_match(tok, w) for w in cands)

    def mentioned(self, text: str, levels: set[str], types: set[str] | None = None) -> list[str]:
        """The places of `levels` (and of one of `types`, closure included) the text names.

        A name matched only by an inflection yields to another candidate's
        name matched more tightly on the same words (`country.tightest`).
        """
        toks = countries.tokens(text)
        found = {q: m for q, p in self.places.items()
                 if set(p["levels"]) & levels and (types is None or set(p.get("classes", [])) & types)
                 and (m := countries.place_match(p, toks))}
        keep = countries.tightest(found)
        return [q for q in found if q in keep]

    def of_type(self, text: str, types: set[str]) -> list[str]:
        """Subnational places the text names that are of one of `types` (closure included)."""
        return self.mentioned(text, SUBNATIONAL, types)


def labels_text(entity: dict[str, Any]) -> list[str]:
    """Every label, in every language: an item labelled only in Polish still names its state."""
    return [o["value"] for o in entity.get("labels", {}).values()]


def shape(text: str, places: Places) -> str:
    """A label with its place names and numbers masked: siblings share one."""
    out = []
    for tok in countries.tokens(text):
        out.append("#" if tok.isdigit() or places.is_place_token(tok) else tok)
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


# --- eras --------------------------------------------------------------------------

Span = tuple[int | None, int | None]


def holder_tenure(row: dict[str, Any]) -> Span:
    """When one holder held the office: the tenure, or failing that the adult life.

    An end that is not known is None (open) for a holder with no death
    year: they may hold it still.
    """
    s, e, b, d = row.get("s"), row.get("e"), row.get("b"), row.get("d")
    start = s if s is not None else e if e is not None else (b + 18 if b is not None else d)
    end = e if e is not None else d
    return start, end


def office_span(item: dict[str, Any], lives: bool = True) -> Span:
    """When the office was active: `P571`/`P576`, else its holders' tenures, else their lives.

    (None, None) when nothing dates it. The end is None (open) when any
    holder may hold it still. `lives=False` leaves out holders whose tenure
    is undated: a life outlasts an office by decades, which is harmless
    for a veto but not for saying the office outlasted a state.
    """
    ent = item.get("entity", {})
    p571, p576 = countries.years(ent, "P571"), countries.years(ent, "P576")
    rows = item.get("holder_rows") or []
    if not lives:
        rows = [r for r in rows if r.get("s") is not None or r.get("e") is not None]
    tenures = [holder_tenure(r) for r in rows]
    starts = [s for s, _ in tenures if s is not None]
    start = min(p571) if p571 else (min(starts) if starts else None)
    if p576:
        end = max(p576)
    elif not tenures or any(e is None for _, e in tenures):
        end = None
    else:
        end = max(e for _, e in tenures)
    if start is None and end is None and not p571 and not tenures:
        return None, None
    return start, end


def overlaps(a: Span, b: Span) -> bool:
    """Whether two year spans share a year; an unknown bound reaches as far as needed."""
    (s1, e1), (s2, e2) = a, b
    return not ((e1 is not None and s2 is not None and e1 < s2) or (e2 is not None and s1 is not None and e2 < s1))


def known(span: Span | None) -> bool:
    return span is not None and (span[0] is not None or span[1] is not None)


def inside(row: dict[str, Any], span: Span) -> bool:
    """Whether a holder's tenure lies inside a state's span (a year's slack at each end).

    A holder with no tenure dates is judged by their life overlapping the
    span; one with no dates at all is not excluded.
    """
    s, e = row.get("s"), row.get("e")
    lo, hi = span
    if s is not None or e is not None:
        ts, te = (s if s is not None else e), (e if e is not None else s)
        return (lo is None or ts >= lo - 1) and (hi is None or te <= hi + 1)
    b, d = row.get("b"), row.get("d")
    if b is None and d is None:
        return True
    return overlaps(((b + 18) if b is not None else None, d), span)


@dataclass
class Facts:
    """What the channels read about one item, gathered by the caller."""

    item: dict[str, Any]
    country: countries.Country
    places: Places
    sib: Siblings
    detected: set[str] = field(default_factory=set)
    #: Body qid → its P17/P1001 values.
    bodies: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    #: Category key → class qids, and the closure of each candidate value.
    cat_classes: dict[str, set[str]] = field(default_factory=dict)
    value_types: dict[str, set[str]] = field(default_factory=dict)
    sender_class: str | None = None
    #: Candidate value → (first, last year), beyond the country's own states.
    value_spans: dict[str, list[int | None]] = field(default_factory=dict)
    #: Candidate values read and found not to be typed a state: never a `P17`.
    non_states: set[str] = field(default_factory=set)
    #: Items other items name in `P279`: classes of office, never typed an office themselves.
    classes: set[str] = field(default_factory=set)
    #: Stem sequences of the head-of-state and head-of-government class names, every language.
    head_seqs: list[list[str]] = field(default_factory=list)

    @property
    def span(self) -> Span:
        return office_span(self.item)

    def value_span(self, value: str) -> Span | None:
        found = self.country.spans.get(value) or self.value_spans.get(value)
        return (found[0], found[1]) if found else None


def era_ok(f: Facts, value: str) -> bool:
    """Whether the value existed while the office did (True when either is undated)."""
    vs, os_ = f.value_span(value), f.span
    return not (known(vs) and known(os_)) or overlaps(vs, os_)


def embedded_head(f: Facts, text: str) -> bool:
    """Whether the state's name in this label belongs to another office it names.

    "Rector of the Academy … under the President of the Republic of X": a
    head-of-state or head-of-government title that does not lead the label
    (deputy words aside) and comes before the state's name makes that name
    the title's, not the office's jurisdiction.
    """
    raw = TOKEN.findall(text)
    stem_at = [next(iter(countries.stems(t)), None) for t in raw]
    idx = [i for i, st in enumerate(stem_at) if st]
    k = countries.deputy_lead(f.country, [stem_at[i] for i in idx])
    own = [w for w in (countries.words(n) for n in f.country.names.get(f.country.qid, [])) if w]
    for j in range(k + 1, len(idx)):
        for need in f.head_seqs:
            here = [stem_at[i] for i in idx[j:j + len(need)]]
            if need and len(here) == len(need) and all(t.startswith(n) for t, n in zip(here, need)):
                after = countries.tokens(" ".join(raw[idx[j]:]))
                if any(countries.has_words(w, after) for w in own):
                    return True
    return False


def era_states(f: Facts, text: str) -> set[str]:
    """The home states a label names whose span the office's overlaps.

    A federation's names count only for a predecessor's office: its
    colloquial names (a nickname that is also the word for "council") are
    words a council's label uses. When
    a name fits the state and a predecessor alike and the office outlasted
    the predecessor, the office is the state's: one item for an office that
    crossed the change of state takes the current state.
    """
    c = f.country
    named = {q for q in countries.named_states(c, text) if era_ok(f, q)}
    if f.item["kind"] != "predecessor":
        named -= c.unions
    dated = office_span(f.item, lives=False)
    if c.qid in named and len(named) > 1 and known(dated):
        end = dated[1]
        others = [f.value_span(q) for q in named - {c.qid}]
        if all(o is not None and o[1] is not None and (end is None or end > o[1]) for o in others):
            return {c.qid}
    return named


def label_states(f: Facts, texts: list[str], to_value: Any) -> set[str] | None:
    """The one value the labels name, read label by label; None when they name none or disagree.

    A label naming two states (a name the state shares with a predecessor)
    decides nothing; a label naming one does, unless another label names a
    different one.
    """
    picks, ambiguous = set(), False
    for t in texts:
        named = {v for v in (to_value(q) for q in era_states(f, t)) if v}
        if len(named) == 1:
            picks |= named
        elif named:
            ambiguous = True
    if len(picks) == 1:
        return picks
    return None if picks or ambiguous else set()


def expected_label(prop: str, f: Facts) -> set[str] | None:
    """The values the labels name for P17/P1001, or None when they name none or are ambiguous."""
    texts = labels_text(f.item["entity"])
    joined = " | ".join(texts)
    c = f.country
    if f.item["kind"] == "ambassador":
        if prop != "P17":
            return None
        found = set(f.places.mentioned(joined, {"country"})) - c.home
        return found or None
    pred = countries.named_predecessor(c, joined) if f.item["kind"] == "predecessor" else None

    def state_of(q: str) -> str:  # the P17 a home state's office carries
        return c.predecessors.get(q, q)

    if prop == "P17":
        if pred:
            return {c.predecessors[pred]}
        named = label_states(f, texts, state_of)
        if named is None or named:
            return named or None  # one state named, or a shared name the era cannot settle
        if f.places.mentioned(joined, SUBNATIONAL) and era_ok(f, c.qid):
            return {c.qid}
        return None
    types: set[str] = set()
    for t in texts:
        types |= countries.level_types(c, t)
    if types:
        found = set(f.places.of_type(joined, types))
        return found or None
    if f.item["kind"] == "subnational":
        # A mayor's or a city's office names its city ("Mayor of <city>"):
        # for a mayor, or when every place the label may name is a city.
        cities = set(f.places.of_type(joined, {CITY}))
        loose = {q for q, p in f.places.places.items()
                 if set(p["levels"]) & SUBNATIONAL and countries.mentions(p, joined)}
        if cities and (countries.is_mayor(c, joined) or all(CITY in f.places.places[q].get("classes", []) for q in loose)):
            return cities
    if pred:
        return {pred}
    # The jurisdiction is a state the label names in its own right, not as
    # part of another office's title ("… under the President of X").
    own = [t for t in texts if not embedded_head(f, t)]
    named = label_states(f, own, lambda q: None if q in c.unions else q)
    return named or None


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
            if value in f.country.p17_values and contemporary_share(f, value) >= 2 / 3:
                out.append("holders")
            if convention(f.sib, qid, "p17") == value:
                out.append("siblings")
        body_props = (prop,)
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


def contemporary_share(f: Facts, value: str) -> float:
    """The share of holders who are citizens of `value` and held the office while it existed.

    0 below two holders. Holders read before holder rows were stored count by
    citizenship alone.
    """
    n = f.item.get("holders") or 0
    if n < 2:
        return 0.0
    rows = f.item.get("holder_rows")
    if not rows:
        return (f.item.get("holder_countries") or {}).get(value, 0) / n
    span = f.value_span(value) or (None, None)
    return sum(1 for r in rows if value in r.get("c", []) and inside(r, span)) / n


def conflict(prop: str, value: str, f: Facts) -> bool:
    """The labels name a value for P17/P1001, and it is not this one."""
    if prop not in ("P17", "P1001"):
        return False
    exp = expected_label(prop, f)
    return bool(exp) and value not in exp
