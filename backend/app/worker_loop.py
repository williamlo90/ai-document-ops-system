from __future__ import annotations

import os
import signal
import threading

from app.api.dependencies import build_container
from app.core.settings import load_settings
from app.worker import run_once


def run_forever(*, poll_seconds: float | None = None) -> None:
    delay = poll_seconds if poll_seconds is not None else _poll_seconds()
    max_idle_delay = max(delay, _max_idle_poll_seconds())
    stopping = threading.Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stopping.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    settings = load_settings()
    container = build_container(settings)
    current_delay = delay
    try:
        while not stopping.is_set():
            processed = run_once(container, settings)
            stopping.wait(current_delay)
            current_delay = delay if processed else min(max_idle_delay, current_delay * 2)
    finally:
        container.close()


def _poll_seconds() -> float:
    raw_value = os.getenv("WORKER_POLL_SECONDS", "5")
    try:
        value = float(raw_value)
    except ValueError:
        return 5.0
    return max(value, 0.1)


def _max_idle_poll_seconds() -> float:
    raw_value = os.getenv("WORKER_MAX_IDLE_POLL_SECONDS", "30")
    try:
        value = float(raw_value)
    except ValueError:
        return 30.0
    return max(value, 0.1)


if __name__ == "__main__":
    run_forever()
