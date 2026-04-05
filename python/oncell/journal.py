"""Journal — durable execution primitive.

Append-only WAL on NVMe. Every step is recorded with its result.
On crash, replayed steps return cached results instead of re-executing.

Usage (automatic via cell.shell with durable=True):
    result = await cell.shell("npm test")  # journaled by default

Usage (manual for custom durability):
    async with cell.journal.step("fetch_data") as step:
        if step.cached:
            data = step.result
        else:
            data = await fetch_data()
            step.record(data)
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass
class JournalEntry:
    step: int
    tag: str
    args_hash: str
    result: Any
    timestamp: float


class Journal:
    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._path.mkdir(parents=True, exist_ok=True)
        self._wal = self._path / "wal.jsonl"
        self._entries: dict[str, JournalEntry] = {}
        self._step_counter = 0
        self._load()

    def _load(self):
        if not self._wal.exists():
            return
        with open(self._wal, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                key = f"{data['step']}:{data['tag']}:{data['args_hash']}"
                self._entries[key] = JournalEntry(
                    step=data["step"],
                    tag=data["tag"],
                    args_hash=data["args_hash"],
                    result=data["result"],
                    timestamp=data["ts"],
                )
                self._step_counter = max(self._step_counter, data["step"] + 1)

    def _key(self, step: int, tag: str, args_hash: str) -> str:
        return f"{step}:{tag}:{args_hash}"

    async def durable(self, tag: str, fn: Callable, *args: Any, **kwargs: Any) -> Any:
        """Execute fn with durable journaling. Returns cached result on replay."""
        step = self._step_counter
        self._step_counter += 1
        args_hash = _hash_args(*args, **kwargs)
        key = self._key(step, tag, args_hash)

        cached = self._entries.get(key)
        if cached is not None:
            return _deserialize(tag, cached.result)

        result = await fn()
        serialized = _serialize(result)

        entry = JournalEntry(step=step, tag=tag, args_hash=args_hash, result=serialized, timestamp=time.time())
        self._entries[key] = entry

        record = {"step": step, "tag": tag, "args_hash": args_hash, "result": serialized, "ts": entry.timestamp}
        with open(self._wal, "a") as f:
            f.write(json.dumps(record, default=str) + "\n")
            f.flush()
            os.fsync(f.fileno())

        return result

    def reset(self):
        """Clear the journal."""
        self._entries.clear()
        self._step_counter = 0
        if self._wal.exists():
            self._wal.unlink()

    @property
    def entries(self) -> int:
        return len(self._entries)


def _hash_args(*args: Any, **kwargs: Any) -> str:
    raw = json.dumps({"a": args, "k": kwargs}, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _serialize(result: Any) -> Any:
    """Convert to JSON-safe form."""
    if hasattr(result, "__dataclass_fields__"):
        from dataclasses import asdict
        return asdict(result)
    return result


def _deserialize(tag: str, data: Any) -> Any:
    """Reconstruct typed result from journal data."""
    if tag == "shell" and isinstance(data, dict) and "exit_code" in data:
        from oncell.cell import ShellResult
        return ShellResult(**data)
    return data
