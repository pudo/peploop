"""Pin the hold: a tool whose data directory holds `HOLD` opens no batch, offline.

    .venv/bin/python -m peploop.corp.check_hold
"""

import tempfile
from pathlib import Path

from peploop import ledger, send
from peploop.tree.check_filter import expect


def main() -> None:
    real = send.HOLD, ledger.open_batch
    opened: list[str] = []
    ledger.open_batch = lambda tool, op, name: opened.append(tool) or 1  # type: ignore[assignment]
    with tempfile.TemporaryDirectory() as tmp:
        send.HOLD = Path(tmp) / "{tool}" / "HOLD"  # type: ignore[assignment]
        (Path(tmp) / "pepcorp").mkdir()
        (Path(tmp) / "pepcorp" / "HOLD").touch()
        try:
            try:
                send._open("pepcorp", "add")
                refused = False
            except RuntimeError:
                refused = True
            expect(refused and not opened, "a held tool is refused before its batch is recorded")
            expect(send.held("pepcorp") and not send.held("peploop"), "the hold is per tool")
        finally:
            send.HOLD, ledger.open_batch = real  # type: ignore[assignment]


if __name__ == "__main__":
    main()
