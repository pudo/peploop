"""Ask and check a fixed set of bodies and compare each outcome with the one expected.

A prompt or rule change is tried on known cases before a country is planned
again: the regression set (`eval/*.yml`) names bodies and the statement
each should or should not get. The bodies go through the same asking and
checks as a run (`decide.decide`, `run.plan`); nothing is written but the
answer ledger: no run file, no report, no decision rows, no removals.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

from peploop import llm
from peploop.corp import decide, run, wd


def outcome(case: dict[str, Any], decisions: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    """What became of a case: a gate's rule or `pass`, else `write`, a statement's rule or `absent`."""
    rows = [d for d in decisions if d["qid"] == case["qid"]]
    if "prop" not in case:
        gate = next((d for d in rows if d["prop"] == "-"), None)
        return (gate["rule"] if gate else "pass" if rows else "absent"), {}
    hits = [d for d in rows if d["prop"] == case["prop"] and (case.get("value") in ("*", d["value"]))]
    written = [d for d in hits if d["disposition"] == "apply"]
    if written:
        return "write", written[0]["detail"]
    return (hits[0]["rule"] if hits else "absent"), {}


def passes(case: dict[str, Any], got: str, detail: dict[str, Any]) -> bool:
    want = case["expect"] if isinstance(case["expect"], list) else [case["expect"]]
    ok = got in want or ("skip" in want and got != "write") or (
        "gated" in want and got not in ("pass", "absent", "write"))
    if got == "write":
        times = {p: (detail.get(p) or {}).get("time", "").lstrip("+") for p in ("P580", "P582")}
        if case.get("dated") and not any(times.values()):
            ok = False
        for prop, prefix in (case.get("forbid") or {}).items():
            if times.get(prop, "").startswith(str(prefix)):
                ok = False
    return ok


def evaluate(path: Path, log: Callable[[str], None] = print) -> list[dict[str, Any]]:
    """Ask and check every body of the set; return each case with what it got."""
    cases = yaml.safe_load(path.read_text())
    started = datetime.now(timezone.utc)
    out = []
    for cc in sorted({c["cc"] for c in cases}):
        mine = [c for c in cases if c["cc"] == cc]
        qids = {c["qid"] for c in mine}
        log(f"{cc}: {len(qids)} bodies")
        asked = {r["qid"] for r in decide.decide(cc, log=log, only=qids)}
        # The country's other answers are the context the rules plan against
        # (a holder this run finds state-controlled); only the set is checked.
        _, decisions, _ = run.plan(cc, decide.from_ledger(cc), log, checked=qids)
        for c in mine:
            got, detail = outcome(c, decisions)
            out.append({**c, "got": got, "ok": passes(c, got, detail), "asked": c["qid"] in asked})
    rows = wd.conn().execute(
        "SELECT model, usage FROM pcorp_call WHERE created_at >= %s AND qid = ANY(%s)",
        (started, sorted({c["qid"] for c in cases}))).fetchall()
    log(f"spend: ${sum(llm.cost(m, u) or 0.0 for m, u in rows):.2f} on {len(rows)} calls")
    return out


def table(results: list[dict[str, Any]]) -> str:
    lines = [f"{'':4} {'cc':3} {'qid':11} {'prop':5} {'value':11} {'expected':24} {'got':22} why"]
    for r in results:
        want = r["expect"] if isinstance(r["expect"], str) else "|".join(r["expect"])
        flags = (" dated" if r.get("dated") else "") + "".join(f" !{p}={v}" for p, v in (r.get("forbid") or {}).items())
        lines.append(f"{'ok' if r['ok'] else 'FAIL':4} {r['cc']:3} {r['qid']:11} {r.get('prop', '-'):5} "
                     f"{r.get('value', '') or '':11} {want + flags:24} {r['got'] + ('' if r['asked'] else ' (old)'):22} "
                     f"{r.get('why', '')}")
    passed = sum(r["ok"] for r in results)
    lines.append(f"{passed}/{len(results)} as expected")
    return "\n".join(lines)
