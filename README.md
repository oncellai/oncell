# oncell

REST API client for [oncell.ai](https://oncell.ai) — per-customer isolated compute for AI agents.

Create, manage, and interact with cells from your application. Each cell is an isolated compute environment with its own filesystem, database, and agent runtime.

## Install

```bash
# TypeScript / Node.js
npm install oncell

# Python
pip install oncell
```

## Quick Start

### TypeScript

```typescript
import { OnCell } from "oncell";

const oncell = new OnCell({ apiKey: "oncell_sk_..." });

// Create a cell for a customer
const cell = await oncell.cells.create({ customerId: "user-1", tier: "standard" });
console.log(cell.previewUrl); // https://dev--user-1.cells.oncell.ai

// Write files to the cell
await oncell.cells.writeFile(cell.id, "index.html", "<h1>Hello</h1>");

// Read files
const { content } = await oncell.cells.readFile(cell.id, "index.html");

// Key-value database
await oncell.cells.dbSet(cell.id, "theme", "dark");
const { value } = await oncell.cells.dbGet(cell.id, "theme");

// Send requests to the agent runtime
const result = await oncell.cells.request_(cell.id, "generate", {
  instruction: "build a landing page",
});

// Lifecycle
await oncell.cells.pause(cell.id);
await oncell.cells.resume(cell.id);
await oncell.cells.setPermanent(cell.id, true);
await oncell.cells.delete(cell.id);

// List cells and pricing tiers
const cells = await oncell.cells.list();
const tiers = await oncell.tiers();
```

### Python

```python
from oncell import OnCell

oncell = OnCell(api_key="oncell_sk_...")

# Create a cell
cell = await oncell.cells.create(customer_id="user-1", tier="standard")
print(cell.preview_url)  # https://dev--user-1.cells.oncell.ai

# Write files
await oncell.cells.write_file(cell.id, "index.html", "<h1>Hello</h1>")

# Read files
result = await oncell.cells.read_file(cell.id, "index.html")
print(result["content"])

# Key-value database
await oncell.cells.db_set(cell.id, "theme", "dark")
result = await oncell.cells.db_get(cell.id, "theme")
print(result["value"])

# Generic agent request
result = await oncell.cells.request(cell.id, "generate", {
    "instruction": "build a landing page",
})

# Lifecycle
await oncell.cells.pause(cell.id)
await oncell.cells.resume(cell.id)
await oncell.cells.set_permanent(cell.id, True)
await oncell.cells.delete(cell.id)

# List cells and tiers
cells = await oncell.cells.list()
tiers = await oncell.tiers()
```

Synchronous methods are also available (Python only):

```python
cell = oncell.cells.create_sync(customer_id="user-1")
oncell.cells.write_file_sync(cell.id, "index.html", "<h1>Hello</h1>")
```

## API Reference

### `OnCell(options)`

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `apiKey` / `api_key` | string | `ONCELL_API_KEY` env | Your API key |
| `baseUrl` / `base_url` | string | `https://api.oncell.ai` | API base URL |

### Cell Methods

| Method | Description |
|--------|-------------|
| `cells.create({ customerId, tier?, permanent? })` | Create a new cell |
| `cells.list()` | List all cells |
| `cells.get(cellId)` | Get a cell by ID |
| `cells.pause(cellId)` | Pause a cell |
| `cells.resume(cellId)` | Resume a paused cell |
| `cells.delete(cellId)` | Delete a cell |
| `cells.setPermanent(cellId, permanent)` | Set permanent flag |
| `cells.writeFile(cellId, path, content)` | Write a file |
| `cells.readFile(cellId, path)` | Read a file |
| `cells.listFiles(cellId, dir?)` | List files |
| `cells.dbSet(cellId, key, value)` | Set a DB key |
| `cells.dbGet(cellId, key)` | Get a DB value |
| `cells.request_(cellId, method, params?)` | Generic agent request |
| `tiers()` | List pricing tiers |

### Cell Object

| Property | Type | Description |
|----------|------|-------------|
| `id` | string | Cell ID |
| `customerId` / `customer_id` | string | Customer ID |
| `tier` | string | Pricing tier |
| `status` | string | `active` or `paused` |
| `permanent` | boolean | Whether the cell persists when idle |
| `previewUrl` / `preview_url` | string | `https://{cell-id}.cells.oncell.ai` |

## Pricing Tiers

| Tier | Spec | Active | Paused |
|------|------|--------|--------|
| Starter | 1 CPU, 1 GB | $0.10/hr | $0.003/hr |
| Standard | 2 CPU, 4 GB | $0.25/hr | $0.005/hr |
| Performance | 4 CPU, 8 GB | $0.50/hr | $0.01/hr |

## License

Apache 2.0
