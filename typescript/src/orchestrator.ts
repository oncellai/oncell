/**
 * Orchestrator — durable workflow primitive.
 *
 * Run multi-step workflows with automatic checkpointing.
 * Supports sync execution, async fire-and-forget, and streaming.
 */

import { Journal } from "./journal.js";
import { randomUUID } from "crypto";

export interface Step {
  name: string;
  fn: (context: Record<string, unknown>) => Promise<unknown>;
  retry?: number;
  timeout?: number;
}

export interface StepResult {
  name: string;
  result: unknown;
  status: "done" | "failed" | "skipped";
  durationMs: number;
  error?: string;
}

export interface TaskStatus {
  taskId: string;
  status: "running" | "done" | "failed";
  stepsDone: number;
  stepsTotal: number;
  results: StepResult[];
  error?: string;
}

export class Orchestrator {
  private name: string;
  private journal: Journal;
  private tasks = new Map<string, TaskStatus>();

  constructor(name: string, journal: Journal) {
    this.name = name;
    this.journal = journal;
  }

  /**
   * Execute steps sequentially. Each step is journaled.
   * Returns dict of {stepName: result}.
   */
  async run(steps: Step[]): Promise<Record<string, unknown>> {
    const context: Record<string, unknown> = {};

    for (const step of steps) {
      const result = await this.executeStep(step, context);
      context[step.name] = result.result;

      if (result.status === "failed") {
        throw new Error(`Step '${step.name}' failed: ${result.error}`);
      }
    }

    return context;
  }

  /**
   * Fire-and-forget execution. Returns taskId immediately.
   */
  async spawn(steps: Step[]): Promise<string> {
    const taskId = randomUUID().slice(0, 8);
    const status: TaskStatus = {
      taskId,
      status: "running",
      stepsDone: 0,
      stepsTotal: steps.length,
      results: [],
    };
    this.tasks.set(taskId, status);

    (async () => {
      try {
        const context: Record<string, unknown> = {};
        for (const step of steps) {
          const result = await this.executeStep(step, context);
          context[step.name] = result.result;
          status.stepsDone++;
          status.results.push(result);
          if (result.status === "failed") {
            status.status = "failed";
            status.error = result.error;
            return;
          }
        }
        status.status = "done";
      } catch (e: any) {
        status.status = "failed";
        status.error = e.message;
      }
    })();

    return taskId;
  }

  /**
   * Execute steps and yield progress events.
   */
  async *stream(steps: Step[]): AsyncGenerator<Record<string, unknown>> {
    const context: Record<string, unknown> = {};
    const total = steps.length;

    for (let i = 0; i < steps.length; i++) {
      const step = steps[i];

      yield { step: step.name, status: "starting", progress: i / total };

      const result = await this.executeStep(step, context);
      context[step.name] = result.result;

      yield {
        step: step.name,
        status: result.status,
        progress: (i + 1) / total,
        durationMs: result.durationMs,
        error: result.error,
      };

      if (result.status === "failed") return;
    }

    yield { status: "done", progress: 1.0 };
  }

  /**
   * Check status of a spawned task.
   */
  status(taskId: string): TaskStatus | undefined {
    return this.tasks.get(taskId);
  }

  private async executeStep(step: Step, context: Record<string, unknown>): Promise<StepResult> {
    const tag = `${this.name}:${step.name}`;
    const attempts = (step.retry ?? 0) + 1;

    for (let attempt = 0; attempt < attempts; attempt++) {
      const start = Date.now();
      try {
        const fn = async () => step.fn(context);

        let result: unknown;
        if (step.timeout) {
          result = await Promise.race([
            this.journal.durable(tag, fn, step.name, attempt),
            new Promise((_, reject) => setTimeout(() => reject(new Error("timeout")), step.timeout)),
          ]);
        } else {
          result = await this.journal.durable(tag, fn, step.name, attempt);
        }

        return { name: step.name, result, status: "done", durationMs: Date.now() - start };
      } catch (e: any) {
        if (attempt === attempts - 1) {
          return { name: step.name, result: null, status: "failed", durationMs: Date.now() - start, error: e.message };
        }
      }
    }

    return { name: step.name, result: null, status: "failed", durationMs: 0, error: "exhausted retries" };
  }
}
