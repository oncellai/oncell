"""Heartbeat — keeps the cell alive during long-running operations.

Without heartbeat, a cell running a 45-min test suite would get
paused at 30 min because no API requests came in. The heartbeat
sends periodic signals to the Control Plane so the idle checker
knows the cell is still working.

Usage (automatic — enabled by default on Cell):
    cell = Cell("acme-corp")
    # Heartbeat runs automatically in background

Usage (manual control):
    cell = Cell("acme-corp", heartbeat_url="http://control:4000")
    cell.heartbeat.stop()   # pause heartbeat
    cell.heartbeat.start()  # resume heartbeat
"""

from __future__ import annotations

import asyncio
import os
from typing import Optional
import logging

logger = logging.getLogger("oncell.heartbeat")


class Heartbeat:
    """Background task that pings the Control Plane every interval."""

    def __init__(
        self,
        cell_id: str,
        control_plane_url: str | None = None,
        interval_secs: int = 60,
    ):
        self._cell_id = cell_id
        self._url = control_plane_url or os.environ.get(
            "ONCELL_CONTROL_PLANE_URL", "http://localhost:4000"
        )
        self._interval = interval_secs
        self._task: Optional[asyncio.Task] = None
        self._running = False

    def start(self):
        """Start the heartbeat background task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.ensure_future(self._loop())
        logger.debug("heartbeat started for cell %s (every %ds)", self._cell_id, self._interval)

    def stop(self):
        """Stop the heartbeat."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.debug("heartbeat stopped for cell %s", self._cell_id)

    @property
    def is_running(self) -> bool:
        return self._running

    async def _loop(self):
        """Send heartbeat every interval."""
        while self._running:
            try:
                await self._ping()
            except Exception as e:
                logger.warning("heartbeat ping failed for %s: %s", self._cell_id, e)
            await asyncio.sleep(self._interval)

    async def _ping(self):
        """Single heartbeat ping to Control Plane."""
        url = f"{self._url}/cells/{self._cell_id}/heartbeat"
        try:
            # Use urllib to avoid requiring aiohttp for heartbeat
            import urllib.request
            req = urllib.request.Request(url, method="POST", data=b"")
            urllib.request.urlopen(req, timeout=5)
        except ImportError:
            pass
        except Exception as e:
            logger.debug("heartbeat ping error: %s", e)

    async def ping_once(self):
        """Send a single heartbeat. Useful for manual control."""
        await self._ping()
