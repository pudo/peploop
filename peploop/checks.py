"""What every offline check of every lane shares: the line it prints per case, and the item it fabricates.

    from peploop.checks import ent, expect
"""


def expect(cond: bool, what: str) -> None:
    """Print one case's line; stop the check at the first that fails."""
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        raise SystemExit(1)


def ent(labels: dict[str, str], **claims: list[str]) -> dict:
    """A fabricated item: labels by language, and item-valued claims of normal rank."""
    return {"labels": {lg: {"value": v} for lg, v in labels.items()},
            "claims": {p: [{"rank": "normal", "mainsnak": {"datavalue": {"value": {"id": q}}}} for q in qs]
                       for p, qs in claims.items()}}
