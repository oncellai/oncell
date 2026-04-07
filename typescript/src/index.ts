// Public API — REST client
export { OnCell, OnCellError } from "./client.js";
export type { Cell, Tier, Domain, CellCreateOptions, OnCellOptions, FileEntry } from "./client.js";

// Internal runtime modules (Cell, Store, DB, Search, Journal, etc.) are still
// in this package for the host-agent runtime but are NOT part of the public API.
// Import them directly if needed: import { Cell } from "oncell/dist/cell.js"
