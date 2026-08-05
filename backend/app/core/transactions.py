from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol


class TransactionManager(Protocol):
    def transaction(self) -> AbstractContextManager[None]: ...
