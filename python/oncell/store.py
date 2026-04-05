"""Store — filesystem primitive for the cell.

Read, write, list, and delete files on the cell's NVMe storage.
All operations are scoped to the cell's working directory.

Usage:
    await cell.store.write("src/app.ts", code)
    content = await cell.store.read("src/app.ts")
    files = await cell.store.list("src/", glob="**/*.ts")
    await cell.store.delete("src/old.ts")
"""

from __future__ import annotations

import glob as globlib
import os
from pathlib import Path


class Store:
    """Filesystem operations scoped to a cell directory."""

    def __init__(self, path: str | Path):
        self._root = Path(path)
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    async def write(self, path: str, content: str | bytes) -> None:
        """Write a file."""
        full = self._resolve(path)
        full.parent.mkdir(parents=True, exist_ok=True)
        mode = "wb" if isinstance(content, bytes) else "w"
        with open(full, mode) as f:
            f.write(content)

    async def read(self, path: str) -> str:
        """Read a file as text."""
        full = self._resolve(path)
        with open(full, "r") as f:
            return f.read()

    async def read_bytes(self, path: str) -> bytes:
        """Read a file as bytes."""
        full = self._resolve(path)
        with open(full, "rb") as f:
            return f.read()

    async def exists(self, path: str) -> bool:
        """Check if a file exists."""
        return self._resolve(path).exists()

    async def delete(self, path: str) -> None:
        """Delete a file."""
        full = self._resolve(path)
        if full.is_file():
            full.unlink()

    async def list(self, path: str = ".", glob: str = "**/*") -> list[str]:
        """List files matching a glob pattern. Returns paths relative to root."""
        base = self._resolve(path)
        if not base.is_dir():
            return []
        matches = globlib.glob(str(base / glob), recursive=True)
        return [
            os.path.relpath(m, self._root)
            for m in matches
            if os.path.isfile(m)
        ]

    async def size(self, path: str) -> int:
        """Get file size in bytes."""
        return self._resolve(path).stat().st_size

    async def disk_usage(self) -> int:
        """Total bytes used by this store."""
        total = 0
        for dirpath, _, filenames in os.walk(self._root):
            for f in filenames:
                total += os.path.getsize(os.path.join(dirpath, f))
        return total

    def _resolve(self, path: str) -> Path:
        """Resolve a relative path within the store root. Prevents directory traversal."""
        resolved = (self._root / path).resolve()
        if not str(resolved).startswith(str(self._root.resolve())):
            raise ValueError(f"Path traversal denied: {path}")
        return resolved
