/**
 * DB — persistent key-value database for the cell.
 *
 * Backed by a JSON file on NVMe for the MVP.
 * Will upgrade to SQLite when we add the native dependency.
 */

import { existsSync, mkdirSync, readFileSync, writeFileSync } from "fs";
import { join } from "path";

export class DB {
  private dir: string;
  private dbPath: string;
  private data: Record<string, string> = {};

  constructor(path: string) {
    this.dir = path;
    this.dbPath = join(path, "cell.json");
    mkdirSync(path, { recursive: true });
    this.load();
  }

  private load(): void {
    if (existsSync(this.dbPath)) {
      this.data = JSON.parse(readFileSync(this.dbPath, "utf-8"));
    }
  }

  private flush(): void {
    writeFileSync(this.dbPath, JSON.stringify(this.data));
  }

  async get<T = unknown>(key: string, defaultValue?: T): Promise<T | undefined> {
    const raw = this.data[key];
    if (raw === undefined) return defaultValue;
    return JSON.parse(raw) as T;
  }

  async set(key: string, value: unknown): Promise<void> {
    this.data[key] = JSON.stringify(value);
    this.flush();
  }

  async delete(key: string): Promise<void> {
    delete this.data[key];
    this.flush();
  }

  async keys(prefix: string = ""): Promise<string[]> {
    return Object.keys(this.data).filter(k => k.startsWith(prefix));
  }

  async scan(prefix: string): Promise<Record<string, unknown>> {
    const result: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(this.data)) {
      if (k.startsWith(prefix)) {
        result[k] = JSON.parse(v);
      }
    }
    return result;
  }

  close(): void {
    this.flush();
  }
}
