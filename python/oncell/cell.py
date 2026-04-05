"""Cell — the core primitive. Connect to an isolated compute cell.

A cell is an isolated environment with its own filesystem, database,
vector search, and durable execution. One cell per customer.

Usage:
    from oncell import Cell

    cell = Cell("acme-corp")
    result = await cell.shell("git clone https://github.com/acme/app /work")
    await cell.store.write("config.json", '{"theme": "dark"}')
    await cell.search.index("/work/src")
    results = await cell.search.query("auth middleware")
"""

from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from oncell.db import DB
from oncell.heartbeat import Heartbeat
from oncell.journal import Journal
from oncell.orchestrator import Orchestrator
from oncell.search import Search
from oncell.store import Store


@dataclass
class ShellResult:
    stdout: str
    stderr: str
    exit_code: int

    @property
    def failed(self) -> bool:
        return self.exit_code != 0


class Cell:
    """An isolated compute cell. One per customer."""

    def __init__(
        self,
        cell_id: str,
        base_dir: str | Path = "/cells",
        control_plane_url: str | None = None,
        heartbeat_interval: int = 60,
    ):
        self.id = cell_id
        self._dir = Path(base_dir) / cell_id
        self._dir.mkdir(parents=True, exist_ok=True)

        self.store = Store(self._dir / "work")
        self.db = DB(self._dir / "data")
        self.search = Search(self._dir / "index")
        self.journal = Journal(self._dir / "journal")
        self.heartbeat = Heartbeat(cell_id, control_plane_url, heartbeat_interval)
        self._orchestrators: dict[str, Orchestrator] = {}

    @property
    def work_dir(self) -> Path:
        """The cell's working directory (customer's files)."""
        return self._dir / "work"

    async def shell(self, cmd: str, cwd: str | None = None, durable: bool = True) -> ShellResult:
        """Run a shell command inside the cell.

        If durable=True (default), the result is journaled.
        On crash recovery, cached result is returned.
        """
        async def _exec() -> ShellResult:
            work = cwd or str(self.work_dir)
            Path(work).mkdir(parents=True, exist_ok=True)
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=work,
            )
            stdout, stderr = await proc.communicate()
            return ShellResult(
                stdout=stdout.decode("utf-8", errors="replace"),
                stderr=stderr.decode("utf-8", errors="replace"),
                exit_code=proc.returncode or 0,
            )

        if durable:
            return await self.journal.durable("shell", _exec, cmd, cwd=cwd)
        return await _exec()

    def orchestrator(self, name: str = "default") -> Orchestrator:
        """Get a named orchestrator for durable multi-step workflows."""
        if name not in self._orchestrators:
            self._orchestrators[name] = Orchestrator(name, self.journal)
        return self._orchestrators[name]

    def __repr__(self) -> str:
        return f"Cell({self.id!r})"
