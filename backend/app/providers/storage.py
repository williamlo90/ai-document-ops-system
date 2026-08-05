from __future__ import annotations

from pathlib import Path
from uuid import uuid4


class PrivateDocumentStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def write(self, content: bytes) -> str:
        key = f"{uuid4().hex}.pdf"
        destination = (self.root / key).resolve()
        if destination.parent != self.root:
            raise ValueError("Storage key escaped private root")
        temporary = destination.with_suffix(".tmp")
        temporary.write_bytes(content)
        temporary.replace(destination)
        return key

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if path.parent != self.root:
            raise ValueError("Storage key escaped private root")
        return path
