from __future__ import annotations

import os
import signal
import threading

from app.worker import run_once


def run_forever(*, poll_seconds: float | None = None) -> None:
    delay = poll_seconds if poll_seconds is not None else _poll_seconds()
    stopping = threading.Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stopping.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    while not stopping.is_set():
        run_once()
        stopping.wait(delay)


def _poll_seconds() -> float:
    raw_value = os.getenv("WORKER_POLL_SECONDS", "5")
    try:
        value = float(raw_value)
    except ValueError:
        return 5.0
    return max(value, 0.1)


if __name__ == "__main__":
    run_forever()
