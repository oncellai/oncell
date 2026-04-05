# oncell

Per-customer isolated compute for AI agents. Python and TypeScript SDKs.

Each customer gets their own **cell** — compute, storage, database, vector search, and durable orchestration co-located on one machine. No network hops. No shared infrastructure.

[oncell.ai](https://oncell.ai) &middot; [Docs](https://oncell.ai/docs) &middot; [Blog](https://oncell.ai/blog)

## Install

```bash
# Python
pip install oncell

# TypeScript
npm install oncell
```

## Quick Start

### Python

```python
from oncell import Cell, Step

cell = Cell("acme-corp")

# Shell — run commands, durable by default
result = await cell.shell("git clone https://github.com/acme/app /work")

# Store — read/write files
await cell.store.write("config.json", '{"theme": "dark"}')
content = await cell.store.read("src/app.ts")

# DB — key-value + raw SQL
await cell.db.set("last_task", "add dark mode")
task = await cell.db.get("last_task")

# Search — vector search, local index
await cell.search.index("/work/src", glob="**/*.ts")
results = await cell.search.query("auth middleware", top_k=10)

# Orchestrator — durable multi-step workflows
orch = cell.orchestrator("deploy")

# Sync
result = await orch.run([
    Step("search", lambda: cell.search.query("auth")),
    Step("edit",   lambda ctx: cell.shell(ctx["search"][0]["content"])),
    Step("test",   lambda: cell.shell("npm test")),
])

# Async (fire and forget)
task_id = await orch.spawn([...])
status = orch.status(task_id)

# Streaming
async for event in orch.stream([
    Step("search", lambda: cell.search.query("auth")),
    Step("test",   lambda: cell.shell("npm test")),
]):
    print(event)  # {"step": "search", "status": "done", "progress": 0.5}
```

### TypeScript

```typescript
import { Cell } from "oncell";

const cell = new Cell("acme-corp");

// Shell
const result = await cell.shell("git clone https://github.com/acme/app /work");

// Store
await cell.store.write("config.json", '{"theme": "dark"}');
const content = await cell.store.read("src/app.ts");

// DB
await cell.db.set("last_task", "add dark mode");
const task = await cell.db.get("last_task");

// Search
await cell.search.index("/work/src", { glob: "**/*.ts" });
const results = await cell.search.query("auth middleware", 10);

// Orchestrator
const orch = cell.orchestrator("deploy");

// Sync
const ctx = await orch.run([
  { name: "search", fn: () => cell.search.query("auth") },
  { name: "test",   fn: () => cell.shell("npm test") },
]);

// Async
const taskId = await orch.spawn([...]);
const status = orch.status(taskId);

// Streaming
for await (const event of orch.stream([...])) {
  console.log(event);
}
```

## Primitives

Six primitives. Each works standalone. Together, they share the same NVMe — no glue code.

| Primitive | What | Python | TypeScript |
|-----------|------|--------|------------|
| **Shell** | Run commands | `cell.shell(cmd)` | `cell.shell(cmd)` |
| **Store** | Read/write files | `cell.store.read(path)` | `cell.store.read(path)` |
| **DB** | Key-value + SQL | `cell.db.get(key)` | `cell.db.get(key)` |
| **Search** | Vector search | `cell.search.query(q)` | `cell.search.query(q)` |
| **Journal** | Durable checkpoints | `cell.journal` | `cell.journal` |
| **Orchestrator** | Multi-step workflows | `cell.orchestrator(name)` | `cell.orchestrator(name)` |

## Why OnCell

- **No network hops.** All primitives share the same NVMe. 7 GB/s reads. Sub-10ms search.
- **Physical isolation.** Each cell is a gVisor sandbox. Cell A cannot access Cell B.
- **Durable execution.** Every shell command is journaled. Crash → resume from last step.
- **Pause economics.** Idle cells cost $0.001/hr. Wake in 200ms. NVMe state preserved.
- **Zero integration.** The NVMe is the integration layer. No duct tape.

## License

Apache 2.0
