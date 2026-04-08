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
 * Built-in methods handled by the runtime before dispatching to the agent.
 *
 * DB entity CRUD (db_create, db_query, etc.) proxies to the cell's own
 * /api/db HTTP endpoint so that SDK calls and window.db calls in the
 * generated app share the same .data/db.json storage file.
 *
 * Key-value (db_set, db_get) uses cell.db directly (separate .data/cell.json).
 * File operations use cell.store directly.
 *
 * Returns undefined if the method is not built-in (falls through to agent).
 */

// Port of the cell's Next.js app — used for proxying entity CRUD
const CELL_APP_PORT = process.env.PORT || process.env.CELL_APP_PORT || "3000";
const CELL_APP_URL = `http://localhost:${CELL_APP_PORT}`;

async function cellDbFetch(method: string, path: string, body?: any): Promise<any> {
  const res = await fetch(`${CELL_APP_URL}/api/db${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  return res.json();
}

async function handleDbMethod(cell: Cell, method: string, params: Record<string, any>): Promise<any | undefined> {
  switch (method) {
    // ─── Key-value (uses cell.db — separate storage) ───
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

    // ─── Entity CRUD (proxies to cell's /api/db → shared db.json) ───
    case "db_create":
      return cellDbFetch("POST", "", { entity: params.entity, data: params.data });

    case "db_query": {
      const qs = new URLSearchParams({ entity: params.entity });
      if (params.where) qs.set("filter", JSON.stringify(params.where));
      if (params.orderBy) qs.set("sort", params.orderBy);
      if (params.order) qs.set("order", params.order);
      if (params.limit) qs.set("limit", String(params.limit));
      if (params.offset) qs.set("offset", String(params.offset));
      return cellDbFetch("GET", `?${qs.toString()}`);
    }

    case "db_get_all": {
      return cellDbFetch("GET", `?entity=${encodeURIComponent(params.entity)}`);
    }

    case "db_get_by_id":
      return cellDbFetch("GET", `?entity=${encodeURIComponent(params.entity)}&id=${encodeURIComponent(params.id)}`);

    case "db_update":
      return cellDbFetch("PUT", "", { entity: params.entity, id: params.id, data: params.data });

    case "db_delete_record":
      return cellDbFetch("DELETE", `?entity=${encodeURIComponent(params.entity)}&id=${encodeURIComponent(params.id)}`);

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
