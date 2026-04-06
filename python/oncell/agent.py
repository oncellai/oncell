"""Agent — the developer-facing base class.

Developers subclass Agent to define their coding agent:

    from oncell import Agent

    class MyAgent(Agent):
        cell = {"compute": "2cpu-4gb", "storage": "10gb"}

        async def setup(self, ctx):
            await ctx.shell("git clone https://github.com/acme/app /cell/work")
            await ctx.search.index("/cell/work/src")

        async def on_request(self, ctx, method, params):
            if method == "generate":
                return await self.generate(ctx, params["instruction"])
            raise ValueError(f"unknown method: {method}")

        async def generate(self, ctx, instruction):
            files = await ctx.search.query(instruction)
            result = await ctx.shell(f"echo 'generating for: {instruction}'")
            return {"output": result.stdout.strip(), "files": len(files)}

The runtime discovers and instantiates this class inside the cell.
"""

from __future__ import annotations

from abc import ABC
from typing import Any

from oncell.cell import Cell


class Agent(ABC):
    """Base class for oncell agents.

    Class attributes:
        cell: Cell spec — compute, storage, packages, network config.
    """

    cell: dict[str, Any] = {}

    async def setup(self, ctx: Cell) -> None:
        """Called once when the cell is first created. Override to install deps, clone repos, etc."""
        pass

    async def on_request(self, ctx: Cell, method: str, params: dict[str, Any]) -> Any:
        """Handle an incoming request. Override to dispatch to your methods.

        Default: looks for a method with the given name on this class.
        """
        handler = getattr(self, method, None)
        if handler is None or method.startswith("_"):
            raise ValueError(f"unknown method: {method}")
        return await handler(ctx, **params)

    async def teardown(self, ctx: Cell) -> None:
        """Called when the cell is being deleted. Override for cleanup."""
        pass
