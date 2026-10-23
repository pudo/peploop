"""Pin the cost tally: list-price dollars per call, grouping, and calls on unpriced models.

    .venv/bin/python -m peploop.check_costs
"""

from datetime import datetime

from peploop import costs
from peploop.checks import expect

MONDAY = datetime(2026, 10, 19, 12)


def main() -> None:
    usage = {"input_tokens": 1_000_000, "cache_read_input_tokens": 1_000_000,
             "cache_creation_input_tokens": 0, "output_tokens": 100_000}
    rows = [
        ("resolve", "claude-sonnet-5", None, usage, MONDAY),
        ("resolve", "claude-sonnet-5", None, usage, MONDAY),
        ("tree", "claude-opus-5-5", "jp", usage, MONDAY),
        ("tree", "claude-unknown-1", "jp", usage, MONDAY),
        ("extract", "claude-sonnet-5", None, None, MONDAY),
    ]
    by_pass = costs.tally(rows, "pass")
    resolve = by_pass["resolve claude-sonnet-5"]
    expect(resolve.calls == 2 and abs(resolve.dollars - 2 * (2.0 + 0.20 + 1.0)) < 1e-9,
           "a Sonnet call is input, cache reads and output at their list prices")
    expect(abs(by_pass["tree claude-opus-5-5"].dollars - (4.0 + 0.20 + 2.0)) < 1e-9, "Opus 5.5 at its own prices")
    unknown = by_pass["tree claude-unknown-1"]
    expect(unknown.calls == 1 and unknown.unpriced == 1 and unknown.dollars == 0,
           "a call on an unpriced model is counted as unpriced, not as free")
    expect("extract claude-sonnet-5" not in by_pass, "a row with no usage recorded is skipped")
    expect(set(costs.tally(rows, "country")) == {"-", "jp"}, "a peploop row without a country groups under -")
    expect(set(costs.tally(rows, "week")) == {"2026-W43"}, "calls group by ISO week")
    expect(costs.tally(rows, "model")["claude-sonnet-5"].calls == 2, "calls group by model")
    total = costs.render(by_pass)[-1]
    expect("1 calls on unpriced models not counted" in total, "the total line names what it could not price")


if __name__ == "__main__":
    main()
