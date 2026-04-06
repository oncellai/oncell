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
        result = await agent.onRequest(cell, body.method, body.params ?? {});
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
