/** Format a process value. `null` means the device reported "not available": never show 0. */
export function formatValue(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toFixed(digits);
}

/** A reading is stale once it is older than three poll intervals (DESIGN.md section 6.2). */
export function isStale(lastUpdateMs: number, nowMs: number, pollIntervalS: number): boolean {
  return nowMs - lastUpdateMs > pollIntervalS * 3 * 1000;
}
