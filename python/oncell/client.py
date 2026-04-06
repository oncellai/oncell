"""OnCell REST API client.

Usage:
    from oncell import OnCell
    oncell = OnCell(api_key="oncell_sk_...")
    cell = await oncell.cells.create(customer_id="user-1")
    print(cell.preview_url)

Synchronous usage:
    from oncell import OnCell
    oncell = OnCell(api_key="oncell_sk_...")
    cell = oncell.cells.create_sync(customer_id="user-1")
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any


class OnCellError(Exception):
    """Raised when the API returns a non-2xx status."""

    def __init__(self, status: int, body: Any):
        self.status = status
        self.body = body
        msg = body.get("error", json.dumps(body)) if isinstance(body, dict) else str(body)
        super().__init__(f"OnCell API error ({status}): {msg}")


@dataclass
class Cell:
    """A cell as returned by the API."""

    id: str
    customer_id: str
    tier: str
    status: str
    permanent: bool
    created_at: str
    host_id: str | None = None
    port: int | None = None
    last_active_at: str | None = None

    @property
    def preview_url(self) -> str:
        return f"https://{self.id}.cells.oncell.ai"


@dataclass
class Tier:
    """Tier pricing info."""

    id: str
    name: str
    spec: str
    active_price: str
    paused_price: str
    storage: str


def _to_cell(raw: dict[str, Any]) -> Cell:
    cell_id = raw.get("cell_id") or raw.get("id") or ""
    return Cell(
        id=cell_id,
        customer_id=raw.get("customer_id", ""),
        tier=raw.get("tier", "starter"),
        status=raw.get("status", "active"),
        permanent=bool(raw.get("permanent", False)),
        created_at=raw.get("created_at", ""),
        host_id=raw.get("host_id"),
        port=raw.get("port"),
        last_active_at=raw.get("last_active_at"),
    )


def _to_tier(raw: dict[str, Any]) -> Tier:
    return Tier(
        id=raw["id"],
        name=raw["name"],
        spec=raw["spec"],
        active_price=raw["active_price"],
        paused_price=raw["paused_price"],
        storage=raw["storage"],
    )


def _api_request(
    method: str,
    url: str,
    api_key: str,
    body: Any | None = None,
) -> Any:
    """Make an HTTP request using urllib (no dependencies)."""
    headers = {"Authorization": f"Bearer {api_key}"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req) as resp:
            resp_body = resp.read().decode("utf-8")
            if not resp_body:
                return None
            return json.loads(resp_body)
    except urllib.error.HTTPError as e:
        resp_body = e.read().decode("utf-8")
        try:
            parsed = json.loads(resp_body)
        except (json.JSONDecodeError, ValueError):
            parsed = resp_body
        raise OnCellError(e.code, parsed) from None


class CellsResource:
    """Cells API resource — all cell operations."""

    def __init__(self, api_key: str, base_url: str):
        self._api_key = api_key
        self._base_url = base_url

    def _url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    def _req(self, method: str, path: str, body: Any | None = None) -> Any:
        return _api_request(method, self._url(path), self._api_key, body)

    # ─── CRUD ───

    def create_sync(
        self,
        customer_id: str,
        tier: str | None = None,
        permanent: bool = False,
    ) -> Cell:
        """Create a new cell (synchronous)."""
        payload: dict[str, Any] = {"customer_id": customer_id}
        if tier is not None:
            payload["tier"] = tier
        if permanent:
            payload["permanent"] = True
        raw = self._req("POST", "/api/v1/cells", payload)
        return _to_cell(raw)

    async def create(
        self,
        customer_id: str,
        tier: str | None = None,
        permanent: bool = False,
    ) -> Cell:
        """Create a new cell."""
        return self.create_sync(customer_id=customer_id, tier=tier, permanent=permanent)

    def list_sync(self) -> list[Cell]:
        """List all cells (synchronous)."""
        raw = self._req("GET", "/api/v1/cells")
        return [_to_cell(c) for c in (raw.get("cells") or [])]

    async def list(self) -> list[Cell]:
        """List all cells."""
        return self.list_sync()

    def get_sync(self, cell_id: str) -> Cell:
        """Get a cell by ID (synchronous)."""
        raw = self._req("GET", f"/api/v1/cells/{_enc(cell_id)}")
        return _to_cell(raw)

    async def get(self, cell_id: str) -> Cell:
        """Get a cell by ID."""
        return self.get_sync(cell_id)

    def pause_sync(self, cell_id: str) -> Cell:
        """Pause a cell (synchronous)."""
        raw = self._req("POST", f"/api/v1/cells/{_enc(cell_id)}/pause")
        return _to_cell({**raw, "cell_id": cell_id})

    async def pause(self, cell_id: str) -> Cell:
        """Pause a cell."""
        return self.pause_sync(cell_id)

    def resume_sync(self, cell_id: str) -> Cell:
        """Resume a paused cell (synchronous)."""
        raw = self._req("POST", f"/api/v1/cells/{_enc(cell_id)}/resume")
        return _to_cell({**raw, "cell_id": cell_id})

    async def resume(self, cell_id: str) -> Cell:
        """Resume a paused cell."""
        return self.resume_sync(cell_id)

    def delete_sync(self, cell_id: str) -> None:
        """Delete a cell (synchronous)."""
        self._req("DELETE", f"/api/v1/cells/{_enc(cell_id)}")

    async def delete(self, cell_id: str) -> None:
        """Delete a cell."""
        self.delete_sync(cell_id)

    def set_permanent_sync(self, cell_id: str, permanent: bool) -> None:
        """Set or clear the permanent flag (synchronous)."""
        self._req("POST", f"/api/v1/cells/{_enc(cell_id)}/permanent", {"permanent": permanent})

    async def set_permanent(self, cell_id: str, permanent: bool) -> None:
        """Set or clear the permanent flag."""
        self.set_permanent_sync(cell_id, permanent)

    # ─── File operations ───

    def write_file_sync(self, cell_id: str, path: str, content: str) -> None:
        """Write a file to the cell (synchronous)."""
        self._req("POST", f"/api/v1/cells/{_enc(cell_id)}/request", {
            "method": "write_file",
            "params": {"path": path, "content": content},
        })

    async def write_file(self, cell_id: str, path: str, content: str) -> None:
        """Write a file to the cell."""
        self.write_file_sync(cell_id, path, content)

    def read_file_sync(self, cell_id: str, path: str) -> dict[str, str]:
        """Read a file from the cell (synchronous)."""
        raw = self._req("POST", f"/api/v1/cells/{_enc(cell_id)}/request", {
            "method": "read_file",
            "params": {"path": path},
        })
        return {"content": raw.get("content", raw) if isinstance(raw, dict) else str(raw)}

    async def read_file(self, cell_id: str, path: str) -> dict[str, str]:
        """Read a file from the cell."""
        return self.read_file_sync(cell_id, path)

    def list_files_sync(self, cell_id: str, dir: str | None = None) -> dict[str, list[str]]:
        """List files in the cell (synchronous)."""
        raw = self._req("POST", f"/api/v1/cells/{_enc(cell_id)}/request", {
            "method": "list_files",
            "params": {"path": dir},
        })
        return {"files": raw.get("files", []) if isinstance(raw, dict) else []}

    async def list_files(self, cell_id: str, dir: str | None = None) -> dict[str, list[str]]:
        """List files in the cell."""
        return self.list_files_sync(cell_id, dir)

    # ─── DB operations ───

    def db_set_sync(self, cell_id: str, key: str, value: Any) -> None:
        """Set a key-value pair in the cell's DB (synchronous)."""
        self._req("POST", f"/api/v1/cells/{_enc(cell_id)}/request", {
            "method": "db_set",
            "params": {"key": key, "value": value},
        })

    async def db_set(self, cell_id: str, key: str, value: Any) -> None:
        """Set a key-value pair in the cell's DB."""
        self.db_set_sync(cell_id, key, value)

    def db_get_sync(self, cell_id: str, key: str) -> dict[str, Any]:
        """Get a value from the cell's DB (synchronous)."""
        raw = self._req("POST", f"/api/v1/cells/{_enc(cell_id)}/request", {
            "method": "db_get",
            "params": {"key": key},
        })
        return {"value": raw.get("value") if isinstance(raw, dict) else raw}

    async def db_get(self, cell_id: str, key: str) -> dict[str, Any]:
        """Get a value from the cell's DB."""
        return self.db_get_sync(cell_id, key)

    # ─── Generic request ───

    def request_sync(self, cell_id: str, method: str, params: dict[str, Any] | None = None) -> Any:
        """Send a generic request to the cell's agent runtime (synchronous)."""
        return self._req("POST", f"/api/v1/cells/{_enc(cell_id)}/request", {
            "method": method,
            "params": params or {},
        })

    async def request(self, cell_id: str, method: str, params: dict[str, Any] | None = None) -> Any:
        """Send a generic request to the cell's agent runtime."""
        return self.request_sync(cell_id, method, params)


def _enc(s: str) -> str:
    """URL-encode a path segment."""
    return urllib.request.quote(s, safe="")


class OnCell:
    """OnCell REST API client.

    Args:
        api_key: API key (oncell_sk_...). Falls back to ONCELL_API_KEY env var.
        base_url: Base URL for the API. Defaults to https://api.oncell.ai.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        self._api_key = api_key or os.environ.get("ONCELL_API_KEY", "")
        if not self._api_key:
            raise ValueError("OnCell: api_key is required. Pass it directly or set ONCELL_API_KEY env var.")
        self._base_url = (base_url or os.environ.get("ONCELL_BASE_URL", "https://api.oncell.ai")).rstrip("/")
        self.cells = CellsResource(self._api_key, self._base_url)

    def tiers_sync(self) -> list[Tier]:
        """List available pricing tiers (synchronous)."""
        raw = _api_request("GET", f"{self._base_url}/api/v1/cells/tiers", self._api_key)
        return [_to_tier(t) for t in (raw.get("tiers") or [])]

    async def tiers(self) -> list[Tier]:
        """List available pricing tiers."""
        return self.tiers_sync()
