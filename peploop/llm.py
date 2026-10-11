"""The pieces every model pass shares: one client, a prompt read with its hash, and token usage.

Each pass keeps its own ledger and its own content key, because what makes two
requests "the same question" differs per pass. What does not differ lives here:
the process-wide client, the rule that a stored answer is keyed by the sha256
of the prompt file's text (so an edit makes the old answers re-askable instead
of mixing two instructions), and the four token counts a ledger row records.
"""

import hashlib
import threading
from pathlib import Path
from typing import Any

import anthropic

_client: anthropic.Anthropic | None = None
_client_lock = threading.Lock()


def client() -> anthropic.Anthropic:
    """Return the process-wide Anthropic client, built on first use."""
    global _client
    with _client_lock:
        if _client is None:
            _client = anthropic.Anthropic()
        return _client


def system_prompt(path: Path) -> tuple[str, str]:
    """Read a frozen prompt file and return it with the sha256 of its text."""
    text = path.read_text()
    return text, hashlib.sha256(text.encode("utf-8")).hexdigest()


def usage(response: Any) -> dict[str, int]:
    """The token counts of one response, as every ledger row stores them."""
    return {
        "input_tokens": response.usage.input_tokens,
        "cache_creation_input_tokens": response.usage.cache_creation_input_tokens or 0,
        "cache_read_input_tokens": response.usage.cache_read_input_tokens or 0,
        "output_tokens": response.usage.output_tokens,
    }


#: List prices per million tokens: input, output, cache read, cache write. A
#: model not listed is reported in tokens only, never priced by a guess.
PRICES: dict[str, tuple[float, float, float, float]] = {
    "claude-sonnet-5": (2.0, 10.0, 0.20, 2.50),
    "claude-sonnet-5-5": (2.0, 10.0, 0.20, 2.50),
    "claude-opus-5": (5.0, 25.0, 0.50, 6.25),
    "claude-opus-5-5": (4.0, 20.0, 0.20, 5.00),
}


def cost(model: str, usage: dict[str, int]) -> float | None:
    """Dollars for one usage tally at list price, or None for an unpriced model."""
    price = PRICES.get(model)
    if price is None:
        return None
    p_in, p_out, p_read, p_write = price
    return (usage.get("input_tokens", 0) * p_in + usage.get("output_tokens", 0) * p_out
            + usage.get("cache_read_input_tokens", 0) * p_read
            + usage.get("cache_creation_input_tokens", 0) * p_write) / 1e6
