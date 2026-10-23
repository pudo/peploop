"""Name what a model's check of a claim can answer, and when that answer lets it through.

Reach for this when a prompt asks a model to confirm or refuse something: a
placement, an office, a link. Every lane asks for a confidence in the same
three words. A narrow check of one claim answers with a verdict from this
closed set and the evidence it quotes. The gate is the same everywhere: the
claim is supported, at better than low confidence.
"""

from typing import Literal

CONFIDENCES = ("high", "medium", "low")
LOW = "low"
Confidence = Literal["high", "medium", "low"]

SUPPORTED = "supported"
#: A check of one claim against its source, in the order the verify prompt introduces them.
VERDICTS = (
    SUPPORTED,
    "unsupported",
    "contradicted",
    "imprecise",
    "already-recorded",
    "wrong-item",
    "wrong-person",
)


def accepts(verdict: str | None, confidence: str | None) -> bool:
    """Whether a check's answer lets the claim through: supported, and not at low confidence."""
    return verdict == SUPPORTED and confidence != LOW
