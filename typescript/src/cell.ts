/**
 * Cell — the core primitive.
 *
 * An isolated compute environment. One per customer.
 * Provides shell, store, db, search, journal, and orchestration.
 */

import { execSync } from "child_process";
import { mkdirSync } from "fs";
import { join } from "path";
import { Store } from "./store.js";
import { DB } from "./db.js";
import { Search } from "./search.js";
import { Journal } from "./journal.js";
import { Orchestrator } from "./orchestrator.js";
import { Heartbeat } from "./heartbeat.js";

export interface ShellResult {
  stdout: string;
  stderr: string;
  exitCode: number;
  failed: boolean;
}

export class Cell {
  readonly id: string;
  readonly store: Store;
  readonly db: DB;
  readonly search: Search;
  readonly journal: Journal;
  readonly heartbeat: Heartbeat;
  private dir: string;
  private orchestrators = new Map<string, Orchestrator>();

  constructor(
    cellId: string,
    opts?: { baseDir?: string; controlPlaneUrl?: string; heartbeatInterval?: number }
  ) {
    this.id = cellId;
    this.dir = join(opts?.baseDir ?? "/cells", cellId);
    mkdirSync(this.dir, { recursive: true });

    this.store = new Store(join(this.dir, "work"));
    this.db = new DB(join(this.dir, "data"));
    this.search = new Search(join(this.dir, "index"));
    this.journal = new Journal(join(this.dir, "journal"));
    this.heartbeat = new Heartbeat(cellId, opts?.controlPlaneUrl, opts?.heartbeatInterval);
  }

  get workDir(): string {
    return join(this.dir, "work");
  }

  orchestrator(name: string = "default"): Orchestrator {
    let orch = this.orchestrators.get(name);
    if (!orch) {
      orch = new Orchestrator(name, this.journal);
      this.orchestrators.set(name, orch);
    }
    return orch;
  }

  async shell(cmd: string, opts?: { cwd?: string; durable?: boolean }): Promise<ShellResult> {
    const cwd = opts?.cwd ?? this.workDir;
    const durable = opts?.durable ?? true;
    mkdirSync(cwd, { recursive: true });

    const exec = async (): Promise<ShellResult> => {
      try {
        const stdout = execSync(cmd, { cwd, encoding: "utf-8", maxBuffer: 50 * 1024 * 1024 });
        return { stdout, stderr: "", exitCode: 0, failed: false };
      } catch (err: any) {
        return {
          stdout: err.stdout?.toString() ?? "",
          stderr: err.stderr?.toString() ?? "",
          exitCode: err.status ?? 1,
          failed: true,
        };
      }
    };

    if (durable) {
      return this.journal.durable("shell", exec, cmd, cwd);
    }
    return exec();
  }
}
