/**
 * OnCell REST API client.
 *
 * Usage:
 *   import { OnCell } from "oncell";
 *   const oncell = new OnCell({ apiKey: "oncell_sk_..." });
 *   const cell = await oncell.cells.create({ customerId: "user-1" });
 *   console.log(cell.previewUrl);
 */

/** Options for constructing the OnCell client. */
export interface OnCellOptions {
  /** API key (oncell_sk_...). Falls back to ONCELL_API_KEY env var. */
  apiKey?: string;
  /** Base URL for the API. Defaults to https://api.oncell.ai */
  baseUrl?: string;
}

/** A cell as returned by the API, with convenience properties. */
export interface Cell {
  id: string;
  customerId: string;
  tier: string;
  status: string;
  permanent: boolean;
  hostId?: string;
  port?: number;
  createdAt: string;
  lastActiveAt?: string;
  /** Live preview URL for this cell. */
  previewUrl: string;
}

/** Tier pricing info. */
export interface Tier {
  id: string;
  name: string;
  spec: string;
  activePrice: string;
  pausedPrice: string;
  storage: string;
}

/** Options for creating a cell. */
export interface CellCreateOptions {
  customerId: string;
  tier?: string;
  permanent?: boolean;
}

/** File entry returned from listFiles. */
export interface FileEntry {
  path: string;
}

/** Error thrown when the API returns a non-2xx status. */
export class OnCellError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, body: unknown) {
    const msg = typeof body === "object" && body !== null && "error" in body
      ? (body as Record<string, unknown>).error
      : JSON.stringify(body);
    super(`OnCell API error (${status}): ${msg}`);
    this.name = "OnCellError";
    this.status = status;
    this.body = body;
  }
}

// ─── Internal helpers ───

function toCell(raw: Record<string, unknown>): Cell {
  const id = (raw.cell_id ?? raw.id ?? "") as string;
  return {
    id,
    customerId: (raw.customer_id ?? "") as string,
    tier: (raw.tier ?? "starter") as string,
    status: (raw.status ?? "active") as string,
    permanent: !!raw.permanent,
    hostId: raw.host_id as string | undefined,
    port: raw.port as number | undefined,
    createdAt: (raw.created_at ?? "") as string,
    lastActiveAt: raw.last_active_at as string | undefined,
    previewUrl: `https://${id}.cells.oncell.ai`,
  };
}

function toTier(raw: Record<string, unknown>): Tier {
  return {
    id: raw.id as string,
    name: raw.name as string,
    spec: raw.spec as string,
    activePrice: raw.active_price as string,
    pausedPrice: raw.paused_price as string,
    storage: raw.storage as string,
  };
}

// ─── CellsResource ───

class CellsResource {
  private apiKey: string;
  private baseUrl: string;

  constructor(apiKey: string, baseUrl: string) {
    this.apiKey = apiKey;
    this.baseUrl = baseUrl;
  }

  private async request<T = unknown>(
    method: string,
    path: string,
    body?: unknown,
  ): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const headers: Record<string, string> = {
      Authorization: `Bearer ${this.apiKey}`,
    };
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
    }

    const res = await fetch(url, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });

    // 204 No Content
    if (res.status === 204) return undefined as T;

    const json = await res.json();

    if (!res.ok) {
      throw new OnCellError(res.status, json);
    }

    return json as T;
  }

  /** Create a new cell. */
  async create(opts: CellCreateOptions): Promise<Cell> {
    const raw = await this.request<Record<string, unknown>>("POST", "/api/v1/cells", {
      customer_id: opts.customerId,
      tier: opts.tier,
      permanent: opts.permanent,
    });
    return toCell(raw);
  }

  /** List all cells for the authenticated developer. */
  async list(): Promise<Cell[]> {
    const raw = await this.request<{ cells: Record<string, unknown>[] }>("GET", "/api/v1/cells");
    return (raw.cells || []).map(toCell);
  }

  /** Get a single cell by ID. */
  async get(cellId: string): Promise<Cell> {
    const raw = await this.request<Record<string, unknown>>("GET", `/api/v1/cells/${encodeURIComponent(cellId)}`);
    return toCell(raw);
  }

  /** Pause a cell. */
  async pause(cellId: string): Promise<Cell> {
    const raw = await this.request<Record<string, unknown>>("POST", `/api/v1/cells/${encodeURIComponent(cellId)}/pause`);
    return toCell({ ...raw, cell_id: cellId });
  }

  /** Resume a paused cell. */
  async resume(cellId: string): Promise<Cell> {
    const raw = await this.request<Record<string, unknown>>("POST", `/api/v1/cells/${encodeURIComponent(cellId)}/resume`);
    return toCell({ ...raw, cell_id: cellId });
  }

  /** Delete a cell. */
  async delete(cellId: string): Promise<void> {
    await this.request("DELETE", `/api/v1/cells/${encodeURIComponent(cellId)}`);
  }

  /** Set or clear the permanent flag on a cell. */
  async setPermanent(cellId: string, permanent: boolean): Promise<void> {
    await this.request("POST", `/api/v1/cells/${encodeURIComponent(cellId)}/permanent`, { permanent });
  }

  // ─── File operations (proxied through the agent runtime) ───

  /** Write a file to the cell's filesystem. */
  async writeFile(cellId: string, path: string, content: string): Promise<void> {
    await this.request("POST", `/api/v1/cells/${encodeURIComponent(cellId)}/request`, {
      method: "write_file",
      params: { path, content },
    });
  }

  /** Read a file from the cell's filesystem. */
  async readFile(cellId: string, path: string): Promise<{ content: string }> {
    const raw = await this.request<{ content: string }>(
      "POST",
      `/api/v1/cells/${encodeURIComponent(cellId)}/request`,
      { method: "read_file", params: { path } },
    );
    return { content: raw.content ?? (raw as unknown as string) };
  }

  /** List files in the cell's filesystem. */
  async listFiles(cellId: string, dir?: string): Promise<{ files: string[] }> {
    const raw = await this.request<{ files: string[] }>(
      "POST",
      `/api/v1/cells/${encodeURIComponent(cellId)}/request`,
      { method: "list_files", params: { path: dir } },
    );
    return { files: raw.files ?? [] };
  }

  // ─── Database operations ───

  /** Set a key-value pair in the cell's database. */
  async dbSet(cellId: string, key: string, value: unknown): Promise<void> {
    await this.request("POST", `/api/v1/cells/${encodeURIComponent(cellId)}/request`, {
      method: "db_set",
      params: { key, value },
    });
  }

  /** Get a value from the cell's database. */
  async dbGet(cellId: string, key: string): Promise<{ value: unknown }> {
    const raw = await this.request<{ value: unknown }>(
      "POST",
      `/api/v1/cells/${encodeURIComponent(cellId)}/request`,
      { method: "db_get", params: { key } },
    );
    return { value: raw.value };
  }

  // ─── Generic request ───

  /**
   * Send a generic request to the cell's agent runtime.
   * This calls POST /api/v1/cells/:cell_id/request with { method, params }.
   */
  async request_<T = unknown>(cellId: string, method: string, params?: Record<string, unknown>): Promise<T> {
    return this.request<T>("POST", `/api/v1/cells/${encodeURIComponent(cellId)}/request`, {
      method,
      params: params ?? {},
    });
  }
}

// ─── OnCell client ───

export class OnCell {
  readonly cells: CellsResource;
  private apiKey: string;
  private baseUrl: string;

  constructor(opts: OnCellOptions = {}) {
    this.apiKey = opts.apiKey ?? (typeof process !== "undefined" ? process.env?.ONCELL_API_KEY ?? "" : "");
    if (!this.apiKey) {
      throw new Error("OnCell: apiKey is required. Pass it directly or set ONCELL_API_KEY env var.");
    }
    this.baseUrl = (opts.baseUrl ?? (typeof process !== "undefined" ? process.env?.ONCELL_BASE_URL : undefined) ?? "https://api.oncell.ai").replace(/\/$/, "");
    this.cells = new CellsResource(this.apiKey, this.baseUrl);
  }

  /** List available pricing tiers. */
  async tiers(): Promise<Tier[]> {
    const url = `${this.baseUrl}/api/v1/cells/tiers`;
    const res = await fetch(url, {
      headers: { Authorization: `Bearer ${this.apiKey}` },
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new OnCellError(res.status, body);
    }
    const json = await res.json() as { tiers: Record<string, unknown>[] };
    return (json.tiers || []).map(toTier);
  }
}
