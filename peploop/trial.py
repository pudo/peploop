"""Replay a fixed sample of a pass's stored questions under another model, effort or thinking, and compare.

A cheaper setting is worth switching to when it answers what the stored
setting answered: each trial asks the same requests again (the prompt
unchanged, only the setting varied), compares the answers field by field
with the stored ones, and sets that beside the noise floor -- the stored
setting asked again on part of the sample, since a model re-asked does not
reproduce itself either. Nothing is written to any ledger; the run's budget
caps the spend.

    .venv/bin/python -m peploop.trial tree --n 120 --model claude-opus-5-5 --effort medium --baseline 40
"""

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable

import click
from pydantic import BaseModel

from peploop import db, llm, mint, prompt, verify
from peploop import extract as extraction
from peploop.tree import repair


@dataclass
class Case:
    """One stored question: its request (output format left out), the answer and what it cost."""

    request: dict[str, Any]
    answer: dict[str, Any]
    dollars: float


def sample(sql: str, args: tuple, n: int, seed: str) -> list[tuple]:
    """A fixed sample of rows: ordered by a hash of their first column and the seed."""
    rows = db.conn().execute(sql, args).fetchall()
    return sorted(rows, key=lambda r: hashlib.sha256(f"{seed}{r[0]}".encode()).hexdigest())[:n]


def tree_cases(n: int, seed: str) -> list[Case]:
    _, h = repair.system_prompt()
    rows = sample("SELECT key, request->>'message', answer, model, usage FROM ptree_call WHERE prompt_hash = %s",
                  (h,), n, seed)
    return [Case(repair.params(m, model), a, llm.cost(model, u) or 0) for _k, m, a, model, u in rows]


def mint_verify_cases(n: int, seed: str) -> list[Case]:
    _, h = mint.verify_prompt()
    rows = sample("SELECT content_key, request_json->>'message', response_json, model, usage_json FROM mint_call"
                  " WHERE pass = 'verify' AND prompt_hash = %s AND render_version = %s",
                  (h, mint.VERIFY_RENDER_VERSION), n, seed)
    return [Case(mint.verify_params(m, model), a, llm.cost(model, u) or 0) for _k, m, a, model, u in rows]


def categorize_cases(n: int, seed: str) -> list[Case]:
    _, h = mint.categorize_prompt()
    rows = sample("SELECT content_key, request_json->>'message', response_json, model, usage_json FROM mint_call"
                  " WHERE pass = 'categorize' AND prompt_hash = %s AND render_version = %s",
                  (h, mint.CATEGORIZE_RENDER_VERSION), n, seed)
    return [Case(mint.categorize_params(m, model), a, llm.cost(model, u) or 0) for _k, m, a, model, u in rows]


def extract_cases(n: int, seed: str) -> list[Case]:
    text, h = prompt.system_prompt()
    rows = sample("SELECT id, request_json, response_json, model, usage_json FROM extraction"
                  " WHERE prompt_hash = %s AND response_json IS NOT NULL", (h,), n, seed)
    out = []
    for _id, req, answer, model, u in rows:
        params = {**extraction.params(req["messages"][0]["content"]), "model": model}
        out.append(Case(params, {k: v for k, v in answer.items() if not k.startswith("_")}, llm.cost(model, u) or 0))
    return out


def verify_cases(n: int, seed: str) -> list[Case]:
    """Peploop's verifier keeps no request: each sampled row is rendered again from its proposal.

    Only rows whose proposal still renders to the stored key are kept, so the
    question is the one that was answered.
    """
    _, h = verify.system_prompt()
    rows = sample(
        "SELECT v.proposal_key, v.proposal_id, v.verdict, v.confidence, v.model, v.usage_json FROM verification v"
        " WHERE v.prompt_hash = %s AND v.render_version = %s AND v.usage_json IS NOT NULL",
        (h, verify.RENDER_VERSION), n * 3, seed)
    out = []
    for key, pid, verdict, confidence, model, u in rows:
        found = db.conn().execute(f"SELECT {', '.join(verify.ROW_COLUMNS)} FROM proposal WHERE id = %s",
                                  (pid,)).fetchone()
        if found is None:
            continue
        row = dict(zip(verify.ROW_COLUMNS, found))
        if verify.content_key(row["person_qid"], row["property"], row["value"], row.get("qualifiers")) != key:
            continue
        try:
            request = verify.request_for(verify.edit_for(row))
        except Exception:  # noqa: BLE001 -- a proposal that no longer renders is left out of the sample
            continue
        out.append(Case({**request, "model": model}, {"verdict": verdict, "confidence": confidence},
                        llm.cost(model, u) or 0))
        if len(out) == n:
            break
    return out


def compare_tree(a: dict[str, Any], b: dict[str, Any]) -> dict[str, bool]:
    out = {"scope": a["scope"]["kind"] == b["scope"]["kind"]}
    for p in ("P17", "P1001", "P279", "P31"):
        out[p] = a[p]["choice"] == b[p]["choice"]
    out["all"] = all(out.values())
    return out


def compare_mint_verify(a: dict[str, Any], b: dict[str, Any]) -> dict[str, bool]:
    return {"verdict": a["verdict"] == b["verdict"],
            "verdict+exists": (a["verdict"], a["exists_qid"]) == (b["verdict"], b["exists_qid"]),
            "shape": a["shape"] == b["shape"]}


def compare_categorize(a: dict[str, Any], b: dict[str, Any]) -> dict[str, bool]:
    def decisions(ans: dict[str, Any]) -> dict[str, str]:
        out = {g: "unassigned" for g in (u["group"] for u in ans["unassigned"])}
        for office in ans["offices"]:
            for g in office["groups"]:
                out[g] = office["decision"]
        return out

    def together(ans: dict[str, Any]) -> set[frozenset[str]]:
        return {frozenset(o["groups"]) for o in ans["offices"]}

    da, db_ = decisions(a), decisions(b)
    groups = set(da) | set(db_)
    same = sum(da.get(g) == db_.get(g) for g in groups)
    return {"decisions (all groups)": same == len(groups), "decisions >= 90%": same >= 0.9 * len(groups),
            "same clusters": together(a) == together(b)}


def compare_extract(a: dict[str, Any], b: dict[str, Any]) -> dict[str, bool]:
    def positions(ans: dict[str, Any]) -> set[tuple]:
        return {(p["title"].lower(), p.get("start")) for p in ans.get("positions", [])}

    def dates(ans: dict[str, Any], f: str) -> set[str]:
        return {d["value"] for d in ans.get(f, [])}

    pa, pb = positions(a), positions(b)
    return {"positions": pa == pb,
            "positions jaccard >= 0.8": len(pa & pb) >= 0.8 * max(len(pa | pb), 1),
            "birth": dates(a, "birth_date") == dates(b, "birth_date"),
            "death": dates(a, "death_date") == dates(b, "death_date")}


def compare_verify(a: dict[str, Any], b: dict[str, Any]) -> dict[str, bool]:
    passes = lambda x: x["verdict"] == verify.SUPPORTED and x["confidence"] != "low"  # noqa: E731
    return {"verdict": a["verdict"] == b["verdict"], "passes the gate": passes(a) == passes(b)}


#: Each pass: its cases, its answer schema, and how two answers are compared.
PASSES: dict[str, tuple[Callable[[int, str], list[Case]], type[BaseModel], Callable]] = {
    "tree": (tree_cases, repair.Answer, compare_tree),
    "mint:verify": (mint_verify_cases, mint.VerifyAnswer, compare_mint_verify),
    "mint:categorize": (categorize_cases, mint.CategorizeAnswer, compare_categorize),
    "extract": (extract_cases, extraction.Extraction, compare_extract),
    "verify": (verify_cases, verify.Answer, compare_verify),
}


def ask(pass_: str, cases: list[Case], schema: type[BaseModel], vary: Callable[[dict], dict],
        log: Callable[[str], None]) -> list[tuple[Case, dict[str, Any], float]]:
    """Ask each case under a varied request; return the case, the new answer and its cost."""
    got: list[tuple[Case, dict[str, Any], float]] = []

    def job(case: Case) -> llm.Job:
        request = vary(case.request)
        return llm.Job(request, schema,
                       lambda answer, usage: got.append((case, answer.model_dump(),
                                                         llm.cost(request["model"], usage) or 0)),
                       stream=request["max_tokens"] > 21_333)

    llm.run(f"trial:{pass_}", [job(c) for c in cases], log, workers=4, batch=False)
    return got


def report(name: str, got: list[tuple[Case, dict[str, Any], float]], compare: Callable) -> list[str]:
    if not got:
        return [f"{name}: nothing answered"]
    agree: Counter[str] = Counter()
    for case, answer, _ in got:
        for k, same in compare(case.answer, answer).items():
            agree[k] += same
    old = sum(c.dollars for c, _a, _d in got) / len(got)
    new = sum(d for _c, _a, d in got) / len(got)
    return [f"{name}: {len(got)} answered; $/call {new:.4f} against the stored {old:.4f} ({new / old - 1:+.0%})"
            if old else f"{name}: {len(got)} answered; $/call {new:.4f}"] + [
        f"  {k}: {v / len(got):.0%} agree with the stored answer" for k, v in agree.items()]


@click.command()
@click.argument("pass_", metavar="PASS", type=click.Choice(list(PASSES)))
@click.option("--n", default=100, show_default=True, help="Cases asked under the variant.")
@click.option("--baseline", default=0, show_default=True, help="Of those, how many to ask again as stored: the noise floor.")
@click.option("--model", help="The variant's model; the stored one when not given.")
@click.option("--effort", type=click.Choice(["low", "medium", "high", "xhigh", "max"]), help="The variant's effort.")
@click.option("--no-thinking", is_flag=True, help="Ask the variant with thinking disabled.")
@click.option("--budget", type=float, default=10.0, show_default=True, help="Dollars the trial may spend.")
@click.option("--seed", default="trial-2026-10-22", show_default=True, help="Which fixed sample.")
@click.option("--out", type=click.Path(dir_okay=False), help="Write every answer of both arms here, as JSON lines.")
def main(pass_: str, n: int, baseline: int, model: str | None, effort: str | None, no_thinking: bool,
         budget: float, seed: str, out: str | None) -> None:
    """Replay a fixed sample of one pass's stored questions under a cheaper setting, and compare."""
    llm.set_budget(budget)
    cases_of, schema, compare = PASSES[pass_]
    cases = cases_of(n, seed)
    click.echo(f"{pass_}: {len(cases)} cases from the ledger")

    def vary(request: dict[str, Any]) -> dict[str, Any]:
        out = dict(request)
        if model:
            out["model"] = model
        if effort:
            out["output_config"] = {**out.get("output_config", {}), "effort": effort}
        if no_thinking:
            out["thinking"] = {"type": "disabled"}
        return out

    label = " ".join(x for x in (model, effort and f"effort={effort}", no_thinking and "no thinking") if x)
    varied = ask(pass_, cases, schema, vary, click.echo)
    for line in report(f"variant ({label or 'as stored'})", varied, compare):
        click.echo(line)
    fresh: list[tuple[Case, dict[str, Any], float]] = []
    if baseline:
        fresh = ask(pass_, cases[:baseline], schema, dict, click.echo)
        for line in report("baseline (as stored)", fresh, compare):
            click.echo(line)
        # The variant against the stored setting asked today, on the same
        # cases: what a request's rendering has drifted since cancels out.
        by_case = {id(c): (a, d) for c, a, d in varied}
        paired = [(Case(c.request, a, d), *by_case[id(c)]) for c, a, d in fresh if id(c) in by_case]
        for line in report("variant against today's baseline", paired, compare):
            click.echo(line)
    if out:
        with open(out, "w") as fh:
            for arm, got in (("variant", varied), ("baseline", fresh)):
                for case, answer, dollars in got:
                    fh.write(json.dumps({"arm": arm, "stored": case.answer, "answer": answer, "dollars": dollars,
                                         "message": case.request["messages"][0]["content"][:300]},
                                        ensure_ascii=False, default=str) + "\n")
    click.echo(f"spent ${llm.spent():.2f}")


if __name__ == "__main__":
    main()
