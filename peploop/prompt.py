"""Render the two halves of one extraction request.

The system prompt is a file, frozen and hashed into every `extraction` row.
Everything that varies per person — the Wikidata state we already hold and the
article texts — goes into the user message, after the cached prefix.
"""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping

from rigour.langs import iso_639_alpha2
from rigour.territories import get_territory_by_qid

from peploop import dates, db, llm, wikidata

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "extract.md"

# A character heuristic, not a tokenizer: the budget only decides how many
# whole articles are sent, and count_tokens would cost a request per person.
# Inflected languages in Latin script run about two characters per token; the
# constant is conservative for English.
TOKEN_CHARS = 2.0
TOKEN_BUDGET = 60_000

QID_PROPS = {
    "P31": "instance of",
    "P21": "sex or gender",
    "P27": "country of citizenship",
    "P19": "place of birth",
}
TIME_PROPS = {"P569": "date of birth", "P570": "date of death"}
POSITION_PROP = "P39"
PRECISION_NAMES = {11: "day", 10: "month", 9: "year", 8: "decade", 7: "century"}


@dataclass
class Article:
    """One Wikipedia article as it will be sent to the model."""

    lang: str
    title: str
    rev_id: int | None
    url: str
    text: str

    @property
    def key(self) -> str:
        """Identify the article revision, for the extraction cache key."""
        return f"{self.lang}:{self.rev_id}"


@lru_cache(maxsize=1)
def system_prompt() -> tuple[str, str]:
    """Read the frozen system prompt and return it with its sha256 hash."""
    return llm.system_prompt(PROMPT_PATH)


def format_time(value: str, precision: int, name_day: bool = True) -> str:
    """Render a Wikidata time value at the precision it claims.

    A precision below 9 means the value is coarser than a year, so the year
    digits it carries are not a year. `name_day=False` drops the "(day)" from
    a full date, where the shape of the value already says what it is; a
    coarser value keeps its name however it is rendered.
    """
    match = dates.TIME_RE.match(value.lstrip("+"))
    name = PRECISION_NAMES.get(precision, f"precision {precision}")
    if match is None:
        return f"{value} ({name})"
    year, month, day = match.groups()
    if precision >= 11:
        return f"{year}-{month}-{day}" + (f" ({name})" if name_day else "")
    if precision == 10:
        return f"{year}-{month} ({name})"
    return f"{year} ({name})"


def qualifier_time(claim: dict[str, Any], prop: str) -> dict[str, Any] | None:
    """Return the first time datavalue of a qualifier on a statement."""
    for snak in claim.get("qualifiers", {}).get(prop, []):
        value = snak.get("datavalue", {}).get("value")
        if isinstance(value, dict) and "time" in value:
            return value
    return None


def state_qids(entity: dict[str, Any]) -> list[str]:
    """List every QID whose label the state block needs, for one batch fetch."""
    qids = [q for prop in QID_PROPS for q in wikidata.claim_qids(entity, prop)]
    qids.extend(wikidata.claim_qids(entity, POSITION_PROP))
    return list(dict.fromkeys(qids))


def named(qid: str, labels: dict[str, str | None], label_first: bool = False) -> str:
    """Render a QID beside its label, or bare when no label was fetched.

    The prompt puts the QID first, because that is what the model answers
    with; `label_first` puts the words first, which is how a reader scans a
    column of them.
    """
    label = labels.get(qid)
    if not label:
        return qid
    return f"{label} {qid}" if label_first else f"{qid} {label}"


def render_state(entity: dict[str, Any], labels: dict[str, str | None]) -> str:
    """Render what Wikidata already records about the person, compactly.

    The model is told this is for recognition: a value already here is only
    reported back when an article refines or disputes it.
    """
    lines = [f"QID: {entity.get('id', '')}"]
    names = {lang: obj["value"] for lang, obj in entity.get("labels", {}).items()}
    lines.append("labels: " + ("; ".join(f"{k}={v}" for k, v in sorted(names.items())) or "—"))
    for prop, name in QID_PROPS.items():
        values = [named(q, labels) for q in wikidata.claim_qids(entity, prop)]
        lines.append(f"{prop} {name}: " + ("; ".join(values) or "—"))
    for prop, name in TIME_PROPS.items():
        values = [format_time(v, p) for v, p in wikidata.claim_time(entity, prop)]
        lines.append(f"{prop} {name}: " + ("; ".join(values) or "—"))
    held = entity.get("claims", {}).get(POSITION_PROP, [])
    lines.append(f"{POSITION_PROP} position held: " + ("" if held else "—"))
    for claim in held:
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if not isinstance(value, dict) or "id" not in value:
            continue
        start = qualifier_time(claim, "P580")
        end = qualifier_time(claim, "P582")
        span = ""
        if start or end:
            edges = [
                format_time(v["time"], v.get("precision", 0)) if v else "?" for v in (start, end)
            ]
            span = f" [{edges[0]} → {edges[1]}]"
        lines.append(f"  - {named(value['id'], labels)}{span}")
    return "\n".join(lines)


def country_langs(seed_lang: str | None, entity: dict[str, Any]) -> list[str]:
    """List the languages of the country this person belongs to.

    Which wiki to read is a property of the person, not of a global ranking:
    the category that found them comes first, then the languages spoken in the
    countries they are recorded as a citizen of.
    """
    langs = [seed_lang] if seed_lang else []
    for qid in wikidata.claim_qids(entity, "P27"):
        territory = get_territory_by_qid(qid)
        if territory is None:
            continue
        langs.extend(iso_639_alpha2(lang) for lang in territory.langs)
    return list(dict.fromkeys(lang for lang in langs if lang and lang != "en"))


def wiki_order(
    langs: Iterable[str], seed_lang: str | None, entity: dict[str, Any], *,
    home_first: bool = False, sizes: Mapping[str, int] | None = None,
) -> list[str]:
    """Order a person's wikis by how much they are worth reading or citing.

    The one ranking behind both which articles the model reads and which one
    a written statement cites. English, then the country's own languages
    (`country_langs`), then the rest longest article first (`sizes`, in
    characters). `home_first` puts English after the country's languages:
    a statement cites the person's home wiki where one attests it. Each
    language appears once; ties keep the order given.
    """
    home = country_langs(seed_lang, entity)
    preferred = [*home, "en"] if home_first else ["en", *home]
    distinct = list(dict.fromkeys(langs))
    known = [lang for lang in preferred if lang in distinct]
    rest = sorted((lang for lang in distinct if lang not in preferred),
                  key=lambda lang: -(sizes or {}).get(lang, 0))
    return known + rest


def select_articles(
    qid: str, seed_lang: str | None, entity: dict[str, Any]
) -> tuple[list[Article], list[str]]:
    """Order this person's articles and pack them into the token budget.

    In `wiki_order`: English first where it exists, then the country's own
    languages, then the rest longest first. The English article and the first
    country-language article go regardless of budget, because they are the two
    the extraction is worth doing at all on; after them packing stops at the
    first article that does not fit rather than skipping ahead to a shorter
    one. An article left out is dropped whole, never truncated, and its
    language is returned so the extraction row records what was left out.
    """
    rows = db.conn().execute(
        "SELECT lang, title, rev_id, url, text FROM article WHERE qid = %s", (qid,)
    )
    articles = [Article(*row) for row in rows]
    order = wiki_order((a.lang for a in articles), seed_lang, entity,
                       sizes={a.lang: len(a.text) for a in articles})
    ordered = sorted(articles, key=lambda article: order.index(article.lang))
    home = set(country_langs(seed_lang, entity))
    first_en = next((a for a in ordered if a.lang == "en"), None)
    first_own = next((a for a in ordered if a.lang in home), None)
    mandatory = {id(a) for a in (first_en, first_own) if a is not None}

    kept: list[Article] = []
    dropped: list[str] = []
    used, full = 0.0, False
    for article in ordered:
        cost = len(article.text) / TOKEN_CHARS
        if id(article) not in mandatory and (full or used + cost > TOKEN_BUDGET):
            full = True
            dropped.append(article.lang)
            continue
        kept.append(article)
        used += cost
    return kept, dropped


def render_user_message(state: str, articles: list[Article]) -> str:
    """Render the per-person half of the request: the state, then the articles."""
    parts = ["# The Wikidata item as it stands", "", state, "", "# The articles"]
    for article in articles:
        parts.append("")
        parts.append(
            f"```article lang={article.lang} title={article.title!r} "
            f"rev={article.rev_id} url={article.url}"
        )
        parts.append(article.text.strip())
        parts.append("```")
    return "\n".join(parts)
