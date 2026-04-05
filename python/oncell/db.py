"""DB — persistent key-value database for the cell.

Backed by SQLite on NVMe. Supports typed get/set, namespaces,
and raw SQL for advanced use cases.

Usage:
    await cell.db.set("last_task", "add dark mode")
    task = await cell.db.get("last_task")
    await cell.db.set("prefs", {"lang": "ts"})  # JSON values
    all_keys = await cell.db.keys()
    await cell.db.delete("old_key")

    # Namespaced
    await cell.db.set("history:1", {...})
    history = await cell.db.scan("history:")

    # Raw SQL
    await cell.db.execute("CREATE TABLE IF NOT EXISTS events (...)")
    rows = await cell.db.query("SELECT * FROM events WHERE ts > ?", [ts])
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class DB:
    """SQLite-backed key-value store + raw SQL access."""

    def __init__(self, path: str | Path):
        self._dir = Path(path)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._dir / "cell.db"
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT)"
        )
        self._conn.commit()

    async def get(self, key: str, default: Any = None) -> Any:
        """Get a value by key. Returns deserialized JSON."""
        row = self._conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        return json.loads(row[0])

    async def set(self, key: str, value: Any) -> None:
        """Set a key-value pair. Value is JSON-serialized."""
        self._conn.execute(
            "INSERT OR REPLACE INTO kv (key, value) VALUES (?, ?)",
            (key, json.dumps(value, default=str)),
        )
        self._conn.commit()

    async def delete(self, key: str) -> None:
        """Delete a key."""
        self._conn.execute("DELETE FROM kv WHERE key = ?", (key,))
        self._conn.commit()

    async def keys(self, prefix: str = "") -> list[str]:
        """List all keys, optionally filtered by prefix."""
        if prefix:
            rows = self._conn.execute(
                "SELECT key FROM kv WHERE key LIKE ?", (prefix + "%",)
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT key FROM kv").fetchall()
        return [r[0] for r in rows]

    async def scan(self, prefix: str) -> dict[str, Any]:
        """Get all key-value pairs matching a prefix."""
        rows = self._conn.execute(
            "SELECT key, value FROM kv WHERE key LIKE ?", (prefix + "%",)
        ).fetchall()
        return {k: json.loads(v) for k, v in rows}

    async def execute(self, sql: str, params: list[Any] | None = None) -> None:
        """Execute raw SQL (for custom tables)."""
        self._conn.execute(sql, params or [])
        self._conn.commit()

    async def query(self, sql: str, params: list[Any] | None = None) -> list[dict]:
        """Query raw SQL, returns list of dicts."""
        cursor = self._conn.execute(sql, params or [])
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def close(self):
        self._conn.close()
