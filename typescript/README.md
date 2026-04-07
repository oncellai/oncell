# @oncell/sdk

TypeScript SDK for [oncell.ai](https://oncell.ai) — per-customer isolated compute for AI agents.

Each cell is an isolated execution environment with filesystem, database, search, and a live preview URL. Your agent code runs inside the cell with direct local access — no network hops.

## Install

```bash
npm install @oncell/sdk
```

## Quick Start

```typescript
import { OnCell } from "@oncell/sdk";

const oncell = new OnCell({ apiKey: "oncell_sk_..." });

// Create a cell with agent code and secrets
const cell = await oncell.cells.create({
  customerId: "user-123",
  tier: "starter",        // starter | standard | performance
  image: "nextjs",        // optional — "default" | "nextjs" | custom
  secrets: { OPENROUTER_API_KEY: "sk-or-..." },
  agent: `
    module.exports = {
      async generate(ctx, params) {
        const context = ctx.search.query(params.instruction);

        const res = await ctx.fetch("https://openrouter.ai/api/v1/chat/completions", {
          method: "POST",
          headers: {
            "Authorization": "Bearer " + process.env.OPENROUTER_API_KEY,
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            model: "google/gemini-2.5-flash",
            messages: [
              { role: "system", content: "Generate HTML with Tailwind CSS." },
              { role: "user", content: params.instruction }
            ]
          })
        });
        const data = await res.json();
        const code = data.choices[0].message.content;

        ctx.store.write("index.html", code);
        ctx.journal.step("generate", "Wrote index.html", { lines: code.split("\\n").length });

        const history = ctx.db.get("history") || [];
        history.push({ instruction: params.instruction, timestamp: new Date().toISOString() });
        ctx.db.set("history", history);

        return { code, files: ctx.store.list() };
      }
    };
  `,
});

console.log(cell.previewUrl);
// https://dev-abc--user-123.cells.oncell.ai
```

## Send Requests to the Agent

```typescript
const result = await oncell.cells.request(cell.id, "generate", {
  instruction: "Build a pricing page with 3 tiers"
});
```

The agent ran inside the cell. `ctx.store.write()`, `ctx.db.set()`, `ctx.search.query()` are all local with 0ms latency. Only the LLM call goes over the network.

Open `cell.previewUrl` in a browser to see the live preview.

## Agent Context (ctx)

Agent code receives a `ctx` object with direct local access to cell primitives:

```
ctx.store                           Filesystem (NVMe)
  .write(path, content)             Write file
  .read(path) -> string             Read file
  .exists(path) -> bool             Check file
  .list(dir?) -> string[]           List files
  .delete(path)                     Delete file

ctx.db                              Key-value database
  .get(key) -> any                  Read value
  .set(key, value)                  Write value
  .delete(key)                      Delete key
  .keys() -> string[]               List keys

ctx.search                          Text search
  .query(text) -> results[]         Search files by relevance

ctx.journal                         Workflow log
  .step(type, msg, meta?)           Log an action
  .entries() -> entry[]             Read journal
  .clear()                          Clear journal

ctx.shell(cmd) -> {stdout, stderr, exitCode}
ctx.shellAsync(cmd) -> Promise<{stdout, stderr, exitCode}>
ctx.fetch                           HTTP (for LLM calls, webhooks, etc.)
ctx.stream(data)                    Send SSE event to client
ctx.cellId                          Cell ID
ctx.workDir                         Working directory path
```

All local operations (store, db, search, shell) are **0ms latency** — no network involved.

## Secrets

Secrets are injected as environment variables inside the cell. They are never written to disk.

```typescript
const cell = await oncell.cells.create({
  customerId: "user-123",
  image: "nextjs",
  secrets: {
    OPENROUTER_API_KEY: "sk-or-...",
    GITHUB_TOKEN: "ghp_...",
  },
  agent: `
    module.exports = {
      async generate(ctx, params) {
        // Access secrets via process.env
        const apiKey = process.env.OPENROUTER_API_KEY;
        // ...
      }
    };
  `,
});
```

## Cell Images

Cell images are pre-built environment templates that cells boot with. Instead of every cell running a bare Node.js runtime, you can specify an image to get a ready-made environment with frameworks, tools, and configuration pre-installed.

```typescript
const cell = await oncell.cells.create({
  customerId: "user-123",
  image: "nextjs",        // pre-built Next.js 15 + Tailwind + runtime APIs
  secrets: { OPENROUTER_API_KEY: "sk-or-..." },
  agent: agentCode,
});
```

The `image` field is optional. If omitted, cells use the `"default"` image (bare Node.js runtime).

### Available images

| Image | Description |
|---|---|
| `default` | Bare Node.js runtime. Agent code runs directly. |
| `nextjs` | Next.js 15 + Tailwind CSS + runtime APIs. Full-stack web apps out of the box. |

### How it works

- Images are pre-built `tar.gz` archives stored in S3
- Each image contains an `oncell.manifest.json` with: name, version, description, start command, health endpoint
- Images are cached on the host's NVMe after the first pull — subsequent cell creates using the same image are instant
- Custom images can be uploaded by developers (coming soon)

## Cell Lifecycle

```
create -> ACTIVE -> idle 15 min -> PAUSED -> resume -> ACTIVE
                                     |
                                   delete -> DELETED
```

- **Active**: running, billed at active rate
- **Paused**: compute freed, data persists on NVMe, billed at paused rate
- **Resume**: 200ms from NVMe cache, 5-30s if restored from S3

## Cell Management

```typescript
// List cells
const cells = await oncell.cells.list();

// Get cell details
const cell = await oncell.cells.get("dev-abc--user-123");

// Pause (frees compute, data persists)
await oncell.cells.pause(cell.id);

// Resume (200ms from NVMe cache)
await oncell.cells.resume(cell.id);

// Delete
await oncell.cells.delete(cell.id);
```

## Custom Domains

Add custom domains to your cells so users can access them at your own domain instead of the default `.cells.oncell.ai` URL.

```typescript
// Add a custom domain to a cell
const domain = await oncell.domains.add("myapp.com", cell.id);
console.log(domain.dnsInstructions);
// { record_type: "A", name: "@", values: ["x.x.x.x", "y.y.y.y"] }

// Verify DNS configuration
const result = await oncell.domains.verify("myapp.com");
if (result.dnsVerified) {
  // Provision SSL certificate
  const ssl = await oncell.domains.provisionSsl("myapp.com");
  console.log(ssl.sslStatus); // "active"
}

// List domains
const domains = await oncell.domains.list();

// Reassign domain to a different cell
await oncell.domains.reassign("myapp.com", newCell.id);

// Delete domain
await oncell.domains.delete("myapp.com");
```

## Permanent Cells

Normal cells auto-pause after 15 minutes idle. Permanent cells never pause and auto-restart on crash.

```typescript
const cell = await oncell.cells.create({
  customerId: "production-worker",
  tier: "standard",
  permanent: true,
  agent: workerAgentCode,
});

// Toggle permanent on existing cell
await oncell.cells.setPermanent(cell.id, true);
```

## File Operations

Read and write files on the cell's filesystem without going through the agent:

```typescript
await oncell.cells.writeFile(cell.id, "data/report.json", jsonContent);
const { content } = await oncell.cells.readFile(cell.id, "data/report.json");
const { files } = await oncell.cells.listFiles(cell.id);
```

## Database Operations

Read and write key-value pairs in the cell's database without going through the agent:

```typescript
await oncell.cells.dbSet(cell.id, "theme", "dark");
const { value } = await oncell.cells.dbGet(cell.id, "theme");
```

## Agent Request (auto-create/resume)

Send a request by customer ID instead of cell ID. The cell is auto-created or resumed as needed. Returns the raw `Response` object (supports both JSON and SSE streaming).

```typescript
const response = await oncell.cells.agentRequest("user-123", "generate", {
  instruction: "Build a pricing page"
});

// JSON response
const result = await response.json();

// Or SSE streaming
const reader = response.body.getReader();
```

## Streaming

Agent methods support three response modes. The cell runtime auto-detects which one:

**Sync** -- return a value:
```javascript
module.exports = {
  greet(ctx, params) {
    return { hello: params.name };
  }
};
```

**Async** -- return a promise:
```javascript
module.exports = {
  async analyze(ctx, params) {
    const result = await ctx.shellAsync("npm test");
    return { passed: result.exitCode === 0 };
  }
};
```

**Stream** -- use `ctx.stream()` during execution:
```javascript
module.exports = {
  async generate(ctx, params) {
    const res = await ctx.fetch("https://openrouter.ai/api/v1/chat/completions", {
      method: "POST",
      headers: { "Authorization": "Bearer " + API_KEY, "Content-Type": "application/json" },
      body: JSON.stringify({ model: "google/gemini-2.5-flash", messages: [...], stream: true }),
    });

    let code = "";
    const reader = res.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      ctx.stream({ text: chunk });  // sent to client in real-time
      code += chunk;
    }

    ctx.store.write("index.html", code);
    return { code, files: ctx.store.list() };  // final SSE event
  }
};
```

## Pricing

Prepaid credits. [Buy credits](https://oncell.ai/dashboard/billing).

| Tier | Spec | Active | Paused |
|---|---|---|---|
| Starter | 1 vCPU, 1 GB | $0.10/hr | $0.003/hr |
| Standard | 2 vCPU, 4 GB | $0.25/hr | $0.005/hr |
| Performance | 4 vCPU, 8 GB | $0.50/hr | $0.01/hr |

```typescript
const tiers = await oncell.tiers();
```

Cells auto-pause after 15 min idle (paused rate). Permanent cells stay active.

## API Reference

### `new OnCell(opts)`

| Option | Type | Default | Description |
|---|---|---|---|
| `apiKey` | `string` | `ONCELL_API_KEY` env var | API key (`oncell_sk_...`) |
| `baseUrl` | `string` | `https://api.oncell.ai` | API base URL |

### `oncell.cells`

| Method | Description |
|---|---|
| `create(opts)` | Create a cell with optional agent code, image, and secrets |
| `list()` | List all cells |
| `get(cellId)` | Get a single cell |
| `pause(cellId)` | Pause a cell |
| `resume(cellId)` | Resume a paused cell |
| `delete(cellId)` | Delete a cell |
| `setPermanent(cellId, bool)` | Toggle permanent flag |
| `writeFile(cellId, path, content)` | Write a file to the cell |
| `readFile(cellId, path)` | Read a file from the cell |
| `listFiles(cellId, dir?)` | List files in the cell |
| `dbSet(cellId, key, value)` | Set a DB key-value pair |
| `dbGet(cellId, key)` | Get a DB value by key |
| `sendRequest(cellId, method, params?)` | Send a request to the agent |
| `request(cellId, method, params?)` | Alias for sendRequest |
| `agentRequest(customerId, method, params?)` | Send request by customer ID (auto-create/resume) |

### `oncell.domains`

| Method | Description |
|---|---|
| `add(domain, cellId)` | Add a custom domain to a cell |
| `list()` | List all custom domains |
| `get(domain)` | Get a single domain |
| `verify(domain)` | Verify DNS configuration |
| `provisionSsl(domain)` | Provision SSL certificate |
| `reassign(domain, cellId)` | Reassign domain to a different cell |
| `delete(domain)` | Delete a custom domain |

### `oncell.tiers()`

Returns available pricing tiers.

## Links

- [oncell.ai](https://oncell.ai) -- sign up
- [Dashboard](https://oncell.ai/dashboard) -- manage cells, keys, billing
- [Demo](https://github.com/oncellai/oncell-demo-agent) -- coding agent built on OnCell
- [Architecture](https://github.com/oncellai/oncell/blob/main/ARCHITECTURE.md)

## License

Apache-2.0
