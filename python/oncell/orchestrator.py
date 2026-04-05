"""Orchestrator — durable workflow primitive.

Run multi-step workflows with automatic checkpointing.
Supports sync execution, async fire-and-forget, and streaming.

Usage (sync — wait for result):
    orch = cell.orchestrator("deploy-task")
    result = await orch.run([
        Step("search", lambda: cell.search.query("auth")),
        Step("plan", lambda ctx: cell.llm(ctx["search"], ...)),
        Step("edit", lambda ctx: cell.shell(ctx["plan"].command)),
        Step("test", lambda: cell.shell("npm test")),
    ])

Usage (async — fire and forget):
    task_id = await orch.spawn([...steps...])
    status = await orch.status(task_id)

Usage (streaming):
    async for event in orch.stream([...steps...]):
        print(event)  # {"step": "search", "status": "done", "progress": 0.25}
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Awaitable

from oncell.journal import Journal


@dataclass
class Step:
    """A single step in a workflow."""
    name: str
    fn: Callable[..., Awaitable[Any]]
    retry: int = 0
    timeout: float | None = None


@dataclass
class StepResult:
    name: str
    result: Any
    status: str  # "done", "failed", "skipped"
    duration_ms: float
    error: str | None = None


@dataclass
class TaskStatus:
    task_id: str
    status: str  # "running", "done", "failed"
    steps_done: int
    steps_total: int
    results: list[StepResult] = field(default_factory=list)
    error: str | None = None


class Orchestrator:
    """Durable multi-step workflow engine."""

    def __init__(self, name: str, journal: Journal):
        self._name = name
        self._journal = journal
        self._tasks: dict[str, TaskStatus] = {}

    async def run(self, steps: list[Step]) -> dict[str, Any]:
        """Execute steps sequentially. Each step is journaled.
        Returns dict of {step_name: result}.

        Previous step results are passed as context to the next step.
        On crash, completed steps return cached results.
        """
        context: dict[str, Any] = {}

        for i, step in enumerate(steps):
            result = await self._execute_step(step, context)
            context[step.name] = result.result

            if result.status == "failed":
                raise RuntimeError(f"Step '{step.name}' failed: {result.error}")

        return context

    async def spawn(self, steps: list[Step]) -> str:
        """Fire-and-forget execution. Returns task_id immediately."""
        task_id = str(uuid.uuid4())[:8]
        status = TaskStatus(
            task_id=task_id,
            status="running",
            steps_done=0,
            steps_total=len(steps),
        )
        self._tasks[task_id] = status

        async def _run():
            try:
                context: dict[str, Any] = {}
                for step in steps:
                    result = await self._execute_step(step, context)
                    context[step.name] = result.result
                    status.steps_done += 1
                    status.results.append(result)
                    if result.status == "failed":
                        status.status = "failed"
                        status.error = result.error
                        return
                status.status = "done"
            except Exception as e:
                status.status = "failed"
                status.error = str(e)

        asyncio.create_task(_run())
        return task_id

    async def stream(self, steps: list[Step]) -> AsyncIterator[dict[str, Any]]:
        """Execute steps and yield progress events."""
        context: dict[str, Any] = {}
        total = len(steps)

        for i, step in enumerate(steps):
            yield {
                "step": step.name,
                "status": "starting",
                "progress": i / total,
            }

            result = await self._execute_step(step, context)
            context[step.name] = result.result

            yield {
                "step": step.name,
                "status": result.status,
                "progress": (i + 1) / total,
                "duration_ms": result.duration_ms,
                "error": result.error,
            }

            if result.status == "failed":
                return

        yield {"status": "done", "progress": 1.0}

    def status(self, task_id: str) -> TaskStatus | None:
        """Check status of a spawned task."""
        return self._tasks.get(task_id)

    async def _execute_step(self, step: Step, context: dict[str, Any]) -> StepResult:
        """Execute a single step with retry, timeout, and journaling."""
        tag = f"{self._name}:{step.name}"
        attempts = step.retry + 1

        for attempt in range(attempts):
            start = time.time()
            try:
                async def _fn():
                    # Pass context if fn accepts it
                    import inspect
                    sig = inspect.signature(step.fn)
                    if sig.parameters:
                        return await step.fn(context)
                    return await step.fn()

                if step.timeout:
                    result = await asyncio.wait_for(
                        self._journal.durable(tag, _fn, step.name, attempt),
                        timeout=step.timeout,
                    )
                else:
                    result = await self._journal.durable(tag, _fn, step.name, attempt)

                duration = (time.time() - start) * 1000
                return StepResult(name=step.name, result=result, status="done", duration_ms=duration)

            except Exception as e:
                duration = (time.time() - start) * 1000
                if attempt == attempts - 1:
                    return StepResult(name=step.name, result=None, status="failed", duration_ms=duration, error=str(e))

        return StepResult(name=step.name, result=None, status="failed", duration_ms=0, error="exhausted retries")
