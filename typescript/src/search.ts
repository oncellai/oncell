/**
 * Search — vector search primitive for the cell.
 *
 * Embedded search engine backed by a JSON index on NVMe.
 * Index files, search by text similarity. No external service.
 */

import { createHash } from "crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync, statSync, readdirSync } from "fs";
import { join, relative } from "path";

export interface SearchResult {
  path: string;
  content: string;
  score: number;
}

interface Chunk {
  id: string;
  path: string;
  content: string;
  hash: string;
}

export class Search {
  private dir: string;
  private dbPath: string;
  private chunks: Chunk[] = [];
  private embedFn?: (text: string) => Promise<number[]>;

  constructor(path: string, embedFn?: (text: string) => Promise<number[]>) {
    this.dir = path;
    this.dbPath = join(path, "search.json");
    this.embedFn = embedFn;
    mkdirSync(path, { recursive: true });
    this.load();
  }

  private load(): void {
    if (existsSync(this.dbPath)) {
      this.chunks = JSON.parse(readFileSync(this.dbPath, "utf-8"));
    }
  }

  private flush(): void {
    writeFileSync(this.dbPath, JSON.stringify(this.chunks));
  }

  async index(path: string, glob: string = "**/*"): Promise<number> {
    const files = walkFiles(path).filter(f => matchGlob(relative(path, f), glob));
    let indexed = 0;

    for (const filepath of files) {
      const content = readFileSync(filepath, "utf-8");
      const hash = createHash("sha256").update(content).digest("hex").slice(0, 16);
      const relPath = relative(path, filepath);

      const existing = this.chunks.find(c => c.path === relPath);
      if (existing && existing.hash === hash) continue;

      // Remove old chunks for this file
      this.chunks = this.chunks.filter(c => c.path !== relPath);

      const parts = chunkCode(content, relPath);
      for (let i = 0; i < parts.length; i++) {
        this.chunks.push({ id: `${relPath}:${i}`, path: relPath, content: parts[i], hash });
        indexed++;
      }
    }

    this.flush();
    return indexed;
  }

  async query(query: string, topK: number = 10): Promise<SearchResult[]> {
    return this.textSearch(query, topK);
  }

  private textSearch(query: string, topK: number): SearchResult[] {
    const terms = query.toLowerCase().split(/\s+/);
    const scored: SearchResult[] = [];

    for (const chunk of this.chunks) {
      const lower = chunk.content.toLowerCase();
      const score = terms.reduce((s, t) => s + (lower.includes(t) ? 1 : 0), 0) / Math.max(terms.length, 1);
      if (score > 0) {
        scored.push({ path: chunk.path, content: chunk.content, score });
      }
    }

    scored.sort((a, b) => b.score - a.score);
    return scored.slice(0, topK);
  }

  get chunkCount(): number {
    return this.chunks.length;
  }

  close(): void {
    this.flush();
  }
}

function chunkCode(content: string, _path: string, maxLines = 50): string[] {
  const lines = content.split("\n");
  if (lines.length <= maxLines) return [content];

  const chunks: string[] = [];
  let current: string[] = [];

  for (const line of lines) {
    const stripped = line.trim();
    const isBoundary =
      stripped.startsWith("def ") ||
      stripped.startsWith("async def ") ||
      stripped.startsWith("class ") ||
      stripped.startsWith("function ") ||
      stripped.startsWith("export ") ||
      stripped.startsWith("const ") ||
      stripped.startsWith("pub fn ") ||
      stripped.startsWith("func ");

    if (isBoundary && current.length > 5) {
      chunks.push(current.join("\n"));
      current = [];
    }

    current.push(line);

    if (current.length >= maxLines) {
      chunks.push(current.join("\n"));
      current = [];
    }
  }

  if (current.length > 0) chunks.push(current.join("\n"));
  return chunks;
}

function walkFiles(dir: string): string[] {
  const results: string[] = [];
  if (!existsSync(dir)) return results;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      results.push(...walkFiles(full));
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
