/**
 * Store — filesystem primitive for the cell.
 *
 * Read, write, list, and delete files on the cell's NVMe storage.
 */

import { existsSync, mkdirSync, readFileSync, writeFileSync, unlinkSync, statSync, readdirSync } from "fs";
import { join, relative, dirname, resolve } from "path";
import { globSync } from "fs";

export class Store {
  private root: string;

  constructor(path: string) {
    this.root = path;
    mkdirSync(path, { recursive: true });
  }

  get rootDir(): string {
    return this.root;
  }

  async write(path: string, content: string | Buffer): Promise<void> {
    const full = this.resolve(path);
    mkdirSync(dirname(full), { recursive: true });
    writeFileSync(full, content);
  }

  async read(path: string): Promise<string> {
    return readFileSync(this.resolve(path), "utf-8");
  }

  async readBytes(path: string): Promise<Buffer> {
    return readFileSync(this.resolve(path));
  }

  async exists(path: string): Promise<boolean> {
    return existsSync(this.resolve(path));
  }

  async delete(path: string): Promise<void> {
    const full = this.resolve(path);
    if (existsSync(full)) unlinkSync(full);
  }

  async list(path: string = ".", glob: string = "**/*"): Promise<string[]> {
    const base = this.resolve(path);
    if (!existsSync(base)) return [];
    return walkDir(base).filter(f => matchGlob(relative(base, f), glob)).map(f => relative(this.root, f));
  }

  async size(path: string): Promise<number> {
    return statSync(this.resolve(path)).size;
  }

  async diskUsage(): Promise<number> {
    let total = 0;
    for (const file of walkDir(this.root)) {
      total += statSync(file).size;
    }
    return total;
  }

  private resolve(path: string): string {
    const full = resolve(this.root, path);
    if (!full.startsWith(resolve(this.root))) {
      throw new Error(`Path traversal denied: ${path}`);
    }
    return full;
  }
}

function walkDir(dir: string): string[] {
  const results: string[] = [];
  if (!existsSync(dir)) return results;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      results.push(...walkDir(full));
    } else {
      results.push(full);
    }
  }
  return results;
}

function matchGlob(path: string, pattern: string): boolean {
  const regex = pattern
    .replace(/\*\*/g, "{{GLOBSTAR}}")
    .replace(/\*/g, "[^/]*")
    .replace(/\{\{GLOBSTAR\}\}/g, ".*");
  return new RegExp(`^${regex}$`).test(path);
}
