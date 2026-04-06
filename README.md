# oncell

Per-customer isolated compute for AI agents. [oncell.ai](https://oncell.ai)

Each cell is an isolated execution environment with filesystem, database, search, and a live preview URL. Your agent code runs inside the cell with direct local access — no network hops.

## Getting Started

### 1. Sign up

Go to [oncell.ai](https://oncell.ai) and create an account (GitHub, Google, or email).

### 2. Add credits

Go to [Dashboard → Billing](https://oncell.ai/dashboard/billing) and add at least $5 in credits. Minimum $5 balance required to use the platform.

### 3. Create an API key

Go to [Dashboard → API Keys](https://oncell.ai/dashboard/keys) and create a key. Copy it — it's shown only once.

### 4. Install the SDK

```bash
npm install oncell
```

### 5. Create a cell with an agent

```typescript
import { OnCell } from "oncell";

const oncell = new OnCell({ apiKey: "oncell_sk_..." });

// Create a cell with your agent code inline
const cell = await oncell.cells.create({
  customerId: "user-123",
  tier: "starter",        // starter | standard | performance
  agent: `
    module.exports = {
      async generate(ctx, params) {
        // Search existing code for context (local — 0ms)
        const context = ctx.search.query(params.instruction);

        // Call LLM (only network call)
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

        // Write to cell storage (local NVMe — 0ms)
        ctx.store.write("index.html", code);

        // Log the action (local — 0ms)
        ctx.journal.step("generate", "Wrote index.html", { lines: code.split("\\n").length });

        // Save conversation (local DB — 0ms)
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

### 6. Send requests to the agent

```typescript
const result = await oncell.cells.request(cell.id, "generate", {
  instruction: "Build a pricing page with 3 tiers"
});

console.log(result);
// { code: "<!DOCTYPE html>...", files: ["index.html"] }
```

The agent ran inside the cell. `ctx.store.write()`, `ctx.db.set()`, `ctx.search.query()` — all local, no network. Only the LLM call went over the network.

### 7. View the preview

Open `cell.previewUrl` in a browser — the cell serves `index.html` automatically.

### 8. Send follow-up requests

```typescript
const result2 = await oncell.cells.request(cell.id, "generate", {
  instruction: "Make it dark mode"
});
// Agent reads existing code from ctx.store, edits it, writes it back
```

---

## Agent Context (ctx)

Your agent code receives a `ctx` object with direct local access to cell primitives:

```
ctx.store                           Filesystem (NVMe)
  .write(path, content)             Write file
  .read(path) → string              Read file
  .exists(path) → bool              Check file
  .list(dir?) → string[]            List files
  .delete(path)                     Delete file

ctx.db                              Key-value database
  .get(key) → any                   Read value
  .set(key, value)                  Write value
  .delete(key)                      Delete key
  .keys() → string[]                List keys

ctx.search                          Text search
  .query(text) → results[]          Search files by relevance

ctx.journal                         Workflow log
  .step(type, msg, meta?)           Log an action
  .entries() → entry[]              Read journal
  .clear()                          Clear journal

ctx.shell(cmd) → {stdout, stderr, exitCode}
ctx.shellAsync(cmd) → Promise<{stdout, stderr, exitCode}>
ctx.fetch                           HTTP (for LLM calls, webhooks, etc.)
ctx.cellId                          Cell ID
ctx.workDir                         Working directory path
```

ctx.stream(data)                    Send SSE event to client (enables streaming mode)

All local operations (store, db, search, shell) are **0ms latency** — no network involved.

---

## Streaming

Agent methods support three response modes — the cell runtime auto-detects which one:

### Sync — return a value
```javascript
module.exports = {
  greet(ctx, params) {
    return { hello: params.name };
  }
};
```
→ JSON response

### Async — return a promise
```javascript
module.exports = {
  async analyze(ctx, params) {
    const result = await ctx.shellAsync("npm test");
    return { passed: result.exitCode === 0 };
  }
};
```
→ JSON response (awaited)

### Stream — use ctx.stream() during execution
```javascript
module.exports = {
  async generate(ctx, params) {
    // Stream LLM response back to client in real-time
    const res = await ctx.fetch("https://openrouter.ai/api/v1/chat/completions", {
      method: "POST",
      headers: { "Authorization": "Bearer " + API_KEY, "Content-Type": "application/json" },
      body: JSON.stringify({ model: "google/gemini-2.5-flash", messages: [...], stream: true }),
    });

    let code = "";
    const reader = res.body.getReader();
    const decoder = new TextDecoder();

    // Each ctx.stream() call sends an SSE event to the client immediately
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      // parse SSE chunks from LLM...
      ctx.stream({ text: chunk });  // sent to client in real-time
      code += chunk;
    }

    ctx.store.write("index.html", code);
    return { code, files: ctx.store.list() };  // sent as final SSE event
  }
};
```
→ SSE stream, then final JSON event with `{ done: true, ...result }`

---

## Cell Management

```typescript
// List cells
const cells = await oncell.cells.list();

// Get cell details
const cell = await oncell.cells.get("dev-abc--user-123");

// Pause (frees compute, data persists, billed at paused rate)
await oncell.cells.pause(cell.id);

// Resume (200ms from NVMe cache, 5-30s from S3)
await oncell.cells.resume(cell.id);

// Delete
await oncell.cells.delete(cell.id);
```

---

## Permanent Cells

Normal cells pause after 15 minutes of inactivity. Permanent cells never pause and auto-restart on crash.

```typescript
// Create a permanent cell
const cell = await oncell.cells.create({
  customerId: "production-worker",
  tier: "standard",
  permanent: true,
  agent: workerAgentCode,
});

// Toggle permanent on existing cell
await oncell.cells.setPermanent(cell.id, true);
```

---

## Observability

### Journal (agent workflow)

```typescript
// In your agent code:
ctx.journal.step("plan", "Planning 3-step build");
ctx.journal.step("llm", "Called Gemini", { tokens: 1200, duration: 2100 });
ctx.journal.step("write", "Wrote app/page.tsx", { lines: 200 });
ctx.journal.step("done", "Build complete");

// Read from your app:
const { entries } = await oncell.cells.request(cell.id, "journal", {});
// [{ ts: "...", type: "plan", msg: "Planning 3-step build" }, ...]
```

### Logs (runtime output)

```typescript
// In your agent code:
console.log("Processing request...");
console.error("LLM timeout, retrying...");

// Read from your app:
const { lines } = await oncell.cells.request(cell.id, "logs", { lines: 100 });
// [{ ts: "...", level: "info", msg: "Processing request..." }, ...]
```

### Metrics

```typescript
const metrics = await oncell.cells.request(cell.id, "metrics", {});
// { requests: 142, errors: 3, avg_latency: 12, uptime: 3600 }
```

All observability data is also visible in the [Dashboard](https://oncell.ai/dashboard) — click any cell to see Workflow, Logs, and Metrics tabs.

---

## File Operations (without agent)

You can also use cells as pure storage without an agent:

```typescript
await oncell.cells.writeFile(cell.id, "data/report.json", jsonContent);
const { content } = await oncell.cells.readFile(cell.id, "data/report.json");
const { files } = await oncell.cells.listFiles(cell.id);
```

---

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

---

## Links

- [oncell.ai](https://oncell.ai) — sign up
- [Dashboard](https://oncell.ai/dashboard) — manage cells, keys, billing
- [Demo](https://github.com/oncellai/oncell-demo-agent) — coding agent built on oncell
- [Architecture](https://github.com/oncellai/oncell/blob/main/ARCHITECTURE.md)

## License

Apache-2.0
