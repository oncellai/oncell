"""Search — vector search primitive for the cell.

Embedded search engine backed by SQLite on NVMe.
Index files, search by semantic similarity. No external service.

Usage:
    await cell.search.index("/work/src", glob="**/*.ts")
    results = await cell.search.query("auth middleware", top_k=10)
    for r in results:
        print(r["path"], r["score"])
"""

from __future__ import annotations

import glob as globlib
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any


class Search:
    """Embedded vector search on NVMe. Uses SQLite for storage."""

    def __init__(self, path: str | Path, embed_fn: Any | None = None):
        self._dir = Path(path)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._dir / "search.db"
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._embed_fn = embed_fn
        self._init_tables()

    def _init_tables(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY,
                path TEXT NOT NULL,
                content TEXT NOT NULL,
                embedding BLOB,
                hash TEXT NOT NULL
            )
        """)
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path)")
        self._conn.commit()

    async def index(self, path: str, glob: str = "**/*") -> int:
        """Index files at path matching glob. Returns number of chunks indexed.

        Incremental — only re-indexes changed files (by content hash).
        """
        base = Path(path)
        if not base.is_dir():
            raise ValueError(f"Not a directory: {path}")

        files = [f for f in globlib.glob(str(base / glob), recursive=True) if os.path.isfile(f)]
        indexed = 0

        for filepath in files:
            with open(filepath, "r", errors="replace") as f:
                content = f.read()

            content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
            rel_path = os.path.relpath(filepath, base)

            existing = self._conn.execute(
                "SELECT hash FROM chunks WHERE path = ?", (rel_path,)
            ).fetchone()

            if existing and existing[0] == content_hash:
                continue

            # Remove old chunks for this file
            self._conn.execute("DELETE FROM chunks WHERE path = ?", (rel_path,))

            # Chunk the file
            chunks = _chunk_code(content, rel_path)

            for i, chunk in enumerate(chunks):
                chunk_id = f"{rel_path}:{i}"
                embedding = None
                if self._embed_fn:
                    embedding = await self._embed_fn(chunk)

                self._conn.execute(
                    "INSERT OR REPLACE INTO chunks (id, path, content, embedding, hash) VALUES (?, ?, ?, ?, ?)",
                    (chunk_id, rel_path, chunk, embedding, content_hash),
                )
                indexed += 1

        self._conn.commit()
        return indexed

    async def query(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        """Search indexed content. Returns [{path, content, score}].

        If no embedding function is set, falls back to text search.
        """
        if self._embed_fn:
            return await self._vector_search(query, top_k)
        return self._text_search(query, top_k)

    async def _vector_search(self, query: str, top_k: int) -> list[dict]:
        """Cosine similarity search using embeddings."""
        query_embedding = await self._embed_fn(query)
        rows = self._conn.execute(
            "SELECT path, content, embedding FROM chunks WHERE embedding IS NOT NULL"
        ).fetchall()

        scored = []
        for path, content, emb_blob in rows:
            if emb_blob is None:
                continue
            emb = json.loads(emb_blob) if isinstance(emb_blob, str) else list(emb_blob)
            score = _cosine_sim(query_embedding, emb)
            scored.append({"path": path, "content": content, "score": score})

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def _text_search(self, query: str, top_k: int) -> list[dict]:
        """Fallback: simple text match scoring."""
        terms = query.lower().split()
        rows = self._conn.execute("SELECT path, content FROM chunks").fetchall()

        scored = []
        for path, content in rows:
            lower = content.lower()
            score = sum(lower.count(t) for t in terms) / max(len(content), 1)
            if score > 0:
                scored.append({"path": path, "content": content, "score": score})

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    @property
    def chunk_count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM chunks").fetchone()
        return row[0] if row else 0

    def close(self):
        self._conn.close()


def _chunk_code(content: str, path: str, max_lines: int = 50) -> list[str]:
    """Split code into chunks by function/class boundaries or fixed lines."""
    lines = content.split("\n")
    if len(lines) <= max_lines:
        return [content]

    chunks = []
    current: list[str] = []

    for line in lines:
        # Split on function/class boundaries
        stripped = line.strip()
        is_boundary = (
            stripped.startswith("def ")
            or stripped.startswith("async def ")
            or stripped.startswith("class ")
            or stripped.startswith("function ")
            or stripped.startswith("export ")
            or stripped.startswith("const ")
            or stripped.startswith("pub fn ")
            or stripped.startswith("func ")
        )

        if is_boundary and len(current) > 5:
            chunks.append("\n".join(current))
            current = []

        current.append(line)

        if len(current) >= max_lines:
            chunks.append("\n".join(current))
            current = []

    if current:
        chunks.append("\n".join(current))

    return chunks


def _cosine_sim(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors."""
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
