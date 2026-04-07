/**
 * Tests for the OnCell REST API client.
 *
 * Uses a mock fetch to verify correct HTTP calls without hitting the real API.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { OnCell, OnCellError } from "../src/client.js";

// ─── Mock fetch ───

type MockResponse = {
  status: number;
  body: unknown;
};

let mockResponses: MockResponse[] = [];
let fetchCalls: { url: string; init: RequestInit }[] = [];

function pushMock(status: number, body: unknown) {
  mockResponses.push({ status, body });
}

beforeEach(() => {
  mockResponses = [];
  fetchCalls = [];

  vi.stubGlobal("fetch", async (url: string | URL | Request, init?: RequestInit) => {
    const urlStr = typeof url === "string" ? url : url instanceof URL ? url.toString() : url.url;
    fetchCalls.push({ url: urlStr, init: init ?? {} });

    const mock = mockResponses.shift();
    if (!mock) throw new Error(`No mock response for ${init?.method ?? "GET"} ${urlStr}`);

    return {
      ok: mock.status >= 200 && mock.status < 300,
      status: mock.status,
      json: async () => mock.body,
      headers: new Headers({ "content-type": "application/json" }),
    } as Response;
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

function client(opts?: { baseUrl?: string }) {
  return new OnCell({ apiKey: "oncell_sk_test123", baseUrl: opts?.baseUrl ?? "https://api.oncell.ai" });
}

// ─── Constructor ───

describe("OnCell constructor", () => {
  it("throws without apiKey", () => {
    expect(() => new OnCell({})).toThrow("apiKey is required");
  });

  it("accepts apiKey", () => {
    const c = client();
    expect(c).toBeDefined();
  });
});

// ─── Cells CRUD ───

describe("cells.create", () => {
  it("sends POST with customer_id and returns Cell", async () => {
    const c = client();
    pushMock(201, {
      cell_id: "dev--user-1",
      customer_id: "user-1",
      tier: "standard",
      status: "active",
      permanent: false,
      created_at: "2026-04-06T00:00:00.000Z",
    });

    const cell = await c.cells.create({ customerId: "user-1", tier: "standard" });

    expect(fetchCalls).toHaveLength(1);
    expect(fetchCalls[0].url).toBe("https://api.oncell.ai/api/v1/cells");
    expect(JSON.parse(fetchCalls[0].init.body as string)).toEqual({
      customer_id: "user-1",
      tier: "standard",
      permanent: undefined,
    });
    expect(cell.id).toBe("dev--user-1");
    expect(cell.customerId).toBe("user-1");
    expect(cell.status).toBe("active");
    expect(cell.previewUrl).toBe("https://dev--user-1.cells.oncell.ai");
  });
});

describe("cells.list", () => {
  it("returns array of cells", async () => {
    const c = client();
    pushMock(200, {
      cells: [
        { cell_id: "c1", customer_id: "u1", status: "active", tier: "starter" },
        { cell_id: "c2", customer_id: "u2", status: "paused", tier: "standard" },
      ],
    });

    const cells = await c.cells.list();
    expect(cells).toHaveLength(2);
    expect(cells[0].id).toBe("c1");
    expect(cells[1].status).toBe("paused");
  });
});

describe("cells.get", () => {
  it("fetches a single cell", async () => {
    const c = client();
    pushMock(200, { cell_id: "c1", customer_id: "u1", status: "active", tier: "starter" });

    const cell = await c.cells.get("c1");
    expect(cell.id).toBe("c1");
    expect(fetchCalls[0].url).toContain("/api/v1/cells/c1");
  });
});

describe("cells.pause", () => {
  it("sends POST to pause endpoint", async () => {
    const c = client();
    pushMock(200, { cell_id: "c1", status: "paused" });

    const cell = await c.cells.pause("c1");
    expect(cell.status).toBe("paused");
    expect(fetchCalls[0].url).toContain("/pause");
  });
});

describe("cells.resume", () => {
  it("sends POST to resume endpoint", async () => {
    const c = client();
    pushMock(200, { cell_id: "c1", status: "active" });

    const cell = await c.cells.resume("c1");
    expect(cell.status).toBe("active");
    expect(fetchCalls[0].url).toContain("/resume");
  });
});

describe("cells.delete", () => {
  it("sends DELETE", async () => {
    const c = client();
    pushMock(200, { ok: true });

    await c.cells.delete("c1");
    expect(fetchCalls[0].init.method).toBe("DELETE");
  });
});

describe("cells.setPermanent", () => {
  it("sends POST with permanent flag", async () => {
    const c = client();
    pushMock(200, { cell_id: "c1", permanent: true });

    await c.cells.setPermanent("c1", true);
    expect(fetchCalls[0].url).toContain("/permanent");
    expect(JSON.parse(fetchCalls[0].init.body as string)).toEqual({ permanent: true });
  });
});

// ─── File operations ───

describe("cells.writeFile", () => {
  it("proxies write_file through request endpoint", async () => {
    const c = client();
    pushMock(200, { ok: true });

    await c.cells.writeFile("c1", "index.html", "<h1>hi</h1>");
    const body = JSON.parse(fetchCalls[0].init.body as string);
    expect(body.method).toBe("write_file");
    expect(body.params.path).toBe("index.html");
    expect(body.params.content).toBe("<h1>hi</h1>");
  });
});

describe("cells.readFile", () => {
  it("proxies read_file and returns content", async () => {
    const c = client();
    pushMock(200, { content: "<h1>hi</h1>" });

    const result = await c.cells.readFile("c1", "index.html");
    expect(result.content).toBe("<h1>hi</h1>");
  });
});

describe("cells.listFiles", () => {
  it("returns file list", async () => {
    const c = client();
    pushMock(200, { files: ["index.html", "style.css"] });

    const result = await c.cells.listFiles("c1");
    expect(result.files).toEqual(["index.html", "style.css"]);
  });
});

// ─── DB operations ───

describe("cells.dbSet", () => {
  it("proxies db_set", async () => {
    const c = client();
    pushMock(200, { ok: true });

    await c.cells.dbSet("c1", "theme", "dark");
    const body = JSON.parse(fetchCalls[0].init.body as string);
    expect(body.method).toBe("db_set");
    expect(body.params).toEqual({ key: "theme", value: "dark" });
  });
});

describe("cells.dbGet", () => {
  it("proxies db_get and returns value", async () => {
    const c = client();
    pushMock(200, { value: "dark" });

    const result = await c.cells.dbGet("c1", "theme");
    expect(result.value).toBe("dark");
  });
});

// ─── Generic request ───

describe("cells.sendRequest", () => {
  it("sends arbitrary method and params", async () => {
    const c = client();
    pushMock(200, { result: "generated" });

    const result = await c.cells.sendRequest("c1", "generate", { instruction: "build a page" });
    expect(result).toEqual({ result: "generated" });
    const body = JSON.parse(fetchCalls[0].init.body as string);
    expect(body.method).toBe("generate");
    expect(body.params.instruction).toBe("build a page");
  });
});

describe("cells.request (alias)", () => {
  it("delegates to sendRequest", async () => {
    const c = client();
    pushMock(200, { result: "generated" });

    const result = await c.cells.request("c1", "generate", { instruction: "build a page" });
    expect(result).toEqual({ result: "generated" });
  });
});

// ─── Tiers ───

describe("tiers", () => {
  it("fetches tier list", async () => {
    const c = client();
    pushMock(200, {
      tiers: [
        { id: "starter", name: "Starter", spec: "1cpu-1gb", active_price: "$0.10/hr", paused_price: "$0.003/hr", storage: "10GB" },
        { id: "standard", name: "Standard", spec: "2cpu-4gb", active_price: "$0.25/hr", paused_price: "$0.005/hr", storage: "50GB" },
      ],
    });

    const tiers = await c.tiers();
    expect(tiers).toHaveLength(2);
    expect(tiers[0].id).toBe("starter");
    expect(tiers[1].activePrice).toBe("$0.25/hr");
  });
});

// ─── Error handling ───

describe("error handling", () => {
  it("throws OnCellError on non-2xx", async () => {
    const c = client();
    pushMock(404, { error: "not found" });

    await expect(c.cells.get("nonexistent")).rejects.toThrow(OnCellError);
    await expect(async () => {
      pushMock(404, { error: "not found" });
      await c.cells.get("nonexistent");
    }).rejects.toMatchObject({ status: 404 });
  });

  it("includes auth header in all requests", async () => {
    const c = client();
    pushMock(200, { cells: [] });

    await c.cells.list();
    expect(fetchCalls[0].init.headers).toHaveProperty("Authorization", "Bearer oncell_sk_test123");
  });
});
