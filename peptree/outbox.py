"""Turn every country's latest proposals into paste-sized QuickStatements chunks, once each.

This is peptree's one export path. A country's run file says what it would add
*now*; the outbox says what has not gone out yet. A fix that re-renders twenty
countries therefore costs only its new statements, in the next chunk, and a
chunk never exceeds what one paste into the importer takes (300 commands).

    python -m peptree.cli outbox            # reconcile, then write new chunks
    python -m peptree.cli outbox --status   # chunks by status, and revert candidates

`ptree_emitted` holds one row per statement written to a chunk, keyed on the
statement itself (the line without its edit summary or retrieval date):

- `emitted` → `landed` once the statement is live on Wikidata (any rank). This
  is also the bootstrap: what earlier pastes put there is never emitted at all.
- `emitted` → `withdrawn` once no country proposes it and it is not live.
- A chunk none of whose lines has landed counts as unpasted. If one of its lines
  is withdrawn, the chunk is retired: its file is deleted and its other lines
  return to pending, so the next run writes them into a fresh chunk. Chunk
  numbers are never reused, and a written chunk is never edited.
- A landed statement on an item the load now drops (a fix found it is no office)
  is a revert candidate. It is listed and never acted on, because removals are a
  human gate. "No longer proposed" is no signal here: a landed statement closes
  its own gap, so no run re-decides it, and a wrong class (the Chief Minister of
  Anguilla made a minister) stays invisible to this list.
- A line of a pasted chunk that never lands (QS refused it) stays `emitted` and
  is listed by `--status`. It is not re-emitted on its own.
"""

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

from peptree import qs, sweep, wd

DIR = qs.OUT_DIR / "outbox"
#: Commands one paste into the QuickStatements importer takes.
CAP = 300
RETRIEVED = re.compile(r"\tS813\t\+\S+")


def key(line: str) -> str:
    """The statement a line adds, without the parts that vary run to run (summary, retrieval date)."""
    return RETRIEVED.sub("", qs.SUMMARY_RE.sub("", line)).strip()


def commands(line: str) -> int:
    """QS commands a line expands to: the statement, plus one for its references."""
    cols = qs.SUMMARY_RE.sub("", line).split("\t")
    return 1 + any(c.startswith("S") and c[1:].isdigit() for c in cols[3:])


def name(chunk: int) -> str:
    return f"peptree outbox chunk-{chunk:03d}"


def renamed(line: str, chunk: int) -> str:
    return qs.SUMMARY_RE.sub("", line) + f" /* {name(chunk)} */"


def chunked(lines: list[str], cap: int = CAP) -> list[list[str]]:
    """Fill chunks in order up to `cap` commands.

    A second value for one single-valued (item, property) waits for a later
    chunk, so every chunk passes `qs.validate`. Two countries may both propose
    a value for one item, as with a board shared by two islands.
    """
    out: list[list[str]] = []
    todo = list(lines)
    while todo:
        chunk, used, seen, rest = [], 0, set(), []
        for line in todo:
            item, prop, _ = qs.statements([line])[0]
            n = commands(line)
            if used + n > cap or (prop != "P279" and (item, prop) in seen):
                rest.append(line)
                continue
            chunk.append(line)
            used += n
            seen.add((item, prop))
        out.append(chunk)
        todo = rest
    return out


def transitions(emitted: dict[str, str], live: set[str], proposed: set[str]) -> dict[str, str]:
    """New status per emitted key: live → landed; neither live nor proposed → withdrawn."""
    out = {}
    for k, status in emitted.items():
        if status == "emitted" and k in live:
            out[k] = "landed"
        elif status == "emitted" and k not in proposed:
            out[k] = "withdrawn"
    return out


def retired(rows: list[tuple[str, int, str]]) -> set[int]:
    """Chunks to retire, from (key, chunk, status) rows: one with a withdrawn line and nothing landed."""
    by: dict[int, set[str]] = defaultdict(set)
    for _, chunk, status in rows:
        by[chunk].add(status)
    return {c for c, ss in by.items() if "withdrawn" in ss and "landed" not in ss}


# --- live state ----------------------------------------------------------------------

def live_keys(lines: list[str]) -> set[str]:
    """Keys of the lines whose statement Wikidata holds now, at any rank (read live)."""
    stmts = qs.statements(lines)
    ents = wd.fetch_items(sorted({q for q, _, _ in stmts}), props="claims")
    out = set()
    for line, (q, prop, value) in zip(lines, stmts):
        for claim in (ents.get(q) or {}).get("claims", {}).get(prop, []):
            v = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
            if isinstance(v, dict) and v.get("id") == value:
                out.add(key(line))
    return out


def proposals() -> dict[str, tuple[str, str]]:
    """key → (country, line) over every place's latest run file; the first country to propose wins."""
    out: dict[str, tuple[str, str]] = {}
    for cc in sorted(sweep.read()):
        path = qs.latest(cc)
        for line in path.read_text().splitlines() if path else []:
            if line.strip():
                out.setdefault(key(line), (cc, line))
    return out


# --- the run ----------------------------------------------------------------------

def rows() -> list[tuple[str, str, str, int, str]]:
    return wd.conn().execute("SELECT key, country, line, chunk, status FROM ptree_emitted").fetchall()


def path_of(chunk: int) -> Path:
    return DIR / f"chunk-{chunk:03d}.qs"


def run(log: Callable[[str], None] = print) -> list[Path]:
    """Reconcile the ledger against live state, retire stale chunks, write the pending lines."""
    con = wd.conn()
    props = proposals()
    have = rows()
    emitted = {k: s for k, _, _, _, s in have}
    live = live_keys([line for k, _, line, _, s in have if s == "emitted"])
    moved = transitions(emitted, live, set(props))
    for k, status in moved.items():
        con.execute("UPDATE ptree_emitted SET status = %s, status_at = now() WHERE key = %s", (status, k))
    log(f"reconciled: {Counter(moved.values()) or 'nothing moved'}")
    stale = {c for c in retired([(k, c, moved.get(k, s)) for k, _, _, c, s in have]) if path_of(c).exists()}
    for c in sorted(stale):
        path_of(c).unlink(missing_ok=True)
        con.execute("DELETE FROM ptree_emitted WHERE chunk = %s AND status = 'emitted'", (c,))
        log(f"retired chunk {c:03d}: a line was withdrawn before it was pasted")
    taken = {k for k, *_ in rows()}
    pending = {k: v for k, v in props.items() if k not in taken}
    live_now = live_keys([line for _, line in pending.values()])
    pending = {k: v for k, v in pending.items() if k not in live_now}
    log(f"proposed {len(props)}, already out {len(taken & set(props))}, live {len(live_now)}, pending {len(pending)}")
    order = sorted(pending.values(), key=lambda cl: (cl[0], cl[1]))
    first = max([c for *_, c, _ in rows()] + [int(p.stem[6:]) for p in DIR.glob("chunk-*.qs")], default=0) + 1
    written = []
    by_line = {line: cc for cc, line in order}
    for i, chunk in enumerate(chunked([line for _, line in order])):
        n = first + i
        lines = [renamed(line, n) for line in chunk]
        errors = qs.validate(lines)
        ok, detail, cmds = qs.parse_commands("\n".join(lines))
        if errors or not ok or len(cmds) > CAP:
            sys.exit(f"chunk {n:03d} refused ({len(cmds)} commands): {errors[:5] or detail}")
        DIR.mkdir(parents=True, exist_ok=True)
        path_of(n).write_text("\n".join(lines) + "\n")
        with con.transaction():
            for raw, line in zip(chunk, lines):
                con.execute("INSERT INTO ptree_emitted (key, country, line, chunk) VALUES (%s,%s,%s,%s)",
                            (key(raw), by_line[raw], line, n))
        written.append(path_of(n))
        log(f"{path_of(n)}: {len(lines)} lines, {len(cmds)} commands")
    return written


def status() -> str:
    have = rows()
    out = ["| chunk | file | emitted | landed | withdrawn |", "|---|---|---|---|---|"]
    by: dict[int, Counter] = defaultdict(Counter)
    for _, _, _, c, s in have:
        by[c][s] += 1
    for c in sorted(by):
        out.append(f"| {c:03d} | {'yes' if path_of(c).exists() else 'retired'} | {by[c]['emitted']} | "
                   f"{by[c]['landed']} | {by[c]['withdrawn']} |")
    pasted = {c for c, n in by.items() if n["landed"]}
    stuck = [(c, line) for _, _, line, c, s in have if s == "emitted" and c in pasted]
    out += ["", f"## Pasted but not live ({len(stuck)})", ""] + [f"- {c:03d}: {line}" for c, line in stuck]
    dropped = set(wd.conn().execute("SELECT country, qid FROM ptree_item WHERE dropped IS NOT NULL").fetchall())
    gone = [(c, cc, line) for _, cc, line, c, s in have
            if s == "landed" and (cc, qs.statements([line])[0][0]) in dropped]
    out += ["", f"## Landed on an item the load now drops: revert candidates ({len(gone)})", ""]
    out += [f"- {c:03d} {cc}: {line}" for c, cc, line in gone]
    return "\n".join(out)


def main(args: list[str]) -> None:
    if args == ["--status"]:
        print(status())
    elif not args:
        log = lambda m: print(m, file=sys.stderr, flush=True)  # noqa: E731
        paths = run(log)
        print("\n".join(str(p) for p in paths) or "nothing pending")
    else:
        sys.exit("usage: outbox [--status]")
