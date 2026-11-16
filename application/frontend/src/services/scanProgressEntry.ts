import type { Scan } from "../types/domain";

// Local navigation intent, never a backend event or a persisted completion fact.
// The first Progress mount consumes it; a later history visit stays immediate.
const submittedEntries = new Set<string>();
const entryKey = (scan: Pick<Scan, "id" | "mode">) => `${scan.mode}:${scan.id}`;
export function markNewScanForProgress(scan: Pick<Scan, "id" | "mode">) {
  if (submittedEntries.size >= 32) submittedEntries.delete(submittedEntries.values().next().value!);
  submittedEntries.add(entryKey(scan));
}
export function isNewScanProgressEntry(scan: Pick<Scan, "id" | "mode">) { return submittedEntries.has(entryKey(scan)); }
export function consumeNewScanProgressEntry(scan: Pick<Scan, "id" | "mode">) { submittedEntries.delete(entryKey(scan)); }
