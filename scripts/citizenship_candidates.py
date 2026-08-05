#!/usr/bin/env python
"""Prepare the citizenship-inference candidates for LLM verification.

    python scripts/citizenship_candidates.py

Takes the strong-majority tiers from holder_citizenship.json (>=3 holders
with P27 at >=80% majority, or 2-of-2 unanimous; top country modern, item
not abolished) and enriches each with the evidence a classifier needs:
holder samples (label + description — for the 60% of candidates without any
Wikipedia article, the holders ARE the evidence) and sitelink languages.

Output: data/jurisdictions/citizenship_candidates.json plus agent-sized
slices in data/jurisdictions/chunks_citizen/chunk_NN.json.
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.api import fetch_entities, sparql
from wd.http import REPO_ROOT, make_session

BASE = REPO_ROOT / "data" / "jurisdictions"
SAMPLE_MAX = 8
# Positions with more holders than this get their own LIMIT query instead of
# joining a grouped VALUES chunk (no per-group LIMIT in SPARQL):
GROUP_MAX_HOLDERS = 30
# WDQS is queried via GET; too many VALUES overflow the URI (HTTP 414):
GROUP_MAX_POSITIONS = 140

GROUP_QUERY = """
SELECT ?pos ?p ?pLabel ?pDesc WHERE {{
  VALUES ?pos {{ {values} }}
  ?p wdt:P39 ?pos .
  OPTIONAL {{ ?p schema:description ?pDesc . FILTER(LANG(?pDesc) = "en") }}
  SERVICE wikibase:label {{
    bd:serviceParam wikibase:language "en,mul,fr,es,sv,de,ru,nl,it,pt,da,no,pl,ja,zh" .
  }}
}}
"""

SINGLE_QUERY = """
SELECT ?pos ?p ?pLabel ?pDesc WHERE {{
  BIND(wd:{qid} AS ?pos)
  ?p wdt:P39 ?pos .
  OPTIONAL {{ ?p schema:description ?pDesc . FILTER(LANG(?pDesc) = "en") }}
  SERVICE wikibase:label {{
    bd:serviceParam wikibase:language "en,mul,fr,es,sv,de,ru,nl,it,pt,da,no,pl,ja,zh" .
  }}
}} LIMIT 12
"""


def is_candidate(r: dict) -> bool:
    top = r["top"]
    if top is None or top["historical"] or r["abolished"]:
        return False
    if r["with_p27"] >= 3 and top["share"] >= 0.8:
        return True
    return r["with_p27"] == 2 and top["share"] == 1.0


def patient(session, query: str, tries: int = 6, wait: float = 30.0) -> list[dict]:
    for attempt in range(tries):
        try:
            return sparql(session, query)
        except Exception as exc:
            print(f"  attempt {attempt + 1}/{tries}: {exc}", file=sys.stderr)
            if attempt + 1 < tries:
                time.sleep(wait)
    raise SystemExit("WDQS would not answer")


def group_fetch(session, qids: list[str]) -> list[dict]:
    """Grouped holder query with bisection: a chunk that times out during
    result serialization (truncated 200 body) fails deterministically, so
    retrying whole is useless — split it until WDQS can answer."""
    query = GROUP_QUERY.format(values=" ".join(f"wd:{q}" for q in qids))
    try:
        return patient(session, query, tries=2, wait=15.0)
    except SystemExit:
        if len(qids) == 1:
            return patient(session, SINGLE_QUERY.format(qid=qids[0]), tries=3)
        mid = len(qids) // 2
        print(f"  bisecting chunk of {len(qids)}", file=sys.stderr)
        return group_fetch(session, qids[:mid]) + group_fetch(session, qids[mid:])


def fetch_samples(session, rows: list[dict]) -> dict[str, list[dict]]:
    samples: dict[str, list[dict]] = {}

    def absorb(bindings: list[dict]) -> None:
        for b in bindings:
            entry = samples.setdefault(b["pos"], [])
            if len(entry) >= SAMPLE_MAX or any(s["qid"] == b["p"] for s in entry):
                continue
            label = b.get("pLabel")
            if label == b["p"]:  # label service echoes the QID when no label
                label = None
            entry.append({"qid": b["p"], "label": label, "desc": b.get("pDesc")})

    small = [r for r in rows if r["holders"] <= GROUP_MAX_HOLDERS]
    big = [r for r in rows if r["holders"] > GROUP_MAX_HOLDERS]

    chunk: list[str] = []
    budget = 0
    chunks: list[list[str]] = []
    for r in small:
        if chunk and (budget + r["holders"] > 4000
                      or len(chunk) >= GROUP_MAX_POSITIONS):
            chunks.append(chunk)
            chunk, budget = [], 0
        chunk.append(r["qid"])
        budget += r["holders"]
    if chunk:
        chunks.append(chunk)
    for i, qids in enumerate(chunks):
        absorb(group_fetch(session, qids))
        print(f"  sample chunk {i + 1}/{len(chunks)} ({len(qids)} positions)",
              file=sys.stderr)
    for i, r in enumerate(big):
        absorb(patient(session, SINGLE_QUERY.format(qid=r["qid"])))
        if (i + 1) % 50 == 0:
            print(f"  big positions {i + 1}/{len(big)}", file=sys.stderr)
    return samples


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", type=int, default=20)
    args = parser.parse_args()

    data = json.loads((BASE / "holder_citizenship.json").read_text())
    rows = [r for r in data if is_candidate(r)]
    print(f"{len(rows)} candidates", file=sys.stderr)

    session = make_session()
    samples = fetch_samples(session, rows)

    # Sitelink language codes tell the classifier where an article exists
    # (the census only kept a count):
    entities = fetch_entities(session, [r["qid"] for r in rows], props="sitelinks")
    wikis: dict[str, list[str]] = {}
    for qid, e in entities.items():
        keys = [k for k in e.get("sitelinks", {}) if k.endswith("wiki")]
        keys.sort(key=lambda k: (k != "enwiki", k))
        wikis[qid] = keys[:6]

    candidates = []
    for r in rows:
        candidates.append({
            "qid": r["qid"],
            "label": r["label"],
            "description": r["description"],
            "instance_of": [t["label"] or t["qid"] for t in r["instance_of"]],
            "holders": r["holders"],
            "with_p27": r["with_p27"],
            "inception": r["inception"],
            "citizenships": [
                {"qid": c["qid"], "label": c["label"], "code": c["code"], "n": c["n"]}
                for c in r["citizenships"][:6]
            ],
            "top": r["top"],
            "wikis": wikis.get(r["qid"], []),
            "holder_samples": samples.get(r["qid"], []),
        })

    (BASE / "citizenship_candidates.json").write_text(
        json.dumps(candidates, indent=1, ensure_ascii=False))

    # Sort by top country then size so each agent sees coherent clusters:
    candidates.sort(key=lambda c: (c["top"]["code"] or c["top"]["qid"], -c["holders"]))
    chunk_dir = BASE / "chunks_citizen"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    per = (len(candidates) + args.chunks - 1) // args.chunks
    for i in range(args.chunks):
        part = candidates[i * per : (i + 1) * per]
        (chunk_dir / f"chunk_{i:02d}.json").write_text(
            json.dumps(part, indent=1, ensure_ascii=False))
        print(f"chunk_{i:02d}: {len(part)}")
    no_article = sum(1 for c in candidates if not c["wikis"])
    no_sample = sum(1 for c in candidates if not c["holder_samples"])
    print(f"{len(candidates)} candidates, {no_article} without any wiki article, "
          f"{no_sample} without holder samples")
    print(f"Wrote {BASE / 'citizenship_candidates.json'} and {chunk_dir}/chunk_*.json")


if __name__ == "__main__":
    main()
