from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import ContextManager, Protocol


class TransactionManager(Protocol):
    def transaction(self) -> ContextManager[None]: ...


class NoopTransactionManager:
    @contextmanager
    def transaction(self) -> Iterator[None]:
        yield
