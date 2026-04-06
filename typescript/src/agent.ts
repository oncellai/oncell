/**
 * Agent — the developer-facing base class.
 *
 * Developers subclass Agent to define their coding agent:
 *
 *     import { Agent, Cell } from "@oncell/sdk";
 *
 *     class MyAgent extends Agent {
 *       static cell = { compute: "2cpu-4gb", storage: "10gb" };
 *
 *       async setup(ctx: Cell) {
 *         await ctx.shell("git clone https://github.com/acme/app /cell/work");
 *       }
 *
 *       async onRequest(ctx: Cell, method: string, params: Record<string, any>) {
 *         if (method === "generate") return this.generate(ctx, params.instruction);
 *         throw new Error(`unknown method: ${method}`);
 *       }
 *
 *       async generate(ctx: Cell, instruction: string) {
 *         const files = await ctx.search.query(instruction);
 *         return { output: "done", files: files.length };
 *       }
 *     }
 *
 *     export default MyAgent;
 */

import type { Cell } from "./cell.js";

export abstract class Agent {
  static cell: Record<string, any> = {};

  async setup(ctx: Cell): Promise<void> {}

  async onRequest(ctx: Cell, method: string, params: Record<string, any>): Promise<any> {
    const handler = (this as any)[method];
    if (!handler || typeof handler !== "function" || method.startsWith("_")) {
      throw new Error(`unknown method: ${method}`);
    }
    return handler.call(this, ctx, ...Object.values(params));
  }

  async teardown(ctx: Cell): Promise<void> {}
}
