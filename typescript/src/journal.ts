/**
 * Journal — durable execution primitive.
 *
 * Append-only WAL on disk. Every step is recorded with its result.
 * On crash, replayed steps return cached results instead of re-executing.
 */

import { createHash } from "crypto";
import { existsSync, mkdirSync, readFileSync, appendFileSync, unlinkSync, writeFileSync } from "fs";
import { join } from "path";

interface JournalEntry {
  step: number;
  tag: string;
  argsHash: string;
  result: unknown;
  ts: number;
}

export class Journal {
  private dir: string;
  private walPath: string;
  private entries = new Map<string, JournalEntry>();
  private stepCounter = 0;

  constructor(path: string) {
    this.dir = path;
    this.walPath = join(path, "wal.jsonl");
    mkdirSync(path, { recursive: true });
    this.load();
  }

  private load(): void {
    if (!existsSync(this.walPath)) return;
    const lines = readFileSync(this.walPath, "utf-8").split("\n");
    for (const line of lines) {
      if (!line.trim()) continue;
      const data = JSON.parse(line);
      const key = `${data.step}:${data.tag}:${data.args_hash}`;
      this.entries.set(key, {
        step: data.step,
        tag: data.tag,
        argsHash: data.args_hash,
        result: data.result,
        ts: data.ts,
      });
      this.stepCounter = Math.max(this.stepCounter, data.step + 1);
    }
  }

  async durable<T>(tag: string, fn: () => Promise<T>, ...args: unknown[]): Promise<T> {
    const step = this.stepCounter++;
    const argsHash = hashArgs(args);
    const key = `${step}:${tag}:${argsHash}`;

    const cached = this.entries.get(key);
    if (cached !== undefined) {
      return cached.result as T;
    }

    const result = await fn();
    const entry: JournalEntry = { step, tag, argsHash, result, ts: Date.now() / 1000 };
    this.entries.set(key, entry);

    const record = JSON.stringify({
      step,
      tag,
      args_hash: argsHash,
      result,
      ts: entry.ts,
    });
    appendFileSync(this.walPath, record + "\n");

    return result;
  }

  reset(): void {
    this.entries.clear();
    this.stepCounter = 0;
    if (existsSync(this.walPath)) unlinkSync(this.walPath);
  }

  get entryCount(): number {
    return this.entries.size;
  }
}

function hashArgs(args: unknown[]): string {
  const raw = JSON.stringify(args);
  return createHash("sha256").update(raw).digest("hex").slice(0, 16);
}
