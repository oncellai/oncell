/**
 * Runtime — runs inside the cell. Loads the agent, handles requests.
 *
 * Usage (called by the base image entrypoint):
 *     npx tsx oncell/runtime.ts --agent /app/agent.ts --cell-id acme-corp --port 8080
 */

import { createServer, IncomingMessage, ServerResponse } from "http";
import { resolve } from "path";
import { Cell } from "./cell.js";
import { Agent } from "./agent.js";

async function loadAgent(agentPath: string): Promise<Agent> {
  const absPath = resolve(agentPath);
  const mod = await import(absPath);
  const exported = mod.default ?? Object.values(mod).find(
    (v: any) => typeof v === "function" && v.prototype instanceof Agent
  );
  if (!exported) {
    throw new Error(`no Agent subclass found in ${agentPath}`);
  }
  return new exported();
}

function readBody(req: IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => resolve(Buffer.concat(chunks).toString()));
    req.on("error", reject);
  });
}

async function handleRequest(
  agent: Agent,
  cell: Cell,
  req: IncomingMessage,
  res: ServerResponse
) {
  const url = req.url ?? "/";
  let status = 200;
  let result: any;

  try {
    if (url === "/health") {
      result = { status: "ok", cell_id: cell.id };

    } else if (url === "/setup" && req.method === "POST") {
      await agent.setup(cell);
      result = { status: "ok" };

    } else if (url === "/request" && req.method === "POST") {
      const raw = await readBody(req);
      const body = JSON.parse(raw);
      if (!body.method) {
        status = 400;
        result = { error: "missing 'method' in request body" };
      } else {
        // Built-in DB entity CRUD — handled by the runtime, not the agent
        const dbResult = await handleDbMethod(cell, body.method, body.params ?? {});
        if (dbResult !== undefined) {
          result = dbResult;
        } else {
          result = await agent.onRequest(cell, body.method, body.params ?? {});
        }
      }

    } else if (url === "/teardown" && req.method === "POST") {
      await agent.teardown(cell);
      result = { status: "ok" };

    } else {
      status = 404;
      result = { error: `not found: ${url}` };
    }
  } catch (err: any) {
    status = 500;
    result = { error: err.message, stack: err.stack };
  }

  const body = JSON.stringify(result);
  res.writeHead(status, { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(body) });
  res.end(body);
}

/**
 * Built-in DB methods handled by the runtime.
 * Supports both key-value (db_set/db_get) and entity CRUD (db_create/db_query/etc).
 * Returns undefined if the method is not a DB method (falls through to agent).
 */
async function handleDbMethod(cell: Cell, method: string, params: Record<string, any>): Promise<any | undefined> {
  switch (method) {
    // ─── Key-value ───
    case "db_set":
      await cell.db.set(params.key, params.value);
      return { ok: true };
    case "db_get":
      return { value: await cell.db.get(params.key) };
    case "db_delete":
      await cell.db.delete(params.key);
      return { ok: true };
    case "db_keys":
      return { keys: await cell.db.keys(params.prefix || "") };

    // ─── Entity CRUD ───
    // Entities are stored as db key "entity:{name}" → JSON array of records
    case "db_create": {
      const { entity, data } = params;
      if (!entity || !data) return { error: "entity and data required" };
      const key = `entity:${entity}`;
      const items: any[] = (await cell.db.get(key)) as any[] || [];
      const record = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        ...data,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };
      items.push(record);
      await cell.db.set(key, items);
      return record;
    }

    case "db_query": {
      const { entity, where, limit, offset, orderBy, order } = params;
      if (!entity) return { error: "entity required" };
      const key = `entity:${entity}`;
      let items: any[] = (await cell.db.get(key)) as any[] || [];

      // Filter
      if (where && typeof where === "object") {
        items = items.filter((item: any) =>
          Object.entries(where).every(([k, v]) => item[k] === v)
        );
      }

      // Sort
      if (orderBy) {
        const dir = order === "desc" ? -1 : 1;
        items.sort((a: any, b: any) => (a[orderBy] > b[orderBy] ? dir : -dir));
      }

      const total = items.length;
      if (offset) items = items.slice(offset);
      if (limit) items = items.slice(0, limit);

      return { items, total };
    }

    case "db_get_all": {
      const { entity } = params;
      if (!entity) return { error: "entity required" };
      const items: any[] = (await cell.db.get(`entity:${entity}`)) as any[] || [];
      return { items, total: items.length };
    }

    case "db_get_by_id": {
      const { entity, id } = params;
      if (!entity || !id) return { error: "entity and id required" };
      const items: any[] = (await cell.db.get(`entity:${entity}`)) as any[] || [];
      const record = items.find((r: any) => r.id === id);
      if (!record) return { error: "not found" };
      return record;
    }

    case "db_update": {
      const { entity, id, data } = params;
      if (!entity || !id || !data) return { error: "entity, id, and data required" };
      const key = `entity:${entity}`;
      const items: any[] = (await cell.db.get(key)) as any[] || [];
      const idx = items.findIndex((r: any) => r.id === id);
      if (idx === -1) return { error: "not found" };
      items[idx] = { ...items[idx], ...data, updatedAt: new Date().toISOString() };
      await cell.db.set(key, items);
      return items[idx];
    }

    case "db_delete_record": {
      const { entity, id } = params;
      if (!entity || !id) return { error: "entity and id required" };
      const key = `entity:${entity}`;
      const items: any[] = (await cell.db.get(key)) as any[] || [];
      const idx = items.findIndex((r: any) => r.id === id);
      if (idx === -1) return { error: "not found" };
      items.splice(idx, 1);
      await cell.db.set(key, items);
      return { ok: true };
    }

    // ─── File operations ───
    case "write_file":
      cell.store.write(params.path, params.content);
      return { ok: true };
    case "read_file":
      return { content: cell.store.read(params.path) };
    case "list_files":
      return { files: cell.store.list(params.path) };

    default:
      return undefined; // Not a built-in method — fall through to agent
  }
}

async function main() {
  const args = process.argv.slice(2);
  const getArg = (name: string, fallback: string) => {
    const idx = args.indexOf(name);
    return idx >= 0 ? args[idx + 1] : fallback;
  };

  const agentPath = process.env.ONCELL_AGENT_PATH ?? getArg("--agent", "/app/agent.ts");
  const cellId = process.env.ONCELL_CELL_ID ?? getArg("--cell-id", "default");
  const port = parseInt(process.env.ONCELL_PORT ?? getArg("--port", "8080"));
  const cellsDir = process.env.ONCELL_CELLS_DIR ?? getArg("--cells-dir", "/cells");
  const controlPlaneUrl = process.env.ONCELL_CONTROL_PLANE_URL ?? getArg("--control-plane-url", "");

  const agent = await loadAgent(agentPath);
  const cell = new Cell(cellId, { baseDir: cellsDir, controlPlaneUrl: controlPlaneUrl || undefined });

  const server = createServer((req, res) => {
    handleRequest(agent, cell, req, res).catch((err) => {
      res.writeHead(500, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: err.message }));
    });
  });

  cell.heartbeat.start();

  server.listen(port, "0.0.0.0", () => {
    console.log(`oncell runtime started — cell=${cellId} port=${port}`);
  });

  const shutdown = () => {
    console.log("shutting down...");
    cell.heartbeat.stop();
    server.close(() => {
      console.log("oncell runtime stopped");
      process.exit(0);
    });
  };

  process.on("SIGTERM", shutdown);
  process.on("SIGINT", shutdown);
}

main().catch((err) => {
  console.error("runtime failed:", err);
  process.exit(1);
});
