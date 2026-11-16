import type { ScanStatus } from "../types/domain";

// Presentation only: animation never advances a task or changes its percentage.
export function progressMotionState(status: ScanStatus, disconnected: boolean, reduced: boolean) {
  if (disconnected || reduced) return "still";
  if (status === "running") return "running";
  if (status === "completed") return "complete";
  return "still";
}
