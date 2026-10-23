"""Pin the one gate a model's check of a claim passes through.

Run it as `python -m peploop.check_verdict` from the repository root.
"""

from typing import get_args

from peploop import policy, verdict, verify
from peploop.checks import expect


def main() -> None:
    expect(verdict.accepts("supported", "high") and verdict.accepts("supported", "medium"),
           "supported at high or medium passes")
    expect(not verdict.accepts("supported", "low"), "supported at low does not")
    expect(not any(verdict.accepts(v, "high") for v in verdict.VERDICTS if v != verdict.SUPPORTED),
           "no other verdict passes")
    expect(get_args(verdict.Confidence) == verdict.CONFIDENCES, "the confidence type is the closed set")
    expect(verify.VERDICTS is verdict.VERDICTS and policy.SUPPORTED is verdict.SUPPORTED,
           "the verifier and the policy read the same words")


if __name__ == "__main__":
    main()
