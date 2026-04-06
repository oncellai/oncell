"""Tests for the OnCell REST API client.

Uses unittest.mock to mock urllib.request.urlopen so we don't hit the real API.
"""

from __future__ import annotations

import json
from io import BytesIO
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from oncell import OnCell, OnCellError


# ─── Fixtures ───


class MockHTTPResponse:
    """Fake http.client.HTTPResponse for mocking urlopen."""

    def __init__(self, status: int, body: Any):
        self.status = status
        self._body = json.dumps(body).encode("utf-8") if body is not None else b""
        self.code = status

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


_mock_responses: list[MockHTTPResponse] = []
_captured_requests: list[dict[str, Any]] = []


def push_mock(status: int, body: Any):
    _mock_responses.append(MockHTTPResponse(status, body))


def fake_urlopen(req, **kwargs):
    _captured_requests.append({
        "url": req.full_url,
        "method": req.get_method(),
        "headers": dict(req.headers),
        "data": json.loads(req.data.decode()) if req.data else None,
    })
    mock = _mock_responses.pop(0)
    if mock.status >= 400:
        import urllib.error
        err = urllib.error.HTTPError(req.full_url, mock.status, "error", {}, BytesIO(mock._body))
        raise err
    return mock


@pytest.fixture(autouse=True)
def reset_mocks():
    _mock_responses.clear()
    _captured_requests.clear()
    yield


def client(base_url: str = "https://api.oncell.ai") -> OnCell:
    return OnCell(api_key="oncell_sk_test123", base_url=base_url)


# ─── Constructor ───


def test_constructor_requires_api_key():
    with pytest.raises(ValueError, match="api_key is required"):
        OnCell()


def test_constructor_accepts_api_key():
    c = client()
    assert c is not None


# ─── Cells CRUD ───


@patch("oncell.client.urllib.request.urlopen", side_effect=fake_urlopen)
def test_create_cell(mock_urlopen):
    c = client()
    push_mock(201, {
        "cell_id": "dev--user-1",
        "customer_id": "user-1",
        "tier": "standard",
        "status": "active",
        "permanent": False,
        "created_at": "2026-04-06T00:00:00.000Z",
    })

    cell = c.cells.create_sync(customer_id="user-1", tier="standard")

    assert len(_captured_requests) == 1
    assert "/api/v1/cells" in _captured_requests[0]["url"]
    assert _captured_requests[0]["data"]["customer_id"] == "user-1"
    assert cell.id == "dev--user-1"
    assert cell.customer_id == "user-1"
    assert cell.status == "active"
    assert cell.preview_url == "https://dev--user-1.cells.oncell.ai"


@patch("oncell.client.urllib.request.urlopen", side_effect=fake_urlopen)
def test_list_cells(mock_urlopen):
    c = client()
    push_mock(200, {
        "cells": [
            {"cell_id": "c1", "customer_id": "u1", "status": "active", "tier": "starter"},
            {"cell_id": "c2", "customer_id": "u2", "status": "paused", "tier": "standard"},
        ]
    })

    cells = c.cells.list_sync()
    assert len(cells) == 2
    assert cells[0].id == "c1"
    assert cells[1].status == "paused"


@patch("oncell.client.urllib.request.urlopen", side_effect=fake_urlopen)
def test_get_cell(mock_urlopen):
    c = client()
    push_mock(200, {"cell_id": "c1", "customer_id": "u1", "status": "active", "tier": "starter"})

    cell = c.cells.get_sync("c1")
    assert cell.id == "c1"


@patch("oncell.client.urllib.request.urlopen", side_effect=fake_urlopen)
def test_pause_cell(mock_urlopen):
    c = client()
    push_mock(200, {"cell_id": "c1", "status": "paused"})

    cell = c.cells.pause_sync("c1")
    assert cell.status == "paused"
    assert "/pause" in _captured_requests[0]["url"]


@patch("oncell.client.urllib.request.urlopen", side_effect=fake_urlopen)
def test_resume_cell(mock_urlopen):
    c = client()
    push_mock(200, {"cell_id": "c1", "status": "active"})

    cell = c.cells.resume_sync("c1")
    assert cell.status == "active"
    assert "/resume" in _captured_requests[0]["url"]


@patch("oncell.client.urllib.request.urlopen", side_effect=fake_urlopen)
def test_delete_cell(mock_urlopen):
    c = client()
    push_mock(200, {"ok": True})

    c.cells.delete_sync("c1")
    assert _captured_requests[0]["method"] == "DELETE"


@patch("oncell.client.urllib.request.urlopen", side_effect=fake_urlopen)
def test_set_permanent(mock_urlopen):
    c = client()
    push_mock(200, {"cell_id": "c1", "permanent": True})

    c.cells.set_permanent_sync("c1", True)
    assert "/permanent" in _captured_requests[0]["url"]
    assert _captured_requests[0]["data"]["permanent"] is True


# ─── File operations ───


@patch("oncell.client.urllib.request.urlopen", side_effect=fake_urlopen)
def test_write_file(mock_urlopen):
    c = client()
    push_mock(200, {"ok": True})

    c.cells.write_file_sync("c1", "index.html", "<h1>hi</h1>")
    data = _captured_requests[0]["data"]
    assert data["method"] == "write_file"
    assert data["params"]["path"] == "index.html"
    assert data["params"]["content"] == "<h1>hi</h1>"


@patch("oncell.client.urllib.request.urlopen", side_effect=fake_urlopen)
def test_read_file(mock_urlopen):
    c = client()
    push_mock(200, {"content": "<h1>hi</h1>"})

    result = c.cells.read_file_sync("c1", "index.html")
    assert result["content"] == "<h1>hi</h1>"


@patch("oncell.client.urllib.request.urlopen", side_effect=fake_urlopen)
def test_list_files(mock_urlopen):
    c = client()
    push_mock(200, {"files": ["index.html", "style.css"]})

    result = c.cells.list_files_sync("c1")
    assert result["files"] == ["index.html", "style.css"]


# ─── DB operations ───


@patch("oncell.client.urllib.request.urlopen", side_effect=fake_urlopen)
def test_db_set(mock_urlopen):
    c = client()
    push_mock(200, {"ok": True})

    c.cells.db_set_sync("c1", "theme", "dark")
    data = _captured_requests[0]["data"]
    assert data["method"] == "db_set"
    assert data["params"] == {"key": "theme", "value": "dark"}


@patch("oncell.client.urllib.request.urlopen", side_effect=fake_urlopen)
def test_db_get(mock_urlopen):
    c = client()
    push_mock(200, {"value": "dark"})

    result = c.cells.db_get_sync("c1", "theme")
    assert result["value"] == "dark"


# ─── Generic request ───


@patch("oncell.client.urllib.request.urlopen", side_effect=fake_urlopen)
def test_generic_request(mock_urlopen):
    c = client()
    push_mock(200, {"result": "generated"})

    result = c.cells.request_sync("c1", "generate", {"instruction": "build a page"})
    assert result == {"result": "generated"}
    data = _captured_requests[0]["data"]
    assert data["method"] == "generate"
    assert data["params"]["instruction"] == "build a page"


# ─── Tiers ───


@patch("oncell.client.urllib.request.urlopen", side_effect=fake_urlopen)
def test_tiers(mock_urlopen):
    c = client()
    push_mock(200, {
        "tiers": [
            {"id": "starter", "name": "Starter", "spec": "1cpu-1gb",
             "active_price": "$0.10/hr", "paused_price": "$0.003/hr", "storage": "10GB"},
            {"id": "standard", "name": "Standard", "spec": "2cpu-4gb",
             "active_price": "$0.25/hr", "paused_price": "$0.005/hr", "storage": "50GB"},
        ]
    })

    tiers = c.tiers_sync()
    assert len(tiers) == 2
    assert tiers[0].id == "starter"
    assert tiers[1].active_price == "$0.25/hr"


# ─── Error handling ───


@patch("oncell.client.urllib.request.urlopen", side_effect=fake_urlopen)
def test_error_raises_oncell_error(mock_urlopen):
    c = client()
    push_mock(404, {"error": "not found"})

    with pytest.raises(OnCellError) as exc_info:
        c.cells.get_sync("nonexistent")

    assert exc_info.value.status == 404
    assert "not found" in str(exc_info.value)


@patch("oncell.client.urllib.request.urlopen", side_effect=fake_urlopen)
def test_auth_header_present(mock_urlopen):
    c = client()
    push_mock(200, {"cells": []})

    c.cells.list_sync()
    assert _captured_requests[0]["headers"]["Authorization"] == "Bearer oncell_sk_test123"


# ─── Async wrappers ───


@pytest.mark.asyncio
@patch("oncell.client.urllib.request.urlopen", side_effect=fake_urlopen)
async def test_async_create(mock_urlopen):
    c = client()
    push_mock(201, {
        "cell_id": "dev--user-1",
        "customer_id": "user-1",
        "tier": "standard",
        "status": "active",
        "permanent": False,
        "created_at": "2026-04-06T00:00:00.000Z",
    })

    cell = await c.cells.create(customer_id="user-1", tier="standard")
    assert cell.id == "dev--user-1"


@pytest.mark.asyncio
@patch("oncell.client.urllib.request.urlopen", side_effect=fake_urlopen)
async def test_async_tiers(mock_urlopen):
    c = client()
    push_mock(200, {
        "tiers": [
            {"id": "starter", "name": "Starter", "spec": "1cpu-1gb",
             "active_price": "$0.10/hr", "paused_price": "$0.003/hr", "storage": "10GB"},
        ]
    })

    tiers = await c.tiers()
    assert len(tiers) == 1
    assert tiers[0].id == "starter"
