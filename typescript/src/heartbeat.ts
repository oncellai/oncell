/**
 * Heartbeat — keeps the cell alive during long-running operations.
 *
 * Without heartbeat, a cell running a 45-min test suite would get
 * paused at 30 min because no API requests came in.
 */

export class Heartbeat {
  private cellId: string;
  private url: string;
  private intervalMs: number;
  private timer?: ReturnType<typeof setInterval>;
  private _running = false;

  constructor(cellId: string, controlPlaneUrl?: string, intervalSecs = 60) {
    this.cellId = cellId;
    this.url = controlPlaneUrl || process.env.ONCELL_CONTROL_PLANE_URL || "http://localhost:4000";
    this.intervalMs = intervalSecs * 1000;
  }

  start(): void {
    if (this._running) return;
    this._running = true;
    this.timer = setInterval(() => this.ping(), this.intervalMs);
  }

  stop(): void {
    this._running = false;
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = undefined;
    }
  }

  get isRunning(): boolean {
    return this._running;
  }

  async ping(): Promise<void> {
    try {
      await fetch(`${this.url}/cells/${this.cellId}/heartbeat`, { method: "POST" });
    } catch {
      // Heartbeat failure is non-fatal
    }
  }
}
