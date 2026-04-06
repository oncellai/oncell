"""Runtime — runs inside the cell. Loads the agent, handles requests.

The Host Agent starts this process inside the gVisor sandbox.
It listens on a unix socket for requests from the Host Agent,
dispatches them to the developer's Agent class, and streams responses back.

Usage (called by the base image entrypoint):
    python -m oncell.runtime --agent /app/agent.py --cell-id acme-corp --port 8080

Protocol:
    POST /setup           → calls agent.setup(ctx)
    POST /request         → calls agent.on_request(ctx, method, params)
    POST /teardown        → calls agent.teardown(ctx)
    GET  /health          → {"status": "ok"}
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import inspect
import json
import os
import signal
import sys
import traceback
from pathlib import Path
from typing import Any

from oncell.agent import Agent
from oncell.cell import Cell


def load_agent(agent_path: str) -> Agent:
    """Load an Agent subclass from a Python file.

    Finds the first class that subclasses Agent in the given file.
    """
    path = Path(agent_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"agent file not found: {agent_path}")

    spec = importlib.util.spec_from_file_location("_agent_module", str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load module from {agent_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules["_agent_module"] = module
    spec.loader.exec_module(module)

    # Find the Agent subclass
    agent_cls = None
    for name, obj in inspect.getmembers(module, inspect.isclass):
        if issubclass(obj, Agent) and obj is not Agent:
            agent_cls = obj
            break

    if agent_cls is None:
        raise ValueError(f"no Agent subclass found in {agent_path}")

    return agent_cls()


async def handle_request(agent: Agent, cell: Cell, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """Handle a single HTTP-like request over the connection."""
    try:
        # Read request line
        request_line = await reader.readline()
        if not request_line:
            return

        request_line = request_line.decode().strip()
        method, path, _ = request_line.split(" ", 2)

        # Read headers
        content_length = 0
        while True:
            line = await reader.readline()
            if line == b"\r\n" or line == b"\n" or not line:
                break
            header = line.decode().strip()
            if header.lower().startswith("content-length:"):
                content_length = int(header.split(":", 1)[1].strip())

        # Read body
        body = None
        if content_length > 0:
            body = await reader.readexactly(content_length)
            body = json.loads(body)

        # Dispatch
        status = 200
        result: Any = None

        if path == "/health":
            result = {"status": "ok", "cell_id": cell.id}

        elif path == "/setup":
            await agent.setup(cell)
            result = {"status": "ok"}

        elif path == "/request":
            if not body or "method" not in body:
                status = 400
                result = {"error": "missing 'method' in request body"}
            else:
                req_method = body["method"]
                params = body.get("params", {})
                result = await agent.on_request(cell, req_method, params)

        elif path == "/teardown":
            await agent.teardown(cell)
            result = {"status": "ok"}

        else:
            status = 404
            result = {"error": f"not found: {path}"}

    except Exception as e:
        status = 500
        result = {"error": str(e), "traceback": traceback.format_exc()}

    # Write response
    response_body = json.dumps(result, default=str).encode()
    response = (
        f"HTTP/1.1 {status} OK\r\n"
        f"Content-Type: application/json\r\n"
        f"Content-Length: {len(response_body)}\r\n"
        f"\r\n"
    ).encode() + response_body

    writer.write(response)
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def run_server(agent: Agent, cell: Cell, port: int):
    """Start the runtime HTTP server."""
    server = await asyncio.start_server(
        lambda r, w: handle_request(agent, cell, r, w),
        host="0.0.0.0",
        port=port,
    )

    print(f"oncell runtime started — cell={cell.id} port={port}", flush=True)

    # Start heartbeat
    cell.heartbeat.start()

    # Handle graceful shutdown
    stop = asyncio.Event()

    def on_signal():
        print("shutting down...", flush=True)
        stop.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, on_signal)

    async with server:
        await stop.wait()

    cell.heartbeat.stop()
    print("oncell runtime stopped", flush=True)


def main():
    parser = argparse.ArgumentParser(description="oncell runtime")
    parser.add_argument("--agent", required=True, help="path to agent.py")
    parser.add_argument("--cell-id", required=True, help="cell ID")
    parser.add_argument("--port", type=int, default=8080, help="listen port")
    parser.add_argument("--cells-dir", default="/cells", help="base cells directory")
    parser.add_argument("--control-plane-url", default=None, help="control plane URL for heartbeat")
    args = parser.parse_args()

    # Override from env
    cell_id = os.environ.get("ONCELL_CELL_ID", args.cell_id)
    port = int(os.environ.get("ONCELL_PORT", args.port))
    cells_dir = os.environ.get("ONCELL_CELLS_DIR", args.cells_dir)
    control_plane_url = os.environ.get("ONCELL_CONTROL_PLANE_URL", args.control_plane_url)

    agent = load_agent(args.agent)
    cell = Cell(cell_id, base_dir=cells_dir, control_plane_url=control_plane_url)

    asyncio.run(run_server(agent, cell, port))


if __name__ == "__main__":
    main()
