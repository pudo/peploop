"""Check each owner and parent link against its quote before it is written.

The decision call reads a whole article and sometimes takes funding, a
body's working level or supervision for ownership. A link is what readers
take as control, so each one the rules would write gets a second, narrow
look: the two bodies and the quote, nothing else. A link refused on its own
quote is checked again against the answer's control quote; one refused on
both is skipped; the rest of the body's answer stands. Answers are kept in
`pcorp_call` by content, like the decisions, so a re-run pays only for new
links.
"""

import concurrent.futures as cf
import os
from pathlib import Path
from typing import Any, Callable

from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict

from peploop import llm, memo
from peploop.corp import decide, wd

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "verify_link.md"
MODEL = os.environ.get("PEPCORP_VERIFY_MODEL", "claude-sonnet-5-5")
RELATIONS = {"P127": "owner", "P749": "parent"}


class Verdict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supports: bool
    reason: str


def message(body: str, target: str, relation: str, quote: str, names: dict[str, str]) -> str:
    return "\n".join([
        f"Body: {body} ({names.get(body, '')})",
        f"Public body: {target} ({names.get(target, '')})",
        f"Link: {relation}",
        "Passage:",
        quote,
    ])


def ask(text: str) -> tuple[Verdict, dict[str, int]]:
    system, _ = llm.system_prompt(PROMPT_PATH)
    response = llm.client().messages.parse(
        model=MODEL, max_tokens=1000, output_config={"effort": "low"},
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": text}], output_format=Verdict)
    if response.parsed_output is None:
        raise RuntimeError(f"no parsed output ({response.stop_reason})")
    return response.parsed_output, llm.usage(response)


def refused(cc: str, decisions: list[dict[str, Any]], answered: list[dict[str, Any]],
            log: Callable[[str], None] = print) -> set[tuple[str, str, str]]:
    """The (body, property, target) links whose quote the check does not accept."""
    reqs = {r["qid"]: r for r in answered}
    links = [(d["qid"], d["prop"], d["value"]) for d in decisions
             if d["disposition"] == "apply" and d["prop"] in RELATIONS]
    if not links:
        return set()
    names = {q: decide.memo_name(i) for q, i in memo.labels_of(sorted({x for l in links for x in (l[0], l[2])}),
                                                               ("en", "mul")).items()}
    _, prompt_hash = llm.system_prompt(PROMPT_PATH)
    # Each link is checked against the owner's own quote, then, if that one
    # is refused, against the answer's control quote: an answer sometimes
    # gives the plain sentence ("belongs wholly to the canton") as the
    # control quote and a weaker one for the owner.
    quotes: dict[tuple[str, str, str], list[str]] = {}
    for qid, prop, target in links:
        req = reqs[qid]
        control = req["answer"]["control"]
        quote = next((o["quote"] for o in control["owners"]
                      if o["relation"] == RELATIONS[prop]
                      and (o["controller"] is not None and 0 <= o["controller"] < len(req["offered"])
                           and req["offered"][o["controller"]] == target or o["controller"] is None)), "")
        quotes[(qid, prop, target)] = list(dict.fromkeys(q for q in (quote, control.get("quote") or "") if q)) or [""]

    def key_text(link: tuple[str, str, str], quote: str) -> tuple[str, str]:
        text = message(link[0], link[2], RELATIONS[link[1]], quote, names)
        return decide.content_key(MODEL, prompt_hash, text), text

    def one(link: tuple[str, str, str], key: str, text: str) -> None:
        if decide.recorded(key) is not None:
            return
        verdict, usage = ask(text)
        wd.conn().execute(
            "INSERT INTO pcorp_call (key, country, qid, model, prompt_hash, request, answer, usage)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (key) DO NOTHING",
            (key, cc, link[0], MODEL, prompt_hash, Jsonb({"message": text, "link": list(link)}),
             Jsonb(verdict.model_dump()), Jsonb(usage)))

    out = set(links)
    for attempt in range(2):
        jobs = {link: key_text(link, qs[attempt]) for link, qs in quotes.items() if link in out and len(qs) > attempt}
        with cf.ThreadPoolExecutor(decide.WORKERS) as ex:
            for fut in cf.as_completed([ex.submit(one, link, *kt) for link, kt in jobs.items()]):
                try:
                    fut.result()
                except Exception as exc:  # one failed check leaves its link unwritten, not the run
                    log(f"  link check failed: {exc}")
        for link, (key, _) in jobs.items():
            verdict = decide.recorded(key)
            if verdict is not None and verdict.get("supports"):
                out.discard(link)
    log(f"{len(quotes)} links checked against their quotes; {len(out)} refused")
    return out
